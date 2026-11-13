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


if __name__ == '__main__':
    unittest.main()
