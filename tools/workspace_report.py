#!/usr/bin/env python3
"""Build a read-only local evidence report for a signed Figma Flow workspace."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import figma_workspace as workspace

HISTORY_SCHEMA = 'figma-flow-viewer-result-v1'
HISTORY_STATUSES = {'requested', 'running', 'finished', 'failed', 'readback', 'verified', 'baseline'}


def validate_history_export(value, file_key, page_id):
    if (not isinstance(value, dict) or value.get('schema') != HISTORY_SCHEMA
            or value.get('operation') != 'viewer-history' or value.get('scope') != 'file'
            or value.get('source') != 'figma-clientStorage' or value.get('fileKey') != file_key
            or value.get('pageId') != page_id or not isinstance(value.get('available'), bool)
            or not isinstance(value.get('history'), list) or len(value['history']) > 80):
        raise ValueError('History export must be the viewer-history result for this exact file and page')
    cleaned = []
    for row in value['history']:
        if (not isinstance(row, dict) or not isinstance(row.get('taskKey'), str) or len(row['taskKey']) > 200
                or not isinstance(row.get('revision'), str) or not re.fullmatch(r'[a-f0-9]{64}', row['revision'])
                or not isinstance(row.get('operation'), str) or len(row['operation']) > 80
                or not isinstance(row.get('status'), str) or row['status'] not in HISTORY_STATUSES):
            continue
        event = {key: row[key] for key in ('taskKey', 'revision', 'operation', 'status')}
        if isinstance(row.get('time'), str) and len(row['time']) <= 40:
            event['time'] = row['time']
        if isinstance(row.get('executionId'), str) and len(row['executionId']) <= 120:
            event['executionId'] = row['executionId']
        if row.get('carousel') is not None:
            carousel = row['carousel']
            if (isinstance(carousel, dict) and carousel.get('schema') == 'figma-flow-carousel-summary-v1'
                    and carousel.get('status') in {'current', 'changed'}
                    and isinstance(carousel.get('file_key'), str) and isinstance(carousel.get('page_id'), str)
                    and isinstance(carousel.get('flow_start_node_id'), str)
                    and isinstance(carousel.get('initial_state'), str)):
                event['carousel'] = {key: carousel[key] for key in ('schema', 'status', 'file_key', 'page_id',
                    'flow_start_node_id', 'initial_state', 'graph_id', 'graph_sha256', 'frame_key') if key in carousel}
        cleaned.append(event)
    return {'scope': 'file-scoped', 'available': value['available'], 'events': cleaned,
        'locale': value.get('locale') if isinstance(value.get('locale'), str) else None}


def _node_projections(payload):
    """Use the same pure JS projections and sanitizer as the panel source."""
    import shutil
    if not shutil.which('node'):
        raise ValueError('Node.js is required for the repository panel projections and audit sanitizer')
    script = r"""
const fs = require('fs'), {createRequire} = require('module');
const repoRequire = createRequire(process.cwd() + '/package.json');
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const workspaceCopy = JSON.parse(fs.readFileSync('./figma-bridge/locales/workspace.json', 'utf8'));
  const translate = (key, params = {}) => workspaceCopy['workspace.' + key].ko.replace(/\{(\w+)\}/g,
    (literal, name) => Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : literal);
  const [{workspaceActivity}, {selectRecommendation}, {assetInventory}, {dependencyView, dependencyFreshness}] = await Promise.all([
    import('./panel-ui/src/WorkspaceActivity.mjs'), import('./panel-ui/src/workspaceRecommendation.mjs'),
    import('./panel-ui/src/assetInventory.mjs'), import('./panel-ui/src/dependencyView.mjs')]);
  const auditLog = repoRequire('./figma-bridge/audit_log.js');
  const projectTasks = input.project ? input.tasks.filter(task => task.project === input.project) : input.tasks;
  const projectEvents = input.project ? input.events.filter(event => input.taskProjects[event.taskKey] === input.project) : input.events;
  const activity = workspaceActivity(projectTasks, projectEvents);
  const scoped = projectTasks.filter(task => !input.kind || task.kind === input.kind);
  const recommendation = selectRecommendation({fileKey:input.fileKey, tasks:input.tasks, history:input.events}, scoped);
  const view = dependencyView(input.tasks, input.taskKey, translate);
  const labels = dependencyFreshness(input.tasks, input.retired).labels.filter(row => row.task_key === input.taskKey || row.dependency === input.taskKey);
  const inventory = assetInventory(input.assetRows, {status:input.assetStatus, kind:input.assetKind, query:input.assetQuery});
  const taskByKey = new Map(input.tasks.map(task => [task.key, task]));
  const deepLinks = [];
  for (const event of input.events) {
    const task = taskByKey.get(event.taskKey), carousel = event.carousel;
    if (!task || !carousel || task.kind !== 'native-edit' || task.revision !== event.revision || carousel.status !== 'current'
      || task.fileKey !== input.fileKey || carousel.file_key !== input.fileKey || task.pageId !== input.pageId || carousel.page_id !== input.pageId
      || !/^[A-Za-z0-9_-]{1,128}$/.test(input.fileKey) || !/^\d+(?:[:-]\d+)$/.test(carousel.flow_start_node_id || '')) continue;
    const page = input.pageId.replaceAll(':','-'), node = carousel.flow_start_node_id.replaceAll(':','-');
    deepLinks.push({taskKey:task.key, executionId:event.executionId || null,
      url:`https://www.figma.com/proto/${input.fileKey}/SaaS?node-id=${node}&starting-point-node-id=${node}&page-id=${page}&scaling=scale-down`,
      source:'file-scoped clientStorage carousel readback', liveTargetVerification:'not-performed-by-local-report'});
  }
  const auditInput = {...input.auditInput, dependency_freshness:labels.map(row => ({
    label:`${row.dependency} ${row.task_key} ${row.pinned_revision}`, freshness:row.state}))};
  const rendered = auditLog.renderAuditExport(auditInput);
  process.stdout.write(JSON.stringify({activity, recommendation:recommendation && {taskKey:recommendation.task.key,
    revision:recommendation.task.revision, title:recommendation.task.title, inspect:recommendation.inspect,
    action:recommendation.inspect?'inspect-latest-result':'open-next-task'},
    assets:inventory, relatedTasks:{view,freshness:labels}, deepLinks,
    diagnosticExport:{schema:rendered.schema,json:rendered.json,text:rendered.text}}));
})().catch(error => {console.error(error); process.exit(1)});
"""
    completed = subprocess.run(['node', '-e', script], input=json.dumps(payload), text=True,
        capture_output=True, check=True, cwd=workspace.ROOT)
    return json.loads(completed.stdout)


def _embedded_json(source, symbol):
    match = re.search(r'\b(?:const|let|var)\s+' + re.escape(symbol) + r'\s*=\s*', source)
    if not match:
        return None
    value, _ = json.JSONDecoder().raw_decode(source[match.end():])
    return value


def _change_manifest(task, bundle):
    """Read apply identities only from the hash-verified generated plugin source."""
    source = workspace.regular(bundle / 'code.js', private=True, limit=workspace.MAX_BYTES).read_text(encoding='utf-8')
    if task['kind'] == 'sync':
        manifest = _embedded_json(source, 'GRAPH_SELECTION_MANIFEST')
        plan = _embedded_json(source, 'GRAPH_SYNC_PLAN')
        if (not isinstance(manifest, dict) or manifest.get('schema') != 'figma-flow-selection-v2'
                or not re.fullmatch(r'[a-f0-9]{64}', str(manifest.get('plan_sha256', '')))
                or not isinstance(manifest.get('changes'), list)):
            return {'available': False, 'reason': 'No pinned protocol-2 selection manifest is embedded in this sync bundle'}
        fields = ('identity', 'group', 'kind', 'name', 'component_id', 'field', 'token_keys', 'root', 'targets', 'before', 'after')
        changes = [{key: row[key] for key in fields if key in row} for row in manifest['changes']
            if isinstance(row, dict) and isinstance(row.get('identity'), str)]
        migration = isinstance(plan, dict) and (any(isinstance(token, dict) and token.get('create') for token in plan.get('tokens', []))
            or bool(plan.get('repair_bindings')))
        return {'available': True, 'schema': manifest['schema'], 'protocol': 2,
            'plan_sha256': manifest['plan_sha256'], 'changes': changes,
            'selected_ids': [row['identity'] for row in changes],
            'partialApplyAvailable': not migration and 0 < len(changes) <= 500,
            'reason': 'migration-requires-full-apply' if migration else 'selection-count-limit' if len(changes) > 500 else None}
    if task['kind'] == 'native-edit':
        plan = _embedded_json(source, 'NATIVE_EDIT_PLAN')
        plan_sha = _embedded_json(source, 'NATIVE_EDIT_SHA256')
        if not isinstance(plan, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(plan_sha or '')):
            return {'available': False, 'reason': 'No pinned native-edit plan is embedded in this task bundle'}
        rows = plan.get('edits')
        if not isinstance(rows, list) and isinstance(plan.get('specifications'), dict):
            rows = plan['specifications'].get('targets', [])
        if not isinstance(rows, list) and isinstance(plan.get('variableedit'), dict):
            rows = [plan['variableedit']]
        if not isinstance(rows, list):
            rows = []
        changes = []
        for index, edit in enumerate(rows):
            if not isinstance(edit, dict):
                continue
            target = edit.get('node_id') or edit.get('variable_id')
            field = edit.get('field') or edit.get('mode_id') or edit.get('property') or 'value'
            changes.append({'identity': f'{target}.{field}' if isinstance(target, str) else f'edit#{index + 1}',
                'group': edit.get('group') or edit.get('group_id'), 'kind': 'native-edit', 'field': field,
                'targets': [target] if isinstance(target, str) else [],
                'before': edit.get('before'), 'after': edit.get('after')})
        return {'available': True, 'schema': 'figma-flow-native-edit-plan-v1', 'protocol': None,
            'plan_sha256': plan_sha, 'changes': changes, 'selected_ids': [], 'partialApplyAvailable': False,
            'reason': 'native-edit-uses-full-plan-apply; protocol-2-partial-selection-is-not-supported'}
    return {'available': False, 'reason': 'Selection manifests are available only for sync and native-edit tasks'}


def build_report(workspace_path, file_key, page_id, task_key, history_path=None, *, project=None, kind=None,
        asset_status=None, asset_kind=None, asset_query=''):
    root = workspace.private_dir(workspace_path)
    base = workspace.activity(root, file_key, page_id)
    with workspace.locked(root):
        catalogue = workspace.current(root, repair=False)
        tasks = catalogue['tasks']
        selected = next((row for row in tasks if row['key'] == task_key), None)
        if not selected:
            raise ValueError('Unknown current task key')
        if selected.get('fileKey') not in (None, file_key) or selected.get('pageId') not in (None, page_id):
            raise ValueError('Task does not belong to the requested exact file/page scope')
        archived = workspace.public_task_metadata(selected)
        current_bundle = None
        try:
            current_bundle = workspace.task_artifacts(root, selected)
            bundle_info = {'status': 'available', 'path': str(current_bundle.relative_to(root)),
                'files': {path.name: workspace.digest(path.read_bytes()) for path in sorted(current_bundle.iterdir()) if path.is_file()}}
        except (ValueError, OSError, KeyError, TypeError) as error:
            bundle_info = {'status': 'unavailable', 'reason': str(error)}
        requests_dir = workspace.child(root, '.control/requests')
        request = readback = None
        if requests_dir.exists():
            for path in sorted(workspace.private_dir(requests_dir).glob('*.json'), key=lambda item: item.stat().st_mtime_ns, reverse=True):
                if not re.fullmatch(r'[a-f0-9]{32}\.json', path.name):
                    continue
                candidate = workspace.read(path, private=True, limit=32768)
                if (candidate.get('key') == task_key and candidate.get('revision') == selected.get('revision')
                        and candidate.get('file_key') == file_key and candidate.get('page_id') == page_id):
                    request = candidate
                    readback_path = candidate.get('readback')
                    if isinstance(readback_path, str):
                        expected_path = root / '.control' / 'readbacks' / (candidate['id'] + '.json')
                        if Path(readback_path) != expected_path:
                            raise ValueError('Control readback path differs from its pinned operation ID')
                        safe_path = workspace.regular(expected_path, private=True, limit=64 * 1024 * 1024)
                        readback = json.loads(safe_path.read_bytes())
                    break
    native_history = {'scope': 'unavailable', 'available': False, 'events': [], 'reason': 'No viewer-history export supplied'}
    if history_path:
        native_history = validate_history_export(workspace.read(history_path, limit=2_000_000), file_key, page_id)
    events = native_history['events']
    if current_bundle is None:
        raise ValueError('Cannot build a result bundle from an unverifiable task artifact')
    control_state = workspace.child(root, '.control')
    uncertainty = None
    uncertainty_path = workspace.child(control_state, 'uncertainty.json')
    if uncertainty_path.exists():
        uncertainty = workspace.read(uncertainty_path, private=True, limit=1_000_000)
    else:
        uncertainty = {'schema': 'unobserved', 'operations': None}
    dependencies_for_audit = []
    # Pass only public task metadata into the panel's pure projection modules.
    public_tasks = []
    for row in tasks:
        safe = workspace.public_task_metadata(row)
        for name in ('productionAdmitted', 'paired'):
            if isinstance(row.get(name), bool):
                safe[name] = row[name]
        public_tasks.append(safe)
    task_projects = {row['key']: row.get('project') for row in public_tasks}
    audit_input = {'plugin_version': workspace.read(workspace.ROOT / 'plugin.json').get('version'),
        'file_key': request.get('file_key') if request else file_key,
        'page_id': request.get('page_id') if request else page_id,
        'task_key': selected.get('key'), 'revision': selected.get('revision'),
        'operation_id': request.get('id') if request else None,
        'pairing': readback.get('pairing') if isinstance(readback, dict) else None,
        'runtime_freshness': 'not-observed',
        'lifecycle': request.get('phase_events') if request else None,
        'uncertainty': {'blocked_write': bool(uncertainty.get('operations')) if isinstance(uncertainty.get('operations'), dict) else None,
            'reasons': ['unresolved-native-operation'] if isinstance(uncertainty.get('operations'), dict) and uncertainty['operations'] else []},
        'input_summary': archived.get('input_summary'), 'dependency_freshness': dependencies_for_audit,
        'native_read': readback, 'operation': request.get('operation') if request else None}
    node_payload = {'tasks': public_tasks, 'events': events, 'taskProjects': task_projects,
        'fileKey': file_key, 'pageId': page_id, 'project': project, 'kind': kind,
        'taskKey': task_key, 'retired': [], 'assetRows': archived.get('input_summary', []),
        'assetStatus': asset_status, 'assetKind': asset_kind, 'assetQuery': asset_query,
        'auditInput': audit_input}
    with workspace.locked(root):
        _, retired = workspace.dependency_history(root)
    node_payload['retired'] = list(retired.values())
    projections = _node_projections(node_payload)
    activity = projections['activity'] if history_path else {'counts': None, 'taskStates': [], 'flows': [], 'legacy': [],
        'recommendation': None, 'observed': False, 'reason': 'No viewer-history export supplied; statuses and next action are unobserved.'}
    recommendation = projections['recommendation'] if history_path else None
    activity['recommendation'] = recommendation
    if history_path:
        activity['observed'] = True
        activity['historyPersistence'] = 'local-storage' if native_history['available'] else 'session-only-or-storage-unavailable'
    related = projections['relatedTasks']
    changes = _change_manifest(selected, current_bundle)
    details = None
    same_task_ops = [row for row in base['operations'] if row['taskKey'] == task_key and row['revision'] == selected['revision']]
    if same_task_ops:
        latest = same_task_ops[-1]
        try:
            details = workspace.history_detail(root, file_key, page_id, latest['operationId'], task_key, selected['revision'])
        except (ValueError, OSError, KeyError, TypeError):
            details = None
    return {'schema': 'figma-flow-workspace-report-v1', 'scope': {'fileKey': file_key, 'pageId': page_id,
        'runtimeGeneration': catalogue.get('runtime', {}).get('generation')},
        'evidence': {'source': 'local-signed-workspace-and-explicit-viewer-history-export',
            'nativeHistoryScope': native_history['scope'], 'nativeHistoryAvailable': native_history['available'],
            'liveFigmaVerification': 'not-performed-by-local-report'}, 'activity': activity,
        'canonicalControlActivity': base, 'latestOperationDetail': details,
        'task': {key: archived.get(key) for key in ('key', 'title', 'project', 'kind', 'fileKey', 'pageId', 'revision', 'handoff')},
        'assets': projections['assets'], 'relatedTasks': related, 'deepLinks': projections['deepLinks'],
        'changes': changes, 'diagnosticExport': projections['diagnosticExport'],
        'localTaskBundle': bundle_info,
        'sharing': {'report': 'local-only; do not treat the full bundle as a sanitized export',
            'sanitizedExports': ['--format audit-json', '--format audit-markdown']},
        'inputFreshness': next((row for row in base['inputFreshness'] if row['taskKey'] == task_key and row['revision'] == selected['revision']), None),
        'verification': {'localArtifactIntegrity': bundle_info['status'], 'nativeCurrentState': 'not-verified',
            'statusHistoryIsNotVerification': True}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--file-key', required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--task-key', required=True)
    parser.add_argument('--history-export', help='Explicit viewer-history JSON from the exact file/page')
    parser.add_argument('--project')
    parser.add_argument('--kind', choices=sorted(workspace.OPTIONS))
    parser.add_argument('--asset-status', choices=['present', '404', 'rejected', 'external-unverified'])
    parser.add_argument('--asset-kind')
    parser.add_argument('--asset-query', default='')
    parser.add_argument('--format', choices=['report', 'audit-json', 'audit-markdown'], default='report',
        help='report is a local result bundle; audit-json/markdown are the sanitized sharing exports')
    args = parser.parse_args(argv)
    try:
        report = build_report(args.workspace, args.file_key, args.page_id, args.task_key, args.history_export,
            project=args.project, kind=args.kind, asset_status=args.asset_status,
            asset_kind=args.asset_kind, asset_query=args.asset_query)
        if args.format == 'audit-json':
            sys.stdout.write(report['diagnosticExport']['json'] + '\n')
        elif args.format == 'audit-markdown':
            sys.stdout.write(report['diagnosticExport']['text'] + '\n')
        else:
            print(json.dumps(report, ensure_ascii=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print('workspace-report: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
