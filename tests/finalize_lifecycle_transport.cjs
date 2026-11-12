const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../figma-bridge/workspace_transport.js'),'utf8');
function transport(url='http://localhost:45000', fetcher=async()=>({ok:true,json:async()=>({ok:true})})) {
  const requests = [], timers = new Map(); let next = 0;
  const env = {WORKSPACE_CONTROL_CONFIG:{url,token:'private-test-token'},
    fetch:async(...args)=>{requests.push(args);return fetcher(...args);},
    setTimeout:(callback,delay)=>{assert.ok(delay>0 && delay<=15000,'transport deadline must be bounded');timers.set(++next,callback);return next;},
    clearTimeout:id=>timers.delete(id)};
  vm.runInNewContext(source,env);
  return {env,requests,timers};
}
test('loopback origin and route allowlist rejects before sending credentials',async()=>{
  for(const url of ['https://example.com','http://localhost.evil:45000','http://127.0.0.1:45000/path','http://user@localhost:45000','http://localhost:45000?x=1']) {
    const d=transport(url); await assert.rejects(d.env.controlRequest('poll',{})); assert.equal(d.requests.length,0,url);
  }
  const d=transport();
  for(const route of ['../secret','poll?x=1','https://example.com','arbitrary']) await assert.rejects(d.env.controlRequest(route,{}));
  assert.equal(d.requests.length,0);
});
test('control request preserves endpoint/auth and rejects over-cap UTF-8 envelopes',async()=>{
  const d=transport();
  assert.equal((await d.env.controlRequest('poll',{file_key:'fixturefile'})).ok,true);
  assert.equal(d.requests[0][0],'http://localhost:45000/control/poll');
  assert.equal(d.requests[0][1].headers.Authorization,'Bearer private-test-token');
  await assert.rejects(d.env.controlRequest('result',{readback_json:'x'.repeat(12*1024*1024+1)}));
  await assert.rejects(d.env.controlRequest('poll',{extra:'é'.repeat(8*1024*1024+1)}));
  assert.equal(d.requests.length,1,'payload limits apply before fetch');
});
test('timeout covers stalled fetch and body parsing without AbortController',async()=>{
  for (const stage of ['fetch','body']) {
    const never=new Promise(()=>{});
    const d=transport('http://localhost:45000',()=>stage==='fetch'?never:Promise.resolve({ok:true,json:()=>never}));
    const pending=d.env.controlRequest('poll',{});
    const settled=assert.rejects(pending,/timeout|timed out|deadline/i);
    await Promise.resolve(); await Promise.resolve();
    assert.ok(d.timers.size,'request must arm a timeout even without AbortController');
    for(const callback of d.timers.values()) callback();
    await settled;
    assert.equal(d.timers.size,0,'settled deadline must release timer');
  }
});
