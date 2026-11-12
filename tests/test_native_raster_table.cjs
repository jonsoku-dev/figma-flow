const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { mergeNativeRasterImages, requireFullNativeRead } = require('../figma-bridge/native_semantic_read.js');

const source = fs.readFileSync(require.resolve('../figma-bridge/code.js'), 'utf8');
const match = source.match(/async function readback\(pages, scope\) \{[\s\S]*?\n\}\nasync function exportReadback/);
assert.ok(match, 'actual readback function exists');

async function readWith(tables) {
  const reads = new Map(tables.map(([id, rasterImages]) => [id, { nodes: [], styles: [], unavailableFields: [], rasterImages }]));
  const sandbox = {
    Object,
    PAYLOAD: { expected_native_handoff: {} },
    mergeNativeRasterImages,
    requireFullNativeRead,
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

function generateDiscoveryCode(root, output) {
  const python = [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(path.join(root, 'tools'))})`,
    'from graph_sync import discovery_bundle',
    `print(json.dumps(discovery_bundle('file-key', 'page-one', ['page-two'], ${JSON.stringify(output)})))`,
  ].join('\n');
  const generated = spawnSync(process.env.PYTHON || 'python3', ['-c', python], { cwd: root, encoding: 'utf8' });
  assert.equal(generated.status, 0, generated.stderr || generated.stdout);
  return fs.readFileSync(path.join(output, 'code.js'), 'utf8');
}

function discoveryPage(id) {
  const page = { id, type: 'PAGE', name: id, children: [], getPluginData: () => '', async loadAsync() {}, findAll() { return this.children; } };
  for (const [suffix, hash] of [['a', 'shared-hash'], ['b', 'shared-hash'], ['c', 'other-hash']]) {
    const node = { id: `${id}-${suffix}`, parent: page, type: 'RECTANGLE', name: `${id}-${suffix}`,
      fills: [{ type: 'IMAGE', imageHash: hash }], getPluginData: key => key === 'rasterAsset' ? 'cover' : '' };
    page.children.push(node);
  }
  return page;
}

async function runGeneratedDiscovery(code, conflict = false) {
  let sharedReads = 0;
  const pages = new Map([['page-one', discoveryPage('page-one')], ['page-two', discoveryPage('page-two')]]);
  const figma = {
    fileKey: 'file-key', currentPage: pages.get('page-one'),
    async getNodeByIdAsync(id) { return pages.get(id); },
    getImageByHash(hash) {
      return { async getBytesAsync() {
        if (hash === 'shared-hash') {
          sharedReads++;
          return Uint8Array.from(conflict && sharedReads > 1 ? [9, 9, 9] : [1, 2, 3]);
        }
        return Uint8Array.from([4, 5, 6]);
      } };
    },
    base64Encode(bytes) { return Buffer.from(bytes).toString('base64'); },
    variables: { async getLocalVariableCollectionsAsync() { return []; } },
    showUI() {}, ui: { postMessage() {} },
  };
  const context = { figma, __html__: '', Buffer };
  vm.runInNewContext(`${code}\nglobalThis.runDiscovery = discoverGraphNative; globalThis.discoveryScope = DISCOVERY_SCOPE;`, context);
  return context.runDiscovery(figma, context.discoveryScope);
}

async function testGeneratedDiscovery() {
  const root = process.cwd();
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-discovery-raster-'));
  try {
    const code = generateDiscoveryCode(root, path.join(temporary, 'bundle'));
    const result = await runGeneratedDiscovery(code);
    assert.deepEqual({ ...result.rasterImages }, { 'shared-hash': 'AQID', 'other-hash': 'BAUG' });
    assert.equal(result.nodes.filter(node => node.rasterImageRef === 'shared-hash').length, 4);
    assert.equal(result.nodes.filter(node => node.rasterImageBytes !== undefined).length, 0);
    await assert.rejects(runGeneratedDiscovery(code, true), /Conflicting native raster bytes for image hash shared-hash/);
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

(async () => {
  const same = await readWith([['first', { shared: 'AQID', firstOnly: 'BAUG' }], ['second', { shared: 'AQID', secondOnly: 'BwgJ' }]]);
  assert.deepEqual({ ...same.rasterImages }, { shared: 'AQID', firstOnly: 'BAUG', secondOnly: 'BwgJ' });

  await assert.rejects(
    readWith([['first', { shared: 'AQID' }], ['second', { shared: 'BAUG' }]]),
    /Conflicting native raster bytes for image hash shared/,
  );
  await testGeneratedDiscovery();
})().catch(error => { console.error(error); process.exitCode = 1; });
