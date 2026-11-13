#!/usr/bin/env python3
"""Search pinned official REST endpoints and print inert request templates."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'library' / 'figma-rest'
INDEX = LIBRARY / 'index.json'
METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
EVIDENCE = 'Pinned OpenAPI declaration only; no requests executed; account access and runtime behavior unverified.'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def verify_source():
    source = json.loads((LIBRARY / 'source.json').read_text())
    for name, expected in source['files'].items():
        if hashlib.sha256((LIBRARY / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Pinned source hash mismatch: {name}')
    raw = gzip.decompress((LIBRARY / 'openapi.yaml.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest() != source['source_sha256']:
        raise ValueError('Decompressed OpenAPI hash mismatch')
    return source, raw


def resolve(value, spec, trail=()):
    if isinstance(value, list):
        return [resolve(item, spec, trail) for item in value]
    if not isinstance(value, dict):
        return value
    ref = value.get('$ref')
    if ref and ref not in trail:
        if not ref.startswith('#/'):
            raise ValueError(f'Nonlocal schema reference: {ref}')
        target = spec
        for part in ref[2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        return resolve({**target, **{k: v for k, v in value.items() if k != '$ref'}}, spec, (*trail, ref))
    return {key: resolve(item, spec, trail) for key, item in value.items()}


def build():
    source, raw = verify_source()
    try:
        import yaml
    except ImportError as exc:
        raise ValueError('Regeneration requires library/figma-rest/requirements.txt; search and template need only Python.') from exc
    if yaml.__version__ != '6.0.2':
        raise ValueError('Regeneration requires pinned PyYAML 6.0.2')
    spec = yaml.safe_load(raw)
    docs = {tag['name']: tag.get('externalDocs', {}).get('url') for tag in spec.get('tags', [])}
    endpoints = []
    for path, item in sorted(spec['paths'].items()):
        for method, operation in sorted(item.items()):
            if method not in METHODS:
                continue
            parameters = {}
            for parameter in item.get('parameters', []) + operation.get('parameters', []):
                parameter = resolve(parameter, spec)
                parameters[(parameter['in'], parameter['name'])] = parameter
            security = operation.get('security', spec.get('security', []))
            description = operation.get('description', '')
            access = [paragraph.strip() for paragraph in description.split('\n\n')
                      if re.search(r'Enterprise|Professional|Organization plan|seat|available only|only available', paragraph, re.I)]
            endpoints.append({
                'operation_id': operation['operationId'], 'method': method.upper(), 'path': path,
                'summary': operation.get('summary', ''), 'description': description,
                'tags': operation.get('tags', []), 'deprecated': operation.get('deprecated', False),
                'parameters': list(parameters.values()),
                'request_body': resolve(operation.get('requestBody'), spec),
                'security': security,
                'scopes': sorted({scope for alternative in security for scopes in alternative.values() for scope in scopes}),
                'access_notes': access,
                'rate_limit_tier': operation.get('x-rate-limit-tier'),
                'docs_urls': sorted({docs[tag] for tag in operation.get('tags', []) if docs.get(tag)}),
                'source_url': f'{source["repository"]}/blob/{source["ref"]}/{source["source_path"]}',
            })
    return {'schema': 'figma-flow-rest-api-inventory-v1', 'source': source,
            'evidence': EVIDENCE, 'server': spec['servers'][0]['url'],
            'security_schemes': spec['components']['securitySchemes'], 'endpoints': endpoints}


def load():
    source, _ = verify_source()
    catalog = json.loads(INDEX.read_text())
    if catalog['source'] != source:
        raise ValueError('Index provenance does not match pinned source; regenerate')
    return catalog


def search(catalog, query='', method=None, limit=50):
    words = query.casefold().split()
    rows = [row for row in catalog['endpoints']
            if (not method or row['method'] == method.upper())
            and all(word in json.dumps(row, ensure_ascii=False).casefold() for word in words)]
    return {'evidence': EVIDENCE, 'source': catalog['source'], 'total': len(rows),
            'rows': rows[:limit] if limit else rows}


def example(schema, name='value'):
    if 'example' in schema:
        return schema['example']
    if 'const' in schema:
        return schema['const']
    if schema.get('enum'):
        return schema['enum'][0]
    for union in ('oneOf', 'anyOf'):
        if schema.get(union):
            return example(schema[union][0], name)
    if schema.get('allOf'):
        parts = [example(part, name) for part in schema['allOf']]
        if all(isinstance(part, dict) for part in parts):
            return {key: value for part in parts for key, value in part.items()}
        return parts[0]
    kind = schema.get('type')
    if kind == 'object' or 'properties' in schema:
        properties = schema.get('properties', {})
        names = schema.get('required') or list(properties)
        return {key: example(properties.get(key, {}), key) for key in names}
    if kind == 'array':
        return [example(schema.get('items', {}), name)]
    if kind in ('number', 'integer'):
        return schema.get('minimum', 1)
    if kind == 'boolean':
        return True
    return '<' + name + '>'


def template(catalog, operation_id):
    row = next((row for row in catalog['endpoints'] if row['operation_id'] == operation_id), None)
    if row is None:
        raise ValueError(f'Unknown operation: {operation_id}')
    query = []
    headers = {}
    required = []
    for parameter in row['parameters']:
        if not parameter.get('required'):
            continue
        required.append({'in': parameter['in'], 'name': parameter['name']})
        value = '<' + parameter['name'] + '>'
        if parameter['in'] == 'query':
            query.append(quote(parameter['name']) + '=' + value)
        elif parameter['in'] == 'header':
            headers[parameter['name']] = value
    path = re.sub(r'\{([^}]+)\}', r'<\1>', row['path'])
    result = {'operation_id': operation_id, 'method': row['method'],
              'url': catalog['server'] + path + ('?' + '&'.join(query) if query else ''),
              'headers': headers, 'required_parameters': required, 'security': row['security'],
              'warning': 'Inert draft. Replace placeholders, review parameter/body schemas and authorization before any request. Union bodies show the first alternative; values are illustrative.',
              'endpoint': row}
    body = row.get('request_body')
    if body:
        content = body['content']
        media = 'application/json' if 'application/json' in content else next(iter(content))
        headers['Content-Type'] = media
        result['body'] = example(content[media].get('schema', {}))
        result['body_required'] = body.get('required', False)
    return result


def request_export(catalog, operation_id, path_values=None, query_values=None, body_file=None, auth='token'):
    """Export a command for manual review; never read credentials or execute curl."""
    draft = template(catalog, operation_id)
    row = draft['endpoint']
    provided = {'path': path_values or {}, 'query': query_values or {}}
    url = row['path']
    for location, values in provided.items():
        declared = {p['name']: p for p in row['parameters'] if p['in'] == location}
        unknown = set(values) - set(declared)
        if unknown:
            raise ValueError(f'Undeclared {location} parameters: {", ".join(sorted(unknown))}')
        missing = [p['name'] for p in declared.values() if p.get('required') and not values.get(p['name'])]
        if missing:
            raise ValueError(f'Missing required {location} parameters: {", ".join(missing)}')
        if location == 'path':
            for name, value in values.items():
                if value in ('.', '..'):
                    raise ValueError(f'Invalid dot segment for path parameter: {name}')
                url = url.replace('{' + name + '}', quote(value, safe=''))
    if any(p.get('required') and p['in'] not in provided for p in row['parameters']):
        raise ValueError('Required header/cookie parameters need a reviewed custom request')
    url = catalog['server'] + url
    if provided['query']:
        url += '?' + urlencode(sorted(provided['query'].items()))
    body = row.get('request_body')
    if body and body.get('required') and not body_file:
        raise ValueError('Required request body: pass --body-file with a reviewed JSON file')
    if body_file and not body:
        raise ValueError('This operation does not declare a request body')
    schemes = catalog['security_schemes']
    supported = {name for alternative in row['security'] for name in alternative}
    if auth == 'token':
        if not any(schemes[name].get('type') == 'apiKey' for name in supported):
            raise ValueError('This operation requires OAuth; use --auth oauth')
        prefix = 'X-Figma-Token: '
    elif auth == 'oauth':
        if not any(schemes[name].get('type') == 'oauth2' for name in supported):
            raise ValueError('This operation does not declare OAuth authentication')
        prefix = 'Authorization: Bearer '
    else:
        raise ValueError('Unknown auth mode')
    argv = ['curl', '--disable', '--globoff', '--proto', '=https', '--max-redirs', '0',
            '--request', row['method'], '--url', url]
    if body_file:
        if 'application/json' not in body['content']:
            raise ValueError('Only JSON body export is supported')
        path = Path(body_file).resolve()
        json.loads(path.read_text())
        argv.extend(['--header', 'Content-Type: application/json', '--data-binary', '@' + str(path)])
    command = shlex.join(argv) + ' --header "' + prefix + '${FIGMA_TOKEN:?Set FIGMA_TOKEN}"'
    return {'operation_id': operation_id, 'method': row['method'], 'url': url,
            'shell_command': command, 'credential_env': 'FIGMA_TOKEN', 'auth': auth,
            'security': row['security'], 'scopes': row['scopes'], 'access_notes': row['access_notes'],
            'docs_urls': row['docs_urls'], 'source_url': row['source_url'],
            'execution': 'not-executed',
            'warning': 'Review this command and authorize its effects before running. Set FIGMA_TOKEN privately; never paste credentials into chat. Export does not establish account access.'}


def assignments(values):
    result = {}
    for value in values:
        name, separator, item = value.partition('=')
        if not separator or not name or name in result:
            raise ValueError('Parameters must be unique NAME=VALUE arguments')
        result[name] = item
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('generate')
    commands.add_parser('verify')
    command = commands.add_parser('search')
    command.add_argument('query', nargs='?', default='')
    command.add_argument('--method', choices=sorted(method.upper() for method in METHODS))
    command.add_argument('--limit', type=int, default=50, help='0 returns all matches')
    command = commands.add_parser('template')
    command.add_argument('operation_id')
    command = commands.add_parser('curl', help='Export a reviewed shell request; never executes it')
    command.add_argument('operation_id')
    command.add_argument('--path', action='append', default=[], metavar='NAME=VALUE')
    command.add_argument('--query', action='append', default=[], metavar='NAME=VALUE')
    command.add_argument('--body-file', help='Reviewed local JSON file; required for required request bodies')
    command.add_argument('--auth', choices=('token', 'oauth'), default='token')
    args = parser.parse_args(argv)
    try:
        if args.command in ('generate', 'verify'):
            catalog = build()
            content = canonical(catalog)
            if args.command == 'generate':
                INDEX.write_text(content)
            elif INDEX.read_text() != content:
                raise ValueError('REST index differs from deterministic regeneration')
            print(canonical({'status': 'ok', 'endpoints': len(catalog['endpoints']), 'ref': catalog['source']['ref']}), end='')
        elif args.command == 'search':
            if args.limit < 0:
                raise ValueError('--limit must be nonnegative')
            print(canonical(search(load(), args.query, args.method, args.limit)), end='')
        elif args.command == 'template':
            print(canonical(template(load(), args.operation_id)), end='')
        else:
            print(canonical(request_export(load(), args.operation_id, assignments(args.path),
                                           assignments(args.query), args.body_file, args.auth)), end='')
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
