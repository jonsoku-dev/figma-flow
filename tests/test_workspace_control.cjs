const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_control.js'), 'utf8');

function driver(kind, callback) {
  const task = {key:'sample', revision:'r', kind, fileKey:'file',sourceSha256:'abc'};
  const history = [];
  const env = {figma:{fileKey:'file',currentPage:{id:'0:1'}}, workspaceActive:null, task, history,
    workspaceRecord:(active, op, state)=>history.push([op,state,active.executionId]),
    async workspaceOpen() {
      const active = {inFlight:0, html:'<script id="graph-panel-config" type="application/json">{"session":"s"}</script>\nconst PAIR = null;\n'};
      active.handler = msg => callback(msg, event=>active.onOutput(event));
      env.workspaceActive = active;
      return active;
    }
  };
  vm.runInNewContext(source, env);
  const run=(operation,extra={})=>env.controlExecute(task,{key:'sample',revision:'r',file_key:'file',page_id:'0:1',claim_id:'1'.repeat(32),deadline:Date.now()/1000+20,operation,...extra});
  return {run,env};
}

test('a stale revision or page is rejected before native execution', async()=>{
  let calls=0;
  const d=driver('sync',()=>calls++);
  await assert.rejects(d.run('apply',{revision:'old'}),/changed/);
  await assert.rejects(d.run('apply',{page_id:'2:0'}),/differs/);
  assert.equal(calls,0);
});
test('silent import cannot become successful even when handler returns',async()=>{
  const {run,env}=driver('import',(m,post)=>{if(m.type==='ready')post({ready:true,session_nonce:m.session_nonce});});
  await assert.rejects(run('import'),/completion/);assert.equal(env.workspaceActive,null);
  const failed=env.history.filter(([,status])=>status==='failed');
  assert.equal(failed.length,1,'remote validation failure must remain in saved history');
  assert.equal(failed[0][2],env.history.find(([op,status])=>op==='import'&&status==='requested')[2]);
});
test('readback is required after a successful import',async()=>{
  const {run,env}=driver('import',(m,post)=>{
    if(m.type==='ready')post({ready:true,session_nonce:m.session_nonce});
    if(m.type==='import'){post({type:'busy',value:true,operation:'import'});post({type:'status',event:'reused',page_id:'0:1',source_sha256:'abc',message:'ok'});post({type:'busy',value:false});}
    if(m.type==='export')post({type:'readback',data:{format:'figma-flow-readback-v1',pages:[{id:'0:1',declared_metadata:{complete:true},source_sha256:'abc'}]}});
  });
  assert.equal((await run('import')).pages[0].id,'0:1');assert.equal(env.workspaceActive,null);
});
test('graph errors return diagnostic readback instead of an apparent success',async()=>{
  const {run}=driver('sync',(m,post)=>post({session:m.session,operation:m.type,error:'collision',readback:{status:'rolled-back'}}));
  await assert.rejects(run('apply'),e=>e.message==='collision' && e.nativeReadback.status==='rolled-back');
});
test('discovery returns the actual scoped getter and never calls apply',async()=>{
  const {run}=driver('discover',(m,post)=>{assert.equal(m.type,'read');post({session:m.session,operation:m.type,readback:{schema:'figma-flow-graph-native-discovery-v1',fileKey:'file',pageId:'0:1',nodes:[{id:'n'}]}});});
  assert.equal((await run('read')).nodes[0].id,'n');
});
test('native graph review uses the signed native-edit read and apply contract',async()=>{
  const {run,env}=driver('native-edit',()=>{});
  env.workspaceOpen=async()=>{const active={inFlight:0,model:{session:'s'},html:'<script type="application/json" id="flow-model">{"session":"s"}</script>'};active.handler=msg=>activeHandler(msg,event=>active.onOutput(event));env.workspaceActive=active;return active;};
  const read=await run('read');assert.equal(read.schema,'figma-flow-graph-native-discovery-v1');assert.equal(read.native_edit.applied,false);
  const applied=await run('apply');assert.equal(applied.native_edit.applied,true);assert.equal(applied.graph_review.status,'created');
  function activeHandler(message,post){
    const applied=message.type==='apply';
    post({session:message.session,operation:message.type,readback:{schema:'figma-flow-graph-native-discovery-v1',fileKey:'file',pageId:'0:1',nodes:[],graph_review:{status:applied?'created':'absent'},native_edit:{operation:message.type,applied}}});
  }
});
test('remote review retains its native readback on receiver failure',async()=>{
  const d=driver('review',(m,post)=>post({type:'readback',data:{packet_sha256:'pin',fileKey:'file',nodes:[{id:'n'}]}}));
  const original=d.env.workspaceOpen;
  d.env.workspaceOpen=async()=>{const a=await original();a.html='const PAIR = {"url":"http://localhost:45000/draft-readback","capability":"'+ 'a'.repeat(64)+'"};';return a;};
  d.env.fetch=async()=>({ok:false,json:async()=>({passed:false})});
  await assert.rejects(d.run('create'),e=>e.nativeReadback.fileKey==='file');
  assert.ok(d.env.history.some(([op,state])=>op==='verification'&&state==='failed'));
  const request=d.env.history.find(([op,state])=>op==='draft-review'&&state==='requested');
  const verification=d.env.history.find(([op,state])=>op==='verification'&&state==='failed');
  assert.ok(request[2]);assert.equal(request[2],verification[2]);
  assert.equal(d.env.history.filter(([,status])=>status==='failed').length,1);
  await assert.rejects(d.run('create'),e=>e.nativeReadback.fileKey==='file');
  const retries=d.env.history.filter(([op,state])=>op==='draft-review'&&state==='requested');
  assert.notEqual(retries[0][2],retries[1][2]);
});

test('explicit focus loads only a page pinned by the prepared task', async()=>{
  const {run,env}=driver('discover',(m,post)=>post({session:'s',operation:'read',readback:{schema:'figma-flow-graph-native-discovery-v1',fileKey:'file',pageId:'2:0'}}));
  env.task.pageId='2:0';
  const page={id:'2:0',type:'PAGE',loadAsync:async()=>{}};
  env.figma.getNodeByIdAsync=async id=>id===page.id?page:null;
  env.figma.setCurrentPageAsync=async target=>{env.figma.currentPage=target;};
  await assert.rejects(run('read',{page_id:'2:0'}),/active page/);
  assert.equal((await run('read',{page_id:'2:0',focus_page:true})).pageId,'2:0');
});

test('read cannot attest a different page even when it becomes the current page', async()=>{
  const d=driver('import',(m,post)=>{
    if(m.type==='ready')post({ready:true,session_nonce:m.session_nonce});
    if(m.type==='export'){
      d.env.figma.currentPage={id:'1:4'};
      post({type:'readback',data:{format:'figma-flow-readback-v1',pages:[{id:'1:4'}]}});
    }
  });
  await assert.rejects(d.run('read'),/readback/);
});
