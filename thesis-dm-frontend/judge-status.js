// Display the recorded evidence without changing the cascade's routing decision.
function uc01JudgeChoice(value) {
    if (!value) return { level: 0, judges: [], arbiter: null };
    if (value.provider) return { level: 1, judges: [value], arbiter: null };
    return value;
}

function uc01ModelStatus(verdict) {
    if (!verdict) return 'not-run';
    if (verdict.status === 'MALFORMED') return 'error';
    if (verdict.status === 'PARTIAL') return 'partial';
    if (verdict.status === 'FULL' && ['valid', 'invalid'].includes(verdict.verdict)) return verdict.verdict;
    return 'error';
}

function uc01PairStatus(judges) {
    if (judges.length < 2) return 'not-run';
    const [first, second] = judges;
    if ([first, second].some((v) => uc01ModelStatus(v) === 'error')) return 'error';
    const same = ['vocative', 'register', 'gender'].every((key) =>
        typeof first.ok?.[key] === 'boolean' && first.ok[key] === second.ok?.[key]);
    if (first.status === 'FULL' && second.status === 'FULL' && same) return uc01ModelStatus(first);
    return 'partial';
}

function uc01JudgeTrailHtml(rules, judgment, config) {
    const labels = { valid: 'valid', partial: 'partial', invalid: 'invalid', error: 'chyba hodnocení', 'not-run': 'neprovedeno' };
    function row(title, state, detail = '') {
        return `<div class="judge-stage"><span class="judge-status judge-status-${state}"><span class="judge-dot" aria-hidden="true"></span>${escHtml(labels[state])}</span><span>${escHtml(title)}${detail ? `<small>${escHtml(detail)}</small>` : ''}</span></div>`;
    }
    function identity(spec) {
        return spec ? `${spec.provider} / ${spec.model || 'výchozí model'}${spec.tier ? ' · ' + spec.tier : ''}` : '';
    }
    const judges = judgment?.judges || [];
    const selected = config?.level || 0;
    let html = row('Úroveň 0 · pravidla', !rules ? 'not-run' : rules.accepted ? 'valid' : 'invalid');
    if (selected >= 1) html += row('Úroveň 1 · soudce 1', uc01ModelStatus(judges[0]), identity(judges[0] || config.judges?.[0]));
    if (selected >= 2) {
        html += row('Soudce 2', uc01ModelStatus(judges[1]), identity(judges[1] || config.judges?.[1]));
        html += row('Úroveň 2 · dva soudci', uc01PairStatus(judges), 'Společné hodnocení obou soudců');
    }
    if (selected >= 3) {
        const arbiter = judgment?.arbiter;
        html += row('Úroveň 3 · eskalace na arbitra', uc01ModelStatus(arbiter),
            arbiter ? identity(arbiter) : judges.length === 2 && ['valid', 'invalid'].includes(uc01PairStatus(judges))
                ? 'Nebylo potřeba: oba soudci se shodli.' : identity(config.arbiter));
    }
    if (judgment) html += `<p class="hint">Výsledek kaskády: ${escHtml(judgment.final)} · ${escHtml(judgment.reason || '')}${judgment.final === 'HUMAN' ? ' · rozhodne člověk' : ''}</p>`;
    return `<div class="judge-trail" aria-label="Výsledky úrovní soudce">${html}</div>`;
}
