"""Use the shipped migrations, forms, views and services against a private PostgreSQL cluster."""
import json
import os
import socket
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1] / 'apps/little-hands'


class BookingDatabaseReleaseTests(unittest.TestCase):
    def test_application_transactions_permissions_and_deployment_checks(self):
        pg = os.environ.get('FIGMA_FLOW_PG_BIN')
        initdb = shutil.which('initdb', path=pg) if pg else shutil.which('initdb')
        if not initdb:
            self.skipTest('Supply PostgreSQL server tools on PATH or with FIGMA_FLOW_PG_BIN')
        tools = Path(initdb).parent
        python = os.environ.get('FIGMA_FLOW_BOOKING_PYTHON', sys.executable)
        if subprocess.run([python, '-c', 'import django, psycopg, axes'], capture_output=True).returncode:
            self.skipTest('Install the booking application lockfile into the witness interpreter')
        # A unique directory selects the socket. No TCP listener or shared database is used.
        with tempfile.TemporaryDirectory(prefix='lh-pg-') as tmp:
            root = Path(tmp)
            data, log = root / 'db', root / 'postgres.log'
            common = dict(cwd=root, capture_output=True, text=True, timeout=95)

            def run(command, **kwargs):
                result = subprocess.run(command, **(common | kwargs))
                self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
                return result

            run([initdb, '-D', data, '--no-locale', '-E', 'UTF8', '-A', 'trust', '-U', 'fixture'])
            run([tools / 'pg_ctl', '-D', data, '-l', log, '-w', 'start',
                 '-o', f"-c listen_addresses='' -c unix_socket_directories='{root}'"])
            try:
                env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1','LH_DB_NAME':'postgres',
                       'LH_DB_USER':'fixture','LH_DB_HOST':str(root),'LH_DB_PORT':'5432',
                       'LH_SECRET_KEY':secrets.token_urlsafe(60),'LH_ENV':'staging',
                       'LH_ALLOWED_HOSTS':'localhost,127.0.0.1,testserver','LH_SITE_URL':'http://localhost'}
                for args in (['check'], ['makemigrations', '--check', '--dry-run'],
                             ['test','booking.tests','config.tests','--verbosity','1','--noinput']):
                    result = run([python,'-B','manage.py',*args],cwd=APP,env=env)
                self.assertRegex(result.stderr + result.stdout, r'Ran [1-9][0-9]+ tests')
                self.assertNotIn('skipped=', result.stderr + result.stdout)
                run([python,'-B','-m','unittest','discover','-s','tests'],cwd=APP,env=env)
                app=root/'app'
                for directory in ('booking','config','static','templates','deploy'):
                    shutil.copytree(APP/directory,app/directory,ignore=shutil.ignore_patterns('__pycache__'))
                (app/'design').mkdir()
                for name in ('export.py','publish_copy.py','session-detail.html.in'):
                    shutil.copyfile(APP/'design'/name,app/'design'/name)
                shutil.copyfile(APP/'manage.py',app/'manage.py')
                run([python,'-B','design/publish_copy.py'], cwd=app)
                product_path=app/'booking/product.json'
                product=json.loads(product_path.read_bytes())
                product.update(serviceName='Fixture Workshop', paymentDisclosure='Fixture on-site payment.')
                product_path.write_text(json.dumps(product))
                stale=subprocess.run([python,'-B','design/publish_copy.py'],cwd=app,capture_output=True)
                self.assertNotEqual(stale.returncode,0)
                run([python,'-B','design/publish_copy.py','--write'],cwd=app)
                run([python,'-B','design/publish_copy.py'],cwd=app)
                policy_path=app/'config/deployment.json'
                policy=json.loads(policy_path.read_bytes())
                db=policy['database']
                connect=['-X','-v','ON_ERROR_STOP=1','-h',str(root),'-U','fixture']
                run([tools/'createdb','-h',root,'-U','fixture',db['name']])
                private=root/'secrets'
                private.mkdir(mode=0o700)
                for key in ('ownerFile','runtimeFile'):
                    (private/policy['secrets'][key]).write_text(secrets.token_urlsafe(30))
                env.update(LH_DB_SECRET_DIRECTORY=str(private),LH_DB_NAME=db['name'],LH_DB_USER=db['owner'],
                           LH_FIXTURE_MEMBER_PASSWORD=secrets.token_urlsafe(20),LH_FIXTURE_STAFF_PASSWORD=secrets.token_urlsafe(20))
                run([tools/'psql',*connect,'-d',db['name'],'-f',app/'deploy/roles.sql'],env=env)
                for args in (['migrate','--noinput'],['collectstatic','--noinput'],['seed_staging']):
                    run([python,'-B','manage.py',*args],cwd=app,env=env)
                run([tools/'psql',*connect,'-d',db['name'],'-f',app/'deploy/grants.sql'],env=env)
                run([tools/'psql','-X','-h',root,'-U',db['runtime'],'-d',db['name'],'-f',app/'deploy/verify.sql'],env=env)
                env['LH_DB_USER']=db['runtime']
                run([python,'-B','design/export.py','--out',root/'export'],cwd=app,env=env)
                pages=list((root/'export').rglob('*.html'))
                self.assertGreater(len(pages),10)
                self.assertTrue(any('data-export-only' in page.read_text() for page in pages))
                html='\n'.join(page.read_text() for page in pages)
                self.assertIn('Fixture Workshop',html)
                self.assertIn('Fixture on-site payment.',html)
                self.assertNotIn('작은손 커피공방',html)

                with socket.socket() as listener:
                    listener.bind(('127.0.0.1',0))
                    listener.listen()
                    policy['web']['internalPort']=listener.getsockname()[1]
                    policy_path.write_text(json.dumps(policy))
                    run([python,'-B','deploy/publish_config.py','--write'],cwd=app,env=env)
                    self.assertIn(f"EXPOSE {policy['web']['internalPort']}",(app/'Dockerfile').read_text())
                    self.assertIn(f":{policy['web']['internalPort']}\"", (app/'compose.yaml').read_text())
                    proc=subprocess.Popen([python,'-B','-m','gunicorn','config.wsgi:application',
                                           '--bind',f'fd://{listener.fileno()}','--workers','1'],
                                          cwd=app,env=env,pass_fds=(listener.fileno(),),
                                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    try:
                        run([python,'-B','deploy/healthcheck.py'],cwd=app,env=env)
                    finally:
                        proc.terminate()
                        proc.wait(timeout=15)
            finally:
                run([tools / 'pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop'])


if __name__ == '__main__':
    unittest.main()
