const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const root = path.join(__dirname, '..');
const sourcePath = path.join(root, 'figma-bridge', 'native_semantic_read.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.ok(source.includes('figma-flow-native-read-summary-v1'), 'summary profile must name its partial coverage');
assert.ok(source.includes('async function readNativeSemantics(figma, page)'));
const {readNativeSemantics, nativeReadGetterLedger} = require(sourcePath);

function node(id) {
  return {
    id, name: id, type: 'RECTANGLE', children: [], width: 12, height: 8, fills: [],
    getPluginData: () => '',
    async loadAsync() {},
    findAll() { return this.children; },
  };
}

(async () => {
  const rect = node('rect');
  const page = node('page');
  page.type = 'PAGE';
  page.children = [rect];
  rect.parent = page;
  const figma = {variables: {getLocalVariableCollectionsAsync: async () => []}};
  const request = {profile: 'summary', nodeIds: ['rect'], fields: ['width']};
  const summary = await readNativeSemantics(figma, page, request);
  assert.equal(summary.schema, 'figma-flow-native-read-summary-v1');
  assert.equal(summary.coverage.profile, 'summary');
  assert.deepEqual(summary.coverage.nodeIds, ['rect']);
  assert.deepEqual(summary.coverage.fields, ['width']);
  assert.equal(summary.coverage.complete, false);
  assert.ok(summary.coverage.omitted.includes('styles'));
  assert.ok(summary.coverage.omitted.includes('variables'));
  assert.ok(summary.coverage.omitted.includes('rasterImages'));
  assert.equal(Object.hasOwn(summary, 'variables'), false);
  assert.equal(Object.hasOwn(summary, 'rasterImages'), false);
  assert.equal(Object.hasOwn(summary, 'styles'), false);
  const full = await readNativeSemantics(figma, page);
  assert.equal(summary.nodes.find(item => item.id === 'rect').width, full.nodes.find(item => item.id === 'rect').width);
  assert.equal(full.nodes.find(item => item.id === 'rect').width, 12);
  assert.ok(Array.isArray(full.variables));
  assert.notEqual(full.schema, 'figma-flow-native-read-summary-v1');
  const fallback = await readNativeSemantics(figma, page, {profile: 'summary', nodeIds: ['rect'], fields: ['fills']});
  assert.notEqual(fallback.schema, 'figma-flow-native-read-summary-v1');
  assert.deepEqual(fallback.nodes.find(item => item.id === 'rect').fills, []);
  const fullLedger = await nativeReadGetterLedger(figma, page);
  const summaryLedger = await nativeReadGetterLedger(figma, page, request);
  assert.ok(summaryLedger.getters.includes('rect.width'));
  assert.ok(!summaryLedger.getters.includes('rect.fills'));
  assert.ok(summaryLedger.getters.length < fullLedger.getters.length);
  const viewSource = fs.readFileSync(path.join(root, 'panel-ui/src/nativeSummary.mjs'), 'utf8');
  assert.ok(viewSource.includes('export function nativeSummaryView'));
  assert.ok(viewSource.includes('read_only: true'));
  assert.ok(!viewSource.includes('send('));
  assert.ok(!viewSource.includes('fetch('));
  const {nativeSummaryView} = await import(pathToFileURL(path.join(root, 'panel-ui/src/nativeSummary.mjs')).href);
  const shown = nativeSummaryView(summary);
  assert.equal(shown.read_only, true);
  assert.equal(shown.ready, true);
  assert.equal(shown.coverage.complete, false);
  assert.equal(shown.rows[0].values[0].value, 12);
  assert.equal(nativeSummaryView(full).ready, false);
  const panel = fs.readFileSync(path.join(root, 'panel-ui/src/ImportPanel.jsx'), 'utf8');
  assert.ok(panel.includes('function NativeSummary'));
  assert.ok(panel.includes('native-summary'));
  assert.ok(panel.includes('nativeSummaryView('));
  const block = panel.slice(panel.indexOf('function NativeSummary'), panel.indexOf('function statusCopy'));
  assert.ok(block.includes('native-summary'));
  assert.ok(block.includes('부분 읽기'));
  assert.ok(!block.includes('send('));
  assert.ok(!block.includes('postMessage'));
  const bundle = fs.readFileSync(path.join(root, 'figma-bridge/assets/panels.js'), 'utf8');
  assert.ok(bundle.includes('native-summary'));
  assert.ok(bundle.includes('부분 읽기'));
  const code = fs.readFileSync(path.join(root, 'figma-bridge/code.js'), 'utf8');
  assert.ok(code.includes('message.type === "native-summary"'));
  assert.ok(code.includes('readNativeSemantics(figma, page, {profile: "summary"'));
  const tasks = fs.readFileSync(path.join(root, 'docs/development-roadmap/RD-06-native-read/tasks.md'), 'utf8');
  assert.ok(tasks.includes('native summary coverage'));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
