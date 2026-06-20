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
        placeholder_apprise_url: 'tgram://BOT_TOKEN/CHAT_ID',
        section_guardian: '\uD83D\uDEE1\uFE0F Guardian',
        label_check_interval: 'Intervalo de verifica\u00E7\u00E3o (segundos, 0 = modo webhook)',
        help_check_interval: '0 desativa o polling \u2014 use com o script de webhook no qBit',
        label_valid_extensions: 'Extens\u00F5es de m\u00EDdia v\u00E1lidas (uma por linha)',
        label_dangerous_extensions: 'Extens\u00F5es perigosas (uma por linha)',
        label_priority_media: 'Prioridade para arquivos de m\u00EDdia (0\u20137)',
        help_priority_media: '7 = m\u00E1xima, 0 = n\u00E3o baixar',
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
        toast_error: 'Erro: '
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
        placeholder_apprise_url: 'tgram://BOT_TOKEN/CHAT_ID',
        section_guardian: '\uD83D\uDEE1\uFE0F Guardian',
        label_check_interval: 'Check interval (seconds, 0 = webhook mode)',
        help_check_interval: '0 disables polling \u2014 use with the qBit webhook script',
        label_valid_extensions: 'Valid media extensions (one per line)',
        label_dangerous_extensions: 'Dangerous extensions (one per line)',
        label_priority_media: 'Media file priority (0\u20137)',
        help_priority_media: '7 = maximum, 0 = skip',
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
        toast_error: 'Error: '
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
 * Walk all elements with [data-i18n] and [data-i18n-placeholder],
 * replacing their text/placeholder with translated strings.
 */
function applyTranslations() {
    // Text content
    var els = document.querySelectorAll('[data-i18n]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n');
        if (key) el.textContent = t(key);
    }

    // Placeholder attributes
    els = document.querySelectorAll('[data-i18n-placeholder]');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var key = el.getAttribute('data-i18n-placeholder');
        if (key) el.placeholder = t(key);
    }

    // Update unit selects (value stays the same, only display text changes)
    var unitSelects = document.querySelectorAll('[data-i18n-units]');
    for (var i = 0; i < unitSelects.length; i++) {
        var sel = unitSelects[i];
        for (var j = 0; j < sel.options.length; j++) {
            var opt = sel.options[j];
            var unitKey = opt.getAttribute('data-i18n-unit');
            if (unitKey) opt.textContent = t(unitKey);
        }
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
