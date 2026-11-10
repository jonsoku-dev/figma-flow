#!/usr/bin/env python3
"""Add exact local design dependencies to a product graph without changing inputs."""
import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts'))
import graph
from design_system import compile_design


def stable_id(kind, *parts):
    # A tuple encoding preserves boundaries that punctuation-based slugs lose.
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()
    return f'DESIGN-{kind}-{digest}'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def pointer(*parts):
    return '#/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts)


def state_destination_matches(product, by_id, shown, action, target):
    state_ids = {key for key in action.get('target_ids', []) if by_id[key]['type'] == 'state'}
    if not state_ids or any((action['id'], key) not in shown for key in state_ids):
        return False
    states = product.get('draft_prototype', {}).get('states', [])
    for key in state_ids:
        screens = [row.get('screen') for row in states if isinstance(row, dict) and row.get('id') == key]
        if screens != [target]:
            return False
    return by_id.get(target, {}).get('type') == 'screen'


def augment(product, design_data, graph_path, design_path, output_path):
    graph_path, design_path, output_path = map(lambda p: Path(os.path.abspath(p)), (graph_path, design_path, output_path))
    if output_path.resolve() in {graph_path.resolve(), design_path.resolve()}:
        raise ValueError('output must not overwrite an input')
    if json.loads(graph_path.read_text(encoding='utf-8')) != product or json.loads(design_path.read_text(encoding='utf-8')) != design_data:
        raise ValueError('source inputs changed before pinning')
    if 'design_system' in product:
        raise ValueError('use the unaugmented source graph when regenerating design dependencies')
    return _build(product, design_data, graph_path, design_path, output_path,
                  hashlib.sha256(graph_path.read_bytes()).hexdigest(),
                  hashlib.sha256(design_path.read_bytes()).hexdigest())


def _build(product, design_data, graph_path, design_path, output_path, graph_sha, design_sha):
    errors, _ = graph.validate_graph(product)
    if errors:
        raise ValueError('invalid product graph: ' + '; '.join(errors))
    design = compile_design(design_data)
    by_id = {node['id']: node for node in product['nodes']}
    edges = {(edge['from'], edge['to']) for edge in product['edges']}
    shown = {(edge['from'], edge['to']) for edge in product['edges'] if edge['type'] == 'shows'}
    coverage = []
    used_variants, used_tokens = set(), set()
    for screen in design['screens']:
        screen_id = screen['id']
        if by_id.get(screen_id, {}).get('type') != 'screen':
            raise ValueError(f'design screen is not a product screen: {screen_id}')
        for trace_id in screen['trace']:
            kind = by_id.get(trace_id, {}).get('type')
            connected = ((trace_id, screen_id) in edges or (screen_id, trace_id) in edges)
            if kind == 'acceptance':
                connected = any(node['type'] == 'requirement' and (node['id'], screen_id) in edges and
                                (node['id'], trace_id) in edges for node in product['nodes'])
            if kind not in {'requirement', 'acceptance', 'state', 'action'} or not connected:
                raise ValueError(f'trace does not belong to screen {screen_id}: {trace_id}')
        actions, variants = [], set()
        for element in screen['elements']:
            action_id = element.get('action_id')
            target = element.get('target_screen')
            if element.get('component') == 'button' and not action_id:
                raise ValueError(f'button requires an explicit action_id in {screen_id}')
            if target and not action_id:
                raise ValueError(f'target_screen requires an explicit action_id in {screen_id}')
            if action_id:
                action = by_id.get(action_id, {})
                if action.get('type') != 'action' or action.get('source_screen') != screen_id or (screen_id, action_id) not in edges:
                    raise ValueError(f'action does not belong to screen {screen_id}: {action_id}')
                screen_targets = {item for item in action.get('target_ids', []) if by_id[item]['type'] == 'screen'}
                direct_target = target in screen_targets and (action_id, target) in edges
                if target and not direct_target and not state_destination_matches(product, by_id, shown, action, target):
                    raise ValueError(f'action target mismatch: {action_id} -> {target}')
                if screen_targets and not target:
                    raise ValueError(f'action requires its target_screen: {action_id}')
                actions.append(action_id)
            if element['kind'] == 'component':
                variant = (element['component'], element['variant'])
                variants.add(variant)
                used_variants.add(variant)
        coverage.append({'screen_id': screen_id, 'trace_ids': screen['trace'],
                         'action_ids': sorted(set(actions)), 'screen_sha256': fingerprint(screen),
                         'component_ids': sorted(stable_id('COMPONENT', *variant) for variant in variants)})
    result = copy.deepcopy(product)
    for existing in result['nodes']:
        locator = existing.get('source')
        if locator and not urlsplit(locator).scheme:
            path, marker, fragment = locator.partition('#')
            prefix = os.path.relpath(graph_path.parent, output_path.parent)
            rebased = path if os.path.isabs(path) else (prefix + '/' + path if prefix != '.' else path)
            existing['source'] = rebased + (marker + fragment if marker else '')
    source = os.path.relpath(design_path, output_path.parent)
    source_sha = design_sha
    generated = set()

    def node(kind, identity, title, locator, value):
        node_id = stable_id(kind, *identity)
        if node_id in by_id or node_id in generated:
            raise ValueError(f'design node ID collision: {node_id}')
        generated.add(node_id)
        result['nodes'].append({'id': node_id, 'type': 'design-token' if kind == 'TOKEN' else 'component',
                                'title': title, 'status': 'observed', 'source': source + locator,
                                'design_sha256': fingerprint(value), 'design_value': value,
                                'detail': '로컬 디자인 선언. 실제 제품의 시각적 적용은 별도 검증이 필요합니다.'})
        return node_id

    def link(start, end):
        item = {'from': start, 'to': end, 'type': 'depends-on'}
        if item not in result['edges']:
            result['edges'].append(item)

    for path, token in design['tokens'].items():
        token_id = node('TOKEN', (path,), f'디자인 토큰 · {path}', pointer('tokens', *path.split('.')), token)
        if token['alias']:
            link(stable_id('TOKEN', token['alias']), token_id)
    for name, component in sorted(design['components'].items()):
        for variant, styles in sorted(component['variants'].items()):
            component_id = node('COMPONENT', (name, variant), f'컴포넌트 · {name} / {variant}',
                                pointer('components', name, 'variants', variant), styles)
            for token_path in sorted(set(styles.values())):
                link(stable_id('TOKEN', token_path), component_id)
                if (name, variant) in used_variants:
                    used_tokens.add(token_path)
    for screen in design['screens']:
        for element in screen['elements']:
            if element['kind'] == 'component':
                component_id = stable_id('COMPONENT', element['component'], element['variant'])
                link(component_id, screen['id'])
                if element.get('action_id'):
                    link(component_id, element['action_id'])
    pending = list(used_tokens)
    while pending:
        alias = design['tokens'][pending.pop()]['alias']
        if alias and alias not in used_tokens:
            used_tokens.add(alias)
            pending.append(alias)
    result['design_system'] = {
        'version': 1, 'dependency_direction': 'dependency-to-consumer',
        'generated_node_ids': sorted(generated),
        'source_hash_scope': 'whole-design-file; shared source evidence can stale all design nodes',
        'inputs': {'graph': {'path': os.path.relpath(graph_path, output_path.parent), 'sha256': graph_sha},
                   'design': {'path': source, 'sha256': source_sha}},
        'coverage': coverage,
        'uncovered_product_screen_ids': sorted(node['id'] for node in product['nodes'] if node['type'] == 'screen' and node['id'] not in {s['id'] for s in design['screens']}),
        'unused_token_paths': sorted(set(design['tokens']) - used_tokens),
        'unused_component_ids': sorted(stable_id('COMPONENT', name, variant) for name, item in design['components'].items() for variant in item['variants'] if (name, variant) not in used_variants)}
    errors, _ = graph.validate_graph(result)
    if errors:
        raise ValueError('invalid augmented graph: ' + '; '.join(errors))
    return result


def audit(product, design_data, graph_path, design_path):
    if not isinstance(product, dict) or not isinstance(product.get('design_system'), dict):
        raise ValueError('audit requires an augmented design graph')
    metadata = product['design_system']
    if not isinstance(product.get('nodes'), list) or not isinstance(product.get('edges'), list):
        raise ValueError('graph nodes and edges must be arrays')
    if any(not isinstance(n, dict) or not isinstance(n.get('id'), str) for n in product['nodes']):
        raise ValueError('graph nodes require string IDs')
    if len({n['id'] for n in product['nodes']}) != len(product['nodes']):
        raise ValueError('duplicate graph node IDs')
    if any(not isinstance(e, dict) or any(not isinstance(e.get(k), str) for k in ('from', 'to', 'type')) for e in product['edges']):
        raise ValueError('graph edges require string endpoints and types')
    design = compile_design(design_data)
    expected_ids = {stable_id('TOKEN', path) for path in design['tokens']}
    expected_ids.update(stable_id('COMPONENT', name, variant) for name, item in design['components'].items() for variant in item['variants'])
    clean = copy.deepcopy(product)
    clean.pop('design_system')
    clean['nodes'] = [n for n in clean['nodes'] if n['id'] not in expected_ids]
    clean['edges'] = [e for e in clean['edges'] if e['from'] not in expected_ids and e['to'] not in expected_ids]
    graph_path, design_path = Path(graph_path).absolute(), Path(design_path).absolute()
    design_sha = hashlib.sha256(design_path.read_bytes()).hexdigest()
    expected = _build(clean, design_data, graph_path, design_path, graph_path, '', design_sha)
    expected_nodes = {n['id']: n for n in expected['nodes'] if n['id'] in expected_ids}
    actual_nodes = {n['id']: n for n in product['nodes'] if n['id'] in expected_ids}
    node_fields = ('type', 'source', 'design_sha256', 'design_value')
    changed_nodes = [{'id': key, 'fields': [field for field in node_fields if actual_nodes[key].get(field) != expected_nodes[key].get(field)]}
                     for key in sorted(expected_ids & actual_nodes.keys())]
    changed_nodes = [item for item in changed_nodes if item['fields']]
    def relations(data):
        return [(e['from'], e['to'], e['type']) for e in data['edges'] if e['from'] in expected_ids or e['to'] in expected_ids]
    wanted, present = set(relations(expected)), set(relations(product))
    def edge_json(items):
        return [dict(zip(('from', 'to', 'type'), item)) for item in sorted(items)]
    drift = []
    for name in ('graph', 'design'):
        pin = metadata.get('inputs', {}).get(name)
        if not isinstance(pin, dict) or not isinstance(pin.get('path'), str) or not isinstance(pin.get('sha256'), str):
            raise ValueError(f'missing source pin: {name}')
        source = graph_path.parent / pin['path']
        try:
            current_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError:
            current_sha = None
        if current_sha != pin['sha256']:
            drift.append({'input': name, 'path': pin['path'], 'expected_sha256': pin['sha256'], 'actual_sha256': current_sha})
        if name == 'design' and (source.resolve() != design_path.resolve() or design_sha != pin['sha256']):
            if not any(item['input'] == 'design' for item in drift):
                drift.append({'input': 'design', 'path': str(design_path), 'expected_sha256': pin['sha256'], 'actual_sha256': design_sha})
    declared_ids = metadata.get('generated_node_ids', sorted(expected_ids))
    if not isinstance(declared_ids, list) or any(not isinstance(item, str) for item in declared_ids):
        raise ValueError('generated_node_ids must be a string array')
    result = {'version': 1, 'missing_node_ids': sorted(expected_ids - actual_nodes.keys()),
              'extra_node_ids': sorted(set(declared_ids) - expected_ids),
              'ownership_changed': sorted(declared_ids) != sorted(expected_ids),
              'changed_nodes': changed_nodes, 'missing_edges': edge_json(wanted - present),
              'extra_edges': edge_json(present - wanted),
              'duplicate_design_edges': edge_json({edge for edge in present if relations(product).count(edge) > 1}),
              'coverage_changed': metadata.get('coverage') != expected['design_system']['coverage'],
              'source_drift': drift,
              'scope': 'exact generated design declarations; unrelated product nodes preserved'}
    result['clear'] = not any(result[key] for key in ('missing_node_ids', 'extra_node_ids', 'ownership_changed', 'changed_nodes', 'missing_edges', 'extra_edges', 'duplicate_design_edges', 'coverage_changed', 'source_drift'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--design', required=True, type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--audit', action='store_true', help='read-only audit; exit 0 clear, 1 findings, 2 invalid input')
    args = parser.parse_args()
    if args.audit and args.out or not args.audit and not args.out:
        parser.error('creation requires --out; --audit does not accept --out')
    try:
        product = json.loads(args.graph.read_text(encoding='utf-8'))
        design = json.loads(args.design.read_text(encoding='utf-8'))
        if args.audit:
            report = audit(product, design, args.graph, args.design)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['clear'] else 1
        result = augment(product, design, args.graph, args.design, args.out)
        with args.out.open('x', encoding='utf-8') as target:
            json.dump(result, target, ensure_ascii=False, indent=2)
            target.write('\n')
        print(json.dumps({'graph': str(args.out), 'coverage': result['design_system']}, ensure_ascii=False))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if args.audit:
            print(json.dumps({'clear': False, 'invalid': str(exc)}, ensure_ascii=False))
            return 2
        parser.exit(1, f'design-graph: {exc}\n')


if __name__ == '__main__':
    sys.exit(main())
