"""
qbit-guardian — Entrypoint.

Inicia o loop guardian em background thread e o servidor web Flask.
"""
import threading
from app.logger import setup_logging, get_logger
from app.guardian import start_guardian, write_heartbeat
from app.web import start_web

setup_logging()
log = get_logger("main")

if __name__ == "__main__":
    log.info("qbit-guardian iniciando...")
    write_heartbeat()
    start_guardian()
    start_web()
