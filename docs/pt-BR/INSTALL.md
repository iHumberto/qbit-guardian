# Instalando o qbit-guardian

> Guia passo a passo para instalar o qbit-guardian. Escolha entre Docker (recomendado) ou instalação manual.

## O que você precisa antes de começar

- Um computador ou servidor que fique ligado (o qbit-guardian precisa rodar 24h).
- O **qBittorrent** já instalado e funcionando, com a **Web UI ativada**.

> **📘 Web UI do qBittorrent:** É a página de controle que permite gerenciar o qBittorrent pelo navegador. Para ativar, vá em **Ferramentas → Opções → Web UI** no qBittorrent, marque a caixa **Usar autenticação** e defina um usuário e senha.

- A **API Key** do qBittorrent. Para encontrá-la:
  1. No qBittorrent: **Ferramentas → Opções → Web UI**.
  2. Copie o valor do campo **Chave da API**. Você vai colá-lo na configuração do qbit-guardian.

> 💡 Guarde essa chave em um local seguro. É com ela que o guardião se conecta ao qBittorrent.

Escolha abaixo o método de instalação que preferir.

---

## Opção 1: Instalação com Docker (recomendada)

O Docker empacota o programa com tudo que ele precisa. Funciona igual em qualquer sistema (Windows, Mac, Linux) e é a forma mais simples de instalar.

> **📘 Docker:** É como uma caixa que contém o programa e todas as suas dependências. Você não precisa instalar Python, bibliotecas nem nada — a caixa já vem pronta. Também facilita atualizar e remover o programa depois.

### Passo 1: Crie o arquivo de configuração

Crie uma pasta para o qbit-guardian. Por exemplo, `/home/usuario/docker/qbit-guardian/`.

Dentro dela, crie um arquivo chamado `config.json` com este conteúdo:

```json
{
  "qbit": {
    "host": "ENDERECO-DO-QBITTORRENT",
    "port": 8080,
    "api_key": "COLE-SUA-API-KEY-AQUI"
  }
}
```

Ajuste os valores:

- `host`: IP ou nome do computador onde o qBittorrent está.
  - Se ambos (qBittorrent e qbit-guardian) rodam na **mesma máquina** com Docker: use `host.docker.internal` (Windows/Mac) ou `172.17.0.1` (Linux).
  - Se estão em máquinas **diferentes**: use o IP do computador onde o qBittorrent roda (ex: `192.168.1.100`).
- `port`: porta da Web UI do qBittorrent. O padrão é `8080`.
- `api_key`: cole a chave que você copiou do qBittorrent.

### Passo 2: Adicione ao docker-compose.yml

Abra o arquivo `docker-compose.yml` onde você já gerencia seus outros serviços (qBittorrent, Sonarr, Radarr) e adicione este bloco:

```yaml
services:
  qbit-guardian:
    image: ghcr.io/ihumberto/qbit-guardian:latest
    container_name: qbit-guardian
    ports:
      - "5000:5000"
    volumes:
      - ./qbit-guardian/config.json:/app/config.json
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "cat", "/tmp/heartbeat"]
      interval: 60s
      timeout: 5s
      retries: 3
```

O que cada linha faz:

| Linha | Explicação |
|-------|-----------|
| `image: ghcr.io/...` | Baixa a imagem do programa pronta para uso. |
| `ports: "5000:5000"` | Torna a página de controle acessível na porta 5000. |
| `volumes: ./qbit-guardian/config.json:/app/config.json` | Conecta seu arquivo de configuração com o container. Assim você edita o config.json fora do container. |
| `restart: unless-stopped` | Se o container parar por algum motivo, o Docker reinicia automaticamente. |
| `healthcheck` | O Docker verifica se o programa está saudável e avisa se algo der errado. |

### Passo 3: Inicie o container

Abra o terminal na pasta onde está o `docker-compose.yml` e execute:

```bash
docker compose up -d qbit-guardian
```

Na primeira vez, o Docker baixa a imagem (pode levar alguns segundos). Depois disso, inicia na hora.

Para ver se está tudo certo:

```bash
docker ps | grep qbit-guardian
```

Se aparecer uma linha com o nome `qbit-guardian` e status `Up`, a instalação deu certo.

### Atualizando o qbit-guardian

Quando sair uma nova versão, atualize com:

```bash
docker compose pull qbit-guardian
docker compose up -d qbit-guardian
```

Sua configuração (arquivo `config.json`) é preservada — só o programa é atualizado.

---

## Opção 2: Instalação manual (sem Docker)

Use esta opção se você não usa Docker ou prefere rodar o programa diretamente. Você vai precisar do **Python 3.10 ou superior** instalado.

### Passo 1: Baixe o projeto

```bash
git clone https://forgejo.home.arpa/Humberto/qbit-guardian.git
cd qbit-guardian
```

Se não tiver o `git` instalado, você pode baixar o projeto como um arquivo `.zip` pelo navegador e extrair.

### Passo 2: Prepare o ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **📘 Ambiente virtual (venv):** É uma pasta isolada onde o Python instala bibliotecas só para este projeto. Funciona como uma gaveta separada — não bagunça o resto do sistema.

### Passo 3: Crie o arquivo de configuração

```bash
cp config.json.example config.json
```

Abra o `config.json` em qualquer editor de texto e preencha:

- `qbit.host`: IP ou nome do computador com qBittorrent.
- `qbit.api_key`: a chave da API que você copiou do qBittorrent.

Os outros campos são opcionais e podem ser preenchidos depois pela página de controle.

### Passo 4: Execute o programa

```bash
python app/app.py
```

O terminal vai mostrar mensagens como:

```
qbit-guardian iniciando...
Conectado ao qBittorrent v5.0.0
Guardian iniciado. Intervalo: 300s
Web UI em http://0.0.0.0:5000
```

O programa fica rodando em primeiro plano. Para parar, pressione `Ctrl+C`.

> 💡 Para manter rodando mesmo depois de fechar o terminal, você pode usar ferramentas como `tmux`, `screen` ou criar um serviço systemd. Esses tópicos estão bem documentados na internet.

---

## Verificando se está funcionando

### Teste 1: Acesse a página de controle

Abra o navegador e vá para `http://endereco-do-servidor:5000`. Você deve ver a tela de configuração.

### Teste 2: Verifique o healthcheck

Acesse (ou use o comando abaixo):

```bash
curl http://endereco-do-servidor:5000/api/health
```

A resposta deve ser:

```json
{"status": "ok"}
```

### Teste 3: Veja os logs

- **Docker:** `docker logs qbit-guardian`
- **Manual:** as mensagens aparecem direto no terminal.

Você deve ver algo como `Conectado ao qBittorrent v...` — isso indica que a conexão com o qBittorrent está funcionando.

### Teste 4: Force uma verificação

Na página de controle, clique em **Forçar verificação** (ou use o comando abaixo se tiver autenticação configurada):

```bash
curl -X POST http://endereco-do-servidor:5000/api/trigger
```

Se a resposta for `{"status": "ok", "checked": ..., "new": ...}`, está tudo funcionando.

---

## Próximos passos

Depois de instalado e funcionando:

1. Acesse a página `http://seu-servidor:5000` e revise as configurações.
2. Se quiser, ative as [notificações](USAGE.md#ativando-notificações) e a [autenticação com senha](USAGE.md#protegendo-a-página-com-senha).
3. Leia o [Guia de Uso](USAGE.md) para entender todos os recursos.

---

## Problemas na instalação?

| Problema | Solução |
|---------|---------|
| "Connection refused" ou "Falha ao conectar no qBit" | Verifique se o qBittorrent está rodando e se o host/porta estão corretos. No Docker, `localhost` dentro do container NÃO é o mesmo da sua máquina — use `host.docker.internal` (Windows/Mac) ou o IP real (Linux). |
| "HTTP 403" ou "Unauthorized" | A API Key está errada. Confira no qBittorrent em **Ferramentas → Opções → Web UI** e cole exatamente. |
| Página não abre na porta 5000 | Confira se o container está rodando (`docker ps`). Na instalação manual, veja se o terminal mostra a mensagem "Web UI em http://...". Verifique se o firewall libera a porta 5000. |
| Porta 5000 já está em uso | Altere o mapeamento no docker-compose (ex: `"5001:5000"`) ou use a variável `PORT` na instalação manual. |

Se o problema persistir, consulte as [Perguntas Frequentes](FAQ.md).
