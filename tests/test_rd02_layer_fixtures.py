import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'rd02'


def load(name):
    return json.loads((FIXTURE / name).read_text())


class LayerFixtureTests(unittest.TestCase):
    def test_flat_and_declared_hierarchies_stay_separate(self):
        flat = load('flat-layers.json')
        declared = load('declared-containers.json')
        self.assertEqual([layer['id'] for layer in flat['layers']], [layer['id'] for layer in declared['layers']])
        self.assertEqual(flat['containers'], [])
        kinds = {item['kind'] for item in declared['containers']}
        self.assertEqual(kinds, {'frame', 'auto-layout', 'group'})
        by_key = {item['key']: item for item in declared['containers']}
        self.assertEqual(by_key['card']['children'], ['copy', 'ornament-cluster', 'actions'])
        self.assertIsNone(by_key['card']['parent'])
        self.assertEqual(by_key['copy']['layout']['direction'], 'VERTICAL')
        self.assertEqual(by_key['actions']['layout']['direction'], 'HORIZONTAL')
        group = by_key['ornament-cluster']
        self.assertEqual(group['parent'], 'card')
        self.assertTrue({'layout', 'fill', 'clip'}.isdisjoint(group))
        layer_ids = {layer['id'] for layer in declared['layers']}
        container_keys = set(by_key)
        self.assertTrue(layer_ids.isdisjoint(container_keys))
        for item in declared['containers']:
            for child in item['children']:
                owner = by_key.get(child)
                if owner is not None:
                    self.assertEqual(owner['parent'], item['key'])
                else:
                    self.assertIn(child, layer_ids)
        self.assertEqual(len(declared['containers']), 4)


if __name__ == '__main__':
    unittest.main()
