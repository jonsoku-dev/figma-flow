"""Link measured viewport variants to their routes in a canonical web design graph."""
from urllib.parse import urlsplit

from web_design import validate_graph


def link_viewports(graph):
    """Read route identity from the capture evidence already bound to each screen."""
    screens = {s['id']: s for s in validate_graph(graph)}
    nodes = {n['id']: n for n in graph['nodes']}
    groups = {}
    for edge in graph['edges']:
        if edge['from'] not in screens or edge['type'] != 'sourced from':
            continue
        ref = nodes[edge['to']]
        if ref['type'] != 'reference' or 'capture_sha256' not in ref:
            continue
        origin = urlsplit(ref['origin'])
        route = ref['page_path']
        if (origin.scheme not in ('http', 'https') or not origin.netloc or not route.startswith('/')
                or origin.username or origin.password):
            raise ValueError('A measured route needs a web origin and browser pathname')
        viewport = ref['viewport']
        size = (viewport['width'], viewport['height'])
        if any(type(v) is not int or v < 1 for v in size):
            raise ValueError('Observed viewport dimensions must be positive integers')
        variants = groups.setdefault((ref['origin'], route), {})
        if size in variants:
            raise ValueError('Each route and viewport pair requires a unique observation')
        variants[size] = edge['from']
    for index, ((origin, route), variants) in enumerate(sorted(groups.items()), 1):
        key = f'ROUTE-{index}'
        if key in nodes:
            raise ValueError('Route identifier already present in the input graph')
        graph['nodes'].append({'id': key, 'type': 'state', 'status': 'observed', 'title': route,
                               'origin': origin, 'detail': 'Browser route with measured viewport variants.'})
        graph['edges'].extend({'from': key, 'to': screen, 'type': 'renders at viewport'}
                              for _, screen in sorted(variants.items()))
    validate_graph(graph)
    return graph
