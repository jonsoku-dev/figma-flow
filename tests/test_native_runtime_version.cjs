const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../figma-bridge/workspace_control.js'), 'utf8');

test('authenticated native poll reports the compiled runtime and generation', async () => {
  const runtime = {version:'1.2.3',implementation:'a'.repeat(64),generation:'b'.repeat(32)};
  let request;
  const env = {WORKSPACE_RUNTIME:runtime, WORKSPACE_CONTROL_CONFIG:{url:'http://localhost:1234',token:'private'},
    workspaceActive:null, workspaceHomeSession:'home', figma:{fileKey:'file',currentPage:{id:'1:2'}},
    fetch:async (url, options) => {request={url,...options};return {ok:true,json:async()=>({operation:null})};}};
  vm.runInNewContext(source, env);
  await env.workspaceControlTick();
  assert.deepEqual(JSON.parse(request.body).runtime, runtime);
  assert.equal(request.headers.Authorization, 'Bearer private');
});

test('legacy native poll stays versionless without inventing current identity', async () => {
  let payload;
  const env = {WORKSPACE_CONTROL_CONFIG:{url:'http://localhost:1234',token:'private'},
    workspaceActive:null, workspaceHomeSession:'home', figma:{fileKey:'file',currentPage:{id:'1:2'}},
    fetch:async (_url, options) => {payload=JSON.parse(options.body);return {ok:true,json:async()=>({operation:null})};}};
  vm.runInNewContext(source, env);
  await env.workspaceControlTick();
  assert.equal('runtime' in payload, false);
});
