#!/usr/bin/env python3
"""Read-only exact-scope operation detail and causal relation projection (NF-03).

Projects canonical control requests, verified signed task revisions, declared
dependencies, explicit recovery links, pinned artifact digests, and redacted
same-field design diffs without mutating workspace state or opening new stores.
"""
import hashlib
import hmac
import json
from pathlib import Path
import re

import figma_workspace as workspace

DETAIL_SCHEMA = 'figma-flow-operation-detail-v1'
MAX_DIFF_FIELDS = 200
MAX_CONFLICTS = 50
MAX_RELATIONS = 200
MAX_PHASES = 128
MAX_RESPONSE_BYTES = 256 * 1024

ALLOWED_OPERATIONS = {'read', 'import', 'sync', 'create', 'apply'}
ALLOWED_STATES = {'pending', 'claimed', 'ok', 'error', 'uncertain', 'expired'}
ALLOWED_RELATION_TYPES = {'declared-dependency', 'recovery-of', 'artifact-input'}
ALLOWED_TASK_KINDS = {'discover', 'import', 'native-edit', 'review', 'sync'}

ALLOWED_DESIGN_FIELDS = {
    'value', 'backgroundColor', 'color', 'borderColor', 'fill', 'stroke', 'strokeWeight',
    'fontSize', 'fontFamily', 'fontWeight', 'lineHeight', 'letterSpacing',
    'padding', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'gap', 'itemSpacing', 'cornerRadius', 'borderRadius', 'opacity',
    'width', 'height', 'visible', 'boolean', 'variant', 'instanceSwap',
    'characters', 'x', 'y',
}

TEXT_FIELDS = {
    'characters', 'text', 'display_text', 'label', 'placeholder',
    'helperText', 'errorMessage', 'caption', 'title', 'content', 'copy',
}

TASK_ARTIFACTS = {
    'sync': 'native-plan.json',
    'native-edit': 'native-edit-plan.json',
    'import': 'reviewed-payload.json',
    'review': 'packet.json',
}

_HEX32 = re.compile(r'^[a-f0-9]{32}$')
_HEX64 = re.compile(r'^[a-f0-9]{64}$')
_TASK_KEY = re.compile(r'^[A-Za-z0-9_-]{1,200}$')
_SESSION_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_FILE_KEY = re.compile(r'^[A-Za-z0-9]{1,128}$')
_PAGE_ID = re.compile(r'^[0-9]+:[0-9]+$')
_SEMVER = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+$')
_RAW_NODE_ID = re.compile(r'(?:^|\b)I?[0-9]+:[0-9]+(?:;[0-9]+:[0-9]+)*(?:\b|$)')
_REASON_CODE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
_SENSITIVE_PATH_RE = re.compile(
    r'(?:^|[\s"\'=:(])(?:/users/|/home/|/private/|/var/folders/|/tmp/|/etc/|[a-z]:[\\/]|file://|https?://|wss?://|data:)',
    re.IGNORECASE,
)
_SENSITIVE_SUBSTRINGS = (
    '.control/', '.tasks/', '.generations/',
    'bearer ', 'authorization:', 'access_token', 'refresh_token',
    'capability=', 'secret=', 'password=', 'token=', 'figd_', 'ghp_', 'sk-',
)
_WINDOWS_PATH = re.compile(r'^[A-Za-z]:[\\/]')


class OperationNotFoundError(LookupError):
    """Raised when an operation ID does not exist in the exact file/page scope."""

    def __init__(self, reason='not-found-in-scope'):
        super().__init__(reason)
        self.reason = reason


class OperationRejectedError(ValueError):
    """Raised when the detail envelope, runtime, or task/revision binding is rejected."""

    def __init__(self, reason='request-rejected'):
        super().__init__(reason)
        self.reason = reason


def _is_sensitive_string(value):
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith(('/', '~/', '\\')) or _WINDOWS_PATH.match(stripped):
        return True
    if _SENSITIVE_PATH_RE.search(stripped):
        return True
    lower = stripped.lower()
    if any(token in lower for token in _SENSITIVE_SUBSTRINGS):
        return True
    if _RAW_NODE_ID.search(stripped):
        return True
    if _HEX64.match(stripped):
        return True
    return False


def _safe_semantic_key(raw, fallback_prefix='item', index=1):
    if not isinstance(raw, str):
        return f'{fallback_prefix}#{index}'
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > 200 or _is_sensitive_string(cleaned):
        return f'{fallback_prefix}#{index}'
    # Strip any accidental #suffix node digits while keeping semantic property names readable.
    if re.search(r'#[0-9]+:[0-9]+$', cleaned):
        cleaned = re.sub(r'#[0-9]+:[0-9]+$', '', cleaned)
    return cleaned if cleaned and not _is_sensitive_string(cleaned) else f'{fallback_prefix}#{index}'


def _text_token(text):
    raw = text if isinstance(text, str) else str(text or '')
    return {
        '__text__': True,
        'length': len(raw),
        'digest': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
    }


def _is_text_token(value):
    return isinstance(value, dict) and value.get('__text__') is True


def _normalize_design_value(field, value):
    """Convert raw artifact values into internal comparable tokens without retaining raw text."""
    if field in TEXT_FIELDS:
        return _text_token(value if isinstance(value, str) else ('' if value is None else str(value)))
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 6) if isinstance(value, float) else int(value)
    if isinstance(value, str):
        if len(value) > 120 or _is_sensitive_string(value):
            return _text_token(value)
        return value
    if isinstance(value, dict):
        if set(value).issubset({'r', 'g', 'b', 'a'}) and {'r', 'g', 'b'}.issubset(value):
            channels = {}
            for channel in ('r', 'g', 'b'):
                val = value.get(channel)
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    return None
                channels[channel] = round(float(val), 6)
            alpha = value.get('a', 1.0)
            if not isinstance(alpha, (int, float)) or isinstance(alpha, bool):
                return None
            channels['a'] = round(float(alpha), 6)
            return channels
        if value.get('type') == 'TEXT' or 'characters' in value or 'text' in value:
            raw_text = value.get('default_value', value.get('value', value.get('characters', value.get('text', ''))))
            return _text_token(raw_text if isinstance(raw_text, str) else '')
        if '$value' in value:
            if value.get('$type') in {'string', 'text'} and field in TEXT_FIELDS:
                return _text_token(value.get('$value', ''))
            return _normalize_design_value(field, value.get('$value'))
    return None


def _value_kind(token):
    if token is None:
        return 'null'
    if _is_text_token(token):
        return 'text'
    if isinstance(token, bool):
        return 'boolean'
    if isinstance(token, (int, float)):
        return 'number'
    if isinstance(token, str):
        return 'string'
    if isinstance(token, dict):
        return 'color'
    return 'unknown'


def _same_design_token(left, right):
    if _value_kind(left) != _value_kind(right):
        return False
    if _is_text_token(left):
        return left['length'] == right['length'] and left['digest'] == right['digest']
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right


def _public_value(token, other_token=None):
    if _is_text_token(token):
        changed = True if other_token is None or not _is_text_token(other_token) else not _same_design_token(token, other_token)
        return {'valueType': 'text', 'changed': changed, 'length': int(token['length'])}
    if isinstance(token, dict):
        return {k: token[k] for k in ('r', 'g', 'b', 'a') if k in token}
    return token


def _validate_envelope(payload):
    required = {'session_id', 'file_key', 'page_id', 'runtime', 'operation_id', 'task_key', 'revision'}
    if not isinstance(payload, dict) or set(payload) != required:
        raise OperationRejectedError('invalid-envelope')
    op_id = payload.get('operation_id')
    if not isinstance(op_id, str) or not _HEX32.fullmatch(op_id):
        raise OperationRejectedError('invalid-operation-id')
    task_key = payload.get('task_key')
    revision = payload.get('revision')
    if (not isinstance(task_key, str) or not _TASK_KEY.fullmatch(task_key)
            or not isinstance(revision, str) or not _HEX64.fullmatch(revision)):
        raise OperationRejectedError('invalid-task-revision-binding')
    session_id = payload.get('session_id')
    file_key = payload.get('file_key')
    page_id = payload.get('page_id')
    runtime = payload.get('runtime')
    if (not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id)
            or not isinstance(file_key, str) or not _FILE_KEY.fullmatch(file_key)
            or not isinstance(page_id, str) or not _PAGE_ID.fullmatch(page_id)
            or not isinstance(runtime, dict) or set(runtime) != {'version', 'implementation', 'generation'}
            or not isinstance(runtime.get('version'), str) or not _SEMVER.fullmatch(runtime['version'])
            or not isinstance(runtime.get('implementation'), str) or not _HEX64.fullmatch(runtime['implementation'])
            or not isinstance(runtime.get('generation'), str) or not _HEX32.fullmatch(runtime['generation'])):
        raise OperationRejectedError('invalid-envelope')


def _collect_verified_task_history(root, catalogue, executed_key_revs):
    """Collect active, dependency-pinned, retired, and executed signed generation task rows."""
    active_by_key = {
        row['key']: row
        for row in catalogue.get('tasks', [])
        if isinstance(row, dict) and isinstance(row.get('key'), str) and _HEX64.fullmatch(str(row.get('revision', '')))
    }
    history_rows, retired_summary = workspace.dependency_history(root)
    by_key_rev = {}
    retired_revs = set()

    # Identify exact (key, revision) pairs recorded in verified retirement archives.
    retired_dir = workspace.child(root, '.retired')
    if retired_dir.exists():
        for path in sorted(workspace.private_dir(retired_dir).glob('*.json')):
            record = workspace.read(path, private=True)
            for row in record.get('retired_tasks', []):
                if isinstance(row, dict) and isinstance(row.get('key'), str) and _HEX64.fullmatch(str(row.get('revision', ''))):
                    retired_revs.add((row['key'], row['revision']))
                    by_key_rev[(row['key'], row['revision'])] = row

    for row in history_rows:
        if isinstance(row, dict) and isinstance(row.get('key'), str) and _HEX64.fullmatch(str(row.get('revision', ''))):
            by_key_rev[(row['key'], row['revision'])] = row

    # Admit signed generation rows ONLY for revisions proven committed by canonical control requests.
    generations_dir = workspace.child(root, '.generations')
    if executed_key_revs and generations_dir.exists():
        for gen_dir in sorted(workspace.private_dir(generations_dir).iterdir()):
            if gen_dir.is_symlink() or not gen_dir.is_dir() or not _HEX32.fullmatch(gen_dir.name):
                continue
            cat_path = gen_dir / 'catalogue.json'
            if cat_path.is_symlink() or not cat_path.is_file():
                continue
            try:
                gen_cat = workspace.read(cat_path, private=True)
                if (not isinstance(gen_cat, dict)
                        or gen_cat.get('schema') != workspace.SCHEMA
                        or gen_cat.get('plugin_id') != catalogue.get('plugin_id')
                        or gen_cat.get('generation') != gen_dir.name
                        or not hmac.compare_digest(
                            str(gen_cat.get('signature', '')),
                            workspace.sign_catalogue(root, gen_cat)['signature'],
                        )):
                    continue
            except (ValueError, OSError, KeyError, TypeError):
                continue
            for row in list(gen_cat.get('dependency_artifacts', [])) + list(gen_cat.get('tasks', [])):
                if not isinstance(row, dict) or not isinstance(row.get('key'), str) or not _HEX64.fullmatch(str(row.get('revision', ''))):
                    continue
                pair = (row['key'], row['revision'])
                if pair in executed_key_revs:
                    by_key_rev.setdefault(pair, row)

    for key, row in active_by_key.items():
        by_key_rev[(key, row['revision'])] = row

    def binding_for(task_key, rev, *, dependency_edge=False):
        current_row = active_by_key.get(task_key)
        if current_row and current_row.get('revision') == rev:
            return 'current'
        if (task_key, rev) in retired_revs or (task_key in retired_summary and retired_summary[task_key].get('revision') == rev):
            return 'retired'
        if (task_key, rev) in by_key_rev:
            return 'pinned-historical'
        return 'orphan' if dependency_edge else 'unknown'

    return active_by_key, by_key_rev, retired_revs, binding_for


def _verified_task_folder(root, task_row):
    """Verify private path, symlink absence, and pinned bundle hashes before reading nested artifacts."""
    immutable = {
        key: value
        for key, value in task_row.items()
        if key not in ('generator_args', 'source_input_pins', 'input_root')
    }
    bundle = workspace.task_artifacts(root, immutable)
    folder = workspace.private_dir(workspace.child(root, task_row['artifact_dir']))
    return folder, bundle


def _read_verified_task_artifact(root, task_row):
    """Return (artifact_name, artifact_sha256, parsed_json) for a verified task revision."""
    folder, _bundle = _verified_task_folder(root, task_row)
    kind = task_row.get('kind')
    artifact_name = TASK_ARTIFACTS.get(kind)
    if not artifact_name:
        return None, None, None
    artifact_path = workspace.child(folder, artifact_name)
    if not artifact_path.exists():
        raise FileNotFoundError(artifact_name)
    raw = workspace.regular(artifact_path, private=True, limit=workspace.MAX_BYTES).read_bytes()
    sha = workspace.digest(raw)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError('Task artifact must be a JSON object')
    return artifact_name, sha, parsed


def _same_scope_operations(requests_dir, file_key, page_id, control_schema):
    """Load canonical requests strictly matching (file_key, page_id)."""
    ops = []
    for path in requests_dir.glob('*.json'):
        if path.is_symlink() or not _HEX32.fullmatch(path.stem) or path.name != path.stem + '.json':
            continue
        try:
            req = workspace.read(path, private=True, limit=32768)
        except (ValueError, OSError):
            continue
        if (not isinstance(req, dict)
                or req.get('schema') != control_schema
                or req.get('id') != path.stem
                or req.get('file_key') != file_key
                or req.get('page_id') != page_id
                or req.get('operation') not in ALLOWED_OPERATIONS
                or not isinstance(req.get('key'), str)
                or not _TASK_KEY.fullmatch(req['key'])
                or not isinstance(req.get('revision'), str)
                or not _HEX64.fullmatch(req['revision'])):
            continue
        created_at = req.get('created_at')
        sort_time = float(created_at) if isinstance(created_at, (int, float)) and not isinstance(created_at, bool) else 0.0
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        ops.append((sort_time, mtime_ns, req['id'], req))
    ops.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in ops]


def _extract_sync_map(plan):
    entries = {}
    tokens = plan.get('tokens')
    if isinstance(tokens, list):
        for idx, token in enumerate(tokens, 1):
            if not isinstance(token, dict):
                continue
            raw_key = token.get('key') or token.get('variable_name')
            key = _safe_semantic_key(raw_key, 'token', idx)
            norm = _normalize_design_value('value', token.get('value'))
            if norm is not None:
                entries[(key, 'value')] = norm
    components = plan.get('components')
    if isinstance(components, list):
        for idx, comp in enumerate(components, 1):
            if not isinstance(comp, dict):
                continue
            comp_key = _safe_semantic_key(comp.get('id'), 'component', idx)
            props = comp.get('properties')
            if isinstance(props, dict):
                for field, token_ref in sorted(props.items()):
                    if field not in ALLOWED_DESIGN_FIELDS:
                        continue
                    norm = _normalize_design_value(field, token_ref)
                    if norm is not None:
                        entries[(f'component:{comp_key}', field)] = norm
    return entries


def _flatten_import_tokens(node, prefix, entries):
    if not isinstance(node, dict):
        return
    if '$value' in node:
        token_type = node.get('$type')
        field = 'characters' if token_type in {'text'} else 'value'
        key = _safe_semantic_key(prefix, 'token', len(entries) + 1)
        norm = _normalize_design_value(field, node.get('$value'))
        if norm is not None:
            entries[(key, field)] = norm
        return
    for child_name, child_val in sorted(node.items()):
        if child_name.startswith('$') or not isinstance(child_name, str):
            continue
        next_prefix = f'{prefix}.{child_name}' if prefix else child_name
        _flatten_import_tokens(child_val, next_prefix, entries)


def _extract_import_map(payload):
    entries = {}
    tokens = payload.get('tokens')
    if isinstance(tokens, dict):
        _flatten_import_tokens(tokens, '', entries)
    components = payload.get('components')
    if isinstance(components, dict):
        for comp_idx, (comp_name, comp_def) in enumerate(sorted(components.items()), 1):
            if not isinstance(comp_def, dict):
                continue
            comp_key = _safe_semantic_key(comp_name, 'component', comp_idx)
            variants = comp_def.get('variants')
            if isinstance(variants, dict):
                for var_name, var_props in sorted(variants.items()):
                    if not isinstance(var_props, dict):
                        continue
                    var_key = _safe_semantic_key(f'{comp_key}.{var_name}', 'variant', comp_idx)
                    for field, val in sorted(var_props.items()):
                        if field not in ALLOWED_DESIGN_FIELDS:
                            continue
                        norm = _normalize_design_value(field, val)
                        if norm is not None:
                            entries[(var_key, field)] = norm
            declared_props = comp_def.get('properties')
            if isinstance(declared_props, dict):
                for prop_name, prop_spec in sorted(declared_props.items()):
                    if not isinstance(prop_spec, dict):
                        continue
                    prop_type = prop_spec.get('type')
                    target = _safe_semantic_key(prop_spec.get('target') or prop_name, 'prop', comp_idx)
                    if prop_type == 'TEXT':
                        entries[(f'{comp_key}.{target}', 'characters')] = _text_token(prop_spec.get('default_value', ''))
                    elif prop_type == 'BOOLEAN':
                        norm = _normalize_design_value('boolean', prop_spec.get('default_value'))
                        if norm is not None:
                            entries[(f'{comp_key}.{target}', 'boolean')] = norm
                    elif prop_type == 'INSTANCE_SWAP':
                        norm = _normalize_design_value('instanceSwap', prop_spec.get('default_value'))
                        if norm is not None:
                            entries[(f'{comp_key}.{target}', 'instanceSwap')] = norm
    screens = payload.get('screens')
    if isinstance(screens, list):
        for s_idx, screen in enumerate(screens, 1):
            if not isinstance(screen, dict):
                continue
            screen_key = _safe_semantic_key(screen.get('id'), 'screen', s_idx)
            if 'title' in screen and isinstance(screen.get('title'), str):
                entries[(screen_key, 'characters')] = _text_token(screen['title'])
            elements = screen.get('elements')
            if isinstance(elements, list):
                for e_idx, element in enumerate(elements, 1):
                    if not isinstance(element, dict):
                        continue
                    elem_id = element.get('id') or element.get('key') or f'{element.get("kind", "el")}-{e_idx}'
                    elem_key = _safe_semantic_key(f'{screen_key}/{elem_id}', 'element', e_idx)
                    if isinstance(element.get('text'), str):
                        entries[(elem_key, 'characters')] = _text_token(element['text'])
                    for field, val in sorted(element.items()):
                        if field in {'id', 'key', 'kind', 'text', 'children'} or field not in ALLOWED_DESIGN_FIELDS:
                            continue
                        norm = _normalize_design_value(field, val)
                        if norm is not None:
                            entries[(elem_key, field)] = norm
    return entries


def _extract_native_edit_map(plan, node_rank_map, var_rank_map):
    entries = {}
    if isinstance(plan.get('edits'), list):
        for row in plan['edits']:
            if not isinstance(row, dict):
                continue
            node_id = row.get('node_id')
            field = row.get('field')
            if not isinstance(node_id, str) or not isinstance(field, str) or field not in ALLOWED_DESIGN_FIELDS:
                continue
            rank = node_rank_map.setdefault(node_id, len(node_rank_map) + 1)
            norm = _normalize_design_value(field, row.get('after'))
            if norm is not None:
                entries[(f'target:node#{rank}', field)] = norm
    if isinstance(plan.get('variableedit'), dict):
        row = plan['variableedit']
        var_key = (str(row.get('variable_id', '')), str(row.get('mode_id', '')))
        rank = var_rank_map.setdefault(var_key, len(var_rank_map) + 1)
        norm = _normalize_design_value('value', row.get('after'))
        if norm is not None:
            entries[(f'target:variable#{rank}', 'value')] = norm
    if isinstance(plan.get('provision'), dict):
        prov = plan['provision']
        frame_key = _safe_semantic_key(prov.get('frame_key'), 'frame', 1)
        for src_field, dst_field in (('background_color', 'backgroundColor'), ('text_color', 'color')):
            if src_field in prov:
                norm = _normalize_design_value(dst_field, prov[src_field])
                if norm is not None:
                    entries[(frame_key, dst_field)] = norm
        if isinstance(prov.get('position'), dict):
            for axis in ('x', 'y'):
                if axis in prov['position']:
                    norm = _normalize_design_value(axis, prov['position'][axis])
                    if norm is not None:
                        entries[(frame_key, axis)] = norm
        if isinstance(prov.get('labels'), dict):
            for label_idx, (label_key, label_val) in enumerate(sorted(prov['labels'].items()), 1):
                safe_k = _safe_semantic_key(f'{frame_key}/{label_key}', 'label', label_idx)
                entries[(safe_k, 'characters')] = _text_token(label_val)
    if isinstance(plan.get('web_design'), dict):
        screens = plan['web_design'].get('screens')
        if isinstance(screens, list):
            for s_idx, screen in enumerate(screens, 1):
                if not isinstance(screen, dict):
                    continue
                s_key = _safe_semantic_key(screen.get('screenId') or screen.get('id'), 'screen', s_idx)
                if isinstance(screen.get('title'), str):
                    entries[(s_key, 'characters')] = _text_token(screen['title'])
                for field in ('width', 'height', 'backgroundColor', 'gap', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft'):
                    if field in screen:
                        norm = _normalize_design_value(field, screen[field])
                        if norm is not None:
                            entries[(s_key, field)] = norm
    if isinstance(plan.get('specifications'), dict):
        specs = plan['specifications'].get('items') or plan['specifications'].get('elements')
        if isinstance(specs, list):
            for idx, item in enumerate(specs, 1):
                if not isinstance(item, dict):
                    continue
                item_key = _safe_semantic_key(item.get('key') or item.get('id'), 'spec', idx)
                if 'display_text' in item:
                    entries[(item_key, 'characters')] = _text_token(item.get('display_text', ''))
                for field, val in sorted(item.items()):
                    if field in {'key', 'id', 'display_text'} or field not in ALLOWED_DESIGN_FIELDS:
                        continue
                    norm = _normalize_design_value(field, val)
                    if norm is not None:
                        entries[(item_key, field)] = norm
    return entries


def _diff_maps(before_map, after_map):
    all_keys = sorted(set(before_map) | set(after_map))
    rows = []
    for key, field in all_keys:
        in_before = (key, field) in before_map
        in_after = (key, field) in after_map
        if in_before and not in_after:
            b_tok = before_map[(key, field)]
            rows.append({
                'key': key,
                'field': field,
                'kind': 'removed',
                'before': _public_value(b_tok),
                'after': None,
            })
        elif in_after and not in_before:
            a_tok = after_map[(key, field)]
            rows.append({
                'key': key,
                'field': field,
                'kind': 'added',
                'before': None,
                'after': _public_value(a_tok),
            })
        else:
            b_tok = before_map[(key, field)]
            a_tok = after_map[(key, field)]
            if _same_design_token(b_tok, a_tok):
                continue
            kind = 'type-changed' if _value_kind(b_tok) != _value_kind(a_tok) else 'changed'
            rows.append({
                'key': key,
                'field': field,
                'kind': kind,
                'before': _public_value(b_tok, a_tok),
                'after': _public_value(a_tok, b_tok),
            })
    return rows


def _extract_redacted_conflicts(root, request, conflict_detail_fn):
    """Extract bounded, strictly redacted conflict rows from the operation's own readback."""
    if not request.get('readback'):
        return [], False
    try:
        control_dir = workspace.private_dir(workspace.child(root, '.control'))
        readbacks_dir = workspace.private_dir(workspace.child(control_dir, 'readbacks'))
        readback_path = workspace.child(readbacks_dir, request['id'] + '.json')
        if not readback_path.exists():
            return [], False
        raw = workspace.regular(readback_path, private=True, limit=32 * 1024 * 1024).read_bytes()
        parsed = json.loads(raw)
        detail = conflict_detail_fn(parsed)
    except (ValueError, OSError, KeyError, TypeError):
        return [], False

    node_ranks = {}
    redacted_rows = []
    raw_conflicts = detail.get('conflicts', [])
    raw_ops = parsed.get('native_edit', {}).get('operations', []) if isinstance(parsed, dict) else []
    var_targets = {
        op.get('variable_id')
        for op in raw_ops
        if isinstance(op, dict) and isinstance(op.get('variable_id'), str)
    }

    for row in raw_conflicts:
        target = row.get('target', '')
        scope_kind = 'variable' if target in var_targets else 'node'
        rank = node_ranks.setdefault((scope_kind, target), len(node_ranks) + 1)
        safe_target = f'target:{scope_kind}#{rank}'
        raw_field = row.get('field', 'value')
        field = raw_field if raw_field in ALLOWED_DESIGN_FIELDS else ('characters' if raw_field in TEXT_FIELDS else 'value')
        b_tok = _normalize_design_value(field, row.get('before'))
        a_tok = _normalize_design_value(field, row.get('after'))
        o_tok = _normalize_design_value(field, row.get('observed'))
        if b_tok is None:
            b_tok = _text_token(str(row.get('before', '')))
        if a_tok is None:
            a_tok = _text_token(str(row.get('after', '')))
        if o_tok is None:
            o_tok = _text_token(str(row.get('observed', '')))
        raw_reason = str(row.get('rollback', '')).strip().lower()
        reason_code = raw_reason if _REASON_CODE.fullmatch(raw_reason) else 'conflict-detected'
        redacted_rows.append({
            'key': safe_target,
            'scope': scope_kind,
            'field': field,
            'reasonCode': reason_code,
            'planSha256': detail['plan_sha256'],
            'expectedBefore': _public_value(b_tok, o_tok),
            'plannedAfter': _public_value(a_tok, b_tok),
            'observed': _public_value(o_tok, b_tok),
        })

    was_truncated = len(redacted_rows) > MAX_CONFLICTS
    return redacted_rows[:MAX_CONFLICTS], was_truncated


def _compute_diff(root, request, task_row, same_scope_ops, by_key_rev, conflicts, conflicts_truncated):
    """Build deterministic two-revision safe design diff or explicit unavailable envelope."""
    after_rev = request['revision']

    def unavailable(reason):
        if conflicts:
            return {
                'status': 'available',
                'reason': reason,
                'basis': None,
                'beforeRevision': None,
                'afterRevision': after_rev,
                'truncated': conflicts_truncated,
                'totalFields': 0,
                'fields': [],
                'conflicts': conflicts,
            }
        return {
            'status': 'unavailable',
            'reason': reason,
            'basis': None,
            'beforeRevision': None,
            'afterRevision': after_rev,
            'truncated': False,
            'totalFields': 0,
            'fields': [],
            'conflicts': [],
        }

    if request['operation'] == 'read' or (task_row and task_row.get('kind') == 'discover'):
        return unavailable('read-only-operation')
    if task_row is None:
        return unavailable('legacy-or-unpinned-artifact')
    kind = task_row.get('kind')
    if kind not in {'sync', 'native-edit', 'import'}:
        return unavailable('unsupported-task-kind')

    try:
        _after_name, _after_sha, after_data = _read_verified_task_artifact(root, task_row)
    except FileNotFoundError:
        return unavailable('before-artifact-missing')
    except (ValueError, OSError, KeyError, TypeError):
        return unavailable('unverified-artifact')

    # Locate exact preceding canonical revision on the same (file_key, page_id) scope.
    before_rev = None
    for candidate in same_scope_ops:
        if candidate['id'] == request['id']:
            break
        if candidate['key'] == request['key'] and candidate.get('state') == 'ok' and candidate['revision'] != after_rev:
            before_rev = candidate['revision']

    # If sync plan explicitly pins previous_graph_sha256, check verified same-task revisions for exact match.
    if before_rev is None and kind == 'sync' and _HEX64.fullmatch(str(after_data.get('previous_graph_sha256', ''))):
        prev_graph_sha = after_data['previous_graph_sha256']
        for (cand_key, cand_rev), cand_row in sorted(by_key_rev.items()):
            if cand_key != request['key'] or cand_rev == after_rev or cand_row.get('kind') != 'sync':
                continue
            if cand_row.get('fileKey') not in (None, request['file_key']) or cand_row.get('pageId') not in (None, request['page_id']):
                continue
            try:
                _, _, cand_plan = _read_verified_task_artifact(root, cand_row)
            except (FileNotFoundError, ValueError, OSError, KeyError, TypeError):
                continue
            if cand_plan.get('graph_sha256') == prev_graph_sha:
                before_rev = cand_rev
                break

    if before_rev is None:
        return unavailable('before-artifact-missing')

    before_row = by_key_rev.get((request['key'], before_rev))
    if before_row is None or before_row.get('kind') != kind:
        return unavailable('before-artifact-missing')

    try:
        _before_name, _before_sha, before_data = _read_verified_task_artifact(root, before_row)
    except FileNotFoundError:
        return unavailable('before-artifact-missing')
    except (ValueError, OSError, KeyError, TypeError):
        return unavailable('unverified-artifact')

    if kind == 'sync':
        before_map = _extract_sync_map(before_data)
        after_map = _extract_sync_map(after_data)
    elif kind == 'import':
        before_map = _extract_import_map(before_data)
        after_map = _extract_import_map(after_data)
    else:
        node_ranks, var_ranks = {}, {}
        # Pre-seed node and variable ordinals deterministically across both revisions so IDs match without leaking.
        all_node_ids = sorted({
            row['node_id']
            for plan in (before_data, after_data)
            for row in (plan.get('edits') or [])
            if isinstance(row, dict) and isinstance(row.get('node_id'), str)
        })
        for idx, nid in enumerate(all_node_ids, 1):
            node_ranks[nid] = idx
        all_var_ids = sorted({
            (str(plan['variableedit'].get('variable_id', '')), str(plan['variableedit'].get('mode_id', '')))
            for plan in (before_data, after_data)
            if isinstance(plan.get('variableedit'), dict)
        })
        for idx, vid in enumerate(all_var_ids, 1):
            var_ranks[vid] = idx
        before_map = _extract_native_edit_map(before_data, node_ranks, var_ranks)
        after_map = _extract_native_edit_map(after_data, node_ranks, var_ranks)

    all_fields = _diff_maps(before_map, after_map)
    total_fields = len(all_fields)
    fields_truncated = total_fields > MAX_DIFF_FIELDS or conflicts_truncated
    bounded_fields = all_fields[:MAX_DIFF_FIELDS]
    status = 'available' if (bounded_fields or conflicts) else 'empty'
    return {
        'status': status,
        'reason': None,
        'basis': 'revision-pair',
        'beforeRevision': before_rev,
        'afterRevision': after_rev,
        'truncated': fields_truncated,
        'totalFields': total_fields,
        'fields': bounded_fields,
        'conflicts': conflicts,
    }


def _failure_summary(state, request, has_conflicts):
    if state in {'ok', 'pending', 'claimed'}:
        return None
    if state == 'expired':
        return {'code': 'claim-expired', 'action': 'inspect-private-status'}
    if state == 'uncertain':
        return {'code': 'operation-uncertain', 'action': 'run-native-read'}
    if has_conflicts:
        return {'code': 'native-conflict', 'action': 'inspect-conflicts'}
    raw_error = str(request.get('error', '')).lower()
    if 'prepared task' in raw_error or 'stale' in raw_error or 'runtime' in raw_error:
        return {'code': 'result-rejected', 'action': 'reopen-plugin'}
    return {'code': 'execution-failed', 'action': 'inspect-private-status'}


def _build_relations(root, request, task_row, task_binding, active_by_key, by_key_rev, binding_for, same_scope_ops, journal_history_fn):
    relations = []
    seen = set()
    ops_by_id = {op['id']: op for op in same_scope_ops}

    def latest_op_id(t_key, t_rev):
        found = None
        for op in same_scope_ops:
            if op['key'] == t_key and op['revision'] == t_rev:
                found = op['id']
        return found

    # 1. Declared dependencies (predecessors on the exact task revision).
    if task_row and isinstance(task_row.get('depends_on'), list):
        for edge in task_row['depends_on']:
            if not isinstance(edge, dict) or edge.get('relation') != 'uses-output':
                continue
            dep_key = edge.get('task_key')
            dep_rev = edge.get('revision')
            artifact = edge.get('artifact')
            art_sha = edge.get('artifact_sha256')
            if (not isinstance(dep_key, str) or not _TASK_KEY.fullmatch(dep_key)
                    or not isinstance(dep_rev, str) or not _HEX64.fullmatch(dep_rev)
                    or artifact not in {'code.js', 'ui.html', 'manifest.json'}
                    or not isinstance(art_sha, str) or not _HEX64.fullmatch(art_sha)):
                continue
            dedup = ('declared-dependency', 'predecessor', dep_key, dep_rev, artifact, art_sha)
            if dedup in seen:
                continue
            seen.add(dedup)
            dep_binding = binding_for(dep_key, dep_rev, dependency_edge=True)
            pinned_row = by_key_rev.get((dep_key, dep_rev))
            if pinned_row and pinned_row.get('artifact_hashes', {}).get(artifact) != art_sha:
                dep_binding = 'orphan'
            relations.append({
                'type': 'declared-dependency',
                'direction': 'predecessor',
                'taskKey': dep_key,
                'revision': dep_rev,
                'currentRevision': active_by_key[dep_key]['revision'] if dep_key in active_by_key else None,
                'revisionBinding': dep_binding,
                'artifact': artifact,
                'artifactSha256': art_sha,
                'targetOperationId': latest_op_id(dep_key, dep_rev),
            })

    # 2. Declared dependencies (successors pinning this exact taskKey + revision).
    candidate_consumers = list(active_by_key.values()) + [
        by_key_rev[(op['key'], op['revision'])]
        for op in same_scope_ops
        if (op['key'], op['revision']) in by_key_rev
    ]
    for consumer in candidate_consumers:
        if not isinstance(consumer, dict) or not isinstance(consumer.get('depends_on'), list):
            continue
        c_key = consumer.get('key')
        c_rev = consumer.get('revision')
        if not isinstance(c_key, str) or not _TASK_KEY.fullmatch(c_key) or not isinstance(c_rev, str) or not _HEX64.fullmatch(c_rev):
            continue
        for edge in consumer['depends_on']:
            if (not isinstance(edge, dict)
                    or edge.get('relation') != 'uses-output'
                    or edge.get('task_key') != request['key']
                    or edge.get('revision') != request['revision']):
                continue
            artifact = edge.get('artifact')
            art_sha = edge.get('artifact_sha256')
            if artifact not in {'code.js', 'ui.html', 'manifest.json'} or not isinstance(art_sha, str) or not _HEX64.fullmatch(art_sha):
                continue
            dedup = ('declared-dependency', 'successor', c_key, c_rev, artifact, art_sha)
            if dedup in seen:
                continue
            seen.add(dedup)
            relations.append({
                'type': 'declared-dependency',
                'direction': 'successor',
                'taskKey': c_key,
                'revision': c_rev,
                'currentRevision': active_by_key[c_key]['revision'] if c_key in active_by_key else None,
                'revisionBinding': binding_for(c_key, c_rev),
                'artifact': artifact,
                'artifactSha256': art_sha,
                'targetOperationId': latest_op_id(c_key, c_rev),
            })

    # 3. Canonical recovery-of links (strictly from explicit server-recorded recovery_of IDs).
    req_journal = journal_history_fn(request)
    if req_journal['classification'] == 'recorded' and isinstance(request.get('recovery_of'), list):
        for orig_id in request['recovery_of']:
            orig = ops_by_id.get(orig_id)
            if orig is None:
                continue
            dedup = ('recovery-of', 'recovers', orig_id)
            if dedup in seen:
                continue
            seen.add(dedup)
            relations.append({
                'type': 'recovery-of',
                'direction': 'recovers',
                'operationId': orig_id,
                'taskKey': orig['key'],
                'revision': orig['revision'],
                'revisionBinding': binding_for(orig['key'], orig['revision']),
            })

    for other in same_scope_ops:
        if other['id'] == request['id']:
            continue
        other_journal = journal_history_fn(other)
        if other_journal['classification'] != 'recorded' or not isinstance(other.get('recovery_of'), list):
            continue
        if request['id'] in other['recovery_of']:
            dedup = ('recovery-of', 'recovered-by', other['id'])
            if dedup in seen:
                continue
            seen.add(dedup)
            relations.append({
                'type': 'recovery-of',
                'direction': 'recovered-by',
                'operationId': other['id'],
                'taskKey': other['key'],
                'revision': other['revision'],
                'revisionBinding': binding_for(other['key'], other['revision']),
            })

    # 4. Canonical pinned artifact inputs on this exact task revision.
    if task_row is not None:
        try:
            _verified_task_folder(root, task_row)
            pin = task_row.get('input_record')
            if isinstance(pin, dict) and pin.get('artifact') == 'input-record.json' and _HEX64.fullmatch(str(pin.get('sha256', ''))):
                try:
                    workspace.task_input_record(root, task_row)
                    try:
                        freshness = workspace.task_input_freshness(root, task_row)['status']
                    except (ValueError, OSError):
                        freshness = 'unverified'
                    if freshness not in {'current', 'stale', 'unverified'}:
                        freshness = 'unverified'
                    relations.append({
                        'type': 'artifact-input',
                        'taskKey': request['key'],
                        'artifact': 'input-record.json',
                        'artifactSha256': pin['sha256'],
                        'revision': request['revision'],
                        'revisionBinding': task_binding,
                        'freshness': freshness,
                    })
                except (ValueError, OSError):
                    pass
            art_name, art_sha, _ = _read_verified_task_artifact(root, task_row)
            if art_name and art_sha:
                relations.append({
                    'type': 'artifact-input',
                    'taskKey': request['key'],
                    'artifact': art_name,
                    'artifactSha256': art_sha,
                    'revision': request['revision'],
                    'revisionBinding': task_binding,
                    'freshness': 'current' if task_binding == 'current' else 'unverified',
                })
        except (FileNotFoundError, ValueError, OSError, KeyError, TypeError):
            pass

    truncated = len(relations) > MAX_RELATIONS
    return relations[:MAX_RELATIONS], truncated


def _enforce_size_cap(dto):
    encoded = workspace.encode(dto)
    if len(encoded) <= MAX_RESPONSE_BYTES:
        return dto
    dto['truncated'] = True
    dto['scopeNotice'] = 'read-only-truncated-256kib'
    while len(workspace.encode(dto)) > MAX_RESPONSE_BYTES and dto['diff']['fields']:
        half = max(1, len(dto['diff']['fields']) // 2)
        dto['diff']['fields'] = dto['diff']['fields'][:len(dto['diff']['fields']) - half]
        dto['diff']['truncated'] = True
    while len(workspace.encode(dto)) > MAX_RESPONSE_BYTES and dto['diff']['conflicts']:
        dto['diff']['conflicts'].pop()
        dto['diff']['truncated'] = True
    while len(workspace.encode(dto)) > MAX_RESPONSE_BYTES and dto['relations']:
        dto['relations'].pop()
    while len(workspace.encode(dto)) > MAX_RESPONSE_BYTES and len(dto['phases']) > 1:
        dto['phases'] = dto['phases'][-max(1, len(dto['phases']) // 2):]
    if len(workspace.encode(dto)) > MAX_RESPONSE_BYTES:
        raise OperationRejectedError('payload-limit-exceeded')
    return dto


def build_operation_detail(root, payload, *, control_schema, journal_history_fn, conflict_detail_fn):
    """Validate exact scope/runtime/revision binding and return a bounded read-only DTO."""
    _validate_envelope(payload)
    try:
        root_dir = workspace.private_dir(root)
    except (ValueError, OSError) as error:
        raise OperationRejectedError('workspace-unverified') from error

    with workspace.locked(root_dir) as locked_root:
        try:
            catalogue = workspace.current(locked_root, repair=False)
        except (ValueError, OSError, KeyError, TypeError) as error:
            raise OperationRejectedError('workspace-unverified') from error

        if payload['runtime'] != catalogue.get('runtime'):
            raise OperationRejectedError('runtime-mismatch')

        control_path = workspace.child(locked_root, '.control')
        if not control_path.exists():
            raise OperationNotFoundError('not-found-in-scope')
        control_dir = workspace.private_dir(control_path)
        requests_path = workspace.child(control_dir, 'requests')
        if not requests_path.exists():
            raise OperationNotFoundError('not-found-in-scope')
        requests_dir = workspace.private_dir(requests_path)

        req_file = workspace.child(requests_dir, payload['operation_id'] + '.json')
        if not req_file.exists():
            raise OperationNotFoundError('not-found-in-scope')
        request = workspace.read(req_file, private=True, limit=32768)
        if (not isinstance(request, dict)
                or request.get('schema') != control_schema
                or request.get('id') != payload['operation_id']
                or request.get('operation') not in ALLOWED_OPERATIONS
                or not isinstance(request.get('key'), str)
                or not _TASK_KEY.fullmatch(request['key'])
                or not isinstance(request.get('revision'), str)
                or not _HEX64.fullmatch(request['revision'])):
            raise OperationNotFoundError('not-found-in-scope')

        # Scope check MUST precede task_key/revision binding check so foreign-page IDs never leak metadata.
        if request.get('file_key') != payload['file_key'] or request.get('page_id') != payload['page_id']:
            raise OperationNotFoundError('not-found-in-scope')

        if request['key'] != payload['task_key'] or request['revision'] != payload['revision']:
            raise OperationRejectedError('task-revision-mismatch')

        journal = journal_history_fn(request)
        classification = journal['classification']
        if classification == 'recorded':
            all_phases = journal['phases']
            phases_truncated = len(all_phases) > MAX_PHASES
            phases = all_phases[-MAX_PHASES:]
            phase = journal['phase']
        else:
            # Never invent phases for legacy or unknown lifecycle records.
            phases_truncated = False
            phases = []
            phase = 'unknown'

        same_scope_ops = _same_scope_operations(requests_dir, payload['file_key'], payload['page_id'], control_schema)
        executed_key_revs = {(op['key'], op['revision']) for op in same_scope_ops}
        active_by_key, by_key_rev, _retired_revs, binding_for = _collect_verified_task_history(
            locked_root, catalogue, executed_key_revs,
        )
        task_key = request['key']
        revision = request['revision']
        task_row = by_key_rev.get((task_key, revision))
        current_row = active_by_key.get(task_key)
        task_binding = binding_for(task_key, revision)
        raw_kind = task_row.get('kind') if task_row else (current_row.get('kind') if current_row else None)
        task_kind = raw_kind if raw_kind in ALLOWED_TASK_KINDS else None

        conflicts, conflicts_truncated = _extract_redacted_conflicts(locked_root, request, conflict_detail_fn)
        diff = _compute_diff(locked_root, request, task_row, same_scope_ops, by_key_rev, conflicts, conflicts_truncated)
        relations, relations_truncated = _build_relations(
            locked_root, request, task_row, task_binding, active_by_key, by_key_rev,
            binding_for, same_scope_ops, journal_history_fn,
        )

        state = request.get('state') if request.get('state') in ALLOWED_STATES else 'uncertain'
        failure = _failure_summary(state, request, bool(conflicts))
        is_truncated = bool(diff['truncated'] or relations_truncated or phases_truncated)
        scope_notice = 'read-only-diff-capped-at-200-fields' if diff['truncated'] else 'read-only-exact-scope'

        dto = {
            'schema': DETAIL_SCHEMA,
            'readOnly': True,
            'operationId': request['id'],
            'scope': {
                'fileKey': payload['file_key'],
                'pageId': payload['page_id'],
                'runtimeGeneration': payload['runtime']['generation'],
            },
            'operation': request['operation'],
            'state': state,
            'classification': classification,
            'phase': phase,
            'phases': phases,
            'task': {
                'key': task_key,
                'revision': revision,
                'currentRevision': current_row['revision'] if current_row else None,
                'revisionBinding': task_binding,
                'kind': task_kind,
            },
            'failure': failure,
            'relations': relations,
            'diff': diff,
            'truncated': is_truncated,
            'scopeNotice': scope_notice,
        }
        return _enforce_size_cap(dto)
