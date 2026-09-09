// ============================================================
// Settings tab: the model for every tab, the whole catalog, the LLM switch
// ============================================================

function LlmSwitchSection({ llm }) {
    if (!llm) return null;
    return (
        <section className="set-sec">
            <div className="panel-title">
                <Icon name="power" />
                Volání modelů (LLM)
            </div>
            <p className="set-hint">
                Jeden vypínač pro každé placené nebo externí volání: Codex, Claude, Antigravity
                (Gemini), cloudový přepis. Výchozí stav je <b>vypnuto</b>; bez zapnutí každé takové
                volání skončí chybou 403 a nic se neutratí. Offline provider <b>mock</b> funguje
                vždy. Přepínač nastavuje proměnnou
                <code> THESIS_LLM_CALLS</code> pro běžící most; trvalé nastavení je v souboru{' '}
                <code>.env</code>, skripty mají <code>--force-llm</code>.
            </p>
            <div className="set-row">
                <div>
                    <div className="lbl">Stav</div>
                    <div className="sub">
                        {llm.reachable
                            ? `${llm.enabled ? 'Zapnuto' : 'Vypnuto'} (zdroj: ${llm.source})`
                            : 'Most neběží, stav nelze zjistit ani měnit.'}
                    </div>
                </div>
                <span className="grow"></span>
                <div className="seg">
                    <button
                        className={llm.reachable && !llm.enabled ? 'on' : ''}
                        disabled={!llm.reachable}
                        onClick={() => llm.enabled && llm.toggle()}
                    >
                        VYP
                    </button>
                    <button
                        className={llm.reachable && llm.enabled ? 'on' : ''}
                        disabled={!llm.reachable}
                        onClick={() => !llm.enabled && llm.toggle()}
                    >
                        ZAP
                    </button>
                </div>
            </div>
        </section>
    );
}

function CatalogTable({ catalog }) {
    const rows = [];
    catalog.providers.forEach((p) => {
        p.models.forEach((m) => rows.push({ provider: p.id, ...m }));
    });
    return (
        <RowsTable
            rows={rows}
            columns={[
                { key: 'provider', label: 'Poskytovatel' },
                { key: 'display_name', label: 'Model' },
                { key: 'id', label: 'id' },
                {
                    key: 'tiers',
                    label: 'Úrovně',
                    fmt: (v) => (v && v.length ? v.join(' · ') : '—'),
                },
                { key: 'pricing', label: 'Vstup $/1M', fmt: (v) => fmtPrice(v && v.input) },
                {
                    key: 'pricing2',
                    label: 'Výstup $/1M',
                    fmt: (v, r) => fmtPrice(r.pricing && r.pricing.output),
                },
                {
                    key: 'context_window',
                    label: 'Kontext',
                    fmt: (v) => (v ? Math.round(v / 1000) + 'k' : '—'),
                },
                {
                    key: 'output_tokens',
                    label: 'Výstup max',
                    fmt: (v) => (v ? Math.round(v / 1000) + 'k' : '—'),
                },
                { key: 'knowledge', label: 'Znalosti do' },
                { key: 'release_date', label: 'Vydán' },
                { key: 'deprecated', label: 'Stav', fmt: (v) => (v ? 'zastaralý' : 'aktivní') },
            ]}
        />
    );
}

const HISTORY_TAB_LABELS = {
    uc01: '01 Personalizace',
    uc02: '02 Pseudonymizace',
    uc03: '03 Hlas → CRM',
    uc04: '04 Doporučování',
    code: 'Kód',
};

// The page history: what every tab kept (its thread and last choices) and the buttons that
// delete it. The files live in the bridge's runtime folder, outside git and outside the runs.
function HistorySection() {
    const [summary, setSummary] = useState(null);
    function load() {
        getJson('/history')
            .then(setSummary)
            .catch((e) => toast.error(e.message));
    }
    useEffect(load, []);
    async function remove(tab) {
        try {
            await deleteJson(tab ? '/history/' + tab : '/history');
            toast.info(
                tab
                    ? `Historie záložky ${HISTORY_TAB_LABELS[tab] || tab} smazána.`
                    : 'Historie všech záložek smazána.',
            );
            load();
        } catch (e) {
            toast.error(e.message);
        }
    }
    const total = summary ? summary.tabs.reduce((n, t) => n + t.messages + t.bytes, 0) : 0;
    return (
        <section className="set-sec">
            <div className="panel-title">
                <Icon name="history" />
                Historie stránky
            </div>
            <p className="set-hint">
                Vlákno a poslední volby každé záložky si most ukládá do{' '}
                <code>{summary ? summary.dir : 'bridge/.runtime/history'}</code>, takže přepnutí
                záložky ani obnovení stránky o ně nepřijde. Složka je mimo git a nemá nic společného
                se složkami běhů; tady ji lze smazat.
            </p>
            {summary &&
                summary.tabs.map((t) => (
                    <div className="set-row compact" key={t.tab}>
                        <div>
                            <div className="lbl">{HISTORY_TAB_LABELS[t.tab] || t.tab}</div>
                            <div className="sub">
                                {t.messages || t.bytes
                                    ? `${t.messages} zpráv · ${Math.max(1, Math.round(t.bytes / 1024))} kB · ${fmtDate(t.updated)}`
                                    : 'prázdné'}
                            </div>
                        </div>
                        <span className="grow"></span>
                        <button
                            className="linklike"
                            disabled={!t.messages && !t.bytes}
                            onClick={() => remove(t.tab)}
                        >
                            Smazat
                        </button>
                    </div>
                ))}
            <button
                className="uc-action ghost"
                disabled={!total}
                onClick={() => remove(null)}
                style={{ alignSelf: 'flex-start' }}
            >
                <Icon name="trash-2" size={16} />
                Smazat historii všech záložek
            </button>
        </section>
    );
}

function Settings({ settings, onChange, llm, catalog, catalogError }) {
    useLucide();
    const provider = catalog ? providerOf(catalog, settings.provider) : null;
    const model = catalog ? modelOf(catalog, settings.provider, settings.model) : null;
    return (
        <div className="app-body">
            <main className="chat">
                <ChatHead
                    title="Nastavení"
                    goal="Poskytovatel, model a úroveň uvažování pro všechny záložky; celý katalog modelů"
                />
                <div className="settings-scroll">
                    <div className="settings-inner">
                        <LlmSwitchSection llm={llm} />
                        <HistorySection />
                        <section className="set-sec">
                            <div className="panel-title">
                                <Icon name="cpu" />
                                Poskytovatel a model
                            </div>
                            <p className="set-hint">
                                Volby pocházejí z katalogu{' '}
                                <b>utils/generation/catalog/catalog.json</b> (vygenerován{' '}
                                {catalog ? fmtDate(catalog.generated_at) : '…'}); stránka o modelech
                                nic netvrdí sama. Výchozí práce:{' '}
                                {catalog
                                    ? `${catalog.default_provider} / ${catalog.default_models[catalog.default_provider]} · ${catalog.default_tier}`
                                    : '…'}
                                .
                            </p>
                            <ErrorLine error={catalogError} />
                            <ModelPicker
                                catalog={catalog}
                                settings={settings}
                                onChange={onChange}
                            />
                        </section>
                        {catalog && (
                            <section className="set-sec">
                                <div className="panel-title">
                                    <Icon name="list" />
                                    Celý katalog (
                                    {catalog.providers.reduce(
                                        (n, p) => n + p.models.length,
                                        0,
                                    )}{' '}
                                    modelů)
                                </div>
                                <p className="set-hint">
                                    Každý model, který generační vrstva umí zavolat, s cenou za
                                    milion tokenů, kontextovým oknem a datem vydání.
                                </p>
                                <CatalogTable catalog={catalog} />
                            </section>
                        )}
                    </div>
                </div>
            </main>
            <aside className="uc-right">
                <div className="panel-title">
                    <Icon name="check-circle-2" />
                    Aktivní konfigurace
                </div>
                {llm && (
                    <Signal icon="power" warn={!(llm.reachable && llm.enabled)}>
                        Volání modelů:{' '}
                        {llm.reachable ? (llm.enabled ? 'ZAPNUTO' : 'VYPNUTO') : 'most neběží'}
                    </Signal>
                )}
                <KeyVals
                    rows={[
                        ['Poskytovatel', settings.provider],
                        ['Model', model ? `${model.display_name} (${model.id})` : settings.model],
                        ['Úroveň', settings.tier || 'nepoužívá se'],
                        [
                            'CLI',
                            provider
                                ? provider.installed
                                    ? provider.cli_status.path || 'k dispozici'
                                    : provider.cli_status
                                      ? provider.cli_status.message
                                      : 'neověřeno'
                                : '…',
                        ],
                        [
                            'Vstup $/1M',
                            model && model.pricing ? fmtPrice(model.pricing.input) : null,
                        ],
                        [
                            'Výstup $/1M',
                            model && model.pricing ? fmtPrice(model.pricing.output) : null,
                        ],
                        [
                            'Kontext',
                            model && model.context_window
                                ? Math.round(model.context_window / 1000) + 'k tokenů'
                                : null,
                        ],
                    ]}
                />
                {settings.provider !== 'mock' && (
                    <div
                        className="guide"
                        style={{ background: 'var(--warning-bg)', borderColor: '#f3d79a' }}
                    >
                        <div className="gh" style={{ color: '#8a5806' }}>
                            <Icon name="alert-triangle" size={15} />
                            Pozor na data
                        </div>
                        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.45, color: '#7a4f08' }}>
                            U cloudového poskytovatele odchází prompt k poskytovateli. Pro zkoušku
                            toku bez nákladů zvolte mock.
                        </p>
                    </div>
                )}
                <Signal icon="info" muted>
                    UC-03 používá vybraný Claude, Codex nebo agy jako hostitele MCP. Ostatní poskytovatele
                    zatím odmítne bez náhrady; změna nastavení otevírá novou konverzaci.
                </Signal>
            </aside>
        </div>
    );
}

Object.assign(window, { Settings });
