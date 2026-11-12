const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sourcePath = path.join(__dirname, '../figma-bridge/direction_review.js');
const fixturePath = path.join(__dirname, 'fixtures/rd02/declared-containers.json');

function absolute(node, screen) {
  let x = 0;
  let y = 0;
  let current = node;
  while (current && current !== screen) {
    x += current.x || 0;
    y += current.y || 0;
    current = current.parent;
  }
  return {x, y, w: node.width, h: node.height};
}

function load() {
  const source = fs.readFileSync(sourcePath, 'utf8');
  let seq = 0;
  function makeNode(type) {
    const node = {
      type,
      id: 'n' + (++seq),
      name: type,
      children: [],
      parent: null,
      x: 0,
      y: 0,
      width: 1,
      height: 1,
      clipsContent: false,
      fills: [],
      layoutMode: 'NONE',
      data: {},
      reactions: [],
      removed: false,
      setPluginData(key, value) { this.data[key] = String(value); },
      getPluginData(key) { return this.data[key] || ''; },
      resize(width, height) { this.width = width; this.height = height; },
      appendChild(child) { this.insertChild(this.children.length, child); },
      insertChild(index, child) {
        if (child.parent) child.parent.children = child.parent.children.filter(item => item !== child);
        child.parent = this;
        this.children.splice(index, 0, child);
      },
      remove() {
        this.removed = true;
        if (this.parent) this.parent.children = this.parent.children.filter(item => item !== this);
        this.parent = null;
      }
    };
    return node;
  }
  const figma = {
    failGroup: false,
    showUI() {},
    ui: {postMessage() {}, onmessage: null},
    createFrame() { return makeNode('FRAME'); },
    group(nodes, parent) {
      if (figma.failGroup) throw Error('group failed');
      const placed = nodes.map(node => ({node, ...absolute(node, parent)}));
      const minX = Math.min(...placed.map(item => item.x));
      const minY = Math.min(...placed.map(item => item.y));
      const group = makeNode('GROUP');
      parent.appendChild(group);
      group.x = minX;
      group.y = minY;
      for (const item of placed) {
        group.appendChild(item.node);
        item.node.x = item.x - minX;
        item.node.y = item.y - minY;
      }
      group.fills = [];
      group.clipsContent = false;
      group.layoutMode = 'NONE';
      return group;
    }
  };
  const context = vm.createContext({DRAFT: {}, __html__: '', figma, console});
  vm.runInContext(source, context, {filename: sourcePath});
  return {context, figma, makeNode, source};
}

function scene(makeNode) {
  const screen = makeNode('FRAME');
  screen.id = 'screen-1';
  screen.name = 'state.idle';
  screen.resize(390, 844);
  screen.clipsContent = true;
  const specs = [
    ['title', 'TEXT', 40, 40, 80, 24, '제목'],
    ['body', 'TEXT', 40, 76, 120, 40, '본문'],
    ['ornament', 'RECTANGLE', 280, 48, 24, 24, ''],
    ['save', 'TEXT', 40, 160, 48, 20, '저장'],
    ['cancel', 'TEXT', 96, 160, 48, 20, '취소'],
    ['loose', 'TEXT', 12, 12, 20, 20, '바깥']
  ];
  const leaves = new Map();
  for (const [id, type, x, y, w, h, characters] of specs) {
    const node = makeNode(type);
    node.name = id;
    node.characters = characters;
    node.resize(w, h);
    node.x = x;
    node.y = y;
    node.setPluginData('semanticKey', id);
    screen.appendChild(node);
    leaves.set(id, node);
  }
  leaves.get('ornament').setPluginData('rasterAsset', 'hero');
  leaves.get('save').reactions = [{trigger: {type: 'ON_CLICK'}, actions: [{type: 'NODE', destinationId: screen.id}]}];
  const positions = new Map([...leaves].map(([id, node]) => [id, {parent: node.parent, x: node.x, y: node.y, characters: node.characters}]));
  return {
    screen,
    leaves,
    positions,
    resolve(id) { return leaves.get(id); }
  };
}

function checkDeclaredParents() {
  const {context, figma, makeNode, source} = load();
  assert.equal(typeof context.placeDeclaredLayerParents, 'function', 'declared parents must reuse authored leaves');
  const authored = source.indexOf("for(const layer of l.layers){if(layer.kind==='image'");
  const call = source.indexOf('placeDeclaredLayerParents(frame, l.containers');
  assert.ok(authored !== -1 && call > authored, 'parent placement follows the existing leaf authoring path');

  const flat = scene(makeNode);
  context.placeDeclaredLayerParents(flat.screen, [], flat.resolve, '');
  assert.equal(flat.leaves.get('title').parent, flat.screen);
  assert.equal(flat.leaves.get('title').x, 40);

  const declared = scene(makeNode);
  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  context.placeDeclaredLayerParents(declared.screen, fixture.containers, declared.resolve, '');
  assert.equal(declared.screen.id, 'screen-1');
  assert.equal(declared.screen.width, 390);
  assert.equal(declared.screen.height, 844);
  assert.equal(declared.screen.clipsContent, true);
  const card = declared.screen.children.find(node => node.getPluginData('semanticKey') === 'card');
  assert.equal(card.type, 'FRAME');
  assert.equal(card.name, 'card');
  assert.deepEqual([card.x, card.y, card.width, card.height], [24, 24, 320, 180]);
  assert.equal(card.clipsContent, true);
  assert.equal(card.getPluginData('containerFill'), 'surface');
  assert.deepEqual(card.children.map(node => node.getPluginData('semanticKey')), ['copy', 'ornament-cluster', 'actions']);
  const copy = card.children[0];
  const cluster = card.children[1];
  const actions = card.children[2];
  assert.equal(copy.type, 'FRAME');
  assert.equal(copy.name, 'copy');
  assert.equal(copy.layoutMode, 'VERTICAL');
  assert.equal(copy.itemSpacing, 12);
  assert.deepEqual([copy.paddingTop, copy.paddingRight, copy.paddingBottom, copy.paddingLeft], [16, 16, 16, 16]);
  assert.equal(copy.counterAxisSizingMode, 'FIXED');
  assert.equal(copy.primaryAxisSizingMode, 'AUTO');
  assert.equal(cluster.type, 'GROUP');
  assert.equal(cluster.name, 'ornament');
  assert.equal(cluster.layoutMode, 'NONE');
  assert.equal(cluster.clipsContent, false);
  assert.deepEqual(cluster.fills, []);
  assert.equal(actions.layoutMode, 'HORIZONTAL');
  assert.equal(actions.itemSpacing, 8);
  assert.equal(actions.layoutSizingHorizontal, 'FILL');
  assert.equal(actions.primaryAxisSizingMode, 'FIXED');
  assert.equal(actions.counterAxisSizingMode, 'AUTO');
  assert.deepEqual(copy.children.map(node => node.getPluginData('semanticKey')), ['title', 'body']);
  assert.deepEqual(actions.children.map(node => node.getPluginData('semanticKey')), ['save', 'cancel']);
  for (const [id, node] of declared.leaves) {
    if (id === 'loose') continue;
    assert.deepEqual(absolute(node, declared.screen), {x: declared.positions.get(id).x, y: declared.positions.get(id).y, w: node.width, h: node.height}, id);
    assert.equal(node.getPluginData('semanticKey'), id);
  }
  assert.equal(declared.leaves.get('title').characters, '제목');
  assert.equal(declared.leaves.get('ornament').getPluginData('rasterAsset'), 'hero');
  assert.equal(declared.leaves.get('save').reactions[0].actions[0].destinationId, declared.screen.id);
  assert.equal(declared.leaves.get('loose').parent, declared.screen);
  assert.equal(declared.leaves.get('loose').x, 12);

  const missing = scene(makeNode);
  assert.throws(() => context.placeDeclaredLayerParents(missing.screen, fixture.containers, id => id === 'ornament' ? undefined : missing.resolve(id), ''), /missing target/);
  assert.equal(missing.leaves.get('title').parent, missing.screen);
  assert.equal(missing.leaves.get('title').x, 40);
  assert.equal(missing.screen.children.some(node => node.getPluginData('containerKind')), false);

  const rollback = scene(makeNode);
  figma.failGroup = true;
  assert.throws(() => context.placeDeclaredLayerParents(rollback.screen, fixture.containers, rollback.resolve, ''), /group failed/);
  for (const [id, node] of rollback.leaves) {
    assert.equal(node.parent, rollback.screen, id);
    assert.equal(node.x, rollback.positions.get(id).x, id);
    assert.equal(node.y, rollback.positions.get(id).y, id);
    assert.equal(node.removed, false);
  }
  assert.equal(rollback.screen.children.some(node => node.getPluginData('containerKind')), false);
  assert.equal(rollback.screen.clipsContent, true);
}

if (require.main === module) {
  try {
    checkDeclaredParents();
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
}
