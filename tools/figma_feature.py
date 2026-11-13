#!/usr/bin/env python3
"""Route feature intent to reviewed next steps; never executes a Figma operation."""
import argparse
import json
import re
import shlex

from figma_api_inventory import ROOT, load, search

MEMO = 'skills/figma-flow/references/figma-feature-routes.md'
DOCS = 'https://developers.figma.com/docs/plugins/api/'


def feature(identity, aliases, kind, steps, prerequisites, recipe=None, editor=None):
    return dict(id=identity, aliases=aliases.split('|'), kind=kind, next_steps=steps,
                prerequisites=prerequisites, recipe=recipe, editor=editor)


def sdk(identity, aliases, editor, scope, review_graph=False, workspace_menu=None, requires_file_key=False):
    steps = [
        f'python3 tools/figma_sdk_project.py init NEW_SDK_DIR --editor {editor} --recipe {identity}',
        'npm --prefix NEW_SDK_DIR install --ignore-scripts --no-audit --no-fund',
        'python3 tools/figma_sdk_project.py check NEW_SDK_DIR',
        'python3 tools/figma_sdk_project.py build NEW_SDK_DIR',
    ]
    if review_graph and requires_file_key:
        steps = [
            'python3 tools/design_type_review_graph.py --file-key FILE_KEY --page-id PAGE_ID --out .figma-flow/type-review-graph.json',
            f'python3 tools/figma_sdk_project.py init NEW_SDK_DIR --editor {editor} --recipe {identity} --review-graph .figma-flow/type-review-graph.json',
            *steps[1:],
        ]
    elif review_graph:
        steps[0] += ' --review-graph GRAPH_JSON --node NODE_ID'
    prerequisites = ['Scope: ' + scope,
        'Use a new directory; review src/code.ts before running anything in Figma.',
        'Initial npm installation needs network or cached packages. Typechecking does not prove runtime support.',
        'Create a separate Figma development plugin, copy its issued ID into manifest.template.json and save as manifest.json.',
        'Import the built manifest in the matching editor/mode, run only with authorized scope, and inspect actual results.']
    if requires_file_key:
        prerequisites.insert(1, 'The recipe requires the explicitly selected file key and existing page ID; its generated graph binds both before compilation.')
    if workspace_menu:
        result = feature(identity, aliases, 'flow-recipe', [
            'python3 tools/figma_workspace.py refresh --workspace WORKSPACE',
            f"In Figma Design, open Figma Flow > Examples · add to current page and choose the {identity} example (command flow-recipe:{identity}).",
            'Review the explicit confirmation, add the example to the current page, and inspect the actual result.',
        ], ['Use the existing registered Flow plugin in an authorized Design file.',
            'Scope: ' + scope,
            'Reload the same registered plugin after refresh. The menu adds an isolated FRAME (Motion: SECTION) to the current page, outside signed task/chat/control flows; it does not create pages or execute arbitrary JavaScript.'],
            recipe=identity, editor=editor)
        result['sdk_fallback'] = {'next_steps': steps, 'prerequisites': prerequisites}
        return result
    return feature(identity, aliases, 'sdk-recipe', steps, prerequisites, recipe=identity, editor=editor)


ROUTES = [
    *(sdk(row['id'], '|'.join(row['aliases']), row['editorType'], row['description'], row.get('reviewGraph', False),
          row.get('workspaceMenu'), row.get('requiresFileKey', False))
      for row in json.loads((ROOT / 'library/figma-recipes/manifest.json').read_text())['recipes']),
    feature('web-design', 'editable web design|web to figma|웹 화면 변환|편집 가능한 웹 화면', 'flow',
            ['Measure the rendered browser page with tools/web_design_capture.js.',
             'python3 tools/web_design_source.py --capture CAPTURE_JSON --assets ASSET_INDEX --id GRAPH_ID --title TITLE --out NEW_GRAPH_JSON',
             'python3 tools/native_edit.py web-design --graph NEW_GRAPH_JSON --file-key FILE_KEY --page-id PAGE_ID --out NEW_PLAN_JSON',
             'Prepare NEW_PLAN_JSON as a native-edit task, apply in the registered workspace and compare the native preview and readback.'],
            ['Use an authorized rendered page, local pinned image bytes, and a chosen Design destination. See docs/web-design-capture.md.']),
    feature('graph-review', 'review board|graph review|검토 보드|근거 그래프', 'flow',
            ['python3 tools/native_edit.py graph-review --graph GRAPH_JSON --node NODE_ID --file-key FILE_KEY --page-id PAGE_ID --out NEW_PLAN_JSON',
             'Prepare the reviewed plan as a native-edit task in the registered workspace and inspect a fresh native read.'],
            ['Select authorized graph records and an existing Design page.']),
    feature('motion-timeline', 'motion|timeline|keyframe|모션|타임라인|키프레임', 'official-api',
            ['python3 tools/figma_api_inventory.py search figma.motion',
             'python3 tools/figma_sdk_project.py init NEW_SDK_DIR --editor figma'],
            ['Scaffold is read-only; author and review timeline code before execution or use the native Motion UI.',
             'Motion is beta; verify editor/node support and actual playback/export.']),
    feature('variables', 'variables|variable|tokens|변수|토큰', 'official-api',
            ['python3 tools/figma_api_inventory.py search figma.variables',
             'python3 tools/figma_sdk_project.py init NEW_SDK_DIR --editor figma'],
            ['The scaffold is a read-only selection report: author and review variable code before execution.',
             'Review variable types, collection/mode IDs and actual bindings; team-library permissions/access and REST plan/scopes are separate gates.']),
    feature('layout', 'auto layout|layout guides|layout guide grid|오토 레이아웃|레이아웃 가이드', 'official-api',
            ['python3 tools/figma_api_inventory.py search layoutMode',
             'python3 tools/figma_api_inventory.py search layoutGrids'],
            ['Auto layout GRID and layout guide grids differ; inspect existing node geometry and constraints before editing.']),
    feature('media', 'image|svg|video|export|이미지|비디오|내보내기', 'official-api',
            ['python3 tools/figma_api_inventory.py search createImage',
             'python3 tools/figma_api_inventory.py search exportAsync',
             'python3 tools/figma_sdk_project.py init NEW_SDK_DIR --editor figma'],
            ['Scaffold is read-only; author/review the specific import/export code, or use the native desktop import/export UI.',
             'Use authorized local assets and exact destinations; network assets require deliberate manifest network access.']),
    feature('discover', 'discover|discovery|readback|inspect document|문서 읽기|전체 읽기|디스커버리', 'flow',
            ['python3 tools/graph_sync.py discover --file-key FILE_KEY --page-id PAGE_ID --out NEW_TASK_DIR',
             'python3 tools/figma_control.py run --workspace WORKSPACE --key TASK_KEY --file-key FILE_KEY --page-id PAGE_ID --expected-revision TASK_REVISION --operation read'],
            ['Use exact file/page IDs and a new output directory.',
             'Discovery prepares a task; import/run its plugin or use a compatible running Flow workspace.',
             'Control run additionally requires the signed task key, workspace and expected revision.']),
    feature('native-edit', 'native edit|bounded edit|네이티브 수정|제한 수정', 'flow',
            ['python3 tools/native_edit.py prepare --plan PLAN_JSON --out NEW_TASK_DIR'],
            ['Prepare an explicit plan pinned to current observations; review it before running the generated plugin.']),
    feature('components', 'component properties|component|components|variant|variants|컴포넌트|배리언트|컴포넌트 소스|컴포넌트 속성 만들기', 'flow',
            ['python3 tools/design_system.py --input SOURCE_JSON --out NEW_PREVIEW_DIR',
             'python3 tools/figma_bridge.py --input SOURCE_JSON --reviewed-sha256 REVIEWED_SHA256 --out NEW_PLUGIN_DIR'],
            ['Source authoring: use your own declared component/property payload under docs/component-property-authoring.md; the design-component-properties route is a bundled demonstration.',
             'Review the source and preview, provide its real SHA-256, then run the plugin in authorized Design context.',
             'Compilation does not prove native property values; read definitions/references and instance values afterward.']),
    feature('design-context', 'design context|design to code|디자인 문맥|디자인 투 코드|구현 문맥', 'flow',
            ['python3 tools/graph_sync.py discover --file-key FILE_KEY --page-id PAGE_ID --out NEW_TASK_DIR'],
            ['Run the scoped discovery with the registered Flow plugin and inspect actual readback plus the native canvas.',
             'Use exact file/page/node IDs; readback is implementation context, not generated-code acceptance.']),
    feature('code-connect', 'code connect|코드 커넥트|컴포넌트 매핑', 'official-api',
            ['Configure the local Code Connect CLI using https://developers.figma.com/docs/code-connect/ and review local mapping files.'],
            ['Exact component URL, repository component and supported framework are required.',
             'Publishing requires an explicitly configured credential, eligible plan/seat and user authority.']),
    feature('make', 'make|코드 가져오기|실행 앱', 'interactive',
            ['Open the target Make project in the native Figma product UI and review its supported code/input workflow.'],
            ['Confirm product access, destination and credit conditions; code layers are not editable Design layers.',
             'No local Make execution recipe is provided; generation or publication requires user authority.']),
    feature('weave', 'weave|위브|generation workflow', 'interactive',
            ['Open the authorized Weave project in its native product UI and review workflow inputs and run cost.'],
            ['Requires Weave product access and credits; paid runs require user authority.',
             'No local Weave execution recipe is provided.']),
    feature('sites', 'sites|website publish|사이트|웹사이트 발행', 'interactive',
            ['Open the target Figma Sites file and use preview/settings/publish in its product UI.'],
            ['Confirm edit access, plan and explicit publication authority; no generic Sites Plugin API route is asserted.']),
    feature('team-library', 'team library|library import|팀 라이브러리|라이브러리 가져오기', 'official-api',
            ['python3 tools/figma_api_inventory.py search figma.teamLibrary',
             'python3 tools/figma_api_inventory.py search importComponentByKeyAsync'],
            ['Verify published keys and account access; users must enable the library in the UI.',
             'Library variable discovery needs the teamlibrary manifest permission; this router grants none.']),
    feature('library-publish', 'publish library|library publish|라이브러리 발행|라이브러리 게시', 'interactive',
            ['Open the source library in Figma and review the Publish changes dialog.'],
            ['Requires library access and explicit publication authority; local components are not already published.']),
    feature('branch', 'branch|merge|브랜치|병합', 'interactive',
            ['Open the exact branch URL and use the product review/merge UI.'],
            ['Distinguish main and branch keys, check plan/access and obtain authority for merge.']),
    feature('comments', 'comment|comments|댓글|답글', 'interactive',
            ['Use the native Figma Comments UI for the exact file/node.',
             'python3 tools/figma_rest_inventory.py template getComments',
             'python3 tools/figma_rest_inventory.py curl getComments --path file_key=FILE_KEY'],
            ['REST requires a configured credential, minimum endpoint scopes and file access; sending a comment requires explicit authority.']),
    feature('widget', 'widget|위젯', 'widget-project',
            ['python3 tools/figma_widget_project.py init NEW_WIDGET_DIR',
             'npm --prefix NEW_WIDGET_DIR install --ignore-scripts --no-audit --no-fund',
             'python3 tools/figma_widget_project.py check NEW_WIDGET_DIR',
             'python3 tools/figma_widget_project.py build NEW_WIDGET_DIR'],
            ['Use a new directory and review src/code.tsx before inserting anything in Figma.',
             'The scaffold is a Widget API project with a separate manifest, not a Plugin project; obtain a Widget ID from Figma and use it in manifest.json.',
             'Compilation checks pinned Widget and Plugin declarations; it does not verify insertion, collaboration, or runtime behavior.',
             'Import and insert only in an authorized Figma Design document. See docs/figma-widget.md.']),
    feature('rest', 'rest|webhook|version history|scim|웹훅|버전 기록|조직 관리', 'official-api',
            ['python3 tools/figma_rest_inventory.py search QUERY',
             'python3 tools/figma_rest_inventory.py template OPERATION_ID',
             'python3 tools/figma_rest_inventory.py curl OPERATION_ID --help'],
            ['Search the pinned catalog, then supply the real operation ID and required path/query/body inputs when exporting a request. The curl command only prints a reviewed command; it does not make a request.',
             'Explicitly configure the exact official REST endpoint and credential; check minimum scopes, file/admin access, plan and rate limits. REST is not generic canvas node CRUD.']),
]


def matches(query, alias):
    if re.search(r'[가-힣]', alias):
        return alias in query
    return re.search(r'(?<![a-z0-9_])' + re.escape(alias) + r'(?![a-z0-9_])', query) is not None


def route(query, catalog=None):
    query = ' '.join(query.casefold().split())
    if not query:
        raise ValueError('Feature query must not be empty')
    base = {'schema': 'figma-flow-feature-route-v1', 'query': query, 'execution': 'not-executed',
            'reference': MEMO, 'runtime_acceptance': 'unverified'}
    exact = [row for row in ROUTES if query == row['id'] or query in row['aliases']]
    candidates = exact or [row for row in ROUTES if any(matches(query, alias) for alias in row['aliases'])]
    if candidates:
        return {**base, 'status': 'routed' if len(candidates) == 1 else 'ambiguous',
                'routes': candidates, 'next_action': 'Review prerequisites and substitute real values in next_steps.' if len(candidates) == 1
                else 'Choose one route ID and rerun; no operation has been executed.'}
    result = search(catalog if catalog is not None else load(), query, limit=0)
    result['rows'].sort(key=lambda row: query not in [row['name'].casefold(),
        (row['owner'] + '.' + row['name']).casefold(), *[path.casefold() for path in row.get('routes', [])]])
    result['rows'] = [{key: row[key] for key in ('owner', 'name', 'signature', 'routes', 'documented_editors', 'required_permissions', 'source_url') if key in row}
                      for row in result['rows'] if not row.get('restricted_access')][:10]
    result['declarations'] = [{key: row[key] for key in ('name', 'kind', 'line') if key in row}
                              for row in result['declarations'][:10]]
    # Do not present undocumented/private declaration-only hits as an executable route.
    found = bool(result['rows'] or result['declarations'])
    return {**base, 'status': 'api-catalog' if found else 'unknown', 'routes': [],
            'catalog': result, 'next_steps': [f'python3 tools/figma_api_inventory.py search {shlex.quote(query)}'],
            'prerequisites': ['Catalog presence proves declarations only. Review editor/mode/permissions and source docs before writing a plugin.'],
            'official_plugin_api': DOCS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('route')
    command.add_argument('query', nargs='+')
    commands.add_parser('list')
    args = parser.parse_args(argv)
    try:
        result = route(' '.join(args.query)) if args.command == 'route' else {'routes': ROUTES, 'execution': 'not-executed', 'reference': MEMO}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'figma-feature: {error}\n')


if __name__ == '__main__':
    main()
