"""Optional, adapter-first metrics and headless observability package for Figma Flow."""
from __future__ import annotations

from .config import (
    config_fingerprint,
    default_config,
    load_effective_config,
    save_config,
    user_config_path,
    validate_config,
    workspace_config_path,
)
from .hub import MetricsHub, default_registry
from .ports import MetricRecorder, NullRecorder, PullAdapter, PushSinkAdapter, SourceAdapter
from .registry import AdapterRegistry, PrivacyFilter, load_schema
from .secrets import SecretResolver, redact_value
from .sources import emit_cli_source_event
from .types import MetricEvent, MetricSample, MetricSnapshot, SendResult, SinkHealth

__all__ = [
    'AdapterRegistry',
    'MetricEvent',
    'MetricRecorder',
    'MetricSample',
    'MetricSnapshot',
    'MetricsHub',
    'NullRecorder',
    'PrivacyFilter',
    'PullAdapter',
    'PushSinkAdapter',
    'SecretResolver',
    'SendResult',
    'SinkHealth',
    'SourceAdapter',
    'config_fingerprint',
    'default_config',
    'default_registry',
    'emit_cli_source_event',
    'load_effective_config',
    'load_schema',
    'redact_value',
    'save_config',
    'user_config_path',
    'validate_config',
    'workspace_config_path',
]
