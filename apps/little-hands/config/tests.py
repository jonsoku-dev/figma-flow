import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from config.middleware import ResponsePolicyMiddleware
from config import context as service_context_module
from config.context import verified_design_system_graph_sha
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

    def test_design_system_sha_requires_paired_source_and_collected_assets(self):
        from django.conf import settings
        from django.contrib.staticfiles.storage import staticfiles_storage
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for logical in ('littlehands/design-system.css', 'littlehands/design-system.js'):
                source = settings.BASE_DIR / 'static' / logical
                target = root / logical
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            with self.settings(STATIC_ROOT=root), patch.object(staticfiles_storage, 'stored_name', side_effect=lambda name: name):
                service_context_module._VERIFIED_DESIGN_SYSTEM = None
                self.assertRegex(verified_design_system_graph_sha(), r'^[0-9a-f]{64}$')
                (root / 'littlehands/design-system.css').write_text('stale', encoding='utf-8')
                service_context_module._VERIFIED_DESIGN_SYSTEM = None
                with self.assertRaisesRegex(RuntimeError, 'Collected static asset does not match'):
                    verified_design_system_graph_sha()
                service_context_module._VERIFIED_DESIGN_SYSTEM = None
