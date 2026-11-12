const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const sourcePath = path.join(__dirname, '..', 'figma-bridge', 'native_semantic_read.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.ok(source.includes('function nativeReadGetterLedger'), 'full native read must record the getters it uses');
assert.ok(source.includes('async function readNativeSemantics(figma, page)'));
const {nativeReadGetterLedger} = require(sourcePath);

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
  const receipt = await nativeReadGetterLedger(figma, page);
  assert.equal(receipt.schema, 'figma-flow-native-read-ledger-v1');
  assert.equal(receipt.full.nodes.find(item => item.id === 'rect').width, 12);
  assert.deepEqual(receipt.full.nodes.find(item => item.id === 'rect').fills, []);
  assert.ok(receipt.getters.includes('rect.width'));
  assert.ok(receipt.getters.includes('rect.fills'));
  assert.ok(!receipt.getters.includes('rect.exportAsync'));
  const again = await nativeReadGetterLedger(figma, page);
  assert.deepEqual(again.getters, receipt.getters);
  const tasks = fs.readFileSync(path.join(__dirname, '..', 'docs/development-roadmap/RD-06-native-read/tasks.md'), 'utf8');
  assert.ok(tasks.includes('nativeReadGetterLedger'));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
