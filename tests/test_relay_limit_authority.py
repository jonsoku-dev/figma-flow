"""Publish a different selection budget and observe it at both relay boundaries."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROBE = """
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import figma_control as control
import figma_workspace as workspace
import figma_follow as follow
import plugin_panel
from relay_view import validate_options

ids = ['1:1', '1:2', '1:3']
rows = [dict(id=i, name=i, type='RECTANGLE') for i in ids]
context = dict(session_id='session', file_key='fixturefile', page_id='12:1', user_id=None)
assert validate_options('selection-info', {'geometry_node_ids':ids[:2]})['geometry_node_ids'] == ids[:2]
assert control._validate_relay_context(dict(context, selection=rows[:2]))['selection'] == rows[:2]
for operation in (lambda: validate_options('selection-info', {'geometry_node_ids':ids}),
                  lambda: control._validate_relay_context(dict(context, selection=rows))):
    try:
        operation()
    except ValueError:
        pass
    else:
        raise AssertionError('Third node passed its admission boundary')
args = SimpleNamespace(include_text=False, inspect_task='inspection', inspect_revision='revision')
with patch.object(follow, 'read_operation', return_value={}) as read:
    result = follow.inspect_events(args, [dict(node_id=i, properties=['opacity']) for i in ids])
assert result['observed_limit'] == 2 and result['omitted_node_count'] == 1
assert read.call_args.args[-1][:4] == ['--inspect-node-id','1:1','--inspect-node-id','1:2']
assert ids[2] not in read.call_args.args[-1]
messages = plugin_panel.panel_messages('chat')
for key in ('chat.limitError', 'chat.includeSelection'):
    assert all('2' in v and '20' not in v for v in messages[key].values())
workspace.init(Path('ws'), Path('issued.json'))
"""
NATIVE = """
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const rows = ['1:1','1:2','1:3'].map(id => ({id, name:id, type:'RECTANGLE',x:0,y:0,width:1,height:1}));
const figma = {fileKey:'fixturefile',editorType:'figma',currentPage:{id:'12:1',name:'Page',selection:rows},
  ui:{postMessage(){}}, showUI(){}, clientStorage:{getAsync:async()=>undefined}};
const ctx = vm.createContext({figma, __html__:'', console, setTimeout, clearTimeout});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
assert.equal(vm.runInContext('workspaceRelaySelection().length',ctx),2);
assert.equal(vm.runInContext('workspaceRelaySelectionTotal()',ctx),3);
assert.throws(()=>vm.runInContext('WorkspaceChat.collect(figma,{})',ctx),e=>e.code === 'limit');
figma.currentPage.selection = rows.slice(0,2);
assert.equal(vm.runInContext('WorkspaceChat.collect(figma,{}).nodes.length',ctx),2);
"""


class RelayLimitAuthorityTests(unittest.TestCase):
    def test_mutated_read_budget_reaches_native_codex_follower_and_translations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('tools', 'figma-bridge', 'library', 'skills', 'specs/workspace-activity', 'panel-ui/src', 'tests/fixtures/rd03'):
                shutil.copytree(ROOT / directory, root / directory,
                                ignore=shutil.ignore_patterns('node_modules', '__pycache__', '.DS_Store'))
            shutil.copyfile(ROOT / 'plugin.json', root / 'plugin.json')
            (root / 'library/figma-profile/read-limits.json').write_text('{"maxNodes":2}')
            (root / 'issued.json').write_text('{"id":"12345"}')
            env = dict(os.environ, PYTHONPATH=str(root / 'tools'), PYTHONDONTWRITEBYTECODE='1')
            subprocess.run([sys.executable, '-B', '-c', PROBE], cwd=root, env=env, check=True, timeout=40)
            main = json.loads((root / 'ws/manifest.json').read_bytes())['main']
            subprocess.run(['node', '-e', NATIVE, str(root / 'ws' / main)], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
