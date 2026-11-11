"""Offline messaging and host-behavior regressions; these are not live Figma proof."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node required for bridge runtime checks')
class BridgeUITests(unittest.TestCase):
    def run_node(self, script):
        setup = "globalThis.renderPanelTemplate = name => require('node:child_process').execFileSync(" + json.dumps(sys.executable) + ", ['-B','-c', \"import sys;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/'tools'));from panel_components import render_components;p=Path(sys.argv[1])/sys.argv[2];print(render_components(p.read_text(),sys.argv[3]))\", process.argv[1], 'figma-bridge/'+name, name==='ui.html'?'import':'chat'], {encoding:'utf8'});\n"
        result = subprocess.run(['node', '-e', setup + script, str(ROOT)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ui_accepts_wrapped_session_messages_and_rejects_stale_messages(self):
        self.run_node(r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const html = renderPanelTemplate('ui.html');
const ids=Array.from(html.matchAll(/\bid="([^"]+)"/g),match=>match[1]);
const nodes = Object.fromEntries(ids.map(id=>[id,{disabled:['import','export','sync','save','fresh'].includes(id),hidden:['sync','sync-section','preview','readback-result'].includes(id),checked:false,value:'',textContent:'',dataset:{},attributes:{},addEventListener(type,handler){this[type]=handler;},setAttribute(key,value){this.attributes[key]=value;},removeAttribute(key){delete this.attributes[key];},replaceChildren(...children){this.children=children;},appendChild(child){(this.children ||= []).push(child);}}]));
const sent=[], timers=new Map(), downloads=[],revoked=[]; let timerId=0, cleared=0;
const parent = {postMessage(message, origin) { assert.equal(origin,'*'); assert.equal(typeof context.window.onmessage,'function'); sent.push(message.pluginMessage); }};
const context = {parent,window:{addEventListener(){}},document:{documentElement:{dataset:{}},getElementById:id=>nodes[id],body:{appendChild(link){downloads.push(link);}},createElement(){return {click(){this.clicked=true;},remove(){this.removed=true;}};}},crypto:require('node:crypto').webcrypto,Uint8Array,Blob,URL:{createObjectURL(){return 'blob:readback';},revokeObjectURL(url){revoked.push(url);}},
  setTimeout(fn) {timers.set(++timerId,fn);return timerId;},clearTimeout(id){timers.delete(id);cleared++;}};
const catalog=JSON.parse(fs.readFileSync(process.argv[1]+'/figma-bridge/locales/import.json','utf8'));
context.FlowUI={locale:'ko',apply(){},t(key,params={}){assert(catalog[key],key);return catalog[key].ko.replace(/\{(\w+)\}/g,(all,name)=>Object.hasOwn(params,name)?String(params[name]):all);}};
vm.runInNewContext(fs.readFileSync(process.argv[1]+'/figma-bridge/panel_components.js','utf8')+'\n'+html.split('<script>')[1].split('</script>')[0],context);
assert.equal(sent.length,1); assert.equal(sent[0].type,'ready');
const nonce = sent[0].session_nonce; assert.match(nonce,/^[a-f0-9]{32}$/);
assert.ok(nodes.import.disabled && nodes.export.disabled && nodes.save.disabled && nodes.fresh.disabled);
const receive = message => context.window.onmessage({source:{wrappedByFigma:true},data:{pluginMessage:message}});
receive({type:'status',ready:true,message:'forged',session_nonce:'0'.repeat(32)});
assert.equal(nodes.status.textContent,'');assert.equal(nodes.import.disabled,true);
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes.import.disabled,true);
receive({type:'status',ready:true,message:'connected',source_label:'connected',session_nonce:nonce});
assert.equal(nodes['source-meta'].textContent,'입력 · connected');assert.equal(nodes.import.disabled,false);assert.equal(cleared,1);
assert.equal(nodes['status-region'].dataset.state,'ready');assert.equal(nodes.status.hidden,true);assert.equal(nodes['readback-result'].hidden,true);assert.equal(nodes.import.className,'primary');assert.equal(nodes.sync.className,'secondary');assert.equal(nodes.sync.hidden,true);assert.equal(nodes.sync.disabled,true);
nodes.fresh.checked=true;nodes.fresh.onchange();assert.equal(nodes.import.textContent,'새 페이지로 가져오기');
nodes.import.onclick();nodes.export.onclick();assert.deepEqual(sent.slice(1).map(x=>x.type),['import']);
assert.equal(sent.at(-1).fresh,true);assert.equal(nodes['status-region'].dataset.state,'busy');assert.equal(nodes.fresh.disabled,true);assert.equal(nodes.workspace.attributes['aria-busy'],'true');
receive({type:'status',message:'기존 페이지를 열었습니다.',session_nonce:nonce});
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes['status-region'].dataset.state,'success');assert.equal(nodes.workspace.attributes['aria-busy'],'false');
nodes.export.onclick();assert.equal(sent.at(-1).type,'export');assert.ok(sent.every(x=>x.session_nonce===nonce));
receive({type:'readback',data:{fake:true},session_nonce:'0'.repeat(32)});
assert.equal(nodes.save.disabled,true);assert.equal(nodes.json.value,'');
receive({type:'readback',data:{format:'figma-flow-readback-v1',pages:[]},session_nonce:nonce});
assert.equal(nodes.save.disabled,true);assert.deepEqual(JSON.parse(nodes.json.value).pages,[]);
receive({type:'status',message:'페이지를 읽었습니다.',session_nonce:nonce});receive({type:'busy',value:false,session_nonce:nonce});
assert.equal(nodes.save.disabled,false);assert.match(nodes['status-title'].textContent,/읽었습니다/);assert.match(nodes['readback-meta'].textContent,/최근 읽은 결과/);assert.equal(nodes['readback-result'].hidden,false);assert.equal(nodes.save.className,'primary');assert.equal(nodes.import.className,'secondary');assert.equal(nodes['readback-details'].open,undefined);
nodes.save.onclick();assert.equal(downloads[0].download,'figma-flow-readback.json');assert.equal(downloads[0].href,'blob:readback');assert.ok(downloads[0].clicked && downloads[0].removed);
[...timers.values()][0]();assert.deepEqual(revoked,['blob:readback']);timers.clear();
receive({type:'busy',value:true,session_nonce:nonce});assert.ok(nodes.import.disabled && nodes.export.disabled && nodes.save.disabled);
receive({type:'busy',value:false,session_nonce:nonce});assert.ok(!nodes.import.disabled && !nodes.export.disabled);
receive({type:'status',ready:true,paired:true,message:'paired',source_label:'초대 화면',target_page_name:'검토 페이지',session_nonce:nonce});assert.equal(nodes['source-meta'].textContent,'입력 · 초대 화면\n연결 페이지 · 검토 페이지');assert.equal(nodes.sync.hidden,false);assert.equal(nodes['sync-section'].hidden,false);assert.equal(nodes.sync.className,'secondary');
nodes.sync.onclick();assert.equal(sent.at(-1).type,'sync');assert.equal(sent.at(-1).session_nonce,nonce);
receive({type:'busy',value:true,session_nonce:nonce});assert.equal(nodes.sync.disabled,true);
receive({type:'status',message:'현재 페이지를 읽었습니다. 앱 결과 대기',session_nonce:nonce});assert.equal(nodes['status-region'].dataset.state,'busy');
receive({type:'sync-result',result:{status:'applied',changed_tokens:['color.brand'],screens:['SCR-1'],code_ids:['CODE-1'],files:['app.css'],report:'report.md'},session_nonce:nonce});
assert.match(nodes['status-title'].textContent,/앱 반영 완료/);assert.match(nodes.status.textContent,/변경 토큰 1개/);assert.match(nodes.status.textContent,/SCR-1/);assert.match(nodes.status.textContent,/CODE-1/);assert.match(nodes.status.textContent,/app.css/);assert.match(nodes.status.textContent,/report.md/);assert.equal(nodes['status-region'].dataset.state,'success');
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes.sync.disabled,false);
receive({type:'preview',url:'https://example.com/',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);
receive({type:'preview',url:'http://127.0.0.1:43123/',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);
receive({type:'preview',url:'http://localhost:43123/',session_nonce:'0'.repeat(32)});assert.equal(nodes.preview.hidden,true);
receive({type:'preview',url:'http://localhost:43123/',session_nonce:nonce});assert.equal(nodes.preview.hidden,false);assert.equal(nodes['preview-frame'].src,'http://localhost:43123/');assert.equal(nodes['preview-link'].href,'http://localhost:43123/');
receive({type:'busy',value:true,operation:'sync',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);assert.equal(nodes['preview-frame'].src,'about:blank');assert.equal(nodes['preview-link'].href,'');
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes.sync.disabled,false);
receive({type:'preview',url:'http://localhost:43123/',session_nonce:nonce});
receive({type:'status',message:'Error: sync failed',session_nonce:nonce});assert.equal(nodes.preview.hidden,true);assert.equal(nodes['preview-frame'].src,'about:blank');assert.equal(nodes['status-region'].dataset.state,'error');assert.match(nodes.status.textContent,/다시 시도/);
receive({type:'busy',value:false,session_nonce:nonce});assert.equal(nodes['status-region'].dataset.state,'error');
receive({type:'preview',url:'http://localhost:43123/',session_nonce:nonce});
receive({type:'sync-result',result:{status:'applied',preview_error:'Browser capture failed'},session_nonce:nonce});assert.equal(nodes.preview.hidden,true);assert.match(nodes['diagnostic-text'].textContent,/Browser capture failed/);assert.match(nodes.status.textContent,/미리보기를 열지 못했습니다/);
assert.match(html, /title="반영된 앱과 실제 화면 비교"/);assert.match(html, /rel="noopener noreferrer"/);
for(const status of ['baseline','unchanged']) { receive({type:'sync-result',result:{status,changed_tokens:[],screens:[],code_ids:[],files:[],report:null},session_nonce:nonce});assert.match(nodes['status-title'].textContent,status==='baseline'?/기준선/:/변경 없음/); }
receive({type:'sync-result',result:{status:'unknown'},session_nonce:nonce});assert.equal(nodes['status-region'].dataset.state,'error');
receive({type:'status',ready:true,paired:true,existing_only:true,message:'paired existing',session_nonce:nonce});assert.equal(nodes['import-section'].hidden,true);assert.equal(nodes.import.disabled,true);assert.equal(nodes.heading.textContent,'앱 동기화');assert.equal(nodes.sync.className,'primary');
receive({type:'status',message:'Error: getter failed',session_nonce:nonce});assert.match(nodes['diagnostic-text'].textContent,/Error: getter failed/);assert.equal(nodes.diagnostics.hidden,false);
const other = {...context,window:{addEventListener(){}},parent:{postMessage(){}}};vm.runInNewContext(fs.readFileSync(process.argv[1]+'/figma-bridge/panel_components.js','utf8')+'\n'+html.split('<script>')[1].split('</script>')[0],other);
[...timers.values()][0]();assert.match(nodes.status.textContent,/Figma 연결 응답/);assert.equal(nodes['status-region'].dataset.state,'error');
''')

    def test_import_panel_translates_all_locales_dynamic_states_and_accessible_names(self):
        self.run_node(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const root=process.argv[1],html=renderPanelTemplate('ui.html');
const catalog={...JSON.parse(fs.readFileSync(root+'/figma-bridge/locales/workspace.json','utf8')),...JSON.parse(fs.readFileSync(root+'/figma-bridge/locales/import.json','utf8'))};
for(const [key,values] of Object.entries(catalog)) {
  assert.deepEqual(Object.keys(values).sort(),['en','ja','ko']);
  const params=Object.values(values).map(value=>[...value.matchAll(/\{(\w+)\}/g)].map(match=>match[1]).sort());
  assert.deepEqual(params[0],params[1],key);assert.deepEqual(params[0],params[2],key);
}
const runtime=fs.readFileSync(root+'/figma-bridge/panel_i18n.js','utf8').replace('__FLOW_MESSAGES__',JSON.stringify(catalog));
for(const locale of ['ko','en','ja']) {
  const all=[],ids={},events={},sent=[];
  const make=attrs=>({attributes:attrs,dataset:{},textContent:'',value:'',checked:false,disabled:Object.hasOwn(attrs,'disabled'),hidden:Object.hasOwn(attrs,'hidden'),children:[],
    addEventListener(type,handler){this[type]=handler;},getAttribute(key){return this.attributes[key]??null;},setAttribute(key,value){this.attributes[key]=value;},removeAttribute(key){delete this.attributes[key];},replaceChildren(...nodes){this.children=nodes;},appendChild(node){this.children.push(node);},click(){},remove(){}});
  for(const tag of html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/gi)) {
    const attrs={};for(const match of tag[2].matchAll(/([\w:-]+)(?:="([^"]*)")?/g))attrs[match[1]]=match[2]??'';
    const node=make(attrs);all.push(node);if(attrs.id)ids[attrs.id]=node;
  }
  const document={documentElement:all[0],getElementById:id=>ids[id],querySelectorAll:selector=>all.filter(node=>Object.hasOwn(node.attributes,selector.slice(1,-1))),createElement:()=>make({}),body:make({})};
  const context={document,navigator:{languages:[locale]},window:{addEventListener(type,fn){events[type]=fn;},dispatchEvent(event){events[event.type]?.(event);}},CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},crypto:require('node:crypto').webcrypto,Uint8Array,Blob,URL:{},setTimeout(){return 1;},clearTimeout(){},parent:{postMessage(message){sent.push(message.pluginMessage);}}};
  vm.createContext(context);vm.runInContext(runtime+'\n'+fs.readFileSync(root+'/figma-bridge/panel_components.js','utf8')+'\n'+html.split('<script>')[1].split('</script>')[0],context);
  const tr=(key,params={})=>catalog['import.'+key][context.FlowUI.locale].replace(/\{(\w+)\}/g,(all,key)=>Object.hasOwn(params,key)?String(params[key]):all);
  assert.equal(document.documentElement.lang,locale);assert.equal(ids.import.textContent,tr('importButton'));assert.equal(ids.json.attributes['aria-label'],tr('jsonLabel'));assert.equal(ids.json.attributes.placeholder,tr('jsonPlaceholder'));assert.equal(ids['preview-frame'].attributes.title,tr('previewFrame'));
  const nonce=sent[0].session_nonce,receive=message=>context.window.onmessage({data:{pluginMessage:{...message,session_nonce:nonce}}});
  receive({type:'status',ready:true,source_names:['초대 원본','Source 二'],source_count:3,target_page_name:'팀의 페이지'});
  assert.equal(ids['status-title'].textContent,tr('ready'));assert.equal(ids['preview-source-count'].textContent,tr('previewSource',{count:3}));
  assert.equal(ids['preview-source-names'].children[0].textContent,'초대 원본');assert.match(ids['source-meta'].textContent,/팀의 페이지/);
  ids.fresh.checked=true;ids.fresh.onchange();assert.equal(ids.import.textContent,tr('freshButton'));assert.equal(ids['preview-source-mode'].textContent,tr('previewFresh'));
  ids.import.onclick();assert.equal(ids['status-title'].textContent,tr('progressImportTitle'));assert.equal(sent.at(-1).type,'import');
  receive({type:'status',event:'imported',counts:{screens:3,components:2,variables:9}});receive({type:'busy',value:false});
  assert.equal(ids.status.textContent,tr('importSummary',{screens:3,components:2,variables:9}));
  const next=locale==='ja'?'en':'ja';assert(context.FlowUI.setLocale(next));
  assert.equal(ids['status-title'].textContent,tr('importComplete'));assert.equal(ids.status.textContent,tr('importSummary',{screens:3,components:2,variables:9}));assert.equal(ids.import.textContent,tr('freshButton'));assert.equal(ids['preview-source-names'].children[0].textContent,'초대 원본');
  receive({type:'readback',data:{pages:[{}],variables:[{},{}]}});assert.equal(ids['readback-meta'].textContent,[tr('recentReadback'),tr('pageCount',{count:1}),tr('variableCount',{count:2})].join(' · '));
  receive({type:'status',event:'error',details:'Required native token binding missing: exact-id'});
  assert.equal(ids['status-title'].textContent,tr('errorTitle'));assert.equal(ids.status.textContent,tr('errorBody'));assert.equal(ids['diagnostic-text'].textContent,'Required native token binding missing: exact-id');assert.equal(ids.diagnostics.hidden,false);
  receive({type:'status',ready:true,paired:true,existing_only:true,source_names:['초대 원본'],source_count:1,target_page_name:'팀의 페이지'});
  assert.equal(ids.heading.textContent,tr('syncTitle'));assert.equal(ids['import-preview'].hidden,true);assert.equal(ids.sync.className,'primary');
  ids.sync.onclick();receive({type:'sync-result',result:{status:'applied',changed_tokens:['이름 유지'],screens:['SCR-1'],code_ids:['CODE-1'],files:['원본.css'],report:'실제.md'}});
  assert.equal(ids['status-title'].textContent,tr('applied'));assert.match(ids.status.textContent,/원본\.css/);assert.match(ids.status.textContent,/실제\.md/);
}
""")

    def test_typography_aliases_accept_uniform_arrays_and_ranges_but_reject_mixed(self):
        self.run_node(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={figma:{ui:{},showUI(){}},__html__:''};vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1]+'/figma-bridge/code.js','utf8'),context);
const alias=id=>({type:'VARIABLE_ALIAS',id});
assert.equal(context.textVariableAlias({type:'TEXT',id:'title',characters:'Title',boundVariables:{fontSize:[alias('size'),alias('size')]}},'fontSize').id,'size');
assert.equal(context.textVariableAlias({type:'TEXT',id:'title',characters:'Title',getRangeBoundVariable(){return alias('range');}},'fontSize').id,'range');
assert.throws(()=>context.textVariableAlias({type:'TEXT',id:'title',characters:'Title',boundVariables:{fontSize:[alias('one'),alias('two')]}},'fontSize'),/Mixed native typography binding/);
assert.throws(()=>context.textVariableAlias({type:'TEXT',id:'title',characters:'Title',getRangeBoundVariable(){return Symbol.for('mixed');}},'fontSize'),/Mixed native typography binding/);
""")

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
const ready=messages.find(x=>x.type==='status' && x.ready===true);assert.ok(ready);assert.equal(ready.target_page_name,'Import');assert.equal(ready.source_label,'화면 0개');assert.deepEqual(Array.from(ready.source_names),[]);assert.equal(ready.source_count,0);assert.equal(ready.event,'ready');assert.equal(ready.file_key,undefined);assert.equal(ready.token,undefined);assert.ok(messages.every(x=>x.session_nonce===nonce));
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
await figma.ui.onmessage({type:'export',session_nonce:nonce});const failed=messages.find(x=>x.type==='status' && x.message==='Error: readback failed');assert.ok(failed);assert.equal(failed.event,'error');assert.equal(failed.operation,'export');assert.match(failed.details,/readback failed/);
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
const copy=JSON.parse(fs.readFileSync(process.argv[1]+'/figma-bridge/locales/import.json','utf8'));
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
  const context={figma,__html__:'',FLOW_IMPORT_COPY:{reused:copy['import.reused'].ko,syncWait:copy['import.syncWait'].ko},PAYLOAD:{source_sha256:digest,screens:[],technical_existing_only:paired},async fetch(url,options){requests.push({url,options});if(pending)await pending;if(reply instanceof Error)throw reply;return {ok,status:ok?200:409,async json(){return reply;}};}};
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
