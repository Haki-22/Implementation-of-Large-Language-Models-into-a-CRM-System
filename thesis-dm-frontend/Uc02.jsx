// ============================================================
// UC-02 tab: reversible pseudonymisation, mask -> (a model) -> restore
// ============================================================

const UC02_HISTORY_KEY = 'thesisdm.uc02.history.v2';

function Uc02({ settings, catalog }) {
    const [samples, setSamples] = useState([]);
    const [text, setText] = useState('');
    const [useNer, setUseNer] = useState(true);
    const [nerBackend, setNerBackend] = useState(null); // null = the package default
    const [nerBackends, setNerBackends] = useState([]);
    const [nerOpen, setNerOpen] = useState(false);
    const [task, setTask] = useState('summarize');
    const {
        messages,
        setMessages,
        restored,
        remember: rememberChoices,
        clearThread,
    } = usePageHistory('uc02');
    const [mapping, setMapping] = useState([]);
    const [masked, setMasked] = useState('');
    const [stage, setStage] = useState('idle'); // idle | masked | restored
    const [busy, setBusy] = useState('');
    const [backend, setBackend] = useState('');
    const [history, setHistory] = useState([]);
    const [rightTab, setRightTab] = useState('tokens');
    const [results, setResults] = useState(null);
    const [runSel, setRunSel] = useState('');
    const [runDetail, setRunDetail] = useState(null);
    useLucide();
    useEffect(() => {
        if (restored)
            applyRestored(restored.state, {
                text: setText,
                useNer: setUseNer,
                nerBackend: setNerBackend,
                task: setTask,
                mapping: setMapping,
                masked: setMasked,
                stage: setStage,
                backend: setBackend,
                rightTab: setRightTab,
            });
    }, [restored]);
    useEffect(
        () =>
            rememberChoices({
                text,
                useNer,
                nerBackend,
                task,
                mapping,
                masked,
                stage,
                backend,
                rightTab,
            }),
        [text, useNer, nerBackend, task, mapping, masked, stage, backend, rightTab],
    );

    useEffect(() => {
        try {
            const saved = localStorage.getItem(UC02_HISTORY_KEY);
            if (saved) setHistory(JSON.parse(saved));
        } catch (e) {}
        getJson('/uc02/ner-backends')
            .then((d) => setNerBackends(d.backends || []))
            .catch((e) => toast.error(e.message));
        getJson('/uc02/samples', { limit: 12 })
            .then((d) => {
                setSamples(d.samples || []);
                if (d.samples && d.samples.length) setText((cur) => cur || d.samples[0].text);
            })
            .catch((e) => toast.error(e.message));
    }, []);

    useEffect(() => {
        if (rightTab !== 'results' || results) return;
        getJson('/uc02/results')
            .then(setResults)
            .catch((e) => toast.error(e.message));
    }, [rightTab]);

    useEffect(() => {
        if (!runSel) return;
        setRunDetail(null);
        getJson('/uc02/runs/' + runSel)
            .then(setRunDetail)
            .catch((e) => toast.error(e.message));
    }, [runSel]);

    const defaultBackend = (nerBackends.find((b) => b.default) || {}).backend || null;
    const activeBackend = nerBackend || defaultBackend;
    const activeRow = nerBackends.find((b) => b.backend === activeBackend);
    const nerLabel = activeRow
        ? `${activeRow.backend} · F1 ${fmtNum(activeRow.f1)}` +
          (activeRow.f1_lower !== null && activeRow.f1_lower !== undefined
              ? ` · malá ${fmtNum(activeRow.f1_lower)}`
              : '') +
          (activeRow.default ? ' · záznam' : '')
        : nerBackend || 'výchozí';

    function remember(original, maskedText, rows) {
        const entry = {
            id: Date.now(),
            time: new Date().toLocaleTimeString('cs-CZ'),
            original,
            masked: maskedText,
            mapping: rows,
            tokens: rows.length,
        };
        const next = [entry, ...history].slice(0, 10);
        setHistory(next);
        try {
            localStorage.setItem(UC02_HISTORY_KEY, JSON.stringify(next));
        } catch (e) {}
    }
    function clearHistory() {
        setHistory([]);
        try {
            localStorage.removeItem(UC02_HISTORY_KEY);
        } catch (e) {}
    }
    function pickHistory(h) {
        setText(h.original);
        setMapping(h.mapping);
        setMasked(h.masked);
        setStage('masked');
        setMessages([
            { role: 'user', html: `<p style="margin:0">${escHtml(h.original)}</p>` },
            {
                role: 'ai',
                html: `<p style="margin:0 0 8px"><b>Z historie</b> (zamaskováno ${h.time}):</p><p style="margin:0">${highlightTokens(h.masked)}</p>`,
            },
        ]);
    }
    function pickSample(s) {
        setText(s.text);
        setStage('idle');
        setMessages([]);
        setMapping([]);
        setMasked('');
    }

    async function mask() {
        if (!text.trim()) return;
        setBusy('mask');
        try {
            const res = await postJson('/uc02/mask', {
                text,
                use_ner: useNer,
                ner_backend: nerBackend,
            });
            setMapping(res.mapping);
            setMasked(res.masked);
            setBackend(
                `${res.backend} · ${res.use_ner ? 'pravidla + NER ' + res.ner_backend : 'jen pravidla'} · ${fmtSeconds(res.seconds)}`,
            );
            setStage('masked');
            setMessages([
                { role: 'user', html: `<p style="margin:0">${escHtml(text)}</p>` },
                {
                    role: 'ai',
                    html: `<p style="margin:0 0 8px"><b>Zamaskováno</b> — tohle by odešlo modelu:</p><p style="margin:0">${highlightTokens(res.masked)}</p>`,
                    meta: `${res.mapping.length} tokenů · ${Object.entries(res.counts)
                        .map(([k, v]) => `${k} ${v}`)
                        .join(', ')} · ${fmtSeconds(res.seconds)}`,
                },
            ]);
            remember(text, res.masked, res.mapping);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setBusy('');
        }
    }

    async function roundtrip() {
        if (!text.trim()) return;
        setBusy('roundtrip');
        setMessages([
            { role: 'user', html: `<p style="margin:0">${escHtml(text)}</p>` },
            { role: 'ai', typing: true },
        ]);
        try {
            const res = await postJson('/uc02/roundtrip', {
                text,
                use_ner: useNer,
                ner_backend: nerBackend,
                task,
                ...generationFields(settings),
            });
            setMapping(res.mapping);
            setMasked(res.masked);
            setStage('restored');
            setBackend(`${res.backend} · ${res.provider}${res.model ? ' / ' + res.model : ''}`);
            const ok = res.attempts.filter((a) => a.integrity_ok).length;
            setMessages([
                { role: 'user', html: `<p style="margin:0">${escHtml(text)}</p>` },
                {
                    role: 'ai',
                    html: `<p style="margin:0 0 8px"><b>1 · Zamaskováno</b> — odešlo modelu:</p><p style="margin:0">${highlightTokens(res.masked)}</p>`,
                    folds: [
                        {
                            title: 'Systémová instrukce a prompt',
                            html: `<pre>${escHtml(res.system_prompt)}</pre><pre>${escHtml((res.attempts[0] || {}).prompt || '')}</pre>`,
                        },
                    ],
                },
                {
                    role: 'ai',
                    html: `<p style="margin:0 0 8px"><b>2 · Odpověď modelu</b> (${escHtml(res.task === 'summarize' ? 'shrnutí' : 'odpověď')}, maskovaná):</p><p style="margin:0">${highlightTokens(res.model_answer_masked || '')}</p>`,
                    meta: `${res.provider}${res.model ? ' / ' + res.model : ''}${res.tier ? ' · ' + res.tier : ''} · ${res.attempts.length} ${res.attempts.length === 1 ? 'pokus' : 'pokusy'} · integrita ${ok ? 'OK' : 'porušena'} · ${fmtSeconds(res.seconds)}`,
                    folds:
                        res.attempts.length > 1
                            ? [
                                  {
                                      title: 'Všechny pokusy',
                                      html: res.attempts
                                          .map(
                                              (a) =>
                                                  `<pre>#${a.attempt} mid_ok=${a.mid_ok} integrity_ok=${a.integrity_ok} chybí=${(a.missing || []).join(',')}\n${escHtml(a.response || a.error || '')}</pre>`,
                                          )
                                          .join(''),
                                  },
                              ]
                            : [],
                },
                {
                    role: 'ai',
                    html: `<p style="margin:0 0 8px"><b>3 · Obnoveno</b> lokálně z mapy:</p><p style="margin:0">${escHtml(res.restored)}</p>`,
                },
            ]);
            remember(text, res.masked, res.mapping);
        } catch (e) {
            toast.error(e.message);
            setMessages((m) => m.slice(0, -1));
        } finally {
            setBusy('');
        }
    }

    async function unmask() {
        if (!masked || !mapping.length) return;
        setBusy('restore');
        try {
            const res = await postJson('/uc02/restore', { text: masked, mapping, original: text });
            setStage('restored');
            setMessages((m) => [
                ...m,
                {
                    role: 'ai',
                    html: `<p style="margin:0 0 8px"><b>Obnoveno</b> lokálně z mapy:</p><p style="margin:0">${escHtml(res.restored)}</p>`,
                    meta: res.exact
                        ? 'shoda s originálem: přesná'
                        : 'shoda s originálem: NE (text se změnil)',
                },
            ]);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setBusy('');
        }
    }

    const counts = {};
    mapping.forEach((m) => {
        counts[m.pii_type] = (counts[m.pii_type] || 0) + 1;
    });

    return (
        <UseCaseShell
            left={
                <>
                    <Guide
                        steps={[
                            'Vyberte řádek <b>korpusu</b> nebo vložte vlastní český text s údaji.',
                            '<b>Zamaskuj</b> zavolá pseudonymizér UC-02 (pravidla + český NER).',
                            '<b>Pošli modelem</b> udělá celý sendvič: maskuj → model → obnov.',
                            'Vpravo je <b>mapa tokenů</b>, která stroj neopouští, a výsledky měření.',
                        ]}
                    />
                    <div className="field-label">Detekce</div>
                    <div className="set-row" style={{ marginBottom: 10 }}>
                        <div>
                            <div className="lbl">Pravidla + český NER</div>
                            <div className="sub">
                                Pravidla najdou formátové údaje; NER (bardsai) jména, firmy, adresy,
                                data.
                            </div>
                        </div>
                        <button
                            className={'toggle' + (useNer ? ' on' : '')}
                            onClick={() => setUseNer((v) => !v)}
                            title="Přepnout NER"
                        ></button>
                    </div>
                    {useNer && (
                        <PickerFold
                            label="NER"
                            value={nerLabel}
                            open={nerOpen}
                            onToggle={() => setNerOpen((o) => !o)}
                        >
                            <div className="muted-line">
                                F1 = tabulka záznamu (pravidla + NER, korpus psaný s velkými
                                písmeny); malá = týž korpus celý malými písmeny. Jiný než výchozí
                                model se načte při prvním použití.
                            </div>
                            <div className="chip-col">
                                {nerBackends.map((b) => (
                                    <button
                                        key={b.backend}
                                        className={
                                            'chip-line' +
                                            (activeBackend === b.backend ? ' sel' : '')
                                        }
                                        onClick={() => {
                                            setNerBackend(b.default ? null : b.backend);
                                            setNerOpen(false);
                                        }}
                                        title={b.model || ''}
                                    >
                                        <span className="brief-title">
                                            {b.backend}
                                            {b.default && (
                                                <span className="pill tiny soft">záznam</span>
                                            )}
                                        </span>
                                        <span className="brief-sub">
                                            F1 {fmtNum(b.f1)} · malá {fmtNum(b.f1_lower)} ·{' '}
                                            {b.licence || '—'}
                                        </span>
                                    </button>
                                ))}
                                {!nerBackends.length && (
                                    <div className="muted-line">Seznam se načítá z mostu…</div>
                                )}
                            </div>
                        </PickerFold>
                    )}
                    <div className="field-label">Ukázky z korpusu</div>
                    <div className="chip-col">
                        {samples.map((s) => (
                            <button
                                key={s.id}
                                className="chip-line"
                                onClick={() => pickSample(s)}
                                title={s.scenario || ''}
                            >
                                <span className="brief-title">{s.label}</span>
                                <span className="brief-sub">{s.scenario || s.id}</span>
                            </button>
                        ))}
                        {!samples.length && (
                            <div className="muted-line">Korpus se načítá z mostu…</div>
                        )}
                    </div>
                    <div className="field-label">Vstupní text</div>
                    <textarea
                        className="uc-textarea"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                    />
                    <div className="field-label">Úloha modelu</div>
                    <div className="seg" style={{ alignSelf: 'flex-start' }}>
                        <button
                            className={task === 'summarize' ? 'on' : ''}
                            onClick={() => setTask('summarize')}
                        >
                            shrnutí
                        </button>
                        <button
                            className={task === 'reply' ? 'on' : ''}
                            onClick={() => setTask('reply')}
                        >
                            odpověď
                        </button>
                    </div>
                    <button className="uc-action" disabled={!!busy || !text.trim()} onClick={mask}>
                        <Icon name="shield" size={18} style={{ color: '#fff' }} />
                        {busy === 'mask' ? 'Maskuji…' : 'Zamaskuj'}
                    </button>
                    <button
                        className="uc-action"
                        disabled={!!busy || !text.trim()}
                        onClick={roundtrip}
                    >
                        <Icon name="send" size={18} style={{ color: '#fff' }} />
                        {busy === 'roundtrip' ? 'Model pracuje…' : 'Pošli modelem'}
                    </button>
                    <button
                        className="uc-action ghost"
                        disabled={!!busy || stage !== 'masked'}
                        onClick={unmask}
                    >
                        <Icon name="shield-check" size={18} />
                        Odmaskuj
                    </button>
                </>
            }
            center={
                messages.length ? (
                    <Chat
                        title="Reverzibilní pseudonymizace"
                        goal="Údaje zmizí před modelem a lokálně se vrátí zpět"
                        builds="importováno do UC-03"
                        messages={messages}
                        onClear={clearThread}
                        empty={
                            <PanelEmpty
                                icon="shield"
                                text="Vyberte text vlevo a klikněte na Zamaskuj nebo Pošli modelem."
                            />
                        }
                        honest="Každé volání jde přes reálný kód UC-02; model vidí jen tokeny <TYP_N>."
                    />
                ) : null
            }
            right={
                <>
                    <SubTabs
                        items={[
                            { id: 'tokens', label: 'Tokeny', badge: mapping.length || null },
                            { id: 'results', label: 'Výsledky' },
                            { id: 'history', label: 'Historie', badge: history.length || null },
                        ]}
                        active={rightTab}
                        onChange={setRightTab}
                    />
                    {rightTab === 'tokens' && (
                        <>
                            <div className="panel-title">
                                <Icon name="table-2" />
                                Mapa tokenů — zůstává lokálně
                            </div>
                            <TokenMap mapping={mapping} />
                            {mapping.length > 0 && (
                                <div className="signal-list">
                                    <Signal icon="braces">
                                        Typy:{' '}
                                        {Object.entries(counts)
                                            .map(([k, v]) => `${k} ${v}`)
                                            .join(', ')}
                                    </Signal>
                                    <Signal icon="repeat">
                                        Stejný údaj = stejný token v daném běhu; skloněné tvary
                                        jména sdílí číslo.
                                    </Signal>
                                </div>
                            )}
                            {backend && (
                                <Signal icon="server" muted>
                                    {backend}
                                </Signal>
                            )}
                        </>
                    )}
                    {rightTab === 'results' && (
                        <>
                            <div className="panel-title">
                                <Icon name="badge-check" />
                                Karta výsledků (eval/RESULTS.md)
                            </div>
                            <MarkdownCard text={results && results.card} empty="Načítám kartu…" />
                            {results && results.ner_comparison && (
                                <details className="fold">
                                    <summary>Srovnání NER backendů (NER-COMPARISON.md)</summary>
                                    <MarkdownCard text={results.ner_comparison} />
                                </details>
                            )}
                            <div className="panel-title">
                                <Icon name="folder-open" />
                                Složky běhů
                            </div>
                            <RunPicker
                                runs={results ? results.runs : []}
                                value={runSel}
                                onChange={setRunSel}
                                describe={(r) => `${r.kind}${r.date ? ' · ' + r.date : ''}`}
                            />
                            {runSel && (
                                <details className="fold" open>
                                    <summary>{shortRun(runSel)}</summary>
                                    <MarkdownCard
                                        text={runDetail && (runDetail.card || runDetail.table)}
                                        empty="Načítám…"
                                    />
                                </details>
                            )}
                        </>
                    )}
                    {rightTab === 'history' && (
                        <>
                            <div className="panel-title">
                                <Icon name="history" />
                                Historie (posledních 10)
                                {history.length > 0 && (
                                    <button
                                        onClick={clearHistory}
                                        style={{
                                            marginLeft: 'auto',
                                            fontSize: 11,
                                            color: 'var(--fg4)',
                                        }}
                                    >
                                        Smazat
                                    </button>
                                )}
                            </div>
                            <div className="opt-list">
                                {history.map((h) => (
                                    <button
                                        key={h.id}
                                        className="opt"
                                        onClick={() => pickHistory(h)}
                                    >
                                        <span
                                            className="av"
                                            style={{
                                                background: 'var(--gray-100)',
                                                color: 'var(--fg3)',
                                            }}
                                        >
                                            {h.tokens}
                                        </span>
                                        <span style={{ minWidth: 0 }}>
                                            <div className="nm" style={{ fontSize: 13 }}>
                                                {h.original.slice(0, 60)}
                                                {h.original.length > 60 ? '…' : ''}
                                            </div>
                                            <div className="sub">
                                                {h.time} · {h.tokens} tokenů
                                            </div>
                                        </span>
                                    </button>
                                ))}
                                {!history.length && (
                                    <PanelEmpty icon="history" text="Žádná historie." />
                                )}
                            </div>
                        </>
                    )}
                </>
            }
        />
    );
}

Object.assign(window, { Uc02 });
