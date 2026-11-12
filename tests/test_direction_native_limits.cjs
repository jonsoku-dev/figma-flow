/* API-shaped storage regressions; the live importer trial remains separate evidence. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const runtime = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
function host() {
  const measurementFrames = [];
  const context = vm.createContext({DRAFT:{}, __html__:'', figma:{showUI(){},ui:{postMessage(){}},
    createFrame(){const frame={children:[],appendChild(node){this.children.push(node);node.parent=this;},remove(){this.removed=true;this.children=[];}};measurementFrames.push(frame);return frame;},
    async getStyleByIdAsync(id){return {id,name:id,fontName:{family:'Inter',style:'Regular'},fontSize:17,lineHeight:{unit:'PIXELS',value:24}};}}});
  vm.runInContext(runtime, context);
  const data = new Map(), writes = [];
  const page = {id:'page',async loadAsync(){},findAll:()=>[],flowStartingPoints:[],getPluginData:key=>data.get(key)||'',setPluginData(key,value){
    const bytes=Buffer.byteLength(key+value,'utf8');
    assert(bytes<=100000,`Figma plugin-data entry exceeds 100 kB: ${key} (${bytes})`);
    writes.push({key,bytes});if(value)data.set(key,value);else data.delete(key);
  }};
  return {context,page,data,writes,measurementFrames};
}
const plain = value => JSON.parse(JSON.stringify(value));

test('all page JSON metadata survives >100 kB UTF-8 writes and ordinary readDraft',async()=>{
  const h=host(), unicode='정원🌿'.repeat(20000);
  const values={draftCanonicalBindings:[{candidate:'a',key:unicode,token:'a/type/body',value:17.5}],
    draftNoteFrames:{a:unicode},draftPalettes:{a:{libraryId:unicode}},draftTextStyles:[unicode]};
  for(const [key,value] of Object.entries(values)) {
    assert(Buffer.byteLength(JSON.stringify(value),'utf8')>100000);
    h.context.writeDraftJSON(h.page,key,value);
    assert.deepEqual(plain(h.context.readDraftJSON(h.page,key,null)),value);
    assert(h.writes.filter(row=>row.key.startsWith(key+'__chunk_')).length>1);
  }
  h.context.readNativeSemantics=async()=>({nodes:[]});
  const readback=await h.context.readDraft(h.page);
  assert.deepEqual(plain(readback.canonicalFoundationBindings),values.draftCanonicalBindings);
  assert.deepEqual(plain(readback.noteFrames),values.draftNoteFrames);
  assert.deepEqual(plain(readback.palettes),values.draftPalettes);
  assert.equal(readback.textStyles[0].id,unicode);
});

test('legacy JSON, missing defaults and rewrites retain exact values without stale chunks',()=>{
  const h=host(),key='draftCanonicalBindings',legacy=[{token:'a/type/body',value:17.5}];
  h.page.setPluginData(key,JSON.stringify(legacy));
  assert.deepEqual(plain(h.context.readDraftJSON(h.page,key,[])),legacy);
  assert.deepEqual(plain(h.context.readDraftJSON(h.page,'missing',[])),[]);
  h.context.writeDraftJSON(h.page,key,['🌿'.repeat(70000)]);
  const oldCount=JSON.parse(h.data.get(key)).chunks;
  h.context.writeDraftJSON(h.page,key,['한'.repeat(25000)]);
  const newCount=JSON.parse(h.data.get(key)).chunks;
  assert(newCount<oldCount);
  for(let i=newCount;i<oldCount;i++)assert(!h.data.has(key+'__chunk_'+i));
  h.context.writeDraftJSON(h.page,key,legacy);
  assert.equal(h.data.get(key),JSON.stringify(legacy));
  assert.equal([...h.data.keys()].filter(k=>k.startsWith(key+'__chunk_')).length,0);
});

test('incomplete chunk storage fails explicitly instead of returning partial evidence',()=>{
  const h=host(),key='draftCanonicalBindings';
  h.context.writeDraftJSON(h.page,key,['정원🌿'.repeat(20000)]);
  h.data.delete(key+'__chunk_1');
  assert.throws(()=>h.context.readDraftJSON(h.page,key,[]),/Missing draft metadata chunk draftCanonicalBindings 1/);
});

test('ordinary numeric declaration preserves values, aliases and valid integer keys',()=>{
  const {context}=host(),tokens=[];
  for(const [name,value,expected] of [['a/type/body/17.5',17.5,'a/type/body/17_5'],['a/radius/observed/3.25',3.25,'a/radius/observed/3_25'],['review/space/24',24,'review/space/24']]) {
    const result=context.declareDraftNumber(tokens,name,value);
    assert.equal(result,expected);
    const token=tokens.find(row=>row.name===result),primitive=tokens.find(row=>row.name===token.alias);
    assert.equal(primitive.value,value);
    assert.equal(token.type,'FLOAT');
  }
  assert(tokens.every(row=>!/[.{}]/.test(row.name)));
});

test('authored invalid role and alias names fail before ordinary importer page creation',async()=>{
  for(const field of ['token','alias']) for(const bad of ['type/body.17','type/{body}','type/body}']) {
    const h=host();let writes=0;
    Object.assign(h.context.DRAFT,{schema:'figma-flow-native-direction-review-v1',scope:'exploratory-only',candidates:[{id:'a',foundationBindings:[{token:'type/body',type:'FLOAT',value:17,bindings:[{key:'a.title',field:'fontSize'}],[field]:bad}]}]});
    h.context.admitDraftColorConsumers=()=>[];
    h.context.figma.createPage=()=>{writes++;throw Error('unexpected native write');};
    await assert.rejects(()=>h.context.makeDraft(),/Invalid Figma variable name for canonical foundation/);
    assert.equal(writes,0);
  }
  assert.equal(host().context.draftFoundationName({id:'a'},'type/body'),'a/type/body');
});

function geometryWorld(layers,observed={}) {
  const h=host(),nodes=[],c={id:'a',fonts:{body:{family:'Inter',style:'Regular'}},prototype:{states:[{id:'idle'}]},state_layouts:{}};
  for(const [viewport,y]of [['desktop',0],['mobile',1000]]) {
    const key='a.'+viewport+'.idle',frame={id:'frame-'+viewport,type:'FRAME',parent:h.page,x:0,y,width:1200,height:800,getPluginData:()=>key};nodes.push(frame);
    c.state_layouts[viewport]={idle:{width:1200,height:800,layers:plain(layers),control_boxes:{}}};
    for(const l of layers)nodes.push({type:'TEXT',parent:frame,x:l.x,y:l.y,width:l.w,height:l.h,textAutoResize:'HEIGHT',characters:l.value,fontName:{family:'Inter',style:'Regular'},fontSize:l.size,textAlignHorizontal:l.align?.toUpperCase()||'LEFT',
      lineHeight:{unit:'PIXELS',value:l.leading||20},letterSpacing:{unit:'PIXELS',value:l.letter_spacing||0},
      getPluginData:()=>key+'.'+l.id,...observed[l.id]});
  }
  h.page.findAll=()=>nodes;
  return {...h,c,nodes,addControl(viewport,control){control.parent=nodes.find(node=>node.type==='FRAME'&&node.getPluginData()==='a.'+viewport+'.idle');for(const label of control.children)label.parent=control;nodes.push(control);},validate(){return h.context.validateDraftGeometry(h.page,[c]);}};
}
function prepareCompletedReview(h,candidates=[h.c]) {
  for(const candidate of candidates)candidate.entry_state='idle';
  Object.assign(h.context.DRAFT,{schema:'figma-flow-native-direction-review-v1',scope:'exploratory-only',
    packet_sha256:'a'.repeat(64),instance_sha256:'b'.repeat(64),layout_sha256:'c'.repeat(64),candidates});
  h.page.setPluginData('figma-flow-direction-review-v1',h.context.DRAFT.instance_sha256);
  h.page.setPluginData('packet_sha256',h.context.DRAFT.packet_sha256);
  h.page.setPluginData('draftCanonicalBindings','[]');
  h.page.setPluginData('draftNoteFrames',JSON.stringify(Object.fromEntries(candidates.map(candidate=>[candidate.id,{boardId:'board-'+candidate.id,entries:[{key:'entry'}]}]))));
  h.page.setPluginData('draftPalettes',JSON.stringify(Object.fromEntries(candidates.map(candidate=>[candidate.id,{libraryId:'library-'+candidate.id,samples:[{instanceId:'sample'}]}]))));
  h.page.setPluginData('draftTextStyles',JSON.stringify(['style-id']));
  h.page.setPluginData('scope','exploratory-only');h.page.setPluginData('productionAdmitted','false');
  h.page.flowStartingPoints=candidates.map(candidate=>({nodeId:'frame-desktop',name:candidate.title||candidate.id}));
}
const textLayer=(id,x,y,w,h,extra={})=>({id,kind:'text',value:id,x,y,w,h,size:16,leading:20,...extra});

test('known first-native MUI and shadcn height growth fails with measured layer budgets',()=>{
  for(const [id,w,budget,actual,leading]of [['mui-title',311.47,39,78,39],['shadcn-title',152.38,51,122,60.9]]) {
    const h=geometryWorld([textLayer(id,108,131,w,budget,{leading})],{[id]:{height:actual}});
    assert.throws(()=>h.validate(),new RegExp(id+': native text height '+actual+' exceeds authored budget '+budget));
  }
});

test('fractional letter spacing and native rounded height obey max_lines without clipping',()=>{
  const layer=textLayer('fractional',20,20,200.25,41.5,{leading:20.25,letter_spacing:-.375,max_lines:2});
  const h=geometryWorld([layer],{fractional:{height:41}});h.validate();
  h.nodes.find(n=>n.type==='TEXT').height=62;
  assert.throws(()=>h.validate(),/native text lines 3 exceeds max_lines 2/);
  for(const bad of [NaN,Infinity,'-.375'])assert.throws(()=>h.context.draftTextGeometry({...layer,letter_spacing:bad}),/Invalid authored text/);
  for(const bad of [0,-1,1.5])assert.throws(()=>h.context.draftTextGeometry({...layer,max_lines:bad}),/Invalid authored text/);
});

test('native sibling overlap and off-frame fail even for malformed overlapping authored boxes',()=>{
  const layers=[textLayer('first',20,20,200,20),textLayer('second',20,45,200,20)];
  const h=geometryWorld(layers,{first:{height:40}});
  assert.throws(()=>h.validate(),/unexpected native overlap with first/);
  const malformed=geometryWorld([textLayer('first',20,20,200,40),textLayer('second',20,45,200,20)]);assert.throws(()=>malformed.validate(),/unexpected native overlap with first/);
  const outside=geometryWorld([textLayer('outside',1190,20,100,20)]);
  assert.throws(()=>outside.validate(),/native text off-frame/);
});

test('post-style measurement retains fractional width and uses true native height',()=>{
  const h=geometryWorld([textLayer('measured',20,20,200.25,20)]);
  for(const node of h.nodes.filter(n=>n.type==='TEXT'))node.resize=function(width){assert.equal(this.textAutoResize,'HEIGHT');this.width=width;this.height=40;};
  h.context.measureDraftText(h.page,[h.c]);
  assert.throws(()=>h.validate(),/height 40 exceeds authored budget 20/);
  assert(h.nodes.filter(n=>n.type==='TEXT').every(n=>n.width===200.25&&n.height===40));
});

test('control instance uses both authored dimensions, centered label and inherited padding',()=>{
  const h=geometryWorld([]),box=[20,40,320.25,60.5];
  for(const viewport of ['desktop','mobile']) {
    const key='a.'+viewport+'.idle',label={type:'TEXT',characters:'초대 보내기',x:16,y:20.25,width:288.25,height:20,lineHeight:{unit:'PIXELS',value:20}};
    const control={type:'INSTANCE',x:0,y:0,width:40,height:40,paddingLeft:16,paddingRight:16,paddingTop:12,paddingBottom:12,
      children:[label],getPluginData:()=>key+'.send',resize(w,height){this.width=w;this.height=height;}};
    h.context.fitDraftControl(control,box);h.addControl(viewport,control);h.c.state_layouts[viewport].idle.control_boxes.send=box;
    assert.equal(control.width,320.25);assert.equal(control.height,60.5);assert.equal(control.paddingTop,12);
    assert.equal(label.textAlignHorizontal,'CENTER');assert.equal(label.layoutSizingHorizontal,'FILL');assert.equal(label.maxWidth,288.25);
  }
  h.validate();
  h.nodes.find(n=>n.type==='INSTANCE').children[0].height=50;
  assert.throws(()=>h.validate(),/native label exceeds padding or is not centered/);
});

test('reopening review from another active page loads only the matched review before traversal',async()=>{
  const h=geometryWorld([textLayer('title',20,20,200,20)]);
  let loaded=false,loads=0,traversals=0,mutations=0;
  prepareCompletedReview(h);
  h.page.loadAsync=async()=>{loads++;loaded=true;};
  h.page.findAll=()=>{assert.equal(loaded,true,'matched review must load before findAll');traversals++;return h.nodes;};
  const unrelated={id:'other-project',getPluginData:()=> 'other-instance',
    async loadAsync(){assert.fail('must not load unrelated pages');},findAll(){assert.fail('must not traverse unrelated pages');}};
  h.c.foundationBindings=[];h.c.foundations={roles:[]};
  h.context.admitDraftColorConsumers=()=>[];
  h.context.figma.listAvailableFontsAsync=async()=>[{fontName:{family:'Inter',style:'Regular'}}];
  h.context.figma.root={children:[unrelated,h.page]};h.context.figma.currentPage=unrelated;
  h.context.figma.createPage=()=>{mutations++;assert.fail('must reuse matched review');};
  h.context.figma.setCurrentPageAsync=async page=>{assert.equal(loaded,true);assert.equal(page,h.page);h.context.figma.currentPage=page;};
  for(const node of h.nodes)for(const method of ['resize','clone','remove'])node[method]=()=>{mutations++;assert.fail('reopening must not mutate nodes');};
  assert.equal(await h.context.makeDraft(),h.page);
  h.context.readNativeSemantics=async()=>({nodes:[]});
  const readback=await h.context.readDraft(h.page);
  assert.equal(readback.scope,'exploratory-only');
  assert.equal(loads,1);assert(traversals>=2);assert.equal(mutations,0);
});

test('matched review load failure propagates before selection or fallback creation',async()=>{
  const h=host();
  h.page.loadAsync=async()=>{throw Error('matched page load failed');};
  h.page.findAll=()=>assert.fail('failed load must not traverse');
  prepareCompletedReview(h,[]);
  h.context.admitDraftColorConsumers=()=>[];h.context.figma.listAvailableFontsAsync=async()=>[];
  h.context.figma.root={children:[h.page]};
  h.context.figma.createPage=()=>assert.fail('must not create a fallback page');
  h.context.figma.setCurrentPageAsync=async()=>assert.fail('must not select an unloaded page');
  await assert.rejects(()=>h.context.makeDraft(),/matched page load failed/);
});

test('overlapping state rows are rejected on reuse and reuse cannot bypass text measurement',async()=>{
  const h=geometryWorld([textLayer('broken',20,20,200,20)],{broken:{height:40}});
  const reused=h.page;prepareCompletedReview(h);
  h.c.foundationBindings=[];h.c.foundations={roles:[]};h.c.fonts={body:{family:'Inter',style:'Regular'}};
  h.context.admitDraftColorConsumers=()=>[];h.context.figma.listAvailableFontsAsync=async()=>[{fontName:{family:'Inter',style:'Regular'}}];
  h.context.figma.root={children:[reused]};h.context.figma.setCurrentPageAsync=async()=>assert.fail('broken page must not be selected as success');
  await assert.rejects(()=>h.context.makeDraft(),/native text height 40 exceeds authored budget 20/);
  const clean=geometryWorld([]);clean.nodes[1].y=500;
  assert.throws(()=>clean.validate(),/Native state frames overlap/);
});

test('passive product buttons retain actual label, variant, size and zero reactions',()=>{
  const h=geometryWorld([]);h.c.control_styles={desktop:{Outline:{fill:'paper',ink:'ink',fontSize:14,leading:20,paddingX:16,paddingY:12}},mobile:{Outline:{fill:'paper',ink:'ink',fontSize:14,leading:20,paddingX:16,paddingY:12}}};
  for(const viewport of ['desktop','mobile']) {
    const state=h.c.state_layouts[viewport].idle;
    state.product_buttons={invite:{box:[20,40,320,60],variant:'Outline',label:'초대 보내기'}};
    const [button]=h.context.draftProductButtons(h.c,viewport,{id:'idle'});
    assert.equal(button.label,'초대 보내기');assert.equal(button.variant,'Outline');
    h.addControl(viewport,{type:'INSTANCE',x:20,y:40,width:320,height:60,paddingLeft:16,paddingRight:16,paddingTop:12,paddingBottom:12,reactions:[],
      getPluginData:()=> 'a.'+viewport+'.idle.invite',children:[{type:'TEXT',characters:button.label,x:16,y:20,width:288,height:20,textAlignHorizontal:'CENTER',textAutoResize:'HEIGHT',fontName:{family:'Inter',style:'Regular'},fontSize:14,lineHeight:{unit:'PIXELS',value:20},letterSpacing:{unit:'PIXELS',value:0}}]});
  }
  h.validate();
  const instance=h.nodes.find(node=>node.type==='INSTANCE');instance.reactions=[{trigger:{type:'ON_CLICK'}}];
  assert.throws(()=>h.validate(),/passive product button must have zero reactions/);
  instance.reactions=[];instance.children[0].characters='검토 행동';
  assert.throws(()=>h.validate(),/native control label missing or differs from authored text/);
  h.c.state_layouts.desktop.idle.control_boxes.invite=[20,40,320,60];
  assert.throws(()=>h.context.draftProductButtons(h.c,'desktop',{id:'idle'}),/Unique safe product button id/);
});

test('full geometry failure evidence preserves all offending rects and native natural width before rollback',()=>{
  const h=geometryWorld([textLayer('line-0',40,22,114.938,19,{leading:19,max_lines:1})],{'line-0':{height:38}});
  const messages=[];let removed=0;
  h.context.figma.ui.postMessage=message=>messages.push(message);
  h.context.figma.createText=()=>{
    const sample={width:128.375,height:19,remove(){removed++;}};
    Object.defineProperty(sample,'textAutoResize',{set(value){assert.equal(value,'WIDTH_AND_HEIGHT');}});
    return sample;
  };
  assert.throws(()=>h.validate(),/native text height 38 exceeds authored budget 19/);
  assert.equal(removed,2);
  assert.equal(h.measurementFrames.length,2);assert(h.measurementFrames.every(frame=>frame.removed));
  const failure=messages.find(message=>message.type==='geometry-failure').data;
  assert.equal(failure.passed,false);
  assert.equal(failure.schema,'figma-flow-native-geometry-failure-v1');
  const overflows=failure.findings.filter(finding=>finding.message.startsWith('native text height'));
  assert.equal(overflows.length,2);
  assert(overflows.every(finding=>finding.authored.rect.w===114.938&&finding.actual.rect.h===38&&finding.actual.naturalWidth===128.375));
});

test('failed width probe removes its fresh text sampler and leaves the original failure actionable',()=>{
  const h=geometryWorld([textLayer('line',20,20,100,20,{max_lines:1})],{line:{height:40}});
  let removed=0;
  h.context.figma.createText=()=>{
    const sample={remove(){removed++;}};
    Object.defineProperty(sample,'fontSize',{set(){throw Error('native measurement unavailable');}});
    return sample;
  };
  let failure;
  h.context.figma.ui.postMessage=message=>{if(message.type==='geometry-failure')failure=message.data;};
  assert.throws(()=>h.validate(),/native text height 40 exceeds authored budget 20/);
  assert.equal(removed,2);
  assert.equal(h.measurementFrames.length,2);assert(h.measurementFrames.every(frame=>frame.removed));
  const overflow=failure.findings.find(finding=>finding.message.startsWith('native text height'));
  assert.equal(overflow.actual.naturalWidth,null);
  assert.match(overflow.actual.naturalWidthError,/native measurement unavailable/);
});

test('observed text tolerance is one pixel and mixed or non-finite typography fails',()=>{
  const h=geometryWorld([textLayer('bounded',-1,20,100,20)]);h.validate();
  h.nodes.find(node=>node.type==='TEXT').x=-1.01;
  assert.throws(()=>h.validate(),/native text off-frame/);
  const invalid=geometryWorld([textLayer('typed',20,20,100,20)],{typed:{fontName:Symbol('mixed'),fontSize:NaN}});
  let payload;invalid.context.figma.ui.postMessage=message=>{payload=message.data;structuredClone(message);};
  assert.throws(()=>invalid.validate(),/native editable text\/font differs/);
  assert.equal(payload.passed,false);
  assert(payload.findings.some(finding=>finding.message.includes('editable text/font')));
});

test('explicit single-line text rounds only available width up for native pixel quantization',()=>{
  const layer=textLayer('line-0',40,22,114.938,19,{leading:19,max_lines:1});
  const h=geometryWorld([layer],{'line-0':{height:38}});
  for(const node of h.nodes.filter(node=>node.type==='TEXT'))node.resize=function(width){
    this.width=width;this.height=width>=115?19:38;
  };
  h.context.measureDraftText(h.page,[h.c]);h.validate();
  assert(h.nodes.filter(node=>node.type==='TEXT').every(node=>node.width===115&&node.height===19&&node.x===40));
  assert.equal(h.context.draftTextWidth({...layer,max_lines:2}),114.938);
  const {max_lines,...unbounded}=layer;
  assert.equal(h.context.draftTextWidth(unbounded),114.938);
  const undersized=geometryWorld([{...layer,w:113.1}],{'line-0':{height:38}});
  for(const node of undersized.nodes.filter(node=>node.type==='TEXT'))node.resize=function(width){
    this.width=width;this.height=width>=115?19:38;
  };
  undersized.context.measureDraftText(undersized.page,[undersized.c]);
  assert.throws(()=>undersized.validate(),/native text height 38 exceeds authored budget 19/);
  assert(undersized.nodes.filter(node=>node.type==='TEXT').every(node=>node.width===114&&node.height===38));
});

test('screen text cannot intersect whole product control padding even below five percent',()=>{
  const h=geometryWorld([textLayer('error-message',20,535.353,100,20)]);
  h.c.control_styles={desktop:{Primary:{fontSize:14,leading:20,paddingX:16,paddingY:12}},mobile:{Primary:{fontSize:14,leading:20,paddingX:16,paddingY:12}}};
  for(const viewport of ['desktop','mobile']) {
    h.c.state_layouts[viewport].idle.product_buttons={invite:{box:[20,554.641,320,60],variant:'Primary',label:'초대 보내기'}};
    h.addControl(viewport,{type:'INSTANCE',x:20,y:554.641,width:320,height:60,paddingLeft:16,paddingRight:16,paddingTop:12,paddingBottom:12,reactions:[],
      getPluginData:()=> 'a.'+viewport+'.idle.invite',children:[{type:'TEXT',characters:'초대 보내기',x:16,y:20,width:288,height:20,textAlignHorizontal:'CENTER',textAutoResize:'HEIGHT',fontName:{family:'Inter',style:'Regular'},fontSize:14,lineHeight:{unit:'PIXELS',value:20},letterSpacing:{unit:'PIXELS',value:0}}]});
  }
  let failure;h.context.figma.ui.postMessage=message=>{if(message.type==='geometry-failure')failure=message.data;};
  assert.throws(()=>h.validate(),/error-message: native screen text intersects whole control invite/);
  const intersection=failure.findings.find(finding=>finding.message.includes('whole control invite'));
  assert.equal(intersection.actual['error-message'].y,535.353);
  assert.equal(intersection.actual.invite.y,554.641);
  for(const node of h.nodes.filter(node=>node.type==='TEXT'))node.y=534.641;
  h.validate();
});

test('reused page rejects hidden, transparent or reparented authored content without mutation',async()=>{
  for(const [name,mutate,pattern]of [
    ['hidden frame',h=>{h.nodes[0].visible=false;},/effectively hidden or transparent/],
    ['transparent frame',h=>{h.nodes[0].opacity=0;},/effectively hidden or transparent/],
    ['hidden text',h=>{h.nodes[1].visible=false;},/effectively hidden or transparent/],
    ['transparent text',h=>{h.nodes[1].opacity=0;},/effectively hidden or transparent/],
    ['reparented text',h=>{h.nodes[1].parent={id:'wrong-container',parent:h.nodes[0]};},/native parent differs/],
    ['reparented frame',h=>{h.nodes[0].parent={id:'wrong-page'};},/native parent differs/],
    ['hidden shape',h=>{h.nodes.find(node=>node.type==='RECTANGLE').visible=false;},/effectively hidden or transparent/],
    ['transparent shape',h=>{h.nodes.find(node=>node.type==='RECTANGLE').opacity=0;},/effectively hidden or transparent/],
    ['reparented shape',h=>{h.nodes.find(node=>node.type==='RECTANGLE').parent=h.page;},/native parent differs/],
    ['hidden control',h=>{h.nodes.find(node=>node.type==='INSTANCE').visible=false;},/effectively hidden or transparent/],
    ['transparent label',h=>{h.nodes.find(node=>node.type==='INSTANCE').children[0].opacity=0;},/effectively hidden or transparent/],
    ['reparented control',h=>{h.nodes.find(node=>node.type==='INSTANCE').parent=h.page;},/native parent differs/],
    ['reparented label',h=>{h.nodes.find(node=>node.type==='INSTANCE').children[0].parent=h.page;},/native parent differs/]
  ]) {
    const h=geometryWorld([textLayer('title',20,20,200,20)]);
    for(const viewport of ['desktop','mobile']) {
      const frame=h.nodes.find(node=>node.type==='FRAME'&&node.getPluginData()==='a.'+viewport+'.idle');
      h.c.state_layouts[viewport].idle.layers.push({id:'surface',kind:'rect',x:10,y:10,w:300,h:70});
      h.nodes.push({type:'RECTANGLE',parent:frame,x:10,y:10,width:300,height:70,getPluginData:()=> 'a.'+viewport+'.idle.surface'});
      h.c.state_layouts[viewport].idle.control_boxes.send=[20,100,320,60];
      h.addControl(viewport,{type:'INSTANCE',x:20,y:100,width:320,height:60,paddingLeft:16,paddingRight:16,paddingTop:12,paddingBottom:12,
        getPluginData:()=> 'a.'+viewport+'.idle.send',children:[{type:'TEXT',characters:'보내기',x:16,y:20,width:288,height:20,textAlignHorizontal:'CENTER',textAutoResize:'HEIGHT',lineHeight:{unit:'PIXELS',value:20}}]});
    }
    mutate(h);
    let mutations=0;
    for(const node of [h.page,...h.nodes,...h.nodes.filter(node=>node.type==='INSTANCE').flatMap(node=>node.children)]) {
      for(const method of ['remove','resize','clone'])node[method]=()=>{mutations++;throw Error('unexpected reuse mutation '+method);};
    }
    h.c.foundationBindings=[];h.c.foundations={roles:[]};
    prepareCompletedReview(h);
    h.context.admitDraftColorConsumers=()=>[];
    h.context.figma.listAvailableFontsAsync=async()=>[{fontName:{family:'Inter',style:'Regular'}}];
    h.context.figma.root={children:[h.page]};
    h.context.figma.setCurrentPageAsync=async()=>{mutations++;};
    await assert.rejects(()=>h.context.makeDraft(),pattern,name);
    assert.equal(mutations,0,name);
  }
});

test('reused overflowing text never creates a natural-width probe on an existing page',async()=>{
  const h=geometryWorld([textLayer('overflow',20,20,200,20,{max_lines:1})],{overflow:{height:40}});
  let clones=0;
  for(const node of h.nodes.filter(node=>node.type==='TEXT'))node.clone=()=>{clones++;throw Error('reuse probe forbidden');};
  h.c.foundationBindings=[];h.c.foundations={roles:[]};prepareCompletedReview(h);
  h.context.admitDraftColorConsumers=()=>[];h.context.figma.listAvailableFontsAsync=async()=>[{fontName:{family:'Inter',style:'Regular'}}];
  h.context.figma.root={children:[h.page]};
  await assert.rejects(()=>h.context.makeDraft(),/native text height 40 exceeds authored budget 20/);
  assert.equal(clones,0);
});

test('two ordered CSS-like native shadows retain offsets, radii, spread and alpha',()=>{
  const {context}=host();
  const authored=[{x:0,y:1,blur:2,spread:-.5,color:'#112233',opacity:.08},{x:-.25,y:0,blur:0,spread:2,color:'#3b82f6',opacity:.35}];
  const effects=plain(context.draftShadows(authored,'card'));
  assert.deepEqual(effects.map(effect=>({type:effect.type,offset:effect.offset,radius:effect.radius,spread:effect.spread,alpha:effect.color.a})),[
    {type:'DROP_SHADOW',offset:{x:0,y:1},radius:2,spread:-.5,alpha:.08},
    {type:'DROP_SHADOW',offset:{x:-.25,y:0},radius:0,spread:2,alpha:.35}]);
  assert.deepEqual(effects[0].color,{r:17/255,g:34/255,b:51/255,a:.08});
  assert(effects.every(effect=>effect.visible&&effect.blendMode==='NORMAL'&&effect.showShadowBehindNode));
  assert.deepEqual(plain(context.draftShadows(undefined,'absent')),[]);
  for(const invalid of [null,{},[{...authored[0],x:NaN}],[{...authored[0],y:Infinity}],[{...authored[0],blur:-1}],
    [{...authored[0],spread:'2'}],[{...authored[0],opacity:-.1}],[{...authored[0],opacity:1.01}],[{...authored[0],color:'#abc'}],
    [{...authored[0],unknown:1}]])assert.throws(()=>context.draftShadows(invalid,'card'),/shadow/);
});

test('invalid shape and control shadows fail preflight before ordinary authoring',async()=>{
  const h=host();let writes=0;
  const candidate={id:'a',fonts:{},foundationBindings:[],foundations:{roles:[]},prototype:{states:[{id:'idle'}],bindings:[]},
    control_styles:{desktop:{Primary:{shadows:[{x:0,y:1,blur:-2,spread:0,color:'#000000',opacity:.1}]}}},
    state_layouts:{desktop:{idle:{layers:[{id:'card',kind:'rect',shadows:[{x:0,y:NaN,blur:2,spread:0,color:'#000000',opacity:.1}]}]}},mobile:{idle:{layers:[]}}}};
  Object.assign(h.context.DRAFT,{schema:'figma-flow-native-direction-review-v1',scope:'exploratory-only',candidates:[candidate]});
  h.context.admitDraftColorConsumers=()=>[];
  h.context.figma.listAvailableFontsAsync=async()=>[];
  h.context.figma.createPage=()=>{writes++;throw Error('unexpected write');};
  await assert.rejects(()=>h.context.makeDraft(),/Finite native shadow/);
  assert.equal(writes,0);
});


test('screen and palette instances keep their text property after Figma drops a label link',()=>{
  const {context}=host();
  const key='문구#13:7', replacement='문구#13:8';
  const text={type:'TEXT',componentPropertyReferences:{}}, other={type:'TEXT',componentPropertyReferences:{visible:'Show#1'}};
  const set={id:'s',componentPropertyDefinitions:{[key]:{type:'TEXT'}},children:[],addComponentProperty(){
    this.componentPropertyDefinitions[replacement]={type:'TEXT'};
    return replacement;
  }};
  const main={parent:set,children:[text]};
  set.children=[main,{children:[other]}];
  const keys=new Map([[set.id,key]]), visible={type:'TEXT',characters:'default'};
  const instance={children:[visible],componentProperties:{},setProperties(values){
    const prop=text.componentPropertyReferences.characters;
    assert.equal(set.componentPropertyDefinitions[prop].type,'TEXT');
    visible.characters=values[prop];
  }};
  context.setDraftControlLabel(instance,main,'장비 확인',keys);
  assert.equal(visible.characters,'장비 확인');
  assert.equal(other.componentPropertyReferences.visible,'Show#1');
  delete set.componentPropertyDefinitions[key];
  context.setDraftControlLabel(instance,main,'돌아가기',keys);
  assert.equal(visible.characters,'돌아가기');
  assert.equal(text.componentPropertyReferences.characters,replacement);
  assert.equal(other.componentPropertyReferences.characters,undefined);
  assert.throws(()=>context.setDraftControlLabel(instance,main,'label',new Map()),/unowned/);
});

test('annotation board requires its own available body font before native writes',()=>{
  const {context}=host(), f={family:'Noto Sans KR',style:'Regular'};
  const candidate={id:'rescue',fonts:{title:f}};
  const check=()=>Array.from(context.preflightDraft({candidates:[candidate]},[f]));
  assert.match(check().join(' '),/annotation font role missing: rescue\/body/);
  candidate.fonts.body=f;
  assert.deepEqual(check(),[]);
});
