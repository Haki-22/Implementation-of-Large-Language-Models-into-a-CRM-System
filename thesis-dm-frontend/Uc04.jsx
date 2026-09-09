// ============================================================
// UC-04 tab: the hidden last purchase against every arm's list; runs as jobs
// ============================================================

function Uc04({ settings, llm }) {
    const [arms, setArms] = useState(null);
    const [customers, setCustomers] = useState([]);
    const [scope, setScope] = useState('pick');
    const [customerId, setCustomerId] = useState(null);
    const [searching, setSearching] = useState(false);
    const [selectedArms, setSelectedArms] = useState(['popularity', 'als_cf']);
    const [selectedMethods, setSelectedMethods] = useState(['rerank_als']);
    const [langs, setLangs] = useState(['en', 'cs']);
    const [regimes, setRegimes] = useState(['crm']);
    const [limit, setLimit] = useState(10);
    const [protocol, setProtocol] = useState('sampled');
    const [runs, setRuns] = useState([]);
    const [runKind, setRunKind] = useState('arena');
    const [runSel, setRunSel] = useState('');
    const [runDetail, setRunDetail] = useState(null);
    const [recordArena, setRecordArena] = useState('');
    const { messages, setMessages, restored, remember, clearThread } = usePageHistory('uc04');
    const [busy, setBusy] = useState(false);
    const [jobId, setJobId] = useState(null);
    const [results, setResults] = useState(null);
    const [rightTab, setRightTab] = useState('customer');
    const job = useJob(jobId);
    const { card, loading: cardLoading, error: cardError } = useContactCard(customerId);
    const [openPicker, setOpenPicker] = useState(false);
    useLucide();
    useEffect(() => {
        if (restored)
            applyRestored(restored.state, {
                scope: setScope,
                customerId: setCustomerId,
                selectedArms: setSelectedArms,
                selectedMethods: setSelectedMethods,
                langs: setLangs,
                regimes: setRegimes,
                limit: setLimit,
                protocol: setProtocol,
                runKind: setRunKind,
                runSel: setRunSel,
                rightTab: setRightTab,
            });
    }, [restored]);
    useEffect(
        () =>
            remember({
                scope,
                customerId,
                selectedArms,
                selectedMethods,
                langs,
                regimes,
                limit,
                protocol,
                runKind,
                runSel,
                rightTab,
            }),
        [
            scope,
            customerId,
            selectedArms,
            selectedMethods,
            langs,
            regimes,
            limit,
            protocol,
            runKind,
            runSel,
            rightTab,
        ],
    );
    const selectedCustomer = customers.find((c) => c.id === customerId);
    const customerLabel = selectedCustomer
        ? `${selectedCustomer.name} · #${selectedCustomer.id}`
        : card
          ? `${card.name} · #${card.id}`
          : customerId
            ? '#' + customerId
            : 'vyberte zákazníka';

    function loadRuns() {
        return getJson('/uc04/runs')
            .then((d) => {
                setRuns(d.runs || []);
                setRecordArena(d.record_arena || '');
                if (!runSel && d.record_arena) setRunSel(d.record_arena);
            })
            .catch((e) => toast.error(e.message));
    }
    useEffect(() => {
        getJson('/uc04/arms')
            .then(setArms)
            .catch((e) => toast.error(e.message));
        loadRuns();
    }, []);
    useEffect(() => {
        loadCustomers('');
    }, [scope]);
    useEffect(() => {
        if (rightTab === 'results' && !results)
            getJson('/uc04/results')
                .then(setResults)
                .catch((e) => toast.error(e.message));
    }, [rightTab]);
    useEffect(() => {
        if (!runSel) return;
        setRunDetail(null);
        getJson('/uc04/runs/' + runSel)
            .then(setRunDetail)
            .catch((e) => toast.error(e.message));
    }, [runSel]);

    async function loadCustomers(query) {
        setSearching(true);
        try {
            const d = await getJson(
                '/uc04/customers',
                query ? { q: query, limit: 40 } : { scope, limit: 40 },
            );
            setCustomers(d.customers || []);
            if (d.customers.length && !d.customers.some((c) => c.id === customerId))
                setCustomerId(d.customers[0].id);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setSearching(false);
        }
    }

    function toggle(list, value, setter) {
        setter(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
    }

    const arenaRun = runs.find((r) => r.name === runSel && r.kind === 'arena')
        ? runSel
        : recordArena;

    async function recommend() {
        if (busy || !customerId) return;
        setBusy(true);
        const c = customers.find((x) => x.id === customerId) || { name: '#' + customerId };
        setMessages((m) => [
            ...m,
            {
                role: 'user',
                text: [
                    `Doporuč pro <b>${escHtml(c.name)}</b> — běh ${escHtml(shortRun(arenaRun))}, protokol ${protocol}`,
                ],
            },
            { role: 'ai', typing: true },
        ]);
        try {
            const d = await getJson('/uc04/customers/' + customerId, { run: arenaRun });
            const rows = d.arms
                .filter((a) => a.protocol === protocol && regimes.includes(a.regime || 'crm'))
                .sort((a, b) => (a.rank || 1e9) - (b.rank || 1e9));
            const hidden = d.hidden
                ? `<p style="margin:0 0 8px">Skrytý poslední nákup: <b>${escHtml(d.hidden.title_cs)}</b>${d.hidden.title_cs !== d.hidden.title ? ` <span class="muted-inline">(${escHtml(d.hidden.title)})</span>` : ''}</p>`
                : '<p>Zákazník v tomto běhu není.</p>';
            const table = rows.length
                ? `<table class="rows"><thead><tr><th>rameno</th><th>větev</th><th>režim</th><th>pořadí</th><th>v top 10</th></tr></thead><tbody>${rows
                      .map(
                          (a) =>
                              `<tr class="${a.hit_in_top10 ? 'hit' : ''}"><td>${escHtml(a.arm)}</td><td>${escHtml(a.branch)}</td><td>${escHtml(a.regime || '')}</td><td>${a.rank ?? '—'}</td><td>${a.hit_in_top10 ? '✓' : '—'}</td></tr>`,
                      )
                      .join('')}</tbody></table>`
                : '<div class="muted-line">Žádné rameno pro zvolený protokol a režim.</div>';
            const folds = rows.map((a) => ({
                title: `${a.arm} · ${a.branch} · ${a.regime || ''} — top 10`,
                html: `<ol class="toplist">${a.top10.map((t) => `<li class="${t.hit ? 'hit' : ''}">${escHtml(t.title)}${t.hit ? ' <b>← skrytý</b>' : ''}</li>`).join('')}</ol>`,
            }));
            if (d.handoff) {
                const h = d.handoff;
                folds.unshift({
                    title: 'Slovní výstupy pro UC-01 (zdůvodnění, persona, aspekty)',
                    html:
                        (h.persona
                            ? `<p><b>Persona:</b> ${escHtml(h.persona.narrative_cs || h.persona.label || '')}</p>`
                            : '') +
                        (h.recommendations && h.recommendations.length
                            ? `<ol class="toplist">${h.recommendations.map((r) => `<li><b>${escHtml(r.title)}</b> — ${escHtml(r.reason || '')}</li>`).join('')}</ol>`
                            : '') +
                        (h.aspects
                            ? `<p><b>Aspekty:</b> ${escHtml(JSON.stringify(h.aspects).slice(0, 400))}</p>`
                            : '') +
                        (h.topic_clusters && h.topic_clusters.length
                            ? `<p><b>Témata:</b> ${escHtml(h.topic_clusters.map((t) => t.label || t.name || JSON.stringify(t)).join(', '))}</p>`
                            : '') +
                        (h.lifecycle
                            ? `<p><b>Fáze vztahu:</b> ${escHtml(h.lifecycle.stage || JSON.stringify(h.lifecycle))}</p>`
                            : ''),
                });
            }
            setMessages((m) => {
                const next = m.slice(0, -1);
                next.push({
                    role: 'ai',
                    html: hidden + table,
                    meta: `${rows.filter((a) => a.hit_in_top10).length} z ${rows.length} seznamů má skrytý nákup v top 10 · protokol ${protocol}`,
                    folds,
                });
                return next;
            });
        } catch (e) {
            toast.error(e.message);
            setMessages((m) => m.slice(0, -1));
        } finally {
            setBusy(false);
        }
    }

    async function runArena() {
        if (jobId) return;
        try {
            const r = await postJson('/uc04/run', { arms: selectedArms, langs, regimes });
            setJobId(r.job.id);
            setRightTab('runs');
            setMessages((m) => [
                ...m,
                {
                    role: 'user',
                    text: [
                        `Spusť arénu: ${escHtml(selectedArms.join(', '))} · ${langs.join(', ')} · ${regimes.join(', ')}`,
                    ],
                },
            ]);
        } catch (e) {
            toast.error(e.message);
        }
    }
    async function runModel() {
        if (jobId) return;
        try {
            const r = await postJson('/uc04/model-run', {
                methods: selectedMethods,
                langs,
                limit: Number(limit),
                ...generationFields(settings),
            });
            setJobId(r.job.id);
            setRightTab('runs');
            setMessages((m) => [
                ...m,
                {
                    role: 'user',
                    text: [
                        `Spusť modelové metody: ${escHtml(selectedMethods.join(', '))} · ${langs.join(', ')} · ${limit} zákazníků · ${escHtml(settings.provider)}${settings.model ? ' / ' + escHtml(settings.model) : ''} (role comparison)`,
                    ],
                },
            ]);
        } catch (e) {
            toast.error(e.message);
        }
    }
    function onJobDone(j) {
        setJobId(null);
        loadRuns().then(() => {
            if (j.result && j.result.run_dir) {
                setRunKind(j.result.kind || 'arena');
                setRunSel(j.result.run_dir);
            }
        });
        setMessages((m) => [
            ...m,
            {
                role: 'ai',
                html:
                    j.state === 'done'
                        ? `<p style="margin:0"><b>Běh doběhl.</b> Složka ${escHtml(j.result.run_dir)}; karta a tabulka jsou vpravo v záložce Běhy.</p>`
                        : `<p style="margin:0"><b>Běh selhal:</b> ${escHtml(j.error || '')}</p>`,
            },
        ]);
    }

    const runsOfKind = runs.filter((r) => r.kind === runKind);
    const rowColumns =
        runDetail && runDetail.kind === 'model'
            ? [
                  { key: 'method', label: 'metoda' },
                  { key: 'branch', label: 'větev' },
                  { key: 'protocol', label: 'protokol' },
                  { key: 'hits_top10', label: 'zásahy@10' },
                  { key: 'customers', label: 'n' },
                  {
                      key: 'calls',
                      label: 'volání',
                      fmt: (v) =>
                          v && typeof v === 'object'
                              ? Object.entries(v)
                                    .map(([k, n]) => `${k} ${n}`)
                                    .join(', ')
                              : (v ?? '—'),
                  },
              ]
            : [
                  { key: 'arm', label: 'rameno' },
                  { key: 'branch', label: 'větev' },
                  { key: 'regime', label: 'režim' },
                  { key: 'protocol', label: 'protokol' },
                  { key: 'hits_top10', label: 'zásahy@10' },
                  { key: 'customers', label: 'n' },
                  { key: 'hr_top10', label: 'HR@10', fmt: (v) => fmtPct(v) },
                  { key: 'seconds', label: 's', fmt: (v) => fmtSeconds(v) },
              ];

    return (
        <UseCaseShell
            left={
                <>
                    <Guide
                        steps={[
                            'Vyberte <b>zákazníka</b>; vpravo je jeho karta.',
                            '<b>Doporuč</b> ukáže skrytý poslední nákup proti seznamu každého ramene zvoleného běhu.',
                            '<b>Spusť arénu</b> přepočítá klasická ramena (bez modelu) do nové složky; <b>modelové metody</b> běží na vzorku a jen jako srovnání.',
                            'Karty a tabulky běhů jsou vpravo v záložce Běhy.',
                        ]}
                    />
                    <PickerFold
                        label="Zákazník"
                        value={customerLabel}
                        open={openPicker}
                        onToggle={() => setOpenPicker((o) => !o)}
                    >
                        <div className="seg" style={{ alignSelf: 'flex-start', marginBottom: 6 }}>
                            <button
                                className={scope === 'pick' ? 'on' : ''}
                                onClick={() => setScope('pick')}
                            >
                                výběr UC-01
                            </button>
                            <button
                                className={scope === 'sample' ? 'on' : ''}
                                onClick={() => setScope('sample')}
                            >
                                vzorek 100
                            </button>
                        </div>
                        <PersonList
                            contacts={customers}
                            value={customerId}
                            onChange={(id) => {
                                setCustomerId(id);
                                setOpenPicker(false);
                            }}
                            onSearch={loadCustomers}
                            searching={searching}
                        />
                    </PickerFold>
                    <div className="field-label">Protokol pro čtení</div>
                    <div className="seg" style={{ alignSelf: 'flex-start' }}>
                        <button
                            className={protocol === 'sampled' ? 'on' : ''}
                            onClick={() => setProtocol('sampled')}
                            title="1 skrytý + 100 nekoupených; náhoda 9,9 %"
                        >
                            vzorkovaný
                        </button>
                        <button
                            className={protocol === 'full' ? 'on' : ''}
                            onClick={() => setProtocol('full')}
                            title="celý katalog 18 213 produktů; náhoda 0,1 %"
                        >
                            celý katalog
                        </button>
                    </div>
                    <button
                        className="uc-action"
                        disabled={busy || !customerId || !arenaRun}
                        onClick={recommend}
                    >
                        <Icon name="target" size={18} style={{ color: '#fff' }} />
                        Doporuč (přečti běh)
                    </button>
                    <div className="field-label">Klasická ramena</div>
                    <div className="chip-col wrap">
                        {(arms ? arms.classical : []).map((a) => (
                            <button
                                key={a.name}
                                className={
                                    'chip-line small' +
                                    (selectedArms.includes(a.name) ? ' sel' : '')
                                }
                                onClick={() => toggle(selectedArms, a.name, setSelectedArms)}
                                title={a.description}
                            >
                                <span className="brief-title">
                                    {a.name}
                                    {a.slow && <span className="pill tiny warn">pomalé</span>}
                                </span>
                                <span className="brief-sub">{a.title}</span>
                            </button>
                        ))}
                    </div>
                    <div className="row-2">
                        <div className="seg">
                            {['en', 'cs'].map((l) => (
                                <button
                                    key={l}
                                    className={langs.includes(l) ? 'on' : ''}
                                    onClick={() => toggle(langs, l, setLangs)}
                                >
                                    {l}
                                </button>
                            ))}
                        </div>
                        <div className="seg">
                            {(arms ? arms.regimes : ['crm']).map((r) => (
                                <button
                                    key={r}
                                    className={regimes.includes(r) ? 'on' : ''}
                                    onClick={() => toggle(regimes, r, setRegimes)}
                                    title={
                                        r === 'population'
                                            ? 'učí se z veřejného dumpu recenzí'
                                            : 'jen CRM'
                                    }
                                >
                                    {r}
                                </button>
                            ))}
                        </div>
                    </div>
                    <button
                        className="uc-action ghost"
                        disabled={
                            !!jobId || !selectedArms.length || !langs.length || !regimes.length
                        }
                        onClick={runArena}
                    >
                        <Icon name="rotate-cw" size={18} />
                        {jobId ? 'Běh probíhá…' : 'Spusť arénu (bez modelu)'}
                    </button>
                    <div className="field-label">Modelové metody (srovnání na vzorku)</div>
                    <div className="chip-col wrap">
                        {(arms ? arms.methods : []).map((m) => (
                            <button
                                key={m.name}
                                className={
                                    'chip-line small' +
                                    (selectedMethods.includes(m.name) ? ' sel' : '')
                                }
                                onClick={() => toggle(selectedMethods, m.name, setSelectedMethods)}
                                title={m.description}
                            >
                                <span className="brief-title">{m.name}</span>
                                <span className="brief-sub">{m.title}</span>
                            </button>
                        ))}
                    </div>
                    <div className="set-row compact">
                        <div>
                            <div className="lbl">Zákazníků ze vzorku</div>
                            <div className="sub">
                                {settings.provider}
                                {settings.model ? ' / ' + settings.model : ''}
                                {settings.tier ? ' · ' + settings.tier : ''}
                            </div>
                        </div>
                        <span className="grow"></span>
                        <input
                            className="num"
                            type="number"
                            min="1"
                            max="100"
                            value={limit}
                            onChange={(e) => setLimit(e.target.value)}
                        />
                    </div>
                    <button
                        className="uc-action ghost"
                        disabled={
                            !!jobId ||
                            !selectedMethods.length ||
                            !langs.length ||
                            (settings.provider !== 'mock' && !(llm && llm.enabled))
                        }
                        onClick={runModel}
                        title={
                            settings.provider !== 'mock' && !(llm && llm.enabled)
                                ? 'Zapněte volání modelů v Nastavení'
                                : ''
                        }
                    >
                        <Icon name="bot" size={18} />
                        {jobId ? 'Běh probíhá…' : 'Spusť modelové metody'}
                    </button>
                </>
            }
            center={
                messages.length ? (
                    <Chat
                        title="Matchmaker zákazník × produkt"
                        goal="Stejná úloha, stejné vstupy, stejná metrika pro klasické ML i jazykový model"
                        builds="předává do UC-01 (6a–6d)"
                        messages={messages}
                        onClear={clearThread}
                        empty={
                            <PanelEmpty
                                icon="target"
                                text="Vyberte zákazníka a klikněte na Doporuč; nebo spusťte běh."
                            />
                        }
                        honest="Pravdu drží chronologicky poslední nákup; měří se, zda je v prvních K doporučeních."
                    />
                ) : null
            }
            right={
                <>
                    {job && <JobProgress job={job} onDone={onJobDone} />}
                    <SubTabs
                        items={[
                            { id: 'customer', label: 'Zákazník' },
                            { id: 'runs', label: 'Běhy', badge: runs.length || null },
                            { id: 'results', label: 'Výsledky' },
                        ]}
                        active={rightTab}
                        onChange={setRightTab}
                    />
                    {rightTab === 'customer' && (
                        <PersonCard
                            card={card}
                            loading={cardLoading}
                            error={cardError}
                            emphasis="orders"
                        />
                    )}
                    {rightTab === 'runs' && (
                        <>
                            <div className="subtabs small">
                                {[
                                    ['arena', 'aréna'],
                                    ['model', 'modelové'],
                                    ['outputs', 'pro UC-01'],
                                    ['personality', 'osobnost'],
                                    ['facts', 'fakta'],
                                    ['smoke', 'smoke'],
                                ].map(([k, l]) => (
                                    <button
                                        key={k}
                                        className={runKind === k ? 'on' : ''}
                                        onClick={() => setRunKind(k)}
                                    >
                                        {l}
                                        <span className="badge">
                                            {runs.filter((r) => r.kind === k).length}
                                        </span>
                                    </button>
                                ))}
                            </div>
                            <RunPicker
                                runs={runsOfKind}
                                value={runSel}
                                onChange={setRunSel}
                                describe={(r) =>
                                    `${r.date || ''}${r.provider ? ' · ' + r.provider + (r.model ? ' / ' + r.model : '') : ''}${r.role ? ' · ' + r.role : ''}${r.limit ? ' · ' + r.limit + ' zák.' : ''}`
                                }
                            />
                            {runSel && (
                                <>
                                    <div className="panel-title">
                                        <Icon name="file-text" />
                                        {shortRun(runSel)}
                                    </div>
                                    {!runDetail && <div className="muted-line">Načítám…</div>}
                                    {runDetail && runDetail.rows && runDetail.rows.length > 0 && (
                                        <RowsTable rows={runDetail.rows} columns={rowColumns} />
                                    )}
                                    {runDetail && (
                                        <details
                                            className="fold"
                                            open={!(runDetail.rows && runDetail.rows.length)}
                                        >
                                            <summary>Karta běhu (RESULTS.md)</summary>
                                            <MarkdownCard
                                                text={runDetail.card || runDetail.table}
                                                empty="Tento běh nemá kartu."
                                            />
                                        </details>
                                    )}
                                </>
                            )}
                        </>
                    )}
                    {rightTab === 'results' && (
                        <>
                            <div className="panel-title">
                                <Icon name="badge-check" />
                                Karta výsledků (eval/RESULTS.md)
                            </div>
                            <MarkdownCard text={results && results.card} empty="Načítám…" />
                        </>
                    )}
                </>
            }
        />
    );
}

Object.assign(window, { Uc04 });
