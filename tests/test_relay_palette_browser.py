"""Browser evidence for graph-owned relay colors and dimensions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from plugin_panel import render_app


class RelayPaletteBrowserTests(unittest.TestCase):
    def test_light_dark_palette_and_responsive_metrics_match_the_previous_design(self):
        with tempfile.TemporaryDirectory() as temp:
            html = Path(temp) / 'relay.html'
            html.write_text(render_app('relay'), encoding='utf-8')
            result = subprocess.run(
                ['node', str(ROOT / 'tests/helpers/relay_palette.mjs'), str(html)],
                capture_output=True, text=True, timeout=30,
            )
        if result.returncode == 77:
            self.skipTest('Chromium executable unavailable')
        self.assertEqual(result.returncode, 0, result.stderr)
        samples = json.loads(result.stdout)
        self.assertEqual([sample['width'] for sample in samples], [320, 400])
        self.assertEqual(samples[0]['palette'], {
            'text': 'rgb(32, 37, 54)', 'canvas': 'rgb(241, 243, 246)', 'card': 'rgb(255, 255, 255)',
            'cardBorder': 'rgb(205, 211, 220)', 'statusError': 'rgb(150, 61, 53)',
            'errorText': 'rgb(126, 48, 42)', 'errorSurface': 'rgb(255, 240, 237)',
        })
        self.assertEqual(samples[0]['darkPalette'], {
            'text': 'rgb(231, 234, 240)', 'canvas': 'rgb(25, 28, 34)', 'card': 'rgb(35, 40, 50)',
            'cardBorder': 'rgb(64, 70, 83)', 'statusError': 'rgb(255, 170, 160)',
            'errorText': 'rgb(255, 209, 203)', 'errorSurface': 'rgb(73, 46, 49)',
        })
        for sample, page_pad, inset, label_width, card_width in zip(samples, ('8px', '10px'), ('12px', '14px'), ('92px', '104px'), ('304px', '380px')):
            metrics = sample['metrics']
            self.assertEqual(metrics['pagePadding'], page_pad)
            self.assertEqual(metrics['pageMinHeight'], '900px')
            self.assertIn('Inter', metrics['pageFont'])
            self.assertEqual(metrics['pageTracking'], '-0.325px')
            self.assertEqual(metrics['cardWidth'], card_width)
            self.assertEqual(metrics['cardBorder'], '1px')
            self.assertEqual(metrics['cardRadius'], '12px')
            self.assertEqual(metrics['cardShadow'], 'rgba(29, 44, 67, 0.06) 0px 2px 8px 0px')
            self.assertEqual(metrics['headerHeight'], '44px')
            self.assertEqual(metrics['headerGap'], '9px')
            self.assertEqual(metrics['headerInset'], inset)
            self.assertEqual(metrics['contentInset'], inset)
            self.assertEqual(metrics['titleSize'], '15px')
            self.assertEqual(metrics['titleTracking'], '-0.6px')
            self.assertEqual(metrics['brandSize'], '25px')
            self.assertEqual(metrics['statusSize'], '11px')
            self.assertEqual(metrics['headingSize'], '18px')
            self.assertEqual(metrics['headingLineHeight'], '23.4px')
            self.assertEqual(metrics['headingTracking'], '-0.81px')
            self.assertEqual(metrics['captionSize'], '12px')
            self.assertEqual(metrics['captionLineHeight'], '17.4px')
            self.assertEqual(metrics['contextHeight'], '30px')
            self.assertEqual(metrics['contextLabelWidth'], label_width)
            self.assertEqual(metrics['contextWeight'], '550')
            self.assertEqual(metrics['errorRadius'], '5px')
            self.assertEqual(metrics['errorFontSize'], '11px')
            self.assertEqual(metrics['footerHeight'], '36px')
            self.assertEqual(metrics['summaryHeight'], '24px')
            self.assertEqual(metrics['detailsPadding'], '2px 0px 5px')


if __name__ == '__main__':
    unittest.main()
