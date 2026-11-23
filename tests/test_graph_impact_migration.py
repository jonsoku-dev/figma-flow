from hashlib import sha256
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from tools.graph_impact import analyze_impact, analyze_observed_impact, changed_paths, panel_base_snapshot, validate_graph


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


def observation(revision, nodes, edges=(), **updates):
    report = {
        'schema': 'figma-flow-observed-panel-v1',
        'sourceFingerprint': revision,
        'extractor': {'name': 'fixture'},
        'inputFiles': {},
        'nodes': [{'path': node, 'origin': 'source', 'sha256': revision + node} for node in nodes],
        'edges': [
            {'from': origin, 'to': target, 'type': kind, 'mode': 'static', 'resolution': 'local',
             'certainty': 'extracted', 'location': {'path': origin, 'line': line}}
            for line, (origin, target, kind) in enumerate(edges, 1)
        ],
        'externalEvidence': [],
        'findings': [],
    }
    return {**report, **updates}


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

    def test_observed_binding_schedules_its_declared_action_in_the_witnessed_revision(self):
        value = graph([
            ('provider', ['provider.js'], 'verify'),
            ('implementation', ['module.js'], 'verify-contract'),
            ('guide', ['guide.md'], 'review-documentation'),
        ], [('guide', 'implementation', 'IMPLEMENTS', 'required')])
        observed = [{
            'path': 'module.js',
            'bindings': {'base': ['implementation'], 'current': ['implementation']},
            'traces': [{'root': 'provider.js', 'revision': 'base'}],
        }]
        report = analyze_impact(value, value, {'provider.js'}, observed_targets=observed)
        self.assertEqual(set(report['changes']['nodes']), {'provider'})
        targets = {row['id']: row for row in report['impacts']}
        self.assertEqual(targets['implementation']['action'], 'verify-contract')
        self.assertEqual(targets['guide']['action'], 'review-documentation')
        [trace] = targets['guide']['traces']
        self.assertEqual(trace['revision'], 'base')
        self.assertEqual(trace['observedOrigins'], [{'path': 'module.js', 'root': 'provider.js'}])
        self.assertEqual(trace['relations'][0]['to'], 'implementation')

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

    def test_observed_impact_keeps_removed_reexports_and_never_mixes_revisions(self):
        provider, bridge, app = ('src/' + name + '.js' for name in ('provider', 'bridge', 'app'))
        paths = (provider, bridge, app)
        before = observation('old', paths, [(bridge, provider, 'REEXPORTS')])
        after = observation('new', paths, [(app, bridge, 'IMPORTS')])
        types = {'IMPORTS': {'impact': True}, 'REEXPORTS': {'impact': True}}
        report = analyze_observed_impact(before, after, {provider}, base_types=types, current_types=types)
        self.assertEqual(report['base']['sourceFingerprint'], 'old')
        self.assertEqual(report['current']['sourceFingerprint'], 'new')
        self.assertEqual({row['kind'] for row in report['relationChanges']}, {'added', 'removed'})
        bridge_target = next(row for row in report['targets'] if row['path'] == bridge)
        [trace] = [trace for trace in bridge_target['traces'] if trace['root'] == provider]
        self.assertEqual(trace['revision'], 'base')
        self.assertEqual(trace['relations'][0]['type'], 'REEXPORTS')
        self.assertEqual(trace['relations'][0]['evidence'][0]['location'], {'path': bridge, 'line': 1})
        app_target = next(row for row in report['targets'] if row['path'] == app)
        self.assertNotIn(provider, {trace['root'] for trace in app_target['traces']})

    def test_observed_impact_follows_projections_and_verified_external_readers(self):
        config, registry, app, consumer = ('routes.json', 'src/registry.js', 'src/app.js', 'tools/report.py')
        report = observation('observed', [app], [(app, registry, 'IMPORTS')],
                             inputFiles={config: 'config-sha', consumer: 'consumer-sha'})
        report['nodes'].append({'path': registry, 'origin': 'generated',
                                'generatedFrom': config, 'sha256': 'generated-sha'})
        report['externalEvidence'].append({'path': app, 'consumer': consumer, 'certainty': 'extracted',
                                           'location': {'path': consumer, 'line': 4}})
        report['edges'].append({'from': app, 'to': 'guess.js', 'type': 'CALLS', 'certainty': 'syntactic'})
        report['findings'].append({'path': app, 'rule': 'dynamic-unknown'})
        types = {kind: {'impact': True} for kind in ('CALLS', 'GENERATED_FROM', 'IMPORTS')}
        result = analyze_observed_impact(report, report, {config}, base_types=types, current_types=types)
        affected = {row['path']: row for row in result['targets']}
        self.assertEqual(set(affected), {config, registry, app, consumer})
        consumer_trace = affected[consumer]['traces'][0]['relations']
        self.assertEqual([edge['mode'] for edge in consumer_trace],
                         ['projection', 'static', 'external-consumer'])
        self.assertEqual(consumer_trace[0]['evidence'][0]['inputSha256'], 'config-sha')
        self.assertEqual(consumer_trace[-1]['evidence'][0]['location']['line'], 4)
        self.assertEqual(result['unknown'][0], {'revision': 'base', 'path': app, 'rule': 'dynamic-unknown'})

    def test_call_impact_keeps_distinct_proven_target_symbols(self):
        caller, provider = 'src/consumer.js', 'src/provider.js'
        before, after = (observation(revision, [caller, provider]) for revision in ('old', 'new'))
        call = {
            'from': caller, 'to': provider, 'type': 'CALLS', 'mode': 'static-import-binding',
            'certainty': 'extracted', 'location': {'path': caller, 'line': 3},
            'importLocation': {'path': caller, 'line': 1},
        }
        before['edges'] = [{**call, 'targetSymbol': 'open', 'symbol': 'openEditor'},
                           {**call, 'targetSymbol': 'close', 'symbol': 'closeEditor'}]
        after['edges'] = [before['edges'][1], {
            'type': 'CALLS', 'from': caller, 'to': None, 'certainty': 'syntactic',
            'importCandidate': {'to': provider, 'targetSymbol': 'open', 'reason': 'possible-lexical-shadow'},
            'location': {'path': caller, 'line': 3},
        }]
        types = {'CALLS': {'impact': True}}
        report = analyze_observed_impact(before, after, {provider}, base_types=types, current_types=types)
        [removed] = report['relationChanges']
        self.assertEqual((removed['kind'], removed['before']['targetSymbol']), ('removed', 'open'))
        self.assertEqual(removed['before']['evidence'][0]['calledAs'], 'openEditor')
        [unknown] = report['unknown']
        self.assertEqual((unknown['revision'], unknown['rule']), ('current', 'call-target-unknown'))
        impact = next(row for row in report['targets'] if row['path'] == caller)
        [trace] = [trace for trace in impact['traces'] if trace['root'] == provider and trace['revision'] == 'current']
        self.assertEqual([edge['targetSymbol'] for edge in trace['relations']], ['close'])

    def test_base_observation_stages_only_selected_git_bytes_and_cleans_up(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                subprocess.run(['git', '-C', directory, *args], capture_output=True, check=True)

            git('init', '-q')
            (root / 'panel-ui/src').mkdir(parents=True)
            source = root / 'panel-ui/src/record.js'
            source.write_bytes(b'committed\r\n\0data')
            (root / 'outside.txt').write_bytes(b'do not stage')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            source.write_bytes(b'unsaved')
            with panel_base_snapshot(root, 'HEAD', ['panel-ui/src/**']) as checkout:
                self.assertEqual((checkout / 'panel-ui/src/record.js').read_bytes(), b'committed\r\n\0data')
                self.assertFalse((checkout / 'outside.txt').exists())
                self.assertFalse((checkout / '.git').exists())
                self.assertEqual(source.read_bytes(), b'unsaved')
            self.assertFalse(checkout.exists())

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
