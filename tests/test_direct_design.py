"""Local synthetic artifact/provenance tests, never visual-quality evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import design_critique
import design_directions as d
import design_intent
from workflow import State
from direction_fixture import selected_direction, write

REQUEST = 'Local HTML only. Create one direction for Fixture title and Open the note without comparison.'


def critique(data):
    return {'schema': design_critique.SCHEMA, 'role': 'agent', 'brief': data['brief'],
            'native_layout': data.get('native_layout'), 'draft_content_sha256': d.digest(data['candidates']),
            'warning_dispositions': [], 'candidates': [dict(
                {k: c[k] for k in ('id', 'composition', 'typography', 'interaction')},
                truth_and_notes='The source exposes the reading action and its planned note.',
                candidate_sha256=c['sha256'], artifacts={k: c[k] for k in ('source', 'review', 'product_graph', 'previews')},
                observations=[{'aspect': a, 'artifact': 'source', 'locator': 'Fixture title', 'excerpt': 'Open the note',
                               'observation': {'purpose': 'The reading purpose is expressed by Fixture title and its adjacent open action.',
                                   'content_hierarchy': 'Fixture title occurs before Open the note in the source reading order.',
                                   'typography': 'The title uses the inherited document typography in this structural fixture.',
                                   'layout': 'The main element groups the heading and note action within one reading region.',
                                   'assets': 'The utility reading screen has no decorative imagery in the supplied source.',
                                   'responsive': 'The source content remains identical across the pinned mobile and desktop fixtures.',
                                   'interaction': 'The source script binds its button action to the show handler for the note.'}[a],
                               'reason': 'The reader can identify the note before opening its detail from the action.',
                               'resolution': 'clean'} for a in ('purpose', 'content_hierarchy', 'typography', 'layout', 'assets', 'responsive', 'interaction')])
                for c in data['candidates']]}


def make_direct(f, request=REQUEST, anchors=None):
    old = json.loads(f.manifest.read_text())
    root = f.manifest.parent.parent
    brief = root / 'direct-brief.md'; brief.write_text(('' if request.startswith('Figma') else 'Local HTML only.\n') + request)
    c = old['candidates'][0]
    item = {k: c[k] for k in ('id', 'title', 'composition', 'typography', 'interaction')}
    item.update(source=c['source']['path'], review=c['review']['path'], graph=c['product_graph']['path'],
                previews=[dict(viewport=p['viewport'], width=p['width'], height=p['height'], path=p['file']['path']) for p in c['previews']])
    spec = {'content': old['content'], 'candidates': [item], 'direct_instruction': {'request_text': request,
             'anchors': anchors if anchors is not None else [{'artifact': 'brief', 'excerpt': request}, {'artifact': 'source', 'excerpt': 'Fixture title'}]}}
    result = d.create_draft(old['project_root'], brief, old['research']['path'], spec, root / 'direct', review_destination='figma' if request.startswith('Figma') else 'local', mode='direct')
    manifest = Path(result['manifest']); data = json.loads(manifest.read_text())
    review = write(root / 'direct-critique.json', critique(data))
    d.review_draft(manifest, review)
    return manifest, review


class DirectDesignTests(unittest.TestCase):
    def test_intent_unresolved_specific_and_comparison(self):
        for text, mode in [('Build a nice landing page', 'inspect-context'), (REQUEST, 'direct'),
                           ('Follow the provided design system', 'direct'),
                           ('비교 안 해도 되니 시안 하나만 만들어줘', 'direct'),
                           ("Create one design, don't compare alternatives", 'direct'),
                           ('Compare three directions then wait for my answer', 'compare'),
                           ('No comparison. Wait for my choice', 'compare'),
                           ('Compare two directions without comparing font options', 'compare')]:
            self.assertEqual(design_intent.direction_mode(text)['mode'], mode)

    def test_one_direction_actual_instruction_and_current_hashes(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, review = make_direct(f)
            self.assertEqual(json.loads(manifest.read_text())['workflow_state'], State.SELECTION_READY.value)
            self.assertFalse((manifest.parent / 'selection-prompt.txt').exists())
            self.assertNotIn('원하는 후보의 ID', (manifest.parent / 'review.html').read_text())
            out = manifest.parent / 'selection.json'
            with self.assertRaises(ValueError):
                d.record_direct_admission(manifest, f.user_event, out)
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': REQUEST}}) + '\n')
            selected = d.record_direct_admission(manifest, f.user_event, out)
            self.assertEqual(selected['authority'], 'direct-user-instruction')
            self.assertEqual(json.loads(out.read_text())['schema'], 'figma-flow-direct-design-admission-v1')
            source = Path(selected['candidate']['source']['path']); source.write_text(source.read_text() + 'changed')
            with self.assertRaises(d.SelectionRequired):
                d.require_selected(out)

    def test_short_reference_and_delegated_single_use_brief_lineage_without_source_quote(self):
        for request in ('첨부한 디자인 그대로 만들어줘', '이 화면 그대로', '시안 하나만 알아서 만들어줘', 'Pick one direction for me', 'Design one concept for the homepage.', '시안 하나만 디자인해줘'):
            with self.subTest(request=request), tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
                manifest, _ = make_direct(f, request, anchors=[{'artifact': 'brief', 'excerpt': request}])
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': request}}) + '\n')
                selected = d.record_direct_admission(manifest, f.user_event, manifest.parent / 'selection.json')
                self.assertEqual(selected['authority'], 'direct-user-instruction')
                self.assertNotIn(request, d.current(selected['candidate']['source']).read_text())

    def test_stop_and_hold_block_initial_and_cached_direct_authority(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': REQUEST}}) + '\n')
            out = manifest.parent / 'selection.json'
            d.record_direct_admission(manifest, f.user_event, out)
            admitted_transcript = f.user_event.read_text()
            for hold in ('진행하지 마', '잠깐 기다려', 'Do not proceed', 'Hold off for now'):
                with self.subTest(hold=hold):
                    f.user_event.write_text(admitted_transcript + json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': hold}}) + '\n')
                    with self.assertRaises(d.SelectionRequired):
                        d.require_selected(out)
                    with self.assertRaises(ValueError):
                        d._direct_human(d.validate_draft(manifest), f.user_event)
                    draft = d.validate_draft(manifest)
                    draft['data']['direct_instruction']['request_text'] = REQUEST + ' ' + hold
                    with self.assertRaises(ValueError):
                        d._direct_human(draft, f.user_event)
                    self.assertFalse(design_intent.authoring_requested(hold))

    def test_urls_are_context_and_do_not_supply_creation_authority(self):
        for request in ('Can you inspect https://example.com?', 'https://example.com 참고만 해줘',
                        'https://example.com', 'https://example.com/create'):
            with self.subTest(request=request), tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
                self.assertEqual(design_intent.direction_mode(request)['mode'], 'inspect-context')
                manifest, _ = make_direct(f, request, anchors=[{'artifact': 'brief', 'excerpt': request}])
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': request}}) + '\n')
                with self.assertRaises(ValueError):
                    d.record_direct_admission(manifest, f.user_event, manifest.parent / 'selection.json')
        self.assertTrue(design_intent.authoring_requested('Create a page using https://example.com'))
        self.assertEqual(design_intent.direction_mode('Create a page using https://example.com')['mode'], 'direct')

    def test_later_native_scope_restriction_invalidates_native_authority(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            request = REQUEST.replace('Local HTML only.', 'Figma native draft review.')
            manifest, _ = make_direct(f, request)
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': request}}) + '\n')
            admitted_transcript = f.user_event.read_text()
            evidence = write(manifest.parent / 'modeled-native.json', {'evidence': 'test adapter only, not actual native observation'})
            data = json.loads(manifest.read_text())
            data['native_review'] = {'readback': d.pin(evidence)}
            manifest.write_text(json.dumps(data))
            # Only local trusted test adapter stands in for native evidence; no Figma tool is invoked.
            with patch.object(d, '_native_review', return_value={'passed': True}):
                out = manifest.parent / 'selection.json'
                d.record_direct_admission(manifest, f.user_event, out)
                for restriction in ('Figma 사용하지 마. 로컬 작업만 계속해줘.', 'Text-only from now on.', 'Do not use Figma', 'Figma 작업하지 마',
                                    '피그마는 들어가지마 접근하면안돼', '텍스트만으로 진행해'):
                    with self.subTest(restriction=restriction):
                        f.user_event.write_text(admitted_transcript + json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': restriction}}) + '\n')
                        with self.assertRaises(d.SelectionRequired):
                            d.require_selected(out)

    def test_native_restriction_targeting_does_not_capture_unrelated_text_edits(self):
        for text in ('설명 텍스트만 바꾸고 Figma 작업은 계속해줘.',
                     'Figma는 유지하고 다른 앱에는 접근하지 마.',
                     'Change the text-only label in Figma.',
                     'Create one design with a text-only label.'):
            with self.subTest(text=text):
                self.assertFalse(design_intent.native_excluded(text))
        self.assertFalse(design_intent.authoring_requested('The one design concept is documented here.'))
        self.assertFalse(design_intent.authoring_requested('시안 하나만 디자인하지 마'))

    def test_optional_reference_pin_remains_current_after_admission(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            request = '첨부한 디자인 그대로 만들어줘'
            reference = f.manifest.parent.parent / 'reference.txt'
            reference.write_text('A supplied reading utility reference.')
            manifest, _ = make_direct(f, request, anchors=[{'artifact': 'brief', 'excerpt': request},
                {'artifact': 'reference', 'record': d.pin(reference)}])
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': request}}) + '\n')
            out = manifest.parent / 'selection.json'
            d.record_direct_admission(manifest, f.user_event, out)
            reference.write_text('Changed reference after admission.')
            with self.assertRaises(d.SelectionRequired):
                d.require_selected(out)

    def test_nonauthoring_policy_comparison_and_wait_requests_cannot_admit_direct(self):
        for request in ('첨부한 디자인 조사만 해줘', '첨부한 디자인 그대로 만들지 마',
                        'Use this design for research only; do not create it',
                        'Compare two directions and wait for my choice',
                        'No comparison. Wait for my choice',
                        'If the user is specific, use one direction without comparison.',
                        '비교 없이 계속해줘'):
            with self.subTest(request=request), tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
                manifest, _ = make_direct(f, request, anchors=[{'artifact': 'brief', 'excerpt': request}])
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': request}}) + '\n')
                with self.assertRaises(ValueError):
                    d.record_direct_admission(manifest, f.user_event, manifest.parent / 'selection.json')
                self.assertFalse((manifest.parent / 'selection.json').exists())

    def test_revocation_requires_a_fresh_actual_instruction(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            out = manifest.parent / 'selection.json'
            def append_request():
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': REQUEST}}) + '\n')
            append_request()
            d.record_direct_admission(manifest, f.user_event, out)
            d.reselect(out)
            with self.assertRaises(ValueError):
                d.record_direct_admission(manifest, f.user_event, out)
            append_request()
            self.assertEqual(d.record_direct_admission(manifest, f.user_event, out)['authority'], 'direct-user-instruction')

    def test_direct_admission_rejects_symlinked_revocation_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            out = manifest.parent / 'selection.json'
            def append_request():
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': REQUEST}}) + '\n')
            append_request()
            d.record_direct_admission(manifest, f.user_event, out)
            d.reselect(out)
            target = manifest.parent / 'outside.json'
            target.write_bytes(out.read_bytes())
            original_target = target.read_bytes()
            out.unlink()
            out.symlink_to(target)
            append_request()
            with self.assertRaisesRegex(ValueError, 'symlink'):
                d.record_direct_admission(manifest, f.user_event, out)
            self.assertEqual(target.read_bytes(), original_target)

    def test_revocation_changed_before_atomic_replacement_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            out = manifest.parent / 'selection.json'
            def append_request():
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': REQUEST}}) + '\n')
            append_request(); d.record_direct_admission(manifest, f.user_event, out); d.reselect(out)
            append_request()
            changed = out.read_bytes() + b' '
            persist = d._persist_admission
            def race(path, result, **kwargs):
                Path(path).write_bytes(changed)
                return persist(path, result, **kwargs)
            with patch.object(d, '_persist_admission', side_effect=race), self.assertRaisesRegex(ValueError, 'changed'):
                d.record_direct_admission(manifest, f.user_event, out)
            self.assertEqual(out.read_bytes(), changed)

    def test_revocation_swapped_to_symlink_before_atomic_replacement_does_not_touch_target(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            out = manifest.parent / 'selection.json'
            def append_request():
                with f.user_event.open('a') as stream:
                    stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': REQUEST}}) + '\n')
            append_request(); d.record_direct_admission(manifest, f.user_event, out); d.reselect(out)
            append_request()
            target = manifest.parent / 'external.json'
            target.write_text('keep me')
            original_target = target.read_bytes()
            persist = d._persist_admission
            def race(path, result, **kwargs):
                Path(path).unlink()
                Path(path).symlink_to(target)
                return persist(path, result, **kwargs)
            with patch.object(d, '_persist_admission', side_effect=race), self.assertRaisesRegex(ValueError, 'symlink'):
                d.record_direct_admission(manifest, f.user_event, out)
            self.assertEqual(target.read_bytes(), original_target)

    def test_generic_policy_fake_record_and_mode_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            data = json.loads(manifest.read_text())
            draft = d.validate_draft(manifest)
            for text in ('Continue with this work please.', 'If the user is specific, use one direction without comparison.'):
                draft['data']['direct_instruction']['request_text'] = text
                with self.assertRaises(ValueError):
                    d._direct_human(draft, f.user_event)
            with self.assertRaises(ValueError):
                d._direct_human(d.validate_draft(manifest), write(Path(tmp) / 'fake.json', {'approved': True}))
            data['mode'] = 'compare'; manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                d.validate_draft(manifest)

    def test_direct_cannot_bypass_native_review(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            native_request = REQUEST.replace('Local HTML only.', 'Figma native draft review.')
            manifest, _ = make_direct(f, native_request)
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': native_request}}) + '\n')
            # Trusted gate adapter is exercised and must block without current actual native evidence.
            with patch.object(d, '_native_review', side_effect=ValueError('No current native canvas')) as gate:
                with self.assertRaises(ValueError):
                    d.record_direct_admission(manifest, f.user_event, manifest.parent / 'selection.json')
                gate.assert_called()

    def test_current_critique_absent_stale_generic_and_warning_disposition(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            manifest, _ = make_direct(f)
            data = json.loads(manifest.read_text()); good = critique(data)
            for change in (lambda r: r.pop('schema'), lambda r: r.update(brief={'sha256': 'old'}),
                           lambda r: r['candidates'][0]['observations'][0].update(reason='looks good'),
                           lambda r: r['candidates'][0]['observations'][0].update(excerpt='unknown source excerpt'),
                           lambda r: r['candidates'][0]['artifacts']['previews'][0]['file'].update(sha256='old'),
                           lambda r: r.update(warning_dispositions=[{'warning_sha256': 'unknown', 'reason': 'ignore everything'}])):
                review = copy.deepcopy(good); change(review)
                with self.assertRaises(ValueError):
                    design_critique.validate(data, review, d.current, d.digest)
            visual = copy.deepcopy(good)
            observation = visual['candidates'][0]['observations'][0]
            observation.update(artifact='preview-mobile', locator={'region': [0, 0, 390, 100]})
            self.assertEqual(design_critique.validate(data, visual, d.current, d.digest)['visual_execution'], 'unverified')
            for invalid in (float('nan'), float('inf'), float('-inf')):
                observation['locator']['region'][0] = invalid
                with self.assertRaises(ValueError):
                    design_critique.validate(data, visual, d.current, d.digest)
            observation['locator']['region'][0] = 0
            observation['locator']['region'][2] = 400
            with self.assertRaises(ValueError):
                design_critique.validate(data, visual, d.current, d.digest)
            data['native_layout'] = d.pin(write(Path(tmp) / 'layout.json', {}))
            good['native_layout'] = data['native_layout']
            warning = {'candidate': 'A', 'code': 'no-visual-anchor', 'state': 'reader', 'viewport': 'mobile', 'layer': None}
            with patch('design_quality.run', return_value={'errors': [], 'warnings': [warning]}):
                with self.assertRaises(ValueError):
                    design_critique.validate(data, good, d.current, d.digest)
                good['warning_dispositions'] = [{'warning': warning, 'warning_sha256': d.digest(warning), 'disposition': 'accepted',
                    'reason': 'The reading utility prioritizes note text and requires no decorative hero image.'}]
                self.assertEqual(design_critique.validate(data, good, d.current, d.digest)['visual_quality'], 'unverified')


if __name__ == '__main__':
    unittest.main()
