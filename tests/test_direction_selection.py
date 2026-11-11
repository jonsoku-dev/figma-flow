"""Modeled transcript/validator fixtures only; no real user consent or native execution."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import design_directions as directions

CHOICE = '현장 브리핑으로 본제작까지 진행해줘. Computer Use 없이 Figma·웹 양방향 동기화까지 테스트하고, 남은 대비 경고도 해결해줘.'


class DirectionSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'modeled-session.jsonl'
        self.draft = {'draft': {'path': str(self.root / 'directions.json'), 'sha256': 'd' * 64}, 'data': {
            'review_id': 'modeled-current-review', 'review_destination': 'figma',
            'native_review': {'readback': {'path': 'modeled-readback.json', 'sha256': 'e' * 64}},
            'candidates': [{'id': 'briefing', 'title': '현장 브리핑', 'sha256': 'a' * 64},
                           {'id': 'notebook', 'title': '등반 수첩', 'sha256': 'b' * 64}]}}
        self.report = {'passed': True, 'file_key': 'modeled-file', 'page_id': '12:1', 'screens': [
            {'id': '12:2', 'key': 'briefing.desktop.state-overview'},
            {'id': '12:3', 'key': 'notebook.desktop.state-overview'}]}
        self.readback = self.root / 'modeled-readback.json'
        self.readback.write_text(json.dumps({'observed_at': '2026-11-10T10:00:00Z'}))
        self.draft['data']['native_review']['readback'] = directions.pin(self.readback)
        self.links = ('[현장 브리핑 Figma](https://www.figma.com/design/modeled-file?node-id=12-2)\n'
                      '[등반 수첩 Figma](https://www.figma.com/design/modeled-file?node-id=12-3)')
        self.root_patch = patch.object(directions, 'user_record_root', return_value=self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        native_patch = patch.object(directions, '_native_review', return_value=self.report)
        self.native = native_patch.start()
        self.addCleanup(native_patch.stop)

    def record(self, role, text, *, phase=None):
        payload = {'type': 'message', 'role': role, 'content': [{'type': 'output_text' if role == 'assistant' else 'input_text', 'text': text}]}
        if phase:
            payload['phase'] = phase
        return {'type': 'response_item', 'timestamp': '2026-11-10T10:01:00Z' if role == 'assistant' else '2026-11-10T10:02:00Z', 'payload': payload}

    def write(self, answer=CHOICE, *, presentation=None, phase='final_answer'):
        self.source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in [
            self.record('assistant', self.links if presentation is None else presentation, phase=phase), self.record('user', answer)]))

    def recognize(self, expected=None):
        return directions._human(self.draft, self.source, expected=expected)

    def append(self, role, text):
        with self.source.open('a') as stream:
            stream.write(json.dumps(self.record(role, text), ensure_ascii=False) + '\n')

    def test_exact_title_affirmative_after_current_native_links_accepts_independent_work(self):
        self.write()
        human, candidate = self.recognize()
        self.assertEqual(candidate['id'], 'briefing')
        self.assertEqual(human['candidate_id'], 'briefing')
        self.native.assert_called_once_with(self.draft['draft']['path'], self.draft['data'])
        self.append('assistant', 'Read-only continuation')
        self.assertEqual(self.recognize(expected=human)[0], human)

    def test_legacy_id_hash_presentation_and_title_forms_remain_pinned(self):
        presentation = self.draft['data']['review_id'] + ' ' + self.draft['draft']['sha256']
        for answer, identity in [('briefing', 'briefing'), ('notebook ' + 'b' * 64, 'notebook'),
                                 ('현장 브리핑을 선택할게요.', 'briefing'), ('“등반 수첩”으로 진행해줘.', 'notebook')]:
            with self.subTest(answer=answer):
                self.write(answer, presentation=presentation, phase=None)
                human, candidate = self.recognize()
                self.assertEqual(candidate['id'], identity)
                self.assertEqual(self.recognize(expected=human)[0], human)
        self.native.assert_not_called()

    def test_later_hold_reversal_and_aggregate_request_reject_selection(self):
        for suffix in ['잠깐, 아직 시작하지 마.', '아니, 방금 요청은 취소할게.', '둘 다 같이 제작해줘.']:
            self.write('현장 브리핑으로 본제작까지 진행해줘. ' + suffix)
            with self.assertRaises(ValueError):
                self.recognize()

    def test_negative_ambiguous_multi_candidate_and_delegation_are_not_choices(self):
        for answer in ['현장 브리핑', '현장 브리핑으로', '현장브리핑으로 진행해줘.',
                       '현장 브리핑으로 진행하지 마.', '현장 브리핑으로 진행할까?',
                       '현장 브리핑으로 진행해줘도 될까?', '현장 브리핑이 좋을 것 같아.',
                       '현장 브리핑 말고 선택해줘.', '둘 중 알아서 선택해서 진행해줘.',
                       '현장 브리핑과 등반 수첩을 모두 선택해줘.',
                       '현장 브리핑으로 진행해줘. 등반 수첩도 같이 만들어줘.',
                       '현장 브리핑으로 진행해줘. notebook도 포함해.',
                       '현장 브리핑으로 진행해줘. 선택은 아직 하지 마.',
                       '사용자가 현장 브리핑으로 진행해줘 라고 말했다.']:
            with self.subTest(answer=answer):
                self.write(answer)
                with self.assertRaises(ValueError):
                    self.recognize()

    def test_native_anchor_requires_each_correct_labeled_current_candidate_node(self):
        for presentation in [self.links.splitlines()[0], self.links.replace('modeled-file', 'another-file'),
                             self.links.replace('12-2', '12-999'), self.links.replace('12-2', '12-1'),
                             self.links.replace('현장 브리핑 Figma', '등반 수첩 Figma'),
                             self.links.replace('www.figma.com', 'www.figma.com.evil.invalid'),
                             '```markdown\n' + self.links + '\n```', '`' + self.links.splitlines()[0] + '`',
                             'https://www.figma.com/design/modeled-file?node-id=12-2']:
            with self.subTest(presentation=presentation):
                self.write(presentation=presentation)
                with self.assertRaises(ValueError):
                    self.recognize()
        self.write(presentation=self.links.replace('12-2', '12%3A2').replace('12-3', '12%3A3'))
        self.assertEqual(self.recognize()[1]['id'], 'briefing')

    def test_nonvisible_tool_arguments_agent_events_and_late_presentation_do_not_admit(self):
        for record in [self.record('assistant', self.links, phase='commentary'),
                       {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': self.links}},
                       {'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'request_user_input', 'arguments': self.links}}]:
            self.source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in [record, self.record('user', CHOICE)]))
            with self.assertRaises(ValueError):
                self.recognize()
        self.source.write_text(json.dumps(self.record('user', CHOICE), ensure_ascii=False) + '\n')
        self.append('assistant', self.links)
        with self.assertRaises(ValueError):
            self.recognize()

    def test_native_validation_failure_and_new_foreign_presentation_fail_closed(self):
        self.write()
        self.native.side_effect = ValueError('stale native readback')
        with self.assertRaisesRegex(ValueError, 'stale native'):
            self.recognize()
        self.native.side_effect = None
        records = [self.record('assistant', self.links, phase='final_answer'),
                   self.record('assistant', self.links.replace('modeled-file', 'foreign-file'), phase='final_answer'),
                   self.record('user', CHOICE)]
        self.source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records))
        with self.assertRaises(ValueError):
            self.recognize()

    def test_native_anchor_rejects_missing_malformed_or_future_getter_time(self):
        self.write()
        for observed_at in (None, 'invalid', '2026-11-10T10:00:00', '2026-11-10T10:03:00Z'):
            with self.subTest(observed_at=observed_at):
                self.readback.write_text(json.dumps({'observed_at': observed_at}))
                self.draft['data']['native_review']['readback'] = directions.pin(self.readback)
                with self.assertRaises(ValueError):
                    self.recognize()
        self.readback.write_text(json.dumps({'observed_at': '2026-11-10T10:00:00Z'}))
        self.draft['data']['native_review']['readback'] = directions.pin(self.readback)
        records = [json.loads(line) for line in self.source.read_text().splitlines()]
        for timestamp in (None, 'invalid', '2026-11-10T10:01:00'):
            with self.subTest(presentation_timestamp=timestamp):
                records[0]['timestamp'] = timestamp
                self.source.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records))
                with self.assertRaises(ValueError):
                    self.recognize()

    def test_revocation_supersession_and_prefix_mutation_keep_old_guards(self):
        self.write()
        human = self.recognize()[0]
        self.append('user', '선택 취소')
        with self.assertRaises(ValueError):
            self.recognize(expected=human)
        self.write()
        human = self.recognize()[0]
        self.append('user', '등반 수첩으로 선택해줘.')
        with self.assertRaisesRegex(ValueError, 'superseded'):
            self.recognize(expected=human)
        self.write()
        human = self.recognize()[0]
        self.source.write_text(self.source.read_text().replace('Computer Use', 'Computer use'))
        with self.assertRaisesRegex(ValueError, 'prefix changed'):
            self.recognize(expected=human)

    def test_duplicate_titles_and_self_written_external_records_are_not_admitted(self):
        self.write()
        self.draft['data']['candidates'][1]['title'] = '현장 브리핑'
        with self.assertRaises(ValueError):
            self.recognize()
        with tempfile.TemporaryDirectory() as foreign:
            external = Path(foreign) / 'approval.jsonl'
            external.write_text(self.source.read_text())
            with self.assertRaisesRegex(ValueError, 'managed user-turn'):
                directions._human(self.draft, external)
