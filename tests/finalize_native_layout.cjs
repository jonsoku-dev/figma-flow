/* Frozen RD02 API-shaped regressions. Actual native resize remains a live acceptance check. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');

function host() {
  let sequence = 0;
  class Node {
    constructor(type) {
      Object.assign(this, {id: String(++sequence), type, children: [], parent: null, x: 0, y: 0,
        width: 20, height: 20, data: {}, reactions: [], removed: false});
      if (type !== 'GROUP') Object.assign(this, {fills: [], layoutMode: 'NONE', clipsContent: false, layoutPositioning: 'AUTO'});
    }
    setPluginData(key, value) {this.data[key] = String(value);}
    getPluginData(key) {return this.data[key] || '';}
    resize(width, height) {assert(Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0); this.width = width; this.height = height;}
    appendChild(node) {this.insertChild(this.children.length, node);}
    insertChild(index, node) {if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = this; this.children.splice(index, 0, node);}
    remove() {this.removed = true; if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null;}
  }
  const absolute = node => {let x = 0, y = 0; for (let n = node; n; n = n.parent) {x += n.x; y += n.y;} return [x, y];};
  const figma = {showUI() {}, ui: {postMessage() {}}, createFrame: () => new Node('FRAME'),
    group(members, parent) {
      if (figma.failGroup) throw Error('injected native group failure');
      const positions = members.map(node => ({node, point: absolute(node)}));
      const origin = absolute(parent), group = new Node('GROUP');
      group.x = Math.min(...positions.map(p => p.point[0])) - origin[0];
      group.y = Math.min(...positions.map(p => p.point[1])) - origin[1];
      parent.appendChild(group);
      for (const {node, point} of positions) {group.appendChild(node); node.x = point[0] - origin[0] - group.x; node.y = point[1] - origin[1] - group.y;}
      return group;
    }};
  const context = vm.createContext({DRAFT: {}, figma, __html__: '', console});
  vm.runInContext(source, context);
  return {context, figma, Node, absolute};
}

function scene(h) {
  const screen = new h.Node('FRAME'); screen.resize(390, 844); screen.clipsContent = true;
  const a = new h.Node('TEXT'), b = new h.Node('INSTANCE'); b.y = 24;
  a.characters = 'Title'; b.mainComponent = {id: 'original-main'};
  a.annotations = [{label: 'Existing note'}]; b.reactions = [{actions: [{type: 'NODE', destinationId: screen.id}]}];
  screen.appendChild(a); screen.appendChild(b);
  const leaves = {a, b};
  return {screen, a, b, resolve: id => leaves[id]};
}
const flow = () => ({key: 'flow', kind: 'auto-layout', parent: null, children: ['a', 'b'],
  layout: {direction: 'VERTICAL', gap: 4, padding: [0, 0, 0, 0], width: 'fixed', height: 'hug'}});

test('declared flow leaves participate in native reflow and preserve fitting pinned geometry', () => {
  const h = host(), s = scene(h), main = s.b.mainComponent, reactions = s.b.reactions, annotations = s.a.annotations;
  h.context.placeDeclaredLayerParents(s.screen, [flow()], s.resolve);
  assert.equal(s.a.layoutPositioning, 'AUTO', 'normal children must participate in Figma Auto Layout resize');
  assert.equal(s.b.layoutPositioning, 'AUTO');
  assert.deepEqual(h.absolute(s.a), [0, 0]); assert.deepEqual(h.absolute(s.b), [0, 24]);
  assert.equal(s.a.parent, s.b.parent); assert.equal(s.a.parent.layoutMode, 'VERTICAL');
  assert.equal(s.b.mainComponent, main); assert.equal(s.b.reactions, reactions); assert.equal(s.a.annotations, annotations);
  assert.equal(s.screen.width, 390); assert.equal(s.screen.height, 844); assert.equal(s.screen.clipsContent, true);
});

test('accepted Group to Group to Frame trees reuse original nodes and fixed geometry', () => {
  const h = host(), s = scene(h); s.a.x = 20; s.a.y = 30;
  const before = h.absolute(s.a);
  const containers = [{key: 'outer', kind: 'group', parent: null, children: ['inner']},
    {key: 'inner', kind: 'group', parent: 'outer', children: ['card']},
    {key: 'card', kind: 'frame', parent: 'inner', children: ['a'], box: [10, 20, 120, 90]}];
  assert.doesNotThrow(() => h.context.placeDeclaredLayerParents(s.screen, containers, s.resolve));
  assert.equal(s.a.parent.type, 'FRAME'); assert.equal(s.a.parent.parent.type, 'GROUP');
  assert.equal(s.a.parent.parent.parent.type, 'GROUP'); assert.equal(s.a.parent.parent.parent.parent, s.screen);
  assert.deepEqual(h.absolute(s.a), before); assert.equal(s.b.parent, s.screen);
});

test('group failure rolls back only newly created containers and restores identity/order/metadata', () => {
  const h = host(), s = scene(h); const original = [...s.screen.children]; h.figma.failGroup = true;
  assert.throws(() => h.context.placeDeclaredLayerParents(s.screen,
    [{key: 'card', kind: 'frame', children: ['g'], box: [0, 0, 100, 80]},
      {key: 'g', kind: 'group', parent: 'card', children: ['a']}], s.resolve), /injected native group failure/);
  assert.deepEqual(s.screen.children, original); assert.equal(s.a.removed, false); assert.equal(s.b.removed, false);
  assert.deepEqual(h.absolute(s.b), [0, 24]); assert.equal(s.a.annotations[0].label, 'Existing note');
});

test('real preflight rejects malformed tree before makeDraft creates a page', async () => {
  const h = host(), font = {family: 'Inter', style: 'Regular'};
  const state = {width: 390, height: 844, layers: [{id: 'a', kind: 'rect'}], control_boxes: {},
    containers: [{key: 'card', kind: 'frame', children: ['missing'], box: [0, 0, 100, 80]}]};
  const candidate = {id: 'a', fonts: {body: font}, foundations: {roles: []}, control_styles: {},
    prototype: {states: [{id: 'one'}], bindings: []}, state_layouts: {desktop: {one: state}, mobile: {one: state}}};
  h.context.DRAFT = {schema: 'figma-flow-native-direction-review-v1', scope: 'exploratory-only', candidates: [candidate]};
  const problems = h.context.preflightDraft(h.context.DRAFT, [font]);
  assert(problems.some(problem => /container|target|parent/i.test(problem)), 'actual preflight must validate container declarations');
  let pages = 0;
  Object.assign(h.figma, {listAvailableFontsAsync: async () => [{fontName: font}], createPage() {pages++; throw Error('page created before rejection');}});
  // Isolate unrelated foundation admission while exercising actual preflight and makeDraft ordering.
  Object.assign(h.context, {admitDraftColorConsumers() {}, declareDraftFoundations() {}, findInterruptedDraftReview: async () => null});
  await assert.rejects(h.context.makeDraft(), /container|target|parent/i);
  assert.equal(pages, 0);
});

test('preflight diagnoses a flow declaration that contradicts pinned leaf geometry', () => {
  const h = host(), font = {family: 'Inter', style: 'Regular'};
  const state = {width: 390, height: 844, control_boxes: {}, containers: [flow()],
    layers: [{id: 'a', kind: 'rect', x: 0, y: 0, w: 20, h: 20},
      {id: 'b', kind: 'rect', x: 100, y: 100, w: 20, h: 20}]};
  const candidate = {id: 'a', fonts: {body: font}, control_styles: {}, prototype: {states: [{id: 'one'}], bindings: []},
    state_layouts: {desktop: {one: state}, mobile: {one: state}}};
  const problems = h.context.preflightDraft({candidates: [candidate]}, [font]);
  assert(problems.some(problem => /geometry|flow|layout/i.test(problem)),
    'contradictory pixel geometry must be diagnosed before mutation, never silently converted to absolute children');
});
