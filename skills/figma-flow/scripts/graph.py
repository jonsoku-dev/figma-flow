#!/usr/bin/env python3
"""Validate and render the Figma flow evidence graph."""

import argparse
import importlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlsplit


NODE_TYPES = {"reference", "requirement", "screen", "state", "action", "figma", "code", "test", "acceptance", "design-token", "component"}
STATUSES = {"planned", "observed", "verified", "blocked", "unverified"}
REQUIRED_NODE_FIELDS = {"id", "type", "title", "status"}
REQUIRED_EDGE_FIELDS = {"from", "to", "type"}
NODE_STRING_FIELDS = ("id", "title", "source", "detail", "type", "status")


def _has_unpaired_surrogate(value):
    index = 0
    while index < len(value):
        codepoint = ord(value[index])
        if 0xD800 <= codepoint <= 0xDBFF:
            if index + 1 == len(value) or not 0xDC00 <= ord(value[index + 1]) <= 0xDFFF:
                return True
            index += 2
        elif 0xDC00 <= codepoint <= 0xDFFF:
            return True
        else:
            index += 1
    return False


def load_graph(path):
    try:
        with Path(path).open(encoding="utf-8") as source:
            graph = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"Cannot read graph JSON: {exc}"]
    return graph, []


def validate_graph(graph, strict_local=False, *, include_figma_warnings=True):
    errors = []
    warnings = []
    if not isinstance(graph, dict):
        return ["Graph must be a JSON object."], warnings
    surrogate_errors = []
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    for index, node in enumerate(nodes if isinstance(nodes, list) else []):
        if isinstance(node, dict):
            for field in NODE_STRING_FIELDS:
                if isinstance(node.get(field), str) and _has_unpaired_surrogate(node[field]):
                    surrogate_errors.append(f"nodes[{index}].{field} must not contain an unpaired Unicode surrogate.")
            if isinstance(node.get("target_ids"), list):
                for target_index, target_id in enumerate(node["target_ids"]):
                    if isinstance(target_id, str) and _has_unpaired_surrogate(target_id):
                        surrogate_errors.append(f"nodes[{index}].target_ids[{target_index}] must not contain an unpaired Unicode surrogate.")
            if isinstance(node.get("source_screen"), str) and _has_unpaired_surrogate(node["source_screen"]):
                surrogate_errors.append(f"nodes[{index}].source_screen must not contain an unpaired Unicode surrogate.")
    for index, edge in enumerate(edges if isinstance(edges, list) else []):
        if isinstance(edge, dict):
            for field in REQUIRED_EDGE_FIELDS:
                if isinstance(edge.get(field), str) and _has_unpaired_surrogate(edge[field]):
                    surrogate_errors.append(f"edges[{index}].{field} must not contain an unpaired Unicode surrogate.")
    if surrogate_errors:
        return surrogate_errors, warnings
    if type(graph.get("version")) is not int or graph["version"] != 1:
        errors.append("version must be the integer 1.")
    if not isinstance(nodes, list):
        errors.append("nodes must be an array.")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges must be an array.")
        edges = []

    by_id = {}
    for index, node in enumerate(nodes):
        where = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{where} must be an object.")
            continue
        missing = REQUIRED_NODE_FIELDS - node.keys()
        if missing:
            errors.append(f"{where} missing required fields: {', '.join(sorted(missing))}.")
        for field in ("id", "title", "source", "detail"):
            if field in node and not isinstance(node[field], str):
                errors.append(f"{where}.{field} must be a string.")
        if "id" in node and isinstance(node["id"], str):
            if not node["id"].strip():
                errors.append(f"{where}.id must not be empty.")
            elif node["id"] in by_id:
                errors.append(f"Duplicate node id: {node['id']!r}.")
            else:
                by_id[node["id"]] = node
        if "title" in node and isinstance(node["title"], str) and not node["title"].strip():
            errors.append(f"{where}.title must not be empty.")
        if "type" in node and (not isinstance(node["type"], str) or node["type"] not in NODE_TYPES):
            errors.append(f"{where}.type must be one of: {', '.join(sorted(NODE_TYPES))}.")
        if "status" in node and (not isinstance(node["status"], str) or node["status"] not in STATUSES):
            errors.append(f"{where}.status must be one of: {', '.join(sorted(STATUSES))}.")
        if node.get("status") == "verified" and not (isinstance(node.get("source"), str) and node["source"].strip()):
            errors.append(f"{where}.source is required for verified nodes.")
        if "source_screen" in node:
            if node.get("type") != "action":
                errors.append(f"{where}.source_screen is only valid on action nodes.")
            if not isinstance(node["source_screen"], str):
                errors.append(f"{where}.source_screen must be a string.")
        if "target_ids" in node:
            if node.get("type") != "action":
                errors.append(f"{where}.target_ids is only valid on action nodes.")
            if not isinstance(node["target_ids"], list):
                errors.append(f"{where}.target_ids must be an array.")
            else:
                for target_index, target_id in enumerate(node["target_ids"]):
                    if not isinstance(target_id, str):
                        errors.append(f"{where}.target_ids[{target_index}] must be a string.")

    adjacency = {node_id: [] for node_id in by_id}
    directed_edges = set()
    incoming = {node_id: set() for node_id in by_id}
    outgoing = {node_id: set() for node_id in by_id}
    for index, edge in enumerate(edges):
        where = f"edges[{index}]"
        if not isinstance(edge, dict):
            errors.append(f"{where} must be an object.")
            continue
        missing = REQUIRED_EDGE_FIELDS - edge.keys()
        if missing:
            errors.append(f"{where} missing required fields: {', '.join(sorted(missing))}.")
        for field in REQUIRED_EDGE_FIELDS:
            if field in edge and not isinstance(edge[field], str):
                errors.append(f"{where}.{field} must be a string.")
        if isinstance(edge.get("type"), str) and not edge["type"].strip():
            errors.append(f"{where}.type must not be empty.")
        if isinstance(edge.get("from"), str) and isinstance(edge.get("to"), str):
            if edge["from"] not in by_id:
                errors.append(f"{where}.from references unknown node {edge['from']!r}.")
            if edge["to"] not in by_id:
                errors.append(f"{where}.to references unknown node {edge['to']!r}.")
            if edge["from"] in adjacency and edge["to"] in by_id:
                adjacency[edge["from"]].append(edge["to"])
                directed_edges.add((edge["from"], edge["to"]))
                incoming[edge["to"]].add(edge["from"])
                outgoing[edge["from"]].add(edge["to"])

    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or node.get("type") != "action":
            continue
        where = f"nodes[{index}]"
        action_id = node.get("id")
        action_label = action_id if "id" in node else index
        has_valid_id = isinstance(action_id, str) and bool(action_id.strip()) and action_id in by_id
        if "source_screen" not in node:
            warnings.append(f"Action {action_label!r} has no source_screen field.")
        else:
            source_id = node.get("source_screen")
            if isinstance(source_id, str):
                source = by_id.get(source_id)
                if source is None:
                    errors.append(f"{where}.source_screen references unknown node {source_id!r}.")
                elif source.get("type") != "screen":
                    errors.append(f"{where}.source_screen must reference a screen node.")
                elif has_valid_id:
                    if (source_id, action_id) not in directed_edges:
                        errors.append(f"{where}.source_screen disagrees with graph edges: expected {source_id!r} -> {action_id!r}.")
                    for incoming_id in sorted(incoming[action_id]):
                        if incoming_id != source_id and by_id[incoming_id].get("type") == "screen":
                            errors.append(f"{where}.source_screen omits incoming screen edge {incoming_id!r} -> {action_id!r}.")
        if "target_ids" not in node:
            warnings.append(f"Action {action_label!r} has no target_ids field.")
        if isinstance(node.get("target_ids"), list):
            targets = {target_id for target_id in node["target_ids"] if isinstance(target_id, str)}
            for target_index, target_id in enumerate(node["target_ids"]):
                if not isinstance(target_id, str):
                    continue
                if target_id not in by_id:
                    errors.append(f"{where}.target_ids[{target_index}] references unknown node {target_id!r}.")
                elif has_valid_id and (action_id, target_id) not in directed_edges:
                    errors.append(f"{where}.target_ids[{target_index}] disagrees with graph edges: expected {action_id!r} -> {target_id!r}.")
            if has_valid_id:
                for target_id in sorted(outgoing[action_id]):
                    if by_id[target_id].get("type") in ("screen", "state") and target_id not in targets:
                        errors.append(f"{where}.target_ids omits outgoing destination edge {action_id!r} -> {target_id!r}.")

    if errors:
        return errors, warnings

    # Reverse traversals share reachability work across all requirements/screens.
    def ancestors_of_type(target_type):
        seen = {node_id for node_id, node in by_id.items() if node["type"] == target_type}
        pending = list(seen)
        while pending:
            for predecessor in incoming[pending.pop()]:
                if predecessor not in seen:
                    seen.add(predecessor)
                    pending.append(predecessor)
        return seen

    reaches = {target: ancestors_of_type(target) for target in ("screen", "figma", "code", "test")}

    requirement_reachable = {node_id for node_id, node in by_id.items() if node["type"] == "requirement"}
    pending = list(requirement_reachable)
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current]:
            if neighbor not in requirement_reachable:
                requirement_reachable.add(neighbor)
                pending.append(neighbor)

    if not any(node["type"] == "requirement" for node in by_id.values()):
        warnings.append("Graph has no requirement nodes.")
    if not any(node["type"] == "screen" for node in by_id.values()):
        warnings.append("Graph has no screen nodes.")
    for node_id, node in by_id.items():
        if node["type"] == "requirement" and node_id not in reaches["screen"]:
            warnings.append(f"Requirement {node_id!r} has no path to a screen.")
        if node["type"] == "screen":
            for target in (("code",) if strict_local or not include_figma_warnings else ("figma", "code")):
                if node_id not in reaches[target]:
                    warnings.append(f"Screen {node_id!r} has no linked {target} node.")
        if node["status"] in {"blocked", "unverified"}:
            if node["type"] == "test":
                warnings.append(f"Test {node_id!r} is {node['status']}, not verified.")
            else:
                warnings.append(f"Node {node_id!r} is {node['status']}, not verified.")
        if node["type"] == "acceptance" and node_id not in reaches["test"]:
            warnings.append(f"Acceptance {node_id!r} has no path to a test.")
        if node["type"] == "acceptance" and node_id not in requirement_reachable:
            warnings.append(f"Acceptance {node_id!r} has no inbound path from a requirement.")
    if strict_local:
        errors.extend(_validate_local_coverage(graph, by_id))
    return errors, warnings


def _validate_local_coverage(graph, by_id):
    """Check explicit local trace declarations, without inspecting evidence files."""
    errors = []
    endpoints = {
        "informs": ("reference", "requirement"),
        "appears on": ("requirement", "screen"),
        "accepted by": ("requirement", "acceptance"),
        "implemented by": (("screen", "state", "action"), "code"),
        "checked by": (("acceptance", "code"), "test"),
    }
    links = {label: {} for label in endpoints}
    for edge in graph["edges"]:
        label = edge["type"]
        if label not in endpoints:
            continue
        source_type, target_type = endpoints[label]
        allowed_sources = (source_type,) if isinstance(source_type, str) else source_type
        if by_id[edge["from"]]["type"] not in allowed_sources or by_id[edge["to"]]["type"] != target_type:
            errors.append(f"Strict local coverage: edge {edge['from']!r} --{label}--> {edge['to']!r} has invalid endpoint types.")
            continue
        links[label].setdefault(edge["from"], set()).add(edge["to"])

    requirements = [node for node in by_id.values() if node["type"] == "requirement"]
    if not requirements:
        errors.append("Strict local coverage: at least one requirement is required.")
    owned = {"screen": set(), "acceptance": set()}
    for requirement in requirements:
        if requirement["status"] not in {"observed", "verified"}:
            errors.append(f"Strict local coverage: requirement {requirement['id']!r} must be observed or verified.")
        for label, target in (("appears on", "screen"), ("accepted by", "acceptance")):
            targets = links[label].get(requirement["id"], set())
            owned[target].update(targets)
            if not targets:
                errors.append(f"Strict local coverage: requirement {requirement['id']!r} needs a direct {label!r} link to a {target}.")
    for node_id, node in by_id.items():
        node_type = node["type"]
        if node_type not in owned:
            continue
        if node_id not in owned[node_type]:
            errors.append(f"Strict local coverage: {node_type} {node_id!r} has no direct requirement trace.")
        label, target = ("implemented by", "code") if node_type == "screen" else ("checked by", "test")
        targets = links[label].get(node_id, set())
        if not targets:
            errors.append(f"Strict local coverage: {node_type} {node_id!r} needs a direct {label!r} link to a {target}.")
        if node_type == "screen" and node["status"] not in {"observed", "verified"}:
            errors.append(f"Strict local coverage: screen {node_id!r} must be observed or verified.")
        if node_type == "acceptance" and node["status"] != "verified":
            errors.append(f"Strict local coverage: acceptance {node_id!r} must be verified.")
        for target_id in sorted(targets):
            if by_id[target_id]["status"] != "verified":
                errors.append(f"Strict local coverage: {target} {target_id!r} linked from {node_id!r} must be verified.")
    verified_tests = {
        owner: {test_id for test_id in tests if by_id[test_id]["status"] == "verified"}
        for owner, tests in links["checked by"].items()
    }
    for requirement in requirements:
        requirement_id = requirement["id"]
        screens = links["appears on"].get(requirement_id, set())
        codes = {code_id for screen in screens for code_id in links["implemented by"].get(screen, set())}
        criteria = links["accepted by"].get(requirement_id, set())
        code_tests = {test for code in codes for test in verified_tests.get(code, set())}
        acceptance_tests = {test for criterion in criteria for test in verified_tests.get(criterion, set())}
        for criterion in sorted(criteria):
            if not verified_tests.get(criterion, set()) & code_tests:
                errors.append(f"Strict local coverage: acceptance {criterion!r} must share a verified test with implemented code for requirement {requirement_id!r}.")
        for code in sorted(codes):
            if not verified_tests.get(code, set()) & acceptance_tests:
                errors.append(f"Strict local coverage: code {code!r} must share a verified test with acceptance for requirement {requirement_id!r}.")
            for test in sorted(links["checked by"].get(code, set())):
                if by_id[test]["status"] != "verified":
                    errors.append(f"Strict local coverage: test {test!r} linked from {code!r} must be verified.")
    return errors


def _mermaid_text(value):
    # Mermaid entity codes keep user text inside quoted labels.
    escaped = {"#": "#35;", "&": "#amp;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "|": "#124;", "`": "#96;"}
    return "".join(escaped.get(char, char) for char in " ".join(value.split()))


def _markdown_code_span(value):
    delimiter = "`" * (value.count("`") + 1)
    padding = " " if value and (value.startswith(" ") or value.endswith(" ")) else ""
    return f"{delimiter}{padding}{value}{padding}{delimiter}"


def _markdown_text(value):
    value = " ".join(value.split())
    return r"\|".join(_markdown_code_span(part) for part in value.split("|"))


def _markdown_source(value):
    if any(unicodedata.category(char) == "Cc" for char in value) or re.search(r"%(?![0-9A-Fa-f]{2})", value):
        return _markdown_text(value)
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        return _markdown_text(value)
    if (url.scheme.lower() != "https" or not url.hostname or url.username is not None
            or url.password is not None or any(char.isspace() for char in url.netloc)
            or "\\" in url.netloc or port == 0):
        return _markdown_text(value)
    destination = quote(value, safe=":/?#[]@!$&'*,;=%")
    return f"[open source](<{destination}>)"


def render_markdown(graph):
    lines = ["# Screen graph", "", f"Graph version: {graph['version']}", "", "## Nodes", "",
             "| ID | Type | Status | Title | Source | Detail |", "| --- | --- | --- | --- | --- | --- |"]
    for node in graph["nodes"]:
        fields = [node.get(key, "") for key in ("id", "type", "status", "title", "source", "detail")]
        rendered = [_markdown_source(str(field)) if key == "source" else _markdown_text(str(field))
                    for key, field in zip(("id", "type", "status", "title", "source", "detail"), fields)]
        lines.append("| " + " | ".join(rendered) + " |")
    lines.extend(["", "## Edges", ""])
    if graph["edges"]:
        for edge in graph["edges"]:
            lines.append(f"- {_markdown_text(edge['from'])} —{_markdown_text(edge['type'])}→ {_markdown_text(edge['to'])}")
    else:
        lines.append("No edges.")
    views = (
        ("Overview", {"requirement", "screen", "figma", "code"}),
        ("Navigation", {"screen", "action", "state"}),
    )
    rendered_views = []
    for title, node_types in views:
        view = _filtered_graph(graph, node_types)
        if view["nodes"] and view["edges"]:
            rendered_views.append((title, render_mermaid(view)))
    if rendered_views:
        lines.extend(["", "## Filtered views (full diagram below)", ""])
        for title, diagram in rendered_views:
            lines.extend([f"### {title} (filtered to selected node types and direct edges)", "", "```mermaid", diagram, "```", ""])
    lines.extend(["", "## Diagram (full graph)", "", "```mermaid", render_mermaid(graph), "```", ""])
    return "\n".join(lines)


def _filtered_graph(graph, node_types):
    nodes = [node for node in graph["nodes"] if node["type"] in node_types]
    node_ids = {node["id"] for node in nodes}
    edges = [edge for edge in graph["edges"] if edge["from"] in node_ids and edge["to"] in node_ids]
    return {"nodes": nodes, "edges": edges}


def render_mermaid(graph):
    ids = {node["id"]: f"n{index}" for index, node in enumerate(graph["nodes"])}
    lines = ["flowchart LR"]
    for node in graph["nodes"]:
        label = f"{node['id']} · {node['title']} ({node['status']})"
        lines.append(f'  {ids[node["id"]]}["{_mermaid_text(label)}"]')
    for edge in graph["edges"]:
        lines.append(f'  {ids[edge["from"]]} -->|"{_mermaid_text(edge["type"])}"| {ids[edge["to"]]}')
    lines.append("")
    return "\n".join(lines)


def impact_report(graph, start):
    nodes = {node["id"]: node for node in graph["nodes"]}
    if start not in nodes:
        raise ValueError(f"Unknown start node: {start!r}.")
    try:
        nx = importlib.import_module("networkx")
    except ImportError as exc:
        requirements = Path(__file__).resolve().parents[3] / "requirements-optional.txt"
        raise RuntimeError(
            "NetworkX is required for impact analysis. Create and activate a virtual environment in the task workspace, then install the optional dependency with: python -m pip install -r \""
            f"{requirements}\". The managed plugin cache remains unchanged."
        ) from exc

    directed = nx.DiGraph()
    directed.add_nodes_from(sorted(nodes))
    directed.add_edges_from(sorted((edge["from"], edge["to"]) for edge in graph["edges"]))
    paths = nx.single_source_shortest_path(directed, start)
    impacted = [
        {"id": node_id, "type": nodes[node_id]["type"], "status": nodes[node_id]["status"], "path": path}
        for node_id, path in sorted(paths.items()) if node_id != start
    ]
    cyclic_components = []
    for component in nx.strongly_connected_components(directed):
        cyclic = len(component) > 1 or any(directed.has_edge(node_id, node_id) for node_id in component)
        if cyclic and any(node_id in paths for node_id in component):
            cyclic_components.append(sorted(component))
    cyclic_components.sort()
    return {
        "classification": "Candidate impacts reachable along directed edges only; no reverse or semantic dependency is inferred, and changes are not verified.",
        "start": start,
        "impacted": impacted,
        "cyclic_components": cyclic_components,
    }


def _report_warnings(warnings):
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)


def _file_identity(stat):
    return stat.st_dev, stat.st_ino


def _remove_if_owned(path, identity):
    try:
        if _file_identity(path.lstat()) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


def _write_exclusive(path, content):
    fd = None
    identity = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        identity = _file_identity(os.fstat(fd))
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            fd = None
            output.write(content)
        return identity
    except (OSError, UnicodeError):
        if fd is not None:
            os.close(fd)
        if identity is not None:
            _remove_if_owned(path, identity)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a graph")
    validate.add_argument("graph")
    validate.add_argument("--strict-local", action="store_true", help="require explicit requirement/screen/code and verified acceptance/test trace coverage; does not inspect evidence")
    render = commands.add_parser("render", help="render graph documentation")
    render.add_argument("graph")
    render.add_argument("--strict-local", action="store_true", help="validate declared local coverage before rendering")
    render.add_argument("--out-dir", required=True)
    impact = commands.add_parser("impact", help="analyze candidate downstream impacts")
    impact.add_argument("graph")
    impact.add_argument("--from", dest="start", required=True, metavar="NODE_ID")
    args = parser.parse_args(argv)

    graph, errors = load_graph(args.graph)
    if not errors:
        errors, warnings = validate_graph(graph, strict_local=getattr(args, "strict_local", False))
    else:
        warnings = []
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    _report_warnings(warnings)
    if args.command == "validate":
        print("Graph structure and declared local coverage are valid." if args.strict_local else "Graph structure is valid.")
        return 0
    if args.command == "impact":
        try:
            report = impact_report(graph, args.start)
        except (RuntimeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    out_dir = Path(args.out_dir)
    outputs = [out_dir / "screen-graph.md", out_dir / "screen-graph.mmd"]
    existing = [path for path in outputs if path.exists()]
    if existing:
        print("Error: refusing to overwrite: " + ", ".join(str(path) for path in existing), file=sys.stderr)
        return 1
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Error: could not create output directory: {exc}", file=sys.stderr)
        return 1
    created = []
    try:
        for path, content in zip(outputs, (render_markdown(graph), render_mermaid(graph))):
            created.append((path, _write_exclusive(path, content)))
    except (OSError, UnicodeError) as exc:
        for path, identity in reversed(created):
            _remove_if_owned(path, identity)
        reason = str(exc) if isinstance(exc, OSError) else "invalid text encoding"
        print(f"Error: could not write graph output: {reason}", file=sys.stderr)
        return 1
    print(f"Rendered {outputs[0]} and {outputs[1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
