// ============================================================
// thesis dm — top bar with the tabs, the LLM switch pill and the active-model pill
// ============================================================
const TABS = [
    { id: 'uc1', tag: '01', label: 'Personalizace' },
    { id: 'uc2', tag: '02', label: 'Pseudonymizace' },
    { id: 'uc3', tag: '03', label: 'Hlas → CRM' },
    { id: 'uc4', tag: '04', label: 'Doporučování' },
    { id: 'code', tag: '—', label: 'Kód' },
    { id: 'settings', tag: '⚙', label: 'Nastavení' },
    { id: 'setup', tag: '⬇', label: 'Instalace' },
];

// One click flips THESIS_LLM_CALLS in the bridge process. OFF is the default,
// so nothing spends quota until someone deliberately switches it on.
function LlmSwitchPill({ llm }) {
    if (!llm.reachable) {
        return (
            <span className="model-pill" title="Most (bridge) neběží; volání modelů nelze zapnout">
                <span className="dot"></span>
                <span className="nm">LLM: bez mostu</span>
            </span>
        );
    }
    return (
        <button
            className="model-pill"
            onClick={llm.toggle}
            title={
                llm.enabled
                    ? 'Volání modelů jsou ZAPNUTÁ (klik = vypnout)'
                    : 'Volání modelů jsou VYPNUTÁ (klik = zapnout)'
            }
        >
            <span className={'dot ' + (llm.enabled ? 'cloud' : 'local')}></span>
            <span className="nm">LLM: {llm.enabled ? 'ZAP' : 'VYP'}</span>
        </button>
    );
}

function TopBar({ active, onTab, settings, catalog, llm }) {
    return (
        <header className="topbar">
            <div className="brand">
                <img src="assets/logo.svg" alt="" />
                thesis dm
            </div>
            <nav className="nav">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        className={active === t.id ? 'active' : ''}
                        onClick={() => onTab(t.id)}
                    >
                        <span className="tag">{t.tag}</span>
                        {t.label}
                    </button>
                ))}
            </nav>
            <div className="spacer"></div>
            {llm ? <LlmSwitchPill llm={llm} /> : null}
            <button className="model-pill" onClick={() => onTab('settings')} title="Změnit model">
                <span
                    className={'dot ' + (settings.provider === 'mock' ? 'local' : 'cloud')}
                ></span>
                <span className="nm">
                    <ActiveModelLine settings={settings} catalog={catalog} />
                </span>
                <Icon name="chevron-down" size={14} />
            </button>
        </header>
    );
}

Object.assign(window, { TopBar, TABS, LlmSwitchPill });
