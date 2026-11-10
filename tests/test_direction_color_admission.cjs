/* Admission tests drive the ordinary importer handler. No live Figma evidence. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const runtime = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));

function candidate() {
  const colors = {paper:'#fffaf0',ink:'#20363d',accent:'#aa4422'};
  const layout = {width:390,height:844,bg:'paper',layers:[
    {id:'title',kind:'text',value:'정원에서 만나는 소리',ink:'ink',font:'body',size:18,x:20,y:40,w:330,h:40}],
    control_boxes:{'inspect-seed':[20,700,330,56]}};
  const result={id:'garden-any-name',colors,foundations:{roles:Object.entries(colors).map(([name,value])=>({kind:'color',token:'color/'+name,value}))},
    foundationBindings:[{token:'type/body',type:'FLOAT',value:18,bindings:[{key:'garden-any-name.desktop.CANONICAL-OTHER.title',field:'fontSize'}]}],
    prototype:{states:[{id:'CANONICAL-OTHER',screen:'SCR-ANY'}],bindings:[
      {viewport:'desktop',source_state:'CANONICAL-OTHER',target_state:'CANONICAL-OTHER',action:'ACT-ANY',control_id:'inspect-seed'},
      {viewport:'mobile',source_state:'CANONICAL-OTHER',target_state:'CANONICAL-OTHER',action:'ACT-ANY',control_id:'inspect-seed'}]},
    state_layouts:{desktop:{'CANONICAL-OTHER':clone(layout)},mobile:{'CANONICAL-OTHER':clone(layout)}},
    action_notes:{'ACT-ANY|inspect-seed':{action:'ACT-ANY',visual_variant:'Custom seed surface'}},
    action_labels:{'ACT-ANY':'씨앗을 살펴보기'},
    fonts:{body:{family:'Inter',style:'Regular'}},
    control_styles:{desktop:{'Custom seed surface':{fill:'accent',ink:'paper'}},mobile:{'Custom seed surface':{fill:'accent',ink:'paper'}}}};
  result.graph={design_foundations:clone(result.foundations)};return result;
}

function host(candidates, reuse=false, packet={}, fonts=[{family:'Inter',style:'Regular'}]) {
  const writes={pages:0,variables:0,styles:0},messages=[];
  const context=vm.createContext({DRAFT:{schema:'figma-flow-native-direction-review-v1',scope:'exploratory-only',production_admitted:false,fileKey:'exact-current-file',instance_sha256:'packet-instance',packet_sha256:'packet-hash',candidates,...packet},__html__:'',
    figma:{fileKey:'exact-current-file',currentPage:{id:'selected-page'},root:{children:reuse?[{getPluginData:()=> 'packet-instance'}]:[]},
      showUI(){},ui:{postMessage(message){messages.push(message);}},
      async listAvailableFontsAsync(){return fonts.map(fontName=>({fontName}));},
      createPage(){writes.pages++;throw Error('AUTHORING_REACHED_AFTER_ADMISSION');},
      createTextStyle(){writes.styles++;throw Error('unexpected style write');},
      variables:{createVariable(){writes.variables++;throw Error('unexpected variable write');},createVariableCollection(){writes.variables++;throw Error('unexpected collection write');}},
      async setCurrentPageAsync(){throw Error('unexpected existing-page reuse before color admission');}}});
  vm.runInContext(runtime,context);
  return {context,writes,messages,async import(){await context.figma.ui.onmessage({type:'draft-review'});}};
}

function addUnused(c,name='unused') {
  c.colors[name]='#9988aa';const role={kind:'color',token:'color/'+name,value:c.colors[name]};c.foundations.roles.push(role);c.graph.design_foundations.roles.push(clone(role));
}

function fromSavedMoss() {
  const root=path.resolve(__dirname,'../../moss-choir');
  const filename=path.join(root,'native-layout.json');
  if(!fs.existsSync(filename))return null;
  const layout=JSON.parse(fs.readFileSync(filename,'utf8'));
  return layout.candidates.map(source=>{
    const graph=JSON.parse(fs.readFileSync(path.resolve(root,source.graph.path),'utf8'));
    const notes={};
    for(const node of graph.nodes.filter(n=>n.type==='action')) {
      const controls=node.annotation.control_ids||[node.annotation.control_id];
      for(const id of controls)notes[node.id+'|'+id]={action:node.id,visual_variant:node.annotation.visual_variant};
    }
    return {...source,graph,foundations:graph.design_foundations,prototype:graph.draft_prototype,foundationBindings:[],action_notes:notes,
      action_labels:Object.fromEntries(graph.nodes.filter(n=>n.type==='action').map(n=>[n.id,n.title]))};
  });
}

test('ordinary current-file import rejects injected unused color before any native write or owned-page reuse',async()=>{
  for(const reuse of [false,true]) {
    const c=candidate();addUnused(c);
    c.color_use_plan={ok:true,allRolesUsed:true};
    const h=host([c],reuse);await h.import();
    assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
    assert(h.messages.some(m=>m.message?.includes('unused role garden-any-name/unused')));
  }
});

test('role declarations, raw gradient hex, palette sample and orphan main style are not source consumers',async()=>{
  const c=candidate();addUnused(c);
  for(const viewport of ['desktop','mobile']) {
    c.state_layouts[viewport]['CANONICAL-OTHER'].layers.push({id:'raw-gradient',kind:'gradient',x:0,y:80,w:200,h:100,stops:[{position:0,color:c.colors.unused,opacity:1}]});
    c.control_styles[viewport]['Orphan variant']={fill:'unused',ink:'ink'};
  }
  c.foundations.palette={samples:[{variant:'Orphan variant'}]};
  const h=host([c]);await h.import();
  assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
  assert(h.messages.some(m=>m.message?.includes('unused role')));
});

test('off-canvas, empty text and unrendered state cannot hide an unused named color',async()=>{
  for(const kind of ['off-canvas','empty-text','unrendered']) {
    const c=candidate();addUnused(c);
    for(const viewport of ['desktop','mobile']) {
      if(kind==='off-canvas')c.state_layouts[viewport]['CANONICAL-OTHER'].layers.push({id:'hidden',kind:'rect',fill:'unused',x:500,y:40,w:30,h:40});
      else if(kind==='empty-text')c.state_layouts[viewport]['CANONICAL-OTHER'].layers.push({id:'empty',kind:'text',value:' ',ink:'unused',size:18,x:0,y:40,w:100,h:40});
      else c.state_layouts[viewport]['UNRENDERED']={width:390,height:844,bg:'unused',layers:[],control_boxes:{}};
    }
    const h=host([c]);await h.import();assert.equal(h.writes.pages,0);assert(h.messages.some(m=>m.message?.includes('unused role')));
  }
});

test('valid arbitrary state/variant names and actual named control color reach ordinary authoring',async()=>{
  const h=host([candidate()]);await h.import();
  assert.equal(h.writes.pages,1);assert.equal(h.writes.variables,0);assert.equal(h.writes.styles,0);
  assert(h.messages.some(m=>m.message?.includes('AUTHORING_REACHED_AFTER_ADMISSION')));
  const derived=vm.runInContext('admitDraftColorConsumers(DRAFT.candidates)',h.context);
  const accent=derived.find(row=>row.token==='color/accent');
  assert.equal(accent.consumers.length,2);
  assert(accent.consumers.every(use=>use.key.endsWith('.inspect-seed')));
});

test('actual saved initial Moss tint packet is rejected without writes',async t=>{
  const candidates=fromSavedMoss();if(!candidates)return t.skip('Saved project evidence not present in isolated plugin checkout');
  assert(candidates[0].colors.tint,'This case pins the initial color/tint source, not the remediated revision');
  const h=host(candidates);await h.import();
  assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
  assert(h.messages.some(m=>m.message?.includes('unused role a/tint')));
});


test('explicit COLOR keeps the named paint and planned alias without duplicate scalar paths',async()=>{
  const c=candidate(),role=c.foundations.roles.find(role=>role.token==='color/accent');
  role.alias='palette/accent';role.native={type:'COLOR',value:{r:170/255,g:68/255,b:34/255,a:1},bindings:[
    {key:c.id+'.desktop.CANONICAL-OTHER.inspect-seed',field:'fills',paintIndex:0}]};
  c.graph.design_foundations=clone(c.foundations);
  c.foundationBindings.push({token:role.token,alias:role.alias,...clone(role.native)});
  c.foundationBindings.at(-1).value={a:1,b:34/255,g:68/255,r:170/255};
  c.foundationBindings.at(-1).bindings[0]={paintIndex:0,field:'fills',key:c.id+'.desktop.CANONICAL-OTHER.inspect-seed'};
  const h=host([c]);await h.import();assert.equal(h.writes.pages,1);
  const definitions=vm.runInContext(`(()=>{const result=[];declareDraftFoundations(DRAFT.candidates[0],(...args)=>declareDraftToken(result,...args));declareDraftToken(result,'garden-any-name/palette/accent','COLOR',{r:170/255,g:68/255,b:34/255});return result;})()`,h.context);
  assert.equal(definitions.filter(row=>row.type==='COLOR').length,2);
  assert.deepEqual(JSON.parse(JSON.stringify(definitions.find(row=>row.name==='garden-any-name/color/accent'))),
    {name:'garden-any-name/color/accent',type:'COLOR',alias:'garden-any-name/palette/accent'});
  for(const mutate of [
    candidate=>{candidate.foundationBindings.at(-1).value.r=0;},
    candidate=>{candidate.foundations.roles.at(-1).value='#000000';},
    candidate=>{candidate.foundationBindings.at(-1).bindings[0].paintIndex=1;},
    candidate=>{candidate.foundationBindings.at(-1).bindings[0].key=candidate.id+'.desktop.CANONICAL-OTHER.title';},
    candidate=>{candidate.foundationBindings.at(-1).bindings[0].field='strokes';}]) {
    const changed=clone(c);mutate(changed);const invalid=host([changed]);await invalid.import();assert.deepEqual(invalid.writes,{pages:0,variables:0,styles:0});
  }
});

test('near-equal explicit RGB is admitted only with exact graph-hex registry declarations',async()=>{
  const c=candidate(),role=c.foundations.roles.find(role=>role.token==='color/accent');
  role.alias='palette/accent';role.native={type:'COLOR',value:{r:170/255+1e-10,g:68/255,b:34/255,a:1},bindings:[
    {key:c.id+'.desktop.CANONICAL-OTHER.inspect-seed',field:'fills'}]};
  c.graph.design_foundations=clone(c.foundations);
  c.foundationBindings.push({token:role.token,alias:role.alias,...clone(role.native)});
  const h=host([c]);await h.import();
  assert.equal(h.writes.pages,1);assert(h.messages.some(message=>message.message?.includes('AUTHORING_REACHED_AFTER_ADMISSION')));
  const registry=vm.runInContext(`(()=>{
    const result=[],c=DRAFT.candidates[0];
    declareDraftFoundations(c,(...args)=>declareDraftToken(result,...args));
    const role=c.foundations.roles.find(role=>role.token==='color/accent'),value=rgb(c.colors.accent);
    declareDraftToken(result,draftFoundationName(c,role.alias),'COLOR',value);
    declareDraftToken(result,draftFoundationName(c,role.token),'COLOR',null,draftFoundationName(c,role.alias));
    return result;
  })()`,h.context);
  const primitive=registry.find(row=>row.name===c.id+'/palette/accent');
  assert.equal(primitive.value.r,170/255);
  assert.notEqual(primitive.value.r,role.native.value.r);
  assert.equal(registry.filter(row=>row.type==='COLOR').length,2);
});

test('equal raw hex never substitutes for the explicitly named COLOR consumer',async()=>{
  const c=candidate(),key=c.id+'.desktop.CANONICAL-OTHER.title';
  c.colors.ink=c.colors.accent;
  c.foundations.roles.find(role=>role.token==='color/ink').value=c.colors.ink;
  const accent=c.foundations.roles.find(role=>role.token==='color/accent');
  accent.native={type:'COLOR',value:{r:170/255,g:68/255,b:34/255},bindings:[{key,field:'fills'}]};
  c.graph.design_foundations=clone(c.foundations);
  c.foundationBindings.push({token:accent.token,alias:null,...clone(accent.native)});
  const h=host([c]);await h.import();assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
  assert(h.messages.some(message=>message.message?.includes('COLOR target is not its named source paint')));
});

test('explicit COLOR instance consumer retains the actual main named paint job',()=>{
  const c=candidate(),role=c.foundations.roles.find(role=>role.token==='color/accent'),key=c.id+'.desktop.CANONICAL-OTHER.inspect-seed';
  role.native={type:'COLOR',value:{r:170/255,g:68/255,b:34/255},bindings:[{key,field:'fills',paintIndex:0}]};
  c.graph.design_foundations=clone(c.foundations);c.foundationBindings=[{token:role.token,alias:null,...clone(role.native)}];
  const node=(id,type,key)=>({id,type,children:[],getPluginData(name){return name==='semanticKey'?key:'';}});
  const page=node('page','PAGE','page'),main=node('main','COMPONENT','main-source'),instance=node('instance','INSTANCE',key);
  instance.parent=page;main.parent=page;page.children=[main,instance];page.findAll=()=>[main,instance];
  instance.getPluginData=name=>name==='semanticComponent'?JSON.stringify({sourceKey:'main-source'}):name==='semanticKey'?key:'';
  const h=host([c]);h.context.resolveInstanceSemanticKey=n=>n.getPluginData('semanticKey');h.context.page=page;
  h.context.jobs=[{key:'main',field:'fills',token:c.id+'/color/accent'}];
  const actual=vm.runInContext('applyDraftFoundations(page,DRAFT.candidates,jobs)',h.context);
  assert.equal(actual[0].nodeId,'instance');assert.equal(actual[0].paintIndex,0);
  assert(h.context.jobs.some(job=>job.key==='instance'&&job.token===c.id+'/color/accent'));
  h.context.jobs=[{key:'main',field:'fills',token:c.id+'/color/ink'}];
  assert.throws(()=>vm.runInContext('applyDraftFoundations(page,DRAFT.candidates,jobs)',h.context),/actual named source paint/);
});

test('injected COLOR rows and numeric aliases cannot mint an alternative color path',async()=>{
  for(const row of [
    {token:'color/rogue',type:'COLOR',value:{r:1,g:0,b:0},bindings:[{key:'somewhere',field:'fills'}]},
    {token:'color/accent',type:'FLOAT',value:18,bindings:[{key:'somewhere',field:'fontSize'}]},
    {token:'palette/accent',type:'FLOAT',value:18,bindings:[{key:'somewhere',field:'fontSize'}]}]) {
    const c=candidate();c.foundations.roles.find(role=>role.token==='color/accent').alias='palette/accent';
    c.graph.design_foundations=clone(c.foundations);c.foundationBindings.push(row);
    const h=host([c]);await h.import();assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
  }
});

test('wrong schema, scope or production claim is rejected before native mutation',async()=>{
  for(const packet of [{schema:'production-import'}, {scope:'production'}, {production_admitted:true}, {production_admitted:'false'}]) {
    const h=host([candidate()],false,packet);await h.import();assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
    assert(h.messages.some(message=>message.message?.includes('Explicit exploratory review packet required')));
  }
});

function solidLayer(extra){return {id:'shape',kind:'rect',x:20,y:120,w:200,h:120,fill:'paper',...extra};}
function withLayer(c,layer){for(const viewport of ['desktop','mobile'])c.state_layouts[viewport]['CANONICAL-OTHER'].layers.push(clone(layer));return c;}
const reached=h=>h.writes.pages===1&&h.messages.some(m=>String(m.message).includes('AUTHORING_REACHED_AFTER_ADMISSION'));

test('0.17 stroke and ellipse fill are actual named color consumers',async()=>{
  for(const layer of [solidLayer({stroke:'unused',stroke_width:2,radius:12,role:'surface'}),{id:'halo',kind:'ellipse',x:40,y:120,w:200,h:200,fill:'unused',opacity:0.4,role:'illustration'}]) {
    const c=candidate();addUnused(c);withLayer(c,layer);
    const h=host([c]);await h.import();
    assert(reached(h),JSON.stringify(h.messages));
  }
});

test('0.17 undeclared stroke or ellipse paint is rejected before any native write',async()=>{
  for(const layer of [solidLayer({stroke:'ghost',stroke_width:2}),{id:'halo',kind:'ellipse',x:40,y:120,w:200,h:200,fill:'ghost'}]) {
    const c=withLayer(candidate(),layer);
    const h=host([c]);await h.import();
    assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
    assert(h.messages.some(m=>String(m.message).includes('undeclared paint garden-any-name/ghost')),JSON.stringify(h.messages));
  }
});

test('preflight lists every missing font, raster and font role in one message before any page',async()=>{
  const c=candidate();c.fonts.display={family:'Pretendard',style:'Bold'};
  withLayer(c,{id:'art',kind:'image',asset:'missing-art',x:0,y:0,w:100,h:100,role:'image'});
  withLayer(c,{id:'caption',kind:'text',value:'캡션',font:'serif',ink:'ink',size:16,x:20,y:300,w:300,h:30});
  const h=host([c],false,{assets:{}});await h.import();
  assert.deepEqual(h.writes,{pages:0,variables:0,styles:0});
  const message=h.messages.map(m=>String(m.message)).find(m=>m.includes('검토 초안을 만들기 전에'))||'';
  assert(message.includes('파일은 변경되지 않았습니다'),message);
  for(const part of ['Pretendard Bold','Pinned raster reference missing missing-art','Pinned font role missing serif'])assert(message.includes(part),part+' in '+message);
});

test('preflight passes when every font is installed and authoring is reached',async()=>{
  const h=host([candidate()]);await h.import();
  assert(reached(h),JSON.stringify(h.messages));
  const missing=host([candidate()],false,{},[]);await missing.import();
  assert.deepEqual(missing.writes,{pages:0,variables:0,styles:0});
  assert(missing.messages.some(m=>String(m.message).includes('필수 실제 글꼴 없음: Inter Regular')));
});
