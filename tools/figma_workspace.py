#!/usr/bin/env python3
"""Compile trusted Figma Flow tasks into one private, atomically published plugin."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:
    fcntl = None
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import uuid

from plugin_panel import display_name, render_app, supported_locales

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'figma-flow-workspace-v1'
MAX_BYTES = 256 * 1024 * 1024
OPTIONS = {
    'native-edit': {'--plan'},
    'import': {'--input', '--reviewed-sha256', '--selection', '--product-graph', '--batch', '--asset-receipts', '--paired-state'},
    'review': {'--manifest', '--layout', '--file-key', '--pair-dir', '--receiver-port', '--selection', '--product-graph', '--change-request', '--plan'},
    'discover': {'--file-key', '--page-id', '--include-page-id'},
    'sync': {'--graph', '--pairing', '--native-readback', '--import-report', '--adopt'},
}
PATH_OPTIONS = {'--plan', '--input', '--selection', '--product-graph', '--batch', '--asset-receipts', '--manifest', '--layout', '--graph', '--pairing', '--native-readback', '--import-report', '--change-request'}


def encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path, *, private=False, limit=MAX_BYTES):
    path = Path(path).expanduser().absolute()
    if private and (os.name != 'posix' or fcntl is None):
        raise ValueError('Private workspaces currently require POSIX owner-only permissions')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Expected a bounded regular file without symlinks')
    if private and (path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid()):
        raise ValueError('Private state files require owner-only permissions')
    return path


def read(path, **kwargs):
    return json.loads(regular(path, **kwargs).read_bytes())


def atomic(path, raw):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing a symlink output')
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_dir(path, *, create=False):
    if os.name != 'posix' or fcntl is None:
        raise ValueError('Private workspaces currently require POSIX owner-only permissions')
    path = Path(path).expanduser().absolute()
    if create and not path.exists():
        path.mkdir(mode=0o700, parents=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise ValueError('Use a dedicated owner-only workspace directory (0700), without symlinks')
    return path


@contextmanager
def locked(workspace):
    workspace = private_dir(workspace)
    lock_path = workspace / '.workspace.lock'
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as lock:
        if os.fstat(lock.fileno()).st_mode & 0o077:
            raise ValueError('Workspace lock must be private')
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield workspace


def label(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(character) < 32 for character in value):
        raise ValueError(f'Invalid {name}')
    if re.search(r'\bBearer\s+\S{16,}|\bsk-[A-Za-z0-9_-]{16,}', value):
        raise ValueError('Credentials cannot be used as task labels')
    return value


def thread_identity(value):
    value = value or os.environ.get('CODEX_THREAD_ID')
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise ValueError('Supply an originating Codex UUID with --thread-id or CODEX_THREAD_ID')
    return str(uuid.UUID(value))


def checked_port(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1024 <= value <= 65535:
        raise ValueError('Expected a localhost port between 1024 and 65535')
    return value


def network(manifest):
    value = manifest.get('networkAccess', {})
    if value.get('allowedDomains') != ['none'] or set(value) - {'allowedDomains', 'devAllowedDomains'}:
        raise ValueError('Generated task requests an unsupported network boundary')
    domains = value.get('devAllowedDomains', [])
    if not isinstance(domains, list) or len(domains) > 8 or len(set(domains)) != len(domains):
        raise ValueError('Local development domains must be bounded and unique')
    for domain in domains:
        match = re.fullmatch(r'http://localhost:([0-9]{1,5})', domain) if isinstance(domain, str) else None
        if not match:
            raise ValueError('Only exact localhost development origins are allowed')
        checked_port(int(match[1]))
    return domains


def trusted_sources():
    hasher = hashlib.sha256()
    for folder in ('tools', 'figma-bridge', 'library'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.js', '.html', '.css', '.json'}:
                if path.is_symlink():
                    raise ValueError('Trusted generator sources cannot be symlinks')
                hasher.update(str(path.relative_to(ROOT)).encode())
                hasher.update(path.read_bytes())
    return hasher.hexdigest()


def arguments(kind, values, *, create_pair=True):
    result, parsed, pins = [], {}, {}
    index = 0
    while index < len(values):
        item = values[index]
        option, equals, value = item.partition('=')
        if option not in OPTIONS[kind]:
            raise ValueError('Only exact flags from the selected trusted generator are accepted')
        if option in parsed and option != '--include-page-id':
            raise ValueError('Duplicate generator option')
        if option == '--adopt':
            if equals:
                raise ValueError('--adopt does not take a value')
            value = True
            result.append(option)
        else:
            if not equals:
                index += 1
                if index == len(values):
                    raise ValueError('Missing generator option value')
                value = values[index]
            if not value or value.startswith('--'):
                raise ValueError('Missing generator option value')
            if option in PATH_OPTIONS:
                path = regular(value)
                value = str(path.resolve())
                pins[option] = digest(path.read_bytes())
            elif option == '--pair-dir':
                value = str(private_dir(value, create=create_pair).resolve())
            elif option == '--receiver-port':
                value = str(checked_port(int(value)))
            elif option == '--paired-state':
                value = str(private_dir(value).resolve())
                pins[option] = digest(regular(Path(value) / 'connection.json', private=True, limit=1_000_000).read_bytes())
            result.extend([option, value])
        parsed.setdefault(option, []).append(value)
        index += 1
    return result, {key: value if key == '--include-page-id' else value[0] for key, value in parsed.items()}, pins


def paired_compile(options, output, plugin_id):
    from figma_bridge import compile_plugin
    connection = read(Path(options['--paired-state']) / 'connection.json', private=True, limit=1_000_000)
    owner = connection.get('identity', {})
    if owner.get('plugin_id') != plugin_id or owner.get('resolved_sha256') != options.get('--reviewed-sha256') or owner.get('resolved_sha256') != digest(Path(options['--input']).read_bytes()):
        raise ValueError('Paired state identity or reviewed source differs from the workspace')
    if not re.fullmatch(r'[A-Za-z0-9]+', str(owner.get('file_key', ''))) or not re.fullmatch(r'[0-9]+:[0-9]+', str(owner.get('page_id', ''))):
        raise ValueError('Paired state requires exact native file and page pins')
    token = connection.get('token')
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{64}', token):
        raise ValueError('Invalid private paired capability')
    sync_port, preview_port = checked_port(connection['sync_port']), checked_port(connection['preview_port'])
    client = http.client.HTTPConnection('localhost', sync_port, timeout=3)
    try:
        # Invalid shape is rejected before native snapshots or project state can be applied.
        client.request('POST', '/sync', b'{}', {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        response = client.getresponse()
        body = response.read(4096)
        if response.status != 409 or json.loads(body) != {'error': 'Expected the paired native snapshot.'}:
            raise ValueError('Existing paired endpoint did not authenticate the expected protocol')
    finally:
        client.close()
    project = Path(owner.get('project', '')).resolve(strict=True)
    product = options.get('--product-graph')
    if product and Path(product).resolve() != project / 'graph.json':
        raise ValueError('Paired production graph differs from its owner')
    if not options.get('--selection') and (options.get('--batch') or options.get('--asset-receipts')):
        raise ValueError('Asset receipts require selected production admission')
    config = {'url': f'http://localhost:{sync_port}/sync', 'preview_url': f'http://localhost:{preview_port}/',
              'file_key': owner['file_key'], 'page_id': owner['page_id'], 'token': token}
    try:
        compile_plugin(options['--input'], options['--reviewed-sha256'], output, plugin_id,
            local_sync=config, technical_existing=not options.get('--selection'), selection_path=options.get('--selection'),
            product_graph=project / 'graph.json' if options.get('--selection') else None,
            batch_path=options.get('--batch'), asset_receipts=options.get('--asset-receipts'))
    except (ValueError, OSError, TypeError, KeyError) as error:
        raise ValueError('Trusted paired generator rejected its source admission') from error
    return owner['file_key'], owner['page_id']


def generate(kind, args, options, output, plugin_id):
    file_key = page_id = None
    if kind == 'import' and '--paired-state' in options:
        file_key, page_id = paired_compile(options, output, plugin_id)
        bundle = output
    else:
        if kind == 'import':
            command, tail, bundle = 'figma_bridge.py', args, output
        elif kind == 'review':
            portable = []
            for option, value in options.items():
                if option not in ('--pair-dir', '--receiver-port'):
                    portable.extend([option, value])
            command, tail, bundle = 'figma_draft.py', ['prepare', *portable], output / 'plugin'
        elif kind == 'native-edit':
            command, tail, bundle = 'native_edit.py', ['prepare', *args], output
        elif kind == 'discover':
            command, tail, bundle = 'graph_sync.py', ['discover', *args], output
        else:
            command, tail, bundle = 'graph_sync.py', ['export', *args, '--web-module', str(output / 'web-module.mjs')], output
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools' / command), *tail,
            '--out', str(output), '--plugin-id', plugin_id], cwd=ROOT, capture_output=True, timeout=180)
        if result.returncode:
            raise ValueError('Trusted generator rejected the task; verify its source pins and admission requirements')
    if kind == 'review' and ('--pair-dir' in options or '--receiver-port' in options):
        if options.get('--selection'):
            raise ValueError('Selected production uses its own verifier; exploratory receiver pairing is unsupported')
        if not options.get('--pair-dir') or not options.get('--receiver-port'):
            raise ValueError('Paired review requires both --pair-dir and --receiver-port')
        from figma_draft import ui_html
        packet = read(output / 'packet.json')
        if not packet.get('fileKey'):
            raise ValueError('Paired review requires an explicit checked Figma file target')
        pair_dir = private_dir(options['--pair-dir'])
        pair_identity = {'schema': 'figma-flow-workspace-review-pair-v1', 'plugin_id': plugin_id,
                         'fileKey': packet['fileKey'], 'packet_sha256': packet['packet_sha256'],
                         'receiver_port': int(options['--receiver-port'])}
        owner_path = pair_dir / 'identity.json'
        if owner_path.exists() and read(owner_path, private=True, limit=4096) != pair_identity:
            raise ValueError('Review pairing belongs to a different file, packet, port or plugin')
        capability = pair_dir / 'capability'
        if not capability.exists():
            atomic(capability, secrets.token_hex(32).encode())
        token = regular(capability, private=True, limit=128).read_text().strip()
        if not re.fullmatch(r'[0-9a-f]{64}', token):
            raise ValueError('Invalid private review capability')
        if not owner_path.exists():
            atomic(owner_path, encode(pair_identity))
        paired = output / 'paired-plugin'
        paired.mkdir(mode=0o700)
        for name in ('code.js', 'manifest.json'):
            atomic(paired / name, regular(bundle / name).read_bytes())
        atomic(paired / 'ui.html', ui_html({'url': 'http://localhost:' + options['--receiver-port'] + '/draft-readback', 'capability': token}, review=packet).encode())
        paired_manifest = read(paired / 'manifest.json')
        paired_manifest['networkAccess']['devAllowedDomains'] = ['http://localhost:' + options['--receiver-port']]
        atomic(paired / 'manifest.json', encode(paired_manifest))
        bundle = paired
    manifest = read(bundle / 'manifest.json')
    if manifest.get('id') != plugin_id or manifest.get('main') != 'code.js' or manifest.get('ui') != 'ui.html' or manifest.get('api') != '1.0.0' or manifest.get('editorType') != ['figma'] or manifest.get('documentAccess') != 'dynamic-page':
        raise ValueError('Generated plugin identity or entry contract differs from this workspace')
    domains = network(manifest)
    regular(bundle / 'code.js')
    regular(bundle / 'ui.html')
    if kind == 'sync':
        data = read(output / 'native-plan.json')
        file_key, page_id, identity = data['file_key'], data['page_id'], data
    elif kind == 'review':
        data = read(output / 'packet.json')
        file_key, identity = data.get('fileKey'), {key: value for key, value in data.items() if key != 'prepared_at'}
        if '--pair-dir' in options:
            identity = {'packet': identity, 'capability_sha256': digest(regular(Path(options['--pair-dir']) / 'capability', private=True).read_bytes())}
    elif kind == 'native-edit':
        identity = read(output / 'native-edit-plan.json')
        file_key, page_id = identity['file_key'], identity['page_id']
    elif kind == 'discover':
        file_key, page_id = options.get('--file-key'), options.get('--page-id')
        identity = options
    else:
        identity = read(output / 'reviewed-payload.json')
    return bundle, file_key, page_id, domains, digest(encode(identity))


def private_tree(path):
    total = 0
    for item in [path, *path.rglob('*')]:
        if item.is_symlink() or not (item.is_dir() or item.is_file()):
            raise ValueError('Generated artifacts must be regular files or directories')
        if item.is_file():
            total += item.stat().st_size
        item.chmod(0o700 if item.is_dir() else 0o600)
    if total > MAX_BYTES:
        raise ValueError('Generated task exceeds the private artifact size limit')


def child(workspace, relative):
    path = workspace
    for part in Path(relative).parts:
        if part in ('..', '/', ''):
            raise ValueError('Workspace path escape')
        path = path / part
        if path.is_symlink():
            raise ValueError('Workspace paths cannot traverse symlinks')
    return path


def sign_catalogue(workspace, catalogue):
    key = regular(Path(workspace) / 'compiler.key', private=True, limit=128).read_bytes()
    if len(key) != 32:
        raise ValueError('Invalid private compiler signing key')
    payload = {name: value for name, value in catalogue.items() if name != 'signature'}
    return {**payload, 'signature': hmac.new(key, encode(payload), hashlib.sha256).hexdigest()}


def require_idle_publication(workspace):
    # figma_control imports this module, so the control schema is read at call time.
    from figma_control import SCHEMA as CONTROL_SCHEMA
    directory = child(workspace, '.control')
    if not directory.exists():
        return
    directory = child(private_dir(directory), 'requests')
    if not directory.exists():
        return
    for path in private_dir(directory).glob('*.json'):
        request = read(path, private=True, limit=32768)
        if not isinstance(request, dict) or request.get('schema') != CONTROL_SCHEMA:
            raise ValueError('Invalid private control request')
        if request.get('state') == 'claimed':
            raise ValueError('Workspace publication blocked: wait for current native run to finish; inspect status with figma_control.py status')


def current(workspace, *, repair=True):
    identity = read(workspace / 'identity.json', private=True)
    if identity.get('schema') != SCHEMA or not re.fullmatch(r'[0-9]+', str(identity.get('plugin_id', ''))):
        raise ValueError('Unknown workspace identity')
    manifest = read(workspace / 'manifest.json', private=True)
    if manifest.get('name') != display_name() or manifest.get('id') != identity['plugin_id']:
        raise ValueError('Foreign plugin identity cannot be replaced')
    match = re.fullmatch(r'\.generations/([a-f0-9]{32})/code.js', str(manifest.get('main', '')))
    if not match or manifest.get('ui') != f'.generations/{match[1]}/ui.html':
        raise ValueError('Workspace generation pointer is invalid')
    folder = private_dir(child(workspace, '.generations/' + match[1]))
    catalogue = read(folder / 'catalogue.json', private=True)
    if not hmac.compare_digest(str(catalogue.get('signature', '')), sign_catalogue(workspace, catalogue)['signature']):
        raise ValueError('Workspace catalogue signature mismatch')
    if catalogue.get('plugin_id') != identity['plugin_id'] or catalogue.get('generation') != match[1] or catalogue.get('schema') != SCHEMA:
        raise ValueError('Workspace catalogue identity mismatch')
    if repair and (not (workspace / 'catalogue.json').exists() or read(workspace / 'catalogue.json', private=True) != catalogue):
        require_idle_publication(workspace)
        atomic(workspace / 'catalogue.json', encode(catalogue))
    return catalogue


def chat_config(workspace):
    if not (workspace / 'chat.json').exists():
        return None
    config = read(workspace / 'chat.json', private=True, limit=4096)
    if config.get('schema') != 'figma-flow-workspace-chat-v1' or not re.fullmatch(r'[0-9a-f]{64}', str(config.get('token', ''))):
        raise ValueError('Invalid private workspace chat configuration')
    return {'url': f'http://localhost:{checked_port(config["port"])}', 'token': config['token']}


def check_source_pins(pins):
    if not isinstance(pins, list) or len(pins) > 256:
        raise ValueError('Invalid bounded source input pins')
    seen = set()
    for pin in pins:
        if not isinstance(pin, dict) or set(pin) != {'path', 'sha256'}:
            raise ValueError('Invalid source input pin')
        path, sha = pin['path'], pin['sha256']
        if not isinstance(path, str) or not Path(path).is_absolute() or path in seen or not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha):
            raise ValueError('Invalid source input path or digest')
        seen.add(path)
        if digest(regular(path).read_bytes()) != sha:
            raise ValueError('Source inputs changed; obtain fresh admission before preparation')
    return pins


def source_inputs(staging):
    sidecar = staging / 'source-inputs.json'
    if not sidecar.exists():
        return []
    value = read(sidecar, private=True, limit=128 * 1024)
    if not isinstance(value, dict) or set(value) != {'schema', 'pins'} or value['schema'] != 'figma-flow-source-pins-v1':
        raise ValueError('Invalid generator source input sidecar')
    return check_source_pins(value['pins'])


def runtime_info(catalogue):
    return {'version': read(ROOT / 'plugin.json')['version'],
            'implementation': trusted_sources(), 'generation': catalogue['generation']}


def task_artifacts(workspace, task):
    check_source_pins(task.get('source_input_pins', []))
    if 'generator_args' in task:
        _, _, pins = arguments(task['kind'], task['generator_args'], create_pair=False)
        if pins != task.get('input_pins'):
            raise ValueError('Prepared task inputs changed; obtain fresh admission')
    relative = task['artifact_dir']
    if not re.fullmatch(r'\.tasks/[a-f0-9]{32}', relative):
        raise ValueError('Task artifact path escapes the private catalogue')
    folder = private_dir(child(workspace, relative))
    bundle_relative = task['bundle_relative']
    if bundle_relative not in ('.', 'plugin', 'paired-plugin'):
        raise ValueError('Unsupported task bundle entry')
    bundle = child(folder, bundle_relative)
    if set(task['artifact_hashes']) != {'code.js', 'ui.html', 'manifest.json'}:
        raise ValueError('Prepared task artifact coverage is incomplete')
    for name, sha in task['artifact_hashes'].items():
        if name not in ('code.js', 'ui.html', 'manifest.json') or digest(regular(bundle / name, private=True).read_bytes()) != sha:
            raise ValueError('Prepared task artifacts changed; prepare a fresh admitted task')
    return bundle


def task_surface(kind, code, original_html, *, shared=False):
    """Rebuild presentation from admitted data without replacing its pinned native handler."""
    bridge = ROOT / 'figma-bridge'
    if kind == 'review':
        from figma_draft import review_thumbnails
        if not code.startswith('const DRAFT='):
            raise ValueError('Unknown prepared review entry')
        packet, _ = json.JSONDecoder().raw_decode(code[len('const DRAFT='):])
        pair_line = re.search(r'^const PAIR = (.*);$', original_html, re.M)
        if not pair_line:
            raise ValueError('Unknown review pairing contract')
        pair = json.loads(pair_line[1])
        candidates = []
        for candidate in packet['candidates']:
            previews = [{'viewport': viewport, 'src': 'data:image/png;base64,' + data}
                        for viewport, data in review_thumbnails(packet, candidate)]
            candidates.append({'title': candidate['title'], 'previews': previews})
        cover = [{'title': entry['title'], 'src': entry['previews'][0]['src']}
                 for entry in candidates[:2] if entry['previews']]
        model = {'candidates': candidates, 'pair': pair, 'filePinned': bool(packet.get('fileKey')),
                 'pageName': ('PRODUCTION · ' + packet['candidates'][0]['title'] if packet.get('scope') == 'selected-production' else 'DRAFT · A/B/C 방향 검토') + ' · ' + packet['packet_sha256'][:8],
                 'selectedProduction': packet.get('scope') == 'selected-production', 'scope': packet['scope'], 'sourceSelection': packet.get('sourceSelection')}
        return {'preview': cover}, render_app('review', model, shared=shared)
    if kind == 'import':
        payload, _ = json.JSONDecoder().raw_decode(code.split('\nconst PAYLOAD = ', 1)[1])
        facts = {'productionAdmitted': bool(payload.get('native_admission') and payload.get('selected_direction')),
                 'sourceSha256': payload['source_sha256']}
        return facts, render_app('import', shared=shared)
    match = re.search(r'<script id="graph-panel-config" type="application/json">(.*?)</script>', original_html, re.S)
    if not match:
        raise ValueError('Unknown prepared graph panel')
    return {}, render_app('graph', json.loads(match[1]), shared=shared)


def normalize_task_dependencies(tasks, dependencies=None):
    """Validate explicit uses-output edges. Same project does not create an edge."""
    if not isinstance(tasks, list):
        raise ValueError('Task dependency catalogue required')
    by_key = {}
    for task in tasks:
        key = task.get('key') if isinstance(task, dict) else None
        if not isinstance(key, str) or key in by_key:
            raise ValueError('duplicate or invalid task')
        by_key[key] = task
    if dependencies is not None and not isinstance(dependencies, dict):
        raise ValueError('Task dependencies must be a map')
    provided = dependencies or {}
    normalized = []
    outgoing = {}
    for task in tasks:
        explicit = task['key'] in provided or 'depends_on' in task
        raw = provided[task['key']] if task['key'] in provided else task.get('depends_on', [])
        if not isinstance(raw, list):
            raise ValueError('Task dependencies must be a list')
        edges = []
        seen = set()
        for edge in raw:
            if not isinstance(edge, dict) or set(edge) != {'task_key', 'revision', 'relation', 'artifact', 'artifact_sha256'}:
                raise ValueError('Invalid task dependency')
            target = edge['task_key']
            if target == task['key']:
                raise ValueError(f'self edge: {task["key"]}')
            if target not in by_key:
                raise ValueError(f'missing target: {target}')
            if edge['relation'] != 'uses-output':
                raise ValueError(f'unsupported dependency relation: {edge["relation"]}')
            if edge['revision'] != by_key[target].get('revision'):
                raise ValueError(f'dependency revision is not current: {target}')
            artifact = edge['artifact']
            if not isinstance(artifact, str) or artifact not in {'code.js', 'ui.html', 'manifest.json'}:
                raise ValueError(f'unregistered artifact: {artifact}')
            digest_value = edge['artifact_sha256']
            if by_key[target].get('artifact_hashes', {}).get(artifact) != digest_value:
                raise ValueError(f'artifact hash mismatch: {target}/{artifact}')
            identity = (target, edge['revision'], edge['relation'], artifact, digest_value)
            if identity in seen:
                raise ValueError(f'duplicate edge: {task["key"]} -> {target}')
            seen.add(identity)
            edges.append(dict(edge))
        outgoing[task['key']] = [item['task_key'] for item in edges]
        if explicit:
            stored = dict(task)
            stored['depends_on'] = edges
            normalized.append(stored)
        else:
            normalized.append(task)
    visiting, visited = set(), set()

    def walk(key):
        if key in visiting:
            raise ValueError(f'cycle: {key}')
        if key in visited:
            return
        visiting.add(key)
        for target in outgoing.get(key, []):
            walk(target)
        visiting.remove(key)
        visited.add(key)

    for key in outgoing:
        walk(key)
    return normalized


def load_task_dependency_fixtures(root):
    """Load the pinned legacy catalogue and the one declared uses-output edge."""
    root = Path(root)
    legacy = json.loads((root / 'tests/fixtures/rd03/legacy-tasks.json').read_text(encoding='utf-8'))
    declared = json.loads((root / 'tests/fixtures/rd03/declared-edges.json').read_text(encoding='utf-8'))
    if legacy.get('schema') != 'figma-flow-task-fixture-v1' or declared.get('schema') != 'figma-flow-task-fixture-v1':
        raise ValueError('Invalid task dependency fixture')
    return {'legacy': normalize_task_dependencies(legacy['tasks']), 'declared': normalize_task_dependencies(declared['tasks'])}


def publish(workspace, catalogue):
    catalogue = {**catalogue, 'tasks': normalize_task_dependencies(catalogue['tasks'])}
    require_idle_publication(workspace)
    generation = uuid.uuid4().hex
    runtime = runtime_info({'generation': generation})
    folder = child(workspace, '.generations/' + generation)
    folder.mkdir(mode=0o700)
    tasks, domains = [], set()
    for task in catalogue['tasks']:
        bundle = task_artifacts(workspace, task)
        domains.update(task['domains'])
        metadata = {key: task.get(key) for key in ('key', 'title', 'project', 'kind', 'fileKey', 'pageId', 'threadId', 'revision', 'handoff')}
        code = regular(bundle / 'code.js', private=True).read_text()
        facts, html = task_surface(task['kind'], code, regular(bundle / 'ui.html', private=True).read_text(), shared=True)
        metadata.update(facts, paired=bool(task['domains']))
        tasks.append(json.dumps(metadata, ensure_ascii=True)[:-1] + ',"run":function(){const figma=workspaceTaskFigma();const __html__=workspaceTaskHtml(workspaceAppHtml(' + json.dumps(html, ensure_ascii=True) + '));\n' + code + '\n}}')
    control = None
    if (workspace / 'control.json').exists():
        from figma_control import config
        private = config(workspace)
        control = {'url': f'http://localhost:{private["port"]}', 'token': private['token']}
        domains.add(control['url'])
    relay = chat_config(workspace)
    if relay:
        domains.add(relay['url'])
    if len(domains) > 8:
        raise ValueError('Workspace exceeds its exact localhost origin limit')
    bridge = ROOT / 'figma-bridge'
    code = 'const WORKSPACE_RUNTIME = ' + json.dumps(runtime) + ';\n'
    chat_catalog = json.loads((bridge / 'locales/chat.json').read_text(encoding='utf-8'))
    code += 'const FLOW_LOCALES = ' + json.dumps(list(supported_locales()), ensure_ascii=True) + ';\n'
    code += 'const FLOW_CHAT_DUPLICATE = ' + json.dumps(chat_catalog['chat.duplicate']['ko'], ensure_ascii=False) + ';\n'
    code += 'const FLOW_TASKS = [' + ',\n'.join(tasks) + '];\n'
    assets = bridge / 'assets'
    react_js = re.sub(r'</script', lambda _match: r'<\/script', (assets / 'panels.js').read_text(), flags=re.I)
    code += 'const packagedReact = ' + json.dumps(react_js) + ';\n'
    code += 'const packagedCSS = ' + json.dumps((assets / 'panels.css').read_text()) + ';\n'
    code += "function workspaceAppHtml(template){return template.replace('/* FLOW_SHARED_PANEL_STYLES */',()=>packagedCSS).replace('/* FLOW_SHARED_REACT_APPLICATION */',()=>packagedReact);}" + '\n'
    code += 'const WORKSPACE_CONTROL_CONFIG = ' + json.dumps(control, ensure_ascii=True) + ';\n'
    code += 'const WORKSPACE_CHAT_CONFIG = ' + json.dumps(relay, ensure_ascii=True) + ';\n'
    code += 'const WORKSPACE_CHAT_UI = workspaceAppHtml(' + json.dumps(render_app('chat', chat_context=True, shared=True), ensure_ascii=True) + ');\n'
    code += (bridge / 'workspace_chat.js').read_text() + '\n' + (bridge / 'workspace_control.js').read_text() + '\n' + (bridge / 'workspace_host.js').read_text()
    if runtime['implementation'] != trusted_sources():
        raise ValueError('Trusted runtime sources changed during publication; retry')
    atomic(folder / 'code.js', code.encode())
    atomic(folder / 'ui.html', render_app('workspace').encode())
    result = sign_catalogue(workspace, {**catalogue, 'generation': generation, 'runtime': runtime})
    atomic(folder / 'catalogue.json', encode(result))
    manifest = {'name': display_name(), 'id': catalogue['plugin_id'], 'api': '1.0.0',
        'main': f'.generations/{generation}/code.js', 'ui': f'.generations/{generation}/ui.html',
        'editorType': ['figma'], 'documentAccess': 'dynamic-page', 'enablePrivatePluginApi': True,
        'networkAccess': {'allowedDomains': ['none']}}
    if domains:
        manifest['networkAccess']['devAllowedDomains'] = sorted(domains)
    network(manifest)
    atomic(workspace / 'catalogue.json', encode(result))
    atomic(workspace / 'manifest.json', encode(manifest))
    return result


def init(workspace, id_from, chat_port=None):
    assigned = read(id_from, limit=1_000_000).get('id')
    if not isinstance(assigned, str) or not re.fullmatch(r'[0-9]+', assigned):
        raise ValueError('--id-from must contain a Figma-assigned numeric plugin ID')
    workspace = Path(workspace).expanduser().absolute()
    if workspace.exists() and not (workspace / 'identity.json').exists() and any(workspace.iterdir()):
        raise ValueError('Refusing to overwrite unrelated workspace files')
    workspace = private_dir(workspace, create=True)
    with locked(workspace):
        if not (workspace / 'manifest.json').exists() or chat_port is not None:
            require_idle_publication(workspace)
        if (workspace / 'identity.json').exists():
            identity = read(workspace / 'identity.json', private=True)
            if identity != {'schema': SCHEMA, 'plugin_id': assigned}:
                raise ValueError('Workspace already belongs to a different plugin identity')
        else:
            atomic(workspace / 'identity.json', encode({'schema': SCHEMA, 'plugin_id': assigned}))
        if chat_port is not None:
            checked_port(chat_port)
            if (workspace / 'chat.json').exists():
                if read(workspace / 'chat.json', private=True)['port'] != chat_port:
                    raise ValueError('Workspace already owns a different chat endpoint')
            else:
                atomic(workspace / 'chat.json', encode({'schema': 'figma-flow-workspace-chat-v1', 'port': chat_port, 'token': secrets.token_hex(32)}))
        if not (workspace / 'compiler.key').exists():
            atomic(workspace / 'compiler.key', secrets.token_bytes(32))
        for name in ('.tasks', '.generations'):
            private_dir(workspace / name, create=True)
        catalogue = current(workspace) if (workspace / 'manifest.json').exists() else {'schema': SCHEMA, 'plugin_id': assigned, 'tasks': []}
        if not (workspace / 'manifest.json').exists() or chat_port is not None:
            catalogue = publish(workspace, catalogue)
        return {'manifest': str(workspace / 'manifest.json'), 'plugin_id': assigned, 'tasks': len(catalogue['tasks'])}


def prepare(workspace, key, title, kind, generator_args, project=None, thread_id=None, replace_expected=None, *, infer_thread=True, depends_on=None):
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', key) or len(key) > 64:
        raise ValueError('Task keys must be lowercase readable kebab names, at most 64 characters')
    title = label(title, 'task title', 160)
    project = label(project, 'project label', 120) if project else ''
    thread_id = thread_identity(thread_id) if thread_id is not None or infer_thread else None
    if kind not in OPTIONS:
        raise ValueError('Unknown trusted task kind')
    args, options, pins = arguments(kind, generator_args)
    payload = {'kind': kind, 'args': args, 'pins': pins, 'title': title, 'project': project, 'threadId': thread_id}
    if depends_on is not None:
        payload['depends_on'] = depends_on
    request_sha = digest(encode(payload))
    with locked(workspace) as workspace:
        catalogue = current(workspace)
        previous = next((task for task in catalogue['tasks'] if task['key'] == key), None)
        if previous and replace_expected is None and previous.get('request_sha256') != request_sha:
            raise ValueError('Task key already exists with different inputs; use --replace-expected')
        if replace_expected is not None and (not previous or previous['revision'] != replace_expected):
            raise ValueError('Stale task revision; list the workspace before replacement')
        before = trusted_sources()
        with tempfile.TemporaryDirectory(prefix='.prepare-', dir=workspace) as temporary:
            staging = Path(temporary) / 'artifacts'
            bundle, file_key, page_id, domains, source_sha = generate(kind, args, options, staging, catalogue['plugin_id'])
            if before != trusted_sources():
                raise ValueError('Trusted generator sources changed during preparation; retry')
            nested_pins = source_inputs(staging)
            if arguments(kind, args, create_pair=False)[2] != pins:
                raise ValueError('Source inputs changed during preparation')
            revision = digest(encode({'request': request_sha, 'source': source_sha, 'generators': before, 'source_inputs': nested_pins}))
            if previous and replace_expected is None:
                if previous['revision'] != revision:
                    raise ValueError('Task key already exists with different inputs; use --replace-expected')
                task_artifacts(workspace, previous)
                return {'key': key, 'revision': revision, 'unchanged': True, 'manifest': str(workspace / 'manifest.json')}
            require_idle_publication(workspace)
            private_tree(staging)
            artifact_id = uuid.uuid4().hex
            relative = '.tasks/' + artifact_id
            bundle_relative = str(bundle.relative_to(staging)) or '.'
            task = {'key': key, 'title': title, 'project': project, 'kind': kind,
                'generator_args': args, 'input_pins': pins, 'source_input_pins': nested_pins, 'generator_sha256': before,
                'threadId': thread_id, 'fileKey': file_key, 'pageId': page_id,
                'revision': revision, 'request_sha256': request_sha, 'artifact_dir': relative, 'bundle_relative': bundle_relative,
                'domains': domains, 'artifact_hashes': {name: digest((bundle / name).read_bytes()) for name in ('code.js', 'ui.html', 'manifest.json')}}
            if depends_on is not None:
                merged = normalize_task_dependencies([*(item for item in catalogue['tasks'] if item['key'] != key), task], {key: depends_on})
                task = next(item for item in merged if item['key'] == key)
            os.replace(staging, child(workspace, relative))
            tasks = [task if item['key'] == key else item for item in catalogue['tasks']]
            if previous is None:
                tasks.append(task)
            result = publish(workspace, {**catalogue, 'tasks': tasks})
            artifact_root = workspace / relative
            return {'key': key, 'revision': revision, 'unchanged': False, 'manifest': str(workspace / 'manifest.json'),
                'generation': result['generation'], 'artifacts': str(artifact_root),
                'web_module': str(artifact_root / 'web-module.mjs') if kind == 'sync' else None}


def replay(workspace, key, expected_revision):
    with locked(workspace) as root:
        catalogue = current(root)
        row = next((row for row in catalogue['tasks'] if row['key'] == key), None)
        if not row or row['revision'] != expected_revision:
            raise ValueError('Stale task revision; list the workspace before replay')
        if 'generator_args' not in row or 'input_pins' not in row:
            raise ValueError('Legacy task has no replay arguments; prepare with original admission')
        task_artifacts(root, row)
        args = row['generator_args']
    return prepare(workspace, key, row['title'], row['kind'], args,
                   row.get('project'), row.get('threadId'), expected_revision, infer_thread=False)


def list_tasks(workspace):
    with locked(workspace) as workspace:
        catalogue = current(workspace)
        return {'manifest': str(workspace / 'manifest.json'), 'plugin_id': catalogue['plugin_id'],
            'tasks': [{key: task.get(key) for key in ('key', 'title', 'project', 'kind', 'threadId', 'fileKey', 'pageId', 'revision')} for task in catalogue['tasks']]}


def retire(workspace, tasks):
    selection = read(tasks, limit=32768)
    if not isinstance(selection, dict) or set(selection) != {'schema', 'tasks'} or selection['schema'] != 'figma-flow-workspace-retirement-v1':
        raise ValueError('Invalid retirement selection schema')
    selected = selection['tasks']
    if not isinstance(selected, list) or not 1 <= len(selected) <= 128:
        raise ValueError('Retirement requires 1 to 128 exact task revisions')
    expected = {}
    for row in selected:
        if not isinstance(row, dict) or set(row) != {'key', 'revision'}:
            raise ValueError('Invalid retirement task row')
        key, revision = row['key'], row['revision']
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', key) or len(key) > 64 or key in expected or not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision):
            raise ValueError('Invalid or duplicate retirement key or revision')
        expected[key] = revision
    with locked(workspace) as root:
        catalogue = current(root, repair=False)
        rows = {row['key']: row for row in catalogue['tasks']}
        if any(key not in rows or rows[key]['revision'] != revision for key, revision in expected.items()):
            raise ValueError('Retirement conflict: unknown task or stale revision; list the workspace')
        require_idle_publication(root)
        directory = child(root, '.control')
        marker = child(root, '.control/uncertainty.json')
        if marker.exists():
            from figma_control import SCHEMA as CONTROL_SCHEMA
            pending = read(marker, private=True, limit=1_000_000)
            if not isinstance(pending, dict) or pending.get('schema') != CONTROL_SCHEMA or not isinstance(pending.get('operations'), dict):
                raise ValueError('Invalid private uncertainty marker')
            uncertain = bool(pending['operations'])
        else:
            uncertain = any(request.get('state') == 'uncertain' and request.get('operation') != 'read'
                for request in (read(path, private=True, limit=32768) for path in child(directory, 'requests').glob('*.json')))
        if uncertain:
            raise ValueError('Retirement blocked: native mutation remains uncertain; re-read the native state')
        remaining = [row for row in catalogue['tasks'] if row['key'] not in expected]
        for row in remaining:
            task_artifacts(root, row)
        record = {'schema': 'figma-flow-workspace-retirement-record-v1',
            'created_at': datetime.now(timezone.utc).isoformat(), 'before_generation': catalogue['generation'],
            'catalogue_before': catalogue, 'retired_tasks': [rows[key] for key in expected]}
        records = private_dir(child(root, '.retired'), create=True)
        record_path = records / (uuid.uuid4().hex + '.json')
        with record_path.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encode(record))
            stream.flush()
            os.fsync(stream.fileno())
        before = regular(root / 'catalogue.json', private=True).read_bytes()
        try:
            result = publish(root, {**catalogue, 'tasks': remaining})
        except Exception:
            # The manifest is the commit point; retain the intent record on failure.
            atomic(root / 'catalogue.json', before)
            raise
        return {'retired': selected, 'record': str(record_path), 'generation': result['generation'],
            'manifest': str(root / 'manifest.json')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('init', allow_abbrev=False)
    create.add_argument('--workspace', required=True)
    create.add_argument('--id-from', required=True)
    create.add_argument('--chat-port', type=int)
    build = commands.add_parser('prepare', allow_abbrev=False)
    for option in ('workspace', 'key', 'title', 'kind'):
        build.add_argument('--' + option, required=True)
    build.add_argument('--project')
    build.add_argument('--thread-id')
    build.add_argument('--replace-expected')
    refresh = commands.add_parser('refresh', allow_abbrev=False)
    refresh.add_argument('--workspace', required=True)
    replaying = commands.add_parser('replay', allow_abbrev=False)
    for option in ('workspace', 'key', 'expected-revision'):
        replaying.add_argument('--' + option, required=True)
    listing = commands.add_parser('list', allow_abbrev=False)
    listing.add_argument('--workspace', required=True)
    retiring = commands.add_parser('retire', allow_abbrev=False)
    retiring.add_argument('--workspace', required=True)
    retiring.add_argument('--tasks', required=True)
    values = list(sys.argv[1:] if argv is None else argv)
    separator = values.index('--') if '--' in values else len(values)
    args = parser.parse_args(values[:separator])
    if os.name != 'posix' or fcntl is None:
        print('figma-workspace: private workspaces currently require POSIX owner-only permissions; use the standalone generators on this platform', file=sys.stderr)
        return 2
    try:
        if args.command == 'init':
            if separator != len(values):
                raise ValueError('init does not accept generator arguments')
            result = init(args.workspace, args.id_from, args.chat_port)
        elif args.command == 'refresh':
            if separator != len(values):
                raise ValueError('refresh does not accept generator arguments')
            with locked(args.workspace) as root:
                updated = publish(root, current(root))
                result = {'manifest': str(root / 'manifest.json'), 'generation': updated['generation'], 'tasks': len(updated['tasks'])}
        elif args.command == 'replay':
            if separator != len(values):
                raise ValueError('replay does not accept new generator arguments')
            result = replay(args.workspace, args.key, args.expected_revision)
        elif args.command == 'retire':
            if separator != len(values):
                raise ValueError('retire does not accept generator arguments')
            result = retire(args.workspace, args.tasks)
        elif args.command == 'prepare':
            if separator == len(values):
                raise ValueError('prepare requires literal -- before trusted generator flags')
            result = prepare(args.workspace, args.key, args.title, args.kind, values[separator + 1:], args.project, args.thread_id, args.replace_expected)
        else:
            if separator != len(values):
                raise ValueError('list does not accept generator arguments')
            result = list_tasks(args.workspace)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except ValueError as error:
        print('figma-workspace: ' + str(error), file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError, subprocess.TimeoutExpired):
        print('figma-workspace: preparation rejected; verify private ownership, exact arguments, source admission and current revision', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
