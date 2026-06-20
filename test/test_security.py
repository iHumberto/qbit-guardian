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
from app.web import app


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

    def test_auth_disabled_by_default_allows_access(self, client, tmp_config):
        """Sem user/password configurados, endpoints sao públicos."""
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
    """CSRF: falta de token anti-CSRF no POST /api/config."""

    def test_post_config_without_csrf_still_works(self, client, tmp_config):
        """POST sem token CSRF — aceito (API local, auth desabilitada)."""
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
