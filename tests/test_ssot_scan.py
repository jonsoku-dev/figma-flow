"""Scanner for hardcoded values that bypass their SSoT, its ratchet baseline, and the SSoT owners."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import ssot_scan  # noqa: E402
import local_endpoint  # noqa: E402
import relay_limits  # noqa: E402
import figma_control as control  # noqa: E402

CONFIG = {
    'schema': ssot_scan.CONFIG_SCHEMA,
    'baseline': 'tools/ssot-baseline.json',
    'scope': {'python': ['tools/*.py'], 'javascript': ['bridge/*.js'], 'exclude': ['tools/skip_*.py']},
    'rules': {
        'loopback-literal': {'owners': ['tools/endpoint_owner.py'], 'message': 'loopback'},
        'port-literal': {'owners': ['tools/endpoint_owner.py'], 'message': 'port'},
        'network-timeout-literal': {'owners': [], 'message': 'timeout'},
        'control-route-literal': {'owners': ['tools/endpoint_owner.py'], 'message': 'route'},
        'private-atomic-writer': {'owners': [], 'message': 'writer'},
        'vocabulary-literal': {'owners': [], 'message': 'vocabulary', 'vocabularies': [
            {'id': 'steps', 'owner': 'tools/steps.py', 'symbol': 'STEPS', 'field': 'action', 'ignoreValues': ['ready']}]},
        'timer-literal': {'owners': [], 'message': 'timer'},
        'inline-limit': {'owners': [], 'minimum': 1000, 'message': 'limit'},
        'schema-id-spread': {'owners': [], 'pattern': 'figma-flow-[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+',
                             'maxFiles': 1, 'message': 'schema'},
    },
    'allow': [{'rule': 'inline-limit', 'path': 'tools/client.py', 'key': '4096', 'reason': 'reviewed fixture'}],
}

CLIENT = '''
"""Talks to http://localhost:1234 in prose only (docstring is ignored)."""
import http.client
import os
import argparse

SCHEMA = 'figma-flow-fixture-v1'


def call(port, timeout=2.5):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    connection.request('POST', '/control/readiness', b'{}', {'Host': f'localhost:{port}'})
    raw = connection.getresponse().read(65537)
    if len(raw) > 65536 or len(raw) > 4096 or ord('a') >= 0xD800:
        raise ValueError('too large')
    return 'enable-control'


def write(path, raw):
    fd = os.open(path, os.O_CREAT, 0o600)
    os.replace(path, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=49185)
    return 'python3 tool.py enable --port 43180', 'ready'
'''

OWNER = '''
BIND_HOST = '127.0.0.1'
DRAFT_PORT = 49185
ROUTE = '/control/readiness'
'''

STEPS = '''
STEPS = (
    {'action': 'init-workspace'},
    {'action': 'enable-control'},
    {'action': 'ready'},
)
CONSUMER = 'figma-flow-fixture-v1'
'''

BRIDGE = r'''
// Comments never count: http://localhost:9999 setTimeout(x, 5000) 'figma-flow-fixture-v1'
/* block: '127.0.0.1' */
const ORIGIN = /^http:\/\/localhost:\d+\/$/;
const ratio = total / count / 2;
function f(value, code) {
  if (value.length > 2000) throw Error('limit');
  if (code >= 0xd800 && code < 2048) return 1;
  setTimeout(() => resolve(), 0);
  const timer = setTimeout(() => reject(Error('late')), 15000);
  setTimeout(() => done(), POLICY.timeoutsMs.plugin);
  return fetch('http://localhost:45000' + '/control/poll', {schema: 'figma-flow-fixture-v1'});
}
const template = `${a / b} is not a regex`;
'''


class Fixture:
    def __init__(self, test: unittest.TestCase):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.write('tools/ssot-scan.json', json.dumps(CONFIG))
        self.write('tools/client.py', CLIENT)
        self.write('tools/endpoint_owner.py', OWNER)
        self.write('tools/steps.py', STEPS)
        self.write('tools/skip_me.py', "HOST = 'localhost'\n")
        self.write('bridge/transport.js', BRIDGE)

    def write(self, name: str, text: str):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding='utf-8')

    def keys(self, rule: str, path: str | None = None):
        return sorted(f.key for f in ssot_scan.scan(self.root) if f.rule == rule and (path is None or f.path == path))


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture(self)

    def test_python_detectors_respect_owners_docstrings_exclusions_and_reviewed_exceptions(self):
        fx = self.fx
        self.assertEqual(fx.keys('loopback-literal', 'tools/client.py'), ['127.0.0.1', 'localhost'])
        self.assertEqual(fx.keys('loopback-literal', 'tools/endpoint_owner.py'), [])
        self.assertEqual(fx.keys('loopback-literal', 'tools/skip_me.py'), [])
        self.assertEqual(fx.keys('port-literal', 'tools/client.py'), ['43180', '49185'])
        self.assertEqual(fx.keys('port-literal', 'tools/endpoint_owner.py'), [])
        self.assertEqual(fx.keys('network-timeout-literal', 'tools/client.py'), ['2.5', '3'])
        self.assertEqual(fx.keys('control-route-literal', 'tools/client.py'), ['/control/readiness'])
        self.assertEqual(fx.keys('private-atomic-writer'), ['write'])
        self.assertEqual(fx.keys('inline-limit', 'tools/client.py'), ['65536', '65537'])
        self.assertEqual(fx.keys('vocabulary-literal'), ['steps:enable-control'])

    def test_javascript_lexer_ignores_comments_hex_division_and_zero_delays(self):
        fx = self.fx
        self.assertEqual(fx.keys('loopback-literal', 'bridge/transport.js'), ['localhost', 'localhost'])
        self.assertEqual(fx.keys('port-literal', 'bridge/transport.js'), ['45000'])
        self.assertEqual(fx.keys('timer-literal'), ['15000'])
        self.assertEqual(fx.keys('inline-limit', 'bridge/transport.js'), ['2000', '2048'])
        self.assertEqual(fx.keys('control-route-literal', 'bridge/transport.js'), ['/control/poll'])
        kinds = {kind for kind, _, _ in ssot_scan.js_tokens(BRIDGE)}
        self.assertIn('re', kinds)
        regexes = [value for kind, value, _ in ssot_scan.js_tokens(BRIDGE) if kind == 're']
        self.assertEqual(regexes, [r'^http:\/\/localhost:\d+\/$'])

    def test_schema_ids_are_flagged_only_when_repeated_across_files(self):
        hits = sorted((f.path, f.key) for f in ssot_scan.scan(self.fx.root) if f.rule == 'schema-id-spread')
        self.assertEqual({path for path, _ in hits}, {'tools/client.py', 'tools/steps.py', 'bridge/transport.js'})
        self.fx.write('tools/steps.py', STEPS.replace("CONSUMER = 'figma-flow-fixture-v1'\n", ''))
        self.fx.write('bridge/transport.js', BRIDGE.replace("{schema: 'figma-flow-fixture-v1'}", '{}'))
        self.assertEqual(self.fx.keys('schema-id-spread'), [])

    def test_missing_vocabulary_owner_fails_closed(self):
        self.fx.write('tools/steps.py', 'OTHER = ()\n')
        with self.assertRaisesRegex(ValueError, 'Vocabulary steps has no values'):
            ssot_scan.scan(self.fx.root)

    def test_reviewed_exception_requires_reason(self):
        config = json.loads(json.dumps(CONFIG))
        config['allow'][0]['reason'] = ' '
        self.fx.write('tools/ssot-scan.json', json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'reason'):
            ssot_scan.load_config(self.fx.root)


class RatchetTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture(self)

    def test_baseline_blocks_new_debt_and_requires_locking_in_resolved_debt(self):
        root = self.fx.root
        summary = ssot_scan.write_baseline(root, allow_growth=True)  # bootstrap is an explicit review step
        self.assertGreater(summary['findings'], 0)
        self.assertEqual(ssot_scan.check(root), [])

        self.fx.write('tools/new.py', "URL = 'http://localhost:8080'\n")
        grown = ssot_scan.check(root)
        self.assertTrue(any('[ssot:loopback-literal]' in p['message'] and p['path'] == 'tools/new.py' for p in grown))
        with self.assertRaisesRegex(ValueError, 'New SSoT debt'):
            ssot_scan.write_baseline(root)
        (root / 'tools/new.py').unlink()

        self.fx.write('tools/client.py', CLIENT.replace("default=49185", "default=DRAFT_PORT"))
        stale = ssot_scan.check(root)
        self.assertEqual(len(stale), 1)
        self.assertIn('port-literal|tools/client.py|49185 dropped from 1 to 0', stale[0]['message'])
        result = ssot_scan.write_baseline(root)
        self.assertEqual(result['removed'], 1)
        self.assertEqual(ssot_scan.check(root), [])

    def test_allow_growth_is_explicit(self):
        root = self.fx.root
        ssot_scan.write_baseline(root, allow_growth=True)
        self.fx.write('tools/new.py', "URL = 'http://localhost:8080'\n")
        # The new URL is both a loopback literal and a port literal.
        self.assertEqual(ssot_scan.write_baseline(root, allow_growth=True)['added'], 2)
        self.assertEqual(ssot_scan.check(root), [])

    def test_schema_registry_and_verified_mirrors_detect_drift_and_staleness(self):
        fx = self.fx
        root = fx.root
        registry = {
            'schema': 'figma-flow-schema-id-registry-v1',
            'ids': {
                'pyOnly': {'id': 'figma-flow-py-only-v1'},
                'fixture': {'id': 'figma-flow-fixture-v1', 'mirrors': ['bridge/transport.js']},
            },
        }
        fx.write('library/schema-ids.json', json.dumps(registry))
        fx.write('library/runtime-limits.json', json.dumps({'limits': {'a': 1000, 'b': 1000}}))
        fx.write('tools/client.py', CLIENT.replace("SCHEMA = 'figma-flow-fixture-v1'", "SCHEMA = 'figma-flow-py-only-v1'"))
        fx.write('tools/steps.py', STEPS.replace("CONSUMER = 'figma-flow-fixture-v1'\n", "OTHER = 'figma-flow-py-only-v1'\n"))
        fx.write('bridge/dup.js', 'if (a > 1000 || b > 1000) throw Error();\n')

        config = json.loads(json.dumps(CONFIG))
        config['rules']['schema-id-spread']['registry'] = 'library/schema-ids.json'
        config['mirrors'] = [
            {'rule': 'inline-limit', 'key': '1000', 'source': 'library/runtime-limits.json#/limits/a', 'paths': ['bridge/dup.js']},
            {'rule': 'inline-limit', 'key': '1000', 'source': 'library/runtime-limits.json#/limits/b', 'paths': ['bridge/dup.js']},
        ]
        fx.write('tools/ssot-scan.json', json.dumps(config))

        # Python hitting registered schema ID directly still fails even when mirrors is empty.
        hits = [f for f in ssot_scan.scan(root) if f.rule == 'schema-id-spread']
        self.assertEqual({(f.path, f.key) for f in hits}, {
            ('tools/client.py', 'figma-flow-py-only-v1'),
            ('tools/steps.py', 'figma-flow-py-only-v1'),
        })
        # JS mirror suppressed cleanly; duplicate-key mirrors in dup.js both match.
        self.assertEqual([f for f in ssot_scan.scan(root) if f.path == 'bridge/dup.js'], [])

        # Dropping 1 of 2 duplicate-key copies causes mirror-stale even though the other copy remains.
        fx.write('bridge/dup.js', 'if (a > 1000) throw Error();\n')
        stale = ssot_scan.check(root)
        self.assertTrue(any('[ssot:mirror-stale]' in p['message'] and p['path'] == 'bridge/dup.js' for p in stale))
        fx.write('bridge/dup.js', 'if (a > 1000 || b > 1000) throw Error();\n')

        # Changing the SSoT value without updating mirror causes hard mirror-drift failure.
        fx.write('library/runtime-limits.json', json.dumps({'limits': {'a': 2000, 'b': 1000}}))
        drift = ssot_scan.check(root)
        self.assertTrue(any('[ssot:mirror-drift]' in p['message'] for p in drift))
        with self.assertRaisesRegex(ValueError, 'mirror/parse'):
            ssot_scan.write_baseline(root, allow_growth=True)


class RepositoryTests(unittest.TestCase):
    def test_repository_has_no_ssot_debt_and_empty_baseline(self):
        config = ssot_scan.load_config(ROOT)
        self.assertEqual(ssot_scan.load_baseline(ROOT, config), {})
        self.assertEqual(ssot_scan.summary(ROOT)['findings'], 0)
        self.assertEqual(ssot_scan.check(ROOT), [])

    def test_endpoint_owner_reads_the_policy_ssot(self):
        policy = json.loads((ROOT / 'library/figma-profile/policy.json').read_bytes())
        endpoint = relay_limits.control_endpoint(policy)
        self.assertEqual(local_endpoint.BIND_HOST, endpoint['bindHost'])
        self.assertEqual(local_endpoint.ORIGIN_HOST, endpoint['originHost'])
        self.assertEqual(local_endpoint.DEFAULT_PORTS, endpoint['defaultPorts'])
        self.assertEqual(local_endpoint.timeout_seconds('probe') * 1000, endpoint['timeoutsMs']['probe'])
        self.assertEqual(local_endpoint.origin(43210), f"http://{endpoint['originHost']}:43210")
        self.assertTrue(local_endpoint.ORIGIN_PATTERN.fullmatch(local_endpoint.origin(43210)))
        self.assertEqual(control.RELAY_REPLY_LIMIT, policy['controlTransport']['relayReplyBytes'])
        self.assertEqual(control.CHANGE_REPLY_LIMIT, policy['controlTransport']['changeReplyBytes'])

    def test_endpoint_policy_rejects_partial_or_privileged_values(self):
        policy = json.loads((ROOT / 'library/figma-profile/policy.json').read_bytes())
        for mutate in (lambda e: e['timeoutsMs'].pop('probe'),
                       lambda e: e['defaultPorts'].update(control=80),
                       lambda e: e.update(bindHost='example.com'),
                       lambda e: e['timeoutsMs'].update(request=0)):
            broken = json.loads(json.dumps(policy))
            mutate(broken['controlEndpoint'])
            with self.assertRaises(ValueError):
                relay_limits.control_endpoint(broken)

    def test_setup_steps_are_table_driven_and_ordered(self):
        self.assertEqual(control.SETUP_ACTIONS[0], 'init-workspace')
        self.assertEqual(control.SETUP_ACTIONS[-1], 'ready')
        facts = {'workspace': '/w', 'workspace_initialized': True, 'control_enabled': False}
        step = control.next_setup_step(facts)
        self.assertEqual(step['next_action'], 'enable-control')
        self.assertIn(f"--port {local_endpoint.DEFAULT_PORTS['control']}", step['next_command'])
        done = {'workspace_initialized': True, 'control_enabled': True, 'manifest_synced': True,
                'server_running': True, 'plugin_connected': True, 'uncertain_operations': 0,
                'profile_confirmed': True}
        self.assertEqual(control.next_setup_step(done)['next_action'], 'ready')
        self.assertIsNone(control.next_setup_step(done)['next_command'])
        self.assertEqual(control.next_setup_step({**done, 'uncertain_operations': 2})['next_action'],
                         'reconcile-uncertain')

    @unittest.skipUnless(os.name == 'posix', 'owner-only modes are POSIX')
    def test_private_io_writes_owner_only_and_refuses_symlinks(self):
        import private_io
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'nested' / 'state.json'
            private_io.atomic_write_json(target, {'a': 1})
            self.assertEqual(json.loads(target.read_text()), {'a': 1})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            shared = Path(temp) / 'nested' / 'shared.json'
            private_io.atomic_write(shared, b'{}', mode=0o640)
            self.assertEqual(shared.stat().st_mode & 0o777, 0o640)
            dir_fd = os.open(target.parent, os.O_RDONLY)
            try:
                private_io.atomic_write_dir_fd(dir_fd, 'excl.json', b'1', exclusive=True)
                with self.assertRaises(FileExistsError):
                    private_io.atomic_write_dir_fd(dir_fd, 'excl.json', b'2', exclusive=True)
                private_io.atomic_write_dir_fd(dir_fd, 'excl.json', b'2', exclusive=False)
                self.assertEqual((target.parent / 'excl.json').read_bytes(), b'2')
            finally:
                os.close(dir_fd)
            link = Path(temp) / 'link.json'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                private_io.atomic_write(link, b'x')
            self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ['excl.json', 'shared.json', 'state.json'])

    def test_schema_ids_and_runtime_limits_validate(self):
        import runtime_limits
        import schema_ids
        self.assertIn('control', schema_ids.ID)
        with tempfile.TemporaryDirectory() as temp:
            bad_schema = Path(temp) / 'schema.json'
            bad_schema.write_text(json.dumps({'schema': 'figma-flow-schema-id-registry-v1',
                                              'ids': {'a': {'id': 'bad'}, 'b': {'id': 'bad'}}}))
            with self.assertRaises(ValueError):
                schema_ids._load(bad_schema)
            bad_limits = Path(temp) / 'limits.json'
            bad_limits.write_text(json.dumps({'schema': 'figma-flow-runtime-limits-v1', 'network': {'x': 0}}))
            with self.assertRaises(ValueError):
                runtime_limits._load(bad_limits)


if __name__ == '__main__':
    unittest.main()
