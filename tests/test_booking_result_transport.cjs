const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const MiB = 1024 * 1024;
const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_transport.js'), 'utf8');

test('only an opted-in successful read uses the large result endpoint when needed', async () => {
  const routes = [];
  const context = vm.createContext({
    WORKSPACE_PROFILE_POLICY:require('../library/figma-profile/policy.json'), WORKSPACE_CONTROL_CONFIG: {url: 'http://localhost:49198', token: 'local-test'},
    setTimeout, clearTimeout,
    fetch: async url => {
      routes.push(new URL(url).pathname);
      return {ok: true, json: async () => ({accepted: true})};
    }
  });
  vm.runInContext(source, context);
  const submit = (status, json, read) => context.controlRequest('result', {status, readback_json: json}, read);
  await submit('ok', '{}', true);
  const utf8 = JSON.stringify({value: '가'.repeat(11 * MiB)});
  await submit('ok', utf8, true);
  const quoteHeavy = JSON.stringify({value: '"'.repeat(11 * MiB)});
  assert.ok(Buffer.byteLength(quoteHeavy) < 32 * MiB);
  assert.ok(Buffer.byteLength(JSON.stringify({readback_json: quoteHeavy})) > 40 * MiB);
  await submit('ok', quoteHeavy, true);
  await assert.rejects(submit('ok', utf8, false), /limit/);
  await assert.rejects(submit('error', utf8, true), /limit/);
  await assert.rejects(submit('ok', 'x'.repeat(64 * MiB + 1), true), /limit/);
  assert.deepEqual(routes, ['/control/result', '/control/result-large', '/control/result-large']);
});
