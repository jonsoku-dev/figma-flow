/* Present fallback: the host-verified Figma prototype URL reaches the panel as a native, user-clicked link. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');

const root = path.join(__dirname, '..');
const panelRoot = path.join(root, 'panel-ui');
const { buildSync } = createRequire(path.join(panelRoot, 'package.json'))('esbuild');
const plugin = JSON.parse(fs.readFileSync(path.join(root, 'plugin.json'), 'utf8'));
const common = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/common.json'), 'utf8'));
const hostSource = fs.readFileSync(path.join(root, 'figma-bridge/workspace_host.js'), 'utf8');
const locales = Object.keys(Object.values(common)[0]);
const EXPECTED_URL = 'https://www.figma.com/proto/file-a/SaaS?node-id=1-3&starting-point-node-id=1-3&page-id=1-2&scaling=scale-down';

function carouselSummary(overrides = {}) {
  return {schema:'figma-flow-carousel-summary-v1', graph_sha256:'a'.repeat(64), graph_id:'graph', file_key:'file-a',
    page_id:'1:2', frame_key:'slides', status:'current', initial_state:'one', flow_start_node_id:'1:3',
    states:[{state_id:'one',screen_id:'WEB-one',frame_id:'1:3',title:'Slide One',status:'current'},
      {state_id:'two',screen_id:'WEB-two',frame_id:'1:4',title:'Slide Two',status:'current'}], edges:[], ...overrides};
}

/** Real workspace_host.js with a file holding one verified carousel start frame. */
function hostHarness() {
  const startPage = {id:'1:1', type:'PAGE', selection:[]};
  const page = {id:'1:2', type:'PAGE', selection:[], flowStartingPoints:[{nodeId:'1:3', name:'Carousel'}], async loadAsync() {}};
  const values = {'figma-flow-web-design-id':'graph/WEB-one', 'figma-flow-web-design-sha256':'a'.repeat(64)};
  const frame = {id:'1:3', type:'FRAME', parent:page, getPluginData:key => values[key] || ''};
  const messages = [], external = [];
  const figma = {fileKey:'file-a', currentPage:startPage, ui:{postMessage(message) {messages.push(message);}},
    viewport:{scrollAndZoomIntoView() {}}, async getNodeByIdAsync(id) {return [startPage, page, frame].find(node => node.id === id) || null;},
    async setCurrentPageAsync(next) {this.currentPage = next;}, openExternal(url) {external.push(url);}, showUI() {}};
  const context = vm.createContext({figma, __html__:'HOME'});
  vm.runInContext(`const FLOW_LOCALES = ${JSON.stringify(locales)};
const FLOW_TASKS = [{key:'a',title:'Carousel Task',project:'Studio',kind:'native-edit',revision:'r1',fileKey:'file-a',pageId:'1:2',run() {}}];
` + hostSource, context);
  const summary = context.workspaceStoredCarousel(carouselSummary());
  vm.runInContext(`workspaceState.history.push({taskKey:'a',revision:'r1',operation:'apply',status:'readback',executionId:'exec-1',time:'2026-11-14T00:00:00Z',carousel:${JSON.stringify(summary)}})`, context);
  return {figma, messages, external, send:message => figma.ui.onmessage(message)};
}

function runPanel(entry, env = {}) {
  const built = buildSync({stdin:{contents:entry, resolveDir:panelRoot, loader:'jsx'}, absWorkingDir:panelRoot, bundle:true,
    write:false, platform:'node', format:'cjs', jsx:'automatic', logLevel:'silent',
    define:{'process.env.NODE_ENV':'"production"', __FLOW_DISPLAY_NAME__:JSON.stringify(plugin.extensions['com.openai'].interface.displayName),
      __FLOW_LOCALES__:JSON.stringify(locales)}});
  const result = spawnSync(process.execPath, ['-e', built.outputFiles[0].text], {cwd:panelRoot, encoding:'utf8', env:{...process.env, ...env}});
  assert.equal(result.status, 0, result.stdout + result.stderr);
  return result.stdout;
}

test('host Present reply carries the exact URL it passed to openExternal, and the panel accepts only that file/page/frame link', async () => {
  const h = hostHarness();
  await h.send({type:'workspace-home-ready'});
  const listing = h.messages.filter(message => message.type === 'workspace-tasks').at(-1);
  await h.send({type:'workspace-carousel-present', workspaceSession:listing.workspaceSession, taskKey:'a', revision:'r1',
    executionId:'exec-1', stateId:'one', nodeId:'1:3'});
  const reply = h.messages.at(-1);
  assert.equal(reply.type, 'workspace-carousel-presented');
  assert.equal(reply.url, EXPECTED_URL);
  assert.deepEqual(h.external, [EXPECTED_URL]);
  assert.equal(reply.taskKey, 'a');

  await h.send({type:'workspace-carousel-select', workspaceSession:listing.workspaceSession, taskKey:'a', revision:'r1',
    executionId:'exec-1', stateId:'one', nodeId:'1:3'});
  assert.equal(h.messages.at(-1).type, 'workspace-carousel-selected');
  assert.equal('url' in h.messages.at(-1), false, 'Select must not hand the panel a presentation link');

  const {verifiedPresentationLink} = await import('../panel-ui/src/carouselPresentation.mjs');
  const model = {fileKey:listing.fileKey, tasks:listing.tasks, history:listing.history};
  const accepted = verifiedPresentationLink(reply, model);
  assert.deepEqual(accepted, {taskKey:'a', executionId:'exec-1', url:EXPECTED_URL});

  const reject = (label, message, scope = model) => assert.equal(verifiedPresentationLink(message, scope), null, label);
  const withUrl = url => ({...reply, url});
  reject('other file key', withUrl(EXPECTED_URL.replace('/file-a/', '/file-b/')));
  reject('other page', withUrl(EXPECTED_URL.replace('page-id=1-2', 'page-id=9-9')));
  reject('other frame', withUrl(EXPECTED_URL.replaceAll('1-3', '1-4')));
  reject('http', withUrl(EXPECTED_URL.replace('https:', 'http:')));
  reject('other host', withUrl(EXPECTED_URL.replace('www.figma.com', 'figma.com.evil.example')));
  reject('userinfo', withUrl(EXPECTED_URL.replace('https://', 'https://user@')));
  reject('fragment', withUrl(EXPECTED_URL + '#x'));
  reject('extra param', withUrl(EXPECTED_URL + '&redirect=https://evil.example'));
  reject('duplicate param', withUrl(EXPECTED_URL + '&node-id=1-3'));
  reject('design path', withUrl(EXPECTED_URL.replace('/proto/', '/design/')));
  reject('script url', withUrl('javascript:alert(1)'));
  reject('non-canonical spelling', withUrl(EXPECTED_URL.replace('https://www.figma.com', 'HTTPS://WWW.FIGMA.COM')));
  reject('missing url', {...reply, url:undefined});
  reject('select reply', {...reply, type:'workspace-carousel-selected'});
  reject('unknown execution', {...reply, executionId:'exec-other'});
  reject('other task', {...reply, taskKey:'b'});
  reject('other frame id', {...reply, nodeId:'1:4'});
  reject('active file changed', reply, {...model, fileKey:'file-b'});
  reject('task revision changed', reply, {...model, tasks:model.tasks.map(task => ({...task, revision:'r2'}))});
  reject('carousel changed', reply, {...model, history:model.history.map(event => event.carousel
    ? {...event, carousel:{...event.carousel, status:'changed'}} : event)});
});

test('Present link renders only under the matching current carousel as a native new-tab anchor, in every locale', () => {
  for (const file of ['Workspace.jsx', 'WorkspaceActivity.jsx', 'CarouselPresentLink.jsx', 'carouselPresentation.mjs'])
    assert.doesNotMatch(fs.readFileSync(path.join(panelRoot, 'src', file), 'utf8'), /window\.open\s*\(/, file + ' must not open windows from script');
  const stdout = runPanel(`
import assert from 'node:assert/strict';
import fs from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CarouselOverview, ExecutionFlows } from './src/WorkspaceActivity.jsx';
import { PanelContext } from './src/components.jsx';
globalThis.window = {};
const dictionary = JSON.parse(fs.readFileSync('../figma-bridge/locales/workspace.json', 'utf8'));
const carousel = ${JSON.stringify(carouselSummary())};
const task = {key:'a', title:'Carousel task', kind:'native-edit', revision:'r1', fileKey:'file-a', pageId:'1:2'};
const event = {taskKey:'a', revision:'r1', operation:'apply', status:'readback', executionId:'exec-1', time:'2026-11-14T00:00:00Z', carousel};
const link = {taskKey:'a', executionId:'exec-1', url:${JSON.stringify(EXPECTED_URL)}};
const anchor = '<a class="workspace-carousel-open" href="' + link.url.replaceAll('&', '&amp;') + '" target="_blank" rel="noopener noreferrer">';
for (const locale of ${JSON.stringify(locales)}) {
  const tr = (key, params = {}) => {
    const text = dictionary['workspace.' + key]?.[locale];
    assert.ok(text, locale + ' missing workspace.' + key);
    return Object.entries(params).reduce((value, [name, param]) => value.replace('{' + name + '}', param), text);
  };
  const render = node => renderToStaticMarkup(<PanelContext.Provider value={{locale, t:key => key, setLocale() {}, hostBusy:false}}>{node}</PanelContext.Provider>);
  const home = (presentLink, items = [{task, event, carousel}]) => render(<CarouselOverview items={items} tr={tr} onOpenTask={() => {}} presentLink={presentLink} />);
  const history = (presentLink, flowEvent = event, current = true) => render(<ExecutionFlows flows={[{key:'f', steps:[{event:flowEvent, index:0, current}]}]}
    tasks={[task]} tr={tr} stateText={() => ''} date={() => ''} rememberFocus={() => () => {}} presentLink={presentLink} />);

  for (const [view, html] of [['home', home(link)], ['history', history(link)]]) {
    assert.equal(html.split(anchor).length - 1, 1, locale + ' ' + view + ' renders exactly one native anchor');
    assert.ok(html.includes(anchor + tr('carouselLinkOpen') + '</a>'), locale + ' ' + view + ' open label');
    assert.ok(html.includes('>' + tr('carouselLinkCopy') + '</button>'), locale + ' ' + view + ' copy button');
    assert.ok(html.includes('aria-label="' + tr('carouselLinkGroup') + '"'), locale + ' ' + view + ' group label');
    assert.ok(html.indexOf('workspace-carousel-present') < html.indexOf(anchor), view + ' link sits below the Present button');
  }
  for (const [label, html] of [
    ['no link', home(null)],
    ['other execution', home({...link, executionId:'exec-2'})],
    ['other task', history({...link, taskKey:'b'})],
    ['stale home carousel', home(link, [{task:{...task, revision:'r2'}, event, carousel}])],
    ['stale history step', history(link, event, false)],
    ['changed history carousel', history(link, {...event, carousel:{...carousel, status:'changed'}})],
  ]) assert.ok(!html.includes('workspace-carousel-link'), locale + ' ' + label);
}
console.log('RENDER_OK');
`);
  assert.match(stdout, /RENDER_OK/);
});

test('Workspace shows the host-verified link after a real Present click, drops forged links, and copies by selecting the URL', () => {
  const stdout = runPanel(`
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import Workspace from './src/Workspace.jsx';
import { Shell, PanelContext } from './src/components.jsx';

class Node {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.nodeType = tag === '#text' ? 3 : tag === '#comment' ? 8 : 1;
    this.ownerDocument = doc; this.childNodes = []; this.parentNode = null; this.attributes = {}; this.listeners = new Map(); this.style = {}; this.text = ''; }
  get nodeName() { return this.tagName; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes.at(-1) || null; }
  get nextSibling() { const siblings = this.parentNode?.childNodes || []; return siblings[siblings.indexOf(this) + 1] || null; }
  get textContent() { return this.nodeType === 1 ? this.childNodes.map(child => child.nodeType === 8 ? '' : child.textContent).join('') : this.text; }
  set textContent(value) { if (this.nodeType !== 1) { this.text = String(value ?? ''); return; }
    this.childNodes = []; if (value !== '' && value != null) this.appendChild(this.ownerDocument.createTextNode(String(value))); }
  get nodeValue() { return this.text; }
  set nodeValue(value) { this.text = String(value ?? ''); }
  get className() { return this.attributes.class || ''; }
  set className(value) { this.attributes.class = String(value); }
  get value() { return this.attributes.value ?? this.textContent; }
  set value(value) { this.attributes.value = String(value ?? ''); }
  get options() { return this.querySelectorAll('option'); }
  appendChild(child) { child.parentNode?.removeChild(child); child.parentNode = this; this.childNodes.push(child); return child; }
  insertBefore(child, before) { if (!before) return this.appendChild(child); child.parentNode?.removeChild(child);
    child.parentNode = this; this.childNodes.splice(this.childNodes.indexOf(before), 0, child); return child; }
  removeChild(child) { this.childNodes.splice(this.childNodes.indexOf(child), 1); child.parentNode = null; return child; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(fn); }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  dispatchEvent(event) { event.target ||= this; event.currentTarget = this; for (const fn of this.listeners.get(event.type) || []) fn(event);
    if (this.parentNode && !event.cancelBubble) this.parentNode.dispatchEvent(event); return true; }
  click() { this.dispatchEvent({type:'click', bubbles:true, cancelBubble:false, preventDefault() {}, stopPropagation() { this.cancelBubble = true; }}); }
  querySelectorAll(selector) {
    const found = [], match = node => selector.startsWith('.') ? node.className.split(/\\s+/).includes(selector.slice(1))
      : selector.startsWith('#') ? node.attributes.id === selector.slice(1) : node.tagName.toLowerCase() === selector;
    const walk = node => node.childNodes.forEach(child => { if (child.nodeType === 1) { if (match(child)) found.push(child); walk(child); } });
    walk(this); return found;
  }
}
const windowListeners = new Map(), clipboard = {result:true, commands:[], selected:null};
const doc = {nodeType:9, defaultView:globalThis, activeElement:null,
  createElement(tag) { return new Node(tag, this); }, createElementNS(_ns, tag) { return new Node(tag, this); },
  createTextNode(text) { const node = new Node('#text', this); node.text = String(text); return node; },
  createComment(text) { const node = new Node('#comment', this); node.text = String(text); return node; },
  addEventListener() {}, removeEventListener() {},
  createRange() { return {selectNodeContents(node) { this.node = node; }}; },
  execCommand(command) { clipboard.commands.push(command); return clipboard.result; }};
doc.documentElement = doc.createElement('html');
globalThis.document = doc;
globalThis.HTMLElement = Node; globalThis.SVGElement = Node; globalThis.HTMLIFrameElement = class {};
globalThis.window = {
  addEventListener(type, fn) { if (!windowListeners.has(type)) windowListeners.set(type, new Set()); windowListeners.get(type).add(fn); },
  removeEventListener(type, fn) { windowListeners.get(type)?.delete(fn); }, setInterval() { return 1; }, clearInterval() {},
  open() { throw new Error('window.open must not be used'); },
  getSelection() { return {removeAllRanges() { clipboard.selected = null; }, addRange(range) { clipboard.selected = range.node; }}; },
};

const copy = {...JSON.parse(fs.readFileSync('../figma-bridge/locales/workspace.json', 'utf8')), ...JSON.parse(fs.readFileSync('../figma-bridge/locales/common.json', 'utf8'))};
const t = (key, params = {}) => Object.entries(params).reduce((text, [name, value]) => text.replace('{' + name + '}', value), copy[key]?.en || key);

const startPage = {id:'1:1', type:'PAGE', selection:[]};
const page = {id:'1:2', type:'PAGE', selection:[], flowStartingPoints:[{nodeId:'1:3', name:'Carousel'}], async loadAsync() {}};
const values = {'figma-flow-web-design-id':'graph/WEB-one', 'figma-flow-web-design-sha256':'a'.repeat(64)};
const frame = {id:'1:3', type:'FRAME', parent:page, getPluginData:key => values[key] || ''};
const hostMessages = [], external = [];
const figma = {fileKey:'file-a', currentPage:startPage, ui:{postMessage(message) { hostMessages.push(message); }},
  viewport:{scrollAndZoomIntoView() {}}, async getNodeByIdAsync(id) { return [startPage, page, frame].find(node => node.id === id) || null; },
  async setCurrentPageAsync(next) { this.currentPage = next; }, openExternal(url) { external.push(url); }, showUI() {}};
const host = vm.createContext({figma, __html__:'HOME'});
vm.runInContext(\`const FLOW_LOCALES = ${JSON.stringify(locales)};
const FLOW_TASKS = [{key:'a',title:'Carousel Task',project:'Studio',kind:'native-edit',revision:'r1',fileKey:'file-a',pageId:'1:2',run() {}}];
\` + fs.readFileSync(process.env.HOST_SOURCE_PATH, 'utf8'), host);
const summary = host.workspaceStoredCarousel(${JSON.stringify(carouselSummary())});
vm.runInContext(\`workspaceState.history.push({taskKey:'a',revision:'r1',operation:'apply',status:'readback',executionId:'exec-1',time:'2026-11-14T00:00:00Z',carousel:\${JSON.stringify(summary)}})\`, host);

const sent = [], container = doc.createElement('div');
const root = createRoot(container, {onUncaughtError(error) { throw error; }});
flushSync(() => root.render(<PanelContext.Provider value={{locale:'en', t, setLocale() {}, hostBusy:false}}>
  <Workspace model={{}} locale="en" t={t} send={message => sent.push(message)} Shell={Shell} /></PanelContext.Provider>));
const deliver = message => flushSync(() => { for (const fn of windowListeners.get('message') || []) fn({data:{pluginMessage:message}}); });
const links = () => container.querySelectorAll('a').filter(node => node.getAttribute('target') === '_blank');

async function run() {
  await new Promise(resolve => setTimeout(resolve, 10));
  await figma.ui.onmessage(sent[0]);
  const listing = hostMessages.filter(message => message.type === 'workspace-tasks').at(-1);
  deliver(listing);
  assert.equal(links().length, 0, 'no link before the host verifies a Present request');

  for (const view of ['home', 'history']) {
    if (view === 'history') flushSync(() => container.querySelectorAll('#tab-history')[0].click());
    const scope = container.querySelectorAll(view === 'home' ? '.workspace-carousel-overview' : '.workspace-flows')[0];
    flushSync(() => scope.querySelectorAll('.workspace-carousel-present')[0].click());
    assert.equal(links().length, 0, view + ': clicking Present clears any previous link');
    await figma.ui.onmessage(sent.at(-1));
    const reply = hostMessages.at(-1);
    assert.equal(reply.type, 'workspace-carousel-presented');
    deliver(reply);
    const shown = links();
    assert.equal(shown.length, 1, view + ': exactly one verified link');
    assert.equal(shown[0].getAttribute('href'), external.at(-1));
    assert.equal(shown[0].getAttribute('href'), reply.url);
    assert.equal(shown[0].getAttribute('rel'), 'noopener noreferrer');
    assert.equal(shown[0].textContent, t('workspace.carouselLinkOpen'));
    assert.equal(scope.querySelectorAll('.workspace-carousel-notice')[0].textContent, t('workspace.carouselPresented'));

    clipboard.result = view === 'home';
    flushSync(() => scope.querySelectorAll('.workspace-carousel-link')[0].querySelectorAll('button')[0].click());
    assert.deepEqual(clipboard.commands.slice(-1), ['copy']);
    assert.equal(clipboard.selected?.textContent, reply.url, 'copy selects the visible verified URL');
    assert.equal(scope.querySelectorAll('.workspace-carousel-link-status')[0].textContent,
      t(view === 'home' ? 'workspace.carouselLinkCopied' : 'workspace.carouselLinkCopyManual'));
  }

  const verified = links()[0].getAttribute('href');
  deliver({...hostMessages.at(-1), url:'https://evil.example/proto/file-a/SaaS'});
  assert.equal(links().length, 0, 'a reply with an unverified URL removes the link instead of rendering it');
  deliver({...hostMessages.at(-1), workspaceSession:'forged'});
  assert.equal(links().length, 0, 'a forged-session reply is ignored');
  deliver(hostMessages.at(-1));
  assert.equal(links()[0].getAttribute('href'), verified);
  deliver({type:'workspace-carousel-error', workspaceSession:listing.workspaceSession, message:'Carousel readback is stale'});
  assert.equal(links().length, 0, 'a host error clears the link');
  console.log('WORKSPACE_OK');
}
run().catch(error => { console.error(error); process.exit(1); });
`, {HOST_SOURCE_PATH:path.join(root, 'figma-bridge/workspace_host.js')});
  assert.match(stdout, /WORKSPACE_OK/);
});
