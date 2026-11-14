import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_read_benchmark as bench

FILE_KEY, PAGE_ID = 'RequestedFile123', '7:1'
LIVE = {'native_status': 'current-self-reported', 'expected_native': {'generation': 'a'}, 'observed_native': {'generation': 'a'}}
TASKS = {'discovery-full-default': ('diag-default', 'd' * 64), 'discovery-full-timed': ('diag-timed', 't' * 64),
         'discovery-full-diagnostic': ('diag-counts', 'g' * 64)}
COUNTS = {'pageId': PAGE_ID, 'reader_elapsed_ms': 900, 'instrumented': True, 'reader_result_bytes': 300,
          'node_property_gets': 120, 'node_property_has': 40, 'by_property': {'id': 30, 'fills': 4},
          'api_calls': {'node.loadAsync': {'calls': 1, 'elapsed_ms': 200}}}


def control(diagnostic=None):
    """Mock control; `diagnostic` edits the getter-counts result. Never native evidence."""
    calls = []

    def read(key, revision):
        calls.append(key)
        created = 100.0 + len(calls) * 10
        status = {'id': f'{len(calls):032x}', 'state': 'ok', 'created_at': created, 'claimed_at': created + .25, 'completed_at': created + 2}
        readback = {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': FILE_KEY, 'pageId': PAGE_ID,
                    'allowed_page_ids': [PAGE_ID], 'collections': [], 'variables': [], 'rasterImages': {},
                    'nodes': [{'id': PAGE_ID, 'unavailable_fields': {}}, {'id': '7:2', 'width': 42, 'unavailable_fields': {}}],
                    'observed_at': f'2026-11-15T00:00:{len(calls):02d}Z'}
        if key == 'diag-timed':
            readback['read_measurement'] = {'schema': 'figma-flow-native-read-measurement-v1', 'mode': 'timing', 'clock': 'performance.now',
                                            'pages': [{'pageId': PAGE_ID, 'reader_elapsed_ms': 500}], 'discovery_elapsed_ms': 600}
        if key == 'diag-counts':
            readback['read_measurement'] = {'schema': 'figma-flow-native-read-measurement-v1', 'mode': 'getter-counts', 'clock': 'performance.now',
                                            'pages': [dict(COUNTS)], 'discovery_elapsed_ms': 1000}
            if diagnostic:
                result = diagnostic(status, readback)
                if result is not None:
                    return result
        return status, json.dumps(readback).encode(), 2500.0
    return read


def execute(read, tasks=TASKS):
    with tempfile.TemporaryDirectory() as directory:
        return bench.run({'tasks': tasks, 'repeats': 5, 'scope': {'file_key': FILE_KEY, 'page_id': PAGE_ID}}, Path(directory) / 'run',
                         control=read, execution='root-live', pins={'dirty': False}, before=LIVE, readiness_after=lambda: LIVE)


def failed(status, readback):
    status.update(state='error', error='proxy: inconsistent get')
    return status, None, 2500.0


def without_counts(status, readback):
    for key in ('node_property_gets', 'node_property_has', 'by_property', 'api_calls', 'reader_result_bytes'):
        readback['read_measurement']['pages'][0].pop(key)


def other_page(status, readback):
    readback['pageId'] = '9:9'
    readback['allowed_page_ids'] = ['9:9']


def other_content(status, readback):
    readback['nodes'][1]['width'] = 43


def missing_page(status, readback):
    readback['read_measurement']['pages'] = []


class DiagnosticGateTest(unittest.TestCase):
    def assert_blocked(self, report, label):
        self.assertTrue(report['verdict'] == 'inconclusive', f'diagnostic gate: {label} must make the verdict inconclusive')
        self.assertTrue(report['native_proof'] is False, f'diagnostic gate: {label} must not be native proof')

    def test_valid_diagnostic_is_required_for_native_proof(self):
        report = execute(control())
        self.assertTrue(report['verdict'] == 'baseline-recorded', 'diagnostic gate: a valid diagnostic with clean samples records the baseline')
        self.assertTrue(report['native_proof'] is True, 'diagnostic gate: a valid root-live run is native proof')

    def test_failed_diagnostic_blocks_the_baseline(self):
        report = execute(control(failed))
        self.assert_blocked(report, 'a failed diagnostic')
        self.assertTrue(report['diagnostic']['state'] == 'error', 'diagnostic gate: the failed diagnostic state is preserved')

    def test_missing_diagnostic_blocks_the_baseline(self):
        self.assert_blocked(execute(control(), {name: task for name, task in TASKS.items() if name != 'discovery-full-diagnostic'}),
                            'a missing diagnostic')

    def test_diagnostic_without_counts_blocks_the_baseline(self):
        self.assert_blocked(execute(control(without_counts)), 'a diagnostic without getter counts')

    def test_diagnostic_without_every_page_blocks_the_baseline(self):
        self.assert_blocked(execute(control(missing_page)), 'a diagnostic missing page counts')

    def test_diagnostic_from_another_scope_blocks_the_baseline(self):
        self.assert_blocked(execute(control(other_page)), 'a diagnostic from another page')

    def test_diagnostic_with_other_content_blocks_the_baseline(self):
        self.assert_blocked(execute(control(other_content)), 'a diagnostic with other content')


if __name__ == '__main__':
    unittest.main()
