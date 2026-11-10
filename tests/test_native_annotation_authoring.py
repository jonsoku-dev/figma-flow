import json
from pathlib import Path
import subprocess
import unittest

BRIDGE = Path(__file__).resolve().parents[1] / 'figma-bridge'


class NativeAnnotationAuthoringTests(unittest.TestCase):
    def run_js(self, body):
        prelude = f"""
const assert = require('node:assert/strict');
const {{ensureNativeAnnotations}} = require({json.dumps(str(BRIDGE / 'native_annotations.js'))});
const {{readNativeSemantics,resolveInstanceSemanticKey}} = require({json.dumps(str(BRIDGE / 'native_semantic_read.js'))});
function node(id,key,type='FRAME') {{ return {{id,name:key,type,children:[],annotations:[],boundVariables:{{}},fills:[],strokes:[],getPluginData:k=>k==='semanticKey'?key:'',async loadAsync(){{}},findAll(){{return this.children.flatMap(child=>[child,...child.findAll()]);}}}}; }}
function attach(parent,child){{parent.children.push(child);child.parent=parent;}}
(async()=>{{
"""
        result = subprocess.run(['node', '-e', prelude + body + '\n})().catch(e=>{console.error(e);process.exit(1)});'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_owned_note_update_preserves_unrelated_and_rollback(self):
        self.run_js("""
const page=node('p','page','PAGE'), button=node('b','save');attach(page,button);
button.annotations=[{label:'Reviewer note',annotationCategoryId:'review'},{label:'[figma-flow:save] stale'}];
const original=structuredClone(button.annotations);
const contract={annotations:[{key:'save',label:'Role: save action. State: disabled while saving. Exception: show retry. Graph: save.',properties:['width','height']}]};
const result=await ensureNativeAnnotations({},page,contract);
assert.equal(result.changed,1);assert.deepEqual(button.annotations[0],original[0]);
assert.deepEqual(button.annotations[1].properties,[{type:'width'},{type:'height'}]);
assert.equal((await ensureNativeAnnotations({},page,contract)).changed,0);
button.annotations.push({label:'Later reviewer note'});
await result.rollback();await result.rollback();
assert.deepEqual(button.annotations,[original[0],{label:'Later reviewer note'},original[1]]);
""")

    def test_native_api_added_defaults_preserve_exact_label_and_notes(self):
        self.run_js("""
const page=node('p','page','PAGE'), a=node('a','a');attach(page,a);
let stored=[{label:'Human note',labelMarkdown:'**Human note**',categoryId:'human',properties:[{type:'height'}]}];
const original=structuredClone(stored);
Object.defineProperty(a,'annotations',{get:()=>stored,set:value=>{stored=value.map(note=>({properties:[],categoryId:'default',...note,labelMarkdown:note.labelMarkdown||note.label}));}});
const result=await ensureNativeAnnotations({},page,{annotations:[{key:'a',label:'Role: save. State: ready. Graph: a.'}]});
assert.equal(result.changed,1);assert.deepEqual(stored[0],original[0]);
assert.equal(stored[1].label,'[figma-flow:a] Role: save. State: ready. Graph: a.');
assert.equal((await ensureNativeAnnotations({},page,{annotations:[{key:'a',label:'Role: save. State: ready. Graph: a.'}]})).changed,0);
await result.rollback();assert.deepEqual(stored,original);
""")

    def test_later_failure_restores_owned_edits(self):
        self.run_js("""
const page=node('p','page','PAGE'), a=node('a','a'), b=node('b','b');attach(page,a);attach(page,b);
a.annotations=[{label:'Keep me'}];let stored=[];
Object.defineProperty(b,'annotations',{get:()=>stored,set:value=>{stored=value.filter(note=>!note.label.startsWith('[figma-flow:'));}});
await assert.rejects(ensureNativeAnnotations({},page,{annotations:[{key:'a',label:'Action A; graph a'},{key:'b',label:'Action B; graph b'}]}),/not retained/);
assert.deepEqual(a.annotations,[{label:'Keep me'}]);
assert.deepEqual(stored,[]);
delete a.annotations;
await assert.rejects(ensureNativeAnnotations({},page,{annotations:[{key:'a',label:'A'}]}),/unsupported/);
""")

    def test_unique_semantic_key_required_and_no_plugin_data_fallback(self):
        self.run_js("""
const page=node('p','page','PAGE');attach(page,node('a','same'));attach(page,node('b','same'));
await assert.rejects(ensureNativeAnnotations({},page,{annotations:[{key:'same',label:'A'}]}),/ambiguous/);
await assert.rejects(ensureNativeAnnotations({},page,{annotations:[{key:'a',label:'A'}]}),/missing/);
assert(page.children.every(n=>n.annotations.length===0));
""")

    def test_selected_page_native_bindings_aliases_components_and_mapping(self):
        self.run_js("""
const page=node('p','page','PAGE'), root=node('i','inherited-root','INSTANCE'), child=node('t','wrong-inherited','TEXT');attach(page,root);attach(root,child);
root.getPluginData=k=>k==='semanticComponent'?JSON.stringify({key:'screen.card',sourceKey:'library.card',childKeys:[{path:[0],key:'screen.title'}]}):'';
const set=node('set','set','COMPONENT_SET'), main=node('main','main','COMPONENT');attach(set,main);
root.getMainComponentAsync=async()=>main;
root.componentProperties={State:{type:'VARIANT',value:'Ready'}};root.variantProperties={State:'Ready'};
child.fills=[{type:'SOLID',boundVariables:{color:{type:'VARIABLE_ALIAS',id:'color'}}}];
const vars={color:{id:'color',name:'color',resolvedType:'COLOR',variableCollectionId:'bound',valuesByMode:{light:{type:'VARIABLE_ALIAS',id:'base'}}},base:{id:'base',name:'base',resolvedType:'COLOR',variableCollectionId:'baseCollection',valuesByMode:{baseMode:{r:1,g:0,b:0}}},managed:{id:'managed',name:'size',resolvedType:'FLOAT',variableCollectionId:'managedCollection',valuesByMode:{m:12}}};
const collection=(id,ids,marker='')=>({id,name:id,modes:[{modeId:id==='bound'?'light':'m',name:'Default'}],defaultModeId:'m',variableIds:ids,getPluginData:()=>marker});
const collections=[collection('bound',['color']),collection('baseCollection',['base']),collection('managedCollection',['managed'],JSON.stringify({pageId:'p',sourceHash:'hash'})),collection('unrelated',['secret'],JSON.stringify({pageId:'other'}))];
const figma={variables:{getLocalVariableCollectionsAsync:async()=>collections,getVariableByIdAsync:async id=>vars[id],getVariableCollectionByIdAsync:async id=>collections.find(c=>c.id===id)}};
const result=await readNativeSemantics(figma,page);
assert.deepEqual(result.selectedPageIds,['p']);
assert.deepEqual(new Set(result.collectionIds),new Set(['bound','baseCollection','managedCollection']));
assert.equal(result.variables.length,3);assert.equal(result.nodes.length,3);
assert.equal(result.nodes.find(n=>n.id==='t').semanticKey,'screen.title');
assert.equal(result.nodes.find(n=>n.id==='i').mainComponentId,'main');
assert.equal(result.nodes.find(n=>n.id==='i').componentSetId,'set');
assert(result.unavailableFields.some(f=>f.field==='annotationCategoryId'));
assert.equal(resolveInstanceSemanticKey(root),'screen.card');
assert.equal(result.variables.find(v=>v.id==='color').valuesByMode.light.id,'base');
""")

    def test_critical_native_failures_are_not_success(self):
        self.run_js("""
const page=node('p','page','PAGE'), instance=node('i','i','INSTANCE');attach(page,instance);
const figma={variables:{getLocalVariableCollectionsAsync:async()=>[]}};
const missing=(await readNativeSemantics(figma,page)).nodes.find(n=>n.id==='i');
assert.equal(missing.mainComponentId,undefined);
assert.match(missing.unavailable_fields.mainComponentId,/main component API unavailable/);
instance.getMainComponentAsync=async()=>null;
const detached=(await readNativeSemantics(figma,page)).nodes.find(n=>n.id==='i');
assert.equal(detached.mainComponentId,undefined);
assert.match(detached.unavailable_fields.mainComponentId,/main component unavailable/);
page.children=[];
await assert.rejects(readNativeSemantics({},page),/native variable collection read API unavailable/);
""")


if __name__ == '__main__':
    unittest.main()
