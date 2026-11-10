"""Self-contained draft tests. Mocks/Pillow demos are never live Figma evidence."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('figma_draft',ROOT/'tools/figma_draft.py')
draft=importlib.util.module_from_spec(spec);spec.loader.exec_module(draft)
EXAMPLE=ROOT/'examples/native-direction-review'
demo_spec=importlib.util.spec_from_file_location('native_review_demo',EXAMPLE/'demo.py')
demo=importlib.util.module_from_spec(demo_spec);demo_spec.loader.exec_module(demo)


def file_hashes(folder):
    import hashlib
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()for p in folder.rglob('*')if p.is_file()and'__pycache__'not in p.parts}


class DraftReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.project=Path(cls.temp.name)/'workshop'
        cls.before=file_hashes(EXAMPLE)
        cls.result=demo.instantiate(cls.project)
        cls.manifest=Path(cls.result['manifest'])

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_default_is_native_pending_without_selection_or_foreign_context(self):
        data=json.loads(self.manifest.read_text())
        self.assertEqual(data['workflow_symbol'],'NATIVE_REVIEW_PENDING')
        self.assertEqual(data['review_destination'],'figma')
        self.assertEqual(data['native_target'],{'mode':'current-design-file'})
        self.assertNotIn('selection',data)
        self.assertFalse(any(self.project.rglob('*selection*.json')))
        self.assertEqual(self.before,file_hashes(EXAMPLE))

    def test_two_non_game_directions_have_exact_native_controls_and_returns(self):
        packet=draft.make_packet(self.manifest)
        self.assertEqual({c['id']for c in packet['candidates']},{'bulletin','agenda'})
        self.assertIsNone(packet['fileKey'])
        self.assertFalse(packet['production_admitted'])
        self.assertEqual(packet['execution_status'],'prepared-not-executed')
        self.assertEqual(packet['layout_sha256'],json.loads(self.manifest.read_text())['native_layout']['sha256'])
        count=0
        for c in packet['candidates']:
            self.assertNotIn(c['prototype']['states'][0]['view'],('reveal','pass','teaser'))
            for viewport,states in c['state_layouts'].items():
                for state_id,state in states.items():
                    self.assertTrue(any(l['kind']=='text'for l in state['layers']))
                    expected={e['control_id']for e in c['prototype']['bindings']if e['viewport']==viewport and e['source_state']==state_id}
                    self.assertEqual(set(state['control_boxes']),expected);count+=len(expected)
        self.assertEqual(count,8)

    def test_unused_named_color_stops_the_normal_cli_before_writing_a_draft(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / 'example'
            shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns('__pycache__'))
            spec_path = project / 'candidate-spec.json'
            spec = json.loads(spec_path.read_text())
            row = spec['candidates'][0]
            graph_path = project / row['graph']
            graph = json.loads(graph_path.read_text())
            color = next(r for r in graph['design_foundations']['roles'] if r['kind'] == 'color')
            role = dict(color, name='Unused duplicate', token='color/unplayed', alias='palette/unplayed')
            graph['design_foundations']['roles'].append(role)
            graph_path.write_text(json.dumps(graph))
            with (project / row['review']).open('a') as review:
                review.write('<p>' + ' '.join(str(v) for v in role.values()) + '</p>')
            layout_path = project / spec['native_layout']['path']
            layout = json.loads(layout_path.read_text())
            authored = next(c for c in layout['candidates'] if c['id'] == row['id'])
            authored['colors']['unplayed'] = role['value']
            authored['graph']['sha256'] = hashlib.sha256(graph_path.read_bytes()).hexdigest()
            layout_path.write_text(json.dumps(layout))
            spec['native_layout']['sha256'] = hashlib.sha256(layout_path.read_bytes()).hexdigest()
            spec_path.write_text(json.dumps(spec))
            output = project / 'new-review'
            result = subprocess.run([sys.executable, '-B', str(ROOT/'tools/design_actions.py'),
                'draft', '--project', str(project), '--brief', 'brief.md', '--research', 'research.md',
                '--from-existing', str(spec_path), '--out', str(output)], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('color/unplayed', json.loads(result.stderr)['blocked_reason'])
            self.assertFalse(output.exists())

    def test_generic_portable_package_never_registers_or_approves(self):
        output=self.project/'portable'
        with patch.object(draft,'PRIVATE',self.project/'forbidden-private'):
            result=draft.prepare(self.manifest,output,plugin_id='1000000000000000001')
        self.assertEqual(result['status'],'prepared-not-executed')
        self.assertEqual(result['warnings'], [])
        self.assertFalse((self.project/'forbidden-private').exists())
        packaged=json.loads((output/'plugin/manifest.json').read_text())
        self.assertEqual(packaged['id'],'1000000000000000001')
        self.assertNotIn('NIGHT',packaged['name'])
        self.assertEqual(json.loads(self.manifest.read_text())['workflow_symbol'],'NATIVE_REVIEW_PENDING')
        self.assertFalse(any(self.project.rglob('*selection*.json')))
        subprocess.run(['node','--check',str(output/'plugin/code.js')],check=True,capture_output=True)

    def test_large_embedded_previews_warn_on_normal_cli_without_blocking(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            shutil.copytree(EXAMPLE, source)
            layout_path = source / 'native-layout.json'
            layout = json.loads(layout_path.read_text())
            for asset in layout['assets'].values():
                if 'desktop' in asset['path']:
                    path = source / asset['path']
                    with Image.open(path) as image:
                        image.copy().save(path, compress_level=0)
                    asset['sha256'] = demo.pin(path)
            demo.dump(layout_path, layout)
            with patch.object(demo, 'EXAMPLE', source):
                manifest = demo.instantiate(root / 'project')['manifest']
            out = root / 'prepared'
            command = [sys.executable, '-B', str(ROOT / 'tools/design_actions.py'), 'prepare-native-review',
                       '--manifest', str(manifest), '--plugin-id', '12345', '--out', str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            packet = json.loads((out / 'packet.json').read_text())
            size = sum(len(data) for data in packet['assets'].values())
            self.assertGreater(size, 4_000_000)
            warnings = json.loads(result.stdout)['warnings']
            self.assertIn(f'{size:,} base64 bytes', warnings[0])
            self.assertEqual(json.loads((out / 'prepared.json').read_text())['warnings'], warnings)
            self.assertTrue((out / 'Figma-Direction-Review.zip').is_file())

    def test_implicit_demo_registration_fails_before_side_effects(self):
        output=self.project/'must-not-exist'
        with patch.object(draft.design_directions,'admit_native_draft')as admission:
            with self.assertRaises(ValueError):draft.prepare(self.manifest,output,register=True)
            admission.assert_not_called()
        self.assertFalse(output.exists())

    def test_private_demo_needs_explicit_matching_owner_pins(self):
        for env, kwargs in [({}, {}),
                            ({'FIGMA_FLOW_NIGHT_FILE_KEY': 'owned', 'FIGMA_FLOW_NIGHT_PLUGIN_ID': '123'},
                             {'file_key': 'another'}),
                            ({'FIGMA_FLOW_NIGHT_FILE_KEY': 'owned', 'FIGMA_FLOW_NIGHT_PLUGIN_ID': '123'},
                             {'plugin_id': '456'})]:
            with self.subTest(kwargs=kwargs), patch.dict(os.environ, env, clear=True), patch.object(draft, 'make_packet') as make:
                with self.assertRaises(ValueError):
                    draft.prepare(self.manifest, self.project/'never-written', register=True, night_demo=True, **kwargs)
                make.assert_not_called()

    def test_wrong_owned_layout_is_rejected(self):
        with tempfile.NamedTemporaryFile(suffix='.json')as file:
            with self.assertRaises(ValueError):draft.make_packet(self.manifest,file.name)

    def test_ui_and_wrong_file_mock_do_not_author(self):
        with tempfile.TemporaryDirectory()as folder:
            script=Path(folder)/'ui.js';script.write_text(re.search(r'<script>([\s\S]*)</script>',draft.ui_html()).group(1));subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
            code="""const fs=require('fs'),vm=require('vm'),assert=require('assert');const messages=[];let creates=0;const figma={fileKey:'wrong',ui:{postMessage:m=>messages.push(m)},showUI:()=>{},createPage:()=>{creates++;throw Error('must not create')}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{DRAFT:{fileKey:'expected'},figma,__html__:''});(async()=>{await figma.ui.onmessage({type:'select-direction'});await figma.ui.onmessage({type:'draft-review'});assert.equal(creates,0);assert(messages.some(m=>m.message&&m.message.includes('Figma')));})();"""
            subprocess.run(['node','-e',code,str(ROOT/'figma-bridge/direction_review.js')],check=True,capture_output=True)


class CopiedPackageTests(unittest.TestCase):
    def test_installed_copy_needs_no_sibling_project(self):
        with tempfile.TemporaryDirectory()as folder:
            copied=Path(folder)/'plugin'
            shutil.copytree(ROOT,copied,ignore=shutil.ignore_patterns('__pycache__','.git'))
            self.assertEqual([p.name for p in Path(folder).iterdir()],['plugin'])
            result=subprocess.run([sys.executable,str(copied/'tests/test_figma_draft.py'),'DraftReviewTests'],cwd=copied,check=False,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('skipped',result.stderr)


class OptionalLiveReadbackTests(unittest.TestCase):
    """Opt-in operator evidence only; never a package/example prerequisite."""
    @unittest.skipUnless(os.getenv('FIGMA_DRAFT_LIVE_MANIFEST')and os.getenv('FIGMA_DRAFT_LIVE_READBACK'),'Optional operator evidence not supplied')
    def test_supplied_native_evidence_and_tampering(self):
        manifest=Path(os.environ['FIGMA_DRAFT_LIVE_MANIFEST']);current=Path(os.environ['FIGMA_DRAFT_LIVE_READBACK'])
        self.assertTrue(draft.verify_native_review(manifest,current)['passed'])
        for mutation in('reaction','design-link'):
            raw=json.loads(current.read_text())
            if mutation=='reaction':next(n for n in raw['nodes']if n.get('type')=='INSTANCE'and n.get('reactions'))['reactions'][0]['actions'][0]['destinationId']='missing-target'
            else:
                entry=next(iter(raw['noteFrames'].values()))['entries'][0]
                next(n for n in raw['nodes']if n['id']==entry['textNodeId'])['hyperlink']={'type':'NODE','value':'unrelated-target'}
            with self.subTest(mutation=mutation),tempfile.NamedTemporaryFile(suffix='.json',mode='w')as file:
                json.dump(raw,file);file.flush();self.assertFalse(draft.verify_native_review(manifest,file.name)['passed'])


if __name__=='__main__':unittest.main()
