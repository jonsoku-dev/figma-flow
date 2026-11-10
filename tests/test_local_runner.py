import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


script = Path(__file__).resolve().parents[1] / "tools/run_local.py"
spec = importlib.util.spec_from_file_location("figma_flow_example", script)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@unittest.skipUnless(shutil.which("node"), "requires Node to execute the bundled example")
class ExampleRunnerTests(unittest.TestCase):
    def test_delivers_views_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            runner.run_example(out)
            result = json.loads((out / "run.json").read_text())
            self.assertEqual(result["status"], "passed")
            self.assertGreater(result["fresh_node_tests"], 0)
            self.assertTrue((out / "trace.html").is_file())
            original = (out / "manifest-001.json").read_bytes()
            with self.assertRaises(FileExistsError):
                runner.run_example(out)
            self.assertEqual(original, (out / "manifest-001.json").read_bytes())

    def test_green_tests_must_match_graph_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            example = Path(tmp) / "example"
            shutil.copytree(runner.EXAMPLE, example)
            tests = example / "tests/app.test.cjs"
            tests.write_text(tests.read_text().replace("TEST-001 ", "TEST-999 ", 1))
            out = Path(tmp) / "run"
            with patch.object(runner, "EXAMPLE", example), self.assertRaisesRegex(ValueError, "differ from the graph"):
                runner.run_example(out)
            receipt = json.loads((out / "run.json").read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["steps"][0]["exit"], 0)

    def test_browser_proof_is_bound_to_app_and_declared_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(runner.EXAMPLE, root, dirs_exist_ok=True)
            receipt = json.loads((root / "evidence/browser.json").read_text())
            ids = {entry["id"] for entry in receipt["checks"]}
            with self.assertRaisesRegex(ValueError, "coverage"):
                runner.verify_browser_receipt(root, ids | {"unobserved"})
            app = root / "app/app.js"
            app.write_bytes(app.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "differs"):
                runner.verify_browser_receipt(root, ids)


if __name__ == "__main__":
    unittest.main()
