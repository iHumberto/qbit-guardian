/**
 * qbit-guardian tour — passeio guiado pela propria interface.
 *
 * Nao e um prototipo a parte: o tour roda EM CIMA das telas reais, por isso
 * nao envelhece sozinho a cada mudanca de layout e nao precisa de uma versao
 * por idioma — o texto de cada passo e uma chave do i18n.js, e o idioma ja
 * esta escolhido no localStorage quando a aba abre.
 *
 * Duas fases, uma por tela:
 *   /login?tour=1  → usuario, senha, entrar
 *   /demo?tour=1   → a home de configuracao, servida em modo demonstracao
 *
 * Em `/demo` o `window.fetch` e trocado por um stub: nenhuma chamada chega a
 * API real, e os valores da tela vem de `/api/demo-config`, que inventa uma
 * instalacao nova em vez de ler o config do disco.
 *
 * Zero dependencia, como o i18n.js. Depende so de `t()` e de `getLang()`.
 */

(function () {
  'use strict';

  var MODO_DEMO = location.pathname === '/demo';
  var PEDIU_TOUR = new URLSearchParams(location.search).get('tour') === '1';

  // ── Passos ────────────────────────────────────────────────────────────
  //
  // `alvo`     seletor do elemento destacado (ausente = balao centralizado)
  // `chave`    chave do i18n com o texto da dica
  // `comando`  linha de terminal mostrada em <code>, fora do texto traduzido
  // `preenche` valor escrito no campo AO SAIR do passo — e o que ensina de
  //            forma visual: o campo anterior fica preenchido enquanto o
  //            proximo recebe o foco
  // `liga`     marca o checkbox ao sair, para os blocos de remocao
  // `vai`      destino ao sair, quando o passo encerra a fase

  var PASSOS_LOGIN = [
    { alvo: '#login_user', chave: 'tour_login_user', preenche: 'admin' },
    { alvo: '#login_password', chave: 'tour_login_senha',
      comando: 'docker logs qbit-guardian', preenche: '••••••••••••' },
    { alvo: '#btn-login', chave: 'tour_login_entrar', vai: '/demo?tour=1' }
  ];

  // A ordem segue a leitura da tela: coluna da esquerda, card do Guardian de
  // cima para baixo, card de notificacoes, botao de salvar.
  var PASSOS_CONFIG = [
    { alvo: '#qbit_url', chave: 'tour_qbit_url', preenche: 'http://192.168.1.100:8080' },
    { alvo: '#qbit_api_key', chave: 'tour_qbit_api_key',
      preenche: '••••••••••••••••' },
    { alvo: '#radarr_url', chave: 'tour_radarr', preenche: 'http://192.168.1.100:7878' },
    { alvo: '#sonarr_url', chave: 'tour_sonarr', preenche: 'http://192.168.1.100:8989' },
    { alvo: '#check_interval', chave: 'tour_polling', preenche: '300' },
    { alvo: '#reevaluate_interval', chave: 'tour_reavaliar', preenche: '300' },
    { alvo: '#retry_interval', chave: 'tour_reconexao', preenche: '120' },
    { alvo: '#priority_media', chave: 'tour_prioridade' },
    { alvo: '#priority_normal', chave: 'tour_prio_aux' },
    { alvo: '#priority_skip', chave: 'tour_prio_outros' },
    { alvo: '#valid_extensions', chave: 'tour_midia' },
    { alvo: '#dangerous_extensions', chave: 'tour_perigosas' },
    { alvo: '#remove_stalled', chave: 'tour_remocao', liga: true },
    { alvo: '#remove_no_seeds', chave: 'tour_sem_seeds', liga: true },
    { alvo: '#remove_slow', chave: 'tour_lento', liga: true },
    { alvo: '#notifications_enabled', chave: 'tour_notificacoes' },
    { alvo: '#apprise_url', chave: 'tour_apprise',
      preenche: 'http://192.168.1.100:8000/notify/guardian' },
    { alvo: '#msg_optimized', chave: 'tour_mensagem' },
    { alvo: '#msg_optimized_wrap .dica', chave: 'tour_variaveis' },
    { alvo: '.btn-save', chave: 'tour_salvar' },
    { chave: 'tour_fim', fim: true }
  ];

  // ── Modo demonstracao ─────────────────────────────────────────────────
  //
  // Instalado na carga do arquivo, ANTES do script da pagina rodar: o painel
  // chama /api/config logo no final do <body>, e um stub tardio nao pegaria
  // essa primeira chamada.

  if (MODO_DEMO) instalarStubDeRede();

  function instalarStubDeRede() {
    var fetchReal = window.fetch.bind(window);
    var promessa = null;

    function dadosDemo() {
      // Uma chamada so, reaproveitada: o painel pede config e defaults em
      // paralelo, e a rota devolve os dois no mesmo corpo.
      if (!promessa) promessa = fetchReal('/api/demo-config').then(function (r) { return r.json(); });
      return promessa;
    }

    function resposta(corpo, status) {
      return new Response(JSON.stringify(corpo), {
        status: status || 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    window.fetch = function (recurso, opcoes) {
      var url = String(recurso && recurso.url ? recurso.url : recurso);
      var metodo = ((opcoes && opcoes.method) || 'GET').toUpperCase();

      // Escrita nunca sai do navegador em demonstracao. O erro e honesto: a
      // tela diz que nao salvou, em vez de fingir sucesso.
      if (metodo !== 'GET') {
        return Promise.resolve(resposta({ error: t('demo_sem_escrita') }, 403));
      }
      if (url.indexOf('/api/config') === 0) {
        return dadosDemo().then(function (d) { return resposta(d.config); });
      }
      if (url.indexOf('/api/defaults') === 0) {
        return dadosDemo().then(function (d) { return resposta(d.defaults); });
      }
      // O resto segue para a rede. Na pratica sobra `/api/version`, que e
      // publico e nao revela nada: o rodape mostra a versao real, que e util
      // de ver ate numa demonstracao.
      return fetchReal(recurso, opcoes);
    };
  }

  // ── Estilo ────────────────────────────────────────────────────────────
  //
  // Vai no proprio arquivo, e nao num .css: o tour e uma peca so, e as duas
  // telas que ele visita ja carregam o CSS delas inline. Usa apenas tokens
  // que existem nas duas (`--card`, `--line`, `--accent`, `--r-card`).

  var CSS = [
    '.tour-furo{position:fixed;pointer-events:none;z-index:9990;',
    '  border-radius:var(--r-pill,13px);',
    '  box-shadow:0 0 0 9999px rgba(10,10,22,.74);',
    '  transition:top .2s ease,left .2s ease,width .2s ease,height .2s ease;}',
    '.tour-balao{position:fixed;z-index:9992;max-width:320px;',
    '  background:var(--card);color:var(--text);border:1px solid var(--line);',
    '  border-radius:var(--r-card);padding:14px 18px;',
    '  font-size:var(--fs-base,14px);line-height:1.35;',
    '  box-shadow:0 8px 28px rgba(0,0,0,.45);}',
    '.tour-balao code{display:block;margin-top:8px;padding:6px 9px;',
    '  background:#0f1830;border-radius:8px;font-size:12px;',
    '  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;',
    '  user-select:all;overflow-wrap:anywhere;}',
    '.tour-acoes{display:flex;align-items:center;justify-content:space-between;',
    '  gap:14px;margin-top:13px;}',
    '.tour-contador{font-size:var(--fs-help,11px);color:var(--muted,#cfd3e0);}',
    '.tour-botoes{display:flex;align-items:center;gap:10px;}',
    '.tour-balao button{font-family:inherit;font-size:var(--fs-help,11px);',
    '  cursor:pointer;background:none;border:none;color:var(--muted,#cfd3e0);',
    '  padding:4px 2px;}',
    '.tour-balao button.principal{font-size:var(--fs-base,14px);color:var(--text);',
    '  border:1px solid var(--line);border-radius:var(--r-pill,13px);padding:4px 14px;}',
    '.tour-balao button.principal:hover{background:#1d2a4d;}',
    '.tour-balao button:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}',
    // O passo das variaveis existe para mostrar um hover funcionando. Sem
    // isto o tour apontaria para um tooltip fechado: foco por script nao
    // dispara :hover, e :focus-visible so vale para foco de teclado.
    '.tour-alvo .dica-tip,.tour-alvo.dica .dica-tip{opacity:1;visibility:visible;}',
    // `hidden` sozinho nao esconde quem tem `display` declarado: a regra do
    // navegador perde na especificidade. Mesmo motivo do `.modal-bg[hidden]`
    // no index.html — em demonstracao estes dois saem da topbar.
    '.docs[hidden],.user-btn[hidden]{display:none;}',
    '.tour-faixa{position:fixed;top:0;left:0;right:0;z-index:9994;',
    '  background:var(--accent);color:#fff;text-align:center;',
    '  font-size:var(--fs-help,11px);line-height:1;padding:7px 12px;}',
    'body.tem-faixa{padding-top:34px;}',
    '@media (prefers-reduced-motion: reduce){.tour-furo{transition:none;}}'
  ].join('\n');

  function injetarEstilo() {
    if (document.getElementById('tour-estilo')) return;
    var tag = document.createElement('style');
    tag.id = 'tour-estilo';
    tag.textContent = CSS;
    document.head.appendChild(tag);
  }

  // ── Motor ─────────────────────────────────────────────────────────────

  var passos = [];
  var indice = 0;
  var furo = null;
  var balao = null;
  var alvoAtual = null;
  var ativo = false;

  function deslocamento() {
    return passos === PASSOS_CONFIG ? PASSOS_LOGIN.length : 0;
  }

  function elemento(passo) {
    return passo && passo.alvo ? document.querySelector(passo.alvo) : null;
  }

  function montar() {
    injetarEstilo();

    furo = document.createElement('div');
    furo.className = 'tour-furo';
    furo.setAttribute('aria-hidden', 'true');

    balao = document.createElement('div');
    balao.className = 'tour-balao';
    balao.setAttribute('role', 'dialog');
    balao.setAttribute('aria-live', 'polite');

    document.body.appendChild(furo);
    document.body.appendChild(balao);
  }

  function desenhar() {
    var passo = passos[indice];
    alvoAtual = elemento(passo);

    // Um passo cujo alvo sumiu (tela menor, bloco escondido) e pulado em vez
    // de travar o tour num furo vazio.
    if (passo.alvo && !alvoAtual) {
      if (indice < passos.length - 1) { indice++; desenhar(); return; }
      encerrar();
      return;
    }

    document.querySelectorAll('.tour-alvo').forEach(function (el) {
      el.classList.remove('tour-alvo');
    });

    balao.innerHTML = '';
    var texto = document.createElement('p');
    texto.textContent = t(passo.chave);
    balao.appendChild(texto);

    if (passo.comando) {
      var cmd = document.createElement('code');
      cmd.textContent = passo.comando;
      balao.appendChild(cmd);
    }

    var acoes = document.createElement('div');
    acoes.className = 'tour-acoes';

    var contador = document.createElement('span');
    contador.className = 'tour-contador';
    // O passeio e um so, em duas telas: contar por fase faria o login
    // terminar em "3 de 3" e a configuracao recomecar do "1 de 11".
    contador.textContent = t('tour_contador')
      .replace('{atual}', deslocamento() + indice + 1)
      .replace('{total}', PASSOS_LOGIN.length + PASSOS_CONFIG.length);
    acoes.appendChild(contador);

    var botoes = document.createElement('div');
    botoes.className = 'tour-botoes';

    // Fim da lista com `vai` nao e fim do passeio: o passo encadeia na outra
    // tela, e oferecer "Fechar" ali encerraria o tour na metade.
    var ultimo = indice === passos.length - 1 && !passo.vai;
    if (!ultimo) {
      var sair = document.createElement('button');
      sair.type = 'button';
      sair.textContent = t('tour_sair');
      sair.addEventListener('click', encerrar);
      botoes.appendChild(sair);
    }

    var proximo = document.createElement('button');
    proximo.type = 'button';
    proximo.className = 'principal';
    proximo.textContent = ultimo ? t('tour_fechar') : t('tour_proximo');
    proximo.addEventListener('click', avancar);
    botoes.appendChild(proximo);

    acoes.appendChild(botoes);
    balao.appendChild(acoes);

    if (alvoAtual) {
      alvoAtual.classList.add('tour-alvo');
      alvoAtual.scrollIntoView({ block: 'center', behavior: 'smooth' });
      // Foco no proprio campo: quem segue o tour ve o cursor onde vai digitar,
      // e o leitor de tela anuncia o rotulo junto com a dica.
      if (typeof alvoAtual.focus === 'function') {
        alvoAtual.focus({ preventScroll: true });
      }
    }

    posicionar();
    // O foco so vai para o botao quando nao ha campo para focar: a tela tem
    // que mostrar o cursor onde o usuario vai digitar, que e metade da dica.
    if (!alvoAtual) proximo.focus({ preventScroll: true });
  }

  // O retangulo do passo inclui o tooltip que ele tenha aberto. Sem isto o
  // passo que explica o `{ }` fica em cima da propria lista de variaveis: o
  // tooltip e maior que o botao e cresce para fora dele.
  function retanguloDeReferencia(el) {
    var r = el.getBoundingClientRect();
    var tip = el.querySelector && el.querySelector('[role="tooltip"]');
    if (!tip) return r;

    // A area vale mais que o `visibility` computado: o tooltip abre por
    // transicao de 150ms e ainda esta escondido no instante deste calculo —
    // mas `visibility:hidden` preserva o layout, entao o retangulo ja e o
    // definitivo. Largura zero significa `display:none`, e ai nao ha o que
    // destacar.
    var rt = tip.getBoundingClientRect();
    if (!rt.width || !rt.height) return r;
    var topo = Math.min(r.top, rt.top);
    var esq = Math.min(r.left, rt.left);
    return {
      top: topo, left: esq,
      right: Math.max(r.right, rt.right),
      bottom: Math.max(r.bottom, rt.bottom),
      width: Math.max(r.right, rt.right) - esq,
      height: Math.max(r.bottom, rt.bottom) - topo
    };
  }

  function posicionar() {
    if (!ativo) return;

    if (!alvoAtual) {
      // Passo sem alvo (o encerramento): furo fechado, balao no centro.
      furo.style.cssText = 'display:none';
      balao.style.top = Math.round(window.innerHeight / 2 - balao.offsetHeight / 2) + 'px';
      balao.style.left = Math.round(window.innerWidth / 2 - balao.offsetWidth / 2) + 'px';
      // Sem furo, o escurecimento vem do proprio balao: a sombra dele.
      balao.style.boxShadow = '0 0 0 9999px rgba(10,10,22,.74)';
      return;
    }

    balao.style.boxShadow = '';
    furo.style.display = '';

    var r = retanguloDeReferencia(alvoAtual);
    var folga = 6;
    furo.style.top = (r.top - folga) + 'px';
    furo.style.left = (r.left - folga) + 'px';
    furo.style.width = (r.width + folga * 2) + 'px';
    furo.style.height = (r.height + folga * 2) + 'px';

    var alt = balao.offsetHeight;
    var larg = balao.offsetWidth;
    var folga_balao = 16;
    var topo, esq;

    // O balao procura o lado antes de procurar embaixo. Embaixo ele cobre o
    // proprio formulario que esta explicando — no login chega a esconder o
    // campo do passo seguinte. Ao lado ele cobre, no maximo, um card vizinho.
    if (r.right + folga_balao + larg <= window.innerWidth - 12) {
      esq = r.right + folga_balao;
      topo = r.top + r.height / 2 - alt / 2;
    } else if (r.left - folga_balao - larg >= 12) {
      esq = r.left - folga_balao - larg;
      topo = r.top + r.height / 2 - alt / 2;
    } else {
      // Sem espaco lateral: embaixo, e so vira para cima quando nao cabe —
      // rolar e melhor que sair da viewport pelo topo.
      var abaixo = r.bottom + 14;
      topo = (abaixo + alt <= window.innerHeight - 12 || r.top - 14 - alt < 12)
        ? abaixo : r.top - 14 - alt;
      esq = r.left;
    }

    // Em qualquer um dos casos o balao fica inteiro dentro da viewport.
    esq = Math.min(Math.max(esq, 12), Math.max(12, window.innerWidth - larg - 12));
    topo = Math.min(Math.max(topo, 12), Math.max(12, window.innerHeight - alt - 12));

    balao.style.top = Math.round(topo) + 'px';
    balao.style.left = Math.round(esq) + 'px';
  }

  function aplicarSaida(passo) {
    var el = elemento(passo);
    if (!el) return;
    if (passo.preenche !== undefined) el.value = passo.preenche;
    if (passo.liga && el.type === 'checkbox' && !el.checked) {
      el.checked = true;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function avancar() {
    var passo = passos[indice];
    aplicarSaida(passo);

    if (passo.vai) { location.href = passo.vai; return; }
    if (indice >= passos.length - 1) { encerrar(); return; }

    indice++;
    desenhar();
  }

  function encerrar() {
    ativo = false;
    document.removeEventListener('click', interceptarClique, true);
    document.removeEventListener('keydown', aoTeclar, true);
    window.removeEventListener('resize', posicionar);
    window.removeEventListener('scroll', posicionar, true);
    document.removeEventListener('change', aoTrocarIdioma);
    document.querySelectorAll('.tour-alvo').forEach(function (el) {
      el.classList.remove('tour-alvo');
    });
    if (furo) furo.remove();
    if (balao) balao.remove();
    furo = balao = alvoAtual = null;
  }

  // Enquanto o tour roda ele e dono dos cliques: no alvo, avanca; em qualquer
  // outro lugar, nada acontece. Sem isto o clique em "Entrar" tentaria logar
  // de verdade e o clique em "Salvar" bateria num 403 no meio do passeio.
  function interceptarClique(e) {
    if (!ativo) return;
    if (balao && balao.contains(e.target)) return;
    // O seletor de idioma e a excecao: o tour e bilingue e trocar de idioma
    // no meio dele tem que valer para o balao tambem, nao so para a tela.
    if (e.target.closest && e.target.closest('#lang-bar')) return;
    e.preventDefault();
    e.stopPropagation();
    if (alvoAtual && (alvoAtual === e.target || alvoAtual.contains(e.target))) avancar();
  }

  // O balao e escrito por script, entao o walker do i18n nao o alcanca: ele
  // so reescreve quem tem `data-i18n`. Redesenhar e o equivalente.
  //
  // Na bolha, e nao na captura: o `setLang()` esta no listener do proprio
  // select, e em captura este handler correria antes dele — redesenhando o
  // balao no idioma que acabou de ser trocado.
  function aoTrocarIdioma(e) {
    if (ativo && e.target && e.target.id === 'lang-select') desenhar();
  }

  function aoTeclar(e) {
    if (!ativo) return;
    if (e.key === 'Escape') { e.preventDefault(); encerrar(); return; }
    if (e.key === 'Enter' || e.key === 'ArrowRight') {
      // Enter dentro de um campo submeteria o formulario de login.
      e.preventDefault();
      e.stopPropagation();
      avancar();
    }
  }

  function iniciar(lista) {
    if (ativo) return;
    passos = lista;
    indice = 0;
    ativo = true;
    montar();
    document.addEventListener('click', interceptarClique, true);
    document.addEventListener('keydown', aoTeclar, true);
    window.addEventListener('resize', posicionar);
    window.addEventListener('scroll', posicionar, true);
    document.addEventListener('change', aoTrocarIdioma);
    desenhar();
  }

  // ── Faixa do modo demonstracao ────────────────────────────────────────

  function montarFaixa() {
    injetarEstilo();
    var faixa = document.createElement('div');
    faixa.className = 'tour-faixa';
    faixa.setAttribute('data-i18n', 'demo_faixa');
    faixa.textContent = t('demo_faixa');
    document.body.appendChild(faixa);
    document.body.classList.add('tem-faixa');

    // O que nao existe em demonstracao sai da tela: trocar credencial de uma
    // conta que nao existe, e um tour dentro do proprio tour.
    var conta = document.getElementById('user-btn');
    if (conta) conta.hidden = true;
    var link = document.getElementById('tour-link');
    if (link) link.hidden = true;
  }

  // ── Entrada ───────────────────────────────────────────────────────────

  function bootstrap() {
    if (MODO_DEMO) montarFaixa();
    if (!PEDIU_TOUR) return;
    // Oferecer o passeio para quem ja esta dentro dele e ruido.
    var chamada = document.getElementById('tour-link');
    if (chamada) chamada.hidden = true;
    // O idioma ja esta aplicado: o i18n.js roda no final do <body> das duas
    // telas, e este bootstrap espera o DOM inteiro.
    iniciar(MODO_DEMO ? PASSOS_CONFIG : PASSOS_LOGIN);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }

  // Exposto para os testes e para quem quiser reabrir o passeio sem recarregar.
  window.tour = { iniciar: iniciar, encerrar: encerrar,
                  PASSOS_LOGIN: PASSOS_LOGIN, PASSOS_CONFIG: PASSOS_CONFIG };
})();
