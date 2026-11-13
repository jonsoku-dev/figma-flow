"""Keep browser-observed CSS letter spacing through the native edit plan."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_edit
import web_design


class WebDesignTrackingTests(unittest.TestCase):
    def graph(self, spacing):
        text = {
            'characters': 'Build something useful',
            'fontFamily': 'Geist',
            'fontSize': 56,
            'fontWeight': 600,
            'lineHeight': 62,
            'color': '#111111',
        }
        if spacing is not None:
            text['letterSpacing'] = spacing
        return {
            'version': 1,
            'id': 'magicui-tracking',
            'title': 'MagicUI tracking observation',
            'nodes': [{
                'id': 'WEB-magicui-home',
                'type': 'screen',
                'title': 'MagicUI home',
                'status': 'observed',
                'layout': {'width': 1440, 'height': 900, 'background': '#ffffff'},
                'elements': [{
                    'id': 'hero-title',
                    'kind': 'text',
                    'path': [],
                    'box': {'x': 176, 'y': 216, 'width': 1088, 'height': 62},
                    'text': text,
                }],
            }],
            'edges': [],
        }

    def make_plan(self, graph):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'graph.json'
            output = Path(directory) / 'plan.json'
            source.write_text(json.dumps(graph))
            web_design.build_plan(source, 'fixture-file', '1:1', output)
            plan = json.loads(output.read_text())
            native_edit.validate_plan(plan)
            return plan['web_design']['screens'][0]['elements'][0]['text']

    def test_nonzero_css_tracking_survives_graph_validation_and_native_plan(self):
        graph = self.graph(-1.12)
        try:
            validated = web_design.validate_graph(graph)
        except ValueError as error:
            self.fail(f'CSS tracking was rejected before native planning: {error}')
        self.assertEqual(validated[0]['elements'][0]['text']['letterSpacing'], -1.12)
        native_text = self.make_plan(graph)
        self.assertEqual(native_text['letterSpacing'], -1.12)

    def test_normal_css_tracking_can_remain_omitted(self):
        graph = self.graph(None)
        validated = web_design.validate_graph(graph)
        self.assertNotIn('letterSpacing', validated[0]['elements'][0]['text'])
        native_text = self.make_plan(graph)
        self.assertNotIn('letterSpacing', native_text)


if __name__ == '__main__':
    unittest.main()
