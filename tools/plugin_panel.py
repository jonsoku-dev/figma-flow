"""Build an offline Figma panel with only its own messages and shared navigation."""
from html import escape
import json
import re
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / 'figma-bridge'
VIEWS = {'workspace', 'import', 'review', 'graph', 'chat'}


def supported_locales():
    """Locale codes declared by the message catalogues, in the first entry's order."""
    files = sorted((BRIDGE / 'locales').glob('*.json'))
    if not files:
        raise ValueError('Locale catalogues required')
    found = None
    for source in files:
        catalog = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(catalog, dict) or not catalog:
            raise ValueError(f'Empty locale catalogue: {source.name}')
        for key, values in catalog.items():
            if (not isinstance(values, dict) or not values or len(values) != len(set(values))
                    or any(not isinstance(code, str) or not code.strip() or not isinstance(text, str) or not text.strip()
                           for code, text in values.items())):
                raise ValueError(f'Incomplete panel translation: {key}')
            codes = tuple(values)
            if found is None:
                found = codes
            elif set(codes) != set(found):
                raise ValueError(f'Locale catalogues disagree: {key}')
    return found


def panel_messages(view):
    messages = {}
    required = set(supported_locales())
    for group in dict.fromkeys(('common', 'workspace', view)):
        source = BRIDGE / 'locales' / (group + '.json')
        catalog = json.loads(source.read_text(encoding='utf-8'))
        for key, values in catalog.items():
            if group == 'workspace' and group != view and not (key.startswith('workspace.nav.') or key == 'workspace.language'):
                continue
            if set(values) != required or not all(isinstance(v, str) and v.strip() for v in values.values()):
                raise ValueError(f'Incomplete panel translation: {key}')
            params = [sorted(set(re.findall(r'\{(\w+)\}', v))) for v in values.values()]
            if any(p != params[0] for p in params):
                raise ValueError(f'Inconsistent translation parameters: {key}')
            messages[key] = values
    return messages


def display_name():
    """Codex interface name. plugin.json is the manifest the runtime already reads for version."""
    manifest = json.loads((BRIDGE.parent / 'plugin.json').read_text(encoding='utf-8'))
    name = manifest['extensions']['com.openai']['interface']['displayName']
    if not isinstance(name, str) or not name.strip():
        raise ValueError('plugin.json interface.displayName required')
    return name


def render_panel(html):
    marker = '/* FIGMA_FLOW_PANEL_CSS */'
    if html.count(marker) != 1:
        raise ValueError('Figma panel requires exactly one shared stylesheet marker')
    html = html.replace(marker, (BRIDGE / 'panel.css').read_text(encoding='utf-8'))
    view = re.search(r'<html\b[^>]*\bdata-flow-view=["\']([^"\']+)["\']', html, re.I)
    if not view:
        return html
    if view[1] not in VIEWS:
        raise ValueError('Unknown Figma panel view')
    from panel_components import render_components
    html = render_components(html, view[1])
    messages = json.dumps(panel_messages(view[1]), ensure_ascii=True, separators=(',', ':')).replace('<', r'\u003c')
    runtime = (BRIDGE / 'panel_i18n.js').read_text(encoding='utf-8').replace('__FLOW_MESSAGES__', messages)
    runtime += '\n' + (BRIDGE / 'panel_components.js').read_text(encoding='utf-8')
    if '<script>' not in html:
        raise ValueError('Figma panel has no script entry')
    return html.replace('<script>', '<script>\n' + runtime + '\n', 1)


def render_app(view, model=None, *, chat_context=False, shared=False):
    """Render the interactive workspace with a locally bundled React application."""
    if view not in VIEWS or (chat_context and view != 'chat'):
        raise ValueError('Unknown Figma app view')
    def inline_data(value):
        return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).replace('<', r'\u003c')
    messages = panel_messages(view)
    runtime = (BRIDGE / 'panel_i18n.js').read_text(encoding='utf-8').replace('__FLOW_MESSAGES__', inline_data(messages))
    script = (BRIDGE / 'assets/panels.js').read_text(encoding='utf-8')
    script = re.sub(r'</script', lambda _match: r'<\/script', script, flags=re.I)
    css = (BRIDGE / 'assets/panels.css').read_text(encoding='utf-8')
    if shared:
        script = '/* FLOW_SHARED_REACT_APPLICATION */'
        css = '/* FLOW_SHARED_PANEL_STYLES */'
    data = '/* WORKSPACE_CHAT_CONTEXT */' if chat_context else inline_data(model or {})
    return (f'<!doctype html><html lang="ko" data-flow-view="{view}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(display_name()) + '</title>'
            + f'<style>{css}</style></head><body class="panel react-panel"><div id="flow-root"></div>'
            + f'<script type="application/json" id="flow-model">{data}</script><script>{runtime}\n{script}</script></body></html>')
