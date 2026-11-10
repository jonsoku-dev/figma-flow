#!/usr/bin/env python3
"""Run the paired Figma Desktop button and review-cards preview on loopback."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading

from figma_bridge import compile_plugin
import design_directions
from promote_idea import require_selection
from workflow import Event
from figma_sync_session import SyncSession
from serve_ideas import snapshot_app
from figma_live_preview import start_preview, update_preview

MAX_BODY = 2_000_000
ORIGINS = {'null', 'https://www.figma.com', 'https://figma.com'}


class SyncHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        print(f'Local sync {self.command} {status}', flush=True)
        self.send_response(status)
        origin = self.headers.get('Origin')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'POST')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
            if self.headers.get('Access-Control-Request-Private-Network') == 'true':
                self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if self.path != '/sync' or self.headers.get('Host') != self.server.host:
            self.reply(404, {'error': 'Unknown local endpoint.'})
            return False
        if self.headers.get('Origin') not in ORIGINS | {None}:
            self.reply(403, {'error': 'Unrecognized request origin.'})
            return False
        return True

    def do_OPTIONS(self):
        if self.allowed():
            self.reply(200, {})

    def do_POST(self):
        if not self.allowed():
            return
        auth = self.headers.get('Authorization', '').encode('utf-8')
        if not hmac.compare_digest(auth, self.server.auth):
            return self.reply(403, {'error': '페어링된 개발 플러그인에서 요청하세요.'})
        if self.headers.get_content_type() != 'application/json':
            return self.reply(415, {'error': 'Expected application/json.'})
        length = self.headers.get('Content-Length', '')
        if self.headers.get('Transfer-Encoding') or not re.fullmatch(r'[0-9]{1,8}', length) or not 0 < int(length) <= MAX_BODY:
            return self.reply(413, {'error': 'Invalid or oversized request.'})
        try:
            body = json.loads(self.rfile.read(int(length)))
            if not isinstance(body, dict) or set(body) != {'file_key', 'page_id', 'readback'}:
                raise ValueError('Expected the paired native snapshot.')
            if (body['file_key'], body['page_id']) != (self.server.file_key, self.server.page_id):
                raise ValueError('Figma file or page differs from the paired project.')
            data = body['readback']
            if not isinstance(data, dict) or data.get('evidence') != 'observed-plugin-api-readback' or data.get('scope') != 'paired-active-import-page':
                raise ValueError('Expected the active native import page.')
            if not isinstance(data.get('pages'), list) or len(data['pages']) != 1 or data['pages'][0].get('id') != body['page_id']:
                raise ValueError('Unexpected page in native readback.')
            with self.server.apply_lock:
                prior = self.server.session.last_comparison()
                previous = (prior[0], snapshot_app(self.server.session.project)) if prior is not None else None
                result = self.server.session.sync(data)
                try:
                    update_preview(self.server.preview, data, body['page_id'], result, previous=previous)
                    result = dict(result, preview_url=self.server.preview_url)
                except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                    result = dict(result, preview_error=f'앱 비교 화면 준비 실패: {exc}')
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, RecursionError) as exc:
            return self.reply(409, {'error': str(exc)})
        self.reply(200, result)


def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError('Use a dedicated private local state directory (permissions 0700).')


def run(project, resolved, page_id, file_key, plugin_id, state_dir, prior_sync=None, *, selection_path=None, batch_path=None, asset_receipts=None):
    project = project.resolve(strict=True)
    state_dir = state_dir.absolute()
    if state_dir.resolve().is_relative_to(project):
        raise ValueError('Keep the paired plugin and session outside your project.')
    if not re.fullmatch(r'[A-Za-z0-9]+', file_key) or not re.fullmatch(r'[0-9]+:[0-9]+', page_id):
        raise ValueError('Expected the Figma file key and numeric native page ID.')
    if not re.fullmatch(r'[0-9]+', plugin_id):
        raise ValueError('Expected a Figma-assigned numeric plugin ID.')
    if selection_path:
        design_directions.require_selected(selection_path, project)
        require_selection({'design_intent': 'create'}, project / 'graph.json', selection_path, project / 'brief.md')
        design_directions.guard_production(selection_path, event=Event.HANDOFF_NATIVE,
            product_graph=project / 'graph.json', batch_path=batch_path, asset_receipts=asset_receipts)
    elif batch_path or asset_receipts:
        raise ValueError('Asset receipts require a selected new-design import; existing-page sync stays sealed.')
    private_dir(state_dir)
    state_dir = state_dir.resolve()
    registry = state_dir / 'connection.json'
    expected = {'project': str(project), 'resolved_sha256': hashlib.sha256(resolved.read_bytes()).hexdigest(),
                'file_key': file_key, 'page_id': page_id, 'plugin_id': plugin_id}
    with ExitStack() as stack:
        lock = stack.enter_context((state_dir / 'server.lock').open('a+b'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            running = json.loads(registry.read_text()) if registry.exists() else None
            if not running or running.get('identity') != expected:
                raise ValueError('A different helper already owns this private directory.')
            print(f"이미 실행 중입니다. 비교 화면: http://localhost:{running['preview_port']}/", flush=True)
            return
        saved = json.loads(registry.read_text()) if registry.exists() else None
        if saved is not None and saved['identity'] != expected:
            raise ValueError('This state directory belongs to a different file or project.')
        session = SyncSession(project, resolved, page_id, state_dir / 'session', prior_sync)
        preview = start_preview(project, port=saved['preview_port'] if saved else 0)
        stack.callback(preview.server_close)
        stack.callback(preview.shutdown)
        last = session.last_comparison()
        if last is not None:
            readback, previous_result = last
            update_preview(preview, readback, page_id, previous_result)
        http = stack.enter_context(ThreadingHTTPServer(('127.0.0.1', saved['sync_port'] if saved else 0), SyncHandler))
        http.host = f'localhost:{http.server_port}'
        http.preview_url = f'http://localhost:{preview.server_port}/'
        token = saved['token'] if saved else secrets.token_hex(32)
        config = {'url': f'http://{http.host}/sync', 'preview_url': http.preview_url,
                  'file_key': file_key, 'page_id': page_id, 'token': token}
        if saved is None:
            connection = dict(identity=expected, sync_port=http.server_port, preview_port=preview.server_port, token=token)
            temporary = registry.with_suffix('.tmp')
            temporary.write_text(json.dumps(connection)+'\n')
            os.chmod(temporary, 0o600)
            os.replace(temporary, registry)
        plugin = state_dir / 'plugin'
        # Compare a fresh compile on resume; never silently replace a registered plugin someone edited.
        with tempfile.TemporaryDirectory(dir=state_dir) as temp:
            build = Path(temp) / 'plugin'
            compile_plugin(resolved, expected['resolved_sha256'], build, plugin_id, local_sync=config, selection_path=selection_path, technical_existing=selection_path is None, product_graph=project / 'graph.json' if selection_path else None, batch_path=batch_path, asset_receipts=asset_receipts)
            if plugin.exists():
                for source in build.iterdir():
                    target = plugin / source.name
                    if target.is_symlink() or not target.is_file() or target.read_bytes() != source.read_bytes():
                        raise ValueError('Paired plugin differs from this build. Use a fresh state directory to upgrade.')
            else:
                os.replace(build, plugin)
        http.session, http.preview, http.file_key, http.page_id = session, preview, file_key, page_id
        http.auth = ('Bearer ' + token).encode('ascii')
        http.apply_lock = threading.Lock()
        print(f'Figma Desktop manifest: {plugin / "manifest.json"}\n비교 화면: {http.preview_url}', flush=True)
        http.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'resolved', 'state-dir'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('page-id', 'file-key', 'plugin-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--selection', type=Path, help='current user selection for UI import; omitted means existing-page sync only')
    parser.add_argument('--batch', type=Path, help='exact frozen asset batch for selected new-design import')
    parser.add_argument('--asset-receipts', type=Path, help='current returned generated assets for that batch')
    parser.add_argument('--prior-sync', type=Path, help='existing 0.7.0 applied run, for the first setup')
    args = parser.parse_args()
    try:
        run(args.project, args.resolved, args.page_id, args.file_key, args.plugin_id, args.state_dir, args.prior_sync, selection_path=args.selection, batch_path=args.batch, asset_receipts=args.asset_receipts)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        parser.exit(1, f'figma-sync: {error}\n')
