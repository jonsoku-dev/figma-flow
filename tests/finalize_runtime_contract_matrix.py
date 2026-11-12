"""RD07 behavioral fixtures: historical extraction, source pins and compiled task isolation.

No Git refs, server, browser, native Figma, or existing workspace are required.
Historical equivalence excludes later protocol-2 and capacity changes.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace


def node(script, *args):
    result = subprocess.run(['node', '-e', script, *map(str, args)], cwd=ROOT,
                            text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class RuntimeContractMatrix(unittest.TestCase):
    def test_ac01_frozen_extraction_body_and_transport_trace(self):
        baseline = json.loads((ROOT / 'tests/fixtures/rd07/extraction-baseline.json').read_text())
        sources = baseline['sources']
        for row in sources.values():
            raw = row['source'].encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(), row['blob'])
        before = sources['before_control']['source']
        start = before.index('async function controlRequest(')
        end = before.index('async function controlExecute(', start)
        extracted = before[start:end]
        after = sources['after_transport']['source']
        transport = after[after.index('async function controlRequest('):]
        self.assertEqual(extracted.rstrip() + '\n', transport.rstrip() + '\n')
        self.assertEqual(before[:start] + before[end:], sources['after_control']['source'])
        old = baseline['publisher']['before']['assembly_line']
        new = baseline['publisher']['after']['assembly_line']
        self.assertNotIn('workspace_transport.js', old)
        self.assertLess(new.index('workspace_transport.js'), new.index('workspace_control.js'))
        # Execute the actual old/new request bodies with the same success/error scenarios.
        trace = node(r'''
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const baseline=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
async function run(source){
 const calls=[], results=[];
 const env={WORKSPACE_CONTROL_CONFIG:{url:'http://localhost:49198',token:'fixture-token'},
 fetch:async(url,options)=>{calls.push({url,...options});return {ok:!url.endsWith('/reject'),status:403,json:async()=>({accepted:true})};}};
 vm.runInNewContext(source,env);
 for(const route of ['poll','native-started','result','reject']){
  try{results.push(await env.controlRequest(route,{operation:route,session_id:'fixture-session'}));}
  catch(error){results.push(error.message);}
 }
 return {calls,results};
}
(async()=>{
 const old=baseline.sources.before_control.source;
 const body=old.slice(old.indexOf('async function controlRequest('),old.indexOf('async function controlExecute('));
 const first=await run(body), second=await run(baseline.sources.after_transport.source);
 assert.deepEqual(JSON.parse(JSON.stringify(first)),JSON.parse(JSON.stringify(second))); assert.equal(first.calls.length,4);
 assert.equal(first.calls[0].method,'POST'); assert.equal(first.calls[0].headers.Authorization,'Bearer fixture-token');
 assert.match(first.results[3],/rejected \(403\)/); console.log('4 historical transport scenarios equivalent');
})().catch(error=>{console.error(error);process.exitCode=1});
''', ROOT / 'tests/fixtures/rd07/extraction-baseline.json')
        self.assertIn('4 historical transport scenarios equivalent', trace)

    @unittest.skipUnless(os.name == 'posix', 'Private workspaces require POSIX')
    def test_ac02_transport_only_change_invalidates_real_mutation_claim(self):
        # A separate interpreter loads all module roots from the copied host sources.
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / 'installation'
            copied.mkdir()
            for folder in ('tools', 'figma-bridge', 'library'):
                shutil.copytree(ROOT / folder, copied / folder,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copy2(ROOT / 'plugin.json', copied / 'plugin.json')
            script = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'tools'))
import figma_workspace as workspace
import figma_control as control
installation=Path(sys.argv[1]); root=installation.parent/'workspace'
identity=installation.parent/'assigned.json'; identity.write_text('{"id":"12345"}')
workspace.init(root,identity)
plan=installation.parent/'plan.json'
plan.write_text(json.dumps({'schema':'figma-flow-native-edit-plan-v1','file_key':'fixturefile','page_id':'12:1',
 'edits':[{'node_id':'13:1','field':'paddingLeft','before':12,'after':20}]}))
prepared=workspace.prepare(root,'mutation','Scoped edit','native-edit',['--plan',str(plan)],infer_thread=False)
control.enable(root,49198)
old=workspace.current(root)['runtime'].copy(); before=workspace.trusted_sources()
path=installation/'figma-bridge/workspace_transport.js'
source_bytes={item:item.read_bytes() for item in installation.rglob('*') if item.is_file()}
path.write_bytes(path.read_bytes()+b'\n/* RD07 fixture: transport-only source drift */\n')
assert {item for item,raw in source_bytes.items() if item.read_bytes()!=raw}=={path}
assert workspace.trusted_sources()!=before
# Real publication updates implementation, then the old native identity tries the claim.
workspace.publish(root,workspace.current(root))
current=workspace.current(root)['runtime']
assert current['implementation']!=old['implementation']
assert current['implementation']==workspace.trusted_sources()
control.enqueue(root,'mutation','apply','fixturefile','12:1',prepared['revision'],120)
payload={'session_id':'old-native-session','file_key':'fixturefile','page_id':'12:1','runtime':{**current,'implementation':old['implementation']}}
assert control.poll(root,payload)['operation'] is None
assert control.status(root)['state']=='pending'
assert control.readiness(root)['native_status']=='unverified'
# Positive control: the exact current identity claims the very same pending mutation.
payload['runtime']=current
assert control.poll(root,payload)['operation']['key']=='mutation'
assert control.status(root)['state']=='claimed'
print('transport drift changed implementation; old identity refused; current identity claimed')
'''
            result = subprocess.run([sys.executable, '-B', '-c', script, str(copied)],
                                    cwd=copied, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.name == 'posix', 'Private workspaces require POSIX')
    def test_ac03_real_publisher_isolates_two_normal_native_edit_closures(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            root = directory / 'workspace'
            identity = directory / 'assigned.json'
            identity.write_text('{"id":"12345"}')
            workspace.init(root, identity)
            sessions = []
            for key, file, page, target in [('a', 'file-a', '1:1', '2:1'), ('b', 'file-b', '9:1', '9:2')]:
                plan = directory / (key + '.json')
                plan.write_text(json.dumps({'schema':'figma-flow-native-edit-plan-v1',
                    'file_key':file, 'page_id':page,
                    'edits':[{'node_id':target,'field':'paddingLeft','before':12,'after':20}]}))
                workspace.prepare(root, key, 'Scoped ' + key, 'native-edit', ['--plan', str(plan)], infer_thread=False)
                task = next(task for task in workspace.current(root)['tasks'] if task['key'] == key)
                code = (workspace.task_artifacts(root, task) / 'code.js').read_text()
                # Both trusted outputs deliberately declare the same lexical names.
                self.assertIn('const NATIVE_EDIT_PLAN = ', code)
                sessions.append(json.loads(code.split('const NATIVE_EDIT_SESSION = ', 1)[1].split(';', 1)[0]))
            self.assertNotEqual(*sessions)
            manifest = json.loads((root / 'manifest.json').read_text())
            node(ISOLATION_VM, root / manifest['main'], json.dumps(sessions))


ISOLATION_VM = r'''
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const sessions=JSON.parse(process.argv[2]), messages=[], shown=[];
function page(id,name){return {id,name,type:'PAGE',children:[],async loadAsync(){},findAll(){return [];},getPluginData(){return '';}};}
const pages=[page('1:1','A private observation'),page('9:1','B private observation')];
const figma={fileKey:'file-a',currentPage:pages[0],ui:{postMessage(value){messages.push(value);}},
 showUI(html){shown.push(html);},async getNodeByIdAsync(id){return pages.find(page=>page.id===id);},
 variables:{async getLocalVariableCollectionsAsync(){return [];}}};
const context=vm.createContext({figma,__html__:'HOME',console,setTimeout(){return 0;},clearTimeout(){}});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const send=message=>figma.ui.onmessage(message);
async function listing(){await send({type:'workspace-home-ready'});return messages.filter(row=>row.type==='workspace-tasks').at(-1);}
async function open(key){const model=await listing();await send({type:'workspace-open',key,workspaceSession:model.workspaceSession});
 const match=shown.at(-1).match(/const workspaceSession = ("[^"]+")/);assert.ok(match);return JSON.parse(match[1]);}
async function read(session,nonce){await send({type:'workspace-task-message',workspaceSession:session,payload:{type:'read',session:nonce}});}
function observations(){return messages.filter(row=>row.payload?.readback);}
(async()=>{
 const model=await listing();assert.equal(model.tasks.length,2);
 for(const task of model.tasks){assert.equal('run' in task,false);assert.equal('NATIVE_EDIT_PLAN' in task,false);}
 assert.ok(!JSON.stringify(model).includes(sessions[0]));assert.ok(!JSON.stringify(model).includes(sessions[1]));
 const a=await open('a'), htmlA=shown.at(-1);
 assert.ok(htmlA.includes(sessions[0]));assert.ok(!htmlA.includes(sessions[1]));
 await read(a,sessions[1]);assert.equal(observations().length,0);
 await read(a,sessions[0]);
 assert.equal(observations().length,1);
 const first=observations()[0].payload.readback;
 assert.equal(first.fileKey,'file-a');assert.equal(first.pageId,'1:1');
 assert.deepEqual(Array.from(first.nodes,row=>row.name),['A private observation']);
 await send({type:'workspace-back',workspaceSession:a});
 figma.fileKey='file-b';figma.currentPage=pages[1];
 const b=await open('b'), htmlB=shown.at(-1);assert.notEqual(a,b);
 assert.ok(htmlB.includes(sessions[1]));assert.ok(!htmlB.includes(sessions[0]));
 await read(a,sessions[0]);await read(b,sessions[0]);assert.equal(observations().length,1);
 await read(b,sessions[1]);assert.equal(observations().length,2);
 const second=observations()[1].payload.readback;
 assert.equal(second.fileKey,'file-b');assert.equal(second.pageId,'9:1');
 assert.deepEqual(Array.from(second.nodes,row=>row.name),['B private observation']);
 assert.ok(!JSON.stringify(second).includes('A private observation'));
 assert.equal(vm.runInContext('typeof NATIVE_EDIT_PLAN',context),'undefined');
 assert.equal(vm.runInContext('typeof NATIVE_EDIT_SESSION',context),'undefined');
 console.log('two normally compiled closures: own UI config/readback; foreign nonce and stale envelopes rejected');
})().catch(error=>{console.error(error);process.exitCode=1});
'''

if __name__ == '__main__':
    unittest.main()
