"""Single owner of local loopback endpoints and the control-server HTTP client.

Hosts, default ports and timeouts come from ``library/figma-profile/policy.json``
``controlEndpoint`` (validated by ``relay_limits.control_endpoint``). The same
policy is embedded in the generated plugin runtime as ``WORKSPACE_PROFILE_POLICY``,
so Python tools and the Figma bridge read one source of truth.
"""
from __future__ import annotations

import http.client
import schema_ids
import json
import os
from pathlib import Path
import re
from typing import NamedTuple

import relay_limits
import runtime_limits

POLICY_PATH = relay_limits.ROOT / 'library' / 'figma-profile' / 'policy.json'
_POLICY = json.loads(POLICY_PATH.read_bytes())
ENDPOINT = relay_limits.control_endpoint(_POLICY)
_TRANSPORT = relay_limits.control_transport(_POLICY)
READINESS_LIMIT = _TRANSPORT['readinessReplyBytes']
CHANGE_REPLY_LIMIT = _TRANSPORT['changeReplyBytes']

CONTROL_SCHEMA = schema_ids.ID['control']
BIND_HOST = ENDPOINT['bindHost']
ORIGIN_HOST = ENDPOINT['originHost']
IPV4_LOOPBACK_HOSTS = (ORIGIN_HOST, BIND_HOST)
LOOPBACK_HOSTS = frozenset(ENDPOINT['loopbackHosts'])
FIGMA_ORIGINS = frozenset({'null', 'https://www.figma.com', 'https://figma.com'})
DEFAULT_PORTS = dict(ENDPOINT['defaultPorts'])
ORIGIN_PATTERN = re.compile(r'http://' + re.escape(ORIGIN_HOST) + r':([0-9]{1,5})')
READINESS_ROUTE = '/control/readiness'
_TOKEN = re.compile(r'[a-f0-9]{64}')


class Reply(NamedTuple):
    status: int
    body: bytes
    content_length: str | None


def timeout_seconds(kind: str) -> float:
    return ENDPOINT['timeoutsMs'][kind] / 1000


def valid_port(port) -> bool:
    return type(port) is int and port in runtime_limits.UNPRIVILEGED_PORTS


def host_header(port: int) -> str:
    return f'{ORIGIN_HOST}:{port}'


def bind_header(port: int) -> str:
    return f'{BIND_HOST}:{port}'


def accepted_host_headers(port: int) -> set[str]:
    return {f'{ORIGIN_HOST}:{port}', f'{BIND_HOST}:{port}'}


def origin(port: int) -> str:
    return f'http://{ORIGIN_HOST}:{port}'


def bind_origin(port: int) -> str:
    return f'http://{BIND_HOST}:{port}'


def origin_pattern(suffix: str = '') -> re.Pattern[str]:
    return re.compile(r'http://' + re.escape(ORIGIN_HOST) + r':[0-9]+' + re.escape(suffix))


def read_endpoint(root, *, limit: int = 4096) -> tuple[int, str] | None:
    """Fail-open read of ``control.json`` → ``(port, token)``; never writes."""
    path = Path(root).expanduser().absolute() / 'control.json'
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        if os.name == 'posix':
            stat = path.stat()
            if stat.st_mode & 0o077 or stat.st_uid != os.getuid():
                return None
        data = json.loads(path.read_bytes().decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get('schema') != CONTROL_SCHEMA:
        return None
    port, token = data.get('port'), data.get('token')
    if not valid_port(port) or not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return None
    return port, token


def connect(port: int, *, timeout_kind: str = 'request', timeout: float | None = None) -> http.client.HTTPConnection:
    return http.client.HTTPConnection(BIND_HOST, port, timeout=timeout_seconds(timeout_kind) if timeout is None else timeout)


def request(port: int, token: str, method: str, route: str, body: bytes | None = None, *, limit: int,
            timeout_kind: str = 'request', timeout: float | None = None) -> Reply:
    """Authenticated loopback request. Reads at most ``limit + 1`` bytes; callers reject ``len > limit``.

    Raises ``OSError``/``http.client.HTTPException`` on transport failure.
    """
    connection = connect(port, timeout_kind=timeout_kind, timeout=timeout)
    headers = {'Host': host_header(port), 'Authorization': 'Bearer ' + token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        connection.request(method, route, body, headers)
        response = connection.getresponse()
        return Reply(response.status, response.read(limit + 1), response.getheader('Content-Length'))
    finally:
        connection.close()


def post_json(port: int, token: str, route: str, payload, *, limit: int, timeout_kind: str = 'request',
              timeout: float | None = None) -> Reply:
    body = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
    return request(port, token, 'POST', route, body, limit=limit, timeout_kind=timeout_kind, timeout=timeout)


def probe_readiness(port: int, token: str, *, timeout_kind: str = 'probe') -> dict | None:
    """Read-only readiness probe; returns the decoded object or ``None`` when unreachable/invalid."""
    try:
        reply = request(port, token, 'POST', READINESS_ROUTE, b'{}', limit=READINESS_LIMIT, timeout_kind=timeout_kind)
        if reply.status != 200 or len(reply.body) > READINESS_LIMIT:
            return None
        value = json.loads(reply.body)
    except (OSError, ValueError, UnicodeError, RecursionError, http.client.HTTPException):
        return None
    return value if isinstance(value, dict) else None


def probe_workspace(root, *, timeout_kind: str = 'probe') -> dict | None:
    endpoint = read_endpoint(root)
    return None if endpoint is None else probe_readiness(*endpoint, timeout_kind=timeout_kind)
