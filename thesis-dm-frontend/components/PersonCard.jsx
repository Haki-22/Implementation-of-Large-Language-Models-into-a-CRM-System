// ============================================================
// thesis dm — the person: a searchable list of contacts and the card of one contact.
// UC-01 and UC-04 read the same card (/uc01/contacts/{id}).
// ============================================================

function OceanBars({ ocean }) {
    if (!ocean)
        return (
            <Signal icon="brain" muted>
                Profil OCEAN chybí.
            </Signal>
        );
    const rows = [
        ['O', 'otevřenost'],
        ['C', 'svědomitost'],
        ['E', 'extraverze'],
        ['A', 'přívětivost'],
        ['N', 'neuroticismus'],
    ];
    return (
        <div className="ocean">
            {rows.map(([k, label]) => {
                const v = Number(ocean[k] || 0);
                return (
                    <div className="b" key={k} title={label}>
                        <span className="k">{k}</span>
                        <span className="track">
                            <span
                                className="fill"
                                style={{ width: Math.round((v / 5) * 100) + '%' }}
                            ></span>
                        </span>
                        <span className="v">{v.toFixed(1)}</span>
                    </div>
                );
            })}
        </div>
    );
}

// contacts: [{id, name, city, pick: {tier, stratum}}]; onSearch(query) hits the bridge
function PersonList({ contacts, value, onChange, onSearch, searching, scopeLabel }) {
    const [q, setQ] = useState('');
    const timer = useRef(null);
    function update(next) {
        setQ(next);
        if (!onSearch) return;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => onSearch(next), 250);
    }
    return (
        <>
            <div className="uc-search">
                <Icon name="search" size={16} />
                <input
                    placeholder="Hledat kontakt (jméno, město, e-mail)…"
                    value={q}
                    onChange={(e) => update(e.target.value)}
                />
            </div>
            {scopeLabel && <div className="muted-line">{scopeLabel}</div>}
            <div className="opt-list">
                {contacts.map((c) => (
                    <button
                        key={c.id}
                        className={'opt' + (value === c.id ? ' sel' : '')}
                        onClick={() => onChange(c.id)}
                    >
                        <span className="av">{initials(c.name)}</span>
                        <span style={{ minWidth: 0 }}>
                            <div className="nm">{c.name}</div>
                            <div className="sub">
                                #{c.id}
                                {c.city ? ' · ' + c.city : ''}
                                {c.pick && c.pick.tier
                                    ? ' · ' + (c.pick.tier === 'linked' ? 's historií' : 'prospekt')
                                    : ''}
                                {c.pick && c.pick.stratum === 'defective'
                                    ? ' · defektní řádek'
                                    : ''}
                                {c.hidden ? ' · skrytý: ' + c.hidden.title_cs : ''}
                            </div>
                        </span>
                    </button>
                ))}
                {searching && <div className="muted-line">Hledám v databázi…</div>}
                {!searching && !contacts.length && (
                    <div className="muted-line">Nic nenalezeno.</div>
                )}
            </div>
        </>
    );
}

// card: the payload of GET /uc01/contacts/{id}
function PersonCard({ card, loading, error, emphasis }) {
    if (error) return <ErrorLine error={error} />;
    if (loading || !card)
        return (
            <PanelEmpty
                icon="user-round"
                text={loading ? 'Načítám kartu…' : 'Vyberte kontakt vlevo.'}
            />
        );
    const gender = card.gender === 'f' ? 'žena' : card.gender === 'm' ? 'muž' : 'neznámý';
    const formal = card.formal === true ? 'vykání' : card.formal === false ? 'tykání' : 'neznámá';
    const levelsOff = (card.levels || []).filter((l) => !l.ok);
    return (
        <div className="person">
            <div className="person-head">
                <span className="av">{initials(card.name)}</span>
                <div style={{ minWidth: 0 }}>
                    <div className="nm">{card.name}</div>
                    <div className="sub">
                        #{card.id} · {card.city || 'město neznámé'}
                        {card.employer ? ' · ' + card.employer : ''}
                    </div>
                </div>
            </div>
            <div className="tag-row">
                <span className="pill">{card.name_vocative || 'bez oslovení'}</span>
                <span className="pill">{gender}</span>
                <span className="pill">{formal}</span>
                {card.is_clean === false && <span className="pill warn">defektní řádek</span>}
                {card.pick && card.pick.tier && (
                    <span className="pill">
                        {card.pick.tier === 'linked' ? 'pick: s historií' : 'pick: prospekt'}
                    </span>
                )}
            </div>
            <KeyVals
                rows={[
                    ['Vztah', card.lifecycle_label],
                    ['Role', card.title],
                    ['Skupina', card.amazon_group ? 'Amazon ' + card.amazon_group : null],
                    ['E-mail', card.email],
                    ['Telefon', card.phone],
                    ['Objednávek', card.orders],
                    ['Recenzí', card.reviews],
                ]}
            />
            {emphasis === 'orders' || (card.purchases && card.purchases.length) ? (
                <>
                    <div className="panel-title">
                        <Icon name="shopping-bag" />
                        Poslední nákupy
                    </div>
                    <div className="mini-list">
                        {(card.purchases || []).map((p, i) => (
                            <div className="mini-row" key={i}>
                                <span className="d">{p.order_date}</span>
                                <span className="t" title={p.name}>
                                    {p.name}
                                </span>
                            </div>
                        ))}
                        {!(card.purchases || []).length && (
                            <div className="muted-line">Bez historie nákupů.</div>
                        )}
                    </div>
                </>
            ) : null}
            {card.frequent_words && card.frequent_words.length > 0 && (
                <>
                    <div className="panel-title">
                        <Icon name="type" />
                        Častá slova
                    </div>
                    <div className="tag-row">
                        {card.frequent_words.slice(0, 8).map((w, i) => (
                            <span className="pill soft" key={i}>
                                {w}
                            </span>
                        ))}
                    </div>
                </>
            )}
            {card.style_excerpt && (
                <>
                    <div className="panel-title">
                        <Icon name="quote" />
                        Ukázka stylu psaní (nejdelší recenze zákazníka, příčka 3a)
                    </div>
                    <div className="excerpt">{card.style_excerpt}</div>
                </>
            )}
            <div className="panel-title">
                <Icon name="brain" />
                Osobnost (OCEAN) ·{' '}
                {card.ocean_source === 'inferred'
                    ? 'odvozená z recenzí'
                    : card.ocean_source === 'sampled'
                      ? 'vzorkovaná'
                      : card.ocean_source || '—'}
            </div>
            <OceanBars ocean={card.ocean} />
            {card.recommendations && card.recommendations.length > 0 && (
                <>
                    <div className="panel-title">
                        <Icon name="target" />
                        Doporučení z UC-04
                    </div>
                    <div className="mini-list">
                        {card.recommendations.slice(0, 3).map((r, i) => (
                            <div className="mini-row" key={i}>
                                <span className="d">{r.rank}.</span>
                                <span className="t" title={r.reason_cs || ''}>
                                    {r.name}
                                </span>
                            </div>
                        ))}
                    </div>
                </>
            )}
            {card.levels && (
                <>
                    <div className="panel-title">
                        <Icon name="layers" />
                        Příčky žebříku
                    </div>
                    {levelsOff.length ? (
                        <div className="muted-line">
                            Nelze:{' '}
                            {levelsOff
                                .map(
                                    (l) =>
                                        `${l.level} (chybí ${l.missing.map((m) => SLOT_LABELS[m] || m).join(', ')})`,
                                )
                                .join(' · ')}
                        </div>
                    ) : (
                        <Signal icon="check-circle-2">
                            Kontakt má data pro všech {card.levels.length} příček.
                        </Signal>
                    )}
                </>
            )}
        </div>
    );
}

// Loads the card for a contact id; shared by UC-01 and UC-04.
function useContactCard(contactId) {
    const [card, setCard] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    useEffect(() => {
        if (!contactId) return;
        let alive = true;
        setLoading(true);
        setError('');
        getJson('/uc01/contacts/' + contactId)
            .then((d) => alive && setCard(d))
            .catch((e) => alive && setError(e.message))
            .finally(() => alive && setLoading(false));
        return () => {
            alive = false;
        };
    }, [contactId]);
    return { card, loading, error };
}

Object.assign(window, { OceanBars, PersonList, PersonCard, useContactCard });
