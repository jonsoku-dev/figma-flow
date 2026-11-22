const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_control.js'), 'utf8');

function driver(kind, callback) {
  const task = {key:'sample', revision:'r', kind, fileKey:'file',sourceSha256:'abc'};
  const history = [];
  const env = {figma:{fileKey:'file',currentPage:{id:'0:1'}}, workspaceActive:null, workspaceHomeSession:'home', task, history,
    workspaceRecord:(active, op, state)=>history.push([op,state,active.executionId]),
    async workspaceOpen() {
      const active = {inFlight:0, html:'<script id="graph-panel-config" type="application/json">{"session":"s"}</script>\nconst PAIR = null;\n'};
      active.handler = msg => callback(msg, event=>active.onOutput(event), env);
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

test('relay polling carries bounded native selection and profile context only in the authenticated poll envelope',async()=>{
  const calls=[]; const selection=Array.from({length:21},(_,index)=>({id:`n${index}`,name:'Node',type:'RECTANGLE'}));
  const env={figma:{fileKey:'file',currentPage:{id:'0:1'}},workspaceActive:null,workspaceHomeSession:'home',
    workspaceRelayViewer:true,workspaceRelayContext:()=>({session_id:'s',file_key:'file',page_id:'0:1',user_id:null,
      selection:selection.slice(0,20),selection_total:21,selection_truncated:true,
      profile:{declared:{plan:'unknown',seat:'unknown'},needsSetup:true,storage:'session'}}),
    workspaceRelayIdentity:()=>null,workspaceRelayViewerState:()=>{},workspaceState:{history:[]},workspaceServerHistory:[],
    workspaceJournalUnavailable:false,workspaceInputFreshness:[],WORKSPACE_CONTROL_CONFIG:{url:'http://localhost:1234',token:'local'},
    async controlRequest(route,body){calls.push({route,body});return {relay:{context:null},operation:null};}};
  vm.runInNewContext(source,env);
  await env.workspaceControlTick();
  assert.equal(calls.length,1);
  assert.equal(calls[0].route,'poll');
  const context=calls[0].body.relay.context;
  assert.equal(context.selection.length,20);
  assert.equal(context.selection_total,21);
  assert.equal(context.selection_truncated,true);
  assert.equal(context.user_id,null);
  assert.deepEqual(JSON.parse(JSON.stringify(context.profile)),{declared:{plan:'unknown',seat:'unknown'},needsSetup:true,storage:'session'});
  assert.equal(JSON.stringify(calls[0].body).includes('Node'),true);
  assert.equal(JSON.stringify(calls[0].body).includes('PRIVATE TEXT'),false);
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
test('fresh import forwards the signed option and reads back the newly created page',async()=>{
  let fresh;
  const {run}=driver('import',(m,post,env)=>{
    if(m.type==='ready')post({ready:true,session_nonce:m.session_nonce});
    if(m.type==='import'){fresh=m.fresh;post({type:'busy',value:true,operation:'import'});post({type:'status',event:'imported',page_id:'8:4',source_sha256:'abc'});env.figma.currentPage={id:'8:4'};post({type:'busy',value:false});}
    if(m.type==='export')post({type:'readback',data:{format:'figma-flow-readback-v1',pages:[{id:'8:4',declared_metadata:{complete:true},source_sha256:'abc'}]}});
  });
  const value=await run('import',{fresh:true});
  assert.equal(fresh,true);assert.equal(value.pages[0].id,'8:4');
});
test('import native summary returns its summary field without exporting a full readback',async()=>{
  const {run}=driver('import',(m,post)=>{
    if(m.type==='ready')post({ready:true,session_nonce:m.session_nonce});
    if(m.type==='native-summary')post({type:'native-summary',summary:{schema:'figma-flow-native-read-summary-v1',coverage:{profile:'summary',complete:false,nodeIds:['0:1'],fields:['width','height']}}});
  });
  assert.equal((await run('native-summary')).coverage.complete,false);
});
test('sync preview survives only when the local app emits the same safe localhost URL',async()=>{
  const run=preview=>{
    const {run}=driver('import',(m,post)=>{
      if(m.type==='ready')post({ready:true,paired:true,session_nonce:m.session_nonce});
      if(m.type==='sync'){
        post({type:'sync-result',result:{status:'applied',preview_url:'http://localhost:4310/'}});
        if(preview)post({type:'preview',url:preview});
      }
    });
    return run('sync');
  };
  assert.equal((await run('http://localhost:4310/')).preview_url,'http://localhost:4310/');
  assert.equal(Object.hasOwn(await run('http://localhost:9999/'),'preview_url'),false);
  assert.equal(Object.hasOwn(await run(undefined),'preview_url'),false);
});
test('graph errors return diagnostic readback instead of an apparent success',async()=>{
  const {run}=driver('sync',(m,post)=>post({session:m.session,operation:m.type,error:'collision',readback:{status:'rolled-back'}}));
  await assert.rejects(run('apply'),e=>e.message==='collision' && e.nativeReadback.status==='rolled-back');
});
test('partial apply forwards only unique selections pinned by the graph plan',async()=>{
  let received;
  const {run,env}=driver('sync',(m,post)=>{
    received=m;
    post({session:m.session,operation:m.type,readback:{schema:'figma-flow-graph-token-readback-v1',file_key:'file',page_id:'0:1',status:'success'}});
  });
  env.workspaceOpen=async()=>{
    const config={session:'s',selection_manifest:{plan_sha256:'a'.repeat(64),changes:[{identity:'space / 1'},{identity:'color'}]}};
    const active={inFlight:0,html:`<script type="application/json" id="flow-model">${JSON.stringify(config)}</script>`};
    active.handler=msg=>{received=msg;receivedHandler(msg,event=>active.onOutput(event));};env.workspaceActive=active;return active;
  };
  await run('apply',{selection:{protocol:2,plan_sha256:'a'.repeat(64),selected_ids:['space / 1']}});
  assert.deepEqual(Array.from(received.selected_ids),['space / 1']);
  assert.equal(received.plan_sha256,'a'.repeat(64));
  async function receivedHandler(message,post){post({session:message.session,operation:message.type,readback:{schema:'figma-flow-graph-token-readback-v1',file_key:'file',page_id:'0:1',status:'success'}});}
});
test('selected IDs cannot turn a native-edit apply into a full unfiltered apply',async()=>{
  let calls=0;
  const {run,env}=driver('native-edit',()=>calls++);
  env.workspaceOpen=async()=>{const active={inFlight:0,model:{session:'s'},html:'<script type="application/json" id="flow-model">{"session":"s"}</script>'};active.handler=()=>calls++;env.workspaceActive=active;return active;};
  await assert.rejects(run('apply',{selection:{protocol:2,plan_sha256:'a'.repeat(64),selected_ids:['one']}}),/only to a signed graph token task/);
  assert.equal(calls,0);
});
test('discovery returns the actual scoped getter and never calls apply',async()=>{
  const {run}=driver('discover',(m,post)=>{assert.equal(m.type,'read');post({session:m.session,operation:m.type,readback:{schema:'figma-flow-graph-native-discovery-v1',fileKey:'file',pageId:'0:1',nodes:[{id:'n'}]}});});
  assert.equal((await run('read')).nodes[0].id,'n');
});
test('discovery native summary preserves the panel readback contract',async()=>{
  const {run}=driver('discover',(m,post)=>post({session:m.session,operation:m.type,readback:{schema:'figma-flow-native-read-summary-v1',coverage:{profile:'summary',complete:false,nodeIds:['0:1'],fields:['width','height']}}}));
  assert.equal((await run('native-summary')).coverage.profile,'summary');
});
test('signed carousel commands reuse the current task readback and return the presentation request',async()=>{
  const {run,env}=driver('native-edit',()=>{});
  const carousel={schema:'figma-flow-carousel-summary-v1',status:'current',file_key:'file',page_id:'0:1',initial_state:'s0',flow_start_node_id:'0:9',states:[{state_id:'s0',status:'current'}],edges:[]};
  let request;
  env.workspaceHomeSession='home';env.workspaceState={history:[{taskKey:'sample',revision:'r',executionId:'run-1',carousel}]};
  env.workspaceStoredCarousel=value=>value;
  env.workspaceSelectCarousel=async(_current,value,home)=>{request={...value,home};return {type:'workspace-carousel-presented',presentation:'openExternal-requested',url:'https://www.figma.com/proto/file/SaaS?node-id=0-9'}};
  const result=await run('carousel-present',{viewer_options:{execution_id:'run-1',state_id:'s0'}});
  assert.equal(request.action,'present');assert.equal(request.taskKey,'sample');assert.equal(request.workspaceSession,'home');assert.equal(request.home,true);
  assert.equal(result.presentation,'openExternal-requested');
});
test('a signed native read stores its carousel receipt under read rather than apply',async()=>{
  const {run,env}=driver('native-edit',()=>{});
  const digest='a'.repeat(64), config={session:'s',web_screen_receipt:{graph_sha256:digest,screen_ids:['screen']}};
  let attached;
  env.workspaceAttachCarousel=(_active,_data,_page,operation)=>{attached=operation;};
  env.workspaceOpen=async()=>{
    const active={inFlight:0,html:`<script type="application/json" id="flow-model">${JSON.stringify(config)}</script>`};
    active.handler=message=>active.onOutput({session:'s',operation:'read',readback:{schema:'figma-flow-web-screen-discovery-v1',readback_scope:'screens',
      graph_sha256:digest,fileKey:'file',pageId:'0:1',nodes:[{}],native_edit:{operation:'read',applied:false},
      web_design:{graph_sha256:digest,screens:[{screen_id:'screen'}],carousel:{}}}});
    env.workspaceActive=active;return active;
  };
  await run('read');
  assert.equal(attached,'read');
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
