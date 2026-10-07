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
| Testing     | pytest 8.x (703 tests: 585 functional + 118 security) |
| License     | GNU GPL v3                          |

## Features

- 🔍 **Malicious file detection** — removes torrents containing executables, scripts, and other dangerous extensions
- 🎬 **Radarr integration** — blocklist + automatic re-search for movies
- 📺 **Sonarr integration** — blocklist + re-search with episode air-date validation
- 🗑️ **Stalled & seedless removal** — cleans up dead torrents after a configurable time limit
- ⚡ **File priority optimization** — auto-prioritizes media files, lowers or skips junk files
- 🔔 **Apprise notifications** — alerts via Telegram, Discord, Slack, Pushover, and 100+ other services
- 🖥️ **Web UI** — three-column dark layout: external services (qBittorrent, Radarr, Sonarr) on the left, Guardian settings in the middle, notifications on the right. Mandatory HTTP Basic Auth, with credentials changeable from the panel itself
- 🪝 **Webhook mode** — real-time processing on torrent addition (no polling delay)
- 🐳 **Docker-first** — pre-built image on `ghcr.io`, healthcheck included

## ⚠️ Upgrading to 2.2.0

Two changes need action from you. Do this **before** pulling the new image:

**1. The config folder must be owned by UID 1000.** The container no longer runs as root. In your `docker-compose.yml` folder:

```bash
sudo chown -R 1000:1000 ./config
```

Without it the container exits immediately and prints that same command to the log.

**2. If you use webhook mode,** set `QBIT_GUARDIAN_PASS` on the qBittorrent service — see [Webhook Mode](#webhook-mode-real-time). `/api/trigger` now requires authentication.

After starting, get the Web UI password with `docker logs qbit-guardian` (see [Web UI Authentication](#web-ui-authentication)). If you already had a username and password configured, they keep working.

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
      test: ["CMD", "python", "app/healthcheck.py"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
```

> The healthcheck checks the **age** of the heartbeat, not just whether the file exists — so a stalled loop is detected instead of reporting `healthy` forever. The tolerance is `max(600s, 3 × check_interval_seconds, 3 × retry_interval_seconds)`: the retry counts because, while qBittorrent is down, the heartbeat is written at the retry's pace.

Then start:

```bash
docker compose up -d
```

On first run, the system creates the configuration automatically — no manual JSON editing needed. Open `http://your-host:5000` to fill in all settings through the Web UI.

> 💡 **What is an API key?** It's a long random password that qBittorrent generates so other programs (like qbit-guardian) can talk to it securely. Find yours in qBittorrent at **Tools → Options → Web UI → API Key**.

### Web UI Layout

The configuration page is split into three columns:

- **Left column**: Connections to your external services — qBittorrent, Radarr and Sonarr.
- **Middle column**: All Guardian settings — check interval, file extensions, file priorities, and stalled/seedless removal rules.
- **Right column**: Apprise notifications.

The header carries a **Docs** icon — hover it for a hint, click it to open this project's documentation in your language — and the language selector.

Below 1200 px the three columns stack vertically, so the page stays usable on tablets and phones without squeezing the longer labels.

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
    "url": "http://localhost:8080",
    "api_key": ""
  },
  "sonarr": {
    "url": "",
    "api_key": ""
  },
  "radarr": {
    "url": "",
    "api_key": ""
  },
  "guardian": {
    "check_interval_seconds": 300,
    "retry_interval_seconds": 120,
    "valid_media_extensions": [
      ".mkv",
      ".mp4",
      ".avi",
      ".mov",
      ".m4v",
      ".ts",
      ".wmv",
      ".flv",
      ".webm"
    ],
    "dangerous_extensions": [
      ".exe",
      ".scr",
      ".bat",
      ".cmd",
      ".vbs",
      ".js",
      ".com",
      ".pif",
      ".msi",
      ".dll",
      ".ps1",
      ".sh",
      ".bin"
    ],
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
    "apprise_url": "",
    "enabled": true,
    "events": {
      "optimized": {
        "enabled": true,
        "title": "⚡ Torrent Otimizado",
        "template": "Nome: {{torrentName}}\nArquivos de midia priorizados."
      },
      "removed": {
        "enabled": true,
        "title": "⚠️ Torrent Removido",
        "template": "Nome: {{torrentName}}\nMotivo: {{reason}}"
      },
      "stalled": {
        "enabled": true,
        "title": "🗑️ Torrent Removido (stalled)",
        "template": "Nome: {{torrentName}}\nMotivo: {{reason}}"
      }
    }
  },
  "webui": {
    "user": "",
    "password": ""
  }
}
```

| Section         | Key fields                                                                 |
|-----------------|---------------------------------------------------------------------------|
| **qbit**        | `url` (scheme + host + port), `api_key` — connection to your qBittorrent instance |
| **sonarr**      | `url`, `api_key` — optional, leave blank to disable                      |
| **radarr**      | `url`, `api_key` — optional, leave blank to disable                      |
| **guardian**    | `check_interval_seconds` (0 = webhook mode), `retry_interval_seconds`, extension lists, stalled/seedless rules, file priorities |
| **notifications** | `apprise_url` — Apprise-compatible URL (see [Apprise docs](https://github.com/caronc/apprise)) |
| **webui**       | `user`, `password`, `secret_key` — provisioned on first startup. The password is stored as a PBKDF2 hash; `secret_key` signs the session cookie |

### Notification messages

Each notification type has its own text — editable in the Web UI or directly in `config.json` — and its own on/off switch, on top of the section's master switch. A message is only sent when **both** are on; while a message is off its text stays visible in the Web UI but cannot be edited.

The default texts reproduce exactly the messages from earlier versions: updating without touching your configuration keeps the notifications you already get. Clearing a box falls back to the default instead of sending an empty notification.

Inside the text, each `{{...}}` from the table below is replaced with the torrent's value. An unknown variable is left literal in the message, so a typo shows up instead of silently disappearing.

| Event | Key under `events` | Available variables |
|-------|--------------------|---------------------|
| Torrent optimised | `optimized` | `{{torrentName}}` `{{priorityMedia}}` `{{priorityAux}}` `{{mediaCount}}` |
| Torrent removed (dangerous / no media) | `removed` | `{{torrentName}}` `{{reason}}` `{{extensions}}` |
| Torrent removed (stalled / seedless) | `stalled` | `{{torrentName}}` `{{reason}}` `{{state}}` `{{stalledTime}}` |

| Variable | Meaning |
|----------|---------|
| `{{extensions}}` | dangerous extensions found (empty when the reason was no valid media) |
| `{{mediaCount}}` | how many media files were prioritised |
| `{{priorityAux}}` | priority applied to auxiliary files (`.nfo`, `.srt`, `.jpg`…) |
| `{{priorityMedia}}` | priority applied to media files |
| `{{reason}}` | removal reason |
| `{{stalledTime}}` | configured stalled threshold (empty when the removal was for lack of seeds) |
| `{{state}}` | torrent state in qBittorrent (`stalledDL`, `metaDL`…) |
| `{{torrentName}}` | torrent name |

Each notification's **title** (`events.<event>.title`) is not exposed in the Web UI but remains editable in `config.json`.

### Web UI Authentication

**The Web UI requires authentication.** There is no sign-up screen: on first boot the guardian **generates the password itself** and prints it to the container log.

```bash
docker logs qbit-guardian
```

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================
```

That password is shown **once**, when it is created. Save it.

The Web UI has its own **login page** at `/login`. Anyone without a session is redirected there; `curl` and scripts keep using HTTP Basic Auth as before.

To change the username or password, click the **user icon** in the top-right corner of the panel. The popup asks for the current password (proof of identity), the new username and the new password — either one can be left blank if you only want to change the other.

The password is stored as a **PBKDF2-SHA256 hash** with a per-password salt. It is never kept in plain text in `config.json` and never returned by `GET /api/config`.

Once signed in, the session lasts 7 days in a signed `HttpOnly` cookie. Changing the username or the password **invalidates every open session**. To sign out, use the **Sign out** button in the same user-icon popup.

> After 5 failed attempts within 5 minutes, login answers `429` for that client — even if the next password is correct.

> **Forgot the password?** Clear the `webui.password` value in `config.json` and restart the container. A new password is generated and announced in the log.

> **Upgrading from before 2.2.0?** If you already had `webui.user`/`webui.password` filled in, nothing changes: the password you were using keeps working and is converted to a hash on first startup. If the fields were empty, a password is generated and shown in the log.

Leaving `webui.user` and `webui.password` empty still disables authentication — for setups already protected another way, such as a reverse proxy with SSO. But the next container restart generates a new password and turns it back on.

## Operating Modes

### Polling (default)

The guardian checks torrents every N seconds. Set `guardian.check_interval_seconds` to any value above 0. Default: 300 seconds (5 minutes).

### Reconnecting to qBittorrent

If qBittorrent isn't reachable — typically when the server reboots and the guardian comes up first — the guardian **doesn't give up**: it logs a `WARNING` and retries every `guardian.retry_interval_seconds` (default: 120 seconds) until it connects. The same applies if qBittorrent goes down later, while already running.

The heartbeat keeps being written during the retry: the healthcheck measures the health of the guardian **process**, not qBittorrent's — that's an external, transient dependency. So the container stays `healthy` while retrying; watch the log to see the outage.

> If you raise `retry_interval_seconds`, the healthcheck tolerance grows with it (3×), so a long retry can't get the container marked `unhealthy` on its own.

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
environment:
  - QBIT_GUARDIAN_URL=http://qbit-guardian:5000
  - QBIT_GUARDIAN_USER=admin
  - QBIT_GUARDIAN_PASS=your-web-ui-password
```

When a torrent is added, qBittorrent calls the script, which sends `POST /api/trigger` to the guardian — processing the torrent instantly.

> ⚠️ **`QBIT_GUARDIAN_PASS` is required as of v2.2.0.** `/api/trigger` requires authentication; without the password the guardian answers 401 and webhook mode stops working. The script reports this on qBittorrent's stderr.

## REST API

The Web UI exposes these endpoints:

| Method   | Endpoint             | Auth      | Description                                                    |
|----------|----------------------|-----------|----------------------------------------------------------------|
| `GET`    | `/api/health`        | Public    | Healthcheck — returns `{"status": "ok"}`                       |
| `GET`    | `/login`             | Public    | Login page (redirects to `/` if a session already exists)      |
| `POST`   | `/api/login`         | Public    | Exchanges username and password for a session cookie. `429` after 5 failures |
| `POST`   | `/api/logout`        | Public    | Ends the session                                               |
| `GET`    | `/api/config`        | Required  | Reads the current configuration. Does **not** return `webui.password` |
| `POST`   | `/api/config`        | Required  | Saves configuration (deep merge). The `webui` section is ignored here |
| `GET`    | `/api/defaults`      | Required  | Default titles/templates and variables for each event          |
| `POST`   | `/api/credentials`   | Required  | Changes the Web UI username and/or password                    |
| `POST`   | `/api/trigger`       | Required  | Forces an immediate check (manual or webhook)                  |

Every write endpoint requires `Content-Type: application/json` (except `/api/trigger`, which has no body) and rejects requests triggered by another site — that is the CSRF protection. Command-line clients such as `curl` are unaffected.

### Example: change the Web UI password

```bash
curl -X POST http://your-host:5000/api/credentials \
  -u admin:current-password \
  -H "Content-Type: application/json" \
  -d '{"current_password": "current-password", "new_password": "new-strong-password"}'
```

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
- Check that `qbit.url` is correct in `config.json` — it includes the scheme, host and port (e.g. `http://192.168.1.10:8080`).
- **Docker users:** `localhost` inside a container points to the container itself, not your host. Use `host.docker.internal` (Windows/Mac) or your host machine's real IP (Linux, e.g. `172.17.0.1`).
- The guardian **keeps retrying** instead of exiting, so this shows up as a repeating `WARNING` in the log, not as a dead container. Fix the URL or bring qBittorrent up and the next retry connects on its own — no restart needed.

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

Leave the `sonarr.url` and `radarr.url` fields empty. The guardian works fine without them — you'll still get dangerous file removal, stalled/seedless cleanup, and file priority optimization. Only blocklisting and re-search are skipped.

## Development

```bash
# Install dependencies (runtime + test tooling)
pip install -r requirements-dev.txt

# Run all tests (703: 585 functional + 118 security)
python -m pytest test/ -v

# Functional tests only
python -m pytest test/test_guardian.py -v

# Security tests only
python -m pytest test/test_security.py -v

# Coverage (settings in .coveragerc)
python -m coverage run -m pytest test/ && python -m coverage report
```

CI runs on every push and pull request via GitHub Actions (`.github/workflows/test.yml`). The image build (`docker-build.yml`) depends on that suite, so nothing is published to the GHCR with failing tests.

## Documentation

Step-by-step guides for newcomers, in English and Portuguese:

| Guide | What for |
|-------|----------|
| [Getting Started](docs/en-US/getting-started.md) | Install and sign in for the first time |
| [Install](docs/en-US/INSTALL.md) | Docker, manual install, webhook mode and troubleshooting |
| [Usage](docs/en-US/USAGE.md) | Every panel feature, in detail |
| [FAQ](docs/en-US/FAQ.md) | Common questions and known errors |

- 📖 [Documentação em português](docs/pt-BR/) — [Primeiros Passos](docs/pt-BR/primeiros-passos.md) · [Instalação](docs/pt-BR/INSTALL.md) · [Uso](docs/pt-BR/USAGE.md) · [FAQ](docs/pt-BR/FAQ.md)

## License

**GNU General Public License v3.0** — see [LICENSE](LICENSE).

This software is free: you may use, study, modify, and redistribute it under the terms of the GPLv3. Any derivative work **must** be distributed under the same license. Closed-source or proprietary derivatives are not permitted.
