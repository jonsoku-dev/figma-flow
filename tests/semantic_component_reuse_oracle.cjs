const assert = require('node:assert/strict');
const {ensureSemanticComponents} = require('../figma-bridge/semantic_components.js');

function world() {
  let seq = 0;
  class Node {
    constructor(type, name = type) {
      this.type = type;
      this.name = name;
      this.id = 'n' + (++seq);
      this.children = [];
      this.parent = null;
      this.data = {};
      this.width = 100;
      this.height = 40;
      this.x = 0;
      this.y = 0;
      this.visible = true;
      this.fills = [];
      this.strokes = [];
      this.opacity = 1;
      this.layoutMode = 'NONE';
      this.relativeTransform = [[1, 0, 0], [0, 1, 0]];
      this.reactions = [];
      this.variantProperties = {};
      this.characters = '';
      this.removed = false;
      this.clipsContent = false;
    }
    setPluginData(key, value) { this.data[key] = value; }
    getPluginData(key) { return this.data[key] || ''; }
    getPluginDataKeys() { return Object.keys(this.data); }
    resize(width, height) { this.width = width; this.height = height; }
    appendChild(child) {
      this.insertChild(this.children.length, child);
      if (this.type === 'COMPONENT_SET' && child.name && child.name.includes('=')) {
        child.variantProperties = Object.fromEntries(child.name.split(', ').map(part => part.split('=')));
      }
    }
    insertChild(index, child) {
      if (child.parent) child.parent.children = child.parent.children.filter(node => node !== child);
      child.parent = this;
      this.children.splice(index, 0, child);
    }
    remove() {
      this.removed = true;
      if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this);
    }
    clone() {
      const copy = new Node(this.type, this.name);
      for (const field of ['width', 'height', 'x', 'y', 'visible', 'opacity', 'layoutMode', 'characters', 'clipsContent']) copy[field] = this[field];
      copy.fills = JSON.parse(JSON.stringify(this.fills));
      copy.strokes = JSON.parse(JSON.stringify(this.strokes));
      copy.relativeTransform = JSON.parse(JSON.stringify(this.relativeTransform));
      copy.data = {...this.data};
      for (const child of this.children) copy.appendChild(child.clone());
      return copy;
    }
    createInstance() {
      const instance = this.clone();
      instance.type = 'INSTANCE';
      instance.main = this;
      instance.getMainComponentAsync = async () => this;
      return instance;
    }
    getRangeAllFontNames() { return [{family: 'Inter', style: 'Regular'}]; }
    getStyledTextSegments() {
      return [{start: 0, end: this.characters.length, fontSize: 16, fontName: {family: 'Inter', style: 'Regular'}}];
    }
    async setReactionsAsync(reactions) { this.reactions = reactions; }
    async getMainComponentAsync() { return this.main || null; }
  }
  const page = new Node('PAGE', 'Fixture');
  const figma = {
    loadFontAsync: async () => {},
    createFrame: () => new Node('FRAME'),
    createComponentFromNode(node) { node.type = 'COMPONENT'; return node; },
    combineAsVariants(nodes, parent) {
      const set = new Node('COMPONENT_SET');
      parent.appendChild(set);
      for (const node of nodes) {
        set.appendChild(node);
        node.variantProperties = Object.fromEntries(node.name.split(', ').map(part => part.split('=')));
      }
      return set;
    }
  };
  const text = (parent, transform = [[1, 0, 0], [0, 1, 0]]) => {
    const node = new Node('TEXT', 'Label');
    node.characters = '계속';
    node.width = 48;
    node.height = 20;
    node.relativeTransform = transform;
    parent.appendChild(node);
    return node;
  };
  const frame = (key, width, height = 40, transform) => {
    const node = new Node('FRAME', key);
    node.layoutMode = 'HORIZONTAL';
    node.width = width;
    node.height = height;
    node.fills = [{type: 'SOLID', boundVariables: {color: {type: 'VARIABLE_ALIAS', id: 'color.brand'}}}];
    node.setPluginData('semanticKey', key);
    page.appendChild(node);
    text(node, transform);
    return node;
  };
  const find = (root, id) => {
    if (root.id === id) return root;
    for (const child of root.children || []) {
      const found = find(child, id);
      if (found) return found;
    }
    return null;
  };
  return {page, figma, frame, find};
}

async function checkSupportedWidthReuse() {
  const {page, figma, frame, find} = world();
  frame('button.primary', 160);
  frame('button.quiet', 160);
  const narrow = frame('use.narrow', 120);
  const wide = frame('use.wide', 240);
  const medium = frame('use.medium', 200);
  const shifted = frame('use.shifted', 160, 40, [[1, 0, 12], [0, 1, 6]]);
  const taller = frame('use.taller', 160, 72);
  const originals = {narrow, wide, medium, shifted, taller};
  for (const source of Object.values(originals)) source.semanticKey = source.getPluginData('semanticKey');
  const requests = [narrow, wide, medium, shifted, taller];
  const spec = {
    componentSets: [{
      id: 'set.button',
      name: 'Button',
      variants: [
        {key: 'button.primary', props: {Visual: 'Primary'}},
        {key: 'button.quiet', props: {Visual: 'Quiet'}}
      ]
    }],
    instances: requests.map(node => ({key: node.getPluginData('semanticKey'), variantKey: 'button.primary'}))
  };
  const result = await ensureSemanticComponents(figma, page, spec);
  const byKey = new Map(result.instances.map(item => [item.key, item]));
  const shared = byKey.get('use.narrow').mainComponentId;
  assert.equal(byKey.get('use.wide').mainComponentId, shared, 'supported width uses must share one main');
  assert.equal(byKey.get('use.medium').mainComponentId, shared, 'supported width uses must share one main');
  assert.notEqual(byKey.get('use.shifted').mainComponentId, shared, 'shifted child geometry keeps a separate main');
  assert.notEqual(byKey.get('use.taller').mainComponentId, shared, 'height difference keeps a separate main');
  assert.notEqual(byKey.get('use.shifted').mainComponentId, byKey.get('use.taller').mainComponentId);
  for (const [name, source] of Object.entries(originals)) {
    const instance = find(page, byKey.get(source.semanticKey).id);
    assert.equal(instance.width, source.width, name + ' render width');
    assert.equal(instance.height, source.height, name + ' render height');
    assert.deepEqual(instance.fills, source.fills, name + ' token binding');
  }
  const again = await ensureSemanticComponents(figma, page, spec);
  assert.equal(again.status, 'unchanged');
  const againByKey = new Map(again.instances.map(item => [item.key, item]));
  for (const key of ['use.narrow', 'use.wide', 'use.medium', 'use.shifted', 'use.taller']) {
    assert.equal(againByKey.get(key).mainComponentId, byKey.get(key).mainComponentId);
    assert.equal(againByKey.get(key).id, byKey.get(key).id);
  }
}

module.exports = {checkSupportedWidthReuse};

if (require.main === module) {
  checkSupportedWidthReuse().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}
