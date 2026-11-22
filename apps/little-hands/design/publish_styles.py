"""Render the app's authored selector graph with its shared design tokens."""
import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile

DESIGN = Path(__file__).resolve().parent
STYLESHEET = DESIGN.parent / 'static/littlehands/app.css'
REFERENCE = re.compile(r'\{\{([\w.-]+)\}\}')


def render_styles(design=DESIGN):
    graph = json.loads((design / 'stylesheet.json').read_bytes())
    tokens = json.loads((design / 'tokens.json').read_bytes())
    if graph['schema'] != 'little-hands-stylesheet-v1':
        raise ValueError('Unknown stylesheet graph schema')

    def resolve(text):
        def substitute(match):
            value = tokens
            for field in match[1].split('.'):
                value = value[int(field)] if isinstance(value, list) else value[field]
            if type(value) not in (str, float, int):
                raise ValueError('Expected a scalar CSS token: ' + match[1])
            return str(value)
        return REFERENCE.sub(substitute, text)

    def rule(node):
        if 'media' in node:
            return '@media' + resolve(node['media']) + '{' + ''.join(map(rule, node['rules'])) + '}'
        if 'comment' in node:
            return '/*' + node['comment'] + '*/'
        declarations = ';'.join(name + ':' + resolve(value) for name, value in node['declarations'].items())
        return node['selector'] + '{' + declarations + '}'

    return '\n'.join(''.join(map(rule, group)) for group in graph['groups']) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    tokens = json.loads((DESIGN / 'tokens.json').read_bytes())
    theme = escape(tokens['colors']['paper'], quote=True)
    projections = {
        STYLESHEET: render_styles(),
        DESIGN.parent / 'templates/includes/theme_color.html': f'<meta name="theme-color" content="{theme}">',
    }
    for path, text in projections.items():
        data = text.encode('utf-8')
        if path.is_file() and path.read_bytes() == data:
            continue
        if not args.write:
            parser.exit(1, f'{path.name} differs from its selector graph or design tokens.\n')
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
            temp = Path(out.name)
        try:
            temp.write_bytes(data)
            temp.chmod(0o644)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
