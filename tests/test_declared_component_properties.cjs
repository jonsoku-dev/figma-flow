const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const root = path.join(__dirname, '..');
const runtime = fs.readFileSync(path.join(root, 'figma-bridge/code.js'), 'utf8');
const source = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/declared-component-properties.json')));
const payload = JSON.parse(execFileSync('python3', ['-B', '-c', 'import json,sys;sys.path.insert(0,"tools");from design_system import compile_design;print(json.dumps(compile_design(json.load(sys.stdin))))'], {cwd:root,input:JSON.stringify(source),encoding:'utf8'}));

function fixture() {
  let sequence = 0;
  class Node {
    constructor(type) { Object.assign(this, {id:String(++sequence),key:'key-'+sequence,type,children:[],data:{},componentPropertyDefinitions:{},visible:true}); }
    appendChild(node) {if(node.parent)node.parent.children=node.parent.children.filter(child=>child!==node);node.parent=this;this.children.push(node);}
    setPluginData(key,value) {this.data[key]=value;}
    getPluginData(key) {return this.data[key] || '';}
    addComponentProperty(name,type,defaultValue,options) {const key=name+'#'+this.id;this.componentPropertyDefinitions[key]={type,defaultValue,...options};return key;}
    createInstance() {
      const clone = node => {
        const result=new Node(node===this?'INSTANCE':node.type);
        result.characters=node.characters;result.name=node.name;result.visible=node.visible;
        result.componentPropertyReferences={...node.componentPropertyReferences};result.data={...node.data};
        if (node.main) result.main=node.main;
        for (const child of node.children) result.appendChild(clone(child));
        return result;
      };
      const instance=clone(this);instance.main=this;
      const owner=this.parent?.type==='COMPONENT_SET'?this.parent:this;
      instance.componentProperties=Object.fromEntries(Object.entries(owner.componentPropertyDefinitions).map(([key,prop])=>[key,{type:prop.type,value:prop.defaultValue}]));
      return instance;
    }
    async getMainComponentAsync() {return this.main;}
    setProperties(values) {
      for (const [key,value] of Object.entries(values)) {
        if (!this.componentProperties[key]) throw Error('unknown native key');
        this.componentProperties[key].value=value;
        const apply=node=>{
          for (const [field,reference] of Object.entries(node.componentPropertyReferences || {})) if (reference===key) {
            if(field==='mainComponent') {const main=[...context.authored.components.values()].find(main=>main.id===value);node.main=main;node.children=main.createInstance().children;}
            else node[field]=value;
          }
          for(const child of node.children) apply(child);
        };
        for(const child of this.children) apply(child);
      }
    }
  }
  const library = new Node('FRAME');
  const figma = {showUI(){},ui:{},createComponent:()=>new Node('COMPONENT'),combineAsVariants(mains,parent){const set=new Node('COMPONENT_SET');parent.appendChild(set);for(const main of mains)set.appendChild(main);return set;}};
  const context=vm.createContext({figma,__html__:'',PAYLOAD:structuredClone(payload),library,variables:new Map(),warnings:new Set(),fonts:new Map()});
  vm.runInContext(runtime,context);
  Object.assign(context,{layout(){},text(value){return Object.assign(new Node('TEXT'),{characters:value});},applyProps(){},decorate:async()=>{}});
  return {context,library,figma,Node};
}

async function author(context) {
  const start=runtime.indexOf('    const components = new Map();');
  const end=runtime.indexOf('    layoutFoundationSets(library, componentSets);',start);
  context.authored=await vm.runInContext('(async()=>{'+runtime.slice(start,end)+';return {components,componentSets};})()',context);
  return context.authored;
}

test('normal importer binds real BOOLEAN and swap slots, local preferred keys, defaults and overrides',async()=>{
  const {context}=fixture();
  vm.runInContext('validateDeclaredComponentProperties(PAYLOAD)',context);
  const {components}=await author(context);
  const button=components.get(JSON.stringify(['button','default']));
  const owner=button.parent, keys=JSON.parse(button.data.figmaFlow || button.getPluginData(vm.runInContext('KEY',context)) || '{}').declared_property_keys;
  assert(keys);assert.equal(Object.keys(owner.componentPropertyDefinitions).length,4,'TEXT + 3 explicit properties');
  const slot=button.children.find(node=>node.name==='slot:symbol');
  assert.equal(slot.type,'INSTANCE');
  assert.equal(slot.main.id,components.get(JSON.stringify(['symbol','circle'])).id);
  assert.equal(slot.componentPropertyReferences.mainComponent,keys.Symbol);
  assert.equal(slot.componentPropertyReferences.visible,keys.ShowSymbol);
  assert.equal(button.children[0].componentPropertyReferences.visible,keys.ShowLabel);
  assert.equal(owner.componentPropertyDefinitions[keys.ShowSymbol].defaultValue,true);
  assert.equal(owner.componentPropertyDefinitions[keys.Symbol].defaultValue,slot.main.id);
  assert.deepEqual(JSON.parse(JSON.stringify(owner.componentPropertyDefinitions[keys.Symbol].preferredValues)),['circle','square'].map(variant=>({type:'COMPONENT',key:components.get(JSON.stringify(['symbol',variant])).key})));
  const defaults=button.createInstance();
  assert.equal(defaults.componentProperties[keys.ShowSymbol].value,true);
  assert.equal(defaults.children[1].main.id,slot.main.id);
  context.instance=button.createInstance();context.main=button;context.element=payload.screens[0].elements[1];context.components=components;
  await vm.runInContext('applyDeclaredInstanceProperties(instance,main,element,components)',context);
  assert.equal(context.instance.children[0].visible,false);
  assert.equal(context.instance.children[1].main.id,components.get(JSON.stringify(['symbol','square'])).id);
  assert.equal(button.children[0].visible,true,'instance overrides preserve main default');
  context.instance=button.createInstance();context.element=payload.screens[0].elements[2];
  await vm.runInContext('applyDeclaredInstanceProperties(instance,main,element,components)',context);
  assert.equal(context.instance.children[1].visible,false);
});

test('preflight rejects unknown refs, invalid types, recursive swaps and unbound overrides',()=>{
  for(const mutate of [
    p=>p.components.button.properties.ShowLabel.default_value='false',
    p=>p.components.button.properties.ShowLabel.target='absent',
    p=>p.components.button.properties.Symbol.default_value.variant='absent',
    p=>p.components.button.properties.Symbol.preferred_values[0].component='absent',
    p=>p.components.button.properties.Symbol.default_value={component:'button',variant:'default'},
    p=>p.screens[0].elements[1].property_values.Unknown=true,
    p=>p.screens[0].elements[1].property_values.ShowLabel=0,
    p=>p.screens[0].elements[1].property_values.Symbol={component:'button',variant:'default'},
  ]) {
    const {context,library}=fixture();mutate(context.PAYLOAD);
    assert.throws(()=>vm.runInContext('validateDeclaredComponentProperties(PAYLOAD)',context),/Declared component properties/);
    assert.equal(library.children.length,0,'rejected before native authoring');
  }
});

test('missing native property API fails visibly rather than silently dropping declarations',async()=>{
  const {context,figma}=fixture();
  const original=figma.combineAsVariants;
  figma.combineAsVariants=(...args)=>{const set=original(...args);set.addComponentProperty=undefined;return set;};
  await assert.rejects(author(context),/Native declared component property API unavailable/);
});


test('snapshots verify declared live structure, preserve valid reused overrides, and reject drift',async()=>{
  const {context,library,Node}=fixture();
  const {components}=await author(context);
  const page=new Node('PAGE');page.appendChild(library);
  for(const screen of payload.screens) {
    const frame=new Node('FRAME');page.appendChild(frame);
    for(const [index,element] of screen.elements.entries()) {
      const main=components.get(JSON.stringify([element.component,element.variant]));
      const instance=main.createInstance();frame.appendChild(instance);
      context.instance=instance;context.main=main;context.element=element;context.components=components;
      await vm.runInContext('applyDeclaredInstanceProperties(instance,main,element,components)',context);
      context.identity=element.id || `${screen.id}/element:${index}`;
      vm.runInContext('metadata(instance,identity); metadata(instance.children[0],identity+"/label")',context);
    }
  }
  // Foundation-palette copies must not inherit the main slot semantic IDs.
  context.paletteSample=components.get(JSON.stringify(['button','default'])).createInstance();
  page.appendChild(context.paletteSample);
  vm.runInContext('metadata(paletteSample,"foundation-sample");metadata(paletteSample.children[0],"foundation-sample/label");markImportedInstanceSlots(paletteSample,"foundation-sample")',context);
  assert.equal(context.paletteSample.children[1].getPluginData('semanticKey'),'foundation-sample/slot:symbol');
  context.page=page;
  const observed=await vm.runInContext('snapshot(page)',context);
  context.observed=observed;
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed)',context);
  if(process.env.FIGMA_DECLARED_READBACK_PATH) fs.writeFileSync(process.env.FIGMA_DECLARED_READBACK_PATH,JSON.stringify(observed));
  const button=observed.children[0].children.find(node=>node.type==='COMPONENT_SET'&&node.name==='button').children[0];
  const keys=button.declared_metadata.declared_property_keys;
  const edited=observed.children[1].children[0];
  edited.componentProperties[keys.ShowLabel].value=false;edited.children[0].visible=false;
  assert.throws(()=>vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed)',context),/source override/);
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed,{preserveInstanceOverrides:true})',context);
  const before=JSON.stringify(observed);
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed,{preserveInstanceOverrides:true})',context);
  assert.equal(JSON.stringify(observed),before,'reuse verification is read-only');
  edited.children[0].visible=true;
  assert.throws(()=>vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed,{preserveInstanceOverrides:true})',context),/actual visibility/);
  edited.children[0].visible=false;
  const symbol=button.children[1];
  symbol.componentPropertyReferences.mainComponent='wrong#1';
  assert.throws(()=>vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed,{preserveInstanceOverrides:true})',context),/layer reference/);
});

test('normal import rolls back only newly created page, styles and variables on property API failure',async()=>{
  const {context,figma,Node}=fixture();
  const created={pages:[],styles:[],variables:[],collections:[]};
  const previous=new Node('PAGE');figma.currentPage=previous;
  Node.prototype.remove=function(){this.removed=true;if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);};
  Node.prototype.setBoundVariable=function(field,variable){this.boundVariables={...this.boundVariables,[field]:{type:'VARIABLE_ALIAS',id:variable.id}};};
  Node.prototype.setTextStyleIdAsync=async function(id){this.textStyleId=id;};
  figma.loadFontAsync=async()=>{};figma.setCurrentPageAsync=async page=>{figma.currentPage=page;};
  figma.createPage=()=>{const page=new Node('PAGE');created.pages.push(page);return page;};
  figma.createFrame=()=>new Node('FRAME');
  figma.createTextStyle=()=>{const style=new Node('TEXT_STYLE');created.styles.push(style);return style;};
  figma.variables={
    createVariableCollection(){const node=new Node('VARIABLE_COLLECTION');node.defaultModeId='default';created.collections.push(node);return node;},
    createVariable(){const node=new Node('VARIABLE');node.setValueForMode=()=>{};created.variables.push(node);return node;},
    createVariableAlias:variable=>({type:'VARIABLE_ALIAS',id:variable.id}),
    setBoundVariableForPaint:(paint,field,variable)=>({...paint,boundVariables:{[field]:{type:'VARIABLE_ALIAS',id:variable.id}}}),
  };
  const original=figma.combineAsVariants;
  figma.combineAsVariants=(...args)=>{const set=original(...args);set.addComponentProperty=undefined;return set;};
  context.PX_PER_REM=16;
  context.PAYLOAD.source_sha256='0'.repeat(64);context.PAYLOAD.selected_direction={};
  context.PAYLOAD.variable_values={'color.ink':['COLOR',{r:0,g:0,b:0,a:1}],'color.surface':['COLOR',{r:1,g:1,b:1,a:1}],'space.gap':['FLOAT',8],'font.body':['STRING','Arial'],'font.size':['FLOAT',16]};
  const type={kind:'typography',token:'font/size',native_type:'FLOAT',native_value:16};
  const space={kind:'spacing',token:'space/gap',native_type:'FLOAT',native_value:8};
  context.PAYLOAD.foundations={roles:[type,space,{kind:'color',token:'color/ink',name:'Ink',native_type:'COLOR',native_value:{r:0,g:0,b:0,a:1}}],auxiliary_type:type,auxiliary_space:space};
  Object.assign(context,{validateProductionColors(){},imports:async()=>[],text(value){return Object.assign(new Node('TEXT'),{characters:value,fontName:{family:'Arial',style:'Regular'}});}});
  await assert.rejects(vm.runInContext('importDesign(false)',context),/Native declared component property API unavailable/);
  assert.equal(figma.currentPage,previous);assert.equal(previous.removed,undefined);
  for(const values of Object.values(created)) {assert(values.length);assert(values.every(node=>node.removed),'only attempted import objects are removed');}
});

test('unnamed elements receive unique fallback slot identities and semanticKey assignments',async()=>{
  const {context,library,Node}=fixture();
  for(const screen of context.PAYLOAD.screens)for(const element of screen.elements)delete element.id;
  const {components}=await author(context);
  const page=new Node('PAGE');page.appendChild(library);
  for(const screen of context.PAYLOAD.screens) {
    const frame=new Node('FRAME');page.appendChild(frame);
    for(const [index,element] of screen.elements.entries()) {
      context.main=components.get(JSON.stringify([element.component,element.variant]));
      context.instance=context.main.createInstance();frame.appendChild(context.instance);
      context.element={...element,id:`${screen.id}/element:${index}`};context.components=components;
      await vm.runInContext('(async()=>{await applyDeclaredInstanceProperties(instance,main,element,components);metadata(instance,element.id);metadata(instance.children[0],element.id+"/label");})()',context);
      const slot=context.instance.children[1];
      assert.equal(slot.getPluginData('semanticKey'),`${screen.id}/element:${index}/slot:symbol`);
      assert.equal(slot.children[0].getPluginData('semanticKey'),`${screen.id}/element:${index}/slot:symbol/child:0`);
    }
  }
  context.page=page;
  context.observed=await vm.runInContext('snapshot(page)',context);
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD,observed)',context);
});
