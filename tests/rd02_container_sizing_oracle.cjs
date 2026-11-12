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
      }
    };
  }
  const figma = {
    showUI() {},
    ui: {postMessage() {}, onmessage: null},
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
  const context = vm.createContext({DRAFT: {}, __html__: '', figma, console});
  vm.runInContext(source, context, {filename: sourcePath});
  return {context, makeNode, source};
}

function scene(makeNode) {
  const screen = makeNode('FRAME');
  screen.id = 'screen-1';
  screen.resize(390, 844);
  screen.clipsContent = true;
  const specs = [
    ['title', 'TEXT', 40, 40, 80, 24, '제목'],
    ['body', 'TEXT', 40, 76, 120, 40, '본문'],
    ['ornament', 'RECTANGLE', 280, 48, 24, 24, ''],
    ['save', 'INSTANCE', 40, 160, 48, 20, '저장'],
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
  save.mainComponentId = 'main-save';
  return {screen, leaves, resolve(id) { return leaves.get(id); }};
}

function checkDeclaredSizing() {
  const {context, makeNode, source} = load();
  assert.equal(typeof context.refreshDeclaredContainerSizing, 'function', 'declared hug fill and fixed sizing must follow text and parent resize');
  assert.ok(source.includes("setPluginData('containerFixedWidth'"), 'fixed container size is recorded before later text growth');

  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const placed = scene(makeNode);
  context.placeDeclaredLayerParents(placed.screen, fixture.containers, placed.resolve, '');
  const find = key => placed.screen.findAll(node => node.getPluginData('semanticKey') === key)[0];
  const copy = find('copy');
  const card = find('card');
  const actions = find('actions');
  const actionsParent = find('actions-parent');
  const title = placed.leaves.get('title');
  const body = placed.leaves.get('body');
  const save = placed.leaves.get('save');
  const fixedWidth = copy.width;
  const longText = '긴 한글 문구가 늘어나면 hug 높이만 따라가고 fixed 너비는 유지됩니다';
  title.characters = longText;
  title.resize(220, 80);
  actionsParent.resize(400, actionsParent.height);
  context.refreshDeclaredContainerSizing(placed.screen, fixture.containers, placed.resolve, '');
  assert.equal(copy.width, fixedWidth);
  assert.equal(copy.height, Math.max(title.y + title.height, body.y + body.height) + 16);
  assert.equal(actions.width, 400);
  assert.equal(actions.height, Math.max(save.y + save.height, placed.leaves.get('cancel').y + placed.leaves.get('cancel').height));
  assert.notEqual(actions.height, card.height);
  assert.equal(title.characters, longText);
  assert.equal(save.type, 'INSTANCE');
  assert.equal(save.mainComponentId, 'main-save');
  assert.equal(placed.screen.id, 'screen-1');
  assert.equal(placed.screen.clipsContent, true);
  assert.equal(absolute(title, placed.screen).x, 40);
  assert.equal(absolute(title, placed.screen).y, 40);
}

if (require.main === module) {
  try {
    checkDeclaredSizing();
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
}
