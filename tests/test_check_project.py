import json
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tools/check_project.py"
SSOT = ROOT / "skills/figma-flow/scripts/ssot.py"


class CheckProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        shutil.copytree(ROOT / "examples/idea-notes", self.project)
        self.manifest = self.project / "nested/manifest.json"
        self.manifest.parent.mkdir()
        result = subprocess.run([sys.executable, "-B", str(SSOT), "snapshot", "--scope", "local-only",
            "--brief", str(self.project / "brief.md"), "--graph", str(self.project / "graph.json"),
            "--bindings", str(self.project / "bindings.json"), "--out", str(self.manifest)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_check(self, out, *flags):
        return subprocess.run([sys.executable, "-B", str(CHECK), str(self.manifest), "--intent", "inspect", "--out", str(out), *flags], capture_output=True, text=True)

    def run_init(self, out, *flags):
        return subprocess.run([sys.executable, "-B", str(CHECK), "--init", "--intent", "inspect", "--brief", str(self.project / "brief.md"),
            "--graph", str(self.project / "graph.json"), "--bindings", str(self.project / "bindings.json"),
            "--out", str(out), *flags], capture_output=True, text=True)

    def test_init_then_recheck_and_diff(self):
        out = self.root / "first"
        result = self.run_init(out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((out / "baseline-graph.json").read_bytes(), (self.project / "graph.json").read_bytes())
        self.assertEqual(json.loads((out / "summary.json").read_text())["baseline_kind"], "independent-first-baseline")
        graph = self.project / "graph.json"
        data = json.loads(graph.read_text())
        data["nodes"][0]["title"] += " changed"
        graph.write_text(json.dumps(data))
        target = self.root / "recheck"
        result = subprocess.run([sys.executable, "-B", str(CHECK), str(out / "manifest-001.json"),
            "--previous-graph", str(out / "baseline-graph.json"), "--out", str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads((target / "summary.json").read_text())["graph_diff_status"], "verified")
        self.assertTrue((target / "graph-diff.html").exists())
        bad = self.root / "bad"
        result = subprocess.run([sys.executable, "-B", str(CHECK), str(out / "manifest-001.json"),
            "--previous-graph", str(graph), "--out", str(bad)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(bad.exists())

    def test_init_missing_evidence_and_output_collision(self):
        (self.project / "evidence/browser.json").unlink()
        out = self.root / "missing"
        result = self.run_init(out)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue((out / "trace.html").exists())
        graph = self.project / "graph.json"
        data = json.loads(graph.read_text())
        data["nodes"][0]["source"] = "future/check.json"
        graph.write_text(json.dumps(data))
        out = self.project / "future"
        self.assertEqual(self.run_init(out).returncode, 1)
        self.assertFalse(out.exists())

    def test_summary_identifies_nodes_without_evidence_and_missing_source(self):
        graph = self.project / 'graph.json'
        data = json.loads(graph.read_text())
        by_id = {node['id']: node for node in data['nodes']}
        del by_id['STATE-001']['source']
        by_id['ACT-001']['source'] = 'missing.html#open'
        graph.write_text(json.dumps(data))
        bindings = self.project / 'bindings.json'
        data = json.loads(bindings.read_text())
        del data['evidence']['STATE-001']
        bindings.write_text(json.dumps(data))
        out = self.root / 'unverified'
        self.assertEqual(self.run_init(out).returncode, 2)
        rows = json.loads((out / 'summary.json').read_text())['freshness_unverified']
        self.assertEqual(rows, [
            {'node': 'ACT-001', 'freshness': 'unverified', 'reasons': ['missing-evidence'],
             'missing': ['../project/missing.html']},
            {'node': 'STATE-001', 'freshness': 'unverified', 'reasons': ['no-evidence'], 'missing': []},
        ])

    def test_current_stale_and_no_overwrite(self):
        out = self.root / "current"
        result = self.run_check(out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((out / "summary.json").read_text())["status"], "current")
        self.assertEqual(json.loads((out / "summary.json").read_text())["audit_status"], "not-requested")
        self.assertTrue((out / "trace.html").is_file())
        before = (out / "check.json").read_bytes()
        self.assertEqual(self.run_check(out).returncode, 1)
        self.assertEqual((out / "check.json").read_bytes(), before)
        with (self.project / "brief.md").open("a") as f:
            f.write("\nchanged\n")
        stale = self.root / "stale"
        self.assertEqual(self.run_check(stale).returncode, 2)
        self.assertEqual(json.loads((stale / "summary.json").read_text())["status"], "stale-or-unavailable")
        self.assertTrue((stale / "trace.html").is_file())

    def test_invalid_manifest(self):
        self.manifest.write_text('{}')
        out = self.root / "invalid"
        self.assertEqual(self.run_check(out).returncode, 1)
        self.assertFalse(out.exists())

    def test_refuses_declared_missing_output_reference(self):
        graph = self.project / "graph.json"
        data = json.loads(graph.read_text())
        data["nodes"][0]["source"] = "future/check.json"
        graph.write_text(json.dumps(data))
        out = self.project / "future"
        result = self.run_check(out)
        self.assertEqual(result.returncode, 1)
        self.assertIn("declared input", result.stderr)
        self.assertFalse(out.exists())

    def test_full_scope_preserves_remote_unavailability(self):
        bindings = self.project / "bindings.json"
        data = json.loads(bindings.read_text())
        data["authorities"]["visual"] = "https://example.com/design"
        bindings.write_text(json.dumps(data))
        full = self.manifest.parent / "full.json"
        result = subprocess.run([sys.executable, "-B", str(SSOT), "snapshot",
            "--brief", str(self.project / "brief.md"), "--graph", str(self.project / "graph.json"),
            "--bindings", str(bindings), "--out", str(full)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.manifest = full
        out = self.root / "full"
        self.assertEqual(self.run_check(out).returncode, 2)
        summary = json.loads((out / "summary.json").read_text())
        self.assertEqual(summary["scope"], "full")
        self.assertEqual(json.loads((out / "check.json").read_text())["unavailable_authorities"], ["visual"])
        self.assertTrue((out / "trace.html").exists())

    def test_collision_preflight_skips_malformed_containers(self):
        spec = importlib.util.spec_from_file_location("check_project", CHECK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out = self.root / "future"
        with self.assertRaisesRegex(ValueError, "declared input"):
            module.reject_output_references(out, self.manifest, {}, {"nodes": None},
                {"authorities": None, "evidence": {"id": ["../future/check.json"]}},
                self.project / "graph.json", self.project / "bindings.json")
        module.reject_output_references(out, self.manifest, {}, {"nodes": None},
            {"authorities": None, "evidence": None}, self.project / "graph.json", self.project / "bindings.json")

    def test_malformed_containers_rejected_without_traceback(self):
        graph = self.project / "graph.json"
        data = json.loads(graph.read_text())
        data["nodes"] = None
        graph.write_text(json.dumps(data))
        result = self.run_init(self.root / "malformed")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "malformed").exists())

    def test_strict_coverage_is_separate_from_ssot(self):
        graph = self.project / "graph.json"
        data = json.loads(graph.read_text())
        data["nodes"] = [node for node in data["nodes"] if node["type"] != "test"]
        ids = {node["id"] for node in data["nodes"]}
        data["edges"] = [edge for edge in data["edges"] if edge["from"] in ids and edge["to"] in ids]
        graph.write_text(json.dumps(data))
        bindings = self.project / "bindings.json"
        binding = json.loads(bindings.read_text())
        binding["evidence"] = {key: value for key, value in binding.get("evidence", {}).items() if key in ids}
        bindings.write_text(json.dumps(binding))
        out = self.root / "coverage"
        result = self.run_check(out)
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads((out / "summary.json").read_text())
        self.assertTrue(summary["strict_local"]["errors"])
        self.assertEqual(summary["ssot_exit"], 2)
        self.assertTrue((out / "trace.html").exists())

    def test_audit_blocks_fresh_but_contradictory_brief(self):
        (self.project / 'brief.md').write_text('After retry, show the same card.\nAfter retry, show the next pending card.\n')
        self.manifest.unlink()
        snapshot = subprocess.run([sys.executable, '-B', str(SSOT), 'snapshot', '--scope', 'local-only',
            '--brief', str(self.project / 'brief.md'), '--graph', str(self.project / 'graph.json'),
            '--bindings', str(self.project / 'bindings.json'), '--out', str(self.manifest)], capture_output=True, text=True)
        self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
        out = self.root / 'audited-contradiction'
        result = self.run_check(out, '--audit', '--project', str(self.project))
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads((out / 'summary.json').read_text())
        self.assertEqual(summary['freshness_status'], 'current')
        self.assertEqual(summary['ssot_exit'], 0)
        self.assertEqual(summary['coverage_status'], 'valid')
        self.assertEqual(summary['audit_status'], 'findings')
        self.assertEqual(summary['brief_audit_status'], 'fail')
        self.assertEqual(summary['acceptance_claim'], 'blocked-by-active-contradiction')
        audit = json.loads((out / 'audit.json').read_text())
        self.assertEqual([item['line'] for item in audit['brief_consistency']['findings'][0]['evidence']], [1, 2])
        self.assertTrue((out / 'audit.md').exists())
        self.assertTrue((out / 'trace.html').exists())
        legacy = self.root / 'legacy-fresh'
        self.assertEqual(self.run_check(legacy).returncode, 0)
        self.assertEqual(json.loads((legacy / 'summary.json').read_text())['audit_status'], 'not-requested')

    def test_audit_review_and_error_are_retained_separately(self):
        out = self.root / 'audited-review'
        result = self.run_check(out, '--audit', '--project', str(self.project), '--spec', 'screen-spec.md')
        self.assertEqual(result.returncode, 2, result.stderr)
        summary = json.loads((out / 'summary.json').read_text())
        self.assertEqual(summary['freshness_status'], 'current')
        self.assertEqual(summary['audit_status'], 'review')
        self.assertTrue((out / 'audit.json').exists())
        error = self.root / 'audited-error'
        self.assertEqual(self.run_check(error, '--audit', '--project', str(self.project), '--spec', 'missing.md').returncode, 1)
        summary = json.loads((error / 'summary.json').read_text())
        self.assertEqual(summary['audit_status'], 'error')
        self.assertEqual(summary['freshness_status'], 'current')
        self.assertTrue(json.loads((error / 'audit.json').read_text())['error'])

    def test_audit_requires_explicit_root_and_supports_initialization(self):
        target = self.root / 'missing-root'
        self.assertEqual(self.run_check(target, '--audit').returncode, 1)
        self.assertFalse(target.exists())
        target = self.root / 'unused-spec'
        self.assertEqual(self.run_check(target, '--spec', 'screen-spec.md').returncode, 1)
        self.assertFalse(target.exists())
        target = self.root / 'init-with-audit'
        result = self.run_init(target, '--audit', '--project', str(self.project))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads((target / 'summary.json').read_text())['baseline_kind'], 'independent-first-baseline')
        self.assertTrue((target / 'audit.json').exists())

    def native_fixture(self):
        spec = importlib.util.spec_from_file_location('native_fixture', ROOT / 'tests/test_native_handoff.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        readback, contract = module.fixture()
        (self.project / 'readback.json').write_text(json.dumps(readback))
        (self.project / 'contract.json').write_text(json.dumps(contract))
        bindings_path = self.project / 'bindings.json'
        bindings = json.loads(bindings_path.read_text())
        bindings['native_handoff'] = {'readback': 'readback.json', 'contract': 'contract.json',
                                      'page_id': '1:1', 'file_key': 'fixture'}
        bindings_path.write_text(json.dumps(bindings))
        return readback, contract

    def test_figma_graph_without_handoff_is_blocked_at_both_entries(self):
        path = self.project / 'graph.json'
        data = json.loads(path.read_text())
        data['nodes'].append({'id': 'FIG-001', 'type': 'figma', 'title': 'Native design',
                              'status': 'observed', 'source': 'https://www.figma.com/design/fixture'})
        data['edges'].append({'from': 'SCR-001', 'to': 'FIG-001', 'type': 'designed as'})
        path.write_text(json.dumps(data))
        for entry in (self.run_init, self.run_check):
            out = self.root / entry.__name__
            result = entry(out)
            self.assertEqual(result.returncode, 1, result.stderr)
            summary = json.loads((out / 'summary.json').read_text())
            self.assertEqual(summary['coverage_status'], 'valid')
            self.assertEqual(summary['native_handoff_status'], 'blocked')
            self.assertEqual(summary['runtime_status'], 'not-checked')
            self.assertEqual(summary['acceptance_claim'], 'blocked-by-native-handoff')
            self.assertIn('bindings.native_handoff', (out / 'screen-spec.md').read_text())

    def test_visual_authority_and_declared_gate_cannot_silently_skip(self):
        path = self.project / 'bindings.json'
        data = json.loads(path.read_text())
        data['authorities']['visual'] = 'https://www.figma.com/design/fixture'
        path.write_text(json.dumps(data))
        self.assertEqual(self.run_init(self.root / 'visual').returncode, 1)
        del data['authorities']['visual']
        for declaration in (None, {}, {'readback': 'missing.json', 'contract': 'also-missing.json', 'page_id': '1:1'}):
            with self.subTest(declaration=declaration):
                data['native_handoff'] = declaration
                path.write_text(json.dumps(data))
                out = self.root / ('declared-' + str(len(list(self.root.iterdir()))))
                self.assertEqual(self.run_init(out).returncode, 1)
                self.assertEqual(json.loads((out / 'native-handoff.json').read_text())['status'], 'blocked')

    def test_valid_native_observation_spec_and_byte_pins(self):
        import hashlib
        self.native_fixture()
        first = self.root / 'native-valid'
        result = self.run_init(first)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.manifest = first / 'manifest-001.json'
        out = self.root / 'native-recheck'
        result = self.run_check(out)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((out / 'native-handoff.json').read_text())
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(report['screens'][0]['observed']['width'], 1440)
        self.assertEqual(report['screens'][0]['controls'][0]['main_component']['id'], '1:5')
        for key in ('readback', 'contract'):
            path = self.project / (key + '.json')
            self.assertEqual(report['evidence_inputs'][key]['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(Path(report['evidence_inputs'][key]['path']).resolve(), path.resolve())
        self.assertEqual(report['inputs']['graph']['sha256'], hashlib.sha256((self.project / 'graph.json').read_bytes()).hexdigest())
        self.assertIn('1440', (out / 'screen-spec.md').read_text())
        self.assertEqual(json.loads((out / 'summary.json').read_text())['acceptance_claim'], 'not-established')
        self.assertEqual(self.run_check(out).returncode, 1)

    def test_real_native_evidence_failures_block_even_with_fresh_baseline(self):
        for mutation in ('annotation', 'binding', 'empty-contract', 'empty-controls', 'file', 'page'):
            with self.subTest(mutation=mutation):
                readback, contract = self.native_fixture()
                if mutation == 'annotation':
                    readback['nodes'][1].pop('annotations')
                elif mutation == 'binding':
                    readback['nodes'][1]['fills'][0]['boundVariables']['color']['id'] = 'other'
                elif mutation == 'empty-contract':
                    contract['screens'] = []
                elif mutation == 'empty-controls':
                    contract['screens'][0]['controls'] = []
                elif mutation == 'file':
                    readback['fileKey'] = 'wrong'
                else:
                    readback['pageId'] = 'other'
                (self.project / 'readback.json').write_text(json.dumps(readback))
                (self.project / 'contract.json').write_text(json.dumps(contract))
                out = self.root / ('native-' + mutation)
                result = self.run_init(out)
                self.assertEqual(result.returncode, 1, result.stderr)
                summary = json.loads((out / 'summary.json').read_text())
                self.assertEqual(summary['freshness_status'], 'current')
                self.assertEqual(summary['native_handoff_status'], 'blocked')
                self.assertTrue(json.loads((out / 'native-handoff.json').read_text())['errors'])

    def test_native_inputs_and_outputs_preserve_declared_files(self):
        self.native_fixture()
        path = self.project / 'bindings.json'
        bindings = json.loads(path.read_text())
        bindings['native_handoff']['readback'] = 'future/native-handoff.json'
        path.write_text(json.dumps(bindings))
        out = self.project / 'future'
        result = self.run_init(out)
        self.assertEqual(result.returncode, 1)
        self.assertIn('declared input', result.stderr)
        self.assertFalse(out.exists())
        self.native_fixture()
        (self.project / 'readback.json').rename(self.project / 'actual.json')
        (self.project / 'readback.json').symlink_to(self.project / 'actual.json')
        out = self.root / 'symlink-input'
        self.assertEqual(self.run_init(out).returncode, 1)
        self.assertIn('symlinks', (out / 'screen-spec.md').read_text())
        (self.root / 'linked-project').symlink_to(self.project, target_is_directory=True)
        result = self.run_init(self.root / 'linked-project/out')
        self.assertEqual(result.returncode, 1)
        self.assertIn('symlinks', result.stderr)
        self.assertFalse((self.project / 'out').exists())


if __name__ == "__main__":
    unittest.main()
