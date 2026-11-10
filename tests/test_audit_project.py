import contextlib
import io
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'tools'))
import audit_project


class ProjectAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'app').mkdir()
        (self.root / 'tests').mkdir()
        (self.root / 'brief.md').write_text('After retry, show the same card.\n')
        (self.root / 'app/cards.cjs').write_text('module.exports = 1;\n')
        (self.root / 'app/review.cjs').write_text("const card = require('./cards.cjs'); module.exports = card;\n")
        (self.root / 'tests/cards.test.cjs').write_text("require('../app/cards.cjs');\n")
        (self.root / 'tests/review.test.cjs').write_text("require('../app/review.cjs');\n")
        self.graph = {'version': 1, 'nodes': [
            {'id': ident, 'type': kind, 'title': ident, 'status': 'observed', 'source': source}
            for ident, kind, source in [('CODE-CARDS', 'code', 'app/cards.cjs'), ('CODE-REVIEW', 'code', 'app/review.cjs'), ('TEST-CARDS', 'test', 'tests/cards.test.cjs'), ('TEST-REVIEW', 'test', 'tests/review.test.cjs')]],
            'edges': [{'from': code, 'to': test, 'type': 'depends-on'} for code, test in [('CODE-CARDS', 'TEST-CARDS'), ('CODE-REVIEW', 'TEST-REVIEW')]]}
        self.bindings = {'version': 1, 'authorities': {'intent': 'brief.md', 'implementation': 'app/review.cjs'}, 'dependency_edge_types': ['depends-on']}
        self.save()

    def save(self):
        for name, value in [('graph.json', self.graph), ('bindings.json', self.bindings)]:
            (self.root / name).write_text(json.dumps(value))

    def audit(self, specs=()):
        return audit_project.audit_project(self.root, 'graph.json', 'bindings.json', 'brief.md', specs)

    def cli(self, out='result', *flags):
        with contextlib.redirect_stderr(io.StringIO()):
            return audit_project.main(['--project', str(self.root), '--graph', 'graph.json', '--bindings', 'bindings.json', '--brief', 'brief.md', '--out', str(self.root / out), *flags])

    def test_legacy_node_sources_are_audited_without_rewriting(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.cli(), 1)
        result = json.loads((self.root / 'result/audit.json').read_text())
        self.assertEqual([(x['from'], x['to'], x['line']) for x in result['source_dependencies']['missing']], [('CODE-CARDS', 'CODE-REVIEW', 1)])
        self.assertEqual(result['brief_consistency']['status'], 'pass')
        self.assertEqual(result['acceptance_claim'], 'not-established')
        for name, value in before.items():
            self.assertEqual((self.root / name).read_bytes(), value)
        report = (self.root / 'result/audit.md').read_text()
        self.assertIn('app/review.cjs:1', report)
        self.assertIn('요구사항', report)

    def test_declared_indirect_import_path_is_clear(self):
        self.graph['edges'].append({'from': 'CODE-CARDS', 'to': 'CODE-REVIEW', 'type': 'depends-on'})
        self.save()
        self.assertEqual(self.cli(), 0)
        self.assertEqual(self.audit()['status'], 'checked-scope-clear')

    def test_explicit_spec_contradiction_remains_separate(self):
        (self.root / 'spec.md').write_text('After retry, show the next pending card.\n')
        self.assertEqual(self.cli('contradiction', '--spec', 'spec.md'), 1)
        result = self.audit(['spec.md'])
        self.assertEqual(result['source_dependencies']['status'], 'missing')
        self.assertEqual(result['brief_consistency']['status'], 'fail')
        self.assertEqual(result['acceptance_claim'], 'blocked-by-active-contradiction')
        markdown = audit_project.markdown(result)
        self.assertIn('spec.md:1', markdown)
        self.assertIn('brief.md:1', markdown)

    def test_unknown_sources_and_unparsed_prose_are_visible(self):
        (self.root / 'app/review.cjs').write_text('require(name);\n')
        (self.root / 'brief.md').write_text('The interface should feel welcoming.\n')
        self.assertEqual(self.cli(), 2)
        result = self.audit()
        self.assertEqual(result['source_dependencies']['status'], 'unknown')
        self.assertEqual(result['brief_consistency']['status'], 'review')
        self.assertIn('app/review.cjs', result['inputs'])
        self.assertEqual(result['brief_consistency']['unsupported'][0]['line'], 1)

    def test_existing_output_and_external_inputs_are_rejected(self):
        target = self.root / 'result'
        target.mkdir()
        (target / 'audit.json').write_text('preserve')
        self.assertEqual(self.cli(), 2)
        self.assertEqual((target / 'audit.json').read_text(), 'preserve')
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / 'spec.md'
            outside.write_text('outside')
            self.assertEqual(self.cli('outside', '--spec', str(outside)), 2)
            self.assertFalse((self.root / 'outside').exists())

    def test_scanners_called_once_and_drift_rejected(self):
        original = audit_project.audit_brief.audit
        def drifting(paths, **kwargs):
            result = original(paths, **kwargs)
            (self.root / 'app/cards.cjs').write_text('module.exports = 2;\n')
            return result
        with patch.object(audit_project.audit_dependencies, 'audit', wraps=audit_project.audit_dependencies.audit) as source, patch.object(audit_project.audit_brief, 'audit', side_effect=drifting) as brief:
            with self.assertRaisesRegex(ValueError, 'changed during analysis'):
                self.audit()
            self.assertEqual((source.call_count, brief.call_count), (1, 1))

    def test_nested_metadata_reference_bases(self):
        (self.root / 'metadata').mkdir()
        for node in self.graph['nodes']:
            node['source'] = '../' + node['source']
        self.bindings['authorities'] = {'intent': '../brief.md', 'implementation': '../app/review.cjs'}
        (self.root / 'metadata/graph.json').write_text(json.dumps(self.graph))
        (self.root / 'metadata/bindings.json').write_text(json.dumps(self.bindings))
        result = audit_project.audit_project(self.root, 'metadata/graph.json', 'metadata/bindings.json', 'brief.md')
        self.assertEqual(result['source_dependencies']['missing'][0]['path'], 'app/review.cjs')

    def test_semantic_review_candidates_keep_pending_judgment(self):
        self.graph['edges'].append({'from': 'CODE-CARDS', 'to': 'CODE-REVIEW', 'type': 'depends-on'})
        self.save()
        (self.root / 'brief.md').write_text('Cards are visible to every visitor.\n')
        (self.root / 'spec.md').write_text('Cards are visible only to signed-in members.\n')
        evidence = [{'file': name, 'line': 1, 'quote': (self.root / name).read_text().strip(),
                     'sha256': hashlib.sha256((self.root / name).read_bytes()).hexdigest()}
                    for name in ('brief.md', 'spec.md')]
        review = {'version': 1, 'reviewer': 'Codex reviewer', 'findings': [{'topic': 'card audience', 'scope': 'card list visibility', 'condition': 'opening the card list', 'rationale': 'The stated audiences appear incompatible.', 'evidence': evidence}]}
        (self.root / 'review.json').write_text(json.dumps(review))
        self.assertEqual(self.cli('reviewed', '--spec', 'spec.md', '--review', 'review.json'), 2)
        result = json.loads((self.root / 'reviewed/audit.json').read_text())
        self.assertEqual(result['brief_consistency']['findings'], [])
        self.assertEqual(result['brief_consistency']['review_findings'][0]['judgment'], 'pending')
        self.assertEqual(result['acceptance_claim'], 'not-established')
        self.assertIn('review.json', result['inputs'])
        self.assertIn('판정 대기', (self.root / 'reviewed/audit.md').read_text())
        (self.root / 'spec.md').write_text('Changed card policy.\n')
        self.assertEqual(self.cli('stale-review', '--spec', 'spec.md', '--review', 'review.json'), 2)
        self.assertFalse((self.root / 'stale-review').exists())

    def test_analyzed_source_digest_must_match_pinned_bytes(self):
        original = audit_project.audit_dependencies.audit
        def mismatched(*args):
            result = original(*args)
            result['scanned_hashes']['app/cards.cjs'] = '0' * 64
            return result
        with patch.object(audit_project.audit_dependencies, 'audit', side_effect=mismatched):
            with self.assertRaisesRegex(ValueError, 'Source bytes analyzed differ'):
                self.audit()

    def test_report_keeps_prose_review_concise_without_dropping_json(self):
        (self.root / 'brief.md').write_text('\n'.join('Unrecognized requirement number ' + str(i) + '.' for i in range(30)))
        result = self.audit()
        self.assertEqual(len(result['brief_consistency']['unsupported']), 30)
        markdown = audit_project.markdown(result)
        self.assertIn('나머지 미분석 구문 22건', markdown)
        self.assertLess(len(markdown.splitlines()), 50)


if __name__ == '__main__':
    unittest.main()
