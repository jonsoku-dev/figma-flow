"""Offline messaging and host-behavior regressions; these are not live Figma proof."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node required for bridge runtime checks')
class BridgeUITests(unittest.TestCase):
    def run_node(self, script):
        result = subprocess.run(['node', '-e', script, str(ROOT)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ui_accepts_wrapped_session_messages_and_rejects_stale_messages(self):
        self.run_node(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const html = fs.readFileSync(process.argv[1]+'/figma-bridge/ui.html','utf8');
const nodes = Object.fromEntries(['import','export','sync','save','fresh','json','status','preview','preview-frame','preview-link'].map(id=>[id,{disabled:['import','export','sync','save'].includes(id),hidden:['sync','preview'].includes(id),checked:false,value:'',textContent:''}]));
const sent=[], timers=new Map(); let timerId=0, cleared=0;
const parent = {postMessage(message, origin) { assert.equal(origin,'*'); assert.equal(typeof context.window.onmessage,'function'); sent.push(message.pluginMessage); }};
const context = {parent,window:{},document:{getElementById:id=>nodes[id]},crypto:require('node:crypto').webcrypto,Uint8Array,
  setTimeout(fn) {timers.set(++timerId,fn);return timerId;},clearTimeout(id){timers.delete(id);cleared++;}};
vm.runInNewContext(html.split('<script>')[1].split('</script>')[0],context);
assert.equal(sent.length,1); assert.equal(sent[0].type,'ready');
const nonce = sent[0].session_nonce; assert.match(nonce,/^[a-f0-9]{32}$/);
assert.ok(nodes.import.disabled && nodes.export.disabled && nodes.save.disabled);
const receive = message => context.window.onmessage({source:{wrappedByFigma:true},data:{pluginMessage:message}});
receive({type:'status',ready:true,message:'forged',session_nonce:'0'.repeat(32)});
assert.equal(nodes.status.textContent,'');assert.equal(nodes.import.disabled,true);
receive({type:'status',ready:true,message:'connected',session_nonce:nonce});
assert.equal(nodes.status.textContent,'connected');assert.equal(nodes.import.disabled,false);assert.equal(cleared,1);
assert.equal(nodes.sync.hidden,true);
nodes.import.onclick();nodes.export.onclick();assert.deepEqual(sent.slice(1).map(x=>x.type),['import','export']);
assert.ok(sent.every(x=>x.session_nonce===nonce));
receive({type:'readback',data:{fake:true},session_nonce:'0'.repeat(32)});
assert.equal(nodes.save.disabled,true);assert.equal(nodes.json.value,'');
receive({type:'readback',data:{format:'figma-flow-readback-v1',pages:[]},session_nonce:nonce});
assert.equal(nodes.save.disabled,false);assert.deepEqual(JSON.parse(nodes.json.value).pages,[]);
receive({type:'busy',value:true,session_nonce:nonce});assert.ok(nodes.import.disabled && nodes.export.disabled);
receive({type:'busy',value:false,session_nonce:nonce});assert.ok(!nodes.import.disabled && !nodes.export.disabled);
receive({type:'status',ready:true,paired:true,message:'paired',session_nonce:nonce});assert.equal(nodes.sync.hidden,false);
nodes.sync.onclick();assert.equal(sent.at(-1).type,'sync');assert.equal(sent.at(-1).session_nonce,nonce);
receive({type:'busy',value:true,session_nonce:nonce});assert.equal(nodes.sync.disabled,true);
receive({type:'sync-result',result:{status:'applied',changed_tokens:['color.brand'],screens:['SCR-1'],code_ids:['CODE-1'],files:['app.css'],report:'report.md'},session_nonce:nonce});
assert.match(nodes.status.textContent,/앱 반영 완료/);assert.match(nodes.status.textContent,/변경 토큰 1개/);assert.match(nodes.status.textContent,/SCR-1/);assert.match(nodes.status.textContent,/CODE-1/);assert.match(nodes.status.textContent,/app.css/);assert.match(nodes.status.textContent,/report.md/);
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes.sync.disabled,false);
receive({type:'preview',url:'https://example.com/',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);
receive({type:'preview',url:'http://127.0.0.1:43123/',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);
receive({type:'preview',url:'http://localhost:43123/',session_nonce:'0'.repeat(32)});assert.equal(nodes.preview.hidden,true);
receive({type:'preview',url:'http://localhost:43123/',session_nonce:nonce});assert.equal(nodes.preview.hidden,false);assert.equal(nodes['preview-frame'].src,'http://localhost:43123/');assert.equal(nodes['preview-link'].href,'http://localhost:43123/');
receive({type:'busy',value:true,operation:'sync',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);assert.equal(nodes['preview-frame'].src,'about:blank');assert.equal(nodes['preview-link'].href,'');
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes.sync.disabled,false);
receive({type:'preview',url:'http://localhost:43123/',session_nonce:nonce});
receive({type:'status',message:'Error: sync failed',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);assert.equal(nodes['preview-frame'].src,'about:blank');
receive({type:'preview',url:'http://localhost:43123/',session_nonce:nonce});
receive({type:'sync-result',result:{status:'applied',preview_error:'Browser capture failed'},session_nonce:nonce});assert.equal(nodes.preview.hidden,true);assert.match(nodes.status.textContent,/미리보기 오류: Browser capture failed/);
assert.match(html, /title="반영된 앱과 실제 화면 비교"/);assert.match(html, /rel="noopener noreferrer"/);
for(const status of ['baseline','unchanged']) { receive({type:'sync-result',result:{status,changed_tokens:[],screens:[],code_ids:[],files:[],report:null},session_nonce:nonce});assert.match(nodes.status.textContent,status==='baseline'?/기준선 저장/:/변경 없음/); }
receive({type:'status',message:'Error: getter failed',session_nonce:nonce});assert.match(nodes.status.textContent,/Error: getter failed/);
const other = {...context,window:{},parent:{postMessage(){}}};vm.runInNewContext(html.split('<script>')[1].split('</script>')[0],other);
[...timers.values()][0]();assert.match(nodes.status.textContent,/Error:/);
''')

    def test_host_requires_ready_and_preserves_readback_with_throwing_native_getters(self):
        self.run_node(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const nonce='1234567890abcdef1234567890abcdef', messages=[];
const page={id:'page',type:'PAGE',name:'Import',getPluginData(){return JSON.stringify({bridge:1,complete:true});},async loadAsync(){},children:[],findAll(){return [node,...node.children];}};
const node={id:'instance',type:'INSTANCE',name:'Instance',getPluginData(){return '{}';},children:[{id:'label',type:'TEXT',name:'Label',characters:'Kept text',getPluginData(){return '{}';}}],
  get componentProperties(){throw Error('not a variant instance');},get variantProperties(){throw Error('variant getter unavailable');},
  get annotations(){throw Error('annotations unavailable');},async getMainComponentAsync(){throw Error('component unavailable');}};
page.children.push(node);
node.parent=page;node.children[0].parent=node;
const figma={currentPage:page,root:{children:[page]},ui:{postMessage(message){messages.push(message);}},
  showUI(){assert.equal(typeof figma.ui.onmessage,'function');},
  variables:{async getLocalVariableCollectionsAsync(){return [];},async getLocalVariablesAsync(){return [];}}};
const context={figma,__html__:'',PAYLOAD:{source_sha256:'a'.repeat(64),screens:[]}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1]+'/figma-bridge/native_semantic_read.js','utf8')+'\n'+fs.readFileSync(process.argv[1]+'/figma-bridge/code.js','utf8'),context);
(async()=>{
await figma.ui.onmessage({type:'export'});await figma.ui.onmessage({type:'export',session_nonce:nonce});assert.equal(messages.length,0);
await figma.ui.onmessage({type:'ready',session_nonce:nonce});
assert.ok(messages.find(x=>x.type==='status' && x.ready===true));assert.ok(messages.every(x=>x.session_nonce===nonce));
const before=messages.length;await figma.ui.onmessage({type:'export',session_nonce:'f'.repeat(32)});assert.equal(messages.length,before);
await figma.ui.onmessage({type:'ready',session_nonce:'f'.repeat(32)});assert.equal(messages.length,before);
await figma.ui.onmessage({type:'export',session_nonce:nonce});
const readback=messages.find(x=>x.type==='readback');assert.ok(readback);assert.equal(readback.session_nonce,nonce);
const saved=readback.data.pages[0].children[0];assert.equal(saved.children[0].characters,'Kept text');
assert.equal(saved.componentProperties,undefined);assert.match(saved.unavailable_fields.componentProperties,/not a variant/);
assert.match(saved.unavailable_fields.variantProperties,/unavailable/);assert.match(saved.unavailable_fields.main_component_id,/unavailable/);
const native=readback.data.nodes.find(row=>row.id==='instance');
assert.match(native.unavailable_fields.mainComponentId,/component unavailable/);
assert.equal(native.mainComponentId,undefined);
assert.equal(saved.annotations_status,'unavailable');assert.match(saved.unavailable_fields.annotations,/unavailable/);
figma.variables.getLocalVariablesAsync=async()=>{throw Error('readback failed');};
await figma.ui.onmessage({type:'export',session_nonce:nonce});assert.ok(messages.find(x=>x.type==='status' && x.message==='Error: readback failed'));
assert.equal(messages.at(-1).type,'busy');assert.equal(messages.at(-1).value,false);
// Model Figma's resize behavior: resizing an auto-layout node fixes its axes.
const frame={resize(width,height){this.width=width;this.height=height;this.primaryAxisSizingMode='FIXED';this.counterAxisSizingMode='FIXED';}};
context.layout(frame,390,24);assert.equal(frame.width,390);assert.equal(frame.primaryAxisSizingMode,'AUTO');assert.equal(frame.counterAxisSizingMode,'FIXED');
assert.equal(frame.paddingBottom,24);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_geometry_values_and_bindings_follow_tokens_and_snapshot_native_corners(self):
        self.run_node(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const corners=['topLeftRadius','topRightRadius','bottomRightRadius','bottomLeftRadius'];
const padding=['paddingTop','paddingRight','paddingBottom','paddingLeft'];
const variables=new Map([['space.round',{id:'round',value:12}],['space.card',{id:'padding',value:16}],['size.body',{id:'size',value:22}]]);
const context={figma:{ui:{},showUI(){}},__html__:'',PAYLOAD:{variable_values:{'space.round':['FLOAT',12],'space.card':['FLOAT',16],'size.body':['FLOAT',22]}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1]+'/figma-bridge/native_semantic_read.js','utf8')+'\n'+fs.readFileSync(process.argv[1]+'/figma-bridge/code.js','utf8'),context);
function nativeNode(type,fields) {
  const values={},bindings={};
  const node={id:type,type,name:type,boundVariables:bindings,getPluginData(){return '{}';},setBoundVariable(field,variable){assert.ok(fields.includes(field),'unsupported native binding '+field);bindings[field]={type:'VARIABLE_ALIAS',id:variable.id};}};
  for(const field of fields) Object.defineProperty(node,field,{configurable:true,get(){const alias=bindings[field];return alias?[...variables.values()].find(v=>v.id===alias.id).value:values[field];},set(value){values[field]=value;}});
  if(type==='COMPONENT') Object.defineProperty(node,'cornerRadius',{get(){const all=corners.map(field=>node[field]);return all.every(value=>value===all[0])?all[0]:Symbol('mixed');}});
  return node;
}
(async()=>{
  for(const radius of ['radius','cornerRadius','border-radius']) {
    const node=nativeNode('COMPONENT',[...corners,...padding]);
    const label=nativeNode('TEXT',['fontSize']);node.children=[label];const warnings=new Set();
    context.applyProps(node,label,{[radius]:'space.round',padding:'space.card','font-size':'size.body'},variables,warnings,new Map());
    for(const field of corners) {assert.equal(node[field],12);assert.equal(node.boundVariables[field].id,'round');}
    for(const field of padding) {assert.equal(node[field],16);assert.equal(node.boundVariables[field].id,'padding');}
    assert.equal(node.boundVariables.cornerRadius,undefined);assert.equal(node.boundVariables.fontSize,undefined);
    assert.equal(label.fontSize,22);assert.equal(label.boundVariables.fontSize.id,'size');assert.equal(warnings.size,0);
    assert.throws(()=>context.applyProps(node,label,{width:'space.card'},variables,warnings,new Map()),/Unsupported reviewed native property: width/);
    variables.get('space.round').value=28;variables.get('space.card').value=24;variables.get('size.body').value=30;
    const saved=await context.snapshot(node);
    assert.equal(saved.cornerRadius,28);for(const field of corners)assert.equal(saved[field],28);
    for(const field of padding)assert.equal(saved[field],24);assert.equal(saved.children[0].fontSize,30);
    assert.equal(saved.children[0].boundVariables.fontSize.id,'size');
    Object.defineProperty(node,'bottomRightRadius',{get(){return 3;}});
    const mixed=await context.snapshot(node);assert.equal(mixed.cornerRadius,undefined);assert.equal(mixed.topLeftRadius,28);assert.equal(mixed.bottomRightRadius,3);
    Object.defineProperty(node,'topRightRadius',{get(){throw Error('corner unavailable');}});
    const partial=await context.snapshot(node);assert.equal(partial.topRightRadius,undefined);assert.equal(partial.topLeftRadius,28);assert.match(partial.unavailable_fields.topRightRadius,/corner unavailable/);
    const textOnly=await context.snapshot(label);assert.equal(textOnly.cornerRadius,undefined);assert.equal(textOnly.topLeftRadius,undefined);
    variables.get('space.round').value=12;variables.get('space.card').value=16;variables.get('size.body').value=22;
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_paired_sync_scopes_native_readback_guards_identity_and_allows_retry(self):
        self.run_node(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source=fs.readFileSync(process.argv[1]+'/figma-bridge/native_semantic_read.js','utf8')+'\n'+fs.readFileSync(process.argv[1]+'/figma-bridge/code.js','utf8');
const nonce='1234567890abcdef1234567890abcdef', digest='a'.repeat(64);
const config={url:'http://localhost:43123/sync',preview_url:'http://localhost:43123/',token:'test-pairing-token',page_id:'2:77',file_key:'paired-file'};
function setup(paired=true,pair=config) {
  const messages=[], requests=[];
  const meta={bridge:1,complete:true,source_sha256:digest,collection_id:'collection'};
  const page={id:'2:77',type:'PAGE',name:'Paired',getPluginData(){return JSON.stringify(meta);},async loadAsync(){},children:[],findAll(){return [];}};
  const unrelated={id:'other-page',getPluginData(){return '{}';},async loadAsync(){throw Error('unrelated page loaded');},get children(){throw Error('unrelated data read');}};
  const collection={id:'collection',name:'Owned',defaultModeId:'default',modes:[{modeId:'default'}],getPluginData(){return JSON.stringify({bridge:1,source_sha256:digest});}};
  const variable={id:'owned-variable',name:'color/brand',resolvedType:'COLOR',variableCollectionId:'collection',valuesByMode:{default:{r:1,g:0,b:0,a:1}},getPluginData(){return JSON.stringify({semantic_id:'color.brand'});}};
  const otherVariable={variableCollectionId:'unrelated',get valuesByMode(){throw Error('unrelated variable read');}};
  const sizes=[];
  const figma={fileKey:'paired-file',currentPage:page,root:{children:[page,unrelated]},ui:{postMessage(message){messages.push(message);},resize(width,height){sizes.push([width,height]);}},showUI(){},variables:{async getLocalVariableCollectionsAsync(){return [collection];},async getLocalVariablesAsync(){return [variable,otherVariable];}}};
  let reply={status:'baseline',changed_tokens:[],screens:[],code_ids:[],files:[],report:'baseline.json'}, ok=true, pending=null;
  const context={figma,__html__:'',PAYLOAD:{source_sha256:digest,screens:[],technical_existing_only:paired},async fetch(url,options){requests.push({url,options});if(pending)await pending;if(reply instanceof Error)throw reply;return {ok,status:ok?200:409,async json(){return reply;}};}};
  vm.createContext(context);
  vm.runInContext((paired?'const LOCAL_SYNC='+JSON.stringify(pair)+';\n':'')+source,context);
  return {figma,meta,page,collection,unrelated,messages,requests,sizes,send:type=>figma.ui.onmessage({type,session_nonce:nonce}),setReply(value,success=true){reply=value;ok=success;},hold(promise){pending=promise;}};
}
(async()=>{
  const h=setup();await h.send('ready');assert.equal(h.messages.find(x=>x.ready).paired,true);
  await h.send('sync');assert.equal(h.requests.length,1);
  const request=h.requests[0];assert.equal(request.url,config.url);assert.equal(request.options.method,'POST');
  assert.equal(request.options.headers.Authorization,'Bearer '+config.token);assert.equal(request.options.headers['Content-Type'],'application/json');
  const body=JSON.parse(request.options.body);assert.deepEqual(Object.keys(body).sort(),['file_key','page_id','readback']);
  assert.equal(body.file_key,config.file_key);assert.equal(body.page_id,config.page_id);assert.equal(body.readback.format,'figma-flow-readback-v1');
  assert.equal(body.readback.scope,'paired-active-import-page');assert.deepEqual(body.readback.pages.map(x=>x.id),['2:77']);
  assert.deepEqual(body.readback.collections.map(x=>x.id),['collection']);assert.deepEqual(body.readback.variables.map(x=>x.id),['owned-variable']);
  assert.equal(h.messages.find(x=>x.type==='sync-result').result.status,'baseline');
  for(const status of ['applied','unchanged']) {h.setReply({status,changed_tokens:['color.brand'],screens:['SCR-1'],code_ids:['CODE-1'],files:['style.css'],report:'report.md'});await h.send('sync');assert.equal(h.messages.findLast(x=>x.type==='sync-result').result.status,status);}
  h.setReply({error:'Token edit rejected'},false);await h.send('sync');assert.match(h.messages.findLast(x=>x.type==='status').message,/Token edit rejected/);assert.equal(h.messages.at(-1).value,false);
  h.setReply(new Error('Network unavailable'));await h.send('sync');assert.match(h.messages.findLast(x=>x.type==='status').message,/Network unavailable/);assert.equal(h.messages.at(-1).value,false);
  h.setReply({status:'unknown'});await h.send('sync');assert.match(h.messages.findLast(x=>x.type==='status').message,/올바른 반영 결과/);
  h.setReply({status:'unchanged'});let release;h.hold(new Promise(resolve=>{release=resolve;}));
  const first=h.send('sync');await new Promise(resolve=>setImmediate(resolve));const calls=h.requests.length;
  assert.equal(h.messages.findLast(m=>m.type==='busy').value,true);await h.send('sync');assert.equal(h.requests.length,calls);release();await first;assert.equal(h.messages.at(-1).value,false);
  h.hold(null);await h.send('sync');assert.equal(h.requests.length,calls+1);
  for(const preview_url of ['https://example.com/','http://127.0.0.1:43123/','http://localhost:9999/','http://localhost:43123/?token=secret']) {h.setReply({status:'applied',preview_url});await h.send('sync');assert.equal(h.messages.filter(x=>x.type==='preview').length,0);}
  h.setReply({status:'applied',preview_url:config.preview_url});await h.send('sync');
  const preview=h.messages.findLast(x=>x.type==='preview');assert.equal(preview.url,config.preview_url);assert.equal(preview.session_nonce,nonce);assert.equal(preview.token,undefined);assert.deepEqual(h.sizes,[[820,720]]);
  assert.ok(h.messages.some(x=>x.type==='busy' && x.value===true && x.operation==='sync'));
  h.setReply({status:'applied',preview_url:config.preview_url,preview_error:'Capture unavailable'});await h.send('sync');assert.equal(h.messages.filter(x=>x.type==='preview').length,1);assert.equal(h.messages.findLast(x=>x.type==='sync-result').result.preview_error,'Capture unavailable');
  const numeric=setup(true,{...config,preview_url:'http://127.0.0.1:43123/'});await numeric.send('ready');numeric.setReply({status:'applied',preview_url:'http://127.0.0.1:43123/'});await numeric.send('sync');assert.equal(numeric.messages.filter(x=>x.type==='preview').length,0);
  const denied = [
    x=>{x.figma.currentPage={...x.page,id:'wrong'};},
    x=>{delete x.figma.fileKey;}, x=>{x.figma.fileKey='wrong-file';},
    x=>{x.meta.bridge=0;},x=>{x.meta.complete=false;},x=>{x.meta.source_sha256='b'.repeat(64);},
    x=>{delete x.meta.collection_id;},x=>{x.meta.collection_id='missing';},
    x=>{x.collection.getPluginData=()=>JSON.stringify({bridge:1,source_sha256:'b'.repeat(64)});},
    x=>{x.unrelated.getPluginData=()=>JSON.stringify({collection_id:'collection'});}
  ];
  for(const alter of denied) {const x=setup();await x.send('ready');alter(x);await x.send('sync');assert.equal(x.requests.length,0);assert.match(x.messages.findLast(m=>m.type==='status').message,/Error:/);assert.equal(x.messages.at(-1).value,false);}
  const offline=setup(false);await offline.send('ready');assert.equal(offline.messages.find(x=>x.ready).paired,false);await offline.send('sync');assert.equal(offline.requests.length,0);
  const missingFile=setup(true,{...config,file_key:null});await missingFile.send('ready');await missingFile.send('sync');assert.equal(missingFile.requests.length,0);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


if __name__ == '__main__':
    unittest.main()
