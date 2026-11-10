import React, { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Download, ExternalLink, FilePlus, Files, FolderOpen, RefreshCw, ScanText } from 'lucide-react';
import { Action, Notice, Section, Disclosure } from './components.jsx';

const initialState = {
  connected: false,
  paired: false,
  existingOnly: false,
  busy: false,
  fresh: false,
  operation: null,
  ready: null,
  data: null,
  diagnostics: '',
  preview: null,
  status: { kind: 'connecting', state: 'busy' },
};
const operations = new Set(['import', 'export', 'sync']);
const syncStatuses = new Set(['baseline', 'applied', 'unchanged']);
const previewAddress = /^http:\/\/localhost:\d+\/$/;

function reduce(state, action) {
  if (action.type === 'fresh') return { ...state, fresh: action.value };
  if (action.type === 'timeout')
    return state.connected ? state : { ...state, status: { kind: 'timeout', state: 'error' } };
  if (action.type === 'start')
    return {
      ...state,
      busy: true,
      operation: action.operation,
      diagnostics: '',
      preview: action.operation === 'sync' ? null : state.preview,
      status: { kind: 'progress', state: 'busy', operation: action.operation, fresh: state.fresh },
    };
  const message = action.message;
  if (message.type === 'status') {
    if (message.ready === true)
      return {
        ...state,
        connected: true,
        paired: message.paired === true,
        existingOnly: message.existing_only === true,
        ready: message,
        status: { kind: 'ready', state: 'ready' },
      };
    const failed = message.event === 'error' || message.message?.startsWith('Error:');
    const diagnostics =
      [message.details, ...(message.warnings || [])].filter(Boolean).join('\n') ||
      (failed ? message.message || '' : '');
    if (failed)
      return { ...state, diagnostics, preview: null, status: { kind: 'error', state: 'error' } };
    if (message.event === 'sync-wait' || (state.operation === 'sync' && state.busy))
      return {
        ...state,
        diagnostics,
        status: { kind: 'sync-wait', state: 'busy' },
      };
    return {
      ...state,
      diagnostics,
      status: {
        kind: 'complete',
        state: 'success',
        operation: state.operation,
        event: message.event,
        counts: message.counts,
        warnings: message.warnings?.length || 0,
      },
    };
  }
  if (message.type === 'busy') {
    const busy = message.value === true;
    const operation = operations.has(message.operation) ? message.operation : null;
    return {
      ...state,
      busy,
      operation: busy && operation ? operation : state.operation,
      preview: busy && operation === 'sync' ? null : state.preview,
      status:
        busy && operation
          ? { kind: 'progress', state: 'busy', operation, fresh: state.fresh }
          : state.status,
    };
  }
  if (message.type === 'sync-result') {
    const result = message.result;
    if (!result || !syncStatuses.has(result.status))
      return {
        ...state,
        diagnostics: JSON.stringify(result ?? null, null, 2),
        preview: null,
        status: { kind: 'invalid-result', state: 'error' },
      };
    return {
      ...state,
      preview: result.preview_error ? null : state.preview,
      diagnostics: result.preview_error || state.diagnostics,
      status: { kind: 'sync-result', state: result.preview_error ? 'error' : 'success', result },
    };
  }
  if (message.type === 'preview' && typeof message.url === 'string' && previewAddress.test(message.url))
    return { ...state, preview: message.url };
  if (message.type === 'readback' && message.data !== undefined)
    return {
      ...state,
      data: message.data,
      status: { kind: 'readback', state: 'success' },
    };
  return state;
}

function statusCopy(status, t) {
  if (status.kind === 'connecting') return [t('import.connectingTitle'), t('import.connectingBody')];
  if (status.kind === 'timeout') return [t('import.timeoutTitle'), t('import.invalidConnection')];
  if (status.kind === 'ready') return [t('import.ready'), ''];
  if (status.kind === 'error') return [t('import.errorTitle'), t('import.errorBody')];
  if (status.kind === 'invalid-result')
    return [t('import.invalidResultTitle'), t('import.invalidResultBody')];
  if (status.kind === 'readback') return [t('import.readComplete'), t('import.readSavedBody')];
  if (status.kind === 'sync-wait') return [t('import.progressSyncTitle'), t('import.syncWait')];
  if (status.kind === 'progress') {
    if (status.operation === 'export')
      return [t('import.progressReadTitle'), t('import.progressReadBody')];
    if (status.operation === 'sync')
      return [t('import.progressSyncTitle'), t('import.progressSyncBody')];
    return [
      t('import.progressImportTitle'),
      t(status.fresh ? 'import.progressFresh' : 'import.progressExisting'),
    ];
  }
  if (status.kind === 'complete') {
    const summary =
      status.event === 'imported'
        ? t('import.importSummary', status.counts)
        : status.event === 'read'
          ? t('import.readSummary', status.counts)
          : status.event === 'reused'
            ? t('import.reused')
            : '';
    const warnings = status.warnings ? t('import.warningCount', { count: status.warnings }) : '';
    return [
      t(status.operation === 'export' ? 'import.readComplete' : 'import.importComplete'),
      [summary, warnings].filter(Boolean).join('\n'),
    ];
  }
  const { result } = status;
  const items = (value) =>
    Array.isArray(value) ? value.join(', ') || t('import.none') : String(value ?? t('import.none'));
  const count = (value) => (Array.isArray(value) ? value.length : (value ?? 0));
  const body = [
    t('import.resultSummary', {
      tokens: count(result.changed_tokens),
      screens: count(result.screens),
      codes: count(result.code_ids),
    }),
    t('import.resultScreens', { value: items(result.screens) }),
    t('import.resultCode', { value: items(result.code_ids) }),
    t('import.resultFiles', { value: items(result.files) }),
    t('import.resultReport', { value: items(result.report) }),
  ];
  if (result.preview_error) body.push(t('import.previewError'));
  return [t(`import.${result.status}`), body.join('\n')];
}

export default function ImportPanel({ locale, t, send, Shell }) {
  const [state, dispatch] = useReducer(reduce, initialState);
  const [nonce] = useState(() =>
    Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join(''),
  );
  const busyRef = useRef(false);
  const connectedRef = useRef(false);
  const readySentRef = useRef(false);
  const readback = useMemo(
    () => (state.data === null ? '' : JSON.stringify(state.data, null, 2)),
    [state.data],
  );

  useEffect(() => {
    let timer;
    const receive = (event) => {
      const message = event.data?.pluginMessage;
      if (!message || message.session_nonce !== nonce) return;
      if (message.type === 'status' && message.ready === true) {
        connectedRef.current = true;
        clearTimeout(timer);
      }
      if (message.type === 'busy') busyRef.current = message.value === true;
      dispatch({ type: 'native', message });
    };
    window.addEventListener('message', receive);
    if (!connectedRef.current) timer = setTimeout(() => dispatch({ type: 'timeout' }), 5000);
    if (!readySentRef.current) {
      readySentRef.current = true;
      send({ type: 'ready', session_nonce: nonce });
    }
    return () => {
      clearTimeout(timer);
      window.removeEventListener('message', receive);
    };
  }, [nonce, send]);

  useEffect(() => {
    document.title = t(state.existingOnly ? 'import.syncDocumentTitle' : 'import.documentTitle');
  }, [locale, state.existingOnly, t]);

  const run = (operation) => {
    if (
      !state.connected ||
      state.busy ||
      busyRef.current ||
      (operation === 'import' && state.existingOnly) ||
      (operation === 'sync' && !state.paired)
    )
      return;
    busyRef.current = true;
    dispatch({ type: 'start', operation });
    send({ type: operation, fresh: state.fresh, session_nonce: nonce });
  };
  const download = () => {
    if (!readback || state.busy || busyRef.current) return;
    const url = URL.createObjectURL(new Blob([readback], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'figma-flow-readback.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const names = Array.isArray(state.ready?.source_names) ? state.ready.source_names : [];
  const total = Number.isInteger(state.ready?.source_count) ? state.ready.source_count : names.length;
  const nameSummary = names.length
    ? total > names.length
      ? t('import.sourceMore', { names: names.join(' · '), count: total - names.length })
      : names.join(' · ')
    : Array.isArray(state.ready?.source_names)
      ? t('import.screenCount', { count: total })
      : state.ready?.source_label || '';
  const context = [
    nameSummary && (!names.length || state.existingOnly)
      ? t('import.source', { name: nameSummary })
      : '',
    state.ready?.target_page_name
      ? t(state.paired ? 'import.pairedPage' : 'import.currentPage', {
          name: state.ready.target_page_name,
        })
      : '',
  ]
    .filter(Boolean)
    .join('\n');
  const summary = [t('import.recentReadback')];
  if (Array.isArray(state.data?.pages))
    summary.push(t('import.pageCount', { count: state.data.pages.length }));
  if (Array.isArray(state.data?.variables))
    summary.push(t('import.variableCount', { count: state.data.variables.length }));
  const [statusTitle, statusBody] = statusCopy(state.status, t);
  const savePrimary = Boolean(readback) && state.operation === 'export';
  const unavailable = !state.connected || state.busy;

  return (
    <Shell view="import" busy={state.busy}>
      <section className="intro">
        <h1 id="heading">{t(state.existingOnly ? 'import.syncTitle' : 'import.title')}</h1>
        <p id="source-meta" className="metadata">
          {state.ready ? context : t('import.sourceWaiting')}
        </p>
      </section>

      {!state.existingOnly && names.length > 0 && (
        <figure id="import-preview" className="import-preview">
          <Files className="mini-pages" size={36} strokeWidth={1.5} aria-hidden="true" />
          <figcaption>
            <strong id="preview-source-count">{t('import.previewSource', { count: total })}</strong>
            <ul id="preview-source-names" aria-label={t('import.previewNames')}>
              {names.map((name, index) => (
                <li key={`${index}:${name}`}>{name}</li>
              ))}
              {total > names.length && (
                <li>{t('import.previewMore', { count: total - names.length })}</li>
              )}
            </ul>
            <p id="preview-source-mode">
              {t(state.fresh ? 'import.previewFresh' : 'import.previewReuse')}
            </p>
          </figcaption>
        </figure>
      )}

      <Notice id="status-region" state={state.status.state} title={statusTitle} body={statusBody} />
      {state.diagnostics && (
        <Disclosure id="diagnostics" title={t('import.diagnostics')}>
          <pre id="diagnostic-text" tabIndex={0} aria-label={t('import.diagnosticLabel')}>
            {state.diagnostics}
          </pre>
        </Disclosure>
      )}

      {!state.existingOnly && (
        <Section
          id="import-section"
          title={t('import.importHeading')}
          description={t('import.importHelp')}
        >
          <div className="import-options">
            <label htmlFor="fresh">
              <input
                id="fresh"
                type="checkbox"
                checked={state.fresh}
                disabled={unavailable}
                aria-describedby="fresh-help"
                onChange={(event) => dispatch({ type: 'fresh', value: event.target.checked })}
              />
              <span>
                <span className="option-title">{t('import.freshLabel')}</span>
                <span id="fresh-help" className="option-help">
                  {t('import.freshHelp')}
                </span>
              </span>
            </label>
          </div>
          <div className="actions">
            <Action
              id="import"
              variant={savePrimary ? 'secondary' : 'primary'}
              icon={state.fresh ? FilePlus : FolderOpen}
              disabled={unavailable}
              onClick={() => run('import')}
            >
              {t(state.fresh ? 'import.freshButton' : 'import.importButton')}
            </Action>
          </div>
        </Section>
      )}

      {state.paired && (
        <Section id="sync-section" title={t('import.syncHeading')} description={t('import.syncHelp')}>
          <div className="actions">
            <Action
              id="sync"
              variant={state.existingOnly && !savePrimary ? 'primary' : 'secondary'}
              icon={RefreshCw}
              disabled={unavailable}
              onClick={() => run('sync')}
            >
              {t('import.syncButton')}
            </Action>
          </div>
        </Section>
      )}

      <Section title={t('import.readHeading')} description={t('import.readHelp')}>
        <div className="actions">
          <Action
            id="export"
            variant="secondary"
            icon={ScanText}
            disabled={unavailable}
            onClick={() => run('export')}
          >
            {t('import.readButton')}
          </Action>
        </div>
        {readback && (
          <div id="readback-result">
            <p id="readback-meta" className="metadata">
              {summary.join(' · ')}
            </p>
            <div className="actions readback-actions">
              <Action
                id="save"
                variant={savePrimary ? 'primary' : 'secondary'}
                icon={Download}
                disabled={state.busy}
                onClick={download}
              >
                {t('import.saveButton')}
              </Action>
            </div>
            <Disclosure id="readback-details" title={t('import.jsonDetails')}>
              <textarea
                id="json"
                className="panel-input panel-code"
                readOnly
                aria-label={t('import.jsonLabel')}
                placeholder={t('import.jsonPlaceholder')}
                value={readback}
              />
            </Disclosure>
          </div>
        )}
      </Section>

      {state.preview && (
        <Section id="preview" className="preview-section" title={t('import.previewHeading')}>
          <a id="preview-link" href={state.preview} target="_blank" rel="noopener noreferrer">
            {t('import.previewLink')} <ExternalLink size={14} aria-hidden="true" />
          </a>
          <iframe
            id="preview-frame"
            className="panel-preview"
            src={state.preview}
            title={t('import.previewFrame')}
            referrerPolicy="no-referrer"
          />
        </Section>
      )}
    </Shell>
  );
}
