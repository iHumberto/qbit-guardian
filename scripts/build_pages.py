#!/usr/bin/env python3
"""Monta o bundle estatico da demonstracao publica (GitHub Pages).

O tour guiado roda em cima das telas REAIS — e essa e a decisao que ele nao
pode perder ao virar pagina estatica. Por isso aqui nada e escrito a mao: as
telas sao copiadas de `static/`, e o unico JSON do bundle e gerado importando
o modulo `guardian` de verdade. Uma copia editada a mao do `index.html`
reintroduziria exatamente o desvio que o tour existe para evitar.

O que o `/demo` precisa do servidor sao DOIS GETs, e os dois sao
deterministicos:

  api/demo-config  `config_default()` + DEFAULT_NOTIFICATIONS +
                   NOTIFICATION_VARIABLES, sem disco e sem segredo (o bloco
                   `webui` e removido, como na rota reitera)
  api/version      so o numero, lido de `app/version.py`. A rota do app
                   tambem consulta a API do GitHub para o aviso de versao
                   nova; aqui isso nao existe, e o `loadVersion()` do painel
                   ja trata a ausencia sem alarme.

                   No app essa rota exige sessao, para nao anunciar a versao
                   exata de uma instalacao a quem nao esta logado. Publica-la
                   aqui nao abre o mesmo flanco: o bundle nao e a instalacao
                   de ninguem, e a versao que ele mostra e a do repositorio
                   publico, que ja esta no CHANGELOG e nas releases.

Todo o resto do modo demonstracao ja e cliente: o `tour.js` troca o
`window.fetch` antes do script da pagina rodar, escrita nenhuma sai do
navegador e `api/config`/`api/defaults` saem do mesmo corpo do demo-config.

Estrutura gerada (plana de proposito — as telas referenciam os assets por
caminho relativo, e um bundle plano faz `demo.html` e `login.html`
resolverem `i18n.js` no mesmo nivel, com ou sem prefixo de repositorio):

    _site/
      .nojekyll
      index.html        redireciona para login.html?tour=1
      login.html        copia de static/, com a flag injetada
      demo.html         copia de static/index.html, com a flag injetada
      i18n.js  tour.js  favicon.svg
      api/demo-config
      api/version

Uso:
    python -m scripts.build_pages [destino]     # padrao: _site
"""

import json
import os
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(RAIZ, "static")

# A flag que liga o modo estatico no `tour.js`: sem backend, nenhuma escrita
# deve sair do navegador — nem o POST da tela de login, que no app de verdade
# e legitimo. Injetada ANTES do `tour.js`, que a le na carga.
FLAG = '<script>window.QBIT_DEMO_ESTATICO = true;</script>\n'
ANCORA_FLAG = '<script src="tour.js"></script>'

# No app o tour comeca pela rota `/login`; no bundle, pelo arquivo.
LINK_TOUR_APP = 'href="/login?tour=1"'
LINK_TOUR_BUNDLE = 'href="login.html?tour=1"'

COPIAR = ["i18n.js", "tour.js", "favicon.svg"]

REDIRECT = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>qbit-guardian — demonstracao</title>
<link rel="icon" href="favicon.svg">
<meta http-equiv="refresh" content="0; url=login.html?tour=1">
</head>
<body>
<p><a href="login.html?tour=1">Abrir a demonstracao</a></p>
</body>
</html>
"""


def _ler(nome):
    with open(os.path.join(STATIC, nome), encoding="utf-8") as f:
        return f.read()


def preparar_pagina(html):
    """Injeta a flag do modo estatico e aponta o link do tour para o arquivo.

    As duas sao substituicoes mecanicas e verificadas: se a ancora sumir do
    `static/`, isto estoura em vez de publicar uma pagina que tentaria falar
    com uma API inexistente.
    """
    if ANCORA_FLAG not in html:
        raise SystemExit(f"ancora {ANCORA_FLAG!r} nao encontrada — "
                         "o <script> do tour mudou de forma em static/")
    html = html.replace(ANCORA_FLAG, FLAG + ANCORA_FLAG, 1)
    if LINK_TOUR_APP not in html:
        raise SystemExit(f"link {LINK_TOUR_APP!r} nao encontrado — "
                         "o botao do tour mudou de destino em static/")
    return html.replace(LINK_TOUR_APP, LINK_TOUR_BUNDLE)


def demo_config():
    """O MESMO corpo que a rota `/api/demo-config` serve.

    Importa o modulo de verdade: se `config_default()` ganhar chave, o bundle
    ganha junto, sem ninguem lembrar de mexer aqui.
    """
    sys.path.insert(0, RAIZ)
    import app.guardian as guardian

    cfg = guardian.config_default()
    cfg.pop("webui", None)
    return {
        "config": cfg,
        "defaults": {
            "notifications": guardian.DEFAULT_NOTIFICATIONS,
            "notification_variables": guardian.NOTIFICATION_VARIABLES,
        },
    }


def versao():
    sys.path.insert(0, RAIZ)
    from app.version import __version__
    return {"version": __version__}


def construir(destino):
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    os.makedirs(os.path.join(destino, "api"))

    def escrever(caminho, texto):
        alvo = os.path.join(destino, caminho)
        with open(alvo, "w", encoding="utf-8") as f:
            f.write(texto)

    # `.nojekyll`: sem ele o Pages roda o Jekyll, que ignora o que comeca com
    # `_` e nao tem nada a fazer com um bundle que ja esta pronto.
    escrever(".nojekyll", "")
    escrever("index.html", REDIRECT)
    escrever("login.html", preparar_pagina(_ler("login.html")))
    escrever("demo.html", preparar_pagina(_ler("index.html")))
    for nome in COPIAR:
        shutil.copyfile(os.path.join(STATIC, nome),
                        os.path.join(destino, nome))
    escrever(os.path.join("api", "demo-config"),
             json.dumps(demo_config(), ensure_ascii=False))
    escrever(os.path.join("api", "version"),
             json.dumps(versao(), ensure_ascii=False))
    return destino


if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "_site")
    construir(alvo)
    print(f"bundle em {alvo}")
    for raiz, _, arquivos in os.walk(alvo):
        for nome in sorted(arquivos):
            caminho = os.path.join(raiz, nome)
            rel = os.path.relpath(caminho, alvo)
            print(f"  {rel}  {os.path.getsize(caminho)}B")
