#!/usr/bin/env python3
"""Pin local SSOT inputs and report content freshness, never semantic verification.

Bindings v1: {"version":1,"authorities":{"intent":"brief.md",
"visual":"https://www.figma.com/...","implementation":"app.py"},
"dependency_edge_types":["depends-on"],"evidence":{"SCR-001":["spec.md"]}}.
Bindings paths are relative to the bindings file. Selected graph edges point from
upstream input to dependent output; navigation edges are not inferred dependencies.
Remote URLs are recorded but never fetched or checked. Snapshots are immutable.
Graph source paths are relative to the graph file. A snapshot without --previous
starts independent history and is never evidence revalidation. Reviewed reconciliation records a human decision, not semantic verification.
Run check on the prior manifest and prepare review JSON with exactly:
{"previous_manifest_sha256":"<prior manifest hash>",
 "current_state_sha256":"<check review_target_sha256>",
 "affected_ids":["<each check review_affected_ids item in order>"],
 "evidence":"<local file relative to review JSON>",
 "evidence_sha256":"<SHA-256 of reviewed evidence file>", "review_note":"<human judgment>"}.
Then use snapshot --previous PRIOR --review REVIEW --out NEW with the same inputs.
Revisions pin review and evidence files; changes to either invalidate later checks.
New manifests pin bindings_policy_sha256 over all binding fields except evidence.
Matching policy pins and unchanged authorities scope evidence edits to their nodes
and declared dependents. Legacy manifests without that pin remain conservative;
their review targets omit the new field so existing v0.4 reviews remain usable.
Local-only scope permits omitted or remote visual authority, but remote evidence
and missing local files never count as checked; Figma state remains unchecked.
"""

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

import graph


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read_local(path, capture=False):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Only regular local files can be hashed.")
        hasher = hashlib.sha256()
        chunks = [] if capture else None
        with os.fdopen(fd, "rb", closefd=False) as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                if capture:
                    chunks.append(chunk)
        return hasher.hexdigest(), b"".join(chunks) if capture else None
    finally:
        os.close(fd)


def read_json(path):
    _, content = read_local(path, capture=True)
    return json.loads(content.decode("utf-8"))


def reference(value, base, output_base):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("References must be nonempty strings.")
    if urlsplit(value).scheme:
        return {"path": value, "availability": "remote-unchecked", "sha256": None}
    path = (base / value.split("#", 1)[0]).absolute()
    item = {"path": os.path.relpath(path, output_base), "availability": "missing", "sha256": None}
    try:
        item["sha256"], _ = read_local(path)
        item["availability"] = "local-hashed"
    except (OSError, ValueError):
        pass
    return item


def read_input(path, output_base):
    path = Path(path).absolute()
    sha, content = read_local(path, capture=True)
    return json.loads(content.decode("utf-8")), {"path": os.path.relpath(path, output_base),
                                                "availability": "local-hashed", "sha256": sha}


def graph_fingerprints(data):
    """Return the existing content fingerprint for each node in a validated graph."""
    incident = {node["id"]: [] for node in data["nodes"]}
    for edge in data["edges"]:
        for node_id in {edge["from"], edge["to"]}:
            incident[node_id].append(edge)
    metadata = {key: value for key, value in data.items() if key not in ("nodes", "edges")}
    return {node["id"]: digest({"node": node, "graph_metadata": metadata,
                                "edges": sorted(incident[node["id"]], key=lambda edge: json.dumps(edge, sort_keys=True))})
            for node in data["nodes"]}


def build(brief_path, graph_path, bindings_path, output_base, scope="full"):
    cache = {}
    def pin(value, base):
        key = (value, str(base))
        if key not in cache:
            cache[key] = reference(value, base, output_base)
        return cache[key]
    data, graph_ref = read_input(graph_path, output_base)
    errors, _ = graph.validate_graph(data)
    if errors:
        raise ValueError("Invalid graph: " + "; ".join(errors))
    bindings, bindings_ref = read_input(bindings_path, output_base)
    if not isinstance(bindings, dict) or type(bindings.get("version")) is not int or bindings["version"] != 1:
        raise ValueError("Bindings version must be integer 1.")
    authorities = bindings.get("authorities")
    if (not isinstance(authorities, dict) or not {"intent", "implementation"} <= set(authorities)
            or set(authorities) - {"intent", "visual", "implementation"}
            or (scope == "full" and "visual" not in authorities)):
        raise ValueError("authorities must declare intent and implementation; full scope also requires visual.")
    edge_types = bindings.get("dependency_edge_types")
    if not isinstance(edge_types, list) or any(not isinstance(v, str) or not v.strip() for v in edge_types):
        raise ValueError("dependency_edge_types must be an array of nonempty edge type strings.")
    evidence = bindings.get("evidence", {})
    ids = {node["id"] for node in data["nodes"]}
    if not isinstance(evidence, dict) or set(evidence) - ids:
        raise ValueError("evidence must map existing graph node IDs to reference arrays.")
    for refs in evidence.values():
        if not isinstance(refs, list):
            raise ValueError("Each evidence entry must be an array of references.")
    base = Path(bindings_path).absolute().parent
    pinned_authorities = {key: pin(value, base) for key, value in sorted(authorities.items())}
    brief = reference(str(Path(brief_path).absolute()), Path.cwd(), output_base)
    intent_path = output_base / pinned_authorities["intent"]["path"]
    brief_locator = output_base / brief["path"]
    same_intent = pinned_authorities["intent"]["path"] == brief["path"]
    if pinned_authorities["intent"]["availability"] == "local-hashed" and brief["availability"] == "local-hashed":
        same_intent = intent_path.samefile(brief_locator)
    if not same_intent:
        raise ValueError("intent authority must reference the supplied requirement brief.")
    if brief["availability"] != "local-hashed":
        raise ValueError("Requirement brief must be a readable local file.")
    dependencies = sorted([edge for edge in data["edges"] if edge["type"] in edge_types], key=lambda edge: (edge["from"], edge["to"], edge["type"]))
    fingerprints = graph_fingerprints(data)
    nodes = {}
    for node in sorted(data["nodes"], key=lambda node: node["id"]):
        refs = [pin(ref, base) for ref in sorted(set(evidence.get(node["id"], [])))]
        if node.get("source"):
            refs.append(pin(node["source"], Path(graph_path).absolute().parent))
        nodes[node["id"]] = {
            "type": node["type"],
            "content_sha256": fingerprints[node["id"]],
            "evidence": sorted(refs, key=lambda ref: ref["path"]),
        }
    return {"version": 1, "classification": "Content freshness only; hashes and declarations do not verify truth, test success, or Figma state.",
            "inputs": {"brief": brief, "graph": graph_ref,
                       "bindings": bindings_ref},
            "bindings_policy_sha256": digest({key: value for key, value in bindings.items() if key != "evidence"}),
            "authorities": pinned_authorities, "dependencies": dependencies, "nodes": nodes}


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or type(manifest.get("revision")) is not int or manifest["revision"] < 1:
        raise ValueError("Invalid SSOT manifest version or revision.")
    expected = manifest.get("manifest_sha256")
    if expected != digest({key: value for key, value in manifest.items() if key != "manifest_sha256"}):
        raise ValueError("Manifest integrity mismatch; use an unchanged snapshot.")


def bindings_change(current, previous):
    """Scope binding edits only when both snapshots explicitly pin equal policy."""
    policy_hash = current.get("bindings_policy_sha256")
    matches = bool(policy_hash) and policy_hash == previous.get("bindings_policy_sha256")
    if current["authorities"] != previous["authorities"]:
        scope, reason = "broad", "authorities-changed"
    elif current["inputs"]["bindings"] == previous["inputs"]["bindings"]:
        scope, reason = "none", "bindings-unchanged"
    elif matches:
        scope, reason = "scoped-evidence", "binding-policy-unchanged"
    else:
        scope, reason = "broad", "binding-policy-changed-or-unpinned"
    return {"scope": scope, "policy_hash_matches": matches, "reason": reason}


def compare(current, previous):
    reasons = {node_id: [] for node_id in current["nodes"]}
    removed = []
    if previous:
        old = previous["nodes"]
        removed = sorted(set(previous.get("removed_nodes", [])) | (set(old) - set(current["nodes"])))
        for node_id, node in current["nodes"].items():
            if node_id not in old or node != {key: value for key, value in old[node_id].items() if key not in ("freshness", "reasons")}:
                reasons[node_id].append("node-or-evidence-changed")
            if old.get(node_id, {}).get("freshness") == "stale":
                reasons[node_id].append("previously-stale")
        if current["inputs"]["brief"] != previous["inputs"]["brief"]:
            for node_id, node in current["nodes"].items():
                if node["type"] == "requirement":
                    reasons[node_id].append("brief-changed")
        if bindings_change(current, previous)["scope"] == "broad":
            for node_id in reasons:
                reasons[node_id].append("authority-or-bindings-changed")
        # Removed edges still invalidate their former dependents.
        dependencies = previous["dependencies"] + current["dependencies"]
    else:
        dependencies = current["dependencies"]
    adjacency = {}
    for edge in dependencies:
        adjacency.setdefault(edge["from"], set()).add(edge["to"])
    pending = [node_id for node_id, values in reasons.items() if values] + removed
    seen = set(pending)
    while pending:
        upstream = pending.pop()
        for downstream in adjacency.get(upstream, ()):
            if downstream in reasons and downstream not in seen:
                seen.add(downstream)
                reasons[downstream].append("upstream-stale")
                pending.append(downstream)
    for node_id, node in current["nodes"].items():
        unavailable = not node["evidence"] or any(ref["availability"] != "local-hashed" for ref in node["evidence"])
        node["freshness"] = "stale" if reasons[node_id] else "unverified" if unavailable else "content-current"
        node["reasons"] = sorted(reasons[node_id])
    current["removed_nodes"] = removed
    current["changed_inputs"] = sorted(key for key in current["inputs"] if previous and current["inputs"][key] != previous["inputs"][key])
    return current


def change_explanation(current, previous):
    """Explain hash deltas and one shortest declared dependency route, without claims."""
    old, new = previous["nodes"], current["nodes"]

    def reference_changes(before, after):
        return [{"key": key, "previous": before.get(key), "current": after.get(key)}
                for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]

    direct = {}
    for node_id in sorted(set(old) | set(new) | set(current["removed_nodes"])):
        before, after = old.get(node_id), new.get(node_id)
        categories = []
        if before is None and after is not None:
            categories.append("added")
        if after is None:
            categories.append("removed")
        if before and after and before["content_sha256"] != after["content_sha256"]:
            categories.append("node-or-incident-graph-changed")
        old_refs = {ref["path"]: ref for ref in (before or {}).get("evidence", [])}
        new_refs = {ref["path"]: ref for ref in (after or {}).get("evidence", [])}
        evidence = [{"path": item["key"], "previous": item["previous"], "current": item["current"]}
                    for item in reference_changes(old_refs, new_refs)]
        if evidence:
            categories.append("evidence-changed")
        if before and after and before.get("freshness") == "stale":
            categories.append("prior-stale-unresolved")
        if categories:
            direct[node_id] = {"categories": categories,
                               "previous_content_sha256": (before or {}).get("content_sha256"),
                               "current_content_sha256": (after or {}).get("content_sha256"),
                               "evidence_changes": evidence,
                               "historic_only": before is None and after is None}

    def edge_keys(state):
        return {(edge["from"], edge["to"], edge["type"]) for edge in state["dependencies"]}

    old_edges, new_edges = edge_keys(previous), edge_keys(current)
    common_edges = old_edges & new_edges
    edges = [{"from": source, "to": target, "type": kind,
              "presence": "both" if (source, target, kind) in common_edges else
              "previous-only" if (source, target, kind) in old_edges else "current-only"}
             for source, target, kind in sorted(old_edges | new_edges)]
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], []).append(edge)
    inputs = reference_changes(previous["inputs"], current["inputs"])
    authorities = reference_changes(previous["authorities"], current["authorities"])
    binding_edit = bindings_change(current, previous)
    global_change = binding_edit["scope"] == "broad"
    brief_change = any(item["key"] == "brief" for item in inputs)
    seeds = {}
    for node_id, node in direct.items():
        categories = node["categories"]
        seeds[node_id] = ("historic-only-unknown" if node["historic_only"] else
                          "prior-stale-unresolved" if categories == ["prior-stale-unresolved"] else "direct-change")
    for node_id, node in sorted(new.items()):
        if node_id not in seeds and node["freshness"] == "stale":
            if global_change:
                seeds[node_id] = "authority-or-bindings-changed"
            elif brief_change and node["type"] == "requirement":
                seeds[node_id] = "brief-changed"
    propagation = {node_id: {"root_id": node_id, "predecessor_id": None, "distance": 0,
                             "edge": None, "root_kind": seeds[node_id]}
                   for node_id in sorted(seeds)}
    pending = deque(propagation)
    while pending:
        source = pending.popleft()
        parent = propagation[source]
        for edge in adjacency.get(source, []):
            target = edge["to"]
            if target in propagation or target not in new or new[target]["freshness"] != "stale":
                continue
            propagation[target] = {"root_id": parent["root_id"], "predecessor_id": source,
                                   "distance": parent["distance"] + 1, "edge": edge,
                                   "root_kind": parent["root_kind"]}
            pending.append(target)
    return {"version": 1, "baseline_manifest_sha256": previous["manifest_sha256"],
            "limitation": "Hash deltas only, not semantic changes or verified causes. One shortest declared dependency route is selected; ties use sorted root IDs and edges. Prior staleness has no recoverable original cause in this baseline.",
            "direct_nodes": direct, "changed_inputs": inputs, "changed_authorities": authorities,
            "bindings_change": binding_edit,
            "dependency_edges": edges, "propagation": propagation}


def review_target(current, previous=None):
    affected = sorted(set(current["removed_nodes"]) | {
        node_id for node_id, node in current["nodes"].items() if node["freshness"] == "stale"
    })
    # v0.4 targets did not include the new policy pin; preserve exact review hashes.
    target = ({key: value for key, value in current.items() if key != "bindings_policy_sha256"}
              if previous is not None and "bindings_policy_sha256" not in previous else current)
    return digest(target), affected


def reconcile(current, previous, review_path, base):
    review, review_ref = read_input(review_path, base)
    target, affected = review_target(current, previous)
    if not isinstance(review, dict) or set(review) != {
            "previous_manifest_sha256", "current_state_sha256", "affected_ids", "evidence", "evidence_sha256", "review_note"}:
        raise ValueError("Review must contain exactly previous_manifest_sha256, current_state_sha256, affected_ids, evidence, evidence_sha256 and review_note.")
    if (not affected or review["previous_manifest_sha256"] != previous["manifest_sha256"]
            or review["current_state_sha256"] != target or review["affected_ids"] != affected):
        raise ValueError("Review does not match the previous manifest, exact current state and affected IDs.")
    if not isinstance(review["review_note"], str) or not review["review_note"].strip():
        raise ValueError("Review requires a nonempty human review_note.")
    evidence_ref = reference(review["evidence"], Path(review_path).absolute().parent, base)
    if review_ref["availability"] != "local-hashed" or evidence_ref["availability"] != "local-hashed":
        raise ValueError("Review and review evidence must be readable local files.")
    if review["evidence_sha256"] != evidence_ref["sha256"]:
        raise ValueError("Review evidence SHA-256 does not match the reviewed file.")
    for node in current["nodes"].values():
        if node["freshness"] == "stale":
            node["freshness"] = "unverified" if not node["evidence"] or any(
                ref["availability"] != "local-hashed" for ref in node["evidence"]) else "content-current"
            node["reasons"] = []
    current["removed_nodes"] = []
    current["reconciliation"] = {"review": review_ref, "evidence": evidence_ref,
                                 "previous_manifest_sha256": previous["manifest_sha256"],
                                 "current_state_sha256": target, "affected_ids": affected,
                                 "review_note": review["review_note"],
                                 "limitation": "Human review is recorded, not independently verified; remote state remains unchecked."}
    return current


def changed_review_pins(manifest, base):
    return [ref["path"] for ref in manifest.get("review_pins", [])
            if reference(ref["path"], base, base) != ref]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="Write a NEW immutable manifest; never validate or clear previous staleness.")
    for flag in ("brief", "graph", "bindings", "out"):
        snapshot.add_argument("--" + flag, required=True, help="Local path" + (" (must not exist)" if flag == "out" else ""))
    snapshot.add_argument("--previous", help="Previous immutable manifest; carries unresolved staleness forward.")
    snapshot.add_argument("--scope", choices=("full", "local-only"), help="Explicit local-only permits omitted or remote visual authority; remote evidence remains unchecked. Inherited from previous revision.")
    snapshot.add_argument("--review", help="Review JSON for the exact previous manifest and state; see check output for target and affected IDs. Requires --previous.")
    check = commands.add_parser("check", help="Read inputs again; JSON to stdout; exit 2 if stale/unavailable, 0 if content-current.")
    check.add_argument("manifest")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            output = Path(args.out).absolute().parent
            previous = read_json(args.previous) if args.previous is not None else None
            if args.previous is not None:
                validate_manifest(previous)
                if Path(args.previous).absolute().parent != output:
                    raise ValueError("Keep revisions in the same directory so relative references remain stable.")
            if previous and changed_review_pins(previous, output):
                raise ValueError("Previous review or review evidence changed or is unavailable.")
            if args.review and not previous:
                raise ValueError("--review requires --previous.")
            previous_scope = previous.get("scope", "full") if previous else None
            scope = args.scope or previous_scope or "full"
            if previous and scope != previous_scope:
                raise ValueError("Scope cannot change within a revision chain.")
            current = compare(build(args.brief, args.graph, args.bindings, output, scope), previous)
            if scope == "local-only":
                current["scope"] = scope
            if args.review:
                current = reconcile(current, previous, args.review, output)
            pins = list(previous.get("review_pins", [])) if previous else []
            if args.review:
                pins.extend([current["reconciliation"]["review"], current["reconciliation"]["evidence"]])
            if pins:
                current["review_pins"] = pins
            current.update(revision=previous["revision"] + 1 if previous else 1,
                           parent_sha256=previous["manifest_sha256"] if previous else None)
            current["manifest_sha256"] = digest(current)
            graph._write_exclusive(Path(args.out), json.dumps(current, ensure_ascii=True, sort_keys=True, indent=2) + "\n")
            print(json.dumps({"manifest": str(args.out), "revision": current["revision"], "manifest_sha256": current["manifest_sha256"]}))
            return 0
        previous = read_json(args.manifest)
        validate_manifest(previous)
        base = Path(args.manifest).absolute().parent
        inputs = {key: base / ref["path"] for key, ref in previous["inputs"].items()}
        scope = previous.get("scope", "full")
        if scope not in ("full", "local-only"):
            raise ValueError("Invalid scope in manifest.")
        current = compare(build(inputs["brief"], inputs["graph"], inputs["bindings"], base, scope), previous)
        if scope == "local-only":
            current["scope"] = scope
        target, affected = review_target(current, previous)
        current["change_explanation"] = change_explanation(current, previous)
        current["review_target_sha256"] = target
        current["review_affected_ids"] = affected
        current["review_requirements"] = "Human judgment of all affected IDs, including removals, remains necessary; remote state is unchecked."
        unavailable = [key for key, ref in current["authorities"].items()
                       if ref["availability"] != "local-hashed" and not
                       (scope == "local-only" and key == "visual" and ref["availability"] == "remote-unchecked")]
        if scope == "local-only":
            current["scope_limitation"] = "Local content freshness only; visual authority and remote state are not verified."
        current["unavailable_authorities"] = unavailable
        current["changed_review_pins"] = changed_review_pins(previous, base)
        print(json.dumps(current, ensure_ascii=True, sort_keys=True, indent=2))
        return 2 if unavailable or current["changed_review_pins"] or current["removed_nodes"] or current["changed_inputs"] or any(node["freshness"] != "content-current" for node in current["nodes"].values()) else 0
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
