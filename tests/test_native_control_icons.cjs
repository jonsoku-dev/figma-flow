const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../figma-bridge/direction_review.js'),'utf8');
function host(){const context=vm.createContext({DRAFT:{assets:{arrow:'cGlubmVk'}},__html__:'',figma:{showUI(){},ui:{postMessage(){}},base64Decode:value=>value,createImage:()=>({hash:'pinned-hash'})}});vm.runInContext(source,context);return context;}
const iconStyle=placement=>({icon:{asset:'arrow',placement,width:18,height:18,gap:18},paddingX:20,paddingY:12});
function fixture(placement='after'){
 const parent={width:160,height:54,paddingLeft:20,paddingRight:20,paddingTop:12,paddingBottom:12,itemSpacing:18,children:[]};
 const label={type:'TEXT',parent,textAutoResize:'WIDTH_AND_HEIGHT',layoutSizingHorizontal:'HUG',x:placement==='after'?27:63,y:15,width:70,height:24,getPluginData:()=>''};
 const image={type:'RECTANGLE',parent,x:placement==='after'?115:27,y:18,width:18,height:18,visible:true,opacity:1,getPluginData:()=> 'arrow',fills:[{type:'IMAGE',imageHash:'pinned-hash',scaleMode:'FIT'}]};
 parent.children=placement==='after'?[label,image]:[image,label];return {parent,label,image};
}
test('before/after controls keep exact pinned image, gap and combined center',()=>{
 const h=host();for(const placement of ['before','after']){const{parent,label}=fixture(placement),errors=[];h.validateDraftControlIcon(parent,iconStyle(placement),label,msg=>errors.push(msg));assert.deepEqual(errors,[]);}
});
test('correct label never admits wrong/missing/hidden/shifted raster icon',()=>{
 const h=host();for(const mutate of [f=>f.parent.children=[f.label],f=>f.image.fills[0].imageHash='wrong',f=>f.image.width=19,f=>f.image.x-=5,f=>f.image.y=10,f=>f.image.opacity=0,f=>f.parent.itemSpacing=0]){const f=fixture(),errors=[];mutate(f);h.validateDraftControlIcon(f.parent,iconStyle('after'),f.label,msg=>errors.push(msg));assert(errors.length);}
});
test('raster is a reusable main child and semantic label/icon keys preserve both placements and palettes',()=>{
 const h=host();for(const placement of ['before','after']){const main={children:[{type:'TEXT',getPluginData:()=>''}],insertChild(index,node){this.children=this.children.filter(n=>n!==node);this.children.splice(index,0,node);}};
  const render=(parent,key,spec)=>{const data={};const n={type:'RECTANGLE',key,spec,setPluginData:(key,value)=>data[key]=value,getPluginData:key=>data[key]||''};parent.children.push(n);return n;};
  h.addDraftControlIcon(main,'a.desktop.component.Primary',iconStyle(placement),render);
  assert.equal(main.children.length,2);assert.equal(main.children[placement==='before'?0:1].spec.asset,'arrow');
  for(const key of ['a.desktop.idle.send','review.palette.a.Primary']){const mapping=JSON.parse(JSON.stringify(h.draftControlChildKeys(main,key)));assert.equal(mapping[placement==='before'?0:1].key,key+'.icon');assert.equal(mapping[placement==='before'?1:0].key,key+'.label');}
 }
});
test('text-only remains compatible and malformed icon is rejected before authoring',()=>{
 const h=host();h.validateDraftControlIcon({children:[{type:'TEXT'}]}, {},null,()=>assert.fail());
 for(const bad of [null,[],{}, {asset:'missing',placement:'after',width:18,height:18,gap:10},{...iconStyle('after').icon,gap:-1}])assert.throws(()=>h.draftControlIcon({icon:bad},h.DRAFT.assets,'key'));
});

test('icon mains own intrinsic HUG text and fitting instances never fixes child widths',()=>{
 const h=host(),label={type:'TEXT',width:51,height:48,resize(){throw Error('Instance label must not be resized');},getPluginData:()=>''};
 const image={width:18,getPluginData:()=> 'arrow'};
 h.configureDraftControlLabel(label,{maxWidth:160.97,paddingLeft:23,paddingRight:23},iconStyle('after'));
 assert.equal(label.layoutSizingHorizontal,'HUG');assert.equal(label.textAutoResize,'WIDTH_AND_HEIGHT');assert.equal(label.maxWidth,null);
 const instance={width:160.97,height:54,paddingLeft:23,paddingRight:23,paddingTop:15,paddingBottom:15,itemSpacing:20,children:[label,image],resize(w,height){this.width=w;this.height=height;}};
 h.fitDraftControl(instance,[56,600.81,160.97,54]);
 assert.equal(label.layoutSizingHorizontal,'HUG');assert.equal(label.textAutoResize,'WIDTH_AND_HEIGHT');assert.equal(label.maxWidth,null);
});

test('same-width wrong palette labels and exposed property overrides are rejected for text-only and icon variants',async()=>{
 const h=host(),property='문구#1',set={componentPropertyDefinitions:{[property]:{type:'TEXT'}}};
 const main={id:'main',type:'COMPONENT',parent:set,children:[{type:'TEXT',componentPropertyReferences:{characters:property}}]};
 const label={type:'TEXT',characters:'Go',componentPropertyReferences:{characters:property}};
 const instance={type:'INSTANCE',children:[label],componentProperties:{[property]:{type:'TEXT',value:'Go'}},async getMainComponentAsync(){return main;},getPluginData:()=> 'review.palette.a.Primary'};
 main.getPluginData=()=> 'a.desktop.component.Primary';
 const candidates=[{id:'a',action_labels:{go:'Go'},foundations:{palette:{samples:[{component:'Primary',variant:'Primary',action:'go'}]}}}];
 const page={findAll:()=>[main,instance]};await h.validateDraftPaletteControls(page,candidates);
 for(const change of [()=>{label.characters='No';},()=>{instance.componentProperties[property].value='No';},()=>{label.componentPropertyReferences.characters='foreign';}]){
  label.characters='Go';instance.componentProperties[property].value='Go';label.componentPropertyReferences.characters=property;change();
  await assert.rejects(()=>h.validateDraftPaletteControls(page,candidates),/palette action label or exposed text property/);
 }
 label.characters='Go';instance.componentProperties[property].value='Go';label.componentPropertyReferences.characters=property;
 instance.getMainComponentAsync=async()=>({...main,id:'other'});
 await assert.rejects(()=>h.validateDraftPaletteControls(page,candidates),/palette main differs/);
});
test('intrinsic icon text passes strict typography only in its declared resize mode',()=>{
 const h=host(),candidate={fonts:{body:{family:'Inter',style:'Regular'}}};
 const authored={value:'Go',size:14,font:'body',align:'center',leading:24,max_lines:1};
 const node={type:'TEXT',characters:'Go',fontName:candidate.fonts.body,fontSize:14,lineHeight:{unit:'PIXELS',value:24},letterSpacing:{unit:'PIXELS',value:0},textAlignHorizontal:'CENTER',textAutoResize:'WIDTH_AND_HEIGHT',height:24};
 const errors=[];h.validateDraftTypography(node,authored,candidate,msg=>errors.push(msg),'WIDTH_AND_HEIGHT');assert.deepEqual(errors,[]);
 h.validateDraftTypography(node,authored,candidate,msg=>errors.push(msg));assert(errors.some(e=>e.includes('auto-resize')));
});
