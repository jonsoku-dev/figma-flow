"""Exercise the real capture generator without modifying the checked-in graph."""
import hashlib
import json
import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


spec = importlib.util.spec_from_file_location('source', HERE / 'source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class RegenerationTest(unittest.TestCase):
    def test_source_change_conflict_and_retired_record(self):
        base = {'nodes': [{'id': 'REQ-006', 'title': 'original', 'type': 'requirement'}], 'edges': []}
        current, candidate = copy.deepcopy(base), copy.deepcopy(base)
        candidate['nodes'][0]['title'] = 'new policy'
        merged, _ = source.reconcile(current, candidate, base)
        self.assertEqual(merged, candidate)
        current['nodes'][0]['title'] = 'approved policy'
        with self.assertRaisesRegex(ValueError, 'REQ-006.*title'):
            source.reconcile(current, candidate, base)
        candidate['nodes'].clear()
        merged, review = source.reconcile(current, candidate, base)
        self.assertEqual(merged, current)
        self.assertTrue(any('REQ-006' in item for item in review['retained_without_source']))


    def test_canonical_edits_survive_repeated_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            design = root / 'apps/little-hands/design'
            shutil.copytree(HERE, design, ignore=shutil.ignore_patterns('reviews', '.figma-flow', '__pycache__'))
            app = design.parent
            for name in ('templates', 'static', 'booking', 'ARCHITECTURE.md'):
                (app / name).symlink_to(HERE.parent / name)
            for name in ('tools', 'skills'):
                (root / name).symlink_to(HERE.parents[2] / name)
            path = design / 'graph.json'
            graph = json.loads(path.read_bytes())
            req = next(row for row in graph['nodes'] if row['id'] == 'REQ-006')
            req.update(title='검토한 취소 정책', review_note='정책 근거 보존')
            graph['edges'].append({'from': 'REQ-006', 'type': 'depends-on', 'to': 'TEST-006'})
            graph['design_system'] = {'version': 1, 'tokens': {'cta': {'type': 'FLOAT', 'value': 22}}, 'components': {}}
            path.write_text(json.dumps(graph, ensure_ascii=False))
            command = [sys.executable, str(design / 'source.py'), '--static-root', str(HERE / 'source_assets')]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(json.loads(path.read_bytes()), graph, 'regeneration lost canonical edits')
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                spec = json.loads((design / 'specifications.json').read_bytes())
                self.assertEqual(spec['source_graph']['sha256'], digest)

            # Insert a new requirement ahead of all ten existing entries and reverse their order.
            drive = (
                "import source; "
                "source.REQS = [('REQ-011','추가 정책',None), *reversed(source.REQS)]; "
                "source.STATIC_ROOT = source.ROOT/'source_assets'; source.build()"
            )
            subprocess.run([sys.executable, '-c', drive], cwd=design, check=True, capture_output=True)
            result = json.loads(path.read_bytes())
            old_ids = {node['id'] for node in graph['nodes']}
            self.assertEqual([node for node in result['nodes'] if node['id'] in old_ids], graph['nodes'])
            self.assertEqual({node['id'] for node in result['nodes']} - old_ids,
                             {'REQ-011', 'AC-011', 'TEST-011'})
            self.assertEqual([edge for edge in result['edges'] if edge['from'] in old_ids], graph['edges'])
            previous = {name: (design / name).read_bytes()
                        for name in ('graph.json', 'native-layout.json', 'specifications.json')}
            stale = subprocess.run([*command, '--expected-sha256', digest], capture_output=True)
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn(b'Stale graph SHA256', stale.stderr)
            drive = drive.replace("source.build()", "source.REQS = [(r, 'source changed' if r == 'REQ-006' else t, v) for r,t,v in source.REQS]; source.build()")
            conflict = subprocess.run([sys.executable, '-c', drive], cwd=design, capture_output=True)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn(b'Graph edit conflicts', conflict.stderr)
            for name, raw in previous.items():
                self.assertEqual((design / name).read_bytes(), raw)

    def _copy_design_workspace(self, temporary):
        root = Path(temporary)
        design = root / 'apps/little-hands/design'
        shutil.copytree(HERE, design, ignore=shutil.ignore_patterns('reviews', '.figma-flow', '__pycache__'))
        app = design.parent
        for name in ('templates', 'static', 'booking', 'ARCHITECTURE.md'):
            (app / name).symlink_to(HERE.parent / name)
        for name in ('tools', 'skills'):
            (root / name).symlink_to(HERE.parents[2] / name)
        return root, design

    def test_adopted_token_edit_and_unrelated_source_foundation_update_do_not_conflict(self):
        tools_dir = str(HERE.parents[2] / 'tools')
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from graph_design_system import load_graph, update_graph_values

        with tempfile.TemporaryDirectory() as temporary:
            _, design = self._copy_design_workspace(temporary)
            cmd = [sys.executable, str(design / 'source.py'), '--static-root', str(HERE / 'source_assets')]
            subprocess.run(cmd, check=True, capture_output=True)

            graph_path = design / 'graph.json'
            loaded = load_graph(graph_path)
            updated_color = {'r': 0.5, 'g': 0.2, 'b': 0.1, 'a': 1}
            update_graph_values(graph_path, {'color.bookingCta': updated_color}, loaded.source_sha256)

            tokens_path = design / 'tokens.json'
            tokens = json.loads(tokens_path.read_text(encoding='utf-8'))
            tokens['colors']['paper'] = '#f7f3ea'
            tokens_path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

            subprocess.run(cmd, check=True, capture_output=True)
            result = json.loads(graph_path.read_bytes())
            self.assertEqual(result['design_system']['tokens']['color.bookingCta']['value'], updated_color)
            roles = {row['token']: row for row in result['design_foundations']['roles']}
            self.assertEqual(roles['color.action.primary']['native']['value'], updated_color)
            self.assertIn('color/css-f6f2e9', roles)

            # Adopted foundation tokens remain owned by design_system even if tokens.json drifts.
            loaded = load_graph(graph_path)
            result['design_system']['tokens']['color/rust'] = {
                'type': 'COLOR',
                'value': {'r': 0.2, 'g': 0.3, 'b': 0.4, 'a': 1},
            }
            graph_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            loaded = load_graph(graph_path)
            adopted_rust = {'r': 0.1, 'g': 0.2, 'b': 0.3, 'a': 1}
            update_graph_values(graph_path, {'color/rust': adopted_rust}, loaded.source_sha256)
            tokens['colors']['rust'] = '#aa1111'
            tokens_path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            subprocess.run(cmd, check=True, capture_output=True)
            after_rust = json.loads(graph_path.read_bytes())
            after_roles = {row['token']: row for row in after_rust['design_foundations']['roles']}
            self.assertEqual(after_rust['design_system']['tokens']['color/rust']['value'], adopted_rust)
            self.assertEqual(after_roles['color/rust']['native']['value'], adopted_rust)

    def test_legacy_graph_without_baseline_preserves_edits_across_reorder_and_insertion(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, design = self._copy_design_workspace(temporary)
            graph_path = design / 'graph.json'
            legacy = json.loads(graph_path.read_bytes())
            legacy.pop('design_system', None)
            legacy['design_foundations']['roles'] = [
                row for row in legacy['design_foundations']['roles']
                if row.get('token') != 'color.action.primary'
            ]
            req = next(row for row in legacy['nodes'] if row['id'] == 'REQ-006')
            req['status'] = 'verified'
            req['review_note'] = 'Legacy approved policy'
            legacy['edges'].append({'from': 'REQ-006', 'type': 'depends-on', 'to': 'TEST-006'})
            graph_path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

            drive = (
                "import source; "
                "reqs = list(source.REQS); "
                "reqs.insert(2, ('REQ-011', '구버전 이관 정책', None)); "
                "source.REQS = list(reversed(reqs)); "
                "source.STATIC_ROOT = source.ROOT/'source_assets'; "
                "source.build()"
            )
            run = subprocess.run([sys.executable, '-c', drive], cwd=design, check=True, capture_output=True, text=True)
            summary = json.loads(run.stdout)
            self.assertIn("graph/nodes/('REQ-006',)/status", summary['retained_legacy_edits'])
            self.assertIn("graph/nodes/('REQ-006',)/detail", summary['retained_legacy_edits'])
            migrated = json.loads(graph_path.read_bytes())
            nodes = {node['id']: node for node in migrated['nodes']}
            self.assertEqual(nodes['REQ-006']['status'], 'verified')
            self.assertEqual(nodes['REQ-006']['review_note'], 'Legacy approved policy')
            self.assertIn('REQ-011', nodes)
            self.assertIn({'from': 'REQ-006', 'type': 'depends-on', 'to': 'TEST-006'}, migrated['edges'])

    def test_states_and_reqs_mid_insertion_and_reorder_preserve_ids_and_prototype_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, design = self._copy_design_workspace(temporary)
            cmd = [sys.executable, str(design / 'source.py'), '--static-root', str(HERE / 'source_assets')]
            subprocess.run(cmd, check=True, capture_output=True)

            graph_path = design / 'graph.json'
            graph = json.loads(graph_path.read_bytes())
            graph['draft_prototype']['entry_states'].append('state-review')
            graph['draft_prototype']['states'][0]['custom_note'] = 'preserve designer prototype note'
            graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

            drive = (
                "import source; "
                "reqs = list(source.REQS); "
                "reqs.insert(3, ('REQ-011', '중간 삽입 정책', None)); "
                "source.REQS = list(reversed(reqs)); "
                "states = list(source.STATES); "
                "states.insert(6, ('waitlisthelp', '대기 안내', 'booking/waitlist_help.html', ['REQ-004'], None)); "
                "states[0], states[1] = states[1], states[0]; "
                "source.STATES = states; "
                "source.STATIC_ROOT = source.ROOT/'source_assets'; "
                "source.build()"
            )
            subprocess.run([sys.executable, '-c', drive], cwd=design, check=True, capture_output=True)

            result = json.loads(graph_path.read_bytes())
            nodes = {node['id']: node for node in result['nodes']}
            self.assertIn('REQ-011', nodes)
            self.assertIn('screen-waitlisthelp', nodes)
            self.assertEqual(nodes['REQ-006']['detail'], graph['nodes'][next(i for i, n in enumerate(graph['nodes']) if n['id'] == 'REQ-006')]['detail'])
            edges = {(e['from'], e['to'], e['type']) for e in result['edges']}
            self.assertIn(('REQ-006', 'screen-confirmed', 'appears on'), edges)
            self.assertIn(('AC-006', 'TEST-006-cutoff', 'checked by'), edges)
            self.assertIn(('REQ-006', 'code-cancellation-policy', 'implemented by'), edges)
            self.assertIn('state-review', result['draft_prototype']['entry_states'])
            publichome = next(row for row in result['draft_prototype']['states'] if row['id'] == 'state-publichome')
            self.assertEqual(publichome['custom_note'], 'preserve designer prototype note')

    def test_deleted_source_reports_orphan_candidates_with_traceable_evidence_across_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, design = self._copy_design_workspace(temporary)
            cmd = [sys.executable, str(design / 'source.py'), '--static-root', str(HERE / 'source_assets')]
            run1 = subprocess.run(cmd, check=True, capture_output=True, text=True)
            status1 = json.loads((design / 'source-status.json').read_bytes())
            self.assertEqual(status1['orphan_candidates'], [])

            graph_path = design / 'graph.json'
            graph = json.loads(graph_path.read_bytes())
            for nid in ('REQ-006', 'AC-006', 'TEST-006'):
                node = next(row for row in graph['nodes'] if row['id'] == nid)
                node['status'] = 'verified'
                node['review_note'] = f'Approved prior evidence for {nid}'
            graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

            drive = (
                "import source; "
                "source.REQS = [row for row in source.REQS if row[0] != 'REQ-006']; "
                "source.STATES = [(n, t, tpl, [r for r in reqs if r != 'REQ-006'], rt) for n, t, tpl, reqs, rt in source.STATES]; "
                "source.STATIC_ROOT = source.ROOT/'source_assets'; "
                "source.build()"
            )
            run2 = subprocess.run([sys.executable, '-c', drive], cwd=design, check=True, capture_output=True, text=True)
            out2 = json.loads(run2.stdout)
            status2 = json.loads((design / 'source-status.json').read_bytes())
            self.assertEqual(out2['orphan_candidates'], status2['orphan_candidates'])

            orphan_nodes = {item['id']: item for item in status2['orphan_candidates'] if item['kind'] == 'node'}
            self.assertEqual(set(orphan_nodes), {'REQ-006', 'AC-006', 'TEST-006'})
            self.assertNotIn('TEST-006-cutoff', orphan_nodes)
            self.assertNotIn('TOKEN-color-bookingCta', orphan_nodes)
            self.assertEqual(orphan_nodes['REQ-006']['status'], 'verified')
            self.assertEqual(orphan_nodes['REQ-006']['review_note'], 'Approved prior evidence for REQ-006')
            self.assertTrue(any(
                e['from'] == 'AC-006' and e['to'] == 'TEST-006-cutoff' and e['type'] == 'checked by'
                for e in orphan_nodes['AC-006']['related_edges']
            ))

            # Prior evidence remains in graph.json and is traceable via graph.py impact.
            merged = json.loads(graph_path.read_bytes())
            merged_nodes = {n['id']: n for n in merged['nodes']}
            self.assertEqual(merged_nodes['REQ-006']['status'], 'verified')
            self.assertEqual(merged_nodes['REQ-006']['review_note'], 'Approved prior evidence for REQ-006')
            impact = subprocess.run(
                [sys.executable, str(root / 'skills/figma-flow/scripts/graph.py'), 'impact', str(graph_path), '--from', 'REQ-006'],
                check=True, capture_output=True, text=True,
            )
            self.assertIn('TEST-006-cutoff', impact.stdout)

            # Subsequent regeneration continues reporting the unreviewed orphan candidates.
            subprocess.run([sys.executable, '-c', drive], cwd=design, check=True, capture_output=True, text=True)
            status3 = json.loads((design / 'source-status.json').read_bytes())
            orphan_nodes3 = {item['id'] for item in status3['orphan_candidates'] if item['kind'] == 'node'}
            self.assertEqual(orphan_nodes3, {'REQ-006', 'AC-006', 'TEST-006'})

    def test_cross_clone_proposal_out_and_base_graph_preserve_edits_and_detect_deletions(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, design = self._copy_design_workspace(temporary)
            proposal_file = Path(temporary) / 'outside-proposal.json'
            cmd = [sys.executable, str(design / 'source.py'), '--static-root', str(HERE / 'source_assets')]
            subprocess.run([*cmd, '--proposal-out', str(proposal_file)], check=True, capture_output=True)
            shutil.rmtree(design / '.figma-flow')

            drive = (
                "from pathlib import Path; import source; "
                "source.REQS = [row for row in source.REQS if row[0] != 'REQ-009']; "
                "source.STATES = [(n, t, tpl, [r for r in reqs if r != 'REQ-009'], rt) for n, t, tpl, reqs, rt in source.STATES]; "
                "source.STATIC_ROOT = source.ROOT/'source_assets'; "
                f"source.build(base_graph=Path({str(proposal_file)!r}))"
            )
            subprocess.run([sys.executable, '-c', drive], cwd=design, check=True, capture_output=True, text=True)
            status = json.loads((design / 'source-status.json').read_bytes())
            orphan_ids = {item['id'] for item in status['orphan_candidates'] if item['kind'] == 'node'}
            self.assertEqual(orphan_ids, {'REQ-009', 'AC-009', 'TEST-009'})


if __name__ == '__main__':
    unittest.main()
