#!/usr/bin/env python3
"""Reconcile the declared Figma panel Graph with the submitted source snapshot."""
import argparse
import schema_ids
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tempfile

import delivery_config
import graph_impact
from graph_document import decode_json, read_json
from graph_generated import DOC_DIR, POLICY_DOC, TOKEN_CSS, check_generated, managed_files, write_policy_doc
from graph_impact import read_git as git
from panel_artifacts import ASSET_DIR, artifact_paths

ROOT = Path(__file__).resolve().parents[1]
GRAPH = 'library/panel-design/governance.json'
POLICY = 'tools/maintenance-contract.json'
SOURCE = 'panel-ui/src/'
EMPTY_GRAPH = {'schema': 1, 'nodes': [], 'relations': [], 'relationTypes': {}}
STAGES = ('graph', 'structure', 'usage', 'generation', 'contract', 'quality', 'documentation', 'impact', 'freshness')
PROOF_FOR_ACTION = {
    'validate-graph': 'graph',
    'verify-structure': 'structure',
    'verify-usage': 'usage',
    'regenerate': 'generation',
    'verify-contract': 'contract',
    'verify-quality': 'quality',
    'review-documentation': 'documentation',
}
IMPORT_EDGES = {'IMPORTS', 'REEXPORTS'}
RELATION_DECLARATIONS = {'GENERATED_FROM', 'DOCUMENTS', 'IMPLEMENTS', 'VERIFIES'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def finding(rule, status, message, **evidence):
    return {'rule': rule, 'status': status, 'severity': 'error' if status != 'agrees' else 'info',
            'message': message, **evidence}


def parts_are_safe(path):
    return isinstance(path, str) and bool(path) and all(
        part not in ('', '.', '..') for part in path.split('/')
    ) and not any(char in path for char in '\\:\0')


def bind_graph(graph, policy):
    graph_impact.validate_graph(graph)
    panel = policy['panelBoundaries']
    for key in ('entry', 'networkOwner', 'bridgeOwner'):
        if not parts_are_safe(panel[key]):
            raise ValueError(f'{POLICY}: specify a path under {SOURCE} for {key}')
    for key in ('networkApis', 'blockedPackages'):
        if (not isinstance(panel[key], list) or not panel[key] or
                any(not isinstance(item, str) or not item for item in panel[key]) or
                len(set(panel[key])) != len(panel[key])):
            raise ValueError(f'{POLICY}: declare unique, nonempty strings for {key}')
    if not isinstance(panel['bridgeApi'], str) or not panel['bridgeApi']:
        raise ValueError(f'{POLICY}: declare the native bridge API')
    for source, imports in panel['externalImports'].items():
        if (not parts_are_safe(source) or not isinstance(imports, list) or not imports or
                any(not isinstance(spec, str) or not spec.startswith('../')
                    or not parts_are_safe(posixpath.normpath(posixpath.join(SOURCE, posixpath.dirname(source), spec)))
                    or posixpath.normpath(posixpath.join(SOURCE, posixpath.dirname(source), spec)).startswith(SOURCE)
                    for spec in imports) or len(set(imports)) != len(imports)):
            raise ValueError(f'{POLICY}: declare unique repository-local external imports for {source}')
    nodes = []
    for node in graph['nodes']:
        if node['action'] not in PROOF_FOR_ACTION:
            raise ValueError(f'No verification for action {node["action"]} on {node["id"]}')
        binding = node.get('binding')
        if binding is not None and binding not in ('networkOwner', 'bridgeOwner'):
            raise ValueError(f'Unknown panel policy binding on {node["id"]}: {binding}')
        paths = [SOURCE + panel[binding]] if binding else node['paths']
        nodes.append({**node, 'paths': paths})
    return {**graph, 'nodes': nodes}


def snapshot(root, graph):
    paths = set(git(root, 'ls-files', '-co', '--exclude-standard', '-z').decode().split('\0')) - {''}
    patterns = {pattern for node in graph['nodes'] for pattern in node['paths']}
    wanted = {path for path in paths if any(graph_impact.matches_path(path, pattern) for pattern in patterns)}
    for directory in (Path(SOURCE), ASSET_DIR, DOC_DIR):
        wanted.update(path.as_posix() for path in managed_files(root, directory))
    content = {}
    for name in sorted(wanted):
        path = root / name
        if path.is_symlink():
            content[name] = {'symlink': str(path.readlink())}
        elif path.is_file():
            content[name] = {'sha256': sha256(path.read_bytes()).hexdigest(), 'executable': bool(path.stat().st_mode & 0o111)}
    return {'sha256': digest(content), 'paths': len(content)}


def run(root, argv, **kwargs):
    return subprocess.run(argv, cwd=root, check=False, capture_output=True, text=True, timeout=180, **kwargs)


def observe(root, graph, policy, *, checkout=None):
    checkout = root if checkout is None else checkout
    process = run(root, ['node', 'panel-ui/observed-graph.cjs', '--options-stdin'], input=json.dumps({
        'root': str(checkout),
        'entries': [SOURCE + policy['panelBoundaries']['entry']],
        'externalConsumers': graph['externalConsumers'],
    }))
    if process.returncode != 0:
        raise ValueError(f'Extract the observed panel Graph: {process.stderr.strip()}')
    report = decode_json(process.stdout)
    if report.get('schema') != schema_ids.ID['observedPanel'] or not report.get('sourceFingerprint'):
        raise ValueError('The panel observer did not produce current source evidence')
    expected = {
        path.relative_to(checkout).as_posix() for path in (checkout / SOURCE).rglob('*')
        if path.suffix in ('.jsx', '.mjs', '.js', '.cjs') and path.is_file() and not path.is_symlink()
    }
    sources = [row['path'] for row in report['nodes'] if row['origin'] == 'source']
    if expected != set(sources) or len(sources) != len(set(sources)):
        raise ValueError(f'Observation omitted or duplicated panel sources: {sorted(expected.symmetric_difference(sources))}')
    return report


def structure(graph, panel, observation):
    issues = []
    observed = {node['path'] for node in observation['nodes']}
    by_id = {node['id']: node for node in graph['nodes']}
    binding_evidence = []
    for node in graph['nodes']:
        if node['kind'] != 'implementation' or node['status'] != 'active':
            continue
        for pattern in node['paths'] or [None]:
            paths = sorted(path for path in observed if pattern and graph_impact.matches_path(path, pattern))
            binding_evidence.append({'target': node['id'], 'path': pattern, 'observedPaths': paths,
                                     'status': 'bound' if paths else 'unbound'})
            if not paths:
                issues.append(finding('implementation-binding', 'unbound', 'Bind the active implementation to observed panel source.',
                                      target=node['id'], path=pattern, action='supply-mapping'))

    imports = [edge for edge in observation['edges'] if edge['type'] in IMPORT_EDGES]
    for relation in graph['relations']:
        kind = relation['type']
        if kind in RELATION_DECLARATIONS:
            continue
        origin, destination = (by_id[relation[key]] for key in ('from', 'to'))
        if 'planned' in (origin['status'], destination['status']):
            continue
        state = relation['state']
        call_binding = kind == 'CALLS' and relation.get('mode') == 'static-import-binding' and relation.get('symbol')
        if kind not in IMPORT_EDGES and not call_binding:
            if state != 'optional':
                issues.append(finding('relation-target-resolution', 'unknown', 'The observer cannot resolve this required or forbidden relationship. Supply a verifier for the declared type.',
                                      relation=relation, target=origin['id'], path=GRAPH, action='supply-mapping'))
            continue
        def endpoint(path, node):
            return path and any(graph_impact.matches_path(path, pattern) for pattern in node['paths'])

        edges = [edge for edge in observation['edges'] if edge['type'] == kind and endpoint(edge['from'], origin)]
        witnesses = [edge['location'] for edge in edges if endpoint(edge.get('to'), destination)
                     and ('mode' not in relation or edge['mode'] == relation['mode'])
                     and (not call_binding or edge.get('targetSymbol') == relation['symbol'])]
        uncertain = [edge['location'] for edge in edges if call_binding and (candidate := edge.get('importCandidate'))
                     and endpoint(candidate['to'], destination) and candidate['targetSymbol'] == relation['symbol']]
        if witnesses and state == 'forbidden':
            status, reason = 'prohibited', 'Remove the prohibited dependency or use the owning adapter.'
        elif not witnesses and state == 'required':
            status, reason = ('unknown', 'Resolve the possible imported call binding before using it as evidence.') if uncertain else (
                'missing', 'Restore the required source relationship or amend the approved Graph.')
        elif uncertain and state == 'forbidden':
            status, reason = 'unknown', 'Resolve the possible prohibited imported call binding.'
        elif witnesses:
            status, reason = 'agrees', 'The declared relationship is present in the observed source.'
        else:
            continue
        issues.append(finding('declared-relationship', status, reason, relation=relation, target=origin['id'],
                              path=GRAPH, evidence=witnesses or uncertain, action='verify-structure'))

    allowed = {(SOURCE + source, spec) for source, values in panel['externalImports'].items() for spec in values}
    observed_outside = {}
    for edge in imports:
        if edge.get('resolution') == 'external-file':
            key = (edge['from'], edge['specifier'])
            observed_outside.setdefault(key, []).append(edge['location'])
    for origin, spec in sorted(allowed | observed_outside.keys()):
        locations = observed_outside.get((origin, spec), [])
        if (origin, spec) not in allowed:
            status, reason = 'prohibited', 'Route this external import through its declared panel contract.'
        elif not locations:
            status, reason = 'missing', 'Restore this contract consumer or retire the declared import with owner review.'
        else:
            status, reason = 'agrees', 'The panel consumes a declared external module.'
        issues.append(finding('external-import', status, reason, path=origin, target=spec,
                              evidence=locations, action='verify-structure'))
    for row in observation['findings']:
        issues.append(finding(row['rule'], 'unknown', 'Resolve the panel dependency so the boundary can be verified.',
                              path=row['path'], evidence=row.get('location'), action='supply-mapping'))
    return binding_evidence, issues


def usage_findings(graph, observation):
    rules = {}
    for row in graph['dispositions']:
        path = row['path']
        if (not parts_are_safe(path) or path in rules or
                not all(isinstance(row.get(key), str) and row[key].strip()
                        for key in ('reason', 'approval', 'reviewCondition')) or
                not re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', ''))):
            raise ValueError('An unused disposition needs a unique path, source SHA, reason, approval and review condition')
        rules[path] = row
    hashes = {node['path']: node['sha256'] for node in observation['nodes']}
    records = Counter(row['path'] for row in observation['usage'])
    if len(hashes) != len(observation['nodes']) or set(records) != hashes.keys() or any(count != 1 for count in records.values()):
        raise ValueError('Usage evidence must cover every observed module exactly once.')
    local_edges = {(edge['from'], edge['to'], edge['mode']) for edge in observation['edges'] if edge.get('resolution') == 'local'}
    external_roots = {(row['path'], row['consumer']) for row in observation['externalEvidence']
                      if row.get('certainty') == 'extracted'}
    issues = []
    applied = set()
    for row in observation['usage']:
        path = row['path']
        if row['status'] not in ('used', 'external', 'unknown', 'unused-candidate'):
            raise ValueError(f'Unknown usage status for {path}: {row["status"]}')
        if row['status'] in ('used', 'external'):
            evidence = row.get('evidence', {})
            route, modes = evidence.get('path'), evidence.get('modes')
            if (not isinstance(route, list) or not route or route[-1] != path or not isinstance(modes, list)
                    or len(modes) != len(route) - 1
                    or any(edge not in local_edges for edge in zip(route, route[1:], modes))
                    or (row['status'] == 'used' and route[0] not in observation['entries'])
                    or (row['status'] == 'external' and (route[0], evidence.get('consumer')) not in external_roots)):
                raise ValueError(f'Usage evidence for {path} does not trace to its runtime or verified external entry.')
        if row['status'] == 'unknown':
            issues.append(finding('usage-evidence', 'unknown', 'Resolve dynamic usage before classifying this module.',
                                  path=path, action='investigate-usage'))
        elif row['status'] == 'unused-candidate':
            if path in rules and hashes[path] == rules[path]['sha256']:
                applied.add(path)
            else:
                issues.append(finding('unused-module', 'needs-review', 'Review the candidate and record evidence before removing or retaining it.',
                                      path=path, action='investigate-usage'))
    for path in sorted(rules.keys() - applied):
        issues.append(finding('stale-disposition', 'needs-review', 'Remove an obsolete disposition or review it against the actual source.',
                              path=path, action='investigate-usage'))
    return issues


def guide_inputs(root, graph, policy):
    pins = read_json(root / 'panel-ui/package.json')['devDependencies']
    return {
        'panel-boundary-policy': digest({'boundaries': policy['panelBoundaries'], 'artifacts': policy['panelArtifacts']}),
        'panel-governance': digest({key: graph[key] for key in ('scope', 'relationTypes', 'relations', 'externalConsumers')}),
        'panel-static-quality': digest({name: pins[name] for name in ('@biomejs/biome', 'oxlint', 'knip')}),
    }


def doc_findings(root, graph, policy):
    review = graph['guideReview']
    inputs = guide_inputs(root, graph, policy)
    if set(review['inputs']) != inputs.keys() or not all(parts_are_safe(review[key]) for key in ('path', 'receipt')):
        raise ValueError('The maintenance guide review must identify the panel boundary policy and portable document paths')
    receipt = read_json(root / review['receipt'])
    fields = {'inputs': inputs, 'documentSha256': sha256((root / review['path']).read_bytes()).hexdigest()}
    if (any(receipt.get(key) != value for key, value in fields.items()) or
            not isinstance(receipt.get('reason'), str) or not receipt['reason'].strip() or
            receipt.get('decision') not in ('updated', 'reviewed-no-change')):
        return [finding('documentation-review', 'needs-review', 'Review the named policy change and update the guide or record a reasoned no-change decision.',
                        path=review['path'], target=review['node'], evidence=fields, action='review-documentation')]
    return []


def contract_proof(root, tests):
    if not tests or any(not parts_are_safe(path) or not cases or not isinstance(cases, list) for path, cases in tests.items()):
        raise ValueError('Declare the named panel contract tests and source paths in the Graph')
    results = {}
    for source, names in tests.items():
        command = ['node', '--test', '--test-reporter=tap', source]
        checks = run(root, command)
        proof = tap_proof(checks.stdout, checks.returncode, names)
        proof.update(command=command, outputSha256=sha256((checks.stdout + checks.stderr).encode()).hexdigest())
        if proof['status'] != 'passed':
            proof['diagnostic'] = '\n'.join((checks.stdout + checks.stderr).splitlines()[-24:])
        results[source] = proof
    return {'status': 'passed' if all(row['status'] == 'passed' for row in results.values()) else 'incomplete',
            'suites': results}


def quality_proof(root):
    project = root / 'panel-ui'
    pins = read_json(project / 'package.json')['devDependencies']
    versions = {name: read_json(project / 'node_modules' / name / 'package.json')['version']
                for name in ('@biomejs/biome', 'oxlint', 'knip')}
    errors = [finding('tool-version', 'missing-or-drift', f'Install {name}@{pins[name]} in panel-ui.', target=name)
              for name, version in versions.items() if pins[name] != version]
    steps = {}
    commands = {
        'format:check': ['node_modules/.bin/biome', 'format', '.'],
        'lint:biome': ['node_modules/.bin/biome', 'lint', '.'],
        'lint:oxlint': ['node_modules/.bin/oxlint', '--max-warnings', '0', '--format', 'json', '.'],
        'lint:knip': ['node', 'knip.config.mjs', '--json'],
    }
    with tempfile.TemporaryDirectory(prefix='figma-flow-quality-') as scratch:
        environment = {**os.environ, **dict.fromkeys(('TMPDIR', 'TMP', 'TEMP'), scratch)}
        results = {task: run(project, command, env=environment) for task, command in commands.items()}
    for task, completed in results.items():
        output = completed.stdout + completed.stderr
        status = 'passed' if completed.returncode == 0 else 'failed'
        steps[task] = {'status': status, 'command': commands[task], 'exit': completed.returncode,
                       'outputSha256': sha256(output.encode()).hexdigest()}
        if status != 'passed':
            errors.append(finding('quality-command', status, f'{task} failed. {output.strip()[-1700:]}', target=task))
        elif task == 'lint:knip':
            receipt = decode_json(completed.stdout)
            if (receipt.get('schema') != 'figma-flow-panel-knip-v1' or receipt.get('status') != 'passed' or
                    {row['mode'] for row in receipt['runs']} != {'production', 'development'}):
                errors.append(finding('quality-evidence', 'unknown', 'Knip must report both production and tooling analysis.', target=task))
            steps[task]['evidence'] = receipt
        elif task == 'lint:oxlint':
            receipt = decode_json(completed.stdout)
            if not receipt['number_of_files'] or not receipt['number_of_rules'] or receipt['diagnostics']:
                errors.append(finding('quality-evidence', 'unknown', 'Oxlint must report active rules and a clean file scan.', target=task))
            steps[task].update(files=receipt['number_of_files'], rules=receipt['number_of_rules'])
        else:
            count = re.search(r'\bChecked ([1-9]\d*) files?\b', output)
            if not count:
                errors.append(finding('quality-evidence', 'unknown', 'The checker did not report a positive file count.', target=task))
            else:
                steps[task]['files'] = int(count[1])
    return {'versions': versions, 'steps': steps}, errors


def tap_proof(output, returncode, required=()):
    counts = {key: [int(value) for value in re.findall(rf'^# {key} (\d+)$', output, re.M)]
              for key in ('tests', 'pass', 'fail', 'skipped', 'cancelled', 'todo')}
    cases = set(re.findall(r'^ok \d+ - (.+)$', output, re.M))
    missing = sorted(set(required) - cases)
    ok = (not missing and all(len(values) == 1 for values in counts.values()) and counts['tests'][0] > 0 and
          counts['tests'] == counts['pass'] and all(counts[key] == [0] for key in ('fail', 'skipped', 'cancelled', 'todo')))
    if not ok or returncode:
        return {'status': 'incomplete' if not returncode else 'failed', 'counts': counts, 'missingCases': missing}
    return {'status': 'passed', 'counts': {key: values[0] for key, values in counts.items()}, 'cases': sorted(cases)}


def aggregate(stages):
    return ('passed' if set(stages) == set(STAGES) and all(
        stage.get('status') == 'passed' and stage.get('evidence') for stage in stages.values()
    ) else 'incomplete')


def read_base(root, ref):
    if not git(root, 'ls-tree', '--name-only', ref, '--', GRAPH).strip():
        # The first adoption deliberately has no prior governance declaration.
        return EMPTY_GRAPH
    return bind_graph(decode_json(git(root, 'show', f'{ref}:{GRAPH}')),
                      decode_json(git(root, 'show', f'{ref}:{POLICY}')))


def changed_symbols(root, base, paths):
    modules = []
    for name, change in paths.items():
        if not name.startswith(SOURCE) or Path(name).suffix not in ('.js', '.mjs', '.jsx', '.cjs'):
            continue
        source = {'path': name}
        for revision, read in (
            ('before', lambda: git(root, 'show', f'{base}:{name}')),
            ('after', lambda: (root / name).read_bytes()),
        ):
            info = change[revision]
            if info is None:
                source[revision] = None
                continue
            if info['mode'] not in ('100644', '100755'):
                raise ValueError(f'Cannot extract symbols from non-regular source {name} ({revision})')
            content = read()
            if sha256(content).hexdigest() != info['sha256']:
                raise ValueError(f'Panel source changed while extracting symbols: {name}')
            source[revision] = content.decode()
        modules.append(source)
    if not modules:
        return {'files': []}
    result = run(root, ['node', 'panel-ui/observed-graph.cjs', '--symbols-stdin'], input=json.dumps(modules))
    if result.returncode:
        raise ValueError('Symbol extraction failed: ' + result.stderr.strip())
    evidence = decode_json(result.stdout)
    if (evidence.get('schema') != 'figma-flow-observed-panel-symbol-diff-v1' or
            {row['path'] for row in evidence['files']} != {row['path'] for row in modules}):
        raise ValueError('Symbol evidence is missing for a changed panel module')
    return evidence


def baseline_observation(root, base, old_graph, current_graph, current, changes):
    old_policy = decode_json(git(root, 'show', f'{base}:{POLICY}'))
    panel = old_policy['panelBoundaries']
    if not panel.get('entry'):
        old_build = git(root, 'show', f'{base}:panel-ui/build.mjs').decode()
        matches = re.findall(r"entryPoints:\s*\[fileURLToPath\(new URL\(['\"]src/([^'\"]+)['\"]", old_build)
        if len(matches) != 1 or not parts_are_safe(matches[0]):
            raise ValueError('The historical panel entry cannot be established from its build configuration.')
        panel['entry'] = matches[0]
    external = old_graph.get('externalConsumers', current_graph['externalConsumers'])
    paths = {SOURCE + '**', POLICY, 'panel-ui/package.json', 'panel-ui/build.mjs',
             'panel-ui/view-registry.mjs', 'library/panel-design/views.json'}
    paths.update(path for path in current['inputFiles'] if not path.startswith('panel-ui/node_modules/'))
    paths.update(row['consumer'] for row in external)
    paths.update(posixpath.normpath(posixpath.join(SOURCE, posixpath.dirname(source), spec))
                 for source, specs in panel['externalImports'].items() for spec in specs)
    if not any(graph_impact.matches_path(path, pattern) for path in changes for pattern in paths) and external == current_graph['externalConsumers']:
        return current
    with graph_impact.panel_base_snapshot(root, base, paths) as checkout:
        report = observe(root, {'externalConsumers': external}, old_policy, checkout=checkout)
        previous = read_json(checkout / 'panel-ui/package.json')
    for package in report['packages']:
        pin = previous['dependencies'].get(package['name'])
        if pin and pin != package['version']:
            report['findings'].append({'rule': 'baseline-package-version-unavailable', 'path': package['manifest'],
                                       'expected': pin, 'observed': package['version']})
    return report


def compare(root, graph, base, *, policy=None, current=None):
    if base is None:
        raise ValueError('Supply an explicit comparison base for impact verification')
    base_sha = git(root, 'rev-parse', '--verify', '--end-of-options', f'{base}^{{commit}}').decode().strip()
    paths = graph_impact.changed_paths(root, base_sha)
    previous = read_base(root, base_sha)
    current = current or observe(root, graph, policy or read_json(root / POLICY))
    baseline = baseline_observation(root, base_sha, previous, graph, current, paths)
    impact = graph_impact.analyze_observed_impact(
        baseline, current, paths, base_types=previous['relationTypes'] or graph['relationTypes'],
        current_types=graph['relationTypes'],
    )
    for row in impact['targets']:
        row['bindings'] = {revision: sorted(node['id'] for node in revision_graph['nodes']
                                            if any(graph_impact.matches_path(row['path'], pattern) for pattern in node['paths']))
                           for revision, revision_graph in (('base', previous), ('current', graph))}
    return {'base': base_sha, 'symbols': changed_symbols(root, base_sha, paths),
            'observedImpact': impact,
            **graph_impact.analyze_impact(previous, graph, paths, observed_targets=impact['targets'])}


def verify(root, graph, policy, base):
    start = snapshot(root, graph)
    stages = {'graph': {'status': 'passed', 'evidence': {'path': GRAPH, 'sha256': digest(graph)}}}
    report = {'schema': 'figma-flow-governance-report-v1', 'version': git(root, 'rev-parse', 'HEAD').decode().strip(),
              'scope': graph['scope'], 'snapshot': start, 'stages': stages}

    def checked(name, callback):
        try:
            evidence, issues = callback()
            stages[name] = {'status': 'failed' if any(row['severity'] == 'error' for row in issues) else 'passed',
                            'evidence': evidence, 'findings': issues}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            stages[name] = {'status': 'unknown', 'findings': [
                finding(name, 'unknown', str(error), action='supply-evidence')]}

    observation = {}
    def verify_structure():
        observation.update(observe(root, graph, policy))
        bindings, issues = structure(graph, policy['panelBoundaries'], observation)
        return {'bindings': bindings, 'sourceFingerprint': observation['sourceFingerprint'],
                'extractor': observation['extractor'], 'packages': observation['packages'],
                'externalEvidence': observation['externalEvidence'], 'observedModules': len(observation['nodes']),
                'observedEdges': len(observation['edges'])}, issues

    def verify_usage():
        return {'usage': observation['usage'], 'cycles': observation['cycles'],
                'dispositions': graph['dispositions']}, usage_findings(graph, observation)

    def verify_generation():
        paths = check_generated(root, policy)
        ci = delivery_config.check(root)
        issues = [finding('generated-drift', 'missing-or-drift', str(item), action='regenerate') for item in [*paths, *ci]]
        evidence = {}
        if not paths:
            outputs = set(artifact_paths(policy).values()) | {POLICY_DOC, TOKEN_CSS}
            evidence['panel'] = {path.as_posix(): sha256((root / path).read_bytes()).hexdigest() for path in sorted(outputs)}
        if not ci:
            evidence['delivery'] = [path.as_posix() for path in sorted(delivery_config.templates(root))]
        return evidence, issues

    checked('structure', verify_structure)
    checked('usage', verify_usage)
    checked('generation', verify_generation)

    def verify_contract():
        proof = contract_proof(root, graph['contractTests'])
        return proof, [] if proof['status'] == 'passed' else [
            finding('behavioral-evidence', 'needs-review', 'Run all required panel contract scenarios without failures or skips.',
                    action='verify-contract')]

    checked('contract', verify_contract)
    checked('quality', lambda: quality_proof(root))
    checked('documentation', lambda: ({'path': graph['guideReview']['receipt']}, doc_findings(root, graph, policy)))

    def verify_impact():
        impact = compare(root, graph, base, policy=policy, current=observation)
        issues = [finding('impact-symbols', 'unknown', 'Resolve the changed panel source before relying on symbol impact.',
                          path=row['path'], evidence=row['unknown'], action='supply-evidence')
                  for row in impact['symbols']['files'] if row['status'] == 'unknown']
        issues.extend(finding('impact-observation', 'unknown', 'Resolve missing historical or current dependency evidence.',
                              path=row['path'], evidence=row, action='supply-evidence')
                      for row in impact['observedImpact']['unknown'])
        for item in impact['impacts']:
            proof = PROOF_FOR_ACTION[item['action']]
            if item['removed']:
                item['status'] = 'retired' if all(
                    relation['to'] != item['id'] and relation['from'] != item['id'] for relation in graph['relations']
                ) else 'needs-review'
            elif item['status'] == 'planned':
                item['status'] = 'not-applicable'
            else:
                item['status'] = 'action-checked' if stages[proof]['status'] == 'passed' else 'needs-review'
            evidence = stages[proof].get('evidence')
            item['evidence'] = {'stage': proof, 'sha256': digest(evidence) if evidence else None}
            if item['status'] == 'needs-review':
                issues.append(finding('impact-incomplete', 'needs-review', 'Complete the required action for this affected target.',
                                      target=item['id'], action=item['action'], evidence=item['traces']))
        return impact, issues

    checked('impact', verify_impact)

    def verify_freshness():
        current = snapshot(root, graph)
        current_policy = read_json(root / POLICY)
        same_authority = current_policy == policy and bind_graph(read_json(root / GRAPH), current_policy) == graph
        return current, [] if current == start and same_authority else [
            finding('snapshot-changed', 'unknown', 'Source changed during verification. Recheck the actual submitted snapshot.',
                    evidence={'before': start, 'after': current}, action='supply-evidence')]

    checked('freshness', verify_freshness)
    report['status'] = aggregate(stages)
    return report


def summary(report):
    print(f'Panel Graph {report["status"]} for {report["version"][:12]} / {report["snapshot"]["sha256"][:12]}')
    for name, stage in report['stages'].items():
        print(f'  {name}: {stage["status"]}')
        for issue in stage.get('findings', []):
            if issue['severity'] == 'error':
                print(f'    {issue.get("path", issue.get("target", ""))} {issue["rule"]}: {issue["message"]}')
    evidence = report['stages']['impact'].get('evidence')
    if evidence:
        print(f'  {len(evidence["impacts"])} declared and {len(evidence["observedImpact"]["targets"])} observed affected targets')
        print(f'  {len(evidence["unmappedPaths"])} changed paths outside declared mappings')


def test_other_suites(root, contract_tests):
    suites = sorted(path.relative_to(root).as_posix() for path in (root / 'tests').glob('*.cjs'))
    pending = [path for path in suites if path not in contract_tests]
    if not pending:
        raise ValueError('The remaining Node test suites are missing')
    return subprocess.run(['node', '--test', *pending], cwd=root, check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('observe', 'impact', 'verify', 'write-doc', 'test-other-suites'))
    parser.add_argument('--base', help='Git commit or ref for the before/after comparison')
    parser.add_argument('--json', action='store_true', help='Print structured evidence')
    args = parser.parse_args()
    try:
        policy = read_json(ROOT / POLICY)
        graph = bind_graph(read_json(ROOT / GRAPH), policy)
        if args.command == 'write-doc':
            write_policy_doc(ROOT, policy)
            return 0
        if args.command == 'test-other-suites':
            return test_other_suites(ROOT, graph['contractTests'])
        if args.command == 'observe':
            result = observe(ROOT, graph, policy)
        elif args.command == 'impact':
            result = compare(ROOT, graph, args.base)
        else:
            result = verify(ROOT, graph, policy, args.base)
            if not args.json:
                summary(result)
        if args.json or args.command != 'verify':
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return int(args.command == 'verify' and result['status'] != 'passed')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Graph governance: {error}\n')


if __name__ == '__main__':
    sys.exit(main())
