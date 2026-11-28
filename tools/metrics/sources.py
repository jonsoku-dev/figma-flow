"""Inbound SourceAdapters and lightweight fail-open CLI ingest client."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import re
from typing import Any

import local_endpoint

from .config import load_effective_config
from .ports import SourceAdapter
from .registry import AdapterRegistry, load_schema
from .types import MetricEvent, MetricSample, now_unix_ns


class OperationsSourceAdapter(SourceAdapter):
    """Normalize control server operation lifecycle and relay outcomes."""

    source_id = 'operations'
    description = 'Control server operations (outcomes, queue/plugin/e2e latency, readback bytes, live plugin health).'

    def normalize(self, payload: dict[str, Any]) -> tuple[list[MetricSample], list[MetricEvent]]:
        ts = now_unix_ns()
        samples: list[MetricSample] = []
        events: list[MetricEvent] = []
        event_kind = payload.get('event')

        if event_kind == 'operation_terminal':
            task_kind = str(payload.get('task_kind') or 'unknown')
            operation = str(payload.get('operation') or 'unknown')
            state = str(payload.get('state') or 'unknown')
            base_labels = {'task_kind': task_kind, 'operation': operation, 'state': state}
            for scope_key in ('file_key', 'page_id', 'task_key'):
                if payload.get(scope_key) is not None:
                    base_labels[scope_key] = str(payload[scope_key])

            samples.append(MetricSample(
                name='figma_flow_operations_total',
                kind='counter',
                value=1.0,
                labels=dict(base_labels),
                source=self.source_id,
                timestamp_ns=ts,
            ))
            events.append(MetricEvent(
                name='figma_flow_operations_total',
                source=self.source_id,
                kind='counter',
                value=1.0,
                labels=dict(base_labels),
                attributes={'route': payload.get('route')},
                timestamp_ns=ts,
            ))

            for field_name, metric_name, include_state in (
                ('queue_ms', 'figma_flow_operation_queue_ms', False),
                ('plugin_ms', 'figma_flow_operation_plugin_ms', False),
                ('e2e_ms', 'figma_flow_operation_e2e_ms', True),
            ):
                val = payload.get(field_name)
                if isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0:
                    labels = dict(base_labels)
                    if not include_state:
                        labels.pop('state', None)
                    samples.append(MetricSample(
                        name=metric_name,
                        kind='histogram',
                        value=float(val),
                        labels=labels,
                        source=self.source_id,
                        timestamp_ns=ts,
                    ))
                    events.append(MetricEvent(
                        name=metric_name,
                        source=self.source_id,
                        kind='histogram',
                        value=float(val),
                        labels=labels,
                        timestamp_ns=ts,
                    ))

            readback_bytes = payload.get('readback_bytes')
            if isinstance(readback_bytes, (int, float)) and not isinstance(readback_bytes, bool) and readback_bytes >= 0:
                rb_labels = {
                    'task_kind': task_kind,
                    'operation': operation,
                    'route': str(payload.get('route') or 'normal'),
                }
                for scope_key in ('file_key', 'page_id', 'task_key'):
                    if payload.get(scope_key) is not None:
                        rb_labels[scope_key] = str(payload[scope_key])
                samples.append(MetricSample(
                    name='figma_flow_readback_bytes',
                    kind='histogram',
                    value=float(readback_bytes),
                    labels=rb_labels,
                    source=self.source_id,
                    timestamp_ns=ts,
                ))
        return samples, events


class LiveChangesSourceAdapter(SourceAdapter):
    """Normalize live Figma Design change stream batches and gaps."""

    source_id = 'live_changes'
    description = 'Live Figma Design page change events and stream gap/unavailable counts.'

    def normalize(self, payload: dict[str, Any]) -> tuple[list[MetricSample], list[MetricEvent]]:
        ts = now_unix_ns()
        samples: list[MetricSample] = []
        events: list[MetricEvent] = []
        scope_extras = {
            k: str(payload[k])
            for k in ('file_key', 'page_id')
            if payload.get(k) is not None
        }
        for row in payload.get('events') or []:
            if not isinstance(row, dict):
                continue
            labels = {
                'change_type': str(row.get('type') or 'unknown'),
                'origin': str(row.get('origin') or 'unknown'),
                **scope_extras,
            }
            samples.append(MetricSample(
                name='figma_flow_live_changes_total',
                kind='counter',
                value=1.0,
                labels=labels,
                source=self.source_id,
                timestamp_ns=ts,
            ))
            events.append(MetricEvent(
                name='figma_flow_live_changes_total',
                source=self.source_id,
                kind='counter',
                value=1.0,
                labels=labels,
                timestamp_ns=ts,
            ))
        gap_reason = payload.get('gap_reason')
        if gap_reason:
            labels = {'reason': str(gap_reason), **scope_extras}
            samples.append(MetricSample(
                name='figma_flow_live_change_gaps_total',
                kind='counter',
                value=1.0,
                labels=labels,
                source=self.source_id,
                timestamp_ns=ts,
            ))
            events.append(MetricEvent(
                name='figma_flow_live_change_gaps_total',
                source=self.source_id,
                kind='counter',
                value=1.0,
                labels=labels,
                timestamp_ns=ts,
            ))
        return samples, events


class WorkspaceSourceAdapter(SourceAdapter):
    """Normalize workspace task prepare and catalogue count events."""

    source_id = 'workspace'
    description = 'Workspace task preparation outcomes and prepared task catalogue gauges.'

    def normalize(self, payload: dict[str, Any]) -> tuple[list[MetricSample], list[MetricEvent]]:
        ts = now_unix_ns()
        samples: list[MetricSample] = []
        events: list[MetricEvent] = []
        kind = payload.get('kind')
        status = payload.get('status')
        if kind and status:
            labels = {'kind': str(kind), 'status': str(status)}
            if payload.get('task_key') is not None:
                labels['task_key'] = str(payload['task_key'])
            samples.append(MetricSample(
                name='figma_flow_tasks_prepared_total',
                kind='counter',
                value=1.0,
                labels=labels,
                source=self.source_id,
                timestamp_ns=ts,
            ))
            events.append(MetricEvent(
                name='figma_flow_tasks_prepared_total',
                source=self.source_id,
                kind='counter',
                value=1.0,
                labels=labels,
                timestamp_ns=ts,
            ))
        counts = payload.get('task_counts_by_kind')
        if isinstance(counts, dict):
            for k, count in counts.items():
                if isinstance(count, (int, float)) and not isinstance(count, bool):
                    samples.append(MetricSample(
                        name='figma_flow_workspace_tasks_count',
                        kind='gauge',
                        value=float(count),
                        labels={'kind': str(k)},
                        source=self.source_id,
                        timestamp_ns=ts,
                    ))
        return samples, events


class QualitySourceAdapter(SourceAdapter):
    """Normalize pre-Figma design quality check evaluations."""

    source_id = 'quality'
    description = 'Pre-Figma design quality check pass/fail and error/warning counts.'

    def normalize(self, payload: dict[str, Any]) -> tuple[list[MetricSample], list[MetricEvent]]:
        ts = now_unix_ns()
        samples: list[MetricSample] = []
        events: list[MetricEvent] = []
        passed = 'true' if payload.get('passed') else 'false'
        strict = 'true' if payload.get('strict') else 'false'
        labels = {'passed': passed, 'strict': strict}
        samples.append(MetricSample(
            name='figma_flow_quality_checks_total',
            kind='counter',
            value=1.0,
            labels=labels,
            source=self.source_id,
            timestamp_ns=ts,
        ))
        events.append(MetricEvent(
            name='figma_flow_quality_checks_total',
            source=self.source_id,
            kind='counter',
            value=1.0,
            labels=labels,
            attributes={
                'errors': int(payload.get('errors') or 0),
                'warnings': int(payload.get('warnings') or 0),
            },
            timestamp_ns=ts,
        ))
        for severity, key in (('error', 'errors'), ('warning', 'warnings')):
            count = payload.get(key)
            if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0:
                samples.append(MetricSample(
                    name='figma_flow_quality_issues_total',
                    kind='counter',
                    value=float(count),
                    labels={'severity': severity},
                    source=self.source_id,
                    timestamp_ns=ts,
                ))
        return samples, events


class BenchmarkSourceAdapter(SourceAdapter):
    """Normalize native_read_benchmark sample measurements."""

    source_id = 'benchmark'
    description = 'Fresh native-read benchmark durations and sample outcomes.'

    def normalize(self, payload: dict[str, Any]) -> tuple[list[MetricSample], list[MetricEvent]]:
        ts = now_unix_ns()
        samples: list[MetricSample] = []
        events: list[MetricEvent] = []
        for row in payload.get('samples') or []:
            if not isinstance(row, dict):
                continue
            ms = row.get('end_to_end_ms')
            if isinstance(ms, (int, float)) and not isinstance(ms, bool) and ms >= 0:
                labels = {
                    'workload': str(row.get('workload') or 'unknown'),
                    'state': str(row.get('state') or 'unknown'),
                }
                samples.append(MetricSample(
                    name='figma_flow_native_read_ms',
                    kind='histogram',
                    value=float(ms),
                    labels=labels,
                    source=self.source_id,
                    timestamp_ns=ts,
                ))
                events.append(MetricEvent(
                    name='figma_flow_native_read_ms',
                    source=self.source_id,
                    kind='histogram',
                    value=float(ms),
                    labels=labels,
                    timestamp_ns=ts,
                ))
        return samples, events


def register_builtin_sources(registry: AdapterRegistry) -> None:
    """Register all built-in SourceAdapters into an AdapterRegistry."""
    registry.register_source(OperationsSourceAdapter())
    registry.register_source(LiveChangesSourceAdapter())
    registry.register_source(WorkspaceSourceAdapter())
    registry.register_source(QualitySourceAdapter())
    registry.register_source(BenchmarkSourceAdapter())


def _read_control_endpoint(workspace_root: Path) -> tuple[int, str] | None:
    return local_endpoint.read_endpoint(workspace_root)


def emit_cli_source_event(
    workspace_root: str | Path | None,
    source_id: str,
    payload: dict[str, Any],
    *,
    timeout: float | None = None,
) -> bool:
    """Best-effort, fail-open CLI ingest to the running serve hub.

    Returns immediately when metrics or the given source are disabled.
    Never raises or blocks normal CLI execution.
    """
    if workspace_root is None:
        return False
    try:
        root = Path(workspace_root).expanduser().absolute()
        schema = load_schema()
        cfg, _ = load_effective_config(root, schema=schema)
        if not cfg.get('enabled') or not cfg.get('sources', {}).get(source_id):
            return False
        endpoint = _read_control_endpoint(root)
        if endpoint is None:
            return False
        port, token = endpoint
        body = json.dumps({'source': source_id, 'payload': payload}, ensure_ascii=True, allow_nan=False).encode('utf-8')
        if len(body) > int(schema['limits']['maxIngestBodyBytes']):
            return False
        reply = local_endpoint.request(port, token, 'POST', '/metrics/ingest', body, limit=1024,
                                       timeout=timeout, timeout_kind='metricsIngest')
        return reply.status == 200
    except Exception:
        return False
