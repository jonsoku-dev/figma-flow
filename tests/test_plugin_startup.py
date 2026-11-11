"""Startup maintenance uses mocked host commands and temporary package/workspace files."""
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import plugin_startup as startup
import figma_workspace as workspace


def package(root, version='1.0.0', name='figma-flow'):
    root.mkdir(parents=True, exist_ok=True)
    (root / '.codex-plugin').mkdir(exist_ok=True)
    for path in (root / 'plugin.json', root / '.codex-plugin/plugin.json'):
        path.write_text(json.dumps({'name':name,'version':version}))
    market = root / '.agents/plugins'
    market.mkdir(parents=True, exist_ok=True)
    (market / 'marketplace.json').write_text(json.dumps({'name':'company-private','plugins':[
        {'name':name,'source':{'source':'local','path':'./'}}]}))
    (root / 'runtime.py').write_text('fixture')
    return root


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        state_env = patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root / 'state')})
        state_env.start()
        self.addCleanup(state_env.stop)
        self.old = package(self.root / 'old')
        self.new = package(self.root / 'new', '1.1.0')
        self.inventory = {'version':'1.0.0','installedPath':str(self.old),'marketplace':'company-private',
            'marketplace_root':str(self.old),'source_type':'local','shared':False,'pin':None,'authority':'https://company.example/private/plugin'}
        self.candidate = {'version':'1.1.0','authority':self.inventory['authority'],'path':str(self.new),
            'bytes':startup.source_bytes(self.new)}
        make_temp = tempfile.mkdtemp
        def local_temporary(*args, **kwargs):
            if args or 'dir' in kwargs:
                return make_temp(*args,**kwargs)
            return make_temp(dir=self.root,**kwargs)
        temporary_paths = patch.object(startup.tempfile,'mkdtemp',side_effect=local_temporary)
        temporary_paths.start()
        self.addCleanup(temporary_paths.stop)

    def adapter(self):
        adapter = Mock()
        adapter.inventory.return_value = self.inventory
        adapter.candidate.return_value = self.candidate
        adapter.upgrade.return_value = {'status':'updated','version':'1.1.0'}
        adapter.recovery = None
        return adapter

    def test_default_ensure_applies_and_forbidden_calls_zero_native_adapters(self):
        adapter = self.adapter()
        result = startup.ensure(adapter, workspace_path=self.root / 'never-touch')
        self.assertEqual(result['codex']['status'], 'updated')
        adapter.upgrade.assert_called_once()
        adapter.native.assert_not_called()
        self.assertFalse((self.root / 'never-touch').exists())
        self.assertEqual(result['native']['reason'], 'figma-access-forbidden')

    def test_check_never_upgrades_and_exact_same_candidate_is_current(self):
        adapter = self.adapter()
        self.assertEqual(startup.ensure(adapter, apply=False)['codex']['status'], 'update-available')
        adapter.upgrade.assert_not_called()
        adapter.candidate.return_value = {**self.candidate, 'version':'1.0.0','bytes':startup.source_bytes(self.old)}
        self.assertEqual(startup.ensure(adapter)['codex']['status'], 'current')
        adapter.upgrade.assert_not_called()

    def test_pins_shared_source_offline_and_install_failure_are_honest_exceptions(self):
        adapter = self.adapter()
        self.assertEqual(startup.ensure(adapter,pin='1.0.0')['codex']['reason'], 'explicit-version-pin')
        adapter.candidate.assert_not_called()
        self.inventory['shared'] = True
        self.assertEqual(startup.ensure(adapter)['codex']['reason'], 'shared-marketplace')
        self.inventory['shared'] = False
        for reason in ('unknown-source','dirty-development-source','offline-auth-or-host-unavailable'):
            adapter.candidate.side_effect = startup.ExceptionStatus(reason)
            self.assertEqual(startup.ensure(adapter)['codex']['reason'], reason)
        adapter.candidate.side_effect = None
        adapter.upgrade.side_effect = startup.ExceptionStatus('installed-bytes-unverified')
        self.assertEqual(startup.ensure(adapter)['codex']['reason'], 'installed-bytes-unverified')

    def test_unknown_authority_and_other_fork_are_never_selected(self):
        host = startup.HostAdapter(authority_url='https://company.example/private/plugin')
        host.git = Mock(side_effect=['', 'https://other.example/private/plugin'])
        with self.assertRaisesRegex(startup.ExceptionStatus,'source-authority-mismatch'):
            host.candidate(self.old,self.inventory)
        host = startup.HostAdapter()
        with self.assertRaisesRegex(startup.ExceptionStatus,'unknown-source'):
            host.candidate(self.old,{**self.inventory,'authority':None})
        for uri in ('https://user:secret@company.example/repo','https://company.example/repo?token=secret','file:///tmp/repo'):
            with self.subTest(uri=uri), self.assertRaises(startup.ExceptionStatus):
                startup.authority(uri)

    def test_dirty_source_fails_before_network(self):
        host = startup.HostAdapter()
        host.git = Mock(return_value=' M runtime.py')
        with self.assertRaisesRegex(startup.ExceptionStatus,'dirty-development-source'):
            host.candidate(self.old,self.inventory)
        host.git.assert_called_once()

    def test_host_install_verifies_returned_path_both_manifests_and_all_bytes(self):
        installed = self.root / 'installed'
        def command(args, **_kwargs):
            if args[:3] == ['codex','plugin','add']:
                shutil.copytree(self.new,installed)
                return {'pluginId':'figma-flow@company-private','name':'figma-flow','marketplaceName':'company-private',
                        'version':'1.1.0','installedPath':str(installed)}
            return {}
        host = startup.HostAdapter()
        host.command = Mock(side_effect=command)
        self.assertEqual(host.upgrade(self.candidate,self.inventory)['status'],'updated')
        self.assertTrue((self.old / 'plugin.json').exists())
        (installed / '.codex-plugin/plugin.json').write_text('{"name":"wrong","version":"1.1.0"}')
        host.command.side_effect = lambda args, **kwargs: {'pluginId':'figma-flow@company-private','name':'figma-flow',
            'marketplaceName':'company-private','version':'1.1.0','installedPath':str(installed)} if args[:3] == ['codex','plugin','add'] else {}
        with self.assertRaisesRegex(startup.ExceptionStatus,'update-failed-recovery-required'):
            host.upgrade(self.candidate,self.inventory)
        self.assertEqual(host.recovery['old_source'],str(self.old))

    def test_verified_stable_tag_snapshot_preserves_fork_provenance(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as archive:
            for path in sorted(self.new.rglob('*')):
                if path.is_file():
                    archive.add(path,arcname=str(path.relative_to(self.new)))
        host = startup.HostAdapter()
        host.git = Mock(side_effect=['',self.inventory['authority'], 'a'*40+'\trefs/tags/v1.1.0', 'a'*40])
        host.command = Mock(side_effect=lambda args, **kwargs: stream.getvalue() if 'archive' in args else b'')
        with patch.object(startup.tempfile,'mkdtemp',return_value=str(self.root / 'snapshot')):
            (self.root / 'snapshot').mkdir()
            candidate = host.candidate(self.old,self.inventory)
        self.assertEqual(candidate['version'],'1.1.0')
        provenance = workspace.read(Path(candidate['path']) / '.figma-flow-source.json', private=True)
        self.assertEqual(provenance['authority'],self.inventory['authority'])
        self.assertEqual(candidate['bytes'],startup.source_bytes(candidate['path']))
        self.assertFalse(any(args[0][0] == 'codex' for args in host.command.call_args_list))

    def test_failed_local_upgrade_restores_exact_original_and_never_claims_current(self):
        host = startup.HostAdapter()
        count = 0
        def command(args, **_kwargs):
            nonlocal count
            if args[:3] == ['codex','plugin','add']:
                count += 1
                if count == 1:
                    raise startup.ExceptionStatus('offline-auth-or-host-unavailable')
                return {'pluginId':'figma-flow@company-private','installedPath':str(self.old)}
            return {}
        host.command = Mock(side_effect=command)
        with self.assertRaisesRegex(startup.ExceptionStatus,'update-failed-restored-original'):
            host.upgrade(self.candidate,{**self.inventory,'source_type':'local'})
        self.assertEqual(count,2)
        self.assertEqual(host.recovery['old_source'],str(self.old))

    def test_git_upgrade_refuses_before_removal_without_exact_offline_recovery(self):
        host = startup.HostAdapter()
        host.command = Mock(side_effect=AssertionError('Git recovery was not proven before removal'))
        with self.assertRaisesRegex(startup.ExceptionStatus,'exact-git-recovery-unavailable'):
            host.upgrade(self.candidate,{**self.inventory,'source_type':'git'})
        host.command.assert_not_called()
        self.assertTrue((self.old / 'plugin.json').exists())

    def test_independent_snapshot_restores_after_host_removes_original_source(self):
        host = startup.HostAdapter()
        old_bytes = startup.source_bytes(self.old)
        adds = 0
        restore_source = None
        def command(args, **_kwargs):
            nonlocal adds, restore_source
            if args[:4] == ['codex','plugin','marketplace','remove'] and self.old.exists():
                snapshot = Path(host.recovery['recovery_source'])
                self.assertEqual(startup.source_bytes(snapshot),old_bytes)
                self.assertNotEqual(snapshot.resolve(),self.old.resolve())
                shutil.rmtree(self.old)
            if args[:4] == ['codex','plugin','marketplace','add']:
                restore_source = Path(args[4])
            if args[:3] == ['codex','plugin','add']:
                adds += 1
                if adds == 1:
                    raise startup.ExceptionStatus('offline-auth-or-host-unavailable')
                return {'pluginId':'figma-flow@company-private','installedPath':str(restore_source)}
            return {}
        host.command = Mock(side_effect=command)
        with self.assertRaisesRegex(startup.ExceptionStatus,'update-failed-restored-original'):
            host.upgrade(self.candidate,self.inventory)
        self.assertFalse(self.old.exists())
        self.assertEqual(startup.source_bytes(restore_source),old_bytes)
        record = workspace.read(restore_source.parent / 'recovery.json',private=True)
        self.assertEqual(record['name'],'figma-flow')
        self.assertEqual(record['authority'],self.inventory['authority'])
        self.assertEqual(record['source_sha256'],workspace.digest(workspace.encode(old_bytes)))

    def test_git_failures_restore_independent_bytes_when_old_cache_is_deleted(self):
        for failure in ('marketplace-add','plugin-add'):
            with self.subTest(failure=failure):
                old = package(self.root / ('git-old-' + failure))
                (old / '.git').mkdir()
                old_bytes = startup.source_bytes(old)
                host = startup.HostAdapter()
                host.git = Mock(side_effect=['',self.inventory['authority'],'a'*40])
                inventory = {**self.inventory,'marketplace_root':str(old),'installedPath':str(old),'source_type':'git'}
                restore_source = None
                def command(args, **_kwargs):
                    nonlocal restore_source
                    if args[:3] == ['codex','plugin','remove'] and old.exists():
                        snapshot = Path(host.recovery['recovery_source'])
                        self.assertEqual(startup.source_bytes(snapshot),old_bytes)
                        shutil.rmtree(old)
                    if args[:4] == ['codex','plugin','marketplace','add']:
                        if args[4] == self.candidate['authority']:
                            if failure == 'marketplace-add':
                                raise startup.ExceptionStatus('offline-auth-or-host-unavailable')
                        else:
                            restore_source = Path(args[4])
                    if args[:3] == ['codex','plugin','add']:
                        if restore_source is None:
                            raise startup.ExceptionStatus('offline-auth-or-host-unavailable')
                        return {'pluginId':'figma-flow@company-private','installedPath':str(restore_source)}
                    return {}
                host.command = Mock(side_effect=command)
                with self.assertRaisesRegex(startup.ExceptionStatus,'update-failed-restored-original'):
                    host.upgrade(self.candidate,inventory)
                self.assertFalse(old.exists())
                self.assertEqual(startup.source_bytes(restore_source),old_bytes)
                self.assertEqual(host.recovery['original_source_type'],'git')
                self.assertEqual(host.recovery['restored_source_type'],'local')
                record = workspace.read(restore_source.parent / 'recovery.json',private=True)
                self.assertEqual(record['original_ref'],'a'*40)
                self.assertEqual(record['authority'],self.inventory['authority'])
                inventory_reader = startup.HostAdapter(installed_root=restore_source)
                inventory_reader.command = Mock(side_effect=[{'installed':[{'pluginId':'figma-flow@company-private',
                    'name':'figma-flow','marketplaceName':'company-private','installed':True,'version':'1.0.0'}]},
                    {'marketplaces':[{'name':'company-private','root':str(restore_source),
                        'marketplaceSource':{'sourceType':'local','source':str(restore_source)}}]}])
                recovered = inventory_reader.inventory()
                self.assertEqual(recovered['authority'],self.inventory['authority'])
                self.assertEqual(recovered['source_type'],'local')

    def test_absent_marketplace_cleanup_cannot_skip_verified_snapshot_restore(self):
        for source_type in ('local','git'):
            for corrupt in (False,True):
                with self.subTest(source_type=source_type,corrupt=corrupt):
                    old = package(self.root / ('absent-old-' + source_type + str(corrupt)))
                    if source_type == 'git':
                        (old / '.git').mkdir()
                    old_bytes = startup.source_bytes(old)
                    host = startup.HostAdapter()
                    host.git = Mock(side_effect=['',self.inventory['authority'],'a'*40])
                    state = {'registered':True,'source':old,'absent_removes':0,'snapshot_adds':0}
                    installed = self.root / ('restored-' + source_type + str(corrupt))
                    def command(args, **_kwargs):
                        if args[:4] == ['codex','plugin','marketplace','remove']:
                            if not state['registered']:
                                state['absent_removes'] += 1
                                raise startup.ExceptionStatus('offline-auth-or-host-unavailable')
                            state['registered'] = False
                        if args[:4] == ['codex','plugin','marketplace','add']:
                            snapshot = Path(host.recovery['recovery_source'])
                            if args[4] != str(snapshot):
                                raise startup.ExceptionStatus('offline-auth-or-host-unavailable')
                            state.update(registered=True,source=snapshot)
                            state['snapshot_adds'] += 1
                        if args[:3] == ['codex','plugin','add']:
                            self.assertTrue(state['registered'])
                            shutil.copytree(state['source'],installed)
                            if corrupt:
                                (installed / 'runtime.py').write_text('corrupted')
                            return {'pluginId':'figma-flow@company-private','installedPath':str(installed)}
                        return {}
                    host.command = Mock(side_effect=command)
                    reason = 'update-failed-recovery-required' if corrupt else 'update-failed-restored-original'
                    with self.assertRaisesRegex(startup.ExceptionStatus,reason):
                        host.upgrade(self.candidate,{**self.inventory,'source_type':source_type,
                            'marketplace_root':str(old),'installedPath':str(old)})
                    self.assertEqual(state['absent_removes'],1)
                    self.assertEqual(state['snapshot_adds'],1)
                    self.assertEqual(startup.source_bytes(host.recovery['recovery_source']),old_bytes)
                    if corrupt:
                        self.assertNotIn('restored_source_type',host.recovery)
                    else:
                        self.assertEqual(startup.source_bytes(installed),old_bytes)
                        self.assertEqual(host.recovery['restored_source_type'],'local')

    def test_registered_release_and_recovery_survive_disposable_temp_cleanup(self):
        ordinary_temp = self.root / 'ordinary-temp'
        old = package(ordinary_temp / 'old')
        release = package(ordinary_temp / 'release','1.1.0')
        (release / 'runtime.py').chmod(0o700)
        old_bytes, new_bytes = startup.source_bytes(old), startup.source_bytes(release)
        host = startup.HostAdapter()
        host.temporary = ordinary_temp
        registered_source = None
        installed = self.root / 'durable-installed'
        def command(args, **_kwargs):
            nonlocal registered_source
            if args[:4] == ['codex','plugin','marketplace','add']:
                registered_source = Path(args[4])
            if args[:3] == ['codex','plugin','add']:
                shutil.copytree(registered_source,installed)
                return {'pluginId':'figma-flow@company-private','name':'figma-flow',
                    'marketplaceName':'company-private','version':'1.1.0','installedPath':str(installed)}
            return {}
        host.command = Mock(side_effect=command)
        result = host.upgrade({**self.candidate,'path':str(release),'bytes':new_bytes},
            {**self.inventory,'marketplace_root':str(old),'installedPath':str(old)})
        host.discard()
        self.assertFalse(ordinary_temp.exists())
        state = self.root / 'state' / host.name / 'plugin-updates'
        recovery = Path(host.recovery['recovery_source'])
        self.assertTrue(registered_source.resolve().is_relative_to(state.resolve()))
        self.assertTrue(recovery.resolve().is_relative_to(state.resolve()))
        self.assertEqual(Path(result['source']),registered_source)
        self.assertEqual(startup.source_bytes(registered_source),new_bytes)
        self.assertEqual(startup.source_bytes(recovery),old_bytes)
        self.assertEqual(startup.source_bytes(installed),new_bytes)
        for path in [state.parent,state,*state.rglob('*')]:
            self.assertEqual(path.stat().st_mode & 0o777,0o700 if path.is_dir() or path.stat().st_mode & 0o100 else 0o600)
        self.assertEqual((registered_source / 'runtime.py').stat().st_mode & 0o777,0o700)

    def test_durable_state_defaults_to_runtime_home_and_rejects_relative_xdg(self):
        host = startup.HostAdapter()
        with patch.dict(os.environ,{'XDG_STATE_HOME':''}), patch.object(startup.Path,'home',return_value=self.root / 'runtime-home'):
            directory, snapshot = host.retain(self.old,'recovery-',startup.source_bytes(self.old))
        expected = self.root / 'runtime-home/.local/state' / host.name / 'plugin-updates'
        self.assertEqual(directory.parent,expected)
        self.assertEqual(startup.source_bytes(snapshot),startup.source_bytes(self.old))
        with patch.dict(os.environ,{'XDG_STATE_HOME':'relative-state'}), patch.object(workspace,'private_dir',
                side_effect=AssertionError('Relative state attempted a filesystem mutation')):
            with self.assertRaisesRegex(startup.ExceptionStatus,'private-state-unverified'):
                host.retain(self.old,'recovery-',startup.source_bytes(self.old))

    def test_read_only_candidate_check_never_creates_retained_state(self):
        host = startup.HostAdapter()
        host.inventory = Mock(return_value=self.inventory)
        host.candidate = Mock(return_value=self.candidate)
        result = startup.ensure(host,apply=False,figma_access='forbidden')
        self.assertEqual(result['codex']['status'],'update-available')
        self.assertFalse((self.root / 'state').exists())

    def test_failed_restore_retains_verified_independent_source(self):
        host = startup.HostAdapter()
        old_bytes = startup.source_bytes(self.old)
        host.command = Mock(side_effect=startup.ExceptionStatus('offline-auth-or-host-unavailable'))
        with self.assertRaisesRegex(startup.ExceptionStatus,'update-failed-recovery-required'):
            host.upgrade(self.candidate,self.inventory)
        self.assertEqual(startup.source_bytes(host.recovery['recovery_source']),old_bytes)

    def test_all_package_exceptions_skip_native_writes_and_forbidden_skips_all_calls(self):
        for phase, reason in (('inventory','unknown-source'),('candidate','offline-auth-or-host-unavailable'),
                              ('candidate','dirty-development-source'),('upgrade','update-failed-recovery-required')):
            for access in ('allowed','forbidden'):
                with self.subTest(phase=phase,reason=reason,access=access):
                    adapter = self.adapter()
                    getattr(adapter,phase).side_effect = startup.ExceptionStatus(reason)
                    result = startup.ensure(adapter,figma_access=access,workspace_path=self.root / 'workspace')
                    self.assertEqual(result['codex']['status'],'exception')
                    self.assertFalse(any(call.args[1] is True for call in adapter.native.call_args_list))
                    if access == 'forbidden':
                        adapter.native.assert_not_called()
        for kind in ('pin','shared','returned-exception'):
            with self.subTest(kind=kind):
                adapter = self.adapter()
                if kind == 'shared':
                    adapter.inventory.return_value = {**self.inventory,'shared':True}
                if kind == 'returned-exception':
                    adapter.upgrade.return_value = {'status':'exception','reason':'update-failed'}
                result = startup.ensure(adapter,pin='1.0.0' if kind == 'pin' else None,
                    figma_access='allowed',workspace_path=self.root / 'workspace')
                self.assertEqual(result['native']['reason'],'package-update-unverified')
                self.assertFalse(any(call.args[1] is True for call in adapter.native.call_args_list))

    def test_only_verified_current_or_updated_admits_native_writes(self):
        for status in ('current','updated'):
            with self.subTest(status=status):
                adapter = self.adapter()
                if status == 'current':
                    adapter.candidate.return_value = {**self.candidate,'version':'1.0.0',
                        'bytes':startup.source_bytes(self.old)}
                adapter.native.return_value = {'status':'files-current','loaded':'unverified'}
                result = startup.ensure(adapter,figma_access='allowed',workspace_path=self.root / 'workspace')
                self.assertEqual(result['codex']['status'],status)
                adapter.native.assert_called_with(self.root / 'workspace',True)

    def test_active_native_preflight_blocks_package_update(self):
        adapter = self.adapter()
        adapter.native.side_effect = startup.ExceptionStatus('active-or-uncertain-native-operation')
        result = startup.ensure(adapter,figma_access='allowed',workspace_path=self.root / 'workspace')
        self.assertEqual(result['codex']['reason'],'native-ownership-or-inputs-unverified')
        adapter.candidate.assert_not_called()
        adapter.upgrade.assert_not_called()

    def load_company_fork(self):
        fork = package(self.root / 'company-fork', name='vibe-ops-figma')
        (fork / 'tools').mkdir()
        entrypoint = fork / 'tools/plugin_startup.py'
        shutil.copyfile(startup.__file__,entrypoint)
        spec = importlib.util.spec_from_file_location('company_startup',entrypoint)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, fork

    def test_invoked_company_fork_targets_only_its_matching_installed_name(self):
        module, fork = self.load_company_fork()
        host = module.HostAdapter()
        self.assertEqual(module.NAME,'vibe-ops-figma')
        self.assertEqual(host.name,'vibe-ops-figma')
        host.command = Mock(side_effect=[{'installed':[{'pluginId':'vibe-ops-figma@company-private',
            'name':'vibe-ops-figma','marketplaceName':'company-private','installed':True,'version':'1.0.0'}]},
            {'marketplaces':[{'name':'company-private','root':str(fork),'marketplaceSource':{
                'sourceType':'git','source':'git@company.example:team/vibe-ops-figma.git'}}]}])
        inventory = host.inventory()
        self.assertEqual(Path(inventory['installedPath']).resolve(),fork.resolve())
        release = package(self.root / 'company-release','1.1.0','vibe-ops-figma')
        installed = self.root / 'company-installed'
        def command(args, **_kwargs):
            if args[:3] == ['codex','plugin','add']:
                shutil.copytree(release,installed)
                return {'pluginId':'vibe-ops-figma@company-private','name':'vibe-ops-figma',
                    'marketplaceName':'company-private','version':'1.1.0','installedPath':str(installed)}
            return {}
        host.command = Mock(side_effect=command)
        result = host.upgrade({'path':str(release),'version':'1.1.0','bytes':module.source_bytes(release),
            'authority':'ssh://git@company.example/team/vibe-ops-figma','tag':'v1.1.0'},{**inventory,'source_type':'local'})
        self.assertEqual(result['status'],'updated')
        targets = [call.args[0][3] for call in host.command.call_args_list if call.args[0][:3] in (
            ['codex','plugin','remove'],['codex','plugin','add'])]
        self.assertEqual(targets,['vibe-ops-figma@company-private']*2)

    def test_company_fork_rejects_wrong_candidate_name_before_any_host_mutation(self):
        module, _fork = self.load_company_fork()
        host = module.HostAdapter()
        host.command = Mock(side_effect=AssertionError('Wrong candidate reached host'))
        with self.assertRaisesRegex(module.ExceptionStatus,'package-identity-mismatch'):
            host.upgrade(self.candidate,self.inventory)
        host.command.assert_not_called()
        manifests = self.root / 'company-fork/.codex-plugin/plugin.json'
        manifests.write_text('{"name":"figma-flow","version":"1.0.0"}')
        with self.assertRaisesRegex(module.ExceptionStatus,'package-identity-mismatch'):
            module.package_identity(self.root / 'company-fork')

    def test_recorded_scp_git_authority_normalizes_without_guessing_or_credentials(self):
        expected = 'ssh://git@company.example/TEAM/private-plugin'
        self.assertEqual(startup.authority('git@COMPANY.EXAMPLE:TEAM/private-plugin.git'),expected)
        self.assertEqual(startup.authority('ssh://git@company.example/TEAM/private-plugin.git'),expected)
        for value in ('git@host:team/repo?token=secret','git@host:team/repo#secret',
                      'git:secret@host:team/repo','git@host:../repo','git@host:team/ghp_secret',
                      'ssh://git:secret@host/team/repo','ssh://git@host/team/repo?token=secret',
                      'ssh://git@host/team/github_pat_secret','https:///team/repo'):
            with self.subTest(value=value), self.assertRaises(startup.ExceptionStatus):
                startup.authority(value)

    def test_command_errors_never_return_credentials(self):
        runner = Mock(return_value=subprocess.CompletedProcess([],1,b'token=private',b'Bearer private'))
        host = startup.HostAdapter(runner=runner)
        with self.assertRaisesRegex(startup.ExceptionStatus,'^offline-auth-or-host-unavailable$'):
            host.command(['codex','plugin','list','--json'])

    def test_grounded_host_inventory_and_shared_marketplace_exception(self):
        installed = [{'pluginId':'figma-flow@company-private','name':'figma-flow','marketplaceName':'company-private',
            'version':'1.0.0','installed':True}]
        host = startup.HostAdapter(installed_root=self.old)
        host.command = Mock(side_effect=[{'installed':installed,'available':[]},{'marketplaces':[
            {'name':'company-private','root':str(self.old),'marketplaceSource':{'sourceType':'local','source':str(self.old)}}]}])
        self.assertEqual(host.inventory()['installedPath'],str(self.old))
        self.assertIsNone(host.authority_url)

    def test_native_claimed_uncertain_and_legacy_are_exceptions_without_publication(self):
        root = self.root / 'workspace'
        assigned = self.root / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(root,assigned)
        control = root / '.control/requests'
        (root / '.control').mkdir(mode=0o700)
        control.mkdir(mode=0o700)
        for state in ('claimed','pending','uncertain'):
            workspace.atomic(control / 'request.json',workspace.encode({'schema':'figma-flow-control-v1','state':state}))
            with patch.object(workspace,'publish',side_effect=AssertionError('published active task')):
                result = startup.ensure(self.adapter_for_native(),figma_access='allowed',workspace_path=root)
            self.assertEqual(result['native']['status'],'exception')
        (control / 'request.json').unlink()
        prepared = workspace.prepare(root,'read','Read','discover',['--file-key','fixturefile','--page-id','12:1'])
        catalogue = workspace.current(root)
        del catalogue['tasks'][0]['generator_args']
        workspace.publish(root,catalogue)
        with self.assertRaisesRegex(startup.ExceptionStatus,'legacy-task-requires-admission'):
            startup.HostAdapter().native(root,False)

    def test_native_check_is_read_only_and_replays_stale_task_generators(self):
        root = self.root / 'workspace'
        assigned = self.root / 'assigned.json'
        assigned.write_text('{"id":"12345"}')
        workspace.init(root,assigned)
        workspace.prepare(root,'read','Read','discover',['--file-key','fixturefile','--page-id','12:1'])
        catalogue = workspace.current(root)
        catalogue['tasks'][0]['generator_sha256'] = '0'*64
        workspace.publish(root,catalogue)
        (root / '.workspace.lock').unlink()
        snapshot = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        host = startup.HostAdapter()
        self.assertEqual(host.native(root,False)['status'],'update-available')
        self.assertEqual(snapshot,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})
        self.assertEqual(host.native(root,True)['status'],'files-updated')
        self.assertEqual(workspace.current(root)['tasks'][0]['generator_sha256'], workspace.trusted_sources())

    def adapter_for_native(self):
        host = startup.HostAdapter()
        host.inventory = Mock(side_effect=startup.ExceptionStatus('unknown-source'))
        return host
