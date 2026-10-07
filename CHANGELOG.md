# Changelog

Todas as mudancas notaveis deste projeto serao documentadas neste arquivo.

O formato e baseado no [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
e o projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
