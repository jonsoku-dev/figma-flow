"""Modeled product-parent regression oracle, never an actual Figma capture."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))

from draft_foundation_audit import audit_draft_foundations
import test_draft_foundation_audit as existing


TARGET = 'invalid-real-product-button'


class ProductButtonParentContractTests(unittest.TestCase):
    def direct(self):
        return existing.ProductButtonAuditTests().fixture()

    def nested(self, kind):
        native, candidate = self.direct()
        layout = candidate['state_layouts']['desktop']['ST']
        inner = {'key': 'controls', 'kind': kind, 'parent': 'panel', 'children': ['product']}
        if kind == 'frame':
            inner.update(box=[4, 10, 200, 70], clip=False)
        elif kind == 'auto-layout':
            inner['layout'] = {'direction': 'HORIZONTAL', 'gap': 0, 'padding': [0, 0, 0, 0],
                               'width': 'hug', 'height': 'hug'}
        layout['containers'] = [
            {'key': 'panel', 'kind': 'frame', 'box': [0, 50, 220, 100],
             'clip': False, 'children': ['controls']}, inner]

        def container(identifier, parent, semantic, node_type, box):
            return {'id': identifier, 'type': node_type, 'parentId': parent,
                    'semanticKey': semantic, 'visible': True, 'fills': [], 'strokes': [],
                    'absoluteBoundingBox': dict(zip(('x', 'y', 'width', 'height'), box))}

        outer = container('panel', 'scene', 'a.desktop.ST.panel', 'FRAME', [0, 50, 220, 100])
        inner_node = container('controls', 'panel', 'a.desktop.ST.controls',
                               'GROUP' if kind == 'group' else 'FRAME',
                               [4, 60, 200, 70] if kind == 'frame' else [10, 70, 160, 50])
        if kind == 'auto-layout':
            inner_node.update(layoutMode='HORIZONTAL', itemSpacing=0,
                              paddingTop=0, paddingRight=0, paddingBottom=0, paddingLeft=0)
        elif kind == 'frame':
            inner_node['layoutMode'] = 'NONE'
        native['nodes'].extend([outer, inner_node])
        nodes = {node['id']: node for node in native['nodes']}
        nodes['product']['parentId'] = 'controls'
        return native, candidate, nodes

    def rejected(self, native, candidate):
        report = audit_draft_foundations(native, candidate)
        self.assertIn(TARGET, {failure['code'] for failure in report['failures']}, report['failures'])

    def test_legacy_direct_screen_parent_remains_valid(self):
        native, candidate = self.direct()
        report = audit_draft_foundations(native, candidate)
        self.assertTrue(report['passed'], report['failures'])

    def test_exact_declared_nested_frame_group_and_auto_layout_are_valid(self):
        for kind in ('frame', 'group', 'auto-layout'):
            with self.subTest(kind=kind):
                native, candidate, _ = self.nested(kind)
                report = audit_draft_foundations(native, candidate)
                self.assertEqual([failure for failure in report['failures']
                                  if failure['code'] != TARGET], [])
                self.assertTrue(report['passed'], report['failures'])

    def test_skipping_declared_immediate_parent_is_rejected(self):
        for kind in ('frame', 'group', 'auto-layout'):
            with self.subTest(kind=kind):
                native, candidate, nodes = self.nested(kind)
                nodes['product']['parentId'] = 'scene'
                self.rejected(native, candidate)

    def test_sibling_parent_within_same_screen_is_rejected(self):
        native, candidate, nodes = self.nested('frame')
        sibling = copy.deepcopy(nodes['controls'])
        sibling.update(id='sibling', semanticKey='a.desktop.ST.sibling')
        native['nodes'].append(sibling)
        nodes['product']['parentId'] = 'sibling'
        self.rejected(native, candidate)

    def test_exact_immediate_parent_under_foreign_screen_is_rejected(self):
        native, candidate, nodes = self.nested('frame')
        foreign = copy.deepcopy(nodes['scene'])
        foreign.update(id='foreign-screen', semanticKey='a.desktop.OTHER')
        native['nodes'].append(foreign)
        nodes['panel']['parentId'] = 'foreign-screen'
        self.rejected(native, candidate)

    def test_declared_container_native_kind_must_match(self):
        for kind in ('frame', 'group', 'auto-layout'):
            with self.subTest(kind=kind):
                native, candidate, nodes = self.nested(kind)
                nodes['controls']['type'] = 'FRAME' if kind == 'group' else 'GROUP'
                self.rejected(native, candidate)

    def test_declared_auto_layout_requires_its_actual_direction(self):
        native, candidate, nodes = self.nested('auto-layout')
        nodes['controls']['layoutMode'] = 'NONE'
        self.rejected(native, candidate)

    def test_wrong_real_main_component_is_rejected(self):
        native, candidate = self.direct()
        nodes = {node['id']: node for node in native['nodes']}
        other_main = copy.deepcopy(nodes['main'])
        other_main.update(id='other-main', semanticKey='a.desktop.component.Other')
        native['nodes'].append(other_main)
        nodes['product']['mainComponentId'] = 'other-main'
        self.rejected(native, candidate)

    def test_source_main_requires_real_component_set(self):
        native, candidate = self.direct()
        next(node for node in native['nodes'] if node['id'] == 'set')['type'] = 'FRAME'
        self.rejected(native, candidate)

    def test_hidden_instance_or_declared_ancestor_is_rejected(self):
        for target in ('product', 'controls'):
            with self.subTest(target=target):
                native, candidate, nodes = self.nested('frame')
                nodes[target]['visible'] = False
                self.rejected(native, candidate)

    def test_missing_nonlist_or_nonempty_reactions_are_rejected(self):
        for value in (None, {}, [{'trigger': {'type': 'ON_CLICK'}}]):
            with self.subTest(reactions=value):
                native, candidate = self.direct()
                instance = next(node for node in native['nodes'] if node['id'] == 'product')
                if value is None:
                    instance.pop('reactions')
                else:
                    instance['reactions'] = value
                self.rejected(native, candidate)


if __name__ == '__main__':
    unittest.main()
