# Changelog

Todas as mudancas notaveis deste projeto serao documentadas neste arquivo.

O formato e baseado no [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
e o projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.10.0] — 2026-10-12

Passeio guiado pela interface, em pt-BR e en-US, rodando em cima das telas de verdade.

### Adicionado
- **Tour guiado de 24 passos**, da tela de login ate a configuracao completa — **todo campo da tela tem o seu**. Cada passo destaca um campo com um recorte de luz, explica o que vai nele e, ao avancar, **preenche o campo com um exemplo** antes de pular para o proximo — a tela vai sendo configurada na frente de quem assiste, que e o que uma lista de instrucoes em texto nao faz. Abre em outra aba pelo icone **Tour** no painel, ou pelo link *Primeira vez? Veja o passeio guiado* na tela de login.
- **Rota `/demo`**: a home de configuracao em modo demonstracao, publica e inerte. E o mesmo `index.html` do painel — nao ha copia da interface para envelhecer — servido num caminho em que o `tour.js` troca o `window.fetch` por um stub: nenhuma requisicao de escrita sai do navegador e nenhuma leitura chega ao config real. Uma faixa no topo avisa disso o tempo todo, e o botao de conta sai da topbar porque em demonstracao ninguem tem conta.
- **Rota `/api/demo-config`**, tambem publica: os valores de uma instalacao nova, montados na memoria por `guardian.config_default()`. Nao le o `config.json` — nao tem como vazar URL, API Key ou credencial, e ha teste que grava segredos reconheciveis no disco e exige que nenhum deles apareca na resposta.
- **O campo Apprise URL avisa na hora quando o valor nao e postavel.** Quem colar uma URL de servico (`tgram://`, `discord://`) ve o campo ficar vermelho enquanto digita, com a dica explicando o formato certo. Sem isso o erro era invisivel: a notificacao morre dentro do guardian com `InvalidSchema` e so aparece no log do container. Nao bloqueia o salvamento — o campo e opcional e um rascunho pode ser guardado; o que ele nao pode e parecer certo. Campo vazio continua valido (notificacoes desligadas), e o estado vai tambem em `aria-invalid`, para quem nao enxerga a borda.
- `guardian.config_default()` — o default que vivia dentro do `load_config()` virou funcao. A rota de demonstracao precisa da mesma estrutura sem tocar o disco, e uma segunda copia sairia de sincronia no primeiro campo novo.

### Corrigido
- **Trocar o modo de operacao pela Web UI nao funcionava — nos dois sentidos.** O Polling decide o modo (acima de 0, polling; em 0, webhook), mas a troca so valia com restart do container, e um dos caminhos deixava o guardian **sem verificacao nenhuma**:
  - `polling -> webhook`: o laco de polling via o 0, logava "entrando em modo webhook" e dava `return` **sem subir a reavaliacao**. Nao sobrava laco: so o `/api/trigger`, que nem existe se o webhook nao estiver configurado no qBittorrent. Quem trocasse de modo pela tela ficava com o guardian parado sem saber.
  - `webhook -> polling`: quem detectaria a volta era o laco de polling, que ja tinha terminado no start. Nunca religava.
  Agora os dois lacos passam o bastao um para o outro, e `POST /api/config` religa na hora — inclusive no caso em que nao ha laco nenhum vivo para perceber (`reevaluate_interval_seconds = 0`). Uma guarda de modo impede que duas threads percebendo a mesma troca subam dois lacos e o ciclo passe a rodar em dobro contra o mesmo qBittorrent.
- **`check_interval_seconds` agora e normalizado como o resto.** `"0"` entre aspas — de um config editado a mao — era modo webhook para o `healthcheck` (que ja usava `_as_int`) e modo polling para o laco, que comparava `"0" == 0`. A nova `_check_interval()` e simetrica a `_reevaluate_interval()` e os dois passaram a concordar.
- **O placeholder do campo Apprise URL ensinava um valor que nunca poderia funcionar.** Ele mostrava `tgram://BOT_TOKEN/CHAT_ID` — formato de URL *de servico* do Apprise. Mas o guardian nao executa o Apprise: `send_notification()` faz `requests.post(url, ...)` para um **servidor Apprise hospedado pelo usuario**, e o `requests` nao tem adapter para `tgram://`. Quem copiasse o placeholder montava uma configuracao que levantava `InvalidSchema` antes de um byte sair do processo, caia no `except` e virava uma linha de log — notificacao nenhuma, sem pista do motivo. O placeholder agora e `http://192.168.1.100:8000/notify/guardian`, no mesmo padrao dos outros campos da tela.
- **A documentacao repetia o erro.** A tabela de *Notificacoes* em `USAGE.md` listava `tgram://`, `discord://` e `pover://` como opcoes do campo, com o endpoint proprio como uma quarta linha — quando so essa ultima funciona. As duas versoes ganharam uma secao explicando que o campo quer o **endpoint HTTP do servidor**, e que as URLs de servico vao na configuracao *daquele servidor*, com o erro exato que aparece no log de quem errar. O comentario em `guardian.py` que descrevia a `apprise_url` como "embute o token do bot (tgram://TOKEN/chat)" foi corrigido pelo mesmo motivo.

### Mudado
- **Placeholders de endereco mais intuitivos.** Os campos de URL (qBittorrent, Radarr, Sonarr, Apprise) passaram a usar `192.168.1.100`, a faixa domestica mais comum — e a mesma que a documentacao ja usava nos exemplos. Deixa claro que ali vai o endereco da rede de quem instala, e nao um endereco a copiar. Os passos do tour que preenchem esses campos acompanham, e ha teste que amarra os dois ao mesmo valor.
- **`/login?tour=1` nao redireciona mais para o painel.** O link do tour nasce dentro do painel, com o usuario ja logado: sem a excecao ele cairia de volta na home sem nunca ver o primeiro passo. Sem o parametro, o atalho continua igual.
- `ARQUIVOS_PUBLICOS` ganhou **`tour.js`**. Quem mais precisa do passeio e justamente quem ainda nao logou — nao sabe que a senha inicial esta no `docker logs`. O arquivo nao le configuracao: so roteiro, estilo e os textos vem do `i18n.js`, que ja era publico.

### Notas
- **Um link, dois idiomas.** O texto de cada passo e chave do `i18n.js`, entao o passeio abre no idioma que estiver selecionado e **troca junto** se o seletor mudar no meio dele — o balao e redesenhado, porque o walker do i18n so alcanca quem tem `data-i18n`. Nao ha URL por idioma nem roteiro duplicado.
- **Por que nao um prototipo navegavel a parte:** ele seria uma foto da interface, precisaria de uma versao por idioma e envelheceria a cada mudanca de layout — a 2.9.0 reescreveu a grade inteira. Rodando sobre a tela real, o passeio acompanha sozinho, e o passo que explica o tooltip de variaveis mostra um **hover de verdade**, que e justamente o que um prototipo nao consegue encenar.
- **O recorte de luz abraca o tooltip do alvo**, nao so o alvo: o `{ }` e pequeno e a lista de variaveis cresce para fora dele, entao o balao escolhia um lado que passava por cima do que o passo mandava olhar. A conta usa a area do tooltip, e nao o `visibility` computado — ele abre por transicao de 150ms e ainda esta escondido no instante do calculo.
- **O balao procura o lado antes de procurar embaixo.** Embaixo ele cobre o proprio formulario que esta explicando; na tela de login chegava a esconder o campo do passo seguinte.
- **O campo `Reavaliar fila` desliga sozinho quando o Polling esta acima de 0.** Ele so vale no modo webhook: com `check_interval_seconds > 0`, `_start_reevaluate_loop()` nunca e chamado e o valor nao tem efeito nenhum. Os dois ficavam lado a lado, editaveis, sem nada dizendo que um anula o outro. Agora o campo aparece esmaecido e bloqueado, com a dica explicando o motivo, e **o valor nao e apagado** — volta a valer assim que o Polling voltar para 0. O passo do tour explica a mesma regra em palavras.
- O contador e do passeio inteiro (`4 de 24`), nao da fase: contado por tela, o login fechava como se fosse o fim e a configuracao recomecava do 1.
- Enquanto o tour roda, ele e dono dos cliques — no alvo avanca, em qualquer outro lugar nada acontece. O seletor de idioma e a unica excecao. `Esc` sai, `Enter` avanca sem submeter o formulario de login.
- Validado no navegador nos dois idiomas, a 1400px e a 500px: nenhum balao sai da viewport, nenhum POST chega ao servidor em `/demo` (conferido no log de acesso e no `config.json`, que fica intacto) e o console nao registra erro.
- Nada mudou no motor: `guardian.py` so ganhou a extracao do default. As chaves do `config.json` sao as mesmas — quem atualizar nao precisa mexer em configuracao.
- Testes: 870 -> **945**. Travam que todo alvo de passo existe na tela da fase, que todo passo tem texto nos dois idiomas, que nenhuma chave do tour fica orfa, que o roteiro nao carrega texto literal, que `tour.js` carrega antes do script do painel, que a rota de demonstracao nao conhece o config real, que a lista de arquivos publicos nao cresce sem querer que o placeholder do Apprise continua sendo um endereco postavel pelo `requests`, que a troca de modo funciona nos dois sentidos (e pelas tres portas: laco de polling, laco de reavaliacao e POST da Web UI) que duas threads na mesma troca sobem um laco so, que todo endereco de exemplo fica na faixa generica e que o campo Apprise recusa visualmente o que o `requests` nao postaria.

## [2.9.0] — 2026-10-11

Retrabalho da home: grade assimetrica, card central em duas colunas e a ajuda inline movida para a documentacao.

### Mudado
- **A grade de tres colunas deixou de ser simetrica.** Era 365 / 365 / 365; agora e **274 / 548 / 320** — nenhuma coluna igual a outra, e cada uma por um motivo: a esquerda tem campos de uma linha, a central abriga duas colunas internas, e a direita tem caixas de texto que se edita de verdade. A largura de conteudo foi de 1151 para **1198px**. A proporcao e declarada em `fr` (`274fr 548fr 320fr`) e nao em largura fixa, para encolher junto em vez de estourar a viewport; os numeros repetem os tokens porque `<flex>` nao aceita `calc()`, e ha teste de paridade entre os dois.
- **O card do Guardian virou duas colunas internas.** Ele tinha onze campos empilhados. Como a grade estica as tres colunas juntas, a altura dele virava a altura das outras duas, e os cards de qBittorrent/Radarr/Sonarr e o de Notificacoes — que tem pouca coisa — ficavam com vazio acumulado no rodape. Dividido, o card perdeu **cerca de 40% da altura** e as outras colunas encolheram junto. Os campos preenchem linha a linha: Polling | Reavaliar fila, Reconexao | Prioridade midia, e assim por diante.
- **Rotulos curtos.** `Intervalo de verificacao (segundos, 0 = modo webhook)` virou **Polling**; `Reavaliacao da fila (segundos)` virou **Reavaliar fila**; `Retentativa de conexao (segundos)` virou **Reconexao**; `Prioridade para arquivos de midia (0, 1, 6 ou 7)` virou **Prioridade midia**. Os tres rotulos de remocao perderam o `Remover torrents`, que subiu uma vez so para o cabecalho do grupo.
- **A unidade saiu do rotulo e foi para o lado da caixa** (`300` `s`). Tirar o `(segundos)` sem isso levaria embora uma informacao que nao e ajuda: e parte do campo.
- **As caixas de Polling, Reavaliar fila e Reconexao ocupam a coluna** (223px), sobrando so o espaco da unidade. Elas chegaram a ter 88px fixos, o que deixava um vazio de 150px dentro da propria coluna.
- Rotulos do card de Notificacoes encurtados para caber em uma linha na coluna estreita: **Otimizado**, **Removido (perigoso)**, **Removido (parado)**. A palavra "Mensagem" era redundante com a caixa de texto logo abaixo.
- **Os controles de velocidade minima sao centralizados**; o rotulo e o liga/desliga seguem nas bordas do bloco, que e onde marcam onde ele comeca e termina. A frase atravessa as duas colunas e e curta demais para encher a largura — alinhada a esquerda, ficava pendurada com um vazio de ~130px a direita.
- `--col` deu lugar a `--col-side`, `--col-main` e `--col-notif`; a largura de formulario curto (modal de conta e tela de login) virou **`--col-form`**, mesmo token nos dois lugares.

### Removido
- **Os textos de ajuda embaixo dos campos.** Eram cinco, um deles com tres linhas, e disputavam atencao com os proprios controles. Tudo o que eles diziam esta agora em `docs/*/USAGE.md`, numa **referencia de campos** que o painel nao tinha: cada campo, o que faz, e a chave correspondente no `config.json` — a ligacao entre rotulo da tela e chave do arquivo nao estava documentada em lugar nenhum.
- A unica ajuda que sobrou na tela e a do modal de conta, que e regra do formulario (a senha atual e sempre obrigatoria) e nao explicacao de para que serve o campo.

### Adicionado
- **Tooltip de variaveis nas caixas de mensagem.** A lista de `{{variaveis}}` ocupava uma linha fixa sob cada caixa; agora abre num `{ }` ao lado do rotulo, em hover ou com o teclado. E a unica ajuda que ficou na tela, de proposito: quem ajusta o texto de uma mensagem precisa dos nomes na mao e nao vai abrir a documentacao so para reordenar duas linhas. O icone e `{ }` e nao `?` porque nomeia o que entrega e ja mostra o formato do que vai na caixa.
- `prefers-reduced-motion` respeitado — a UI tem transicao em switch e em tooltip e nao oferecia saida.

### Notas
- **Acessibilidade do tooltip:** `aria-describedby` alem do `aria-label`. So com o rotulo, um leitor de tela anuncia "Variaveis que esta mensagem aceita, botao" e para — as variaveis nunca chegam a quem nao ve a tela. O `{ }` leva `aria-hidden` para nao ser lido duas vezes.
- **O fundo do tooltip e `--bg`, nao `--card`:** ele abre *sobre* o card, e a cor do card nao separaria um do outro.
- **O titulo dos cards da coluna 1 voltou a alinhar com os vizinhos.** O `space-evenly` que distribuia a sobra punha ar *acima* do `<h2>` tambem, e o titulo descia alguns pixels. `space-between` mantem o titulo no topo e reparte a sobra entre os campos.
- **O breakpoint acompanhou a largura do conteudo.** Com a grade em 1198px (1238 com o padding do body) e o breakpoint parado em 1199, existiria uma faixa de 1200 a 1238 em que a grade continuaria em tres colunas sem caber — e a pagina ganharia rolagem horizontal. Passou para 1245px, e ha teste que amarra um ao outro.
- Validado no navegador em pt-BR e en-US, a 1920px, a 1210px e empilhado: nenhum rotulo quebra em tres linhas, nenhum controle estoura a borda do card, nenhuma rolagem horizontal, e as tres colunas medem **274 / 548 / 320** terminando na mesma altura.
- Nada mudou no motor: `guardian.py` nao foi tocado. As chaves do `config.json` sao as mesmas — quem atualizar nao precisa mexer em configuracao.
- Testes: 815 -> **870**. Travam a proporcao da grade, a ordem dos campos nas duas colunas, a presenca da unidade ao lado das caixas de tempo, a ausencia de ajuda inline no card central, o tooltip (escondido por padrao, abre em hover e em foco, contrasta com o card, tem nome acessivel) e a exigencia de que a documentacao cubra cada campo que perdeu a explicacao na tela.

## [2.8.2] — 2026-10-11

Espera na fila deixa de contar como inatividade do torrent.

### Corrigido
- **Falso positivo na remocao por stalled, especialmente em `metaDL`.** Com `max_active_downloads` baixo, um torrent passa horas em `queuedDL` — estado que nenhuma regra avalia. No instante em que finalmente entra em `metaDL`, o `tempo_parado` ja acumulou **toda** a espera da fila, porque para quem nunca transferiu nada o calculo cai em `added_on`. Resultado: removido na hora, sem ter tido um segundo de chance real de buscar metadados. Medido em producao: **36 de 37** enfileirados com `time_active == 0` e **290 min** de idade. Mesmo defeito conceitual que a v2.7.0 corrigiu para `queuedDL` no criterio de sem-seeds, entrando por outra porta.
- Agora ha um **piso de `time_active`**: nao basta estar parado ha X, o torrent precisa ter tido X de tempo **ativo**. Vale para o criterio de stalled e para o de sem-seeds.

### Notas
- `time_active` e o contador do proprio qBittorrent — zero enquanto o torrent espera em `queuedDL`, crescendo so quando ele tem slot. Ja vem em `/torrents/info`, entao nao custa chamada extra.
- **Por que `time_active` e nao os limites da fila**, que era a sugestao inicial: ele e **por torrent** em vez de global (mesmo com a fila folgada, um torrent recem-ativado nao deve ser julgado), mede o que de fato aconteceu em vez de inferir de um limite saturado, e dispensa consultar `/app/preferences`. A intuicao de que a fila era a causa estava certa; o dado certo e outro.
- **Campo ausente nao e zero**: `tempo_ativo()` devolve `None` quando `time_active` nao veio, e nesse caso o piso nao se aplica. Em producao o qBittorrent sempre envia; a distincao existe para que teste focado em outro criterio nao precise declarar o campo.
- Testes: 810 -> **815**. Cobrem o `metaDL` recem-ativado sendo poupado, o `metaDL` com tempo ativo suficiente ainda sendo removido (o piso nao pode virar imunidade), o piso no criterio de sem-seeds, a distincao entre ausente e zero, e a preservacao do comportamento anterior quando o campo nao vem.

## [2.8.1] — 2026-10-11

O blocklist no Radarr/Sonarr nao acontecia quando a fila passava de 10 itens.

### Corrigido
- **A queue do Arr era pedida sem `pageSize`, e a API devolve 10 itens por default.** Com a fila maior que isso, o torrent a bloquear ficava fora da primeira pagina, o `downloadId` nunca casava e o blocklist simplesmente nao acontecia. **A falha era silenciosa**: "nao achei na queue" cai no fallback por nome e depois desiste sem erro nenhum. Medido em producao ao validar a v2.8.0 — `totalRecords=43`, `records` retornados **10**, e o release removido por lentidao nao entrou no blocklist. Afeta **todas** as remocoes (stalled, sem-seeds e lentidao), nao so a feature nova; e um defeito que existia desde que o `_handle_arr` foi escrito.
- Agora a queue e pedida com `pageSize=ARR_QUEUE_PAGE_SIZE` (1000), e um **aviso** sai no log quando `totalRecords` ainda excede o que a pagina trouxe — falha silenciosa e pior que falha barulhenta.

### Notas
- Limite conhecido que ficou de fora: o **fallback por nome** compara o nome do release com o titulo no Arr, e nao casa quando os dois estao em idiomas diferentes. No caso medido, o release era `Ballerina 2025 1080p...` e o titulo no Radarr, `Bailarina: Do Universo de John Wick`. Com a paginacao corrigida o caminho da queue resolve, e o fallback deixa de ser exercitado nesse cenario — mas segue frágil para torrent que o Arr nao rastreia mais.
- Testes: 805 -> **810**. Cobrem o `pageSize` explicito na chamada, o alvo na posicao 40 de 43 sendo encontrado, o aviso de truncamento, e a ausencia de aviso quando a pagina cobre tudo.

## [2.8.0] — 2026-10-11

Velocidade minima de download: torrent que fica lento por tempo demais sai da fila.

### Adicionado
- **Remocao por velocidade sustentada abaixo de um minimo.** Cinco chaves novas: `remove_slow`, `slow_speed`, `slow_speed_unit` (`KiB`/`MiB`/`GiB`/`TiB`), `slow_time` e `slow_unit`. O caso que motivou: um torrent de 2,5 GiB baixando a **2,2 KiB/s** com ETA de **6 dias**, ocupando um slot da fila indefinidamente — um filme nessa taxa nunca termina, e com `MaxActiveDownloads` baixo ele trava o que vem atras. Como as outras remocoes, passa por `block_and_search`: o release e marcado como falho no Radarr/Sonarr, que buscam outro.
- **`reevaluate_interval_seconds` e `retry_interval_seconds` expostos na Web UI.** Existiam desde a v2.7.0 e a v2.0.6 respectivamente, mas so no `config.json` — e ate a v2.7.2 editar o arquivo nao surtia efeito sem restart. O primeiro deixou de ser conveniencia e passou a ser **requisito** da velocidade minima: ele e a granularidade de todos os limites de tempo, e um limite menor que o intervalo nunca e atingido antes do ciclo seguinte. O rotulo na UI diz isso.

### Notas
- **A velocidade julgada e a media na janela**, nao o `dlspeed` instantaneo: `(baixado_agora - baixado_no_inicio) / tempo_decorrido`, medida desde o instante em que o torrent ficou lento. O `dlspeed` oscila demais para decidir remocao — um download de 2 KiB/s tem picos momentaneos acima de qualquer limite razoavel. Se o torrent recupera no meio, a media sobe, a janela e descartada e ele escapa.
- **Avalia somente `state == "downloading"`.** `queuedDL` ficou fora de proposito: torrent na fila tem 0 B/s por definicao, e incluir esse estado repetiria o defeito que qualificou 51 de 54 torrents enfileirados para remocao na v2.7.0. Ha teste de regressao fixando isso, e outro cobrindo `stalledDL`, `metaDL`, `uploading`, `stoppedUP` e `checkingDL`. `stalledDL` tambem fica fora por ja ser coberto por `remove_stalled`.
- **Unidades em base 1024 com rotulos KiB/MiB/GiB/TiB**, que e exatamente como o qBittorrent exibe velocidade na propria interface: o numero digitado aqui e comparavel ao que se le na lista de torrents, sem conversao mental. O campo `dlspeed` da API ja vem em bytes/s. Unidade desconhecida na config cai em KiB em vez de virar limite absurdo, e valor nao numerico desliga a regra em vez de estourar.
- A remocao reaproveita o evento de notificacao `stalled`, cujo template ja expoe `{{reason}}` — a mensagem informa a media medida, a janela e o minimo configurado (ex.: `2.17 KiB/s de media por >15m (minimo 100 KiB/s)`). Nao foi criado evento novo para nao mexer na superficie de notificacoes.
- `_lento_desde` (o estado das janelas) entra no `_prune_processed`: torrent removido ou concluido nao tem janela a manter, e sem isso o dict cresceria indefinidamente.
- Testes: 790 -> **805**.

### Adicionado (infraestrutura de teste, vinha de `[Nao lancado]`)
- **`pytest-timeout` com teto de 45 s por teste** (`pytest.ini`, `requirements-dev.txt`). O codigo tem `while True` (`guardian_loop`, `_reevaluate_loop`) e a suite os chama: um teste cuja condicao de parada falhe entra em espera, cai no `except Exception` do ciclo e volta ao laco, ficando **pendurado** em vez de falhar. Ja aconteceu — trocar `get_config` por `load_config` nos loops deixou o `_LoopHarness` sem efeito e levou a suite de 29 s para travada. A suite inteira roda em ~29 s e nenhum teste passa de 1 s, entao 45 s nao incomoda teste legitimo. Validado com um teste descartavel que dorme 50 s: `Failed: Timeout (>45.0s) from pytest-timeout` em 45,01 s.
- Testes de paridade da propria rede de seguranca: `pytest.ini` precisa declarar `timeout` dentro de uma faixa util, o plugin precisa estar em `requirements-dev.txt`, e **nao** pode estar em `requirements.txt` (dependencia de teste nao engorda a imagem do RPi).

### Corrigido
- **Vazamento de threads na suite, introduzido na v2.7.0.** `guardian_loop` em modo webhook chama `_start_reevaluate_loop`, e cinco testes exercitam esse caminho — mas so um mockava a funcao. Os outros quatro deixavam para tras uma thread daemon parada em `Event.wait()`, que sobrevivia ao teste, podia acordar quando outro teste setava o Event e estourava ao encontrar o `CONFIG_PATH` do temporario ja removido. Aparecia como `PytestUnhandledThreadExceptionWarning` **intermitente** — flaky porque dependia da ordem de execucao. O `conftest` passa a neutralizar a criacao da thread por default; quem precisa verificar que o loop subiu faz seu proprio patch.
- Testes: 787 -> **790**. Tres rodadas consecutivas sem nenhum warning.

## [2.7.2] — 2026-10-11

Editar o `config.json` na mao passa a valer sem reiniciar o container.

### Corrigido
- **`get_config()` devolvia o cache e so tocava o disco com `_config is None`.** Consequencia: ajustar qualquer coisa no `config.json` fora da Web UI nao surtia efeito ate reiniciar o container — e o loop trazia o comentario *"Recarrega config a cada iteracao para detectar mudancas no intervalo"*, descrevendo uma recarga que nao acontecia. Mudanca pela Web UI funcionava porque `save_config` atualiza o cache, o que escondia o defeito. Agora o cache e invalidado por **`mtime`**: `stat` e ordens de grandeza mais barato que abrir e parsear o JSON, e isto e chamado uma vez por torrent em `analyze_torrent`/`is_stalled` — com o arquivo parado, o custo e uma syscall.

### Notas
- A correcao ficou dentro do `get_config()` de proposito, em vez de trocar as chamadas nos loops por `load_config()`. Trocar nos loops teria duas consequencias ruins: reler e parsear o JSON a cada ciclo mesmo sem mudanca, e **quebrar o `_LoopHarness` da suite**, que encerra `guardian_loop` interceptando `get_config` — com o loop consultando outra funcao, ele nunca sairia, e a suite passava de 29 s para travada. Invalidar por mtime corrige na raiz sem mexer em interface nenhuma.
- `load_config` e `save_config` passam a registrar o mtime; sem isso a propria gravacao pela Web UI deixaria o cache "velho" aos olhos do `get_config`, forcando uma releitura inutil em seguida.
- Falha de `stat` (arquivo removido ou ilegivel) nao interrompe o ciclo: segue com o que esta em memoria.

### Testes
- 784 -> **787**. Cobrem os dois lados do contrato: com o arquivo parado, `get_config()` **nao** dispara releitura (o caminho quente continua barato); com o arquivo alterado por fora, a mudanca e vista sem restart.
- **Dois testes do loop de reavaliacao foram blindados.** Eles chamavam `_reevaluate_loop()` — que tem `while True` — contando apenas com a leitura da config para sair. Se essa leitura falhasse, o loop entrava em `wait(300)`, estourava no ciclo com um mock nao-iteravel, caia no `except Exception` e **voltava ao laco**, girando indefinidamente com o pytest pendurado. Agora o `wait` e mockado para devolver `True`, o que serve de rede de seguranca e de assercao ao mesmo tempo: se o loop chegou a esperar, nao saiu pelo caminho previsto e o teste falha.
- Removidos tres testes redundantes que cobriam exatamente a mesma releitura de config.
- `conftest` passa a limpar o `Event` `_parar_reevaluate` entre testes: era global de modulo e vazava, podendo encerrar o loop do teste seguinte na primeira espera sem deixar rastro do motivo.

## [2.7.1] — 2026-10-11

A prioridade dos arquivos voltou a ser aplicada em torrent que entra na fila sem metadados.

### Corrigido
- **O ciclo periodico do modo webhook so reavaliava stalled, nunca a fila de pendentes.** A v2.7.0 trouxe o loop de volta, mas ele rodava apenas o pass 2. Resultado observado em producao: 47 torrents adicionados em lote entraram em `queuedDL` sem metadados, `analyze_torrent` recusou a analise (correto — nao havia arquivos para avaliar), e **ninguem voltava neles**: os `.mkv` ficaram em `priority=1` em vez do `priority_media=7` configurado, e o `.jpg` em 1 em vez do `priority_skip=0`. O qBittorrent **nao busca metadados de torrent enfileirado**, entao com `MaxActiveDownloads` baixo a janela entre "adicionado" e "tem metadados" pode ser de horas — e o unico gatilho era o webhook de *torrent adicionado*, que ja tinha passado.

### Alterado
- **Ciclo unico em `executar_ciclo()`**, usado pelos tres chamadores (loop completo, loop do modo webhook e `/api/trigger`). O pass 2 estava duplicado em tres lugares; agora ha uma implementacao so, e o loop do modo webhook executa o **ciclo completo** — drena a fila de pendentes e reavalia stalled.
- A "fila de pendentes" nao e estrutura nova: e o complemento de `_processed`, onde `analyze_torrent` deixa de fora quem recusou. O custo se ajusta ao que falta fazer — com pendentes, uma requisicao por torrent da fila; com a fila vazia, o pass 1 nao faz requisicao nenhuma e o ciclo custa apenas o `get_torrents()`. Nao ha modo a alternar.
- `/api/trigger` passa a devolver tambem **`sem_metadados`**: quantos seguem pendentes depois do ciclo.

### Notas
- O log do ciclo periodico fica em silencio quando nao houve nada a fazer. Com a fila vazia o loop roda a cada intervalo sem produzir trabalho, e logar isso seriam 288 linhas por dia sem informacao.
- Enquanto houver torrent enfileirado sem metadados, cada ciclo gasta uma requisicao por pendente (local, ao proprio qBittorrent). E o custo inerente de descobrir se os metadados chegaram.
- Testes: 781 -> **784**.

## [2.7.0] — 2026-10-11

Torrent na fila deixa de ser confundido com torrent sem seeders, e o modo webhook volta a reavaliar stalled sozinho.

### Corrigido
- **`queuedDL` saiu do criterio de remocao por "sem seeds".** Um torrent na fila nao conectou ao tracker, logo `num_complete == 0` nele significa "ainda nao perguntei", nao "nao existem seeders". Com `MaxActiveDownloads` baixo e a fila cheia, o guardian considerava sem-seeds todo download que ainda nao tinha tido a vez: em producao, **51 de 54** torrents enfileirados se qualificavam para remocao de uma vez. E como a remocao chama `block_and_search`, o Radarr marcaria falha e buscaria outro release — com `autoRedownloadFailed`, um ciclo.
- **O limiar de tempo media a IDADE do torrent, nao o tempo parado.** `added_on` no lugar de `last_activity` invertia a regra: um torrent baixado ha semanas que perdeu os seeders agora era removido de imediato, e um adicionado ha cinco minutos e parado desde o inicio nunca era. Novo helper `tempo_parado()` usa `last_activity` — o campo que o qBittorrent atualiza a cada chunk — com `added_on` como fallback.
- **Em modo webhook (`check_interval_seconds: 0`) nada era reavaliado.** O "pass 2", que reavalia stalled/sem-seeds de todos os torrents, vivia apenas dentro do loop (que o modo webhook nao executa) e no handler de `/api/trigger` — e o trigger e disparado pelo hook do qBittorrent ao **adicionar** torrent. Consequencia: sem torrent novo entrando, um torrent que ficava stalled nunca era reavaliado, independente do limiar configurado.

### Adicionado
- **`guardian.reevaluate_interval_seconds`** (padrao `300`, `0` desliga): ritmo do pass 2, agora separado do `check_interval_seconds`. O que o modo webhook evita e o ciclo **completo** — `analyze_torrent` faz uma chamada HTTP por torrent sem metadados, e com a fila cheia isso vira dezenas de requisicoes por ciclo. O pass 2 nao tem esse custo: uma chamada (`get_torrents`) e o resto e leitura de JSON. Em modo webhook o guardian sobe um loop proprio so para ele.

### Notas
- A espera do loop novo usa `Event.wait()` em vez de `time.sleep()`: fica interrompivel e nao se confunde com o sleep do retry de conexao, que a suite verifica isoladamente.
- Com `last_activity` **e** `added_on` zerados o torrent segue tratado como muito antigo, e nao como recem-visto — comportamento preservado de proposito, porque parte da suite usa `"added_on": 0` como atalho para "antigo". Na pratica o qBittorrent sempre preenche os dois: nos 53 torrents medidos em producao, nenhum vinha sem.
- `remove_stalled` nao mudou de escopo: segue alcancando `stalledDL`, `stalledUP` e `metaDL`, e `check_stalled_and_remove` continua pulando estados UP (download concluido em seeding nao e removido).
- Testes: 774 -> **781**.

## [2.6.2] — 2026-10-10

`latest` passa a significar "ultima release", e a versao publicada para de oscilar.

### Corrigido
- **A versao da imagem `latest` ora saia `2.6.1`, ora `2.6.1+768f557`.** Branch e tag sao empurrados juntos, e os **dois** builds publicavam a `latest`: o de main com o sufixo de commit, o de tag com o numero limpo. Ficava o que terminasse por ultimo — era corrida, nao regra.
- A causa de o build de tag tambem publicar a `latest` era a condicao `{{is_default_branch}}`, que o `docker/metadata-action` considera verdadeira **tambem em push de tag**. A regra agora e explicita: `startsWith(github.ref, 'refs/tags/v')`.

### Alterado
- **`latest` so se move em tag de versao.** Quem usa `ghcr.io/ihumberto/qbit-guardian:latest` (o que os docs recomendam) passa a receber **releases**, nao todo commit de `main`.
- Build de `main` publica em **`edge`**. O sufixo de commit (`2.6.2+abc1234`) passa a marcar exatamente o que ele e: build que **nao** e release.

### Notas
- **Isto muda o fluxo de deploy de quem acompanha a `latest`**: push para `main` deixa de atualizar o container sozinho; e preciso taguear. Em troca, a versao que aparece na notificacao do Watchtower e sempre um numero de release limpo (`2.6.1` -> `2.6.2`).
- Testes: 772 -> **774**. O teste de regressao rejeita explicitamente o `is_default_branch` na regra da `latest`, que e a armadilha que criou a corrida.

## [2.6.1] — 2026-10-10

O extrator do CHANGELOG estava na pasta errada.

### Alterado
- `changelog_section.py` saiu de `scripts/` para **`.github/scripts/`**. A `scripts/` da raiz e pasta de **entregavel do usuario** — o `qbit-guardian-hook.sh` e copiado para a maquina de quem roda o qBittorrent. O extrator e o oposto: so existe em tempo de publicacao, roda no runner e nunca sai de la. Agora fica colado no unico arquivo que o consome.

### Corrigido
- **A mudanca de pasta quebraria o release em silencio**: o script calculava a raiz do repositorio subindo **dois** niveis a partir do proprio arquivo. De `.github/scripts/` isso aponta para `.github/`, e o `CHANGELOG.md` nao seria encontrado — o workflow chama sem passar caminho. Ajustado para tres niveis, com teste que roda o script como o workflow roda.
- **O teste que protegia esse caminho nao protegia**: ele afirmava `"scripts/changelog_section.py" in texto`, e o caminho antigo e **substring** do novo — passaria com o arquivo em qualquer um dos dois lugares. Apertado para o caminho completo e conferido contra a versao errada.

### Notas
- `.github/scripts/**` **nao** entra no filtro de `paths` do build, de proposito: o job de release so roda em push de tag, e tag ignora `paths`. Incluir o caminho republicaria imagem identica a cada ajuste no script — exatamente o problema que a v2.3.2 consertou. Ha teste fixando isso.
- Testes: 769 -> **772**.
- De passagem: o `__pycache__` da raiz tinha `guardian.pyc` e `web.pyc` de **2026-06-18**, vespera do commit que criou `app/` (`ef4f5bd`, 2026-06-19). Residuo do layout antigo, nunca versionado, sem fonte correspondente na raiz hoje. Removido junto com o `scripts/__pycache__`, que era resto da suite importando o extrator.

## [2.6.0] — 2026-10-10

Cada tag publicada vira um GitHub Release com as notas desta pagina.

### Adicionado
- **Release automatico no GitHub a cada tag**, com a secao correspondente do CHANGELOG como corpo. A pagina de releases do projeto estava vazia porque o fluxo criava **tags**, nao releases — e era para ela que o aviso de versao nova apontava.
- `scripts/changelog_section.py`: extrai a secao de uma versao do CHANGELOG. Ficou como script, e nao como regex dentro do YAML, porque assim a suite testa a extracao contra o CHANGELOG real e um erro falha com mensagem em vez de publicar um release de corpo vazio.
- O aviso do rodape agora linka direto para as **notas da versao disponivel** (`/releases/tag/vX.Y.Z`) em vez da lista inteira. O `href` do HTML e so o destino de fallback, para antes do JavaScript rodar.

### Notas
- O job de release usa o `gh`, que ja vem no runner, em vez de uma action de terceiro — uma dependencia a menos na cadeia de publicacao. Roda so em tag (`startsWith(github.ref, 'refs/tags/v')`) e depende do build: release apontando para imagem que nao subiu seria pior que release nenhum.
- A cadeia de guardas fica completa: a suite exige `app/version.py` == topo do CHANGELOG, o build exige tag == `app/version.py`, e o release exige secao do CHANGELOG para aquela versao.
- `--verify-tag` impede o `gh` de criar a tag sozinho a partir do branch caso a ref nao exista.
- Testes: 759 -> **769**. Um teste antigo foi robustecido de quebra: ele delimitava um bloco de JavaScript por janela de 400 caracteres e quebrou ao ganhar uma linha — fragilidade do teste, nao do codigo.

## [2.5.2] — 2026-10-10

O aviso de versao nova aparecia sempre, com o placeholder cru.

### Corrigido
- **O aviso do rodape nunca ficava escondido**, e mostrava `{version} disponivel` mesmo com a versao mais recente instalada. O atributo `hidden` so esconde por causa da regra `[hidden] { display: none }` do **navegador**, que perde para qualquer `display:` declarado na folha de estilo — e o aviso declara `display:inline-block`. Sem a guarda `.atualizacao[hidden]`, o elemento ficava visivel; e como o `applyTranslations()` escreve nele mesmo escondido, o `{version}` sem `data-version` ia para a tela. O `.modal-bg[hidden]` ja existia no arquivo pelo mesmo motivo.
- O link do aviso aponta para `/tags` em vez de `/releases`: o repositorio cria **tags**, nao releases, entao a pagina de releases fica vazia. `/tags` lista exatamente o que a checagem compara.

### Notas
- Testes: 756 -> **759**. Um deles e generico: qualquer classe que declare `display:` e seja usada com o atributo `hidden` precisa da guarda `[hidden]`. Os tres foram conferidos contra o codigo bugado.
- Verificado no navegador nos dois cenarios: sem versao nova o aviso fica com `display:none` e o rodape mostra so `v2.5.2`; com versao nova ele aparece e acompanha a troca de idioma.
- O backend estava certo o tempo todo (`update_available: false`): o bug era so de apresentacao.

## [2.5.1] — 2026-10-10

O aviso de versao nova ficava em ingles depois de trocar o idioma.

### Corrigido
- **O aviso do rodape congelava no idioma do primeiro carregamento.** Em pt-BR ele continuava mostrando "available" e o tooltip em ingles. Causa: `setLang()` re-renderiza a pagina **sem recarregar**, e o `applyTranslations()` so alcanca elementos marcados com `data-i18n*` — o aviso escrevia `textContent` e `title` na mao, uma unica vez, entao nada o reescrevia na troca de idioma.
- O aviso passou a usar `data-i18n` e `data-i18n-title`, como o resto da interface. O `renderVars()` **ja documentava essa convencao** para elementos criados por JS; o aviso e que nao a seguiu.

### Adicionado
- O walker do i18n passa a preencher placeholders `{nome}` a partir dos `data-nome` do proprio elemento. Sem isso um texto com valor no meio (`{version} disponivel`) nao teria como passar pelo walker: quem tem o valor precisaria escrever o texto por fora — que e exatamente o que causava o congelamento.

### Notas
- Testes: 752 -> **756**. Os tres testes de regressao foram conferidos contra o codigo bugado: reprovam nele e passam na correcao.
- Verificado no navegador alternando pt-BR -> en-US -> pt-BR -> en-US: texto e tooltip acompanham as quatro trocas.

## [2.5.0] — 2026-10-10

O rodape avisa quando ha versao nova publicada.

### Adicionado
- **Aviso de versao nova no rodape**, ao lado da versao instalada: `v2.4.0  [v2.5.0 disponivel]`, com link para os releases. Nos dois idiomas.
- `app/updates.py`: compara a versao instalada com a **maior tag de release** do repositorio. Tag, e nao o label da imagem `:latest`, porque um build de `main` nao e um release — avisar a cada commit viraria ruido que o usuario aprende a ignorar.
- `/api/version` passa a responder `latest` e `update_available`. O veredito sai pronto do backend: o HTML nao compara versao.

### Notas
- **A comparacao e por numero, nao por texto.** Em ordem alfabetica `"2.10.0" < "2.9.0"`, o que esconderia exatamente a atualizacao que importa. Ha teste para esse par.
- **Tag mais velha que o instalado nao vira aviso de downgrade.** Caso real: o repo ficou em `v2.0.5` enquanto o codigo andou ate 2.4.0.
- **O sufixo de build nao participa da comparacao**: `2.4.0+a81f306` e `2.4.0` sao a mesma versao, senao todo build de `main` se anunciaria como atualizacao de si mesmo.
- **Falha de rede vira "nao sei", nunca erro na tela**: um painel de homelab precisa abrir sem internet. Resultado em cache por 6h, inclusive o "nao sei" — senao uma caixa offline paga o timeout a cada carregamento de pagina.
- Testes: 728 -> **752**.

## [2.4.0] — 2026-10-10

A imagem e a interface passam a dizer qual versao estao rodando.

### Adicionado
- `app/version.py` como **fonte unica da versao**. O projeto nao tinha a versao em lugar nenhum do codigo: existia no CHANGELOG e nas tags do git, e nada dentro da imagem sabia dizer qual versao era.
- **Rodape na Web UI** com a versao instalada, centralizado, alimentado por `/api/version`. O numero **nao** e escrito no HTML: vem do backend, que le a mesma `app/version.py` que o CI usa para etiquetar a imagem, para nao haver uma terceira copia saindo de sincronia.
- `GET /api/version`, atras de autenticacao. De proposito: o `/api/health`, que o healthcheck do container consome, continua publico **e sem a versao** — anunciar a versao exata para quem nao esta logado so ajuda quem procura alvo com versao conhecida.

### Corrigido
- **A imagem se anunciava como versao "latest".** O `docker/metadata-action` escreve `org.opencontainers.image.version` a partir do output `version` dele; num push para `main` a unica regra que dispara e `type=raw,value=latest`, entao o label saia literalmente `latest`. O build passa a **sobrescrever** o label com a versao do codigo (os labels do input entram depois dos automaticos, com dedup por chave last-wins).
- Build de **tag** usa o numero limpo e **falha** quando a tag nao casa com `app/version.py`; build de **main** anexa o commit curto (`2.4.0+abc1234`), para duas imagens consecutivas nao se anunciarem com a mesma versao.

### Notas
- Testes: 716 -> **728**.
- Os releases 2.1.0 a 2.3.3 **nunca foram tagueados** — e e por isso que a regra `type=semver` nunca disparava e toda imagem saia de push para `main`.

## [2.3.3] — 2026-10-07

Modo webhook que nunca funcionou para quem roda o qBittorrent em container.

### Corrigido
- **O script do webhook nao rodava nas imagens Docker do qBittorrent.** Ele comecava com `#!/bin/bash` e usava `curl`; as imagens sao baseadas em **Alpine Linux**, que **nao traz nenhum dos dois**. O qBittorrent falhava com "not found" (codigo 127) antes da primeira linha executar, e sem mensagem util. Verificado rodando o script dentro de uma `alpine:3`.
- O script virou **POSIX puro** (`#!/bin/sh`), e usa `curl` quando existe, caindo para o **`wget` do busybox** quando nao. Como o wget do busybox nao tem `--user`, o Basic Auth vai montado a mao com `base64`. Testado ponta a ponta de dentro de uma Alpine sem bash e sem curl: o script principal retorna em **0 ms** e a chamada chega ao `/api/trigger` com a credencial correta.
- Quando nao ha nem `curl` nem `wget`, o script diz isso no stderr do qBittorrent em vez de falhar em silencio.

### Adicionado
- Documentacao do que de fato impede o webhook de funcionar, nos dois idiomas: a **caixa de selecao** ao lado de "Executar programa externo ao adicionar torrent" precisa estar marcada, senao o qBittorrent **nao salva** o caminho e o campo volta vazio; o comando que confere isso pela API do qBittorrent (`/api/v2/app/preferences`, chaves `autorun_on_torrent_added_*`), que nao depende da tela; o bit de execucao do script; e `QBIT_GUARDIAN_PASS`.
- Testes do script: shebang POSIX, ausencia de construcoes exclusivas do bash, fallback para wget com `--post-data` e cabecalho de autenticacao, aviso quando nao ha cliente HTTP, e o bit de execucao.

### Notas
- Testes: 703 → **716**. 8 mutacoes no script, 8 pegas.
- O teste de paridade de endpoints precisou distinguir as duas APIs: `/api/v2/...` e do **qBittorrent**, nao do guardian. Ele reprovou a documentacao nova antes de a distincao existir.

## [2.3.2] — 2026-10-07

### Corrigido
- **Commit de documentacao publicava imagem nova no GHCR.** O `docker-build` disparava em qualquer push para `main`, entao mexer em `docs/`, README ou CHANGELOG gerava um build multi-arch e uma imagem **identica** no registry — e o Watchtower trocava o container em producao sem nada ter mudado. O gatilho passou a filtrar por caminho, listando exatamente o que entra na imagem: `app/`, `static/`, `requirements.txt`, `Dockerfile` e os dois workflows.
- Push de **tag** continua publicando normalmente: o GitHub Actions ignora `paths` em push de tag, entao `git push --tags` segue gerando release.

### Alterado
- O workflow `tests` **nao** ganhou filtro, de proposito. A documentacao passou a ser verificada por teste na v2.3.1, entao um ajuste em `docs/` pode legitimamente quebrar a suite — pular os testes nesse caso anularia a protecao inteira. A suite leva ~30s; o que custa caro e o build multi-arch, e esse sim e filtrado.

### Adicionado
- `TestWorkflowBuild` e `TestWorkflowTestes`: o filtro do build e conferido contra as linhas `COPY` do **Dockerfile**, entao passar a copiar uma pasta nova sem incluir no filtro quebra a suite — senao mudancas nessa pasta nunca chegariam a producao. Tambem fixam que `docs/`, README, CHANGELOG e `test/` **nao** disparam build, que o gatilho de tag continua la, e que o build segue atras do gate da suite.

### Notas
- Testes: 687 → **703**. 8 mutacoes nos workflows, 8 pegas.

## [2.3.1] — 2026-10-07

Reescrita da documentacao de usuario (`docs/`), que estava quatro releases
atras do codigo. Nenhuma mudanca de comportamento.

### Corrigido
- **Instalar seguindo a documentacao era impossivel.** O `INSTALL.md` mandava criar um `config.json` com `qbit.host` e `qbit.port`; o codigo usa `qbit.url` desde a v2.0.7, entao o guardian subia e morria com `KeyError: 'url'`. Mesmo erro em `primeiros-passos.md` e nos dois arquivos em ingles.
- **O volume do Docker apontava para o lugar errado**: `./config.json:/app/config.json`, enquanto a imagem le `/app/config/config.json`. O arquivo do usuario era ignorado, a config nascia dentro do container e **se perdia a cada atualizacao**.
- **A instalacao manual mandava rodar `python app/app.py`** — arquivo que nunca existiu. O entrypoint e `app/main.py`, e precisa ser chamado como `python -m app.main`: sem o `-m` o Python nao acha o pacote e sai com `ModuleNotFoundError`.
- **`cp config.json.example config.json`** — esse arquivo nao existe. Nenhum arquivo precisa ser criado: o `config.json` e gerado no primeiro boot.
- **O healthcheck documentado era o antigo** (`cat /tmp/heartbeat`), que so verificava a existencia do arquivo e reportava `healthy` para sempre com o loop morto. A imagem traz o correto desde a v2.0.5, e nao precisa ser declarado no compose.
- **A variavel `PORT`** aparecia no guia de problemas como forma de trocar a porta. O codigo nunca a leu — so `CONFIG_PATH` e `LOG_LEVEL`.
- **`USAGE.md` descrevia a tela em duas colunas** (sao tres desde a v2.0.8), mandava proteger o painel por uma "secao Autenticacao" que **nao existe na Web UI**, e trazia uma tabela de "status dos torrents processados" (`completed`, `dangerous`, `no_media`...) **inteiramente ficticia** — `_processed` e um set de hashes, sem status. Documentava tambem um log `Nenhum torrent novo` que o codigo nao emite.
- **Links para `forgejo.home.arpa`**, inalcancavel fora da rede do mantenedor, e um link interno para `configuracao.md`, que nao existe.

### Adicionado
- Documentacao de tudo que entrou entre a v2.0.6 e a v2.3.0 e nao estava em `docs/`: reconexao ao qBittorrent com `retry_interval_seconds`, grade de tres colunas, mensagens de notificacao editaveis com suas variaveis, autenticacao obrigatoria com senha gerada no startup, tela de login, troca de credenciais pelo icone de conta, freio de forca bruta, `chown` da pasta `config` e `QBIT_GUARDIAN_PASS` no hook do webhook.
- `docs/en-US/getting-started.md`, equivalente ao `primeiros-passos.md` que so existia em portugues.
- Os dois READMEs passaram a linkar cada guia individualmente, em vez de apontar so para a pasta.
- **Testes de paridade entre `docs/` e o codigo** (`TestDocsEstrutura`, `TestDocsContraOCodigo`, `TestDocsValoresPadrao`), que e o que impede isso de acontecer de novo. Eles conferem: schema do config, entrypoint, caminho do volume, UID do `chown` contra o Dockerfile, endpoints contra as rotas do Flask, variaveis de ambiente contra os pontos onde o codigo as le, listas de extensoes e escala de prioridade contra os defaults, variaveis de notificacao contra `NOTIFICATION_VARIABLES`, links internos e paridade de paginas entre os dois idiomas.

### Notas
- Testes: 546 → **687**. 16 mutacoes na documentacao, 16 pegas.
- Duas das mutacoes expuseram fraqueza nos proprios testes antes de qualquer doc quebrar: o teste de variaveis de ambiente passava um `PORT=` inventado, porque procurava a string no codigo e `TRANSPORT_ERRORS` contem "PORT"; e o teste do intervalo padrao procurava o numero solto no arquivo, entao trocar o padrao de 300 para 600 nao quebrava nada, ja que "300" aparece em outros exemplos. Os dois foram reescritos para ancorar no ponto certo.
- O teste que proibe variavel de notificacao inexistente pegou a propria prosa nova: eu tinha escrito `{{variavel}}` como exemplo generico, indistinguivel de uma variavel real.

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
