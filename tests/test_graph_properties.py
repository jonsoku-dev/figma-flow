"""Run reproducible graph invariants against bounded, generated inputs."""
import argparse
import json
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from graph_document import contract, decode_json


def cases(seed, trials):
    rng = random.Random(seed)
    for index in range(trials):
        nodes = [
            {'id':f'SCREEN-{i}', 'type':'screen', 'title':rng.choice(('시안', '図', 'Screen', '🎨')),
             'status':'planned'}
            for i in range(rng.randint(1, 6))
        ]
        edges = [{'from':n['id'], 'to':rng.choice(nodes)['id'], 'type':'compares'} for n in nodes]
        graph = {'version':1, 'nodes':nodes, 'edges':edges}
        canonical = json.dumps(graph, ensure_ascii=False)
        decoded = decode_json(canonical.encode())
        if decoded != graph or contract.validate_graph(graph)[0]:
            raise AssertionError(f'Seed {seed}, case {index}, valid graph {canonical}')
        shuffled = {**graph, 'nodes':rng.sample(nodes,len(nodes)), 'edges':rng.sample(edges,len(edges))}
        if contract.validate_graph(shuffled)[0]:
            raise AssertionError(f'Seed {seed}, case {index}, reordered graph {json.dumps(shuffled)}')
        malformed = rng.choice([[], {}, True, None, 8, [None]])
        # Each mutation changes one structural field, so its failure includes a replayable input.
        type_of_change = rng.randrange(4)
        if type_of_change == 0:
            graph['nodes'][0]['type'] = malformed
        elif type_of_change == 1:
            graph['nodes'].append(dict(graph['nodes'][0]))
        elif type_of_change == 2:
            graph['edges'][0]['to'] = 'MISSING'
        else:
            graph['edges'][0]['type'] = malformed
        try:
            errors, _ = contract.validate_graph(graph)
            if not errors:
                raise AssertionError('Malformed input passed graph validation')
        except Exception as exc:
            raise AssertionError(f'Seed {seed}, case {index}, mutated graph {json.dumps(graph)}') from exc

        key = rng.choice(('owner', '검증', 'node'))
        duplicate = '{' + json.dumps(key) + ':1,' + json.dumps(key) + ':2}'
        try:
            decode_json(duplicate)
        except ValueError:
            continue
        raise AssertionError(f'Seed {seed}, case {index}, duplicate key input {duplicate}')


class GraphPropertiesTests(unittest.TestCase):
    def test_bounded_graph_inputs_preserve_identity_and_reject_corruption(self):
        cases(271828, 250)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=271828)
    parser.add_argument('--trials', type=int, default=250)
    args = parser.parse_args()
    if not 1 <= args.trials <= 20000:
        parser.error('Choose 1–20,000 trials')
    cases(args.seed,args.trials)
    print(f'Graph properties passed for {args.trials} generated cases with seed {args.seed}.')
