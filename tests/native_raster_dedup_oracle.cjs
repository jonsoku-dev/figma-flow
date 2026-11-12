const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { readNativeSemantics } = require(path.join(process.cwd(), 'figma-bridge/native_semantic_read.js'));

const imageHash = 'same-native-image-hash';
const imageBytes = fs.readFileSync(path.join(process.cwd(), 'examples/regression-program/html/positive-assets/coffee.jpg'));
const base64 = imageBytes.toString('base64');

function node(id, asset, paint) {
  return {
    id, name: id, type: 'RECTANGLE', children: [], fills: paint ? [paint] : [],
    getPluginData: key => key === 'rasterAsset' ? asset : '',
    async loadAsync() {}, findAll() { return this.children; },
  };
}

function pageWithMarkedImages(count) {
  const marked = Array.from({ length: count }, (_, index) => node(
    `photo-${index}`, `photo-${index}`,
    { type: 'IMAGE', imageHash, scaleMode: 'FIT' },
  ));
  const unmarked = node('unmarked-private-image', '', {
    type: 'IMAGE', imageHash: 'unmarked-private-hash', scaleMode: 'FILL',
  });
  const page = {
    id: 'page', type: 'PAGE', children: [...marked, unmarked], getPluginData: () => '',
    async loadAsync() {}, findAll() { return this.children; },
  };
  for (const child of page.children) child.parent = page;
  return { page, marked, unmarked };
}

async function check(count) {
  let reads = 0;
  const fixture = pageWithMarkedImages(count);
  const figma = {
    getImageByHash: hash => hash === imageHash ? {
      getBytesAsync: async () => { reads += 1; return imageBytes; },
    } : null,
    base64Encode: bytes => Buffer.from(bytes).toString('base64'),
    variables: { getLocalVariableCollectionsAsync: async () => [] },
  };
  const result = await readNativeSemantics(figma, fixture.page);

  assert.equal(reads, 1, 'repeated native image must be read once');
  assert.equal(imageBytes.length, 115640, 'oracle JPEG fixture must remain the captured 115640-byte source');
  assert.equal(result.rasterImages?.[imageHash], base64, 'top-level raster image table must hold the actual encoded bytes');
  for (const row of result.nodes.filter(item => item.id.startsWith('photo-'))) {
    assert.equal(row.rasterImageRef, imageHash, 'marked row must reference its actual paint imageHash');
    assert.equal(row.fills[0].imageHash, row.rasterImageRef, 'row reference must match its actual IMAGE paint');
    assert.equal(Object.hasOwn(row, 'rasterImageBytes'), false, 'marked row must not duplicate inline raster bytes');
  }
  const unmarked = result.nodes.find(item => item.id === fixture.unmarked.id);
  assert.equal(Object.hasOwn(unmarked, 'rasterImageRef'), false, 'unmarked image must not receive a raster reference');
  assert.equal(Object.hasOwn(unmarked, 'rasterImageBytes'), false, 'unmarked image must not receive inline bytes');
  assert.deepEqual(Object.keys(result.rasterImages || {}), [imageHash], 'only the actual marked image may be in the table');
  const readback = { format: 'figma-flow-readback-v1', ...result };
  assert.ok(Buffer.byteLength(JSON.stringify(readback), 'utf8') < 2_000_000,
    'deduplicated native readback must stay below the 2,000,000-byte sync cap');
}

(async () => {
  const counts = process.argv.slice(2).map(Number);
  for (const count of counts.length ? counts : [14, 56]) {
    if (!Number.isInteger(count) || count < 1) throw new Error('Provide positive integer marked-node counts');
    await check(count);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
