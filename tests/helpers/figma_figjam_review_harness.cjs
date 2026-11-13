const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const sourceA = fs.readFileSync(process.argv[2], 'utf8');
const expectedA = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sourceB = fs.readFileSync(process.argv[4], 'utf8');
const expectedB = JSON.parse(fs.readFileSync(process.argv[5], 'utf8'));

function world() {
  let nextId = 0;
  const page = { id: 'page-1', children: [], selection: [] };
  const messages = [];
  const text = () => ({ characters: '', fontName: undefined });
  const create = type => {
    const data = new Map();
    const node = {
      id: `${type}-${++nextId}`,
      type,
      name: '',
      x: 0,
      y: 0,
      width: 100,
      height: 100,
      removed: false,
      getPluginData(key) { return data.get(key) ?? ''; },
      setPluginData(key, value) { data.set(key, value); },
      remove() {
        this.removed = true;
        page.children = page.children.filter(child => child !== this);
      },
    };
    page.children.push(node);
    return node;
  };
  const figma = {
    editorType: 'figjam',
    mode: 'default',
    currentPage: page,
    viewport: {
      center: { x: 600, y: 400 },
      scrollAndZoomIntoView() {},
    },
    async loadFontAsync() {},
    createSticky() {
      const node = create('STICKY');
      node.text = text();
      return node;
    },
    createTable(rowCount, columnCount) {
      const node = create('TABLE');
      const cells = Array.from({ length: rowCount }, () => Array.from({ length: columnCount }, () => ({ text: text() })));
      node.cellAt = (row, column) => cells[row][column];
      node.resizeColumn = () => {};
      return node;
    },
    createCodeBlock() {
      const node = create('CODE_BLOCK');
      node.code = '';
      return node;
    },
    createConnector() {
      const node = create('CONNECTOR');
      node.text = text();
      return node;
    },
    closePlugin(message) { messages.push(String(message ?? '')); },
  };
  return { figma, page, messages };
}

async function run(source, state) {
  vm.runInNewContext(source, vm.createContext({ figma: state.figma }));
  await new Promise(resolve => setImmediate(resolve));
  return state.messages.at(-1);
}

function addLegacyBoard(state, expected) {
  const graph = expected.graph;
  const stamp = (node, semanticId) => {
    node.setPluginData('figmaFlowRecipe', 'figjam-review-planner');
    node.setPluginData('figmaFlowGraphSha256', expected.sourceSha256);
    node.setPluginData('figmaFlowSemanticId', semanticId);
    return node;
  };
  const display = (value, limit) => value.length <= limit ? value : value.slice(0, limit - 1) + '…';
  const title = stamp(state.figma.createSticky(), 'meta:title');
  title.text.characters = `Review planner · ${display(graph.title, 120)}\nGraph ${graph.id} · SHA-256 ${expected.sourceSha256}`;
  const byId = new Map();
  graph.nodes.forEach(item => {
    const sticky = stamp(state.figma.createSticky(), 'node:' + item.id);
    sticky.text.characters = `${item.kind.toUpperCase()} · ${item.status}\n${display(item.title, 120)}\n${display(item.detail, 320)}\nID: ${display(item.id, 128)}`;
    byId.set(item.id, sticky);
  });
  const table = stamp(state.figma.createTable(graph.nodes.length + 1, 4), 'meta:table');
  const rows = [
    ['Kind · status', 'Semantic ID', 'Node title', 'Designer ↔ developer note'],
    ...graph.nodes.map(item => [item.kind + ' · ' + item.status, display(item.id, 160),
      display(item.title, 160), display(item.detail, 280)]),
  ];
  rows.forEach((cells, row) => cells.forEach((value, column) => {
    table.cellAt(row, column).text.characters = value;
  }));
  const evidence = stamp(state.figma.createCodeBlock(), 'meta:evidence');
  evidence.code = JSON.stringify({
    recipe: 'figjam-review-planner',
    graphId: graph.id,
    graphSha256: expected.sourceSha256,
    nodes: graph.nodes.map(item => ({ id: item.id, kind: item.kind, type: item.type, status: item.status, title: item.title })),
    semanticEdges: graph.edges.map(edge => ({ id: 'edge:' + JSON.stringify([edge.from, edge.to, edge.type]),
      from: edge.from, to: edge.to, type: edge.type })),
  }, null, 2);
  graph.edges.forEach(edge => {
    const connector = stamp(state.figma.createConnector(), 'edge:' + JSON.stringify([edge.from, edge.to, edge.type]));
    connector.connectorStart = { endpointNodeId: byId.get(edge.from).id, magnet: 'AUTO' };
    connector.connectorEnd = { endpointNodeId: byId.get(edge.to).id, magnet: 'AUTO' };
    connector.text.characters = display(edge.type, 80);
  });
}

(async () => {
  assert.equal(expectedA.sourceSha256, expectedB.sourceSha256);
  assert.notEqual(expectedA.selectionSha256, expectedB.selectionSha256);
  const state = world();
  const countA = expectedA.graph.nodes.length + expectedA.graph.edges.length + 3;
  const countB = expectedB.graph.nodes.length + expectedB.graph.edges.length + 3;

  const firstA = await run(sourceA, state);
  assert.match(firstA, /Created /);
  assert.equal(state.page.children.length, countA);

  const firstB = await run(sourceB, state);
  assert.match(firstB, /Created /);
  assert.equal(state.page.children.length, countA + countB);
  for (const [expected, selectionSha] of [[expectedA, expectedA.selectionSha256], [expectedB, expectedB.selectionSha256]]) {
    const nodes = state.page.children.filter(node => node.getPluginData('figmaFlowSelectionSha256') === selectionSha);
    assert.equal(nodes.length, expected.graph.nodes.length + expected.graph.edges.length + 3);
    assert.ok(nodes.every(node => node.getPluginData('figmaFlowGraphId') === expected.graph.id));
    assert.ok(nodes.every(node => node.getPluginData('figmaFlowGraphSha256') === expected.sourceSha256));
    const semanticIds = nodes.map(node => node.getPluginData('figmaFlowSemanticId')).sort();
    const expectedIds = [
      'meta:title', 'meta:table', 'meta:evidence',
      ...expected.graph.nodes.map(node => `node:${node.id}`),
      ...expected.graph.edges.map(edge => `edge:${JSON.stringify([edge.from, edge.to, edge.type])}`),
    ].sort();
    assert.equal(JSON.stringify(semanticIds), JSON.stringify(expectedIds));
  }

  const firstBoardA = state.page.children.filter(node => node.getPluginData('figmaFlowSelectionSha256') === expectedA.selectionSha256);
  const secondA = await run(sourceA, state);
  assert.match(secondA, /Already on this page:/);
  assert.equal(state.page.children.length, countA + countB);
  assert.equal(state.page.selection.length, firstBoardA.length);

  const edited = firstBoardA.find(node => node.getPluginData('figmaFlowSemanticId').startsWith('edge:'));
  assert.ok(edited);
  edited.setPluginData('figmaFlowSemanticId', 'edge:manual-edit');
  const countBeforeConflict = state.page.children.length;
  const conflict = await run(sourceA, state);
  assert.match(conflict, /partial board.*exists/);
  assert.equal(state.page.children.length, countBeforeConflict);

  const migrated = world();
  addLegacyBoard(migrated, expectedA);
  const legacyCount = migrated.page.children.length;
  const legacyEvidence = migrated.page.children.find(node => node.type === 'CODE_BLOCK').code;
  const subsetBeforeLegacyMigration = await run(sourceB, migrated);
  assert.match(subsetBeforeLegacyMigration, /Created /);
  assert.equal(migrated.page.children.length, legacyCount + countB);
  const migration = await run(sourceA, migrated);
  assert.match(migration, /Migrated and selected the existing FigJam review/);
  assert.equal(migrated.page.children.length, legacyCount + countB);
  const migratedNodes = migrated.page.children.filter(node => node.getPluginData('figmaFlowSelectionSha256') === expectedA.selectionSha256);
  assert.equal(migratedNodes.length, countA);
  assert.ok(migratedNodes.every(node => node.getPluginData('figmaFlowGraphId') === expectedA.graph.id));
  assert.equal(migrated.page.children.find(node => node.type === 'CODE_BLOCK').code, legacyEvidence);
  const migratedAgain = await run(sourceA, migrated);
  assert.match(migratedAgain, /Already on this page:/);
  assert.equal(migrated.page.children.length, legacyCount + countB);

  const editedLegacy = world();
  addLegacyBoard(editedLegacy, expectedA);
  const legacyNode = editedLegacy.page.children.find(node => node.getPluginData('figmaFlowSemanticId') === `node:${expectedA.graph.nodes[0].id}`);
  legacyNode.text.characters += '\nmanual edit';
  const editedCount = editedLegacy.page.children.length;
  const rejectedLegacy = await run(sourceA, editedLegacy);
  assert.match(rejectedLegacy, /Legacy board content conflicts/);
  assert.equal(editedLegacy.page.children.length, editedCount);
  assert.ok(editedLegacy.page.children.every(node => !node.getPluginData('figmaFlowSelectionSha256')));

  const ambiguousLegacy = world();
  addLegacyBoard(ambiguousLegacy, expectedA);
  addLegacyBoard(ambiguousLegacy, expectedA);
  const ambiguousCount = ambiguousLegacy.page.children.length;
  const ambiguous = await run(sourceA, ambiguousLegacy);
  assert.match(ambiguous, /Legacy board markers are ambiguous/);
  assert.equal(ambiguousLegacy.page.children.length, ambiguousCount);
  assert.ok(ambiguousLegacy.page.children.every(node => !node.getPluginData('figmaFlowSelectionSha256')));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
