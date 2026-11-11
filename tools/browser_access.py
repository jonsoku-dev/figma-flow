#!/usr/bin/env python3
"""Configure Figma Flow browser network access in an @playwright/mcp config file."""
import argparse
import ipaddress
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


RELOAD_STATUS = "Reload or reconnect the MCP server, then verify network.allowedOrigins and network.blockedOrigins with browser_get_config before browsing."


def _origin(value):
    if not isinstance(value, str) or not value or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("URL must be a non-empty http(s) URL without whitespace or control characters")
    if "\\" in value:
        raise ValueError("URL must not contain backslashes")
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            raise ValueError("URL must use http or https and include a host")
        if "@" in parsed.netloc or "*" in parsed.netloc:
            raise ValueError("URL credentials and wildcard authorities are not allowed")
        if parsed.netloc.endswith(":"):
            raise ValueError("URL authority has an empty port")
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid URL authority: {exc}") from None
    if not host:
        raise ValueError("URL must include a valid host")
    if "%" in host:
        raise ValueError("Percent-encoded hosts and IPv6 zone identifiers are not allowed")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("URL port must be between 1 and 65535")

    try:
        address = ipaddress.ip_address(host)
        canonical_host = f"[{address.compressed}]" if address.version == 6 else str(address)
    except ValueError:
        if ":" in host or "%" in host:
            raise ValueError("Invalid IP address host") from None
        if not host.isascii():
            raise ValueError("Use the browser's ASCII/punycode hostname for an international domain")
        canonical_host = host.lower()
        labels = canonical_host.removesuffix(".").split(".")
        if (not canonical_host or len(canonical_host) > 253 or
                any(not label or len(label) > 63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in labels)):
            raise ValueError("Invalid DNS host")
        if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]*)", labels[-1]):
            raise ValueError("Use a canonical IPv4 address instead of a numeric DNS host")

    scheme = parsed.scheme.lower()
    default_port = 80 if scheme == "http" else 443
    suffix = f":{port}" if port is not None and port != default_port else ""
    return f"{scheme}://{canonical_host}{suffix}"


def _existing_origin(value):
    origin = _origin(value)
    parsed = urlsplit(value)
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Existing network.allowedOrigins entries must be origins without paths or queries")
    return origin


def register(config_path, urls):
    """Add exact URL origins while preserving existing blocked origins and options."""
    return _configure(config_path, urls, auto_allow=False)


def configure_auto_allow(config_path):
    """Allow network requests in Figma Flow's dedicated isolated browser."""
    return _configure(config_path, [], auto_allow=True)


def _configure(config_path, urls, *, auto_allow):
    path = Path(config_path)
    urls = list(urls)
    if not urls and not auto_allow:
        raise ValueError("Provide at least one --url")
    requested = [_origin(url) for url in urls]
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink config path")

    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read existing config: {exc}") from None
        if not isinstance(config, dict):
            raise ValueError("Existing config must be a JSON object")
    else:
        config = {}

    browser = config.setdefault("browser", {})
    server = config.setdefault("server", {})
    network = config.setdefault("network", {})
    if not all(isinstance(item, dict) for item in (browser, server, network)):
        raise ValueError("Existing browser, server, and network settings must be objects")
    browser.setdefault("isolated", True)
    browser.setdefault("contextOptions", {})
    if not isinstance(browser["contextOptions"], dict):
        raise ValueError("Existing browser.contextOptions must be an object")
    browser["contextOptions"].setdefault("serviceWorkers", "block")
    server.setdefault("host", "127.0.0.1")
    server.setdefault("allowedHosts", ["localhost", "127.0.0.1"])
    capabilities = config.setdefault("capabilities", [])
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        raise ValueError("Existing capabilities must be a list of names")
    if "config" not in capabilities:
        capabilities.append("config")

    allowed = network.setdefault("allowedOrigins", [])
    if not isinstance(allowed, list):
        raise ValueError("Existing network.allowedOrigins must be a list")
    origins = []
    for entry in allowed:
        origin = _existing_origin(entry)
        if origin not in origins:
            origins.append(origin)
    for origin in requested:
        if origin not in origins:
            origins.append(origin)
    if auto_allow:
        blocked = network.get("blockedOrigins", [])
        if not isinstance(blocked, list) or not all(isinstance(item, str) for item in blocked):
            raise ValueError("Existing network.blockedOrigins must be a list of strings")
        browser["isolated"] = True
        server["host"] = "127.0.0.1"
        server["allowedHosts"] = ["localhost", "127.0.0.1"]
        origins = []
        network["blockedOrigins"] = []
    network["allowedOrigins"] = origins

    output = (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == output:
        pass
    else:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    return {"config_path": str(path.resolve()), "origins": origins, "status": RELOAD_STATUS,
            "network_policy": "auto-allow" if auto_allow else "exact-origins", "config": config,
            "mcp_server": {"command": "npx",
                           "args": ["-y", "@playwright/mcp@0.0.85", "--config", str(path.resolve())],
                           "cwd": str(Path.cwd().resolve()), "startup_timeout_sec": 60,
                           "tool_timeout_sec": 60, "enabled": True,
                           "disabled_tools": ["browser_run_code_unsafe"]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to @playwright/mcp JSON config")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--url", action="append", help="Explicit target URL (repeatable)")
    mode.add_argument("--auto-allow", action="store_true",
                      help="Allow all network origins in Figma Flow's dedicated isolated browser")
    args = parser.parse_args(argv)
    try:
        result = configure_auto_allow(args.config) if args.auto_allow else register(args.config, args.url)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        print(f"browser_access: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
