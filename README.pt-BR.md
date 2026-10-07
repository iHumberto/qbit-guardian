# 🛡️ qbit-guardian

> Proteção em tempo real para o seu qBittorrent — detecta e remove torrents maliciosos antes que causem estragos.

🇺🇸 **Read in English:** [README.md](README.md)

[![tests](https://github.com/iHumberto/qbit-guardian/actions/workflows/test.yml/badge.svg)](https://github.com/iHumberto/qbit-guardian/actions/workflows/test.yml)
[![docker-build](https://github.com/iHumberto/qbit-guardian/actions/workflows/docker-build.yml/badge.svg)](https://github.com/iHumberto/qbit-guardian/actions/workflows/docker-build.yml)
[![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)](https://github.com/iHumberto/qbit-guardian)
[![License: GPL v3](https://img.shields.io/badge/License-GNU_GPL_v3-brightgreen?style=flat&logo=gnuprivacyguard)](https://www.gnu.org/licenses/gpl-3.0)

---

## O que é o qbit-guardian?

O qbit-guardian monitora os torrents ativos do seu qBittorrent e remove automaticamente aqueles que contêm arquivos perigosos (`.exe`, `.scr`, `.bat`, `.ps1`, `.vbs` e outros), estão parados há muito tempo ou não têm seeds. Quando integrado ao Sonarr/Radarr, ele também bloqueia o lançamento ruim e dispara uma nova busca automática — assim sua biblioteca continua crescendo sem intervenção manual.

Ele roda como um container Docker leve (ou como um processo Python) com uma interface Web integrada para configuração, notificações via Apprise e um modo webhook opcional para processamento em tempo real.

## Stack

| Componente    | Tecnologia                          |
|---------------|-------------------------------------|
| Runtime       | Python 3.12                         |
| Interface Web | Flask 3.x                           |
| Cliente HTTP  | requests 2.x                        |
| Notificações  | Apprise (Telegram, Discord, Slack e mais de 100 serviços) |
| Testes        | pytest 8.x (716 testes: 598 funcionais + 118 segurança) |
| Licença       | GNU GPL v3                          |

## Funcionalidades

- 🔍 **Detecção de arquivos maliciosos** — remove torrents com executáveis, scripts e outras extensões perigosas
- 🎬 **Integração com Radarr** — blocklist + busca automática para filmes
- 📺 **Integração com Sonarr** — blocklist + busca automática com validação de data de lançamento dos episódios
- 🗑️ **Remoção de stalled e sem seeds** — limpa torrents mortos após um tempo configurável
- ⚡ **Otimização de prioridades** — prioriza automaticamente arquivos de mídia, reduz ou pula arquivos inúteis
- 🔔 **Notificações via Apprise** — alertas por Telegram, Discord, Slack, Pushover e mais de 100 outros serviços
- 🖥️ **Web UI** — três colunas com tema escuro: serviços externos (qBittorrent, Radarr, Sonarr) à esquerda, configurações do Guardian no meio, notificações à direita. HTTP Basic Auth obrigatória, com troca de credenciais pelo próprio painel
- 🪝 **Modo webhook** — processamento em tempo real quando um torrent é adicionado (sem delay de polling)
- 🐳 **Docker-first** — imagem pronta no `ghcr.io`, healthcheck incluso

## ⚠️ Atualizando para a 2.2.0

Duas mudanças pedem uma ação sua. Faça **antes** de subir a nova imagem:

**1. A pasta de configuração precisa pertencer ao UID 1000.** O container deixou de rodar como root. Na pasta do `docker-compose.yml`:

```bash
sudo chown -R 1000:1000 ./config
```

Sem isso o container sai na hora e imprime esse mesmo comando no log.

**2. Se você usa o modo webhook,** defina `QBIT_GUARDIAN_PASS` no serviço do qBittorrent — veja [Modo Webhook](#modo-webhook-tempo-real). O `/api/trigger` passou a exigir autenticação.

Depois de subir, pegue a senha da Web UI com `docker logs qbit-guardian` (veja [Autenticação da Web UI](#autenticação-da-web-ui)). Se você já tinha usuário e senha configurados, eles continuam valendo.

## Quick Start (Docker)

Adicione ao seu `docker-compose.yml` junto com o qBittorrent:

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "app/healthcheck.py"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
```

> O healthcheck verifica a **idade** do heartbeat, não apenas a existência do arquivo — assim um loop travado é detectado em vez de reportar `healthy` para sempre. A tolerância é `max(600s, 3 × check_interval_seconds, 3 × retry_interval_seconds)`: o retry entra na conta porque, enquanto o qBittorrent está fora, o heartbeat sai no ritmo do retry.

Depois inicie:

```bash
docker compose up -d
```

Na primeira execução, o sistema cria a configuração automaticamente — nada de editar JSON manualmente. Acesse `http://seu-host:5000` para preencher todas as configurações pela Web UI.

> 💡 **O que é uma API Key?** É uma senha longa e aleatória que o qBittorrent gera para que outros programas (como o qbit-guardian) conversem com ele de forma segura. Encontre a sua no qBittorrent em **Ferramentas → Opções → Web UI → Chave da API**.

### Layout da Web UI

A página de configuração é dividida em três colunas:

- **Coluna esquerda**: conexões com seus serviços externos — qBittorrent, Radarr e Sonarr.
- **Coluna do meio**: todas as configurações do Guardian — intervalo de verificação, extensões de arquivo, prioridades e regras de remoção de stalled/sem seeds.
- **Coluna direita**: notificações via Apprise.

No cabeçalho ficam o ícone **Docs** — passe o mouse para a dica, clique para abrir a documentação do projeto no seu idioma — e o seletor de idioma.

Abaixo de 1200 px as três colunas se empilham na vertical, para a página continuar usável em tablets e celulares sem espremer os rótulos mais longos.

## Instalação Manual (sem Docker)

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.json.example config.json   # edite com suas credenciais
python app/app.py
```

O processo roda em primeiro plano. Pressione `Ctrl+C` para parar.

## Configuração

Todas as opções ficam no arquivo `config.json` e podem ser editadas pela Web UI ou diretamente. Estrutura completa:

```json
{
  "qbit": {
    "url": "http://localhost:8080",
    "api_key": ""
  },
  "sonarr": {
    "url": "",
    "api_key": ""
  },
  "radarr": {
    "url": "",
    "api_key": ""
  },
  "guardian": {
    "check_interval_seconds": 300,
    "retry_interval_seconds": 120,
    "valid_media_extensions": [
      ".mkv",
      ".mp4",
      ".avi",
      ".mov",
      ".m4v",
      ".ts",
      ".wmv",
      ".flv",
      ".webm"
    ],
    "dangerous_extensions": [
      ".exe",
      ".scr",
      ".bat",
      ".cmd",
      ".vbs",
      ".js",
      ".com",
      ".pif",
      ".msi",
      ".dll",
      ".ps1",
      ".sh",
      ".bin"
    ],
    "remove_stalled": false,
    "stalled_time": 0,
    "stalled_unit": "hours",
    "remove_no_seeds": false,
    "no_seeds_time": 0,
    "no_seeds_unit": "hours",
    "priority_media": 7,
    "priority_normal": 1,
    "priority_skip": 0
  },
  "notifications": {
    "apprise_url": "",
    "enabled": true,
    "events": {
      "optimized": {
        "enabled": true,
        "title": "⚡ Torrent Otimizado",
        "template": "Nome: {{torrentName}}\nArquivos de midia priorizados."
      },
      "removed": {
        "enabled": true,
        "title": "⚠️ Torrent Removido",
        "template": "Nome: {{torrentName}}\nMotivo: {{reason}}"
      },
      "stalled": {
        "enabled": true,
        "title": "🗑️ Torrent Removido (stalled)",
        "template": "Nome: {{torrentName}}\nMotivo: {{reason}}"
      }
    }
  },
  "webui": {
    "user": "",
    "password": ""
  }
}
```

| Seção            | Campos principais                                                                                     |
|------------------|-------------------------------------------------------------------------------------------------------|
| **qbit**         | `url` (esquema + host + porta), `api_key` — conexão com sua instância do qBittorrent                 |
| **sonarr**       | `url`, `api_key` — opcional, deixe em branco para desativar                                          |
| **radarr**       | `url`, `api_key` — opcional, deixe em branco para desativar                                          |
| **guardian**     | `check_interval_seconds` (0 = modo webhook), `retry_interval_seconds`, listas de extensões, regras de stalled/sem seeds, prioridades |
| **notifications** | `apprise_url` — URL compatível com Apprise (veja [documentação do Apprise](https://github.com/caronc/apprise)) |
| **webui**        | `user`, `password`, `secret_key` — provisionados no primeiro startup. A senha fica como hash PBKDF2; a `secret_key` assina o cookie de sessão |

### Mensagens de notificação

Cada tipo de notificação tem seu próprio texto, editável na Web UI ou direto no `config.json`, e um liga/desliga próprio — além do liga/desliga geral da seção. O envio só acontece com os **dois** ligados; com a mensagem desligada, o texto continua visível na Web UI, mas não pode ser alterado.

Os textos padrão reproduzem exatamente as mensagens das versões anteriores: quem atualizar sem mexer na configuração continua recebendo a notificação de sempre. Uma caixa apagada volta ao padrão em vez de enviar notificação em branco.

Dentro do texto, cada `{{...}}` da tabela abaixo é substituído pelo valor do torrent. Uma variável que não existe fica literal na mensagem — assim um erro de digitação aparece em vez de sumir em silêncio.

| Evento | Chave em `events` | Variáveis disponíveis |
|--------|-------------------|------------------------|
| Torrent otimizado | `optimized` | `{{torrentName}}` `{{priorityMedia}}` `{{priorityAux}}` `{{mediaCount}}` |
| Torrent removido (perigoso / sem mídia) | `removed` | `{{torrentName}}` `{{reason}}` `{{extensions}}` |
| Torrent removido (stalled / sem seeds) | `stalled` | `{{torrentName}}` `{{reason}}` `{{state}}` `{{stalledTime}}` |

| Variável | Significado |
|----------|-------------|
| `{{extensions}}` | extensões perigosas encontradas (vazio quando o motivo foi ausência de mídia válida) |
| `{{mediaCount}}` | quantos arquivos de mídia foram priorizados |
| `{{priorityAux}}` | prioridade aplicada aos arquivos auxiliares (`.nfo`, `.srt`, `.jpg`…) |
| `{{priorityMedia}}` | prioridade aplicada aos arquivos de mídia |
| `{{reason}}` | motivo da remoção |
| `{{stalledTime}}` | limiar de stalled configurado (vazio quando a remoção foi por falta de seeds) |
| `{{state}}` | estado do torrent no qBittorrent (`stalledDL`, `metaDL`…) |
| `{{torrentName}}` | nome do torrent |

O **título** de cada notificação (`events.<evento>.title`) não aparece na Web UI, mas continua editável no `config.json`.

### Autenticação da Web UI

**A Web UI exige autenticação.** Não há tela de cadastro: na primeira subida o guardian **gera a senha sozinho** e a imprime no log do container.

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

Essa senha aparece **uma vez**, no momento em que é criada. Guarde-a.

A Web UI tem **tela de login propria** em `/login`. Quem acessa sem sessao e redirecionado para la; `curl` e scripts continuam usando HTTP Basic Auth normalmente.

Para trocar usuário ou senha, clique no **ícone de usuário** no canto superior direito do painel. O popup pede a senha atual (prova de identidade), o novo usuário e a nova senha — qualquer um dos dois pode ficar em branco se você só quer trocar o outro.

A senha é guardada como **hash PBKDF2-SHA256** com salt por senha. Ela nunca fica em texto claro no `config.json` e nunca é devolvida pelo `GET /api/config`.

Depois de entrar, a sessão vale 7 dias e fica num cookie `HttpOnly` assinado. Trocar o usuário ou a senha **invalida todas as sessões abertas**. Para sair, use o botão **Sair** no mesmo popup do ícone de usuário.

> Depois de 5 tentativas erradas em 5 minutos, o login responde `429` para aquele cliente — inclusive se a senha seguinte estiver certa.

> **Esqueceu a senha?** Apague o valor de `webui.password` no `config.json` e reinicie o container. Uma senha nova é gerada e anunciada no log.

> **Atualizando de uma versão anterior a 2.2.0?** Se você já tinha `webui.user`/`webui.password` preenchidos, nada muda: a senha que você usava continua valendo e é convertida para hash no primeiro startup. Se os campos estavam vazios, uma senha é gerada e aparece no log.

Deixar `webui.user` e `webui.password` vazios continua desligando a autenticação — para quem já protege a porta por outro meio, como um proxy reverso com SSO. Mas o próximo restart do container gera uma senha nova e religa.

## Modos de Operação

### Polling (padrão)

O guardian verifica os torrents a cada N segundos. Defina `guardian.check_interval_seconds` com qualquer valor acima de 0. Padrão: 300 segundos (5 minutos).

### Reconexão ao qBittorrent

Se o qBittorrent não estiver disponível — tipicamente quando o servidor reinicia e o guardian sobe primeiro — o guardian **não desiste**: ele registra um `WARNING` e tenta de novo a cada `guardian.retry_interval_seconds` (padrão: 120 segundos) até conectar. O mesmo vale se o qBittorrent cair depois, já em operação.

Durante o retry o heartbeat continua sendo atualizado: o healthcheck mede a saúde do **processo** guardian, não a do qBittorrent, que é uma dependência externa e transitória. Por isso o container permanece `healthy` enquanto está retentando — acompanhe o log para ver a indisponibilidade.

> Se você aumentar `retry_interval_seconds`, a tolerância do healthcheck cresce junto (3×), então não há risco de o container ser marcado `unhealthy` só por causa de um retry longo.

### Webhook (tempo real)

Defina `check_interval_seconds` como `0` e configure o qBittorrent para chamar o guardian a cada novo torrent:

**1.** No qBittorrent: **Configurações → Downloads → Executar programa externo ao adicionar torrent**:

```
/scripts/qbit-guardian-hook.sh
```

**2.** Monte o script de webhook no container do qBittorrent:

```yaml
# No serviço do qBittorrent no docker-compose:
volumes:
  - ./caminho/para/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
environment:
  - QBIT_GUARDIAN_URL=http://qbit-guardian:5000
  - QBIT_GUARDIAN_USER=admin
  - QBIT_GUARDIAN_PASS=a-senha-da-web-ui
```

Quando um torrent é adicionado, o qBittorrent chama o script, que envia `POST /api/trigger` para o guardian — processando o torrent instantaneamente.

> ⚠️ **`QBIT_GUARDIAN_PASS` é obrigatória desde a v2.2.0.** O `/api/trigger` exige autenticação; sem a senha o guardian responde 401 e o modo webhook para de funcionar. O script avisa no stderr do qBittorrent quando isso acontece.

## API REST

A Web UI expõe estes endpoints:

| Método   | Endpoint             | Auth        | Descrição                                                        |
|----------|----------------------|-------------|------------------------------------------------------------------|
| `GET`    | `/api/health`        | Público     | Healthcheck — retorna `{"status": "ok"}`                         |
| `GET`    | `/login`             | Público     | Tela de login (redireciona para `/` se já há sessão)             |
| `POST`   | `/api/login`         | Público     | Troca usuário e senha por cookie de sessão. `429` após 5 erros   |
| `POST`   | `/api/logout`        | Público     | Encerra a sessão                                                 |
| `GET`    | `/api/config`        | Obrigatória | Lê a configuração atual. **Não** devolve `webui.password`        |
| `POST`   | `/api/config`        | Obrigatória | Salva configuração (deep merge). A seção `webui` é ignorada aqui |
| `GET`    | `/api/defaults`      | Obrigatória | Títulos/templates padrão e variáveis de cada evento              |
| `POST`   | `/api/credentials`   | Obrigatória | Troca usuário e/ou senha da Web UI                               |
| `POST`   | `/api/trigger`       | Obrigatória | Força verificação imediata (manual ou webhook)                   |

Todo endpoint de escrita exige `Content-Type: application/json` (exceto `/api/trigger`, que não tem corpo) e recusa requisição disparada por outro site — é a proteção contra CSRF. Clientes de linha de comando como o `curl` não são afetados.

### Exemplo: trocar a senha da Web UI

```bash
curl -X POST http://seu-host:5000/api/credentials \
  -u admin:senha-atual \
  -H "Content-Type: application/json" \
  -d '{"current_password": "senha-atual", "new_password": "senha-nova-forte"}'
```

### Exemplo: disparar verificação

```bash
curl -X POST http://seu-host:5000/api/trigger \
  -u admin:sua-senha
```

### Exemplo: alterar configuração pela API

```bash
curl -X POST http://seu-host:5000/api/config \
  -u admin:sua-senha \
  -H "Content-Type: application/json" \
  -d '{"guardian": {"check_interval_seconds": 120}}'
```

## Variáveis de Ambiente

| Variável       | Padrão          | Descrição                          |
|----------------|-----------------|------------------------------------|
| `CONFIG_PATH`  | `./config.json` | Caminho para o arquivo de configuração |
| `LOG_LEVEL`    | `ERROR`         | Nível de detalhe dos logs (veja [Níveis de Log](#níveis-de-log)) |

## Níveis de Log

O qbit-guardian pode mostrar diferentes quantidades de detalhes nos logs. Escolha o nível ideal para você:

| Nível    | O que aparece |
|----------|--------------|
| `ERROR`  | Só problemas: torrents removidos, falhas de conexão. É o padrão — silencioso e direto ao ponto. |
| `INFO`   | ERROR mais uma linha de resumo após cada verificação: "Verificação #42: 23 torrents, 2 novos, 1 removidos". Bom para saber que o guardian está funcionando. |
| `VERBOSE` | INFO mais uma linha por ação em cada torrent: "[Filme.Nome.2026] stalled (stalledDL) por >5h — REMOVIDO", "[TV.Show.S01] otimizado". Ideal para entender *por que* um torrent foi removido. |
| `DEBUG`   | Tudo: chamadas HTTP, URLs, dados enviados. Bem verboso — use só para investigar problemas de integração (Sonarr, Radarr, qBittorrent). |

### Como configurar

**Docker (recomendado):** Adicione a variável `LOG_LEVEL` no seu `docker-compose.yml`:

```yaml
services:
  qbit-guardian:
    environment:
      - LOG_LEVEL=VERBOSE
```

Depois recrie o container:

```bash
docker compose up -d
```

**Instalação manual:** Defina a variável antes de iniciar:

```bash
LOG_LEVEL=DEBUG python app/app.py
```

> 💡 **O que é nível de log?** Pense como um controle de volume para os logs. No mínimo (`ERROR`) você só escuta quando algo dá errado. No máximo (`DEBUG`) você escuta cada detalhe — útil quando algo não está funcionando e você precisa investigar.

### Exemplo de saída

Veja o que aparece após uma verificação com `LOG_LEVEL=VERBOSE`:

```
2026-06-22 14:35:01,012 [VERBOSE] [Filme.Nome.2026.1080p] otimizado (2 arquivos de midia priorizados)
2026-06-22 14:35:01,123 [VERBOSE] [Serie.T01E05.1080p] otimizado (1 arquivos de midia priorizados)
2026-06-22 14:35:01,234 [VERBOSE] [Lancamento.Antigo.2025.720p] stalled (stalledDL) por >5h — REMOVIDO
2026-06-22 14:35:01,456 [INFO   ] Verificacao #1: 23 torrents, 23 novos, 2 removidos
```

Com `LOG_LEVEL=ERROR` (o padrão), você veria apenas a linha de remoção e eventuais erros de conexão — nada além disso.

## Problemas Comuns

### "Connection refused" ou "Falha ao conectar no qBit"

- Verifique se o qBittorrent está rodando e com a Web UI ativada.
- Confira se `qbit.url` está correto no `config.json` — ele inclui esquema, host e porta (ex.: `http://192.168.1.10:8080`).
- **Usuários Docker:** `localhost` dentro do container aponta para o próprio container, não para a máquina host. Use `host.docker.internal` (Windows/Mac) ou o IP real da máquina (Linux, ex: `172.17.0.1`).
- O guardian **continua retentando** em vez de encerrar, então isso aparece como um `WARNING` repetido no log, não como container morto. Corrija a URL ou suba o qBittorrent e a próxima tentativa conecta sozinha — sem precisar reiniciar.

### "HTTP 403" / "Unauthorized"

A API Key está errada ou vazia.
- No qBittorrent: **Ferramentas → Opções → Web UI**.
- Confirme que a autenticação está ativada (usuário `admin` + uma senha).
- Copie a Chave da API exatamente como aparece — sem espaços ou quebras de linha extras.

### A página não abre na porta 5000

- Veja se o container está rodando: `docker ps | grep qbit-guardian`
- Na instalação manual, procure por `Web UI em http://0.0.0.0:5000` no terminal.
- Confira se o firewall da máquina libera a porta 5000.
- Tente acessar de outra máquina na mesma rede.

### Não uso Sonarr nem Radarr

Deixe os campos `sonarr.url` e `radarr.url` em branco. O guardian funciona perfeitamente sem eles — você ainda terá remoção de arquivos perigosos, limpeza de stalled/sem seeds e otimização de prioridades. Apenas o bloqueio e a re-busca automática são ignorados.

## Desenvolvimento

```bash
# Instalar dependências (runtime + ferramentas de teste)
pip install -r requirements-dev.txt

# Rodar todos os testes (716: 598 funcionais + 118 de segurança)
python -m pytest test/ -v

# Apenas testes funcionais
python -m pytest test/test_guardian.py -v

# Apenas testes de segurança
python -m pytest test/test_security.py -v

# Cobertura (configuração em .coveragerc)
python -m coverage run -m pytest test/ && python -m coverage report
```

CI roda a cada push e pull request via GitHub Actions (`.github/workflows/test.yml`). O build da imagem (`docker-build.yml`) depende dessa suite, então nada é publicado no GHCR com teste quebrado.

## Documentação

Guias passo a passo para quem está começando, em português e inglês:

| Guia | Para quê |
|------|----------|
| [Primeiros Passos](docs/pt-BR/primeiros-passos.md) | Instalar e acessar pela primeira vez |
| [Instalação](docs/pt-BR/INSTALL.md) | Docker, instalação manual, modo webhook e solução de problemas |
| [Uso](docs/pt-BR/USAGE.md) | Todos os recursos do painel, em detalhe |
| [Perguntas Frequentes](docs/pt-BR/FAQ.md) | Dúvidas comuns e erros conhecidos |

- 📖 [English docs](docs/en-US/) — [Getting Started](docs/en-US/getting-started.md) · [Install](docs/en-US/INSTALL.md) · [Usage](docs/en-US/USAGE.md) · [FAQ](docs/en-US/FAQ.md)

## Licença

**GNU General Public License v3.0** — veja [LICENSE](LICENSE).

Este software é livre: você pode usar, estudar, modificar e redistribuir sob os termos da GPLv3. Qualquer trabalho derivado **deve** ser distribuído sob a mesma licença. Derivados de código fechado ou proprietários não são permitidos.
