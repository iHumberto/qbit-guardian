# 🛡️ qbit-guardian

> Real-time protection for your qBittorrent — detects and removes malicious torrents before they can cause harm.

🇧🇷 **Leia em português:** [README.pt-BR.md](README.pt-BR.md)

[![tests](https://github.com/iHumberto/qbit-guardian/actions/workflows/test.yml/badge.svg)](https://github.com/iHumberto/qbit-guardian/actions/workflows/test.yml)
[![docker-build](https://github.com/iHumberto/qbit-guardian/actions/workflows/docker-build.yml/badge.svg)](https://github.com/iHumberto/qbit-guardian/actions/workflows/docker-build.yml)
[![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)](https://github.com/iHumberto/qbit-guardian)
[![License: GPL v3](https://img.shields.io/badge/License-GNU_GPL_v3-brightgreen?style=flat&logo=gnuprivacyguard)](https://www.gnu.org/licenses/gpl-3.0)

---

## What is qbit-guardian?

qbit-guardian monitors your qBittorrent's active torrents and automatically removes those that contain dangerous files (`.exe`, `.scr`, `.bat`, `.ps1`, `.vbs`, and more), have been stalled too long, or have zero seeds. When integrated with Sonarr/Radarr, it also blocklists the bad release and triggers a new search — so your library keeps growing without manual intervention.

It runs as a lightweight Docker container (or a Python process) with a built-in Web UI for configuration, Apprise-powered notifications, and optional webhook mode for real-time processing.

## Stack

| Component   | Technology                          |
|-------------|-------------------------------------|
| Runtime     | Python 3.12                         |
| Web UI      | Flask 3.x                           |
| HTTP client | requests 2.x                        |
| Notifications | Apprise (Telegram, Discord, Slack, and 100+ services) |
| Testing     | pytest 8.x (79 tests: 59 functional + 20 security) |
| License     | GNU GPL v3                          |

## Features

- 🔍 **Malicious file detection** — removes torrents containing executables, scripts, and other dangerous extensions
- 🎬 **Radarr integration** — blocklist + automatic re-search for movies
- 📺 **Sonarr integration** — blocklist + re-search with episode air-date validation
- 🗑️ **Stalled & seedless removal** — cleans up dead torrents after a configurable time limit
- ⚡ **File priority optimization** — auto-prioritizes media files, lowers or skips junk files
- 🔔 **Apprise notifications** — alerts via Telegram, Discord, Slack, Pushover, and 100+ other services
- 🖥️ **Web UI** — two-column layout with dark theme: external services (qBittorrent, Sonarr, Radarr, notifications) on the left, Guardian settings on the right. HTTP Basic Auth support
- 🪝 **Webhook mode** — real-time processing on torrent addition (no polling delay)
- 🐳 **Docker-first** — pre-built image on `ghcr.io`, healthcheck included

## Quick Start (Docker)

Add this to your `docker-compose.yml` alongside qBittorrent:

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "cat", "/tmp/heartbeat"]
      interval: 60s
      timeout: 5s
      retries: 3
```

Then start:

```bash
docker compose up -d
```

On first run, the system creates the configuration automatically — no manual JSON editing needed. Open `http://your-host:5000` to fill in all settings through the Web UI.

> 💡 **What is an API key?** It's a long random password that qBittorrent generates so other programs (like qbit-guardian) can talk to it securely. Find yours in qBittorrent at **Tools → Options → Web UI → API Key**.

### Web UI Layout

The configuration page is split into two columns:

- **Left column**: Connections to your external services — qBittorrent, Sonarr, Radarr, and Apprise notifications.
- **Right column**: All Guardian settings — check interval, file extensions, priorities, and stalled/seedless removal rules.

On phones and tablets (screens narrower than 768 px), the columns stack vertically so everything remains easy to use.

## Manual Installation (without Docker)

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.json.example config.json   # edit with your credentials
python app/app.py
```

The process runs in the foreground. Press `Ctrl+C` to stop.

## Configuration

All settings live in `config.json` and can be edited through the Web UI or directly. Here's the full structure:

```json
{
  "qbit": {
    "host": "localhost",
    "port": 8080,
    "api_key": ""
  },
  "sonarr": {
    "host": "",
    "port": 8989,
    "api_key": ""
  },
  "radarr": {
    "host": "",
    "port": 7878,
    "api_key": ""
  },
  "guardian": {
    "check_interval_seconds": 300,
    "valid_media_extensions": [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".webm"],
    "dangerous_extensions": [".exe", ".scr", ".bat", ".cmd", ".vbs", ".js", ".com", ".pif", ".msi", ".dll", ".ps1", ".sh", ".bin"],
    "remove_stalled": false,
    "stalled_time": 0,
    "stalled_unit": "hours",
    "remove_no_seeds": false,
    "no_seeds_time": 0,
    "no_seeds_unit": "hours",
    "priority_media": 7,
    "priority_normal": 1,
    "priority_skip": 0
  },
  "notifications": {
    "apprise_url": ""
  },
  "webui": {
    "user": "",
    "password": ""
  }
}
```

| Section         | Key fields                                                                 |
|-----------------|---------------------------------------------------------------------------|
| **qbit**        | `host`, `port`, `api_key` — connection to your qBittorrent instance       |
| **sonarr**      | `host`, `port`, `api_key` — optional, leave blank to disable              |
| **radarr**      | `host`, `port`, `api_key` — optional, leave blank to disable              |
| **guardian**    | `check_interval_seconds` (0 = webhook mode), extension lists, stalled/seedless rules, file priorities |
| **notifications** | `apprise_url` — Apprise-compatible URL (see [Apprise docs](https://github.com/caronc/apprise)) |
| **webui**       | `user`, `password` — HTTP Basic Auth credentials. Leave both empty for public access |

### Web UI Authentication

To password-protect the dashboard, fill in `webui.user` and `webui.password`. The browser will prompt for credentials on every visit. Leave both empty to keep the page public.

> ⚠️ If you forget the password, edit `config.json` directly and clear both fields.

## Operating Modes

### Polling (default)

The guardian checks torrents every N seconds. Set `guardian.check_interval_seconds` to any value above 0. Default: 300 seconds (5 minutes).

### Webhook (real-time)

Set `check_interval_seconds` to `0` and configure qBittorrent to call the guardian on every new torrent:

**1.** In qBittorrent: **Settings → Downloads → Run external program on torrent added**:

```
/scripts/qbit-guardian-hook.sh
```

**2.** Mount the webhook script into your qBittorrent container:

```yaml
# In your qBittorrent docker-compose service:
volumes:
  - ./path/to/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
```

When a torrent is added, qBittorrent calls the script, which sends `POST /api/trigger` to the guardian — processing the torrent instantly.

## REST API

The Web UI exposes these endpoints:

| Method   | Endpoint       | Auth     | Description                                      |
|----------|----------------|----------|--------------------------------------------------|
| `GET`    | `/api/health`  | Public   | Healthcheck — returns `{"status": "ok"}`         |
| `GET`    | `/api/config`  | Required | Read current configuration (full JSON)           |
| `POST`   | `/api/config`  | Required | Save configuration (JSON body, deep merge)       |
| `POST`   | `/api/trigger` | Required | Force an immediate check (manual or webhook)     |

### Example: trigger a check

```bash
curl -X POST http://your-host:5000/api/trigger \
  -u admin:your-password
```

### Example: update config via API

```bash
curl -X POST http://your-host:5000/api/config \
  -u admin:your-password \
  -H "Content-Type: application/json" \
  -d '{"guardian": {"check_interval_seconds": 120}}'
```

## Environment Variables

| Variable       | Default        | Description                    |
|----------------|----------------|--------------------------------|
| `CONFIG_PATH`  | `./config.json` | Path to the config file       |
| `LOG_LEVEL`    | `ERROR`         | Log verbosity (see [Log Levels](#log-levels)) |

## Log Levels

qbit-guardian can output different amounts of detail in its logs. Choose the level that matches your needs:

| Level    | What you'll see |
|----------|----------------|
| `ERROR`  | Only problems: removed torrents, connection failures. The default — quiet and focused. |
| `INFO`   | ERROR plus a summary line after each check: "Check #42: 23 torrents, 2 new, 1 removed". Good for knowing the guardian is alive and working. |
| `VERBOSE` | INFO plus one line per torrent action: "[Movie.Name.2026] stalled (stalledDL) for >5h — REMOVED", "[TV.Show.S01] optimized". Ideal for understanding *why* a torrent was removed. |
| `DEBUG`   | Everything: HTTP calls, URLs, payloads. Very noisy — use only for troubleshooting integrations (Sonarr, Radarr, qBittorrent). |

### Setting the log level

**Docker (recommended):** Add the `LOG_LEVEL` environment variable to your `docker-compose.yml`:

```yaml
services:
  qbit-guardian:
    environment:
      - LOG_LEVEL=VERBOSE
```

Then recreate the container:

```bash
docker compose up -d
```

**Manual install:** Set the variable before starting:

```bash
LOG_LEVEL=DEBUG python app/app.py
```

> 💡 **What is a log level?** Think of it as a volume knob for your logs. Turn it down (`ERROR`) and you only hear about problems. Turn it up (`DEBUG`) and you hear every detail — useful when something isn't working and you need to investigate.

### Example output

Here's what you'd see after one check with `LOG_LEVEL=VERBOSE`:

```
2026-06-22 14:35:01,012 [VERBOSE] [Movie.Name.2026.1080p] optimized (2 media files prioritized)
2026-06-22 14:35:01,123 [VERBOSE] [TV.Show.S01E05.1080p] optimized (1 media files prioritized)
2026-06-22 14:35:01,234 [VERBOSE] [Old.Release.2025.720p] stalled (stalledDL) for >5h — REMOVED
2026-06-22 14:35:01,456 [INFO   ] Check #1: 23 torrents, 23 new, 2 removed
```

With `LOG_LEVEL=ERROR` (the default), you'd only see the removal line and any connection errors — nothing else.

## Troubleshooting

### "Connection refused" or "Failed to connect to qBit"

- Make sure qBittorrent is running and its Web UI is enabled.
- Check that `qbit.host` and `qbit.port` are correct in `config.json`.
- **Docker users:** `localhost` inside a container points to the container itself, not your host. Use `host.docker.internal` (Windows/Mac) or your host machine's real IP (Linux, e.g. `172.17.0.1`).

### "HTTP 403" / "Unauthorized"

Your API key is wrong or empty.
- In qBittorrent: **Tools → Options → Web UI**.
- Make sure authentication is enabled (user `admin` + a password).
- Copy the API Key exactly — no extra spaces or line breaks.

### Web UI doesn't open on port 5000

- Check if the container is running: `docker ps | grep qbit-guardian`
- For manual installs, look for `Web UI em http://0.0.0.0:5000` in the terminal output.
- Ensure your firewall allows port 5000.
- Try accessing from another machine on the same network.

### I don't use Sonarr or Radarr

Leave the `sonarr.host` and `radarr.host` fields empty. The guardian works fine without them — you'll still get dangerous file removal, stalled/seedless cleanup, and file priority optimization. Only blocklisting and re-search are skipped.

## Development

```bash
# Install dependencies (includes pytest)
pip install -r requirements.txt

# Run all tests (79: 59 functional + 20 security)
python -m pytest test/ -v

# Functional tests only
python -m pytest test/test_guardian.py -v

# Security tests only
python -m pytest test/test_security.py -v
```

CI runs on every push and pull request via GitHub Actions (`.github/workflows/test.yml`).

## Documentation

- 📖 [English docs](docs/en-US/) — detailed guides and reference
- 📖 [Documentação em português](docs/pt-BR/) — guias detalhados e referência

## License

**GNU General Public License v3.0** — see [LICENSE](LICENSE).

This software is free: you may use, study, modify, and redistribute it under the terms of the GPLv3. Any derivative work **must** be distributed under the same license. Closed-source or proprietary derivatives are not permitted.
