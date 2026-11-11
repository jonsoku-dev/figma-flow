const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{execFileSync}=require('node:child_process');
const source=fs.readFileSync(path.join(__dirname,'../figma-bridge/native_edit.js'),'utf8');
const planSchema=JSON.parse(execFileSync('python3.13',['-B','-c','import json,sys; sys.path.insert(0, sys.argv[1]); from native_edit import PLAN_SCHEMA; sys.stdout.write(json.dumps(PLAN_SCHEMA))',path.join(__dirname,'../tools')],{encoding:'utf8'}));
const clone=value=>JSON.parse(JSON.stringify(value));
const plan=edits=>({schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',edits:edits||[{node_id:'2:1',field:'paddingLeft',before:16,after:24}]});
function world(extra={}){
 const state={loads:[],messages:[],used:true,onLoad:null,onRead:null};
 const page={id:'1:1',type:'PAGE',getPluginData:()=>''};
 const main={id:'2:1',type:'COMPONENT',parent:page,paddingLeft:16,paddingRight:16,cornerRadius:6,topLeftRadius:6,topRightRadius:6,bottomLeftRadius:6,bottomRightRadius:6,boundVariables:{},fills:[{type:'SOLID',color:{r:0,g:0,b:0},opacity:1}],setBoundVariable(key,variable){if(variable)this.boundVariables[key]={type:'VARIABLE_ALIAS',id:variable.id};else delete this.boundVariables[key];}};
 const text={id:'3:1',type:'TEXT',parent:main,characters:'Actual native text',fontName:{family:'Inter',style:'Regular'},fontSize:14,textStyleId:'',bindings:{fontSize:{type:'VARIABLE_ALIAS',id:'variable'}},getRangeAllFontNames(){return[this.fontName];},getRangeBoundVariable(a,b,key){return state.used?this.bindings[key]||null:null;},setRangeBoundVariable(a,b,key,variable){if(variable)this.bindings[key]={type:'VARIABLE_ALIAS',id:variable.id};else delete this.bindings[key];}};
 const instance={id:'4:1',type:'INSTANCE',parent:page},instanceText={...text,id:'5:1',parent:instance};
 const objects=new Map([page,main,text,instance,instanceText].map(node=>[node.id,node]));page.findAll=()=>[main,text];
 const collection={id:'collection',modes:[{modeId:'mode'}],getPluginData:()=>''};
 const variable={id:'variable',variableCollectionId:'collection',resolvedType:'FLOAT',valuesByMode:{mode:14},setValueForMode(mode,value){this.valuesByMode[mode]=value;}};
 const variableMap=new Map([[variable.id,variable]]);
 const figma={fileKey:'file',currentPage:page,ui:{postMessage(message){state.messages.push(message);}},showUI(){},async getNodeByIdAsync(id){return objects.get(id);},variables:{async getVariableByIdAsync(id){return variableMap.get(id)||null;},async getVariableCollectionByIdAsync(){return collection;}},async listAvailableFontsAsync(){return[{fontName:{family:'Inter',style:'Regular'}},{fontName:{family:'Other',style:'Regular'}}];},async loadFontAsync(font){state.loads.push(font);await state.onLoad?.();}};
 const readNativeSemantics=async()=>{await state.onRead?.();return{nodes:[{id:page.id,type:'PAGE'},{id:main.id,type:'COMPONENT',paddingLeft:main.paddingLeft,paddingRight:main.paddingRight,fills:clone(main.fills)},{id:text.id,type:'TEXT',fontSize:text.fontSize,fontName:clone(text.fontName),boundVariables:clone(text.bindings)}],variables:[...variableMap.values()].map(clone),collections:[{id:'collection'}]};};
 const context=vm.createContext({figma,readNativeSemantics,NATIVE_EDIT_SHA256:'pinned-plan',NATIVE_EDIT_PLAN_SCHEMA:planSchema,...extra});vm.runInContext(source,context);
 return{state,page,main,text,instance,instanceText,variable,variableMap,figma,context,run:(data,operation)=>context.runNativeEdit(figma,data,operation)};
}
test('actual getters change only declared main padding and discovery remains a normal native readback',async()=>{
 const h=world();const result=await h.run(plan());assert.equal(h.main.paddingLeft,24);assert.equal(h.main.paddingRight,16);assert.equal(result.schema,'figma-flow-graph-native-discovery-v1');assert.equal(result.nodes.find(n=>n.id==='2:1').paddingLeft,24);assert.equal(result.native_edit.applied,true);assert.deepEqual(Array.from(result.allowed_page_ids),['1:1']);
 const read=await h.run(plan(),'read');assert.equal(read.native_edit.applied,false);assert.equal(read.nodes.find(n=>n.id==='2:1').paddingLeft,24);
 await assert.rejects(()=>h.run(plan()),/before-value drift/);
});
test('wrong file, page, before value and instance targets are rejected before any writes',async()=>{
 for(const alter of [h=>h.figma.fileKey='wrong',h=>h.figma.currentPage={id:'9:9'},h=>h.main.paddingLeft=17]){const h=world();alter(h);const before=h.main.paddingLeft;await assert.rejects(()=>h.run(plan()));assert.equal(h.main.paddingLeft,before);}
 const h=world();await assert.rejects(()=>h.run(plan([{node_id:'5:1',main_id:'2:1',field:'fontSize',before:14,after:18}])) ,/instance overrides/);assert.equal(h.text.fontSize,14);
});
test('font edits await exact existing fonts and reject drift introduced during any await',async()=>{
 const h=world();await h.run(plan([{node_id:'3:1',main_id:'2:1',field:'fontFamily',before:'Inter',after:'Other'}]));assert.equal(h.text.fontName.family,'Other');assert(h.state.loads.some(font=>font.family==='Other'));
 const stale=world();stale.state.onLoad=()=>{stale.main.paddingLeft=99;};await assert.rejects(()=>stale.run(plan([{node_id:'3:1',main_id:'2:1',field:'fontSize',before:14,after:18},{node_id:'2:1',field:'paddingLeft',before:16,after:24}])));assert.equal(stale.text.fontSize,14);assert.equal(stale.main.paddingLeft,99);
 const page=world();page.state.onLoad=()=>{page.figma.currentPage={id:'9:9'};};await assert.rejects(()=>page.run(plan([{node_id:'3:1',main_id:'2:1',field:'fontSize',before:14,after:18}])));assert.equal(page.text.fontSize,14);
 const missing=world();await assert.rejects(()=>missing.run(plan([{node_id:'3:1',main_id:'2:1',field:'fontFamily',before:'Inter',after:'Missing'}])),/font unavailable/);assert.equal(missing.text.fontName.family,'Inter');
});
test('partial setter failure restores exact old values and bound typography',async()=>{
 const h=world();h.text.bindings.fontSize={type:'VARIABLE_ALIAS',id:'variable'};let right=16,fail=true;
 Object.defineProperty(h.main,'paddingRight',{get(){return right;},set(value){if(value===24&&fail){fail=false;throw Error('setter failure');}right=value;}});
 await assert.rejects(()=>h.run(plan([{node_id:'3:1',main_id:'2:1',field:'fontSize',before:14,after:18},{node_id:'2:1',field:'paddingRight',before:16,after:24}])),error=>{assert.equal(error.readback.status,'rolled-back');return true;});
 assert.equal(h.text.fontSize,14);assert.equal(h.text.bindings.fontSize.id,'variable');assert.equal(h.main.paddingRight,16);
});
test('external drift during receipt discovery is preserved and reported as rollback conflict',async()=>{
 const h=world();h.state.onRead=()=>{h.main.paddingLeft=99;};await assert.rejects(()=>h.run(plan()),error=>{assert.equal(error.readback.status,'rollback-conflict');assert(error.rollback_conflicts.length);return true;});assert.equal(h.main.paddingLeft,99);
});
test('only an existing admitted page variable and exact mode can be changed',async()=>{
 const data={schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',variableedit:{variable_id:'variable',mode_id:'mode',before:14,after:18}};
 const h=world(),result=await h.run(data);assert.equal(h.variable.valuesByMode.mode,18);assert.equal(result.variables[0].valuesByMode.mode,18);
 const missing=world();missing.state.used=false;await assert.rejects(()=>missing.run(data),/not used/);assert.equal(missing.variable.valuesByMode.mode,14);
 const mode=world();await assert.rejects(()=>mode.run({...data,variableedit:{...data.variableedit,mode_id:'other'}}),/existing local variable/i);assert.equal(mode.variable.valuesByMode.mode,14);
});
test('runtime nonce and busy guards reject wrong sessions and duplicate apply',async()=>{
 const h=world({NATIVE_EDIT_PLAN:plan(),NATIVE_EDIT_SESSION:'nonce',__html__:'UI'});
 await h.figma.ui.onmessage({type:'apply',session:'wrong'});assert.equal(h.main.paddingLeft,16);
 const pending=h.figma.ui.onmessage({type:'apply',session:'nonce'});await h.figma.ui.onmessage({type:'apply',session:'nonce'});await pending;
 assert.equal(h.main.paddingLeft,24);assert.equal(h.state.messages.filter(m=>m.readback?.native_edit?.applied).length,1);
});

test('font rollback restores an existing linked style and rejects changes during that await',async()=>{
 for(const drift of [false,true]){
  const h=world(),style={id:'style',type:'TEXT',fontName:{family:'Inter',style:'Regular'},fontSize:14,boundVariables:{}};
  h.text.textStyleId='style';h.figma.getStyleByIdAsync=async()=>style;
  let size=14;Object.defineProperty(h.text,'fontSize',{get(){return size;},set(value){size=value;if(value===18)h.text.textStyleId='';}});
  h.text.setTextStyleIdAsync=async id=>{h.text.textStyleId=id;size=drift?99:style.fontSize;};
  let fail=true,right=16;Object.defineProperty(h.main,'paddingRight',{get(){return right;},set(value){if(value===24&&fail){fail=false;throw Error('second setter failed');}right=value;}});
  await assert.rejects(()=>h.run(plan([{node_id:'3:1',main_id:'2:1',field:'fontSize',before:14,after:18},{node_id:'2:1',field:'paddingRight',before:16,after:24}])),error=>{assert.equal(error.readback.status,drift?'rollback-conflict':'rolled-back');return true;});
  assert.equal(h.text.fontSize,drift?99:14);assert.equal(h.text.textStyleId,'style');
 }
});

test('opaque RGB values compare with actual getter RGBA without widening paint scope',async()=>{
 const h=world();h.main.fills=[{type:'SOLID',color:{r:0,g:0,b:0},opacity:1,blendMode:'NORMAL',boundVariables:{color:{type:'VARIABLE_ALIAS',id:'variable'}}}];
 const result=await h.run(plan([{node_id:'2:1',field:'backgroundColor',before:{r:0,g:0,b:0},after:{r:1,g:0.5,b:0}}]));
 assert.equal(h.main.fills[0].color.r,1);assert.equal(h.main.fills[0].blendMode,'NORMAL');assert.equal(h.main.fills[0].boundVariables,undefined);
 assert.equal(result.nodes.find(n=>n.id==='2:1').fills[0].color.r,1);assert.equal(result.native_edit.operations[0].before_observed.a,1);assert.equal(h.variable.valuesByMode.mode,14);
});

test('uniform corner radius supports the existing whole-radius variable binding',async()=>{
 const h=world();h.variable.valuesByMode.mode=6;h.main.boundVariables.cornerRadius={type:'VARIABLE_ALIAS',id:'variable'};
 let radius=6;Object.defineProperty(h.main,'cornerRadius',{get(){return radius;},set(value){radius=value;for(const key of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])h.main[key]=value;}});
 await h.run(plan([{node_id:'2:1',field:'borderRadius',before:6,after:10}]));
 assert.equal(h.main.cornerRadius,10);assert.equal(h.main.boundVariables.cornerRadius,undefined);assert.equal(h.variable.valuesByMode.mode,6);
});

test('a collection member used only on another page is not an admitted variable edit',async()=>{
 const h=world();let writes=0;
 const unrelated={id:'unrelated',variableCollectionId:'collection',resolvedType:'FLOAT',valuesByMode:{mode:9},setValueForMode(mode,value){writes++;this.valuesByMode[mode]=value;}};
 h.variableMap.set(unrelated.id,unrelated);
 const otherPage={id:'9:1',type:'PAGE'},otherNode={id:'9:2',parent:otherPage,type:'FRAME',boundVariables:{paddingLeft:{type:'VARIABLE_ALIAS',id:unrelated.id}}};
 otherPage.findAll=()=>[otherNode];
 h.page.getPluginData=key=>key==='graphSSOT'?JSON.stringify({owned_variable_ids:[unrelated.id]}):'';
 const data={schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',variableedit:{variable_id:unrelated.id,mode_id:'mode',before:9,after:12}};
 const discovery=await h.run(data,'read');assert(discovery.variables.some(variable=>variable.id===unrelated.id));
 await assert.rejects(()=>h.run(data),/not used by an actual binding on the admitted page/);
 assert.equal(writes,0);assert.equal(unrelated.valuesByMode.mode,9);assert.equal(h.variable.valuesByMode.mode,14);
});

test('an actually bound alias admits its existing scalar root without collection-wide adoption',async()=>{
 const h=world();h.variableMap.set('size-alias',{id:'size-alias',variableCollectionId:'collection',resolvedType:'FLOAT',valuesByMode:{mode:{type:'VARIABLE_ALIAS',id:'variable'}}});
 h.text.bindings.fontSize={type:'VARIABLE_ALIAS',id:'size-alias'};
 const data={schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',variableedit:{variable_id:'variable',mode_id:'mode',before:14,after:18}};
 await h.run(data);assert.equal(h.variable.valuesByMode.mode,18);
 assert.equal(h.variableMap.get('size-alias').valuesByMode.mode.id,'variable');
});

test('page binding removed during variable mode preflight is rejected before mutation',async()=>{
 const h=world(),get=h.figma.variables.getVariableCollectionByIdAsync;let reads=0;
 h.figma.variables.getVariableCollectionByIdAsync=async id=>{const result=await get(id);if(++reads===2)delete h.text.bindings.fontSize;return result;};
 const data={schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',variableedit:{variable_id:'variable',mode_id:'mode',before:14,after:18}};
 await assert.rejects(()=>h.run(data),/not used by an actual binding/);assert.equal(h.variable.valuesByMode.mode,14);
});

for(const style of ['shared-style',Symbol.for('mixed')])test(`paint style ${String(style)} is rejected before any fill assignment`,async()=>{
 for(const text of [false,true]){
  const h=world(),node=text?h.text:h.main;
  let fills=[{type:'SOLID',color:{r:0,g:0,b:0},opacity:1}],writes=0;
  Object.defineProperty(node,'fills',{get(){return fills;},set(value){writes++;fills=value;}});node.fillStyleId=style;
  const edit={node_id:node.id,field:text?'color':'backgroundColor',before:{r:0,g:0,b:0},after:{r:1,g:1,b:1}};
  if(text)edit.main_id=h.main.id;
  await assert.rejects(()=>h.run(plan([edit])),/Style-backed or mixed native fill cannot be edited/);
  assert.equal(writes,0);assert.equal(node.fillStyleId,style);assert.deepEqual(fills[0].color,{r:0,g:0,b:0});
 }
});

test('a paint style added during another target font await is not detached',async()=>{
 const h=world();h.main.fillStyleId='';h.state.onLoad=()=>{h.main.fillStyleId='new-external-style';};
 await assert.rejects(()=>h.run(plan([{node_id:h.main.id,field:'backgroundColor',before:{r:0,g:0,b:0},after:{r:1,g:1,b:1}},{node_id:h.text.id,main_id:h.main.id,field:'fontSize',before:14,after:18}])),/Style-backed or mixed native fill/);
 assert.equal(h.main.fillStyleId,'new-external-style');assert.deepEqual(h.main.fills[0].color,{r:0,g:0,b:0});assert.equal(h.text.fontSize,14);
});
