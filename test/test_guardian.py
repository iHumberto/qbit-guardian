"""
qbit-guardian — Functional tests.

Testa o motor guardian (analyze_torrent, is_stalled, block_and_search),
endpoints Flask (/api/health, /api/trigger, /api/config),
HTTP Basic Auth e deep merge de config.

Run: .venv/bin/python -m pytest test/test_guardian.py -v
"""

import json
import os
import tempfile
import time
import base64
import requests
from unittest import mock

import pytest

import app.guardian as g
from app.web import app


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def tmp_config():
    """Config.json temporario isolado por teste."""
    import app.web as w

    old_path = w.CONFIG_PATH
    old_gpath = g.CONFIG_PATH

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "qbit": {"url": "http://localhost:8080", "api_key": "test-key"},
            "sonarr": {"url": "http://sonarr:8989", "api_key": "skey"},
            "radarr": {"url": "http://radarr:7878", "api_key": "rkey"},
            "guardian": {
                "check_interval_seconds": 300,
                "valid_media_extensions": [".mkv", ".mp4", ".avi"],
                "dangerous_extensions": [".exe", ".scr", ".bat", ".sh"],
                "remove_stalled": True, "stalled_time": 24, "stalled_unit": "hours",
                "remove_no_seeds": True, "no_seeds_time": 48, "no_seeds_unit": "hours",
                "priority_media": 7, "priority_normal": 1, "priority_skip": 0
            },
            "notifications": {"apprise_url": "http://apprise:8000/notify"},
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


@pytest.fixture
def client(tmp_config):
    """Flask test client."""
    app.config["TESTING"] = True
    return app.test_client()


# ── _time_to_seconds ───────────────────────────────────────────────────

class TestTimeToSeconds:
    """Conversao de unidades de tempo."""

    def test_seconds(self):
        assert g._time_to_seconds(30, "seconds") == 30

    def test_minutes(self):
        assert g._time_to_seconds(5, "minutes") == 300

    def test_hours(self):
        assert g._time_to_seconds(2, "hours") == 7200

    def test_zero(self):
        assert g._time_to_seconds(0, "hours") == 0

    def test_default_unit_is_hours(self):
        """Unidade desconhecida cai no else (horas)."""
        assert g._time_to_seconds(1, "days") == 3600


# ── is_stalled ─────────────────────────────────────────────────────────

class TestIsStalled:
    """Logica de remocao por stalled/sem seeds."""

    def make_torrent(self, state, added_on, seeds=-1, num_complete=-1):
        return {
            "hash": "abc123",
            "name": "test.torrent",
            "state": state,
            "added_on": added_on,
            "num_seeds": seeds,
            "num_complete": num_complete,
        }

    def test_not_stalled_when_disabled(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["remove_stalled"] = False
        g.save_config(cfg)
        t = self.make_torrent("stalledDL", time.time() - 100_000)
        stalled, reason = g.is_stalled(t, cfg)
        assert not stalled

    def test_stalled_over_limit(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["stalled_time"] = 1
        cfg["guardian"]["stalled_unit"] = "hours"
        g.save_config(cfg)
        t = self.make_torrent("stalledDL", time.time() - 7200)
        stalled, reason = g.is_stalled(t, cfg)
        assert stalled
        assert "1h" in reason

    def test_stalled_under_limit(self, tmp_config):
        cfg = g.load_config()
        t = self.make_torrent("stalledDL", time.time() - 60)
        stalled, reason = g.is_stalled(t, cfg)
        assert not stalled

    def test_stalled_only_for_stalled_states(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["stalled_time"] = 1
        cfg["guardian"]["stalled_unit"] = "minutes"
        g.save_config(cfg)
        past = time.time() - 120
        assert g.is_stalled(self.make_torrent("stalledDL", past), cfg)[0]
        assert g.is_stalled(self.make_torrent("stalledUP", past), cfg)[0]
        assert not g.is_stalled(self.make_torrent("downloading", past), cfg)[0]
        assert not g.is_stalled(self.make_torrent("uploading", past), cfg)[0]

    def test_no_seeds_removal(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["no_seeds_time"] = 1
        cfg["guardian"]["no_seeds_unit"] = "hours"
        g.save_config(cfg)
        t = self.make_torrent("downloading", time.time() - 7200, num_complete=0)
        stalled, reason = g.is_stalled(t, cfg)
        assert stalled
        assert "0 seeds" in reason

    def test_no_seeds_with_seeds_present(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["no_seeds_time"] = 1
        cfg["guardian"]["no_seeds_unit"] = "hours"
        g.save_config(cfg)
        t = self.make_torrent("downloading", time.time() - 7200, num_complete=5)
        stalled, reason = g.is_stalled(t, cfg)
        assert not stalled

    def test_zero_time_limit_disables(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["stalled_time"] = 0
        g.save_config(cfg)
        t = self.make_torrent("stalledDL", time.time() - 100_000)
        stalled, reason = g.is_stalled(t, cfg)
        assert not stalled


# ── analyze_torrent ────────────────────────────────────────────────────

class TestAnalyzeTorrent:
    """Analise de torrents com mock das APIs."""

    def make_torrent(self, state="downloading"):
        return {
            "hash": "abc123",
            "name": "Test.Movie.2024",
            "state": state,
            "added_on": time.time(),
            "num_complete": 50,
        }

    def test_skip_completed_uploading_states(self, tmp_config):
        g.load_config()
        for state in ("uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"):
            t = self.make_torrent(state)
            with mock.patch.object(g, "get_files") as m_get_files:
                g.analyze_torrent(t)
                m_get_files.assert_not_called()

    def test_dangerous_extension_triggers_removal(self, tmp_config):
        g.load_config()
        t = self.make_torrent("downloading")

        with mock.patch.object(g, "get_files") as m_files, \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search") as m_block, \
             mock.patch.object(g, "send_notification") as m_notify:

            m_files.return_value = [
                {"index": 0, "name": "movie.mkv"},
                {"index": 1, "name": "crack.exe"},
            ]

            g.analyze_torrent(t)

            m_remove.assert_called_once_with("abc123")
            m_block.assert_called_once_with("abc123", "Test.Movie.2024")
            m_notify.assert_called_once()
            assert "Arquivos perigosos" in m_notify.call_args[0][1]

    def test_no_valid_media_extension_triggers_removal(self, tmp_config):
        g.load_config()
        t = self.make_torrent("downloading")

        with mock.patch.object(g, "get_files") as m_files, \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search") as m_block, \
             mock.patch.object(g, "send_notification") as m_notify:

            m_files.return_value = [
                {"index": 0, "name": "readme.txt"},
                {"index": 1, "name": "info.nfo"},
            ]

            g.analyze_torrent(t)

            m_remove.assert_called_once()
            m_block.assert_called_once()
            m_notify.assert_called_once()
            assert "Nenhum arquivo" in m_notify.call_args[0][1]

    def test_valid_media_no_removal_optimizes_priority(self, tmp_config):
        g.load_config()
        t = self.make_torrent("downloading")

        with mock.patch.object(g, "get_files") as m_files, \
             mock.patch.object(g, "set_file_priority") as m_prio, \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search") as m_block:

            m_files.return_value = [
                {"index": 0, "name": "movie.mkv"},
                {"index": 1, "name": "info.nfo"},
                {"index": 2, "name": "subs.srt"},
            ]

            g.analyze_torrent(t)

            m_remove.assert_not_called()
            m_block.assert_not_called()
            assert m_prio.call_count == 3
            assert m_prio.call_args_list[0][0][2] == 7

    def test_stalled_torrent_removed_without_file_check(self, tmp_config):
        g.load_config()
        past = time.time() - 100_000
        t = {
            "hash": "stalledhash",
            "name": "Old.Stalled.Torrent",
            "state": "stalledDL",
            "added_on": past,
            "num_complete": 0,
        }

        with mock.patch.object(g, "get_files") as m_files, \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "send_notification") as m_notify:

            g.analyze_torrent(t)

            m_files.assert_not_called()
            m_remove.assert_called_once_with("stalledhash")
            m_notify.assert_called_once()
            assert "stalled" in m_notify.call_args[0][0].lower()

    def test_empty_files_list_skips(self, tmp_config):
        g.load_config()
        t = self.make_torrent("downloading")

        with mock.patch.object(g, "get_files") as m_files, \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search") as m_block:

            m_files.return_value = []

            g.analyze_torrent(t)

            m_remove.assert_not_called()
            m_block.assert_not_called()

    def test_notification_silent_when_no_url(self, tmp_config):
        cfg = g.load_config()
        cfg["notifications"]["apprise_url"] = ""
        g.save_config(cfg)

        t = self.make_torrent("downloading")

        with mock.patch.object(g, "get_files") as m_files, \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search"), \
             mock.patch("app.guardian.requests.post") as m_post:

            m_files.return_value = [{"index": 0, "name": "virus.exe"}]

            g.analyze_torrent(t)

            m_remove.assert_called_once()
            apprise_calls = [c for c in m_post.call_args_list
                             if "apprise" in str(c.args[0])]
            assert len(apprise_calls) == 0


# ── _prune_processed ───────────────────────────────────────────────────

class TestPruneProcessed:
    """Limpeza e limite do set _processed."""

    def test_prune_removes_absent_hashes(self):
        g._processed = {"h1", "h2", "h3"}
        current = {"h2", "h3", "h4"}
        g._prune_processed(current)
        assert g._processed == {"h2", "h3"}

    def test_prune_enforces_hard_cap(self):
        """Quando _processed excede MAX_PROCESSED_SIZE, trunca."""
        g._processed = set(f"hash_{i}" for i in range(15_000))
        assert len(g._processed) == 15_000

        current = set(f"hash_{i}" for i in range(15_000))
        g._prune_processed(current)

        assert len(g._processed) == g.MAX_PROCESSED_SIZE

    def test_prune_noop_when_under_limit(self):
        g._processed = {"h1", "h2", "h3"}
        current = {"h1", "h2", "h3"}
        g._prune_processed(current)
        assert g._processed == {"h1", "h2", "h3"}

    def test_prune_intersection_before_cap(self):
        """Primeiro remove ausentes, depois aplica cap."""
        g._processed = set(f"hash_{i}" for i in range(12_000))
        current = set(f"hash_{i}" for i in range(0, 12_000, 2))  # metade
        g._prune_processed(current)
        assert len(g._processed) == 6_000  # metade de 12000, abaixo do cap


# ── Flask endpoints ────────────────────────────────────────────────────

class TestFlaskEndpoints:
    """Testes para os endpoints REST."""

    def test_health_returns_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json == {"status": "ok"}

    def test_get_config_returns_valid_json(self, client, tmp_config):
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json
        assert "qbit" in data
        assert "sonarr" in data
        assert "radarr" in data
        assert "guardian" in data
        assert "notifications" in data
        assert "webui" in data

    def test_post_config_persists_with_deep_merge(self, client, tmp_config):
        """POST faz deep merge — campos ausentes preservados."""
        payload = {
            "qbit": {"url": "http://10.0.0.1:9090"}
        }
        r = client.post("/api/config", json=payload)
        assert r.status_code == 200

        r2 = client.get("/api/config")
        saved = r2.json
        # Campos enviados: atualizados
        assert saved["qbit"]["url"] == "http://10.0.0.1:9090"
        # Campo nao enviado: preservado
        assert saved["qbit"]["api_key"] == "test-key"
        # Outras secoes: intactas
        assert saved["guardian"]["check_interval_seconds"] == 300

    def test_trigger_endpoint_with_mock(self, client, tmp_config):
        g.load_config()
        g._processed.clear()

        mock_torrents = [
            {"hash": "h1", "name": "test1", "state": "downloading",
             "added_on": time.time(), "num_complete": 50},
        ]

        with mock.patch.object(g, "get_torrents", return_value=mock_torrents), \
             mock.patch.object(g, "analyze_torrent") as m_analyze:

            r = client.post("/api/trigger")
            assert r.status_code == 200
            data = r.json
            assert data["status"] == "ok"
            assert data["checked"] == 1
            assert data["new"] == 1
            m_analyze.assert_called_once()

    def test_trigger_skips_already_processed(self, client, tmp_config):
        g.load_config()
        g._processed.clear()
        g._processed.add("h1")

        mock_torrents = [{"hash": "h1", "name": "test1", "state": "downloading",
                          "added_on": time.time(), "num_complete": 50}]

        with mock.patch.object(g, "get_torrents", return_value=mock_torrents), \
             mock.patch.object(g, "analyze_torrent") as m_analyze:

            r = client.post("/api/trigger")
            assert r.status_code == 200
            assert r.json["new"] == 0
            m_analyze.assert_not_called()

    def test_trigger_propagates_error(self, client, tmp_config):
        g.load_config()

        with mock.patch.object(g, "get_torrents", side_effect=Exception("qBit offline")):
            r = client.post("/api/trigger")
            assert r.status_code == 500
            assert r.json["status"] == "error"
            assert "qBit offline" in r.json["message"]


# ── HTTP Basic Auth ────────────────────────────────────────────────────

class TestHttpAuth:
    """Autenticacao HTTP Basic na Web UI."""

    AUTH = "Basic " + base64.b64encode(b"admin:secret").decode()

    def _enable_auth(self, tmp_config):
        with open(tmp_config) as f:
            cfg = json.load(f)
        cfg["webui"] = {"user": "admin", "password": "secret"}
        with open(tmp_config, "w") as f:
            json.dump(cfg, f)

    def test_auth_required_when_configured(self, client, tmp_config):
        """Com auth habilitada, endpoints protegidos exigem credenciais."""
        self._enable_auth(tmp_config)
        r = client.get("/")
        assert r.status_code == 401

    def test_auth_bypass_with_correct_credentials(self, client, tmp_config):
        """Credenciais corretas acessam endpoints protegidos."""
        self._enable_auth(tmp_config)
        r = client.get("/", headers={"Authorization": self.AUTH})
        assert r.status_code == 200

    def test_auth_blocks_post_config(self, client, tmp_config):
        self._enable_auth(tmp_config)
        r = client.post("/api/config", json={})
        assert r.status_code == 401

    def test_auth_allows_post_config_with_credentials(self, client, tmp_config):
        self._enable_auth(tmp_config)
        r = client.post("/api/config", json={"qbit": {"url": "http://test:1", "api_key": "k"}},
                        headers={"Authorization": self.AUTH})
        assert r.status_code == 200

    def test_auth_blocks_trigger(self, client, tmp_config):
        self._enable_auth(tmp_config)
        r = client.post("/api/trigger")
        assert r.status_code == 401

    def test_health_always_public_without_auth(self, client, tmp_config):
        self._enable_auth(tmp_config)
        r = client.get("/api/health")
        assert r.status_code == 200


# ── Deep merge ─────────────────────────────────────────────────────────

class TestDeepMerge:
    """Deep merge de config no POST /api/config."""

    def test_merge_preserves_nested_dicts(self, client, tmp_config):
        """Subobjetos nao enviados permanecem intactos."""
        r = client.post("/api/config", json={
            "guardian": {"check_interval_seconds": 999}
        })
        assert r.status_code == 200
        saved = client.get("/api/config").json
        assert saved["guardian"]["check_interval_seconds"] == 999
        assert saved["guardian"]["valid_media_extensions"] == [".mkv", ".mp4", ".avi"]
        assert saved["qbit"]["url"] == "http://localhost:8080"
        assert saved["sonarr"]["api_key"] == "skey"

    def test_merge_adds_new_top_level_keys(self, client, tmp_config):
        """Nova chave top-level e adicionada."""
        r = client.post("/api/config", json={
            "future_section": {"enabled": True}
        })
        assert r.status_code == 200
        saved = client.get("/api/config").json
        assert saved["future_section"] == {"enabled": True}
        assert "qbit" in saved  # intacto

    def test_merge_overwrites_scalar_values(self, client, tmp_config):
        """Valores escalares sao sobrescritos."""
        r = client.post("/api/config", json={
            "qbit": {"url": "http://new-host:9090", "api_key": "new-key",
                     "extra_field": "bonus"}
        })
        assert r.status_code == 200
        saved = client.get("/api/config").json
        assert saved["qbit"]["url"] == "http://new-host:9090"
        assert saved["qbit"]["extra_field"] == "bonus"


# ── Config cache sync (web.py ↔ guardian.py) ────────────────────────────

class TestConfigCacheSync:
    """Sincronizacao do cache _config entre web.py e guardian.py."""

    def test_post_config_updates_guardian_cache(self, client, tmp_config):
        """POST /api/config deve atualizar o cache _config do guardian."""
        g.load_config()  # popula o cache
        assert g.get_config()["guardian"]["check_interval_seconds"] == 300

        r = client.post("/api/config", json={
            "guardian": {"check_interval_seconds": 0}
        })
        assert r.status_code == 200

        # Verifica que get_config() (cache) reflete a alteracao
        cached = g.get_config()
        assert cached["guardian"]["check_interval_seconds"] == 0, \
            f"Cache stale: esperado 0, obtido {cached['guardian']['check_interval_seconds']}"

    def test_post_config_persists_disk_and_cache(self, client, tmp_config):
        """POST deve persistir no disco E no cache simultaneamente."""
        g.load_config()
        old_interval = g.get_config()["guardian"]["check_interval_seconds"]

        r = client.post("/api/config", json={
            "guardian": {"check_interval_seconds": 60}
        })
        assert r.status_code == 200

        # Cache atualizado
        assert g.get_config()["guardian"]["check_interval_seconds"] == 60

        # Disco atualizado (via load_config que rele do disco)
        g._config = None  # invalida cache para forcar releitura do disco
        disk = g.load_config()
        assert disk["guardian"]["check_interval_seconds"] == 60

    def test_guardian_loop_reloads_interval(self, tmp_config):
        """Guardian loop deve recarregar check_interval_seconds a cada iteracao."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["check_interval_seconds"] = 1  # entra no loop
        g.save_config(cfg)

        call_count = [0]
        original_get_config = g.get_config  # salva referencia antes do mock

        def mock_get_config():
            call_count[0] += 1
            cfg_copy = original_get_config().copy()  # usa a original, nao o mock
            # Na segunda chamada, muda para webhook mode
            if call_count[0] >= 2:
                cfg_copy["guardian"] = dict(cfg_copy["guardian"])
                cfg_copy["guardian"]["check_interval_seconds"] = 0
            return cfg_copy

        with mock.patch.object(g, "get_config", side_effect=mock_get_config), \
             mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "get_torrents", return_value=[]), \
             mock.patch.object(g, "time", mock.MagicMock()) as m_time:

            g.guardian_loop()

            # Deve ter saido do loop (entrou em webhook mode)
            # sleep nao deve ser chamado com intervalo > 0 apos a troca
            # O importante: a funcao retornou (nao entrou em loop infinito)
            assert call_count[0] >= 2, "get_config deveria ter sido chamada ao menos 2x"


# ── Notificacoes ─────────────────────────────────────────────────────────

class TestSendNotification:
    """send_notification com verify=False direto (homelab, SSL auto-assinado)."""

    def test_send_notification_uses_verify_false(self, tmp_config):
        """Toda chamada Apprise usa verify=False (homelab)."""
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"]["apprise_url"] = "https://apprise.home.arpa/notify"
        g.save_config(cfg)

        with mock.patch("app.guardian.requests.post") as m_post:
            g.send_notification("Test", "Body")
            m_post.assert_called_once()
            _, kwargs = m_post.call_args
            assert kwargs["verify"] is False

    def test_no_notification_when_url_empty(self, tmp_config):
        """URL vazia → requests.post NUNCA chamado."""
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"]["apprise_url"] = ""
        g.save_config(cfg)

        with mock.patch("app.guardian.requests.post") as m_post:
            g.send_notification("Test", "Body")
            m_post.assert_not_called()

    def test_connection_error_is_logged_not_raised(self, tmp_config):
        """Erro de conexao loga erro sem propagar excecao."""
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"]["apprise_url"] = "https://apprise.home.arpa/notify"
        g.save_config(cfg)

        with mock.patch("app.guardian.requests.post",
                       side_effect=requests.exceptions.ConnectionError("refused")), \
             mock.patch("app.guardian.log.error") as m_log:
            g.send_notification("Test", "Body")
            m_log.assert_called_once()
            assert "Apprise" in m_log.call_args[0][0]

    def test_sslerror_is_logged_as_error(self, tmp_config):
        """SSLError em homelab vira log.error (nao tenta fallback)."""
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"]["apprise_url"] = "https://apprise.home.arpa/notify"
        g.save_config(cfg)

        with mock.patch("app.guardian.requests.post",
                       side_effect=requests.exceptions.SSLError("cert verify failed")), \
             mock.patch("app.guardian.log.error") as m_log:
            g.send_notification("Test", "Body")
            # Com verify=False, SSLError nao deve ocorrer na pratica,
            # mas se ocorrer por algum motivo, deve ser logado
            m_log.assert_called_once()
            assert "Apprise" in m_log.call_args[0][0]


# ── qBit session ────────────────────────────────────────────────────────

class TestQbitSession:
    """get_qbit_session() com verify=False (homelab, SSL auto-assinado)."""

    def test_session_has_verify_false(self, tmp_config):
        """Sessao do qBittorrent SEMPRE usa verify=False."""
        g.load_config()
        cfg = g.get_config()
        cfg["qbit"]["url"] = "https://torrent.home.arpa/"
        g.save_config(cfg)

        # Forcar reset da sessao
        g._qbit_session = None
        g._qbit_base = None

        sess, base = g.get_qbit_session()
        assert sess.verify is False
        assert base == "https://torrent.home.arpa"

    def test_session_reused_when_base_unchanged(self, tmp_config):
        """Sessao e reutilizada quando a URL base nao muda."""
        g.load_config()
        cfg = g.get_config()
        cfg["qbit"]["url"] = "https://torrent.home.arpa/"
        g.save_config(cfg)

        g._qbit_session = None
        g._qbit_base = None

        sess1, _ = g.get_qbit_session()
        sess2, _ = g.get_qbit_session()
        assert sess1 is sess2

    def test_session_recreated_when_base_changes(self, tmp_config):
        """Sessao e recriada quando a URL base muda."""
        g.load_config()
        cfg = g.get_config()
        cfg["qbit"]["url"] = "https://torrent.home.arpa/"
        g.save_config(cfg)

        g._qbit_session = None
        g._qbit_base = None

        sess1, _ = g.get_qbit_session()

        # Mudar URL
        cfg["qbit"]["url"] = "http://192.168.1.10:8080/"
        g.save_config(cfg)

        sess2, _ = g.get_qbit_session()
        assert sess1 is not sess2
        assert sess2.verify is False  # Nova sessao tambem verify=False
