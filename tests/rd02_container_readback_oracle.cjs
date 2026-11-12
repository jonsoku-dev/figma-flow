const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sourcePath = path.join(__dirname, '../figma-bridge/direction_review.js');
const readerPath = path.join(__dirname, '../figma-bridge/native_semantic_read.js');
const fixturePath = path.join(__dirname, 'fixtures/rd02/declared-containers.json');

function absolute(node, screen) {
  let x = 0;
  let y = 0;
  let current = node;
  while (current && current !== screen) {
    if (current === node || !['GROUP', 'BOOLEAN_OPERATION'].includes(current.type)) {
      x += current.x || 0;
      y += current.y || 0;
    }
    current = current.parent;
  }
  return {x, y};
}

function load() {
  const source = fs.readFileSync(sourcePath, 'utf8');
  let seq = 0;
  function makeNode(type) {
    return {
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
      annotations: [],
      reactions: [],
      visible: true,
      opacity: 1,
      data: {},
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
      },
      findAll(test) {
        const walk = node => node.children.flatMap(child => [child, ...walk(child)]);
        return walk(this).filter(node => test(node));
      },
      async loadAsync() {}
    };
  }
  const figma = {
    showUI() {},
    ui: {postMessage() {}, onmessage: null},
    variables: {getLocalVariableCollectionsAsync: async () => []},
    createFrame() { return makeNode('FRAME'); },
    group(nodes, parent) {
      const placed = nodes.map(node => ({node, ...absolute(node, parent)}));
      const minX = Math.min(...placed.map(item => item.x));
      const minY = Math.min(...placed.map(item => item.y));
      const group = makeNode('GROUP');
      parent.appendChild(group);
      group.x = minX;
      group.y = minY;
      for (const item of placed) {
        group.appendChild(item.node);
        item.node.x = item.x;
        item.node.y = item.y;
      }
      group.fills = [];
      group.clipsContent = false;
      group.layoutMode = 'NONE';
      Object.defineProperties(group, {
        x: {get() {return Math.min(...this.children.map(child => child.x));},
          set(value) {const delta = value - this.x; for (const child of this.children) child.x += delta;}},
        y: {get() {return Math.min(...this.children.map(child => child.y));},
          set(value) {const delta = value - this.y; for (const child of this.children) child.y += delta;}},
        width: {get() {return Math.max(...this.children.map(child => child.x + child.width)) - this.x;}},
        height: {get() {return Math.max(...this.children.map(child => child.y + child.height)) - this.y;}}
      });
      return group;
    }
  };
  const context = vm.createContext({
    DRAFT: {},
    __html__: '',
    figma,
    console,
    unescape,
    encodeURIComponent
  });
  vm.runInContext(fs.readFileSync(readerPath, 'utf8'), context, {filename: readerPath});
  vm.runInContext(source, context, {filename: sourcePath});
  return {context, makeNode, source};
}

function scene(makeNode) {
  const page = makeNode('PAGE');
  page.id = 'page-1';
  const screen = makeNode('FRAME');
  screen.id = 'screen-1';
  screen.name = 'state.idle';
  screen.resize(390, 844);
  screen.clipsContent = true;
  page.appendChild(screen);
  const specs = [
    ['title', 'TEXT', 40, 40, 80, 24, '제목'],
    ['body', 'TEXT', 40, 76, 120, 40, '본문'],
    ['ornament', 'RECTANGLE', 280, 48, 24, 24, ''],
    ['save', 'TEXT', 40, 160, 48, 20, '저장'],
    ['cancel', 'TEXT', 96, 160, 48, 20, '취소']
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
  const save = leaves.get('save');
  save.reactions = [{trigger: {type: 'ON_CLICK'}, actions: [{type: 'NODE', destinationId: screen.id, navigation: 'NAVIGATE'}]}];
  save.annotations = [{label: '저장 명세'}];
  save.setPluginData('figmaFlowSpecification', '{"schema":"not-a-spec"}');
  return {page, screen, leaves, resolve(id) { return leaves.get(id); }};
}

async function checkDeclaredReadback() {
  const {context, makeNode, source} = load();
  assert.equal(typeof context.readDeclaredContainerLinks, 'function', 'declared container links must match the native reader');
  const start = source.indexOf('async function readDeclaredContainerLinks');
  const end = source.indexOf('async function makeDraft');
  assert.ok(start !== -1 && end > start && source.slice(start, end).includes('readNativeSemantics('), 'container readback uses the native reader');
  assert.ok(source.includes('readDeclaredContainerLinks(page, frame, l.containers'), 'authoring compares container links after parent placement');

  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const placed = scene(makeNode);
  context.placeDeclaredLayerParents(placed.screen, fixture.containers, placed.resolve, '');
  const report = await context.readDeclaredContainerLinks(placed.page, placed.screen, fixture.containers, '');
  assert.equal(report.screen.id, 'screen-1');
  assert.equal(report.screen.width, 390);
  assert.equal(report.screen.height, 844);
  assert.equal(report.screen.clipsContent, true);
  const card = report.containers.find(item => item.key === 'card');
  const copy = report.containers.find(item => item.key === 'copy');
  const cluster = report.containers.find(item => item.key === 'ornament-cluster');
  const actions = report.containers.find(item => item.key === 'actions');
  assert.equal(card.type, 'FRAME');
  assert.equal(card.parentId, placed.screen.id);
  assert.equal(card.clipsContent, true);
  assert.equal(copy.type, 'FRAME');
  assert.equal(copy.parentId, card.id);
  assert.equal(copy.layoutMode, 'VERTICAL');
  assert.equal(cluster.type, 'GROUP');
  assert.equal(cluster.parentId, card.id);
  assert.equal(cluster.layoutMode, 'NONE');
  assert.equal(cluster.clipsContent, false);
  assert.equal(actions.type, 'FRAME');
  assert.equal(actions.layoutMode, 'HORIZONTAL');
  const title = report.leaves.find(item => item.key === 'title');
  const save = report.leaves.find(item => item.key === 'save');
  assert.equal(title.parentId, copy.id);
  assert.equal(title.box.x, 40);
  assert.equal(title.box.y, 40);
  assert.equal(title.box.w, 80);
  assert.equal(title.box.h, 24);
  assert.equal(save.parentId, actions.id);
  assert.equal(save.reactions[0].actions[0].destinationId, placed.screen.id);
  assert.equal(save.annotations[0].label, '저장 명세');
  assert.equal(save.specificationStatus, 'invalid');
  assert.equal(report.containers.every(item => item.annotations.length === 0), true);
  assert.equal(report.containers.every(item => item.specificationStatus == null), true);

  const moved = scene(makeNode);
  context.placeDeclaredLayerParents(moved.screen, fixture.containers, moved.resolve, '');
  const movedCard = moved.screen.findAll(node => node.getPluginData('semanticKey') === 'card')[0];
  moved.leaves.get('save').reactions[0].actions[0].destinationId = movedCard.id;
  await assert.rejects(context.readDeclaredContainerLinks(moved.page, moved.screen, fixture.containers, ''), /prototype target moved onto container/);
}

if (require.main === module) {
  checkDeclaredReadback().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}
