"""0.17.6: a selection reached through a project manifest's relative path is still the same record."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_directions  # noqa: E402


class SelectionPathTests(unittest.TestCase):
    def test_dotdot_path_to_the_same_record_is_accepted_and_a_copy_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            record = root / 'review' / 'selection.json'
            record.parent.mkdir()
            (root / 'checks' / '001').mkdir(parents=True)
            record.write_text(json.dumps({'self_path': str(record)}))
            copy = root / 'copy.json'
            copy.write_text(record.read_text())
            seen = []
            def stop(*_args, **_kwargs):
                seen.append('passed-path-check')
                raise ValueError('stop after the path check')
            with patch.object(design_directions, 'assert_workflow_sync'), patch.object(design_directions, 'validate_selection', side_effect=stop, create=True):
                via_manifest = root / 'checks' / '001' / '..' / '..' / 'review' / 'selection.json'
                for path in (via_manifest, copy):
                    with self.assertRaises(ValueError) as caught:
                        design_directions.require_selected(path)
                    if path == copy:
                        self.assertIn('Archived/copied', str(caught.exception))
                    else:
                        self.assertNotIn('Archived/copied', str(caught.exception))


if __name__ == '__main__':
    unittest.main()


class VariantSetRadiusTests(unittest.TestCase):
    def test_importers_clear_figma_default_variant_set_radius(self):
        # A live run showed Figma's default 5px radius on new variant sets surfacing as an unbound rendered use.
        for name, var in (('figma-bridge/code.js', 'set'), ('figma-bridge/semantic_components.js', 'nativeSet')):
            source = (ROOT / name).read_text()
            created = source.index('combineAsVariants(', source.index('combineAsVariants(') + 1) if source.count('combineAsVariants(') > 1 else source.index('combineAsVariants(')
            self.assertIn(f"if ('cornerRadius' in {var}) {var}.cornerRadius = 0;", source[created:created + 600], name)
