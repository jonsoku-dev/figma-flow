"""Check shipped historical audit output, fresh starter source pins, and exact release oracles."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import figma_api_audit
import major_release
import native_edit
import starter_cta


class ToolingContractsTests(unittest.TestCase):
    def test_historical_api_report_regenerates_without_changing_evidence_status(self):
        base=ROOT/'library/figma-api/audit'
        data=json.loads((base/'members.json').read_bytes())
        self.assertEqual(figma_api_audit.report(data),(base/'report.md').read_text())
        self.assertEqual(len(data['members']),len({row['key'] for row in data['members']}))
        for source in data['curated_evidence_sources']:
            self.assertEqual(hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest(),source['sha256'])

    def test_starter_plan_takes_labels_and_component_identity_from_pinned_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            readback=tmp/'read.json';out=tmp/'plan.json'
            example={'schema':'figma-flow-graph-native-discovery-v1','fileKey':'fixture','pageId':'1:1',
                     'allowed_page_ids':['1:1'],'collections':[],'variables':[], 'nodes':[
                         {'id':'1:1','type':'PAGE','name':'QA'},
                         {'id':'1:2','parentId':'1:1','type':'FRAME','name':'Existing','x':20,'y':10,'width':70,'height':35,
                          'absoluteBoundingBox':{'x':20,'y':10,'width':70,'height':35}}]}
            readback.write_text(json.dumps(example))
            graph=ROOT/'apps/little-hands/design/graph.json'
            starter_cta.prepare(graph,readback,'fixture','1:1',out)
            plan=json.loads(out.read_bytes());provision=plan['provision']
            native_edit.validate_plan(plan)
            component=json.loads(graph.read_bytes())['design_system']['components'][starter_cta.STARTER['componentId']]
            self.assertEqual(provision['instance_keys'],component['native']['instanceKeys'])
            self.assertEqual(provision['position']['x'],90+starter_cta.STARTER['canvasGap'])
            self.assertEqual(provision['label_source_sha256'],hashlib.sha256(Path(provision['label_source_path']).read_bytes()).hexdigest())
            self.assertTrue(all(provision['labels'].get(k) for k in provision['instance_keys']))
            provision['canonical_variable_name']='unregistered-color'
            with self.assertRaisesRegex(ValueError,'semantic token'):
                native_edit.validate_plan(plan)

    def test_archive_case_runner_rejects_unregistered_and_skipped_node_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            test=root/'tests/demo.cjs'
            test.parent.mkdir()
            for source in ('console.log("fixture finished");', "require('node:test').skip('reviewed case',()=>{});"):
                test.write_text(source)
                case={'test':'tests/demo.cjs','case':'reviewed case','testSha256':hashlib.sha256(test.read_bytes()).hexdigest()}
                with self.assertRaisesRegex(ValueError,'Named test case'):
                    major_release.rerun_witness(root,case)
            test.write_text("require('node:test')('reviewed case',()=>require('node:assert/strict').equal(2+2,4));")
            case['testSha256']=hashlib.sha256(test.read_bytes()).hexdigest()
            major_release.rerun_witness(root,case)

    def test_panel_witness_uses_explicit_external_dependencies_without_changing_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            outer=Path(temp);root=outer/'candidate';(root/'tests').mkdir(parents=True)
            (root/'panel-ui').mkdir()
            (root/'panel-ui/package.json').write_text('{"dependencies":{"fixture-build":"1.0.0"}}')
            deps=outer/'installed/node_modules';pkg=deps/'fixture-build';pkg.mkdir(parents=True)
            (pkg/'index.js').write_text("module.exports='locked-input';")
            script=root/'tests/view.cjs'
            script.write_text("require('node:test')('published model', () => {"
                "const load=require('node:module').createRequire(require('node:path').resolve('panel-ui/package.json'));"
                "require('node:assert/strict').equal(load('fixture-build'),'locked-input');});")
            case={'test':'tests/view.cjs','testSha256':hashlib.sha256(script.read_bytes()).hexdigest(),'case':'published model'}
            with self.assertRaises(ValueError):
                major_release.rerun_witness(root,case,panel_deps=outer/'absent')
            major_release.rerun_witness(root,case,panel_deps=deps)
            self.assertFalse((root/'node_modules').exists())
            self.assertFalse((root/'panel-ui/node_modules').exists())

    def test_checker_import_graph_includes_new_local_transitive_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            directory=root/'tools';directory.mkdir()
            (directory/'major_release.py').write_text('import local_check\n')
            (directory/'local_check.py').write_text('from extra_rule import verify\n')
            (directory/'extra_rule.py').write_text('def verify(): return []\n')
            self.assertTrue({'tools/extra_rule.py','tools/local_check.py'} <= major_release.checker_inputs(root))


if __name__=='__main__':
    unittest.main()
