#!/usr/bin/env python3
"""Imprime a secao do CHANGELOG.md de uma versao — corpo do GitHub Release.

Uso: changelog_section.py 2.6.0 [caminho/do/CHANGELOG.md]

Mora em `.github/scripts/` por ser maquinario de publicacao: so roda no runner,
em push de tag, e nunca sai de la. A pasta `scripts/` da raiz e outra coisa —
entregavel para o usuario copiar (o hook do qBittorrent), e misturar as duas
apagaria essa distincao.

Fica como script, e nao como regex dentro do YAML, por dois motivos: a suite
consegue testar a extracao contra o CHANGELOG real, e um erro aqui falha com
mensagem em vez de publicar um release com corpo vazio.

Sai com codigo 1 quando a versao nao tem secao — release sem notas e pior que
release nenhum, entao o workflow para em vez de publicar algo vazio.
"""

import os
import re
import sys

# .github/scripts/<arquivo> -> sobe tres niveis para chegar a raiz do repo.
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PADRAO = r"(?m)^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)"


def secao(versao, texto):
    """Corpo da secao da versao, sem o cabecalho `## [x.y.z] - data`.

    O cabecalho fica de fora porque a pagina do release ja mostra a versao e a
    data; repetir vira ruido no topo das notas.
    """
    achado = re.search(PADRAO % re.escape(versao), texto, re.DOTALL)
    return achado.group(1).strip() if achado else None


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    versao = argv[1].lstrip("v")
    caminho = argv[2] if len(argv) > 2 else os.path.join(RAIZ, "CHANGELOG.md")

    with open(caminho, encoding="utf-8") as f:
        corpo = secao(versao, f.read())

    if not corpo:
        print(f"CHANGELOG.md sem secao para a versao {versao}", file=sys.stderr)
        return 1

    print(corpo)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
