/* One local plugin entry. Registered task hosts retain their native scope guards. */
const workspaceKinds = new Set(['import', 'review', 'discover', 'sync', 'native-edit']);
const workspaceTasks = new Map();
for (const task of FLOW_TASKS) {
  if (!task || typeof task.key !== 'string' || !task.key || workspaceTasks.has(task.key) ||
      !workspaceKinds.has(task.kind) || typeof task.run !== 'function') {
    throw Error('Invalid or duplicate registered Figma Flow task');
  }
  workspaceTasks.set(task.key, task);
}
let workspaceActive = null;
let workspaceHomeSession = '';
let workspaceNotice = '';
const workspaceLocales = new Set(FLOW_LOCALES);
const workspaceOperations = new Set(['import', 'export', 'sync', 'draft-review', 'read', 'apply', 'verification', 'download', 'chat:queue', 'chat:open']);
const workspaceStatuses = new Set(['requested', 'running', 'finished', 'failed', 'readback', 'verified', 'baseline']);
const workspaceStorageKey = figma.fileKey ? 'figma-flow-workspace-v1:' + figma.fileKey : null;
let workspaceState = {locale: null, history: []};
let workspaceWrites = Promise.resolve();
let workspaceStorageError = false;
let workspaceHomeView = 'tasks', workspaceProject = null, workspaceFocus = null;
const workspaceLoaded = (async () => {
  if (!workspaceStorageKey || !figma.clientStorage) return;
  try {
    const saved = await figma.clientStorage.getAsync(workspaceStorageKey);
    if (!saved || typeof saved !== 'object') return;
    if (workspaceLocales.has(saved.locale)) workspaceState.locale = saved.locale;
    if (Array.isArray(saved.history)) workspaceState.history = saved.history.filter(event =>
      event && typeof event.taskKey === 'string' && event.taskKey.length <= 200 &&
      typeof event.revision === 'string' && event.revision.length <= 128 &&
      workspaceOperations.has(event.operation) && workspaceStatuses.has(event.status) &&
      typeof event.time === 'string' && event.time.length <= 40 && Number.isFinite(Date.parse(event.time))).slice(-80)
      .map(({taskKey, revision, time, operation, status, executionId}) => ({taskKey, revision, time, operation, status,
        ...(typeof executionId === 'string' && /^[a-z0-9-]{1,80}$/.test(executionId) ? {executionId} : {})}));
  } catch (_) {workspaceStorageError = true;}
})();
function workspacePersist() {
  if (!workspaceStorageKey || !figma.clientStorage) return;
  const snapshot = JSON.parse(JSON.stringify(workspaceState));
  workspaceWrites = workspaceWrites.catch(() => {}).then(() => figma.clientStorage.setAsync(workspaceStorageKey, snapshot))
    .catch(() => {workspaceStorageError = true;});
}
function workspaceJournalHistory(view) {
  if (!view || typeof view !== 'object' || view.classification === 'legacy') return {classification: 'legacy', phase: 'unknown', phases: []};
  if (view.classification !== 'recorded' || !Array.isArray(view.phases)) return {classification: 'unknown', phase: 'unknown', phases: []};
  const phases = view.phases.filter(item => item && typeof item.phase === 'string' && typeof item.time === 'string').map(item => ({phase: item.phase, time: item.time}));
  return {classification: 'recorded', phase: phases.length ? phases[phases.length - 1].phase : 'unknown', phases};
}
function workspaceRecord(current, operation, status, journal) {
  if (!workspaceCurrent(current) || !workspaceOperations.has(operation) || !workspaceStatuses.has(status)) return;
  const event = {taskKey: current.task.key, revision: current.task.revision || '',
    time: new Date().toISOString(), operation, status,
    ...(operation === 'download' || !current.executionId ? {} : {executionId: current.executionId})};
  if (journal) {
    const serverJournal = workspaceJournalHistory(journal);
    event.classification = serverJournal.classification;
    event.phase = serverJournal.phase;
  }
  workspaceState.history.push(event);
  workspaceState.history = workspaceState.history.slice(-80);
  workspacePersist();
}
function workspaceObserve(current, message) {
  if (!message || !current.operation) return;
  if (message.busy === true || message.state === 'busy' || (message.type === 'busy' && message.value === true)) {
    if (!current.started) workspaceRecord(current, current.operation, 'running');
    current.started = true;
  }
  if (message.type === 'geometry-failure' || message.type === 'chat:error' || message.error || message.readback?.status === 'error' ||
      message.rollback_conflicts?.length || message.readback?.rollback_conflicts?.length ||
      (message.type === 'sync-result' && (message.result?.preview_error || !['baseline','applied','unchanged'].includes(message.result?.status))) ||
      (message.type === 'status' && (message.state === 'error' || /^Error:/.test(message.message || '')))) {
    if (current.outcome !== 'failed') workspaceRecord(current, current.operation, 'failed');
    current.outcome = 'failed';
  } else if (message.type === 'readback' || message.readback) {
    if (!current.outcome) workspaceRecord(current, current.operation, 'readback');
    current.outcome = 'readback';
  } else if (message.type === 'sync-result' || message.type === 'chat:result') {
    const outcome = message.type === 'sync-result' && message.result.status === 'baseline' ? 'baseline' : 'finished';
    if (!current.outcome) workspaceRecord(current, current.operation, outcome);
    current.outcome = outcome;
  }
}
function workspacePreview(task) {
  return (Array.isArray(task.preview) ? task.preview : []).filter(item =>
    item && typeof item.title === 'string' && item.title.length <= 120 && typeof item.src === 'string' &&
    item.src.length <= 600000 && /^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/=]+$/.test(item.src)).slice(0, 2)
    .map(({title, src}) => ({title, src}));
}
function workspaceLocaleHtml(html) {
  const locale = workspaceState.locale;
  if (!locale) return html;
  return html.replace(/<html([^>]*)>/i, (_, attributes) => '<html' + attributes.replace(/\sdata-flow-locale=(?:"[^"]*"|'[^']*')/gi, '') +
    ' data-flow-locale="' + locale + '">');
}
const workspaceSession = () => Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2);
const workspaceBusy = current => current.inFlight > 0 || current.busy;
const workspaceCurrent = current => workspaceActive === current;
function workspaceControl(current) {
  if (current.view === 'remote') return;
  if (workspaceCurrent(current)) figma.ui.postMessage({workspaceSession: current.session, workspaceControl: true, busy: workspaceBusy(current)});
}
function workspaceHome(notice = '', view = 'tasks', project = null, focus = null) {
  if (workspaceActive && workspaceBusy(workspaceActive)) return false;
  if (workspaceActive?.controller) workspaceActive.controller.close();
  workspaceActive = null;
  workspaceNotice = notice;
  workspaceHomeView = view; workspaceProject = project; workspaceFocus = focus;
  workspaceHomeSession = workspaceSession();
  figma.showUI(workspaceLocaleHtml(__html__), {width: 560, height: 680, themeColors: true});
  return true;
}
function workspaceTaskFigma() {
  const current = workspaceActive;
  if (!current) throw Error('No registered workspace task is open');
  const assertCurrent = () => {
    if (!workspaceCurrent(current)) throw Error('Workspace task session expired');
    if (current.task.fileKey && current.task.fileKey !== figma.fileKey) throw Error('Workspace task file scope changed');
  };
  const ui = new Proxy({}, {
    get(_target, key) {
      const target = figma.ui;
      if (key === 'onmessage') return current.handler;
      if (key === 'postMessage') return message => {
        if (!workspaceCurrent(current)) return;
        if (typeof message?.busy === 'boolean') current.busy = message.busy;
        else if (message?.type === 'busy' && typeof message.value === 'boolean') current.busy = message.value;
        else if (message?.state === 'busy') current.busy = true;
        else if (message && ('readback' in message || 'error' in message)) current.busy = false;
        workspaceObserve(current, message);
        if (current.view === 'remote') {if (current.onOutput) current.onOutput(message); return;}
        target.postMessage({workspaceSession: current.session, payload: message});
        workspaceControl(current);
      };
      const value = Reflect.get(target, key);
      return typeof value === 'function' ? (...args) => {assertCurrent(); return value.apply(target, args);} : value;
    },
    set(target, key, value) {
      assertCurrent();
      if (key !== 'onmessage' || typeof value !== 'function') throw Error('Unsupported task UI assignment');
      current.handler = value;
      return true;
    }
  });
  return new Proxy({}, {
    get(_target, key) {
      const target = figma;
      if (key === 'ui') return ui;
      const value = Reflect.get(target, key);
      return typeof value === 'function' ? (...args) => {
        assertCurrent();
        if (key === 'showUI') {
          if (current.view === 'remote') {current.html = args[0]; current.options = args[1]; return;}
          const options = {...args[1], themeColors: true};
          const result = value.call(target, args[0], options);
          workspaceControl(current);
          return result;
        }
        return value.apply(target, args);
      } : value;
    },
    set() {throw Error('Task cannot replace workspace host state');}
  });
}
function workspaceTaskHtml(html) {
  if (!workspaceActive || typeof html !== 'string') throw Error('Task HTML requires an active workspace session');
  html = workspaceLocaleHtml(html).replace(/<html([^>]*)>/i, (_, attributes) =>
    '<html' + attributes.replace(/\sdata-flow-workspace=(?:"[^"]*"|'[^']*')/gi, '') + ' data-flow-workspace="true">');
  const session = JSON.stringify(workspaceActive.session);
  // The lexical parent wrapper keeps existing approved message schemas intact.
  const relay = `<script>
const workspaceSession = ${session};
const workspaceView = ${JSON.stringify(workspaceActive.view === 'chat' ? 'codex' : 'tasks')};
let workspaceHostBusy = false;
window.FlowWorkspace = Object.freeze({
  active: workspaceView,
  canChat: ${JSON.stringify(!!workspaceActive.task.threadId)},
  get busy() {return workspaceHostBusy;},
  go(name) {
    if (workspaceHostBusy || !['tasks', 'history', 'codex'].includes(name) || (name === 'codex' && workspaceView === 'codex')) return;
    const type = name === 'history' ? 'workspace-history' : name === 'codex' ? 'workspace-chat' : 'workspace-back';
    window.parent.postMessage({pluginMessage: {type, workspaceSession}}, '*');
  },
  setLocale(locale) {
    if (!${JSON.stringify([...workspaceLocales])}.includes(locale)) return;
    if (window.FlowUI) window.FlowUI.setLocale(locale);
    window.parent.postMessage({pluginMessage: {type: 'workspace-locale', workspaceSession, locale}}, '*');
  }
});
const parent = {postMessage(message) {
  window.parent.postMessage({pluginMessage: {type: 'workspace-task-message', workspaceSession, payload: message.pluginMessage}}, '*');
}};
window.addEventListener('message', event => {
  const message = event.data && event.data.pluginMessage;
  if (!message || message.workspaceSession !== workspaceSession) {event.stopImmediatePropagation(); return;}
  if (message.workspaceControl) {
    workspaceHostBusy = !!message.busy;
    window.dispatchEvent(new CustomEvent('flow:host-busy', {detail: {busy: workspaceHostBusy}}));
    if (window.FlowPanel) window.FlowPanel.setState({busy: !!message.busy});
    event.stopImmediatePropagation(); return;
  }
  Object.defineProperty(event, 'data', {value: {pluginMessage: message.payload}});
}, true);
window.addEventListener('DOMContentLoaded', () => {
  if (window.FlowPanel) window.FlowPanel.mount({
    mode: 'workspace', active: workspaceView,
    onNavigate: window.FlowWorkspace.go,
    onLocale: window.FlowWorkspace.setLocale
  });
  document.addEventListener('click', event => {
    if (event.target.closest && event.target.closest('#save:not(:disabled), #download:not(:disabled)'))
      window.parent.postMessage({pluginMessage: {type: 'workspace-download', workspaceSession}}, '*');
  }, true);
  window.parent.postMessage({pluginMessage: {type: 'workspace-navigation-ready', workspaceSession}}, '*');
});
</script>`;
  const head = html.match(/<head(?:\s[^>]*)?>/i);
  if (head) return html.replace(head[0], head[0] + relay);
  const opening = html.match(/<html(?:\s[^>]*)?>/i) || html.match(/<!doctype[^>]*>/i);
  return opening ? html.replace(opening[0], opening[0] + relay) : relay + html;
}
async function workspaceOpen(task, view = 'task') {
  if (workspaceActive && workspaceBusy(workspaceActive)) return;
  if (task.fileKey && task.fileKey !== figma.fileKey) return;
  if (workspaceActive?.controller) workspaceActive.controller.close();
  const current = {task, view, session: workspaceSession(), handler: null, inFlight: 1, busy: false, controller: null};
  workspaceActive = current;
  try {
    if (view === 'chat') {
      if (typeof WorkspaceChat === 'undefined' || !task.threadId) throw Error('이 작업에는 Codex 대화가 연결되지 않았습니다.');
      const proxy = workspaceTaskFigma();
      current.controller = WorkspaceChat.open(proxy, task, {
        session: current.session, isCurrent: () => workspaceCurrent(current),
        showUI: (html, options) => proxy.showUI(workspaceTaskHtml(html), options),
        postMessage: message => proxy.ui.postMessage(message), uiHtml: WORKSPACE_CHAT_UI,
        onBack: workspaceHome,
        relay: typeof WORKSPACE_CHAT_CONFIG === 'undefined' ? null : WORKSPACE_CHAT_CONFIG
      });
      current.handler = message => current.controller.handle(message);
    } else {
      await task.run();
    }
  } catch (error) {
    current.inFlight = 0; current.busy = false;
    if (view === 'remote') {workspaceActive = null; throw error;}
    workspaceHome(String(error.message || error));
  } finally {
    current.inFlight = 0;
    workspaceControl(current);
  }
  return workspaceCurrent(current) ? current : null;
}
figma.ui.onmessage = async message => {
  if (!message || typeof message !== 'object') return;
  const activeBeforeLoad = workspaceActive, homeBeforeLoad = workspaceHomeSession;
  await workspaceLoaded;
  if (workspaceActive !== activeBeforeLoad || (!workspaceActive && workspaceHomeSession !== homeBeforeLoad)) return;
  if (message.type === 'workspace-locale') {
    const expected = !workspaceActive || workspaceActive.view === 'remote' ? workspaceHomeSession : workspaceActive.session;
    if (message.workspaceSession === expected && workspaceLocales.has(message.locale) &&
        (!workspaceActive?.task.fileKey || workspaceActive.task.fileKey === figma.fileKey)) {
      workspaceState.locale = message.locale; workspacePersist();
    }
    return;
  }
  if (message.type === 'workspace-control-tick') {
    if (message.workspaceSession === workspaceHomeSession && message.fileKey === figma.fileKey &&
        (!workspaceActive || workspaceActive.view === 'remote') && typeof workspaceControlTick === 'function') await workspaceControlTick();
    return;
  }
  if (!workspaceActive) {
    if (message.type === 'workspace-home-ready') {
      if (!workspaceState.locale) {
        const code = String(message.locale || '').toLowerCase().split('-')[0];
        workspaceState.locale = workspaceLocales.has(code) ? code : 'ko'; workspacePersist();
      }
      figma.ui.postMessage({type: 'workspace-tasks', workspaceSession: workspaceHomeSession,
        fileKey: figma.fileKey || null, controlEnabled: typeof WORKSPACE_CONTROL_CONFIG !== 'undefined' && !!WORKSPACE_CONTROL_CONFIG, locale: workspaceState.locale, history: workspaceState.history,
        view: workspaceHomeView, project: workspaceProject, focusKey: workspaceFocus, storageError: workspaceStorageError, error: workspaceNotice || null, tasks: [...workspaceTasks.values()].map(({key, title, project, kind, fileKey, pageId, threadId, revision, preview, paired, productionAdmitted}) =>
          ({key, title, project, kind, fileKey: fileKey || null, pageId: pageId || null, threadId: threadId || null, revision: revision || '', preview: workspacePreview({preview}), paired: paired === true, productionAdmitted: productionAdmitted === true}))});
      return;
    }
    if (!['workspace-open', 'workspace-chat-open'].includes(message.type) || message.workspaceSession !== workspaceHomeSession) return;
    const task = workspaceTasks.get(message.key);
    if (!task) return;
    if (task.fileKey && task.fileKey !== figma.fileKey) {
      workspaceNotice = '이 작업은 지정된 Design 파일에서만 열 수 있습니다.';
      figma.ui.postMessage({type: 'workspace-error', workspaceSession: workspaceHomeSession, message: workspaceNotice});
      return;
    }
    await workspaceOpen(task, message.type === 'workspace-chat-open' ? 'chat' : 'task');
    return;
  }
  const current = workspaceActive;
  if (message.workspaceSession !== current.session) return;
  if (message.type === 'workspace-back' || message.type === 'workspace-history') {
    workspaceHome('', message.type === 'workspace-history' ? 'history' : 'tasks', current.task.project || null, current.task.key); return;
  }
  if (message.type === 'workspace-download') {workspaceRecord(current, 'download', 'requested'); return;}
  if (message.type === 'workspace-navigation-ready') {workspaceControl(current); return;}
  if (message.type === 'workspace-chat') {
    if (current.view === 'chat') return;
    if (current.task.threadId) await workspaceOpen(current.task, 'chat');
    else workspaceHome('', 'codex', current.task.project || null, current.task.key);
    return;
  }
  if (message.type !== 'workspace-task-message' || !current.handler) return;
  if (current.view === 'chat' && message.payload?.type === 'chat:back') {workspaceHome(); return;}
  if (current.task.fileKey && current.task.fileKey !== figma.fileKey) return;
  const operation = message.payload?.type;
  if (workspaceOperations.has(operation) && workspaceBusy(current)) return;
  if (workspaceOperations.has(operation)) {current.executionId = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12); current.operation = operation; current.outcome = null; current.started = false; current.verificationRecorded = false; workspaceRecord(current, operation, 'requested');}
  if (!workspaceOperations.has(operation) && operation !== 'receipt') {current.operation = null; current.outcome = null;}
  if (operation === 'receipt' && current.operation === 'draft-review' && current.outcome === 'readback' && !current.verificationRecorded) {
    current.verificationRecorded = true; workspaceRecord(current, 'verification', message.payload.passed === true ? 'verified' : 'failed');
    current.operation = 'verification'; current.outcome = message.payload.passed === true ? 'verified' : 'failed';
  }
  current.inFlight++;
  workspaceControl(current);
  try {
    await current.handler(message.payload);
    if (workspaceOperations.has(operation) && !current.outcome && current.started && operation === 'import') workspaceRecord(current, operation, 'finished');
  }
  catch (error) {
    if (current.outcome !== 'failed') workspaceRecord(current, workspaceOperations.has(operation) ? operation : current.operation, 'failed');
    current.outcome = 'failed';
    if (workspaceCurrent(current)) figma.ui.postMessage({workspaceSession: current.session,
      workspaceControl: true, busy: false, error: String(error.message || error)});
  } finally {
    current.inFlight--;
    workspaceControl(current);
  }
};
workspaceHome();
