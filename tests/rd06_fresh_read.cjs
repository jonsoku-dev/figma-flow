const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const sourcePath = path.join(root, 'figma-bridge', 'native_semantic_read.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.ok(source.includes('native read keeps no session snapshot'), 'native read must not serve a stored snapshot');
assert.ok(source.includes('function nativeReadSessionSnapshot'));
assert.ok(!source.includes('clientStorage'));
assert.ok(source.includes('async function readNativeSemantics(figma, page)'));
const {readNativeSemantics, nativeReadSessionSnapshot} = require(sourcePath);

function node(id) {
  return {
    id, name: id, type: 'RECTANGLE', children: [], width: 12, height: 8, fills: [],
    getPluginData: () => '',
    async loadAsync() { this.loads = (this.loads || 0) + 1; },
    findAll() { return this.children; },
  };
}

(async () => {
  assert.equal(nativeReadSessionSnapshot(), null);
  const rect = node('rect');
  const page = node('page');
  page.type = 'PAGE';
  page.children = [rect];
  rect.parent = page;
  const figma = {variables: {getLocalVariableCollectionsAsync: async () => []}};
  const request = {profile: 'summary', nodeIds: ['rect'], fields: ['width']};
  const first = await readNativeSemantics(figma, page);
  const firstSummary = await readNativeSemantics(figma, page, request);
  assert.equal(first.nodes.find(item => item.id === 'rect').width, 12);
  assert.equal(firstSummary.nodes.find(item => item.id === 'rect').width, 12);
  rect.width = 21;
  const second = await readNativeSemantics(figma, page);
  const secondSummary = await readNativeSemantics(figma, page, request);
  assert.equal(second.nodes.find(item => item.id === 'rect').width, 21);
  assert.equal(secondSummary.nodes.find(item => item.id === 'rect').width, 21);
  assert.notEqual(first, second);
  assert.notEqual(firstSummary, secondSummary);
  assert.equal(page.loads, 4);
  const tasks = fs.readFileSync(path.join(root, 'docs/development-roadmap/RD-06-native-read/tasks.md'), 'utf8');
  assert.ok(tasks.includes('session cache를 넣지 않는다'));
  assert.ok(tasks.includes('TTL은 coverage가 아니다'));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
