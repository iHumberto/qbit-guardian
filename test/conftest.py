"""Fixtures compartilhadas pelos dois arquivos de teste.

Run: .venv/bin/python -m pytest test/ -v
"""

import pytest

import app.guardian as g


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
