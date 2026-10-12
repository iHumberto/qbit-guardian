"""Fixtures compartilhadas pelos dois arquivos de teste.

Run: .venv/bin/python -m pytest test/ -v
"""

import hashlib
import os

import pytest

import app.guardian as g

CONFIG_REAL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


@pytest.fixture(autouse=True)
def reset_guardian_globals():
    """Zera o estado global do guardian antes e depois de cada teste.

    `_processed`, `_check_count` e a sessao HTTP em cache sao globais de modulo
    e vazavam entre testes: o teste do hard cap do _prune_processed, por
    exemplo, deixa 10 mil hashes para tras. Os testes que dependiam de um set
    limpo chamavam `_processed.clear()` na mao, um por um — e quem esquecesse
    herdava o estado do vizinho, com resultado dependente da ordem de execucao.
    """
    def _limpar():
        g._processed.clear()
        g._check_count = 0
        g._qbit_session = None
        g._qbit_base = None
        # Event de modulo: se um teste o deixa setado, o loop de reavaliacao do
        # teste seguinte encerra na primeira espera e o motivo fica invisivel.
        g._parar_reevaluate.clear()
        # Janelas de lentidao: um teste que deixa hash marcado como lento faria
        # o seguinte remover torrent que nunca ficou lento.
        g._lento_desde.clear()
        # Modo em execucao (polling/webhook): tambem e global de modulo. Um
        # teste que sai com "webhook" faz o POST /api/config do teste seguinte
        # achar que precisa religar o polling — e subir a thread de verdade.
        g._definir_modo(None)

    _limpar()
    yield
    _limpar()


@pytest.fixture(autouse=True)
def nao_sobe_thread_de_reavaliacao(monkeypatch):
    """Impede que os testes criem a thread real do loop de reavaliacao.

    `guardian_loop` em modo webhook chama `_start_reevaluate_loop`, e varios
    testes exercitam esse caminho. Sem isto, cada um deixa para tras uma thread
    daemon parada em `Event.wait()`: ela sobrevive ao teste, pode acordar quando
    outro teste seta o Event e entao estoura ao encontrar o CONFIG_PATH do
    temporario ja removido. Aparecia como PytestUnhandledThreadExceptionWarning
    intermitente — flaky, porque depende da ordem em que os testes rodam.

    O outro lado da troca de modo — `_reevaluate_loop` e
    `aplicar_modo_da_config` chamando `start_guardian` ao ver o polling
    religado — nao precisa de patch aqui: nenhum dos dois caminhos roda com o
    modo em `None`, e `reset_guardian_globals` zera o modo a cada teste.
    Patchar `start_guardian` tambem apagaria o unico teste que verifica que
    ele cria a thread daemon.

    Quem precisa verificar que o loop foi iniciado faz seu proprio patch e
    inspeciona a chamada; quem so passa pelo caminho nao paga uma thread.
    """
    monkeypatch.setattr(g, "_start_reevaluate_loop", lambda: None)


@pytest.fixture(autouse=True)
def protege_config_do_repositorio():
    """Falha o teste que gravar no config.json versionado.

    Um teste que executava o entrypoint de verdade rodou o provisionamento de
    credenciais contra o CONFIG_PATH padrao: gerou senha, gravou o hash e sujou
    um arquivo rastreado pelo git. O estrago foi silencioso — so apareceu
    porque um teste seguinte, sem fixture de config, passou a receber 401.

    Qualquer teste que mexa em config precisa apontar CONFIG_PATH para um
    arquivo temporario.
    """
    def _impressao():
        try:
            with open(CONFIG_REAL, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except FileNotFoundError:
            return None

    antes = _impressao()
    yield
    depois = _impressao()
    assert depois == antes, (
        f"o teste alterou {CONFIG_REAL}, que e versionado. "
        f"Use a fixture tmp_config (ou monkeypatch CONFIG_PATH) em vez do "
        f"caminho padrao."
    )
