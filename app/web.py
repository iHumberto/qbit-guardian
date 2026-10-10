"""
qbit-guardian — Web UI (Flask).

Serve a pagina de configuracao e endpoints REST para ler/salvar config.json.
Exige HTTP Basic Auth: as credenciais sao provisionadas no startup
(`app/auth.py`) e trocadas pela propria Web UI via `POST /api/credentials`.
"""

import copy
import hashlib
import json
import os
import time
import warnings
import functools
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_from_directory, Response, redirect
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException
import app.guardian as guardian
from app.version import __version__
import app.updates as updates
import app.auth as auth
from app.logger import get_logger

# Suprimir warning "This is a development server" do Flask
warnings.filterwarnings("ignore", message=".*development server.*")

log = get_logger("web")

CONFIG_PATH = os.environ.get("CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"))
STATIC_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

# static_folder=None desliga a rota estatica automatica do Flask. Com ela
# ligada, `/index.html` e `/i18n.js` eram servidos SEM passar pelo
# @requires_auth — so `/` exigia senha. A rota explicita no fim do arquivo
# serve os mesmos arquivos, agora autenticados.
app = Flask(__name__, static_folder=None)

# Corpo maximo aceito. Sem limite, um POST arbitrariamente grande e parseado em
# memoria e gravado no config.json.
MAX_BODY_BYTES = 1 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

METODOS_DE_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}

# Cookie de sessao da tela de login.
COOKIE_SESSAO = "qbg_sessao"
SESSAO_VALIDADE = 7 * 24 * 3600
SAL_SESSAO = "qbit-guardian-sessao"

# Arquivos de static/ servidos SEM autenticacao, porque a tela de login
# precisa deles antes de existir sessao. Sao strings de interface e um icone —
# nenhum dado de configuracao. `index.html` deliberadamente fica de fora.
ARQUIVOS_PUBLICOS = {"login.html", "i18n.js", "favicon.svg"}

# Freio de forca bruta na tela de login: com formulario (em vez do popup do
# navegador) um script consegue tentar milhares de senhas sem atrito.
TENTATIVAS_MAX = 5
JANELA_TENTATIVAS = 300
_tentativas = {}


# ── Auth ────────────────────────────────────────────────────────────────

def _is_auth_enabled():
    """Verifica se autenticacao esta configurada (user ou password preenchidos).

    Desde a v2.2.0 o startup provisiona credenciais, entao em producao isto e
    sempre verdadeiro. Continua existindo como escape hatch consciente para
    quem ja protege a porta por outro meio (proxy reverso com SSO, por
    exemplo): basta esvaziar `webui` — mas o proximo restart gera senha nova.
    """
    cfg = _read_config()
    webui = cfg.get("webui", {})
    return bool(webui.get("user") or webui.get("password"))


def _check_auth(username, password):
    """Verifica credenciais contra config.json > webui.

    Usuario e senha sao SEMPRE os dois verificados, mesmo com o usuario
    errado: encerrar cedo revelaria, pelo tempo de resposta, que o nome existe.
    """
    cfg = _read_config()
    webui = cfg.get("webui", {})
    ok_usuario = auth.verificar_usuario(username or "", webui.get("user") or "")
    ok_senha = auth.verificar_senha(password or "", webui.get("password") or "")
    return ok_usuario and ok_senha


# ── Sessao (tela de login) ──────────────────────────────────────────────

def _marcador_credencial(webui):
    """Impressao curta do par usuario+senha guardado.

    Vai dentro do cookie: trocar usuario ou senha muda o marcador e invalida
    todas as sessoes abertas, sem precisar guardar lista de sessao nenhuma.
    """
    bruto = f"{webui.get('user') or ''}:{webui.get('password') or ''}".encode()
    return hashlib.sha256(bruto).hexdigest()[:16]


def _serializador():
    """Assinador do cookie, ou None se ainda nao ha chave provisionada."""
    webui = _read_config().get("webui") or {}
    chave = webui.get("secret_key")
    if not isinstance(chave, str) or not chave.strip():
        return None
    return URLSafeTimedSerializer(chave, salt=SAL_SESSAO)


def _emitir_sessao():
    """Token assinado para o usuario configurado."""
    serializador = _serializador()
    if serializador is None:
        return None
    webui = _read_config().get("webui") or {}
    return serializador.dumps({"u": webui.get("user"),
                               "v": _marcador_credencial(webui)})


def _sessao_valida():
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return False
    serializador = _serializador()
    if serializador is None:
        return False
    try:
        dados = serializador.loads(token, max_age=SESSAO_VALIDADE)
    except (BadSignature, SignatureExpired):
        return False
    if not isinstance(dados, dict):
        return False
    webui = _read_config().get("webui") or {}
    return (dados.get("u") == webui.get("user")
            and dados.get("v") == _marcador_credencial(webui))


def _quer_html():
    """True quando e navegacao de navegador, nao chamada de API.

    Decide entre redirecionar para a tela de login e devolver 401 em JSON: o
    `fetch` da propria pagina precisa do 401 para mostrar o erro, enquanto quem
    digitou a URL precisa ver a tela.
    """
    if request.path.startswith("/api/"):
        return False
    return "text/html" in (request.headers.get("Accept") or "")


def _auth_required():
    """Manda para a tela de login, ou devolve 401 em JSON.

    Sem `WWW-Authenticate`: era ele que fazia o navegador abrir o popup nativo
    de usuario e senha, no lugar da tela de login da aplicacao.
    """
    if _quer_html():
        return redirect("/login")
    return jsonify({"error": "autenticacao necessaria"}), 401


def requires_auth(f):
    """Exige sessao valida OU HTTP Basic Auth.

    As duas formas convivem de proposito: o navegador usa a tela de login e o
    cookie; `curl` e o hook do webhook continuam mandando Basic Auth, que nao
    tem tela para preencher.

    Com `webui.user` e `webui.password` vazios a autenticacao fica desligada —
    escape hatch para quem ja protege a porta por outro meio.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _is_auth_enabled():
            return f(*args, **kwargs)
        if _sessao_valida():
            return f(*args, **kwargs)
        auth_header = request.authorization
        if auth_header and _check_auth(auth_header.username, auth_header.password):
            return f(*args, **kwargs)
        return _auth_required()
    return decorated


# ── Freio de forca bruta ────────────────────────────────────────────────

def _chave_tentativa():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def _bloqueado_por_tentativas():
    agora = time.time()
    recentes = [t for t in _tentativas.get(_chave_tentativa(), []) if agora - t < JANELA_TENTATIVAS]
    _tentativas[_chave_tentativa()] = recentes
    return len(recentes) >= TENTATIVAS_MAX


def _registrar_falha():
    _tentativas.setdefault(_chave_tentativa(), []).append(time.time())


def _limpar_tentativas():
    _tentativas.pop(_chave_tentativa(), None)


# ── CSRF ────────────────────────────────────────────────────────────────

def _origem_confiavel():
    """True quando a escrita NAO veio de outro site.

    O Basic Auth e reenviado pelo navegador automaticamente, entao sem esta
    checagem qualquer pagina que a vitima visitasse podia reconfigurar o
    guardian com as credenciais dela — apontar `qbit.url` para fora (e vazar a
    API key do qBittorrent no header) ou transformar `.mkv` em extensao
    perigosa (e apagar a biblioteca do disco).

    Navegador atual sempre manda `Sec-Fetch-Site`. Ausente = cliente nao-
    navegador (curl, script do webhook), que nao sofre CSRF.
    """
    site = request.headers.get("Sec-Fetch-Site")
    if site is not None:
        return site in ("same-origin", "same-site", "none")

    origem = request.headers.get("Origin")
    if origem:
        return urlparse(origem).netloc == request.host

    return True


@app.before_request
def _bloqueia_origem_externa():
    if request.method not in METODOS_DE_ESCRITA:
        return None
    if not _origem_confiavel():
        log.warning(f"escrita bloqueada: origem externa em {request.path}")
        return jsonify({"error": "origem nao permitida"}), 403
    return None


@app.after_request
def _headers_de_seguranca(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.errorhandler(413)
def _corpo_grande(_erro):
    return jsonify({"error": f"corpo acima de {MAX_BODY_BYTES} bytes"}), 413


def _exige_json():
    """415 quando o corpo nao e application/json.

    Content-Type simples (`text/plain`, `multipart/form-data`) nao dispara
    preflight de CORS — era por ai que o CSRF passava.
    """
    if request.is_json:
        return None
    return jsonify({"error": "Content-Type deve ser application/json"}), 415


# ── Helpers ────────────────────────────────────────────────────────────

def _read_config():
    return guardian.load_config()


def _write_config(data):
    """Persiste config.json no disco E atualiza cache do guardian (thread-safe)."""
    guardian.save_config(data)


def deep_merge(base, override):
    """Merge profundo: override sobrescreve base, preservando campos ausentes."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _config_para_leitura():
    """Copia do config sem a senha da Web UI.

    A copia e profunda de proposito: `load_config()` devolve o objeto em cache,
    e remover a senha dele apagaria a credencial do processo inteiro.
    """
    cfg = copy.deepcopy(_read_config())
    webui = cfg.get("webui")
    if isinstance(webui, dict):
        webui.pop("password", None)
        # A chave de sessao assina o cookie: quem a tiver forja login.
        webui.pop("secret_key", None)
    return cfg


# ── Rotas ──────────────────────────────────────────────────────────────

@app.route("/login")
def pagina_login():
    """Tela de login. Publica por definicao.

    Quem ja tem sessao valida nao precisa dela — vai direto para o painel,
    senao o usuario ficaria olhando um formulario que nao precisa preencher.
    """
    if _is_auth_enabled() and _sessao_valida():
        return redirect("/")
    return send_from_directory(STATIC_DIR, "login.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    erro = _exige_json()
    if erro:
        return erro

    if _bloqueado_por_tentativas():
        resposta = jsonify({"error": "tentativas demais, aguarde alguns minutos"})
        resposta.headers["Retry-After"] = str(JANELA_TENTATIVAS)
        return resposta, 429

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "corpo invalido"}), 400

    if not _check_auth(data.get("user") or "", data.get("password") or ""):
        _registrar_falha()
        log.warning("login recusado")
        return jsonify({"error": "usuario ou senha invalidos"}), 401

    token = _emitir_sessao()
    if token is None:
        return jsonify({"error": "sessao indisponivel: secret_key ausente"}), 500

    _limpar_tentativas()
    resposta = jsonify({"status": "ok"})
    resposta.set_cookie(
        COOKIE_SESSAO, token,
        max_age=SESSAO_VALIDADE,
        httponly=True,       # fora do alcance de qualquer JS
        samesite="Lax",      # o cookie nao acompanha POST de outro site
        path="/",
    )
    return resposta


@app.route("/api/logout", methods=["POST"])
def api_logout():
    resposta = jsonify({"status": "ok"})
    resposta.delete_cookie(COOKIE_SESSAO, path="/")
    return resposta


@app.route("/")
@requires_auth
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/config", methods=["GET"])
@requires_auth
def api_get_config():
    try:
        return jsonify(_config_para_leitura())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["POST"])
@requires_auth
def api_save_config():
    erro = _exige_json()
    if erro:
        return erro
    try:
        # Quem barra Content-Type simples e `_exige_json()` acima, nao a
        # ausencia de `force=True` aqui: com o guarda no lugar, os dois se
        # comportam igual. Mutacao verificada — remover o guarda e que reabre
        # o CSRF, e ha teste para isso (S28/TestCSRFOrigemExterna).
        data = request.get_json()
        if isinstance(data, dict):
            # Credenciais nao passam por aqui: trocar senha tem endpoint
            # proprio, que exige a senha atual. Sem esta remocao, um POST de
            # config comum sobrescreveria usuario e senha.
            data.pop("webui", None)
        current = _read_config()
        merged = deep_merge(current, data)
        _write_config(merged)
        return jsonify({"status": "ok"})
    except HTTPException:
        # Corpo acima do limite vira 413 pelo errorhandler, nao 400 generico:
        # o cliente precisa distinguir "payload invalido" de "payload grande".
        raise
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/credentials", methods=["POST"])
@requires_auth
def api_credentials():
    """Troca usuario e/ou senha da Web UI.

    A senha atual e sempre exigida — e a prova de identidade que impede que
    uma sessao esquecida aberta no navegador vire troca de credencial.
    Qualquer um dos dois campos pode ser omitido: quem so quer trocar o nome
    manda `user` + `current_password`.
    """
    erro = _exige_json()
    if erro:
        return erro

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "corpo invalido"}), 400

    cfg = _read_config()
    webui = cfg.get("webui") or {}

    if not auth.verificar_senha(data.get("current_password") or "",
                                webui.get("password") or ""):
        log.warning("troca de credenciais recusada: senha atual incorreta")
        return jsonify({"error": "senha atual incorreta"}), 403

    novo_usuario = (data.get("user") or "").strip()
    nova_senha = data.get("new_password") or ""

    if not novo_usuario and not nova_senha:
        return jsonify({"error": "informe novo usuario ou nova senha"}), 400

    if nova_senha and len(nova_senha) < auth.TAMANHO_MINIMO_SENHA:
        return jsonify({
            "error": f"a nova senha precisa de ao menos "
                     f"{auth.TAMANHO_MINIMO_SENHA} caracteres"
        }), 400

    if novo_usuario:
        webui["user"] = novo_usuario
    if nova_senha:
        webui["password"] = auth.hash_senha(nova_senha)

    cfg["webui"] = webui
    _write_config(cfg)
    log.warning(f"credenciais da Web UI alteradas (usuario: {webui['user']})")
    return jsonify({"status": "ok", "user": webui["user"]})


@app.route("/api/defaults", methods=["GET"])
@requires_auth
def api_defaults():
    """Titulos/templates padrao e variaveis disponiveis por evento.

    A Web UI consome isto em vez de carregar copia das mesmas strings: config
    gravada antes da v2.1.0 nao tem a chave `events`, e sem o default a caixa
    apareceria vazia enquanto o guardian usaria o texto padrao — a tela
    mentiria sobre o que seria enviado.
    """
    return jsonify({
        "notifications": guardian.DEFAULT_NOTIFICATIONS,
        "notification_variables": guardian.NOTIFICATION_VARIABLES,
    })


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/version")
@requires_auth
def api_version():
    """Versao instalada e, quando se sabe, a ultima publicada.

    Atras de autenticacao de proposito: o /api/health e publico porque o
    healthcheck do container o consome, e anunciar a versao exata para quem
    nao esta logado so ajuda quem procura um alvo com versao conhecida.

    `latest` vem `null` quando a consulta nao deu certo (sem internet, API
    fora do ar, rate limit). O rodape simplesmente nao mostra aviso nenhum:
    nao saber se ha versao nova nao e erro que mereca tela.
    """
    ultima = updates.ultima_versao()
    return jsonify({
        "version": __version__,
        "latest": ultima,
        "update_available": updates.ha_atualizacao(__version__, ultima),
    })


@app.route("/api/trigger", methods=["POST"])
@requires_auth
def api_trigger():
    """Forca uma verificacao imediata (acionamento manual ou webhook).

    Nao exige corpo JSON: o hook do qBittorrent faz um POST vazio. A protecao
    contra CSRF aqui vem da checagem de origem em `_bloqueia_origem_externa`.
    """
    try:
        guardian.load_config()
        torrents = guardian.get_torrents()
        current = {t["hash"] for t in torrents}
        new = [t for t in torrents if t["hash"] not in guardian._processed]
        count = len(new)
        for t in new:
            # So marca como processado se a analise foi concluida (torrents sem
            # metadados sao reavaliados no proximo ciclo).
            if guardian.analyze_torrent(t):
                guardian._processed.add(t["hash"])

        # Pass 2: reavalia stalled/no-seeds para TODOS os torrents
        stalled_removed = 0
        for t in torrents:
            if guardian.check_stalled_and_remove(t):
                stalled_removed += 1

        guardian._prune_processed(current)
        guardian.write_heartbeat()
        return jsonify({"status": "ok", "checked": len(torrents), "new": count,
                       "stalled_removed": stalled_removed})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/<path:arquivo>")
def arquivo_estatico(arquivo):
    """Serve static/ — autenticado, menos o que a tela de login precisa.

    `send_from_directory` rejeita path traversal. A rota existe para que
    `/index.html` nao fique publico enquanto `/` pede senha; `i18n.js` e
    `favicon.svg` sao liberados porque a tela de login os carrega antes de
    existir sessao, e nao contem nada alem de strings de interface.
    """
    if arquivo in ARQUIVOS_PUBLICOS:
        return send_from_directory(STATIC_DIR, arquivo)
    return requires_auth(lambda: send_from_directory(STATIC_DIR, arquivo))()


# ── Entrypoint ─────────────────────────────────────────────────────────

def start_web(host="0.0.0.0", port=5000):
    """Inicia o servidor Flask (bloqueante)."""
    log.info(f"Web UI em http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)
