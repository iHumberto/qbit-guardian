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
import sys
import tempfile
import time
import base64
import requests
from unittest import mock

import pytest

import app.guardian as g
import app.updates as u
from app.version import __version__ as APP_VERSION
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

    # ── regressao: fila nao e "sem seeds" ──────────────────────────────

    def test_queued_nunca_removido_por_sem_seeds(self, tmp_config):
        """`queuedDL` fora do criterio de sem-seeds.

        Um torrent na fila nao conectou ao tracker, logo `num_complete == 0`
        nele significa "ainda nao perguntei", nao "nao existem seeders". Com
        MaxActiveDownloads baixo e a fila cheia, incluir esse estado removia em
        massa downloads que nunca tiveram chance de comecar — foi o que
        aconteceu com 51 de 54 torrents enfileirados em producao.
        """
        cfg = g.load_config()
        cfg["guardian"]["remove_no_seeds"] = True
        cfg["guardian"]["no_seeds_time"] = 15
        cfg["guardian"]["no_seeds_unit"] = "minutes"
        g.save_config(cfg)
        antigo = time.time() - 7200
        t = self.make_torrent("queuedDL", antigo, num_complete=0)
        assert not g.is_stalled(t, cfg)[0]
        # os estados que de fato tentaram conectar seguem valendo
        assert g.is_stalled(self.make_torrent("downloading", antigo, num_complete=0), cfg)[0]
        assert g.is_stalled(self.make_torrent("stalledDL", antigo, num_complete=0), cfg)[0]

    # ── regressao: espera na fila nao e inatividade do torrent ─────────

    def test_metadl_recem_ativado_nao_e_removido(self, tmp_config):
        """O falso positivo que o Humberto suspeitou, e que era real.

        Com `max_active_downloads` baixo, um torrent passa horas em `queuedDL`
        — estado que nenhuma regra avalia. No instante em que entra em
        `metaDL`, o `tempo_parado` ja acumulou TODA a espera da fila (porque
        quem nunca transferiu cai em `added_on`), e ele seria removido na hora,
        sem ter tido um segundo de chance real.

        Medido em producao: 36 de 37 enfileirados com `time_active == 0` e
        290 min de idade.
        """
        cfg = g.load_config()
        cfg["guardian"]["remove_stalled"] = True
        cfg["guardian"]["stalled_time"] = 15
        cfg["guardian"]["stalled_unit"] = "minutes"
        g.save_config(cfg)

        t = self.make_torrent("metaDL", time.time() - 290 * 60)   # 4,8 h de idade
        t["time_active"] = 0                                      # nunca teve slot
        assert not g.is_stalled(t, cfg)[0], \
            "espera na fila nao pode contar como inatividade do torrent"

    def test_metadl_com_tempo_ativo_suficiente_e_removido(self, tmp_config):
        """O piso nao pode virar imunidade: quem teve chance e julgado."""
        cfg = g.load_config()
        cfg["guardian"]["remove_stalled"] = True
        cfg["guardian"]["stalled_time"] = 15
        cfg["guardian"]["stalled_unit"] = "minutes"
        g.save_config(cfg)

        t = self.make_torrent("metaDL", time.time() - 290 * 60)
        t["time_active"] = 3600        # uma hora ativo, e nada transferido
        assert g.is_stalled(t, cfg)[0]

    def test_piso_vale_tambem_para_sem_seeds(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["remove_no_seeds"] = True
        cfg["guardian"]["no_seeds_time"] = 15
        cfg["guardian"]["no_seeds_unit"] = "minutes"
        g.save_config(cfg)

        t = self.make_torrent("downloading", time.time() - 7200, num_complete=0)
        t["time_active"] = 0
        assert not g.is_stalled(t, cfg)[0], "recem-ativado sem seeds nao e culpa dele"
        t["time_active"] = 7200
        assert g.is_stalled(t, cfg)[0]

    def test_tempo_ativo_distingue_ausente_de_zero(self, tmp_config):
        """`None` e "desconhecido"; `0` e "nao teve tempo nenhum".

        Em producao o campo sempre vem. A distincao existe para que teste
        focado em outro criterio nao precise declarar `time_active`.
        """
        assert g.tempo_ativo({}) is None
        assert g.tempo_ativo({"time_active": 0}) == 0
        assert g.tempo_ativo({"time_active": 965}) == 965
        assert g.tempo_ativo({"time_active": "abc"}) is None
        assert g.tempo_ativo({"time_active": -5}) == 0

    def test_campo_ausente_preserva_o_comportamento_anterior(self, tmp_config):
        """Sem o campo nao ha base para o piso — a regra antiga vale."""
        cfg = g.load_config()
        cfg["guardian"]["remove_stalled"] = True
        cfg["guardian"]["stalled_time"] = 1
        cfg["guardian"]["stalled_unit"] = "hours"
        g.save_config(cfg)
        t = self.make_torrent("stalledDL", time.time() - 7200)
        assert "time_active" not in t
        assert g.is_stalled(t, cfg)[0]

    # ── regressao: tempo parado != idade do torrent ────────────────────

    def test_usa_last_activity_e_nao_a_idade_do_torrent(self, tmp_config):
        """O limiar mede tempo PARADO, nao idade.

        Com `added_on`, um torrent baixado a semanas e que parou agora era
        removido de imediato, e um recem-adicionado e parado desde o inicio
        nunca era. `last_activity` inverte isso para o lado certo.
        """
        cfg = g.load_config()
        cfg["guardian"]["remove_stalled"] = True
        cfg["guardian"]["stalled_time"] = 1
        cfg["guardian"]["stalled_unit"] = "hours"
        g.save_config(cfg)

        # antigo, mas transferiu algo ha 1 minuto -> NAO deve ser removido
        t = self.make_torrent("stalledDL", time.time() - 7 * 86400)
        t["last_activity"] = time.time() - 60
        assert not g.is_stalled(t, cfg)[0]

        # recente, porem sem transferir nada ha 2 horas -> deve ser removido
        t2 = self.make_torrent("stalledDL", time.time() - 300)
        t2["last_activity"] = time.time() - 7200
        assert g.is_stalled(t2, cfg)[0]

    def test_tempo_parado_cai_para_added_on(self, tmp_config):
        """Sem `last_activity`, o calculo usa `added_on`."""
        agora = time.time()
        t = {"added_on": agora - 3600}
        assert 3590 <= g.tempo_parado(t) <= 3610
        t2 = {"added_on": agora - 3600, "last_activity": agora - 120}
        assert 110 <= g.tempo_parado(t2) <= 130


# ── is_slow: velocidade minima ─────────────────────────────────────────

class TestVelocidadeMinima:
    """Remocao por velocidade sustentada abaixo de um minimo.

    Caso que motivou: um torrent de 2,5 GiB baixando a 2,2 KiB/s com ETA de
    6 dias, ocupando um slot da fila indefinidamente.
    """

    KiB = 1024

    def make(self, state="downloading", dlspeed=0, downloaded=0, h="abc123"):
        return {"hash": h, "name": "test.torrent", "state": state,
                "dlspeed": dlspeed, "downloaded": downloaded,
                "added_on": time.time() - 3600}

    def _cfg(self, speed=100, unit="KiB", tempo=15, tunit="minutes", on=True):
        cfg = g.load_config()
        gu = cfg["guardian"]
        gu["remove_slow"] = on
        gu["slow_speed"] = speed
        gu["slow_speed_unit"] = unit
        gu["slow_time"] = tempo
        gu["slow_unit"] = tunit
        g.save_config(cfg)
        return cfg

    # ── conversao de unidades ──

    def test_converte_as_quatro_unidades(self, tmp_config):
        assert g._speed_to_bytes(1, "KiB") == 1024
        assert g._speed_to_bytes(1, "MiB") == 1024 ** 2
        assert g._speed_to_bytes(1, "GiB") == 1024 ** 3
        assert g._speed_to_bytes(1, "TiB") == 1024 ** 4

    def test_unidade_desconhecida_cai_em_kib(self, tmp_config):
        """Config corrompida nao deve virar limite absurdo."""
        assert g._speed_to_bytes(10, "furlongs") == 10 * 1024

    def test_valor_invalido_desliga_em_vez_de_estourar(self, tmp_config):
        assert g._speed_to_bytes("abc", "KiB") == 0.0
        assert g._speed_to_bytes(None, "KiB") == 0.0

    def test_formata_na_maior_unidade_legivel(self, tmp_config):
        assert g._fmt_speed(512) == "512 B/s"
        assert g._fmt_speed(2219) == "2.17 KiB/s"
        assert g._fmt_speed(5 * 1024 ** 2) == "5.00 MiB/s"

    # ── o caminho principal ──

    def test_remove_quando_a_media_fica_abaixo_pelo_tempo_limite(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        # janela aberta 20 min atras, com 1 MiB baixado desde entao
        # media = 1 MiB / 1200 s = ~0,85 KiB/s, bem abaixo de 100 KiB/s
        g._lento_desde["abc123"] = (time.time() - 1200, 0)
        lento, motivo = g.is_slow(self.make(downloaded=1024 ** 2), cfg)
        assert lento
        assert "media" in motivo and "minimo 100 KiB" in motivo

    def test_nao_remove_antes_do_tempo_limite(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        g._lento_desde["abc123"] = (time.time() - 60, 0)   # 1 min de janela
        assert not g.is_slow(self.make(downloaded=1024), cfg)[0]

    def test_recuperou_no_meio_descarta_a_janela(self, tmp_config):
        """Media acima do limite = o torrent se recuperou; janela some.

        Sem isto, um torrent que ficou lento por um momento carregaria a marca
        para sempre e seria removido ao cruzar o tempo, mesmo baixando bem.
        """
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        g._lento_desde["abc123"] = (time.time() - 1200, 0)
        # 500 MiB em 1200 s = ~426 KiB/s, acima do minimo
        lento, _ = g.is_slow(self.make(downloaded=500 * 1024 ** 2), cfg)
        assert not lento
        assert "abc123" not in g._lento_desde, "janela deveria ter sido descartada"

    def test_primeira_observacao_so_abre_janela_se_ja_esta_lento(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        # rapido: nao abre janela
        assert not g.is_slow(self.make(dlspeed=500 * self.KiB), cfg)[0]
        assert "abc123" not in g._lento_desde
        # lento: abre, mas nao remove nesta passada
        assert not g.is_slow(self.make(dlspeed=2 * self.KiB), cfg)[0]
        assert "abc123" in g._lento_desde

    # ── regressao: a licao do queuedDL ──

    def test_queued_nunca_e_avaliado_por_velocidade(self, tmp_config):
        """`queuedDL` tem 0 B/s por definicao — julgar isso e remover a fila.

        Mesmo defeito que, no criterio de sem-seeds, qualificou 51 de 54
        torrents enfileirados para remocao na v2.7.0.
        """
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        g._lento_desde["abc123"] = (time.time() - 99999, 0)
        lento, _ = g.is_slow(self.make(state="queuedDL"), cfg)
        assert not lento
        assert "abc123" not in g._lento_desde, "estado fora de download limpa a janela"

    def test_outros_estados_tambem_ficam_fora(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        for estado in ("stalledDL", "metaDL", "uploading", "stoppedUP", "checkingDL"):
            g._lento_desde["abc123"] = (time.time() - 99999, 0)
            assert not g.is_slow(self.make(state=estado), cfg)[0], estado

    # ── desligado / mal configurado ──

    def test_desligado_nao_remove(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=15, on=False)
        g._lento_desde["abc123"] = (time.time() - 99999, 0)
        assert not g.is_slow(self.make(downloaded=0), cfg)[0]

    def test_limite_zero_desliga(self, tmp_config):
        cfg = self._cfg(speed=0, tempo=15)
        g._lento_desde["abc123"] = (time.time() - 99999, 0)
        assert not g.is_slow(self.make(downloaded=0), cfg)[0]

    def test_tempo_zero_desliga(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=0)
        g._lento_desde["abc123"] = (time.time() - 99999, 0)
        assert not g.is_slow(self.make(downloaded=0), cfg)[0]

    # ── integracao e limpeza de estado ──

    def test_check_stalled_and_remove_remove_por_lentidao(self, tmp_config):
        cfg = self._cfg(speed=100, tempo=15, tunit="minutes")
        cfg["guardian"]["remove_stalled"] = False
        cfg["guardian"]["remove_no_seeds"] = False
        g.save_config(cfg)
        g._lento_desde["abc123"] = (time.time() - 1200, 0)
        with mock.patch.object(g, "block_and_search") as m_block, \
             mock.patch.object(g, "remove_torrent") as m_rm, \
             mock.patch.object(g, "send_notification"):
            assert g.check_stalled_and_remove(self.make(downloaded=1024))
        assert m_block.called and m_rm.called

    def test_prune_limpa_janelas_de_torrent_que_saiu(self, tmp_config):
        """Sem isto o dict cresce indefinidamente conforme torrents vao e vem."""
        g._lento_desde.update({"vivo": (time.time(), 0), "morto": (time.time(), 0)})
        g._prune_processed({"vivo"})
        assert "vivo" in g._lento_desde
        assert "morto" not in g._lento_desde


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
        # (url, params) — separado de `gets` para nao quebrar quem compara
        # `sess.gets` como lista de URLs.
        self.get_calls = []
        self.deletes = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append(url)
        self.get_calls.append((url, kwargs.get("params")))
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


class TestArrQueuePaginacao:
    """A queue do Arr vem paginada, e o default de 10 escondia o blocklist.

    Bug medido em producao: 43 itens na queue do Radarr, 10 retornados. O
    torrent a bloquear estava fora da primeira pagina, entao o `downloadId`
    nunca casava — e a falha era **silenciosa**, porque "nao achei na queue"
    cai no fallback por nome e depois desiste sem erro.
    """

    BASE = "https://radarr.home.arpa/api/v3"

    @pytest.fixture
    def radarr_cfg(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["radarr"]["url"] = "https://radarr.home.arpa/"
        cfg["radarr"]["api_key"] = "rkey"
        g.save_config(cfg)
        return cfg

    def test_queue_e_pedida_com_page_size_explicito(self, radarr_cfg):
        get_map = {"/queue": {"records": [{"id": 42, "downloadId": "ABC123", "movieId": 77}]}}
        with _run_handle_arr("Radarr", "radarr", get_map,
                             "abc123", "Some.Movie.2020.mkv") as sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")

        queue_calls = [(u, p) for u, p in sess.get_calls if u.endswith("/queue")]
        assert queue_calls, "a queue nem foi consultada"
        _, params = queue_calls[0]
        assert params and params.get("pageSize") == g.ARR_QUEUE_PAGE_SIZE, \
            f"queue pedida sem pageSize: {params!r} — volta a ver so 10 itens"

    def test_page_size_cobre_fila_de_dezenas(self, radarr_cfg):
        """O valor pedido tem de ser maior que uma fila realista."""
        assert g.ARR_QUEUE_PAGE_SIZE >= 100

    def test_acha_item_que_estaria_fora_da_primeira_pagina(self, radarr_cfg):
        """Com 43 itens e o alvo na posicao 40, o blocklist precisa acontecer."""
        registros = [{"id": i, "downloadId": f"HASH{i:03d}", "movieId": i}
                     for i in range(1, 44)]
        registros[39] = {"id": 999, "downloadId": "ABC123", "movieId": 77}
        get_map = {"/queue": {"totalRecords": 43, "records": registros}}
        with _run_handle_arr("Radarr", "radarr", get_map,
                             "abc123", "Some.Movie.2020.mkv") as sess:
            g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")

        assert sess.deletes == [(f"{self.BASE}/queue/999",
                                 {"blocklist": "true", "removeFromClient": "false"})]
        assert sess.commands == [{"name": "MoviesSearch", "movieIds": [77]}]

    def test_avisa_quando_a_pagina_trunca(self, radarr_cfg):
        """Falha silenciosa e pior que barulhenta: tem de sair warning."""
        get_map = {"/queue": {"totalRecords": 5000,
                              "records": [{"id": 1, "downloadId": "X", "movieId": 1}]},
                   "/movie": [],
                   }
        with mock.patch.object(g.log, "warning") as m_warn:
            with _run_handle_arr("Radarr", "radarr", get_map,
                                 "abc123", "Some.Movie.2020.mkv"):
                g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")
        assert m_warn.called, "queue truncada deveria avisar"
        assert "5000" in str(m_warn.call_args)

    def test_nao_avisa_quando_a_pagina_cobre_tudo(self, radarr_cfg):
        get_map = {"/queue": {"totalRecords": 1,
                              "records": [{"id": 42, "downloadId": "ABC123", "movieId": 77}]}}
        with mock.patch.object(g.log, "warning") as m_warn:
            with _run_handle_arr("Radarr", "radarr", get_map,
                                 "abc123", "Some.Movie.2020.mkv"):
                g._handle_arr("Radarr", "radarr", "abc123", "Some.Movie.2020.mkv")
        assert not m_warn.called


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


def _bloco_balanceado(html, inicio):
    """Recorta de `inicio` ate o </div> que fecha a <div> aberta ali.

    Substitui os regex que casavam `\n        </div>` — indentacao exata. Com
    os blocos dentro do grid de duas colunas do card central a indentacao
    mudou, e um teste ancorado nela procura um fechamento que nao existe.
    """
    nivel = 0
    for m in re.finditer(r"<div\b|</div>", html[inicio:]):
        nivel += 1 if m.group(0).startswith("<div") else -1
        if nivel == 0:
            return html[inicio:inicio + m.end()]
    raise AssertionError("<div> sem fechamento a partir de %d" % inicio)


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

    # A escala errada chegou ao `CONTEXT.md` justamente porque esta varredura
    # nasceu olhando so para `static/`: o glossario dizia "Valor de 0 a 7",
    # a string que o teste ja proibia, num arquivo fora da lista.
    PROIBIDOS = ("(0\u20137)", "(0-7)", "0 a 7",
                 "7 = m\u00e1xima, 0", "7 = maximum, 0")

    @pytest.mark.parametrize("fonte", ["index.html", "i18n.js"])
    def test_nenhum_texto_anuncia_escala_continua(self, fonte):
        """REGRESSAO: o rotulo dizia "(0–7)", sugerindo que 2-5 valem."""
        texto = _read_static(fonte)
        for proibido in self.PROIBIDOS:
            assert proibido not in texto, \
                f"{fonte} ainda anuncia a escala antiga: {proibido!r}"

    @pytest.mark.parametrize("fonte", ["CONTEXT.md", "README.md", "README.pt-BR.md"])
    def test_nenhum_arquivo_da_raiz_anuncia_escala_continua(self, fonte):
        with open(os.path.join(REPO_ROOT, fonte), encoding="utf-8") as f:
            texto = f.read()
        for proibido in self.PROIBIDOS:
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
        ("--col-side", "274px"),
        ("--col-main", "548px"),
        ("--col-notif", "320px"),
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

    def _tokens_de_coluna(self):
        html = _read_static("index.html")
        root = re.search(r":root\s*\{(.*?)\}", html, re.S).group(1)
        return [int(re.search(r"--col-%s:\s*(\d+)px" % nome, root).group(1))
                for nome in ("side", "main", "notif")]

    def test_largura_do_container_deriva_dos_tokens(self):
        """A largura maxima e a soma das tres colunas + 2 gutters.

        Numero solto aqui sai de sincronia na primeira vez que uma coluna
        mudar de largura — foi o que aconteceu quando Notificacoes passou de
        274 para 320.
        """
        html = _read_static("index.html")
        assert re.search(r"\.container\s*\{[^}]*max-width:\s*calc\(\s*"
                         r"var\(--col-side\)\s*\+\s*"
                         r"var\(--col-main\)\s*\+\s*var\(--col-notif\)\s*"
                         r"\+\s*var\(--gutter\)\s*\*\s*2\s*\)", html, re.S)

    def test_as_tres_colunas_tem_larguras_diferentes(self):
        """Nenhuma coluna e igual a outra, e cada uma tem um motivo.

        A esquerda tem campos de uma linha; a central abriga duas colunas
        internas; a direita tem caixas de texto que se edita de verdade.
        """
        lado, centro, notif = self._tokens_de_coluna()
        assert centro == lado * 2, f"a central ({centro}) deveria caber duas colunas internas"
        assert notif > lado, f"Notificacoes ({notif}) nao pode ser mais estreita que a esquerda"

    def test_proporcao_em_fr_bate_com_os_tokens_em_px(self):
        """Os `fr` da grade repetem os numeros dos tokens porque `<flex>` nao
        aceita `calc()`. Esta e a amarra que impede os dois de divergirem.
        """
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.grid\s*\{(.*?)\}", html, re.S)
        assert m, "regra .grid nao encontrada"
        fr = re.search(r"grid-template-columns:\s*(\d+)fr\s+(\d+)fr\s+(\d+)fr", m.group(1))
        assert fr, m.group(1)
        assert [int(v) for v in fr.groups()] == self._tokens_de_coluna(), \
            f"grid-template-columns {fr.groups()} != tokens {self._tokens_de_coluna()}"

    def test_grade_nao_usa_largura_fixa(self):
        """Com `px` em vez de `fr` a grade estoura a viewport antes do
        breakpoint em vez de encolher junto."""
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.grid\s*\{(.*?)\}", html, re.S)
        assert not re.search(r"grid-template-columns:[^;]*\dpx", m.group(1)), m.group(1)

    def test_breakpoint_acompanha_a_largura_do_conteudo(self):
        """O breakpoint nao pode ficar ABAIXO da largura do conteudo.

        Se ficar, existe uma faixa de viewports entre os dois em que a grade
        continua em tres colunas sem caber — e a pagina ganha rolagem
        horizontal. Quando Notificacoes foi de 274 para 320, o conteudo passou
        de 1152 para 1198 px (1238 com o padding do body) e o breakpoint parado
        em 1199 abriria exatamente essa faixa, de 1200 a 1238.

        Empilhar um pouco antes e deliberado: na folga o layout caberia, mas
        encostado nas bordas da janela.
        """
        html = _read_static("index.html")
        conteudo = sum(self._tokens_de_coluna()) + 28 * 2
        m = re.search(r"@media \(max-width:(\d+)px\) \{\s*\.grid \{ grid-template-columns:1fr", html)
        assert m, "breakpoint da grade nao encontrado"
        corpo = re.search(r"body \{(.*?)\}", html, re.S).group(1)
        padding = re.search(r"padding:\s*\d+px\s+(\d+)px", corpo)
        total = conteudo + int(padding.group(1)) * 2
        assert int(m.group(1)) >= total, \
            f"empilha em {m.group(1)}px, mas o conteudo so para de caber em {total}px"

    def test_modal_nao_segue_a_coluna_da_grade(self):
        """A lateral virou 274px: estreita para um formulario de tres campos.

        Mesmo token da tela de login — e a mesma coisa: largura confortavel
        para um formulario curto, que nao deriva da grade de cards.
        """
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.modal\s*\{(.*?)\}", html, re.S)
        assert m and "var(--col-form)" in m.group(1), m.group(1) if m else None

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

    def _blocos_de_remocao(self):
        html = _read_static("index.html")
        achados = [_bloco_balanceado(html, m.start())
                   for m in re.finditer(r'<div class="toggle-block[^"]*">', html)]
        assert achados, "nenhum bloco de remocao encontrado"
        return achados

    @pytest.mark.parametrize("lid", ["remove_stalled", "remove_no_seeds", "remove_slow"])
    def test_toggle_de_remocao_fica_na_linha_do_rotulo(self, lid):
        """REGRESSAO: o toggle vinha depois da unidade e sobrava espaco a direita.

        Mesma anatomia dos blocos de mensagem — rotulo a esquerda, liga/desliga
        encostado na borda direita, controles na linha de baixo.
        """
        alvo = next((b for b in self._blocos_de_remocao() if f'id="{lid}"' in b), None)
        assert alvo, f"bloco de {lid} nao encontrado"

        cabeca = re.search(r'<div class="head">(.*?)</div>', alvo, re.S).group(1)
        assert f'id="{lid}"' in cabeca, "o toggle deve ficar no cabecalho, com o rotulo"
        assert f'for="{lid}"' in cabeca
        # os controles ficam depois do cabecalho
        assert alvo.index('class="inline"') > alvo.index(f'id="{lid}"')

    def test_layout_antigo_de_linha_unica_nao_voltou(self):
        html = _read_static("index.html")
        assert "toggle-row" not in html


class TestWebUICardCentral:
    """O card do Guardian e o unico com duas colunas internas.

    Ele tinha onze campos empilhados numa coluna. Como a grade estica as tres
    colunas juntas, a altura dele virava a altura das outras duas: os cards de
    qBittorrent/Radarr/Sonarr e o de Notificacoes, que tem pouca coisa, ficavam
    com um vazio enorme no rodape. Dividir em duas colunas corta a altura pela
    metade e as outras encolhem junto.
    """

    def _duo(self):
        html = _read_static("index.html")
        i = html.find('<div class="duo">')
        assert i >= 0, "grid de duas colunas nao encontrado"
        return _bloco_balanceado(html, i)

    def test_tem_grid_de_duas_colunas(self):
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.duo\s*\{([^}]*)\}", html)
        assert m, "falta a regra .duo"
        assert "repeat(2," in m.group(1).replace(" ", ""), m.group(1)

    def test_so_o_card_central_se_divide(self):
        """As laterais tem um campo por linha: dividir deixaria tudo apertado."""
        html = _read_static("index.html")
        assert html.count('<div class="duo">') == 1

    def test_ordem_dos_campos_preenche_linha_a_linha(self):
        """Polling | Reavaliar fila, depois Reconexao | Prioridade midia.

        A ordem e o layout: o grid preenche da esquerda para a direita, entao
        trocar a ordem no HTML move o campo de lugar na tela.
        """
        campos = re.findall(r'<(?:input|select|textarea) id="(\w+)"', self._duo())
        assert campos[:8] == [
            "check_interval", "reevaluate_interval",
            "retry_interval", "priority_media",
            "priority_normal", "priority_skip",
            "valid_extensions", "dangerous_extensions",
        ], campos[:8]

    def test_campos_de_tempo_declaram_a_unidade(self):
        """O rotulo perdeu o "(segundos)" — a unidade foi para o lado da caixa.

        Sem isto a limpeza dos rotulos levaria embora a informacao de que o
        numero e em segundos, que nao e ajuda: e parte do campo.
        """
        duo = self._duo()
        for cid in ("check_interval", "reevaluate_interval", "retry_interval"):
            assert re.search(r'<div class="num">\s*<input id="' + cid + r'".*?'
                             r'data-i18n="unit_s"', duo, re.S), \
                f"{cid} sem a unidade ao lado da caixa"

    def test_caixa_de_tempo_ocupa_a_coluna(self):
        """A caixa cresce com a coluna; sobra so o espaco da unidade.

        Ela ja teve 88px fixos — curta demais, com um vazio de 150px a direita
        dentro da propria coluna.
        """
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.field \.num input\s*\{([^}]*)\}", html)
        assert m, "falta a regra da caixa numerica"
        regra = m.group(1).replace(" ", "")
        assert "flex:1" in regra, regra
        assert not re.search(r"(?<!min-)width:\d+px", regra), \
            "largura fixa volta a deixar vazio dentro da coluna"

    def test_caixa_de_tempo_encolhe_abaixo_do_tamanho_intrinseco(self):
        """Item de flex nao encolhe abaixo do conteudo sem `min-width:0`.

        Um <input> tem ~170px de largura intrinseca; sem isto o par
        caixa + unidade estoura a coluna de 240px.
        """
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.field \.num input\s*\{([^}]*)\}", html)
        assert "min-width:0" in m.group(1).replace(" ", ""), m.group(1)

    def test_unidade_nao_estica_junto(self):
        """O `s` ocupa so o que precisa — quem cresce e a caixa."""
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.num \.unidade\s*\{([^}]*)\}", html)
        assert m and "flex:0 0 auto" in m.group(1), m.group(1) if m else None

    def test_controles_da_velocidade_sao_centralizados(self):
        """A frase atravessa as duas colunas e e curta demais para encher a
        largura: centralizada ela fica sob o meio do bloco em vez de pendurada
        na esquerda com um vazio a direita."""
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.toggle-block\.span2 > \.inline\s*\{([^}]*)\}", html)
        assert m, "falta a regra que centraliza os controles de velocidade"
        assert "justify-content:center" in m.group(1).replace(" ", ""), m.group(1)

    def test_rotulo_da_velocidade_nao_acompanha_a_centralizacao(self):
        """O rotulo e o toggle marcam as bordas do bloco: centraliza-los
        tiraria a referencia de onde o bloco comeca e termina."""
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.head\s*\{([^}]*)\}", html)
        assert m and "space-between" in m.group(1), m.group(1) if m else None

    def test_bloco_de_velocidade_atravessa_as_duas_colunas(self):
        """Os dois pares formam uma frase — abaixo de X por Y. Em colunas
        separadas o limite perderia a janela em que ele vale."""
        duo = self._duo()
        i = duo.index('id="remove_slow"')
        abertura = duo.rindex('<div class="toggle-block', 0, i)
        assert "span2" in duo[abertura:i], "o bloco de velocidade deveria ser span2"

    def test_frase_da_velocidade_tem_conector(self):
        """Sem o "por", os quatro controles viram uma fileira de caixas sem
        relacao declarada entre os dois pares."""
        duo = self._duo()
        assert 'data-i18n="conector_por"' in duo

    def test_span2_tem_regra_de_grid(self):
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.duo > \.span2\s*\{([^}]*)\}", html)
        assert m, "falta a regra .duo > .span2"
        assert "1 / -1" in m.group(1), m.group(1)

    def test_blocos_vizinhos_alinham_os_controles(self):
        """Os rotulos dos dois blocos tem alturas diferentes (um quebra em duas
        linhas). Sem empurrar os controles para a base, as caixas ficam em
        degrau dentro da mesma linha do grid."""
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.duo > \.toggle-block\s*\{([^}]*)\}", html)
        assert m, "falta a regra que alinha os blocos de remocao"
        assert "space-between" in m.group(1), m.group(1)

    def test_verbo_remover_subiu_para_o_grupo(self):
        """Era repetido nos tres rotulos."""
        assert '<h3 class="span2" data-i18n="section_remove">' in _read_static("index.html")

    @pytest.mark.parametrize("chave", ["label_remove_stalled", "label_remove_no_seeds",
                                       "label_remove_slow"])
    def test_rotulo_de_remocao_so_declara_a_condicao(self, chave):
        """Com o verbo no cabecalho do grupo, cada linha diz so a condicao."""
        js = _read_static("i18n.js")
        valores = re.findall(chave + r":\s*'([^']*)'", js)
        assert len(valores) == 2, f"{chave} deveria existir nos dois idiomas"
        for valor in valores:
            assert "Remover" not in valor and "Remove" not in valor, valor


class TestWebUIAjudaSaiuDaTela:
    """A home nao explica mais campo por campo: a documentacao faz isso.

    Os textos embaixo de cada campo disputavam atencao com os proprios
    controles — e um deles tinha tres linhas. Os nomes das variaveis de
    mensagem sao a unica excecao e viraram tooltip, porque quem edita o texto
    precisa deles na mao e nao vai abrir a doc para mudar um layout.
    """

    HELPS_REMOVIDOS = ["help_check_interval", "help_reevaluate_interval",
                       "help_retry_interval", "help_priority_media",
                       "help_remove_slow"]

    @pytest.mark.parametrize("chave", HELPS_REMOVIDOS)
    @pytest.mark.parametrize("fonte", ["index.html", "i18n.js"])
    def test_chave_de_ajuda_nao_sobrou(self, fonte, chave):
        """Chave orfa no i18n volta para a tela no proximo copiar e colar."""
        assert chave not in _read_static(fonte), f"{chave} ainda em {fonte}"

    def test_nenhum_campo_do_guardian_tem_ajuda_embaixo(self):
        html = _read_static("index.html")
        duo = _bloco_balanceado(html, html.index('<div class="duo">'))
        assert 'class="help"' not in duo, "voltou texto de ajuda no card central"

    def test_a_unica_ajuda_que_fica_e_a_do_modal(self):
        """`help_cred` fica: a senha atual ser obrigatoria e regra do
        formulario, nao explicacao de para que serve o campo."""
        html = _read_static("index.html")
        assert html.count('class="help"') == 1, \
            "a home voltou a explicar campo na tela"
        assert 'data-i18n="help_cred"' in html

    def test_a_doc_cobre_os_campos_que_perderam_a_ajuda(self):
        """A UI limpa so funciona se o conhecimento tiver outro lugar.

        Cada campo que perdeu a explicacao na tela precisa aparecer na
        referencia de campos da documentacao, nos dois idiomas.
        """
        campos = ["check_interval_seconds", "reevaluate_interval_seconds",
                  "retry_interval_seconds", "priority_media",
                  "priority_normal", "priority_skip",
                  "valid_media_extensions", "dangerous_extensions",
                  "remove_stalled", "remove_no_seeds", "remove_slow",
                  "slow_speed_unit", "slow_unit"]
        for lang in ("pt-BR", "en-US"):
            caminho = os.path.join(REPO_ROOT, "docs", lang, "USAGE.md")
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
            for campo in campos:
                assert campo in texto, f"docs/{lang}/USAGE.md nao cobre {campo}"


class TestWebUITooltipDeVariaveis:
    """As variaveis de template viraram tooltip ao lado do rotulo."""

    EVENTOS = ["optimized", "removed", "stalled"]

    @pytest.mark.parametrize("ev", EVENTOS)
    def test_variaveis_ficam_dentro_do_tooltip(self, ev):
        html = _read_static("index.html")
        assert re.search(r'<button type="button" class="dica".*?id="vars_' + ev + r'"',
                         html, re.S), f"vars_{ev} deveria estar dentro do botao de dica"

    @pytest.mark.parametrize("ev", EVENTOS)
    def test_lista_nao_ficou_embaixo_da_caixa(self, ev):
        """REGRESSAO: a lista ocupava uma linha fixa sob cada caixa de texto."""
        html = _read_static("index.html")
        assert f'<span class="help vars" id="vars_{ev}">' not in html

    def test_so_as_mensagens_tem_tooltip(self):
        """Lembrete rapido e para quem edita texto; o resto e documentacao."""
        html = _read_static("index.html")
        assert html.count('class="dica"') == len(self.EVENTOS)

    def test_tooltip_comeca_escondido(self):
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.dica-tip\s*\{(.*?)\}", html, re.S)
        assert m, "falta a regra .dica-tip"
        assert "visibility:hidden" in m.group(1).replace(" ", "")

    def test_tooltip_abre_no_hover_e_no_foco(self):
        """`:focus` e nao so `:focus-visible`: em toque o navegador foca sem
        marcar como visible, e o lembrete tem que abrir no dedo tambem."""
        html = _read_static("index.html")
        assert re.search(r"\.dica:hover \.dica-tip", html)
        assert re.search(r"\.dica:focus \.dica-tip", html)

    def test_tooltip_contrasta_com_o_card(self):
        """Ele abre SOBRE o card: com `--card` de fundo nao se separaria dele."""
        html = _read_static("index.html")
        m = re.search(r"(?m)^\s*\.dica-tip\s*\{(.*?)\}", html, re.S)
        assert "background:var(--bg)" in m.group(1).replace(" ", "")

    def test_botao_tem_nome_acessivel(self):
        """O icone `{ }` nao e texto que um leitor de tela saiba anunciar."""
        html = _read_static("index.html")
        botoes = re.findall(r'<button type="button" class="dica"(.*?)>', html, re.S)
        assert len(botoes) == len(self.EVENTOS)
        for b in botoes:
            assert 'data-i18n-aria="vars_tooltip"' in b, b

    @pytest.mark.parametrize("ev", EVENTOS)
    def test_variaveis_sao_anunciadas_e_nao_so_o_botao(self, ev):
        """O rotulo diz que ha variaveis; a descricao diz quais.

        Sem `aria-describedby` um leitor de tela anuncia "Variaveis que esta
        mensagem aceita, botao" e para — o conteudo do tooltip nunca chega a
        quem nao ve a tela.
        """
        html = _read_static("index.html")
        m = re.search(r'<button type="button" class="dica"([^>]*)>\s*'
                      r'<span class="dica-ico"[^>]*>[^<]*</span>\s*'
                      r'<span class="dica-tip vars" role="tooltip" id="vars_' + ev + r'"',
                      html, re.S)
        assert m, f"estrutura do botao de {ev} mudou"
        assert f'aria-describedby="vars_{ev}"' in m.group(1), m.group(1)

    def test_icone_e_escondido_do_leitor_de_tela(self):
        """O nome acessivel ja esta no botao: o `{ }` seria lido duas vezes."""
        html = _read_static("index.html")
        icones = re.findall(r'<span class="dica-ico"(.*?)>', html)
        assert len(icones) == len(self.EVENTOS)
        for i in icones:
            assert 'aria-hidden="true"' in i, i

    def test_renderizacao_das_variaveis_nao_mudou_de_alvo(self):
        """O renderVars() escreve em `vars_<evento>`; o tooltip e so o lugar
        onde esse span passou a morar."""
        html = _read_static("index.html")
        assert "getElementById('vars_' + ev)" in html


class TestWebUIMovimento:
    """Transicoes respeitam quem pediu menos movimento."""

    def test_reduced_motion_e_respeitado(self):
        html = _read_static("index.html")
        assert "prefers-reduced-motion" in html, \
            "a UI tem transicao em switch e tooltip e nao oferece saida"


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


def _passos_do_tour(nome_da_lista):
    """Extrai os passos de uma das listas de `static/tour.js`.

    Parse por regex, como `_i18n_tables()`: o teste nao executa JS de
    proposito, e so precisa de `alvo` e `chave` de cada passo.
    """
    src = _read_static("tour.js")
    m = re.search(r"var " + nome_da_lista + r" = \[(.*?)\n  \];", src, re.S)
    assert m, f"{nome_da_lista} nao encontrada em tour.js"
    passos = []
    for bloco in re.findall(r"\{(.*?)\}", m.group(1), re.S):
        alvo = re.search(r"alvo:\s*'([^']+)'", bloco)
        chave = re.search(r"chave:\s*'([^']+)'", bloco)
        assert chave, f"passo sem chave de i18n em {nome_da_lista}: {bloco}"
        passos.append((alvo.group(1) if alvo else None, chave.group(1)))
    assert passos, f"{nome_da_lista} ficou vazia"
    return passos


def _seletor_existe(seletor, html):
    """Confere `#id` e `.classe` de um seletor simples contra o HTML.

    Nao e um motor de CSS: cada parte do seletor so precisa aparecer no
    arquivo. Basta para pegar o que importa — um alvo renomeado no HTML e
    esquecido no tour.
    """
    for parte in re.findall(r"[#.][\w-]+", seletor):
        if parte.startswith("#"):
            if f'id="{parte[1:]}"' not in html:
                return False
        elif not re.search(r'class="[^"]*\b' + re.escape(parte[1:]) + r'\b', html):
            return False
    return True


class TestPlaceholderApprise:
    """O campo Apprise espera um endpoint HTTP, nao uma URL de servico.

    `send_notification` faz `requests.post(url, ...)`. Um esquema proprio do
    Apprise (`tgram://`, `discord://`, `pover://`) nao tem adapter no
    `requests`: a chamada levanta `InvalidSchema` antes de qualquer byte sair
    do processo, cai no `except` e vira uma linha de log. O placeholder
    ensinava exatamente esse valor — quem copiasse montava uma configuracao
    que nunca poderia notificar.

    O guardian nao executa o Apprise: ele fala com um servidor Apprise
    hospedado pelo usuario, cujo endpoint e `http://host:8000/notify/<chave>`.
    As URLs de servico vivem na configuracao daquele servidor.
    """

    ESQUEMAS_DE_SERVICO = ("tgram://", "discord://", "pover://", "mailto://",
                           "slack://", "gotify://", "ntfy://")

    @pytest.mark.parametrize("fonte", ["index.html", "i18n.js"])
    def test_placeholder_nao_ensina_url_de_servico(self, fonte):
        """REGRESSAO: o placeholder era `tgram://BOT_TOKEN/CHAT_ID`."""
        texto = _read_static(fonte)
        for linha in texto.splitlines():
            # `erro_apprise_url` cita `tgram://` de proposito: e a mensagem que
            # ensina a NAO usar. O que nao pode sugerir e o placeholder.
            if "apprise_url" not in linha or "erro_apprise_url" in linha:
                continue
            for esquema in self.ESQUEMAS_DE_SERVICO:
                assert esquema not in linha, \
                    f"{fonte} voltou a sugerir {esquema} no campo Apprise: {linha.strip()}"

    def _exemplos_de_apprise(self, fonte):
        """Todo valor de exemplo do campo, venha do HTML ou das tabelas.

        A tag do `<input>` e lida inteira, e nao linha a linha: ela ja passou
        de uma linha para tres quando ganhou o `aria-describedby`, e um teste
        ancorado em linha quebra por formatacao sem que nada tenha piorado.
        """
        texto = _read_static(fonte)
        if fonte.endswith(".html"):
            tag = re.search(r'<input[^>]*id="apprise_url"[^>]*>', texto, re.S)
            assert tag, f"{fonte} nao tem o campo Apprise"
            # O lookbehind evita casar dentro de `data-i18n-placeholder=`,
            # cujo valor e o nome da chave, nao um endereco.
            return re.findall(r'(?<![-\w])placeholder="([^"]+)"', tag.group(0))
        return re.findall(r"placeholder_apprise_url:\s*'([^']+)'", texto)

    @pytest.mark.parametrize("fonte", ["index.html", "i18n.js"])
    def test_placeholder_e_um_endpoint_http(self, fonte):
        exemplos = self._exemplos_de_apprise(fonte)
        assert exemplos, f"{fonte} nao tem exemplo para o campo Apprise"
        for valor in exemplos:
            assert re.match(r"^https?://", valor), \
                f"{fonte}: o placeholder precisa ser um endereco HTTP — {valor}"
            assert "/notify/" in valor, \
                (f"{fonte}: o endpoint do servidor Apprise tem o caminho "
                 f"/notify/<chave> — {valor}")

    def test_o_esquema_do_placeholder_e_aceito_pelo_requests(self):
        """O valor sugerido tem de ser postavel — era isso que faltava.

        Nao faz requisicao: checa o adapter registrado, que e o que o
        `requests` consulta antes de abrir conexao.
        """
        import requests
        sessao = requests.Session()
        js = _read_static("i18n.js")
        for valor in re.findall(r"placeholder_apprise_url:\s*'([^']+)'", js):
            assert sessao.get_adapter(valor), f"{valor} nao tem adapter no requests"
        with pytest.raises(requests.exceptions.InvalidSchema):
            sessao.get_adapter("tgram://BOT_TOKEN/CHAT_ID")

    @pytest.mark.parametrize("doc", ["docs/pt-BR/USAGE.md", "docs/en-US/USAGE.md"])
    def test_a_doc_avisa_que_url_de_servico_nao_vale_no_campo(self, doc):
        """A tabela antiga listava `tgram://` como opcao do campo."""
        with open(os.path.join(REPO_ROOT, doc), encoding="utf-8") as f:
            texto = f.read()
        assert "/notify/" in texto, f"{doc} nao mostra o formato do endpoint"
        assert ("nao funcionam aqui" in texto or "do not work here" in texto
                or "n\u00e3o funcionam aqui" in texto), \
            f"{doc} nao avisa que a URL de servico nao vale no campo"


class TestCampoReavaliarSegueOModo:
    """A tela nao pode oferecer um controle que o motor ignora.

    Com `check_interval_seconds > 0` o guardian roda em polling e
    `_start_reevaluate_loop()` nunca e chamado: o campo *Reavaliar fila*
    ficava editavel, ao lado do Polling, sem nada indicando que o valor nao
    teria efeito. Ver TestTrocaDeModoEmRuntime para o lado do motor.
    """

    def test_o_campo_tem_ancora_para_o_estilo(self):
        html = _read_static("index.html")
        assert 'id="campo-reevaluate"' in html, \
            "sem o wrapper identificado nao da para esmaecer o campo"

    def test_existe_regra_visual_de_campo_ignorado(self):
        html = _read_static("index.html")
        assert ".field.ignorado" in html, "falta o estilo do campo desligado"
        assert re.search(r"\.field\.ignorado input\s*\{[^}]*not-allowed", html), \
            "o campo desligado precisa mostrar que nao aceita edicao"

    def test_a_funcao_liga_o_campo_ao_polling(self):
        html = _read_static("index.html")
        assert "function syncModo()" in html
        m = re.search(r"function syncModo\(\)\s*\{(.*?)\n\}", html, re.S)
        corpo = m.group(1)
        assert "check_interval" in corpo, "o modo e decidido pelo Polling"
        assert "reevaluate_interval" in corpo and "disabled" in corpo

    def test_o_campo_sincroniza_ao_carregar_e_ao_digitar(self):
        """So no load, um Polling recem-digitado nao refletiria no campo."""
        html = _read_static("index.html")
        assert "syncModo();" in html, "falta a chamada no carregamento"
        assert re.search(r"getElementById\('check_interval'\)\s*\.addEventListener\('input', syncModo\)",
                         html), "o campo precisa acompanhar o que esta sendo digitado"

    def test_o_valor_nao_e_apagado_quando_ignorado(self):
        """Desligar o campo nao pode perder o valor: ele volta a valer.

        `disabled` em vez de limpar — e o `getVal` continua lendo o campo, de
        modo que salvar em modo polling preserva o intervalo de reavaliacao.
        """
        html = _read_static("index.html")
        m = re.search(r"function syncModo\(\)\s*\{(.*?)\n\}", html, re.S)
        corpo = m.group(1)
        assert "setVal('reevaluate_interval'" not in corpo and ".value = ''" not in corpo, \
            "o campo desligado mantem o valor guardado"

    @pytest.mark.parametrize("lang", ["pt-BR", "en-US"])
    def test_a_dica_explica_o_motivo_nos_dois_idiomas(self, lang):
        tables = _i18n_tables()
        assert "tip_reevaluate" in tables[lang]
        js = _read_static("i18n.js")
        assert 'data-i18n-title="tip_reevaluate"' in _read_static("index.html"), \
            "a dica precisa passar pelo walker para trocar de idioma"
        valores = re.findall(r"tip_reevaluate:\s*'([^']*)'", js)
        assert len(valores) == 2
        for valor in valores:
            assert "webhook" in valor.lower(), valor


class TestPlaceholdersDeRede:
    """Endereco de exemplo nao pode ser o de uma rede real.

    Placeholder e material de leitura: ele vai para a documentacao, para
    print de tela e para o repositorio publico. Usar a faixa domestica mais
    comum (`192.168.1.x`) deixa claro que ali vai o IP de quem instala, e nao
    o de quem escreveu — alem de ser o que o resto da documentacao ja usava.
    """

    FAIXA_GENERICA = "192.168.1."
    FONTES = ["index.html", "i18n.js", "tour.js"]

    @pytest.mark.parametrize("fonte", FONTES)
    def test_todo_ip_de_exemplo_esta_na_faixa_generica(self, fonte):
        texto = _read_static(fonte)
        for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", texto):
            if ip.startswith("127.") or ip == "0.0.0.0":
                continue
            assert ip.startswith(self.FAIXA_GENERICA), \
                f"{fonte}: {ip} nao esta na faixa de exemplo {self.FAIXA_GENERICA}x"

    @pytest.mark.parametrize("doc", ["docs/pt-BR/USAGE.md", "docs/en-US/USAGE.md"])
    def test_a_doc_usa_a_mesma_faixa(self, doc):
        with open(os.path.join(REPO_ROOT, doc), encoding="utf-8") as f:
            texto = f.read()
        for ip in re.findall(r"\b192\.168\.(?:\d{1,3})\.\d{1,3}\b", texto):
            assert ip.startswith(self.FAIXA_GENERICA), \
                f"{doc}: {ip} foge da faixa de exemplo"

    def test_o_tour_preenche_com_o_mesmo_endereco_do_placeholder(self):
        """O passo que digita no campo nao pode ensinar outro endereco."""
        js = _read_static("i18n.js")
        tour = _read_static("tour.js")
        for chave, campo in [("placeholder_qbit_url", "#qbit_url"),
                             ("placeholder_apprise_url", "#apprise_url")]:
            valor = re.search(chave + r":\s*'([^']+)'", js).group(1)
            passo = re.search(r"alvo: '" + re.escape(campo) + r"'.*?\}", tour, re.S).group(0)
            preenche = re.search(r"preenche: '([^']+)'", passo)
            assert preenche, f"o passo de {campo} deveria preencher o campo"
            assert preenche.group(1) == valor, \
                f"{campo}: o tour digita {preenche.group(1)}, o placeholder diz {valor}"


class TestValidacaoApprise:
    """O campo avisa na hora quando o valor nao e postavel.

    Sem isto o erro e invisivel: o `requests` recusa `tgram://` dentro do
    guardian, a excecao vira uma linha no log do container e a tela segue
    mostrando a configuracao como se estivesse certa. Ver
    TestPlaceholderApprise para o lado do formato.
    """

    def _funcao(self):
        html = _read_static("index.html")
        m = re.search(r"function validarApprise\(\)\s*\{(.*?)\n\}", html, re.S)
        assert m, "validarApprise() nao encontrada"
        return m.group(1)

    def test_aceita_so_http_e_https(self):
        corpo = self._funcao()
        assert re.search(r"\^https\?:", corpo), \
            "a regra precisa ancorar no inicio e aceitar http e https"

    def test_campo_vazio_nao_e_erro(self):
        """Apprise e opcional: campo em branco significa sem notificacao."""
        corpo = self._funcao()
        assert re.search(r"if\s*\(\s*valor\s*&&", corpo), \
            "o ramo de erro precisa exigir valor — vazio nao e invalido"

    def test_marca_o_campo_e_avisa_o_leitor_de_tela(self):
        corpo = self._funcao()
        assert "classList.toggle('invalido'" in corpo
        assert "aria-invalid" in corpo, \
            "quem nao ve a borda vermelha precisa do estado no leitor de tela"

    def test_o_erro_nao_usa_o_mesmo_sinal_do_foco(self):
        """REGRESSAO: campo correto em foco parecia errado.

        `.field input:focus` ja e `outline:2px solid var(--accent)` — o mesmo
        vermelho, na tela inteira, desde o prototipo. Com outline no estado
        de erro, focar um campo certo acendia o aviso e um campo errado nao
        se distinguia de um campo em foco. O erro fala por dentro do campo e
        por uma linha de texto, que o foco nunca produz.
        """
        html = _read_static("index.html")
        m = re.search(r"\.field input\.invalido\s*\{([^}]*)\}", html)
        assert m, "falta o estilo do campo invalido"
        assert "outline" not in m.group(1), \
            "outline e o estilo de foco da tela — o erro precisa de outro sinal"
        assert "background" in m.group(1), \
            "sem fundo proprio, o campo invalido fica igual ao valido"

    def test_o_erro_tem_mensagem_visivel_no_formulario(self):
        """Cor sozinha nao diz o que fazer — e nao chega a quem nao a ve."""
        html = _read_static("index.html")
        assert 'id="erro_apprise"' in html, "falta o alvo da mensagem de erro"
        assert 'class="erro-campo"' in html
        assert 'role="alert"' in html, "o erro precisa ser anunciado"
        assert 'aria-describedby="erro_apprise"' in html, \
            "a mensagem precisa estar ligada ao campo"
        assert re.search(r"\.erro-campo:empty\s*\{[^}]*display:none", html), \
            "sem conteudo a mensagem nao pode ocupar espaco"

    def test_valida_ao_digitar_e_ao_carregar(self):
        html = _read_static("index.html")
        assert "validarApprise();" in html, "falta validar no carregamento"
        assert re.search(r"getElementById\('apprise_url'\)\s*\.addEventListener\('input', validarApprise\)",
                         html), "o aviso tem de aparecer enquanto se digita"

    @pytest.mark.parametrize("lang", ["pt-BR", "en-US"])
    @pytest.mark.parametrize("chave", ["erro_apprise_url", "erro_apprise_servico",
                                       "erro_apprise_formato"])
    def test_a_mensagem_existe_nos_dois_idiomas(self, lang, chave):
        assert chave in _i18n_tables()[lang]

    def test_url_de_servico_tem_erro_proprio(self):
        """`tgram://` e `slack://` nao sao "endereco invalido" qualquer.

        Sao o erro que o usuario comete copiando a documentacao do Apprise, e
        merecem a mensagem que diz para onde aquele valor realmente vai.
        """
        corpo = self._funcao()
        assert "erro_apprise_servico" in corpo and "erro_apprise_formato" in corpo, \
            "os dois casos precisam de mensagens distintas"
        assert re.search(r"\^\[a-z\]\[a-z0-9\+\.\\-\]\*:", corpo), \
            "falta reconhecer `esquema://` generico, nao so os esquemas conhecidos"

    def test_a_mensagem_do_campo_passa_pelo_walker(self):
        """Senao ela congela no idioma em que o erro apareceu."""
        corpo = self._funcao()
        assert "setAttribute('data-i18n'" in corpo
        assert "removeAttribute('data-i18n')" in corpo, \
            "o walker reescreveria uma mensagem ja apagada"

    def test_a_mensagem_diz_o_que_fazer(self):
        js = _read_static("i18n.js")
        for valor in re.findall(r"erro_apprise_url:\s*'([^']*)'", js):
            assert "/notify/" in valor, "a mensagem precisa mostrar o formato certo"
            assert "tgram" in valor, "e nomear o erro que ela esta corrigindo"

    def test_o_proprio_placeholder_passa_na_validacao(self):
        """O exemplo da tela nao pode ser marcado como invalido."""
        js = _read_static("i18n.js")
        for valor in re.findall(r"placeholder_apprise_url:\s*'([^']+)'", js):
            assert re.match(r"^https?://", valor), valor


class TestTourGuiado:
    """O passeio guiado roda em cima das telas de verdade.

    Essa e a razao de ele existir em vez de um prototipo a parte: nao ha
    segunda copia da interface para envelhecer. So que isso vale enquanto os
    alvos de cada passo continuarem existindo — um `id` renomeado na home
    deixaria o tour apontando para o nada, e em silencio, porque `tour.js`
    pula passo sem alvo em vez de travar a tela do usuario.
    """

    FASES = [("PASSOS_LOGIN", "login.html"), ("PASSOS_CONFIG", "index.html")]

    @pytest.mark.parametrize("lista,arquivo", FASES)
    def test_todo_alvo_existe_na_tela_da_fase(self, lista, arquivo):
        html = _read_static(arquivo)
        for alvo, chave in _passos_do_tour(lista):
            if alvo is None:
                continue
            assert _seletor_existe(alvo, html), \
                f"{lista}: o passo {chave} aponta para {alvo}, que nao esta em {arquivo}"

    @pytest.mark.parametrize("lista,_arquivo", FASES)
    def test_todo_passo_tem_texto_nos_dois_idiomas(self, lista, _arquivo):
        tables = _i18n_tables()
        for _alvo, chave in _passos_do_tour(lista):
            for lang in ("pt-BR", "en-US"):
                assert chave in tables[lang], f"{chave} falta na tabela {lang}"

    def test_a_fase_de_login_termina_na_tela_de_demonstracao(self):
        """Sem o `vai`, o tour pararia no botao de entrar."""
        src = _read_static("tour.js")
        assert "vai: PAGINA_CONFIG" in src, \
            "a fase de login nao encadeia na home de demonstracao"
        # O destino e computado porque os dois hosts escrevem o caminho
        # diferente — `/demo` no Flask, `demo.html` no bundle do Pages.
        assert "'demo.html' : 'demo'" in src, \
            "PAGINA_CONFIG deixou de cobrir os dois hosts"

    def test_nenhuma_chave_do_tour_ficou_orfa(self):
        """Chave sem uso volta para a tela no proximo copiar e colar."""
        usado = (_read_static("tour.js") + _read_static("index.html")
                 + _read_static("login.html"))
        for chave in _i18n_tables()["pt-BR"]:
            if chave.startswith(("tour_", "demo_")):
                assert chave in usado, f"{chave} nao e usada em lugar nenhum"

    def test_o_texto_do_passo_nao_fica_dentro_do_tour(self):
        """REGRESSAO: dica escrita no roteiro congela no idioma do autor.

        O tour precisa abrir em pt-BR ou en-US conforme a tela — por isso todo
        texto visivel sai de `t(chave)`, e o unico literal permitido e o
        comando de terminal, que nao se traduz.
        """
        src = _read_static("tour.js")
        m = re.search(r"var PASSOS_LOGIN = \[(.*?)var CSS", src, re.S)
        for bloco in re.findall(r"\{(.*?)\}", m.group(1), re.S):
            for campo, valor in re.findall(r"(\w+):\s*'([^']*)'", bloco):
                assert campo in ("alvo", "chave", "comando", "preenche", "vai"), \
                    f"campo inesperado no roteiro: {campo}"
                if campo in ("alvo", "chave", "vai", "preenche"):
                    continue
                assert campo == "comando", f"texto literal no roteiro: {valor!r}"

    def test_o_stub_de_demonstracao_recusa_escrita(self):
        """Em `/demo` nenhum POST pode chegar a API real."""
        src = _read_static("tour.js")
        assert "if (metodo !== 'GET')" in src, \
            "o stub de rede deixou de barrar metodo de escrita"
        assert "'api/demo-config'" in src, \
            "a tela de demonstracao precisa ler os valores da rota publica"

    def test_tour_js_carrega_antes_do_script_do_painel(self):
        """O stub tem que estar de pe antes do primeiro `/api/config`.

        O painel chama `loadConfig()` no fim do `<body>`. Com `tour.js` depois
        dele, a primeira requisicao escaparia para a API real e a tela de
        demonstracao abriria com 401 — ou, pior, com dado de verdade.
        """
        html = _read_static("index.html")
        assert html.index('src="tour.js"') < html.index("const API = 'api/config'")

    @pytest.mark.parametrize("arquivo", ["index.html", "login.html"])
    def test_as_duas_telas_oferecem_o_tour(self, arquivo):
        html = _read_static(arquivo)
        assert 'id="tour-link"' in html, f"{arquivo} nao oferece o passeio"
        assert "/login?tour=1" in html, \
            f"{arquivo}: o tour precisa comecar pela tela de login"

    def test_o_contador_e_do_passeio_inteiro(self):
        """REGRESSAO: a fase de login terminava em "3 de 3".

        O passeio tem duas telas e um numero so. Contado por fase, o login
        fechava como se fosse o fim e a configuracao recomecava do 1 — e o
        usuario via "3 de 3" num passo que ainda tinha onze pela frente.
        """
        src = _read_static("tour.js")
        assert "PASSOS_LOGIN.length + PASSOS_CONFIG.length" in src, \
            "o total voltou a ser o tamanho de uma fase so"
        assert "deslocamento() + indice + 1" in src, \
            "o passo atual precisa somar a fase anterior"

    def test_passo_que_encadeia_nao_oferece_fechar(self):
        """REGRESSAO: o ultimo passo do login dizia "Fechar".

        Fim da lista nao e fim do passeio quando o passo tem `vai`: ali o
        tour muda de tela. Oferecer "Fechar" encerrava na metade.
        """
        src = _read_static("tour.js")
        assert "indice === passos.length - 1 && !passo.vai" in src, \
            "o fim do passeio voltou a ser so o fim da lista"

    def test_o_que_o_tour_esconde_tem_regra_de_display(self):
        """REGRESSAO: `hidden` nao escondia a topbar em /demo.

        `[hidden]{display:none}` do navegador perde para o `display:flex` da
        classe — o mesmo motivo que ja obrigou `.modal-bg[hidden]` e
        `.rodape .atualizacao[hidden]` no index.html.
        """
        src = _read_static("tour.js")
        assert ".docs[hidden]" in src and ".user-btn[hidden]" in src, \
            "sem a regra, o botao de conta e o link do tour ficam visiveis em /demo"

    def test_troca_de_idioma_e_ouvida_na_bolha(self):
        """REGRESSAO: o balao redesenhava no idioma antigo.

        `setLang()` roda no listener do proprio `<select>`. Em captura, o
        tour corria antes dele e reescrevia o balao com a tabela anterior.
        """
        src = _read_static("tour.js")
        assert "document.addEventListener('change', aoTrocarIdioma);" in src, \
            "o listener de idioma voltou para a fase de captura"

    def test_o_destaque_abraca_o_tooltip_do_alvo(self):
        """REGRESSAO: o balao cobria a lista de variaveis que explicava.

        O tooltip e maior que o botao `{ }` e cresce para fora dele. Sem
        soma-lo ao retangulo do passo, o balao escolhia um lado que passava
        por cima justamente do que o passo mandava olhar.
        """
        src = _read_static("tour.js")
        assert 'querySelector(\'[role="tooltip"]\')' in src, \
            "o retangulo do passo voltou a ignorar o tooltip aberto"
        corpo = re.search(r"function retanguloDeReferencia.*?\n  \}", src, re.S).group(0)
        codigo = re.sub(r"//.*", "", corpo)
        assert "getComputedStyle" not in codigo, \
            ("o tooltip abre por transicao e ainda esta `hidden` na hora da "
             "conta — a area e que vale, nao o estilo computado")

    def test_o_link_do_painel_abre_em_outra_aba_com_seguranca(self):
        """O painel fica aberto atras: o passeio nao rouba a aba de trabalho."""
        html = _read_static("index.html")
        m = re.search(r'<a class="docs tour"[^>]*>', html, re.S)
        assert m, "link do tour nao encontrado na topbar"
        tag = m.group(0)
        assert 'target="_blank"' in tag, tag
        assert "noopener" in tag, tag


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


class TestApiVersion:
    """/api/version alimenta o rodape da Web UI."""

    def test_retorna_a_versao_do_codigo(self, client, tmp_config):
        r = client.get("/api/version")
        assert r.status_code == 200
        assert r.get_json()["version"] == APP_VERSION

    def test_exige_autenticacao(self, client, tmp_config):
        """A versao exata nao e informacao para quem nao esta logado."""
        cfg = g.load_config()
        cfg["webui"] = {"user": "admin", "password": "secreta"}
        g.save_config(cfg)
        assert client.get("/api/version").status_code == 401

        auth = base64.b64encode(b"admin:secreta").decode()
        r = client.get("/api/version", headers={"Authorization": f"Basic {auth}"})
        assert r.status_code == 200

    def test_health_continua_sem_versao(self, client, tmp_config):
        """O /api/health e publico — nao deve vazar a versao."""
        dados = client.get("/api/health").get_json()
        assert "version" not in dados


class TestChecagemDeVersao:
    """Comparacao com a ultima tag publicada — o que alimenta o aviso."""

    @pytest.fixture(autouse=True)
    def _cache_limpo(self):
        u.limpar_cache()
        yield
        u.limpar_cache()

    @pytest.mark.parametrize("instalada,publicada,espera", [
        ("2.4.0", "2.5.0", True),
        ("2.4.0", "2.4.1", True),
        ("2.4.0", "2.4.0", False),
        ("2.4.0", "2.0.5", False),      # repo parou de taguear: nao e downgrade
        ("2.9.0", "2.10.0", True),      # texto diria que 2.10.0 < 2.9.0
        ("2.4.0+a81f306", "2.4.0", False),  # sufixo de build nao conta
        ("2.4.0", None, False),         # consulta falhou
        ("2.4.0", "nightly", False),
    ])
    def test_compara_por_numero_nao_por_texto(self, instalada, publicada, espera):
        assert u.ha_atualizacao(instalada, publicada) is espera

    def test_maior_tag_ignora_o_que_nao_e_versao(self):
        tags = [{"name": "v2.0.5"}, {"name": "nightly"}, {"name": "v2.10.0"},
                {"name": "v2.9.0"}]
        assert u._maior_tag(tags) == "2.10.0"

    def test_sem_tag_valida_devolve_none(self):
        assert u._maior_tag([{"name": "nightly"}]) is None

    def test_erro_de_rede_vira_desconhecido(self):
        """Painel de homelab abre sem internet: falha nao pode virar erro."""
        with mock.patch.object(u.requests, "get",
                               side_effect=requests.exceptions.ConnectionError("refused")):
            assert u.ultima_versao() is None

    def test_http_de_erro_vira_desconhecido(self):
        resp = mock.Mock(status_code=403)
        with mock.patch.object(u.requests, "get", return_value=resp):
            assert u.ultima_versao() is None

    def test_cache_evita_consulta_a_cada_pagina(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = [{"name": "v2.5.0"}]
        with mock.patch.object(u.requests, "get", return_value=resp) as m:
            assert u.ultima_versao() == "2.5.0"
            assert u.ultima_versao() == "2.5.0"
            assert m.call_count == 1, "consultou a API duas vezes"

    def test_cache_expira(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = [{"name": "v2.5.0"}]
        with mock.patch.object(u.requests, "get", return_value=resp) as m:
            u.ultima_versao(agora=1000.0)
            u.ultima_versao(agora=1000.0 + u.TTL_SEGUNDOS + 1)
            assert m.call_count == 2

    def test_desconhecido_tambem_fica_em_cache(self):
        """Senao uma caixa offline paga o timeout a cada carregamento."""
        with mock.patch.object(u.requests, "get",
                               side_effect=requests.exceptions.Timeout("t")) as m:
            assert u.ultima_versao() is None
            assert u.ultima_versao() is None
            assert m.call_count == 1

    def test_consulta_tem_timeout(self):
        """Sem timeout, a API fora do ar trava o carregamento do painel."""
        resp = mock.Mock(status_code=200)
        resp.json.return_value = []
        with mock.patch.object(u.requests, "get", return_value=resp) as m:
            u.ultima_versao()
            assert m.call_args.kwargs.get("timeout") == u.TIMEOUT


class TestChecagemPeriodicaDeVersao:
    """O aviso nao pode depender de alguem abrir o painel.

    Antes a consulta era so sob demanda, com cache de 6h em memoria. Quem
    estivesse com a tela aberta quando saisse uma versao nova nao via nada: o
    F5 batia no cache ainda valido, e o unico jeito de zera-lo era reiniciar o
    container — de onde vinha a impressao de que a checagem "so funciona
    quando o server inicia".

    O conserto tem duas pernas, com validades diferentes de proposito: a
    thread periodica (6h) para quem nao esta olhando, e a revalidacao curta
    (10min) no `/api/version` para quem esta.
    """

    @pytest.fixture(autouse=True)
    def _cache_limpo(self):
        u.limpar_cache()
        u._parar_checagem.set()
        yield
        u._parar_checagem.set()
        u.limpar_cache()

    def test_a_validade_da_pagina_e_menor_que_a_do_ciclo(self):
        """Se forem iguais, o refresh volta a nao adiantar nada."""
        assert u.TTL_PAGINA < u.TTL_SEGUNDOS
        assert u.TTL_PAGINA > 0, "zero faria cada F5 bater na API do GitHub"

    def test_o_teto_de_consultas_cabe_no_limite_do_github(self):
        """Sem autenticacao sao 60 req/h por IP; o piso curto nao pode furar."""
        por_hora = 3600 / u.TTL_PAGINA + 3600 / u.TTL_SEGUNDOS
        assert por_hora <= 30, f"{por_hora:.0f} consultas/h e perto demais do limite"

    def test_pagina_revalida_antes_do_ttl_longo(self):
        """Cache de 1h: o ciclo de 6h aceitaria, a pagina nao."""
        resp = mock.Mock(status_code=200)
        resp.json.return_value = [{"name": "v2.5.0"}]
        with mock.patch.object(u.requests, "get", return_value=resp) as m:
            u.ultima_versao(agora=1000.0)
            assert m.call_count == 1
            # Uma hora depois: dentro do TTL do ciclo, fora do da pagina.
            u.ultima_versao(agora=1000.0 + 3600, validade=u.TTL_PAGINA)
            assert m.call_count == 2, "o refresh precisa revalidar"
            u.ultima_versao(agora=1000.0 + 3600)
            assert m.call_count == 2, "o ciclo longo ainda aceita o cache"

    def test_dentro_da_validade_curta_o_cache_vale(self):
        """F5 em sequencia nao pode virar rajada na API."""
        resp = mock.Mock(status_code=200)
        resp.json.return_value = [{"name": "v2.5.0"}]
        with mock.patch.object(u.requests, "get", return_value=resp) as m:
            for i in range(5):
                u.ultima_versao(agora=1000.0 + i, validade=u.TTL_PAGINA)
            assert m.call_count == 1

    def test_validade_zero_sempre_consulta(self):
        """E o que o ciclo usa: ele renova o cache, nao le dele."""
        resp = mock.Mock(status_code=200)
        resp.json.return_value = [{"name": "v2.5.0"}]
        with mock.patch.object(u.requests, "get", return_value=resp) as m:
            u.ultima_versao(agora=1000.0, validade=0)
            u.ultima_versao(agora=1000.0, validade=0)
            assert m.call_count == 2

    def test_o_ciclo_consulta_antes_de_esperar(self):
        """Checa no start: o primeiro carregamento ja encontra o dado quente."""
        chamadas = []
        with mock.patch.object(u, "ultima_versao",
                               side_effect=lambda **kw: chamadas.append(kw)), \
             mock.patch.object(u._parar_checagem, "wait", return_value=True):
            u._loop_de_checagem(intervalo=1)
        assert chamadas == [{"validade": 0}], \
            "o ciclo precisa forcar a consulta, nao reaproveitar o cache"

    def test_o_ciclo_espera_o_intervalo_configurado(self):
        with mock.patch.object(u, "ultima_versao", return_value="2.5.0"), \
             mock.patch.object(u._parar_checagem, "wait", return_value=True) as m:
            u._loop_de_checagem(intervalo=42)
        assert m.call_args.args[0] == 42

    def test_o_ciclo_usa_seis_horas_por_padrao(self):
        with mock.patch.object(u, "ultima_versao", return_value="2.5.0"), \
             mock.patch.object(u._parar_checagem, "wait", return_value=True) as m:
            u._loop_de_checagem()
        assert m.call_args.args[0] == u.TTL_SEGUNDOS == 6 * 3600

    def test_falha_na_consulta_nao_mata_o_ciclo(self):
        """Sem isto o aviso volta a depender de visita, e em silencio."""
        tentativas = []

        def explode(**kw):
            tentativas.append(kw)
            raise RuntimeError("API fora do ar")

        with mock.patch.object(u, "ultima_versao", side_effect=explode), \
             mock.patch.object(u._parar_checagem, "wait",
                               side_effect=[False, True]) as m:
            u._loop_de_checagem(intervalo=1)
        assert len(tentativas) == 2, "o ciclo parou na primeira falha"
        assert m.call_count == 2

    def test_o_evento_de_parada_encerra_o_ciclo(self):
        with mock.patch.object(u, "ultima_versao", return_value="2.5.0"), \
             mock.patch.object(u._parar_checagem, "wait", return_value=True):
            u._loop_de_checagem(intervalo=1)   # retorna sem pendurar

    def test_iniciar_sobe_thread_daemon(self):
        with mock.patch.object(u, "_loop_de_checagem") as alvo:
            t = u.iniciar_checagem_periodica(intervalo=1)
            t.join(timeout=2)
        assert t.daemon, "thread nao-daemon seguraria o shutdown do container"
        assert alvo.called

    def test_iniciar_limpa_o_sinal_de_parada(self):
        """Senao um ciclo anterior encerrado deixa o novo morrer na 1a espera."""
        u._parar_checagem.set()
        with mock.patch.object(u, "_loop_de_checagem"):
            u.iniciar_checagem_periodica(intervalo=1).join(timeout=2)
        assert not u._parar_checagem.is_set()

    def test_o_entrypoint_sobe_a_checagem(self):
        """De nada adianta a thread existir se ninguem a inicia."""
        fonte = open(os.path.join(REPO_ROOT, "app", "main.py"), encoding="utf-8").read()
        assert "iniciar_checagem_periodica()" in fonte, \
            "main.py nao sobe a checagem periodica"

    def test_a_api_pede_a_validade_curta(self):
        fonte = open(os.path.join(REPO_ROOT, "app", "web.py"), encoding="utf-8").read()
        assert "ultima_versao(validade=updates.TTL_PAGINA)" in fonte, \
            "/api/version voltou a aceitar o cache de 6h"


class TestApiVersionAtualizacao:
    """/api/version entrega o veredito pronto para o rodape."""

    @pytest.fixture(autouse=True)
    def _cache_limpo(self):
        u.limpar_cache()
        yield
        u.limpar_cache()

    def test_anuncia_versao_nova(self, client, tmp_config):
        with mock.patch.object(u, "ultima_versao", return_value="99.0.0"):
            dados = client.get("/api/version").get_json()
        assert dados["latest"] == "99.0.0"
        assert dados["update_available"] is True

    def test_em_dia_nao_anuncia(self, client, tmp_config):
        with mock.patch.object(u, "ultima_versao", return_value=APP_VERSION):
            dados = client.get("/api/version").get_json()
        assert dados["update_available"] is False

    def test_sem_internet_responde_200(self, client, tmp_config):
        """Nao saber nao e erro: o painel carrega igual."""
        with mock.patch.object(u, "ultima_versao", return_value=None):
            r = client.get("/api/version")
        assert r.status_code == 200
        assert r.get_json()["latest"] is None
        assert r.get_json()["update_available"] is False


class TestWebUIRodape:
    """Rodape mostra a versao instalada, vinda do backend."""

    def test_rodape_existe_centralizado(self):
        html = _read_static("index.html")
        assert re.search(r'<footer class="rodape">', html), "sem rodape no HTML"
        assert re.search(r"\.rodape\s*\{[^}]*text-align:center", html), \
            "rodape sem centralizacao no CSS"

    def test_rodape_tem_o_alvo_da_versao(self):
        html = _read_static("index.html")
        assert 'id="app-version"' in html

    def test_rodape_busca_a_versao_na_api(self):
        html = _read_static("index.html")
        assert "const VERSION_API = 'api/version';" in html, \
            "o HTML nao consome api/version"
        assert "loadVersion()" in html, "loadVersion nunca e chamada"

    def test_versao_nao_esta_escrita_no_html(self):
        """Numero no HTML seria uma copia a mais para sair de sincronia."""
        html = _read_static("index.html")
        assert APP_VERSION not in html, \
            f"versao {APP_VERSION} hardcoded no HTML — deve vir de /api/version"

    def test_aviso_de_versao_nova_existe_escondido(self):
        """Nasce `hidden`: so aparece quando o backend disser que ha versao nova."""
        html = _read_static("index.html")
        aviso = re.search(r'<a class="atualizacao" id="app-update"[^>]*>', html)
        assert aviso, "sem o elemento do aviso de atualizacao"
        assert "hidden" in aviso.group(0)

    def test_aviso_fica_ao_lado_da_versao(self):
        html = _read_static("index.html")
        rodape = re.search(r"<footer class=\"rodape\">(.*?)</footer>", html, re.S)
        assert rodape, "sem rodape"
        assert rodape.group(1).index('id="app-version"') < \
            rodape.group(1).index('id="app-update"'), \
            "o aviso precisa vir depois da versao instalada"

    def test_aviso_depende_do_veredito_do_backend(self):
        html = _read_static("index.html")
        assert "dados.update_available" in html, \
            "o HTML decide sozinho se ha atualizacao em vez de usar o backend"

    def test_aviso_tem_traducao_nos_dois_idiomas(self):
        tables = _i18n_tables()
        for lang, known in tables.items():
            assert "update_available" in known, f"{lang} sem update_available"
            assert "update_tooltip" in known, f"{lang} sem update_tooltip"

    def test_aviso_passa_pelo_walker_do_i18n(self):
        """Regressao: texto escrito na mao congela no idioma do 1o carregamento.

        `setLang()` re-renderiza sem recarregar a pagina e so alcanca quem tem
        `data-i18n*`. Quem escreve `textContent`/`title` por fora continua em
        ingles depois de trocar para pt-BR — foi o que aconteceu.
        """
        html = _read_static("index.html")
        aviso = re.search(r'<a class="atualizacao"[^>]*>', html, re.S).group(0)
        assert 'data-i18n="update_available"' in aviso, \
            "texto do aviso fora do walker: congela ao trocar de idioma"
        assert 'data-i18n-title="update_tooltip"' in aviso, \
            "tooltip do aviso fora do walker: congela ao trocar de idioma"
        assert "t('update_available')" not in html, \
            "aviso ainda escreve o texto na mao em paralelo ao walker"

    def test_aviso_re_renderiza_ao_receber_a_versao(self):
        """O walker precisa rodar depois que o data-version chega.

        Delimita pela funcao inteira, e nao por uma janela de N caracteres:
        janela fixa quebra quando se acrescenta uma linha ao bloco, que e
        fragilidade do teste e nao do codigo.
        """
        html = _read_static("index.html")
        corpo = html[html.index("async function loadVersion()"):]
        corpo = corpo[:corpo.index("\n}")]
        assert "data-version" in corpo
        assert "applyTranslations()" in corpo, \
            "sem re-render, o aviso aparece com o placeholder {version} cru"
        assert corpo.index("data-version") < corpo.index("applyTranslations()"), \
            "re-render antes do valor chegar deixaria o placeholder cru"

    def test_walker_preenche_placeholder(self):
        """`{version}` so chega ao usuario se o walker souber substituir."""
        js = _read_static("i18n.js")
        assert "_fillVars" in js, "walker sem substituicao de placeholder"
        assert r"\{(\w+)\}" in js, "sem a regex de placeholder no i18n.js"

    def test_strings_do_aviso_tem_o_placeholder(self):
        """Traducao sem `{version}` viraria aviso sem numero de versao."""
        js = _read_static("i18n.js")
        for linha in re.findall(r"update_available: '([^']*)'", js):
            assert "{version}" in linha, f"traducao sem placeholder: {linha!r}"

    def test_aviso_fica_realmente_escondido(self):
        """Regressao: o aviso aparecia sempre, com o `{version}` cru na tela.

        O atributo `hidden` so esconde por causa da regra `[hidden]{display:none}`
        do navegador, que perde para qualquer `display:` declarado na folha. Com
        `display:inline-block` e sem guarda, o elemento fica visivel — e o
        applyTranslations() escreve nele mesmo escondido, entao o placeholder
        sem `data-version` vai para a tela.
        """
        html = _read_static("index.html")
        assert re.search(r"\.atualizacao\[hidden\]\s*\{[^}]*display:\s*none", html), \
            "sem guarda [hidden]: o aviso aparece mesmo sem atualizacao"

    def test_classe_com_display_usada_com_hidden_tem_guarda(self):
        """A mesma armadilha para qualquer elemento que nasca `hidden`.

        O `.modal-bg[hidden]` ja existia no arquivo pelo mesmo motivo; este
        teste impede que o proximo elemento escondido repita o erro.
        """
        html = _read_static("index.html")
        classes = set()
        for tag in re.findall(r"<[a-z]+[^>]*\bhidden\b[^>]*>", html):
            achado = re.search(r'class="([^"]+)"', tag)
            if achado:
                classes.update(achado.group(1).split())
        assert classes, "nenhum elemento hidden com classe — seletor desatualizado?"

        for classe in sorted(classes):
            escapada = re.escape(classe)
            define_display = re.search(
                r"\.%s\b[^{]*\{[^}]*display:" % escapada, html)
            if not define_display:
                continue
            guarda = re.search(
                r"\.%s\[hidden\]\s*\{[^}]*display:\s*none" % escapada, html)
            assert guarda, (
                f".{classe} declara display e e usada com o atributo hidden, "
                f"mas nao tem a guarda .{classe}[hidden]")

    def test_link_do_aviso_leva_as_notas_da_versao(self):
        """Fallback na lista de releases; com a versao em maos, a release dela."""
        html = _read_static("index.html")
        aviso = re.search(r'<a class="atualizacao"[^>]*>', html, re.S).group(0)
        assert "/releases" in aviso, "link do aviso nao leva aos releases"
        assert "RELEASES_URL + '/tag/v' + dados.latest" in html, \
            "o aviso nao aponta para as notas da versao disponivel"

    def test_link_do_aviso_abre_com_seguranca(self):
        """target=_blank sem rel deixa a aba nova com acesso a window.opener."""
        html = _read_static("index.html")
        aviso = re.search(r'<a class="atualizacao"[^>]*>', html, re.S).group(0)
        assert 'target="_blank"' in aviso
        assert "noopener" in aviso


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
        i = html.find(f'<div class="msg" id="msg_{ev}_wrap">')
        assert i >= 0, f"bloco de {ev} nao encontrado"
        corpo = _bloco_balanceado(html, i)
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
        assert "const DEFAULTS_API = 'api/defaults';" in html

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


# ── Contrato HTTP com o qBittorrent ────────────────────────────────────

class _FakeResponse:
    """Resposta HTTP minima, com raise_for_status fiel ao requests."""

    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = [] if payload is None else payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class _FakeQbitSession:
    """Session falsa que registra cada chamada HTTP.

    Os quatro wrappers da API do qBit eram sempre substituidos INTEIROS nos
    testes (`mock.patch.object(g, "get_torrents")`), entao o corpo deles nunca
    executava: URL, params, timeout e header de autenticacao nao tinham
    verificacao nenhuma. E a mesma classe de buraco que deixou a escala de
    prioridade errada chegar em producao.
    """

    def __init__(self, respostas=None):
        self.verify = True
        self.headers = {}
        self.calls = []
        self._respostas = respostas or {}

    def _registra(self, metodo, url, kwargs):
        self.calls.append({"method": metodo, "url": url, **kwargs})
        return self._respostas.get(url, _FakeResponse())

    def get(self, url, **kwargs):
        return self._registra("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._registra("POST", url, kwargs)


QBIT_URL = "https://torrent.home.arpa/"
QBIT_BASE = "https://torrent.home.arpa"
QBIT_KEY = "chave-secreta-do-qbit"


@contextlib.contextmanager
def _qbit_http(respostas=None):
    """Monta a sessao real do guardian sobre uma Session falsa."""
    g.load_config()
    cfg = g.get_config()
    cfg["qbit"]["url"] = QBIT_URL
    cfg["qbit"]["api_key"] = QBIT_KEY
    g.save_config(cfg)
    g._qbit_session = None
    g._qbit_base = None

    sess = _FakeQbitSession(respostas)
    with mock.patch.object(g.requests, "Session", return_value=sess):
        yield sess


class TestQbitHttpContract:
    """Corpo real de qbit_login/get_torrents/get_files/remove_torrent.

    Cobre o contrato com a API do qBittorrent: endpoint, forma do payload,
    timeout e tratamento de status — tudo que ficava invisivel enquanto os
    testes substituiam a funcao inteira.
    """

    def test_login_consulta_app_version(self, tmp_config):
        url = f"{QBIT_BASE}/api/v2/app/version"
        with _qbit_http({url: _FakeResponse(200, "v4.6.0")}) as sess:
            g.qbit_login()

        assert sess.calls == [{"method": "GET", "url": url, "timeout": 10}]

    @pytest.mark.parametrize("status", [401, 403, 404, 500, 502])
    def test_login_falha_levanta_runtime_error(self, status, tmp_config):
        """Credencial errada ou qBit quebrado NAO pode passar em silencio.

        O retorno de qbit_login e o que faz guardian_loop entrar em retry; um
        login que "da certo" com HTTP 403 deixaria o loop rodando contra um
        qBit que recusa tudo.
        """
        url = f"{QBIT_BASE}/api/v2/app/version"
        with _qbit_http({url: _FakeResponse(status, "Forbidden")}):
            with pytest.raises(RuntimeError) as exc:
                g.qbit_login()

        assert str(status) in str(exc.value)

    def test_get_torrents_endpoint_e_payload(self, tmp_config):
        url = f"{QBIT_BASE}/api/v2/torrents/info"
        payload = [{"hash": "abc", "name": "Filme"}]
        with _qbit_http({url: _FakeResponse(200, payload=payload)}) as sess:
            assert g.get_torrents() == payload

        assert sess.calls == [{"method": "GET", "url": url, "timeout": 10}]

    def test_get_torrents_propaga_erro_http(self, tmp_config):
        """raise_for_status e o que converte 5xx em erro de transporte.

        Sem ele, get_torrents devolveria o JSON de erro como se fosse a lista
        de torrents e o loop trataria zero torrents como estado normal.
        """
        url = f"{QBIT_BASE}/api/v2/torrents/info"
        with _qbit_http({url: _FakeResponse(503, "unavailable")}):
            with pytest.raises(requests.exceptions.HTTPError):
                g.get_torrents()

    def test_get_files_manda_hash_em_params(self, tmp_config):
        """O hash vai em params, nao concatenado na URL (evita quebra de escape)."""
        url = f"{QBIT_BASE}/api/v2/torrents/files"
        torrent_hash = "a1b2c3d4e5f6"
        payload = [{"name": "ep.mkv", "index": 0}]
        with _qbit_http({url: _FakeResponse(200, payload=payload)}) as sess:
            assert g.get_files(torrent_hash) == payload

        assert sess.calls == [{"method": "GET", "url": url,
                               "params": {"hash": torrent_hash}, "timeout": 10}]
        assert torrent_hash not in sess.calls[0]["url"]

    def test_get_files_propaga_erro_http(self, tmp_config):
        url = f"{QBIT_BASE}/api/v2/torrents/files"
        with _qbit_http({url: _FakeResponse(404, "not found")}):
            with pytest.raises(requests.exceptions.HTTPError):
                g.get_files("hash-inexistente")

    def test_remove_torrent_apaga_arquivos(self, tmp_config):
        """deleteFiles=true e o que diferencia remover de apenas destorrentar.

        Sem essa flag o conteudo perigoso continuaria no disco depois da
        "remocao" — que e justamente o que o guardian existe para evitar.
        """
        url = f"{QBIT_BASE}/api/v2/torrents/delete"
        with _qbit_http() as sess:
            g.remove_torrent("hash-ruim")

        assert sess.calls == [{"method": "POST", "url": url,
                               "data": {"hashes": "hash-ruim",
                                        "deleteFiles": "true"},
                               "timeout": 10}]

    def test_api_key_vai_no_header_bearer(self, tmp_config):
        with _qbit_http({f"{QBIT_BASE}/api/v2/app/version":
                         _FakeResponse(200, "v4.6.0")}) as sess:
            g.qbit_login()

        assert sess.headers == {"Authorization": f"Bearer {QBIT_KEY}"}

    def test_api_key_nunca_vaza_para_url_ou_corpo(self, tmp_config):
        """A chave so pode viajar no header.

        Em query string ela entraria no log de acesso do reverse proxy e no
        historico do navegador; no corpo, em qualquer dump de requisicao.
        """
        with _qbit_http({f"{QBIT_BASE}/api/v2/app/version":
                         _FakeResponse(200, "v4.6.0")}) as sess:
            g.qbit_login()
            g.get_torrents()
            g.get_files("hash1")
            g.remove_torrent("hash1")
            g.set_file_priority("hash1", 0, 7)

        assert len(sess.calls) == 5
        for call in sess.calls:
            visivel = " ".join(str(call.get(k, "")) for k in ("url", "params", "data"))
            assert QBIT_KEY not in visivel, f"api_key exposta em {call['url']}"

    def test_todas_as_chamadas_tem_timeout(self, tmp_config):
        """Sem timeout, uma chamada pendurada congela a thread do guardian.

        E o timeout tambem e o que transforma um qBit mudo em Timeout —
        exatamente a excecao que TRANSPORT_ERRORS usa para reconectar.
        """
        with _qbit_http({f"{QBIT_BASE}/api/v2/app/version":
                         _FakeResponse(200, "v4.6.0")}) as sess:
            g.qbit_login()
            g.get_torrents()
            g.get_files("hash1")
            g.remove_torrent("hash1")
            g.set_file_priority("hash1", 0, 7)

        assert [c.get("timeout") for c in sess.calls] == [10] * 5


# ── Contagem do pass 2 (stalled removidos) ─────────────────────────────

class TestPassDoisContagem:
    """O numero de removidos no pass 2 e reportado, nunca so contado.

    O incremento `stalled_removed += 1` nunca executava em teste: nenhum caso
    chegava a remover de verdade no pass 2. Um off-by-one aqui mente no log e
    na resposta do /api/trigger sem quebrar nada.
    """

    TORRENTS = [{"hash": "a", "name": "A"},
                {"hash": "b", "name": "B"},
                {"hash": "c", "name": "C"}]

    def test_trigger_reporta_quantos_foram_removidos(self, client, tmp_config):
        removidos = {"b", "c"}
        with mock.patch.object(g, "get_torrents", return_value=self.TORRENTS), \
             mock.patch.object(g, "analyze_torrent", return_value=True), \
             mock.patch.object(g, "check_stalled_and_remove",
                               side_effect=lambda t: t["hash"] in removidos):
            r = client.post("/api/trigger")

        assert r.status_code == 200
        corpo = r.get_json()
        assert corpo["stalled_removed"] == 2
        assert corpo["checked"] == 3
        assert corpo["new"] == 3

    def test_trigger_reporta_zero_quando_nada_removido(self, client, tmp_config):
        with mock.patch.object(g, "get_torrents", return_value=self.TORRENTS), \
             mock.patch.object(g, "analyze_torrent", return_value=True), \
             mock.patch.object(g, "check_stalled_and_remove", return_value=False):
            r = client.post("/api/trigger")

        assert r.get_json()["stalled_removed"] == 0

    def test_pass_dois_avalia_torrents_ja_processados(self, client, tmp_config):
        """O pass 2 roda sobre TODOS os torrents, nao so os novos.

        Era o bug original: um torrent ja em _processed que ficava stalled
        depois nunca mais era reavaliado.
        """
        g._processed.update({"a", "b", "c"})
        avaliados = []
        with mock.patch.object(g, "get_torrents", return_value=self.TORRENTS), \
             mock.patch.object(g, "analyze_torrent", return_value=True), \
             mock.patch.object(g, "check_stalled_and_remove",
                               side_effect=lambda t: avaliados.append(t["hash"])):
            r = client.post("/api/trigger")

        assert r.get_json()["new"] == 0
        assert avaliados == ["a", "b", "c"]


# ── reavaliacao periodica em modo webhook ──────────────────────────────

class TestReavaliacaoPeriodica:
    """O modo webhook tambem precisa reavaliar stalled sozinho.

    Era o furo: o Pass 2 rodava no ciclo completo e dentro de /api/trigger, e
    o trigger e disparado pelo hook do qBittorrent ao ADICIONAR torrent. Com
    `check_interval_seconds: 0` e nenhum torrent novo entrando, um torrent que
    ficava stalled nunca era reavaliado — ficava parado indefinidamente,
    independente do limiar configurado.
    """

    TORRENTS = [{"hash": "a", "name": "A"}, {"hash": "b", "name": "B"}]

    def test_modo_webhook_sobe_o_loop_de_reavaliacao(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["check_interval_seconds"] = 0
        g.save_config(cfg)
        with mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "write_heartbeat"), \
             mock.patch.object(g, "_start_reevaluate_loop") as m_loop:
            g.guardian_loop()
        assert m_loop.called, "modo webhook deve subir a reavaliacao periodica"

    def test_ciclo_avalia_stalled_em_todos_e_conta(self, tmp_config):
        avaliados = []

        def fake(t):
            avaliados.append(t["hash"])
            return t["hash"] == "b"

        g._processed.update({"a", "b"})
        with mock.patch.object(g, "get_torrents", return_value=self.TORRENTS), \
             mock.patch.object(g, "check_stalled_and_remove", side_effect=fake):
            r = g.executar_ciclo()
        assert r["removidos"] == 1
        assert avaliados == ["a", "b"]

    def test_ciclo_reanalisa_pendentes_ate_os_metadados_chegarem(self, tmp_config):
        """A fila de pendentes e o complemento de `_processed`.

        O qBittorrent nao busca metadados de torrent enfileirado: com
        `MaxActiveDownloads` baixo, um torrent fica em `queuedDL` sem arquivo
        nenhum e so ganha metadados quando chega a vez dele. Se o ciclo nao
        voltar nele, a prioridade dos arquivos nunca e aplicada — foi o que
        aconteceu em producao, com os `.mkv` ficando em `priority=1` em vez do
        `priority_media=7` configurado.
        """
        g._processed.clear()
        tentativas = []
        # recusa na primeira passada (sem metadados), aceita na segunda
        def fake_analyze(t):
            tentativas.append(t["hash"])
            return tentativas.count(t["hash"]) > 1

        with mock.patch.object(g, "get_torrents", return_value=self.TORRENTS), \
             mock.patch.object(g, "check_stalled_and_remove", return_value=False), \
             mock.patch.object(g, "analyze_torrent", side_effect=fake_analyze):
            r1 = g.executar_ciclo()
            assert r1["pendentes"] == 2 and r1["analisados"] == 0
            assert r1["restantes"] == 2, "sem metadados segue pendente"

            r2 = g.executar_ciclo()
            assert r2["pendentes"] == 2, "voltou a tentar os mesmos dois"
            assert r2["analisados"] == 2 and r2["restantes"] == 0

            r3 = g.executar_ciclo()
            assert r3["pendentes"] == 0, "fila drenada: ninguem mais e reanalisado"

        assert tentativas == ["a", "b", "a", "b"]

    def test_ciclo_com_fila_vazia_nao_chama_analyze(self, tmp_config):
        """Fila drenada: o pass 1 nao gasta requisicao nenhuma."""
        g._processed.update({"a", "b"})
        with mock.patch.object(g, "get_torrents", return_value=self.TORRENTS), \
             mock.patch.object(g, "check_stalled_and_remove", return_value=False), \
             mock.patch.object(g, "analyze_torrent") as m_an:
            r = g.executar_ciclo()
        assert not m_an.called
        assert r["pendentes"] == 0 and r["analisados"] == 0

    def test_ciclo_aceita_torrents_ja_obtidos(self, tmp_config):
        """Chamador que ja tem a lista nao paga um segundo get_torrents."""
        g._processed.update({"a", "b"})
        with mock.patch.object(g, "get_torrents") as m_get, \
             mock.patch.object(g, "check_stalled_and_remove", return_value=False):
            r = g.executar_ciclo(torrents=self.TORRENTS)
        assert not m_get.called
        assert r["total"] == 2

    def test_intervalo_le_config_e_aceita_zero(self, tmp_config):
        cfg = g.load_config()
        cfg["guardian"]["reevaluate_interval_seconds"] = 90
        assert g._reevaluate_interval(cfg) == 90
        cfg["guardian"]["reevaluate_interval_seconds"] = 0
        assert g._reevaluate_interval(cfg) == 0
        cfg["guardian"]["reevaluate_interval_seconds"] = "nao-numero"
        assert g._reevaluate_interval(cfg) == 300, "valor invalido cai no default"

    # ── cache de config: invalidacao por mtime ─────────────────────────

    def test_get_config_serve_cache_enquanto_o_arquivo_nao_muda(self, tmp_config):
        """O caminho quente nao pode reler o JSON a cada chamada.

        `get_config()` e chamado uma vez por torrent em `analyze_torrent` e
        `is_stalled`. Com o arquivo parado, o custo precisa ser so o `stat` da
        checagem de mtime — nunca abrir e parsear o arquivo.
        """
        g.load_config()
        with mock.patch.object(g, "load_config") as m_load:
            for _ in range(5):
                g.get_config()
        assert not m_load.called, "arquivo parado nao deve disparar releitura"

    def test_get_config_recarrega_quando_o_arquivo_muda_por_fora(self, tmp_config):
        """Edicao fora da Web UI passa a valer sem restart.

        Era o defeito: `get_config()` devolvia o cache e so tocava o disco com
        `_config is None`, entao editar o `config.json` na mao nao surtia efeito
        nenhum ate reiniciar o container. Mudanca pela Web UI funcionava porque
        `save_config` atualiza o cache — o que escondia o problema.
        """
        cfg = g.load_config()
        cfg["guardian"]["reevaluate_interval_seconds"] = 300
        g.save_config(cfg)
        assert g.get_config()["guardian"]["reevaluate_interval_seconds"] == 300

        # edicao externa: escreve direto no arquivo, sem passar por save_config
        with open(g.CONFIG_PATH) as f:
            bruto = json.load(f)
        bruto["guardian"]["reevaluate_interval_seconds"] = 7
        with open(g.CONFIG_PATH, "w") as f:
            json.dump(bruto, f)
        os.utime(g.CONFIG_PATH, (0, 0))   # mtime distinto, sem depender da resolucao do FS

        assert g.get_config()["guardian"]["reevaluate_interval_seconds"] == 7, \
            "mudanca no arquivo precisa ser vista sem restart"

    def test_loop_ve_intervalo_alterado_por_fora(self, tmp_config):
        """O loop encerra ao ler do arquivo um intervalo 0 que o cache nao tinha."""
        cfg = g.load_config()
        cfg["guardian"]["reevaluate_interval_seconds"] = 300
        g.save_config(cfg)

        with open(g.CONFIG_PATH) as f:
            bruto = json.load(f)
        bruto["guardian"]["reevaluate_interval_seconds"] = 0
        with open(g.CONFIG_PATH, "w") as f:
            json.dump(bruto, f)
        os.utime(g.CONFIG_PATH, (0, 0))

        with mock.patch.object(g._parar_reevaluate, "wait", return_value=True) as m_wait, \
             mock.patch.object(g, "get_torrents") as m_get:
            g._reevaluate_loop()
        assert not m_wait.called, "deveria sair pelo intervalo 0 lido do arquivo"
        assert not m_get.called

    def test_intervalo_zero_encerra_o_loop(self, tmp_config):
        """Com 0 o loop sai em vez de girar — e nao chama o qBittorrent."""
        cfg = g.load_config()
        cfg["guardian"]["reevaluate_interval_seconds"] = 0
        g.save_config(cfg)
        # O mock do `wait` e rede de seguranca E asercao: `_reevaluate_loop` tem
        # `while True`, e a unica saida natural aqui e o `intervalo <= 0`. Com o
        # wait devolvendo True, o loop encerra mesmo se a leitura da config
        # falhar — em vez de girar a cada 300s com o pytest pendurado. E se o
        # wait tiver sido chamado, o teste falha: significa que nao saiu pelo
        # caminho do intervalo zero.
        with mock.patch.object(g._parar_reevaluate, "wait", return_value=True) as m_wait, \
             mock.patch.object(g, "get_torrents") as m_get:
            g._reevaluate_loop()
        assert not m_wait.called, "deveria sair antes de esperar, pelo intervalo 0"
        assert not m_get.called




# ── Troca de modo em runtime ───────────────────────────────────────────

class TestTrocaDeModoEmRuntime:
    """Trocar o Polling pela Web UI tem de trocar o modo sem restart.

    Os dois sentidos estavam quebrados em producao:

    - `polling -> webhook`: o laco de polling via o 0, logava "entrando em
      modo webhook" e dava `return` **sem subir a reavaliacao**. Nao sobrava
      laco nenhum: so o `/api/trigger`, que nem existe se o webhook nao
      estiver configurado no qBittorrent.
    - `webhook -> polling`: quem detectaria a volta era o laco de polling,
      que ja tinha terminado no start. So com restart do container.

    O segundo caso tem duas entradas: o laco de reavaliacao percebe sozinho
    quando esta vivo, e o POST da Web UI cobre o caso em que nao ha laco
    nenhum (reavaliacao desligada).
    """

    CICLO = {"total": 0, "pendentes": 0, "removidos": 0, "analisados": 0,
             "restantes": 0, "fora_do_historico": 0}

    def _config(self, check, reevaluate=300):
        cfg = g.load_config()
        cfg["guardian"]["check_interval_seconds"] = check
        cfg["guardian"]["reevaluate_interval_seconds"] = reevaluate
        g.save_config(cfg)

    @pytest.fixture(autouse=True)
    def _modo_limpo(self):
        """Cada teste comeca sem modo definido e nao vaza para o proximo."""
        g._definir_modo(None)
        yield
        g._definir_modo(None)
        g._parar_reevaluate.clear()

    def test_polling_para_webhook_sobe_a_reavaliacao(self, tmp_config):
        """REGRESSAO: o laco morria e nada mais olhava a fila."""
        self._config(300)

        def poe_webhook(_s):
            cfg = g.load_config()
            cfg["guardian"]["check_interval_seconds"] = 0
            g.save_config(cfg)

        with mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "write_heartbeat"), \
             mock.patch.object(g, "executar_ciclo", return_value=self.CICLO), \
             mock.patch.object(g.time, "sleep", side_effect=poe_webhook), \
             mock.patch.object(g, "_start_reevaluate_loop") as subiu:
            g.guardian_loop()

        assert subiu.called, \
            "sem a reavaliacao, o modo webhook fica so com o /api/trigger"
        assert g.modo_em_execucao() == "webhook"

    def test_webhook_para_polling_pelo_proprio_laco(self, tmp_config):
        """O laco de reavaliacao devolve o bastao quando o Polling volta."""
        self._config(0, reevaluate=300)
        g._definir_modo("webhook")

        def poe_polling(_timeout):
            cfg = g.load_config()
            cfg["guardian"]["check_interval_seconds"] = 300
            g.save_config(cfg)
            return False

        with mock.patch.object(g, "start_guardian") as subiu, \
             mock.patch.object(g._parar_reevaluate, "wait", side_effect=poe_polling), \
             mock.patch.object(g, "executar_ciclo", return_value=self.CICLO), \
             mock.patch.object(g, "write_heartbeat"):
            g._reevaluate_loop()

        assert subiu.called, "o polling precisa voltar sem restart"
        assert g.modo_em_execucao() == "polling"

    def test_webhook_sem_reavaliacao_volta_pelo_salvar_da_tela(self, tmp_config):
        """O caso sem laco nenhum: `reevaluate_interval_seconds = 0`.

        Aqui ninguem esta vivo para reler a config — o religamento so pode
        vir do evento de salvar.
        """
        self._config(0, reevaluate=0)
        g._definir_modo("webhook")
        self._config(300, reevaluate=0)

        with mock.patch.object(g, "start_guardian") as subiu:
            assert g.aplicar_modo_da_config() == "polling"
        assert subiu.called
        assert g.modo_em_execucao() == "polling"

    def test_salvar_sem_trocar_de_modo_nao_sobe_laco(self, tmp_config):
        """Salvar outra coisa qualquer nao pode duplicar o laco em execucao."""
        self._config(300)
        g._definir_modo("polling")
        with mock.patch.object(g, "start_guardian") as subiu:
            assert g.aplicar_modo_da_config() is None
        assert not subiu.called

    def test_sem_laco_nenhum_o_salvar_nao_inventa_um(self, tmp_config):
        """Antes de o guardian subir (`modo None`), salvar nao dispara nada.

        Quem sobe o primeiro laco e o `start_guardian()` do entrypoint.
        """
        self._config(300)
        with mock.patch.object(g, "start_guardian") as subiu:
            assert g.aplicar_modo_da_config() is None
        assert not subiu.called

    def test_duas_threads_na_mesma_troca_sobem_um_laco_so(self, tmp_config):
        """A thread atrasada acorda com a troca feita e nao pode duplicar.

        Sem a guarda, o ciclo passaria a rodar em dobro contra o mesmo
        qBittorrent — duas remocoes concorrentes do mesmo torrent.
        """
        g._definir_modo("webhook")
        subidas = []

        primeira = g._passar_bastao("webhook", "polling", lambda: subidas.append(1))
        segunda = g._passar_bastao("webhook", "polling", lambda: subidas.append(1))

        assert primeira is True
        assert segunda is False, "a segunda troca nao era desta thread"
        assert len(subidas) == 1

    def test_reavaliacao_segue_viva_quando_a_troca_nao_e_dela(self, tmp_config):
        """`_passar_bastao` False nao pode encerrar o laco por engano.

        Com o modo em `polling` (outra thread ja assumiu), o laco de
        reavaliacao que ainda estiver de pe segue o fluxo normal em vez de
        dar `return` no meio.
        """
        self._config(300, reevaluate=300)
        g._definir_modo("polling")

        with mock.patch.object(g, "start_guardian") as subiu, \
             mock.patch.object(g._parar_reevaluate, "wait", return_value=True), \
             mock.patch.object(g, "executar_ciclo", return_value=self.CICLO):
            g._reevaluate_loop()

        assert not subiu.called, "nao era a vez desta thread trocar o modo"

    def test_o_sinal_de_parada_nao_fica_preso_para_o_proximo_laco(self, tmp_config):
        """`aplicar_modo_da_config` levanta o Event; quem assume, limpa.

        Sem o `clear()` na entrada, o proximo modo webhook encerraria na
        primeira espera, com o flag que sobrou da troca anterior.
        """
        self._config(0, reevaluate=0)
        g._parar_reevaluate.set()

        with mock.patch.object(g, "start_guardian"):
            g._reevaluate_loop()   # sai pelo intervalo 0, mas limpa antes

        assert not g._parar_reevaluate.is_set(), "flag preso derruba o proximo laco"


class TestCheckIntervalNormalizado:
    """`"0"` entre aspas tambem e modo webhook, como no healthcheck.

    O healthcheck normalizava (`_as_int`) enquanto o laco comparava o valor
    cru — e `"0" == 0` e False. Os dois discordavam sobre o modo de um config
    editado a mao.
    """

    @pytest.mark.parametrize("valor,esperado", [
        (0, 0), ("0", 0), (300, 300), ("300", 300),
        (-5, 0), (None, 300), ("nao-numero", 300), (3.7, 3),
    ])
    def test_leitura(self, valor, esperado):
        assert g._check_interval({"guardian": {"check_interval_seconds": valor}}) == esperado

    def test_ausente_cai_no_default(self):
        assert g._check_interval({"guardian": {}}) == 300
        assert g._check_interval({}) == 300

    def test_mesma_regra_do_reevaluate(self):
        """As duas leituras tem de se comportar igual — sao o mesmo contrato."""
        for valor in (0, "0", 300, "300", -5, "nao-numero", None):
            cfg_c = {"guardian": {"check_interval_seconds": valor}}
            cfg_r = {"guardian": {"reevaluate_interval_seconds": valor}}
            assert g._check_interval(cfg_c) == g._reevaluate_interval(cfg_r), valor


# ── Corpo do guardian_loop ─────────────────────────────────────────────

class _LoopHarness:
    """Faz guardian_loop sair apos UMA iteracao, via modo webhook.

    guardian_loop chama get_config() antes do laco e de novo no fim de cada
    iteracao; devolver check_interval_seconds=0 na 2a chamada encerra o loop
    pelo caminho de producao, sem matar a thread com excecao.
    """

    def __init__(self, iteracoes=1):
        self.original = g.get_config
        self.chamadas = 0
        self.iteracoes = iteracoes

    def get_config(self):
        self.chamadas += 1
        cfg = dict(self.original())
        if self.chamadas > self.iteracoes:
            cfg["guardian"] = dict(cfg["guardian"])
            cfg["guardian"]["check_interval_seconds"] = 0
        return cfg


class TestGuardianLoopCorpo:
    """Iteracao do loop: marcacao de processados, contagem e resiliencia."""

    def _preparar(self, tmp_config, interval=300):
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["check_interval_seconds"] = interval
        g.save_config(cfg)
        return _LoopHarness()

    def test_so_marca_processado_quando_a_analise_conclui(self, tmp_config):
        """Torrent sem metadados (analyze_torrent -> False) volta no proximo ciclo.

        Marcar antes dos metadados chegarem fazia o torrent nunca mais ser
        validado — o magnet entrava em metaDL, era dado como processado e
        passava batido mesmo trazendo .exe depois.
        """
        harness = self._preparar(tmp_config)
        torrents = [{"hash": "com-metadados", "name": "A"},
                    {"hash": "sem-metadados", "name": "B"}]

        with mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "get_torrents", return_value=torrents), \
             mock.patch.object(g, "check_stalled_and_remove", return_value=False), \
             mock.patch.object(g, "write_heartbeat"), \
             mock.patch.object(g, "analyze_torrent",
                               side_effect=lambda t: t["hash"] == "com-metadados"), \
             mock.patch.object(g, "get_config", side_effect=harness.get_config):
            g.guardian_loop()

        assert g._processed == {"com-metadados"}

    def test_resumo_da_verificacao_traz_as_contagens(self, tmp_config):
        harness = self._preparar(tmp_config)
        torrents = [{"hash": h, "name": h.upper()} for h in ("a", "b", "c")]
        removidos = {"a", "c"}

        with mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "get_torrents", return_value=torrents), \
             mock.patch.object(g, "analyze_torrent", return_value=True), \
             mock.patch.object(g, "check_stalled_and_remove",
                               side_effect=lambda t: t["hash"] in removidos), \
             mock.patch.object(g, "write_heartbeat"), \
             mock.patch.object(g, "get_config", side_effect=harness.get_config), \
             mock.patch.object(g, "log") as m_log:
            g.guardian_loop()

        resumos = [c.args[0] for c in m_log.info.call_args_list
                   if "Verificacao #" in c.args[0]]
        assert len(resumos) == 1, f"esperado 1 resumo, veio {resumos}"
        assert "3 torrents" in resumos[0]
        assert "3 novos" in resumos[0]
        assert "2 stalled removidos" in resumos[0]

    def test_erro_de_dominio_nao_dispara_reconexao(self, tmp_config):
        """So erro de transporte reconecta; o resto so loga e segue.

        Reconectar a cada KeyError de payload esconderia o bug real atras de
        um login bem-sucedido.
        """
        harness = self._preparar(tmp_config)

        with mock.patch.object(g, "_connect_with_retry") as m_conn, \
             mock.patch.object(g, "get_torrents", side_effect=ValueError("payload torto")), \
             mock.patch.object(g, "write_heartbeat"), \
             mock.patch.object(g, "get_config", side_effect=harness.get_config), \
             mock.patch.object(g, "log") as m_log:
            g.guardian_loop()

        assert m_conn.call_count == 1, "reconexao so no startup"
        erros = [c.args[0] for c in m_log.error.call_args_list]
        assert any("payload torto" in e for e in erros), erros

    def test_loop_sobrevive_a_falha_de_escrita_do_heartbeat(self, tmp_config):
        """/tmp cheio ou somente-leitura nao pode derrubar a thread.

        O heartbeat e diagnostico; perde-lo deixa o container unhealthy, mas
        matar o loop por causa dele transforma um problema de disco em parada
        total do guardian.
        """
        harness = self._preparar(tmp_config)

        with mock.patch.object(g, "qbit_login"), \
             mock.patch.object(g, "get_torrents", return_value=[]), \
             mock.patch.object(g, "write_heartbeat",
                               side_effect=OSError("read-only file system")), \
             mock.patch.object(g, "get_config", side_effect=harness.get_config):
            g.guardian_loop()  # nao pode levantar

        assert harness.chamadas >= 2


class TestConnectRetryResiliencia:
    """_connect_with_retry nunca pode morrer durante a espera."""

    def test_heartbeat_quebrado_nao_interrompe_o_retry(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"]["retry_interval_seconds"] = 5
        g.save_config(cfg)

        tentativas = {"n": 0}

        def login():
            tentativas["n"] += 1
            if tentativas["n"] == 1:
                raise requests.exceptions.ConnectionError("qbit fora do ar")

        with mock.patch.object(g, "qbit_login", side_effect=login), \
             mock.patch.object(g, "write_heartbeat",
                               side_effect=OSError("read-only file system")), \
             mock.patch.object(g.time, "sleep") as m_sleep:
            g._connect_with_retry()

        assert tentativas["n"] == 2
        assert m_sleep.call_args_list == [mock.call(5)]


# ── Estados UP: torrent completo nunca e removido ──────────────────────

class TestCheckStalledEstadosUp:
    """Torrent completo/semeando esta fora do escopo do guardian.

    E o caminho mais destrutivo do codigo: um erro aqui apaga do disco
    (deleteFiles=true) midia que ja terminou de baixar.
    """

    UP_STATES = ["uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"]

    @pytest.mark.parametrize("state", UP_STATES)
    def test_estado_up_nao_remove(self, state, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(remove_stalled=True, stalled_time=1,
                               stalled_unit="seconds", remove_no_seeds=True,
                               no_seeds_time=1, no_seeds_unit="seconds")
        g.save_config(cfg)

        # Torrent que satisfaria TODOS os gatilhos se o estado nao fosse UP.
        torrent = {"hash": "h1", "name": "Filme.Completo", "state": state,
                   "added_on": 0, "num_complete": 0}

        with mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search") as m_block, \
             mock.patch.object(g, "send_notification") as m_notify:
            assert g.check_stalled_and_remove(torrent) is False

        assert not m_remove.called, f"{state} nao pode ser removido"
        assert not m_block.called
        assert not m_notify.called

    def test_stalled_dl_ainda_e_removido(self, tmp_config):
        """Contraprova: o skip e por estado UP, nao um 'nunca remove'."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(remove_stalled=True, stalled_time=1,
                               stalled_unit="seconds")
        g.save_config(cfg)
        torrent = {"hash": "h1", "name": "Filme.Travado", "state": "stalledDL",
                   "added_on": 0, "num_complete": 5}

        with mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "send_notification"):
            assert g.check_stalled_and_remove(torrent) is True

        m_remove.assert_called_once_with("h1")


# ── _stalled_threshold com remocao por stalled desligada ───────────────

class TestStalledThresholdDesligado:
    """{{stalledTime}} fica vazio quando o limiar nao se aplica.

    O evento `stalled` tambem e disparado pelo ramo de "0 seeds", onde
    stalled_time nao tem nenhuma relacao com o motivo da remocao. Preencher o
    limiar ali faria a notificacao afirmar um prazo que nao foi o criterio.
    """

    def test_vazio_quando_remocao_por_stalled_desligada(self, tmp_config):
        cfg = {"guardian": {"remove_stalled": False, "stalled_time": 24,
                            "stalled_unit": "hours"}}
        assert g._stalled_threshold(cfg) == ""

    def test_preenchido_quando_ligada(self, tmp_config):
        cfg = {"guardian": {"remove_stalled": True, "stalled_time": 15,
                            "stalled_unit": "minutes"}}
        assert g._stalled_threshold(cfg) == "15 minutes"

    def test_notificacao_de_sem_seeds_nao_afirma_limiar_de_stalled(self, tmp_config):
        """Remocao por 0 seeds com stalled desligado: limiar nao aparece."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(remove_stalled=False, stalled_time=24,
                               stalled_unit="hours", remove_no_seeds=True,
                               no_seeds_time=1, no_seeds_unit="seconds")
        cfg["notifications"] = {
            "apprise_url": "http://apprise:8000/notify",
            "enabled": True,
            "events": {"stalled": {
                "enabled": True,
                "template": "Motivo: {{reason}} | Limiar: [{{stalledTime}}]"}},
        }
        g.save_config(cfg)

        torrent = {"hash": "h1", "name": "Filme.Sem.Seeds", "state": "downloading",
                   "added_on": 0, "num_complete": 0}

        with mock.patch.object(g, "send_notification") as m, \
             mock.patch.object(g, "block_and_search"), \
             mock.patch.object(g, "remove_torrent"):
            assert g.check_stalled_and_remove(torrent) is True

        corpo = m.call_args[0][1]
        assert "Motivo: 0 seeds" in corpo
        assert "Limiar: []" in corpo, corpo
        assert "24" not in corpo, f"limiar de stalled nao se aplica aqui: {corpo}"


# ── Otimizacao de prioridades: os tres ramos ───────────────────────────

class TestOtimizacaoPrioridades:
    """Cada extensao cai no ramo certo: midia, auxiliar ou descarte.

    O ramo `else` (descarte) nunca executava em teste. E ele que impede o
    download de anexos indesejados que nao estao na lista de perigosos —
    `.url`, `.lnk`, `.par2`, executaveis renomeados.
    """

    FILES = [{"name": "ep.mkv", "index": 0},
             {"name": "info.nfo", "index": 1},
             {"name": "clique-aqui.url", "index": 2},
             {"name": "arquivo.par2", "index": 3}]

    def _rodar(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(priority_media=7, priority_normal=1,
                               priority_skip=0, remove_stalled=False,
                               remove_no_seeds=False)
        g.save_config(cfg)
        torrent = {"hash": "h1", "name": "Serie.S01E01", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "get_files", return_value=self.FILES), \
             mock.patch.object(g, "set_file_priority") as m_prio, \
             mock.patch.object(g, "send_notification"):
            assert g.analyze_torrent(torrent) is True
        return m_prio

    def test_cada_extensao_recebe_a_prioridade_do_seu_ramo(self, tmp_config):
        m_prio = self._rodar(tmp_config)
        assert m_prio.call_args_list == [
            mock.call("h1", 0, 7),   # .mkv  -> midia
            mock.call("h1", 1, 1),   # .nfo  -> auxiliar
            mock.call("h1", 2, 0),   # .url  -> descarte
            mock.call("h1", 3, 0),   # .par2 -> descarte
        ]

    def test_arquivo_desconhecido_nao_e_tratado_como_midia(self, tmp_config):
        """Contagem de midia so conta o que casa com valid_media_extensions."""
        m_prio = self._rodar(tmp_config)
        prioridades = [c.args[2] for c in m_prio.call_args_list]
        assert prioridades.count(7) == 1, \
            f"apenas o .mkv e midia, veio {prioridades}"

    def test_descarte_respeita_priority_skip_da_config(self, tmp_config):
        """priority_skip configuravel: -1 (sem prioridade) em vez de 0."""
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(priority_media=6, priority_normal=1,
                               priority_skip=-1, remove_stalled=False,
                               remove_no_seeds=False)
        g.save_config(cfg)
        torrent = {"hash": "h1", "name": "Serie.S01E01", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "get_files", return_value=self.FILES), \
             mock.patch.object(g, "set_file_priority") as m_prio, \
             mock.patch.object(g, "send_notification"):
            g.analyze_torrent(torrent)

        assert m_prio.call_args_list == [
            mock.call("h1", 0, 6),
            mock.call("h1", 1, 1),
            mock.call("h1", 2, -1),
            mock.call("h1", 3, -1),
        ]


# ── get_config: cache vazio ────────────────────────────────────────────

class TestGetConfigCacheVazio:
    """get_config() com cache vazio le o disco em vez de devolver None.

    Acontece de verdade: a Web UI pode atender uma requisicao antes de o loop
    do guardian ter rodado load_config().
    """

    def test_cache_vazio_recarrega_do_disco(self, tmp_config):
        g._config = None
        cfg = g.get_config()
        assert cfg["qbit"]["url"] == "http://localhost:8080"

    def test_cache_preenchido_nao_le_o_disco(self, tmp_config):
        g.load_config()
        g._config["qbit"]["url"] = "http://memoria-apenas:1234"
        assert g.get_config()["qbit"]["url"] == "http://memoria-apenas:1234"


# ── /api/config: falha de leitura ──────────────────────────────────────

class TestApiConfigFalhaDeLeitura:
    """Config ilegivel devolve 500 em JSON, nao traceback HTML.

    Um traceback do Flask exporia caminhos do sistema de arquivos e trechos de
    codigo na resposta.
    """

    def test_erro_de_leitura_vira_500_json(self, client, tmp_config):
        real = g.load_config()
        # A 1a chamada e do decorator de auth; a 2a e a do endpoint.
        with mock.patch("app.web._read_config",
                        side_effect=[real, OSError("config.json ilegivel")]):
            r = client.get("/api/config")

        assert r.status_code == 500
        assert r.is_json, "resposta de erro deve ser JSON"
        assert "error" in r.get_json()

    def test_erro_nao_expoe_traceback(self, client, tmp_config):
        real = g.load_config()
        with mock.patch("app.web._read_config",
                        side_effect=[real, OSError("config.json ilegivel")]):
            r = client.get("/api/config")

        corpo = r.get_data(as_text=True)
        assert "Traceback" not in corpo
        assert "app/web.py" not in corpo


# ── logger: nivel VERBOSE ──────────────────────────────────────────────

class TestLoggerVerbose:
    """log.verbose() respeita o nivel configurado.

    O nivel VERBOSE e injetado em logging.Logger por setattr; se o guard de
    nivel quebrar, LOG_LEVEL=ERROR em producao passa a despejar uma linha por
    torrent por ciclo.
    """

    @contextlib.contextmanager
    def _capturar(self, nivel):
        import logging
        from app.logger import get_logger

        log = get_logger("teste-verbose")
        registros = []
        handler = logging.Handler()
        handler.emit = registros.append
        nivel_antigo = log.level
        log.setLevel(nivel)
        log.addHandler(handler)
        try:
            yield registros
        finally:
            log.removeHandler(handler)
            log.setLevel(nivel_antigo)

    def test_emite_no_nivel_15(self):
        import logging
        from app.logger import VERBOSE

        with self._capturar(VERBOSE) as registros:
            logging.getLogger("qbit-guardian.teste-verbose").verbose(
                "torrent otimizado")

        assert [r.levelno for r in registros] == [VERBOSE]
        assert registros[0].getMessage() == "torrent otimizado"
        assert registros[0].levelname == "VERBOSE"

    def test_silencioso_quando_nivel_e_mais_alto(self):
        import logging

        with self._capturar(logging.INFO) as registros:
            logging.getLogger("qbit-guardian.teste-verbose").verbose("detalhe")

        assert registros == [], "VERBOSE nao pode sair com nivel INFO"

    def test_interpolacao_de_args(self):
        import logging
        from app.logger import VERBOSE

        with self._capturar(VERBOSE) as registros:
            logging.getLogger("qbit-guardian.teste-verbose").verbose(
                "torrent %s otimizado", "Serie.S01E01")

        assert registros[0].getMessage() == "torrent Serie.S01E01 otimizado"


# ── Healthcheck: config ilegivel ───────────────────────────────────────

class TestHealthcheckConfigIlegivel:
    """Config quebrada nao pode derrubar o healthcheck.

    Uma excecao em _read_intervals sairia como traceback e exit != 0: o
    container ficaria `unhealthy` para sempre, mesmo com o guardian vivo — e
    `restart: always` nao reinicia container unhealthy.

    A tolerancia reportada prova qual valor foi usado:
    max(600, 300*3, 120*3) = 900s com os defaults.
    """

    TOLERANCIA_DEFAULT = "tolerancia 900s"

    def _heartbeat(self, path, age_seconds=30):
        with open(path, "w") as f:
            f.write(str(time.time() - age_seconds))
        return str(path)

    def test_config_ausente_cai_nos_defaults(self, tmp_path):
        from app import healthcheck

        hb = self._heartbeat(tmp_path / "heartbeat")
        ok, msg = healthcheck.check(heartbeat_path=hb,
                                    config_path=str(tmp_path / "nao-existe.json"))
        assert ok, msg
        assert self.TOLERANCIA_DEFAULT in msg

    def test_config_com_json_invalido_cai_nos_defaults(self, tmp_path):
        from app import healthcheck

        cfg = tmp_path / "config.json"
        cfg.write_text("{ isso nao e json ]")
        hb = self._heartbeat(tmp_path / "heartbeat")

        ok, msg = healthcheck.check(heartbeat_path=hb, config_path=str(cfg))
        assert ok, msg
        assert self.TOLERANCIA_DEFAULT in msg

    def test_config_sem_secao_guardian_cai_nos_defaults(self, tmp_path):
        from app import healthcheck

        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"qbit": {"url": "http://x"}}))
        hb = self._heartbeat(tmp_path / "heartbeat")

        ok, msg = healthcheck.check(heartbeat_path=hb, config_path=str(cfg))
        assert ok, msg
        assert self.TOLERANCIA_DEFAULT in msg

    def test_config_ilegivel_nao_vira_modo_webhook(self, tmp_path):
        """O fallback e 300s, nao 0 — senao o healthcheck passaria sempre.

        Com interval=0 o healthcheck devolve 'modo webhook' sem nem olhar o
        heartbeat: uma config corrompida silenciaria a deteccao de loop morto.
        """
        from app import healthcheck

        hb = self._heartbeat(tmp_path / "heartbeat", age_seconds=5000)
        ok, msg = healthcheck.check(heartbeat_path=hb,
                                    config_path=str(tmp_path / "nao-existe.json"))
        assert not ok, msg
        assert "atrasado" in msg


# ── _handle_arr com tipo desconhecido ──────────────────────────────────

class TestArrTipoDesconhecido:
    """Tipo de *Arr fora de Radarr/Sonarr degrada sem efeito colateral.

    Os ramos por tipo nao tem `else`. Se um terceiro *Arr for ligado no futuro
    sem tratar o tipo, o handler precisa sair em silencio — nunca disparar um
    comando de busca com item_id indefinido.
    """

    def test_nao_dispara_busca_nem_quebra(self, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["lidarr"] = {"url": "https://lidarr.home.arpa", "api_key": "lkey"}
        g.save_config(cfg)

        sess = mock.MagicMock()
        sess.get.return_value.json.return_value = {
            "records": [{"id": 1, "downloadId": "HASH1", "artistId": 9}]}

        with mock.patch.object(g.requests, "Session", return_value=sess):
            g._handle_arr("Lidarr", "lidarr", "hash1", "Album.2020")

        assert not sess.post.called, "sem tipo tratado nao se dispara re-search"
        # O blocklist da queue ainda acontece: o item foi identificado.
        sess.delete.assert_called_once()


# ── is_stalled: limites do ramo "sem seeds" ────────────────────────────

class TestIsStalledSemSeedsLimites:
    """Zero e tempo insuficiente nao removem.

    `no_seeds_time: 0` precisa significar "desligado", nunca "remover agora" —
    e o valor que a config default grava.
    """

    def _cfg(self, **guardian):
        base = {"remove_stalled": False, "remove_no_seeds": True,
                "no_seeds_time": 48, "no_seeds_unit": "hours"}
        base.update(guardian)
        return {"guardian": base}

    def test_tempo_zero_nao_remove(self):
        torrent = {"state": "downloading", "num_complete": 0, "added_on": 0}
        stalled, motivo = g.is_stalled(torrent, self._cfg(no_seeds_time=0))
        assert stalled is False
        assert motivo == ""

    def test_tempo_insuficiente_nao_remove(self):
        torrent = {"state": "downloading", "num_complete": 0,
                   "added_on": time.time()}
        stalled, _ = g.is_stalled(torrent, self._cfg())
        assert stalled is False

    def test_tempo_atingido_remove(self):
        """Contraprova: o limiar funciona quando de fato e atingido."""
        torrent = {"state": "downloading", "num_complete": 0,
                   "added_on": time.time() - 48 * 3600 - 1}
        stalled, motivo = g.is_stalled(torrent, self._cfg())
        assert stalled is True
        assert motivo == "0 seeds"


# ── valid_media_extensions vazia ───────────────────────────────────────

class TestListaDeMidiaVazia:
    """Lista de extensoes de midia vazia desliga o criterio, nao apaga tudo.

    `valid_media_extensions: []` e um estado alcancavel pela Web UI. Se a
    checagem de "nenhum arquivo de midia valido" rodasse com a lista vazia,
    TODO torrent seria removido com os arquivos do disco.
    """

    def _rodar(self, tmp_config, files):
        g.load_config()
        cfg = g.get_config()
        cfg["guardian"].update(valid_media_extensions=[], remove_stalled=False,
                               remove_no_seeds=False)
        g.save_config(cfg)
        torrent = {"hash": "h1", "name": "Qualquer.Coisa", "state": "downloading",
                   "added_on": 0}

        with mock.patch.object(g, "get_files", return_value=files), \
             mock.patch.object(g, "set_file_priority"), \
             mock.patch.object(g, "remove_torrent") as m_remove, \
             mock.patch.object(g, "block_and_search") as m_block, \
             mock.patch.object(g, "send_notification") as m_notify:
            assert g.analyze_torrent(torrent) is True
        return m_remove, m_block, m_notify

    def test_nao_remove_quando_a_lista_esta_vazia(self, tmp_config):
        m_remove, m_block, _ = self._rodar(
            tmp_config, [{"name": "leia-me.txt", "index": 0}])
        assert not m_remove.called, "lista vazia nao pode remover torrent"
        assert not m_block.called

    def test_sem_midia_priorizada_nao_notifica_otimizacao(self, tmp_config):
        """Nada foi otimizado: nao ha o que anunciar.

        Notificar "otimizado (0 arquivos)" treinaria o usuario a ignorar o
        canal.
        """
        _, _, m_notify = self._rodar(
            tmp_config, [{"name": "leia-me.txt", "index": 0}])
        assert not m_notify.called

    def test_extensao_perigosa_ainda_remove(self, tmp_config):
        """Lista de midia vazia nao desliga a checagem de perigosos."""
        m_remove, m_block, _ = self._rodar(
            tmp_config, [{"name": "setup.exe", "index": 0}])
        m_remove.assert_called_once_with("h1")
        m_block.assert_called_once()


# ── Entrypoints: contrato de execucao ──────────────────────────────────

class TestEntrypointsFiacao:
    """Como o processo e montado: thread daemon, Flask sem debug, ordem."""

    def test_guardian_roda_em_thread_daemon(self):
        """Thread nao-daemon impediria o container de encerrar.

        O loop e infinito: sem daemon=True, `docker stop` esperaria o timeout
        e o container morreria com SIGKILL em vez de sair limpo.
        """
        with mock.patch.object(g.threading, "Thread") as m_thread:
            t = g.start_guardian()

        m_thread.assert_called_once_with(target=g.guardian_loop, daemon=True)
        m_thread.return_value.start.assert_called_once()
        assert t is m_thread.return_value

    def test_flask_nunca_sobe_com_debug(self):
        """debug=True exporia o console interativo do Werkzeug.

        Com o debugger ligado, qualquer um que alcance a porta executa Python
        arbitrario no container — sem passar pelo Basic Auth.
        """
        import app.web as w

        with mock.patch.object(w.app, "run") as m_run:
            w.start_web(host="127.0.0.1", port=5555)

        m_run.assert_called_once_with(host="127.0.0.1", port=5555,
                                      debug=False, threaded=True)

    def test_main_provisiona_credenciais_antes_de_abrir_a_porta(self):
        """Ordem importa: credenciais, heartbeat, guardian, web.

        O provisionamento vem primeiro porque a janela entre a porta abrir e a
        senha existir precisa ser zero — senao a Web UI fica publica por
        alguns instantes a cada deploy.

        O heartbeat vem antes de guardian e web porque o HEALTHCHECK do
        container comeca a rodar junto com o processo: sem o arquivo, a
        primeira checagem marcaria `unhealthy` logo no startup.
        """
        import runpy

        ordem = []
        with mock.patch.object(g, "bootstrap_credenciais",
                               side_effect=lambda: ordem.append("credenciais")), \
             mock.patch.object(g, "write_heartbeat",
                              side_effect=lambda: ordem.append("heartbeat")), \
             mock.patch.object(g, "start_guardian",
                               side_effect=lambda: ordem.append("guardian")), \
             mock.patch("app.web.start_web",
                        side_effect=lambda: ordem.append("web")):
            runpy.run_module("app.main", run_name="__main__")

        assert ordem == ["credenciais", "heartbeat", "guardian", "web"]


# ── Healthcheck: contrato de exit code ─────────────────────────────────

class TestHealthcheckExitCode:
    """O Docker le o exit code, nao a mensagem.

    `HEALTHCHECK CMD python app/healthcheck.py` decide healthy/unhealthy pelo
    codigo de saida: 0 = healthy, qualquer outro = unhealthy.
    """

    def test_main_devolve_zero_quando_saudavel(self, capsys):
        from app import healthcheck

        with mock.patch.object(healthcheck, "check",
                               return_value=(True, "heartbeat ok")):
            assert healthcheck.main() == 0

        assert "heartbeat ok" in capsys.readouterr().out

    def test_main_devolve_um_quando_doente(self, capsys):
        from app import healthcheck

        with mock.patch.object(healthcheck, "check",
                               return_value=(False, "heartbeat atrasado")):
            assert healthcheck.main() == 1

        assert "heartbeat atrasado" in capsys.readouterr().out

    def test_script_executado_direto_sai_com_o_codigo_do_check(self, tmp_path):
        """Executa o arquivo como o Dockerfile executa, via __main__."""
        import subprocess
        import sys

        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"guardian": {"check_interval_seconds": 0}}))

        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, os.path.join(raiz, "app", "healthcheck.py")],
                           env={**os.environ, "CONFIG_PATH": str(cfg)},
                           capture_output=True, text=True, timeout=30)

        assert r.returncode == 0, r.stderr
        assert "webhook" in r.stdout

    def test_config_path_default_quando_nao_informado(self, tmp_path):
        """check() sem config_path usa o CONFIG_PATH do modulo."""
        from app import healthcheck

        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"guardian": {"check_interval_seconds": 0}}))

        antigo = healthcheck.CONFIG_PATH
        healthcheck.CONFIG_PATH = str(cfg)
        try:
            ok, msg = healthcheck.check(heartbeat_path=str(tmp_path / "ausente"))
        finally:
            healthcheck.CONFIG_PATH = antigo

        assert ok, msg
        assert "webhook" in msg


# ── Contagem de testes nos READMEs ─────────────────────────────────────

class TestReadmeContagemDeTestes:
    """As duas mencoes de contagem em cada README nao podem divergir.

    Isso ja falhou duas vezes: a linha do comando `pytest` foi atualizada e a
    da tabela de stack ficou para tras, afirmando 79 testes por varias
    versoes. O teste nao julga se o numero esta certo — garante que as
    mencoes, nos dois idiomas, contem a MESMA historia, e que atualizar uma e
    esquecer a outra fica vermelho.
    """

    # Qualquer parenteses que fale de testes "funcionais": pega tanto
    # "(308 tests: 288 functional + 20 security)" na tabela de stack quanto
    # "(308: 288 funcionais + 20 de segurança)" no bloco de comandos, nos dois
    # idiomas, sem depender da ordem das palavras.
    PADRAO = re.compile(r"\(([^)]*(?:functional|funcionais)[^)]*)\)")

    def _mencoes(self, arquivo):
        with open(os.path.join(REPO_ROOT, arquivo), encoding="utf-8") as f:
            texto = f.read()
        return [tuple(int(n) for n in re.findall(r"\d+", grupo))
                for grupo in self.PADRAO.findall(texto)]

    @pytest.mark.parametrize("arquivo", ["README.md", "README.pt-BR.md"])
    def test_mencoes_do_mesmo_readme_concordam(self, arquivo):
        mencoes = self._mencoes(arquivo)
        assert len(mencoes) >= 2, \
            f"{arquivo}: esperado 2 mencoes de contagem, achei {mencoes}"
        assert len(set(mencoes)) == 1, \
            f"{arquivo}: mencoes divergentes {mencoes}"

    @pytest.mark.parametrize("arquivo", ["README.md", "README.pt-BR.md"])
    def test_total_e_a_soma_das_partes(self, arquivo):
        total, funcionais, seguranca = self._mencoes(arquivo)[0]
        assert total == funcionais + seguranca, \
            f"{arquivo}: {funcionais} + {seguranca} != {total}"

    def test_os_dois_idiomas_concordam(self):
        assert self._mencoes("README.md")[0] == self._mencoes("README.pt-BR.md")[0]


# ── Afirmacoes dos READMEs sobre a instalacao e o tour ─────────────────

# Todo arquivo markdown da raiz afirma coisas sobre o projeto, e nenhum deles
# estava em `TODOS_OS_DOCS`. O CHANGELOG fica de fora de proposito: ele e
# historico, e CITA os erros corrigidos para registrar que foram corrigidos.
DOCS_DA_RAIZ = ["README.md", "README.pt-BR.md", "CONTEXT.md"]


class TestReadmeNaoRepeteErroJaCorrigidoNosDocs:
    """Os arquivos da raiz ficaram fora de `TODOS_OS_DOCS` e por isso nao
    foram varridos quando `docs/` perdeu o `forgejo.home.arpa`, o
    `config.json.example` e o `python app/app.py` (v2.3.1). O bloco de
    instalacao manual dos dois READMEs seguiu com as tres coisas por quatro
    releases. Estes testes estendem as mesmas regras aos arquivos da raiz.
    """

    @pytest.mark.parametrize("arquivo", DOCS_DA_RAIZ)
    def test_repositorio_citado_e_alcancavel_de_fora(self, arquivo):
        """`forgejo.home.arpa` so existe na rede do mantenedor."""
        with open(os.path.join(REPO_ROOT, arquivo), encoding="utf-8") as f:
            assert "forgejo.home.arpa" not in f.read()

    @pytest.mark.parametrize("arquivo", DOCS_DA_RAIZ)
    @pytest.mark.parametrize("inexistente", ["app/app.py", "config.json.example"])
    def test_nao_cita_arquivo_inexistente(self, arquivo, inexistente):
        with open(os.path.join(REPO_ROOT, arquivo), encoding="utf-8") as f:
            texto = f.read()
        if inexistente not in texto:
            return
        assert os.path.exists(os.path.join(REPO_ROOT, inexistente)), \
            f"{arquivo} cita {inexistente}, que nao existe"

    @pytest.mark.parametrize("arquivo", ["README.md", "README.pt-BR.md"])
    def test_entrypoint_manual_e_o_que_funciona(self, arquivo):
        """`python app/main.py` levanta ModuleNotFoundError.

        So os READMEs: o `CONTEXT.md` e glossario de dominio, nao ensina a
        instalar — exigir o comando dele seria exigir conteudo que nao e dele.
        """
        with open(os.path.join(REPO_ROOT, arquivo), encoding="utf-8") as f:
            assert "python -m app.main" in f.read(), arquivo


class TestReadmeContagemDoTour:
    """O numero de passos no texto tem que bater com `static/tour.js`.

    Os READMEs nasceram afirmando 14 passos quando o tour sempre teve 24 — o
    contador da propria tela soma `PASSOS_LOGIN + PASSOS_CONFIG`, e nada
    ligava a prosa ao codigo.
    """

    # Cada passo e um objeto com uma `chave` de traducao; contar as chaves
    # dentro de cada array nao depende de o objeto caber em uma linha.
    @staticmethod
    def _passos_do_codigo():
        with open(os.path.join(STATIC_DIR, "tour.js"), encoding="utf-8") as f:
            codigo = f.read()
        total = 0
        for nome in ("PASSOS_LOGIN", "PASSOS_CONFIG"):
            inicio = codigo.index("var %s = [" % nome)
            fim = codigo.index("];", inicio)
            trecho = codigo[inicio:fim]
            assert "chave:" in trecho, nome
            total += trecho.count("chave:")
        return total

    PADROES = {"README.md": r"(\d+)-step walkthrough",
               "README.pt-BR.md": r"passeio de (\d+) passos"}

    @pytest.mark.parametrize("arquivo", ["README.md", "README.pt-BR.md"])
    def test_contagem_bate_com_o_tour(self, arquivo):
        with open(os.path.join(REPO_ROOT, arquivo), encoding="utf-8") as f:
            texto = f.read()
        achados = re.findall(self.PADROES[arquivo], texto)
        assert achados, f"{arquivo}: nenhuma mencao a contagem de passos"
        esperado = self._passos_do_codigo()
        for n in achados:
            assert int(n) == esperado, \
                f"{arquivo}: diz {n} passos, tour.js tem {esperado}"


# ── Bundle estatico da demonstracao (GitHub Pages) ─────────────────────

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "build_pages", os.path.join(REPO_ROOT, "scripts", "build_pages.py"))
build_pages = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(build_pages)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """Gera o bundle uma vez e devolve a pasta."""
    destino = str(tmp_path_factory.mktemp("site"))
    return build_pages.construir(destino)


def _bundle_ler(bundle, caminho):
    with open(os.path.join(bundle, caminho), encoding="utf-8") as f:
        return f.read()


class TestBundleDaDemonstracao:
    """A demonstracao publica nao pode virar uma copia que envelhece.

    O tour roda em cima das telas reais — e e isso que o faz acompanhar a
    interface a cada versao. Um `index.html` editado a mao para o Pages
    reintroduziria o desvio que ele existe para evitar, so que fora da
    varredura dos outros testes. Dai o bundle ser gerado, e estes testes
    conferirem que o gerado bate com a fonte.
    """

    ARQUIVOS = [".nojekyll", "index.html", "login.html", "demo.html",
                "i18n.js", "tour.js", "favicon.svg",
                os.path.join("api", "demo-config"),
                os.path.join("api", "version")]

    @pytest.mark.parametrize("nome", ARQUIVOS)
    def test_bundle_tem_o_arquivo(self, bundle, nome):
        assert os.path.isfile(os.path.join(bundle, nome)), f"faltando: {nome}"

    def test_demo_config_e_o_mesmo_corpo_da_rota(self, bundle):
        """A unica fonte de dado da tela publica tem que bater com a rota.

        Se divergir, a demonstracao mostra uma instalacao que o app nunca
        produz — e ninguem percebe, porque as duas telas abrem iguais.
        """
        with app.test_client() as c:
            da_rota = c.get("/api/demo-config").get_json()
        do_bundle = json.loads(_bundle_ler(bundle, os.path.join("api", "demo-config")))
        assert do_bundle == da_rota

    def test_demo_config_nao_leva_bloco_de_credenciais(self, bundle):
        """Mesma garantia da rota: em demonstracao ninguem tem conta."""
        do_bundle = json.loads(_bundle_ler(bundle, os.path.join("api", "demo-config")))
        assert "webui" not in do_bundle["config"]

    def test_versao_do_bundle_e_a_do_codigo(self, bundle):
        do_bundle = json.loads(_bundle_ler(bundle, os.path.join("api", "version")))
        assert do_bundle == {"version": APP_VERSION}

    def test_as_telas_sao_copia_fiel_da_fonte(self, bundle):
        """So as duas substituicoes declaradas separam o bundle de `static/`."""
        for origem, no_bundle in (("login.html", "login.html"),
                                  ("index.html", "demo.html")):
            esperado = build_pages.preparar_pagina(_read_static(origem))
            assert _bundle_ler(bundle, no_bundle) == esperado, \
                f"{no_bundle} divergiu da transformacao declarada"

    @pytest.mark.parametrize("nome", ["login.html", "demo.html"])
    def test_flag_do_modo_estatico_vem_antes_do_tour(self, bundle, nome):
        """Depois do `tour.js` a flag nao existiria na hora de instalar o stub."""
        html = _bundle_ler(bundle, nome)
        assert "window.QBIT_DEMO_ESTATICO = true" in html, f"{nome} sem a flag"
        assert html.index("QBIT_DEMO_ESTATICO") < html.index('src="tour.js"'), \
            f"{nome}: a flag caiu depois do tour.js"

    @pytest.mark.parametrize("nome", ["login.html", "demo.html", "index.html"])
    def test_nenhum_link_do_bundle_assume_raiz(self, bundle, nome):
        """Sob `/<repo>/`, `/i18n.js` e 404 — e o tour abre sem traducao."""
        html = _bundle_ler(bundle, nome)
        absolutos = re.findall(r'(?:src|href)="(/[^"]*)"', html)
        assert absolutos == [], f"{nome} aponta para a raiz: {absolutos}"

    def test_o_tour_do_bundle_aponta_para_o_arquivo(self, bundle):
        """No Pages nao ha rota `/login` — ha o arquivo."""
        for nome in ("login.html", "demo.html"):
            assert 'href="login.html?tour=1"' in _bundle_ler(bundle, nome), nome

    def test_a_porta_de_entrada_leva_ao_primeiro_passo(self, bundle):
        """Quem abre a raiz do Pages tem que cair no comeco do passeio."""
        assert "login.html?tour=1" in _bundle_ler(bundle, "index.html")

    def test_gerador_estoura_se_a_ancora_sumir(self):
        """Falhar no build e melhor que publicar tela que fala com API morta."""
        with pytest.raises(SystemExit):
            build_pages.preparar_pagina("<html><body>sem o script do tour</body></html>")


class TestTelasServemOsDoisHosts:
    """As telas nao podem assumir que estao na raiz do dominio.

    O app Flask serve `/login` e `/demo`; o Pages serve
    `/<repo>/login.html` e `/<repo>/demo.html`. Caminho relativo resolve
    certo nos dois; caminho absoluto so no primeiro.
    """

    @pytest.mark.parametrize("arquivo", ["index.html", "login.html"])
    def test_assets_locais_sao_relativos(self, arquivo):
        html = _read_static(arquivo)
        locais = [u for u in re.findall(r'(?:src|href)="(/[^"]*)"', html)
                  if not u.startswith("//")]
        # `/login?tour=1` e rota do app, e o gerador a troca pelo arquivo.
        assert locais == ["/login?tour=1"], \
            f"{arquivo}: asset preso na raiz: {locais}"

    @pytest.mark.parametrize("arquivo", ["index.html", "login.html"])
    def test_chamadas_de_api_sao_relativas(self, arquivo):
        html = _read_static(arquivo)
        assert "'/api/" not in html, \
            f"{arquivo}: chamada de API presa na raiz do dominio"

    @pytest.mark.parametrize("caminho", ["/demo", "/demo/", "/demo.html",
                                         "/qbit-guardian/demo.html"])
    def test_o_modo_demo_reconhece_as_formas_dos_dois_hosts(self, caminho):
        """O regex do `tour.js`, aplicado aos caminhos que os hosts geram."""
        src = _read_static("tour.js")
        m = re.search(r"var MODO_DEMO = /(.+?)/\.test", src)
        assert m, "o teste do MODO_DEMO mudou de forma"
        padrao = m.group(1).replace("\\/", "/")
        assert re.search(padrao, caminho), \
            f"MODO_DEMO nao reconhece {caminho}"

    @pytest.mark.parametrize("caminho", ["/login", "/login.html", "/", "/demos"])
    def test_o_modo_demo_nao_pega_o_que_nao_e_demo(self, caminho):
        src = _read_static("tour.js")
        padrao = re.search(r"var MODO_DEMO = /(.+?)/\.test", src).group(1)
        padrao = padrao.replace("\\/", "/")
        assert not re.search(padrao, caminho), \
            f"MODO_DEMO pegou {caminho}, que nao e a tela de demonstracao"


# ── Link da demonstracao publicada ─────────────────────────────────────

class TestLinkDaDemonstracao:
    """O endereco da demonstracao aparece em quatro arquivos.

    E o mesmo formato de erro que ja aconteceu com a contagem de testes:
    atualizar uma mencao e esquecer as outras. Aqui o teste nao aceita
    qualquer URL — ele DERIVA o endereco do Pages a partir do repositorio
    que os proprios documentos citam, entao mudar de dono ou de nome de
    repositorio quebra aqui antes de quebrar o link de quem leu.
    """

    ARQUIVOS = ["README.md", "README.pt-BR.md",
                os.path.join("docs", "en-US", "getting-started.md"),
                os.path.join("docs", "pt-BR", "primeiros-passos.md")]

    @staticmethod
    def _texto(arquivo):
        with open(os.path.join(REPO_ROOT, arquivo), encoding="utf-8") as f:
            return f.read()

    def _esperada(self):
        """`github.com/<dono>/<repo>` → `https://<dono>.github.io/<repo>/`."""
        m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", self._texto("README.md"))
        assert m, "README sem o repositorio do GitHub"
        dono, repo = m.group(1), m.group(2)
        return f"https://{dono.lower()}.github.io/{repo}/"

    @pytest.mark.parametrize("arquivo", ARQUIVOS)
    def test_o_arquivo_oferece_a_demonstracao(self, arquivo):
        assert "github.io" in self._texto(arquivo), \
            f"{arquivo} nao oferece a demonstracao publicada"

    @pytest.mark.parametrize("arquivo", ARQUIVOS)
    def test_o_endereco_bate_com_o_repositorio(self, arquivo):
        esperada = self._esperada()
        achadas = set(re.findall(r"https://[\w.-]+\.github\.io/[\w.-]*/?",
                                 self._texto(arquivo)))
        assert achadas, f"{arquivo}: nenhuma URL do Pages"
        assert achadas == {esperada}, \
            f"{arquivo}: esperava {esperada}, achei {sorted(achadas)}"

    def test_a_demonstracao_e_a_que_o_workflow_publica(self):
        """Sem o workflow, o link dos documentos aponta para o nada."""
        assert os.path.isfile(os.path.join(WORKFLOWS_DIR, "pages.yml")), \
            "os documentos linkam uma demonstracao que ninguem publica"


# ── Modulo de credenciais (app/auth.py) ────────────────────────────────

import app.auth as a


class TestGeracaoDeSenha:
    """A senha inicial e lida do log e digitada a mao."""

    def test_tamanho_declarado(self):
        assert len(a.gerar_senha()) == a.TAMANHO_SENHA_GERADA

    def test_tamanho_sob_medida(self):
        assert len(a.gerar_senha(32)) == 32

    def test_duas_chamadas_diferem(self):
        """Fonte criptografica, nao `random` com seed previsivel."""
        assert len({a.gerar_senha() for _ in range(20)}) == 20

    @pytest.mark.parametrize("ambiguo", ["0", "O", "1", "l", "I"])
    def test_sem_caracteres_ambiguos(self, ambiguo):
        """`0` e `O` na mesma senha custam um chamado de suporte."""
        assert ambiguo not in a.ALFABETO

    def test_usa_fonte_criptografica(self):
        """`random` e previsivel a partir de algumas amostras."""
        with mock.patch.object(a.secrets, "choice", wraps=a.secrets.choice) as m:
            a.gerar_senha(5)
        assert m.call_count == 5


class TestHashDeSenha:
    """PBKDF2-SHA256 com salt por senha."""

    def test_formato(self):
        partes = a.hash_senha("qualquer").split("$")
        assert partes[0] == a.PREFIXO_HASH
        assert int(partes[1]) == a.ITERACOES
        assert len(partes) == 4

    def test_senha_nao_aparece_no_hash(self):
        assert "qualquer" not in a.hash_senha("qualquer")

    def test_salt_diferente_a_cada_chamada(self):
        """Sem salt por senha, duas contas com a mesma senha teriam o mesmo
        hash — e uma rainbow table quebraria as duas de uma vez."""
        assert a.hash_senha("mesma") != a.hash_senha("mesma")

    def test_iteracoes_no_minimo_recomendado(self):
        """OWASP (2023): >= 600k para PBKDF2-HMAC-SHA256."""
        assert a.ITERACOES >= 600_000

    def test_verifica_a_propria_saida(self):
        assert a.verificar_senha("mesma", a.hash_senha("mesma"))


class TestVerificacaoDeSenha:
    @pytest.mark.parametrize("senha", ["", " ", "errada", "MESMA", "mesma "])
    def test_senha_errada_recusada(self, senha):
        assert a.verificar_senha(senha, a.hash_senha("mesma")) is False

    @pytest.mark.parametrize("armazenado", ["", None, 123, [], "pbkdf2_sha256$lixo",
                                            "pbkdf2_sha256$x$y$z"])
    def test_valor_armazenado_invalido_nao_autentica(self, armazenado):
        """Hash corrompido recusa todo mundo, nunca aceita todo mundo."""
        assert a.verificar_senha("qualquer", armazenado) is False

    @pytest.mark.parametrize("senha", [None, 123, []])
    def test_senha_de_tipo_errado_recusada(self, senha):
        assert a.verificar_senha(senha, a.hash_senha("mesma")) is False

    def test_formato_legado_em_texto_claro_aceito(self):
        """Config anterior a v2.2.0 guardava a senha em texto.

        Recusar aqui trancaria para fora todo mundo que atualizasse.
        """
        assert a.verificar_senha("antiga", "antiga") is True
        assert a.verificar_senha("outra", "antiga") is False

    def test_usa_comparacao_em_tempo_constante(self):
        """`==` em string vaza quantos caracteres do inicio estao certos."""
        with mock.patch.object(a.hmac, "compare_digest",
                               wraps=a.hmac.compare_digest) as m:
            a.verificar_senha("x", a.hash_senha("x"))
            a.verificar_senha("x", "legado")
        assert m.call_count == 2

    def test_usuario_em_tempo_constante(self):
        with mock.patch.object(a.hmac, "compare_digest",
                               wraps=a.hmac.compare_digest) as m:
            assert a.verificar_usuario("admin", "admin") is True
        assert m.called

    @pytest.mark.parametrize("args", [(None, "admin"), ("admin", None), (1, "admin")])
    def test_usuario_de_tipo_errado_recusado(self, args):
        assert a.verificar_usuario(*args) is False


class TestGarantirCredenciais:
    """Provisionamento: gera, migra ou nao mexe."""

    def test_config_vazia_gera_usuario_e_senha(self, capsys):
        cfg, alterou = a.garantir_credenciais({"webui": {"user": "", "password": ""}})
        assert alterou is True
        assert cfg["webui"]["user"] == a.USUARIO_PADRAO
        assert a.e_hash(cfg["webui"]["password"])

    def test_senha_gerada_e_anunciada_no_stdout(self, capsys):
        """`print`, nao `log`: o compose publicado usa LOG_LEVEL=ERROR, e uma
        senha anunciada em INFO nao apareceria no `docker logs`."""
        cfg, _ = a.garantir_credenciais({})
        saida = capsys.readouterr().out
        assert "usuario: admin" in saida
        assert "senha:" in saida
        # A senha impressa e a que autentica.
        senha = [l.split("senha:")[1].strip() for l in saida.splitlines()
                 if l.strip().startswith("senha:")][0]
        assert a.verificar_senha(senha, cfg["webui"]["password"])

    def test_senha_em_texto_claro_vira_hash(self, capsys):
        cfg, alterou = a.garantir_credenciais(
            {"webui": {"user": "humberto", "password": "antiga"}})
        assert alterou is True
        assert a.e_hash(cfg["webui"]["password"])
        # A senha que o usuario ja usava continua valendo.
        assert a.verificar_senha("antiga", cfg["webui"]["password"])
        assert cfg["webui"]["user"] == "humberto"

    def test_migracao_nao_anuncia_senha(self, capsys):
        """Nao ha senha nova para anunciar — e seria vaza-la no log."""
        a.garantir_credenciais({"webui": {"user": "humberto", "password": "antiga"}})
        assert "senha:" not in capsys.readouterr().out

    def test_hash_existente_nao_e_tocado(self, capsys):
        existente = a.hash_senha("ja-definida")
        cfg, alterou = a.garantir_credenciais(
            {"webui": {"user": "humberto", "password": existente,
                       "secret_key": "chave-ja-definida"}})
        assert alterou is False
        assert cfg["webui"]["password"] == existente

    def test_usuario_vazio_com_hash_valido_so_ajusta_o_usuario(self, capsys):
        existente = a.hash_senha("ja-definida")
        cfg, alterou = a.garantir_credenciais({"webui": {"user": "", "password": existente}})
        assert alterou is True
        assert cfg["webui"]["user"] == a.USUARIO_PADRAO
        assert cfg["webui"]["password"] == existente

    @pytest.mark.parametrize("webui", [None, "texto", 123, []])
    def test_secao_webui_invalida_e_reconstruida(self, webui, capsys):
        cfg, alterou = a.garantir_credenciais({"webui": webui})
        assert alterou is True
        assert cfg["webui"]["user"] == a.USUARIO_PADRAO
        assert a.e_hash(cfg["webui"]["password"])

    @pytest.mark.parametrize("senha", ["", "   ", None])
    def test_senha_em_branco_gera_nova(self, senha, capsys):
        cfg, alterou = a.garantir_credenciais({"webui": {"user": "x", "password": senha}})
        assert alterou is True
        assert a.e_hash(cfg["webui"]["password"])


class TestBootstrapCredenciais:
    """guardian.bootstrap_credenciais() — roda no entrypoint."""

    def test_grava_no_disco(self, tmp_config, capsys):
        cfg = g.load_config()
        cfg["webui"] = {"user": "", "password": ""}
        g.save_config(cfg)

        assert g.bootstrap_credenciais() is True
        with open(tmp_config) as f:
            salvo = json.load(f)
        assert salvo["webui"]["user"] == "admin"
        assert a.e_hash(salvo["webui"]["password"])

    def test_segundo_boot_nao_troca_a_senha(self, tmp_config, capsys):
        """Senha regenerada a cada restart trancaria o usuario para fora."""
        g.load_config()
        g.bootstrap_credenciais()
        with open(tmp_config) as f:
            primeira = json.load(f)["webui"]["password"]

        g._config = None
        assert g.bootstrap_credenciais() is False
        with open(tmp_config) as f:
            assert json.load(f)["webui"]["password"] == primeira

    def test_config_sem_permissao_de_escrita_falha_cedo(self, tmp_path, capsys):
        """Falhar antes de sortear a senha.

        O container passou a rodar sem privilegio; um volume `./config` criado
        pelas versoes antigas pertence ao root. Sem esta checagem a senha seria
        anunciada no log e nunca chegaria ao disco — o usuario tentaria entrar
        com uma credencial que nao existe.
        """
        caminho = tmp_path / "somente-leitura" / "config.json"
        caminho.parent.mkdir()
        caminho.write_text("{}")
        caminho.chmod(0o400)

        antigo = g.CONFIG_PATH
        g.CONFIG_PATH = str(caminho)
        g._config = None
        try:
            with pytest.raises(PermissionError):
                g.bootstrap_credenciais()
        finally:
            g.CONFIG_PATH = antigo
            g._config = None
            caminho.chmod(0o600)

        assert "senha:" not in capsys.readouterr().out

    def test_diretorio_gravavel_sem_arquivo_e_aceito(self, tmp_path):
        """Primeira instalacao: o config.json ainda nao existe."""
        antigo = g.CONFIG_PATH
        g.CONFIG_PATH = str(tmp_path / "config" / "config.json")
        try:
            assert g.config_gravavel() is True
        finally:
            g.CONFIG_PATH = antigo


class TestEntrypointPermissao:
    """O entrypoint explica o conserto em vez de soltar traceback."""

    def test_banner_traz_o_comando_de_chown(self, capsys):
        import app.main as m
        m._erro_de_permissao("/app/config/config.json")
        saida = capsys.readouterr().out
        assert "chown -R 1000:1000 ./config" in saida
        assert "/app/config/config.json" in saida


# ── Higiene de log ─────────────────────────────────────────────────────

class TestApprisUrlNaoVazaNoLog:
    """A apprise_url embute o token do bot (tgram://TOKEN/chat)."""

    def _registrar(self, apprise_url, tmp_config):
        g.load_config()
        cfg = g.get_config()
        cfg["notifications"] = {"apprise_url": apprise_url}
        g.save_config(cfg)

        with mock.patch.object(g.requests, "post"), \
             mock.patch.object(g, "log") as m_log:
            g.send_notification("titulo", "corpo")

        return " ".join(str(c) for c in
                        m_log.debug.call_args_list + m_log.error.call_args_list)

    @pytest.mark.parametrize("url,segredo", [
        # Em cada esquema do Apprise o segredo mora num lugar diferente da URL.
        ("tgram://123456:AAH-token-do-bot/987", "AAH-token-do-bot"),
        ("discord://id-do-webhook/token-do-webhook", "token-do-webhook"),
        ("pover://user-key/app-token", "app-token"),
        ("https://TOKEN-SECRETO@apprise.home.arpa:8443/notify/x", "TOKEN-SECRETO"),
        ("https://apprise.home.arpa/notify/token-no-caminho", "token-no-caminho"),
    ])
    def test_segredo_nao_chega_ao_log(self, url, segredo, tmp_config):
        assert segredo not in self._registrar(url, tmp_config)

    def test_host_proprio_continua_visivel_para_depurar(self, tmp_config):
        """Apprise self-hosted em http(s): o endereco ajuda e nao e credencial."""
        registrado = self._registrar("https://apprise.home.arpa/notify/x", tmp_config)
        assert "apprise.home.arpa" in registrado

    @pytest.mark.parametrize("url,esperado", [
        ("https://apprise.home.arpa/notify/x", "https://apprise.home.arpa"),
        ("http://apprise:8000/notify", "http://apprise:8000"),
        # Esquema proprio do Apprise: o authority E a credencial.
        ("tgram://token/123", "tgram://..."),
        ("discord://id/token", "discord://..."),
        # http com userinfo tambem esconde: o usuario pode ser o segredo.
        ("https://user:senha@host/x", "https://..."),
        # Porta nao numerica: nao da para separar host de credencial.
        ("tgram://123456:AAH-token/987", "tgram://..."),
    ])
    def test_destino_de(self, url, esperado):
        assert g._destino_de(url) == esperado

    @pytest.mark.parametrize("url", ["nao-e-url", "", "://sem-esquema"])
    def test_url_invalida_nao_quebra(self, url):
        assert g._destino_de(url) == "<url invalida>"


# ── Web UI: icone de conta e modal de credenciais ──────────────────────

class TestWebUIConta:
    """O modal de troca de credenciais existe e esta ligado ao endpoint."""

    @property
    def html(self):
        return _read_static("index.html")

    def test_botao_de_conta_na_topbar(self):
        html = self.html
        assert 'id="user-btn"' in html
        # Dentro da topbar, depois do seletor de idioma (canto superior direito).
        # A topbar vai da abertura ate o <h1> seguinte: parar no primeiro
        # </div> pegaria so o seletor de idioma.
        topbar = html[html.index('<div class="topbar">'):html.index("<h1")]
        assert 'id="user-btn"' in topbar
        assert topbar.index('id="lang-bar"') < topbar.index('id="user-btn"')

    def test_icone_e_o_circle_user_do_prototipo(self):
        """24x24, traco branco de 2px — o componente que esta no Penpot."""
        html = self.html
        svg = re.search(r'<button[^>]*id="user-btn".*?</button>', html, re.S).group(0)
        assert '<circle cx="12" cy="12" r="10"/>' in svg
        assert '<circle cx="12" cy="10" r="3"/>' in svg
        assert 'M7 20.662V19a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v1.662' in svg

        regra = re.search(r"(?m)^\s*\.user-btn svg\s*\{([^}]*)\}", html).group(1)
        assert "width:24px" in regra and "height:24px" in regra
        assert "stroke:currentColor" in regra
        assert "stroke-width:2" in regra

    @pytest.mark.parametrize("campo,tipo", [
        ("cred_user", None),
        ("cred_current", "password"),
        ("cred_new", "password"),
    ])
    def test_campos_do_modal(self, campo, tipo):
        html = self.html
        entrada = re.search(r'<input id="%s"[^>]*>' % campo, html).group(0)
        if tipo:
            assert f'type="{tipo}"' in entrada, entrada
        assert f'for="{campo}"' in html, "todo campo precisa de label associado"

    def test_senha_atual_e_obrigatoria(self):
        entrada = re.search(r'<input id="cred_current"[^>]*>', self.html).group(0)
        assert "required" in entrada

    def test_modal_comeca_escondido(self):
        assert re.search(r'<div class="modal-bg" id="cred-modal" hidden', self.html)

    def test_envia_para_o_endpoint_proprio_em_json(self):
        """Nunca por /api/config: la o `webui` e descartado de proposito."""
        html = self.html
        assert "const CRED_API = 'api/credentials';" in html
        envio = re.search(r"credForm\.addEventListener\('submit'.*?\n\}\);", html, re.S).group(0)
        assert "'Content-Type': 'application/json'" in envio
        assert "CRED_API" in envio
        assert "current_password" in envio

    def test_senha_atual_nunca_e_pre_preenchida(self):
        """Pre-preencher anularia a prova de identidade."""
        abrir = re.search(r"function abrirCred\(\) \{.*?\n\}", self.html, re.S).group(0)
        assert "setVal('cred_current', '')" in abrir
        assert "setVal('cred_new', '')" in abrir

    def test_usuario_atual_vem_do_get_config(self):
        assert "setVal('cred_user', (c.webui || {}).user)" in self.html

    def test_manda_para_o_login_depois_de_trocar(self):
        """Trocar credencial invalida a sessao: o cookie carrega um marcador
        do par usuario+senha.

        Recarregar o painel so mostraria 401 — o caminho honesto e a tela de
        login.
        """
        envio = re.search(r"credForm\.addEventListener\('submit'.*?\n\}\);",
                          self.html, re.S).group(0)
        assert "location.href = '/login'" in envio

    def test_fecha_por_esc_e_por_clique_fora(self):
        html = self.html
        assert "e.key === 'Escape'" in html
        assert "if (e.target === credModal) fecharCred();" in html

    @pytest.mark.parametrize("chave", [
        "account_title", "label_cred_user", "label_cred_current",
        "label_cred_new", "help_cred", "btn_cancel", "btn_save_short",
        "toast_cred_saved",
    ])
    def test_chaves_de_traducao_nos_dois_idiomas(self, chave):
        js = _read_static("i18n.js")
        blocos = re.findall(r"'(?:pt-BR|en-US)':\s*\{(.*?)\n    \}", js, re.S)
        assert len(blocos) == 2, "esperado um bloco por idioma"
        for bloco in blocos:
            assert re.search(r"\b%s\s*:" % chave, bloco), f"{chave} ausente num idioma"

    def test_i18n_traduz_title_e_aria(self):
        """O botao nao tem texto visivel: title/aria-label sao o rotulo."""
        js = _read_static("i18n.js")
        assert "data-i18n-title" in js
        assert "data-i18n-aria" in js
        html = self.html
        botao = re.search(r'<button[^>]*id="user-btn"[^>]*>', html, re.S).group(0)
        assert 'data-i18n-title="account_title"' in botao
        assert 'data-i18n-aria="account_title"' in botao


# ── Empacotamento e hook ───────────────────────────────────────────────

class TestDockerfileSemRoot:
    """O container nao roda como root."""

    @property
    def dockerfile(self):
        with open(os.path.join(REPO_ROOT, "Dockerfile"), encoding="utf-8") as f:
            return f.read()

    def test_declara_usuario_sem_privilegio(self):
        conteudo = self.dockerfile
        assert re.search(r"(?m)^USER\s+guardian\s*$", conteudo), \
            "sem USER, o processo roda como root e grava o volume como root"

    def test_usuario_criado_com_uid_1000(self):
        """UID 1000 e o primeiro usuario comum: casa com o bind mount do host."""
        assert "--uid 1000" in self.dockerfile

    def test_config_pertence_ao_usuario(self):
        conteudo = self.dockerfile
        assert "chown -R guardian:guardian /app" in conteudo

    def test_user_vem_depois_dos_copy(self):
        """Trocar de usuario antes do COPY deixaria os arquivos sem dono certo."""
        conteudo = self.dockerfile
        assert conteudo.index("COPY static/") < conteudo.index("USER guardian")


class TestHookDoWebhook:
    """scripts/qbit-guardian-hook.sh — webhook com auth obrigatoria."""

    @property
    def script(self):
        caminho = os.path.join(REPO_ROOT, "scripts", "qbit-guardian-hook.sh")
        with open(caminho, encoding="utf-8") as f:
            return f.read()

    def test_envia_credenciais_quando_definidas(self):
        """Sem credencial o /api/trigger devolve 401 e o webhook morre."""
        conteudo = self.script
        assert "QBIT_GUARDIAN_USER" in conteudo
        assert "QBIT_GUARDIAN_PASS" in conteudo
        assert "--user" in conteudo

    def test_curl_falha_em_erro_http(self):
        """`curl -s` sem `-f` sai com codigo 0 num 401: a falha sumia.

        Com isso ate a tentativa extra passava despercebida — o modo webhook
        parava de funcionar sem nenhum sinal.
        """
        assert re.search(r"curl\s+-sf\b", self.script)

    def test_avisa_no_stderr_quando_desiste(self):
        conteudo = self.script
        assert ">&2" in conteudo
        assert "QBIT_GUARDIAN_PASS nao definida" in conteudo

    def test_continua_nao_bloqueante(self):
        """O qBittorrent nao pode esperar o guardian."""
        conteudo = self.script
        assert conteudo.rstrip().endswith(") &")
        assert "--connect-timeout 5" in conteudo
        assert "--max-time 10" in conteudo

    def test_sintaxe_valida(self):
        import subprocess
        caminho = os.path.join(REPO_ROOT, "scripts", "qbit-guardian-hook.sh")
        r = subprocess.run(["sh", "-n", caminho], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_shebang_e_posix(self):
        """As imagens Docker do qBittorrent sao Alpine, que NAO tem /bin/bash.

        Com `#!/bin/bash` o qBittorrent falha ao executar com "not found"
        (exit 127) e o modo webhook nunca funciona — verificado rodando o
        script dentro de uma alpine:3.
        """
        assert self.script.startswith("#!/bin/sh\n"), \
            "shebang precisa ser POSIX: Alpine nao tem bash"

    def test_sem_construcoes_exclusivas_do_bash(self):
        conteudo = self.script
        assert "local " not in conteudo, "`local` nao e POSIX"
        assert not re.search(r"^\s*\w+=\(", conteudo, re.M), "array e bash-ismo"
        assert "[[" not in conteudo, "`[[` nao e POSIX"

    def test_tem_fallback_para_wget(self):
        """Alpine limpa tambem nao traz curl — so o wget do busybox."""
        conteudo = self.script
        assert "command -v curl" in conteudo
        assert "command -v wget" in conteudo
        # O wget do busybox nao tem --user: o Basic Auth vai montado a mao.
        assert "base64" in conteudo
        assert "Authorization: Basic" in conteudo
        assert "--post-data" in conteudo, "sem isso o wget faria GET"

    def test_avisa_quando_nao_ha_cliente_http(self):
        assert "nao tem curl nem wget" in self.script

    def test_executavel(self):
        """qBittorrent executa o arquivo direto, nao via shell.

        Sem o bit de execucao, a chamada falha antes do shebang importar.
        """
        caminho = os.path.join(REPO_ROOT, "scripts", "qbit-guardian-hook.sh")
        assert os.access(caminho, os.X_OK), "falta chmod +x"


# ── Bordas defensivas de v2.2.0 ────────────────────────────────────────

class TestDestinoDeBordas:
    """_destino_de nunca propaga excecao: e chamado dentro do notificador."""

    def test_urlparse_quebrado_nao_derruba_a_notificacao(self):
        with mock.patch.object(g, "urlparse", side_effect=ValueError("url torta")):
            assert g._destino_de("qualquer-coisa") == "<url invalida>"

    def test_porta_nao_numerica_em_http_esconde_o_authority(self):
        """`https://host:nao-numerica/x`: nao da para separar host de credencial."""
        assert g._destino_de("https://apprise.home.arpa:porta/x") == "https://..."

    def test_config_gravavel_com_diretorio_pai_inexistente(self, tmp_path):
        """Caminho aninhado que ainda nao existe: decide pelo avo gravavel."""
        alvo = tmp_path / "ainda-nao" / "config.json"
        assert g.config_gravavel(str(alvo)) is True

    def test_config_gravavel_com_arvore_inexistente(self):
        assert g.config_gravavel("/nao/existe/mesmo/config.json") is False

    def test_config_gravavel_com_diretorio_existente_e_arquivo_novo(self, tmp_path):
        """Caso do primeiro boot: a pasta montada existe, o arquivo ainda nao."""
        assert g.config_gravavel(str(tmp_path / "config.json")) is True


class TestHashComSaltFixo:
    """O salt pode ser informado — e o que torna o hash reproduzivel."""

    def test_mesmo_salt_gera_o_mesmo_hash(self):
        salt = b"0123456789abcdef"
        assert a.hash_senha("x", salt=salt) == a.hash_senha("x", salt=salt)

    def test_salt_entra_no_hash_resultante(self):
        import base64 as b64
        salt = b"0123456789abcdef"
        armazenado = a.hash_senha("x", salt=salt)
        assert armazenado.split("$")[2] == b64.b64encode(salt).decode()

    def test_iteracoes_sob_medida_sao_respeitadas(self):
        """Permite baratear o custo em teste sem mexer no default."""
        armazenado = a.hash_senha("x", iteracoes=1000)
        assert armazenado.split("$")[1] == "1000"
        assert a.verificar_senha("x", armazenado)


class TestApiConfigBordas:
    """Entradas fora do formato esperado no POST /api/config."""

    def test_corpo_json_que_nao_e_objeto(self, client, tmp_config):
        """Uma lista no lugar do objeto nao pode virar config."""
        r = client.post("/api/config", json=["nao", "e", "objeto"])
        assert r.status_code == 400

    def test_falha_ao_gravar_vira_400_json(self, client, tmp_config):
        import app.web as w
        with mock.patch.object(w, "_write_config", side_effect=OSError("disco cheio")):
            r = client.post("/api/config", json={"guardian": {"check_interval_seconds": 60}})
        assert r.status_code == 400
        assert r.is_json
        assert "disco cheio" in r.get_json()["error"]

    def test_config_sem_secao_webui_nao_quebra_a_leitura(self, client, tmp_config):
        """Config antigo pode nem ter `webui`."""
        import app.web as w
        cfg = g.load_config()
        cfg.pop("webui", None)
        g.save_config(cfg)
        r = client.get("/api/config")
        assert r.status_code == 200
        assert "webui" not in r.get_json()


# ── Tela de login ──────────────────────────────────────────────────────

class TestWebUILogin:
    """static/login.html — a tela que substituiu o popup do navegador."""

    @property
    def html(self):
        return _read_static("login.html")

    def test_campos_de_usuario_e_senha(self):
        html = self.html
        usuario = re.search(r'<input id="login_user"[^>]*>', html).group(0)
        senha = re.search(r'<input id="login_password"[^>]*>', html).group(0)
        assert 'type="password"' in senha
        assert 'type="password"' not in usuario
        assert "required" in usuario and "required" in senha
        assert 'for="login_user"' in html and 'for="login_password"' in html

    def test_foco_comeca_no_usuario(self):
        assert "autofocus" in re.search(r'<input id="login_user"[^>]*>', self.html).group(0)

    def test_autocomplete_para_o_gerenciador_de_senhas(self):
        html = self.html
        assert 'autocomplete="username"' in html
        assert 'autocomplete="current-password"' in html

    def test_envia_para_api_login_em_json(self):
        envio = re.search(r"form\.addEventListener\('submit'.*?\n\}\);", self.html, re.S).group(0)
        assert "'api/login'" in envio
        assert "'Content-Type': 'application/json'" in envio

    def test_redireciona_para_o_painel_no_sucesso(self):
        assert "location.href = '/'" in self.html

    def test_trata_429_e_401_com_mensagem_propria(self):
        """Erro generico do servidor nao diz ao usuario o que fazer."""
        html = self.html
        assert "r.status === 429" in html
        assert "login_throttled" in html
        assert "r.status === 401" in html
        assert "login_invalid" in html

    def test_diz_onde_achar_a_senha_inicial(self):
        """Sem isso o primeiro acesso vira suporte: a senha so existe no log."""
        assert "login_hint" in self.html
        js = _read_static("i18n.js")
        assert "docker logs qbit-guardian" in js

    def test_usa_os_tokens_do_design_system(self):
        """Mesma paleta do painel — a tela de login nao e uma ilha.

        `--col-form` e o mesmo token do modal de conta: largura confortavel
        para um formulario curto. Ele se chamava `--col` enquanto a grade do
        painel tinha tres colunas iguais de 365px — hoje a grade e 274/548/274
        e o nome antigo prometia um parentesco que nao existe mais.
        """
        html = self.html
        for token, valor in [("--bg", "#1a1a2e"), ("--card", "#16213e"),
                             ("--field", "#ffffff"), ("--accent", "#e94560"),
                             ("--col-form", "365px"), ("--r-card", "15px")]:
            assert re.search(r"%s:\s*%s" % (re.escape(token), re.escape(valor)), html), token

    def test_tem_seletor_de_idioma(self):
        html = self.html
        assert 'id="lang-bar"' in html
        assert '<script src="i18n.js">' in html
        assert "initI18N()" in html

    def test_nao_carrega_nada_de_fora(self):
        """Painel de homelab precisa abrir sem internet."""
        html = self.html
        externos = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
        assert externos == [], f"recurso externo na tela de login: {externos}"

    @pytest.mark.parametrize("chave", [
        "login_title", "label_login_password", "btn_login",
        "login_invalid", "login_throttled", "login_hint", "btn_logout",
    ])
    def test_chaves_de_traducao_nos_dois_idiomas(self, chave):
        js = _read_static("i18n.js")
        blocos = re.findall(r"'(?:pt-BR|en-US)':\s*\{(.*?)\n    \}", js, re.S)
        assert len(blocos) == 2
        for bloco in blocos:
            assert re.search(r"\b%s\s*:" % chave, bloco), f"{chave} ausente num idioma"


class TestWebUISair:
    """Botao de sair no modal de conta.

    Com Basic Auth nao havia como sair; com sessao, sair e expectativa basica.
    """

    @property
    def html(self):
        return _read_static("index.html")

    def test_botao_existe_no_modal(self):
        html = self.html
        acoes = re.search(r'<div class="modal-actions">(.*?)</div>', html, re.S).group(1)
        assert 'id="cred-logout"' in acoes
        assert 'data-i18n="btn_logout"' in acoes

    def test_sair_fica_na_outra_ponta(self):
        """Nao e acao do formulario: nao pode encostar em Salvar.

        Checa os dois lados — a regra CSS e a classe no botao. Verificar so a
        regra deixa passar o botao perder a classe.
        """
        html = self.html
        regra = re.search(r"(?m)^\s*\.modal-actions \.secundario\s*\{([^}]*)\}",
                          html).group(1)
        assert "margin-right:auto" in regra

        botao = re.search(r'<button[^>]*id="cred-logout"[^>]*>', html).group(0)
        assert 'class="secundario"' in botao, botao

    def test_chama_api_logout_e_vai_para_o_login(self):
        trecho = re.search(r"cred-logout'\)\.addEventListener.*?\n\}\);",
                           self.html, re.S).group(0)
        assert "'api/logout'" in trecho
        assert "method: 'POST'" in trecho
        assert "location.href = '/login'" in trecho

    def test_falha_de_rede_nao_impede_sair(self):
        """Sair local vale mesmo se o servidor nao responder."""
        trecho = re.search(r"cred-logout'\)\.addEventListener.*?\n\}\);",
                           self.html, re.S).group(0)
        assert "catch" in trecho


class TestChaveDeSessao:
    """`webui.secret_key` e provisionada junto com a senha.

    Sem ela o `POST /api/login` nao consegue emitir token e devolve 500: numa
    instalacao nova, a tela de login ficaria inutilizavel mesmo com a senha
    correta em maos.
    """

    def test_config_vazia_ganha_chave(self, capsys):
        cfg, alterou = a.garantir_credenciais({"webui": {}})
        assert alterou is True
        assert isinstance(cfg["webui"]["secret_key"], str)
        assert cfg["webui"]["secret_key"].strip()

    def test_chave_existente_e_preservada(self, capsys):
        existente = a.gerar_secret_key()
        cfg, _ = a.garantir_credenciais(
            {"webui": {"user": "admin", "password": a.hash_senha("x"),
                       "secret_key": existente}})
        assert cfg["webui"]["secret_key"] == existente

    def test_config_com_senha_mas_sem_chave_ganha_chave(self, capsys):
        """Config da v2.2.0: tinha senha em hash, nao tinha chave de sessao."""
        cfg, alterou = a.garantir_credenciais(
            {"webui": {"user": "admin", "password": a.hash_senha("x")}})
        assert alterou is True
        assert cfg["webui"].get("secret_key")

    def test_bootstrap_grava_a_chave_no_disco(self, tmp_config, capsys):
        cfg = g.load_config()
        cfg["webui"] = {"user": "", "password": "", "secret_key": ""}
        g.save_config(cfg)
        g.bootstrap_credenciais()
        with open(tmp_config) as f:
            assert json.load(f)["webui"]["secret_key"]

    def test_chave_e_longa_e_aleatoria(self):
        chaves = {a.gerar_secret_key() for _ in range(10)}
        assert len(chaves) == 10
        assert all(len(c) >= 32 for c in chaves)

    def test_chave_nao_deriva_da_senha(self, capsys):
        """Reaproveitar o hash da senha como chave assinante junta dois
        segredos de propositos diferentes: vazar um entregaria o outro.

        O cenario precisa ser o de uma senha JA existente — numa config vazia
        a chave e criada antes da senha, e qualquer implementacao passaria.
        """
        senha_hash = a.hash_senha("x")
        cfg, _ = a.garantir_credenciais(
            {"webui": {"user": "admin", "password": senha_hash}})
        chave = cfg["webui"]["secret_key"]
        assert chave != senha_hash
        assert senha_hash not in chave
        assert cfg["webui"]["password"] not in chave


# ── Documentacao de usuario (docs/) ────────────────────────────────────

DOCS_DIR = os.path.join(REPO_ROOT, "docs")

# pt-BR e en-US tem o mesmo conteudo com nomes diferentes no guia inicial.
PAGINAS = [
    ("INSTALL.md", "INSTALL.md"),
    ("USAGE.md", "USAGE.md"),
    ("FAQ.md", "FAQ.md"),
    ("primeiros-passos.md", "getting-started.md"),
]


def _docs(*nomes):
    """Caminhos de todos os arquivos de docs/, ou so os nomeados."""
    caminhos = []
    for idioma, indice in (("pt-BR", 0), ("en-US", 1)):
        for par in PAGINAS:
            if nomes and par[indice] not in nomes and par[0] not in nomes:
                continue
            caminhos.append(os.path.join(DOCS_DIR, idioma, par[indice]))
    return caminhos


def _ler_doc(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


TODOS_OS_DOCS = _docs()


class TestDocsEstrutura:
    """Os dois idiomas cobrem as mesmas paginas."""

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_pagina_existe(self, caminho):
        assert os.path.isfile(caminho), f"faltando: {caminho}"

    def test_nenhuma_pagina_orfa(self):
        """Arquivo solto em docs/ que a lista nao conhece passaria sem teste."""
        esperados = {os.path.abspath(c) for c in TODOS_OS_DOCS}
        encontrados = set()
        for raiz, _, arquivos in os.walk(DOCS_DIR):
            for nome in arquivos:
                if nome.endswith(".md"):
                    encontrados.add(os.path.abspath(os.path.join(raiz, nome)))
        assert encontrados == esperados, \
            f"fora da lista: {sorted(encontrados - esperados)}"

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_links_internos_resolvem(self, caminho):
        """Link para arquivo inexistente e beco sem saida para o usuario."""
        pasta = os.path.dirname(caminho)
        alvos = re.findall(r"\]\(([A-Za-z0-9_.-]+\.md)(?:#[^)]*)?\)", _ler_doc(caminho))
        quebrados = [a for a in alvos if not os.path.isfile(os.path.join(pasta, a))]
        assert quebrados == [], f"{os.path.basename(caminho)}: {quebrados}"


class TestDocsContraOCodigo:
    """Instrucoes dos docs conferidas contra o que o codigo de fato faz.

    O `docs/` ficou quatro releases atras sem ninguem perceber: ensinava
    `qbit.host`/`port` (que hoje levanta KeyError), `python app/app.py` (arquivo
    que nunca existiu) e um `config.json.example` inexistente. Instalar
    seguindo a documentacao era impossivel.
    """

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    @pytest.mark.parametrize("chave", ["qbit.host", "qbit.port", '"host"', '"port"'])
    def test_nao_ensina_schema_antigo(self, caminho, chave):
        """A conexao com o qBit e `qbit.url`, uma URL completa."""
        assert chave not in _ler_doc(caminho), \
            f"{os.path.basename(caminho)} ainda cita {chave}"

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    @pytest.mark.parametrize("inexistente", ["app/app.py", "config.json.example",
                                             "configuracao.md"])
    def test_nao_cita_arquivo_inexistente(self, caminho, inexistente):
        texto = _ler_doc(caminho)
        if inexistente not in texto:
            return
        # So vale como erro se nao estiver num aviso de "isto falha".
        assert os.path.exists(os.path.join(REPO_ROOT, inexistente)), \
            f"{os.path.basename(caminho)} cita {inexistente}, que nao existe"

    def test_entrypoint_manual_e_o_que_funciona(self):
        """`python app/main.py` levanta ModuleNotFoundError."""
        for caminho in _docs("INSTALL.md", "primeiros-passos.md", "getting-started.md"):
            texto = _ler_doc(caminho)
            assert "python -m app.main" in texto, os.path.basename(caminho)

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_volume_bate_com_o_config_path_da_imagem(self, caminho):
        """O Dockerfile fixa CONFIG_PATH=/app/config/config.json.

        Montar em `/app/config.json` faz o arquivo do usuario ser ignorado — e
        a config viver dentro do container, perdida a cada atualizacao.
        """
        texto = _ler_doc(caminho)
        assert ":/app/config.json" not in texto, \
            f"{os.path.basename(caminho)}: volume no caminho errado"

    def test_docker_compose_dos_docs_bate_com_o_do_repositorio(self):
        with open(os.path.join(REPO_ROOT, "docker-compose.yaml"), encoding="utf-8") as f:
            compose = f.read()
        assert "./config:/app/config" in compose
        for caminho in _docs("INSTALL.md", "primeiros-passos.md", "getting-started.md"):
            assert "./config:/app/config" in _ler_doc(caminho), os.path.basename(caminho)

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_nao_ensina_o_healthcheck_antigo(self, caminho):
        """`cat /tmp/heartbeat` so verificava a existencia do arquivo.

        Como o heartbeat nunca e apagado, um loop morto reportava `healthy`
        para sempre. A imagem traz o healthcheck correto desde a v2.0.5.
        """
        assert "cat\", \"/tmp/heartbeat" not in _ler_doc(caminho)
        assert 'cat /tmp/heartbeat' not in _ler_doc(caminho)

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_repositorio_citado_e_alcancavel_de_fora(self, caminho):
        """`forgejo.home.arpa` so existe na rede do mantenedor."""
        assert "forgejo.home.arpa" not in _ler_doc(caminho)

    def test_uid_do_chown_bate_com_o_dockerfile(self):
        with open(os.path.join(REPO_ROOT, "Dockerfile"), encoding="utf-8") as f:
            dockerfile = f.read()
        uid = re.search(r"--uid (\d+)", dockerfile).group(1)
        for caminho in _docs("INSTALL.md", "primeiros-passos.md", "getting-started.md", "FAQ.md"):
            texto = _ler_doc(caminho)
            assert f"chown -R {uid}:{uid}" in texto, \
                f"{os.path.basename(caminho)}: chown com UID diferente do Dockerfile"

    @staticmethod
    def _variaveis_lidas():
        """Variaveis de ambiente que o codigo DE FATO consulta.

        Busca pelo ponto de leitura, nao por substring: `TRANSPORT_ERRORS` no
        guardian contem "PORT" e fazia um `PORT=` inventado passar no teste.
        """
        lidas = set()
        for modulo in ("logger.py", "guardian.py", "web.py", "healthcheck.py"):
            with open(os.path.join(REPO_ROOT, "app", modulo), encoding="utf-8") as f:
                lidas |= set(re.findall(r"os\.environ\.get\(\s*[\"']([A-Z0-9_]+)", f.read()))
        with open(os.path.join(REPO_ROOT, "scripts", "qbit-guardian-hook.sh"),
                  encoding="utf-8") as f:
            lidas |= set(re.findall(r"\$\{([A-Z0-9_]+)", f.read()))
        return lidas

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_variaveis_de_ambiente_citadas_existem(self, caminho):
        """Doc que ensina uma variavel que o codigo nao le engana o usuario.

        `PORT` ja foi documentada assim por versoes, e nunca foi lida.
        """
        lidas = self._variaveis_lidas()
        texto = _ler_doc(caminho)
        citadas = set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})=", texto))
        # Nomes de exemplos de outros programas, nao do guardian.
        citadas -= {"PUID", "PGID", "TZ"}
        faltando = citadas - lidas
        assert not faltando, \
            f"{os.path.basename(caminho)}: {sorted(faltando)} nao e lida pelo codigo"

    def test_o_extrator_de_variaveis_funciona(self):
        """Contraprova: se este conjunto vier vazio, o teste acima nao testa nada."""
        lidas = self._variaveis_lidas()
        assert {"LOG_LEVEL", "CONFIG_PATH", "QBIT_GUARDIAN_URL",
                "QBIT_GUARDIAN_USER", "QBIT_GUARDIAN_PASS"} <= lidas
        assert "PORT" not in lidas

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_endpoints_citados_existem(self, caminho):
        """Endpoints DO GUARDIAN citados nos docs precisam existir.

        `/api/v2/...` fica de fora: e a API do proprio qBittorrent, que os
        docs citam para o usuario conferir as preferencias de autorun.
        """
        import app.web as w
        rotas = {str(r.rule) for r in w.app.url_map.iter_rules()}
        citados = {c for c in re.findall(r"(/api/[a-z][a-z_]*)", _ler_doc(caminho))
                   if not c.startswith("/api/v")}
        # Nem toda pagina cita endpoint — os guias iniciais nao citam nenhum.
        for rota in citados:
            assert rota in rotas, f"{os.path.basename(caminho)}: {rota} nao existe"

    @pytest.mark.parametrize("caminho", TODOS_OS_DOCS)
    def test_endpoints_do_qbittorrent_sao_da_api_v2(self, caminho):
        """Contraprova: o que e citado como API do qBit tem o prefixo certo."""
        texto = _ler_doc(caminho)
        for trecho in re.findall(r"/api/v\d[a-z0-9/_]*", texto):
            assert trecho.startswith("/api/v2/"), f"prefixo inesperado: {trecho}"


class TestDocsValoresPadrao:
    """Listas e escalas documentadas conferem com os defaults do codigo."""

    def _default(self, chave):
        import tempfile as _tmp
        antigo, g._config = g.CONFIG_PATH, None
        pasta = _tmp.mkdtemp()
        g.CONFIG_PATH = os.path.join(pasta, "config.json")
        try:
            return g.load_config()["guardian"][chave]
        finally:
            g.CONFIG_PATH = antigo
            g._config = None

    @pytest.mark.parametrize("caminho", _docs("USAGE.md", "FAQ.md"))
    def test_extensoes_perigosas_batem(self, caminho):
        texto = _ler_doc(caminho)
        if "`.exe`" not in texto:
            return
        for ext in self._default("dangerous_extensions"):
            assert f"`{ext}`" in texto, f"{os.path.basename(caminho)}: falta {ext}"

    @pytest.mark.parametrize("caminho", _docs("USAGE.md"))
    def test_extensoes_de_midia_batem(self, caminho):
        texto = _ler_doc(caminho)
        for ext in self._default("valid_media_extensions"):
            assert f"`{ext}`" in texto, f"{os.path.basename(caminho)}: falta {ext}"

    @pytest.mark.parametrize("caminho", _docs("USAGE.md"))
    def test_escala_de_prioridade_bate(self, caminho):
        """A escala do qBittorrent nao e continua: 2 a 5 devolvem HTTP 400."""
        texto = _ler_doc(caminho)
        for valido in sorted(g.VALID_FILE_PRIORITIES - {-1}):
            assert f"`{valido}`" in texto, f"falta prioridade {valido}"
        assert "`2`, `3`, `4`" in texto or "`2`, `3`, `4` ou `5`" in texto or \
               "2`, `3`, `4` or `5" in texto, "docs precisam avisar sobre 2-5"

    @pytest.mark.parametrize("caminho", _docs("USAGE.md"))
    def test_variaveis_de_notificacao_batem(self, caminho):
        texto = _ler_doc(caminho)
        for evento, variaveis in g.NOTIFICATION_VARIABLES.items():
            for v in variaveis:
                assert "{{%s}}" % v in texto, \
                    f"{os.path.basename(caminho)}: falta {{{{{v}}}}} ({evento})"

    @pytest.mark.parametrize("caminho", _docs("USAGE.md"))
    def test_nao_inventa_variavel_de_notificacao(self, caminho):
        declaradas = {v for vs in g.NOTIFICATION_VARIABLES.values() for v in vs}
        citadas = set(re.findall(r"\{\{(\w+)\}\}", _ler_doc(caminho)))
        assert citadas <= declaradas, f"variavel inexistente: {sorted(citadas - declaradas)}"

    @pytest.mark.parametrize("caminho", _docs("USAGE.md"))
    def test_intervalo_padrao_bate(self, caminho):
        """Ancorado na linha que anuncia o padrao.

        Procurar o numero solto no arquivo inteiro nao prova nada: "300"
        aparece em varios exemplos, entao trocar o padrao para 600 passava.
        """
        padrao = self._default("check_interval_seconds")
        linha = re.search(r"(?m)^-?\s*\*\*(?:Padr[ãa]o|Default):\*\*\s*(\d+)",
                          _ler_doc(caminho))
        assert linha, f"{os.path.basename(caminho)}: sem linha de padrao"
        assert int(linha.group(1)) == padrao

    @pytest.mark.parametrize("caminho", _docs("USAGE.md"))
    def test_retry_padrao_bate(self, caminho):
        texto = _ler_doc(caminho)
        achado = re.search(r"retry_interval_seconds`?\s*\((?:padr[ãa]o|default):\s*(\d+)",
                           texto)
        assert achado, f"{os.path.basename(caminho)}: sem o padrao do retry"
        assert int(achado.group(1)) == g.DEFAULT_RETRY_INTERVAL

    @pytest.mark.parametrize("caminho", _docs("USAGE.md", "FAQ.md"))
    def test_tamanho_minimo_de_senha_bate(self, caminho):
        texto = _ler_doc(caminho)
        if "8 caracteres" in texto or "8 characters" in texto:
            assert a.TAMANHO_MINIMO_SENHA == 8

    @pytest.mark.parametrize("caminho", _docs("USAGE.md", "FAQ.md"))
    def test_estados_up_documentados_batem(self, caminho):
        texto = _ler_doc(caminho)
        if "stalledUP" not in texto:
            return
        for estado in ("uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"):
            assert f"`{estado}`" in texto, f"{os.path.basename(caminho)}: falta {estado}"


# ── Workflows de CI ────────────────────────────────────────────────────

WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")


def _workflow(nome):
    with open(os.path.join(WORKFLOWS_DIR, nome), encoding="utf-8") as f:
        return f.read()


class TestWorkflowPages:
    """A demonstracao publicada nao pode ficar atras do codigo.

    Aqui o risco e o inverso do docker-build: sub-disparar nao publica
    imagem a toa, deixa a demonstracao velha — o mesmo defeito que o README
    teve por quatro releases.
    """

    @staticmethod
    def _paths_do_pages():
        texto = _workflow("pages.yml")
        bloco = re.search(r"(?m)^    paths:\n((?:      - .*\n)+)", texto)
        assert bloco, "pages.yml sem filtro de paths"
        return [l.strip().lstrip("- ").strip("'\"") for l in bloco.group(1).splitlines()]

    @pytest.mark.parametrize("fonte", ["static/**", "app/**",
                                       "scripts/build_pages.py",
                                       ".github/workflows/pages.yml"])
    def test_tudo_que_entra_no_bundle_dispara_publicacao(self, fonte):
        """`build_pages.py` le `static/` e importa `app.guardian`/`app.version`."""
        assert fonte in self._paths_do_pages()

    def test_publicacao_passa_pela_suite(self):
        """Entre os testes estao os que conferem o bundle contra a fonte."""
        texto = _workflow("pages.yml")
        assert "uses: ./.github/workflows/test.yml" in texto, \
            "a demonstracao subiria com a suite vermelha"
        assert re.search(r"(?m)^  build:\n    needs: test", texto), \
            "o build do bundle nao espera a suite"

    def test_tem_permissao_de_publicar_e_so(self):
        texto = _workflow("pages.yml")
        bloco = re.search(r"(?m)^permissions:\n((?:  .*\n)+)", texto).group(1)
        assert "pages: write" in bloco and "id-token: write" in bloco
        assert "contents: read" in bloco, \
            "o workflow da demonstracao nao precisa escrever no repositorio"

    def test_uma_publicacao_por_vez_sem_cancelar_pela_metade(self):
        """Cancelar no meio deixa o site sem parte dos arquivos."""
        texto = _workflow("pages.yml")
        assert "cancel-in-progress: false" in texto

    def test_o_passo_manual_esta_registrado_no_workflow(self):
        """`enablement: true` foi tentado e nao funciona com o GITHUB_TOKEN.

        Sem a razao escrita ao lado, a proxima pessoa (ou eu, daqui a tres
        meses) tenta de novo o parametro que a mensagem de erro do GitHub
        sugere e perde a mesma meia hora.
        """
        texto = _workflow("pages.yml")
        # Linha de verdade, nao mencao em comentario — o comentario fala do
        # parametro justamente para explicar por que ele nao esta la.
        efetivas = [l.strip() for l in texto.splitlines()
                    if not l.strip().startswith("#")]
        assert not any(l.startswith("enablement:") for l in efetivas), \
            "o parametro nao cria o site: Resource not accessible by integration"
        assert "Settings > Pages" in texto, \
            "o workflow nao diz onde o Pages e habilitado"


class TestWorkflowBuild:
    """O build so roda quando o conteudo da imagem muda.

    Antes, qualquer push reconstruia e publicava no GHCR — inclusive ajuste de
    documentacao. O Watchtower entao trocava o container em producao por uma
    imagem identica.
    """

    @staticmethod
    def _paths_do_build():
        """Lista de `paths` do gatilho de push do docker-build."""
        texto = _workflow("docker-build.yml")
        bloco = re.search(r"(?m)^    paths:\n((?:      - .*\n)+)", texto)
        assert bloco, "docker-build.yml sem filtro de paths"
        return [l.strip().lstrip("- ").strip("'\"")
                for l in bloco.group(1).splitlines()]

    @staticmethod
    def _copiado_pelo_dockerfile():
        """O que o Dockerfile traz para dentro da imagem."""
        with open(os.path.join(REPO_ROOT, "Dockerfile"), encoding="utf-8") as f:
            origens = re.findall(r"(?m)^COPY\s+(\S+)", f.read())
        return {o.rstrip("/") for o in origens}

    def test_build_filtra_por_path(self):
        assert self._paths_do_build(), "sem filtro, docs republicam a imagem"

    @pytest.mark.parametrize("obrigatorio", ["Dockerfile", "requirements.txt"])
    def test_arquivos_da_imagem_disparam_build(self, obrigatorio):
        assert obrigatorio in self._paths_do_build()

    def test_tudo_que_o_dockerfile_copia_dispara_build(self):
        """Se o Dockerfile passar a copiar uma pasta nova e o filtro nao
        acompanhar, mudancas nela nunca chegam a producao."""
        paths = self._paths_do_build()
        for origem in self._copiado_pelo_dockerfile():
            casa = any(p == origem or p.startswith(origem + "/") for p in paths)
            assert casa, f"Dockerfile copia {origem}, mas o filtro nao cobre"

    def test_o_proprio_workflow_dispara_build(self):
        """Mexer no workflow sem rodar o workflow esconde o erro ate o
        proximo push de aplicacao."""
        paths = self._paths_do_build()
        assert ".github/workflows/docker-build.yml" in paths
        assert ".github/workflows/test.yml" in paths, \
            "o build reutiliza o test.yml como gate"

    @pytest.mark.parametrize("inerte", ["docs/**", "docs/", "README.md",
                                        "CHANGELOG.md", "LICENSE", "test/**",
                                        ".github/scripts/**"])
    def test_arquivo_sem_efeito_na_imagem_nao_dispara_build(self, inerte):
        assert inerte not in self._paths_do_build()

    def test_latest_se_move_so_em_release(self):
        """Regressao da corrida pela `latest`.

        `{{is_default_branch}}` e verdadeiro tambem em push de TAG no
        metadata-action. Com branch e tag indo no mesmo push, os dois builds
        disputavam a `latest` e a versao publicada ora saia limpa, ora com o
        sufixo de commit, dependendo de qual terminasse por ultimo.
        """
        texto = _workflow("docker-build.yml")
        regra = re.search(r"type=raw,value=latest,enable=([^\n]+)", texto)
        assert regra, "sem regra para a tag latest"
        assert "is_default_branch" not in regra.group(1), \
            "is_default_branch tambem vale para push de tag: volta a corrida"
        assert "refs/tags/v" in regra.group(1), \
            "latest precisa se mover so em tag de versao"

    def test_build_de_main_publica_em_edge(self):
        """Main continua publicando imagem — so nao mexe na `latest`."""
        texto = _workflow("docker-build.yml")
        regra = re.search(r"type=raw,value=edge,enable=([^\n]+)", texto)
        assert regra, "build de main sem destino: o push-action falha sem tags"
        assert "!startsWith(github.ref, 'refs/tags/')" in regra.group(1), \
            "edge sairia tambem em push de tag"

    def test_tag_continua_publicando(self):
        """`paths` e ignorado em push de tag (comportamento do GitHub).

        O gatilho de tag precisa continuar la, senao um release deixa de
        publicar quando o commit da tag nao toca a aplicacao.
        """
        texto = _workflow("docker-build.yml")
        assert re.search(r"(?m)^    tags:\n      - 'v\*'", texto)

    def test_build_continua_atras_da_suite(self):
        """Gate de publicacao: imagem nao sobe com teste vermelho."""
        texto = _workflow("docker-build.yml")
        assert "uses: ./.github/workflows/test.yml" in texto
        assert "needs: test" in texto


class TestVersaoDaImagem:
    """A imagem publicada tem de se anunciar com a versao do codigo.

    Sem isto o label `org.opencontainers.image.version` vinha do
    metadata-action, que num push para main so tem a tag `latest` para
    oferecer: a imagem se anunciava como versao "latest" e a notificacao do
    Watchtower nao tinha o que mostrar alem do digest.
    """

    @staticmethod
    def _versao_do_changelog():
        """Primeira versao listada no CHANGELOG.md (a mais recente)."""
        with open(os.path.join(REPO_ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            achado = re.search(r"(?m)^## \[(\d+\.\d+\.\d+)\]", f.read())
        assert achado, "CHANGELOG.md sem entrada de versao no formato `## [x.y.z]`"
        return achado.group(1)

    def test_version_py_e_semver(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION), \
            f"__version__ = {APP_VERSION!r}: use x.y.z"

    def test_version_py_bate_com_changelog(self):
        """Duas fontes da mesma verdade: subir uma sem a outra e drift."""
        assert APP_VERSION == self._versao_do_changelog(), \
            "app/version.py e o topo do CHANGELOG.md discordam"

    def test_workflow_le_a_versao_do_codigo(self):
        """O CI nao pode voltar a inventar a versao a partir da tag."""
        texto = _workflow("docker-build.yml")
        assert "app/version.py" in texto, \
            "o build nao le a versao do codigo"

    def test_workflow_sobrescreve_o_label_de_versao(self):
        """O label automatico do metadata-action e o que precisa ser vencido."""
        texto = _workflow("docker-build.yml")
        assert re.search(
            r"org\.opencontainers\.image\.version=\$\{\{\s*steps\.appver\.outputs\.version\s*\}\}",
            texto), "o build nao sobrescreve org.opencontainers.image.version"

    def test_workflow_exige_tag_casando_com_o_codigo(self):
        """Release tagueado com numero diferente do codigo publica versao errada."""
        texto = _workflow("docker-build.yml")
        assert "GITHUB_REF_TYPE" in texto and "nao casa com __version__" in texto, \
            "o build de tag nao confere a tag contra app/version.py"


class TestReleaseAutomatico:
    """Tag publicada vira GitHub Release com a secao do CHANGELOG."""

    @staticmethod
    def _secao():
        import importlib.util
        caminho = os.path.join(REPO_ROOT, ".github", "scripts", "changelog_section.py")
        spec = importlib.util.spec_from_file_location("changelog_section", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.secao

    CHANGELOG_FAKE = (
        "# Changelog\n\n"
        "## [2.6.0] \u2014 2026-10-10\n\nResumo novo.\n\n### Adicionado\n- coisa nova\n\n"
        "## [2.5.2] \u2014 2026-10-10\n\nResumo velho.\n\n### Corrigido\n- coisa velha\n"
    )

    def test_extrai_a_secao_da_versao(self):
        corpo = self._secao()("2.6.0", self.CHANGELOG_FAKE)
        assert "Resumo novo." in corpo
        assert "coisa nova" in corpo

    def test_para_na_versao_seguinte(self):
        """Senao o release da 2.6.0 traria o changelog inteiro do projeto."""
        corpo = self._secao()("2.6.0", self.CHANGELOG_FAKE)
        assert "coisa velha" not in corpo
        assert "2.5.2" not in corpo

    def test_nao_repete_o_cabecalho(self):
        """A pagina do release ja mostra versao e data."""
        corpo = self._secao()("2.6.0", self.CHANGELOG_FAKE)
        assert not corpo.startswith("## [")

    def test_versao_sem_secao_devolve_nada(self):
        """Release sem notas e pior que release nenhum: o workflow para."""
        assert self._secao()("9.9.9", self.CHANGELOG_FAKE) is None

    def test_versao_instalada_tem_secao_no_changelog_real(self):
        with open(os.path.join(REPO_ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            corpo = self._secao()(APP_VERSION, f.read())
        assert corpo, f"CHANGELOG.md sem secao para {APP_VERSION}: a tag falharia"

    def test_workflow_publica_release_so_em_tag(self):
        texto = _workflow("docker-build.yml")
        assert re.search(r"(?m)^  release:", texto), "sem job de release"
        assert "startsWith(github.ref, 'refs/tags/v')" in texto, \
            "o release rodaria tambem em push para main"

    def test_release_espera_a_imagem_subir(self):
        """Release apontando para imagem que nao subiu e pior que nenhum."""
        texto = _workflow("docker-build.yml")
        bloco = texto[texto.index("  release:"):]
        assert "needs: build-and-push" in bloco

    def test_release_usa_a_secao_do_changelog(self):
        """Caminho completo: `scripts/...` e substring de `.github/scripts/...`,
        entao a assercao frouxa passaria com o arquivo no lugar errado."""
        texto = _workflow("docker-build.yml")
        assert ".github/scripts/changelog_section.py" in texto
        assert "--notes-file" in texto, "release publicado sem corpo"

    def test_script_mora_no_maquinario_de_ci(self):
        """`scripts/` da raiz e entregavel do usuario (o hook do qBittorrent);
        o extrator so roda no runner e nao deve se misturar com ele."""
        assert os.path.isfile(
            os.path.join(REPO_ROOT, ".github", "scripts", "changelog_section.py"))
        assert not os.path.exists(
            os.path.join(REPO_ROOT, "scripts", "changelog_section.py"))

    def test_script_acha_o_changelog_sozinho(self):
        """O workflow chama sem passar caminho: a raiz tem de resolver do novo
        local. Mover a pasta sem ajustar o calculo quebra exatamente aqui."""
        import subprocess
        caminho = os.path.join(REPO_ROOT, ".github", "scripts",
                               "changelog_section.py")
        r = subprocess.run([sys.executable, caminho, APP_VERSION],
                           capture_output=True, text=True, cwd=REPO_ROOT)
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip(), "release sairia com corpo vazio"

    def test_release_tem_permissao_de_escrita(self):
        """Sem contents: write o gh release create falha com 403."""
        bloco = _workflow("docker-build.yml")
        bloco = bloco[bloco.index("  release:"):]
        assert re.search(r"permissions:\s*\n\s*contents: write", bloco)

    def test_release_confere_que_a_tag_existe(self):
        """--verify-tag evita o gh criar a tag sozinho a partir do branch."""
        texto = _workflow("docker-build.yml")
        assert "--verify-tag" in texto


class TestWorkflowTestes:
    """A suite roda em qualquer mudanca, inclusive em docs/."""

    def test_sem_filtro_de_paths(self):
        """Documentacao e verificada por teste desde a v2.3.1.

        Filtrar docs/ aqui faria um ajuste de documentacao escapar da propria
        suite que existe para pegar o drift dela.
        """
        texto = _workflow("test.yml")
        gatilho = texto.split("jobs:")[0]
        assert "paths:" not in gatilho
        assert "paths-ignore:" not in gatilho

    def test_roda_em_push_e_pull_request(self):
        texto = _workflow("test.yml")
        assert re.search(r"(?m)^  push:", texto)
        assert re.search(r"(?m)^  pull_request:", texto)

    def test_exposto_para_reuso(self):
        assert re.search(r"(?m)^  workflow_call:", _workflow("test.yml"))


class TestTimeoutDaSuite:
    """A suite precisa de teto de tempo por teste.

    O codigo tem `while True` (`guardian_loop`, `_reevaluate_loop`) e a suite os
    chama. Um teste cuja condicao de parada falhe entra em espera, cai no
    `except Exception` do ciclo e volta ao laco — ficando pendurado ate alguem
    notar, em vez de falhar. Ja aconteceu: trocar `get_config` por
    `load_config` nos loops deixou o `_LoopHarness` sem efeito e levou a suite
    de 29 s para travada.
    """

    def _ler(self, nome):
        with open(os.path.join(REPO_ROOT, nome), encoding="utf-8") as f:
            return f.read()

    def test_pytest_ini_define_timeout_por_teste(self):
        ini = self._ler("pytest.ini")
        m = re.search(r"(?m)^\s*timeout\s*=\s*(\d+)", ini)
        assert m, "pytest.ini sem `timeout`: a suite volta a poder pendurar"
        segundos = int(m.group(1))
        # A suite inteira roda em ~29 s e nenhum teste passa de 1 s. Teto baixo
        # demais tornaria a suite instavel em maquina lenta; alto demais deixa o
        # travamento passar por lentidao.
        assert 20 <= segundos <= 120, \
            f"timeout = {segundos}s esta fora da faixa util"

    def test_pytest_timeout_declarado_em_dev(self):
        assert "pytest-timeout" in self._ler("requirements-dev.txt"), \
            "o teto de tempo depende do plugin; declare-o em requirements-dev.txt"

    def test_pytest_timeout_fora_da_imagem(self):
        """Dependencia de teste nao entra no runtime.

        O `requirements.txt` e o que o Dockerfile instala. Plugin de pytest ali
        engorda a imagem do RPi sem servir para nada em producao.
        """
        assert "pytest" not in self._ler("requirements.txt").lower(), \
            "requirements.txt (runtime) nao deve conter dependencia de teste"
