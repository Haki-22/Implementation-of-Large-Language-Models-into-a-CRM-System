// Each model role is configured independently; Claude is deliberately unavailable.
function Uc01JudgeModel({ catalog, value, onChange, id, label }) {
    const selected = settingsFromCatalog(catalog, value);
    const provider = providerOf(catalog, selected.provider);
    const tiers = tiersOf(catalog, selected.provider, selected.model);
    function choose(change) {
        const next = settingsFromCatalog(catalog, { ...selected, ...change });
        onChange({ provider: next.provider, model: next.model, tier: next.tier });
    }
    return (
        <fieldset className="judge-role">
            <legend>{label}</legend>
            <label className="field-label" htmlFor={`${id}-provider`}>Poskytovatel · {label}</label>
            <select id={`${id}-provider`} className="uc-select" value={selected.provider}
                onChange={(e) => choose({ provider: e.target.value, model: null })}>
                {catalog.providers.filter((p) => ['codex', 'agy'].includes(p.id)).map((p) =>
                    <option key={p.id} value={p.id}>{p.id}</option>)}
            </select>
            <label className="field-label" htmlFor={`${id}-model`}>Model · {label}</label>
            <select id={`${id}-model`} className="uc-select" value={selected.model}
                onChange={(e) => choose({ model: e.target.value })}>
                {provider.models.filter((m) => !/claude|sonnet|opus|haiku/i.test(m.id)).map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}
            </select>
            <label className="field-label" htmlFor={`${id}-tier`}>Úroveň uvažování · {label}</label>
            <select id={`${id}-tier`} className="uc-select" value={selected.tier || ''}
                disabled={!tiers.length} onChange={(e) => choose({ tier: e.target.value })}>
                {tiers.length ? tiers.map((tier) => <option key={tier}>{tier}</option>) : <option value="">nepoužívá se</option>}
            </select>
        </fieldset>
    );
}

function Uc01JudgePicker({ catalog, value, onChange }) {
    const selected = uc01JudgeChoice(value);
    const names = ['Jen pravidla', 'Jeden soudce', 'Dva soudci', 'Dva soudci + eskalace'];
    function defaultRole(provider, tier = 'low') {
        const role = settingsFromCatalog(catalog, { provider, tier });
        return { provider: role.provider, model: role.model, tier: role.tier };
    }
    function chooseLevel(level) {
        if (!level) return onChange(null);
        const first = selected.judges[0] || defaultRole('codex');
        const second = selected.judges[1] || defaultRole(first.provider === 'codex' ? 'agy' : 'codex');
        onChange({ level, judges: level === 1 ? [first] : [first, second],
            arbiter: level === 3 ? selected.arbiter || defaultRole('codex', 'high') : null });
    }
    function chooseJudge(index, role) {
        onChange({ ...selected, judges: selected.judges.map((old, i) => i === index ? role : old) });
    }
    return (
        <>
            <label className="field-label" htmlFor="uc01-judge-level">Úroveň soudce</label>
            <select id="uc01-judge-level" className="uc-select" value={selected.level}
                disabled={!catalog} onChange={(e) => chooseLevel(Number(e.target.value))}>
                {names.map((name, level) => <option key={level} value={level}>{level} · {name}</option>)}
            </select>
            {catalog && selected.judges.map((role, index) =>
                <Uc01JudgeModel key={index} catalog={catalog} value={role} id={`uc01-judge-${index + 1}`}
                    label={`Soudce ${index + 1}`} onChange={(next) => chooseJudge(index, next)} />)}
            {catalog && selected.level === 3 && <Uc01JudgeModel catalog={catalog} value={selected.arbiter}
                id="uc01-arbiter" label="Arbitr" onChange={(arbiter) => onChange({ ...selected, arbiter })} />}
            <p className="hint">Pravidla běží vždy první. Úroveň 1 volá jednoho soudce, úroveň 2 dva.
                Úroveň 3 přidá arbitra jen při neshodě, neúplném hodnocení nebo chybě soudce.
                Každá role má vlastní model i úroveň uvažování. Claude se nepoužívá.</p>
            {selected.level >= 2 && <p className="hint">Dva soudci musí mít různé providery.
                Arbitr může sdílet providera; nejde pak o nezávislé posouzení třetím providerem.</p>}
            <p className="hint">Hodnotí oslovení, vykání/tykání a rod, nikoli pravdivost všech tvrzení.</p>
        </>
    );
}
