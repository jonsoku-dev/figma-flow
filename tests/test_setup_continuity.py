"""Tests for PC-local workspace registry, setup-status continuity, and live startup checks."""
from __future__ import annotations

import contextlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import figma_control as control
import figma_workspace as workspace
import plugin_startup as startup
import workspace_registry


@unittest.skipUnless(os.name == 'posix', 'Private workspace requires POSIX')
class SetupContinuityTests(unittest.TestCase):
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
        self.assigned = self.dir / 'assigned.json'
        self.assigned.write_text('{"id":"554433"}', encoding='utf-8')
        self.addCleanup(self._cleanup_state)

    def _cleanup_state(self):
        key = str(self.root.resolve())
        with control.METRICS_HUBS_LOCK:
            hub = control.METRICS_HUBS.pop(key, None)
        if hub is not None:
            hub.close()
        control.NATIVE_CLIENTS.pop(key, None)
        with control.RELAY_LOCK:
            control.RELAY_STATES.pop(key, None)

    def start_server(self, *, bind_configured_port=False):
        settings = control.config(self.root)
        port = int(settings.get('port', 0)) if bind_configured_port else 0

        class _ReuseServer(ThreadingHTTPServer):
            allow_reuse_address = True

        server = _ReuseServer(('127.0.0.1', port), control.Handler)
        server.workspace = self.root
        server.token = settings['token']
        if not bind_configured_port:
            settings['port'] = server.server_port
            workspace.atomic(self.root / 'control.json', workspace.encode(settings))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, settings

    def test_workspace_registry_remembers_init_enable_and_ignores_deleted_entries(self):
        self.assertEqual(workspace_registry.discover_workspaces(), [])
        self.assertIsNone(workspace_registry.resolve_workspace())

        workspace.init(self.root, self.assigned)
        self.assertTrue(workspace_registry.register_workspace(self.root, set_default=True))
        control.enable(self.root, 49231)

        reg_path = workspace_registry.registry_path()
        self.assertTrue(reg_path.is_file())
        self.assertEqual(reg_path.stat().st_mode & 0o777, 0o600)

        found = workspace_registry.discover_workspaces()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['plugin_id'], '554433')
        self.assertEqual(found[0]['control_port'], 49231)
        self.assertTrue(found[0]['is_default'])
        self.assertEqual(workspace_registry.resolve_workspace(), self.root.resolve())

        # setup-status finds the registered workspace even without --workspace
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = control.main(['setup-status'])
        self.assertEqual(rc, 0)
        status = json.loads(out.getvalue())
        self.assertEqual(status['workspace'], str(self.root.resolve()))
        self.assertEqual(status['plugin_id'], '554433')

        # Missing/deleted workspace entries are skipped safely
        deleted_ws = self.dir / 'deleted-ws'
        assigned_deleted = self.dir / 'deleted-assigned.json'
        assigned_deleted.write_text('{"id":"111222"}', encoding='utf-8')
        workspace.init(deleted_ws, assigned_deleted)
        self.assertTrue(workspace_registry.register_workspace(deleted_ws))
        import shutil
        shutil.rmtree(deleted_ws)
        found_after = workspace_registry.discover_workspaces()
        self.assertEqual(len(found_after), 1)
        self.assertEqual(found_after[0]['path'], str(self.root.resolve()))

    def test_enable_reports_refresh_required_accurately_and_supports_atomic_refresh(self):
        workspace.init(self.root, self.assigned)

        # Before refresh, control config is not embedded in manifest/code.js
        first = control.enable(self.root, 49232)
        self.assertTrue(first['refresh_required'])
        self.assertFalse(first['refreshed'])

        # enable --refresh refreshes once and clears refresh_required
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = control.main(['enable', '--workspace', str(self.root), '--port', '49232', '--refresh'])
        self.assertEqual(rc, 0)
        second = json.loads(out.getvalue())
        self.assertFalse(second['refresh_required'])
        self.assertTrue(second['refreshed'])

        # Subsequent enable call sees embedded config and does NOT demand refresh
        gen_before = workspace.current(self.root)['generation']
        third = control.enable(self.root, 49232, refresh=True)
        self.assertFalse(third['refresh_required'])
        self.assertFalse(third['refreshed'])
        self.assertEqual(workspace.current(self.root)['generation'], gen_before)

    def test_plugin_startup_reports_current_self_reported_when_live_server_confirms_plugin(self):
        workspace.init(self.root, self.assigned)
        control.enable(self.root, 49233, refresh=True)

        # Server offline -> loaded remains unverified and server_online is False
        offline = startup.HostAdapter().native(self.root, False)
        self.assertEqual(offline['status'], 'files-current')
        self.assertEqual(offline['loaded'], 'unverified')
        self.assertFalse(offline['server_online'])
        self.assertNotIn('Reopen', offline['action'])

        # Server online + authenticated current poll -> loaded becomes current-self-reported!
        self.start_server()
        runtime = workspace.current(self.root)['runtime']
        control.poll(self.root, {
            'session_id': 'plugin-session-live',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'runtime': runtime,
        })
        online = startup.HostAdapter().native(self.root, False)
        self.assertEqual(online['status'], 'files-current')
        self.assertEqual(online['loaded'], 'current-self-reported')
        self.assertTrue(online['server_online'])
        self.assertIsNone(online['action'])

    def test_setup_status_progression_never_asks_to_reconfigure_completed_steps(self):
        # Step 0: nothing registered
        s0 = control.setup_status()
        self.assertFalse(s0['already_configured'])
        self.assertEqual(s0['next_action'], 'init-workspace')

        # Step 1: initialize and explicitly choose the reusable PC workspace.
        workspace.init(self.root, self.assigned)
        self.assertTrue(workspace_registry.register_workspace(self.root, set_default=True))
        s1 = control.setup_status()
        self.assertTrue(s1['workspace_initialized'])
        self.assertFalse(s1['control_enabled'])
        self.assertEqual(s1['next_action'], 'enable-control')

        # Step 2: enable without refresh
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        control.enable(self.root, port)
        s2 = control.setup_status()
        self.assertTrue(s2['control_enabled'])
        self.assertFalse(s2['manifest_synced'])
        self.assertEqual(s2['next_action'], 'refresh-workspace')

        # Step 3: refresh -> already_configured is True, only start-serve needed
        workspace.refresh(self.root)
        s3 = control.setup_status()
        self.assertTrue(s3['already_configured'])
        self.assertFalse(s3['server_running'])
        self.assertEqual(s3['next_action'], 'start-serve')

        # Step 4: server running, plugin not yet connected -> reopen-plugin
        self.start_server(bind_configured_port=True)
        s4 = control.setup_status()
        self.assertTrue(s4['server_running'])
        self.assertFalse(s4['plugin_connected'])
        self.assertEqual(s4['next_action'], 'reopen-plugin')

        # Step 5: plugin connected with needsSetup=True -> confirm-profile
        runtime = workspace.current(self.root)['runtime']
        base_poll = {
            'session_id': 'plugin-session-setup',
            'file_key': 'fixturefile',
            'page_id': '12:1',
            'runtime': runtime,
            'relay': {
                'context': {
                    'session_id': 'plugin-session-setup',
                    'file_key': 'fixturefile',
                    'page_id': '12:1',
                    'user_id': 'user-1',
                    'selection': [],
                    'profile': {'declared': {'plan': 'unknown', 'seat': 'unknown'}, 'needsSetup': True, 'storage': 'local'},
                }
            },
        }
        control.poll(self.root, base_poll)
        s5 = control.setup_status()
        self.assertTrue(s5['plugin_connected'])
        self.assertFalse(s5['profile_confirmed'])
        self.assertEqual(s5['next_action'], 'confirm-profile')
        self.assertIsNotNone(s5['context_fingerprint'])

        # Step 6: profile confirmed -> ready_for_work is True and setup-status leaves workspace untouched
        saved_poll = {
            **base_poll,
            'relay': {
                'context': {
                    **base_poll['relay']['context'],
                    'profile': {'declared': {'plan': 'unknown', 'seat': 'unknown'}, 'needsSetup': False, 'storage': 'local'},
                }
            },
        }
        control.poll(self.root, saved_poll)
        before_files = {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob('*')) if p.is_file()}
        s6 = control.setup_status()
        after_files = {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob('*')) if p.is_file()}
        self.assertEqual(before_files, after_files)
        self.assertTrue(s6['ready_for_work'])
        self.assertEqual(s6['next_action'], 'ready')
        self.assertIsNone(s6['next_command'])


if __name__ == '__main__':
    unittest.main()
