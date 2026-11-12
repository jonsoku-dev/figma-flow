/* Frozen API-shaped scroll oracle; live Figma acceptance is separate. No production function is replaced. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {readNativeSemantics, requireFullNativeRead} = require('../figma-bridge/native_semantic_read.js');
const runtime = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
const enumValues = {horizontal: 'HORIZONTAL', vertical: 'VERTICAL', both: 'BOTH', none: 'NONE'};

function host() {
  let sequence = 0;
  class Node {
    constructor(type) {
      Object.assign(this, {id: String(++sequence), type, name: type, children: [], parent: null,
        x: 0, y: 0, width: 20, height: 20, data: {}, reactions: [], annotations: []});
      if (type === 'FRAME') Object.assign(this, {clipsContent: false, layoutMode: 'NONE', fills: [], _overflow: 'NONE', writes: [], reads: 0});
    }
    // Prototype accessor models the real API getter, which JSON.stringify(node) cannot capture.
    get overflowDirection() {this.reads++; return this._overflow;}
    set overflowDirection(value) {
      assert.equal(this.type, 'FRAME'); assert(Object.values(enumValues).includes(value));
      this.writes.push(value); this._overflow = value;
    }
    getPluginData(key) {return this.data[key] || '';}
    setPluginData(key, value) {this.data[key] = String(value);}
    resize(width, height) {assert(width > 0 && height > 0); this.width = width; this.height = height;}
    appendChild(node) {this.insertChild(this.children.length, node);}
    insertChild(index, node) {if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = this; this.children.splice(index, 0, node);}
    findAll(predicate) {return this.children.flatMap(child => [...(predicate(child) ? [child] : []), ...child.findAll(predicate)]);}
    async loadAsync() {}
    remove() {if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null;}
  }
  const figma = {showUI() {}, ui: {postMessage() {}}, createFrame: () => new Node('FRAME'),
    variables: {async getLocalVariableCollectionsAsync() {return [];}}};
  const context = vm.createContext({DRAFT: {}, figma, __html__: '', console, readNativeSemantics, requireFullNativeRead});
  vm.runInContext(runtime, context);
  const page = new Node('PAGE');
  return {context, figma, page, Node};
}

const declaration = (scroll = 'horizontal') => ({key: 'table', kind: 'frame', parent: null,
  children: ['cell'], box: [10, 10, 370, 300], clip: true, scroll});
function placed(scroll = 'horizontal') {
  const h = host(), screen = new h.Node('FRAME'), cell = new h.Node('RECTANGLE');
  h.page.appendChild(screen); screen.resize(390, 800); screen.clipsContent = true;
  screen.setPluginData('semanticKey', 'a.mobile.idle');
  screen.appendChild(cell); cell.x = 800; cell.y = 30; cell.resize(80, 20); cell.setPluginData('semanticKey', 'a.mobile.idle.cell');
  const declarations = [declaration(scroll)];
  h.context.placeDeclaredLayerParents(screen, declarations, id => id === 'cell' ? cell : null, 'a.mobile.idle.');
  return {...h, screen, cell, declarations, container: cell.parent};
}

function packet(container) {
  const font = {family: 'Inter', style: 'Regular'};
  const layout = {width: 390, height: 800, layers: [{id: 'cell', kind: 'rect', x: 30, y: 30, w: 80, h: 20}],
    control_boxes: {}, containers: [container]};
  return {font, draft: {candidates: [{id: 'a', fonts: {body: font}, control_styles: {},
    prototype: {states: [{id: 'idle'}], bindings: []}, state_layouts: {desktop: {idle: layout}, mobile: {idle: layout}}}]}};
}

test('actual preflight rejects invalid scroll enums and every non-clipped/non-Frame declaration', () => {
  const good = packet(declaration());
  assert.deepEqual(plain(host().context.preflightDraft(good.draft, [good.font])), []);
  const changes = [{scroll: 'HORIZONTAL'}, {scroll: 'diagonal'}, {scroll: null}, {scroll: true},
    {clip: false}, {clip: undefined}, {kind: 'group', clip: undefined},
    {kind: 'auto-layout', layout: {direction: 'VERTICAL', gap: 0, padding: [0, 0, 0, 0], width: 'fixed', height: 'fixed'}}];
  for (const change of changes) {
    const container = {...declaration(), ...change};
    if (change.clip === undefined && Object.hasOwn(change, 'clip')) delete container.clip;
    if (container.kind === 'group') {delete container.clip; delete container.box;}
    const {font, draft} = packet(container);
    const problems = host().context.preflightDraft(draft, [font]);
    assert(problems.some(problem => /scroll|clip|frame|container/i.test(problem)), JSON.stringify(change) + ': malformed scroll reached authoring');
  }
});

test('ordinary importer uses the native overflow setter and real semantic getter for all declared modes', async () => {
  for (const [scroll, native] of Object.entries(enumValues)) {
    const h = placed(scroll);
    assert.equal(h.container.type, 'FRAME'); assert.equal(h.container.clipsContent, true);
    assert.equal(h.container.overflowDirection, native, scroll + ': placement must configure native overflow');
    if (scroll !== 'none') assert(h.container.writes.includes(native), 'native property setter was never called');
    const beforeReads = h.container.reads;
    const raw = await readNativeSemantics(h.figma, h.page);
    const row = raw.nodes.find(node => node.id === h.container.id);
    assert.equal(row.overflowDirection, native, 'full reader must copy API-backed overflowDirection');
    assert(h.container.reads > beforeReads, 'full read must execute the native getter');
    const links = await h.context.readDeclaredContainerLinks(h.page, h.screen, h.declarations, 'a.mobile.idle.');
    assert.equal(links.containers[0].overflowDirection, native);
    assert.deepEqual(plain(links.leaves[0].box), {x: 800, y: 30, w: 80, h: 20}, 'readback must retain full raw table geometry');
  }
});

test('full semantic read executes and preserves the actual API-backed overflow getter', async () => {
  const h = host(), frame = new h.Node('FRAME'); h.page.appendChild(frame);
  frame.overflowDirection = 'HORIZONTAL';
  const before = frame.reads;
  const raw = await readNativeSemantics(h.figma, h.page);
  assert.equal(raw.nodes.find(row => row.id === frame.id).overflowDirection, 'HORIZONTAL');
  assert(frame.reads > before, 'the real reader must execute the native getter');
});

test('normal readback rejects actual clip/overflow drift and unavailable overflow getter', async () => {
  for (const change of ['clip', 'axis', 'none', 'missing']) {
    const h = placed();
    // Supply an observed native state independently of the importer being tested above.
    h.container.overflowDirection = 'HORIZONTAL';
    if (change === 'clip') h.container.clipsContent = false;
    if (change === 'axis') h.container.overflowDirection = 'VERTICAL';
    if (change === 'none') h.container.overflowDirection = 'NONE';
    if (change === 'missing') Object.defineProperty(h.container, 'overflowDirection', {get() {throw Error('native getter unavailable');}});
    await assert.rejects(h.context.readDeclaredContainerLinks(h.page, h.screen, h.declarations, 'a.mobile.idle.'),
      /clip differs|overflow|scroll|native getter unavailable/i, change + ': readback admitted native property drift');
  }
});

function geometry(scroll = 'horizontal', {x = 800, y = 30, ordinary = false, rootOnly = false} = {}) {
  const h = host(), candidate = {id: 'a', fonts: {body: {family: 'Inter', style: 'Regular'}},
    prototype: {states: [{id: 'idle'}], bindings: []}, state_layouts: {}};
  for (const [viewport, frameY] of [['desktop', 0], ['mobile', 1000]]) {
    const key = 'a.' + viewport + '.idle', screen = new h.Node('FRAME');
    h.page.appendChild(screen); screen.resize(390, 800); screen.y = frameY; screen.clipsContent = true;
    screen.setPluginData('semanticKey', key);
    const layer = {id: 'cell', kind: 'text', value: 'cell', x, y, w: 80, h: 20, size: 16, leading: 20};
    const container = declaration(scroll);
    if (ordinary) delete container.scroll;
    const state = {width: 390, height: 800, layers: [layer], control_boxes: {}, containers: rootOnly ? [] : [container]};
    candidate.state_layouts[viewport] = {idle: state};
    const parent = rootOnly ? screen : new h.Node('FRAME');
    if (!rootOnly) {
      screen.appendChild(parent); parent.x = 10; parent.y = 10; parent.resize(370, 300);
      parent.clipsContent = true; parent.overflowDirection = ordinary ? 'NONE' : enumValues[scroll];
      parent.setPluginData('semanticKey', key + '.table');
    } else screen.overflowDirection = 'BOTH';
    const cell = new h.Node('TEXT'); parent.appendChild(cell);
    Object.assign(cell, {x: x - (rootOnly ? 0 : 10), y: y - (rootOnly ? 0 : 10), width: 80, height: 20,
      characters: 'cell', fontName: candidate.fonts.body, fontSize: 16, textAutoResize: 'HEIGHT', textAlignHorizontal: 'LEFT',
      lineHeight: {unit: 'PIXELS', value: 20}, letterSpacing: {unit: 'PIXELS', value: 0}});
    cell.setPluginData('semanticKey', key + '.cell');
  }
  return {...h, candidate, validate() {return h.context.validateDraftGeometry(h.page, [candidate], false);}};
}

test('actual native geometry permits only declared axes and keeps raw coordinates', () => {
  for (const [scroll, box] of [['horizontal', {x: 800}], ['vertical', {x: 30, y: 900}], ['both', {x: 800, y: 900}]]) {
    const h = geometry(scroll, box), cells = h.page.findAll(node => node.type === 'TEXT');
    const before = cells.map(node => ({x: node.x, y: node.y, width: node.width, height: node.height}));
    assert.doesNotThrow(() => h.validate(), scroll + ': declared clipped scroll must be admitted');
    assert.deepEqual(cells.map(node => ({x: node.x, y: node.y, width: node.width, height: node.height})), before);
    cells[0].x += 10;
    assert.throws(() => h.validate(), /geometry differs/, 'scroll permission must not suppress authored geometry drift');
  }
});

test('root clipping, ordinary frames and wrong axes cannot excuse accidental off-frame content', () => {
  for (const [scroll, options] of [['horizontal', {y: 900}], ['vertical', {}], ['none', {}],
    ['horizontal', {ordinary: true}], ['horizontal', {rootOnly: true}]]) {
    assert.throws(() => geometry(scroll, options).validate(), /off-frame/, JSON.stringify({scroll, options}));
  }
});

test('nested scroll clips apply in ancestry order instead of unioning axis permissions', () => {
  const h = geometry('vertical', {x: 800, y: 900});
  for (const viewport of ['desktop', 'mobile']) {
    const key = 'a.' + viewport + '.idle', state = h.candidate.state_layouts[viewport].idle;
    const outer = h.page.findAll(node => node.getPluginData('semanticKey') === key + '.table')[0];
    const cell = outer.children[0], inner = new h.Node('FRAME');
    outer.appendChild(inner); inner.resize(370, 1000); inner.clipsContent = true; inner.overflowDirection = 'HORIZONTAL';
    inner.setPluginData('semanticKey', key + '.inner'); inner.appendChild(cell);
    state.containers[0].children = ['inner'];
    state.containers.push({key: 'inner', kind: 'frame', parent: 'table', children: ['cell'],
      box: [0, 0, 370, 1000], clip: true, scroll: 'horizontal'});
  }
  assert.doesNotThrow(() => h.validate());
  for (const viewport of ['desktop', 'mobile']) {
    const key = 'a.' + viewport + '.idle', state = h.candidate.state_layouts[viewport].idle;
    state.containers[0].scroll = 'horizontal'; state.containers[1].scroll = 'vertical';
    h.page.findAll(node => node.getPluginData('semanticKey') === key + '.table')[0].overflowDirection = 'HORIZONTAL';
    h.page.findAll(node => node.getPluginData('semanticKey') === key + '.inner')[0].overflowDirection = 'VERTICAL';
  }
  assert.throws(() => h.validate(), /off-frame|clip|scroll/, 'inner wrong-axis clip cannot inherit outer permission');
});
