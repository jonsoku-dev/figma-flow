/* Bounded transport capacity oracle. API-shaped fetch is not a live Figma run. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_transport.js'), 'utf8');
const MiB = 1024 * 1024;

function host(response = {accepted: true}) {
  const seen = {calls: 0, deadline: null, cleared: false};
  const context = vm.createContext({
    WORKSPACE_CONTROL_CONFIG: {url: 'http://localhost:49198', token: 'capacity-test-token'},
    setTimeout(fn, delay) {seen.deadline = delay; return setTimeout(fn, delay);},
    clearTimeout(timer) {seen.cleared = true; clearTimeout(timer);},
    async fetch(url, options) {
      seen.calls++;
      seen.url = url;
      seen.authorization = options.headers.Authorization;
      seen.bytes = Buffer.byteLength(options.body);
      seen.noncePresent = options.body.includes('capacity-claim');
      return {ok: true, json: async () => response};
    },
  });
  vm.runInContext(source, context);
  return {context, seen};
}

function nativeJSON(bytes, quotes = 0) {
  const prefix = '{"text":"', suffix = '"}';
  return prefix + '\\"'.repeat(quotes) + 'a'.repeat(bytes - prefix.length - suffix.length - quotes * 2) + suffix;
}

function receipt(raw) {
  return {id: 'capacity-operation', claim_id: 'capacity-claim', session_id: 'capacity-session',
    file_key: 'fixturefile', page_id: '12:1', revision: 'a'.repeat(64), status: 'ok', readback_json: raw};
}

test('actual transport admits a 29,991,516-byte native JSON result with escaped envelope overhead', async () => {
  const {context, seen} = host();
  const raw = nativeJSON(29991516, 1713000);
  assert.equal(Buffer.byteLength(raw), 29991516);
  assert.equal((await context.controlRequest('result', receipt(raw))).accepted, true);
  assert.equal(seen.calls, 1);
  assert(seen.bytes > 33000000 && seen.bytes < 40 * MiB);
  assert.equal(seen.url, 'http://localhost:49198/control/result');
  assert.equal(seen.authorization, 'Bearer capacity-test-token');
  assert.equal(seen.noncePresent, true);
  assert.equal(seen.deadline, 15000);
  assert.equal(seen.cleared, true);
});

test('raw result limit measures UTF-8 bytes and accepts exactly 32 MiB', async () => {
  const {context, seen} = host();
  const prefix = '{"text":"', suffix = '"}';
  const available = 32 * MiB - prefix.length - suffix.length;
  const raw = prefix + '가😀'.repeat(Math.floor(available / 7)) + 'a'.repeat(available % 7) + suffix;
  assert.equal(Buffer.byteLength(raw), 32 * MiB);
  assert.equal((await context.controlRequest('result', receipt(raw))).accepted, true);
  assert.equal(seen.calls, 1);
});

test('more than 32 MiB of raw UTF-8 is rejected before fetch', async () => {
  const {context, seen} = host();
  const raw = '{"text":"' + '가'.repeat(Math.ceil(32 * MiB / 3)) + '"}';
  assert(raw.length < 32 * MiB && Buffer.byteLength(raw) > 32 * MiB);
  await assert.rejects(context.controlRequest('result', receipt(raw)), /limit/);
  assert.equal(seen.calls, 0);
  assert.equal(seen.deadline, null);
});

test('request envelope accepts exactly 40 MiB of UTF-8', async () => {
  const {context, seen} = host();
  const overhead = Buffer.byteLength(JSON.stringify({padding: ''}));
  const available = 40 * MiB - overhead;
  const body = {padding: '가😀'.repeat(Math.floor(available / 7)) + 'a'.repeat(available % 7)};
  assert.equal((await context.controlRequest('result', body)).accepted, true);
  assert.equal(seen.calls, 1);
  assert.equal(seen.bytes, 40 * MiB);
});

test('more than 40 MiB of UTF-8 envelope is rejected before fetch', async () => {
  const {context, seen} = host();
  const body = {padding: '가'.repeat(Math.ceil(40 * MiB / 3))};
  await assert.rejects(context.controlRequest('result', body), /limit/);
  assert.equal(seen.calls, 0);
  assert.equal(seen.deadline, null);
});

test('response JSON stays bounded at the existing 16 MiB limit', async () => {
  const {context, seen} = host({padding: '가'.repeat(Math.ceil(16 * MiB / 3))});
  await assert.rejects(context.controlRequest('history', {}), /limit/);
  assert.equal(seen.calls, 1);
  assert.equal(seen.cleared, true);
});

test('route, origin and envelope guards still reject before fetch', async () => {
  const {context, seen} = host();
  for (const route of ['run', '../result', 'result?extra=1', ''])
    await assert.rejects(context.controlRequest(route, {}), /endpoint or envelope/);
  for (const url of ['https://localhost:49198', 'http://example.com:49198', 'http://localhost:0', 'http://localhost:65536', 'http://localhost:49198/path']) {
    context.WORKSPACE_CONTROL_CONFIG.url = url;
    await assert.rejects(context.controlRequest('result', {}), /endpoint or envelope/);
  }
  context.WORKSPACE_CONTROL_CONFIG.url = 'http://localhost:49198';
  for (const body of [null, [], 'text'])
    await assert.rejects(context.controlRequest('result', body), /endpoint or envelope/);
  assert.equal(seen.calls, 0);
});
