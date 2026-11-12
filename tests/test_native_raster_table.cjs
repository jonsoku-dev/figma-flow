const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../figma-bridge/code.js'), 'utf8');
const match = source.match(/async function readback\(pages, scope\) \{[\s\S]*?\n\}\nasync function exportReadback/);
assert.ok(match, 'actual readback function exists');

async function readWith(tables) {
  const reads = new Map(tables.map(([id, rasterImages]) => [id, { nodes: [], styles: [], unavailableFields: [], rasterImages }]));
  const sandbox = {
    Object,
    PAYLOAD: { expected_native_handoff: {} },
    figma: { variables: {
      getLocalVariableCollectionsAsync: async () => [],
      getLocalVariablesAsync: async () => [],
    } },
    info: () => ({}),
    snapshot: async page => ({ id: page.id }),
    readNativeSemantics: async (_figma, page) => reads.get(page.id),
  };
  vm.runInNewContext(`${match[0].replace(/\nasync function exportReadback$/, '')}\nglobalThis.runReadback = readback;`, sandbox);
  const pages = tables.map(([id]) => ({ id, async loadAsync() {} }));
  return sandbox.runReadback(pages, 'test');
}

(async () => {
  const same = await readWith([['first', { shared: 'AQID', firstOnly: 'BAUG' }], ['second', { shared: 'AQID', secondOnly: 'BwgJ' }]]);
  assert.deepEqual({ ...same.rasterImages }, { shared: 'AQID', firstOnly: 'BAUG', secondOnly: 'BwgJ' });

  await assert.rejects(
    readWith([['first', { shared: 'AQID' }], ['second', { shared: 'BAUG' }]]),
    /Conflicting native raster bytes for image hash shared/,
  );
})().catch(error => { console.error(error); process.exitCode = 1; });
