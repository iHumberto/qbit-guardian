# qbit-guardian

Protege instalações do qBittorrent contra torrents maliciosos, removendo automaticamente arquivos perigosos e torrents problemáticos, com integração ao ecossistema *Arr (Sonarr/Radarr).

## Linguagem

**qBittorrent (qBit)**:
Cliente BitTorrent monitorado pelo guardian.
_Evitar_: qbit (minúsculo no meio de frase), client, downloader

**Torrent**:
Unidade de download no qBittorrent, composta por um ou mais arquivos. Cada torrent tem hash único, nome, estado e metadados.
_Evitar_: download, release (termo do Sonarr/Radarr), pacote

**Seed**:
Peer na rede BitTorrent que possui o arquivo completo.
_Evitar_: seeder, fonte

**Stalled**:
Estado do torrent quando está parado — sem atividade de download (stalledDL) ou upload (stalledUP). Torrents stalled são candidatos a remoção automática.
_Evitar_: parado, travado, inativo

**Extensão (extension)**:
Sufixo do nome do arquivo que indica seu tipo (ex: `.mkv`, `.exe`). O guardian classifica extensões em válidas (mídia) ou perigosas (executáveis/scripts).
_Evitar_: formato, tipo de arquivo

**Arquivo de mídia (media file)**:
Arquivo com extensão considerada segura e desejável (`.mkv`, `.mp4`, `.avi` etc.). Torrents sem nenhum arquivo de mídia válido são removidos.
_Evitar_: vídeo, filme, episódio

**Arquivo perigoso (dangerous file)**:
Arquivo com extensão associada a malware ou execução de código (`.exe`, `.scr`, `.bat`, `.sh` etc.). Torrents contendo tais arquivos são removidos e bloqueados.
_Evitar_: malware, vírus, executável

**Prioridade (priority)**:
Valor de 0 a 7 no qBittorrent que controla a ordem e urgência de download dos arquivos de um torrent. 7 = máxima prioridade, 0 = não baixar.
_Evitar_: peso, ranking

**Polling**:
Modo de operação onde o guardian consulta a API do qBittorrent a cada N segundos (`check_interval_seconds > 0`).
_Evitar_: loop, verificação periódica

**Webhook**:
Modo de operação onde o qBittorrent notifica o guardian via HTTP POST (`/api/trigger`) quando um torrent é adicionado. Configurado com `check_interval_seconds = 0`.
_Evitar_: callback, notificação, hook

**Sonarr**:
Gerenciador de séries de TV. O guardian interage via API v3 para blocklist e re-search de episódios, com validação de data de lançamento.
_Evitar_: series, tv

**Radarr**:
Gerenciador de filmes. O guardian interage via API v3 para blocklist e re-search de filmes.
_Evitar_: movies, filmes

**Blocklist**:
Ação de adicionar um release à lista de bloqueio do Sonarr/Radarr, impedindo que o mesmo release seja baixado novamente.
_Evitar_: blacklist, bloquear, banir

**Re-search**:
Comando enviado ao Sonarr/Radarr para iniciar busca automática por um release alternativo após um blocklist.
_Evitar_: re-busca, procurar de novo, search again

**Apprise**:
Serviço de notificação multi-backend (Telegram, Discord, Slack, etc.) usado para alertar sobre remoções e otimizações.
_Evitar_: notificador, alerta, push

**API Key**:
Token de autenticação usado para acessar as APIs do qBittorrent (Bearer token no header `Authorization`), Sonarr e Radarr (header `X-Api-Key`).
_Evitar_: senha, token, chave, secret

## Relações

- Um **qBittorrent** gerencia múltiplos **Torrents**
- Um **Torrent** contém múltiplos arquivos, cada um com uma **Extensão**
- Uma **Extensão** é classificada como **Arquivo de mídia** ou **Arquivo perigoso**
- Um **Torrent** pode estar em estado **Stalled**
- Um **Torrent** é removido → dispara **Blocklist** no **Sonarr** ou **Radarr** → dispara **Re-search**
- O guardian opera em modo **Polling** OU **Webhook** (mutuamente exclusivos)
- Notificações de remoção/otimização são enviadas via **Apprise**

## Diálogo de exemplo

> **Dev:** "Quando o guardian encontra um torrent com `.exe`, ele remove e faz blocklist no Radarr. Mas e se for uma série — ele tenta blocklist no Sonarr também?"
> **Domain expert:** "O guardian tenta blocklist em AMBOS. Se o torrent está na queue do Radarr, bloqueia lá. Se está na queue do Sonarr, bloqueia lá. Se não está em nenhum, tenta match por nome. A única diferença é que no Sonarr ele valida data de lançamento do episódio antes de disparar re-search."

> **Dev:** "O que acontece se `check_interval_seconds = 0` mas eu não configurar o webhook no qBit?"
> **Domain expert:** "O guardian fica em modo **Webhook** — ele NÃO faz polling. Só processa torrents quando recebe um POST no `/api/trigger`. Se o webhook não estiver configurado no qBit, nenhum torrent novo será analisado."

## Ambiguidades sinalizadas

- "remove" foi usado para significar tanto **remoção do qBittorrent** (`/api/v2/torrents/delete`) quanto **remoção da queue do Sonarr/Radarr** (`/api/v3/queue/{id}` com `removeFromClient=false`) — resolvido: são operações distintas. "Remover" sem qualificação = remoção do qBittorrent. "Remover da queue" = operação no *Arr.
