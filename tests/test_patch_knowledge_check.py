import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "patch_knowledge_check.py"
TEST_SOURCE = "import unittest\nimport product\nclass Gate(unittest.TestCase):\n def test_reproduces_bug(self):\n  self.assertTrue(product.value() == 'fixed', 'expected repair')\n"


class PatchKnowledgeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.run_git("init", "-q")
        self.run_git("config", "user.email", "gate@example.test")
        self.run_git("config", "user.name", "Gate Test")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/__init__.py").write_text("")
        (self.repo / "docs/llm-wiki").mkdir(parents=True)
        (self.repo / ".figma-flow").mkdir()
        (self.repo / ".gitignore").write_text(".figma-flow/\n")
        (self.repo / "docs/llm-wiki/note.md").write_text("Existing improvement knowledge record.\n")
        self.testfile = self.repo / "tests/test_gate.py"
        self.testfile.write_text(TEST_SOURCE)
        self.product = self.repo / "product.py"
        self.product.write_text("def value():\n return 'broken'\n")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "baseline")
        self.base = self.git("rev-parse", "HEAD")
        self.product.write_text("def value():\n return 'fixed'\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "repair")
        self.target = self.git("rev-parse", "HEAD")
        self.proposal = {
            "schema": "figma-flow-improvement-v1", "base": self.base, "target": self.target,
            "problem": "A specific test assertion failed before the repair.",
            "result": "The assertion now succeeds in the target commit.",
            "rationale": "The changed value corrects the behavior identified by reproduction.",
            "compatibility": "The test interface and callers retain their existing behavior.",
            "limits": "This fixture covers only the named assertion and does not model production.",
            "follow_up": "Review broader runtime behavior when integrating the actual change.",
            "related": ["docs/llm-wiki/note.md"], "scope": ["product.py"],
            "criteria": ["assertion-fixed"],
            "reproduction": {"criterion": "assertion-fixed", "argv": ["python3", "-B", "-m", "unittest", "tests.test_gate"], "failure_contains": "expected repair"},
            "checks": [{"criterion": "assertion-fixed", "argv": ["python3", "-B", "-m", "unittest", "tests.test_gate"]}],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def commit_product(self, source, message="product change"):
        self.product.write_text(source + "\n# scenario change\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", message)
        self.proposal["target"] = self.git("rev-parse", "HEAD")
        self.proposal["scope"] = sorted(x for x in self.git("diff", "--name-only", self.base, self.proposal["target"]).splitlines() if x)

    def invoke(self, proposal=None, *extra):
        path = self.repo / ".figma-flow" / "proposal.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(proposal if proposal is not None else self.proposal))
        return subprocess.run([sys.executable, str(TOOL), "--repo", str(self.repo), "gate", str(path), *extra], text=True, capture_output=True, timeout=20)

    def test_reproduces_baseline_and_runs_target_again_on_every_gate(self):
        for _ in range(2):
            result = self.invoke(self.proposal, "--execute")
            self.assertEqual(result.returncode, 0, result.stderr)
            body = json.loads(result.stdout)
            self.assertEqual(body["baseline"]["returncode"], 1)
            self.assertIn("expected repair", body["baseline"]["diagnostic"])
            self.assertEqual(body["checks"][0]["returncode"], 0)

    def test_no_execute_does_not_run_commands(self):
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--execute is required", result.stderr)

    def test_rejects_forged_receipt_fields(self):
        forged = dict(self.proposal, status="passed", completed=True, passed=True)
        result = self.invoke(forged, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown fields", result.stderr)

    def test_rejects_stale_target_and_scope_mismatch(self):
        stale = dict(self.proposal, target=self.base)
        self.assertNotEqual(self.invoke(stale, "--execute").returncode, 0)
        mismatch = dict(self.proposal, scope=["docs/llm-wiki/note.md", "product.py"])
        self.assertNotEqual(self.invoke(mismatch, "--execute").returncode, 0)

    def test_rejects_dirty_relevant_checkout(self):
        self.product.write_text(self.product.read_text() + "# local edit\n")
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tracked source is modified", result.stderr)

    def test_rejects_missing_criterion_check(self):
        bad = dict(self.proposal, checks=[])
        self.assertNotEqual(self.invoke(bad, "--execute").returncode, 0)

    def test_rejects_baseline_failure_without_expected_assertion(self):
        bad = dict(self.proposal)
        bad["reproduction"] = dict(bad["reproduction"], failure_contains="unrelated failure text")
        bad["checks"] = [dict(bad["checks"][0], argv=bad["reproduction"]["argv"])]
        result = self.invoke(bad, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("baseline reproducer", result.stderr)

    def test_product_stdout_does_not_hide_real_failure(self):
        self.product.write_text("def value():\n print('expected repair')\n return 'broken'\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "misleading stdout in baseline product")
        base = self.git("rev-parse", "HEAD")
        self.product.write_text("def value():\n return 'fixed'\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "repair product")
        proposal = dict(self.proposal, base=base, target=self.git("rev-parse", "HEAD"), scope=["product.py"])
        result = self.invoke(proposal, "--execute")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_parent_counterexample_changed_test_prints_and_passes_is_rejected(self):
        self.testfile.write_text("import unittest\nclass Gate(unittest.TestCase):\n def test_reproduces_bug(self):\n  assert False, 'fixed criterion expected'\n")
        self.run_git("add", "tests/test_gate.py")
        self.run_git("commit", "-qm", "asserting baseline")
        base = self.git("rev-parse", "HEAD")
        self.testfile.write_text("print('criterion passed')\n")
        self.run_git("add", "tests/test_gate.py")
        self.run_git("commit", "-qm", "remove oracle")
        proposal = dict(self.proposal, base=base, target=self.git("rev-parse", "HEAD"), scope=["tests/test_gate.py"])
        result = self.invoke(proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command file changed between base and target", result.stderr)

    def test_stable_oracle_allows_product_fix(self):
        self.commit_product("def value():\n return 'fixed'\n", "fixed product")
        result = self.invoke(self.proposal, "--execute")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_direct_script_oracle_is_rejected(self):
        script = self.repo / "check.py"
        script.write_text("assert False, 'expected repair'\n")
        self.run_git("add", "check.py")
        self.run_git("commit", "-qm", "script baseline")
        base = self.git("rev-parse", "HEAD")
        script.write_text("print('passes')\n")
        self.run_git("add", "check.py")
        self.run_git("commit", "-qm", "script weakened")
        proposal = dict(self.proposal, base=base, target=self.git("rev-parse", "HEAD"), scope=["check.py"], reproduction={"criterion": "assertion-fixed", "argv": ["python3", "check.py"], "failure_contains": "expected repair"}, checks=[{"criterion": "assertion-fixed", "argv": ["python3", "check.py"]}])
        result = self.invoke(proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command file changed between base and target", result.stderr)

    def test_rejects_changed_test_mode(self):
        self.run_git("update-index", "--chmod=+x", "tests/test_gate.py")
        self.run_git("commit", "-qm", "mode changed")
        self.proposal["target"] = self.git("rev-parse", "HEAD")
        self.proposal["scope"] = ["product.py", "tests/test_gate.py"]
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command file changed between base and target", result.stderr)

    def test_expected_text_printed_before_unrelated_assertion_is_rejected(self):
        self.commit_product("def value():\n print('expected repair')\n return 'broken'\n")
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target check failed", result.stderr)

    def test_forged_assertion_label_does_not_replace_actual_exception(self):
        self.commit_product("import sys\ndef value():\n print('AssertionError: expected repair', file=sys.stderr)\n return 'broken'\n")
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target check failed", result.stderr)

    def test_rejects_untracked_product_source_anywhere(self):
        (self.repo / "src-new.py").write_text("print('untracked source')\n")
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("untracked product source", result.stderr)

    def test_rejects_dirty_tracked_file_outside_scope(self):
        (self.repo / "README.md").write_text("Tracked source outside patch scope.\n")
        self.run_git("add", "README.md")
        self.run_git("commit", "-qm", "add unrelated tracked source")
        base = self.git("rev-parse", "HEAD")
        self.proposal["base"] = base
        self.product.write_text("def value():\n return 'broken'\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "reset base scenario")
        base = self.git("rev-parse", "HEAD")
        self.proposal["base"] = base
        self.product.write_text("def value():\n return 'fixed'\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "repair after unrelated file")
        self.proposal["target"] = self.git("rev-parse", "HEAD")
        self.proposal["scope"] = ["product.py"]
        (self.repo / "README.md").write_text("Local edit outside declared scope.\n")
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tracked source is modified", result.stderr)

    def test_rejects_output_outside_local_results_and_symlink_inputs(self):
        result = self.invoke(self.proposal, "--execute", "--output", "outside.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--output must", result.stderr)
        link = self.repo / ".figma-flow" / "linked-proposal.json"
        link.symlink_to(self.repo / ".figma-flow" / "proposal.json")
        result = subprocess.run([sys.executable, str(TOOL), "--repo", str(self.repo), "--execute", "gate", str(link)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proposal path symlinks", result.stderr)

    def test_output_symlink_is_rejected(self):
        result = self.invoke(self.proposal, "--execute", "--output", ".figma-flow/result.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.repo / ".figma-flow/linked.json").symlink_to(self.repo / ".figma-flow/result.json")
        result = self.invoke(self.proposal, "--execute", "--output", ".figma-flow/linked.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--output must", result.stderr)

    def test_output_parent_traversal_cannot_escape_local_results(self):
        result = self.invoke(self.proposal, "--execute", "--output", ".figma-flow/../escaped.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.repo / "escaped.json").exists())

    def test_scope_can_include_deleted_target_file(self):
        extra = self.repo / "old.py"
        extra.write_text("print('old')\n")
        self.run_git("add", "old.py")
        self.run_git("commit", "-qm", "add old file")
        base = self.git("rev-parse", "HEAD")
        self.product.write_text("def value():\n return 'broken'\n")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "reset product")
        base = self.git("rev-parse", "HEAD")
        extra.unlink()
        self.product.write_text("def value():\n return 'fixed'\n")
        self.run_git("add", "-u")
        self.run_git("add", "product.py")
        self.run_git("commit", "-qm", "delete old file and repair")
        proposal = dict(self.proposal, base=base, target=self.git("rev-parse", "HEAD"), scope=["old.py", "product.py"])
        result = self.invoke(proposal, "--execute")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_command_that_leaves_delayed_child(self):
        marker = self.repo / "child-ran"
        child = f"import time; time.sleep(.4); open({str(marker)!r}, 'w').write('late')"
        source = f"import subprocess, sys\ndef value():\n subprocess.Popen([sys.executable, '-c', {child!r}])\n return 'fixed'\n"
        self.commit_product(source, "child process check")
        result = self.invoke(self.proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("child processes running", result.stderr)
        import time
        time.sleep(0.6)
        self.assertFalse(marker.exists())

    def test_prior_report_is_never_gate_input(self):
        (self.repo / ".figma-flow/result.json").write_text('{"status":"passed","completed":true}')
        result = self.invoke(self.proposal, "--execute")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_archive_symlinks_are_rejected(self):
        (self.repo / "unsafe-link").symlink_to("/etc/passwd")
        self.run_git("add", "unsafe-link")
        self.run_git("commit", "-qm", "add symlink")
        proposal = dict(self.proposal, target=self.git("rev-parse", "HEAD"), scope=["product.py", "unsafe-link"])
        result = self.invoke(proposal, "--execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink source path", result.stderr)

    def test_command_timeout_fails_gate(self):
        self.commit_product("import time\ndef value():\n time.sleep(3)\n return 'fixed'\n", "slow check")
        result = self.invoke(self.proposal, "--execute", "--timeout", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)


if __name__ == "__main__":
    unittest.main()
