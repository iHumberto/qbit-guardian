#!/bin/bash
# qbit-guardian webhook script
# Configure no qBittorrent: Settings > Downloads > Run external program on torrent added
# Path: /scripts/qbit-guardian-hook.sh
#
# Certifique-se de que o container qbit-guardian esta acessivel na rede Docker.
# Ajuste QBIT_GUARDIAN_URL conforme sua configuracao.

QBIT_GUARDIAN_URL="${QBIT_GUARDIAN_URL:-http://qbit-guardian:5000}"

curl -s -X POST "${QBIT_GUARDIAN_URL}/api/trigger" > /dev/null 2>&1
