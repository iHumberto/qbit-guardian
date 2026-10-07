"""
qbit-guardian — Security tests.

Vetores primários: CSRF, XSS, API key exposure, path traversal, auth bypass.
Vetores secundários: race condition, JSON injection.
Vetores de borda: Unicode, config corrompido.

Run: .venv/bin/python -m pytest test/test_security.py -v
"""

import json
import os
import tempfile
import base64
import pytest
from unittest import mock

import app.auth as auth
import app.guardian as g
import app.web as w
from app.web import app

SENHA = "senha-de-teste-123"


def _json_headers(**extra):
    base = {"Content-Type": "application/json"}
    base.update(extra)
    return base


def _basic(usuario, senha):
    bruto = f"{usuario}:{senha}".encode()
    return {"Authorization": "Basic " + base64.b64encode(bruto).decode()}


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def tmp_config():
    """Cria config.json temporário e restaura depois."""
    import app.web as w
    import app.guardian as g
    old_path = w.CONFIG_PATH
    old_gpath = g.CONFIG_PATH

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "qbit": {"url": "http://localhost:8080", "api_key": "test-key"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv", ".mp4"],
                "dangerous_extensions": [".exe", ".scr"],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""},
            "webui": {"user": "", "password": ""}
        }, f)
        tmp_path = f.name

    w.CONFIG_PATH = tmp_path
    g.CONFIG_PATH = tmp_path
    g._config = None

    yield tmp_path

    w.CONFIG_PATH = old_path
    g.CONFIG_PATH = old_gpath
    g._config = None
    os.unlink(tmp_path)


# ── Auth ───────────────────────────────────────────────────────────────

class TestAuth:
    """HTTP Basic Auth na Web UI."""

    AUTH = "Basic " + base64.b64encode(b"admin:secret").decode()

    def _enable_auth(self, tmp_config):
        with open(tmp_config, "r") as f:
            cfg = json.load(f)
        cfg["webui"] = {"user": "admin", "password": "secret"}
        with open(tmp_config, "w") as f:
            json.dump(cfg, f)

    def test_auth_pode_ser_desligada_explicitamente(self, client, tmp_config):
        """Campos vazios desligam a auth — escape hatch consciente.

        Nao e mais o estado inicial: desde a v2.2.0 o startup provisiona
        usuario e senha (ver TestBootstrapCredenciais). Esvaziar `webui`
        continua valendo para quem ja protege a porta por outro meio, mas o
        proximo restart gera senha nova.
        """
        r = client.get("/api/config")
        assert r.status_code == 200

    def test_auth_enabled_blocks_unauthorized(self, client, tmp_config):
        """Com auth configurada, sem header -> 401."""
        self._enable_auth(tmp_config)
        r = client.get("/api/config")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers

    def test_auth_wrong_password_returns_401(self, client, tmp_config):
        """Credenciais erradas -> 401."""
        self._enable_auth(tmp_config)
        wrong = "Basic " + base64.b64encode(b"admin:wrong").decode()
        r = client.get("/api/config", headers={"Authorization": wrong})
        assert r.status_code == 401

    def test_auth_correct_credentials_returns_200(self, client, tmp_config):
        """Credenciais corretas -> 200."""
        self._enable_auth(tmp_config)
        r = client.get("/api/config", headers={"Authorization": self.AUTH})
        assert r.status_code == 200

    def test_auth_enabled_blocks_post(self, client, tmp_config):
        """POST sem auth -> 401."""
        self._enable_auth(tmp_config)
        r = client.post("/api/config", json={"qbit": {}})
        assert r.status_code == 401

    def test_auth_enabled_allows_post_with_credentials(self, client, tmp_config):
        """POST com auth correta -> 200."""
        self._enable_auth(tmp_config)
        r = client.post("/api/config", json={"qbit": {"url": "http://test:1", "api_key": "k"}},
                        headers={"Authorization": self.AUTH})
        assert r.status_code == 200

    def test_health_is_always_public(self, client, tmp_config):
        """/api/health nunca requer auth."""
        self._enable_auth(tmp_config)
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json == {"status": "ok"}


# ── Vetores primários ──────────────────────────────────────────────────

class TestXSS:
    """XSS: script injection via config fields."""

    def test_xss_in_extensions_sanitized(self, client, tmp_config):
        """Injetar <script> no campo de extensoes nao deve executar."""
        payload = {
            "qbit": {"url": "http://localhost:8080", "api_key": "x"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": ["<script>alert(1)</script>", ".exe"],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200

        # Verifica que o script foi salvo literalmente (nao sanitizado pelo server)
        with open(tmp_config) as f:
            saved = json.load(f)
        assert "<script>" in saved["guardian"]["dangerous_extensions"][0]

    def test_xss_in_html_page_no_inline_script(self, client, tmp_config):
        """Pagina HTML nao deve conter dados do usuario inline (escapados)."""
        r = client.get("/")
        assert r.status_code == 200
        html = r.data.decode()
        assert "alert(1)" not in html.lower()


class TestCSRF:
    """POST /api/config aceita requisicao local, nunca de outro site."""

    def test_post_config_do_proprio_painel_funciona(self, client, tmp_config):
        """Requisicao same-origin continua passando normalmente."""
        r = client.post("/api/config", json={
            "qbit": {"url": "http://test:8080", "api_key": "k"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""}
        })
        # Auth desabilitada -> aceito
        assert r.status_code == 200

    def test_invalid_json_rejected(self, client):
        """JSON invalido deve ser rejeitado com 400."""
        r = client.post("/api/config", data="not json", content_type="application/json")
        assert r.status_code == 400


class TestConfigIntegrity:
    """Verifica que config.json mantem integridade com deep merge."""

    def test_missing_fields_preserved_with_deep_merge(self, client, tmp_config):
        """Campos nao enviados no POST sao preservados (deep merge)."""
        # Salva config inicial com um valor conhecido
        initial = {
            "qbit": {"url": "http://keep-me:8080", "api_key": "k"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""},
            "webui": {"user": "", "password": ""}
        }
        with open(tmp_config, "w") as f:
            json.dump(initial, f)

        # POST apenas com api_key nova — url deve ser preservada
        r = client.post("/api/config", json={
            "qbit": {"api_key": "new-key"}
        })
        assert r.status_code == 200

        # Deep merge: url preservada, api_key atualizada
        with open(tmp_config) as f:
            saved = json.load(f)
        assert saved["qbit"]["url"] == "http://keep-me:8080"
        assert saved["qbit"]["api_key"] == "new-key"
        # Outras secoes intactas
        assert saved["guardian"]["check_interval_seconds"] == 300

    def test_deep_merge_preserves_nested_fields(self, client, tmp_config):
        """Merge preserva subsections inteiras quando nao enviadas."""
        initial = {
            "qbit": {"url": "http://x:8080", "api_key": "k"},
            "sonarr": {"url": "http://sonarr.local:8989", "api_key": "sk"},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""},
            "webui": {"user": "", "password": ""}
        }
        with open(tmp_config, "w") as f:
            json.dump(initial, f)

        # Envia apenas guardian.check_interval_seconds
        r = client.post("/api/config", json={
            "guardian": {"check_interval_seconds": 60}
        })
        assert r.status_code == 200

        with open(tmp_config) as f:
            saved = json.load(f)
        assert saved["guardian"]["check_interval_seconds"] == 60
        assert saved["guardian"]["valid_media_extensions"] == [".mkv"]
        assert saved["sonarr"]["url"] == "http://sonarr.local:8989"


# ── Vetores secundários ────────────────────────────────────────────────

class TestRaceCondition:
    """Simula race condition entre Web UI e guardian loop."""

    def test_concurrent_read_write_config(self, tmp_config):
        """Multiplas leituras simultaneas nao corrompem o arquivo."""
        import app.guardian as g

        valid = {"qbit": {"url": "http://x:1", "api_key": "k"},
                 "sonarr": {"url": "", "api_key": ""},
                 "radarr": {"url": "", "api_key": ""},
                 "guardian": {
                     "check_interval_seconds": 300,
                     "valid_media_extensions": [], "dangerous_extensions": [],
                     "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                     "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                     "priority_media": 7, "priority_normal": 1, "priority_skip": 0
                 },
                 "notifications": {"apprise_url": ""},
                 "webui": {"user": "", "password": ""}}
        import threading

        errors = []
        def read_loop():
            for _ in range(50):
                try:
                    g.load_config()
                except Exception as e:
                    errors.append(str(e))

        def write_loop():
            for _ in range(50):
                try:
                    g.save_config(valid)
                except Exception as e:
                    errors.append(str(e))

        threads = []
        for _ in range(4):
            threads.append(threading.Thread(target=read_loop))
            threads.append(threading.Thread(target=write_loop))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Race condition errors: {errors}"

        with open(tmp_config) as f:
            json.load(f)


class TestJSONInjection:
    """JSON injection via API."""

    def test_nested_json_injection_in_api_key(self, client, tmp_config):
        """Injetar JSON malicioso via campo api_key."""
        payload = {
            "qbit": {"url": "http://x:8080", "api_key": '\"; alert(1); \"'},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200

        with open(tmp_config) as f:
            saved = json.load(f)
        assert saved["qbit"]["api_key"] == '\"; alert(1); \"'

    def test_priority_out_of_range(self, client, tmp_config):
        """Prioridade >7 ou <0 deve ser aceita mas cabe ao guardian validar."""
        payload = {
            "qbit": {"url": "http://x:8080", "api_key": "k"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 999, "priority_normal": -1, "priority_skip": 50
            },
            "notifications": {"apprise_url": ""}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200


# ── Vetores de borda ───────────────────────────────────────────────────

class TestEdgeCases:
    """Casos extremos: Unicode, config corrompido, campos vazios."""

    def test_unicode_in_extensions(self, client, tmp_config):
        """Extensoes com caracteres Unicode devem ser preservadas."""
        payload = {
            "qbit": {"url": "http://x:8080", "api_key": "k"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [".éxé", ".測試"],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200

        with open(tmp_config) as f:
            saved = json.load(f)
        assert ".éxé" in saved["guardian"]["dangerous_extensions"]
        assert ".測試" in saved["guardian"]["dangerous_extensions"]

    def test_empty_extensions_list(self, client, tmp_config):
        """Lista vazia de extensoes perigosas — nada e removido."""
        payload = {
            "qbit": {"url": "http://x:8080", "api_key": "k"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200
        with open(tmp_config) as f:
            saved = json.load(f)
        assert saved["guardian"]["dangerous_extensions"] == []

    def test_corrupted_config_fallback(self, tmp_config):
        """Config JSON corrompido — load_config deve lancar erro."""
        import app.guardian as g
        g._config = None

        with open(tmp_config, "w") as f:
            f.write("{invalid json!!!")

        with pytest.raises(json.JSONDecodeError):
            g.load_config()

    def test_config_with_extra_unknown_fields(self, client, tmp_config):
        """Campos desconhecidos sao preservados silenciosamente (deep merge)."""
        payload = {
            "qbit": {"url": "http://x:8080", "api_key": "k"},
            "sonarr": {"url": "", "api_key": ""},
            "radarr": {"url": "", "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv"],
                "dangerous_extensions": [],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0,
                "unknown_future_field": "should_survive"
            },
            "notifications": {"apprise_url": ""}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200

        with open(tmp_config) as f:
            saved = json.load(f)
        assert saved["guardian"]["unknown_future_field"] == "should_survive"


# ── CSRF: o vetor que a v2.2.0 fechou ──────────────────────────────────

@pytest.fixture
def auth_config(tmp_config):
    """Config com autenticacao ligada e senha conhecida."""
    with open(tmp_config) as f:
        cfg = json.load(f)
    cfg["webui"] = {"user": "admin", "password": auth.hash_senha(SENHA)}
    with open(tmp_config, "w") as f:
        json.dump(cfg, f)
    g._config = None
    return tmp_config


class TestCSRFOrigemExterna:
    """Escrita vinda de outro site e recusada, com ou sem credencial valida.

    Era o buraco exploravel do projeto: `request.get_json(force=True)` aceitava
    `Content-Type: text/plain`, que nao dispara preflight de CORS. Qualquer
    pagina que a vitima visitasse podia disparar um POST, e o navegador anexava
    o Basic Auth dela sozinho — dava para apontar `qbit.url` para fora (e vazar
    a API key do qBittorrent no header `Authorization`) ou transformar `.mkv`
    em extensao perigosa (e apagar a biblioteca, porque a remocao usa
    `deleteFiles=true`).
    """

    PAYLOAD = {"guardian": {"check_interval_seconds": 42}}

    @pytest.mark.parametrize("rota", ["/api/config", "/api/credentials"])
    @pytest.mark.parametrize("tipo", ["text/plain", "application/x-www-form-urlencoded",
                                      "multipart/form-data"])
    def test_content_type_simples_recusado(self, rota, tipo, client, auth_config):
        """So `application/json` passa — o resto dispensaria preflight."""
        r = client.post(rota, data=json.dumps(self.PAYLOAD), content_type=tipo,
                        headers=_basic("admin", SENHA))
        assert r.status_code == 415, r.get_data(as_text=True)

    @pytest.mark.parametrize("site", ["cross-site", "same-site-forjado", "qualquer-coisa"])
    def test_sec_fetch_site_externo_recusado(self, site, client, auth_config):
        r = client.post("/api/config", json=self.PAYLOAD,
                        headers={**_basic("admin", SENHA), "Sec-Fetch-Site": site})
        assert r.status_code == 403

    @pytest.mark.parametrize("site", ["same-origin", "none"])
    def test_sec_fetch_site_proprio_aceito(self, site, client, auth_config):
        r = client.post("/api/config", json=self.PAYLOAD,
                        headers={**_basic("admin", SENHA), "Sec-Fetch-Site": site})
        assert r.status_code == 200

    def test_origin_de_outro_host_recusado(self, client, auth_config):
        """Navegador antigo, sem Sec-Fetch-Site: o Origin decide."""
        r = client.post("/api/config", json=self.PAYLOAD,
                        headers={**_basic("admin", SENHA), "Origin": "http://evil.tld"})
        assert r.status_code == 403

    def test_origin_do_proprio_host_aceito(self, client, auth_config):
        r = client.post("/api/config", json=self.PAYLOAD,
                        headers={**_basic("admin", SENHA), "Origin": "http://localhost"})
        assert r.status_code == 200

    def test_cliente_sem_cabecalhos_de_navegador_aceito(self, client, auth_config):
        """curl e o hook do webhook nao mandam Sec-Fetch-Site nem Origin.

        Um cliente que nao e navegador nao sofre CSRF: nao ha sessao que outro
        site possa sequestrar.
        """
        r = client.post("/api/config", json=self.PAYLOAD, headers=_basic("admin", SENHA))
        assert r.status_code == 200

    def test_leitura_nao_e_bloqueada_por_origem(self, client, auth_config):
        """GET nao muda estado — a checagem e so para escrita."""
        r = client.get("/api/config", headers={**_basic("admin", SENHA),
                                               "Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 200

    def test_trigger_protegido_por_origem(self, client, auth_config):
        r = client.post("/api/trigger", headers={**_basic("admin", SENHA),
                                                 "Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403

    def test_trigger_aceita_post_sem_corpo(self, client, auth_config):
        """O hook do qBittorrent faz POST vazio, sem Content-Type.

        Exigir JSON aqui quebraria o modo webhook inteiro.
        """
        with mock.patch.object(g, "get_torrents", return_value=[]), \
             mock.patch.object(g, "write_heartbeat"):
            r = client.post("/api/trigger", headers=_basic("admin", SENHA))
        assert r.status_code == 200


class TestCredenciaisForaDoConfig:
    """`/api/config` nao mexe em `webui`; a senha nao sai no GET."""

    def test_post_config_nao_altera_credenciais(self, client, auth_config):
        """Sem isto, a troca de senha seria contornavel por um POST comum."""
        r = client.post("/api/config",
                        json={"webui": {"user": "atacante", "password": "123"}},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 200

        with open(auth_config) as f:
            salvo = json.load(f)
        assert salvo["webui"]["user"] == "admin"
        assert auth.verificar_senha(SENHA, salvo["webui"]["password"])

    def test_credencial_antiga_continua_valendo_apos_post(self, client, auth_config):
        client.post("/api/config", json={"webui": {"user": "atacante", "password": "123"}},
                    headers=_basic("admin", SENHA))
        assert client.get("/api/config", headers=_basic("admin", SENHA)).status_code == 200
        assert client.get("/api/config", headers=_basic("atacante", "123")).status_code == 401

    def test_get_config_nao_devolve_a_senha(self, client, auth_config):
        corpo = client.get("/api/config", headers=_basic("admin", SENHA)).get_json()
        assert "password" not in corpo.get("webui", {})
        assert corpo["webui"]["user"] == "admin"
        assert SENHA not in json.dumps(corpo)

    def test_get_config_nao_apaga_a_senha_do_cache(self, client, auth_config):
        """A copia devolvida e profunda.

        `load_config()` devolve o objeto em cache: remover a senha dele
        apagaria a credencial do processo inteiro e o proximo login falharia.
        """
        client.get("/api/config", headers=_basic("admin", SENHA))
        assert g.get_config()["webui"].get("password")
        assert client.get("/api/config", headers=_basic("admin", SENHA)).status_code == 200


class TestArquivosEstaticosAutenticados:
    """`/index.html` nao pode ser publico enquanto `/` pede senha."""

    ARQUIVOS = ["/index.html", "/i18n.js", "/favicon.svg"]

    @pytest.mark.parametrize("rota", ARQUIVOS + ["/"])
    def test_sem_credencial_recusa(self, rota, client, auth_config):
        assert client.get(rota).status_code == 401

    @pytest.mark.parametrize("rota", ARQUIVOS + ["/"])
    def test_com_credencial_serve(self, rota, client, auth_config):
        assert client.get(rota, headers=_basic("admin", SENHA)).status_code == 200

    def test_health_continua_publico(self, client, auth_config):
        """Healthcheck do Docker roda sem credencial."""
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.get_json() == {"status": "ok"}

    @pytest.mark.parametrize("alvo", [
        "/../config.json", "/..%2fconfig.json", "/%2e%2e/config.json",
        "/....//config.json", "/app/web.py", "/static/../config.json",
    ])
    def test_path_traversal_nao_escapa_de_static(self, alvo, client, auth_config):
        r = client.get(alvo, headers=_basic("admin", SENHA))
        assert r.status_code == 404, f"{alvo} devolveu {r.status_code}"


class TestComparacaoDeCredenciais:
    """Usuario e senha sao comparados em tempo constante, sem curto-circuito."""

    def test_senha_e_verificada_mesmo_com_usuario_errado(self, auth_config):
        """Encerrar cedo revelaria, pelo tempo, que o nome de usuario existe."""
        with mock.patch.object(w.auth, "verificar_senha",
                               wraps=w.auth.verificar_senha) as m:
            assert w._check_auth("nao-existe", SENHA) is False
        assert m.called, "a senha precisa ser verificada mesmo com usuario errado"

    def test_usuario_e_verificado_mesmo_com_senha_errada(self, auth_config):
        with mock.patch.object(w.auth, "verificar_usuario",
                               wraps=w.auth.verificar_usuario) as m:
            assert w._check_auth("admin", "errada") is False
        assert m.called

    def test_credencial_correta_passa(self, auth_config):
        assert w._check_auth("admin", SENHA) is True


class TestLimiteDeCorpo:
    """Corpo grande e recusado antes de virar config.json."""

    def test_acima_do_limite_devolve_413(self, client, auth_config):
        corpo = "x" * (w.MAX_BODY_BYTES + 1024)
        r = client.post("/api/config", data=corpo, content_type="application/json",
                        headers=_basic("admin", SENHA))
        assert r.status_code == 413
        assert r.is_json

    def test_dentro_do_limite_passa(self, client, auth_config):
        extensoes = [f".ext{i}" for i in range(500)]
        r = client.post("/api/config", json={"guardian": {"dangerous_extensions": extensoes}},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 200


class TestHeadersDeSeguranca:
    """Respostas trazem os cabecalhos defensivos basicos."""

    @pytest.mark.parametrize("header,valor", [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
    ])
    def test_header_presente(self, header, valor, client, tmp_config):
        r = client.get("/api/health")
        assert r.headers.get(header) == valor


class TestEndpointCredenciais:
    """POST /api/credentials — unica porta para trocar usuario/senha."""

    def test_sem_autenticacao_recusa(self, client, auth_config):
        r = client.post("/api/credentials",
                        json={"current_password": SENHA, "new_password": "outra-senha"})
        assert r.status_code == 401

    def test_senha_atual_errada_recusa(self, client, auth_config):
        r = client.post("/api/credentials",
                        json={"current_password": "chute", "new_password": "outra-senha"},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 403
        assert "senha atual" in r.get_json()["error"]

    def test_senha_nova_curta_recusa(self, client, auth_config):
        r = client.post("/api/credentials",
                        json={"current_password": SENHA, "new_password": "curta"},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 400
        assert str(auth.TAMANHO_MINIMO_SENHA) in r.get_json()["error"]

    def test_sem_nada_para_alterar_recusa(self, client, auth_config):
        r = client.post("/api/credentials", json={"current_password": SENHA},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 400

    def test_troca_apenas_o_usuario(self, client, auth_config):
        r = client.post("/api/credentials",
                        json={"user": "humberto", "current_password": SENHA},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 200
        assert r.get_json()["user"] == "humberto"
        # Mesma senha, nome novo.
        assert client.get("/api/config", headers=_basic("humberto", SENHA)).status_code == 200
        assert client.get("/api/config", headers=_basic("admin", SENHA)).status_code == 401

    def test_troca_apenas_a_senha(self, client, auth_config):
        r = client.post("/api/credentials",
                        json={"current_password": SENHA, "new_password": "senha-nova-999"},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 200
        assert client.get("/api/config",
                          headers=_basic("admin", "senha-nova-999")).status_code == 200
        assert client.get("/api/config", headers=_basic("admin", SENHA)).status_code == 401

    def test_troca_os_dois_de_uma_vez(self, client, auth_config):
        r = client.post("/api/credentials",
                        json={"user": "humberto", "current_password": SENHA,
                              "new_password": "senha-nova-999"},
                        headers=_basic("admin", SENHA))
        assert r.status_code == 200
        assert client.get("/api/config",
                          headers=_basic("humberto", "senha-nova-999")).status_code == 200

    def test_senha_nova_e_gravada_como_hash(self, client, auth_config):
        client.post("/api/credentials",
                    json={"current_password": SENHA, "new_password": "senha-nova-999"},
                    headers=_basic("admin", SENHA))
        with open(auth_config) as f:
            salvo = json.load(f)["webui"]["password"]
        assert auth.e_hash(salvo)
        assert "senha-nova-999" not in salvo

    def test_corpo_nao_json_recusa(self, client, auth_config):
        r = client.post("/api/credentials", data="user=x", content_type="text/plain",
                        headers=_basic("admin", SENHA))
        assert r.status_code == 415

    def test_corpo_que_nao_e_objeto_recusa(self, client, auth_config):
        r = client.post("/api/credentials", json=["lista"], headers=_basic("admin", SENHA))
        assert r.status_code == 400

    def test_auth_desligada_nao_permite_definir_credencial(self, client, tmp_config):
        """Com `webui` vazio, nao ha senha atual que confira — ninguem assume.

        Quem quiser voltar a ter senha reinicia o container: o provisionamento
        gera uma nova e anuncia no log.
        """
        r = client.post("/api/credentials",
                        json={"user": "atacante", "current_password": "",
                              "new_password": "senha-do-atacante"})
        assert r.status_code == 403
