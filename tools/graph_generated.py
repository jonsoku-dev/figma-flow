"""Compare committed panel projections with verified builds in owned scratch space."""
from pathlib import Path
import subprocess
import tempfile


ASSET_DIR = Path('figma-bridge/assets')
TOKEN_CSS = Path('panel-ui/src/styles/tokens.css')
DOC_DIR = Path('docs/generated')
POLICY_DOC = DOC_DIR / 'panel-boundaries.md'


def render_policy_doc(contract):
    policy = contract['panelBoundaries']
    network = ', '.join(f'`{name}`' for name in sorted(policy['networkApis']))
    blocked = ', '.join(f'`{name}`' for name in sorted(policy['blockedPackages']))
    lines = [
        '<!-- Generated from tools/maintenance-contract.json -->',
        '# Panel boundaries',
        '',
        'Change [the maintenance contract](../../tools/maintenance-contract.json) to update these boundaries.',
        '',
        f'- The panel bundle starts at `panel-ui/src/{policy["entry"]}`.',
        f'- `{policy["networkOwner"]}` owns network access through {network}.',
        f'- `{policy["bridgeOwner"]}` owns native messages through `{policy["bridgeApi"]}`.',
        f'- Panel modules cannot import Node built-ins, remote URLs or the packages {blocked}.',
        '- Imports outside the panel source directory require an explicit contract binding.',
        '',
        '| Panel module | Allowed external import |',
        '| --- | --- |',
    ]
    for importer, targets in sorted(policy['externalImports'].items()):
        for target in sorted(targets):
            lines.append(f'| `{importer}` | `{target}` |')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def symlinked(root, relative):
    return any((root / part).is_symlink() for part in (relative, *relative.parents))


def write_policy_doc(root, contract):
    root = Path(root).resolve()
    if symlinked(root, POLICY_DOC):
        raise ValueError(f'Remove the symbolic link before regenerating {POLICY_DOC}.')
    output = root / POLICY_DOC
    if output.exists() and not output.is_file():
        raise ValueError(f'Move the existing entry at {POLICY_DOC} before regenerating it.')
    output.parent.mkdir(parents=True, exist_ok=True)
    content = render_policy_doc(contract)
    if not output.is_file() or output.read_bytes() != content:
        output.write_bytes(content)


def managed_files(root, directory):
    path = root / directory
    if symlinked(root, directory) or (path.exists() and not path.is_dir()):
        return {directory}
    return {item.relative_to(root) for item in path.rglob('*') if item.is_symlink() or not item.is_dir()}


def check_content(root, relative, expected):
    path = root / relative
    if symlinked(root, relative) or (path.exists() and not path.is_file()):
        return f'Invalid generated path {relative}; use a regular file.'
    if not path.is_file():
        return f'Missing generated file {relative}.'
    if path.read_bytes() != expected:
        return f'Stale generated file {relative}; regenerate it from its source.'
    return None


def check_generated(root, contract):
    root = Path(root).resolve()
    findings = [f'Unexpected generated file {path}.' for path in sorted(managed_files(root, DOC_DIR) - {POLICY_DOC})]
    findings.append(check_content(root, POLICY_DOC, render_policy_doc(contract)))
    with tempfile.TemporaryDirectory(prefix='figma-flow-panel-build-') as location:
        scratch = Path(location)
        try:
            result = subprocess.run(
                ['node', 'panel-ui/build.mjs', '--output-root', str(scratch)],
                cwd=root, capture_output=True, text=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            findings.append(f'Cannot regenerate panel assets: {error}.')
            return [finding for finding in findings if finding]
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().replace(str(scratch), '<scratch>')
            findings.append(f'Panel asset regeneration failed ({result.returncode}): {detail[:1600]}')
            return [finding for finding in findings if finding]

        expected = managed_files(scratch, ASSET_DIR)
        actual = managed_files(root, ASSET_DIR)
        required = {ASSET_DIR / name for name in contract['panelArtifacts']}
        if not required or any(path.parent != ASSET_DIR for path in required):
            raise ValueError('Declare the required panel artifact filenames in the maintenance contract.')
        findings.extend(f'Build did not produce a required panel artifact {path}.' for path in sorted(required - expected))
        findings.extend(f'Unexpected panel build output {path}; update the artifact contract if this output is intentional.'
                        for path in sorted(expected - required))
        findings.extend(f'Unexpected generated file {path}.' for path in sorted(actual - required))
        for path in sorted((expected & required) | {TOKEN_CSS}):
            if not (scratch / path).is_file() or symlinked(scratch, path):
                findings.append(f'Build did not produce a regular file at {path}.')
                continue
            findings.append(check_content(root, path, (scratch / path).read_bytes()))
    return [finding for finding in findings if finding]
