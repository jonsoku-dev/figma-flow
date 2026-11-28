"""Single owner of owner-only (0600) atomic file writes."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile

PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700


def ensure_private_parent(path) -> Path:
    """Create the parent directory owner-only and tighten it when it is group/world accessible."""
    parent = Path(path).expanduser().absolute().parent
    if os.name == 'posix':
        parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        if parent.stat().st_mode & 0o077:
            os.chmod(parent, PRIVATE_DIR_MODE)
    else:
        parent.mkdir(parents=True, exist_ok=True)
    return parent


@contextmanager
def locked_update(path: Path):
    """Serialize read/modify/replace on this path. Keep the lock inode across replacements."""
    path = Path(path)
    path.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + '.lock')
    if lock_path.is_symlink():
        raise ValueError('Refusing a symlink lock')
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(lock_path, flags, PRIVATE_FILE_MODE)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Private file lock must be a regular file')
        if os.name == 'posix':
            import fcntl
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Private file lock must be owner-only')
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        yield
    finally:
        os.close(fd)


def atomic_write(path, raw: bytes, *, create_parent: bool = False, mode: int = PRIVATE_FILE_MODE) -> None:
    """Replace ``path`` with ``raw`` via fsync + rename; defaults to owner-only (0600)."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing a symlink output')
    if create_parent:
        ensure_private_parent(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if os.name == 'posix':
                os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_dir_fd(
    parent_fd: int,
    name: str,
    raw: bytes,
    *,
    exclusive: bool = False,
    temp_prefix: str = '.tmp-',
) -> None:
    """Write ``name`` relative to an already-opened directory descriptor with O_NOFOLLOW (0600)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    temporary = None
    try:
        if exclusive:
            descriptor = os.open(name, flags, PRIVATE_FILE_MODE, dir_fd=parent_fd)
        else:
            temporary = temp_prefix + secrets.token_hex(12)
            descriptor = os.open(temporary, flags, PRIVATE_FILE_MODE, dir_fd=parent_fd)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary:
            os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            temporary = None
    finally:
        if temporary:
            os.unlink(temporary, dir_fd=parent_fd)


def atomic_write_json(path, data, *, create_parent: bool = True) -> None:
    raw = (json.dumps(data, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('utf-8')
    atomic_write(Path(path).expanduser().absolute(), raw, create_parent=create_parent)
