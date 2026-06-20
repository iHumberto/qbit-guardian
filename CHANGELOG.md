# Changelog

Todas as mudancas notaveis deste projeto serao documentadas neste arquivo.

O formato e baseado no [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
e o projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Modificado
- Layout da Web UI refinado: container ampliado (+15% width, max-width: 1035px); gap entre colunas de 30px; coluna do Guardian estica verticalmente para mesma altura da coluna de serviços via flexbox aninhado (`align-items: stretch` + `.col + .col > .card { flex: 1 }`); título centralizado; botão "Salvar Configurações" centralizado. (#0f528c9)

### Corrigido
- Erro de SSL ao conectar com Apprise usando certificado auto-assinado (comum em homelabs com dominios `.home.arpa` ou `.local`). A verificacao SSL foi removida: `requests.post(verify=False)` usado diretamente, sem config `verify_ssl` e sem fallback. Warnings do urllib3 sao suprimidos. (#t_397f341c)

## [2.0.0] — 2026-06-07

### Adicionado
- Web UI em Flask (`web.py`) para configuracao visual — acesse `http://host:5000`
- Frontend single-page (`static/index.html`) com fetch API, sem frameworks JS
- Favicon shield (escudo) em `static/favicon.svg` — icone da aba do navegador, tema dark
- Persistencia de configuracao em `config.json` (substitui env vars)
- Thread-safety com `threading.Lock` no acesso ao arquivo de config
- Modo webhook: `check_interval_seconds = 0` + script `qbit-guardian-hook.sh`
- Endpoint `POST /api/trigger` — processamento sob demanda
- Endpoint `GET /api/health` — healthcheck para Docker
- Heartbeat em `/tmp/heartbeat` para healthcheck externo
- Otimizacao de prioridades de arquivos (midia=7, auxiliares=1, outros=0)
- Remocao por stalled e no-seeds com tempo configuravel
- Integracao com Sonarr: validacao de data de lancamento antes de re-search
- Integracao com Radarr: blocklist + re-search
- Notificacoes via Apprise (Telegram, Discord, etc)
- `CONTEXT.md` com glossario de dominio (15 termos)
- Suite de testes: 12 de seguranca + 25 funcionais (37 total)
- Notas de conceito no vault Obsidian (thread-safe-config, Apprise, qBit API)
- `README.md` com instrucoes Docker, manual, API REST e desenvolvimento
- `CHANGELOG.md` (este arquivo)

### Modificado
- Layout refeito como duas colunas seguindo protótipo Penpot: serviços externos (qBittorrent, Sonarr, Radarr, notificações) à esquerda, Guardian à direita
- Arquitetura: monolito (`guardian.py` 327 linhas) → modulos (`app.py` + `guardian.py` + `web.py` 507 linhas)
- Configuracao: env vars → JSON editavel via Web UI
- Guardian loop: processo unico → thread daemon com Flask na main thread
- Extensoes: sets hardcoded → customizaveis via Web UI
- Docker: `docker-compose.yaml` generico (sem rede fixa), `python:3.12-slim`
- Licenca: adicionada GPL v3 explicita

### Removido
- Dependencia de env vars para credenciais (`.env/.env` depreciado)
- Sets hardcoded de extensoes (`VALID_MEDIA`, `DANGEROUS`)

## [1.0.0] — ~2025

### Versao inicial
- Script monolito Python (`guardian.py`, 327 linhas)
- Loop `while True` com polling a cada N segundos
- Deteccao de extensoes perigosas (.exe, .scr, .bat, etc.)
- Integracao basica com Sonarr e Radarr (blocklist + re-search)
- Notificacoes via Apprise
- Configuracao exclusivamente por variaveis de ambiente
- Dockerfile com `python:3.12-slim`
