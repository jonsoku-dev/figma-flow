import copy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / 'skills' / 'figma-flow' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import graph_diff
import ssot


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


class GraphDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous = Path(self.temp.name) / 'previous.json'
        self.current = Path(self.temp.name) / 'current.json'
        self.data = {'version': 1, 'nodes': [
            {'id': 'R', 'type': 'requirement', 'title': '요구사항', 'status': 'observed', 'source': 'brief.md'},
            {'id': 'S', 'type': 'screen', 'title': '화면', 'status': 'planned'}],
            'edges': [{'from': 'R', 'to': 'S', 'type': 'appears on'}]}

    def pin(self, before, after):
        for path, value in ((self.previous, before), (self.current, after)):
            path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        def ref(path):
            return {'availability': 'local-hashed', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest = {'version': 1, 'revision': 1, 'inputs': {'graph': ref(self.previous)}}
        manifest['manifest_sha256'] = ssot.digest(manifest)
        check = {'inputs': {'graph': ref(self.current)},
                 'change_explanation': {'baseline_manifest_sha256': manifest['manifest_sha256']}}
        return manifest, check

    def compare(self, before, after):
        manifest, check = self.pin(before, after)
        return graph_diff.compare_graphs(self.previous, self.current, manifest, check)

    def test_title_source_metadata_and_missing_null_are_exact_fields(self):
        before = copy.deepcopy(self.data)
        before['nodes'][0]['metadata'] = None
        after = copy.deepcopy(self.data)
        after['nodes'][0].update(title='수정 제목', source='new.md', extra=None)
        result = self.compare(before, after)
        fields = {item['field']: item for item in result['nodes']['modified'][0]['fields']}
        self.assertEqual(fields['title']['old']['value'], '요구사항')
        self.assertEqual(fields['title']['new']['value'], '수정 제목')
        self.assertEqual(fields['source']['new']['value'], 'new.md')
        self.assertEqual(fields['metadata']['old'], {'present': True, 'value': None})
        self.assertEqual(fields['metadata']['new'], {'present': False})
        self.assertEqual(fields['extra']['old'], {'present': False})
        self.assertEqual(fields['extra']['new'], {'present': True, 'value': None})

    def test_added_removed_nodes_and_labeled_edges_preserve_multiplicity(self):
        after = copy.deepcopy(self.data)
        after['nodes'][1]['id'] = 'NEW'
        after['edges'] = [{'from': 'R', 'to': 'NEW', 'type': '새 연결'}] * 2
        result = self.compare(self.data, after)
        self.assertEqual([node['id'] for node in result['nodes']['added']], ['NEW'])
        self.assertEqual([node['id'] for node in result['nodes']['removed']], ['S'])
        self.assertEqual(len(result['edges']['added']), 2)
        self.assertEqual(result['edges']['removed'], self.data['edges'])
        after = copy.deepcopy(self.data)
        after['edges'] *= 2
        self.assertEqual(self.compare(self.data, after)['edges']['added'], self.data['edges'])

    def test_reordering_nodes_edges_and_object_keys_is_unchanged(self):
        after = copy.deepcopy(self.data)
        after['nodes'].reverse()
        after['nodes'][0] = dict(reversed(list(after['nodes'][0].items())))
        result = self.compare(self.data, after)
        self.assertTrue(all(count == 0 for count in result['counts'].values()))
        self.assertNotEqual(result['previous']['sha256'], result['current']['sha256'])
        self.assertTrue(result['byte_changed'])
        self.assertFalse(result['structural_changed'])
        self.assertIn('구조 변경은 없습니다', graph_diff.render_diff(result))

    def test_graph_metadata_only_change_including_missing_null(self):
        after = copy.deepcopy(self.data)
        after['metadata'] = None
        result = self.compare(self.data, after)
        self.assertEqual(result['graph_fields'], [{'field': 'metadata', 'old': {'present': False},
                                                  'new': {'present': True, 'value': None}}])
        self.assertEqual(result['counts']['nodes_modified'], 0)
        self.assertEqual(result['counts']['graph_fields_modified'], 1)
        self.assertTrue(result['structural_changed'])
        self.assertIn('그래프 공통 필드 변경 · 1', graph_diff.render_diff(result))
        self.assertIn('metadata', graph_diff.render_diff(result))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires FIFO support')
    def test_fifo_is_rejected_without_opening_a_blocking_reader(self):
        manifest, check = self.pin(self.data, self.data)
        self.current.unlink()
        os.mkfifo(self.current)
        with self.assertRaisesRegex(ValueError, 'Only regular local files'):
            graph_diff.compare_graphs(self.previous, self.current, manifest, check)

    def test_renamed_node_keeps_unchanged_incident_edges_in_diagram(self):
        after = copy.deepcopy(self.data)
        after['nodes'][1]['title'] = '새 화면 이름'
        result = self.compare(self.data, after)
        self.assertEqual(result['edges'], {'added': [], 'removed': []})
        self.assertEqual(result['neighborhoods']['previous']['edges'], self.data['edges'])
        self.assertEqual(result['neighborhoods']['current']['edges'], self.data['edges'])
        html = graph_diff.render_diff(result)
        self.assertIn('화면', html)
        self.assertIn('새 화면 이름', html)
        self.assertIn('appears on', html)
        self.assertIn('[수정] S', html)

    def test_removal_and_edge_only_changes_have_neighborhoods(self):
        after = copy.deepcopy(self.data)
        after['nodes'].pop()
        after['edges'] = []
        result = self.compare(self.data, after)
        self.assertEqual(len(result['neighborhoods']['previous']['nodes']), 2)
        self.assertEqual(len(result['neighborhoods']['current']['nodes']), 1)
        self.assertIn('[삭제] S', graph_diff.render_diff(result))
        after = copy.deepcopy(self.data)
        after['edges'][0]['type'] = 'new label'
        result = self.compare(self.data, after)
        self.assertEqual(len(result['neighborhoods']['previous']['nodes']), 2)
        self.assertEqual(result['counts']['nodes_modified'], 0)
        self.assertIn('new label', graph_diff.render_diff(result))

    def test_relation_cards_label_added_and_removed_edges_without_svg_collisions(self):
        before = {'version': 1, 'nodes': [
            {'id': 'REQ-003', 'type': 'requirement', 'title': '요구사항', 'status': 'planned'},
            {'id': 'ACT-005', 'type': 'action', 'title': '새 동작', 'status': 'planned'},
            {'id': 'S', 'type': 'screen', 'title': '기존 화면', 'status': 'planned'}],
            'edges': [{'from': 'REQ-003', 'to': 'S', 'type': '이전 관계'}]}
        after = copy.deepcopy(before)
        after['edges'] = [{'from': 'REQ-003', 'to': 'ACT-005', 'type': '새 관계'},
                          {'from': 'REQ-003', 'to': 'S', 'type': '또 다른 관계'}]
        html = graph_diff.render_diff(self.compare(before, after))
        self.assertIn('[추가 연결] 새 관계', html)
        self.assertIn('[추가 연결] 또 다른 관계', html)
        self.assertIn('[삭제 연결] 이전 관계', html)
        self.assertIn('REQ-003 → ACT-005', html)
        self.assertIn('class="relation-card added"', html)
        self.assertIn('class="relation-card removed"', html)
        self.assertIn('class="endpoint-label">출발', html)
        self.assertIn('class="endpoint-label">도착', html)
        tags = Tags()
        tags.feed(html)
        self.assertEqual(tags.tags.count('ol'), 2)
        self.assertNotIn('svg', tags.tags)
        self.assertNotIn('position:absolute', html)

    def test_json_number_bool_distinction(self):
        before, after = copy.deepcopy(self.data), copy.deepcopy(self.data)
        before['nodes'][0]['metadata'] = {'enabled': 1}
        after['nodes'][0]['metadata'] = {'enabled': True}
        self.assertEqual(self.compare(before, after)['counts']['nodes_modified'], 1)

    def test_previous_current_and_baseline_hash_mismatches(self):
        for target in ('previous', 'current', 'baseline'):
            with self.subTest(target=target):
                manifest, check = self.pin(self.data, self.data)
                if target == 'previous':
                    self.previous.write_text(self.previous.read_text() + '\n')
                elif target == 'current':
                    self.current.write_text(self.current.read_text() + '\n')
                else:
                    check['change_explanation']['baseline_manifest_sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    graph_diff.compare_graphs(self.previous, self.current, manifest, check)

    def test_manifest_integrity_is_required_and_explanation_is_optional(self):
        manifest, check = self.pin(self.data, self.data)
        check.pop('change_explanation')
        self.assertEqual(graph_diff.compare_graphs(self.previous, self.current, manifest, check)['counts']['nodes_modified'], 0)
        manifest['revision'] = 2
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            graph_diff.compare_graphs(self.previous, self.current, manifest, check)

    def test_strict_json_and_graph_validation(self):
        invalid = [self.data | {'version': True}, self.data | {'nodes': self.data['nodes'] * 2},
                   self.data | {'edges': [{'from': 'UNKNOWN', 'to': 'S', 'type': 'x'}]}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.compare(self.data, data)
        for raw in ('{"version":1,"version":1,"nodes":[],"edges":[]}',
                    '{"version":1,"nodes":[],"edges":[],"extra":NaN}',
                    '{"version":1,"nodes":[],"edges":[],"extra":1e999}',
                    '{"version":1,"nodes":[],"edges":[],"extra":"\\ud800"}'):
            with self.subTest(raw=raw):
                manifest, check = self.pin(self.data, self.data)
                self.current.write_text(raw)
                with self.assertRaisesRegex(ValueError, 'Invalid graph'):
                    graph_diff.compare_graphs(self.previous, self.current, manifest, check)

    def test_korean_and_malicious_strings_remain_inert_text(self):
        after = copy.deepcopy(self.data)
        malicious = '</pre><script>alert("한글")</script><img src=x onerror=alert(1)>'
        after['nodes'][0]['title'] = malicious
        after['nodes'][0]['metadata'] = {'<svg/onload=alert(1)>': malicious}
        result = self.compare(self.data, after)
        html = graph_diff.render_diff(result)
        tags = Tags()
        tags.feed(html)
        self.assertNotIn('script', tags.tags)
        self.assertNotIn('img', tags.tags)
        self.assertNotIn('svg', tags.tags)
        self.assertNotIn('<svg/onload', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('한글', html)
        self.assertIn('lang="ko"', html)
        self.assertIn('scope="col">이전', html)
        self.assertIn('scope="col">현재', html)
        self.assertIn(result['previous']['sha256'], html)
        self.assertIn(result['current']['sha256'], html)
        self.assertIn("default-src 'none'", html)


if __name__ == '__main__':
    unittest.main()
