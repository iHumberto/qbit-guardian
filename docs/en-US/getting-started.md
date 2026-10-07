# Getting Started

This guide walks you through installing and opening **qbit-guardian** for the first time.

## What is qbit-guardian?

qbit-guardian watches the torrents in your **qBittorrent** and automatically removes:

- **Dangerous files** — those ending in `.exe`, `.scr`, `.bat` and similar, which may carry viruses.
- **Long-stalled torrents** — downloads that got stuck and will never finish.
- **Seedless torrents** — when nobody is sharing the complete file any more.

> 💡 A **seed** is someone who already downloaded the whole file and keeps uploading it. If a torrent has zero seeds, you will never complete the download.

It also adjusts file priorities inside each torrent: the video comes first, the extras afterwards, and the junk isn't downloaded at all.

When you use **Sonarr** (TV shows) or **Radarr** (movies), qbit-guardian blocklists the bad release and triggers a fresh search, so you aren't left waiting for nothing.

---

## Prerequisites

- A **home server** or computer that stays on, with:
  - **qBittorrent** installed and reachable over the network (same server or another).
  - **Docker** (recommended) OR **Python 3.10+** (manual install).

- qBittorrent's **API Key**. To find it:
  1. Open qBittorrent and go to **Tools** > **Options** > **Web UI** tab.
  2. Copy the value of the **API Key** field.

> 💡 The **API Key** is a long random password qBittorrent generates. It lets other programs talk to qBittorrent securely, without needing your login and password.

---

## Option 1 — Docker install (recommended)

> 💡 **Docker** is like a box that packages the program with everything it needs to run. It works the same on any computer, with no extra dependencies to install.

### Step 1: Create the configuration folder

In the folder holding your `docker-compose.yml`:

```bash
mkdir -p config
sudo chown -R 1000:1000 config
```

> ⚠️ **The `chown` is mandatory.** For security, the container runs as a regular user (UID 1000), not root. Without the ownership fix it cannot write its configuration and exits immediately.

**No file needs to be created.** `config.json` is generated on first run.

### Step 2: Add it to your docker-compose.yml

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
    environment:
      - LOG_LEVEL=ERROR
    restart: unless-stopped
```

> 📘 A **volume** is the bridge between the container's files and your machine's. Whatever the program saves in `/app/config` inside the container shows up in `./config` on your server. So even if you recreate the container, your settings survive.

### Step 3: Start the container

```bash
docker compose up -d qbit-guardian
```

### Step 4: Get your access password

The Web UI requires a login, and the password is generated on first run:

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

> ⚠️ **Copy it now.** That password is shown only once.

---

## Option 2 — Manual install (no Docker)

Use this if you don't use Docker or prefer running directly on the system.

### Step 1: Download the project

```bash
git clone https://github.com/iHumberto/qbit-guardian.git
cd qbit-guardian
```

### Step 2: Install the dependencies

> 💡 A **virtual environment (venv)** is an isolated folder where Python installs libraries for this project only, without cluttering the rest of the system.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Run the program

```bash
python -m app.main
```

> ⚠️ Use `python -m app.main`, with the `-m`. Running `python app/main.py` fails with `ModuleNotFoundError: No module named 'app'`.

`config.json` is created at the project root, and the access password appears in the terminal. Leave it open — the program runs until you press `Ctrl+C`.

> 💡 To keep it running in the background after closing the terminal, use `tmux` or create a systemd service.

---

## First access to the Web UI

Open a browser and go to:

```
http://your-server-address:5000
```

Examples:

- Running on the same machine: `http://localhost:5000`
- Running on another computer on the network: `http://192.168.1.100:5000`

You land on the **login page**. Sign in with the username `admin` and the password from the log.

### Change the password

Click the **user icon** in the top-right corner. Enter the current password, pick a new one (minimum 8 characters) and save. You can change the username in the same popup.

After saving you return to the login page — that's expected, the change ends open sessions.

---

## Minimum configuration to get going

Once signed in, only two fields are required:

| Field | What to enter |
|-------|--------------|
| **qBittorrent > URL** | Full address, with `http://` and port. E.g. `http://192.168.1.50:8080` |
| **qBittorrent > API Key** | The key you copied from qBittorrent's options |

> ⚠️ It is the **full URL**, not separate host and port.

> ⚠️ In Docker, `localhost` inside the container points at the container itself, not at your machine. If qBittorrent is in another container or on the host, use `host.docker.internal` (Windows/Mac) or the real IP (Linux, e.g. `http://172.17.0.1:8080`).

Click **Save Configuration**. The guardian starts checking torrents every **300 seconds (5 minutes)** using the default rules.

To tune the behaviour — dangerous extensions, stalled removal, priorities, notifications — see the **[Usage Guide](USAGE.md)**.

---

## What to expect

- As soon as you save the configuration, the guardian starts working.
- At every configured interval (default: 300 seconds) it checks all active torrents.
- If it finds an `.exe`, `.scr`, `.bat` or another suspicious file, the torrent is removed on the spot, along with the files.
- If you configured Sonarr/Radarr, it also blocklists the release and searches for an alternative.
- Messages show up in `docker logs` (or the terminal).

> 💡 The log defaults to `LOG_LEVEL=ERROR`, which is very quiet. To see every action, switch to `LOG_LEVEL=VERBOSE` in `docker-compose.yml`.

---

## Common installation problems

### ❌ The container exits right after starting

**Cause:** the `config` folder belongs to root and the container runs unprivileged.

**Fix:** `sudo chown -R 1000:1000 ./config` and start again. The log prints that exact command.

### ❌ I don't know the Web UI password

**Fix:** run `docker logs qbit-guardian` and look for the credentials block. If the log has scrolled too far, clear `webui.password` in `config.json` (leaving `""`) and restart the container — a new password is generated.

### ❌ "Connection refused" or "qBittorrent indisponivel"

**Cause:** qbit-guardian cannot reach qBittorrent.

**Fix:**
- Check that qBittorrent is running.
- Check the **URL** in the panel: it must be complete, with `http://` and port.
- In Docker, `localhost` inside the container is not your machine's. Use `host.docker.internal` (Windows/Mac) or the real IP (Linux).

### ❌ "qBittorrent: HTTP 403"

**Cause:** the API Key is wrong or empty.

**Fix:**
- Go to **Tools** > **Options** > **Web UI** in qBittorrent.
- Confirm "Use authentication" is ticked.
- Copy the **API Key** and paste it exactly — no spaces.

### ❌ `ModuleNotFoundError: No module named 'app'`

**Cause:** on a manual install, the program was started as `python app/main.py`.

**Fix:** use `python -m app.main`, from the project folder.

### ❌ The page won't open at http://...:5000

**Fix:**
- Check the container is running: `docker ps | grep qbit-guardian`.
- On a manual install, see whether the terminal shows "Web UI em http://0.0.0.0:5000".
- Check that your firewall allows port 5000.

### ❌ I don't want to use Sonarr or Radarr

Leave the Sonarr and Radarr **URL** fields **blank**. The guardian works perfectly without them — it just won't blocklist and re-search. You still get removal of dangerous files, stalled and seedless torrents.

---

## Next steps

- [Usage Guide](USAGE.md) — every feature, in detail.
- [Installation Guide](INSTALL.md) — webhook mode, advanced manual install, troubleshooting.
- [FAQ](FAQ.md) — common questions.
