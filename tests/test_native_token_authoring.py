"""Native-token authoring regressions using API-shaped mocks; never live evidence."""
from pathlib import Path
import subprocess
import unittest

BRIDGE=Path(__file__).resolve().parents[1]/'figma-bridge'

PRELUDE=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const env={figma:{showUI(){},ui:{postMessage(){}}},__html__:'',DRAFT:{candidates:[]}};vm.createContext(env);
for(const path of process.argv.slice(1))vm.runInContext(fs.readFileSync(path,'utf8'),env);
function world(){
 const collections=[],variables=new Map(),styles=new Map();let seq=0;
 const result={collections,variables,styles,rangeWrites:0,nodeFontWrites:0,styleAttaches:0};
 const alias=id=>({type:'VARIABLE_ALIAS',id});
 const resolve=variable=>{const v=variable.valuesByMode.m1;return v&&v.type==='VARIABLE_ALIAS'?resolve(variables.get(v.id)):v;};
 result.fig={async loadFontAsync(){},async getStyleByIdAsync(id){return styles.get(id);},variables:{
  async getLocalVariableCollectionsAsync(){return collections;},async getLocalVariablesAsync(){return [...variables.values()];},
  createVariableCollection(name){const data={};const c={id:'col'+(++seq),name,modes:[{modeId:'m1',name:'Default'}],defaultModeId:'m1',variableIds:[],getPluginData:k=>data[k]||'',setPluginData:(k,v)=>data[k]=v,remove(){collections.splice(collections.indexOf(c),1);}};collections.push(c);return c;},
  createVariable(name,c,type){const v={id:'var'+(++seq),name,resolvedType:type,variableCollectionId:c.id,valuesByMode:{},setValueForMode(mode,value){this.valuesByMode[mode]=value;},resolveForConsumer(){return {resolvedType:type,value:resolve(v)};},remove(){variables.delete(v.id);c.variableIds.splice(c.variableIds.indexOf(v.id),1);}};variables.set(v.id,v);c.variableIds.push(v.id);return v;},
  createVariableAlias:v=>alias(v.id),setBoundVariableForPaint:(paint,field,v)=>({...paint,boundVariables:{[field]:alias(v.id)}})
 }};
 function base(id,key,type='FRAME'){const data={semanticKey:key};const n={id,name:key,type,children:[],parent:null,getPluginData:k=>data[k]||'',setPluginData:(k,v)=>data[k]=v,async loadAsync(){},findAll(){return this.children.flatMap(c=>[c,...c.findAll()]);}};return n;}
 result.node=base;result.attach=(p,n)=>{p.children.push(n);n.parent=p;return n;};result.page=base('page','page','PAGE');
 result.style=(id='s1')=>{const s={id,type:'TEXT',name:'Owned typography',boundVariables:{},setBoundVariable(field,v){if(v)this.boundVariables[field]=alias(v.id);else delete this.boundVariables[field];}};Object.defineProperty(s,'fontName',{get(){return {family:s.boundVariables.fontFamily?resolve(variables.get(s.boundVariables.fontFamily.id)):'Gowun Dodum',style:'Regular'};}});Object.defineProperty(s,'fontSize',{get(){return s.boundVariables.fontSize?resolve(variables.get(s.boundVariables.fontSize.id)):17;}});styles.set(id,s);return s;};
 result.text=(id,key,styleId='s1',main=null)=>{const n=base(id,key,'TEXT');n.characters='Saltline';n._styleId=styleId;n.direct={};n.main=main;
  Object.defineProperty(n,'textStyleId',{get(){return n.main?n.main.textStyleId:n._styleId;}});
  const currentStyle=()=>styles.get(n.textStyleId);
  const binding=field=>n.main?n.main.boundVariables[field]:(n.direct[field]||currentStyle()?.boundVariables[field]);
  Object.defineProperty(n,'boundVariables',{get(){const out={};for(const field of ['fontFamily','fontSize']){const v=binding(field);if(v)out[field]=Array.isArray(v)?v:[v];}return out;}});
  Object.defineProperty(n,'fontName',{get(){const v=binding('fontFamily');const one=Array.isArray(v)?v[0]:v;return {family:one?resolve(variables.get(one.id)):'Gowun Dodum',style:'Regular'};}});
  Object.defineProperty(n,'fontSize',{get(){if(n.forceSize!==undefined)return n.forceSize;const v=binding('fontSize'),one=Array.isArray(v)?v[0]:v;return one?resolve(variables.get(one.id)):17;},set(v){n.literalSize=v;}});
  n.getRangeAllFontNames=()=>[n.fontName];n.getRangeBoundVariable=(a,b,field)=>{const v=binding(field);return Array.isArray(v)?v[0]:v||null;};
  n.setRangeBoundVariable=(a,b,field,v)=>{if(n.main)throw Error('instance font setter forbidden');result.rangeWrites++;if(v)n.direct[field]=alias(v.id);else delete n.direct[field];n._styleId='';};
  n.setBoundVariable=(field,v)=>{if(n.main)throw Error('instance node setter forbidden');result.nodeFontWrites++;if(v)n.direct[field]=alias(v.id);else delete n.direct[field];};
  n.setTextStyleIdAsync=async id=>{if(n.main)throw Error('instance style setter forbidden');result.styleAttaches++;n._styleId=id;n.direct={};};return n;
 };
 result.frame=(id,key,type='FRAME',main=null)=>{const n=base(id,key,type);n.local={};n.literal={paddingLeft:24,paddingRight:24,paddingTop:14,paddingBottom:14,itemSpacing:0,cornerRadius:0,topLeftRadius:0,topRightRadius:0,bottomLeftRadius:0,bottomRightRadius:0};
  Object.defineProperty(n,'boundVariables',{get(){return main?main.boundVariables:n.local;}});
  for(const field of Object.keys(n.literal))Object.defineProperty(n,field,{get(){const a=n.boundVariables[field];return a?resolve(variables.get(a.id)):n.literal[field];},set(value){n.literal[field]=value;}});
  n.setBoundVariable=(field,v)=>{if(main)throw Error('instance frame setter forbidden');const fields=field==='cornerRadius'?['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius']:[field];for(const f of fields){if(v)n.local[f]=alias(v.id);else delete n.local[f];}};return n;
 };
 result.find=name=>[...variables.values()].find(v=>v.name===name);return result;
}
const typed=[{name:'a/font/body',type:'STRING',value:'Gowun Dodum'},{name:'a/type/body',type:'STRING',alias:'a/font/body'},{name:'a/size/body',type:'FLOAT',value:17},{name:'a/type/body-size',type:'FLOAT',alias:'a/size/body'}];
const contract=bindings=>({sourceHash:'owned-source',collectionName:'Owned draft roles',tokens:typed,bindings,strictValues:true,bindTextStyles:true,ownedTextStyleIds:['s1']});
(async()=>{
'''


class NativeTokenAuthoringTests(unittest.TestCase):
    def run_js(self,body):
        script=PRELUDE+body+'\n})().catch(error=>{console.error(error);process.exit(1)});'
        result=subprocess.run(['node','-e',script,str(BRIDGE/'semantic_tokens.js'),str(BRIDGE/'native_semantic_read.js'),str(BRIDGE/'direction_review.js')],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_owned_style_keeps_family_size_and_inherited_instance_bindings(self):
        self.run_js(r'''
const w=world(),style=w.style(),main=w.attach(w.page,w.node('main','main','COMPONENT')),label=w.attach(main,w.text('label','main.label')),instance=w.attach(w.page,w.node('instance','screen.control','INSTANCE')),copy=w.attach(instance,w.text('copy','main.label','s1',label));
const result=await env.ensureSemanticTokens(w.fig,w.page,contract([{key:'copy',field:'fontFamily',token:'a/type/body'},{key:'label',field:'fontSize',token:'a/type/body-size'},{key:'copy',field:'fontSize',token:'a/type/body-size'},{key:'label',field:'fontFamily',token:'a/type/body'}]));
assert.equal(label.textStyleId,'s1');assert.equal(copy.textStyleId,'s1');assert.equal(label.getRangeBoundVariable(0,8,'fontFamily').id,w.find('a/type/body').id);assert.equal(copy.getRangeBoundVariable(0,8,'fontSize').id,w.find('a/type/body-size').id);assert.equal(style.boundVariables.fontFamily.id,w.find('a/type/body').id);assert.equal(style.boundVariables.fontSize.id,w.find('a/type/body-size').id);assert.equal(w.rangeWrites,0);assert.equal(w.nodeFontWrites,0);assert(w.styleAttaches>=2);assert.equal(w.collections[0].modes.length,1);assert.equal(w.find('a/type/body').valuesByMode.m1.id,w.find('a/font/body').id);assert(result.bindings.filter(b=>b.inherited).length===2);
''')

    def test_zero_radius_separate_spacing_and_direct_values_are_bound(self):
        self.run_js(r'''
const w=world(),main=w.attach(w.page,w.frame('main','main')),instance=w.attach(w.page,w.frame('instance','screen.control','INSTANCE',main));
const tokens=[{name:'a/space/x',type:'FLOAT',value:24},{name:'a/scale/y',type:'FLOAT',value:14},{name:'a/space/y',type:'FLOAT',alias:'a/scale/y'},{name:'a/radius/base',type:'FLOAT',value:0},{name:'a/radius/control',type:'FLOAT',alias:'a/radius/base'}];
const bindings=[];for(const node of [instance,main])for(const [field,token]of [['paddingLeft','a/space/x'],['paddingRight','a/space/x'],['paddingTop','a/space/y'],['paddingBottom','a/space/y'],['cornerRadius','a/radius/control']])bindings.push({key:node.id,field,token});
await env.ensureSemanticTokens(w.fig,w.page,{sourceHash:'source',tokens,bindings,strictValues:true});
assert.equal(w.find('a/space/x').valuesByMode.m1,24);assert.equal(w.variables.size,5);assert.equal(instance.paddingLeft,24);assert.equal(instance.paddingTop,14);for(const key of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])assert.equal(instance.boundVariables[key].id,w.find('a/radius/control').id);assert.equal(instance.cornerRadius,0);
''')

    def test_immutable_values_reject_edits_without_changing_legacy_replay(self):
        self.run_js(r'''
const w=world();w.style();const label=w.attach(w.page,w.text('label','label'));const base=contract([{key:'label',field:'fontSize',token:'a/type/body-size'}]);await env.ensureSemanticTokens(w.fig,w.page,base);w.find('a/size/body').setValueForMode('m1',19);
await env.ensureSemanticTokens(w.fig,w.page,{...base,strictValues:false});assert.equal(label.fontSize,19);await assert.rejects(()=>env.ensureSemanticTokens(w.fig,w.page,base),/immutable native value differs/);assert.equal(w.find('a/size/body').valuesByMode.m1,19);assert.equal(label.fontSize,19);
''')

    def test_strict_prebound_consumer_mismatch_and_unowned_styles_are_rejected(self):
        self.run_js(r'''
const w=world();w.style();const label=w.attach(w.page,w.text('label','label'));const base=contract([{key:'label',field:'fontSize',token:'a/type/body-size'}]);await env.ensureSemanticTokens(w.fig,w.page,base);label.forceSize=18;await assert.rejects(()=>env.ensureSemanticTokens(w.fig,w.page,base),/immutable bound consumer differs/);assert.equal(label.forceSize,18);
const other=world();other.style();other.attach(other.page,other.text('label','label'));await assert.rejects(()=>env.ensureSemanticTokens(other.fig,other.page,{...base,ownedTextStyleIds:[]}),/outside the new owned transaction/);assert.equal(other.variables.size,0);assert.equal(other.styleAttaches,0);
''')

    def test_binding_cannot_change_family_or_overwrite_a_different_style_role(self):
        self.run_js(r'''
const w=world();w.style();w.attach(w.page,w.text('label','label'));await assert.rejects(()=>env.ensureSemanticTokens(w.fig,w.page,{...contract([{key:'label',field:'fontFamily',token:'family'}]),tokens:[{name:'family',type:'STRING',value:'Inter'}]}),/binding would change appearance/);assert.equal(w.variables.size,0);assert.equal(w.collections.length,0);assert.equal(w.rangeWrites,0);
const v=world();v.style();v.attach(v.page,v.text('one','one'));v.attach(v.page,v.text('two','two'));await assert.rejects(()=>env.ensureSemanticTokens(v.fig,v.page,{...contract([{key:'one',field:'fontFamily',token:'first'},{key:'two',field:'fontFamily',token:'second'}]),tokens:[{name:'first',type:'STRING',value:'Gowun Dodum'},{name:'second',type:'STRING',value:'Gowun Dodum'}]}),/existing different binding/);assert.equal(v.variables.size,0);assert.equal(v.styles.get('s1').boundVariables.fontFamily,undefined);
''')

    def test_canonical_plan_preserves_aliases_direct_values_zero_and_unique_paths(self):
        self.run_js(r'''
const w=world(),main=w.attach(w.page,w.node('main','a.desktop.component.Primary','COMPONENT')),label=w.attach(main,w.node('label','a.desktop.component.Primary.label','TEXT')),copy=w.attach(w.page,w.node('copy','review.palette.a.component','INSTANCE'));const cloned=w.attach(copy,w.node('cloned','a.desktop.component.Primary.label','TEXT'));copy.setPluginData('semanticComponent',JSON.stringify({key:'review.palette.a.component',childKeys:[{path:[0],key:'review.palette.a.component.label'}]}));
const c={id:'a',foundationBindings:[{token:'type/body',alias:'font/body',type:'STRING',value:'Gowun Dodum',bindings:[{key:'a.desktop.component.Primary.label',field:'fontFamily'}]},{token:'radius/control',alias:null,type:'FLOAT',value:0,bindings:[{key:'a.desktop.component.Primary',field:'cornerRadius'}]}]};const defs=[];env.declareDraftFoundations(c,(...args)=>env.declareDraftToken(defs,...args));assert(defs.some(t=>t.name==='a/type/body'&&t.alias==='a/font/body'));assert(defs.some(t=>t.name==='a/radius/control'&&t.value===0&&!('alias'in t)));assert.equal(env.draftFoundationName(c,'a/type/body'),'a/type/body');
const jobs=[{key:'main',field:'cornerRadius',token:'review/primitive/0'}];const resolved=env.applyDraftFoundations(w.page,[c],jobs);assert.equal(resolved.find(r=>r.field==='fontFamily').nodeId,'label');assert(!jobs.some(j=>j.key==='cloned'));assert.equal(jobs.find(j=>j.key==='main').token,'a/radius/control');
env.declareDraftToken(defs,'a/font/body','STRING','Gowun Dodum');assert.throws(()=>env.declareDraftToken(defs,'a/font/body','STRING','Inter'),/Conflicting/);assert.throws(()=>env.declareDraftToken(defs,'a/type/body','STRING',null,'review/adaptor'),/Conflicting/);
''')


if __name__=='__main__':unittest.main()
