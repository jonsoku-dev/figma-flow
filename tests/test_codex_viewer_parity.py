"""Drive the published host on a real signed task using a synthetic Design document."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_workspace as workspace

DRIVER = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const page = {id:'12:1',name:'Design page',type:'PAGE',selection:[]};
const text = {id:'12:2',name:'Title',type:'TEXT',characters:'Reserve',parent:page,x:0,y:4,width:100,height:24};
const foreign = {...text,id:'17:3',parent:{id:'17:1',type:'PAGE'}};
const stored = new Map();
const figma = {fileKey:'fixturefile',pluginId:'12345',apiVersion:'1.0.0',editorType:'figma',mode:'default',
  currentPage:page, root:{name:'Fixture'}, currentUser:{id:'fixture-user',name:'User'}, viewport:{scrollAndZoomIntoView(){}},
  getNodeByIdAsync:async id => id===text.id ? text : foreign, showUI(){}, ui:{postMessage(){}},
  clientStorage:{getAsync:async k=>stored.get(k),setAsync:async(k,v)=>stored.set(k,v)}};
const ctx = vm.createContext({figma,__html__:'',console,setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const execute = vm.runInContext(`async (operation,options) => {
  await workspaceLoaded;
  const task=workspaceTasks.get('parity');
  const cmd={key:task.key,file_key:task.fileKey,page_id:task.pageId,revision:task.revision,operation,
    session_id:controlRunSession,deadline:Date.now()/1000+10,viewer_options:options};
  return controlExecute(task,cmd,async()=>{});
}`,ctx);
(async () => {
  await figma.ui.onmessage({type:'workspace-home-ready',locale:'en',requestId:'check'});
  const selected=await execute('select-node',{node_id:text.id});
  assert.equal(selected.selected.id,text.id);
  await assert.rejects(execute('select-node',{node_id:foreign.id}));
  assert.equal(page.selection[0],text);
  const regular=await execute('selection-info',{include_text:false});
  assert.equal(regular.selection.nodes[0].width,100);
  assert.equal(regular.selection.nodes[0].textExcerpt,undefined);
  assert.equal((await execute('selection-info',{include_text:true})).selection.nodes[0].textExcerpt,'Reserve');
  const locale=await execute('viewer-language',{language:'ja'});
  assert.equal(locale.storage,'local');
  const history=await execute('viewer-history',{});
  assert.equal(history.locale,'ja');
  assert.equal(history.scope,'file');
  assert.equal(stored.get('figma-flow-workspace-v1:fixturefile').locale,'ja');
})().catch(error=>{console.error(error);process.exitCode=1});
"""


class CodexViewerParityTests(unittest.TestCase):
    def test_published_task_selects_reads_and_preserves_file_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            issued, root = folder / 'issued.json', folder / 'ws'
            issued.write_text('{"id":"12345"}')
            workspace.init(root, issued)
            workspace.prepare(root, 'parity', 'Read', 'discover',
                              ['--file-key', 'fixturefile', '--page-id', '12:1'], infer_thread=False)
            manifest = json.loads((root / 'manifest.json').read_bytes())
            result = subprocess.run(['node', '-e', DRIVER, str(root / manifest['main'])],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, 'Codex must select and inspect a Design layer through its signed task. ' + result.stderr)


if __name__ == '__main__':
    unittest.main()
