# 🛡️ qbit-guardian

Protect your qBittorrent from malicious torrents.

Monitors active torrents and automatically removes files with dangerous extensions (.exe, .scr, .bat, etc.), seedless torrents, or those stalled for too long. Integrates with Sonarr and Radarr for blocklisting and automatic re-search.

> 📖 **Leia em português:** [README.pt-BR.md](README.pt-BR.md)

## Features

- 🔍 Detects and removes torrents with dangerous files
- 🎬 Radarr integration (blocklist + re-search)
- 📺 Sonarr integration (blocklist + re-search with airdate validation)
- 🗑️ Removes stalled or seedless torrents
- 🔔 Notifications via Apprise (Telegram, Discord, etc.)
- ⚡ Automatic file priority optimization
- 🖥️ Web UI for configuration
- 🪝 Webhook mode (real-time) in addition to traditional polling

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

Access `http://your-host:5000` to configure.

## Manual Installation (without Docker)

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.json.example config.json  # edit with your credentials
python app/app.py
```

## Configuration via Web UI

After starting, access the web interface and configure:

- **qBittorrent**: host, port, API key
- **Sonarr/Radarr**: hosts, ports, API keys
- **Extensions**: valid and dangerous (customizable)
- **Stalled/No-seeds**: time limit for removal
- **Notifications**: Apprise URL
- **Priorities**: Configurable (0-7, same scale as qBit)
- **Webhook mode**: Interval = 0 disables polling, use with the webhook script in qBit

## Operating Modes

### Polling (default)

The guardian checks torrents every N seconds. Set `check_interval_seconds` in the Web UI.

### Webhook (real-time)

Set `check_interval_seconds = 0` and add the webhook script to qBittorrent:

**1. In qBittorrent:** Settings > Downloads > Run external program on torrent added
```
/scripts/qbit-guardian-hook.sh
```

**2. Mount the script in your qBit container:**
```yaml
volumes:
  - ./path/to/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
```

When a torrent is added, qBit calls the script which sends `POST /api/trigger` to the guardian, processing the torrent in real time.

## REST API

The Web UI exposes the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Healthcheck — returns `{"status": "ok"}` |
| `GET` | `/api/config` | Read current configuration (full JSON) |
| `POST` | `/api/config` | Save configuration (JSON body, deep merge) |
| `POST` | `/api/trigger` | Force immediate check (used by webhook) |

### Docker Healthcheck

The guardian writes a heartbeat to `/tmp/heartbeat`. Use in `docker-compose.yml`:

```yaml
healthcheck:
  test: ["CMD", "cat", "/tmp/heartbeat"]
  interval: 60s
  timeout: 5s
  retries: 3
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `./config.json` | Path to config file |

## Development

```bash
# Install dependencies (includes pytest)
pip install -r requirements.txt

# Run all tests (58: 42 functional + 16 security)
python -m pytest test/ -v

# Functional tests only
python -m pytest test/test_guardian.py -v

# Security tests only
python -m pytest test/test_security.py -v
```

## License

GNU GPL v3 — This software is free. You may use, modify, and redistribute it,
but ANY derivative work MUST be distributed under the same license.
Nothing made with this code may be closed-source or proprietary.
