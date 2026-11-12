const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const sourcePath = path.join(root, 'figma-bridge', 'native_semantic_read.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.ok(source.includes('function compareNativeReadProfiles'), 'native read comparison must report measured bytes');
assert.ok(!source.includes('9.16MB'));
assert.ok(!source.includes('0.68MB'));
const {readNativeSemantics, compareNativeReadProfiles} = require(sourcePath);

function node(id) {
  return {
    id, name: id, type: 'RECTANGLE', children: [], width: 12, height: 8, fills: [],
    getPluginData: () => '',
    async loadAsync() {},
    findAll() { return this.children; },
  };
}

function utf8JsonBytes(value) {
  return new TextEncoder().encode(JSON.stringify(value)).length;
}

(async () => {
  const rect = node('rect');
  const page = node('page');
  page.type = 'PAGE';
  page.children = [rect];
  rect.parent = page;
  const figma = {variables: {getLocalVariableCollectionsAsync: async () => []}};
  const request = {profile: 'summary', nodeIds: ['rect'], fields: ['width']};
  const full = await readNativeSemantics(figma, page);
  const summary = await readNativeSemantics(figma, page, request);
  const measured = await compareNativeReadProfiles(figma, page, request);
  assert.equal(measured.schema, 'figma-flow-native-read-comparison-v1');
  assert.equal(measured.requestedFieldsEqual, true);
  assert.equal(summary.nodes.find(item => item.id === 'rect').width, full.nodes.find(item => item.id === 'rect').width);
  assert.ok(measured.getters.summary.includes('rect.width'));
  assert.ok(!measured.getters.summary.includes('rect.fills'));
  assert.ok(measured.getters.full.includes('rect.width'));
  assert.ok(measured.getters.full.includes('rect.fills'));
  assert.ok(measured.getters.summary.length < measured.getters.full.length);
  assert.equal(measured.bytes.full, utf8JsonBytes(full));
  assert.equal(measured.bytes.summary, utf8JsonBytes(summary));
  assert.ok(measured.bytes.summary < measured.bytes.full);
  assert.equal(measured.invalidation, 'unmeasured');
  assert.equal(Object.hasOwn(measured, 'wallClockMs'), false);
  const tasks = fs.readFileSync(path.join(root, 'docs/development-roadmap/RD-06-native-read/tasks.md'), 'utf8');
  assert.ok(tasks.includes('compareNativeReadProfiles'));
  assert.ok(tasks.includes('wall-clock은 측정하지 않는다'));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
