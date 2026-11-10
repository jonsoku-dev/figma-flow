"""Source-level color admission regressions; no native or image provenance claim."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from draft_token_plan import authored_color_consumers, foundation_bindings


def source_fixture():
    colors = {'paper': '#fffaf0', 'ink': '#20363d', 'accent': '#227758'}
    roles = [{'kind': 'color', 'token': 'color/' + name, 'alias': 'palette/' + name, 'value': value} for name, value in colors.items()]
    graph = {'nodes': [{'id': 'open', 'type': 'action', 'title': 'Open details', 'annotation': {'visual_variant': 'Primary'}},
                       {'id': 'back', 'type': 'action', 'title': 'Return', 'annotation': {'visual_variant': 'Return'}}],
             'draft_prototype': {'states': [{'id': 'COVER'}, {'id': 'DETAIL'}], 'bindings': []},
             'design_foundations': {'roles': roles}}
    source = {'id': 'x', 'colors': colors, 'fonts': {'body': {'family': 'Inter', 'style': 'Regular'}},
              'control_styles': {}, 'state_layouts': {}, 'layouts': {}}
    for viewport in ('desktop', 'mobile'):
        source['control_styles'][viewport] = {
            'Primary': {'fill': 'accent', 'ink': 'paper', 'radius': 0, 'fontSize': 16, 'paddingX': 24, 'paddingY': 14},
            'Return': {'fill': 'paper', 'ink': 'ink', 'radius': 0, 'fontSize': 16, 'paddingX': 24, 'paddingY': 14}}
        source['state_layouts'][viewport] = {}
        for state, action in [('COVER', 'open'), ('DETAIL', 'back')]:
            source['state_layouts'][viewport][state] = {'width': 320, 'height': 240, 'bg': 'paper',
                'layers': [{'id': 'headline', 'kind': 'text', 'value': 'Readable content', 'font': 'body', 'size': 16,
                            'ink': 'ink', 'x': 24, 'y': 24, 'w': 240, 'h': 40}],
                'control_boxes': {action: [24, 120, 240, 60]}}
            graph['draft_prototype']['bindings'].append({'viewport': viewport, 'source_state': state,
                                                        'action': action, 'control_id': action})
    return source, graph


def extra_color(source, graph, name='tint', value='#d8e5d0'):
    source['colors'][name] = value
    graph['design_foundations']['roles'].append({'kind': 'color', 'token': 'color/' + name, 'alias': 'palette/' + name, 'value': value})


class DraftColorConsumerTests(unittest.TestCase):
    def test_normal_roles_use_real_screen_and_only_consumed_control_paints(self):
        source, graph = source_fixture()
        before = copy.deepcopy((source, graph))
        reports = authored_color_consumers(source, graph)
        accent = next(row for row in reports if row['token'] == 'color/accent')
        self.assertEqual(accent['consumers'], [{'key': 'x.desktop.COVER.open', 'field': 'fills'},
                                              {'key': 'x.mobile.COVER.open', 'field': 'fills'}])
        self.assertFalse(any('.component.' in use['key'] for row in reports for use in row['consumers']))
        self.assertEqual(foundation_bindings(source, graph), [])  # Implicit paint path remains unchanged.
        self.assertEqual((source, graph), before)

    def test_unused_named_role_is_rejected_even_with_same_hex_as_used_role(self):
        source, graph = source_fixture()
        extra_color(source, graph, value=source['colors']['paper'])
        with self.assertRaisesRegex(ValueError, 'color/tint: no visible authored'):
            foundation_bindings(source, graph)

    def test_unused_styles_metadata_references_and_raw_stops_do_not_camouflage_role(self):
        for kind in ('style', 'metadata', 'gradient', 'unrendered-state'):
            source, graph = source_fixture()
            extra_color(source, graph)
            if kind == 'style':
                for styles in source['control_styles'].values():
                    styles['Orphan'] = dict(styles['Primary'], fill='tint')
            elif kind == 'metadata':
                source.update(references={'desktop': 'tint-image'}, palette={'fill': 'tint'})
                source['layouts'] = {'desktop': {'bg': 'tint'}}
            elif kind == 'gradient':
                for layouts in source['state_layouts'].values():
                    layouts['COVER']['layers'].append({'id': 'glow', 'kind': 'gradient', 'x': 0, 'y': 0, 'w': 100, 'h': 100,
                                                      'stops': [{'color': source['colors']['tint'], 'position': 0, 'opacity': 1}]})
            else:
                for layouts in source['state_layouts'].values():
                    layouts['ORPHAN'] = dict(layouts['COVER'], bg='tint')
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'color/tint: no visible authored'):
                foundation_bindings(source, graph)

    def test_empty_text_and_fully_clipped_rectangles_are_not_consumers(self):
        for layer in ({'kind': 'text', 'value': '  ', 'ink': 'tint', 'size': 16, 'x': 0, 'y': 0, 'w': 100, 'h': 30},
                      {'kind': 'rect', 'fill': 'tint', 'x': 500, 'y': 0, 'w': 10, 'h': 10},
                      {'kind': 'rect', 'fill': 'tint', 'x': 0, 'y': 0, 'w': 0, 'h': 10}):
            source, graph = source_fixture()
            extra_color(source, graph)
            source['state_layouts']['desktop']['COVER']['layers'].append(dict(layer, id='unused'))
            with self.assertRaisesRegex(ValueError, 'color/tint: no visible authored'):
                foundation_bindings(source, graph)

    def test_intersecting_named_rectangle_is_a_real_consumer(self):
        source, graph = source_fixture()
        extra_color(source, graph)
        source['state_layouts']['desktop']['COVER']['layers'].append({'id': 'edge', 'kind': 'rect', 'fill': 'tint', 'x': -2, 'y': 20, 'w': 8, 'h': 20})
        self.assertEqual(next(row for row in authored_color_consumers(source, graph) if row['token'] == 'color/tint')['consumers'],
                         [{'key': 'x.desktop.COVER.edge', 'field': 'fills'}])

    def test_control_only_color_needs_visible_graph_edge_not_just_main_style(self):
        for change in ('remove-edge', 'clip', 'missing-box'):
            source, graph = source_fixture()
            for viewport in ('desktop', 'mobile'):
                if change == 'remove-edge':
                    graph['draft_prototype']['bindings'] = [e for e in graph['draft_prototype']['bindings'] if e['action'] != 'open']
                elif change == 'clip':
                    source['state_layouts'][viewport]['COVER']['control_boxes']['open'][0] = 500
                else:
                    source['state_layouts'][viewport]['COVER']['control_boxes'].clear()
            with self.subTest(change=change), self.assertRaises(ValueError):
                foundation_bindings(source, graph)

    def test_unknown_or_literal_paint_names_are_rejected_including_nonconsumer_rows(self):
        for field in ('bg', 'rect', 'text', 'orphan-style'):
            source, graph = source_fixture()
            layout = source['state_layouts']['desktop']['COVER']
            if field == 'bg':
                layout['bg'] = '#fffaf0'
            elif field == 'rect':
                layout['layers'].append({'id': 'offscreen', 'kind': 'rect', 'fill': 'missing', 'x': 500, 'y': 0, 'w': 10, 'h': 10})
            elif field == 'text':
                layout['layers'][0].update(value='', ink='missing')
            else:
                source['control_styles']['desktop']['Orphan'] = dict(source['control_styles']['desktop']['Primary'], fill='missing')
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Unknown/unbound authored paint'):
                foundation_bindings(source, graph)

    def test_source_color_map_and_graph_values_match_before_make_packet(self):
        for change in ('value', 'missing', 'extra'):
            source, graph = source_fixture()
            if change == 'value':
                source['colors']['paper'] = '#000000'
            elif change == 'missing':
                source['colors'].pop('paper')
            else:
                source['colors']['unbound'] = '#ffffff'
            with self.subTest(change=change), self.assertRaises(ValueError):
                foundation_bindings(source, graph)

    def test_direct_colors_and_aliased_colors_preserve_noncolor_zero_radius(self):
        source, graph = source_fixture()
        graph['design_foundations']['roles'][0]['alias'] = None
        graph['design_foundations']['roles'].append({'kind': 'radius', 'token': 'radius/control', 'alias': 'radius/base', 'value': '0px',
            'native': {'type': 'FLOAT', 'value': 0, 'bindings': [{'key': 'x.desktop.component.Primary', 'field': 'cornerRadius'}]}})
        rows = foundation_bindings(source, graph)
        self.assertEqual([(row['token'], row['value']) for row in rows], [('radius/control', 0)])

    def test_explicit_native_color_targets_are_exact_named_fills(self):
        source, graph = source_fixture()
        role = graph['design_foundations']['roles'][2]
        rgb = {'r': 34 / 255, 'g': 119 / 255, 'b': 88 / 255, 'a': 1}
        role['native'] = {'type': 'COLOR', 'value': rgb, 'bindings': [{'key': 'x.desktop.COVER.open', 'field': 'fills', 'paintIndex': 0}]}
        row = foundation_bindings(source, graph)[0]
        self.assertEqual(row, {'token': role['token'], 'alias': role['alias'], **role['native']})
        for field, index, target in [('strokes', 0, 'x.desktop.COVER.open'), ('fills', 1, 'x.desktop.COVER.open'),
                                     ('fills', 0, 'x.desktop.component.Primary')]:
            role['native']['bindings'] = [{'key': target, 'field': field, 'paintIndex': index}]
            with self.subTest(field=field, index=index, target=target), self.assertRaisesRegex(ValueError, 'not its authored named paint'):
                foundation_bindings(source, graph)

    def test_explicit_same_hex_wrong_role_target_and_translucent_claim_are_rejected(self):
        source, graph = source_fixture()
        role = graph['design_foundations']['roles'][2]
        role['value'] = source['colors']['ink']
        source['colors']['accent'] = source['colors']['ink']
        rgb = {'r': 32 / 255, 'g': 54 / 255, 'b': 61 / 255}
        role['native'] = {'type': 'COLOR', 'value': rgb, 'bindings': [{'key': 'x.desktop.COVER.headline', 'field': 'fills'}]}
        with self.assertRaisesRegex(ValueError, 'not its authored named paint'):
            foundation_bindings(source, graph)
        role['native']['bindings'][0]['key'] = 'x.desktop.COVER.open'
        role['native']['value']['a'] = .5
        with self.assertRaisesRegex(ValueError, 'RGB.A. differs'):
            foundation_bindings(source, graph)

    def test_duplicate_leaf_and_malformed_hex_fail(self):
        source, graph = source_fixture()
        duplicate = copy.deepcopy(graph['design_foundations']['roles'][0])
        duplicate['token'] = 'other/paper'
        graph['design_foundations']['roles'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'Ambiguous authored paint name'):
            foundation_bindings(source, graph)
        source, graph = source_fixture()
        source['colors']['paper'] = graph['design_foundations']['roles'][0]['value'] = '#fff'
        with self.assertRaisesRegex(ValueError, 'six-digit hex'):
            foundation_bindings(source, graph)


if __name__ == '__main__':
    unittest.main()
