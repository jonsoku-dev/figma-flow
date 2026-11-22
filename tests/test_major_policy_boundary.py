"""The task runner must obtain its admission vocabulary from the published policy."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('figma-bridge/workspace_control.js', 'utf8');
async function enters(policy) {
  let entered = false;
  const env = {workspaceHomeSession:'one',workspaceActive:null,
    figma:{fileKey:'fixture',currentPage:{id:'2:1'}},
    workspaceOpen:async () => {entered=true;throw Error('end of probe');}};
  if (policy) env.WORKSPACE_PROFILE_POLICY=policy;
  vm.createContext(env); vm.runInContext(source,env);
  const task={kind:'discover',revision:'r',fileKey:'fixture',pageId:'2:1'};
  const cmd={operation:'read',revision:'r',file_key:'fixture',page_id:'2:1',deadline:Date.now()/1000+10};
  try {await env.controlExecute(task,cmd)} catch (_) {}
  return entered;
}
(async()=>{
  const policy=JSON.parse(fs.readFileSync('library/figma-profile/policy.json','utf8'));
  console.log(JSON.stringify([await enters(policy), await enters(undefined)]));
})().catch(e=>{console.error(e);process.exitCode=1});
"""


class MajorPolicyBoundaryTest(unittest.TestCase):
    def test_missing_policy_cannot_dispatch_using_an_embedded_copy(self):
        values = json.loads(subprocess.check_output(['node', '-e', PROBE], cwd=ROOT, text=True))
        self.assertTrue(values[0], 'The canonical policy must admit the signed discover read')
        self.assertFalse(values[1], 'Missing graph authority must prevent native task dispatch')


if __name__ == '__main__':
    unittest.main()
