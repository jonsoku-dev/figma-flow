"""Codex-visible edit facts, opt-in text and resumable follower state."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import figma_follow as follow
from relay_view import validate_options


class DetailTests(unittest.TestCase):
    def test_explicit_fields_are_read_in_pinned_page_without_selection_or_implicit_text(self):
        ids=['1:1','9:1']
        opts=validate_options('selection-info', {'inspect_node_ids':ids,'fields':['opacity','name','fills']})
        self.assertFalse(opts['include_text'])
        for invalid in ({'fields':['pluginData']},{'fields':['characters']},{'geometry_node_ids':ids}):
            with self.assertRaises(ValueError):
                validate_options('selection-info',{**opts,**invalid})
        script = r"""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const page={id:'1:0',type:'PAGE',selection:[]};
const local={id:'1:1',type:'TEXT',name:'Title',opacity:.92,characters:'x'.repeat(300),fills:[],parent:page};
const foreign={id:'9:1',type:'TEXT',name:'Off page',parent:{id:'9:0',type:'PAGE'}};
const figs={fileKey:'demo',currentPage:page,getNodeByIdAsync:async id=>id==='1:1'?local:foreign};
const env=vm.createContext({figma:figs,controlRunSession:'session',WORKSPACE_READ_LIMITS:require('./library/figma-profile/read-limits.json'),WORKSPACE_PROFILE_POLICY:require('./library/figma-profile/policy.json')});
vm.runInContext(fs.readFileSync('figma-bridge/relay_view.js','utf8'),env);
const task={kind:'discover',fileKey:'demo',pageId:'1:0',revision:'r'};
const run=opts=>env.workspaceViewerExecute(task,{revision:'r',file_key:'demo',page_id:'1:0',operation:'selection-info',session_id:'session',viewer_options:opts},()=>{});
(async()=>{
 const options=JSON.parse(process.argv[1]), value=await run(options);
 assert.equal(value.selection_included,false);
 const [node,missing]=value.details.nodes;
 assert.equal(node.fields.opacity.value,.92);assert.equal(node.fields.characters,undefined);
 assert.equal(missing.status,'missing');assert.equal(missing.fields,undefined);
 const excerpt=await run({...options,inspect_node_ids:['1:1'],fields:['characters'],include_text:true});
 assert.equal(excerpt.details.nodes[0].fields.characters.value.length,200);
 assert.equal(excerpt.details.nodes[0].fields.characters.truncated,true);
 assert.equal(page.selection.length,0);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        result=subprocess.run(['node','-e',script,json.dumps(opts)],cwd=ROOT,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_latest_view_invalidates_on_gap_and_coalesces_back_to_back_notifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            args=SimpleNamespace(inspect_task=None,read_task=None,resume_chat=True)
            scope={'file_key':'demo','page_id':'1:0'}
            def batch(i,node=None):
                return {'scope':scope,'cursor':{'epoch':'one','seq':i},'events':
                        [{'type':'PROPERTY_CHANGE','origin':'unknown','properties':['opacity'],'node_id':node}] if node else [],
                        'gap':None if node else {'reason':'cursor_expired'}}
            with patch.object(follow,'notify',return_value={'state':'queued'}) as notify:
                follow.handle_batch(args,folder,'test',batch(1,'1:1'))
                follow.handle_batch(args,folder,'test',batch(2,'1:2'))
                self.assertEqual(notify.call_count,1)
                current=json.loads((folder/'latest.json').read_bytes())
                self.assertEqual(current['notification']['state'],'coalesced')
                self.assertEqual(set(current['nodes']),{'1:1','1:2'})
                follow.handle_batch(args,folder,'test',batch(3))
                self.assertFalse(json.loads((folder/'latest.json').read_bytes())['nodes'])
                older = batch(4,'1:7')
                older['scope'] = {**scope,'generation':'old'}
                follow.handle_batch(args,folder,'test',older)
                newer = batch(5,'1:8')
                newer['scope'] = {**scope,'generation':'new'}
                follow.handle_batch(args,folder,'test',newer)
                self.assertEqual(set(json.loads((folder/'latest.json').read_bytes())['nodes']), {'1:8'})
