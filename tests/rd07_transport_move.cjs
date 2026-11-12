const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const transportPath = path.join(root, 'figma-bridge', 'workspace_transport.js');
const transport = fs.existsSync(transportPath) ? fs.readFileSync(transportPath, 'utf8') : '';
assert.ok(transport.includes('async function controlRequest'), 'pure transport must leave domain checks in place');
const control = fs.readFileSync(path.join(root, 'figma-bridge', 'workspace_control.js'), 'utf8');
assert.ok(!control.includes('async function controlRequest'));
assert.ok(control.includes("controlRequest('poll'"));
assert.ok(control.includes("controlRequest('native-started'"));
assert.ok(control.includes("controlRequest('result'"));
assert.ok(control.includes('async function controlExecute'));
assert.ok(control.includes('const controlAllowed'));
assert.ok(!transport.includes('controlAllowed'));
assert.ok(!transport.includes('controlExecute'));
assert.ok(!transport.includes('eval('));
const publisher = fs.readFileSync(path.join(root, 'tools', 'figma_workspace.py'), 'utf8');
const transportAt = publisher.indexOf('workspace_transport.js');
const controlAt = publisher.indexOf('workspace_control.js');
assert.ok(transportAt !== -1 && transportAt < controlAt);
const tasks = fs.readFileSync(path.join(root, 'docs/development-roadmap/RD-07-runtime-boundaries/tasks.md'), 'utf8');
assert.ok(tasks.includes('controlRequest만'));

(async () => {
  let seen;
  const env = {
    WORKSPACE_CONTROL_CONFIG: {url: 'http://localhost:9', token: 'private'},
    setTimeout, clearTimeout,
    fetch: async (url, options) => {
      seen = {url, options};
      return {ok: true, json: async () => ({ok: true})};
    },
  };
  vm.runInNewContext(transport + '\n' + control, env);
  const body = await env.controlRequest('poll', {session_id: 's'});
  assert.equal(body.ok, true);
  assert.equal(seen.url, 'http://localhost:9/control/poll');
  assert.equal(seen.options.method, 'POST');
  assert.equal(seen.options.headers.Authorization, 'Bearer private');
  assert.equal(JSON.parse(seen.options.body).session_id, 's');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
