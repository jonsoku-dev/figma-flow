"""OpenTelemetry OTLP/HTTP JSON push sink adapter (Python stdlib only)."""
from __future__ import annotations

import json
import time
from typing import Any
import urllib.error
import urllib.request

import runtime_limits

from ..config import validate_http_url
from ..ports import PushSinkAdapter
from ..registry import load_schema
from ..secrets import SecretResolver, redact_value
from ..types import MetricSnapshot, SendResult, now_unix_ns

DEFAULT_TIMEOUT_SEC = float(load_schema()['defaults']['sinkTimeoutSec'])


def _kv_attributes(labels: dict[str, str]) -> list[dict[str, Any]]:
    return [{'key': str(k), 'value': {'stringValue': str(v)}} for k, v in sorted(labels.items())]


def _number_point(value: float | int, labels: dict[str, str], time_ns: int) -> dict[str, Any]:
    point: dict[str, Any] = {
        'attributes': _kv_attributes(labels),
        'timeUnixNano': str(time_ns),
    }
    if isinstance(value, int) and not isinstance(value, bool):
        point['asInt'] = str(value)
    elif float(value).is_integer():
        point['asInt'] = str(int(value))
    else:
        point['asDouble'] = float(value)
    return point


def build_otlp_payload(
    snapshot: MetricSnapshot | None,
    items: list[dict[str, Any]],
    *,
    service_name: str = 'figma-flow',
    service_version: str = '1.0.0',
) -> dict[str, Any]:
    """Encode MetricSnapshot (or fallback event batch) into OTLP ExportMetricsServiceRequest JSON."""
    time_ns = snapshot.generated_at_ns if snapshot else now_unix_ns()
    static_tags = dict(snapshot.static_tags) if snapshot else {}
    resource_attrs = _kv_attributes({'service.name': service_name, 'service.version': service_version, **static_tags})

    grouped: dict[str, dict[str, Any]] = {}

    if snapshot is not None:
        for row in snapshot.counters:
            name = row['name']
            entry = grouped.setdefault(name, {'name': name, 'sum': {'dataPoints': [], 'aggregationTemporality': 2, 'isMonotonic': True}})
            entry['sum']['dataPoints'].append(_number_point(row['value'], row.get('labels') or {}, time_ns))

        for row in snapshot.gauges:
            name = row['name']
            entry = grouped.setdefault(name, {'name': name, 'gauge': {'dataPoints': []}})
            entry['gauge']['dataPoints'].append(_number_point(row['value'], row.get('labels') or {}, time_ns))

        for row in snapshot.histograms:
            name = row['name']
            entry = grouped.setdefault(name, {'name': name, 'histogram': {'dataPoints': [], 'aggregationTemporality': 2}})
            bounds: list[float] = []
            counts: list[str] = []
            prev = 0
            for bound, cumulative in row.get('buckets', []):
                cumulative_int = int(cumulative)
                delta = max(0, cumulative_int - prev)
                prev = cumulative_int
                counts.append(str(delta))
                if bound != '+Inf':
                    bounds.append(float(bound))
            entry['histogram']['dataPoints'].append({
                'attributes': _kv_attributes(row.get('labels') or {}),
                'timeUnixNano': str(time_ns),
                'count': str(int(row['count'])),
                'sum': float(row['sum']),
                'explicitBounds': bounds,
                'bucketCounts': counts,
            })
    else:
        for item in items:
            name = str(item.get('name', 'figma_flow_event'))
            entry = grouped.setdefault(name, {'name': name, 'gauge': {'dataPoints': []}})
            entry['gauge']['dataPoints'].append(
                _number_point(float(item.get('value', 1.0)), item.get('labels') or {}, time_ns)
            )

    return {
        'resourceMetrics': [
            {
                'resource': {'attributes': resource_attrs},
                'scopeMetrics': [
                    {
                        'scope': {'name': 'figma-flow.metrics', 'version': service_version},
                        'metrics': list(grouped.values()),
                    }
                ],
            }
        ]
    }


class OtlpHttpSinkAdapter(PushSinkAdapter):
    """Push cumulative OTLP/HTTP JSON metrics to OTel Collector, Grafana, Datadog, etc."""

    sink_type = 'otlp-http'
    description = 'OpenTelemetry OTLP/HTTP JSON push adapter (/v1/metrics).'

    def __init__(self, sink_config: dict[str, Any], *, secret_resolver: SecretResolver | None = None):
        super().__init__(sink_config, secret_resolver=secret_resolver or SecretResolver())

    @classmethod
    def validate_config(cls, sink_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        cfg = dict(sink_config)
        allow_http = bool(cfg.get('allow_insecure_http', False))
        if not isinstance(cfg.get('allow_insecure_http', False), bool):
            raise ValueError('allow_insecure_http must be a boolean')
        cfg['url'] = validate_http_url(str(cfg.get('url', '')), allow_insecure_http=allow_http)
        headers = cfg.get('headers') or {}
        if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
            raise ValueError('OTLP sink headers must be a string-to-string object')
        cfg['headers'] = dict(headers)
        return cfg

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
        payload = build_otlp_payload(snapshot, items)
        body = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode('utf-8')
        request = urllib.request.Request(self.sink_config['url'], data=body, headers=headers, method='POST')
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
        }
