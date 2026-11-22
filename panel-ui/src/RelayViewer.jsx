import React, { useEffect, useState } from 'react';
import { Circle, FileText, Layers3, Radio } from 'lucide-react';
import './styles/relay.css';

const emptyState = { status: 'offline', file: null, page: null, selection: [], selectionTotal: 0, selectionTruncated: false, profile: null, lastOkAt: null, lastResult: null, error: '' };
const text = (value) => typeof value === 'string' && value.trim() ? value : '';

export default function RelayViewer({ model, locale, t, send }) {
  const [state, setState] = useState(emptyState);

  useEffect(() => {
    let active = true;
    let timer = null;
    let workspaceSession = null;
    let fileKey = '';
    const requestId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    const receive = (event) => {
      const message = event.data?.pluginMessage;
      if (!message || typeof message !== 'object' || message.type !== 'workspace-relay-viewer-state' || message.requestId !== requestId) return;
      const next = message;
      if (!['offline', 'live', 'busy', 'uncertain'].includes(next.status)) return;
      if (!/^[A-Za-z0-9_-]{1,160}$/.test(message.workspaceSession || '') ||
          (workspaceSession && message.workspaceSession !== workspaceSession)) return;
      if (!next.file || typeof next.file !== 'object' || (next.file.key !== null && typeof next.file.key !== 'string') ||
          !next.page || typeof next.page !== 'object' || (next.page.id !== null && typeof next.page.id !== 'string')) return;
      workspaceSession = message.workspaceSession;
      fileKey = text(next.file.key);
      if (workspaceSession && timer === null) timer = window.setInterval(() => {
        send({ type: 'workspace-control-tick', workspaceSession, fileKey });
      }, 1000);
      if (active) setState({
        status: next.status,
        file: next.file,
        page: next.page,
        selection: Array.isArray(next.selection) ? next.selection.slice(0, 20) : [],
        selectionTotal: Number.isInteger(next.selectionTotal) && next.selectionTotal >= 0 ? next.selectionTotal : (Array.isArray(next.selection) ? next.selection.length : 0),
        selectionTruncated: next.selectionTruncated === true,
        profile: next.profile && typeof next.profile === 'object' ? next.profile : null,
        lastOkAt: text(next.lastOkAt),
        lastResult: ['ok', 'error', 'uncertain'].includes(next.lastResult) ? next.lastResult : null,
        error: text(next.error),
      });
    };
    window.addEventListener('message', receive);
    send({ type: 'workspace-home-ready', locale, requestId });
    return () => { active = false; if (timer !== null) window.clearInterval(timer); window.removeEventListener('message', receive); };
  }, [model.fileKey, locale, send]);

  const statusKey = state.status === 'busy' ? 'running' : state.status === 'live' ? 'connected' : state.status;
  const selected = state.selection;
  const selectionLabel = selected.length
    ? selected.map((item) => text(item?.name) || text(item?.type) || t('relay.selection.unnamed')).join(', ')
    : t('relay.selection.none');
  const displayedSelection = state.selectionTruncated
    ? t('relay.selection.truncated', { shown: selected.length, total: state.selectionTotal })
    : selectionLabel;
  return (
    <main className="relay-view" lang={locale}>
      <section className="relay-card" aria-label={t('relay.title')}>
        <header className="relay-header">
          <span className="relay-brand-mark" aria-hidden="true"><Layers3 size={16} /></span>
          <strong>{t('relay.title')}</strong>
          <span className="relay-status" data-state={state.status} role="status">
            <Circle size={8} fill="currentColor" aria-hidden="true" />{t(`relay.status.${statusKey}`)}
          </span>
        </header>
        <div className="relay-content">
          <h1>{t(`relay.headline.${statusKey}`)}</h1>
          <p className="relay-caption">{t(`relay.caption.${statusKey}`)}</p>
          <div className="relay-context-row">
            <span><FileText size={14} aria-hidden="true" />{t('relay.file')}</span>
            <strong title={state.file?.name || ''}>{text(state.file?.name) || t('relay.unknown')}</strong>
          </div>
          <div className="relay-context-row">
            <span><Layers3 size={14} aria-hidden="true" />{t('relay.page')}</span>
            <strong title={state.page?.name || ''}>{text(state.page?.name) || t('relay.unknown')}</strong>
          </div>
          <div className="relay-context-row relay-selection">
            <span><Radio size={14} aria-hidden="true" />{t('relay.selection.title')}</span>
            <strong title={selectionLabel}>{displayedSelection}</strong>
          </div>
        </div>
        <footer className="relay-footer">
          <details>
            <summary>{t('relay.disclosure')}</summary>
            <div className="relay-details">
              {state.profile && <p>{t('relay.profile', { plan: text(state.profile.declared?.plan) || t('relay.unknown'), seat: text(state.profile.declared?.seat) || t('relay.unknown') })}</p>}
              {state.profile?.needsSetup && <p>{t('relay.profileNeedsSetup')}</p>}
              {state.profile && <p>{t(`relay.storage.${state.profile.storage === 'local' ? 'local' : 'session'}`)}</p>}
              {state.lastOkAt && <p>{t('relay.lastResult', { time: state.lastOkAt })}</p>}
              {state.lastResult && <p role={state.lastResult === 'error' ? 'alert' : undefined}>{t(`relay.result.${state.lastResult}`)}{state.lastResult === 'error' && state.error ? ` · ${state.error}` : ''}</p>}
              {state.error && state.lastResult !== 'error' && <p role="alert">{state.error}</p>}
              {!state.profile && !state.lastOkAt && !state.lastResult && !state.error && <p>{t('relay.noDetails')}</p>}
            </div>
          </details>
          <span>{t('relay.codexNote')}</span>
        </footer>
      </section>
    </main>
  );
}
