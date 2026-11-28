import React from 'react';
import { useRelaySnapshot } from './useRelaySnapshot.js';
import RelaySelection from './RelaySelection.jsx';
import { Circle, FileText, Layers3, Radio } from 'lucide-react';
import './styles/relay.css';
import { panelDesignMetrics } from './panelContracts.mjs';

const text = (value) => typeof value === 'string' && value.trim() ? value : '';
const diagReasons = new Set(['missing-control-config', 'server-unreachable', 'stale-runtime', 'file-key-unavailable']);

export default function RelayViewer({ locale, t, send }) {
  const state = useRelaySnapshot(send);

  const statusKey = state.status === 'busy' ? 'running' : state.status === 'live' ? 'connected' : state.status;
  const diag = state.diagnostics;
  const diagReason = diag && diagReasons.has(diag.reason) ? diag.reason : null;
  const captionText = diagReason
    ? t(`relay.diag.${diagReason}`, diagReason === 'server-unreachable' ? { port: text(diag.port) || t('relay.unknown') } : undefined)
    : t(`relay.caption.${statusKey}`);
  const hasDiagMeta = Boolean(diag && (text(diag.pluginId) || text(diag.port) || text(diag.generation)));
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
          <span className="relay-brand-mark" aria-hidden="true"><Layers3 size={panelDesignMetrics.iconStandard} /></span>
          <strong>{t('relay.title')}</strong>
          <span className="relay-status" data-state={state.status} role="status">
            <Circle size={panelDesignMetrics.iconTiny} fill="currentColor" aria-hidden="true" />{t(`relay.status.${statusKey}`)}
          </span>
        </header>
        <div className="relay-content">
          <h1>{t(`relay.headline.${statusKey}`)}</h1>
          <p className="relay-caption">{captionText}</p>
          <div className="relay-context-row">
            <span><FileText size={panelDesignMetrics.iconMedium} aria-hidden="true" />{t('relay.file')}</span>
            <strong title={state.file?.name || ''}>{text(state.file?.name) || t('relay.unknown')}</strong>
          </div>
          <div className="relay-context-row">
            <span><Layers3 size={panelDesignMetrics.iconMedium} aria-hidden="true" />{t('relay.page')}</span>
            <strong title={state.page?.name || ''}>{text(state.page?.name) || t('relay.unknown')}</strong>
          </div>
          <div className="relay-context-row relay-selection">
            <span><Radio size={panelDesignMetrics.iconMedium} aria-hidden="true" />{t('relay.selection.title')}</span>
            <strong title={selectionLabel}>{displayedSelection}</strong>
          </div>
        </div>
        <footer className="relay-footer">
          <details>
            <summary>{t('relay.disclosure')}</summary>
            <div className="relay-details">
              {selected.length > 0 && <RelaySelection selection={selected} t={t} />}
              {state.profile && <p>{t('relay.profile', { plan: text(state.profile.declared?.plan) || t('relay.unknown'), seat: text(state.profile.declared?.seat) || t('relay.unknown') })}</p>}
              {state.profile?.needsSetup && <p>{t('relay.profileNeedsSetup')}</p>}
              {state.profile && <p>{t(`relay.storage.${state.profile.storage === 'local' ? 'local' : 'session'}`)}</p>}
              {state.lastOkAt && <p>{t('relay.lastResult', { time: state.lastOkAt })}</p>}
              {state.lastResult && <p role={state.lastResult === 'error' ? 'alert' : undefined}>{t(`relay.result.${state.lastResult}`)}{state.lastResult === 'error' && state.error ? ` · ${state.error}` : ''}</p>}
              {state.error && state.lastResult !== 'error' && <p role="alert">{state.error}</p>}
              {hasDiagMeta && <p>{t('relay.diag.meta', { pluginId: text(diag.pluginId) || t('relay.unknown'), port: text(diag.port) || t('relay.unknown'), generation: text(diag.generation) || t('relay.unknown') })}</p>}
              {!selected.length && !state.profile && !state.lastOkAt && !state.lastResult && !state.error && !hasDiagMeta && <p>{t('relay.noDetails')}</p>}
            </div>
          </details>
        </footer>
      </section>
    </main>
  );
}
