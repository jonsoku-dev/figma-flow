#!/usr/bin/env python3
"""Run the bundled idea-notes example in a fresh directory."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parents[1]
EXAMPLE = PLUGIN / "examples" / "idea-notes"
SCRIPTS = PLUGIN / "skills" / "figma-flow" / "scripts"


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_browser_receipt(root, expected_checks):
    historical = json.loads((root / "evidence/browser.json").read_text(encoding="utf-8"))
    old_checks = historical["checks"]
    old_ids = [check.get("id") for check in old_checks]
    if (not isinstance(old_checks, list) or not old_checks
            or any(not isinstance(check, dict) or check.get("passed") is not True for check in old_checks)):
        raise ValueError("The historical browser checks are missing or include a failure.")
    if not expected_checks or len(set(old_ids)) != len(old_ids) or set(old_ids) != expected_checks:
        raise ValueError("The historical browser receipt has duplicate IDs or lacks declared interaction coverage.")
    if not historical.get("date", "").startswith("2026-11-07"):
        raise ValueError("The archived browser record lost its original date.")

    current = json.loads((root / "evidence/browser-current.json").read_text(encoding="utf-8"))
    checks = current.get("checks")
    current_ids = {check.get("id") for check in checks} if isinstance(checks, list) else set()
    required_current = expected_checks | {"visual-token-mutation"}
    if (current_ids != required_current or
            any(not isinstance(check, dict) or check.get("passed") is not True or not check.get("observed")
                for check in checks)):
        raise ValueError("The current browser proof lacks its scoped local interaction coverage.")
    expected = current.get("app_sha256")
    actual = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((root / "app").rglob("*")) if p.is_file()}
    if not actual or actual != expected:
        raise ValueError("The app differs from the version covered by the current browser proof.")
    screenshots = current.get("screenshots")
    required_screenshots = {"evidence/browser-current-mobile.png", "evidence/browser-current-visual-mutation.png"}
    if not isinstance(screenshots, dict) or set(screenshots) != required_screenshots:
        raise ValueError("The current browser proof is missing its mobile or graph-mutation screenshot.")
    for relative, digest in screenshots.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("A current browser screenshot differs from the proof.")
    return {"historical": len(old_checks), "current": len(checks)}


def run_example(out):
    out = out.resolve()
    if out == EXAMPLE or EXAMPLE in out.parents:
        raise ValueError("Choose a new output directory outside the bundled example.")
    out.mkdir(parents=True, exist_ok=False)
    results = {"status": "running", "steps": []}

    def step(name, command, log):
        result = subprocess.run([str(v) for v in command], cwd=out, capture_output=True)
        (out / log).write_bytes(result.stdout)
        if result.stderr:
            (out / (name + ".stderr.txt")).write_bytes(result.stderr)
        results["steps"].append({"name": name, "command": [str(v) for v in command],
                                 "exit": result.returncode, "stdout": log})
        if result.returncode:
            raise ValueError(f"{name} failed (exit {result.returncode}). See {out}.")

    python = [sys.executable, "-B"]
    graph = python + [SCRIPTS / "graph.py"]
    ssot = python + [SCRIPTS / "ssot.py"]
    try:
        shutil.copytree(EXAMPLE, out, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        step("node-tests", ["node", "--test", "--test-reporter=tap", "tests/app.test.cjs"], "evidence/node-tests.tap")
        tap = (out / "evidence/node-tests.tap").read_text(encoding="utf-8")
        counts = {name: int(count) for name, count in re.findall(r"^# (tests|pass|skipped|todo) (\d+)\s*$", tap, re.M)}
        graph_data = json.loads((out / "graph.json").read_text(encoding="utf-8"))
        test_nodes = [node for node in graph_data["nodes"] if node["type"] == "test"]
        declared = {node["id"] for node in test_nodes if node["source"] == "evidence/node-tests.tap"}
        passed = re.findall(r"^ok \d+ - (TEST-\d+) ", tap, re.M)
        if (not declared or len(passed) != len(declared) or set(passed) != declared
                or counts.get("tests") != len(passed) or counts.get("pass") != len(passed)
                or counts.get("skipped") != 0 or counts.get("todo") != 0):
            raise ValueError("Fresh Node test results differ from the graph. See evidence/node-tests.tap.")
        results["fresh_node_tests"] = len(passed)
        browser_checks = {check for node in test_nodes if node["source"] == "evidence/browser.json"
                          for check in node["check_ids"]}
        results["browser_evidence"] = verify_browser_receipt(out, browser_checks)
        step("strict-local", graph + ["validate", "graph.json", "--strict-local"], "validate.txt")
        step("render", graph + ["render", "graph.json", "--strict-local", "--out-dir", "rendered"], "render.txt")
        step("snapshot", ssot + ["snapshot", "--scope", "local-only", "--brief", "brief.md",
                                 "--graph", "graph.json", "--bindings", "bindings.json",
                                 "--out", "manifest-001.json"], "snapshot.json")
        step("check", ssot + ["check", "manifest-001.json"], "ssot-check.json")
        step("trace", python + [SCRIPTS / "trace_report.py", "graph.json", "--check", "ssot-check.json",
                                "--out", "trace.html"], "trace.txt")
        results["status"] = "passed"
    except (OSError, ValueError, KeyError, TypeError) as error:
        results.update(status="failed", error=str(error))
        raise
    finally:
        save_json(out / "run.json", results)
    print(f"Local checks passed. Open {out / 'trace.html'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="new directory for the project, evidence and graph")
    try:
        run_example(parser.parse_args().out)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")
