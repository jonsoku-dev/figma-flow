"""Regression for graph-scoped native receipts on multi-screen page imports."""
from pathlib import Path
import subprocess
import sys
import unittest


class RouteReadbackTest(unittest.TestCase):
    def test_public_scope_option(self):
        tool = Path(__file__).resolve().parents[1] / 'tools/native_edit.py'
        run = subprocess.run([sys.executable, '-B', str(tool), 'web-design', '--help'],
                             text=True, capture_output=True, check=True)
        self.assertIn('--readback-scope', run.stdout, 'owned screen discovery is unavailable')
