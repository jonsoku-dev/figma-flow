const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
const root = process.cwd();
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-discovery-raster-'));
try {
  const output = path.join(temporary, 'bundle');
  const python = [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(path.join(root, 'tools'))})`,
    'from graph_sync import discovery_bundle',
    `print(json.dumps(discovery_bundle('file-key', 'page-one', ['page-two'], ${JSON.stringify(output)})))`,
  ].join('\n');
  const generated = spawnSync(process.env.PYTHON || 'python3', ['-c', python], { cwd: root, encoding: 'utf8' });
  assert.equal(generated.status, 0, generated.stderr || generated.stdout);
  const bundle = JSON.parse(generated.stdout);
  const code = fs.readFileSync(path.join(output, 'code.js'), 'utf8');
  const bytes = Buffer.from([1, 2, 3, 4]);
  const hash = 'shared-image-hash';
  const expectedBase64 = bytes.toString('base64');
  let reads = 0;
  const makeNode = (id, parent, marked) => ({
    id, parent, type: 'RECTANGLE', name: id, fills: [{ type: 'IMAGE', imageHash: hash }],
    getPluginData: key => key === 'rasterAsset' && marked ? 'cover' : '',
  });
  const makePage = id => {
    const page = { id, type: 'PAGE', name: id, children: [], getPluginData: () => '', async loadAsync() {}, findAll() { return this.children; } };
    page.children.push(makeNode(`${id}-marked-a`, page, true), makeNode(`${id}-marked-b`, page, true));
    return page;
  };
  const pages = new Map([['page-one', makePage('page-one')], ['page-two', makePage('page-two')]]);
  const figma = {
    fileKey: 'file-key', currentPage: pages.get('page-one'),
    async getNodeByIdAsync(id) { return pages.get(id); },
    getImageByHash() { return { async getBytesAsync() { reads++; return bytes; } }; },
    base64Encode(value) { return Buffer.from(value).toString('base64'); },
    variables: { async getLocalVariableCollectionsAsync() { return []; } },
    showUI() {}, ui: { postMessage() {} },
  };
  const context = { figma, __html__: '', Buffer };
  vm.runInNewContext(`${code}\nglobalThis.runDiscovery = discoverGraphNative; globalThis.discoveryScope = DISCOVERY_SCOPE;`, context);
  const result = await context.runDiscovery(figma, context.discoveryScope);
  assert.ok(result.rasterImages?.[hash] === expectedBase64, 'discovery must preserve actual raster bytes');
  assert.equal(result.nodes.filter(node => node.rasterImageRef === hash).length, 4);
  assert.equal(result.nodes.filter(node => node.rasterImageBytes !== undefined).length, 0);
  assert.equal(reads, 2);
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}
}

main().catch(error => { console.error(error); process.exitCode = 1; });
