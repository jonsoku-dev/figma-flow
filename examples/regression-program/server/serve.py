#!/usr/bin/env python3
"""Serve the exploratory regression apps and their mock API."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import mock_api

ROOT = Path(__file__).resolve().parents[1]
APPS = {'atlas': ROOT / 'atlas/app/index.html', 'morrow': ROOT / 'morrow/app/index.html', 'paper': ROOT / 'paper/app/index.html'}
TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.md': 'text/plain; charset=utf-8'}


def _safe(url_path):
    path = unquote(urlsplit(url_path).path)
    if '\\' in path or '\x00' in path:
        return None
    parts = [part for part in path.split('/') if part not in ('', '.')]
    if any(part == '..' for part in parts):
        return None
    current = ROOT
    for part in parts:
        current = current / part
        if current.is_symlink():
            return None
    resolved = current.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        return None
    return current


class Handler(BaseHTTPRequestHandler):
    server_version = 'RegressionMock/1.0'

    def log_message(self, fmt, *args):
        return

    def _send(self, status, body, content_type='application/json; charset=utf-8'):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('content-type', content_type)
        self.send_header('content-length', str(len(raw)))
        self.send_header('cache-control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if urlsplit(self.path).path == '/api/health':
            self._send(200, {'ok': True, 'seed': 20261111, 'scope': 'exploratory'})
            return
        target = _safe(self.path)
        if target is not None and target.is_file():
            self._send(200, target.read_bytes(), TYPES.get(target.suffix, 'application/octet-stream'))
            return
        parts = [part for part in urlsplit(self.path).path.split('/') if part]
        if parts and parts[0] in APPS:
            self._send(200, APPS[parts[0]].read_bytes(), TYPES['.html'])
            return
        self._send(404, {'ok': False, 'error': 'not-found'})

    def do_POST(self):
        length = int(self.headers.get('content-length', '0') or '0')
        if length < 0 or length > 100_000:
            self._send(413, {'ok': False, 'error': 'payload-too-large'})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode())
            status, body = mock_api.handle(urlsplit(self.path).path, payload)
        except (UnicodeError, json.JSONDecodeError):
            self._send(400, {'ok': False, 'error': 'invalid-json'})
            return
        except ValueError:
            self._send(404, {'ok': False, 'error': 'unknown-api'})
            return
        self._send(status, body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'LISTENING {server.server_address[1]}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
