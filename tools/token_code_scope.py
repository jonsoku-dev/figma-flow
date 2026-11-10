#!/usr/bin/env python3
"""Bounded static token-consumer report and guarded generated CSS update."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
import stat
import tempfile
from pathlib import Path
import re
import sys

from design_system import compile_design, components_css, render

VAR = re.compile(r'var\(\s*(--[\w-]+)')
RULE = re.compile(r'([^{}]+)\{([^{}]*)\}')
DECL = re.compile(r'([\w-]+)\s*:\s*([^;]+)')
CLASS = re.compile(r'\.([\w-]+)')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def within(root, relative):
    part = Path(relative)
    if part.is_absolute() or '..' in part.parts:
        raise ValueError(f'unsafe project path: {relative}')
    path = root / part
    current = root
    for component in part.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f'symlink in project path: {relative}')
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'unsafe project path: {relative}')
    return path


def mask_comments_and_strings(source, strings=True):
    # Preserve offsets and line numbers for source evidence.
    pattern = r"""/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`"""
    def mask(match):
        value = match.group()
        if not strings and value[0] in '"\'`':
            return value
        return ''.join('\n' if c == '\n' else ' ' for c in value)
    return re.sub(pattern, mask, source)


class HTMLUses(HTMLParser):
    def __init__(self, screens):
        super().__init__()
        self.screens, self.stack, self.uses = screens, [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        screen = attrs.get('id') if attrs.get('id') in self.screens else (self.stack[-1][1] if self.stack else None)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, screen))
        for name in attrs.get('class', '').split():
            self.uses.append((name, self.getpos()[0], screen, attrs.get('class', '').split()))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def analyze(project, before, after, apply=False):
    root = Path(project).resolve(strict=True)
    old = compile_design(read_json(before) if isinstance(before, (str, Path)) else before)
    new = compile_design(read_json(after) if isinstance(after, (str, Path)) else after)
    graph, bindings = read_json(within(root, 'graph.json')), read_json(within(root, 'bindings.json'))
    if graph.get('version') != 1 or bindings.get('version') != 1 or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('edges'), list) or not isinstance(bindings.get('evidence'), dict):
        raise ValueError('invalid graph or bindings metadata')
    nodes = {n['id']: n['type'] for n in graph['nodes']}
    if len(nodes) != len(graph['nodes']) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in nodes.items()):
        raise ValueError('invalid or duplicate graph nodes')
    for edge in graph['edges']:
        if edge.get('from') not in nodes or edge.get('to') not in nodes or not isinstance(edge.get('type'), str):
            raise ValueError('invalid graph edge')
    for node, paths in bindings['evidence'].items():
        if node not in nodes or not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError('invalid binding evidence')
        for path in paths:
            within(root, path)
    screens = {k for k, v in nodes.items() if v == 'screen'}
    evidence = bindings['evidence']
    codepaths = {}
    for code, paths in evidence.items():
        if nodes.get(code) == 'code':
            for p in paths:
                if p.startswith('app/'):
                    codepaths.setdefault(p, []).append(code)
    changed = {k for k in old['tokens'].keys() | new['tokens'].keys() if old['tokens'].get(k) != new['tokens'].get(k)}
    css_changed = {'--' + x.replace('.', '-') for x in changed}
    declarations, aliases, gaps, unknowns = [], {}, [], []
    app = within(root, 'app')
    runtime_extensions = {'.html', '.htm', '.css', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.vue', '.svelte'}
    inventory = []
    if not app.is_dir():
        raise ValueError('app directory is missing')
    for path in sorted(app.rglob('*')):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            unknowns.append({'source': rel, 'reason': 'symlinked runtime path was not inspected'})
            continue
        if path.is_file() and path.suffix.lower() in runtime_extensions:
            inventory.append(rel)
            if len(inventory) > 500:
                raise ValueError('runtime source inventory exceeds 500 files')
            if path.stat().st_size > 2_000_000:
                unknowns.append({'source': rel, 'reason': 'runtime file exceeds 2 MB and was not inspected'})
                continue
            if rel not in codepaths:
                unknowns.append({'source': rel, 'reason': 'runtime source is not bound to a graph code node'})
            elif path.suffix.lower() not in {'.css', '.html', '.js'}:
                unknowns.append({'source': rel, 'reason': 'runtime source language is unsupported'})
    for path in sorted(codepaths):
        if path.startswith('app/') and not within(root, path).is_file():
            unknowns.append({'source': path, 'reason': 'bound runtime source is missing'})
    css_files = sorted(p for p in codepaths if p.endswith('.css') and within(root, p).is_file() and within(root, p).stat().st_size <= 2_000_000)

    for path in css_files:
        data = within(root, path).read_text(encoding='utf-8')
        if '@' in data or '/*' in data:
            gaps.append(f'{path}: nested rules, comments or at-rules may not be fully analyzed')
        clean = mask_comments_and_strings(data)
        for rule in RULE.finditer(clean):
            selector, body = rule.groups()
            for decl in DECL.finditer(body):
                prop, value = decl.groups()
                refs = VAR.findall(value)
                if prop.startswith('--'):
                    aliases.setdefault(prop, set()).update(refs)
                    if selector.strip() != ':root':
                        unknowns.append({'source': path, 'line': data.count('\n', 0, rule.start() + len(selector) - len(selector.lstrip())) + 1, 'selector': selector.strip(), 'reason': 'scoped custom property definition may affect runtime cascade'})
                elif refs:
                    names = CLASS.findall(selector)
                    simple = bool(re.fullmatch(r'\s*\.[\w-]+\s*', selector))
                    for name in names:
                        declarations.append((path, data.count('\n', 0, rule.start() + len(selector) - len(selector.lstrip())) + 1, name, prop, refs, simple))
                    if not names:
                        unknowns.append({'source': path, 'line': data.count('\n', 0, rule.start() + len(selector) - len(selector.lstrip())) + 1, 'selector': selector.strip(), 'property': prop, 'tokens': refs, 'reason': 'token consumer selector has no class and is not mapped'})
                    if not simple:
                        gaps.append(f'{path}: complex selector {selector.strip()!r} requires runtime verification')
    def reaches(name, seen=None):
        seen = set() if seen is None else seen
        if name in seen:
            return False
        seen.add(name)
        return name in css_changed or any(reaches(n, seen) for n in aliases.get(name, ()))
    relevant = [x for x in declarations if any(reaches(v) for v in x[4])]
    uses = []
    for path in sorted(codepaths):
        if not path.endswith(('.html', '.js')) or not within(root, path).is_file() or within(root, path).stat().st_size > 2_000_000:
            continue
        data = within(root, path).read_text(encoding='utf-8')
        if path.endswith('.html'):
            parser = HTMLUses(screens)
            parser.feed(data)
            found = parser.uses
            for match in re.finditer(r'<style\b|\bstyle\s*=', data, re.I):
                unknowns.append({'source': path, 'line': data.count('\n', 0, match.start()) + 1, 'reason': 'inline style or style element is not analyzed'})
        else:
            found = []
            clean = mask_comments_and_strings(data, strings=False)
            code_only = mask_comments_and_strings(data)
            for match in re.finditer(r'\.className\s*=\s*([\'\"])([^\'\"]*)\1|\.classList\.(?:add|toggle|remove)\(\s*([\'\"])([^\'\"]*)\3', clean):
                if not code_only[match.start():match.start() + 1].strip():
                    continue
                for cls in (match.group(2) or match.group(4)).split():
                    found.append((cls, data.count('\n', 0, match.start()) + 1, None, (match.group(2) or match.group(4)).split()))
            gaps.append(f'{path}: computed classes and runtime DOM placement are not resolved')
            for match in re.finditer(r'\.style\b|\.setProperty\s*\(|\.cssText\b|<style\b|style\s*=', clean):
                unknowns.append({'source': path, 'line': data.count('\n', 0, match.start()) + 1, 'reason': 'dynamic or embedded style may use tokens and is not analyzed'})
        for cls, line, screen, all_classes in found:
            for css_path, css_line, name, prop, refs, simple in relevant:
                if cls != name:
                    continue
                owners = sorted(codepaths[path])
                implementations = [e for e in graph['edges'] if e['type'] == 'implemented by' and e['to'] in owners]
                traces = [[e['from'], e['to']] for e in implementations if e['from'] in screens]
                traces += [[edge['from'], edge['to'], impl['to']] for impl in implementations for edge in graph['edges'] if edge['type'] == 'has state' and edge['from'] in screens and edge['to'] == impl['from']]
                inferred_screens = sorted({trace[0] for trace in traces})
                uses.append({'source': path, 'line': line, 'class': cls, 'property': prop, 'css_source': css_path, 'css_line': css_line, 'tokens': refs, 'component': cls.split('--', 1)[0] if '--' in cls else None, 'code_ids': owners, 'screen_ids': [screen] if screen else [], 'candidate_screen_ids': [] if screen else inferred_screens, 'candidate_screen_traces': [] if screen else sorted(traces), 'co_classes': all_classes, 'evidence': 'literal class' if simple else 'class only; selector match unproven'})
    candidates = []
    for screen in new['screens']:
        for el in screen['elements']:
            if el['kind'] == 'component' and any(x[2] == el['component'] + '--' + el['variant'] for x in relevant):
                candidates.append({'screen_id': screen['id'], 'component': el['component'], 'variant': el['variant'], 'element_id': el.get('id')})
    for _, _, cls, _, _, _ in relevant:
        if not any(x['class'] == cls for x in uses):
            gaps.append(f'{cls}: affected CSS selector has no observed literal class usage')
    overrides = []
    for path in css_files:
        data = within(root, path).read_text(encoding='utf-8')
        clean = mask_comments_and_strings(data)
        for rule in RULE.finditer(clean):
            selector, body = rule.groups()
            names = CLASS.findall(selector)
            for decl in DECL.finditer(body):
                prop, value = decl.groups()
                if VAR.search(value):
                    continue
                for use in uses:
                    if prop == use['property'] and any(n in use['co_classes'] for n in names):
                        overrides.append({'source': path, 'line': data.count('\n', 0, rule.start() + len(selector) - len(selector.lstrip())) + 1, 'selector': selector.strip(), 'property': prop, 'value': value.strip(), 'consumer_source': use['source'], 'consumer_line': use['line'], 'status': 'candidate; cascade and selector match unverified'})
    plan = []
    generated = [('app/tokens.css', render(old, True)[1], render(new, True)[1]), ('app/components.css', components_css(old), components_css(new))]
    for path, expected, target in generated:
        if path not in codepaths:
            if expected != target:
                raise ValueError(f'{path}: changed generated asset is not bound to a code node')
            gaps.append(f'{path}: generated asset is not bound to a code node')
            continue
        current = within(root, path).read_bytes()
        if current == target.encode():
            continue
        if expected == target:
            gaps.append(f'{path}: generated CSS differs from design; left unchanged')
            continue
        if current != expected.encode():
            raise ValueError(f'{path}: generated CSS differs from before design; refusing overwrite')
        plan.append({'path': path, 'preimage_sha256': digest(current), 'content': target})
    result = {'version': 1, 'changed_tokens': sorted(changed), 'observed_consumers': uses, 'structural_candidates': candidates, 'possible_overrides': overrides, 'runtime_inventory': inventory, 'unknowns': unknowns, 'gaps': sorted(set(gaps)), 'plan': plan, 'limitations': ['Static literal evidence only; dynamic classes, cascade, selector matching and runtime visibility are not established.']}
    if apply:
        apply_plan(root, result['plan'])
    return result


def apply_changes(project, changes):
    """Commit only allowlisted, preimage-pinned files; restore our writes on error."""
    root = Path(project).resolve(strict=True)
    allowed = {'design.json', 'app/tokens.css', 'app/components.css'}
    seen, prepared, committed = set(), [], []

    def checked(path, expected):
        target = within(root, path)
        info = target.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f'{path}: target must be an unlinked regular file')
        content = target.read_bytes()
        if digest(content) != expected:
            raise ValueError(f'{path}: stale preimage')
        return target, info, content

    def stage(target, content, mode):
        fd, name = tempfile.mkstemp(prefix='.token-scope-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, stat.S_IMODE(mode))
            return Path(name)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise

    try:
        for item in changes:
            path = item['path']
            if path not in allowed or path in seen or not isinstance(item.get('content'), str) or not re.fullmatch(r'[0-9a-f]{64}', item.get('preimage_sha256', '')):
                raise ValueError(f'invalid or duplicate change: {path}')
            seen.add(path)
            target, info, original = checked(path, item['preimage_sha256'])
            prepared.append({'item': item, 'target': target, 'info': info, 'original': original})
        for entry in prepared:
            entry['staged'] = stage(entry['target'], entry['item']['content'].encode('utf-8'), entry['info'].st_mode)
            entry['backup'] = stage(entry['target'], entry['original'], entry['info'].st_mode)
        for entry in prepared:
            checked(entry['item']['path'], entry['item']['preimage_sha256'])
        for entry in prepared:
            checked(entry['item']['path'], entry['item']['preimage_sha256'])
            os.replace(entry['staged'], entry['target'])
            committed.append(entry)
    except BaseException as exc:
        failures = []
        for entry in reversed(committed):
            try:
                checked(entry['item']['path'], digest(entry['item']['content'].encode('utf-8')))
                os.replace(entry['backup'], entry['target'])
            except (OSError, ValueError) as rollback_exc:
                failures.append(f"{entry['item']['path']}: {rollback_exc}")
        if failures:
            raise RuntimeError(f'{exc}; rollback skipped or failed: {"; ".join(failures)}') from exc
        raise
    finally:
        for entry in prepared:
            for key in ('staged', 'backup'):
                if key in entry:
                    entry[key].unlink(missing_ok=True)


def apply_plan(project, plan):
    apply_changes(project, plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.project, args.before, args.after, args.apply), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
