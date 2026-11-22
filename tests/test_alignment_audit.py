import json
import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get('CHROME_BIN') or shutil.which('chromium') or shutil.which('google-chrome') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'<!doctype html><style>body{margin:0}#anchor{position:absolute;left:20px;top:20px;width:40px;height:20px} .target{position:absolute;left:20px;top:50px;width:30px;height:10px}#drift{left:25px}#intentional{left:28px}#hidden{opacity:0}#ready{position:absolute;width:2px;height:2px}.ink{position:absolute;left:30px;top:100px;display:block;width:60px;height:30px;font:20px Arial,sans-serif;line-height:30px;white-space:pre}#ink-anchor{top:60px}#ink-offscreen,#ink-decorated,#ink-background-only,#ink-dynamic{top:160px}.paintSvg{position:absolute;left:30px;top:100px;width:60px;height:30px}.offscreen{left:-2px}.decorated{background:#f00}@keyframes blink{to{opacity:.5}}.dynamic{animation:blink 1s infinite}.clipbox{position:absolute;left:30px;top:210px;width:10px;height:30px;overflow:hidden}.clipbox>.ink{left:0;top:0}</style><div id="anchor"></div><div class="target" id="aligned"></div><div class="target" id="drift"></div><div class="target" id="intentional"></div><div class="target" id="hidden"></div><span class="ink" id="ink-anchor">M</span><svg class="paintSvg" id="ink-narrow" viewBox="0 0 60 30"><rect x="2" y="4" width="3" height="12"/></svg><svg class="paintSvg" id="ink-wide" viewBox="0 0 60 30"><rect x="30" y="4" width="14" height="12"/></svg><span class="ink offscreen" id="ink-offscreen">W</span><span class="ink decorated" id="ink-decorated">W</span><span class="ink decorated" id="ink-background-only"></span><span class="ink" id="ink-empty">   </span><svg class="paintSvg dynamic" id="ink-dynamic" viewBox="0 0 60 30"><rect x="30" y="4" width="14" height="12"/></svg><span class="ink" id="ink-nested"><b>W</b></span><div class="clipbox"><span class="ink">WWWW</span></div><script>setTimeout(()=>{const node=document.createElement("i");node.id="ready";document.body.append(node)},150)</script>'
        self.send_response(200); self.send_header('Content-Type', 'text/html'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass


@unittest.skipUnless(Path(CHROME).exists(), 'installed Chromium required for browser behavior proof')
class AlignmentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/fixture?case=alignment#home'

    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()

    def run_audit(self, rules):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        base = Path(temp.name); rulefile = base/'rules.json'; rulefile.write_text(json.dumps(rules))
        out = base/'evidence'
        proc = subprocess.run(['node', str(ROOT/'tools/alignment_audit.mjs'), '--url', self.url, '--rules', str(rulefile), '--out', str(out), '--widths', '320', '--height', '300', '--chrome', CHROME], capture_output=True, text=True, timeout=50)
        return proc, out

    def test_signed_drift_and_missing_are_distinct_and_captures_are_written(self):
        proc, out = self.run_audit({'readySelector':'#ready','groups':[{'id':'targets','axis':'x','edge':'start','anchor':'#anchor','targets':['#aligned','#drift','.target:not(#intentional)','#missing']},{'id':'optical-offset','axis':'x','edge':'start','anchor':'#anchor','targets':['#intentional'],'expectedOffset':8}]})
        self.assertEqual(proc.returncode, 2, proc.stderr)
        report = json.loads((out/'report.json').read_text())
        self.assertEqual(report['pageKey'], '/fixture?case=alignment#home')
        targets = report['viewports'][0]['groups'][0]['targets']
        self.assertEqual([(t['status'],t.get('delta')) for t in targets], [('pass',0),('drift',5),('pass',0),('drift',5),('unverified',None)])
        self.assertEqual(targets[-1]['reason'], 'missing-target')
        self.assertEqual([t['occurrenceIndex'] for t in targets[2:4]], [0,1])
        offset = report['viewports'][0]['groups'][1]['targets'][0]
        self.assertEqual((offset['delta'],offset['expectedOffset'],offset['deviation'],offset['status']), (8,8,0,'pass'))
        self.assertTrue((out/'width-320-clean.png').stat().st_size > 100)
        self.assertTrue((out/'width-320-guide-overlay.png').stat().st_size > 100)
        colors=[color for _,color in Image.open(out/'width-320-guide-overlay.png').convert('RGB').getcolors(1_000_000)]
        self.assertTrue(any(b > r and b > g for r,g,b in colors), 'guide overlay includes blue anchor reference')
        self.assertTrue(any(r > g and r > b for r,g,b in colors), 'guide overlay includes red drift marker')

    def test_missing_anchor_is_unverified(self):
        proc, out = self.run_audit({'groups':[{'id':'missing-anchor','axis':'y','edge':'center','anchor':'#absent','targets':['#aligned']}]})
        self.assertEqual(proc.returncode, 2, proc.stderr)
        target = json.loads((out/'report.json').read_text())['viewports'][0]['groups'][0]['targets'][0]
        self.assertEqual(target['status'], 'unverified'); self.assertEqual(target['reason'], 'missing-anchor')

    def test_exit_codes_follow_pass_and_drift_statuses(self):
        passing, _ = self.run_audit({'groups':[{'id':'aligned','axis':'x','edge':'start','anchor':'#anchor','targets':['#aligned']}]})
        drifting, _ = self.run_audit({'groups':[{'id':'offset','axis':'x','edge':'start','anchor':'#anchor','targets':['#drift']}]})
        self.assertEqual(passing.returncode, 0, passing.stderr)
        self.assertEqual(drifting.returncode, 1, drifting.stderr)

    def test_paint_mode_measures_ink_separately_from_equal_css_boxes(self):
        proc, out = self.run_audit({'measurement':'paint','groups':[{'id':'ink','axis':'x','edge':'end','anchor':'#ink-anchor','targets':['#ink-narrow','#ink-wide'],'expectedOffset':-11,'tolerance':1}]})
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        report = json.loads((out/'report.json').read_text())
        self.assertEqual(report['status'], 'drift')
        group = report['viewports'][0]['groups'][0]
        narrow, wide = group['targets']
        self.assertEqual((narrow['rect'], wide['rect']), (narrow['boxRect'], wide['boxRect']))
        self.assertEqual((narrow['rect']['width'], wide['rect']['width']), (60, 60))
        self.assertGreater(wide['paintedRect']['width'], narrow['paintedRect']['width'])
        self.assertNotEqual(narrow['delta'], wide['delta'])
        self.assertEqual((narrow['delta'],narrow['expectedOffset'],narrow['deviation'],narrow['status']),(-11,-11,0,'pass'))
        self.assertEqual(wide['status'], 'drift')
        self.assertEqual(group['anchorRect']['width'], 60)
        self.assertIn('anchorPaintedRect', group)
        self.assertTrue(all((out/name).exists() for name in narrow['pixelEvidence']))

    def test_paint_mode_rejects_empty_offscreen_and_decorated_elements(self):
        proc, out = self.run_audit({'measurement':'paint','groups':[{'id':'ink','axis':'x','edge':'start','anchor':'#ink-anchor','targets':['#ink-offscreen','#ink-decorated','#ink-background-only','#ink-empty','#ink-dynamic','#ink-nested','.clipbox > .ink']}]})
        self.assertEqual(proc.returncode, 2, proc.stderr)
        rows = json.loads((out/'report.json').read_text())['viewports'][0]['groups'][0]['targets']
        self.assertEqual([row['reason'] for row in rows], ['offscreen-or-clipped','decorated-or-mixed-html',
                                                           'unsupported-or-empty-text','unsupported-or-empty-text',
                                                           'dynamic-or-clipped','unsupported-or-empty-text',
                                                           'partially-clipped'])
        self.assertTrue(all('paintedRect' not in row for row in rows))

    def test_box_mode_keeps_legacy_normalized_hash_and_fields(self):
        rules = {'groups':[{'id':'aligned','axis':'x','edge':'start','anchor':'#anchor','targets':['#aligned']}]}
        proc, out = self.run_audit(rules)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads((out/'report.json').read_text())
        normalized = {'readySelector':None,'groups':[{'id':'aligned','axis':'x','edge':'start','anchor':'#anchor','targets':['#aligned'],'tolerance':1,'expectedOffset':0}]}
        expected = hashlib.sha256(json.dumps(normalized, separators=(',',':')).encode()).hexdigest()
        self.assertEqual(report['rulesSha256'], expected)
        self.assertNotIn('measurement', report['viewports'][0])
        self.assertNotIn('paintedRect', report['viewports'][0]['groups'][0]['targets'][0])


if __name__ == '__main__': unittest.main()
