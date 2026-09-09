// ============================================================
// thesis dm — shared helpers: fetch, settings, formatting, hooks
// No datasets live here: everything the page shows comes from the bridge.
// ============================================================
const { useState, useEffect, useRef, useMemo, useCallback } = React;

function Icon({ name, size = 18, className = '', style = {} }) {
    return (
        <span className={'ico ' + className} style={{ width: size, height: size, ...style }}>
            <i data-lucide={name}></i>
        </span>
    );
}
function useLucide() {
    useEffect(() => {
        if (window.lucide) window.lucide.createIcons();
    });
}
function initials(name) {
    return String(name || '?')
        .split(' ')
        .filter(Boolean)
        .map((w) => w[0])
        .slice(0, 2)
        .join('')
        .toUpperCase();
}

// ---- HTTP (the bridge is the only backend; a failure is an error, never a fallback) ----
async function readError(res) {
    let text = await res.text();
    try {
        const data = JSON.parse(text);
        if (data && data.detail)
            text = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch (e) {}
    return new Error(`${res.status}: ${text}`);
}
async function getJson(path, params) {
    const url = params
        ? path +
          '?' +
          new URLSearchParams(
              Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
          )
        : path;
    const res = await fetch(url);
    if (!res.ok) throw await readError(res);
    return res.json();
}
async function sendJson(method, path, payload, keepalive) {
    const res = await fetch(path, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
        keepalive: !!keepalive,
    });
    if (!res.ok) throw await readError(res);
    return res.json();
}
function postJson(path, payload) {
    return sendJson('POST', path, payload);
}
function putJson(path, payload, keepalive) {
    return sendJson('PUT', path, payload, keepalive);
}
async function deleteJson(path) {
    const res = await fetch(path, { method: 'DELETE' });
    if (!res.ok) throw await readError(res);
    return res.json();
}
async function uploadFile(path, file, fields) {
    const form = new FormData();
    form.append('file', file, file.name || 'recording.wav');
    Object.entries(fields || {}).forEach(([k, v]) => form.append(k, v));
    const res = await fetch(path, { method: 'POST', body: form });
    if (!res.ok) throw await readError(res);
    return res.json();
}

// ---- Formatting ----
function escHtml(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
function highlightTokens(text) {
    return escHtml(text).replace(
        /&lt;([A-Z_]+_\d+[a-z]?)&gt;/g,
        '<span class="msg-tok">&lt;$1&gt;</span>',
    );
}
function md(text) {
    if (!text) return '';
    if (window.marked && window.marked.parse) return sanitizeHtml(window.marked.parse(text));
    return '<pre style="white-space:pre-wrap">' + escHtml(text) + '</pre>';
}
// Every HTML that did not come from our own escHtml() passes through DOMPurify: Markdown
// cards from the repository and answers written by a model are both untrusted markup.
function sanitizeHtml(html, allowedTags) {
    if (window.DOMPurify) {
        const opts = allowedTags
            ? { ALLOWED_TAGS: allowedTags, ALLOWED_ATTR: ['href', 'title'] }
            : { USE_PROFILES: { html: true } };
        return window.DOMPurify.sanitize(html, opts);
    }
    return '<pre style="white-space:pre-wrap">' + escHtml(html) + '</pre>';
}
const ANSWER_TAGS = ['p', 'br', 'b', 'strong', 'i', 'em', 'code', 'ul', 'ol', 'li'];
function fmtCalls(x) {
    if (x === null || x === undefined) return '—';
    if (typeof x === 'object')
        return Object.entries(x)
            .map(([k, v]) => `${k} ${v}`)
            .join(', ');
    return String(x);
}
function fmtSeconds(s) {
    if (s === null || s === undefined) return '—';
    const n = Number(s);
    if (!Number.isFinite(n)) return '—';
    if (n < 60) return n.toFixed(n < 10 ? 1 : 0) + ' s';
    return Math.floor(n / 60) + ' min ' + Math.round(n % 60) + ' s';
}
function fmtPct(x, digits = 1) {
    return x === null || x === undefined ? '—' : (Number(x) * 100).toFixed(digits) + ' %';
}
function fmtNum(x, digits = 3) {
    return typeof x === 'number' ? x.toFixed(digits) : '—';
}
function fmtPrice(x) {
    return x === null || x === undefined ? '—' : '$' + Number(x).toFixed(2);
}
function fmtDate(iso) {
    if (!iso) return '—';
    return String(iso).replace('T', ' ').slice(0, 16);
}
function shortRun(name) {
    return String(name || '').replace(/^\d{4}-\d{2}-\d{2}-/, '');
}

// ---- Level labels of the UC-01 ladder (UI copy; the ladder itself comes from the bridge) ----
const LEVEL_LABELS = {
    0: { name: 'Šablona', sub: 'bez personalizace, bez modelu' },
    1: { name: 'Sloučení', sub: 'oslovení a forma dosazené pravidlem' },
    2: { name: 'Morfologie', sub: 'vokativ · Ty/Vy · rod' },
    '3a': { name: 'Jazyk', sub: 'častá slova a styl psaní' },
    '3b': { name: 'Nákupy', sub: 'historie nákupů' },
    '3c': { name: 'Recenze', sub: 'vlastní recenze zákazníka' },
    '3d': { name: 'Role', sub: 'pozice a zaměstnavatel' },
    3: { name: 'Chování', sub: 'jazyk + nákupy + recenze' },
    4: { name: 'Aspekty', sub: '+ hodnocené vlastnosti (ABSA)' },
    5: { name: 'Psychografika', sub: '+ osobnostní profil OCEAN' },
    '6a': { name: 'Doporučení', sub: '+ doporučené produkty z UC-04' },
    '6b': { name: 'Témata', sub: '+ zájmová témata z UC-04' },
    '6c': { name: 'Životní cyklus', sub: '+ fáze vztahu z UC-04' },
    '6d': { name: 'Cena', sub: '+ nabídková cena podle pravidla' },
    6: { name: 'Hyperpersonalizace', sub: 'vše dohromady' },
};
const SLOT_LABELS = {
    frequent_words: 'častá slova',
    style_excerpt: 'ukázka stylu',
    purchases: 'nákupy',
    reviews: 'recenze',
    role: 'role',
    aspects: 'aspekty',
    ocean: 'OCEAN',
    recommendations: 'doporučení UC-04',
    topics: 'témata UC-04',
    lifecycle: 'životní cyklus',
    pricing: 'cena',
};

// ---- Settings: one provider / model / tier for the whole page, kept in the browser ----
const SETTINGS_KEY = 'thesisdm.settings.v3';
function loadSettings() {
    try {
        const raw = localStorage.getItem(SETTINGS_KEY);
        if (raw) return JSON.parse(raw);
    } catch (e) {}
    return null;
}
function saveSettings(s) {
    try {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
    } catch (e) {}
}
function providerOf(catalog, id) {
    return (catalog && catalog.providers.find((p) => p.id === id)) || null;
}
function modelOf(catalog, providerId, modelId) {
    const p = providerOf(catalog, providerId);
    if (!p) return null;
    const alias = p.aliases && p.aliases[modelId];
    return (
        p.models.find(
            (m) => m.id === modelId || m.id === alias || (m.aliases || []).includes(modelId),
        ) || null
    );
}
function tiersOf(catalog, providerId, modelId) {
    const m = modelOf(catalog, providerId, modelId);
    return m && m.tiers ? m.tiers : [];
}
// Reconcile stored settings with the catalog: unknown provider/model -> thesis defaults.
function settingsFromCatalog(catalog, stored) {
    const provider =
        stored && providerOf(catalog, stored.provider) ? stored.provider : catalog.default_provider;
    const p = providerOf(catalog, provider);
    let model = stored && stored.provider === provider ? stored.model : null;
    if (!model || !modelOf(catalog, provider, model))
        model = p.thesis_default_model || p.default_model || (p.models[0] && p.models[0].id);
    const tiers = tiersOf(catalog, provider, model);
    let tier = stored && stored.tier ? stored.tier : catalog.default_tier;
    if (tiers.length && !tiers.includes(tier))
        tier = tiers.includes(catalog.default_tier) ? catalog.default_tier : tiers[0];
    if (!tiers.length) tier = null;
    return { provider, model, tier };
}
function generationFields(settings) {
    return { provider: settings.provider, model: settings.model, tier: settings.tier };
}

// ---- Page history: the thread and the last choices of a tab live in the bridge's runtime
// folder (bridge/.runtime/history/<tab>.json), so a tab switch or a reload keeps them and the
// settings screen can delete them. The file is rewritten a moment after every change. ----
function usePageHistory(tab) {
    const [messages, setMessages] = useState([]);
    const [restored, setRestored] = useState(null); // {thread, state} once the file was read
    const loaded = useRef(false);
    const stateRef = useRef({});
    const threadRef = useRef([]);
    const timer = useRef(null);
    function write(keepalive) {
        timer.current = null;
        putJson(
            '/history/' + tab,
            { thread: threadRef.current.filter((m) => !m.typing), state: stateRef.current },
            keepalive,
        ).catch((e) => toast.error(e.message));
    }
    function schedule() {
        if (!loaded.current) return;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => write(false), 300);
    }
    useEffect(() => {
        let alive = true;
        getJson('/history/' + tab)
            .then((h) => {
                if (!alive) return;
                stateRef.current = h.state || {};
                threadRef.current = h.thread || [];
                setMessages(h.thread || []);
                loaded.current = true;
                setRestored({ thread: h.thread || [], state: h.state || {} });
            })
            .catch((e) => {
                if (!alive) return;
                toast.error(e.message);
                loaded.current = true;
                setRestored({ thread: [], state: {} });
            });
        return () => {
            alive = false;
            if (timer.current) {
                clearTimeout(timer.current);
                write(true);
            }
        };
    }, [tab]);
    useEffect(() => {
        threadRef.current = messages;
        schedule();
    }, [messages]);
    // remember({key: value}) keeps a choice with the thread; applyRestored puts it back.
    function remember(partial) {
        Object.assign(stateRef.current, partial);
        schedule();
    }
    function clearThread() {
        setMessages([]);
    }
    return { messages, setMessages, restored, remember, clearThread };
}
function applyRestored(state, setters) {
    Object.entries(setters).forEach(([key, set]) => {
        if (state && state[key] !== undefined && state[key] !== null) set(state[key]);
    });
}

// ---- Toasts: a failed call reports here; the host (<Toaster/>) is mounted once in App ----
const toastStore = { items: [], listeners: new Set(), seq: 0 };
function emitToasts() {
    toastStore.listeners.forEach((fn) => fn(toastStore.items));
}
function dismissToast(id) {
    const item = toastStore.items.find((t) => t.id === id);
    if (!item) return;
    clearTimeout(item.timer);
    toastStore.items = toastStore.items.filter((t) => t.id !== id);
    emitToasts();
}
function pushToast(kind, text, ms) {
    const msg = String(text || '').trim() || 'Neznámá chyba.';
    // The same text again refreshes the toast already showing instead of stacking a copy
    // (a polling effect can fail several times in a row).
    const same = toastStore.items.find((t) => t.kind === kind && t.text === msg);
    if (same) {
        clearTimeout(same.timer);
        same.timer = setTimeout(() => dismissToast(same.id), ms);
        return same.id;
    }
    const id = ++toastStore.seq;
    const next = [...toastStore.items, { id, kind, text: msg, timer: null }];
    while (next.length > 5) clearTimeout(next.shift().timer);
    next[next.length - 1].timer = setTimeout(() => dismissToast(id), ms);
    toastStore.items = next;
    emitToasts();
    return id;
}
const toast = {
    error: (text) => pushToast('error', text, 9000),
    info: (text) => pushToast('info', text, 4000),
    dismiss: dismissToast,
};
function useToasts() {
    const [items, setItems] = useState(toastStore.items);
    useEffect(() => {
        toastStore.listeners.add(setItems);
        return () => toastStore.listeners.delete(setItems);
    }, []);
    return items;
}

// ---- Hooks ----
function useCatalog() {
    const [catalog, setCatalog] = useState(window.__catalog || null);
    const [error, setError] = useState('');
    useEffect(() => {
        if (window.__catalog) return;
        getJson('/generation/catalog')
            .then((data) => {
                window.__catalog = data;
                setCatalog(data);
            })
            .catch((e) => setError(e.message));
    }, []);
    return { catalog, error };
}

// Poll one job until it ends; returns the latest job record.
function useJob(jobId) {
    const [job, setJob] = useState(null);
    useEffect(() => {
        if (!jobId) {
            setJob(null);
            return;
        }
        let alive = true;
        let timer = null;
        async function tick() {
            try {
                const data = await getJson('/jobs/' + jobId);
                if (!alive) return;
                setJob(data);
                if (data.state === 'queued' || data.state === 'running')
                    timer = setTimeout(tick, 1500);
            } catch (e) {
                if (alive) setJob({ id: jobId, state: 'failed', error: e.message, log: [] });
            }
        }
        tick();
        return () => {
            alive = false;
            if (timer) clearTimeout(timer);
        };
    }, [jobId]);
    return job;
}

Object.assign(window, {
    Icon,
    useLucide,
    initials,
    getJson,
    postJson,
    putJson,
    deleteJson,
    uploadFile,
    escHtml,
    highlightTokens,
    md,
    sanitizeHtml,
    ANSWER_TAGS,
    fmtCalls,
    fmtSeconds,
    fmtPct,
    fmtNum,
    fmtPrice,
    fmtDate,
    shortRun,
    LEVEL_LABELS,
    SLOT_LABELS,
    loadSettings,
    saveSettings,
    providerOf,
    modelOf,
    tiersOf,
    settingsFromCatalog,
    generationFields,
    useCatalog,
    useJob,
    toast,
    useToasts,
    usePageHistory,
    applyRestored,
});
