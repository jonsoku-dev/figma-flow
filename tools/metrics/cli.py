"""Headless JSON CLI subcommands for configuring and diagnosing PC-local metrics."""
from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

import local_endpoint
import private_io

from .config import (
    default_config,
    load_effective_config,
    save_config,
    user_config_path,
    workspace_config_path,
)
from .hub import MetricsHub, default_registry
from .registry import load_schema
from .secrets import redact_value

MAX_WATCH_COUNT = 1000


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {'true', '1', 'yes', 'on'}:
        return True
    if lowered in {'false', '0', 'no', 'off'}:
        return False
    raise argparse.ArgumentTypeError(f'Expected true or false, got {value!r}')


def _parse_kv(value: str) -> tuple[str, str]:
    key, sep, val = value.partition('=')
    if not sep or not key.strip():
        raise argparse.ArgumentTypeError(f'Expected KEY=VALUE, got {value!r}')
    return key.strip(), val


def _target_path(args: argparse.Namespace) -> Path:
    if getattr(args, 'use_global', False):
        return user_config_path()
    if getattr(args, 'workspace', None) is None:
        raise ValueError('Specify --workspace PATH or --global')
    return workspace_config_path(args.workspace)


def _load_or_init_target(path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        if path.is_symlink():
            raise ValueError('Refusing symlink metrics config file')
        raw = json.loads(path.read_bytes().decode('utf-8'))
        if not isinstance(raw, dict):
            raise ValueError('Existing metrics config is not a JSON object')
        return raw
    return default_config(schema)


_REPLY_LIMIT = local_endpoint.CHANGE_REPLY_LIMIT


def _read_control(workspace: Path) -> tuple[int, str] | None:
    return local_endpoint.read_endpoint(workspace)


def _http_get_local(port: int, path: str, token: str, *, timeout_kind: str = 'request') -> tuple[int, bytes] | None:
    try:
        reply = local_endpoint.request(port, token, 'GET', path, limit=_REPLY_LIMIT, timeout_kind=timeout_kind)
    except (OSError, http.client.HTTPException):
        return None
    return reply.status, reply.body[:_REPLY_LIMIT]


def _http_post_local(port: int, path: str, token: str, payload: dict[str, Any], *,
                     timeout_kind: str = 'bulkRequest') -> tuple[int, bytes] | None:
    try:
        reply = local_endpoint.post_json(port, token, path, payload, limit=_REPLY_LIMIT, timeout_kind=timeout_kind)
    except (OSError, http.client.HTTPException, ValueError):
        return None
    return reply.status, reply.body[:_REPLY_LIMIT]


def register_metrics_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Attach `metrics` subcommands to figma_control.py CLI parser."""
    metrics_parser = subparsers.add_parser('metrics', help='Configure and inspect optional PC-local metrics')
    actions = metrics_parser.add_subparsers(dest='metrics_action', required=True)
    schema = load_schema()

    def add_target_flags(p: argparse.ArgumentParser, *, allow_global: bool = True) -> None:
        p.add_argument('--workspace', type=Path)
        if allow_global:
            p.add_argument('--global', dest='use_global', action='store_true', help='Target PC-wide user metrics config')

    actions.add_parser('list-adapters', help='List registered source, pull, and push sink adapters')

    p_init = actions.add_parser('init', help='Create an optional 0600 metrics config template (disabled by default)')
    add_target_flags(p_init)
    p_init.add_argument('--force', action='store_true')

    p_en = actions.add_parser('enable', help='Enable metrics collection in target config')
    add_target_flags(p_en)

    p_dis = actions.add_parser('disable', help='Disable metrics collection in target config')
    add_target_flags(p_dis)

    p_src = actions.add_parser('set-source', help='Enable or disable a specific source adapter')
    add_target_flags(p_src)
    p_src.add_argument('--source', required=True, choices=schema['sources'])
    p_src.add_argument('--enabled', required=True, type=_parse_bool)

    p_pull = actions.add_parser('set-pull', help='Configure local Pull endpoints (/metrics, /metrics/json)')
    add_target_flags(p_pull)
    p_pull.add_argument('--enabled', type=_parse_bool)
    p_pull.add_argument('--auth', choices=schema['pullAuthModes'])
    p_pull.add_argument('--bearer-secret')
    p_pull.add_argument('--format', action='append', dest='formats', choices=schema['pullFormats'])

    p_priv = actions.add_parser('set-privacy', help='Configure label privacy mode and static tags')
    add_target_flags(p_priv)
    p_priv.add_argument('--scope-labels', choices=schema['privacyModes'])
    p_priv.add_argument('--include-host-tag', type=_parse_bool)
    p_priv.add_argument('--tag', action='append', dest='tags', type=_parse_kv)
    p_priv.add_argument('--clear-tags', action='store_true')

    p_add = actions.add_parser('add-sink', help='Add or update a push sink adapter')
    add_target_flags(p_add)
    p_add.add_argument('--id', required=True)
    p_add.add_argument('--type', required=True, dest='sink_type', choices=schema['sinkTypes'])
    p_add.add_argument('--url')
    p_add.add_argument('--path')
    p_add.add_argument('--method', choices=('POST', 'PUT'))
    p_add.add_argument('--header', action='append', dest='headers', type=_parse_kv)
    p_add.add_argument('--mode', choices=('events', 'snapshot', 'events_and_snapshot'))
    p_add.add_argument('--batch-size', type=int)
    p_add.add_argument('--flush-interval', type=float)
    p_add.add_argument('--timeout', type=float)
    p_add.add_argument('--max-retries', type=int)
    p_add.add_argument('--include-source', action='append', dest='include_sources', choices=schema['sources'])
    p_add.add_argument('--exclude-metric', action='append', dest='exclude_metrics')
    p_add.add_argument('--mapping-json')
    p_add.add_argument('--allow-insecure-http', action='store_true')
    p_add.add_argument('--max-bytes', type=int)
    p_add.add_argument('--max-files', type=int)
    p_add.add_argument('--host')
    p_add.add_argument('--port', type=int)
    p_add.add_argument('--prefix')
    p_add.add_argument('--dogstatsd-tags', type=_parse_bool)
    p_add.add_argument('--enabled', type=_parse_bool, default=True)

    p_rem = actions.add_parser('remove-sink', help='Remove a push sink by id')
    add_target_flags(p_rem)
    p_rem.add_argument('--id', required=True)

    p_test = actions.add_parser('test', help='Test delivery (or dry-run) against a configured sink')
    p_test.add_argument('--workspace', type=Path, required=True)
    p_test.add_argument('--sink', required=True)
    p_test.add_argument('--dry-run', action='store_true')

    p_snap = actions.add_parser('snapshot', help='Render current metrics snapshot (live serve or offline)')
    p_snap.add_argument('--workspace', type=Path, required=True)
    p_snap.add_argument('--format', default='json', choices=schema['pullFormats'])

    p_doc = actions.add_parser('doctor', help='Run headless metrics diagnostics')
    p_doc.add_argument('--workspace', type=Path, required=True)

    p_flush = actions.add_parser('flush', help='Flush buffered metrics from the running serve process to enabled sinks')
    p_flush.add_argument('--workspace', type=Path, required=True)

    p_watch = actions.add_parser('watch', help='Stream headless readiness and plugin health as NDJSON without Computer Use')
    p_watch.add_argument('--workspace', type=Path, required=True)
    p_watch.add_argument('--interval', type=float, default=2.0)
    p_watch.add_argument('--count', type=int, default=1)
    p_watch.add_argument('--until-ready', action='store_true')


_CONFIG_ACTIONS = {'init', 'enable', 'disable', 'set-source', 'set-pull', 'set-privacy', 'add-sink', 'remove-sink'}


def _update_config(args, path, registry):
    schema = registry.schema
    action = args.metrics_action
    if action == 'init':
        if path.exists() and not args.force:
            raise ValueError('Metrics config already exists; pass --force to overwrite')
        saved = save_config(path, default_config(schema), schema=schema, registry=registry)
        return 0, json.dumps({'path': redact_value(path), 'config': saved}, ensure_ascii=True) + '\n'

    cfg = _load_or_init_target(path, schema)
    if action in {'enable', 'disable'}:
        cfg['enabled'] = (action == 'enable')
        saved = save_config(path, cfg, schema=schema, registry=registry)
        return 0, json.dumps({'path': redact_value(path), 'enabled': saved['enabled']}, ensure_ascii=True) + '\n'

    if action == 'set-source':
        sources = dict(cfg.get('sources') or {})
        sources[args.source] = args.enabled
        cfg['sources'] = sources
        saved = save_config(path, cfg, schema=schema, registry=registry)
        return 0, json.dumps({'path': redact_value(path), 'sources': saved['sources']}, ensure_ascii=True) + '\n'

    if action == 'set-pull':
        pull = dict(cfg.get('pull') or {})
        if args.enabled is not None:
            pull['enabled'] = args.enabled
        if args.auth is not None:
            pull['auth'] = args.auth
        if args.bearer_secret is not None:
            pull['bearer_secret'] = args.bearer_secret
        if args.formats is not None:
            pull['formats'] = list(args.formats)
        cfg['pull'] = pull
        saved = save_config(path, cfg, schema=schema, registry=registry)
        return 0, json.dumps({'path': redact_value(path), 'pull': saved['pull']}, ensure_ascii=True) + '\n'

    if action == 'set-privacy':
        privacy = dict(cfg.get('privacy') or {})
        if args.scope_labels is not None:
            privacy['scope_labels'] = args.scope_labels
        if args.include_host_tag is not None:
            privacy['include_host_tag'] = args.include_host_tag
        tags = {} if args.clear_tags else dict(privacy.get('static_tags') or {})
        for key, value in (args.tags or []):
            tags[key] = value
        privacy['static_tags'] = tags
        cfg['privacy'] = privacy
        saved = save_config(path, cfg, schema=schema, registry=registry)
        return 0, json.dumps({'path': redact_value(path), 'privacy': saved['privacy']}, ensure_ascii=True) + '\n'

    if action == 'add-sink':
        sink: dict[str, Any] = {'id': args.id, 'type': args.sink_type, 'enabled': args.enabled}
        if args.url is not None:
            sink['url'] = args.url
        if args.path is not None:
            sink['path'] = args.path
        if args.method is not None:
            sink['method'] = args.method
        if args.headers:
            sink['headers'] = {k: v for k, v in args.headers}
        if args.mode is not None:
            sink['mode'] = args.mode
        if args.batch_size is not None:
            sink['batch_size'] = args.batch_size
        if args.flush_interval is not None:
            sink['flush_interval_sec'] = args.flush_interval
        if args.timeout is not None:
            sink['timeout_sec'] = args.timeout
        if args.max_retries is not None:
            sink['max_retries'] = args.max_retries
        if args.include_sources is not None:
            sink['include_sources'] = list(args.include_sources)
        if args.exclude_metrics is not None:
            sink['exclude_metrics'] = list(args.exclude_metrics)
        if args.mapping_json is not None:
            sink['payload_mapping'] = json.loads(args.mapping_json)
        if args.allow_insecure_http:
            sink['allow_insecure_http'] = True
        if args.max_bytes is not None:
            sink['max_bytes'] = args.max_bytes
        if args.max_files is not None:
            sink['max_files'] = args.max_files
        if args.host is not None:
            sink['host'] = args.host
        if args.port is not None:
            sink['port'] = args.port
        if args.prefix is not None:
            sink['prefix'] = args.prefix
        if args.dogstatsd_tags is not None:
            sink['dogstatsd_tags'] = args.dogstatsd_tags
        sinks = [row for row in (cfg.get('sinks') or []) if isinstance(row, dict) and row.get('id') != args.id]
        sinks.append(sink)
        cfg['sinks'] = sinks
        saved = save_config(path, cfg, schema=schema, registry=registry)
        stored = next(row for row in saved['sinks'] if row['id'] == args.id)
        return 0, json.dumps({'path': redact_value(path), 'sink': stored}, ensure_ascii=True) + '\n'

    if action == 'remove-sink':
        before = list(cfg.get('sinks') or [])
        after = [row for row in before if not (isinstance(row, dict) and row.get('id') == args.id)]
        if len(before) == len(after):
            raise ValueError(f'Unknown sink id: {args.id}')
        cfg['sinks'] = after
        save_config(path, cfg, schema=schema, registry=registry)
        return 0, json.dumps({'path': redact_value(path), 'removed': args.id}, ensure_ascii=True) + '\n'


def run_metrics_cli(args: argparse.Namespace, *, live_state_fn: Any = None) -> tuple[int, str]:
    """Execute a metrics CLI subcommand and return (exit_code, stdout_text)."""
    registry = default_registry()
    action = args.metrics_action

    if action == 'list-adapters':
        return 0, json.dumps(registry.describe(), ensure_ascii=True, indent=2) + '\n'

    if action in _CONFIG_ACTIONS:
        path = _target_path(args)
        with private_io.locked_update(path):
            return _update_config(args, path, registry)

    if action == 'test':
        hub = MetricsHub(args.workspace, registry=registry, start_workers=False)
        try:
            result = hub.test_sink(args.sink, dry_run=args.dry_run)
        finally:
            hub.close()
        return (0 if result.get('ok') else 2), json.dumps(result, ensure_ascii=True) + '\n'

    if action == 'snapshot':
        ctrl = _read_control(args.workspace)
        if ctrl is not None:
            port, token = ctrl
            endpoint = '/metrics/json' if args.format == 'json' else '/metrics'
            resp = _http_get_local(port, endpoint, token)
            if resp is not None and resp[0] == 200:
                return 0, resp[1].decode('utf-8')
        hub = MetricsHub(args.workspace, registry=registry, start_workers=False)
        try:
            _ctype, body = hub.render_pull(args.format)
            return 0, body.decode('utf-8')
        finally:
            hub.close()

    if action == 'doctor':
        ctrl = _read_control(args.workspace)
        if ctrl is not None:
            port, token = ctrl
            resp = _http_get_local(port, '/metrics/doctor', token)
            if resp is not None and resp[0] == 200:
                return 0, resp[1].decode('utf-8')
        hub = MetricsHub(args.workspace, registry=registry, start_workers=False)
        try:
            live_state = live_state_fn(args.workspace) if live_state_fn else None
            report = hub.doctor_report(live_state=live_state, server_online=False)
            return 0, json.dumps(report, ensure_ascii=True, indent=2) + '\n'
        finally:
            hub.close()

    if action == 'flush':
        ctrl = _read_control(args.workspace)
        if ctrl is not None:
            port, token = ctrl
            resp = _http_post_local(port, '/metrics/flush', token, {})
            if resp is not None:
                code_num, body = resp
                if code_num == 200:
                    return 0, body.decode('utf-8')
                return 2, body.decode('utf-8')
        return 2, json.dumps({
            'flushed': False,
            'server_online': False,
            'error': 'Control server unavailable',
        }, ensure_ascii=True) + '\n'

    if action == 'watch':
        if isinstance(args.interval, bool) or not 0.05 <= args.interval <= 300:
            raise ValueError('Watch interval must be between 0.05 and 300 seconds')
        if isinstance(args.count, bool) or not 1 <= args.count <= MAX_WATCH_COUNT:
            raise ValueError(f'Watch count must be between 1 and {MAX_WATCH_COUNT}')
        lines: list[str] = []
        ready_reached = False
        for sample_idx in range(1, args.count + 1):
            report = None
            ctrl = _read_control(args.workspace)
            if ctrl is not None:
                port, token = ctrl
                resp = _http_get_local(port, '/metrics/doctor', token)
                if resp is not None and resp[0] == 200:
                    report = json.loads(resp[1].decode('utf-8'))
            if report is None:
                hub = MetricsHub(args.workspace, registry=registry, start_workers=False)
                try:
                    live_state = live_state_fn(args.workspace) if live_state_fn else None
                    report = hub.doctor_report(live_state=live_state, server_online=False)
                finally:
                    hub.close()
            live = report.get('live_state') or {}
            server_online = bool(report.get('server_online'))
            plugin_online = bool(live.get('plugin_online'))
            runtime_current = bool(live.get('plugin_runtime_current'))
            uncertain_ops = int(live.get('uncertain_operations') or 0)
            ready = bool(server_online and plugin_online and runtime_current and uncertain_ops == 0)
            sink_errors = [
                row['id']
                for row in (report.get('sinks') or [])
                if isinstance(row.get('runtime'), dict)
                and (row['runtime'].get('circuit_open') or row['runtime'].get('last_error'))
            ]
            row = {
                'sample': sample_idx,
                'timestamp': report.get('generated_at'),
                'server_online': server_online,
                'plugin_online': plugin_online,
                'plugin_last_seen_age_seconds': live.get('plugin_last_seen_age_seconds', -1.0),
                'runtime_status': live.get('runtime_status', 'offline'),
                'plugin_runtime_current': runtime_current,
                'active_operation_state': live.get('active_operation_state', 'idle'),
                'uncertain_operations': uncertain_ops,
                'profile_needs_setup': bool(live.get('profile_needs_setup')),
                'ready': ready,
                'sink_errors': sink_errors,
            }
            line = json.dumps(row, ensure_ascii=True)
            lines.append(line)
            if args.until_ready and ready:
                ready_reached = True
                break
            if sample_idx < args.count:
                time.sleep(args.interval)
        exit_code = 0 if (not args.until_ready or ready_reached) else 2
        return exit_code, '\n'.join(lines) + '\n'

    raise ValueError(f'Unsupported metrics action: {action}')
