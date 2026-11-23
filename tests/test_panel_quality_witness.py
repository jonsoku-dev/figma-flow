from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PanelQualityWitnessTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='figma-flow-lint-proof-')))
        self.source = self.workspace / 'src'
        self.source.mkdir()
        self.bin = Path(os.environ.get('FIGMA_FLOW_PANEL_DEPENDENCIES') or ROOT / 'panel-ui/node_modules') / '.bin'

    def run_check(self, tool, *arguments):
        return subprocess.run([str(self.bin / tool), *arguments], cwd=self.workspace,
                              capture_output=True, text=True, timeout=30)

    def test_biome_panel_rules_accept_valid_inputs_and_reject_css_and_json_defects(self):
        shutil.copyfile(ROOT / 'panel-ui/biome.json', self.workspace / 'biome.json')
        styles = self.source / 'styles'
        styles.mkdir()
        css = styles / 'fixture.css'
        data = self.workspace / 'fixture.json'
        css.write_text('a { color: red; }\n')
        data.write_text('{"visible": true}\n')
        valid = self.run_check('biome', 'lint', '.')
        self.assertEqual(0, valid.returncode, valid.stdout + valid.stderr)

        css.write_text('a { nonexistent-property: 1; }\n')
        duplicate = '{"visible": true, "visible": false}\n'
        data.write_text(duplicate)
        invalid = self.run_check('biome', 'lint', '.')
        self.assertEqual(1, invalid.returncode, invalid.stdout + invalid.stderr)
        self.assertIn('lint/correctness/noUnknownProperty', invalid.stderr)
        self.assertIn('lint/suspicious/noDuplicateObjectKeys', invalid.stderr)
        self.assertEqual(duplicate, data.read_text())

    def test_oxlint_panel_rules_accept_valid_hooks_and_reject_conditional_hooks(self):
        shutil.copyfile(ROOT / 'panel-ui/.oxlintrc.json', self.workspace / '.oxlintrc.json')
        view = self.source / 'Fixture.jsx'
        view.write_text("import { useState } from 'react';\nexport function Fixture() { useState(0); return null; }\n")
        options = ('--max-warnings', '0', '--format', 'json', '.')
        valid = self.run_check('oxlint', *options)
        self.assertEqual(0, valid.returncode, valid.stdout + valid.stderr)
        self.assertEqual(1, json.loads(valid.stdout)['number_of_files'])

        broken = ("import { useState } from 'react';\n"
                  "export function Fixture({ ready }) { if (ready) useState(0); return null; }\n")
        view.write_text(broken)
        invalid = self.run_check('oxlint', *options)
        self.assertEqual(1, invalid.returncode, invalid.stdout + invalid.stderr)
        diagnostics = json.loads(invalid.stdout)['diagnostics']
        self.assertTrue(any('rules-of-hooks' in item['code'] for item in diagnostics), diagnostics)
        self.assertEqual(broken, view.read_text())


if __name__ == '__main__':
    unittest.main()
