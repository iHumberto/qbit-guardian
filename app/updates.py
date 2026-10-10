"""Checagem de versao nova publicada — alimenta o aviso no rodape da Web UI.

Compara a versao instalada (`app/version.py`) com a maior **tag de release**
do repositorio. Tag, e nao label da imagem `:latest`, por dois motivos: a tag
e o que tem numero limpo (`v2.5.0`, o formato que o rodape mostra), e um build
de `main` nao e um release — avisar a cada commit transformaria o aviso em
ruido que o usuario aprende a ignorar.

Falha em silencio de proposito: um painel de homelab precisa abrir sem
internet, entao qualquer erro de rede vira "nao sei" (`None`), nunca um erro
na tela. O resultado fica em cache por `TTL_SEGUNDOS` — inclusive o "nao sei",
senao uma caixa offline paga o timeout a cada carregamento de pagina.
"""

import re
import threading
import time

import requests

from app.logger import get_logger

log = get_logger("updates")

TAGS_URL = "https://api.github.com/repos/iHumberto/qbit-guardian/tags"
TIMEOUT = 5
TTL_SEGUNDOS = 6 * 3600

_RE_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

_cache = {"em": 0.0, "versao": None}
_lock = threading.Lock()


def _como_tupla(versao):
    """`"2.4.0"` -> `(2, 4, 0)`. Devolve None para o que nao for x.y.z.

    O sufixo de build dos builds de `main` (`2.4.0+a81f306`) e descartado: ele
    identifica o commit, nao a versao, e nao participa da comparacao.
    """
    if not versao:
        return None
    achado = _RE_TAG.match(str(versao).split("+", 1)[0].strip())
    return tuple(int(p) for p in achado.groups()) if achado else None


def _maior_tag(tags):
    """Maior versao entre os nomes de tag, ignorando o que nao for x.y.z."""
    versoes = []
    for tag in tags:
        nome = tag.get("name") if isinstance(tag, dict) else tag
        t = _como_tupla(nome)
        if t:
            versoes.append(t)
    if not versoes:
        return None
    return ".".join(str(p) for p in max(versoes))


def _buscar():
    """Maior tag publicada, ou None se a consulta nao der certo."""
    try:
        r = requests.get(TAGS_URL, timeout=TIMEOUT,
                         headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            log.debug(f"Checagem de versao: HTTP {r.status_code}")
            return None
        return _maior_tag(r.json())
    except Exception as e:
        log.debug(f"Checagem de versao: {e}")
        return None


def ultima_versao(agora=None):
    """Maior versao publicada, com cache de `TTL_SEGUNDOS`. None se desconhecida."""
    agora = time.time() if agora is None else agora
    with _lock:
        if _cache["em"] and (agora - _cache["em"]) < TTL_SEGUNDOS:
            return _cache["versao"]
    versao = _buscar()
    with _lock:
        _cache["em"] = agora
        _cache["versao"] = versao
    return versao


def ha_atualizacao(instalada, disponivel):
    """True so quando a publicada e **estritamente maior** que a instalada.

    A comparacao e por tupla, nao por texto: `"2.10.0" > "2.9.0"` e falso em
    ordem alfabetica. Tag mais velha que o instalado (o repo ficou com
    `v2.0.5` enquanto o codigo andou ate 2.4.0) nao vira aviso de downgrade.
    """
    atual = _como_tupla(instalada)
    nova = _como_tupla(disponivel)
    if not atual or not nova:
        return False
    return nova > atual


def limpar_cache():
    """Zera o cache — usado pelos testes."""
    with _lock:
        _cache["em"] = 0.0
        _cache["versao"] = None
