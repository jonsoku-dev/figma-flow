import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleCheck,
  Clock3,
  FileText,
  Minus,
  Plus,
  RefreshCw,
  ScanSearch,
  TriangleAlert,
} from 'lucide-react';
import { Action, Section, Notice, PreviewStrip } from './components.jsx';
import { workspaceActivity } from './WorkspaceActivity.mjs';
import { ActivitySummary, CarouselOverview, ExecutionFlows } from './WorkspaceActivity.jsx';
import { dependencyFreshness, dependencyView } from './dependencyView.mjs';
import { verifiedPresentationLink } from './carouselPresentation.mjs';
import { assetInventory } from './assetInventory.mjs';
import {
  DETAIL_PROTOCOL,
  OPERATION_DETAIL_SCHEMA,
  buildDetailScope,
  isDetailResponseStale,
  normalizeDetailDto,
  normalizeDetailResult,
  safeOperationId,
  scopesMatch,
} from './operationDetail.mjs';

const locales = new Set(__FLOW_LOCALES__);
const terminal = new Set(['finished', 'readback', 'verified', 'baseline']);
const historyOf = (model) => (Array.isArray(model.history) ? model.history : []);
const tasksOf = (model) => (Array.isArray(model.tasks) ? model.tasks : []);
const latestFor = (model, task) =>
  [...historyOf(model)]
    .reverse()
    .find(
      (event) =>
        event.taskKey === task.key && event.revision === task.revision && event.operation !== 'download',
    );
const phase = (task) =>
  task.kind === 'sync' || (task.kind === 'import' && task.paired) ? 3 : task.kind === 'import' ? 2 : 1;
const progressed = (model, task) =>
  task.kind !== 'review' &&
  (task.productionAdmitted || task.paired) &&
  historyOf(model).some(
    (event) =>
      event.taskKey === task.key &&
      event.revision === task.revision &&
      terminal.has(event.status) &&
      !event.operation.startsWith('chat:'),
  );

export function selectRecommendation(model, tasks) {
  const available = tasks.filter((task) => !task.fileKey || task.fileKey === model.fileKey);
  const admitted = available.filter((task) => task.productionAdmitted);
  const continued = available.filter(
    (task) =>
      (task.kind === 'sync' || task.kind === 'import') &&
      task.paired &&
      tasksOf(model).some(
        (previous) => previous.project === task.project && progressed(model, previous),
      ),
  );
  let candidates =
    admitted.length || continued.length
      ? available.filter((task) => admitted.includes(task) || continued.includes(task))
      : available;
  if (admitted.length || continued.length)
    candidates = candidates.filter(
      (task) =>
        phase(task) >=
        Math.max(
          0,
          ...candidates
            .filter((previous) => previous.project === task.project && progressed(model, previous))
            .map(phase),
        ),
    );
  const failed = candidates.find((task) => latestFor(model, task)?.status === 'failed');
  if (failed) return { task: failed, inspect: false };
  const pending = candidates.find((task) => !latestFor(model, task));
  if (pending) return { task: pending, inspect: false };
  const actual = [...historyOf(model)]
    .reverse()
    .find((event) =>
      candidates.some(
        (task) =>
          task.key === event.taskKey &&
          task.revision === event.revision &&
          event.operation !== 'download',
      ),
    );
  const task = candidates.find((task) => task.key === actual?.taskKey) || candidates[0];
  return task ? { task, inspect: true } : null;
}

export function workspacePreviews(task) {
  return (Array.isArray(task?.preview) ? task.preview : [])
    .filter(
      (item) =>
        item &&
        typeof item.title === 'string' &&
        typeof item.src === 'string' &&
        item.src.length <= 600000 &&
        /^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/=]+$/.test(item.src),
    )
    .slice(0, 2);
}

function AssetDisclosure({ summary, freshness, tr }) {
  const [status, setStatus] = React.useState('');
  const [kind, setKind] = React.useState('');
  const [query, setQuery] = React.useState('');
  const inventory = assetInventory(summary, { status, kind, query });
  const states = ['present', '404', 'rejected', 'external-unverified'];
  const current = ['current', 'stale'].includes(freshness?.status) ? freshness.status : 'unverified';
  return (
    <details className="workspace-asset-list">
      <summary>
        {tr('assetTitle')} · {tr('assetProblems', {count: inventory.problems})}
      </summary>
      <p role="status" data-state={current}>{tr('assetFreshness.' + current)}</p>
      {current === 'stale' && <p>{(freshness.changed || []).join(', ')}</p>}
      <label>{tr('assetSearch')}<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <label>{tr('assetKind')}<select value={kind} onChange={event => setKind(event.target.value)}>
        <option value="">{tr('assetAllKinds')}</option>
        {Object.keys(inventory.counts).map(value => <option key={value} value={value}>{tr('assetKind.' + value)} · {inventory.counts[value]}</option>)}
      </select></label>
      <label>
        {tr('assetStatus')}
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">{tr('assetAllStatuses')}</option>
          {states.map((item) => (
            <option key={item} value={item}>
              {tr('assetStatus.' + item)}
            </option>
          ))}
        </select>
      </label>
      {inventory.empty && <p>{tr('assetEmpty')}</p>}
      {!inventory.empty && !inventory.rows.length && <p>{tr('assetNoMatches')}</p>}
      <ul>
        {inventory.rows.map((row) => (
          <li key={row.ref + row.status}>
            {row.ref} · {tr('assetKind.' + row.kind)} · {tr('assetStatus.' + row.status)} · {row.source}
          </li>
        ))}
      </ul>
    </details>
  );
}

function DependencyText({ tasks, selected, retired, onSelect, tr }) {
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus(); }, [selected]);
  const view = dependencyView(tasks, selected);
  const freshness = dependencyFreshness(tasks, Array.isArray(retired) ? retired : []);
  const related = freshness.labels.filter((label) => label.task_key === selected || label.dependency === selected);
  const missing = related.filter(row => row.task_key === selected && !tasks.some(task => task.key === row.dependency))
    .map(row => ({role:'predecessor', key:row.dependency, title:row.dependency, unavailable:true}));
  const rows = [...new Map([...view.predecessors, ...missing, ...view.successors].map(row => [row.role + ':' + row.key, row])).values()];
  const before = rows.filter(row => row.role === 'predecessor'), after = rows.filter(row => row.role === 'successor');
  const height = Math.max(112, Math.max(before.length, after.length) * 52 + 20);
  const title = key => tasks.find(task => task.key === key)?.title || key;
  const label = value => value.length > 14 ? value.slice(0, 13) + '…' : value;
  const marker = React.useId().replace(/:/g, '');
  return (
    <div className="workspace-dependency-view">
      <h3 tabIndex={-1} ref={heading}>{tr('dependencySelected', {title:title(selected)})}</h3>
      <svg className="workspace-dependency-graph" aria-hidden="true" viewBox={`0 0 600 ${height}`}>
        <defs><marker id={marker} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
        {[before, after].map((items, side) => items.map((item, index) => <g key={item.role + item.key}>
          <line x1={side ? 380 : 180} y1={side ? height / 2 : 30 + index * 52} x2={side ? 420 : 220} y2={side ? 30 + index * 52 : height / 2} markerEnd={`url(#${marker})`} />
          <rect x={side ? 420 : 0} y={10 + index * 52} width="180" height="40" rx="6" />
          <text x={side ? 510 : 90} y={34 + index * 52} textAnchor="middle">{label(item.title)}</text>
        </g>))}
        <rect className="selected" x="220" y={height / 2 - 20} width="160" height="40" rx="6" />
        <text x="300" y={height / 2 + 4} textAnchor="middle">{label(title(selected))}</text>
      </svg>
      <details><summary>{tr('dependencyEvidence')}</summary><ol className="workspace-dependency-text">
        {view.text.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ol></details>
      <ul className="workspace-dependency-state">
        {related.map((label, index) => (
          <li key={label.task_key + label.dependency + index} data-state={label.state}>
            {title(label.dependency)} → {title(label.task_key)} · {tr('dependencyState.' + label.state)}
          </li>
        ))}
      </ul>
      {rows.map((item) => (
        <button type="button" key={item.role + item.key} disabled={item.unavailable} onClick={() => onSelect(item.key)}>
          {tr('dependencyRole.' + item.role)} · {item.title}
        </button>
      ))}
    </div>
  );
}

function EventIcon({ status, ...props }) {
  const Icon =
    status === 'failed'
      ? TriangleAlert
      : status === 'verified'
        ? CircleCheck
        : status === 'finished'
          ? Check
          : status === 'requested'
            ? Clock3
            : FileText;
  return <Icon size={16} strokeWidth={1.5} aria-hidden="true" {...props} />;
}

const KNOWN_JOURNAL_PHASES = new Set([
  'queued',
  'claimed',
  'native-started',
  'result-received',
  'reconciled',
  'uncertain',
  'unknown',
]);
const KNOWN_DIFF_REASONS = new Set([
  'before-artifact-missing',
  'read-only-operation',
  'unsupported-task-kind',
  'legacy-or-unpinned-artifact',
  'unverified-artifact',
  'legacy-record',
  'unknown-record',
  'unavailable',
]);
const KNOWN_UNAVAILABLE_REASONS = new Set(['not-found-in-scope', 'control-unavailable']);
const KNOWN_ERROR_REASONS = new Set([
  'invalid-operation-id',
  'invalid-task-revision-binding',
  'task-revision-mismatch',
  'runtime-mismatch',
  'request-rejected',
  'payload-limit-exceeded',
  'request-timeout',
]);
const KNOWN_FAILURE_CODES = new Set([
  'native-conflict',
  'result-rejected',
  'claim-expired',
  'operation-uncertain',
  'execution-failed',
]);
const KNOWN_FAILURE_ACTIONS = new Set([
  'inspect-conflicts',
  'run-native-read',
  'reopen-plugin',
  'inspect-private-status',
]);

function journalPhaseLabel(phase, tr) {
  return tr('journalPhase.' + (KNOWN_JOURNAL_PHASES.has(phase) ? phase : 'unknown'));
}

function diffReasonText(reason, tr) {
  if (KNOWN_DIFF_REASONS.has(reason)) return tr('journalDiffReason.' + reason);
  return reason ? tr('journalDetailErrorCode', { code: reason }) : tr('journalDiffReason.unavailable');
}

function diffKindSymbol(kind) {
  if (kind === 'added') return '+';
  if (kind === 'removed') return '−';
  if (kind === 'type-changed') return '⇄';
  if (kind === 'unknown') return '?';
  return '~';
}

function DiffKindIcon({ kind }) {
  const Icon =
    kind === 'added'
      ? Plus
      : kind === 'removed'
        ? Minus
        : kind === 'unknown'
          ? TriangleAlert
          : RefreshCw;
  return <Icon size={12} strokeWidth={1.75} aria-hidden="true" />;
}

function revisionBindingText(binding, currentRevision, tr) {
  if (binding === 'current') return tr('journalRevisionCurrent');
  if (binding === 'pinned-historical') return tr('journalRevisionPast');
  if (binding === 'retired') return tr('journalRevisionRetired');
  if (binding === 'orphan') return tr('journalRevisionOrphan');
  return currentRevision ? tr('journalRevisionUnknown') : tr('journalRevisionUnknown');
}

function relationBindingText(rel, tr) {
  if (rel.revisionBinding === 'current') return tr('journalRelationCurrentRev');
  if (rel.revisionBinding === 'pinned-historical') {
    return tr('journalRelationPinnedRev', { current: rel.currentRevision || '—' });
  }
  if (rel.revisionBinding === 'retired') return tr('journalRelationRetired');
  if (rel.revisionBinding === 'orphan') return tr('journalRelationOrphan');
  return tr('journalRelationUnknownRev');
}

function conflictCellText(cell, tr) {
  if (!cell) return '—';
  if (cell.isText) {
    return `${tr('journalTextLengthMeta')} (${cell.length ?? '—'})`;
  }
  return cell.text || '—';
}

function relationDirectionLabel(rel, tr) {
  if (rel.type === 'recovery-of' && (rel.direction === 'recovers' || rel.direction === 'recovered-by')) {
    return tr('journalRelation.recovery-of.' + rel.direction);
  }
  if (
    rel.type === 'declared-dependency' &&
    (rel.direction === 'predecessor' || rel.direction === 'successor')
  ) {
    return tr('journalRelation.declared-dependency.' + rel.direction);
  }
  return tr('journalRelationType.' + rel.type);
}

function OperationDetailPanel({
  detailState,
  tasks,
  tr,
  date,
  headingRef,
  onBack,
  onOpenRelated,
}) {
  const detail = detailState?.detail || null;
  const status = detailState?.status || 'loading';
  const taskKey = detail ? detail.task?.key || '' : detailState?.taskKey || '';
  const taskTitle = tasks.find((item) => item.key === taskKey)?.title || tr('removedTask');
  const relations = Array.isArray(detail?.relations) ? detail.relations : [];
  const inputRelations = relations.filter(
    (rel) =>
      rel.type === 'artifact-input' ||
      (rel.type === 'declared-dependency' && rel.direction === 'predecessor'),
  );
  const linkedRelations = relations.filter(
    (rel) => rel.type === 'recovery-of' || rel.type === 'declared-dependency',
  );
  const classificationKey =
    detail?.classification === 'recorded'
      ? 'journalRecorded'
      : detail?.classification === 'legacy'
        ? 'journalLegacy'
        : 'journalUnknown';

  return (
    <Section className="workspace-journal-detail" aria-live="polite">
      <div className="workspace-detail-header">
        <Action
          variant="quiet"
          icon={ArrowLeft}
          className="workspace-journal-back"
          onClick={onBack}
        >
          {tr('journalBack')}
        </Action>
        <h2 ref={headingRef} tabIndex={-1}>
          {tr('journalDetailTitle', { title: taskTitle })}
        </h2>
        <p className="workspace-boundary">{tr('journalDetailBoundary')}</p>
      </div>

      {status === 'loading' && (
        <Notice state="busy" title={tr('loading')} body={tr('journalDetailLoading')} />
      )}
      {status === 'scope-changed' && (
        <Notice
          state="error"
          title={tr('journalDetailError')}
          body={tr('journalDetailScopeChanged')}
        />
      )}
      {status === 'unavailable' && (
        <Notice
          state="ready"
          title={tr('journalDetailUnavailable')}
          body={
            KNOWN_UNAVAILABLE_REASONS.has(detailState?.reason)
              ? tr('journalUnavailableReason.' + detailState.reason)
              : tr('journalDetailErrorCode', { code: detailState?.reason || 'unavailable' })
          }
        />
      )}
      {status === 'error' && (
        <Notice
          state="error"
          title={tr('journalDetailError')}
          body={
            KNOWN_ERROR_REASONS.has(detailState?.reason)
              ? tr('journalErrorReason.' + detailState.reason)
              : tr('journalDetailErrorCode', { code: detailState?.reason || 'unknown' })
          }
        />
      )}

      {detail && status === 'ok' && (
        <>
          {detail.truncated && (
            <Notice
              state="ready"
              title={tr(
                detail.scopeNotice === 'read-only-truncated-256kib'
                  ? 'journalTruncated256KiB'
                  : 'journalDetailTruncated',
              )}
            />
          )}
          {detail.classification === 'legacy' && (
            <Notice state="ready" title={tr('journalLegacy')} body={tr('journalLegacyNotice')} />
          )}
          {detail.classification === 'unknown' && (
            <Notice state="error" title={tr('journalUnknown')} body={tr('journalUnknownNotice')} />
          )}
          {detail.failure && (
            <Notice
              state="error"
              title={tr('journalFailureTitle')}
              body={[
                KNOWN_FAILURE_CODES.has(detail.failure.code)
                  ? tr('journalFailureCode.' + detail.failure.code)
                  : tr('journalDetailErrorCode', { code: detail.failure.code || 'unknown' }),
                KNOWN_FAILURE_ACTIONS.has(detail.failure.action)
                  ? tr('journalFailureAction.' + detail.failure.action)
                  : '',
              ]
                .filter(Boolean)
                .join(' ')}
            />
          )}

          <dl className="workspace-detail-meta">
            <div>
              <dt>{tr('journalTaskKey')}</dt>
              <dd>
                <code>{detail.task?.key || '—'}</code>
              </dd>
            </div>
            <div>
              <dt>{tr('journalRevision')}</dt>
              <dd>
                <code className="workspace-detail-hash">{detail.task?.revision || '—'}</code>
                {detail.task?.revision && (
                  <span
                    className="workspace-detail-badge"
                    data-state={detail.task.revisionBinding === 'current' ? 'current' : 'stale'}
                  >
                    {revisionBindingText(detail.task.revisionBinding, detail.task.currentRevision, tr)}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt>{tr('journalOperation')}</dt>
              <dd>
                <code>{detail.operationId || tr('journalUnknown')}</code>
                {detail.operation ? ` · ${detail.operation}` : ''}
                {detail.state ? ` · ${detail.state}` : ''}
              </dd>
            </div>
            <div>
              <dt>{tr('journalClassification')}</dt>
              <dd>
                {tr(classificationKey)} · {journalPhaseLabel(detail.phase, tr)}
              </dd>
            </div>
            <div>
              <dt>{tr('journalObservedScope')}</dt>
              <dd>
                {tr('journalScopeFile')}: <code>{detail.scope?.fileKey || '—'}</code> ·{' '}
                {tr('journalScopePage')}: <code>{detail.scope?.pageId || '—'}</code> ·{' '}
                {tr('journalScopeRuntime')}: <code>{detail.scope?.runtimeGeneration || '—'}</code>
              </dd>
            </div>
          </dl>

          <section className="workspace-detail-block" aria-labelledby="detail-inputs-heading">
            <h3 id="detail-inputs-heading">{tr('journalSectionInputs')}</h3>
            {!inputRelations.length ? (
              <p className="workspace-empty">{tr('journalInputsEmpty')}</p>
            ) : (
              <ul className="workspace-detail-list">
                {inputRelations.map((rel, idx) => (
                  <li
                    key={`rel-in-${rel.type}-${rel.taskKey || rel.artifact}-${idx}`}
                    data-state={rel.revisionBinding}
                    data-direction={rel.direction || undefined}
                  >
                    <span className="workspace-detail-rel-type">{relationDirectionLabel(rel, tr)}</span>{' '}
                    {rel.taskKey ? (
                      <>
                        <strong>{rel.title || rel.taskKey}</strong> (<code>{rel.taskKey}</code>)
                      </>
                    ) : (
                      <strong>{rel.artifact || '—'}</strong>
                    )}
                    {rel.revision && <code className="workspace-detail-hash">{rel.revision}</code>}
                    <span
                      className="workspace-detail-badge"
                      data-state={rel.revisionBinding === 'current' ? 'current' : rel.revisionBinding}
                    >
                      {relationBindingText(rel, tr)}
                    </span>
                    {rel.freshness && <span className="workspace-detail-sub">{rel.freshness}</span>}
                    {(rel.artifact || rel.artifactSha256) && (
                      <span className="workspace-detail-sub">
                        {rel.taskKey && rel.artifact ? rel.artifact : ''}
                        {rel.taskKey && rel.artifact && rel.artifactSha256 ? ' · ' : ''}
                        {rel.artifactSha256 || ''}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="workspace-detail-block" aria-labelledby="detail-diff-heading">
            <h3 id="detail-diff-heading">{tr('journalSectionDiff')}</h3>
            {detail.diff.status === 'unavailable' ? (
              <Notice
                state="ready"
                title={tr('journalDiffUnavailable')}
                body={diffReasonText(detail.diff.reason, tr)}
              />
            ) : !detail.diff.fields.length ? (
              <p className="workspace-empty">{tr('journalDiffUnchanged')}</p>
            ) : (
              <>
                {detail.diff.basis && (
                  <p className="workspace-detail-sub">
                    {tr('journalDiffBasis', { basis: detail.diff.basis, total: detail.diff.totalFields })}
                  </p>
                )}
                <div
                  className="workspace-diff-scroll"
                  tabIndex={0}
                  role="region"
                  aria-label={tr('journalDiffCaption')}
                >
                  <table className="workspace-diff-table">
                    <caption>{tr('journalDiffCaption')}</caption>
                    <thead>
                      <tr>
                        <th scope="col">{tr('journalDiffColKey')}</th>
                        <th scope="col">{tr('journalDiffColField')}</th>
                        <th scope="col">{tr('journalDiffColKind')}</th>
                        <th scope="col">{tr('journalDiffColBefore')}</th>
                        <th scope="col">{tr('journalDiffColAfter')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.diff.fields.map((row, idx) => (
                        <tr key={`${row.key}-${row.field}-${idx}`} data-kind={row.kind}>
                          <td data-label={tr('journalDiffColKey')}>
                            <code>{row.key || '—'}</code>
                          </td>
                          <td data-label={tr('journalDiffColField')}>
                            <code>{row.field || '—'}</code>
                          </td>
                          <td data-label={tr('journalDiffColKind')}>
                            <span className="workspace-diff-badge" data-kind={row.kind}>
                              <DiffKindIcon kind={row.kind} />
                              <span aria-hidden="true">{diffKindSymbol(row.kind)}</span>
                              <span>{tr('journalDiffKind.' + row.kind)}</span>
                            </span>
                          </td>
                          <td data-label={tr('journalDiffColBefore')}>
                            {row.isText
                              ? `${tr('journalTextLengthMeta')} (${row.textLengthBefore ?? '—'})`
                              : row.before || '—'}
                          </td>
                          <td data-label={tr('journalDiffColAfter')}>
                            {row.isText
                              ? `${tr('journalTextLengthMeta')} (${row.textLengthAfter ?? '—'})`
                              : row.after || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {detail.diff.conflicts.length > 0 && (
              <div className="workspace-detail-conflicts">
                <h4>{tr('journalConflictTitle')}</h4>
                <ul className="workspace-detail-list">
                  {detail.diff.conflicts.map((conflict, idx) => (
                    <li key={`conflict-${conflict.key}-${idx}`}>
                      <strong>{conflict.key || '—'}</strong> · <code>{conflict.field || '—'}</code>
                      <span className="workspace-detail-sub">
                        {tr('journalConflictExpected')}: {conflictCellText(conflict.expectedBefore, tr)} ·{' '}
                        {tr('journalConflictPlannedAfter')}: {conflictCellText(conflict.plannedAfter, tr)} ·{' '}
                        {tr('journalConflictObserved')}: {conflictCellText(conflict.observed, tr)}
                      </span>
                      {conflict.scope && (
                        <span className="workspace-detail-sub">
                          {tr('journalConflictScope')}: {conflict.scope}
                        </span>
                      )}
                      {conflict.reasonCode && (
                        <span className="workspace-detail-sub">
                          {tr('journalConflictReason')}: {conflict.reasonCode}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="workspace-detail-block" aria-labelledby="detail-related-heading">
            <h3 id="detail-related-heading">{tr('journalSectionRelated')}</h3>
            <h4>{tr('journalPhasesTitle')}</h4>
            {!detail.phases.length ? (
              <p className="workspace-empty">{tr('journalPhasesEmpty')}</p>
            ) : (
              <ol className="workspace-detail-phases">
                {detail.phases.map((item, idx) => (
                  <li key={`${item.phase}-${idx}`}>
                    <span>{journalPhaseLabel(item.phase, tr)}</span>
                    {item.time && <time dateTime={item.time}> · {date(item.time)}</time>}
                  </li>
                ))}
              </ol>
            )}
            <h4>{tr('journalRecoveryLinksTitle')}</h4>
            {!linkedRelations.length ? (
              <p className="workspace-empty">{tr('journalNoRelated')}</p>
            ) : (
              <ul className="workspace-detail-list">
                {linkedRelations.map((rel, idx) => (
                  <li
                    key={`rec-${rel.direction || rel.type}-${rel.linkedOperationId || rel.taskKey}-${idx}`}
                    data-direction={rel.direction || undefined}
                  >
                    <span className="workspace-detail-rel-type">{relationDirectionLabel(rel, tr)}</span>{' '}
                    {rel.taskKey && <code>{rel.taskKey}</code>}
                    {rel.revision && <code className="workspace-detail-hash">{rel.revision}</code>}
                    {rel.linkedOperationId && rel.taskKey && rel.revision ? (
                      <button
                        type="button"
                        className="workspace-recovery-link"
                        aria-label={tr('journalRecoveryAria', {
                          label: relationDirectionLabel(rel, tr),
                          operationId: rel.linkedOperationId,
                        })}
                        onClick={() => onOpenRelated(rel)}
                      >
                        {tr('journalRecoveryOpen', { operationId: rel.linkedOperationId })}
                      </button>
                    ) : (
                      <span className="workspace-detail-sub">{tr('journalRecoveryNoOperationId')}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Section>
  );
}

export default function Workspace({
  model: initialModel = {},
  locale = 'ko',
  t,
  send,
  setLocale,
  Shell,
}) {
  const [model, setModel] = useState(initialModel);
  const [ready, setReady] = useState(Boolean(initialModel.tasks));
  const [view, setView] = useState(initialModel.view || 'tasks');
  const [project, setProject] = useState(initialModel.project || '');
  const [stage, setStage] = useState('');
  const [activityTask, setActivityTask] = useState('');
  const [control, setControl] = useState(null);
  const [carouselNotice, setCarouselNotice] = useState(null);
  const [carouselLink, setCarouselLink] = useState(null);
  const [focusTask, setFocusTask] = useState(null);
  const [dependencyKey, setDependencyKey] = useState('');
  const [detailView, setDetailView] = useState(null);
  const session = useRef(null);
  const modelRef = useRef(initialModel);
  const sendRef = useRef(send);
  const localeRef = useRef(setLocale);
  const focusTargets = useRef(new Map());
  const detailTriggerRefs = useRef(new Map());
  const detailHeadingRef = useRef(null);
  const detailViewRef = useRef(null);
  const pendingDetailRef = useRef(null);
  const detailRequestSeq = useRef(0);
  const detailRestoreRef = useRef(null);
  const detailBackStackRef = useRef([]);
  const pendingRestoreRef = useRef(null);
  const focusDetailHeadingRef = useRef(false);
  const heading = useRef(null);
  useEffect(() => {
    sendRef.current = send;
    localeRef.current = setLocale;
  }, [send, setLocale]);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);
  useEffect(() => {
    detailViewRef.current = detailView;
  }, [detailView]);
  const tr = (key, params) => t('workspace.' + key, params);
  const sendMessage = (type, extra = {}) =>
    sendRef.current({ type, workspaceSession: session.current, ...extra });

  useEffect(() => {
    function receive(event) {
      const message = event.data?.pluginMessage;
      if (!message) return;
      if (['workspace-carousel-selected','workspace-carousel-presented','workspace-carousel-error'].includes(message.type)) {
        if (message.workspaceSession && message.workspaceSession !== session.current) return;
        setCarouselNotice(message.type === 'workspace-carousel-selected' ? 'selected' :
          message.type === 'workspace-carousel-presented' ? 'presented' : message.message || 'error');
        setCarouselLink(verifiedPresentationLink(message, {fileKey:modelRef.current.fileKey,
          tasks:tasksOf(modelRef.current), history:historyOf(modelRef.current)}));
        return;
      }
      if (message.type === DETAIL_PROTOCOL.resultType) {
        const currentScope = buildDetailScope(modelRef.current, session.current);
        if (isDetailResponseStale(pendingDetailRef.current, message, currentScope)) return;
        const expectedTaskKey = pendingDetailRef.current?.taskKey || '';
        pendingDetailRef.current = null;
        const result = normalizeDetailResult(
          message,
          currentScope,
          tasksOf(modelRef.current),
          modelRef.current.retired,
        );
        if (result.status === 'scope-changed') {
          detailBackStackRef.current = [];
        }
        setDetailView({
          ...result,
          taskKey: result.detail?.task?.key || expectedTaskKey,
        });
        return;
      }
      if (message.type === DETAIL_PROTOCOL.scopeChangedType) {
        if (!session.current || message.workspaceSession !== session.current) return;
        const nextModelPatch = {
          fileKey: typeof message.fileKey === 'string' && message.fileKey ? message.fileKey : null,
          pageId: typeof message.pageId === 'string' && message.pageId ? message.pageId : null,
          ...(Array.isArray(message.journalHistory) ? { journalHistory: message.journalHistory } : {}),
          ...(typeof message.journalUnavailable === 'boolean'
            ? { journalUnavailable: message.journalUnavailable }
            : {}),
          ...(Array.isArray(message.inputFreshness) ? { inputFreshness: message.inputFreshness } : {}),
        };
        const nextModel = { ...modelRef.current, ...nextModelPatch };
        const nextScope = buildDetailScope(nextModel, session.current);
        modelRef.current = nextModel;
        setModel(nextModel);
        pendingDetailRef.current = null;
        detailBackStackRef.current = [];
        if (detailViewRef.current) {
          focusDetailHeadingRef.current = true;
          setDetailView({
            status: 'scope-changed',
            reason: 'scope-changed',
            operationId: null,
            detail: null,
            scope: nextScope,
          });
        }
        return;
      }
      if (message.type === 'workspace-control-state') {
        if (message.workspaceSession !== session.current) return;
        const nextModelPatch = {
          ...(Array.isArray(message.history) ? { history: message.history } : {}),
          ...(Array.isArray(message.journalHistory)
            ? { journalHistory: message.journalHistory, journalUnavailable: message.journalUnavailable === true }
            : message.journalUnavailable === true
              ? { journalUnavailable: true }
              : {}),
          ...(Array.isArray(message.inputFreshness) ? { inputFreshness: message.inputFreshness } : {}),
          ...(typeof message.fileKey === 'string' ? { fileKey: message.fileKey } : {}),
          ...(typeof message.pageId === 'string' ? { pageId: message.pageId } : {}),
          ...(message.runtime !== undefined ? { runtime: message.runtime } : {}),
          ...(typeof message.runtimeGeneration === 'string'
            ? { runtimeGeneration: message.runtimeGeneration }
            : {}),
        };
        const nextScope = buildDetailScope({ ...modelRef.current, ...nextModelPatch }, session.current);
        setControl({ busy: message.busy === true, outcome: message.outcome });
        if (Object.keys(nextModelPatch).length) {
          setModel((previous) => ({ ...previous, ...nextModelPatch }));
        }
        if (detailViewRef.current && !scopesMatch(detailViewRef.current.scope, nextScope)) {
          pendingDetailRef.current = null;
          detailBackStackRef.current = [];
          focusDetailHeadingRef.current = true;
          setDetailView({
            status: 'scope-changed',
            reason: 'scope-changed',
            operationId: null,
            detail: null,
            scope: nextScope,
          });
        } else if (message.journalUnavailable === true && detailViewRef.current?.status === 'loading') {
          pendingDetailRef.current = null;
          setDetailView({
            status: 'unavailable',
            reason: 'control-unavailable',
            operationId: detailViewRef.current.operationId || null,
            taskKey: detailViewRef.current.taskKey || '',
            detail: null,
            scope: nextScope,
          });
        }
      } else if (message.type === 'workspace-error') {
        if (session.current && message.workspaceSession !== session.current) return;
        setModel((previous) => ({ ...previous, error: message.message }));
      } else if (message.type === 'workspace-tasks') {
        if (message.workspaceSession !== session.current) setCarouselLink(null);
        session.current = message.workspaceSession;
        const nextScope = buildDetailScope(message, message.workspaceSession);
        if (detailViewRef.current) {
          if ((message.view && message.view !== 'history') || !scopesMatch(detailViewRef.current.scope, nextScope)) {
            pendingDetailRef.current = null;
            detailBackStackRef.current = [];
            if (message.view && message.view !== 'history') {
              detailRestoreRef.current = null;
              setDetailView(null);
            } else {
              focusDetailHeadingRef.current = true;
              setDetailView({
                status: 'scope-changed',
                reason: 'scope-changed',
                operationId: null,
                detail: null,
                scope: nextScope,
              });
            }
          }
        }
        const tasks = tasksOf(message);
        const previous = [...historyOf(message)]
          .reverse()
          .map((event) => tasks.find((task) => task.key === event.taskKey))
          .find(Boolean);
        setReady(true);
        setModel(message);
        modelRef.current = message;
        setView(message.view || 'tasks');
        setProject(
          message.project ||
            previous?.project ||
            tasks.find((task) => !task.fileKey || task.fileKey === message.fileKey)?.project ||
            tasks[0]?.project ||
            '',
        );
        setStage('');
        setActivityTask(message.focusKey || '');
        setFocusTask(message.focusKey || null);
        if (locales.has(message.locale)) localeRef.current?.(message.locale);
      }
    }
    window.addEventListener('message', receive);
    sendRef.current({ type: 'workspace-home-ready', locale: navigator.language });
    const heartbeat = window.setInterval(() => {
      if (session.current)
        sendRef.current({
          type: 'workspace-control-tick',
          workspaceSession: session.current,
          fileKey: modelRef.current.fileKey,
        });
    }, 1000);
    return () => {
      window.removeEventListener('message', receive);
      window.clearInterval(heartbeat);
    };
  }, []);

  const tasks = tasksOf(model);
  const history = historyOf(model);
  const projects = [...new Set(tasks.map((task) => task.project).filter(Boolean))];
  const projectTasks = tasks.filter((task) => !project || task.project === project);
  const inputFreshness = task => (Array.isArray(model.inputFreshness) ? model.inputFreshness : []).find(row => row.taskKey === task.key && row.revision === task.revision);
  const activityHistory = history.filter(event => !project || tasks.find(task => task.key === event.taskKey)?.project === project);
  const activity = workspaceActivity(projectTasks, activityHistory);
  const scoped = projectTasks.filter((task) => !stage || task.kind === stage);
  const recommendation = view === 'tasks' ? selectRecommendation(model, scoped) : null;
  const recommended = recommendation?.task;
  const recommendedEvent = recommended ? latestFor(model, recommended) : null;
  const carouselTasks = projectTasks.filter(task => task.kind === 'native-edit' && task.fileKey === model.fileKey && task.pageId)
    .map(task => {
      const event = [...history].reverse().find(item => item.taskKey === task.key && item.revision === task.revision
        && item.carousel?.schema === 'figma-flow-carousel-summary-v1' && item.carousel.file_key === model.fileKey
        && item.carousel.page_id === task.pageId);
      return {task, event, carousel:event?.carousel || null};
    });
  const carouselRequest = type => (event, carousel) => {
    setCarouselNotice(null);
    setCarouselLink(null);
    sendMessage(type, {taskKey:event.taskKey, revision:event.revision, executionId:event.executionId,
      stateId:carousel.initial_state, nodeId:carousel.flow_start_node_id});
  };
  const carouselActions = {presentLink:carouselLink, onSelectCarousel:carouselRequest('workspace-carousel-select'),
    onPresentCarousel:carouselRequest('workspace-carousel-present')};
  const busy = control?.busy === true;
  const recent = [...history]
    .reverse()
    .find(
      (event) =>
        projectTasks.some((task) => task.key === event.taskKey && task.revision === event.revision) &&
        event.status !== 'requested',
    );
  const previewSource = workspacePreviews(recommended).length
    ? recommended
    : projectTasks.find(
        (task) => task.project === recommended?.project && workspacePreviews(task).length,
      );
  const remaining = scoped.filter((task) => (view === 'codex' ? task.threadId : task !== recommended));
  const visibleHistory = history
    .map((event, index) => ({
      ...event,
      eventKey: [event.taskKey, event.revision, event.time, event.operation, event.status, index].join(
        ':',
      ),
    }))
    .reverse()
    .filter(
      (event) => (!project || tasks.find((task) => task.key === event.taskKey)?.project === project) &&
        (!activityTask || event.taskKey === activityTask),
    );
  const stateText = (event) => tr(event.operation === 'download' ? 'downloadRequested' : event.status);
  const date = (time) => new Date(time).toLocaleString(locale);
  const rememberFocus = (key) => (node) => {
    if (node) focusTargets.current.set(key, node);
    else focusTargets.current.delete(key);
  };
  const rememberDetailTrigger = (key) => (node) => {
    if (node) detailTriggerRefs.current.set(key, node);
    else detailTriggerRefs.current.delete(key);
  };
  useEffect(() => {
    if (!focusTask || busy) return;
    const target = focusTargets.current.get(focusTask) || heading.current;
    target?.focus();
    setFocusTask(null);
  }, [focusTask, view, busy, model]);
  useEffect(() => {
    if (detailView && focusDetailHeadingRef.current) {
      focusDetailHeadingRef.current = false;
      detailHeadingRef.current?.focus();
    }
  }, [detailView]);
  useEffect(() => {
    if (detailView || view !== 'history' || !pendingRestoreRef.current) return;
    const saved = pendingRestoreRef.current;
    pendingRestoreRef.current = null;
    if (typeof window !== 'undefined') {
      if (typeof window.scrollTo === 'function') window.scrollTo(0, saved.scrollY || 0);
      if (typeof document !== 'undefined' && document.documentElement) {
        document.documentElement.scrollTop = saved.scrollY || 0;
      }
    }
    const trigger = detailTriggerRefs.current.get(saved.triggerKey);
    (trigger || heading.current)?.focus?.();
  }, [detailView, view, project, activityTask]);
  const closeOperationDetail = () => {
    pendingDetailRef.current = null;
    if (detailViewRef.current?.status !== 'scope-changed' && detailBackStackRef.current.length > 0) {
      const previous = detailBackStackRef.current.pop();
      focusDetailHeadingRef.current = true;
      setDetailView(previous);
      return;
    }
    detailBackStackRef.current = [];
    if (detailRestoreRef.current) {
      pendingRestoreRef.current = detailRestoreRef.current;
      setProject(detailRestoreRef.current.project);
      setActivityTask(detailRestoreRef.current.activityTask);
      detailRestoreRef.current = null;
    }
    setDetailView(null);
  };
  useEffect(() => {
    if (!detailView || view !== 'history' || typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
      return;
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeOperationDetail();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [detailView, view]);
  const openOperationDetail = (row, triggerKey, { pushHistory = false } = {}) => {
    const currentScope = buildDetailScope(modelRef.current, session.current);
    const scrollY =
      typeof window !== 'undefined' && typeof window.scrollY === 'number'
        ? window.scrollY
        : typeof document !== 'undefined' && document.documentElement
          ? document.documentElement.scrollTop || 0
          : 0;
    if (pushHistory && detailViewRef.current) {
      detailBackStackRef.current = [...detailBackStackRef.current, detailViewRef.current];
    } else {
      detailBackStackRef.current = [];
      detailRestoreRef.current = {
        triggerKey: triggerKey || row?.operationId || '',
        project,
        activityTask,
        scrollY,
      };
    }
    focusDetailHeadingRef.current = true;
    const opId = safeOperationId(row?.operationId);
    const taskKey = typeof row?.taskKey === 'string' ? row.taskKey.trim() : '';
    const revision =
      typeof row?.revision === 'string' && /^[a-f0-9]{64}$/i.test(row.revision.trim())
        ? row.revision.trim().toLowerCase()
        : '';
    if (!opId) {
      pendingDetailRef.current = null;
      const fallbackDetail = normalizeDetailDto(
        {
          schema: OPERATION_DETAIL_SCHEMA,
          classification: row?.classification === 'legacy' ? 'legacy' : 'unknown',
          operation: row?.operation || '',
          task: taskKey ? { key: taskKey, revision } : null,
        },
        currentScope,
        tasks,
        model.retired,
      );
      setDetailView({
        status: 'ok',
        reason: null,
        operationId: null,
        taskKey: fallbackDetail.task.key,
        revision: fallbackDetail.task.revision,
        detail: fallbackDetail,
        scope: currentScope,
      });
      return;
    }
    if (!taskKey || taskKey.length > 200 || !revision) {
      pendingDetailRef.current = null;
      setDetailView({
        status: 'error',
        reason: 'invalid-task-revision-binding',
        operationId: opId,
        taskKey,
        revision,
        detail: null,
        scope: currentScope,
      });
      return;
    }
    const requestId = 'detail-' + ++detailRequestSeq.current;
    pendingDetailRef.current = {
      requestId,
      operationId: opId,
      taskKey,
      revision,
      scope: currentScope,
    };
    setDetailView({
      status: 'loading',
      requestId,
      operationId: opId,
      taskKey,
      revision,
      detail: null,
      scope: currentScope,
    });
    sendMessage(DETAIL_PROTOCOL.requestType, {
      operationId: opId,
      taskKey,
      revision,
      requestId,
    });
  };
  const openTask = (task, chat = false) =>
    sendMessage(chat ? 'workspace-chat-open' : 'workspace-open', { key: task.key });
  const navigate = (name) => {
    pendingDetailRef.current = null;
    detailBackStackRef.current = [];
    detailRestoreRef.current = null;
    pendingRestoreRef.current = null;
    setDetailView(null);
    setView(name);
    setStage('');
    setActivityTask('');
  };
  const changeLocale = (code) => {
    if (locales.has(code)) sendMessage('workspace-locale', { locale: code });
  };
  const jumpToReceipt = (task) => {
    pendingDetailRef.current = null;
    detailBackStackRef.current = [];
    detailRestoreRef.current = null;
    pendingRestoreRef.current = null;
    setDetailView(null);
    setView('history');
    setStage('');
    setActivityTask(task.key);
    setFocusTask(task.key);
  };
  const rowKey = (event, index) => event.eventKey || String(index);

  return (
    <Shell view="workspace" active={view} busy={busy} onNavigate={navigate} onLocale={changeLocale}>
      <header className="workspace-context">
        <div>
          <h1 ref={heading} tabIndex={-1}>
            {project ||
              (projects.length === 1 ? projects[0] : tr(projects.length ? 'allProjects' : 'title'))}
          </h1>
          <p>
            {tr('currentFile')} · {tr('taskCount', { count: projectTasks.length })}
          </p>
        </div>
        {view === 'tasks' && model.controlEnabled && <Action variant="quiet" icon={RefreshCw} disabled={busy} onClick={() => sendRef.current({type:'workspace-home-ready',locale})}>{tr('refreshInputs')}</Action>}
        {projects.length > 1 && (
          <label className="workspace-project">
            <span aria-hidden="true">{tr('switchProject')}</span>
            <select
              aria-label={tr('project')}
              value={project}
              onChange={(event) => {
                pendingDetailRef.current = null;
                detailBackStackRef.current = [];
                detailRestoreRef.current = null;
                pendingRestoreRef.current = null;
                setDetailView(null);
                setProject(event.target.value);
                setStage('');
                setActivityTask('');
              }}
            >
              <option value="">{tr('allProjects')}</option>
              {projects.map((name) => (
                <option value={name} key={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>
      {model.controlEnabled && <p className="workspace-auto">{t('common.modeAutomatic')}</p>}
      {(!ready || !tasks.length || model.error || model.storageError) && (
        <Notice
          state={!ready ? 'busy' : model.error ? 'error' : 'ready'}
          title={tr(
            !ready ? 'loading' : model.error ? 'error' : model.storageError ? 'nav.history' : 'empty',
          )}
          body={
            model.error || tr(!ready ? 'loadingBody' : model.storageError ? 'storageError' : 'emptyBody')
          }
        />
      )}
      {control && (busy || control.outcome !== 'finished' || !recent) && (
        <Notice
          state={busy ? 'busy' : ['failed', 'uncertain'].includes(control.outcome) ? 'error' : 'success'}
          title={tr(busy ? 'controlBusy' : 'controlDone')}
          body={tr(
            'control.' +
              (['finished', 'failed', 'uncertain'].includes(control.outcome)
                ? control.outcome
                : 'waiting'),
          )}
        />
      )}
      {recent && view !== 'history' && !recommendation?.inspect && (
        <div className="workspace-receipt" role="status">
          <EventIcon status={recent.status} />
          <span>
            {tasks.find((task) => task.key === recent.taskKey)?.title} · {stateText(recent)}
          </span>
          <time dateTime={recent.time}>
            {new Date(recent.time).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}
          </time>
        </div>
      )}
      {view === 'tasks' &&
        projectTasks.length > 4 &&
        new Set(projectTasks.map((task) => task.kind)).size > 1 && (
          <label className="workspace-filter">
            {tr('typeFilter')}
            <select value={stage} disabled={busy} onChange={(event) => setStage(event.target.value)}>
              <option value="">{tr('allStages')}</option>
              {[...new Set(projectTasks.map((task) => task.kind))].map((kind) => (
                <option key={kind} value={kind}>
                  {tr('kind.' + kind)}
                </option>
              ))}
            </select>
          </label>
        )}
      {(view === 'tasks' || (view === 'history' && !detailView)) && ready && projectTasks.length > 0 && (
        <ActivitySummary activity={activity} tr={tr} />
      )}
      {view === 'tasks' && ready && carouselTasks.length > 0 && <CarouselOverview items={carouselTasks.slice(0,16)} tr={tr}
        notice={carouselNotice}
        onOpenTask={openTask} {...carouselActions}
      />}
      {recommended && (
        <>
          <PreviewStrip items={workspacePreviews(previewSource)} />
          <Section className="workspace-next">
            <p className="eyebrow">{tr(recommendation.inspect ? 'latestResult' : 'next')}</p>
            <div className="workspace-next-line">
              <h2>{recommended.title}</h2>
              <Action
                variant="primary"
                disabled={busy}
                ref={rememberFocus(recommended.key)}
                aria-label={tr(
                  recommendation.inspect
                    ? 'receiptFor'
                    : model.controlEnabled && recommended.threadId
                      ? 'chatOpen'
                      : 'openTask',
                  { title: recommended.title },
                )}
                onClick={() =>
                  recommendation.inspect
                    ? jumpToReceipt(recommended)
                    : openTask(recommended, !!(model.controlEnabled && recommended.threadId))
                }
              >
                {recommendation.inspect
                  ? tr('viewReceipt')
                  : model.controlEnabled && recommended.threadId
                    ? t('common.continueCodex')
                    : tr('open')}
              </Action>
            </div>
            <p>
              {tr('kind.' + recommended.kind)} ·{' '}
              {recommendation.inspect && recommendedEvent
                ? stateText(recommendedEvent) + ' · ' + date(recommendedEvent.time)
                : tr(
                    !recommendedEvent
                      ? 'nextNew'
                      : recommendedEvent.status === 'failed'
                        ? 'nextRetry'
                        : 'nextCheck',
                  )}
            </p>
            <button type="button" className="workspace-dependency-link" onClick={() => setDependencyKey(dependencyKey === recommended.key ? '' : recommended.key)} aria-expanded={dependencyKey === recommended.key}>{tr('dependencyHeading')}</button>
            {(recommended.has_input_record || Array.isArray(recommended.input_summary)) && <AssetDisclosure summary={recommended.input_summary} freshness={inputFreshness(recommended)} tr={tr} />}
          </Section>
        </>
      )}
      {view === 'history' ? (
        detailView ? (
          <OperationDetailPanel
            detailState={detailView}
            tasks={tasks}
            tr={tr}
            date={date}
            headingRef={detailHeadingRef}
            onBack={closeOperationDetail}
            onOpenRelated={(rel) =>
              openOperationDetail(
                { operationId: rel.linkedOperationId, taskKey: rel.taskKey, revision: rel.revision },
                null,
                { pushHistory: true },
              )
            }
          />
        ) : (
        <>
        <Section title={tr('journalTitle')}>
          <p className="workspace-boundary">{tr('journalBoundary')}</p>
          {model.journalUnavailable && <p role="status">{tr('journalUnavailable')}</p>}
          {!model.journalUnavailable && !(model.journalHistory || []).length && <p>{tr('journalEmpty')}</p>}
          <ol className="workspace-history">
            {(Array.isArray(model.journalHistory) ? model.journalHistory : []).filter(row =>
              (!project || tasks.find(task => task.key === row.taskKey)?.project === project) && (!activityTask || row.taskKey === activityTask))
              .slice(-80).reverse().map((row, index) => {
                const triggerKey = row.operationId || `${row.taskKey || 'unknown'}:${index}`;
                const taskTitle = tasks.find(task => task.key === row.taskKey)?.title || tr('removedTask');
                return (
                <li key={triggerKey} className="workspace-journal-row">
                  <div className="workspace-journal-row-head">
                    <h3>{taskTitle}</h3>
                    <button
                      type="button"
                      className="workspace-journal-detail-btn"
                      ref={rememberDetailTrigger(triggerKey)}
                      aria-label={tr('journalDetailFor', { title: taskTitle, operationId: row.operationId || tr('journalUnknown') })}
                      onClick={() => openOperationDetail(row, triggerKey)}
                    >
                      {tr('journalViewDetail')}
                    </button>
                  </div>
                  <p>{tr('journalOperation')} · <code>{row.operationId || tr('journalUnknown')}</code>{row.revision ? <> · <code className="workspace-detail-hash">{row.revision}</code></> : null}</p>
                  <p>{tr(row.classification === 'recorded' ? 'journalRecorded' : row.classification === 'legacy' ? 'journalLegacy' : 'journalUnknown')} · {journalPhaseLabel(row.phase, tr)}</p>
                  <ol>{(Array.isArray(row.phases) ? row.phases : []).map((event, phaseIndex) => <li key={phaseIndex}>
                    <span>{journalPhaseLabel(event.phase, tr)}</span> · <time dateTime={event.time}>{date(event.time)}</time>
                  </li>)}</ol>
                </li>
                );
              })}
          </ol>
        </Section>
        <Section title={tr('historyTitle')}>
          <p className="workspace-activity-caption">{tr('flowBoundary')}</p>
          <label className="workspace-filter">
            {tr('flowFilter')}
            <select value={activityTask} onChange={event => setActivityTask(event.target.value)}>
              <option value="">{tr('allTasks')}</option>
              {projectTasks.map(task => <option value={task.key} key={task.key}>{task.title}</option>)}
            </select>
          </label>
          {!visibleHistory.length && <p className="workspace-empty">{tr('historyEmpty')}</p>}
          <ExecutionFlows
            flows={activity.flows.filter(flow => !activityTask || flow.steps[0].event.taskKey === activityTask)}
            tasks={tasks} tr={tr} stateText={stateText} date={date} rememberFocus={rememberFocus}
            carouselNotice={carouselNotice} {...carouselActions}
            fileKey={model.fileKey}
          />
          {!!activity.legacy.filter(step => !activityTask || step.event.taskKey === activityTask).length && <details className="workspace-flow workspace-unlinked">
            <summary ref={activityTask && !activity.flows.some(flow => flow.steps[0].event.taskKey === activityTask) ? rememberFocus(activityTask) : undefined}><span>{tr('unlinkedHistory')}</span><span>{tr('flowSteps', { count: activity.legacy.filter(step => !activityTask || step.event.taskKey === activityTask).length })}</span></summary>
            <ol>{activity.legacy.filter(step => !activityTask || step.event.taskKey === activityTask).map(({ event, index, current }) => <li key={index} data-state={event.status}>
              <span>{tasks.find(task => task.key === event.taskKey)?.title || tr('removedTask')} · {event.operation === 'download' ? tr('downloadRequested') : tr('op.' + event.operation)} · {stateText(event)}</span>
              <time dateTime={event.time}>{date(event.time)}</time>
              <span>{current ? tr('currentRevision') : tr('stale')}</span>
            </li>)}</ol>
          </details>}
          {!!visibleHistory.length && <details className="workspace-raw-history"><summary>{tr('rawHistory')}</summary>
          <ol className="workspace-history">
            {visibleHistory.map((event, index) => {
              const task = tasks.find((task) => task.key === event.taskKey),
                stale = !task || task.revision !== event.revision;
              const operation = tr(
                event.operation === 'verification'
                  ? 'verification'
                  : event.operation === 'download'
                    ? 'downloadRequested'
                    : 'op.' + event.operation,
              );
              return (
                <li key={rowKey(event, index)} data-state={event.status}>
                  <EventIcon status={event.status} />
                  <div className="workspace-history-meta">
                    <time dateTime={event.time}>{date(event.time)}</time>
                    {stale && <span>{tr('stale')}</span>}
                  </div>
                  <h3>{task?.title || tr('removedTask')}</h3>
                  <p>
                    {event.operation === 'download' ? operation : operation + ' · ' + stateText(event)}
                  </p>
                  {task && (
                    <Action
                      variant="quiet"
                                            disabled={busy || (!!task.fileKey && task.fileKey !== model.fileKey)}
                      onClick={() => openTask(task)}
                    >
                      {tr(stale ? 'openCurrent' : 'open')}
                    </Action>
                  )}
                </li>
              );
            })}
          </ol>
          </details>}
          <p className="workspace-boundary">{tr('historyBoundary')}</p>
        </Section>
        </>
        )
      ) : (
        <Section>
          {view === 'tasks' && dependencyKey && tasks.some((task) => task.key === dependencyKey) && (
            <DependencyText tasks={tasks} selected={dependencyKey} retired={model.retired} onSelect={setDependencyKey} tr={tr} />
          )}
          {!!remaining.length && view === 'tasks' && (
            <h2 className="workspace-list-title">{tr(recommended ? 'otherTasks' : 'allStages')}</h2>
          )}
          {remaining.map((task) => {
            const event = latestFor(model, task),
              wrong = !!task.fileKey && task.fileKey !== model.fileKey;
            const Icon =
              task.kind === 'sync' ? RefreshCw : task.kind === 'discover' ? ScanSearch : FileText;
            return (
              <div className="workspace-row-group" key={task.key}>
              <Action
                className="workspace-row"
                variant="quiet"
                ref={rememberFocus(task.key)}
                disabled={busy || wrong}
                aria-label={tr(view === 'codex' ? 'chatOpen' : wrong ? 'wrongOpen' : 'openTask', {
                  title: task.title,
                })}
                onClick={() => openTask(task, view === 'codex')}
              >
                <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
                <span className="workspace-row-info">
                  <span className="workspace-row-title">{task.title}</span>
                  <span
                    className="workspace-row-meta"
                    title={[task.fileKey, task.pageId].filter(Boolean).join(' / ')}
                  >
                    {tr('kind.' + task.kind)} · {tr(wrong ? 'wrongFile' : 'currentFile')}
                    {task.pageId ? ' · ' + tr('page') : ''}
                  </span>
                  <span className="workspace-row-state" data-state={event?.status || 'ready'}>
                    {event ? stateText(event) + ' · ' + tr('op.' + event.operation) : tr('notRun')}
                  </span>
                </span>
                <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
              </Action>
              <button type="button" className="workspace-history-link" onClick={() => jumpToReceipt(task)}>{tr('viewTaskFlow')}</button>
              <button type="button" className="workspace-dependency-link" onClick={() => setDependencyKey(task.key)}>{tr('dependencyHeading')}</button>
              {(task.has_input_record || Array.isArray(task.input_summary)) && <AssetDisclosure summary={task.input_summary} freshness={inputFreshness(task)} tr={tr} />}
              </div>
            );
          })}
          {!remaining.length && !recommended && tasks.length > 0 && (
            <p className="workspace-empty">{tr(view === 'codex' ? 'noChat' : 'noMatch')}</p>
          )}
        </Section>
      )}
    </Shell>
  );
}
