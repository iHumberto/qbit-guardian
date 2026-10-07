# Installing qbit-guardian

> Step-by-step guide to installing qbit-guardian. Pick either Docker (recommended) or a manual install.

## What you need before starting

- A computer or server that stays on (qbit-guardian needs to run 24/7).
- **qBittorrent** already installed and running, with the **Web UI enabled**.

> **📘 qBittorrent Web UI:** The control page that lets you manage qBittorrent from a browser. To enable it, go to **Tools → Options → Web UI** in qBittorrent, tick **Use authentication** and set a username and password.

- qBittorrent's **API Key**. To find it:
  1. In qBittorrent: **Tools → Options → Web UI**.
  2. Copy the value of the **API Key** field. You will paste it into qbit-guardian's configuration.

> 💡 Keep that key somewhere safe. It is what the guardian uses to connect to qBittorrent.

Pick your preferred install method below.

---

## Option 1: Docker install (recommended)

Docker packages the program with everything it needs. It works the same on any system (Windows, Mac, Linux) and is the simplest way to install.

> **📘 Docker:** Think of it as a box holding the program and all its dependencies. You don't need to install Python, libraries or anything else — the box comes ready. It also makes updating and removing the program easier later.

### Step 1: Create the configuration folder

Create a folder for qbit-guardian, for example `/home/user/docker/qbit-guardian/`. Inside it, create a `config` subfolder and fix its ownership:

```bash
mkdir -p config
sudo chown -R 1000:1000 config
```

> ⚠️ **The `chown` is mandatory.** For security, the container runs as an unprivileged user (UID 1000). Without the ownership fix it cannot write and exits immediately — printing that same command to the log.

**You do not need to create any configuration file.** `config.json` is generated automatically on first run, with default values.

### Step 2: Add it to docker-compose.yml

Open the `docker-compose.yml` where you already manage your other services (qBittorrent, Sonarr, Radarr) and add this block:

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

What each line does:

| Line | Explanation |
|------|-------------|
| `image: ghcr.io/...` | Pulls the ready-to-use program image. |
| `ports: "5000:5000"` | Makes the control page reachable on port 5000. |
| `volumes: ./config:/app/config` | Connects your machine's `config` folder to the container's. Configuration survives updates. |
| `environment: LOG_LEVEL=ERROR` | Log detail level. Options: `ERROR`, `INFO`, `VERBOSE`, `DEBUG`. |
| `restart: unless-stopped` | If the container stops for any reason, Docker restarts it automatically. |

> 💡 **Healthcheck:** no need to declare one. The image already ships a healthcheck that verifies the guardian loop is still alive, by comparing the heartbeat file's age against the configured interval.

### Step 3: Start the container

Open a terminal in the folder holding `docker-compose.yml` and run:

```bash
docker compose up -d qbit-guardian
```

The first time, Docker pulls the image (may take a few seconds). After that it starts instantly.

To check everything is fine:

```bash
docker ps | grep qbit-guardian
```

If you see a line with `qbit-guardian` and status `Up`, the install worked.

### Step 4: Get your access password

The Web UI requires a login. On first boot the guardian **generates the password itself** and prints it to the log:

```bash
docker logs qbit-guardian
```

You will see a block like this:

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================
```

> ⚠️ **That password is shown only once**, at the moment it is created. Copy and store it now.

You can change it later: in the panel, click the **user icon** (top-right corner) and provide the current password plus the new one.

> **Forgot the password?** Open `config.json` in the `config` folder, clear the `webui.password` field (leaving `""`) and restart the container. A new password is generated and announced in the log.

### Updating qbit-guardian

When a new version ships, update with:

```bash
docker compose pull qbit-guardian
docker compose up -d qbit-guardian
```

Your configuration (the `config` folder) is preserved — only the program is updated.

---

## Option 2: Manual install (no Docker)

Use this if you don't use Docker or prefer running the program directly. You will need **Python 3.10 or newer**.

### Step 1: Download the project

```bash
git clone https://github.com/iHumberto/qbit-guardian.git
cd qbit-guardian
```

If you don't have `git`, you can download the project as a `.zip` from the browser and extract it.

### Step 2: Prepare the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **📘 Virtual environment (venv):** An isolated folder where Python installs libraries for this project only. Like a separate drawer — it doesn't clutter the rest of the system.

### Step 3: Run the program

```bash
python -m app.main
```

> ⚠️ Use `python -m app.main`, with the `-m`. Running `python app/main.py` fails with `ModuleNotFoundError: No module named 'app'`, because Python cannot find the project folder.

**No configuration file needs to be created beforehand.** `config.json` is generated at the project root on first run.

The terminal will show messages like:

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================

qbit-guardian iniciando...
Conectado ao qBittorrent v5.0.0
Guardian iniciado. Intervalo: 300s
Web UI em http://0.0.0.0:5000
```

The program runs in the foreground. Press `Ctrl+C` to stop.

> 💡 To keep it running after closing the terminal, use tools like `tmux`, `screen`, or create a systemd service. Those topics are well documented online.

### Changing where config.json lives

By default, a manual install keeps the file at the project root. To choose another location, use the `CONFIG_PATH` variable:

```bash
CONFIG_PATH=/etc/qbit-guardian/config.json python -m app.main
```

---

## Verifying it works

### Test 1: Open the control page

Open a browser and go to `http://your-server-address:5000`. You will land on the **login page**. Sign in with `admin` and the password from the log.

### Test 2: Check the healthcheck

This endpoint is public — no password needed:

```bash
curl http://your-server-address:5000/api/health
```

The response should be:

```json
{"status": "ok"}
```

### Test 3: Look at the logs

- **Docker:** `docker logs qbit-guardian`
- **Manual:** messages appear directly in the terminal.

You should see something like `Conectado ao qBittorrent v...` — that means the connection to qBittorrent is working.

> 💡 With `LOG_LEVEL=ERROR` (the default) the log is very quiet. To see more, use `LOG_LEVEL=INFO` or `LOG_LEVEL=VERBOSE`.

### Test 4: Force a check

On the control page, click **Force check**. Or from the command line, with your credentials:

```bash
curl -X POST http://your-server-address:5000/api/trigger \
  -u admin:your-password
```

If the response is `{"status": "ok", "checked": ..., "new": ..., "stalled_removed": ...}`, everything works.

---

## Setting up the Webhook (real time)

The webhook lets qBittorrent notify the guardian the moment a torrent is added — no waiting for the next check cycle. It is the fastest option.

> ⚠️ The webhook script is **non-blocking**: it does not stall qBittorrent. The main script returns in under 4 milliseconds — qBittorrent keeps working while the check happens in the background.

### Step 1: Mount the script in the qBittorrent container

The `qbit-guardian-hook.sh` script lives in the repository's `scripts/` folder. Add this volume to the `qbittorrent` service in your `docker-compose.yml`:

```yaml
services:
  qbittorrent:
    # ... your current settings ...
    volumes:
      - ./qbit-guardian/scripts/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh:ro
```

> 💡 The trailing `:ro` means "read-only" — the container can run the script but not modify it.

### Step 2: Give the script your credentials

`/api/trigger` requires authentication. Without credentials the guardian answers `401` and the webhook won't work. Add these variables to the qBittorrent service:

```yaml
services:
  qbittorrent:
    environment:
      - QBIT_GUARDIAN_URL=http://qbit-guardian:5000
      - QBIT_GUARDIAN_USER=admin
      - QBIT_GUARDIAN_PASS=your-web-ui-password
```

| Variable | What it does |
|----------|--------------|
| `QBIT_GUARDIAN_URL` | Where the guardian is. The default `http://qbit-guardian:5000` works if both containers share a Docker network. For IP access: `http://192.168.1.100:5000`. |
| `QBIT_GUARDIAN_USER` | Web UI username. Default: `admin`. |
| `QBIT_GUARDIAN_PASS` | Web UI password. **Required.** |

> 💡 If you change the password in the panel, remember to update `QBIT_GUARDIAN_PASS` here too.

### Step 3: Configure qBittorrent

1. In qBittorrent, go to **Tools → Options → Downloads**.
2. Find **Run external program on torrent added**.
3. **Tick the checkbox** next to the field. Without it ticked qBittorrent **does not save** the path — the field comes back empty and the webhook never fires. This is the most common cause of "I configured it and nothing happens".
4. In the field, paste:

```
/scripts/qbit-guardian-hook.sh
```

5. Click **Save**.

To confirm it really was stored, without relying on the screen:

```bash
curl -s -H "Authorization: Bearer YOUR_QBIT_API_KEY" \
  http://QBIT-IP:PORT/api/v2/app/preferences \
  | python3 -m json.tool | grep autorun
```

You should see `"autorun_on_torrent_added_enabled": true` and the path in
`"autorun_on_torrent_added_program"`. If you get `false` and `""`, the setting
was not saved.

> **📘 Why the script is `#!/bin/sh` and not `#!/bin/bash`:** qBittorrent's Docker images are based on **Alpine Linux**, which ships **neither bash nor curl**. A script with `#!/bin/bash` fails with "not found" (exit 127) the moment qBittorrent tries to run it, with no useful message. The project's script is plain POSIX and uses `curl` when present, falling back to busybox `wget` when it isn't — so it works either way.

To check what your container has:

```bash
docker exec qbittorrent sh -c 'command -v sh bash curl wget base64'
```

### Step 4: Set the interval to zero

On the qbit-guardian control page, set **Check interval** to `0`. That turns off polling mode and turns on webhook mode.

Done. From now on, every torrent added is checked instantly.

### How the script avoids stalls

- **10-second sleep:** prevents the guardian from checking the torrent before qBittorrent has registered it (race condition).
- **curl timeouts:** 5 seconds to connect, 10 seconds total. If the guardian doesn't answer, the script doesn't hang.
- **Background execution:** the main script finishes in ~4 ms. qBittorrent doesn't wait for the check.
- **Extra attempt:** if the first call fails, the script tries again after 5 seconds.
- **Failures are reported:** if both attempts fail, the script writes to qBittorrent's stderr instead of giving up silently. If the cause is a missing password, it says so.

---

## Next steps

Once installed and running:

1. Open `http://your-server:5000`, sign in with the password from the log and review the settings.
2. Change the password via the **user icon** in the top-right corner.
3. If you want, enable [notifications](USAGE.md#notifications).
4. Read the [Usage Guide](USAGE.md) to understand every feature.

---

## Installation problems?

| Problem | Solution |
|---------|----------|
| Container exits right after starting, with a permission message | The `config` folder belongs to root. Run `sudo chown -R 1000:1000 ./config` and start again. The log prints that exact command. |
| "Connection refused" or "qBittorrent indisponivel" | Check that qBittorrent is running and the URL is correct. In Docker, `localhost` inside the container is NOT your machine — use `host.docker.internal` (Windows/Mac) or the real IP (Linux). |
| "qBittorrent: HTTP 403" | The API Key is wrong. Check it under **Tools → Options → Web UI** in qBittorrent and paste it exactly. |
| I don't know the Web UI password | Run `docker logs qbit-guardian` and look for the credentials block. If the log has scrolled too far, clear `webui.password` in `config.json` and restart — a new password is generated. |
| Login says "too many attempts" | That's 5 wrong attempts in 5 minutes. Wait a few minutes — the block applies even to the correct password. |
| `ModuleNotFoundError: No module named 'app'` | On a manual install, use `python -m app.main` (with `-m`), from the project folder. |
| The page doesn't open on port 5000 | Check the container is running (`docker ps`). On a manual install, see whether the terminal shows "Web UI em http://...". Check that your firewall allows port 5000. |
| Port 5000 is already in use | Change the mapping in docker-compose (e.g. `"5001:5000"`). On a manual install the port is fixed at 5000 — use a reverse proxy if you need another. |
| The webhook stopped working | `/api/trigger` requires authentication. Check `QBIT_GUARDIAN_PASS` on the qBittorrent service; the script reports the problem on stderr. |

If the problem persists, check the [FAQ](FAQ.md).
