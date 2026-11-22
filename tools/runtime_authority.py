"""Check that runtime task authority stays connected to the profile policy."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import re
import sys

import native_windows
import component_family_contract


def check(root: Path) -> list[dict]:
    """Return actionable policy graph or runtime authority findings."""
    root = Path(root)
    findings: list[dict] = []

    def add(code: str, path: str, message: str, key: str | None = None) -> None:
        finding = {'code': code, 'path': path, 'message': message}
        if key is not None:
            finding['key'] = key
        findings.append(finding)

    policy_path = root / 'library/figma-profile/policy.json'
    try:
        policy = json.loads(policy_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        return [{'code': 'POLICY_UNAVAILABLE', 'path': 'library/figma-profile/policy.json',
                 'message': f'Cannot load runtime authority policy: {error}'}]

    tasks = policy.get('taskOperations')
    capabilities = policy.get('capabilities')
    facts = policy.get('facts')
    operations = policy.get('operations')
    passthrough = policy.get('passthrough')
    options = policy.get('options')
    if not isinstance(options, dict):
        add('PROFILE_OPTIONS_INVALID', 'library/figma-profile/policy.json',
            'Define the declared plan and seat options in the authority policy.')
        options = {}
    for dimension in ('plans', 'seats'):
        values = options.get(dimension)
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
            add('PROFILE_OPTIONS_INVALID', 'library/figma-profile/policy.json',
                f'Define a non-empty string list for options.{dimension}.')
        elif len(values) != len(set(values)):
            add('PROFILE_OPTION_DUPLICATE', 'library/figma-profile/policy.json',
                f'Remove duplicate values from options.{dimension}.')
    if not isinstance(tasks, dict) or not tasks:
        add('TASK_MATRIX_INVALID', 'library/figma-profile/policy.json',
            'Define a non-empty taskOperations object in the authority policy.')
        tasks = {}
    if not isinstance(capabilities, dict) or not capabilities:
        add('CAPABILITY_GRAPH_INVALID', 'library/figma-profile/policy.json',
            'Define a non-empty capabilities object in the authority policy.')
        capabilities = {}
    if not isinstance(facts, dict) or not facts:
        add('FACT_GRAPH_INVALID', 'library/figma-profile/policy.json',
            'Define a non-empty facts object in the authority policy.')
        facts = {}
    if not isinstance(operations, dict):
        add('OPERATION_GRAPH_INVALID', 'library/figma-profile/policy.json',
            'Define an operations map in the authority policy.')
        operations = {}
    if not isinstance(passthrough, list):
        add('PASSTHROUGH_INVALID', 'library/figma-profile/policy.json',
            'Define passthrough as an explicit list in the authority policy.')
        passthrough = []

    for kind, actions in tasks.items():
        if not isinstance(kind, str) or not kind or not isinstance(actions, list) or not actions:
            add('TASK_ENTRY_INVALID', 'library/figma-profile/policy.json',
                'Each task kind must have a non-empty operation list.', str(kind))
            continue
        if any(not isinstance(action, str) or not action for action in actions):
            add('TASK_OPERATION_INVALID', 'library/figma-profile/policy.json',
                'Each task operation must be a non-empty string.', kind)
            continue
        if len(actions) != len(set(actions)):
            add('TASK_OPERATION_DUPLICATE', 'library/figma-profile/policy.json',
                'Remove duplicate operations from this task kind.', kind)
        for action in actions:
            if action not in operations and action not in passthrough:
                add('TASK_OPERATION_UNMAPPED', 'library/figma-profile/policy.json',
                    'Map this task operation to a capability or explicitly mark it passthrough.',
                    f'{kind}/{action}')

    for operation, capability in operations.items():
        if not isinstance(capability, str) or capability not in capabilities:
            add('OPERATION_CAPABILITY_MISSING', 'library/figma-profile/policy.json',
                'Map this operation to a declared capability.', str(operation))
    refresh = policy.get('refreshBeforeDispatch')
    if not isinstance(refresh, list):
        add('REFRESH_RULES_INVALID', 'library/figma-profile/policy.json',
            'Define refreshBeforeDispatch as an explicit list.')
        refresh = []
    for capability in refresh:
        if capability not in capabilities:
            add('REFRESH_CAPABILITY_MISSING', 'library/figma-profile/policy.json',
                'Refresh rules may reference only declared capabilities.', str(capability))
    for capability, alternatives in capabilities.items():
        if not isinstance(alternatives, list) or not alternatives:
            add('CAPABILITY_WITHOUT_FACTS', 'library/figma-profile/policy.json',
                'Each capability needs at least one required-fact alternative.', str(capability))
            continue
        for required in alternatives:
            if not isinstance(required, list) or not required:
                add('CAPABILITY_WITHOUT_FACTS', 'library/figma-profile/policy.json',
                    'Each capability alternative needs at least one required fact.', str(capability))
                continue
            for fact in required:
                if not isinstance(fact, str) or fact not in facts:
                    add('CAPABILITY_FACT_MISSING', 'library/figma-profile/policy.json',
                        'Declare each capability fact in the facts graph.', f'{capability}/{fact}')
    context_fields = policy.get('contextFields')
    known_fact_fields = set(context_fields) if isinstance(context_fields, dict) else set()
    known_fact_fields.update(('plan', 'seat', 'confirmed'))
    for fact, conditions in facts.items():
        if not isinstance(conditions, dict) or not conditions:
            add('FACT_CONDITION_INVALID', 'library/figma-profile/policy.json',
                'Each fact needs at least one field condition.', str(fact))
            continue
        for field, allowed in conditions.items():
            if field not in known_fact_fields or not isinstance(allowed, list) or not allowed:
                add('FACT_CONDITION_INVALID', 'library/figma-profile/policy.json',
                    'Use a declared context/profile field and a non-empty allowed-value list.', f'{fact}/{field}')
                continue
            dimension = {'plan': 'plans', 'seat': 'seats'}.get(field)
            if dimension and isinstance(options.get(dimension), list):
                unknown = [value for value in allowed if value not in options[dimension]]
                if unknown:
                    add('PROFILE_OPTION_UNDECLARED', 'library/figma-profile/policy.json',
                        f'Add these {dimension} values to options or correct the fact condition.',
                        f'{fact}/{field}: {unknown}')
    if any(not isinstance(operation, str) or not operation for operation in passthrough):
        add('PASSTHROUGH_INVALID', 'library/figma-profile/policy.json',
            'Every passthrough operation must be a non-empty string.')
    for operation in passthrough:
        if not isinstance(operation, str):
            continue
        if operation in operations:
            add('OPERATION_POLICY_AMBIGUOUS', 'library/figma-profile/policy.json',
                'An operation cannot be both capability-gated and passthrough.', str(operation))

    sources = {
        'figma-bridge/workspace_control.js': (root / 'figma-bridge/workspace_control.js'),
        'figma-bridge/workspace_host.js': (root / 'figma-bridge/workspace_host.js'),
        'tools/figma_workspace.py': (root / 'tools/figma_workspace.py'),
        'tools/operation_detail.py': (root / 'tools/operation_detail.py'),
    }
    loaded: dict[str, str] = {}
    for relative, path in sources.items():
        try:
            loaded[relative] = path.read_text(encoding='utf-8')
        except OSError as error:
            add('RUNTIME_SOURCE_UNAVAILABLE', relative, f'Cannot inspect runtime authority source: {error}')
    checks = [
        ('figma-bridge/workspace_control.js', r'const\s+controlAllowed\s*=.*?WORKSPACE_PROFILE_POLICY\?\.taskOperations',
         'CONTROL_POLICY_NOT_USED', 'Read task permissions from WORKSPACE_PROFILE_POLICY.taskOperations.'),
        ('figma-bridge/workspace_host.js', r'const\s+workspaceKinds\s*=\s*new Set\([^\n]*WORKSPACE_PROFILE_POLICY',
         'HOST_KIND_POLICY_NOT_USED', 'Derive host task kinds from WORKSPACE_PROFILE_POLICY.taskOperations.'),
        ('tools/figma_workspace.py', r"def\s+bundle_task_kinds\(\):\s+policy\s*=\s*read\(ROOT\s*/\s*'library'.*?return\s+tuple\(sorted\(policy\['taskOperations'\]\)\)",
         'BUNDLE_KIND_POLICY_NOT_USED', 'Derive bundle task kinds from the profile policy.'),
        ('tools/operation_detail.py', r"ALLOWED_TASK_KINDS\s*=\s*set\(_PROFILE_POLICY\['taskOperations'\]\)",
         'DETAIL_KIND_POLICY_NOT_USED', 'Derive detail task kinds from the profile policy.'),
    ]
    for relative, expression, code, message in checks:
        source = loaded.get(relative, '')
        if source and not re.search(expression, source, re.S):
            add(code, relative, message)

    view_consumers = {
        'tools/plugin_panel.py': (
            r'VIEW_REGISTRY\s*=\s*load_view_registry\(\).*?VIEWS\s*=\s*frozenset\(VIEW_REGISTRY\)',
            'PYTHON_VIEW_ROUTER_DRIFT',
            'Derive the Python panel renderer view IDs from the view graph.'),
        'tools/figma_workspace.py': (
            r'from\s+plugin_panel\s+import[^\n]*registered_home_view.*?render_app\(registered_home_view\(\)\)',
            'PUBLISHER_HOME_ROLE_DRIFT',
            'Publish the registered home selected by the view graph role.'),
        'panel-ui/src/app.jsx': (
            r"import\s+\{\s*views\s*\}\s+from\s+['\"]\./view-registry\.generated\.js['\"].*?const\s+View\s*=\s*views\[view\]",
            'REACT_VIEW_ROUTER_DRIFT',
            'Route React views through the graph-generated view registry.'),
        'panel-ui/build.mjs': (
            r"import\s+\{\s*panelViewRegistryModule\s*\}\s+from\s+['\"]\./view-registry\.mjs['\"].*?const\s+viewRegistrySource\s*=\s*await\s+panelViewRegistryModule\(\).*?name:\s*['\"]panel-view-graph['\"]",
            'BUNDLER_VIEW_GRAPH_DRIFT',
            'Generate the React route module from the canonical panel view graph.'),
        'panel-ui/view-registry.mjs': (
            r"const\s+GRAPH_RELATIVE\s*=\s*['\"]library/panel-design/views\.json['\"].*?export\s+async\s+function\s+panelViewRegistryModule",
            'VIEW_REGISTRY_GENERATOR_MISSING',
            'Keep the standard-library view graph module generator available to builds.'),
    }
    panel_sources: dict[str, str] = {}
    for relative, (expression, code, message) in view_consumers.items():
        try:
            panel_sources[relative] = (root / relative).read_text(encoding='utf-8')
        except OSError as error:
            add(code, relative, f'{message} Source unavailable: {error}')
            continue
        if not re.search(expression, panel_sources[relative], re.S):
            add(code, relative, message)
    if 'tools/plugin_panel.py' in panel_sources and re.search(
            r'VIEWS\s*=\s*\{', panel_sources['tools/plugin_panel.py']):
        add('PYTHON_VIEW_MATRIX_DUPLICATED', 'tools/plugin_panel.py',
            'Remove the literal Python view set and derive it from the view graph.')
    if 'panel-ui/src/app.jsx' in panel_sources and re.search(
            r'const\s+views\s*=\s*\{', panel_sources['panel-ui/src/app.jsx']):
        add('REACT_VIEW_MATRIX_DUPLICATED', 'panel-ui/src/app.jsx',
            'Remove the literal React view map and import the graph-generated registry.')

    plugin_panel_path = root / 'tools/plugin_panel.py'
    if plugin_panel_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location('runtime_authority_candidate_panel', plugin_panel_path)
            if spec is None or spec.loader is None:
                raise ImportError('Cannot load candidate plugin_panel.py')
            candidate_panel = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(candidate_panel)
            candidate_panel.load_view_registry(root=root)
            candidate_panel.registered_home_view()
        except Exception as error:
            add('PANEL_VIEW_GRAPH_INVALID', 'library/panel-design/views.json',
                f'Candidate view graph, roles, sources or entrypoint coverage are invalid: {error}')

    forbidden = [
        ('figma-bridge/workspace_control.js', r'const\s+controlAllowed\s*=.*?:\s*\{\s*review\s*:',
         'CONTROL_AUTHORITY_FALLBACK', 'Remove the duplicated task permission fallback; absent policy must deny all tasks.'),
        ('figma-bridge/workspace_host.js', r'const\s+workspaceKinds\s*=\s*new Set\(\s*\[',
         'HOST_KIND_MATRIX_DUPLICATED', 'Derive host task kinds from the authority policy.'),
        ('tools/operation_detail.py', r'ALLOWED_TASK_KINDS\s*=\s*\{',
         'DETAIL_KIND_MATRIX_DUPLICATED', 'Derive detail task kinds from the authority policy.'),
        ('tools/figma_workspace.py', r"(?ms)^def\s+bundle_task_kinds\(\):(?:(?!^def\s).)*?^[ \t]+return\s+\(\s*['\"]",
         'BUNDLE_KIND_MATRIX_DUPLICATED', 'Derive bundle task kinds from the authority policy.'),
    ]
    for relative, expression, code, message in forbidden:
        source = loaded.get(relative)
        if source and re.search(expression, source, re.S):
            add(code, relative, message)

    try:
        findings.extend(native_windows.check(root))
    except (OSError, ValueError, KeyError, TypeError) as error:
        add('NATIVE_WINDOWS_UNVERIFIED', str(native_windows.SOURCE), str(error))

    try:
        findings.extend(component_family_contract.check(root))
    except (OSError, ValueError, KeyError, TypeError) as error:
        add('FAMILY_CONTRACT_UNVERIFIED', str(component_family_contract.DATA), str(error))

    return findings


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = check(args.root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(1 if result else 0)
