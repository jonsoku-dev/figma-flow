#!/usr/bin/env python3
"""Compare local source imports and explicit code/test coverage to impact paths.

Source parsing is static evidence, not a runtime trace.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from bisect import bisect_left
from collections import defaultdict, deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

SOURCE = {'.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.html', '.htm', '.css'}
JS = SOURCE - {'.html', '.htm', '.css'}
def parse_js(files, root):
    if not files:
        return {}
    installed = [Path(path) for path in ('/opt/homebrew/bin/node', '/usr/local/bin/node', '/usr/bin/node')]
    installed.append(Path.home() / '.local/bin/node')
    on_path = shutil.which('node')
    if on_path:
        installed.append(Path(on_path))
    node = next((str(path.resolve()) for path in installed if path.is_file() and
                 os.access(path, os.X_OK) and not path.resolve().is_relative_to(root)), None)
    if not node:
        return {item['path']: {'refs': [], 'unknown': [{'line': 1, 'reason': 'Node runtime unavailable'}]} for item in files}
    helper = Path(__file__).resolve().with_name('audit_js.cjs')
    try:
        process = subprocess.run([node, '--no-addons', str(helper)], input=json.dumps(files), text=True,
                                 capture_output=True, timeout=30, env={'PATH': os.defpath, 'LANG': 'C.UTF-8', 'TZ': 'UTC'})
        if process.returncode:
            raise ValueError('parser process failed')
        return {item['path']: item for item in json.loads(process.stdout)}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {item['path']: {'refs': [], 'unknown': [{'line': 1, 'reason': 'JavaScript parser unavailable'}]} for item in files}


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.unknown = []
        self.inline_script = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        ref = attrs.get('src') if tag == 'script' else None
        if tag == 'link' and any(x in (attrs.get('rel') or '').lower().split() for x in ('stylesheet', 'modulepreload')):
            ref = attrs.get('href')
        if ref:
            self.refs.append((ref, self.getpos()[0], tag))
        if tag == 'script' and not ref:
            self.inline_script = True

    def handle_data(self, data):
        if self.inline_script and data.strip():
            self.unknown.append((self.getpos()[0], 'inline script not inspected'))

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inline_script = False


CSS_TOKEN = re.compile(r"/\*[\s\S]*?\*/|\"(?:\\[\s\S]|[^\"\\])*\"|'(?:\\[\s\S]|[^'\\])*'|@[a-zA-Z_-][\w-]*|[^\s]", re.ASCII)
CSS_IMPORT = re.compile(r"^(?:\"([^\"]*)\"|'([^']*)'|url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'()]+))\s*\))\s*(.*)$", re.IGNORECASE | re.DOTALL)


def parse_css(text):
    # Tokenize strings and comments first so their contents cannot become imports.
    tokens = list(CSS_TOKEN.finditer(text))
    newlines = [i for i, char in enumerate(text) if char == "\n"]
    for token in tokens:
        if token.group() in ('\"', "'") or text.startswith('/*', token.start()) and not token.group().endswith('*/'):
            return [], [(bisect_left(newlines, token.start()) + 1, 'malformed CSS string or comment')]
    refs, unknown = [], []
    depth, start, i, allowed = 0, True, 0, True
    while i < len(tokens):
        token = tokens[i].group()
        line = bisect_left(newlines, tokens[i].start()) + 1
        if token.startswith('/*'):
            i += 1
            continue
        if token == '\\' or (token.lower() == '@import' and not start):
            unknown.append((line, 'unsupported CSS escape or import context'))
        if token.lower() == '@import' and start:
            j, parens = i + 1, 0
            comments = []
            while j < len(tokens):
                part = tokens[j].group()
                if part == ';' and parens == 0:
                    break
                if part in ('{', '}') and parens == 0:
                    break
                if part == '(':
                    parens += 1
                elif part == ')':
                    parens -= 1
                if part.startswith('/*'):
                    comments.append((tokens[j].start(), tokens[j].end()))
                j += 1
            # Preserve whitespace between tokens, including in media conditions.
            end = tokens[j].start() if j < len(tokens) else len(text)
            body = text[tokens[i].end():end]
            for a, b in reversed(comments):
                a, b = a - tokens[i].end(), b - tokens[i].end()
                body = body[:a] + ' ' + body[b:]
            body = body.strip()
            match = CSS_IMPORT.fullmatch(body)
            if depth or not allowed or j == len(tokens) or tokens[j].group() != ';' or parens or not match:
                unknown.append((line, 'unsupported or malformed CSS import'))
            elif match.group(6).strip():
                unknown.append((line, 'conditional CSS import not evaluated'))
            else:
                refs.append((next((x for x in match.groups()[:5] if x is not None), ''), line, 'css-import'))
            i = j + 1 if j < len(tokens) and tokens[j].group() == ';' else j
            start = True
            continue
        if i == 0 and token.lower() == '@charset' and i + 2 < len(tokens):
            encoding, end = tokens[i + 1:i + 3]
            if encoding.group().startswith('"') and end.group() == ';':
                i += 3
                continue
        if depth == 0 and token != ';':
            allowed = False
        if token == '{':
            depth += 1
            start = True
        elif token == '}':
            depth = max(depth - 1, 0)
            start = True
        elif token == ';':
            start = True
        else:
            start = False
        i += 1
    return refs, unknown


def audit(root, graph, bindings):
    root = root.resolve()
    nodes = {n['id']: n for n in graph['nodes']}
    owners = defaultdict(set)
    unknown = []
    evidence = {ident: list(paths) for ident, paths in bindings['evidence'].items()}
    for ident, node in nodes.items():
        if node.get('type') in ('code', 'test') and node.get('source'):
            evidence.setdefault(ident, []).append(node['source'])
    for ident, paths in evidence.items():
        if nodes.get(ident, {}).get('type') not in ('code', 'test'):
            continue
        for name in paths:
            path = (root / name).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Evidence path outside project: ' + name)
            if path.suffix.lower() in SOURCE | {'.css'}:
                if not path.is_file():
                    unknown.append({'path': name, 'reason': 'bound source missing'})
                else:
                    owners[path].add(ident)
    # Unbound source importers are not silently treated as analyzed.
    source_roots = {root / p.relative_to(root).parts[0] for p in owners if len(p.relative_to(root).parts) > 1}
    candidates_on_disk = list(root.iterdir())
    for directory in source_roots:
        if directory.is_dir() and not directory.is_symlink():
            for folder, dirs, names in os.walk(directory, followlinks=False):
                dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'vendor'}]
                candidates_on_disk.extend(Path(folder) / name for name in names)
    discovered = set()
    for path in sorted(set(candidates_on_disk)):
        if any(part in ('.git', 'node_modules', 'vendor') for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in SOURCE:
            continue
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            unknown.append({'path': str(path.relative_to(root)), 'reason': 'source symlink outside project'})
        elif path.is_file() and path.resolve() not in owners:
            unknown.append({'path': str(path.relative_to(root)), 'reason': 'source file has no code/test binding'})
            discovered.add(path.resolve())
    if not any(path.suffix.lower() in SOURCE for path in owners):
        unknown.append({'path': '.', 'reason': 'no supported source importer bound to a code or test node'})
    adjacency = defaultdict(set)
    edge_types = set(bindings.get('dependency_edge_types', ['depends-on']))
    for edge in graph['edges']:
        if edge['type'] in edge_types:
            adjacency[edge['from']].add(edge['to'])

    def reachable(start, target):
        seen, pending = {start}, deque([start])
        while pending:
            for node in adjacency[pending.popleft()]:
                if node == target:
                    return True
                if node not in seen:
                    seen.add(node)
                    pending.append(node)
        return start == target

    observations, missing, candidates = [], [], []
    captured = {}
    for path in sorted(set(owners) | discovered):
        actual = path.resolve(strict=True)
        if not actual.is_relative_to(root) or not actual.is_file():
            raise ValueError('Source path escaped project during scan')
        captured[path] = actual.read_bytes()
    scanned_hashes = {str(path.relative_to(root)): hashlib.sha256(data).hexdigest() for path, data in captured.items()}
    scanned_files = sorted(scanned_hashes)
    def compare(source, target, evidence, certainty, kind):
        record = {'from': source, 'to': target, 'kind': kind, 'certainty': certainty, **evidence}
        record['declared_path'] = reachable(source, target)
        observations.append(record)
        if not record['declared_path']:
            (missing if certainty == 'proven' else candidates).append(record)

    # Coverage is a declared semantic relationship, not observed execution.
    for edge in graph['edges']:
        source, target = edge['from'], edge['to']
        if edge['type'] == 'checked by' and nodes.get(source, {}).get('type') == 'code' and nodes.get(target, {}).get('type') == 'test':
            compare(source, target, {'path': 'graph', 'line': None}, 'candidate', 'coverage')

    js_files = [{'path': str(path.relative_to(root)), 'text': captured[path].decode('utf-8')}
                for path in sorted(owners) if path.suffix.lower() in {'.js', '.mjs', '.cjs'}]
    parsed = parse_js(js_files, root)
    for path, source_ids in sorted(owners.items()):
        if path.suffix.lower() not in SOURCE:
            continue
        name = str(path.relative_to(root))
        text = captured[path].decode('utf-8')
        if path.suffix.lower() in {'.jsx', '.ts', '.tsx'}:
            refs = []
            unknown.append({'path': name, 'line': 1, 'reason': 'TypeScript or JSX not supported'})
        elif path.suffix.lower() in JS:
            item = parsed[name]
            refs = item['refs']
            unknown.extend({'path': name, **entry} for entry in item['unknown'])
        elif path.suffix.lower() == '.css':
            refs, css_unknown = parse_css(text)
            unknown.extend({'path': name, 'line': line, 'reason': reason} for line, reason in css_unknown)
        else:
            parser = Assets()
            parser.feed(text)
            refs = parser.refs
            unknown.extend({'path': name, 'line': line, 'reason': reason} for line, reason in parser.unknown)
        for spec, line, kind in refs:
            url = urlsplit(spec)
            if url.scheme or url.netloc or spec.startswith('//') or (not spec.startswith(('.', '/')) and kind not in ('script', 'link', 'css-import')):
                continue
            if '\\' in spec or '%' in spec:
                unknown.append({'path': name, 'line': line, 'reason': 'escaped or encoded asset path', 'specifier': spec})
                continue
            dest = ((root / unquote(url.path).lstrip('/')) if spec.startswith('/') else (path.parent / unquote(url.path))).resolve()
            choices = [dest] if dest.suffix else [dest, *(dest.with_suffix(ext) for ext in ('.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx')), *(dest / ('index' + ext) for ext in ('.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx'))]
            choices = [p for p in choices if p.is_relative_to(root) and p.is_file()]
            if len(choices) != 1:
                unknown.append({'path': name, 'line': line, 'reason': 'local target unresolved or ambiguous', 'specifier': spec})
                continue
            target_ids = owners.get(choices[0], set())
            if not target_ids:
                unknown.append({'path': name, 'line': line, 'reason': 'local target has no code/test binding', 'specifier': spec})
                continue
            # Dependency graph points from changed imported file to the impacted importer.
            pairs = {(target, source) for target in target_ids for source in source_ids if target != source}
            certainty = 'proven' if len(target_ids) == len(source_ids) == 1 else 'candidate'
            for source, target in sorted(pairs):
                compare(source, target, {'path': name, 'line': line, 'specifier': spec, 'target_path': str(choices[0].relative_to(root))}, certainty, 'source-import')
    return {'status': 'missing' if missing else 'unknown' if unknown or candidates else 'clear', 'observations': observations, 'missing': missing, 'candidates': candidates, 'unknown': unknown, 'scanned_files': scanned_files, 'scanned_hashes': scanned_hashes,
            'limitations': ['Static AST source references and declared code-to-test coverage only; coverage is a candidate, not observed execution. Navigation and screen appearances are not dependency proof.', 'Shared evidence bindings make source ownership ambiguous; dynamic imports and unbound local targets remain unknown.', 'CSS custom properties and other CSS asset references are not analyzed.', 'Does not execute code, resolve packages or prove complete runtime dependency coverage; unbound importer files outside the root and bound source trees are outside the scan.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--graph', required=True)
    parser.add_argument('--bindings', required=True)
    args = parser.parse_args(argv)
    try:
        root = Path(args.project).resolve(strict=True)
        def load(name):
            path = (root / name).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Input must be a file inside project: ' + name)
            return json.loads(path.read_text(encoding='utf-8'))
        result = audit(root, load(args.graph), load(args.bindings))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return {'clear': 0, 'missing': 1, 'unknown': 2}[result['status']]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
