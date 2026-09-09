// ============================================================
// thesis dm — the chat: bubbles with folds and meta lines, the thread, the composer,
// the guide, the chat header, the three-pane shell. Every tab composes these.
// ============================================================

// A turn: { role: 'user'|'ai', text: [..] | html, typing, meta, folds: [{title, html}] }
function Message({ turn }) {
    const isUser = turn.role === 'user';
    return (
        <div className={'turn ' + (isUser ? 'user' : 'ai')}>
            <div className="msg-av">
                {isUser ? (
                    <Icon name="user" size={17} style={{ color: '#fff' }} />
                ) : (
                    <img src="assets/logo.svg" alt="" />
                )}
            </div>
            <div className="bubble">
                {turn.typing ? (
                    <div className="typing">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                ) : turn.html ? (
                    <div dangerouslySetInnerHTML={{ __html: turn.html }} />
                ) : (
                    (turn.text || []).map((p, i) => (
                        <p key={i} dangerouslySetInnerHTML={{ __html: p }} />
                    ))
                )}
                {turn.meta && !turn.typing && <div className="bubble-meta">{turn.meta}</div>}
                {(turn.folds || []).map((f, i) => (
                    <details className="fold" key={i}>
                        <summary>{f.title}</summary>
                        <div className="fold-body" dangerouslySetInnerHTML={{ __html: f.html }} />
                    </details>
                ))}
            </div>
        </div>
    );
}

function Thread({ messages, empty }) {
    const endRef = useRef(null);
    useEffect(() => {
        if (endRef.current) endRef.current.parentElement.scrollTop = endRef.current.offsetTop;
    }, [messages]);
    if (!messages.length && empty) {
        return (
            <div className="thread">
                <div className="thread-inner">{empty}</div>
            </div>
        );
    }
    return (
        <div className="thread">
            <div className="thread-inner">
                {messages.map((m, i) => (
                    <Message key={i} turn={m} />
                ))}
                <div ref={endRef}></div>
            </div>
        </div>
    );
}

function Composer({ onSend, placeholder, disabled, value, onChange, extra }) {
    const [inner, setInner] = useState('');
    const controlled = value !== undefined;
    const val = controlled ? value : inner;
    const setVal = controlled ? onChange : setInner;
    const taRef = useRef(null);
    function grow() {
        const ta = taRef.current;
        if (!ta) return;
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
    }
    function submit() {
        const t = String(val || '').trim();
        if (!t || disabled) return;
        onSend(t);
        setVal('');
        requestAnimationFrame(() => {
            if (taRef.current) taRef.current.style.height = 'auto';
        });
    }
    return (
        <div className="composer-wrap">
            <div className="composer-inner">
                <div className="composer">
                    <textarea
                        ref={taRef}
                        rows={1}
                        placeholder={placeholder || 'Napište zprávu…'}
                        value={val}
                        disabled={disabled}
                        onChange={(e) => {
                            setVal(e.target.value);
                            grow();
                        }}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                submit();
                            }
                        }}
                    />
                    <div className="toolbar">
                        {extra}
                        <span className="grow"></span>
                        <span className="hint">Enter pro odeslání</span>
                        <button
                            className="send"
                            disabled={!String(val || '').trim() || disabled}
                            onClick={submit}
                            title="Odeslat"
                        >
                            <Icon name="arrow-up" size={20} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// One chat column: header, thread, optional composer, honest line.
function Chat({
    title,
    goal,
    builds,
    onClear,
    messages,
    empty,
    onSend,
    placeholder,
    disabled,
    composerValue,
    onComposerChange,
    composerExtra,
    honest,
}) {
    return (
        <>
            <ChatHead
                title={title}
                goal={goal}
                builds={builds}
                onClear={messages && messages.length ? onClear : null}
            />
            <Thread messages={messages} empty={empty} />
            {onSend && (
                <Composer
                    onSend={onSend}
                    placeholder={placeholder}
                    disabled={disabled}
                    value={composerValue}
                    onChange={onComposerChange}
                    extra={composerExtra}
                />
            )}
            {honest && <Honest text={honest} />}
        </>
    );
}

function Guide({ steps }) {
    return (
        <div className="guide">
            <div className="gh">
                <Icon name="compass" size={15} />
                Jak demo použít
            </div>
            <ol>
                {steps.map((s, i) => (
                    <li key={i} dangerouslySetInnerHTML={{ __html: s }} />
                ))}
            </ol>
        </div>
    );
}

function ChatHead({ title, goal, builds, onClear }) {
    return (
        <div className="chat-head">
            <div>
                <h2 className="h1">{title}</h2>
                <div className="goal">{goal}</div>
            </div>
            {builds && (
                <span className="builds">
                    <Icon name="link" size={13} />
                    {builds}
                </span>
            )}
            {onClear && (
                <button
                    className="head-clear"
                    onClick={onClear}
                    title="Vyprázdní vlákno; historie záložky v mostu se přepíše prázdným vláknem"
                >
                    <Icon name="eraser" size={14} />
                    Vyčistit
                </button>
            )}
        </div>
    );
}

function Honest({ text }) {
    return (
        <div className="honest">
            <Icon name="info" size={13} />
            {text}
        </div>
    );
}

function PanelEmpty({ icon, text }) {
    return (
        <div className="panel-empty">
            <Icon name={icon} />
            {text}
        </div>
    );
}

// The middle column exists only when there is something to show in it; until the first
// result the setup on the left and the card on the right share the width.
function UseCaseShell({ left, center, right }) {
    return (
        <div className={'app-body' + (center ? '' : ' no-center')}>
            <aside className="uc-left">{left}</aside>
            {center && <main className="chat">{center}</main>}
            <aside className="uc-right">{right}</aside>
        </div>
    );
}

Object.assign(window, {
    Message,
    Thread,
    Composer,
    Chat,
    Guide,
    ChatHead,
    Honest,
    PanelEmpty,
    UseCaseShell,
});
