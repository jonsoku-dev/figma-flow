#!/usr/bin/env python3
"""Bounded local commands for the single running Figma Flow plugin.

Uncertain writes require a successful scoped read before another write. For a
create-only or revised task, prepare a signed discover task for the original
file/page and run read; its actual getter reconciles the preserved receipt.
"""
import argparse
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

import figma_workspace as workspace

SCHEMA = 'figma-flow-control-v1'
MAX_BODY = 16 * 1024 * 1024
MAX_READBACK = 12 * 1024 * 1024
OPERATIONS = {'review': {'create'}, 'import': {'read', 'import', 'sync'},
              'discover': {'read'}, 'sync': {'read', 'apply'}, 'native-edit': {'read', 'apply'}}
TERMINAL = {'ok', 'error', 'uncertain', 'expired'}
ORIGINS = {'null', 'https://www.figma.com', 'https://figma.com'}
MAX_READINESS = 64 * 1024
READINESS_PROTOCOL = 'figma-flow-control-readiness-v1'
# Capture the implementation loaded by this process, even if installation files change later.
LOADED_VERSION = json.loads((Path(__file__).resolve().parents[1] / 'plugin.json').read_bytes())['version']
LOADED_IMPLEMENTATION = hashlib.sha256(Path(__file__).read_bytes() + b'\0' + Path(workspace.__file__).read_bytes()).hexdigest()


NATIVE_CLIENTS = {}


def native_state(root):
    catalogue = workspace.current(workspace.private_dir(root), repair=False)
    expected = catalogue.get('runtime')
    client = NATIVE_CLIENTS.get(str(Path(root).resolve()))
    observed = client['runtime'] if client and time.time() - client['seen_at'] <= 15 else None
    return {'expected_native': expected, 'observed_native': observed,
            'native_status': 'current-self-reported' if expected and expected == observed else 'unverified',
            'native_action': None if expected and expected == observed else 'Reopen the SAME registered Figma Flow plugin; then wait for its authenticated poll.'}


def readiness(root=None):
    return {'schema': SCHEMA, 'protocol': READINESS_PROTOCOL, 'version': LOADED_VERSION,
            **(native_state(root) if root is not None else {'expected_native': None, 'observed_native': None, 'native_status': 'unverified', 'native_action': 'Reopen the SAME registered Figma Flow plugin; then wait for its authenticated poll.'}),
            'implementation': LOADED_IMPLEMENTATION,
            'operations': {kind: sorted(operations) for kind, operations in OPERATIONS.items()}}


class ReadinessError(ValueError):
    pass


def require_ready(root, key, operation, file_key, page_id, revision, *, focus_page=False):
    root = workspace.private_dir(root)
    settings = config(root)
    row = task(root, {'key': key, 'operation': operation, 'file_key': file_key,
                      'page_id': page_id, 'revision': revision, 'focus_page': focus_page})
    repair = '; restart only this workspace\'s existing serve command using the current installed plugin root'
    connection = http.client.HTTPConnection('127.0.0.1', settings['port'], timeout=3)
    try:
        connection.request('POST', '/control/readiness', b'{}',
                           {'Host': f'localhost:{settings["port"]}', 'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + settings['token']})
        response = connection.getresponse()
        if response.status != 200:
            raise ReadinessError(f'Control readiness rejected (HTTP {response.status})' + repair)
        length = response.getheader('Content-Length')
        if length is not None and (not re.fullmatch(r'[0-9]{1,9}', length) or int(length) > MAX_READINESS):
            raise ReadinessError('Control readiness response is oversized or malformed' + repair)
        raw = response.read(MAX_READINESS + 1)
        if len(raw) > MAX_READINESS:
            raise ReadinessError('Control readiness response is oversized' + repair)
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise ReadinessError('Control readiness response is malformed' + repair) from None
        expected = readiness()
        if not isinstance(value, dict) or set(value) != set(expected):
            raise ReadinessError('Control readiness response has an unsupported format' + repair)
        if any(value[field] != expected[field] for field in ('schema', 'protocol', 'version', 'implementation')):
            raise ReadinessError('Control server loaded version or implementation differs from this CLI' + repair)
        capabilities = value['operations']
        if (not isinstance(capabilities, dict) or not all(isinstance(kind, str) and isinstance(operations, list)
                and all(isinstance(item, str) for item in operations) for kind, operations in capabilities.items())):
            raise ReadinessError('Control readiness capabilities are malformed' + repair)
        if operation != 'read' and (value.get('native_status') != 'current-self-reported' or
                not value.get('expected_native') or value['expected_native'] != value.get('observed_native') or
                value['expected_native'] != workspace.current(root, repair=False).get('runtime')):
            raise ReadinessError('Native plugin runtime is stale or unknown; reopen the SAME registered Figma Flow plugin')
        if operation not in capabilities.get(row['kind'], []):
            raise ReadinessError('Control server does not support the requested task kind and operation' + repair)
    except ConnectionRefusedError:
        raise ReadinessError('Control server is not running' + repair) from None
    except TimeoutError:
        raise ReadinessError('Control readiness timed out' + repair) from None
    except (OSError, http.client.HTTPException):
        raise ReadinessError('Control readiness connection failed' + repair) from None
    finally:
        connection.close()


def config(root):
    value = workspace.read(root / 'control.json', private=True, limit=4096)
    if set(value) != {'schema', 'port', 'token'} or value['schema'] != SCHEMA or not re.fullmatch(r'[a-f0-9]{64}', str(value['token'])):
        raise ValueError('Invalid private control configuration')
    workspace.checked_port(value['port'])
    return value


def state_dir(root):
    directory = workspace.private_dir(root / '.control', create=True)
    for name in ('requests', 'receipts', 'readbacks'):
        workspace.private_dir(directory / name, create=True)
    return directory


def identity(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError('Invalid ' + label)
    return value


def scope(file_key, page_id, revision):
    if not isinstance(file_key, str) or not re.fullmatch(r'[A-Za-z0-9]{1,128}', file_key):
        raise ValueError('Exact Figma file key required')
    if not isinstance(page_id, str) or not re.fullmatch(r'[0-9]+:[0-9]+', page_id):
        raise ValueError('Exact numeric Figma page ID required')
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision):
        raise ValueError('Exact task revision SHA256 required')


def task(root, request):
    catalogue = workspace.current(root)
    matches = [row for row in catalogue['tasks'] if row['key'] == request['key']]
    if len(matches) != 1 or matches[0]['revision'] != request['revision']:
        raise ValueError('Unknown or stale prepared task')
    row = matches[0]
    if request['operation'] not in OPERATIONS.get(row['kind'], set()):
        raise ValueError('Operation is not admitted for this task kind')
    for field, argument in (('fileKey', 'file_key'), ('pageId', 'page_id')):
        if row.get(field) is not None and row[field] != request[argument]:
            raise ValueError('Prepared task scope differs from command scope')
    if not isinstance(request.get('focus_page', False), bool):
        raise ValueError('Page focus must be an explicit boolean')
    if request.get('focus_page') and (row.get('fileKey') != request['file_key'] or row.get('pageId') != request['page_id']):
        raise ValueError('Page focus requires exact signed task file and page pins')
    bundle = workspace.task_artifacts(root, row)
    if request['operation'] == 'sync':
        # The existing compiler seals this capability into the generated import UI.
        if not (bundle / 'code.js').read_text(encoding='utf-8').startswith('const LOCAL_SYNC = '):
            raise ValueError('Import task has no paired app sync capability')
    return row


def save(directory, request):
    if request['state'] == 'uncertain' and request['operation'] != 'read':
        pending = uncertainties(directory)
        pending['operations'][request['id']] = request.copy()
        workspace.atomic(directory / 'uncertainty.json', workspace.encode(pending))
    workspace.atomic(directory / 'requests' / (request['id'] + '.json'), workspace.encode(request))
    if request['state'] in TERMINAL:
        workspace.atomic(directory / 'receipts' / (request['id'] + '.json'), workspace.encode(request))


def uncertainties(directory):
    path = directory / 'uncertainty.json'
    if path.exists():
        pending = workspace.read(path, private=True, limit=1_000_000)
        if pending.get('schema') != SCHEMA or not isinstance(pending.get('operations'), dict):
            raise ValueError('Invalid private uncertainty marker')
        return pending
    # Upgrade existing queues without losing uncertainty hidden by a later read.
    operations = {}
    for path in (directory / 'requests').glob('*.json'):
        request = workspace.read(path, private=True, limit=32768)
        if request.get('state') == 'uncertain' and request.get('operation') != 'read':
            operations[request['id']] = request
    pending = {'schema': SCHEMA, 'operations': operations}
    workspace.atomic(directory / 'uncertainty.json', workspace.encode(pending))
    return pending


def recovery_read(request, row, data, original):
    """A signed discovery of the original scope can recover create-only/revised tasks."""
    if request['operation'] != 'read' or any(request[field] != original[field] for field in ('file_key', 'page_id')):
        return False
    same_task = (request['key'], request['revision']) == (original['key'], original['revision'])
    scoped_discovery = (row['kind'] == 'discover' and row.get('fileKey') == original['file_key'] and row.get('pageId') == original['page_id'])
    if not (same_task or scoped_discovery) or data.get('error') or data.get('status') not in (None, 'ok', 'success') or data.get('rollback_conflicts'):
        return False
    if data.get('schema') == 'figma-flow-graph-native-discovery-v1':
        return (row['kind'] == 'discover' and data.get('fileKey') == original['file_key'] and data.get('pageId') == original['page_id']
                and isinstance(data.get('allowed_page_ids'), list) and original['page_id'] in data['allowed_page_ids']
                and all(isinstance(data.get(key), list) for key in ('nodes', 'variables', 'collections')))
    if data.get('schema') == 'figma-flow-graph-token-readback-v1':
        return (row['kind'] == 'sync' and data.get('operation') == 'inspect' and data.get('file_key') == original['file_key']
                and data.get('page_id') == original['page_id'] and all(isinstance(data.get(key), list) for key in ('tokens', 'components')))
    return (row['kind'] == 'import' and data.get('format') == 'figma-flow-readback-v1' and data.get('evidence') == 'observed-plugin-api-readback'
            and data.get('fileKey') == original['file_key'] and isinstance(data.get('pages'), list)
            and any(isinstance(page, dict) and page.get('id') == original['page_id'] for page in data['pages'])
            and all(isinstance(data.get(key), list) for key in ('variables', 'collections')))


def active(directory):
    path = directory / 'active.json'
    if not path.exists():
        return None
    pointer = workspace.read(path, private=True, limit=4096)
    operation_id = pointer.get('id')
    if not isinstance(operation_id, str) or not re.fullmatch(r'[a-f0-9]{32}', operation_id):
        raise ValueError('Invalid operation pointer')
    request = workspace.read(directory / 'requests' / (operation_id + '.json'), private=True, limit=32768)
    if request['state'] not in TERMINAL and time.time() >= request['deadline']:
        request.update(state='uncertain' if request['state'] == 'claimed' else 'expired', completed_at=time.time())
        save(directory, request)
    return request


def enable(root, port):
    port = workspace.checked_port(port)
    with workspace.locked(root) as root:
        workspace.current(root)
        state_dir(root)
        if (root / 'control.json').exists():
            value = config(root)
            if value['port'] != port:
                raise ValueError('Control is already enabled on another port')
        else:
            workspace.atomic(root / 'control.json', workspace.encode({'schema': SCHEMA, 'port': port, 'token': secrets.token_hex(32)}))
    return {'enabled': True, 'port': port, 'refresh_required': True}


def enqueue(root, key, operation, file_key, page_id, revision, timeout, *, focus_page=False):
    scope(file_key, page_id, revision)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise ValueError('Timeout must be between 1 and 3600 seconds')
    with workspace.locked(root) as root:
        config(root)
        directory = state_dir(root)
        previous = active(directory)
        if previous and previous['state'] not in TERMINAL:
            raise ValueError('An operation is already active; inspect its status')
        if uncertainties(directory)['operations'] and operation != 'read':
            raise ValueError('Previous claimed operation is uncertain; re-read the native state before starting another command')
        request = {'schema': SCHEMA, 'id': secrets.token_hex(16), 'key': key, 'operation': operation,
                   'file_key': file_key, 'page_id': page_id, 'revision': revision,
                   'focus_page': focus_page,
                   'created_at': time.time(), 'deadline': time.time() + timeout, 'state': 'pending'}
        task(root, request)
        save(directory, request)
        workspace.atomic(directory / 'active.json', workspace.encode({'id': request['id']}))
        return request


def poll(root, payload):
    if set(payload) not in ({'session_id', 'file_key', 'page_id'}, {'session_id', 'file_key', 'page_id', 'runtime'}):
        raise ValueError('Exact plugin poll fields required')
    runtime = payload.get('runtime')
    if runtime is not None and (not isinstance(runtime, dict) or set(runtime) != {'version', 'implementation', 'generation'} or
            not isinstance(runtime['version'], str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', runtime['version']) or
            not isinstance(runtime['implementation'], str) or not re.fullmatch(r'[a-f0-9]{64}', runtime['implementation']) or
            not isinstance(runtime['generation'], str) or not re.fullmatch(r'[a-f0-9]{32}', runtime['generation'])):
        raise ValueError('Invalid native runtime identity')
    session = identity(payload['session_id'], 'plugin session')
    scope(payload['file_key'], payload['page_id'], '0' * 64)
    with workspace.locked(root) as root:
        client_key = str(root.resolve())
        if len(NATIVE_CLIENTS) >= 256 and client_key not in NATIVE_CLIENTS:
            NATIVE_CLIENTS.pop(next(iter(NATIVE_CLIENTS)))
        NATIVE_CLIENTS[client_key] = {'runtime': runtime, 'session_id': session, 'seen_at': time.time()}
        native = native_state(root)
        directory = state_dir(root)
        request = active(directory)
        if not request or request['state'] != 'pending':
            return {'operation': None, **native}
        if request['operation'] != 'read' and native['native_status'] != 'current-self-reported':
            return {'operation': None, **native}
        if request['operation'] != 'read' and uncertainties(directory)['operations']:
            request.update(state='error', error='Previous mutation remains uncertain', completed_at=time.time())
            save(directory, request)
            return {'operation': None, **native}
        if request['file_key'] != payload['file_key'] or request['page_id'] != payload['page_id'] and not request.get('focus_page', False):
            return {'operation': None, **native}
        try:
            task(root, request)
        except ValueError:
            request.update(state='error', error='Prepared task changed before claim', completed_at=time.time())
            save(directory, request)
            return {'operation': None, **native}
        request.update(state='claimed', session_id=session, claim_id=secrets.token_hex(16), claimed_at=time.time())
        save(directory, request)
        return {**native, 'operation': {**{key: request[key] for key in ('id', 'claim_id', 'session_id', 'key', 'operation', 'file_key', 'page_id', 'revision', 'deadline')}, 'focus_page': request.get('focus_page', False)}}


def result(root, payload):
    required = {'id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision', 'status'}
    if not required <= set(payload) or set(payload) - required - {'readback_json', 'error'} or payload['status'] not in {'ok', 'error'}:
        raise ValueError('Exact plugin result fields required')
    raw = payload.get('readback_json')
    if raw is not None:
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_READBACK or not isinstance(json.loads(raw), dict):
            raise ValueError('Readback must be a bounded JSON object string')
    if payload.get('error') is not None and (not isinstance(payload['error'], str) or len(payload['error']) > 2000):
        raise ValueError('Invalid plugin error')
    with workspace.locked(root) as root:
        directory = state_dir(root)
        request = active(directory)
        if not request or request['state'] != 'claimed':
            raise ValueError('No current claim accepts this result')
        if any(payload[key] != request[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')):
            raise ValueError('Result claim or scope mismatch')
        try:
            row = task(root, request)
        except ValueError:
            request.update(state='uncertain', error='Prepared task changed after claim', completed_at=time.time())
            save(directory, request)
            raise ValueError('Prepared task changed after claim')
        if payload['status'] == 'ok' and raw is None:
            raise ValueError('Successful operation requires the actual native result JSON')
        if payload['status'] == 'ok' and request['operation'] == 'sync' and json.loads(raw).get('status') not in {'baseline', 'applied', 'unchanged'}:
            raise ValueError('Successful sync requires a native baseline, applied or unchanged result')
        if raw is not None:
            path = directory / 'readbacks' / (request['id'] + '.json')
            workspace.atomic(path, raw.encode('utf-8'))
            request['readback'] = str(path)
        request.update(state=payload['status'], completed_at=time.time(), evidence='authenticated-running-plugin-result; not independent origin authentication')
        if payload.get('error'):
            request['error'] = payload['error']
        pending = uncertainties(directory)
        recovered = [identity for identity, original in pending['operations'].items()
                     if payload['status'] == 'ok' and recovery_read(request, row, json.loads(raw), original)]
        if recovered:
            request['reconciles'] = recovered
        save(directory, request)
        if recovered:
            for identity in recovered:
                del pending['operations'][identity]
            workspace.atomic(directory / 'uncertainty.json', workspace.encode(pending))
        client = NATIVE_CLIENTS.get(str(root.resolve()))
        if (client and client.get('session_id') == payload['session_id'] and client.get('runtime')
                and client['runtime'] == workspace.current(root, repair=False).get('runtime')):
            client['seen_at'] = time.time()
        return {'accepted': True, 'id': request['id'], 'state': request['state']}


def status(root, operation_id=None):
    with workspace.locked(root) as root:
        directory = state_dir(root)
        current = active(directory)
        if operation_id is None:
            value = current or {'state': 'idle'}
        else:
            if not re.fullmatch(r'[a-f0-9]{32}', operation_id):
                raise ValueError('Invalid operation ID')
            value = current if current and current['id'] == operation_id else workspace.read(directory / 'requests' / (operation_id + '.json'), private=True, limit=32768)
        pending = uncertainties(directory)['operations']
        return {**value, 'uncertain_operations': [{key: original[key] for key in ('id', 'key', 'operation', 'file_key', 'page_id', 'revision')} for original in pending.values()]}


def pinned_operation_transitions(root, discovery_revision, mutation_revision, other_revision):
    """Replay the current enqueue, poll, result, timeout, and recovery transitions."""
    original_time = time.time
    native_started = False

    def note(value):
        nonlocal native_started
        if 'native-started' in json.dumps(value):
            native_started = True
        return value

    def claim_page(page_id, runtime=False):
        payload = {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': page_id}
        if runtime:
            payload['runtime'] = workspace.current(root)['runtime']
        return poll(root, payload)

    def finish(claim, raw):
        payload = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        payload.update(status='ok', readback_json=raw)
        return result(root, payload)

    def discovery(page_id):
        return json.dumps({'schema': 'figma-flow-graph-native-discovery-v1', 'fileKey': 'fixturefile', 'pageId': page_id,
                            'allowed_page_ids': [page_id], 'nodes': [], 'variables': [], 'collections': []})

    try:
        enqueue(root, 'discovery', 'read', 'fixturefile', '12:1', discovery_revision, 30)
        read = [note(status(root))['state']]
        claim = claim_page('12:1')['operation']
        read.append(note(status(root))['state'])
        finish(claim, '{"scope":"synthetic-test-only"}')
        read.append(note(status(root))['state'])

        request = enqueue(root, 'discovery', 'read', 'fixturefile', '12:1', discovery_revision, 1)
        time.time = lambda: request['deadline'] + 1
        timeout_before_claim = note(status(root))['state']
        time.time = original_time

        request = enqueue(root, 'discovery', 'read', 'fixturefile', '12:1', discovery_revision, 1)
        claim = claim_page('12:1')['operation']
        time.time = lambda: request['deadline'] + 1
        timeout_after_claim = note(status(root))['state']
        try:
            finish(claim, '{"scope":"synthetic-test-only"}')
            result_after_claimed_timeout = 'accepted'
        except ValueError:
            result_after_claimed_timeout = 'rejected'
        time.time = original_time
        try:
            enqueue(root, 'discovery', 'read', 'fixturefile', '12:1', discovery_revision, 30)
            read_claim_timeout_blocks_later_commands = False
            finish(claim_page('12:1')['operation'], '{"scope":"synthetic-test-only"}')
        except ValueError:
            read_claim_timeout_blocks_later_commands = True

        request = enqueue(root, 'mutation', 'apply', 'fixturefile', '12:1', mutation_revision, 1)
        claim_page('12:1', runtime=True)
        time.time = lambda: request['deadline'] + 1
        mutation_claim_timeout = note(status(root))['state']
        mutation_id = request['id']
        time.time = original_time
        try:
            enqueue(root, 'mutation', 'apply', 'fixturefile', '12:1', mutation_revision, 30)
            mutation_reenqueued_while_uncertain = 'allowed'
        except ValueError as error:
            mutation_reenqueued_while_uncertain = 'blocked' if 'uncertain' in str(error) else 'other'

        enqueue(root, 'other-page', 'read', 'fixturefile', '12:9', other_revision, 30)
        finish(claim_page('12:9', runtime=True)['operation'], discovery('12:9'))
        other_page_read_reconciles = note(status(root)).get('reconciles') == [mutation_id]

        enqueue(root, 'discovery', 'read', 'fixturefile', '12:1', discovery_revision, 30)
        recovery_claim = claim_page('12:1', runtime=True)['operation']
        finish(recovery_claim, discovery('12:1'))
        current = note(status(root))
        same_scope_discovery_reconciles = current.get('reconciles') == [mutation_id] and current['uncertain_operations'] == []
        try:
            finish(recovery_claim, discovery('12:1'))
            duplicate_terminal_result = 'accepted'
        except ValueError:
            duplicate_terminal_result = 'rejected'
    finally:
        time.time = original_time
    return {
        'schema': 'figma-flow-operation-transition-fixture-v1',
        'read': read,
        'timeout_before_claim': timeout_before_claim,
        'timeout_after_claim': timeout_after_claim,
        'result_after_claimed_timeout': result_after_claimed_timeout,
        'read_claim_timeout_blocks_later_commands': read_claim_timeout_blocks_later_commands,
        'mutation_claim_timeout': mutation_claim_timeout,
        'mutation_reenqueued_while_uncertain': mutation_reenqueued_while_uncertain,
        'other_page_read_reconciles': other_page_read_reconciles,
        'same_scope_discovery_reconciles': same_scope_discovery_reconciles,
        'duplicate_terminal_result': duplicate_terminal_result,
        'native_started': native_started,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, code, value):
        body = workspace.encode(value)
        self.send_response(code)
        origin = self.headers.get('Origin')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'POST')
            if self.headers.get('Access-Control-Request-Private-Network') == 'true':
                self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        return (self.path in {'/control/poll', '/control/result', '/control/readiness'} and self.headers.get('Host') == f'localhost:{self.server.server_port}'
                and self.headers.get('Origin') in ORIGINS | {None})

    def do_OPTIONS(self):
        self.reply(200 if self.allowed() else 403, {})

    def do_POST(self):
        self.connection.settimeout(15)
        if not self.allowed() or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.token):
            return self.reply(403, {'error': 'Control authentication or endpoint rejected'})
        length = self.headers.get('Content-Length', '')
        if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json' or not re.fullmatch(r'[0-9]{1,9}', length) or not 0 < int(length) <= MAX_BODY:
            return self.reply(413, {'error': 'Invalid control request body'})
        try:
            payload = json.loads(self.rfile.read(int(length)))
            if not isinstance(payload, dict):
                raise ValueError('Object required')
            if self.path == '/control/readiness':
                if payload:
                    raise ValueError('Exact empty readiness object required')
                value = readiness(self.server.workspace)
            else:
                value = poll(self.server.workspace, payload) if self.path == '/control/poll' else result(self.server.workspace, payload)
        except (ValueError, KeyError, TypeError, OSError):
            return self.reply(409, {'error': 'Control request rejected; inspect private operation status'})
        self.reply(200, value)


def serve(root):
    root = workspace.private_dir(root)
    with workspace.locked(root):
        workspace.current(root)
        value = config(root)
        directory = state_dir(root)
    fd = os.open(directory / 'server.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as lock:
        if os.fstat(lock.fileno()).st_mode & 0o077 or os.fstat(lock.fileno()).st_uid != os.getuid():
            raise ValueError('Control server lock must be owner-only')
        workspace.fcntl.flock(lock, workspace.fcntl.LOCK_EX | workspace.fcntl.LOCK_NB)
        with ThreadingHTTPServer(('127.0.0.1', value['port']), Handler) as server:
            server.workspace, server.token = root, value['token']
            print(json.dumps({'serving': True, 'port': value['port']}), flush=True)
            server.serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('enable', 'serve', 'run', 'status'):
        command = commands.add_parser(name)
        command.add_argument('--workspace', type=Path, required=True)
        if name == 'enable':
            command.add_argument('--port', type=int, required=True)
        elif name == 'status':
            command.add_argument('--id')
        elif name == 'run':
            for field in ('key', 'file-key', 'page-id', 'expected-revision'):
                command.add_argument('--' + field, required=True)
            command.add_argument('--operation', choices=sorted(set.union(*OPERATIONS.values())), required=True)
            command.add_argument('--timeout', type=float, default=120)
            command.add_argument('--no-wait', action='store_true', help='Return after queueing on a compatible running server')
            command.add_argument('--focus-page', action='store_true', help='Focus the exact signed task page within the current file')
    args = parser.parse_args(argv)
    try:
        if args.command == 'enable':
            value = enable(args.workspace, args.port)
        elif args.command == 'serve':
            serve(args.workspace)
            return 0
        elif args.command == 'status':
            value = status(args.workspace, args.id)
        else:
            require_ready(args.workspace, args.key, args.operation, args.file_key, args.page_id, args.expected_revision, focus_page=args.focus_page)
            value = enqueue(args.workspace, args.key, args.operation, args.file_key, args.page_id, args.expected_revision, args.timeout, focus_page=args.focus_page)
            if not args.no_wait:
                while value['state'] not in TERMINAL:
                    time.sleep(min(.2, max(.01, value['deadline'] - time.time())))
                    value = status(args.workspace, value['id'])
        print(json.dumps(value, ensure_ascii=True, allow_nan=False))
        return 2 if value.get('state') in {'error', 'uncertain', 'expired'} else 0
    except ReadinessError as error:
        print('figma-control: ' + str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError):
        print('figma-control: rejected; inspect private configuration, task revision, scope and operation status', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
