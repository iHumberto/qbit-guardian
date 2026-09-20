"""
qbit-guardian — Healthcheck do container.

Verifica se o loop do guardian continua VIVO, comparando o timestamp do
heartbeat com o intervalo configurado em `guardian.check_interval_seconds`.

O healthcheck anterior (`cat /tmp/heartbeat`) apenas verificava a EXISTENCIA
do arquivo: como o heartbeat nunca e apagado, um loop travado permanecia
"healthy" indefinidamente. Este script falha quando o heartbeat fica mais
antigo que a tolerancia.

Tolerancia = max(600s, 3 * intervalo) — cobre folgadamente um ciclo perdido
sem gerar falso positivo quando o intervalo e longo.

Modo webhook (intervalo = 0) nao tem loop periodico: o heartbeat e escrito
sob demanda pelo /api/trigger, entao o healthcheck sempre passa.

Uso (Dockerfile/compose):
    CMD ["python", "app/healthcheck.py"]
"""

import json
import os
import sys
import time

HEARTBEAT_PATH = "/tmp/heartbeat"
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config/config.json")
DEFAULT_INTERVAL = 300
MIN_TOLERANCE_SECONDS = 600


def _read_interval():
    """Le check_interval_seconds do config (fallback: DEFAULT_INTERVAL)."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)["guardian"].get("check_interval_seconds", DEFAULT_INTERVAL)
    except Exception:
        return DEFAULT_INTERVAL


def check(heartbeat_path=HEARTBEAT_PATH, config_path=None):
    """Retorna (ok: bool, mensagem: str).

    Separado do main() para permitir teste sem tocar em /tmp real.
    """
    global CONFIG_PATH
    if config_path is not None:
        CONFIG_PATH = config_path

    interval = _read_interval()

    # Modo webhook: sem loop periodico — heartbeat so no startup/trigger.
    if interval == 0:
        return True, "modo webhook (intervalo=0) — sem loop periodico"

    try:
        with open(heartbeat_path) as f:
            last = float(f.read().strip())
    except Exception as e:
        return False, f"heartbeat ausente/ilegivel em {heartbeat_path}: {e}"

    age = time.time() - last
    tolerance = max(MIN_TOLERANCE_SECONDS, interval * 3)

    if age > tolerance:
        return False, (f"heartbeat atrasado: {age:.0f}s "
                       f"(tolerancia {tolerance}s, intervalo {interval}s)")

    return True, f"heartbeat ok ({age:.0f}s atras, tolerancia {tolerance}s)"


def main():
    ok, message = check()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
