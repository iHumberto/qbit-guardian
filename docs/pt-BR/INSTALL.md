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

### Passo 1: Crie a pasta de configuração

Crie uma pasta para o qbit-guardian. Por exemplo, `/home/usuario/docker/qbit-guardian/`. Dentro dela, crie uma subpasta `config` e ajuste o dono:

```bash
mkdir -p config
sudo chown -R 1000:1000 config
```

> ⚠️ **O `chown` é obrigatório.** O container roda como usuário sem privilégio (UID 1000), por segurança. Sem o ajuste de dono, ele não consegue gravar e sai na hora — imprimindo esse mesmo comando no log.

**Você não precisa criar nenhum arquivo de configuração.** O `config.json` é gerado automaticamente na primeira execução, com valores padrão.

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
      - ./config:/app/config
    environment:
      - LOG_LEVEL=ERROR
    restart: unless-stopped
```

O que cada linha faz:

| Linha | Explicação |
|-------|-----------|
| `image: ghcr.io/...` | Baixa a imagem do programa pronta para uso. |
| `ports: "5000:5000"` | Torna a página de controle acessível na porta 5000. |
| `volumes: ./config:/app/config` | Conecta a pasta `config` da sua máquina com a do container. Assim a configuração sobrevive a atualizações. |
| `environment: LOG_LEVEL=ERROR` | Nível de detalhe do log. Opções: `ERROR`, `INFO`, `VERBOSE`, `DEBUG`. |
| `restart: unless-stopped` | Se o container parar por algum motivo, o Docker reinicia automaticamente. |

> 💡 **Healthcheck:** não precisa declarar. A imagem já traz um, que verifica se o loop do guardião continua vivo comparando a idade do arquivo de heartbeat com o intervalo configurado.

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

### Passo 4: Pegue a senha de acesso

A Web UI exige login. Na primeira subida o guardião **gera a senha sozinho** e a imprime no log:

```bash
docker logs qbit-guardian
```

Você verá um bloco como este:

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================
```

> ⚠️ **Essa senha aparece uma vez só**, no momento em que é criada. Copie e guarde agora.

Depois você troca por uma de sua escolha: no painel, clique no **ícone de usuário** (canto superior direito) e informe a senha atual mais a nova.

> **Esqueceu a senha?** Abra o `config.json` na pasta `config`, apague o conteúdo do campo `webui.password` (deixando `""`) e reinicie o container. Uma senha nova é gerada e anunciada no log.

### Atualizando o qbit-guardian

Quando sair uma nova versão, atualize com:

```bash
docker compose pull qbit-guardian
docker compose up -d qbit-guardian
```

Sua configuração (pasta `config`) é preservada — só o programa é atualizado.

---

## Opção 2: Instalação manual (sem Docker)

Use esta opção se você não usa Docker ou prefere rodar o programa diretamente. Você vai precisar do **Python 3.10 ou superior** instalado.

### Passo 1: Baixe o projeto

```bash
git clone https://github.com/iHumberto/qbit-guardian.git
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

### Passo 3: Execute o programa

```bash
python -m app.main
```

> ⚠️ Use `python -m app.main`, com o `-m`. Rodar `python app/main.py` falha com `ModuleNotFoundError: No module named 'app'`, porque o Python não encontra a pasta do projeto.

**Nenhum arquivo de configuração precisa ser criado antes.** O `config.json` é gerado na raiz do projeto na primeira execução.

O terminal vai mostrar mensagens como:

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================

qbit-guardian iniciando...
Conectado ao qBittorrent v5.0.0
Guardian iniciado. Intervalo: 300s
Web UI em http://0.0.0.0:5000
```

O programa fica rodando em primeiro plano. Para parar, pressione `Ctrl+C`.

> 💡 Para manter rodando mesmo depois de fechar o terminal, você pode usar ferramentas como `tmux`, `screen` ou criar um serviço systemd. Esses tópicos estão bem documentados na internet.

### Mudando onde fica o config.json

Por padrão, na instalação manual o arquivo fica na raiz do projeto. Para escolher outro lugar, use a variável `CONFIG_PATH`:

```bash
CONFIG_PATH=/etc/qbit-guardian/config.json python -m app.main
```

---

## Verificando se está funcionando

### Teste 1: Acesse a página de controle

Abra o navegador e vá para `http://endereco-do-servidor:5000`. Você será levado à **tela de login**. Entre com `admin` e a senha que apareceu no log.

### Teste 2: Verifique o healthcheck

Este endpoint é público — não precisa de senha:

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

> 💡 Com `LOG_LEVEL=ERROR` (o padrão) o log é bem silencioso. Para ver mais, use `LOG_LEVEL=INFO` ou `LOG_LEVEL=VERBOSE`.

### Teste 4: Force uma verificação

Na página de controle, clique em **Forçar verificação**. Ou pela linha de comando, informando usuário e senha:

```bash
curl -X POST http://endereco-do-servidor:5000/api/trigger \
  -u admin:sua-senha
```

Se a resposta for `{"status": "ok", "checked": ..., "new": ..., "stalled_removed": ...}`, está tudo funcionando.

---

## Configurando o Webhook (tempo real)

O webhook permite que o qBittorrent avise o guardião no exato momento em que um torrent é adicionado — sem esperar o próximo ciclo de verificação. É a opção mais rápida.

> ⚠️ O script de webhook é **não-bloqueante**: ele não trava o qBittorrent. O script principal retorna em menos de 4 milissegundos — o qBittorrent continua funcionando normalmente enquanto a verificação acontece em segundo plano.

### Passo 1: Monte o script no container do qBittorrent

O script `qbit-guardian-hook.sh` está na pasta `scripts/` do repositório. Adicione este volume ao serviço `qbittorrent` no seu `docker-compose.yml`:

```yaml
services:
  qbittorrent:
    # ... suas configurações atuais ...
    volumes:
      - ./qbit-guardian/scripts/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh:ro
```

> 💡 O `:ro` no final significa "read-only" (somente leitura) — o container pode executar o script, mas não pode modificá-lo.

### Passo 2: Informe as credenciais ao script

O `/api/trigger` exige autenticação. Sem credenciais o guardião responde `401` e o webhook não funciona. Adicione as variáveis no serviço do qBittorrent:

```yaml
services:
  qbittorrent:
    environment:
      - QBIT_GUARDIAN_URL=http://qbit-guardian:5000
      - QBIT_GUARDIAN_USER=admin
      - QBIT_GUARDIAN_PASS=a-senha-da-web-ui
```

| Variável | Para que serve |
|----------|---------------|
| `QBIT_GUARDIAN_URL` | Onde o guardião está. O padrão `http://qbit-guardian:5000` funciona se os dois containers estão na mesma rede Docker. Para acesso por IP: `http://192.168.1.100:5000`. |
| `QBIT_GUARDIAN_USER` | Usuário da Web UI. Padrão: `admin`. |
| `QBIT_GUARDIAN_PASS` | Senha da Web UI. **Obrigatória.** |

> 💡 Se você trocar a senha pelo painel, lembre de atualizar `QBIT_GUARDIAN_PASS` aqui também.

### Passo 3: Configure o qBittorrent

1. No qBittorrent, vá em **Ferramentas → Opções → Downloads**.
2. Em **Executar programa externo ao adicionar torrent**, cole:

```
/scripts/qbit-guardian-hook.sh
```

3. Clique em **Salvar**.

### Passo 4: Ajuste o intervalo para zero

Na página de controle do qbit-guardian, defina o **Intervalo de verificação** como `0`. Isso desativa o modo polling e ativa o modo webhook.

Pronto. A partir de agora, todo torrent adicionado será verificado instantaneamente.

### Como o script evita travamentos

- **Sleep de 10 segundos:** evita que o guardião tente verificar o torrent antes de ele estar registrado no qBittorrent (race condition).
- **Timeouts no curl:** conexão tem limite de 5 segundos, operação completa de 10 segundos. Se o guardião não responder, o script não trava.
- **Execução em segundo plano:** o script principal termina em ~4 ms. O qBittorrent não espera a verificação terminar.
- **Tentativa extra:** se a primeira chamada falhar, o script tenta de novo após 5 segundos.
- **Falha reportada:** se as duas tentativas falharem, o script escreve no stderr do qBittorrent em vez de desistir em silêncio. Se o motivo for a falta de senha, ele diz isso.

---

## Próximos passos

Depois de instalado e funcionando:

1. Acesse a página `http://seu-servidor:5000`, entre com a senha do log e revise as configurações.
2. Troque a senha pelo **ícone de usuário** no canto superior direito.
3. Se quiser, ative as [notificações](USAGE.md#ativando-notificações).
4. Leia o [Guia de Uso](USAGE.md) para entender todos os recursos.

---

## Problemas na instalação?

| Problema | Solução |
|---------|---------|
| Container sai logo depois de subir, com mensagem sobre permissão | A pasta `config` pertence ao root. Rode `sudo chown -R 1000:1000 ./config` e suba de novo. O próprio log imprime esse comando. |
| "Connection refused" ou "qBittorrent indisponivel" | Verifique se o qBittorrent está rodando e se a URL está correta. No Docker, `localhost` dentro do container NÃO é o mesmo da sua máquina — use `host.docker.internal` (Windows/Mac) ou o IP real (Linux). |
| "qBittorrent: HTTP 403" | A API Key está errada. Confira no qBittorrent em **Ferramentas → Opções → Web UI** e cole exatamente. |
| Não sei a senha da Web UI | Rode `docker logs qbit-guardian` e procure o bloco de credenciais. Se o log já rolou demais, apague o valor de `webui.password` no `config.json` e reinicie — uma senha nova é gerada. |
| Login responde "Tentativas demais" | São 5 tentativas erradas em 5 minutos. Espere alguns minutos — o bloqueio vale até para a senha certa. |
| `ModuleNotFoundError: No module named 'app'` | Na instalação manual, use `python -m app.main` (com `-m`), a partir da pasta do projeto. |
| Página não abre na porta 5000 | Confira se o container está rodando (`docker ps`). Na instalação manual, veja se o terminal mostra "Web UI em http://...". Verifique se o firewall libera a porta 5000. |
| Porta 5000 já está em uso | Altere o mapeamento no docker-compose (ex: `"5001:5000"`). Na instalação manual, a porta é fixa em 5000 — use um proxy reverso se precisar de outra. |
| Webhook parou de funcionar | O `/api/trigger` exige autenticação. Confira `QBIT_GUARDIAN_PASS` no serviço do qBittorrent; o script avisa no stderr quando falta. |

Se o problema persistir, consulte as [Perguntas Frequentes](FAQ.md).
