"""No-Figma integration tests for the live-follow read receipt and graph projection path."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

import figma_follow
import graph_sync
from graph_design_system import emit_web_module, load_graph
from test_graph_sync import fixture as graph_sync_fixture


class FigmaLiveProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        graph, native = graph_sync_fixture()
        self.graph_path = self.directory / 'graph.json'
        self.graph_path.write_text(json.dumps(graph), encoding='utf-8')
        loaded = load_graph(self.graph_path)
        self.plan = graph_sync.build_plan(loaded, native)
        self.focused = graph_sync.normalize(native, self.plan)
        self.focused['schema'] = 'figma-flow-graph-token-readback-v1'
        self.focused['baseline'] = {'page_id': 'page', 'collection_id': 'collection',
                                    'graph_sha256': self.plan['graph_sha256']}
        pairing = graph_sync.receipt(loaded, self.plan, self.focused)
        self.web_path = self.directory / 'tokens.mjs'
        emit_web_module(self.graph_path, self.web_path)
        pairing['web_module_sha256'] = hashlib.sha256(self.web_path.read_bytes()).hexdigest()
        self.pairing_path = self.directory / 'pairing.json'
        self.pairing_path.write_text(json.dumps(pairing), encoding='utf-8')
        self.pairing_bytes = self.pairing_path.read_bytes()
        self.readback_path = self.directory / 'native-readback.json'
        self.readback_path.write_text(json.dumps(self.changed_size_readback()), encoding='utf-8')
        self.args = SimpleNamespace(
            read_task='pinned-sync-read', revision='revision-1', read_timeout=30,
            pairing=self.pairing_path, graph=self.graph_path, web_module=self.web_path,
            component_edits=False, apply_clean=True,
        )

    def changed_size_readback(self):
        data = copy.deepcopy(self.focused)
        for token in data['tokens']:
            if token['key'] in {'b/size/button', 'b/type/button'}:
                token['resolved'] = 24
        for component in data['components']:
            for consumer in component['consumers']:
                if consumer['field'] == 'fontSize':
                    consumer['value'] = 24
        return data

    def transport(self, *args, **kwargs):
        self.assertEqual(args[1:4], ('pinned-sync-read', 'revision-1', 'read'))
        return {'state': 'read', 'operation_id': 'receipt-1', 'readback': str(self.readback_path)}

    def run_fresh_read(self, allow_publish=True, events=()):
        with patch.object(figma_follow, 'read_operation', side_effect=self.transport):
            return figma_follow.fresh_read(self.args, self.directory / 'fresh-read', allow_publish, events=events)

    @staticmethod
    def mapped_font_size_event(node_id='main.text'):
        return {'node_id': node_id, 'type': 'PROPERTY_CHANGE', 'properties': ['fontSize'], 'origin': 'unknown'}

    def test_fresh_read_preview_uses_native_receipt_without_changing_canonical_files(self):
        graph_before, web_before, pairing_before = (p.read_bytes() for p in
            (self.graph_path, self.web_path, self.pairing_path))
        self.args.apply_clean = False
        result = self.run_fresh_read(allow_publish=False)
        self.assertEqual(result['state'], 'preview')
        self.assertEqual(result['operation_id'], 'receipt-1')
        self.assertFalse(result['applied'])
        self.assertGreater(result['proposed_updates'], 0)
        self.assertEqual(self.graph_path.read_bytes(), graph_before)
        self.assertEqual(self.web_path.read_bytes(), web_before)
        self.assertEqual(self.pairing_path.read_bytes(), pairing_before)

    def test_apply_clean_updates_mapped_graph_and_web_but_keeps_pairing_as_original_baseline(self):
        pairing = json.loads(self.pairing_path.read_text(encoding='utf-8'))
        scoped_consumers = {node_id for identity, ids in pairing['consumer_ids'].items()
                            if identity.endswith(':fontSize') for node_id in ids}
        self.assertEqual(scoped_consumers, {'main.text', 'instance.text'})
        result = self.run_fresh_read(allow_publish=True, events=[self.mapped_font_size_event()])
        graph = load_graph(self.graph_path)
        tokens = graph['design_system']['tokens']
        self.assertEqual(result['state'], 'applied')
        self.assertTrue(result['applied'])
        self.assertFalse(result['pairing_advanced'])
        self.assertEqual(tokens['b/size/button']['value'], 24)
        self.assertEqual(tokens['b/type/button'], {'type': 'FLOAT', 'alias': 'b/size/button'})
        self.assertEqual(tokens['b/space/padding-16']['value'], 18)
        self.assertIn('24px', self.web_path.read_text(encoding='utf-8'))
        self.assertEqual(self.pairing_path.read_bytes(), self.pairing_bytes)

    def test_unrelated_change_witness_cannot_publish_a_paired_token_root(self):
        graph_before, web_before, pairing_before = (path.read_bytes() for path in
            (self.graph_path, self.web_path, self.pairing_path))
        result = self.run_fresh_read(allow_publish=True, events=[self.mapped_font_size_event('unpaired-node')])
        self.assertEqual(result['state'], 'review-required')
        self.assertIn('change witness', result['reason'])
        self.assertFalse(result.get('applied', False))
        self.assertEqual(self.graph_path.read_bytes(), graph_before)
        self.assertEqual(self.web_path.read_bytes(), web_before)
        self.assertEqual(self.pairing_path.read_bytes(), pairing_before)

    def test_gap_and_unsupported_native_changes_preserve_all_paired_files(self):
        baseline = {path: path.read_bytes() for path in (self.graph_path, self.web_path, self.pairing_path)}
        receipt = self.directory / 'receipt-with-gap'
        args = SimpleNamespace(inspect_task=None, read_task='pinned-sync-read', revision='revision-1',
                               resume_chat=False, pairing=self.pairing_path, graph=self.graph_path,
                               web_module=self.web_path, component_edits=False, apply_clean=True, read_timeout=30)
        batch = {'scope': {'file_key': 'file', 'page_id': 'page'}, 'cursor': {'epoch': 'e', 'seq': 3},
                 'events': [{'node_id': 'main', 'type': 'PROPERTY_CHANGE', 'properties': ['fontSize']}],
                 'gap': {'from': 2, 'to': 2}}
        with patch.object(figma_follow, 'read_operation', side_effect=self.transport), redirect_stdout(io.StringIO()):
            path = figma_follow.handle_batch(args, receipt, None, batch)
        record = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(record['read']['state'], 'review-required')
        self.assertIn('gap', record['read']['reason'])
        self.assertFalse(record['read'].get('applied', False))
        self.assertEqual({path: path.read_bytes() for path in baseline}, baseline)

        unsupported = self.changed_size_readback()
        unsupported['unsupported_changes'] = [{'field': 'opacity', 'reason': 'unmapped'}]
        self.readback_path.write_text(json.dumps(unsupported), encoding='utf-8')
        before = {path: path.read_bytes() for path in (self.graph_path, self.web_path, self.pairing_path)}
        result = self.run_fresh_read(allow_publish=True, events=[self.mapped_font_size_event()])
        self.assertEqual(result['state'], 'review-required')
        self.assertEqual(result['unsupported_changes'], 1)
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_local_graph_drift_blocks_apply_and_preserves_the_drift(self):
        self.graph_path.write_bytes(self.graph_path.read_bytes() + b'\n')
        graph_drift = self.graph_path.read_bytes()
        web_before = self.web_path.read_bytes()
        result = self.run_fresh_read(allow_publish=True, events=[self.mapped_font_size_event()])
        self.assertEqual(result['state'], 'review-required')
        self.assertEqual(self.graph_path.read_bytes(), graph_drift)
        self.assertEqual(self.web_path.read_bytes(), web_before)

    def test_unsupported_unpaired_web_file_is_preserved(self):
        self.web_path.write_bytes(b'unsupported local web module\x00')
        drifted_web = self.web_path.read_bytes()
        graph_before = self.graph_path.read_bytes()
        result = self.run_fresh_read(allow_publish=True, events=[self.mapped_font_size_event()])
        self.assertEqual(result['state'], 'review-required')
        self.assertEqual(self.graph_path.read_bytes(), graph_before)
        self.assertEqual(self.web_path.read_bytes(), drifted_web)

    def test_web_edit_racing_after_preflight_is_rejected_before_graph_write(self):
        graph_before, web_before = self.graph_path.read_bytes(), self.web_path.read_bytes()
        original = graph_sync.import_values

        def edit_web_before_apply(*args, **kwargs):
            if kwargs.get('apply'):
                self.web_path.write_text('// concurrent local edit\n', encoding='utf-8')
            return original(*args, **kwargs)

        with patch.object(figma_follow, 'read_operation', side_effect=self.transport), \
             patch.object(graph_sync, 'import_values', side_effect=edit_web_before_apply):
            result = figma_follow.fresh_read(self.args, self.directory / 'race', True,
                                             events=[self.mapped_font_size_event()])
        self.assertEqual(result['state'], 'review-required')
        self.assertEqual(self.graph_path.read_bytes(), graph_before)
        self.assertNotEqual(self.web_path.read_bytes(), web_before)
        self.assertEqual(self.web_path.read_text(encoding='utf-8'), '// concurrent local edit\n')

    def test_notification_targets_only_the_current_codex_thread(self):
        current_thread = '2d8d8f2e-4978-4f34-a1bb-d681f3242a93'
        with patch.dict(os.environ, {'CODEX_THREAD_ID': current_thread}), \
             patch.object(figma_follow.shutil, 'which', return_value='/usr/local/bin/codex'):
            thread = figma_follow.thread_destination(True)
        self.assertEqual(thread, current_thread)
        calls = []
        with patch.object(figma_follow.subprocess, 'run', side_effect=lambda command, **kwargs: calls.append(command) or
                          SimpleNamespace(returncode=0, stderr='')):
            result = figma_follow.notify(thread, self.directory / 'event.json', 1, False, False)
        self.assertEqual(result['state'], 'queued')
        self.assertIn('--thread', calls[0])
        self.assertEqual(calls[0][calls[0].index('--thread') + 1], current_thread)
        self.assertFalse(any('all' in value or value == '--broadcast' for value in calls[0]))

    def test_duplicate_and_crash_replay_never_resend_uncertain_notification(self):
        args = SimpleNamespace(inspect_task=None, read_task=None, resume_chat=False)
        batch = {'scope': {'file_key': 'file', 'page_id': 'page'}, 'cursor': {'epoch': 'e', 'seq': 8},
                 'events': [{'node_id': '0:1', 'type': 'PROPERTY_CHANGE', 'properties': ['width'], 'origin': 'unknown'}],
                 'gap': None}
        out = io.StringIO()
        with patch.object(figma_follow, 'notify', return_value={'state': 'queued', 'consumed': False}) as send, \
             redirect_stdout(out):
            first = figma_follow.handle_batch(args, self.directory / 'duplicates', '2d8d8f2e-4978-4f34-a1bb-d681f3242a93', batch)
            second = figma_follow.handle_batch(args, self.directory / 'duplicates', '2d8d8f2e-4978-4f34-a1bb-d681f3242a93', batch)
        self.assertEqual(first, second)
        send.assert_called_once()

        identifier = figma_follow.digest((batch['scope'], batch['cursor']))
        event_path = self.directory / 'crash' / identifier / 'event.json'
        event_path.parent.mkdir(mode=0o700, parents=True)
        figma_follow.save(event_path, {'schema': figma_follow.SCHEMA, 'scope': batch['scope'], 'cursor': batch['cursor'],
            'events': batch['events'], 'gap': None, 'received_at': 0,
            'notification': {'state': 'uncertain', 'consumed': False}})
        with patch.object(figma_follow, 'notify') as never_resend, redirect_stdout(io.StringIO()):
            figma_follow.handle_batch(args, self.directory / 'crash', '2d8d8f2e-4978-4f34-a1bb-d681f3242a93', batch)
        never_resend.assert_not_called()


if __name__ == '__main__':
    unittest.main()
