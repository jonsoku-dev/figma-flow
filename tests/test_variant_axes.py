import json
import subprocess
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('design_system', ROOT / 'tools/design_system.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeclaredVariantAxisTests(unittest.TestCase):
    def test_real_design_system_axes_do_not_grow_combinations(self):
        data = json.loads((ROOT / 'examples/regression-program/design-system/design.json').read_text())
        axes = json.loads((ROOT / 'examples/regression-program/design-system/axes.json').read_text())['components']
        data['variant_axes'] = axes
        design = module.compile_design(data)
        button = design['components']['button']
        self.assertEqual(button.get('variant_axes'), axes['button'], 'declared axes must be preserved without new combinations')
        self.assertEqual(set(button['variants']), {'sm', 'md', 'disabled', 'loading', 'error'})
        self.assertNotIn('usage', button)
        field = design['components']['field']
        self.assertEqual(field['variant_axes'], {'state': ['disabled', 'error']})
        self.assertIn('default', field['variants'])
        self.assertNotIn('default', field['variant_axes']['state'])
        self.assertNotIn('light', json.dumps(design['components']))
        result = subprocess.run(['node', str(ROOT / 'tests/variant_axes_oracle.cjs')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
