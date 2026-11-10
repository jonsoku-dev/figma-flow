import React, { createContext, useContext, useId } from 'react';
import {
  PanelsTopLeft,
  ListTodo,
  History,
  MessagesSquare,
  CircleCheck,
  CircleAlert,
  LoaderCircle,
  Info,
  ChevronRight,
} from 'lucide-react';

export const PanelContext = createContext(null);
const destinations = [
  ['tasks', ListTodo],
  ['history', History],
  ['codex', MessagesSquare],
];

export function Shell({
  view,
  active = view === 'chat' ? 'codex' : 'tasks',
  busy = false,
  onNavigate,
  onLocale,
  title,
  description,
  children,
}) {
  const { t, locale, setLocale, hostBusy } = useContext(PanelContext);
  const home = view === 'workspace',
    navigation = window.FlowWorkspace;
  const showNav = home || Boolean(navigation);
  function go(key) {
    if (home) onNavigate?.(key);
    else navigation?.go(key);
  }
  function language(code) {
    setLocale(code);
    if (onLocale) onLocale(code);
    else navigation?.setLocale(code);
  }
  function keys(event) {
    const buttons = [...event.currentTarget.querySelectorAll('button:not(:disabled)')];
    const index = buttons.indexOf(document.activeElement);
    if (index < 0 || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? buttons.length - 1
          : (index + (event.key === 'ArrowLeft' ? -1 : 1) + buttons.length) % buttons.length;
    buttons[next].focus();
    if (home) buttons[next].click();
  }
  return (
    <>
      <header className="masthead panel-shell">
        <div className="brand">
          <span className="brand-mark">
            <PanelsTopLeft size={16} aria-hidden="true" />
          </span>
          Figma Flow
        </div>
        <label className="workspace-toolbar">
          <span>{t('workspace.language')}</span>
          <select id="workspace-locale" value={locale} onChange={(e) => language(e.target.value)}>
            <option value="ko">한국어</option>
            <option value="en">English</option>
            <option value="ja">日本語</option>
          </select>
        </label>
      </header>
      {showNav && (
        <nav
          className="workspace-tabs panel-nav"
          role={home ? 'tablist' : undefined}
          aria-label={t('workspace.nav.label')}
          onKeyDown={keys}
        >
          {destinations.map(([key, Icon]) => (
            <button
              key={key}
              id={'tab-' + key}
              type="button"
              role={home ? 'tab' : undefined}
              aria-selected={home ? key === active : undefined}
              aria-current={!home && key === active ? 'page' : undefined}
              disabled={
                busy ||
                hostBusy ||
                (!home && key === 'codex' && navigation?.canChat === false && view !== 'chat')
              }
              tabIndex={home && key !== active ? -1 : 0}
              aria-controls={home ? 'panel-content' : undefined}
              onClick={() => go(key)}
            >
              <Icon size={16} strokeWidth={1.7} aria-hidden="true" />
              {t('workspace.nav.' + key)}
            </button>
          ))}
        </nav>
      )}
      <main
        id="panel-content"
        className={'workspace view-' + view}
        role={home ? 'tabpanel' : undefined}
        aria-labelledby={home ? 'tab-' + active : undefined}
      >
        {title && (
          <div className="intro">
            <h1>{title}</h1>
            {description && <p>{description}</p>}
          </div>
        )}
        {children}
      </main>
    </>
  );
}

export function Action({ variant = 'secondary', icon: Icon, children, className = '', ...props }) {
  return (
    <button
      type="button"
      {...props}
      className={['panel-action', variant, className].filter(Boolean).join(' ')}
    >
      {Icon && <Icon size={16} strokeWidth={1.7} aria-hidden="true" />}
      {children}
    </button>
  );
}
export function Section({ title, description, className = '', children, ...props }) {
  const heading = useId();
  return (
    <section
      aria-labelledby={title ? heading : undefined}
      {...props}
      className={'work-section ' + className}
    >
      {title && <h2 id={heading}>{title}</h2>}
      {description && <p>{description}</p>}
      {children}
    </section>
  );
}
export function Notice({ state = 'ready', title, body, children, className = '', ...props }) {
  const Icon = { busy: LoaderCircle, success: CircleCheck, error: CircleAlert }[state] || Info;
  return (
    <section
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-state={state}
      {...props}
      className={'status panel-status ' + className}
    >
      {title && (
        <div className="status-title">
          <Icon size={16} aria-hidden="true" />
          {title}
        </div>
      )}
      {body && <p className="status-body">{body}</p>}
      {children}
    </section>
  );
}
export function Disclosure({ title, children, className = '', ...props }) {
  return (
    <details className={'details ' + className} {...props}>
      <summary>
        <ChevronRight size={14} aria-hidden="true" />
        {title}
      </summary>
      {children}
    </details>
  );
}
export function PreviewStrip({ items = [], className = '', ...props }) {
  const safe = items.filter(
    (item) =>
      typeof item.src === 'string' &&
      item.src.startsWith('data:image/png;base64,') &&
      item.src.length <= 600000,
  );
  if (!safe.length) return null;
  return (
    <div className={'preview-strip ' + className} {...props}>
      {safe.map((item, n) => (
        <figure key={n}>
          <img src={item.src} alt={item.alt ?? item.title} />
          <figcaption>{item.caption ?? item.title}</figcaption>
        </figure>
      ))}
    </div>
  );
}
