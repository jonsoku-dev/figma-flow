import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Check,
  CircleCheck,
  Clock3,
  FileText,
  RefreshCw,
  ScanSearch,
  TriangleAlert,
} from 'lucide-react';
import { Action, Section, Notice, PreviewStrip } from './components.jsx';
import { workspaceActivity } from './WorkspaceActivity.mjs';
import { ActivitySummary, CarouselOverview, ExecutionFlows } from './WorkspaceActivity.jsx';
import { dependencyFreshness, dependencyView } from './dependencyView.mjs';
import { assetInventory } from './assetInventory.mjs';

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
  const [focusTask, setFocusTask] = useState(null);
  const [dependencyKey, setDependencyKey] = useState('');
  const session = useRef(null);
  const modelRef = useRef(initialModel);
  const sendRef = useRef(send);
  const localeRef = useRef(setLocale);
  const focusTargets = useRef(new Map());
  const heading = useRef(null);
  useEffect(() => {
    sendRef.current = send;
    localeRef.current = setLocale;
  }, [send, setLocale]);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);
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
        return;
      }
      if (message.type === 'workspace-control-state') {
        if (message.workspaceSession !== session.current) return;
        setControl({ busy: message.busy === true, outcome: message.outcome });
        if (Array.isArray(message.history))
          setModel((previous) => ({ ...previous, history: message.history }));
        if (Array.isArray(message.journalHistory))
          setModel((previous) => ({ ...previous, journalHistory: message.journalHistory, journalUnavailable: message.journalUnavailable === true }));
        if (Array.isArray(message.inputFreshness))
          setModel(previous => ({...previous, inputFreshness:message.inputFreshness}));
      } else if (message.type === 'workspace-error') {
        if (session.current && message.workspaceSession !== session.current) return;
        setModel((previous) => ({ ...previous, error: message.message }));
      } else if (message.type === 'workspace-tasks') {
        session.current = message.workspaceSession;
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
  useEffect(() => {
    if (!focusTask || busy) return;
    const target = focusTargets.current.get(focusTask) || heading.current;
    target?.focus();
    setFocusTask(null);
  }, [focusTask, view, busy, model]);
  const openTask = (task, chat = false) =>
    sendMessage(chat ? 'workspace-chat-open' : 'workspace-open', { key: task.key });
  const navigate = (name) => {
    setView(name);
    setStage('');
    setActivityTask('');
  };
  const changeLocale = (code) => {
    if (locales.has(code)) sendMessage('workspace-locale', { locale: code });
  };
  const jumpToReceipt = (task) => {
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
      {(view === 'tasks' || view === 'history') && ready && projectTasks.length > 0 && (
        <ActivitySummary activity={activity} tr={tr} />
      )}
      {view === 'tasks' && ready && carouselTasks.length > 0 && <CarouselOverview items={carouselTasks.slice(0,16)} tr={tr}
        notice={carouselNotice}
        onOpenTask={openTask}
        onSelectCarousel={(event, carousel) => {
          setCarouselNotice(null);
          sendMessage('workspace-carousel-select', {executionId:event.executionId,stateId:carousel.initial_state,nodeId:carousel.flow_start_node_id});
        }}
        onPresentCarousel={(event, carousel) => {
          setCarouselNotice(null);
          sendMessage('workspace-carousel-present', {executionId:event.executionId,stateId:carousel.initial_state,nodeId:carousel.flow_start_node_id});
        }}
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
        <>
        <Section title={tr('journalTitle')}>
          <p className="workspace-boundary">{tr('journalBoundary')}</p>
          {model.journalUnavailable && <p role="status">{tr('journalUnavailable')}</p>}
          {!model.journalUnavailable && !(model.journalHistory || []).length && <p>{tr('journalEmpty')}</p>}
          <ol className="workspace-history">
            {(Array.isArray(model.journalHistory) ? model.journalHistory : []).filter(row =>
              (!project || tasks.find(task => task.key === row.taskKey)?.project === project) && (!activityTask || row.taskKey === activityTask))
              .slice(-80).reverse().map(row => <li key={row.operationId}>
                <h3>{tasks.find(task => task.key === row.taskKey)?.title || tr('removedTask')}</h3>
                <p>{tr('journalOperation')} · <code>{row.operationId}</code></p>
                <p>{tr(row.classification === 'recorded' ? 'journalRecorded' : row.classification === 'legacy' ? 'journalLegacy' : 'journalUnknown')} · {row.phase}</p>
                <ol>{(Array.isArray(row.phases) ? row.phases : []).map((event, index) => <li key={index}>
                  <span>{event.phase}</span> · <time dateTime={event.time}>{date(event.time)}</time>
                </li>)}</ol>
              </li>)}
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
            carouselNotice={carouselNotice}
            onSelectCarousel={(event, carousel) => {
              setCarouselNotice(null);
              sendMessage('workspace-carousel-select', {executionId:event.executionId,
                stateId:carousel.initial_state, nodeId:carousel.flow_start_node_id});
            }}
            onPresentCarousel={(event, carousel) => {
              setCarouselNotice(null);
              sendMessage('workspace-carousel-present', {executionId:event.executionId,
                stateId:carousel.initial_state, nodeId:carousel.flow_start_node_id});
            }}
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
