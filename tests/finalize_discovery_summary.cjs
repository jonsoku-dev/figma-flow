const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const plain = value => JSON.parse(JSON.stringify(value));

async function main() {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-discovery-summary-'));
  try {
    const output = path.join(temporary, 'bundle');
    execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
      'import sys;sys.path.insert(0,sys.argv[1]);from graph_sync import discovery_bundle;discovery_bundle("file-key","primary",["secondary"],sys.argv[2])',
      path.join(root, 'tools'), output], {cwd: root});
    const code = fs.readFileSync(path.join(output, 'code.js'), 'utf8');
    const messages = [], reads = [], lookups = [];
    let fullGetterReads = 0, release = null;
    function page(id) {
      const value = {id, type: 'PAGE', name: id, children: [], async loadAsync() { if (release) await release.promise; },
        findAll() {return this.children;}, getPluginData() {return '';}};
      const child = {id: id + '-rect', parent: value, type: 'RECTANGLE', name: 'Rectangle', width: 42, height: 24,
        getPluginData() {return '';}};
      Object.defineProperty(child, 'fills', {get() {fullGetterReads++; return [];}});
      value.children.push(child);
      return value;
    }
    const pages = new Map([['primary', page('primary')], ['secondary', page('secondary')]]);
    const figma = {fileKey: 'file-key', currentPage: pages.get('primary'),
      async getNodeByIdAsync(id) {lookups.push(id); return pages.get(id);},
      variables: {async getLocalVariableCollectionsAsync() {return [];}},
      showUI() {}, ui: {postMessage(value) {messages.push(plain(value));}}};
    const context = {figma, __html__: ''};
    vm.runInNewContext(code + `\nconst originalReader = readNativeSemantics;
      readNativeSemantics = async function(figma, page, request) { trackRead(page.id, request); return originalReader(figma, page, request); };
      globalThis.testSession = GRAPH_PANEL_SESSION;`, {...context, trackRead(id, request) {reads.push({id, request: request && plain(request)});}});
    const session = messages[0]?.session;
    // The generated session is intentionally opaque; discover it from the generated declaration.
    const token = JSON.parse(code.match(/const GRAPH_PANEL_SESSION = ("[^"]+");/)[1]);
    assert.equal(session, undefined);
    await figma.ui.onmessage({type: 'native-summary', session: 'wrong'});
    await figma.ui.onmessage({type: 'apply', session: token});
    assert.equal(messages.length, 0, 'wrong sessions and mutation operations must be ignored');
    await figma.ui.onmessage({type: 'native-summary', session: token});
    assert.equal(messages.length, 2, 'standard discovery must accept a separate native-summary action');
    const summary = messages.at(-1).readback;
    assert.equal(messages.at(-1).operation, 'native-summary');
    assert.equal(summary.schema, 'figma-flow-native-read-summary-v1');
    assert.equal(summary.fileKey, 'file-key');
    assert.equal(summary.pageId, 'primary');
    assert.deepEqual(summary.expected_scope, {file_key: 'file-key', page_id: 'primary', allowed_page_ids: ['primary', 'secondary']});
    assert.deepEqual(summary.coverage.pageIds, ['primary'], 'summary must explicitly cover only the primary admitted page');
    assert.equal(summary.coverage.profile, 'summary');
    assert.equal(summary.coverage.complete, false);
    assert.deepEqual(summary.coverage.nodeIds, ['primary', 'primary-rect']);
    assert.deepEqual(summary.coverage.fields, ['width', 'height']);
    for (const key of ['styles', 'variables', 'collections', 'rasterImages', 'textSegments']) assert.ok(summary.coverage.omitted.includes(key));
    assert.deepEqual(reads, [{id: 'primary', request: {profile: 'summary', nodeIds: ['primary', 'primary-rect'], fields: ['width', 'height']}}]);
    assert.deepEqual(lookups, ['primary']);
    assert.equal(fullGetterReads, 0, 'summary must never fall back to a full native read');
    assert.equal(summary.nodes[1].width, 42);
    assert.equal(summary.nodes[1].height, 24);
    for (const key of ['variables', 'collections', 'rasterImages', 'graphSSOT']) assert.equal(Object.hasOwn(summary, key), false);
    assert.equal(pages.get('primary').children[0].width, 42, 'summary must leave native nodes unchanged');

    let resolve;
    release = {promise: new Promise(done => {resolve = done;})};
    const pending = figma.ui.onmessage({type: 'native-summary', session: token});
    const beforeDuplicate = messages.length;
    await figma.ui.onmessage({type: 'read', session: token});
    await figma.ui.onmessage({type: 'native-summary', session: token});
    assert.equal(messages.length, beforeDuplicate, 'busy discovery must reject duplicate and cross-profile operations');
    resolve(); release = null; await pending;
    figma.fileKey = 'wrong';
    const beforeWrongScope = reads.length;
    await figma.ui.onmessage({type: 'native-summary', session: token});
    assert.ok(messages.at(-1).error, 'wrong files must fail closed');
    assert.equal(reads.length, beforeWrongScope);
    figma.fileKey = 'file-key'; figma.currentPage = pages.get('secondary');
    await figma.ui.onmessage({type: 'native-summary', session: token});
    assert.ok(messages.at(-1).error, 'switching to another admitted page must still reject the primary-page summary');
    assert.equal(reads.length, beforeWrongScope);
    figma.currentPage = pages.get('primary');
    const originalLoad = figma.currentPage.loadAsync;
    figma.currentPage.loadAsync = async () => {figma.currentPage = pages.get('secondary');};
    await figma.ui.onmessage({type: 'native-summary', session: token});
    assert.ok(messages.at(-1).error, 'scope changes during summary reads must fail closed');
    figma.currentPage = pages.get('primary'); figma.currentPage.loadAsync = originalLoad;
    await figma.ui.onmessage({type: 'read', session: token});
    const full = messages.at(-1).readback;
    assert.equal(full.schema, 'figma-flow-graph-native-discovery-v1', 'ordinary read must remain the full default');
    assert.deepEqual(full.allowed_page_ids, ['primary', 'secondary']);
    assert.equal(full.nodes.length, 4);
    assert.ok(reads.slice(-2).every(read => read.request === undefined));
    assert.ok(fullGetterReads > 0);
    const audit = require(path.join(root, 'figma-bridge/audit_log.js'));
    const diagnostic = audit.buildAuditRecord({native_read: summary});
    assert.equal(diagnostic.native_read.complete, false);
    assert.deepEqual(diagnostic.native_read.node_ids, summary.coverage.nodeIds);
    assert.deepEqual(diagnostic.native_read.fields, summary.coverage.fields);
    assert.deepEqual(diagnostic.native_read.omitted, summary.coverage.omitted);
    execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
      'import json,sys;sys.path.insert(0,sys.argv[1]);from graph_sync import normalize\ntry: normalize(json.loads(sys.argv[2]), {})\nexcept (ValueError,KeyError): pass\nelse: raise AssertionError("summary accepted as graph mutation evidence")',
      path.join(root, 'tools'), JSON.stringify(summary)], {cwd: root});

    const react = fs.readFileSync(path.join(root, 'panel-ui/src/GraphPanel.jsx'), 'utf8');
    const legacy = fs.readFileSync(path.join(root, 'figma-bridge/graph-panel.html'), 'utf8');
    for (const [name, source] of [['React', react], ['legacy', legacy]]) {
      assert.ok(source.includes("start('native-summary')"), name + ' must expose the separate summary action');
      assert.ok(source.includes('graph-native-summary.json'), name + ' must use a distinct summary filename');
      assert.ok(source.includes('summaryBoundary'), name + ' must show the partial primary-page boundary');
      assert.ok(source.includes('coverage'), name + ' must expose exact partial coverage');
      assert.ok(source.includes('protocol: 2'), name + ' must retain selective apply protocol');
    }
    assert.ok(react.includes('nativeSummaryView(') || react.includes('<NativeSummary'), 'React must reuse the existing summary view');
    assert.ok(react.includes('evidence={evidence}'), 'React diagnostic must use the same latest readback');
    assert.ok(legacy.includes('seen.native_read = message.readback'), 'legacy diagnostic must replace summary with the latest full readback');
    const locales = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/graph.json')));
    for (const key of ['graph.summaryRead', 'graph.summaryBoundary']) for (const locale of ['ko', 'en', 'ja']) assert.ok(locales[key]?.[locale]);
    assert.match(locales['graph.summaryBoundary'].en, /primary page/i);
    assert.match(locales['graph.summaryBoundary'].en, /width.*height/i);
    console.log('discovery summary host, scope, full-default, read-only, diagnostic and affordance checks passed');
  } finally {
    fs.rmSync(temporary, {recursive: true, force: true});
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
