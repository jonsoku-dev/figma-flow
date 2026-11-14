"""Validate docs/next-roadmap/backlog.graph.json invariants, links, anchors, and DAG readiness."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROADMAP_DIR = ROOT / 'docs/next-roadmap'
GRAPH_PATH = ROADMAP_DIR / 'backlog.graph.json'
SATISFIED_STATUSES = {'accepted', 'verified'}
EXPECTED_P0_PROOF_REFS = {
    'p0-reference-acceptance.md',
    '../../tools/reference_distribution_guard.py',
    '../../tests/test_reference_distribution_guard.py',
    '../../.github/workflows/reference-guard.yml',
    '../../examples/owned-design-baseline/',
    '../../examples/owned-design-baseline/README.md',
    '../../examples/owned-design-baseline/graph.json',
    '../../examples/owned-design-baseline/manifest.json',
    '../../tests/test_owned_design_baseline.py',
}
EXPECTED_P1_NF03_PROOF_REFS = {
    'p1-acceptance.md',
    '../../tools/figma_control.py',
    '../../tools/operation_detail.py',
    '../../tests/test_operation_detail.py',
    '../../figma-bridge/workspace_control.js',
    '../../figma-bridge/workspace_host.js',
    '../../figma-bridge/workspace_transport.js',
    '../../tests/nf03_history_detail.cjs',
    '../../panel-ui/src/operationDetail.mjs',
    '../../panel-ui/src/Workspace.jsx',
    '../../tests/test_nf03_panel_ui.cjs',
}


def _markdown_anchors(text):
    anchors = set(re.findall(r'<a\s+id=["\']([^"\']+)["\']\s*>', text))
    for heading in re.findall(r'^#{1,6}\s+(.+)$', text, flags=re.MULTILINE):
        cleaned = re.sub(r'[`*_]', '', heading).strip().lower()
        slug = re.sub(r'[^\w\s-]', '', cleaned).replace(' ', '-')
        slug_keep_dots = re.sub(r'[^\w\s.-]', '', cleaned).replace(' ', '-')
        anchors.update({slug, slug_keep_dots})
    return anchors


def next_ready_tasks(graph):
    """Return proposed task IDs whose depends-on prerequisites are all accepted or verified."""
    by_id = {node['id']: node for node in graph['nodes']}
    deps = {node['id']: [] for node in graph['nodes']}
    for edge in graph['edges']:
        if edge['type'] == 'depends-on':
            deps[edge['from']].append(edge['to'])
    return [
        node['id']
        for node in graph['nodes']
        if node['type'] == 'task'
        and node['status'] == 'proposed'
        and all(by_id[dep]['status'] in SATISFIED_STATUSES for dep in deps[node['id']])
    ]


def validate_backlog_graph(graph, roadmap_dir=ROADMAP_DIR):
    """Verify DAG acyclicity, doc/spec references, and status/evidence invariants."""
    errors = []
    if graph.get('schema') != 'figma-flow-capability-backlog-v1':
        errors.append(f"Unexpected schema: {graph.get('schema')!r}")
    if graph.get('entry_document') != 'README.md':
        errors.append(f"Unexpected entry_document: {graph.get('entry_document')!r}")
    if graph.get('planning_document') != 'capability-review.md':
        errors.append(f"Unexpected planning_document: {graph.get('planning_document')!r}")

    vocab = set(graph.get('status_vocabulary', []))
    nodes = graph.get('nodes', [])
    by_id = {}
    for node in nodes:
        node_id = node.get('id')
        if not node_id or node_id in by_id:
            errors.append(f'Invalid or duplicate node id: {node_id!r}')
            continue
        by_id[node_id] = node
        if node.get('status') not in vocab:
            errors.append(f'{node_id}: invalid status {node.get("status")!r}')

    deps = {node_id: [] for node_id in by_id}
    for edge in graph.get('edges', []):
        src, dst, kind = edge.get('from'), edge.get('to'), edge.get('type')
        if src not in by_id or dst not in by_id:
            errors.append(f'Edge references unknown node: {edge!r}')
            continue
        if kind == 'depends-on':
            deps[src].append(dst)

    visiting, visited = set(), set()

    def visit(node_id):
        if node_id in visited:
            return
        if node_id in visiting:
            errors.append(f'Cycle detected at {node_id}')
            return
        visiting.add(node_id)
        for dep in deps[node_id]:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in by_id:
        visit(node_id)

    anchor_cache = {}

    def check_local_ref(ref, owner_id, *, allow_missing=False):
        rel_path, _, anchor = ref.partition('#')
        target = (roadmap_dir / rel_path).resolve()
        if not target.exists():
            if not allow_missing:
                errors.append(f'{owner_id}: missing referenced path {ref!r}')
            return
        if anchor:
            anchors = anchor_cache.setdefault(
                target, _markdown_anchors(target.read_text(encoding='utf-8'))
            )
            if anchor not in anchors:
                errors.append(f'{owner_id}: missing anchor #{anchor} in {rel_path}')

    for node in nodes:
        node_id = node.get('id')
        if node_id not in by_id:
            continue
        status = node.get('status')
        evidence_status = node.get('evidence_status', '')
        check_local_ref(node['doc_ref'], node_id)
        for ref in node.get('spec_refs', []):
            check_local_ref(ref, node_id)

        if status in SATISFIED_STATUSES:
            if evidence_status == 'unstarted' or evidence_status.startswith('pending-'):
                errors.append(f'{node_id}: satisfied status {status!r} conflicts with {evidence_status!r}')
            if node.get('type') == 'task':
                for dep in deps[node_id]:
                    if by_id[dep].get('status') not in SATISFIED_STATUSES:
                        errors.append(f'{node_id}: {status} task has unsatisfied dependency {dep!r}')
            has_evidence = bool(node.get('proof_refs') or node.get('observed_evidence') or node.get('spec_refs'))
            if not has_evidence:
                errors.append(f'{node_id}: {status} node lacks public evidence references')
            for ref in node.get('proof_refs', []):
                check_local_ref(ref, node_id, allow_missing=False)
        elif status == 'proposed':
            if evidence_status in SATISFIED_STATUSES:
                errors.append(f'{node_id}: proposed node cannot claim evidence_status {evidence_status!r}')
            for ref in node.get('proof_refs', []):
                check_local_ref(ref, node_id, allow_missing=True)

    return errors


class NextRoadmapBacklogTest(unittest.TestCase):
    def test_live_backlog_graph_satisfies_invariants_and_p0_contract(self):
        graph = json.loads(GRAPH_PATH.read_text(encoding='utf-8'))
        self.assertEqual(validate_backlog_graph(graph, ROADMAP_DIR), [])

        by_id = {node['id']: node for node in graph['nodes']}
        self.assertTrue(EXPECTED_P0_PROOF_REFS.issubset(set(by_id['p0-reference-safety']['proof_refs'])))
        self.assertTrue(EXPECTED_P1_NF03_PROOF_REFS.issubset(set(by_id['p1-causal-review-history']['proof_refs'])))
        self.assertEqual(by_id['p1-causal-review-history']['status'], 'verified')
        ready = next_ready_tasks(graph)
        self.assertTrue(ready or all(n['status'] in SATISFIED_STATUSES for n in graph['nodes'] if n['type'] == 'task'))
        for task_id in ready:
            self.assertEqual(by_id[task_id]['status'], 'proposed')

    def test_invariants_accept_progressed_p0_and_reject_invalid_states(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            doc_dir = temp_root / 'docs/next-roadmap'
            doc_dir.mkdir(parents=True)
            (doc_dir / 'capability-review.md').write_text(
                '<a id="base"></a>\n<a id="p0"></a>\n<a id="q"></a>\n<a id="p1"></a>\n',
                encoding='utf-8',
            )
            proof = temp_root / 'tools/guard.py'
            proof.parent.mkdir(parents=True)
            proof.write_text('# guard\n', encoding='utf-8')

            base_graph = {
                'schema': 'figma-flow-capability-backlog-v1',
                'entry_document': 'README.md',
                'planning_document': 'capability-review.md',
                'status_vocabulary': ['accepted', 'proposed', 'in-progress', 'verified', 'blocked'],
                'nodes': [
                    {
                        'id': 'baseline',
                        'type': 'reference',
                        'status': 'accepted',
                        'doc_ref': 'capability-review.md#base',
                        'spec_refs': ['capability-review.md#base'],
                    },
                    {
                        'id': 'p0',
                        'type': 'task',
                        'status': 'verified',
                        'evidence_status': 'verified',
                        'doc_ref': 'capability-review.md#p0',
                        'proof_refs': ['../../tools/guard.py'],
                    },
                    {
                        'id': 'p0-queue',
                        'type': 'task',
                        'status': 'proposed',
                        'evidence_status': 'cli-reproduction-observed',
                        'doc_ref': 'capability-review.md#q',
                    },
                    {
                        'id': 'p1',
                        'type': 'task',
                        'status': 'proposed',
                        'evidence_status': 'unstarted',
                        'doc_ref': 'capability-review.md#p1',
                    },
                ],
                'edges': [
                    {'from': 'p0-queue', 'to': 'p0', 'type': 'depends-on'},
                    {'from': 'p1', 'to': 'p0', 'type': 'depends-on'},
                    {'from': 'p1', 'to': 'p0-queue', 'type': 'depends-on'},
                ],
            }

            # Positive: once p0 is verified with existing proof on disk, p0-queue becomes next-ready.
            self.assertEqual(validate_backlog_graph(base_graph, doc_dir), [])
            self.assertEqual(next_ready_tasks(base_graph), ['p0-queue'])

            # Negative 1: verified task whose depends-on dependency is still proposed.
            bad_dep = copy.deepcopy(base_graph)
            bad_dep['nodes'][3]['status'] = 'verified'
            bad_dep['nodes'][3]['evidence_status'] = 'verified'
            bad_dep['nodes'][3]['proof_refs'] = ['../../tools/guard.py']
            self.assertTrue(any('unsatisfied dependency' in e for e in validate_backlog_graph(bad_dep, doc_dir)))

            # Negative 2: verified task pointing to a missing proof file on disk.
            missing_proof = copy.deepcopy(base_graph)
            missing_proof['nodes'][1]['proof_refs'] = ['../../tools/missing.py']
            self.assertTrue(any('missing referenced path' in e for e in validate_backlog_graph(missing_proof, doc_dir)))

            # Negative 3: verified node without any public evidence.
            no_evidence = copy.deepcopy(base_graph)
            del no_evidence['nodes'][1]['proof_refs']
            self.assertTrue(any('lacks public evidence' in e for e in validate_backlog_graph(no_evidence, doc_dir)))

            # Negative 4: proposed node claiming verified evidence_status.
            bad_proposed = copy.deepcopy(base_graph)
            bad_proposed['nodes'][2]['evidence_status'] = 'verified'
            self.assertTrue(any('proposed node cannot claim' in e for e in validate_backlog_graph(bad_proposed, doc_dir)))

            # Negative 5: depends-on cycle.
            cyclic = copy.deepcopy(base_graph)
            cyclic['edges'].append({'from': 'p0', 'to': 'p1', 'type': 'depends-on'})
            self.assertTrue(any('Cycle detected' in e for e in validate_backlog_graph(cyclic, doc_dir)))

    def test_roadmap_markdown_links_and_portability(self):
        forbidden_substrings = (
            '/Users/',
            '/home/',
            'C:\\',
            '옮길 문서다',
            'Cursor 실행자는',
            'Cursor 범위와 명령',
            '409dbfdd',
            '4237a49c',
        )
        anchor_cache = {}
        for filename in ('README.md', 'capability-review.md', 'p0-reference-acceptance.md', 'p1-acceptance.md', 'backlog.graph.json'):
            path = ROADMAP_DIR / filename
            text = path.read_text(encoding='utf-8')
            for marker in forbidden_substrings:
                self.assertNotIn(marker, text, f'Forbidden text {marker!r} in {filename}')
            if not filename.endswith('.md'):
                continue
            for _, raw_target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text):
                if raw_target.startswith(('http://', 'https://', '#')):
                    continue
                rel_path, _, anchor = raw_target.partition('#')
                target = (ROADMAP_DIR / rel_path).resolve()
                self.assertTrue(target.exists(), f'Broken link {raw_target} in {filename}')
                if anchor:
                    anchors = anchor_cache.setdefault(
                        target, _markdown_anchors(target.read_text(encoding='utf-8'))
                    )
                    self.assertIn(anchor, anchors, f'Broken anchor {raw_target} in {filename}')

        readme_text = (ROADMAP_DIR / 'README.md').read_text(encoding='utf-8')
        for index in range(1, 10):
            self.assertIn(f'NF-0{index}', readme_text)
        self.assertIn('backlog.graph.json', readme_text)
        self.assertIn('capability-review.md', readme_text)
