"""Rotating NDJSON / JSONL local file sink adapter."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from ..ports import PushSinkAdapter
from ..secrets import redact_value
from ..types import MetricSnapshot, SendResult

MIN_ROTATE_BYTES = 1024
MAX_ROTATE_BYTES = 100 * 1024 * 1024


class JsonlFileSinkAdapter(PushSinkAdapter):
    """Write metrics events into a rotating 0600 JSONL file for local log shippers."""

    sink_type = 'jsonl-file'
    description = 'Rotating local JSONL/NDJSON file sink (0600 permissions) for Fluent Bit/Vector/Filebeat.'

    def __init__(self, sink_config: dict[str, Any], *, secret_resolver: Any = None):
        super().__init__(sink_config, secret_resolver=secret_resolver)
        self._lock = threading.Lock()

    @classmethod
    def validate_config(cls, sink_config: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        cfg = dict(sink_config)
        raw_path = cfg.get('path')
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError('jsonl-file sink requires a non-empty path')
        max_bytes = cfg.get('max_bytes', 10 * 1024 * 1024)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not MIN_ROTATE_BYTES <= max_bytes <= MAX_ROTATE_BYTES:
            raise ValueError(f'jsonl-file sink max_bytes must be between {MIN_ROTATE_BYTES} and {MAX_ROTATE_BYTES}')
        max_files = cfg.get('max_files', 3)
        if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= 20:
            raise ValueError('jsonl-file sink max_files must be between 1 and 20')
        cfg['max_bytes'] = max_bytes
        cfg['max_files'] = max_files
        return cfg

    def _resolved_path(self) -> Path:
        raw = str(self.sink_config['path'])
        workspace = self.sink_config.get('_workspace_root')
        if workspace and '$WORKSPACE' in raw:
            raw = raw.replace('$WORKSPACE', str(workspace))
        return Path(raw).expanduser().absolute()

    def _rotate_if_needed(self, path: Path, incoming_bytes: int) -> None:
        max_bytes = int(self.sink_config['max_bytes'])
        max_files = int(self.sink_config['max_files'])
        if not path.exists():
            return
        if path.stat().st_size + incoming_bytes <= max_bytes:
            return
        for idx in range(max_files - 1, 0, -1):
            src = Path(f'{path}.{idx}')
            dst = Path(f'{path}.{idx + 1}')
            if src.exists():
                if idx + 1 > max_files:
                    src.unlink(missing_ok=True)
                else:
                    os.replace(src, dst)
        if max_files >= 1:
            os.replace(path, Path(f'{path}.1'))

    def send(self, items: list[dict[str, Any]], snapshot: MetricSnapshot | None = None) -> SendResult:
        started = time.monotonic()
        rows = list(items)
        if not rows and snapshot is not None:
            rows = [{
                'kind': 'snapshot',
                'generated_at': snapshot.generated_at_iso,
                'counters': snapshot.counters,
                'gauges': snapshot.gauges,
                'histograms': snapshot.histograms,
            }]
        if not rows:
            return SendResult(ok=True, sent_count=0, latency_ms=(time.monotonic() - started) * 1000)
        payload = ''.join(json.dumps(row, ensure_ascii=True, allow_nan=False) + '\n' for row in rows).encode('utf-8')
        try:
            target = self._resolved_path()
            if target.is_symlink():
                raise ValueError('Refusing symlink jsonl-file target')
            if os.name == 'posix':
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                self._rotate_if_needed(target, len(payload))
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    if os.name == 'posix':
                        os.fchmod(fd, 0o600)
                    os.write(fd, payload)
                    os.fsync(fd)
                finally:
                    os.close(fd)
            return SendResult(ok=True, sent_count=len(rows), latency_ms=(time.monotonic() - started) * 1000)
        except (OSError, ValueError) as exc:
            return SendResult(
                ok=False,
                sent_count=0,
                error=redact_value(exc),
                latency_ms=(time.monotonic() - started) * 1000,
                retryable=False,
            )

    def healthcheck(self) -> dict[str, Any]:
        return {
            'sink_id': self.sink_id,
            'type': self.sink_type,
            'path': redact_value(str(self._resolved_path())),
            'max_bytes': self.sink_config['max_bytes'],
            'max_files': self.sink_config['max_files'],
        }
