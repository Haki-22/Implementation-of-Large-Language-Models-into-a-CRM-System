// ============================================================
// thesis dm — run folders and cards: a picker over run folders, a Markdown card,
// a rows table, the progress of a background job.
// ============================================================

// runs: [{name, kind, date|created, record, ...}]; renders one line per folder
function RunPicker({ runs, value, onChange, describe }) {
    if (!runs || !runs.length)
        return <PanelEmpty icon="folder-open" text="Zatím žádná složka běhu." />;
    return (
        <div className="opt-list">
            {runs.map((r) => (
                <button
                    key={r.name}
                    className={'opt run' + (value === r.name ? ' sel' : '')}
                    onClick={() => onChange(r.name)}
                    title={r.name}
                >
                    <span className={'av' + (r.record ? ' rec' : '')}>
                        {r.record ? '★' : (r.kind || '?').slice(0, 2)}
                    </span>
                    <span style={{ minWidth: 0 }}>
                        <div className="nm">{shortRun(r.name)}</div>
                        <div className="sub">
                            {describe ? describe(r) : r.date || r.created || ''}
                        </div>
                    </span>
                </button>
            ))}
        </div>
    );
}

// Markdown rendered from a card file (RESULTS.md, TABLE.md, README.md)
function MarkdownCard({ text, empty }) {
    if (!text) return <PanelEmpty icon="file-text" text={empty || 'Karta zatím není.'} />;
    return <div className="md-card" dangerouslySetInnerHTML={{ __html: md(text) }} />;
}

// rows: list of dicts; columns: [{key, label, fmt}]
function RowsTable({ rows, columns, empty }) {
    if (!rows || !rows.length) return <div className="muted-line">{empty || 'Bez řádků.'}</div>;
    return (
        <div className="table-wrap">
            <table className="rows">
                <thead>
                    <tr>
                        {columns.map((c) => (
                            <th key={c.key}>{c.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className={r._hit ? 'hit' : ''}>
                            {columns.map((c) => (
                                <td key={c.key}>
                                    {c.fmt ? c.fmt(r[c.key], r) : (r[c.key] ?? '—')}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// job: the record of GET /jobs/{id}
function JobProgress({ job, onDone }) {
    const notified = useRef(null);
    useEffect(() => {
        if (
            job &&
            (job.state === 'done' || job.state === 'failed') &&
            notified.current !== job.id
        ) {
            notified.current = job.id;
            if (onDone) onDone(job);
        }
    }, [job && job.state]);
    if (!job) return null;
    const running = job.state === 'queued' || job.state === 'running';
    return (
        <div className={'job ' + job.state}>
            <div className="job-head">
                <Icon
                    name={running ? 'loader' : job.state === 'done' ? 'check-circle-2' : 'x-circle'}
                    size={15}
                />
                <span className="job-label">{job.label}</span>
                <span className="job-state">
                    {running ? 'běží' : job.state === 'done' ? 'hotovo' : 'selhalo'}
                </span>
            </div>
            {running && <ProgressBar done={job.done} total={job.total} />}
            {job.elapsed_seconds !== null && job.elapsed_seconds !== undefined && (
                <div className="muted-line">{fmtSeconds(job.elapsed_seconds)} od startu</div>
            )}
            {job.error && <ErrorLine error={job.error} />}
            {job.result && job.result.run_dir && (
                <Signal icon="folder-open">
                    Složka běhu: {job.result.run_dir}
                    {job.result.messages !== undefined ? ` · ${job.result.messages} zpráv` : ''}
                    {job.result.llm_calls !== undefined ? ` · volání ${fmtCalls(job.result.llm_calls)}` : ''}
                    {job.result.reused !== undefined ? ` · ${job.result.reused} převzato` : ''}
                </Signal>
            )}
            {job.log && job.log.length > 0 && (
                <details className="fold">
                    <summary>Log ({job.log.length})</summary>
                    <pre className="fold-body mono">{job.log.slice(-25).join('\n')}</pre>
                </details>
            )}
        </div>
    );
}

Object.assign(window, { RunPicker, MarkdownCard, RowsTable, JobProgress });
