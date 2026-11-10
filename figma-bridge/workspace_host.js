/* One local plugin entry. Registered task hosts retain their native scope guards. */
const workspaceKinds = new Set(['import', 'review', 'discover', 'sync']);
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
const workspaceSession = () => Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2);
const workspaceBusy = current => current.inFlight > 0 || current.busy;
const workspaceCurrent = current => workspaceActive === current;
function workspaceControl(current) {
  if (workspaceCurrent(current)) figma.ui.postMessage({workspaceSession: current.session, workspaceControl: true, busy: workspaceBusy(current)});
}
function workspaceHome(notice = '') {
  if (workspaceActive && workspaceBusy(workspaceActive)) return false;
  if (workspaceActive?.controller) workspaceActive.controller.close();
  workspaceActive = null;
  workspaceNotice = notice;
  workspaceHomeSession = workspaceSession();
  figma.showUI(__html__, {width: 520, height: 680, themeColors: true});
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
  const session = JSON.stringify(workspaceActive.session);
  // The lexical parent wrapper keeps existing approved message schemas intact.
  const relay = `<script>
const workspaceSession = ${session};
const workspaceCanChat = ${JSON.stringify(!!workspaceActive.task.threadId && workspaceActive.view === 'task')};
const parent = {postMessage(message) {
  window.parent.postMessage({pluginMessage: {type: 'workspace-task-message', workspaceSession, payload: message.pluginMessage}}, '*');
}};
window.addEventListener('message', event => {
  const message = event.data && event.data.pluginMessage;
  if (!message || message.workspaceSession !== workspaceSession) {event.stopImmediatePropagation(); return;}
  if (message.workspaceControl) {
    const button = document.getElementById('workspace-back');
    if (button) {button.disabled = !!message.busy; button.title = message.busy ? '실행이 끝나면 작업 목록으로 돌아갈 수 있습니다.' : '';}
    const chat = document.getElementById('workspace-chat');
    if (chat) chat.disabled = !!message.busy;
    event.stopImmediatePropagation(); return;
  }
  Object.defineProperty(event, 'data', {value: {pluginMessage: message.payload}});
}, true);
window.addEventListener('DOMContentLoaded', () => {
  const bar = document.createElement('nav');
  bar.setAttribute('aria-label', '작업 이동');
  bar.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:6px 14px;box-sizing:border-box;max-width:100%;border-bottom:1px solid var(--figma-color-border,#dedde5);background:var(--figma-color-bg,#fff);';
  const button = document.createElement('button');
  button.id = 'workspace-back'; button.type = 'button'; button.textContent = '작업 목록으로';
  button.style.cssText = 'min-height:32px;padding:4px 10px;font-size:12px;';
  button.onclick = () => window.parent.postMessage({pluginMessage: {type: 'workspace-back', workspaceSession}}, '*');
  bar.appendChild(button);
  if (workspaceCanChat) {
    const chat = document.createElement('button');
    chat.id = 'workspace-chat'; chat.type = 'button'; chat.textContent = 'Codex 연결';
    chat.title = '현재 패널 입력을 초기화하고 연결 화면을 엽니다.';
    chat.style.cssText = 'min-height:32px;padding:4px 10px;font-size:12px;';
    chat.onclick = () => window.parent.postMessage({pluginMessage: {type: 'workspace-chat', workspaceSession}}, '*');
    bar.appendChild(chat);
  }
  document.body.prepend(bar);
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
    workspaceHome(String(error.message || error));
  } finally {
    current.inFlight = 0;
    workspaceControl(current);
  }
}
figma.ui.onmessage = async message => {
  if (!message || typeof message !== 'object') return;
  if (!workspaceActive) {
    if (message.type === 'workspace-home-ready') {
      figma.ui.postMessage({type: 'workspace-tasks', workspaceSession: workspaceHomeSession,
        fileKey: figma.fileKey || null, error: workspaceNotice || null, tasks: [...workspaceTasks.values()].map(({key, title, project, kind, fileKey, pageId, threadId}) =>
          ({key, title, project, kind, fileKey: fileKey || null, pageId: pageId || null, threadId: threadId || null}))});
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
  if (message.type === 'workspace-back') {workspaceHome(); return;}
  if (message.type === 'workspace-navigation-ready') {workspaceControl(current); return;}
  if (message.type === 'workspace-chat') {await workspaceOpen(current.task, 'chat'); return;}
  if (message.type !== 'workspace-task-message' || !current.handler) return;
  if (current.view === 'chat' && message.payload?.type === 'chat:back') {workspaceHome(); return;}
  if (current.task.fileKey && current.task.fileKey !== figma.fileKey) return;
  current.inFlight++;
  workspaceControl(current);
  try {await current.handler(message.payload);}
  catch (error) {
    if (workspaceCurrent(current)) figma.ui.postMessage({workspaceSession: current.session,
      workspaceControl: true, busy: false, error: String(error.message || error)});
  } finally {
    current.inFlight--;
    workspaceControl(current);
  }
};
workspaceHome();
