#!/usr/bin/env python3
"""Serve a read-only, offline design-routing planner on IPv4 loopback."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

import campaign_library
import route_design

MAX_BODY = 131072
MAX_TEXT = 16000
HTML = Path(__file__).with_name('design-routes.html')


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        pass  # Prompts and request paths are never logged.

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.wfile.write(data)

    def local_request(self):
        authority = f'127.0.0.1:{self.server.server_port}'
        if (self.headers.get_all('Host') != [authority]
                or self.headers.get('Origin') not in (None, 'http://' + authority)
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.reply(403, {'error': '이 로컬 페이지에서만 요청할 수 있습니다.'})
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        if self.path != '/':
            self.reply(404, {'error': '경로를 찾을 수 없습니다.'})
            return
        self.reply(200, self.server.html, 'text/html; charset=utf-8')

    def do_POST(self):
        if not self.local_request():
            return
        if self.path != '/plan':
            self.reply(404, {'error': '경로를 찾을 수 없습니다.'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.reply(415, {'error': 'application/json 요청이 필요합니다.'})
            return
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            self.reply(400, {'error': '유효한 Content-Length가 필요합니다.'})
            return
        if len(lengths[0]) > 6:
            self.reply(413, {'error': '요청 크기 제한을 초과했습니다.'})
            return
        size = int(lengths[0])
        if not 0 < size <= MAX_BODY:
            self.reply(413, {'error': '요청 크기 제한을 초과했습니다.'})
            return
        try:
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError('Incomplete request')
            payload = json.loads(body.decode('utf-8'))
            if not isinstance(payload, dict) or set(payload) - {'prompt', 'context'}:
                raise ValueError('Unknown fields')
            prompt, context = payload.get('prompt'), payload.get('context')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_TEXT:
                raise ValueError('Invalid prompt')
            if context is not None and (not isinstance(context, str) or len(context) > MAX_TEXT):
                raise ValueError('Invalid context')
            prompt.encode('utf-8')  # A lone surrogate raises UnicodeEncodeError -> 400, not a dropped connection.
            if context is not None:
                context.encode('utf-8')
            result = route_design.route(prompt, registry=self.server.registry,
                                        campaign_data=self.server.campaign_data, context=context)
        except (ValueError, UnicodeError):
            self.reply(400, {'error': f'프롬프트와 선택 맥락은 각각 {MAX_TEXT:,}자 이내의 텍스트여야 합니다.'})
            return
        self.reply(200, result)


def create_server(port=0):
    registry = route_design.load_registry()
    campaign_data = campaign_library.load_library(campaign_library.DEFAULT_DATA)
    html = HTML.read_bytes()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.registry, server.campaign_data, server.html = registry, campaign_data, html
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0, help='Loopback port; 0 selects an available port')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    with create_server(args.port) as server:
        print(f'디자인 라우팅: http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
