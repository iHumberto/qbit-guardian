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
- 🪝 Modo webhook (tempo real) alem do polling tradicional

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

## Instalacao Manual (sem Docker)

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.json.example config.json  # edite com suas credenciais
python app.py
```

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
  - ./caminho/para/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
```

Quando um torrent e adicionado, o qBit chama o script que faz `POST /api/trigger` no guardian, processando o torrent em tempo real.

## API REST

A Web UI expoe os seguintes endpoints:

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| `GET` | `/api/health` | Healthcheck — retorna `{"status": "ok"}` |
| `GET` | `/api/config` | Le a configuracao atual (JSON completo) |
| `POST` | `/api/config` | Salva a configuracao (JSON no body) |
| `POST` | `/api/trigger` | Forca verificacao imediata (usado pelo webhook) |

### Healthcheck Docker

O guardian escreve um heartbeat em `/tmp/heartbeat`. Use no `docker-compose.yml`:

```yaml
healthcheck:
  test: ["CMD", "cat", "/tmp/heartbeat"]
  interval: 60s
  timeout: 5s
  retries: 3
```

## Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `CONFIG_PATH` | `./config.json` | Caminho do arquivo de config |

## Desenvolvimento

```bash
# Instalar dependencias (inclui pytest)
pip install -r requirements.txt

# Rodar todos os testes (37: 25 funcionais + 12 seguranca)
python -m pytest test/ -v

# Apenas testes funcionais
python -m pytest test/test_guardian.py -v

# Apenas testes de seguranca
python -m pytest test/test_security.py -v
```

## Licenca

GNU GPL v3 — Este software e livre. Voce pode usar, modificar e redistribuir,
mas QUALQUER trabalho derivado DEVE ser distribuido sob a mesma licenca.
Nada feito com este codigo pode ser fechado ou proprietario.
