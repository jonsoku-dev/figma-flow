const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'plugin.json'), 'utf8'));
const audit = require(path.join(root, 'figma-bridge/audit_log.js'));
const html = fs.readFileSync(path.join(root, 'figma-bridge/graph-panel.html'), 'utf8');
const binder = html.match(/<script id="audit-export-bind">([\s\S]*?)<\/script>/)[1];

function legacyDiagnostic(config) {
  const elements = new Map();
  for (const id of ['graph-panel-config', 'audit-text', 'audit-copy', 'audit-download-md', 'audit-download-json']) {
    elements.set(id, {textContent: '', value: '', focus() {}, select() {}});
  }
  elements.get('graph-panel-config').textContent = JSON.stringify(config);
  const records = [];
  let writes = 0;
  const forbidden = () => {writes++; throw Error('diagnostics must be read-only');};
  vm.runInNewContext(binder, {
    document: {getElementById: id => elements.get(id)},
    window: {addEventListener() {}},
    FlowAuditLog: {renderAuditExport(input) {const result = audit.renderAuditExport(input); records.push(result.record); return result;}},
    fetch: forbidden, parent: {postMessage: forbidden}, figma: new Proxy({}, {get: forbidden}),
  });
  const fenced = elements.get('audit-text').value.split('```json\n')[1].split('\n```')[0];
  assert.deepEqual(JSON.parse(fenced), records.at(-1), 'visible diagnostic and JSON must contain the same version');
  assert.equal(writes, 0);
  return records.at(-1);
}

test('graph panel compilation supplies the canonical manifest version to the React model and legacy config', () => {
  const generated = execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
    'import sys;sys.path.insert(0,sys.argv[1]);from graph_sync import graph_panel;print(graph_panel("discovery",{"file_key":"file","page_id":"page"},session="test-session"))',
    path.join(root, 'tools')], {cwd: root, encoding: 'utf8'});
  const config = JSON.parse(generated.match(/<script id="graph-panel-config" type="application\/json">([\s\S]*?)<\/script>/)[1]);
  assert.equal(config.plugin_version, manifest.version, 'generated graph config must use plugin.json version');
  assert.equal(legacyDiagnostic(config).plugin_version, manifest.version);
  const react = fs.readFileSync(path.join(root, 'panel-ui/src/DiagnosticExport.jsx'), 'utf8');
  assert.ok(react.includes('plugin_version: model.plugin_version'), 'React diagnostic must consume that same model metadata');
});

for (const version of [manifest.version, '88.77.66', null]) {
  test(`legacy diagnostic uses admitted config version ${JSON.stringify(version)} without a fallback`, () => {
    const config = {session: 'test-session', file_key: 'file', page_id: 'page'};
    if (version !== null) config.plugin_version = version;
    const record = legacyDiagnostic(config);
    assert.equal(record.plugin_version, version, 'legacy diagnostic must report the supplied version or null when absent');
    assert.equal(record.unobserved.some(item => item.check === 'plugin-version'), version === null);
  });
}
