"""Canonical immutable data types for the optional Figma Flow metrics subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any


def now_unix_ns() -> int:
    """Return current UTC epoch time in nanoseconds."""
    return time.time_ns()


def now_iso(unix_ns: int | None = None) -> str:
    """Format an epoch nanosecond timestamp as RFC3339/ISO-8601 UTC string."""
    seconds = (now_unix_ns() if unix_ns is None else unix_ns) / 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


@dataclass(frozen=True)
class MetricSample:
    """Normalized single metric observation produced by a source or core hub."""

    name: str
    kind: str  # 'counter' | 'gauge' | 'histogram'
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    source: str = 'operations'
    timestamp_ns: int = field(default_factory=now_unix_ns)


@dataclass(frozen=True)
class MetricEvent:
    """Normalized structured event sent to event-capable push sinks."""

    name: str
    source: str
    kind: str  # 'counter' | 'gauge' | 'histogram' | 'event'
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp_ns: int = field(default_factory=now_unix_ns)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            'name': self.name,
            'source': self.source,
            'kind': self.kind,
            'value': self.value,
            'labels': dict(self.labels),
            'attributes': dict(self.attributes),
            'timestamp_unix': round(self.timestamp_ns / 1_000_000_000, 6),
            'timestamp_iso': now_iso(self.timestamp_ns),
        }


@dataclass(frozen=True)
class SinkHealth:
    """Current health and delivery counters for one configured push sink."""

    sink_id: str
    sink_type: str
    enabled: bool
    queue_depth: int = 0
    sent_total: int = 0
    failed_total: int = 0
    dropped_total: int = 0
    consecutive_failures: int = 0
    circuit_open: bool = False
    last_error: str | None = None
    last_success_iso: str | None = None
    last_attempt_iso: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable health summary."""
        return {
            'id': self.sink_id,
            'type': self.sink_type,
            'enabled': self.enabled,
            'queue_depth': self.queue_depth,
            'sent_total': self.sent_total,
            'failed_total': self.failed_total,
            'dropped_total': self.dropped_total,
            'consecutive_failures': self.consecutive_failures,
            'circuit_open': self.circuit_open,
            'last_error': self.last_error,
            'last_success_iso': self.last_success_iso,
            'last_attempt_iso': self.last_attempt_iso,
        }


@dataclass(frozen=True)
class MetricSnapshot:
    """Point-in-time read-only snapshot rendered by PullAdapters and PushSinkAdapters."""

    schema: str
    generated_at_iso: str
    generated_at_ns: int
    privacy_mode: str
    sources: dict[str, bool]
    counters: list[dict[str, Any]]
    gauges: list[dict[str, Any]]
    histograms: list[dict[str, Any]]
    sink_health: list[dict[str, Any]]
    static_tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    """Outcome of a single PushSinkAdapter delivery attempt."""

    ok: bool
    sent_count: int = 0
    status_code: int | None = None
    error: str | None = None
    latency_ms: float | None = None
    retryable: bool = True
