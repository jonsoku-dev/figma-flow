const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');

const source=fs.readFileSync(path.join(__dirname,'../figma-bridge/native_provision.js'),'utf8');
const plan=()=>({schema:'figma-flow-native-edit-plan-v1',file_key:'file',page_id:'1:1',provision:{
 schema:'figma-flow-starter-cta-provision-v1',graph_sha256:'a'.repeat(64),token_source_sha256:'b'.repeat(64),readback_sha256:'c'.repeat(64),
 frame_key:'little-hands/booking-cta/starter-frame',main_key:'bookingCTA',instance_keys:['reserve-preview','reserve-login'],
 seed_collection_name:'Little Hands · CTA SSOT seed',seed_variable_name:'starter/little-hands/booking-cta-seed',canonical_variable_name:'ssot/little-hands/color/action/primary',
 background_color:{r:0.55,g:0.24,b:0.15},text_color:{r:1,g:0.99,b:0.97},
 labels:{main:'예약하기','reserve-preview':'예약하기','reserve-login':'예약하기'},page_roots:[],position:{x:196,y:0}
}});

function world(extra={}){
 let next=1,failRead=false,afterRead=null;
 const objects=new Map(),collections=new Map(),variables=new Map();
 class Node{
  constructor(type,name=''){this.id=`2:${next++}`;this.type=type;this.name=name;this.parent=null;this.children=[];this.data={};this.x=0;this.y=0;this.width=80;this.height=40;this.visible=true;objects.set(this.id,this)}
  appendChild(node){if(node.parent)throw Error('already parented');node.parent=this;this.children.push(node)}
  remove(){if(this.parent)this.parent.children.splice(this.parent.children.indexOf(this),1);this.parent=null;objects.delete(this.id)}
  setPluginData(key,value){this.data[key]=value}
  getPluginData(key){return this.data[key]||''}
  resize(width,height){this.width=width;this.height=height}
  get absoluteBoundingBox(){return {x:this.x+(this.parent?.absoluteBoundingBox?.x||0),y:this.y+(this.parent?.absoluteBoundingBox?.y||0),width:this.width,height:this.height}}
  findAll(predicate){const rows=[];const walk=node=>{for(const child of node.children){if(predicate(child))rows.push(child);walk(child)}};walk(this);return rows}
  findOne(predicate){return this.findAll(predicate)[0]||null}
 }
 class Frame extends Node{constructor(){super('FRAME');this.layoutMode='NONE';this.clipsContent=false;this.fills=[]} }
 class Component extends Frame{constructor(){super();this.type='COMPONENT';this.remote=false;this.cornerRadius=0;this.paddingLeft=0;this.paddingRight=0;this.paddingTop=0;this.paddingBottom=0;this.itemSpacing=0}
  createInstance(){const i=new Node('INSTANCE',this.name);i.mainComponent=this;i.getMainComponentAsync=async()=>this;i.fills=JSON.parse(JSON.stringify(this.fills));i.findOne=predicate=>{const found=i.findAll(predicate);return found[0]||null};for(const child of this.children){if(child.type==='TEXT'){const t=new Node('TEXT',child.name);for(const key of ['characters','fontName','fontSize','fills'])t[key]=JSON.parse(JSON.stringify(child[key]));i.appendChild(t)}}return i}
 }
 class Text extends Node{constructor(){super('TEXT');this.characters='';this.fontName={family:'Inter',style:'Regular'};this.fontSize=14;this.fills=[]}}
 const page=new Node('PAGE','Pinned page');page.id='1:1';objects.delete('2:1');objects.set(page.id,page);page.loadAsync=async()=>{};
 const sibling=new Frame();sibling.id='1:2';objects.delete('2:2');objects.set(sibling.id,sibling);sibling.name='Existing content';sibling.x=0;sibling.y=0;sibling.resize(100,100);page.appendChild(sibling);
 const rootRow={id:sibling.id,type:sibling.type,name:sibling.name,semanticKey:null,x:sibling.x,y:sibling.y,width:sibling.width,height:sibling.height,absoluteBoundingBox:sibling.absoluteBoundingBox};
 const dataFor=node=>{const row={id:node.id,parentId:node.parent?.id||null,type:node.type,name:node.name,semanticKey:node.getPluginData('semanticKey')||null,x:node.x,y:node.y,width:node.width,height:node.height,absoluteBoundingBox:node.absoluteBoundingBox};if(node.type==='COMPONENT'||node.type==='INSTANCE'){row.fills=JSON.parse(JSON.stringify(node.fills));row.mainComponentId=node.mainComponent?.id||null}if(node.type==='TEXT'){row.characters=node.characters;row.fontName=node.fontName;row.fontSize=node.fontSize;row.fills=node.fills}return row};
 const figma={fileKey:'file',currentPage:page,async getNodeByIdAsync(id){return objects.get(id)||null},async loadFontAsync(){},createFrame(){return new Frame()},createComponent(){return new Component()},createText(){return new Text()},
  variables:{createVariableCollection(name){const collection={id:`collection:${next++}`,name,defaultModeId:'mode',variableIds:[],data:{},setPluginData(key,value){this.data[key]=value},getPluginData(key){return this.data[key]||''},remove(){for(const id of this.variableIds)variables.delete(id);collections.delete(this.id)}};collections.set(collection.id,collection);return collection},
   createVariable(name,collection,type){const variable={id:`variable:${next++}`,name,variableCollectionId:collection.id,resolvedType:type,valuesByMode:{},setValueForMode(mode,value){this.valuesByMode[mode]=value},remove(){variables.delete(this.id);collection.variableIds=collection.variableIds.filter(id=>id!==this.id)}};variables.set(variable.id,variable);collection.variableIds.push(variable.id);return variable},
   setBoundVariableForPaint(paint,field,variable){return {...paint,boundVariables:{[field]:{type:'VARIABLE_ALIAS',id:variable.id}}}},
   async getVariableByIdAsync(id){return variables.get(id)||null},async getVariableCollectionByIdAsync(id){return collections.get(id)||null}}
 };
 const actualPlan=plan();actualPlan.provision.page_roots=[rootRow];
 const context=vm.createContext({figma,NATIVE_PROVISION_SCHEMA:undefined,NATIVE_PROVISION_SHA256:'plan',NATIVE_EDIT_SHA256:'plan',NATIVE_EDIT_PLAN_SCHEMA:actualPlan.schema,
  nativeEditValidatePlan:p=>{if(!p.provision)throw Error('provision required')},nativeEditScope:(f,p)=>{if(f.fileKey!==p.file_key||f.currentPage.id!==p.page_id)throw Error('scope changed')},
  nativeEditEqual:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
  nativeEditDiscovery:async()=>{afterRead?.();afterRead=null;if(failRead)throw Error('getter failure');return {schema:'figma-flow-graph-native-discovery-v1',fileKey:'file',pageId:'1:1',nodes:page.findAll(()=>true).map(dataFor),variables:[...variables.values()],collections:[...collections.values()]}}
 });
 vm.runInContext(source,context);
 return {figma,page,sibling,objects,collections,variables,plan:actualPlan,run:(p=actualPlan,op='apply')=>context.nativeProvisionRun(figma,p,op),failGetter(){failRead=true},afterRead(callback){afterRead=callback},Frame};
}

test('creates one owned main and two instances on the existing page, then reuses them idempotently',async()=>{
 const h=world(),first=await h.run();
 assert.equal(h.page.children.length,2);assert.equal(first.native_edit.changed,6);assert.equal(first.native_edit.idempotent,false);
 const frame=h.page.children.find(node=>node.name.includes('Booking CTA'));assert(frame);assert.equal(frame.parent,h.page);
 assert.equal(frame.getPluginData('semanticKey'),'little-hands/booking-cta/starter-frame');
 const main=frame.children.find(node=>node.type==='COMPONENT');assert.equal(main.getPluginData('semanticKey'),'bookingCTA');
 const instances=frame.children.filter(node=>node.type==='INSTANCE');assert.deepEqual(instances.map(node=>node.getPluginData('semanticKey')).sort(),['reserve-login','reserve-preview']);
 assert.equal(main.fills[0].boundVariables.color.type,'VARIABLE_ALIAS');assert.equal(h.collections.size,1);assert.equal(h.page.children.filter(node=>node.type==='PAGE').length,0);
 const second=await h.run();assert.equal(second.native_edit.changed,0);assert.equal(second.native_edit.idempotent,true);assert.equal(h.page.children.length,2);assert.equal(h.collections.size,1);
});

test('preserves a manually added disjoint page sibling on a repeated run',async()=>{
 const h=world();await h.run();const manual=new h.Frame();manual.name='Manual layer';manual.x=700;manual.y=0;manual.resize(80,60);h.page.appendChild(manual);
 const result=await h.run();assert.equal(result.native_edit.idempotent,true);assert.equal(manual.parent,h.page);assert.equal(h.page.children.length,3);
});

test('rejects stale page geometry and pre-existing semantic key collisions before creating anything',async()=>{
 const stale=world();stale.sibling.x=10;await assert.rejects(()=>stale.run(),/sibling changed/);assert.equal(stale.page.children.length,1);assert.equal(stale.collections.size,0);
 const collision=world();const other=new collision.Frame();other.setPluginData('semanticKey','bookingCTA');collision.page.appendChild(other);
 await assert.rejects(()=>collision.run(),/key collision/);assert.equal(collision.page.children.length,2);assert.equal(collision.collections.size,0);
});

test('rolls back only unchanged owned creation when the final getter fails',async()=>{
 const h=world();h.failGetter();await assert.rejects(()=>h.run(),error=>{assert.equal(error.native_rollback,'created CTA frame and seed collection removed after failed getter');return true});
 assert.equal(h.page.children.length,1);assert.equal(h.page.children[0],h.sibling);assert.equal(h.collections.size,0);assert.equal(h.variables.size,0);
});

test('keeps the created frame when an external manual child appears before failed readback',async()=>{
 const h=world();h.failGetter();h.afterRead(()=>{const frame=h.page.children.find(node=>node.getPluginData('semanticKey')==='little-hands/booking-cta/starter-frame');const manual=new h.Frame();manual.name='User addition';frame.appendChild(manual)});
 await assert.rejects(()=>h.run(),error=>{assert.equal(error.rollback_conflicts.length,1);return true});
 const frame=h.page.children.find(node=>node.getPluginData('semanticKey')==='little-hands/booking-cta/starter-frame');assert(frame);assert(frame.children.some(node=>node.name==='User addition'));assert.equal(h.collections.size,1);
});
