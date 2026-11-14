const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const plain = value => JSON.parse(JSON.stringify(value));

function bundle(measure) {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-read-measure-'));
  try {
    execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
      'import sys;sys.path.insert(0,sys.argv[1]);from graph_sync import discovery_bundle;' +
      'discovery_bundle("file-key","primary",["secondary"],sys.argv[2],read_measure=(sys.argv[3] or None))',
      path.join(root, 'tools'), path.join(output, 'bundle'), measure || ''], {cwd: root});
    return fs.readFileSync(path.join(output, 'bundle', 'code.js'), 'utf8');
  } finally {
    fs.rmSync(output, {recursive: true, force: true});
  }
}

function host(code) {
  const clock = {now: 0};
  const native = {fills: 0};
  function page(id) {
    const value = {id, type: 'PAGE', name: id, children: [], findAll() { return this.children; }, getPluginData() { return ''; },
      async loadAsync() { clock.now += 7; }};
    const child = {id: id + '-rect', parent: value, type: 'RECTANGLE', name: 'Rectangle', width: 42, height: 24, getPluginData() { return ''; }};
    for (const node of [value, child]) Object.defineProperty(node, 'fills', {get() { native.fills++; return []; }});
    value.children.push(child);
    return value;
  }
  const pages = new Map([['primary', page('primary')], ['secondary', page('secondary')]]);
  const messages = [];
  const figma = {fileKey: 'file-key', currentPage: pages.get('primary'),
    async getNodeByIdAsync(id) { clock.now += 3; return pages.get(id); },
    variables: {async getLocalVariableCollectionsAsync() { return []; }},
    showUI() {}, ui: {postMessage(value) { messages.push(plain(value)); }}};
  vm.runInNewContext(code, {figma, __html__: '', performance: {now: () => clock.now}, TextEncoder});
  const token = JSON.parse(code.match(/const GRAPH_PANEL_SESSION = ("[^"]+");/)[1]);
  const send = async type => { await figma.ui.onmessage({type, session: token}); return messages.at(-1).readback; };
  return {send, native};
}

const content = readback => {
  const {observed_at, read_measurement, ...rest} = readback;
  return rest;
};

test('default discovery bundle carries no measurement code or field', async () => {
  const code = bundle();
  assert.ok(!code.includes('installNativeReadMeasurement'));
  assert.ok(!code.includes('figma-flow-native-read-measurement-v1'));
  const full = await host(code).send('read');
  assert.equal(full.schema, 'figma-flow-graph-native-discovery-v1');
  assert.equal(Object.hasOwn(full, 'read_measurement'), false);
});

test('timing wraps only each full reader await and keeps discovery content', async () => {
  const baseline = await host(bundle()).send('read');
  const timed = host(bundle('timing'));
  const full = await timed.send('read');
  assert.deepEqual(content(full), content(baseline), 'measured discovery must return the same native content');
  const measured = full.read_measurement;
  assert.equal(measured.schema, 'figma-flow-native-read-measurement-v1');
  assert.equal(measured.mode, 'timing');
  assert.equal(measured.clock, 'performance.now');
  assert.deepEqual(measured.pages, [{pageId: 'primary', reader_elapsed_ms: 7}, {pageId: 'secondary', reader_elapsed_ms: 7}],
    'reader clock covers the reader loadAsync and excludes the outer page lookup');
  assert.equal(measured.discovery_elapsed_ms, 20, 'discovery clock adds both page lookups');
  const summary = await timed.send('native-summary');
  assert.equal(summary.schema, 'figma-flow-native-read-summary-v1');
  assert.equal(Object.hasOwn(summary, 'read_measurement'), false, 'summary requests pass through unmeasured');
  const again = await timed.send('read');
  assert.equal(again.read_measurement.pages.length, 2, 'each discovery owns a fresh measurement');
});

test('getter-counts records every executed native getter and API call without changing the read', async () => {
  const baseline = await host(bundle()).send('read');
  const counted = host(bundle('getter-counts'));
  const before = counted.native.fills;
  const full = await counted.send('read');
  assert.deepEqual(content(full), content(baseline));
  const [primary, secondary] = full.read_measurement.pages;
  assert.equal(primary.instrumented, true);
  assert.equal(primary.pageId, 'primary');
  assert.equal(secondary.pageId, 'secondary');
  assert.equal(primary.by_property.fills + secondary.by_property.fills, counted.native.fills - before,
    'counted fills gets equal the native getter executions inside the reader');
  for (const row of [primary, secondary]) {
    assert.equal(row.api_calls['node.loadAsync'].calls, 1);
    assert.equal(row.api_calls['node.findAll'].calls, 1);
    assert.equal(row.api_calls['figma.variables.getLocalVariableCollectionsAsync'].calls, 1);
    assert.equal(row.api_calls['node.loadAsync'].elapsed_ms, 7);
    assert.ok(row.node_property_gets >= Object.values(row.by_property).reduce((sum, value) => sum + value, 0));
    assert.ok(row.node_property_has > 0, 'field presence checks are counted separately');
    assert.ok(row.reader_result_bytes > 0);
  }
});

test('measured reader result equals the unwrapped reader and its byte count', async () => {
  const context = vm.createContext({TextEncoder, console});
  vm.runInContext(fs.readFileSync(path.join(root, 'figma-bridge/native_semantic_read.js'), 'utf8') + '\n' +
    fs.readFileSync(path.join(root, 'figma-bridge/native_read_measurement.js'), 'utf8') +
    '\nglobalThis.api = {readNativeSemantics, measureNativeRead};', context);
  const rect = {id: 'rect', type: 'RECTANGLE', name: 'rect', width: 12, height: 8, fills: [], getPluginData: () => ''};
  const page = {id: 'page', type: 'PAGE', name: 'page', children: [rect], getPluginData: () => '', async loadAsync() {}, findAll() { return this.children; }};
  rect.parent = page;
  const figma = {variables: {getLocalVariableCollectionsAsync: async () => []}};
  const direct = await context.api.readNativeSemantics(figma, page);
  const {read, row} = await context.api.measureNativeRead(context.api.readNativeSemantics, figma, page, 'getter-counts', () => 0);
  assert.deepEqual(plain(read), plain(direct));
  assert.equal(row.reader_result_bytes, new TextEncoder().encode(JSON.stringify(direct)).length);
  await assert.rejects(context.api.measureNativeRead(context.api.readNativeSemantics, figma, page, 'cache', () => 0), /Unknown native read measurement mode/);
});

test('generator refuses unknown modes and probe tasks before writing', () => {
  const never = path.join(os.tmpdir(), 'figma-flow-read-measure-never');
  assert.throws(() => execFileSync(process.env.PYTHON || 'python3', ['-B', path.join(root, 'tools/graph_sync.py'), 'discover',
    '--file-key', 'file-key', '--page-id', '1:1', '--out', never, '--read-measure', 'cache'], {cwd: root, stdio: 'pipe'}));
  assert.throws(() => execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
    'import sys;sys.path.insert(0,sys.argv[1]);from graph_sync import discovery_bundle;discovery_bundle("k","1:1",[],sys.argv[2],api_probe_path=sys.argv[3],read_measure="timing")',
    path.join(root, 'tools'), never, 'probe.json'], {cwd: root, stdio: 'pipe'}), /--read-measure/);
  assert.equal(fs.existsSync(never), false, 'rejected tasks write no bundle');
});
