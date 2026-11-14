const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const plain = value => JSON.parse(JSON.stringify(value));
const fixed = (object, key, value) => Object.defineProperty(object, key, {value, writable: false, configurable: false, enumerable: true});

function bundle(measure) {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-read-descriptors-'));
  try {
    execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
      'import sys;sys.path.insert(0,sys.argv[1]);from graph_sync import discovery_bundle;' +
      'discovery_bundle("file-key","primary",[],sys.argv[2],read_measure=(sys.argv[3] or None))',
      path.join(root, 'tools'), path.join(output, 'bundle'), measure || ''], {cwd: root});
    return fs.readFileSync(path.join(output, 'bundle', 'code.js'), 'utf8');
  } finally {
    fs.rmSync(output, {recursive: true, force: true});
  }
}

function nativeHost() {
  const native = {fills: 0, thisMismatch: 0};
  const page = {};
  const rect = {};
  const method = (owner, fn) => function(...args) { if (this !== owner) native.thisMismatch++; return fn.apply(owner, args); };
  fixed(page, 'id', 'primary');
  fixed(page, 'type', 'PAGE');
  fixed(page, 'name', 'Primary');
  fixed(page, 'parent', null);
  fixed(rect, 'id', 'primary-rect');
  fixed(rect, 'type', 'RECTANGLE');
  fixed(rect, 'name', 'Rectangle');
  fixed(rect, 'parent', page);
  fixed(rect, 'width', 42);
  fixed(rect, 'height', 24);
  for (const node of [page, rect]) Object.defineProperty(node, 'fills', {get() { native.fills++; return []; }, configurable: false, enumerable: true});
  fixed(page, 'children', Object.freeze([rect]));
  fixed(page, 'findAll', method(page, () => [rect]));
  fixed(page, 'loadAsync', method(page, async () => {}));
  for (const node of [page, rect]) fixed(node, 'getPluginData', method(node, () => ''));
  const variables = {};
  fixed(variables, 'getLocalVariableCollectionsAsync', method(variables, async () => []));
  const messages = [];
  const figma = {currentPage: page, showUI() {}, ui: {postMessage(value) { messages.push(plain(value)); }}};
  fixed(figma, 'fileKey', 'file-key');
  fixed(figma, 'variables', variables);
  fixed(figma, 'getNodeByIdAsync', method(figma, async id => id === 'primary' ? page : null));
  return {figma, messages, native};
}

async function discover(code) {
  const host = nativeHost();
  vm.runInNewContext(code, {figma: host.figma, __html__: '', TextEncoder});
  const token = JSON.parse(code.match(/const GRAPH_PANEL_SESSION = ("[^"]+");/)[1]);
  await host.figma.ui.onmessage({type: 'read', session: token});
  return {readback: host.messages.at(-1).readback, native: host.native};
}

const content = ({observed_at, read_measurement, ...rest}) => rest;

(async () => {
  const baseline = await discover(bundle());
  assert.equal(baseline.readback.status, undefined, 'default discovery reads read-only native descriptors');
  const diagnostic = await discover(bundle('getter-counts'));
  if (diagnostic.readback.error) console.error('diagnostic discovery error:', diagnostic.readback.error.split('\n')[0]);
  assert.ok(diagnostic.readback.error === undefined, 'getter-counts must read read-only native descriptors without a proxy invariant error');
  assert.deepEqual(content(diagnostic.readback), content(baseline.readback), 'getter-counts must keep the default discovery content');
  const [row] = diagnostic.readback.read_measurement.pages;
  assert.equal(row.by_property.fills, diagnostic.native.fills, 'counted fills gets equal native getter executions');
  assert.equal(row.api_calls['figma.variables.getLocalVariableCollectionsAsync'].calls, 1, 'read-only figma.variables calls are counted');
  assert.equal(row.api_calls['node.findAll'].calls, 1, 'read-only node methods are counted');
  assert.equal(diagnostic.native.thisMismatch, 0, 'native methods run with the original object as this');
  const timed = await discover(bundle('timing'));
  assert.deepEqual(content(timed.readback), content(baseline.readback), 'timing keeps the default discovery content');
  console.log('read-only native descriptor measurement checks passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
