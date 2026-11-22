"""Use one edited transport contract for the native requester and the authenticated Python receiver."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const d=JSON.parse(fs.readFileSync(0,'utf8')), routes=[];
const ctx=vm.createContext({WORKSPACE_PROFILE_POLICY:d.policy,WORKSPACE_CONTROL_CONFIG:d.config,setTimeout,clearTimeout,
  fetch:async (url,options)=>{routes.push(new URL(url).pathname);return fetch(url,options)}});
vm.runInContext(fs.readFileSync('figma-bridge/workspace_transport.js','utf8'),ctx);
(async()=>{
  const body={...d.claim,status:'ok',readback_json:d.raw};
  await assert.rejects(ctx.controlRequest('result',body,false), /limit/);
  await assert.rejects(ctx.controlRequest('result',{...body,readback_json:'x'.repeat(520)},true), /limit/);
  await ctx.controlRequest('result',body,true);
  assert.deepEqual(routes,['/control/result-large']);
})().catch(e=>{console.error(e.message);process.exitCode=1});
"""
PROBE = """
import json,sys,subprocess
from pathlib import Path
from test_figma_control import ControlTests,control
f=ControlTests()
try:
    f.setUp()
    server=f.start_server()
    f.enqueue()
    claim=f.claim()
    payload={k:claim[k] for k in ('id','claim_id','session_id','file_key','page_id','revision')}
    raw=json.dumps({'title':'가'*32},ensure_ascii=False)
    try:
        control.result(f.root,dict(payload,status='ok',readback_json=raw))
    except ValueError as exc:
        assert 'bounded JSON' in str(exc)
    else:
        raise AssertionError('Ordinary server path admitted an oversized receipt')
    cfg=control.config(f.root)
    packet=dict(policy=control.PROFILE_POLICY,config=dict(url='http://localhost:'+str(server.server_port),token=cfg['token']),claim=payload,raw=raw)
    subprocess.run(['node','--dns-result-order=ipv4first','-e',sys.argv[1]],input=json.dumps(packet),text=True,check=True,timeout=15)
    receipt=control.status(f.root)
    assert receipt['state']=='ok'
    assert Path(receipt['readback']).read_bytes()==raw.encode()
finally:
    f.doCleanups()
"""


class TransportAuthorityTests(unittest.TestCase):
    def test_changed_read_budget_reaches_both_ends_of_an_actual_local_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for directory in ('tools','skills','figma-bridge','library','specs/workspace-activity','panel-ui/src','tests/fixtures'):
                shutil.copytree(ROOT/directory,root/directory,ignore=shutil.ignore_patterns('node_modules','__pycache__','.DS_Store'))
            shutil.copyfile(ROOT/'plugin.json',root/'plugin.json')
            shutil.copyfile(ROOT/'tests/test_figma_control.py',root/'tests/test_figma_control.py')
            p=root/'library/figma-profile/policy.json'
            policy=json.loads(p.read_bytes())
            policy['controlTransport'].update(normal={'bodyBytes':2048,'readbackBytes':32},largeRead={'bodyBytes':4096,'readbackBytes':512})
            p.write_text(json.dumps(policy))
            env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(root/i) for i in ('tests','tools')),PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run([sys.executable,'-B','-c',PROBE,DRIVER],cwd=root,capture_output=True,text=True,env=env,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
