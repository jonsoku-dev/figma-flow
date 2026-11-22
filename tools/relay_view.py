"""Bounded options for non-canvas Design viewer commands on a pinned discover task."""
import re

OPERATIONS = frozenset({'select-node', 'selection-info', 'viewer-history', 'viewer-language'})


def validate_options(operation, options):
    allowed = {'select-node': {'node_id'}, 'selection-info': {'include_text'},
               'viewer-language': {'language'}, 'viewer-history': set()}
    if operation not in allowed or not isinstance(options, dict):
        raise ValueError('Invalid viewer operation or options')
    if operation == 'selection-info' and not options:
        return {'include_text': False}
    if set(options) != allowed[operation]:
        raise ValueError('Viewer options differ from the operation')
    if operation == 'select-node':
        value = options['node_id']
        if not isinstance(value, str) or len(value) > 120 or not re.fullmatch(r'I?\d+:\d+(?:;\d+:\d+)*', value, re.ASCII):
            raise ValueError('Select an exact Design scene node ID')
    if operation == 'selection-info' and not isinstance(options['include_text'], bool):
        raise ValueError('Text excerpts require explicit opt-in')
    if operation == 'viewer-language':
        from plugin_panel import supported_locales
        if options['language'] not in (*supported_locales(), 'auto'):
            raise ValueError('Unsupported viewer language')
    return dict(options)
