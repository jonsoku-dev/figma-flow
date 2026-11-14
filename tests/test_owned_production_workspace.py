"""Verify the owned production workspace fixture, its digest allowlist, and its serve boundary."""
from collections import deque
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples' / 'owned-production-workspace'
sys.path.insert(0, str(ROOT / 'skills' / 'figma-flow' / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools'))

import graph as graph_tool  # noqa: E402
import owned_production_workspace as workspace  # noqa: E402
import review_graph  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


class FixtureCopy:
    """A temporary copy of the fixture whose manifest can be re-pinned after an edit."""

    def __init__(self, test):
        self._tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / 'examples' / 'owned-production-workspace'
        shutil.copytree(FIXTURE, self.root, ignore=shutil.ignore_patterns('.DS_Store', '__pycache__'))

    def manifest(self):
        return load(self.root / 'manifest.json')

    def write_manifest(self, manifest):
        (self.root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    def repin(self, rel):
        manifest = self.manifest()
        entry = next(item for item in manifest['files'] if item['path'] == rel)
        entry['sha256'] = hashlib.sha256((self.root / rel).read_bytes()).hexdigest()
        self.write_manifest(manifest)

    def edit_graph(self, change):
        graph = load(self.root / 'graph.json')
        change(graph)
        (self.root / 'graph.json').write_text(json.dumps(graph, indent=2) + '\n', encoding='utf-8')
        self.repin('graph.json')

    def outside_copy(self, rel):
        target = self.base / ('outside-' + Path(rel).name)
        shutil.copyfile(self.root / rel, target)
        return target


class VerifyTest(unittest.TestCase):
    def assertRejected(self, root, expected):
        with self.assertRaises(workspace.WorkspaceError) as caught:
            workspace.verify(root)
        self.assertTrue(any(expected in problem for problem in caught.exception.problems),
                        f'{expected!r} not in {caught.exception.problems}')

    def test_receipt_records_input_and_output_digests(self):
        receipt = workspace.verify(FIXTURE)
        self.assertEqual(receipt, workspace.verify(FIXTURE))
        manifest = load(FIXTURE / 'manifest.json')
        graph = load(FIXTURE / 'graph.json')

        self.assertEqual(receipt['inputs']['manifest_sha256'],
                         hashlib.sha256((FIXTURE / 'manifest.json').read_bytes()).hexdigest())
        declared = {entry['path'] for entry in manifest['files']}
        self.assertEqual({item['path'] for item in receipt['inputs']['files']}, declared)
        for item in receipt['inputs']['files']:
            data = (FIXTURE / item['path']).read_bytes()
            self.assertEqual(item['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(item['bytes'], len(data))

        self.assertEqual([screen['id'] for screen in receipt['screens']], ['SCR-OPS-QUEUE', 'SCR-OPS-REVIEW'])
        self.assertEqual({(v['key'], v['width'], v['height']) for v in receipt['viewports']},
                         {('desktop', 1440, 900), ('mobile', 390, 844)})

        projection = receipt['outputs']['review_projection']
        selection = workspace.review_selection(graph)
        projected, source_sha = review_graph.project_graph(FIXTURE / 'graph.json', selection)
        self.assertEqual(projection['source_graph_sha256'], source_sha)
        self.assertEqual(projection['node_ids'], [node['id'] for node in projected['nodes']])
        self.assertEqual(projection['selection_sha256'], review_graph.selection_sha256(projected))
        self.assertEqual(projected['id'], 'owned-production-workspace')

    def test_cli_receipt_is_private_and_new(self):
        fixture = FixtureCopy(self)
        receipt = fixture.base / 'receipt.json'
        self.assertEqual(workspace.main(['verify', '--root', str(fixture.root), '--receipt', str(receipt)]), 0)
        self.assertEqual(load(receipt)['schema'], workspace.RECEIPT_SCHEMA)
        self.assertEqual(workspace.main(['verify', '--root', str(fixture.root), '--receipt', str(receipt)]), 1)
        inside = fixture.root / 'receipt.json'
        self.assertEqual(workspace.main(['verify', '--root', str(fixture.root), '--receipt', str(inside)]), 1)
        self.assertFalse(inside.exists())

    def test_rejects_changed_bytes(self):
        fixture = FixtureCopy(self)
        with (fixture.root / 'styles.css').open('a', encoding='utf-8') as handle:
            handle.write('\n')
        self.assertRejected(fixture.root, 'digest drift for styles.css')

    def test_rejects_undeclared_file(self):
        fixture = FixtureCopy(self)
        (fixture.root / 'media' / 'extra.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding='utf-8')
        self.assertRejected(fixture.root, 'undeclared file: media/extra.svg')

    def test_rejects_symlink_with_matching_bytes(self):
        for target in ('outside', 'inside'):
            with self.subTest(target=target):
                fixture = FixtureCopy(self)
                rel = 'media/queue-empty.svg'
                source = fixture.outside_copy(rel) if target == 'outside' else fixture.root / 'media' / 'queue-empty-copy.svg'
                if target == 'inside':
                    shutil.copyfile(fixture.root / rel, source)
                (fixture.root / rel).unlink()
                os.symlink(source, fixture.root / rel)
                self.assertEqual(hashlib.sha256((fixture.root / rel).read_bytes()).hexdigest(),
                                 next(e['sha256'] for e in fixture.manifest()['files'] if e['path'] == rel))
                self.assertRejected(fixture.root, 'symlink rejected: media/queue-empty.svg')

    def test_rejects_escaping_manifest_paths(self):
        for path, expected in (('../graph.json', 'path escapes'), ('/etc/hosts', 'absolute path'),
                               ('media/../graph.json', 'path escapes'), ('media\\queue-empty.svg', 'backslash')):
            with self.subTest(path=path):
                fixture = FixtureCopy(self)
                manifest = fixture.manifest()
                manifest['files'][0] = dict(manifest['files'][0], path=path)
                fixture.write_manifest(manifest)
                self.assertRejected(fixture.root, expected)

    def test_rejects_external_and_sensitive_text(self):
        cases = (
            ('external URL in graph.json', lambda g: g['workspace']['copy'].update(app_summary='See https://cdn.example.test/kit')),
            ('email address in graph.json', lambda g: g['workspace']['teams'][0].update(label='owner@example.test')),
            ('personal home path in graph.json', lambda g: g['workspace']['copy'].update(search_hint='/Users/someone/file')),
            ('Figma file reference in graph.json', lambda g: g['workspace']['copy'].update(back='figma.com/design/abc')),
            ('source is not a manifest path', lambda g: g['nodes'][0].update(source='../owned-design-baseline/graph.json')),
            ('not an approved served manifest asset', lambda g: g['workspace']['evidence'][0].update(asset='media/missing.svg')),
            ('lowercase sRGB hex color', lambda g: g['workspace']['tokens'].update({'ink-primary': 'rgb(0, 0, 0)'})),
        )
        for expected, change in cases:
            with self.subTest(expected=expected):
                fixture = FixtureCopy(self)
                fixture.edit_graph(change)
                self.assertRejected(fixture.root, expected)

    def test_scan_allows_escaped_svg_namespace_only(self):
        self.assertEqual(workspace.scan_text('x.json', '{"svg": "<svg xmlns=\\"http://www.w3.org/2000/svg\\">"}'), [])
        self.assertEqual(workspace.scan_text('x.json', '"http://127.0.0.1:8893/index.html"'), [])
        self.assertTrue(workspace.scan_text('x.json', '"http://www.w3.org.evil.test/x"'))

    def test_rejects_stylesheet_network_fetch(self):
        fixture = FixtureCopy(self)
        with (fixture.root / 'styles.css').open('a', encoding='utf-8') as handle:
            handle.write('.x { background-image: url(remote.png); }\n')
        fixture.repin('styles.css')
        self.assertRejected(fixture.root, 'network fetch syntax in styles.css')


class ServeTest(unittest.TestCase):
    def start(self, root, access_log=None):
        server, _ = workspace.make_server(root, '127.0.0.1', 0, access_log)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def request(self, port, path, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_serves_only_approved_unchanged_files(self):
        fixture = FixtureCopy(self)
        log = fixture.base / 'served.jsonl'
        port = self.start(fixture.root, log)

        status, headers, body = self.request(port, '/')
        self.assertEqual(status, 200)
        self.assertEqual(body, (fixture.root / 'index.html').read_bytes())
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request(port, '/graph.json')[1]['Content-Type'], 'application/json')
        self.assertEqual(self.request(port, '/media/queue-empty.svg')[1]['Content-Type'], 'image/svg+xml')

        for path in ('/README.md', '/manifest.json', '/../../LICENSE', '/%2e%2e/%2e%2e/LICENSE',
                     '/media//queue-empty.svg', '/media/./queue-empty.svg', '/media%5cqueue-empty.svg', '/index.html%00'):
            with self.subTest(path=path):
                self.assertEqual(self.request(port, path)[0], 404)
        self.assertEqual(self.request(port, '/index.html', 'POST')[0], 501)

        with (fixture.root / 'styles.css').open('a', encoding='utf-8') as handle:
            handle.write('\n')
        status, _, body = self.request(port, '/styles.css')
        self.assertEqual(status, 409)
        self.assertIn(b'digest drift', body)

        rel = 'media/queue-empty.svg'
        outside = fixture.outside_copy(rel)
        (fixture.root / rel).unlink()
        os.symlink(outside, fixture.root / rel)
        self.assertEqual(self.request(port, '/' + rel)[0], 403)

        records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        served = {record['path']: record for record in records if record['status'] == 200}
        self.assertEqual(served['index.html']['sha256'], hashlib.sha256((fixture.root / 'index.html').read_bytes()).hexdigest())
        self.assertTrue(all(record['sha256'] is None for record in records if record['status'] != 200))

    def test_refuses_to_start_on_unsafe_input(self):
        fixture = FixtureCopy(self)
        with self.assertRaises(workspace.WorkspaceError):
            workspace.make_server(fixture.root, '0.0.0.0', 0)
        with self.assertRaises(workspace.WorkspaceError):
            workspace.make_server(fixture.root, '127.0.0.1', 0, fixture.root / 'served.jsonl')
        (fixture.root / 'renderer.js').write_text('// changed\n', encoding='utf-8')
        with self.assertRaises(workspace.WorkspaceError):
            workspace.make_server(fixture.root, '127.0.0.1', 0)


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.graph = load(FIXTURE / 'graph.json')
        self.by_id = {node['id']: node for node in self.graph['nodes']}

    def edges(self, source, kind):
        return [self.by_id[edge['to']] for edge in self.graph['edges'] if edge['from'] == source and edge['type'] == kind]

    def test_trace_is_complete_and_only_observation_is_pending(self):
        self.assertEqual(graph_tool.validate_graph(self.graph)[0], [])
        strict_errors, _ = graph_tool.validate_graph(self.graph, strict_local=True)
        self.assertTrue(strict_errors)
        self.assertTrue(all(re.search(r'must be (observed or )?verified\.$', error) for error in strict_errors), strict_errors)

        observed = copy.deepcopy(self.graph)
        for node in observed['nodes']:
            if node['type'] in ('requirement', 'screen'):
                node['status'] = 'observed'
            elif node['type'] == 'acceptance':
                node['status'] = 'verified'
        self.assertEqual(graph_tool.validate_graph(observed, strict_local=True)[0], [])
        for node in self.graph['nodes']:
            if node['type'] == 'figma':
                self.assertEqual((node['status'], node['layer']), ('planned', 'generated-private-output'))

    def test_production_scope_is_declared_in_the_graph(self):
        kinds = {node['kind'] for node in self.graph['nodes'] if node['type'] == 'state'}
        self.assertTrue({'ready', 'empty', 'error', 'idle', 'invalid', 'recorded'} <= kinds)
        components = {node['component_key'] for node in self.graph['nodes'] if node['type'] == 'component'}
        self.assertEqual(components, {'status-badge', 'data-table', 'form-field', 'gate-disclosure', 'evidence-card'})
        data = self.graph['workspace']
        self.assertGreaterEqual(len(data['packages']), 6)
        self.assertGreaterEqual(len(data['gates']), 2)
        self.assertGreaterEqual(len(data['evidence']), 2)
        self.assertEqual(len({gate['title'] for gate in data['gates']}), len(data['gates']))

    def test_states_are_reachable_and_transitions_are_unambiguous(self):
        states = [node for node in self.graph['nodes'] if node['type'] == 'state']
        queue = deque(state['id'] for state in states if state['initial'])
        seen = set(queue)
        while queue:
            current = queue.popleft()
            choices = set()
            for action in self.edges(current, 'accepts input'):
                key = (action['control'], action.get('outcome'))
                self.assertNotIn(key, choices, f'{current} has two actions for {key}')
                choices.add(key)
                for target in self.edges(action['id'], 'navigates to'):
                    if target['id'] not in seen:
                        seen.add(target['id'])
                        queue.append(target['id'])
        for state in states:
            if state['id'] not in seen:
                self.assertEqual(state.get('entry'), 'route', f'{state["id"]} is unreachable and not a route entry')
        self.assertEqual([state['id'] for state in states if state.get('entry') == 'route'], ['STATE-QUEUE-ERROR'])


class SingleSourceTest(unittest.TestCase):
    def setUp(self):
        self.graph = load(FIXTURE / 'graph.json')
        self.sources = {name: (FIXTURE / name).read_text(encoding='utf-8') for name in ('index.html', 'styles.css', 'renderer.js')}

    def graph_strings(self):
        found = []

        def walk(value):
            if isinstance(value, str):
                found.append(value)
            elif isinstance(value, dict):
                for key, item in value.items():
                    if key != 'tone':
                        walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(self.graph['workspace'])
        for node in self.graph['nodes']:
            found += [node['id'], node['title'], node.get('detail', '')]
        return [value for value in found if value]

    def test_renderer_repeats_no_graph_copy_or_value(self):
        for value in self.graph_strings():
            for name, content in self.sources.items():
                if ' ' in value or len(value) >= 12:
                    self.assertFalse(value in content, f'{value!r} duplicated in {name}')
                else:
                    literal = re.search(r'[\'"`]' + re.escape(value) + r'[\'"`]', content)
                    self.assertIsNone(literal, f'{value!r} literal in {name}')

    def test_styles_use_only_graph_tokens(self):
        styles = self.sources['styles.css']
        self.assertNotRegex(styles, r'#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(')
        self.assertNotRegex(self.sources['renderer.js'], r'[\'"]#[0-9a-fA-F]{3,8}[\'"]')
        tokens = self.graph['workspace']['tokens']
        self.assertEqual(set(re.findall(r'var\(--([a-z-]+)\)', styles)) - set(tokens), set())
        data = self.graph['workspace']
        tones = {entry['tone'] for entry in data['statuses'] + data['gate_results']}
        tones |= {node['tone'] for node in self.graph['nodes'] if 'tone' in node}
        self.assertEqual(tones - set(re.findall(r'\[data-tone="([a-z]+)"\]', styles)), set())

    def test_tokens_continue_the_owned_baseline(self):
        baseline = (ROOT / 'examples' / 'owned-design-baseline' / 'styles.css').read_text(encoding='utf-8')
        declared = dict(re.findall(r'--([a-z-]+):\s*([^;]+);', baseline.split('}', 1)[0]))
        tokens = self.graph['workspace']['tokens']
        self.assertEqual({name: tokens[name] for name in declared}, {name: value.strip() for name, value in declared.items()})

    def test_manifest_rights_match_repository_license(self):
        manifest = load(FIXTURE / 'manifest.json')
        license_text = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertIn('MIT License', license_text)
        self.assertIn(manifest['ownership']['copyright'], license_text)
        self.assertTrue((FIXTURE / manifest['ownership']['license_path']).resolve().samefile(ROOT / 'LICENSE'))
        self.assertEqual(manifest['schema'], workspace.SCHEMA)
        for entry in manifest['files']:
            self.assertNotIn(Path(entry['path']).suffix, {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.woff', '.woff2', '.ttf'})


if __name__ == '__main__':
    unittest.main()
