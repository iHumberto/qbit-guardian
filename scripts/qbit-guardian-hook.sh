#!/bin/sh
# qbit-guardian webhook script — nao-bloqueante, com timeout
#
# Configuracao no qBittorrent:
#   Opcoes > Downloads > Executar programa externo ao ADICIONAR torrent
#   Caminho: /scripts/qbit-guardian-hook.sh
#   (a caixa precisa ficar MARCADA, senao o campo nao e salvo)
#
# POSIX sh de proposito: as imagens Docker do qBittorrent sao baseadas em
# Alpine, onde **nao existe /bin/bash**. Um shebang `#!/bin/bash` faz o
# qBittorrent falhar na hora de executar, sem mensagem util. Pelo mesmo
# motivo, `curl` pode nao estar instalado — por isso o fallback para o wget
# do busybox.
#
# Variaveis de ambiente (definidas no servico do qBittorrent):
#   QBIT_GUARDIAN_URL   onde o guardian responde
#                       - mesma rede Docker: http://qbit-guardian:5000
#                       - por IP do host:     http://192.168.15.4:5000
#   QBIT_GUARDIAN_USER  usuario da Web UI (padrao: admin)
#   QBIT_GUARDIAN_PASS  senha da Web UI — obrigatoria desde a v2.2.0,
#                       porque /api/trigger exige autenticacao

QBIT_GUARDIAN_URL="${QBIT_GUARDIAN_URL:-http://qbit-guardian:5000}"
QBIT_GUARDIAN_USER="${QBIT_GUARDIAN_USER:-admin}"

log() {
    echo "qbit-guardian-hook: $*" >&2
}

# Dispara o /api/trigger. Devolve 0 so quando o guardian responde 2xx: um 401
# silencioso fazia o modo webhook morrer sem nenhum sinal.
disparar() {
    if command -v curl >/dev/null 2>&1; then
        if [ -n "${QBIT_GUARDIAN_PASS}" ]; then
            curl -sf -X POST --connect-timeout 5 --max-time 10 \
                --user "${QBIT_GUARDIAN_USER}:${QBIT_GUARDIAN_PASS}" \
                "${QBIT_GUARDIAN_URL}/api/trigger" > /dev/null
        else
            curl -sf -X POST --connect-timeout 5 --max-time 10 \
                "${QBIT_GUARDIAN_URL}/api/trigger" > /dev/null
        fi
    elif command -v wget >/dev/null 2>&1; then
        # O wget do busybox nao tem --user: o Basic Auth vai montado a mao.
        # `--post-data=''` e o que transforma a chamada em POST.
        if [ -n "${QBIT_GUARDIAN_PASS}" ]; then
            credencial=$(printf '%s:%s' "${QBIT_GUARDIAN_USER}" "${QBIT_GUARDIAN_PASS}" \
                | base64 | tr -d '\n')
            wget -q -T 10 -O - --post-data='' \
                --header="Authorization: Basic ${credencial}" \
                "${QBIT_GUARDIAN_URL}/api/trigger" > /dev/null
        else
            wget -q -T 10 -O - --post-data='' \
                "${QBIT_GUARDIAN_URL}/api/trigger" > /dev/null
        fi
    else
        log "o container do qBittorrent nao tem curl nem wget."
        return 127
    fi
}

# Tudo em subshell em background — o qBittorrent NAO espera este script
# terminar. O processo principal sai em poucos milissegundos.
(
    # 1. Aguarda o torrent estar registrado no qBit (evita race condition)
    sleep 10

    # 2. Primeira tentativa
    if disparar; then
        exit 0
    fi

    # 3. Segunda tentativa apos 5s
    sleep 5
    if disparar; then
        exit 0
    fi

    # 4. Falhou duas vezes: reporta em vez de sumir em silencio.
    log "/api/trigger falhou em ${QBIT_GUARDIAN_URL}."
    if [ -z "${QBIT_GUARDIAN_PASS}" ]; then
        log "QBIT_GUARDIAN_PASS nao definida — a Web UI exige autenticacao desde a v2.2.0."
    fi
    exit 1
) &
