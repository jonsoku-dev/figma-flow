"""Check the rendered Compose, nginx, build context and staging-only resource selection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1] / 'apps/little-hands'


class BookingDeploymentFilesTests(unittest.TestCase):
    def test_changed_private_endpoints_reach_compose_proxy_and_built_image(self):
        if not shutil.which('docker'):
            self.skipTest('Docker Compose CLI required to resolve native configuration')
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)
            for name in ('config','deploy'):
                shutil.copytree(APP/name,app/name,ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('Dockerfile','compose.yaml','.dockerignore','.gitignore'):
                shutil.copyfile(APP/name,app/name)
            def command(*argv,**kw):
                return subprocess.run(list(argv),cwd=app,capture_output=True,text=True,timeout=20,**kw)
            generator=[sys.executable,'-B','deploy/publish_config.py']
            command(*generator,check=True)
            path=app/'config/deployment.json'
            contract=json.loads(path.read_bytes())
            contract['web'].update(internalPort=18407,hostPort=18917)
            contract['database'].update(name='workshop',runtime='workshop_web',owner='workshop_migrate')
            path.write_text(json.dumps(contract))
            self.assertNotEqual(command(*generator).returncode,0)
            command(*generator,'--write',check=True)
            secrets=app/'secrets';secrets.mkdir()
            env={**os.environ,'LH_SECRETS_DIR':str(secrets),'LH_ALLOWED_HOSTS':'localhost','LH_SITE_URL':'https://localhost'}
            env.pop('LH_HTTP_PORT',None)
            result=command('docker','compose','--profile','tools','config','--format','json',env=env,check=True)
            services=json.loads(result.stdout)['services']
            port,=services['web']['ports']
            self.assertEqual((port['host_ip'],int(port['published']),port['target']),('127.0.0.1',18917,18407))
            self.assertEqual(services['web']['environment']['LH_DB_USER'],'workshop_web')
            self.assertEqual(services['migrate']['environment']['LH_DB_USER'],'workshop_migrate')
            self.assertEqual(services['db']['environment']['MYSQL_DATABASE'],'workshop')
            self.assertEqual(services['db']['image'], contract['database']['image'])
            self.assertNotIn('ports', services['db'])
            self.assertIn('127.0.0.1:18917',(app/'deploy/nginx.conf.example').read_text())
            dockerfile=(app/'Dockerfile').read_text()
            self.assertIn('EXPOSE 18407',dockerfile)
            self.assertIn('--bind=0.0.0.0:18407',dockerfile)
            self.assertIn('workshop_web',(app/'deploy/grants.sql').read_text())
            self.assertIn('workshop_migrate',(app/'deploy/roles.sql').read_text())
            command('git','init','-q',check=True)
            for name in ('.env','.venv/runtime','design/fonts/metric.ttf','design/reviews/report.json','cache.pyc'):
                self.assertEqual(command('git','check-ignore','--no-index','-q',name).returncode,0,name)
            self.assertEqual(command('git','check-ignore','--no-index','-q','templates/base.html').returncode,1)
            excluded=set((app/'.dockerignore').read_text().splitlines())
            self.assertTrue({'**/.env','**/.venv','design','tests','staticfiles','.secrets'} <= excluded)
            copies=[line.split()[1:-1] for line in dockerfile.splitlines() if line.startswith('COPY ')]
            self.assertFalse(any(source in ('.','./','design/','.env','.secrets/') for row in copies for source in row))
            self.assertIn(['booking/'],copies)
            self.assertIn(['static/'],copies)


if __name__=='__main__':
    unittest.main()
