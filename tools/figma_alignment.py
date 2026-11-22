#!/usr/bin/env python3
"""Compare explicit Design node edges using a signed viewer readback receipt."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

NODE_ID = re.compile(r'I?\d+:\d+(?:;\d+:\d+)*\Z', re.ASCII)
EDGES = {'start': 0.0, 'center': 0.5, 'end': 1.0}


def load_receipt(path):
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode('utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f'Cannot read JSON receipt: {error}') from error
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON readback receipt')
    if value.get('schema') == 'figma-flow-viewer-result-v1' and value.get('operation') == 'selection-info':
        value['_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
        return value
    if value.get('schema') == 'figma-flow-graph-native-discovery-v1':
        value['_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
        return value
    raise ValueError('Expected a selection-info or native-discovery readback receipt')


def edge(box, axis, edge_name):
    start = box['x' if axis == 'x' else 'y']
    size = box['width' if axis == 'x' else 'height']
    return start + size * EDGES[edge_name]


def compare(receipt, file_key, page_id, anchor_id, target_ids, axis, anchor_edge, target_edge, tolerance,
            expected_offset=0.0):
    if receipt.get('fileKey') != file_key or receipt.get('pageId') != page_id:
        raise ValueError('Receipt file or page does not match the explicitly requested scope')
    geometry = receipt.get('geometry')
    if geometry is not None and not isinstance(geometry, dict):
        raise ValueError('Receipt geometry field is malformed')
    rows = geometry.get('nodes') if isinstance(geometry, dict) else None
    if rows is None and receipt.get('schema') == 'figma-flow-graph-native-discovery-v1':
        rows = receipt.get('nodes')
    if geometry and geometry.get('coordinate_space') not in (None, 'page-absolute-axis-aligned'):
        raise ValueError('Unsupported geometry coordinate space')
    if not isinstance(rows, list):
        rows = []
    ids = [row.get('id') for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)]
    if len(ids) != len(rows) or len(ids) != len(set(ids)):
        raise ValueError('Receipt geometry contains missing or duplicate node IDs')
    by_id = {row['id']: row for row in rows}

    def observed(node_id):
        row = by_id.get(node_id)
        box = row.get('absoluteBoundingBox') if row else None
        if not row or row.get('status') == 'missing':
            return None, 'missing'
        status = row.get('status')
        legacy_box = receipt.get('schema') == 'figma-flow-graph-native-discovery-v1' and status is None
        if (status != 'observed' and not legacy_box) or not isinstance(box, dict) or any(
            isinstance(box.get(key), bool) or not isinstance(box.get(key), (int, float)) or not math.isfinite(box[key])
            for key in ('x', 'y', 'width', 'height')
        ) or box['width'] < 0 or box['height'] < 0:
            return None, 'unmeasurable'
        return (edge(box, axis, anchor_edge), row), None

    anchor_result, anchor_error = observed(anchor_id)
    output = []
    for target_id in target_ids:
        base = {'anchor_id': anchor_id, 'target_id': target_id, 'axis': axis,
                'anchor_edge': anchor_edge, 'target_edge': target_edge,
                'tolerance': tolerance, 'coordinate_space': 'page-absolute-axis-aligned'}
        if anchor_error:
            output.append({**base, 'status': 'missing_anchor' if anchor_error == 'missing' else 'unmeasurable_anchor'})
            continue
        target_result, target_error = observed(target_id)
        if target_error:
            output.append({**base, 'status': 'missing_target' if target_error == 'missing' else 'unmeasurable_target'})
            continue
        anchor_value, anchor_row = anchor_result
        target_value = edge(target_result[1]['absoluteBoundingBox'], axis, target_edge)
        delta = target_value - anchor_value
        deviation = delta - expected_offset
        pair_rows = (anchor_row, target_result[1])
        rotation_known = all(not isinstance(row.get('rotation'), bool) and
                             isinstance(row.get('rotation'), (int, float)) and math.isfinite(row['rotation'])
                             for row in pair_rows)
        rotated = (any(abs(row['rotation'] % 360) > 1e-6 for row in pair_rows)
                   if rotation_known else None)
        aligned = abs(deviation) <= tolerance
        axis_bounds = rotated is not False
        status = (('rotated_' if rotated else '') + ('aligned_axis_aligned_bounds' if aligned else 'drift_axis_aligned_bounds')
                  if axis_bounds else ('aligned' if aligned else 'drift'))
        output.append({**base, 'anchor_value': anchor_value, 'target_value': target_value,
                       'delta': delta, 'expected_offset': expected_offset, 'deviation': deviation,
                       'absolute_deviation': abs(deviation), 'status': status,
                       'rotated': rotated, 'rotation_known': rotation_known,
                       'edge_basis': 'axis-aligned absoluteBoundingBox'})
    unverified = any(row['status'].startswith(('missing_', 'unmeasurable_')) for row in output)
    drift = any('drift' in row['status'] for row in output)
    overall = 'unverified' if unverified else 'drift' if drift else 'aligned'
    return {'schema': 'figma-flow-alignment-report-v1', 'file_key': file_key, 'page_id': page_id,
            'receipt_sha256': receipt.get('_receipt_sha256'),
            'axis': axis, 'anchor_id': anchor_id, 'target_ids': target_ids,
            'results': output, 'status': overall}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check', help='Compare explicit node edges from one selection-info receipt')
    check.add_argument('--receipt', required=True, help='Path to the latest signed selection-info result JSON')
    check.add_argument('--file-key', required=True)
    check.add_argument('--page-id', required=True)
    check.add_argument('--anchor-id', required=True)
    check.add_argument('--target-id', action='append', required=True)
    check.add_argument('--axis', choices=('x', 'y'), required=True)
    check.add_argument('--anchor-edge', choices=tuple(EDGES), required=True)
    check.add_argument('--target-edge', choices=tuple(EDGES), required=True)
    check.add_argument('--tolerance', type=float, required=True)
    check.add_argument('--expected-offset', type=float, default=0.0,
                       help='Signed target-edge minus anchor-edge offset in pixels (default: 0)')
    args = parser.parse_args(argv)
    try:
        ids = [args.anchor_id, *args.target_id]
        if len(ids) > 20 or any(not NODE_ID.fullmatch(value) for value in ids) or len(set(ids)) != len(ids):
            raise ValueError('Use up to 20 unique exact node IDs for anchor and targets')
        if isinstance(args.tolerance, bool) or not math.isfinite(args.tolerance) or args.tolerance < 0:
            raise ValueError('Tolerance must be a finite nonnegative number')
        if not math.isfinite(args.expected_offset):
            raise ValueError('Expected offset must be finite')
        receipt = load_receipt(args.receipt)
        report = compare(receipt, args.file_key, args.page_id, args.anchor_id, args.target_id,
                         args.axis, args.anchor_edge, args.target_edge, args.tolerance, args.expected_offset)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return {'aligned': 0, 'drift': 1, 'unverified': 2}[report['status']]
    except (OSError, ValueError) as error:
        print(json.dumps({'schema': 'figma-flow-alignment-report-v1', 'status': 'error', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
