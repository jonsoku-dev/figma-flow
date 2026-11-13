from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from tools import replay_optional_tests as replay


class ReplayOptionalTests(unittest.TestCase):
    def test_only_zero_skip_python_and_node_results_pass(self):
        python_pass = replay.python_counts('Ran 1 test in 0.1s\n\nOK\n')
        python_skip = replay.python_counts('Ran 1 test in 0.1s\n\nOK (skipped=1)\n')
        node_pass = replay.tap_counts('# tests 16\n# pass 16\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n')
        node_skip = replay.tap_counts('# tests 16\n# pass 15\n# fail 0\n# cancelled 0\n# skipped 1\n# todo 0\n')
        self.assertEqual(replay.result_record('python', SimpleNamespace(returncode=0, stdout='', stderr='Ran 1 test in 0.1s\n\nOK\n'), python_pass)['status'], 'passed')
        self.assertEqual(replay.result_record('python', SimpleNamespace(returncode=0, stdout='', stderr=''), python_skip)['status'], 'skipped')
        self.assertEqual(replay.result_record('node', SimpleNamespace(returncode=0, stdout='', stderr=''), node_pass)['status'], 'passed')
        self.assertEqual(replay.result_record('node', SimpleNamespace(returncode=0, stdout='', stderr=''), node_skip)['status'], 'skipped')

    def test_parallel_checkouts_are_isolated_and_fixture_links_are_read_only_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shadow, moss = root / 'shadow', root / 'moss'
            shadow.mkdir(); moss.mkdir()
            (shadow / 'native-layout.json').write_text('{}')
            (moss / 'native-layout.json').write_text('{}')

            def checkout():
                with replay.isolated_checkout(shadow.resolve(), moss.resolve()) as (project, temp):
                    shadow_link = temp / 'shadow-troupe'
                    moss_link = temp / 'moss-choir'
                    self.assertTrue(shadow_link.is_symlink())
                    self.assertTrue(moss_link.is_symlink())
                    self.assertEqual(shadow_link.resolve(), shadow.resolve())
                    self.assertEqual(moss_link.resolve(), moss.resolve())
                    return str(temp.resolve())

            with ThreadPoolExecutor(max_workers=2) as pool:
                roots = list(pool.map(lambda _: checkout(), range(2)))
            self.assertEqual(len(set(roots)), 2)
            self.assertEqual((shadow / 'native-layout.json').read_text(), '{}')
            self.assertEqual((moss / 'native-layout.json').read_text(), '{}')

    def test_file_inputs_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'original.json'; original.write_text('{}')
            link = root / 'link.json'; link.symlink_to(original)
            with self.assertRaises(ValueError): replay.file_input(link, 'fixture')


if __name__ == '__main__':
    unittest.main()
