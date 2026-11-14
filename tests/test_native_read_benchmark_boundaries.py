import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_read_benchmark as bench

FILE_KEY, PAGE_ID = 'RequestedFile123', '7:1'
LIVE = {'native_status': 'current-self-reported', 'expected_native': {'generation': 'a'}, 'observed_native': {'generation': 'a'}}
TASKS = {'discovery-full-default': ('boundary-default', 'd' * 64)}


def control(file_key=FILE_KEY, page_id=PAGE_ID):
    calls = []

    def read(key, revision):
        calls.append(key)
        created = 100.0 + len(calls) * 10
        readback = {'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': file_key, 'pageId': page_id,
                    'allowed_page_ids': [page_id], 'collections': [], 'variables': [], 'rasterImages': {},
                    'nodes': [{'id': page_id, 'unavailable_fields': {'fills': 'unsupported on this node'}}],
                    'observed_at': f'2026-11-15T00:00:{len(calls):02d}Z'}
        status = {'id': f'{len(calls):032x}', 'state': 'ok', 'created_at': created, 'claimed_at': created + .25, 'completed_at': created + 2}
        return status, json.dumps(readback).encode(), 2500.0
    return read


def execute(read, pins, execution='unit-mock'):
    with tempfile.TemporaryDirectory() as directory:
        return bench.run({'tasks': TASKS, 'repeats': 5, 'scope': {'file_key': FILE_KEY, 'page_id': PAGE_ID}}, Path(directory) / 'run',
                         control=read, execution=execution, pins=pins, before=LIVE, readiness_after=lambda: LIVE)


class BenchmarkBoundaryTest(unittest.TestCase):
    def test_full_discovery_coverage_is_not_inferred_complete(self):
        report = execute(control(), {'dirty': False})
        coverage = report['coverage']
        self.assertEqual(coverage['unavailable_fields'], 1)
        self.assertTrue(coverage['complete'] is not True,
                        'benchmark boundary: discovery readback has no coverage object, so completeness must not be inferred')

    def test_dirty_source_cannot_record_a_baseline(self):
        report = execute(control(), {'dirty': True}, execution='root-live')
        self.assertFalse(report['native_proof'], 'benchmark boundary: dirty source must never be native proof')
        self.assertTrue(report['verdict'] == 'inconclusive', 'benchmark boundary: dirty source must make the verdict inconclusive')

    def test_unknown_source_state_cannot_record_a_baseline(self):
        report = execute(control(), {}, execution='root-live')
        self.assertTrue(report['verdict'] == 'inconclusive', 'benchmark boundary: unpinned source state must make the verdict inconclusive')

    def test_readback_from_another_file_or_page_is_not_a_sample(self):
        for read in (control(file_key='OtherFile456'), control(page_id='9:9')):
            report = execute(read, {'dirty': False})
            entry = report['workloads']['discovery-full-default']
            self.assertTrue(entry['ok'] == 0, 'benchmark boundary: readback outside the requested file/page must not count as a sample')
            self.assertTrue(entry['failures'] == {'scope-mismatch': 5}, 'benchmark boundary: scope mismatches must be counted as failures')

    def test_appendix_does_not_bound_cache_savings_from_full_reader_share(self):
        appendix = (ROOT / 'docs/next-roadmap/NF-02-incremental-native-read.md').read_text(encoding='utf-8')
        self.assertFalse('캐시가 줄일 수 있는 시간의 상한' in appendix,
                         'benchmark boundary: full reader share must not be presented as a cache-savings bound')


if __name__ == '__main__':
    unittest.main()
