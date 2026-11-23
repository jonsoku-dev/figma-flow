from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.graph_impact import changed_paths, intent_to_add_paths, panel_base_snapshot, read_git, read_git_blobs


def git(root, *args, env=None, check=True):
    return subprocess.run(['git', '-C', str(root), *args], env=env, capture_output=True, check=check)


def initialize(root, name, content):
    git(root, 'init', '-q')
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    git(root, 'add', name)
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')


class DevelopmentGitEvidenceTests(unittest.TestCase):
    def test_intent_to_add_has_no_staged_blob_even_for_a_base_file_and_a_missing_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, 'reintroduced.txt', b'base bytes')
            git(root, 'rm', '--cached', 'reintroduced.txt')
            existing = 'candidate\twith escaped path.txt'
            (root / existing).write_bytes(b'working bytes')
            (root / 'missing.txt').write_bytes(b'removed later')
            (root / 'empty.txt').write_bytes(b'')
            git(root, 'add', 'empty.txt')
            git(root, 'add', '-N', existing, 'missing.txt', 'reintroduced.txt')
            (root / 'missing.txt').unlink()
            (root / 'reintroduced.txt').write_bytes(b'reintroduced bytes')
            index_before = (root / '.git/index').read_bytes()

            self.assertEqual(intent_to_add_paths(root), {existing, 'missing.txt', 'reintroduced.txt'})
            evidence = changed_paths(root, 'HEAD')
            self.assertEqual((root / '.git/index').read_bytes(), index_before)

        self.assertEqual(evidence[existing]['kind'], 'added')
        self.assertEqual(evidence[existing]['after']['sha256'], sha256(b'working bytes').hexdigest())
        self.assertTrue(evidence[existing]['intentToAdd'])
        self.assertIsNone(evidence[existing]['staged'])
        self.assertEqual(evidence['missing.txt'],
                         {'kind': 'intent-to-add', 'before': None, 'after': None, 'staged': None, 'intentToAdd': True})
        self.assertTrue(evidence['reintroduced.txt']['intentToAdd'])
        self.assertEqual(evidence['reintroduced.txt']['before']['sha256'], sha256(b'base bytes').hexdigest())
        self.assertIsNone(evidence['reintroduced.txt']['staged'])
        self.assertNotIn('intentToAdd', evidence['empty.txt'])
        self.assertEqual(evidence['empty.txt']['staged']['sha256'], sha256(b'').hexdigest())

    def test_partial_clone_local_fetchable_objects_stay_absent_until_explicit_git_read(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / 'origin'
            origin.mkdir()
            path = 'panel-ui/src/app.js'
            payload = b'export const localOnlyFixture = true;\n'
            initialize(origin, path, payload)
            git(origin, 'config', 'uploadpack.allowFilter', 'true')
            git(origin, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
            partial = root / 'partial'
            git(root, '-c', 'protocol.file.allow=always', 'clone', '-q', '--no-checkout', '--filter=blob:none',
                origin.as_uri(), str(partial))
            oid = git(origin, 'rev-parse', 'HEAD:' + path).stdout.decode().strip()
            pack = partial / '.git/objects/pack'
            pack_before = {name.name for name in pack.iterdir()}
            offline = {**os.environ, 'GIT_ALLOW_PROTOCOL': '', 'GIT_NO_LAZY_FETCH': '1'}
            self.assertNotEqual(git(partial, 'cat-file', '-e', oid, env=offline, check=False).returncode, 0)
            trace = root / 'trace.jsonl'

            with patch.dict(os.environ, GIT_ALLOW_PROTOCOL='file', GIT_NO_LAZY_FETCH='0', GIT_TRACE2_EVENT=str(trace)):
                with self.assertRaises(subprocess.CalledProcessError):
                    read_git(partial, 'show', 'HEAD:' + path)
                with self.assertRaisesRegex(ValueError, 'Local Git blob .* is unavailable'):
                    read_git_blobs(partial, [oid])
                with self.assertRaisesRegex(ValueError, 'Local Git blob .* is unavailable'):
                    changed_paths(partial, 'HEAD')
                with self.assertRaisesRegex(ValueError, 'Local Git blob .* is unavailable'):
                    with panel_base_snapshot(partial, 'HEAD', [path]):
                        self.fail('Historical staging accepted a missing blob')

            self.assertEqual({name.name for name in pack.iterdir()}, pack_before)
            self.assertNotEqual(git(partial, 'cat-file', '-e', oid, env=offline, check=False).returncode, 0)
            events = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertTrue(events)
            self.assertFalse(any('fetch' in event.get('argv', ()) for event in events))
            online = {**os.environ, 'GIT_ALLOW_PROTOCOL': 'file', 'GIT_NO_LAZY_FETCH': '0'}
            self.assertEqual(git(partial, 'show', 'HEAD:' + path, env=online).stdout, payload)
            self.assertEqual(read_git_blobs(partial, [oid, oid]), {oid: payload})


if __name__ == '__main__':
    unittest.main()
