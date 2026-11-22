"""Observe the actual call argument at each registered Figma window site after changing its graph."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import native_windows

# Isolate the window's real showUI argument from unrelated canvas work. Figma receives this
# exact expression; the registered home can choose either the relay or the legacy frame.
DRIVER = r"""
const vm=require('node:vm'), assert=require('node:assert/strict'), fs=require('node:fs');
const graph=JSON.parse(fs.readFileSync('library/figma-profile/native-windows.json'));
for (const [file,bindings] of Object.entries(graph.bindings)) {
  const lines=fs.readFileSync(file,'utf8').split('\n').filter(line=>line.includes('/* flow-window'));
  const counts={};
  for (const line of lines) {
    assert.ok(line.includes('showUI('), file);
    const args=line.slice(line.indexOf('/* flow-window'));
    const configured=[...args.matchAll(/\/\* flow-window (\w+) \*\/\s*(\{[^{}]*\})/g)];
    assert.ok(configured.length);
    let argument=line.slice(line.indexOf(', /* flow-window')+2);
    if (configured.length===2) argument=line.slice(line.indexOf('workspaceRelayViewer ?'));
    else argument=args;
    argument=argument.slice(0,argument.indexOf(');'));
    for (const [i,match] of configured.entries()) {
      let shown;
      vm.runInNewContext('figma.showUI(html, '+argument+');',
        {figma:{showUI:(_,o)=>{shown=JSON.parse(JSON.stringify(o));}},html:'fixture',workspaceRelayViewer:i===0});
      assert.deepEqual(shown,graph.windows[match[1]],file+' '+match[1]);
      counts[match[1]]=(counts[match[1]]||0)+1;
    }
  }
  assert.deepEqual(counts,bindings);
}
"""


class NativeWindowTests(unittest.TestCase):
    def test_all_showui_calls_receive_the_edited_window_dimensions(self):
        graph=json.loads((ROOT/native_windows.SOURCE).read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            sources=[native_windows.SOURCE,Path('tools/native_windows.py'),*(Path(s) for s in graph['bindings'])]
            for p in sources:
                (root/p).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/p,root/p)
            for index,options in enumerate(graph['windows'].values(),1):
                options.update(width=550+index,height=380+index)
            (root/native_windows.SOURCE).write_text(json.dumps(graph))
            self.assertEqual({f['path'] for f in native_windows.check(root)}, set(graph['bindings']))
            cmd=[sys.executable,'-B',root/'tools/native_windows.py']
            subprocess.run([*cmd,'--write'],cwd=root,check=True)
            subprocess.run(cmd,cwd=root,check=True)
            subprocess.run(['node','-e',DRIVER],cwd=root,check=True,capture_output=True,text=True)


if __name__=='__main__':
    unittest.main()
