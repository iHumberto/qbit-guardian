# Perguntas Frequentes (FAQ)

> Respostas diretas para as dúvidas mais comuns sobre o qbit-guardian.

---

## Por que um torrent não foi removido?

Existem alguns motivos para um torrent continuar ativo mesmo depois de passar pelo guardião:

**1. O torrent já está completo.** Torrents que já terminaram de baixar e estão apenas enviando (status: uploading, seeding) **não são removidos**. O guardião entende que esses torrents já foram analisados e estão ok — você já tem os arquivos, não faz sentido apagá-los.

**2. O torrent já foi processado antes.** O guardião mantém uma lista dos torrents que já analisou. Se ele já passou pelo guardião em uma verificação anterior e não foi considerado problemático, não será verificado de novo.

**3. O tempo de stalled/sem seeds ainda não foi atingido.** Se você configurou remoção de stalled para "6 horas", um torrent que está parado há apenas 3 horas ainda não será removido. Aguarde o tempo definido.

**4. O arquivo perigoso não está na lista.** Verifique se a extensão do arquivo está na lista de **extensões perigosas** na página de configuração. Se não estiver, o guardião não vai removê-lo.

**5. O intervalo de verificação ainda não passou.** No modo polling, o guardião só verifica a cada N segundos. Um torrent adicionado agora só será analisado na próxima rodada.

---

## Como ativar a autenticação na página de controle?

Na página de configuração (`http://seu-servidor:5000`), vá até a seção **Autenticação** e preencha:

- **Usuário:** um nome de sua escolha (ex: `admin`).
- **Senha:** escolha uma senha forte.

Clique em **Salvar Configurações**. A partir desse momento, o navegador vai pedir usuário e senha sempre que alguém acessar a página.

Se preferir editar o arquivo diretamente, adicione no `config.json`:

```json
{
  "webui": {
    "user": "admin",
    "password": "uma-senha-forte"
  }
}
```

> ⚠️ Se esquecer a senha, edite o `config.json` e apague os campos `user` e `password` (ou deixe-os em branco). A página volta a ficar pública e você pode definir uma senha nova.

Para desativar a autenticação, basta deixar **ambos** os campos em branco.

---

## O que são extensões perigosas? Posso personalizar?

**Extensões perigosas** são terminações de arquivo (`.exe`, `.scr`, `.bat`, etc.) conhecidas por serem usadas para espalhar vírus e programas maliciosos. Se o qbit-guardian encontra qualquer arquivo com uma dessas extensões dentro de um torrent, ele remove o torrent inteiro na hora.

A lista padrão é:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

**Sim, você pode personalizar.** Na página de configuração, na seção **Guardian**, você encontra o campo **Extensões perigosas**. Adicione ou remova extensões conforme sua necessidade.

Exemplos de quando personalizar:

- Você baixa jogos e confia em `.exe` de certas fontes → remova `.exe` da lista.
- Quer proteção extra contra `.iso` mascarado → adicione `.iso` à lista.
- Quer bloquear `.zip` e `.rar` que podem conter vírus → adicione à lista.

> ⚠️ **Atenção:** Ao remover `.exe` da lista, você perde a proteção principal do guardião. Arquivos executáveis são o veículo mais comum de vírus em torrents. Só faça isso se tiver absoluta certeza do que está fazendo.

---

## Qual a diferença entre polling e webhook?

São duas formas de o guardião saber que um torrent novo chegou:

| | Polling (padrão) | Webhook |
|---|---|---|
| **Como funciona** | O guardião verifica os torrents a cada X segundos. | O qBittorrent avisa o guardião no exato momento em que um torrent é adicionado. |
| **Velocidade** | Depende do intervalo. Com 300s, um torrent perigoso pode ficar até 5 minutos ativo. | Instantâneo. |
| **Configuração** | Basta definir o intervalo. | Precisa configurar o qBittorrent e montar um script. |
| **Uso de recursos** | Constante, mas leve. | Mínimo — só age quando acionado. |
| **Melhor para** | A maioria dos usuários. Intervalo de 5 minutos é suficiente. | Quem quer máxima segurança e resposta imediata. |

**Resumo prático:**
- Se você não quer complicar, use polling com intervalo de 300 segundos (padrão). Funciona bem.
- Se quer que um `.exe` seja removido no mesmo segundo em que o torrent é adicionado, use webhook.

Para configurar o webhook, veja a seção [Modo Webhook](USAGE.md#modo-webhook-tempo-real) do Guia de Uso.

---

## Preciso de Sonarr ou Radarr para usar o qbit-guardian?

**Não.** O Sonarr e o Radarr são completamente opcionais.

O qbit-guardian funciona perfeitamente sem eles. Você ainda terá:

- ✅ Remoção de torrents com arquivos perigosos.
- ✅ Remoção de torrents parados (stalled).
- ✅ Remoção de torrents sem seeds.
- ✅ Otimização de prioridades de download.
- ✅ Notificações via Apprise.

A única coisa que você **não** terá sem Sonarr/Radarr é o bloqueio automático do lançamento ruim e a re-busca por uma versão alternativa — porque essas funções dependem das APIs do Sonarr e Radarr.

Para desativar a integração, deixe os campos `host` do Sonarr e Radarr **em branco** na configuração.

---

## Como testar se o qbit-guardian está funcionando?

Use um destes métodos:

### Teste rápido: healthcheck

```bash
curl http://seu-servidor:5000/api/health
```

Resposta esperada: `{"status": "ok"}`. Isso confirma que o programa está rodando e respondendo.

### Teste real: força uma verificação

Na página de controle, clique em **Forçar verificação**. O guardião vai analisar todos os torrents ativos imediatamente.

Ou use o comando:

```bash
curl -X POST http://seu-servidor:5000/api/trigger
```

### Teste com um torrent de mentira

A forma mais confiável é adicionar um torrent que você sabe que será removido:

1. Encontre um torrent pequeno qualquer (um `.txt` ou `.pdf`, por exemplo).
2. Adicione no qBittorrent.
3. Aguarde o intervalo de verificação (ou clique em **Forçar verificação**).
4. Veja nos logs (`docker logs qbit-guardian`) se o torrent foi analisado.

Se não foi removido, verifique se o torrent já foi processado antes (o guardião não reprocessa torrents já analisados).

### Verificando os logs

```bash
# Docker
docker logs qbit-guardian

# Instalação manual: as mensagens aparecem no terminal
```

Procure por linhas como `Conectado ao qBittorrent v...` — isso indica que a conexão foi bem-sucedida. Se aparecer `Falha ao conectar no qBit`, há algo errado com o host, porta ou API Key.

---

## O qbit-guardian funciona com outros clientes de torrent?

**Não.** O qbit-guardian foi feito exclusivamente para o **qBittorrent**.

Ele usa a API do qBittorrent para listar torrents, ver arquivos, remover e ajustar prioridades — tudo isso é específico do qBittorrent. Outros clientes como Transmission, Deluge ou uTorrent têm APIs diferentes e não são compatíveis.

Se você usa outro cliente de torrent e gostaria de uma ferramenta parecida, considere migrar para o qBittorrent — ele é gratuito, de código aberto e tem uma das APIs mais completas entre os clientes de torrent.

---

## Como sei qual versão estou usando?

### Docker

```bash
docker inspect qbit-guardian | grep -i "image"
```

Você verá algo como `ghcr.io/ihumberto/qbit-guardian:latest` ou uma tag de versão específica.

### Instalação manual

Se você clonou o repositório com git:

```bash
cd qbit-guardian
git log -1 --oneline
```

Isso mostra o último commit, que indica a versão instalada.

---

## O qbit-guardian manda dados para a internet?

**Não.** Todo o processamento acontece localmente, dentro do seu servidor. O qbit-guardian não envia nenhum dado para servidores externos.

As únicas conexões de rede que ele faz são:

- Com o **qBittorrent** (na sua rede local) — para gerenciar os torrents.
- Com o **Sonarr/Radarr** (na sua rede local) — se você tiver integração ativada.
- Com o serviço de notificação configurado via **Apprise** — se você tiver configurado uma URL de notificação (Telegram, Discord, etc.).

Nenhum dado sobre seus torrents, sua biblioteca ou sua configuração sai do seu servidor.

---

## Posso instalar em um Raspberry Pi?

**Sim.** O qbit-guardian é leve e funciona bem em Raspberry Pi (modelos 3 e superiores) com Raspberry Pi OS.

Use a instalação Docker (a imagem está disponível para arquitetura ARM) ou a instalação manual com Python. O consumo de recursos é mínimo — o programa usa pouca memória e processador, mesmo no modo polling.

---

## O programa atualiza sozinho?

**Não automaticamente.** Você precisa atualizar manualmente:

- **Docker:** `docker compose pull qbit-guardian && docker compose up -d qbit-guardian`
- **Manual:** `git pull` dentro da pasta do projeto e reinicie o programa.

Recomendamos verificar por atualizações a cada 1-2 meses.

---

## Como faço backup da minha configuração?

Copie o arquivo `config.json` para um local seguro. É só isso — toda a configuração do qbit-guardian está nesse único arquivo.

Para restaurar, basta colocar o arquivo de volta no lugar e reiniciar o programa.

Se você usa Docker e montou o `config.json` como volume, ele já está fora do container, seguro na sua máquina.

---

## Posso contribuir com o projeto?

Sim. O projeto é **código aberto** (licença GPLv3). Você pode:

- Reportar problemas e sugerir melhorias.
- Enviar correções e novas funcionalidades.
- Melhorar a documentação.

O repositório está em: `https://forgejo.home.arpa/Humberto/qbit-guardian`

---

## Como remover completamente o qbit-guardian?

### Docker

```bash
docker compose down qbit-guardian
docker rmi ghcr.io/ihumberto/qbit-guardian:latest
```

Depois apague a pasta com o `config.json` e o bloco do serviço no `docker-compose.yml`.

### Instalação manual

```bash
# Pare o programa (Ctrl+C no terminal)
# Depois apague a pasta:
rm -rf /caminho/para/qbit-guardian
# E remova o ambiente virtual:
rm -rf /caminho/para/qbit-guardian/.venv
```

Nenhum arquivo é instalado fora da pasta do projeto — a remoção é completa.

---

## Ainda tem dúvidas?

- Consulte o [Guia de Uso](USAGE.md) para explicações detalhadas de cada funcionalidade.
- Veja o [Guia de Instalação](INSTALL.md) se precisar reinstalar ou atualizar.
- Abra uma issue no [repositório do projeto](https://forgejo.home.arpa/Humberto/qbit-guardian).
