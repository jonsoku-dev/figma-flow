"""Captured raw Group getters; synthetic enclosing Frames exercise screen admission."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_draft

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/rd02/native-group-coordinates.json').read_text())
KEY = 'a.mobile.idle'


def scene(nested=False):
    rows = copy.deepcopy(FIXTURE['nodes'])
    frame = dict(id='screen', parentId='page', type='FRAME', x=700, y=900, width=1000, height=1000)
    outer = dict(id='enclosing', type='FRAME', parentId='screen', x=200, y=400, width=700, height=600)
    rows[0]['parentId'] = 'enclosing'
    containers = [dict(key='enclosing', kind='frame', parent=None, children=['group'], box=[200, 400, 700, 600], clip=False),
                  dict(key='group', kind='group', parent='enclosing', children=[row['id'] for row in rows if row['type'] == 'TEXT'])]
    if nested:
        rows.append(dict(id='nested', type='GROUP', parentId='enclosing', x=-165, y=-324, width=438, height=564))
        rows[0]['parentId'] = 'nested'
        containers[0]['children'] = ['nested']
        containers.insert(1, dict(key='nested', kind='group', parent='enclosing', children=['group']))
        containers[-1]['parent'] = 'nested'
    layers = [dict(id=row['id'], kind='rect', x=row['absoluteBoundingBox']['x'] + 200,
                   y=row['absoluteBoundingBox']['y'] + 400, w=row['width'], h=row['height']) for row in rows if row['type'] == 'TEXT']
    state = dict(width=1000, height=1000, layers=layers, containers=containers, control_boxes={})
    candidate = dict(id='a', prototype={'states': [{'id': 'idle'}], 'bindings': []},
                     state_layouts={'mobile': {'idle': state}})
    keyed = {KEY: frame, KEY + '.enclosing': outer, **{KEY + '.' + row['id']: row for row in rows}}
    return candidate, frame, keyed


class NativeGroupCoordinates(unittest.TestCase):
    def test_group_and_nested_group_use_nearest_frame_coordinate_container(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                candidate, frame, keyed = scene(nested)
                before = copy.deepcopy(keyed)
                self.assertEqual(figma_draft.native_screen_findings(candidate, 'mobile', 'idle', frame, keyed, page_id='page'), [])
                self.assertEqual(keyed, before)

    def test_real_coordinate_drift_and_missing_or_cyclic_ancestry_still_fail(self):
        for defect in ('drift', 'missing', 'cycle'):
            candidate, frame, keyed = scene(True)
            if defect == 'drift':
                keyed[KEY + '.title']['x'] += 10
                expected = 'geometry-drift'
            else:
                keyed[KEY + '.nested']['parentId'] = 'missing' if defect == 'missing' else 'group'
                expected = 'parent-drift'
            with self.subTest(defect=defect):
                findings = figma_draft.native_screen_findings(candidate, 'mobile', 'idle', frame, keyed)
                self.assertIn(expected, {row['code'] for row in findings})


if __name__ == '__main__':
    unittest.main()
