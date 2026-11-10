import base64
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / 'skills' / 'figma-flow' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('trace_report', SCRIPTS / 'trace_report.py')
trace_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace_report)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class TraceReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.graph = self.base / 'graph.json'
        self.check = self.base / 'check.json'
        self.out = self.base / 'report.html'
        self.data = {'version': 1, 'nodes': [
            {'id': 'R', 'type': 'requirement', 'title': '결제 요구사항', 'status': 'observed', 'source': 'brief.md'},
            {'id': 'S', 'type': 'screen', 'title': '결제 화면', 'status': 'planned'},
            {'id': 'C', 'type': 'code', 'title': '결제 코드', 'status': 'observed', 'source': 'code.py'},
            {'id': 'T', 'type': 'test', 'title': '결제 테스트', 'status': 'verified', 'source': 'test.txt'},
            {'id': 'U', 'type': 'screen', 'title': '연결되지 않은 화면', 'status': 'blocked'},
        ], 'edges': [
            {'from': 'R', 'to': 'S', 'type': 'covers'},
            {'from': 'S', 'to': 'C', 'type': 'implemented-by'},
            {'from': 'C', 'to': 'T', 'type': 'checked-by'},
            {'from': 'T', 'to': 'S', 'type': 'cycle'},
        ]}
        for name in ('brief.md', 'code.py', 'test.txt'):
            (self.base / name).write_text(name, encoding='utf-8')
        bindings = {'version': 1, 'authorities': {'intent': 'brief.md', 'implementation': 'code.py'},
                    'dependency_edge_types': ['covers', 'implemented-by', 'checked-by'], 'evidence': {'S': ['brief.md']}}
        (self.base / 'bindings.json').write_text(json.dumps(bindings), encoding='utf-8')
        self.pin()

    def pin(self):
        self.graph.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        current = trace_report.ssot.build(self.base / 'brief.md', self.graph,
                                         self.base / 'bindings.json', self.base, 'local-only')
        self.check_data = trace_report.ssot.compare(current, None)
        self.check.write_text(json.dumps(self.check_data), encoding='utf-8')

    def run_cli(self):
        return subprocess.run([sys.executable, str(SCRIPTS / 'trace_report.py'), str(self.graph),
                               '--check', str(self.check), '--out', str(self.out)], text=True, capture_output=True)

    def test_cli_creates_offline_report_without_changing_inputs(self):
        before = {p: p.read_bytes() for p in self.base.iterdir()}
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['nodes'], 5)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        page = self.out.read_text()
        tags = Tags()
        tags.feed(page)
        self.assertEqual(next(attrs['lang'] for tag, attrs in tags.tags if tag == 'html'), 'ko')
        self.assertFalse(any('src' in attrs or 'href' in attrs for _, attrs in tags.tags))
        self.assertIn("default-src 'none'", page)
        digest = base64.b64encode(hashlib.sha256(trace_report.SCRIPT.encode()).digest()).decode()
        self.assertIn("script-src 'sha256-" + digest + "'", page)

    def test_existing_output_and_symlink_are_never_replaced(self):
        self.out.write_text('user content')
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(self.out.read_text(), 'user content')
        self.out.unlink()
        target = self.base / 'target.html'
        target.write_text('target')
        self.out.symlink_to(target)
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(target.read_text(), 'target')

    def test_wrong_graph_bytes_rejected_even_with_same_node_ids(self):
        self.graph.write_text(json.dumps(self.data, indent=2))
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA-256 mismatch', result.stderr)
        self.assertFalse(self.out.exists())

    def test_node_fingerprint_mismatch_rejected(self):
        self.check_data['nodes']['S']['content_sha256'] = 'wrong'
        self.check.write_text(json.dumps(self.check_data))
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fingerprint mismatch', result.stderr)
        self.assertFalse(self.out.exists())

    def test_node_set_and_malformed_freshness_rejected(self):
        for mutation, message in ((lambda check: check['nodes'].pop('S'), 'node IDs mismatch'),
                                  (lambda check: check['nodes']['S'].pop('freshness'), 'Invalid SSOT freshness'),
                                  (lambda check: check['nodes']['S'].update(reasons='oops'), 'Invalid SSOT reasons'),
                                  (lambda check: check['nodes']['S'].update(evidence=[{}]), 'Invalid SSOT evidence')):
            with self.subTest(message=message):
                self.pin()
                mutation(self.check_data)
                self.check.write_text(json.dumps(self.check_data))
                result = self.run_cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(self.out.exists())

    def test_invalid_graph_is_rejected_before_rendering(self):
        self.data['edges'][0]['to'] = 'missing'
        self.graph.write_text(json.dumps(self.data))
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid graph', result.stderr)
        self.assertFalse(self.out.exists())

    def test_hostile_strings_are_only_json_data_and_text(self):
        hostile = '</script><img src="https://example.invalid/a" onerror="alert(1)">&\u2028'
        self.data['nodes'][0]['title'] = hostile
        self.data['nodes'][0]['source'] = 'javascript:alert(1)'
        self.pin()
        self.check_data['change_explanation'] = self.explanation_fixture()
        self.check_data['change_explanation']['direct_nodes']['R']['evidence_changes'][0]['path'] = hostile
        self.check.write_text(json.dumps(self.check_data))
        payload = trace_report.prepare(self.graph, self.check)
        page = trace_report.render(payload)
        tags = Tags()
        tags.feed(page)
        self.assertEqual(sum(tag == 'script' for tag, _ in tags.tags), 2)
        self.assertFalse(any(tag == 'img' for tag, _ in tags.tags))
        encoded = page.split('<script id="trace-data" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertNotIn('<', encoded)
        self.assertEqual(json.loads(encoded)['graph']['nodes'][0]['title'], hostile)
        self.assertEqual(json.loads(encoded)['change_explanation']['direct_nodes']['R']['evidence_changes'][0]['path'], hostile)
        self.assertNotIn('innerHTML', trace_report.SCRIPT)
        self.assertNotIn('fetch(', trace_report.SCRIPT)
        self.assertNotIn('eval(', trace_report.SCRIPT)

    def run_dom(self, payload, assertions, fragment=''):
        harness = r"""
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.attrs = {}; this.value = ''; this.textContent = ''; }
  append(...items) { this.children.push(...items); if (this.tag === 'select' && !this.value && items.length) this.value = items[0].value; }
  replaceChildren(...items) { this.children = items; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(key, value) { this.attrs[key] = value; }
  get options() { return this.children; }
  focus() { this.focused = true; }
}
const elements = new Map();
for (const id of ['trace-data', 'node-list', 'search', 'list-count', 'node-detail', 'paths', 'requirement', 'summary', 'hash', 'check-summary', 'warnings', 'change-summary']) elements.set(id, new Element(id === 'requirement' ? 'select' : 'div'));
elements.get('trace-data').textContent = JSON.stringify(PAYLOAD);
const document = {getElementById: id => elements.get(id), createElement: tag => new Element(tag)};
function all(element) { return [element, ...element.children.flatMap(all)]; }
function texts(element) { return all(element).map(item => item.textContent).join(' '); }
const location = {hash: FRAGMENT};
require('node:vm').runInNewContext(SCRIPT, {document, location});
""" + assertions
        program = harness.replace('JSON.stringify(PAYLOAD)', 'JSON.stringify(' + json.dumps(payload) + ')')
        program = program.replace('FRAGMENT', json.dumps(fragment))
        program = program.replace('runInNewContext(SCRIPT,', 'runInNewContext(' + json.dumps(trace_report.SCRIPT) + ',')
        result = subprocess.run(['node', '-e', program], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the isolated DOM self-check')
    def test_renderer_navigates_cycles_and_search_without_inventing_paths(self):
        payload = trace_report.prepare(self.graph, self.check)
        self.run_dom(payload, r"""
const paths = elements.get('paths');
assert.equal(paths.children.filter(item => item.className === 'path').length, 3);
assert.ok(texts(paths).includes('implemented-by'));
assert.ok(texts(paths).includes('checked-by'));
assert.ok(!texts(paths).includes('연결되지 않은 화면'));
const target = all(paths).find(item => item.tag === 'button' && item.textContent.startsWith('T ·'));
target.listeners.click();
assert.ok(texts(elements.get('node-detail')).includes('T · 결제 테스트'));
assert.ok(texts(elements.get('node-detail')).includes('cycle'));
assert.ok(elements.get('node-detail').children[0].focused);
elements.get('search').value = '연결되지';
elements.get('search').listeners.input();
assert.equal(elements.get('node-list').children.length, 1);
assert.ok(texts(elements.get('node-list')).includes('U ·'));
"""
        )

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the isolated DOM self-check')
    def test_fragment_selects_encoded_node_without_stealing_focus(self):
        payload = trace_report.prepare(self.graph, self.check)
        self.run_dom(payload, r"""
assert.ok(texts(elements.get('node-detail')).includes('T · 결제 테스트'));
assert.equal(elements.get('node-detail').children[0].focused, undefined);
assert.equal(elements.get('requirement').value, 'R');
assert.equal(location.hash, '#node=%54');
assert.ok(all(elements.get('node-list')).find(item => item.attrs['aria-current'] === 'true').textContent.startsWith('T ·'));
""", fragment='#node=%54')

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the isolated DOM self-check')
    def test_fragment_requirement_also_selects_its_paths(self):
        self.data['nodes'].append({'id': 'R2', 'type': 'requirement', 'title': '다른 요구사항', 'status': 'planned'})
        self.data['edges'].append({'from': 'R2', 'to': 'U', 'type': 'covers'})
        self.pin()
        payload = trace_report.prepare(self.graph, self.check)
        self.run_dom(payload, r"""
assert.equal(elements.get('requirement').value, 'R2');
assert.ok(texts(elements.get('node-detail')).includes('R2 · 다른 요구사항'));
assert.ok(texts(elements.get('paths')).includes('U · 연결되지 않은 화면'));
assert.ok(!texts(elements.get('paths')).includes('S · 결제 화면'));
""", fragment='#node=R2')

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the isolated DOM self-check')
    def test_unsupported_or_malformed_fragment_falls_back(self):
        payload = trace_report.prepare(self.graph, self.check)
        for fragment in ('#other=T', '#node=unknown', '#node=%E0%A4%A', '#node=', '#node=T&extra=R'):
            with self.subTest(fragment=fragment):
                self.run_dom(payload, r"""
assert.ok(texts(elements.get('node-detail')).includes('R · 결제 요구사항'));
assert.equal(elements.get('requirement').value, 'R');
assert.equal(elements.get('node-detail').children[0].focused, undefined);
""", fragment=fragment)

    def explanation_fixture(self):
        previous = {'path': 'before.txt', 'availability': 'local-hashed', 'sha256': 'old'}
        current = {'path': 'before.txt', 'availability': 'missing', 'sha256': None}
        return {'version': 1, 'baseline_manifest_sha256': 'baseline', 'limitation': '검사 시점의 증거',
                'direct_nodes': {'R': {'categories': ['evidence-changed'], 'historic_only': False,
                    'previous_content_sha256': 'same', 'current_content_sha256': 'same',
                    'evidence_changes': [{'path': 'before.txt', 'previous': previous, 'current': current}]}},
                'changed_inputs': [{'key': 'brief', 'previous': previous, 'current': current}],
                'changed_authorities': [], 'dependency_edges': [],
                'propagation': {
                    'R': {'root_id': 'R', 'root_kind': 'direct-change', 'predecessor_id': None, 'edge': None},
                    'T': {'root_id': 'R', 'root_kind': 'direct-change', 'predecessor_id': 'R',
                          'edge': {'from': 'R', 'to': 'T', 'type': 'old-dependency', 'presence': 'previous-only'}},
                    'U': {'root_id': 'REMOVED', 'root_kind': 'historic-only-unknown', 'predecessor_id': 'REMOVED',
                          'edge': {'from': 'REMOVED', 'to': 'U', 'type': 'former-dependency', 'presence': 'previous-only'}},
                    'REMOVED': {'root_id': 'REMOVED', 'root_kind': 'historic-only-unknown', 'predecessor_id': None, 'edge': None}}}

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the isolated DOM self-check')
    def test_change_explanation_uses_recorded_dependency_forest_and_evidence(self):
        self.check_data['change_explanation'] = self.explanation_fixture()
        for node_id in ('R', 'T', 'U'):
            self.check_data['nodes'][node_id].update(freshness='stale', reasons=['upstream-stale'])
        self.check.write_text(json.dumps(self.check_data))
        payload = trace_report.prepare(self.graph, self.check)
        self.run_dom(payload, r"""
const summary = texts(elements.get('change-summary'));
assert.ok(summary.includes('증거 경로: before.txt'));
assert.ok(summary.includes('이전: before.txt · local-hashed · SHA-256: old'));
assert.ok(summary.includes('현재: before.txt · missing · SHA-256: 없음'));
assert.ok(summary.includes('변경 입력: brief'));
const nodeList = elements.get('node-list');
all(nodeList).find(item => item.tag === 'button' && item.textContent.startsWith('T ·')).listeners.click();
let detail = elements.get('node-detail');
const explanation = detail.children.slice(detail.children.findIndex(item => item.textContent === '이 노드가 오래된 이유'), detail.children.findIndex(item => item.textContent === '직접 연결 · 방향과 관계명'));
assert.ok(explanation.map(texts).join(' ').includes('old-dependency [이전에만 있던 연결 · 현재 삭제됨]'));
assert.ok(!explanation.map(texts).join(' ').includes('implemented-by'));
assert.ok(detail.children[0].focused);
all(elements.get('node-list')).find(item => item.tag === 'button' && item.textContent.startsWith('U ·')).listeners.click();
assert.ok(texts(elements.get('node-detail')).includes('REMOVED · 현재 그래프에 없음'));
assert.ok(texts(elements.get('node-detail')).includes('원래 변경 원인은 알 수 없습니다'));
""")

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the isolated DOM self-check')
    def test_old_check_has_explicit_unknown_explanation(self):
        self.check_data.pop('change_explanation', None)
        self.check_data['nodes']['R'].update(freshness='stale', reasons=['previously-stale'])
        self.check.write_text(json.dumps(self.check_data))
        payload = trace_report.prepare(self.graph, self.check)
        self.run_dom(payload, r"""
assert.ok(texts(elements.get('change-summary')).includes('이 검사에는 변경 설명이 없습니다'));
assert.ok(texts(elements.get('node-detail')).includes('이유를 추정하지 않습니다'));
""")

    def test_accepts_real_ssot_evidence_change_explanation(self):
        manifest = self.base / 'manifest.json'
        result = subprocess.run([sys.executable, str(SCRIPTS / 'ssot.py'), 'snapshot',
                                 '--brief', str(self.base / 'brief.md'), '--graph', str(self.graph),
                                 '--bindings', str(self.base / 'bindings.json'), '--scope', 'local-only',
                                 '--out', str(manifest)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.base / 'test.txt').write_text('changed test evidence')
        result = subprocess.run([sys.executable, str(SCRIPTS / 'ssot.py'), 'check', str(manifest)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.check.write_text(result.stdout)
        payload = trace_report.prepare(self.graph, self.check)
        change = payload['change_explanation']['direct_nodes']['T']['evidence_changes'][0]
        self.assertEqual(change['path'], 'test.txt')
        self.assertNotEqual(change['previous']['sha256'], change['current']['sha256'])
        self.assertEqual(self.run_cli().returncode, 0)

    def test_malformed_change_explanation_is_rejected(self):
        self.check_data['change_explanation'] = self.explanation_fixture()
        self.check_data['change_explanation']['direct_nodes']['R']['evidence_changes'] = 'invalid'
        self.check.write_text(json.dumps(self.check_data))
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertFalse(self.out.exists())

    def test_empty_graph_is_browsable_without_a_requirement(self):
        self.data = {'version': 1, 'nodes': [], 'edges': []}
        bindings_path = self.base / 'bindings.json'
        bindings = json.loads(bindings_path.read_text())
        bindings['evidence'] = {}
        bindings_path.write_text(json.dumps(bindings))
        self.pin()
        self.assertEqual(self.run_cli().returncode, 0)
        payload = trace_report.prepare(self.graph, self.check)
        self.assertTrue(payload['warnings'])
        self.assertEqual(payload['check']['nodes'], {})


if __name__ == '__main__':
    unittest.main()
