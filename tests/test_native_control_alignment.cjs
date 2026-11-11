const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../figma-bridge/direction_review.js'),'utf8');
function host(){const context=vm.createContext({DRAFT:{assets:{arrow:'cGlubmVk'}},__html__:'',figma:{showUI(){},ui:{postMessage(){}},base64Decode:value=>value,createImage:()=>({hash:'pinned'})}});vm.runInContext(source,context);return context;}
function fixture(placement='after'){
 const style={justifyContent:'space-between',paddingX:16,paddingY:13,icon:{asset:'arrow',placement,width:18,height:18,gap:12}};
 const parent={width:292,height:46,paddingLeft:16,paddingRight:16,paddingTop:13,paddingBottom:13,itemSpacing:12,primaryAxisAlignItems:'SPACE_BETWEEN',children:[]};
 const label={parent,type:'TEXT',textAutoResize:'WIDTH_AND_HEIGHT',layoutSizingHorizontal:'HUG',x:placement==='after'?16:178,y:13,width:98,height:20};
 const icon={parent,type:'RECTANGLE',x:placement==='after'?258:16,y:14,width:18,height:18,opacity:1,getPluginData:()=> 'arrow',fills:[{type:'IMAGE',imageHash:'pinned',scaleMode:'FIT'}]};
 parent.children=placement==='after'?[label,icon]:[icon,label];return {parent,label,icon,style};
}
test('actual Quiet Seat CTA geometry distributes surplus width beyond the CSS minimum gap',()=>{
 const h=host();for(const placement of ['before','after']){const f=fixture(placement),errors=[];h.validateDraftControlIcon(f.parent,f.style,f.label,m=>errors.push(m));assert.deepEqual(errors,[]);}
});
test('explicit alignment, endpoints, semantic order, vertical center, minimum gap and raster are enforced',()=>{
 const h=host();for(const mutate of [f=>f.parent.primaryAxisAlignItems='CENTER',f=>delete f.parent.primaryAxisAlignItems,f=>f.style.icon.placement='before',f=>f.label.x=20,f=>f.icon.x=120,f=>f.icon.y=8,f=>f.label.y=8,f=>f.parent.itemSpacing=0,f=>f.parent.paddingLeft=0,f=>f.parent.children=[f.label]]){
  const f=fixture(),errors=[];mutate(f);h.validateDraftControlIcon(f.parent,f.style,f.label,m=>errors.push(m));assert(errors.length);
 }
});
test('alignment is a strict optional enum and schema checks preserve legacy packets',()=>{
 const h=host(),style=fixture().style;delete style.justifyContent;const before=JSON.stringify(style);h.draftControlIcon(style,h.DRAFT.assets,'control');assert.equal(JSON.stringify(style),before);
 for(const value of [null,[],{},false,'SPACE_BETWEEN','left'])assert.throws(()=>h.draftControlIcon({...style,justifyContent:value},h.DRAFT.assets,'control'),/justifyContent/);
 for(const value of ['center','space-between'])h.draftControlIcon({...style,justifyContent:value},h.DRAFT.assets,'control');
 const textOnly={...style};delete textOnly.icon;
 h.draftControlIcon({...textOnly,justifyContent:'center'},h.DRAFT.assets,'control');
 assert.throws(()=>h.draftControlIcon({...textOnly,justifyContent:'space-between'},h.DRAFT.assets,'control'),/requires a label and icon/);
});
test('fixed instances retain alignment, authored minimum gap and side padding',()=>{
 const h=host(),f=fixture();f.parent.resize=function(w,height){this.width=w;this.height=height;};h.fitDraftControl(f.parent,[0,0,320,46]);
 assert.equal(f.parent.width,320);assert.equal(f.parent.primaryAxisAlignItems,'SPACE_BETWEEN');assert.equal(f.parent.itemSpacing,12);assert.equal(f.parent.paddingLeft,16);assert.equal(f.parent.paddingRight,16);
 assert.match(source,/primaryAxisAlignItems=style\.justifyContent==='space-between'\?'SPACE_BETWEEN':'CENTER'/);
 assert.match(source,/'layoutMode','primaryAxisAlignItems','primaryAxisSizingMode'/);
});
