import React, { useEffect, useRef, useState } from 'react';
import { Download, Eye, RefreshCw, Check, X } from 'lucide-react';
import { Action, Notice, Section, Disclosure, PreviewStrip } from './components.jsx';
import { graphSelection } from './graphSelection.mjs';

function parsed(value) {
  try {
    return JSON.parse(value);
  } catch (_) {
    return value;
  }
}
function colorValue(value) {
  if (typeof value === 'string' && /^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(value)) return value;
  if (
    value &&
    typeof value === 'object' &&
    ['r', 'g', 'b'].every((k) => Number.isFinite(value[k]) && value[k] >= 0 && value[k] <= 1)
  ) {
    return `rgba(${['r', 'g', 'b'].map((k) => Math.round(value[k] * 255)).join(',')},${Number.isFinite(value.a) ? Math.max(0, Math.min(1, value.a)) : 1})`;
  }
  return null;
}
function TokenValue({ name, side, raw, t }) {
  const value = parsed(raw),
    color = colorValue(value);
  const numeric = typeof value === 'number' && Number.isFinite(value) && value >= 0;
  const spacing = numeric && /space|padding|gap/i.test(name);
  const typography = numeric && value > 0 && /font|type|size/i.test(name) && !spacing;
  return (
    <div className="value-cell">
      <span className="value-label">{t(`graph.${side}`)}</span>
      {color && (
        <span
          className="swatch"
          role="img"
          aria-label={`${t(`graph.${side}`)}: ${raw}`}
          style={{ '--token-color': color }}
        />
      )}
      {typography && (
        <span
          className="type-sample"
          aria-hidden="true"
          style={{ '--token-font-size': Math.min(48, value) + 'px' }}
        >
          Aa
        </span>
      )}
      {spacing && (
        <span
          className="measure"
          role="img"
          aria-label={t('graph.scale')}
          style={{ '--token-space': Math.min(96, value) + 'px' }}
        />
      )}
      <code className="graph-value-code">{raw}</code>
    </div>
  );
}
function saveEvidence(evidence, discovery) {
  if (!evidence) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(evidence, null, 2)], { type: 'application/json' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = discovery ? 'graph-native-discovery.json' : 'graph-token-readback.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function GraphPanel({ model, locale, t, send, Shell }) {
  const discovery = model.mode === 'discovery';
  const [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false);
  const [evidence, setEvidence] = useState(null),
    [result, setResult] = useState(null),
    [notice, setNotice] = useState(null),
    [chosen, setChosen] = useState(null);
  const busyRef = useRef(false),
    operation = useRef(null),
    statusRef = useRef(null),
    applyRef = useRef(null),
    reviewRef = useRef(null);
  useEffect(() => {
    const receive = (event) => {
      const message = event.data?.pluginMessage;
      if (!message || typeof message !== 'object' || message.session !== model.session) return;
      if (message.state === 'busy') {
        busyRef.current = true;
        setBusy(true);
        return;
      }
      if (!message.readback && !message.error) return;
      busyRef.current = false;
      setBusy(false);
      const actual = message.readback,
        failure = message.error || actual?.error || (actual?.status ? `status: ${actual.status}` : null);
      const conflicts = actual?.rollback_conflicts || message.rollback_conflicts || [];
      const op = message.operation || operation.current;
      setResult({
        operation: op,
        status: actual?.status || (failure ? 'error' : 'success'),
        error: failure,
        rollback_conflicts: conflicts,
        file_key: actual?.file_key || actual?.fileKey,
        page_id: actual?.page_id || actual?.pageId,
        hasReadback: !!actual,
      });
      if (actual) {
        setEvidence(actual);
        saveEvidence(actual, discovery);
      }
      if (failure)
        setNotice({
          state: 'error',
          title: conflicts.length
            ? 'conflict'
            : actual?.status === 'rolled-back'
              ? 'rolledBack'
              : 'failed',
          body: conflicts.length ? 'conflictHelp' : 'failedHelp',
          params: { count: conflicts.length },
        });
      else if (discovery)
        setNotice({
          state: 'success',
          title: 'readDone',
          body: 'readCounts',
          params: { nodes: actual?.nodes?.length || 0, variables: actual?.variables?.length || 0 },
        });
      else
        setNotice({
          state: 'success',
          title: op === 'apply' ? 'applied' : 'readDone',
          body: actual?.migration_pending ? 'pending' : op === 'apply' ? 'appliedHelp' : 'readSaved',
        });
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [model.session, discovery]);
  useEffect(() => {
    if (confirm) applyRef.current?.focus();
  }, [confirm]);
  useEffect(() => {
    if (result) statusRef.current?.focus();
  }, [result]);
  const cancel = () => {
    if (busyRef.current) return;
    setConfirm(false);
    reviewRef.current?.focus();
  };
  useEffect(() => {
    const escape = (event) => {
      if (event.key === 'Escape' && confirm && !busyRef.current) {
        event.preventDefault();
        cancel();
      }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [confirm]);
  const selection = graphSelection(model.changes, chosen);
  const applyBlocked = Array.isArray(model.changes) && model.changes.length > 0 && selection.count === 0;
  function start(type) {
    if (busyRef.current || (type === 'apply' && (discovery || !confirm || applyBlocked))) return;
    busyRef.current = true;
    setBusy(true);
    operation.current = type;
    setConfirm(false);
    setNotice({ state: 'busy', title: type === 'apply' ? 'busyApply' : 'busyRead', body: 'busyHelp' });
    send({ type, session: model.session });
  }
  const field = (name) => {
    const label = t('graph.field.' + name);
    return label === 'graph.field.' + name ? name : label;
  };
  const scope = [
    ['file', model.file_key],
    ['page', model.page_id],
    ['allowed', (model.pages || []).join(', ')],
    ...(model.collection_id ? [['collection', model.collection_id]] : []),
    ...(model.graph_sha256 ? [['hash', model.graph_sha256]] : []),
    ...(!discovery
      ? [
          ['mains', (model.main_ids || []).join(', ')],
          ['instances', (model.instance_ids || []).join(', ')],
        ]
      : []),
  ];
  return (
    <Shell
      view="graph"
      title={t(discovery ? 'graph.readTitle' : 'graph.title')}
      description={t(discovery ? 'graph.readDescription' : 'graph.description')}
      busy={busy}
    >
      <Section title={t('graph.scope')}>
        <p>
          {t('graph.pages', { count: model.pages?.length || 0 })}
          {discovery ? ' · ' + t('graph.readOnly') : ''}
        </p>
        {!discovery && (
          <div className="graph-stats">
            {['tokens', 'mains', 'instances'].map((key) => (
              <div key={key}>
                <span>{t('graph.' + key)}</span>
                <strong className="graph-stat-value">{model.stats?.[key] || 0}</strong>
              </div>
            ))}
          </div>
        )}
        <Disclosure title={t('graph.scopeDetails')}>
          <dl className="metadata">
            {scope.map(([key, value]) => (
              <React.Fragment key={key}>
                <dt>{t('graph.' + key)}</dt>
                <dd className="graph-scope-value">{value}</dd>
              </React.Fragment>
            ))}
          </dl>
        </Disclosure>
      </Section>
      <Section title={t('graph.action')} description={t('graph.readOnly')}>
        <div className="actions">
          <Action
            variant={discovery ? 'primary' : 'secondary'}
            icon={Eye}
            disabled={busy}
            onClick={() => start('read')}
          >
            {t('graph.read')}
          </Action>
          {!discovery && (
            <Action
              ref={reviewRef}
              variant="primary"
              icon={RefreshCw}
              disabled={busy}
              aria-expanded={confirm}
              aria-controls="graph-confirmation"
              onClick={() => {
                if (!busyRef.current) setConfirm(true);
              }}
            >
              {t('graph.review')}
            </Action>
          )}
        </div>
        {confirm && (
          <section
            id="graph-confirmation"
            className="graph-confirmation"
            aria-labelledby="graph-confirm-title"
          >
            <h2 id="graph-confirm-title">{t('graph.confirmTitle')}</h2>
            <p>{t('graph.impact', model.stats)}</p>
            <p className="graph-selection-count">{t('graph.selectionCount', { count: selection.count })}</p>
            <button type="button" onClick={() => setChosen(null)}>{t('graph.selectAll')}</button>
            <ul className="graph-component-list">
              {(model.components || []).map((component) => (
                <li key={component.id}>
                  <strong>{component.id}</strong>: {component.fields.map(field).join(', ')} ·{' '}
                  {t('graph.component', component)}
                </li>
              ))}
            </ul>
            {(model.changes || []).map((change, index) => (
              <article className="change-card" key={`${change.name}-${index}`}>
                <h3 className="graph-token-name">{change.name}</h3>
                <div className="value-pair">
                  {['before', 'after'].map((side) => (
                    <TokenValue key={side} name={change.name} side={side} raw={change[side]} t={t} />
                  ))}
                </div>
                <label className="graph-selection-row">
                  <input
                    type="checkbox"
                    checked={selection.rows[index].selected}
                    onChange={() => {
                      const current = new Set(selection.rows.filter((row) => row.selected).map((row) => row.identity));
                      if (current.has(selection.rows[index].identity)) current.delete(selection.rows[index].identity);
                      else current.add(selection.rows[index].identity);
                      setChosen([...current]);
                    }}
                  />
                  <span className="graph-selection-targets">{selection.rows[index].targets.join(', ')}</span>
                </label>
              </article>
            ))}
            <p>{t('graph.confirmHelp')}</p>
            <div className="actions">
              <Action
                ref={applyRef}
                variant="primary"
                icon={Check}
                disabled={busy || applyBlocked}
                onClick={() => start('apply')}
              >
                {t('graph.apply')}
              </Action>
              <Action variant="secondary" icon={X} disabled={busy} onClick={cancel}>
                {t('graph.cancel')}
              </Action>
            </div>
          </section>
        )}
      </Section>
      {notice && (
        <div ref={statusRef} tabIndex={-1} aria-busy={busy}>
          <Notice
            state={notice.state}
            title={t('graph.' + notice.title, notice.params)}
            body={t('graph.' + notice.body, notice.params)}
          />
        </div>
      )}
      {result && (
        <Section
          title={t('graph.evidence')}
          description={t(result.hasReadback ? 'graph.evidenceCurrent' : 'graph.evidencePrevious')}
        >
          <Action
            variant="secondary"
            icon={Download}
            disabled={!evidence}
            onClick={() => saveEvidence(evidence, discovery)}
          >
            {t('graph.downloadAgain')}
          </Action>
          <Disclosure title={t('graph.history')}>
            <pre className="graph-diagnostics">{JSON.stringify(result, null, 2)}</pre>
          </Disclosure>
        </Section>
      )}
    </Shell>
  );
}
