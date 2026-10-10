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
        placeholder_qbit_url: 'http://192.168.15.3:8080',
        placeholder_qbit_api_key: 'Cole sua API Key do qBittorrent aqui',
        section_sonarr: '\uD83D\uDCFA Sonarr',
        placeholder_sonarr_url: 'http://192.168.15.3:8989',
        placeholder_sonarr_api_key: 'API Key do Sonarr',
        section_radarr: '\uD83C\uDFAC Radarr',
        placeholder_radarr_url: 'http://192.168.15.3:7878',
        placeholder_radarr_api_key: 'API Key do Radarr',
        section_notifications: '\uD83D\uDD14 Notifica\u00E7\u00F5es',
        label_apprise_url: 'Apprise URL (Telegram, Discord, etc.)',
        label_msg_optimized: 'Mensagem para Torrent Otimizado',
        label_msg_removed: 'Mensagem para Torrent Exclu\u00EDdo (Perigoso)',
        label_msg_stalled: 'Mensagem para Torrent Exclu\u00EDdo (Stalled)',
        vars_label: 'Vari\u00E1veis dispon\u00EDveis:',
        docs_label: 'Docs',
        docs_tooltip: 'Com d\u00FAvidas? Leia a documenta\u00E7\u00E3o e aprenda a configurar',
        docs_url: 'https://github.com/iHumberto/qbit-guardian/tree/main/docs/pt-BR',
        placeholder_apprise_url: 'tgram://BOT_TOKEN/CHAT_ID',
        section_guardian: '\uD83D\uDEE1\uFE0F Guardian',
        label_check_interval: 'Intervalo de verifica\u00E7\u00E3o (segundos, 0 = modo webhook)',
        help_check_interval: '0 desativa o polling \u2014 use com o script de webhook no qBit',
        label_valid_extensions: 'Extens\u00F5es de m\u00EDdia v\u00E1lidas (uma por linha)',
        label_dangerous_extensions: 'Extens\u00F5es perigosas (uma por linha)',
        label_priority_media: 'Prioridade para arquivos de m\u00EDdia (0, 1, 6 ou 7)',
        help_priority_media: '0 = n\u00E3o baixar \u00B7 1 = normal \u00B7 6 = alta \u00B7 7 = m\u00E1xima',
        prio_skip: '0 \u2014 n\u00E3o baixar',
        prio_normal: '1 \u2014 normal',
        prio_high: '6 \u2014 alta',
        prio_max: '7 \u2014 m\u00E1xima',
        label_priority_normal: 'Prioridade para arquivos auxiliares (.nfo, .srt, .jpg)',
        label_priority_skip: 'Prioridade para outros arquivos',
        label_remove_stalled: 'Remover torrents parados (stalled) h\u00E1 mais de',
        unit_seconds: 'segundos',
        unit_minutes: 'minutos',
        unit_hours: 'horas',
        label_remove_no_seeds: 'Remover torrents sem seeds h\u00E1 mais de',
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
        update_tooltip: 'Uma vers\u00E3o mais nova foi publicada \u2014 atualize a imagem do container'
    },
    'en-US': {
        title: '\uD83D\uDEE1\uFE0F qbit-guardian',
        subtitle: 'Protect your qBittorrent from malicious torrents',
        section_qbit: '\uD83D\uDD17 qBittorrent',
        label_url: 'URL',
        label_api_key: 'API Key',
        placeholder_qbit_url: 'http://192.168.15.3:8080',
        placeholder_qbit_api_key: 'Paste your qBittorrent API Key here',
        section_sonarr: '\uD83D\uDCFA Sonarr',
        placeholder_sonarr_url: 'http://192.168.15.3:8989',
        placeholder_sonarr_api_key: 'Sonarr API Key',
        section_radarr: '\uD83C\uDFAC Radarr',
        placeholder_radarr_url: 'http://192.168.15.3:7878',
        placeholder_radarr_api_key: 'Radarr API Key',
        section_notifications: '\uD83D\uDD14 Notifications',
        label_apprise_url: 'Apprise URL (Telegram, Discord, etc.)',
        label_msg_optimized: 'Message for Optimized Torrent',
        label_msg_removed: 'Message for Removed Torrent (Dangerous)',
        label_msg_stalled: 'Message for Removed Torrent (Stalled)',
        vars_label: 'Available variables:',
        docs_label: 'Docs',
        docs_tooltip: 'Questions? Read the documentation and learn how to set it up',
        docs_url: 'https://github.com/iHumberto/qbit-guardian/tree/main/docs/en-US',
        placeholder_apprise_url: 'tgram://BOT_TOKEN/CHAT_ID',
        section_guardian: '\uD83D\uDEE1\uFE0F Guardian',
        label_check_interval: 'Check interval (seconds, 0 = webhook mode)',
        help_check_interval: '0 disables polling \u2014 use with the qBit webhook script',
        label_valid_extensions: 'Valid media extensions (one per line)',
        label_dangerous_extensions: 'Dangerous extensions (one per line)',
        label_priority_media: 'Media file priority (0, 1, 6 or 7)',
        help_priority_media: '0 = skip \u00B7 1 = normal \u00B7 6 = high \u00B7 7 = maximum',
        prio_skip: '0 \u2014 skip',
        prio_normal: '1 \u2014 normal',
        prio_high: '6 \u2014 high',
        prio_max: '7 \u2014 maximum',
        label_priority_normal: 'Auxiliary file priority (.nfo, .srt, .jpg)',
        label_priority_skip: 'Other file priority',
        label_remove_stalled: 'Remove stalled torrents older than',
        unit_seconds: 'seconds',
        unit_minutes: 'minutes',
        unit_hours: 'hours',
        label_remove_no_seeds: 'Remove seedless torrents older than',
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
        update_tooltip: 'A newer version was published \u2014 update the container image'
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
