/* API-shaped native fixtures. Live Figma execution is a separate acceptance step. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const root = path.join(__dirname, '..');
const python = process.env.PYTHON || 'python3.13';
const runtime = fs.readFileSync(path.join(root, 'figma-bridge/direction_review.js'), 'utf8');
const prelude = execFileSync(python, ['-B', '-c', 'import sys; sys.path.insert(0,sys.argv[1]); from specification_contract import spec_label_prelude; print(spec_label_prelude())', path.join(root, 'tools')], {encoding: 'utf8'});
const spec = JSON.parse(execFileSync(python, ['-B', '-c', 'import sys,json; sys.path[:0]=sys.argv[1:]; from test_specification_contract import fixture; from specification_contract import derive_specifications; g=fixture(); g["nodes"][1]["annotation"]["control_id"]="deliver"; print(json.dumps(derive_specifications(g)[1]))', path.join(root, 'tools'), path.join(root, 'tests')], {encoding: 'utf8'}));
let sequence = 0;
class Node {
  constructor(type) {Object.assign(this, {id: String(++sequence), type, name: type, children: [], data: {}, annotations: [], x: 0, y: 0, width: 100, height: 20, visible: true});}
  appendChild(node) {if (node.parent) node.parent.children = node.parent.children.filter(n => n !== node); node.parent = this; this.children.push(node);}
  setPluginData(key, value) {this.data[key] = value;}
  getPluginData(key) {return this.data[key] || '';}
  async loadAsync() {}
  findAll(test) {return this.children.flatMap(n => [...(test(n) ? [n] : []), ...n.findAll(test)]);}
  findOne(test) {return this.findAll(test)[0] || null;}
  resize(width, height) {this.width = width; this.height = height;}
  setRangeHyperlink(start, end, link) {this.link = link;}
  getRangeHyperlink() {return this.link || null;}
  getRangeBoundVariable() {return null;}
  getStyledTextSegments() {return [];}
  async getMainComponentAsync() {return this.main;}
  remove() {this.parent.children = this.parent.children.filter(n => n !== this);}
}
function host() {
  const figma = {fileKey: 'file-key', showUI() {}, ui: {postMessage() {}},
    createFrame: () => new Node('FRAME'), createText: () => new Node('TEXT'), loadFontAsync: async () => {},
    variables: {getLocalVariableCollectionsAsync: async () => []}};
  const context = vm.createContext({figma, DRAFT: {candidates: []}, __html__: ''});
  vm.runInContext(prelude, context);
  for (const file of ['native_annotations.js', 'design_note_board.js', 'native_semantic_read.js', 'direction_review.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'figma-bridge', file), 'utf8'), context);
  }
  return context;
}
const plain = value => JSON.parse(JSON.stringify(value));
function candidate() {
  return {id: 'app', prototype: {states: [{id: 'one', screen: 'screen'}], bindings: []}, entry_state: 'one', entry_states: ['one'],
    state_layouts: {desktop: {one: {control_boxes: {}, layers: [], product_buttons: {deliver: {box: [10, 10, 200, 48], variant: 'Primary', label: 'Deliver', specification_id: 'deliver'}}}}},
    control_styles: {desktop: {Primary: {}}}, specifications: {deliver: spec}};
}

test('explicit entries create native starts in both viewports; omitted entries keep desktop default', () => {
  const h = host(), c = candidate(), frames = new Map();
  for (const viewport of ['desktop', 'mobile']) for (const state of ['one', 'two']) frames.set('app.' + viewport + '.' + state, {id: viewport + '-' + state});
  assert.deepEqual(plain(h.draftFlowStarts([c], frames)).map(row => row.node.id), ['desktop-one']);
  c.prototype.entry_states = ['one'];
  assert.deepEqual(plain(h.draftFlowStarts([c], frames)).map(row => row.node.id), ['desktop-one', 'mobile-one']);
  c.entry_states = c.prototype.entry_states = ['one', 'two'];
  assert.deepEqual(plain(h.draftFlowStarts([c], frames)).map(row => row.node.id), ['desktop-one', 'desktop-two', 'mobile-one', 'mobile-two']);
});

test('runtime rejects unknown, wrong-screen, non-action and bound static specification references', () => {
  const h = host();
  assert.equal(h.draftProductButtons(candidate(), 'desktop', {id: 'one', screen: 'screen'})[0].specification.id, 'deliver');
  for (const problem of ['unknown', 'screen', 'kind', 'action', 'canonical control', 'bound action', 'bound control', 'null', 'empty']) {
    const c = candidate(); c.specifications = structuredClone(c.specifications);
    if (problem === 'unknown') c.specifications = {};
    if (problem === 'screen') c.specifications.deliver.screen_id = 'other';
    if (problem === 'kind') c.specifications.deliver.kind = 'screen';
    if (problem === 'canonical control') c.specifications.deliver.target_id = 'other';
    if (problem === 'action') c.specifications.deliver.meaning.action = 'other';
    if (problem === 'bound action') c.prototype.bindings = [{action: 'deliver', control_id: 'other'}];
    if (problem === 'bound control') c.prototype.bindings = [{action: 'other', control_id: 'deliver'}];
    if (problem === 'null') c.state_layouts.desktop.one.product_buttons.deliver.specification_id = null;
    if (problem === 'empty') c.state_layouts.desktop.one.product_buttons.deliver.specification_id = '';
    assert.throws(() => h.draftProductButtons(c, 'desktop', {id: 'one', screen: 'screen'}), /Canonical unbound/, problem);
  }
  const legacy = candidate(); delete legacy.state_layouts.desktop.one.product_buttons.deliver.specification_id;
  assert.equal(h.draftProductButtons(legacy, 'desktop', {id: 'one', screen: 'screen'})[0].specification, undefined);
});

test('static control identity can differ from its canonical action identity', () => {
  const h = host(), c = candidate();
  const original = c.specifications.deliver;
  c.specifications = {'ACT-deliver': {...original, id: 'ACT-deliver', meaning: {...original.meaning, action: 'ACT-deliver'}}};
  c.state_layouts.desktop.one.product_buttons.deliver.specification_id = 'ACT-deliver';
  const button = h.draftProductButtons(c, 'desktop', {id: 'one', screen: 'screen'})[0];
  assert.equal(button.id, 'deliver');
  assert.equal(button.specification.id, 'ACT-deliver');
});

test('static INSTANCE gets connected human summary, full board and real getter readback without reactions', async () => {
  const h = host(), page = new Node('PAGE'), target = new Node('INSTANCE'), main = new Node('COMPONENT');
  page.flowStartingPoints = [];
  target.main = main; target.reactions = [];
  page.appendChild(main);
  const c = candidate();
  Object.assign(h, {c, viewport: 'desktop', state: {id: 'one', screen: 'screen'}, frame: page, page, l: c.state_layouts.desktop.one, key: 'app.desktop.one', mains: new Map([['app.desktop.Primary', main]]), notes: [],
    control(frame, key, main, label, box) {target.setPluginData('semanticKey', key); frame.appendChild(target); return target;}});
  const start = runtime.indexOf(' for(const button of draftProductButtons(c,viewport,state)){control(');
  const end = runtime.indexOf('\n x+=', start);
  assert(start > 0 && end > start);
  await vm.runInContext('(async () => {' + runtime.slice(start, end) + '\n})()', h);
  assert.equal(h.notes.length, 1);
  assert.equal(h.notes[0].specification.id, 'deliver');
  const button = h.draftProductButtons(candidate(), 'desktop', {id: 'one', screen: 'screen'})[0];
  const board = await h.ensureDesignNoteBoard(h.figma, page, {presentation: 'readable-specs', sourceHash: 'owner', font: {family: 'Inter', style: 'Regular'},
    notes: [{key: 'desktop|one|deliver', targetId: target.id, specification: button.specification}]});
  await h.ensureNativeAnnotations(h.figma, page, {presentation: 'readable-specs', sourceHash: 'owner', annotations: h.notes.map(note => ({...note,
    board: {boardId: board.boardId, textNodeId: board.entries[0].textNodeId, key: board.entries[0].key}}))});
  const row = (await h.readDraft(page)).nodes.find(n => n.id === target.id);
  assert.equal(row.specification_status, 'observed');
  assert.equal(row.mainComponentId, main.id);
  assert.deepEqual(plain(row.reactions), []);
  assert.equal(target.annotations.length, 1);
  assert(target.annotations[0].labelMarkdown.includes('https://www.figma.com/design/file-key?node-id='));
  const text = page.findOne(n => n.id === board.entries[0].textNodeId);
  assert.equal(text.characters, spec.title + '\n' + spec.display_text);
  assert.deepEqual(plain(text.getRangeHyperlink()), {type: 'NODE', value: target.id});
  delete target.reactions;
  assert.equal(Object.hasOwn((await h.readDraft(page)).nodes.find(n => n.id === target.id), 'reactions'), false);
  target.getReactions = async () => [{trigger: {type: 'ON_HOVER'}}];
  assert.equal((await h.readDraft(page)).nodes.find(n => n.id === target.id).reactions[0].trigger.type, 'ON_HOVER');
  delete text.getRangeHyperlink;
  text.getRangeHyperlink = undefined;
  assert.equal((await h.readNativeSemantics(h.figma, page)).nodes.find(n => n.id === target.id).specification_status, 'invalid');
});

test('self NAVIGATE fails preflight and ordinary authoring before any Figma write', async () => {
  for (const viewport of ['desktop', 'mobile']) for (const explicit of [false, true]) {
    const h = host(), font = {family: 'Inter', style: 'Regular'};
    const c = {id: 'app', fonts: {body: font}, foundations: {roles: []}, foundationBindings: [], control_styles: {},
      prototype: {states: [{id: 'one'}, {id: 'two'}], bindings: [{viewport, source_state: 'one', target_state: 'two', control_id: 'next'}, {viewport, source_state: 'two', target_state: 'one', control_id: 'back'}]},
      state_layouts: {}};
    for (const vp of ['desktop', 'mobile']) c.state_layouts[vp] = {one: {layers: [], control_boxes: {next: [0, 0, 100, 48]}}, two: {layers: [], control_boxes: {back: [0, 0, 100, 48]}}};
    if (explicit) c.prototype.entry_states = ['one'];
    const draft = {schema: 'figma-flow-native-direction-review-v1', scope: 'exploratory-only', candidates: [c]};
    assert.deepEqual(plain(h.preflightDraft(draft, [font])), [], 'ordinary two-frame cycles remain valid');
    c.prototype.bindings[0].target_state = 'one';
    assert(h.preflightDraft(draft, [font]).some(message => message.includes('Native NAVIGATE requires a different target state')));
    Object.assign(h.DRAFT, draft);
    h.admitDraftColorConsumers = () => [];
    h.figma.listAvailableFontsAsync = async () => [{fontName: font}];
    let writes = 0;
    h.figma.createPage = () => {writes++; assert.fail('invalid self-navigation must not create a page');};
    h.figma.setCurrentPageAsync = async () => {writes++; assert.fail('invalid self-navigation must not change the current page');};
    await assert.rejects(h.makeDraft(), /Native NAVIGATE requires a different target state/);
    assert.equal(writes, 0);
  }
});
