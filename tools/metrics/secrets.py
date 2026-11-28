"""Secret resolution and redaction helpers for local metrics configuration."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

_ENV_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
_SECRET_QUERY = re.compile(
    r'([?&](?:access_token|refresh_token|id_token|sync_token|local_sync_token|chat_token|token|api_key|apikey|key|secret|password|capability|bearer|auth)=)[^&#\s"\'<>]*',
    re.IGNORECASE,
)
_HOME_PATH = re.compile(r'(?:/Users/[^/\s"\'<>]+|/home/[^/\s"\'<>]+|[A-Za-z]:\\Users\\[^\\/\s"\'<>]+)')
_BEARER = re.compile(r'Bearer\s+[A-Za-z0-9._~+/=-]{6,}')
MAX_SECRET_FILE_BYTES = 16384


def redact_value(value: Any) -> str:
    """Strip credentials, tokens, and personal home paths from diagnostic text."""
    text = str(value)
    text = re.sub(r'([a-z][a-z0-9+.-]*://)[^/\s"\'<>]+@', r'\1', text, flags=re.IGNORECASE)
    text = _HOME_PATH.sub('[home]', text)
    text = _SECRET_QUERY.sub(r'\1[redacted]', text)
    text = _BEARER.sub('Bearer [redacted]', text)
    return text


def _read_private_secret_file(raw_path: str) -> str:
    path = Path(raw_path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Secret file reference must be an existing regular file without symlinks')
    if os.name == 'posix':
        stat = path.stat()
        if stat.st_mode & 0o077 or stat.st_uid != os.getuid():
            raise ValueError('Secret file must have owner-only permissions (0600)')
    if path.stat().st_size > MAX_SECRET_FILE_BYTES:
        raise ValueError('Secret file exceeds 16 KiB limit')
    return path.read_text(encoding='utf-8').rstrip('\r\n')


class SecretResolver:
    """Resolve ${ENV_VAR} and file:/path references at send/auth time only."""

    def __init__(self, environ: dict[str, str] | None = None):
        self._environ = environ if environ is not None else os.environ

    def resolve(self, value: str) -> str:
        """Resolve secret references inside a configuration string."""
        if not isinstance(value, str):
            raise ValueError('Secret reference must be a string')
        if value.startswith('file:'):
            return _read_private_secret_file(value[5:])

        def replace_env(match: re.Match[str]) -> str:
            var = match.group(1)
            resolved = self._environ.get(var)
            if resolved is None or resolved == '':
                raise ValueError(f'Missing environment variable for secret reference: {var}')
            return resolved

        return _ENV_PATTERN.sub(replace_env, value)

    def resolve_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        """Resolve all header values without mutating the source mapping."""
        if not headers:
            return {}
        return {str(key): self.resolve(str(val)) for key, val in headers.items()}

    def inspect_refs(self, value: Any) -> list[dict[str, Any]]:
        """Inspect secret references in a config tree without ever returning secret values."""
        findings: list[dict[str, Any]] = []

        def walk(item: Any) -> None:
            if isinstance(item, dict):
                for val in item.values():
                    walk(val)
            elif isinstance(item, list):
                for val in item:
                    walk(val)
            elif isinstance(item, str):
                if item.startswith('file:'):
                    raw_path = item[5:]
                    try:
                        _read_private_secret_file(raw_path)
                        findings.append({'kind': 'file', 'ref': redact_value(raw_path), 'present': True, 'error': None})
                    except (OSError, ValueError) as exc:
                        findings.append({'kind': 'file', 'ref': redact_value(raw_path), 'present': False, 'error': redact_value(exc)})
                else:
                    for match in _ENV_PATTERN.finditer(item):
                        var = match.group(1)
                        present = bool(self._environ.get(var))
                        findings.append({
                            'kind': 'env',
                            'ref': var,
                            'present': present,
                            'error': None if present else f'Environment variable {var} is unset or empty',
                        })

        walk(value)
        return findings
