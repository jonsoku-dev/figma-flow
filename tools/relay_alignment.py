#!/usr/bin/env python3
"""Render a synthetic host around the built relay and run the shared alignment audit."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from plugin_panel import render_app


FIXTURE = {
    'type': 'workspace-relay-viewer-state',
    'workspaceSession': 'alignment-fixture',
    'status': 'live',
    'locale': 'ko',
    'file': {'key': 'alignment-file', 'name': '예약 흐름 설계'},
    'page': {'id': '2:3', 'name': '모바일 화면'},
    'selection': [
        {'id': '4:5', 'name': '예약 카드', 'type': 'FRAME'},
        {'id': '4:6', 'name': '확인 버튼', 'type': 'INSTANCE'},
    ],
}

HOST_BRIDGE = f"""<script>
window.addEventListener('message', event => {{
  const request = event.data?.pluginMessage;
  if (request?.type !== 'workspace-home-ready') return;
  window.postMessage({{pluginMessage:{{...{json.dumps(FIXTURE, ensure_ascii=False)}, requestId:request.requestId}}}}, '*');
}});
const openSelection = () => {{
  const details = document.querySelector('.relay-footer details');
  const rows = document.querySelectorAll('.relay-layers tbody tr');
  if (details && rows.length === 2) {{
    details.open = true;
    document.documentElement.dataset.relayAlignmentReady = 'true';
    return true;
  }}
  return false;
}};
new MutationObserver(openSelection).observe(document.documentElement, {{childList:true,subtree:true}});
document.addEventListener('DOMContentLoaded', openSelection);
</script>"""


class FixtureHandler(BaseHTTPRequestHandler):
    document = ''
    external_requests = []

    def do_GET(self):
        if self.path != '/':
            type(self).external_requests.append(self.path)
            self.send_error(404)
            return
        body = type(self).document.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:")
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='new directory for report and screenshots')
    parser.add_argument('--widths', default='320,400', help='comma-separated viewport widths')
    parser.add_argument('--height', default='420', help='viewport height in CSS pixels')
    parser.add_argument('--chrome', help='Chromium executable (defaults to tools/chromium_pipe.mjs detection)')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error(f'output directory must not already exist: {out}')

    document = render_app('relay')
    document = document.replace('</head>', '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; font-src data:\">\n</head>')
    document = document.replace('<body class="panel react-panel">', '<body class="panel react-panel">' + HOST_BRIDGE, 1)
    FixtureHandler.document = document
    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        command = [
            'node', str(ROOT / 'tools/alignment_audit.mjs'),
            '--url', f'http://127.0.0.1:{server.server_port}/',
            '--rules', str(ROOT / 'tools/relay_alignment_rules.json'),
            '--out', str(out), '--widths', args.widths, '--height', args.height,
        ]
        if args.chrome:
            command.extend(['--chrome', args.chrome])
        result = subprocess.run(command, cwd=ROOT, check=False)
        if FixtureHandler.external_requests:
            print('Fixture received unexpected requests: ' + ', '.join(FixtureHandler.external_requests), file=sys.stderr)
            return 2
        if (out / 'report.json').exists():
            print(f'Report: {out / "report.json"}')
        return result.returncode
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    raise SystemExit(main())
