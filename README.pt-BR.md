# 🛡️ qbit-guardian

> Proteção em tempo real para o seu qBittorrent — detecta e remove torrents maliciosos antes que causem estragos.

🇺🇸 **Read in English:** [README.md](README.md)

[![tests](https://github.com/iHumberto/qbit-guardian/actions/workflows/test.yml/badge.svg)](https://github.com/iHumberto/qbit-guardian/actions/workflows/test.yml)
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
| Testes        | pytest 8.x (79 testes: 59 funcionais + 20 segurança) |
| Licença       | GNU GPL v3                          |

## Funcionalidades

- 🔍 **Detecção de arquivos maliciosos** — remove torrents com executáveis, scripts e outras extensões perigosas
- 🎬 **Integração com Radarr** — blocklist + busca automática para filmes
- 📺 **Integração com Sonarr** — blocklist + busca automática com validação de data de lançamento dos episódios
- 🗑️ **Remoção de stalled e sem seeds** — limpa torrents mortos após um tempo configurável
- ⚡ **Otimização de prioridades** — prioriza automaticamente arquivos de mídia, reduz ou pula arquivos inúteis
- 🔔 **Notificações via Apprise** — alertas por Telegram, Discord, Slack, Pushover e mais de 100 outros serviços
- 🖥️ **Web UI** — duas colunas com tema escuro: serviços externos (qBittorrent, Sonarr, Radarr, notificações) à esquerda, configurações do Guardian à direita. Suporte a HTTP Basic Auth
- 🪝 **Modo webhook** — processamento em tempo real quando um torrent é adicionado (sem delay de polling)
- 🐳 **Docker-first** — imagem pronta no `ghcr.io`, healthcheck incluso

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
      test: ["CMD", "cat", "/tmp/heartbeat"]
      interval: 60s
      timeout: 5s
      retries: 3
```

Depois inicie:

```bash
docker compose up -d
```

Na primeira execução, o sistema cria a configuração automaticamente — nada de editar JSON manualmente. Acesse `http://seu-host:5000` para preencher todas as configurações pela Web UI.

> 💡 **O que é uma API Key?** É uma senha longa e aleatória que o qBittorrent gera para que outros programas (como o qbit-guardian) conversem com ele de forma segura. Encontre a sua no qBittorrent em **Ferramentas → Opções → Web UI → Chave da API**.

### Layout da Web UI

A página de configuração é dividida em duas colunas:

- **Coluna esquerda**: conexões com seus serviços externos — qBittorrent, Sonarr, Radarr e notificações via Apprise.
- **Coluna direita**: todas as configurações do Guardian — intervalo de verificação, extensões de arquivo, prioridades e regras de remoção de stalled/sem seeds.

Em celulares e tablets (telas com menos de 768 px de largura), as colunas se empilham na vertical para manter tudo fácil de usar.

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
    "host": "localhost",
    "port": 8080,
    "api_key": ""
  },
  "sonarr": {
    "host": "",
    "port": 8989,
    "api_key": ""
  },
  "radarr": {
    "host": "",
    "port": 7878,
    "api_key": ""
  },
  "guardian": {
    "check_interval_seconds": 300,
    "valid_media_extensions": [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".webm"],
    "dangerous_extensions": [".exe", ".scr", ".bat", ".cmd", ".vbs", ".js", ".com", ".pif", ".msi", ".dll", ".ps1", ".sh", ".bin"],
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
    "apprise_url": ""
  },
  "webui": {
    "user": "",
    "password": ""
  }
}
```

| Seção            | Campos principais                                                                                     |
|------------------|-------------------------------------------------------------------------------------------------------|
| **qbit**         | `host`, `port`, `api_key` — conexão com sua instância do qBittorrent                                 |
| **sonarr**       | `host`, `port`, `api_key` — opcional, deixe em branco para desativar                                 |
| **radarr**       | `host`, `port`, `api_key` — opcional, deixe em branco para desativar                                 |
| **guardian**     | `check_interval_seconds` (0 = modo webhook), listas de extensões, regras de stalled/sem seeds, prioridades |
| **notifications** | `apprise_url` — URL compatível com Apprise (veja [documentação do Apprise](https://github.com/caronc/apprise)) |
| **webui**        | `user`, `password` — credenciais HTTP Basic Auth. Deixe ambos vazios para acesso público             |

### Autenticação da Web UI

Para proteger o painel com senha, preencha `webui.user` e `webui.password`. O navegador passará a pedir usuário e senha em todo acesso. Deixe ambos vazios para manter a página pública.

> ⚠️ Se esquecer a senha, edite o `config.json` diretamente e limpe os dois campos.

## Modos de Operação

### Polling (padrão)

O guardian verifica os torrents a cada N segundos. Defina `guardian.check_interval_seconds` com qualquer valor acima de 0. Padrão: 300 segundos (5 minutos).

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
```

Quando um torrent é adicionado, o qBittorrent chama o script, que envia `POST /api/trigger` para o guardian — processando o torrent instantaneamente.

## API REST

A Web UI expõe estes endpoints:

| Método   | Endpoint        | Auth      | Descrição                                           |
|----------|-----------------|-----------|-----------------------------------------------------|
| `GET`    | `/api/health`   | Público   | Healthcheck — retorna `{"status": "ok"}`            |
| `GET`    | `/api/config`   | Obrigatória | Lê a configuração atual (JSON completo)           |
| `POST`   | `/api/config`   | Obrigatória | Salva configuração (JSON no body, deep merge)     |
| `POST`   | `/api/trigger`  | Obrigatória | Força verificação imediata (manual ou webhook)     |

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
| `VERBOSE` | INFO mais uma linha por ação em cada torrent: "[Filme.Nome.2026] stalled por >5h — REMOVIDO", "[TV.Show.S01] otimizado". Ideal para entender *por que* um torrent foi removido. |
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
2026-06-22 14:35:01,234 [VERBOSE] [Lancamento.Antigo.2025.720p] stalled por >5h — REMOVIDO
2026-06-22 14:35:01,456 [INFO   ] Verificacao #1: 23 torrents, 23 novos, 2 removidos
```

Com `LOG_LEVEL=ERROR` (o padrão), você veria apenas a linha de remoção e eventuais erros de conexão — nada além disso.

## Problemas Comuns

### "Connection refused" ou "Falha ao conectar no qBit"

- Verifique se o qBittorrent está rodando e com a Web UI ativada.
- Confira se `qbit.host` e `qbit.port` estão corretos no `config.json`.
- **Usuários Docker:** `localhost` dentro do container aponta para o próprio container, não para a máquina host. Use `host.docker.internal` (Windows/Mac) ou o IP real da máquina (Linux, ex: `172.17.0.1`).

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

Deixe os campos `sonarr.host` e `radarr.host` em branco. O guardian funciona perfeitamente sem eles — você ainda terá remoção de arquivos perigosos, limpeza de stalled/sem seeds e otimização de prioridades. Apenas o bloqueio e a re-busca automática são ignorados.

## Desenvolvimento

```bash
# Instalar dependências (inclui pytest)
pip install -r requirements.txt

# Rodar todos os testes (79: 59 funcionais + 20 de segurança)
python -m pytest test/ -v

# Apenas testes funcionais
python -m pytest test/test_guardian.py -v

# Apenas testes de segurança
python -m pytest test/test_security.py -v
```

CI roda a cada push e pull request via GitHub Actions (`.github/workflows/test.yml`).

## Documentação

- 📖 [Documentação em português](docs/pt-BR/) — guias detalhados e referência
- 📖 [English docs](docs/en-US/) — detailed guides and reference

## Licença

**GNU General Public License v3.0** — veja [LICENSE](LICENSE).

Este software é livre: você pode usar, estudar, modificar e redistribuir sob os termos da GPLv3. Qualquer trabalho derivado **deve** ser distribuído sob a mesma licença. Derivados de código fechado ou proprietários não são permitidos.
