const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../figma-bridge/workspace_changes.js'),'utf8');
const controlSource = fs.readFileSync(path.join(__dirname,'../figma-bridge/workspace_control.js'),'utf8');
const policy = require('../library/figma-profile/policy.json');
function load(extra={}) {const env={WORKSPACE_PROFILE_POLICY:policy,...extra};vm.runInNewContext(source,env);return env;}
const scope={file_key:'file-A',page_id:'page-A',generation:'a'.repeat(32),session_id:'session-A'};

test('feed emits bounded, deduped metadata and never copies native values',()=>{
  const e=load();const feed=e.createWorkspaceChangeFeed({randomEpoch:()=> 'b'.repeat(32),maxEvents:2});
  feed.reset(scope);
  assert.equal(feed.recordMany([
    {id:'0:1',type:'PROPERTY_CHANGE',properties:['width','characters','width','name','paddingLeft','layoutMode','relativeTransform','experimentalThing']},
    {id:'0:1',type:'PROPERTY_CHANGE',properties:['width','characters','width','name','paddingLeft','layoutMode','relativeTransform','experimentalThing']}
  ]),1);
  const beforeOverflow=feed.batch(scope);
  assert.deepEqual(Array.from(beforeOverflow.events[0].properties),['characters','layoutMode','name','paddingLeft','relativeTransform','width']);
  assert.deepEqual(Array.from(beforeOverflow.events[0].unknown_properties),['experimentalThing']);
  assert.equal(feed.record({id:'0:1',type:'PROPERTY_CHANGE',properties:['width']}),true,'same changes in a later callback remain observable');
  feed.record({id:'0:2',type:'CREATE'});
  feed.record({id:'0:3',type:'DELETE'});
  const batch=feed.batch(scope);
  assert.equal(batch.cursor.seq,4);assert.equal(batch.events.length,2);
  assert.equal(batch.events.every(item=>item.origin==='unknown'),true);
  assert.equal(batch.gap.from,1);assert.equal(batch.gap.to,2);
  assert.equal(JSON.stringify(batch).includes('secret'),false);
  assert.equal(JSON.stringify(batch).includes('Morning session'),false);
});

test('property names cover the complete pinned Figma NodeChangeProperty union',()=>{
  const typings=fs.readFileSync(path.join(__dirname,'../library/figma-api/plugin-api.d.ts'),'utf8');
  const declaration=typings.match(/type NodeChangeProperty =([\s\S]*?)\n\ninterface NodeChangeEvent/);
  assert.ok(declaration,'pinned Figma API types must retain the NodeChangeProperty declaration');
  const names=[...declaration[1].matchAll(/'([^']+)'/g)].map(match=>match[1]).sort();
  const e=load();const feed=e.createWorkspaceChangeFeed({randomEpoch:()=> 'e'.repeat(32)});feed.reset(scope);
  for(let i=0;i<names.length;i+=32) feed.record({id:'0:'+i,type:'PROPERTY_CHANGE',properties:names.slice(i,i+32)});
  const events=feed.batch(scope).events;
  assert.deepEqual([...new Set(events.flatMap(event=>Array.from(event.properties)))].sort(),names);
  assert.equal(events.some(event=>event.unknown_properties.length>0),false);
});

test('only a matching durable acknowledgement retires queued events',()=>{
  const e=load();const feed=e.createWorkspaceChangeFeed({randomEpoch:()=> 'c'.repeat(32)});feed.reset(scope);
  feed.record({id:'0:1',type:'CREATE'});
  const batch=feed.batch(scope);
  assert.equal(feed.acknowledge({scope:{...scope,page_id:'page-B'},status:'available',accepted_cursor:{epoch:batch.cursor.epoch,seq:1}},scope),false);
  assert.equal(feed.getState().pending,1);
  assert.equal(feed.acknowledge({scope,status:'available',accepted_cursor:{epoch:batch.cursor.epoch,seq:2}},scope),false);
  assert.equal(feed.getState().pending,1);
  assert.equal(feed.acknowledge({scope,status:'available',accepted_cursor:{epoch:batch.cursor.epoch,seq:1}},scope),true);
  assert.equal(feed.getState().pending,0);
});

test('unavailable listener batches expose status without acknowledging pending edits',()=>{
  const e=load();const feed=e.createWorkspaceChangeFeed({randomEpoch:()=> 'd'.repeat(32)});feed.reset(scope);
  feed.record({id:'0:1',type:'CREATE'});
  const batch=feed.batch(scope,'unavailable');
  assert.equal(batch.status,'unavailable');assert.equal(batch.reason,'page-listener-unavailable');
  assert.deepEqual(Array.from(batch.events),[]);assert.equal(batch.gap,null);
  assert.equal(feed.acknowledge({scope,status:'unavailable',accepted_cursor:{epoch:batch.cursor.epoch,seq:1}},scope),false);
  assert.equal(feed.getState().pending,1);
});

test('scope changes reset cursor and reject events from the former page',()=>{
  const e=load();const feed=e.createWorkspaceChangeFeed({randomEpoch:()=>Math.random().toString(16).slice(2).padEnd(32,'0').slice(0,32)});
  feed.reset(scope);feed.record({id:'old',type:'CREATE'});
  const next={...scope,page_id:'page-B'};feed.reset(next);
  assert.equal(feed.batch(scope),null);
  assert.equal(feed.batch(next).cursor.seq,0);
  assert.equal(feed.getState().pending,0);
});

test('current page binding uses nodechange and unbinds the prior page',()=>{
  const events=()=>({handlers:new Map(),on(type,fn){this.handlers.set(type,fn);},off(type,fn){if(this.handlers.get(type)===fn)this.handlers.delete(type);}});
  const pageA=events();pageA.id='page-A';const pageB=events();pageB.id='page-B';
  const e=load({figma:{fileKey:'file-A',currentPage:pageA},WORKSPACE_RUNTIME:{generation:scope.generation},controlRunSession:scope.session_id,
    workspaceActive:null,setTimeout:()=>1,clearTimeout:()=>{}});
  e.workspaceBindChangePage();
  assert.equal(pageA.handlers.has('nodechange'),true);
  pageA.handlers.get('nodechange')({nodeChanges:[{id:'0:1',type:'CREATE'}]});
  e.figma.currentPage=pageB;e.workspaceBindChangePage();
  assert.equal(pageA.handlers.has('nodechange'),false);assert.equal(pageB.handlers.has('nodechange'),true);
  pageB.handlers.get('nodechange')({nodeChanges:[{id:'0:2',type:'PROPERTY_CHANGE',properties:['width','characters']}]});
  const batch=e.workspaceChangeFeed.batch({...scope,page_id:'page-B'});
  assert.equal(batch.events[0].node_id,'0:2');assert.deepEqual(Array.from(batch.events[0].properties),['characters','width']);
  e.figma.currentPage=pageA;e.workspaceBindChangePage();
  const resumed=e.workspaceChangeFeed.batch(scope);
  assert.equal(resumed.events[0].node_id,'0:1');
});

test('failed page listener registration is reported and retried after loading the active page',async()=>{
  let retry,attempts=0,loads=0;const page={id:'page-A',on(){if(++attempts===1)throw Error('not loaded');},off(){},async loadAsync(){loads++;}};
  const e=load({figma:{fileKey:'file-A',currentPage:page},WORKSPACE_RUNTIME:{generation:scope.generation},controlRunSession:scope.session_id,
    setTimeout(fn){retry=fn;return 1;},clearTimeout(){}});
  e.workspaceBindChangePage();
  assert.equal(e.workspaceChangeFeedStatus.status,'unavailable');
  await retry();
  assert.equal(loads,1);assert.equal(e.workspaceChangeFeedStatus.status,'available');
});

test('authenticated poll piggybacks events and retires only the acknowledged cursor',async()=>{
  const calls=[];const page={id:'page-A',on(){},off(){}};
  const env=load({figma:{fileKey:'file-A',currentPage:page},WORKSPACE_RUNTIME:{generation:scope.generation},
    WORKSPACE_CONTROL_CONFIG:{url:'http://localhost:1234',token:'fixture'},workspaceActive:null,workspaceHomeSession:'home',
    workspaceState:{history:[]},workspaceServerHistory:[],workspaceJournalUnavailable:false,workspaceInputFreshness:[],
    async controlRequest(route,body){calls.push({route,body});return {operation:null,changes:{scope:body.change_batch.scope,status:'available',
      accepted_cursor:{epoch:body.change_batch.cursor.epoch,seq:body.change_batch.cursor.seq}}};}});
  vm.runInNewContext(controlSource,env);
  const current=env.workspaceChangeScope();env.workspaceBindChangePage();env.workspaceChangeFeed.reset(current);
  env.workspaceChangeFeed.record({id:'0:1',type:'PROPERTY_CHANGE',properties:['width']});
  await env.workspaceControlTick();
  assert.equal(calls.length,1);assert.equal(calls[0].route,'poll');
  assert.deepEqual(Object.keys(calls[0].body.change_batch.scope).sort(),['file_key','generation','page_id','session_id']);
  assert.equal(calls[0].body.change_batch.events[0].node_id,'0:1');
  assert.equal(env.workspaceChangeFeed.getState().pending,0);
});
