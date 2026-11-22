"""Audit registered feature graphs against the repository's graph-root registry.

Checks are structural and local. They do not infer meaning from prose or promote
declared evidence to runtime acceptance.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urlparse

from graph_document import contract as _graph_contract, read_json as _load


ROOT_REGISTRY = Path("specs/graph-roots.json")
NODE_TYPES = _graph_contract.NODE_TYPES
STATUSES = _graph_contract.STATUSES
REQUIRED_NODE_FIELDS = _graph_contract.REQUIRED_NODE_FIELDS
REQUIRED_EDGE_FIELDS = _graph_contract.REQUIRED_EDGE_FIELDS
DECLARED_ID = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*|`)?((?:REQ|AC)-[A-Z0-9][A-Z0-9_-]*)(?:\*\*|`)?\s*(?:[—–:|])")
GRAPH_ID_REFERENCE = re.compile(r"\b(?:REQ|AC|SCR|ACT|CODE|TEST|STATE|FIGMA|ALIGN|ROUTE|APP|CMP)-[A-Z0-9][A-Z0-9_-]*\b")
# Canonical relationships whose direction and endpoint types are defined by
# skills/figma-flow/references/graph-contract.md. Unknown legacy labels remain
# usable as trace edges; they are not interpreted as evidence links.
TYPED_EDGES = {
    label: (set(sources), {target})
    for label, (sources, target) in _graph_contract.LOCAL_TRACE_ENDPOINTS.items()
}
# A feature-level requirement can own implementation directly in a release specification.
sources, targets = TYPED_EDGES["implemented by"]
TYPED_EDGES.update({
    "implemented by": (sources | {"requirement"}, targets),
    "has acceptance criterion": TYPED_EDGES["accepted by"],
    "verified by": TYPED_EDGES["checked by"],
    "has state": ({"screen"}, {"state"}),
    "triggers": ({"screen"}, {"action"}),
    "navigates to": ({"action"}, {"screen", "state"}),
    "rendered as": ({"screen"}, {"figma"}),
    "observed in": ({"screen", "figma"}, {"test"}),
    "exercised through": ({"acceptance"}, {"code"}),
    "represented by": ({"screen", "state", "action"}, {"figma"}),
})


def _finding(code: str, path: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "path": path, "message": message, **extra}


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


def _index_links(root: Path, readme: Path) -> tuple[list[tuple[str, Path]], list[dict[str, Any]]]:
    """Resolve local links in the human feature index without fetching URLs."""
    links: list[tuple[str, Path]] = []
    findings: list[dict[str, Any]] = []
    text = readme.read_text(encoding="utf-8", errors="replace")
    for line_number, line in enumerate(text.splitlines(), 1):
        for match in re.finditer(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", line):
            raw = match.group(1)
            parsed = urlparse(raw)
            if parsed.scheme or parsed.netloc or raw.startswith(("//", "\\\\")):
                continue
            target_text = unquote(parsed.path)
            if not target_text:
                continue
            target = (readme.parent / target_text).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                findings.append(_finding("unsafe-index-link", "specs/README.md", f"Local index link escapes repository: {raw}", source=f"specs/README.md:{line_number}"))
                continue
            if not target.exists():
                findings.append(_finding("broken-index-link", "specs/README.md", f"Local index target does not exist: {raw}", source=f"specs/README.md:{line_number}"))
                continue
            links.append((raw, target))
    return links, findings


def _render_receipts(key, nodes, edges):
    observations = {}
    for source, target, label in edges:
        if label == 'observed in':
            observations.setdefault(source, []).append(target)
    findings = []
    paired_subjects = set()
    receipt_owners = {}
    for source, target, label in edges:
        if label != 'rendered as':
            continue
        screen, frame = nodes[source], nodes[target]
        if (frame.get('status') != 'verified' and screen.get('status') != 'verified'
                and not observations.get(source) and not observations.get(target)):
            continue
        seen = observations.get(source, [])
        paired_subjects.update((source, target))
        same = len(seen) == 1 and seen == observations.get(target, [])
        if same and seen[0] in receipt_owners:
            same = False
        elif same:
            receipt_owners[seen[0]] = (source,target)
        record = nodes[seen[0]] if same else {}
        dimensions = {'width':frame.get('frame_width'),'height':frame.get('frame_height')}
        valid = (same and record.get('type') == 'test' and record.get('status') == 'verified'
                 and all(type(v) in (int,float) and v > 0 for v in dimensions.values())
                 and screen.get('document') == dimensions
                 and record.get('reapply_sha256') == frame.get('receipt_sha256')
                 and all(isinstance(record.get(field), str) and re.fullmatch(r'[0-9a-f]{64}',record[field])
                         for field in ('capture_sha256','reapply_sha256','browser_png_sha256','figma_png_sha256')))
        if not valid:
            findings.append(_finding('unpaired-render-observation', key,
                f'{source} and {target} require matching dimensions and the same browser/native receipt.', identity=target))
    for subject in sorted(set(observations) - paired_subjects):
        findings.append(_finding('unpaired-render-observation', key,
            f'{subject} names a render observation without its screen and native frame.', identity=subject))
    return findings


def check(root: str | Path) -> list[dict[str, Any]]:
    """Return blockers and explicitly non-blocking unresolved references."""
    root = Path(root).resolve()
    registry_path = root / ROOT_REGISTRY
    findings: list[dict[str, Any]] = []
    if not (root / "specs").is_dir():
        return [_finding("missing-specs-root", "specs", "Registered specs directory is missing")]
    try:
        registry = _load(registry_path)
    except (OSError, ValueError) as exc:
        return [_finding("invalid-root-registry", ROOT_REGISTRY.as_posix(), str(exc))]
    if not isinstance(registry, dict) or registry.get("version") != 1 or not isinstance(registry.get("roots"), list):
        return [_finding("unsupported-root-registry", ROOT_REGISTRY.as_posix(), "Expected version 1 object with roots array")]
    readme = root / "specs/README.md"
    if not readme.is_file():
        findings.append(_finding("registry-not-indexed", "specs/README.md", "README must link the authoritative graph-roots.json registry"))
        index_links = []
    else:
        readme_text = readme.read_text(encoding="utf-8")
        if "[graph-roots.json](graph-roots.json)" not in readme_text:
            findings.append(_finding("registry-not-indexed", "specs/README.md", "README must link the authoritative graph-roots.json registry"))
        index_links, link_findings = _index_links(root, readme)
        findings.extend(link_findings)
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
    # Every registered feature must be discoverable from the canonical index.
    # The index may point to its graph or to the feature's requirement/screen
    # document; both are legitimate entry points to the same directory.
    for key in sorted(registered):
        feature_dir = (root / key).parent
        if not any(target == feature_dir or feature_dir in target.parents for _, target in index_links):
            findings.append(_finding("root-not-indexed", "specs/README.md", f"Canonical graph root has no feature entry in the README: {key}", identity=key))

    for key, registration in sorted(registered.items()):
        graph_path = root / key
        if not graph_path.is_file():
            continue
        try:
            graph = _load(graph_path)
        except (OSError, ValueError) as exc:
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
                    severity = "blocker" if label in {"accepted by","rendered as","observed in","exercised through"} else "advisory"
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
                for identity in sorted(set(GRAPH_ID_REFERENCE.findall(line)) - set(node_map)):
                    findings.append(_finding("referenced-spec-id-unmapped", key, f"Referenced ID {identity} has no graph node", identity=identity, source=f"{prose_path.relative_to(root).as_posix()}:{line_number}"))
        findings.extend(_render_receipts(key, node_map, edges))
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
