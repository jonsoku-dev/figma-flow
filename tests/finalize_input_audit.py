"""Producer-to-summary privacy and caller-owned browser observation contract."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import input_effect


class InputAuditBoundary(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for folder in ['css', 'fonts', 'photos']:
            (root / folder).mkdir()
        (root / 'index.html').write_text('<link rel="stylesheet" href="css/a.css"><link rel="stylesheet" href="css/b.css"><p>가</p>')
        (root / 'css/a.css').write_text('@font-face{font-family:Body;src:url(../fonts/body.woff2)}p{background:url(../photos/card.png)}')
        (root / 'css/b.css').write_text('@font-face{font-family:Other;src:url(../fonts/./body.woff2)}')
        (root / 'fonts/body.woff2').write_bytes(b'font-fixture')
        (root / 'photos/card.png').write_bytes(b'image-fixture')
        return root

    def test_no_browser_process_or_undeclared_browser_dependency(self):
        root = self.fixture()
        with patch('subprocess.Popen', side_effect=AssertionError('input comparison must not launch a process')):
            try:
                result = input_effect.contrast_css_browser_loading(root, requested_paths=[])
            except TypeError as error:
                self.fail('input comparison must accept a supplied browser observation: ' + str(error))
        self.assertEqual(result['browser']['requested'], [])

    def test_producer_keeps_asset_types_and_all_ingress_sources(self):
        root = self.fixture()
        channel = input_effect.html_channel(root / 'index.html', root)
        record = {'schema': input_effect.RESULT_SCHEMA, 'channels': {'html': channel}}
        rows = input_effect.summarize_input_record(record)['summary']
        font = next(row for row in rows if row['ref'].endswith('body.woff2'))
        self.assertEqual(sum(row['kind'] == 'font' for row in rows), 1, 'one local file must keep all equivalent references together')
        image = next(row for row in rows if row['ref'].endswith('card.png'))
        self.assertEqual(font['kind'], 'font', 'real producer rows must retain font kind')
        self.assertEqual(image['kind'], 'image')
        self.assertIn('css/a.css', font['source'], 'all CSS ingress must reach the summary')
        self.assertIn('css/b.css', font['source'])

    def test_url_userinfo_is_removed_from_summary_and_audit(self):
        value = 'https://alice:fixture-secret@example.test/font.woff2?token=fixture-query#private'
        record = {'schema': input_effect.RESULT_SCHEMA, 'channels': {'html': {'assets': [
            {'ref': value, 'source': value, 'kind': 'font', 'status': 'external-unverified'},
        ]}}}
        serialized = json.dumps(input_effect.summarize_input_record(record)['summary'])
        self.assertNotIn('fixture-secret', serialized, 'URL userinfo must not reach public input summaries')
        script = "const a=require('./figma-bridge/audit_log.js');process.stdout.write(JSON.stringify(a.renderAuditExport(JSON.parse(process.argv[1]))));"
        run = subprocess.run(['node', '-e', script, json.dumps({'input_summary': record['channels']['html']['assets']})], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn('fixture-secret', run.stdout, 'diagnostic export must redact URL userinfo independently')
        self.assertNotIn('fixture-query', run.stdout)

    def test_browser_comparison_requires_explicit_observation(self):
        root = self.fixture()
        observed = ['css/a.css', 'fonts/body.woff2', 'photos/card.png']
        try:
            result = input_effect.contrast_css_browser_loading(root, requested_paths=observed)
        except TypeError as error:
            self.fail('browser contrast must accept an explicit approved observation: ' + str(error))
        self.assertEqual(result['browser']['requested'], sorted(observed))
        self.assertEqual(result['browser']['source'], 'provided-observation')
        with self.assertRaises(ValueError):
            input_effect.contrast_css_browser_loading(root)
        with self.assertRaises(ValueError):
            input_effect.contrast_css_browser_loading(root, requested_paths=['../../outside'])

    def test_shipped_react_graph_has_diagnostic_export(self):
        source = (ROOT / 'panel-ui/src/GraphPanel.jsx').read_text()
        self.assertIn('DiagnosticExport', source, 'shipped React graph panel must expose diagnostic export')


if __name__ == '__main__':
    unittest.main()
