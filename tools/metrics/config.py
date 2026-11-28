"""PC-local configuration loader, hierarchy merger, and atomic 0600 writer."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlparse

import local_endpoint
import private_io

from .registry import AdapterRegistry, load_schema
from .secrets import redact_value

_SINK_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
_TAG_KEY = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
_LOCALHOST_HOSTS = local_endpoint.LOOPBACK_HOSTS


def user_config_path() -> Path:
    """Return the per-PC user metrics config path respecting XDG_CONFIG_HOME."""
    xdg = os.environ.get('XDG_CONFIG_HOME', '').strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / '.config'
    return base.absolute() / 'figma-flow' / 'metrics.json'


def workspace_config_path(workspace_root: str | Path) -> Path:
    """Return the workspace-scoped metrics config path."""
    return Path(workspace_root).expanduser().absolute() / 'metrics.json'


def default_config(schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the default disabled (opt-in) configuration template."""
    schema_doc = schema if schema is not None else load_schema()
    return {
        'schema': schema_doc['configSchema'],
        'enabled': False,
        'privacy': {
            'scope_labels': 'strict',
            'include_host_tag': False,
            'static_tags': {},
        },
        'sources': {
            source_id: (source_id == 'operations')
            for source_id in schema_doc['sources']
        },
        'pull': {
            'enabled': False,
            'auth': 'control-token',
            'formats': list(schema_doc['pullFormats']),
        },
        'sinks': [],
    }


def _read_private_json(path: Path, limit: int) -> dict[str, Any]:
    path = Path(path).expanduser().absolute()
    if os.name == 'posix':
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            raise ValueError('Metrics config must be a bounded regular file without symlinks')
        stat = path.stat()
        if stat.st_mode & 0o077 or stat.st_uid != os.getuid():
            raise ValueError('Metrics config requires owner-only permissions (0600)')
    elif path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Metrics config must be a bounded regular file without symlinks')
    data = json.loads(path.read_bytes().decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Metrics config root must be a JSON object')
    return data


def _atomic_write_private(path: Path, data: dict[str, Any]) -> None:
    private_io.atomic_write_json(path, data)


def validate_http_url(url: str, *, allow_insecure_http: bool = False) -> str:
    """Enforce https:// for remote targets while allowing localhost http://."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError('HTTP sink requires a non-empty url')
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or not parsed.hostname:
        raise ValueError('HTTP sink url must use http:// or https:// with a valid host')
    if parsed.username or parsed.password:
        raise ValueError('Do not embed credentials in sink URL; use headers with ${ENV_VAR} or file:/path')
    host = parsed.hostname.lower()
    if parsed.scheme == 'http' and host not in _LOCALHOST_HOSTS and not allow_insecure_http:
        raise ValueError('Remote HTTP sink requires https:// unless allow_insecure_http is explicitly true')
    return url


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key == 'sinks' and isinstance(value, list):
            by_id: dict[str, dict[str, Any]] = {
                str(row['id']): copy.deepcopy(row)
                for row in merged.get('sinks', [])
                if isinstance(row, dict) and row.get('id')
            }
            order = [
                str(row['id'])
                for row in merged.get('sinks', [])
                if isinstance(row, dict) and row.get('id')
            ]
            for row in value:
                if not isinstance(row, dict) or not row.get('id'):
                    raise ValueError('Each sink entry must be an object with a valid id')
                sid = str(row['id'])
                if sid not in by_id:
                    order.append(sid)
                by_id[sid] = copy.deepcopy(row)
            merged['sinks'] = [by_id[sid] for sid in order]
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def validate_config(
    raw: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
    registry: AdapterRegistry | None = None,
) -> dict[str, Any]:
    """Validate and normalize a metrics configuration dictionary."""
    schema_doc = schema if schema is not None else load_schema()
    limits = schema_doc['limits']
    if not isinstance(raw, dict):
        raise ValueError('Metrics config must be a JSON object')
    allowed_top = {'schema', 'enabled', 'privacy', 'sources', 'pull', 'sinks'}
    extra_top = set(raw) - allowed_top
    if extra_top:
        raise ValueError(f'Unknown metrics config keys: {", ".join(sorted(extra_top))}')
    if raw.get('schema') != schema_doc['configSchema']:
        raise ValueError(f'Metrics config schema must be {schema_doc["configSchema"]}')
    enabled = raw.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('Metrics config "enabled" must be a boolean')

    base = default_config(schema_doc)
    merged = _merge_dicts(base, raw)

    # Validate privacy
    privacy = merged['privacy']
    if not isinstance(privacy, dict) or set(privacy) - {'scope_labels', 'include_host_tag', 'static_tags'}:
        raise ValueError('Invalid privacy section in metrics config')
    if privacy.get('scope_labels') not in set(schema_doc['privacyModes']):
        raise ValueError('Invalid privacy.scope_labels mode')
    if not isinstance(privacy.get('include_host_tag', False), bool):
        raise ValueError('privacy.include_host_tag must be a boolean')
    tags = privacy.get('static_tags')
    if not isinstance(tags, dict) or len(tags) > int(limits['maxStaticTags']):
        raise ValueError('Invalid privacy.static_tags object')
    clean_tags: dict[str, str] = {}
    for k, v in tags.items():
        if not isinstance(k, str) or not _TAG_KEY.fullmatch(k) or not isinstance(v, (str, int, float, bool)):
            raise ValueError(f'Invalid static tag {k!r}')
        clean_tags[k] = str(v)[:int(limits['maxLabelLength'])]
    privacy['static_tags'] = clean_tags

    # Validate sources
    sources = merged['sources']
    allowed_sources = set(schema_doc['sources'])
    if not isinstance(sources, dict) or set(sources) - allowed_sources:
        raise ValueError('Unknown source in metrics config sources')
    for src in allowed_sources:
        val = sources.get(src, False)
        if not isinstance(val, bool):
            raise ValueError(f'Source toggle {src!r} must be a boolean')
        sources[src] = val

    # Validate pull
    pull = merged['pull']
    if not isinstance(pull, dict) or set(pull) - {'enabled', 'auth', 'formats', 'bearer_secret'}:
        raise ValueError('Invalid pull section in metrics config')
    if not isinstance(pull.get('enabled', False), bool):
        raise ValueError('pull.enabled must be a boolean')
    auth = pull.get('auth', 'control-token')
    if auth not in set(schema_doc['pullAuthModes']):
        raise ValueError(f'Invalid pull.auth mode: {auth!r}')
    if auth == 'bearer-secret' and (not isinstance(pull.get('bearer_secret'), str) or not pull['bearer_secret']):
        raise ValueError('pull.auth="bearer-secret" requires pull.bearer_secret')
    formats = pull.get('formats', list(schema_doc['pullFormats']))
    if (not isinstance(formats, list) or not formats
            or any(not isinstance(fmt, str) or fmt not in set(schema_doc['pullFormats']) for fmt in formats)
            or len(set(formats)) != len(formats)):
        raise ValueError('Invalid pull.formats list')

    # Validate sinks
    sinks = merged['sinks']
    if not isinstance(sinks, list) or len(sinks) > int(limits['maxSinks']):
        raise ValueError('Invalid or oversized sinks list')
    seen_ids: set[str] = set()
    normalized_sinks: list[dict[str, Any]] = []
    known_sink_types = set(schema_doc['sinkTypes'])
    for row in sinks:
        if not isinstance(row, dict):
            raise ValueError('Sink entry must be an object')
        sid = row.get('id')
        if not isinstance(sid, str) or not _SINK_ID.fullmatch(sid):
            raise ValueError(f'Invalid sink id: {sid!r}')
        if sid in seen_ids:
            raise ValueError(f'Duplicate sink id: {sid}')
        seen_ids.add(sid)
        stype = row.get('type')
        if not isinstance(stype, str) or (stype not in known_sink_types and (registry is None or not registry.has_sink(stype))):
            raise ValueError(f'Unsupported sink type: {stype!r}')
        if 'enabled' in row and not isinstance(row['enabled'], bool):
            raise ValueError(f'Sink {sid} enabled must be boolean')
        include_sources = row.get('include_sources')
        if include_sources is not None:
            if (not isinstance(include_sources, list)
                    or any(not isinstance(item, str) or item not in allowed_sources for item in include_sources)):
                raise ValueError(f'Sink {sid} include_sources contains unknown source')
        exclude_metrics = row.get('exclude_metrics')
        if exclude_metrics is not None:
            if not isinstance(exclude_metrics, list) or any(not isinstance(item, str) or not item for item in exclude_metrics):
                raise ValueError(f'Sink {sid} exclude_metrics must be a list of metric names')
        defaults = schema_doc['defaults']
        batch_size = row.get('batch_size', defaults['sinkBatchSize'])
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= int(limits['maxBatchSize']):
            raise ValueError(f'Sink {sid} batch_size out of range')
        flush_sec = row.get('flush_interval_sec', defaults['sinkFlushIntervalSec'])
        if (isinstance(flush_sec, bool) or not isinstance(flush_sec, (int, float))
                or not int(limits['minFlushIntervalSec']) <= flush_sec <= int(limits['maxFlushIntervalSec'])):
            raise ValueError(f'Sink {sid} flush_interval_sec out of range')
        timeout_sec = row.get('timeout_sec', defaults['sinkTimeoutSec'])
        if isinstance(timeout_sec, bool) or not isinstance(timeout_sec, (int, float)) or not 0.1 <= timeout_sec <= int(limits['maxTimeoutSec']):
            raise ValueError(f'Sink {sid} timeout_sec out of range')
        max_retries = row.get('max_retries', defaults['sinkMaxRetries'])
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 0 <= max_retries <= int(limits['maxRetries']):
            raise ValueError(f'Sink {sid} max_retries out of range')
        if registry is not None:
            sink_cls = registry.get_sink_class(stype)
            normalized_sinks.append(sink_cls.validate_config(row, schema_doc))
        else:
            normalized_sinks.append(copy.deepcopy(row))
    merged['sinks'] = normalized_sinks
    return merged


def load_effective_config(
    workspace_root: str | Path | None = None,
    *,
    schema: dict[str, Any] | None = None,
    registry: AdapterRegistry | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load optional global + workspace configs, returning (effective_config, provenance)."""
    schema_doc = schema if schema is not None else load_schema()
    limit = int(schema_doc['limits']['maxConfigBytes'])
    effective = default_config(schema_doc)
    loaded_files: list[str] = []
    errors: list[dict[str, str]] = []

    candidates: list[tuple[str, Path]] = [('global', user_config_path())]
    if workspace_root is not None:
        candidates.append(('workspace', workspace_config_path(workspace_root)))

    for layer, path in candidates:
        if not path.exists() and not path.is_symlink():
            continue
        try:
            raw = _read_private_json(path, limit)
            validated = validate_config(raw, schema=schema_doc, registry=registry)
            # Merge only explicitly present keys from the raw layer onto effective
            partial = {k: v for k, v in validated.items() if k in raw}
            partial['schema'] = validated['schema']
            effective = validate_config(_merge_dicts(effective, partial), schema=schema_doc, registry=registry)
            loaded_files.append(f'{layer}:{redact_value(path)}')
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({'layer': layer, 'path': redact_value(path), 'error': redact_value(exc)})

    provenance = {
        'loaded_layers': loaded_files,
        'errors': errors,
        'has_workspace_config': workspace_root is not None and workspace_config_path(workspace_root).exists(),
        'has_global_config': user_config_path().exists(),
    }
    return effective, provenance


def save_config(
    path: str | Path,
    config: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
    registry: AdapterRegistry | None = None,
) -> dict[str, Any]:
    """Validate and atomically write a 0600 private metrics config file."""
    validated = validate_config(config, schema=schema, registry=registry)
    _atomic_write_private(Path(path), validated)
    return validated


def config_fingerprint(workspace_root: str | Path | None = None) -> tuple[Any, ...]:
    """Return a lightweight stat fingerprint for global + workspace config files."""
    items: list[Any] = []
    paths = [user_config_path()]
    if workspace_root is not None:
        paths.append(workspace_config_path(workspace_root))
    for path in paths:
        try:
            if path.is_symlink():
                items.append(('symlink', str(path)))
            elif path.is_file():
                st = path.stat()
                items.append(('file', st.st_mtime_ns, st.st_size, st.st_mode & 0o777))
            else:
                items.append(('missing',))
        except OSError:
            items.append(('error',))
    return tuple(items)
