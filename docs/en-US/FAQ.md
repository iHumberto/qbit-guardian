# ❓ Frequently Asked Questions

---

## Why wasn't a torrent removed?

There are a few common reasons:

### The torrent is already completed

qbit-guardian only processes **active** torrents — those still downloading. If a torrent finished downloading before the guardian saw it (or before qbit-guardian was installed), it is skipped.

Completed torrents are already on your disk. The guardian's job is to stop bad ones from finishing — it doesn't scan files you already have.

### The torrent was already processed

The guardian remembers which torrents it has already checked. If it analyzed a torrent on a previous cycle and decided it was fine, it won't check it again. Only **new** torrents (ones the guardian hasn't seen yet) are scanned each cycle.

If you want to force a re-check, restart the container or process — the memory resets.

### The stalled time hasn't been reached yet

Stalled and seedless removal have a waiting period. If you set **No Seeds Time** to `48` hours, the torrent needs to have zero seeds for **two full days** before it's removed. A torrent with 15 minutes without seeds won't be touched.

Check your settings:

- **Remove Stalled** / **Remove No Seeds** — are they turned ON?
- **Stalled Time** / **No Seeds Time** — is the value high enough for your needs?
- **Stalled Unit** / **No Seeds Unit** — make sure you didn't set `seconds` when you meant `hours`.

### The torrent has no dangerous files and no media files... but it just started

If a torrent is new and qBittorrent hasn't fetched its file list yet, the guardian may see zero files and skip it. On the next poll cycle (a few minutes later), the files should be visible and the torrent will be analyzed normally.

---

## How do I enable authentication on the Web UI?

In the Web UI, scroll to the **Web UI Authentication** section. Fill in:

- **Username** — any name you want (e.g. `admin`).
- **Password** — a strong password.

Click **Save Configuration**. From now on, your browser will prompt for these credentials whenever you visit the dashboard.

You can also set this directly in `config.json`:

```json
{
  "webui": {
    "user": "admin",
    "password": "my-strong-password"
  }
}
```

To **disable** authentication, clear both fields (set them to `""`). The page becomes public again.

> ⚠️ If you forget your password, edit `config.json` directly and clear the `user` and `password` fields. The dashboard opens up and you can set a new password.

---

## What are dangerous extensions? Can I customize them?

**Dangerous extensions** are file types often used to spread viruses and malware. By default, qbit-guardian blocks:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

These are executable files and scripts — programs that can run on your computer. If a torrent contains any of these, it's removed immediately.

**Yes, you can customize the list.** In the Web UI, edit the **Dangerous Extensions** field. Add or remove entries (each with a dot, like `.exe`). You can also edit `config.json` directly:

```json
{
  "guardian": {
    "dangerous_extensions": [".exe", ".scr", ".bat", ".ps1"]
  }
}
```

> ⚠️ Removing entries makes the guardian less strict. Only do this if you're certain those file types are safe in your environment.

---

## What's the difference between polling and webhook?

|                  | Polling (default)                     | Webhook                              |
|------------------|---------------------------------------|--------------------------------------|
| **How it works** | Checks all torrents every N seconds   | qBittorrent calls the guardian instantly when a torrent is added |
| **Speed**        | Up to N seconds of delay              | Instant — no delay                   |
| **Setup**        | Nothing extra — works out of the box  | Requires a hook script mounted in qBittorrent |
| **Best for**     | Most users, simple setup              | Users who want real-time protection  |

**Polling** is the default. Set the interval to any number above 0 (e.g. `300` for 5 minutes). The guardian wakes up, scans all torrents, and goes back to sleep. Simple and reliable.

**Webhook** sets the interval to `0`. The guardian stops the loop and waits. qBittorrent calls it directly via a small script whenever a new torrent is added. The guardian processes it right away.

To switch to webhook mode:
1. Set **Check Interval** to `0` in the Web UI.
2. Configure qBittorrent to run the hook script: **Settings → Downloads → Run external program on torrent added** → `/scripts/qbit-guardian-hook.sh`.
3. Mount the script into your qBittorrent container and set the `QBIT_GUARDIAN_URL` environment variable if needed. See the step-by-step guide in the [Installation Guide](INSTALL.md#setting-up-webhook-mode-real-time).

> 💡 The hook script is now **non-blocking**: it won't freeze qBittorrent. The script runs in the background with built-in timeouts, a safety sleep, and automatic retry — safe and reliable.

---

## Do I need Sonarr or Radarr to use qbit-guardian?

**No, they are completely optional.**

Without Sonarr or Radarr, you still get:

- ✅ Dangerous file detection and removal (`.exe`, `.scr`, etc.)
- ✅ Stalled torrent cleanup
- ✅ Seedless torrent removal
- ✅ Media file priority optimization
- ✅ Apprise notifications

The **only** things you miss without Sonarr/Radarr are:

- ❌ Automatic blocklisting of bad releases in Sonarr/Radarr
- ❌ Automatic re-search for a replacement release

To disable Sonarr/Radarr integration, simply leave their **Host** fields blank in the Web UI.

---

## How do I test if it's working?

### Quick test: check the logs

**Docker:**
```bash
docker logs qbit-guardian
```

**Manual:** look at the terminal output.

If you see a line like `Conectado ao qBittorrent vX.X.X`, the connection is working.

### Real test: add a safe dummy torrent

1. Create a text file, rename it to `test.exe` (it's still just text — safe).
2. Use qBittorrent to create a `.torrent` file from it, then add it to qBittorrent.
3. Within your configured interval (default: 5 minutes), check the logs. You should see:

   ```
   [your-torrent-name] Arquivos perigosos: ['.exe'] — Removendo e Bloqueando
   ```

4. The torrent disappears from qBittorrent.

In **webhook mode** (`check_interval_seconds=0`), the removal happens instantly.

### Health check (Docker only)

```bash
docker ps | grep qbit-guardian
```

Look for `(healthy)` in the STATUS column.

---

## Does qbit-guardian work with other torrent clients?

**No.** qbit-guardian only works with **qBittorrent**.

It communicates through qBittorrent's specific API — the set of commands that qBittorrent exposes for other programs. Other torrent clients (Transmission, Deluge, rTorrent) have different APIs and are not supported.

If you use another client, you would need a different tool built for that client.

---

## I use Docker. Why can't it connect to qBittorrent?

Inside a Docker container, `localhost` means the container itself — not your computer. If your `config.json` has:

```json
{ "qbit": { "host": "localhost", "port": 8080 } }
```

…the guardian will try to connect to **itself**, not to qBittorrent.

Fix it by using the correct address:

| Your setup                                   | Use this as host                      |
|----------------------------------------------|---------------------------------------|
| qBittorrent on the same machine (Windows/Mac) | `host.docker.internal`                |
| qBittorrent on the same machine (Linux)       | Your machine's real IP (e.g. `192.168.1.50`) |
| qBittorrent in another Docker container      | The container name (e.g. `qbittorrent`) |

---

## How do I stop getting notifications for every optimized torrent?

The guardian sends a notification every time it prioritizes media files in a torrent. If you find these too noisy, you have two options:

1. **Turn off notifications entirely:** clear the **Apprise URL** field and save.
2. **Filter on your notification service side:** many services let you filter by title. Optimization notifications have the title `⚡ Torrent Otimizado` — you can mute or redirect these.

---

## Can I run qbit-guardian on Windows?

The project is designed for Linux and Docker. On Windows:

- **Docker method:** works the same way via Docker Desktop or WSL2.
- **Manual (Python) method:** should work if you have Python 3.10+ installed and follow the same steps, using `.venv\Scripts\activate` instead of `source .venv/bin/activate`. However, this is not officially tested — Docker on Windows is the recommended approach.
