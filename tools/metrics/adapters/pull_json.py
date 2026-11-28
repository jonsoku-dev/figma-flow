"""Structured JSON snapshot PullAdapter."""
from __future__ import annotations

import json
from typing import Any

from ..ports import PullAdapter
from ..types import MetricSnapshot


class JsonPullAdapter(PullAdapter):
    """Render MetricSnapshot as canonical figma-flow-metrics-snapshot-v1 JSON."""

    format_id = 'json'
    content_type = 'application/json; charset=utf-8'
    description = 'Structured JSON metrics snapshot endpoint (GET /metrics/json).'

    def render(self, snapshot: MetricSnapshot, *, schema: dict[str, Any] | None = None) -> bytes:
        payload = {
            'schema': snapshot.schema,
            'generated_at': snapshot.generated_at_iso,
            'privacy_mode': snapshot.privacy_mode,
            'sources': dict(snapshot.sources),
            'static_tags': dict(snapshot.static_tags),
            'counters': list(snapshot.counters),
            'gauges': list(snapshot.gauges),
            'histograms': list(snapshot.histograms),
            'sink_health': list(snapshot.sink_health),
        }
        return (json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('utf-8')
