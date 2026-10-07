# Changelog

Todas as mudancas notaveis deste projeto serao documentadas neste arquivo.

O formato e baseado no [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
e o projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] — 2026-10-07

Tela de login propria no lugar do popup nativo do navegador.

### Adicionado
- **Pagina de login** (`/login`), com a paleta e os tokens do resto do painel: card centralizado, usuario, senha e um aviso de onde achar a senha inicial. Seletor de idioma no canto, como no painel. Nao carrega nada de fora — painel de homelab precisa abrir sem internet.
- **Sessao por cookie assinado.** `POST /api/login` troca credencial por um token assinado com `webui.secret_key`, provisionada no startup junto com a senha. O cookie e `HttpOnly` (fora do alcance de qualquer JS), `SameSite=Lax` (nao acompanha POST disparado por outro site) e vale 7 dias.
- **O token carrega um marcador do par usuario+senha**, entao trocar qualquer um dos dois invalida todas as sessoes abertas — sem precisar guardar lista de sessao nenhuma. Apagar `webui.secret_key` do config e o botao de panico: derruba tudo de uma vez.
- **Botao "Sair"** no modal de conta. Com Basic Auth nao havia como sair; com sessao, sair e expectativa basica.
- **Freio de forca bruta** no login: 5 tentativas por cliente em 5 minutos, depois `429` com `Retry-After`. Com formulario (em vez do popup do navegador) um script consegue tentar milhares de senhas sem atrito. A janela desliza, o bloqueio vale **tambem para a senha certa** — senao bastaria errar quatro vezes e acertar na quinta sem custo — e a contagem e por cliente, para um vizinho errando a senha nao trancar os outros.

### Alterado
- **O header `WWW-Authenticate` saiu das respostas 401.** Era ele que fazia o navegador abrir o popup nativo de usuario e senha. Agora navegacao sem sessao **redireciona** para `/login`, enquanto chamada de API continua recebendo `401` em JSON — o `fetch` da propria pagina precisa do 401 para mostrar o erro.
- **HTTP Basic Auth continua funcionando** para quem nao tem tela onde digitar: `curl`, scripts e o hook do webhook seguem iguais. As duas formas convivem de proposito.
- `static/i18n.js` e `static/favicon.svg` passaram a ser **publicos**, por uma allowlist explicita: a tela de login os carrega antes de existir sessao. Sao strings de interface e um icone — nenhum dado de configuracao. `index.html` continua exigindo autenticacao.
- Trocar credenciais pelo modal agora manda para `/login` em vez de recarregar o painel: a sessao acabou de ser invalidada, e recarregar so mostraria 401.
- `webui.secret_key` nunca e devolvida pelo `GET /api/config` nem aceita pelo `POST /api/config` — quem a tiver forja login.

### Notas
- Testes: 476 → **546**. Cobertura: **100%** em `app/web.py` e `app/auth.py`; 99% de ramo no total, zero statements descobertos.
- 29 mutacoes da tela de login aplicadas uma a uma, 29 pegas — depois de fechar duas lacunas que a primeira rodada expos: nada verificava o provisionamento da `secret_key` (sem ela a tela de login devolve 500 numa instalacao nova) e o teste do botao Sair conferia a regra CSS sem conferir se o botao tinha a classe.
- Uma das mutacoes nao verificava nada: trocar `TENTATIVAS_MAX` por um valor alto deixava a suite verde, porque os testes montam o cenario lendo a propria constante. Virou `TestConstantesDeSeguranca`, que fixa a faixa aceitavel (3 a 10 tentativas, janela >= 60s, sessao <= 30 dias) em vez do cenario.
- Fluxo verificado no navegador: redirecionamento sem sessao, login com senha errada e certa, cookie invisivel ao JS, freio disparando na sexta tentativa, troca de idioma e botao de sair.

## [2.2.0] — 2026-10-07

Endurecimento de seguranca a partir de uma auditoria da superficie de ataque.
**Esta versao pede duas acoes de quem ja roda o guardian** — ver "Atualizando"
nos READMEs: `chown -R 1000:1000 ./config` e, no modo webhook,
`QBIT_GUARDIAN_PASS` no servico do qBittorrent.

### Corrigido (seguranca)
- **CSRF no `POST /api/config`.** `request.get_json(force=True)` aceitava `Content-Type: text/plain`, que nao dispara preflight de CORS. Qualquer pagina que a vitima visitasse podia disparar um POST, e o navegador anexava o Basic Auth dela automaticamente — dava para apontar `qbit.url` para fora (e vazar a API key do qBittorrent no header `Authorization`), transformar `.mkv` em extensao perigosa (e apagar a biblioteca, porque a remocao usa `deleteFiles=true`) ou simplesmente trocar as credenciais. Agora escrita exige `application/json` e e recusada quando `Sec-Fetch-Site`/`Origin` indicam outro site. `curl` e o hook do webhook nao sao afetados: cliente que nao e navegador nao sofre CSRF.
- **Segredos expostos sem autenticacao.** O default era `webui` vazio, o que desligava a auth, e o compose publica a porta 5000 em todas as interfaces: `GET /api/config` devolvia `qbit.api_key`, `sonarr.api_key`, `radarr.api_key`, a `apprise_url` (que embute o token do bot) e a propria senha da Web UI para quem alcancasse a porta. A autenticacao passou a ser provisionada no startup e a senha sumiu da resposta.
- **`/index.html` e `/i18n.js` eram publicos** enquanto `/` pedia senha: a rota estatica automatica do Flask nao passava pelo `@requires_auth`. Agora os arquivos de `static/` sao servidos por rota propria, autenticada. `/api/health` continua publico, para o healthcheck do Docker.
- **Credenciais comparadas com `==`**, que vaza pelo tempo de resposta quantos caracteres do inicio estao certos. Trocado por `hmac.compare_digest`, e usuario e senha sao sempre os dois verificados: encerrar cedo revelaria que o nome existe.
- **Sem limite de corpo.** Um POST arbitrariamente grande era parseado em memoria e gravado no `config.json`. Teto de 1 MB, com `413` em JSON.
- **Token do Apprise no log.** `send_notification` registrava a `apprise_url` inteira em `DEBUG` — e em `tgram://TOKEN/CHAT` o authority **e** a credencial. Agora so o esquema sai no log para os esquemas proprios do Apprise; em `http(s)` sem userinfo o host continua visivel, que ajuda a depurar e nao e segredo.
- **Container rodava como root.** Passou a rodar como UID 1000. O arquivo de configuracao deixa de ser escrito como root no volume do host.
- **Hook do webhook engolia falhas.** `curl -s` sem `-f` sai com codigo 0 num 401, entao nem a tentativa extra percebia: o modo webhook parava de funcionar sem nenhum sinal. Agora usa `-sf`, manda credenciais e reporta no stderr do qBittorrent.

### Adicionado
- **Autenticacao obrigatoria com senha provisionada.** Sem tela de cadastro: no primeiro startup o guardian gera a senha, grava o hash e imprime usuario e senha no stdout — `docker logs qbit-guardian`. Vai em `print`, nao em `log`: o compose publicado usa `LOG_LEVEL=ERROR`, e uma senha anunciada em INFO nao apareceria justamente na hora em que o usuario precisa dela. Usuario padrao `admin`.
- **Senha guardada como hash PBKDF2-SHA256** (600k iteracoes, salt por senha), nunca em texto claro. Config gravada antes desta versao tem a senha em texto: ela continua autenticando e e convertida para hash no primeiro startup, sem o usuario precisar fazer nada.
- **Icone de conta na Web UI** (o `circle-user` do prototipo Penpot) abrindo um popup com usuario, senha atual e nova senha. A senha atual e sempre exigida — e a prova de identidade que impede que um navegador deixado aberto vire troca de credencial. Quem so quer trocar o nome deixa a nova senha em branco, e vice-versa.
- **`POST /api/credentials`**, unica porta para trocar usuario/senha. A secao `webui` passou a ser **descartada** no `POST /api/config`: sem isso, a troca de senha seria contornavel por um POST de configuracao comum.
- Cabecalhos `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` e `Referrer-Policy: no-referrer`.
- `QBIT_GUARDIAN_USER` e `QBIT_GUARDIAN_PASS` no hook do webhook.
- Guarda no `conftest.py` que falha qualquer teste que grave no `config.json` versionado — um teste que executava o entrypoint de verdade rodou o provisionamento contra o caminho padrao e sujou um arquivo rastreado.

### Notas
- Testes: 313 → **476**. Cobertura: **99%** de ramo, zero statements descobertos.
- 32 mutacoes de seguranca aplicadas uma a uma, 31 pegas. A sobrevivente (devolver `force=True` ao `get_json`) e **equivalente**: com `_exige_json()` no lugar, os dois se comportam igual — o que protege e o guarda, e remove-lo e pego por teste. Documentado no codigo para ninguem tirar o guarda achando que o `get_json()` sozinho basta.
- A auditoria tambem confirmou o que **nao** e problema: path traversal e barrado pelo Werkzeug (6 variantes testadas), nao ha `eval`/`exec`/`subprocess`/`pickle`/`yaml.load` no projeto, e nao ha sink de XSS no DOM — todo valor de config entra por `.value`/`.checked`/`.textContent`.
- Continua possivel desligar a autenticacao esvaziando `webui`, para quem ja protege a porta com proxy reverso + SSO. Deixou de ser o padrao, e o proximo restart religa.

## [2.1.2] — 2026-10-07

Fechamento das lacunas de cobertura. **Nenhuma mudanca de comportamento em
producao**: so testes, configuracao de cobertura e documentacao.

### Adicionado
- **Contrato HTTP com o qBittorrent sob teste** (`TestQbitHttpContract`). Os quatro wrappers da API (`qbit_login`, `get_torrents`, `get_files`, `remove_torrent`) eram sempre substituidos INTEIROS nos testes, entao o corpo deles nunca executava: endpoint, forma do payload, `timeout` e autenticacao nao tinham verificacao nenhuma — a mesma classe de buraco que deixou a escala de prioridade errada chegar em producao. Agora ha uma `Session` falsa que registra cada chamada e os testes exigem: hash em `params` (nao concatenado na URL), `deleteFiles=true` no delete, `raise_for_status()` nos GETs, `timeout=10` em todas as cinco chamadas, HTTP != 200 no login virando `RuntimeError`, e a `api_key` **somente** no header `Authorization: Bearer` — nunca em query string (onde entraria no log de acesso do reverse proxy) nem no corpo.
- **Estados UP nunca sao removidos** (`TestCheckStalledEstadosUp`), parametrizado nos cinco estados, com um torrent que satisfaria todos os gatilhos de remocao. E o caminho mais destrutivo do codigo: remocao usa `deleteFiles=true`, ou seja, apaga do disco midia que ja terminou de baixar.
- **Lista de extensoes de midia vazia nao apaga tudo** (`TestListaDeMidiaVazia`). `valid_media_extensions: []` e alcancavel pela Web UI; se a checagem de "nenhum arquivo de midia valido" rodasse com a lista vazia, TODO torrent seria removido com os arquivos. A deteccao de extensoes perigosas continua ativa nesse estado.
- **Flask nunca sobe com `debug=True`** e **guardian roda em thread daemon** (`TestEntrypointsFiacao`). Com o debugger do Werkzeug ligado, qualquer um que alcance a porta executa Python arbitrario no container, sem passar pelo Basic Auth. O `app/main.py` tambem passou a ter teste de ordem: heartbeat antes de subir guardian e web, porque o HEALTHCHECK comeca a rodar junto com o processo.
- **Contagem do pass 2** (`TestPassDoisContagem`): `/api/trigger` e o resumo do loop reportam quantos torrents foram removidos. O incremento nunca executava em teste — um off-by-one ali mentiria no log sem quebrar nada.
- **Resiliencia do loop** (`TestGuardianLoopCorpo`, `TestConnectRetryResiliencia`): torrent sem metadados nao e marcado como processado; erro de dominio loga sem reconectar (so erro de transporte reconecta); `/tmp` cheio ou somente-leitura nao derruba a thread, nem no loop nem durante o retry.
- **Config corrompida nao derruba o healthcheck** (`TestHealthcheckConfigIlegivel`) e **contrato de exit code** (`TestHealthcheckExitCode`, incluindo execucao do script via subprocess, como o Dockerfile faz). Uma excecao em `_read_intervals` sairia como traceback e exit != 0: o container ficaria `unhealthy` para sempre mesmo com o guardian vivo — e `restart: always` nao reinicia container unhealthy. O fallback tambem nao pode cair em `interval=0`, que silenciaria a deteccao de loop morto.
- **Ramo de descarte da otimizacao** (`TestOtimizacaoPrioridades`): `.url`, `.lnk`, `.par2` e companhia recebem `priority_skip` e nao sao baixados. O ramo `else` nunca tinha executado em teste.
- **Limites do criterio "sem seeds"** (`TestIsStalledSemSeedsLimites`): `no_seeds_time: 0` significa desligado, nunca "remover agora" — e e o valor que a config default grava.
- **`{{stalledTime}}` vazio quando o limiar nao se aplica** (`TestStalledThresholdDesligado`): o evento `stalled` tambem e disparado pelo ramo de "0 seeds", onde `stalled_time` nao foi o criterio. Preencher o limiar ali faria a notificacao afirmar um prazo que nao foi usado.
- **`.coveragerc`** com `source`, `branch` e as exclusoes convencionais, para `coverage report` ser reproduzivel. A CI nao mede cobertura; o arquivo serve ao uso local, documentado nos dois READMEs.
- **Paridade da contagem de testes nos READMEs** (`TestReadmeContagemDeTestes`): as mencoes dentro de cada README e entre os dois idiomas tem de contar a mesma historia, e o total tem de ser a soma das partes.

### Corrigido
- A tabela de stack dos dois READMEs afirmava **79 testes** desde varias versoes atras: a linha do comando `pytest` vinha sendo atualizada e a da tabela ficava para tras. Agora ha teste proibindo a divergencia.

### Notas
- Testes: 249 → 313. Cobertura: 88% → **99%** (branch, `app/` inteiro), com **zero statements descobertos**. O unico ramo restante (`guardian.py 414->exit`) e defensivo e comprovadamente inalcancavel: exige `arr_type` fora de Radarr/Sonarr **com** `item_id` preenchido, e so os dois tipos tratados preenchem o id.
- As 24 regressoes correspondentes foram injetadas uma a uma e todas ficaram vermelhas, mais tres mutacoes na contagem dos READMEs.
- A sugestao de "notificacao Apprise apos N retries", registrada como pendencia aberta desde a v2.0.6, foi **descartada**: era mitigacao opcional autogerada na secao de riscos do planejamento, nunca um requisito. O healthcheck mede a saude do processo guardian; indisponibilidade do qBittorrent e estado externo (pode ser config do usuario ou problema no proprio qBittorrent) e nao justifica notificar.

## [2.1.1] — 2026-10-07

Ajustes de layout reportados a partir de uma captura da instalacao em producao.

### Corrigido
- O seletor de unidade de tempo (stalled e sem seeds) tinha largura fixa de 84px, mas "segundos" precisa de 97px com o padding — o texto era **cortado**. Passou a `width:auto` com `min-width:104px`, que cobre a maior opcao tambem em en-US. Largura fixa ali volta a cortar assim que uma traducao crescer, entao ha teste proibindo.
- Cada card da coluna 1 (qBittorrent, Radarr, Sonarr) acumulava **~60px de vazio no rodape**. Os tres sao pequenos e esticam ate a altura da coluna Guardian; a sobra agora e distribuida (`space-evenly`), e o vazio cai para ~16px em cima e embaixo.
- O liga/desliga das linhas de remocao ficava solto depois do campo de unidade, deixando um buraco ate a borda do card. Passou para a linha do rotulo, encostado na direita — mesma anatomia dos blocos de mensagem de notificacao, que ja faziam assim.

### Alterado
- As caixas de mensagem de notificacao crescem com a sobra da coluna 3 (`flex:1`): espaco que antes ficava vazio no rodape do card vira area de edicao.
- Campo numerico das linhas de remocao de 69 para 76px, para o valor nao disputar espaco com o stepper nativo.
- Prototipo Penpot atualizado junto: toggle na linha do rotulo em ΔX 315 e unidade de 84 para 104px.

### Notas
- Testes: 242 → 249, com as cinco regressoes verificadas por mutacao.

## [2.1.0] — 2026-10-07

Segunda e ultima fatia da nova Web UI desenhada no Penpot: as mensagens de
notificacao deixam de ser hardcoded e passam a ser editaveis, com liga/desliga
por tipo.

### Adicionado
- **Mensagens de notificacao editaveis**, uma por tipo de evento (`optimized`, `removed`, `stalled`), na Web UI ou direto no `config.json`. Dentro do texto, cada `{{...}}` e substituida pelo valor do torrent. Placeholder desconhecido fica **literal** na mensagem: um erro de digitacao aparece em vez de sumir em silencio.
- **Liga/desliga em dois niveis**, como no prototipo: `notifications.enabled` (geral, no cabecalho do card) e `events.<evento>.enabled` (por tipo). O envio so acontece com os dois ligados. Com a mensagem desligada, o texto **continua visivel** na Web UI mas nao pode ser alterado; com o geral desligado, os toggles de tipo tambem travam, preservando o estado de cada um para quando religar.
- Variaveis por evento, listadas sob cada caixa na Web UI e documentadas nos dois READMEs: `{{torrentName}}`, `{{priorityMedia}}`, `{{priorityAux}}`, `{{mediaCount}}` (otimizado); `{{torrentName}}`, `{{reason}}`, `{{extensions}}` (removido); `{{torrentName}}`, `{{reason}}`, `{{state}}`, `{{stalledTime}}` (stalled).
- Novo endpoint `GET /api/defaults` (autenticado) com os titulos/templates padrao e as variaveis de cada evento. A Web UI consome isto em vez de carregar copia das strings: config gravada antes desta versao nao tem a chave `events`, e sem o default a caixa apareceria vazia enquanto o guardian usaria o texto padrao — a tela mentiria sobre o que seria enviado.
- Novas chaves de config: `notifications.enabled` e `notifications.events.<evento>` com `enabled`, `title` e `template`. Todas opcionais, com fallback campo a campo.
- Testes: 192 → 242. Cobertura de `app/guardian.py`: 89% → 90%.

### Alterado
- Os tres `send_notification()` com f-string hardcoded deram lugar a `notify(evento, **variaveis)`, que resolve titulo e template, aplica os dois niveis de toggle e renderiza.
- Os textos padrao **reproduzem exatamente** as mensagens das versoes anteriores: quem atualizar o container sem mexer na config continua recebendo a notificacao de sempre. Tres testes de regressao comparam o titulo e o corpo byte a byte com o que a v2.0.8 enviava.

### Corrigido
- Caixa de mensagem apagada (vazia, so espacos, nula ou nao-string) volta ao texto padrao em vez de enviar notificacao em branco. O mesmo vale para o titulo.

### Notas
- O **titulo** de cada evento nao e exposto na Web UI — o prototipo mostra uma caixa por tipo, e o `deep_merge` do backend preserva o titulo gravado. Continua editavel no `config.json`.
- `{{stalledTime}}` vem vazio quando a remocao foi pelo ramo de "0 seeds", onde o limiar de stalled nao se aplica; `{{extensions}}` vem vazio quando o motivo foi ausencia de midia valida.

## [2.0.8] — 2026-10-07

Primeira fatia da nova Web UI desenhada no Penpot. Esta entrega e so a camada
visual — os templates de mensagem de notificacao vem na v2.1.0.

### Alterado
- Web UI migrada de **2 para 3 colunas**, fechando a divergencia protótipo × codigo que estava aberta desde 2026-09-21. Coluna 1: qBittorrent → Radarr → Sonarr (a ordem anterior trazia Sonarr antes de Radarr). Coluna 2: Guardian. Coluna 3: Notificacoes, que antes dividia espaco com os servicos externos.
- Grade e formas vindas do design system medido no prototipo: colunas de 365px com gutters de 28px (container 1151px), cards com radius 15 e borda `#ffffff` 1px, padding 14/26, campos curtos em pilula de 26px (radius 13), caixas de texto com radius 15, caixas de valor+unidade com radius 16. Os valores viraram tokens CSS em `:root`, e a largura do container e calculada a partir deles em vez de um numero solto.
- Paleta fiel ao prototipo: campos com fundo branco e texto escuro, bordas e titulos em branco, botao Salvar com fundo de card e borda branca. O accent `#e94560` passa a aparecer so em `:focus` e no toast de erro. Era a unica divergencia de cor ainda sem decisao no design system.
- Tipografia do prototipo: titulo 36px, rotulos e titulos de secao 14px, texto de ajuda 11px, botao 16px. A familia Source Sans Pro e usada se estiver instalada, com fallback para a fonte do sistema — um painel de homelab precisa abrir sem internet, entao nenhuma webfont remota e carregada.
- O checkbox nativo deu lugar ao **switch** do prototipo como padrao unico de liga/desliga. CSS puro sobre o proprio `input[type=checkbox]`, entao estado, teclado e `<label for>` continuam funcionando sem JS.
- Separadores `<hr>` removidos dos cards: o prototipo nao os tem.
- Responsivo: abaixo de 1200px as tres colunas empilham. O breakpoint subiu de 768px porque tres colunas de 365px precisam de 1151px de conteudo; espremer antes disso quebra os rotulos longos.

### Adicionado
- Icone **Docs** no cabecalho, com tooltip em hover e clique abrindo a documentacao do projeto no idioma ativo (`docs/pt-BR` ou `docs/en-US`). Novo mecanismo `data-i18n-href` no i18n para o link acompanhar o idioma, e novas chaves `docs_label`, `docs_tooltip` e `docs_url` nos dois idiomas.
- Testes: 174 → 192. `TestWebUILayout` trava a grade de 3 colunas, a ordem das secoes, os tokens do design system e a derivacao da largura do container; `TestWebUIDocsLink` trava o link (nova aba com `noopener`, tooltip escondido por padrao, URL por idioma) e verifica que a pasta de docs apontada **existe no repo e tem conteudo**.

### Corrigido
- Acessibilidade: os 13 campos do formulario nao tinham `<label for>`, entao nenhum leitor de tela associava rotulo e campo (o Chrome reportava "No label associated with a form field"). Todos associados, com teste de regressao.

## [2.0.7] — 2026-10-07

### Corrigido
- Bug: `_arr_match_by_name()` casava com item sem titulo. `item.get("title", "").lower() in torrent_name.lower()` — `"" in qualquer_string` e sempre `True`, entao um unico item sem `title` (ou com titulo vazio/nulo) na resposta do Sonarr/Radarr casava com QUALQUER torrent e disparava `MoviesSearch`/`SeriesSearch` na midia errada. Itens sem titulo agora sao ignorados.
- Bug: o fallback por nome nunca casava com release name real. O *Arr devolve o titulo com espacos (`Breaking Bad`) e o torrent usa separadores (`Breaking.Bad.S01E01.1080p`), entao a comparacao crua por substring era codigo morto na pratica — o unico "match" que acontecia era o acidental do bug acima. A comparacao passa por `_normalize_title()`: minusculas, separadores viram espaco e as pontas sao delimitadas, o que tambem evita casar titulo curto no meio de outra palavra (`Her` em `Where`).
- Web UI: escala de prioridade errada (pendencia aberta desde v2.0.5). Os tres campos eram `<input type="number" min="0" max="7">` e o rotulo dizia "(0–7)", mas o `POST /api/v2/torrents/filePrio` do qBittorrent aceita apenas `0`, `1`, `6` e `7` — 2 a 5 devolvem HTTP 400. Quem digitasse `4` tinha a priorizacao silenciosamente descartada (o motor recusa com WARNING desde v2.0.5). Agora sao `<select>` com so os valores validos; um config gravado antes disso com valor invalido cai no default da chave em vez de abrir o campo em branco.
- `app/healthcheck.py`: a tolerancia ignorava `retry_interval_seconds`. Era `max(600s, 3 × check_interval)`, mas durante indisponibilidade do qBit o heartbeat sai no ritmo do RETRY — um `retry_interval_seconds` maior que a tolerancia marcaria o container `unhealthy` exatamente no cenario que o retry do v2.0.6 existe para sobreviver (e `restart: always` nao reinicia container unhealthy). Agora e `max(600s, 3 × check_interval, 3 × retry_interval)`, e a mensagem de falha cita os dois intervalos.
- `app/healthcheck.py`: valor nao numerico de intervalo estourava o calculo (`"300" * 3` em `max()`). Nova coercao `_as_int()` com fallback seguro; `check_interval` continua aceitando `0` (modo webhook), `retry_interval` nao.
- READMEs (pt-BR e en-US): o exemplo de config e a tabela de secoes documentavam `qbit.host` + `qbit.port`, enquanto o codigo le `qbit.url` desde a unificacao de URL. Como `load_config()` NAO faz merge com os defaults quando o arquivo existe, quem seguisse o README montava um `config.json` que estourava `KeyError` em `get_qbit_session()`. Corrigido tambem no troubleshooting e na secao "nao uso Sonarr/Radarr".
- `config.json` versionado nao trazia `retry_interval_seconds`, divergindo do default de `load_config()` — quem lia o arquivo para saber o que existe nao via a chave nova. Adicionada aqui e no `dev-config.json`.

### Adicionado
- Docs: nova secao "Reconexao ao qBittorrent" nos dois READMEs, com o comportamento do retry, a razao de o container seguir `healthy` durante a indisponibilidade e a relacao com a tolerancia do healthcheck. `retry_interval_seconds` entrou no exemplo de config e na tabela de secoes.
- Testes — 109 → 174 (154 funcionais + 20 de seguranca). Cobertura de `app/guardian.py`: 75% → 89%.
  - `TestArrMatchByName` (12): regressao dos dois bugs de match, normalizacao de separadores, limite de palavra, `title_field` customizado.
  - `TestHandleArrRadarr` / `TestHandleArrSonarr` / `TestBlockAndSearch` (16): a maior funcao do projeto (`_handle_arr`, 115 linhas) estava sem teste comportamental — so `verify=False` e headers. Agora cobre blocklist (`DELETE` com `blocklist=true` / `removeFromClient=false`), `movieId` vs `seriesId`, extracao de `episodeId`/`episodes`, fallback por nome, validacao de `airDateUtc` (episodio futuro e excluido do re-search), `EpisodeSearch` vs `SeriesSearch` e secao desconfigurada. O helper falha o teste se `log.error` for emitido: o `except Exception` generico de `_handle_arr` transformava qualquer erro em log silencioso.
  - `TestWebUIPriorityScale` / `TestWebUIi18n` (17): nenhum teste tocava em `static/` antes. Travam a escala oferecida pela UI contra `VALID_FILE_PRIORITIES`, o alinhamento do default do select com o `config.json`, a ausencia do rotulo "(0–7)" e a paridade de chaves i18n entre pt-BR e en-US.
  - `TestDocsConfigParity` (6): o exemplo `json` de cada README precisa ter exatamente as chaves do `config.json` e ser aceito por `load_config()` — e a classe de drift que passou despercebida na unificacao de URL.
  - `TestConfigAutoCreation.test_config_json_do_repo_bate_com_o_default`: impede o `config.json` versionado de divergir do default de `load_config()`.
  - `TestHealthcheck`: 5 casos novos para a interacao com o retry e para intervalos invalidos.
  - `test/conftest.py`: fixture `autouse` zerando `_processed`, `_check_count` e a sessao HTTP em cache entre testes. Eram globais de modulo limpos na mao, teste a teste — a suite agora passa tambem em ordem inversa.
- `requirements-dev.txt`: dependencias de teste separadas do runtime.

### Alterado
- Reforco dos testes de retry do v2.0.6, que tinham dois furos (confirmados por mutacao): nada amarrava `_retry_interval()` ao `time.sleep()` do retry (um valor fixo passaria a suite) e nada distinguia "reconecta retentando ate conectar" de "tenta uma vez e segue" no loop principal.
- `pytest` saiu do `requirements.txt` para o `requirements-dev.txt` — nao vai mais para a imagem Docker, que instala apenas o runtime.
- CI: `docker-build.yml` agora depende de `test.yml` (via `workflow_call`). Antes os dois workflows corriam em paralelo e independentes no push para `main`, entao teste quebrado nao impedia a publicacao da imagem no GHCR.
- Web UI: o marcador de traducao de `<option>` passou de `data-i18n-unit`/`data-i18n-units` (so unidades de tempo) para `data-i18n-option`, generico, agora usado tambem pela escala de prioridade.

## [2.0.6] — 2026-09-25

### Corrigido
- Bug: o guardian morria no startup quando o qBittorrent ainda nao estava disponivel (ex.: apos reboot do servidor, quando o qbit-guardian sobe antes do qBittorrent). `guardian_loop()` fazia `return` na primeira falha de `qbit_login()` (tipicamente `SSLError(UNEXPECTED_EOF_WHILE_READING)`), encerrando a thread definitivamente. Consequencia em cadeia: o heartbeat (`/tmp/heartbeat`) parava de ser atualizado e, passada a tolerancia do healthcheck (`max(600s, 3x intervalo)`), o container era marcado `unhealthy`; como `restart: always` nao reinicia container unhealthy (so em crash), o guardian ficava morto ate intervencao manual.
  - `guardian_loop()` agora chama `_connect_with_retry()`, que retenta `qbit_login()` a cada `retry_interval_seconds` ate sucesso, escrevendo `write_heartbeat()` a cada tentativa (o healthcheck mede a saude do PROCESSO guardian, nao do qBit);
  - Loop principal ampliado: `except TRANSPORT_ERRORS` captura a familia de erros de transporte (`ConnectionError`, `SSLError`, `Timeout`, `ReadTimeout`) — antes so `ConnectionError` era capturado, e `SSLError`/`Timeout` escapavam para o `except Exception` generico (apenas logava, sem reconectar).

### Adicionado
- Nova chave `guardian.retry_interval_seconds` (default 120s) — intervalo entre tentativas de reconexao ao qBit, independente de `check_interval_seconds`. Fallback seguro para valores ausentes/invalidos (<= 0, nao numerico).
- Testes: `TestGuardianRetry` (retry no startup, heartbeat vivo durante retry prolongado, reconexao nos 4 erros de transporte, fallback do retry_interval).

## [2.0.5] — 2026-09-19

### Corrigido
- Bug: prioridade de arquivo **invalida** falhava em silencio. O qBittorrent aceita apenas `-1`, `0`, `1`, `6` e `7` em `/api/v2/torrents/filePrio` — qualquer outro valor devolve HTTP 400 `A prioridade nao e valida`. Como `set_file_priority()` nao conferia o retorno do POST, a priorizacao simplesmente nao acontecia e nada era registrado em log. Descoberto em producao: a config tinha `priority_normal: 4` (valor inexistente na escala), entao os arquivos auxiliares (`.nfo`, `.srt`, `.jpg`) eram rejeitados em rajada a cada ciclo — 8 HTTP 400 por varredura, invisiveis sem LOG_LEVEL=DEBUG.
  - `set_file_priority()` valida contra `VALID_FILE_PRIORITIES` antes de enviar e emite `log.warning` (valor invalido ou HTTP != 200), em vez de silenciar;
  - Config do servidor ajustada: `priority_normal` 4 -> 1 (o default do codigo);
  - Testes: `TestSetFilePriority` (5 valores validos, 6 invalidos, erro da API).

## [2.0.4] — 2026-09-19

### Corrigido
- Bug: torrents vistos **sem metadados** (`metaDL`/`queuedDL` — magnet ainda resolvendo) eram marcados como processados mesmo com a analise incompleta. `analyze_torrent()` retornava cedo no caso "sem metadados" sem validar nada, mas `guardian_loop()` e `api_trigger()` adicionavam o hash em `_processed` de forma incondicional — e o torrent **nunca mais** era reavaliado. Quando os metadados chegavam (trazendo `.exe`/`.scr` ou nenhum arquivo de midia valida), nada acontecia: o torrent ficava no cliente indefinidamente. Como `_processed` vive em memoria, so um restart do container reprocessava o backlog — o que produzia a rajada de remocoes que o usuario observava ("do nada disparou varias mensagens"). O 2.0.1 corrigiu o caso analogo para stalled/no-seeds; este fix cobre a validacao de **arquivos**.
  - `analyze_torrent()` agora retorna `True` (analise concluida) ou `False` (sem metadados, reavaliar depois);
  - `guardian_loop()` e `api_trigger()` so marcam o hash como processado quando a analise retorna `True`;
  - Teste de regressao: `test_trigger_reprocessa_torrent_sem_metadados`.

### Alterado
- Healthcheck agora detecta loop travado. O anterior (`cat /tmp/heartbeat`) apenas verificava a **existencia** do arquivo — como o heartbeat nunca e apagado, um guardian travado permanecia reportando `healthy` indefinidamente (o que mascarava justamente este tipo de bug). Substituido por `app/healthcheck.py`, que compara a **idade** do heartbeat com `guardian.check_interval_seconds`: falha quando o atraso passa de `max(600s, 3x intervalo)`. Modo webhook (intervalo = 0) sempre passa, pois nao ha loop periodico.
  - Dockerfile e os dois composes atualizados para `["CMD", "python", "app/healthcheck.py"]` (timeout 10s, start_period 30s);
  - Testes: `TestHealthcheck` (heartbeat recente, atrasado, ausente, intervalo longo e modo webhook).

## [2.0.3] — 2026-06-23

### Corrigido
- Bug: torrents presos em `state=metaDL` (baixando metadados) nunca eram removidos. `is_stalled()` só verificava `stalledDL` e `stalledUP`. Corrigido adicionando `metaDL` à tupla de estados stalled e incluindo o estado no log (`stalled (metaDL) por >5h`). (#b734e32)

## [2.0.2] — 2026-06-23

### Corrigido
- Bug: `check_stalled_and_remove()` removia o torrent do qBittorrent mas não chamava `block_and_search()` — ou seja, não bloqueava no Radarr/Sonarr nem iniciava nova pesquisa. Corrigido adicionando `block_and_search()` antes de `remove_torrent()`, igual ao fluxo de torrents maliciosos. (#ee9878a)

## [2.0.1] — 2026-06-23

### Corrigido
- Bug: guardian nao reavaliava stalled/sem seeds em torrents ja processados em ciclos anteriores. O set global `_processed` impedia que torrents fossem reavaliados apos a primeira analise, fazendo com que torrents que ficassem stalled depois nunca fossem detectados nem removidos. Corrigido com funcao `check_stalled_and_remove()` extraida de `analyze_torrent()` e segunda passada no loop principal (`guardian_loop`) e endpoint `/api/trigger` (`api_trigger`) que reavalia TODOS os torrents a cada ciclo. (#898e822)

## [2.0.0] — 2026-06-07

### Adicionado
- Web UI em Flask (`web.py`) para configuracao visual — acesse `http://host:5000`
- Frontend single-page (`static/index.html`) com fetch API, sem frameworks JS
- Favicon shield (escudo) em `static/favicon.svg` — icone da aba do navegador, tema dark
- Persistencia de configuracao em `config.json` (substitui env vars)
- Thread-safety com `threading.Lock` no acesso ao arquivo de config
- Modo webhook: `check_interval_seconds = 0` + script `qbit-guardian-hook.sh`
- Endpoint `POST /api/trigger` — processamento sob demanda
- Endpoint `GET /api/health` — healthcheck para Docker
- Heartbeat em `/tmp/heartbeat` para healthcheck externo
- Otimizacao de prioridades de arquivos (midia=7, auxiliares=1, outros=0)
- Remocao por stalled e no-seeds com tempo configuravel
- Integracao com Sonarr: validacao de data de lancamento antes de re-search
- Integracao com Radarr: blocklist + re-search
- Notificacoes via Apprise (Telegram, Discord, etc)
- `CONTEXT.md` com glossario de dominio (15 termos)
- Suite de testes: 12 de seguranca + 25 funcionais (37 total)
- Notas de conceito no vault Obsidian (thread-safe-config, Apprise, qBit API)
- `README.md` com instrucoes Docker, manual, API REST e desenvolvimento
- `CHANGELOG.md` (este arquivo)
- Workflow GitHub Actions `docker-build.yml` — build multi-arch (amd64/arm64) e push para GHCR

### Modificado
- Layout refeito como duas colunas seguindo protótipo Penpot: serviços externos (qBittorrent, Sonarr, Radarr, notificações) à esquerda, Guardian à direita
- Layout da Web UI refinado: container ampliado (+15% width, max-width: 1035px); gap entre colunas de 30px; coluna do Guardian estica verticalmente para mesma altura da coluna de serviços via flexbox aninhado (`align-items: stretch` + `.col + .col > .card { flex: 1 }`); título centralizado; botão "Salvar Configurações" centralizado. (#0f528c9)
- Arquitetura: monolito (`guardian.py` 327 linhas) → modulos (`app.py` + `guardian.py` + `web.py` 507 linhas)
- Configuracao: env vars → JSON editavel via Web UI
- Guardian loop: processo unico → thread daemon com Flask na main thread
- Extensoes: sets hardcoded → customizaveis via Web UI
- Docker: `docker-compose.yaml` generico (sem rede fixa), `python:3.12-slim`
- Licenca: adicionada GPL v3 explicita

### Corrigido
- Erro de SSL ao conectar com Apprise usando certificado auto-assinado (comum em homelabs com dominios `.home.arpa` ou `.local`). A verificacao SSL foi removida: `requests.post(verify=False)` usado diretamente, sem config `verify_ssl` e sem fallback. Warnings do urllib3 sao suprimidos. (#66e1e4f)

### Removido
- Dependencia de env vars para credenciais (`.env/.env` depreciado)
- Sets hardcoded de extensoes (`VALID_MEDIA`, `DANGEROUS`)

## [1.0.0] — ~2025

### Versao inicial
- Script monolito Python (`guardian.py`, 327 linhas)
- Loop `while True` com polling a cada N segundos
- Deteccao de extensoes perigosas (.exe, .scr, .bat, etc.)
- Integracao basica com Sonarr e Radarr (blocklist + re-search)
- Notificacoes via Apprise
- Configuracao exclusivamente por variaveis de ambiente
- Dockerfile com `python:3.12-slim`
