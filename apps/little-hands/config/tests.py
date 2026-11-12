import os
from pathlib import Path
import subprocess
import sys

from django.test import RequestFactory, SimpleTestCase

from config.middleware import ResponsePolicyMiddleware
from django.http import HttpResponse


class ConfigurationTests(SimpleTestCase):
    def setting_process(self, **values):
        env = {**os.environ, 'LH_ENV':'production', 'LH_SECRET_KEY':'a-production-test-secret-with-enough-distinct-characters-0123456789',
               'LH_ALLOWED_HOSTS':'studio.example.test', 'LH_SITE_URL':'https://studio.example.test', **values}
        return subprocess.run([sys.executable, '-c', 'import config.settings as s; assert not s.DEBUG; assert s.SESSION_COOKIE_SECURE; assert s.CSRF_COOKIE_SECURE; assert s.SECURE_SSL_REDIRECT'],
                              cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)

    def test_production_security_defaults_and_exact_hosts(self):
        self.assertEqual(self.setting_process().returncode, 0)
        for hosts in ['*', '.example.test', '*.example.test']:
            self.assertNotEqual(self.setting_process(LH_ALLOWED_HOSTS=hosts).returncode, 0)

    def test_production_rejects_insecure_or_mismatched_origin_and_secret(self):
        for values in [{'LH_SITE_URL':'http://studio.example.test'}, {'LH_SITE_URL':'https://other.example.test'}, {'LH_SECRET_KEY':'short'}]:
            self.assertNotEqual(self.setting_process(**values).returncode, 0)

    def test_response_policy_does_not_require_authentication_or_database(self):
        response = ResponsePolicyMiddleware(lambda request:HttpResponse('ok'))(RequestFactory().get('/health/'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])
        self.assertNotIn('unsafe-inline', response['Content-Security-Policy'])
        self.assertIn('camera=()', response['Permissions-Policy'])
