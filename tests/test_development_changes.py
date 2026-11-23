from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / 'tools/development_changes.py'
sys.path.insert(0, str(ROOT / 'tools'))
import development_changes as planner


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True).stdout


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return path


def authorities():
    return {
        'schema': 'figma-flow-major-authority-v1',
        'nodes': [
            {'id': 'tools', 'type': 'surface', 'roots': ['tools'], 'coverage': 'review'},
            {'id': 'guides', 'type': 'surface', 'roots': ['docs'], 'coverage': 'review'},
            {'id': 'records', 'type': 'surface', 'roots': ['docs/archive'], 'coverage': 'record'},
            {'id': 'tests', 'type': 'surface', 'roots': ['tests'], 'coverage': 'test-oracle'},
            {'id': 'panel', 'type': 'surface', 'roots': ['panel-ui'], 'coverage': 'review'},
            {'id': 'release', 'type': 'surface', 'roots': ['release'], 'coverage': 'gate-data'},
            {'id': 'policy', 'type': 'authority', 'source': 'docs/policy.json'},
            {'id': 'check-tool', 'type': 'check', 'source': 'tests/test_tool.py'},
        ],
        'edges': [
            {'from': 'tools', 'to': 'policy', 'type': 'owned-by'},
            {'from': 'tools', 'to': 'check-tool', 'type': 'checked-by'},
        ],
    }


def initialize(root, graph, policy=None):
    git(root, '-c', 'init.defaultBranch=main', 'init', '-q')
    write(root, 'release/authority.json', graph)
    write(root, 'panel-ui/package.json', {'devDependencies': {}})
    write(root, 'tools/mixed.txt', b'base\n')
    write(root, 'tools/relocated.txt', b'original contents\0')
    write(root, 'docs/policy.json', {'mode': 'baseline'} if policy is None else policy)
    write(root, 'tests/test_tool.py',
          b'from pathlib import Path\nPath(__file__).with_name("check-ran.txt").touch()\n')
    commit_fixture(root)


def commit_fixture(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')


def report(root):
    result = subprocess.run([sys.executable, '-B', str(PLANNER), '--repo', str(root), '--base', 'HEAD',
                             '--inventory', '--json'], capture_output=True, text=True)
    return result, json.loads(result.stdout) if result.stdout else {}


def add_witness(root):
    test = 'tests/historical.py'
    body = b'def test_feature():\n    assert True\n'
    source = write(root, test, body)
    witness = 'release/reviews/evidence/tools/example.json'
    review = 'release/reviews/tools.json'
    covered = 'tools/mixed.txt'
    authority = 'docs/policy.json#/mode'
    fingerprint = 'a' * 64
    receipt = write(root, witness, {'surfaceFingerprint': fingerprint, 'status': 'passed', 'checks': [{
        'test': test, 'case': 'test_feature', 'testSha256': sha256(source.read_bytes()).hexdigest(),
        'covers': [covered], 'authority': authority, 'assertion': 'Check the feature contract', 'observed': True,
    }]})
    write(root, review, {'schema': 'figma-flow-major-review-v1', 'surface': 'tools', 'fingerprint': fingerprint,
                        'openFindings': [], 'bindings': [{'files': [covered], 'authority': authority,
                        'witnesses': [{'path': witness, 'sha256': sha256(receipt.read_bytes()).hexdigest()}]}]})
    commit_fixture(root)
    return test, witness, covered


class DevelopmentChangesTests(unittest.TestCase):
    def test_deleted_authority_and_check_are_review_required_even_with_an_owner(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            (root / 'docs/policy.json').unlink()
            (root / 'tests/test_tool.py').unlink()
            result, plan = report(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual('review-required', plan['status'])
            self.assertEqual([], plan['unmapped'])
            self.assertEqual({('docs/policy.json', 'missing-authority-source'), ('tests/test_tool.py', 'missing-check-source')},
                             {(row['path'], row['rule']) for row in plan['findings']['working']})

    def test_test_change_and_removal_reach_covered_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            test, _, covered = add_witness(root)
            for body in (b'def test_feature():\n    assert False\n', None):
                with self.subTest(removed=body is None):
                    if body is None:
                        (root / test).unlink()
                    else:
                        write(root, test, body)
                    result, plan = report(root)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    routes = plan['changes'][test]['witnessDependents']
                    self.assertEqual('historical-candidates', routes['base'][0]['status'])
                    self.assertEqual('needs-review', routes['working'][0]['status'])
                    self.assertEqual([covered], routes['working'][0]['coveredPaths'])
                    self.assertIn(test, plan['surfaces']['working']['tools']['reasons'])
                    self.assertNotIn(covered, plan['changes'])

    def test_corrupted_evidence_reports_previous_dependents_and_exits_nonzero(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            test, witness, covered = add_witness(root)
            write(root, witness, b'{}')
            write(root, test, b'changed test\n')
            write(root, covered, b'changed implementation\n')
            result, plan = report(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual('needs-review', plan['changes'][covered]['revisions']['working']['witnesses']['status'])
            row = plan['changes'][test]['witnessDependents']['working'][0]
            self.assertEqual('prior-witness', row['basis'])
            self.assertEqual('index', row['basisRevision'])
            self.assertEqual([covered], row['coveredPaths'])
            self.assertEqual('needs-review', row['status'])

    def test_working_only_test_cannot_appear_as_earlier_revision_witness(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            _, witness, covered = add_witness(root)
            expected = json.loads((root / witness).read_bytes())
            write(root, witness, b'{}')
            git(root, 'add', witness)
            new_test = 'tests/new_test.py'
            body = b'def test_feature():\n    assert True\n'
            write(root, new_test, body)
            expected['checks'][0].update(test=new_test, testSha256=sha256(body).hexdigest())
            receipt = write(root, witness, expected)
            review = 'release/reviews/tools.json'
            declaration = json.loads((root / review).read_bytes())
            declaration['bindings'][0]['witnesses'][0]['sha256'] = sha256(receipt.read_bytes()).hexdigest()
            write(root, review, declaration)
            result, plan = report(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            routes = plan['changes'][new_test]['witnessDependents']
            self.assertEqual(['working'], list(routes))
            self.assertEqual([covered], routes['working'][0]['coveredPaths'])

    def test_human_output_lists_all_three_check_revisions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = authorities()
            initialize(root, graph)
            write(root, 'tests/staged.py', b'# staged\n')
            graph['nodes'][-1]['source'] = 'tests/staged.py'
            write(root, 'release/authority.json', graph)
            git(root, 'add', 'release/authority.json', 'tests/staged.py')
            write(root, 'tests/working.py', b'# working\n')
            graph['nodes'][-1]['source'] = 'tests/working.py'
            write(root, 'release/authority.json', graph)
            result = subprocess.run([sys.executable, '-B', str(PLANNER), '--repo', str(root)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for rev, path in [('base', 'tests/test_tool.py'), ('index', 'tests/staged.py'), ('working', 'tests/working.py')]:
                self.assertIn(f'{rev} tools: {path} (surface-declaration)', result.stdout)

    def test_intent_placeholder_is_not_a_staged_revision(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            write(root, 'tools/intent.txt', b'future change\n')
            git(root, 'add', '-N', 'tools/intent.txt')
            result, plan = report(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            row = plan['changes']['tools/intent.txt']
            self.assertTrue(row['intentToAdd'])
            self.assertIsNone(row['staged'])
            self.assertEqual(['working'], list(row['revisions']))

    def test_visibility_flags_changing_during_analysis_require_a_fresh_read(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            original = planner.panel_tools

            def mask_during(root, run_tools):
                git(root, 'update-index', '--assume-unchanged', 'tools/mixed.txt')
                return original(root, run_tools)

            with patch.object(planner, 'panel_tools', side_effect=mask_during):
                with self.assertRaisesRegex(ValueError, 'drifted'):
                    planner.analyze(root, 'HEAD')

    def test_transient_authority_edit_cannot_pass_when_git_state_recovers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = authorities()
            initialize(root, graph)
            original = planner.working_bytes
            edited = False

            def transient_read(root, name):
                nonlocal edited
                snapshot = original(root, name)
                if name == 'release/authority.json' and not edited:
                    edited = True
                    graph['nodes'][1]['roots'].append('tools/mixed.txt')
                    path = write(root, name, graph)
                    changing = original(root, name)
                    path.write_bytes(snapshot)
                    return changing
                return snapshot

            with patch.object(planner, 'working_bytes', side_effect=transient_read):
                with self.assertRaisesRegex(ValueError, 'Working evidence drifted.*release/authority.json'):
                    planner.analyze(root, 'HEAD')

    def test_git_visible_nested_repository_is_reported_without_traversal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            embedded = root / 'tools/embedded'
            embedded.mkdir()
            initialize(embedded, authorities())
            result, plan = report(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(['tools/embedded'], plan['notInspected']['uninspectedDirectories'])
            self.assertEqual({}, plan['changes'])

    def test_tool_configuration_and_installation_are_separate_from_execution(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            write(root, 'panel-ui/package.json', {
                'devDependencies': {'@biomejs/biome': '1.0.0', 'oxlint': '1.0.0'},
                'scripts': {'postinstall': 'touch executed-during-discovery'},
            })
            write(root, 'panel-ui/biome.json', {})
            write(root, 'panel-ui/.oxlintrc.json', {})
            write(root, 'panel-ui/node_modules/@biomejs/biome/package.json', {'version': '2.0.0'})
            result, plan = report(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            tools = plan['panelTools']['tools']
            self.assertEqual(tools['@biomejs/biome']['status'], 'version-mismatch')
            self.assertEqual(tools['oxlint']['status'], 'not-installed')
            self.assertEqual(tools['knip']['status'], 'not-configured')
            self.assertEqual(plan['panelTools']['status'], 'not-run')
            self.assertFalse((root / 'panel-ui/executed-during-discovery').exists())

    def test_developer_and_release_authority_reject_negative_array_index(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = authorities()
            graph['nodes'][-2]['members'] = {'pointer': '/-1/rows', 'pathField': 'path'}
            initialize(root, graph, [{'rows': [{'path': 'tools/mixed.txt'}]}])
            result, output = report(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Invalid authority array index', result.stderr)
            self.assertEqual({}, output)

    def test_stat_only_git_diff_leaves_index_bytes_and_timestamp_untouched(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            git(root, 'config', 'diff.autoRefreshIndex', 'true')
            index = root / '.git/index'
            before = (index.read_bytes(), index.stat().st_mtime_ns)
            os.utime(root / 'tools/mixed.txt', (1_000_000_000, 1_000_000_000))
            result, plan = report(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({}, plan['changes'])
            self.assertEqual(before, (index.read_bytes(), index.stat().st_mtime_ns))

    def test_reports_historical_gitlink_and_excludes_symlink_parent_contents(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / 'repo'
            root.mkdir()
            initialize(root, authorities())
            commit = git(root, 'rev-parse', 'HEAD').decode().strip()
            git(root, 'update-index', '--add', '--cacheinfo', f'160000,{commit},tools/base-submodule')
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'old gitlink')
            git(root, 'update-index', '--force-remove', '--', 'tools/base-submodule')
            (root / 'tools').rename(home / 'external')
            (root / 'tools').symlink_to(home / 'external', target_is_directory=True)
            result, plan = report(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(['tools/base-submodule'], plan['notInspected']['submodules'])
            self.assertIn('tools/mixed.txt', plan['notInspected']['symlinkedWorkingPaths'])
            self.assertNotIn('working', plan['changes']['tools/mixed.txt']['revisions'])

    def test_a_graph_saved_during_analysis_requires_fresh_read(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = authorities()
            initialize(root, graph)
            capture = planner.changed_paths
            later = False

            def edit_during(root, base, **options):
                nonlocal later
                state = capture(root, base, **options)
                if not later:
                    graph['nodes'][1]['roots'].append('tools/mixed.txt')
                    write(root, 'release/authority.json', graph)
                    later = True
                return state

            with patch.object(planner, 'changed_paths', side_effect=edit_during):
                with self.assertRaisesRegex(ValueError, 'drifted'):
                    planner.analyze(root, 'HEAD')

    def test_routes_working_index_and_base_without_running_checks_or_changing_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, authorities())
            write(root, 'tools/mixed.txt', b'index\n')
            staged_only = write(root, 'docs/staged-only.txt', b'staged and then removed locally\n')
            git(root, 'add', 'tools/mixed.txt', 'docs/staged-only.txt')
            staged_only.unlink()
            write(root, 'tools/mixed.txt', b'working\n')
            write(root, 'docs/policy.json', {'mode': 'working'})
            moved = root / 'docs/archive/relocated.txt'
            moved.parent.mkdir()
            (root / 'tools/relocated.txt').rename(moved)
            write(root, 'unknown/file.txt', b'outside declared roots')

            status = git(root, 'status', '--porcelain=v1', '-z')
            candidate_tree = git(root, 'write-tree')
            result, plan = report(root)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(plan['status'], 'review-required')
            self.assertEqual(plan['unmapped'], ['unknown/file.txt'])
            self.assertEqual(plan['inventory']['unmapped'], ['unknown/file.txt'])
            self.assertEqual(plan['panelTools']['status'], 'not-run')
            self.assertFalse((root / 'tests/check-ran.txt').exists())
            self.assertEqual(git(root, 'status', '--porcelain=v1', '-z'), status)
            self.assertEqual(git(root, 'write-tree'), candidate_tree)
            self.assertEqual((root / 'tools/mixed.txt').read_bytes(), b'working\n')
            self.assertEqual(moved.read_bytes(), b'original contents\0')

            rows = plan['changes']
            mixed = rows['tools/mixed.txt']
            self.assertEqual({key: mixed[key]['sha256'] for key in ('before', 'staged', 'after')},
                             {key: sha256(body).hexdigest() for key, body in
                              (('before', b'base\n'), ('staged', b'index\n'), ('after', b'working\n'))})
            self.assertEqual(set(mixed['revisions']), {'base', 'index', 'working'})
            self.assertEqual(rows['docs/staged-only.txt']['kind'], 'staged-only')
            self.assertEqual(set(rows['docs/staged-only.txt']['revisions']), {'index'})
            self.assertIsNone(rows['docs/staged-only.txt']['after'])

            old, new = rows['tools/relocated.txt'], rows['docs/archive/relocated.txt']
            self.assertEqual(old['moveCandidate']['to'], 'docs/archive/relocated.txt')
            self.assertEqual(new['moveCandidate']['from'], 'tools/relocated.txt')
            self.assertEqual(old['revisions']['base']['owner']['surface'], 'tools')
            self.assertEqual(new['revisions']['working']['owner'],
                             {'surface': 'records', 'root': 'docs/archive', 'role': 'record'})
            self.assertNotIn('working', old['revisions'])
            self.assertNotIn('base', new['revisions'])

            route = rows['docs/policy.json']['revisions']['working']
            self.assertEqual(route['status'], 'mapped')
            self.assertEqual(route['authorityIds'], ['policy'])
            self.assertEqual(route['declaredConsumers'], ['tools'])
            self.assertEqual(plan['surfaces']['working']['guides']['status'], 'no-surface-check')
            self.assertIn('docs/policy.json', plan['surfaces']['working']['tools']['reasons'])
            self.assertEqual(plan['surfaces']['working']['tools']['declaredChecks'],
                             [{'path': 'tests/test_tool.py', 'status': 'surface-declaration'}])

    def test_reports_ownership_change_when_file_bytes_stay_fixed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = authorities()
            initialize(root, graph)
            graph['nodes'][1]['roots'].append('tools/mixed.txt')
            write(root, 'release/authority.json', graph)
            git(root, 'add', 'release/authority.json')
            graph['nodes'][1]['roots'].remove('tools/mixed.txt')
            graph['nodes'][2]['roots'].append('tools/mixed.txt')
            write(root, 'release/authority.json', graph)

            result, plan = report(root)

        self.assertEqual(result.returncode, 0, result.stderr)
        row = plan['changes']['tools/mixed.txt']
        self.assertEqual(row['kind'], 'ownership-changed')
        self.assertEqual({key: route['owner']['surface'] for key, route in row['revisions'].items()},
                         {'base': 'tools', 'index': 'guides', 'working': 'records'})
        self.assertEqual(len({snapshot['release/authority.json']
                              for snapshot in plan['authoritySnapshots'].values()}), 3)


if __name__ == '__main__':
    unittest.main()
