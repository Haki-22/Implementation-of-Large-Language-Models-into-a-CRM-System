// ============================================================
// thesis dm — small reusable pieces: error line, sub-tabs, key/value rows,
// token map, tool calls, audit trail, check rows, fold, toasts, picker fold
// ============================================================

function ErrorLine({ error }) {
    if (!error) return null;
    return (
        <div className="signal warn">
            <Icon name="circle-alert" />
            <span style={{ wordBreak: 'break-word' }}>{error}</span>
        </div>
    );
}

function Signal({ icon, children, warn, muted, title }) {
    return (
        <div className={'signal' + (warn ? ' warn' : '') + (muted ? ' muted' : '')} title={title}>
            <Icon name={icon} />
            <span style={{ minWidth: 0, wordBreak: 'break-word' }}>{children}</span>
        </div>
    );
}

// Sub-tabs inside a panel: items = [{id, label, badge}]
function SubTabs({ items, active, onChange }) {
    return (
        <div className="subtabs">
            {items.map((t) => (
                <button
                    key={t.id}
                    className={active === t.id ? 'on' : ''}
                    onClick={() => onChange(t.id)}
                >
                    {t.label}
                    {t.badge !== undefined && t.badge !== null && (
                        <span className="badge">{t.badge}</span>
                    )}
                </button>
            ))}
        </div>
    );
}

function KeyVals({ rows }) {
    return (
        <div className="kv">
            {rows
                .filter((r) => r && r[1] !== undefined && r[1] !== null && r[1] !== '')
                .map(([k, v], i) => (
                    <div className="kv-row" key={i}>
                        <span className="k">{k}</span>
                        <span className="v">{v}</span>
                    </div>
                ))}
        </div>
    );
}

// mapping rows: {token, surface_form|value, pii_type, source}
function TokenMap({ mapping }) {
    if (!mapping || !mapping.length)
        return (
            <PanelEmpty
                icon="table-2"
                text="Po zamaskování se zde zobrazí dvojice token → hodnota."
            />
        );
    return (
        <div className="tokmap">
            {mapping.map((m, i) => {
                const src =
                    m.source ||
                    (['PERSON', 'ORG', 'ADDRESS', 'DATE', 'LOC'].includes(m.pii_type)
                        ? 'ner'
                        : 'rules');
                return (
                    <div className="tm" key={i}>
                        <span className="tok">{m.token}</span>
                        <Icon name="arrow-right" size={13} className="arrow" />
                        <span className="orig">{m.surface_form ?? m.value}</span>
                        <span className={'ty ' + (src === 'ner' ? 'ner' : 'det')}>
                            {src === 'ner' ? 'NER' : 'pravidlo'}
                        </span>
                    </div>
                );
            })}
        </div>
    );
}

function iconForTool(tool) {
    const t = String(tool || '');
    if (t === 'ping' || t === 'server_info') return 'server';
    if (t === 'whoami') return 'badge-info';
    if (t.startsWith('search')) return 'search';
    if (t.startsWith('get_') || t === 'list_orders') return 'user';
    if (t === 'create_note') return 'file-plus';
    if (t.startsWith('update_') || t.startsWith('delete_')) return 'pencil';
    if (t === 'query_sql') return 'database';
    return 'terminal';
}

// tool_calls: [{tool, input, output}]
function toolCallsHtml(calls) {
    if (!calls || !calls.length)
        return '<p style="margin:0;color:var(--fg3)">Model nezavolal žádný nástroj.</p>';
    return calls
        .map((c) =>
            c.from_audit
                ? `<div class="toolcall"><div class="tc-name">${escHtml(c.tool)}()</div><div class="muted-line">z auditního řetězu · args_hash ${escHtml(String(c.args_hash || '').slice(0, 16))} (argumenty se logují jen jako hash)</div></div>`
                : `<div class="toolcall"><div class="tc-name">${escHtml(c.tool)}(${escHtml(
                      Object.entries(c.input || {})
                          .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                          .join(', '),
                  )})</div><pre class="tc-out">${escHtml(String(c.output || '').slice(0, 600))}</pre></div>`,
        )
        .join('');
}

function AuditTrail({ entries, verify }) {
    if (!entries || !entries.length)
        return (
            <PanelEmpty
                icon="scroll-text"
                text="Volání nástrojů se zde objeví po odpovědi modelu."
            />
        );
    return (
        <>
            {verify && (
                <Signal icon={verify.ok ? 'shield-check' : 'shield-alert'} warn={!verify.ok}>
                    Řetěz: {verify.ok ? 'ověřen' : 'PORUŠEN'} · {verify.entries ?? entries.length}{' '}
                    záznamů · {verify.message}
                </Signal>
            )}
            <div className="audit">
                {entries.map((e, i) => (
                    <div className="row" key={(e.seq ?? i) + '-' + (e.this_hash || '')}>
                        <div className="rail">
                            <div className="node">
                                <Icon name={iconForTool(e.tool)} />
                            </div>
                            {i < entries.length - 1 && <div className="line"></div>}
                        </div>
                        <div className="body">
                            <div className="tool">
                                #{e.seq ?? i} {e.tool}()
                            </div>
                            <div className="args">
                                args_hash {String(e.args_hash || '').slice(0, 16)} ·{' '}
                                {e.author || ''}
                            </div>
                            <div className="meta">
                                <span>{e.ts || ''}</span>
                                <span className="hash">
                                    {String(e.this_hash || '').slice(0, 10)}
                                </span>
                                <span className="hash">
                                    ← {String(e.prev_hash || '').slice(0, 10) || 'genesis'}
                                </span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </>
    );
}

function CheckRow({ label, ok, note }) {
    const state = ok === null || ok === undefined ? 'na' : ok ? 'ok' : 'no';
    return (
        <div className={'check-row ' + state} title={note || ''}>
            <span className="lbl">{label}</span>
            <span className="res">
                <Icon
                    name={
                        state === 'ok'
                            ? 'check-circle-2'
                            : state === 'no'
                              ? 'x-circle'
                              : 'minus-circle'
                    }
                    size={14}
                />
                {state === 'ok' ? 'OK' : state === 'no' ? 'chyba' : 'nekontrolováno'}
            </span>
        </div>
    );
}

// rules: the RulesVerdict dict of UC-01
function rulesHtml(rules) {
    if (!rules) return '';
    const unchecked = new Set(rules.unchecked || []);
    const row = (label, key, ok) => {
        const state = unchecked.has(key) ? 'na' : ok ? 'ok' : 'no';
        const txt =
            state === 'ok' ? 'OK' : state === 'no' ? 'chyba' : 'nekontrolováno (pole chybí)';
        return `<div class="check-row ${state}"><span class="lbl">${label}</span><span class="res">${txt}</span></div>`;
    };
    let out = '<div class="checks">';
    out += row('Oslovení (vokativ)', 'vocative', rules.vocative_ok);
    out += row('Forma (Ty / Vy)', 'register', rules.register_ok);
    out += row('Gramatický rod', 'gender', rules.gender_ok);
    if (rules.pricing_sites && rules.pricing_sites.length)
        out += row('Cena a věta o ceně', 'pricing', rules.pricing_ok);
    if (rules.duplicate_greeting)
        out += `<div class="check-row no"><span class="lbl">Zdvojené oslovení</span><span class="res">chyba</span></div>`;
    if (rules.instruction_bleed && rules.instruction_bleed.length)
        out += `<div class="check-row no"><span class="lbl">Prosáklá instrukce</span><span class="res">${escHtml(rules.instruction_bleed.join(', '))}</span></div>`;
    out += '</div>';
    if (rules.failures && rules.failures.length)
        out += `<div class="muted-line">Selhání: ${escHtml(rules.failures.join(', '))}</div>`;
    return out;
}

function ProgressBar({ done, total }) {
    const pct = total ? Math.min(100, Math.round((100 * (done || 0)) / total)) : null;
    return (
        <div className="progress">
            <div className="progress-track">
                <div
                    className={'progress-fill' + (pct === null ? ' indeterminate' : '')}
                    style={pct === null ? {} : { width: pct + '%' }}
                ></div>
            </div>
            <span className="progress-label">{total ? `${done || 0} / ${total}` : 'běží…'}</span>
        </div>
    );
}

// The toast host: mounted once in App. toast.error(text) from anywhere puts a line here;
// it goes away on its own or on the close button.
function Toaster() {
    const items = useToasts();
    useLucide();
    if (!items.length) return null;
    return (
        <div className="toaster" role="status" aria-live="polite">
            {items.map((t) => (
                <div className={'toast ' + t.kind} key={t.id}>
                    <Icon name={t.kind === 'error' ? 'circle-alert' : 'info'} size={16} />
                    <span className="toast-text">{t.text}</span>
                    <button
                        className="toast-close"
                        onClick={() => toast.dismiss(t.id)}
                        title="Zavřít"
                    >
                        <Icon name="x" size={14} />
                    </button>
                </div>
            ))}
        </div>
    );
}

// A picker folded to one line: the label, the current choice, a chevron. The list opens on
// click and the caller closes it again once a choice is made.
function PickerFold({ label, value, open, onToggle, children }) {
    return (
        <div className={'picker' + (open ? ' open' : '')}>
            <button className="picker-head" onClick={onToggle} aria-expanded={!!open}>
                <span className="picker-label">{label}</span>
                <span className="picker-value" title={typeof value === 'string' ? value : ''}>
                    {value}
                </span>
            </button>
            {open && <div className="picker-body">{children}</div>}
        </div>
    );
}

Object.assign(window, {
    ErrorLine,
    Signal,
    SubTabs,
    KeyVals,
    TokenMap,
    iconForTool,
    toolCallsHtml,
    AuditTrail,
    CheckRow,
    rulesHtml,
    ProgressBar,
    Toaster,
    PickerFold,
});
