# Guia de Uso do qbit-guardian

> Aprenda a usar o qbit-guardian no dia a dia: configurar, entender os modos de operação e interpretar o que está acontecendo.

## O que é

O qbit-guardian é um vigia automático para os seus torrents. Depois de instalado e configurado, ele trabalha sozinho em segundo plano. Você só precisa acessar a página de configuração de vez em quando para ajustar alguma coisa.

---

## Entrando no painel

Abra o navegador e digite o endereço do servidor onde o qbit-guardian está rodando, sempre na porta **5000**:

```
http://endereco-do-seu-servidor:5000
```

Exemplos práticos:

- **No mesmo computador:** `http://localhost:5000`
- **Em outro computador da rede:** `http://192.168.1.100:5000`
- **Servidor com nome na rede:** `http://meu-servidor:5000`

Você cai na **tela de login**. O usuário padrão é `admin`, e a senha foi gerada na primeira execução e impressa no log do container — veja [Primeiro acesso](#primeiro-acesso-e-troca-de-senha).

Depois de entrar, você vê o painel em **três colunas**:

| Coluna | O que tem |
|--------|-----------|
| **Esquerda** | qBittorrent, Radarr e Sonarr — os serviços externos |
| **Centro** | Guardian — intervalo, extensões, regras de remoção e prioridades |
| **Direita** | Notificações — Apprise e as mensagens de cada evento |

O botão **Salvar Configurações** fica centralizado abaixo das três colunas.

### Idioma

No canto superior direito há um seletor de idioma:

- 🇧🇷 **PT-BR (padrão):** a interface abre em português do Brasil na primeira vez.
- 🇺🇸 **EN-US:** alterna toda a interface para inglês americano.

A troca é instantânea — não precisa recarregar. O navegador lembra sua escolha.

> 💡 O seletor funciona offline. Toda a tradução já vem dentro da aplicação — nenhum serviço externo é usado. Sua preferência fica salva no próprio navegador (localStorage).

---

## Primeiro acesso e troca de senha

A Web UI **sempre** exige login. Não existe tela de cadastro: na primeira execução o guardião gera a senha sozinho e a imprime no log.

```bash
docker logs qbit-guardian
```

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================
```

> ⚠️ Essa senha aparece **uma vez só**. Copie e guarde.

### Trocando usuário ou senha

No painel, clique no **ícone de usuário** no canto superior direito. Abre um popup com três campos:

| Campo | Quando preencher |
|-------|-----------------|
| **Usuário** | Se quiser mudar o nome de usuário |
| **Senha atual** | **Sempre** — é a prova de que é você |
| **Nova senha** | Só se quiser trocar a senha (mínimo 8 caracteres) |

Quer trocar só o nome? Preencha usuário + senha atual e deixe a nova senha em branco. Quer trocar só a senha? Preencha senha atual + nova senha.

Depois de salvar, você volta para a tela de login — a troca encerra todas as sessões abertas, inclusive a sua.

> **📘 Por que a senha atual é sempre pedida:** sem ela, qualquer pessoa que encontrasse um navegador seu já logado poderia tomar a conta em dois cliques.

### Saindo

O mesmo popup tem o botão **Sair**, do lado esquerdo.

### Como a senha é guardada

Como **hash PBKDF2-SHA256** com salt próprio. Ela nunca fica em texto claro no `config.json` e nunca é devolvida pela API. Mesmo quem leia o arquivo não consegue recuperar a senha.

### Esqueci a senha

Abra o `config.json` na pasta `config`, deixe `webui.password` vazio (`""`) e reinicie o container. Uma senha nova é gerada e anunciada no log.

### Tentativas demais

Depois de **5 tentativas erradas em 5 minutos**, o login responde "Tentativas demais" para aquele cliente — inclusive se a senha seguinte estiver certa. É proteção contra alguém tentando adivinhar a senha por força bruta. Espere alguns minutos.

---

## Configuração essencial

Para o qbit-guardian começar a funcionar, apenas dois campos são obrigatórios:

| Campo | Onde encontrar |
|-------|---------------|
| **URL do qBittorrent** | Endereço completo com `http://` e porta (ex: `http://192.168.1.50:8080`) |
| **API Key do qBittorrent** | No qBittorrent: **Ferramentas → Opções → Web UI → Chave da API** |

> ⚠️ É **URL completa**, não host e porta separados. Escreva `http://192.168.1.50:8080`, não apenas `192.168.1.50`.

> **📘 API Key:** É uma senha longa e aleatória que o qBittorrent gera. Ela permite que outros programas conversem com o qBittorrent de forma segura. Pense nela como uma chave de acesso que você entrega para um aplicativo de confiança.

Preencha esses dois campos, clique em **Salvar Configurações** e pronto — o guardião já está trabalhando.

### Integração com Sonarr e Radarr (opcional)

Se você usa o Sonarr (para séries) ou o Radarr (para filmes), preencha também os campos de **URL** e **API Key** dessas ferramentas.

Com essa integração ativa, sempre que o qbit-guardian remover um torrent problemático, ele também:

1. Bloqueia aquele lançamento no Sonarr/Radarr (para não baixar de novo).
2. Dispara uma nova busca automática por uma versão alternativa.

> 💡 Se você não usa Sonarr nem Radarr, deixe os campos em branco. O guardião funciona normalmente — só a parte de bloqueio e re-busca automática é ignorada.

---

## Notificações

O qbit-guardian pode te avisar pelo celular ou computador sempre que uma ação importante acontecer. Para isso, ele usa o **Apprise** — um sistema que envia mensagens para mais de 100 serviços diferentes (Telegram, Discord, Slack, Pushover, e-mail e muitos outros).

> **📘 Apprise:** É como um carteiro universal. Você entrega uma única URL e ele se encarrega de entregar a mensagem no serviço que você escolheu. Você não precisa instalar nada extra, só gerar a URL correta.

### Ativando notificações

Preencha o campo **Apprise URL** com o endereço gerado para o seu serviço e ligue o interruptor no cabeçalho do card **Notificações**. Exemplos de URLs Apprise:

| Serviço | Formato da URL |
|---------|---------------|
| Telegram | `tgram://TOKEN_DO_BOT/ID_DO_CHAT` |
| Discord | `discord://ID_DO_WEBHOOK/TOKEN` |
| Pushover | `pover://USER_KEY/APP_TOKEN` |
| Apprise próprio | `https://apprise.minha-rede/notify/guardian` |

> Consulte a [lista completa de formatos](https://github.com/caronc/apprise#supported-notifications) na documentação oficial do Apprise.

### Os três eventos

| Evento | Quando dispara |
|--------|---------------|
| ⚡ **Torrent Otimizado** | As prioridades dos arquivos foram ajustadas |
| ⚠️ **Torrent Excluído (Perigoso)** | Removido por arquivo perigoso ou por não ter mídia válida |
| 🗑️ **Torrent Excluído (Stalled)** | Removido por estar parado tempo demais ou sem seeds |

Cada um tem seu próprio **interruptor** e sua própria **caixa de texto**.

### Editando as mensagens

Cada caixa de texto é a mensagem que será enviada. Dentro dela, cada `{{...}}` é substituída pelo valor real do torrent.

As variáveis disponíveis aparecem listadas logo abaixo de cada caixa:

| Evento | Variáveis |
|--------|-----------|
| Otimizado | `{{torrentName}}` `{{priorityMedia}}` `{{priorityAux}}` `{{mediaCount}}` |
| Excluído (perigoso) | `{{torrentName}}` `{{reason}}` `{{extensions}}` |
| Excluído (stalled) | `{{torrentName}}` `{{reason}}` `{{state}}` `{{stalledTime}}` |

> 💡 Se você escrever uma variável que não existe, ela aparece **literalmente** na mensagem — assim um erro de digitação fica visível em vez de sumir em silêncio.

**Dois níveis de liga/desliga.** A notificação só é enviada com os **dois** ligados: o interruptor geral (no cabeçalho do card) e o do evento. Com a mensagem desligada, o texto continua visível mas não pode ser editado — você vê o que seria enviado sem conseguir alterar por acidente.

Apagou o texto por engano? Caixa vazia volta ao padrão em vez de enviar mensagem em branco.

> O **título** de cada notificação não aparece no painel, mas continua editável no `config.json`, em `notifications.events.<evento>.title`.

### Apprise com certificado auto-assinado

Se o seu servidor Apprise usa um certificado SSL auto-assinado (comum em redes domésticas com endereços como `apprise.home.arpa`), o guardião já funciona sem verificação SSL. Nenhuma configuração adicional é necessária.

> **📘 Certificado SSL auto-assinado:** É um certificado gerado por você mesmo, sem a validação de uma autoridade externa. Em redes caseiras é uma alternativa gratuita aos certificados pagos — o navegador e outros programas não confiam nele automaticamente.

---

## Modos de operação

O qbit-guardian tem duas formas de funcionar. Você escolhe no campo **Intervalo de verificação** da seção Guardian.

### Modo Polling (padrão)

Neste modo, o guardião verifica os torrents de tempos em tempos. Você define o intervalo em segundos.

- **Padrão:** 300 segundos (5 minutos).
- **Exemplo rápido:** 60 segundos (1 minuto).
- **Exemplo econômico:** 1800 segundos (30 minutos).

Quanto menor o intervalo, mais rápido um torrent perigoso é detectado. Quanto maior, menos recursos do servidor são usados.

Recomendamos **300 segundos** para uso geral — é rápido o suficiente e não sobrecarrega nada.

### Modo Webhook (tempo real)

Neste modo, o qBittorrent avisa o guardião **no exato momento** em que um torrent é adicionado. Coloque `0` no intervalo de verificação e siga o passo a passo em [Configurando o Webhook](INSTALL.md#configurando-o-webhook-tempo-real).

> ⚠️ O webhook precisa das variáveis `QBIT_GUARDIAN_USER` e `QBIT_GUARDIAN_PASS` no serviço do qBittorrent, porque o `/api/trigger` exige autenticação.

### Se o qBittorrent cair

O guardião **não desiste**. Ele registra um aviso no log e tenta reconectar a cada `retry_interval_seconds` (padrão: 120 segundos) até o qBittorrent voltar. Isso vale tanto no startup — quando o servidor reinicia e o guardião sobe primeiro — quanto durante a operação normal.

Durante o retry o container continua `healthy`: o healthcheck mede a saúde do **processo guardião**, não a do qBittorrent, que é uma dependência externa e transitória. Acompanhe o log para ver a indisponibilidade.

---

## Personalizando as regras

### Extensões perigosas

São as extensões que, se encontradas dentro de um torrent, fazem o guardião remover tudo na hora. A lista padrão:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

Você pode adicionar ou remover extensões na seção **Guardian**, uma por linha.

> ⚠️ Só faça isso se tiver certeza. Arquivos `.exe` são o principal veículo de vírus em torrents. Se remover, você perde a proteção principal do guardião.

### Extensões de mídia válidas

É a lista de formatos que o guardião considera "conteúdo legítimo". Se um torrent não tiver **nenhum** arquivo com essas extensões, ele é tratado como suspeito e removido.

A lista padrão: `.mkv` `.mp4` `.avi` `.mov` `.m4v` `.ts` `.wmv` `.flv` `.webm`

Adicione ou remova formatos conforme sua preferência. Por exemplo, se você baixa ISOs de Blu-ray, adicione `.iso` e `.m2ts`.

> 💡 Deixar a lista **vazia** desliga esse critério: nenhum torrent é removido por "não ter mídia válida". A detecção de extensões perigosas continua funcionando normalmente.

### Remoção de torrents parados (stalled)

Um torrent "stalled" é aquele que não consegue baixar — seja porque as fontes sumiram, seja por problema de conexão.

Para ativar, ligue o interruptor **Remover torrents parados (stalled) há mais de** e defina o tempo e a unidade (segundos, minutos ou horas).

Exemplo: `6 horas` — o guardião remove torrents parados há mais de 6 horas.

> ⚠️ Tempo `0` significa **desligado**, nunca "remover agora".

### Remoção de torrents sem seeds

Um torrent "sem seeds" é aquele onde ninguém está compartilhando o arquivo completo. Sem seeds, é impossível completar o download.

Ligue o interruptor **Remover torrents sem seeds há mais de** e defina o tempo de espera (ex: `24 horas`).

> 💡 **Seed** (ou semeador) é alguém que já baixou o arquivo inteiro e continua enviando para os outros. Se um torrent tem zero seeds, você jamais conseguirá completar o download — é como tentar copiar um livro que ninguém mais tem.

### Torrents já completos nunca são tocados

Torrents que terminaram de baixar e estão semeando (estados `uploading`, `stalledUP`, `pausedUP`, `checkingUP`, `queuedUP`) ficam fora do escopo do guardião. Ele não remove nem reprioriza nada neles.

### Prioridades de arquivos

Quando um torrent tem vários tipos de arquivo, o guardião ajusta automaticamente a prioridade de download:

| Tipo de arquivo | Prioridade padrão | O que acontece |
|----------------|------------------|---------------|
| Arquivos de mídia (`.mkv`, `.mp4`, etc.) | **7 — máxima** | São baixados primeiro |
| Arquivos auxiliares (`.nfo`, `.srt`, `.jpg`, `.png`, `.txt`, `.sub`, `.idx`) | **1 — normal** | Baixados depois |
| Qualquer outro arquivo | **0 — não baixar** | Nem chegam ao disco |

Isso faz o download do filme ou episódio começar mais rápido e evita baixar arquivos inúteis — inclusive anexos indesejados como `.url` e `.lnk`, que não estão na lista de perigosos mas também não interessam.

A escala aceita pelo qBittorrent **não é contínua**. Os valores válidos são:

| Valor | Significado |
|-------|------------|
| `0` | Não baixar |
| `1` | Normal |
| `6` | Alta |
| `7` | Máxima |

> ⚠️ Valores como `2`, `3`, `4` ou `5` são recusados pelo qBittorrent com erro HTTP 400. Os três campos de prioridade no painel são listas suspensas, então você só escolhe valores válidos.

---

## Entendendo o que aparece nos logs

O qbit-guardian registra o que faz. Você pode ver os logs de duas formas:

- **Docker:** `docker logs qbit-guardian`
- **Instalação manual:** direto no terminal onde o programa está rodando

### Níveis de log

Controlados pela variável de ambiente `LOG_LEVEL`:

| Nível | O que mostra |
|-------|-------------|
| `ERROR` (padrão) | Apenas erros e remoções |
| `INFO` | Resumo de cada verificação |
| `VERBOSE` | Cada ação por torrent |
| `DEBUG` | Tudo, incluindo chamadas HTTP |

> 💡 O padrão é silencioso de propósito. Se está investigando algum comportamento, suba para `INFO` ou `VERBOSE` temporariamente.

### Mensagens comuns

| Mensagem no log | O que aconteceu |
|----------------|-----------------|
| `Verificacao #12: 30 torrents, 2 novos, 1 stalled removidos, 0 removidos do historico` | Resumo de um ciclo (nível `INFO`). |
| `Arquivos perigosos: ['.exe'] — Removendo e Bloqueando` | O torrent continha um `.exe` e foi removido. Se Sonarr/Radarr estiverem configurados, o lançamento foi bloqueado e uma nova busca iniciada. |
| `Nenhum arquivo de midia valido — Removendo e Bloqueando` | O torrent não tinha nenhum arquivo com as extensões de mídia configuradas. |
| `stalled (stalledDL) por >6h — REMOVIDO` | O torrent estava parado há mais de 6 horas. |
| `0 seeds — REMOVIDO` | O torrent estava sem seeds pelo tempo configurado. |
| `sem metadados — sera reavaliado no proximo ciclo` | Magnet ainda baixando a lista de arquivos. Ele volta ao próximo ciclo, não é dado como processado. |
| `otimizado (3 arquivos de midia priorizados)` | As prioridades de download foram ajustadas. |
| `qBittorrent indisponivel (...) — nova tentativa em 120s` | Perdeu contato com o qBittorrent. Está retentando. |
| `qBittorrent inacessivel, reconectando...` | Erro de transporte durante a operação. Entra em retry. |
| `prioridade de arquivo invalida: 4` | Um dos campos de prioridade tem valor fora da escala aceita. Corrija no painel. |

---

## Forçando uma verificação manual

Se quiser que o guardião verifique os torrents agora, sem esperar o intervalo, use o botão **Forçar verificação** na página de configuração.

Ou, pela linha de comando:

```bash
curl -X POST http://seu-servidor:5000/api/trigger -u usuario:senha
```

Isso é útil para testar se está tudo funcionando depois de configurar.

---

## Dicas e boas práticas

- **Troque a senha gerada.** A do log serve para o primeiro acesso; escolha uma sua pelo ícone de usuário.
- **Teste primeiro sem notificações.** Deixe o guardião rodar alguns dias em silêncio. Depois que estiver confiante no comportamento, ative as notificações.
- **Intervalo de 5 minutos é suficiente.** Para uso doméstico, checar a cada 300 segundos é rápido o bastante. Não precisa colocar 10 segundos — você não vai notar diferença e só gasta recursos.
- **Mantenha as extensões perigosas atualizadas.** De tempos em tempos, aparecem novos tipos de arquivo usados para espalhar vírus.
- **Se usa Sonarr/Radarr, aproveite a integração.** Preencher os campos faz o guardião bloquear lançamentos ruins e buscar alternativas automaticamente.
- **Faça backup da pasta `config`.** É um arquivo JSON só — copiar já resolve.

---

## Precisa de ajuda?

- Leia as [Perguntas Frequentes](FAQ.md) para dúvidas comuns.
- Veja o [Guia de Instalação](INSTALL.md) se precisar instalar do zero.
- Problemas, sugestões e contribuições: [repositório do projeto](https://github.com/iHumberto/qbit-guardian).
