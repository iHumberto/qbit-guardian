# 🛡️ Usage Guide

> How to set up and use qbit-guardian to keep your torrents safe.

---

## What is qbit-guardian?

qbit-guardian watches the torrents in your qBittorrent and removes the bad ones — automatically. No need to check each file yourself.

It protects you in three ways:

- **Dangerous files** — torrents containing `.exe`, `.scr`, `.bat`, and other executable or script files are removed right away. These files can hide viruses.
- **Stalled downloads** — torrents that have been stuck for too long (no progress) are cleaned up.
- **No seeds** — if nobody is sharing the complete file anymore, the torrent is deleted because you'll never finish it.

> 💡 **Seed** (or seeder) is someone who already has the whole file and keeps sharing it. Zero seeds = no way to finish the download.

If you use **Sonarr** (TV series) or **Radarr** (movies), qbit-guardian also blocks the bad release and tells Sonarr/Radarr to search for a better copy. Your library keeps growing without you lifting a finger.

---

## Accessing the Web UI

Once qbit-guardian is running, open your browser and go to:

```
http://your-server-address:5000
```

Examples:

| Your setup                  | Address to type               |
|-----------------------------|-------------------------------|
| Same computer               | `http://localhost:5000`       |
| Another computer on your network | `http://192.168.1.100:5000`  |

You will see a dark dashboard with two columns: **external services** (qBittorrent, Sonarr, Radarr, Notifications) on the left and **Guardian** on the right, with a centered **Save Configuration** button below.

### Language

Every page of the Web UI has a language dropdown in the top-right corner:

- 🇧🇷 **PT-BR (default):** The interface opens in Brazilian Portuguese the first time you visit.
- 🇺🇸 **EN-US:** Switches the entire interface to American English.

Switching is instant — no page reload needed. Your browser remembers your choice: switch to English, close the page, and when you come back it opens in English automatically.

> 💡 The selector works offline. All translations are built right into the application — no external translation services are used. Your language preference is saved in your browser (localStorage).

---

## Configuration

### Required: qBittorrent connection

These two fields are the only ones you **must** fill in for qbit-guardian to work:

| Field                | What to enter                                                                 |
|----------------------|-------------------------------------------------------------------------------|
| **URL**              | The full address where qBittorrent is running (e.g. `http://192.168.1.50:8080`) |
| **API Key**          | The long random password from qBittorrent's settings                          |

> 💡 **API Key** is a secret code that qBittorrent creates so other programs (like qbit-guardian) can talk to it safely. Find yours in qBittorrent: **Tools → Options → Web UI → API Key**. Copy it exactly — no extra spaces.

The URL defaults to `http://localhost:8080`, which is qBittorrent's standard port on your local machine. Change it only if qBittorrent runs on a different machine or port.

Click **Save Configuration** and the guardian starts watching. By default it checks every 5 minutes (300 seconds).

### Optional: Sonarr and Radarr

If you use Sonarr (TV series) or Radarr (movies), fill in their URL and API key. This lets qbit-guardian automatically block bad releases and trigger a new search.

If you don't use Sonarr or Radarr, just leave those fields blank. The guardian still removes dangerous files, stalled torrents, and seedless torrents — only the blocklist and re-search steps are skipped.

### Optional: Apprise notifications

qbit-guardian can send you alerts when it takes action. It uses **Apprise**, a tool that connects to over 100 notification services: Telegram, Discord, Slack, Pushover, email, and many more.

1. Go to the [Apprise documentation](https://github.com/caronc/apprise) and build a notification URL for your service.
2. Paste that URL into the **Apprise URL** field.
3. Save the configuration.

Examples of Apprise URLs:

| Service    | URL format                                               |
|------------|----------------------------------------------------------|
| Telegram   | `tgram://BOT_TOKEN/CHAT_ID`                              |
| Discord    | `discord://WEBHOOK_ID/WEBHOOK_TOKEN`                      |
| Slack      | `slack://TOKENA/TOKENB/TOKENC/CHANNEL`                   |
| Gotify     | `gotify://hostname/token`                                |

Events that trigger a notification:

- ⚠️ **Dangerous file removed** — torrent deleted because it contained `.exe`, `.scr`, etc.
- 🗑️ **Stalled torrent removed** — torrent stuck for longer than your time limit.
- ⚡ **Torrent optimized** — media files were prioritized, junk files were lowered or skipped.

> 💡 **Apprise** is like a universal adapter for notifications. Instead of learning how to send messages to each service, you build one URL and Apprise handles the rest.

### Connecting to a self-signed Apprise (homelab)

If your Apprise server uses a self-signed SSL certificate (common in home networks with addresses like `apprise.home.arpa` or `apprise.local`), the guardian is already configured to work without SSL verification.

> **📘 Self-signed SSL certificate:** A security certificate you create yourself, without paying for a commercial one. Your browser and other programs don't trust it automatically.

qbit-guardian **always** disables SSL verification for Apprise calls (`verify=False`), since this project is designed for homelab/local networks where self-signed certificates are normal. No additional configuration is needed.

Just set the Apprise URL in `config.json`:

```json
{
  "notifications": {
    "apprise_url": "https://apprise.home.arpa/notify/guardian"
  }
}
```

---

## Dangerous and media extensions

### Dangerous extensions

These are file types that often carry viruses or malware. By default, qbit-guardian removes any torrent that contains:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

You can change this list in the Web UI by editing the **Dangerous Extensions** field. Add or remove entries as needed — each one starts with a dot (e.g. `.scr`).

> ⚠️ **Be careful.** Removing entries from this list makes the guardian less strict. Only do it if you're sure those file types are safe in your setup.

### Valid media extensions

The guardian also checks if a torrent has at least one media file. The default list includes common video formats:

`.mkv` `.mp4` `.avi` `.mov` `.m4v` `.ts` `.wmv` `.flv` `.webm`

If a torrent has no dangerous files but also no valid media file, it's still removed — it's likely junk.

You can customize this list too, for example if you want to include `.ogv`, `.divx`, or other video formats.

---

## Operating Modes

qbit-guardian can run in two modes. Choose the one that fits your needs.

### Polling mode (default)

The guardian checks all your torrents every N seconds. Set **Check Interval** to any number above 0.

| Setting   | Behavior                                                       |
|-----------|----------------------------------------------------------------|
| `300`     | Check every 5 minutes (default)                                |
| `60`      | Check every minute — more responsive, uses a bit more CPU      |
| `600`     | Check every 10 minutes — less frequent, lighter on resources   |
| `3600`    | Check every hour                                               |

This is the simplest mode. It works without any extra setup on qBittorrent's side.

### Webhook mode (real-time)

Set **Check Interval** to `0` and the guardian stops polling. Instead, it waits for qBittorrent to call it directly whenever a new torrent is added.

This mode reacts instantly — no waiting for the next poll cycle.

#### How to set up webhook mode

**Step 1: Change the interval to 0**

In the Web UI, set **Check Interval** to `0` and save.

**Step 2: Configure qBittorrent**

Open qBittorrent and go to **Settings → Downloads**. At the bottom, find **Run external program on torrent added** and enter:

```
/scripts/qbit-guardian-hook.sh
```

**Step 3: Mount the hook script into qBittorrent**

If you use Docker for qBittorrent, add this volume to your qBittorrent service in `docker-compose.yml`:

```yaml
services:
  qbittorrent:
    # ... your existing qBittorrent config ...
    volumes:
      - ./scripts/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
```

The script is located in the `scripts/` folder of the qbit-guardian repository. Download it from there or copy the content below:

```bash
#!/bin/bash
QBIT_GUARDIAN_URL="${QBIT_GUARDIAN_URL:-http://qbit-guardian:5000}"
curl -s -X POST "${QBIT_GUARDIAN_URL}/api/trigger" > /dev/null 2>&1
```

> 💡 The script uses a variable `QBIT_GUARDIAN_URL` so you can adjust the guardian's address without editing the script. The default (`http://qbit-guardian:5000`) works when both containers are on the same Docker network and the guardian container is named `qbit-guardian`.

Now, every time qBittorrent adds a new torrent, it calls the script, which instantly tells qbit-guardian to check it. No waiting.

---

## Web UI Authentication

By default, the dashboard is open — anyone on your network can access it. To protect it with a password:

1. In the Web UI, scroll to the **Web UI Authentication** section.
2. Enter a **Username** (e.g. `admin`) and a **Password**.
3. Save the configuration.

Your browser will now ask for credentials before showing the page.

You can also set this directly in `config.json`:

```json
{
  "webui": {
    "user": "admin",
    "password": "your-strong-password-here"
  }
}
```

> ⚠️ **Forgot the password?** Edit `config.json` directly and clear both `user` and `password` (set them to `""`). The page becomes public again and you can set a new password through the Web UI.

When both fields are empty, authentication is off and the page is public.

---

## Understanding torrent statuses

When qbit-guardian processes a torrent, here is what each status means:

| Status        | Meaning                                                                                            |
|---------------|----------------------------------------------------------------------------------------------------|
| **completed** | The torrent finished downloading. The guardian skips it — the file is already on your disk.       |
| **dangerous** | The torrent contains at least one file with a dangerous extension (`.exe`, `.bat`, etc.). It gets removed immediately. |
| **stalled**   | The torrent has made no progress for longer than your time limit. It gets removed.                 |
| **no_seeds**  | The torrent has zero seeds and has been in that state longer than your time limit. It gets removed. |
| **no_media**  | The torrent has no dangerous files, but also no valid media files (`.mkv`, `.mp4`, etc.). It gets removed as junk. |

### Configuring stalled and seedless removal

Both are **off by default**. To enable them:

| Setting                | What it does                                                       |
|------------------------|--------------------------------------------------------------------|
| **Remove Stalled**     | Turn ON to delete torrents stuck with no progress.                 |
| **Stalled Time**       | How long the torrent must be stuck before removal (e.g. `24`).     |
| **Stalled Unit**       | Unit for the time: `seconds`, `minutes`, or `hours`.              |
| **Remove No Seeds**    | Turn ON to delete torrents that lost all their seeds.              |
| **No Seeds Time**      | How long the torrent must have zero seeds before removal (e.g. `48`). |
| **No Seeds Unit**      | Unit for the time: `seconds`, `minutes`, or `hours`.              |

Example: set **Remove No Seeds** ON, **No Seeds Time** to `48`, and **No Seeds Unit** to `hours`. After two days with nobody sharing the file, the torrent is automatically removed.

---

## Understanding the logs

qbit-guardian logs everything it does. You can see the logs in two ways:

- **Docker:** `docker logs qbit-guardian`
- **Manual install:** directly in the terminal where the program is running

Here's what each message means:

| Log message | What happened |
|-------------|---------------|
| `Dangerous files: ['.exe'] — Removing and Blocking` | The torrent contained an `.exe` and was removed. If Sonarr/Radarr are configured, the release was blocked and a new search started. |
| `No valid media files — Removing and Blocking` | The torrent had no files matching the configured media extensions. It was removed. |
| `stalled (stalledDL) for >6h — Removing` | The torrent was stuck for more than 6 hours. Removed. |
| `0 seeds — Removing` | The torrent had no seeds for longer than the configured time. Removed. |
| `Disabled → filename.exe` | A file inside the torrent was set to priority zero — it won't be downloaded. |
| `Media files prioritized` | Download priorities were adjusted. Video files were moved to the top of the queue. |
| `No new torrents` | The guardian checked and found no unprocessed torrents. Everything is fine. |
| `qBittorrent unreachable, reconnecting...` | The guardian lost contact with qBittorrent. It retries automatically on each cycle. |

### Processed torrent statuses

The guardian keeps an internal list of torrents it has already processed. This prevents the same torrent from being checked multiple times. Possible statuses:

| Status | Description |
|--------|-------------|
| **completed** | Torrents that finished downloading and are now uploading/seeding. The guardian **does not touch** them — they're already done. |
| **dangerous** | Torrents that contained dangerous files. Already removed. |
| **stalled** | Torrents that were removed for being stuck too long. |
| **no_seeds** | Torrents removed for lack of seeds. |
| **no_media** | Torrents removed for having no valid media files. |
| **optimized** | Torrents where file priorities were adjusted. They continue downloading normally. |

---

## Forcing a manual check

If you want the guardian to check torrents right now, without waiting for the interval, use the **Force Check** button on the configuration page.

Or, from the command line:

```bash
curl -X POST http://your-server:5000/api/trigger -u username:password
```

This is useful for testing that everything works after configuring.

---

## Tips and best practices

- **Test without notifications first.** Let the guardian run silently for a few days. Once you're confident in its behavior, enable notifications.
- **A 5-minute interval is enough.** For home use, checking every 300 seconds is fast enough. You don't need 10 seconds — you won't notice the difference and it only wastes resources.
- **Keep dangerous extensions up to date.** New file types used to spread malware appear from time to time. Stay alert.
- **If you use Sonarr/Radarr, take advantage of the integration.** Filling in the integration fields lets the guardian block bad releases and search for alternatives automatically. Your library grows without you lifting a finger.

---

## Need help?

- Read the [Frequently Asked Questions](FAQ.md) for common questions.
- See the [Installation Guide](INSTALL.md) if you need to install from scratch.
- Issues, suggestions, and contributions: [project repository](https://forgejo.home.arpa/Humberto/qbit-guardian).
