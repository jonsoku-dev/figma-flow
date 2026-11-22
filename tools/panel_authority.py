"""Fail closed when the shipped relay palette escapes its design graph."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


_COLOR_DECLARATION = re.compile(
    r'(?:^|[;{])\s*(?:color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?(?:-color)?|box-shadow)\s*:\s*([^;}]+)',
    re.IGNORECASE | re.MULTILINE,
)
_COLOR_LITERAL = re.compile(r'#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?)\s*\(', re.IGNORECASE)
_VARIABLE = re.compile(r'var\(\s*(--[a-z0-9-]+)', re.IGNORECASE)
_LOCAL_VARIABLE = re.compile(r'(?:^|[;{])\s*(--[a-z0-9-]+)\s*:', re.IGNORECASE | re.MULTILINE)
_DIMENSION_LITERAL = re.compile(r'(?<![\w-])-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|em|rem|vw|vh|%)\b', re.IGNORECASE)


def check(root: Path) -> list[dict[str, str]]:
    """Return graph projection and relay literal findings for a repository root."""
    root = Path(root)
    findings: list[dict[str, str]] = []
    relay_path = root / 'panel-ui/src/styles/relay.css'
    try:
        relay = relay_path.read_text(encoding='utf-8')
    except OSError as error:
        return [{'code': 'PANEL_RELAY_CSS_MISSING', 'path': 'panel-ui/src/styles/relay.css',
                 'message': f'Cannot read relay stylesheet: {error}'}]

    graph_path = root / 'library/panel-design/tokens.json'
    try:
        graph = json.loads(graph_path.read_text(encoding='utf-8'))
        token_ids = [token['id'] for token in graph['tokens']]
        token_names = {f'--{token_id}' for token_id in token_ids}
        token_names.update(f"--{token['id']}-dark" for token in graph['tokens'])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        return [{'code': 'PANEL_TOKEN_GRAPH_UNAVAILABLE', 'path': 'library/panel-design/tokens.json',
                 'message': f'Cannot read panel token graph: {error}'}]

    for variable in _VARIABLE.findall(relay):
        if variable not in token_names:
            findings.append({
                'code': 'PANEL_RELAY_TOKEN_UNOWNED',
                'path': 'panel-ui/src/styles/relay.css',
                'message': f'{variable} is not declared by the panel design graph.',
            })
    if _LOCAL_VARIABLE.search(relay):
        findings.append({
            'code': 'PANEL_RELAY_LOCAL_TOKEN_OVERRIDE',
            'path': 'panel-ui/src/styles/relay.css',
            'message': 'Relay token values must be declared only by the generated panel token stylesheet.',
        })
    if _DIMENSION_LITERAL.search(relay):
        findings.append({
            'code': 'PANEL_RELAY_DIMENSION_LITERAL',
            'path': 'panel-ui/src/styles/relay.css',
            'message': 'Relay dimensions and typography values must come from the panel design graph.',
        })
    if relay.count('__PANEL_TOKEN_relay-mobile-breakpoint__') != 1:
        findings.append({
            'code': 'PANEL_RELAY_BREAKPOINT_MARKER_INVALID',
            'path': 'panel-ui/src/styles/relay.css',
            'message': 'The graph-owned mobile breakpoint marker must occur exactly once.',
        })

    for match in _COLOR_LITERAL.finditer(relay):
        findings.append({
            'code': 'PANEL_RELAY_COLOR_LITERAL',
            'path': 'panel-ui/src/styles/relay.css',
            'message': 'Relay palette values must come from library/panel-design/tokens.json.',
        })
        break
    for match in _COLOR_DECLARATION.finditer(relay):
        value = match.group(1).strip().lower()
        if not any(allowed in value for allowed in ('var(', 'currentcolor', 'inherit', 'initial', 'unset', 'revert', 'none')) and value != '0':
            findings.append({
                'code': 'PANEL_RELAY_UNOWNED_COLOR',
                'path': 'panel-ui/src/styles/relay.css',
                'message': 'Color-related declarations must reference a graph token or currentColor.',
            })
            break

    generator = root / 'panel-ui/build-tokens.mjs'
    try:
        result = subprocess.run(
            ['node', str(generator), '--check'], cwd=root, capture_output=True,
            text=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return findings + [{'code': 'PANEL_TOKEN_CHECK_UNAVAILABLE', 'path': 'panel-ui/build-tokens.mjs',
                            'message': f'Cannot verify graph-backed panel tokens: {error}'}]
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        findings.append({
            'code': 'PANEL_TOKEN_PROJECTION_INVALID',
            'path': 'library/panel-design/tokens.json',
            'message': detail[-1] if detail else 'Panel token graph or generated CSS check failed.',
        })
    return findings
