const assert = require('node:assert/strict');
const { readNativeSemantics } = require('../figma-bridge/native_semantic_read.js');

function node(id, asset, paint, image) {
  return {
    id, name: id, type: 'RECTANGLE', children: [], fills: paint ? [paint] : [],
    getPluginData: key => key === 'rasterAsset' ? asset : '',
    async loadAsync() {}, findAll() { return this.children; }, image,
  };
}
function figmaFor(images) {
  return {
    getImageByHash: hash => images[hash],
    base64Encode: bytes => Buffer.from(bytes).toString('base64'),
    variables: { getLocalVariableCollectionsAsync: async () => [] },
  };
}

(async () => {
  const owned = node('owned', 'photo', { type: 'IMAGE', imageHash: 'owned-hash', scaleMode: 'FIT' });
  const unrelated = node('unrelated', '', { type: 'IMAGE', imageHash: 'private-hash', scaleMode: 'FILL' });
  const frame = { ...node('frame', '', null), type: 'FRAME', clipsContent: false,
    reactions: [{ trigger: { type: 'ON_CLICK' }, actions: [{ type: 'NODE', navigation: 'NAVIGATE', destinationId: 'other-frame' }] }] };
  const page = { id: 'page', type: 'PAGE', children: [owned, unrelated, frame], getPluginData: () => '', async loadAsync() {}, findAll() { return this.children; } };
  owned.parent = unrelated.parent = frame.parent = page;
  const result = await readNativeSemantics(figmaFor({ 'owned-hash': { getBytesAsync: async () => Uint8Array.from([1, 2, 3]) } }), page);
  const row = result.nodes.find(item => item.id === 'owned');
  assert.equal(row.rasterAsset, 'photo');
  assert.equal(row.rasterImageBytes, 'AQID');
  assert.equal(result.nodes.find(item => item.id === 'unrelated').rasterImageBytes, undefined);
  const actualFrame = result.nodes.find(item => item.id === 'frame');
  assert.equal(actualFrame.clipsContent, false);
  assert.deepEqual(actualFrame.reactions, frame.reactions);

  const missing = await readNativeSemantics(figmaFor({}), page);
  assert.match(missing.nodes.find(item => item.id === 'owned').unavailable_fields.rasterImageBytes, /unavailable/);
  const failed = await readNativeSemantics(figmaFor({ 'owned-hash': { getBytesAsync: async () => { throw new Error('read denied'); } } }), page);
  assert.match(failed.nodes.find(item => item.id === 'owned').unavailable_fields.rasterImageBytes, /read denied/);
})().catch(error => { console.error(error); process.exitCode = 1; });
