"""The installable inspection limits its receiver surface and binds the actual audit keys."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_api_inspect as inspect


class ServiceInspectionTest(unittest.TestCase):
    def test_project_is_private_design_only_and_graph_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'specimen'
            receipt = inspect.prepare(target, 'SampleDesignFile', '2:1', '123456')
            graph = json.loads((target / 'graph.json').read_bytes())
            self.assertEqual(receipt['graph_sha256'], hashlib.sha256((target/'graph.json').read_bytes()).hexdigest())
            self.assertEqual(receipt['selected_members'], len(graph['edges']))
            nodes = [n for n in graph['nodes'] if n['type'] == 'figma']
            self.assertEqual(len(nodes), len({n['id'] for n in nodes}))
            self.assertTrue(all(n['status'] == 'planned' for n in nodes))
            manifest = json.loads((target/'manifest.json').read_bytes())
            self.assertEqual(manifest['editorType'], ['figma'])
            self.assertEqual(manifest['networkAccess']['allowedDomains'], ['none'])
            if os.name == 'posix':
                self.assertEqual((target/'code.js').stat().st_mode & 0o777, 0o600)
            script = (target/'code.js').read_text()
            self.assertIn(receipt['graph_sha256'], script)
            self.assertNotIn('SampleDesignFile', json.dumps(graph))
            subprocess.run(['node','--check',str(target/'code.js')],check=True)
            with self.assertRaisesRegex(ValueError, 'new'):
                inspect.prepare(target, 'SampleDesignFile', '2:1', '123456')

    def test_wrong_page_is_rejected_before_touching_the_document(self):
        fixture = ROOT/'library/figma-recipes/inspection/services.js'
        js = """const fs=require('node:fs'),vm=require('node:vm');
const c=vm.createContext({});vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
const api={currentPage:{id:'2:1'},editorType:'figma',fileKey:'fixture'};
c.inspectDesignServices(api,{file:'fixture',page:'4:2'}).then(()=>process.exit(1)).catch(e=>{
 if(!String(e).includes('admitted by the inspection graph'))process.exit(1);});"""
        subprocess.run(['node', '-e', js, str(fixture)], check=True)
