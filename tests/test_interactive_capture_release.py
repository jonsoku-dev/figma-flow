"""Drive actual browser inputs on disposable pages and verify the resulting editable state graph."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
HEAD='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fixture workshop</title><style>*{box-sizing:border-box}body{margin:0;padding:12px;font:16px Arial,sans-serif;background:white;color:black}button,summary{padding:12px}h2{font-size:20px}</style><body>'
TABS=HEAD+'''<div id="tabs"><button>Overview</button><button>Details</button></div><section id="panel">Overview content</section>
<script>document.querySelectorAll('button').forEach(b=>b.onclick=()=>document.querySelector('#panel').textContent=b.textContent+' content')</script></body></html>'''
DISCLOSURE=HEAD+'''<div id="faq"><div class="item"><button aria-expanded="false" aria-controls="answer-a">First question</button><div hidden id="answer-a">First answer</div></div><div class="item"><button aria-expanded="false" aria-controls="answer-b">Second question</button><div hidden id="answer-b">Second answer</div></div></div>
<script>for(const button of document.querySelectorAll('button'))button.onclick=()=>{
 const open=button.getAttribute('aria-expanded')==='false';
 for(const other of document.querySelectorAll('button')){const yes=open&&other===button;other.setAttribute('aria-expanded',String(yes));document.getElementById(other.getAttribute('aria-controls')).hidden=!yes;}
}</script></body></html>'''
CAROUSEL=HEAD+'''<style>#rail{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;touch-action:pan-x;width:100%;height:188px}article{flex:0 0 100%;scroll-snap-align:center;padding:15px;background:#eee}article:nth-child(2){background:#ddd}body{min-height:1500px;padding-top:390px}</style><div id="rail"><article><h2>First class</h2><p>Morning session</p></article><article><h2>Second class</h2><p>Afternoon session</p></article></div><script>const rail=document.getElementById('rail');let timer;function arm(){clearInterval(timer);timer=setInterval(()=>{rail.scrollTo({left:rail.scrollLeft>rail.clientWidth/2?0:rail.clientWidth,behavior:'instant'})},2600)}arm();rail.addEventListener('touchend',arm)</script></body></html>'''


class InteractiveBrowserTests(unittest.TestCase):
    def capture(self,mode,html,args):
        class Page(BaseHTTPRequestHandler):
            def do_GET(self):
                body=html.encode()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self,*_):
                pass
        with ThreadingHTTPServer(('127.0.0.1',0),Page) as server,tempfile.TemporaryDirectory() as temp:
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            dest=Path(temp)/'capture'
            try:
                command=['node','tools/web_'+mode+'_capture.mjs','--url',f'http://127.0.0.1:{server.server_port}/',
                         '--out',str(dest),'--id','release-fixture',*args]
                result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=85,
                                      env={**os.environ,'PYTHON':sys.executable,'PYTHONDONTWRITEBYTECODE':'1'})
                self.assertTrue(result.returncode==0, f'{mode} capture must accept the observed control in its source state\n'+result.stderr[-2400:])
                observations=json.loads((dest/'observations.json').read_bytes())
                graph=json.loads((dest/(mode+'-graph.json')).read_bytes())
                states=observations['states']
                self.assertGreaterEqual(len(states),2)
                self.assertTrue(observations['transitions'])
                self.assertTrue(graph)
                for row in states:
                    self.assertTrue((dest/(row['id']+'.json')).is_file())
                pictures=list(dest.glob('*.png'))
                self.assertGreaterEqual(len({hashlib.sha256(p.read_bytes()).digest() for p in pictures}),2)
                return observations
            finally:
                server.shutdown()
                thread.join()

    def test_tabs_roundtrip_compiles_two_actual_states(self):
        obs=self.capture('tabs',TABS,['--tabs','#tabs','--panel','#panel','--click','Details','--click','Overview','--settle-ms','50'])
        self.assertEqual(len(obs['states']),2)
        self.assertEqual(len(obs['transitions']),2)

    def test_disclosure_open_close_switch_compiles_three_observed_states(self):
        obs=self.capture('disclosure',DISCLOSURE,['--accordion','#faq','--item','.item','--trigger','button','--content','[id^=answer]',
                         '--click','First question','--click','First question','--click','First question','--click','Second question','--settle-ms','50'])
        self.assertEqual(len(obs['states']),3)

    def test_carousel_autoplay_and_real_gesture_are_recorded(self):
        obs=self.capture('carousel',CAROUSEL,['--rail','#rail','--interval-ms','2600','--first-card','First class'])
        self.assertEqual(len(obs['states']),2)


if __name__=='__main__':
    unittest.main()
