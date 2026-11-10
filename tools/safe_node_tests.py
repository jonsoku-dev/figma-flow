#!/usr/bin/env python3
"""Run concrete Node tests with a read-only OS sandbox and project-only Node access."""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time


class TestRunError(ValueError):
    def __init__(self, message, results):
        super().__init__(message)
        self.results = results


def receipt_name(file):
    return hashlib.sha256(file.encode('utf-8')).hexdigest()[:16] + '.tap'


def safe_file(project, file):
    path = Path(file)
    if path.is_absolute() or '..' in path.parts or path.suffix not in ('.js', '.mjs', '.cjs'):
        raise ValueError('Test must be a local .js/.mjs/.cjs file')
    target = project / path
    for candidate in [target, *list(target.parents)[:len(path.parts) - 1]]:
        if candidate.is_symlink():
            raise ValueError('Test paths must not contain symlinks')
    info = target.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size == 0:
        raise ValueError('Tests must be nonempty, unlinked regular files')
    return target


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execute(argv, project, stdout, stderr, timeout):
    # No inherited tokens, NODE_OPTIONS, preload hooks, proxy settings, or module paths.
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    with stdout.open('x', encoding='utf-8') as output, stderr.open('x', encoding='utf-8') as errors:
        process = subprocess.Popen(argv, cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, shell=False, start_new_session=True)
        deadline = time.monotonic() + timeout
        budget = 4 * 1024 * 1024
        try:
            with selectors.DefaultSelector() as streams:
                streams.register(process.stdout, selectors.EVENT_READ, output)
                streams.register(process.stderr, selectors.EVENT_READ, errors)
                while streams.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return 124
                    for key, _ in streams.select(remaining):
                        data = os.read(key.fd, 65536)
                        if not data:
                            streams.unregister(key.fd)
                            continue
                        budget -= len(data)
                        if budget < 0:
                            return 125
                        key.data.buffer.write(data)
            return process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return 124
        finally:
            # The reporter may have stopped while a child is still running.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass  # macOS reports EPERM when the group holds only unreaped zombies.
            try:
                process.wait()
            finally:
                process.stdout.close()
                process.stderr.close()


# Only the parent emits TAP. Child stdout/stderr are diagnostic events, never results.
RUNNER = r"""
const { run } = require('node:test');
const { inspect } = require('node:util');
const [file, root, probe] = process.argv.slice(2);
const execArgv = ['--permission', '--allow-fs-read=' + root, '--no-addons', '--max-old-space-size=128'];
if (probe) execArgv.push('--allow-fs-read=' + file);
(async () => {
  const stream = run({files: [file], isolation: 'process', execArgv, concurrency: 1});
  let real = 0, fileSummary, finalSummary, count = 0, bytes = 0;
  console.log('TAP version 13');
  for await (const {type, data} of stream) {
    if (type === 'test:stdout' || type === 'test:stderr') {
      bytes += Buffer.byteLength(data.message);
      if (bytes > 1024 * 1024) throw Error('Test diagnostic output exceeded 1 MiB');
      process.stderr.write(data.message);
    } else if (type === 'test:pass' || type === 'test:fail') {
      if (++count > 10000) throw Error('Test result count exceeded 10000');
      const ok = type === 'test:pass';
      if (ok && data.entryFile === file && data.details.type === 'test' && !data.skip && !data.todo) real++;
      const name = JSON.stringify(String(data.name).slice(0, 512));
      console.log((ok ? 'ok ' : 'not ok ') + count + ' - ' + name);
      if (!ok) console.error(inspect(data.details.error, {depth: 4, maxStringLength: 1500}).slice(0, 3000));
    } else if (type === 'test:summary') {
      if (data.file === file && data.entryFile === file) fileSummary = data;
      if (!data.file) finalSummary = data;
    }
  }
  const counts = finalSummary?.counts;
  const passed = Boolean(real && fileSummary?.success && finalSummary?.success && counts.tests === counts.passed
    && !counts.failed && !counts.skipped && !counts.todo && !counts.cancelled);
  console.log('1..' + count);
  console.log('# tests ' + (counts?.tests ?? 0));
  console.log('# pass ' + (counts?.passed ?? 0));
  console.log('# fail ' + (counts?.failed ?? 0));
  console.log('# controller ' + JSON.stringify({passed, tests: counts?.tests ?? 0, failed: counts?.failed ?? 0}));
  process.exitCode = passed ? 0 : 1;
})().catch(e => { console.error(String(e)); process.exit(1); });
"""


PROBE = r"""
const test=require('node:test'),fs=require('node:fs'),net=require('node:net'),assert=require('node:assert/strict');
test('child permissions', async () => {
  for (const permission of ['net','child','worker','fs.write']) assert.equal(process.permission.has(permission),false);
  const denied=e=>['ERR_ACCESS_DENIED','EPERM','EACCES'].includes(e.code);
  for (const action of [()=>fs.readFileSync(OUTSIDE),()=>fs.writeFileSync(FORBIDDEN,'forbidden'),
                        ()=>require('node:child_process').spawnSync('/usr/bin/true')]) assert.throws(action,denied);
  await assert.rejects(new Promise((resolve,reject)=>{
    const socket=net.connect({host:'127.0.0.1',port:9});
    socket.on('connect',()=>{socket.destroy();resolve()}).on('error',reject);
  }),denied);
});
"""


def run_tests(project, files, receipt_dir, *, timeout=60):
    """Create immutable per-file receipts; TestRunError.results retains partial evidence.

    receipt and stderr paths in returned tests are relative to receipt_dir. Files
    are relative to project. Unsupported confinement fails before project code runs.
    """
    project, receipt_dir = Path(project).resolve(), Path(receipt_dir).absolute()
    if not files or len(files) != len(set(files)):
        raise ValueError('Select nonempty unique concrete test files')
    for path in project.rglob('*'):
        if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
            raise ValueError('Project symlinks and hardlinks are not permitted during execution')
    targets = {file: safe_file(project, file) for file in files}
    snapshots = {file: _digest(target) for file, target in targets.items()}
    executables = {}
    for name in ('node', 'codex'):
        value = shutil.which(name)
        if not value or Path(value).resolve().is_relative_to(project):
            raise ValueError(f'Trusted {name} executable unavailable outside project')
        executables[name] = str(Path(value).resolve())
    receipt_dir.mkdir(exist_ok=False)
    base = [executables['codex'], 'sandbox', '-P', ':read-only', '-C', str(project), '--', executables['node'], '--max-old-space-size=192']
    results = {'tests': [], 'sandbox': {'argv_prefix': base, 'profile': ':read-only', 'network': 'denied',
                                      'node_read_root': str(project), 'node_write': 'denied', 'environment': ['PATH', 'LANG', 'TZ']}}
    with tempfile.TemporaryDirectory(prefix='promotion-confinement-') as directory:
        control = Path(directory).resolve()
        runner = control / 'runner.cjs'
        runner.write_text(RUNNER)
        sentinel = control / 'sentinel'
        sentinel.write_text('confinement probe only')
        forbidden = control / 'must-not-exist'
        probe = control / 'probe.cjs'
        probe.write_text('const OUTSIDE=' + json.dumps(str(sentinel)) + ',FORBIDDEN=' + json.dumps(str(forbidden)) + ';\n' + PROBE)
        probe_argv = base + [str(runner), str(probe), str(project), 'probe']
        code = _execute(probe_argv, project, receipt_dir / 'sandbox.stdout.log', receipt_dir / 'sandbox.stderr.log', 10)
        results['sandbox'].update(isolation='process', controller_sha256=_digest(runner), probe_exit_code=code, probe_stdout='sandbox.stdout.log', probe_stderr='sandbox.stderr.log')
        if code or forbidden.exists():
            results['error_kind'] = 'sandbox'
            raise TestRunError('Confinement probe failed; no generated tests executed', results)
        return _run_files(project, receipt_dir, targets, snapshots, base, runner, results, timeout)


def _run_files(project, receipt_dir, targets, snapshots, base, runner, results, timeout):
    for file, target in targets.items():
        # Validate immediately before and after each invocation; OS confinement also
        # prevents the generated code from replacing project inputs during the run.
        if _digest(safe_file(project, file)) != snapshots[file]:
            results['error_kind'] = 'tamper'
            raise TestRunError('Test changed before execution', results)
        receipt = receipt_name(file)
        stderr = receipt.removesuffix('.tap') + '.stderr.log'
        argv = base + [str(runner), str(target), str(project)]
        code = _execute(argv, project, receipt_dir / receipt, receipt_dir / stderr, timeout)
        tap = (receipt_dir / receipt).read_text(encoding='utf-8')
        last_line = tap.splitlines()[-1] if tap else ''
        counts = json.loads(last_line.removeprefix('# controller ')) if last_line.startswith('# controller ') else {}
        passed = code == 0 and counts.get('passed') is True
        item = {'file': file, 'sha256': snapshots[file], 'argv': argv, 'exit_code': code, 'receipt': receipt,
                'receipt_sha256': _digest(receipt_dir / receipt), 'stderr': stderr,
                'tests': counts.get('tests', 0),
                'passed': passed, 'failed': counts.get('failed')}
        results['tests'].append(item)
        changed = _digest(safe_file(project, file)) != snapshots[file]
        if code or not passed or changed:
            results['error_kind'] = ('tamper' if changed else 'timeout' if code == 124 else
                                     'security' if re.search(r'ERR_ACCESS_DENIED|EPERM|EACCES|Operation not permitted', tap + (receipt_dir / stderr).read_text()) else 'assertion')
            raise TestRunError(f'Behavior tests failed or contained no real passing subtests: {file}', results)
    return results
