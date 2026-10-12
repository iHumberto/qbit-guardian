"""Checagem de versao nova publicada — alimenta o aviso no rodape da Web UI.

Compara a versao instalada (`app/version.py`) com a maior **tag de release**
do repositorio. Tag, e nao label da imagem `:latest`, por dois motivos: a tag
e o que tem numero limpo (`v2.5.0`, o formato que o rodape mostra), e um build
de `main` nao e um release — avisar a cada commit transformaria o aviso em
ruido que o usuario aprende a ignorar.

Falha em silencio de proposito: um painel de homelab precisa abrir sem
internet, entao qualquer erro de rede vira "nao sei" (`None`), nunca um erro
na tela. O resultado fica em cache — inclusive o "nao sei", senao uma caixa
offline paga o timeout a cada carregamento de pagina.

A checagem acontece por dois caminhos, com validades diferentes:

- **Periodica** (`TTL_SEGUNDOS`, 6h): uma thread checa no start e a cada
  intervalo, independente de alguem abrir o painel. Sem ela, a consulta so
  acontecia por visita — e o cache em memoria so era zerado reiniciando o
  container, de onde vinha a impressao de que o aviso "so funciona quando o
  server inicia".
- **No carregamento da pagina** (`TTL_PAGINA`, 10min): `/api/version` revalida
  quando o cache passou desse tempo. E o que faz um F5 mostrar a versao que
  saiu ha pouco, em vez de esperar o proximo ciclo de 6h.

As duas validades existem porque as perguntas sao diferentes: quem esta
olhando a tela aceita no maximo 10 minutos de defasagem; quem nao esta so
precisa que o dado esteja quente quando abrir. Com 10min de piso, o teto de
consultas a API do GitHub e 6/h — bem abaixo do limite de 60/h por IP sem
autenticacao.
"""

import re
import threading
import time

import requests

from app.logger import get_logger

log = get_logger("updates")

TAGS_URL = "https://api.github.com/repos/iHumberto/qbit-guardian/tags"
TIMEOUT = 5

# Intervalo da checagem periodica, e validade padrao do cache.
TTL_SEGUNDOS = 6 * 3600

# Validade aceita por quem acabou de abrir o painel. Menor de proposito: e o
# que transforma um F5 em "ja apareceu a versao nova".
TTL_PAGINA = 10 * 60

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


def ultima_versao(agora=None, validade=None):
    """Maior versao publicada, do cache ou da API. None se desconhecida.

    `validade` e a idade maxima aceita para o valor em cache, em segundos.
    O default (`TTL_SEGUNDOS`) serve a checagem periodica; `/api/version` pede
    `TTL_PAGINA`, mais curto, porque quem esta com a tela aberta quer ver a
    novidade no refresh. `validade=0` forca a consulta.
    """
    agora = time.time() if agora is None else agora
    validade = TTL_SEGUNDOS if validade is None else validade
    with _lock:
        if _cache["em"] and (agora - _cache["em"]) < validade:
            return _cache["versao"]
    versao = _buscar()
    with _lock:
        _cache["em"] = agora
        _cache["versao"] = versao
    return versao


# ── Checagem periodica ─────────────────────────────────────────────────

_parar_checagem = threading.Event()


def _loop_de_checagem(intervalo=None):
    """Consulta no start e a cada `intervalo`, ate `_parar_checagem`.

    Roda mesmo sem ninguem abrir o painel: assim o aviso nao depende de visita
    e o primeiro carregamento do dia ja encontra o dado quente, sem pagar o
    timeout da consulta.
    """
    intervalo = TTL_SEGUNDOS if intervalo is None else intervalo
    while True:
        try:
            # `validade=0`: este e o ciclo que renova o cache, nao um leitor
            # dele — reaproveitar o valor antigo aqui seria nao checar nada.
            versao = ultima_versao(validade=0)
            log.debug(f"Checagem periodica de versao: {versao or 'desconhecida'}")
        except Exception as e:
            # A thread nao pode morrer: sem ela o aviso volta a depender de
            # visita, e em silencio.
            log.debug(f"Checagem periodica de versao falhou: {e}")
        if _parar_checagem.wait(intervalo):
            return


def iniciar_checagem_periodica(intervalo=None):
    """Sobe a thread da checagem periodica (daemon). Devolve a thread."""
    _parar_checagem.clear()
    t = threading.Thread(target=_loop_de_checagem, args=(intervalo,), daemon=True)
    t.start()
    log.info("Checagem de versao a cada "
             f"{(TTL_SEGUNDOS if intervalo is None else intervalo) // 3600}h")
    return t


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
