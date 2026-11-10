#!/usr/bin/env python3
"""Verify and resolve the immutable skill sources packaged with this plugin."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PLUGIN_ROOT / 'vendor/skills/manifest.json'
SCHEMA = 'figma-flow-skill-dependencies-v1'


def _relative(value, label):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError(label + ' must be a safe relative POSIX path')
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or path.as_posix() != value or any(part == '..' for part in path.parts):
        raise ValueError(label + ' must be a safe relative POSIX path')
    return path


def _inside(root, relative, label):
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(label + ' must not traverse symlinks')
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(label + ' escapes plugin root')
    return resolved


def verify_bundle():
    """Validate all manifest-pinned bytes, paths, identities, and licenses."""
    manifest_path = _inside(PLUGIN_ROOT, MANIFEST.relative_to(PLUGIN_ROOT), 'managed skill manifest')
    if not manifest_path.is_file():
        raise ValueError('managed skill manifest missing or unsafe')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA or not isinstance(manifest.get('skills'), dict):
        raise ValueError('unsupported managed skill manifest')
    skills = manifest['skills']
    if set(skills) != {'impeccable', 'design-taste-frontend', 'unslop'}:
        raise ValueError('managed skill set does not match the pinned plugin bundle')
    resolved = {}
    for identity, item in skills.items():
        if not isinstance(item, dict):
            raise ValueError('invalid managed skill record: ' + identity)
        directory = _relative(item.get('directory'), identity + ' directory')
        entrypoint = _relative(item.get('entrypoint'), identity + ' entrypoint')
        package = _inside(PLUGIN_ROOT, directory, identity + ' directory')
        if not package.is_dir():
            raise ValueError('managed skill directory missing: ' + identity)
        files = item.get('files')
        license_files = item.get('license_files')
        source_record = item.get('source')
        if not isinstance(files, dict) or not files or not isinstance(license_files, list) or not license_files:
            raise ValueError('managed skill needs complete file hashes and license coverage: ' + identity)
        if (not isinstance(source_record, dict) or
                not isinstance(source_record.get('repository'), str) or not source_record['repository'].startswith('https://') or
                not isinstance(source_record.get('commit'), str) or not re.fullmatch(r'[0-9a-f]{40}', source_record['commit'])):
            raise ValueError('managed skill source provenance is invalid: ' + identity)
        _relative(source_record.get('path'), identity + ' source path')
        extra_files = source_record.get('extra_files')
        if not isinstance(extra_files, list):
            raise ValueError('managed skill source extras are invalid: ' + identity)
        for name in extra_files:
            _relative(name, identity + ' source extra')
        expected = set()
        for relative_name, digest in files.items():
            relative = _relative(relative_name, identity + ' file')
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('invalid SHA256 in managed skill manifest: ' + identity)
            path = _inside(package, relative, identity + ' file')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('missing or modified managed skill file: ' + identity + '/' + relative_name)
            expected.add(relative.as_posix())
        if entrypoint.as_posix() not in expected:
            raise ValueError('entrypoint is not pinned: ' + identity)
        for name in license_files:
            relative = _relative(name, identity + ' license file')
            if relative.as_posix() not in expected:
                raise ValueError('license file is not pinned: ' + identity)
        if not isinstance(item.get('license'), str) or not item['license'].strip():
            raise ValueError('license identifier missing: ' + identity)
        observed = set()
        for path in package.rglob('*'):
            if path.is_symlink():
                raise ValueError('managed skill package contains symlink: ' + identity)
            if path.is_file():
                observed.add(path.relative_to(package).as_posix())
        if observed != expected:
            raise ValueError('managed skill package differs from complete manifest: ' + identity)
        source = _inside(package, entrypoint, identity + ' entrypoint')
        content = source.read_text(encoding='utf-8')
        if not re.search(r'^name:\s*' + re.escape(identity) + r'\s*$', content, re.M):
            raise ValueError('managed skill frontmatter identity mismatch: ' + identity)
        resolved[identity] = source
    return resolved


def resolve_skill(identity):
    """Return the verified plugin-owned SKILL.md for a known identity."""
    skills = verify_bundle()
    if identity not in skills:
        raise ValueError('unknown managed skill: ' + str(identity))
    return skills[identity]


def source_record(identity):
    """Return a portable receipt source and its current pinned hash."""
    path = resolve_skill(identity)
    return {'source': path.relative_to(PLUGIN_ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify every packaged skill and print JSON status')
    args = parser.parse_args()
    if not args.check:
        parser.error('use --check')
    try:
        skills = verify_bundle()
        print(json.dumps({'status': 'ready', 'skills': sorted(skills)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
