const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function check(recipe, failure) {
  let sequence = 0;
  const nodes = [];
  const messages = [];
  let page;
  class Node {
    constructor(type, attach = true) {
      this.type = type; this.id = String(++sequence); this.key = 'key-' + this.id;
      this.children = []; this.data = {}; this.removed = false; this.visible = true;
      this.x = 0; this.y = 0; this.width = 100; this.height = 100;
      this.componentPropertyDefinitions = {}; this.componentPropertyReferences = {};
      nodes.push(this);
      if (attach && page) page.appendChild(this);
    }
    appendChild(node) {
      if (failure === 'slot-append' && this.type === 'COMPONENT' && node.type === 'INSTANCE') {
        throw Error('Native slot parenting unsupported');
      }
      if (node.parent) node.parent.children = node.parent.children.filter(child => child !== node);
      node.parent = this; this.children.push(node);
    }
    resize(width, height) {this.width = width; this.height = height;}
    remove() {
      assert(!this.preexisting, 'rollback must never remove an existing node');
      this.removed = true;
      for (const child of [...this.children]) child.remove();
      if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    }
    set layoutMode(value) {
      if (failure === 'grid' && value === 'GRID') throw Error('GRID unsupported in this editor version');
      this.mode = value;
    }
    get layoutMode() {return this.mode;}
    setPluginData(key, value) {this.data[key] = value;}
    getPluginData(key) {return this.data[key] || '';}
    addComponentProperty(name, type, defaultValue) {
      if (type === 'BOOLEAN') throw Error('Native BOOLEAN API unsupported');
      const key = name + '#' + this.id;
      this.componentPropertyDefinitions[key] = {type, defaultValue};
      return key;
    }
    createInstance() {
      const result = new Node('INSTANCE');
      for (const child of this.children) {
        const copy = new Node(child.type);
        copy.name = child.name; copy.characters = child.characters;
        result.appendChild(copy);
      }
      return result;
    }
  }
  page = new Node('PAGE', false);
  const existing = new Node('FRAME');
  existing.name = 'User content'; existing.preexisting = true;
  page.selection = [existing];
  const unrelated = new Node('RECTANGLE');
  unrelated.name = 'Unrelated concurrent addition'; unrelated.preexisting = true;
  const original = {name: existing.name, children: [...existing.children], selection: [...page.selection]};
  const figma = {
    editorType: 'figma', currentPage: page,
    viewport: {scrollAndZoomIntoView() {}},
    loadFontAsync: async () => {},
    closePlugin: message => messages.push(message),
    createFrame: () => new Node('FRAME'), createRectangle: () => new Node('RECTANGLE'),
    createEllipse: () => new Node('ELLIPSE'), createText: () => new Node('TEXT'),
    createComponent: () => new Node('COMPONENT'),
    combineAsVariants(mains, parent) {
      const set = new Node('COMPONENT_SET'); parent.appendChild(set);
      for (const main of mains) set.appendChild(main);
      return set;
    },
    union(owned) {
      existing.appendChild(owned[0]);
      throw Error('Boolean operation unavailable after reparent');
    },
  };
  const source = fs.readFileSync(path.join(__dirname, 'bundled', recipe + '.js'), 'utf8');
  vm.runInNewContext(source, {figma});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(messages.length, 1);
  assert.match(messages[0], /unsupported|unavailable/);
  assert.deepEqual(page.children, [existing, unrelated], 'only invocation-owned nodes were removed');
  assert.equal(page.selection.length, original.selection.length, 'original selection size restored');
  assert(page.selection.every((node, index) => node === original.selection[index]), 'original selection restored');
  assert.equal(existing.name, original.name);
  assert.deepEqual(existing.children, original.children, 'reparented owned nodes rolled back');
  assert(nodes.filter(node => node !== page && !node.preexisting).every(node => node.removed));
}

(async () => {
  await check('design-grid', 'grid');
  await check('design-shapes', 'boolean');
  await check('design-component-properties', 'properties');
  await check('design-component-properties', 'slot-append');
  process.stdout.write('PASS: unsupported grid, reparented boolean, production BOOLEAN and unparented slot failures preserve existing nodes and selection.\n');
})().catch(error => {process.stderr.write(String(error.stack) + '\n'); process.exitCode = 1;});
