import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'tools/idea_catalog.py'
SSOT = ROOT / 'skills/figma-flow/scripts/ssot.py'


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifests = []
        for name in ('a', 'b'):
            project = self.root / name
            shutil.copytree(ROOT / 'examples/idea-notes', project)
            manifest = project / 'nested/manifest.json'
            manifest.parent.mkdir()
            result = subprocess.run([sys.executable, str(SSOT), 'snapshot', '--scope', 'local-only',
                '--brief', str(project / 'brief.md'), '--graph', str(project / 'graph.json'),
                '--bindings', str(project / 'bindings.json'), '--out', str(manifest)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.manifests.append(manifest)

    def run_catalog(self, out, *pairs):
        args = [sys.executable, str(CATALOG)]
        for label, manifest in pairs:
            args += ['--project', label, str(manifest)]
        return subprocess.run(args + ['--out', str(out)], capture_output=True, text=True)

    def test_independent_colliding_ids_and_relations(self):
        out = self.root / 'catalog'
        result = self.run_catalog(out, ('첫 프로젝트', self.manifests[0]), ('두 번째', self.manifests[1]))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((out / 'catalog.json').read_text())
        self.assertEqual(len(data['projects']), 2)
        self.assertEqual(data['projects'][0]['nodes'][0]['id'], data['projects'][1]['nodes'][0]['id'])
        self.assertTrue(any(e['from'] == 'REQ-001' and e['to'] == 'SCR-001' and e['type'] == 'appears on' for e in data['projects'][0]['edges']))
        self.assertTrue((out / data['projects'][1]['trace']).exists())
        html = (out / 'index.html').read_text()
        for selector in ('id="search"', 'id="project"', 'id="kind"', 'id="results"'):
            self.assertIn(selector, html)
        self.assertIn('Content-Security-Policy', html)

    def test_stale_and_invalid_do_not_hide_other_projects(self):
        (self.root / 'a/brief.md').write_text('changed')
        invalid = self.root / 'invalid.json'
        invalid.write_text('{}')
        out = self.root / 'catalog'
        result = self.run_catalog(out, ('stale', self.manifests[0]), ('invalid', invalid), ('valid', self.manifests[1]))
        self.assertEqual(result.returncode, 1)
        projects = json.loads((out / 'catalog.json').read_text())['projects']
        self.assertEqual([p['status'] for p in projects], ['stale-or-unavailable', 'invalid', 'current'])
        self.assertTrue(projects[0]['stale_count'] > 0)
        self.assertTrue(projects[2]['trace'])
        stale = self.run_catalog(self.root / 'only-stale', ('stale', self.manifests[0]))
        self.assertEqual(stale.returncode, 2)

    def test_nonfinite_draft_metadata_keeps_other_entries_visible(self):
        valid = self.root / 'a/graph.json'
        data = json.loads(valid.read_text())
        data['nodes'][0]['score'] = float('nan')
        invalid = self.root / 'bad.json'
        invalid.write_text(json.dumps(data))
        out = self.root / 'drafts'
        result = subprocess.run([sys.executable, str(CATALOG), '--idea', 'ok', str(valid),
                                 '--idea', 'bad', str(invalid), '--out', str(out)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((out / 'index.html').is_file())
        entries = json.loads((out / 'catalog.json').read_text())['projects']
        self.assertEqual([item['status'] for item in entries], ['draft', 'invalid'])

    def test_refuses_output_containing_missing_references_and_duplicate_labels(self):
        graph = self.root / 'a/graph.json'
        data = json.loads(graph.read_text())
        data['nodes'][0]['source'] = 'future/index.html'
        graph.write_text(json.dumps(data))
        out = self.root / 'a/future'
        result = self.run_catalog(out, ('one', self.manifests[0]))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(out.exists())
        result = self.run_catalog(self.root / 'dup', ('same', self.manifests[0]), ('same', self.manifests[1]))
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.root / 'dup').exists())

    def test_draft_only_and_mixed_with_invalid_draft(self):
        draft = self.root / 'draft.json'
        draft.write_text(json.dumps({'version': 1, 'nodes': [
            {'id': 'REQ-001', 'type': 'requirement', 'title': '새 기능', 'status': 'planned'},
            {'id': 'SCR-001', 'type': 'screen', 'title': '새 화면', 'status': 'planned'}],
            'edges': [{'from': 'REQ-001', 'to': 'SCR-001', 'type': 'appears on'}]}))
        out = self.root / 'draft-out'
        result = subprocess.run([sys.executable, str(CATALOG), '--idea', '초안', str(draft), '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads((out / 'catalog.json').read_text())['projects'][0]
        self.assertEqual(item['status'], 'draft')
        self.assertEqual(item['nodes'][0]['freshness'], 'unverified')
        self.assertIsNone(item['trace'])
        self.assertEqual(item['edges'][0]['type'], 'appears on')
        result = subprocess.run([sys.executable, str(CATALOG), '--project', '검사', str(self.manifests[0]),
            '--idea', '초안', str(draft), '--idea', '잘못됨', str(self.root / 'missing'),
            '--out', str(self.root / 'mixed')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        items = json.loads((self.root / 'mixed/catalog.json').read_text())['projects']
        self.assertEqual([i['status'] for i in items], ['current', 'draft', 'invalid'])
        self.assertEqual(items[0]['nodes'][0]['id'], items[1]['nodes'][0]['id'])

    def test_fifo_inputs_and_invalid_manifest_output_reference(self):
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        result = subprocess.run([sys.executable, str(CATALOG), '--project', 'fifo project', str(fifo),
            '--idea', 'fifo draft', str(fifo), '--out', str(self.root / 'fifo-out')], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        items = json.loads((self.root / 'fifo-out/catalog.json').read_text())['projects']
        self.assertTrue(all(p['stale_count'] is None and p['error'] for p in items))
        manifest = self.root / 'bad.json'
        manifest.write_text(json.dumps({'inputs': {'anything': {'path': 'future/index.html'}, 'graph': 3}}))
        result = self.run_catalog(self.root / 'future', ('bad', manifest))
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.root / 'future').exists())
        (self.root / 'link').symlink_to(self.root / 'missing-target')
        result = self.run_catalog(self.root / 'link', ('good', self.manifests[0]))
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.root / 'link').is_symlink())

    def test_linked_search_navigation_and_namespace_with_dom_stub(self):
        if not shutil.which('node'):
            self.skipTest('node unavailable')
        graph = lambda title: {'version': 1, 'nodes': [
            {'id':'REQ-001', 'type':'requirement', 'title':title, 'status':'planned'},
            {'id':'SCR-001', 'type':'screen', 'title':'목록 화면', 'status':'planned'}],
            'edges':[{'from':'REQ-001','to':'SCR-001','type':'appears on'}]}
        for name, title in [('one','검색'), ('two','작성')]:
            (self.root / (name + '.json')).write_text(json.dumps(graph(title)))
        out = self.root / 'ui'
        result = subprocess.run([sys.executable, str(CATALOG), '--idea', '첫째', str(self.root / 'one.json'),
            '--idea', '둘째', str(self.root / 'two.json'), '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Execute the actual page script against a minimal DOM; no browser claims are made.
        js = r"""
const fs = require('fs'), vm = require('vm'), html = fs.readFileSync(process.argv[1], 'utf8');
class E { constructor(tag, text='') { this.tag=tag; this.textContent=text; this.children=[]; this.listeners={}; this.value=''; }
 append(...items) { this.children.push(...items); } replaceChildren() { this.children=[]; }
 addEventListener(name, fn) { this.listeners[name]=fn; } focus() {} querySelector(tag) { return walk(this).find(x=>x.tag===tag); } }
function walk(e) { return [e,...e.children.filter(x=>x instanceof E).flatMap(walk)]; }
const elems = Object.fromEntries(['catalog-data','project','kind','search','results','count'].map(x=>[x,new E('div')]));
elems['catalog-data'].textContent = html.match(/<script id="catalog-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
elems.project.value='all'; elems.kind.value='all';
const doc={getElementById:id=>elems[id],createElement:tag=>new E(tag)};
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]; vm.runInNewContext(scripts[0][1], {document:doc,Map,Set});
const texts=()=>walk(elems.results).map(e=>e.textContent).join('|');
function change(id,value) { elems[id].value=value; elems[id].listeners[id==='search'?'input':'change'](); }
change('kind','screen'); change('search','검색');
if (!texts().includes('첫째') || !texts().includes('연결된 검색 결과') || texts().includes('둘째')) throw Error('linked screen search');
walk(elems.results).find(e=>e.tag==='button').listeners.click();
if (elems.project.value!=='0' || elems.kind.value!=='requirement' || !texts().includes('검색')) throw Error('navigate');
change('search','목록 화면'); if (!texts().includes('연결된 검색 결과')) throw Error('reverse linked search');
change('search',''); change('project','all'); if (!texts().includes('첫째') || !texts().includes('둘째')) throw Error('empty filter');
"""
        result = subprocess.run(['node', '-e', js, str(out / 'index.html')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_drafts_isolated_and_collision_still_refused(self):
        bad = self.root / 'bad-draft.json'
        bad.write_text(json.dumps({'version': 1, 'nodes': None, 'edges': []}))
        good = self.root / 'a/graph.json'
        out = self.root / 'mixed-invalid'
        result = subprocess.run([sys.executable, str(CATALOG), '--idea', '정상', str(good),
            '--idea', '잘못됨', str(bad), '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        items = json.loads((out / 'catalog.json').read_text())['projects']
        self.assertEqual([item['status'] for item in items], ['draft', 'invalid'])
        self.assertTrue(items[1]['error'])
        graph = self.root / 'a/graph.json'
        data = json.loads(graph.read_text()); data['nodes'] = None
        graph.write_text(json.dumps(data))
        bindings = self.root / 'a/bindings.json'
        data = json.loads(bindings.read_text()); data['evidence'] = {'N': ['future/catalog.json']}
        bindings.write_text(json.dumps(data))
        target = self.root / 'a/future'
        result = self.run_catalog(target, ('invalid', self.manifests[0]), ('valid', self.manifests[1]))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(target.exists())
        data['evidence'] = None; data['authorities'] = None
        bindings.write_text(json.dumps(data))
        result = self.run_catalog(self.root / 'mixed-project', ('invalid', self.manifests[0]), ('valid', self.manifests[1]))
        self.assertEqual(result.returncode, 1)
        items = json.loads((self.root / 'mixed-project/catalog.json').read_text())['projects']
        self.assertEqual([item['status'] for item in items], ['invalid', 'current'])

    def test_surrogate_label_serializes_safely(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        self.addCleanup(sys.path.remove, str(ROOT / 'tools'))
        import idea_catalog
        out = self.root / 'unicode'
        self.assertEqual(idea_catalog.build([], out, [('초안\ud800\x01', self.root / 'a/graph.json')]), 0)
        data = json.loads((out / 'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(data['projects'][0]['label'], '초안\ud800\x01')
        self.assertIn('\\ud800', (out / 'index.html').read_text())

    def test_html_script_injection_is_encoded(self):
        out = self.root / 'catalog'
        result = self.run_catalog(out, ('</script><script>alert(1)</script>', self.manifests[0]))
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (out / 'index.html').read_text()
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('\\u003c/script\\u003e', html)


if __name__ == '__main__':
    unittest.main()
