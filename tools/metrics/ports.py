"""Ports (interfaces) for the optional Figma Flow metrics subsystem."""
from __future__ import annotations

from typing import Any

from .types import MetricEvent, MetricSample, MetricSnapshot, SendResult


class MetricRecorder:
    """Inbound port used by Figma Flow tools without knowing any collector."""

    def is_enabled(self) -> bool:
        """Return True if metrics recording is active."""
        return False

    def source_enabled(self, source_id: str) -> bool:
        """Return True if a specific inbound source adapter is enabled."""
        return False

    def inc(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None, *, source: str = 'operations') -> None:
        """Increment a counter metric."""

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None, *, source: str = 'operations') -> None:
        """Set a gauge metric value."""

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None, *, source: str = 'operations') -> None:
        """Record an observation into a histogram metric."""

    def emit_event(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        *,
        source: str = 'operations',
        kind: str = 'event',
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Emit a discrete event to push sinks without mutating pull counters."""

    def record_source(self, source_id: str, payload: dict[str, Any]) -> int:
        """Normalize and record a domain payload via a registered SourceAdapter."""
        return 0


class NullRecorder(MetricRecorder):
    """Default zero-overhead No-op recorder when metrics are disabled."""


class SourceAdapter:
    """Port converting domain-specific payloads into canonical samples and events."""

    source_id: str = ''
    description: str = ''

    def normalize(self, payload: dict[str, Any]) -> tuple[list[MetricSample], list[MetricEvent]]:
        """Convert a domain payload dict into canonical MetricSamples and MetricEvents."""
        raise NotImplementedError


class PullAdapter:
    """Outbound port rendering a MetricSnapshot for pull/scrape HTTP endpoints."""

    format_id: str = ''
    content_type: str = 'text/plain; charset=utf-8'
    description: str = ''

    def render(self, snapshot: MetricSnapshot, *, schema: dict[str, Any] | None = None) -> bytes:
        """Render the snapshot into wire bytes."""
        raise NotImplementedError


class PushSinkAdapter:
    """Outbound port delivering batched metric events/snapshots to an external sink."""

    sink_type: str = ''
    description: str = ''

    def __init__(self, sink_config: dict[str, Any], *, secret_resolver: Any = None):
        self.sink_config = dict(sink_config)
        self.sink_id = str(sink_config.get('id', ''))
        self.secret_resolver = secret_resolver

    @classmethod
    def validate_config(cls, sink_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize sink-specific configuration."""
        return dict(sink_config)

    def send(self, items: list[dict[str, Any]], snapshot: MetricSnapshot | None = None) -> SendResult:
        """Deliver a batch of normalized items and/or current snapshot."""
        raise NotImplementedError

    def healthcheck(self) -> dict[str, Any]:
        """Return safe configuration diagnostics without leaking secrets."""
        return {'sink_id': self.sink_id, 'type': self.sink_type}

    def close(self) -> None:
        """Release any open resources."""
