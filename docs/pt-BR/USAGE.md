# Guia de Uso do qbit-guardian

> Aprenda a usar o qbit-guardian no dia a dia: configurar, entender os modos de operação e interpretar o que está acontecendo.

## O que é

O qbit-guardian é um vigia automático para os seus torrents. Depois de instalado e configurado, ele trabalha sozinho em segundo plano. Você só precisa acessar a página de configuração de vez em quando para ajustar alguma coisa.

---

## Acessando a página de controle

Abra o navegador e digite o endereço do servidor onde o qbit-guardian está rodando, sempre na porta **5000**:

```
http://endereco-do-seu-servidor:5000
```

Exemplos práticos:

- **No mesmo computador:** `http://localhost:5000`
- **Em outro computador da rede:** `http://192.168.1.100:5000`
- **Servidor com nome na rede:** `http://meu-servidor:5000`

Você verá a tela de configuração dividida em seções: **qBittorrent**, **Radarr**, **Sonarr**, **Guardian**, **Notificações** e **Autenticação**.

---

## Configuração essencial

Para o qbit-guardian começar a funcionar, apenas dois campos são obrigatórios:

| Campo | Onde encontrar |
|-------|---------------|
| **Host do qBittorrent** | IP ou nome do computador onde o qBittorrent está instalado |
| **API Key do qBittorrent** | No qBittorrent: **Ferramentas → Opções → Web UI → Chave da API** |

> **📘 API Key:** É uma senha longa e aleatória que o qBittorrent gera. Ela permite que outros programas (como o qbit-guardian) conversem com o qBittorrent de forma segura. Pense nela como uma chave de acesso que você entrega para um aplicativo de confiança.

Preencha esses dois campos, clique em **Salvar Configurações** e pronto — o guardião já está trabalhando.

### Integração com Sonarr e Radarr (opcional)

Se você usa o Sonarr (para séries) ou o Radarr (para filmes), preencha também os campos de **host**, **porta** e **API Key** dessas ferramentas.

Com essa integração ativa, sempre que o qbit-guardian remover um torrent problemático, ele também:
1. Bloqueia aquele lançamento no Sonarr/Radarr (para não baixar de novo).
2. Dispara uma nova busca automática por uma versão alternativa.

> 💡 Se você não usa Sonarr nem Radarr, deixe os campos em branco. O guardião funciona normalmente — só a parte de bloqueio e re-busca automática é ignorada.

### Ativando notificações

O qbit-guardian pode te avisar pelo celular ou computador sempre que uma ação importante acontecer. Para isso, ele usa o **Apprise** — um sistema que envia mensagens para mais de 100 serviços diferentes (Telegram, Discord, Slack, Pushover, e-mail e muitos outros).

> **📘 Apprise:** É como um carteiro universal. Você entrega uma única URL e ele se encarrega de entregar a mensagem no serviço que você escolheu — Telegram, Discord, e-mail, etc. Você não precisa instalar nada extra, só gerar a URL correta.

Para ativar, preencha o campo **Apprise URL** com o endereço gerado para o seu serviço. Exemplos de URLs Apprise:

| Serviço | Formato da URL |
|---------|---------------|
| Telegram | `tgram://TOKEN_DO_BOT/ID_DO_CHAT` |
| Discord | `discord://ID_DO_WEBHOOK` |
| Pushover | `pover://USER_KEY/APP_TOKEN` |

> Consulte a [lista completa de formatos](https://github.com/caronc/apprise#supported-notifications) na documentação oficial do Apprise.

Os eventos que geram notificação são:

- ⚠️ **Torrent removido por arquivo perigoso** (ex: `.exe`, `.scr`)
- ⚠️ **Torrent removido por não ter arquivo de mídia válido**
- 🗑️ **Torrent removido por estar parado há muito tempo** (stalled)
- 🗑️ **Torrent removido por não ter seeds**
- ⚡ **Torrent otimizado** (prioridades de arquivos ajustadas)

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

Neste modo, o qBittorrent avisa o guardião **no exato momento** em que um torrent é adicionado. O processamento é instantâneo — sem esperar o próximo ciclo de verificação.

Para usar este modo:

**1.** No campo **Intervalo de verificação**, coloque `0` (zero).

**2.** No qBittorrent, vá em **Ferramentas → Opções → Downloads** e localize o campo **Executar programa externo ao adicionar torrent**. Preencha com o caminho do script:

```
/scripts/qbit-guardian-hook.sh
```

**3.** Monte o script de webhook no container do qBittorrent. No seu `docker-compose.yml`, na parte do serviço do qBittorrent, adicione:

```yaml
volumes:
  - ./caminho/para/scripts/qbit-guardian-hook.sh:/scripts/qbit-guardian-hook.sh
```

> O script `qbit-guardian-hook.sh` já vem com o projeto, na pasta `scripts/`. Ele é bem simples: só avisa o guardião que um torrent novo chegou.

Pronto. A partir de agora, cada torrent adicionado é analisado imediatamente.

---

## Personalizando as regras

### Extensões perigosas

São as extensões de arquivo que, se encontradas dentro de um torrent, fazem o guardião remover tudo na hora. A lista padrão inclui os suspeitos de sempre:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

Você pode adicionar ou remover extensões na seção **Guardian** da página de configuração. Por exemplo, se você baixa jogos e confia em `.exe`, remova essa extensão da lista.

> ⚠️ Só faça isso se tiver certeza. Arquivos `.exe` são o principal veículo de vírus em torrents. Se remover, você perde a proteção principal do guardião.

### Extensões de mídia válidas

É a lista de formatos de vídeo que o guardião considera "conteúdo legítimo". Se um torrent não tiver **nenhum** arquivo com essas extensões, ele é tratado como suspeito e removido.

A lista padrão: `.mkv` `.mp4` `.avi` `.mov` `.m4v` `.ts` `.wmv` `.flv` `.webm`

Adicione ou remova formatos conforme sua preferência. Por exemplo, se você baixa ISOs de Blu-ray, adicione `.iso` e `.m2ts`.

### Remoção de torrents parados (stalled)

Um torrent "stalled" (parado) é aquele que não consegue baixar — seja porque as fontes sumiram, seja por problema de conexão.

Para ativar a limpeza automática:
- Marque **Remover stalled**.
- Defina há quantas **horas** ou **minutos** o torrent precisa estar parado para ser removido.

Exemplo: `6 horas` — o guardião remove torrents que estão parados há mais de 6 horas.

### Remoção de torrents sem seeds

Um torrent "sem seeds" é aquele onde ninguém está compartilhando o arquivo completo. Sem seeds, é impossível completar o download.

Para ativar:
- Marque **Remover sem seeds**.
- Defina o tempo mínimo de espera (ex: `24 horas`).

> 💡 **Seed** (ou semeador) é alguém que já baixou o arquivo inteiro e continua enviando para os outros. Se um torrent tem zero seeds, você jamais conseguirá completar o download — é como tentar copiar um livro que ninguém mais tem.

### Prioridades de arquivos

Quando um torrent tem vários tipos de arquivo, o guardião ajusta automaticamente a prioridade de download:

| Tipo de arquivo | Prioridade | O que acontece |
|----------------|-----------|---------------|
| Arquivos de mídia (`.mkv`, `.mp4`, etc.) | **Alta** (padrão: 7) | São baixados primeiro |
| Arquivos complementares (`.nfo`, `.srt`, `.jpg`) | **Normal** (padrão: 1) | Baixados depois |
| Outros arquivos | **Pular** (padrão: 0) | Nem são baixados |

Isso faz o download do filme ou episódio começar mais rápido e evita baixar arquivos inúteis. Os valores podem ser alterados nos campos **Prioridade mídia**, **Prioridade normal** e **Prioridade pular**.

---

## Protegendo a página com senha

Por padrão, a página de configuração não tem senha — qualquer pessoa na sua rede pode acessá-la.

Para proteger, na seção **Autenticação** da página, preencha:

- **Usuário:** um nome de sua escolha (ex: `admin`).
- **Senha:** uma senha forte (ex: `M1nh4S3nh4F0rt3!`).

Salve. Na próxima vez que acessar, o navegador vai pedir usuário e senha.

> ⚠️ Se esquecer a senha, edite o arquivo `config.json` diretamente e apague os campos `user` e `password`. A autenticação será desativada e a página ficará pública de novo. Depois você pode definir uma senha nova pela própria página.

Se ambos os campos (`user` e `password`) estiverem vazios, a autenticação fica desativada e a página volta a ser pública.

---

## Entendendo o que aparece nos logs

O qbit-guardian registra tudo que faz. Você pode ver os logs de duas formas:

- **Docker:** `docker logs qbit-guardian`
- **Instalação manual:** direto no terminal onde o programa está rodando

Veja o que cada mensagem significa:

| Mensagem no log | O que aconteceu |
|----------------|-----------------|
| `Arquivos perigosos: ['.exe'] — Removendo e Bloqueando` | O torrent continha um `.exe` e foi removido. Se Sonarr/Radarr estiverem configurados, o lançamento foi bloqueado e uma nova busca iniciada. |
| `Nenhum arquivo de midia valido — Removendo e Bloqueando` | O torrent não tinha nenhum arquivo com as extensões de mídia configuradas. Foi removido. |
| `stalled por >6h — Removendo` | O torrent estava parado há mais de 6 horas. Removido. |
| `0 seeds — Removendo` | O torrent estava sem seeds pelo tempo configurado. Removido. |
| `Desativado → nome-do-arquivo.exe` | Um arquivo dentro do torrent foi marcado como prioridade zero — não será baixado. |
| `Arquivos de midia priorizados` | As prioridades de download foram ajustadas. Os arquivos de vídeo foram colocados no topo da fila. |
| `Nenhum torrent novo` | O guardião verificou e não encontrou torrents que ainda não tivesse processado. Tudo em ordem. |
| `qBittorrent inacessivel, reconectando...` | O guardião perdeu contato com o qBittorrent. Ele tenta reconectar automaticamente a cada ciclo. |

### Status dos torrents processados

O guardião mantém uma lista interna dos torrents que já analisou. Isso evita que um mesmo torrent seja reprocessado várias vezes. Os status possíveis:

| Status | Descrição |
|--------|-----------|
| **completed** | Torrents que já terminaram de baixar e estão enviando (uploading/seeding). O guardião **não mexe** neles — já estão prontos. |
| **dangerous** | Torrents que continham arquivos perigosos. Já foram removidos. |
| **stalled** | Torrents que foram removidos por estarem parados tempo demais. |
| **no_seeds** | Torrents removidos por falta de seeds. |
| **no_media** | Torrents removidos por não conterem arquivos de mídia válidos. |
| **optimized** | Torrents onde as prioridades de arquivos foram ajustadas. Continuam baixando normalmente. |

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

- **Teste primeiro sem notificações.** Deixe o guardião rodar alguns dias em silêncio. Depois que estiver confiante no comportamento, ative as notificações.
- **Intervalo de 5 minutos é suficiente.** Para uso doméstico, checar a cada 300 segundos é rápido o bastante. Não precisa colocar 10 segundos — você não vai notar diferença e só gasta recursos.
- **Mantenha as extensões perigosas atualizadas.** De tempos em tempos, aparecem novos tipos de arquivo usados para espalhar vírus. Fique de olho.
- **Se usa Sonarr/Radarr, aproveite a integração.** Preencher os campos de integração faz o guardião bloquear lançamentos ruins e buscar alternativas automaticamente. Sua biblioteca cresce sem você precisar fazer nada.

---

## Precisa de ajuda?

- Leia as [Perguntas Frequentes](FAQ.md) para dúvidas comuns.
- Veja o [Guia de Instalação](INSTALL.md) se precisar instalar do zero.
- Problemas, sugestões e contribuições: [repositório do projeto](https://forgejo.home.arpa/Humberto/qbit-guardian).
