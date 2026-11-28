#!/usr/bin/env python3
"""Find hardcoded values that bypass their single source of truth (SSoT).

Rules, owners, scope and reviewed exceptions live in ``tools/ssot-scan.json``.
Known debt is ratcheted in ``tools/ssot-baseline.json``: ``check`` fails when a
rule/path/key count grows beyond the baseline *and* when the baseline still
allows debt that has been removed, so fixed debt cannot silently return.

Python is analysed with ``ast`` (docstrings ignored). JavaScript/JSX is analysed
with a small line-bounded lexer that drops comments and keeps string, template,
regex, number, identifier and punctuation tokens.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path('tools/ssot-scan.json')
CONFIG_SCHEMA = 'figma-flow-ssot-scan-v1'
BASELINE_SCHEMA = 'figma-flow-ssot-baseline-v1'

# Detector vocabulary (what a finding *is*), not product configuration.
_HOST_RE = re.compile(r'(?:^|//|\\/\\/)(?:localhost|127\.0\.0\.1|127\\\.0\\\.0\\\.1)(?=$|[:/\\])')
_URL_PORT_RE = re.compile(r'(?:localhost|127\.0\.0\.1|127\\\.0\\\.0\\\.1):\d{2,5}\b')
_FLAG_PORT_RE = re.compile(r'--(?:[a-z]+-)*port[ =]\d{2,5}\b')
_ROUTE_RE = re.compile(r'^/control/[a-z][a-z-]*$')
_PORT_NAME_RE = re.compile(r'(?:^|_)port$', re.I)
_NET_CALLS = frozenset({'HTTPConnection', 'HTTPSConnection', 'urlopen', 'create_connection'})
_JS_COMPARE = frozenset({'<', '>', '<=', '>=', '==', '!=', '===', '!=='})
_JS_REGEX_PREV_WORDS = frozenset({'return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete',
                                  'void', 'throw', 'instanceof', 'yield', 'await'})
_JS_PUNCT = sorted(['>>>=', '...', '===', '!==', '**=', '<<=', '>>=', '>>>', '&&=', '||=', '??=',
                    '=>', '==', '!=', '<=', '>=', '&&', '||', '??', '?.', '++', '--', '+=', '-=', '*=',
                    '/=', '%=', '&=', '|=', '^=', '**', '<<', '>>'], key=len, reverse=True)
_JS_NUMBER_RE = re.compile(r'0[xX][0-9a-fA-F_]+n?|0[bB][01_]+n?|0[oO][0-7_]+n?|'
                           r'(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?n?')
_JS_IDENT_RE = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    key: str
    message: str

    @property
    def bucket(self) -> str:
        return f'{self.rule}|{self.path}|{self.key}'


# --------------------------------------------------------------------------- config

def load_config(root: Path = ROOT) -> dict:
    data = json.loads((root / CONFIG).read_bytes())
    if data.get('schema') != CONFIG_SCHEMA:
        raise ValueError('Unknown SSoT scan configuration schema')
    rules = data.get('rules')
    if not isinstance(rules, dict) or not rules:
        raise ValueError('SSoT scan configuration needs rules')
    for rule_id, rule in rules.items():
        if not isinstance(rule, dict) or not isinstance(rule.get('message'), str):
            raise ValueError(f'Rule {rule_id} needs a message')
    for entry in data.get('allow', []):
        if set(entry) != {'rule', 'path', 'key', 'reason'} or not entry['reason'].strip():
            raise ValueError('Every reviewed exception needs rule, path, key and a reason')
        if entry['rule'] not in rules:
            raise ValueError(f'Exception references unknown rule {entry["rule"]}')
    return data


def _listed_files(root: Path) -> list[str]:
    if (root / '.git').exists():
        try:
            raw = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'],
                                          cwd=root, stderr=subprocess.DEVNULL)
            return sorted({name.decode() for name in raw.split(b'\0') if name})
        except (OSError, subprocess.SubprocessError):
            pass
    skip = {'.git', 'node_modules', '__pycache__', '.figma-flow'}
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*')
                  if path.is_file() and not skip & set(path.relative_to(root).parts))


def _matches(name: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def scoped_files(root: Path, config: dict) -> dict[str, list[str]]:
    scope = config['scope']
    excluded = scope.get('exclude', [])
    result = {'python': [], 'javascript': []}
    for name in _listed_files(root):
        path = root / name
        if _matches(name, excluded) or not path.is_file() or path.is_symlink():
            continue
        for language in result:
            if _matches(name, scope.get(language, [])):
                result[language].append(name)
                break
    return result


# --------------------------------------------------------------------------- python

def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if isinstance(body, list):
            for statement in body:
                if (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
                        and isinstance(statement.value.value, str)):
                    ids.add(id(statement.value))
    return ids


def _number(node) -> int | float | None:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_net_call(node) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = _call_name(node)
    if name in _NET_CALLS or name == 'settimeout':
        return True
    return (name == 'open' and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and 'opener' in node.func.value.id.lower())


def _fmt(value) -> str:
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def _vocabulary(root: Path, spec: dict) -> tuple[set[str], tuple[int, int] | None]:
    """Read vocabulary values from their owning Python assignment (the SSoT)."""
    owner = root / spec['owner']
    if not owner.is_file():
        return set(), None
    tree = ast.parse(owner.read_bytes(), filename=spec['owner'])
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if not any(isinstance(t, ast.Name) and t.id == spec['symbol'] for t in targets) or node.value is None:
            continue
        values = set()
        for element in getattr(node.value, 'elts', []):
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                values.add(element.value)
            elif isinstance(element, ast.Dict) and spec.get('field'):
                for key, value in zip(element.keys, element.values):
                    if (isinstance(key, ast.Constant) and key.value == spec['field']
                            and isinstance(value, ast.Constant) and isinstance(value.value, str)):
                        values.add(value.value)
        return values - set(spec.get('ignoreValues', [])), (node.lineno, node.end_lineno)
    return set(), None


def scan_python(name: str, source: bytes, rules: dict, vocabularies: list) -> tuple[list[Finding], list[tuple]]:
    findings: list[Finding] = []
    schema_hits: list[tuple] = []
    try:
        tree = ast.parse(source, filename=name)
    except SyntaxError as error:
        return [Finding('parse-error', name, error.lineno or 1, 'syntax', 'File could not be parsed')], []
    docstrings = _docstring_ids(tree)
    minimum = rules.get('inline-limit', {}).get('minimum', 1000)
    schema_re = re.compile(rules['schema-id-spread']['pattern']) if 'schema-id-spread' in rules else None
    lines = source.decode('utf-8', errors='replace').splitlines()

    def add(rule, node, key):
        if rule in rules:
            findings.append(Finding(rule, name, getattr(node, 'lineno', 1), key, rules[rule]['message']))

    def based(node) -> bool:
        # Hex/octal/binary literals are code points or bit masks (same as the JS lexer).
        line = lines[node.lineno - 1] if 0 < getattr(node, 'lineno', 0) <= len(lines) else ''
        return line[node.col_offset:node.col_offset + 2].lower() in ('0x', '0o', '0b')

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            text = node.value
            match = _HOST_RE.search(text)
            if match:
                add('loopback-literal', node, match.group(0).lstrip('/\\'))
            for pattern in (_URL_PORT_RE, _FLAG_PORT_RE):
                for hit in pattern.finditer(text):
                    add('port-literal', node, re.search(r'\d+$', hit.group(0)).group(0))
            if _ROUTE_RE.match(text):
                add('control-route-literal', node, text)
            if schema_re and schema_re.fullmatch(text):
                schema_hits.append((text, node.lineno))
            for vocabulary in vocabularies:
                values, span = vocabulary['values'], vocabulary['span']
                if text in values and not (vocabulary['owner'] == name and span and span[0] <= node.lineno <= span[1]):
                    add('vocabulary-literal', node, f'{vocabulary["id"]}:{text}')
        elif isinstance(node, ast.Call):
            call = _call_name(node)
            if _is_net_call(node):
                exprs = [kw.value for kw in node.keywords if kw.arg == 'timeout']
                if call == 'settimeout':
                    exprs += node.args[:1]
                for expr in exprs:
                    for inner in ast.walk(expr):
                        value = _number(inner)
                        if value is not None and value > 0:
                            add('network-timeout-literal', inner, _fmt(value))
            if call == 'add_argument' and any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                                               and a.value.startswith('--') and _PORT_NAME_RE.search(a.value.replace('-', '_'))
                                               for a in node.args):
                for kw in node.keywords:
                    value = _number(kw.value)
                    if kw.arg == 'default' and isinstance(value, int) and value > 0:
                        add('port-literal', kw.value, str(value))
            if call == 'read' and node.args:
                value = _number(node.args[0])
                if isinstance(value, int) and value >= minimum:
                    add('inline-limit', node.args[0], str(value))
        elif isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                value = _number(operand)
                if value is not None and not isinstance(value, bool) and abs(value) >= minimum and not based(operand):
                    add('inline-limit', operand, _fmt(value))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = [*node.args.posonlyargs, *node.args.args]
            pairs = list(zip(positional[len(positional) - len(node.args.defaults):], node.args.defaults))
            pairs += [(a, d) for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d is not None]
            has_net = any(_is_net_call(inner) for inner in ast.walk(node))
            for arg, default in pairs:
                value = _number(default)
                if value is None or isinstance(value, bool):
                    continue
                if _PORT_NAME_RE.search(arg.arg) and isinstance(value, int) and value > 0:
                    add('port-literal', default, str(value))
                if arg.arg == 'timeout' and has_net and value > 0:
                    add('network-timeout-literal', default, _fmt(value))
            if any(_number(c) == 0o600 for c in ast.walk(node)) and any(
                    isinstance(c, ast.Call) and _call_name(c) in ('replace', 'rename')
                    and isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)
                    and c.func.value.id == 'os' for c in ast.walk(node)):
                add('private-atomic-writer', node, node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = _number(node.value) if node.value is not None else None
            if isinstance(value, int) and 1024 <= value <= 65535 and any(
                    isinstance(t, ast.Name) and 'PORT' in t.id.upper() for t in targets):
                add('port-literal', node.value, str(value))
    return findings, schema_hits


# --------------------------------------------------------------------------- javascript

def js_tokens(text: str) -> list[tuple[str, str, int]]:
    """Tokenize JS/JSX without comments. Strings and regexes never span lines."""
    tokens: list[tuple[str, str, int]] = []
    i, n, line = 0, len(text), 1

    def regex_allowed():
        if not tokens:
            return True
        kind, value, _ = tokens[-1]
        if kind == 'p':
            return value not in (')', ']', '}')
        return kind == 'id' and value in _JS_REGEX_PREV_WORDS

    while i < n:
        c = text[i]
        if c == '\n':
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif text.startswith('//', i):
            end = text.find('\n', i)
            i = n if end < 0 else end
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            end = n if end < 0 else end + 2
            line += text.count('\n', i, end)
            i = end
        elif c in '\'"':
            j = i + 1
            while j < n and text[j] != c and text[j] != '\n':
                j += 2 if text[j] == '\\' else 1
            tokens.append(('str', text[i + 1:min(j, n)], line))
            i = j + 1 if j < n and text[j] == c else j
        elif c == '`':
            j, depth = i + 1, 0
            while j < n:
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if depth == 0 and ch == '`':
                    break
                if text.startswith('${', j):
                    depth += 1
                    j += 2
                    continue
                if ch == '}' and depth:
                    depth -= 1
                j += 1
            tokens.append(('tmpl', text[i + 1:min(j, n)], line))
            line += text.count('\n', i, min(j, n))
            i = j + 1
        elif c == '/' and regex_allowed():
            j, in_class = i + 1, False
            while j < n and text[j] != '\n':
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == '[':
                    in_class = True
                elif ch == ']':
                    in_class = False
                elif ch == '/' and not in_class:
                    break
                j += 1
            if j < n and text[j] == '/':
                k = j + 1
                while k < n and text[k].isalpha():
                    k += 1
                tokens.append(('re', text[i + 1:j], line))
                i = k
            else:
                tokens.append(('p', '/', line))
                i += 1
        elif c.isdigit() or (c == '.' and i + 1 < n and text[i + 1].isdigit()):
            match = _JS_NUMBER_RE.match(text, i)
            tokens.append(('num', match.group(0), line))
            i = match.end()
        elif c.isalpha() or c in '_$':
            match = _JS_IDENT_RE.match(text, i)
            tokens.append(('id', match.group(0), line))
            i = match.end()
        else:
            op = next((p for p in _JS_PUNCT if text.startswith(p, i)), c)
            tokens.append(('p', op, line))
            i += len(op)
    return tokens


def _js_number(raw: str) -> float | None:
    if raw[:2].lower() in ('0x', '0b', '0o') or raw.endswith('n'):
        return None
    try:
        return float(raw.replace('_', ''))
    except ValueError:
        return None


def scan_javascript(name: str, text: str, rules: dict) -> tuple[list[Finding], list[tuple]]:
    findings: list[Finding] = []
    schema_hits: list[tuple] = []
    tokens = js_tokens(text)
    minimum = rules.get('inline-limit', {}).get('minimum', 1000)
    schema_re = re.compile(rules['schema-id-spread']['pattern']) if 'schema-id-spread' in rules else None

    def add(rule, line, key):
        if rule in rules:
            findings.append(Finding(rule, name, line, key, rules[rule]['message']))

    for index, (kind, value, line) in enumerate(tokens):
        if kind in ('str', 'tmpl', 're'):
            match = _HOST_RE.search(value)
            if match:
                add('loopback-literal', line, match.group(0).replace('\\', '').lstrip('/'))
            if kind != 're':
                for hit in _URL_PORT_RE.finditer(value):
                    add('port-literal', line, hit.group(0).rsplit(':', 1)[-1])
                if _ROUTE_RE.match(value):
                    add('control-route-literal', line, value)
                if kind == 'str' and schema_re and schema_re.fullmatch(value):
                    schema_hits.append((value, line))
        elif kind == 'id' and value in ('setTimeout', 'setInterval') and index + 1 < len(tokens) \
                and tokens[index + 1][1] == '(':
            depth, last_arg_start, j = 0, None, index + 1
            while j < len(tokens):
                t_kind, t_value, _ = tokens[j]
                if t_kind == 'p' and t_value in '([{':
                    depth += 1
                elif t_kind == 'p' and t_value in ')]}':
                    depth -= 1
                    if depth == 0:
                        break
                elif t_kind == 'p' and t_value == ',' and depth == 1:
                    last_arg_start = j + 1
                j += 1
            if last_arg_start is not None and j - last_arg_start == 1 and tokens[last_arg_start][0] == 'num':
                number = _js_number(tokens[last_arg_start][1])
                if number:
                    add('timer-literal', tokens[last_arg_start][2], _fmt(number))
        elif kind == 'num':
            number = _js_number(value)
            if number is None or number < minimum:
                continue
            before = tokens[index - 1] if index else None
            after = tokens[index + 1] if index + 1 < len(tokens) else None
            if (before and before[0] == 'p' and before[1] in _JS_COMPARE) or \
                    (after and after[0] == 'p' and after[1] in _JS_COMPARE):
                add('inline-limit', line, _fmt(number))
    return findings, schema_hits


# --------------------------------------------------------------------------- scan

def scan(root: Path = ROOT, config: dict | None = None) -> list[Finding]:
    root = Path(root)
    config = config or load_config(root)
    rules = config['rules']
    vocabularies = []
    for spec in rules.get('vocabulary-literal', {}).get('vocabularies', []):
        values, span = _vocabulary(root, spec)
        if not values:
            raise ValueError(f'Vocabulary {spec["id"]} has no values in {spec["owner"]}:{spec["symbol"]}')
        vocabularies.append({**spec, 'values': values, 'span': span})
    files = scoped_files(root, config)
    findings: list[Finding] = []
    schema_index: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for name in files['python']:
        found, hits = scan_python(name, (root / name).read_bytes(), rules, vocabularies)
        findings += found
        for value, line in hits:
            schema_index[value].append((name, line))
    for name in files['javascript']:
        found, hits = scan_javascript(name, (root / name).read_text(encoding='utf-8', errors='replace'), rules)
        findings += found
        for value, line in hits:
            schema_index[value].append((name, line))
    spread = rules.get('schema-id-spread')
    mirrors = list(config.get('mirrors', []))
    if spread:
        registry = load_schema_registry(root, spread) if spread.get('registry') else {}
        for value, hits in schema_index.items():
            entry = registry.get(value)
            if entry is not None:
                # Registered IDs: Python imports schema_ids; non-importing runtimes keep verified mirrors.
                for path, line in hits:
                    if path.endswith('.py'):
                        findings.append(Finding('schema-id-spread', path, line, value,
                                                f'Registered schema ID; use schema_ids.ID[{entry["name"]!r}].'))
                    else:
                        findings.append(Finding('schema-id-spread', path, line, value, spread['message']))
            elif len({path for path, _ in hits}) > spread.get('maxFiles', 1):
                findings += [Finding('schema-id-spread', path, line, value, spread['message']) for path, line in hits]
        for value, entry in registry.items():
            if entry['mirrors']:
                mirrors.append({'rule': 'schema-id-spread', 'key': value, 'paths': entry['mirrors'],
                                'source': f'{spread["registry"]}#/ids/{entry["name"]}/id'})
    allowed = {(a['rule'], a['path'], a['key']) for a in config.get('allow', [])}
    owners = {rule_id: set(rule.get('owners', [])) for rule_id, rule in rules.items()}
    findings = [f for f in findings if f.path not in owners.get(f.rule, ()) and (f.rule, f.path, f.key) not in allowed]
    findings = apply_mirrors(root, mirrors, findings)
    return sorted(findings, key=lambda f: (f.rule, f.path, f.line, f.key))


HARD_RULES = frozenset({'mirror-drift', 'mirror-stale', 'parse-error'})


def resolve_source(root: Path, source: str):
    """Resolve ``path#/json/pointer`` against a repository JSON file."""
    path, _, pointer = source.partition('#')
    value = json.loads((root / path).read_bytes())
    for part in [p.replace('~1', '/').replace('~0', '~') for p in pointer.split('/')[1:]]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def apply_mirrors(root: Path, mirrors: list, findings: list[Finding]) -> list[Finding]:
    """Suppress declared copies in runtimes that cannot import the SSoT, after verifying them.

    A mirror whose SSoT value differs from its key reports ``mirror-drift``; a declared path
    that no longer contains the copy reports ``mirror-stale``. Both fail ``check`` regardless
    of the baseline.
    """
    by_bucket: dict[tuple[str, str, str], list[Finding]] = defaultdict(list)
    for finding in findings:
        by_bucket[(finding.rule, finding.path, finding.key)].append(finding)
    claimed: Counter[tuple[str, str, str]] = Counter()
    suppressed: set[tuple[str, str, str]] = set()
    extra: list[Finding] = []
    for mirror in mirrors:
        if set(mirror) - {'rule', 'key', 'paths', 'source', 'name'} or not mirror.get('paths'):
            raise ValueError(f'Invalid mirror declaration: {mirror}')
        try:
            value = resolve_source(root, mirror['source'])
        except (OSError, KeyError, IndexError, ValueError):
            value = None
        expected = value if isinstance(value, str) else _fmt(value) if type(value) in (int, float) else None
        anchor = mirror['source'].partition('#')[0]
        if expected != mirror['key']:
            extra.append(Finding('mirror-drift', anchor, 1, f'{mirror["rule"]}:{mirror["key"]}',
                                 f'Mirror source {mirror["source"]} is {value!r}; update the declared copies and the mirror key.'))
            continue
        for path in mirror['paths']:
            bucket = (mirror['rule'], path, mirror['key'])
            claimed[bucket] += 1
            if len(by_bucket.get(bucket, ())) < claimed[bucket]:
                extra.append(Finding('mirror-stale', path, 1, f'{mirror["rule"]}:{mirror["key"]}',
                                     f'Declared mirror of {mirror["source"]} no longer appears here; remove the declaration.'))
            else:
                suppressed.add(bucket)
    return [f for f in findings if (f.rule, f.path, f.key) not in suppressed] + extra


def load_schema_registry(root: Path, spread: dict) -> dict[str, dict]:
    data = json.loads((root / spread['registry']).read_bytes())
    if data.get('schema') != 'figma-flow-schema-id-registry-v1' or not isinstance(data.get('ids'), dict):
        raise ValueError('Unknown schema ID registry')
    pattern = re.compile(spread['pattern'])
    result = {}
    for name, entry in data['ids'].items():
        if (not isinstance(entry, dict) or set(entry) - {'id', 'mirrors', 'description'}
                or not isinstance(entry.get('id'), str) or not pattern.fullmatch(entry['id'])
                or not isinstance(entry.get('mirrors', []), list) or entry['id'] in result):
            raise ValueError(f'Invalid schema ID registry entry {name}')
        result[entry['id']] = {'name': name, 'mirrors': list(entry.get('mirrors', []))}
    return result


def counts(findings) -> dict[str, int]:
    return dict(sorted(Counter(f.bucket for f in findings).items()))


def load_baseline(root: Path, config: dict) -> dict[str, int]:
    path = root / config['baseline']
    if not path.is_file():
        return {}
    data = json.loads(path.read_bytes())
    if data.get('schema') != BASELINE_SCHEMA or not isinstance(data.get('entries'), dict):
        raise ValueError('Unknown SSoT baseline schema')
    return {key: int(value) for key, value in data['entries'].items()}


def compare(findings, baseline: dict[str, int]) -> dict:
    current = counts(findings)
    grown = {k: (baseline.get(k, 0), v) for k, v in current.items() if v > baseline.get(k, 0)}
    stale = {k: (v, current.get(k, 0)) for k, v in baseline.items() if current.get(k, 0) < v}
    return {'current': current, 'grown': grown, 'stale': stale}


def check(root: Path = ROOT) -> list[dict]:
    """Return maintenance findings: new debt beyond the baseline and resolved-but-unlocked debt."""
    root = Path(root)
    config = load_config(root)
    findings = scan(root, config)
    result = compare(findings, load_baseline(root, config))
    problems = []
    by_bucket = defaultdict(list)
    for finding in findings:
        by_bucket[finding.bucket].append(finding)
    for finding in findings:
        if finding.rule in HARD_RULES:
            problems.append({'path': finding.path, 'line': finding.line,
                             'message': f'[ssot:{finding.rule}] {finding.key}: {finding.message}'})
    for bucket, (allowed, found) in result['grown'].items():
        if bucket.split('|', 1)[0] in HARD_RULES:
            continue
        for finding in by_bucket[bucket]:
            problems.append({'path': finding.path, 'line': finding.line,
                             'message': f'[ssot:{finding.rule}] {finding.key}: {finding.message} '
                                        f'({found} found, baseline allows {allowed})'})
    for bucket, (allowed, found) in result['stale'].items():
        problems.append({'path': config['baseline'], 'line': 1,
                         'message': f'[ssot:baseline] {bucket} dropped from {allowed} to {found}; '
                                    'lock it in with `python3 -B tools/ssot_scan.py baseline --write`.'})
    return problems


def write_baseline(root: Path, *, allow_growth: bool = False) -> dict:
    config = load_config(root)
    findings = scan(root, config)
    result = compare(findings, load_baseline(root, config))
    hard = [f for f in findings if f.rule in HARD_RULES]
    if hard:
        raise ValueError('Fix mirror/parse problems before writing a baseline: '
                         + ', '.join(f'{f.path}:{f.rule}:{f.key}' for f in hard))
    if result['grown'] and not allow_growth:
        raise ValueError('New SSoT debt found; fix it or rerun with --allow-growth after review: '
                         + ', '.join(sorted(result['grown'])))
    path = root / config['baseline']
    raw = (json.dumps({'schema': BASELINE_SCHEMA, 'entries': result['current']}, indent=2,
                      ensure_ascii=False) + '\n').encode()
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        os.chmod(temporary, 0o644)
        Path(temporary).replace(path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'entries': len(result['current']), 'findings': len(findings),
            'removed': len(result['stale']), 'added': len(result['grown'])}


def summary(root: Path = ROOT) -> dict:
    config = load_config(root)
    findings = scan(root, config)
    baseline = load_baseline(root, config)
    result = compare(findings, baseline)
    rules = defaultdict(lambda: {'findings': 0, 'files': set(), 'new': 0})
    for finding in findings:
        row = rules[finding.rule]
        row['findings'] += 1
        row['files'].add(finding.path)
    for bucket, (allowed, found) in result['grown'].items():
        rules[bucket.split('|', 1)[0]]['new'] += found - allowed
    return {'schema': 'figma-flow-ssot-summary-v1', 'findings': len(findings),
            'new': sum(r['new'] for r in rules.values()), 'stale_buckets': len(result['stale']),
            'rules': {rule: {'findings': row['findings'], 'files': len(row['files']), 'new': row['new']}
                      for rule, row in sorted(rules.items())}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('scan', help='List every finding (baselined or not)')
    listing.add_argument('--json', action='store_true')
    listing.add_argument('--rule')
    listing.add_argument('--path', help='fnmatch pattern for repository-relative paths')
    commands.add_parser('summary', help='Counts per rule, including new debt beyond the baseline')
    commands.add_parser('check', help='Fail on new debt or on resolved debt not yet removed from the baseline')
    baseline = commands.add_parser('baseline', help='Rewrite the ratchet baseline from the current scan')
    baseline.add_argument('--write', action='store_true', required=True)
    baseline.add_argument('--allow-growth', action='store_true',
                          help='Accept new debt (requires review; prefer fixing it)')
    args = parser.parse_args(argv)
    try:
        if args.command == 'scan':
            findings = [f for f in scan(ROOT) if (not args.rule or f.rule == args.rule)
                        and (not args.path or fnmatch.fnmatchcase(f.path, args.path))]
            if args.json:
                print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
            else:
                for f in findings:
                    print(f'{f.path}:{f.line}: [{f.rule}] {f.key}')
                print(f'{len(findings)} finding(s)', file=sys.stderr)
            return 0
        if args.command == 'summary':
            print(json.dumps(summary(ROOT), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'check':
            problems = check(ROOT)
            for item in problems:
                print(f"{item['path']}:{item['line']}: {item['message']}", file=sys.stderr)
            return int(bool(problems))
        print(json.dumps(write_baseline(ROOT, allow_growth=args.allow_growth)))
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f'ssot_scan: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
