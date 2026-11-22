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
import threading
import time

import figma_workspace as workspace
import operation_detail as detail_projection
import relay_view
import relay_limits
import change_journal

CAROUSEL_OPERATIONS = frozenset({'carousel-select', 'carousel-present'})
SCHEMA = 'figma-flow-control-v1'
NON_CANVAS_OPERATIONS = {'native-summary', *relay_view.OPERATIONS, *CAROUSEL_OPERATIONS}
READ_ONLY_OPERATIONS = {'read', *NON_CANVAS_OPERATIONS}
TERMINAL = {'ok', 'error', 'uncertain', 'expired'}
ORIGINS = {'null', 'https://www.figma.com', 'https://figma.com'}
READINESS_PROTOCOL = 'figma-flow-control-readiness-v1'


def operation_options(operation, options):
    if operation in relay_view.OPERATIONS:
        return relay_view.validate_options(operation, options)
    if operation in CAROUSEL_OPERATIONS:
        if not isinstance(options, dict) or set(options) != {'execution_id', 'state_id'}:
            raise ValueError('Carousel operation requires its readback execution and state IDs')
        if not isinstance(options['execution_id'], str) or not re.fullmatch(r'[a-z0-9-]{1,80}', options['execution_id']):
            raise ValueError('Invalid carousel readback execution ID')
        if not isinstance(options['state_id'], str) or not re.fullmatch(r'[^\x00-\x1f]{1,128}', options['state_id']):
            raise ValueError('Invalid carousel state ID')
        return dict(options)
    if options is not None:
        raise ValueError('Operation options are not admitted for this operation')
    return None
# Capture the implementation loaded by this process, even if installation files change later.
LOADED_VERSION = json.loads((Path(__file__).resolve().parents[1] / 'plugin.json').read_bytes())['version']
PROFILE_POLICY_PATH = Path(__file__).resolve().parents[1] / 'library' / 'figma-profile' / 'policy.json'
PROFILE_POLICY = json.loads(PROFILE_POLICY_PATH.read_bytes())
TRANSPORT = relay_limits.control_transport(PROFILE_POLICY)
MAX_BODY = TRANSPORT['normal']['bodyBytes']
MAX_READBACK = TRANSPORT['normal']['readbackBytes']
MAX_LARGE_READ_BODY = TRANSPORT['largeRead']['bodyBytes']
MAX_LARGE_READBACK = TRANSPORT['largeRead']['readbackBytes']
MAX_READINESS = TRANSPORT['readinessReplyBytes']
OPERATIONS = {kind: set(actions) for kind, actions in PROFILE_POLICY['taskOperations'].items()}
LOADED_IMPLEMENTATION = hashlib.sha256(
    Path(__file__).read_bytes()
    + b'\0' + Path(workspace.__file__).read_bytes()
    + b'\0' + Path(detail_projection.__file__).read_bytes()
    + b'\0' + Path(relay_view.__file__).read_bytes()
    + b'\0' + Path(change_journal.__file__).read_bytes()
    + b'\0' + PROFILE_POLICY_PATH.read_bytes()
    + b'\0' + Path(relay_limits.__file__).read_bytes()
    + b'\0' + (relay_limits.ROOT / relay_limits.LIMITS_FILE).read_bytes()
).hexdigest()


NATIVE_CLIENTS = {}
CHANGE_CLIENTS = {}
CHANGE_CLIENTS_LOCK = threading.Lock()
RELAY_STATES = {}
RELAY_LOCK = threading.RLock()
RELAY_TTL = 15
RELAY_REQUEST_TTL = 120
PROFILE_PLANS = set(PROFILE_POLICY['options']['plans'])
PROFILE_SEATS = set(PROFILE_POLICY['options']['seats'])
PROFILE_ERROR_CODES = {'profile-save-failed', 'profile-storage-unavailable'}


def context_fingerprint(context):
    scope_value = {key: context.get(key) for key in ('session_id', 'file_key', 'page_id', 'user_id',
                                                        'native_status', 'native_session_matches',
                                                        'native_generation', 'expected_generation')}
    return hashlib.sha256(workspace.encode(scope_value)).hexdigest()


def _cli_context(root, context):
    status = native_state(root)
    client = NATIVE_CLIENTS.get(_relay_key(root))
    session_matches = bool(client and client.get('session_id') == context.get('session_id') and
                           time.time() - client.get('seen_at', 0) <= RELAY_TTL)
    observed = status.get('observed_native') or {}
    expected = status.get('expected_native') or {}
    native_status_value = status['native_status'] if session_matches else 'unverified'
    return {**context, 'native_status': native_status_value, 'native_session_matches': session_matches,
            'native_generation': observed.get('generation'), 'expected_generation': expected.get('generation')}


def _validate_profile_projection(profile):
    if profile is None:
        return
    required = {'declared', 'needsSetup', 'storage'}
    allowed = required | {'capabilities'}
    if (not isinstance(profile, dict) or set(profile) - allowed or not required <= set(profile) or
            not isinstance(profile.get('declared'), dict) or set(profile['declared']) != {'plan', 'seat'} or
            profile['declared'].get('plan') not in PROFILE_PLANS or profile['declared'].get('seat') not in PROFILE_SEATS or
            not isinstance(profile['needsSetup'], bool) or profile['storage'] not in {'local', 'session'}):
        raise ValueError('Invalid profile projection')
    capabilities = profile.get('capabilities')
    if capabilities is not None and (not isinstance(capabilities, dict) or
            set(capabilities) != set(PROFILE_POLICY['capabilities']) or
            any(not isinstance(value, bool) for value in capabilities.values())):
        raise ValueError('Invalid profile capabilities')


def _relay_key(root):
    return str(Path(root).resolve())


def _relay_state(root):
    key = _relay_key(root)
    now = time.time()
    state = RELAY_STATES.get(key)
    if state is None:
        if len(RELAY_STATES) >= 128:
            oldest = min(RELAY_STATES, key=lambda item: RELAY_STATES[item].get('touched_at', 0))
            RELAY_STATES.pop(oldest, None)
        state = {'context': None, 'requests': {}, 'active': None}
        RELAY_STATES[key] = state
    state['touched_at'] = now
    requests = state['requests']
    for request_id, request in list(requests.items()):
        if request['state'] != 'pending' and now - request.get('completed_at', now) > RELAY_REQUEST_TTL:
            requests.pop(request_id, None)
    if len(requests) > 64:
        for request_id, request in sorted(requests.items(), key=lambda item: item[1].get('created_at', 0)):
            if request_id != state.get('active') and request['state'] != 'pending':
                requests.pop(request_id, None)
                if len(requests) <= 64:
                    break
    return state


def _validate_relay_context(value):
    if not isinstance(value, dict) or set(value) - {'session_id', 'file_key', 'page_id', 'user_id', 'selection', 'selection_total', 'selection_truncated', 'profile'} or not {'session_id', 'file_key', 'page_id', 'user_id', 'selection'} <= set(value):
        raise ValueError('Invalid relay context')
    identity(value['session_id'], 'plugin session')
    scope(value['file_key'], value['page_id'], '0' * 64)
    if value['user_id'] is not None and (not isinstance(value['user_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', value['user_id'])):
        raise ValueError('Invalid local account identifier')
    rows = value['selection']
    if not isinstance(rows, list) or len(rows) > relay_view.MAX_NODES:
        raise ValueError('Invalid bounded selection')
    total = value.get('selection_total', len(rows))
    truncated = value.get('selection_truncated', total > len(rows))
    if not isinstance(total, int) or isinstance(total, bool) or total < len(rows) or not isinstance(truncated, bool) or truncated != (total > len(rows)):
        raise ValueError('Invalid selection coverage')
    selection = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'name', 'type'}:
            raise ValueError('Invalid selection metadata')
        if any(not isinstance(row[key], str) or len(row[key]) > limit or (key != 'name' and not row[key])
               for key, limit in (('id', 200), ('name', 200), ('type', 80))):
            raise ValueError('Invalid selection metadata')
        selection.append(dict(row))
    _validate_profile_projection(value.get('profile'))
    return {**value, 'selection': selection, 'selection_total': total, 'selection_truncated': truncated}


def _relay_poll_unlocked(root, payload):
    if not isinstance(payload, dict) or set(payload) - {'context', 'profile_result'}:
        raise ValueError('Invalid relay poll')
    now = time.time()
    state = _relay_state(root)
    context = _validate_relay_context(payload['context']) if 'context' in payload else None
    if context:
        state['context'] = {**context, 'seen_at': now}
    result = payload.get('profile_result')
    if result is not None:
        if not isinstance(result, dict) or set(result) - {'request_id', 'status', 'profile', 'error_code'} or not {'request_id', 'status'} <= set(result):
            raise ValueError('Invalid profile result')
        request_id = result.get('request_id')
        request = state['requests'].get(request_id) if isinstance(request_id, str) else None
        if request_id and (not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{32}', request_id)):
            raise ValueError('Invalid profile request ID')
        if result['status'] in {'ok', 'error', 'uncertain'}:
            error_code = result.get('error_code')
            if error_code is None or error_code in PROFILE_ERROR_CODES:
                profile = result.get('profile')
                try:
                    _validate_profile_projection(profile)
                except ValueError:
                    profile = None
                    error_code = None
                ack = {'status': result['status']}
                if profile is not None:
                    ack['profile'] = profile
                if error_code is not None:
                    ack['error_code'] = error_code
                if request is None and request_id:
                    # A server restart lost the mailbox. Consume the late result as uncertain;
                    # never issue a new save based on an orphaned acknowledgement.
                    request = {'request_id': request_id, 'session_id': context.get('session_id') if context else None,
                               'file_key': context.get('file_key') if context else None,
                               'page_id': context.get('page_id') if context else None,
                               'user_id': context.get('user_id') if context else None,
                               'requested_profile': None, 'state': 'uncertain', 'observed_profile': profile,
                               'error_code': error_code, 'ack': ack, 'created_at': now, 'completed_at': now}
                    state['requests'][request_id] = request
                elif request:
                    if request.get('ack') == ack:
                        pass
                    elif request['state'] == 'pending':
                        same_scope = context and all(context[field] == request[field] for field in ('session_id', 'file_key', 'page_id', 'user_id'))
                        if now > request['deadline'] or not same_scope:
                            terminal = 'uncertain' if request.get('dispatched_at') else 'expired'
                            request.update(state=terminal, observed_profile=profile, error_code=error_code,
                                           ack=ack, completed_at=now)
                        else:
                            status = result['status']
                            if status == 'ok' and (not profile or profile.get('declared') != request['requested_profile'] or
                                    profile.get('storage') != 'local' or profile.get('needsSetup') is not False):
                                status = 'uncertain'
                            request.update(state=status, observed_profile=profile, error_code=error_code,
                                           ack=ack, completed_at=now)
                    elif request['state'] in {'expired', 'uncertain'} and request.get('dispatched_at'):
                        request.update(state='uncertain', observed_profile=profile, error_code=error_code,
                                       ack=ack, completed_at=now)
                    else:
                        # Conflicting or late ACKs for terminal requests are consumed, not retried forever.
                        request['ignored_ack'] = ack
    active = state.get('active')
    if active:
        request = state['requests'].get(active)
        if not request or request['state'] != 'pending' or now > request['deadline']:
            if request and request['state'] == 'pending':
                terminal = 'uncertain' if request.get('dispatched_at') else 'expired'
                request.update(state=terminal, completed_at=now)
            state['active'] = None
    request = state['requests'].get(state.get('active')) if state.get('active') else None
    if request and request['state'] == 'pending' and context and all(context[field] == request[field] for field in ('session_id', 'file_key', 'page_id', 'user_id')):
        command = {key: request[key] for key in ('request_id', 'session_id', 'file_key', 'page_id', 'user_id')}
        command['profile'] = request['requested_profile']
    else:
        command = None
    return _relay_reply(state, now, command)


def _relay_reply(state, now, command=None):
    return {'profile_request': command,
            'context': ({key: value for key, value in state['context'].items() if key != 'seen_at'}
                        if state['context'] and now - state['context']['seen_at'] <= RELAY_TTL else None)}


def relay_poll(root, payload):
    with RELAY_LOCK:
        return _relay_poll_unlocked(root, payload)


def relay_mark_dispatched(root, request_id):
    with RELAY_LOCK:
        state = _relay_state(root)
        request = state['requests'].get(request_id)
        if request and request['state'] == 'pending' and time.time() <= request['deadline']:
            request.setdefault('dispatched_at', time.time())


def _relay_command_unlocked(root, payload):
    if not isinstance(payload, dict) or payload.get('action') not in {'context', 'profile-get', 'profile-set', 'profile-status'}:
        raise ValueError('Invalid relay command')
    state = _relay_state(root)
    now = time.time()
    action = payload['action']
    fields = {'context': {'action'}, 'profile-get': {'action'},
              'profile-status': {'action', 'request_id'},
              'profile-set': {'action', 'profile', 'expected_context'}}
    if set(payload) != fields[action]:
        raise ValueError('Relay command fields do not match its action')
    active_id = state.get('active')
    active_request = state['requests'].get(active_id) if active_id else None
    if active_request and active_request['state'] == 'pending' and now > active_request['deadline']:
        active_request.update(state='uncertain' if active_request.get('dispatched_at') else 'expired', completed_at=now)
        state['active'] = None
    if action == 'profile-status':
        request = state['requests'].get(payload.get('request_id'))
        if request and request['state'] == 'pending' and now > request['deadline']:
            request.update(state='uncertain' if request.get('dispatched_at') else 'expired', completed_at=now)
            if state.get('active') == request['request_id']:
                state['active'] = None
        return dict(request) if request else {'state': 'expired', 'request_id': payload.get('request_id')}
    current = state.get('context')
    if not current or now - current['seen_at'] > RELAY_TTL:
        return {'state': 'offline', 'context': None}
    context = _cli_context(root, {key: value for key, value in current.items() if key != 'seen_at'})
    if action == 'context':
        return {'state': 'ok', 'context': context, 'context_fingerprint': context_fingerprint(context)}
    if action == 'profile-get':
        return {'state': 'ok' if context.get('profile') else 'unknown', 'context': context,
                'profile': context.get('profile'), 'context_fingerprint': context_fingerprint(context)}
    profile = payload.get('profile')
    if (not isinstance(profile, dict) or set(profile) != {'plan', 'seat'} or
            profile['plan'] not in PROFILE_PLANS or profile['seat'] not in PROFILE_SEATS):
        raise ValueError('Invalid profile declaration')
    expected_context = payload.get('expected_context')
    fingerprint = context_fingerprint(context)
    if not isinstance(expected_context, str) or not hmac.compare_digest(expected_context, fingerprint):
        return {'state': 'scope-changed', 'context_fingerprint': fingerprint}
    if context.get('native_status') != 'current-self-reported' or context.get('native_generation') != context.get('expected_generation'):
        return {'state': 'stale-native', 'context': context, 'context_fingerprint': fingerprint}
    if context.get('user_id') is None:
        return {'state': 'unconfirmed', 'context': context, 'profile': context.get('profile')}
    active_id = state.get('active')
    existing = state['requests'].get(active_id) if active_id else None
    if existing and existing['state'] == 'pending':
        if all(existing[field] == context[field] for field in ('session_id', 'file_key', 'page_id', 'user_id')) and existing['requested_profile'] == profile:
            return {key: value for key, value in existing.items() if key != 'deadline'}
        return {'state': 'busy', 'context_fingerprint': fingerprint}
    current_profile = context.get('profile')
    if (current_profile and current_profile['storage'] == 'local' and not current_profile['needsSetup'] and
            current_profile['declared'] == profile):
        return {'state': 'ok', 'profile': current_profile,
                **{key: context[key] for key in ('session_id', 'file_key', 'page_id')}}
    directory = state_dir(root)
    active_request = active(directory)
    if ((active_request and active_request['state'] in {'pending', 'claimed', 'uncertain'}) or
            uncertainties(directory)['operations']):
        return {'state': 'busy', 'context_fingerprint': fingerprint}
    request_id = secrets.token_hex(16)
    request = {'request_id': request_id, **{key: context[key] for key in ('session_id', 'file_key', 'page_id', 'user_id')},
               'requested_profile': profile, 'state': 'pending', 'created_at': now, 'deadline': now + RELAY_REQUEST_TTL}
    state['requests'][request_id] = request
    state['active'] = request_id
    return {key: value for key, value in request.items() if key != 'deadline'}


def relay_command(root, payload):
    with workspace.locked(root):
        with RELAY_LOCK:
            return _relay_command_unlocked(root, payload)


def relay_request(root, action, *, profile=None, request_id=None, expected_context=None):
    settings = config(workspace.private_dir(root))
    payload = {'action': action}
    if profile is not None:
        payload['profile'] = profile
    if request_id is not None:
        payload['request_id'] = request_id
    if expected_context is not None:
        payload['expected_context'] = expected_context
    connection = http.client.HTTPConnection('127.0.0.1', settings['port'], timeout=3)
    try:
        connection.request('POST', '/control/relay', workspace.encode(payload),
                           {'Host': f'localhost:{settings["port"]}', 'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + settings['token']})
        response = connection.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise ReadinessError('Relay request rejected or oversized; reopen the same Figma Flow plugin')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ReadinessError('Malformed relay response')
        return value
    except (ConnectionRefusedError, TimeoutError, OSError, http.client.HTTPException):
        raise ReadinessError('Control server unavailable; reopen the same Figma Flow plugin') from None
    finally:
        connection.close()


def change_query(root, file_key, page_id, *, cursor=None, timeout=0):
    """Query the durable current-page change feed; a missing cursor starts at its head."""
    scope(file_key, page_id, '0' * 64)
    root = workspace.private_dir(root)
    def live_context():
        key = (str(root.resolve()),file_key,page_id)
        with CHANGE_CLIENTS_LOCK:
            observed = CHANGE_CLIENTS.get(key)
        if observed:
            current, runtime, seen = observed
            online = time.time() - seen <= RELAY_TTL and runtime == workspace.current(root,repair=False).get('runtime')
            return current, online
        return None, False
    return change_journal.query(state_dir(root) / 'changes.json', file_key, page_id, cursor, timeout,
                                status_provider=live_context)


def change_request(root, file_key, page_id, *, cursor=None, timeout=0):
    settings = config(workspace.private_dir(root))
    payload = {'file_key': file_key, 'page_id': page_id, 'timeout': timeout}
    if cursor is not None:
        payload['cursor'] = cursor
    connection = http.client.HTTPConnection('127.0.0.1', settings['port'], timeout=max(5, timeout + 5))
    try:
        connection.request('POST', '/control/changes', workspace.encode(payload),
                           {'Host': f'localhost:{settings["port"]}', 'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + settings['token']})
        response = connection.getresponse()
        raw = response.read(2_000_001)
        if response.status != 200 or len(raw) > 2_000_000:
            raise ReadinessError('Change query rejected or oversized; reopen the same Figma Flow plugin')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ReadinessError('Malformed change query response')
        return value
    except (ConnectionRefusedError, TimeoutError, OSError, http.client.HTTPException):
        raise ReadinessError('Control server unavailable; reopen the same Figma Flow plugin') from None
    finally:
        connection.close()


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


def require_ready(root, key, operation, file_key, page_id, revision, *, focus_page=False, viewer_options=None):
    root = workspace.private_dir(root)
    settings = config(root)
    task_request = {'key': key, 'operation': operation, 'file_key': file_key,
                    'page_id': page_id, 'revision': revision, 'focus_page': focus_page}
    if operation in relay_view.OPERATIONS | CAROUSEL_OPERATIONS:
        task_request['viewer_options'] = operation_options(operation, viewer_options or {})
    row = task(root, task_request)
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
    if 'fresh' in request and (not isinstance(request['fresh'], bool) or request['fresh'] and request['operation'] != 'import'):
        raise ValueError('Fresh import flag is invalid for this operation')
    selection = request.get('selection')
    if selection is not None and (request['operation'] != 'apply' or not isinstance(selection, dict)
            or row['kind'] != 'sync'
            or set(selection) != {'protocol', 'plan_sha256', 'selected_ids'} or selection.get('protocol') != 2
            or not isinstance(selection.get('plan_sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', selection['plan_sha256'])
            or not isinstance(selection.get('selected_ids'), list) or not 0 < len(selection['selected_ids']) <= 500
            or len(set(selection['selected_ids'])) != len(selection['selected_ids'])
            or any(not isinstance(item, str) or not re.fullmatch(r'[^\x00-\x1f]{1,240}', item) for item in selection['selected_ids'])):
        raise ValueError('Partial apply selection is malformed')
    if request['operation'] in relay_view.OPERATIONS | CAROUSEL_OPERATIONS:
        if request.get('viewer_options') != operation_options(request['operation'], request.get('viewer_options', {})):
            raise ValueError('Viewer options are malformed')
    elif request.get('viewer_options') is not None:
        raise ValueError('Viewer options are not admitted for this operation')
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
    if request['state'] == 'uncertain' and request['operation'] not in READ_ONLY_OPERATIONS:
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
        if request.get('state') == 'uncertain' and request.get('operation') not in READ_ONLY_OPERATIONS:
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
    if data.get('schema') == 'figma-flow-web-screen-discovery-v1':
        edit, web = data.get('native_edit'), data.get('web_design')
        if not (same_task and row['kind'] == 'native-edit' and isinstance(edit, dict)
                and isinstance(web, dict) and data.get('readback_scope') == 'screens'
                and data.get('fileKey') == original['file_key'] and data.get('pageId') == original['page_id']
                and edit.get('operation') == 'read' and edit.get('applied') is False
                and isinstance(edit.get('plan_sha256'), str)
                and edit['plan_sha256'] == row.get('input_pins', {}).get('--plan')
                and isinstance(web.get('graph_sha256'), str) and data.get('graph_sha256') == web['graph_sha256']
                and isinstance(data.get('nodes'), list) and isinstance(web.get('screens'), list)
                and web['screens']):
            return False
        return all(isinstance(screen, dict) and screen.get('status') in ('current', 'missing')
                   and (screen['status'] == 'missing' or bool(screen.get('frame_id'))) for screen in web['screens'])
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


LIFECYCLE_FIELDS = ('lifecycle_version', 'operation_id', 'phase_events', 'recovery_of')
PHASES = {'queued', 'claimed', 'native-started', 'result-received', 'reconciled', 'uncertain'}


def lifecycle_present(request):
    return any(field in request for field in LIFECYCLE_FIELDS)


def validate_lifecycle(request):
    events = request.get('phase_events')
    recovery = request.get('recovery_of') if 'recovery_of' in request else False
    valid_recovery = recovery is None or (
        isinstance(recovery, list) and all(isinstance(item, str) and re.fullmatch(r'[a-f0-9]{32}', item) for item in recovery))
    valid_events = isinstance(events, list) and all(
        isinstance(event, dict) and event.get('source') == 'server' and event.get('phase') in PHASES and isinstance(event.get('time'), str)
        for event in events)
    if request.get('lifecycle_version') != 1 or request.get('operation_id') != request.get('id') or not valid_events or not valid_recovery:
        raise ValueError('Invalid operation lifecycle')


def record_phase(request, phase):
    if phase not in PHASES:
        raise ValueError('Invalid operation lifecycle')
    if not lifecycle_present(request):
        request['lifecycle_version'] = 1
        request['operation_id'] = request['id']
        request['phase_events'] = []
        request['recovery_of'] = None
    else:
        validate_lifecycle(request)
    request['phase_events'].append({'phase': phase, 'time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'source': 'server'})


def journal_history(request):
    """Safe history lookup. Legacy requests stay unknown instead of inventing phases."""
    if not isinstance(request, dict):
        raise ValueError('Invalid operation journal')
    identity = request.get('id')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
        identity = None
    if not lifecycle_present(request):
        return {'operation_id': identity, 'classification': 'legacy', 'phase': 'unknown', 'phases': []}
    try:
        validate_lifecycle(request)
    except ValueError:
        return {'operation_id': None, 'classification': 'unknown', 'phase': 'unknown', 'phases': []}
    phases = [{'phase': event['phase'], 'time': event['time']} for event in request['phase_events']]
    return {'operation_id': request['operation_id'], 'classification': 'recorded', 'phase': phases[-1]['phase'] if phases else 'unknown', 'phases': phases}


def task_operation_boundary(root, revision):
    """Show that a prepared task revision is not a control operation id."""
    before = workspace.current(root)
    task = next((row for row in before['tasks'] if row.get('key') == 'discovery'), None)
    if not task or task.get('revision') != revision:
        raise ValueError('Prepared task revision mismatch')
    request = enqueue(root, 'discovery', 'read', 'fixturefile', '12:1', revision, 30)
    journal = journal_history(status(root))
    after = workspace.current(root)
    current = next(row for row in after['tasks'] if row.get('key') == 'discovery')
    return {
        'schema': 'figma-flow-identity-boundary-v1',
        'task_key': task['key'],
        'revision_length': len(task['revision']),
        'operation_id_length': len(request['operation_id']),
        'identities_differ': request['operation_id'] not in {task['revision'], task['key']},
        'operation_uses_task_key': request['key'] == task['key'],
        'catalogue_contains_operation_id': any(row.get('key') == request['operation_id'] for row in after['tasks']),
        'catalogue_revision_unchanged': current.get('revision') == task['revision'],
        'journal_operation_id_matches': journal.get('operation_id') == request['operation_id'],
        'dependency_inferred': 'depends_on' in task or 'depends_on' in current,
        'request_count': len(list((Path(root) / '.control' / 'requests').glob('*.json'))),
    }


def conflict_detail(readback):
    """Explicit conflict lookup. It does not overwrite the observed value or offer a rerun."""
    if not isinstance(readback, dict):
        raise ValueError('Invalid conflict detail')
    native = readback.get('native_edit')
    if not isinstance(native, dict):
        raise ValueError('Invalid conflict detail')
    plan = native.get('plan_sha256')
    conflicts = readback.get('rollback_conflicts')
    operations = native.get('operations')
    if not isinstance(plan, str) or not re.fullmatch(r'[a-f0-9]{64}', plan) or not isinstance(conflicts, list) or not conflicts or not isinstance(operations, list):
        raise ValueError('Invalid conflict detail')
    rows = []
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            raise ValueError('Invalid conflict detail')
        target = conflict.get('node_id') or conflict.get('variable_id')
        if not isinstance(target, str) or not target:
            raise ValueError('Invalid conflict detail')
        match = None
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            same_target = (conflict.get('node_id') and operation.get('node_id') == conflict.get('node_id')) or (conflict.get('variable_id') and operation.get('variable_id') == conflict.get('variable_id'))
            same_field = 'field' not in conflict or operation.get('field') == conflict.get('field')
            if same_target and same_field:
                match = operation
                break
        if match is None:
            raise ValueError('Invalid conflict detail')

        def take(key):
            if key in conflict:
                return conflict[key]
            if key in match:
                return match[key]
            raise ValueError('Invalid conflict detail')

        field = take('field')
        before = take('before')
        after = take('after')
        observed = take('observed')
        reason = conflict.get('reason')
        if not isinstance(field, str) or not field or not isinstance(reason, str) or not reason or conflict.get('plan_sha256') not in (None, plan):
            raise ValueError('Invalid conflict detail')
        rows.append({'target': target, 'field': field, 'before': json.loads(json.dumps(before)), 'after': json.loads(json.dumps(after)), 'observed': json.loads(json.dumps(observed)), 'rollback': reason, 'plan_sha256': plan})
    return {'plan_sha256': plan, 'actions': ['save-evidence', 'read-scope'], 'conflicts': rows}


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
        if request['state'] == 'uncertain' and lifecycle_present(request):
            record_phase(request, 'uncertain')
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


def enqueue(root, key, operation, file_key, page_id, revision, timeout, *, focus_page=False, fresh=False, selected_ids=None, plan_sha256=None, viewer_options=None):
    scope(file_key, page_id, revision)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise ValueError('Timeout must be between 1 and 3600 seconds')
    with workspace.locked(root) as root:
        config(root)
        directory = state_dir(root)
        previous = active(directory)
        if previous and previous['state'] not in TERMINAL:
            raise ValueError('An operation is already active; inspect its status')
        if uncertainties(directory)['operations'] and operation not in READ_ONLY_OPERATIONS:
            raise ValueError('Previous claimed operation is uncertain; re-read the native state before starting another command')
        if not isinstance(fresh, bool) or (fresh and operation != 'import'):
            raise ValueError('Fresh import is available only for import operations')
        selection = None
        if selected_ids is not None or plan_sha256 is not None:
            if operation != 'apply' or not isinstance(plan_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', plan_sha256):
                raise ValueError('Partial apply requires an exact selection plan hash')
            if not isinstance(selected_ids, list) or not selected_ids or len(selected_ids) > 500 or any(
                    not isinstance(item, str) or not re.fullmatch(r'[^\x00-\x1f]{1,240}', item) for item in selected_ids) or len(set(selected_ids)) != len(selected_ids):
                raise ValueError('Partial apply requires unique bounded selected IDs')
            selection = {'protocol': 2, 'plan_sha256': plan_sha256, 'selected_ids': selected_ids}
        request = {'schema': SCHEMA, 'id': secrets.token_hex(16), 'key': key, 'operation': operation,
                   'file_key': file_key, 'page_id': page_id, 'revision': revision,
                   'focus_page': focus_page,
                   'created_at': time.time(), 'deadline': time.time() + timeout, 'state': 'pending'}
        if fresh: request['fresh'] = True
        if selection: request['selection'] = selection
        if operation in relay_view.OPERATIONS | CAROUSEL_OPERATIONS:
            request['viewer_options'] = operation_options(operation, viewer_options or {})
        elif viewer_options is not None:
            raise ValueError('Viewer options are available only for viewer operations')
        task(root, request)
        record_phase(request, 'queued')
        save(directory, request)
        workspace.atomic(directory / 'active.json', workspace.encode({'id': request['id']}))
        return request


def poll(root, payload):
    poll_fields = {'session_id', 'file_key', 'page_id'}
    if not isinstance(payload, dict) or set(payload) - (poll_fields | {'runtime', 'relay', 'change_batch'}) or not poll_fields <= set(payload):
        raise ValueError('Exact plugin poll fields required')
    runtime = payload.get('runtime')
    if runtime is not None and (not isinstance(runtime, dict) or set(runtime) != {'version', 'implementation', 'generation'} or
            not isinstance(runtime['version'], str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', runtime['version']) or
            not isinstance(runtime['implementation'], str) or not re.fullmatch(r'[a-f0-9]{64}', runtime['implementation']) or
            not isinstance(runtime['generation'], str) or not re.fullmatch(r'[a-f0-9]{32}', runtime['generation'])):
        raise ValueError('Invalid native runtime identity')
    session = identity(payload['session_id'], 'plugin session')
    scope(payload['file_key'], payload['page_id'], '0' * 64)
    relay = None
    if 'relay' in payload:
        relay_payload = payload['relay']
        if not isinstance(relay_payload, dict) or set(relay_payload) - {'context', 'profile_result'}:
            raise ValueError('Invalid relay poll')
        if 'context' in relay_payload:
            context = _validate_relay_context(relay_payload['context'])
            if (context['session_id'], context['file_key'], context['page_id']) != (session, payload['file_key'], payload['page_id']):
                raise ValueError('Relay context differs from authenticated plugin poll')
        relay = relay_poll(root, relay_payload)
    with workspace.locked(root) as root:
        client_key = str(root.resolve())
        if len(NATIVE_CLIENTS) >= 256 and client_key not in NATIVE_CLIENTS:
            NATIVE_CLIENTS.pop(next(iter(NATIVE_CLIENTS)))
        NATIVE_CLIENTS[client_key] = {'runtime': runtime, 'session_id': session, 'seen_at': time.time()}
        native = native_state(root)
        directory = state_dir(root)
        request = active(directory)
        if relay is not None and relay.get('profile_request'):
            unresolved = request and request['state'] in {'pending', 'claimed', 'uncertain'}
            if not unresolved:
                unresolved = bool(uncertainties(directory)['operations'])
            relay_context = relay.get('context')
            current_native = (native['native_status'] == 'current-self-reported' and
                              isinstance(relay_context, dict) and relay_context.get('session_id') == session and
                              relay_context.get('file_key') == payload['file_key'] and relay_context.get('page_id') == payload['page_id'])
            if unresolved or not current_native:
                relay = {**relay, 'profile_request': None}

        change_receipt = None
        if 'change_batch' in payload:
            batch = payload['change_batch']
            batch_scope = batch.get('scope') if isinstance(batch, dict) else None
            relay_context = relay.get('context') if relay is not None else None
            if (not isinstance(batch_scope, dict) or set(batch_scope) != {'file_key', 'page_id', 'generation', 'session_id'} or
                    not isinstance(relay_context, dict) or runtime is None or native['native_status'] != 'current-self-reported' or
                    (batch_scope['session_id'], batch_scope['file_key'], batch_scope['page_id'], batch_scope['generation']) !=
                    (session, payload['file_key'], payload['page_id'], runtime['generation']) or
                    (relay_context['session_id'], relay_context['file_key'], relay_context['page_id']) !=
                    (session, payload['file_key'], payload['page_id'])):
                raise ValueError('Native changes require the verified active session, file, page and canonical runtime')
            change_receipt = change_journal.ingest(directory / 'changes.json', payload['change_batch'], batch_scope)
            # Other open documents may poll between two reads of this page.
            with CHANGE_CLIENTS_LOCK:
                change_key = (str(root.resolve()),payload['file_key'],payload['page_id'])
                if len(CHANGE_CLIENTS) >= 128 and change_key not in CHANGE_CLIENTS:
                    oldest = min(CHANGE_CLIENTS, key=lambda key: CHANGE_CLIENTS[key][2])
                    del CHANGE_CLIENTS[oldest]
                CHANGE_CLIENTS[change_key] = (dict(batch_scope),runtime,time.time())


        def poll_reply(value):
            profile_command = relay.get('profile_request') if relay is not None else None
            if profile_command:
                relay_mark_dispatched(root, profile_command['request_id'])
            return {**value, **({'relay': relay} if relay is not None else {}),
                    **({'changes': change_receipt} if change_receipt is not None else {})}
        if not request or request['state'] != 'pending':
            return poll_reply({'operation': None, **native})
        if request['operation'] != 'read' and native['native_status'] != 'current-self-reported':
            return poll_reply({'operation': None, **native})
        if request['operation'] not in READ_ONLY_OPERATIONS and uncertainties(directory)['operations']:
            request.update(state='error', error='Previous mutation remains uncertain', completed_at=time.time())
            save(directory, request)
            return poll_reply({'operation': None, **native})
        if request['file_key'] != payload['file_key'] or request['page_id'] != payload['page_id'] and not request.get('focus_page', False):
            return poll_reply({'operation': None, **native})
        try:
            task(root, request)
        except ValueError:
            request.update(state='error', error='Prepared task changed before claim', completed_at=time.time())
            save(directory, request)
            return poll_reply({'operation': None, **native})
        if lifecycle_present(request):
            validate_lifecycle(request)
        request.update(state='claimed', session_id=session, claim_id=secrets.token_hex(16), claimed_at=time.time())
        if lifecycle_present(request):
            record_phase(request, 'claimed')
        save(directory, request)
        command_fields = ('id', 'claim_id', 'session_id', 'key', 'operation', 'file_key', 'page_id', 'revision', 'deadline')
        command = {**{key: request[key] for key in command_fields}, 'focus_page': request.get('focus_page', False)}
        if request.get('fresh'): command['fresh'] = True
        if request.get('selection'): command['selection'] = request['selection']
        if request.get('viewer_options') is not None: command['viewer_options'] = request['viewer_options']
        return poll_reply({**native, 'operation': command})


def result(root, payload, *, large_body_bytes=None):
    required = {'id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision', 'status'}
    if not required <= set(payload) or set(payload) - required - {'readback_json', 'error'} or payload['status'] not in {'ok', 'error'}:
        raise ValueError('Exact plugin result fields required')
    for field in ('id', 'claim_id'):
        if not isinstance(payload[field], str) or not re.fullmatch(r'[a-f0-9]{32}', payload[field]):
            raise ValueError('Invalid result ' + field)
    identity(payload['session_id'], 'plugin session')
    scope(payload['file_key'], payload['page_id'], payload['revision'])
    raw = payload.get('readback_json')
    large_read = large_body_bytes is not None
    if large_read and (payload['status'] != 'ok' or raw is None or not 0 < large_body_bytes <= MAX_LARGE_READ_BODY):
        raise ValueError('A large result requires a successful bounded read')
    if raw is not None:
        if not isinstance(raw, str):
            raise ValueError('Readback must be a bounded JSON object string')
        raw_bytes = len(raw.encode('utf-8'))
        if raw_bytes > (MAX_LARGE_READBACK if large_read else MAX_READBACK) or not isinstance(json.loads(raw), dict):
            raise ValueError('Readback must be a bounded JSON object string')
        if large_read and raw_bytes <= MAX_READBACK and large_body_bytes <= MAX_BODY:
            raise ValueError('Use the ordinary route for this result')
    if payload.get('error') is not None and (not isinstance(payload['error'], str) or len(payload['error']) > 2000):
        raise ValueError('Invalid plugin error')
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    with workspace.locked(root) as root:
        directory = state_dir(root)
        receipt_path = directory / 'receipts' / (payload['id'] + '.json')
        if receipt_path.exists():
            receipt = workspace.read(receipt_path, private=True, limit=32768)
            if (large_read and receipt.get('operation') != 'read' or
                    receipt.get('state') not in {'ok', 'error'} or receipt.get('state') != payload['status'] or
                    receipt.get('result_payload_sha256') != fingerprint or
                    any(payload[key] != receipt.get(key) for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision'))):
                raise ValueError('Terminal result differs from the accepted plugin result')
            if lifecycle_present(receipt):
                validate_lifecycle(receipt)
            return {'accepted': True, 'id': receipt['id'], 'state': receipt['state']}
        request = active(directory)
        if not request or request['state'] != 'claimed':
            raise ValueError('No current claim accepts this result')
        if lifecycle_present(request):
            validate_lifecycle(request)
        if any(payload[key] != request[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')):
            raise ValueError('Result claim or scope mismatch')
        if large_read and request['operation'] != 'read':
            raise ValueError('A large result requires a claimed read operation')
        try:
            row = task(root, request)
        except ValueError:
            request.update(state='uncertain', error='Prepared task changed after claim', completed_at=time.time())
            if lifecycle_present(request):
                record_phase(request, 'uncertain')
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
        request.update(state=payload['status'], completed_at=time.time(), result_payload_sha256=fingerprint,
                       evidence='authenticated-running-plugin-result; not independent origin authentication')
        if payload.get('error'):
            request['error'] = payload['error']
        pending = uncertainties(directory)
        recovered = [identity for identity, original in pending['operations'].items()
                     if payload['status'] == 'ok' and recovery_read(request, row, json.loads(raw), original)]
        if recovered:
            request['reconciles'] = recovered
        if lifecycle_present(request):
            record_phase(request, 'result-received')
            if recovered:
                request['recovery_of'] = list(recovered)
                record_phase(request, 'reconciled')
        save(directory, request)
        if recovered:
            for operation_id in recovered:
                del pending['operations'][operation_id]
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
        journal = journal_history(value if isinstance(value, dict) else {})
        return {**value, 'journal': journal, 'uncertain_operations': [{key: original[key] for key in ('id', 'key', 'operation', 'file_key', 'page_id', 'revision')} for original in pending.values()]}


def history(root, payload):
    """Bounded canonical summaries, never native readback or client telemetry."""
    if set(payload) != {'session_id', 'file_key', 'page_id', 'runtime'}:
        raise ValueError('Exact history scope required')
    identity(payload['session_id'], 'native session')
    scope(payload['file_key'], payload['page_id'], '0' * 64)
    with workspace.locked(root) as root:
        catalogue = workspace.current(root, repair=False)
        if payload['runtime'] != catalogue.get('runtime'):
            raise ValueError('History runtime differs from the current prepared workspace')
        directory = state_dir(root)
        active(directory)
        rows = []
        paths = sorted(directory.joinpath('requests').glob('*.json'), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in paths:
            if not re.fullmatch(r'[a-f0-9]{32}\.json', path.name):
                continue
            request = workspace.read(path, private=True, limit=32768)
            if request.get('file_key') != payload['file_key'] or request.get('page_id') != payload['page_id']:
                continue
            journal = journal_history(request)
            if request.get('id') != path.stem or not isinstance(request.get('key'), str) or len(request['key']) > 200:
                continue
            revision = request.get('revision')
            if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision) or request.get('operation') not in set.union(*OPERATIONS.values()):
                continue
            rows.append({'taskKey': request['key'], 'revision': revision, 'operation': request['operation'],
                         'operationId': request['id'], **{key: journal[key] for key in ('classification', 'phase', 'phases')}})
            if len(rows) == 80:
                break
        inputs = [workspace.task_input_freshness(root, task) for task in catalogue['tasks']
                  if task.get('input_record') and task.get('fileKey') in {None, payload['file_key']}]
        return {'journalHistory': list(reversed(rows)), 'inputFreshness': inputs[:80]}


def history_detail(root, payload):
    """Bounded read-only exact-scope operation detail, causal relations, and safe diff."""
    return detail_projection.build_operation_detail(
        root,
        payload,
        control_schema=SCHEMA,
        journal_history_fn=journal_history,
        conflict_detail_fn=conflict_detail,
    )


operation_detail = history_detail


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
        try:
            finish(recovery_claim, discovery('12:1') + '\n')
            conflicting_duplicate_terminal_result = 'accepted'
        except ValueError:
            conflicting_duplicate_terminal_result = 'rejected'
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
        'conflicting_duplicate_terminal_result': conflicting_duplicate_terminal_result,
        'native_started': native_started,
    }


def note_native_started(root, payload):
    """Record one explicit native start after the claim and current runtime match."""
    required = {'id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision', 'runtime'}
    if set(payload) != required:
        raise ValueError('Exact native start fields required')
    runtime = payload['runtime']
    if (not isinstance(runtime, dict) or set(runtime) != {'version', 'implementation', 'generation'} or
            not isinstance(runtime['version'], str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', runtime['version']) or
            not isinstance(runtime['implementation'], str) or not re.fullmatch(r'[a-f0-9]{64}', runtime['implementation']) or
            not isinstance(runtime['generation'], str) or not re.fullmatch(r'[a-f0-9]{32}', runtime['generation'])):
        raise ValueError('Invalid native runtime identity')
    with workspace.locked(root) as root:
        directory = state_dir(root)
        request = active(directory)
        if not request or request['state'] != 'claimed':
            raise ValueError('No current claim accepts native start')
        if any(payload[key] != request[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')):
            raise ValueError('Native start claim or scope mismatch')
        if not lifecycle_present(request):
            raise ValueError('Invalid operation lifecycle')
        validate_lifecycle(request)
        current = workspace.current(root, repair=False).get('runtime')
        client = NATIVE_CLIENTS.get(str(root.resolve()))
        if payload['runtime'] != current or not client or client.get('session_id') != payload['session_id'] or client.get('runtime') != payload['runtime']:
            raise ValueError('Native start runtime does not match the claimed session')
        if any(isinstance(event, dict) and event.get('phase') == 'native-started' for event in request['phase_events']):
            raise ValueError('Native start was already recorded')
        record_phase(request, 'native-started')
        save(directory, request)
        return {'accepted': True, 'id': request['id'], 'state': request['state'], 'phase': 'native-started'}


def restart_delivery_report(root, mutation_revision):
    """Exercise the HTTP server, then drop its memory and miss the result post."""
    settings = dict(config(root))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.workspace, server.token = root, settings['token']
    settings['port'] = server.server_port
    workspace.atomic(root / 'control.json', workspace.encode(settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_time = time.time

    def post(path, payload):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.request('POST', path, json.dumps(payload), {
                'Host': f'localhost:{server.server_port}',
                'Authorization': 'Bearer ' + settings['token'],
                'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        runtime = workspace.current(root)['runtime']
        request = enqueue(root, 'mutation', 'apply', 'fixturefile', '12:1', mutation_revision, 30)
        code, polled = post('/control/poll', {'session_id': 'plugin-session-1', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': runtime})
        claim = polled.get('operation') if code == 200 else None
        if not claim:
            raise ValueError('HTTP claim was not delivered')
        started = {key: claim[key] for key in ('id', 'claim_id', 'session_id', 'file_key', 'page_id', 'revision')}
        started['runtime'] = runtime
        started_code, started_body = post('/control/native-started', started)
        if started_code != 200 or started_body.get('state') != 'claimed':
            raise ValueError('HTTP native start was not recorded')
        NATIVE_CLIENTS.pop(str(Path(root).resolve()), None)
        time.time = lambda: request['deadline'] + 1
        current = status(root)
        time.time = original_time
        try:
            enqueue(root, 'mutation', 'apply', 'fixturefile', '12:1', mutation_revision, 30)
            reenqueued = 'allowed'
        except ValueError as error:
            reenqueued = 'blocked' if 'uncertain' in str(error) else 'other'
        rerun_code, rerun = post('/control/poll', {'session_id': 'plugin-session-2', 'file_key': 'fixturefile', 'page_id': '12:1', 'runtime': runtime})
        return {
            'schema': 'figma-flow-control-restart-v1',
            'state': current['state'],
            'phases': [event['phase'] for event in current['phase_events']],
            'same_operation_id': current.get('operation_id') == request['id'],
            'mutation_reenqueued': reenqueued,
            'plugin_rerun_redelivers': rerun_code == 200 and rerun.get('operation') is not None,
            'result_delivered': current['state'] == 'ok',
            'request_count': len(list((Path(root) / '.control' / 'requests').glob('*.json'))),
        }
    finally:
        time.time = original_time
        server.shutdown()
        server.server_close()


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
        return (self.path in {'/control/poll', '/control/result', '/control/result-large', '/control/readiness', '/control/native-started', '/control/history', '/control/history-detail', '/control/relay', '/control/changes'} and self.headers.get('Host') == f'localhost:{self.server.server_port}'
                and self.headers.get('Origin') in ORIGINS | {None})

    def do_OPTIONS(self):
        self.reply(200 if self.allowed() else 403, {})

    def do_POST(self):
        self.connection.settimeout(70 if self.path == '/control/changes' else 15)
        if not self.allowed() or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.token):
            return self.reply(403, {'error': 'Control authentication or endpoint rejected'})
        length = self.headers.get('Content-Length', '')
        body_limit = MAX_LARGE_READ_BODY if self.path == '/control/result-large' else MAX_BODY
        if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json' or not re.fullmatch(r'[0-9]{1,9}', length) or not 0 < int(length) <= body_limit:
            return self.reply(413, {'error': 'Invalid control request body'})
        try:
            body = self.rfile.read(int(length))
            if len(body) != int(length):
                raise ValueError('Incomplete control request body')
            payload = json.loads(body)
            del body
            if not isinstance(payload, dict):
                raise ValueError('Object required')
            if self.path == '/control/readiness':
                if payload:
                    raise ValueError('Exact empty readiness object required')
                value = readiness(self.server.workspace)
            elif self.path == '/control/native-started':
                value = note_native_started(self.server.workspace, payload)
            elif self.path == '/control/history':
                value = history(self.server.workspace, payload)
            elif self.path == '/control/history-detail':
                value = history_detail(self.server.workspace, payload)
            elif self.path == '/control/relay':
                value = relay_command(self.server.workspace, payload)
            elif self.path == '/control/changes':
                if set(payload) - {'file_key', 'page_id', 'cursor', 'timeout'} or not {'file_key', 'page_id', 'timeout'} <= set(payload):
                    raise ValueError('Exact change query fields required')
                value = change_query(self.server.workspace, payload['file_key'], payload['page_id'],
                                     cursor=payload.get('cursor'), timeout=payload['timeout'])
            elif self.path == '/control/result-large':
                value = result(self.server.workspace, payload, large_body_bytes=int(length))
            else:
                value = poll(self.server.workspace, payload) if self.path == '/control/poll' else result(self.server.workspace, payload)
        except detail_projection.OperationNotFoundError as error:
            return self.reply(404, {'error': 'Control operation not found in this scope', 'reason': error.reason})
        except detail_projection.OperationRejectedError as error:
            return self.reply(409, {'error': 'Control request rejected; inspect private operation status', 'reason': error.reason})
        except (ValueError, KeyError, TypeError, OSError):
            if self.path == '/control/history-detail':
                return self.reply(409, {'error': 'Control request rejected; inspect private operation status', 'reason': 'request-rejected'})
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
    for name in ('enable', 'serve', 'run', 'status', 'context', 'profile', 'changes'):
        command = commands.add_parser(name)
        command.add_argument('--workspace', type=Path, required=True)
        if name == 'enable':
            command.add_argument('--port', type=int, required=True)
        elif name == 'status':
            command.add_argument('--id')
        elif name == 'changes':
            command.add_argument('--file-key', required=True)
            command.add_argument('--page-id', required=True)
            command.add_argument('--cursor', help='JSON resume cursor returned by a previous changes query')
            command.add_argument('--timeout', type=float, default=0, help='Long-poll up to 60 seconds for new changes')
        elif name == 'profile':
            command.add_argument('action', choices=('get', 'set', 'status'))
            command.add_argument('--plan', choices=sorted(PROFILE_PLANS))
            command.add_argument('--seat', choices=sorted(PROFILE_SEATS))
            command.add_argument('--request-id')
            command.add_argument('--expected-context')
            command.add_argument('--timeout', type=float, default=30)
        elif name == 'run':
            for field in ('key', 'file-key', 'page-id', 'expected-revision'):
                command.add_argument('--' + field, required=True)
            command.add_argument('--operation', choices=sorted(set.union(*OPERATIONS.values())), required=True)
            command.add_argument('--timeout', type=float, default=120)
            command.add_argument('--fresh', action='store_true', help='Import the source as a new page')
            command.add_argument('--plan-sha256')
            command.add_argument('--selected-id', action='append', dest='selected_ids')
            command.add_argument('--node-id')
            command.add_argument('--language')
            command.add_argument('--include-text', action='store_true')
            command.add_argument('--geometry-node-id', action='append', dest='geometry_node_ids')
            command.add_argument('--inspect-node-id', action='append', dest='inspect_node_ids')
            command.add_argument('--field', action='append', dest='inspect_fields', choices=sorted(relay_view.INSPECT_FIELDS))
            command.add_argument('--execution-id')
            command.add_argument('--state-id')
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
        elif args.command == 'context':
            value = relay_request(args.workspace, 'context')
        elif args.command == 'changes':
            cursor = json.loads(args.cursor) if args.cursor else None
            if not 0 <= args.timeout <= 60:
                raise ValueError('Changes timeout must be between 0 and 60 seconds')
            value = change_request(args.workspace, args.file_key, args.page_id,
                                   cursor=cursor, timeout=args.timeout)
        elif args.command == 'profile':
            if args.action == 'get':
                value = relay_request(args.workspace, 'profile-get')
            elif args.action == 'status':
                if not args.request_id:
                    raise ValueError('Profile status requires --request-id')
                value = relay_request(args.workspace, 'profile-status', request_id=args.request_id)
            else:
                if not args.plan or not args.seat or not args.expected_context or not 1 <= args.timeout <= 3600:
                    raise ValueError('Profile set requires --plan, --seat, --expected-context and a valid timeout')
                value = relay_request(args.workspace, 'profile-set', profile={'plan': args.plan, 'seat': args.seat},
                                      expected_context=args.expected_context)
                if value.get('state') == 'pending':
                    deadline = time.time() + args.timeout
                    while value.get('state') == 'pending' and time.time() < deadline:
                        time.sleep(.25)
                        value = relay_request(args.workspace, 'profile-status', request_id=value['request_id'])
        else:
            viewer_options = {}
            if args.operation != 'selection-info' and (args.inspect_node_ids or args.inspect_fields):
                raise ValueError('Property reads require selection-info')
            if args.operation not in CAROUSEL_OPERATIONS and (args.execution_id is not None or args.state_id is not None):
                raise ValueError('Carousel flags do not match the selected operation')
            if args.operation == 'select-node':
                if args.language is not None or args.include_text or args.geometry_node_ids: raise ValueError('Viewer flags do not match select-node')
                viewer_options = {'node_id': args.node_id}
            elif args.operation == 'viewer-language':
                if args.node_id is not None or args.include_text or args.geometry_node_ids: raise ValueError('Viewer flags do not match viewer-language')
                viewer_options = {'language': args.language}
            elif args.operation == 'selection-info':
                if args.node_id is not None or args.language is not None: raise ValueError('Viewer flags do not match selection-info')
                if args.geometry_node_ids is not None and args.include_text:
                    raise ValueError('Geometry-only selection-info cannot include text')
                viewer_options = {'include_text': args.include_text}
                if args.geometry_node_ids is not None: viewer_options['geometry_node_ids'] = args.geometry_node_ids
                if args.inspect_node_ids: viewer_options['inspect_node_ids'] = args.inspect_node_ids
                if args.inspect_fields: viewer_options['fields'] = args.inspect_fields
            elif args.operation == 'viewer-history':
                if args.node_id is not None or args.language is not None or args.include_text or args.geometry_node_ids:
                    raise ValueError('Viewer flags do not match viewer-history')
            elif args.operation in CAROUSEL_OPERATIONS:
                if args.node_id is not None or args.language is not None or args.include_text or args.geometry_node_ids:
                    raise ValueError('Viewer flags do not match carousel operation')
                viewer_options = {'execution_id': args.execution_id, 'state_id': args.state_id}
            elif args.node_id is not None or args.language is not None or args.include_text or args.geometry_node_ids:
                raise ValueError('Viewer flags do not match the selected operation')
            require_ready(args.workspace, args.key, args.operation, args.file_key, args.page_id, args.expected_revision,
                          focus_page=args.focus_page, viewer_options=viewer_options)
            value = enqueue(args.workspace, args.key, args.operation, args.file_key, args.page_id, args.expected_revision, args.timeout,
                            focus_page=args.focus_page, fresh=args.fresh, selected_ids=args.selected_ids, plan_sha256=args.plan_sha256,
                            viewer_options=viewer_options if args.operation in relay_view.OPERATIONS | CAROUSEL_OPERATIONS else None)
            if not args.no_wait:
                while value['state'] not in TERMINAL:
                    time.sleep(min(.2, max(.01, value['deadline'] - time.time())))
                    value = status(args.workspace, value['id'])
        print(json.dumps(value, ensure_ascii=True, allow_nan=False))
        return 2 if value.get('state') in {'error', 'uncertain', 'expired', 'scope-changed', 'unconfirmed', 'offline', 'stale-native', 'busy'} else 0
    except ReadinessError as error:
        print('figma-control: ' + str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError):
        print('figma-control: rejected; inspect private configuration, task revision, scope and operation status', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
