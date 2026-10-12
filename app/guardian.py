"""
qbit-guardian — Motor principal.

Monitora torrents ativos no qBittorrent e remove arquivos maliciosos,
bloqueia no Sonarr/Radarr e dispara nova busca.
Configuravel via config.json + Web UI (web.py).
"""

import os
import re
import json
import time
import logging
import threading
import requests
import urllib3
from datetime import datetime, timezone
from urllib.parse import urlparse

# Suprimir warnings de SSL inseguro (homelab com certificados auto-assinados)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app.logger import get_logger, VERBOSE
import app.auth as auth

log = get_logger("guardian")

CONFIG_PATH = os.environ.get("CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"))

MAX_PROCESSED_SIZE = 10_000

# Intervalo padrao entre tentativas de reconexao ao qBittorrent (segundos).
# Independente de check_interval_seconds: este e o ritmo do retry de conexao,
# aquele e o ritmo da verificacao periodica de torrents.
DEFAULT_RETRY_INTERVAL = 120

# Familia de excecoes de transporte na comunicacao com o qBittorrent. O loop
# principal antes so capturava ConnectionError; SSLError e Timeout/ReadTimeout
# escapavam para o `except Exception` generico (apenas loga, sem reconectar).
# ConnectionError ja cobre SSLError/ProxyError/ConnectTimeout e Timeout cobre
# ReadTimeout/ConnectTimeout — a lista explicita documenta a intencao e resiste
# a mudancas na hierarquia de excecoes do requests.
TRANSPORT_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.SSLError,
    requests.exceptions.Timeout,
    requests.exceptions.ReadTimeout,
)

# Eventos de notificacao: titulo e template padrao de cada um. Os templates
# reproduzem exatamente as mensagens que eram hardcoded ate a v2.0.8 — quem
# nao mexer na config continua recebendo o mesmo texto de sempre.
DEFAULT_NOTIFICATIONS = {
    "optimized": {
        "title": "⚡ Torrent Otimizado",
        "template": "Nome: {{torrentName}}\nArquivos de midia priorizados.",
    },
    "removed": {
        "title": "⚠️ Torrent Removido",
        "template": "Nome: {{torrentName}}\nMotivo: {{reason}}",
    },
    "stalled": {
        "title": "🗑️ Torrent Removido (stalled)",
        "template": "Nome: {{torrentName}}\nMotivo: {{reason}}",
    },
}

# Variaveis que cada evento disponibiliza no template. A Web UI le esta mesma
# lista para mostrar ao usuario o que ele pode usar em cada caixa.
NOTIFICATION_VARIABLES = {
    "optimized": ["torrentName", "priorityMedia", "priorityAux", "mediaCount"],
    "removed": ["torrentName", "reason", "extensions"],
    "stalled": ["torrentName", "reason", "state", "stalledTime"],
}

# ── Config loader ──────────────────────────────────────────────────────
_config = None
_config_mtime = None
_config_lock = threading.Lock()


def _marca_mtime():
    """Registra o mtime do config.json recem-lido/escrito.

    Guardar isso e o que permite ao `get_config` saber que o arquivo mudou por
    fora (edicao manual, outro processo) sem reler o JSON a cada chamada.
    """
    global _config_mtime
    try:
        _config_mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        _config_mtime = None


def config_default():
    """Config de uma instalacao nova, montada na memoria.

    Vive fora do `load_config()` porque nao e so o arquivo inicial: a rota
    `/api/demo-config` serve esta mesma estrutura para o tour guiado, e uma
    segunda copia dos defaults sairia de sincronia no primeiro campo novo.
    """
    return {
        "qbit": {"url": "", "api_key": ""},
        "sonarr": {"url": "", "api_key": ""},
        "radarr": {"url": "", "api_key": ""},
        "guardian": {
            "check_interval_seconds": 300,
            "reevaluate_interval_seconds": 300,
            "retry_interval_seconds": 120,
            "valid_media_extensions": [
                ".mkv", ".mp4", ".avi", ".mov", ".m4v",
                ".ts", ".wmv", ".flv", ".webm"
            ],
            "dangerous_extensions": [
                ".exe", ".scr", ".bat", ".cmd", ".vbs",
                ".js", ".com", ".pif", ".msi", ".dll",
                ".ps1", ".sh", ".bin"
            ],
            "remove_stalled": False,
            "stalled_time": 0,
            "stalled_unit": "hours",
            "remove_no_seeds": False,
            "no_seeds_time": 0,
            "no_seeds_unit": "hours",
            "remove_slow": False,
            "slow_speed": 0,
            "slow_speed_unit": "KiB",
            "slow_time": 0,
            "slow_unit": "minutes",
            "priority_media": 7,
            "priority_normal": 1,
            "priority_skip": 0
        },
        "notifications": {
            "apprise_url": "",
            "enabled": True,
            "events": {
                ev: {"enabled": True, **spec}
                for ev, spec in DEFAULT_NOTIFICATIONS.items()
            },
        },
        "webui": {"user": "", "password": ""}
    }


def load_config():
    """Le config.json (thread-safe). Cria default se nao existir."""
    global _config
    with _config_lock:
        if not os.path.exists(CONFIG_PATH):
            default = config_default()
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(default, f, indent=2)
            _config = default
            _marca_mtime()
            log.info("config.json criado com valores default — configure pela Web UI")
            return _config
        with open(CONFIG_PATH, "r") as f:
            _config = json.load(f)
        _marca_mtime()
    return _config


def get_config():
    """Retorna a config, recarregando quando o arquivo mudou no disco.

    Antes isto devolvia o cache e so tocava o disco com `_config is None`.
    Consequencia: edicao feita no `config.json` fora da Web UI nao surtia
    efeito nenhum ate reiniciar o container — e o loop trazia o comentario
    "Recarrega config a cada iteracao para detectar mudancas no intervalo",
    descrevendo uma recarga que nao acontecia. Mudanca pela Web UI funcionava
    porque `save_config` atualiza o cache, o que escondia o defeito.

    A invalidacao e por `mtime`, nao por releitura cega: `stat` e ordens de
    grandeza mais barato que abrir e parsear o JSON, e isto e chamado uma vez
    por torrent em `analyze_torrent`/`is_stalled`. Com o arquivo parado — o
    caso normal — o custo e uma syscall por chamada.
    """
    global _config
    if _config is None:
        return load_config()
    try:
        if os.path.getmtime(CONFIG_PATH) != _config_mtime:
            return load_config()
    except OSError:
        # arquivo sumiu ou ilegivel: segue com o que esta em memoria, que e
        # melhor que estourar no meio de um ciclo
        pass
    return _config


def save_config(data):
    """Salva config.json (thread-safe)."""
    with _config_lock:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        global _config
        _config = data
        # sem isto, a propria gravacao pela Web UI deixaria o cache "velho"
        # aos olhos do get_config, forcando uma releitura inutil em seguida
        _marca_mtime()


# ── qBitTorrent session ────────────────────────────────────────────────
_qbit_session = None
_qbit_base = None


def get_qbit_session():
    global _qbit_session, _qbit_base
    cfg = get_config()
    url = cfg["qbit"]["url"].rstrip("/")
    key = cfg["qbit"]["api_key"]

    base = url
    if _qbit_session is None or _qbit_base != base:
        _qbit_session = requests.Session()
        _qbit_session.verify = False  # Homelab: certificados auto-assinados
        _qbit_session.headers.update({"Authorization": f"Bearer {key}"})
        _qbit_base = base
    return _qbit_session, _qbit_base


def qbit_login():
    sess, base = get_qbit_session()
    log.debug(f"HTTP GET {base}/api/v2/app/version")
    r = sess.get(f"{base}/api/v2/app/version", timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"qBittorrent: HTTP {r.status_code}")
    log.info(f"Conectado ao qBittorrent v{r.text.strip()}")


def get_torrents():
    sess, base = get_qbit_session()
    log.debug(f"HTTP GET {base}/api/v2/torrents/info")
    r = sess.get(f"{base}/api/v2/torrents/info", timeout=10)
    r.raise_for_status()
    return r.json()


def get_files(torrent_hash):
    sess, base = get_qbit_session()
    log.debug(f"HTTP GET {base}/api/v2/torrents/files?hash={torrent_hash[:8]}")
    r = sess.get(f"{base}/api/v2/torrents/files",
                 params={"hash": torrent_hash}, timeout=10)
    r.raise_for_status()
    return r.json()


def remove_torrent(torrent_hash):
    sess, base = get_qbit_session()
    log.debug(f"HTTP POST {base}/api/v2/torrents/delete (hash={torrent_hash[:8]})")
    sess.post(f"{base}/api/v2/torrents/delete",
              data={"hashes": torrent_hash, "deleteFiles": "true"}, timeout=10)
    log.error(f"Removido: {torrent_hash}")


# O qBittorrent aceita APENAS estas prioridades de arquivo. Qualquer outro
# valor devolve HTTP 400 "A prioridade nao e valida" — que antes passava em
# silencio (o retorno do POST nao era conferido), deixando os arquivos sem
# priorizacao nenhuma.
#   -1 = sem prioridade | 0 = nao baixar | 1 = normal | 6 = alta | 7 = maxima
VALID_FILE_PRIORITIES = {-1, 0, 1, 6, 7}


def set_file_priority(torrent_hash, file_id, priority):
    if priority not in VALID_FILE_PRIORITIES:
        log.warning(f"prioridade de arquivo invalida: {priority} "
                    f"(validas: -1, 0, 1, 6, 7) — arquivo NAO priorizado. "
                    f"Corrija priority_media/priority_normal/priority_skip na config.")
        return

    sess, base = get_qbit_session()
    r = sess.post(f"{base}/api/v2/torrents/filePrio",
                  data={"hash": torrent_hash, "id": file_id, "priority": priority},
                  timeout=10)
    if r.status_code != 200:
        log.warning(f"filePrio falhou (hash={torrent_hash[:8]} id={file_id} "
                    f"priority={priority}): HTTP {r.status_code} "
                    f"{r.text.strip()[:60]}")


# ── Notificacoes ───────────────────────────────────────────────────────

def _notification_event(cfg, event):
    """Resolve titulo/template/enabled de um evento, com fallback seguro.

    Config gravada antes da v2.1.0 nao tem a chave `events` — e `load_config()`
    nao faz merge com os defaults quando o arquivo existe. Entao cada campo cai
    no default individualmente: titulo ou template vazio/nao-string tambem
    voltam ao padrao, para uma caixa apagada na Web UI nao virar notificacao em
    branco.
    """
    spec = DEFAULT_NOTIFICATIONS[event]
    cfgev = ((cfg.get("notifications") or {}).get("events") or {}).get(event) or {}

    titulo = cfgev.get("title")
    if not isinstance(titulo, str) or not titulo.strip():
        titulo = spec["title"]

    template = cfgev.get("template")
    if not isinstance(template, str) or not template.strip():
        template = spec["template"]

    return {
        "enabled": cfgev.get("enabled", True) is not False,
        "title": titulo,
        "template": template,
    }


def _render_template(template, variaveis):
    """Substitui {{nome}} pelos valores informados.

    Placeholder desconhecido fica literal no texto: um erro de digitacao na
    Web UI aparece na notificacao em vez de sumir em silencio.
    """
    def troca(m):
        nome = m.group(1).strip()
        if nome in variaveis:
            return str(variaveis[nome])
        return m.group(0)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", troca, template)


def notify(event, **variaveis):
    """Envia a notificacao de um evento, se ela estiver habilitada.

    Dois niveis de liga/desliga, como no prototipo: o geral
    (`notifications.enabled`) e o do tipo (`events.<nome>.enabled`). O envio so
    acontece com os dois ligados.
    """
    cfg = get_config()
    notif = cfg.get("notifications") or {}

    if notif.get("enabled", True) is False:
        log.debug(f"notificacao '{event}' suprimida: desligada no geral")
        return

    ev = _notification_event(cfg, event)
    if not ev["enabled"]:
        log.debug(f"notificacao '{event}' suprimida: tipo desligado")
        return

    send_notification(ev["title"], _render_template(ev["template"], variaveis))


# Esquemas em que o authority e um endereco de servidor, nao credencial.
ESQUEMAS_COM_HOST_PUBLICO = {"http", "https"}


def _destino_de(url):
    """Identifica o backend de notificacao sem revelar credencial.

    Em http/https o authority e um endereco e ajuda a depurar. Nos esquemas
    proprios do Apprise o authority E o segredo — `tgram://TOKEN/CHAT`,
    `discord://ID/TOKEN`, `pover://USER/APP` —, entao desses so o esquema sai
    no log.
    """
    try:
        partes = urlparse(url)
    except Exception:
        return "<url invalida>"

    esquema = (partes.scheme or "").lower()
    if not esquema:
        return "<url invalida>"

    if esquema not in ESQUEMAS_COM_HOST_PUBLICO or partes.username or partes.password:
        return f"{esquema}://..."

    try:
        porta = f":{partes.port}" if partes.port else ""
    except ValueError:
        # Authority com porta nao numerica: nao da para separar host de
        # credencial com seguranca, entao nao arrisca.
        return f"{esquema}://..."

    return f"{esquema}://{partes.hostname or '<sem host>'}{porta}"


def send_notification(title, message):
    cfg = get_config()
    url = cfg["notifications"].get("apprise_url", "")
    if not url:
        return
    try:
        # So o host: a apprise_url pode embutir credencial no caminho ou na
        # query (a chave de configuracao do servidor Apprise, um token), e com
        # LOG_LEVEL=DEBUG ela iria inteira para o `docker logs`.
        log.debug(f"HTTP POST {_destino_de(url)} (Apprise: {title})")
        requests.post(url, data={"title": title, "body": message},
                     timeout=10, verify=False)
    except Exception as e:
        log.error(f"Apprise: {e}")


# ── Bloqueio e re-busca ────────────────────────────────────────────────

def _normalize_title(value):
    """Normaliza nome para comparacao por palavras.

    Minusculas, qualquer sequencia de nao-alfanumericos vira um espaco, e o
    resultado e envolto em espacos. Necessario porque release names usam
    separadores (`Breaking.Bad.S01E01.1080p.WEB-DL`) enquanto o *Arr devolve o
    titulo com espacos (`Breaking Bad`) — comparar os dois crus nunca casa.

    Os espacos nas pontas forcam alinhamento em limite de palavra: evita que
    um titulo curto case no meio de outra palavra (`Her` em `Where`).
    """
    return " " + re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip() + " "


def _arr_match_by_name(items, torrent_name, title_field="title"):
    """Busca item na lista por match parcial de nome.

    Itens sem titulo (ausente, nulo ou vazio) sao IGNORADOS: `"" in qualquer`
    e sempre True, entao um unico item sem titulo na resposta do *Arr casava
    com qualquer torrent e disparava o re-search na midia errada.

    O match continua sendo por substring (titulo contido no nome do torrent),
    agora sobre a forma normalizada — ver _normalize_title().
    """
    name = _normalize_title(torrent_name)
    for item in items:
        title = _normalize_title(item.get(title_field))
        if title.strip() and title in name:
            return item.get("id")
    return None


# Tamanho de pagina pedido na queue do Radarr/Sonarr. O default da API e 10,
# pequeno demais para uma fila de dezenas de itens.
ARR_QUEUE_PAGE_SIZE = 1000


def _avisa_queue_truncada(arr_type, resposta):
    """Avisa quando a queue tem mais itens do que uma pagina devolve.

    Falha silenciosa e pior que falha barulhenta: sem este aviso, um blocklist
    que nao acontece por truncamento e indistinguivel de um torrent que
    legitimamente nao esta na fila.
    """
    try:
        corpo = resposta.json()
        total = corpo.get("totalRecords")
        trazidos = len(corpo.get("records", []))
    except Exception:
        return
    if isinstance(total, int) and total > trazidos:
        log.warning(f"{arr_type}: queue tem {total} itens e a pagina trouxe "
                    f"{trazidos} — aumente ARR_QUEUE_PAGE_SIZE")


def _handle_arr(arr_type, config_key, torrent_hash, torrent_name):
    """Handler generico para Sonarr ou Radarr.

    Fluxo:
    1. Busca torrent na queue → blocklist + extrai ID
    2. Fallback: busca por nome se nao encontrou na queue
    3. Dispara comando de re-search
    4. (Sonarr apenas) Valida data de lancamento dos episodios
    """
    cfg = get_config()
    section = cfg[config_key]

    if not section["url"] or not section["api_key"]:
        return

    try:
        url = section["url"].rstrip("/")
        key = section["api_key"]
        base = f"{url}/api/v3"
        hdrs = {"X-Api-Key": key}

        sess = requests.Session()
        sess.verify = False  # Homelab: certificados auto-assinados
        sess.headers.update(hdrs)

        # 1. Buscar na queue
        #
        # `pageSize` explicito e obrigatorio: a API do Radarr/Sonarr pagina a
        # queue e devolve **10** itens por default. Sem isto o guardian so via
        # os 10 primeiros, e com a fila cheia o blocklist simplesmente nao
        # acontecia — em silencio, porque "nao achei na queue" cai no fallback
        # por nome e depois desiste sem erro. Medido em producao: 43 itens na
        # queue, 10 retornados.
        log.debug(f"HTTP GET {base}/queue?pageSize={ARR_QUEUE_PAGE_SIZE}")
        rq = sess.get(f"{base}/queue",
                      params={"pageSize": ARR_QUEUE_PAGE_SIZE},
                      timeout=10)
        _avisa_queue_truncada(arr_type, rq)
        item_id = None
        extra_ids = []  # Sonarr: episode_ids

        for item in rq.json().get("records", []):
            if item.get("downloadId", "").lower() == torrent_hash.lower():
                # Blocklist
                log.debug(f"HTTP DELETE {base}/queue/{item['id']}?blocklist=true")
                sess.delete(f"{base}/queue/{item['id']}",
                                params={"blocklist": "true", "removeFromClient": "false"},
                                timeout=10)
                log.info(f"{arr_type}: '{torrent_name}' -> BLOCKLIST")

                if arr_type == "Radarr":
                    item_id = item.get("movieId")
                elif arr_type == "Sonarr":
                    item_id = item.get("seriesId")
                    if "episodeId" in item:
                        extra_ids.append(item["episodeId"])
                    elif "episodes" in item:
                        extra_ids.extend([ep["id"] for ep in item["episodes"]])
                break

        # 2. Fallback: busca por nome
        if not item_id:
            if arr_type == "Radarr":
                log.debug(f"HTTP GET {base}/movie")
                rm = sess.get(f"{base}/movie", timeout=10)
                item_id = _arr_match_by_name(rm.json(), torrent_name)
            elif arr_type == "Sonarr":
                log.debug(f"HTTP GET {base}/series")
                rs = sess.get(f"{base}/series", timeout=10)
                item_id = _arr_match_by_name(rs.json(), torrent_name)

        if not item_id:
            return

        # 3. Disparar re-search
        if arr_type == "Radarr":
            log.debug(f"HTTP POST {base}/command (MoviesSearch)")
            sess.post(f"{base}/command",
                          json={"name": "MoviesSearch", "movieIds": [item_id]},
                          timeout=10)
            log.info("Radarr: busca disparada")

        elif arr_type == "Sonarr":
            if extra_ids:
                # Validar data de lancamento dos episodios
                now = datetime.now(timezone.utc)
                released = []
                for eid in extra_ids:
                    try:
                        log.debug(f"HTTP GET {base}/episode/{eid}")
                        rep = sess.get(f"{base}/episode/{eid}",
                                       timeout=10)
                        ad = rep.json().get("airDateUtc")
                        if ad:
                            adt = datetime.fromisoformat(ad.replace("Z", "+00:00"))
                            if adt <= now:
                                released.append(eid)
                            else:
                                log.info(f"Sonarr: episodio {eid} nao lancado ({ad})")
                        else:
                            released.append(eid)
                    except Exception as ex:
                        log.error(f"Sonarr episodio {eid}: {ex}")
                        released.append(eid)

                if released:
                    log.debug(f"HTTP POST {base}/command (EpisodeSearch)")
                    sess.post(f"{base}/command",
                                  json={"name": "EpisodeSearch",
                                        "episodeIds": released},
                                  timeout=10)
                    log.info(f"Sonarr: busca para {released}")
                else:
                    log.warning(f"Sonarr: '{torrent_name}' episodios nao lancados")
            else:
                log.debug(f"HTTP POST {base}/command (SeriesSearch)")
                sess.post(f"{base}/command",
                              json={"name": "SeriesSearch",
                                    "seriesId": item_id},
                              timeout=10)
                log.info("Sonarr: busca da serie disparada")

    except Exception as e:
        log.error(f"{arr_type}: {e}")


def block_and_search(torrent_hash, torrent_name):
    """Bloqueia nos Arrs e dispara re-search."""
    _handle_arr("Radarr", "radarr", torrent_hash, torrent_name)
    _handle_arr("Sonarr", "sonarr", torrent_hash, torrent_name)


# ── Analise de torrent ─────────────────────────────────────────────────

def tempo_parado(torrent):
    """Segundos desde a ultima transferencia real do torrent.

    `added_on` mede a IDADE do torrent, nao o tempo parado, e usar um no lugar
    do outro inverte a regra: um torrent adicionado ha uma hora que perdeu os
    seeders agora era removido de imediato, enquanto um adicionado ha cinco
    minutos e parado desde o inicio nunca era.

    `last_activity` e o campo que o qBittorrent atualiza a cada chunk baixado
    ou enviado — e portanto o que "parado por X" quer dizer. Cai para
    `added_on` quando `last_activity` vem ausente ou zerado.

    Com os dois campos zerados o torrent e tratado como muito antigo (desde a
    epoca Unix), e nao como recem-visto: comportamento preservado do codigo
    anterior, do qual a suite depende. Na pratica o qBittorrent sempre preenche
    os dois — nos 53 torrents medidos em producao, nenhum vinha sem.
    """
    ultima = torrent.get("last_activity") or 0
    if ultima <= 0:
        ultima = torrent.get("added_on", 0) or 0
    return max(0.0, time.time() - ultima)


def tempo_ativo(torrent):
    """Segundos que o torrent efetivamente passou ATIVO, fora da fila.

    `time_active` e o contador do proprio qBittorrent: zero enquanto o torrent
    espera em `queuedDL`, crescendo so quando ele tem slot. E a medida de
    quanta chance real o torrent teve.

    Existe para fechar um falso positivo: com `max_active_downloads` baixo, um
    torrent pode passar horas em `queuedDL` — estado que nenhuma regra avalia —
    e, no instante em que finalmente entra em `metaDL`, ser removido na hora,
    porque `tempo_parado` (medido de `last_activity`, que para quem nunca
    transferiu cai em `added_on`) ja acumulou toda a espera da fila. Medido em
    producao: 36 de 37 enfileirados com `time_active == 0` e 290 min de idade.

    Devolve **None** quando o campo nao veio: desconhecido nao e zero. Em
    producao o qBittorrent sempre o envia, entao o piso sempre vale; a
    distincao existe para que teste focado em outro criterio nao precise
    declarar `time_active` para seguir valendo.
    """
    if "time_active" not in torrent:
        return None
    try:
        return max(0, int(torrent.get("time_active") or 0))
    except (TypeError, ValueError):
        return None


def _ativo_o_bastante(torrent, seconds):
    """True quando o torrent teve tempo ativo suficiente para ser julgado."""
    ativo = tempo_ativo(torrent)
    return ativo is None or ativo >= seconds


def is_stalled(torrent, cfg):
    """Verifica se torrent deve ser removido por stalled/no-seeds."""
    g = cfg["guardian"]
    state = torrent.get("state", "")
    parado = tempo_parado(torrent)

    # Stalled (parado por X tempo)
    if g.get("remove_stalled") and state in ("stalledDL", "stalledUP", "metaDL"):
        seconds = _time_to_seconds(g.get("stalled_time", 0), g.get("stalled_unit", "hours"))
        # `tempo_ativo` como piso: nao basta estar parado ha X, o torrent
        # precisa ter tido X de tempo ATIVO. Sem isso, a espera na fila conta
        # como se fosse inatividade dele.
        if seconds > 0 and parado >= seconds and _ativo_o_bastante(torrent, seconds):
            return True, f"stalled ({state}) por >{g['stalled_time']}{g['stalled_unit'][0]}"

    # Sem seeds. `queuedDL` ficou DE FORA de proposito: um torrent na fila nao
    # conectou ao tracker, logo `num_complete == 0` nele significa "ainda nao
    # perguntei", nao "nao existem seeders". Com MaxActiveDownloads baixo e
    # muitos torrents enfileirados, incluir esse estado removia em massa
    # downloads que nunca tiveram chance de comecar.
    if g.get("remove_no_seeds") and state in ("stalledDL", "downloading"):
        seeds = torrent.get("num_complete", -1)
        if seeds == 0:
            seconds = _time_to_seconds(g.get("no_seeds_time", 0), g.get("no_seeds_unit", "hours"))
            if seconds > 0 and parado >= seconds and _ativo_o_bastante(torrent, seconds):
                return True, "0 seeds"

    return False, ""


def _time_to_seconds(value, unit):
    if unit == "seconds":
        return int(value)
    elif unit == "minutes":
        return int(value) * 60
    else:
        return int(value) * 3600


_UNIDADES_VELOCIDADE = {
    "KiB": 1024,
    "MiB": 1024 ** 2,
    "GiB": 1024 ** 3,
    "TiB": 1024 ** 4,
}


def _speed_to_bytes(valor, unidade):
    """Converte o par (valor, unidade) da config para bytes por segundo.

    Base 1024 e rotulos KiB/MiB/GiB/TiB de proposito: e exatamente como o
    qBittorrent exibe velocidade na propria interface, entao o numero que o
    usuario digita aqui e comparavel ao que ele le na lista de torrents sem
    fazer conta. O campo `dlspeed` da API ja vem em bytes/s.
    """
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return valor * _UNIDADES_VELOCIDADE.get(unidade, _UNIDADES_VELOCIDADE["KiB"])


def _fmt_speed(bytes_por_s):
    """Formata bytes/s na maior unidade que ainda deixa o numero legivel."""
    valor = float(bytes_por_s)
    for unidade in ("TiB", "GiB", "MiB"):
        fator = _UNIDADES_VELOCIDADE[unidade]
        if valor >= fator:
            return f"{valor / fator:.2f} {unidade}/s"
    if valor >= 1024:
        return f"{valor / 1024:.2f} KiB/s"
    return f"{valor:.0f} B/s"


def is_slow(torrent, cfg):
    """Verifica se o torrent deve ser removido por velocidade abaixo do minimo.

    **Esta funcao tem efeito colateral**, diferente de `is_stalled`: mantem
    `_lento_desde` para saber desde quando o torrent esta lento. Sem esse
    ponto de partida nao da para medir "x minutos abaixo de y" — so dava para
    olhar o `dlspeed` instantaneo, que oscila demais (um download de 2 KiB/s
    tem picos momentaneos acima de qualquer limite razoavel).

    A velocidade julgada e a **media na janela**: `(baixado_agora -
    baixado_no_inicio) / tempo_decorrido`. Se o torrent recupera no meio, a
    media sobe, a janela e descartada e ele escapa — que e o comportamento
    justo.

    Avalia **somente** `state == "downloading"`. `queuedDL` esta fora de
    proposito: torrent na fila tem 0 B/s por definicao, e incluir esse estado
    repetiria o defeito que qualificou 51 de 54 torrents enfileirados para
    remocao na v2.7.0. `stalledDL` tambem fica fora, por ja ser coberto por
    `remove_stalled`.
    """
    g = cfg["guardian"]
    h = torrent.get("hash")

    if torrent.get("state") != "downloading":
        _lento_desde.pop(h, None)
        return False, ""

    if not g.get("remove_slow"):
        return False, ""

    limite = _speed_to_bytes(g.get("slow_speed", 0), g.get("slow_speed_unit", "KiB"))
    segundos = _time_to_seconds(g.get("slow_time", 0), g.get("slow_unit", "minutes"))
    if limite <= 0 or segundos <= 0:
        return False, ""

    agora = time.time()
    baixado = torrent.get("downloaded", 0) or 0

    if h not in _lento_desde:
        # Abre a janela so quando a leitura instantanea ja sugere lentidao:
        # marcar todo torrent saudavel encheria o dict sem necessidade.
        if (torrent.get("dlspeed") or 0) < limite:
            _lento_desde[h] = (agora, baixado)
        return False, ""

    inicio, bytes_inicio = _lento_desde[h]
    decorrido = agora - inicio
    if decorrido <= 0:
        return False, ""

    media = (baixado - bytes_inicio) / decorrido
    if media >= limite:
        _lento_desde.pop(h, None)
        return False, ""
    if decorrido >= segundos:
        _lento_desde.pop(h, None)
        return True, (f"{_fmt_speed(media)} de media por "
                      f">{g.get('slow_time')}{str(g.get('slow_unit', 'minutes'))[0]} "
                      f"(minimo {g.get('slow_speed')} {g.get('slow_speed_unit', 'KiB')}/s)")
    return False, ""


def _stalled_threshold(cfg):
    """Limiar configurado de stalled, como texto ("15 minutes").

    Vazio quando a remocao por stalled esta desligada — o evento pode ter sido
    disparado pelo ramo de "0 seeds", onde esse limiar nao se aplica.
    """
    g = cfg.get("guardian") or {}
    if not g.get("remove_stalled"):
        return ""
    return f"{g.get('stalled_time', 0)} {g.get('stalled_unit', 'hours')}"


def check_stalled_and_remove(torrent):
    """Verifica stalled/sem seeds e remove se necessario.

    Funcao leve: so le campos do JSON, sem chamadas HTTP.
    Extraida de analyze_torrent para permitir reavaliacao
    periodica de torrents ja processados (pass 2 do loop).
    Retorna True se removeu o torrent.
    """
    cfg = get_config()
    state = torrent.get("state", "")

    # UP states: skip (torrent ja completou ou esta enviando)
    if state in ("uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"):
        return False

    stalled, stalled_reason = is_stalled(torrent, cfg)
    if not stalled:
        # Avaliado depois do stalled de proposito: um torrent que ja esta
        # `stalledDL` sai pelo criterio de stalled, com a mensagem propria.
        # `is_slow` so julga `downloading`, entao nao ha sobreposicao real —
        # a ordem apenas garante a mensagem mais especifica.
        stalled, stalled_reason = is_slow(torrent, cfg)
    if stalled:
        hash_ = torrent["hash"]
        name = torrent["name"]
        log.verbose(f"[{name}] {stalled_reason} — REMOVIDO")
        block_and_search(hash_, name)
        remove_torrent(hash_)
        notify("stalled",
               torrentName=name,
               reason=stalled_reason,
               state=state,
               stalledTime=_stalled_threshold(cfg))
        return True
    return False


def analyze_torrent(torrent):
    """Analisa um torrent novo.

    Retorna True quando a analise foi concluida (o torrent pode ser marcado
    como processado) e False quando os metadados ainda nao chegaram — nesse
    caso ele precisa ser reavaliado num ciclo futuro. Marcar como processado
    antes dos metadados existirem fazia o torrent nunca mais ser validado.
    """
    cfg = get_config()
    g = cfg["guardian"]
    valid_ext = set(g.get("valid_media_extensions", []))
    dangerous_ext = set(g.get("dangerous_extensions", []))

    hash_ = torrent["hash"]
    name  = torrent["name"]
    state = torrent.get("state", "")

    # Pular torrents ja completos/uploading
    if state in ("uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"):
        return True

    # Verificar stalled/sem seeds (funcao extraida, mesma logica)
    if check_stalled_and_remove(torrent):
        return True

    files = get_files(hash_)
    if not files:
        # Metadados ainda nao chegaram (magnet em metaDL/queuedDL). Validar
        # agora e impossivel, e marcar como processado impediria a validacao
        # definitiva quando os arquivos aparecessem.
        log.verbose(f"[{name}] sem metadados — sera reavaliado no proximo ciclo")
        return False

    extensions = [os.path.splitext(f["name"])[1].lower() for f in files]
    dangerous_found = [e for e in extensions if e in dangerous_ext]

    should_remove = False
    reason = ""

    if dangerous_found:
        should_remove = True
        reason = f"Arquivos perigosos: {dangerous_found}"
    elif valid_ext:
        media_files = [f for f in files if os.path.splitext(f["name"])[1].lower() in valid_ext]
        if not media_files:
            should_remove = True
            reason = "Nenhum arquivo de midia valido"

    if should_remove:
        log.warning(f"[{name}] {reason} — Removendo e Bloqueando")
        block_and_search(hash_, name)
        remove_torrent(hash_)
        notify("removed",
               torrentName=name,
               reason=reason,
               extensions=", ".join(dangerous_found))
        return True

    # Otimizar prioridades
    optimized = False
    prio_media = g.get("priority_media", 7)
    prio_norm  = g.get("priority_normal", 1)
    prio_skip  = g.get("priority_skip", 0)
    media_count = 0
    for f in files:
            ext = os.path.splitext(f["name"])[1].lower()
            file_id = f.get("index", f.get("id"))
            if ext in valid_ext:
                set_file_priority(hash_, file_id, prio_media)
                optimized = True
                media_count += 1
            elif ext in {".nfo", ".jpg", ".png", ".txt", ".srt", ".sub", ".idx"}:
                set_file_priority(hash_, file_id, prio_norm)
            else:
                set_file_priority(hash_, file_id, prio_skip)
                log.debug(f"[{name}] Desativado → {f['name']}")
    if optimized:
        log.verbose(f"[{name}] otimizado ({media_count} arquivos de midia priorizados)")
        notify("optimized",
               torrentName=name,
               priorityMedia=prio_media,
               priorityAux=prio_norm,
               mediaCount=media_count)

    return True


# ── Heartbeat ──────────────────────────────────────────────────────────

def write_heartbeat():
    """Escreve timestamp em /tmp/heartbeat para healthcheck Docker.

    Chamado no startup (main.py), periodicamente (guardian_loop)
    e sob demanda (api_trigger em modo webhook).
    """
    try:
        with open("/tmp/heartbeat", "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


# ── Loop principal ─────────────────────────────────────────────────────

_processed = set()
_check_count = 0
_parar_reevaluate = threading.Event()

# hash -> (instante em que ficou lento, bytes baixados naquele instante).
# Guardar o PONTO DE PARTIDA, e nao a ultima medicao, e o que permite medir
# velocidade media na janela inteira de lentidao em vez de confiar no `dlspeed`
# instantaneo, que oscila demais para decidir remocao.
_lento_desde = {}


def _prune_processed(current_hashes):
    """Limpa _processed: remove hashes ausentes e aplica hard cap.

    Limpa tambem `_lento_desde`: torrent removido ou concluido nao tem janela
    de lentidao a manter, e sem isso o dict cresceria indefinidamente.
    """
    _processed.intersection_update(current_hashes)
    for h in [h for h in _lento_desde if h not in current_hashes]:
        _lento_desde.pop(h, None)
    if len(_processed) > MAX_PROCESSED_SIZE:
        excess = len(_processed) - MAX_PROCESSED_SIZE
        remove = set(list(_processed)[:excess])
        _processed.difference_update(remove)
        log.warning(f"_processed atingiu {MAX_PROCESSED_SIZE}, "
                    f"removidos {excess} hashes antigos")


def _retry_interval(cfg):
    """Le guardian.retry_interval_seconds com fallback seguro.

    Retorna sempre um inteiro positivo. Valores ausentes, nao numericos ou
    <= 0 caem no DEFAULT_RETRY_INTERVAL — evita busy loop no retry quando a
    config esta corrompida ou mal preenchida.
    """
    raw = (cfg.get("guardian") or {}).get("retry_interval_seconds",
                                          DEFAULT_RETRY_INTERVAL)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_INTERVAL
    return val if val > 0 else DEFAULT_RETRY_INTERVAL


def _connect_with_retry():
    """Conecta ao qBittorrent, retentando a cada retry_interval_seconds.

    NUNCA retorna/levanta por falha de conexao: mantem a thread do guardian
    viva, retentando ate o qBit responder. A cada tentativa fracassada escreve
    o heartbeat — o healthcheck mede a saude do PROCESSO guardian, nao a do
    qBit, e a indisponibilidade do qBit e um estado externo transitorio.
    """
    while True:
        try:
            qbit_login()
            return
        except Exception as e:
            cfg = get_config()
            retry_interval = _retry_interval(cfg)
            log.warning(f"qBittorrent indisponivel ({e}) — "
                        f"nova tentativa em {retry_interval}s")
            try:
                write_heartbeat()
            except Exception:
                pass
            time.sleep(retry_interval)


def _reevaluate_interval(cfg):
    """Intervalo do Pass 2, em segundos (0 desliga)."""
    g = cfg.get("guardian") or {}
    try:
        return max(0, int(g.get("reevaluate_interval_seconds", 300)))
    except (TypeError, ValueError):
        return 300


def _check_interval(cfg):
    """Intervalo do polling, em segundos (0 = modo webhook).

    Simetrica a `_reevaluate_interval`, e pelo mesmo motivo: o valor pode vir
    como string de um config editado a mao, e `"0" == 0` e False. O
    healthcheck ja normalizava (`_as_int`) enquanto o loop comparava cru — os
    dois discordavam sobre o modo de um `"0"` entre aspas.
    """
    g = cfg.get("guardian") or {}
    try:
        return max(0, int(g.get("check_interval_seconds", 300)))
    except (TypeError, ValueError):
        return 300


# ── Modo de operacao: polling x webhook ────────────────────────────────
#
# Sao dois lacos distintos e so um roda por vez; trocar de modo e passar o
# bastao de um para o outro. Sem isso, os dois sentidos falhavam:
#
#   polling -> webhook: o laco de polling dava `return` sem acordar a
#       reavaliacao. Nao sobrava laco nenhum — so o `/api/trigger`, que nem
#       existe se o webhook nao estiver configurado no qBittorrent.
#   webhook -> polling: quem detectaria a volta era o laco de polling, que
#       tinha terminado no start. So com restart do container.
_modo_lock = threading.Lock()
_modo_atual = None


def _definir_modo(modo):
    """Registra quem esta no comando. Chamado por quem assume o laco."""
    global _modo_atual
    with _modo_lock:
        _modo_atual = modo


def modo_em_execucao():
    """`"polling"`, `"webhook"` ou None (nenhum laco subiu ainda)."""
    with _modo_lock:
        return _modo_atual


def _passar_bastao(de, para, subir):
    """Troca o modo UMA vez, mesmo com duas threads percebendo a mudanca.

    A guarda e o `de`: so troca quem ainda e o dono do modo. Sem ela, uma
    thread atrasada — dormindo no intervalo enquanto a troca ja aconteceu —
    acordaria e subiria um segundo laco, e o ciclo passaria a rodar em dobro
    contra o mesmo qBittorrent.

    Devolve False quando a troca nao era desta thread, e aí o chamador segue
    o que estava fazendo em vez de encerrar.
    """
    global _modo_atual
    with _modo_lock:
        if _modo_atual != de:
            return False
        _modo_atual = para
    subir()
    return True


def aplicar_modo_da_config():
    """Religa o laco certo quando a Web UI troca o modo. Chamada pelo POST.

    O laco de polling percebe a troca sozinho, ao fim do ciclo em andamento.
    A volta nao tinha quem percebesse: em modo webhook com a reavaliacao
    desligada (`reevaluate_interval_seconds = 0`) nao ha laco nenhum rodando,
    e salvar um Polling > 0 pela tela nao religava nada ate o restart.

    Devolve o modo para o qual trocou, ou None quando nao havia o que fazer.
    """
    desejado = "polling" if _check_interval(get_config()) > 0 else "webhook"
    atual = modo_em_execucao()
    if atual is None or desejado == atual:
        return None

    if desejado == "polling":
        # Acorda o laco de webhook, que pode estar dormindo ate o proximo
        # intervalo de reavaliacao. Quem sobe um `_reevaluate_loop` novo limpa
        # o Event, entao nao ha flag preso para a proxima vez.
        _parar_reevaluate.set()
        if _passar_bastao("webhook", "polling", start_guardian):
            log.info("Polling religado pela Web UI — voltando do modo webhook.")
            return "polling"
        return None

    # polling -> webhook: o proprio laco de polling trata, ao acordar.
    return None


def executar_ciclo(torrents=None):
    """Um ciclo de analise: pendentes (pass 1) + reavaliacao de stalled (pass 2).

    A "fila de pendentes" nao e estrutura separada: e o complemento de
    `_processed`. `analyze_torrent` so devolve True quando a analise concluiu,
    e um torrent sem metadados devolve False — ficando de fora de `_processed`
    e, portanto, pendente para o proximo ciclo.

    Isso importa porque o qBittorrent **nao busca metadados de torrent
    enfileirado**: com `MaxActiveDownloads` baixo, um torrent fica em
    `queuedDL` sem arquivo nenhum e so ganha metadados quando chega a vez dele.
    A prioridade dos arquivos (`priority_media`/`priority_skip`) nao pode ser
    aplicada antes disso.

    Quando a fila de pendentes esvazia, o pass 1 nao faz requisicao nenhuma e o
    ciclo custa a unica chamada de `get_torrents()`.

    Retorna um dict com as metricas do ciclo.
    """
    if torrents is None:
        torrents = get_torrents()

    pendentes = [t for t in torrents if t["hash"] not in _processed]
    analisados = 0
    for t in pendentes:
        if analyze_torrent(t):
            _processed.add(t["hash"])
            analisados += 1

    # Pass 2: reavalia stalled/no-seeds para TODOS os torrents
    # (torrents ja em _processed podem ter ficado stalled depois)
    removidos = 0
    for t in torrents:
        if check_stalled_and_remove(t):
            removidos += 1

    current_hashes = {t["hash"] for t in torrents}
    fora_do_historico = len([h for h in _processed if h not in current_hashes])
    _prune_processed(current_hashes)

    return {
        "total": len(torrents),
        "pendentes": len(pendentes),
        "analisados": analisados,
        "restantes": len(pendentes) - analisados,
        "removidos": removidos,
        "fora_do_historico": fora_do_historico,
    }


def _reevaluate_loop():
    """Ciclo periodico no modo webhook: drena a fila de pendentes e reavalia stalled.

    Sem este loop, o unico gatilho era `/api/trigger`, que o hook do
    qBittorrent dispara ao ADICIONAR torrent. Duas consequencias, as duas
    observadas em producao:

    1. Um torrent que ficava stalled depois de processado so era reavaliado se
       outro torrent fosse adicionado — sem isso, ficava parado indefinidamente.
    2. Torrent adicionado em lote entrava em `queuedDL` sem metadados, a analise
       era recusada, e **a prioridade dos arquivos nunca era aplicada**: quando
       os metadados finalmente chegavam, nao havia mais quem olhasse.

    O custo se ajusta sozinho ao que falta fazer: com pendentes, o ciclo gasta
    uma requisicao por torrent da fila; com a fila vazia, gasta apenas o
    `get_torrents()`. Nao ha modo a alternar — o loop fica barato quando nao ha
    trabalho, e volta a trabalhar quando um lote novo entra.
    """
    # Quem assume o laco limpa o sinal de parada: `aplicar_modo_da_config()`
    # o levanta para acordar a thread anterior, e deixar o flag preso faria
    # este laco encerrar na primeira espera.
    _parar_reevaluate.clear()

    while True:
        cfg = get_config()

        # Polling religado: devolve o bastao e sai. Se a troca nao for desta
        # thread (`False`), segue reavaliando — outra ja assumiu.
        if _check_interval(cfg) > 0:
            if _passar_bastao("webhook", "polling", start_guardian):
                log.info("Polling religado — saindo do modo webhook.")
                return

        intervalo = _reevaluate_interval(cfg)
        if intervalo <= 0:
            log.info("reevaluate_interval_seconds=0 — reavaliacao periodica desligada.")
            return
        # Event.wait em vez de time.sleep: a espera fica interrompivel (um
        # `_parar_reevaluate.set()` encerra na hora em vez de esperar o
        # intervalo inteiro) e nao se confunde com o sleep do retry de conexao,
        # que a suite verifica isoladamente.
        if _parar_reevaluate.wait(intervalo):
            return
        try:
            r = executar_ciclo()
            # Silencio quando nao houve nada a fazer: com a fila vazia este
            # loop roda a cada intervalo sem produzir trabalho, e logar isso
            # viraria ruido de 288 linhas por dia.
            if r["analisados"] or r["removidos"] or r["restantes"]:
                log.info(f"Reavaliacao periodica: {r['total']} torrents, "
                         f"{r['analisados']} analisados, "
                         f"{r['removidos']} removidos, "
                         f"{r['restantes']} ainda sem metadados")
            write_heartbeat()
        except TRANSPORT_ERRORS:
            log.warning("qBittorrent inacessivel na reavaliacao periodica")
        except Exception as e:
            log.error(f"Erro na reavaliacao periodica: {e}")


def _start_reevaluate_loop():
    t = threading.Thread(target=_reevaluate_loop, daemon=True)
    t.start()
    return t


def guardian_loop():
    global _check_count
    load_config()

    # Conecta com retry: se o qBit ainda nao estiver disponivel no startup
    # (ex.: qbit-guardian sobe antes do qBittorrent apos um reboot), o loop
    # retenta a cada retry_interval_seconds em vez de encerrar a thread.
    _connect_with_retry()

    cfg = get_config()
    interval = _check_interval(cfg)

    if interval == 0:
        reeval = _reevaluate_interval(cfg)
        log.info("Guardian iniciado em modo webhook (intervalo=0). "
                 f"Aguardando /api/trigger; reavaliacao de stalled a cada {reeval}s.")
        _definir_modo("webhook")
        _start_reevaluate_loop()
        return  # sem ciclo completo — so responde a /api/trigger

    _definir_modo("polling")
    log.info(f"Guardian iniciado. Intervalo: {interval}s")

    while True:
        _check_count += 1
        removed_this_check = 0
        new_this_check = 0

        try:
            r = executar_ciclo()
            new_this_check = r["pendentes"]
            removed_this_check = r["fora_do_historico"]

            # ── Log INFO: resumo da verificacao ──
            log.info(f"Verificacao #{_check_count}: {r['total']} torrents, "
                     f"{new_this_check} novos, {r['removidos']} stalled removidos, "
                     f"{removed_this_check} removidos do historico")

        except TRANSPORT_ERRORS:
            log.warning("qBittorrent inacessivel, reconectando...")
            _connect_with_retry()
        except Exception as e:
            log.error(f"Erro: {e}")

        try:
            write_heartbeat()
        except Exception:
            pass

        # Recarrega config a cada iteracao para detectar mudancas no intervalo
        # (`get_config` invalida o cache por mtime — ver a funcao)
        cfg = get_config()
        interval = _check_interval(cfg)
        if interval == 0:
            log.info("Intervalo alterado para 0 — entrando em modo webhook. Aguardando /api/trigger.")
            # Passar o bastao e o que faltava: antes o laco so terminava, e
            # ninguem mais olhava a fila ate o restart do container.
            _passar_bastao("polling", "webhook", _start_reevaluate_loop)
            return

        time.sleep(interval)


def config_gravavel(caminho=None):
    """True se o guardian consegue persistir o config.json.

    O container passou a rodar como usuario nao-root (v2.2.0). Um volume
    `./config` criado pelas versoes antigas pertence ao root, e o processo
    sem privilegio nao escreve nele: sem esta checagem a falha apareceria como
    PermissionError no meio do provisionamento, depois de a senha ja ter sido
    sorteada e anunciada — senha que nunca chegaria ao disco.
    """
    caminho = caminho or CONFIG_PATH
    if os.path.exists(caminho):
        return os.access(caminho, os.W_OK)
    diretorio = os.path.dirname(caminho) or "."
    if not os.path.isdir(diretorio):
        diretorio = os.path.dirname(diretorio) or "."
    return os.path.isdir(diretorio) and os.access(diretorio, os.W_OK)


def bootstrap_credenciais():
    """Provisiona as credenciais da Web UI antes de o servidor subir.

    Roda no entrypoint, nao sob demanda: a janela entre o processo subir e as
    credenciais existirem precisa ser zero, senao a Web UI fica publica por
    alguns instantes a cada deploy.

    Retorna True se o config.json foi alterado.
    """
    if not config_gravavel():
        raise PermissionError(CONFIG_PATH)
    cfg = load_config()
    cfg, alterou = auth.garantir_credenciais(cfg)
    if alterou:
        save_config(cfg)
    return alterou


def start_guardian():
    """Inicia o loop em thread separada."""
    t = threading.Thread(target=guardian_loop, daemon=True)
    t.start()
    log.info("Guardian thread iniciada")
    return t
