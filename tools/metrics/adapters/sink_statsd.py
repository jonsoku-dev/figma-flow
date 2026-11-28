"""StatsD / DogStatsD UDP push sink adapter (Python stdlib only)."""
from __future__ import annotations

import re
import socket
import time
from typing import Any

import local_endpoint
import runtime_limits

from ..ports import PushSinkAdapter
from ..registry import load_schema
from ..secrets import redact_value
from ..types import MetricSnapshot, SendResult

_PREFIX_RE = re.compile(r'^[A-Za-z0-9_.-]{0,64}$')
_TAG_SANITIZE_RE = re.compile(r'[|,\r\n:]')
_DEFAULTS = load_schema()['defaults']
DEFAULT_TIMEOUT_SEC = runtime_limits.NETWORK['statsdSocketTimeoutMs'] / 1000


def _sanitize_tag_part(value: str) -> str:
    return _TAG_SANITIZE_RE.sub('_', str(value)).strip()


def _format_number(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f'{float(value):.6g}'


def format_statsd_line(
    item: dict[str, Any],
    *,
    prefix: str = '',
    dogstatsd_tags: bool = True,
    static_tags: dict[str, str] | None = None,
) -> str:
    """Encode a normalized metric event dict into a StatsD/DogStatsD line."""
    raw_name = str(item.get('name') or 'figma_flow_event')
    metric_name = f'{prefix}.{raw_name}' if prefix else raw_name
    kind = str(item.get('kind') or 'counter')
    value = float(item.get('value', 1.0))

    if kind == 'gauge':
        type_code = 'g'
    elif kind == 'histogram':
        type_code = 'ms' if raw_name.endswith('_ms') else 'h'
    else:
        type_code = 'c'

    line = f'{metric_name}:{_format_number(value)}|{type_code}'
    if dogstatsd_tags:
        merged = {**(static_tags or {}), **(item.get('labels') or {})}
        if merged:
            tags = ','.join(
                f'{_sanitize_tag_part(k)}:{_sanitize_tag_part(v)}'
                for k, v in sorted(merged.items())
                if _sanitize_tag_part(k)
            )
            if tags:
                line += f'|#{tags}'
    return line


class StatsdUdpSinkAdapter(PushSinkAdapter):
    """Send StatsD / DogStatsD UDP datagrams to local or internal metrics agents."""

    sink_type = 'statsd-udp'
    description = 'StatsD / DogStatsD UDP datagram push adapter (no external dependencies).'

    def __init__(self, sink_config: dict[str, Any], *, secret_resolver: Any = None):
        super().__init__(sink_config, secret_resolver=secret_resolver)
        self._sock: socket.socket | None = None

    @classmethod
    def validate_config(cls, sink_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        cfg = dict(sink_config)
        host = cfg.get('host', local_endpoint.BIND_HOST)
        if not isinstance(host, str) or not host.strip() or any(ch.isspace() for ch in host):
            raise ValueError('statsd-udp sink requires a valid non-empty host')
        defaults = schema['defaults']
        port = cfg.get('port', defaults['statsdPort'])
        if isinstance(port, bool) or not isinstance(port, int) or port not in runtime_limits.TCP_PORTS:
            raise ValueError(f'statsd-udp sink port must be an integer between 1 and {runtime_limits.NETWORK["maxTcpPort"]}')
        prefix = cfg.get('prefix', '')
        if not isinstance(prefix, str) or not _PREFIX_RE.fullmatch(prefix):
            raise ValueError('statsd-udp sink prefix may contain only [A-Za-z0-9_.-] (max 64 chars)')
        dogstatsd_tags = cfg.get('dogstatsd_tags', True)
        if not isinstance(dogstatsd_tags, bool):
            raise ValueError('statsd-udp sink dogstatsd_tags must be a boolean')
        max_packet_bytes = cfg.get('max_packet_bytes', defaults['statsdMaxPacketBytes'])
        if (isinstance(max_packet_bytes, bool) or not isinstance(max_packet_bytes, int)
                or not 256 <= max_packet_bytes <= runtime_limits.NETWORK['maxUdpPayloadBytes']):
            raise ValueError(f'statsd-udp sink max_packet_bytes must be between 256 and {runtime_limits.NETWORK["maxUdpPayloadBytes"]}')
        cfg['host'] = host.strip()
        cfg['port'] = port
        cfg['prefix'] = prefix.strip('.')
        cfg['dogstatsd_tags'] = dogstatsd_tags
        cfg['max_packet_bytes'] = max_packet_bytes
        return cfg

    def _get_socket(self) -> socket.socket:
        if self._sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(float(self.sink_config.get('timeout_sec', DEFAULT_TIMEOUT_SEC)))
            self._sock = sock
        return self._sock

    def send(self, items: list[dict[str, Any]], snapshot: MetricSnapshot | None = None) -> SendResult:
        started = time.monotonic()
        static_tags = dict(snapshot.static_tags) if snapshot else {}
        prefix = str(self.sink_config.get('prefix', ''))
        dogstatsd_tags = bool(self.sink_config.get('dogstatsd_tags', True))
        max_bytes = int(self.sink_config.get('max_packet_bytes', _DEFAULTS['statsdMaxPacketBytes']))

        rows = list(items)
        if not rows and snapshot is not None:
            for g in snapshot.gauges:
                rows.append({'name': g['name'], 'kind': 'gauge', 'value': g['value'], 'labels': g.get('labels') or {}})

        if not rows:
            return SendResult(ok=True, sent_count=0, latency_ms=(time.monotonic() - started) * 1000)

        lines = [
            format_statsd_line(row, prefix=prefix, dogstatsd_tags=dogstatsd_tags, static_tags=static_tags)
            for row in rows
        ]

        packets: list[bytes] = []
        current: list[str] = []
        current_bytes = 0
        for line in lines:
            line_bytes = len(line.encode('utf-8')) + 1
            if current and current_bytes + line_bytes > max_bytes:
                packets.append(('\n'.join(current)).encode('utf-8'))
                current = [line]
                current_bytes = line_bytes
            else:
                current.append(line)
                current_bytes += line_bytes
        if current:
            packets.append(('\n'.join(current)).encode('utf-8'))

        try:
            sock = self._get_socket()
            addr = (self.sink_config['host'], int(self.sink_config['port']))
            for packet in packets:
                sock.sendto(packet, addr)
            return SendResult(
                ok=True,
                sent_count=len(rows),
                latency_ms=(time.monotonic() - started) * 1000,
            )
        except (OSError, ValueError) as exc:
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
            'host': self.sink_config.get('host'),
            'port': self.sink_config.get('port'),
            'prefix': self.sink_config.get('prefix', ''),
            'dogstatsd_tags': self.sink_config.get('dogstatsd_tags', True),
        }

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
