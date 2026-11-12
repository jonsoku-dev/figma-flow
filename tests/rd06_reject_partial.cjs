const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const sourcePath = path.join(root, 'figma-bridge', 'native_semantic_read.js');
const source = fs.readFileSync(sourcePath, 'utf8');
assert.ok(source.includes('function requireFullNativeRead'), 'full consumers must reject a partial native read');
const {readNativeSemantics, requireFullNativeRead} = require(sourcePath);

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
  const summary = await readNativeSemantics(figma, page, {profile: 'summary', nodeIds: ['rect'], fields: ['width']});
  assert.throws(() => requireFullNativeRead(summary), /partial native read cannot be stored as full evidence/);
  const full = await readNativeSemantics(figma, page);
  const accepted = requireFullNativeRead(full);
  assert.equal(accepted.nodes.find(item => item.id === 'rect').width, 12);
  assert.ok(Array.isArray(accepted.styles));
  assert.ok(Array.isArray(accepted.variables));
  assert.equal(accepted.schema, undefined);
  const code = fs.readFileSync(path.join(root, 'figma-bridge/code.js'), 'utf8');
  assert.ok(code.includes('requireFullNativeRead(await readNativeSemantics(figma,page))'));
  const summaryHandler = code.slice(code.indexOf('message.type === "native-summary"'), code.indexOf('if (!sessionNonce || message.session_nonce !== sessionNonce || !["import", "export", "sync"]'));
  assert.ok(summaryHandler.includes('readNativeSemantics(figma, page, {profile: "summary"'));
  assert.ok(!summaryHandler.includes('requireFullNativeRead'));
  const nativeEdit = fs.readFileSync(path.join(root, 'figma-bridge/native_edit.js'), 'utf8');
  assert.ok(nativeEdit.includes('requireFullNativeRead(await readNativeSemantics(figma,page))'));
  const review = fs.readFileSync(path.join(root, 'figma-bridge/direction_review.js'), 'utf8');
  assert.equal(review.split('requireFullNativeRead(await readNativeSemantics(').length - 1, 2);
  const discovery = fs.readFileSync(path.join(root, 'tools/graph_sync.py'), 'utf8');
  assert.ok(discovery.includes('requireFullNativeRead(await readNativeSemantics(figma, page))'));
  const tasks = fs.readFileSync(path.join(root, 'docs/development-roadmap/RD-06-native-read/tasks.md'), 'utf8');
  assert.ok(tasks.includes('requireFullNativeRead'));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
