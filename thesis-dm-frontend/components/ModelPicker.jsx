// ============================================================
// thesis dm — the model picker over the catalog: provider → model → tier.
// One instance in Settings drives every tab; a compact read-out sits in the top bar.
// ============================================================

function ProviderCard({ p, selected, onPick }) {
    const status = p.cli_status || {};
    const cloud = p.id !== 'mock';
    return (
        <button className={'model-card' + (selected ? ' sel' : '')} onClick={() => onPick(p.id)}>
            <div className="top">
                <span className={'mi ' + (cloud ? 'cloud' : 'local')}>
                    <Icon name={cloud ? 'cloud' : 'hard-drive'} size={19} />
                </span>
                <span>
                    <div className="mn">{p.id}</div>
                    <div className="mv">{p.cli ? `CLI ${p.cli}` : 'vestavěný, bez volání'}</div>
                </span>
                <span className="check">
                    <Icon name="check" />
                </span>
            </div>
            <div className="md">
                {p.models.length}{' '}
                {p.models.length === 1 ? 'model' : p.models.length < 5 ? 'modely' : 'modelů'}
                {p.thesis_default_model ? ` · výchozí práce: ${p.thesis_default_model}` : ''}
            </div>
            <div className="meta">
                <span className={'mtag ' + (p.installed ? 'local' : 'warn')}>
                    <Icon name={p.installed ? 'check-circle-2' : 'triangle-alert'} />
                    {p.installed
                        ? status.path || 'k dispozici'
                        : status.message || 'CLI nenalezeno'}
                </span>
                {cloud && (
                    <span className="mtag cloud">
                        <Icon name="globe" />
                        cloud
                    </span>
                )}
            </div>
        </button>
    );
}

function ModelTable({ provider, selectedModel, onPick, compact }) {
    const columns = [
        { key: 'display_name', label: 'Model' },
        { key: 'id', label: 'id' },
        { key: 'tiers', label: 'Úrovně', fmt: (v) => (v && v.length ? v.join(' · ') : '—') },
        { key: 'pricing', label: 'Vstup $/1M', fmt: (v) => fmtPrice(v && v.input) },
        {
            key: 'pricing_out',
            label: 'Výstup $/1M',
            fmt: (v, r) => fmtPrice(r.pricing && r.pricing.output),
        },
        {
            key: 'context_window',
            label: 'Kontext',
            fmt: (v) => (v ? Math.round(v / 1000) + 'k' : '—'),
        },
        { key: 'release_date', label: 'Vydán' },
    ];
    if (compact) columns.splice(1, 1);
    return (
        <div className="table-wrap">
            <table className="rows clickable">
                <thead>
                    <tr>
                        {columns.map((c) => (
                            <th key={c.key}>{c.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {provider.models.map((m) => (
                        <tr
                            key={m.id}
                            className={
                                (selectedModel === m.id ? 'sel' : '') +
                                (m.deprecated ? ' deprecated' : '')
                            }
                            onClick={() => onPick && onPick(m.id)}
                            title={m.deprecated ? 'zastaralý' : m.id}
                        >
                            {columns.map((c) => (
                                <td key={c.key}>
                                    {c.fmt ? c.fmt(m[c.key], m) : (m[c.key] ?? '—')}
                                    {c.key === 'display_name' &&
                                    m.id === provider.thesis_default_model ? (
                                        <span className="pill soft tiny">výchozí</span>
                                    ) : null}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function ModelPicker({ catalog, settings, onChange }) {
    if (!catalog) return <PanelEmpty icon="cpu" text="Katalog modelů se načítá z mostu…" />;
    const provider = providerOf(catalog, settings.provider);
    const tiers = tiersOf(catalog, settings.provider, settings.model);
    function pickProvider(id) {
        onChange(settingsFromCatalog(catalog, { provider: id, model: null, tier: settings.tier }));
    }
    function pickModel(id) {
        onChange(
            settingsFromCatalog(catalog, {
                provider: settings.provider,
                model: id,
                tier: settings.tier,
            }),
        );
    }
    return (
        <>
            <div className="model-grid">
                {catalog.providers.map((p) => (
                    <ProviderCard
                        key={p.id}
                        p={p}
                        selected={settings.provider === p.id}
                        onPick={pickProvider}
                    />
                ))}
            </div>
            <div className="field-label">Model poskytovatele {provider.id}</div>
            <ModelTable provider={provider} selectedModel={settings.model} onPick={pickModel} />
            <div className="set-row">
                <div>
                    <div className="lbl">Úroveň uvažování (tier)</div>
                    <div className="sub">
                        {tiers.length
                            ? `Model ${settings.model} podporuje ${tiers.join(', ')}`
                            : `${settings.provider} tento parametr nepoužívá`}
                    </div>
                </div>
                <span className="grow"></span>
                <div className="seg">
                    {(tiers.length ? tiers : ['n/a']).map((t) => (
                        <button
                            key={t}
                            disabled={t === 'n/a'}
                            className={
                                settings.tier === t || (!tiers.length && t === 'n/a') ? 'on' : ''
                            }
                            onClick={() => t !== 'n/a' && onChange({ ...settings, tier: t })}
                        >
                            {t}
                        </button>
                    ))}
                </div>
            </div>
        </>
    );
}

function ActiveModelLine({ settings, catalog }) {
    const m = catalog ? modelOf(catalog, settings.provider, settings.model) : null;
    return (
        <span>
            {settings.provider}
            {settings.model ? ' / ' + (m && m.display_name ? m.display_name : settings.model) : ''}
            {settings.tier ? ' · ' + settings.tier : ''}
        </span>
    );
}

Object.assign(window, { ProviderCard, ModelTable, ModelPicker, ActiveModelLine });
