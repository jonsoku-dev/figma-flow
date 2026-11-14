import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_read_benchmark as bench
import figma_workspace

FILE_KEY, PAGE_ID = 'PrivateFileKey123', '643:1'
LIVE = {'native_status': 'current-self-reported', 'expected_native': {'generation': 'a'}, 'observed_native': {'generation': 'a'}}


class FakeControl:
    """Stands in for figma_control; its numbers are never native evidence."""

    def __init__(self, states=None, width=42):
        self.states, self.width, self.calls, self.clock = list(states or []), width, [], 100.0

    def __call__(self, key, revision):
        self.calls.append(key)
        state = self.states.pop(0) if self.states else 'ok'
        created = self.clock
        self.clock += 10
        status = {'id': f'{len(self.calls):032x}', 'state': state, 'created_at': created, 'claimed_at': created + 0.25,
                  'completed_at': created + 2.25 if state == 'ok' else None}
        if state != 'ok':
            return status, None, 3000.0
        width = self.width(len(self.calls)) if callable(self.width) else self.width
        readback = {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': FILE_KEY, 'pageId': PAGE_ID,
                    'allowed_page_ids': [PAGE_ID], 'collections': [], 'variables': [], 'rasterImages': {},
                    'nodes': [{'id': PAGE_ID, 'unavailable_fields': {'fills': 'unsupported on this node'}},
                              {'id': '643:2', 'width': width, 'unavailable_fields': {}}],
                    'observed_at': f'2026-11-15T00:00:{len(self.calls):02d}Z'}
        if key == 'p2-private-timed':
            readback['read_measurement'] = {'schema': 'figma-flow-native-read-measurement-v1', 'mode': 'timing', 'clock': 'Date.now',
                                            'pages': [{'pageId': PAGE_ID, 'reader_elapsed_ms': 1000 + len(self.calls)}],
                                            'discovery_elapsed_ms': 1500}
        if key == 'p2-private-diag':
            readback['read_measurement'] = {'schema': 'figma-flow-native-read-measurement-v1', 'mode': 'getter-counts', 'clock': 'Date.now',
                                            'pages': [{'pageId': PAGE_ID, 'reader_elapsed_ms': 9000, 'instrumented': True,
                                                       'reader_result_bytes': 512, 'node_property_gets': 140, 'node_property_has': 90,
                                                       'by_property': {'fills': 6, 'id': 40},
                                                       'api_calls': {'node.loadAsync': {'calls': 1, 'elapsed_ms': 4000}}}],
                                            'discovery_elapsed_ms': 9500}
        return status, json.dumps(readback).encode(), 2500.0 + len(self.calls)


TASKS = {'discovery-full-default': ('p2-private-default', 'd' * 64), 'discovery-full-timed': ('p2-private-timed', 't' * 64),
         'discovery-full-diagnostic': ('p2-private-diag', 'g' * 64)}


def execute(control, tasks=TASKS, repeats=5, after=LIVE):
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / 'run'
        report = bench.run({'tasks': tasks, 'repeats': repeats, 'scope': {'file_key': FILE_KEY, 'page_id': PAGE_ID}}, out,
                           control=control, execution='unit-mock', pins={'source_commit': 'c' * 40, 'dirty': False},
                           before=LIVE, readiness_after=lambda: after)
        samples = [json.loads(line) for line in (out / 'samples.jsonl').read_text().splitlines()]
        public = (out / 'public-summary.json').read_text()
    return report, samples, public


class NativeReadBenchmarkTest(unittest.TestCase):
    def test_alternates_workloads_and_keeps_diagnostic_out_of_statistics(self):
        control = FakeControl()
        report, samples, _ = execute(control)
        self.assertEqual(control.calls, ['p2-private-default', 'p2-private-timed'] * 5 + ['p2-private-diag'])
        self.assertEqual(report['verdict'], 'baseline-recorded')
        self.assertFalse(report['native_proof'], 'mocked control is never native proof')
        self.assertEqual(report['executions'], ['unit-mock'])
        default, timed = report['workloads']['discovery-full-default'], report['workloads']['discovery-full-timed']
        self.assertEqual((default['ok'], default['retries'], default['timeouts']), (5, 0, 0))
        self.assertIsNone(default['stats']['reader_elapsed_ms'], 'default discovery has no reader clock')
        self.assertEqual(timed['stats']['reader_elapsed_ms'], {'n': 5, 'median': 1006, 'min': 1002, 'max': 1010})
        self.assertEqual(timed['stats']['queue_ms']['median'], 250)
        self.assertEqual(timed['stats']['plugin_span_ms']['median'], 2000)
        self.assertNotIn('discovery-full-diagnostic', report['workloads'])
        self.assertTrue(all(sample['getter_counts'] is None for sample in samples if sample['role'] == 'sample'))
        profile = report['diagnostic']['profile']['pages'][0]
        self.assertEqual((profile['node_property_gets'], profile['named_call_elapsed_ms'], profile['unattributed_ms']), (140, 4000, 5000))
        self.assertTrue(report['timing_overhead_check']['ranges_overlap'])
        self.assertEqual(report['scope']['nodes'], 2)
        self.assertEqual(report['coverage']['unavailable_fields'], 1)
        self.assertFalse(report['summary_profile']['measured'], 'summary is explicitly unmeasured')

    def test_failures_are_counted_not_retried_or_dropped(self):
        control = FakeControl(states=['ok', 'expired'])
        report, samples, _ = execute(control)
        self.assertEqual(len(control.calls), 11, 'a failed read is not retried')
        timed = report['workloads']['discovery-full-timed']
        self.assertEqual((timed['attempts'], timed['ok'], timed['timeouts']), (5, 4, 1))
        self.assertIsNone(timed['stats'])
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertIn('expired', [sample['state'] for sample in samples])

    def test_content_drift_blocks_statistics(self):
        report, _, _ = execute(FakeControl(width=lambda call: 42 if call < 6 else 43))
        self.assertEqual(report['verdict'], 'inconclusive')
        self.assertIn('content drift across successful samples', report['reasons'])
        self.assertTrue(all(entry['stats'] is None for entry in report['workloads'].values()))

    def test_content_hash_ignores_only_volatile_fields(self):
        control = FakeControl()
        status, raw, elapsed = control('p2-private-timed', 't' * 64)
        timed = bench.sample_from('discovery-full-timed', 'sample', 0, status, raw, elapsed, 'unit-mock')
        status, raw, elapsed = control('p2-private-default', 'd' * 64)
        default = bench.sample_from('discovery-full-default', 'sample', 1, status, raw, elapsed, 'unit-mock')
        self.assertEqual(timed['content_sha256'], default['content_sha256'])
        mismatch = bench.sample_from('discovery-full-default', 'sample', 2, *control('p2-private-timed', 't' * 64), 'unit-mock')
        self.assertEqual(mismatch['state'], 'workload-mismatch', 'a measured task cannot stand in for the default workload')

    def test_stale_runtime_after_run_is_inconclusive(self):
        report, _, _ = execute(FakeControl(), after={**LIVE, 'native_status': 'unverified'})
        self.assertEqual(report['verdict'], 'inconclusive')

    def test_public_summary_hides_private_ids(self):
        _, _, public = execute(FakeControl())
        for private in (FILE_KEY, PAGE_ID, '643:2', 'p2-private'):
            self.assertNotIn(private, public)
        self.assertEqual(json.loads(public)['scope']['nodes'], 2)

    def test_runner_requires_five_repeats(self):
        with self.assertRaises(SystemExit):
            bench.main(['--workspace', '.', '--file-key', FILE_KEY, '--page-id', PAGE_ID, '--timed', 'k:' + 't' * 64,
                        '--repeats', '4', '--out', 'unused'])

    def test_workspace_admits_measured_discover_tasks(self):
        tail, options, _ = figma_workspace.arguments('discover', ['--file-key', FILE_KEY, '--page-id', PAGE_ID, '--read-measure', 'timing'])
        self.assertEqual(options['--read-measure'], 'timing')
        self.assertIn('--read-measure', tail)


if __name__ == '__main__':
    unittest.main()
