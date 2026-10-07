# Perguntas Frequentes (FAQ)

> Respostas diretas para as dúvidas mais comuns sobre o qbit-guardian.

---

## Por que a página agora pede senha?

A partir da **versão 2.2.0** a Web UI exige autenticação, sempre. Antes ela vinha pública por padrão, e isso era um problema sério: a porta 5000 fica exposta na rede, e o `GET /api/config` devolvia em texto claro as API Keys do qBittorrent, do Sonarr e do Radarr, além da URL do Apprise — que costuma embutir o token do seu bot do Telegram.

Não existe tela de cadastro. Na primeira execução o guardião **gera a senha sozinho** e a imprime no log:

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

Se você **já tinha** `webui.user` e `webui.password` preenchidos antes de atualizar, nada muda: a senha que você usava continua valendo e é convertida para hash no primeiro startup.

---

## Como troco o usuário ou a senha?

No painel, clique no **ícone de usuário** no canto superior direito. O popup pede:

- **Usuário** — só se quiser mudar o nome.
- **Senha atual** — sempre, é a prova de identidade.
- **Nova senha** — só se quiser trocar a senha (mínimo 8 caracteres).

Deixe em branco o que não quiser alterar. Depois de salvar, você volta para a tela de login, porque a troca encerra todas as sessões abertas.

Pela linha de comando:

```bash
curl -X POST http://seu-servidor:5000/api/credentials \
  -u admin:senha-atual \
  -H "Content-Type: application/json" \
  -d '{"current_password": "senha-atual", "new_password": "senha-nova-forte"}'
```

---

## Esqueci a senha. E agora?

Abra o `config.json` (na pasta `config`, se você usa Docker), deixe o campo `webui.password` vazio e reinicie:

```json
{
  "webui": {
    "user": "admin",
    "password": ""
  }
}
```

```bash
docker compose restart qbit-guardian
docker logs qbit-guardian
```

Uma senha nova é gerada e anunciada no log.

---

## O login diz "Tentativas demais". O que é isso?

Proteção contra força bruta: **5 tentativas erradas em 5 minutos** bloqueiam aquele cliente, e o bloqueio vale **até para a senha certa** — senão bastaria errar quatro vezes e acertar na quinta sem custo nenhum.

Espere alguns minutos e tente de novo. A contagem é por cliente, então outras pessoas na rede não são afetadas.

---

## Posso deixar a página pública de novo?

Dá, mas pense duas vezes: a página expõe as suas API Keys.

Deixe `webui.user` e `webui.password` **ambos vazios** no `config.json`. A autenticação é desligada enquanto estiverem assim.

> ⚠️ O próximo restart do container gera uma senha nova e religa a autenticação. O escape hatch existe para quem já protege a porta por outro meio — um proxy reverso com SSO, por exemplo —, não para uso permanente.

---

## O container sai logo depois de subir, falando de permissão

A partir da **versão 2.2.0** o container roda como usuário sem privilégio (UID 1000), em vez de root. Se a pasta `config` foi criada por uma versão antiga, ela pertence ao root e o processo não consegue gravar.

O próprio log imprime o conserto:

```bash
sudo chown -R 1000:1000 ./config
docker compose up -d qbit-guardian
```

É um comando só, e só precisa ser feito uma vez.

---

## O webhook parou de funcionar depois de atualizar

O `/api/trigger` passou a exigir autenticação. Sem credenciais o guardião responde `401` e o script não tem como avisar que um torrent chegou.

Adicione as variáveis no serviço do **qBittorrent** no `docker-compose.yml`:

```yaml
services:
  qbittorrent:
    environment:
      - QBIT_GUARDIAN_URL=http://qbit-guardian:5000
      - QBIT_GUARDIAN_USER=admin
      - QBIT_GUARDIAN_PASS=a-senha-da-web-ui
```

O script escreve no stderr do qBittorrent quando falha, inclusive dizendo se o motivo foi a falta de senha.

> 💡 Se trocar a senha pelo painel, atualize `QBIT_GUARDIAN_PASS` também.

---

## Por que um torrent não foi removido?

Existem alguns motivos para um torrent continuar ativo mesmo depois de passar pelo guardião:

**1. O torrent já está completo.** Torrents que terminaram de baixar e estão semeando (`uploading`, `stalledUP`, `pausedUP`, `checkingUP`, `queuedUP`) **não são tocados**. Você já tem os arquivos — não faz sentido apagá-los.

**2. O torrent já foi processado antes.** O guardião mantém uma lista dos torrents que já analisou. Se ele passou numa verificação anterior e não foi considerado problemático, não é reanalisado quanto a arquivos perigosos.

> As regras de **stalled** e **sem seeds**, porém, são reavaliadas em todo ciclo, inclusive para torrents já processados. Um torrent que travou depois continua sendo pego.

**3. O tempo de stalled/sem seeds ainda não foi atingido.** Se você configurou "6 horas", um torrent parado há 3 horas ainda não será removido.

**4. O tempo está em `0`.** Zero significa **desligado**, não "remover agora".

**5. A extensão não está na lista.** Verifique se ela está em **Extensões perigosas** no painel.

**6. O intervalo ainda não passou.** No modo polling, o guardião só verifica a cada N segundos. Use **Forçar verificação** para não esperar.

**7. O magnet ainda não trouxe os arquivos.** Um torrent sem metadados não pode ser analisado. Ele é reavaliado no próximo ciclo — o log mostra `sem metadados — sera reavaliado no proximo ciclo`.

---

## O que são extensões perigosas? Posso personalizar?

**Extensões perigosas** são terminações de arquivo (`.exe`, `.scr`, `.bat`, etc.) conhecidas por serem usadas para espalhar vírus. Se o qbit-guardian encontra qualquer arquivo com uma dessas extensões dentro de um torrent, ele remove o torrent inteiro na hora — **com os arquivos do disco**.

A lista padrão é:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

**Sim, você pode personalizar.** Na seção **Guardian** do painel, edite o campo **Extensões perigosas**, uma por linha.

Exemplos de quando personalizar:

- Você baixa jogos e confia em `.exe` de certas fontes → remova `.exe` da lista.
- Quer proteção extra contra `.iso` mascarado → adicione `.iso` à lista.
- Quer bloquear `.zip` e `.rar` que podem conter vírus → adicione à lista.

> ⚠️ **Atenção:** Ao remover `.exe` da lista, você perde a proteção principal do guardião. Arquivos executáveis são o veículo mais comum de vírus em torrents.

---

## E se eu deixar a lista de extensões de mídia vazia?

O critério "nenhum arquivo de mídia válido" fica **desligado**: nenhum torrent é removido por esse motivo. A detecção de extensões perigosas continua normal.

É útil se você baixa coisas que não são vídeo (documentos, software, música) e não quer que o guardião trate isso como suspeito.

---

## Qual a diferença entre polling e webhook?

| | Polling | Webhook |
|---|---------|---------|
| **Como funciona** | O guardião verifica de tempos em tempos | O qBittorrent avisa na hora que o torrent é adicionado |
| **Velocidade** | Até N segundos de atraso | Imediato |
| **Configuração** | Só o intervalo no painel | Script montado no qBittorrent + credenciais |
| **Quando usar** | Uso geral, mais simples | Quando quer remoção instantânea |

Para ativar o webhook, coloque `0` no **Intervalo de verificação** e siga o passo a passo em [Configurando o Webhook](INSTALL.md#configurando-o-webhook-tempo-real).

> 💡 No modo webhook o guardião não roda ciclos periódicos — ele só responde a chamadas. O healthcheck sabe disso e não acusa problema.

---

## Preciso de Sonarr ou Radarr para usar o qbit-guardian?

**Não.** São opcionais.

Sem eles, o guardião ainda remove arquivos perigosos, torrents parados e sem seeds, e ajusta prioridades. O que você perde é o bloqueio do lançamento e a busca automática por uma versão alternativa.

Para desativar a integração, deixe os campos **URL** do Sonarr e do Radarr **em branco** na configuração.

---

## Como testar se o qbit-guardian está funcionando?

### Teste rápido: healthcheck

```bash
curl http://seu-servidor:5000/api/health
```

Resposta esperada: `{"status": "ok"}`. Este endpoint é **público** — não precisa de senha, porque é ele que o Docker usa.

### Teste real: force uma verificação

Na página de controle, clique em **Forçar verificação**. Ou pela linha de comando, com usuário e senha:

```bash
curl -X POST http://seu-servidor:5000/api/trigger -u admin:sua-senha
```

A resposta traz o que foi feito:

```json
{"status": "ok", "checked": 30, "new": 2, "stalled_removed": 1}
```

### Verificando os logs

```bash
# Docker
docker logs qbit-guardian

# Instalação manual: as mensagens aparecem no terminal
```

Procure por `Conectado ao qBittorrent v...` — isso indica que a conexão foi bem-sucedida. Se aparecer `qBittorrent indisponivel`, há algo errado com a URL ou a API Key.

> 💡 Com `LOG_LEVEL=ERROR` (o padrão) o log é bem silencioso. Para investigar, suba temporariamente para `LOG_LEVEL=INFO` ou `VERBOSE`.

---

## O qbit-guardian funciona com outros clientes de torrent?

**Não.** Ele foi feito exclusivamente para o **qBittorrent**.

Ele usa a API do qBittorrent para listar torrents, ver arquivos, remover e ajustar prioridades — tudo específico desse cliente. Transmission, Deluge e uTorrent têm APIs diferentes e não são compatíveis.

Há espaço para evolução futura. Se tem interesse, fique de olho nas releases ou contribua.

---

## Como sei qual versão estou usando?

### Docker

```bash
docker inspect qbit-guardian --format '{{.Config.Image}}'
```

Você verá algo como `ghcr.io/ihumberto/qbit-guardian:latest` ou uma tag específica.

### Instalação manual

```bash
cd qbit-guardian
git log -1 --oneline
```

Em qualquer caso, o [CHANGELOG](https://github.com/iHumberto/qbit-guardian/blob/main/CHANGELOG.md) lista o que mudou em cada versão.

---

## O qbit-guardian manda dados para a internet?

**Não.** Todo o processamento acontece localmente, dentro do seu servidor.

As únicas conexões de rede que ele faz são:

- Com o **qBittorrent** (na sua rede local) — para gerenciar os torrents.
- Com o **Sonarr/Radarr** (na sua rede local) — se você tiver integração ativada.
- Com o serviço de notificação configurado via **Apprise** — só se você configurar uma URL.

Nenhum dado sobre seus torrents, sua biblioteca ou sua configuração sai do seu servidor. A própria Web UI não carrega nada de fora: fontes, traduções e ícones vêm todos da aplicação, então o painel abre mesmo sem internet.

---

## Posso instalar em um Raspberry Pi?

**Sim.** O qbit-guardian é leve e funciona bem em Raspberry Pi (modelos 3 e superiores).

A imagem é multi-arquitetura, então o `docker compose pull` baixa a versão ARM automaticamente. O consumo de recursos é mínimo.

---

## O programa atualiza sozinho?

**Não por conta própria.** Você atualiza assim:

- **Docker:** `docker compose pull qbit-guardian && docker compose up -d qbit-guardian`
- **Manual:** `git pull` dentro da pasta do projeto e reinicie.

> 💡 Se você usa **Watchtower** ou similar, a atualização acontece automática. Nesse caso, fique atento às notas de versão: a 2.2.0, por exemplo, exigiu um `chown` na pasta `config`.

---

## Como faço backup da minha configuração?

Copie o `config.json` para um lugar seguro. É só isso — toda a configuração está nesse único arquivo.

```bash
cp config/config.json ~/backup-qbit-guardian.json
```

Para restaurar, coloque o arquivo de volta e reinicie o programa.

> ⚠️ O backup contém as suas **API Keys** e o hash da senha da Web UI. Guarde com o mesmo cuidado que teria com uma senha.

---

## Posso contribuir com o projeto?

Sim. O projeto é **código aberto** (licença GPLv3). Você pode:

- Reportar problemas e sugerir melhorias.
- Enviar correções e novas funcionalidades.
- Melhorar a documentação.

O repositório está em: <https://github.com/iHumberto/qbit-guardian>

---

## Como remover completamente o qbit-guardian?

### Docker

```bash
docker compose down qbit-guardian
docker rmi ghcr.io/ihumberto/qbit-guardian:latest
```

Depois apague a pasta `config` e o bloco do serviço no `docker-compose.yml`. Se você configurou o webhook, remova também o volume do script e as variáveis `QBIT_GUARDIAN_*` do serviço do qBittorrent, e limpe o campo **Executar programa externo** nas opções do qBittorrent.

### Instalação manual

```bash
# Pare o programa (Ctrl+C no terminal)
rm -rf /caminho/para/qbit-guardian
```

Nenhum arquivo é instalado fora da pasta do projeto — a remoção é completa.

---

## Ainda tem dúvidas?

- Consulte o [Guia de Uso](USAGE.md) para explicações detalhadas de cada funcionalidade.
- Veja o [Guia de Instalação](INSTALL.md) se precisar reinstalar ou atualizar.
- Abra uma issue no [repositório do projeto](https://github.com/iHumberto/qbit-guardian).
