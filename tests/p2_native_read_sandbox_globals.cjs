const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

// The Figma plugin sandbox is not Node or a browser page: TextEncoder, TextDecoder, Buffer, performance,
// process and require are absent there. Guests run in a bare vm context; the byte oracle stays on the host.
const HOST_ONLY = ['TextEncoder', 'TextDecoder', 'Buffer', 'performance', 'process', 'require'];
const READER_TEXT_SHA256 = '8d4f0e5f883a1b46d8b919320b094d0fb0ee209442df1f424c5dc33c5999bb22';
const root = path.resolve(__dirname, '..');
const readerPath = path.join(root, 'figma-bridge/native_semantic_read.js');
const plain = value => JSON.parse(JSON.stringify(value));
const hostBytes = text => Buffer.byteLength(text, 'utf8');

function sandbox(extra = {}) {
  const context = vm.createContext({...extra});
  const missing = JSON.parse(vm.runInContext(`JSON.stringify([${HOST_ONLY.map(name => `typeof ${name}`).join(',')}])`, context));
  assert.deepEqual(missing, HOST_ONLY.map(() => 'undefined'), 'sandbox must lack Node and browser host globals');
  return context;
}

function bundle(measure) {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-read-sandbox-'));
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

function fixture() {
  const page = {id: 'primary', type: 'PAGE', name: '페이지 🎨', children: [], getPluginData: () => '', async loadAsync() {},
    findAll() { return this.children; }};
  const names = ['한국어 버튼', 'emoji 👩‍💻', 'lone \ud800 high', 'lone \udc00 low', 'escaped "quote" \\ \n\t', 'ascii'];
  for (const [index, name] of names.entries())
    page.children.push({id: `primary-${index}`, parent: page, type: 'RECTANGLE', name, width: 10 + index, height: 4, fills: [], getPluginData: () => ''});
  return page;
}

function figmaFor(page, messages) {
  return {fileKey: 'file-key', currentPage: page, async getNodeByIdAsync(id) { return id === page.id ? page : null; },
    variables: {async getLocalVariableCollectionsAsync() { return []; }},
    showUI() {}, ui: {postMessage(value) { messages.push(plain(value)); }}};
}

async function discover(code) {
  const page = fixture(), messages = [];
  const figma = figmaFor(page, messages);
  vm.runInContext(code, sandbox({figma, __html__: ''}));
  const token = JSON.parse(code.match(/const GRAPH_PANEL_SESSION = ("[^"]+");/)[1]);
  await figma.ui.onmessage({type: 'read', session: token});
  return messages.at(-1).readback;
}

const content = ({observed_at, read_measurement, ...rest}) => rest;

(async () => {
  const source = fs.readFileSync(readerPath, 'utf8');
  const reader = source.slice(source.indexOf('async function readNativeSemantics(figma, page) {'), source.indexOf('async function nativeReadGetterLedger'));
  assert.equal(crypto.createHash('sha256').update(reader).digest('hex'), READER_TEXT_SHA256, 'readNativeSemantics text must stay unchanged');

  const plainRead = await discover(bundle());
  assert.equal(plainRead.error, undefined, 'default discovery must run in the Figma-like sandbox');
  const diagnostic = await discover(bundle('getter-counts'));
  if (diagnostic.error) console.error('sandbox diagnostic error:', diagnostic.error);
  assert.ok(diagnostic.error === undefined, 'getter-counts diagnostic must run in a Figma-like sandbox without TextEncoder');
  assert.deepEqual(content(diagnostic), content(plainRead), 'diagnostic discovery keeps the default discovery content');
  const [row] = diagnostic.read_measurement.pages;
  assert.equal(diagnostic.read_measurement.clock, 'Date.now', 'the sandbox has no performance clock');
  const hostRead = await require(readerPath).readNativeSemantics(figmaFor(fixture(), []), fixture());
  assert.equal(row.reader_result_bytes, hostBytes(JSON.stringify(hostRead)), 'reader_result_bytes equals the host UTF-8 oracle');

  const guest = sandbox();
  vm.runInContext(source, guest);
  const cases = ['', 'ascii', '가', '한국어', '🎨', '👩‍💻', '\ud800', '\udc00', '\udc00\ud800', 'a\ud800b', '"\\\n\t\u0001', '\u007f\u0080߿ࠀ￿',
    {name: '한국어 🎨', nested: ['\ud800', 1, null, true]}, [1.5, 'x'], null];
  for (const value of cases) {
    let measured;
    try { measured = vm.runInContext('utf8JsonBytes', guest)(value); }
    catch (error) { measured = String(error.message || error); }
    assert.equal(measured, hostBytes(JSON.stringify(value)), 'utf8JsonBytes equals the host UTF-8 oracle for JSON text');
  }
  const rawGuest = sandbox();
  vm.runInContext(source + '\nJSON.stringify = value => value;', rawGuest);
  for (const raw of ['\ud800', '\udc00', 'x\ud83dy', '🎨', '가']) {
    let measured;
    try { measured = vm.runInContext('utf8JsonBytes', rawGuest)(raw); }
    catch (error) { measured = String(error.message || error); }
    assert.equal(measured, hostBytes(raw), 'an engine that leaves lone surrogates unescaped still gets UTF-8 replacement lengths');
  }
  console.log('Figma-like sandbox diagnostic and UTF-8 byte oracle checks passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
