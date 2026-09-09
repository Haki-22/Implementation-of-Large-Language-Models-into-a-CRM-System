// ============================================================
// UC-03 — MCP-Privacy: one chat window = one session; the model keeps the context,
// the envelope keeps the tokens, the audit chain keeps every call.
// ============================================================

const UC03_AUDIT_POLL_MS = 2500;
const UC03_EXAMPLES = [
    'Najdi kontakt Sedláček a shrň, co u nás naposledy koupil.',
    'Zapiš Antonínu Sedláčkovi poznámku: volal kvůli reklamaci reproduktoru k vysílačce, chce výměnu.',
    'Které poznámky máme u zákazníků z Brna?',
];

// Browser recording -> 16 kHz mono 16-bit WAV (what stt.read_wav_pcm accepts)
function encodeWav16k(chunks, sourceRate) {
    let length = 0;
    chunks.forEach((c) => (length += c.length));
    const merged = new Float32Array(length);
    let offset = 0;
    chunks.forEach((c) => {
        merged.set(c, offset);
        offset += c.length;
    });
    const ratio = sourceRate / 16000;
    const outLen = Math.floor(merged.length / ratio);
    const pcm = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
        const pos = i * ratio;
        const lo = Math.floor(pos);
        const hi = Math.min(lo + 1, merged.length - 1);
        const v = merged[lo] + (merged[hi] - merged[lo]) * (pos - lo);
        pcm[i] = Math.max(-1, Math.min(1, v)) * 0x7fff;
    }
    const buffer = new ArrayBuffer(44 + pcm.length * 2);
    const view = new DataView(buffer);
    const str = (o, s) => [...s].forEach((ch, i) => view.setUint8(o + i, ch.charCodeAt(0)));
    str(0, 'RIFF');
    view.setUint32(4, 36 + pcm.length * 2, true);
    str(8, 'WAVE');
    str(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true);
    view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    str(36, 'data');
    view.setUint32(40, pcm.length * 2, true);
    new Int16Array(buffer, 44).set(pcm);
    return new Blob([buffer], { type: 'audio/wav' });
}

function Uc03({ settings }) {
    const [profile, setProfile] = useState('strict');
    const [session, setSession] = useState(null);
    const [supportedProviders, setSupportedProviders] = useState([]);
    const [tools, setTools] = useState([]);
    const { messages, setMessages, restored, remember, clearThread } = usePageHistory('uc03');
    const [busy, setBusy] = useState(false);
    const [audit, setAudit] = useState({ entries: [], verify: null });
    const [review, setReview] = useState(null);
    const [results, setResults] = useState(null);
    const [rightTab, setRightTab] = useState('audit');
    const [draft, setDraft] = useState('');
    const [recording, setRecording] = useState(false);
    const [transcribing, setTranscribing] = useState(false);
    const [lastTranscript, setLastTranscript] = useState(null);
    const rec = useRef(null);
    const fileRef = useRef(null);
    useLucide();
    useEffect(() => {
        if (!restored) return;
        const s = restored.state;
        if (s.profile && s.profile !== profile) {
            keepThread.current = true;
            setProfile(s.profile);
        }
        applyRestored(s, { rightTab: setRightTab });
    }, [restored]);
    useEffect(() => remember({ profile, rightTab }), [profile, rightTab]);

    // Leaving the tab while recording must release the microphone and the audio context.
    useEffect(() => {
        return () => {
            const r = rec.current;
            if (!r) return;
            try {
                r.proc.disconnect();
                r.stream.getTracks().forEach((t) => t.stop());
                r.ctx.close();
            } catch (e) {}
            rec.current = null;
        };
    }, []);

    const supported = supportedProviders.includes(settings.provider);
    const openingSession = useRef(0);

    // Set by the history restore: the restored profile opens a new session over the old
    // thread instead of wiping it (the model does not remember that thread; the reader does).
    const keepThread = useRef(false);
    async function newSession(p) {
        const requestId = ++openingSession.current;
        setSession(null);
        if (!supported) return;
        if (!keepThread.current) setMessages([]);
        keepThread.current = false;
        setAudit({ entries: [], verify: null });
        try {
            const s = await postJson('/uc03/session', { profile: p, ...generationFields(settings) });
            if (openingSession.current === requestId) setSession(s);
        } catch (e) {
            toast.error(e.message);
        }
    }
    useEffect(() => {
        getJson('/uc03/tools', { profile })
            .then((d) => { setTools(d.tools || []); setSupportedProviders(d.providers || []); })
            .catch((e) => toast.error(e.message));
    }, [profile]);
    useEffect(() => {
        newSession(profile);
        return () => { openingSession.current += 1; };
    }, [profile, settings.provider, settings.model, settings.tier, supported]);

    useEffect(() => {
        if (rightTab === 'review' && review === null)
            getJson('/uc03/review')
                .then(setReview)
                .catch((e) => toast.error(e.message));
        if (rightTab === 'results' && results === null)
            getJson('/uc03/results')
                .then(setResults)
                .catch((e) => toast.error(e.message));
    }, [rightTab]);

    async function refreshAudit(s) {
        const sess = s || session;
        if (!sess) return;
        try {
            const d = await getJson('/uc03/audit', { session: sess.session, limit: 30 });
            setAudit({ entries: d.entries || [], verify: d.verify || null });
        } catch (e) {}
    }

    async function send(text) {
        if (busy || !session || !supported) return;
        setBusy(true);
        setMessages((m) => [
            ...m,
            { role: 'user', text: [escHtml(text)] },
            { role: 'ai', typing: true },
        ]);
        const poll = setInterval(() => refreshAudit(), UC03_AUDIT_POLL_MS);
        try {
            const r = await postJson('/uc03/chat', {
                session: session.session,
                message: text,
                profile,
                provider: session.provider,
                model: session.model,
                tier: session.tier,
            });
            await refreshAudit();
            setSession((s) => s && s.session === r.session ? ({ ...s, turns: r.turn }) : s);
            if (r.restoration && !r.restoration.ok) toast.error('Odpověď obsahuje neplatný token; obnova selhala.');
            setMessages((m) => {
                const next = m.slice(0, -1);
                next.push({
                    role: 'ai',
                    html: `<p style="margin:0">${escHtml(r.answer).replace(/\n/g, '<br/>')}</p>`,
                    meta: `${(r.latency_ms / 1000).toFixed(1)} s · ${r.tool_calls.length} ${r.tool_calls.length === 1 ? 'volání nástroje' : 'volání nástrojů'} · profil ${r.profile} · ${r.provider} / ${r.model}${r.tier ? ' · ' + r.tier : ''} · tah ${r.turn}${r.resumed ? ' (navazuje na předchozí)' : ' (nová konverzace)'}`,
                    folds: [
                        {
                            title: 'Co viděl model',
                            html:
                                `<div class="muted-line">Váš text, jak odešel modelu:</div><p>${highlightTokens(r.model_saw)}</p>` +
                                `<div class="muted-line">Odpověď modelu před obnovením:</div><p>${highlightTokens(r.answer_model_view)}</p>`,
                        },
                        {
                            title: `Volání nástrojů (${r.tool_calls.length})`,
                            html: toolCallsHtml(r.tool_calls),
                        },
                    ],
                });
                return next;
            });
            if (rightTab === 'review')
                getJson('/uc03/review')
                    .then(setReview)
                    .catch(() => {});
        } catch (e) {
            toast.error(e.message);
            setMessages((m) => {
                const next = m.slice(0, -1);
                next.push({
                    role: 'ai',
                    html: `<p style="margin:0"><b>Tah selhal:</b> ${escHtml(e.message)}</p>`,
                });
                return next;
            });
        } finally {
            clearInterval(poll);
            setBusy(false);
        }
    }

    async function transcribe(blob, name) {
        setTranscribing(true);
        try {
            const file =
                blob instanceof File
                    ? blob
                    : new File([blob], name || 'recording.wav', { type: 'audio/wav' });
            const r = await uploadFile('/uc03/transcribe', file, { backend: 'whisper' });
            setLastTranscript(r);
            setDraft(r.text);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setTranscribing(false);
        }
    }

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const source = ctx.createMediaStreamSource(stream);
            const proc = ctx.createScriptProcessor(4096, 1, 1);
            const chunks = [];
            proc.onaudioprocess = (e) =>
                chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
            source.connect(proc);
            proc.connect(ctx.destination);
            rec.current = { stream, ctx, proc, chunks };
            setRecording(true);
        } catch (e) {
            toast.error('Mikrofon: ' + e.message);
        }
    }
    async function stopRecording() {
        const r = rec.current;
        if (!r) return;
        r.proc.disconnect();
        r.stream.getTracks().forEach((t) => t.stop());
        const rate = r.ctx.sampleRate;
        await r.ctx.close();
        rec.current = null;
        setRecording(false);
        const blob = encodeWav16k(r.chunks, rate);
        await transcribe(blob, 'nahravka.wav');
    }

    const disabledTools = tools.filter((t) => t.disabled).map((t) => t.name);

    return (
        <UseCaseShell
            left={
                <>
                    <Guide
                        steps={[
                            'Zvolte <b>bezpečnostní profil</b>; každá změna otevře novou konverzaci.',
                            'Napište příkaz, nebo <b>nadiktujte</b> (mikrofon či WAV) — přepis se objeví v poli k potvrzení.',
                            'Model si sám vybere <b>nástroje</b> serveru; vpravo běží auditní řetěz.',
                            'Další tah <b>navazuje</b>: model má kontext celé konverzace a tokeny platí stále.',
                        ]}
                    />
                    <div className="field-label">Bezpečnostní profil</div>
                    <div className="muted-line">
                        {supported
                            ? `UC03: ${session ? session.provider + ' / ' + session.model : settings.provider + ' · otevírám konverzaci…'}`
                            : `UC03 zatím nepodporuje poskytovatele ${settings.provider}. Vyberte v Nastavení: ${supportedProviders.join(', ') || 'načítám…'}.`}
                    </div>
                    <div className="seg" style={{ alignSelf: 'flex-start' }}>
                        {['open', 'masked', 'strict'].map((p) => (
                            <button
                                key={p}
                                className={profile === p ? 'on' : ''}
                                disabled={busy}
                                onClick={() => setProfile(p)}
                            >
                                {p}
                            </button>
                        ))}
                    </div>
                    <div className="muted-line">
                        {profile === 'open' &&
                            'Model vidí hodnoty v čitelné podobě a má i SQL nad databází.'}
                        {profile === 'masked' &&
                            'Každý výsledek a každý argument zápisu prochází obálkou UC-02; id řádků jsou náhodné handly.'}
                        {profile === 'strict' &&
                            'Obálka + rozsah: asistent vidí jen potřebná pole, SQL vypnuto, změny polí čekají na schválení.'}
                    </div>
                    <div className="field-label">Diktát</div>
                    <div className="row-2">
                        <button
                            className={'uc-action' + (recording ? ' danger' : ' ghost')}
                            disabled={transcribing || busy}
                            onClick={recording ? stopRecording : startRecording}
                        >
                            <Icon name={recording ? 'square' : 'mic'} size={18} />
                            {recording ? 'Zastavit a přepsat' : 'Nahrát'}
                        </button>
                        <button
                            className="uc-action ghost"
                            disabled={transcribing || recording || busy}
                            onClick={() => fileRef.current && fileRef.current.click()}
                        >
                            <Icon name="upload" size={18} />
                            WAV soubor
                        </button>
                        <input
                            ref={fileRef}
                            type="file"
                            accept=".wav,audio/wav"
                            style={{ display: 'none' }}
                            onChange={(e) => e.target.files[0] && transcribe(e.target.files[0])}
                        />
                    </div>
                    {transcribing && <Signal icon="loader">Přepisuji lokálním Whisperem…</Signal>}
                    {lastTranscript && !transcribing && (
                        <Signal icon="mic" muted>
                            Přepis {lastTranscript.backend}
                            {lastTranscript.model ? ' ' + lastTranscript.model : ''} ·{' '}
                            {fmtSeconds(lastTranscript.audio_seconds)} zvuku za{' '}
                            {fmtSeconds(lastTranscript.seconds)}
                        </Signal>
                    )}
                    <div className="field-label">Ukázky příkazů</div>
                    <div className="chip-col">
                        {UC03_EXAMPLES.map((p, i) => (
                            <button
                                key={i}
                                className="chip-line"
                                disabled={busy}
                                onClick={() => setDraft(p)}
                            >
                                <Icon
                                    name="message-square"
                                    size={13}
                                    style={{
                                        color: 'var(--orange-500)',
                                        marginRight: 7,
                                        verticalAlign: '-2px',
                                    }}
                                />
                                {p}
                            </button>
                        ))}
                    </div>
                    <div className="field-label">Nástroje serveru ({tools.length})</div>
                    <div className="signal-list compact">
                        {tools.map((t) => (
                            <div
                                className={'signal' + (t.disabled ? ' muted' : '')}
                                key={t.name}
                                title={t.description_full || t.description}
                            >
                                <Icon name={iconForTool(t.name)} />
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                                    {t.name}
                                    {t.disabled
                                        ? ' · vypnuto'
                                        : t.held_for_review
                                          ? ' · ke schválení'
                                          : ''}
                                </span>
                            </div>
                        ))}
                    </div>
                </>
            }
            center={
                <Chat
                    title="MCP-Privacy · hlas → CRM"
                    goal="Model ovládá CRM přes nástroje; jména stroj neopustí; audit dokládá každé volání"
                    builds="importuje UC-02"
                    messages={messages}
                    onClear={clearThread}
                    empty={
                        <PanelEmpty
                            icon="mic"
                            text={
                                session
                                    ? `Konverzace ${session.session.slice(0, 8)} · profil ${profile}. Napište příkaz dole nebo nadiktujte.`
                                    : 'Otevírám konverzaci…'
                            }
                        />
                    }
                    onSend={send}
                    disabled={busy || !session}
                    placeholder="Např.: Najdi kontakt Sedláček a shrň, co naposledy koupil…"
                    composerValue={draft}
                    onComposerChange={setDraft}
                    composerExtra={
                        <span className="hint">
                            {session ? `tah ${(session.turns || 0) + 1}` : ''}
                            {session ? ` · ${session.provider} / ${session.model}${session.tier ? ` / ${session.tier}` : ''}` : ''}
                        </span>
                    }
                    honest="Tah zahrnuje start vybraného CLI, připojení MCP, model a nástroje; délka závisí na hostiteli a dotazu."
                />
            }
            right={
                <>
                    <SubTabs
                        items={[
                            { id: 'audit', label: 'Audit', badge: audit.entries.length || null },
                            {
                                id: 'review',
                                label: 'Ke schválení',
                                badge: review && review.count ? review.count : null,
                            },
                            { id: 'results', label: 'Whisper' },
                        ]}
                        active={rightTab}
                        onChange={setRightTab}
                    />
                    {rightTab === 'audit' && (
                        <>
                            <div className="panel-title">
                                <Icon name="scroll-text" />
                                Auditní řetěz této konverzace
                            </div>
                            <AuditTrail entries={audit.entries} verify={audit.verify} />
                            {audit.entries.length > 0 && (
                                <div className="signal-list">
                                    <Signal icon="link">
                                        Každý hash kotví ten předchozí; změna řádku řetěz rozbije.
                                    </Signal>
                                    <Signal icon="eye-off">
                                        V logu je hash argumentů, ne jejich text.
                                    </Signal>
                                </div>
                            )}
                            {disabledTools.length > 0 && (
                                <Signal icon="lock" muted>
                                    Vypnuto v profilu {profile}: {disabledTools.join(', ')}
                                </Signal>
                            )}
                        </>
                    )}
                    {rightTab === 'review' && (
                        <>
                            <div className="panel-title">
                                <Icon name="clipboard-check" />
                                Změny polí čekající na člověka
                            </div>
                            {!review && <div className="muted-line">Načítám…</div>}
                            {review && !review.count && (
                                <PanelEmpty
                                    icon="clipboard-check"
                                    text="Fronta je prázdná. Pod profilem strict sem padne každá změna pole, kterou model požádá."
                                />
                            )}
                            {review && review.count > 0 && (
                                <div className="mini-list">
                                    {review.changes.map((c) => (
                                        <div className="mini-row col" key={c.id}>
                                            <span className="t">
                                                #{c.id} {c.entity_type} {c.entity_id} · {c.field}:{' '}
                                                {String(c.old_value)} → <b>{String(c.new_value)}</b>
                                            </span>
                                            <span className="d">
                                                {c.author} · {c.created_at} ·{' '}
                                                {c.still_current
                                                    ? 'řádek beze změny'
                                                    : 'řádek se mezitím změnil'}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <Signal icon="terminal" muted>
                                Schválení: python -m ucs.uc03_mcp_privacy.review apply &lt;id&gt;
                            </Signal>
                        </>
                    )}
                    {rightTab === 'results' && (
                        <>
                            <div className="panel-title">
                                <Icon name="audio-lines" />
                                Přepis řeči na syntetickém korpusu
                            </div>
                            {!results && <div className="muted-line">Načítám…</div>}
                            {results &&
                                Object.entries(results.summaries).map(([name, s]) => (
                                    <div className="stat-card" key={name}>
                                        <div className="stat-head">{name}</div>
                                        <KeyVals
                                            rows={Object.entries(s)
                                                .filter(([k, v]) => typeof v !== 'object')
                                                .map(([k, v]) => [
                                                    k,
                                                    typeof v === 'number'
                                                        ? Math.abs(v) < 1
                                                            ? fmtPct(v)
                                                            : v.toFixed(2)
                                                        : String(v),
                                                ])}
                                        />
                                    </div>
                                ))}
                            {results && results.readme && (
                                <details className="fold">
                                    <summary>Co čísla znamenají (eval/README.md)</summary>
                                    <MarkdownCard text={results.readme} />
                                </details>
                            )}
                        </>
                    )}
                </>
            }
        />
    );
}

Object.assign(window, { Uc03 });
