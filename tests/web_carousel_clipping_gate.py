"""Run the frozen public capture regression under the patch knowledge assertion gate."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
result = subprocess.run(['node', '--test', 'tests/test_web_design_capture_clipping.cjs'],
                        cwd=root, capture_output=True, text=True)
if result.returncode and 'false !== true' in result.stdout:
    raise AssertionError('Browser scroll rail leaked an offscreen card')
result.check_returncode()
