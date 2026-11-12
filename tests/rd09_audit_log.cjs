const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const sourcePath = path.join(root, 'figma-bridge', 'audit_log.js');
const source = fs.existsSync(sourcePath) ? fs.readFileSync(sourcePath, 'utf8') : '';
assert.ok(source.includes('function buildAuditRecord'), 'audit export must keep the diagnostic record');
assert.ok(source.includes('function renderAuditExport'));
assert.ok(source.includes('figma-flow-audit-log-v1'));
assert.ok(!source.includes('postMessage'));
assert.ok(!source.includes('innerHTML'));
assert.ok(!source.includes('fetch('));
const {buildAuditRecord, renderAuditExport} = require(sourcePath);

const secretError = 'Previous claimed operation is uncertain; node 12:34; Bearer super-secret-bearer; see /Users/ada/figma-flow/tools/x.py?capability=deadbeef';
const input = {
  plugin_version: '0.26.3',
  file_key: 'AbC123',
  page_id: '12:34',
  page_name: '홈',
  task_key: 'import-home',
  revision: 'rev-9f3a',
  operation_id: '0123456789abcdef0123456789abcdef',
  pairing: {state: 'paired', freshness: 'fresh', sync_token: 'sync-token-value'},
  runtime_freshness: 'current',
  lifecycle: [
    {phase: 'queued', status: 'ok', error: null, time: '2026-11-12T00:00:00Z'},
    {phase: 'uncertain', status: 'blocked', error: secretError, time: '2026-11-12T00:01:00Z'},
  ],
  uncertainty: {blocked_write: true, reasons: ['Previous claimed operation is uncertain; node 12:34']},
  input_summary: [{ref: 'photos/mark.png', kind: 'image', status: '404', source: 'css/a.css?chat_token=chat-token-value'}],
  dependency_freshness: [{label: 'photos/mark.png', freshness: 'stale'}],
  native_read: {
    schema: 'figma-flow-native-read-summary-v1',
    coverage: {
      profile: 'summary',
      nodeIds: ['12:34', '5:1'],
      fields: ['width', 'height'],
      omitted: ['styles', 'variables', 'collections', 'rasterImages', 'textSegments'],
      complete: false,
    },
    nodes: [{id: '12:34', width: 12}, {id: '5:1', width: 4}],
  },
  chat_token: 'chat-token-value',
  authorization: 'Bearer super-secret-bearer',
};
const before = JSON.stringify(input);
const exported = renderAuditExport(input);
assert.equal(JSON.stringify(input), before);
const record = exported.record;
assert.equal(record.schema, 'figma-flow-audit-log-v1');
const manifestVersion = JSON.parse(fs.readFileSync(path.join(root, 'plugin.json'), 'utf8')).version;
assert.match(manifestVersion, /^[0-9]+\.[0-9]+\.[0-9]+$/);
assert.equal(JSON.parse(fs.readFileSync(path.join(root, '.codex-plugin/plugin.json'), 'utf8')).version, manifestVersion);
assert.equal(record.plugin_version, '0.26.3');
assert.equal(record.file_key, 'AbC123');
assert.deepEqual(record.page, {id: '12:34', name: '홈'});
assert.equal(record.task_key, 'import-home');
assert.equal(record.revision, 'rev-9f3a');
assert.equal(record.operation_id, '0123456789abcdef0123456789abcdef');
assert.deepEqual(record.pairing, {state: 'paired', freshness: 'fresh'});
assert.equal(record.runtime_freshness, 'current');
assert.equal(record.lifecycle.length, 2);
assert.equal(record.lifecycle[0].phase, 'queued');
assert.equal(record.lifecycle[0].status, 'ok');
assert.equal(record.lifecycle[0].error, null);
assert.equal(record.lifecycle[1].phase, 'uncertain');
assert.equal(record.lifecycle[1].status, 'blocked');
assert.ok(record.lifecycle[1].error.includes('Previous claimed operation is uncertain'));
assert.ok(record.lifecycle[1].error.includes('node 12:34'));
assert.ok(!record.lifecycle[1].error.includes('super-secret-bearer'));
assert.ok(!record.lifecycle[1].error.includes('/Users/ada'));
assert.ok(!record.lifecycle[1].error.includes('deadbeef'));
assert.equal(record.uncertainty.blocked_write, true);
assert.ok(record.uncertainty.reasons.includes('Previous claimed operation is uncertain; node 12:34'));
assert.deepEqual(record.input_summary, [{
  ref: 'photos/mark.png', kind: 'image', status: '404', source: 'css/a.css?chat_token=[redacted]',
}]);
assert.deepEqual(record.dependency_freshness, [{label: 'photos/mark.png', freshness: 'stale'}]);
assert.equal(record.native_read.profile, 'summary');
assert.deepEqual(record.native_read.node_ids, ['12:34', '5:1']);
assert.deepEqual(record.native_read.fields, ['width', 'height']);
assert.deepEqual(record.native_read.omitted, ['styles', 'variables', 'collections', 'rasterImages', 'textSegments']);
assert.equal(record.native_read.complete, false);
assert.ok(record.unobserved.some((item) => item.check === 'live-figma-panel'));
assert.ok(!record.unobserved.some((item) => item.check === 'native-read'));
const blob = exported.json + '\n' + exported.markdown + '\n' + exported.text;
assert.ok(!blob.includes('super-secret-bearer'));
assert.ok(!blob.includes('sync-token-value'));
assert.ok(!blob.includes('chat-token-value'));
assert.ok(!blob.includes('/Users/ada'));
assert.ok(!blob.includes('deadbeef'));
assert.ok(blob.includes('12:34'));
assert.ok(blob.includes('5:1'));
assert.ok(blob.includes('rev-9f3a'));
assert.ok(blob.includes('0123456789abcdef0123456789abcdef'));
assert.ok(blob.includes('Previous claimed operation is uncertain'));
assert.equal(exported.text, exported.markdown);
assert.ok(exported.markdown.startsWith('# Figma Flow 진단 기록'));
assert.ok(exported.markdown.includes('```json\n'));
const fenced = exported.markdown.split('```json\n')[1].split('\n```')[0];
assert.equal(fenced, exported.json);
assert.deepEqual(JSON.parse(fenced), record);
assert.equal(exported.json, JSON.stringify(record, null, 2));

const full = buildAuditRecord({
  plugin_version: '0.26.3',
  file_key: 'AbC123',
  page_id: '12:34',
  page_name: '홈',
  task_key: 'import-home',
  revision: 'rev-9f3a',
  operation_id: '0123456789abcdef0123456789abcdef',
  pairing: {state: 'paired', freshness: 'stale'},
  runtime_freshness: 'current',
  lifecycle: [{phase: 'result-received', status: 'ok', error: null, time: '2026-11-12T00:02:00Z'}],
  uncertainty: {blocked_write: false, reasons: []},
  input_summary: [],
  dependency_freshness: [{label: 'fonts/body.woff2', freshness: 'fresh'}],
  native_read: {nodes: [{id: '12:34', width: 12, fills: []}, {id: '5:1', name: 'label'}]},
});
assert.equal(full.native_read.profile, 'full');
assert.equal(full.native_read.complete, true);
assert.deepEqual(full.native_read.node_ids, ['12:34', '5:1']);
assert.ok(full.native_read.fields.includes('width'));
assert.ok(full.native_read.fields.includes('fills'));
assert.ok(full.native_read.fields.includes('name'));
assert.deepEqual(full.native_read.omitted, []);
assert.equal(full.uncertainty.blocked_write, false);
assert.equal(full.input_summary.length, 0);
assert.ok(!full.unobserved.some((item) => item.check === 'input-summary'));

const missing = buildAuditRecord({plugin_version: '0.26.3', file_key: 'AbC123', page_id: '1:2', page_name: '빈 페이지'});
for (const check of ['task-key', 'revision', 'operation-id', 'pairing', 'runtime-freshness', 'lifecycle', 'blocked-write', 'input-summary', 'dependency-freshness', 'native-read', 'live-figma-panel']) {
  assert.ok(missing.unobserved.some((item) => item.check === check), check);
}
assert.equal(missing.native_read, null);
assert.equal(missing.page.id, '1:2');
assert.equal(missing.operation_id, null);
assert.equal(missing.revision, null);

const html = fs.readFileSync(path.join(root, 'figma-bridge/graph-panel.html'), 'utf8');
assert.ok(html.includes('id="audit-copy"'));
assert.ok(html.includes('id="audit-download-md"'));
assert.ok(html.includes('id="audit-download-json"'));
assert.ok(html.includes('id="audit-text"'));
assert.ok(html.includes('진단 기록 복사'));
assert.ok(html.includes('마크다운 저장'));
assert.ok(html.includes('JSON 저장'));
assert.ok(html.includes('페어링을 바꾸지 않습니다'));
assert.ok(html.includes('네이티브 쓰기를 보내지 않습니다'));
assert.ok(html.includes('function bindAuditExport'));
assert.ok(html.includes('FlowAuditLog.renderAuditExport'));
assert.ok(html.includes('readonly'));
assert.ok(html.includes(source));
const bindStart = html.indexOf('function bindAuditExport');
const bindEnd = html.indexOf('bindAuditExport();', bindStart);
const bind = html.slice(bindStart, bindEnd);
assert.ok(bind.includes('renderAuditExport'));
assert.ok(bind.includes('config.plugin_version'), 'diagnostic version must come from generated config');
assert.ok(!bind.includes('postMessage'));
assert.ok(!bind.includes('innerHTML'));
assert.ok(!bind.includes('fetch('));
