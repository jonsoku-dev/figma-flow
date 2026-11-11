#!/usr/bin/env python3
"""Explicit, authenticated loopback actions for registered workspace Codex chats."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid

import figma_workspace

MAX_BODY = 100_000
ORIGINS = {'null', 'https://www.figma.com', 'https://figma.com'}


def read_private(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a private workspace file.')
    if os.name != 'nt' and path.stat().st_mode & 0o077:
        raise ValueError('Workspace files must have private permissions (0600).')
    if path.stat().st_size > 4_000_000:
        raise ValueError('Workspace file is too large.')
    return json.loads(path.read_text(encoding='utf-8'))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate request field.')
        result[key] = value
    return result


class ChatHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def reply(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
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
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if self.path not in {'/chat/open', '/chat/queue'} or self.headers.get_all('Host') != [self.server.host]:
            self.reply(404, {'error': 'Unknown local endpoint.'})
            return False
        if len(self.headers.get_all('Origin', [])) > 1 or self.headers.get('Origin') not in ORIGINS | {None}:
            self.reply(403, {'error': 'Unrecognized request origin.'})
            return False
        return True

    def do_OPTIONS(self):
        if self.allowed():
            self.reply(200, {})

    def do_POST(self):
        if not self.allowed():
            return
        side_effects_possible = False
        try:
            config = read_private(self.server.workspace / 'chat.json')
            expected_auth = 'Bearer ' + config['token']
            if config != self.server.config or self.headers.get_all('Authorization') != [self.headers.get('Authorization')]:
                raise ValueError('Workspace chat configuration changed.')
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(), expected_auth.encode()):
                return self.reply(403, {'error': 'Workspace authorization required.'})
            if self.headers.get_content_type() != 'application/json':
                return self.reply(415, {'error': 'Expected application/json.'})
            lengths = self.headers.get_all('Content-Length', [])
            if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,6}', lengths[0]) or not 0 < int(lengths[0]) <= MAX_BODY:
                return self.reply(413, {'error': 'Invalid or oversized request.'})
            data = json.loads(self.rfile.read(int(lengths[0])), object_pairs_hook=unique_object)
            required = {'key', 'threadId', 'revision', 'requestId'}
            queue = self.path == '/chat/queue'
            if not isinstance(data, dict) or set(data) != required | ({'text'} if queue else set()):
                raise ValueError('Unexpected request fields.')
            if any(not isinstance(value, str) for value in data.values()):
                raise ValueError('Expected string request fields.')
            if str(uuid.UUID(data['threadId'])) != data['threadId'] or str(uuid.UUID(data['requestId'])) != data['requestId']:
                raise ValueError('Expected canonical UUIDs.')
            if not re.fullmatch(r'[0-9a-f]{64}', data['revision']) or not 0 < len(data['key']) <= 200:
                raise ValueError('Invalid task identity.')
            if queue and (not data['text'].strip() or '\x00' in data['text'] or len(data['text'].encode('utf-8')) > 64_000):
                raise ValueError('Expected bounded reviewed text.')
            with self.server.action_lock, figma_workspace.locked(self.server.workspace) as workspace:
                catalogue = figma_workspace.current(workspace)
                tasks = catalogue['tasks']
                matches = [task for task in tasks if task.get('key') == data['key']]
                if catalogue.get('schema') != figma_workspace.SCHEMA or len(matches) != 1 or any(matches[0].get(field) != data[field] for field in ('threadId', 'revision')):
                    raise ValueError('Task, revision or chat differs from the current workspace registry.')
                status, result = self.server.perform(self.path, data)
                side_effects_possible = result.get('status') in {'queued', 'opened', 'uncertain'}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, RuntimeError):
            if side_effects_possible:
                status, result = 504, {'status': 'uncertain', 'error': 'Action outcome is uncertain. Check the originating chat before creating another request.'}
            else:
                status, result = 409, {'error': 'Invalid request or private workspace state; no action was started.'}
        self.reply(status, result)


class ChatServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, workspace, *, cli=None, timeout=15, port=None):
        self.workspace = figma_workspace.private_dir(workspace)
        self.config = read_private(self.workspace / 'chat.json')
        if set(self.config) != {'schema', 'port', 'token'} or self.config['schema'] != 'figma-flow-workspace-chat-v1' or type(self.config['port']) is not int or not 1024 <= self.config['port'] <= 65535 or not isinstance(self.config['token'], str) or not re.fullmatch(r'[0-9a-f]{64}', self.config['token']):
            raise ValueError('Invalid workspace chat configuration.')
        self.cli = cli or shutil.which('codex')
        self.action_timeout = timeout
        self.action_lock = threading.Lock()
        super().__init__(('127.0.0.1', self.config['port'] if port is None else port), ChatHandler)
        self.host = f'localhost:{self.server_port}'

    def perform(self, endpoint, data):
        ledger_path = self.workspace / 'chat-requests.json'
        ledger = read_private(ledger_path) if ledger_path.exists() else {}
        fingerprint = hashlib.sha256(json.dumps([endpoint, data], sort_keys=True).encode()).hexdigest()
        request_id = data['requestId']
        if request_id in ledger:
            prior = ledger[request_id]
            if prior['fingerprint'] != fingerprint:
                return 409, {'error': 'Request ID already used for another action.'}
            return 409, dict(prior['result'], replayed=True)
        if len(ledger) >= 10_000:
            return 409, {'error': 'Request ledger is full; no action was started.'}
        if endpoint == '/chat/queue' and not self.cli:
            return 503, {'error': 'Official Codex CLI was not found on PATH; no action was started.'}
        if endpoint == '/chat/queue' and sys.platform == 'win32' and not self.cli.lower().endswith('.exe'):
            return 503, {'error': 'Use the official native codex.exe on PATH; Windows batch wrappers cannot preserve literal text safely.'}
        if endpoint == '/chat/open' and sys.platform != 'darwin' and sys.platform != 'win32':
            return 503, {'error': 'Opening Codex chats is supported on macOS and Windows.'}
        uncertain = {'status': 'uncertain', 'error': 'Delivery is uncertain. Check the originating chat before creating another request.'}
        ledger[request_id] = {'fingerprint': fingerprint, 'result': uncertain}
        self.save_ledger(ledger_path, ledger)
        try:
            if endpoint == '/chat/queue':
                subprocess.run([self.cli, 'queue', '--thread', data['threadId'], '--message=' + data['text']],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=self.action_timeout, check=True, shell=False)
                result = {'status': 'queued', 'consumed': False}
            else:
                uri = 'codex://threads/' + data['threadId']
                if sys.platform == 'win32':
                    os.startfile(uri)
                else:
                    subprocess.run(['/usr/bin/open', uri], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=self.action_timeout, check=True, shell=False)
                result = {'status': 'opened'}
            ledger[request_id]['result'] = result
            self.save_ledger(ledger_path, ledger)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, RuntimeError, subprocess.SubprocessError):
            # The durable claim remains uncertain if the command or final receipt fails.
            return 504, uncertain
        return 200, result

    @staticmethod
    def save_ledger(path, ledger):
        fd, temporary_name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(ledger, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    try:
        with ChatServer(args.workspace) as server:
            print(f'Workspace chat relay: http://{server.host}', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(1, 'workspace-chat: Could not start the private workspace relay.\n')


if __name__ == '__main__':
    main()
