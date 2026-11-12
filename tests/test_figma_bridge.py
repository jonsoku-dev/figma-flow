import hashlib
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direction_fixture import selected_direction

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('figma_bridge', ROOT / 'tools/figma_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def design():
    return {'version': 1, 'tokens': {
        'palette.blue': {'type': 'color', 'value': '#12345680'},
        'color.brand': {'type': 'color', 'value': '#12345680', 'alias': 'palette.blue'},
        'font.body': {'type': 'fontFamily', 'value': 'Arial'},
        'space.card': {'type': 'dimension', 'value': '1rem'},
        'type.body': {'type': 'dimension', 'value': '1rem', 'alias': 'space.card'}},
        'components': {'button': {'variants': {'primary': {'background': 'color.brand', 'padding': 'space.card',
                                                          'font-family': 'font.body', 'font-size': 'space.card'},
                                              'secondary': {'background': 'palette.blue', 'padding': 'space.card'}}},
                       'card': {'variants': {'default': {'background': 'palette.blue'}}}},
        'screens': [{'id': 'SCR-ONE', 'title': 'One', 'trace': ['REQ-ONE'], 'annotation': 'Screen declaration',
                     'elements': [{'id': 'title', 'kind': 'heading', 'text': '</script><script>not code</script>'},
                                  {'id': 'go', 'kind': 'component', 'component': 'button', 'variant': 'primary',
                                   'text': 'Go', 'target_screen': 'SCR-TWO', 'action_id': 'ACT-GO', 'annotation': 'Go declaration'}]},
                    {'id': 'SCR-TWO', 'title': 'Two', 'elements': [{'id': 'body', 'kind': 'text', 'text': 'Hello'}]}]}


def selected_graph(source):
    nodes = [{'id': screen['id'], 'type': 'screen', 'title': screen['title']} for screen in source['screens']]
    nodes += [{'id': component, 'type': 'component', 'title': component + ' component'} for component in source['components']]
    nodes += [{'id': 'ST-READY', 'type': 'state', 'title': 'Ready to continue'}]
    for screen in source['screens']:
        for element in screen['elements']:
            if element.get('action_id'):
                nodes.append({'id':element['action_id'], 'type':'action', 'title':'Continue reading', 'source_screen':screen['id'],
                              'annotation':{'control_id':element['id'], 'purpose':'Continue the reading journey.',
                                            'behavior':'Open the next reading screen.', 'result':'Display the selected destination.',
                                            'functional_states':['ST-READY']}})
    return {'version':1, 'nodes':nodes, 'edges':[], 'design_foundations':{'version':1, 'roles':[
        {'name':'Brand ink','kind':'color','token':'color/brand','alias':'palette/blue','value':'#12345680'},
        {'name':'Body size','kind':'typography','token':'type/body','alias':'space/card','value':'16px'},
        {'name':'Content space','kind':'spacing','token':'space/card','value':'16px'}],
        'palette':{'samples':[{'label':component+' example','component':component,'variant':next(iter(definition['variants'])),
                               'action':'ACT-GO','state':'ST-READY','useCases':['Continue reading']} for component,definition in source['components'].items()]}}}


def simulated_readback(source, digest, tag='one'):
    """Explicit local fixture; never a claim of an actual Figma export."""
    collection_id = tag + ':collection'
    native_screens = {screen['id']: tag + ':' + screen['id'] for screen in source['screens']}
    def bind(node, label, props):
        for prop, path in props.items():
            alias = {'type': 'VARIABLE_ALIAS', 'id': tag + ':variable:' + path}
            if prop == 'background':
                node['fills'] = [{'type': 'SOLID', 'boundVariables': {'color': alias}}]
            elif prop == 'padding':
                node.setdefault('boundVariables', {}).update({field: alias for field in ('paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft')})
            elif prop in ('font-family', 'font-size'):
                label.setdefault('boundVariables', {})['fontFamily' if prop == 'font-family' else 'fontSize'] = alias
    library = []
    for name, component in source['components'].items():
        for variant, props in component['variants'].items():
            identity = f'component:{name}/{variant}'
            label = {'id': tag + ':' + identity + '/label', 'semantic_id': identity + '/label', 'type': 'TEXT'}
            node = {'id': tag + ':' + identity, 'semantic_id': identity, 'type': 'COMPONENT', 'children': [label]}
            bind(node, label, props)
            library.append(node)
    grouped = []
    for name, definition in source['components'].items():
        variants = [node for node in library if node['semantic_id'].startswith('component:' + name + '/')]
        for node in variants:
            node['variantProperties'] = {'Variant': node['semantic_id'].split('/')[-1]}
        grouped.append({'id': tag + ':set:' + name, 'type': 'COMPONENT_SET',
                        'semantic_id': 'component-set:' + name, 'children': variants})
    library = grouped
    screens = []
    notes = bridge.handoff_contract(source)['required_annotations']
    for screen in source['screens']:
        elements = []
        for index, element in enumerate(screen['elements']):
            identity = element.get('id', f"{screen['id']}/element:{index}")
            node = {'id': tag + ':' + identity, 'semantic_id': identity, 'type': 'INSTANCE' if element['kind'] == 'component' else 'TEXT',
                    'name': element['text'][:80], 'reactions': []}
            if identity in notes:
                node['annotations'] = [{'label': notes[identity]}]
            if element['kind'] == 'component':
                node['main_component_id'] = tag + ':component:' + element['component'] + '/' + element['variant']
                node['children'] = [{'id': tag + ':' + identity + '/label', 'type': 'TEXT', 'semantic_id': identity + '/label', 'characters': element['text']}]
                bind(node, node['children'][0], source['components'][element['component']]['variants'][element['variant']])
            else:
                node['characters'] = element['text']
            if element.get('target_screen'):
                node['reactions'] = [{'trigger': {'type': 'ON_CLICK'}, 'actions': [{'type': 'NODE', 'navigation': 'NAVIGATE', 'destinationId': native_screens[element['target_screen']]}]}]
            elements.append(node)
        screens.append({'id': native_screens[screen['id']], 'semantic_id': screen['id'], 'name': f"{screen['id']} · {screen['title']}", 'type': 'FRAME', 'annotations': [{'label': notes[screen['id']]}], 'children': elements})
    variables = []
    for path, token in source['tokens'].items():
        kind, value = bridge.variable_value(token)
        variables.append({'id': tag + ':variable:' + path, 'name': path.replace('.', '/'), 'semantic_id': path, 'resolvedType': kind,
                          'variableCollectionId': collection_id, 'valuesByMode': {'default': {'type': 'VARIABLE_ALIAS', 'id': tag + ':variable:' + token['alias']} if token.get('alias') else value}})
    return {'format': 'figma-flow-readback-v1', 'fileKey': 'fixturefile', 'evidence': 'simulated-local-fixture-not-live',
            'pages': [{'id': tag + ':page', 'type': 'PAGE', 'name': 'Simulated import', 'source_sha256': digest,
                       'declared_metadata': {'collection_id': collection_id}, 'children': screens + library}],
            'collections': [{'id': collection_id, 'semantic_id': 'token-collection', 'defaultModeId': 'default', 'modes': [{'modeId': 'default', 'name': 'Mode 1'}]}],
            'variables': variables}


def readback_nodes(exported):
    nodes = []
    def walk(node):
        nodes.append(node)
        for child in node.get('children', []):
            walk(child)
    for page in exported['pages']:
        walk(page)
    return nodes


MOCK = r'''
const assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs');
let seq = 0, current, failure = false, annotationFailure = false;
const collections = [], variables = [], messages = [], styles = [];
class Node {
  constructor(type, name = type) { this.type = type; this.name = name; this.id = String(++seq); this.children = []; this.data = {}; this.width = 100; this.height = 30; this.reactions = []; this.boundVariables = {}; this._annotations = []; this.x=0;this.y=0;this.visible=true;this.fills=[];this.strokes=[];this.paddingTop=this.paddingRight=this.paddingBottom=this.paddingLeft=this.itemSpacing=this.cornerRadius=0; }
  get width(){return this.counterAxisSizingMode==='AUTO'&&this.children.length?Math.max(...this.children.map(c=>c.width))+(this.paddingLeft||0)+(this.paddingRight||0):this._width;}
  set width(value){this._width=value;}
  get height(){return this.primaryAxisSizingMode==='AUTO'&&this.children.length?this.children.reduce((sum,c)=>sum+c.height,0)+(this.children.length-1)*(this.itemSpacing||0)+(this.paddingTop||0)+(this.paddingBottom||0):this._height;}
  set height(value){this._height=value;}
  get x(){return this.parent?.layoutMode==='VERTICAL'?(this.parent.paddingLeft||0):(this._x||0);}
  set x(value){this._x=value;}
  get y(){return this.parent?.layoutMode==='VERTICAL'?this.parent.children.slice(0,this.parent.children.indexOf(this)).reduce((sum,c)=>sum+c.height+(this.parent.itemSpacing||0),this.parent.paddingTop||0):(this._y||0);}
  set y(value){this._y=value;}
  get absoluteBoundingBox(){const p=this.parent?.absoluteBoundingBox||{x:0,y:0};return {x:p.x+this.x,y:p.y+this.y,width:this.width,height:this.height};}
  get annotations() { return this._annotations; }
  set annotations(value) { if(annotationFailure) throw Error('annotations unavailable'); this._annotations=value; }
  setPluginData(key, value) { this.data[key] = value; }
  getPluginData(key) { return this.data[key] || ''; }
  appendChild(child) { if (child.parent) child.parent.children = child.parent.children.filter(n => n !== child); child.parent = this; this.children.push(child); }
  resize(w,h) { assert.ok(w > 0 && h > 0); this.width = w; this.height = h; }
  setBoundVariable(field, variable) { if(!variable){delete this.boundVariables[field];return;} assert.equal(typeof variable, 'object'); assert.ok(variable.id); this.boundVariables[field] = this.type === 'TEXT' && ['fontSize','fontFamily'].includes(field) ? [{type:'VARIABLE_ALIAS', id:variable.id}] : {type:'VARIABLE_ALIAS', id:variable.id}; }
  async setReactionsAsync(reactions) { if (failure) throw Error('reaction failure'); for (const reaction of reactions) { assert.equal(reaction.trigger.type, 'ON_CLICK'); assert.ok(reaction.actions[0].destinationId); assert.equal(reaction.actions[0].navigation, 'NAVIGATE'); } this.reactions = reactions; }
  async loadAsync() {}
  findAll(test) { return this.children.flatMap(child => [...(test(child)?[child]:[]), ...child.findAll(test)]); }
  getRangeAllFontNames(){return [this.fontName];}
  getRangeBoundVariable(start,end,field){const value=this.boundVariables[field];return Array.isArray(value)?value.every(item=>item.id===value[0]?.id)?value[0]||null:Symbol.for('mixed'):value||null;}
  setRangeHyperlink(start,end,link){assert.equal(start,0);assert.equal(end,this.characters.length);this.hyperlink=link;}
  getRangeHyperlink(start,end){assert.equal(start,0);assert.equal(end,this.characters.length);return this.hyperlink||null;}
  async setTextStyleIdAsync(id){this.textStyleId=id;}
  remove() { this.removed = true; if (this.parent) this.parent.children = this.parent.children.filter(n => n !== this); }
  findOne(test) { for (const child of this.children) { if (test(child)) return child; const found = child.findOne(test); if (found) return found; } return null; }
  addComponentProperty(name, type, defaultValue) {
    if (this.type !== 'COMPONENT' && this.type !== 'COMPONENT_SET') throw new Error('addComponentProperty requires a component');
    if (type !== 'TEXT' || typeof name !== 'string' || !name || typeof defaultValue !== 'string') throw new Error('TEXT property required');
    this.componentPropertyDefinitions = this.componentPropertyDefinitions || {};
    if (Object.values(this.componentPropertyDefinitions).some(item => item.name === name)) throw new Error('duplicate component property name: ' + name);
    const key = name + '#' + this.id + ':0';
    this.componentPropertyDefinitions[key] = {type, defaultValue, name};
    return key;
  }
  setProperties(values) {
    if (this.type !== 'INSTANCE' || !this._main) throw new Error('setProperties requires an instance');
    const owner = this._main.parent?.type === 'COMPONENT_SET' ? this._main.parent : this._main;
    this.componentProperties = {...(this.componentProperties || {})};
    for (const [key, value] of Object.entries(values)) {
      const definition = owner.componentPropertyDefinitions?.[key];
      if (definition?.type !== 'TEXT' || typeof value !== 'string') throw new Error('TEXT property value required: ' + key);
      this.componentProperties[key] = {type: 'TEXT', value};
      const labels = [];
      const walk = node => { if (node.componentPropertyReferences?.characters === key) labels.push(node); for (const child of node.children || []) walk(child); };
      walk(this);
      if (labels.length !== 1) throw new Error('label reference missing for ' + key);
      labels[0].characters = value;
    }
  }
  createInstance() {
    assert.equal(this.type, 'COMPONENT');
    function clone(source) { const copy = new Node(source.type); for (const key of ['data', 'boundVariables', 'fills', 'strokes', 'strokeWeight', 'characters', 'fontName', 'fontSize', 'textStyleId','layoutMode','primaryAxisSizingMode','counterAxisSizingMode','paddingTop','paddingRight','paddingBottom','paddingLeft','itemSpacing','cornerRadius','width','height','componentPropertyReferences']) if(source[key]) copy[key] = JSON.parse(JSON.stringify(source[key])); for (const child of source.children) copy.appendChild(clone(child)); return copy; }
    const instance = clone(this); instance.type = 'INSTANCE'; instance._main = this; instance.mainComponentId = this.id; instance.getMainComponentAsync = async () => this; return instance;
  }
}
const root = new Node('DOCUMENT'); current = new Node('PAGE', 'User work'); root.appendChild(current);
const userNode = new Node('FRAME', 'Keep me'); current.appendChild(userNode);
function create(type) { const node = new Node(type); current.appendChild(node); return node; }
const figma = { root, fileKey:'fixturefile', get currentPage() { return current; }, async setCurrentPageAsync(page) { current = page; },
  createPage() { const page = new Node('PAGE'); root.appendChild(page); return page; },
  createFrame: () => create('FRAME'), createComponent: () => create('COMPONENT'), createText: () => {const n=create('TEXT');n.fills=[{type:'SOLID',color:{r:0,g:0,b:0},opacity:1}];return n;},
  combineAsVariants(nodes,parent) { assert.ok(nodes.length>=1); assert.ok(nodes.every(node=>node.type==='COMPONENT' && node.name.startsWith('Variant='))); const set = new Node('COMPONENT_SET'); parent.appendChild(set); for(const node of nodes) { set.appendChild(node); node.variantProperties={Variant:node.name.split('=')[1]}; } return set; },
  async getNodeByIdAsync(id){return [root,...root.findAll(()=>true)].find(n=>n.id===id)||null;},
  createTextStyle(){const style=new Node('TEXT_STYLE');style.type='TEXT';Object.defineProperty(style,'fontSize',{get(){return this._fontSize;},set(value){this._fontSize=value;delete this.boundVariables.fontSize;}});styles.push(style);return style;},
  async getStyleByIdAsync(id){return styles.find(s=>s.id===id&&!s.removed)||null;},
  async loadFontAsync(name) { assert.ok(name.family && name.style); }, viewport:{ scrollAndZoomIntoView(){} },
  showUI(){}, ui:{postMessage(message){ messages.push(message); }},
  variables:{
    createVariableCollection(name) { const collection = new Node('COLLECTION', name); collection.defaultModeId = 'default'; collection.modes = [{modeId:'default',name:'Mode 1'}]; Object.defineProperty(collection,'variableIds',{get(){return variables.filter(v=>v.variableCollectionId===collection.id&&!v.removed).map(v=>v.id);}});collections.push(collection); return collection; },
    createVariable(name, collection, type) { assert.equal(collection.type, 'COLLECTION'); assert.ok(['COLOR','STRING','FLOAT','BOOLEAN'].includes(type)); const variable = new Node('VARIABLE', name); variable.resolvedType = type; variable.variableCollectionId = collection.id; variable.valuesByMode = {}; variable.setValueForMode = (mode, value) => {variable.valuesByMode[mode] = value;}; variable.resolveForConsumer=()=>{let value=variable.valuesByMode.default;const seen=new Set();while(value?.type==='VARIABLE_ALIAS'){assert(!seen.has(value.id));seen.add(value.id);value=variables.find(v=>v.id===value.id).valuesByMode.default;}return {resolvedType:type,value};};variables.push(variable); return variable; },
    createVariableAlias(variable) { assert.ok(variable.id); return {type:'VARIABLE_ALIAS', id:variable.id}; },
    setBoundVariableForPaint(paint, field, variable) { assert.equal(field, 'color'); return {...paint,opacity:1,boundVariables:{color:{type:'VARIABLE_ALIAS',id:variable.id}}}; },
    async getLocalVariableCollectionsAsync(){return collections.filter(x=>!x.removed);},
    async getLocalVariablesAsync(){return variables.filter(x=>!x.removed);},
    async getVariableByIdAsync(id){return variables.find(v=>v.id===id&&!v.removed)||null;},
    async getVariableCollectionByIdAsync(id){return collections.find(v=>v.id===id&&!v.removed)||null;}
  }
};
function load(path) { vm.runInNewContext(fs.readFileSync(path,'utf8'), {figma,__html__:'',console}); }
const meta = node => JSON.parse(node.getPluginData('figmaFlow') || '{}');
const imported = () => root.children.filter(node => meta(node).bridge === 1);
const sessionNonce = '0123456789abcdef0123456789abcdef';
const send = message => figma.ui.onmessage({...message, session_nonce:sessionNonce});
(async()=>{
  load(process.argv[2]);
  await send({type:'ready'});
  await send({type:'import'});
  assert.equal(imported().length, 1,JSON.stringify(messages)); assert.equal(variables.filter(x=>!x.removed).length, 5);
  assert.equal(root.children[0].children[0], userNode);
  const page = imported()[0], title = page.findOne(node=>meta(node).semantic_id === 'title');
  const componentSet = page.findOne(node=>node.type==='COMPONENT_SET');
  assert.equal(componentSet.name,'button'); assert.equal(componentSet.children.length,2);
  const single = page.findOne(node=>meta(node).semantic_id==='component:card/default');
  assert.equal(single.type,'COMPONENT'); assert.equal(single.parent.type,'COMPONENT_SET');
  assert.equal(title.characters, '</script><script>not code</script>');
  assert(Array.isArray(title.boundVariables.fontSize));
  const titleStyle = styles.find(style => style.id === title.textStyleId); assert(titleStyle);
  assert.equal(titleStyle.fontName.family,title.fontName.family);assert.equal(titleStyle.fontSize,title.fontSize);
  assert.equal(title.getRangeBoundVariable(0,title.characters.length,'fontSize').id,titleStyle.getRangeBoundVariable(0,0,'fontSize').id);
  await send({type:'export'});
  fs.writeFileSync(process.argv[4]+'.pristine',JSON.stringify(messages.findLast(m=>m.type==='readback').data));
  title.characters = 'Edited in Figma';
  const go = page.findOne(node=>meta(node).semantic_id === 'go');
  assert.equal(go.type,'INSTANCE'); assert.ok(go.reactions[0].actions[0].destinationId);
  assert.equal((await go.getMainComponentAsync()).parent,componentSet);
  assert.equal((await go.getMainComponentAsync()).name,'Variant=primary');
  assert.ok(go.annotations[0].label.includes('Continue the reading journey.')); assert.equal(meta(go).annotation_mode,'native');
  const brand = variables.find(node=>meta(node).semantic_id==='color.brand');
  assert.equal(brand.valuesByMode.default.type,'VARIABLE_ALIAS');
  assert.equal(variables.find(node=>meta(node).semantic_id==='palette.blue').valuesByMode.default.a,128/255);
  const spacing = variables.find(node=>meta(node).semantic_id==='space.card');
  assert.equal(spacing.valuesByMode.default,16);
  assert.equal(meta(spacing).source_value,'1rem'); assert.equal(meta(spacing).dimension_base_px,16);
  assert.ok(go.children[0]);
  assert.equal(go.children[0].fontName.family,'Arial');
  assert.ok(go.children[0].boundVariables.fontFamily);
  assert.ok(go.children[0].boundVariables.fontSize);
  await send({type:'import'}); assert.equal(imported().length,1); assert.equal(title.characters,'Edited in Figma');
  brand.valuesByMode.default = {r:1,g:0,b:0,a:1};
  await send({type:'export'});
  const readback = messages.findLast(message=>message.type==='readback').data;
  assert.equal(readback.scope,'active-generated-import-page');
  const savedTitle = readback.pages[0].children.flatMap(node=>node.children||[]).find(node=>node.semantic_id==='title');
  assert.equal(savedTitle.characters,'Edited in Figma');
  assert.ok(savedTitle.id); assert.ok(savedTitle.declared_metadata);
  const savedGo = readback.pages[0].children.flatMap(node=>node.children||[]).find(node=>node.semantic_id==='go');
  assert.ok(savedGo.annotations[0].label.includes('Continue the reading journey.')); assert.equal(savedGo.annotations_status,'observed');
  assert.equal(readback.variables.find(node=>node.semantic_id==='color.brand').valuesByMode.default.r,1);
  fs.writeFileSync(process.argv[4],JSON.stringify(readback));
  load(process.argv[3]); await send({type:'ready'}); await send({type:'import'}); assert.equal(imported().length,1);
  assert.match(messages.findLast(message=>message.type==='status').message,/different or incomplete/);
  await send({type:'import',fresh:true}); assert.equal(imported().length,2); assert.equal(title.characters,'Edited in Figma');
  annotationFailure=true;
  await send({type:'import',fresh:true}); assert.equal(imported().length,2);
  assert.match(messages.findLast(message=>message.type==='status').message,/annotations unavailable/);
  annotationFailure=false;
  await figma.setCurrentPageAsync(imported()[1]); await send({type:'import'});
  assert.equal(figma.currentPage,imported()[1]);
  const currentGo=imported()[1].findOne(node=>meta(node).semantic_id==='go');
  currentGo.annotations=[];
  await send({type:'import'});
  assert.match(messages.findLast(message=>message.type==='status').message,/Required native annotation missing/);
  assert.equal(imported().length,2);
  await send({type:'import',fresh:true}); assert.equal(imported().length,3);
  const latestGo=imported()[2].findOne(node=>meta(node).semantic_id==='go');
  latestGo.fills=[];
  await send({type:'import'});
  assert.match(messages.findLast(message=>message.type==='status').message,/Required native token binding missing/);
  const oldVariables = variables.filter(x=>!x.removed).length;
  failure=true; await send({type:'import',fresh:true});
  assert.equal(imported().length,3); assert.equal(variables.filter(x=>!x.removed).length,oldVariables);
  assert.equal(root.children[0].children[0],userNode);
  assert.match(messages.findLast(message=>message.type==='status').message,/reaction failure/);
  console.log('mocked Plugin API lifecycle passed; not live Figma evidence');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''

THREE_LABEL_SCRIPT = r'''
(async()=>{
  load(process.argv[2]);
  await send({type:'ready'});
  await send({type:'import'});
  assert.equal(imported().length, 1, JSON.stringify(messages.filter(message => message.type === 'status')));
  const page = imported()[0];
  const expected = {save:'저장', cancel:'취소', send:'보내기'};
  const instances = Object.keys(expected).map(id => page.findOne(node => meta(node).semantic_id === id));
  assert.ok(instances.every(node => node?.type === 'INSTANCE'));
  const mains = [];
  for (const instance of instances) mains.push(await instance.getMainComponentAsync());
  assert.equal(new Set(mains.map(node => node.id)).size, 1);
  const main = mains[0], set = main.parent;
  const mainLabel = main.children.find(child => child.type === 'TEXT');
  const key = mainLabel?.componentPropertyReferences?.characters;
  assert.equal(typeof key, 'string', 'TEXT property reference missing');
  const definition = set?.componentPropertyDefinitions?.[key];
  assert.equal(set?.type, 'COMPONENT_SET');
  assert.equal(definition?.type, 'TEXT');
  assert.notEqual(key, definition.name);
  assert.equal(meta(main).label_property_key, key);
  assert.equal(meta(set).label_property_key, key);
  assert.equal(mainLabel.characters, definition.defaultValue);
  assert.equal(Object.keys(set.componentPropertyDefinitions).length, 1);
  const secondary = set.children.find(node => node.type === 'COMPONENT' && node !== main);
  assert.equal(secondary.children.find(child => child.type === 'TEXT').componentPropertyReferences.characters, key);
  for (const instance of instances) {
    const id = meta(instance).semantic_id;
    const label = instance.findOne(child => child.type === 'TEXT');
    assert.equal(label.characters, expected[id]);
    assert.equal(label.componentPropertyReferences.characters, key);
    assert.equal(instance.componentProperties[key].type, 'TEXT');
    assert.equal(instance.componentProperties[key].value, expected[id]);
    assert.notEqual(label.characters, mainLabel.characters);
  }
  const palette = page.findOne(node => meta(node).semantic_id === 'palette:0:button/primary');
  const paletteLabel = palette.findOne(child => child.type === 'TEXT');
  assert.equal(palette.type, 'INSTANCE');
  assert.equal(await palette.getMainComponentAsync(), main);
  assert.equal(paletteLabel.characters, mainLabel.characters);
  assert.equal(paletteLabel.componentPropertyReferences.characters, key);
  const pageId = page.id, setId = set.id, mainId = main.id, instanceIds = instances.map(node => node.id);
  const edited = instances[0].findOne(child => child.type === 'TEXT');
  const editedSize = edited.fontSize + 4;
  edited.fontSize = editedSize;
  instances[0].opacity = 0.42;
  instances[0].setProperties({[key]: '사용자가 고친 문구'});
  await send({type:'import'});
  assert.equal(imported().length, 1, JSON.stringify(messages.filter(message => message.type === 'status').slice(-2)));
  assert.equal(page.id, pageId);
  assert.equal(set.id, setId);
  assert.equal(main.id, mainId);
  assert.deepEqual(instances.map(node => node.id), instanceIds);
  assert.equal(edited.characters, '사용자가 고친 문구');
  assert.equal(instances[0].componentProperties[key].value, '사용자가 고친 문구');
  assert.equal(edited.fontSize, editedSize);
  assert.equal(instances[0].opacity, 0.42);
  assert.equal(instances[1].findOne(child => child.type === 'TEXT').characters, '취소');
  assert.equal(instances[2].findOne(child => child.type === 'TEXT').characters, '보내기');
  console.log('three label property relationship observed in mock; not live Figma evidence');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''

THREE_LABEL_DIRECT_SCRIPT = r'''
(async()=>{
  Node.prototype.addComponentProperty = undefined;
  load(process.argv[2]);
  await send({type:'ready'});
  await send({type:'import'});
  assert.equal(imported().length, 1, JSON.stringify(messages.filter(message => message.type === 'status')));
  const page = imported()[0];
  const expected = {save:'저장', cancel:'취소', send:'보내기'};
  const instances = Object.keys(expected).map(id => page.findOne(node => meta(node).semantic_id === id));
  const mains = [];
  for (const instance of instances) mains.push(await instance.getMainComponentAsync());
  assert.equal(new Set(mains.map(node => node.id)).size, 1);
  const mainLabel = mains[0].children.find(child => child.type === 'TEXT');
  assert.equal(mainLabel.componentPropertyReferences, undefined);
  assert.equal(meta(mains[0]).label_property_key, undefined);
  assert.equal(meta(mains[0].parent).label_property_key, undefined);
  for (const instance of instances) {
    const label = instance.findOne(child => child.type === 'TEXT');
    assert.equal(label.characters, expected[meta(instance).semantic_id]);
    assert.equal(instance.componentProperties, undefined);
  }
  console.log('direct label fallback observed in mock; not live Figma evidence');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


class FigmaBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'resolved.json'
        self.source.write_text(json.dumps(design()))
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.admission = self.enterContext(selected_direction(self.root / 'directions', graph=selected_graph(design()), native_review=True))

    def build(self, name='build', digest=None):
        out = self.root / name
        result = bridge.compile_plugin(self.source, digest or self.digest, out, selection_path=self.admission.selection_path, product_graph=self.admission.product_graph)
        return out, result

    def test_generated_panel_embeds_theme_and_keeps_advanced_readback_collapsed(self):
        out, _ = self.build()
        html = (out / 'ui.html').read_text()
        self.assertNotIn('/* FIGMA_FLOW_PANEL_CSS */', html)
        self.assertIn('body.panel', html)
        self.assertIn('class="panel-shell masthead"', html)
        self.assertIn('class="workspace"', html)
        self.assertIn('별도 페이지로 새로 가져오기', html)
        self.assertIn('기존 가져오기는 그대로 유지됩니다.', html)
        self.assertIn('<details id="readback-details" class="details">', html)
        self.assertIn('<div id="readback-result" hidden>', html)
        self.assertLess(html.index('id="save"'), html.index('<details id="readback-details"'))
        self.assertIn('<h1 id="heading" data-i18n="import.title">디자인 가져오기</h1>', html)
        self.assertIn('aria-describedby="fresh-help"', html)
        self.assertIn('aria-atomic="true"', html)
        self.assertIn('id="sync-section" class="work-section" hidden', html)
        self.assertNotIn('<link', html)
        self.assertNotIn('https://fonts.', html)

    def test_pinned_compilation_is_offline_and_never_overwrites(self):
        out, result = self.build()
        self.assertFalse(result['figma_import_verified'])
        from workflow import Event
        self.assertEqual(result['native_admission']['event'], Event.HANDOFF_NATIVE.value)
        self.assertEqual(result['native_admission']['effect_status'], 'admitted-not-executed')
        payload = json.loads((out / 'reviewed-payload.json').read_text())
        self.assertEqual(payload['native_admission'], result['native_admission'])
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertEqual(manifest['name'], 'Figma Flow — Reviewed local design')
        self.assertEqual(manifest['networkAccess']['allowedDomains'], ['none'])
        self.assertEqual(manifest['documentAccess'], 'dynamic-page')
        self.assertNotIn('id', manifest)
        self.assertIn(self.digest, (out / 'code.js').read_text())
        with self.assertRaises(FileExistsError):
            self.build()
        with self.assertRaisesRegex(ValueError, 'Reviewed SHA256'):
            self.build('bad', '0' * 64)
        self.assertFalse((self.root / 'bad').exists())

    def test_creation_requires_current_selection_and_exact_graph_before_output(self):
        out = self.root / 'unselected'
        with self.assertRaisesRegex(ValueError, 'WAIT_SELECTION'):
            bridge.compile_plugin(self.source, self.digest, out)
        self.assertFalse(out.exists())
        fake = self.root / 'claimed.json'
        fake.write_text(json.dumps({'approved': True, 'candidate_id': 'A'}))
        with self.assertRaises(ValueError):
            bridge.compile_plugin(self.source, self.digest, out, selection_path=fake, product_graph=self.admission.product_graph)
        self.assertFalse(out.exists())
        wrong = self.root / 'other-graph.json'
        wrong.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'exact human-selected'):
            bridge.compile_plugin(self.source, self.digest, out, selection_path=self.admission.selection_path, product_graph=wrong)
        self.assertFalse(out.exists())
        graph = json.loads(self.admission.product_graph.read_text())
        graph['nodes'][0]['title'] = 'Unreviewed change'
        self.admission.product_graph.write_text(json.dumps(graph))
        with self.assertRaises(ValueError):
            bridge.compile_plugin(self.source, self.digest, out, selection_path=self.admission.selection_path, product_graph=self.admission.product_graph)
        self.assertFalse(out.exists())

    def test_game_asset_scope_requires_actual_batch_and_returned_asset_evidence(self):
        graph = selected_graph(design())
        graph['game_id'] = 'fixture-game'
        with selected_direction(self.root / 'game-directions', graph=graph, native_review=True) as selected:
            out = self.root / 'unadmitted-game'
            # Selection alone cannot unlock an installable authoring bundle.
            with self.assertRaisesRegex(ValueError, 'actual asset production'):
                bridge.compile_plugin(self.source, self.digest, out, selection_path=selected.selection_path, product_graph=selected.product_graph)
            self.assertFalse(out.exists())
            batch = self.root / 'claimed-batch.json'
            receipts = self.root / 'claimed-receipts.json'
            batch.write_text(json.dumps({'approved': True, 'batch_id': 'claim'}))
            receipts.write_text(json.dumps({'generated': True, 'assets': []}))
            with self.assertRaisesRegex(ValueError, 'Both actual frozen batch'):
                bridge.compile_plugin(self.source, self.digest, out, selection_path=selected.selection_path, product_graph=selected.product_graph, batch_path=batch)
            self.assertFalse(out.exists())
            # Self-asserted JSON is not returned managed generation evidence.
            with self.assertRaises(ValueError):
                bridge.compile_plugin(self.source, self.digest, out, selection_path=selected.selection_path, product_graph=selected.product_graph, batch_path=batch, asset_receipts=receipts)
            self.assertFalse(out.exists())

    def test_reviewed_source_cannot_override_selected_token_value(self):
        source = design()
        source['tokens']['palette.blue']['value'] = '#000000'
        source['tokens']['color.brand']['value'] = '#000000'
        self.source.write_text(json.dumps(source))
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'selected canonical role value'):
            bridge.compile_plugin(self.source, digest, self.root / 'wrong-color', selection_path=self.admission.selection_path, product_graph=self.admission.product_graph)
        self.assertFalse((self.root / 'wrong-color').exists())

    def test_draft_cli_is_inert_and_unselected_production_cli_never_writes(self):
        command = [sys.executable, str(ROOT / 'tools/figma_bridge.py'), '--input', str(self.source), '--reviewed-sha256', self.digest]
        denied = self.root / 'denied'
        result = subprocess.run(command + ['--out', str(denied)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WAIT_SELECTION', result.stderr)
        self.assertFalse(denied.exists())
        draft = self.root / 'draft'
        result = subprocess.run(command + ['--out', str(draft), '--draft-only'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p.name for p in draft.iterdir()}, {'draft-preview.json'})
        self.assertFalse(json.loads((draft / 'draft-preview.json').read_text())['native_verified'])

    @unittest.skipUnless(shutil.which('node'), 'Node required for packaged entry checks')
    def test_static_component_gets_selected_use_case_without_fake_action(self):
        source = design()
        source['screens'][1]['elements'].append({'id':'static-card','kind':'component','component':'card','variant':'default','text':'Reading contents'})
        graph = selected_graph(source)
        graph['design_foundations']['palette']['samples'][1].update(action='Static content; no action', state='Content available')
        self.source.write_text(json.dumps(source))
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with selected_direction(self.root / 'static-directions', graph=graph, native_review=True) as selected:
            out = self.root / 'static-build'
            bridge.compile_plugin(self.source, digest, out, selection_path=selected.selection_path, product_graph=selected.product_graph)
        expected = json.loads((out / 'expected-native-handoff.json').read_text())
        control = next(control for screen in expected['screens'] for control in screen['controls'] if control['key']=='static-card')
        self.assertTrue(control['static'])
        self.assertNotIn('action', control)
        self.assertIn('Continue reading', control['static_annotation'])
        smoke = MOCK.split('(async()=>{', 1)[0] + r"""
(async()=>{load(process.argv[2]);await send({type:'ready'});await send({type:'import'});assert.equal(imported().length,1,JSON.stringify(messages));await send({type:'export'});fs.writeFileSync(process.argv[3],JSON.stringify(messages.findLast(m=>m.type==='readback').data));})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        mock = self.root / 'static-smoke.cjs'; mock.write_text(smoke)
        exported = self.root / 'static-export.json'
        result = subprocess.run(['node', str(mock), str(out / 'code.js'), str(exported)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        from native_handoff import evaluate
        from design_foundations import validate_foundations
        data = json.loads(exported.read_text())
        report = evaluate(data, expected, data['pages'][0]['id'])
        self.assertTrue(report['passed'], report)
        foundations = validate_foundations(data, expected['design_foundations'])
        self.assertTrue(foundations['ok'], foundations)

    @unittest.skipUnless(shutil.which('node'), 'Node required for packaged entry checks')
    def test_three_shared_labels_use_one_returned_text_property(self):
        source = design()
        source['screens'] = [{
            'id': 'SCR-ONE', 'title': 'Actions', 'trace': ['REQ-ONE'], 'annotation': 'Three labels share one main',
            'elements': [
                {'id': 'title', 'kind': 'heading', 'text': 'Actions'},
                {'id': 'save', 'kind': 'component', 'component': 'button', 'variant': 'primary', 'text': '저장',
                 'action_id': 'ACT-GO', 'annotation': 'Save the current draft'},
                {'id': 'cancel', 'kind': 'component', 'component': 'button', 'variant': 'primary', 'text': '취소',
                 'annotation': 'Discard the draft'},
                {'id': 'send', 'kind': 'component', 'component': 'button', 'variant': 'primary', 'text': '보내기',
                 'annotation': 'Send the draft'},
            ],
        }]
        self.source.write_text(json.dumps(source))
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with selected_direction(self.root / 'label-directions', graph=selected_graph(source), native_review=True) as selected:
            out = self.root / 'label-build'
            bridge.compile_plugin(self.source, digest, out, selection_path=selected.selection_path, product_graph=selected.product_graph)
        mock = self.root / 'label-smoke.cjs'
        mock.write_text(MOCK.split('(async()=>{', 1)[0] + THREE_LABEL_SCRIPT)
        result = subprocess.run(['node', str(mock), str(out / 'code.js')], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('not live Figma evidence', result.stdout)
        direct = self.root / 'label-direct.cjs'
        direct.write_text(MOCK.split('(async()=>{', 1)[0] + THREE_LABEL_DIRECT_SCRIPT)
        fallback = subprocess.run(['node', str(direct), str(out / 'code.js')], capture_output=True, text=True, timeout=20)
        self.assertEqual(fallback.returncode, 0, fallback.stdout + fallback.stderr)
        self.assertIn('not live Figma evidence', fallback.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node required for packaged entry checks')
    def test_existing_sync_bundle_cannot_import_or_export_an_unpaired_page(self):
        out = self.root / 'sync-only'
        bridge.compile_plugin(self.source, self.digest, out, '1234', technical_existing=True, local_sync={
            'url':'http://localhost:43123/sync','preview_url':'http://localhost:43123/',
            'file_key':'fixturefile','page_id':'8:16','token':'fixture-token'})
        smoke = MOCK.split('(async()=>{', 1)[0] + r"""
(async()=>{load(process.argv[2]);await send({type:'ready'});await send({type:'import'});assert.equal(imported().length,0);assert.match(messages.findLast(m=>m.type==='status').message,/cannot author new UI/);await send({type:'export'});assert(!messages.some(m=>m.type==='readback'));assert.match(messages.findLast(m=>m.type==='status').message,/paired native file\/page/);assert.equal(root.children.length,1);})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        mock = self.root / 'sync-smoke.cjs'; mock.write_text(smoke)
        result = subprocess.run(['node', str(mock), str(out / 'code.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaisesRegex(ValueError, 'exact native file/page'):
            bridge.compile_plugin(self.source, self.digest, self.root / 'unsafe', technical_existing=True)

    def test_invalid_alias_targets_identity_and_values_are_rejected(self):
        invalid = []
        data = design(); data['tokens']['palette.blue']['alias'] = 'color.brand'; invalid.append(data)
        data = design(); data['tokens']['color.brand']['alias'] = 'missing'; invalid.append(data)
        data = design(); data['tokens']['palette.blue']['value'] = 1; invalid.append(data)
        data = design(); data['screens'][0]['elements'][1]['target_screen'] = 'missing'; invalid.append(data)
        data = design(); data['screens'][1]['elements'][0]['id'] = 'title'; invalid.append(data)
        data = design(); data['components']['button']['variants']['primary']['padding'] = []; invalid.append(data)
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                bridge.validate(candidate)

    @unittest.skipUnless(shutil.which('node'), 'Node required for syntax and offline Plugin API lifecycle checks')
    def test_generated_js_and_realistic_api_lifecycle_readback(self):
        out, _ = self.build()
        subprocess.run(['node', '--check', str(out / 'code.js')], check=True, capture_output=True, text=True)
        html = (out / 'ui.html').read_text()
        ui_script = self.root / 'ui.cjs'
        ui_script.write_text(html.split('<script>')[1].split('</script>')[0])
        subprocess.run(['node', '--check', str(ui_script)], check=True, capture_output=True, text=True)
        changed = design(); changed['screens'][0]['title'] = 'Reviewed revision 2'
        self.source.write_text(json.dumps(changed))
        other, _ = self.build('other', hashlib.sha256(self.source.read_bytes()).hexdigest())
        mock = self.root / 'mock.cjs'; mock.write_text(MOCK)
        readback = self.root / 'readback.json'
        result = subprocess.run(['node', str(mock), str(out / 'code.js'), str(other / 'code.js'), str(readback)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('not live Figma evidence', result.stdout)
        # This exercises the actual packaged entry/helper/read/evaluator chain under
        # modeled Plugin API behavior; it does not assert live Figma appearance.
        from design_foundations import validate_foundations
        from native_handoff import evaluate
        pristine = json.loads(Path(str(readback) + '.pristine').read_text())
        expected = json.loads((out / 'expected-native-handoff.json').read_text())
        foundations = validate_foundations(pristine, expected['design_foundations'])
        self.assertTrue(foundations['ok'], foundations)
        drift = copy.deepcopy(pristine)
        title = next(node for node in drift['nodes'] if node.get('semanticKey') == 'title')
        title['boundVariables'].pop('fontSize')
        title.pop('textStyleId', None)
        self.assertFalse(validate_foundations(drift, expected['design_foundations'])['ok'])
        native_report = evaluate(pristine, expected, pristine['pages'][0]['id'])
        self.assertTrue(native_report['passed'], native_report)
        self.assertTrue(all(not binding['key'].startswith('foundation-role:') for role in expected['design_foundations']['roles'] for binding in role['bindings']))

        self.source.write_text(json.dumps(design()))
        report = bridge.inspect_readback(readback, self.source)
        self.assertTrue(report['origin_stamp_match'])
        self.assertFalse(report['matches_supplied_source'])
        self.assertEqual(report['current_compared_state'], 'changed')
        self.assertEqual(next(token for token in report['import_checks'][0]['token_checks'] if token['token'] == 'color.brand')['status'], 'changed')
        self.assertEqual(next(element for element in report['import_checks'][0]['element_checks'] if element['semantic_id'] == 'title')['text_status'], 'changed')
        self.assertEqual(report['external_reaction_targets'], [])
        self.assertEqual(report['external_variable_references'], [])
        self.assertEqual(report['reactions'], 1)
        bad = json.loads(readback.read_text()); bad['pages'][0]['source_sha256'] = '0' * 64
        readback.write_text(json.dumps(bad))
        mismatch = bridge.inspect_readback(readback, self.source)
        self.assertFalse(mismatch['origin_stamp_match'])
        self.assertFalse(mismatch['matches_supplied_source'])

    def test_axis_padding_final_bindings_and_authored_native_values_match_order(self):
        source = design()
        source['tokens'].update({'space.x': {'type': 'dimension', 'value': '24px'},
                                 'space.y': {'type': 'dimension', 'value': '14px'},
                                 'space.gap': {'type': 'dimension', 'value': '6px'}})
        props = source['components']['button']['variants']['primary']
        props.update({'padding-inline': 'space.x', 'padding-block': 'space.y', 'gap': 'space.gap'})
        for uniform_last in (False, True):
            if uniform_last:
                props['padding'] = props.pop('padding')
            expected = bridge.expected_handoff(source)['screens'][0]['controls'][0]
            values = {binding['property']: binding['variable'] for binding in expected['token_bindings']}
            self.assertEqual(values['paddingLeft'], 'space/card' if uniform_last else 'space/x')
            self.assertEqual(values['paddingTop'], 'space/card' if uniform_last else 'space/y')
            self.assertEqual(values['itemSpacing'], 'space/gap')
            function = (ROOT / 'figma-bridge/code.js').read_text().split('function applyProps(', 1)[1].split('async function imports()', 1)[0]
            script = 'const assert=require("node:assert/strict"); const PAYLOAD=' + json.dumps({'variable_values': {path: bridge.variable_value(token) for path, token in source['tokens'].items()}}) + ';' + r"""
const figma={variables:{setBoundVariableForPaint:(paint,field,v)=>({...paint,boundVariables:{color:{id:v.id}}})}};
function node(){return {boundVariables:{},setBoundVariable(field,v){this.boundVariables[field]={id:v.id};}};}
const n=node(),label=node(),variables=new Map(Object.keys(PAYLOAD.variable_values).map(k=>[k,{id:k}]));
""" + 'function applyProps(' + function + '\napplyProps(n,label,' + json.dumps(props) + ',variables,new Set(),new Map([["font.body",{family:"Arial",style:"Regular"}]]));' + \
                f'assert.equal(n.paddingLeft,{16 if uniform_last else 24});assert.equal(n.paddingTop,{16 if uniform_last else 14});assert.equal(n.itemSpacing,6);'
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_typed_family_zero_roles_use_real_source_consumers_and_auxiliary_size(self):
        from design_foundations import validate_foundations
        source = design()
        source['tokens'].update({
            'font.source': {'type': 'fontFamily', 'value': 'Arial'},
            'font.body': {'type': 'fontFamily', 'value': 'Arial', 'alias': 'font.source'},
            'space.zero': {'type': 'dimension', 'value': '0px'},
            'space.flush': {'type': 'dimension', 'value': '0px', 'alias': 'space.zero'},
            'radius.zero': {'type': 'dimension', 'value': '0px'},
            'radius.flat': {'type': 'dimension', 'value': '0px', 'alias': 'radius.zero'}})
        source['components']['button']['variants']['primary'].update(padding='space.flush', radius='radius.flat')
        graph = selected_graph(source)
        graph['design_foundations']['roles'] = [r for r in graph['design_foundations']['roles'] if r['kind'] != 'typography'] + [
            {'name': 'Body family', 'kind': 'typography', 'token': 'font/body', 'alias': 'font/source', 'value': 'Source family',
             'native': {'type': 'STRING', 'value': 'Arial', 'bindings': [{'key': 'draft-only', 'field': 'fontFamily'}]}},
            {'name': 'Flush padding', 'kind': 'spacing', 'token': 'space/flush', 'alias': 'space/zero', 'value': 'No padding',
             'native': {'type': 'FLOAT', 'value': 0, 'bindings': [{'key': 'draft-only', 'field': 'paddingTop'}]}},
            {'name': 'Flat corners', 'kind': 'radius', 'token': 'radius/flat', 'alias': 'radius/zero', 'value': 'Square corners',
             'native': {'type': 'FLOAT', 'value': 0, 'bindings': [{'key': 'draft-only', 'field': 'cornerRadius'}]}}]
        self.source.write_text(json.dumps(source))
        with selected_direction(self.root / 'typed-directions', graph=graph, native_review=True) as selected:
            output = self.root / 'typed-build'
            bridge.compile_plugin(self.source, hashlib.sha256(self.source.read_bytes()).hexdigest(), output,
                                  selection_path=selected.selection_path, product_graph=selected.product_graph)
        payload = json.loads((output / 'reviewed-payload.json').read_text())
        self.assertEqual(payload['foundations']['auxiliary_type']['token'], 'space/card')
        family = next(r for r in payload['foundations']['roles'] if r['name'] == 'Body family')
        self.assertEqual(family['native_type'], 'STRING')
        self.assertEqual(family['bindings'], [{'key': 'go/label', 'field': 'fontFamily'}])
        self.assertNotIn('styleName', family)
        script = self.root / 'typed-mock.cjs'
        script.write_text(MOCK.split('(async()=>{', 1)[0] + r"""
(async()=>{load(process.argv[2]);await send({type:'ready'});await send({type:'import'});
assert.equal(imported().length,1,JSON.stringify(messages));await send({type:'export'});
const data=messages.findLast(m=>m.type==='readback').data;fs.writeFileSync(process.argv[3],JSON.stringify(data));
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
        readback = self.root / 'typed-native.json'
        result = subprocess.run(['node', str(script), str(output / 'code.js'), str(readback)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        native = json.loads(readback.read_text())
        report = validate_foundations(native, payload['expected_native_handoff']['design_foundations'])
        self.assertTrue(report['ok'], report)
        actual = next(n for n in native['nodes'] if n.get('semanticKey') == 'go/label')
        self.assertEqual(actual['fontName']['family'], 'Arial')
        self.assertTrue(actual['boundVariables']['fontFamily'])
        invalid = copy.deepcopy(source)
        invalid['components']['button']['variants']['primary'].pop('font-size')
        with self.assertRaisesRegex(ValueError, 'Actual used positive numeric source font-size'):
            bridge.production_contract(invalid, json.loads(selected.product_graph.read_text()))

    def test_native_handoff_rejects_metadata_only_unused_components_and_unbound_tokens(self):
        path = self.root / 'handoff.json'
        def report(exported):
            path.write_text(json.dumps(exported))
            return bridge.inspect_readback(path, self.source)
        exported = simulated_readback(design(), self.digest)
        self.assertTrue(report(exported)['matches_supplied_source'])
        exported['pages'][0]['children'][0]['annotations'] = []
        self.assertFalse(report(exported)['matches_supplied_source'])
        self.assertEqual(bridge.inspect_readback(path)['native_handoff_coverage'], 'partial-historical-inspection')
        exported = simulated_readback(design(), self.digest)
        go = exported['pages'][0]['children'][0]['children'][1]
        go['main_component_id'] = 'dummy-unused-component'
        self.assertFalse(report(exported)['matches_supplied_source'])
        exported = simulated_readback(design(), self.digest)
        go = exported['pages'][0]['children'][0]['children'][1]
        go['fills'] = []
        self.assertFalse(report(exported)['matches_supplied_source'])
        local = design()
        local['screens'][0]['elements'] = local['screens'][0]['elements'][:1]
        self.assertTrue(bridge.validate(local))  # Offline/manual artifacts remain supported.
        self.source.write_text(json.dumps(local))
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertFalse(report(simulated_readback(local, digest))['matches_supplied_source'])

    def test_expected_contract_invokes_shared_native_gate_without_metadata_success(self):
        exported = self.root / 'export.json'
        exported.write_text(json.dumps(simulated_readback(design(), self.digest)))
        contract = self.root / 'expected.json'
        contract.write_text('{}')
        report = bridge.inspect_readback(exported, self.source, contract)
        self.assertFalse(report['matches_supplied_source'])
        self.assertFalse(report['native_handoff']['passed'])
        self.assertTrue(report['native_handoff']['errors'])

    def test_plugin_id_and_readback_are_validated(self):
        with self.assertRaisesRegex(ValueError, 'numeric ID'):
            bridge.compile_plugin(self.source, self.digest, self.root / 'bad', 'invented-id', selection_path=self.admission.selection_path, product_graph=self.admission.product_graph)
        path = self.root / 'readback.json'
        path.write_text(json.dumps({'format': 'figma-flow-readback-v1', 'pages': [{'id': '1', 'children': [{'id': '1'}]}], 'variables': []}))
        with self.assertRaisesRegex(ValueError, 'unique current native'):
            bridge.inspect_readback(path)

    def test_dimension_conversion_matches_fixed_svg_rem_base(self):
        for source, expected in [('0px', 0), ('1.25rem', 20), ('0.5px', 0.5)]:
            self.assertEqual(bridge.variable_value({'type': 'dimension', 'value': source}), ('FLOAT', expected))

    def test_simulated_current_tokens_and_navigation_override_matching_origin_stamp(self):
        exported = simulated_readback(design(), self.digest)
        path = self.root / 'simulated-export.json'
        path.write_text(json.dumps(exported))
        self.assertTrue(bridge.inspect_readback(path, self.source)['matches_supplied_source'])
        exported['variables'][0]['valuesByMode']['default'] = {'r': 1, 'g': 0, 'b': 0, 'a': 1}
        go = exported['pages'][0]['children'][0]['children'][1]
        go['reactions'][0]['actions'][0]['destinationId'] = exported['pages'][0]['children'][0]['id']
        go['children'][0]['characters'] = 'Changed label'
        path.write_text(json.dumps(exported))
        report = bridge.inspect_readback(path, self.source)
        self.assertTrue(report['origin_stamp_match'])
        self.assertFalse(report['matches_supplied_source'])
        checked = report['import_checks'][0]
        self.assertEqual(checked['status'], 'changed')
        brand = next(token for token in checked['token_checks'] if token['token'] == 'color.brand')
        self.assertEqual(brand['modes']['default']['alias_status'], 'match')
        self.assertEqual(brand['modes']['default']['value_status'], 'changed')
        navigation = next(element for element in checked['element_checks'] if element['semantic_id'] == 'go')
        self.assertEqual(navigation['navigation_status'], 'changed')
        self.assertEqual(navigation['text_status'], 'changed')
        self.assertNotEqual(navigation['current_native_targets'], navigation['expected_native_targets'])
        self.assertIn('does not authenticate', report['evidence'])

    def test_simulated_imports_never_union_screen_coverage_across_pages_or_hashes(self):
        first = simulated_readback(design(), self.digest, 'first')
        second = simulated_readback(design(), '0' * 64, 'second')
        first['pages'][0]['children'] = first['pages'][0]['children'][:1] + first['pages'][0]['children'][2:]
        second['pages'][0]['children'] = second['pages'][0]['children'][1:]
        fixture = dict(first, pages=first['pages'] + second['pages'], variables=first['variables'] + second['variables'],
                       collections=first['collections'] + second['collections'])
        path = self.root / 'simulated-multiple-imports.json'
        path.write_text(json.dumps(fixture))
        report = bridge.inspect_readback(path, self.source)
        self.assertTrue(report['origin_stamp_match'])
        self.assertFalse(report['matches_supplied_source'])
        self.assertEqual(report['import_checks'][0]['missing_screens'], ['SCR-TWO'])
        self.assertEqual(report['import_checks'][1]['status'], 'source-mismatch')
        fixture['pages'][1]['source_sha256'] = self.digest
        path.write_text(json.dumps(fixture))
        report = bridge.inspect_readback(path, self.source)
        self.assertFalse(report['matches_supplied_source'])
        self.assertEqual(report['import_checks'][0]['missing_screens'], ['SCR-TWO'])
        self.assertEqual(report['import_checks'][1]['missing_screens'], ['SCR-ONE'])

    def test_simulated_missing_tokens_and_unsupported_alias_resolution_are_reported(self):
        exported = simulated_readback(design(), self.digest)
        exported['variables'] = [variable for variable in exported['variables'] if variable['semantic_id'] != 'space.card']
        brand = next(variable for variable in exported['variables'] if variable['semantic_id'] == 'color.brand')
        brand['valuesByMode']['default'] = {'type': 'VARIABLE_ALIAS', 'id': 'not-exported'}
        path = self.root / 'simulated-missing-token.json'; path.write_text(json.dumps(exported))
        report = bridge.inspect_readback(path, self.source)
        checked = {token['token']: token for token in report['import_checks'][0]['token_checks']}
        self.assertEqual(checked['space.card']['status'], 'missing')
        self.assertEqual(checked['color.brand']['modes']['default']['value_status'], 'unsupported')
        self.assertFalse(report['matches_supplied_source'])

    def test_binding_drift_and_strict_cli(self):
        exported = simulated_readback(design(), self.digest)
        path = self.root / 'bindings.json'
        def run(*args):
            return subprocess.run([sys.executable, str(ROOT / 'tools/figma_bridge.py'), '--inspect-readback', str(path),
                                   '--input', str(self.source), *args], capture_output=True, text=True)
        path.write_text(json.dumps(exported))
        self.assertEqual(run('--require-match').returncode, 0)
        go = exported['pages'][0]['children'][0]['children'][1]
        go['fills'][0]['boundVariables']['color']['id'] = 'one:variable:palette.blue'
        del go['boundVariables']['paddingTop']
        path.write_text(json.dumps(exported))
        report = bridge.inspect_readback(path, self.source)
        checks = {(check['semantic_id'], check['property']): check['status'] for check in report['import_checks'][0]['binding_checks']}
        self.assertEqual(checks[('go', 'fills.color')], 'changed')
        self.assertEqual(checks[('go', 'boundVariables.paddingTop')], 'missing')
        self.assertFalse(report['matches_supplied_source'])
        self.assertEqual(run().returncode, 0)
        self.assertEqual(run('--require-match').returncode, 1)
        self.assertNotEqual(subprocess.run([sys.executable, str(ROOT / 'tools/figma_bridge.py'), '--inspect-readback', str(path), '--require-match'], capture_output=True).returncode, 0)

    def test_paired_manifest_name_distinguishes_current_native_build(self):
        out = self.root / 'paired'
        bridge.compile_plugin(self.source, self.digest, out, '123456789', local_sync={
            'url': 'http://localhost:43123/sync', 'preview_url': 'http://localhost:43123/',
            'file_key': 'test-file', 'page_id': '8:16', 'token': 'test-token'}, technical_existing=True)
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertEqual(manifest['name'], 'Figma Flow · 앱에 반영 0.9')
        self.assertEqual(manifest['networkAccess']['allowedDomains'], ['none'])
        self.assertEqual(manifest['networkAccess']['devAllowedDomains'], ['http://localhost:43123', 'http://localhost:43123'])

    def test_single_text_binding_arrays_match_but_mixed_and_wrong_aliases_do_not(self):
        exported = simulated_readback(design(), self.digest)
        go = exported['pages'][0]['children'][0]['children'][1]
        label = go['children'][0]
        library = next(node for node in readback_nodes(exported) if node.get('semantic_id') == 'component:button/primary')
        for target in (label, library['children'][0]):
            for field in ('fontSize', 'fontFamily'):
                target['boundVariables'][field] = [target['boundVariables'][field]]
        path = self.root / 'text-arrays.json'
        def inspect():
            path.write_text(json.dumps(exported))
            return bridge.inspect_readback(path, self.source)
        self.assertTrue(inspect()['matches_supplied_source'])
        def status(field):
            checks = inspect()['import_checks'][0]['binding_checks']
            return next(check['status'] for check in checks if check['semantic_id'] == 'go/label' and check['property'] == 'boundVariables.' + field)
        for field, token in (('fontSize', 'space.card'), ('fontFamily', 'font.body')):
            alias = {'type': 'VARIABLE_ALIAS', 'id': 'one:variable:' + token}
            label['boundVariables'][field] = [dict(alias), dict(alias)]
            self.assertEqual(status(field), 'unsupported')
            label['boundVariables'][field] = []
            self.assertEqual(status(field), 'unsupported')
            label['boundVariables'][field] = [{'type': 'VARIABLE_ALIAS', 'id': 'one:variable:palette.blue'}]
            self.assertEqual(status(field), 'changed')
            label['boundVariables'][field] = [None]
            self.assertEqual(status(field), 'missing')
            label['boundVariables'][field] = dict(alias)
            self.assertEqual(status(field), 'match')
            label['boundVariables'][field] = [dict(alias)]
        label['type'] = 'FRAME'
        self.assertEqual(status('fontSize'), 'changed')

    def test_native_radius_expansion_and_override(self):
        source = design()
        source['components']['button']['variants']['primary']['radius'] = 'space.card'
        self.source.write_text(json.dumps(source))
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        exported = simulated_readback(source, digest)
        go = exported['pages'][0]['children'][0]['children'][1]
        corners = ('topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius')
        alias = {'type': 'VARIABLE_ALIAS', 'id': 'one:variable:space.card'}
        go['boundVariables'].update({corner: dict(alias) for corner in corners})
        library = next(node for node in readback_nodes(exported) if node.get('semantic_id') == 'component:button/primary')
        library['boundVariables'].update({corner: dict(alias) for corner in corners})
        path = self.root / 'radius.json'
        def status():
            path.write_text(json.dumps(exported))
            checks = bridge.inspect_readback(path, self.source)['import_checks'][0]['binding_checks']
            return next(check['status'] for check in checks if check['semantic_id'] == 'go' and check['property'] == 'boundVariables.cornerRadius')
        self.assertEqual(status(), 'match')
        go['boundVariables']['cornerRadius'] = dict(alias)
        go['boundVariables']['topLeftRadius']['id'] = 'one:variable:palette.blue'
        self.assertEqual(status(), 'changed')
        del go['boundVariables']['topLeftRadius']
        self.assertEqual(status(), 'missing')

    def test_current_review_design_compiler_output_is_accepted(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/design_system.py'), '--input',
                                 str(ROOT / 'examples/review-design/design.json'), '--out', str(self.root / 'design')],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.root / 'design/resolved.json'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        output = self.root / 'example-plugin'
        # A fixture numeric ID proves serialization only, not a Figma-assigned identity.
        with self.assertRaises(ValueError):
            bridge.compile_plugin(source, digest, output, '123456789')
        self.assertFalse(output.exists())
        summary = bridge.compile_plugin(source, digest, output, '123456789', draft_only=True)
        self.assertEqual(summary['status'], 'draft-only-no-native-authoring')
        self.assertFalse((output / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
