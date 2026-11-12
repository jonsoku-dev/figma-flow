"""Load operator-owned Compose secrets without putting them in command arguments."""
import os
from pathlib import Path
import sys

for name in ('LH_SECRET_KEY', 'LH_DB_PASSWORD'):
    if name + '_FILE' in os.environ:
        if os.environ.get(name):
            raise SystemExit(f'Use only {name}_FILE or {name}')
        value = Path(os.environ[name + '_FILE']).read_text().rstrip('\r\n')
        if not value:
            raise SystemExit(f'{name}_FILE must not be empty')
        os.environ[name] = value
os.execvp(sys.argv[1], sys.argv[1:])
