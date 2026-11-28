#!/usr/bin/env python3
"""Run a test command and its descendants with a fresh, owner-only XDG config root."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


@contextmanager
def private_test_config():
    with tempfile.TemporaryDirectory(prefix='figma-flow-test-config-') as directory:
        yield str(Path(directory).resolve())


def terminate(signum, _frame):
    raise SystemExit(128 + signum)


def main(argv):
    if not argv:
        print('Usage: test_env.py COMMAND [ARG ...]', file=sys.stderr)
        return 2
    with private_test_config() as xdg:
        env = {**os.environ, 'XDG_CONFIG_HOME': xdg}
        try:
            process = subprocess.Popen(argv, env=env, start_new_session=os.name == 'posix')
        except OSError as error:
            print(f'test_env: {error}', file=sys.stderr)
            return 127
        try:
            code = process.wait()
        finally:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.wait()
        return code if code >= 0 else 128 - code


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main(sys.argv[1:]))
