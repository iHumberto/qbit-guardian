"""
qbit-guardian — Security tests.

Vetores primários: CSRF, XSS, API key exposure, path traversal.
Vetores secundários: race condition, JSON injection.
Vetores de borda: Unicode, config corrompido.

Run: .venv/bin/python -m pytest test/test_security.py -v
"""

import json
import os
import tempfile
import pytest
from web import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def tmp_config():
    """Cria config.json temporário e restaura depois."""
    import web as w
    import guardian as g
    old_path = w.CONFIG_PATH
    old_gpath = g.CONFIG_PATH

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "qbit": {"host": "localhost", "port": 8080, "api_key": "test-key"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv", ".mp4"],
                "dangerous_extensions": [".exe", ".scr"],
                "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": ""}
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


# ── Vetores primários ──────────────────────────────────────────────────

class TestXSS:
    """XSS: script injection via config fields."""

    def test_xss_in_extensions_sanitized(self, client, tmp_config):
        """Injetar <script> no campo de extensoes nao deve executar."""
        payload = {
            "qbit": {"host": "localhost", "port": 8080, "api_key": "x"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
        # O frontend deve escapar na renderizacao — testamos que o server nao rejeita
        with open(tmp_config) as f:
            saved = json.load(f)
        assert "<script>" in saved["guardian"]["dangerous_extensions"][0]

    def test_xss_in_html_page_no_inline_script(self, client, tmp_config):
        """Pagina HTML nao deve conter dados do usuario inline (escapados)."""
        r = client.get("/")
        assert r.status_code == 200
        html = r.data.decode()
        # Nao deve ter script inline com dados (alem do codigo legítimo)
        assert "alert(1)" not in html.lower()


class TestCSRF:
    """CSRF: falta de token anti-CSRF no POST /api/config."""

    def test_post_config_without_csrf_still_works(self, client, tmp_config):
        """POST sem token CSRF — aceito (API local, sem auth por enquanto)."""
        r = client.post("/api/config", json={
            "qbit": {"host": "test", "port": 8080, "api_key": "k"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
        # Currently accepted — this test DOCUMENTS the gap
        # When CSRF protection is added, this test should be updated to EXPECT rejection
        assert r.status_code == 200

    def test_invalid_json_rejected(self, client):
        """JSON invalido deve ser rejeitado com 400."""
        r = client.post("/api/config", data="not json", content_type="application/json")
        assert r.status_code == 400


class TestConfigIntegrity:
    """Verifica que config.json mantem integridade."""

    def test_missing_fields_preserved(self, client, tmp_config):
        """Campos nao enviados no POST nao devem ser perdidos."""
        # Salva config inicial com um valor conhecido
        with open(tmp_config, "w") as f:
            json.dump({"qbit": {"host": "keep-me", "port": 8080, "api_key": "k"},
                       "sonarr": {"host": "", "port": 8989, "api_key": ""},
                       "radarr": {"host": "", "port": 7878, "api_key": ""},
                       "guardian": {
                           "check_interval_seconds": 300,
                           "valid_media_extensions": [".mkv"],
                           "dangerous_extensions": [],
                           "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                           "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                           "priority_media": 7, "priority_normal": 1, "priority_skip": 0
                       },
                       "notifications": {"apprise_url": ""}}, f)

        # POST sem o campo qbit.host
        r = client.post("/api/config", json={
            "qbit": {"port": 9090, "api_key": "new-key"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
        assert r.status_code == 200

        # Verifica que qbit.host FOI SOBRESCRITO (comportamento atual: replace total)
        # Isso e um GAP — o POST substitui o objeto inteiro, nao faz merge
        with open(tmp_config) as f:
            saved = json.load(f)
        # O POST atual substitui o objeto qbit inteiro — host foi perdido
        assert "host" not in saved["qbit"]


# ── Vetores secundários ────────────────────────────────────────────────

class TestRaceCondition:
    """Simula race condition entre Web UI e guardian loop."""

    def test_concurrent_read_write_config(self, tmp_config):
        """Multiplas leituras simultaneas nao corrompem o arquivo."""
        import guardian as g

        # Escreve config valido
        valid = {"qbit": {"host": "x", "port": 1, "api_key": "k"},
                 "sonarr": {"host": "", "port": 8989, "api_key": ""},
                 "radarr": {"host": "", "port": 7878, "api_key": ""},
                 "guardian": {
                     "check_interval_seconds": 300,
                     "valid_media_extensions": [], "dangerous_extensions": [],
                     "remove_stalled": False, "stalled_time": 0, "stalled_unit": "hours",
                     "remove_no_seeds": False, "no_seeds_time": 0, "no_seeds_unit": "hours",
                     "priority_media": 7, "priority_normal": 1, "priority_skip": 0
                 },
                 "notifications": {"apprise_url": ""}}
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

        # Config final deve ser JSON valido
        with open(tmp_config) as f:
            json.load(f)


class TestJSONInjection:
    """JSON injection via API."""

    def test_nested_json_injection_in_api_key(self, client, tmp_config):
        """Injetar JSON malicioso via campo api_key."""
        payload = {
            "qbit": {"host": "x", "port": 8080, "api_key": '"; alert(1); "'},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
        # API key com caracteres especiais deve ser salva como string literal
        assert saved["qbit"]["api_key"] == '"; alert(1); "'

    def test_priority_out_of_range(self, client, tmp_config):
        """Prioridade >7 ou <0 deve ser aceita mas cabe ao guardian validar."""
        payload = {
            "qbit": {"host": "x", "port": 8080, "api_key": "k"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
        # Server aceita qualquer numero — validacao fica pro guardian loop


# ── Vetores de borda ───────────────────────────────────────────────────

class TestEdgeCases:
    """Casos extremos: Unicode, config corrompido, campos vazios."""

    def test_unicode_in_extensions(self, client, tmp_config):
        """Extensoes com caracteres Unicode devem ser preservadas."""
        payload = {
            "qbit": {"host": "x", "port": 8080, "api_key": "k"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
            "qbit": {"host": "x", "port": 8080, "api_key": "k"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
        import guardian as g
        g._config = None

        with open(tmp_config, "w") as f:
            f.write("{invalid json!!!")

        with pytest.raises(json.JSONDecodeError):
            g.load_config()

    def test_config_with_extra_unknown_fields(self, client, tmp_config):
        """Campos desconhecidos sao preservados silenciosamente."""
        payload = {
            "qbit": {"host": "x", "port": 8080, "api_key": "k"},
            "sonarr": {"host": "", "port": 8989, "api_key": ""},
            "radarr": {"host": "", "port": 7878, "api_key": ""},
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
