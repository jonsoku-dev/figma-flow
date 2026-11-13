#!/usr/bin/env python3
"""Create and compile a separate local Widget API project; never run Figma."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import figma_api_inventory as plugin_api
from figma_sdk_project import ROOT, TYPESCRIPT, encoded, safe_path

LIBRARY = ROOT / 'library' / 'figma-widget'
INPUTS = ['vendor/plugin/plugin-api.d.ts', 'vendor/widget/index.d.ts', 'src/globals.d.ts', 'src/code.tsx']
OPTIONS = {'strict': True, 'target': 'ES2020', 'lib': ['ES2020'], 'module': 'none',
           'jsx': 'react', 'jsxFactory': 'figma.widget.h', 'jsxFragmentFactory': 'figma.widget.Fragment',
           'skipLibCheck': False, 'noEmitOnError': True, 'types': [], 'outFile': 'dist/code.js'}
SAMPLE = '''const { widget } = figma;
const { AutoLayout, Text, useSyncedState } = widget;

function Counter() {
  const [count, setCount] = useSyncedState<number>('count', 0);
  return (
    <AutoLayout direction="horizontal" spacing={16} padding={24}
      cornerRadius={12} fill="#FFFFFF" stroke="#D8D8D8"
      onClick={() => setCount(previous => previous + 1)}>
      <Text fontSize={20}>Shared counter</Text>
      <Text fontSize={20}>{count}</Text>
      <Text fontSize={16}>Click to add 1</Text>
    </AutoLayout>
  );
}

widget.register(Counter);
'''


def verify_source():
    source = json.loads((LIBRARY / 'source.json').read_text())
    for name, expected in source['files'].items():
        path = LIBRARY / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Pinned Widget API source changed: {name}')
    return source


def search(query='', limit=30):
    source = verify_source()
    words = query.casefold().split()
    rows = []
    for name in ('index.d.ts', 'widget-api.d.ts'):
        lines = (LIBRARY / name).read_text().splitlines()
        for offset, line in enumerate(lines):
            if all(word in line.casefold() for word in words):
                rows.append({'file': name, 'line': offset + 1, 'text': line,
                             'context': '\n'.join(lines[max(0, offset - 2):offset + 3]),
                             'source_url': f'{source["repository"]}/blob/{source["ref"]}/{name}#L{offset + 1}'})
    return {'source': source, 'evidence': 'Source-text matches only; documentation examples and declarations may both match. Runtime unverified.',
            'total': len(rows), 'rows': rows[:limit] if limit else rows}


def initialize(path, widget_id=None):
    path = safe_path(path)
    if path.exists():
        raise ValueError('Destination already exists; existing plugins and widgets are never replaced')
    if not path.parent.is_dir():
        raise ValueError('Destination parent must already exist')
    if widget_id is not None and not re.fullmatch(r'[0-9]+', widget_id):
        raise ValueError('Supply the numeric widget ID issued by Figma')
    source = verify_source()
    plugin_source = plugin_api.verify_source()
    manifest = {'name': 'Local Widget SDK counter', 'api': '1.0.0', 'widgetApi': '1.0.0',
                'containsWidget': True, 'editorType': ['figma', 'figjam'], 'main': 'dist/code.js',
                'documentAccess': 'dynamic-page', 'networkAccess': {'allowedDomains': ['none']}}
    if widget_id:
        manifest['id'] = widget_id
    files = {
        'manifest.json' if widget_id else 'manifest.template.json': encoded(manifest),
        'package.json': encoded({'name': 'local-figma-widget-project', 'version': '0.0.0', 'private': True,
            'scripts': {'check': 'tsc --noEmit', 'build': 'tsc'}, 'devDependencies': {'typescript': TYPESCRIPT}}),
        'tsconfig.json': encoded({'compilerOptions': OPTIONS, 'files': INPUTS}),
        'src/code.tsx': SAMPLE, 'src/globals.d.ts': 'declare const figma: PluginAPI;\n',
        'vendor/widget/source.json': encoded(source), 'vendor/plugin/source.json': encoded(plugin_source),
        'widget-project.json': encoded({'schemaVersion': 1, 'typescript': TYPESCRIPT, 'runtimeAcceptance': 'unverified'}),
        '.gitignore': 'node_modules/\ndist/\n',
        'README.md': '''# Local Widget API counter

This separate widget uses figma.widget, useSyncedState and AutoLayout in Design and FigJam.
Install TypeScript once: npm install --ignore-scripts --no-audit --no-fund.
Keep package-lock.json; later use npm ci --offline --ignore-scripts with a populated cache.
Run npm run check and npm run build. Review src/code.tsx before inserting the widget.
Create a NEW widget through Figma desktop > Widgets > Development > New widget.
Use its Figma-issued manifest id here. If needed, copy manifest.template.json to
manifest.json and add that id. Import manifest.json through Widgets > Development
> Import widget from manifest, then insert this widget in a Design or FigJam file.
This tool cannot issue IDs or verify their ownership. Do not reuse the Flow plugin ID.
Clicks update this widget's synced count. No network or private APIs are enabled.
Compilation proves typing compatibility only; native and collaborative behavior remain unverified.
Official setup: https://developers.figma.com/docs/widgets/setup-guide/
Manifest: https://developers.figma.com/docs/widgets/widget-manifest/
''',
    }
    path.mkdir()
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    for folder, library, pin in [('widget', LIBRARY, source), ('plugin', plugin_api.LIBRARY, plugin_source)]:
        for name in pin['files']:
            shutil.copyfile(library / name, path / 'vendor' / folder / name)
    return {'project': str(path), 'manifest': 'manifest.json' if widget_id else 'manifest.template.json',
            'editors': ['figma', 'figjam'], 'runtime': 'not-executed'}


def compile_project(path, build=False, typescript=None):
    path = safe_path(path)
    for name in [*INPUTS, 'widget-project.json', 'vendor/widget/source.json', 'vendor/plugin/source.json', 'dist/code.js']:
        target = path / name
        if any(part.is_symlink() for part in [target, *target.parents]):
            raise ValueError(f'Symlink not allowed: {name}')
    for folder, library, pin in [('widget', LIBRARY, verify_source()), ('plugin', plugin_api.LIBRARY, plugin_api.verify_source())]:
        if json.loads((path / 'vendor' / folder / 'source.json').read_text()) != pin:
            raise ValueError(f'Pinned {folder} provenance changed')
        for name, expected in pin['files'].items():
            target = path / 'vendor' / folder / name
            if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError(f'Pinned {folder} source changed: {name}')
    if json.loads((path / 'widget-project.json').read_text()).get('typescript') != TYPESCRIPT:
        raise ValueError('Unexpected TypeScript version')
    compiler = Path(typescript).resolve() if typescript else path / 'node_modules/typescript/lib/tsc.js'
    package = json.loads((compiler.parent.parent / 'package.json').read_text())
    if package.get('name') != 'typescript' or package.get('version') != TYPESCRIPT or compiler.name != 'tsc.js':
        raise ValueError(f'Compiler must be TypeScript {TYPESCRIPT} lib/tsc.js')
    flags = ['--strict', '--target', 'ES2020', '--lib', 'ES2020', '--module', 'none', '--jsx', 'react',
             '--jsxFactory', 'figma.widget.h', '--jsxFragmentFactory', 'figma.widget.Fragment',
             '--skipLibCheck', 'false', '--typeRoots', 'vendor/no-ambient-types', '--noEmitOnError', '--outFile', 'dist/code.js']
    result = subprocess.run(['node', str(compiler), *flags, *([] if build else ['--noEmit']), *INPUTS], cwd=path)
    if result.returncode:
        raise ValueError('Widget TypeScript compilation failed')
    return {'project': str(path), 'status': 'built' if build else 'typechecked', 'runtime': 'not-executed'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('path')
    init.add_argument('--widget-id', help='Numeric widget ID issued by Figma; never a fabricated plugin ID')
    for name in ('check', 'build'):
        command = commands.add_parser(name)
        command.add_argument('path')
        command.add_argument('--typescript', help='Trusted offline TypeScript 5.9.3 lib/tsc.js')
    command = commands.add_parser('search')
    command.add_argument('query', nargs='?', default='')
    command.add_argument('--limit', type=int, default=30)
    commands.add_parser('verify')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = initialize(args.path, args.widget_id)
        elif args.command in ('check', 'build'):
            result = compile_project(args.path, args.command == 'build', args.typescript)
        elif args.command == 'search':
            if args.limit < 0:
                raise ValueError('--limit must be nonnegative')
            result = search(args.query, args.limit)
        else:
            result = {'status': 'ok', 'source': verify_source()}
        print(encoded(result), end='')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'figma-widget-project: {exc}\n')


if __name__ == '__main__':
    main()
