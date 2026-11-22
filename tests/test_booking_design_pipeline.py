"""Exercise the booking design adapter and its actual input and output boundaries."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/little-hands'
DESIGN = APP / 'design'


def read(path):
    return json.loads(path.read_bytes())


class BookingDesignPipelineTests(unittest.TestCase):
    def test_rebuilds_handoffs_from_captures_and_retains_authored_graph_identity(self):
        outputs = ['app/index.html','app/inspect.html','visual-review.html','control-reuse.json',
                   'dom-map.json','native-layout.json','source-status.json','specifications.json',
                   'screen-spec.md','input-pins.json']
        with tempfile.TemporaryDirectory(prefix='little-hands-') as temp:
            root = Path(temp)
            app = root/'apps/little-hands'
            design = app/'design'
            shutil.copytree(DESIGN,design,ignore=shutil.ignore_patterns('.figma-flow','reviews','*.lock','*.ttf','__pycache__'))
            for name in ('templates','static','booking','ARCHITECTURE.md'):
                (app/name).symlink_to(APP/name)
            for name in ('tools','skills','library','figma-bridge','vendor','tests'):
                (root/name).symlink_to(ROOT/name)
            def execute(*args):
                result = subprocess.run([sys.executable,'-B',*args],cwd=root,capture_output=True,text=True,timeout=110)
                self.assertEqual(result.returncode,0,result.stderr[-3000:])
            execute(design/'prepare_fonts.py')
            for name in outputs:
                (design/name).unlink()
            execute(design/'source.py','--static-root',design/'source_assets')
            for name in outputs + ['graph.json']:
                self.assertEqual((design/name).read_bytes(),(DESIGN/name).read_bytes(),name)
            execute(ROOT/'tools/design_quality.py','--layout',design/'native-layout.json','--out',root/'quality.json')
            self.assertEqual(read(root/'quality.json'),read(DESIGN/'quality.json'))
            execute('-m','unittest','discover','-s',design,'-p','test_*.py')

    def test_capture_plan_requirement_names_resolve_to_actual_app_tests_and_templates(self):
        import ast
        plan = read(DESIGN/'capture-plan.json')
        graph = read(DESIGN/'graph.json')
        nodes={n['id']:n for n in graph['nodes']}
        test_body=ast.parse((APP/'booking/tests/test_booking.py').read_text())
        checks={n.name for n in ast.walk(test_body) if isinstance(n,ast.FunctionDef)}
        for req in plan['requirements']:
            self.assertEqual(nodes[req['id']]['type'],'requirement')
            if req['test'] is None:
                test_id = req['id'].replace('REQ-', 'TEST-')
                self.assertEqual(nodes[test_id]['source'], 'README.md#실제-검증')
                self.assertIn('## 실제 검증', (DESIGN/'README.md').read_text())
                self.assertTrue(read(DESIGN/'native-qa-summary.json')['prototype_ui_observed'])
            else:
                self.assertIn(req['test'],checks)
        for screen in plan['screens']:
            self.assertEqual(nodes['screen-'+screen['id']]['type'],'screen')
            self.assertTrue((APP/'templates'/screen['template']).is_file(),screen['id'])
            self.assertTrue(all(nodes[req]['type']=='requirement' for req in screen['requirements']))
        status=read(DESIGN/'source-status.json')
        self.assertEqual(status['approval'],'not-recorded')
        self.assertEqual(status['actual_captures'],2*len(plan['screens']))
        self.assertEqual(status['pending_measurements'],[])

    def test_preserved_native_allocation_and_reuse_reports_match_their_inputs(self):
        def design(name):
            return read(DESIGN/(name+'.json'))
        def styles(layout):
            return {k:len(v) for k,v in layout['candidates'][0]['control_styles'].items()}
        g4=design('control-baseline-r4-graph')
        g5=design('native-graph-baseline-r5')
        report=design('control-reuse-regression-r4-r5')
        self.assertEqual(styles(design('control-baseline-r4-native-layout')),report['previous_styles'])
        self.assertEqual(styles(design('native-allocation-baseline-r5')),report['current_styles'])
        self.assertEqual(sum(report['previous_styles'].values()),report['previous_declared_mains'])
        self.assertEqual(sum(report['current_styles'].values()),report['current_declared_mains'])
        self.assertEqual(g4['draft_prototype']['bindings'],g5['draft_prototype']['bindings'])
        by_state={(r['state'],r['viewport']):r for r in design('snapshot-baseline-r5')['snapshots']}
        for row in report['unchanged_capture_and_snapshot_hash_pairs']:
            screen=by_state[row['state'],row['viewport']]
            self.assertEqual((row['capture_sha256'],row['html_sha256']),(screen['capture_sha256'],screen['html_sha256']))
        r6=design('native-allocation-r6-report')
        protected=design('r6-protected-input-baseline')['files']
        self.assertEqual(len(protected),r6['protected_input_count'])
        projections = {r['path']:r for r in design('observation-provenance')['projections']}
        for row in protected:
            path = DESIGN/row['path']
            expected = row['sha256']
            if row['path'] in projections:
                projection = projections.pop(row['path'])
                self.assertEqual(projection['sourceSha256'], expected)
                expected = projection['publishedSha256']
                data = read(path)
                self.assertNotIn('fileKey',data)
                self.assertRegex(data['fileKeySha256'], r'^[0-9a-f]{64}$')
                canonical = json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
                self.assertEqual(hashlib.sha256(canonical).hexdigest(),projection['publicDataSha256'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),expected,row['path'])
        self.assertFalse(projections)
        self.assertTrue(r6['brand_control_allocations'] and r6['hero_label_normalizations'])
        qa=design('native-qa-summary')
        self.assertEqual(qa['status'],'scoped-verification-record')
        self.assertTrue(qa['pending'] and qa['limits'])
        self.assertRegex(qa['source_commit'],r'^[0-9a-f]{40}$')
        groups=design('grouping-qa')
        self.assertEqual(groups['observed']['groups'],len(groups['groups']))
        for row in groups['groups']:
            self.assertEqual(row['group']['kind'],'group')
            self.assertTrue(row['group']['children'])
            self.assertIn((row['state'],row['viewport']),by_state)


if __name__=='__main__':
    unittest.main()
