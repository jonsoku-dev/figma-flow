#!/usr/bin/env python3
"""Create and compile a standalone local Figma developer plugin; never runs it."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from figma_api_inventory import LIBRARY, ROOT, verify_source
from review_graph import project_graph, typescript_projection

TYPESCRIPT = '5.9.3'
EDITORS = ('figma',)
MODES = ('default',)
RECIPES = ROOT / 'library' / 'figma-recipes'
FLAGS = ['--strict', '--target', 'ES2020', '--lib', 'ES2020', '--module', 'none',
         '--skipLibCheck', 'false', '--typeRoots', 'vendor', '--noEmitOnError', '--outFile', 'dist/code.js']
INPUTS = ['vendor/plugin-api.d.ts', 'src/globals.d.ts', 'src/code.ts']


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def safe_path(value):
    path = Path(value).expanduser().absolute()
    if '..' in path.parts or any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError('Project path must not contain symlinks or parent traversal')
    return path


def example(editor, mode):
    if editor != 'figma' or mode != 'default':
        raise ValueError('The standalone SDK starter is limited to Figma Design default mode.')
    guard = "if (figma.editorType !== 'figma' || figma.mode !== 'default') {\n  throw new Error('Open this plugin in Figma Design/default.');\n}\n\n"
    return guard + """// Read-only selection report. Select nodes, then run this plugin again.
const selection = figma.currentPage.selection;
const summary = selection.map(node => `${node.name} (${node.type}, ${node.id})`);
figma.closePlugin(summary.length ? summary.join('; ') : 'No nodes selected on this page.');
"""


def initialize(path, editor, mode=None, plugin_id=None, recipe=None, review_graph=None, selected_ids=None):
    path = safe_path(path)
    if path.exists():
        raise ValueError('Destination already exists; choose a new directory (registered workspaces are never replaced)')
    if not path.parent.is_dir():
        raise ValueError('Destination parent must already exist')
    if editor not in EDITORS:
        raise ValueError('Choose exactly one supported editor')
    mode = mode or 'default'
    if mode not in MODES:
        raise ValueError('The standalone SDK starter supports Figma Design/default mode only.')
    if plugin_id is not None and not re.fullmatch(r'[0-9]+', plugin_id):
        raise ValueError('Supply the numeric ID issued by Figma; this tool cannot issue or authenticate an ID')
    source = verify_source()
    code = example(editor, mode)
    helper = None
    projection = None
    graph_pin = None
    if recipe:
        catalog = json.loads((RECIPES / 'manifest.json').read_text())
        rows = [row for row in catalog['recipes'] if row['id'] == recipe]
        if len(rows) != 1:
            raise ValueError('Unknown or ambiguous recipe')
        row = rows[0]
        if row['editorType'] != editor or row.get('mode', 'default') != mode:
            raise ValueError('Recipe editor/mode differs from the chosen editor/mode')
        entry = Path(row['entry'])
        if (entry.is_absolute() or '..' in entry.parts
                or any(part.is_symlink() for part in [(RECIPES / entry), *(RECIPES / entry).parents])):
            raise ValueError('Unsafe recipe entry')
        code = (RECIPES / entry).read_text()
        if row.get('reviewGraph') is True:
            if review_graph is None:
                raise ValueError('Graph-driven recipes require --review-graph and the intended node selection')
            graph, graph_pin = project_graph(review_graph, selected_ids)
            projection = typescript_projection(graph, graph_pin)
        if row.get('runtimeHelpers'):
            helper_entry = Path(row['runtimeHelpers'])
            if (helper_entry.is_absolute() or '..' in helper_entry.parts
                    or any(part.is_symlink() for part in [(RECIPES / helper_entry), *(RECIPES / helper_entry).parents])):
                raise ValueError('Unsafe recipe helpers')
            helper = (RECIPES / helper_entry).read_text()
    if projection is None and (review_graph is not None or selected_ids):
        raise ValueError('This recipe does not consume a review graph')
    manifest = {'name': 'Local SDK workbench', 'api': '1.0.0', 'main': 'dist/code.js',
                'editorType': [editor], 'documentAccess': 'dynamic-page',
                'networkAccess': {'allowedDomains': ['none']}}
    if recipe and row.get('requiresFileKey'):
        manifest['enablePrivatePluginApi'] = True
    if plugin_id:
        manifest['id'] = plugin_id
    inputs = INPUTS[:-1] + (['vendor/recipe-runtime.js'] if helper is not None else []) + INPUTS[-1:]
    if projection is not None:
        inputs.insert(-1, 'src/review-graph.ts')
    files = {
        'manifest.json' if plugin_id else 'manifest.template.json': encoded(manifest),
        'package.json': encoded({'name': 'local-figma-sdk-project', 'version': '0.0.0', 'private': True,
            'scripts': {'check': 'tsc --noEmit', 'build': 'tsc'}, 'devDependencies': {'typescript': TYPESCRIPT}}),
        'tsconfig.json': encoded({'compilerOptions': {'strict': True, 'target': 'ES2020', 'lib': ['ES2020'],
            'module': 'none', 'allowJs': helper is not None, 'skipLibCheck': False, 'noEmitOnError': True, 'types': [], 'outFile': 'dist/code.js'},
            'files': inputs}),
        'src/code.ts': code,
        'src/globals.d.ts': 'declare const figma: PluginAPI;\n',
        'vendor/source.json': encoded(source),
        'sdk-project.json': encoded({'schemaVersion': 1, 'editor': editor, 'mode': mode, 'typescript': TYPESCRIPT,
                                    'recipe': recipe, 'runtimeHelpers': None if helper is None else {'path': 'vendor/recipe-runtime.js',
                                        'sha256': hashlib.sha256(helper.encode()).hexdigest()}, 'runtimeAcceptance': 'unverified',
                                    **({'reviewGraph': {'graphSha256': graph_pin,
                                        'projectionSha256': hashlib.sha256(projection.encode()).hexdigest()}} if projection else {})}),
        '.gitignore': 'node_modules/\ndist/\n',
        'README.md': """# Local Figma SDK project

Review `src/code.ts` before importing or running. This project does not connect to Figma Flow.
Install once with `npm install --ignore-scripts --no-audit --no-fund`; retain package-lock.json.
Later use `npm ci --offline --ignore-scripts --no-audit --no-fund` with a populated npm cache.
Run `npm run check` and `npm run build` (offline after installation).
No ID? Create a NEW development plugin in Figma, copy its Figma-issued id into
manifest.template.json, and save that as manifest.json. Do not reuse the registered
Figma Flow manifest or overwrite its workspace. Build, then import this manifest via
Figma's development plugin menu in Figma Design.
The ID is supplied by you; this tool cannot verify ownership or platform validity.
Network is denied by default; no permissions or private/proposed API are enabled.
Author any additional permissions/network/modes deliberately using official docs:
https://developers.figma.com/docs/plugins/manifest/
Typechecking proves declaration compatibility only, not editor support or runtime safety.
""",
    }
    if projection is not None:
        files['src/review-graph.ts'] = projection
    if helper is not None:
        files['vendor/recipe-runtime.js'] = helper
    # Exclusive creation prevents accidental replacement of an existing plugin.
    path.mkdir()
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    for name in source['files']:
        shutil.copyfile(LIBRARY / name, path / 'vendor' / name)
    return {'project': str(path), 'manifest': 'manifest.json' if plugin_id else 'manifest.template.json',
            'editor': editor, 'mode': mode, 'runtime': 'not-executed'}


def compile_project(path, build=False, typescript=None):
    path = safe_path(path)
    for name in [*INPUTS, 'sdk-project.json', 'vendor/source.json', 'package.json', 'dist', 'dist/code.js']:
        target = path / name
        if any(part.is_symlink() for part in [target, *target.parents]):
            raise ValueError(f'Symlink not allowed: {name}')
    source = verify_source()
    if json.loads((path / 'vendor/source.json').read_text()) != source:
        raise ValueError('Project typings provenance differs from the pinned inventory source')
    for name, expected in source['files'].items():
        target = path / 'vendor' / name
        if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Pinned typings changed: {name}')
    metadata = json.loads((path / 'sdk-project.json').read_text())
    if metadata['typescript'] != TYPESCRIPT:
        raise ValueError('Unexpected TypeScript version in project')
    inputs = list(INPUTS)
    helper = metadata.get('runtimeHelpers')
    if helper is not None:
        if not isinstance(helper, dict) or helper.get('path') != 'vendor/recipe-runtime.js':
            raise ValueError('Unexpected recipe helper path')
        helper_path = path / helper['path']
        if helper_path.is_symlink() or hashlib.sha256(helper_path.read_bytes()).hexdigest() != helper.get('sha256'):
            raise ValueError('Pinned recipe helpers changed')
        inputs.insert(-1, helper['path'])
    if 'reviewGraph' in metadata:
        projection = safe_path(path / 'src/review-graph.ts').read_bytes()
        if hashlib.sha256(projection).hexdigest() != metadata['reviewGraph']['projectionSha256']:
            raise ValueError('Review graph projection changed. Regenerate it from the canonical graph.')
        inputs.insert(-1, 'src/review-graph.ts')
    compiler = Path(typescript).resolve() if typescript else path / 'node_modules/typescript/lib/tsc.js'
    package = json.loads((compiler.parent.parent / 'package.json').read_text())
    if package.get('name') != 'typescript' or package.get('version') != TYPESCRIPT or compiler.name != 'tsc.js':
        raise ValueError(f'Compiler must be TypeScript {TYPESCRIPT} lib/tsc.js')
    result = subprocess.run(['node', str(compiler), *FLAGS, *(['--allowJs'] if helper is not None else []), *([] if build else ['--noEmit']), *inputs], cwd=path)
    if result.returncode:
        raise ValueError('TypeScript compilation failed')
    return {'project': str(path), 'status': 'built' if build else 'typechecked', 'runtime': 'not-executed'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('path')
    init.add_argument('--editor', choices=EDITORS, required=True)
    init.add_argument('--mode', choices=MODES)
    init.add_argument('--plugin-id', help='ID issued by Figma, never a fabricated ID')
    init.add_argument('--recipe', help='ID in library/figma-recipes/manifest.json')
    init.add_argument('--review-graph', type=Path, help='Canonical Figma Flow product graph')
    init.add_argument('--node', action='append', help='Node to include in the reviewed subgraph (repeatable)')
    for command in ('check', 'build'):
        child = commands.add_parser(command)
        child.add_argument('path')
        child.add_argument('--typescript', help=f'Offline path to trusted TypeScript {TYPESCRIPT} lib/tsc.js')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = initialize(args.path, args.editor, args.mode, args.plugin_id, args.recipe,
                                args.review_graph, args.node)
        else:
            result = compile_project(args.path, args.command == 'build', args.typescript)
        print(encoded(result), end='')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'figma-sdk-project: {error}\n')


if __name__ == '__main__':
    main()
