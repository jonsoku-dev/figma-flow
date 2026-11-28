"""Explicit PC-local registration and read-only discovery of Figma Flow workspaces.

Stores only non-secret metadata (workspace path, numeric plugin_id, control port,
timestamps) in $XDG_CONFIG_HOME/figma-flow/workspaces.json (0600 owner-only) so
new Codex sessions can reuse an already-configured workspace without repeating setup.
"""
from __future__ import annotations

from datetime import datetime, timezone
import schema_ids
from graph_document import decode_json
import os
from pathlib import Path
import re
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
        data = decode_json(path.read_bytes())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _atomic_write_private(path: Path, data: dict[str, Any]) -> None:
    private_io.atomic_write_json(path, data)


def _read_registry(path: Path) -> dict[str, Any]:
    # Absence allows creation. A broken link, invalid JSON or a permission failure does not.
    try:
        path.lstat()
    except FileNotFoundError:
        return _empty_registry()
    data = _read_private_json(path)
    if not data or data.get('schema') != SCHEMA or not isinstance(data.get('workspaces'), list):
        raise ValueError('Invalid workspace registry')
    if len(data['workspaces']) > 32:
        raise ValueError('Invalid workspace registry size')
    paths = set()
    for row in data['workspaces']:
        if not isinstance(row, dict):
            raise ValueError('Invalid workspace registry entry')
        name = row.get('path')
        if not isinstance(name, str) or '\x00' in name or not Path(name).is_absolute() or name in paths:
            raise ValueError('Invalid workspace registry path')
        if (not isinstance(row.get('plugin_id'), str) or not _PLUGIN_ID_RE.fullmatch(row['plugin_id'])
                or row.get('control_port') is not None and not local_endpoint.valid_port(row['control_port'])):
            raise ValueError('Invalid workspace registry metadata')
        if any(key in row and not isinstance(row[key], str) for key in ('registered_at', 'updated_at')):
            raise ValueError('Invalid workspace registry timestamp')
        paths.add(name)
    default = data.get('default_workspace')
    if default is not None and not isinstance(default, str):
        raise ValueError('Invalid default workspace')
    return data


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Discovery remains fail-open; registration must use the strict read under its lock."""
    try:
        return _read_registry(path if path is not None else registry_path())
    except (OSError, ValueError):
        return _empty_registry()


def inspect_workspace_dir(ws_path: Path) -> dict[str, Any]:
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
    set_default: bool = False,
) -> bool:
    """Explicitly remember a workspace, selecting it as default only on request."""
    try:
        if not isinstance(set_default, bool):
            return False
        ws_path = Path(workspace_root).expanduser().resolve()
        info = inspect_workspace_dir(ws_path)
        pid = plugin_id or info.get('plugin_id')
        if not isinstance(pid, str) or not _PLUGIN_ID_RE.fullmatch(pid):
            return False
        port = control_port if control_port is not None else info.get('control_port')
        if port is not None and not local_endpoint.valid_port(port):
            port = None

        path = registry_path()
        with private_io.locked_update(path):
            reg = _read_registry(path)
            target = str(ws_path)
            existing = next((row for row in reg['workspaces'] if row['path'] == target), None)
            change_default = set_default and reg.get('default_workspace') != target
            if existing and existing['plugin_id'] == pid and existing.get('control_port') == port and not change_default:
                return True
            now = _now_iso()
            entry = {**(existing or {}), 'path': target, 'plugin_id': pid, 'control_port': port,
                     'registered_at': (existing or {}).get('registered_at') or now, 'updated_at': now}
            rows = [entry, *(row for row in reg['workspaces'] if row['path'] != target)]
            if set_default:
                reg['default_workspace'] = target
            if len(rows) > 32:
                # Keep the selected default even when it is the oldest row.
                last = next(i for i in reversed(range(1, len(rows))) if rows[i]['path'] != reg.get('default_workspace'))
                rows.pop(last)
            reg['workspaces'] = rows
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
        info = inspect_workspace_dir(Path(raw_path))
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


def resolve_workspace(explicit_path: str | Path | None = None, *,
                      discovered: list[dict[str, Any]] | None = None) -> Path | None:
    """Resolve explicit workspace path or fall back to the default/sole PC-registered workspace."""
    if explicit_path is not None:
        return Path(explicit_path).expanduser().absolute()
    if discovered is None:
        discovered = discover_workspaces()
    if not discovered:
        return None
    for row in discovered:
        if row.get('is_default'):
            return Path(row['path'])
    return Path(discovered[0]['path']) if len(discovered) == 1 else None
