// ============================================================
// thesis dm — app root: tab routing, the catalog, the settings, the LLM switch
// ============================================================

// The LLM switch lives in the bridge process (THESIS_LLM_CALLS). The page
// only mirrors it; every endpoint that could call a model checks it server-side.
function useLlmSwitch() {
    const [state, setState] = useState({ enabled: false, source: 'unknown', reachable: false });
    function refresh() {
        fetch('/llm-switch')
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
                if (data) setState({ ...data, reachable: true });
            })
            .catch(() => setState((s) => ({ ...s, reachable: false })));
    }
    function toggle() {
        fetch('/llm-switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: !state.enabled }),
        })
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
                if (data) setState({ ...data, reachable: true });
            })
            .catch(() => {});
    }
    useEffect(refresh, []);
    return { ...state, toggle, refresh };
}

function App() {
    const [tab, setTab] = useState('uc1');
    const { catalog, error: catalogError } = useCatalog();
    const [settings, setSettings] = useState(
        () => loadSettings() || { provider: 'codex', model: null, tier: 'low' },
    );
    const llm = useLlmSwitch();
    useLucide();

    // A fresh clone lands on the installation screen until the database exists.
    useEffect(() => {
        getJson('/setup/status')
            .then((s) => {
                if (!s.ready) setTab('setup');
            })
            .catch(() => {});
    }, []);

    // Once the catalog is here, reconcile what the browser remembered with what exists.
    useEffect(() => {
        if (!catalog) return;
        const next = settingsFromCatalog(catalog, settings);
        if (
            next.provider !== settings.provider ||
            next.model !== settings.model ||
            next.tier !== settings.tier
        ) {
            setSettings(next);
            saveSettings(next);
        }
    }, [catalog]);

    function updateSettings(next) {
        setSettings(next);
        saveSettings(next);
    }

    const common = { settings, catalog, llm };
    let view = null;
    if (tab === 'uc1') view = <Uc01 {...common} />;
    else if (tab === 'uc2') view = <Uc02 {...common} />;
    else if (tab === 'uc3') view = <Uc03 {...common} />;
    else if (tab === 'uc4') view = <Uc04 {...common} />;
    else if (tab === 'code') view = <UcCode {...common} />;
    else if (tab === 'setup') view = <Setup onReady={() => setTab('uc1')} />;
    else if (tab === 'settings')
        view = (
            <Settings
                settings={settings}
                onChange={updateSettings}
                llm={llm}
                catalog={catalog}
                catalogError={catalogError}
            />
        );

    return (
        <div className="app">
            <TopBar active={tab} onTab={setTab} settings={settings} catalog={catalog} llm={llm} />
            {/* key forces a clean remount of per-tab state when switching */}
            <React.Fragment key={tab}>{view}</React.Fragment>
            <Toaster />
        </div>
    );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
