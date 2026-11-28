"""Hold one real atomic replacement while separate CLI processes update local files."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
CONTROL = [sys.executable, '-B', str(TOOLS / 'figma_control.py'), 'metrics']


def register(path):
    sys.path.insert(0, str(TOOLS))
    import workspace_registry
    return 0 if workspace_registry.register_workspace(path, plugin_id='123') else 1


def run_held(ready, release, target, command):
    original = os.replace

    def pause(source, dest, **kwargs):
        if Path(dest) == Path(target):
            Path(ready).touch()
            wait_for(Path(release))
        return original(source, dest, **kwargs)

    with patch.object(os, 'replace', pause):
        if command[0] == 'register':
            return register(command[1])
        sys.path.insert(0, str(TOOLS))
        import figma_control
        return figma_control.main(['metrics', *command])


def wait_for(path):
    deadline = time.monotonic() + 20
    while not path.exists():
        if time.monotonic() > deadline:
            raise TimeoutError(path.name)
        time.sleep(0.01)


@unittest.skipUnless(os.name == 'posix', 'POSIX workspace integration')
class TransactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.ws = self.root / 'workspace'
        self.ws.mkdir(mode=0o700)
        self.xdg = self.root / 'config'
        self.env = {**os.environ, 'XDG_CONFIG_HOME': str(self.xdg)}
        self.local = ['--workspace', str(self.ws)]

    @contextlib.contextmanager
    def held(self, target, *args):
        ready, release = self.root / 'ready', self.root / 'release'
        with subprocess.Popen([sys.executable, '-B', __file__, 'held', str(ready),
                               str(release), str(target), *args], stdout=subprocess.PIPE, env=self.env) as p:
            try:
                wait_for(ready)
                yield
            finally:
                release.touch()
                p.communicate(timeout=20)
            self.assertEqual(p.returncode, 0)

    def overlap(self, target, first, second, independent=None):
        with self.held(target, *first):
            p = subprocess.Popen(second, env=self.env, stdout=subprocess.PIPE)
            try:
                if independent:
                    subprocess.run(independent, env=self.env, check=True, capture_output=True, timeout=8)
                # An unlocked second writer finishes here. A serialized writer waits for release.
                try:
                    p.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    pass
            finally:
                (self.root / 'release').touch()
                p.communicate(timeout=20)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        return json.loads(target.read_bytes())

    def test_concurrent_source_changes(self):
        target = self.ws / 'metrics.json'
        args = ['set-source', *self.local, '--enabled', 'true', '--source']
        result = self.overlap(target, [*args, 'workspace'], [*CONTROL, *args, 'quality'],
                              [*CONTROL, 'enable', '--global'])
        self.assertFalse(result['enabled'])
        self.assertTrue(result['sources']['workspace'] and result['sources']['quality'],
                        'two successful commands must retain both sources')

    def test_forced_global_init_serializes_with_updates(self):
        target = self.xdg / 'figma-flow' / 'metrics.json'
        result = self.overlap(target, ['enable', '--global'], [*CONTROL, 'init', '--global', '--force'],
                              [*CONTROL, 'enable', *self.local])
        self.assertFalse(result['enabled'], 'force init must observe the committed predecessor')

    def test_failed_update_releases_lock_and_preserves_file(self):
        subprocess.run([*CONTROL, 'init', *self.local], env=self.env, check=True, capture_output=True)
        target = self.ws / 'metrics.json'
        before = target.read_bytes()
        sys.path.insert(0, str(TOOLS))
        import figma_control
        with patch.dict(os.environ, self.env), contextlib.redirect_stderr(io.StringIO()):
            code = figma_control.main(['metrics', 'remove-sink', *self.local, '--id', 'absent'])
        self.assertEqual(code, 2)
        self.assertEqual(target.read_bytes(), before)
        subprocess.run([*CONTROL, 'enable', *self.local], env=self.env, check=True,
                       capture_output=True, timeout=8)
        self.assertTrue(json.loads(target.read_bytes())['enabled'])

    def test_two_successful_registrations_survive(self):
        target = self.xdg / 'figma-flow' / 'workspaces.json'
        other = self.root / 'other'
        other.mkdir(mode=0o700)
        result = self.overlap(target, ['register', str(self.ws)],
                              [sys.executable, '-B', __file__, 'register', str(other)])
        self.assertEqual({row['path'] for row in result['workspaces']},
                         {str(self.ws.resolve()), str(other.resolve())}, 'both registrations must survive')


if __name__ == '__main__':
    if sys.argv[1:2] == ['held']:
        sys.exit(run_held(*sys.argv[2:5], sys.argv[5:]))
    if sys.argv[1:2] == ['register']:
        sys.exit(register(sys.argv[2]))
    unittest.main()
