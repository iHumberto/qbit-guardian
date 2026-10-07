# Frequently Asked Questions (FAQ)

> Direct answers to the most common questions about qbit-guardian.

---

## Why does the page ask for a password now?

Since **version 2.2.0** the Web UI always requires authentication. It used to be public by default, and that was a serious problem: port 5000 is exposed on your network, and `GET /api/config` returned, in plain text, your qBittorrent, Sonarr and Radarr API keys plus the Apprise URL — which usually embeds your Telegram bot token.

There is no sign-up screen. On first run the guardian **generates the password itself** and prints it to the log:

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

If you **already had** `webui.user` and `webui.password` filled in before upgrading, nothing changes: the password you were using keeps working and is converted to a hash on first startup.

---

## How do I change the username or password?

In the panel, click the **user icon** in the top-right corner. The popup asks for:

- **Username** — only if you want to change the name.
- **Current password** — always, as proof of identity.
- **New password** — only if you want to change the password (minimum 8 characters).

Leave blank whatever you don't want to change. After saving you return to the login page, because the change ends every open session.

From the command line:

```bash
curl -X POST http://your-server:5000/api/credentials \
  -u admin:current-password \
  -H "Content-Type: application/json" \
  -d '{"current_password": "current-password", "new_password": "new-strong-password"}'
```

---

## I forgot the password. Now what?

Open `config.json` (in the `config` folder if you use Docker), leave `webui.password` empty and restart:

```json
{
  "webui": {
    "user": "admin",
    "password": ""
  }
}
```

```bash
docker compose restart qbit-guardian
docker logs qbit-guardian
```

A new password is generated and announced in the log.

---

## Login says "too many attempts". What is that?

Brute-force protection: **5 wrong attempts in 5 minutes** block that client, and the block applies **even to the correct password** — otherwise you could just miss four times and hit on the fifth at no cost.

Wait a few minutes and try again. The count is per client, so other people on the network are unaffected.

---

## Can I make the page public again?

You can, but think twice: the page exposes your API keys.

Leave both `webui.user` and `webui.password` **empty** in `config.json`. Authentication stays off while they are.

> ⚠️ The next container restart generates a new password and turns authentication back on. The escape hatch exists for setups already protected another way — a reverse proxy with SSO, for example — not for permanent use.

---

## The container exits right after starting, complaining about permissions

Since **version 2.2.0** the container runs as an unprivileged user (UID 1000) instead of root. If the `config` folder was created by an older version, it belongs to root and the process cannot write to it.

The log prints the fix itself:

```bash
sudo chown -R 1000:1000 ./config
docker compose up -d qbit-guardian
```

It's a single command, and only needs doing once.

---

## The webhook stopped working after I updated

`/api/trigger` now requires authentication. Without credentials the guardian answers `401` and the script has no way to report that a torrent arrived.

Add these variables to the **qBittorrent** service in `docker-compose.yml`:

```yaml
services:
  qbittorrent:
    environment:
      - QBIT_GUARDIAN_URL=http://qbit-guardian:5000
      - QBIT_GUARDIAN_USER=admin
      - QBIT_GUARDIAN_PASS=your-web-ui-password
```

The script writes to qBittorrent's stderr when it fails, including whether the cause was a missing password.

> 💡 If you change the password in the panel, update `QBIT_GUARDIAN_PASS` too.

---

## Why wasn't a torrent removed?

There are a few reasons a torrent stays active after the guardian looked at it:

**1. The torrent is already complete.** Torrents that finished downloading and are seeding (`uploading`, `stalledUP`, `pausedUP`, `checkingUP`, `queuedUP`) are **never touched**. You already have the files — deleting them makes no sense.

**2. The torrent was processed before.** The guardian keeps a list of torrents it has analyzed. If it passed an earlier check and wasn't considered problematic, it isn't re-analyzed for dangerous files.

> The **stalled** and **seedless** rules, however, are re-evaluated every cycle, including for already-processed torrents. A torrent that stalls later is still caught.

**3. The stalled/seedless time hasn't been reached.** If you set "6 hours", a torrent stalled for 3 hours won't be removed yet.

**4. The time is set to `0`.** Zero means **off**, not "remove now".

**5. The extension isn't on the list.** Check **Dangerous extensions** in the panel.

**6. The interval hasn't elapsed.** In polling mode the guardian only checks every N seconds. Use **Force check** to skip the wait.

**7. The magnet hasn't fetched its files yet.** A torrent without metadata can't be analyzed. It is re-evaluated next cycle — the log shows `sem metadados — sera reavaliado no proximo ciclo`.

---

## What are dangerous extensions? Can I customize them?

**Dangerous extensions** are file endings (`.exe`, `.scr`, `.bat`, etc.) known for spreading viruses. If qbit-guardian finds any file with one of these inside a torrent, it removes the whole torrent immediately — **along with the files on disk**.

The default list is:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

**Yes, you can customize it.** In the **Guardian** section of the panel, edit the **Dangerous extensions** field, one per line.

Examples of when to customize:

- You download games and trust `.exe` from certain sources → remove `.exe` from the list.
- You want extra protection against disguised `.iso` → add `.iso`.
- You want to block `.zip` and `.rar` that may hide viruses → add them.

> ⚠️ **Careful:** Removing `.exe` from the list costs you the guardian's main protection. Executables are the most common virus vector in torrents.

---

## What if I leave the media extension list empty?

The "no valid media file" criterion is **disabled**: no torrent is removed for that reason. Dangerous-extension detection keeps working normally.

Useful if you download things that aren't video (documents, software, music) and don't want the guardian treating that as suspicious.

---

## What is the difference between polling and webhook?

| | Polling | Webhook |
|---|---------|---------|
| **How it works** | The guardian checks every so often | qBittorrent notifies it the moment a torrent is added |
| **Speed** | Up to N seconds of delay | Immediate |
| **Setup** | Just the interval in the panel | Script mounted in qBittorrent + credentials |
| **When to use** | General use, simpler | When you want instant removal |

To enable the webhook, put `0` in **Check interval** and follow the steps in [Setting up the Webhook](INSTALL.md#setting-up-the-webhook-real-time).

> 💡 In webhook mode the guardian doesn't run periodic cycles — it only answers calls. The healthcheck knows that and doesn't report a problem.

---

## Do I need Sonarr or Radarr to use qbit-guardian?

**No.** They are optional.

Without them the guardian still removes dangerous files, stalled and seedless torrents, and adjusts priorities. What you lose is release blocklisting and the automatic search for an alternative version.

To disable the integration, leave the Sonarr and Radarr **URL** fields blank.

---

## How do I test that qbit-guardian is working?

### Quick test: healthcheck

```bash
curl http://your-server:5000/api/health
```

Expected response: `{"status": "ok"}`. This endpoint is **public** — no password needed, because Docker uses it.

### Real test: force a check

On the control page, click **Force check**. Or from the command line, with credentials:

```bash
curl -X POST http://your-server:5000/api/trigger -u admin:your-password
```

The response tells you what happened:

```json
{"status": "ok", "checked": 30, "new": 2, "stalled_removed": 1}
```

### Checking the logs

```bash
# Docker
docker logs qbit-guardian

# Manual install: messages appear in the terminal
```

Look for `Conectado ao qBittorrent v...` — that means the connection succeeded. If you see `qBittorrent indisponivel`, something is wrong with the URL or the API Key.

> 💡 With `LOG_LEVEL=ERROR` (the default) the log is very quiet. To investigate, raise it temporarily to `LOG_LEVEL=INFO` or `VERBOSE`.

---

## Does qbit-guardian work with other torrent clients?

**No.** It was built exclusively for **qBittorrent**.

It uses qBittorrent's API to list torrents, inspect files, remove them and adjust priorities — all specific to that client. Transmission, Deluge and uTorrent have different APIs and are not compatible.

There is room for future evolution. If you're interested, watch the releases or contribute.

---

## How do I know which version I'm running?

### Docker

```bash
docker inspect qbit-guardian --format '{{.Config.Image}}'
```

You will see something like `ghcr.io/ihumberto/qbit-guardian:latest` or a specific tag.

### Manual install

```bash
cd qbit-guardian
git log -1 --oneline
```

Either way, the [CHANGELOG](https://github.com/iHumberto/qbit-guardian/blob/main/CHANGELOG.md) lists what changed in each version.

---

## Does qbit-guardian send data to the internet?

**No.** All processing happens locally, inside your server.

The only network connections it makes are:

- To **qBittorrent** (on your local network) — to manage torrents.
- To **Sonarr/Radarr** (on your local network) — if you enabled the integration.
- To the notification service configured via **Apprise** — only if you set a URL.

No data about your torrents, your library or your configuration leaves your server. The Web UI itself loads nothing from outside: fonts, translations and icons all ship with the application, so the panel opens even without internet.

---

## Can I install it on a Raspberry Pi?

**Yes.** qbit-guardian is light and runs well on a Raspberry Pi (model 3 and above).

The image is multi-architecture, so `docker compose pull` fetches the ARM build automatically. Resource usage is minimal.

---

## Does the program update itself?

**Not on its own.** You update it like this:

- **Docker:** `docker compose pull qbit-guardian && docker compose up -d qbit-guardian`
- **Manual:** `git pull` inside the project folder and restart.

> 💡 If you use **Watchtower** or similar, updates happen automatically. In that case, keep an eye on the release notes: 2.2.0, for instance, required a `chown` on the `config` folder.

---

## How do I back up my configuration?

Copy `config.json` somewhere safe. That's it — the whole configuration lives in that single file.

```bash
cp config/config.json ~/backup-qbit-guardian.json
```

To restore, put the file back and restart the program.

> ⚠️ The backup contains your **API keys** and the Web UI password hash. Treat it with the same care as a password.

---

## Can I contribute to the project?

Yes. The project is **open source** (GPLv3 license). You can:

- Report problems and suggest improvements.
- Send fixes and new features.
- Improve the documentation.

The repository is at: <https://github.com/iHumberto/qbit-guardian>

---

## How do I remove qbit-guardian completely?

### Docker

```bash
docker compose down qbit-guardian
docker rmi ghcr.io/ihumberto/qbit-guardian:latest
```

Then delete the `config` folder and the service block in `docker-compose.yml`. If you set up the webhook, also remove the script volume and the `QBIT_GUARDIAN_*` variables from the qBittorrent service, and clear the **Run external program** field in qBittorrent's options.

### Manual install

```bash
# Stop the program (Ctrl+C in the terminal)
rm -rf /path/to/qbit-guardian
```

No files are installed outside the project folder — removal is complete.

---

## Still have questions?

- Check the [Usage Guide](USAGE.md) for detailed explanations of every feature.
- See the [Installation Guide](INSTALL.md) if you need to reinstall or update.
- Open an issue on the [project repository](https://github.com/iHumberto/qbit-guardian).
