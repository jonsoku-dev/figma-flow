"""Build an offline Figma panel with only its own messages and shared navigation."""
from html import escape
import json
import re
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / 'figma-bridge'
ROOT = BRIDGE.parent
VIEW_GRAPH = ROOT / 'library' / 'panel-design' / 'views.json'
_VIEW_SIGNAL = re.compile(r'data-flow-view=["\']([a-z][a-z0-9-]*)["\']|render_app\(["\']([a-z][a-z0-9-]*)["\']')


def load_view_registry(*, root=ROOT, graph_path=None):
    """Load and validate the route-to-React-source graph used by the panel."""
    root = Path(root).resolve()
    graph_path = Path(graph_path) if graph_path is not None else root / 'library/panel-design/views.json'
    graph_path = graph_path.resolve()
    try:
        graph = json.loads(graph_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f'Panel view graph unavailable: {error}') from error
    if not isinstance(graph, dict) or graph.get('schema') != 'figma-flow-panel-view-graph-v1' or graph.get('version') != 1:
        raise ValueError('Unsupported panel view graph')
    nodes = graph.get('nodes')
    edges = graph.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('Panel view graph requires nodes and edges arrays')
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('id'), str) or not node['id'] or node['id'] in by_id:
            raise ValueError('Panel view graph contains an invalid or duplicate node ID')
        by_id[node['id']] = node
    routes = {}
    for view in (node for node in nodes if node.get('type') == 'screen'):
        view_id = view['id']
        roles = {'registered-home': 'active', 'task': 'active', 'standalone': 'legacy'}
        if (not re.fullmatch(r'[a-z][a-z0-9-]*', view_id) or view.get('role') not in roles or
                view.get('lifecycle') != roles[view.get('role')]):
            raise ValueError(f'Invalid panel view ID or role: {view_id}')
        locale = view.get('locale')
        if not isinstance(locale, str) or not locale:
            raise ValueError(f'Panel view locale required: {view_id}')
        implementations = [edge for edge in edges if isinstance(edge, dict) and
                            edge.get('from') == view_id and edge.get('type') == 'implemented by']
        if len(implementations) != 1:
            raise ValueError(f'Panel view requires exactly one React implementation edge: {view_id}')
        implementation = by_id.get(implementations[0].get('to'))
        if not implementation or implementation.get('type') != 'code' or not isinstance(implementation.get('source'), str):
            raise ValueError(f'Panel view React implementation is missing: {view_id}')
        source = (graph_path.parent / implementation['source']).resolve()
        try:
            source.relative_to(root / 'panel-ui/src')
        except ValueError as error:
            raise ValueError(f'Panel view source must stay under panel-ui/src: {view_id}') from error
        if source.suffix != '.jsx' or not source.is_file():
            raise ValueError(f'Panel view React source is missing: {implementation["source"]}')
        routes[view_id] = {'role': view['role'], 'locale': locale, 'source': source}
    if not routes:
        raise ValueError('Panel view graph has no screen routes')
    homes = [view_id for view_id, route in routes.items() if route['role'] == 'registered-home']
    if len(homes) != 1:
        raise ValueError('Panel view graph must define exactly one registered-home route')

    signals = {}
    for source_path in [*sorted((root / 'figma-bridge').glob('*.html')),
                        *sorted((root / 'tools').glob('*.py'))]:
        try:
            source = source_path.read_text(encoding='utf-8')
        except OSError:
            continue
        for match in _VIEW_SIGNAL.finditer(source):
            view_id = match.group(1) or match.group(2)
            signals.setdefault(view_id, source_path.relative_to(root).as_posix())
    missing = sorted(set(signals) - set(routes))
    if missing:
        raise ValueError(f'Panel entrypoint references unregistered view {missing[0]} in {signals[missing[0]]}')
    return routes


VIEW_REGISTRY = load_view_registry()
VIEWS = frozenset(VIEW_REGISTRY)


def registered_home_view(view_registry=None):
    """Return the single route designated as the registered plugin home."""
    registry = VIEW_REGISTRY if view_registry is None else view_registry
    homes = [view_id for view_id, route in registry.items() if route['role'] == 'registered-home']
    if len(homes) != 1:
        raise ValueError('Panel view graph must define exactly one registered-home route')
    return homes[0]


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


def render_app(view, model=None, *, chat_context=False, shared=False, view_registry=None):
    """Render the interactive workspace with a locally bundled React application."""
    registry = VIEW_REGISTRY if view_registry is None else view_registry
    if view not in registry or (chat_context and view != 'chat'):
        raise ValueError('Unknown Figma app view')
    def inline_data(value):
        return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).replace('<', r'\u003c')
    messages = panel_messages(registry[view]['locale'])
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
