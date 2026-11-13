#!/usr/bin/env python3
"""Build a per-member, evidence-separated audit of the pinned Plugin API inventory."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'library' / 'figma-api' / 'audit'
DATASET = AUDIT / 'members.json'
REPORT = AUDIT / 'report.md'
CURATED = AUDIT / 'evidence' / 'curated.json'
BASELINE_REF = 'v0.27.1'
BASELINE_COMMIT = '42379a56d677ad29296ae3ae6495742a11fbaf43'
BASELINE_TAG_OBJECT = '1c6280fcdf049ed38ec900ec37f3b08e8e66cfaf'
BASELINE_TREE = '0a62cb4cc395ac41ed522927cafce0d3c0f4cdb7'
CANDIDATE_REF = '4c3b39218e5b214e0e21b762678a23dc55a3cd1f'
CANDIDATE_TREE = '779be49d9fe2068b763d62dcdc23505e9059f83d'
API_INVENTORY_REF = 'fad40b21f8fbb14209f50b3029bd656d40bbb1fe'
MEMBER_STATUSES = ('observed', 'implemented', 'compile_only', 'unsupported',
                   'verified_unimplemented', 'unresolved')
EVIDENCE_DIR = AUDIT / 'evidence'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def git(*args, text=True):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True,
                          text=text).stdout


def snapshot_pins(ref):
    return {'ref': ref, 'commit': git('rev-parse', ref + '^{commit}').strip(),
            'tree': git('rev-parse', ref + '^{tree}').strip()}


def read_blob(ref, path):
    return git('show', f'{ref}:{path}', text=False)


def tracked_paths(ref, prefix):
    command = ['ls-tree', '-r', '--name-only', ref]
    if prefix:
        command += ['--', prefix]
    raw = git(*command)
    return [line for line in raw.splitlines() if line]


def extract_runtime_snapshot(ref, destination):
    paths = tracked_paths(ref, 'figma-bridge')
    paths += tracked_paths(ref, 'library/figma-recipes')
    paths += [path for path in tracked_paths(ref, 'tools') if path == 'tools/workspace_recipes.py']
    archive = subprocess.run(['git', 'archive', '--format=tar', ref, *sorted(set(paths))],
                             cwd=ROOT, check=True, capture_output=True).stdout
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not member.isfile():
                if member.isdir():
                    continue
                raise ValueError(f'Unexpected runtime snapshot entry: {member.name}')
            output = destination.joinpath(*path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = bundle.extractfile(member).read()
            output.write_bytes(raw)
    return destination


def runtime_sources(snapshot):
    sources = []
    bridge = snapshot / 'figma-bridge'
    if bridge.is_dir():
        sources.extend({'path': path.relative_to(snapshot).as_posix(), 'text': path.read_text()}
                       for path in sorted(bridge.glob('*.js')) if path.is_file())
    recipes = snapshot / 'library' / 'figma-recipes'
    bundle_path = recipes / 'bundle.json'
    if bundle_path.is_file():
        bundle = json.loads(bundle_path.read_text())
        for recipe in bundle.get('recipes', []):
            entry = recipes / recipe['entry']
            if not entry.is_file():
                raise ValueError(f'Missing shipped recipe entry: {recipe["entry"]}')
            sources.append({'path': entry.relative_to(snapshot).as_posix(), 'text': entry.read_text()})
    recipes_tool = snapshot / 'tools' / 'workspace_recipes.py'
    if recipes_tool.is_file():
        spec = importlib.util.spec_from_file_location(f'audit_workspace_recipes_{snapshot.name}', recipes_tool)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(snapshot / 'tools'))
        try:
            spec.loader.exec_module(module)
            sources.append({'path': 'tools/workspace_recipes.py::dispatch_source',
                            'text': module.dispatch_source()})
        finally:
            sys.path.remove(str(snapshot / 'tools'))
    return sources


def scan_references(snapshot, typescript):
    sources = runtime_sources(snapshot)
    scanner = snapshot / 'library' / 'figma-api' / 'scan.cjs'
    if not scanner.is_file():
        # The v0.27.1 tree predates the inventory. Reuse the candidate scanner, pinned in this repo.
        scanner = ROOT / 'library' / 'figma-api' / 'scan.cjs'
    result = subprocess.run(['node', str(scanner), str(Path(typescript).resolve())],
        input=json.dumps(sources, ensure_ascii=False), text=True, capture_output=True, check=True)
    rows = json.loads(result.stdout)
    source_hashes = [{'path': row['path'], 'sha256': hashlib.sha256(row['text'].encode()).hexdigest()}
                     for row in sources]
    return rows, source_hashes


def test_mentions(ref, members):
    paths = [path for path in tracked_paths(ref, 'tests')
             if path.endswith(('.py', '.cjs', '.js', '.mjs', '.ts'))]
    mentions = {row['id']: {'total': 0, 'examples': []} for row in members}
    indexed = {}
    route_index = {}
    for row in members:
        indexed.setdefault(row['name'], []).append(row['id'])
        for route in row.get('routes', []):
            route_index.setdefault(route, []).append(row['id'])
    for path in paths:
        try:
            text = read_blob(ref, path).decode('utf-8')
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for route, member_id in route_index.items():
                if route in line:
                    for identity in member_id:
                        append_mention(mentions[identity], path, line_number, 'qualified-route-mention-only')
            identifiers = set(re.findall(r'(?<![A-Za-z0-9_$])[A-Za-z_$][A-Za-z0-9_$]*(?![A-Za-z0-9_$])', line))
            for name in sorted(identifiers):
                member_id = indexed.get(name)
                for identity in member_id or []:
                    append_mention(mentions[identity], path, line_number, 'member-name-mention-only')
    return mentions


def append_mention(record, path, line, match):
    record['total'] += 1
    if len(record['examples']) < 30:
        record['examples'].append({'path': path, 'line': line, 'match': match})


def reference_summary(rows, limit=5):
    return {'count': len(rows), 'examples': [
        {key: row[key] for key in ('path', 'line', 'column', 'syntax', 'usage') if key in row}
        for row in rows[:limit]]}


def mention_summary(row):
    return {'count': row['total'], 'examples': row['examples'][:3]}


def key_for(member):
    shape = {key: member.get(key) for key in ('owner', 'name', 'signature')}
    digest = hashlib.sha256(json.dumps(shape, sort_keys=True, ensure_ascii=False,
                                       separators=(',', ':')).encode()).hexdigest()
    return 'member:' + digest


def owner_surfaces(catalog):
    runtime_routes = {row['interface']: row['routes'] for row in catalog.get('namespaces', [])}
    runtime_nodes = {row['name'] for row in catalog.get('nodes', [])}
    declarations = {row['name']: row for row in catalog.get('declarations', [])}
    changed = True
    while changed:
        changed = False
        for name in tuple(runtime_nodes):
            for parent in declarations.get(name, {}).get('extends', []):
                if parent not in runtime_nodes:
                    runtime_nodes.add(parent)
                    changed = True
    return runtime_routes, runtime_nodes, declarations


def classify_surface(member, runtime_routes, runtime_nodes, declarations):
    owner = member['owner']
    if owner in runtime_routes:
        return {'class': 'runtime-api-member', 'applicability': 'runtime',
                'basis': 'owner has an API namespace route from PluginAPI'}
    if owner in runtime_nodes:
        return {'class': 'runtime-object-member', 'applicability': 'runtime',
                'basis': 'owner is a node or an inherited node mixin in the catalog'}
    declaration = declarations.get(owner)
    if declaration and declaration.get('kind') == 'TypeAliasDeclaration':
        return {'class': 'type-contract-member', 'applicability': 'type-only-or-value-shape',
                'basis': 'owner is a declared TypeScript type alias, not an API namespace route'}
    return {'class': 'unresolved-owner-member', 'applicability': 'unresolved',
            'basis': 'no generated API namespace or concrete node/mixin relation establishes runtime applicability'}


def _merge_status(left, right, identity):
    if left == right:
        return left
    if left == 'unresolved':
        return right
    if right == 'unresolved':
        return left
    positive = {'compile_only': 1, 'implemented': 2, 'observed': 3}
    if left in positive and right in positive:
        return max((left, right), key=positive.__getitem__)
    raise ValueError(f'Conflicting curated statuses for {identity}: {left} vs {right}')


def _merge_evidence_rows(left, right):
    rows = []
    for value in (left or [], right or []):
        rows.extend(value if isinstance(value, list) else [value])
    unique = {canonical(row): row for row in rows}
    return [unique[key] for key in sorted(unique)]


def _merge_member(left, right):
    identity = (left['owner'], left['name'], left['signature'])
    merged = dict(left)
    merged['status'] = _merge_status(left['status'], right['status'], identity)
    baseline_left = left.get('baseline_status', 'unresolved')
    baseline_right = right.get('baseline_status', 'unresolved')
    merged['baseline_status'] = _merge_status(baseline_left, baseline_right, identity)
    for field in ('applicability', 'baseline_applicability'):
        a, b = left.get(field), right.get(field)
        if a and b and a != b and 'unresolved' not in (a, b):
            raise ValueError(f'Conflicting curated applicability for {identity}: {a} vs {b}')
        merged[field] = b if a in (None, 'unresolved') else a
    fields = ('code_evidence', 'test_evidence', 'runtime_evidence', 'limitation_evidence',
              'baseline_code_evidence', 'baseline_test_evidence', 'baseline_runtime_evidence',
              'baseline_limitation_evidence')
    for field in fields:
        if field in left or field in right:
            merged[field] = _merge_evidence_rows(left.get(field), right.get(field))
    for field in ('absence_review', 'baseline_absence_review'):
        a, b = left.get(field), right.get(field)
        if a and b and a != b:
            raise ValueError(f'Conflicting absence review for {identity}')
        if a or b:
            merged[field] = a or b
    scopes = sorted({value for value in (left.get('evidence_scope'), right.get('evidence_scope')) if value})
    if scopes:
        merged['evidence_scope'] = scopes
    merged['evidence_files'] = sorted(set(left.get('evidence_files', [])) | set(right.get('evidence_files', [])))
    return merged


def _merge_scope_finding(left, right):
    if left['id'] != right['id']:
        raise ValueError('Scope finding ID mismatch')
    merged = dict(left)
    for field in ('status', 'baseline_status', 'candidate_status'):
        a = left.get(field, 'unresolved')
        b = right.get(field, 'unresolved')
        merged[field] = _merge_status(a, b, ('scope finding', left['id'], field))
    merged['evidence'] = _merge_evidence_rows(left.get('evidence'), right.get('evidence'))
    merged['scope'] = left.get('scope') or right.get('scope')
    notes = sorted({value for value in (left.get('note'), right.get('note')) if value})
    if notes:
        merged['note'] = ' '.join(notes)
    merged['evidence_files'] = sorted(set(left.get('evidence_files', [])) | set(right.get('evidence_files', [])))
    return merged


def load_curated(candidate_pins, baseline_pins):
    members = {}
    findings = {}
    sources = []
    for path in sorted(EVIDENCE_DIR.glob('*.json')):
        curated = json.loads(path.read_text())
        if curated.get('schema') != 'figma-flow-api-audit-curated-evidence-v1':
            continue
        for key, expected in (('candidate', candidate_pins), ('baseline', baseline_pins)):
            actual = curated.get(key, {})
            if any(actual.get(field) != expected[field] for field in ('ref', 'commit', 'tree')):
                raise ValueError(f'{path.name} {key} pin differs from the audit snapshot')
        source = {'path': path.relative_to(ROOT).as_posix(),
                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        sources.append(source)
        for row in curated.get('members', []):
            status = row.get('status')
            if status not in MEMBER_STATUSES:
                raise ValueError(f'Unknown curated status for {row.get("owner")}.{row.get("name")}')
            identity = (row['owner'], row['name'], row['signature'])
            copy = dict(row)
            copy['evidence_files'] = [source['path']]
            members[identity] = _merge_member(members[identity], copy) if identity in members else copy
        for row in curated.get('scope_findings', []):
            if row.get('status', 'unresolved') not in MEMBER_STATUSES:
                raise ValueError(f'Unknown scope finding status: {row.get("id")}')
            copy = dict(row)
            copy['evidence_files'] = [source['path']]
            findings[row['id']] = _merge_scope_finding(findings[row['id']], copy) if row['id'] in findings else copy
    return {'members': members, 'scope_findings': [findings[key] for key in sorted(findings)],
            'evidence_sources': sources}


def validate_evidence(member, evidence, source_blobs):
    status = evidence['status']
    code = evidence.get('code_evidence', [])
    tests = evidence.get('test_evidence', [])
    runtime = evidence.get('runtime_evidence', [])
    limitations = evidence.get('limitation_evidence', [])
    absence = evidence.get('absence_review')
    if status == 'implemented' and (not code or not tests):
        raise ValueError(f'Implemented needs code and test evidence: {member["owner"]}.{member["name"]}')
    if status == 'observed' and (not code or not runtime):
        raise ValueError(f'Observed needs source and runtime evidence: {member["owner"]}.{member["name"]}')
    if status in ('observed', 'implemented') and evidence.get('applicability') not in ('runtime', 'type-only'):
        raise ValueError(f'Supported rows need runtime or type-only applicability evidence: {member["owner"]}.{member["name"]}')
    if status == 'compile_only' and not tests:
        raise ValueError(f'Compile-only needs an exact compiler/test record: {member["owner"]}.{member["name"]}')
    if status == 'unsupported' and not limitations:
        raise ValueError(f'Unsupported needs explicit scoped limitation evidence: {member["owner"]}.{member["name"]}')
    if status == 'verified_unimplemented' and not (absence and all(absence.get(key) for key in ('feature_route', 'declaration_lookup', 'scope'))):
        raise ValueError(f'Unimplemented needs route, declaration and scope checks: {member["owner"]}.{member["name"]}')
    if evidence.get('applicability') not in (None, 'runtime', 'type-only', 'unresolved'):
        raise ValueError(f'Unknown applicability classification: {evidence.get("applicability")}')
    for row in code:
        pin_ref = row.get('ref', CANDIDATE_REF)
        pin = git('rev-parse', pin_ref + '^{commit}').strip()
        if pin not in source_blobs:
            source_blobs[pin] = {}
        if row.get('path') not in source_blobs[pin]:
            try:
                source_blobs[pin][row['path']] = read_blob(pin, row['path']).decode('utf-8')
            except (subprocess.CalledProcessError, UnicodeDecodeError):
                raise ValueError(f'Code evidence source is absent or non-text: {row.get("path")}')
        source = source_blobs[pin][row['path']]
        if status in ('implemented', 'observed') and row.get('symbol') and row['symbol'] not in source:
            symbol = re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*', row['symbol'])
            terminal = symbol[-1] if symbol else ''
            if not terminal or terminal not in source:
                raise ValueError(f'Code evidence symbol not found in {row["path"]}: {row["symbol"]}')
    for row in tests:
        pin_ref = row.get('ref', CANDIDATE_REF)
        pin = git('rev-parse', pin_ref + '^{commit}').strip()
        if pin not in source_blobs:
            source_blobs[pin] = {}
        if row.get('path') not in source_blobs[pin]:
            try:
                source_blobs[pin][row['path']] = read_blob(pin, row['path']).decode('utf-8')
            except (subprocess.CalledProcessError, UnicodeDecodeError):
                raise ValueError(f'Test evidence source is absent or non-text: {row.get("path")}')
        source = source_blobs[pin][row['path']]
        if row.get('test') and row['test'] not in source:
            raise ValueError(f'Test evidence assertion not found in {row["path"]}: {row["test"]}')
    for row in runtime:
        pin_ref = row.get('ref', CANDIDATE_REF)
        pin = git('rev-parse', pin_ref + '^{commit}').strip()
        if pin not in source_blobs:
            source_blobs[pin] = {}
        path = row.get('source')
        if not path or path not in source_blobs[pin]:
            try:
                source_blobs[pin][path] = read_blob(pin, path).decode('utf-8')
            except (subprocess.CalledProcessError, UnicodeDecodeError, TypeError):
                raise ValueError(f'Runtime evidence source is absent or non-text: {path}')
        if not row.get('action') or not row.get('observed_result'):
            raise ValueError(f'Runtime evidence needs an action and observed result: {path}')
    limitation_rows = limitations if isinstance(limitations, list) else [limitations] if limitations else []
    for row in limitation_rows:
        pin_ref = row.get('ref', CANDIDATE_REF)
        pin = git('rev-parse', pin_ref + '^{commit}').strip()
        if pin not in source_blobs:
            source_blobs[pin] = {}
        path = row.get('source')
        if not path:
            raise ValueError(f'Limitation evidence requires an exact source: {member["owner"]}.{member["name"]}')
        if path not in source_blobs[pin]:
            try:
                source_blobs[pin][path] = read_blob(pin, path).decode('utf-8')
            except (subprocess.CalledProcessError, UnicodeDecodeError, TypeError):
                raise ValueError(f'Limitation source is absent or non-text: {path}')


def validate_scope_findings(findings, source_blobs):
    for finding in findings:
        if not finding.get('id') or not finding.get('scope'):
            raise ValueError('Scoped feature findings need an ID and exact scope')
        for key in ('status', 'baseline_status', 'candidate_status'):
            if key in finding and finding[key] not in MEMBER_STATUSES:
                raise ValueError(f'Unknown scoped finding status: {finding.get("id")}')
        if finding.get('status') == 'verified_unimplemented':
            absence = finding.get('absence_review', {})
            if not all(absence.get(key) for key in ('feature_route', 'declaration_lookup', 'scope')):
                raise ValueError(f'Unimplemented finding lacks route/declaration scope review: {finding["id"]}')
        for evidence in finding.get('evidence', []):
            ref = evidence.get('ref', CANDIDATE_REF)
            commit = git('rev-parse', ref + '^{commit}').strip()
            path = evidence.get('path')
            if not path:
                raise ValueError(f'Scoped finding evidence needs an exact source path: {finding["id"]}')
            source_blobs.setdefault(commit, {})
            if path not in source_blobs[commit]:
                try:
                    source_blobs[commit][path] = read_blob(commit, path).decode('utf-8')
                except (subprocess.CalledProcessError, UnicodeDecodeError):
                    raise ValueError(f'Scoped finding source is absent or non-text: {path}')
            if not evidence.get('action'):
                raise ValueError(f'Scoped finding evidence needs an action: {finding["id"]}')


def assemble(candidate_ref, baseline_ref, typescript):
    baseline_pins = snapshot_pins(baseline_ref)
    candidate_pins = snapshot_pins(candidate_ref)
    api_candidate_commit = git('rev-parse', API_INVENTORY_REF + '^{commit}').strip()
    api_index_bytes = read_blob(candidate_ref, 'library/figma-api/index.json')
    api_index = json.loads(api_index_bytes)
    candidate_plugin = json.loads(read_blob(candidate_ref, 'plugin.json'))
    baseline_plugin = json.loads(read_blob(baseline_ref, 'plugin.json'))
    api_source = json.loads(read_blob(candidate_ref, 'library/figma-api/source.json'))
    if api_index.get('source') != api_source:
        raise ValueError('Candidate API index provenance differs from source.json')
    for filename, digest in api_source.get('files', {}).items():
        actual = hashlib.sha256(read_blob(candidate_ref, 'library/figma-api/' + filename)).hexdigest()
        if actual != digest:
            raise ValueError(f'Candidate pinned API source hash differs: {filename}')
    catalog_blob = git('rev-parse', candidate_ref + ':library/figma-api/index.json').strip()
    introduced_catalog_blob = git('rev-parse', API_INVENTORY_REF + ':library/figma-api/index.json').strip()
    if catalog_blob != introduced_catalog_blob:
        raise ValueError('Candidate catalog differs from the pinned inventory-introduction commit')
    if len(api_index.get('members', [])) != 1382:
        raise ValueError('Pinned candidate API catalog no longer has 1,382 rows; review the audit scope')
    member_identities = [(row['owner'], row['name'], row['signature']) for row in api_index['members']]
    if len(set(member_identities)) != len(member_identities):
        raise ValueError('Candidate catalog contains duplicate owner/member/signature keys')
    widget_source = None
    try:
        widget_source = json.loads(read_blob(candidate_ref, 'library/figma-widget/source.json'))
        for filename, digest in widget_source.get('files', {}).items():
            actual = hashlib.sha256(read_blob(candidate_ref, 'library/figma-widget/' + filename)).hexdigest()
            if actual != digest:
                raise ValueError(f'Candidate pinned Widget API source hash differs: {filename}')
    except subprocess.CalledProcessError:
        widget_source = None
    if candidate_pins['tree'] != CANDIDATE_TREE and candidate_ref == CANDIDATE_REF:
        raise ValueError('Candidate tree pin changed')
    if baseline_pins['tree'] != BASELINE_TREE and baseline_ref == BASELINE_REF:
        raise ValueError('Baseline tree pin changed')

    with tempfile.TemporaryDirectory(prefix='figma-api-audit-') as temporary:
        scratch = Path(temporary)
        baseline_snapshot = extract_runtime_snapshot(baseline_ref, scratch / 'baseline')
        candidate_snapshot = extract_runtime_snapshot(candidate_ref, scratch / 'candidate')
        baseline_refs, baseline_hashes = scan_references(baseline_snapshot, typescript)
        candidate_refs, candidate_hashes = scan_references(candidate_snapshot, typescript)
        scanner_path = candidate_snapshot / 'library' / 'figma-api' / 'scan.cjs'
        if not scanner_path.is_file():
            scanner_path.parent.mkdir(parents=True, exist_ok=True)
            scanner_path.write_bytes(read_blob(candidate_ref, 'library/figma-api/scan.cjs'))

        source_blobs = {baseline_pins['commit']: {}, candidate_pins['commit']: {}}

        curated = load_curated(candidate_pins, baseline_pins)
        curated_members = curated['members']
        scope_findings = curated['scope_findings']
        validate_scope_findings(scope_findings, source_blobs)
        test_rows = test_mentions(candidate_ref, api_index['members'])
        baseline_by_route, candidate_by_route = {}, {}
        for ref in baseline_refs:
            if ref.get('qualified'):
                baseline_by_route.setdefault(ref['qualified'], []).append(ref)
        for ref in candidate_refs:
            if ref.get('qualified'):
                candidate_by_route.setdefault(ref['qualified'], []).append(ref)
        generic_baseline, generic_candidate = {}, {}
        for row in baseline_refs:
            if not row.get('qualified'):
                generic_baseline.setdefault(row['name'], []).append(row)
        for row in candidate_refs:
            if not row.get('qualified'):
                generic_candidate.setdefault(row['name'], []).append(row)

        runtime_routes, runtime_nodes, declarations = owner_surfaces(api_index)
        rows = []
        for member in sorted(api_index['members'], key=lambda row: (row['owner'], row['name'], row['signature'])):
            member_key = key_for(member)
            identity = (member['owner'], member['name'], member['signature'])
            proof = curated_members.get(identity)
            if proof:
                candidate_proof = {**proof, 'status': proof['status']}
                validate_evidence(member, candidate_proof, source_blobs)
                baseline_proof = {
                    'status': proof.get('baseline_status', 'unresolved'),
                    'applicability': proof.get('baseline_applicability', proof.get('applicability', 'unresolved')),
                    'code_evidence': proof.get('baseline_code_evidence', []),
                    'test_evidence': proof.get('baseline_test_evidence', []),
                    'runtime_evidence': proof.get('baseline_runtime_evidence', []),
                    'limitation_evidence': proof.get('baseline_limitation_evidence', []),
                    'absence_review': proof.get('baseline_absence_review'),
                }
                if baseline_proof['status'] != 'unresolved' or any(
                        baseline_proof[key] for key in ('code_evidence', 'test_evidence', 'runtime_evidence', 'limitation_evidence', 'absence_review')):
                    validate_evidence(member, baseline_proof, source_blobs)
                applicability = proof.get('applicability')
            else:
                candidate_proof = {'status': 'unresolved'}
                baseline_proof = {'status': 'unresolved'}
                applicability = None
            surface = classify_surface(member, runtime_routes, runtime_nodes, declarations)
            if applicability:
                surface['applicability'] = applicability
                surface['basis'] += '; curated classification supplied'
            route_refs = [ref for route in member.get('routes', []) for ref in candidate_by_route.get(route, [])]
            base_refs = [ref for route in member.get('routes', []) for ref in baseline_by_route.get(route, [])]
            test_refs = test_rows.get(member['id'], [])
            rows.append({
                'key': member_key,
                'owner': member['owner'], 'name': member['name'], 'signature': member['signature'],
                'kind': member['kind'], 'optional': member['optional'], 'readonly': member['readonly'],
                'type_surface': surface,
                'official_declaration': {
                    'api_version': api_source.get('version'), 'upstream_ref': api_source.get('ref'),
                    'source_url': member.get('source_url'), 'line': member.get('line'),
                    'end_line': member.get('end_line'),
                    'value_type': member.get('value_type'), 'restrictions': member.get('restrictions', []),
                    'restricted_access': member.get('restricted_access', False),
                    'documented_editors': member.get('documented_editors', []),
                    'required_permissions': member.get('required_permissions', []),
                },
                'route': {'paths': member.get('routes', []), 'execution': 'not-executed'},
                'release_status': {
                    'baseline': {
                        'status': baseline_proof['status'],
                        'basis': ('curated v0.27.1 evidence' if baseline_proof['status'] != 'unresolved' else
                                  'unresolved; no historical proof supplied for this candidate API key'),
                        'evidence': baseline_proof if baseline_proof['status'] != 'unresolved' else None,
                    },
                    'candidate': {
                        'status': candidate_proof['status'],
                        'basis': ('curated candidate evidence' if proof else
                                  'unresolved; declaration presence, route names and static references do not prove support'),
                        'evidence': proof,
                    },
                },
                'evidence': {
                    'curated': proof or None,
                    'candidate_static_references': reference_summary(route_refs),
                    'baseline_static_references': reference_summary(base_refs),
                    'candidate_unresolved_name_references': reference_summary(generic_candidate.get(member['name'], []), 3),
                    'baseline_unresolved_name_references': reference_summary(generic_baseline.get(member['name'], []), 3),
                    'test_mentions_only': mention_summary(test_refs),
                },
                'release_delta': {
                    'baseline_catalog_member': False,
                    'baseline_exact_route_reference_count': len(base_refs),
                    'candidate_exact_route_reference_count': len(route_refs),
                    'static_route_change': ('added' if route_refs and not base_refs else
                        'removed' if base_refs and not route_refs else
                        'changed' if len(route_refs) != len(base_refs) else 'same-or-none'),
                    'interpretation': 'Static route reference delta only; it does not prove implementation or runtime support.',
                },
            })

    release_counts = {release: {status: sum(row['release_status'][release]['status'] == status for row in rows)
                                for status in MEMBER_STATUSES}
                      for release in ('baseline', 'candidate')}
    runtime_rows = [row for row in rows if row['type_surface']['applicability'] == 'runtime']
    unresolved_runtime = [row for row in rows if row['type_surface']['applicability'] == 'unresolved']

    def bounds(release):
        status = lambda row: row['release_status'][release]['status']
        code_lower = sum(status(row) in ('observed', 'implemented') for row in runtime_rows)
        observed_lower = sum(status(row) == 'observed' for row in runtime_rows)
        member_code_lower = sum(status(row) in ('observed', 'implemented') and
                                row['type_surface']['applicability'] in ('runtime', 'type-only') for row in rows)
        member_observed_lower = sum(status(row) == 'observed' for row in rows)
        type_only_observed = sum(status(row) == 'observed' and
                                 row['type_surface']['applicability'] == 'type-only' for row in rows)
        possible_surface = [row for row in rows if row['type_surface']['applicability'] != 'type-only']
        possible = [row for row in possible_surface if status(row) in ('compile_only', 'unresolved')]
        return {'code_implemented_lower_bound': code_lower,
                'code_implemented_lower_bound_denominator': len(runtime_rows),
                'native_observed_lower_bound': observed_lower,
                'native_observed_lower_bound_denominator': len(runtime_rows),
                'api_member_implemented_lower_bound': member_code_lower,
                'api_member_implemented_lower_bound_denominator': len(rows),
                'api_member_native_observed_lower_bound': member_observed_lower,
                'api_member_native_observed_lower_bound_denominator': len(rows),
                'type_only_native_observed_members': type_only_observed,
                'possible_upper_bound': code_lower + len(possible),
                'possible_upper_bound_denominator': len(possible_surface),
                'explicit_type_only_members_excluded_from_runtime_upper_bound': len(rows) - len(possible_surface),
                'upper_bound_includes_unresolved_runtime_applicability': sum(
                    row['type_surface']['applicability'] == 'unresolved' and
                    status(row) in ('compile_only', 'unresolved') for row in rows)}

    verified_pairs = [row for row in rows if row['release_status']['baseline']['status'] != 'unresolved'
                      and row['release_status']['candidate']['status'] != 'unresolved']
    status_changes = sum(row['release_status']['baseline']['status'] != row['release_status']['candidate']['status']
                         for row in verified_pairs)
    dataset = {
        'schema': 'figma-flow-plugin-api-member-audit-v1',
        'evidence_policy': {
            'statuses': list(MEMBER_STATUSES),
            'disjoint_status_totals': True,
            'declaration_presence_is_support': False,
            'static_name_or_route_reference_is_support': False,
            'no_static_reference_means_unimplemented': False,
            'verified_unimplemented_requires': ['exact feature route review', 'exact declaration lookup', 'declared scope'],
            'implemented_requires': ['exact source path, symbol and action', 'automated test path, test and assertion'],
            'observed_requires': ['exact source path, symbol and action', 'actual runtime source, action and result'],
            'bounds': 'Code support lower bound counts observed+implemented runtime rows. Native observed lower bound counts observed rows only. Possible upper bound adds compile-only and unresolved rows whose applicability is not explicitly type-only.',
        },
        'curated_evidence_sources': curated['evidence_sources'],
        'comparison': {
            'baseline': {**snapshot_pins(baseline_ref), 'ref': baseline_ref,
                         'tag_object': git('rev-parse', baseline_ref).strip(),
                         'plugin_version': baseline_plugin.get('version'),
                         'api_catalog_present': False},
            'candidate': {**snapshot_pins(candidate_ref), 'ref': candidate_ref,
                          'plugin_version': candidate_plugin.get('version'),
                          'api_catalog_member_count': len(api_index['members']),
                          'api_inventory_introduced_commit': api_candidate_commit,
                          'api_source_version': api_source.get('version'),
                          'api_source_ref': api_source.get('ref'),
                          'api_source_files': api_source.get('files')},
            'baseline_static_source_hashes': baseline_hashes,
            'candidate_static_source_hashes': candidate_hashes,
            'release_comparison_limit': 'v0.27.1 has no library/figma-api catalog. Its runtime source is compared only against candidate member routes; this is not an API declaration-version comparison.',
            'post_candidate_runtime_follow_up': {
                'commit': git('rev-parse', '42752d5^{commit}').strip(),
                'tree': git('rev-parse', '42752d5^{tree}').strip(),
                'scope': 'Updates existing native instance label writes to use actual template branches; changes figma-bridge/native_provision.js and related source/test/verification files.',
                'api_categories_added': [],
                'audit_cutoff': candidate_ref,
                'interpretation': 'This follow-up is outside the pinned 4c3b392 scan. Its source validation/readback is later evidence, not retroactive evidence for the 4c3b392 snapshot.',
            },
        },
        'counts': {'members': len(rows), 'release_statuses': release_counts,
                   'type_surface': {value: sum(row['type_surface']['class'] == value for row in rows)
                                    for value in sorted({row['type_surface']['class'] for row in rows})},
                   'runtime_applicable_rows': len(runtime_rows),
                   'runtime_applicability_unresolved_rows': len(unresolved_runtime),
                   'rows_with_status_in_both_releases': len(verified_pairs),
                   'known_status_changes_between_releases': status_changes},
        'support_bounds': {release: bounds(release) for release in ('baseline', 'candidate')},
        'scoped_feature_findings': scope_findings,
        'denominator_exclusions': ([{
            'id': 'figma-widget-api',
            'status': 'separate-api-surface-not-in-this-denominator',
            'source_version': widget_source.get('version'),
            'source_ref': widget_source.get('ref'),
            'source_hashes': widget_source.get('files'),
            'member_audit_count': None,
            'reason': 'Widget API declarations have a separate pinned source under library/figma-widget. They are not part of the @figma/plugin-typings Plugin API denominator.',
        }] if widget_source else []),
        'members': rows,
    }
    return dataset


def report(dataset):
    comparison = dataset['comparison']
    counts = dataset['counts']
    bounds = dataset['support_bounds']
    status_rows = '\n'.join(
        f"| `{status}` | {counts['release_statuses']['baseline'][status]} | "
        f"{counts['release_statuses']['candidate'][status]} |"
        for status in MEMBER_STATUSES)
    surface_rows = '\n'.join(f"| `{key}` | {value} |" for key, value in counts['type_surface'].items())
    bound_rows = '\n'.join(
        f"| {release} | {value['code_implemented_lower_bound']} / {value['code_implemented_lower_bound_denominator']} | "
        f"{value['native_observed_lower_bound']} / {value['native_observed_lower_bound_denominator']} | "
        f"{value['api_member_implemented_lower_bound']} / {value['api_member_implemented_lower_bound_denominator']} | "
        f"{value['api_member_native_observed_lower_bound']} / {value['api_member_native_observed_lower_bound_denominator']} | "
        f"{value['possible_upper_bound']} / {value['possible_upper_bound_denominator']} |"
        for release, value in bounds.items())
    findings = dataset['scoped_feature_findings']
    finding_rows = '\n'.join(
        f"| `{row['id']}` | {row.get('baseline_status', 'unresolved')} | "
        f"{row.get('candidate_status', row.get('status', 'unresolved'))} | {row.get('scope', '')} |"
        for row in findings)
    exclusions = dataset['denominator_exclusions']
    exclusion_lines = '\n'.join(
        f"- **{row['id']}** is excluded. Source {row['source_version']} at `{row['source_ref']}` is pinned separately. {row['reason']}"
        for row in exclusions)
    follow_up = comparison['post_candidate_runtime_follow_up']
    evidence_sources = '\n'.join(f"- `{row['path']}` SHA-256 `{row['sha256']}`"
                                 for row in dataset['curated_evidence_sources']) or '- No curated evidence files were supplied.'
    verified_unimplemented = [row for row in dataset['members']
                              if row['release_status']['candidate']['status'] == 'verified_unimplemented']
    unimplemented_rows = '\n'.join(
        f"| `{row['owner']}.{row['name']}` | {row['release_status']['candidate']['evidence']['absence_review']['scope']} |"
        for row in verified_unimplemented)
    return f'''# Figma Plugin API member audit

This report audits each of the {counts['members']:,} distinct candidate owner/member/signature keys. The catalog is a declaration inventory, not an implementation inventory. The audit keeps candidate source references, curated source/tests, compile-only evidence, and actual Figma observations separate.

## Pinned comparison

| Snapshot | Ref | Commit | Tree | Plugin version | API inventory |
| --- | --- | --- | --- | --- | --- |
| Baseline | `{comparison['baseline']['ref']}` | `{comparison['baseline']['commit']}` | `{comparison['baseline']['tree']}` | `{comparison['baseline']['plugin_version']}` | No catalog in this tree |
| Candidate runtime | `{comparison['candidate']['ref']}` | `{comparison['candidate']['commit']}` | `{comparison['candidate']['tree']}` | `{comparison['candidate']['plugin_version']}` | {comparison['candidate']['api_catalog_member_count']:,} members, API source {comparison['candidate']['api_source_version']} |

The catalog was introduced at `{comparison['candidate']['api_inventory_introduced_commit']}`. The candidate catalog and pinned source blobs match that inventory commit. The v0.27.1 baseline has no `library/figma-api` inventory, so this is not a declaration-version diff. Per-member release deltas compare exact candidate namespace routes against static source references in each runtime snapshot. Those references do not prove support.

The candidate runtime includes `figma-bridge/native_provision.js`. The report cutoff is `{comparison['candidate']['commit']}`. Follow-up `{follow_up['commit']}` changes existing native label writes and records later source/readback validation. Its diff added no API categories, but those later results are not substituted for evidence from the pinned candidate snapshot. The later G5 handoff package changes Python packaging only and is outside the audited native runtime snapshot.

## Disjoint per-release status totals

| Status | v0.27.1 baseline | 0.28.0 development candidate |
| --- | ---: | ---: |
{status_rows}

| Owner surface class | Members |
| --- | ---: |
{surface_rows}

`runtime-api-member` rows have a generated namespace route. `runtime-object-member` rows belong to a concrete node or inherited node mixin. `type-contract-member` rows belong to a TypeScript type alias and are not treated as callable runtime routes. Other owners remain applicability-unresolved. None of these classes means implemented or unsupported.

## Per-release support bounds

| Release | Runtime code lower bound | Runtime native-observed lower bound | All-member code lower bound | All-member native-observed lower bound | Possible runtime upper bound |
| --- | ---: | ---: | ---: | ---: | ---: |
{bound_rows}

The v0.27.1 baseline has no pinned API catalog. Its rows reuse the candidate API keys only to compare routes with historical runtime source. A baseline unresolved row does not mean the API member was absent or unsupported in v0.27.1. Current evidence never fills a historical status.

Runtime lower bounds count curated `observed` and `implemented` runtime rows. The native-observed runtime lower bound counts `observed` rows only. All-member bounds also count curated type-only contract fields when their exact shape was observed. The possible runtime upper bound adds compile-only and unresolved rows that are not explicitly type-only. This is a ceiling, not a support estimate. There are {counts['rows_with_status_in_both_releases']} members with non-unresolved status in both releases; {counts['known_status_changes_between_releases']} of those have different status labels.

## Scoped feature findings

These findings are separate from the 1,382 member totals. A feature-level limitation does not mean the corresponding official API member is unavailable in Figma.

| Finding | v0.27.1 | Candidate | Scope |
| --- | --- | --- | --- |
{finding_rows or '| None supplied | unresolved | unresolved | No scoped feature claim is curated. |'}

Curated feature-evidence files:
{evidence_sources}

## Separate API denominators

{exclusion_lines or '- No separately pinned API surface was detected.'}

`unsupported` requires an explicit scoped limitation. `verified_unimplemented` requires a feature-route review and exact declaration lookup. A missing source reference, missing route, or absent old catalog leaves a row unresolved. A static reference and a test name mention are locators only.

## Verified gaps in shipped routes

The following methods are verified absent only from the stated prebuilt Flow routes and unmodified recipe. These entries do not claim that Figma lacks the API or that a user-authored SDK plugin cannot call it.

| Member | Scope checked |
| --- | --- |
{unimplemented_rows or '| None verified | No member has affirmative unimplemented evidence. |'}

## Row-level data

[`members.json`](members.json) contains every row, the official declaration URL and source lines, route and permission metadata, exact baseline/candidate static references, test name mentions, curated evidence, and release deltas. Review each `status_basis` and evidence object before using a row as a product claim. The files under `evidence/` hold the separately reviewed per-member and scoped feature records.

## Reproduction

Run the pinned TypeScript 5.9.3 scanner and rebuild the report:

```sh
python3 tools/figma_api_audit.py generate --typescript PATH_TO_TYPESCRIPT_5_9_3
python3 tools/figma_api_audit.py verify --typescript PATH_TO_TYPESCRIPT_5_9_3
```

The tool reads the baseline and candidate by their pinned Git refs, checks their commit/tree IDs, and writes only `library/figma-api/audit/members.json` and `report.md`. It does not edit the existing API catalog. It makes no Figma MCP call or native runtime claim.
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command_name in ('generate', 'verify'):
        command = commands.add_parser(command_name)
        command.add_argument('--typescript', required=True,
                             help='Path to the pinned TypeScript 5.9.3 lib/typescript.js')
        command.add_argument('--baseline', default=BASELINE_REF)
        command.add_argument('--candidate', default=CANDIDATE_REF)
    args = parser.parse_args(argv)
    try:
        dataset = assemble(args.candidate, args.baseline, args.typescript)
        generated = {DATASET: canonical(dataset), REPORT: report(dataset)}
        if args.command == 'verify':
            for path, expected in generated.items():
                if not path.is_file() or path.read_text() != expected:
                    raise ValueError(f'Audit output differs from deterministic regeneration: {path.relative_to(ROOT)}')
            print(f"Verified {dataset['counts']['members']} per-member records and release report")
        else:
            AUDIT.mkdir(parents=True, exist_ok=True)
            for path, content in generated.items():
                path.write_text(content, encoding='utf-8')
            print(f"Wrote {DATASET.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            tarfile.TarError, json.JSONDecodeError) as error:
        parser.exit(1, f'figma-api-audit: {error}\n')


if __name__ == '__main__':
    main()
