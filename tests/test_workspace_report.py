"""Local report projection tests compare retained history semantics without Figma access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import figma_workspace as workspace
import workspace_report as report
from test_graph_sync import fixture as graph_fixture


@unittest.skipUnless(os.name == 'posix', 'Private workspace permissions currently require POSIX')
class WorkspaceReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = self.root / 'workspace'
        identity = self.root / 'assigned.json'
        identity.write_text('{"id":"12345"}')
        workspace.init(self.workspace, identity)

    def test_activity_status_distribution_and_recommendation_keep_panel_order(self):
        digest = 'a' * 64
        tasks = [
            {'key':'pending', 'revision':digest, 'fileKey':'file', 'kind':'discover'},
            {'key':'failed', 'revision':'b' * 64, 'fileKey':'file', 'kind':'discover'},
            {'key':'other-file', 'revision':'c' * 64, 'fileKey':'elsewhere', 'kind':'discover'},
        ]
        events = [
            {'taskKey':'pending', 'revision':digest, 'operation':'download', 'status':'requested'},
            {'taskKey':'pending', 'revision':digest, 'operation':'chat:open', 'status':'finished'},
            {'taskKey':'failed', 'revision':'b' * 64, 'operation':'read', 'status':'failed', 'executionId':'e1'},
            {'taskKey':'failed', 'revision':'b' * 64, 'operation':'read', 'status':'failed', 'executionId':'e1'},
        ]
        result = report._node_projections({'tasks':tasks, 'events':events, 'taskProjects':{}, 'fileKey':'file',
            'pageId':'1:1', 'project':None, 'kind':None, 'taskKey':'failed', 'retired':[], 'assetRows':[],
            'assetStatus':None, 'assetKind':None, 'assetQuery':'', 'auditInput':{}})
        self.assertEqual(result['activity']['counts'], {'baseline':0, 'failed':1, 'finished':0, 'pending':2,
            'readback':0, 'requested':0, 'running':0, 'verified':0})
        self.assertEqual(result['recommendation']['taskKey'], 'failed')
        self.assertFalse(result['recommendation']['inspect'])
        self.assertEqual(len(result['activity']['flows']), 1)
        self.assertEqual([step['event']['operation'] for step in result['activity']['flows'][0]['steps']], ['read', 'read'])
        self.assertEqual(len(result['activity']['legacy']), 2)

    def test_activity_continues_latest_candidate_without_collapsing_tasks_by_key(self):
        tasks = [
            {'key':'a', 'revision':'1' * 64, 'fileKey':'file', 'kind':'discover', 'project':'p', 'productionAdmitted':True},
            {'key':'b', 'revision':'2' * 64, 'fileKey':'file', 'kind':'import', 'project':'p', 'productionAdmitted':True},
            {'key':'c', 'revision':'3' * 64, 'fileKey':'file', 'kind':'discover', 'project':'q'},
        ]
        events = [{'taskKey':'a', 'revision':'1' * 64, 'operation':'read', 'status':'verified', 'time':'t1'},
            {'taskKey':'b', 'revision':'2' * 64, 'operation':'read', 'status':'readback', 'time':'t2'}]
        result = report._node_projections({'tasks':tasks, 'events':events, 'taskProjects':{}, 'fileKey':'file',
            'pageId':'1:1', 'project':None, 'kind':None, 'taskKey':'b', 'retired':[], 'assetRows':[],
            'assetStatus':None, 'assetKind':None, 'assetQuery':'', 'auditInput':{}})
        self.assertEqual(result['recommendation']['taskKey'], 'b')
        self.assertTrue(result['recommendation']['inspect'])
        self.assertEqual(result['activity']['counts']['pending'], 1)
        self.assertEqual(result['activity']['counts']['verified'], 1)
        self.assertEqual(result['activity']['counts']['readback'], 1)

    def test_local_activity_matches_live_panel_projection_and_recommendation_source(self):
        tasks = [
            {'key':'p1', 'revision':'1' * 64, 'fileKey':'file', 'kind':'discover', 'project':'alpha', 'productionAdmitted':True},
            {'key':'p2', 'revision':'2' * 64, 'fileKey':'file', 'kind':'discover', 'project':'alpha', 'productionAdmitted':True},
            {'key':'p3', 'revision':'3' * 64, 'fileKey':'file', 'kind':'discover', 'project':'beta'},
            {'key':'foreign', 'revision':'4' * 64, 'fileKey':'other', 'kind':'discover'},
        ]
        events = [
            {'taskKey':'p1','revision':'1' * 64,'operation':'download','status':'requested','time':'2026-11-01T00:00:00Z'},
            {'taskKey':'p1','revision':'1' * 64,'operation':'read','status':'verified','executionId':'e1','time':'2026-11-01T00:01:00Z'},
            {'taskKey':'p2','revision':'2' * 64,'operation':'chat:open','status':'finished','executionId':'e2','time':'2026-11-01T00:02:00Z'},
            {'taskKey':'p2','revision':'2' * 64,'operation':'read','status':'failed','executionId':'e3','time':'2026-11-01T00:03:00Z'},
            {'taskKey':'orphan','revision':'5' * 64,'operation':'read','status':'failed','time':'2026-11-01T00:04:00Z'},
        ]
        projected = report._node_projections({'tasks':tasks, 'events':events, 'taskProjects':{task['key']:task.get('project') for task in tasks},
            'fileKey':'file', 'pageId':'1:1', 'project':None, 'kind':None, 'taskKey':'p1', 'retired':[], 'assetRows':[],
            'assetStatus':None, 'assetKind':None, 'assetQuery':'', 'auditInput':{}})
        script = r"""
const fs = require('fs');
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const {workspaceActivity} = await import('./panel-ui/src/WorkspaceActivity.mjs');
  const {selectRecommendation} = await import('./panel-ui/src/workspaceRecommendation.mjs');
  const model = {fileKey: input.file_key, tasks: input.tasks, history: input.events};
  const ui = workspaceActivity(input.tasks, input.events);
  const recommendation = selectRecommendation(model, input.tasks);
  process.stdout.write(JSON.stringify({counts:ui.counts, flows:ui.flows.map(flow => ({executionId:flow.executionId, taskKey:flow.steps[0].event.taskKey, current:flow.steps[0].current})), legacy:ui.legacy.length,
    recommendation:recommendation && {taskKey:recommendation.task.key, inspect:recommendation.inspect}}));
})().catch(error => {console.error(error); process.exit(1)});
"""
        completed = subprocess.run(['node', '-e', script], input=json.dumps({'file_key':'file','tasks':tasks,'events':events}),
            cwd=ROOT, text=True, capture_output=True, check=True)
        ui = json.loads(completed.stdout)
        self.assertEqual(projected['activity']['counts'], ui['counts'])
        self.assertEqual([(flow['executionId'], flow['steps'][0]['event']['taskKey'], flow['steps'][0]['current']) for flow in projected['activity']['flows']],
            [(flow['executionId'], flow['taskKey'], flow['current']) for flow in ui['flows']])
        self.assertEqual(len(projected['activity']['legacy']), ui['legacy'])
        self.assertEqual((projected['recommendation']['taskKey'], projected['recommendation']['inspect']),
            (ui['recommendation']['taskKey'], ui['recommendation']['inspect']))
        filtered = report._node_projections({'tasks':tasks, 'events':events,
            'taskProjects':{task['key']:task.get('project') for task in tasks}, 'fileKey':'file', 'pageId':'1:1',
            'project':'alpha', 'kind':'discover', 'taskKey':'p2', 'retired':[], 'assetRows':[],
            'assetStatus':None, 'assetKind':None, 'assetQuery':'', 'auditInput':{}})
        self.assertEqual([row['task']['key'] for row in filtered['activity']['taskStates']], ['p1', 'p2'])
        self.assertEqual(filtered['recommendation']['taskKey'], 'p2')
        self.assertEqual(filtered['activity']['counts']['pending'], 0)
        self.assertEqual(filtered['activity']['counts']['failed'], 1)

    def test_local_report_bundles_assets_related_deep_link_and_readonly_audit(self):
        plan = self.root / 'edit.json'
        plan.write_text(json.dumps({'schema':'figma-flow-native-edit-plan-v1', 'file_key':'fixturefile',
            'page_id':'12:1', 'edits':[{'node_id':'3:4','field':'paddingLeft','before':12,'after':20}]}))
        result = workspace.prepare(self.workspace, 'edit-button', 'Edit button', 'native-edit', ['--plan', str(plan)])
        task = workspace.current(self.workspace)['tasks'][0]
        history = {'schema':report.HISTORY_SCHEMA, 'operation':'viewer-history', 'scope':'file',
            'source':'figma-clientStorage', 'fileKey':'fixturefile', 'pageId':'12:1', 'available':True,
            'history':[{'taskKey':'edit-button','revision':task['revision'],'operation':'apply','status':'readback',
                'time':'2026-11-22T00:00:00Z','executionId':'run1','carousel':{'status':'current',
                    'schema':'figma-flow-carousel-summary-v1','file_key':'fixturefile','page_id':'12:1',
                    'initial_state':'state-a','flow_start_node_id':'3:4'}}]}
        history_path = self.root / 'history.json'
        history_path.write_text(json.dumps(history))
        report_value = report.build_report(self.workspace, 'fixturefile', '12:1', 'edit-button', history_path)
        self.assertEqual(report_value['activity']['recommendation']['action'], 'inspect-latest-result')
        self.assertEqual(report_value['assets']['rows'], [])
        self.assertEqual(report_value['localTaskBundle']['status'], 'available')
        self.assertEqual(report_value['deepLinks'][0]['url'],
            'https://www.figma.com/proto/fixturefile/SaaS?node-id=3-4&starting-point-node-id=3-4&page-id=12-1&scaling=scale-down')
        self.assertEqual(report_value['verification']['nativeCurrentState'], 'not-verified')
        self.assertTrue(report_value['diagnosticExport']['json'].startswith('{'))
        self.assertEqual(report_value['sharing']['sanitizedExports'], ['--format audit-json', '--format audit-markdown'])
        offline = report.build_report(self.workspace, 'fixturefile', '12:1', 'edit-button')
        self.assertFalse(offline['activity']['observed'])
        self.assertIsNone(offline['activity']['counts'])
        self.assertIsNone(offline['activity']['recommendation'])

        for export_format in ('audit-json', 'audit-markdown'):
            command = [sys.executable, str(ROOT / 'tools/workspace_report.py'), '--workspace', str(self.workspace),
                '--file-key', 'fixturefile', '--page-id', '12:1', '--task-key', 'edit-button',
                '--history-export', str(history_path), '--format', export_format]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            if export_format == 'audit-json':
                self.assertEqual(json.loads(completed.stdout), json.loads(report_value['diagnosticExport']['json']))
            else:
                self.assertEqual(completed.stdout, report_value['diagnosticExport']['text'] + '\n')

    def test_viewer_history_export_rejects_foreign_page_or_native_operation(self):
        bad = {'schema':report.HISTORY_SCHEMA, 'operation':'viewer-history', 'scope':'file',
            'source':'figma-clientStorage', 'fileKey':'file', 'pageId':'12:2', 'available':True, 'history':[]}
        with self.assertRaisesRegex(ValueError, 'exact file and page'):
            report.validate_history_export(bad, 'file', '12:1')
        bad['pageId'] = '12:1'
        bad['operation'] = 'apply'
        with self.assertRaisesRegex(ValueError, 'exact file and page'):
            report.validate_history_export(bad, 'file', '12:1')

    def test_sync_bundle_exposes_pinned_selection_ids_group_targets_and_before_after(self):
        import graph_sync
        plan = {'tokens':[{'key':'color/action','root_variable_id':'root','variable_id':'root',
            'variable_name':'color/action','before':{'r':0,'g':0,'b':0},'value':{'r':1,'g':1,'b':1}}],
            'components':[{'id':'button','properties':{'fill':'color/action'},'main_keys':['main'],'instance_keys':['instance']}],
            'repair_bindings':[]}
        manifest = graph_sync.selection_manifest(plan)
        bundle = self.root / 'bundle'
        bundle.mkdir(mode=0o700)
        source = 'const GRAPH_SELECTION_MANIFEST = ' + json.dumps(manifest) + ';\nconst GRAPH_SYNC_PLAN = ' + json.dumps(plan) + ';\n'
        workspace.atomic(bundle / 'code.js', source.encode())
        task = {'kind':'sync'}
        selection = report._change_manifest(task, bundle)
        self.assertEqual(selection['schema'], 'figma-flow-selection-v2')
        self.assertEqual(selection['protocol'], 2)
        self.assertEqual(len(selection['plan_sha256']), 64)
        self.assertTrue(selection['changes'])
        self.assertTrue(selection['selected_ids'])
        row = selection['changes'][0]
        self.assertIn('identity', row)
        self.assertIn('group', row)
        self.assertIn('targets', row)
        self.assertIn('before', row)
        self.assertIn('after', row)

    def test_asset_filter_matches_panel_search_and_keeps_global_problem_count(self):
        task = {'key':'x', 'revision':'a' * 64, 'fileKey':'file', 'kind':'discover'}
        rows = [
            {'ref':'brief.md', 'kind':'brief', 'status':'present', 'source':'manual brief', 'digest':'a'},
            {'ref':'hero.png', 'kind':'image', 'status':'external-unverified', 'source':'remote image', 'digest':'b'},
            {'ref':'button.svg', 'kind':'icon', 'status':'present', 'source':'local asset', 'digest':'c'},
        ]
        projected = report._node_projections({'tasks':[task], 'events':[], 'taskProjects':{'x':''}, 'fileKey':'file',
            'pageId':'1:1', 'project':None, 'kind':None, 'taskKey':'x', 'retired':[], 'assetRows':rows,
            'assetStatus':None, 'assetKind':None, 'assetQuery':'image', 'auditInput':{}})['assets']
        self.assertEqual([row['ref'] for row in projected['rows']], ['hero.png'])
        self.assertEqual(projected['problems'], 1)
        self.assertEqual(projected['counts'], {'brief':1, 'icon':1, 'image':1})


if __name__ == '__main__':
    unittest.main()
