/**
 * qbit-guardian i18n — lightweight bilingual support (PT-BR / EN-US).
 *
 * Zero dependencies. Reads/writes localStorage('lang').
 * Exposes: t(key), setLang(lang), getLang(), initI18N()
 */

const translations = {
    'pt-BR': {
        title: '\uD83D\uDEE1\uFE0F qbit-guardian',
        subtitle: 'Protege seu qBittorrent contra torrents maliciosos',
        section_qbit: '\uD83D\uDD17 qBittorrent',
        label_url: 'URL',
        label_api_key: 'API Key',
        placeholder_qbit_url: 'http://192.168.1.100:8080',
        placeholder_qbit_api_key: 'Cole sua API Key do qBittorrent aqui',
        section_sonarr: '\uD83D\uDCFA Sonarr',
        placeholder_sonarr_url: 'http://192.168.1.100:8989',
        placeholder_sonarr_api_key: 'API Key do Sonarr',
        section_radarr: '\uD83C\uDFAC Radarr',
        placeholder_radarr_url: 'http://192.168.1.100:7878',
        placeholder_radarr_api_key: 'API Key do Radarr',
        section_notifications: '\uD83D\uDD14 Notifica\u00E7\u00F5es',
        label_apprise_url: 'Apprise URL',
        label_msg_optimized: 'Otimizado',
        label_msg_removed: 'Removido (perigoso)',
        label_msg_stalled: 'Removido (parado)',
        vars_label: 'Vari\u00E1veis dispon\u00EDveis:',
        docs_label: 'Docs',
        docs_tooltip: 'Com d\u00FAvidas? Leia a documenta\u00E7\u00E3o e aprenda a configurar',
        docs_url: 'https://github.com/iHumberto/qbit-guardian/tree/main/docs/pt-BR',
        placeholder_apprise_url: 'http://192.168.1.100:8000/notify/guardian',
        erro_apprise_url: 'Endere\u00E7o inv\u00E1lido. Use o endpoint HTTP do seu servidor Apprise (http://\u2026 /notify/chave). URLs de servi\u00E7o como tgram:// n\u00E3o funcionam aqui \u2014 elas v\u00E3o na configura\u00E7\u00E3o do Apprise.',
        erro_apprise_servico: 'URL de servi\u00E7o do Apprise n\u00E3o vale aqui \u2014 ela vai na configura\u00E7\u00E3o do seu servidor Apprise. Neste campo vai o endere\u00E7o do servidor.',
        erro_apprise_formato: 'Endere\u00E7o inv\u00E1lido \u2014 use http:// ou https://.',
        section_guardian: '\uD83D\uDEE1\uFE0F Guardian',
        label_check_interval: 'Polling',
        label_valid_extensions: 'Extens\u00F5es de m\u00EDdia',
        label_dangerous_extensions: 'Extens\u00F5es perigosas',
        label_priority_media: 'Prioridade m\u00EDdia',
        prio_skip: '0 \u2014 n\u00E3o baixar',
        prio_normal: '1 \u2014 normal',
        prio_high: '6 \u2014 alta',
        prio_max: '7 \u2014 m\u00E1xima',
        label_priority_normal: 'Prioridade auxiliares',
        label_priority_skip: 'Prioridade outros',
        label_remove_stalled: 'Parados (stalled) h\u00E1 mais de',
        unit_seconds: 'segundos',
        unit_minutes: 'minutos',
        unit_hours: 'horas',
        unit_kib: 'KiB/s',
        unit_mib: 'MiB/s',
        unit_gib: 'GiB/s',
        unit_tib: 'TiB/s',
        label_remove_slow: 'Abaixo da velocidade m\u00EDnima',
        label_reevaluate_interval: 'Reavaliar fila',
        tip_reevaluate: 'S\u00F3 vale no modo webhook (Polling em 0). Com Polling acima de 0 o guardian varre a fila sozinho e este valor \u00E9 ignorado.',
        label_retry_interval: 'Reconex\u00E3o',
        label_remove_no_seeds: 'Sem seeds h\u00E1 mais de',
        section_remove: 'Remover torrents',
        conector_por: 'por',
        unit_s: 's',
        vars_tooltip: 'Vari\u00E1veis que esta mensagem aceita',
        btn_save: '\uD83D\uDCBE Salvar Configura\u00E7\u00F5es',
        toast_saved: 'Configura\u00E7\u00F5es salvas!',
        toast_load_error: 'Erro ao carregar configura\u00E7\u00E3o: ',
        toast_error: 'Erro: ',
        account_title: '\uD83D\uDC64 Conta',
        label_cred_user: 'Usu\u00E1rio',
        label_cred_current: 'Senha atual',
        label_cred_new: 'Nova senha',
        help_cred: 'Deixe em branco para manter a senha atual. A senha atual \u00E9 sempre obrigat\u00F3ria.',
        btn_cancel: 'Cancelar',
        btn_save_short: 'Salvar',
        toast_cred_saved: 'Credenciais alteradas. Entre de novo com os dados novos.',
        login_title: '\uD83D\uDD10 Entrar',
        label_login_password: 'Senha',
        btn_login: 'Entrar',
        login_invalid: 'Usu\u00E1rio ou senha inv\u00E1lidos.',
        login_throttled: 'Tentativas demais. Aguarde alguns minutos e tente de novo.',
        login_hint: 'Primeiro acesso? A senha foi gerada no startup e aparece em `docker logs qbit-guardian`.',
        btn_logout: 'Sair',
        update_available: '{version} dispon\u00EDvel',
        update_tooltip: 'Uma vers\u00E3o mais nova foi publicada \u2014 atualize a imagem do container',
        // Tour guiado. O texto de cada passo e chave daqui, e nao do tour.js:
        // assim o passeio troca de idioma junto com o resto da tela.
        tour_label: 'Tour',
        tour_tooltip: 'Primeira vez por aqui? Veja um passeio guiado pela tela, do login \u00E0 configura\u00E7\u00E3o',
        tour_login_link: 'Primeira vez? Veja o passeio guiado',
        tour_login_user: 'Comece pelo usu\u00E1rio. Numa instala\u00E7\u00E3o nova ele \u00E9 admin \u2014 a conta \u00E9 criada no primeiro start do container.',
        tour_login_senha: 'A senha inicial \u00E9 sorteada no start e aparece no log do container:',
        tour_login_entrar: 'Entre. Depois do primeiro login, troque a senha pelo \u00EDcone de conta, no canto do painel.',
        tour_qbit_url: 'Endere\u00E7o do qBittorrent, com a porta da Web UI. \u00C9 a \u00FAnica integra\u00E7\u00E3o obrigat\u00F3ria \u2014 sem ela o guardian n\u00E3o tem o que vigiar.',
        tour_qbit_api_key: 'A API Key do qBittorrent. Sem ela o guardian n\u00E3o consegue listar nem remover torrent nenhum.',
        tour_radarr: 'Radarr \u00E9 opcional. Preenchido, todo torrent removido tamb\u00E9m entra na blocklist e dispara uma nova busca pelo filme.',
        tour_sonarr: 'Sonarr faz o mesmo para s\u00E9ries, com uma diferen\u00E7a: valida a data de lan\u00E7amento do epis\u00F3dio antes de buscar de novo.',
        tour_polling: 'De quanto em quanto tempo a fila inteira \u00E9 varrida. Este campo decide o modo: acima de 0 o guardian varre sozinho; em 0 ele para de varrer e passa a agir s\u00F3 quando o qBittorrent avisa, por webhook.',
        tour_reavaliar: 'S\u00F3 vale no modo webhook (Polling em 0). \u00C9 o que traz o guardian de volta \u00E0 fila sozinho \u2014 sem isso, um torrent que travou depois de adicionado esperaria outro torrent chegar. Com Polling acima de 0 este campo \u00E9 ignorado.',
        tour_reconexao: 'Quando o qBittorrent some, \u00E9 de quanto em quanto tempo o guardian tenta de novo. Vale tamb\u00E9m no start: ele espera o qBittorrent subir em vez de desistir.',
        tour_prio_aux: 'Prioridade dos arquivos auxiliares \u2014 legenda, amostra, NFO. Baixam, mas depois da m\u00EDdia.',
        tour_prio_outros: 'Prioridade de todo o resto. Em 0 o arquivo nem \u00E9 baixado, que \u00E9 o padr\u00E3o: \u00E9 assim que o torrent para de gastar banda com o que voc\u00EA n\u00E3o quer.',
        tour_midia: 'As extens\u00F5es que contam como m\u00EDdia. Torrent que n\u00E3o traga nenhuma delas \u00E9 removido \u2014 \u00E9 por esta lista que o guardian sabe o que veio buscar. Uma por linha.',
        tour_sem_seeds: 'Torrent sem nenhum seed \u00E0 vista h\u00E1 tempo demais. O tempo s\u00F3 conta enquanto ele est\u00E1 ativo de verdade: espera na fila n\u00E3o entra.',
        tour_lento: 'Abaixo de uma velocidade m\u00EDnima por tempo demais. A conta \u00E9 pela m\u00E9dia na janela, n\u00E3o pela velocidade do instante \u2014 uma queda de alguns segundos n\u00E3o condena o download.',
        tour_notificacoes: 'A chave geral das notifica\u00E7\u00F5es. Desligada aqui, nada sai, mesmo com as tr\u00EAs mensagens ligadas.',
        tour_apprise: 'O endere\u00E7o do seu servidor Apprise \u2014 um endpoint HTTP, com /notify/ e a chave de configura\u00E7\u00E3o. Aten\u00E7\u00E3o: URL de servi\u00E7o (tgram://, discord://) n\u00E3o funciona aqui; ela vai na configura\u00E7\u00E3o do pr\u00F3prio Apprise.',
        tour_mensagem: 'O texto que chega no seu celular. Cada {{vari\u00E1vel}} \u00E9 trocada pelo valor real do torrent, e a caixa j\u00E1 abre com a mensagem padr\u00E3o.',
        tour_prioridade: 'Prioridade dos arquivos de m\u00EDdia dentro do torrent. A escala do qBittorrent tem buracos \u2014 s\u00F3 0, 1, 6 e 7 valem \u2014, por isso \u00E9 uma lista e n\u00E3o um n\u00FAmero.',
        tour_perigosas: 'Torrent que traga qualquer uma destas extens\u00F5es \u00E9 removido na hora e vai para a blocklist. Uma por linha.',
        tour_remocao: 'Aqui ficam as remo\u00E7\u00F5es por tempo. Ligue a chave e diga h\u00E1 quanto tempo o torrent pode ficar parado antes de sair da fila.',
        tour_variaveis: 'O { } lista as vari\u00E1veis que aquela mensagem aceita. Ele abre no hover e tamb\u00E9m pelo teclado.',
        tour_salvar: 'Salvar aplica na hora: o guardian recarrega a configura\u00E7\u00E3o sem reiniciar o container.',
        tour_fim: '\u00C9 isso. Esta tela \u00E9 uma demonstra\u00E7\u00E3o \u2014 nada do que voc\u00EA digitou aqui foi salvo. Feche a aba e configure no painel de verdade.',
        tour_proximo: 'Pr\u00F3ximo',
        tour_sair: 'Sair',
        tour_fechar: 'Fechar',
        tour_contador: '{atual} de {total}',
        demo_faixa: 'Modo demonstra\u00E7\u00E3o \u2014 nada nesta tela \u00E9 salvo',
        demo_sem_escrita: 'modo demonstra\u00E7\u00E3o, nada \u00E9 salvo'
    },
    'en-US': {
        title: '\uD83D\uDEE1\uFE0F qbit-guardian',
        subtitle: 'Protect your qBittorrent from malicious torrents',
        section_qbit: '\uD83D\uDD17 qBittorrent',
        label_url: 'URL',
        label_api_key: 'API Key',
        placeholder_qbit_url: 'http://192.168.1.100:8080',
        placeholder_qbit_api_key: 'Paste your qBittorrent API Key here',
        section_sonarr: '\uD83D\uDCFA Sonarr',
        placeholder_sonarr_url: 'http://192.168.1.100:8989',
        placeholder_sonarr_api_key: 'Sonarr API Key',
        section_radarr: '\uD83C\uDFAC Radarr',
        placeholder_radarr_url: 'http://192.168.1.100:7878',
        placeholder_radarr_api_key: 'Radarr API Key',
        section_notifications: '\uD83D\uDD14 Notifications',
        label_apprise_url: 'Apprise URL',
        label_msg_optimized: 'Optimized',
        label_msg_removed: 'Removed (dangerous)',
        label_msg_stalled: 'Removed (stalled)',
        vars_label: 'Available variables:',
        docs_label: 'Docs',
        docs_tooltip: 'Questions? Read the documentation and learn how to set it up',
        docs_url: 'https://github.com/iHumberto/qbit-guardian/tree/main/docs/en-US',
        placeholder_apprise_url: 'http://192.168.1.100:8000/notify/guardian',
        erro_apprise_url: 'Invalid address. Use the HTTP endpoint of your Apprise server (http://\u2026 /notify/key). Service URLs like tgram:// do not work here \u2014 they go in the Apprise configuration itself.',
        erro_apprise_servico: 'An Apprise service URL does not belong here \u2014 it goes in your Apprise server configuration. This field takes the server address.',
        erro_apprise_formato: 'Invalid address \u2014 use http:// or https://.',
        section_guardian: '\uD83D\uDEE1\uFE0F Guardian',
        label_check_interval: 'Polling',
        label_valid_extensions: 'Media extensions',
        label_dangerous_extensions: 'Dangerous extensions',
        label_priority_media: 'Media priority',
        prio_skip: '0 \u2014 skip',
        prio_normal: '1 \u2014 normal',
        prio_high: '6 \u2014 high',
        prio_max: '7 \u2014 maximum',
        label_priority_normal: 'Auxiliary priority',
        label_priority_skip: 'Other priority',
        label_remove_stalled: 'Stalled longer than',
        unit_seconds: 'seconds',
        unit_minutes: 'minutes',
        unit_hours: 'hours',
        unit_kib: 'KiB/s',
        unit_mib: 'MiB/s',
        unit_gib: 'GiB/s',
        unit_tib: 'TiB/s',
        label_remove_slow: 'Below the minimum speed',
        label_reevaluate_interval: 'Queue recheck',
        tip_reevaluate: 'Only applies in webhook mode (Polling at 0). With Polling above 0 the guardian sweeps the queue on its own and this value is ignored.',
        label_retry_interval: 'Reconnect',
        label_remove_no_seeds: 'Seedless longer than',
        section_remove: 'Remove torrents',
        conector_por: 'for',
        unit_s: 's',
        vars_tooltip: 'Variables this message accepts',
        btn_save: '\uD83D\uDCBE Save Settings',
        toast_saved: 'Settings saved!',
        toast_load_error: 'Error loading configuration: ',
        toast_error: 'Error: ',
        account_title: '\uD83D\uDC64 Account',
        label_cred_user: 'Username',
        label_cred_current: 'Current password',
        label_cred_new: 'New password',
        help_cred: 'Leave blank to keep the current password. The current password is always required.',
        btn_cancel: 'Cancel',
        btn_save_short: 'Save',
        toast_cred_saved: 'Credentials changed. Sign in again with the new details.',
        login_title: '\uD83D\uDD10 Sign in',
        label_login_password: 'Password',
        btn_login: 'Sign in',
        login_invalid: 'Invalid username or password.',
        login_throttled: 'Too many attempts. Wait a few minutes and try again.',
        login_hint: 'First time? The password was generated at startup and shows up in `docker logs qbit-guardian`.',
        btn_logout: 'Sign out',
        update_available: '{version} available',
        update_tooltip: 'A newer version was published \u2014 update the container image',
        // Guided tour. See the pt-BR table for why the text lives here.
        tour_label: 'Tour',
        tour_tooltip: 'First time here? Take a guided walk through the screen, from login to configuration',
        tour_login_link: 'First time? Take the guided tour',
        tour_login_user: 'Start with the username. On a fresh install it is admin \u2014 the account is created on the first container start.',
        tour_login_senha: 'The initial password is drawn at startup and shows up in the container log:',
        tour_login_entrar: 'Sign in. After the first login, change the password from the account icon, in the corner of the panel.',
        tour_qbit_url: 'The qBittorrent address, with the Web UI port. This is the only required integration \u2014 without it the guardian has nothing to watch.',
        tour_qbit_api_key: 'The qBittorrent API Key. Without it the guardian cannot list or remove a single torrent.',
        tour_radarr: 'Radarr is optional. Filled in, every removed torrent also lands on the blocklist and triggers a fresh search for the movie.',
        tour_sonarr: 'Sonarr does the same for series, with one difference: it checks the episode release date before searching again.',
        tour_polling: 'How often the whole queue gets swept. This field picks the mode: above 0 the guardian sweeps on its own; at 0 it stops sweeping and only acts when qBittorrent calls it, over webhook.',
        tour_reavaliar: 'Only matters in webhook mode (Polling at 0). It is what brings the guardian back to the queue on its own \u2014 without it, a torrent that stalled after being added would wait for another torrent to show up. With Polling above 0 this field is ignored.',
        tour_reconexao: 'When qBittorrent goes away, this is how often the guardian tries again. It applies at startup too: it waits for qBittorrent to come up instead of giving up.',
        tour_prio_aux: 'Priority for the helper files \u2014 subtitles, samples, NFO. They download, but after the media.',
        tour_prio_outros: 'Priority for everything else. At 0 the file is not downloaded at all, which is the default: that is how the torrent stops spending bandwidth on what you did not ask for.',
        tour_midia: 'The extensions that count as media. A torrent carrying none of them is removed \u2014 this list is how the guardian knows what it came for. One per line.',
        tour_sem_seeds: 'Torrents with no seed in sight for too long. The clock only runs while the torrent is actually active: time spent queued does not count.',
        tour_lento: 'Below a minimum speed for too long. The reading is the average over the window, not the speed of the moment \u2014 a dip of a few seconds does not condemn the download.',
        tour_notificacoes: 'The master switch for notifications. Off here, nothing goes out, even with all three messages enabled.',
        tour_apprise: 'The address of your Apprise server \u2014 an HTTP endpoint, with /notify/ and the config key. Careful: a service URL (tgram://, discord://) does not work here; that one goes in Apprise\'s own configuration.',
        tour_mensagem: 'The text that lands on your phone. Each {{variable}} is swapped for the torrent\'s real value, and the box opens with the default message already in it.',
        tour_prioridade: 'Priority of the media files inside the torrent. The qBittorrent scale has gaps \u2014 only 0, 1, 6 and 7 are valid \u2014 so this is a list, not a number.',
        tour_perigosas: 'A torrent carrying any of these extensions is removed right away and goes to the blocklist. One per line.',
        tour_remocao: 'This is where time-based removals live. Flip the switch and say how long a torrent may sit still before it leaves the queue.',
        tour_variaveis: 'The { } lists the variables that message accepts. It opens on hover, and from the keyboard too.',
        tour_salvar: 'Saving applies immediately: the guardian reloads the configuration without restarting the container.',
        tour_fim: 'That is it. This screen is a demo \u2014 nothing you typed here was saved. Close the tab and set it up on the real panel.',
        tour_proximo: 'Next',
        tour_sair: 'Exit',
        tour_fechar: 'Close',
        tour_contador: '{atual} of {total}',
        demo_faixa: 'Demo mode \u2014 nothing on this screen is saved',
        demo_sem_escrita: 'demo mode, nothing is saved'
    }
};

var _currentLang = (function () {
    try {
        var stored = localStorage.getItem('lang');
        if (stored && translations[stored]) return stored;
    } catch (e) { /* localStorage blocked */ }
    return 'pt-BR';
})();

/**
 * Return the translated string for key in the current language.
 * Falls back to pt-BR if the key is missing.
 */
function t(key) {
    var lang = translations[_currentLang];
    if (lang && lang[key] !== undefined) return lang[key];
    var fallback = translations['pt-BR'];
    return (fallback && fallback[key] !== undefined) ? fallback[key] : key;
}

/**
 * Return the current language code ('pt-BR' or 'en-US').
 */
function getLang() {
    return _currentLang;
}

/**
 * Switch language, persist to localStorage, and re-render the page.
 */
function setLang(lang) {
    if (!translations[lang]) return;
    _currentLang = lang;
    try { localStorage.setItem('lang', lang); } catch (e) { /* ignore */ }
    document.documentElement.lang = lang;
    applyTranslations();
    updateLangSelector();
}

/**
 * Fill `{name}` placeholders in a translated string from the element's own
 * `data-name` attributes.
 *
 * Without this, a string with a value in the middle ('{version} available')
 * could not go through the walker: whoever had the value would have to write
 * the text by hand, and that text would then stay frozen in the language of
 * the first render, because setLang() re-renders without reloading the page.
 * An absent attribute leaves the placeholder untouched.
 */
function _fillVars(texto, el) {
    return texto.replace(/\{(\w+)\}/g, function (todo, nome) {
        var valor = el.getAttribute('data-' + nome);
        return valor === null ? todo : valor;
    });
}

/**
 * Walk all elements with [data-i18n] and [data-i18n-placeholder],
 * replacing their text/placeholder with translated strings.
 */
function applyTranslations() {
    // Text content
    var els = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n');
        if (key) el.textContent = _fillVars(t(key), el);
    }

    // Placeholder attributes
    els = document.querySelectorAll('[data-i18n-placeholder]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n-placeholder');
        if (key) el.placeholder = t(key);
    }

    // Href attributes (the docs link points at the active language's folder)
    els = document.querySelectorAll('[data-i18n-href]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n-href');
        if (key) el.href = t(key);
    }

    // Title and aria-label (the account button has no visible text).
    els = document.querySelectorAll('[data-i18n-title]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n-title');
        if (key) el.title = t(key);
    }

    els = document.querySelectorAll('[data-i18n-aria]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n-aria');
        if (key) el.setAttribute('aria-label', t(key));
    }

    // Select options (value stays the same, only display text changes).
    // Cobre unidades de tempo e a escala de prioridade.
    els = document.querySelectorAll('option[data-i18n-option]');
    for (var i = 0; i < els.length; i++) {
        var opt = els[i];
        var optKey = opt.getAttribute('data-i18n-option');
        if (optKey) opt.textContent = t(optKey);
    }
}

/**
 * Build and inject the language selector dropdown.
 * Called once by initI18N().
 */
function buildLangSelector() {
    var bar = document.getElementById('lang-bar');
    if (!bar) return;

    bar.innerHTML = '';

    // Flag map
    var flags = { 'pt-BR': '\uD83C\uDDE7\uD83C\uDDF7', 'en-US': '\uD83C\uDDFA\uD83C\uDDF8' };

    var select = document.createElement('select');
    select.id = 'lang-select';
    select.setAttribute('aria-label', 'Language / Idioma');

    var langs = ['pt-BR', 'en-US'];
    for (var i = 0; i < langs.length; i++) {
        var code = langs[i];
        var opt = document.createElement('option');
        opt.value = code;
        opt.textContent = flags[code] + ' ' + code;
        select.appendChild(opt);
    }

    select.value = _currentLang;

    select.addEventListener('change', function () {
        setLang(select.value);
    });

    bar.appendChild(select);
}

/**
 * Sync the <select> value to the current language after a setLang() call.
 */
function updateLangSelector() {
    var sel = document.getElementById('lang-select');
    if (sel) sel.value = _currentLang;
}

/**
 * Initialize i18n: build the dropdown, apply translations.
 * Call once on page load (or DOMContentLoaded).
 */
function initI18N() {
    buildLangSelector();
    document.documentElement.lang = _currentLang;
    applyTranslations();
}
