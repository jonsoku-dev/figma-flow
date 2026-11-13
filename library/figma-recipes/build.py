#!/usr/bin/env python3
"""Compile reviewed Design recipes and statically share production property helpers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

LIBRARY = Path(__file__).resolve().parent
ROOT = LIBRARY.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from design_system import compile_design


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(compiler):
    compiler = Path(compiler).resolve()
    package = json.loads((compiler.parent.parent / 'package.json').read_text())
    if package.get('name') != 'typescript' or package.get('version') != '5.9.3' or compiler.name != 'tsc.js':
        raise ValueError('Use the pinned TypeScript 5.9.3 lib/tsc.js')
    runtime = (ROOT / 'figma-bridge/code.js').read_text()
    names = ['metadata', 'info', 'bindOwnedLabelProperty', 'validateDeclaredComponentProperties',
             'markComponentSlot', 'markImportedInstanceSlots', 'bindDeclaredComponentProperties', 'applyDeclaredInstanceProperties']
    starts = list(re.finditer(r'^(?:async )?function ([A-Za-z0-9_]+)\(', runtime, re.M))
    functions = []
    for name in names:
        hits = [i for i, match in enumerate(starts) if match.group(1) == name]
        if len(hits) != 1:
            raise ValueError('Expected one production helper ' + name)
        index = hits[0]
        end = starts[index + 1].start() if index + 1 < len(starts) else len(runtime)
        functions.append(runtime[starts[index].start():end].rstrip())
    fixture = json.loads((ROOT / 'tests/fixtures/declared-component-properties.json').read_text())
    payload = compile_design(fixture)
    helpers = 'const KEY="figmaFlow";\nconst PAYLOAD=' + json.dumps(payload, ensure_ascii=False) + ';\n' + '\n\n'.join(functions) + '\n'
    helpers_path = LIBRARY / 'component-properties.helpers.js'
    helpers_path.write_text(helpers)
    assert all(helpers.count(function) == 1 for function in functions)
    assert 'importDesign(' not in helpers and 'figma.createPage(' not in helpers and '.remove(' not in helpers
    subprocess.run(['node', '--check', str(helpers_path)], check=True)
    rows = []
    ids = ['design-shapes', 'design-grid', 'design-motion', 'design-component-properties']
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        globals = temp / 'globals.d.ts'
        globals.write_text('declare const figma: PluginAPI;\n')
        for recipe in ids:
            source = LIBRARY / (recipe + '.ts')
            output = temp / (recipe + '.js')
            shared = recipe == 'design-component-properties'
            subprocess.run(['node', str(compiler), '--strict', '--target', 'ES2020', '--lib', 'ES2020',
                '--module', 'none', '--noEmitOnError', '--outFile', str(output),
                *(['--allowJs'] if shared else []),
                str(ROOT / 'library/figma-api/plugin-api.d.ts'), str(globals),
                *([str(helpers_path)] if shared else []), str(source)], check=True)
            code = output.read_text()
            row = {'id': recipe, 'source': source.name, 'sourceSha256': digest(source.read_bytes()),
                   'entry': 'bundled/' + recipe + '.js'}
            if recipe == 'design-component-properties':
                row.update(helpers=helpers_path.name, helpersSha256=digest(helpers_path.read_bytes()),
                           productionFunctions=names,
                           productionFunctionSha256={name: digest(function.encode()) for name, function in zip(names, functions)},
                           productionSourceSha256=digest(runtime.encode()))
            assert 'figma.createPage(' not in code
            assert 'node.remove()' in code and 'owned' in code
            target = LIBRARY / row['entry']
            target.parent.mkdir(exist_ok=True)
            target.write_text(code)
            subprocess.run(['node', '--check', str(target)], check=True)
            row['jsSha256'] = digest(target.read_bytes())
            rows.append(row)
    (LIBRARY / 'bundle.json').write_text(json.dumps({'schemaVersion': 1,
        'typescriptVersion': '5.9.3', 'recipes': rows}, indent=2) + '\n')
    print('Compiled four Design recipes with owned-node rollback and no page creation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--typescript', required=True, help='Trusted TypeScript 5.9.3 lib/tsc.js')
    build(parser.parse_args().typescript)
