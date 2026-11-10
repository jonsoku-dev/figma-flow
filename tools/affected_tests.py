#!/usr/bin/env python3
"""Plan declared graph impacts and optionally run explicitly mapped Node tests.

Mapping: {"version":1,"tests":{"TEST-001":["tests/example.test.js"]}}.
Output directory must not exist. A plan is content evidence, not semantic proof.
"""
import argparse
import json
from collections import deque
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/figma-flow/scripts"))
import ssot
import safe_node_tests
import audit_project


def sha(path):
    return ssot.read_local(path)[0]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--project", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--spec", action="append", default=[], help="Additional active requirement documents inside project")
    parser.add_argument("--review", help="Optional pinned semantic-review candidates")
    parser.add_argument("--all", action="store_true", help="Select all mapped graph tests")
    args = parser.parse_args(argv)
    out = Path(args.out).absolute()
    created = False
    try:
        out = out.resolve()
        if out.exists():
            raise ValueError("Output directory already exists")
        root = Path(args.project).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Project must be a directory")
        manifest_path = Path(args.manifest).resolve(strict=True)
        mapping_path = Path(args.mapping).resolve(strict=True)
        if not mapping_path.is_relative_to(root):
            raise ValueError("Mapping must be inside the project")
        manifest_sha, manifest_bytes = ssot.read_local(manifest_path, capture=True)
        baseline = json.loads(manifest_bytes)
        ssot.validate_manifest(baseline)
        check = subprocess.run([sys.executable, str(Path(ssot.__file__)), "check", str(manifest_path)], capture_output=True, text=True)
        if check.returncode not in (0, 2):
            raise ValueError("SSOT check failed: " + check.stderr.strip())
        report = json.loads(check.stdout)
        if report["unavailable_authorities"] or report["changed_review_pins"]:
            raise ValueError("Required authority or review proof unavailable or changed")
        for node in report["nodes"].values():
            if not node["evidence"] or any(r["availability"] != "local-hashed" for r in node["evidence"]):
                raise ValueError("Node evidence missing or unavailable")
        graph_path = (manifest_path.parent / baseline["inputs"]["graph"]["path"]).resolve(strict=True)
        graph_sha, graph_bytes = ssot.read_local(graph_path, capture=True)
        graph = json.loads(graph_bytes)
        if sha(manifest_path) != manifest_sha or graph_sha != report['inputs']['graph']['sha256']:
            raise ValueError("Manifest or graph drifted during SSOT check")
        audit = audit_project.audit_project(root, graph_path,
                    manifest_path.parent / baseline['inputs']['bindings']['path'],
                    manifest_path.parent / baseline['inputs']['brief']['path'], args.spec, project_only=False, review=args.review)
        if audit['inputs'].get(audit_project.input_name(root, graph_path)) != graph_sha:
            raise ValueError('Graph drifted during audit')
        source_audit = audit['source_dependencies']
        source_fallback = bool(source_audit['missing'] or source_audit['candidates'] or source_audit['unknown'])
        acceptance_blocked = audit['acceptance_claim'] == 'blocked-by-active-contradiction'
        mapping_sha, mapping_bytes = ssot.read_local(mapping_path, capture=True)
        mapping = json.loads(mapping_bytes)
        if not isinstance(mapping, dict) or not {"version", "tests"} <= set(mapping) or set(mapping) - {"version", "tests", "inputs"} or type(mapping["version"]) is not int or mapping["version"] != 1 or not isinstance(mapping["tests"], dict):
            raise ValueError("Invalid mapping schema")
        types = {n["id"]: n["type"] for n in graph["nodes"]}
        test_ids = {n for n, t in types.items() if t == "test"}
        if not test_ids or set(mapping["tests"]) != test_ids:
            raise ValueError("Mapping must cover exactly all graph test IDs")
        mapped = {}
        for test_id, names in mapping["tests"].items():
            if not isinstance(names, list) or not names or any(not isinstance(x, str) or not x or Path(x).is_absolute() for x in names):
                raise ValueError("Each test must map to nonempty relative file paths")
            files = []
            for name in names:
                path = (root / name).resolve(strict=True)
                if not path.is_relative_to(root) or not path.is_file() or path.suffix not in (".js", ".mjs", ".cjs"):
                    raise ValueError("Test file must be a local JavaScript file inside project")
                evidence_paths = {(manifest_path.parent / ref['path']).resolve() for ref in report['nodes'][test_id]['evidence'] if ref['availability'] == 'local-hashed'}
                if path not in evidence_paths:
                    raise ValueError("Mapped test file must be declared as evidence for " + test_id)
                files.append(path)
            mapped[test_id] = files
        extra = mapping.get('inputs', [])
        if not isinstance(extra, list) or any(not isinstance(x, str) or not x or Path(x).is_absolute() for x in extra):
            raise ValueError("Mapping inputs must be relative paths")
        extra_paths = {(root / name).resolve(strict=True) for name in extra}
        if any(not p.is_relative_to(root) or not p.is_file() for p in extra_paths):
            raise ValueError("Mapping inputs must be files inside project")
        refs = list(report['inputs'].values()) + list(report['authorities'].values()) + [r for n in report['nodes'].values() for r in n['evidence']] + baseline.get('review_pins', [])
        files_to_pin = {manifest_path, mapping_path, graph_path} | extra_paths | {p for files in mapped.values() for p in files}
        files_to_pin.update(root / name for name in audit['inputs'])
        files_to_pin.update((manifest_path.parent / ref['path']).resolve(strict=True) for ref in refs if ref['availability'] == 'local-hashed')
        if any(p == out or p.is_relative_to(out) for p in files_to_pin):
            raise ValueError("Output directory overlaps a declared input")
        for ref in refs:
            if ref['availability'] == 'local-hashed' and sha((manifest_path.parent / ref['path']).resolve(strict=True)) != ref['sha256']:
                raise ValueError("Declared inputs drifted during planning")
        if any(sha(root / name) != digest for name, digest in audit['inputs'].items()):
            raise ValueError('Audit inputs drifted during planning')
        recheck = subprocess.run([sys.executable, str(Path(ssot.__file__)), "check", str(manifest_path)], capture_output=True, text=True)
        if recheck.returncode not in (0, 2) or json.loads(recheck.stdout) != report or sha(mapping_path) != mapping_sha or sha(manifest_path) != manifest_sha:
            raise ValueError("Inputs drifted during planning")
        out.mkdir(parents=False, exist_ok=False)
        created = True
        explanation = report["change_explanation"]
        direct = explanation["direct_nodes"]
        seeds = set(direct)
        adjacency, current_adj = {}, {}
        for edge in explanation["dependency_edges"]:
            adjacency.setdefault(edge["from"], []).append((edge["to"], edge["type"], 'ssot-dependency', edge['presence']))
            if edge['presence'] != 'previous-only':
                current_adj.setdefault(edge['from'], []).append(edge['to'])
        nodes = {node['id']: node for node in graph['nodes']}
        coverage_edges = []
        for edge in graph['edges']:
            if edge['type'] != 'checked by':
                continue
            source, target = edge['from'], edge['to']
            if types.get(source) not in ('acceptance', 'code') or types.get(target) != 'test' or nodes[target]['status'] != 'verified':
                raise ValueError('checked by must connect acceptance or code to a verified test')
            coverage_edges.append(edge)
            adjacency.setdefault(source, []).append((target, edge['type'], 'current-test-coverage', 'current-only'))
            current_adj.setdefault(source, []).append(target)
        paths = {seed: [seed] for seed in sorted(seeds)}
        path_edges = {seed: [] for seed in sorted(seeds)}
        queue = deque(paths)
        while queue:
            source = queue.popleft()
            for target, edge_type, meaning, presence in sorted(adjacency.get(source, []), key=lambda edge: (edge[0], edge[2] != 'ssot-dependency', edge[1], edge[3])):
                if target not in paths:
                    paths[target] = paths[source] + [target]
                    path_edges[target] = path_edges[source] + [{'from': source, 'to': target, 'type': edge_type, 'meaning': meaning, 'presence': presence}]
                    queue.append(target)
        changed_inputs = {item['key'] for item in explanation['changed_inputs']}
        binding_change = explanation.get('bindings_change')
        scoped_binding = (isinstance(binding_change, dict)
                          and binding_change.get('scope') == 'scoped-evidence'
                          and binding_change.get('policy_hash_matches') is True)
        global_change = (bool(explanation["changed_authorities"]) or 'brief' in changed_inputs
                         or ('bindings' in changed_inputs and not scoped_binding))
        # A seed with no declared route to a test, or an isolated test, cannot safely narrow coverage.
        reverse = {}
        for source, targets in current_adj.items():
            for target in targets:
                reverse.setdefault(target, []).append(source)
        can_reach, pending = set(test_ids), deque(test_ids)
        while pending:
            for source in reverse.get(pending.popleft(), []):
                if source not in can_reach:
                    can_reach.add(source)
                    pending.append(source)
        def complete_branches(seed):
            seen, pending = {seed}, deque([seed])
            while pending:
                node = pending.popleft()
                if node not in can_reach:
                    return False
                if node in test_ids:
                    continue
                targets = current_adj.get(node, [])
                if not targets:
                    return False
                for target in targets:
                    if target not in seen:
                        seen.add(target)
                        pending.append(target)
            return bool(seen & test_ids)
        incoming = {target for targets in current_adj.values() for target in targets}
        fallback = bool(seeds) and (any(not complete_branches(seed) for seed in seeds) or bool(test_ids - incoming))
        graph_fallback = fallback
        fallback = graph_fallback or source_fallback or acceptance_blocked
        broad = args.all or global_change or fallback
        selected = sorted(test_ids if broad else test_ids & paths.keys())
        selected_files = {p for key in selected for p in mapped[key]}
        executed_ids = {key for key in test_ids if selected_files.intersection(mapped[key])}
        reasons = {node: {"type": types.get(node, "removed"), "path": path, "path_edges": path_edges[node],
                          "reason": direct.get(path[0], {}).get("categories", [])}
                   for node, path in sorted(paths.items())}
        plan = {"baseline_manifest_sha256": baseline["manifest_sha256"], "scope": "all" if broad else "declared-paths", "fallback": fallback,
                "global_change": global_change, "impacted": reasons, "selected_tests": selected,
                "bindings_change": binding_change, "source_audit_fallback": source_fallback, "graph_fallback": graph_fallback,
                "audit_status": audit['status'], "acceptance_claim": audit['acceptance_claim'],
                "shared_file_test_ids": sorted(executed_ids - set(selected)),
                "partial_file_test_ids": sorted(key for key in executed_ids if not set(mapped[key]) <= selected_files),
                "excluded_tests": sorted(test_ids - executed_ids), "excluded_count": len(test_ids - executed_ids),
                "files": {key: [str(p.relative_to(root)) for p in mapped[key]] for key in selected},
                "limitation": "SSOT dependency paths and current checked-by coverage select tests; source findings or unknowns and active contradictions conservatively select all tests; checked-by does not itself assert SSOT staleness. Local hashes and declarations do not prove semantic correctness or graph completeness."}
        write(out / "audit.json", audit)
        (out / 'audit.md').write_text(audit_project.markdown(audit), encoding='utf-8')
        write(out / "plan.json", plan)
        if not args.run:
            return 1 if acceptance_blocked else 0
        if not selected:
            raise ValueError("No runnable tests selected")
        # Audit-read files join declared SSOT inputs in drift detection.
        def pins():
            return {str(p): sha(p) for p in sorted(files_to_pin)}
        before = pins()
        if any(before[str(root / name)] != digest for name, digest in audit['inputs'].items()):
            raise ValueError('Audit inputs drifted during planning')
        if before[str(manifest_path)] != manifest_sha or before[str(mapping_path)] != mapping_sha or before[str(graph_path)] != report['inputs']['graph']['sha256']:
            raise ValueError("Manifest, mapping or graph drifted during planning")
        def current_check():
            result = subprocess.run([sys.executable, str(Path(ssot.__file__)), "check", str(manifest_path)], capture_output=True, text=True)
            if result.returncode not in (0, 2):
                raise ValueError("SSOT check failed during execution")
            return json.loads(result.stdout)
        if current_check() != report:
            raise ValueError("Inputs drifted during planning")
        run_result = {"tests": [], "sandbox": {}}
        execution_error = None
        try:
            run_result = safe_node_tests.run_tests(root, [str(p.relative_to(root)) for p in sorted(selected_files)], out / 'node-tests')
        except safe_node_tests.TestRunError as exc:
            run_result, execution_error = exc.results, str(exc)
        except (OSError, ValueError) as exc:
            execution_error = str(exc)
        try:
            after = pins()
            drift = before != after or current_check() != report
            post_error = None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            after, drift, post_error = {}, True, str(exc)
        test_hashes_match = all(before.get(str(root / item['file'])) == item['sha256'] for item in run_result['tests'])
        success = not drift and test_hashes_match and execution_error is None and len(run_result['tests']) == len(selected_files)
        write(out / "receipt.json", {"result": "passed" if success and not acceptance_blocked else "failed", "test_result": "passed" if success else "failed", "acceptance_claim": audit['acceptance_claim'], "drift_scope": "Declared SSOT files, audit-read sources and specs, mapping, all mapped test files, and optional mapping inputs; unresolved runtime dependencies are not tracked.", "inputs_before": before, "inputs_after": after, "drift": drift, "test_hashes_match": test_hashes_match, "post_check_error": post_error, "execution_error": execution_error, "receipt_directory": "node-tests", "sandbox": run_result['sandbox'], "tests": run_result['tests']})
        return 0 if success and not acceptance_blocked else 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        if created and not (out / "receipt.json").exists():
            write(out / "error.json", {"error": str(exc)})
        print("Error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
