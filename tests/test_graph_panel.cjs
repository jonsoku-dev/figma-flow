const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const os = require('node:os');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const template = execFileSync(process.env.PYTHON || 'python3', ['-B', '-c', 'import sys;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"tools"));from panel_components import render_components;print(render_components((Path(sys.argv[1])/"figma-bridge/graph-panel.html").read_text(),"graph"))', root], {encoding: 'utf8'});
const components = fs.readFileSync(path.join(root, 'figma-bridge/panel_components.js'), 'utf8');
const translations={...JSON.parse(fs.readFileSync(path.join(root,'figma-bridge/locales/workspace.json'))),...JSON.parse(fs.readFileSync(path.join(root,'figma-bridge/locales/graph.json')))};
const translate=(locale,key,params={})=>(translations[key]?.[locale]||key).replace(/\{(\w+)\}/g,(_,name)=>params[name]??'{'+name+'}');
const script = [...template.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
function panel(mode = 'sync', extra = {}, locale='ko') {
  const listeners=new Map();
  const posted = [], downloads = [], urls = new Map(), elements = new Map();
  class Element {
    constructor(tag) {this.tagName = tag; this.children = []; this.textContent = ''; this.dataset = {}; this.style={}; this.disabled = false; this.hidden = false;}
    appendChild(child) {this.children.push(child); return child;}
    replaceChildren(){this.children=[];}
    setAttribute(name, value) {this[name] = value;}
    removeAttribute(name) {delete this[name];}
    addEventListener(name, handler) {this[name] = handler;}
    focus() {this.focused = true;}
    remove() {}
    click() {if (this.disabled) return; if (this.tagName === 'a') downloads.push({name: this.download, blob: urls.get(this.href)}); else this.onclick?.();}
  }
  for (const match of template.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
    const element = new Element(match[0].match(/^<([^\s>]+)/)[1]);
    element.disabled = /\bdisabled\b/.test(match[0]); element.hidden = /\bhidden\b/.test(match[0]);
    elements.set(match[1], element);
  }
  const config = {mode, session: 'test-session', file_key: '</script><unsafe>', page_id: 'page', pages: ['page', 'other'],
    collection_id: 'collection', graph_sha256: 'a'.repeat(64), main_ids: ['main'], instance_ids: ['instance'],
    components: [{id: '<unsafe>', fields: ['fontSize'], mains: 1, instances: 1}], changes: [],
    stats: {tokens: 2, components: 1, mains: 1, instances: 1, updates: 1, creates: 0, bindings: 1}, ...extra};
  elements.get('graph-panel-config').textContent = JSON.stringify(config);
  const parent = {postMessage(message) {posted.push(message.pluginMessage);}};
  const context = {document: {documentElement:{dataset:{}},getElementById: id => elements.get(id), createElement: tag => new Element(tag), body: new Element('body')},
    FlowUI:{get locale(){return locale;},t:(key,params)=>translate(locale,key,params),apply(){}},addEventListener(type,handler){const previous=listeners.get(type);listeners.set(type,previous?(...args)=>{previous(...args);handler(...args);}:handler);},parent, Blob, URL: {createObjectURL(blob) {const key = 'blob:' + urls.size; urls.set(key, blob); return key;}, revokeObjectURL() {}}, setTimeout() {}};
  context.window = context;
  vm.runInNewContext(components+'\n'+script, context);
  return {elements, posted, downloads, locale(code){locale=code;listeners.get('flow:locale')();},key(key){listeners.get('keydown')({key,preventDefault(){}});},receive(message, source = parent) {context.onmessage({source, data: {pluginMessage: {session: config.session, ...message}}});}};
}

test('sync asks for explicit scope confirmation, then sends one apply and blocks duplicate work', () => {
  const p = panel();
  assert.equal(p.elements.get('evidence-section').hidden, true);
  assert.equal(p.elements.get('status').hidden, true);
  p.elements.get('apply').click(); assert.equal(p.posted.length, 0);
  p.elements.get('review').click(); assert.equal(p.elements.get('confirmation').hidden, false);
  assert.match(p.elements.get('impact-summary').textContent, /값 변경 1개/);
  assert.equal(p.elements.get('impact').children[0].textContent, '<unsafe>: 글자 크기 · 메인 1개 / 인스턴스 1개');
  assert.equal(p.elements.get('review')['aria-expanded'], 'true');
  p.elements.get('cancel').click();
  assert.equal(p.elements.get('confirmation').hidden, true);
  assert.equal(p.elements.get('review').focused, true);
  assert.equal(p.posted.length, 0);
  p.elements.get('review').click();
  p.elements.get('apply').click(); p.elements.get('apply').click(); p.elements.get('read').click();
  assert.equal(JSON.stringify(p.posted), '[{"type":"apply","session":"test-session"}]');
  assert.equal(p.elements.get('status').dataset.state, 'busy');
  assert.equal(p.elements.get('read').disabled, true);
  assert.equal(p.elements.get('status')['aria-busy'], 'true');
});

test('actual readback downloads unchanged, stays available after errors, and reports recovery conflicts', async () => {
  const p = panel();
  p.elements.get('read').click();
  const actual = {schema: 'figma-flow-graph-token-readback-v1', tokens: [{key: 'size', resolved: 19}], components: []};
  p.receive({operation: 'read', readback: actual});
  assert.equal(p.elements.get('status').dataset.state, 'success');
  assert.deepEqual(JSON.parse(await p.downloads[0].blob.text()), actual);
  p.receive({error: 'Read failed'});
  assert.equal(p.elements.get('status').dataset.state, 'error');
  assert.equal(p.elements.get('download').disabled, false);
  p.elements.get('download').click();
  assert.deepEqual(JSON.parse(await p.downloads[1].blob.text()), actual);
  const failure = {schema: actual.schema, status: 'rollback-conflict', error: 'Changed externally', rollback_conflicts: [{kind: 'binding-changed', node_id: 'main'}]};
  p.receive({error: failure.error, readback: failure, rollback_conflicts: failure.rollback_conflicts});
  assert.equal(p.elements.get('status-title').textContent, '복구 확인이 필요합니다');
  assert.deepEqual(JSON.parse(await p.downloads[2].blob.text()), failure);
  assert.match(p.elements.get('report').textContent, /binding-changed/);
});

test('discovery only reads, accepts Figma relay frames and rejects unrelated sessions', () => {
  const p = panel('discovery');
  assert.equal(p.elements.get('review').hidden, true);
  p.elements.get('apply').click(); assert.equal(p.posted.length, 0);
  p.elements.get('read').click(); assert.equal(JSON.stringify(p.posted), '[{"type":"read","session":"test-session"}]');
  p.receive({session: 'unrelated', readback: {nodes: [], variables: []}}, {});
  assert.equal(p.elements.get('status').dataset.state, 'busy');
  p.receive({readback: {schema: 'figma-flow-graph-native-discovery-v1', nodes: [{id: 'actual'}], variables: [{id: 'variable'}]}}, {});
  assert.match(p.elements.get('status-body').textContent, /노드 1개 · 변수 1개/);
  assert.equal(p.downloads[0].name, 'graph-native-discovery.json');
});

test('packaged sync host uses themed HTML and returns downloadable failure evidence on preflight errors', async () => {
  const shown = [], messages = [];
  const figma = {fileKey: 'actual-file', currentPage: {id: 'actual-page'}, showUI(...args) {shown.push(args);}, ui: {postMessage(message) {messages.push(message);}}};
  const context = {figma, GRAPH_PANEL_SESSION: 'host-session', __html__: '<html>packaged panel</html>', GRAPH_SYNC_PLAN: {schema: 'figma-flow-graph-token-sync-v1', graph_sha256: 'a'.repeat(64), file_key: 'expected-file', page_id: 'expected-page', collection_id: 'expected-collection'}};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'figma-bridge/graph_token_sync.js'), 'utf8'), context);
  assert.equal(shown[0][0], context.__html__); assert.equal(shown[0][1].themeColors, true); assert.equal(shown[0][1].height, 470);
  const pending = figma.ui.onmessage({type: 'read', session: 'host-session'});
  await figma.ui.onmessage({type: 'read', session: 'host-session'}); await pending;
  assert.equal(messages.length, 2);
  assert.equal(messages[0].state, 'busy');
  assert.equal(messages[1].readback.status, 'failed');
  assert.equal(messages[1].readback.file_key, 'actual-file');
  assert.equal(messages[1].readback.expected_scope.file_key, 'expected-file');
  assert.match(messages[1].readback.error, /wrong file/);
  assert.equal(messages[1].readback.tokens, undefined);
  Object.defineProperty(figma, 'fileKey', {get() {throw Error('fileKey unavailable without private API');}});
  await figma.ui.onmessage({type: 'read', session: 'host-session'});
  assert.equal(messages.at(-1).readback.status, 'failed');
  assert.equal(messages.at(-1).readback.file_key, null);
  assert.match(messages.at(-1).readback.error, /private API/);
  await figma.ui.onmessage({type: 'read', session: 'host-session'});
  assert.equal(messages.length, 6);
  Object.defineProperty(figma, 'fileKey', {get() {return undefined;}});
  await figma.ui.onmessage({type: 'read', session: 'host-session'});
  assert.equal(messages.at(-1).readback.status, 'failed');
  assert.equal(messages.at(-1).readback.file_key, null);
});

test('normal discovery bundle is self-contained and preserves failure evidence from actual scope checks', async () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'graph-panel-'));
  try {
    const out = path.join(temporary, 'discovery');
    execFileSync('python3', ['tools/graph_sync.py', 'discover', '--file-key', 'expected', '--page-id', 'page', '--out', out], {cwd: root});
    const manifest = JSON.parse(fs.readFileSync(path.join(out, 'manifest.json')));
    const html = fs.readFileSync(path.join(out, manifest.ui), 'utf8');
    const session = JSON.parse(html.match(/<script id="graph-panel-config" type="application\/json">(.*?)<\/script>/s)[1]).session;
    assert.equal(manifest.enablePrivatePluginApi, true);
    assert.match(html, /body class="panel"/); assert.match(html, /Figma Flow/);
    assert.doesNotMatch(html, /FIGMA_FLOW_PANEL_CSS|__GRAPH_PANEL_CONFIG__|<script src=|<link /);
    const shown = [], messages = [];
    const figma = {fileKey: 'actual', currentPage: {id: 'page'}, showUI(...args) {shown.push(args);}, ui: {postMessage(message) {messages.push(message);}}};
    vm.runInNewContext(fs.readFileSync(path.join(out, 'code.js'), 'utf8'), {figma, __html__: html});
    assert.equal(shown[0][0], html); assert.equal(shown[0][1].themeColors, true); assert.equal(shown[0][1].height, 390);
    await figma.ui.onmessage({type: 'read', session});
    assert.equal(messages[1].readback.status, 'failed');
    assert.equal(messages[1].readback.fileKey, 'actual');
    assert.equal(messages[1].readback.expected_scope.file_key, 'expected');
    assert.equal(messages[1].readback.nodes, undefined);
    Object.defineProperty(figma, 'fileKey', {get() {throw Error('fileKey unavailable');}});
    await figma.ui.onmessage({type: 'read', session});
    assert.equal(messages.at(-1).readback.fileKey, null);
    assert.equal(messages.at(-1).readback.status, 'failed');
    assert.match(messages.at(-1).readback.error, /fileKey unavailable/);
  } finally {fs.rmSync(temporary, {recursive: true, force: true});}
});

for(const locale of ['ko','en','ja'])test('localized visual confirmation '+locale,()=>{
  const changes=[{name:'color/primary',before:'{"r":0,"g":0,"b":0}',after:'"#abcdef"'},
    {name:'type/button',before:'14',after:'18'},{name:'space/padding',before:'16',after:'24'}];
  const p=panel('sync',{changes},locale);
  assert.equal(p.elements.get('title').textContent,translations['graph.title'][locale]);
  p.elements.get('review').click();
  const cards=p.elements.get('impact').children.filter(c=>c.className==='change-card');
  assert.equal(cards.length,3);
  assert.equal(cards[0].children[1].children[0].children[1].style.backgroundColor,'rgba(0,0,0,1)');
  assert.ok(cards[0].children[1].children[0].children[1]['aria-label'].includes(changes[0].before));
  assert.equal(cards[1].children[1].children[1].children[1].style.fontSize,'18px');
  assert.equal(cards[2].children[1].children[1].children[1].style.width,'24px');
  assert.equal(cards[2].children[1].children[1].children[2].textContent,'24');
  p.key('Escape');assert.equal(p.elements.get('confirmation').hidden,true);
  p.elements.get('read').click();p.receive({readback:{nodes:[],variables:[]}});
  p.locale(locale==='en'?'ja':'en');
  assert.equal(p.elements.get('download').disabled,false);assert.equal(p.posted.length,1);
});
test('graph catalogue has all three locales and static labels',()=>{
  for(const [key,values]of Object.entries(translations))for(const locale of ['ko','en','ja'])assert.ok(values[locale],key+' '+locale);
  for(const match of template.matchAll(/data-i18n(?:-[a-z]+)?="([^"]+)"/g))assert.ok(translations[match[1]],match[1]);
  assert.match(template,/data-flow-view="graph"/);assert.match(template,/@media\(max-width:340px\)/);
});
