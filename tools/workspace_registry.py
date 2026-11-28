"""PC-local, fail-open registry of initialized Figma Flow workspaces.

Stores only non-secret metadata (workspace path, numeric plugin_id, control port,
timestamps) in $XDG_CONFIG_HOME/figma-flow/workspaces.json (0600 owner-only) so
new Codex sessions can reuse an already-configured workspace without repeating setup.
"""
from __future__ import annotations

from datetime import datetime, timezone
import schema_ids
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

import local_endpoint
import private_io

SCHEMA = 'figma-flow-workspace-registry-v1'
_PLUGIN_ID_RE = re.compile(r'^[0-9]+$')


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def registry_path() -> Path:
    """Return the per-PC workspace registry path respecting XDG_CONFIG_HOME."""
    xdg = os.environ.get('XDG_CONFIG_HOME', '').strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / '.config'
    return base.absolute() / 'figma-flow' / 'workspaces.json'


def _should_skip_auto_registration(workspace_root: Path) -> bool:
    """Avoid polluting the user's real ~/.config when tests run without XDG_CONFIG_HOME."""
    if os.environ.get('XDG_CONFIG_HOME', '').strip():
        return False
    try:
        resolved = workspace_root.resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        return resolved.is_relative_to(temp_root)
    except OSError:
        return False


def _empty_registry() -> dict[str, Any]:
    return {'schema': SCHEMA, 'default_workspace': None, 'workspaces': []}


def _read_private_json(path: Path, *, limit: int = 262144) -> dict[str, Any] | None:
    try:
        path = Path(path).expanduser().absolute()
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        if os.name == 'posix':
            st = path.stat()
            if st.st_mode & 0o077 or st.st_uid != os.getuid():
                return None
        data = json.loads(path.read_bytes().decode('utf-8'))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _atomic_write_private(path: Path, data: dict[str, Any]) -> None:
    private_io.atomic_write_json(path, data)


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Read the PC workspace registry safely; return an empty registry if missing/invalid."""
    data = _read_private_json(path if path is not None else registry_path())
    if not data or data.get('schema') != SCHEMA or not isinstance(data.get('workspaces'), list):
        return _empty_registry()
    rows = []
    for row in data['workspaces']:
        if isinstance(row, dict) and isinstance(row.get('path'), str) and row['path']:
            rows.append(dict(row))
    default_ws = data.get('default_workspace') if isinstance(data.get('default_workspace'), str) else None
    return {'schema': SCHEMA, 'default_workspace': default_ws, 'workspaces': rows}


def _inspect_workspace_dir(ws_path: Path) -> dict[str, Any]:
    """Strictly read-only inspection of one workspace directory."""
    try:
        resolved = ws_path.expanduser().resolve()
    except OSError:
        return {'path': str(ws_path), 'valid': False}
    if not resolved.is_dir() or resolved.is_symlink():
        return {'path': str(resolved), 'valid': False}
    if os.name == 'posix':
        try:
            st = resolved.stat()
            if st.st_mode & 0o077 or st.st_uid != os.getuid():
                return {'path': str(resolved), 'valid': False}
        except OSError:
            return {'path': str(resolved), 'valid': False}
    identity = _read_private_json(resolved / 'identity.json', limit=16384)
    manifest_ok = (resolved / 'manifest.json').is_file() and not (resolved / 'manifest.json').is_symlink()
    plugin_id = identity.get('plugin_id') if isinstance(identity, dict) else None
    if not isinstance(plugin_id, str) or not _PLUGIN_ID_RE.fullmatch(plugin_id) or not manifest_ok:
        return {'path': str(resolved), 'valid': False}
    ctrl = _read_private_json(resolved / 'control.json', limit=4096)
    port = None
    if isinstance(ctrl, dict) and ctrl.get('schema') == schema_ids.ID['control']:
        raw_port = ctrl.get('port')
        if local_endpoint.valid_port(raw_port):
            port = raw_port
    return {
        'path': str(resolved),
        'valid': True,
        'plugin_id': plugin_id,
        'control_port': port,
    }


def register_workspace(
    workspace_root: str | Path,
    *,
    plugin_id: str | None = None,
    control_port: int | None = None,
    set_default: bool = True,
) -> bool:
    """Fail-open registration of a configured workspace in the PC-local registry."""
    try:
        ws_path = Path(workspace_root).expanduser().resolve()
        if _should_skip_auto_registration(ws_path):
            return False
        info = _inspect_workspace_dir(ws_path)
        pid = plugin_id or info.get('plugin_id')
        if not isinstance(pid, str) or not _PLUGIN_ID_RE.fullmatch(pid):
            return False
        port = control_port if control_port is not None else info.get('control_port')
        if port is not None and not local_endpoint.valid_port(port):
            port = None

        path = registry_path()
        with private_io.locked_update(path):
            reg = load_registry(path)
            now = _now_iso()
            target_str = str(ws_path)
            existing = None
            others: list[dict[str, Any]] = []
            for row in reg['workspaces']:
                if row.get('path') == target_str:
                    existing = row
                else:
                    others.append(row)

            entry = {
                'path': target_str,
                'plugin_id': pid,
                'control_port': port,
                'registered_at': (existing or {}).get('registered_at') or now,
                'updated_at': now,
            }
            reg['workspaces'] = [entry, *others[:31]]
            if set_default or not reg.get('default_workspace'):
                reg['default_workspace'] = target_str
            _atomic_write_private(path, reg)
        return True
    except Exception:
        return False


def discover_workspaces() -> list[dict[str, Any]]:
    """Return currently valid registered workspaces on this PC without mutating disk."""
    reg = load_registry()
    default_ws = reg.get('default_workspace')
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reg['workspaces']:
        raw_path = row.get('path')
        if not isinstance(raw_path, str) or raw_path in seen:
            continue
        seen.add(raw_path)
        info = _inspect_workspace_dir(Path(raw_path))
        if not info.get('valid'):
            continue
        found.append({
            'path': info['path'],
            'plugin_id': info['plugin_id'],
            'control_port': info['control_port'],
            'is_default': info['path'] == default_ws,
            'registered_at': row.get('registered_at'),
            'updated_at': row.get('updated_at'),
            'valid': True,
        })
    return found


def resolve_workspace(explicit_path: str | Path | None = None) -> Path | None:
    """Resolve explicit workspace path or fall back to the default/sole PC-registered workspace."""
    if explicit_path is not None:
        return Path(explicit_path).expanduser().absolute()
    discovered = discover_workspaces()
    if not discovered:
        return None
    for row in discovered:
        if row.get('is_default'):
            return Path(row['path'])
    if len(discovered) == 1:
        return Path(discovered[0]['path'])
    return Path(discovered[0]['path'])
