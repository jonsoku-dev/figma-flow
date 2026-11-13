"""Frozen external contract for creating a reviewed web import plan from the normal CLI."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WebDesignEntry(unittest.TestCase):
    def test_public_web_design_entry(self):
        help_page = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/native_edit.py'), 'web-design', '--help'],
                                   capture_output=True, text=True)
        self.assertIn('--graph', help_page.stdout, 'public web-design graph entry is missing')
        self.assertEqual(help_page.returncode, 0, help_page.stderr)


if __name__ == '__main__':
    unittest.main()
