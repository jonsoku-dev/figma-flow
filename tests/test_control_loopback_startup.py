"""The registered local relay must become ready without resolving a host name."""
import json
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import figma_control as control
import figma_workspace as workspace
import local_endpoint


class LoopbackStartupTests(unittest.TestCase):
    def test_serve_is_ready_without_reverse_dns(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / 'workspace'
            assigned = Path(name) / 'assigned.json'
            assigned.write_text('{"id":"12345"}')
            workspace.init(root, assigned)
            with socket.socket() as sock:
                sock.bind((local_endpoint.BIND_HOST, 0))
                port = sock.getsockname()[1]
            control.enable(root, port)
            # Run the real CLI with just its reverse lookup unavailable.
            worker = """import runpy, socket, sys
from pathlib import Path
from unittest.mock import patch
script = Path(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, str(script.parent))
with patch.object(socket, 'getfqdn', side_effect=RuntimeError('unexpected reverse lookup')):
    runpy.run_path(str(script), run_name='__main__')
"""
            args = [sys.executable, '-B', '-c', worker, str(TOOLS/'figma_control.py'),
                    'serve', '--workspace', str(root)]
            with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
                try:
                    self.assertTrue(select.select([process.stdout], [], [], 20)[0])
                    line = process.stdout.readline()
                    self.assertTrue(line, 'control must serve without reverse DNS')
                    self.assertEqual(json.loads(line), {'serving': True, 'port': port})
                    settings = control.config(root)
                    reply = local_endpoint.request(port, settings['token'], 'POST', local_endpoint.READINESS_ROUTE,
                                                   b'{}', limit=control.MAX_READINESS)
                    self.assertEqual(reply.status, 200)
                    self.assertEqual(json.loads(reply.body)['implementation'], control.LOADED_IMPLEMENTATION)
                finally:
                    process.terminate()
                    process.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
