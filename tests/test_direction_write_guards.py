import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))
import asset_batch
import design_bundle
from workflow import Event, State
from direction_fixture import selected_direction
from design_directions import guard_production


class WriteGuardTests(unittest.TestCase):
    def test_asset_entry_rejects_missing_choice_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            concept = base / 'project.md'
            concept.write_text('A game campaign with a shared art context.')
            target = base / 'nested' / 'production'
            parents_before = set(base.iterdir())
            with self.assertRaisesRegex(ValueError, State.WAIT_SELECTION.name):
                asset_batch.freeze(concept, [], ['mark:logo'], target, batch_id='batch', game_id='game',
                                  concept_id='concept', version='1')
            self.assertEqual(set(base.iterdir()), parents_before)

    def test_a_written_approval_claim_does_not_unlock_either_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            selection = base / 'unverified.json'
            selection.write_text(json.dumps({'approved': True, 'candidate_id': 'A', 'workflow_state': State.SELECTED.value}))
            output = base / 'output'
            with self.assertRaisesRegex(ValueError, State.WAIT_SELECTION.name):
                design_bundle.build(base/'design.json', base/'graph.json', output, selection_path=selection)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, State.WAIT_SELECTION.name):
                asset_batch.freeze(base/'concept.md', [], [], output, batch_id='batch', game_id='game',
                                  concept_id='concept', version='1', selection_path=selection)
            self.assertFalse(output.exists())

    def test_batch_carries_the_actual_candidate_and_rechecks_inputs_for_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            concept = base/'concept.md'
            concept.write_text('Use a shared game world and the exact chosen printable composition.')
            with selected_direction(base) as selected:
                out = base/'pack'
                roles = ['label:logo','key:key_art','icon:icon','cast:character','plate:section_title','frame:button_frame']
                result = asset_batch.freeze(concept, [], roles, out, selection_path=selected.selection_path,
                                            batch_id='batch-id',game_id='example',concept_id='game',version='1')
                batch = json.loads((out/'batch.json').read_text())
                self.assertEqual(result['workflow_state'], State.BATCH_FROZEN.value)
                evidence = json.loads((out/'generation-requests.json').read_text())['requests']
                self.assertEqual({r['evidence_input']['candidate_id'] for r in evidence},{'A'})
                self.assertEqual(len(batch['references']), 2)
                for ref in batch['references']:
                    self.assertTrue((out/ref['path']).is_file())
                admission = asset_batch.release_requests(selected.selection_path,out/'batch.json',out/'generation-requests.json')
                self.assertEqual(admission['state'],State.GENERATION.value)
                packet = json.loads((out/'generation-requests.json').read_text())
                packet['requests'][0]['args']['prompt'] = 'Unreviewed replacement.'
                (out/'generation-requests.json').write_text(json.dumps(packet))
                with self.assertRaisesRegex(ValueError, 'Cached host requests differ'):
                    asset_batch.release_requests(selected.selection_path,out/'batch.json',out/'generation-requests.json')
                (out/batch['references'][0]['path']).write_bytes(b'changed while waiting')
                with self.assertRaises(ValueError):
                    guard_production(selected.selection_path,event=Event.GENERATE,batch_path=out/'batch.json')

    def test_selected_game_does_not_compile_before_asset_results_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = {'version':1,'game_id':'test-game','nodes':[{'id':'example','type':'screen',
                     'title':'Show the game','status':'planned'}],'edges':[]}
            with selected_direction(root,graph,native_review=True) as selected:
                with self.assertRaisesRegex(ValueError,'asset production'):
                    design_bundle.build(root/'unused.json',selected.product_graph,root/'native-import',
                                        selection_path=selected.selection_path)
                self.assertFalse((root/'native-import').exists())

    def test_production_bundle_cli_blocks_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / 'bundle'
            result = subprocess.run([sys.executable, '-B', str(TOOLS/'design_bundle.py'), '--design',
                                     str(root/'design.json'), '--graph', str(root/'graph.json'), '--out', str(out)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(State.WAIT_SELECTION.name, result.stderr)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
