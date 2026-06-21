# Primeiros Passos

Este guia ensina você a instalar e acessar o **qbit-guardian** pela primeira vez.

## O que é o qbit-guardian?

O qbit-guardian é um programa que vigia os torrents do seu **qBittorrent** e remove automaticamente:

- Arquivos **perigosos** — aqueles com extensão `.exe`, `.scr`, `.bat` e similares, que podem conter vírus.
- Torrents **parados há muito tempo** — downloads que travaram e não vão terminar.
- Torrents **sem seeds** — quando ninguém mais está compartilhando o arquivo completo.

> 💡 **Seed** (ou semeador) é alguém que já baixou o arquivo inteiro e continua enviando para os outros. Se um torrent tem zero seeds, você jamais conseguirá completar o download.

Quando você usa **Sonarr** (séries) ou **Radarr** (filmes), o qbit-guardian bloqueia o torrent ruim e dispara uma nova busca automática, para você não ficar esperando à toa.

---

## Pré-requisitos

- Um **servidor doméstico** ou computador que fique ligado com:
  - **qBittorrent** instalado e acessível via rede (no mesmo servidor ou em outro).
  - **Docker** (recomendado) OU **Python 3.10+** (instalação manual).

- A **API Key** do qBittorrent. Para encontrá-la:
  1. Abra o qBittorrent e vá em **Ferramentas** > **Opções** > aba **Web UI**.
  2. Copie o valor do campo **Chave da API**. Você vai precisar colar essa chave na configuração do qbit-guardian.

> 💡 **API Key** é uma senha longa e aleatória que o qBittorrent gera. Ela serve para que outros programas (como o qbit-guardian) conversem com o qBittorrent de forma segura, sem precisar usar seu login e senha.

---

## Opção 1 — Instalação com Docker (recomendada)

> 💡 **Docker** é como uma caixa que empacota o programa com tudo que ele precisa para rodar. Funciona igual em qualquer computador, sem instalar dependências extras.

### Passo 1: Adicione ao seu docker-compose.yml

Abra o arquivo `docker-compose.yml` onde você já configura seus outros serviços (qBittorrent, Sonarr, Radarr) e adicione:

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
```

> 📘 **Volume** é a ponte entre os arquivos do container e os arquivos da sua máquina. O que o programa salvar em `/app/config` dentro do container aparece na pasta `./config` do seu servidor. Assim, mesmo se recriar o container, suas configurações não se perdem.

### Passo 2: Inicie o container

Na pasta onde está seu `docker-compose.yml`, execute:

```bash
docker compose up -d
```

O programa baixa a imagem e inicia automaticamente. **Nenhum arquivo de configuração precisa ser criado antes** — o sistema gera tudo sozinho na primeira execução.

### Passo 3: Configure tudo pela Web UI

Abra o navegador e acesse `http://endereco-do-seu-servidor:5000`. Todos os campos aparecem vazios, prontos para você preencher:

- **qBittorrent**: endereço, porta e a API Key do seu cliente de torrents.
- **Sonarr** e **Radarr**: integração com séries e filmes (opcional — pode deixar em branco).
- **Guardian**: regras de monitoramento, intervalos, prioridades.
- **Notificações**: alertas via Telegram, Discord e outros (opcional).
- **Web UI**: proteção com senha para o painel (opcional).

Preencha os campos que desejar e clique em **Salvar**. Pronto — as configurações são gravadas automaticamente em `./config/config.json` e carregadas nas próximas execuções.

> ⚠️ No Docker, `localhost` dentro do container aponta para o próprio container, não para sua máquina. Se o qBittorrent está em outro container ou na máquina host, use `host.docker.internal` (Windows/Mac) ou o IP real da máquina (Linux, ex: `172.17.0.1`).

---

## Opção 2 — Instalação Manual (sem Docker)

Use esta opção se você não usa Docker ou prefere rodar diretamente no sistema.

### Passo 1: Clone o projeto (opcional)

Você pode baixar os arquivos do projeto pelo git ou manualmente pelo navegador:

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
```

### Passo 2: Instale as dependências com Python

> 💡 **Ambiente virtual (venv)** é uma pasta isolada onde o Python instala bibliotecas só para este projeto, sem bagunçar o resto do sistema. Funciona como uma gaveta separada.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Passo 3: Crie e edite o arquivo de configuração

```bash
cp config.json.example config.json
```

Abra o `config.json` em qualquer editor de texto e preencha:

- **qbit.host**: endereço IP ou nome do computador com qBittorrent.
- **qbit.api_key**: a chave da API que você copiou do qBittorrent.

### Passo 4: Execute o programa

```bash
python app/app.py
```

Deixe o terminal aberto. O programa fica rodando até você pressionar `Ctrl+C`.

> 💡 Para manter rodando em segundo plano mesmo fechando o terminal, use uma ferramenta como `tmux` ou crie um serviço systemd. Esses tópicos estão fora do escopo deste guia, mas são bem documentados na internet.

---

## Primeiro acesso à Web UI

Depois que o programa estiver rodando, abra o navegador e acesse:

```
http://endereco-do-seu-servidor:5000
```

Exemplos:

- Se roda na mesma máquina: `http://localhost:5000`
- Se roda em outro computador da rede: `http://192.168.1.100:5000`

**Na primeira vez**, todos os campos aparecem vazios — o sistema cria um arquivo de configuração novo. Preencha as seções conforme sua necessidade:

- **qBittorrent**: conexão com seu cliente de torrents.
- **Radarr** e **Sonarr**: integração (opcional, pode deixar em branco).
- **Guardian**: regras de monitoramento.
- **Notificações**: alertas via Telegram, Discord, etc.

Depois de preencher, clique em **Salvar**. A configuração fica gravada e carrega automaticamente nas próximas execuções.

> ⚠️ Na primeira execução, a página **não tem senha**. Qualquer pessoa na sua rede pode acessar. Veja abaixo como proteger.

---

## Configuração mínima para funcionar

Para o qbit-guardian começar a proteger seus torrents, apenas dois campos são obrigatórios:

| Campo | O que preencher |
|-------|----------------|
| **qBittorrent > Host** | IP ou nome do computador com qBittorrent |
| **qBittorrent > API Key** | A chave que você copiou das opções do qBittorrent |

Com isso, o guardian já começa a verificar torrents a cada **300 segundos (5 minutos)** usando as regras padrão. Clique em **Salvar Configurações**.

Para ajustar o comportamento — extensões perigosas, remoção de stalled, prioridades, notificações — veja o **[Guia de Configuração](configuracao.md)**.

---

## Protegendo a Web UI com senha

No arquivo `config.json`, adicione o bloco `webui`:

```json
{
  "webui": {
    "user": "admin",
    "password": "uma-senha-forte"
  }
}
```

Se preferir, edite pela própria Web UI: a seção de autenticação aparece no final da página.

Depois de salvar, o navegador vai pedir usuário e senha sempre que você acessar a página. Se você esquecer a senha, basta editar o `config.json` diretamente e remover os campos `user` e `password`.

> ⚠️ Se ambos os campos (`user` e `password`) estiverem vazios, a autenticação é desativada e a página fica pública novamente.

---

## O que esperar

- Assim que você salvar a configuração, o guardian começa a trabalhar.
- A cada intervalo definido (padrão: 300 segundos), ele verifica todos os torrents ativos.
- Se encontrar um `.exe`, `.scr`, `.bat` ou outro arquivo suspeito, o torrent é removido na hora.
- Se você configurou Sonarr/Radarr, o programa também bloqueia o lançamento e busca uma versão alternativa.
- Mensagens de log aparecem no terminal (ou no `docker logs`) mostrando cada ação: `"Arquivos perigosos: ['.exe'] — Removendo e Bloqueando"`.

---

## Problemas comuns na instalação

### ❌ "Connection refused" ou "Falha ao conectar no qBit"

**Causa:** o qbit-guardian não consegue encontrar o qBittorrent.

**Solução:**
- Verifique se o qBittorrent está rodando.
- Confira o **host** e a **porta** no `config.json`.
- Se usa Docker, o `localhost` dentro do container não é o mesmo `localhost` da sua máquina. Use `host.docker.internal` (Windows/Mac) ou o IP real da máquina (Linux).

### ❌ "HTTP 403" ou "Unauthorized"

**Causa:** a API Key está errada ou vazia.

**Solução:**
- Vá em **Ferramentas** > **Opções** > **Web UI** no qBittorrent.
- Confirme que a opção "Usar autenticação" está marcada (usuário: `admin`, defina uma senha).
- Copie a **Chave da API** e cole exatamente como está — não adicione espaços.

### ❌ A página não abre em http://...:5000

**Causa:** porta 5000 bloqueada ou programa não iniciou.

**Solução:**
- Verifique se o container Docker está rodando: `docker ps | grep qbit-guardian`.
- Na instalação manual, veja se o terminal mostra "Web UI em http://0.0.0.0:5000".
- Confira se o firewall da máquina libera a porta 5000.
- Tente acessar de outra máquina na mesma rede.

### ❌ Não quero usar Sonarr nem Radarr

Deixe os campos de host do Sonarr e Radarr **em branco**. O guardian funciona perfeitamente sem eles — apenas não fará bloqueio e re-busca automática. Você ainda terá remoção de arquivos perigosos, stalled e sem seeds.
