from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from development_witnesses import witness_index


REVIEW = 'release/reviews/panel.json'
WITNESS = 'release/reviews/evidence/panel/fixture.json'
SOURCE = 'panel-ui/src/feature.jsx'
TEST = 'tests/test_feature.cjs'
AUTHORITY = 'library/panel-design/governance.json#/fixture'
FINGERPRINT = 'a' * 64


class DevelopmentWitnessesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.test_sha = self.write(TEST, "throw new Error('Do not execute development evidence.');\n")
        self.witness = {
            'schema': 'figma-flow-major-witness-v1',
            'surfaceFingerprint': FINGERPRINT,
            'status': 'passed',
            'checks': [{
                'test': TEST, 'case': 'renders the bound style', 'testSha256': self.test_sha,
                'authority': AUTHORITY, 'covers': [SOURCE, 'panel-ui/src/unbound.jsx'],
                'assertion': 'The panel renders the bound style.', 'observed': 'The style appeared.',
            }],
        }
        self.review = {
            'schema': 'figma-flow-major-review-v1', 'surface': 'panel', 'fingerprint': FINGERPRINT,
            'openFindings': [], 'bindings': [{
                'authority': AUTHORITY,
                'files': [SOURCE],
                'witnesses': [{'path': WITNESS, 'sha256': self.write(WITNESS, self.witness)}],
            }],
        }
        self.write(REVIEW, self.review)

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        content = (value if isinstance(value, str) else json.dumps(value)).encode()
        target.write_bytes(content)
        return sha256(content).hexdigest()

    def index(self, read=None):
        paths = {item.relative_to(self.root).as_posix() for item in self.root.rglob('*') if item.is_file()}
        return witness_index(read or (lambda path: (self.root / path).read_bytes()), paths, {
            'panel': {'coverage': 'review'}, 'gate-data': {'coverage': 'gate-data'},
        })

    def test_finds_historical_candidates_in_both_directions_without_executing_tests(self):
        index = self.index()
        result = index.for_path(SOURCE, 'panel')
        self.assertEqual(result['status'], 'historical-candidates')
        self.assertEqual(result['checks'][0]['testStatus'], 'historical-match')
        self.assertEqual(result['checks'][0]['actualTestSha256'], self.test_sha)
        self.assertEqual(set(index.inputs), {TEST, REVIEW, WITNESS})
        for trigger in (TEST, REVIEW, WITNESS):
            self.assertEqual(index.dependencies(trigger)[0]['coveredPaths'], [SOURCE])
            self.assertEqual(index.dependencies(trigger)[0]['surface'], 'panel')
        self.assertEqual(index.for_path('panel-ui/src/unbound.jsx', 'panel')['status'], 'no-file-witness')
        self.assertEqual(index.dependencies('release/reviews/gate-data.json'), [])

    def test_stale_missing_and_unreadable_tests_keep_exact_reverse_routes(self):
        changed = self.write(TEST, 'A different test source.')
        index = self.index()
        result = index.for_path(SOURCE, 'panel')
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(result['checks'][0]['testStatus'], 'stale-source')
        self.assertEqual(result['checks'][0]['actualTestSha256'], changed)
        self.assertEqual(index.dependencies(TEST)[0]['status'], 'needs-review')
        self.assertEqual(index.dependencies(TEST)[0]['coveredPaths'], [SOURCE])

        def read(path):
            if path == TEST:
                raise PermissionError(path)
            return (self.root / path).read_bytes()

        self.assertEqual(self.index(read).for_path(SOURCE, 'panel')['checks'][0]['testStatus'], 'unreadable-source')
        (self.root / TEST).unlink()
        missing = self.index()
        check = missing.for_path(SOURCE, 'panel')['checks'][0]
        self.assertEqual(check['testStatus'], 'missing-source')
        self.assertFalse(check['testPresent'])
        self.assertEqual(missing.dependencies(TEST)[0]['coveredPaths'], [SOURCE])

    def test_invalid_witness_does_not_establish_new_test_routes_or_erase_review_requirement(self):
        wrong_test = 'tests/test_forged.cjs'
        self.witness['checks'][0]['test'] = wrong_test
        self.write(WITNESS, self.witness)
        index = self.index()
        self.assertEqual(index.dependencies(wrong_test), [])
        self.assertEqual(index.for_path(SOURCE, 'panel')['status'], 'needs-review')
        self.assertIn('differs from its declaration', index.for_path(SOURCE, 'panel')['reason'])
        for trigger in (REVIEW, WITNESS):
            self.assertEqual(index.dependencies(trigger)[0]['status'], 'needs-review')
            self.assertEqual(index.dependencies(trigger)[0]['coveredPaths'], [SOURCE])

    def test_missing_sibling_witness_keeps_valid_candidates_and_reports_review(self):
        absent = 'release/reviews/evidence/panel/absent.json'
        self.review['bindings'][0]['witnesses'].append({'path': absent, 'sha256': 'e' * 64})
        self.write(REVIEW, self.review)
        index = self.index()
        result = index.for_path(SOURCE, 'panel')
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual([item['witness'] for item in result['checks']], [WITNESS])
        self.assertIn(absent, result['reason'])
        self.assertEqual(index.dependencies(absent)[0]['status'], 'needs-review')
        self.assertEqual(index.dependencies(TEST)[0]['status'], 'historical-candidates')

    def test_digest_match_cannot_authorize_an_incomplete_witness(self):
        self.witness['checks'][0]['covers'] = ['panel-ui/src/unbound.jsx']
        self.review['bindings'][0]['witnesses'][0]['sha256'] = self.write(WITNESS, self.witness)
        self.write(REVIEW, self.review)
        index = self.index()
        self.assertEqual(index.dependencies(TEST), [])
        self.assertIn('does not account for', index.for_path(SOURCE, 'panel')['reason'])
        self.assertEqual(index.dependencies(WITNESS)[0]['status'], 'needs-review')

    def test_unreadable_review_keeps_surface_route_without_forging_covered_paths(self):
        self.write(REVIEW, '{ broken')
        index = self.index()
        self.assertEqual(index.for_path(SOURCE, 'panel')['status'], 'needs-review')
        self.assertEqual(index.dependencies(REVIEW)[0]['status'], 'needs-review')
        self.assertEqual(index.dependencies(REVIEW)[0]['coveredPaths'], [])
        self.assertEqual(index.dependencies(TEST), [])


if __name__ == '__main__':
    unittest.main()
