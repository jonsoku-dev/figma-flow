"""Audit registered feature graphs against the repository's graph-root registry.

Checks are structural and local. They do not infer meaning from prose or promote
declared evidence to runtime acceptance.
"""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse


ROOT_REGISTRY = Path("specs/graph-roots.json")
GRAPH_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "skills/figma-flow/scripts/graph.py"
_graph_spec = importlib.util.spec_from_file_location("figma_flow_graph_contract", GRAPH_CONTRACT_PATH)
if _graph_spec is None or _graph_spec.loader is None:
    raise ImportError(f"Cannot load graph contract constants from {GRAPH_CONTRACT_PATH}")
_graph_contract = importlib.util.module_from_spec(_graph_spec)
_graph_spec.loader.exec_module(_graph_contract)
NODE_TYPES = _graph_contract.NODE_TYPES
STATUSES = _graph_contract.STATUSES
REQUIRED_NODE_FIELDS = _graph_contract.REQUIRED_NODE_FIELDS
REQUIRED_EDGE_FIELDS = _graph_contract.REQUIRED_EDGE_FIELDS
DECLARED_ID = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*|`)?((?:REQ|AC)-[A-Z0-9][A-Z0-9_-]*)(?:\*\*|`)?\s*(?:[—–:|])")
# Canonical relationships whose direction and endpoint types are defined by
# skills/figma-flow/references/graph-contract.md. Unknown legacy labels remain
# usable as trace edges; they are not interpreted as evidence links.
TYPED_EDGES = {
    "informs": ({"reference"}, {"requirement"}),
    "appears on": ({"requirement"}, {"screen"}),
    "accepted by": ({"requirement"}, {"acceptance"}),
    # Existing graph-review uses this explicit legacy equivalent.
    "has acceptance criterion": ({"requirement"}, {"acceptance"}),
    "has state": ({"screen"}, {"state"}),
    "triggers": ({"screen"}, {"action"}),
    "navigates to": ({"action"}, {"screen", "state"}),
    "represented by": ({"screen", "state", "action"}, {"figma"}),
    "implemented by": ({"screen", "state", "action", "requirement"}, {"code"}),
    "checked by": ({"acceptance", "code"}, {"test"}),
    "verified by": ({"acceptance", "code"}, {"test"}),
}


def _finding(code: str, path: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "path": path, "message": message, **extra}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_target(root: Path, graph_dir: Path, source: str) -> tuple[str, Path | None]:
    """Return source kind and safe local target; do not fetch external URLs."""
    parsed = urlparse(source)
    if parsed.scheme in {"https", "http"} and parsed.netloc:
        return "external", None
    if parsed.scheme or source.startswith(("//", "\\\\")):
        return "unsupported", None
    path_part = source.split("#", 1)[0]
    if not path_part:
        return "unsupported", None
    target = (graph_dir / path_part).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return "escape", target
    return "local", target


def check(root: str | Path) -> list[dict[str, Any]]:
    """Return blockers and explicitly non-blocking unresolved references."""
    root = Path(root).resolve()
    registry_path = root / ROOT_REGISTRY
    findings: list[dict[str, Any]] = []
    if not (root / "specs").is_dir():
        return [_finding("missing-specs-root", "specs", "Registered specs directory is missing")]
    try:
        registry = _load(registry_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [_finding("invalid-root-registry", ROOT_REGISTRY.as_posix(), str(exc))]
    if not isinstance(registry, dict) or registry.get("version") != 1 or not isinstance(registry.get("roots"), list):
        return [_finding("unsupported-root-registry", ROOT_REGISTRY.as_posix(), "Expected version 1 object with roots array")]
    readme = root / "specs/README.md"
    if not readme.is_file() or "[graph-roots.json](graph-roots.json)" not in readme.read_text(encoding="utf-8"):
        findings.append(_finding("registry-not-indexed", "specs/README.md", "README must link the authoritative graph-roots.json registry"))
    if not registry["roots"]:
        findings.append(_finding("empty-root-registry", ROOT_REGISTRY.as_posix(), "Registry must retain at least one required graph root"))
    registered: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(registry["roots"]):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("role"), str):
            findings.append(_finding("invalid-root-entry", ROOT_REGISTRY.as_posix(), f"Root entry {i} needs path and role")); continue
        rel = Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.parts[:1] != ("specs",) or rel.name != "graph.json":
            findings.append(_finding("unsafe-root-entry", ROOT_REGISTRY.as_posix(), f"Invalid repository graph path {item['path']!r}")); continue
        key = rel.as_posix()
        if key in registered:
            findings.append(_finding("duplicate-root-entry", ROOT_REGISTRY.as_posix(), f"Duplicate registered graph {key}"))
        registered[key] = item
    actual = {p.relative_to(root).as_posix() for p in (root / "specs").glob("*/graph.json")} if (root / "specs").is_dir() else set()
    for key in sorted(set(registered) - actual):
        findings.append(_finding("registered-graph-missing", key, "Registered canonical graph is missing"))
    for key in sorted(actual - set(registered)):
        findings.append(_finding("unregistered-graph", key, "Graph exists but is absent from the authoritative root registry"))

    for key, registration in sorted(registered.items()):
        graph_path = root / key
        if not graph_path.is_file():
            continue
        try:
            graph = _load(graph_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(_finding("invalid-graph", key, str(exc))); continue
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
            findings.append(_finding("unsupported-schema", key, "Expected object with nodes and edges arrays")); continue
        node_map: dict[str, dict[str, Any]] = {}
        for i, node in enumerate(graph["nodes"]):
            if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
                findings.append(_finding("invalid-node", key, f"Node {i} requires string id")); continue
            node_id = node["id"]
            if node_id in node_map:
                findings.append(_finding("duplicate-id", key, f"Duplicate node ID {node_id}", identity=node_id))
            node_map[node_id] = node
            missing_fields = REQUIRED_NODE_FIELDS - node.keys()
            if missing_fields:
                findings.append(_finding("invalid-node-fields", key, f"Node {node_id} is missing required graph fields: {', '.join(sorted(missing_fields))}", identity=node_id))
            if not isinstance(node.get("type"), str) or node.get("type") not in NODE_TYPES:
                findings.append(_finding("invalid-node-type", key, f"Node {node_id} has unsupported type {node.get('type')!r}", identity=node_id))
            if not isinstance(node.get("title"), str) or not node.get("title"):
                findings.append(_finding("invalid-node-title", key, f"Node {node_id} requires nonempty title", identity=node_id))
            if not isinstance(node.get("status"), str):
                pass
            elif node["status"] not in STATUSES:
                findings.append(_finding("invalid-status", key, f"Node {node_id} has unsupported status {node['status']!r}", identity=node_id))
            elif node["status"] == "verified" and not (isinstance(node.get("source"), str) and node["source"].strip()):
                findings.append(_finding("verified-source-missing", key, f"Verified node {node_id} has no source reference", identity=node_id))
            source = node.get("source")
            if source is not None:
                if not isinstance(source, str) or not source.strip():
                    findings.append(_finding("invalid-source", key, f"Node {node_id} source must be a nonempty string", identity=node_id)); continue
                kind, target = _source_target(root, graph_path.parent, source)
                if kind == "escape":
                    findings.append(_finding("unsafe-source-path", key, f"Node {node_id} source escapes repository: {source}", identity=node_id))
                elif kind == "unsupported":
                    findings.append(_finding("unsupported-source", key, f"Node {node_id} source format is unsupported: {source}", identity=node_id))
                elif kind == "local" and target is not None and not target.exists():
                    findings.append(_finding("missing-source-target", key, f"Node {node_id} source target does not exist: {source}", identity=node_id))
                elif kind == "external":
                    findings.append(_finding("external-source-unverified", key, f"Node {node_id} source was not fetched: {source}", severity="unverified", identity=node_id))

        degree = {node_id: 0 for node_id in node_map}
        edges: list[tuple[str, str, str]] = []
        for i, edge in enumerate(graph["edges"]):
            if not isinstance(edge, dict) or not all(isinstance(edge.get(k), str) and edge[k] for k in REQUIRED_EDGE_FIELDS):
                findings.append(_finding("invalid-edge", key, f"Edge {i} requires nonempty from, to, type")); continue
            src, dst, label = edge["from"], edge["to"], edge["type"]
            if src not in node_map or dst not in node_map:
                findings.append(_finding("dangling-edge", key, f"Edge {i} references missing endpoint(s): {src!r} -> {dst!r}")); continue
            degree[src] += 1; degree[dst] += 1; edges.append((src, dst, label))
            if label in TYPED_EDGES:
                from_types, to_types = TYPED_EDGES[label]
                actual_types = (node_map[src].get("type"), node_map[dst].get("type"))
                if actual_types[0] not in from_types or actual_types[1] not in to_types:
                    severity = "blocker" if label == "accepted by" else "advisory"
                    findings.append(_finding("typed-edge-mismatch", key, f"{label!r} is a canonical authoring convention ({sorted(from_types)} -> {sorted(to_types)}); inspect this existing trace: {actual_types}", severity=severity, edge=i))
        for node_id, count in degree.items():
            if count == 0:
                findings.append(_finding("orphan-node", key, f"Node {node_id} has no relationships", identity=node_id))

        # Requirement criteria are direct semantic links in the graph contract.
        reqs = {node_id for node_id, n in node_map.items() if n.get("type") == "requirement"}
        acs = {node_id for node_id, n in node_map.items() if n.get("type") == "acceptance"}
        for prose_path in sorted(graph_path.parent.glob("*.md")):
            for line_number, line in enumerate(prose_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                match = DECLARED_ID.match(line)
                if match and match.group(1) not in node_map:
                    findings.append(_finding("declared-spec-id-unmapped", key, f"Declared ID {match.group(1)} has no graph node", identity=match.group(1), source=f"{prose_path.relative_to(root).as_posix()}:{line_number}"))
        for req in sorted(reqs):
            if not any(a == req and label in {"accepted by", "has acceptance criterion"} and b in acs for a, b, label in edges):
                findings.append(_finding("requirement-unaccepted", key, f"Requirement {req} has no direct accepted-by criterion", identity=req))
        for ac in sorted(acs):
            if not any(a in reqs and b == ac and label in {"accepted by", "has acceptance criterion"} for a, b, label in edges):
                findings.append(_finding("acceptance-unowned", key, f"Acceptance {ac} has no direct owning requirement", identity=ac))
            # Permit acceptance -> implementation/evaluator -> test evidence chains.
            reachable = {ac}; changed = True
            while changed:
                changed = False
                for a, b, label in edges:
                    if a in reachable and label in {"checked by", "verified by", "evaluated by", "implemented by", "uses"} and b not in reachable:
                        reachable.add(b); changed = True
            if not any(node_map.get(item, {}).get("type") == "test" for item in reachable):
                findings.append(_finding("acceptance-no-test", key, f"Acceptance {ac} has no linked test through a declared evidence chain", identity=ac))

        # Code/test/source references on any node are checked above. Explicitly
        # mark requirements with no implementation trace path as a blocker.
        for req in sorted(reqs):
            reachable = {req}; changed = True
            while changed:
                changed = False
                for a, b, label in edges:
                    if a in reachable and label in {"appears on", "triggers", "implemented by", "represented by", "renders", "renders in", "requires", "describes", "includes"} and b not in reachable:
                        reachable.add(b); changed = True
            if not any(node_map.get(item, {}).get("type") == "code" for item in reachable):
                findings.append(_finding("requirement-no-code-path", key, f"Requirement {req} has no implementation path to code", identity=req))
    return findings


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    report = check(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if any(f.get("severity", "blocker") == "blocker" for f in report) else 0)
