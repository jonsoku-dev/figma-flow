#!/usr/bin/env python3
"""Check each workflow's package and native files; apply only proven safe updates."""
import argparse
from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit

import figma_workspace as workspace

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'figma-flow-startup-v1'


class ExceptionStatus(ValueError):
    """A bounded exception code, never raw host command output."""


def authority(value):
    if not isinstance(value, str) or not value or re.search(r'gh[pousr]_|github_pat_|glpat-|\bsk-', value, re.I):
        raise ExceptionStatus('unknown-source')
    scp = re.fullmatch(r'git@([A-Za-z0-9][A-Za-z0-9.-]*):([A-Za-z0-9._/-]+)', value)
    if scp:
        value = 'ssh://git@' + scp[1] + '/' + scp[2]
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ExceptionStatus('unknown-source') from None
    if (parsed.scheme not in {'https', 'ssh'} or not parsed.hostname or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', parsed.hostname) or
            parsed.password or parsed.query or parsed.fragment or
            (parsed.scheme == 'https' and parsed.username) or
            (parsed.username and not re.fullmatch(r'[A-Za-z0-9._-]+', parsed.username)) or
            (port is not None and not 1 <= port <= 65535) or
            not parsed.path.startswith('/') or '..' in parsed.path.split('/')):
        raise ExceptionStatus('unknown-source')
    host = parsed.hostname.lower() + (':' + str(port) if port is not None else '')
    user = parsed.username + '@' if parsed.username else ''
    return parsed.scheme + '://' + user + host + parsed.path.rstrip('/').removesuffix('.git')


def package_identity(root):
    root = Path(root)
    a = workspace.read(root / 'plugin.json', limit=128 * 1024)
    b = workspace.read(root / '.codex-plugin/plugin.json', limit=128 * 1024)
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ExceptionStatus('package-identity-mismatch')
    if (not isinstance(a.get('name'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,127}', a['name']) or
            b.get('name') != a['name'] or a.get('version') != b.get('version') or
            not re.fullmatch(r'\d+\.\d+\.\d+', str(a.get('version')))):
        raise ExceptionStatus('package-identity-mismatch')
    return a['name'], a['version']


NAME = package_identity(ROOT)[0]


def package(root, expected_name=NAME):
    name, version = package_identity(root)
    if name != expected_name:
        raise ExceptionStatus('package-identity-mismatch')
    return version


def source_bytes(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob('*')):
        if '.git' in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            raise ExceptionStatus('unsafe-source')
        if path.is_file():
            result[str(path.relative_to(root))] = workspace.digest(workspace.regular(path).read_bytes())
    return result


class HostAdapter:
    def __init__(self, *, authority_url=None, runner=subprocess.run, installed_root=ROOT):
        self.authority_url = authority_url
        self.runner = runner
        self.installed_root = Path(installed_root)
        self.name = package_identity(self.installed_root)[0]
        self.recovery = None
        self.native_root = self.installed_root
        self.temporary = None

    def command(self, args, *, cwd=None, raw=False, timeout=120):
        try:
            reply = self.runner(args, cwd=cwd, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise ExceptionStatus('offline-auth-or-host-unavailable') from None
        if reply.returncode:
            raise ExceptionStatus('offline-auth-or-host-unavailable')
        if raw:
            return reply.stdout
        try:
            value = json.loads(reply.stdout)
            if not isinstance(value, dict):
                raise ExceptionStatus('unsupported-host-response')
            return value
        except (ValueError, UnicodeError):
            raise ExceptionStatus('unsupported-host-response') from None

    def git(self, *args, cwd=None):
        return self.command(['git', *args], cwd=cwd, raw=True).decode().strip()

    def inventory(self):
        listings = self.command(['codex', 'plugin', 'list', '--json'])
        markets = self.command(['codex', 'plugin', 'marketplace', 'list', '--json'])
        rows = listings.get('installed', [])
        matches = [row for row in rows if row.get('name') == self.name and row.get('installed') is True]
        if len(matches) != 1:
            raise ExceptionStatus('ambiguous-installed-package')
        row = matches[0]
        name = row['marketplaceName']
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', name) or row.get('pluginId') != self.name + '@' + name:
            raise ExceptionStatus('ambiguous-installed-package')
        found = [market for market in markets.get('marketplaces', []) if market.get('name') == name]
        if len(found) != 1:
            raise ExceptionStatus('unknown-source')
        market = found[0]
        descriptor = workspace.read(Path(market['root']) / '.agents/plugins/marketplace.json', limit=128 * 1024)
        declared = descriptor.get('plugins', [])
        shared = len(declared) != 1 or declared[0].get('name') != self.name or len([r for r in rows if r.get('marketplaceName') == name]) != 1
        if (self.installed_root / '.git').exists():
            raise ExceptionStatus('development-checkout')
        version = package(self.installed_root, self.name)
        if version != row.get('version'):
            raise ExceptionStatus('installed-version-unverified')
        recorded = market.get('marketplaceSource', {})
        origin = recorded.get('source') if recorded.get('sourceType') == 'git' else None
        provenance = Path(market['root']) / '.figma-flow-source.json'
        if origin is None and provenance.exists():
            saved = workspace.read(provenance, private=True, limit=4096)
            if set(saved) != {'schema', 'authority', 'tag', 'sha'} or saved['schema'] != 'figma-flow-startup-source-v1':
                raise ExceptionStatus('unknown-source')
            if not isinstance(saved['tag'], str) or saved['tag'].removeprefix('v') != version or not isinstance(saved['sha'], str) or not re.fullmatch(r'[a-f0-9]{40,64}', saved['sha']):
                raise ExceptionStatus('unknown-source')
            origin = authority(saved['authority'])
        recovery_record = Path(market['root']).parent / 'recovery.json'
        if origin is None and recovery_record.exists():
            saved = workspace.read(recovery_record, private=True, limit=8192)
            if (saved.get('schema') != 'figma-flow-startup-recovery-v1' or saved.get('name') != self.name or
                    saved.get('version') != version or saved.get('marketplace') != name or
                    saved.get('source_type') != 'local' or
                    Path(saved.get('recovery_source', '')).resolve() != Path(market['root']).resolve() or
                    saved.get('source_sha256') != workspace.digest(workspace.encode(source_bytes(market['root'])))):
                raise ExceptionStatus('unknown-source')
            origin = authority(saved['authority'])
        return {'installedPath': str(self.installed_root), 'version': version, 'marketplace': name,
                'marketplace_root': market['root'], 'authority': origin, 'shared': shared,
                'pin': None, 'source_type': recorded.get('sourceType')}

    def candidate(self, source, inventory):
        if inventory.get('authority') and self.authority_url and authority(inventory['authority']) != authority(self.authority_url):
            raise ExceptionStatus('source-authority-mismatch')
        trusted = inventory.get('authority') or self.authority_url
        trusted = authority(trusted)
        if source is not None:
            source = Path(source).resolve()
            if self.git('status', '--porcelain', '--untracked-files=all', cwd=source):
                raise ExceptionStatus('dirty-development-source')
            if authority(self.git('remote', 'get-url', 'origin', cwd=source)) != trusted:
                raise ExceptionStatus('source-authority-mismatch')
        # Resolve remote release tags without modifying the caller's checkout or cache.
        refs = self.git('ls-remote', '--tags', '--refs', trusted)
        tags = []
        for line in refs.splitlines():
            match = re.fullmatch(r'([a-f0-9]{40,64})\s+refs/tags/(v?(\d+)\.(\d+)\.(\d+))', line)
            if match:
                tags.append((tuple(int(match[i]) for i in (3, 4, 5)), match[2], match[1]))
        if not tags:
            raise ExceptionStatus('no-stable-release')
        version, tag, sha = max(tags)
        if len({item[2] for item in tags if item[0] == version}) != 1:
            raise ExceptionStatus('ambiguous-release-tags')
        version = '.'.join(map(str, version))
        if tuple(map(int, version.split('.'))) < tuple(map(int, inventory['version'].split('.'))):
            raise ExceptionStatus('installed-newer-than-release')
        candidate = {'source': str(source), 'authority': trusted, 'tag': tag, 'sha': sha, 'version': version}
        directory = Path(tempfile.mkdtemp(prefix='figma-flow-release-'))
        self.temporary = directory
        os.chmod(directory, 0o700)
        repo = directory / 'repo'
        self.command(['git', 'init', '--bare', str(repo)], raw=True)
        self.command(['git', '-C', str(repo), 'fetch', '--depth=1', candidate['authority'], 'refs/tags/' + candidate['tag']], raw=True)
        if self.git('-C', str(repo), 'rev-parse', 'FETCH_HEAD') != candidate['sha']:
            raise ExceptionStatus('release-changed-during-check')
        archive = self.command(['git', '-C', str(repo), 'archive', '--format=tar', 'FETCH_HEAD'], raw=True)
        release = directory / 'release'
        release.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream.getmembers():
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                    raise ExceptionStatus('unsafe-source')
            stream.extractall(release, filter='data')
        if package(release, self.name) != candidate['version']:
            raise ExceptionStatus('release-manifest-mismatch')
        descriptor = workspace.read(release / '.agents/plugins/marketplace.json', limit=128 * 1024)
        declared = descriptor.get('plugins', [])
        if descriptor.get('name') != inventory['marketplace'] or len(declared) != 1 or declared[0].get('name') != self.name or declared[0].get('source') != {'source':'local', 'path':'./'}:
            raise ExceptionStatus('release-marketplace-mismatch')
        if inventory.get('source_type') != 'git':
            workspace.atomic(release / '.figma-flow-source.json', workspace.encode({'schema':'figma-flow-startup-source-v1',
                'authority':trusted, 'tag':tag, 'sha':sha}))
        expected = source_bytes(release)
        return {**candidate, 'path':str(release), 'bytes':expected}

    def discard(self):
        if self.temporary is not None:
            shutil.rmtree(self.temporary)
            self.temporary = None

    def retain(self, source, prefix, expected):
        base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state').expanduser()
        if not base.is_absolute():
            raise ExceptionStatus('private-state-unverified')
        package_state = workspace.private_dir(base / self.name, create=True)
        state = workspace.private_dir(package_state / 'plugin-updates', create=True)
        directory = Path(tempfile.mkdtemp(prefix=prefix, dir=state))
        snapshot = directory / 'source'
        shutil.copytree(source, snapshot, symlinks=True, ignore=shutil.ignore_patterns('.git'))
        for path in snapshot.rglob('*'):
            if not path.is_symlink():
                path.chmod(0o700 if path.is_dir() or path.stat().st_mode & 0o100 else 0o600)
        snapshot.chmod(0o700)
        if package(snapshot, self.name) != package(source, self.name) or source_bytes(snapshot) != expected:
            raise ExceptionStatus('retained-source-unverified')
        return directory, snapshot

    def upgrade(self, candidate, inventory):
        if inventory.get('shared'):
            raise ExceptionStatus('shared-marketplace')
        release = Path(candidate['path'])
        expected = candidate['bytes']
        if package(release, self.name) != candidate['version']:
            raise ExceptionStatus('release-manifest-mismatch')
        if inventory.get('source_type') not in {'local', 'git'}:
            raise ExceptionStatus('source-recovery-unverified')
        target = self.name + '@' + inventory['marketplace']
        old_root = Path(inventory['marketplace_root'])
        old_bytes = source_bytes(old_root)
        if (package(old_root, self.name) != inventory['version'] or
                source_bytes(inventory['installedPath']) != old_bytes or source_bytes(release) != expected):
            raise ExceptionStatus('source-changed-before-update')
        descriptor = workspace.read(old_root / '.agents/plugins/marketplace.json', limit=128 * 1024)
        rows = descriptor.get('plugins', [])
        if (descriptor.get('name') != inventory['marketplace'] or len(rows) != 1 or
                rows[0].get('name') != self.name or rows[0].get('source') != {'source':'local', 'path':'./'}):
            raise ExceptionStatus('source-recovery-unverified')
        if any(Path(name).name in {'compiler.key', 'connection.json', 'capability'} or '.control' in Path(name).parts for name in old_bytes):
            raise ExceptionStatus('private-workspace-in-package')
        original_authority = authority(inventory.get('authority') or candidate['authority'])
        original_ref = None
        if inventory['source_type'] == 'git':
            if (old_root / '.git').exists():
                if self.git('status', '--porcelain', '--untracked-files=all', cwd=old_root):
                    raise ExceptionStatus('source-recovery-unverified')
                if authority(self.git('remote', 'get-url', 'origin', cwd=old_root)) != original_authority:
                    raise ExceptionStatus('source-authority-mismatch')
                original_ref = self.git('rev-parse', 'HEAD', cwd=old_root)
            else:
                provenance = old_root / '.figma-flow-source.json'
                if provenance.exists():
                    saved = workspace.read(provenance, private=True, limit=4096)
                    if (saved.get('schema') == 'figma-flow-startup-source-v1' and
                            authority(saved.get('authority')) == original_authority and
                            isinstance(saved.get('tag'), str) and saved['tag'].removeprefix('v') == inventory['version']):
                        original_ref = saved.get('sha')
            if not isinstance(original_ref, str) or not re.fullmatch(r'[a-f0-9]{40,64}', original_ref):
                raise ExceptionStatus('exact-git-recovery-unavailable')
        recovery_root, snapshot = self.retain(old_root, 'recovery-', old_bytes)
        _, release = self.retain(release, 'release-', expected)
        self.recovery = {'old_source': str(old_root), 'recovery_source': str(snapshot),
                         'candidate_source': str(release), 'authority': original_authority,
                         'original_source_type':inventory['source_type'], 'original_ref':original_ref}
        workspace.atomic(recovery_root / 'recovery.json', workspace.encode({
            'schema':'figma-flow-startup-recovery-v1', 'name':self.name, 'version':inventory['version'],
            'marketplace':inventory['marketplace'], 'source_type':'local', **self.recovery,
            'source_sha256':workspace.digest(workspace.encode(old_bytes))}))
        try:
            self.command(['codex', 'plugin', 'remove', target, '--json'])
            self.command(['codex', 'plugin', 'marketplace', 'remove', inventory['marketplace'], '--json'])
            if inventory.get('source_type') == 'git':
                self.command(['codex', 'plugin', 'marketplace', 'add', candidate['authority'], '--ref', candidate['tag'], '--json'])
            else:
                self.command(['codex', 'plugin', 'marketplace', 'add', str(release), '--json'])
            installed = self.command(['codex', 'plugin', 'add', target, '--json'])
            if installed.get('pluginId') != target or installed.get('name') != self.name or installed.get('marketplaceName') != inventory['marketplace'] or installed.get('version') != candidate['version'] or not isinstance(installed.get('installedPath'), str):
                raise ExceptionStatus('installed-package-unverified')
            destination = Path(installed['installedPath'])
            if package(destination, self.name) != candidate['version'] or source_bytes(destination) != expected:
                raise ExceptionStatus('installed-bytes-unverified')
        except (OSError, ValueError, KeyError, TypeError):
            if inventory.get('source_type') in {'local', 'git'}:
                try:
                    try:
                        self.command(['codex', 'plugin', 'marketplace', 'remove', inventory['marketplace'], '--json'])
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                    self.command(['codex', 'plugin', 'marketplace', 'add', str(snapshot), '--json'])
                    restored = self.command(['codex', 'plugin', 'add', target, '--json'])
                    if restored.get('pluginId') == target and package(restored['installedPath'], self.name) == inventory['version'] and source_bytes(restored['installedPath']) == old_bytes:
                        self.recovery['restored_source_type'] = 'local'
                        raise ExceptionStatus('update-failed-restored-original')
                except ExceptionStatus as error:
                    if str(error) == 'update-failed-restored-original':
                        raise
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            raise ExceptionStatus('update-failed-recovery-required') from None
        self.native_root = destination
        return {'status': 'updated', 'version': candidate['version'], 'installedPath': str(destination), 'source': str(release)}

    def native(self, path, apply):
        if self.native_root.resolve() != ROOT.resolve():
            return self.command([sys.executable, '-B', str(self.native_root / 'tools/plugin_startup.py'),
                'native', '--workspace', str(path), '--figma-access', 'allowed', *([] if apply else ['--read-only'])], timeout=1800)
        with (workspace.locked(path) if apply else nullcontext(workspace.private_dir(path))) as root:
            directory = root / '.control'
            if directory.exists():
                uncertain = False
                for request in (directory / 'requests').glob('*.json'):
                    request = workspace.read(request, private=True, limit=32768)
                    if request.get('state') in {'pending', 'claimed'}:
                        raise ExceptionStatus('active-or-uncertain-native-operation')
                    uncertain |= request.get('state') == 'uncertain' and request.get('operation') != 'read'
                marker = directory / 'uncertainty.json'
                if marker.exists():
                    from figma_control import SCHEMA as CONTROL_SCHEMA
                    pending = workspace.read(marker, private=True, limit=1_000_000)
                    if not isinstance(pending, dict) or pending.get('schema') != CONTROL_SCHEMA or not isinstance(pending.get('operations'), dict):
                        raise ValueError('Invalid private uncertainty marker')
                    uncertain = bool(pending['operations'])
                if uncertain:
                    raise ExceptionStatus('active-or-uncertain-native-operation')
            workspace.require_idle_publication(root)
            catalogue = workspace.current(root, repair=apply)
            for row in catalogue['tasks']:
                if 'generator_args' not in row or 'input_pins' not in row:
                    raise ExceptionStatus('legacy-task-requires-admission')
                workspace.task_artifacts(root, row)
            expected_runtime = workspace.runtime_info(catalogue)
            if catalogue.get('runtime') == expected_runtime and all(row.get('generator_sha256') == expected_runtime['implementation'] for row in catalogue['tasks']):
                return {'status':'files-current', 'loaded':'unverified', 'action':'Reopen the SAME registered Figma Flow plugin to verify its loaded runtime.'}
        if not apply:
            return {'status':'update-available', 'loaded':'unverified'}
        for row in catalogue['tasks']:
            workspace.replay(path, row['key'], row['revision'])
        with workspace.locked(path) as root:
            workspace.publish(root, workspace.current(root))
        return {'status':'files-updated', 'loaded':'unverified', 'action':'Reopen the SAME registered Figma Flow plugin; files do not prove the loaded runtime.'}


def ensure(adapter, *, apply=True, figma_access='forbidden', workspace_path=None, source=None, pin=None):
    result = {'schema':SCHEMA, 'mode':'ensure' if apply else 'check', 'codex':{},
              'native':{'status':'exception', 'reason':'figma-access-forbidden' if figma_access == 'forbidden' else 'workspace-unspecified'}}
    if figma_access not in {'forbidden', 'allowed'}:
        raise ValueError('Explicit Figma access policy required')
    try:
        inventory = adapter.inventory()
        if pin or inventory.get('pin'):
            raise ExceptionStatus('explicit-version-pin')
        if inventory.get('shared'):
            raise ExceptionStatus('shared-marketplace')
        if figma_access == 'allowed' and workspace_path is not None:
            try:
                native_check = adapter.native(workspace_path, False)
                if isinstance(native_check, dict) and native_check.get('status') == 'exception':
                    raise ExceptionStatus('native-ownership-or-inputs-unverified')
            except (OSError, ValueError, KeyError, TypeError):
                raise ExceptionStatus('native-ownership-or-inputs-unverified') from None
        candidate = adapter.candidate(source, inventory)
        if candidate['version'] == inventory['version'] and source_bytes(inventory['installedPath']) == candidate['bytes']:
            result['codex'] = {'status':'current', 'version':inventory['version'], 'authority':candidate['authority']}
        elif not apply:
            result['codex'] = {'status':'update-available', 'version':candidate['version']}
        else:
            result['codex'] = adapter.upgrade(candidate, inventory)
    except ExceptionStatus as error:
        result['codex'] = {'status':'exception', 'reason':str(error)}
        if getattr(adapter, 'recovery', None):
            result['codex']['recovery'] = adapter.recovery
    except (OSError, ValueError, KeyError, TypeError):
        result['codex'] = {'status':'exception', 'reason':'package-check-unverified'}
    cleanup = getattr(adapter, 'discard', None)
    if callable(cleanup):
        try:
            cleanup()
        except OSError:
            pass
    # Forbidden access exits before native adapters, probes, locks or filesystem writes.
    if figma_access == 'allowed' and result['codex'].get('status') not in {'current', 'updated'}:
        result['native'] = {'status':'exception', 'reason':'package-update-unverified', 'loaded':'unverified'}
    elif figma_access == 'allowed' and workspace_path is not None:
        try:
            result['native'] = adapter.native(workspace_path, apply)
        except ExceptionStatus as error:
            result['native'] = {'status':'exception', 'reason':str(error), 'loaded':'unverified'}
        except (OSError, ValueError, KeyError, TypeError):
            result['native'] = {'status':'exception', 'reason':'native-inputs-or-ownership-unverified', 'loaded':'unverified'}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('command', choices=['check', 'ensure', 'native'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--authority')
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--figma-access', choices=['forbidden', 'allowed'], default='forbidden')
    parser.add_argument('--pin')
    parser.add_argument('--read-only', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'native':
        if args.figma_access != 'allowed' or args.workspace is None:
            parser.error('native requires explicit allowed Figma access and workspace')
        try:
            value = HostAdapter().native(args.workspace, not args.read_only)
        except (OSError, ValueError, KeyError, TypeError):
            value = {'status':'exception', 'reason':'native-inputs-or-ownership-unverified', 'loaded':'unverified'}
        print(json.dumps(value))
        return 0
    print(json.dumps(ensure(HostAdapter(authority_url=args.authority), apply=args.command == 'ensure',
          figma_access=args.figma_access, workspace_path=args.workspace, source=args.source, pin=args.pin), ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
