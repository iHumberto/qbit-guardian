"""
qbit-guardian — Entrypoint.

Inicia o loop guardian em background thread e o servidor web Flask.
"""
import threading
import logging
from guardian import start_guardian
from web import start_web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("qbit-guardian")

if __name__ == "__main__":
    log.info("qbit-guardian iniciando...")
    start_guardian()
    start_web()
