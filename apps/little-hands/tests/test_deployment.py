"""Packaging contract checks, independent of Django and a running database."""
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_direct_requirements_are_locked_with_hashes(self):
        lock = (ROOT / 'requirements.lock').read_text()
        records = lock.replace('\\\n', '').splitlines()
        pins = {}
        for record in records:
            if not record or record.startswith('#'):
                continue
            match = re.match(r'([\w-]+)==([\w.]+)\s+--hash=sha256:[0-9a-f]{64}', record)
            self.assertIsNotNone(match, record)
            pins[match[1].lower()] = match[2]
        for requirement in (ROOT / 'requirements.txt').read_text().splitlines():
            name, version = requirement.split('==')
            self.assertEqual(pins[name.split('[')[0].lower()], version)
        self.assertIn('psycopg-binary', pins)

    def test_container_and_proxy_boundaries(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        compose = (ROOT / 'compose.yaml').read_text()
        self.assertRegex(dockerfile, r'FROM python:3\.13[^\n]+@sha256:[a-f0-9]{64}')
        self.assertRegex(compose, r'image: postgres:17[^\n]+@sha256:[a-f0-9]{64}')
        self.assertIn('USER 10001:10001', dockerfile)
        self.assertIn('--no-control-socket', dockerfile)
        self.assertIn('networks: [backend, ingress]', compose)
        self.assertIn('--require-hashes --only-binary=:all:', dockerfile)
        self.assertNotIn('COPY . ', dockerfile)
        self.assertIn('127.0.0.1:${LH_HTTP_PORT:-8870}:8000', compose)
        self.assertIn('read_only: true', compose)
        self.assertNotIn('5432:5432', compose)
        self.assertIn('LH_DB_PASSWORD_FILE', compose)
        ignored = (ROOT / '.dockerignore').read_text()
        for private in ('**/.env', '**/.venv', '**/captures', '**/private', '**/*.dump'):
            self.assertIn(private, ignored)
        proxy = (ROOT / 'deploy/nginx.conf.example').read_text()
        self.assertIn('proxy_set_header X-Forwarded-Proto https;', proxy)
        self.assertIn('proxy_set_header X-Forwarded-For $remote_addr;', proxy)

    def test_runtime_has_no_migration_or_journal_mutation_grants(self):
        sql = (ROOT / 'deploy/grants.sql').read_text()
        self.assertIn('REVOKE ALL ON django_migrations FROM littlehands_runtime;', sql)
        self.assertIn('REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON booking_auditevent, booking_operation', sql)
        self.assertNotIn('ALL PRIVILEGES', sql)
        self.assertNotIn('ALTER DEFAULT PRIVILEGES', sql)
        roles = (ROOT / 'deploy/roles.sql').read_text()
        self.assertEqual(roles.count('NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION'), 2)
        self.assertIn('REVOKE ALL ON SCHEMA public FROM PUBLIC', roles)

    def test_secret_loader_passes_value_without_command_line_exposure(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / 'secret'
            secret.write_text(secrets.token_urlsafe(48) + '\n')
            import os
            env = dict(os.environ, LH_DB_PASSWORD_FILE=str(secret))
            env.pop('LH_DB_PASSWORD', None)
            command = [sys.executable, str(ROOT / 'deploy/entrypoint.py'), sys.executable,
                       '-c', 'import os; from pathlib import Path; assert os.environ["LH_DB_PASSWORD"] == Path(os.environ["LH_DB_PASSWORD_FILE"]).read_text().rstrip()']
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            env['LH_DB_PASSWORD'] = secrets.token_urlsafe(48)
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(env['LH_DB_PASSWORD'], result.stderr)


if __name__ == '__main__':
    unittest.main()
