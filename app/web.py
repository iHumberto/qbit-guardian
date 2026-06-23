"""
qbit-guardian — Web UI (Flask).

Serve a pagina de configuracao e endpoints REST para ler/salvar config.json.
Requer autenticacao HTTP Basic Auth (configurada em config.json > webui).
"""

import json
import os
import warnings
import functools
from flask import Flask, request, jsonify, send_from_directory, Response
import app.guardian as guardian
from app.logger import get_logger

# Suprimir warning "This is a development server" do Flask
warnings.filterwarnings("ignore", message=".*development server.*")

log = get_logger("web")

CONFIG_PATH = os.environ.get("CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"))
STATIC_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


# ── Auth ────────────────────────────────────────────────────────────────

def _is_auth_enabled():
    """Verifica se autenticacao esta configurada (user ou password preenchidos)."""
    cfg = _read_config()
    webui = cfg.get("webui", {})
    return bool(webui.get("user") or webui.get("password"))


def _check_auth(username, password):
    """Verifica credenciais contra config.json > webui."""
    cfg = _read_config()
    webui = cfg.get("webui", {})
    return username == webui.get("user", "") and password == webui.get("password", "")


def _auth_required():
    """Retorna 401 com header WWW-Authenticate."""
    return Response(
        "Autenticacao necessaria",
        401,
        {"WWW-Authenticate": "Basic realm=\"qbit-guardian\""}
    )


def requires_auth(f):
    """Decorator: exige HTTP Basic Auth se configurada em webui.user/webui.password.
    
    Se ambos os campos estiverem vazios, auth e desabilitada e o endpoint e publico.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _is_auth_enabled():
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not _check_auth(auth.username, auth.password):
            return _auth_required()
        return f(*args, **kwargs)
    return decorated


# ── Helpers ────────────────────────────────────────────────────────────

def _read_config():
    return guardian.load_config()


def _write_config(data):
    """Persiste config.json no disco E atualiza cache do guardian (thread-safe)."""
    guardian.save_config(data)


def deep_merge(base, override):
    """Merge profundo: override sobrescreve base, preservando campos ausentes."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# ── Rotas ──────────────────────────────────────────────────────────────

@app.route("/")
@requires_auth
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/config", methods=["GET"])
@requires_auth
def api_get_config():
    try:
        return jsonify(_read_config())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["POST"])
@requires_auth
def api_save_config():
    try:
        data = request.get_json(force=True)
        current = _read_config()
        merged = deep_merge(current, data)
        _write_config(merged)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/trigger", methods=["POST"])
@requires_auth
def api_trigger():
    """Forca uma verificacao imediata (acionamento manual ou webhook)."""
    try:
        guardian.load_config()
        torrents = guardian.get_torrents()
        current = {t["hash"] for t in torrents}
        new = [t for t in torrents if t["hash"] not in guardian._processed]
        count = len(new)
        for t in new:
            guardian.analyze_torrent(t)
            guardian._processed.add(t["hash"])

        # Pass 2: reavalia stalled/no-seeds para TODOS os torrents
        stalled_removed = 0
        for t in torrents:
            if guardian.check_stalled_and_remove(t):
                stalled_removed += 1

        guardian._prune_processed(current)
        guardian.write_heartbeat()
        return jsonify({"status": "ok", "checked": len(torrents), "new": count,
                       "stalled_removed": stalled_removed})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Entrypoint ─────────────────────────────────────────────────────────

def start_web(host="0.0.0.0", port=5000):
    """Inicia o servidor Flask (bloqueante)."""
    log.info(f"Web UI em http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)
