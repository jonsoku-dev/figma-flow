"""Built-in optional Pull and Push Sink adapters."""
from __future__ import annotations

from .pull_json import JsonPullAdapter
from .pull_prometheus import PrometheusPullAdapter
from .sink_http_json import HttpJsonSinkAdapter
from .sink_jsonl import JsonlFileSinkAdapter
from .sink_otlp_http import OtlpHttpSinkAdapter
from .sink_statsd import StatsdUdpSinkAdapter


def register_builtin_adapters(registry) -> None:
    """Register all built-in PullAdapter and PushSinkAdapter implementations."""
    registry.register_pull(PrometheusPullAdapter)
    registry.register_pull(JsonPullAdapter)
    registry.register_sink(HttpJsonSinkAdapter)
    registry.register_sink(OtlpHttpSinkAdapter)
    registry.register_sink(JsonlFileSinkAdapter)
    registry.register_sink(StatsdUdpSinkAdapter)


__all__ = [
    'PrometheusPullAdapter',
    'JsonPullAdapter',
    'HttpJsonSinkAdapter',
    'OtlpHttpSinkAdapter',
    'JsonlFileSinkAdapter',
    'StatsdUdpSinkAdapter',
    'register_builtin_adapters',
]
