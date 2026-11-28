"""Core MetricsHub: thread-safe aggregation, live gauges, fail-open per-sink dispatch, and doctor."""
from __future__ import annotations

from collections import deque
import hashlib
import socket
import threading
import time
from typing import Any, Callable

from .adapters import register_builtin_adapters
from .config import config_fingerprint, load_effective_config
from .ports import MetricRecorder, PushSinkAdapter
from .registry import AdapterRegistry, PrivacyFilter, load_schema
from .secrets import SecretResolver, redact_value
from .sources import register_builtin_sources
from .types import MetricEvent, MetricSample, MetricSnapshot, SendResult, SinkHealth, now_iso, now_unix_ns


def default_registry() -> AdapterRegistry:
    """Create a registry populated with all built-in Source, Pull, and Sink adapters."""
    schema = load_schema()
    registry = AdapterRegistry(schema)
    register_builtin_sources(registry)
    register_builtin_adapters(registry)
    return registry


def _label_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _labels_from_key(key: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return dict(key)


class _SinkWorker:
    """Independent bounded queue + background flush worker with circuit breaker."""

    def __init__(
        self,
        adapter: PushSinkAdapter,
        sink_cfg: dict[str, Any],
        hub: 'MetricsHub',
        *,
        max_queue_size: int,
    ):
        self.adapter = adapter
        self.sink_cfg = dict(sink_cfg)
        self.sink_id = str(sink_cfg['id'])
        self.sink_type = str(sink_cfg['type'])
        self.enabled = bool(sink_cfg.get('enabled', True))
        self.hub = hub
        self.max_queue_size = max_queue_size
        self.batch_size = int(sink_cfg.get('batch_size', 50))
        self.flush_interval_sec = float(sink_cfg.get('flush_interval_sec', 15))
        self.max_retries = int(sink_cfg.get('max_retries', 2))
        raw_sources = sink_cfg.get('include_sources')
        self.include_sources: set[str] | None = set(raw_sources) if raw_sources is not None else None
        self.exclude_metrics: set[str] = set(sink_cfg.get('exclude_metrics') or [])

        self._lock = threading.Lock()
        self._queue: deque[dict[str, Any]] = deque()
        self._wake = threading.Event()
        self._stop = threading.Event()

        self.sent_total = 0
        self.failed_total = 0
        self.dropped_total = 0
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0
        self.last_error: str | None = None
        self.last_success_iso: str | None = None
        self.last_attempt_iso: str | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f'figma-flow-metrics-{self.sink_id}',
            daemon=True,
        )
        self._thread.start()

    def admits(self, source: str, metric_name: str) -> bool:
        if not self.enabled:
            return False
        if self.include_sources is not None and source not in self.include_sources:
            return False
        if metric_name in self.exclude_metrics:
            return False
        return True

    def enqueue(self, item: dict[str, Any]) -> None:
        if not self.admits(str(item.get('source', '')), str(item.get('name', ''))):
            return
        dropped_count = 0
        with self._lock:
            while len(self._queue) >= self.max_queue_size:
                self._queue.popleft()
                self.dropped_total += 1
                dropped_count += 1
            self._queue.append(item)
            should_wake = len(self._queue) >= self.batch_size
        for _ in range(dropped_count):
            self.hub._record_internal_drop(self.sink_id)
        if should_wake:
            self._wake.set()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.flush_interval_sec)
            self._wake.clear()
            if self._stop.is_set():
                break
            self.flush_once()

    def flush_once(self, *, ignore_circuit: bool = False) -> SendResult | None:
        now_mono = time.monotonic()
        if not ignore_circuit and now_mono < self.circuit_open_until:
            return None
        with self._lock:
            if not self._queue and self.sink_cfg.get('mode') != 'snapshot':
                return None
            batch: list[dict[str, Any]] = []
            while self._queue and len(batch) < self.batch_size:
                batch.append(self._queue.popleft())
        if not batch and self.sink_cfg.get('mode') != 'snapshot':
            return None
        snapshot = self.hub.snapshot()
        result = self._deliver_with_retry(batch, snapshot)
        return result

    def _deliver_with_retry(self, batch: list[dict[str, Any]], snapshot: MetricSnapshot | None) -> SendResult:
        last_result = SendResult(ok=False, error='No delivery attempted', retryable=False)
        for attempt in range(self.max_retries + 1):
            last_result = self.adapter.send(batch, snapshot)
            if last_result.ok:
                break
            if not last_result.retryable or attempt >= self.max_retries:
                break
            backoff = min(2.0, 0.1 * (2 ** attempt))
            if self._stop.wait(backoff):
                break
        now_str = now_iso()
        with self._lock:
            self.last_attempt_iso = now_str
            if last_result.ok:
                self.sent_total += last_result.sent_count or len(batch)
                self.consecutive_failures = 0
                self.circuit_open_until = 0.0
                self.last_error = None
                self.last_success_iso = now_str
            else:
                self.failed_total += 1
                self.consecutive_failures += 1
                self.last_error = last_result.error or 'Delivery failed'
                if self.consecutive_failures >= 5:
                    self.circuit_open_until = time.monotonic() + 30.0
        self.hub._record_internal_export(self.sink_id, 'ok' if last_result.ok else 'error')
        return last_result

    def health(self) -> SinkHealth:
        with self._lock:
            return SinkHealth(
                sink_id=self.sink_id,
                sink_type=self.sink_type,
                enabled=self.enabled,
                queue_depth=len(self._queue),
                sent_total=self.sent_total,
                failed_total=self.failed_total,
                dropped_total=self.dropped_total,
                consecutive_failures=self.consecutive_failures,
                circuit_open=time.monotonic() < self.circuit_open_until,
                last_error=self.last_error,
                last_success_iso=self.last_success_iso,
                last_attempt_iso=self.last_attempt_iso,
            )

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self.adapter.close()
        except Exception:
            pass


class MetricsHub(MetricRecorder):
    """Central thread-safe metrics aggregator, pull renderer, and async push dispatcher."""

    def __init__(
        self,
        workspace_root: str | object = None,
        *,
        registry: AdapterRegistry | None = None,
        secret_resolver: SecretResolver | None = None,
        start_workers: bool = True,
    ):
        self.workspace_root = str(workspace_root) if workspace_root is not None else None
        self.registry = registry if registry is not None else default_registry()
        self.schema = self.registry.schema
        self.secret_resolver = secret_resolver if secret_resolver is not None else SecretResolver()
        self._start_workers = start_workers
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, Any]] = {}
        self._gauge_collectors: list[Callable[[], list[MetricSample]]] = []
        self._workers: dict[str, _SinkWorker] = {}
        self._config_fp: tuple[Any, ...] | None = None
        self._config: dict[str, Any] = {}
        self._provenance: dict[str, Any] = {}
        self._privacy: PrivacyFilter = PrivacyFilter(self.schema)
        self._salt = hashlib.sha256((self.workspace_root or 'global').encode('utf-8')).hexdigest()[:16]
        self.reload(force=True)

    def reload(self, *, force: bool = False) -> bool:
        """Reload global + workspace configs if changed on disk."""
        fp = config_fingerprint(self.workspace_root)
        with self._lock:
            if not force and fp == self._config_fp:
                return False
            cfg, prov = load_effective_config(self.workspace_root, schema=self.schema, registry=self.registry)
            privacy_cfg = dict(cfg.get('privacy') or {})
            privacy = PrivacyFilter(self.schema, privacy_cfg, salt=self._salt)
            if privacy.include_host_tag and 'host' not in privacy.static_tags:
                privacy.static_tags['host'] = socket.gethostname()[:privacy.max_label_len]

            old_workers = list(self._workers.values())
            new_workers: dict[str, _SinkWorker] = {}
            max_q = int(self.schema['limits']['maxQueueSize'])
            if cfg.get('enabled'):
                for sink_cfg in cfg.get('sinks') or []:
                    if not sink_cfg.get('enabled', True):
                        continue
                    try:
                        enriched = dict(sink_cfg)
                        if self.workspace_root:
                            enriched['_workspace_root'] = self.workspace_root
                        adapter = self.registry.create_sink(enriched, secret_resolver=self.secret_resolver)
                        worker = _SinkWorker(adapter, enriched, self, max_queue_size=max_q)
                        if self._start_workers:
                            worker.start()
                        new_workers[worker.sink_id] = worker
                    except Exception as exc:
                        prov.setdefault('sink_errors', []).append({
                            'id': sink_cfg.get('id'),
                            'error': redact_value(exc),
                        })

            self._config = cfg
            self._provenance = prov
            self._privacy = privacy
            self._workers = new_workers
            self._config_fp = fp

        for worker in old_workers:
            worker.close()
        return True

    def maybe_reload(self) -> None:
        if config_fingerprint(self.workspace_root) != self._config_fp:
            self.reload(force=False)

    def is_enabled(self) -> bool:
        self.maybe_reload()
        with self._lock:
            return bool(self._config.get('enabled'))

    def source_enabled(self, source_id: str) -> bool:
        self.maybe_reload()
        with self._lock:
            return bool(self._config.get('enabled') and self._config.get('sources', {}).get(source_id))

    def is_pull_enabled(self, format_id: str) -> bool:
        self.maybe_reload()
        with self._lock:
            if not self._config.get('enabled'):
                return False
            pull = self._config.get('pull') or {}
            return bool(pull.get('enabled') and format_id in (pull.get('formats') or []))

    def pull_auth_config(self) -> tuple[str, str | None]:
        self.maybe_reload()
        with self._lock:
            pull = self._config.get('pull') or {}
            return str(pull.get('auth', 'control-token')), pull.get('bearer_secret')

    def register_gauge_collector(self, collector: Callable[[], list[MetricSample]]) -> None:
        with self._lock:
            self._gauge_collectors.append(collector)

    def _record_internal_export(self, sink_id: str, status: str) -> None:
        with self._lock:
            key = ('figma_flow_metrics_export_total', (('sink', sink_id), ('status', status)))
            self._counters[key] = self._counters.get(key, 0.0) + 1.0

    def _record_internal_drop(self, sink_id: str) -> None:
        with self._lock:
            key = ('figma_flow_metrics_queue_dropped_total', (('sink', sink_id),))
            self._counters[key] = self._counters.get(key, 0.0) + 1.0

    def _store_sample_unlocked(self, sample: MetricSample) -> MetricSample | None:
        spec = self.schema['metrics'].get(sample.name)
        if not spec:
            return None
        clean_labels = self._privacy.filter_labels(sample.name, sample.labels)
        lkey = _label_key(clean_labels)
        mkey = (sample.name, lkey)
        kind = spec['type']
        if kind == 'counter':
            self._counters[mkey] = self._counters.get(mkey, 0.0) + float(sample.value)
        elif kind == 'gauge':
            self._gauges[mkey] = float(sample.value)
        elif kind == 'histogram':
            bounds = tuple(float(b) for b in spec.get('buckets') or [])
            entry = self._histograms.get(mkey)
            if entry is None:
                entry = {'bounds': bounds, 'counts': [0] * (len(bounds) + 1), 'sum': 0.0, 'count': 0}
                self._histograms[mkey] = entry
            val = float(sample.value)
            entry['sum'] += val
            entry['count'] += 1
            for idx, bound in enumerate(bounds):
                if val <= bound:
                    entry['counts'][idx] += 1
            entry['counts'][-1] += 1
        return MetricSample(
            name=sample.name,
            kind=kind,
            value=float(sample.value),
            labels=clean_labels,
            source=sample.source,
            timestamp_ns=sample.timestamp_ns,
        )

    def inc(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None, *, source: str = 'operations') -> None:
        if not self.source_enabled(source):
            return
        with self._lock:
            stored = self._store_sample_unlocked(MetricSample(name=name, kind='counter', value=value, labels=labels or {}, source=source))
            workers = list(self._workers.values())
        if stored:
            event = MetricEvent(name=stored.name, source=source, kind='counter', value=stored.value, labels=stored.labels, timestamp_ns=stored.timestamp_ns).to_dict()
            for worker in workers:
                worker.enqueue(event)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None, *, source: str = 'operations') -> None:
        if not self.source_enabled(source):
            return
        with self._lock:
            stored = self._store_sample_unlocked(MetricSample(name=name, kind='gauge', value=value, labels=labels or {}, source=source))
            workers = list(self._workers.values())
        if stored:
            event = MetricEvent(name=stored.name, source=source, kind='gauge', value=stored.value, labels=stored.labels, timestamp_ns=stored.timestamp_ns).to_dict()
            for worker in workers:
                worker.enqueue(event)

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None, *, source: str = 'operations') -> None:
        if not self.source_enabled(source):
            return
        with self._lock:
            stored = self._store_sample_unlocked(MetricSample(name=name, kind='histogram', value=value, labels=labels or {}, source=source))
            workers = list(self._workers.values())
        if stored:
            event = MetricEvent(name=stored.name, source=source, kind='histogram', value=stored.value, labels=stored.labels, timestamp_ns=stored.timestamp_ns).to_dict()
            for worker in workers:
                worker.enqueue(event)

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
        if not self.source_enabled(source):
            return
        with self._lock:
            clean_labels = self._privacy.filter_labels(name, labels) if name in self.schema['metrics'] else {}
            clean_attrs = self._privacy.filter_attributes(attributes)
            workers = list(self._workers.values())
        event = MetricEvent(name=name, source=source, kind=kind, value=float(value), labels=clean_labels, attributes=clean_attrs).to_dict()
        for worker in workers:
            worker.enqueue(event)

    def record_source(self, source_id: str, payload: dict[str, Any]) -> int:
        if not self.source_enabled(source_id):
            return 0
        adapter = self.registry.get_source(source_id)
        if adapter is None:
            return 0
        samples, events = adapter.normalize(payload)
        stored_count = 0
        with self._lock:
            for sample in samples:
                if self._store_sample_unlocked(sample) is not None:
                    stored_count += 1
            workers = list(self._workers.values())
            filtered_events: list[dict[str, Any]] = []
            for event in events:
                clean_labels = self._privacy.filter_labels(event.name, event.labels) if event.name in self.schema['metrics'] else {}
                clean_attrs = self._privacy.filter_attributes(event.attributes)
                filtered_events.append(MetricEvent(
                    name=event.name,
                    source=event.source,
                    kind=event.kind,
                    value=event.value,
                    labels=clean_labels,
                    attributes=clean_attrs,
                    timestamp_ns=event.timestamp_ns,
                ).to_dict())
        for item in filtered_events:
            for worker in workers:
                worker.enqueue(item)
        return stored_count

    def snapshot(self) -> MetricSnapshot:
        """Return a thread-safe point-in-time MetricSnapshot including live gauges."""
        self.maybe_reload()
        with self._lock:
            collectors = list(self._gauge_collectors)
            cfg = dict(self._config)
            privacy = self._privacy
            counters = [
                {'name': name, 'labels': _labels_from_key(lkey), 'value': val}
                for (name, lkey), val in sorted(self._counters.items())
            ]
            gauges_map = dict(self._gauges)
            histograms = []
            for (name, lkey), entry in sorted(self._histograms.items()):
                buckets = [
                    [bound, entry['counts'][idx]]
                    for idx, bound in enumerate(entry['bounds'])
                ]
                buckets.append(['+Inf', entry['counts'][-1]])
                histograms.append({
                    'name': name,
                    'labels': _labels_from_key(lkey),
                    'count': entry['count'],
                    'sum': entry['sum'],
                    'buckets': buckets,
                })
            workers = list(self._workers.values())

        # Evaluate dynamic live gauges outside hub lock to prevent lock ordering issues.
        dynamic_samples: list[MetricSample] = []
        for collector in collectors:
            try:
                dynamic_samples.extend(collector())
            except Exception:
                pass
        for sample in dynamic_samples:
            if sample.name in self.schema['metrics']:
                try:
                    clean_labels = privacy.filter_labels(sample.name, sample.labels)
                    gauges_map[(sample.name, _label_key(clean_labels))] = float(sample.value)
                except ValueError:
                    pass

        gauges = [
            {'name': name, 'labels': _labels_from_key(lkey), 'value': val}
            for (name, lkey), val in sorted(gauges_map.items())
        ]
        sink_health = [worker.health().to_dict() for worker in workers]
        ts = now_unix_ns()
        return MetricSnapshot(
            schema=self.schema['snapshotSchema'],
            generated_at_iso=now_iso(ts),
            generated_at_ns=ts,
            privacy_mode=privacy.mode,
            sources=dict(cfg.get('sources') or {}),
            counters=counters,
            gauges=gauges,
            histograms=histograms,
            sink_health=sink_health,
            static_tags=dict(privacy.static_tags),
        )

    def render_pull(self, format_id: str) -> tuple[str, bytes]:
        """Render the current snapshot using the registered PullAdapter."""
        adapter = self.registry.create_pull(format_id)
        snap = self.snapshot()
        return adapter.content_type, adapter.render(snap, schema=self.schema)

    def flush_all(self) -> dict[str, SendResult | None]:
        """Synchronously drain all active sink worker queues (useful for shutdown and tests)."""
        with self._lock:
            workers = list(self._workers.items())
        results: dict[str, SendResult | None] = {}
        for sink_id, worker in workers:
            last: SendResult | None = None
            while True:
                res = worker.flush_once(ignore_circuit=True)
                if res is None:
                    break
                last = res
                if not res.ok:
                    break
                with worker._lock:
                    if not worker._queue:
                        break
            results[sink_id] = last
        return results

    def test_sink(self, sink_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """Validate and optionally send a single synthetic probe item to one configured sink."""
        self.maybe_reload()
        with self._lock:
            sinks = list(self._config.get('sinks') or [])
            privacy = self._privacy
        sink_cfg = next((row for row in sinks if row.get('id') == sink_id), None)
        if sink_cfg is None:
            raise ValueError(f'Unknown sink id: {sink_id}')
        enriched = dict(sink_cfg)
        if self.workspace_root:
            enriched['_workspace_root'] = self.workspace_root
        adapter = self.registry.create_sink(enriched, secret_resolver=self.secret_resolver)
        secret_status = self.secret_resolver.inspect_refs(sink_cfg)
        probe_event = MetricEvent(
            name='figma_flow_operations_total',
            source='operations',
            kind='counter',
            value=1.0,
            labels=privacy.filter_labels('figma_flow_operations_total', {'task_kind': 'discover', 'operation': 'read', 'state': 'ok'}),
            attributes={'probe': True},
        ).to_dict()
        snapshot = self.snapshot()
        try:
            if dry_run:
                return {
                    'sink_id': sink_id,
                    'type': adapter.sink_type,
                    'dry_run': True,
                    'ok': all(ref['present'] for ref in secret_status),
                    'healthcheck': adapter.healthcheck(),
                    'secret_refs': secret_status,
                    'sample_item': probe_event,
                }
            result = adapter.send([probe_event], snapshot)
            return {
                'sink_id': sink_id,
                'type': adapter.sink_type,
                'dry_run': False,
                'ok': result.ok,
                'status_code': result.status_code,
                'sent_count': result.sent_count,
                'latency_ms': round(result.latency_ms, 2) if result.latency_ms is not None else None,
                'error': result.error,
                'healthcheck': adapter.healthcheck(),
                'secret_refs': secret_status,
            }
        finally:
            adapter.close()

    def doctor_report(self, *, live_state: dict[str, Any] | None = None, server_online: bool = True) -> dict[str, Any]:
        """Build a headless diagnostic report without revealing secrets."""
        self.maybe_reload()
        snap = self.snapshot()
        with self._lock:
            cfg = dict(self._config)
            prov = dict(self._provenance)
            workers = dict(self._workers)

        secret_refs = self.secret_resolver.inspect_refs(cfg)
        sink_rows = []
        for row in cfg.get('sinks') or []:
            sid = row.get('id')
            worker = workers.get(sid)
            enriched = dict(row)
            if self.workspace_root:
                enriched['_workspace_root'] = self.workspace_root
            hc: dict[str, Any] = {'sink_id': sid, 'type': row.get('type')}
            try:
                temp_adapter = self.registry.create_sink(enriched, secret_resolver=self.secret_resolver)
                try:
                    hc = temp_adapter.healthcheck()
                finally:
                    temp_adapter.close()
            except Exception as exc:
                hc['validation_error'] = redact_value(exc)
            sink_rows.append({
                'id': sid,
                'type': row.get('type'),
                'enabled': bool(row.get('enabled', True)),
                'healthcheck': hc,
                'runtime': worker.health().to_dict() if worker else None,
            })

        recommendations: list[str] = []
        if not cfg.get('enabled'):
            recommendations.append('Enable metrics with: figma_control.py metrics enable --workspace <WORKSPACE>')
        if not server_online:
            recommendations.append('Start the local relay server with: figma_control.py serve --workspace <WORKSPACE>')
        for ref in secret_refs:
            if not ref['present']:
                recommendations.append(f"Provide missing {ref['kind']} secret reference: {ref['ref']}")
        if live_state and not live_state.get('plugin_online'):
            recommendations.append('Reopen the registered Figma Flow plugin once in Figma Desktop to resume polling.')

        return {
            'schema': self.schema['doctorSchema'],
            'generated_at': now_iso(),
            'server_online': server_online,
            'enabled': bool(cfg.get('enabled')),
            'provenance': prov,
            'privacy': {
                'scope_labels': cfg.get('privacy', {}).get('scope_labels', 'strict'),
                'include_host_tag': cfg.get('privacy', {}).get('include_host_tag', False),
                'static_tag_keys': sorted((cfg.get('privacy', {}).get('static_tags') or {}).keys()),
            },
            'sources': dict(cfg.get('sources') or {}),
            'pull': {
                'enabled': bool(cfg.get('pull', {}).get('enabled', False)),
                'auth': cfg.get('pull', {}).get('auth', 'control-token'),
                'formats': list(cfg.get('pull', {}).get('formats') or []),
            },
            'secret_refs': secret_refs,
            'sinks': sink_rows,
            'live_state': live_state or {},
            'gauges': snap.gauges,
            'recommendations': recommendations,
        }

    def close(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers = {}
        for worker in workers:
            worker.close()
