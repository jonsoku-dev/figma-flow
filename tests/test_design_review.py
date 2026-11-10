"""Synthetic local evidence validates the gate, never proves a real visual review/generation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_review
import asset_batch
import check_project
import prepare_design_review


def png(width, height, color):
    def chunk(kind, raw):
        return struct.pack('>I', len(raw)) + kind + raw + struct.pack('>I', zlib.crc32(kind + raw) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress((b'\0' + bytes(color) * width) * height)) + chunk(b'IEND', b''))


class DesignReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.paths = {}
        for identity in design_review.SKILLS:
            path = self.base / identity / 'SKILL.md'
            path.parent.mkdir()
            path.write_text('---\nname: ' + identity + '\n---\nExplicit synthetic skill fixture.\n')
            self.paths[identity] = path
        resolver = patch.object(design_review, 'resolve_skill', side_effect=lambda identity: self.paths[identity].resolve())
        managed = patch.object(design_review, 'generated_artifact_root', return_value=self.base / 'generated')
        managed.start()
        self.addCleanup(managed.stop)
        resolver.start()
        self.addCleanup(resolver.stop)
        (self.base / 'app.html').write_text('<main id="hero"><h1 id="title">Real target text with specific hierarchy</h1></main>')
        (self.base / 'font-first.md').write_text('Compared two rendered font candidates before the target UI authoring stage.')
        self.artifacts = [self.pin('app.html')]
        self.hashes = {p['path']: p['sha256'] for p in self.artifacts}
        for name, width, color in [('font-desktop', 1200, (1, 2, 3)), ('font-mobile', 390, (2, 3, 4)),
                                   ('before', 1200, (5, 6, 7)), ('final-desktop', 1200, (8, 9, 10)), ('final-mobile', 390, (11, 12, 13))]:
            (self.base / (name + '.png')).write_bytes(png(width, 600, color))
        self.sample = 'Actual title and body specimen uses the selected target language.'
        desktop, mobile = self.capture('final-desktop', 1200, final=True), self.capture('final-mobile', 390, final=True)
        self.receipt = {'schema': 'figma-flow-design-review-v1', 'artifacts': self.artifacts,
            'skills': [{'id': identity, 'source': str(path), 'sha256': self.pin(str(path))['sha256'],
                        'application': {'target': 'app.html', 'decision': 'Use the actual target hierarchy and type rhythm to govern the final responsive composition.',
                                        'phases': ['before-authoring', 'after-critique']}} for identity, path in self.paths.items()],
            'font_selection': {'sequence': 1, 'sample_text': self.sample,
                'candidates': [{'family': 'Candidate A', 'script': 'latin'}, {'family': 'Candidate B', 'script': 'latin'}],
                'chosen': [{'role': 'heading', 'family': 'Candidate A', 'reason': 'The open counters and width support the actual title at mobile width.'}],
                'decision': self.pin('font-first.md'), 'specimens': [self.capture('font-desktop', 1200), self.capture('font-mobile', 390)]},
            'authoring': {'sequence': 2}, 'critique': {'sequence': 3, 'reviewer': 'explicit synthetic test reviewer',
                'findings': [{'id': 'type', 'dimension': 'typography', 'target': 'app.html', 'locator': '#title',
                              'observation': '#title has crowded lines in the recorded initial desktop composition.',
                              'fix': 'Reduce title scale and increase line-height to preserve the actual title rhythm.',
                              'before_value': '64px/1', 'after_value': '52px/1.12', 'status': 'fixed',
                              'before': self.pin('before.png'), 'after': self.pin('final-desktop.png')},
                             {'id': 'layout', 'dimension': 'composition', 'target': 'app.html', 'locator': '#hero',
                              'observation': '#hero leaves the action disconnected from the principal reading path.',
                              'fix': 'Align the action with the title baseline and reduce the excessive opening gap.',
                              'before_value': 120, 'after_value': 64, 'status': 'fixed',
                              'before': self.pin('before.png'), 'after': self.pin('final-desktop.png')}],
                'confirmation': {'sequence': 4, 'captures': [desktop, mobile]}}}
        self.declaration = {'operation': 'create', 'target_kind': 'website', 'receipt': 'review.json'}

    def pin(self, name):
        path = Path(name) if Path(name).is_absolute() else self.base / name
        return {'path': str(name), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def capture(self, name, width, final=False):
        item = dict(self.pin(name + '.png'), viewport='desktop' if width >= 1000 else 'mobile', width=width, height=600,
                    tool='stagehand', target='http://127.0.0.1:1234/specimen' if not final else 'http://127.0.0.1:1234/',
                    observed_at='2026-11-09T02:00:00Z')
        if final:
            item['artifact_hashes'] = self.hashes
        else:
            item.update(text=self.sample, fonts=[{'family': 'Candidate A', 'loaded': True}, {'family': 'Candidate B', 'loaded': True}])
        return item

    def evaluate(self, receipt=None, declaration=None, request=''):
        (self.base / 'review.json').write_text(json.dumps(receipt if receipt is not None else self.receipt))
        return design_review.evaluate(self.base, declaration if declaration is not None else self.declaration, request_text=request, inspection=True)

    def test_current_concrete_evidence_passes_but_never_claims_skill_or_platform_attestation(self):
        result = self.evaluate()
        self.assertTrue(result['passed'], result['errors'])
        self.assertIn('do not prove', result['evidence_boundary'])
        self.assertIn(str((self.base / 'app.html').resolve()), result['pinned_files'])

    def test_missing_font_only_fake_generic_and_stale_evidence_fail(self):
        mutations = [lambda r: r.clear(), lambda r: r.pop('critique'),
                     lambda r: r['font_selection'].pop('specimens'),
                     lambda r: r['skills'].clear(),
                     lambda r: r['critique']['findings'][0].update(observation='Looks good.'),
                     lambda r: r['critique']['findings'][0].update(locator='#invented'),
                     lambda r: r['critique']['findings'][0].update(after_value='64px/1'),
                     lambda r: r['critique']['confirmation']['captures'][0].update(artifact_hashes={})]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                receipt = copy.deepcopy(self.receipt)
                mutation(receipt)
                self.assertFalse(self.evaluate(receipt)['passed'])
        self.assertFalse(design_review.evaluate(self.base, None, required=True, inspection=True)['passed'])
        (self.base / 'app.html').write_text('changed current artifact')
        self.assertFalse(self.evaluate()['passed'])

    def test_korean_requires_target_script_specimens_not_latin_only(self):
        self.assertFalse(self.evaluate(request='한국어 캠페인을 처음부터 제작한다.')['passed'])
        receipt = copy.deepcopy(self.receipt)
        receipt['font_selection']['sample_text'] = '오늘의 이야기를 실제 한국어 제목과 본문으로 비교합니다.'
        for specimen in receipt['font_selection']['specimens']:
            specimen['text'] = receipt['font_selection']['sample_text']
        self.assertTrue(self.evaluate(receipt, request='한국어 웹을 제작한다.')['passed'])

    def clean_checks(self, game=False):
        criteria = ['typography', 'composition', 'desktop', 'mobile', 'click_area']
        if game:
            criteria += ['focal_crop', 'heading_treatment', 'control_treatment']
        return [{'criterion': criterion, 'target': 'app.html', 'locator': '#title',
                 'observation': '#title keeps the recorded type measure and visible reading hierarchy.',
                 'observed_value': {'line_count': 2, 'clipping': False}, 'status': 'pass',
                 'capture': 'final-mobile.png' if criterion == 'mobile' else 'final-desktop.png'} for criterion in criteria]

    def test_substantiated_clean_review_and_explicit_project_root(self):
        receipt = copy.deepcopy(self.receipt)
        receipt['critique']['findings'] = []
        receipt['critique']['checks'] = self.clean_checks()
        self.assertTrue(self.evaluate(receipt)['passed'])
        receipt['critique']['checks'][0]['observation'] = 'All checks passed'
        self.assertFalse(self.evaluate(receipt)['passed'])
        (self.base / 'handoff').mkdir()
        (self.base / 'review.json').write_text(json.dumps(self.receipt))
        declaration = dict(self.declaration, project_root='..', receipt='../review.json')
        result = design_review.evaluate(self.base / 'handoff', declaration, inspection=True)
        self.assertTrue(result['passed'], result['errors'])

    def test_default_frontend_creation_blocks_missing_entire_review_and_inspection_never_claims_design(self):
        import shutil
        project = self.base / 'project'
        shutil.copytree(ROOT / 'examples/idea-notes', project)
        output = self.base / 'creation'
        import design_directions
        with self.assertRaises(design_directions.SelectionRequired):
            check_project.init_project(project / 'brief.md', project / 'graph.json', project / 'bindings.json', output)
        self.assertFalse(output.exists())
        output = self.base / 'inspection'
        status = check_project.init_project(project / 'brief.md', project / 'graph.json', project / 'bindings.json', output, intent='inspect')
        self.assertEqual(status, 0)
        self.assertEqual(json.loads((output / 'summary.json').read_text())['design_completion'], 'not-claimed')
        data = {'nodes': [{'type': 'code', 'source': 'api.py'}]}
        self.assertFalse(design_review.frontend(data, {'authorities': {'implementation': 'api.py'}}))

    def add_asset(self):
        (self.base / 'concept.md').write_text('One frozen original game concept shared by every production role.')
        (self.base / 'reference.png').write_bytes(png(40, 40, (90, 80, 70)))
        (self.base / 'original.png').write_bytes(png(80, 80, (20, 30, 40)))
        (self.base / 'generated').mkdir()
        (self.base / 'generated/explicit-synthetic-fixture.png').write_bytes((self.base / 'original.png').read_bytes())
        (self.base / 'logo.png').write_bytes((self.base / 'original.png').read_bytes())
        batch = {'schema': 'figma-flow-asset-batch-v1', 'batch_id': 'fixture-v1', 'game_id': 'fixture',
                 'concept': dict(self.pin('concept.md'), id='fixture', version='1'),
                 'references': [self.pin('reference.png')], 'roles': [{'id': 'brand', 'kind': 'logo'}]}
        (self.base / 'batch.json').write_text(json.dumps(batch))
        self.receipt['asset_batch'] = self.pin('batch.json')
        self.receipt['assets'] = [{'role_id': 'brand', 'batch_id': 'fixture-v1', 'source': self.pin('original.png'),
            'generation': {'tool': 'image_gen.imagegen', 'tool_call_id': 'explicit-synthetic-fixture', 'evidence': {}},
            'derivative': dict(self.pin('logo.png'), operations=[]),
            'usage': [{'target': 'app.html', 'locator': '#logo', 'visible': True, 'capture': 'final-desktop.png', 'bounds': [0, 0, 80, 80], 'semantic_role': 'brand_mark', 'purpose': 'Identify the project brand in the page header.', 'observation': 'brand is visibly displayed as the generated mark in the final state.', 'source_sha256': self.pin('logo.png')['sha256']}]}]
        html = self.base / 'app.html'
        html.write_text(html.read_text() + '<img id="logo" src="logo.png" alt="Generated brand">')
        self.receipt['artifacts'] = [self.pin('app.html')]
        hashes = {p['path']: p['sha256'] for p in self.receipt['artifacts']}
        for capture in self.receipt['critique']['confirmation']['captures']:
            capture['artifact_hashes'] = hashes
        context = (self.base / 'concept.md').read_text()
        event = {'tool': 'image_gen.imagegen', 'tool_call_id': 'explicit-synthetic-fixture',
                 'input': {'role_ids': ['brand'], 'prompt': context + ' ' + batch['concept']['sha256'] + ' ' + batch['references'][0]['sha256'],
                           'batch_id': 'fixture-v1', 'batch_sha256': self.pin('batch.json')['sha256'],
                           'context_sha256': batch['concept']['sha256'], 'context_text': context,
                           'reference_sha256': [batch['references'][0]['sha256']], 'referenced_image_paths': ['reference.png']},
                 'output': {'image_path': str(self.base / 'generated/explicit-synthetic-fixture.png'), 'sha256': self.pin('original.png')['sha256'], 'mime_type': 'image/png'}}
        (self.base / 'generation.json').write_text(json.dumps(event))
        self.receipt['assets'][0]['generation']['evidence'] = self.pin('generation.json')

    def test_generated_raster_chain_passes_manual_svg_bare_manifest_unused_and_mixed_batch_fail(self):
        self.add_asset()
        self.assertTrue(self.evaluate()['passed'])
        for mutate in (lambda r: r['assets'][0].update(batch_id='other-game'),
                       lambda r: r['assets'][0].update(usage=[]),
                       lambda r: r['assets'][0]['generation'].update(evidence=self.pin('batch.json')),
                       lambda r: r['assets'][0]['usage'][0].update(source_sha256='0' * 64),
                       lambda r: r['assets'].clear()):
            receipt = copy.deepcopy(self.receipt)
            mutate(receipt)
            self.assertFalse(self.evaluate(receipt)['passed'])
        (self.base / 'manual.svg').write_text('<svg><path d="M0 0h20v20z"/></svg>')
        receipt = copy.deepcopy(self.receipt)
        receipt['assets'][0]['source'] = self.pin('manual.svg')
        self.assertFalse(self.evaluate(receipt)['passed'])
        self.assertFalse(self.evaluate(declaration=dict(self.declaration, target_kind='game-campaign', game_id='fixture'))['passed'])

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow required for optional raster transform validation')
    def test_replayed_crop_resize_pixels_and_extra_content_rejection(self):
        from PIL import Image
        self.add_asset()
        image = Image.open(self.base / 'original.png').crop((5, 6, 70, 60)).resize((100, 90), Image.Resampling.LANCZOS).convert('RGBA')
        image.save(self.base / 'logo.png')
        operations = [{'op': 'crop', 'box': [5, 6, 70, 60]}, {'op': 'resize', 'size': [100, 90], 'resample': 'LANCZOS'}, {'op': 'convert', 'mode': 'RGBA'}, {'op': 'format', 'format': 'PNG'}]
        self.receipt['assets'][0]['derivative'] = dict(self.pin('logo.png'), operations=operations)
        self.receipt['assets'][0]['usage'][0]['source_sha256'] = self.pin('logo.png')['sha256']
        self.assertTrue(self.evaluate()['passed'])
        image.putpixel((0, 0), (255, 0, 0, 255))
        image.save(self.base / 'logo.png')
        self.receipt['assets'][0]['derivative'].update(self.pin('logo.png'))
        self.receipt['assets'][0]['usage'][0]['source_sha256'] = self.pin('logo.png')['sha256']
        self.assertFalse(self.evaluate()['passed'])

    def test_game_skins_need_real_text_growth_corners_padding_and_visible_product_usage(self):
        self.add_asset()
        kinds = ['logo', 'icon', 'character', 'key_art', 'section_title', 'button_frame']
        html = self.base / 'app.html'
        html.write_text(html.read_text() + '<div id="chapter-content">Actual content wrapper</div><style>.skin{display:inline-flex;width:max-content;height:auto;border-image:url(logo.png) 8 fill/8px stretch}</style>' +
                        ''.join(f'<div id="slot-{kind}"><img src="logo.png"><span>PLAY</span></div>' for kind in kinds))
        self.receipt['artifacts'] = [self.pin('app.html')]
        hashes = {p['path']: p['sha256'] for p in self.receipt['artifacts']}
        batch = json.loads((self.base / 'batch.json').read_text())
        batch['roles'] = [{'id': kind, 'kind': kind} for kind in kinds]
        (self.base / 'batch.json').write_text(json.dumps(batch))
        self.receipt['asset_batch'] = self.pin('batch.json')
        event = json.loads((self.base / 'generation.json').read_text())
        event['input'].update(batch_sha256=self.pin('batch.json')['sha256'], role_ids=kinds)
        (self.base / 'generation.json').write_text(json.dumps(event))
        original = self.receipt['assets'][0]
        self.receipt['assets'] = []
        for kind in kinds:
            asset = copy.deepcopy(original)
            asset['role_id'] = kind
            asset['generation']['evidence'] = self.pin('generation.json')
            asset['usage'][0].update(semantic_role=kind, purpose='Role-specific generated imagery for its actual semantic function.', locator='#slot-' + kind, observation=kind + ' is actually visible in the recorded product state.', text_mode='live-text', label_text='PLAY')
            self.receipt['assets'].append(asset)
        self.receipt['critique']['findings'] = []
        self.receipt['critique']['checks'] = self.clean_checks(game=True)
        captures = self.receipt['critique']['confirmation']['captures']
        for capture in captures:
            capture['artifact_hashes'] = hashes
        for name, color in [('short-probe', (20, 50, 80)), ('long-probe', (30, 70, 100))]:
            (self.base / (name + '.png')).write_bytes(png(320, 600, color))
            capture = self.capture(name, 320, final=True)
            capture.update(state='responsive-probe', artifact_hashes=hashes)
            captures.append(capture)
        self.receipt['responsive_skins'] = []
        for kind in ('section_title', 'button_frame'):
            observations = []
            for label, width, capture in [('PLAY', 80, 'short-probe.png'), ('PLAY THE NEXT ROUND', 180, 'long-probe.png')]:
                observations.append({'label': label, 'frame': [0, 0, width, 60], 'label_bounds': [10, 10, width - 20, 40],
                    'padding': [10, 10, 10, 10], 'corners': [[8, 8]] * 4, 'viewport_width': 320, 'capture': capture,
                    'source_layout': {'display': 'inline-flex', 'width': 'max-content', 'height': 'auto', 'border_model': 'nine-slice'}})
            evidence = {'surface': 'web', 'locator': '#slot-' + kind, 'observations': observations}
            if kind == 'section_title':
                evidence['title_for'] = '#chapter-content'
                for observation in observations:
                    observation.update(content_bounds=[0, 80, 300, 100], next_bounds=[0, 200, 300, 100])
            (self.base / (kind + '-probe.json')).write_text(json.dumps(evidence))
            self.receipt['responsive_skins'].append(dict(evidence, role_id=kind, target='app.html', model='nine-slice',
                source=self.pin('app.html'), evidence=self.pin(kind + '-probe.json')))
        declaration = dict(self.declaration, target_kind='game-campaign', game_id='fixture')
        result = self.evaluate(declaration=declaration)
        self.assertTrue(result['passed'], result['errors'])
        for field, value in [('frame', [0, 0, 80, 60]), ('corners', [[12, 12]] * 4), ('label_bounds', [10, 10, 300, 40]),
                             ('source_layout', {'width': '200px'})]:
            receipt = copy.deepcopy(self.receipt)
            skin = receipt['responsive_skins'][0]
            skin['observations'][1][field] = value
            evidence_path = self.base / 'bad-probe.json'
            evidence_path.write_text(json.dumps({k: skin[k] for k in ('surface', 'locator', 'observations', 'title_for') if k in skin}))
            skin['evidence'] = self.pin('bad-probe.json')
            self.assertFalse(self.evaluate(receipt, declaration=declaration)['passed'])
        receipt = copy.deepcopy(self.receipt)
        receipt['assets'][0]['usage'][0]['capture'] = 'long-probe.png'
        self.assertFalse(self.evaluate(receipt, declaration=declaration)['passed'])

    def test_prepare_profile_pins_actual_observations_and_preserves_missing_evidence_as_blocked(self):
        (self.base / 'applications.json').write_text(json.dumps({s['id']: s['application'] for s in self.receipt['skills']}))
        (self.base / 'font.json').write_text(json.dumps(self.receipt['font_selection']))
        (self.base / 'critique.json').write_text(json.dumps(self.receipt['critique']))
        prepared = prepare_design_review.prepare(self.base, self.base / 'prepared', ['app.html'],
            applications=self.base / 'applications.json', font=self.base / 'font.json', critique=self.base / 'critique.json')
        declaration = json.loads(Path(prepared['declaration']).read_text())['design_review']
        result = design_review.evaluate(self.base, declaration, inspection=True)
        self.assertTrue(result['passed'], result['errors'])
        pending = prepare_design_review.prepare(self.base, self.base / 'pending', ['app.html'])
        declaration = json.loads(Path(pending['declaration']).read_text())['design_review']
        self.assertFalse(design_review.evaluate(self.base, declaration, inspection=True)['passed'])
        self.assertEqual(pending['status'], 'prepared-not-reviewed')
        bad = copy.deepcopy(self.receipt['font_selection'])
        bad['decision']['sha256'] = '0' * 64
        (self.base / 'bad-font.json').write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, 'mismatched original'):
            prepare_design_review.prepare(self.base, self.base / 'bad-prepared', ['app.html'], font=self.base / 'bad-font.json')

    def test_asset_batch_freezes_context_and_complete_inventory_before_generation(self):
        (self.base / 'concept.md').write_text('Exact common game context before any role production.')
        (self.base / 'reference.png').write_bytes(png(20, 20, (1, 2, 3)))
        roles = [kind + ':' + kind for kind in ('logo', 'icon', 'character', 'key_art', 'section_title', 'button_frame')]
        out = self.base / 'production'
        from direction_fixture import selected_direction
        from workflow import State
        with selected_direction(self.base) as admitted:
            result = asset_batch.freeze(self.base / 'concept.md', [self.base / 'reference.png'], roles, out,
                                        batch_id='v1', game_id='game', concept_id='concept', version='1', selection_path=admitted.selection_path)
            self.assertEqual(result['workflow_state'], State.BATCH_FROZEN.value)
            packet = json.loads((out / 'generation-requests.json').read_text())
            self.assertEqual(len(packet['requests']), len(roles))
            for request in packet['requests']:
                self.assertEqual(request['tool'], 'image_gen.imagegen')
                self.assertEqual(request['evidence_input']['batch_sha256'], result['batch_sha256'])
                self.assertIn((self.base / 'concept.md').read_text(), request['args']['prompt'])
            self.assertIn((self.base / 'concept.md').read_text(), (out / 'shared-prompt.txt').read_text())
            with self.assertRaises(FileExistsError):
                asset_batch.freeze(self.base / 'concept.md', [self.base / 'reference.png'], roles, out,
                                   batch_id='v1', game_id='game', concept_id='concept', version='1', selection_path=admitted.selection_path)



if __name__ == '__main__':
    unittest.main()
