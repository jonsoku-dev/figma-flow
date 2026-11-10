"""The skill preflight is local, read-only, and bound to the packaged bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import skill_dependencies


class SkillDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='技能 bundle ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'Figma Flow 插件'
        (self.root / 'tools').mkdir(parents=True)
        shutil.copy2(ROOT / 'tools/skill_dependencies.py', self.root / 'tools/skill_dependencies.py')
        shutil.copytree(ROOT / 'vendor/skills', self.root / 'vendor/skills')
        spec = importlib.util.spec_from_file_location('isolated_skill_dependencies', self.root / 'tools/skill_dependencies.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def manifest(self):
        return json.loads((self.root / 'vendor/skills/manifest.json').read_text())

    def save_manifest(self, value):
        (self.root / 'vendor/skills/manifest.json').write_text(json.dumps(value))

    def test_plugin_paths_and_cli_work_after_relocation_without_home_or_writes(self):
        before = {path.relative_to(self.root): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in self.root.rglob('*') if path.is_file()}
        with patch.object(Path, 'home', side_effect=AssertionError('global skill lookup forbidden')):
            resolved = self.module.resolve_skill('impeccable')
            self.assertEqual(resolved, (self.root / 'vendor/skills/impeccable/SKILL.md').resolve())
            result = subprocess.run([sys.executable, str(self.root / 'tools/skill_dependencies.py'), '--check'],
                                    cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ready')
        after = {path.relative_to(self.root): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_missing_or_tampered_pinned_files_block(self):
        for identity, relative in [('impeccable', 'reference/adapt.md'), ('impeccable', 'LICENSE'),
                                   ('impeccable', 'SKILL.md')]:
            with self.subTest(identity=identity, relative=relative):
                package = self.root / 'vendor/skills' / identity / relative
                original = package.read_bytes()
                package.unlink()
                with self.assertRaises(ValueError):
                    self.module.verify_bundle()
                package.write_bytes(original + b' tampered')
                with self.assertRaises(ValueError):
                    self.module.verify_bundle()
                package.write_bytes(original)

    def test_unsafe_paths_and_symlink_escape_block(self):
        manifest = self.manifest()
        digest = manifest['skills']['impeccable']['files'].pop('reference/adapt.md')
        manifest['skills']['impeccable']['files']['../outside.md'] = digest
        self.save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, 'safe relative'):
            self.module.verify_bundle()
        manifest = json.loads((ROOT / 'vendor/skills/manifest.json').read_text())
        self.save_manifest(manifest)
        path = self.root / 'vendor/skills/impeccable/reference/adapt.md'
        raw = path.read_bytes()
        outside = Path(self.temp.name) / 'outside.md'
        outside.write_bytes(raw)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.module.verify_bundle()

    def test_missing_bundle_blocks_without_global_fallback_and_unknown_ids_fail(self):
        (self.root / 'vendor/skills/impeccable/SKILL.md').unlink()
        with patch.object(Path, 'home', side_effect=AssertionError('global skill lookup forbidden')):
            with self.assertRaises(ValueError):
                self.module.resolve_skill('impeccable')
            with self.assertRaisesRegex(ValueError, 'unknown managed skill'):
                skill_dependencies.resolve_skill('taste')

    def test_manifest_parent_symlink_is_rejected(self):
        vendor = self.root / 'vendor'
        outside = Path(self.temp.name) / 'outside-vendor'
        vendor.rename(outside)
        vendor.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.module.verify_bundle()

    def test_unlisted_package_files_are_rejected(self):
        (self.root / 'vendor/skills/impeccable/untracked.md').write_text('not part of the reviewed source')
        with self.assertRaisesRegex(ValueError, 'complete manifest'):
            self.module.verify_bundle()


if __name__ == '__main__':
    unittest.main()
