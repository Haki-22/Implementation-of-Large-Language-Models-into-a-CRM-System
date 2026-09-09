// ============================================================
// Kod tab: the repository as git sees it: tree, READMEs rendered in place, files with
// line numbers, search; beside it the explainer that cites the open file.
// ============================================================

const CODE_QUESTIONS = [
    'Co dělá tento soubor a kdo ho volá?',
    'Jak funguje deterministická vrstva v pseudonymizéru?',
    'Kde se UC-02 znovu použije v UC-03?',
    'Jak se měří úspěšnost doporučení v aréně?',
];

function resolveRelative(fromDir, href) {
    const base = 'http://repo/' + (fromDir ? fromDir + '/' : '');
    try {
        const url = new URL(href, base);
        if (url.host !== 'repo') return null;
        return { path: decodeURIComponent(url.pathname.replace(/^\/+/, '')), hash: url.hash };
    } catch (e) {
        return null;
    }
}

// Keep repository-relative image links valid when Markdown is shown under /dm/.
// Build the sanitized HTML off-screen so the browser never requests the old URL.
function repositoryMarkdown(text, fromDir) {
    const template = document.createElement('template');
    template.innerHTML = md(text);
    const assetPrefix = 'thesis-dm-frontend/assets/';
    for (const img of template.content.querySelectorAll('img[src]')) {
        const src = img.getAttribute('src');
        if (/^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(src)) continue;
        const target = resolveRelative(fromDir, src);
        if (target && target.path.startsWith(assetPrefix)) {
            const asset = target.path.slice(assetPrefix.length).split('/').map(encodeURIComponent).join('/');
            img.setAttribute('src', '/dm/assets/' + asset + target.hash);
        }
    }
    return template.innerHTML;
}

function CodeView({ content, highlight }) {
    const lines = (content || '').split('\n');
    return (
        <div className="code-view">
            <table>
                <tbody>
                    {lines.map((l, i) => (
                        <tr key={i} className={highlight === i + 1 ? 'hl' : ''} id={'L' + (i + 1)}>
                            <td className="ln">{i + 1}</td>
                            <td>{l}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function UcCode({ settings }) {
    const [tree, setTree] = useState(null);
    const [file, setFile] = useState(null);
    const [highlight, setHighlight] = useState(null);
    const [loading, setLoading] = useState(false);
    const [query, setQuery] = useState('');
    const [hits, setHits] = useState(null);
    const { messages, setMessages, restored, remember, clearThread } = usePageHistory('code');
    const [busy, setBusy] = useState(false);
    const [useLlm, setUseLlm] = useState(false);
    const docRef = useRef(null);
    useLucide();
    useEffect(() => {
        if (!restored) return;
        applyRestored(restored.state, { query: setQuery, useLlm: setUseLlm });
        if (restored.state.path) openFile(restored.state.path);
    }, [restored]);
    useEffect(
        () => remember({ path: file ? file.path : null, query, useLlm }),
        [file, query, useLlm],
    );

    async function openDir(path) {
        try {
            const t = await getJson('/repo/tree', { path });
            setTree(t);
            return t;
        } catch (e) {
            toast.error(e.message);
            return null;
        }
    }
    async function openFile(path, line) {
        setLoading(true);
        setHighlight(line || null);
        try {
            const f = await getJson('/repo/file', { path });
            setFile(f);
            if (tree === null || (tree.path !== f.dir && !(tree.path === '' && f.dir === '')))
                await openDir(f.dir);
            if (line)
                setTimeout(() => {
                    const row = document.getElementById('L' + line);
                    if (row) row.scrollIntoView({ block: 'center' });
                }, 50);
        } catch (e) {
            toast.error(e.message);
        } finally {
            setLoading(false);
        }
    }
    async function enterDir(path) {
        const t = await openDir(path);
        if (t && t.readme) openFile(t.readme);
    }
    useEffect(() => {
        openFile('README.md');
    }, []);

    // Relative links inside a rendered README open the target in this tab.
    useEffect(() => {
        const el = docRef.current;
        if (!el || !file) return;
        function onClick(e) {
            const a = e.target.closest('a');
            if (!a) return;
            const href = a.getAttribute('href') || '';
            if (/^(https?:|mailto:)/.test(href)) {
                a.setAttribute('target', '_blank');
                return;
            }
            if (href.startsWith('#')) return;
            const target = resolveRelative(file.dir, href);
            if (!target) {
                e.preventDefault(); // any other scheme (javascript:, data:, file:) is refused
                return;
            }
            e.preventDefault();
            const clean = target.path.replace(/\/$/, '');
            if (!clean || clean.endsWith('/')) return enterDir(clean);
            const isDir = tree && tree.dirs.some((d) => d.path === clean);
            if (isDir || !/\.[a-z0-9]+$/i.test(clean)) enterDir(clean);
            else openFile(clean);
        }
        el.addEventListener('click', onClick);
        return () => el.removeEventListener('click', onClick);
    }, [file, tree]);

    async function search(q) {
        const s = q.trim();
        setQuery(q);
        if (s.length < 2) {
            setHits(null);
            return;
        }
        try {
            const r = await getJson('/repo/search', { q: s, limit: 60 });
            setHits(r.hits);
        } catch (e) {
            toast.error(e.message);
        }
    }

    async function ask(q) {
        if (busy) return;
        setBusy(true);
        setMessages((m) => [
            ...m,
            { role: 'user', text: [escHtml(q)] },
            { role: 'ai', typing: true },
        ]);
        try {
            const res = await postJson('/code/ask', {
                question: q,
                file_path: file ? file.path : null,
                use_llm: useLlm,
                ...generationFields(settings),
            });
            setMessages((m) => {
                const next = m.slice(0, -1);
                next.push({
                    role: 'ai',
                    html: `<p style="margin:0">${sanitizeHtml(res.answer, ANSWER_TAGS)}</p>`,
                    meta: `${res.file.path} — ${res.used_llm ? `${res.provider}${res.model ? ' / ' + res.model : ''} · ${(res.latency_ms / 1000).toFixed(1)} s` : 'rychlý router (bez modelu)'}`,
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

    const crumbs = tree ? tree.crumbs : [];
    return (
        <UseCaseShell
            left={
                <>
                    <div className="uc-search">
                        <Icon name="search" size={16} />
                        <input
                            placeholder="Hledat v repozitáři (git grep)…"
                            value={query}
                            onChange={(e) => search(e.target.value)}
                        />
                    </div>
                    {hits !== null ? (
                        <>
                            <div className="muted-line">
                                {hits.length} nálezů pro „{query.trim()}“ ·{' '}
                                <button className="linklike" onClick={() => search('')}>
                                    zpět na strom
                                </button>
                            </div>
                            <div className="search-hits">
                                {hits.map((h, i) => (
                                    <button
                                        key={i}
                                        className="search-hit"
                                        onClick={() => openFile(h.path, h.line)}
                                    >
                                        <span className="p">
                                            {h.path}:{h.line}
                                        </span>
                                        <span className="t">{h.text}</span>
                                    </button>
                                ))}
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="crumbs">
                                <button onClick={() => enterDir('')}>thesis</button>
                                {crumbs.map((c) => (
                                    <React.Fragment key={c.path}>
                                        <span className="sep">/</span>
                                        <button onClick={() => enterDir(c.path)}>{c.name}</button>
                                    </React.Fragment>
                                ))}
                            </div>
                            <div className="repo-list">
                                {tree && tree.path && (
                                    <button
                                        className="filerow dir"
                                        onClick={() =>
                                            enterDir(
                                                tree.path.includes('/')
                                                    ? tree.path.slice(0, tree.path.lastIndexOf('/'))
                                                    : '',
                                            )
                                        }
                                    >
                                        <Icon name="corner-left-up" />
                                        ..
                                    </button>
                                )}
                                {(tree ? tree.dirs : []).map((d) => (
                                    <button
                                        key={d.path}
                                        className={'filerow dir' + (d.readme ? ' readme' : '')}
                                        onClick={() => enterDir(d.path)}
                                        title={d.readme ? 'má README' : ''}
                                    >
                                        <Icon name={d.readme ? 'book-open' : 'folder'} />
                                        {d.name}/<span className="meta">{d.files}</span>
                                    </button>
                                ))}
                                {(tree ? tree.files : []).map((f) => (
                                    <button
                                        key={f.path}
                                        className={
                                            'filerow' +
                                            (file && file.path === f.path ? ' sel' : '') +
                                            (f.name.toLowerCase() === 'readme.md' ? ' readme' : '')
                                        }
                                        onClick={() => openFile(f.path)}
                                    >
                                        <Icon
                                            name={
                                                f.kind === 'markdown'
                                                    ? 'book-open'
                                                    : f.kind === 'binary'
                                                      ? 'file-archive'
                                                      : 'file-code'
                                            }
                                        />
                                        {f.name}
                                        <span className="meta">
                                            {f.size !== null && f.size !== undefined
                                                ? f.size > 1e6
                                                    ? (f.size / 1e6).toFixed(1) + ' MB'
                                                    : f.size > 1000
                                                      ? Math.round(f.size / 1000) + ' kB'
                                                      : f.size + ' B'
                                                : ''}
                                        </span>
                                    </button>
                                ))}
                            </div>
                            {tree && (
                                <div className="muted-line">
                                    {tree.total_tracked} sledovaných souborů · {tree.source}
                                </div>
                            )}
                        </>
                    )}
                </>
            }
            center={
                <>
                    <div className="doc-head">
                        <Icon
                            name={file && file.kind === 'markdown' ? 'book-open' : 'file-code'}
                            size={15}
                        />
                        <span className="path">{file ? file.path : '…'}</span>
                        {file && (
                            <span>
                                {file.size > 1000
                                    ? Math.round(file.size / 1000) + ' kB'
                                    : file.size + ' B'}
                                {file.truncated ? ' · zkráceno' : ''}
                                {file.kind === 'binary' ? ' · binární' : ''}
                            </span>
                        )}
                        {loading && <span>načítám…</span>}
                    </div>
                    <div className="doc-scroll" ref={docRef}>
                        {!file && <PanelEmpty icon="book-open" text="Vyberte soubor vlevo." />}
                        {file && file.kind === 'markdown' && (
                            <div
                                className="md-card"
                                dangerouslySetInnerHTML={{ __html: repositoryMarkdown(file.content, file.dir) }}
                            />
                        )}
                        {file && (file.kind === 'code' || file.kind === 'text') && (
                            <CodeView content={file.content} highlight={highlight} />
                        )}
                        {file && file.kind === 'binary' && (
                            <PanelEmpty
                                icon="file-archive"
                                text="Binární soubor; v repozitáři je jako artefakt (snímek, archiv, model)."
                            />
                        )}
                    </div>
                </>
            }
            right={
                <>
                    <div className="panel-title">
                        <Icon name="message-square" />
                        Zeptejte se na otevřený soubor
                    </div>
                    <div className="set-row compact">
                        <div>
                            <div className="lbl">Odpověď modelem</div>
                            <div className="sub">
                                {useLlm
                                    ? `${settings.provider}${settings.model ? ' / ' + settings.model : ''} nad prvními 200 řádky`
                                    : 'bez modelu: router s citací'}
                            </div>
                        </div>
                        <span className="grow"></span>
                        <button
                            className={'toggle' + (useLlm ? ' on' : '')}
                            onClick={() => setUseLlm((v) => !v)}
                        ></button>
                    </div>
                    <div className="chip-col">
                        {CODE_QUESTIONS.map((q, i) => (
                            <button
                                key={i}
                                className="chip-line"
                                disabled={busy}
                                onClick={() => ask(q)}
                            >
                                {q}
                            </button>
                        ))}
                    </div>
                    <div className="side-chat">
                        <Thread
                            messages={messages}
                            empty={
                                <PanelEmpty
                                    icon="folder-search"
                                    text="Odpověď cituje otevřený soubor."
                                />
                            }
                        />
                        <Composer onSend={ask} disabled={busy} placeholder="Otázka k souboru…" />
                    </div>
                </>
            }
        />
    );
}

Object.assign(window, { UcCode });
