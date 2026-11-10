#!/usr/bin/env python3
"""Check a project's existing SSOT manifest without running project code."""
import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/figma-flow/scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(SCRIPTS))
import graph
import graph_diff
import ssot
import trace_report
import native_handoff
import design_review
import design_directions
import app_states
import workflow
from workflow import State


def selected_creation(data, bindings, bindings_path, graph_path, intent, manifest=None, brief_path=None):
    active = intent if intent != 'auto' else (manifest or {}).get('design_intent',
        'create' if design_review.frontend(data, bindings) or 'design_review' in bindings else 'technical')
    if active not in design_review.OPERATIONS:
        return active, None
    declaration = bindings.get('design_directions')
    if not isinstance(declaration, dict) or not isinstance(declaration.get('selection'), str):
        raise design_directions.SelectionRequired(f'{State.WAIT_SELECTION.name}: current actual user-selected direction is required before creation admission')
    selected = design_directions.require_implementation_selection(bindings_path.parent / declaration['selection'], graph_path)
    if brief_path is not None:
        from review_destination import resolve
        draft = design_directions.validate_draft(selected['draft_path'])['data']
        if design_directions.pin(brief_path)['sha256'] != draft['brief']['sha256']:
            raise design_directions.SelectionRequired('Current brief differs from exact user-reviewed request')
        graph_requires = data.get('requires_figma') is True or any(n.get('type') == 'figma' for n in data.get('nodes', []))
        resolve(Path(brief_path).read_text(), explicit=selected['review_destination'], graph_requires=graph_requires)
    return active, selected


def figma_sources(data, bindings):
    """Structural Figma evidence only; local-only SSOT is not an exemption."""
    sources = []
    def visit(value):
        if isinstance(value, str):
            try:
                parsed = urlsplit(value)
            except ValueError:
                return
            if parsed.scheme == 'figma' or parsed.hostname in ('figma.com', 'www.figma.com'):
                sources.append(value)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(data.get('nodes', []))
    visit(data.get('edges', []))
    authorities = bindings.get('authorities')
    if isinstance(authorities, dict):
        visit(authorities.get('visual'))
    nodes = data.get('nodes')
    required = (data.get('requires_figma') is True or 'native_handoff' in bindings or bool(sources) or
                any(isinstance(n, dict) and n.get('type') == 'figma'
                    for n in (nodes if isinstance(nodes, list) else [])))
    return required, sources


def has_symlink(path):
    # macOS exposes standard temporary/config roots through system aliases.
    aliases = {Path('/var'): Path('/private/var'), Path('/tmp'): Path('/private/tmp'), Path('/etc'): Path('/private/etc')}
    return any(p.is_symlink() and aliases.get(p) != p.resolve() for p in (path, *path.parents))


def evaluate_native(data, bindings, bindings_path, inputs, check, *, strict_creation=False, direction=None):
    """Pin supplied local evidence; this does not attest its remote capture origin."""
    required, sources = figma_sources(data, bindings)
    if strict_creation:
        from review_destination import resolve
        required = required or resolve(Path(inputs['brief']).read_text(), explicit=direction.get('review_destination') if direction else None, graph_requires=data.get('requires_figma') is True) == 'figma'
    if not required:
        return None
    report = native_handoff.evaluate(None, None)
    report['errors'] = []
    report['inputs'] = {key: {'path': str(path.absolute()), 'sha256': check['inputs'][key]['sha256']}
                        for key, path in inputs.items()}
    report['evidence_inputs'] = {}
    try:
        declaration = bindings.get('native_handoff')
        if not isinstance(declaration, dict):
            raise ValueError('Figma-backed delivery requires bindings.native_handoff')
        page_id = declaration.get('page_id')
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError('native_handoff.page_id is required')
        documents = {}
        for key in ('readback', 'contract'):
            value = declaration.get(key)
            if not isinstance(value, str) or not value.strip() or urlsplit(value).scheme or Path(value).is_absolute():
                raise ValueError('native_handoff.' + key + ' must be a local path relative to bindings')
            path = (bindings_path.parent / value).absolute()
            if has_symlink(path):
                raise ValueError('native handoff input must not traverse symlinks: ' + value)
            sha256, content = ssot.read_local(path, capture=True)
            report['evidence_inputs'][key] = {'path': str(path), 'sha256': sha256}
            documents[key] = json.loads(content.decode('utf-8'))
        readback, contract = documents['readback'], documents['contract']
        actual_key = readback.get('fileKey', readback.get('file_key')) if isinstance(readback, dict) else None
        expected_keys = {declaration.get('file_key')} if declaration.get('file_key') else set()
        for source in sources:
            parts = urlsplit(source).path.strip('/').split('/')
            if len(parts) > 1 and parts[0] in ('design', 'file'):
                expected_keys.add(parts[1])
        if isinstance(contract, dict):
            expected_keys.update(v for v in (contract.get('file_key'), contract.get('fileKey')) if v)
        if expected_keys and (len(expected_keys) != 1 or actual_key not in expected_keys):
            raise ValueError('native readback file key does not match declared Figma source')
        if strict_creation:
            selected = design_directions.require_selected(bindings_path.parent / bindings['design_directions']['selection'])
            selected_graph = design_directions.read(selected['product_graph'])
            import annotation_contract
            import design_foundations
            contract['mode'] = 'strict-creation'
            declaration_notes = contract.get('annotation_contract', {})
            if declaration_notes.get('product_graph', selected_graph) != selected_graph:
                raise ValueError('Native annotation source differs from selected graph')
            contract['annotation_contract'] = {'mode': 'strict-creation', 'product_graph': selected_graph, 'notes': declaration_notes.get('notes', annotation_contract.derive_notes(selected_graph))}
            foundation_contract = contract.get('design_foundations', design_foundations.derive_foundations(selected_graph))
            foundation_result = design_foundations.validate_foundations(readback, foundation_contract, stage='native')
        else:
            foundation_result = None
        result = native_handoff.evaluate(readback, contract, page_id)
        if foundation_result is not None:
            result['design_foundations'] = foundation_result
            if not foundation_result['ok']:
                result['errors'].append('Native usable palette/type/spacing/radius foundations incomplete')
                result.update(status='blocked', passed=False)
        result.update(inputs=report['inputs'], evidence_inputs=report['evidence_inputs'])
        report = result
        if isinstance(readback, dict) and readback.get('pageId') and readback['pageId'] != page_id:
            report['errors'].append('native readback selected page does not match native_handoff.page_id')
        for pin in (*report['inputs'].values(), *report['evidence_inputs'].values()):
            if ssot.read_local(Path(pin['path']))[0] != pin['sha256']:
                report['errors'].append('native handoff input changed during validation: ' + pin['path'])
        if report['errors']:
            report.update(status='blocked', passed=False)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        report['errors'].append('native handoff blocked: ' + str(exc))
        report.update(status='blocked', passed=False)
    return report


def reject_output_references(out, manifest_path, manifest, data, bindings, graph_path, bindings_path, *, own_manifest=False, previous_graph=None):
    # Both historical and current references matter, including currently missing paths.
    refs = [] if own_manifest else [(str(manifest_path), Path.cwd())]
    if previous_graph is not None:
        refs.append((str(previous_graph), Path.cwd()))
    def collect(value, base):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str):
                refs.append((value["path"], base))
            for child in value.values():
                collect(child, base)
        elif isinstance(value, list):
            for child in value:
                collect(child, base)
    collect(manifest, manifest_path.parent)
    nodes = data.get("nodes")
    for node in nodes if isinstance(nodes, list) else []:
        if isinstance(node, dict) and isinstance(node.get("source"), str):
            refs.append((node["source"], graph_path.parent))
    authorities = bindings.get("authorities")
    for value in authorities.values() if isinstance(authorities, dict) else ():
        if isinstance(value, str):
            refs.append((value, bindings_path.parent))
    evidence = bindings.get("evidence")
    for values in evidence.values() if isinstance(evidence, dict) else ():
        if isinstance(values, list):
            refs.extend((v, bindings_path.parent) for v in values if isinstance(v, str))
    creative = bindings.get('design_review')
    if isinstance(creative, dict) and isinstance(creative.get('receipt'), str):
        refs.append((creative['receipt'], bindings_path.parent))
        receipt_path = bindings_path.parent / creative['receipt']
        if receipt_path.is_file():
            collect(json.loads(receipt_path.read_text()), (bindings_path.parent / creative.get('project_root', '.')).resolve())
    declaration = bindings.get('native_handoff')
    if isinstance(declaration, dict):
        refs.extend((declaration[key], bindings_path.parent) for key in ('readback', 'contract')
                    if isinstance(declaration.get(key), str))
    if figma_sources(data, bindings)[0] and has_symlink(out):
        raise ValueError('Native handoff output must not traverse symlinks')
    destination = out.resolve()
    for value, base in refs:
        if not urlsplit(value).scheme:
            target = (base / value.split("#", 1)[0]).resolve()
            if target == destination or destination in target.parents:
                raise ValueError(f"Output directory contains a declared input: {value}")


def check_project(manifest_path, out, *, own_output=False, previous_graph=None, audit=False, project=None, specs=(), review=None, intent="auto"):
    manifest_path = Path(manifest_path).absolute()
    out = Path(out).absolute()
    manifest_bytes_hash, manifest_bytes = ssot.read_local(manifest_path, capture=True)
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    ssot.validate_manifest(manifest)
    base = manifest_path.parent
    inputs = {key: base / manifest["inputs"][key]["path"] for key in ("brief", "graph", "bindings")}
    graph_hash, graph_bytes = ssot.read_local(inputs["graph"], capture=True)
    data = json.loads(graph_bytes.decode("utf-8"))
    bindings_hash, bindings_bytes = ssot.read_local(inputs["bindings"], capture=True)
    bindings = json.loads(bindings_bytes.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(bindings, dict):
        raise ValueError("Graph and bindings must be objects.")
    active_intent, direction = selected_creation(data, bindings, inputs['bindings'], inputs['graph'], intent, manifest, brief_path=inputs['brief'])
    reject_output_references(out, manifest_path, manifest, data, bindings, inputs["graph"], inputs["bindings"],
                             own_manifest=own_output, previous_graph=previous_graph)
    errors, warnings = graph.validate_graph(data, strict_local=True)
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        ssot_exit = ssot.main(["check", str(manifest_path)])
    if ssot_exit == 1:
        raise ValueError(stderr.getvalue().strip() or "SSOT check failed.")
    check = json.loads(stdout.getvalue())
    if (check.get("change_explanation", {}).get("baseline_manifest_sha256") != manifest["manifest_sha256"]
            or ssot.read_local(manifest_path)[0] != manifest_bytes_hash
            or check["inputs"]["graph"]["sha256"] != graph_hash
            or check["inputs"]["bindings"]["sha256"] != bindings_hash):
        raise ValueError("Manifest, graph or bindings changed during validation; no report was generated.")
    diff = graph_diff.compare_graphs(previous_graph, inputs["graph"], manifest, check) if previous_graph else None
    audit_result = None
    if audit:
        import audit_project
        try:
            audit_result = audit_project.audit_project(project, inputs['graph'], inputs['bindings'], inputs['brief'], specs, review=review)
            audit_root = Path(audit_result['project'])
            if any(audit_result['inputs'].get(audit_project.input_name(audit_root, path.resolve())) != check['inputs'][key]['sha256']
                   for key, path in inputs.items()) or ssot.read_local(manifest_path)[0] != manifest_bytes_hash:
                raise ValueError('Manifest inputs changed during audit')
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
            audit_result = {'version': 1, 'status': 'error', 'error': str(exc), 'acceptance_claim': 'not-established'}
    native_result = evaluate_native(data, bindings, inputs['bindings'], inputs, check, strict_creation=direction is not None, direction=direction)
    app_state_result = app_states.validate(inputs['graph'], bindings.get('app_state_ssot'), inputs['bindings'].parent) if direction else None
    # Active intent and exact selected contract were checked before any report mutation.
    creative_required = active_intent in design_review.OPERATIONS
    creative_paths = [inputs['bindings'].parent / bindings.get('authorities', {}).get('implementation', '')]
    if isinstance(bindings.get('native_handoff'), dict) and isinstance(bindings['native_handoff'].get('readback'), str):
        creative_paths.append(inputs['bindings'].parent / bindings['native_handoff']['readback'])
    creative_result = design_review.evaluate(inputs['bindings'].parent, bindings.get('design_review'),
        request_text=ssot.read_local(inputs['brief'], capture=True)[1].decode('utf-8'), required=True, expected_paths=creative_paths, native_required='native_handoff' in bindings, selection_path=direction['selection_path'] if direction else None) if creative_required else None
    if not own_output:
        out.mkdir(exist_ok=False)
    summary = {"status": "invalid" if errors else "current" if ssot_exit == 0 else "stale-or-unavailable",
               "strict_local": {"errors": errors, "warnings": warnings},
               "coverage_status": "invalid" if errors else "valid",
               "freshness_status": "current" if ssot_exit == 0 else "stale-or-unavailable",
               "baseline_manifest_sha256": manifest["manifest_sha256"],
               "baseline_revision": manifest["revision"],
               "baseline_kind": "independent-first-baseline" if own_output else "existing",
               "audit_status": audit_result['status'] if audit_result else 'not-requested',
               "acceptance_claim": audit_result['acceptance_claim'] if audit_result else 'not-established',
               "graph_diff_status": "verified" if diff is not None else "not-requested",
               "ssot_exit": ssot_exit, "scope": check.get("scope", "full"),
               "graph_sha256": graph_hash,
               "limitation": "Content freshness and declared coverage only; project commands and remote state were not checked."}
    summary["freshness_unverified"] = []
    for node_id, node in check["nodes"].items():
        if node["freshness"] == "content-current":
            continue
        evidence = node["evidence"]
        reasons = set(node["reasons"])
        reasons.update(ref["availability"] + "-evidence" for ref in evidence if ref["availability"] != "local-hashed")
        if not evidence:
            reasons.add("no-evidence")
        summary["freshness_unverified"].append({
            "node": node_id, "freshness": node["freshness"], "reasons": sorted(reasons),
            "missing": sorted({ref["path"] for ref in evidence if ref["availability"] == "missing"}),
        })
    if audit_result is not None:
        summary.update(source_audit_status=audit_result.get('source_dependencies', {}).get('status', 'error'),
                       brief_audit_status=audit_result.get('brief_consistency', {}).get('status', 'error'),
                       audit_receipt='audit.json')
        graph._write_exclusive(out / 'audit.json', json.dumps(audit_result, ensure_ascii=False, indent=2) + '\n')
        graph._write_exclusive(out / 'audit.md', audit_project.markdown(audit_result) if audit_result['status'] != 'error' else '# 로컬 프로젝트 감사\n\n감사 오류: ' + audit_result['error'] + '\n')
        if not errors and audit_result['status'] != 'checked-scope-clear':
            summary['status'] = 'audit-' + audit_result['status']
    if native_result is not None:
        summary.update(native_handoff_status=native_result['status'], runtime_status='not-checked',
                       native_handoff_receipt='native-handoff.json')
        if not native_result['passed']:
            summary.update(status='native-handoff-blocked', acceptance_claim='blocked-by-native-handoff')
        graph._write_exclusive(out / 'native-handoff.json', json.dumps(native_result, ensure_ascii=False, indent=2) + '\n')
        graph._write_exclusive(out / 'screen-spec.json', json.dumps(
            {'schema': native_result['schema'], 'status': native_result['status'], 'screens': native_result['screens']},
            ensure_ascii=False, indent=2) + '\n')
        graph._write_exclusive(out / 'screen-spec.md', native_handoff.markdown(native_result))
    summary.update(workflow_graph_sha256=workflow.graph_hash(), workflow_state=State.SELECTED.value if direction else State.BRIEF.value,
                   workflow_symbol=State.SELECTED.name if direction else State.BRIEF.name, direction_selection=direction,
                   app_state_ssot=app_state_result)
    if app_state_result is not None and not app_state_result['passed']:
        summary.update(status='app-state-ssot-blocked', acceptance_claim='blocked-by-state-drift')
    summary.update(design_intent=active_intent, design_completion='not-claimed' if not creative_required else
                   'evidence-checked' if creative_result['passed'] else 'blocked',
                   design_review_status=creative_result['status'] if creative_result else 'not-requested')
    if creative_result is not None:
        summary['design_review_receipt'] = 'design-review.json'
        graph._write_exclusive(out / 'design-review.json', json.dumps(creative_result, ensure_ascii=False, indent=2) + '\n')
        if not creative_result['passed']:
            summary.update(status='design-review-blocked', acceptance_claim='blocked-by-design-review')
    graph._write_exclusive(out / "check.json", stdout.getvalue())
    if diff is not None:
        graph._write_exclusive(out / "graph-diff.json", json.dumps(diff, ensure_ascii=False, indent=2) + "\n")
    try:
        payload = trace_report.prepare(inputs["graph"], out / "check.json")
        if payload["graph_sha256"] != graph_hash:
            raise ValueError("Graph changed during report generation.")
        graph._write_exclusive(out / "trace.html", trace_report.render(payload, has_graph_diff=diff is not None))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        summary["status"] = "invalid"
        summary["trace_error"] = str(exc)
    if diff is not None:
        graph._write_exclusive(out / "graph-diff.html", graph_diff.render_diff(diff, has_trace="trace_error" not in summary))
    graph._write_exclusive(out / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    if app_state_result is not None and not app_state_result['passed']:
        return 1
    if creative_result is not None and not creative_result['passed']:
        return 1
    if native_result is not None and not native_result['passed']:
        return 1
    if summary['status'] == 'invalid' or audit_result and audit_result['status'] in ('findings', 'error'):
        return 1
    return 2 if audit_result and audit_result['status'] == 'review' else ssot_exit


def init_project(brief, graph_path, bindings_path, out, *, audit=False, project=None, specs=(), review=None, intent="auto"):
    out = Path(out).absolute()
    graph_path, bindings_path, brief = (Path(p).absolute() for p in (graph_path, bindings_path, brief))
    graph_hash, graph_bytes = ssot.read_local(graph_path, capture=True)
    data = json.loads(graph_bytes.decode("utf-8"))
    bindings_hash, bindings_bytes = ssot.read_local(bindings_path, capture=True)
    bindings = json.loads(bindings_bytes.decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(bindings, dict):
        raise ValueError("Graph and bindings must be objects.")
    selected_creation(data, bindings, bindings_path, graph_path, intent, brief_path=brief)
    errors, _ = graph.validate_graph(data, strict_local=True)
    if errors:
        raise ValueError("Strict local coverage invalid: " + "; ".join(errors))
    current = ssot.build(brief, graph_path, bindings_path, out.parent, "local-only")
    seen = set()
    def rebase(value):
        if isinstance(value, (dict, list)):
            if id(value) in seen:
                return
            seen.add(id(value))
        if isinstance(value, dict):
            if "path" in value and value.get("availability") in ("local-hashed", "missing"):
                value["path"] = os.path.relpath(out.parent / value["path"], out)
            for item in value.values():
                rebase(item)
        elif isinstance(value, list):
            for item in value:
                rebase(item)
    rebase(current)
    current = ssot.compare(current, None)
    current["scope"] = "local-only"
    current.update(revision=1, parent_sha256=None, design_review_policy=1,
                   design_intent=intent if intent != 'auto' else ('create' if design_review.frontend(data, bindings) or 'design_review' in bindings else 'technical'))
    current["manifest_sha256"] = ssot.digest(current)
    manifest_path = out / "manifest-001.json"
    reject_output_references(out, manifest_path, current, data, bindings, graph_path, bindings_path, own_manifest=True)
    if (current["inputs"]["graph"]["sha256"] != graph_hash
            or current["inputs"]["bindings"]["sha256"] != bindings_hash
            or ssot.read_local(graph_path)[0] != graph_hash):
        raise ValueError("Graph or bindings changed during initialization.")
    out.mkdir(exist_ok=False)
    graph._write_exclusive(manifest_path, json.dumps(current, ensure_ascii=True, sort_keys=True, indent=2) + "\n")
    graph._write_exclusive(out / "baseline-graph.json", graph_bytes.decode("utf-8"))
    return check_project(manifest_path, out, own_output=True, audit=audit, project=project, specs=specs, review=review, intent=intent)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--intent", choices=("auto", "create", "redesign", "refine", "inspect", "technical"), default="auto", help="auto requires creative evidence for frontend creation; inspect/technical never claim design completion")
    parser.add_argument("--init", action="store_true", help="create an independent local-only first baseline")
    parser.add_argument("--brief", type=Path)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--previous-graph", type=Path, help="exact graph pinned by the existing manifest")
    parser.add_argument('--audit', action='store_true', help='audit source dependencies and requirement contradictions separately from SSOT freshness')
    parser.add_argument('--project', type=Path, help='explicit local project root for --audit')
    parser.add_argument('--spec', action='append', default=[], type=Path, help='additional active requirement document for --audit')
    parser.add_argument('--review', type=Path, help='pinned reviewer candidates for --audit')
    parser.add_argument("--out", required=True, type=Path, help="new output directory; parent must exist")
    args = parser.parse_args()
    if args.audit and not args.project:
        parser.error('--audit requires --project')
    if not args.audit and (args.project or args.spec or args.review):
        parser.error('--project, --spec and --review require --audit')
    if args.init:
        if args.manifest or args.previous_graph or not all((args.brief, args.graph, args.bindings)):
            parser.error("--init requires --brief, --graph and --bindings; it cannot be combined with a manifest or --previous-graph")
    elif not args.manifest or any((args.brief, args.graph, args.bindings)):
        parser.error("supply a manifest, or use --init with all three input flags")
    try:
        result = (init_project(args.brief, args.graph, args.bindings, args.out, audit=args.audit, project=args.project, specs=args.spec, review=args.review, intent=args.intent) if args.init else
                  check_project(args.manifest, args.out, previous_graph=args.previous_graph, audit=args.audit, project=args.project, specs=args.spec, review=args.review, intent=args.intent))
        print(f"Report: {args.out / 'summary.json'}")
        return result
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
