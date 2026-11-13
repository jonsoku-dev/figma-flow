"""Verify two designer-specified button families using private, screen-scoped Figma receipts."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def verify(graph_path, receipt_path, pairs, drift_path=None, drift_element=None):
    raw = graph_path.read_bytes()
    digest, graph = hashlib.sha256(raw).hexdigest(), json.loads(raw)
    if len(pairs) < 2 or len({e for pair in pairs for e in pair}) != 2 * len(pairs):
        raise ValueError('Specify at least two disjoint main/instance element ID pairs')
    ids = {e for pair in pairs for e in pair}
    screens = [s for s in graph['nodes'] if s['type'] == 'screen' and
               ids <= {e['id'] for e in s['elements'] if e['kind'] == 'component'}]
    if len(screens) != 1:
        raise ValueError('Expected pairs must identify one captured screen')
    screen, = screens
    expected = {e['id']: e['text']['letterSpacing'] for e in screen['elements'] if e['id'] in ids}

    def read(path):
        record = json.loads(path.read_bytes())
        design = record['web_design']
        if (record['schema'] != 'figma-flow-web-screen-discovery-v1' or record['readback_scope'] != 'screens'
                or record['graph_sha256'] != digest or design['graph_sha256'] != digest or design['graph_id'] != graph['id']):
            raise ValueError('Receipt does not reference the exact graph bytes')
        receipt, = (s for s in design['screens'] if s['screen_id'] == screen['id'])
        rows = [n for n in record['nodes'] if n['screenKey'] == graph['id'] + '/' + screen['id']]
        return receipt, rows, (record['fileKey'], record['pageId'], receipt['frame_id'])

    def one(rows, node_type, element_id):
        row, = (n for n in rows if n['type'] == node_type and n['elementId'] == element_id)
        return row

    def matches(row, value):
        obs = row.get('letterSpacing') or {}
        return (obs.get('unit') == 'PIXELS' and type(obs.get('value')) in (float, int)
                and math.isclose(obs['value'], value, rel_tol=0, abs_tol=0.01))

    receipt, rows, identity = read(receipt_path)
    if receipt.get('status', 'current') != 'current':
        raise ValueError('Positive receipt must describe a current frame')
    links = {(r['instance_id'], r['main_id']) for r in receipt['component_mains']}
    main_values, main_ids = set(), set()
    for main_key, instance_key in pairs:
        main, instance = one(rows, 'COMPONENT', main_key), one(rows, 'INSTANCE', instance_key)
        if (instance['id'], main['id']) not in links or expected[main_key] != expected[instance_key]:
            raise ValueError(f'{instance_key} did not reuse its expected tracking family')
        for key, owner in [(main_key, main), (instance_key, instance)]:
            label = one(rows, 'TEXT', key)
            if label['parentId'] != owner['id'] or not matches(label, expected[key]):
                raise ValueError(f'{key} label parent or native PIXELS value differs')
        main_ids.add(main['id'])
        main_values.add(expected[main_key])
    if len(main_ids) != len(pairs) or len(main_values) < 2:
        raise ValueError('No independent native mains for the distinct tracking values')
    if (drift_path is None) != (drift_element is None):
        raise ValueError('Provide both drift readback and affected element')
    if drift_path:
        after, after_rows, after_id = read(drift_path)
        before_label = one(rows, 'TEXT', drift_element)
        after_label = one(after_rows, 'TEXT', drift_element)
        if (after_id != identity or after.get('status') != 'changed' or before_label['id'] != after_label['id']
                or matches(after_label, expected[drift_element])):
            raise ValueError('Expected the same edited native label and a changed screen')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--pair', nargs=2, action='append', required=True, metavar=('MAIN', 'INSTANCE'))
    parser.add_argument('--drift-readback', type=Path)
    parser.add_argument('--drift-element')
    args = parser.parse_args()
    try:
        verify(args.graph, args.receipt, args.pair, args.drift_readback, args.drift_element)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(1, f'FAIL: {error}\n')
    print('PASS: pinned graph, native label tracking and main/instance links' +
          (', designer edit detected' if args.drift_readback else ''))
