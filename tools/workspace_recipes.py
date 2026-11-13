"""Static, source-pinned Design examples for the native plugin menu only."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'library' / 'figma-recipes'
ACTIONS = {
    'design-shapes': 'Boolean operations + alpha mask',
    'design-grid': 'Auto layout grid',
    'design-motion': 'Smart Animate prototype',
    'design-component-properties': 'Component properties and instance swap',
}
PREFIX = 'flow-recipe:'
def helper_sources(source, names):
    starts = list(re.finditer(r'^(?:async )?function ([A-Za-z0-9_]+)\(', source, re.M))
    result = {}
    for index, match in enumerate(starts):
        name = match.group(1)
        if name in names:
            if name in result:
                raise ValueError('Duplicate production helper')
            end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
            result[name] = source[match.start():end].rstrip()
    if set(result) != set(names):
        raise ValueError('Missing production helper')
    return result


def menu():
    return [{'name': 'Figma Flow workspace', 'command': 'workspace-home'},
            {'name': 'Examples · add to current page', 'menu': [
                {'name': title, 'command': PREFIX + key} for key, title in ACTIONS.items()]}]


def bundled_actions():
    bundle = json.loads((LIBRARY / 'bundle.json').read_text())
    if bundle.get('schemaVersion') != 1 or bundle.get('typescriptVersion') != '5.9.3':
        raise ValueError('Recipe bundle must use pinned TypeScript 5.9.3')
    rows = bundle['recipes']
    if {row['id'] for row in rows} != set(ACTIONS) or len(rows) != len(ACTIONS):
        raise ValueError('Recipe bundle differs from the static Design allowlist')
    result = {}
    for row in rows:
        key = row['id']
        if row['source'] != key + '.ts' or row['entry'] != 'bundled/' + key + '.js':
            raise ValueError('Recipe bundle entry differs from the static path')
        pins = [('source', 'sourceSha256'), ('entry', 'jsSha256')]
        if key == 'design-component-properties':
            if row.get('helpers') != 'component-properties.helpers.js':
                raise ValueError('Component recipe requires reviewed production helpers')
            pins.append(('helpers', 'helpersSha256'))
        elif 'helpers' in row:
            raise ValueError('Unexpected helpers for bundled Design action')
        for field, sha_field in pins:
            path = LIBRARY / row[field]
            if any(parent.is_symlink() for parent in [path, *path.parents]):
                raise ValueError('Recipe bundle cannot contain symlinks')
            if hashlib.sha256(path.read_bytes()).hexdigest() != row[sha_field]:
                raise ValueError('Recipe source or compiled bundle changed; rebuild and review it')
        result[key] = (LIBRARY / row['entry']).read_text()
    return result


def verify_production_helpers():
    """Explicit build/CI drift check; ordinary workspace publication uses approved pins."""
    bundled_actions()
    rows = json.loads((LIBRARY / 'bundle.json').read_text())['recipes']
    row = next(row for row in rows if row['id'] == 'design-component-properties')
    names = row.get('productionFunctions')
    if (not isinstance(names, list) or not names or len(names) != len(set(names))
            or any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in names)):
        raise ValueError('Invalid production helper dependency list')
    production = ROOT / 'figma-bridge' / 'code.js'
    if production.is_symlink() or helper_sources(production.read_text(), names) != helper_sources((LIBRARY / row['helpers']).read_text(), names):
        raise ValueError('Required production helpers changed; rebuild and review the recipe bundle')
    return {'status': 'verified', 'productionFunctions': names}


def confirmation(key, title):
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Figma Flow example</title>
<style>body{font:14px system-ui;padding:20px;color:var(--figma-color-text);background:var(--figma-color-bg)}button{font:inherit;padding:10px;margin:8px 8px 0 0}</style>
<h1 style="font-size:20px">''' + html.escape(title) + '''</h1>
<p>Add this example in a new named container on the current Design page. Existing nodes are preserved. The new container becomes selected.</p>
<p>This is a bundled example, separate from your prepared Codex tasks. No chat or local control service is started.</p>
<button id="create">Add example to current page</button><button id="cancel">Cancel</button>
<script>const recipe=''' + json.dumps(key) + ''';
document.getElementById('create').onclick=()=>{document.getElementById('create').disabled=true;parent.postMessage({pluginMessage:{type:'workspace-recipe-run',recipe}},'*');};
document.getElementById('cancel').onclick=()=>parent.postMessage({pluginMessage:{type:'workspace-recipe-cancel'}},'*');
</script></html>'''


def dispatch_source():
    functions = []
    for key, source in bundled_actions().items():
        functions.append(json.dumps(key) + ': function(){\n' + source + '\n}')
    confirmations = {key: confirmation(key, title) for key, title in ACTIONS.items()}
    return '''// Bundled examples never enter the signed task, chat or control dispatch.
function workspaceRecipeDispatch() {
  const prefix = ''' + json.dumps(PREFIX) + ''';
  if (typeof figma.command !== 'string' || !figma.command.startsWith(prefix)) return false;
  const key = figma.command.slice(prefix.length);
  const actions = {''' + ',\n'.join(functions) + '''};
  const confirmations = ''' + json.dumps(confirmations) + ''';
  if (!Object.prototype.hasOwnProperty.call(actions, key) || figma.editorType !== 'figma' || figma.mode !== 'default') {
    figma.closePlugin('This bundled example requires Figma Design in default mode.');
    return true;
  }
  let used = false;
  figma.showUI(confirmations[key], {width: 460, height: 320, themeColors: true});
  figma.ui.onmessage = message => {
    if (used || !message || typeof message !== 'object') return;
    if (message.type === 'workspace-recipe-cancel') {used = true; figma.closePlugin(); return;}
    if (message.type !== 'workspace-recipe-run' || message.recipe !== key) return;
    used = true;
    if (figma.editorType !== 'figma' || figma.mode !== 'default') {figma.closePlugin('Editor context changed.'); return;}
    try {actions[key]();} catch (error) {figma.closePlugin(String(error));}
  };
  return true;
}
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify-helpers'])
    parser.parse_args()
    try:
        print(json.dumps(verify_production_helpers(), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'workspace-recipes: {error}\n')
