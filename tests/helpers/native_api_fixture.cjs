const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const sourcePath = process.argv[2];
const context = {};
vm.runInNewContext(fs.readFileSync(sourcePath, 'utf8')
  + '\nglobalThis.__fixture = {createNativeApiLabFixtures, runNativeApiLabOwnedWrites, runNativeApiLabOwnedReads};', context, {filename: sourcePath});

let nextId = 1;
class Node {
  constructor(type) {
    this.id = `${nextId++}:0`;
    this.type = type;
    this.name = type;
    this.children = [];
    this.parent = null;
    this.selection = [];
    this.pluginData = {};
    this.removed = false;
    this.vectorPaths = [];
    this.characters = '';
    this.fontName = {family: 'Inter', style: 'Regular'};
    this._rangeFontName = this.fontName;
    this._rangeFontSize = 14;
    this._rangeLineHeight = {unit: 'PIXELS', value: 20};
    this._rangeLetterSpacing = {unit: 'PIXELS', value: 0};
    this._rangeFills = [{type: 'SOLID', color: {r: 0, g: 0, b: 0}}];
  }
  appendChild(node) {
    if (node.parent) node.parent.children = node.parent.children.filter(child => child !== node);
    node.parent = this;
    this.children.push(node);
  }
  setPluginData(key, value) { this.pluginData[key] = value; }
  getPluginData(key) { return this.pluginData[key] || ''; }
  resize(width, height) { this.width = width; this.height = height; }
  findAll(predicate) {
    const result = [];
    const visit = node => { for (const child of node.children) { if (predicate(child)) result.push(child); visit(child); } };
    visit(this);
    return result;
  }
  createInstance() {
    const instance = new Node('INSTANCE');
    instance.mainComponent = this;
    this.instances = this.instances || [];
    this.instances.push(instance);
    return instance;
  }
  createSlot() { const slot = new Node('SLOT'); this.appendChild(slot); return slot; }
  async getInstancesAsync() { return this.instances || []; }
  async getMainComponentAsync() { return this.mainComponent || null; }
  async loadAsync() {}
  getRangeFontName() { return this._rangeFontName; }
  setRangeFontName(start, end, value) { this._rangeFontName = value; }
  getRangeFontSize() { return this._rangeFontSize; }
  setRangeFontSize(start, end, value) { this._rangeFontSize = value; }
  getRangeLineHeight() { return this._rangeLineHeight; }
  setRangeLineHeight(start, end, value) { this._rangeLineHeight = value; }
  getRangeLetterSpacing() { return this._rangeLetterSpacing; }
  setRangeLetterSpacing(start, end, value) { this._rangeLetterSpacing = value; }
  getRangeFills() { return JSON.parse(JSON.stringify(this._rangeFills)); }
  setRangeFills(start, end, value) { this._rangeFills = JSON.parse(JSON.stringify(value)); }
}

async function main() {
  const root = new Node('DOCUMENT');
  const originalPage = new Node('PAGE');
  originalPage.name = 'Existing page';
  originalPage.selection = [new Node('RECTANGLE')];
  root.appendChild(originalPage);
  let currentPage = originalPage;
  const calls = {createPage: 0, createNode: 0};
  const make = type => () => {
    calls.createNode++;
    const node = new Node(type);
    currentPage.appendChild(node);
    return node;
  };
  const figma = {
    editorType: 'figma', mode: 'default', fileKey: 'fixture-file', root,
    get currentPage() { return currentPage; },
    set currentPage(value) { currentPage = value; },
    async setCurrentPageAsync(page) { currentPage = page; },
    async loadFontAsync() {},
    createPage() { calls.createPage++; const page = new Node('PAGE'); root.appendChild(page); return page; },
    createFrame: make('FRAME'), createRectangle: make('RECTANGLE'), createEllipse: make('ELLIPSE'),
    createLine: make('LINE'), createPolygon: make('POLYGON'), createStar: make('STAR'),
    createVector: make('VECTOR'), createText: make('TEXT'), createComponent: make('COMPONENT'),
    createSection: make('SECTION'), createSlice: make('SLICE'), createConnector: make('CONNECTOR'),
    createTable() {
      const table = new Node('TABLE');
      for (let index = 0; index < 4; index++) table.appendChild(new Node('TABLE_CELL'));
      currentPage.appendChild(table);
      return table;
    },
    combineAsVariants(components, parent) {
      const set = new Node('COMPONENT_SET');
      components.forEach(child => set.appendChild(child));
      parent.appendChild(set);
      return set;
    },
    group(children, parent) { const node = new Node('GROUP'); children.forEach(child => parent.children = parent.children.filter(item => item !== child)); children.forEach(child => node.appendChild(child)); parent.appendChild(node); return node; },
    union(children, parent) { const node = new Node('BOOLEAN_OPERATION'); children.forEach(child => parent.children = parent.children.filter(item => item !== child)); children.forEach(child => node.appendChild(child)); parent.appendChild(node); return node; },
    createTextPath() { const path = new Node('TEXT_PATH'); currentPage.appendChild(path); return path; },
  };

  const create = context.__fixture.createNativeApiLabFixtures;
  const first = await create(figma, 'fixture-file');
  assert.equal(first.schema, 'figma-flow-native-api-lab-fixture-v1');
  assert.equal(first.createdCount > 0, true);
  assert.equal(figma.currentPage, originalPage);
  assert.equal(originalPage.selection.length, 1);
  assert.ok(first.nodes.some(row => row.observed_type === 'DOCUMENT' && row.semantic_id === 'document-root'));
  assert.ok(first.nodes.some(row => row.observed_type === 'PAGE' && row.semantic_id === 'page-root'));
  assert.ok(first.nodes.some(row => row.observed_type === 'TEXT_PATH'));
  assert.equal(new Set(first.nodes.map(row => row.semantic_id)).size, first.nodes.length);
  const firstCount = root.children.length + root.children.flatMap(page => page.findAll(() => true)).length;
  const second = await create(figma, 'fixture-file');
  const secondCount = root.children.length + root.children.flatMap(page => page.findAll(() => true)).length;
  assert.equal(second.createdCount, 0, JSON.stringify(second.createdSemanticIds));
  assert.equal(second.reused, true);
  assert.equal(firstCount, secondCount);
  assert.equal(calls.createPage, 1);
  const fixturePage = root.children.find(page => page.name === 'Figma Flow API Probe Lab');
  currentPage = fixturePage;
  const text = fixturePage.findAll(node => node.type === 'TEXT')[0];
  const originalStyles = {fontName: text._rangeFontName, fontSize: text._rangeFontSize,
    lineHeight: JSON.stringify(text._rangeLineHeight), letterSpacing: JSON.stringify(text._rangeLetterSpacing),
    fills: JSON.stringify(text._rangeFills)};
  const writes = await context.__fixture.runNativeApiLabOwnedWrites(figma, 'fixture-file');
  assert.ok(Number.isFinite(Date.parse(writes.observed_at)));
  assert.equal(writes.counts.success, 8);
  assert.equal(writes.counts.restoreFailed, 0);
  assert.deepEqual(Array.from(writes.methods, row => row.method).sort(),
    ['resize', 'getPluginData', 'setPluginData', 'setRangeFills', 'setRangeFontName', 'setRangeFontSize',
      'setRangeLetterSpacing', 'setRangeLineHeight'].sort());
  assert.equal(text._rangeFontName, originalStyles.fontName);
  assert.equal(text._rangeFontSize, originalStyles.fontSize);
  assert.equal(JSON.stringify(text._rangeLineHeight), originalStyles.lineHeight);
  assert.equal(JSON.stringify(text._rangeLetterSpacing), originalStyles.letterSpacing);
  assert.equal(JSON.stringify(text._rangeFills), originalStyles.fills);
  const component = fixturePage.findAll(node => node.type === 'COMPONENT')[0];
  const foreignInstance = component.createInstance();
  fixturePage.appendChild(foreignInstance);
  const reads = await context.__fixture.runNativeApiLabOwnedReads(figma, 'fixture-file');
  assert.equal(reads.counts.success, 2);
  assert.equal(reads.methods.find(row => row.method === 'getInstancesAsync').value.count, 1);
  assert.equal(reads.methods.find(row => row.method === 'getMainComponentAsync').value, 'linked-to-owned-component');
  assert.ok(!JSON.stringify(reads).includes(foreignInstance.id));
  await assert.rejects(create({...figma, fileKey: 'other-file'}, 'fixture-file'), /does not match/);
  const wrongEditor = {...figma, editorType: 'other-editor'};
  await assert.rejects(create(wrongEditor, 'fixture-file'), /Figma Design/);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
