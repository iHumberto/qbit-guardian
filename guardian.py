"""
qbit-guardian — Motor principal.

Monitora torrents ativos no qBittorrent e remove arquivos maliciosos,
bloqueia no Sonarr/Radarr e dispara nova busca.
Configuravel via config.json + Web UI (web.py).
"""

import os
import json
import time
import logging
import threading
import requests
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("qbit-guardian")

CONFIG_PATH = os.environ.get("CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))

# ── Config loader ──────────────────────────────────────────────────────
_config = None
_config_lock = threading.Lock()


def load_config():
    """Le config.json (thread-safe)."""
    global _config
    with _config_lock:
        with open(CONFIG_PATH, "r") as f:
            _config = json.load(f)
    return _config


def get_config():
    """Retorna config em cache ou recarrega."""
    global _config
    if _config is None:
        return load_config()
    return _config


def save_config(data):
    """Salva config.json (thread-safe)."""
    with _config_lock:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        global _config
        _config = data


# ── qBitTorrent session ────────────────────────────────────────────────
_qbit_session = None
_qbit_base = None


def get_qbit_session():
    global _qbit_session, _qbit_base
    cfg = get_config()
    host = cfg["qbit"]["host"]
    port = cfg["qbit"]["port"]
    key  = cfg["qbit"]["api_key"]

    base = f"http://{host}:{port}"
    if _qbit_session is None or _qbit_base != base:
        _qbit_session = requests.Session()
        _qbit_session.headers.update({"Authorization": f"Bearer {key}"})
        _qbit_base = base
    return _qbit_session, _qbit_base


def qbit_login():
    sess, base = get_qbit_session()
    r = sess.get(f"{base}/api/v2/app/version", timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"qBittorrent: HTTP {r.status_code}")
    log.info(f"Conectado ao qBittorrent v{r.text.strip()}")


def get_torrents():
    sess, base = get_qbit_session()
    r = sess.get(f"{base}/api/v2/torrents/info", timeout=10)
    r.raise_for_status()
    return r.json()


def get_files(torrent_hash):
    sess, base = get_qbit_session()
    r = sess.get(f"{base}/api/v2/torrents/files",
                 params={"hash": torrent_hash}, timeout=10)
    r.raise_for_status()
    return r.json()


def remove_torrent(torrent_hash):
    sess, base = get_qbit_session()
    sess.post(f"{base}/api/v2/torrents/delete",
              data={"hashes": torrent_hash, "deleteFiles": "true"}, timeout=10)
    log.warning(f"Removido: {torrent_hash}")


def set_file_priority(torrent_hash, file_id, priority):
    sess, base = get_qbit_session()
    sess.post(f"{base}/api/v2/torrents/filePrio",
              data={"hash": torrent_hash, "id": file_id, "priority": priority}, timeout=10)


# ── Notificacoes ───────────────────────────────────────────────────────

def send_notification(title, message):
    cfg = get_config()
    url = cfg["notifications"].get("apprise_url", "")
    if not url:
        return
    try:
        requests.post(url, data={"title": title, "body": message}, timeout=10)
    except Exception as e:
        log.error(f"Apprise: {e}")


# ── Bloqueio e re-busca ────────────────────────────────────────────────

def block_and_search(torrent_hash, torrent_name):
    cfg = get_config()

    # Radarr
    if cfg["radarr"]["host"] and cfg["radarr"]["api_key"]:
        try:
            rh = cfg["radarr"]["host"]
            rp = cfg["radarr"]["port"]
            rk = cfg["radarr"]["api_key"]
            base = f"http://{rh}:{rp}/api/v3"
            hdrs = {"X-Api-Key": rk}

            rq = requests.get(f"{base}/queue", headers=hdrs, timeout=10)
            movie_id = None
            for item in rq.json().get("records", []):
                if item.get("downloadId", "").lower() == torrent_hash.lower():
                    requests.delete(f"{base}/queue/{item['id']}", headers=hdrs,
                                    params={"blocklist": "true", "removeFromClient": "false"}, timeout=10)
                    movie_id = item.get("movieId")
                    log.info(f"Radarr: '{torrent_name}' → BLOCKLIST")
                    break

            if not movie_id:
                rm = requests.get(f"{base}/movie", headers=hdrs, timeout=10)
                for m in rm.json():
                    if m.get("title", "").lower() in torrent_name.lower():
                        movie_id = m["id"]
                        break

            if movie_id:
                requests.post(f"{base}/command", headers=hdrs,
                              json={"name": "MoviesSearch", "movieIds": [movie_id]}, timeout=10)
                log.info("Radarr: busca disparada")
        except Exception as e:
            log.error(f"Radarr: {e}")

    # Sonarr
    if cfg["sonarr"]["host"] and cfg["sonarr"]["api_key"]:
        try:
            sh = cfg["sonarr"]["host"]
            sp = cfg["sonarr"]["port"]
            sk = cfg["sonarr"]["api_key"]
            base = f"http://{sh}:{sp}/api/v3"
            hdrs = {"X-Api-Key": sk}

            rq = requests.get(f"{base}/queue", headers=hdrs, timeout=10)
            series_id = None
            episode_ids = []

            for item in rq.json().get("records", []):
                if item.get("downloadId", "").lower() == torrent_hash.lower():
                    series_id = item.get("seriesId")
                    if "episodeId" in item:
                        episode_ids.append(item["episodeId"])
                    elif "episodes" in item:
                        episode_ids.extend([ep["id"] for ep in item["episodes"]])

                    requests.delete(f"{base}/queue/{item['id']}", headers=hdrs,
                                    params={"blocklist": "true", "removeFromClient": "false"}, timeout=10)
                    log.info(f"Sonarr: '{torrent_name}' → BLOCKLIST")
                    break

            if not series_id:
                rs = requests.get(f"{base}/series", headers=hdrs, timeout=10)
                for s in rs.json():
                    if s.get("title", "").lower() in torrent_name.lower():
                        series_id = s["id"]
                        break

            if episode_ids:
                now = datetime.now(timezone.utc)
                released = []
                for eid in episode_ids:
                    try:
                        re = requests.get(f"{base}/episode/{eid}", headers=hdrs, timeout=10)
                        ad = re.json().get("airDateUtc")
                        if ad:
                            adt = datetime.fromisoformat(ad.replace("Z", "+00:00"))
                            if adt <= now:
                                released.append(eid)
                            else:
                                log.info(f"Sonarr: episodio {eid} nao lancado ({ad})")
                        else:
                            released.append(eid)
                    except Exception as ex:
                        log.error(f"Sonarr episodio {eid}: {ex}")
                        released.append(eid)

                if released:
                    requests.post(f"{base}/command", headers=hdrs,
                                  json={"name": "EpisodeSearch", "episodeIds": released}, timeout=10)
                    log.info(f"Sonarr: busca para {released}")
                else:
                    log.warning(f"Sonarr: '{torrent_name}' episodios nao lancados")

            elif series_id:
                requests.post(f"{base}/command", headers=hdrs,
                              json={"name": "SeriesSearch", "seriesId": series_id}, timeout=10)
                log.info("Sonarr: busca da serie disparada")
        except Exception as e:
            log.error(f"Sonarr: {e}")


# ── Analise de torrent ─────────────────────────────────────────────────

def is_stalled(torrent, cfg):
    """Verifica se torrent deve ser removido por stalled/no-seeds."""
    g = cfg["guardian"]
    state = torrent.get("state", "")

    # Stalled (parado por X tempo)
    if g.get("remove_stalled") and state in ("stalledDL", "stalledUP"):
        seconds = _time_to_seconds(g.get("stalled_time", 0), g.get("stalled_unit", "hours"))
        if seconds > 0:
            added_on = torrent.get("added_on", 0)
            if time.time() - added_on >= seconds:
                return True, f"stalled por >{g['stalled_time']}{g['stalled_unit'][0]}"

    # Sem seeds
    if g.get("remove_no_seeds") and state in ("stalledDL", "downloading", "queuedDL"):
        seeds = torrent.get("num_complete", -1)
        if seeds == 0:
            seconds = _time_to_seconds(g.get("no_seeds_time", 0), g.get("no_seeds_unit", "hours"))
            if seconds > 0:
                added_on = torrent.get("added_on", 0)
                if time.time() - added_on >= seconds:
                    return True, "0 seeds"

    return False, ""


def _time_to_seconds(value, unit):
    if unit == "seconds":
        return int(value)
    elif unit == "minutes":
        return int(value) * 60
    else:
        return int(value) * 3600


def analyze_torrent(torrent):
    cfg = get_config()
    g = cfg["guardian"]
    valid_ext = set(g.get("valid_media_extensions", []))
    dangerous_ext = set(g.get("dangerous_extensions", []))

    hash_ = torrent["hash"]
    name  = torrent["name"]
    state = torrent.get("state", "")

    # Pular torrents ja completos/uploading
    if state in ("uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"):
        return

    # Verificar stalled/sem seeds
    stalled, stalled_reason = is_stalled(torrent, cfg)
    if stalled:
        log.warning(f"[{name}] {stalled_reason} — Removendo")
        remove_torrent(hash_)
        send_notification("🗑️ Torrent Removido (stalled)",
                          f"Nome: {name}\nMotivo: {stalled_reason}")
        return

    files = get_files(hash_)
    if not files:
        return

    extensions = [os.path.splitext(f["name"])[1].lower() for f in files]
    dangerous_found = [e for e in extensions if e in dangerous_ext]

    should_remove = False
    reason = ""

    if dangerous_found:
        should_remove = True
        reason = f"Arquivos perigosos: {dangerous_found}"
    elif valid_ext:
        media_files = [f for f in files if os.path.splitext(f["name"])[1].lower() in valid_ext]
        if not media_files:
            should_remove = True
            reason = "Nenhum arquivo de midia valido"

    if should_remove:
        log.warning(f"[{name}] {reason} — Removendo e Bloqueando")
        block_and_search(hash_, name)
        remove_torrent(hash_)
        send_notification("⚠️ Torrent Removido",
                          f"Nome: {name}\nMotivo: {reason}")
        return

    # Otimizar prioridades
    optimized = False
    prio_media = g.get("priority_media", 7)
    prio_norm  = g.get("priority_normal", 1)
    prio_skip  = g.get("priority_skip", 0)
    for f in files:
            ext = os.path.splitext(f["name"])[1].lower()
            file_id = f.get("index", f.get("id"))
            if ext in valid_ext:
                set_file_priority(hash_, file_id, prio_media)
                optimized = True
            elif ext in {".nfo", ".jpg", ".png", ".txt", ".srt", ".sub", ".idx"}:
                set_file_priority(hash_, file_id, prio_norm)
            else:
                set_file_priority(hash_, file_id, prio_skip)
                log.info(f"[{name}] Desativado → {f['name']}")
    if optimized:
        send_notification("⚡ Torrent Otimizado",
                          f"Nome: {name}\nArquivos de midia priorizados.")


# ── Loop principal ─────────────────────────────────────────────────────

_processed = set()


def guardian_loop():
    load_config()
    try:
        qbit_login()
    except Exception as e:
        log.error(f"Falha ao conectar no qBit: {e}")
        return

    cfg = get_config()
    interval = cfg["guardian"].get("check_interval_seconds", 300)
    log.info(f"Guardian iniciado. Intervalo: {interval}s")

    while True:
        try:
            torrents = get_torrents()
            new = [t for t in torrents if t["hash"] not in _processed]

            if new:
                log.info(f"{len(new)} torrent(s) novo(s)")
                for t in new:
                    analyze_torrent(t)
                    _processed.add(t["hash"])
            else:
                log.debug("Nenhum torrent novo")

            # Limpar processed periodicamente (evita memory leak)
            current_hashes = {t["hash"] for t in torrents}
            _processed.intersection_update(current_hashes)

        except requests.exceptions.ConnectionError:
            log.warning("qBittorrent inacessivel, reconectando...")
            try:
                qbit_login()
            except Exception:
                pass
        except Exception as e:
            log.error(f"Erro: {e}")

        try:
            with open("/tmp/heartbeat", "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass

        time.sleep(interval)


def start_guardian():
    """Inicia o loop em thread separada."""
    t = threading.Thread(target=guardian_loop, daemon=True)
    t.start()
    log.info("Guardian thread iniciada")
    return t
