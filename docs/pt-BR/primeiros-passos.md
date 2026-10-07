# Primeiros Passos

Este guia ensina você a instalar e acessar o **qbit-guardian** pela primeira vez.

## O que é o qbit-guardian?

O qbit-guardian é um programa que vigia os torrents do seu **qBittorrent** e remove automaticamente:

- Arquivos **perigosos** — aqueles com extensão `.exe`, `.scr`, `.bat` e similares, que podem conter vírus.
- Torrents **parados há muito tempo** — downloads que travaram e não vão terminar.
- Torrents **sem seeds** — quando ninguém mais está compartilhando o arquivo completo.

> 💡 **Seed** (ou semeador) é alguém que já baixou o arquivo inteiro e continua enviando para os outros. Se um torrent tem zero seeds, você jamais conseguirá completar o download.

Ele também ajusta a prioridade dos arquivos dentro de cada torrent: o vídeo vem primeiro, os extras depois, e o lixo nem é baixado.

Quando você usa **Sonarr** (séries) ou **Radarr** (filmes), o qbit-guardian bloqueia o torrent ruim e dispara uma nova busca automática, para você não ficar esperando à toa.

---

## Pré-requisitos

- Um **servidor doméstico** ou computador que fique ligado com:
  - **qBittorrent** instalado e acessível via rede (no mesmo servidor ou em outro).
  - **Docker** (recomendado) OU **Python 3.10+** (instalação manual).

- A **API Key** do qBittorrent. Para encontrá-la:
  1. Abra o qBittorrent e vá em **Ferramentas** > **Opções** > aba **Web UI**.
  2. Copie o valor do campo **Chave da API**.

> 💡 **API Key** é uma senha longa e aleatória que o qBittorrent gera. Ela serve para que outros programas conversem com o qBittorrent de forma segura, sem precisar do seu login e senha.

---

## Opção 1 — Instalação com Docker (recomendada)

> 💡 **Docker** é como uma caixa que empacota o programa com tudo que ele precisa para rodar. Funciona igual em qualquer computador, sem instalar dependências extras.

### Passo 1: Crie a pasta de configuração

Na pasta onde fica o seu `docker-compose.yml`:

```bash
mkdir -p config
sudo chown -R 1000:1000 config
```

> ⚠️ **O `chown` é obrigatório.** Por segurança, o container roda como usuário comum (UID 1000) e não como root. Sem o ajuste de dono, ele não consegue gravar a configuração e sai na hora.

**Nenhum arquivo precisa ser criado.** O `config.json` é gerado sozinho na primeira execução.

### Passo 2: Adicione ao seu docker-compose.yml

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./config:/app/config
    environment:
      - LOG_LEVEL=ERROR
    restart: unless-stopped
```

> 📘 **Volume** é a ponte entre os arquivos do container e os da sua máquina. O que o programa salvar em `/app/config` dentro do container aparece na pasta `./config` do seu servidor. Assim, mesmo recriando o container, suas configurações não se perdem.

### Passo 3: Inicie o container

```bash
docker compose up -d qbit-guardian
```

### Passo 4: Pegue a senha de acesso

A Web UI exige login, e a senha é gerada na primeira execução:

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

> ⚠️ **Copie agora.** Essa senha aparece uma vez só.

---

## Opção 2 — Instalação Manual (sem Docker)

Use esta opção se você não usa Docker ou prefere rodar diretamente no sistema.

### Passo 1: Baixe o projeto

```bash
git clone https://github.com/iHumberto/qbit-guardian.git
cd qbit-guardian
```

### Passo 2: Instale as dependências

> 💡 **Ambiente virtual (venv)** é uma pasta isolada onde o Python instala bibliotecas só para este projeto, sem bagunçar o resto do sistema.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Passo 3: Execute o programa

```bash
python -m app.main
```

> ⚠️ Use `python -m app.main`, com o `-m`. Rodar `python app/main.py` falha com `ModuleNotFoundError: No module named 'app'`.

O `config.json` é criado sozinho na raiz do projeto, e a senha de acesso aparece no terminal. Deixe-o aberto — o programa roda até você pressionar `Ctrl+C`.

> 💡 Para manter rodando em segundo plano mesmo fechando o terminal, use `tmux` ou crie um serviço systemd.

---

## Primeiro acesso à Web UI

Abra o navegador e acesse:

```
http://endereco-do-seu-servidor:5000
```

Exemplos:

- Se roda na mesma máquina: `http://localhost:5000`
- Se roda em outro computador da rede: `http://192.168.1.100:5000`

Você cai na **tela de login**. Entre com o usuário `admin` e a senha que apareceu no log.

### Troque a senha

Clique no **ícone de usuário** no canto superior direito. Informe a senha atual, escolha uma nova (mínimo 8 caracteres) e salve. Se quiser, mude o nome de usuário no mesmo popup.

Depois de salvar você volta para a tela de login — é esperado, a troca encerra as sessões abertas.

---

## Configuração mínima para funcionar

Depois de entrar, apenas dois campos são obrigatórios:

| Campo | O que preencher |
|-------|----------------|
| **qBittorrent > URL** | Endereço completo, com `http://` e porta. Ex: `http://192.168.1.50:8080` |
| **qBittorrent > API Key** | A chave que você copiou das opções do qBittorrent |

> ⚠️ É a **URL completa**, não host e porta separados.

> ⚠️ No Docker, `localhost` dentro do container aponta para o próprio container, não para sua máquina. Se o qBittorrent está em outro container ou na máquina host, use `host.docker.internal` (Windows/Mac) ou o IP real (Linux, ex: `http://172.17.0.1:8080`).

Clique em **Salvar Configurações**. O guardião já começa a verificar torrents a cada **300 segundos (5 minutos)** usando as regras padrão.

Para ajustar o comportamento — extensões perigosas, remoção de stalled, prioridades, notificações — veja o **[Guia de Uso](USAGE.md)**.

---

## O que esperar

- Assim que você salvar a configuração, o guardião começa a trabalhar.
- A cada intervalo definido (padrão: 300 segundos), ele verifica todos os torrents ativos.
- Se encontrar um `.exe`, `.scr`, `.bat` ou outro arquivo suspeito, o torrent é removido na hora, com os arquivos.
- Se você configurou Sonarr/Radarr, o programa também bloqueia o lançamento e busca uma versão alternativa.
- As mensagens aparecem no `docker logs` (ou no terminal).

> 💡 O log vem em `LOG_LEVEL=ERROR` por padrão, que é bem silencioso. Para ver cada ação, mude para `LOG_LEVEL=VERBOSE` no `docker-compose.yml`.

---

## Problemas comuns na instalação

### ❌ O container sai logo depois de subir

**Causa:** a pasta `config` pertence ao root e o container roda sem privilégio.

**Solução:** `sudo chown -R 1000:1000 ./config` e suba de novo. O próprio log imprime esse comando.

### ❌ Não sei a senha da Web UI

**Solução:** rode `docker logs qbit-guardian` e procure o bloco de credenciais. Se o log já rolou demais, apague o valor de `webui.password` no `config.json` (deixando `""`) e reinicie o container — uma senha nova é gerada.

### ❌ "Connection refused" ou "qBittorrent indisponivel"

**Causa:** o qbit-guardian não consegue encontrar o qBittorrent.

**Solução:**
- Verifique se o qBittorrent está rodando.
- Confira a **URL** no painel: tem que ser completa, com `http://` e porta.
- Se usa Docker, `localhost` dentro do container não é o mesmo da sua máquina. Use `host.docker.internal` (Windows/Mac) ou o IP real (Linux).

### ❌ "qBittorrent: HTTP 403"

**Causa:** a API Key está errada ou vazia.

**Solução:**
- Vá em **Ferramentas** > **Opções** > **Web UI** no qBittorrent.
- Confirme que "Usar autenticação" está marcada.
- Copie a **Chave da API** e cole exatamente — sem espaços.

### ❌ `ModuleNotFoundError: No module named 'app'`

**Causa:** na instalação manual, o programa foi iniciado como `python app/main.py`.

**Solução:** use `python -m app.main`, a partir da pasta do projeto.

### ❌ A página não abre em http://...:5000

**Solução:**
- Verifique se o container está rodando: `docker ps | grep qbit-guardian`.
- Na instalação manual, veja se o terminal mostra "Web UI em http://0.0.0.0:5000".
- Confira se o firewall da máquina libera a porta 5000.

### ❌ Não quero usar Sonarr nem Radarr

Deixe os campos de **URL** do Sonarr e Radarr **em branco**. O guardião funciona perfeitamente sem eles — apenas não fará bloqueio e re-busca automática. Você ainda terá remoção de arquivos perigosos, stalled e sem seeds.

---

## Próximos passos

- [Guia de Uso](USAGE.md) — todos os recursos, em detalhe.
- [Guia de Instalação](INSTALL.md) — modo webhook, instalação manual avançada, solução de problemas.
- [Perguntas Frequentes](FAQ.md) — dúvidas comuns.
