"""Versao da aplicacao — fonte unica da verdade.

O CI le este arquivo e grava o valor em `org.opencontainers.image.version` na
imagem publicada. Antes disso o label vinha do `docker/metadata-action`, que
sem tag de release so tinha a tag `latest` para oferecer — e a imagem se
anunciava como versao "latest", o que deixava a notificacao do Watchtower sem
nada util para mostrar.

Ao subir a versao aqui, atualize tambem o CHANGELOG.md: ha teste de paridade
entre os dois (test_guardian.py > TestVersaoDaImagem).
"""

__version__ = "2.5.1"
