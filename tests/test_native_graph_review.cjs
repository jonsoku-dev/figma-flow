const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const reviewSource=fs.readFileSync(path.join(__dirname,'../figma-bridge/native_graph_review.js'),'utf8');
const editSource=fs.readFileSync(path.join(__dirname,'../figma-bridge/native_edit.js'),'utf8');

class SceneNode {
  constructor(type,state){this.type=type;this.state=state;this.id=String(++state.nextId)+':1';this.name=type;this.x=0;this.y=0;this.width=0;this.height=0;this.children=[];this.parent=null;this.pluginData={};this.visible=true;this.removed=false;}
  resize(width,height){this.width=width;this.height=height;}
  appendChild(child){this.state.appendCount++;if(this.state.failAt===this.state.appendCount)throw Error('injected append failure');if(child.parent){const at=child.parent.children.indexOf(child);if(at>=0)child.parent.children.splice(at,1);}child.parent=this;this.children.push(child);}
  remove(){if(this.parent){const at=this.parent.children.indexOf(this);if(at>=0)this.parent.children.splice(at,1);}this.parent=null;this.removed=true;}
  setPluginData(key,value){this.pluginData[key]=value;}
  getPluginData(key){return this.pluginData[key]||'';}
  findAll(predicate){const result=[];const visit=node=>{for(const child of node.children){if(predicate(child))result.push(child);visit(child);}};visit(this);return result;}
}

function graphPlan(title='Review graph',source='a'.repeat(64)){
  return {schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',graph_review:{source_graph_sha256:source,projection:{id:'sample.graph',title,nodes:[
    {id:'REQ-1',kind:'requirement',type:'requirement',title:'Page shows product facts',detail:'Measured from local source',status:'observed'},
    {id:'SCR-1',kind:'screen',type:'screen',title:'Main page',detail:'SSR title and body',status:'verified'},
    {id:'CMP-1',kind:'component',type:'component',title:'Hero action',detail:'Visible primary action',status:'observed'},
    {id:'EVD-1',kind:'evidence',type:'reference',title:'HTTP capture',detail:'sha256 exact body',status:'verified'},
  ],edges:[{from:'REQ-1',to:'SCR-1',type:'appears on'},{from:'SCR-1',to:'CMP-1',type:'contains'},{from:'CMP-1',to:'EVD-1',type:'supported by'}]}}};
}

function world(){
  const state={nextId:0,appendCount:0,failAt:0,loaded:[],onLoad:null};
  const page=new SceneNode('PAGE',state);page.id='1:1';page.findAll=SceneNode.prototype.findAll;page.getPluginData=SceneNode.prototype.getPluginData;
  const frame=()=>new SceneNode('FRAME',state),component=()=>{
    const main=new SceneNode('COMPONENT',state);
    main.createInstance=()=>{const instance=new SceneNode('INSTANCE',state);for(const child of main.children){const copy=new SceneNode(child.type,state);copy.name=child.name;copy.characters=child.characters;copy.fontName=child.fontName;copy.fontSize=child.fontSize;copy.fills=child.fills;copy.resize(child.width,child.height);instance.appendChild(copy);}return instance;};
    return main;
  };
  const figma={fileKey:'file',currentPage:page,viewport:{center:{x:600,y:400},scrollAndZoomIntoView(){}},showUI(){},ui:{postMessage(){}},createFrame:frame,createComponent:component,createText:()=>new SceneNode('TEXT',state),async listAvailableFontsAsync(){return[{fontName:{family:'Inter',style:'Regular'}}];},async loadFontAsync(font){state.loaded.push(font);await state.onLoad?.();},async getNodeByIdAsync(id){return id==='1:1'?page:null;},variables:{async getVariableByIdAsync(){return null;},async getVariableCollectionByIdAsync(){return null;}}};
  const context=vm.createContext({figma,NATIVE_EDIT_PLAN_SCHEMA:'figma-flow-native-edit-plan-v1',NATIVE_EDIT_SHA256:'c'.repeat(64),readNativeSemantics:async p=>({nodes:[],variables:[],collections:[],fileKey:figma.fileKey,pageId:p.id}),requireFullNativeRead:value=>value});
  vm.runInContext(reviewSource,context);vm.runInContext(editSource,context);
  return {figma,page,state,context,run:(plan,operation='apply')=>context.runNativeEdit(figma,plan,operation)};
}

test('normal native-edit operations return real discovery contract with a reusable grouped board',async()=>{
  const h=world(),plan=graphPlan();
  const first=await h.run(plan,'apply');
  assert.equal(first.schema,'figma-flow-graph-native-discovery-v1');assert.equal(first.native_edit.applied,true);assert.equal(first.native_edit.operation,'apply');
  assert.equal(first.graph_review.status,'created');assert.equal(first.graph_review.node_count,4);assert.equal(first.graph_review.edge_count,3);
  const board=h.page.children.find(node=>node.getPluginData('figmaFlow.graphReview.owner'));
  assert.ok(board);assert.equal(board.findAll(node=>node.type==='COMPONENT').length,4);assert.equal(board.findAll(node=>node.type==='INSTANCE'&&node.getPluginData('figmaFlow.graphReview.nodeId')).length,4);
  assert.equal(board.findAll(node=>node.getPluginData('figmaFlow.graphReview.edge')).length,3);
  const read=await h.run(plan,'read');assert.equal(read.schema,'figma-flow-graph-native-discovery-v1');assert.equal(read.native_edit.applied,false);assert.equal(read.graph_review.status,'current');
  const second=await h.run(plan,'apply');assert.equal(second.graph_review.unchanged,true);assert.equal(h.page.children.filter(node=>node.getPluginData('figmaFlow.graphReview.owner')).length,1);
});

test('changed source is compared and atomically refreshes only its owned board',async()=>{
  const h=world(),first=await h.run(graphPlan(),'apply'),oldId=first.graph_review.board_id;
  const updated=await h.run(graphPlan('Updated review graph','b'.repeat(64)),'apply');
  assert.equal(updated.graph_review.status,'created');assert.notEqual(updated.graph_review.board_id,oldId);
  const boards=h.page.children.filter(node=>node.getPluginData('figmaFlow.graphReview.owner'));
  assert.equal(boards.length,1);assert.equal(boards[0].getPluginData('figmaFlow.graphReview.sourceSha256'),'b'.repeat(64));
});

test('failed replacement removes staged nodes and preserves the prior board',async()=>{
  const h=world(),first=await h.run(graphPlan(),'apply'),oldId=first.graph_review.board_id;
  h.state.appendCount=0;h.state.failAt=9;
  await assert.rejects(()=>h.run(graphPlan('Changed graph','b'.repeat(64)),'apply'),error=>{
    assert.equal(error.readback.schema,'figma-flow-graph-review-v1');assert.equal(error.readback.status,'rolled-back');return true;
  });
  const boards=h.page.children.filter(node=>node.getPluginData('figmaFlow.graphReview.owner'));
  assert.equal(boards.length,1);assert.equal(boards[0].id,oldId);
});

test('wrong page, duplicate ownership and edited boards stop before replacement',async()=>{
  const wrong=world();wrong.figma.currentPage={id:'9:9',children:[]};await assert.rejects(()=>wrong.run(graphPlan(),'apply'),/Wrong native edit file or page/);
  const h=world();await h.run(graphPlan(),'apply');const board=h.page.children[0];board.setPluginData('figmaFlow.graphReview.nodeIds','[]');
  await assert.rejects(()=>h.run(graphPlan('New source','b'.repeat(64)),'apply'),/content changed/);assert.equal(h.page.children.length,1);
  const duplicate=new SceneNode('FRAME',h.state);duplicate.setPluginData('figmaFlow.graphReview.owner','figma-flow-graph-review-v1');duplicate.setPluginData('figmaFlow.graphReview.id','sample.graph');h.page.appendChild(duplicate);
  await assert.rejects(()=>h.run(graphPlan(),'apply'),/Multiple owned graph review boards/);
});

test('manual canvas edits are detected by current reads and never deleted by refresh',async()=>{
  const h=world(),first=await h.run(graphPlan(),'apply'),board=h.page.children[0];
  const title=board.findAll(node=>node.type==='TEXT').find(node=>node.name==='Board title');
  title.characters='Human-edited title';
  assert.equal((await h.run(graphPlan(),'read')).graph_review.status,'integrity-conflict');
  await assert.rejects(()=>h.run(graphPlan('New source','b'.repeat(64)),'apply'),/content changed/);
  assert.equal(h.page.children.length,1);assert.equal(h.page.children[0].id,first.graph_review.board_id);assert.equal(title.characters,'Human-edited title');
});

test('a page switch during async font preflight leaves the selected page untouched',async()=>{
  const h=world();h.state.onLoad=()=>{h.figma.currentPage={id:'9:9',children:[]};};
  await assert.rejects(()=>h.run(graphPlan(),'apply'),/Wrong native graph review file or page/);
  assert.equal(h.page.children.length,0);
});
