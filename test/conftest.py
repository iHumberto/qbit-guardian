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

    _limpar()
    yield
    _limpar()


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
