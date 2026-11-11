const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),{execFileSync}=require('node:child_process'),path=require('node:path');
const prelude=execFileSync('python3.13',['-B','-c','import sys; sys.path.insert(0, sys.argv[1]); from specification_contract import spec_label_prelude; from native_edit import PLAN_SCHEMA; sys.stdout.write(spec_label_prelude()+"var NATIVE_EDIT_PLAN_SCHEMA = "+__import__("json").dumps(PLAN_SCHEMA)+";\\n")',path.join(__dirname,'../tools')],{encoding:'utf8'});
const source=prelude+['native_semantic_read.js','native_annotations.js','design_note_board.js','native_specifications.js','native_edit.js'].map(name=>fs.readFileSync(__dirname+'/../figma-bridge/'+name,'utf8')).join('\n');
const clone=value=>JSON.parse(JSON.stringify(value));
let sequence=0;
class Node {
 constructor(type){Object.assign(this,{id:`${++sequence}:1`,type,name:type,children:[],data:{},annotations:[],x:0,y:0,width:100,height:20,visible:true,fontSize:17,fontName:{family:'Explicit',style:'Regular'},characters:'',textStyleId:'',boundVariables:{}});}
 appendChild(node){node.parent=this;this.children.push(node);}
 getPluginData(key){return this.data[key]||'';}
 setPluginData(key,value){if(this.failData){this.failData=false;this.annotations.push({label:'concurrent user'});throw Error('injected metadata setter');}this.data[key]=value;}
 async loadAsync(){}
 findAll(test){return this.children.flatMap(n=>[...(test(n)?[n]:[]),...n.findAll(test)]);}
 resize(width,height){this.width=width;this.height=height;}
 setRangeHyperlink(a,b,link){this.link=link;}
 getRangeHyperlink(){return this.link||null;}
 getRangeAllFontNames(){return[this.fontName];}
 getRangeBoundVariable(){return null;}
 remove(){this.parent.children=this.parent.children.filter(n=>n!==this);this.removed=true;}
}
const specification=(text='원래 동작')=>({schema:'figma-flow-readable-spec-v1',id:'note',kind:'control',screen_id:'screen',target_id:'deliver',title:'배달',meaning:{purpose:text},meaning_sha256:(text==='원래 동작'?'a':'c').repeat(64),source_graph_sha256:'b'.repeat(64),source_graph_encoding:'file-bytes-sha256',display_text:text,trace:{status:'unverified'}});
async function setup(){
 sequence=0;const page=new Node('PAGE'),target=new Node('FRAME'),other=new Node('FRAME');page.appendChild(target);page.appendChild(other);target.setPluginData('semanticKey','full.deliver');other.setPluginData('semanticKey','full.other');other.x=200;
 const figma={fileKey:'file',currentPage:page,createFrame:()=>new Node('FRAME'),createText:()=>new Node('TEXT'),loadFontAsync:async()=>{},getNodeByIdAsync:async id=>[page,...page.findAll(()=>true)].find(n=>n.id===id),variables:{getLocalVariableCollectionsAsync:async()=>[]}};
 const context=vm.createContext({NATIVE_EDIT_SHA256:'prepared-pin'});vm.runInContext(source,context);
 const boardResult=await context.ensureDesignNoteBoard(figma,page,{sourceHash:'d'.repeat(64),font:target.fontName,notes:[{key:'viewport|state|control',targetId:target.id,label:'Legacy readable explanation'},{key:'viewport|state|other',targetId:other.id,label:'Keep other text'}]});
 const board=page.findAll(n=>n.id===boardResult.boardId)[0];target.annotations=[{label:'user note'},{label:'[figma-flow:full.deliver] legacy original',labelMarkdown:'**original**'}];
 const entries=board.children.map(n=>({key:n.getPluginData('semanticKey'),textNodeId:n.id,characters:n.characters,hyperlink:n.getRangeHyperlink()}));
 const plan={schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:page.id,specifications:{source_graph:{path:'/fixture-only/graph.json',sha256:'b'.repeat(64)},board:{key:'design-note-board',node_id:board.id,owner:{pageId:page.id,sourceHash:'d'.repeat(64)},font:clone(target.fontName),entries},targets:[{node_id:target.id,semantic_key:'full.deliver',before:{specification:null,annotations:clone(target.annotations)},after:specification('갱신된 동작'),legacy_annotations:[{index:1,annotation:clone(target.annotations[1])}],legacy_proof:null}]}};
 return {page,target,other,figma,context,board,plan,run:()=>context.runNativeEdit(figma,plan)};
}
test('legacy migration and graph behavior update preserve IDs, other text, user annotations; repeat is noop',async()=>{
 const e=await setup(),ids=e.board.children.map(n=>n.id),other=e.board.children[2].characters;
 const result=await e.run();assert.equal(result.native_edit.applied,true);assert.equal(result.schema,'figma-flow-graph-native-discovery-v1');
 assert.deepEqual(e.board.children.map(n=>n.id),ids);assert.equal(e.board.children[2].characters,other);assert.deepEqual(clone(e.target.annotations),[{label:'user note'}]);
 const getter=result.nodes.find(n=>n.id===e.target.id);assert.equal(getter.specification.specification.display_text,'갱신된 동작');assert.equal(getter.specification.legacy_annotations[0].annotation.labelMarkdown,'**original**');
 assert.equal((await e.run()).native_edit.changed,0);
 const before=clone(e.plan);before.specifications.targets[0].before={specification:clone(getter.specification),annotations:clone(e.target.annotations)};before.specifications.board.entries=e.board.children.map(n=>({key:n.getPluginData('semanticKey'),textNodeId:n.id,characters:n.characters,hyperlink:n.getRangeHyperlink()}));before.specifications.targets[0].legacy_annotations=[];before.specifications.targets[0].legacy_proof=null;before.specifications.targets[0].after=specification('두 번째 동작');
 await e.context.runNativeEdit(e.figma,before);assert.equal(e.board.children[1].characters,'배달\n두 번째 동작');assert.deepEqual(e.board.children.map(n=>n.id),ids);
});
test('connected specification writes a two-way linked owned human annotation and verifies its getter snapshot',async()=>{
 const e=await setup(),row=e.plan.specifications.targets[0];row.after={...row.after,presentation:'connected-spec-v2',locale:'ja',sections:[{key:'purpose',title:'目的',body:'配達先を選びます。'}],annotation_text:'配達先を選ぶと確認へ進めます。'};
 row.legacy_annotations=[];row.before.annotations=[{label:'preserve this user note'}];e.target.annotations=clone(row.before.annotations);
 let result=await e.run();assert.equal(result.native_edit.applied,true);assert.deepEqual(clone(e.target.annotations.slice(0,1)),[{label:'preserve this user note'}]);
 const wrapper=JSON.parse(e.target.getPluginData('figmaFlowSpecification')),human=wrapper.human_annotation,text=e.board.children[1];
 assert.equal(human.schema,'figma-flow-human-annotation-v1');assert.equal(human.annotation.labelMarkdown.includes(human.url),true);assert.equal(human.board.textNodeId,text.id);assert.equal(text.getRangeHyperlink().value,e.target.id);
 assert.match(human.annotation.labelMarkdown,/仕様の詳細を見る/);assert.equal((await e.run()).native_edit.changed,0);
 const plan=clone(e.plan);plan.specifications.targets[0].before={specification:wrapper,annotations:clone(e.target.annotations)};plan.specifications.targets[0].legacy_annotations=[];plan.specifications.targets[0].after=clone(wrapper.specification);plan.specifications.board.entries=e.board.children.map(n=>({key:n.getPluginData('semanticKey'),textNodeId:n.id,characters:n.characters,hyperlink:n.getRangeHyperlink()}));
 assert.equal((await e.context.runNativeEdit(e.figma,plan)).native_edit.changed,0);
});
test('wrong binding, owner, user board children, duplicate and changed snapshots conflict before mutation',async()=>{
 for(const mutate of [e=>e.target.setPluginData('semanticKey','wrong'),e=>e.board.setPluginData('designNoteBoard','{}'),e=>e.board.children[1].link={type:'NODE',value:'foreign'},e=>e.board.appendChild(new Node('TEXT')),e=>e.target.annotations[1].label+='edited',e=>{const n=new Node('FRAME');n.setPluginData('semanticKey','full.deliver');e.page.appendChild(n);}]){
  const e=await setup();mutate(e);const text=e.board.children[1].characters;await assert.rejects(e.run);assert.equal(e.target.getPluginData('figmaFlowSpecification'),'');assert.equal(e.board.children[1].characters,text);
 }
});
test('font await drift and mixed partial states reject overwrite',async()=>{
 const e=await setup();e.figma.loadFontAsync=async()=>{e.target.annotations.push({label:'during await'});};await assert.rejects(e.run,/conflict/);assert.equal(e.target.annotations.at(-1).label,'during await');
 const p=await setup();p.board.children[1].characters='배달\n갱신된 동작';await assert.rejects(p.run,/partial|conflict/);assert.equal(p.target.getPluginData('figmaFlowSpecification'),'');
});
test('injected metadata setter failure rolls board back and preserves concurrent user annotation',async()=>{
 const e=await setup(),before=e.board.children[1].characters;e.target.failData=true;
 await assert.rejects(e.run,error=>{assert.match(error.message,/injected/);assert.equal(error.readback.native_edit.applied,false);return true;});
 assert.equal(e.board.children[1].characters,before);assert.equal(e.target.getPluginData('figmaFlowSpecification'),'');assert.equal(e.target.annotations.at(-1).label,'concurrent user');assert.equal(e.target.annotations[1].label,'[figma-flow:full.deliver] legacy original');
});
test('annotation helper await cannot admit a new user state as the durable before state',async()=>{
 const e=await setup(),before=e.board.children[1].characters;let loads=0,writes=0;const setter=e.target.setPluginData.bind(e.target);e.target.setPluginData=(key,value)=>{if(key==='figmaFlowSpecification')writes++;setter(key,value);};
 e.page.loadAsync=async()=>{if(++loads===2)e.target.annotations.push({label:'during annotation await'});};
 await assert.rejects(e.run,/await|conflict|drift/);
 assert.equal(e.board.children[1].characters,before);assert.equal(e.target.getPluginData('figmaFlowSpecification'),'');assert.equal(e.target.annotations.at(-1).label,'during annotation await');assert.equal(writes,0,'no target metadata mutation admitted after concurrent await change');
});
test('exact unprefixed import annotation migrates only with native metadata and source proof',async()=>{
 const e=await setup(),slot={index:1,annotation:{label:'Legacy readable explanation',labelMarkdown:'**original**'}};
 const legacyBody=`FRAME · viewport|state|control\n${slot.annotation.label}\n화면·조작으로 이동`;
 e.board.children[1].characters=legacyBody;e.plan.specifications.board.entries[1].characters=legacyBody;e.target.annotations=[{label:'keep this user note'},clone(slot.annotation)];
 e.target.setPluginData('figmaFlow',JSON.stringify({annotation_mode:'native',semantic_id:'full.deliver'}));e.page.setPluginData('figmaFlow',JSON.stringify({source_sha256:'d'.repeat(64)}));
 e.plan.specifications.targets[0].before.annotations=clone(e.target.annotations);e.plan.specifications.targets[0].legacy_annotations=[slot];e.plan.specifications.targets[0].legacy_proof={annotation_mode:'native',semantic_id:'full.deliver',page_source_sha256:'d'.repeat(64),target_name:'FRAME',legacy_body:legacyBody};
 const result=await e.run();assert.equal(result.native_edit.applied,true);assert.deepEqual(clone(e.target.annotations),[{label:'keep this user note'}]);
 const unsafe=await setup();unsafe.board.children[1].characters=legacyBody;unsafe.plan.specifications.board.entries[1].characters=legacyBody;unsafe.target.annotations=[{label:'Legacy'}];unsafe.plan.specifications.targets[0].before.annotations=clone(unsafe.target.annotations);unsafe.plan.specifications.targets[0].legacy_annotations=[{index:0,annotation:clone(unsafe.target.annotations[0])}];
 await assert.rejects(unsafe.run,/ownership|display/);assert.deepEqual(clone(unsafe.target.annotations),[{label:'Legacy'}]);
});
test('concurrent edit during independent getter discovery is preserved as a rollback conflict',async()=>{
 const e=await setup(),getter=e.figma.getNodeByIdAsync;e.figma.getNodeByIdAsync=async id=>{e.board.children[1].characters='concurrent human edit';return getter(id);};
 await assert.rejects(e.run,error=>{assert(error.rollback_conflicts.length);assert.equal(error.readback.native_edit.applied,false);return true;});
 assert.equal(e.board.children[1].characters,'concurrent human edit');
});
