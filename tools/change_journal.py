"""Durable, bounded journal for verified Figma-to-canonical change intake."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

import figma_workspace as workspace

MAX_EVENTS = 500
MAX_STREAMS = 32
MAX_AGE = 7 * 24 * 60 * 60
SOURCE_TTL = 20
MAX_SOURCES = 16
KNOWN_PROPERTIES = frozenset(json.loads((Path(__file__).resolve().parents[1] /
                                        'library/figma-profile/policy.json').read_bytes())['nodeChangeProperties'])
CHANGE_TYPES = {'CREATE', 'DELETE', 'PROPERTY_CHANGE'}
_condition = threading.Condition()


def _key(file_key, page_id):
    return hashlib.sha256((file_key + '\0' + page_id).encode()).hexdigest()


def _source_key(scope):
    return hashlib.sha256((scope['generation'] + '\0' + scope['session_id']).encode()).hexdigest()


def _read(path):
    try:
        value = json.loads(path.read_text())
        if value.get('schema') != 'figma-flow-change-journal-v1' or not isinstance(value.get('streams'), dict):
            raise ValueError('Invalid change journal')
        return value
    except FileNotFoundError:
        return {'schema': 'figma-flow-change-journal-v1', 'streams': {}}


def _write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace.atomic(path, workspace.encode(value))
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stream(value, file_key, page_id):
    key = _key(file_key, page_id)
    stream = value['streams'].get(key)
    if stream is None:
        if len(value['streams']) >= MAX_STREAMS:
            oldest = min(value['streams'], key=lambda k: value['streams'][k].get('touched_at', 0))
            del value['streams'][oldest]
        stream = {'file_key': file_key, 'page_id': page_id, 'epoch': secrets.token_hex(16), 'seq': 0,
                  'events': [], 'sources': {}, 'scope': None, 'status': 'available', 'reason': None,
                  'touched_at': time.time()}
        value['streams'][key] = stream
    if 'sources' not in stream:
        stream['sources'] = {}
        old = stream.pop('source', None)
        if old:
            old_scope = {'generation': old['generation'], 'session_id': old['session_id']}
            stream['sources'][_source_key(old_scope)] = {**old, 'last_seen': stream.get('touched_at', time.time()),
                                                         'status': stream.get('status', 'available')}
    stream['touched_at'] = time.time()
    stream['events'] = [row for row in stream['events'] if time.time() - row['at'] <= MAX_AGE]
    return stream


def _append_gap(stream, reason, source_seq):
    stream['seq'] += 1
    gap = {'from': source_seq + 1, 'to': source_seq + 1, 'reason': reason}
    stream['events'].append({'at': time.time(), 'kind': 'gap', 'seq': stream['seq'], 'gap': gap})
    return gap


def ingest(path, batch, verified_scope):
    """Persist each source cursor independently before acknowledging its batch."""
    if not isinstance(batch, dict) or set(batch) - {'scope', 'cursor', 'events', 'gap', 'status', 'reason'} or not {'scope', 'cursor', 'events', 'gap', 'status'} <= set(batch):
        raise ValueError('Invalid native change batch')
    scope = batch['scope']
    if scope != verified_scope:
        raise ValueError('Native changes differ from the authenticated active page')
    cursor = batch['cursor']
    if not isinstance(cursor, dict) or set(cursor) != {'epoch', 'seq'} or not isinstance(cursor['epoch'], str) or not re.fullmatch(r'[a-f0-9]{32}', cursor['epoch']) or type(cursor['seq']) is not int or cursor['seq'] < 0:
        raise ValueError('Invalid native change cursor')
    status = batch['status']
    reason = batch.get('reason')
    if (status not in {'available', 'unavailable'} or
            (status == 'unavailable' and reason != 'page-listener-unavailable') or
            (status == 'available' and reason is not None)):
        raise ValueError('Invalid native listener status')
    events = batch['events']
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError('Invalid bounded native change events')
    prior_seq = -1
    for event in events:
        if not isinstance(event, dict) or set(event) - {'seq', 'node_id', 'type', 'properties', 'unknown_properties', 'properties_truncated', 'origin'} or not {'seq', 'node_id', 'type', 'properties', 'origin'} <= set(event):
            raise ValueError('Invalid native change event')
        if type(event['seq']) is not int or event['seq'] <= prior_seq or event['seq'] > cursor['seq']:
            raise ValueError('Native change sequence is not ordered')
        unknown = event.get('unknown_properties', [])
        if (not isinstance(event['node_id'], str) or not re.fullmatch(r'[A-Za-z0-9:;_-]{1,160}', event['node_id']) or
                event['type'] not in CHANGE_TYPES or not isinstance(event['properties'], list) or len(event['properties']) > 32 or
                any(item not in KNOWN_PROPERTIES for item in event['properties']) or len(set(event['properties'])) != len(event['properties']) or
                not isinstance(unknown, list) or len(unknown) > 32 or
                any(not isinstance(item, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', item) or item in KNOWN_PROPERTIES for item in unknown) or
                len(set(unknown)) != len(unknown) or
                ('properties_truncated' in event and not isinstance(event['properties_truncated'], bool)) or
                (len(event['properties']) + len(unknown) > 32 and event.get('properties_truncated') is not True) or
                event['origin'] not in {'figma-flow-plugin', 'unknown'}):
            raise ValueError('Invalid native change event fields')
        prior_seq = event['seq']
    gap = batch['gap']
    if gap is not None and (not isinstance(gap, dict) or set(gap) != {'from', 'to'} or
            type(gap['from']) is not int or type(gap['to']) is not int or not 1 <= gap['from'] <= gap['to'] <= cursor['seq']):
        raise ValueError('Invalid native change gap')
    if status == 'unavailable' and (events or gap is not None):
        raise ValueError('Unavailable listener batches cannot contain changes or gaps')
    path = Path(path)
    with _condition:
        value = _read(path)
        stream = _stream(value, scope['file_key'], scope['page_id'])
        sources = stream['sources']
        key = _source_key(scope)
        source = sources.get(key)
        source_created = source is None
        now = time.time()
        prior_status = source.get('status') if source else None
        rollover = False
        gap_added = None
        if source is None:
            other_live_sources = [item for known_key, item in sources.items()
                                  if known_key != key and now - item.get('last_seen', 0) <= SOURCE_TTL]
            if sources and not other_live_sources:
                prior = max(sources.values(), key=lambda item: item.get('last_seen', 0))
                gap_added = _append_gap(stream, 'session_rollover', prior['cursor']['seq'])
                rollover = True
            if len(sources) >= MAX_SOURCES:
                stale = [item_key for item_key, item in sources.items() if now - item.get('last_seen', 0) > SOURCE_TTL]
                evict = stale[0] if stale else min(sources, key=lambda item_key: sources[item_key].get('last_seen', 0))
                sources.pop(evict, None)
            source = {'epoch': cursor['epoch'], 'cursor': {'epoch': cursor['epoch'], 'seq': 0},
                      'session_id': scope['session_id'], 'generation': scope['generation'],
                      'last_seen': now, 'status': status, 'reason': reason}
            sources[key] = source
        epoch_changed = bool(source and source['epoch'] != cursor['epoch'])
        if epoch_changed:
            gap_added = _append_gap(stream, 'cursor_epoch_changed', source['cursor']['seq'])
            source.update(epoch=cursor['epoch'], cursor={'epoch': cursor['epoch'], 'seq': 0})
        source['last_seen'] = now
        source['status'], source['reason'] = status, reason
        stream['status'], stream['reason'] = status, reason
        stream['scope'] = scope
        if status == 'unavailable':
            changed = prior_status != status or gap_added is not None
            if changed:
                _write(path, value)
                _condition.notify_all()
            return {'scope': scope, 'status': status, 'reason': batch['reason'],
                    'accepted_cursor': dict(source['cursor']), 'gap': None, 'session_rollover': rollover}
        accepted = source['cursor']
        if gap and gap['to'] > accepted['seq']:
            stream['seq'] += 1
            gap_added = {'from': gap['from'], 'to': gap['to'], 'reason': 'native_overflow'}
            stream['events'].append({'at': time.time(), 'kind': 'gap', 'seq': stream['seq'], 'gap': gap_added})
            accepted['seq'] = gap['to']
        new_events = 0
        for event in events:
            if event['seq'] <= accepted['seq']:
                continue
            if event['seq'] != accepted['seq'] + 1:
                raise ValueError('Native change batch has an unreported sequence gap')
            stream['seq'] += 1
            stream['events'].append({'at': time.time(), 'kind': 'change', 'seq': stream['seq'],
                                     'source_epoch': cursor['epoch'], 'source_seq': event['seq'],
                                     'scope': scope, 'event': event})
            new_events += 1
            accepted['seq'] = event['seq']
        if cursor['seq'] > accepted['seq']:
            if not gap or gap['to'] < cursor['seq']:
                raise ValueError('Native change cursor exceeds received events')
            accepted['seq'] = cursor['seq']
        stream['scope'] = scope
        source['cursor'] = accepted
        unchanged_ack = (not source_created and not epoch_changed and new_events == 0 and
                         gap_added is None and prior_status == status and
                         source['cursor']['seq'] == cursor['seq'])
        stream['events'] = stream['events'][-MAX_EVENTS:]
        if not unchanged_ack:
            _write(path, value)
            _condition.notify_all()
        return {'scope': scope, 'status': status, **({'reason': reason} if reason else {}), 'accepted_cursor': dict(accepted), 'gap': gap,
                'session_rollover': rollover}


def query(path, file_key, page_id, cursor=None, timeout=0, *, active_scope=None, online=False, status_provider=None):
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 <= timeout <= 60:
        raise ValueError('Change wait timeout must be between 0 and 60 seconds')
    if cursor is not None and (not isinstance(cursor, dict) or set(cursor) != {'epoch', 'seq'} or
            not isinstance(cursor['epoch'], str) or type(cursor['seq']) is not int or cursor['seq'] < 0):
        raise ValueError('Invalid change resume cursor')
    deadline = time.monotonic() + timeout
    path = Path(path)
    with _condition:
        while True:
            value = _read(path)
            stream = value['streams'].get(_key(file_key, page_id))
            if status_provider:
                resolved_scope, resolved_online = status_provider()
            else:
                resolved_scope = active_scope() if callable(active_scope) else active_scope
                resolved_online = online() if callable(online) else online
            if stream is None:
                return {'scope': None, 'events': [], 'cursor': None, 'high_water': None,
                        'gap': ({'from': cursor['seq'] + 1, 'to': cursor['seq'] + 1,
                                 'reason': 'journal_expired'} if cursor is not None else None),
                        'session_rollover': False, 'status': 'unavailable',
                        'reason': 'journal_expired' if cursor is not None else 'no-native-feed',
                        'offline': not resolved_online}
            high = {'epoch': stream['epoch'], 'seq': stream['seq']}
            if cursor is not None and cursor['epoch'] == high['epoch'] and cursor['seq'] > high['seq']:
                raise ValueError('Change cursor is ahead of journal high-water')
            start = high if cursor is None else cursor
            expired = cursor is not None and cursor['epoch'] != stream['epoch']
            rows = stream['events']
            if not expired and cursor is not None and rows:
                retained = [row['seq'] for row in rows if 'seq' in row]
                first = min(retained) if retained else stream['seq'] + 1
                expired = cursor['epoch'] == stream['epoch'] and cursor['seq'] < first - 1
            available = cursor is None or expired or stream.get('status') == 'unavailable' or (cursor['epoch'] == stream['epoch'] and cursor['seq'] < stream['seq'])
            if available or time.monotonic() >= deadline:
                result = []
                if cursor is not None and not expired:
                    result = [row for row in rows if row.get('kind') == 'change' and row['seq'] > cursor['seq']]
                gap = ({'from': (1 if cursor['epoch'] != high['epoch'] else start['seq'] + 1),
                        'to': max(1, high['seq']), 'reason': 'cursor_expired'} if expired else None)
                if gap is None and cursor is not None:
                    gaps = [row['gap'] for row in rows if row.get('kind') == 'gap' and row['seq'] > cursor['seq']]
                    if gaps: gap = gaps[-1]
                session_rollover = bool(gap and gap.get('reason') == 'session_rollover')
                scope = resolved_scope or stream.get('scope')
                gap_rows = [row for row in rows if row.get('kind') == 'gap' and not expired and
                            cursor is not None and row['seq'] > cursor['seq']]
                consumed = [row['seq'] for row in result] + [row['seq'] for row in gap_rows]
                next_cursor = high if cursor is None or expired or not consumed else {
                    'epoch': stream['epoch'], 'seq': max(consumed)}
                return {'scope': scope, 'events': [{'scope': row['scope'], **row['event']} for row in result],
                        'cursor': next_cursor,
                        'high_water': high, 'gap': gap, 'session_rollover': session_rollover,
                        'status': stream.get('status', 'available'), 'reason': stream.get('reason'), 'offline': not resolved_online}
            remaining = deadline - time.monotonic()
            _condition.wait(remaining)
