"""
qbit-guardian — Logger centralizado.

Configura logging com nivel controlado via env var LOG_LEVEL.

Níveis (em ordem de verbosidade):
    ERROR   (40) — Apenas erros: remove torrent, falha de conexão
    INFO    (20) — Polling básico: "Verificação #N: X torrents, Y novos, Z removidos"
    VERBOSE (15) — Detalhado: cada ação por torrent (stalled, sem seeds, perigoso, otimizado)
    DEBUG   (10) — Tudo: chamadas HTTP, payloads

Uso:
    from app.logger import setup_logging, get_logger, VERBOSE
    setup_logging()
    log = get_logger("guardian")
    log.verbose("[nome] stalled por >5h — REMOVIDO")
"""

import os
import logging
import sys

# ── Nível customizado VERBOSE (entre DEBUG=10 e INFO=20) ───────────────
VERBOSE = 15
logging.addLevelName(VERBOSE, "VERBOSE")


def _verbose(self, message, *args, **kwargs):
    """Loga no nivel VERBOSE."""
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs)


setattr(logging.Logger, "verbose", _verbose)  # type: ignore[attr-defined]

# ── Mapeamento de strings para níveis Python ────────────────────────────
_LEVEL_MAP = {
    "ERROR": logging.ERROR,
    "INFO": logging.INFO,
    "VERBOSE": VERBOSE,
    "DEBUG": logging.DEBUG,
}

# ── Setup ───────────────────────────────────────────────────────────────
_logging_configured = False


def setup_logging():
    """Configura o logging root uma única vez."""
    global _logging_configured
    if _logging_configured:
        return

    level_str = os.environ.get("LOG_LEVEL", "ERROR").upper()
    level = _LEVEL_MAP.get(level_str, logging.ERROR)

    # Handler: stdout com timestamp + nível
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(message)s"
    ))

    root = logging.getLogger()
    root.setLevel(level)
    # Remove handlers existentes para evitar duplicação
    root.handlers.clear()
    root.addHandler(handler)

    _logging_configured = True


def get_logger(name):
    """Retorna um logger nomeado. Garante que setup foi chamado."""
    setup_logging()
    return logging.getLogger(f"qbit-guardian.{name}")
