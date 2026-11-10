"""Isolated controller fixtures; no real user approval, GUI, hooks or production generation."""
import copy
import io
import json
from contextlib import redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import app_states
import design_actions
import design_directions as directions
import sync_workflow
from workflow import State
from direction_fixture import selected_direction


class DirectionAdmissionTests(unittest.TestCase):
    def test_selected_fixture_is_exact_idempotent_and_append_only(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            before = f.selection_path.read_bytes()
            admitted = directions.record_selection(f.manifest, f.user_event, f.selection_path)
            self.assertEqual(admitted['state'], State.SELECTED.value)
            self.assertEqual(f.selection_path.read_bytes(), before)
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'Read-only audit.'}}) + '\n')
            self.assertEqual(directions.require_selected(f.selection_path)['selection_sha256'], directions.pin(f.selection_path)['sha256'])

    def test_no_choice_auto_delegation_and_all_form_choice_do_not_authorize(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            original = f.selection_path.read_bytes()
            records = [json.loads(line) for line in f.user_event.read_text().splitlines()]
            for role, text in [('assistant', 'A'), ('user', '1,2,3 모두'), ('user', '알아서 선택해줘')]:
                changed = copy.deepcopy(records)
                changed[-1]['payload'].update(role=role, content=[{'type': 'input_text', 'text': text}])
                f.user_event.write_text(''.join(json.dumps(item) + '\n' for item in changed))
                with self.assertRaises(ValueError):
                    directions.record_selection(f.manifest, f.user_event, f.selection_path)
                self.assertEqual(f.selection_path.read_bytes(), original)

    def test_structured_real_user_reply_and_explicit_revocation(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            data = json.loads(f.manifest.read_text())
            reply = '<send_user_message_question_reply>' + json.dumps([{'questionItemId': 'direction',
                'question': data['review_id'] + ' ' + directions.pin(f.manifest)['sha256'], 'answer': 'B'}]) + '</send_user_message_question_reply>'
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': reply}}) + '\n')
            self.assertEqual(directions.record_selection(f.manifest, f.user_event, f.selection_path)['candidate_id'], 'B')
            with f.user_event.open('a') as stream:
                stream.write(json.dumps({'type': 'event_msg', 'payload': {'type': 'user_message', 'message': '선택 취소'}}) + '\n')
            with self.assertRaises(directions.SelectionRequired):
                directions.require_selected(f.selection_path)

    def test_stale_candidate_and_duplicate_or_cosmetic_candidates_fail(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            data = json.loads(f.manifest.read_text())
            broken = copy.deepcopy(data)
            second = broken['candidates'][1]
            second['previews'] = copy.deepcopy(broken['candidates'][0]['previews'])
            second['sha256'] = directions.digest({key: value for key, value in second.items() if key != 'sha256'})
            with self.assertRaisesRegex(ValueError, 'Same-byte|cosmetic'):
                directions.validate_draft(f.manifest, require_agent_review=False, _data=broken)
            source = Path(data['candidates'][0]['source']['path'])
            source.write_text(source.read_text() + '<p>Changed scope</p>')
            with self.assertRaises(directions.SelectionRequired):
                directions.require_selected(f.selection_path)

    def test_reselect_invalidates_active_eligibility_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            old = f.selection_path.read_bytes()
            result = directions.reselect(f.selection_path)
            self.assertEqual(result['workflow_state'], State.WAIT_SELECTION.value)
            self.assertTrue(result['invalidated_active_records'])
            self.assertEqual(Path(result['archived_selection']['path']).read_bytes(), old)
            with self.assertRaises(directions.SelectionRequired):
                directions.require_selected(f.selection_path)
            with self.assertRaises(ValueError):
                directions.record_selection(f.manifest, f.user_event, f.selection_path)

    def test_candidate_scope_escape_and_early_error_do_not_invent_current_state(self):
        with tempfile.TemporaryDirectory() as tmp, selected_direction(Path(tmp)) as f:
            data = json.loads(f.manifest.read_text())
            data['candidates'][0]['source']['path'] = str(Path(tmp).parent / 'outside.html')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                directions.validate_draft(f.manifest, require_agent_review=False, _data=data)
            error = io.StringIO()
            with redirect_stderr(error):
                code = design_actions.main(['draft', '--project', tmp, '--brief', 'missing.md', '--research', 'missing.md', '--from-existing', 'missing.json', '--out', str(Path(tmp) / 'no-output')])
            self.assertEqual(code, 1)
            self.assertIsNone(json.loads(error.getvalue())['workflow_state'])
            self.assertFalse((Path(tmp) / 'no-output').exists())

    def test_graph_exports_are_synchronized_and_product_state_drift_is_rejected(self):
        self.assertEqual(sync_workflow.check(), [])
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state_id = 'STATE-READ'
            graph = base / 'graph.json'
            graph.write_text(json.dumps({'nodes': [{'id': state_id, 'type': 'state', 'title': 'Read'}]}))
            export = base / 'states.js'
            export.write_text(app_states.render(graph))
            consumer = base / 'app.js'
            consumer.write_text("import {AppState} from './states.js';const current=AppState.STATE_READ;")
            declaration = {'exports': [{'path': 'states.js'}], 'consumers': [{'path': 'app.js', 'export': 'states.js'}]}
            self.assertTrue(app_states.validate(graph, declaration, base)['passed'])
            consumer.write_text(consumer.read_text() + 'const duplicate=' + json.dumps(state_id) + ';')
            self.assertFalse(app_states.validate(graph, declaration, base)['passed'])
            consumer.write_text("import {AppState} from './states.js';const current=AppState.UNDECLARED;")
            self.assertFalse(app_states.validate(graph, declaration, base)['passed'])
            export.write_text(export.read_text() + '// drift')
            self.assertFalse(app_states.validate(graph, declaration, base)['passed'])


if __name__ == '__main__':
    unittest.main()
