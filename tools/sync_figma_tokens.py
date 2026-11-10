#!/usr/bin/env python3
"""Plan offline Figma scalar-token edits from two pinned readback exports.

Only existing direct scalar tokens can be written. Alias topology, names, types,
native IDs, collection ownership and the single mode must stay fixed. Dimensions
retain their px/rem unit (the bridge uses 16px/rem); colors must round-trip through
8-bit sRGB hex. Structured source values are preserved but cannot be edited here.
Exports are supplied evidence, not authenticated proof of a live Figma session.
For consecutive edits on the same native import, --prior-sync pins the preceding
plan and export. --resolved always names the original reviewed import payload;
--design names the preceding plan's design.json (equivalent JSON is accepted).
"""
import argparse
import copy
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import struct

import design_graph
from design_system import compile_design, components_css, render
from figma_bridge import MAX_BYTES, variable_value, validate


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('inputs must be regular JSON files of at most 2 MB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    raw = path.read_bytes()
    data = json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON number')))
    return data, hashlib.sha256(raw).hexdigest()


def metadata(item, key):
    declared = item.get('declared_metadata', {})
    if not isinstance(declared, dict):
        raise ValueError('declared_metadata must be an object')
    if key in item and key in declared and item[key] != declared[key]:
        raise ValueError(f'conflicting metadata: {key}')
    return item.get(key, declared.get(key))


def indexed(items, label):
    if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] for item in items):
        raise ValueError(f'{label} require native IDs')
    result = {item['id']: item for item in items}
    if len(result) != len(items):
        raise ValueError(f'duplicate {label} native IDs')
    return result


def selected(export, page_id, digest, expected):
    if not isinstance(export, dict) or export.get('format') != 'figma-flow-readback-v1':
        raise ValueError('expected figma-flow-readback-v1 export')
    pages = indexed(export.get('pages'), 'pages')
    variables = indexed(export.get('variables'), 'variables')
    collections = indexed(export.get('collections'), 'collections')
    page = pages.get(page_id)
    if not page or metadata(page, 'source_sha256') != digest:
        raise ValueError('selected page is missing or has a stale/wrong source SHA256')
    collection_id = metadata(page, 'collection_id')
    collection = collections.get(collection_id)
    if not collection:
        raise ValueError('selected page collection is missing')
    if any(other['id'] != page_id and metadata(other, 'collection_id') == collection_id for other in pages.values()):
        raise ValueError('selected page collection is shared with another import page')
    mode = collection.get('defaultModeId')
    modes = collection.get('modes')
    if not isinstance(mode, str) or not isinstance(modes, list) or len(modes) != 1 or not isinstance(modes[0], dict) or modes[0].get('modeId') != mode:
        raise ValueError('only a single default collection mode is supported')
    owned = {key: value for key, value in variables.items() if value.get('variableCollectionId') == collection_id}
    semantic = {}
    for variable in owned.values():
        identity = metadata(variable, 'semantic_id')
        if not isinstance(identity, str) or identity not in expected:
            raise ValueError('unknown/orphan variable in selected collection')
        if identity in semantic:
            raise ValueError(f'ambiguous semantic token: {identity}')
        if variable.get('name') != identity.replace('.', '/') or variable.get('resolvedType') != variable_value(expected[identity])[0]:
            raise ValueError(f'token name/type drift: {identity}')
        values = variable.get('valuesByMode')
        if not isinstance(values, dict) or set(values) != {mode}:
            raise ValueError(f'unsupported/missing mode values: {identity}')
        semantic[identity] = variable
    if set(semantic) != set(expected):
        raise ValueError('selected collection has missing semantic tokens')
    for identity, variable in semantic.items():
        value = variable['valuesByMode'][mode]
        alias = expected[identity].get('alias')
        if alias:
            if value != {'type': 'VARIABLE_ALIAS', 'id': semantic[alias]['id']}:
                raise ValueError(f'alias topology changed: {identity}')
        elif isinstance(value, dict) and value.get('type') == 'VARIABLE_ALIAS':
            raise ValueError(f'alias topology changed: {identity}')
        else:
            native_value(expected[identity]['type'], value)
    return page, collection, semantic, mode


def native_value(kind, value):
    if kind == 'color':
        if not isinstance(value, dict) or set(value) - {'r', 'g', 'b', 'a'} or not {'r', 'g', 'b'} <= set(value):
            raise ValueError('color must be an sRGB native color')
        channels = [value.get(key, 1) for key in ('r', 'g', 'b', 'a')]
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in channels):
            raise ValueError('color channels must be finite numbers in 0..1')
        return dict(zip(('r', 'g', 'b', 'a'), channels))
    if kind in {'number', 'dimension'}:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (kind == 'dimension' and value < 0):
            raise ValueError('numeric token must be finite (dimensions nonnegative)')
    elif kind == 'fontFamily':
        if not isinstance(value, str):
            raise ValueError('fontFamily must be a string')
    else:
        raise ValueError(f'unsupported token type: {kind}')
    return value


def same(kind, left, right):
    left, right = native_value(kind, left), native_value(kind, right)
    if kind == 'color':
        return color_bytes(left) == color_bytes(right)
    return left == right


def color_bytes(channels):
    encoded = []
    for key in ('r', 'g', 'b', 'a'):
        channel = channels[key]
        byte = int((Decimal(str(channel)) * 255).quantize(Decimal('1')))
        exact = byte / 255
        # Figma exports its float32 storage; accept that exact encoding, not a
        # tolerance that could silently import an arbitrary non-byte color.
        native = struct.unpack('f', struct.pack('f', exact))[0]
        if channel not in (exact, native):
            raise ValueError('color cannot round-trip through 8-bit sRGB (double or Figma float32 storage)')
        encoded.append(byte)
    return encoded


def scalar_edit(original, kind, observed):
    if isinstance(original, (dict, list)):
        raise ValueError('editing structured source token values is unsupported')
    if kind == 'color':
        channels = native_value(kind, observed)
        encoded = color_bytes(channels)
        value = '#' + ''.join(f'{x:02x}' for x in (encoded[:3] if encoded[3] == 255 else encoded))
    elif kind == 'dimension':
        unit = 'rem' if original.endswith('rem') else 'px'
        amount = Decimal(str(observed)) / (16 if unit == 'rem' else 1)
        value = format(amount, 'f') + unit
    else:
        value = observed
    _, encoded = variable_value({'type': kind, 'value': value})
    if not same(kind, encoded, observed):
        raise ValueError('changed value cannot round-trip through the supported source representation')
    return value


def difference_paths(before, after, path='#'):
    if type(before) is type(after) and isinstance(before, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            child = path + '/' + str(key).replace('~', '~0').replace('/', '~1')
            result.extend(difference_paths(before[key], after[key], child) if key in before and key in after else [child])
        return result
    if type(before) is type(after) and isinstance(before, list) and len(before) == len(after):
        return [item for index, (a, b) in enumerate(zip(before, after)) for item in difference_paths(a, b, path + '/' + str(index))]
    return [] if before == after else [path]


def impact_report(product, design, design_path, graph_path, out, roots):
    augmented = design_graph.augment(product, design, graph_path, design_path, out / 'dependencies.json')
    compiled = compile_design(design)
    affected = set(roots)
    while True:
        inherited = {path for path, token in compiled['tokens'].items() if token['alias'] in affected}
        if inherited <= affected:
            break
        affected.update(inherited)
    by_id = {node['id']: node for node in augmented['nodes']}
    relations = {(edge['from'], edge['to']) for edge in augmented['edges'] if edge['type'] == 'depends-on'}
    variants, screens = [], {}
    for name, component in sorted(compiled['components'].items()):
        for variant, styles in sorted(component['variants'].items()):
            properties = [{'property': prop, 'token': token} for prop, token in sorted(styles.items()) if token in affected]
            if not properties:
                continue
            node_id = design_graph.stable_id('COMPONENT', name, variant)
            consumers = sorted(screen['id'] for screen in compiled['screens'] if (node_id, screen['id']) in relations)
            variants.append({'component': name, 'variant': variant, 'node_id': node_id, 'properties': properties, 'declared_screen_ids': consumers})
            for screen_id in consumers:
                screen = screens.setdefault(screen_id, {'screen_id': screen_id, 'node_id': screen_id,
                                                         'source': by_id[screen_id].get('source'), 'paths': []})
                for token in sorted({item['token'] for item in properties}):
                    chain = [token]
                    while chain[-1] not in roots:
                        chain.append(compiled['tokens'][chain[-1]]['alias'])
                    ids = [design_graph.stable_id('TOKEN', path) for path in reversed(chain)] + [node_id, screen_id]
                    if any((a, b) not in relations for a, b in zip(ids, ids[1:])):
                        raise ValueError('missing generated impact dependency')
                    screen['paths'].append({'root': chain[-1], 'token': token, 'component': name, 'variant': variant, 'node_ids': ids})
    return ({'changed_roots': sorted(roots), 'inherited_aliases': sorted(affected - set(roots)),
             'affected_tokens': sorted(affected), 'variants': variants, 'screens': [screens[key] for key in sorted(screens)]}, augmented)


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def check_prior(prior_dir, sources, current, page_id):
    prior_dir = Path(prior_dir)
    if prior_dir.is_symlink() or not prior_dir.is_dir() or (prior_dir / 'assets').is_symlink():
        raise ValueError('prior-sync must be an unmodified plan directory')
    prior, prior_sha = read_json(prior_dir / 'impact.json')
    if not isinstance(prior, dict) or not isinstance(prior.get('receipt'), dict):
        raise ValueError('prior-sync receipt is missing or invalid')
    receipt = prior.get('receipt', {})
    expected_artifacts = {'design.json', 'resolved.json', 'dependencies.json', 'assets/tokens.css', 'assets/components.css', 'report.md'}
    artifacts = receipt.get('artifacts', {})
    if prior.get('version') != 1 or not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        raise ValueError('prior-sync receipt/artifact pins are missing or invalid')
    pins = prior.get('pins')
    if not isinstance(pins, dict) or any(not isinstance(pins.get(key), dict) for key in ('graph', 'resolved', 'after')):
        raise ValueError('prior-sync input pins are missing or invalid')
    for name in sorted(expected_artifacts):
        path = prior_dir / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES or hashlib.sha256(path.read_bytes()).hexdigest() != artifacts[name]:
            raise ValueError(f'corrupt prior-sync artifact: {name}')
    prior_design, _ = read_json(prior_dir / 'design.json')
    prior_resolved, _ = read_json(prior_dir / 'resolved.json')
    if design_graph.fingerprint(prior_design) != receipt.get('design_canonical_sha256') or prior_design != sources['design'][0]:
        raise ValueError('current design does not match prior-sync output design')
    if compile_design(prior_design) != prior_resolved or current != prior_resolved:
        raise ValueError('prior-sync compiled design/resolved artifact mismatch')
    origin = receipt.get('origin', {})
    if not isinstance(origin, dict) or origin.get('resolved_sha256') != sources['resolved'][1] or origin.get('page_id') != page_id or prior.get('page_id') != page_id or prior.get('collection_id') != origin.get('collection_id'):
        raise ValueError('prior-sync origin, source, page or collection mismatch')
    if origin.get('graph_sha256') != sources['graph'][1] or pins['graph'].get('sha256') != sources['graph'][1]:
        raise ValueError('prior-sync source product graph mismatch')
    if pins['resolved'].get('sha256') != sources['resolved'][1]:
        raise ValueError('prior-sync baseline resolved pin mismatch')
    if pins['after'].get('sha256') != sources['before'][1]:
        raise ValueError('new before export does not match exact prior after export SHA256')
    original = sources['resolved'][0]
    def topology(resolved):
        return dict(resolved, tokens={path: {key: value for key, value in token.items() if key != 'value'} for path, token in resolved['tokens'].items()})
    if topology(current) != topology(original):
        raise ValueError('prior-sync token/component/screen topology differs from original import')
    return origin, {'path': str((prior_dir / 'impact.json').resolve()), 'sha256': prior_sha}


def sync_tokens(design_path, resolved_path, before_path, after_path, page_id, graph_path, out, prior_sync=None):
    out = Path(out)
    if out.exists() or out.is_symlink():
        raise ValueError('output must be a fresh directory')
    sources = {key: read_json(path) for key, path in [('design', design_path), ('resolved', resolved_path),
               ('before', before_path), ('after', after_path), ('graph', graph_path)]}
    design, resolved = sources['design'][0], sources['resolved'][0]
    current = compile_design(design)
    validate(resolved)
    origin, prior_pin = None, None
    if prior_sync is not None:
        origin, prior_pin = check_prior(prior_sync, sources, current, page_id)
    elif current != resolved:
        raise ValueError('stale resolved source: design does not compile exactly to pinned resolved.json')
    before, after = sources['before'][0], sources['after'][0]
    a_page, a_collection, a_tokens, a_mode = selected(before, page_id, sources['resolved'][1], current['tokens'])
    b_page, b_collection, b_tokens, b_mode = selected(after, page_id, sources['resolved'][1], current['tokens'])
    if a_collection != b_collection or a_mode != b_mode:
        raise ValueError('collection identity/mode metadata changed')
    if origin is not None and a_collection['id'] != origin['collection_id']:
        raise ValueError('prior-sync native collection mismatch')
    if origin is None:
        origin = {'resolved_sha256': sources['resolved'][1], 'design_sha256': sources['design'][1],
                  'graph_sha256': sources['graph'][1], 'page_id': page_id, 'collection_id': a_collection['id']}
    revised, changes = copy.deepcopy(design), []
    for path, token in current['tokens'].items():
        a, b = a_tokens[path], b_tokens[path]
        if a['id'] != b['id']:
            raise ValueError(f'native token identity changed: {path}')
        if token['alias']:
            continue
        old, new = a['valuesByMode'][a_mode], b['valuesByMode'][b_mode]
        if not same(token['type'], variable_value(token)[1], old):
            raise ValueError(f'stale baseline token value: {path}')
        if same(token['type'], old, new):
            continue
        target = revised['tokens']
        for part in path.split('.'):
            target = target[part]
        value = scalar_edit(target['$value'], token['type'], new)
        changes.append({'token': path, 'before': target['$value'], 'after': value, 'figma_variable_id': a['id']})
        target['$value'] = value
    result = compile_design(revised)
    report, dependencies = impact_report(sources['graph'][0], design, design_path, graph_path, out, {change['token'] for change in changes})
    dependency_json = json_text(dependencies)
    selected_ids = {variable['id'] for variable in a_tokens.values()}
    unrelated = lambda export: {key: [item for item in export[key] if item['id'] not in ({page_id} if key == 'pages' else selected_ids if key == 'variables' else {a_collection['id']})] for key in ('pages', 'variables', 'collections')}
    ignored = {'selected_page_paths': difference_paths(a_page, b_page),
               'outside_selected_collection_paths': difference_paths(unrelated(before), unrelated(after))}
    report.update(version=1, page_id=page_id, collection_id=a_collection['id'], changes=changes,
                  pins={key: {'path': str(Path(path).resolve()), 'sha256': sources[key][1]} for key, path in [('design', design_path), ('resolved', resolved_path), ('before', before_path), ('after', after_path), ('graph', graph_path)]},
                  ignored_changes=ignored,
                  dependency_graph={'path': 'dependencies.json', 'sha256': hashlib.sha256(dependency_json.encode('utf-8')).hexdigest(),
                                    'based_on': 'this run\'s pinned input design and source graph; scalar edits preserve dependency topology',
                                    'design_sha256': sources['design'][1], 'graph_sha256': sources['graph'][1]},
                  scope='Offline scalar token plan; graph paths describe declared dependencies, not runtime proof. Figma origin is not authenticated.',
                  limitations=['Single fixed mode and collection; no alias topology/name/type/native identity changes.', 'Only direct scalar edits; structured values are preserved unchanged.', 'sRGB hex colors must round-trip at 8-bit precision (exact double or Figma float32 encoding); dimensions preserve px/rem with 16px/rem.', 'Screen/layout/text/binding edits are reported and never imported; raw code mapping is a separate review.'])
    _, css = render(result, True)
    findings = ['# Figma token change plan', '', report['scope'], '', f"Changed roots: {len(changes)}; inherited aliases: {len(report['inherited_aliases'])}; consuming variants: {len(report['variants'])}; declared screens: {len(report['screens'])}.", '']
    findings += [f"- `{change['token']}`: `{change['before']}` → `{change['after']}`" for change in changes] or ['No supported token value changes.']
    findings += ['', 'Inherited aliases: ' + (', '.join(f'`{path}`' for path in report['inherited_aliases']) or 'none') + '.', '', '## Declared consumers', '']
    findings += [f"- `{item['component']}/{item['variant']}`: " + (', '.join(f'`{screen}`' for screen in item['declared_screen_ids']) or 'no declared screen uses this variant') for item in report['variants']] or ['No declared variant consumers.']
    findings += ['', 'Dependency paths are recorded in `impact.json` and backed by `dependencies.json`, generated from this run\'s pinned input design and product graph. Scalar edits preserve that topology.', '',
                 f"Ignored selected-page edit paths: {len(ignored['selected_page_paths'])}; outside scope edit paths: {len(ignored['outside_selected_collection_paths'])}. Exact paths are listed in `impact.json`.", '', '## Limits', ''] + ['- ' + text for text in report['limitations']]
    findings += ['', 'For another edit on this native import, pass `--prior-sync` with this output directory, this output `design.json`, the exact previous after export as the next before export, and the original reviewed `--resolved` payload. The receipt checks all emitted artifacts and pins the prior report SHA256. Equivalent serialization of the current design is accepted by canonical JSON comparison.']
    files = {'design.json': json_text(revised), 'resolved.json': json_text(result), 'dependencies.json': dependency_json,
             'assets/tokens.css': css, 'assets/components.css': components_css(result), 'report.md': '\n'.join(findings) + '\n'}
    report['receipt'] = {'origin': origin, 'prior_report': prior_pin, 'design_canonical_sha256': design_graph.fingerprint(revised),
                         'artifacts': {name: hashlib.sha256(content.encode('utf-8')).hexdigest() for name, content in files.items()}}
    files['impact.json'] = json_text(report)
    # Complete validation before creating the fresh output ownership boundary.
    out.mkdir()
    (out / 'assets').mkdir()
    for name, content in files.items():
        (out / name).write_text(content, encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('design', 'resolved', 'before', 'after', 'graph', 'out'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--prior-sync', type=Path, help='preceding unmodified plan directory for another edit on the same native import')
    args = parser.parse_args()
    try:
        report = sync_tokens(args.design, args.resolved, args.before, args.after, args.page_id, args.graph, args.out, prior_sync=args.prior_sync)
        print(json.dumps({'output': str(args.out.resolve()), 'changed_roots': report['changed_roots'], 'declared_screen_ids': [item['screen_id'] for item in report['screens']]}, ensure_ascii=False))
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        parser.exit(1, f'sync-figma-tokens: {exc}\n')


if __name__ == '__main__':
    main()
