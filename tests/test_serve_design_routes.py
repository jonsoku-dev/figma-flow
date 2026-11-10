import contextlib
import http.client
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import route_design
import serve_design_routes as app


class DesignRoutesServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.create_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method='GET', path='/', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def post(self, payload, headers=None):
        return self.request('POST', '/plan', json.dumps(payload, ensure_ascii=False).encode(),
                            {'Content-Type': 'application/json', **(headers or {})})

    def test_loopback_offline_page_and_paths(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertIn('디자인 라우팅', body.decode())
        self.assertIn('connect-src \'self\'', headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(b'innerHTML', body)
        self.assertNotIn(b'<script src=', body)
        self.assertNotIn(b'<link ', body)
        self.assertEqual(self.request(path='/library/design-routes.json')[0], 404)
        self.assertEqual(self.request(path='/../route_design.py')[0], 404)

    def test_plan_matches_exact_shared_router_and_context(self):
        prompt = '한국·일본 출시 cinematic key art 생성. KR JP typography'
        context = 'bold graphic logo. illustrated collectible 굿즈 생성'
        expected = route_design.route(prompt, self.server.registry, self.server.campaign_data, context)
        with patch.object(app.route_design, 'route', wraps=route_design.route) as shared:
            status, _, body = self.post({'prompt': prompt, 'context': context})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), expected)
        shared.assert_called_once_with(prompt, registry=self.server.registry,
                                       campaign_data=self.server.campaign_data, context=context)
        self.assertTrue(expected['campaign_plans'])
        self.assertEqual(self.post({'prompt': '로고 제작'})[0], 200)

    def test_research_preservation_and_no_generation(self):
        status, _, body = self.post({'prompt': 'Research only: 폰트 유지. 이미지 생성 없이. 모션 제외.'})
        self.assertEqual(status, 200)
        plan = json.loads(body)
        self.assertEqual(plan['mode'], 'research')
        self.assertEqual(plan['constraints']['image_generation'], 'excluded')
        self.assertEqual(plan['constraints']['font_policy'], 'preserve')
        self.assertFalse({'images', 'typography', 'motion'} & {row['id'] for row in plan['routes']})

    def test_input_boundaries(self):
        for payload in ([], {}, {'prompt': ''}, {'prompt': 1}, {'prompt': 'x', 'context': []},
                        {'prompt': 'x', 'extra': True}, {'prompt': 'x' * (app.MAX_TEXT + 1)},
                        {'prompt': 'x', 'context': 'x' * (app.MAX_TEXT + 1)}):
            with self.subTest(payload_type=type(payload)):
                self.assertEqual(self.post(payload)[0], 400)
        self.assertEqual(self.request('POST', '/plan', '{', {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.request('POST', '/plan', b'\xff', {'Content-Type': 'application/json'})[0], 400)
        # A lone surrogate is valid JSON but not encodable text: answer 400 instead of dropping the connection.
        for body in (b'{"prompt": "\\ud800"}', b'{"prompt": "x", "context": "\\ud800"}'):
            self.assertEqual(self.request('POST', '/plan', body, {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.request('POST', '/plan', '{}')[0], 415)
        # Reject oversized headers before any body upload can race the server's connection close.
        with patch.object(app.route_design, 'route', wraps=route_design.route) as shared:
            for length in (str(app.MAX_BODY + 1), '9' * 5000):
                with self.subTest(content_length_digits=len(length)):
                    status, headers, body = self.request('POST', '/plan', headers={
                        'Content-Type': 'application/json', 'Content-Length': length})
                    self.assertEqual(status, 413)
                    self.assertEqual(json.loads(body), {'error': '요청 크기 제한을 초과했습니다.'})
                    self.assertEqual(int(headers['Content-Length']), len(body))
            shared.assert_not_called()

    def test_rejects_remote_host_and_origin_without_logging_prompt(self):
        secret = 'PRIVATE_PROMPT_SENTINEL'
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(self.post({'prompt': secret}, {'Origin': 'https://example.com'})[0], 403)
            self.assertEqual(self.post({'prompt': secret}, {'Host': 'example.com'})[0], 403)
            self.assertEqual(self.post({'prompt': secret}, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
            self.assertEqual(self.post({'prompt': secret})[0], 200)
        self.assertNotIn(secret, errors.getvalue())
        self.assertEqual(errors.getvalue(), '')
        origin = f'http://127.0.0.1:{self.server.server_port}'
        self.assertEqual(self.post({'prompt': '로고'}, {'Origin': origin})[0], 200)

    def test_cli_port_option(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/serve_design_routes.py'), '--port', '-1'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--port must be', result.stderr)


if __name__ == '__main__':
    unittest.main()
