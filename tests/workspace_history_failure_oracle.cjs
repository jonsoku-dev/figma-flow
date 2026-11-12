const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const bridge = name => fs.readFileSync(path.join(__dirname, '../figma-bridge', name), 'utf8');

async function main() {
  const events = [];
  const task = {key:'sample',revision:'r',kind:'discover',fileKey:'file'};
  const remote = {
    figma:{fileKey:'file',currentPage:{id:'0:1'}}, workspaceActive:null,
    workspaceRecord:(active, operation, status) => events.push({operation,status,executionId:active.executionId}),
    async workspaceOpen() {
      const active = {inFlight:0,html:'<script id="graph-panel-config" type="application/json">{"session":"s"}</script>',handler:async()=>{}};
      remote.workspaceActive = active;
      return active;
    },
  };
  vm.runInNewContext(bridge('workspace_control.js'), remote);
  await assert.rejects(remote.controlExecute(task, {
    key:'sample',revision:'r',file_key:'file',page_id:'0:1',claim_id:'1'.repeat(32),
    deadline:Date.now()/1000+20,operation:'read',
  }), /expected native evidence/);
  assert.equal(events.filter(event=>event.status==='failed').length,1,
    'remote validation failure must remain in saved history');
  assert.ok(events[0].executionId);
  assert.equal(events.at(-1).executionId,events[0].executionId);

  const messages = [];
  const figma = {fileKey:'file',ui:{postMessage:message=>messages.push(message)},showUI(){}};
  const local = vm.createContext({figma,__html__:'HOME'});
  vm.runInContext(`
    const FLOW_LOCALES=['ko'];
    const WORKSPACE_CONTROL_CONFIG=null;
    const WORKSPACE_CHAT_CONFIG=null;
    const FLOW_TASKS=[{key:'sample',kind:'discover',revision:'r',fileKey:'file',run(){
      const scoped=workspaceTaskFigma();
      scoped.showUI('<html><head></head><body></body></html>',{});
      scoped.ui.onmessage=async()=>{scoped.ui.postMessage({error:'synthetic failure'});throw Error('synthetic failure');};
    }}];
  ` + bridge('workspace_host.js'), local);
  await figma.ui.onmessage({type:'workspace-home-ready'});
  const listing=messages.find(message=>message.type==='workspace-tasks');
  await figma.ui.onmessage({type:'workspace-open',key:'sample',workspaceSession:listing.workspaceSession});
  const session=vm.runInContext('workspaceActive.session',local);
  await figma.ui.onmessage({type:'workspace-task-message',workspaceSession:session,payload:{type:'read'}});
  const history=vm.runInContext('workspaceState.history',local);
  assert.equal(history.filter(event=>event.status==='failed').length,1,
    'one native failure must be one execution step');
  assert.equal(history.at(-1).executionId,history[0].executionId);
  console.log('Remote validation and local observed/throw failures are recorded once with their actual execution.');
}

main().catch(error=>{console.error(error);process.exitCode=1;});
