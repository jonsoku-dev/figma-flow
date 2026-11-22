"""Bounded options for non-canvas Design viewer commands on a pinned discover task."""
import json
from pathlib import Path
import re

from relay_limits import MAX_NODES

INSPECT_FIELDS = json.loads((Path(__file__).resolve().parents[1] / 'library/figma-profile/policy.json').read_bytes())['inspectFields']

OPERATIONS = frozenset({'select-node', 'selection-info', 'viewer-history', 'viewer-language'})


def validate_options(operation, options):
    allowed = {'select-node': {'node_id'}, 'selection-info': {'include_text', 'geometry_node_ids', 'inspect_node_ids', 'fields'},
               'viewer-language': {'language'}, 'viewer-history': set()}
    if operation not in allowed or not isinstance(options, dict):
        raise ValueError('Invalid viewer operation or options')
    if operation == 'selection-info' and not options:
        return {'include_text': False}
    if operation == 'selection-info':
        if set(options) - allowed[operation]:
            raise ValueError('Viewer options differ from the operation')
        result = {'include_text': options.get('include_text', False)}
        if not isinstance(result['include_text'], bool):
            raise ValueError('Text excerpts require explicit opt-in')
        inspecting = 'inspect_node_ids' in options
        if 'fields' in options and not inspecting:
            raise ValueError('Fields require explicit Design node IDs')
        if inspecting and 'geometry_node_ids' in options:
            raise ValueError('Choose a geometry or a property read')
        key = 'inspect_node_ids' if inspecting else 'geometry_node_ids'
        ids = options.get(key)
        if key in options:
            if not inspecting and result['include_text']:
                raise ValueError('Geometry-only selection-info cannot include text')
            if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_NODES or
                    any(not isinstance(value, str) or len(value) > 120 or
                        not re.fullmatch(r'I?\d+:\d+(?:;\d+:\d+)*', value, re.ASCII) for value in ids) or
                    len(set(ids)) != len(ids)):
                raise ValueError(f'Read 1 to {MAX_NODES} unique exact Design node IDs')
            result[key] = list(ids)
        if inspecting:
            fields = options.get('fields')
            if (not isinstance(fields, list) or not fields or len(fields) > len(INSPECT_FIELDS)
                    or any(not isinstance(f, str) or f not in INSPECT_FIELDS for f in fields)
                    or len(set(fields)) != len(fields) or ('characters' in fields) != result['include_text']):
                raise ValueError('Choose supported fields; characters require explicit text opt-in')
            result['fields'] = list(fields)
        return result
    if set(options) != allowed[operation]:
        raise ValueError('Viewer options differ from the operation')
    if operation == 'select-node':
        value = options['node_id']
        if not isinstance(value, str) or len(value) > 120 or not re.fullmatch(r'I?\d+:\d+(?:;\d+:\d+)*', value, re.ASCII):
            raise ValueError('Select an exact Design scene node ID')
    if operation == 'viewer-language':
        from plugin_panel import supported_locales
        if options['language'] not in (*supported_locales(), 'auto'):
            raise ValueError('Unsupported viewer language')
    return dict(options)
