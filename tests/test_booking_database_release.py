"""Run the shipped app against an explicitly provisioned MySQL 8.4 test server."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1] / 'apps/little-hands'


def statements(path):
    return [sql.strip() for sql in path.read_text().split(';') if sql.strip()]


class BookingDatabaseReleaseTests(unittest.TestCase):
    def test_application_transactions_permissions_and_deployment_checks(self):
        host = os.environ.get('FIGMA_FLOW_MYSQL_TEST_HOST')
        if not host:
            self.skipTest('Set FIGMA_FLOW_MYSQL_TEST_HOST for the dedicated MySQL 8.4 fixture server')
        import MySQLdb

        port = int(os.environ['FIGMA_FLOW_MYSQL_TEST_PORT'])
        user = os.environ.get('FIGMA_FLOW_MYSQL_TEST_USER', 'root')
        password = os.environ['FIGMA_FLOW_MYSQL_TEST_PASSWORD']
        admin = MySQLdb.connect(host=host, port=port, user=user, password=password, autocommit=True,
                                  connection_timeout=10)
        self.addCleanup(admin.close)
        self.assertEqual(admin.get_server_info().split('.')[:2], ['8', '4'])

        suffix = secrets.token_hex(6)
        name, owner, runtime = (f'lh_{role}_{suffix}' for role in ('test', 'owner', 'web'))
        owner_password, web_password = secrets.token_urlsafe(36), secrets.token_urlsafe(36)

        def execute(sql, connection=admin):
            with connection.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall() if cursor.description else None

        execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs')
        self.addCleanup(execute, f'DROP DATABASE IF EXISTS `{name}`')
        self.addCleanup(execute, f"DROP USER IF EXISTS '{owner}'@'%', '{runtime}'@'%'")

        with tempfile.TemporaryDirectory(prefix='lh-mysql-witness-') as temp:
            root = Path(temp)
            app = root/'app'
            for directory in ('booking', 'config', 'static', 'templates', 'deploy', 'tests'):
                shutil.copytree(APP/directory, app/directory, ignore=shutil.ignore_patterns('__pycache__'))
            (app/'design').mkdir()
            for filename in ('export.py', 'publish_copy.py', 'session-detail.html.in'):
                shutil.copyfile(APP/'design'/filename, app/'design'/filename)
            shutil.copyfile(APP/'manage.py', app/'manage.py')

            python = os.environ.get('FIGMA_FLOW_BOOKING_PYTHON', sys.executable)
            env = {key: value for key, value in os.environ.items() if not key.startswith('LH_')}
            env.update(PYTHONDONTWRITEBYTECODE='1', LH_ENV='staging', LH_SECRET_KEY=secrets.token_urlsafe(60),
                       LH_ALLOWED_HOSTS='localhost,127.0.0.1,testserver', LH_SITE_URL='http://localhost',
                       LH_DB_HOST=host, LH_DB_PORT=str(port), LH_DB_NAME=name, LH_DB_USER=user, LH_DB_PASSWORD=password,
                       LH_FIXTURE_MEMBER_PASSWORD=secrets.token_urlsafe(24),
                       LH_FIXTURE_STAFF_PASSWORD=secrets.token_urlsafe(24))

            def run(*argv, check=True):
                result = subprocess.run([python, '-B', *argv], cwd=app, env=env, capture_output=True,
                                        text=True, timeout=100)
                if check:
                    self.assertEqual(result.returncode, 0, result.stdout[-1800:] + result.stderr[-1800:])
                return result

            # These tests create and remove Django's uniquely named test schema.
            for args in (['check'], ['makemigrations', '--check', '--dry-run'],
                         ['test', 'booking.tests', 'config.tests', '--verbosity', '1', '--noinput']):
                result = run('manage.py', *args)
            self.assertRegex(result.stderr + result.stdout, r'Ran [1-9][0-9]+ tests')
            self.assertNotIn('skipped=', result.stderr + result.stdout)
            # Deployment tests read the shipped filenames and contain no database I/O.
            self.assertEqual(subprocess.run([python, '-B', '-m', 'unittest', 'discover', '-s', 'tests'],
                                            cwd=APP, env=env, capture_output=True).returncode, 0)

            product_path = app/'booking/product.json'
            product = json.loads(product_path.read_bytes())
            product.update(serviceName='Fixture Workshop', paymentDisclosure='Fixture on-site payment.')
            product_path.write_text(json.dumps(product))
            self.assertNotEqual(run('design/publish_copy.py', check=False).returncode, 0)
            run('design/publish_copy.py', '--write')
            run('design/publish_copy.py')

            policy_path = app/'config/deployment.json'
            policy = json.loads(policy_path.read_bytes())
            policy['database'].update(name=name, owner=owner, runtime=runtime)
            policy_path.write_text(json.dumps(policy))
            run('deploy/publish_config.py', '--write')
            for sql in statements(app/'deploy/roles.sql'):
                execute(sql.replace('__LH_OWNER_PASSWORD__', owner_password).replace('__LH_RUNTIME_PASSWORD__', web_password))
            env.update(LH_DB_USER=owner, LH_DB_PASSWORD=owner_password)
            for args in (['migrate', '--noinput'], ['collectstatic', '--noinput'], ['seed_staging']):
                run('manage.py', *args)
            for sql in statements(app/'deploy/grants.sql'):
                execute(sql)
            for sql in statements(app/'deploy/verify.sql'):
                results = execute(sql)
                self.assertTrue(results)
                self.assertEqual({key: count for key, count in results if count}, {})

            web = MySQLdb.connect(host=host, port=port, database=name, user=runtime, password=web_password)
            self.addCleanup(web.close)
            with web:
                self.assertIsNotNone(execute('SELECT COUNT(*) FROM booking_booking', web))
                execute("INSERT INTO auth_group (name) VALUES ('Fixture operations admin')", web)
                self.assertEqual(execute("SELECT COUNT(*) FROM auth_group WHERE name = 'Fixture operations admin'", web), ((1,),))
                for sql in (
                    'UPDATE booking_auditevent SET created_at = UTC_TIMESTAMP()',
                    'DELETE FROM booking_operation',
                    'SELECT * FROM django_migrations',
                    'DELETE FROM booking_roomscheduleentry',
                ):
                    with self.assertRaises(MySQLdb.DatabaseError) as error:
                        execute(sql, web)
                    self.assertEqual(error.exception.args[0], 1142)

            env.update(LH_DB_USER=runtime, LH_DB_PASSWORD=web_password)
            run('design/export.py', '--out', str(root/'export'))
            pages = list((root/'export').rglob('*.html'))
            self.assertGreater(len(pages), 10)
            html = '\n'.join(page.read_text() for page in pages)
            self.assertIn('data-export-only', html)
            self.assertIn('Fixture Workshop', html)
            self.assertIn('Fixture on-site payment.', html)
            self.assertNotIn('작은손 커피공방', html)

            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen()
                policy['web']['internalPort'] = listener.getsockname()[1]
                policy_path.write_text(json.dumps(policy))
                run('deploy/publish_config.py', '--write')
                self.assertIn(f"EXPOSE {policy['web']['internalPort']}", (app/'Dockerfile').read_text())
                self.assertIn(f":{policy['web']['internalPort']}\"", (app/'compose.yaml').read_text())
                proc = subprocess.Popen([python, '-B', '-m', 'gunicorn', 'config.wsgi:application',
                                         '--bind', f'fd://{listener.fileno()}', '--workers', '1'],
                                        cwd=app, env=env, pass_fds=(listener.fileno(),),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    run('deploy/healthcheck.py')
                finally:
                    proc.terminate()
                    proc.wait(timeout=15)


if __name__ == '__main__':
    unittest.main()
