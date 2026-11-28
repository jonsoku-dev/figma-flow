"""Prometheus / OpenMetrics text exposition PullAdapter."""
from __future__ import annotations

from typing import Any

from ..ports import PullAdapter
from ..types import MetricSnapshot


def _escape_label(value: str) -> str:
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ''
    pairs = [f'{key}="{_escape_label(str(labels[key]))}"' for key in sorted(labels)]
    return '{' + ','.join(pairs) + '}'


def _format_number(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f'{float(value):.6g}'


class PrometheusPullAdapter(PullAdapter):
    """Render MetricSnapshot in Prometheus text exposition format (0.0.4)."""

    format_id = 'prometheus'
    content_type = 'text/plain; version=0.0.4; charset=utf-8'
    description = 'Prometheus / OpenMetrics text scrape endpoint (GET /metrics).'

    def render(self, snapshot: MetricSnapshot, *, schema: dict[str, Any] | None = None) -> bytes:
        metrics_meta = (schema or {}).get('metrics', {})
        lines: list[str] = []
        declared: set[str] = set()

        def emit_header(name: str, kind: str) -> None:
            if name in declared:
                return
            declared.add(name)
            meta = metrics_meta.get(name, {})
            help_text = str(meta.get('help', name)).replace('\\', '\\\\').replace('\n', ' ')
            lines.append(f'# HELP {name} {help_text}')
            lines.append(f'# TYPE {name} {kind}')

        for row in snapshot.counters:
            name = row['name']
            emit_header(name, 'counter')
            merged = {**snapshot.static_tags, **(row.get('labels') or {})}
            lines.append(f"{name}{_format_labels(merged)} {_format_number(row['value'])}")

        for row in snapshot.gauges:
            name = row['name']
            emit_header(name, 'gauge')
            merged = {**snapshot.static_tags, **(row.get('labels') or {})}
            lines.append(f"{name}{_format_labels(merged)} {_format_number(row['value'])}")

        for row in snapshot.histograms:
            name = row['name']
            emit_header(name, 'histogram')
            merged = {**snapshot.static_tags, **(row.get('labels') or {})}
            for bound, count in row.get('buckets', []):
                le = '+Inf' if bound == '+Inf' else _format_number(bound)
                bucket_labels = {**merged, 'le': le}
                lines.append(f'{name}_bucket{_format_labels(bucket_labels)} {int(count)}')
            lines.append(f"{name}_sum{_format_labels(merged)} {_format_number(row['sum'])}")
            lines.append(f"{name}_count{_format_labels(merged)} {int(row['count'])}")

        if not lines:
            lines.append('# No Figma Flow metrics recorded yet.')
        return ('\n'.join(lines) + '\n').encode('utf-8')
