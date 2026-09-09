// ============================================================
// Installation tab: what a fresh clone still lacks and the buttons that supply it.
// Shown first when the database is missing; reachable from the tabs after.
// ============================================================

function CheckLine({ check }) {
    const icon =
        check.state === 'ok'
            ? 'check-circle-2'
            : check.state === 'todo'
              ? 'circle-alert'
              : check.state === 'optional'
                ? 'circle-dashed'
                : 'info';
    const detail = check.detail || {};
    let text = '';
    if (check.id === 'packed')
        text = Object.entries(detail)
            .map(([p, s]) => `${p.split('/').pop()}: ${s}`)
            .join(' · ');
    else if (check.id === 'database')
        text = detail.size_mb ? `${detail.size_mb} MB · ${detail.path}` : detail.path;
    else if (check.id === 'raw_inputs')
        text =
            detail.problems && detail.problems.length
                ? `chybí ${detail.download_mb} MB ke stažení`
                : 'dumpy na disku a ověřené';
    else if (check.id === 'clis')
        text = Object.entries(detail)
            .map(([n, ok]) => `${n} ${ok ? '✓' : '✗'}`)
            .join(' · ');
    else if (check.id === 'hf_token')
        text = (detail.present ? 'token uložen' : 'bez tokenu') + ' · ' + detail.note;
    else text = Object.values(detail).join(' · ');
    return (
        <div
            className={
                'signal' + (check.state === 'todo' ? ' warn' : check.state === 'ok' ? '' : ' muted')
            }
        >
            <Icon name={icon} />
            <span style={{ minWidth: 0 }}>
                <b>{check.label}</b>
                <div className="muted-line" style={{ padding: 0 }}>
                    {text}
                </div>
            </span>
        </div>
    );
}

function Setup({ onReady }) {
    const [status, setStatus] = useState(null);
    const [jobId, setJobId] = useState(null);
    const [hfToken, setHfToken] = useState('');
    const [hfUser, setHfUser] = useState('');
    const job = useJob(jobId);
    useLucide();

    function refresh() {
        getJson('/setup/status')
            .then((s) => {
                setStatus(s);
                if (s.running && !jobId) setJobId(s.running);
            })
            .catch((e) => toast.error(e.message));
    }
    useEffect(refresh, []);

    async function run(payload) {
        try {
            const r = await postJson('/setup/run', payload);
            setJobId(r.job.id);
        } catch (e) {
            toast.error(e.message);
        }
    }
    async function saveToken() {
        try {
            const r = await postJson('/setup/hf-token', { token: hfToken.trim() });
            setHfUser(r.user || 'ok');
            setHfToken('');
            refresh();
        } catch (e) {
            toast.error(e.message);
        }
    }
    function onJobDone() {
        setJobId(null);
        refresh();
    }

    const todo = status ? status.checks.filter((c) => c.state === 'todo') : [];
    const running = job && (job.state === 'queued' || job.state === 'running');
    return (
        <div className="app-body">
            <main className="chat">
                <ChatHead
                    title="Instalace"
                    goal="Co čerstvý klon ještě nemá, a tlačítka, která to doplní"
                />
                <div className="settings-scroll">
                    <div className="settings-inner">
                        {!status && <PanelEmpty icon="loader" text="Zjišťuji stav…" />}
                        {status && (
                            <>
                                <section className="set-sec">
                                    <div className="panel-title">
                                        <Icon
                                            name={status.ready ? 'check-circle-2' : 'circle-alert'}
                                        />
                                        {status.ready
                                            ? 'Stránka může běžet'
                                            : 'Stránka zatím nemůže běžet'}
                                    </div>
                                    <p className="set-hint">
                                        {status.ready
                                            ? 'Snímky jsou rozbalené a databáze sestavená. Modely pro UC-02 a UC-03 se stahují při prvním použití, nebo je stáhněte teď.'
                                            : 'Git nese velké snímky komprimované a databázi nikoli. Tlačítko „Připravit stránku" je rozbalí, sestaví databázi z commitnutých snímků a stáhne oba lokální modely. Překlad recenzí je zmrazený snímek a znovu se nepřekládá.'}
                                    </p>
                                    <div className="signal-list">
                                        {status.checks.map((c) => (
                                            <CheckLine key={c.id} check={c} />
                                        ))}
                                    </div>
                                </section>
                                <section className="set-sec">
                                    <div className="panel-title">
                                        <Icon name="key-round" />
                                        Token Hugging Face (volitelné)
                                    </div>
                                    <p className="set-hint">
                                        Oba stahované modely jsou veřejné, přihlášení nepotřebují.
                                        Token je třeba jen u gated modelů nebo když Hugging Face
                                        omezí anonymní stahování; uloží se tam, kde ho klient hledá
                                        (<code>~/.cache/huggingface/token</code>), a stránka ho
                                        nikdy nezobrazí.
                                    </p>
                                    <div className="set-row compact">
                                        <input
                                            className="num"
                                            style={{ width: 280 }}
                                            type="password"
                                            placeholder="hf_…"
                                            value={hfToken}
                                            onChange={(e) => setHfToken(e.target.value)}
                                        />
                                        <button
                                            className="uc-action ghost"
                                            style={{ margin: 0 }}
                                            disabled={!hfToken.trim() || running}
                                            onClick={saveToken}
                                        >
                                            <Icon name="save" size={16} />
                                            Uložit token
                                        </button>
                                        <span className="muted-line">
                                            {hfUser ? `uložen (účet ${hfUser})` : ''}
                                        </span>
                                    </div>
                                </section>
                                <section className="set-sec">
                                    <div className="panel-title">
                                        <Icon name="play" />
                                        Kroky
                                    </div>
                                    <div className="row-2">
                                        <button
                                            className="uc-action"
                                            disabled={running}
                                            onClick={() => run({ plan: 'minimal' })}
                                            title={status.plans.minimal.join(' → ')}
                                        >
                                            <Icon
                                                name="download"
                                                size={18}
                                                style={{ color: '#fff' }}
                                            />
                                            Připravit stránku (rozbalit, databáze, modely)
                                        </button>
                                        <button
                                            className="uc-action ghost"
                                            disabled={running}
                                            onClick={() => run({ plan: 'full' })}
                                            title={status.plans.full.join(' → ')}
                                        >
                                            <Icon name="refresh-cw" size={18} />
                                            Úplná rekonstrukce ze surových dumpů (1,5 GB)
                                        </button>
                                    </div>
                                    <div className="mini-list">
                                        {Object.entries(status.steps).map(([id, s]) => (
                                            <div className="mini-row col" key={id}>
                                                <span className="t">
                                                    <b>{s.label}</b> · {s.cost}
                                                    <button
                                                        className="linklike"
                                                        disabled={running}
                                                        onClick={() => run({ steps: [id] })}
                                                        style={{ marginLeft: 8 }}
                                                    >
                                                        spustit jen tento krok
                                                    </button>
                                                </span>
                                                <span className="d">
                                                    {s.detail} · <code>{s.command}</code>
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </section>
                                {status.ready && (
                                    <section className="set-sec">
                                        <button
                                            className="uc-action"
                                            onClick={onReady}
                                            disabled={running}
                                        >
                                            <Icon
                                                name="arrow-right"
                                                size={18}
                                                style={{ color: '#fff' }}
                                            />
                                            Otevřít stránku
                                        </button>
                                    </section>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </main>
            <aside className="uc-right">
                <div className="panel-title">
                    <Icon name="activity" />
                    Průběh
                </div>
                {job ? (
                    <JobProgress job={job} onDone={onJobDone} />
                ) : (
                    <PanelEmpty
                        icon="activity"
                        text="Po spuštění kroku se zde ukáže průběh a log."
                    />
                )}
                {status && todo.length > 0 && !running && (
                    <Signal icon="list-checks" warn>
                        Zbývá: {todo.map((c) => c.label).join(' · ')}
                    </Signal>
                )}
                <Signal icon="terminal" muted>
                    Totéž z příkazové řádky:{' '}
                    <code>python -m substrate.pipeline.build_all --force --from database</code>
                </Signal>
            </aside>
        </div>
    );
}

Object.assign(window, { Setup });
