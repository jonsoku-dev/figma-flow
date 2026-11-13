"""Asset inventory filters by status and shows the relative source.

The list is not a browser load of the font or photo.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import figma_workspace as workspace


ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
import { assetInventory } from './panel-ui/src/assetInventory.mjs';
const input = JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify(assetInventory(input.summary, input.filter)));
"""


class AssetInventoryTests(unittest.TestCase):
    def inventory(self, summary, filter=None):
        completed = subprocess.run(
            ['node', '--input-type=module', '--eval', RUNNER, json.dumps({'summary': summary, 'filter': filter or {}})],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_status_filter_keeps_the_relative_source(self):
        module = ROOT / 'panel-ui/src/assetInventory.mjs'
        source = module.read_text(encoding='utf-8') if module.is_file() else ''
        self.assertIn('export function assetInventory', source, 'asset inventory must filter status and show the relative source')
        self.assertNotIn('fetch(', source)
        rows = [
            {'ref': 'fonts/body.woff2', 'kind': 'font', 'status': 'present', 'source': 'css/type.css', 'digest': 'abc'},
            {'ref': 'photos/missing.png', 'kind': 'image', 'status': '404', 'source': 'index.html', 'digest': 'def'},
            {'ref': 'https://fonts.example/font.woff2', 'kind': 'font', 'status': 'external-unverified', 'source': 'css/type.css', 'digest': 'ghi'},
        ]
        listed = self.inventory(rows)
        self.assertEqual([row['status'] for row in listed['rows']], ['404', 'external-unverified', 'present'])
        self.assertEqual(listed['counts'], {'font': 2, 'image': 1})
        self.assertEqual(listed['problems'], 2)
        self.assertFalse(listed['ready'])
        missing = self.inventory(rows, {'status': '404'})
        self.assertEqual(missing['rows'], [{'ref': 'photos/missing.png', 'kind': 'image', 'status': '404', 'source': 'index.html', 'digest': 'def'}])
        empty = self.inventory([])
        self.assertTrue(empty['empty'])
        self.assertFalse(empty['ready'])
        meta = workspace.public_task_metadata({
            'key': 'html-task', 'title': 'HTML', 'project': 'desk', 'kind': 'discover', 'revision': 'a' * 64,
            'input_record': {'artifact': 'input-record.json', 'sha256': 'b' * 64},
            'input_summary': rows + [{'ref': '/Users/example-designer/secret.png', 'kind': 'image', 'status': 'rejected', 'source': 'index.html', 'digest': 'hid'}],
        })
        self.assertEqual(meta['input_summary'], rows)
        self.assertNotIn('input_record', meta)
        self.assertNotIn('/Users/example-designer', json.dumps(meta))
        host = (ROOT / 'figma-bridge/workspace_host.js').read_text(encoding='utf-8')
        self.assertIn('function workspaceAssetSummary', host)
        self.assertIn('input_summary: assets', host)
        ui = (ROOT / 'panel-ui/src/Workspace.jsx').read_text(encoding='utf-8')
        self.assertIn('function AssetDisclosure', ui)
        self.assertIn('assetInventory(', ui)
        self.assertIn('workspace-asset-list', ui)
        self.assertNotIn('fetch(', ui[ui.index('function AssetDisclosure'):ui.index('function DependencyText')])
        bundle = (ROOT / 'figma-bridge/assets/panels.js').read_text(encoding='utf-8')
        self.assertIn('workspace-asset-list', bundle)
        tasks_doc = (ROOT / 'docs/development-roadmap/RD-05-asset-inventory/tasks.md').read_text(encoding='utf-8')
        self.assertIn('assetInventory', tasks_doc)
