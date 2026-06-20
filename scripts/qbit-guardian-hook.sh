#!/bin/bash
# qbit-guardian webhook script — non-blocking, timeout-protected
#
# Configuracao no qBittorrent:
#   Settings > Downloads > Run external program on torrent added
#   Path: /scripts/qbit-guardian-hook.sh
#
# QBIT_GUARDIAN_URL: URL do servico qbit-guardian (configuravel via env)
#   - Container na mesma rede Docker: http://qbit-guardian:5000
#   - Acesso externo (IP do host):     http://192.168.15.4:5000

QBIT_GUARDIAN_URL="${QBIT_GUARDIAN_URL:-http://qbit-guardian:5000}"

# Tudo em subshell background — o qBittorrent NAO espera este script terminar
(
    # 1. Aguarda o torrent estar registrado no qBit (evita race condition)
    sleep 10

    # Funcao de disparo com timeouts rigidos
    trigger() {
        curl -s -X POST \
            --connect-timeout 5 \
            --max-time 10 \
            "${QBIT_GUARDIAN_URL}/api/trigger" \
            > /dev/null 2>&1
    }

    # 2. Primeira tentativa (com timeout)
    if trigger; then
        exit 0
    fi

    # 3. Segunda tentativa apos 5s (retry simples)
    sleep 5
    trigger
) &
