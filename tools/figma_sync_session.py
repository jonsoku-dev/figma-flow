"""Durable, local scalar-token apply sessions. State belongs outside the app."""
import fcntl
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

import apply_figma_change as change
import sync_figma_tokens as tokens
from design_system import compile_design, components_css, render


class SyncSession:
    def __init__(self, project, resolved, page_id, state_dir, prior_sync=None):
        self.project = Path(project).resolve(strict=True)
        self.resolved = Path(resolved).resolve(strict=True)
        self.page_id = page_id
        self.directory = Path(state_dir).absolute()
        if self.directory.is_symlink() or self.directory.resolve().is_relative_to(self.project):
            raise ValueError('Session state must be private and outside the project.')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory = self.directory.resolve(strict=True)
        if self.directory.stat().st_mode & 0o077:
            raise ValueError('Session state directory must have mode 0700.')
        self.prior = str(Path(prior_sync).resolve(strict=True)) if prior_sync else None

    def _read(self, path):
        return tokens.read_json(path)[0]

    def _write(self, path, value):
        fd, name = tempfile.mkstemp(prefix='.state-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(change.encode(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            Path(name).unlink(missing_ok=True)

    def _identity(self):
        return {'project': str(self.project), 'resolved': str(self.resolved),
                'resolved_sha256': tokens.read_json(self.resolved)[1], 'page_id': self.page_id,
                'graph_sha256': tokens.read_json(change.code.within(self.project, 'graph.json'))[1],
                'bindings_sha256': tokens.read_json(change.code.within(self.project, 'bindings.json'))[1]}

    def _hashes(self):
        return {name: hashlib.sha256(change.code.within(self.project, name).read_bytes()).hexdigest()
                for name in ('design.json', 'app/tokens.css', 'app/components.css')}

    def _css_guard(self):
        model = compile_design(self._read(change.code.within(self.project, 'design.json')))
        for name, expected in [('app/tokens.css', render(model, True)[1]),
                               ('app/components.css', components_css(model))]:
            if change.code.within(self.project, name).read_bytes() != expected.encode():
                raise ValueError(f'{name}: generated CSS differs from current design; refusing sync')

    def _validate(self, state):
        if state['identity'] != self._identity():
            raise ValueError('Session project, page, resolved, graph or bindings changed.')
        if state.get('prior'):
            wrapper = Path(state['prior'])
            result = self._read(wrapper / 'result.json')
            report, sha = tokens.read_json(wrapper / 'token-plan/impact.json')
            if result.get('status') != 'applied' or result.get('page_id') != self.page_id or result.get('token_report_sha256') != sha:
                raise ValueError('Session applied wrapper is corrupt or belongs to another page.')
            for key, path in [('design', self.project / 'design.json'), ('graph', self.project / 'graph.json'),
                              ('resolved', self.resolved)]:
                if report.get('pins', {}).get(key, {}).get('path') != str(path):
                    raise ValueError('Applied wrapper belongs to another project or resolved path.')
            sources = {key: tokens.read_json(path) for key, path in (
                ('design', self.project / 'design.json'), ('resolved', self.resolved),
                ('graph', self.project / 'graph.json'), ('before', state['snapshot']))}
            tokens.check_prior(wrapper / 'token-plan', sources, compile_design(sources['design'][0]), self.page_id)
        self._css_guard()

    def _result(self, wrapper, status):
        if wrapper is None:
            return dict(status=status, changed_tokens=[], screens=[], code_ids=[], files=[], report=None)
        receipt = self._read(wrapper / 'result.json')
        impact = self._read(wrapper / 'token-plan/impact.json')
        return dict(status=status, changed_tokens=impact['changed_roots'],
                    screens=receipt['declared_screens'], code_ids=receipt['observed_code_ids'],
                    files=receipt['planned_files'], report=str(wrapper))

    def _timestamp(self, readback):
        value = readback.get('exported_at')
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('exported_at must be an ISO UTC timestamp.')
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as error:
            raise ValueError('exported_at must be an ISO UTC timestamp.') from error
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError('exported_at must be an ISO UTC timestamp.')
        return parsed.isoformat()

    def _finish(self, state, pending):
        wrapper = Path(pending['slot']) / 'applied'
        os.chmod(wrapper, 0o700)
        impact = self._read(wrapper / 'token-plan/impact.json')
        state['latest_exported_at'] = self._timestamp(self._read(Path(pending['slot']) / 'snapshot.json'))
        if not impact['changes'] and state.get('prior'):
            self._write(self.directory / 'state.json', state)
            (self.directory / 'pending.json').unlink()
            shutil.rmtree(pending['slot'])
            return self._result(None, 'unchanged')
        for path in sorted(wrapper.rglob('*'), reverse=True) + [wrapper, Path(pending['slot'])]:
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        for directory in (self.project, self.project / 'app'):
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        state.update(prior=str(wrapper), snapshot=str(Path(pending['slot']) / 'snapshot.json'))
        self._write(self.directory / 'state.json', state)
        (self.directory / 'pending.json').unlink()
        return self._result(wrapper, 'baseline' if pending['baseline'] else 'applied')

    def _recover(self, state):
        journal = self.directory / 'pending.json'
        if not journal.exists():
            return None
        pending = self._read(journal)
        if pending['identity'] != self._identity():
            raise ValueError('Interrupted sync identity no longer matches.')
        value = pending.get('slot')
        if not isinstance(value, str):
            raise ValueError('Interrupted sync slot must be an owned run directory.')
        slot = Path(value)
        if (slot.parent != self.directory or not slot.name.startswith('run-') or slot.is_symlink()
                or not slot.is_dir() or slot.stat().st_uid != os.getuid() or slot.stat().st_mode & 0o077):
            raise ValueError('Interrupted sync slot must be an owned private run directory.')
        if any(path.is_symlink() for path in slot.rglob('*')):
            raise ValueError('Interrupted sync run directory must not contain symlinks.')
        wrapper = slot / 'applied'
        # A committed pointer wins over its leftover journal after a crash.
        if state.get('prior') == str(wrapper):
            self._validate(state)
            journal.unlink()
            return self._result(wrapper, 'baseline' if pending['baseline'] else 'applied')
        current = self._hashes()
        if (wrapper / 'token-plan/impact.json').is_file() and (wrapper / 'code-scope.json').is_file():
            impact, report_sha = tokens.read_json(wrapper / 'token-plan/impact.json')
            scope = self._read(wrapper / 'code-scope.json')
            changes = list(scope['plan'])
            if impact['changes']:
                changes.append({'path': 'design.json', 'content': (wrapper / 'token-plan/design.json').read_text()})
            expected = dict(pending['before'])
            expected.update({item['path']: hashlib.sha256(item['content'].encode()).hexdigest() for item in changes})
            if current == expected:
                receipt = {'status': 'applied', 'applied': True, 'page_id': self.page_id,
                           'planned_files': [item['path'] for item in changes],
                           'declared_screens': [item['screen_id'] for item in impact['screens']],
                           'observed_code_ids': sorted({node for use in scope['observed_consumers'] for node in use['code_ids']}),
                           'token_report_sha256': report_sha, 'expected_after': {item['path']: expected[item['path']] for item in changes}}
                receipt_path = wrapper / 'result.json'
                if receipt_path.exists():
                    existing = self._read(receipt_path)
                    expected_inputs = {
                        'design': pending['before']['design.json'],
                        'graph': pending['identity']['graph_sha256'],
                        'bindings': pending['identity']['bindings_sha256'],
                        'resolved': pending['identity']['resolved_sha256'],
                        'before': tokens.read_json(state['snapshot'] if state.get('prior') else slot / 'snapshot.json')[1],
                        'after': tokens.read_json(slot / 'snapshot.json')[1]}
                    if ('inputs' in existing and existing['inputs'] != expected_inputs) or any(
                            key in existing and existing[key] != receipt[key]
                            for key in ('token_report_sha256', 'expected_after', 'page_id')):
                        raise ValueError('Interrupted sync receipt pins differ from the journal or artifacts.')
                    receipt = dict(existing, **receipt)
                self._write(receipt_path, receipt)
                candidate = dict(state, prior=str(wrapper), snapshot=str(Path(pending['slot']) / 'snapshot.json'))
                self._validate(candidate)
                return self._finish(state, pending)
        if current != pending['before']:
            raise ValueError('Interrupted sync has partial writes or local edits; inspect pending.json before continuing.')
        if Path(pending['slot']).exists():
            shutil.rmtree(pending['slot'])
        journal.unlink()
        return None

    def last_comparison(self):
        """Return the last committed paired snapshot and result after a restart."""
        descriptor = os.open(self.directory / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state_path = self.directory / 'state.json'
            if not state_path.exists() and not (self.directory / 'pending.json').exists():
                return None
            state = self._read(state_path) if state_path.exists() else {
                'identity': self._identity(), 'prior': None, 'snapshot': None}
            if state['identity'] != self._identity():
                raise ValueError('Session project, page, resolved, graph or bindings changed.')
            if self.prior and state.get('prior') and state.get('bootstrap_source') != self.prior:
                raise ValueError('Bootstrap prior does not match the existing session chain.')
            self._recover(state)
            if state_path.exists():
                state = self._read(state_path)
            self._validate(state)
            if not state.get('prior'):
                return None
            snapshot = Path(state['snapshot'])
            slot = snapshot.parent
            if slot.parent != self.directory or not slot.name.startswith('run-'):
                return None
            if (slot.is_symlink() or snapshot.is_symlink() or snapshot.name != 'snapshot.json'
                    or state['prior'] != str(slot / 'applied')):
                raise ValueError('Committed comparison must belong to its session run directory.')
            wrapper = slot / 'applied'
            impact = self._read(wrapper / 'token-plan/impact.json')
            status = 'applied' if impact['changes'] else 'baseline'
            return self._read(snapshot), self._result(wrapper, status)

    def sync(self, readback):
        if not isinstance(readback, dict):
            raise ValueError('Native readback must be an object.')
        encoded = change.encode(readback)
        if len(encoded.encode()) > tokens.MAX_BYTES:
            raise ValueError('Native readback exceeds 2 MB.')
        descriptor = os.open(self.directory / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state_path = self.directory / 'state.json'
            state = self._read(state_path) if state_path.exists() else {'identity': self._identity(), 'prior': None, 'snapshot': None}
            if state['identity'] != self._identity():
                raise ValueError('Session project, page, resolved, graph or bindings changed.')
            if self.prior and state.get('prior') and state.get('bootstrap_source') != self.prior:
                raise ValueError('Bootstrap prior does not match the existing session chain.')
            recovered = self._recover(state)
            if recovered:
                state = self._read(state_path)
                if self._read(state['snapshot']) == readback:
                    return recovered
            if self.prior and state.get('prior') is None:
                wrapper = Path(self.prior)
                receipt = self._read(wrapper / 'result.json')
                report, sha = tokens.read_json(wrapper / 'token-plan/impact.json')
                if receipt.get('status') != 'applied' or receipt.get('page_id') != self.page_id or receipt.get('token_report_sha256') != sha:
                    raise ValueError('Bootstrap requires an intact applied wrapper for this page.')
                exported = Path(report['pins']['after']['path'])
                if tokens.read_json(exported)[1] != report['pins']['after']['sha256']:
                    raise ValueError('Bootstrap prior after export digest differs.')
                snapshot = self.directory / 'bootstrap.json'
                # Preserve the exact byte pin used by check_prior, including whitespace.
                snapshot.write_bytes(exported.read_bytes())
                os.chmod(snapshot, 0o600)
                state.update(prior=str(wrapper), snapshot=str(snapshot), bootstrap_source=self.prior)
                self._validate(state)
                self._write(state_path, state)
            self._validate(state)
            incoming_time = self._timestamp(readback)
            latest = state.get('latest_exported_at') or (self._timestamp(self._read(state['snapshot'])) if state.get('snapshot') else None)
            if latest and (incoming_time is None or datetime.fromisoformat(incoming_time) < datetime.fromisoformat(latest)):
                raise ValueError('Readback is older than the last accepted native snapshot.')
            if state.get('prior') and self._read(state['snapshot']) == readback:
                return self._result(None, 'unchanged')
            slot = Path(tempfile.mkdtemp(prefix='run-', dir=self.directory))
            snapshot = slot / 'snapshot.json'
            self._write(snapshot, readback)
            baseline = state.get('prior') is None
            pending = {'identity': state['identity'], 'slot': str(slot), 'before': self._hashes(), 'baseline': baseline}
            self._write(self.directory / 'pending.json', pending)
            try:
                change.run(self.project, self.resolved, snapshot if baseline else state['snapshot'], snapshot,
                           self.page_id, slot / 'applied', apply=True, prior_sync=state.get('prior'))
            except BaseException:
                if self._hashes() == pending['before']:
                    shutil.rmtree(slot)
                    (self.directory / 'pending.json').unlink()
                raise
            return self._finish(state, pending)
