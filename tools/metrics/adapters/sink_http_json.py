"""Generic HTTP/HTTPS JSON push sink adapter with declarative payload mapping."""
from __future__ import annotations

import json
import re
import time
from typing import Any
import urllib.error
import urllib.request

import runtime_limits

from ..config import validate_http_url
from ..ports import PushSinkAdapter
from ..registry import load_schema
from ..secrets import SecretResolver, redact_value
from ..types import MetricSnapshot, SendResult, now_iso

DEFAULT_TIMEOUT_SEC = float(load_schema()['defaults']['sinkTimeoutSec'])

_PLACEHOLDER = re.compile(r'^\{\{([a-z_]+)\}\}$')
_INLINE_PLACEHOLDER = re.compile(r'\{\{([a-z_]+)\}\}')
_VALID_MODES = {'events', 'snapshot', 'events_and_snapshot'}
_VALID_METHODS = {'POST', 'PUT'}


def _render_mapping_value(template: Any, context: dict[str, Any]) -> Any:
    if isinstance(template, str):
        exact = _PLACEHOLDER.fullmatch(template)
        if exact:
            return context.get(exact.group(1))
        return _INLINE_PLACEHOLDER.sub(lambda m: str(context.get(m.group(1), '')), template)
    if isinstance(template, dict):
        return {str(k): _render_mapping_value(v, context) for k, v in template.items()}
    if isinstance(template, list):
        return [_render_mapping_value(v, context) for v in template]
    return template


def map_event_item(item: dict[str, Any], static_tags: dict[str, str], mapping: dict[str, Any] | None) -> dict[str, Any]:
    """Transform a normalized event item according to optional payload_mapping."""
    if not mapping:
        return dict(item)
    fields = mapping.get('fields')
    if not isinstance(fields, dict) or not fields:
        return dict(item)
    merged_labels = {**static_tags, **(item.get('labels') or {})}
    context = {
        'name': item.get('name'),
        'source': item.get('source'),
        'kind': item.get('kind'),
        'value': item.get('value'),
        'labels': merged_labels,
        'attributes': item.get('attributes') or {},
        'static_tags': dict(static_tags),
        'timestamp_iso': item.get('timestamp_iso'),
        'timestamp_unix': item.get('timestamp_unix'),
    }
    return {str(k): _render_mapping_value(v, context) for k, v in fields.items()}


class HttpJsonSinkAdapter(PushSinkAdapter):
    """Push batched metric events and/or snapshots to any external REST API."""

    sink_type = 'http-json'
    description = 'Configurable HTTP/HTTPS JSON push adapter for custom or internal metrics APIs.'

    def __init__(self, sink_config: dict[str, Any], *, secret_resolver: SecretResolver | None = None):
        super().__init__(sink_config, secret_resolver=secret_resolver or SecretResolver())

    @classmethod
    def validate_config(cls, sink_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        cfg = dict(sink_config)
        allow_http = bool(cfg.get('allow_insecure_http', False))
        if not isinstance(cfg.get('allow_insecure_http', False), bool):
            raise ValueError('allow_insecure_http must be a boolean')
        cfg['url'] = validate_http_url(str(cfg.get('url', '')), allow_insecure_http=allow_http)
        method = str(cfg.get('method', 'POST')).upper()
        if method not in _VALID_METHODS:
            raise ValueError(f'Unsupported HTTP sink method: {method}')
        cfg['method'] = method
        mode = str(cfg.get('mode', 'events_and_snapshot'))
        if mode not in _VALID_MODES:
            raise ValueError(f'Unsupported HTTP sink mode: {mode}')
        cfg['mode'] = mode
        headers = cfg.get('headers') or {}
        if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
            raise ValueError('HTTP sink headers must be a string-to-string object')
        cfg['headers'] = dict(headers)
        mapping = cfg.get('payload_mapping')
        if mapping is not None:
            if not isinstance(mapping, dict) or set(mapping) - {'envelope', 'fields'}:
                raise ValueError('HTTP sink payload_mapping only admits envelope and fields')
            if 'envelope' in mapping and (not isinstance(mapping['envelope'], str) or not mapping['envelope']):
                raise ValueError('HTTP sink payload_mapping.envelope must be a non-empty string')
            if 'fields' in mapping and not isinstance(mapping['fields'], dict):
                raise ValueError('HTTP sink payload_mapping.fields must be an object')
        return cfg

    def build_payload(self, items: list[dict[str, Any]], snapshot: MetricSnapshot | None) -> dict[str, Any]:
        mode = self.sink_config.get('mode', 'events_and_snapshot')
        mapping = self.sink_config.get('payload_mapping')
        static_tags = dict(snapshot.static_tags) if snapshot else {}
        mapped_items = [map_event_item(item, static_tags, mapping) for item in items]

        if mapping and mapping.get('envelope'):
            payload: dict[str, Any] = {mapping['envelope']: mapped_items}
            if mode == 'events_and_snapshot' and snapshot is not None:
                payload['snapshot'] = {
                    'generated_at': snapshot.generated_at_iso,
                    'counters': snapshot.counters,
                    'gauges': snapshot.gauges,
                    'histograms': snapshot.histograms,
                }
            return payload

        body: dict[str, Any] = {
            'schema': 'figma-flow-metrics-ingest-v1',
            'sent_at': now_iso(),
            'static_tags': static_tags,
        }
        if mode in {'events', 'events_and_snapshot'}:
            body['items'] = mapped_items
        if mode in {'snapshot', 'events_and_snapshot'} and snapshot is not None:
            body['snapshot'] = {
                'generated_at': snapshot.generated_at_iso,
                'counters': snapshot.counters,
                'gauges': snapshot.gauges,
                'histograms': snapshot.histograms,
            }
        return body

    def send(self, items: list[dict[str, Any]], snapshot: MetricSnapshot | None = None) -> SendResult:
        started = time.monotonic()
        try:
            headers = self.secret_resolver.resolve_headers(self.sink_config.get('headers'))
        except ValueError as exc:
            return SendResult(
                ok=False,
                sent_count=0,
                error=redact_value(exc),
                latency_ms=(time.monotonic() - started) * 1000,
                retryable=False,
            )
        headers.setdefault('Content-Type', 'application/json')
        body = json.dumps(self.build_payload(items, snapshot), ensure_ascii=True, allow_nan=False).encode('utf-8')
        request = urllib.request.Request(
            self.sink_config['url'],
            data=body,
            headers=headers,
            method=self.sink_config.get('method', 'POST'),
        )
        timeout = float(self.sink_config.get('timeout_sec', DEFAULT_TIMEOUT_SEC))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, 'status', 200))
                response.read(runtime_limits.NETWORK['maxErrorResponseBytes'])
                return SendResult(
                    ok=200 <= status < 300,
                    sent_count=len(items),
                    status_code=status,
                    error=None if 200 <= status < 300 else f'HTTP {status}',
                    latency_ms=(time.monotonic() - started) * 1000,
                    retryable=status >= 500 or status == 429,
                )
        except urllib.error.HTTPError as exc:
            return SendResult(
                ok=False,
                sent_count=0,
                status_code=int(exc.code),
                error=f'HTTP {exc.code}',
                latency_ms=(time.monotonic() - started) * 1000,
                retryable=exc.code >= 500 or exc.code == 429,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return SendResult(
                ok=False,
                sent_count=0,
                error=redact_value(exc),
                latency_ms=(time.monotonic() - started) * 1000,
                retryable=True,
            )

    def healthcheck(self) -> dict[str, Any]:
        return {
            'sink_id': self.sink_id,
            'type': self.sink_type,
            'url': redact_value(self.sink_config.get('url', '')),
            'method': self.sink_config.get('method', 'POST'),
            'mode': self.sink_config.get('mode', 'events_and_snapshot'),
        }
