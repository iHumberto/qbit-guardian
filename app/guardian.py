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
import urllib3
from datetime import datetime, timezone

# Suprimir warnings de SSL inseguro (homelab com certificados auto-assinados)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app.logger import get_logger, VERBOSE

log = get_logger("guardian")

CONFIG_PATH = os.environ.get("CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"))

MAX_PROCESSED_SIZE = 10_000

# ── Config loader ──────────────────────────────────────────────────────
_config = None
_config_lock = threading.Lock()


def load_config():
    """Le config.json (thread-safe). Cria default se nao existir."""
    global _config
    with _config_lock:
        if not os.path.exists(CONFIG_PATH):
            default = {
                "qbit": {"url": "", "api_key": ""},
                "sonarr": {"url": "", "api_key": ""},
                "radarr": {"url": "", "api_key": ""},
                "guardian": {
                    "check_interval_seconds": 300,
                    "valid_media_extensions": [
                        ".mkv", ".mp4", ".avi", ".mov", ".m4v",
                        ".ts", ".wmv", ".flv", ".webm"
                    ],
                    "dangerous_extensions": [
                        ".exe", ".scr", ".bat", ".cmd", ".vbs",
                        ".js", ".com", ".pif", ".msi", ".dll",
                        ".ps1", ".sh", ".bin"
                    ],
                    "remove_stalled": False,
                    "stalled_time": 0,
                    "stalled_unit": "hours",
                    "remove_no_seeds": False,
                    "no_seeds_time": 0,
                    "no_seeds_unit": "hours",
                    "priority_media": 7,
                    "priority_normal": 1,
                    "priority_skip": 0
                },
                "notifications": {"apprise_url": ""},
                "webui": {"user": "", "password": ""}
            }
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(default, f, indent=2)
            _config = default
            log.info("config.json criado com valores default — configure pela Web UI")
            return _config
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
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
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
    url = cfg["qbit"]["url"].rstrip("/")
    key = cfg["qbit"]["api_key"]

    base = url
    if _qbit_session is None or _qbit_base != base:
        _qbit_session = requests.Session()
        _qbit_session.verify = False  # Homelab: certificados auto-assinados
        _qbit_session.headers.update({"Authorization": f"Bearer {key}"})
        _qbit_base = base
    return _qbit_session, _qbit_base


def qbit_login():
    sess, base = get_qbit_session()
    log.debug(f"HTTP GET {base}/api/v2/app/version")
    r = sess.get(f"{base}/api/v2/app/version", timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"qBittorrent: HTTP {r.status_code}")
    log.info(f"Conectado ao qBittorrent v{r.text.strip()}")


def get_torrents():
    sess, base = get_qbit_session()
    log.debug(f"HTTP GET {base}/api/v2/torrents/info")
    r = sess.get(f"{base}/api/v2/torrents/info", timeout=10)
    r.raise_for_status()
    return r.json()


def get_files(torrent_hash):
    sess, base = get_qbit_session()
    log.debug(f"HTTP GET {base}/api/v2/torrents/files?hash={torrent_hash[:8]}")
    r = sess.get(f"{base}/api/v2/torrents/files",
                 params={"hash": torrent_hash}, timeout=10)
    r.raise_for_status()
    return r.json()


def remove_torrent(torrent_hash):
    sess, base = get_qbit_session()
    log.debug(f"HTTP POST {base}/api/v2/torrents/delete (hash={torrent_hash[:8]})")
    sess.post(f"{base}/api/v2/torrents/delete",
              data={"hashes": torrent_hash, "deleteFiles": "true"}, timeout=10)
    log.error(f"Removido: {torrent_hash}")


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
        log.debug(f"HTTP POST {url} (Apprise: {title})")
        requests.post(url, data={"title": title, "body": message},
                     timeout=10, verify=False)
    except Exception as e:
        log.error(f"Apprise: {e}")


# ── Bloqueio e re-busca ────────────────────────────────────────────────

def _arr_match_by_name(items, torrent_name, title_field="title"):
    """Busca item na lista por match parcial de nome."""
    for item in items:
        if item.get(title_field, "").lower() in torrent_name.lower():
            return item["id"]
    return None


def _handle_arr(arr_type, config_key, torrent_hash, torrent_name):
    """Handler generico para Sonarr ou Radarr.

    Fluxo:
    1. Busca torrent na queue → blocklist + extrai ID
    2. Fallback: busca por nome se nao encontrou na queue
    3. Dispara comando de re-search
    4. (Sonarr apenas) Valida data de lancamento dos episodios
    """
    cfg = get_config()
    section = cfg[config_key]

    if not section["url"] or not section["api_key"]:
        return

    try:
        url = section["url"].rstrip("/")
        key = section["api_key"]
        base = f"{url}/api/v3"
        hdrs = {"X-Api-Key": key}

        sess = requests.Session()
        sess.verify = False  # Homelab: certificados auto-assinados
        sess.headers.update(hdrs)

        # 1. Buscar na queue
        log.debug(f"HTTP GET {base}/queue")
        rq = sess.get(f"{base}/queue", timeout=10)
        item_id = None
        extra_ids = []  # Sonarr: episode_ids

        for item in rq.json().get("records", []):
            if item.get("downloadId", "").lower() == torrent_hash.lower():
                # Blocklist
                log.debug(f"HTTP DELETE {base}/queue/{item['id']}?blocklist=true")
                sess.delete(f"{base}/queue/{item['id']}",
                                params={"blocklist": "true", "removeFromClient": "false"},
                                timeout=10)
                log.info(f"{arr_type}: '{torrent_name}' -> BLOCKLIST")

                if arr_type == "Radarr":
                    item_id = item.get("movieId")
                elif arr_type == "Sonarr":
                    item_id = item.get("seriesId")
                    if "episodeId" in item:
                        extra_ids.append(item["episodeId"])
                    elif "episodes" in item:
                        extra_ids.extend([ep["id"] for ep in item["episodes"]])
                break

        # 2. Fallback: busca por nome
        if not item_id:
            if arr_type == "Radarr":
                log.debug(f"HTTP GET {base}/movie")
                rm = sess.get(f"{base}/movie", timeout=10)
                item_id = _arr_match_by_name(rm.json(), torrent_name)
            elif arr_type == "Sonarr":
                log.debug(f"HTTP GET {base}/series")
                rs = sess.get(f"{base}/series", timeout=10)
                item_id = _arr_match_by_name(rs.json(), torrent_name)

        if not item_id:
            return

        # 3. Disparar re-search
        if arr_type == "Radarr":
            log.debug(f"HTTP POST {base}/command (MoviesSearch)")
            sess.post(f"{base}/command",
                          json={"name": "MoviesSearch", "movieIds": [item_id]},
                          timeout=10)
            log.info("Radarr: busca disparada")

        elif arr_type == "Sonarr":
            if extra_ids:
                # Validar data de lancamento dos episodios
                now = datetime.now(timezone.utc)
                released = []
                for eid in extra_ids:
                    try:
                        log.debug(f"HTTP GET {base}/episode/{eid}")
                        re = sess.get(f"{base}/episode/{eid}",
                                         timeout=10)
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
                    log.debug(f"HTTP POST {base}/command (EpisodeSearch)")
                    sess.post(f"{base}/command",
                                  json={"name": "EpisodeSearch",
                                        "episodeIds": released},
                                  timeout=10)
                    log.info(f"Sonarr: busca para {released}")
                else:
                    log.warning(f"Sonarr: '{torrent_name}' episodios nao lancados")
            else:
                log.debug(f"HTTP POST {base}/command (SeriesSearch)")
                sess.post(f"{base}/command",
                              json={"name": "SeriesSearch",
                                    "seriesId": item_id},
                              timeout=10)
                log.info("Sonarr: busca da serie disparada")

    except Exception as e:
        log.error(f"{arr_type}: {e}")


def block_and_search(torrent_hash, torrent_name):
    """Bloqueia nos Arrs e dispara re-search."""
    _handle_arr("Radarr", "radarr", torrent_hash, torrent_name)
    _handle_arr("Sonarr", "sonarr", torrent_hash, torrent_name)


# ── Analise de torrent ─────────────────────────────────────────────────

def is_stalled(torrent, cfg):
    """Verifica se torrent deve ser removido por stalled/no-seeds."""
    g = cfg["guardian"]
    state = torrent.get("state", "")

    # Stalled (parado por X tempo)
    if g.get("remove_stalled") and state in ("stalledDL", "stalledUP", "metaDL"):
        seconds = _time_to_seconds(g.get("stalled_time", 0), g.get("stalled_unit", "hours"))
        if seconds > 0:
            added_on = torrent.get("added_on", 0)
            if time.time() - added_on >= seconds:
                return True, f"stalled ({state}) por >{g['stalled_time']}{g['stalled_unit'][0]}"

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


def check_stalled_and_remove(torrent):
    """Verifica stalled/sem seeds e remove se necessario.

    Funcao leve: so le campos do JSON, sem chamadas HTTP.
    Extraida de analyze_torrent para permitir reavaliacao
    periodica de torrents ja processados (pass 2 do loop).
    Retorna True se removeu o torrent.
    """
    cfg = get_config()
    state = torrent.get("state", "")

    # UP states: skip (torrent ja completou ou esta enviando)
    if state in ("uploading", "stalledUP", "pausedUP", "checkingUP", "queuedUP"):
        return False

    stalled, stalled_reason = is_stalled(torrent, cfg)
    if stalled:
        hash_ = torrent["hash"]
        name = torrent["name"]
        log.verbose(f"[{name}] {stalled_reason} — REMOVIDO")
        block_and_search(hash_, name)
        remove_torrent(hash_)
        send_notification("🗑️ Torrent Removido (stalled)",
                          f"Nome: {name}\nMotivo: {stalled_reason}")
        return True
    return False


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

    # Verificar stalled/sem seeds (funcao extraida, mesma logica)
    if check_stalled_and_remove(torrent):
        return

    files = get_files(hash_)
    if not files:
        log.verbose(f"[{name}] ignorado (sem metadados)")
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
    media_count = 0
    for f in files:
            ext = os.path.splitext(f["name"])[1].lower()
            file_id = f.get("index", f.get("id"))
            if ext in valid_ext:
                set_file_priority(hash_, file_id, prio_media)
                optimized = True
                media_count += 1
            elif ext in {".nfo", ".jpg", ".png", ".txt", ".srt", ".sub", ".idx"}:
                set_file_priority(hash_, file_id, prio_norm)
            else:
                set_file_priority(hash_, file_id, prio_skip)
                log.debug(f"[{name}] Desativado → {f['name']}")
    if optimized:
        log.verbose(f"[{name}] otimizado ({media_count} arquivos de midia priorizados)")
        send_notification("⚡ Torrent Otimizado",
                          f"Nome: {name}\nArquivos de midia priorizados.")


# ── Heartbeat ──────────────────────────────────────────────────────────

def write_heartbeat():
    """Escreve timestamp em /tmp/heartbeat para healthcheck Docker.

    Chamado no startup (main.py), periodicamente (guardian_loop)
    e sob demanda (api_trigger em modo webhook).
    """
    try:
        with open("/tmp/heartbeat", "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


# ── Loop principal ─────────────────────────────────────────────────────

_processed = set()
_check_count = 0


def _prune_processed(current_hashes):
    """Limpa _processed: remove hashes ausentes e aplica hard cap."""
    _processed.intersection_update(current_hashes)
    if len(_processed) > MAX_PROCESSED_SIZE:
        excess = len(_processed) - MAX_PROCESSED_SIZE
        remove = set(list(_processed)[:excess])
        _processed.difference_update(remove)
        log.warning(f"_processed atingiu {MAX_PROCESSED_SIZE}, "
                    f"removidos {excess} hashes antigos")


def guardian_loop():
    global _check_count
    load_config()
    try:
        qbit_login()
    except Exception as e:
        log.error(f"Falha ao conectar no qBit: {e}")
        return

    cfg = get_config()
    interval = cfg["guardian"].get("check_interval_seconds", 300)

    if interval == 0:
        log.info("Guardian iniciado em modo webhook (intervalo=0). Aguardando chamadas /api/trigger.")
        return  # sem loop — so responde a /api/trigger

    log.info(f"Guardian iniciado. Intervalo: {interval}s")

    while True:
        _check_count += 1
        removed_this_check = 0
        new_this_check = 0

        try:
            torrents = get_torrents()
            total = len(torrents)
            new = [t for t in torrents if t["hash"] not in _processed]

            if new:
                new_this_check = len(new)
                for t in new:
                    analyze_torrent(t)
                    _processed.add(t["hash"])

            # Pass 2: reavalia stalled/no-seeds para TODOS os torrents
            # (torrents ja em _processed podem ter ficado stalled depois)
            stalled_removed = 0
            for t in torrents:
                if check_stalled_and_remove(t):
                    stalled_removed += 1

            current_hashes = {t["hash"] for t in torrents}
            removed_this_check = len([h for h in _processed if h not in current_hashes])
            _prune_processed(current_hashes)

            # ── Log INFO: resumo da verificacao ──
            log.info(f"Verificacao #{_check_count}: {total} torrents, "
                     f"{new_this_check} novos, {stalled_removed} stalled removidos, "
                     f"{removed_this_check} removidos do historico")

        except requests.exceptions.ConnectionError:
            log.warning("qBittorrent inacessivel, reconectando...")
            try:
                qbit_login()
            except Exception:
                pass
        except Exception as e:
            log.error(f"Erro: {e}")

        try:
            write_heartbeat()
        except Exception:
            pass

        # Recarrega config a cada iteracao para detectar mudancas no intervalo
        cfg = get_config()
        interval = cfg["guardian"].get("check_interval_seconds", 300)
        if interval == 0:
            log.info("Intervalo alterado para 0 — entrando em modo webhook. Aguardando /api/trigger.")
            return

        time.sleep(interval)


def start_guardian():
    """Inicia o loop em thread separada."""
    t = threading.Thread(target=guardian_loop, daemon=True)
    t.start()
    log.info("Guardian thread iniciada")
    return t
