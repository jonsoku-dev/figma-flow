/* Captured native getters plus synthetic translated/nested regressions. Live acceptance is separate. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const fixture = require('./fixtures/rd02/native-group-coordinates.json');
const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
const transparent = node => ['GROUP', 'BOOLEAN_OPERATION'].includes(node.type);

function host() {
  let sequence = 0;
  class Node {
    constructor(type, properties = {}) {
      Object.assign(this, {id: 'synthetic-' + ++sequence, type, parent: null, children: [], _x: 0, _y: 0,
        _width: 1, _height: 1, data: {}, reactions: [], annotations: [], visible: true, opacity: 1,
        clipsContent: false, layoutMode: 'NONE', removed: false}, properties);
    }
    get x() {return transparent(this) && this.children.length ? Math.min(...this.children.map(n => n.x)) : this._x;}
    set x(value) {const delta = value - this.x; this._x = value; if (transparent(this)) for (const child of this.children) child.x += delta;}
    get y() {return transparent(this) && this.children.length ? Math.min(...this.children.map(n => n.y)) : this._y;}
    set y(value) {const delta = value - this.y; this._y = value; if (transparent(this)) for (const child of this.children) child.y += delta;}
    get width() {return transparent(this) && this.children.length ? Math.max(...this.children.map(n => n.x + n.width)) - this.x : this._width;}
    set width(value) {this._width = value;}
    get height() {return transparent(this) && this.children.length ? Math.max(...this.children.map(n => n.y + n.height)) - this.y : this._height;}
    set height(value) {this._height = value;}
    resize(width, height) {this.width = width; this.height = height;}
    appendChild(node) {this.insertChild(this.children.length, node);}
    insertChild(index, node) {if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = this; this.children.splice(index, 0, node);}
    remove() {if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; this.removed = true;}
    getPluginData(key) {return this.data[key] || '';}
    setPluginData(key, value) {this.data[key] = String(value);}
  }
  const figma = {showUI() {}, ui: {postMessage() {}}, createFrame: () => new Node('FRAME'),
    group(members, parent) {
      if (figma.failGroup) throw Error('injected group failure');
      const group = new Node('GROUP'); parent.appendChild(group);
      for (const member of members) {assert.equal(member.parent, parent); group.appendChild(member);}
      return group;
    }};
  const context = vm.createContext({DRAFT: {}, __html__: '', figma, console});
  vm.runInContext(source, context);
  return {Node, context, figma};
}

function captured(h, type = 'PAGE') {
  const screen = new h.Node(type, {id: 'page', x: 0, y: 0, width: 1000, height: 1000});
  const nodes = new Map(fixture.nodes.map(row => [row.id, new h.Node(row.type, {...row})]));
  for (const row of fixture.nodes) (row.parentId === 'page' ? screen : nodes.get(row.parentId)).appendChild(nodes.get(row.id));
  return {screen, nodes};
}

const pair = box => ({x: box.x, y: box.y, w: box.w, h: box.h});

test('captured Group/Text getters preserve the independent absoluteBoundingBox', () => {
  const h = host(), s = captured(h);
  for (const row of fixture.nodes) {
    const expected = row.absoluteBoundingBox;
    assert.deepEqual(pair(h.context.draftAbsoluteBox(s.nodes.get(row.id), s.screen)),
      {x: expected.x, y: expected.y, w: expected.width, h: expected.height}, row.id);
  }
});

test('translated Frame and nested transparent ancestors add only the Frame origin', () => {
  const h = host(), s = captured(h);
  const frame = new h.Node('FRAME', {x: 200, y: 400}); s.screen.appendChild(frame);
  const outer = new h.Node('GROUP'); frame.appendChild(outer); outer.appendChild(s.nodes.get('group'));
  for (const type of ['GROUP', 'BOOLEAN_OPERATION']) {
    outer.type = type;
    for (const id of ['title', 'body', 'group']) {
      const row = fixture.nodes.find(n => n.id === id);
      const box = h.context.draftAbsoluteBox(s.nodes.get(id), s.screen);
      assert.equal(box.x, row.absoluteBoundingBox.x + 200, id);
      assert.equal(box.y, row.absoluteBoundingBox.y + 400, id);
    }
  }
});

test('readback traverses the complete native Group parent chain without adding its origin', async () => {
  const h = host(), s = captured(h, 'FRAME');
  h.context.readNativeSemantics = () => {};
  const rows = [{id: 'page', width: 1000, height: 1000, clipsContent: true},
    ...fixture.nodes.map(row => ({...row, semanticKey: row.id}))];
  const declarations = [{key: 'group', kind: 'group', parent: null, children: ['title', 'body']}];
  const index = {byId: new Map(rows.map(row => [row.id, row])), byKey: new Map(rows.map(row => [row.semanticKey, row]))};
  const report = await h.context.readDeclaredContainerLinks(null, s.screen, declarations, '', index);
  for (const leaf of report.leaves) {
    const expected = fixture.nodes.find(row => row.id === leaf.id).absoluteBoundingBox;
    assert.equal(leaf.box.x, expected.x); assert.equal(leaf.box.y, expected.y);
  }
  index.byId.get('group').parentId = 'group';
  await assert.rejects(h.context.readDeclaredContainerLinks(null, s.screen, declarations, '', index), /parent|cycle/);
});

test('placement from a native Group preserves source coordinates and metadata', () => {
  const h = host(), s = captured(h, 'FRAME'), title = s.nodes.get('title');
  title.annotations = [{label: 'preserved'}]; title.reactions = [{actions: [{destinationId: 'page'}]}];
  const annotations = title.annotations, reactions = title.reactions;
  const result = h.context.placeDeclaredLayerParents(s.screen,
    [{key: 'card', kind: 'frame', parent: null, children: ['title'], box: [-200, -400, 600, 700]}], id => s.nodes.get(id));
  const card = result.get('card');
  assert.equal(title.parent, card); assert.equal(title.x, 35); assert.equal(title.y, 76);
  assert.equal(title.annotations, annotations); assert.equal(title.reactions, reactions); assert.equal(title.removed, false);
  assert.equal(s.nodes.get('body').parent, s.nodes.get('group'));
});

test('nested new Groups moved into a Frame preserve the original leaf absolute geometry', () => {
  const h = host(), screen = new h.Node('FRAME', {x: 700, y: 900, width: 1000, height: 1000});
  const a = new h.Node('TEXT', {x: 50, y: 80, width: 40, height: 20}); screen.appendChild(a);
  const declarations = [{key: 'card', kind: 'frame', parent: null, children: ['outer'], box: [20, 30, 200, 200]},
    {key: 'outer', kind: 'group', parent: 'card', children: ['inner']},
    {key: 'inner', kind: 'group', parent: 'outer', children: ['a']}];
  const placed = h.context.placeDeclaredLayerParents(screen, declarations, id => id === 'a' ? a : null);
  assert.equal(a.x, 30); assert.equal(a.y, 50);
  assert.equal(a.parent, placed.get('inner')); assert.equal(a.parent.parent, placed.get('outer'));
  assert.equal(placed.get('outer').parent, placed.get('card'));
  assert.deepEqual(pair(h.context.draftAbsoluteBox(a, screen)), {x: 50, y: 80, w: 40, h: 20});
  assert.deepEqual(pair(h.context.draftAbsoluteBox(placed.get('inner'), screen)), {x: 50, y: 80, w: 40, h: 20});
});

test('failed placement restores raw Group child coordinates, identity and order', () => {
  const h = host(), s = captured(h, 'FRAME'), group = s.nodes.get('group'), title = s.nodes.get('title');
  const order = [...group.children]; h.figma.failGroup = true;
  assert.throws(() => h.context.placeDeclaredLayerParents(s.screen,
    [{key: 'outer', kind: 'group', parent: null, children: ['card']},
      {key: 'card', kind: 'frame', parent: 'outer', children: ['title'], box: [-200, -400, 600, 700]}], id => s.nodes.get(id)), /injected group failure/);
  assert.deepEqual(group.children, order); assert.equal(title.parent, group); assert.equal(title.removed, false);
  assert.equal(title.x, -165); assert.equal(title.y, -324);
});

test('actual preflight and post-authoring geometry accept translated captured Group children', () => {
  const h = host(), page = new h.Node('PAGE'), font = {family: 'Inter', style: 'Regular'};
  page.findAll = () => all;
  const all = [], candidate = {id: 'a', fonts: {body: font}, control_styles: {},
    prototype: {states: [{id: 'idle'}], bindings: []}, state_layouts: {}};
  for (const [viewport, frameY] of [['desktop', 0], ['mobile', 1100]]) {
    const key = 'a.' + viewport + '.idle', frame = new h.Node('FRAME', {x: 0, y: frameY, width: 1000, height: 1000});
    page.appendChild(frame); frame.setPluginData('semanticKey', key); all.push(frame);
    const enclosing = new h.Node('FRAME', {x: 200, y: 400, width: 700, height: 600}); frame.appendChild(enclosing);
    enclosing.setPluginData('semanticKey', key + '.enclosing'); all.push(enclosing);
    const group = new h.Node('GROUP'); enclosing.appendChild(group); group.setPluginData('semanticKey', key + '.group'); all.push(group);
    const layers = [];
    for (const row of fixture.nodes.filter(row => row.type === 'TEXT')) {
      const layer = {id: row.id, kind: 'text', value: row.id, x: row.absoluteBoundingBox.x + 200,
        y: row.absoluteBoundingBox.y + 400, w: row.width, h: row.height, size: 20, leading: row.height, max_lines: 1, font: 'body', ink: 'ink'};
      const node = new h.Node('TEXT', {...row, characters: row.id, fontName: font, fontSize: 20,
        lineHeight: {unit: 'PIXELS', value: row.height}, letterSpacing: {unit: 'PIXELS', value: 0},
        textAutoResize: 'HEIGHT', textAlignHorizontal: 'LEFT'});
      node.setPluginData('semanticKey', key + '.' + row.id); group.appendChild(node); layers.push(layer); all.push(node);
    }
    candidate.state_layouts[viewport] = {idle: {width: 1000, height: 1000, layers, control_boxes: {}, containers: [
      {key: 'enclosing', kind: 'frame', parent: null, children: ['group'], box: [200, 400, 700, 600], clip: false},
      {key: 'group', kind: 'group', parent: 'enclosing', children: layers.map(layer => layer.id)}]}};
  }
  assert.deepEqual(JSON.parse(JSON.stringify(h.context.preflightDraft({candidates: [candidate]}, [font]))), []);
  assert.doesNotThrow(() => h.context.validateDraftGeometry(page, [candidate], false));
  all.find(node => node.type === 'TEXT').x += 10;
  assert.throws(() => h.context.validateDraftGeometry(page, [candidate], false), /geometry differs/);
});
