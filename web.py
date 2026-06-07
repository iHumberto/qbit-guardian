"""
qbit-guardian — Web UI (Flask).

Serve a pagina de configuracao e endpoints REST para ler/salvar config.json.
"""
import json
import os
import logging
from flask import Flask, request, jsonify, send_from_directory

log = logging.getLogger("qbit-guardian.web")

CONFIG_PATH = os.environ.get("CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
STATIC_DIR  = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


# ── Helpers ────────────────────────────────────────────────────────────

def _read_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def _write_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Rotas ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/config", methods=["GET"])
def api_get_config():
    try:
        return jsonify(_read_config())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["POST"])
def api_save_config():
    try:
        data = request.get_json(force=True)
        _write_config(data)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    """Forca uma verificacao imediata (acionamento manual ou webhook)."""
    import guardian
    try:
        guardian.load_config()
        torrents = guardian.get_torrents()
        current = {t["hash"] for t in torrents}
        new = [t for t in torrents if t["hash"] not in guardian._processed]
        count = len(new)
        for t in new:
            guardian.analyze_torrent(t)
            guardian._processed.add(t["hash"])
        guardian._processed.intersection_update(current)
        return jsonify({"status": "ok", "checked": len(torrents), "new": count})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Entrypoint ─────────────────────────────────────────────────────────

def start_web(host="0.0.0.0", port=5000):
    """Inicia o servidor Flask (bloqueante)."""
    log.info(f"Web UI em http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)
