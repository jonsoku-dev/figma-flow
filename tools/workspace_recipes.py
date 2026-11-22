"""Source-pinned Design examples for Codex tasks and legacy menu generation."""
from report_appearance import report_css
import argparse
import hashlib
import html
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'library' / 'figma-recipes'
if str(LIBRARY) not in sys.path:
    sys.path.insert(0, str(LIBRARY))
import recipe_design_graph as design_graph

def design_recipes(library=None):
    entries = json.loads(((library or LIBRARY) / 'manifest.json').read_text())['recipes']
    if any(row.get('editorType') != 'figma' or row.get('mode', 'default') != 'default'
           or row.get('designGraph') != 'design-examples.graph.json' for row in entries):
        raise ValueError('Recipe editor/mode differs from Design/default or visual values graph source is not canonical. See CONSTITUTION.md.')
    return entries


def registered_actions():
    entries = [row for row in design_recipes() if 'workspaceMenu' in row]
    if any(row.get('editorType') != 'figma' or row.get('mode') != 'default' or row.get('reviewGraph')
           or not re.fullmatch(r'[a-z][a-z0-9-]+', row['id']) or not row['workspaceMenu'] for row in entries):
        raise ValueError('Invalid static Design menu declaration')
    actions = {row['id']: row['workspaceMenu'] for row in entries}
    if len(actions) != len(entries):
        raise ValueError('Duplicate Design menu declaration')
    return actions


ACTIONS = registered_actions()
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
    graph_pin = bundle.get('designGraph')
    graph_source = graph_pin.get('source') if isinstance(graph_pin, dict) else None
    if graph_source != 'design-examples.graph.json':
        raise ValueError('Recipe bundle has no canonical visual values graph')
    graph_path = LIBRARY / graph_source
    if graph_path.is_symlink():
        raise ValueError('Recipe visual values graph cannot be a symlink')
    graph_raw = graph_path.read_bytes()
    graph_data = design_graph.parse_graph(graph_raw)
    graph = design_graph.validate_graph(graph_data)
    projection = design_graph.typescript_projection(graph_data)
    payload = design_graph.payload_projection(graph_data)
    if (graph_pin.get('sourceSha256') != hashlib.sha256(graph_raw).hexdigest()
            or graph_pin.get('projectionSha256') != hashlib.sha256(projection.encode()).hexdigest()
            or graph_pin.get('componentPayloadSource') != 'tests/fixtures/declared-component-properties.json'
            or graph_pin.get('componentPayloadSha256') != hashlib.sha256(payload.encode()).hexdigest()
            or set(graph['visuals']) != {row['id'] for row in design_recipes()}):
        raise ValueError('Recipe bundle does not match the canonical visual values graph')
    rows = bundle['recipes']
    if {row['id'] for row in rows} != set(ACTIONS) or len(rows) != len(ACTIONS):
        raise ValueError('Recipe bundle differs from the static Design allowlist')
    result = {}
    for row in rows:
        key = row['id']
        visual_projection = design_graph.typescript_projection(graph_data, {key})
        if row.get('visualProjectionSha256') != hashlib.sha256(visual_projection.encode()).hexdigest():
            raise ValueError('Recipe bundle visual values differ from the canonical graph')
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
    sdk_rows = bundle.get('sdkGraphRecipes')
    if not isinstance(sdk_rows, list) or {row.get('id') for row in sdk_rows} != set(graph['visuals']) - set(ACTIONS):
        raise ValueError('Graph-driven SDK recipe set differs from the canonical visual graph')
    for row in sdk_rows:
        visual_projection = design_graph.typescript_projection(graph_data, {row['id']})
        if row.get('visualProjectionSha256') != hashlib.sha256(visual_projection.encode()).hexdigest():
            raise ValueError('SDK recipe visual values differ from the canonical graph')
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


def prepare_relay_example(options, output, plugin_id):
    """Wrap a fixed, hash-checked example in the existing signed native-edit lifecycle."""
    if set(options) != {'--recipe', '--file-key', '--page-id'}:
        raise ValueError('Example preparation requires exactly --recipe, --file-key and --page-id')
    key, file_key, page_id = (options[n] for n in ('--recipe', '--file-key', '--page-id'))
    if not re.fullmatch(r'[A-Za-z0-9]{1,128}', file_key) or not re.fullmatch(r'[0-9]+:[0-9]+', page_id):
        raise ValueError('A real Design file key and page ID are required')
    source = bundled_actions().get(key)
    if source is None:
        raise ValueError('Unknown bundled example')
    entry = 'main().catch((error) => figma.closePlugin(String(error)));'
    if not source.rstrip().endswith(entry):
        raise ValueError('Unrecognized pinned example entry')
    plan = {'schema':'figma-flow-example-plan-v1','file_key':file_key,'page_id':page_id,'recipe':key,
            'source_sha256':hashlib.sha256(source.encode()).hexdigest()}
    plan['pin'] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    model = {'session': plan['pin'], 'mode':'example', 'recipe_receipt':{'recipe':key, 'pin':plan['pin']}}
    # Existing SDK examples close their standalone plugin after success. Here
    # the workspace owns the lifetime, and main() must finish before readback.
    runner = ('async function runPinnedExample(host) {\n'
              'const figma = new Proxy({}, {get(_, key) { if (key === "closePlugin") return () => {}; '
              'const value = host[key]; return typeof value === "function" ? value.bind(host) : value; }});\n'
              + source.rstrip().removesuffix(entry) + '\nawait main();\n}\n')
    code = ('const RECIPE_PLAN = ' + json.dumps(plan) + ';\nconst RECIPE_SESSION = ' + json.dumps(plan['pin']) +
            ';\n' + runner + (ROOT/'figma-bridge/relay_recipe.js').read_text())
    manifest = {'name':'Flow scoped example','id':plugin_id,'api':'1.0.0','main':'code.js','ui':'ui.html',
                'editorType':['figma'],'documentAccess':'dynamic-page','networkAccess':{'allowedDomains':['none']}}
    output.mkdir()
    (output/'code.js').write_text(code)
    (output/'ui.html').write_text('<script id="graph-panel-config" type="application/json">'+json.dumps(model)+'</script>')
    (output/'manifest.json').write_text(json.dumps(manifest))
    (output/'native-edit-plan.json').write_text(json.dumps(plan))
    return output


def confirmation(key, title):
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Figma Flow example</title>
<style>''' + report_css("recipeConfirmation") + '''</style>
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
  figma.showUI(confirmations[key], /* flow-window recipe */ {width: 460, height: 320, themeColors: true});
  figma.ui.onmessage = message => {
    if (used || !message || typeof message !== 'object') return;
    if (message.type === 'workspace-recipe-cancel') {used = true; figma.closePlugin(); return;}
    if (message.type !== 'workspace-recipe-run' || message.recipe !== key) return;
    used = true;
    if (figma.editorType !== 'figma' || figma.mode !== 'default') {figma.closePlugin('Editor context changed.'); return;}
    const file = figma.fileKey, pageId = figma.currentPage && figma.currentPage.id;
    const run = allowed => {
      if (!allowed || figma.fileKey !== file || (figma.currentPage && figma.currentPage.id) !== pageId ||
          figma.editorType !== 'figma' || figma.mode !== 'default') {
        figma.closePlugin('Open Figma Flow workspace to review the current file and authoring settings.');
        return;
      }
      try {actions[key]();} catch (error) {figma.closePlugin(String(error));}
    };
    if (typeof workspaceProfileAdmit === 'function') {
      return workspaceProfileAdmit('workspace-recipe-run').then(run, () => run(false));
    }
    run(true);
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
