"""
qbit-guardian — Functional tests.

Testa o motor guardian (analyze_torrent, is_stalled, block_and_search),
endpoints Flask (/api/health, /api/trigger, /api/config),
HTTP Basic Auth e deep merge de config.

Run: .venv/bin/python -m pytest test/test_guardian.py -v
"""

import contextlib
import json
import os
import re
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
        assert g.is_stalled(self.make_torrent("metaDL", past), cfg)[0]
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
             mock.patch.object(g, "block_and_search") as m_block, \
             mock.patch.object(g, "send_notification") as m_notify:

            g.analyze_torrent(t)

            m_files.assert_not_called()
            m_block.assert_called_once_with("stalledhash", "Old.Stalled.Torrent")
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


# ── set_file_priority ──────────────────────────────────────────────────

class TestSetFilePriority:
    """Prioridade invalida devolvia HTTP 400 em silencio no qBittorrent.

    O qBittorrent aceita apenas -1, 0, 1, 6 e 7. Qualquer outro valor (ex.: 4)
    devolve 400 "A prioridade nao e valida" — e como o retorno do POST nao era
    conferido, a priorizacao simplesmente nao acontecia, sem nenhum sinal.
    """

    @pytest.mark.parametrize("prio", [-1, 0, 1, 6, 7])
    def test_prioridade_valida_envia(self, prio, tmp_config):
        g.load_config()
        with mock.patch.object(g, "get_qbit_session") as m_sess:
            sess = mock.MagicMock()
            sess.post.return_value = mock.MagicMock(status_code=200, text="")
            m_sess.return_value = (sess, "http://qbit")
            g.set_file_priority("hash123", 0, prio)
        sess.post.assert_called_once()

    @pytest.mark.parametrize("prio", [2, 3, 4, 5, 8, 99])
    def test_prioridade_invalida_nao_envia_e_avisa(self, prio, tmp_config):
        g.load_config()
        with mock.patch.object(g, "get_qbit_session") as m_sess, \
             mock.patch.object(g, "log") as m_log:
            sess = mock.MagicMock()
            m_sess.return_value = (sess, "http://qbit")
            g.set_file_priority("hash123", 0, prio)

        assert not sess.post.called, f"prioridade {prio} nao deveria ser enviada"
        m_log.warning.assert_called_once()

    def test_erro_da_api_gera_warning(self, tmp_config):
        """Falha do filePrio nao pode passar em silencio."""
        g.load_config()
        with mock.patch.object(g, "get_qbit_session") as m_sess, \
             mock.patch.object(g, "log") as m_log:
            sess = mock.MagicMock()
            sess.post.return_value = mock.MagicMock(
                status_code=400, text="A prioridade não é válida")
            m_sess.return_value = (sess, "http://qbit")
            g.set_file_priority("hash123", 0, 7)

        m_log.warning.assert_called_once()


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

    def test_trigger_reprocessa_torrent_sem_metadados(self, client, tmp_config):
        """Regressao: nao 'queimar' torrent cuja analise foi incompleta (sem metadados).

        Sintoma real: torrents baixados via magnet eram vistos em metaDL,
        ignorados por falta de metadados ('sem metadados') e MESMO ASSIM
        marcados como processados. Quando os metadados chegavam — trazendo
        arquivos .exe/.scr — o guardian nunca mais os validava. So voltavam a
        ser tratados quando o container reiniciava (o _processed e em memoria),
        o que explicava a rajada de remocoes apos um restart.
        """
        g.load_config()
        g._processed.clear()

        torrent = {"hash": "h1", "name": "Fake.Movie.2024", "state": "metaDL",
                   "added_on": time.time(), "num_complete": 10}

        # Ciclo 1 — torrent ainda sem metadados (magnet resolvendo)
        with mock.patch.object(g, "get_torrents", return_value=[torrent]), \
             mock.patch.object(g, "get_files", return_value=[]):
            r = client.post("/api/trigger")
            assert r.status_code == 200
            assert r.json["new"] == 1

        assert "h1" not in g._processed, (
            "torrent sem metadados foi marcado como processado — "
            "nunca mais sera reavaliado quando os metadados chegarem"
        )

        # Ciclo 2 — metadados chegaram, com arquivo malicioso
        with mock.patch.object(g, "get_torrents", return_value=[torrent]), \
             mock.patch.object(g, "get_files",
                               return_value=[{"index": 0, "name": "malware.exe"}]), \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "send_notification"):
            r = client.post("/api/trigger")
            assert r.status_code == 200
            assert m_remove.call_count == 1, (
                "torrent malicioso nao foi removido apos os metadados chegarem"
            )


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


# ── Templates de notificacao ────────────────────────────────────────────

class TestRenderTemplate:
    """Substituicao de {{variavel}} no texto da notificacao."""

    def test_substitui_variaveis(self):
        assert g._render_template(
            "Nome: {{torrentName}} / {{reason}}",
            {"torrentName": "Show.S01E01", "reason": "0 seeds"}
        ) == "Nome: Show.S01E01 / 0 seeds"

    def test_aceita_espacos_dentro_das_chaves(self):
        assert g._render_template("{{ torrentName }}", {"torrentName": "X"}) == "X"

    def test_placeholder_desconhecido_fica_literal(self):
        """Erro de digitacao tem que aparecer, nao sumir em silencio."""
        assert g._render_template("{{naoExiste}}", {"torrentName": "X"}) == "{{naoExiste}}"

    def test_converte_valores_nao_string(self):
        assert g._render_template("{{mediaCount}}", {"mediaCount": 3}) == "3"

    def test_variavel_repetida(self):
        assert g._render_template("{{a}}-{{a}}", {"a": "x"}) == "x-x"

    def test_texto_sem_variavel_passa_intacto(self):
        assert g._render_template("sem variaveis", {"a": 1}) == "sem variaveis"


class TestNotifyToggles:
    """Dois niveis de liga/desliga: o geral e o do tipo de mensagem."""

    def _cfg(self, geral=True, **tipos):
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"] = {
            "apprise_url": "http://apprise:8000/notify",
            "enabled": geral,
            "events": {ev: {"enabled": on, **g.DEFAULT_NOTIFICATIONS[ev]}
                       for ev, on in tipos.items()},
        }
        g.save_config(cfg)

    def test_envia_com_os_dois_ligados(self, tmp_config):
        self._cfg(geral=True, optimized=True)
        with mock.patch.object(g, "send_notification") as m:
            g.notify("optimized", torrentName="X")
        m.assert_called_once()

    def test_geral_desligado_nao_envia(self, tmp_config):
        """Toggle geral OFF cala todos os tipos, mesmo os ligados."""
        self._cfg(geral=False, optimized=True)
        with mock.patch.object(g, "send_notification") as m:
            g.notify("optimized", torrentName="X")
        assert not m.called

    def test_tipo_desligado_nao_envia(self, tmp_config):
        self._cfg(geral=True, optimized=False)
        with mock.patch.object(g, "send_notification") as m:
            g.notify("optimized", torrentName="X")
        assert not m.called

    def test_tipo_desligado_nao_afeta_os_outros(self, tmp_config):
        self._cfg(geral=True, optimized=False, removed=True)
        with mock.patch.object(g, "send_notification") as m:
            g.notify("optimized", torrentName="X")
            g.notify("removed", torrentName="Y", reason="r", extensions="")
        assert m.call_count == 1
        assert "Y" in m.call_args[0][1]

    @pytest.mark.parametrize("event", ["optimized", "removed", "stalled"])
    def test_config_sem_a_chave_events_envia_com_o_padrao(self, tmp_config, event):
        """REGRESSAO: config anterior a v2.1.0 nao tem `events`.

        load_config() nao faz merge com os defaults quando o arquivo existe,
        entao quem atualizar o container sem tocar na config precisa continuar
        recebendo notificacao — com o texto de sempre.
        """
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"] = {"apprise_url": "http://apprise:8000/notify"}
        g.save_config(cfg)

        with mock.patch.object(g, "send_notification") as m:
            g.notify(event, torrentName="X", reason="r", extensions="",
                     state="s", stalledTime="", priorityMedia=7,
                     priorityAux=1, mediaCount=2)

        m.assert_called_once()
        assert m.call_args[0][0] == g.DEFAULT_NOTIFICATIONS[event]["title"]


class TestNotificationDefaults:
    """Fallback campo a campo em `_notification_event`."""

    def _com_evento(self, ev, dados):
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"] = {"apprise_url": "x", "events": {ev: dados}}
        g.save_config(cfg)
        return g.get_config()

    @pytest.mark.parametrize("vazio", ["", "   ", None, 123, []])
    def test_template_invalido_cai_no_padrao(self, tmp_config, vazio):
        """Caixa apagada na Web UI nao pode virar notificacao em branco."""
        cfg = self._com_evento("removed", {"template": vazio})
        assert g._notification_event(cfg, "removed")["template"] == \
            g.DEFAULT_NOTIFICATIONS["removed"]["template"]

    @pytest.mark.parametrize("vazio", ["", "   ", None, 7])
    def test_titulo_invalido_cai_no_padrao(self, tmp_config, vazio):
        cfg = self._com_evento("removed", {"title": vazio})
        assert g._notification_event(cfg, "removed")["title"] == \
            g.DEFAULT_NOTIFICATIONS["removed"]["title"]

    def test_titulo_customizado_e_respeitado(self, tmp_config):
        cfg = self._com_evento("removed", {"title": "Meu titulo"})
        assert g._notification_event(cfg, "removed")["title"] == "Meu titulo"

    def test_enabled_ausente_significa_ligado(self, tmp_config):
        cfg = self._com_evento("removed", {"template": "x"})
        assert g._notification_event(cfg, "removed")["enabled"] is True


class TestNotificationCallSites:
    """As tres origens de notificacao passam as variaveis que anunciam.

    Se a Web UI oferece {{mediaCount}} mas o call site nao passa mediaCount, o
    placeholder vai literal para a notificacao do usuario. Estes testes usam um
    template com TODAS as variaveis declaradas e exigem que nada sobre.
    """

    def _template_com_todas(self, event):
        return " ".join("{{%s}}" % v for v in g.NOTIFICATION_VARIABLES[event])

    def _preparar(self, event, **guardian_cfg):
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"] = {
            "apprise_url": "http://apprise:8000/notify",
            "enabled": True,
            "events": {event: {"enabled": True,
                               "template": self._template_com_todas(event)}},
        }
        cfg["guardian"].update(guardian_cfg)
        g.save_config(cfg)

    def test_stalled_passa_todas_as_variaveis(self, tmp_config):
        self._preparar("stalled", remove_stalled=True, stalled_time=15,
                       stalled_unit="minutes")
        torrent = {"hash": "h1", "name": "Show.S01E01", "state": "stalledDL",
                   "added_on": 0, "num_complete": 5}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "remove_torrent"):
            assert g.check_stalled_and_remove(torrent)

        corpo = m.call_args[0][1]
        assert "{{" not in corpo, f"variavel nao passada pelo call site: {corpo}"
        assert "Show.S01E01" in corpo
        assert "stalledDL" in corpo
        assert "15 minutes" in corpo

    def test_removed_passa_todas_as_variaveis(self, tmp_config):
        self._preparar("removed")
        torrent = {"hash": "h1", "name": "Filme.2020", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "get_files",
                               return_value=[{"name": "setup.exe", "index": 0}]), \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "remove_torrent"):
            assert g.analyze_torrent(torrent)

        corpo = m.call_args[0][1]
        assert "{{" not in corpo, f"variavel nao passada pelo call site: {corpo}"
        assert "Filme.2020" in corpo
        assert ".exe" in corpo

    def test_optimized_passa_todas_as_variaveis(self, tmp_config):
        self._preparar("optimized", priority_media=7, priority_normal=1,
                       priority_skip=0)
        torrent = {"hash": "h1", "name": "Serie.S02E03", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "get_files",
                               return_value=[{"name": "ep.mkv", "index": 0},
                                             {"name": "info.nfo", "index": 1}]), \
             mock.patch.object(g, "set_file_priority"):
            assert g.analyze_torrent(torrent)

        corpo = m.call_args[0][1]
        assert "{{" not in corpo, f"variavel nao passada pelo call site: {corpo}"
        assert "Serie.S02E03" in corpo
        assert "1" in corpo  # mediaCount

    @pytest.mark.parametrize("event", ["optimized", "removed", "stalled"])
    def test_template_padrao_so_usa_variaveis_declaradas(self, event):
        """O texto padrao nao pode citar variavel que o evento nao fornece."""
        usadas = set(re.findall(r"\{\{\s*(\w+)\s*\}\}",
                                g.DEFAULT_NOTIFICATIONS[event]["template"]))
        declaradas = set(g.NOTIFICATION_VARIABLES[event])
        assert usadas <= declaradas, \
            f"{event} usa variavel nao declarada: {sorted(usadas - declaradas)}"


class TestNotificationBackCompat:
    """O texto padrao reproduz exatamente as mensagens hardcoded ate a v2.0.8."""

    def test_stalled_mantem_a_mensagem_antiga(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(remove_stalled=True, stalled_time=24,
                               stalled_unit="hours")
        cfg["notifications"]["apprise_url"] = "http://apprise:8000/notify"
        g.save_config(cfg)
        torrent = {"hash": "h", "name": "Show", "state": "stalledDL",
                   "added_on": 0, "num_complete": 1}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "remove_torrent"):
            g.check_stalled_and_remove(torrent)

        titulo, corpo = m.call_args[0]
        assert titulo == "🗑️ Torrent Removido (stalled)"
        assert corpo == "Nome: Show\nMotivo: stalled (stalledDL) por >24h"

    def test_removed_mantem_a_mensagem_antiga(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"]["apprise_url"] = "http://apprise:8000/notify"
        g.save_config(cfg)
        torrent = {"hash": "h", "name": "Filme", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "get_files",
                               return_value=[{"name": "a.exe", "index": 0}]), \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "remove_torrent"):
            g.analyze_torrent(torrent)

        titulo, corpo = m.call_args[0]
        assert titulo == "⚠️ Torrent Removido"
        assert corpo == "Nome: Filme\nMotivo: Arquivos perigosos: ['.exe']"

    def test_optimized_mantem_a_mensagem_antiga(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"]["apprise_url"] = "http://apprise:8000/notify"
        g.save_config(cfg)
        torrent = {"hash": "h", "name": "Serie", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "get_files",
                               return_value=[{"name": "ep.mkv", "index": 0}]), \
             mock.patch.object(g, "set_file_priority"):
            g.analyze_torrent(torrent)

        titulo, corpo = m.call_args[0]
        assert titulo == "⚡ Torrent Otimizado"
        assert corpo == "Nome: Serie\nArquivos de midia priorizados."


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


# ── Sonarr/Radarr SSL ─────────────────────────────────────────────────────

class TestArrSession:
    """_handle_arr() usa Session com verify=False (homelab, SSL auto-assinado)."""

    def test_sonarr_session_has_verify_false(self, tmp_config):
        """Sonarr: sessao criada com verify=False."""
        g.load_config()
        cfg = g.get_config()
        cfg["sonarr"]["url"] = "https://sonarr.home.arpa/"
        cfg["sonarr"]["api_key"] = "skey"
        g.save_config(cfg)

        mock_session = mock.MagicMock()
        mock_session.get.return_value.json.return_value = {"records": []}

        with mock.patch("app.guardian.requests.Session", return_value=mock_session) as m_session:
            g._handle_arr("Sonarr", "sonarr", "hash123", "Test.Show")

        m_session.assert_called_once()
        # A sessao deve ter verify=False
        assert mock_session.verify is False

    def test_radarr_session_has_verify_false(self, tmp_config):
        """Radarr: sessao criada com verify=False."""
        g.load_config()
        cfg = g.get_config()
        cfg["radarr"]["url"] = "https://radarr.home.arpa/"
        cfg["radarr"]["api_key"] = "rkey"
        g.save_config(cfg)

        mock_session = mock.MagicMock()
        mock_session.get.return_value.json.return_value = {"records": []}

        with mock.patch("app.guardian.requests.Session", return_value=mock_session) as m_session:
            g._handle_arr("Radarr", "radarr", "hash456", "Test.Movie")

        m_session.assert_called_once()
        assert mock_session.verify is False

    def test_arr_session_headers_set(self, tmp_config):
        """Headers X-Api-Key sao injetados na sessao."""
        g.load_config()
        cfg = g.get_config()
        cfg["sonarr"]["url"] = "https://sonarr.home.arpa/"
        cfg["sonarr"]["api_key"] = "my-secret-key"
        g.save_config(cfg)

        mock_session = mock.MagicMock()
        mock_session.get.return_value.json.return_value = {"records": []}

        with mock.patch("app.guardian.requests.Session", return_value=mock_session):
            g._handle_arr("Sonarr", "sonarr", "hash123", "Test.Show")

        mock_session.headers.update.assert_called_once_with({"X-Api-Key": "my-secret-key"})


# ── Match por nome (_normalize_title / _arr_match_by_name) ──────────────

class TestArrMatchByName:
    """Fallback por nome quando o torrent nao esta na queue do *Arr.

    Dois bugs cobertos aqui:
    1. Item sem titulo casava com QUALQUER torrent (`"" in x` e sempre True),
       disparando re-search na midia errada.
    2. O match cru nunca casava com release name real: o *Arr devolve
       `Breaking Bad` e o torrent chama `Breaking.Bad.S01E01` — comparar sem
       normalizar os separadores deixava o fallback inteiro morto.
    """

    def test_match_release_name_com_separadores(self):
        """Titulo com espacos casa com release name pontuado."""
        items = [{"id": 7, "title": "Breaking Bad"}]
        assert g._arr_match_by_name(
            items, "Breaking.Bad.S01E01.1080p.WEB-DL.x264.mkv") == 7

    def test_match_com_hifen_no_titulo(self):
        """Separadores do titulo tambem sao normalizados."""
        items = [{"id": 5, "title": "Spider-Man"}]
        assert g._arr_match_by_name(items, "Spider.Man.2002.1080p.mkv") == 5

    def test_match_case_insensitive(self):
        items = [{"id": 3, "title": "THE OFFICE"}]
        assert g._arr_match_by_name(items, "the.office.s02e01.mkv") == 3

    def test_item_sem_title_e_ignorado(self):
        """REGRESSAO: item sem a chave title nao pode casar com tudo."""
        items = [{"id": 99}, {"id": 7, "title": "Breaking Bad"}]
        assert g._arr_match_by_name(items, "Breaking.Bad.S01E01.mkv") == 7

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_item_com_title_vazio_e_ignorado(self, empty):
        """REGRESSAO: title nulo/vazio/so-espacos nao pode casar com tudo."""
        items = [{"id": 99, "title": empty}, {"id": 7, "title": "Breaking Bad"}]
        assert g._arr_match_by_name(items, "Breaking.Bad.S01E01.mkv") == 7

    def test_so_item_sem_title_retorna_none(self):
        """REGRESSAO: sem candidato valido, o resultado e None (nao o id 99)."""
        assert g._arr_match_by_name([{"id": 99}], "Breaking.Bad.S01E01.mkv") is None

    def test_torrent_sem_nome_nao_casa_com_item_sem_title(self):
        """Nome vazio dos dois lados nao pode virar match.

        Borda que justifica a guarda explicita de titulo vazio: com o torrent
        sem nome, a forma normalizada dos dois lados e a mesma e o match por
        substring passaria a valer sem essa checagem.
        """
        assert g._arr_match_by_name([{"id": 99}], "") is None
        assert g._arr_match_by_name([{"id": 99, "title": ""}], "") is None

    def test_titulo_curto_nao_casa_no_meio_de_palavra(self):
        """'Her' nao pode casar dentro de 'Where' (match em limite de palavra)."""
        items = [{"id": 5, "title": "Her"}]
        assert g._arr_match_by_name(
            items, "Where.The.Wild.Things.Are.2009.mkv") is None

    def test_sem_match_retorna_none(self):
        items = [{"id": 9, "title": "Dexter"}]
        assert g._arr_match_by_name(items, "Breaking.Bad.S01E01.mkv") is None

    def test_lista_vazia_retorna_none(self):
        assert g._arr_match_by_name([], "Breaking.Bad.S01E01.mkv") is None

    def test_primeiro_match_ganha(self):
        items = [{"id": 1, "title": "Breaking Bad"},
                 {"id": 2, "title": "Breaking Bad"}]
        assert g._arr_match_by_name(items, "Breaking.Bad.S01E01.mkv") == 1

    def test_title_field_customizado(self):
        items = [{"id": 4, "nome": "Breaking Bad"}]
        assert g._arr_match_by_name(
            items, "Breaking.Bad.S01E01.mkv", title_field="nome") == 4
        assert g._arr_match_by_name(items, "Breaking.Bad.S01E01.mkv") is None


# ── _handle_arr: blocklist + re-search ──────────────────────────────────

class _FakeArrSession:
    """Session falsa que roteia GET por sufixo de URL e grava DELETE/POST.

    Um GET para URL nao mapeada e um erro do TESTE, nao do codigo: _handle_arr
    engole qualquer excecao num `except Exception` generico, entao um mock
    permissivo esconderia a falha.
    """

    def __init__(self, get_map):
        self._get_map = get_map
        self.verify = True
        self.headers = mock.MagicMock()
        self.gets = []
        self.deletes = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append(url)
        for suffix, payload in self._get_map.items():
            if url.endswith(suffix):
                if isinstance(payload, Exception):
                    raise payload
                resp = mock.MagicMock()
                resp.json.return_value = payload
                return resp
        raise AssertionError(f"GET nao mapeado no teste: {url}")

    def delete(self, url, **kwargs):
        self.deletes.append((url, kwargs.get("params")))
        return mock.MagicMock()

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs.get("json")))
        return mock.MagicMock()

    @property
    def commands(self):
        """Payloads dos POST /command disparados."""
        return [body for url, body in self.posts if url.endswith("/command")]


@contextlib.contextmanager
def _run_handle_arr(arr_type, config_key, get_map, torrent_hash, torrent_name):
    """Executa _handle_arr com Session falsa e falha se log.error for emitido.

    O `except Exception` generico de _handle_arr transforma qualquer erro em
    um log.error silencioso — sem esta guarda, um teste passaria verde mesmo
    com o fluxo inteiro estourando na primeira linha.
    """
    sess = _FakeArrSession(get_map)
    with mock.patch("app.guardian.requests.Session", return_value=sess), \
         mock.patch.object(g.log, "error") as m_err:
        yield sess
    assert not m_err.called, f"log.error inesperado: {m_err.call_args_list}"


class TestHandleArrRadarr:
    """Radarr: blocklist na queue, fallback por nome e MoviesSearch."""

    @pytest.fixture
    def radarr_cfg(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["radarr"]["url"] = "https://radarr.home.arpa/"
        cfg["radarr"]["api_key"] = "rkey"
        g.save_config(cfg)
        return cfg

    BASE = "https://radarr.home.arpa/api/v3"

    def test_queue_match_faz_blocklist_e_dispara_busca(self, radarr_cfg):
        """Torrent na queue → DELETE com blocklist + MoviesSearch no movieId."""
        get_map = {
            "/queue": {"records": [
                {"id": 11, "downloadId": "OTHERHASH", "movieId": 1},
                {"id": 42, "downloadId": "ABC123", "movieId": 77},
            ]},
        }
        with _run_handle_arr("Radarr", "radarr", get_map,
                             "abc123", "Some.Movie.2020.mkv") as sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")

        # Blocklist no item certo (match de downloadId e case-insensitive)
        assert sess.deletes == [(f"{self.BASE}/queue/42",
                                 {"blocklist": "true", "removeFromClient": "false"})]
        # Re-search no movieId extraido da queue — sem fallback por nome
        assert sess.commands == [{"name": "MoviesSearch", "movieIds": [77]}]
        assert not any(u.endswith("/movie") for u in sess.gets)

    def test_fallback_por_nome_quando_fora_da_queue(self, radarr_cfg):
        """Sem match na queue → busca em /movie e dispara MoviesSearch."""
        get_map = {
            "/queue": {"records": []},
            "/movie": [{"id": 5, "title": "Some Movie"}],
        }
        with _run_handle_arr("Radarr", "radarr", get_map,
                             "abc123", "Some.Movie.2020.1080p.mkv") as sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.1080p.mkv")

        assert sess.deletes == []  # nao estava na queue: nada a bloquear
        assert sess.commands == [{"name": "MoviesSearch", "movieIds": [5]}]

    def test_sem_movie_id_nao_dispara_busca(self, radarr_cfg):
        """Nem queue nem nome casam → nenhum comando e enviado."""
        get_map = {
            "/queue": {"records": []},
            "/movie": [{"id": 5, "title": "Outro Filme"}],
        }
        with _run_handle_arr("Radarr", "radarr", get_map,
                             "abc123", "Some.Movie.2020.mkv") as sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")

        assert sess.posts == []
        assert sess.deletes == []

    def test_blocklist_sem_movie_id_cai_no_fallback(self, radarr_cfg):
        """Queue sem movieId: bloqueia e ainda tenta achar o filme por nome."""
        get_map = {
            "/queue": {"records": [{"id": 42, "downloadId": "ABC123"}]},
            "/movie": [{"id": 5, "title": "Some Movie"}],
        }
        with _run_handle_arr("Radarr", "radarr", get_map,
                             "abc123", "Some.Movie.2020.mkv") as sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")

        assert len(sess.deletes) == 1
        assert sess.commands == [{"name": "MoviesSearch", "movieIds": [5]}]

    @pytest.mark.parametrize("field", ["url", "api_key"])
    def test_secao_incompleta_nao_faz_request(self, radarr_cfg, field):
        """URL ou API key vazia → _handle_arr sai sem tocar na rede."""
        cfg = g.get_config()
        cfg["radarr"][field] = ""
        g.save_config(cfg)

        with mock.patch("app.guardian.requests.Session") as m_sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.mkv")

        assert not m_sess.called


class TestHandleArrSonarr:
    """Sonarr: blocklist, validacao de data de lancamento e re-search."""

    BASE = "https://sonarr.home.arpa/api/v3"
    PAST = "2020-01-01T00:00:00Z"
    FUTURE = "2099-01-01T00:00:00Z"

    @pytest.fixture
    def sonarr_cfg(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["sonarr"]["url"] = "https://sonarr.home.arpa/"
        cfg["sonarr"]["api_key"] = "skey"
        g.save_config(cfg)
        return cfg

    def test_queue_match_com_episode_id_dispara_episode_search(self, sonarr_cfg):
        """episodeId na queue + episodio lancado → EpisodeSearch."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9, "episodeId": 31},
            ]},
            "/episode/31": {"airDateUtc": self.PAST},
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Show.S01E01.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01E01.mkv")

        assert sess.deletes == [(f"{self.BASE}/queue/42",
                                 {"blocklist": "true", "removeFromClient": "false"})]
        assert sess.commands == [{"name": "EpisodeSearch", "episodeIds": [31]}]

    def test_queue_match_com_lista_episodes(self, sonarr_cfg):
        """Queue com lista `episodes` → todos os ids entram na busca."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9,
                 "episodes": [{"id": 31}, {"id": 32}]},
            ]},
            "/episode/31": {"airDateUtc": self.PAST},
            "/episode/32": {"airDateUtc": self.PAST},
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Show.S01.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01.mkv")

        assert sess.commands == [{"name": "EpisodeSearch", "episodeIds": [31, 32]}]

    def test_episodio_nao_lancado_e_excluido_da_busca(self, sonarr_cfg):
        """Episodio com airDate futuro nao entra no EpisodeSearch."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9,
                 "episodes": [{"id": 31}, {"id": 32}]},
            ]},
            "/episode/31": {"airDateUtc": self.PAST},
            "/episode/32": {"airDateUtc": self.FUTURE},
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Show.S01.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01.mkv")

        assert sess.commands == [{"name": "EpisodeSearch", "episodeIds": [31]}]

    def test_todos_nao_lancados_nao_dispara_busca(self, sonarr_cfg):
        """Nenhum episodio lancado → blocklist sim, re-search nao."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9, "episodeId": 31},
            ]},
            "/episode/31": {"airDateUtc": self.FUTURE},
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Show.S01E01.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01E01.mkv")

        assert len(sess.deletes) == 1, "blocklist deve acontecer de todo jeito"
        assert sess.commands == []

    def test_sem_airdate_trata_como_lancado(self, sonarr_cfg):
        """airDateUtc ausente → nao bloqueia a busca (fail-open)."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9, "episodeId": 31},
            ]},
            "/episode/31": {},
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Show.S01E01.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01E01.mkv")

        assert sess.commands == [{"name": "EpisodeSearch", "episodeIds": [31]}]

    def test_erro_ao_consultar_episodio_trata_como_lancado(self, sonarr_cfg):
        """Falha no GET /episode nao impede a busca (fail-open, loga o erro)."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9, "episodeId": 31},
            ]},
            "/episode/31": requests.exceptions.Timeout("timeout"),
        }
        sess = _FakeArrSession(get_map)
        with mock.patch("app.guardian.requests.Session", return_value=sess), \
             mock.patch.object(g.log, "error") as m_err:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01E01.mkv")

        assert sess.commands == [{"name": "EpisodeSearch", "episodeIds": [31]}]
        assert m_err.called, "a falha do episodio deve ser logada"

    def test_fallback_por_nome_dispara_series_search(self, sonarr_cfg):
        """Fora da queue → match em /series e SeriesSearch (sem episodeIds)."""
        get_map = {
            "/queue": {"records": []},
            "/series": [{"id": 9, "title": "Some Show"}],
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Some.Show.S01E01.1080p.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Some.Show.S01E01.1080p.mkv")

        assert sess.deletes == []
        assert sess.commands == [{"name": "SeriesSearch", "seriesId": 9}]

    def test_queue_sem_episodios_dispara_series_search(self, sonarr_cfg):
        """Queue com seriesId mas sem episodio → SeriesSearch."""
        get_map = {
            "/queue": {"records": [
                {"id": 42, "downloadId": "ABC123", "seriesId": 9},
            ]},
        }
        with _run_handle_arr("Sonarr", "sonarr", get_map,
                             "abc123", "Show.S01.mkv") as sess:
            g._handle_arr("Sonarr", "sonarr", "abc123", "Show.S01.mkv")

        assert len(sess.deletes) == 1
        assert sess.commands == [{"name": "SeriesSearch", "seriesId": 9}]


class TestBlockAndSearch:
    """block_and_search() aciona os dois *Arr."""

    def test_chama_radarr_e_sonarr(self, tmp_config):
        with mock.patch.object(g, "_handle_arr") as m:
            g.block_and_search("abc123", "Some.Movie.mkv")

        assert m.call_args_list == [
            mock.call("Radarr", "radarr", "abc123", "Some.Movie.mkv"),
            mock.call("Sonarr", "sonarr", "abc123", "Some.Movie.mkv"),
        ]


# ── Config auto-creation (zero config) ──────────────────────────────────

class TestConfigAutoCreation:
    """Config.json criado automaticamente se nao existir."""

    def test_creates_default_config_when_file_missing(self):
        """load_config() cria config.json default em diretorio vazio."""
        import app.web as w

        old_path = w.CONFIG_PATH
        old_gpath = g.CONFIG_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_config = os.path.join(tmpdir, "config.json")
            w.CONFIG_PATH = tmp_config
            g.CONFIG_PATH = tmp_config
            g._config = None

            # Arquivo nao existe ainda
            assert not os.path.exists(tmp_config)

            cfg = g.load_config()

            # Arquivo foi criado
            assert os.path.exists(tmp_config)

            # Estrutura default
            assert "qbit" in cfg
            assert cfg["qbit"]["url"] == ""
            assert cfg["qbit"]["api_key"] == ""
            assert "sonarr" in cfg
            assert "radarr" in cfg
            assert "guardian" in cfg
            assert cfg["guardian"]["check_interval_seconds"] == 300
            assert cfg["guardian"]["retry_interval_seconds"] == \
                g.DEFAULT_RETRY_INTERVAL
            assert len(cfg["guardian"]["valid_media_extensions"]) > 0
            assert len(cfg["guardian"]["dangerous_extensions"]) > 0
            assert "notifications" in cfg
            assert cfg["notifications"]["apprise_url"] == ""
            assert "webui" in cfg
            assert cfg["webui"]["user"] == ""
            assert cfg["webui"]["password"] == ""

            # Verifica JSON salvo no disco
            with open(tmp_config) as f:
                saved = json.load(f)
            assert saved == cfg

        w.CONFIG_PATH = old_path
        g.CONFIG_PATH = old_gpath
        g._config = None

    def test_config_json_do_repo_bate_com_o_default(self):
        """O config.json versionado e o default de load_config() sao o MESMO contrato.

        Divergiam: `retry_interval_seconds` entrou no default de load_config()
        em v2.0.6 mas nao no config.json do repo. Sem esta guarda, quem le o
        arquivo versionado para saber o que existe nao ve a chave nova.
        """
        import app.web as w

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo_root, "config.json")) as f:
            versionado = json.load(f)

        old_path, old_gpath = w.CONFIG_PATH, g.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                w.CONFIG_PATH = g.CONFIG_PATH = os.path.join(tmpdir, "config.json")
                g._config = None
                gerado = g.load_config()
        finally:
            w.CONFIG_PATH, g.CONFIG_PATH = old_path, old_gpath
            g._config = None

        def chaves(d, prefixo=""):
            out = set()
            for k, v in d.items():
                out.add(prefixo + k)
                if isinstance(v, dict):
                    out |= chaves(v, prefixo + k + ".")
            return out

        so_no_default = chaves(gerado) - chaves(versionado)
        so_no_arquivo = chaves(versionado) - chaves(gerado)
        assert not so_no_default, \
            f"chaves no default de load_config() e nao no config.json: {sorted(so_no_default)}"
        assert not so_no_arquivo, \
            f"chaves no config.json e nao no default de load_config(): {sorted(so_no_arquivo)}"

    def test_load_config_existing_file_still_works(self):
        """load_config() continua lendo arquivo existente normalmente."""
        import app.web as w

        old_path = w.CONFIG_PATH
        old_gpath = g.CONFIG_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_config = os.path.join(tmpdir, "config.json")
            w.CONFIG_PATH = tmp_config
            g.CONFIG_PATH = tmp_config
            g._config = None

            custom = {
                "qbit": {"url": "http://x:8080", "api_key": "mykey"},
                "sonarr": {"url": "", "api_key": ""},
                "radarr": {"url": "", "api_key": ""},
                "guardian": {"check_interval_seconds": 60},
                "notifications": {"apprise_url": ""},
                "webui": {"user": "", "password": ""}
            }
            with open(tmp_config, "w") as f:
                json.dump(custom, f)

            cfg = g.load_config()
            assert cfg["qbit"]["url"] == "http://x:8080"
            assert cfg["qbit"]["api_key"] == "mykey"
            assert cfg["guardian"]["check_interval_seconds"] == 60

        w.CONFIG_PATH = old_path
        g.CONFIG_PATH = old_gpath
        g._config = None

    def test_config_created_in_nested_directory(self):
        """load_config() cria diretorios pais se necessario."""
        import app.web as w

        old_path = w.CONFIG_PATH
        old_gpath = g.CONFIG_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "a", "b", "config.json")
            w.CONFIG_PATH = nested
            g.CONFIG_PATH = nested
            g._config = None

            assert not os.path.exists(os.path.dirname(nested))
            cfg = g.load_config()
            assert os.path.exists(nested)
            assert "qbit" in cfg

        w.CONFIG_PATH = old_path
        g.CONFIG_PATH = old_gpath
        g._config = None

    def test_config_dir_exists_but_file_missing(self):
        """Regressao: diretorio existe (bind mount) mas config.json nao.

        Simula o cenario Docker onde ./config:/app/config monta o diretorio
        vazio do host — o diretorio /app/config/ existe (bind mount),
        mas /app/config/config.json ainda nao foi criado.
        load_config() deve criar o arquivo dentro do diretorio existente.
        """
        import app.web as w

        old_path = w.CONFIG_PATH
        old_gpath = g.CONFIG_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            # Cria o diretorio (simula bind mount que ja existe)
            config_dir = os.path.join(tmpdir, "config")
            os.makedirs(config_dir)
            assert os.path.isdir(config_dir)

            config_file = os.path.join(config_dir, "config.json")
            w.CONFIG_PATH = config_file
            g.CONFIG_PATH = config_file
            g._config = None

            # Arquivo NAO existe ainda (primeiro run)
            assert not os.path.exists(config_file)

            # load_config deve criar o config.json dentro do dir existente
            cfg = g.load_config()

            # Arquivo foi criado DENTRO do diretorio existente
            assert os.path.exists(config_file)
            assert os.path.dirname(config_file) == config_dir

            # Estrutura default completa
            assert cfg["qbit"]["url"] == ""
            assert cfg["sonarr"]["url"] == ""
            assert cfg["radarr"]["url"] == ""
            assert cfg["guardian"]["check_interval_seconds"] == 300
            assert cfg["notifications"]["apprise_url"] == ""
            assert cfg["webui"]["user"] == ""

            # Verifica que os.makedirs nao quebrou o diretorio existente
            assert os.path.isdir(config_dir)
            assert len(os.listdir(config_dir)) == 1  # so config.json

        w.CONFIG_PATH = old_path
        g.CONFIG_PATH = old_gpath
        g._config = None


# ── Contrato da Web UI (static/) ────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "static")


def _read_static(name):
    """Le um arquivo de static/ com os escapes \\uXXXX ja resolvidos.

    O i18n.js escreve acentos e pontuacao como escape JS (`(0\\u20137)`), o
    index.html usa o caractere direto. Normalizar na leitura faz a asserção
    valer para os dois sem depender de qual forma o arquivo usa.
    """
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as f:
        raw = f.read()
    return re.sub(r"\\u([0-9a-fA-F]{4})",
                  lambda m: chr(int(m.group(1), 16)), raw)


def _i18n_tables():
    """Extrai as tabelas pt-BR / en-US do static/i18n.js.

    Parse por regex em vez de execucao de JS: so precisamos das CHAVES, e
    manter o teste sem dependencia (node/JS engine) e deliberado.
    """
    src = _read_static("i18n.js")
    tables = {}
    for lang in ("pt-BR", "en-US"):
        m = re.search(r"'" + lang + r"':\s*\{(.*?)\n    \}", src, re.S)
        assert m, f"tabela {lang} nao encontrada em i18n.js"
        tables[lang] = set(re.findall(r"^\s{8}(\w+):", m.group(1), re.M))
    return tables


class TestWebUIPriorityScale:
    """A Web UI nao pode oferecer prioridades que o qBittorrent rejeita.

    A escala do filePrio nao e continua: so -1, 0, 1, 6 e 7 sao aceitos. A UI
    trazia `<input type="number" min="0" max="7">`, que deixava digitar 2, 3,
    4 e 5 — o guardian recusava depois, com um WARNING no log, e a priorizacao
    silenciosamente nao acontecia. Ver TestSetFilePriority para o lado do motor.
    """

    PRIORITY_IDS = ["priority_media", "priority_normal", "priority_skip"]

    @pytest.mark.parametrize("field_id", PRIORITY_IDS)
    def test_select_so_oferece_valores_validos(self, field_id):
        """Cada campo de prioridade e um select com exatamente 0, 1, 6 e 7."""
        html = _read_static("index.html")
        m = re.search(r'<select id="' + field_id + r'">(.*?)</select>', html, re.S)
        assert m, f"{field_id} deveria ser um <select>"

        values = [int(v) for v in re.findall(r'value="(-?\d+)"', m.group(1))]
        assert values == [0, 1, 6, 7], f"{field_id} oferece {values}"
        assert set(values) <= g.VALID_FILE_PRIORITIES, \
            f"{field_id} oferece valor recusado pelo filePrio: {values}"

    @pytest.mark.parametrize("field_id", PRIORITY_IDS)
    def test_nao_e_input_numerico(self, field_id):
        """REGRESSAO: input numerico 0-7 aceitava 2, 3, 4 e 5."""
        html = _read_static("index.html")
        assert not re.search(r'<input[^>]*id="' + field_id + r'"', html), \
            f"{field_id} voltou a ser <input> — a escala nao e continua"

    @pytest.mark.parametrize("field_id", PRIORITY_IDS)
    def test_select_tem_exatamente_um_default(self, field_id):
        """Um e so um `selected`, senao o campo abre em branco ou ambiguo."""
        html = _read_static("index.html")
        m = re.search(r'<select id="' + field_id + r'">(.*?)</select>', html, re.S)
        assert m.group(1).count("selected") == 1

    def test_defaults_da_ui_batem_com_o_config(self):
        """O `selected` de cada select e o default da chave no config.json."""
        html = _read_static("index.html")
        with open(os.path.join(os.path.dirname(STATIC_DIR), "config.json")) as f:
            guardian_cfg = json.load(f)["guardian"]

        for field_id in self.PRIORITY_IDS:
            m = re.search(r'<select id="' + field_id + r'">(.*?)</select>', html, re.S)
            selected = re.search(r'value="(-?\d+)" selected', m.group(1))
            assert selected, f"{field_id} sem opcao selected"
            assert int(selected.group(1)) == guardian_cfg[field_id], \
                f"{field_id}: UI default {selected.group(1)} != config"

    @pytest.mark.parametrize("fonte", ["index.html", "i18n.js"])
    def test_nenhum_texto_anuncia_escala_continua(self, fonte):
        """REGRESSAO: o rotulo dizia "(0–7)", sugerindo que 2-5 valem."""
        texto = _read_static(fonte)
        for proibido in ("(0\u20137)", "(0-7)", "0 a 7",
                         "7 = m\u00e1xima, 0", "7 = maximum, 0"):
            assert proibido not in texto, \
                f"{fonte} ainda anuncia a escala antiga: {proibido!r}"


class TestWebUILayout:
    """Grade de 3 colunas do prototipo Penpot.

    O codigo ficou em 2 colunas (`.two-col`) por meses depois de o prototipo
    migrar para 3 — ver conceitos/design-system-webui no vault, decisao 5.
    Estes testes travam a estrutura para a divergencia nao voltar em silencio.
    """

    def test_grade_tem_tres_colunas(self):
        html = _read_static("index.html")
        m = re.search(r'<div class="grid">(.*?)\n  </div>', html, re.S)
        assert m, "container .grid nao encontrado"
        assert m.group(1).count('<div class="col">') == 3

    def test_layout_de_duas_colunas_nao_voltou(self):
        """REGRESSAO: `.two-col` era o layout antigo."""
        html = _read_static("index.html")
        assert "two-col" not in html

    def test_ordem_das_secoes_segue_o_prototipo(self):
        """Col 1: qBittorrent → Radarr → Sonarr. Col 2: Guardian. Col 3: Notificacoes."""
        html = _read_static("index.html")
        colunas = re.findall(r'<div class="col">(.*?)\n    </div>', html, re.S)
        assert len(colunas) == 3
        secoes = [re.findall(r'<h2 data-i18n="(\w+)"', c) for c in colunas]
        assert secoes == [
            ["section_qbit", "section_radarr", "section_sonarr"],
            ["section_guardian"],
            ["section_notifications"],
        ], secoes

    @pytest.mark.parametrize("token,valor", [
        ("--col", "365px"),
        ("--gutter", "28px"),
        ("--r-card", "15px"),
        ("--r-pill", "13px"),
        ("--r-stepper", "16px"),
        ("--bg", "#1a1a2e"),
        ("--card", "#16213e"),
    ])
    def test_tokens_do_design_system(self, token, valor):
        """Valores medidos no prototipo, declarados como token em :root."""
        html = _read_static("index.html")
        m = re.search(r":root\s*\{(.*?)\}", html, re.S)
        assert m, ":root nao encontrado"
        assert re.search(re.escape(token) + r":\s*" + re.escape(valor) + r"\s*;", m.group(1)), \
            f"{token} deveria ser {valor}"

    def test_largura_do_container_deriva_dos_tokens(self):
        """A largura maxima e 3 colunas + 2 gutters, nao um numero solto."""
        html = _read_static("index.html")
        assert re.search(r"\.container\s*\{[^}]*max-width:\s*calc\(var\(--col\)\s*\*\s*3", html)

    def test_todo_campo_tem_label_associado(self):
        """REGRESSAO: 13 campos ficaram sem `for`, sem leitor de tela conseguir ler."""
        html = _read_static("index.html")
        sem_for = [l for l in html.split("\n")
                   if l.strip().startswith("<label ") and "for=" not in l]
        assert not sem_for, f"labels sem for: {sem_for}"

    def test_todo_checkbox_e_switch(self):
        """O switch do prototipo e o unico padrao de liga/desliga da UI."""
        html = _read_static("index.html")
        checkboxes = re.findall(r'<input[^>]*type="checkbox"[^>]*>', html)
        assert checkboxes, "nenhum checkbox encontrado — seletor desatualizado?"
        for c in checkboxes:
            assert 'class="switch"' in c, f"checkbox sem a classe switch: {c}"


class TestWebUIEspacamento:
    """Aproveitamento do espaco: nada cortado, nada de vazio acumulado.

    Reportado em producao numa captura de tela: a unidade de tempo aparecia
    cortada ("minutos" sem o final), cada card da coluna 1 tinha ~60 px de
    vazio no rodape, e o toggle das linhas de remocao ficava solto no meio da
    largura, deixando um buraco ate a borda do card.
    """

    def _regra(self, seletor):
        """Corpo da regra cujo seletor abre a linha.

        Ancorado em inicio de linha para nao casar com uma regra agrupada que
        termine no mesmo seletor (`.inline input, .inline select { ... }`).
        """
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", html)
        assert m, f"regra CSS nao encontrada: {seletor}"
        return m.group(1).replace(" ", "")

    def test_unidade_de_tempo_tem_largura_automatica(self):
        """REGRESSAO: width fixo de 84px cortava "segundos" (precisa de 97)."""
        regra = self._regra(".inline select")
        assert "width:auto" in regra, regra
        m = re.search(r"min-width:(\d+)px", regra)
        assert m, f"falta min-width em .inline select: {regra}"
        assert int(m.group(1)) >= 100, \
            f"min-width {m.group(1)}px e curto para a maior unidade"

    def test_unidade_nao_tem_largura_fixa(self):
        """Largura fixa volta a cortar o texto assim que a traducao crescer."""
        regra = self._regra(".inline select")
        assert not re.search(r"(?<!min-)width:\d+px", regra), regra

    def test_coluna_1_distribui_a_sobra(self):
        """REGRESSAO: a sobra se acumulava no rodape de cada card da coluna 1.

        Os tres cards sao pequenos e esticam ate a altura da coluna Guardian.
        Sem distribuir, sobravam ~60 px de vazio em cada rodape.
        """
        html = _read_static("index.html")
        m = re.search(r"\.col:first-child > \.card\s*\{([^}]*)\}", html)
        assert m, "falta a regra que distribui a sobra na coluna 1"
        assert "space-evenly" in m.group(1) or "space-between" in m.group(1), m.group(1)

    def test_caixa_de_mensagem_absorve_a_sobra(self):
        """Espaco sobrando na coluna 3 vira area de edicao, nao vazio."""
        assert "flex:1" in self._regra(".msg textarea")

    @pytest.mark.parametrize("lid", ["remove_stalled", "remove_no_seeds"])
    def test_toggle_de_remocao_fica_na_linha_do_rotulo(self, lid):
        """REGRESSAO: o toggle vinha depois da unidade e sobrava espaco a direita.

        Mesma anatomia dos blocos de mensagem — rotulo a esquerda, liga/desliga
        encostado na borda direita, controles na linha de baixo.
        """
        html = _read_static("index.html")
        bloco = re.search(
            r'<div class="toggle-block">\s*<div class="head">(.*?)</div>(.*?)</div>\s*</div>',
            html, re.S)
        assert bloco, "bloco de remocao nao segue a estrutura head + inline"

        m = re.search(r'<div class="toggle-block">(.*?)\n        </div>', html, re.S)
        blocos = re.findall(r'<div class="toggle-block">(.*?)\n        </div>', html, re.S)
        alvo = next((b for b in blocos if f'id="{lid}"' in b), None)
        assert alvo, f"bloco de {lid} nao encontrado"

        cabeca = re.search(r'<div class="head">(.*?)</div>', alvo, re.S).group(1)
        assert f'id="{lid}"' in cabeca, "o toggle deve ficar no cabecalho, com o rotulo"
        assert f'for="{lid}"' in cabeca
        # os controles ficam depois do cabecalho
        assert alvo.index('class="inline"') > alvo.index(f'id="{lid}"')

    def test_layout_antigo_de_linha_unica_nao_voltou(self):
        html = _read_static("index.html")
        assert "toggle-row" not in html


class TestWebUIDocsLink:
    """Icone de documentacao do prototipo: tooltip em hover + link por idioma."""

    def _docs_urls(self):
        js = _read_static("i18n.js")
        urls = {}
        for lang in ("pt-BR", "en-US"):
            m = re.search(r"'" + lang + r"':\s*\{(.*?)\n    \}", js, re.S)
            u = re.search(r"docs_url:\s*'([^']+)'", m.group(1))
            assert u, f"docs_url ausente em {lang}"
            urls[lang] = u.group(1)
        return urls

    def test_link_existe_e_abre_em_nova_aba_com_seguranca(self):
        html = _read_static("index.html")
        m = re.search(r'<a class="docs"[^>]*>', html)
        assert m, "link de documentacao nao encontrado"
        tag = m.group(0)
        assert 'target="_blank"' in tag
        # noopener evita que a pagina aberta acesse window.opener
        assert "noopener" in tag, tag
        assert 'data-i18n-href="docs_url"' in tag, tag

    def test_tooltip_so_aparece_no_hover(self):
        html = _read_static("index.html")
        assert 'class="docs-tip"' in html
        m = re.search(r"\.docs-tip\s*\{(.*?)\}", html, re.S)
        assert m and "visibility:hidden" in m.group(1).replace(" ", ""), \
            "o tooltip deve comecar escondido"
        assert re.search(r"\.docs:hover \.docs-tip", html), \
            "falta a regra de hover que revela o tooltip"

    def test_url_aponta_para_a_pasta_de_docs_do_idioma(self):
        urls = self._docs_urls()
        assert urls["pt-BR"].endswith("/docs/pt-BR")
        assert urls["en-US"].endswith("/docs/en-US")
        assert urls["pt-BR"] != urls["en-US"]

    @pytest.mark.parametrize("lang", ["pt-BR", "en-US"])
    def test_pasta_de_docs_existe_no_repo(self, lang):
        """O link nao pode apontar para uma pasta que nao existe."""
        urls = self._docs_urls()
        pasta = urls[lang].rsplit("/tree/main/", 1)[1]
        caminho = os.path.join(REPO_ROOT, pasta)
        assert os.path.isdir(caminho), f"{caminho} nao existe"
        assert [f for f in os.listdir(caminho) if f.endswith(".md")], \
            f"{caminho} nao tem documentacao"


class TestApiDefaults:
    """/api/defaults alimenta a Web UI com os padroes do backend."""

    def test_retorna_eventos_e_variaveis(self, client, tmp_config):
        r = client.get("/api/defaults")
        assert r.status_code == 200
        dados = r.get_json()
        assert dados["notifications"] == g.DEFAULT_NOTIFICATIONS
        assert dados["notification_variables"] == g.NOTIFICATION_VARIABLES

    def test_exige_autenticacao(self, client, tmp_config):
        cfg = g.load_config()
        cfg["webui"] = {"user": "admin", "password": "secreta"}
        g.save_config(cfg)
        assert client.get("/api/defaults").status_code == 401

        auth = base64.b64encode(b"admin:secreta").decode()
        r = client.get("/api/defaults", headers={"Authorization": f"Basic {auth}"})
        assert r.status_code == 200


class TestWebUINotifications:
    """Card de Notificacoes: toggle geral + um por mensagem, com template."""

    EVENTOS = ["optimized", "removed", "stalled"]

    def test_toggle_geral_no_cabecalho_do_card(self):
        html = _read_static("index.html")
        assert re.search(
            r'<h2 data-i18n="section_notifications".*?'
            r'<input type="checkbox" class="switch" id="notifications_enabled">',
            html, re.S)

    @pytest.mark.parametrize("ev", EVENTOS)
    def test_cada_evento_tem_toggle_caixa_e_variaveis(self, ev):
        html = _read_static("index.html")
        bloco = re.search(r'<div class="msg" id="msg_' + ev + r'_wrap">(.*?)</div>\n\n',
                          html, re.S)
        assert bloco, f"bloco de {ev} nao encontrado"
        corpo = bloco.group(1)
        assert f'id="msg_{ev}_enabled"' in corpo and 'class="switch"' in corpo
        assert f'<textarea id="msg_{ev}"' in corpo
        assert f'id="vars_{ev}"' in corpo

    def test_eventos_do_html_batem_com_os_do_backend(self):
        """A UI nao pode oferecer evento que o guardian nao conhece."""
        html = _read_static("index.html")
        do_html = set(re.findall(r'<textarea id="msg_(\w+)"', html))
        assert do_html == set(g.DEFAULT_NOTIFICATIONS), \
            f"html: {sorted(do_html)} vs backend: {sorted(g.DEFAULT_NOTIFICATIONS)}"

    def test_lista_de_eventos_do_js_bate_com_o_backend(self):
        html = _read_static("index.html")
        m = re.search(r"const MSG_EVENTS = \[(.*?)\];", html)
        assert m, "MSG_EVENTS nao encontrado"
        do_js = set(re.findall(r"'(\w+)'", m.group(1)))
        assert do_js == set(g.DEFAULT_NOTIFICATIONS)

    def test_ui_nao_carrega_copia_dos_templates(self):
        """Os textos padrao vem de /api/defaults, nao duplicados no HTML.

        Duplicar deixaria a tela mostrando um texto e o guardian enviando
        outro assim que um dos dois mudasse.
        """
        html = _read_static("index.html")
        for ev, spec in g.DEFAULT_NOTIFICATIONS.items():
            primeira_linha = spec["template"].split("\n")[0]
            assert primeira_linha not in html, \
                f"template de {ev} duplicado no HTML: {primeira_linha!r}"
        assert "/api/defaults" in html

    def test_payload_nao_envia_title(self):
        """`title` fica so no config.json: o deep_merge preserva o que esta la."""
        html = _read_static("index.html")
        m = re.search(r"events: Object\.fromEntries\((.*?)\)\n", html, re.S)
        assert m, "payload de events nao encontrado"
        assert "title" not in m.group(1), "title nao deve ir no payload da UI"
        assert "enabled" in m.group(1) and "template" in m.group(1)

    def test_caixa_desabilita_com_o_toggle(self):
        """Mensagem desligada aparece, mas nao pode ser editada."""
        html = _read_static("index.html")
        m = re.search(r"function syncNotifications\(\) \{(.*?)\n\}", html, re.S)
        assert m, "syncNotifications nao encontrado"
        corpo = m.group(1)
        # a caixa desabilita pelo toggle do tipo E pelo geral
        assert re.search(r"caixa\.disabled\s*=\s*!geral\s*\|\|\s*!\w+\.checked", corpo), corpo
        # o toggle do tipo desabilita com o geral desligado
        assert re.search(r"\w+\.disabled\s*=\s*!geral", corpo), corpo

    def test_toggles_estao_ligados_ao_sync(self):
        html = _read_static("index.html")
        assert re.search(r"getElementById\('notifications_enabled'\)\s*\n?\s*"
                         r"\.addEventListener\('change', syncNotifications\)", html)
        assert re.search(r"'msg_' \+ ev \+ '_enabled'\)\s*\n?\s*"
                         r"\.addEventListener\('change', syncNotifications\)", html)

    def test_caixa_desabilitada_continua_legivel(self):
        """Nao basta desabilitar: o texto tem que continuar visivel."""
        html = _read_static("index.html")
        m = re.search(r"\.msg textarea:disabled \{([^}]*)\}", html)
        assert m, "falta o estilo da caixa desabilitada"
        regra = m.group(1)
        assert "color:" in regra and "background:" in regra
        assert "display:none" not in regra and "visibility:hidden" not in regra


class TestWebUIi18n:
    """Toda chave usada no HTML existe nos DOIS idiomas."""

    def test_tabelas_tem_as_mesmas_chaves(self):
        """pt-BR e en-US nao podem divergir — chave faltante vira texto cru."""
        tables = _i18n_tables()
        assert tables["pt-BR"] == tables["en-US"], (
            f"so em pt-BR: {sorted(tables['pt-BR'] - tables['en-US'])}; "
            f"so em en-US: {sorted(tables['en-US'] - tables['pt-BR'])}")

    @pytest.mark.parametrize("attr", ["data-i18n", "data-i18n-placeholder",
                                      "data-i18n-option"])
    def test_chaves_do_html_existem_nas_tabelas(self, attr):
        html = _read_static("index.html")
        keys = set(re.findall(attr + r'="(\w+)"', html))
        assert keys, f"nenhuma chave {attr} encontrada — seletor desatualizado?"

        tables = _i18n_tables()
        for lang, known in tables.items():
            faltando = keys - known
            assert not faltando, f"{attr} sem traducao em {lang}: {sorted(faltando)}"

    def test_escala_de_prioridade_traduzida_nos_dois_idiomas(self):
        """As 4 opcoes de prioridade tem chave propria em cada idioma."""
        tables = _i18n_tables()
        esperadas = {"prio_skip", "prio_normal", "prio_high", "prio_max"}
        for lang, known in tables.items():
            assert esperadas <= known, \
                f"{lang} sem as chaves de prioridade: {sorted(esperadas - known)}"


# ── Paridade doc x codigo ───────────────────────────────────────────────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _flat_keys(d, prefixo=""):
    """Caminhos de chave de um dict aninhado ("qbit.url", "guardian.priority_media")."""
    out = set()
    for k, v in d.items():
        out.add(prefixo + k)
        if isinstance(v, dict):
            out |= _flat_keys(v, prefixo + k + ".")
    return out


class TestDocsConfigParity:
    """O exemplo de config dos READMEs tem que ser o config de verdade.

    Os dois READMEs documentavam `qbit.host` + `qbit.port` enquanto o codigo le
    `qbit.url` (unificado em v2.0.x). Quem seguisse o README montava um
    config.json que estourava KeyError em get_qbit_session() — load_config()
    nao faz merge com os defaults quando o arquivo existe.
    """

    READMES = ["README.md", "README.pt-BR.md"]

    def _exemplo_do_readme(self, nome):
        with open(os.path.join(REPO_ROOT, nome), encoding="utf-8") as f:
            texto = f.read()
        blocos = re.findall(r"```json\n(.*?)```", texto, re.S)
        assert blocos, f"{nome}: nenhum bloco ```json encontrado"
        # O primeiro bloco json de cada README e a estrutura completa do config
        return json.loads(blocos[0])

    @pytest.mark.parametrize("nome", READMES)
    def test_exemplo_do_readme_e_json_valido(self, nome):
        assert isinstance(self._exemplo_do_readme(nome), dict)

    @pytest.mark.parametrize("nome", READMES)
    def test_exemplo_do_readme_bate_com_config_json(self, nome):
        """Mesmas chaves do config.json versionado — nem a mais, nem a menos."""
        with open(os.path.join(REPO_ROOT, "config.json")) as f:
            real = json.load(f)

        doc = self._exemplo_do_readme(nome)
        so_no_doc = _flat_keys(doc) - _flat_keys(real)
        so_no_real = _flat_keys(real) - _flat_keys(doc)

        assert not so_no_doc, f"{nome} documenta chave inexistente: {sorted(so_no_doc)}"
        assert not so_no_real, f"{nome} nao documenta: {sorted(so_no_real)}"

    @pytest.mark.parametrize("nome", READMES)
    def test_readme_documenta_todas_as_variaveis(self, nome):
        """Toda variavel que um evento fornece aparece no README.

        A Web UI mostra os nomes mas nao o que cada um significa; o README e
        onde isso esta. Variavel nova sem documentacao fica invisivel.
        """
        with open(os.path.join(REPO_ROOT, nome), encoding="utf-8") as f:
            texto = f.read()
        for ev, variaveis in g.NOTIFICATION_VARIABLES.items():
            assert f"`{ev}`" in texto, f"{nome} nao documenta o evento {ev}"
            for v in variaveis:
                assert "{{" + v + "}}" in texto, \
                    f"{nome} nao documenta a variavel {{{{{v}}}}} ({ev})"

    @pytest.mark.parametrize("nome", READMES)
    def test_readme_nao_documenta_variavel_inexistente(self, nome):
        """O caminho inverso: nada de prometer variavel que o codigo nao passa."""
        with open(os.path.join(REPO_ROOT, nome), encoding="utf-8") as f:
            texto = f.read()
        reais = {v for vs in g.NOTIFICATION_VARIABLES.values() for v in vs}
        citadas = set(re.findall(r"\{\{(\w+)\}\}", texto))
        assert citadas <= reais, \
            f"{nome} documenta variavel inexistente: {sorted(citadas - reais)}"

    @pytest.mark.parametrize("nome", READMES)
    def test_exemplo_do_readme_e_aceito_por_load_config(self, nome):
        """O exemplo, salvo como config.json, faz o guardian funcionar.

        Checagem de ponta a ponta: carrega o exemplo e exercita os acessos que
        o codigo faz de verdade (cfg["qbit"]["url"] etc.).
        """
        import app.web as w

        doc = self._exemplo_do_readme(nome)
        old_path, old_gpath = w.CONFIG_PATH, g.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                caminho = os.path.join(tmpdir, "config.json")
                with open(caminho, "w") as f:
                    json.dump(doc, f)
                w.CONFIG_PATH = g.CONFIG_PATH = caminho
                g._config = None
                cfg = g.load_config()

                # Acessos reais do codigo — KeyError aqui = README quebrado
                assert cfg["qbit"]["url"] is not None
                assert cfg["qbit"]["api_key"] is not None
                for arr in ("sonarr", "radarr"):
                    assert cfg[arr]["url"] is not None
                    assert cfg[arr]["api_key"] is not None
                assert g._retry_interval(cfg) > 0
                assert cfg["guardian"]["check_interval_seconds"] is not None
                assert cfg["notifications"]["apprise_url"] is not None
        finally:
            w.CONFIG_PATH, g.CONFIG_PATH = old_path, old_gpath
            g._config = None


# ── Heartbeat ───────────────────────────────────────────────────────────

class TestHeartbeat:
    """write_heartbeat() para healthcheck Docker."""

    def test_write_heartbeat_creates_file(self):
        """Funcao cria /tmp/heartbeat com timestamp."""
        import os
        import app.guardian as g

        # Remove se existir de teste anterior
        try:
            os.unlink("/tmp/heartbeat")
        except FileNotFoundError:
            pass

        g.write_heartbeat()

        assert os.path.exists("/tmp/heartbeat")
        with open("/tmp/heartbeat") as f:
            content = f.read().strip()
        assert content  # nao vazio
        # Deve ser um timestamp (float)
        float(content)

    def test_write_heartbeat_silent_on_permission_error(self):
        """Erro de permissao nao propaga excecao."""
        import app.guardian as g
        from unittest import mock

        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            # Nao deve lancar excecao
            g.write_heartbeat()

    def test_trigger_endpoint_writes_heartbeat(self, client, tmp_config):
        """/api/trigger atualiza o heartbeat (modo webhook)."""
        import os
        import app.guardian as g
        from unittest import mock

        g.load_config()
        g._processed.clear()

        mock_torrents = [{"hash": "h1", "name": "test1", "state": "downloading",
                          "added_on": __import__("time").time(), "num_complete": 50}]

        # Remove heartbeat se existir
        try:
            os.unlink("/tmp/heartbeat")
        except FileNotFoundError:
            pass

        with mock.patch.object(g, "get_torrents", return_value=mock_torrents), \
             mock.patch.object(g, "analyze_torrent"):
            r = client.post("/api/trigger")
            assert r.status_code == 200

        # Heartbeat deve existir apos trigger
        assert os.path.exists("/tmp/heartbeat"), \
            "api_trigger deve escrever heartbeat (modo webhook)"
        with open("/tmp/heartbeat") as f:
            assert f.read().strip()

    def test_guardian_loop_writes_heartbeat(self, tmp_config):
        """guardian_loop escreve heartbeat durante iteracao."""
        import os
        import app.guardian as g
        from unittest import mock

        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["check_interval_seconds"] = 1
        g.save_config(cfg)

        # Remove heartbeat
        try:
            os.unlink("/tmp/heartbeat")
        except FileNotFoundError:
            pass

        heartbeat_calls = []

        def fake_write_heartbeat():
            heartbeat_calls.append(1)

        # Captura referencia original ANTES do mock
        orig_get_config = g.get_config

        # Mock get_config para alternar para webhook mode na 2a chamada
        call_count = [0]

        def mock_get_config():
            call_count[0] += 1
            cfg_copy = orig_get_config().copy()
            if call_count[0] >= 2:
                cfg_copy["guardian"] = dict(cfg_copy["guardian"])
                cfg_copy["guardian"]["check_interval_seconds"] = 0
            return cfg_copy

        with mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "get_torrents", return_value=[]), \
             mock.patch.object(g, "write_heartbeat", side_effect=fake_write_heartbeat), \
             mock.patch.object(g, "get_config", side_effect=mock_get_config):

            g.guardian_loop()

            # Deve ter chamado write_heartbeat ao menos 1x
            assert len(heartbeat_calls) >= 1, \
                f"guardian_loop deve chamar write_heartbeat, chamadas: {len(heartbeat_calls)}"


# ── Healthcheck ─────────────────────────────────────────────────────────

class TestHealthcheck:
    """app/healthcheck.py — detecta loop travado via idade do heartbeat.

    O healthcheck antigo (`cat /tmp/heartbeat`) so verificava a EXISTENCIA do
    arquivo, entao um loop morto continuava reportando "healthy" para sempre.
    """

    def _config(self, path, interval, retry=None):
        guardian = {"check_interval_seconds": interval}
        if retry is not None:
            guardian["retry_interval_seconds"] = retry
        with open(path, "w") as f:
            json.dump({"guardian": guardian}, f)

    def _heartbeat(self, path, age_seconds):
        with open(path, "w") as f:
            f.write(str(time.time() - age_seconds))

    def test_ok_quando_heartbeat_recente(self, tmp_path):
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 180)
        self._heartbeat(hb, 30)

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok, msg

    def test_falha_quando_heartbeat_atrasado(self, tmp_path):
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 180)
        self._heartbeat(hb, 2000)  # muito acima da tolerancia (600s)

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert not ok
        assert "atrasado" in msg

    def test_tolerancia_acompanha_intervalo_longo(self, tmp_path):
        """Intervalo de 1h nao pode gerar falso positivo aos 20 min."""
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 3600)
        self._heartbeat(hb, 1200)  # 20 min < 3*3600

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok, msg

    def test_modo_webhook_sempre_ok(self, tmp_path):
        """Intervalo 0 (webhook) nao tem loop periodico — healthcheck passa."""
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 0)

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok
        assert "webhook" in msg

    def test_falha_quando_heartbeat_ausente(self, tmp_path):
        from app import healthcheck

        cfg = tmp_path / "config.json"
        self._config(cfg, 180)

        ok, msg = healthcheck.check(heartbeat_path=str(tmp_path / "inexistente"),
                                    config_path=str(cfg))
        assert not ok
        assert "ausente" in msg

    # ── Interacao com o retry de conexao ────────────────────────────────

    def test_tolerancia_acompanha_retry_longo(self, tmp_path):
        """Retry maior que a tolerancia base nao pode marcar unhealthy.

        Enquanto o qBit esta fora, o heartbeat sai a cada retry_interval — nao
        a cada check_interval. Com retry de 1h e tolerancia presa em
        max(600, 3*300)=900s, o container seria marcado unhealthy justamente no
        cenario que o retry existe para sobreviver, e `restart: always` nao
        reinicia container unhealthy: o guardian ficaria morto.
        """
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 300, retry=3600)
        self._heartbeat(hb, 2000)  # > max(600, 3*300), < 3*3600

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok, msg

    def test_retry_longo_nao_torna_tolerancia_infinita(self, tmp_path):
        """A tolerancia cresce com o retry, mas continua finita (3x)."""
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 300, retry=600)
        self._heartbeat(hb, 5000)  # acima de 3*600 e de 3*300

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert not ok
        assert "retry" in msg, f"a mensagem deve citar o retry: {msg}"

    def test_retry_ausente_usa_default(self, tmp_path):
        """Config sem a chave: tolerancia e a base de 600s (3*120 < 600)."""
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 300)  # sem retry_interval_seconds
        self._heartbeat(hb, 500)

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok, msg
        assert "tolerancia 900s" in msg, msg

    @pytest.mark.parametrize("bad", [None, 0, -5, "abc", ""])
    def test_retry_invalido_cai_no_default(self, tmp_path, bad):
        """Retry invalido nao pode zerar nem explodir o calculo.

        Com o default de 120s, 3*120 fica abaixo do piso de 600s: a tolerancia
        resultante e a mesma do check_interval (3*300=900).
        """
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, 300, retry=bad)
        self._heartbeat(hb, 500)

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok, msg
        assert "tolerancia 900s" in msg, msg

    @pytest.mark.parametrize("bad", ["abc", None, -1])
    def test_check_interval_invalido_cai_no_default(self, tmp_path, bad):
        """REGRESSAO: `intervalo * 3` com valor nao numerico estourava.

        A tolerancia precisa cair em 3*DEFAULT_INTERVAL (900s) em vez de
        propagar o valor cru para a multiplicacao.
        """
        from app import healthcheck

        cfg, hb = tmp_path / "config.json", tmp_path / "heartbeat"
        self._config(cfg, bad)
        self._heartbeat(hb, 100)

        ok, msg = healthcheck.check(heartbeat_path=str(hb), config_path=str(cfg))
        assert ok, msg
        assert "tolerancia 900s" in msg, msg

    def test_webhook_aceita_zero_como_string(self):
        """Config com "0" (string) tambem e modo webhook."""
        from app import healthcheck
        assert healthcheck._as_int("0", 300, allow_zero=True) == 0


# ── Retry de conexao ao qBit ───────────────────────────────────────────

class TestGuardianRetry:
    """Retry de conexao ao qBittorrent no startup e no loop principal.

    Corrige o bug em que uma unica falha de qbit_login() no startup encerrava a
    thread do guardian (return), congelando o heartbeat e deixando o container
    unhealthy indefinidamente. Agora o guardian retenta a cada
    retry_interval_seconds ate reconectar, mantendo o heartbeat vivo.
    """

    def test_guardian_loop_retries_on_startup_failure(self, tmp_config):
        """qbit_login falha no startup → retenta ate sucesso (thread nao morre)."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["check_interval_seconds"] = 0  # webhook apos conectar
        # Valor deliberadamente distinto do DEFAULT_RETRY_INTERVAL (120) e do
        # check_interval (0): o sleep do retry precisa vir DESTA chave.
        cfg["guardian"]["retry_interval_seconds"] = 7
        g.save_config(cfg)

        attempts = {"n": 0}

        def fake_qbit_login():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")
            # sucesso na 3a tentativa

        with mock.patch.object(g, "qbit_login", side_effect=fake_qbit_login), \
             mock.patch.object(g, "write_heartbeat") as m_hb, \
             mock.patch("time.sleep") as m_sleep:
            g.guardian_loop()

        assert attempts["n"] == 3, \
            f"esperado 3 tentativas de login, obtido {attempts['n']}"
        # heartbeat escrito nas 2 tentativas fracassadas (criterio de aceite)
        assert m_hb.call_count >= 2, \
            f"heartbeat deve ser escrito a cada retry, chamadas: {m_hb.call_count}"
        # O retry dorme retry_interval_seconds, nao um valor fixo nem o
        # check_interval: em modo webhook o unico sleep e o do retry.
        assert m_sleep.call_args_list == [mock.call(7), mock.call(7)], \
            f"sleep deve usar retry_interval_seconds, chamadas: {m_sleep.call_args_list}"

    def test_heartbeat_kept_alive_during_prolonged_retry(self, tmp_config):
        """Heartbeat continua vivo enquanto o qBit esta fora (retry prolongado)."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["check_interval_seconds"] = 0
        cfg["guardian"]["retry_interval_seconds"] = 1
        g.save_config(cfg)

        attempts = {"n": 0}
        hb = {"n": 0}
        sleeps = {"n": 0}

        def fake_qbit_login():
            attempts["n"] += 1
            raise requests.exceptions.ConnectionError("refused")

        def fake_write_heartbeat():
            hb["n"] += 1

        class _StopRetry(Exception):
            pass

        slept = []

        def fake_sleep(secs):
            # time.sleep fica FORA do try/except de _connect_with_retry, entao
            # levantar aqui propaga e interrompe o loop de retry no teste.
            slept.append(secs)
            sleeps["n"] += 1
            if sleeps["n"] >= 4:
                raise _StopRetry()

        with mock.patch.object(g, "qbit_login", side_effect=fake_qbit_login), \
             mock.patch.object(g, "write_heartbeat", side_effect=fake_write_heartbeat), \
             mock.patch("time.sleep", side_effect=fake_sleep):
            with pytest.raises(_StopRetry):
                g.guardian_loop()

        # 4 falhas processadas → 4 heartbeats, um por tentativa
        assert attempts["n"] >= 4
        assert hb["n"] == 4, f"heartbeat esperado 4x durante retry, obtido {hb['n']}"
        # Todo sleep do retry usa retry_interval_seconds (nao decai nem muda)
        assert slept == [1, 1, 1, 1], f"intervalos de retry: {slept}"

    @pytest.mark.parametrize("exc", [
        requests.exceptions.ConnectionError("conn refused"),
        requests.exceptions.SSLError("ssl eof"),
        requests.exceptions.Timeout("timeout"),
        requests.exceptions.ReadTimeout("read timeout"),
    ])
    def test_guardian_loop_reconnects_on_transport_error(self, exc, tmp_config):
        """Qualquer erro de transporte no get_torrents dispara reconexao.

        Antes, so ConnectionError era capturado; SSLError/Timeout/ReadTimeout
        escapavam para o except Exception generico (apenas loga, sem reconectar).
        """
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["check_interval_seconds"] = 1
        cfg["guardian"]["retry_interval_seconds"] = 1
        g.save_config(cfg)

        torrent_calls = {"n": 0}
        login_calls = {"n": 0}

        def fake_get_torrents():
            torrent_calls["n"] += 1
            if torrent_calls["n"] == 1:
                raise exc
            return []

        def fake_qbit_login():
            login_calls["n"] += 1
            # Startup conecta de primeira. A reconexao disparada pelo erro de
            # transporte falha 2x antes de dar certo: o loop principal precisa
            # RETENTAR ate conectar, nao tentar uma unica vez e seguir adiante.
            if login_calls["n"] in (2, 3):
                raise exc

        orig_get_config = g.get_config

        def mock_get_config():
            # Sai do loop depois do ciclo bem-sucedido pos-reconexao. O gatilho
            # e o progresso de get_torrents, nao a contagem de get_config —
            # assim o numero de reconexoes nao altera quando o loop termina.
            c = orig_get_config()
            if torrent_calls["n"] >= 2:
                c = dict(c)
                c["guardian"] = dict(c["guardian"])
                c["guardian"]["check_interval_seconds"] = 0
            return c

        with mock.patch.object(g, "get_config", side_effect=mock_get_config), \
             mock.patch.object(g, "qbit_login", side_effect=fake_qbit_login), \
             mock.patch.object(g, "get_torrents", side_effect=fake_get_torrents), \
             mock.patch.object(g, "write_heartbeat"), \
             mock.patch("time.sleep"):
            g.guardian_loop()

        # get_torrents voltou a rodar apos a reconexao e o loop principal seguiu
        assert torrent_calls["n"] == 2, \
            f"get_torrents deveria rodar apos reconexao, chamadas: {torrent_calls['n']}"
        # 1 login no startup + 3 na reconexao (2 falhas + 1 sucesso). Uma
        # implementacao que tenta reconectar so uma vez para em 2.
        assert login_calls["n"] == 4, \
            f"a reconexao deve retentar ate conectar, logins: {login_calls['n']}"

    def test_retry_interval_default_positive(self, tmp_config):
        """Chave valida e respeitada."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["retry_interval_seconds"] = 60
        assert g._retry_interval(cfg) == 60

    @pytest.mark.parametrize("bad_value", [None, 0, -5, "abc", ""])
    def test_retry_interval_fallback(self, bad_value, tmp_config):
        """Valores ausentes/invalidos caem no DEFAULT_RETRY_INTERVAL (120)."""
        g.load_config()
        cfg = g.get_config()
        if bad_value is None:
            cfg["guardian"].pop("retry_interval_seconds", None)
        else:
            cfg["guardian"]["retry_interval_seconds"] = bad_value
        assert g._retry_interval(cfg) == g.DEFAULT_RETRY_INTERVAL
