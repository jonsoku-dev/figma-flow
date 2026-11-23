import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.graph_generated import ASSET_DIR, POLICY_DOC, TOKEN_CSS, check_generated, write_policy_doc
from tools.panel_artifacts import read_panel_artifact


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path('tools/maintenance-contract.json')


class GeneratedPanelTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temporary) / 'checkout'
        self.scratch = Path(temporary) / 'scratch'
        self.scratch.mkdir()
        self.enterContext(patch.object(tempfile, 'tempdir', str(self.scratch)))
        shutil.copytree(ROOT / 'panel-ui', self.root / 'panel-ui', ignore=shutil.ignore_patterns('node_modules'))
        shutil.copytree(ROOT / 'figma-bridge', self.root / 'figma-bridge')
        for relative in ('library', 'specs', 'vendor', 'panel-ui/node_modules'):
            (self.root / relative).symlink_to(ROOT / relative, target_is_directory=True)
        for relative in (Path('plugin.json'), CONTRACT, POLICY_DOC):
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, self.root / relative)
        self.contract = json.loads((self.root / CONTRACT).read_bytes())

    def test_clean_build_then_detects_drift_without_rewriting_checkout(self):
        self.assertEqual([], check_generated(self.root, self.contract))
        self.assertEqual([], list(self.scratch.iterdir()))
        missing = ASSET_DIR / 'panel-shell.css'
        stale = ASSET_DIR / 'panels.css'
        obsolete = ASSET_DIR / 'retired.js'
        obsolete_doc = POLICY_DOC.parent / 'retired.md'
        (self.root / missing).unlink()
        (self.root / TOKEN_CSS).unlink()
        modified = (stale, obsolete, POLICY_DOC, obsolete_doc)
        for relative in modified:
            (self.root / relative).write_bytes(b'edited')

        self.assertCountEqual(check_generated(self.root, self.contract), [
            f'Missing generated file {missing}.',
            f'Missing generated file {TOKEN_CSS}.',
            f'Unexpected generated file {obsolete}.',
            f'Unexpected generated file {obsolete_doc}.',
            f'Stale generated file {stale}; regenerate it from its source.',
            f'Stale generated file {POLICY_DOC}; regenerate it from its source.',
        ])
        self.assertFalse((self.root / missing).exists())
        self.assertFalse((self.root / TOKEN_CSS).exists())
        for relative in modified:
            self.assertEqual(b'edited', (self.root / relative).read_bytes())
        self.assertEqual([], list(self.scratch.iterdir()))

    def test_partial_build_failure_cleans_up_and_preserves_current_assets(self):
        entry = self.root / 'panel-ui/src' / self.contract['panelBoundaries']['entry']
        with entry.open('a', encoding='utf-8') as source:
            source.write('\nimport "missing-panel-generation-test-package";\n')
        before = (self.root / TOKEN_CSS).read_bytes()

        findings = check_generated(self.root, self.contract)
        self.assertEqual(1, len(findings), findings)
        self.assertIn('Panel asset regeneration failed', findings[0])
        self.assertIn('missing-panel-generation-test-package', findings[0])
        self.assertEqual(before, (self.root / TOKEN_CSS).read_bytes())
        self.assertEqual([], list(self.scratch.iterdir()))

    def test_successful_build_cannot_redefine_the_expected_inventory(self):
        missing = ASSET_DIR / 'panels.js'
        (self.root / missing).unlink()
        build = self.root / 'panel-ui/build.mjs'
        original = build.read_text()
        build.write_text(original + '\nawait (await import("node:fs/promises")).unlink(out + "/panels.js");\n')
        self.assertIn(f'Build did not produce a required panel artifact {missing}.', check_generated(self.root, self.contract))
        self.assertEqual([], list(self.scratch.iterdir()))

    def test_policy_projection_follows_boundary_owner(self):
        original = (self.root / POLICY_DOC).read_text(encoding='utf-8')
        policy = self.contract['panelBoundaries']
        owner = policy['networkOwner']
        policy['networkOwner'] = 'replacement.mjs'
        write_policy_doc(self.root, self.contract)
        current = (self.root / POLICY_DOC).read_text(encoding='utf-8')
        self.assertEqual(original.replace(f'`{owner}` owns network', '`replacement.mjs` owns network'), current)

    def test_authorized_policy_expansion_passes_after_document_regeneration(self):
        policy = self.contract['panelBoundaries']
        policy['blockedPackages'].append('@fixture/direct-transport')
        (self.root / CONTRACT).write_text(json.dumps(self.contract))
        self.assertIn(f'Stale generated file {POLICY_DOC}; regenerate it from its source.',
                      check_generated(self.root, self.contract))
        write_policy_doc(self.root, self.contract)
        self.assertIn('@fixture/direct-transport', (self.root / POLICY_DOC).read_text())
        self.assertEqual([], check_generated(self.root, self.contract))
        self.assertEqual([], list(self.scratch.iterdir()))

    def test_script_rename_propagates_to_bundle_css_legal_comments_and_runtime_reader(self):
        self.contract['panelArtifacts']['script'] = 'design-panel.js'
        (self.root / CONTRACT).write_text(json.dumps(self.contract))
        stale = ('panels.js', 'panels.css', 'panels.js.LEGAL.txt')
        before = check_generated(self.root, self.contract)
        for name in stale:
            self.assertIn(f'Unexpected generated file {ASSET_DIR / name}.', before)
        subprocess.run(['node', 'panel-ui/build.mjs'], cwd=self.root, check=True, capture_output=True)
        for name in stale:
            (self.root / ASSET_DIR / name).unlink()
        write_policy_doc(self.root, self.contract)
        self.assertEqual([], check_generated(self.root, self.contract))
        for role, name in [('script', 'design-panel.js'), ('bundleStyle', 'design-panel.css')]:
            self.assertEqual(read_panel_artifact(self.root, role), (self.root / ASSET_DIR / name).read_text())


if __name__ == '__main__':
    unittest.main()
