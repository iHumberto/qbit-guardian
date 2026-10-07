"""
qbit-guardian — Healthcheck do container.

Verifica se o loop do guardian continua VIVO, comparando o timestamp do
heartbeat com o intervalo configurado em `guardian.check_interval_seconds`.

O healthcheck anterior (`cat /tmp/heartbeat`) apenas verificava a EXISTENCIA
do arquivo: como o heartbeat nunca e apagado, um loop travado permanecia
"healthy" indefinidamente. Este script falha quando o heartbeat fica mais
antigo que a tolerancia.

Tolerancia = max(600s, 3 * check_interval, 3 * retry_interval) — cobre
folgadamente um ciclo perdido sem gerar falso positivo quando o intervalo e
longo.

O retry entra na conta porque, enquanto o qBittorrent esta fora, o guardian
escreve o heartbeat no ritmo de `guardian.retry_interval_seconds` (nao no de
check_interval). Sem isso, um retry_interval maior que a tolerancia marcaria o
container `unhealthy` justamente no cenario que o retry existe para sobreviver
— e `restart: always` nao reinicia container unhealthy.

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
DEFAULT_RETRY_INTERVAL = 120
MIN_TOLERANCE_SECONDS = 600


def _as_int(raw, default, allow_zero=False):
    """Converte para int com fallback seguro.

    Config pode estar corrompida ou mal preenchida (string, nulo, negativo).
    Sem isso, `intervalo * 3` com uma string estoura ou repete texto.
    """
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    if val < 0 or (val == 0 and not allow_zero):
        return default
    return val


def _read_intervals():
    """Le (check_interval_seconds, retry_interval_seconds) do config.

    check_interval aceita 0 (modo webhook); retry_interval, nao.
    """
    try:
        with open(CONFIG_PATH) as f:
            guardian = json.load(f)["guardian"]
    except Exception:
        return DEFAULT_INTERVAL, DEFAULT_RETRY_INTERVAL

    return (
        _as_int(guardian.get("check_interval_seconds"), DEFAULT_INTERVAL,
                allow_zero=True),
        _as_int(guardian.get("retry_interval_seconds"), DEFAULT_RETRY_INTERVAL),
    )


def check(heartbeat_path=HEARTBEAT_PATH, config_path=None):
    """Retorna (ok: bool, mensagem: str).

    Separado do main() para permitir teste sem tocar em /tmp real.
    """
    global CONFIG_PATH
    if config_path is not None:
        CONFIG_PATH = config_path

    interval, retry_interval = _read_intervals()

    # Modo webhook: sem loop periodico — heartbeat so no startup/trigger.
    if interval == 0:
        return True, "modo webhook (intervalo=0) — sem loop periodico"

    try:
        with open(heartbeat_path) as f:
            last = float(f.read().strip())
    except Exception as e:
        return False, f"heartbeat ausente/ilegivel em {heartbeat_path}: {e}"

    age = time.time() - last
    # O retry entra na conta: durante indisponibilidade do qBit o heartbeat
    # sai no ritmo do retry, nao no do check_interval.
    tolerance = max(MIN_TOLERANCE_SECONDS, interval * 3, retry_interval * 3)

    if age > tolerance:
        return False, (f"heartbeat atrasado: {age:.0f}s "
                       f"(tolerancia {tolerance}s, intervalo {interval}s, "
                       f"retry {retry_interval}s)")

    return True, f"heartbeat ok ({age:.0f}s atras, tolerancia {tolerance}s)"


def main():
    ok, message = check()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
