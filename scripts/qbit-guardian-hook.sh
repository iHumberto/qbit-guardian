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
#
# QBIT_GUARDIAN_USER / QBIT_GUARDIAN_PASS: credenciais da Web UI.
#   A partir da v2.2.0 a autenticacao e obrigatoria e /api/trigger exige
#   Basic Auth. Sem credencial o guardian responde 401 e o modo webhook para
#   de funcionar — por isso o script agora TRATA a falha em vez de ignora-la.

QBIT_GUARDIAN_URL="${QBIT_GUARDIAN_URL:-http://qbit-guardian:5000}"
QBIT_GUARDIAN_USER="${QBIT_GUARDIAN_USER:-admin}"

# Tudo em subshell background — o qBittorrent NAO espera este script terminar
(
    # 1. Aguarda o torrent estar registrado no qBit (evita race condition)
    sleep 10

    # Funcao de disparo com timeouts rigidos.
    # -f faz o curl falhar em HTTP >= 400: sem ele, um 401 saia com codigo 0 e
    # ate a tentativa extra passava despercebida — o webhook morria em silencio.
    trigger() {
        local auth=()
        if [ -n "${QBIT_GUARDIAN_PASS}" ]; then
            auth=(--user "${QBIT_GUARDIAN_USER}:${QBIT_GUARDIAN_PASS}")
        fi
        curl -sf -X POST \
            --connect-timeout 5 \
            --max-time 10 \
            "${auth[@]}" \
            "${QBIT_GUARDIAN_URL}/api/trigger" \
            > /dev/null
    }

    # 2. Primeira tentativa (com timeout)
    if trigger; then
        exit 0
    fi

    # 3. Segunda tentativa apos 5s (retry simples)
    sleep 5
    if trigger; then
        exit 0
    fi

    # 4. Falhou duas vezes: registra no stderr do qBittorrent em vez de sumir.
    echo "qbit-guardian-hook: /api/trigger falhou em ${QBIT_GUARDIAN_URL}." >&2
    if [ -z "${QBIT_GUARDIAN_PASS}" ]; then
        echo "qbit-guardian-hook: QBIT_GUARDIAN_PASS nao definida — a Web UI" \
             "exige autenticacao desde a v2.2.0." >&2
    fi
    exit 1
) &
