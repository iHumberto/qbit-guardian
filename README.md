# 🛡️ qbit-guardian

Protege seu qBittorrent contra torrents maliciosos.

Monitora torrents ativos e remove automaticamente arquivos com extensoes perigosas (.exe, .scr, .bat, etc), torrents sem seeds ou parados ha muito tempo. Integra com Sonarr e Radarr para bloquear e disparar nova busca automaticamente.

## Features

- 🔍 Detecta e remove torrents com arquivos perigosos
- 🎬 Integracao com Radarr (blocklist + re-search)
- 📺 Integracao com Sonarr (blocklist + re-search com validacao de data de lancamento)
- 🗑️ Remove torrents stalled ou sem seeds
- 🔔 Notificacoes via Apprise (Telegram, Discord, etc)
- ⚡ Otimizacao automatica de prioridades de arquivos
- 🖥️ Web UI para configuracao

## Quick Start (Docker)

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./config.json:/app/config.json
    restart: unless-stopped
```

Acesse `http://seu-host:5000` para configurar.

## Configuracao via Web UI

Apos iniciar, acesse a interface web e configure:

- **qBittorrent**: host, porta, API key
- **Sonarr/Radarr**: hosts, portas, API keys
- **Extensoes**: validas e perigosas (customizaveis)
- **Stalled/No-seeds**: tempo limite para remocao
- **Notificacoes**: Apprise URL
- **Prioridades**: Configuravel (0-7, igual escala do qBit)
- **Modo webhook**: Intervalo = 0 desativa polling, use com script no qBit

## Modos de operacao

### Polling (padrao)

O guardian verifica os torrents a cada N segundos. Configure `check_interval_seconds` na Web UI.

### Webhook (tempo real)

Configure `check_interval_seconds = 0` e adicione o script de webhook no qBittorrent:

**1. No qBittorrent:** Settings > Downloads > Run external program on torrent added
```
/scripts/qbit-guardian-hook.sh
```

**2. Monte o script no container qBit:**
```yaml
volumes:
  - ./scripts/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
```

## Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `CONFIG_PATH` | `./config.json` | Caminho do arquivo de config |

## Licenca

GNU GPL v3 — Este software e livre. Voce pode usar, modificar e redistribuir,
mas QUALQUER trabalho derivado DEVE ser distribuido sob a mesma licenca.
Nada feito com este codigo pode ser fechado ou proprietario.
