import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import major_release as gate
import plugin_manifest


def write(root, name, value):
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value,str) else value)
    return path


class MajorReleaseTests(unittest.TestCase):
    def test_review_binds_coverage_authority_witness_and_exact_candidate_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            owner = 'library/policy.json'
            write(root,owner,{'tasks':{'read':'designRead'}})
            paths = ['tools/one.py','tools/two.py']
            for name in paths:
                write(root,name,'pass')
            surface = {'id':'tools'}
            fingerprint = lambda: gate.scope_digest(root, [owner,*paths])
            check = lambda: gate.verify_review(root,surface,paths,{owner},fingerprint())
            self.assertEqual(check()[0]['code'],'unreviewed-surface')
            test = write(root,'tests/test_read.py',
                         "from pathlib import Path\nimport unittest\nclass Read(unittest.TestCase):\n"
                         " def test_files(self):\n  self.assertEqual(Path('tools/one.py').read_text(), Path('tools/two.py').read_text())\n")
            witness = write(root,'release/reviews/evidence/tools.json',
                            {'surfaceFingerprint':fingerprint(),'status':'passed','checks':[
                                {'assertion':'the two fixture files agree','observed':'equal','authority':owner+'#/tasks/read',
                                 'covers':paths,'test':'tests/test_read.py','case':'Read.test_files',
                                 'testSha256':hashlib.sha256(test.read_bytes()).hexdigest()}]})
            binding = {'files':paths.copy(),'authority':owner+'#/tasks/read','reason':'Task admission',
                       'witnesses':[{'path':witness.relative_to(root).as_posix(),'sha256':hashlib.sha256(witness.read_bytes()).hexdigest()}]}
            doc = {'schema':'figma-flow-major-review-v1','surface':'tools','fingerprint':fingerprint(),
                   'openFindings':[], 'bindings':[binding]}
            review = lambda: write(root,'release/reviews/tools.json',doc)
            review()
            self.assertEqual(check(),[])
            binding['files'].pop()
            review()
            self.assertIn('Missing bindings',check()[0]['message'])
            binding['files'] = paths
            binding['authority'] = owner+'#/missing'
            review()
            self.assertTrue(check())
            binding['authority'] = owner+'#/tasks/read'
            review()
            test_before = test.read_bytes()
            test.write_text('wrong')
            self.assertIn('test implementation changed',check()[0]['message'])
            test.write_bytes(test_before)
            before = witness.read_bytes()
            witness.write_bytes(before+b' ')
            self.assertIn('Witness bytes',check()[0]['message'])
            witness.write_bytes(before)
            write(root,paths[0],'new implementation')
            self.assertIn('stale',check()[0]['message'])

    def test_inventory_never_drops_unknown_files_or_relabels_product_as_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            graph={'schema':'figma-flow-major-authority-v1','nodes':[
                {'id':'tool','type':'surface','roots':['tools'],'coverage':'record'},
                {'id':'policy','type':'authority','source':'tools/policy.json'}],
                'edges':[{'type':'owned-by','from':'tool','to':'policy'}]}
            write(root,gate.REGISTRY,graph)
            write(root,'tools/policy.json',{})
            write(root,'new-area/app.js','')
            found, surfaces=gate.inventory(root,{'tools/policy.json','new-area/app.js'})
            self.assertEqual(surfaces[0]['files'],['tools/policy.json'])
            self.assertEqual({f['code'] for f in found},{'unowned-archive-file','incorrect-support-role','missing-release-control'})
            graph['edges'][0]['to']='missing'
            write(root,gate.REGISTRY,graph)
            with self.assertRaisesRegex(ValueError,'authority edge'):
                gate.inventory(root,{'tools/policy.json'})

    def test_tag_packaging_checks_ref_bytes_not_dirty_checkout_or_supplied_same_major_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args):
                return subprocess.check_output(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.invalid',
                                                '-c','core.hooksPath=/dev/null',*args],text=True).strip()
            git('init','-q')
            def manifest(v):
                value={'name':'fixture','description':'Fixture','version':v,'extensions':{'com.openai':{
                    'onboardingSkill':'setup','interface':{},'requires_local_executor':True}}}
                write(root,'plugin.json',value)
                write(root,'.codex-plugin/plugin.json',plugin_manifest.projection(value))
            manifest('0.36.0')
            git('add','.');git('commit','-qm','minor');git('tag','v0.36.0')
            manifest('1.2.0')
            git('add','.');git('commit','-qm','first major');git('tag','v1.2.0')
            manifest('0.36.0')  # An unstaged manifest must never decide what gets shipped.
            archive=root/'dist.zip'
            def run(*args):
                return subprocess.run([sys.executable,'-B',str(ROOT/'tools/major_release.py'),'--repo',str(root),
                                       '--if-major','--archive',str(archive),*args],capture_output=True,text=True)
            blocked=run('--ref','v1.2.0','--base-ref','HEAD')
            self.assertNotEqual(blocked.returncode,0)
            self.assertEqual(json.loads(blocked.stdout)['status'],'blocked')
            self.assertFalse(archive.exists())
            git('tag','v0.99.0')
            wrong_tag = run('--ref','refs/tags/v0.99.0')
            self.assertIn('Tag',json.loads(wrong_tag.stdout)['error'])
            given=run('--ref','v0.36.0')
            self.assertEqual(given.returncode,0,given.stderr)
            with ZipFile(archive) as z:
                self.assertEqual(json.loads(z.read('figma-flow-plugin/plugin.json'))['version'],'0.36.0')
            original=archive.read_bytes()
            self.assertNotEqual(run('--ref','v0.36.0').returncode,0)
            self.assertEqual(original,archive.read_bytes())
            manifest('0.39.0')
            git('add','plugin.json','.codex-plugin/plugin.json')
            git('commit','-qm','major downgrade');git('tag','v0.39.0')
            self.assertIn('downgrade',json.loads(run('--ref','v0.39.0').stdout)['error'])
            self.assertEqual(original,archive.read_bytes())


if __name__=='__main__':
    unittest.main()
