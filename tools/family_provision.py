#!/usr/bin/env python3
"""Prepare a page-scoped, idempotent NF-01 component families provision plan."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import design_system
from native_handoff import normalize
from native_edit import ID, PLAN_SCHEMA, validate_plan

PROVISION_SCHEMA = 'figma-flow-component-families-provision-v1'
CONTRACT_SCHEMA = 'figma-flow-semantic-family-contract-v1'
DEFAULT_OWNER_KEY = 'nf01.component-families'
DEFAULT_WORKBENCH_NAME = 'NF-01 · Component families workbench'
ALLOWED_FAMILIES = frozenset({'field', 'input', 'checkbox', 'radio', 'table-row', 'table-cell'})
SHA256_RE = re.compile(r'[a-f0-9]{64}\Z')
OWNER_KEY_RE = re.compile(r'[A-Za-z][A-Za-z0-9._:-]{0,119}\Z')
GRAPH_ID_RE = re.compile(r'[A-Za-z0-9._:-]{1,120}\Z')


def _is_finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _regular_local_file(raw_path, *, limit, label):
    if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
        raise ValueError(f'Pinned {label} path is required')
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = candidate.absolute()
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f'Pinned {label} is missing or not a regular file')
    size = candidate.stat().st_size
    if size > limit:
        raise ValueError(f'Pinned {label} exceeds size bound')
    return candidate.resolve()


def _root_projection(row):
    box = row.get('absoluteBoundingBox')
    if (not isinstance(box, dict)
            or set(box) != {'x', 'y', 'width', 'height'}
            or not all(_is_finite_number(box.get(field)) for field in ('x', 'y', 'width', 'height'))):
        raise ValueError(f'Actual top-level bounds required: {row.get("id")}')
    projected = {
        field: row.get(field)
        for field in ('id', 'type', 'name', 'semanticKey', 'x', 'y', 'width', 'height', 'absoluteBoundingBox')
    }
    if (not isinstance(projected['id'], str) or not ID.fullmatch(projected['id'])
            or not isinstance(projected['type'], str) or not isinstance(projected['name'], str)
            or (projected['semanticKey'] is not None and not isinstance(projected['semanticKey'], str))
            or not all(_is_finite_number(projected[field]) for field in ('x', 'y', 'width', 'height'))):
        raise ValueError(f'Invalid existing page root metadata: {row.get("id")}')
    return projected


def _subtree_ids(root_id, parents):
    children_by_parent = {}
    for nid, pid in parents.items():
        if pid is not None:
            children_by_parent.setdefault(pid, []).append(nid)
    owned = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        if cur in owned:
            continue
        owned.add(cur)
        stack.extend(children_by_parent.get(cur, ()))
    return owned


def _workbench_bounds(contract):
    set_count = len(contract.get('componentSets') or ())
    inst_count = len(contract.get('instances') or ())
    return {
        'width': 1280,
        'height': max(720, 220 * set_count + 104 * inst_count + 96),
    }


def _load_sources(graph_path):
    source_file = _regular_local_file(graph_path, limit=12_000_000, label='source graph')
    source_bytes = source_file.read_bytes()
    graph_sha256 = hashlib.sha256(source_bytes).hexdigest()
    try:
        doc = json.loads(source_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Pinned source graph is not valid UTF-8 JSON') from error
    if not isinstance(doc, dict):
        raise ValueError('Pinned source graph must be a JSON object')

    has_inline_families = (
        'componentFamilies' in doc
        or 'component_families_design' in doc
        or (isinstance(doc.get('design_system'), dict) and (
            'componentFamilies' in doc['design_system'] or 'family_design' in doc['design_system']
        ))
    )
    design_file = None
    design_sha256 = None
    compile_source = doc
    if 'design_source' in doc and not has_inline_families:
        rel = doc['design_source']
        if not isinstance(rel, str) or not rel.strip():
            raise ValueError('design_source must be a relative local path')
        rel_path = Path(rel)
        if rel_path.is_absolute() or '..' in rel_path.parts:
            raise ValueError('design_source must stay within the graph directory')
        joined = source_file.parent / rel_path
        if joined.is_symlink():
            raise ValueError('design_source must not be a symlink')
        resolved_design = _regular_local_file(joined, limit=12_000_000, label='design_source')
        if not resolved_design.is_relative_to(source_file.parent):
            raise ValueError('design_source escaped the graph directory')
        design_bytes = resolved_design.read_bytes()
        design_sha256 = hashlib.sha256(design_bytes).hexdigest()
        try:
            compile_source = json.loads(design_bytes.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError('Pinned design_source is not valid UTF-8 JSON') from error
        if not isinstance(compile_source, dict):
            raise ValueError('Pinned design_source must be a JSON object')
        design_file = resolved_design

    raw_id = doc.get('id')
    if raw_id is None:
        graph_id = 'nf01-component-families'
    elif isinstance(raw_id, str) and GRAPH_ID_RE.fullmatch(raw_id):
        graph_id = raw_id
    else:
        raise ValueError('Graph id must be a bounded safe identifier')
    return source_file, graph_sha256, design_file, design_sha256, graph_id, compile_source


def _inspect_readback(readback_path, file_key, page_id, owner_key):
    rb_file = _regular_local_file(readback_path, limit=24_000_000, label='native discovery readback')
    rb_bytes = rb_file.read_bytes()
    rb_sha256 = hashlib.sha256(rb_bytes).hexdigest()
    try:
        readback = json.loads(rb_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Pinned native discovery readback is not valid UTF-8 JSON') from error
    if (not isinstance(readback, dict)
            or readback.get('schema') != 'figma-flow-graph-native-discovery-v1'
            or readback.get('fileKey') != file_key
            or readback.get('pageId') != page_id
            or readback.get('allowed_page_ids') != [page_id]
            or not isinstance(readback.get('nodes'), list)):
        raise ValueError('Full native discovery must match the exact file and existing page')

    nodes, parents = normalize(readback)
    page = nodes.get(page_id)
    if not page or page.get('type') != 'PAGE':
        raise ValueError('Actual selected native page is absent from full discovery')

    frame_key = f'{owner_key}/workbench'
    owned_frames = [
        row for row in readback['nodes']
        if isinstance(row, dict) and (row.get('semanticKey') or row.get('key')) == frame_key
    ]
    if len(owned_frames) > 1:
        raise ValueError('Duplicate owned component families workbench frame key')
    frame = owned_frames[0] if owned_frames else None
    if frame is not None:
        if parents.get(frame.get('id')) != page_id or frame.get('type') != 'FRAME':
            raise ValueError('Existing component families workbench key belongs to another parent or node type')
        box = frame.get('absoluteBoundingBox')
        if (not isinstance(box, dict)
                or not all(_is_finite_number(box.get(k)) for k in ('x', 'y', 'width', 'height'))):
            raise ValueError('Existing owned component families workbench bounds are required')
        fx = frame['x'] if _is_finite_number(frame.get('x')) else box['x']
        fy = frame['y'] if _is_finite_number(frame.get('y')) else box['y']
        position = {'x': fx, 'y': fy}
        owned_ids = _subtree_ids(frame['id'], parents)
    else:
        owned_ids = set()
        position = None

    root_rows = [
        _root_projection(row)
        for row in readback['nodes']
        if isinstance(row, dict)
        and parents.get(row.get('id')) == page_id
        and row.get('id') != (frame or {}).get('id')
    ]
    root_rows.sort(key=lambda row: row['id'])
    if len(root_rows) > 4000:
        raise ValueError('Bounded existing page root snapshot required')
    seen_ids = set()
    for row in root_rows:
        if row['id'] in seen_ids:
            raise ValueError('Duplicate existing page root ID in discovery readback')
        seen_ids.add(row['id'])

    if position is None:
        if root_rows:
            position = {
                'x': max(row['absoluteBoundingBox']['x'] + row['absoluteBoundingBox']['width'] for row in root_rows) + 96,
                'y': 0,
            }
        else:
            position = {'x': 0, 'y': 0}

    return rb_file, rb_sha256, readback, frame, owned_ids, root_rows, position


def _compile_and_verify_contract(compile_source, readback, owned_ids, *, owner_key, workbench_name, position):
    if not hasattr(design_system, 'compile_graph_component_families'):
        raise ValueError('Core design_system.compile_graph_component_families is required for NF-01 provisioning')
    contract = design_system.compile_graph_component_families(
        compile_source,
        owner_key=owner_key,
        workbench_name=workbench_name,
        position=position,
    )
    if (not isinstance(contract, dict)
            or contract.get('schema') != CONTRACT_SCHEMA
            or contract.get('version') != 1
            or contract.get('mode') != 'additive-family-workbench'
            or contract.get('ownerKey') != owner_key):
        raise ValueError('Core compiler returned an unsupported semantic family contract')
    csets = contract.get('componentSets')
    insts = contract.get('instances')
    if not isinstance(csets, list) or not 1 <= len(csets) <= 6:
        raise ValueError('Provisioning requires 1–6 canonical component family sets')
    for cset in csets:
        if not isinstance(cset, dict) or cset.get('family') not in ALLOWED_FAMILIES:
            raise ValueError(f'Unsupported component family in compiled contract: {(cset or {}).get("family")!r}')
    if not isinstance(insts, list) or not 1 <= len(insts) <= 512:
        raise ValueError('Provisioning requires at least one declared component family instance')

    wb = contract.get('workbench') or {}
    reserved_keys = {
        wb.get('frameKey'),
        wb.get('libraryKey'),
        wb.get('instancesFrameKey'),
    }
    for cset in csets:
        reserved_keys.add(cset.get('id'))
        reserved_keys.add(f"component.{cset.get('id')}")
        for variant in cset.get('variants') or ():
            reserved_keys.add(variant.get('key'))
            reserved_keys.add(f"component.{variant.get('key')}")
    for inst in insts:
        reserved_keys.add(inst.get('key'))
    reserved_keys.discard(None)

    owner_prefix = f'{owner_key}/'
    comp_owner_prefix = f'component.{owner_key}/'
    for row in readback['nodes']:
        if not isinstance(row, dict) or row.get('id') in owned_ids:
            continue
        sk = row.get('semanticKey') or row.get('key')
        if isinstance(sk, str) and (sk in reserved_keys or sk.startswith(owner_prefix) or sk.startswith(comp_owner_prefix)):
            raise ValueError(f'Component family semantic key is already used outside the owned workbench: {sk}')
    return contract


def _build_provision_dict(graph_path, readback_path, file_key, page_id, *, owner_key, workbench_name):
    if not isinstance(owner_key, str) or not OWNER_KEY_RE.fullmatch(owner_key):
        raise ValueError('Bounded safe owner_key required')
    if not isinstance(workbench_name, str) or not workbench_name.strip() or len(workbench_name) > 120:
        raise ValueError('Bounded workbench_name required')

    source_file, graph_sha256, design_file, design_sha256, graph_id, compile_source = _load_sources(graph_path)
    rb_file, rb_sha256, readback, frame, owned_ids, root_rows, position = _inspect_readback(
        readback_path, file_key, page_id, owner_key
    )
    contract = _compile_and_verify_contract(
        compile_source,
        readback,
        owned_ids,
        owner_key=owner_key,
        workbench_name=workbench_name,
        position=position,
    )
    provision = {
        'schema': PROVISION_SCHEMA,
        'graph_id': graph_id,
        'source_graph_path': str(source_file),
        'graph_sha256': graph_sha256,
        'readback_path': str(rb_file),
        'readback_sha256': rb_sha256,
        'owner_key': owner_key,
        'frame_key': f'{owner_key}/workbench',
        'position': position,
        'workbench_bounds': _workbench_bounds(contract),
        'page_roots': root_rows,
        'contract': contract,
    }
    if design_file is not None:
        provision['design_source_path'] = str(design_file)
        provision['design_source_sha256'] = design_sha256
    return provision, frame is not None


def validate_provision(plan):
    provision = plan.get('provision')
    required = {
        'schema',
        'graph_id',
        'source_graph_path',
        'graph_sha256',
        'readback_path',
        'readback_sha256',
        'owner_key',
        'frame_key',
        'position',
        'workbench_bounds',
        'page_roots',
        'contract',
    }
    design_pair = {'design_source_path', 'design_source_sha256'}
    if (not isinstance(provision, dict)
            or provision.get('schema') != PROVISION_SCHEMA
            or set(provision) not in (required, required | design_pair)):
        raise ValueError('Exact NF-01 component families provision contract required')

    pin_pairs = [
        ('source_graph_path', 'graph_sha256'),
        ('readback_path', 'readback_sha256'),
    ]
    if 'design_source_path' in provision:
        pin_pairs.append(('design_source_path', 'design_source_sha256'))

    for path_field, sha_field in pin_pairs:
        raw_path = provision[path_field]
        expected_sha = provision[sha_field]
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ValueError(f'Absolute pinned path required: {path_field}')
        if not isinstance(expected_sha, str) or not SHA256_RE.fullmatch(expected_sha):
            raise ValueError(f'Valid pinned {sha_field} required')
        resolved = _regular_local_file(raw_path, limit=24_000_000, label=path_field)
        if str(resolved) != raw_path or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected_sha:
            raise ValueError(f'Pinned NF-01 provision source changed or is unavailable: {path_field}')

    contract = provision['contract']
    if not isinstance(contract, dict) or not isinstance(contract.get('workbench'), dict):
        raise ValueError('Valid compiled semantic family contract required')
    workbench_name = contract['workbench'].get('name')
    expected_provision, _ = _build_provision_dict(
        provision['source_graph_path'],
        provision['readback_path'],
        plan['file_key'],
        plan['page_id'],
        owner_key=provision['owner_key'],
        workbench_name=workbench_name,
    )
    if 'design_source_path' in expected_provision and provision.get('design_source_path') != expected_provision['design_source_path']:
        raise ValueError('Pinned design_source_path differs from source graph resolution')
    if ('design_source_path' in provision) != ('design_source_path' in expected_provision):
        raise ValueError('Unexpected or missing design_source pin on provision plan')
    if not all(_is_finite_number(provision['position'].get(k)) for k in ('x', 'y')):
        raise ValueError('Finite workbench position required')
    if not all(_is_finite_number(provision['workbench_bounds'].get(k)) for k in ('width', 'height')):
        raise ValueError('Finite workbench bounds required')
    if json.dumps(provision, sort_keys=True) != json.dumps(expected_provision, sort_keys=True):
        raise ValueError('Component families provision plan differs from its pinned canonical sources')
    return plan


def prepare(
    graph_path,
    readback_path,
    file_key,
    page_id,
    out,
    *,
    owner_key=DEFAULT_OWNER_KEY,
    workbench_name=DEFAULT_WORKBENCH_NAME,
):
    if not isinstance(file_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file_key):
        raise ValueError('Exact safe native file_key required')
    if not isinstance(page_id, str) or not ID.fullmatch(page_id):
        raise ValueError('Exact safe native page_id required')

    output = Path(out).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing to overwrite existing provision plan: {output}')
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError('Provision plan parent must be an existing local directory')

    provision, existing_workbench = _build_provision_dict(
        graph_path,
        readback_path,
        file_key,
        page_id,
        owner_key=owner_key,
        workbench_name=workbench_name,
    )
    plan = {
        'schema': PLAN_SCHEMA,
        'file_key': file_key,
        'page_id': page_id,
        'provision': provision,
    }
    validate_plan(plan)
    output.write_text(json.dumps(plan, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    output.chmod(0o600)
    contract = provision['contract']
    receipt = {
        'plan': str(output),
        'file_key': file_key,
        'page_id': page_id,
        'graph_id': provision['graph_id'],
        'graph_sha256': provision['graph_sha256'],
        'readback_sha256': provision['readback_sha256'],
        'owner_key': owner_key,
        'frame_key': provision['frame_key'],
        'families': [cset['family'] for cset in contract['componentSets']],
        'instance_count': len(contract['instances']),
        'existing_workbench': existing_workbench,
        'position': provision['position'],
        'status': 'prepared-not-executed',
    }
    if 'design_source_sha256' in provision:
        receipt['design_source_sha256'] = provision['design_source_sha256']
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare')
    build.add_argument('--graph', required=True, help='Canonical graph.json or design.json with componentFamilies')
    build.add_argument('--readback', required=True, help='Full current-page native discovery JSON')
    build.add_argument('--file-key', required=True)
    build.add_argument('--page-id', required=True)
    build.add_argument('--out', required=True)
    build.add_argument('--owner-key', default=DEFAULT_OWNER_KEY)
    build.add_argument('--workbench-name', default=DEFAULT_WORKBENCH_NAME)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(
            args.graph,
            args.readback,
            args.file_key,
            args.page_id,
            args.out,
            owner_key=args.owner_key,
            workbench_name=args.workbench_name,
        ), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'status': 'blocked', 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
