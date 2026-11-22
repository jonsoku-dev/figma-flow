import json
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
        body = b'<!doctype html><style>body{margin:0}#anchor{position:absolute;left:20px;top:20px;width:40px;height:20px} .target{position:absolute;left:20px;top:50px;width:30px;height:10px}#drift{left:25px}#intentional{left:28px}#hidden{opacity:0}#ready{position:absolute;width:2px;height:2px}</style><div id="anchor"></div><div class="target" id="aligned"></div><div class="target" id="drift"></div><div class="target" id="intentional"></div><div class="target" id="hidden"></div><script>setTimeout(()=>{const node=document.createElement("i");node.id="ready";document.body.append(node)},150)</script>'
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


if __name__ == '__main__': unittest.main()
