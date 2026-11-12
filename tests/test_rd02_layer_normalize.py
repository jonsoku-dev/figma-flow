import json
import sys
import unittest
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('design_directions', ROOT / 'tools/design_directions.py')
directions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(directions)
FIXTURE = ROOT / 'tests' / 'fixtures' / 'rd02'


def load(name):
    return json.loads((FIXTURE / name).read_text())


class LayerContainerNormalizationTests(unittest.TestCase):
    def test_declared_containers_normalize_without_inferred_groups(self):
        normalize = getattr(directions, 'normalize_layer_containers', None)
        self.assertIsNotNone(normalize, 'declared containers must be normalized before authoring')
        flat = normalize(load('flat-layers.json'))
        self.assertEqual(flat['containers'], [])
        self.assertEqual([layer['id'] for layer in flat['layers']], ['title', 'body', 'ornament', 'save', 'cancel'])
        declared = normalize(load('declared-containers.json'))
        self.assertEqual([item['kind'] for item in declared['containers']], ['frame', 'auto-layout', 'group', 'auto-layout'])
        self.assertEqual([item['key'] for item in declared['containers']], ['card', 'copy', 'ornament-cluster', 'actions'])
        self.assertEqual(declared['containers'][0]['children'], ['copy', 'ornament-cluster', 'actions'])
        self.assertTrue({'layout', 'fill', 'clip'}.isdisjoint(declared['containers'][2]))
        cycled = load('declared-containers.json')
        cycled['containers'][0]['parent'] = 'copy'
        with self.assertRaisesRegex(ValueError, 'cycle'):
            normalize(cycled)
        duplicated = load('declared-containers.json')
        duplicated['containers'].append(dict(duplicated['containers'][2], key='extra-ornament', children=['ornament']))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            normalize(duplicated)
        missing = load('declared-containers.json')
        missing['containers'][1]['children'] = ['title', 'missing']
        with self.assertRaisesRegex(ValueError, 'missing'):
            normalize(missing)
        grouped = load('declared-containers.json')
        grouped['containers'][2]['fill'] = 'surface'
        with self.assertRaisesRegex(ValueError, 'group'):
            normalize(grouped)


if __name__ == '__main__':
    unittest.main()
