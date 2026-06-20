# 📦 Installation Guide

> How to install and run qbit-guardian on your server.

---

## Before you start

You need:

- A computer or home server that stays on (where your qBittorrent also runs, or on the same network).
- **qBittorrent** already installed and running.
- Your qBittorrent **API Key** — find it in qBittorrent: **Tools → Options → Web UI → API Key**.

> 💡 **API Key** is a long random password that qBittorrent creates. Other programs use it to talk to qBittorrent securely. Copy it exactly as shown — no spaces, no extra characters.

Choose one of the two installation methods below.

---

## Option 1: Docker Compose (recommended)

> 💡 **Docker** is a tool that packages programs with everything they need. Once packaged, they run the same way on any computer. You don't need to install Python or other dependencies manually.

### Step 1: Create a configuration folder

Pick a folder on your server for qbit-guardian's files. For example:

```bash
mkdir -p ~/docker/qbit-guardian
cd ~/docker/qbit-guardian
```

### Step 2: Create the config.json file

Create a file named `config.json` in that folder with this content:

```json
{
  "qbit": {
    "host": "192.168.1.100",
    "port": 8080,
    "api_key": "PASTE-YOUR-API-KEY-HERE"
  }
}
```

> ⚠️ Replace `192.168.1.100` with the real IP address of the computer running qBittorrent.
>
> **Docker users — important:** `localhost` inside a Docker container means the container itself, not your computer. If qBittorrent runs on the same machine, use:
> - Windows/Mac: `host.docker.internal`
> - Linux: your machine's real IP (e.g. `172.17.0.1` or `192.168.1.100`)
>
> If qBittorrent is in another container, use the container name (e.g. `qbittorrent`).

### Step 3: Add to your docker-compose.yml

Open your existing `docker-compose.yml` file (where you already have qBittorrent, Sonarr, Radarr, etc.) and add this service:

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./qbit-guardian/config.json:/app/config.json
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "cat", "/tmp/heartbeat"]
      interval: 60s
      timeout: 5s
      retries: 3
```

> 💡 **Healthcheck** is a built-in test that Docker runs to check if the program is still working. The guardian writes a heartbeat signal to a file every cycle. If that file gets too old, Docker marks the container as unhealthy — so you can see problems before they affect you.

### Step 4: Start the container

```bash
docker compose up -d qbit-guardian
```

Docker downloads the image and starts qbit-guardian in the background.

### Step 5: Verify it's working

Check if the container is running:

```bash
docker ps | grep qbit-guardian
```

Open the Web UI in your browser:

```
http://your-server-address:5000
```

If you see the configuration dashboard, the installation is complete! 🎉

---

## Option 2: Manual installation (Python)

Use this if you don't use Docker or prefer to run programs directly.

### Step 1: Download the project

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
```

### Step 2: Set up a Python virtual environment

> 💡 A **virtual environment** (or `venv`) is an isolated folder where Python installs libraries just for this project. It keeps things tidy — no conflicts with other programs on your computer. Think of it as a separate drawer for this project's tools.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, use `.venv\Scripts\activate` instead.

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

This installs everything qbit-guardian needs: Flask (for the web page), requests (to talk to qBittorrent), and their supporting libraries.

### Step 4: Configure the program

Edit the `config.json` file. At minimum, fill in your qBittorrent details:

```json
{
  "qbit": {
    "host": "192.168.1.100",
    "port": 8080,
    "api_key": "PASTE-YOUR-API-KEY-HERE"
  }
}
```

### Step 5: Run the program

```bash
python app/app.py
```

You should see output like this:

```
qbit-guardian iniciando...
Conectado ao qBittorrent v5.0.0
Guardian iniciado. Intervalo: 300s
Web UI em http://0.0.0.0:5000
```

The program runs in the foreground — leave the terminal open. Press `Ctrl+C` to stop it.

> 💡 To keep it running after you close the terminal, use a tool like `tmux`, `screen`, or create a systemd service. These are well-documented online and outside the scope of this guide.

### Step 6: Verify it's working

Open your browser and go to:

```
http://localhost:5000
```

If you see the configuration dashboard, everything is working!

---

## After installation

Both methods lead to the same result. Now you should:

1. Open the Web UI at `http://your-server-address:5000`.
2. Fill in the remaining configuration (Sonarr, Radarr, notifications, etc.) if you want.
3. **[Optional]** Protect the dashboard with a password — see the [Usage Guide](USAGE.md#web-ui-authentication).

---

## Checking if it's working

Here is how to make sure qbit-guardian is actually protecting your torrents:

### Health check (Docker)

```bash
docker ps | grep qbit-guardian
```

Look for `(healthy)` in the STATUS column. Docker automatically monitors the heartbeat and shows the health here.

### Logs (Docker)

```bash
docker logs qbit-guardian
```

You should see messages like:

```
Conectado ao qBittorrent v5.0.0
Guardian iniciado. Intervalo: 300s
```

When the guardian finds a bad torrent, you'll see lines like:

```
[Bad.Movie.2024] Arquivos perigosos: ['.exe'] — Removendo e Bloqueando
```

### Logs (Manual install)

The output appears directly in your terminal. Look for the same messages described above.

### Test it yourself

Want to be absolutely sure? Add a harmless test torrent that contains a `.txt` file renamed to `.exe`. The guardian should detect it as dangerous and remove it within a few minutes (or instantly in webhook mode).

> ⚠️ Don't test with real dangerous files. Create a safe dummy file — rename a `.txt` to `.exe` and create a torrent from it.

---

## Updating

### Docker

```bash
docker compose pull qbit-guardian
docker compose up -d qbit-guardian
```

### Manual

```bash
cd qbit-guardian
git pull
source .venv/bin/activate
pip install -r requirements.txt
```

Then restart the program.

---

## Uninstalling

### Docker

```bash
docker compose down qbit-guardian
```

Delete the folder with `config.json` if you no longer need it.

### Manual

Press `Ctrl+C` to stop, then delete the `qbit-guardian` folder.
