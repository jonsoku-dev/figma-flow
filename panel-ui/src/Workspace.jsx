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

const locales = new Set(['ko', 'en', 'ja']);
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
  const [control, setControl] = useState(null);
  const [focusTask, setFocusTask] = useState(null);
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
      if (message.type === 'workspace-control-state') {
        if (message.workspaceSession !== session.current) return;
        setControl({ busy: message.busy === true, outcome: message.outcome });
        if (Array.isArray(message.history))
          setModel((previous) => ({ ...previous, history: message.history }));
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
  const scoped = projectTasks.filter((task) => !stage || task.kind === stage);
  const recommendation = view === 'tasks' ? selectRecommendation(model, scoped) : null;
  const recommended = recommendation?.task;
  const recommendedEvent = recommended ? latestFor(model, recommended) : null;
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
      (event) => !project || tasks.find((task) => task.key === event.taskKey)?.project === project,
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
  };
  const changeLocale = (code) => {
    if (locales.has(code)) sendMessage('workspace-locale', { locale: code });
  };
  const jumpToReceipt = (task) => {
    setView('history');
    setStage('');
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
        {projects.length > 1 && (
          <label className="workspace-project">
            <span aria-hidden="true">{tr('switchProject')}</span>
            <select
              aria-label={tr('project')}
              value={project}
              onChange={(event) => {
                setProject(event.target.value);
                setStage('');
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
          </Section>
        </>
      )}
      {view === 'history' ? (
        <Section title={tr('historyTitle')}>
          {!visibleHistory.length && <p className="workspace-empty">{tr('historyEmpty')}</p>}
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
              const firstForTask =
                visibleHistory.findIndex((previous) => previous.taskKey === event.taskKey) === index;
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
                      ref={firstForTask ? rememberFocus(task.key) : undefined}
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
          <p className="workspace-boundary">{tr('historyBoundary')}</p>
        </Section>
      ) : (
        <Section>
          {!!remaining.length && view === 'tasks' && (
            <h2 className="workspace-list-title">{tr(recommended ? 'otherTasks' : 'allStages')}</h2>
          )}
          {remaining.map((task) => {
            const event = latestFor(model, task),
              wrong = !!task.fileKey && task.fileKey !== model.fileKey;
            const Icon =
              task.kind === 'sync' ? RefreshCw : task.kind === 'discover' ? ScanSearch : FileText;
            return (
              <Action
                className="workspace-row"
                variant="quiet"
                key={task.key}
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
                    {event ? stateText(event) : tr('notRun')}
                  </span>
                </span>
                <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
              </Action>
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
