"""Registry consent and test isolation through the public process boundaries."""
import json
import os
import runpy
from pathlib import Path
import select
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
PYTHON = [sys.executable, '-B']


def api_init(path, assigned):
    sys.path.insert(0, str(TOOLS))
    import figma_workspace
    figma_workspace.init(path, assigned)


@unittest.skipUnless(os.name == 'posix', 'Figma private workspace requires POSIX')
class RegistryIntentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        home, self.xdg, temp = (self.base / key for key in ('fake-home', 'fake-config', 'system-tmp'))
        for path in (home, self.xdg, temp):
            path.mkdir(mode=0o700)
        self.home = home
        self.virtual = False
        self.env = {**os.environ, 'XDG_CONFIG_HOME': str(self.xdg), 'TMPDIR': str(temp)}
        self.fallback = home / '.config/figma-flow'
        self.registry = self.xdg / 'figma-flow/workspaces.json'
        self.ws = self.base / 'projects/scratch'
        self.ws.parent.mkdir(mode=0o700)
        self.assigned = self.base / 'assigned.json'
        self.assigned.write_text('{"id":"554433"}')

    def command(self, tool, *args):
        return self.python(TOOLS / tool, *args)

    def python(self, script, *args):
        prefix = [__file__, 'virtual-pc', str(self.home)] if self.virtual else []
        return [*PYTHON, *prefix, str(script), *map(str, args)]

    def run_ok(self, tool, *args, env=None):
        result = subprocess.run(self.command(tool, *args), env=self.env if env is None else env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def init(self, path, env=None):
        return self.run_ok('figma_workspace.py','init','--workspace',path,'--id-from',self.assigned,env=env)

    def remember(self, path, *flags):
        return self.run_ok('figma_workspace.py','remember','--workspace',path,*flags)

    def lifecycle(self, env):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port = probe.getsockname()[1]
        control = self.ws / 'control.json'
        if control.exists():
            port = json.loads(control.read_bytes())['port']
        self.run_ok('figma_control.py','enable','--workspace',self.ws,'--port',port,env=env)
        self.run_ok('figma_workspace.py','refresh','--workspace',self.ws,env=env)
        with subprocess.Popen(self.command('figma_control.py','serve','--workspace',self.ws),
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as p:
            try:
                self.assertTrue(select.select([p.stdout], [], [], 20)[0], 'server readiness timed out')
                self.assertEqual(json.loads(p.stdout.readline())['port'], port)
            finally:
                p.terminate()
                p.communicate(timeout=10)
        return port

    def test_unregistered_lifecycle_leaves_both_config_roots_absent(self):
        # The virtual branch redirects only registry lookup; other code keeps the isolated process XDG.
        for has_xdg in (False, True):
            with self.subTest(explicit_xdg=has_xdg):
                env=self.env.copy()
                self.virtual = not has_xdg
                self.ws=self.ws.with_name('explicit' if has_xdg else 'fallback')
                subprocess.run(self.python(__file__, 'api-init', self.ws, self.assigned),
                               env=env, check=True, timeout=30)
                self.init(self.ws,env)
                self.lifecycle(env)
                self.assertFalse(self.fallback.exists() or self.registry.parent.exists(),
                                 'ordinary lifecycle must not create a PC registry directory or lock')

    def test_rc2_registry_and_default_remain_stable(self):
        other=self.ws.with_name('remembered')
        self.init(other)
        self.init(self.ws)
        self.registry.parent.mkdir(mode=0o700,exist_ok=True)
        original={'schema':'figma-flow-workspace-registry-v1','default_workspace':str(other.resolve()),
                  'workspaces':[{'path':str(other.resolve()),'plugin_id':'554433','control_port':None,
                                 'registered_at':'2026-01-01T00:00:00Z','updated_at':'2026-01-01T00:00:00Z'}]}
        self.registry.write_text(json.dumps(original)); self.registry.chmod(0o600)
        before=self.registry.read_bytes()
        self.lifecycle(self.env)
        self.assertEqual(self.registry.read_bytes(),before,'ordinary commands must preserve the legacy default')
        self.remember(self.ws)
        remembered = self.registry.read_bytes()
        self.lifecycle(self.env)
        self.remember(self.ws)
        self.assertEqual(self.registry.read_bytes(), remembered)
        reg=json.loads(self.registry.read_bytes())
        self.assertEqual(reg['default_workspace'],str(other.resolve()))
        self.assertEqual(len(reg['workspaces']),2)
        self.assertEqual(self.run_ok('figma_control.py','setup-status')['workspace'],str(other.resolve()))
        self.remember(self.ws,'--default')
        self.assertEqual(self.run_ok('figma_control.py','setup-status')['workspace'],str(self.ws.resolve()))
        self.assertEqual(stat.S_IMODE(self.registry.stat().st_mode),0o600)

    def test_discovery_requires_choice_when_default_is_missing(self):
        paths = [self.ws, self.ws.with_name('another')]
        for path in paths:
            self.init(path)
        self.registry.parent.mkdir(mode=0o700, exist_ok=True)
        rows = [{'path': str(path.resolve()), 'plugin_id': '554433', 'control_port': None} for path in paths]
        for default in (None, str(self.ws.with_name('deleted'))):
            with self.subTest(default=default):
                raw = json.dumps({'schema': 'figma-flow-workspace-registry-v1',
                                  'default_workspace': default, 'workspaces': rows}).encode()
                self.registry.write_bytes(raw)
                self.registry.chmod(0o600)
                status = self.run_ok('figma_control.py', 'setup-status')
                self.assertIsNone(status['workspace'], 'multiple workspaces require an explicit selection')
                self.assertEqual(len(status['registered_workspaces']), 2)
                self.assertIn('--workspace', status['next_command'])
                self.assertIn('remember', status['guidance'])
                chosen = self.run_ok('figma_control.py', 'setup-status', '--workspace', paths[1])
                self.assertEqual(chosen['workspace'], str(paths[1].resolve()))
                self.assertEqual(self.registry.read_bytes(), raw)
        paths[1].rename(self.ws.with_name('unregistered'))
        self.assertEqual(self.run_ok('figma_control.py', 'setup-status')['workspace'], str(self.ws.resolve()))

    def test_concurrent_explicit_cli_and_default(self):
        other = self.ws.with_name('second')
        self.init(self.ws)
        self.init(other)
        with subprocess.Popen(self.command('figma_workspace.py', 'remember', '--workspace', self.ws, '--default'),
                              env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as first:
            self.remember(other)
            _, error = first.communicate(timeout=30)
            self.assertEqual(first.returncode, 0, error)
        data = json.loads(self.registry.read_bytes())
        self.assertEqual(data['default_workspace'], str(self.ws.resolve()))
        self.assertEqual({r['path'] for r in data['workspaces']}, {str(p.resolve()) for p in (self.ws, other)})
        self.remember(other)
        self.assertEqual(self.run_ok('figma_control.py', 'setup-status')['workspace'], str(self.ws.resolve()))

    def test_explicit_write_preserves_bad_registry(self):
        self.init(self.ws)
        self.registry.parent.mkdir(mode=0o700,exist_ok=True)
        for raw, mode in [(b'{not json',0o600),(b'{"schema":"new-format","workspaces":[]}',0o600),
                          (b'{"schema":"figma-flow-workspace-registry-v1","workspaces":[42]}',0o600),
                          (b'{"schema":"figma-flow-workspace-registry-v1","workspaces":[]}',0o644)]:
            with self.subTest(raw=raw,mode=mode):
                self.registry.write_bytes(raw);self.registry.chmod(mode)
                result=subprocess.run(self.command('figma_workspace.py','remember','--workspace',self.ws),
                                      env=self.env,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,2)
                self.assertIn('registry',result.stderr)
                self.assertEqual(self.registry.read_bytes(),raw)
                self.assertEqual(stat.S_IMODE(self.registry.stat().st_mode),mode)

    def test_direct_registration_refuses_corrupt_existing_file(self):
        self.registry.parent.mkdir(mode=0o700,exist_ok=True)
        self.registry.write_bytes(b'preserve broken registry');self.registry.chmod(0o600)
        self.ws.mkdir(mode=0o700)
        child=subprocess.run([*PYTHON,__file__,'api-register',str(self.ws)],env=self.env,capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(child.stdout.strip(),'False','explicit registration must preserve corrupt bytes')
        self.assertEqual(self.registry.read_bytes(),b'preserve broken registry')

    def test_ci_and_contributor_commands_use_isolation(self):
        suites = {'test': ('-m unittest discover -v -s tests', 'graph_governance.py test-other-suites'),
                  'little-hands': ('manage.py test booking.tests', '-m unittest discover -s tests'),
                  'patch-knowledge': ('-m unittest discover',),
                  'reference-guard': ('-m unittest tests.test_major_release', 'tools/major_release.py --if-major')}
        for name, commands in suites.items():
            for path in (ROOT / 'library/delivery' / (name+'.yml.in'), ROOT / '.github/workflows' / (name+'.yml')):
                for command in commands:
                    matches = [line for line in path.read_text().splitlines() if command in line]
                    self.assertTrue(matches, command)
                    self.assertTrue(all('tools/test_env.py' in line for line in matches), command)
        for doc in ('CONTRIBUTING.md', 'skills/patch-knowledge/SKILL.md'):
            self.assertIn('tools/test_env.py', (ROOT / doc).read_text())

    def test_runner_isolates_descendants_and_cleans_after_failure(self):
        paths=self.base/'observed.json'
        child=[*PYTHON,'-c',"import os,sys,pathlib,json; p=pathlib.Path(os.environ['XDG_CONFIG_HOME']); "
               "pathlib.Path(sys.argv[1]).write_text(json.dumps([str(p),p.stat().st_mode & 0o777])); sys.exit(19)", str(paths)]
        driver=[*PYTHON,'-c','import subprocess,sys;sys.exit(subprocess.call(sys.argv[1:]))',*child]
        observed = set()
        for _ in range(2):
            run=subprocess.run(self.command('test_env.py',*driver),env=self.env,capture_output=True,timeout=30)
            self.assertEqual(run.returncode,19)
            path,mode=json.loads(paths.read_bytes())
            self.assertNotIn(path, observed)
            observed.add(path)
            self.assertNotEqual(Path(path), self.xdg)
            self.assertEqual(mode,0o700)
            self.assertFalse(Path(path).exists())
        self.assertEqual(list(self.xdg.iterdir()),[])


if __name__=='__main__':
    if sys.argv[1:2] == ['virtual-pc']:
        home, script, *arguments = sys.argv[2:]
        sys.path.insert(0, str(Path(script).parent))
        sys.argv = [script, *arguments]
        sys.path.insert(0, str(TOOLS))
        import workspace_registry
        virtual_os = Mock(wraps=os)
        virtual_os.name = os.name
        virtual_os.environ = {k: v for k, v in os.environ.items() if k != 'XDG_CONFIG_HOME'}
        with patch.object(Path, 'home', return_value=Path(home)), patch.object(workspace_registry, 'os', virtual_os):
            runpy.run_path(script, run_name='__main__')
    elif sys.argv[1:2]==['api-init']:
        api_init(*sys.argv[2:])
    elif sys.argv[1:2]==['api-register']:
        sys.path.insert(0,str(TOOLS))
        import workspace_registry
        print(workspace_registry.register_workspace(sys.argv[2],plugin_id='554433'))
    else:
        unittest.main()
