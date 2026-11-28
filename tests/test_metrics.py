"""Unit and local integration tests for optional PC-local metrics and headless diagnostics."""
from __future__ import annotations

import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import design_quality
import figma_control as control
import figma_feature as feature
import figma_workspace as workspace
import metrics
from metrics.ports import PullAdapter, PushSinkAdapter
from metrics.types import MetricSnapshot, SendResult


class _MockCollectorHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or '0')
        body = self.rfile.read(length) if length else b''
        delay = getattr(self.server, 'delay_sec', 0.0)
        if delay:
            time.sleep(delay)
        status = getattr(self.server, 'status_code', 200)
        self.server.received.append({
            'path': self.path,
            'method': self.command,
            'headers': {k.lower(): v for k, v in self.headers.items()},
            'body': json.loads(body.decode('utf-8')) if body else None,
        })
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_PUT(self):
        self.do_POST()


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class MetricsSubsystemTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.xdg_dir = self.dir / 'xdg'
        self.xdg_dir.mkdir(mode=0o700)
        env_patch = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.xdg_dir)})
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.root = self.dir / 'workspace'
        assigned = self.dir / 'assigned.json'
        assigned.write_text('{"id":"998877"}', encoding='utf-8')
        workspace.init(self.root, assigned)
        self.prepared = workspace.prepare(
            self.root,
            'discovery',
            'Read values',
            'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'],
        )
        control.enable(self.root, 49210)
        self.addCleanup(self._cleanup_hub)

    def _cleanup_hub(self):
        key = str(self.root.resolve())
        with control.METRICS_HUBS_LOCK:
            hub = control.METRICS_HUBS.pop(key, None)
        if hub is not None:
            hub.close()
        control.NATIVE_CLIENTS.pop(key, None)
        with control.RELAY_LOCK:
            control.RELAY_STATES.pop(key, None)

    def start_control_server(self):
        settings = control.config(self.root)
        server = ThreadingHTTPServer(('127.0.0.1', 0), control.Handler)
        server.workspace = self.root
        server.token = settings['token']
        settings['port'] = server.server_port
        workspace.atomic(self.root / 'control.json', workspace.encode(settings))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, settings

    def start_mock_collector(self, *, status_code=200, delay_sec=0.0):
        server = ThreadingHTTPServer(('127.0.0.1', 0), _MockCollectorHandler)
        server.received = []
        server.status_code = status_code
        server.delay_sec = delay_sec
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def http_request(self, port, method, path, *, headers=None, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def test_1_default_off_zero_side_effects_and_readiness_preserved(self):
        recorder = metrics.NullRecorder()
        self.assertFalse(recorder.is_enabled())
        self.assertEqual(recorder.record_source('operations', {'event': 'operation_terminal'}), 0)

        server, settings = self.start_control_server()
        before_files = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))

        # Pull endpoints are 404 when disabled/unconfigured
        for path in ('/metrics', '/metrics/json'):
            code, _, _ = self.http_request(
                server.server_port,
                'GET',
                path,
                headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + settings['token']},
            )
            self.assertEqual(code, 404)

        # Doctor requires control token and works read-only
        code, _, _ = self.http_request(
            server.server_port,
            'GET',
            '/metrics/doctor',
            headers={'Host': f'localhost:{server.server_port}'},
        )
        self.assertEqual(code, 403)
        code, _, raw = self.http_request(
            server.server_port,
            'GET',
            '/metrics/doctor',
            headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + settings['token']},
        )
        self.assertEqual(code, 200)
        doc = json.loads(raw)
        self.assertEqual(doc['schema'], 'figma-flow-metrics-doctor-v1')
        self.assertFalse(doc['enabled'])
        self.assertTrue(doc['server_online'])

        # Existing readiness contract unchanged and no workspace files mutated (no uncertainty.json created)
        code, _, r_raw = self.http_request(
            server.server_port,
            'POST',
            '/control/readiness',
            headers={
                'Host': f'localhost:{server.server_port}',
                'Authorization': 'Bearer ' + settings['token'],
                'Content-Type': 'application/json',
            },
            body=b'{}',
        )
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(r_raw), control.readiness(self.root))
        after_files = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        self.assertEqual(before_files, after_files)

    def test_2_adapter_registry_extensibility_and_list_adapters_cli(self):
        class CustomPull(PullAdapter):
            format_id = 'custom-text'
            content_type = 'text/plain'
            description = 'Custom pull'

            def render(self, snapshot: MetricSnapshot, *, schema=None) -> bytes:
                return f'COUNT={len(snapshot.counters)}\n'.encode('utf-8')

        class CustomSink(PushSinkAdapter):
            sink_type = 'custom-sink'
            description = 'Custom sink'
            seen = []

            def send(self, items, snapshot=None) -> SendResult:
                self.seen.extend(items)
                return SendResult(ok=True, sent_count=len(items))

        reg = metrics.default_registry()
        reg.register_pull(CustomPull)
        reg.register_sink(CustomSink)
        self.assertTrue(reg.has_pull('custom-text'))
        self.assertTrue(reg.has_sink('custom-sink'))

        hub = metrics.MetricsHub(self.root, registry=reg, start_workers=False)
        self.addCleanup(hub.close)
        ctype, rendered = hub.render_pull('custom-text')
        self.assertEqual(ctype, 'text/plain')
        self.assertEqual(rendered, b'COUNT=0\n')

        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = control.main(['metrics', 'list-adapters'])
        self.assertEqual(rc, 0)
        desc = json.loads(out.getvalue())
        self.assertEqual([row['format'] for row in desc['pull_adapters']], ['json', 'prometheus'])
        self.assertEqual([row['type'] for row in desc['sink_adapters']], ['http-json', 'jsonl-file', 'otlp-http', 'statsd-udp'])

    def test_3_config_hierarchy_permissions_url_policy_and_secret_redaction(self):
        secret_file = self.dir / 'api-secret.txt'
        secret_file.write_text('super-secret-file-token\n', encoding='utf-8')
        os.chmod(secret_file, 0o600)

        global_cfg = metrics.default_config()
        global_cfg['enabled'] = True
        global_cfg['pull'] = {'enabled': True, 'auth': 'control-token', 'formats': ['json']}
        global_cfg['privacy']['static_tags'] = {'env': 'global-pc'}
        global_cfg['sinks'] = [
            {
                'id': 'shared-api',
                'type': 'http-json',
                'enabled': True,
                'url': 'https://metrics.example.com/ingest',
                'headers': {'Authorization': 'Bearer ${TEST_METRIC_ENV_TOKEN}'},
            }
        ]
        metrics.save_config(metrics.user_config_path(), global_cfg)

        ws_cfg = metrics.default_config()
        ws_cfg['enabled'] = True
        ws_cfg['privacy']['static_tags'] = {'env': 'ws-override', 'team': 'design'}
        ws_cfg['sinks'] = [
            {
                'id': 'ws-api',
                'type': 'http-json',
                'enabled': True,
                'url': 'https://ws.example.com/ingest',
                'headers': {'X-Api-Key': f'file:{secret_file}'},
            }
        ]
        metrics.save_config(metrics.workspace_config_path(self.root), ws_cfg)

        with patch.dict(os.environ, {'TEST_METRIC_ENV_TOKEN': 'top-secret-env-value'}):
            eff, prov = metrics.load_effective_config(self.root, registry=metrics.default_registry())
            self.assertTrue(eff['enabled'])
            self.assertEqual(eff['privacy']['static_tags'], {'env': 'ws-override', 'team': 'design'})
            self.assertEqual([s['id'] for s in eff['sinks']], ['shared-api', 'ws-api'])
            self.assertEqual(prov['errors'], [])

            hub = metrics.MetricsHub(self.root, start_workers=False)
            self.addCleanup(hub.close)
            doctor = hub.doctor_report(server_online=False)
            doctor_text = json.dumps(doctor)
            self.assertNotIn('top-secret-env-value', doctor_text)
            self.assertNotIn('super-secret-file-token', doctor_text)
            self.assertTrue(all(ref['present'] for ref in doctor['secret_refs']))

        # Reject 0644 permissions on workspace config
        os.chmod(metrics.workspace_config_path(self.root), 0o644)
        _, bad_prov = metrics.load_effective_config(self.root, registry=metrics.default_registry())
        self.assertTrue(any('0600' in err['error'] for err in bad_prov['errors']))
        os.chmod(metrics.workspace_config_path(self.root), 0o600)

        # Reject insecure remote http:// unless allow_insecure_http=True
        bad_sink_cfg = metrics.default_config()
        bad_sink_cfg['sinks'] = [{'id': 'bad', 'type': 'http-json', 'url': 'http://remote.example.com/ingest'}]
        with self.assertRaisesRegex(ValueError, 'https://'):
            metrics.validate_config(bad_sink_cfg, registry=metrics.default_registry())

    def test_4_pull_adapters_auth_and_headless_gauges(self):
        cfg = metrics.default_config()
        cfg['enabled'] = True
        cfg['pull'] = {'enabled': True, 'auth': 'bearer-secret', 'bearer_secret': '${PULL_SECRET}', 'formats': ['prometheus', 'json']}
        metrics.save_config(metrics.workspace_config_path(self.root), cfg)

        with patch.dict(os.environ, {'PULL_SECRET': 'pull-token-123'}):
            server, settings = self.start_control_server()
            # Simulate live plugin poll + relay profile needsSetup + active op
            control.poll(self.root, {
                'session_id': 'plugin-session-1',
                'file_key': 'fixturefile',
                'page_id': '12:1',
                'runtime': workspace.current(self.root)['runtime'],
                'relay': {
                    'context': {
                        'session_id': 'plugin-session-1',
                        'file_key': 'fixturefile',
                        'page_id': '12:1',
                        'user_id': 'user-1',
                        'selection': [],
                        'profile': {'declared': {'plan': 'unknown', 'seat': 'unknown'}, 'needsSetup': True, 'storage': 'local'},
                    }
                },
            })
            req = control.enqueue(self.root, 'discovery', 'read', 'fixturefile', '12:1', self.prepared['revision'], 60)
            claim = control.poll(self.root, {
                'session_id': 'plugin-session-1',
                'file_key': 'fixturefile',
                'page_id': '12:1',
                'runtime': workspace.current(self.root)['runtime'],
            })['operation']
            control.result(self.root, {
                'id': claim['id'],
                'claim_id': claim['claim_id'],
                'session_id': claim['session_id'],
                'file_key': claim['file_key'],
                'page_id': claim['page_id'],
                'revision': claim['revision'],
                'status': 'ok',
                'readback_json': '{"scope":"ok"}',
            })

            # Wrong token rejected
            code, _, _ = self.http_request(
                server.server_port,
                'GET',
                '/metrics',
                headers={'Host': f'127.0.0.1:{server.server_port}', 'Authorization': 'Bearer wrong'},
            )
            self.assertEqual(code, 403)

            # Prometheus scrape succeeds with custom bearer secret
            code, headers, prom_body = self.http_request(
                server.server_port,
                'GET',
                '/metrics',
                headers={'Host': f'127.0.0.1:{server.server_port}', 'Authorization': 'Bearer pull-token-123'},
            )
            self.assertEqual(code, 200)
            self.assertIn('text/plain', headers.get('Content-Type', ''))
            prom_text = prom_body.decode('utf-8')
            self.assertIn('figma_flow_operations_total{operation="read",state="ok",task_kind="discover"} 1', prom_text)
            self.assertIn('figma_flow_operation_e2e_ms_count{operation="read",state="ok",task_kind="discover"} 1', prom_text)
            self.assertIn('figma_flow_plugin_online{runtime_status="current-self-reported"} 1', prom_text)
            self.assertIn('figma_flow_plugin_runtime_current 1', prom_text)
            self.assertIn('figma_flow_profile_needs_setup 1', prom_text)

            # JSON pull snapshot succeeds
            code, _, json_body = self.http_request(
                server.server_port,
                'GET',
                '/metrics/json',
                headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer pull-token-123'},
            )
            self.assertEqual(code, 200)
            snap = json.loads(json_body)
            self.assertEqual(snap['schema'], 'figma-flow-metrics-snapshot-v1')
            self.assertTrue(any(g['name'] == 'figma_flow_uncertain_operations' and g['value'] == 0.0 for g in snap['gauges']))
            self.assertEqual(req['id'], claim['id'])

    def test_5_push_sinks_http_otlp_jsonl_and_routing(self):
        http_collector = self.start_mock_collector()
        otlp_collector = self.start_mock_collector()
        jsonl_path = self.dir / 'logs' / 'metrics.jsonl'

        cfg = metrics.default_config()
        cfg['enabled'] = True
        cfg['sources'] = {'operations': True, 'live_changes': True, 'workspace': True, 'quality': True, 'benchmark': False}
        cfg['privacy']['static_tags'] = {'team': 'core'}
        cfg['sinks'] = [
            {
                'id': 'custom-rest',
                'type': 'http-json',
                'enabled': True,
                'url': f'http://127.0.0.1:{http_collector.server_port}/v1/custom',
                'headers': {'Authorization': 'Bearer ${REST_KEY}'},
                'include_sources': ['quality'],
                'exclude_metrics': ['figma_flow_quality_issues_total'],
                'batch_size': 10,
                'flush_interval_sec': 1,
                'mode': 'events',
                'payload_mapping': {
                    'envelope': 'records',
                    'fields': {
                        'metric': '{{name}}',
                        'val': '{{value}}',
                        'dims': '{{labels}}',
                        'ts': '{{timestamp_iso}}',
                    },
                },
            },
            {
                'id': 'otel',
                'type': 'otlp-http',
                'enabled': True,
                'url': f'http://127.0.0.1:{otlp_collector.server_port}/v1/metrics',
                'batch_size': 10,
                'flush_interval_sec': 1,
            },
            {
                'id': 'local-file',
                'type': 'jsonl-file',
                'enabled': True,
                'path': str(jsonl_path),
                'max_bytes': 1024,
                'max_files': 2,
                'batch_size': 1,
                'flush_interval_sec': 1,
            },
        ]
        metrics.save_config(metrics.workspace_config_path(self.root), cfg)

        with patch.dict(os.environ, {'REST_KEY': 'rest-secret-xyz'}):
            hub = metrics.MetricsHub(self.root, start_workers=False)
            self.addCleanup(hub.close)
            hub.record_source('operations', {'event': 'operation_terminal', 'task_kind': 'discover', 'operation': 'read', 'state': 'ok', 'e2e_ms': 42})
            hub.record_source('quality', {'passed': True, 'strict': False, 'errors': 0, 'warnings': 2})
            for idx in range(15):
                hub.record_source('live_changes', {
                    'events': [{'type': 'PROPERTY_CHANGE', 'origin': 'unknown'}],
                    'file_key': f'file-{idx}',
                    'page_id': '12:1',
                })
            hub.flush_all()

        # Verify http-json received only quality event mapped with custom envelope + resolved auth
        self.assertEqual(len(http_collector.received), 1)
        req = http_collector.received[0]
        self.assertEqual(req['headers']['authorization'], 'Bearer rest-secret-xyz')
        records = req['body']['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['metric'], 'figma_flow_quality_checks_total')
        self.assertEqual(records[0]['dims'], {'team': 'core', 'passed': 'true', 'strict': 'false'})

        # Verify otlp-http received standard resourceMetrics JSON across drained batches
        self.assertEqual(len(otlp_collector.received), 2)
        otlp_body = otlp_collector.received[-1]['body']
        metric_names = {m['name'] for m in otlp_body['resourceMetrics'][0]['scopeMetrics'][0]['metrics']}
        self.assertIn('figma_flow_operations_total', metric_names)
        self.assertIn('figma_flow_quality_checks_total', metric_names)

        # Verify jsonl-file rotated and kept 0600 permissions
        self.assertTrue(jsonl_path.exists())
        self.assertEqual(jsonl_path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(Path(f'{jsonl_path}.1').exists())

    def test_6_fail_open_circuit_breaker_and_queue_overflow(self):
        # Unreachable port for external sink
        dead_server = ThreadingHTTPServer(('127.0.0.1', 0), _MockCollectorHandler)
        dead_port = dead_server.server_port
        dead_server.server_close()

        cfg = metrics.default_config()
        cfg['enabled'] = True
        cfg['sinks'] = [
            {
                'id': 'dead-api',
                'type': 'http-json',
                'enabled': True,
                'url': f'http://127.0.0.1:{dead_port}/ingest',
                'timeout_sec': 0.2,
                'max_retries': 0,
                'batch_size': 100,
                'flush_interval_sec': 60,
            }
        ]
        metrics.save_config(metrics.workspace_config_path(self.root), cfg)

        # Control poll/result must succeed cleanly without waiting on dead sink
        t0 = time.monotonic()
        control.enqueue(self.root, 'discovery', 'read', 'fixturefile', '12:1', self.prepared['revision'], 30)
        claim = control.poll(self.root, {
            'session_id': 'plugin-session-1',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'runtime': workspace.current(self.root)['runtime'],
        })['operation']
        res = control.result(self.root, {
            'id': claim['id'],
            'claim_id': claim['claim_id'],
            'session_id': claim['session_id'],
            'file_key': claim['file_key'],
            'page_id': claim['page_id'],
            'revision': claim['revision'],
            'status': 'ok',
            'readback_json': '{"scope":"ok"}',
        })
        self.assertEqual(res['state'], 'ok')
        self.assertLess(time.monotonic() - t0, 2.0)

        # Overflow bounded queue and trigger circuit breaker
        hub = control.get_metrics_hub(self.root)
        worker = hub._workers['dead-api']
        with worker._lock:
            worker._queue.clear()
            worker.dropped_total = 0
        worker.max_queue_size = 3
        for idx in range(6):
            hub.inc('figma_flow_operations_total', labels={'task_kind': 'discover', 'operation': 'read', 'state': f's{idx}'})
        health_before = worker.health()
        self.assertEqual(health_before.dropped_total, 3)

        for idx in range(5):
            hub.inc('figma_flow_operations_total', labels={'task_kind': 'discover', 'operation': 'read', 'state': f'fail{idx}'})
            worker.flush_once(ignore_circuit=True)
        health_after = worker.health()
        self.assertTrue(health_after.circuit_open)
        self.assertGreaterEqual(health_after.failed_total, 5)
        doctor = hub.doctor_report(server_online=True)
        self.assertTrue(doctor['sinks'][0]['runtime']['circuit_open'])

    def test_7_privacy_modes_strict_hashed_scoped(self):
        schema = metrics.load_schema()
        raw_labels = {
            'task_kind': 'discover',
            'operation': 'read',
            'state': 'Bearer secret123456 /Users/alice/private',
            'file_key': 'FileKey123',
            'page_id': '12:1',
            'task_key': 'my-task',
            'user_id': 'u-99',
        }

        strict = metrics.PrivacyFilter(schema, {'scope_labels': 'strict'}, salt='s1').filter_labels('figma_flow_operations_total', raw_labels)
        self.assertNotIn('file_key', strict)
        self.assertNotIn('page_id', strict)
        self.assertNotIn('task_key', strict)
        self.assertNotIn('user_id', strict)
        self.assertIn('Bearer [redacted]', strict['state'])
        self.assertIn('[home]', strict['state'])

        hashed = metrics.PrivacyFilter(schema, {'scope_labels': 'hashed'}, salt='s1').filter_labels('figma_flow_operations_total', raw_labels)
        self.assertTrue(hashed['file_key'].startswith('h_'))
        self.assertNotEqual(hashed['file_key'], 'FileKey123')
        self.assertTrue(hashed['page_id'].startswith('h_'))

        scoped = metrics.PrivacyFilter(schema, {'scope_labels': 'scoped'}, salt='s1').filter_labels('figma_flow_operations_total', raw_labels)
        self.assertEqual(scoped['file_key'], 'FileKey123')
        self.assertEqual(scoped['page_id'], '12:1')
        self.assertEqual(scoped['task_key'], 'my-task')

    def test_8_headless_cli_workflow_and_dynamic_reload(self):
        collector = self.start_mock_collector()
        server, settings = self.start_control_server()

        def run_cli(*cli_args):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = control.main(list(cli_args))
            return code, out.getvalue()

        code, raw = run_cli('metrics', 'init', '--workspace', str(self.root))
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(raw)['config']['enabled'])

        code, _ = run_cli('metrics', 'add-sink', '--workspace', str(self.root), '--id', 'local-rest', '--type', 'http-json', '--url', f'http://127.0.0.1:{collector.server_port}/ingest')
        self.assertEqual(code, 0)
        code, _ = run_cli('metrics', 'set-pull', '--workspace', str(self.root), '--enabled', 'true', '--auth', 'control-token', '--format', 'json', '--format', 'prometheus')
        self.assertEqual(code, 0)
        code, _ = run_cli('metrics', 'set-source', '--workspace', str(self.root), '--source', 'quality', '--enabled', 'true')
        self.assertEqual(code, 0)
        code, _ = run_cli('metrics', 'set-privacy', '--workspace', str(self.root), '--scope-labels', 'hashed', '--tag', 'team=platform')
        self.assertEqual(code, 0)
        code, _ = run_cli('metrics', 'enable', '--workspace', str(self.root))
        self.assertEqual(code, 0)

        # Running server dynamically detects config change without restart!
        code, _, body = self.http_request(
            server.server_port,
            'GET',
            '/metrics/json',
            headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + settings['token']},
        )
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['privacy_mode'], 'hashed')

        # Dry-run and live test via CLI
        code, raw = run_cli('metrics', 'test', '--workspace', str(self.root), '--sink', 'local-rest', '--dry-run')
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(raw)['dry_run'])

        code, raw = run_cli('metrics', 'test', '--workspace', str(self.root), '--sink', 'local-rest')
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(raw)['ok'])
        self.assertEqual(len(collector.received), 1)

        # Online doctor & snapshot
        code, raw = run_cli('metrics', 'doctor', '--workspace', str(self.root))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(raw)['server_online'])

        code, raw = run_cli('metrics', 'snapshot', '--workspace', str(self.root), '--format', 'prometheus')
        self.assertEqual(code, 0)
        self.assertIn('figma_flow_plugin_online', raw)

        # Remove sink & disable
        code, _ = run_cli('metrics', 'remove-sink', '--workspace', str(self.root), '--id', 'local-rest')
        self.assertEqual(code, 0)
        code, _ = run_cli('metrics', 'disable', '--workspace', str(self.root))
        self.assertEqual(code, 0)

        # Offline doctor
        server.shutdown()
        code, raw = run_cli('metrics', 'doctor', '--workspace', str(self.root))
        self.assertEqual(code, 0)
        doc = json.loads(raw)
        self.assertFalse(doc['server_online'])
        self.assertFalse(doc['enabled'])

    def test_9_multiprocess_ingest_and_cli_source_hooks(self):
        cfg = metrics.default_config()
        cfg['enabled'] = True
        cfg['sources'] = {'operations': True, 'live_changes': True, 'workspace': True, 'quality': True, 'benchmark': True}
        cfg['pull'] = {'enabled': True, 'auth': 'control-token', 'formats': ['json']}
        metrics.save_config(metrics.workspace_config_path(self.root), cfg)

        server, settings = self.start_control_server()

        # Unauthorized ingest rejected
        code, _, _ = self.http_request(
            server.server_port,
            'POST',
            '/metrics/ingest',
            headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer wrong', 'Content-Type': 'application/json'},
            body=b'{"source":"workspace","payload":{}}',
        )
        self.assertEqual(code, 403)

        # Cross-origin ingest rejected
        code, _, _ = self.http_request(
            server.server_port,
            'POST',
            '/metrics/ingest',
            headers={'Host': f'localhost:{server.server_port}', 'Origin': 'https://www.figma.com', 'Authorization': 'Bearer ' + settings['token'], 'Content-Type': 'application/json'},
            body=b'{"source":"workspace","payload":{}}',
        )
        self.assertEqual(code, 403)

        # Workspace prepare hook forwards event to running server
        workspace.prepare(
            self.root,
            'discovery-two',
            'Second read',
            'discover',
            ['--file-key', 'fixturefile', '--page-id', '12:1'],
        )

        # Design quality CLI hook with --workspace forwards quality event
        layout_path = self.dir / 'layout.json'
        layout_path.write_text(json.dumps({
            'schema': 'figma-flow-authored-native-layout-v1',
            'candidates': [{
                'id': 'cand-1',
                'colors': {'bg': '#FFFFFF', 'fg': '#111111'},
                'state_layouts': {
                    'desktop': {
                        'default': {
                            'width': 390,
                            'height': 200,
                            'background': 'bg',
                            'texts': [{'id': 't1', 'text': 'Hello', 'fontSize': 16, 'color': 'fg', 'x': 16, 'y': 16, 'width': 100, 'height': 24}],
                            'controls': [],
                        }
                    }
                },
            }],
        }), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            design_quality.main(['--layout', str(layout_path), '--workspace', str(self.root)])

        # Benchmark event via emit_cli_source_event
        sent = metrics.emit_cli_source_event(self.root, 'benchmark', {
            'samples': [{'workload': 'discovery-full-default', 'state': 'ok', 'end_to_end_ms': 125.0}],
        })
        self.assertTrue(sent)

        code, _, raw = self.http_request(
            server.server_port,
            'GET',
            '/metrics/json',
            headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + settings['token']},
        )
        self.assertEqual(code, 200)
        snap = json.loads(raw)
        counter_names = {row['name'] for row in snap['counters']}
        hist_names = {row['name'] for row in snap['histograms']}
        self.assertIn('figma_flow_tasks_prepared_total', counter_names)
        self.assertIn('figma_flow_quality_checks_total', counter_names)
        self.assertIn('figma_flow_native_read_ms', hist_names)

    def test_10_statsd_udp_adapter_and_cli_add_sink(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.bind(('127.0.0.1', 0))
        udp_sock.settimeout(2.0)
        self.addCleanup(udp_sock.close)
        udp_port = udp_sock.getsockname()[1]

        for args in (
            ['metrics', 'init', '--workspace', str(self.root)],
            ['metrics', 'set-privacy', '--workspace', str(self.root), '--tag', 'env=local'],
            ['metrics', 'add-sink', '--workspace', str(self.root), '--id', 'local-statsd', '--type', 'statsd-udp',
             '--host', '127.0.0.1', '--port', str(udp_port), '--prefix', 'ff', '--dogstatsd-tags', 'true',
             '--batch-size', '10', '--flush-interval', '1'],
            ['metrics', 'enable', '--workspace', str(self.root)],
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(control.main(args), 0)

        hub = metrics.MetricsHub(self.root, start_workers=False)
        self.addCleanup(hub.close)
        hub.record_source('operations', {
            'event': 'operation_terminal',
            'task_kind': 'discover',
            'operation': 'read',
            'state': 'ok',
            'e2e_ms': 45,
        })
        hub.set_gauge('figma_flow_uncertain_operations', 0)
        res = hub.flush_all()['local-statsd']
        self.assertIsNotNone(res)
        self.assertTrue(res.ok)

        packet, _addr = udp_sock.recvfrom(8192)
        text = packet.decode('utf-8')
        self.assertIn('ff.figma_flow_operations_total:1|c|#env:local,operation:read,state:ok,task_kind:discover', text)
        self.assertIn('ff.figma_flow_operation_e2e_ms:45|ms|#env:local,operation:read,state:ok,task_kind:discover', text)
        self.assertIn('ff.figma_flow_uncertain_operations:0|g|#env:local', text)

        doctor = hub.doctor_report(server_online=False)
        self.assertEqual(doctor['sinks'][0]['healthcheck']['port'], udp_port)

    def test_11_metrics_flush_endpoint_and_cli(self):
        # Offline flush returns exit code 2 cleanly
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = control.main(['metrics', 'flush', '--workspace', str(self.root)])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out.getvalue())['flushed'])

        collector = self.start_mock_collector()
        cfg = metrics.default_config()
        cfg['enabled'] = True
        cfg['sinks'] = [{
            'id': 'buffered-http',
            'type': 'http-json',
            'enabled': True,
            'url': f'http://127.0.0.1:{collector.server_port}/ingest',
            'batch_size': 100,
            'flush_interval_sec': 300,
            'mode': 'events',
        }]
        metrics.save_config(metrics.workspace_config_path(self.root), cfg)
        server, settings = self.start_control_server()

        # Unauthorized, cross-origin, and non-empty body rejected
        code, _, _ = self.http_request(
            server.server_port, 'POST', '/metrics/flush',
            headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer wrong', 'Content-Type': 'application/json'},
            body=b'{}',
        )
        self.assertEqual(code, 403)
        code, _, _ = self.http_request(
            server.server_port, 'POST', '/metrics/flush',
            headers={'Host': f'localhost:{server.server_port}', 'Origin': 'https://www.figma.com', 'Authorization': 'Bearer ' + settings['token'], 'Content-Type': 'application/json'},
            body=b'{}',
        )
        self.assertEqual(code, 403)
        code, _, _ = self.http_request(
            server.server_port, 'POST', '/metrics/flush',
            headers={'Host': f'localhost:{server.server_port}', 'Authorization': 'Bearer ' + settings['token'], 'Content-Type': 'application/json'},
            body=b'{"extra":1}',
        )
        self.assertEqual(code, 409)

        hub = control.get_metrics_hub(self.root)
        hub.inc('figma_flow_operations_total', labels={'task_kind': 'discover', 'operation': 'read', 'state': 'ok'})
        self.assertEqual(len(collector.received), 0)

        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = control.main(['metrics', 'flush', '--workspace', str(self.root)])
        self.assertEqual(rc, 0)
        flush_reply = json.loads(out.getvalue())
        self.assertTrue(flush_reply['flushed'])
        self.assertTrue(flush_reply['sinks']['buffered-http']['ok'])
        self.assertEqual(len(collector.received), 1)

    def test_12_metrics_watch_until_ready_and_timeout(self):
        server, _settings = self.start_control_server()

        # Timeout when plugin never polls
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = control.main(['metrics', 'watch', '--workspace', str(self.root), '--until-ready', '--interval', '0.05', '--count', '2'])
        self.assertEqual(rc, 2)
        rows = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row['ready'] and row['server_online'] and not row['plugin_online'] for row in rows))

        # Spawn background thread that brings plugin online after 0.15s
        def bring_online():
            time.sleep(0.15)
            control.poll(self.root, {
                'session_id': 'plugin-session-watch',
                'file_key': 'fixturefile',
                'page_id': '12:1',
                'runtime': workspace.current(self.root)['runtime'],
            })

        worker = threading.Thread(target=bring_online, daemon=True)
        worker.start()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = control.main(['metrics', 'watch', '--workspace', str(self.root), '--until-ready', '--interval', '0.05', '--count', '30'])
        worker.join(timeout=2)
        self.assertEqual(rc, 0)
        rows = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        self.assertGreaterEqual(len(rows), 2)
        self.assertFalse(rows[0]['ready'])
        self.assertTrue(rows[-1]['ready'])
        self.assertTrue(rows[-1]['plugin_online'])
        self.assertTrue(rows[-1]['plugin_runtime_current'])
        self.assertEqual(rows[-1]['uncertain_operations'], 0)
        self.assertEqual(server.server_port, control.config(self.root)['port'])

    def test_13_feature_route_for_metrics_korean_and_english(self):
        for query in ('메트릭', 'metrics', 'prometheus', 'statsd'):
            routed = feature.route(query)
            self.assertEqual(routed['status'], 'routed')
            self.assertEqual(routed['routes'][0]['id'], 'metrics-export')
            self.assertEqual(routed['execution'], 'not-executed')


if __name__ == '__main__':
    unittest.main()
