/* Regression checks for WorkspaceActivity/Workspace carousel notices and host message contracts. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');

const panelRoot = path.join(__dirname, '../panel-ui');
const panelRequire = createRequire(path.join(panelRoot, 'package.json'));
const { buildSync } = panelRequire('esbuild');
const plugin = JSON.parse(fs.readFileSync(path.join(__dirname, '../plugin.json'), 'utf8'));
const commonCatalog = JSON.parse(fs.readFileSync(path.join(__dirname, '../figma-bridge/locales/common.json'), 'utf8'));
const hostSource = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_host.js'), 'utf8');
const activitySource = fs.readFileSync(path.join(panelRoot, 'src/WorkspaceActivity.jsx'), 'utf8');

function runPanelTest(entryCode) {
  const built = buildSync({
    stdin: { contents: entryCode, resolveDir: panelRoot, loader: 'jsx' },
    absWorkingDir: panelRoot,
    bundle: true,
    write: false,
    platform: 'node',
    format: 'cjs',
    jsx: 'automatic',
    define: {
      'process.env.NODE_ENV': '"production"',
      __FLOW_DISPLAY_NAME__: JSON.stringify(plugin.extensions['com.openai'].interface.displayName),
      __FLOW_LOCALES__: JSON.stringify(Object.keys(Object.values(commonCatalog)[0])),
    },
    logLevel: 'silent',
  });
  const result = spawnSync(process.execPath, ['-e', built.outputFiles[0].text], {
    cwd: panelRoot,
    encoding: 'utf8',
    env: { ...process.env, HOST_SOURCE_PATH: path.join(__dirname, '../figma-bridge/workspace_host.js') },
  });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}

test('WorkspaceActivity shares one notice helper for home and history and translates selected/presented across all locales', () => {
  const noticeMatches = activitySource.match(/<CarouselNotice\b/g) || [];
  assert.equal(noticeMatches.length, 2, 'both CarouselOverview and ExecutionFlows must share CarouselNotice');
  assert.equal((activitySource.match(/carouselSelected/g) || []).length, 1, 'selected notice key must not be duplicated');
  assert.equal((activitySource.match(/carouselPresented/g) || []).length, 1, 'presented notice key must not be duplicated');

  const stdout = runPanelTest(`
import assert from 'node:assert/strict';
import fs from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CarouselOverview, ExecutionFlows, carouselNoticeText } from './src/WorkspaceActivity.jsx';
import { PanelContext } from './src/components.jsx';

globalThis.window = {};
const dictionary = JSON.parse(fs.readFileSync('../figma-bridge/locales/workspace.json', 'utf8'));
const makeTr = locale => (key, params = {}) => {
  const full = 'workspace.' + key;
  let text = dictionary[full]?.[locale] || full;
  for (const [name, value] of Object.entries(params)) text = text.replace('{' + name + '}', value);
  return text;
};
const makeT = locale => (key, params = {}) => {
  let text = dictionary[key]?.[locale] || key;
  for (const [name, value] of Object.entries(params)) text = text.replace('{' + name + '}', value);
  return text;
};

const carousel = {
  schema: 'figma-flow-carousel-summary-v1',
  graph_sha256: 'a'.repeat(64),
  graph_id: 'graph',
  file_key: 'file-a',
  page_id: '1:2',
  frame_key: 'slides',
  status: 'current',
  initial_state: 'one',
  flow_start_node_id: '1:3',
  states: [
    { state_id: 'one', screen_id: 'WEB-one', frame_id: '1:3', title: 'Slide 1', status: 'current' },
    { state_id: 'two', screen_id: 'WEB-two', frame_id: '1:4', title: 'Slide 2', status: 'current' },
  ],
  edges: [],
};
const task = { key: 'a', title: 'Carousel task', kind: 'native-edit', revision: 'r1', fileKey: 'file-a', pageId: '1:2' };
const event = { taskKey: 'a', revision: 'r1', operation: 'apply', status: 'readback', executionId: 'exec-1', time: '2026-11-14T00:00:00Z', carousel };
const flows = [{ key: 'a:r1:exec-1', steps: [{ event, index: 0, current: true }] }];

for (const locale of ['ko', 'en', 'ja']) {
  const tr = makeTr(locale);
  const t = makeT(locale);
  assert.equal(carouselNoticeText('selected', tr), tr('carouselSelected'));
  assert.equal(carouselNoticeText('presented', tr), tr('carouselPresented'));
  assert.equal(carouselNoticeText('Custom error', tr), 'Custom error');
  assert.equal(carouselNoticeText(null, tr), '');

  const renderWithContext = node => renderToStaticMarkup(
    <PanelContext.Provider value={{ locale, t, setLocale() {}, hostBusy: false }}>{node}</PanelContext.Provider>
  );

  for (const [code, key] of [['selected', 'carouselSelected'], ['presented', 'carouselPresented']]) {
    const homeHtml = renderWithContext(<CarouselOverview items={[{ task, event, carousel }]} tr={tr} notice={code} />);
    assert.ok(homeHtml.includes('role="status">' + tr(key) + '</p>'), locale + ' home ' + code);
    assert.ok(!homeHtml.includes('>' + code + '<'), locale + ' home must not leak raw ' + code);

    const historyHtml = renderWithContext(
      <ExecutionFlows
        flows={flows}
        tasks={[task]}
        tr={tr}
        stateText={() => 'Readback'}
        date={() => '2026-11-14'}
        rememberFocus={() => () => {}}
        carouselNotice={code}
      />
    );
    assert.ok(historyHtml.includes('role="status">' + tr(key) + '</p>'), locale + ' history ' + code);
    assert.ok(!historyHtml.includes('>' + code + '<'), locale + ' history must not leak raw ' + code);
  }

  const errorHistoryHtml = renderWithContext(
    <ExecutionFlows
      flows={flows}
      tasks={[task]}
      tr={tr}
      stateText={() => 'Readback'}
      date={() => '2026-11-14'}
      rememberFocus={() => () => {}}
      carouselNotice="Host rejection message"
    />
  );
  assert.ok(errorHistoryHtml.includes('role="status">Host rejection message</p>'));

  const emptyHistoryHtml = renderWithContext(
    <ExecutionFlows
      flows={flows}
      tasks={[task]}
      tr={tr}
      stateText={() => 'Readback'}
      date={() => '2026-11-14'}
      rememberFocus={() => () => {}}
      carouselNotice={null}
    />
  );
  assert.ok(!emptyHistoryHtml.includes('workspace-carousel-notice'));
}
console.log('NOTICE_OK');
`);
  assert.match(stdout, /NOTICE_OK/);
});

test('Workspace UI carousel buttons dispatch real host-compatible payloads on Home and History and render host replies', () => {
  const stdout = runPanelTest(`
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import Workspace from './src/Workspace.jsx';
import { Shell, PanelContext } from './src/components.jsx';

class NodeShim {
  constructor(tag, ownerDocument) {
    this.nodeType = tag === '#text' ? 3 : tag === '#comment' ? 8 : 1;
    this.tagName = tag.toUpperCase();
    this.nodeName = this.tagName;
    this.ownerDocument = ownerDocument;
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = {};
    this.listeners = new Map();
    this.style = {};
    this.dataset = {};
    this.textContentValue = '';
  }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  get nextSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return i >= 0 ? this.parentNode.childNodes[i + 1] || null : null;
  }
  get previousSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return i > 0 ? this.parentNode.childNodes[i - 1] || null : null;
  }
  get textContent() {
    if (this.nodeType === 3 || this.nodeType === 8) return this.textContentValue;
    return this.childNodes.map(c => c.nodeType === 8 ? '' : c.textContent).join('');
  }
  set textContent(v) {
    if (this.nodeType === 3 || this.nodeType === 8) { this.textContentValue = String(v ?? ''); return; }
    this.childNodes = [];
    if (v !== '' && v != null) this.appendChild(this.ownerDocument.createTextNode(String(v)));
  }
  set nodeValue(v) { this.textContentValue = String(v ?? ''); }
  get nodeValue() { return this.textContentValue; }
  get className() { return this.attributes.class || ''; }
  set className(v) { this.attributes.class = String(v); }
  get disabled() { return Boolean(this.attributes.disabled); }
  set disabled(v) { if (v) this.attributes.disabled = true; else delete this.attributes.disabled; }
  get options() { return this.querySelectorAll('option'); }
  get value() { return this.attributes.value ?? this.textContent; }
  set value(v) { this.attributes.value = String(v ?? ''); }
  get selected() { return Boolean(this.attributes.selected); }
  set selected(v) { if (v) this.attributes.selected = true; else delete this.attributes.selected; }
  get defaultSelected() { return Boolean(this.attributes.selected); }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  insertBefore(child, before) {
    if (!before) return this.appendChild(child);
    if (child.parentNode) child.parentNode.removeChild(child);
    const idx = this.childNodes.indexOf(before);
    child.parentNode = this;
    if (idx < 0) this.childNodes.push(child);
    else this.childNodes.splice(idx, 0, child);
    return child;
  }
  removeChild(child) {
    const idx = this.childNodes.indexOf(child);
    if (idx >= 0) { this.childNodes.splice(idx, 1); child.parentNode = null; }
    return child;
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  removeAttribute(k) { delete this.attributes[k]; }
  getAttribute(k) { return this.attributes[k] ?? null; }
  hasAttribute(k) { return k in this.attributes; }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
  }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  dispatchEvent(event) {
    event.target = event.target || this;
    event.currentTarget = this;
    for (const fn of this.listeners.get(event.type) || []) fn(event);
    if (this.parentNode && !event.cancelBubble) this.parentNode.dispatchEvent(event);
    return true;
  }
  focus() { this.ownerDocument.activeElement = this; }
  click() {
    this.dispatchEvent({ type: 'click', bubbles: true, cancelBubble: false, preventDefault(){}, stopPropagation(){ this.cancelBubble = true; } });
  }
  querySelectorAll(sel) {
    const matches = [];
    const walk = node => {
      for (const child of node.childNodes) {
        if (child.nodeType === 1) {
          const hit = sel.startsWith('.')
            ? (child.className || '').split(/\\s+/).includes(sel.slice(1))
            : sel.startsWith('#')
              ? child.attributes.id === sel.slice(1)
              : child.tagName.toLowerCase() === sel.toLowerCase();
          if (hit) matches.push(child);
          walk(child);
        }
      }
    };
    walk(this);
    return matches;
  }
}

const winListeners = new Map();
const docListeners = new Map();
const doc = {
  nodeType: 9,
  activeElement: null,
  documentElement: null,
  defaultView: globalThis,
  createElement(tag) { return new NodeShim(tag, this); },
  createElementNS(_ns, tag) { return new NodeShim(tag, this); },
  createTextNode(text) { const n = new NodeShim('#text', this); n.textContent = text; return n; },
  createComment(text) { const n = new NodeShim('#comment', this); n.textContent = text; return n; },
  addEventListener(t, fn) { if (!docListeners.has(t)) docListeners.set(t, new Set()); docListeners.get(t).add(fn); },
  removeEventListener(t, fn) { docListeners.get(t)?.delete(fn); },
};
doc.documentElement = doc.createElement('html');
globalThis.HTMLIFrameElement = class HTMLIFrameElement {};
globalThis.HTMLElement = NodeShim;
globalThis.SVGElement = NodeShim;
globalThis.window = {
  addEventListener(t, fn) { if (!winListeners.has(t)) winListeners.set(t, new Set()); winListeners.get(t).add(fn); },
  removeEventListener(t, fn) { winListeners.get(t)?.delete(fn); },
  setInterval() { return 1; },
  clearInterval() {},
  dispatchEvent() {},
};
globalThis.document = doc;

const dictionary = JSON.parse(fs.readFileSync('../figma-bridge/locales/workspace.json', 'utf8'));
const common = JSON.parse(fs.readFileSync('../figma-bridge/locales/common.json', 'utf8'));
const allCopy = { ...dictionary, ...common };
const locale = 'en';
const t = (key, params = {}) => {
  let text = allCopy[key]?.[locale] || key;
  for (const [name, value] of Object.entries(params)) text = text.replace('{' + name + '}', value);
  return text;
};

const hostCode = fs.readFileSync(process.env.HOST_SOURCE_PATH, 'utf8');
const startPage = { id: '1:1', type: 'PAGE', selection: [] };
const targetPage = { id: '1:2', type: 'PAGE', loaded: 0, selection: [], flowStartingPoints: [{ nodeId: '1:3', name: 'Carousel' }], async loadAsync() { this.loaded++; } };
const values = { 'figma-flow-web-design-id': 'graph/WEB-one', 'figma-flow-web-design-sha256': 'a'.repeat(64) };
const frame = { id: '1:3', type: 'FRAME', parent: targetPage, getPluginData: key => values[key] || '' };
targetPage.children = [frame];
const hostMessages = [];
const hostProbe = { scrolled: [], external: [] };
const figma = {
  fileKey: 'file-a',
  currentPage: startPage,
  ui: { postMessage(m) { hostMessages.push(m); } },
  viewport: { scrollAndZoomIntoView(nodes) { hostProbe.scrolled = nodes.map(n => n.id); } },
  async getNodeByIdAsync(id) { return [startPage, targetPage, frame].find(n => n.id === id) || null; },
  async setCurrentPageAsync(page) { this.currentPage = page; },
  openExternal(url) { hostProbe.external.push(url); },
  showUI() {},
};
const hostCtx = vm.createContext({ figma, __html__: 'HOME', probe: hostProbe });
vm.runInContext(\`
const FLOW_LOCALES = ['ko', 'en', 'ja'];
const FLOW_TASKS = [
  { key: 'a', title: 'Carousel Task', project: 'Studio', kind: 'native-edit', revision: 'r1', fileKey: 'file-a', pageId: '1:2', run() {} }
];
\` + hostCode, hostCtx);

const summary = hostCtx.workspaceStoredCarousel({
  schema: 'figma-flow-carousel-summary-v1',
  graph_sha256: 'a'.repeat(64),
  graph_id: 'graph',
  file_key: 'file-a',
  page_id: '1:2',
  frame_key: 'slides',
  status: 'current',
  initial_state: 'one',
  flow_start_node_id: '1:3',
  states: [
    { state_id: 'one', screen_id: 'WEB-one', frame_id: '1:3', title: 'Slide One', status: 'current' },
    { state_id: 'two', screen_id: 'WEB-two', frame_id: '1:4', title: 'Slide Two', status: 'current' },
  ],
  edges: [],
});
vm.runInContext(\`workspaceState.history.push({taskKey:'a',revision:'r1',operation:'apply',status:'readback',executionId:'exec-ui',time:'2026-11-14T00:00:00Z',carousel:\${JSON.stringify(summary)}})\`, hostCtx);

const sent = [];
const container = doc.createElement('div');
const root = createRoot(container, { onUncaughtError(error) { throw error; } });
flushSync(() => {
  root.render(
    <PanelContext.Provider value={{ locale, t, setLocale() {}, hostBusy: false }}>
      <Workspace model={{}} locale={locale} t={t} send={m => sent.push(m)} Shell={Shell} />
    </PanelContext.Provider>
  );
});

async function run() {
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(sent.length, 1);
  assert.equal(sent[0].type, 'workspace-home-ready');

  await figma.ui.onmessage(sent[0]);
  const tasksMessage = hostMessages.filter(m => m.type === 'workspace-tasks').at(-1);
  assert.ok(tasksMessage?.workspaceSession);

  const deliver = msg => flushSync(() => {
    for (const fn of winListeners.get('message') || []) fn({ data: { pluginMessage: msg } });
  });
  deliver(tasksMessage);

  const expectedPayload = {
    workspaceSession: tasksMessage.workspaceSession,
    taskKey: 'a',
    revision: 'r1',
    executionId: 'exec-ui',
    stateId: 'one',
    nodeId: '1:3',
  };

  // Home view: Select button -> Host -> UI notice
  const homeOverview = container.querySelectorAll('.workspace-carousel-overview')[0];
  assert.ok(homeOverview);
  flushSync(() => { homeOverview.querySelectorAll('.workspace-carousel-select')[0].click(); });
  const homeSelectMsg = sent.at(-1);
  assert.deepEqual(homeSelectMsg, { type: 'workspace-carousel-select', ...expectedPayload });
  await figma.ui.onmessage(homeSelectMsg);
  const homeSelectedReply = hostMessages.at(-1);
  assert.equal(homeSelectedReply.type, 'workspace-carousel-selected');
  assert.equal(figma.currentPage.id, '1:2');
  assert.deepEqual(Array.from(hostProbe.scrolled), ['1:3']);
  assert.equal(hostProbe.external.length, 0);
  deliver(homeSelectedReply);
  assert.equal(homeOverview.querySelectorAll('.workspace-carousel-notice')[0].textContent, t('workspace.carouselSelected'));

  // Home view: Present button -> Host -> UI notice
  flushSync(() => { homeOverview.querySelectorAll('.workspace-carousel-present')[0].click(); });
  const homePresentMsg = sent.at(-1);
  assert.deepEqual(homePresentMsg, { type: 'workspace-carousel-present', ...expectedPayload });
  await figma.ui.onmessage(homePresentMsg);
  const homePresentedReply = hostMessages.at(-1);
  assert.equal(homePresentedReply.type, 'workspace-carousel-presented');
  assert.equal(hostProbe.external.length, 1);
  deliver(homePresentedReply);
  assert.equal(homeOverview.querySelectorAll('.workspace-carousel-notice')[0].textContent, t('workspace.carouselPresented'));

  // History view: Select and Present buttons -> Host -> UI notice
  flushSync(() => { container.querySelectorAll('#tab-history')[0].click(); });
  const historyFlows = container.querySelectorAll('.workspace-flows')[0];
  assert.ok(historyFlows);

  flushSync(() => { historyFlows.querySelectorAll('.workspace-carousel-select')[0].click(); });
  const historySelectMsg = sent.at(-1);
  assert.deepEqual(historySelectMsg, { type: 'workspace-carousel-select', ...expectedPayload });
  await figma.ui.onmessage(historySelectMsg);
  deliver(hostMessages.at(-1));
  assert.equal(historyFlows.querySelectorAll('.workspace-carousel-notice')[0].textContent, t('workspace.carouselSelected'));

  flushSync(() => { historyFlows.querySelectorAll('.workspace-carousel-present')[0].click(); });
  const historyPresentMsg = sent.at(-1);
  assert.deepEqual(historyPresentMsg, { type: 'workspace-carousel-present', ...expectedPayload });
  await figma.ui.onmessage(historyPresentMsg);
  const historyPresentedReply = hostMessages.at(-1);
  assert.equal(historyPresentedReply.type, 'workspace-carousel-presented');
  assert.equal(hostProbe.external.length, 2);
  deliver(historyPresentedReply);
  assert.equal(historyFlows.querySelectorAll('.workspace-carousel-notice')[0].textContent, t('workspace.carouselPresented'));
  assert.notEqual(historyFlows.querySelectorAll('.workspace-carousel-notice')[0].textContent, 'presented');

  // Mismatched session reply must be ignored by UI
  deliver({ type: 'workspace-carousel-error', workspaceSession: 'forged-session', message: 'FORGED_ERROR' });
  assert.equal(historyFlows.querySelectorAll('.workspace-carousel-notice')[0].textContent, t('workspace.carouselPresented'));

  // Host error reply for current session is displayed in UI
  deliver({ type: 'workspace-carousel-error', workspaceSession: tasksMessage.workspaceSession, message: 'Host stale error' });
  assert.equal(historyFlows.querySelectorAll('.workspace-carousel-notice')[0].textContent, 'Host stale error');

  console.log('CONTRACT_OK');
}
run().catch(err => { console.error(err); process.exit(1); });
`);
  assert.match(stdout, /CONTRACT_OK/);
});
