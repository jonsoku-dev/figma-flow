"""Replay tests use private temporary workspaces and synthetic generator metadata."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        assigned = self.root / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        self.path = self.root / 'workspace'
        workspace.init(self.path, assigned)

    def prepare(self):
        return workspace.prepare(self.path, 'read', 'Read', 'discover', ['--file-key', 'fixturefile', '--page-id', '12:1'])

    def row(self):
        return workspace.current(self.path)['tasks'][0]

    def test_replay_preserves_args_scope_identity_and_private_keys(self):
        result = self.prepare()
        keys = {name: (self.path / name).read_bytes() for name in ('identity.json', 'compiler.key')}
        row = self.row()
        with patch.object(workspace, 'trusted_sources', return_value='a' * 64), patch.dict(os.environ,
                {'CODEX_THREAD_ID':'12345678-abcd-4abc-9abc-123456789abc'}):
            refreshed = workspace.replay(self.path, 'read', result['revision'])
        self.assertNotEqual(refreshed['revision'], result['revision'])
        self.assertEqual(self.row()['generator_args'], row['generator_args'])
        self.assertEqual(self.row()['threadId'], row['threadId'])
        self.assertEqual(keys, {name: (self.path / name).read_bytes() for name in keys})
        with self.assertRaisesRegex(ValueError, 'Stale'):
            workspace.replay(self.path, 'read', result['revision'])

    def test_legacy_requires_original_admission(self):
        result = self.prepare()
        catalogue = workspace.current(self.path)
        del catalogue['tasks'][0]['generator_args']
        workspace.publish(self.path, catalogue)
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            workspace.replay(self.path, 'read', result['revision'])

    def test_plan_is_path_pinned_and_drift_blocks_dispatch_and_replay(self):
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'schema':'figma-flow-native-edit-plan-v1','file_key':'FILE123','page_id':'1:2',
                                   'edits':[{'node_id':'3:4','field':'paddingLeft','before':12,'after':20}]}))
        result = workspace.prepare(self.path, 'edit', 'Edit', 'native-edit', ['--plan', str(plan)])
        row = self.row()
        self.assertEqual(row['input_pins']['--plan'], workspace.digest(plan.read_bytes()))
        plan.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            workspace.task_artifacts(self.path, row)
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            workspace.replay(self.path, 'edit', result['revision'])

    def test_nested_source_sidecar_pins_are_checked_on_replay_and_dispatch(self):
        graph = self.root / 'graph.json'
        graph.write_text('{}')
        original = workspace.generate
        def generate(*args):
            value = original(*args)
            workspace.atomic(args[3] / 'source-inputs.json', workspace.encode({'schema':'figma-flow-source-pins-v1',
                'pins':[{'path':str(graph), 'sha256':workspace.digest(graph.read_bytes())}]}))
            return value
        with patch.object(workspace, 'generate', side_effect=generate):
            result = self.prepare()
        self.assertEqual(self.row()['source_input_pins'][0]['path'], str(graph))
        graph.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'Source inputs changed'):
            workspace.task_artifacts(self.path, self.row())
        with self.assertRaisesRegex(ValueError, 'Source inputs changed'):
            workspace.replay(self.path, 'read', result['revision'])

    def test_source_sidecar_rejects_escaping_or_unbounded_shapes(self):
        for pin in ({'path':'relative', 'sha256':'0'*64}, {'path':str(self.root), 'sha256':'not-sha'},
                    {'path':str(self.root), 'sha256':'0'*64, 'other':True}):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                workspace.check_source_pins([pin])
