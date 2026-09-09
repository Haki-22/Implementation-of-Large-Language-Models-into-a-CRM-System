// ============================================================
// UC-01 tab: a person, the card, a rung of the ladder, one message (or the whole ladder as a job)
// ============================================================

function LevelPicker({ levels, value, onChange, card }) {
    const [showArms, setShowArms] = useState(false);
    const can = {};
    (card && card.levels ? card.levels : []).forEach((l) => (can[l.level] = l));
    function render(lvl) {
        const label = LEVEL_LABELS[lvl.id] || { name: lvl.name, sub: '' };
        const state = can[lvl.id];
        const off = state && !state.ok;
        const title = off
            ? 'Chybí: ' + state.missing.map((m) => SLOT_LABELS[m] || m).join(', ')
            : lvl.uses_model
              ? 'volá model'
              : 'bez modelu';
        return (
            <button
                key={lvl.id}
                className={'tier' + (value === lvl.id ? ' sel' : '') + (off ? ' off' : '')}
                onClick={() => onChange(lvl.id)}
                title={title}
            >
                <span className="tno">{lvl.id}</span>
                <span>
                    <div className="tn">
                        {label.name}
                        {!lvl.uses_model && <span className="pill tiny soft">bez modelu</span>}
                    </div>
                    <div className="ts">
                        {off
                            ? 'chybí ' + state.missing.map((m) => SLOT_LABELS[m] || m).join(', ')
                            : label.sub}
                    </div>
                </span>
            </button>
        );
    }
    const tiers = levels.filter((l) => l.tier);
    const arms = levels.filter((l) => !l.tier);
    return (
        <>
            <div className="opt-list">{tiers.map(render)}</div>
            <button className="linklike" onClick={() => setShowArms((v) => !v)}>
                {showArms ? 'Skrýt' : 'Zobrazit'} jednotlivá ramena ({arms.length})
            </button>
            {showArms && <div className="opt-list">{arms.map(render)}</div>}
        </>
    );
}

function Uc01({ settings, catalog }) {
    const [levels, setLevels] = useState([]);
    const [contacts, setContacts] = useState([]);
    const [scopeLabel, setScopeLabel] = useState('');
    const [searching, setSearching] = useState(false);
    const [contactId, setContactId] = useState(null);
    const [briefs, setBriefs] = useState([]);
    const [briefId, setBriefId] = useState(null);
    const [messageMode, setMessageMode] = useState('brief');
    const [customTemplate, setCustomTemplate] = useState('');
    const [level, setLevel] = useState('2');
    const [judgeChoice, setJudgeChoice] = useState(null);
    const { messages, setMessages, restored, remember, clearThread } = usePageHistory('uc01');
    const [busy, setBusy] = useState(false);
    const [jobId, setJobId] = useState(null);
    const [runs, setRuns] = useState([]);
    const [runSel, setRunSel] = useState('');
    const [runRows, setRunRows] = useState(null);
    const [onlyContact, setOnlyContact] = useState(true);
    const [results, setResults] = useState(null);
    const [rightTab, setRightTab] = useState('card');
    const [openPicker, setOpenPicker] = useState(null);
    const job = useJob(jobId);
    const { card, loading: cardLoading, error: cardError } = useContactCard(contactId);
    useLucide();
    useEffect(() => {
        if (restored)
            applyRestored(restored.state, {
                contactId: setContactId,
                level: setLevel,
                briefId: setBriefId,
                messageMode: setMessageMode,
                customTemplate: setCustomTemplate,
                rightTab: setRightTab,
                runSel: setRunSel,
                onlyContact: setOnlyContact,
                judgeChoice: setJudgeChoice,
            });
    }, [restored]);
    useEffect(
        () =>
            remember({
                contactId,
                level,
                briefId,
                messageMode,
                customTemplate,
                rightTab,
                runSel,
                onlyContact,
                judgeChoice,
            }),
        [contactId, level, briefId, messageMode, customTemplate, rightTab, runSel, onlyContact, judgeChoice],
    );

    function loadRuns() {
        return getJson('/uc01/runs')
            .then((d) => {
                setRuns(d.runs || []);
                if (!runSel && d.record) setRunSel(d.record);
            })
            .catch((e) => toast.error(e.message));
    }
    useEffect(() => {
        getJson('/uc01/levels')
            .then((d) => setLevels(d.levels || []))
            .catch((e) => toast.error(e.message));
        loadContacts('');
        getJson('/uc01/briefs')
            .then((d) => {
                setBriefs(d.briefs || []);
                const ladder = (d.briefs || []).find((b) => b.ladder);
                setBriefId(
                    (cur) =>
                        cur ||
                        (ladder ? ladder.id : d.briefs && d.briefs[0] ? d.briefs[0].id : null),
                );
            })
            .catch((e) => toast.error(e.message));
        loadRuns();
    }, []);

    useEffect(() => {
        if (rightTab === 'results' && !results)
            getJson('/uc01/results')
                .then(setResults)
                .catch((e) => toast.error(e.message));
    }, [rightTab]);

    // the record first, then the others as the bridge lists them (newest name first)
    const messageRuns = runs
        .filter((r) => r.has_messages)
        .sort((a, b) => (b.record ? 1 : 0) - (a.record ? 1 : 0));
    const otherRuns = runs.filter((r) => !r.has_messages);
    useEffect(() => {
        if (!runSel || !runs.length) return;
        const sel = runs.find((r) => r.name === runSel);
        if (!sel || !sel.has_messages) return; // an OCEAN or faithfulness folder has no messages
        setRunRows(null);
        getJson(`/uc01/runs/${runSel}/messages`, {
            contact: onlyContact ? contactId : null,
            limit: 400,
        })
            .then((d) => setRunRows(d.rows || []))
            .catch((e) => toast.error(e.message));
    }, [runSel, onlyContact, contactId, runs]);

    async function loadContacts(query) {
        setSearching(true);
        try {
            const d = await getJson(
                '/uc01/contacts',
                query ? { q: query, scope: 'all', limit: 30 } : {},
            );
            setContacts(d.contacts || []);
            setScopeLabel(
                d.scope === 'pick'
                    ? `Výběr práce (${d.contacts.length} kontaktů, 4 defektní řádky); hledání prohledá všech 500.`
                    : `Hledání „${d.query}“ ve všech kontaktech.`,
            );
            if (d.contacts.length && !d.contacts.some((c) => c.id === contactId))
                setContactId(d.contacts[0].id);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setSearching(false);
        }
    }

    const selectedBrief = briefs.find((b) => b.id === briefId);
    const levelObj = levels.find((l) => l.id === level);
    const label = LEVEL_LABELS[level] || {};
    const selectedContact = contacts.find((c) => c.id === contactId);
    const contactLabel = selectedContact
        ? `${selectedContact.name} · #${selectedContact.id}`
        : card
          ? `${card.name} · #${card.id}`
          : contactId
            ? '#' + contactId
            : 'vyberte osobu';
    const messageLabel =
        messageMode === 'custom'
            ? customTemplate.trim()
                ? 'vlastní text'
                : 'vlastní text (zatím prázdný)'
            : selectedBrief
              ? selectedBrief.title
              : 'brief z korpusu';
    const levelState = card && card.levels ? card.levels.find((l) => l.level === level) : null;
    const levelLabel =
        `${level} · ${label.name || (levelObj ? levelObj.name : '')}` +
        (levelState && !levelState.ok ? ' · kontakt nemá vstup' : '');
    function togglePicker(id) {
        setOpenPicker((o) => (o === id ? null : id));
    }

    async function generate() {
        if (busy || !contactId) return;
        if (messageMode === 'custom' && !customTemplate.trim()) {
            toast.error('Vlastní zpráva je prázdná.');
            return;
        }
        setBusy(true);
        const contact =
            contacts.find((c) => c.id === contactId) ||
            (card ? { name: card.name } : { name: '#' + contactId });
        const briefLabel =
            messageMode === 'custom'
                ? 'vlastní text'
                : selectedBrief
                  ? selectedBrief.title
                  : 'brief';
        setMessages((m) => [
            ...m,
            {
                role: 'user',
                text: [
                    `Vygeneruj — <b>${escHtml(contact.name)}</b> · ${escHtml(briefLabel)} · úroveň ${level} (${escHtml(label.name || '')})`,
                ],
            },
            { role: 'ai', typing: true },
        ]);
        try {
            const r = await postJson('/uc01/generate', {
                contact_id: contactId,
                brief_id: messageMode === 'custom' ? null : briefId,
                custom_template: messageMode === 'custom' ? customTemplate.trim() : null,
                level,
                judge: judgeChoice,
                ...generationFields(settings),
            });
            setMessages((m) => {
                const next = m.slice(0, -1);
                if (r.skipped && r.skipped.length) {
                    next.push({
                        role: 'ai',
                        html: `<p style="margin:0"><b>Úroveň ${level} pro tento kontakt nelze:</b> chybí ${escHtml(r.skipped.map((s) => SLOT_LABELS[s] || s).join(', '))}.</p>`,
                    });
                } else if (r.error) {
                    next.push({
                        role: 'ai',
                        html: `<p style="margin:0"><b>Model selhal:</b> ${escHtml(r.error)}</p>`,
                    });
                } else {
                    next.push({
                        role: 'ai',
                        html: `<p style="margin:0">${escHtml(r.text).replace(/\n/g, '<br/>')}</p>` + uc01JudgeTrailHtml(r.rules, r.judgment, r.judge_config),
                        meta: `${r.used_model ? `${r.provider} / ${r.model}${r.tier ? ' · ' + r.tier : ''}` : 'bez modelu'} · ${fmtSeconds(r.seconds)} · prompt v${r.prompt_version}${r.reused_from ? ' · převzato z ' + r.reused_from : ''} · pravidla: ${r.rules && r.rules.accepted ? 'přijato' : 'zamítnuto'}${r.judgment ? ' · soudce: ' + r.judgment.final + ' · volání ' + r.judgment.calls : ''}`,
                        folds: [
                            { title: 'Pravidlový soudce', html: rulesHtml(r.rules) },
                            ...(r.judgment ? [{
                                title: `Soudcovská kaskáda · úroveň ${r.judge_config.level}`,
                                html: `<p>${escHtml(r.judgment.reason)}${r.judgment.calls === 0 ? ' — pravidla odmítla zprávu, model se nevolal.' : ''}</p><pre>${escHtml(JSON.stringify(r.judgment, null, 2))}</pre>`,
                            }] : []),
                            {
                                title: `Sloty (${(r.slots || []).length})`,
                                html: `<div class="tag-row">${(r.slots || []).map((s) => `<span class="pill soft">${escHtml(SLOT_LABELS[s] || s)}</span>`).join('')}</div>`,
                            },
                            ...(r.system_prompt
                                ? [
                                      {
                                          title: 'Prompt (systémový + uživatelský)',
                                          html: `<pre>${escHtml(r.system_prompt)}</pre><pre>${escHtml(r.user_prompt || '')}</pre>`,
                                      },
                                  ]
                                : []),
                        ],
                    });
                }
                return next;
            });
        } catch (e) {
            toast.error(e.message);
            setMessages((m) => m.slice(0, -1));
        } finally {
            setBusy(false);
        }
    }

    async function runLadder() {
        if (!contactId || jobId) return;
        try {
            const r = await postJson('/uc01/ladder', {
                contact_id: contactId,
                levels: 'all',
                judge: judgeChoice,
                ...generationFields(settings),
            });
            setJobId(r.job.id);
            setRightTab('runs');
            setMessages((m) => [
                ...m,
                {
                    role: 'user',
                    text: [
                        `Spusť celý žebřík pro kontakt #${contactId} (${escHtml(settings.provider)}${settings.model ? ' / ' + escHtml(settings.model) : ''}); shodná volání ze záznamu se převezmou.`,
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
            if (j.result && j.result.run_dir) setRunSel(j.result.run_dir);
        });
        setMessages((m) => [
            ...m,
            {
                role: 'ai',
                html:
                    j.state === 'done'
                        ? `<p style="margin:0"><b>Žebřík doběhl.</b> Složka ${escHtml(j.result.run_dir)}: ${j.result.messages} zpráv, volání ${fmtCalls(j.result.llm_calls)} modelu, ${j.result.reused} převzato. Zprávy jsou vpravo v záložce Běhy.</p>`
                        : `<p style="margin:0"><b>Žebřík selhal:</b> ${escHtml(j.error || '')}</p>`,
                folds: j.result && j.result.judgment ? [{
                    title: 'Hodnocení žebříku — samostatný průchod',
                    html: `<pre>${escHtml(JSON.stringify(j.result.judgment, null, 2))}</pre>`,
                }] : [],
            },
            ...((j.result?.judgment?.rows || j.result?.rows || []).map((row) => ({
                role: 'ai',
                html: `<p><b>Úroveň personalizace ${escHtml(row.level)} · brief ${escHtml(row.brief_id)}</b></p><p>${escHtml(row.text).replace(/\n/g, '<br/>')}</p>` +
                    uc01JudgeTrailHtml(row.rules, row.final ? row : null, j.result.judgment?.config?.cascade),
                folds: [{ title: 'Podrobnosti hodnocení', html: `<pre>${escHtml(JSON.stringify(row, null, 2))}</pre>` }],
            }))),
        ]);
    }

    const briefsByCategory = {};
    briefs.forEach((b) => {
        const k = b.category || 'ostatní';
        (briefsByCategory[k] = briefsByCategory[k] || []).push(b);
    });

    return (
        <UseCaseShell
            left={
                <>
                    <Guide
                        steps={[
                            'Vyberte <b>osobu</b>; vpravo je její karta z databáze.',
                            'Zvolte zprávu: <b>brief</b> z korpusu, nebo napište vlastní text.',
                            'Zvolte <b>úroveň personalizace</b> (šedé příčky kontakt nemůže: chybí mu vstup).',
                            '<b>Vygeneruj</b> jednu zprávu, nebo spusťte <b>celý žebřík</b> na pozadí.',
                        ]}
                    />
                    <PickerFold
                        label="Osoba"
                        value={contactLabel}
                        open={openPicker === 'person'}
                        onToggle={() => togglePicker('person')}
                    >
                        <PersonList
                            contacts={contacts}
                            value={contactId}
                            onChange={(id) => {
                                setContactId(id);
                                setOpenPicker(null);
                            }}
                            onSearch={loadContacts}
                            searching={searching}
                            scopeLabel={scopeLabel}
                        />
                    </PickerFold>
                    <PickerFold
                        label="Zpráva"
                        value={messageLabel}
                        open={openPicker === 'message'}
                        onToggle={() => togglePicker('message')}
                    >
                        <div className="seg" style={{ alignSelf: 'flex-start' }}>
                            <button
                                className={messageMode === 'brief' ? 'on' : ''}
                                onClick={() => setMessageMode('brief')}
                            >
                                Brief z korpusu
                            </button>
                            <button
                                className={messageMode === 'custom' ? 'on' : ''}
                                onClick={() => setMessageMode('custom')}
                            >
                                Vlastní text
                            </button>
                        </div>
                        {messageMode === 'brief' ? (
                            <div className="chip-col">
                                {Object.entries(briefsByCategory).map(([cat, list]) => (
                                    <React.Fragment key={cat}>
                                        <div className="muted-line cat">{cat}</div>
                                        {list.map((b) => (
                                            <button
                                                key={b.id}
                                                className={
                                                    'chip-line' + (b.id === briefId ? ' sel' : '')
                                                }
                                                onClick={() => {
                                                    setBriefId(b.id);
                                                    setOpenPicker(null);
                                                }}
                                                title={b.default_template}
                                            >
                                                <span className="brief-title">
                                                    {b.title}
                                                    {b.ladder && (
                                                        <span className="pill tiny soft">
                                                            žebřík
                                                        </span>
                                                    )}
                                                </span>
                                                <span className="brief-sub">
                                                    {b.default_template.slice(0, 70)}…
                                                </span>
                                            </button>
                                        ))}
                                    </React.Fragment>
                                ))}
                            </div>
                        ) : (
                            <textarea
                                className="uc-textarea"
                                value={customTemplate}
                                onChange={(e) => setCustomTemplate(e.target.value)}
                                placeholder="Sem vložte text zprávy, kterou má UC-01 personalizovat…"
                            />
                        )}
                    </PickerFold>
                    <PickerFold
                        label="Úroveň"
                        value={levelLabel}
                        open={openPicker === 'level'}
                        onToggle={() => togglePicker('level')}
                    >
                        <LevelPicker
                            levels={levels}
                            value={level}
                            onChange={(id) => {
                                setLevel(id);
                                setOpenPicker(null);
                            }}
                            card={card}
                        />
                    </PickerFold>
                    <PickerFold
                        label="Soudce"
                        value={['0 · jen pravidla', '1 · jeden soudce', '2 · dva soudci', '3 · dva soudci + eskalace'][uc01JudgeChoice(judgeChoice).level]}
                        open={openPicker === 'judge'}
                        onToggle={() => togglePicker('judge')}
                    >
                        <Uc01JudgePicker catalog={catalog} value={judgeChoice} onChange={setJudgeChoice} />
                    </PickerFold>
                    <button className="uc-action" disabled={busy || !contactId} onClick={generate}>
                        <Icon name="sparkles" size={18} style={{ color: '#fff' }} />
                        {busy ? 'Generuji…' : 'Vygeneruj zprávu'}
                    </button>
                    <button
                        className="uc-action ghost"
                        disabled={!!jobId || !contactId}
                        onClick={runLadder}
                        title="Všech 15 příček pro vybraný kontakt na briefech žebříku; shodná volání ze záznamu se převezmou"
                    >
                        <Icon name="layers" size={18} />
                        {jobId ? 'Žebřík běží…' : 'Celý žebřík (na pozadí)'}
                    </button>
                </>
            }
            center={
                messages.length ? (
                    <Chat
                        title="Hyperpersonalizace"
                        goal="Z dat kontaktu gramaticky správná česká zpráva; každá příčka přidá jeden vstup"
                        builds={level.startsWith('6') ? 'čerpá z UC-04' : null}
                        messages={messages}
                        onClear={clearThread}
                        empty={
                            <PanelEmpty
                                icon="wand-sparkles"
                                text="Vyberte osobu, zprávu a úroveň vlevo, pak vygenerujte."
                            />
                        }
                        honest="Demonstrace nad syntetickými daty; oslovení, vykání/tykání a rod kontrolují pravidla a volitelný modelový soudce. Míru odpovědí neměříme."
                    />
                ) : null
            }
            right={
                <>
                    {job && <JobProgress job={job} onDone={onJobDone} />}
                    <SubTabs
                        items={[
                            { id: 'card', label: 'Karta' },
                            { id: 'runs', label: 'Běhy', badge: messageRuns.length || null },
                            { id: 'results', label: 'Výsledky' },
                        ]}
                        active={rightTab}
                        onChange={setRightTab}
                    />
                    {rightTab === 'card' && (
                        <PersonCard card={card} loading={cardLoading} error={cardError} />
                    )}
                    {rightTab === 'runs' && (
                        <>
                            <div className="panel-title">
                                <Icon name="folder-open" />
                                Složky běhů (★ = záznam)
                            </div>
                            <RunPicker
                                runs={messageRuns}
                                value={runSel}
                                onChange={setRunSel}
                                describe={(r) =>
                                    `${r.kind} · ${r.provider || '—'}${r.model ? ' / ' + r.model : ''} · ${r.messages ?? '?'} zpráv`
                                }
                            />
                            {otherRuns.length > 0 && (
                                <div className="muted-line">
                                    Bez zpráv (jiný druh běhu):{' '}
                                    {otherRuns
                                        .map((r) => `${r.kind} · ${shortRun(r.name)}`)
                                        .join(' · ')}
                                    . Odvozený profil OCEAN je na kartě osoby, věrnost v záložce
                                    Výsledky.
                                </div>
                            )}
                            {runSel && messageRuns.some((r) => r.name === runSel) && (
                                <>
                                    <div className="set-row compact">
                                        <div className="lbl">Jen vybraná osoba</div>
                                        <span className="grow"></span>
                                        <button
                                            className={'toggle' + (onlyContact ? ' on' : '')}
                                            onClick={() => setOnlyContact((v) => !v)}
                                        ></button>
                                    </div>
                                    {runRows === null && (
                                        <div className="muted-line">Načítám zprávy…</div>
                                    )}
                                    {runRows && !runRows.length && (
                                        <div className="muted-line">
                                            Tento běh vybranou osobu neobsahuje.
                                        </div>
                                    )}
                                    {runRows && runRows.length > 0 && (
                                        <div className="mini-list">
                                            {runRows.map((row, i) => (
                                                <details className="fold" key={i}>
                                                    <summary>
                                                        <span className="pill tiny">
                                                            {row.level}
                                                        </span>{' '}
                                                        {LEVEL_LABELS[row.level]
                                                            ? LEVEL_LABELS[row.level].name
                                                            : row.level_name}{' '}
                                                        · brief {row.brief_id} · #{row.contact_id}
                                                        {row.rules
                                                            ? row.rules.accepted
                                                                ? ' · ✓'
                                                                : ' · ✗ ' +
                                                                  (row.rules.failures || []).join(
                                                                      ',',
                                                                  )
                                                            : ''}
                                                        {row.skipped && row.skipped.length
                                                            ? ' · přeskočeno'
                                                            : ''}
                                                    </summary>
                                                    <div className="fold-body">
                                                        {row.text ? (
                                                            <p
                                                                style={{
                                                                    whiteSpace: 'pre-wrap',
                                                                    margin: 0,
                                                                }}
                                                            >
                                                                {row.text}
                                                            </p>
                                                        ) : (
                                                            <span className="muted-line">
                                                                {row.error ||
                                                                    'bez textu: ' +
                                                                        (row.skipped || []).join(
                                                                            ', ',
                                                                        )}
                                                            </span>
                                                        )}
                                                        <div className="muted-line">
                                                            {row.provider || 'bez modelu'}
                                                            {row.model
                                                                ? ' / ' + row.model
                                                                : ''} · {fmtSeconds(row.seconds)}
                                                            {row.reused_from ? ' · převzato' : ''}
                                                        </div>
                                                    </div>
                                                </details>
                                            ))}
                                        </div>
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
                            {results && results.pick && (
                                <details className="fold">
                                    <summary>Pravidlo výběru osob ({results.pick.name})</summary>
                                    <div className="fold-body">{results.pick.rule}</div>
                                </details>
                            )}
                        </>
                    )}
                </>
            }
        />
    );
}

Object.assign(window, { Uc01, LevelPicker });
