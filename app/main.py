"""
qbit-guardian — Entrypoint.

Provisiona as credenciais da Web UI, inicia o loop guardian em background
thread e o servidor web Flask.
"""
import sys
import threading
from app.logger import setup_logging, get_logger
from app.guardian import start_guardian, write_heartbeat, bootstrap_credenciais
from app.web import start_web

setup_logging()
log = get_logger("main")


def _erro_de_permissao(caminho):
    """Instrucao acionavel em vez de traceback.

    A partir da v2.2.0 o container roda como UID 1000. Um volume `./config`
    criado pelas versoes anteriores pertence ao root, e o processo sem
    privilegio nao consegue gravar — o conserto e um comando so, e ele precisa
    aparecer no `docker logs`, nao ficar escondido numa stack trace.
    """
    linha = "=" * 68
    print(
        f"\n{linha}\n"
        f"  qbit-guardian — sem permissao de escrita em {caminho}\n"
        f"{linha}\n"
        f"  O container agora roda como usuario nao-root (UID 1000) e a pasta\n"
        f"  de configuracao ainda pertence ao root.\n\n"
        f"  No host, na pasta do docker-compose, rode:\n\n"
        f"      sudo chown -R 1000:1000 ./config\n\n"
        f"  e suba o container de novo.\n"
        f"{linha}\n",
        flush=True,
    )


if __name__ == "__main__":
    log.info("qbit-guardian iniciando...")
    # Antes de qualquer porta abrir: a Web UI nunca pode responder sem senha.
    try:
        bootstrap_credenciais()
    except PermissionError as e:
        _erro_de_permissao(e.args[0] if e.args else "config.json")
        sys.exit(1)
    write_heartbeat()
    start_guardian()
    start_web()
