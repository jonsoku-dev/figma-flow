"""Schema loader, adapter registry, and privacy/label filtering."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .ports import PullAdapter, PushSinkAdapter, SourceAdapter
from .secrets import redact_value

SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'library' / 'metrics' / 'schema.json'
_SAFE_KEY = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Load the canonical metrics SSoT schema from library/metrics/schema.json."""
    target = Path(path) if path is not None else SCHEMA_PATH
    data = json.loads(target.read_text(encoding='utf-8'))
    if data.get('schema') != 'figma-flow-metrics-schema-v1':
        raise ValueError('Unsupported metrics schema file')
    return data


class PrivacyFilter:
    """Enforce metric allowlists, label cardinality bounds, and scope privacy modes."""

    def __init__(self, schema: dict[str, Any], privacy_config: dict[str, Any] | None = None, *, salt: str = ''):
        self.schema = schema
        cfg = privacy_config if isinstance(privacy_config, dict) else {}
        self.mode = str(cfg.get('scope_labels', 'strict'))
        if self.mode not in set(schema['privacyModes']):
            raise ValueError(f'Unsupported privacy mode: {self.mode}')
        self.include_host_tag = bool(cfg.get('include_host_tag', False))
        self.salt = salt
        self.max_label_len = int(schema['limits']['maxLabelLength'])
        self.scope_fields = set(schema['scopeLabelFields'])
        raw_tags = cfg.get('static_tags') or {}
        if not isinstance(raw_tags, dict):
            raise ValueError('static_tags must be an object')
        if len(raw_tags) > int(schema['limits']['maxStaticTags']):
            raise ValueError('static_tags exceeds schema limit')
        self.static_tags: dict[str, str] = {}
        for key, value in raw_tags.items():
            if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
                raise ValueError(f'Invalid static tag name: {key!r}')
            self.static_tags[key] = self._clean_label_value(str(value))

    def _clean_label_value(self, raw: Any) -> str:
        text = redact_value(raw)
        text = re.sub(r'[\r\n\t]+', ' ', text).strip()
        return text[:self.max_label_len]

    def _scope_value(self, key: str, raw: str) -> str | None:
        if self.mode == 'strict':
            return None
        cleaned = self._clean_label_value(raw)
        if not cleaned:
            return None
        if self.mode == 'hashed':
            digest = hashlib.sha256(f'{self.salt}:{key}:{cleaned}'.encode('utf-8')).hexdigest()
            return 'h_' + digest[:12]
        return cleaned

    def filter_labels(self, metric_name: str, labels: dict[str, Any] | None) -> dict[str, str]:
        """Return sanitized labels conforming to schema and active privacy mode."""
        spec = self.schema['metrics'].get(metric_name)
        if not spec:
            raise ValueError(f'Unregistered metric name: {metric_name}')
        allowed = set(spec.get('labels') or [])
        result: dict[str, str] = {}
        for key, value in (labels or {}).items():
            if not isinstance(key, str) or value is None:
                continue
            if key in self.scope_fields:
                scoped = self._scope_value(key, str(value))
                if scoped is not None:
                    result[key] = scoped
                continue
            if key in allowed:
                result[key] = self._clean_label_value(value)
        return result

    def filter_attributes(self, attributes: dict[str, Any] | None) -> dict[str, Any]:
        """Sanitize optional event attributes, stripping or hashing scope fields."""
        if not isinstance(attributes, dict):
            return {}
        clean: dict[str, Any] = {}
        for key, value in attributes.items():
            if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
                continue
            if key in self.scope_fields:
                scoped = self._scope_value(key, '' if value is None else str(value))
                if scoped is not None:
                    clean[key] = scoped
            elif isinstance(value, (bool, int, float)) or value is None:
                clean[key] = value
            elif isinstance(value, str):
                clean[key] = self._clean_label_value(value)
        return clean


class AdapterRegistry:
    """Central registry decoupling core metrics hub from concrete adapters."""

    def __init__(self, schema: dict[str, Any] | None = None):
        self.schema = schema if schema is not None else load_schema()
        self._sources: dict[str, SourceAdapter] = {}
        self._pulls: dict[str, type[PullAdapter]] = {}
        self._sinks: dict[str, type[PushSinkAdapter]] = {}

    def register_source(self, adapter: SourceAdapter) -> None:
        if not adapter.source_id:
            raise ValueError('SourceAdapter requires non-empty source_id')
        self._sources[adapter.source_id] = adapter

    def register_pull(self, adapter_cls: type[PullAdapter]) -> None:
        if not adapter_cls.format_id:
            raise ValueError('PullAdapter requires non-empty format_id')
        self._pulls[adapter_cls.format_id] = adapter_cls

    def register_sink(self, adapter_cls: type[PushSinkAdapter]) -> None:
        if not adapter_cls.sink_type:
            raise ValueError('PushSinkAdapter requires non-empty sink_type')
        self._sinks[adapter_cls.sink_type] = adapter_cls

    def get_source(self, source_id: str) -> SourceAdapter | None:
        return self._sources.get(source_id)

    def create_pull(self, format_id: str) -> PullAdapter:
        cls = self._pulls.get(format_id)
        if cls is None:
            raise ValueError(f'Unsupported pull format adapter: {format_id}')
        return cls()

    def get_sink_class(self, sink_type: str) -> type[PushSinkAdapter]:
        cls = self._sinks.get(sink_type)
        if cls is None:
            raise ValueError(f'Unsupported push sink adapter: {sink_type}')
        return cls

    def create_sink(self, sink_config: dict[str, Any], *, secret_resolver: Any = None) -> PushSinkAdapter:
        sink_type = str(sink_config.get('type', ''))
        cls = self.get_sink_class(sink_type)
        validated = cls.validate_config(sink_config, self.schema)
        return cls(validated, secret_resolver=secret_resolver)

    def has_source(self, source_id: str) -> bool:
        return source_id in self._sources

    def has_pull(self, format_id: str) -> bool:
        return format_id in self._pulls

    def has_sink(self, sink_type: str) -> bool:
        return sink_type in self._sinks

    def describe(self) -> dict[str, Any]:
        """Return machine-readable descriptions of all registered adapters."""
        return {
            'schema': self.schema['schema'],
            'sources': [
                {'id': key, 'description': adapter.description}
                for key, adapter in sorted(self._sources.items())
            ],
            'pull_adapters': [
                {'format': key, 'content_type': cls.content_type, 'description': cls.description}
                for key, cls in sorted(self._pulls.items())
            ],
            'sink_adapters': [
                {'type': key, 'description': cls.description}
                for key, cls in sorted(self._sinks.items())
            ],
        }
