from hashlib import sha256
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from tools.graph_impact import analyze_impact, changed_paths, validate_graph


def graph(nodes, relations=()):
    return {
        'schema': 1,
        'nodes': [
            {'id': name, 'paths': paths, 'kind': 'source', 'action': action, 'status': 'active'}
            for name, paths, action in nodes
        ],
        'relations': [
            {'from': consumer, 'to': provider, 'type': relation, 'state': state}
            for consumer, provider, relation, state in relations
        ],
        'relationTypes': {
            'IMPLEMENTS': {'impact': True, 'usage': True, 'acyclic': False},
            'GENERATED_FROM': {'impact': True, 'usage': False, 'acyclic': True},
            'ANNOTATES': {'impact': False, 'usage': False, 'acyclic': False},
        },
    }


class GraphImpactMigrationTests(unittest.TestCase):
    def test_removed_provider_keeps_previous_typed_trace_and_action(self):
        source = ('policy', ['policy.json'], 'verify')
        consumer = ('implementation', ['app/**/*.js'], 'verify')
        document = ('documentation', ['README.md'], 'review-documentation')
        base = graph([source, consumer, document], [
            ('implementation', 'policy', 'IMPLEMENTS', 'required'),
            ('documentation', 'implementation', 'IMPLEMENTS', 'optional'),
        ])
        current = graph([consumer, document], [('documentation', 'implementation', 'IMPLEMENTS', 'optional')])
        report = analyze_impact(base, current, {'policy.json'})
        by_id = {impact['id']: impact for impact in report['impacts']}

        self.assertEqual(report['changes']['nodes']['policy']['kind'], 'removed')
        self.assertTrue(by_id['policy']['removed'])
        self.assertEqual(by_id['documentation']['action'], 'review-documentation')
        trace = next(trace for trace in by_id['documentation']['traces'] if trace['root'] == 'policy')
        self.assertEqual(trace['revision'], 'base')
        self.assertEqual(
            [(edge['from'], edge['to'], edge['type'], edge['state']) for edge in trace['relations']],
            [('implementation', 'policy', 'IMPLEMENTS', 'required'),
             ('documentation', 'implementation', 'IMPLEMENTS', 'optional')],
        )
        self.assertIsNone(report['changes']['relations'][0]['after'])

    def test_a_trace_never_mixes_relationships_from_different_revisions(self):
        nodes = [(node, [node + '.js'], 'verify') for node in ('provider', 'bridge', 'target')]
        base = graph(nodes, [('bridge', 'provider', 'IMPLEMENTS', 'required')])
        current = graph(nodes, [('target', 'bridge', 'IMPLEMENTS', 'required')])
        report = analyze_impact(base, current, {'provider.js'})
        target = next(impact for impact in report['impacts'] if impact['id'] == 'target')
        self.assertNotIn('provider', {trace['root'] for trace in target['traces']})
        self.assertIn('bridge', {trace['root'] for trace in target['traces']})

    def test_glob_scope_and_policy_keep_unsupported_dependencies_out(self):
        value = graph([
            ('source', ['app/**/*.js'], 'verify'),
            ('forbidden', ['bad.js'], 'verify'),
            ('annotation', [], 'review-documentation'),
        ], [
            ('forbidden', 'source', 'IMPLEMENTS', 'forbidden'),
            ('annotation', 'source', 'ANNOTATES', 'required'),
        ])
        report = analyze_impact(value, value, {'app/button.js', 'app/parts/icon.js', 'apps/other.js', 'app/route.ts'})
        self.assertEqual([item['id'] for item in report['impacts']], ['source'])
        self.assertEqual(report['changes']['nodes']['source']['sourcePaths'], ['app/button.js', 'app/parts/icon.js'])
        self.assertEqual(report['unmappedPaths'], ['app/route.ts', 'apps/other.js'])

    def test_a_source_move_preserves_the_declared_id(self):
        before = graph([('stable', ['old.js'], 'verify'), ('retired', ['removed.js'], 'verify')])
        after = graph([('stable', ['new.js'], 'verify'), ('introduced', ['added.js'], 'verify')])
        report = analyze_impact(before, after, {'old.js', 'new.js', 'removed.js', 'added.js'})
        changes = report['changes']['nodes']
        self.assertEqual({node: change['kind'] for node, change in changes.items()},
                         {'stable': 'moved', 'retired': 'removed', 'introduced': 'added'})
        self.assertEqual(changes['stable']['before']['paths'], ['old.js'])
        self.assertEqual(changes['stable']['after']['paths'], ['new.js'])

    def test_relation_removal_marks_unchanged_consumer_for_its_declared_action(self):
        nodes = [('source', ['source.js'], 'verify'), ('docs', ['guide.md'], 'review-documentation')]
        before = graph(nodes, [('docs', 'source', 'IMPLEMENTS', 'required')])
        report = analyze_impact(before, graph(nodes), set())
        self.assertEqual(report['changes']['nodes'], {})
        [relation] = report['changes']['relations']
        self.assertEqual((relation['kind'], relation['before']['from']), ('removed', 'docs'))
        [impact] = report['impacts']
        self.assertEqual((impact['id'], impact['action']), ('docs', 'review-documentation'))

    def test_a_new_file_in_node_scope_is_a_definition_change(self):
        before = graph([('existing', ['original.js'], 'verify')])
        after = graph([('existing', ['original.js', 'added.js'], 'verify')])
        [change] = analyze_impact(before, after, {'added.js'})['changes']['nodes'].values()
        self.assertEqual(change['kind'], 'modified')
        self.assertEqual(change['sourcePaths'], ['added.js'])

    def test_only_a_declared_execution_order_cycle_is_invalid(self):
        nodes = [('a', [], 'verify'), ('b', [], 'verify')]
        allowed = graph(nodes, [
            ('a', 'b', 'IMPLEMENTS', 'required'), ('b', 'a', 'IMPLEMENTS', 'required'),
            ('a', 'b', 'GENERATED_FROM', 'required'), ('b', 'a', 'GENERATED_FROM', 'forbidden'),
        ])
        validate_graph(allowed)
        self.assertEqual(len(analyze_impact(allowed, allowed, set())['impacts']), 0)
        allowed['relations'][3]['state'] = 'required'
        with self.assertRaisesRegex(ValueError, 'form a cycle'):
            validate_graph(allowed)

    def test_source_evidence_hashes_base_index_and_worktree_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                subprocess.run(['git', '-C', directory, *args], capture_output=True, check=True)

            def write(name, body):
                (root / name).write_bytes(body)

            git('init', '-q')
            write('mixed.txt', b'base\n')
            write('staged-only.txt', b'original\n')
            write('move-from.txt', b'linked\n')
            write('ambiguous-a.txt', b'duplicate\n')
            write('ambiguous-b.txt', b'duplicate\n')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            write('mixed.txt', b'staged\n')
            write('staged-only.txt', b'index\n')
            git('add', 'mixed.txt', 'staged-only.txt')
            write('mixed.txt', b'working\n')
            write('staged-only.txt', b'original\n')
            (root / 'move-from.txt').rename(root / 'move-to.txt')
            (root / 'ambiguous-a.txt').rename(root / 'ambiguous-new.txt')
            (root / 'ambiguous-b.txt').unlink()
            write('untracked.txt', b'untracked\0data')
            observed = changed_paths(root, 'HEAD')

        self.assertEqual(
            {key: observed['mixed.txt'][key]['sha256'] for key in ('before', 'staged', 'after')},
            {'before': sha256(b'base\n').hexdigest(),
             'staged': sha256(b'staged\n').hexdigest(),
             'after': sha256(b'working\n').hexdigest()},
        )
        self.assertEqual(observed['staged-only.txt']['kind'], 'staged-only')
        self.assertEqual(observed['move-from.txt']['kind'], 'removed')
        self.assertEqual(observed['move-from.txt']['moveCandidate']['to'], 'move-to.txt')
        self.assertEqual(observed['move-to.txt']['kind'], 'added')
        self.assertEqual(observed['ambiguous-new.txt']['moveCandidate']['evidence'], 'ambiguous-identical-bytes-and-mode')
        self.assertEqual(observed['untracked.txt']['after']['sha256'], sha256(b'untracked\0data').hexdigest())


if __name__ == '__main__':
    unittest.main()
