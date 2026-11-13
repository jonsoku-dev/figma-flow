const test = require('node:test');
const assert = require('node:assert/strict');
const { runNativeValuePaths, safePathSummary } = require('../library/figma-recipes/inspection/values.js');
const policy = require('../library/figma-recipes/inspection/values.json');

class FakeNode {
  constructor(type, id) {
    this.type = type;
    this.id = id;
    this.name = '';
    this.x = 0;
    this.y = 0;
    this.width = 0;
    this.height = 0;
    this.children = [];
    this._data = {};
    this._reactions = [];
    this._effects = [];
    this._layoutGrids = [];
  }
  appendChild(node) {
    node.parent = this;
    this.children.push(node);
  }
  resize(width, height) { this.width = width; this.height = height; }
  setPluginData(key, value) { this._data[key] = value; }
  getPluginData(key) { return this._data[key] || ''; }
  findOne(predicate) {
    for (const child of this.children) {
      if (predicate(child)) return child;
      const nested = child.findOne(predicate);
      if (nested) return nested;
    }
    return null;
  }
  set reactions(value) { this._reactions = value; }
  get reactions() { return this._reactions; }
  async setReactionsAsync(value) {
    this._reactions = structuredClone(value).map(reaction => ({
      ...reaction,
      actions: reaction.actions?.map(action => ({
        ...action,
        transition: action.transition ? {...action.transition, duration: .25} : null,
      })),
    }));
  }
  set effects(value) {
    this._effects = structuredClone(value).map(effect => effect.type === 'INNER_SHADOW'
      ? {...effect, spread: 2} : effect);
  }
  get effects() { return this._effects; }
  set layoutGrids(value) {
    this._layoutGrids = structuredClone(value).map(grid => ({...grid,
      offset: grid.pattern === 'ROWS' ? 5 : grid.pattern === 'COLUMNS' ? 7 : grid.offset}));
  }
  get layoutGrids() { return this._layoutGrids; }
}

function fixturePlan() {
  const specs = [
    ['SimpleTransition', 'duration', 'prototype-reactions'],
    ['RowsColsLayoutGrid', 'offset', 'layout-grid-rows-columns'],
    ['RowsColsLayoutGrid', 'pattern', 'layout-grid-rows-columns'],
    ['InnerShadowEffect', 'spread', 'scene-effects'],
    ['VectorPath', 'data', 'vector-path-values'],
    ['VectorPath', 'windingRule', 'vector-path-values'],
  ];
  return {file: 'private-file', page: '77:1', graph_sha256: 'a'.repeat(64),
    policy_sha256: 'b'.repeat(64), service_graph_sha256: 'c'.repeat(64),
    api_source_ref: 'pinned-source', receipt_schema: 'figma-flow-native-value-observation-v2',
    capabilities: {getLocalVariableCollectionsAsync: false, getVariableByIdAsync: false,
      setBoundVariableForEffect: false, setBoundVariableForLayoutGrid: false},
    routes: policy.routes,
    candidate_members: specs.map(([owner, name, route], index) => ({owner, name, route,
      member_id: `member:${String(index + 1).padStart(64, '0')}`}))};
}

function fakeFigma(plan) {
  let next = 1;
  const page = new FakeNode('PAGE', '77:1');
  page.loadAsync = async () => {};
  const serviceRoot = new FakeNode('FRAME', '77:2');
  serviceRoot.setPluginData('figmaFlowServiceSpecimen', plan.service_graph_sha256);
  const vectorWrapper = new FakeNode('FRAME', '77:3');
  vectorWrapper.setPluginData('figmaFlowServiceSpecimen', 'Vector specimen');
  const vector = new FakeNode('VECTOR', '77:4');
  vector.vectorPaths = [{windingRule: 'NONZERO', data: 'M 0 0 L 10 0 L 0 10 Z'}];
  vectorWrapper.appendChild(vector);
  serviceRoot.appendChild(vectorWrapper);
  page.appendChild(serviceRoot);
  return {editorType: 'figma', fileKey: plan.file, currentPage: page,
    createFrame: () => new FakeNode('FRAME', `77:${next++}`),
    createRectangle: () => new FakeNode('RECTANGLE', `77:${next++}`),
    variables: {getLocalVariableCollectionsAsync: async () => []}};
}

test('native values use normalized getter return values, not assigned literals', async () => {
  const plan = fixturePlan();
  const receipt = await runNativeValuePaths(fakeFigma(plan), plan);
  const observed = new Map(receipt.observations.map(row => [`${row.owner}.${row.name}`, row.value]));
  assert.deepEqual(observed.get('SimpleTransition.duration'), {value: .25});
  assert.equal(observed.get('RowsColsLayoutGrid.offset').samples[0].value, 5);
  assert.equal(observed.get('RowsColsLayoutGrid.offset').samples[1].value, 7);
  assert.deepEqual(observed.get('InnerShadowEffect.spread'), {value: 2});
  assert.equal(observed.get('VectorPath.windingRule').value, 'NONZERO');
  assert.equal(observed.get('VectorPath.data').coordinateCount, 6);
  assert.equal(JSON.stringify(receipt).includes('M 0 0 L 10 0'), false);
  assert.equal(JSON.stringify(receipt).includes('77:4'), false);
  assert.equal('fileKey' in receipt, false);
  assert.equal('pageId' in receipt, false);
  assert.equal(receipt.scenarios.find(row => row.route === 'prototype-reactions').assignments_succeeded, 6);
});

test('vector path summaries never return the original path string', () => {
  const summary = safePathSummary('M 0 0 L 12 0 C 14 2 16 4 18 6 Z');
  assert.deepEqual(summary.commandCounts, {C: 1, L: 1, M: 1, Q: 0, Z: 1});
  assert.equal(summary.coordinateCount, 10);
  assert.equal(JSON.stringify(summary).includes('M 0 0'), false);
});
