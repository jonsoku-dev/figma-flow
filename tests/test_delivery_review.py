"""Behavior witnesses for the release configuration as installed from a source ZIP."""
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import delivery_config as delivery


def run(cwd, *args, **options):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, **options)


def block(source, marker):
    """Read a literal run/env block without evaluating GitHub expression syntax."""
    lines = source.splitlines()
    index = next(i for i, line in enumerate(lines) if line.strip() == marker)
    indent = len(lines[index]) - len(lines[index].lstrip())
    result = []
    for line in lines[index + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        result.append(line[indent + 2:])
    return '\n'.join(result)


class DeliveryReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.graph = json.loads((ROOT/delivery.GRAPH).read_bytes())

    def copy_graph(self):
        for name in ('library/delivery', '.github/workflows', '.agents/plugins'):
            shutil.copytree(ROOT/name, self.tmp/name)
        for name in ('plugin.json', self.graph['inputs']['typescript']['source'],
                     self.graph['inputs']['appCi']['deploymentSource']):
            target = self.tmp/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name,target)

    def test_marketplace_uses_local_product_identity_and_preserves_fork_policy(self):
        self.copy_graph()
        path, original = delivery.marketplace(self.tmp)
        self.assertEqual(json.loads(path.read_bytes()), original)
        original['name'] = 'company-market'
        original['plugins'][0]['policy']['installation'] = 'CUSTOM'
        path.write_text(json.dumps(original))
        product_path = self.tmp/'plugin.json'
        product = json.loads(product_path.read_bytes())
        product['name'] = 'new-flow'
        product['extensions']['com.openai']['interface']['category'] = 'Design'
        product_path.write_text(json.dumps(product))
        self.assertIn('.agents/plugins/marketplace.json', delivery.check(self.tmp))
        _, synchronized = delivery.marketplace(self.tmp)
        self.assertEqual(synchronized['name'],'company-market')
        updated = synchronized['plugins'][0]
        self.assertEqual((updated['name'],updated['category']),('new-flow','Design'))
        self.assertEqual(updated['source'],{'source':'local','path':'./'})
        self.assertEqual(updated['policy'], original['plugins'][0]['policy'])

    def test_git_checkout_preserves_upstream_bytes_and_normalizes_ordinary_text(self):
        shutil.copyfile(ROOT/'.gitattributes',self.tmp/'.gitattributes')
        run(self.tmp,'git','init','-q',check=True)
        data = b'first line\r\nsecond line\r\n'
        for name in ('upstream.txt','library/figma-api/plugin-api.d.ts','vendor/skills/unslop/SKILL.md',
                     'library/figma-widget/api.d.ts','library/figma-rest/LICENSE'):
            path=self.tmp/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
            run(self.tmp,'git','-c','core.autocrlf=input','add','--',name,check=True)
            actual=subprocess.check_output(['git','show',':'+name],cwd=self.tmp)
            self.assertEqual(actual, data.replace(b'\r\n',b'\n') if name=='upstream.txt' else data)
        for name in ('library/figma-api/plugin-api.d.ts','vendor/skills/impeccable/SKILL.md',
                     'vendor/skills/design-taste-frontend/SKILL.md','vendor/skills/unslop/SKILL.md','library/figma-widget/api.d.ts'):
            attr=run(self.tmp,'git','check-attr','whitespace','--',name,check=True)
            self.assertTrue(attr.stdout.rstrip().endswith('unset'),name)
        for name in ('library/figma-api/upstream-package.json','library/figma-widget/upstream-package.json',
                     'library/figma-api/LICENSE','library/figma-widget/LICENSE','library/figma-rest/LICENSE'):
            self.assertTrue(run(self.tmp,'git','check-attr','text','--',name,check=True).stdout.rstrip().endswith('unset'),name)

    def test_git_and_npm_keep_local_state_and_lock_files_out_of_distribution(self):
        for name in ('.gitignore','.npmrc'):
            shutil.copyfile(ROOT/name,self.tmp/name)
        run(self.tmp,'git','init','-q',check=True)
        for path in ('.figma-flow/workspace/control.json','.codex/config.toml','app/.env.production',
                     'nested/package-lock.json','node_modules/p/index.js','.references/input.zip',
                     'evidence/raw.json','figma-flow-plugin-1.0.0.zip','magicuidesign-source.zip','tmp/scratch',
                     'pkg/__pycache__/cache','pkg/a.pyc','.DS_Store','env/.venv/bin/tool',
                     'pkg/npm-shrinkwrap.json','pkg/pnpm-lock.yaml','pkg/yarn.lock','pkg/bun.lock','pkg/bun.lockb',
                     '.env','.herdr/a','.private/a','private/a','.local/a','_references/a','reference-zips/a',
                     'local-reference/a','scratch/a','.tmp/a','captures/a','receipts/a','a.tmp','a.bak','a.orig',
                     'a.sha256','release.tar','magicuidesign-sample/a'):
            self.assertEqual(run(self.tmp,'git','check-ignore','-q','--no-index',path).returncode,0,path)
        for path in ('app/.env.example','release/authority.json','specs/codex-relay/graph.json'):
            self.assertEqual(run(self.tmp,'git','check-ignore','-q','--no-index',path).returncode,1,path)
        (self.tmp/'package.json').write_text('{"name":"delivery-probe","version":"0.0.1","private":true}')
        env={k:v for k,v in os.environ.items() if not k.lower().startswith('npm_config_')}
        env.update(npm_config_userconfig=os.devnull,npm_config_cache=str(self.tmp/'cache'))
        self.assertEqual(run(self.tmp,'npm','config','get','package-lock',env=env,check=True).stdout.strip(),'false')
        run(self.tmp,'npm','install','--offline','--no-audit','--no-fund','--ignore-scripts',env=env,check=True)
        self.assertFalse((self.tmp/'package-lock.json').exists())

    def test_optional_requirements_resolve_compatible_packages_without_network(self):
        requirements = ROOT/'requirements-optional.txt'
        wheels = self.tmp/'wheels'
        wheels.mkdir()
        versions={}
        for line in requirements.read_text().splitlines():
            match=re.fullmatch(r'([A-Za-z0-9-]+)(?:\[([a-z]+)\])?>=([0-9.]+),<(\d+)',line)
            self.assertIsNotNone(match,line)
            package,extra,low,high=match.groups()
            versions[package.lower()]=low
            for version in (low,high+'.0'):
                dist=package.replace('-','_')
                meta=f'{dist}-{version}.dist-info'
                with zipfile.ZipFile(wheels/f'{dist}-{version}-py3-none-any.whl','w') as z:
                    info=f'Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n'
                    z.writestr(meta+'/METADATA', info+(f'Provides-Extra: {extra}\n' if extra else ''))
                    z.writestr(meta+'/WHEEL','Wheel-Version: 1.0\nGenerator: delivery-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
                    z.writestr(meta+'/RECORD','')
        self.assertEqual(set(versions),{'networkx','pillow','fonttools','tinycss2'})
        def resolve(dest):
            return run(self.tmp,sys.executable,'-m','pip','--isolated','--disable-pip-version-check','download',
                       '--no-index','--no-deps','--no-cache-dir','--find-links',str(wheels),
                       '--dest',str(dest),'-r',str(requirements))
        dest=self.tmp/'allowed'
        resolved=resolve(dest)
        self.assertEqual(resolved.returncode,0,resolved.stderr)
        self.assertEqual({p.name.lower().split('-')[0]:p.name.split('-')[1] for p in dest.iterdir()},versions)
        next(wheels.glob('networkx-'+versions['networkx']+'-*')).unlink()
        self.assertNotEqual(resolve(self.tmp/'rejected').returncode,0)

    def test_ci_pins_and_node_selection_follow_their_declared_sources(self):
        self.copy_graph()
        self.assertFalse(delivery.check(self.tmp))
        node_file=self.graph['inputs']['nodeVersionFile']
        self.assertRegex((ROOT/node_file).read_text().strip(),r'^\d+\.\d+\.\d+$')
        config_path=self.tmp/delivery.GRAPH
        self.graph['inputs']['actions']['checkout']='1'*40
        self.graph['inputs']['python']='3.99'
        self.graph['inputs']['nativeValidationRunner']='fixture-native-runner'
        config_path.write_text(json.dumps(self.graph))
        ts=self.tmp/self.graph['inputs']['typescript']['source']
        package=json.loads(ts.read_bytes())
        package['devDependencies']['typescript']='99.9.9'
        ts.write_text(json.dumps(package))
        rendered=delivery.templates(self.tmp)
        self.assertEqual(set(delivery.check(self.tmp)),set(str(p) for p in rendered))
        for content in rendered.values():
            self.assertIn('actions/checkout@'+'1'*40,content)
            self.assertIn("python-version: '3.99'",content)
            if 'actions/setup-node@' in content:
                self.assertEqual(content.count('node-version-file: '+node_file),content.count('actions/setup-node@'))
        for name in ('test', 'reference-guard'):
            self.assertIn('runs-on: fixture-native-runner',rendered[Path(f'.github/workflows/{name}.yml')])
        ci=rendered[Path('.github/workflows/test.yml')]
        self.assertEqual(ci.count('typescript@99.9.9'),2)
        for artifact in self.graph['inputs']['sandboxCli']['artifacts'].values():
            self.assertIn('target='+artifact['target']+'; digest='+artifact['sha256'],ci)

    def test_app_workflow_projects_service_credentials_into_actual_staging_settings(self):
        self.copy_graph()
        self.graph['inputs']['appCi'].update(disposablePassword='test-fixture')
        contract_path = self.tmp/self.graph['inputs']['appCi']['deploymentSource']
        contract = json.loads(contract_path.read_bytes())
        contract['database'].update(name='probe_db', port=15432)
        contract_path.write_text(json.dumps(contract))
        (self.tmp/delivery.GRAPH).write_text(json.dumps(self.graph))
        job=delivery.templates(self.tmp)[Path('.github/workflows/little-hands.yml')]
        settings_env=dict(re.findall(r"^      (LH_\w+): ['\"]?([^'\"\n]+)['\"]?$",job,re.M))
        with patch.dict(os.environ,settings_env,clear=True):
            settings=runpy.run_path(str(ROOT/'apps/little-hands/config/settings.py'))
        db=settings['DATABASES']['default']
        self.assertEqual((db['NAME'],db['USER'],str(db['PORT']),db['PASSWORD']),('probe_db','root','15432','test-fixture'))
        self.assertEqual(db['ENGINE'],'django.db.backends.mysql')
        self.assertIn('image: '+contract['database']['image'],job)
        self.assertIn('MYSQL_DATABASE: '+db['NAME'],job)
        self.assertIn('MYSQL_ROOT_PASSWORD: '+db['PASSWORD'],job)
        self.assertIn('15432:15432',job)
        self.assertFalse(settings['PRODUCTION'])
        self.assertIn('python -m pip install --require-hashes',job)
        self.assertIn('python -B manage.py test booking.tests config.tests',job)

    def test_major_native_sandbox_cli_is_verified_before_install_and_path_update(self):
        import hashlib
        import io
        import tarfile
        self.copy_graph()
        fixture=self.tmp/'cli.tar.gz'
        record=self.graph['inputs']['sandboxCli']['artifacts']['arm64']
        executable='codex-'+record['target']
        data=b'#!/bin/sh\nexit 0\n'
        with tarfile.open(fixture,'w:gz') as archive:
            entry=tarfile.TarInfo(executable);entry.size=len(data);entry.mode=0o755
            archive.addfile(entry,io.BytesIO(data))
        record['sha256']=hashlib.sha256(fixture.read_bytes()).hexdigest()
        (self.tmp/delivery.GRAPH).write_text(json.dumps(self.graph))
        source=delivery.templates(self.tmp)[Path('.github/workflows/reference-guard.yml')]
        self.assertIn('runs-on: macos-15',source)
        self.assertIn('brew install mysql@8.4 pkgconf',source)
        self.assertIn('--bind-address=127.0.0.1',source)
        start=source.index('            mkdir -p "$RUNNER_TEMP/figma-flow-codex"')
        snippet=source[start:source.index('            fixture=',start)]
        bindir=self.tmp/'fixture-bin';bindir.mkdir()
        fetch=bindir/'curl'
        fetch.write_text('#!/bin/sh\nwhile [ "$1" != "--output" ]; do shift; done\ncp "$LOCAL_ARCHIVE" "$2"\n')
        fetch.chmod(0o755)
        for valid in (True,False):
            scratch=self.tmp/('allow' if valid else 'reject');scratch.mkdir()
            env=dict(os.environ,RUNNER_TEMP=str(scratch),GITHUB_PATH=str(scratch/'path.txt'),
                     LOCAL_ARCHIVE=str(fixture),PATH=str(bindir)+os.pathsep+os.environ['PATH'])
            if not valid:
                fixture.write_bytes(b'wrong digest')
            proc=run(self.tmp,'bash','-e','-o','pipefail','-c',snippet,env=env)
            installed=scratch/'figma-flow-codex/codex'
            self.assertEqual(proc.returncode==0,valid,proc.stderr)
            self.assertEqual(installed.is_file(),valid)
            self.assertEqual((scratch/'path.txt').exists(),valid)
            if valid:self.assertEqual(installed.read_bytes(),data)

    def test_reference_job_runs_its_actual_packaging_and_stops_before_major_zip(self):
        graph_dir = self.tmp/'repo'
        graph_dir.mkdir()
        binary_dir = self.tmp/'bin'
        binary_dir.mkdir()
        (binary_dir/'python').symlink_to(sys.executable)
        # Invoke the real checker against an isolated Git repository, as on a runner.
        tools = graph_dir/'tools'
        tools.mkdir()
        for name in ('major_release.py','reference_distribution_guard.py'):
            (tools/name).write_text(
                "import os,sys\n"
                f"args=[sys.executable,'-B',{str(ROOT/'tools'/name)!r},'--repo',os.getcwd(),*sys.argv[1:]]\n"
                "os.execv(sys.executable,args)\n")
        def git(*args):
            return run(graph_dir,'git','-c','core.hooksPath=/dev/null','-c','user.name=Fixture',
                       '-c','user.email=ci@example.invalid',*args,check=True).stdout.strip()
        git('init','-q')
        (graph_dir/'.codex-plugin').mkdir()
        for v in ('0.36.0','1.0.0'):
            for name in ('plugin.json','.codex-plugin/plugin.json'):
                (graph_dir/name).write_text(json.dumps({'version':v}))
            git('add','.');git('commit','-qm','package '+v);git('tag','v'+v)
        workflow = (ROOT/'.github/workflows/reference-guard.yml').read_text()
        command = block(workflow.split('name: Check version and SSOT before packaging this Git tree',1)[1],'run: |')
        env = {**os.environ,'PATH':str(binary_dir)+os.pathsep+os.environ['PATH'],
               'RUNNER_TEMP':str(self.tmp),'PREVIOUS_REF':'0'*40,'RELEASE_REF':'v0.36.0'}
        archive=self.tmp/'dist-check.zip'
        first=run(graph_dir,'bash','-e','-c',command,env=env)
        self.assertEqual(first.returncode,0,first.stdout+first.stderr)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(json.loads(z.read('figma-flow-plugin/plugin.json'))['version'],'0.36.0')
        archive.unlink()
        env.update(RELEASE_REF='v1.0.0',PREVIOUS_REF=git('rev-parse','v0.36.0'))
        blocked=run(graph_dir,'bash','-e','-c',command,env=env)
        self.assertNotEqual(blocked.returncode,0)
        self.assertIn('"status": "blocked"',blocked.stdout)
        self.assertFalse(archive.exists())

    def test_history_job_refuses_missing_candidate_catalog_and_unverified_legacy_data(self):
        source=(ROOT/'.github/workflows/patch-knowledge.yml').read_text()
        self.assertIn('fetch-depth: 0',source)
        commands = [line.strip().removeprefix('run: ').split() for line in source.splitlines()
                    if line.strip().startswith('run: python tools/')]
        self.assertEqual(len(commands),2)
        run(self.tmp,'git','init','-q',check=True)
        run(self.tmp,'git','-c','core.hooksPath=/dev/null','-c','user.name=Fixture','-c','user.email=ci@example.invalid',
            'commit','--allow-empty','-qm','test commit',check=True)
        for command in commands:
            with self.subTest(tool=command[1]):
                self.assertIn('verify',command)
                program=ROOT/command[1]
                result=run(self.tmp,sys.executable,str(program),*command[2:])
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(result.stderr.startswith('usage:'),result.stderr)
                self.assertRegex((result.stdout+result.stderr).lower(),r'catalog|legacy|manifest|wiki')

    def test_sandbox_job_refuses_an_archive_with_the_wrong_digest(self):
        ci=(ROOT/'.github/workflows/test.yml').read_text()
        command=block(ci.split('name: Install native Codex CLI for the OS sandbox tests',1)[1],'run: |')
        mock=self.tmp/'curl'
        mock.write_text('#!/bin/sh\nprintf bad-archive > codex.tar.gz\n')
        mock.chmod(0o755)
        env={**os.environ,'PATH':str(self.tmp)+os.pathsep+os.environ['PATH'],'GITHUB_PATH':str(self.tmp/'env-path')}
        result=run(self.tmp,'bash','-e','-c',command,env=env)
        self.assertNotEqual(result.returncode,0)
        self.assertTrue((self.tmp/'codex.tar.gz').is_file())
        self.assertFalse((self.tmp/'figma-flow-cli').exists())
        self.assertFalse((self.tmp/'env-path').exists())


if __name__ == '__main__':
    unittest.main()
