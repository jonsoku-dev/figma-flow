"""Offline declaration coverage and inert request drafts, not API acceptance."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import figma_rest_inventory as inventory


class FigmaRESTInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = inventory.load()

    def test_offline_search_and_concrete_parameters(self):
        result = inventory.search(self.catalog, 'file_variables:read', method='GET', limit=0)
        self.assertEqual({row['operation_id'] for row in result['rows']},
                         {'getLocalVariables', 'getPublishedVariables'})
        row = inventory.search(self.catalog, 'getFileNodes')['rows'][0]
        self.assertTrue({'file_key', 'ids'} <= {p['name'] for p in row['parameters']})
        variables = result['rows'][0]
        self.assertTrue(any('Enterprise' in note for note in variables['access_notes']))
        self.assertIsNone(variables['rate_limit_tier'])
        self.assertTrue(variables['docs_urls'])
        self.assertIn(self.catalog['source']['ref'], variables['source_url'])

    def test_templates_cover_required_parameters_and_bodies_without_requests(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            for endpoint in self.catalog['endpoints']:
                draft = inventory.template(self.catalog, endpoint['operation_id'])
                self.assertEqual(draft['method'], endpoint['method'])
                for parameter in endpoint['parameters']:
                    if not parameter.get('required'):
                        continue
                    self.assertIn({'in': parameter['in'], 'name': parameter['name']}, draft['required_parameters'])
                    target = draft['url'] if parameter['in'] in ('path', 'query') else json.dumps(draft['headers'])
                    self.assertIn('<' + parameter['name'] + '>', target)
                self.assertEqual(bool(endpoint['request_body']), 'body' in draft)
                self.assertFalse(re.search(r'\{[^}]+\}', draft['url']))
            nodes = inventory.template(self.catalog, 'getFileNodes')
            self.assertEqual(nodes['url'], 'https://api.figma.com/v1/files/<file_key>/nodes?ids=<ids>')
            comment = inventory.template(self.catalog, 'postComment')
            self.assertIn('message', comment['body'])
            self.assertEqual(comment['headers'], {'Content-Type': 'application/json'})
            self.assertIn('first alternative', comment['warning'])
            with self.assertRaisesRegex(ValueError, 'Unknown operation'):
                inventory.template(self.catalog, 'notAnEndpoint')

    def test_source_and_license_hashes_reject_changes(self):
        with patch.object(inventory.hashlib, 'sha256') as digest:
            digest.return_value.hexdigest.return_value = '0' * 64
            with self.assertRaisesRegex(ValueError, 'Pinned source hash mismatch'):
                inventory.verify_source()
        self.assertIn('MIT License', (inventory.LIBRARY / 'LICENSE').read_text())

    def test_regeneration_covers_every_official_operation_byte_identically(self):
        import yaml
        _, raw = inventory.verify_source()
        spec = yaml.safe_load(raw)
        expected = {(method.upper(), path, operation['operationId'])
                    for path, item in spec['paths'].items() for method, operation in item.items()
                    if method in inventory.METHODS}
        actual = {(row['method'], row['path'], row['operation_id']) for row in self.catalog['endpoints']}
        self.assertEqual(expected, actual)
        self.assertEqual(len(actual), 59)
        self.assertEqual(inventory.INDEX.read_text(), inventory.canonical(inventory.build()))

    def test_cli_search_and_template_need_only_standard_library(self):
        for args in [('search', 'getFileNodes'), ('template', 'postComment')]:
            result = subprocess.run([sys.executable, '-S', str(ROOT / 'tools/figma_rest_inventory.py'), *args],
                                    capture_output=True, text=True, check=True)
            self.assertIsInstance(json.loads(result.stdout), dict)

    def test_curl_export_encodes_parameters_and_keeps_auth_in_environment(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            draft = inventory.request_export(self.catalog, 'getFileNodes',
                                             {'file_key': 'a/b?x#z'}, {'ids': '1:2,3:4&x=5'}, auth='oauth')
        self.assertEqual(draft['url'], 'https://api.figma.com/v1/files/a%2Fb%3Fx%23z/nodes?ids=1%3A2%2C3%3A4%26x%3D5')
        args = shlex.split(draft['shell_command'])
        self.assertEqual(args[:4], ['curl', '--disable', '--globoff', '--proto'])
        self.assertIn('Authorization: Bearer ${FIGMA_TOKEN:?Set FIGMA_TOKEN}', args)
        self.assertEqual(args[args.index('--request') + 1], 'GET')
        self.assertEqual(args[args.index('--max-redirs') + 1], '0')
        self.assertNotIn('--location', args)
        self.assertEqual(draft['execution'], 'not-executed')
        with self.assertRaisesRegex(ValueError, 'Missing required path'):
            inventory.request_export(self.catalog, 'getFileNodes')
        for segment in ('.', '..'):
            with self.assertRaisesRegex(ValueError, 'dot segment'):
                inventory.request_export(self.catalog, 'getFile', {'file_key': segment})
        with self.assertRaisesRegex(ValueError, 'Missing required query'):
            inventory.request_export(self.catalog, 'getFileNodes', {'file_key': 'abc'})
        with self.assertRaisesRegex(ValueError, 'Undeclared query'):
            inventory.request_export(self.catalog, 'getFile', {'file_key': 'abc'}, {'evil': 'x'})
        with self.assertRaisesRegex(ValueError, 'unique NAME=VALUE'):
            inventory.assignments(['ids=a', 'ids=b'])

    def test_every_endpoint_exports_a_method_and_reviewed_body(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed ' body.json"
            for row in self.catalog['endpoints']:
                values = {location: {p['name']: 'example' for p in row['parameters']
                                     if p['in'] == location and p.get('required')}
                          for location in ('path', 'query')}
                body_file = None
                if row['request_body']:
                    path.write_text(json.dumps(inventory.template(self.catalog, row['operation_id'])['body']))
                    body_file = path
                oauth = any(self.catalog['security_schemes'][name]['type'] == 'oauth2'
                            for alternative in row['security'] for name in alternative)
                draft = inventory.request_export(self.catalog, row['operation_id'], values['path'],
                                                 values['query'], body_file, auth='oauth' if oauth else 'token')
                args = shlex.split(draft['shell_command'])
                self.assertEqual(args[args.index('--request') + 1], row['method'])
                if body_file:
                    self.assertEqual(args[args.index('--data-binary') + 1], '@' + str(path.resolve()))
                else:
                    self.assertNotIn('--data-binary', args)
            path.write_text('{}')
            draft = inventory.request_export(self.catalog, 'postComment', {'file_key': 'abc'}, body_file=path)
            self.assertIn('X-Figma-Token: ${FIGMA_TOKEN:?Set FIGMA_TOKEN}', shlex.split(draft['shell_command']))
            with self.assertRaisesRegex(ValueError, 'Required request body'):
                inventory.request_export(self.catalog, 'postComment', {'file_key': 'abc'})
            with self.assertRaisesRegex(ValueError, 'does not declare a request body'):
                inventory.request_export(self.catalog, 'getFile', {'file_key': 'abc'}, body_file=path)


if __name__ == '__main__':
    unittest.main()
