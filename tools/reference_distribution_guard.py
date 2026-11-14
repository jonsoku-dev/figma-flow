#!/usr/bin/env python3
"""Guard Git refs, working trees, and distribution ZIPs against reference leaks.

Checks forbidden paths and ephemeral evidence unconditionally. When optional
--reference-zip and/or --reference-literals inputs are supplied, also detects
raw ZIP matches, renamed/CRLF-normalized member SHA-256 matches, and 1-line
unique reference literal matches. Emits paths, SHA-256 digests, rule IDs, and
counts only; private text and personal paths are never printed or stored.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
import skill_dependencies  # noqa: E402

SCHEMA = 'figma-flow-reference-guard-v1'
MAX_SCAN_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 100000
AMBIGUOUS_MAX_BYTES = 128
HEX_SHA256 = re.compile(r'^[0-9a-f]{64}$')

LOCKFILES = frozenset({
    'package-lock.json', 'npm-shrinkwrap.json', 'pnpm-lock.yaml',
    'yarn.lock', 'bun.lock', 'bun.lockb',
})
PRIVATE_DIRS = frozenset({
    '.figma-flow', '.git', '.herdr', '.local', '.private', '.references',
    '.tmp', '.venv', '__pycache__', '_references', 'local-reference',
    'node_modules', 'private', 'reference-zips', 'scratch', 'tmp',
})
ROOT_EPHEMERAL_DIRS = frozenset({'captures', 'evidence', 'receipts'})
EPHEMERAL_FILES = frozenset({
    'acceptance.json', 'design-review.json', 'generation-requests.json',
    'live-readback.json', 'optional-readback-replay.json', 'receipt.json',
    'renderer-snapshot.json',
})
COMMON_BOILERPLATE = frozenset({
    '.env.example', '.eslintrc', '.eslintrc.cjs', '.eslintrc.js', '.eslintrc.json',
    '.gitattributes', '.gitignore', '.npmrc', '.nvmrc', '.prettierrc',
    '.prettierrc.json', 'components.json', 'favicon.ico', 'globals.css',
    'jsconfig.json', 'license', 'license.md', 'license.txt', 'next.config.js',
    'next.config.mjs', 'next.config.ts', 'package.json', 'postcss.config.cjs',
    'postcss.config.js', 'postcss.config.mjs', 'readme.md', 'robots.txt',
    'tailwind.config.js', 'tailwind.config.mjs', 'tailwind.config.ts',
    'tsconfig.json', 'utils.js', 'utils.ts',
})


class GuardError(Exception):
    """Raised when inputs, Git state, or archives cannot be verified."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_ref(ref: str) -> str:
    if (not ref or ref.startswith(('-', '/')) or '..' in ref or '\\' in ref
            or re.search(r'[\x00-\x20~^:?*\[]', ref)):
        raise GuardError(f'unsafe git ref: {ref}')
    return ref


def normalize_rel_path(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or '\x00' in raw or raw.startswith('/') or '\\' in raw:
        raise GuardError(f'unsafe relative path: {raw}')
    cleaned = raw
    while cleaned.startswith('./'):
        cleaned = cleaned[2:]
    if not cleaned:
        raise GuardError('invalid empty relative path')
    path = PurePosixPath(cleaned)
    if path.is_absolute() or any(part in ('', '.', '..') for part in path.parts):
        raise GuardError(f'unsafe path traversal: {raw}')
    return path


def _normalize_text(text: str) -> tuple[str, str, str]:
    has_crlf = '\r\n' in text
    no_crlf = text.replace('\r\n', '\n')
    has_cr = '\r' in no_crlf
    has_lf = '\n' in text.replace('\r\n', '')
    if has_crlf and (has_lf or has_cr):
        ending = 'mixed'
    elif has_crlf:
        ending = 'crlf'
    elif has_cr:
        ending = 'cr'
    elif has_lf:
        ending = 'lf'
    else:
        ending = 'none'
    norm_text = no_crlf.replace('\r', '\n').lstrip('\ufeff')
    return ending, norm_text, sha256_hex(norm_text.encode('utf-8'))


def analyze_text(data: bytes) -> tuple[str, str | None, str | None]:
    """Return (line_ending_kind, normalized_lf_text_or_none, normalized_sha256_or_none)."""
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            text = data.decode('utf-16')
            if '\x00' not in text:
                return _normalize_text(text)
        except UnicodeDecodeError:
            pass
    if b'\x00' in data:
        return 'binary', None, None
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return 'binary_or_non_utf8', None, None
    return _normalize_text(text)


def run_git(repo: Path, *args: str, input_bytes: bytes = b'') -> bytes:
    proc = subprocess.run(['git', '-C', str(repo), *args], input=input_bytes,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise GuardError(proc.stderr.decode('utf-8', 'replace').strip() or f'git {args[0]} failed')
    return proc.stdout


def batch_git_blobs(repo: Path, oids: list[str]) -> dict[str, bytes]:
    if not oids:
        return {}
    unique = list(dict.fromkeys(oids))
    raw = run_git(repo, 'cat-file', '--batch', input_bytes=''.join(f'{o}\n' for o in unique).encode('ascii'))
    out, pos, total = {}, 0, len(raw)
    for oid in unique:
        nl = raw.find(b'\n', pos)
        if nl == -1:
            raise GuardError('truncated git cat-file header')
        parts = raw[pos:nl].decode('ascii', 'replace').split()
        pos = nl + 1
        if len(parts) != 3 or parts[1] != 'blob':
            raise GuardError(f'unexpected git object for {oid}')
        size = int(parts[2])
        if pos + size + 1 > total:
            raise GuardError(f'truncated git blob for {oid}')
        out[parts[0]] = raw[pos:pos + size]
        pos += size + 1
    return out


def load_reference_zips(paths: list[Path]) -> tuple[list[dict], dict[str, list[int]], dict[str, list[dict]], dict[str, list[dict]]]:
    zips_meta, by_zip_sha, by_raw, by_norm = [], {}, {}, {}
    for idx, raw_path in enumerate(paths):
        path = raw_path.expanduser()
        if not path.is_file():
            raise GuardError(f'reference ZIP not found (index {idx})')
        try:
            zip_bytes = path.read_bytes()
        except OSError as exc:
            raise GuardError(f'unable to read reference ZIP (index {idx}): {type(exc).__name__}') from exc
        if len(zip_bytes) > MAX_SCAN_BYTES:
            raise GuardError(f'reference ZIP exceeds size limit (index {idx})')
        zip_sha = sha256_hex(zip_bytes)
        by_zip_sha.setdefault(zip_sha, []).append(idx)
        member_count = crlf_count = total_uncompressed = 0
        unique_hashes = set()
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    member_count += 1
                    if member_count > MAX_ARCHIVE_MEMBERS:
                        raise GuardError(f'reference ZIP exceeds member limit (index {idx})')
                    total_uncompressed += max(0, info.file_size)
                    if total_uncompressed > MAX_SCAN_BYTES:
                        raise GuardError(f'reference ZIP uncompressed content exceeds size limit (index {idx})')
                    data = zf.read(info.filename)
                    raw_sha = sha256_hex(data)
                    ending, _, norm_sha = analyze_text(data)
                    if ending in ('crlf', 'mixed'):
                        crlf_count += 1
                    unique_hashes.add(raw_sha)
                    rec = {
                        'idx': idx, 'zip_sha': zip_sha, 'raw_sha': raw_sha,
                        'base': PurePosixPath(info.filename.replace('\\', '/').strip('/')).name.lower(),
                        'ending': ending, 'trivial': len(data.strip()) == 0,
                    }
                    by_raw.setdefault(raw_sha, []).append(rec)
                    if norm_sha is not None:
                        by_norm.setdefault(norm_sha, []).append(rec)
        except zipfile.BadZipFile as exc:
            raise GuardError(f'invalid reference ZIP (index {idx})') from exc
        except OSError as exc:
            raise GuardError(f'unable to read reference ZIP (index {idx}): {type(exc).__name__}') from exc
        if member_count == 0:
            raise GuardError(f'reference ZIP has no file members (index {idx})')
        zips_meta.append({
            'reference_index': idx, 'zip_sha256': zip_sha, 'byte_length': len(zip_bytes),
            'member_count': member_count, 'unique_raw_hashes': len(unique_hashes),
            'crlf_member_count': crlf_count,
        })
    return zips_meta, by_zip_sha, by_raw, by_norm


def load_reference_literals(paths: list[Path]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Load private literal rules without storing or printing literal text or file paths."""
    meta, rules = [], []
    for idx, raw_path in enumerate(paths):
        path = raw_path.expanduser()
        if not path.is_file():
            raise GuardError(f'reference literals file not found (index {idx})')
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            raise GuardError(f'unable to read reference literals (index {idx}): {type(exc).__name__}') from exc
        if len(raw_bytes) > MAX_SCAN_BYTES:
            raise GuardError(f'reference literals file exceeds size limit (index {idx})')
        try:
            text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise GuardError(f'reference literals file must be UTF-8 (index {idx})') from exc
        parsed: list[tuple[str, str]] = []
        stripped = text.lstrip()
        if path.suffix.lower() == '.json' or stripped.startswith(('{', '[')):
            try:
                obj = json.loads(text)
            except ValueError as exc:
                raise GuardError(f'invalid JSON in reference literals (index {idx})') from exc
            items = obj.get('rules') if isinstance(obj, dict) and 'rules' in obj else obj
            if isinstance(items, dict):
                for key, val in items.items():
                    if not isinstance(key, str) or not key.strip() or not isinstance(val, str) or not val.strip():
                        raise GuardError(f'invalid literal mapping entry (index {idx})')
                    parsed.append((key, val))
            elif isinstance(items, list):
                for n, item in enumerate(items, 1):
                    if isinstance(item, str) and item.strip():
                        parsed.append((f'lit-{idx + 1}-{n}', item))
                    elif isinstance(item, dict):
                        raw_id = item.get('id')
                        rid = f'lit-{idx + 1}-{n}' if raw_id is None else raw_id
                        lit = (item['literal'] if 'literal' in item
                               else item['pattern'] if 'pattern' in item
                               else item.get('text'))
                        if not isinstance(rid, str) or not rid.strip() or not isinstance(lit, str) or not lit.strip():
                            raise GuardError(f'invalid literal rule object (index {idx})')
                        parsed.append((rid, lit))
                    else:
                        raise GuardError(f'invalid literal rule item (index {idx})')
            else:
                raise GuardError(f'unsupported JSON structure in reference literals (index {idx})')
        else:
            for line_no, line in enumerate(text.splitlines(), 1):
                if line.strip() and not line.lstrip().startswith('#'):
                    parsed.append((f'lit-{idx + 1}-{line_no}', line))
        if not parsed:
            raise GuardError(f'reference literals file has no rules (index {idx})')
        for rid, lit in parsed:
            norm = lit.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff')
            if not norm.strip():
                raise GuardError(f'empty literal rule {rid} (index {idx})')
            rules.append((rid, norm))
        meta.append({'literals_index': idx, 'file_sha256': sha256_hex(raw_bytes), 'rule_count': len(parsed)})
    return meta, rules


def classify_path(raw_rel: str, stripped_rel: str) -> tuple[str, str, str] | None:
    raw_parts = [p.lower() for p in PurePosixPath(raw_rel).parts]
    parts = [p.lower() for p in PurePosixPath(stripped_rel).parts]
    base = parts[-1]
    if any(p == 'magicuidesign' or p.startswith(('magicuidesign-', 'reference-audit-')) for p in raw_parts):
        return 'forbidden_path', 'blocked_forbidden_reference_path', 'reference_archive_or_extracted_dir'
    if base.endswith(('.zip', '.tar', '.tgz', '.tar.gz')) or base.startswith('figma-flow-plugin-') or base.endswith('.sha256'):
        return 'forbidden_path', 'blocked_forbidden_archive', 'archive_or_release_artifact'
    if raw_rel.lower() == '.codex/config.toml' or stripped_rel.lower() == '.codex/config.toml' or raw_rel.lower().endswith('/.codex/config.toml'):
        return 'forbidden_path', 'blocked_private_config', 'personal_codex_config'
    if any(p in PRIVATE_DIRS for p in raw_parts[:-1]) or (len(parts) > 1 and parts[0] in PRIVATE_DIRS):
        return 'forbidden_path', 'blocked_private_or_scratch_dir', 'protected_local_directory'
    if base == '.ds_store' or base.endswith(('.pyc', '.pyo')):
        return 'forbidden_path', 'blocked_local_build_artifact', 'os_or_python_cache_artifact'
    if base in LOCKFILES:
        return 'forbidden_path', 'blocked_disallowed_lockfile', 'package_manager_lockfile'
    if (base == '.env' or base.startswith('.env.')) and base != '.env.example':
        return 'forbidden_path', 'blocked_env_secret_file', 'dotenv_secret_file'
    if len(parts) > 1 and parts[0] in ROOT_EPHEMERAL_DIRS:
        return 'ephemeral_evidence', 'blocked_ephemeral_evidence', 'root_ephemeral_evidence_dir'
    if base in EPHEMERAL_FILES or base.endswith(('-receipt.json', '.receipt.json', '-readback.json', '.tmp', '.bak', '.orig')):
        return 'ephemeral_evidence', 'blocked_ephemeral_evidence', 'ephemeral_receipt_or_temp_file'
    return None


def _add_pinned_map(pinned: set[tuple[str, str]], prefix: str, files: dict, label: str) -> None:
    for rel, digest in files.items():
        if not isinstance(rel, str) or not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest):
            raise GuardError(f'invalid pinned file digest in {label}')
        safe_rel = normalize_rel_path(rel).as_posix()
        pinned.add((f'{prefix}/{safe_rel}', digest))


def _verify_acorn_provenance(get_bytes) -> list[tuple[str, str]]:
    raw_prov = get_bytes('vendor/acorn/PROVENANCE.txt')
    if raw_prov is None:
        return []
    try:
        lines = [line.strip() for line in raw_prov.decode('utf-8').splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise GuardError('invalid vendor/acorn/PROVENANCE.txt encoding') from exc
    if (len(lines) < 4 or not lines[0].startswith('Acorn ')
            or not lines[1].startswith('https://registry.npmjs.org/acorn/-/acorn-')
            or not lines[2].startswith('sha512-')
            or not lines[3].startswith('Files:')):
        raise GuardError('invalid vendor/acorn/PROVENANCE.txt format')
    verified = [('vendor/acorn/PROVENANCE.txt', sha256_hex(raw_prov))]
    lic = get_bytes('vendor/acorn/LICENSE')
    if lic is not None:
        lic_text = lic.decode('utf-8', 'replace')
        if 'MIT License' not in lic_text or 'Copyright' not in lic_text:
            raise GuardError('invalid vendor/acorn/LICENSE content')
        verified.append(('vendor/acorn/LICENSE', sha256_hex(lic)))
    acorn_js = get_bytes('vendor/acorn/acorn.js')
    if acorn_js is not None:
        if b'global.acorn' not in acorn_js and b'exports.acorn' not in acorn_js:
            raise GuardError('invalid vendor/acorn/acorn.js bundle')
        verified.append(('vendor/acorn/acorn.js', sha256_hex(acorn_js)))
    return verified


def load_legitimate_pins(get_bytes) -> set[tuple[str, str]]:
    pinned: set[tuple[str, str]] = set()
    raw_skills = get_bytes('vendor/skills/manifest.json')
    if raw_skills is not None:
        try:
            manifest_obj = json.loads(raw_skills.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as exc:
            raise GuardError('invalid vendor/skills/manifest.json') from exc
        if (not isinstance(manifest_obj, dict)
                or manifest_obj.get('schema') != skill_dependencies.SCHEMA
                or not isinstance(manifest_obj.get('skills'), dict)):
            raise GuardError('unsupported vendor/skills/manifest.json schema')
        pinned.add(('vendor/skills/manifest.json', sha256_hex(raw_skills)))
        readme = get_bytes('vendor/skills/README.md')
        if readme is not None:
            pinned.add(('vendor/skills/README.md', sha256_hex(readme)))
        for item in manifest_obj['skills'].values():
            if not isinstance(item, dict) or not isinstance(item.get('directory'), str) or not isinstance(item.get('files'), dict):
                raise GuardError('invalid entry in vendor/skills/manifest.json')
            prefix = normalize_rel_path(item['directory'].rstrip('/')).as_posix()
            _add_pinned_map(pinned, prefix, item['files'], 'vendor/skills/manifest.json')

    for lib_dir in ('library/figma-api', 'library/figma-widget', 'library/figma-rest'):
        raw_src = get_bytes(f'{lib_dir}/source.json')
        if raw_src is None:
            continue
        try:
            src_obj = json.loads(raw_src.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as exc:
            raise GuardError(f'invalid {lib_dir}/source.json') from exc
        if not isinstance(src_obj, dict) or not isinstance(src_obj.get('files'), dict):
            raise GuardError(f'invalid files map in {lib_dir}/source.json')
        pinned.add((f'{lib_dir}/source.json', sha256_hex(raw_src)))
        _add_pinned_map(pinned, lib_dir, src_obj['files'], f'{lib_dir}/source.json')

    pinned.update(_verify_acorn_provenance(get_bytes))
    return pinned


def _symlink_target_is_unsafe(stripped_path: str, target_bytes: bytes | None) -> bool:
    if target_bytes is None:
        return True
    target = target_bytes.decode('utf-8', 'surrogateescape').replace('\\', '/')
    if not target or '\x00' in target or target.startswith(('/', '~')):
        return True
    parent_parts = list(PurePosixPath(stripped_path).parts[:-1])
    depth = len(parent_parts)
    resolved_parts = list(parent_parts)
    for part in PurePosixPath(target).parts:
        if part in ('', '.'):
            continue
        if part == '..':
            if depth == 0:
                return True
            depth -= 1
            resolved_parts.pop()
        else:
            depth += 1
            resolved_parts.append(part)
    resolved_rel = '/'.join(resolved_parts)
    if resolved_rel and classify_path(resolved_rel, resolved_rel) is not None:
        return True
    target_parts = [p.lower() for p in PurePosixPath(target).parts if p not in ('', '.', '..')]
    return any(p in PRIVATE_DIRS or p == 'magicuidesign' or p.startswith(('magicuidesign-', 'reference-audit-'))
               for p in target_parts)


def _normalize_entry_kind(kind_or_symlink: bool | str) -> str:
    if isinstance(kind_or_symlink, str):
        return kind_or_symlink
    return 'symlink' if kind_or_symlink else 'file'


def evaluate_entries(target_kind: str, target_label: str, entries: list[tuple[str, str, bytes | None, bool | str]],
                     pinned: set[tuple[str, str]], zip_index: tuple, literal_rules: list[tuple[str, str]]) -> tuple[dict, list[dict]]:
    zips_meta, _, by_raw, by_norm = zip_index
    counts = {
        'scanned_files': 0, 'forbidden_paths': 0, 'ephemeral_evidence': 0,
        'exact_reference_zips': 0, 'unique_reference_matches': 0,
        'ambiguous_reference_matches': 0, 'reference_literal_matches': 0,
        'trivial_empty_skipped': 0, 'legitimate_dependency_preserved': 0,
    }
    findings: list[dict] = []
    encoded_rules = [(rid, lit, lit.encode('utf-8')) for rid, lit in literal_rules]

    for raw_path, stripped_path, data, kind_or_symlink in entries:
        counts['scanned_files'] += 1
        entry_kind = _normalize_entry_kind(kind_or_symlink)
        hit = classify_path(raw_path, stripped_path)
        if hit is not None:
            category, disposition, rule = hit
            counts['forbidden_paths' if category == 'forbidden_path' else 'ephemeral_evidence'] += 1
            findings.append({
                'category': category, 'disposition': disposition, 'rule': rule,
                'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                'byte_length': len(data) if data is not None else 0,
                'target_sha256': sha256_hex(data) if data is not None else None,
            })
            continue
        if entry_kind == 'gitlink':
            counts['forbidden_paths'] += 1
            findings.append({
                'category': 'forbidden_path', 'disposition': 'blocked_gitlink_submodule', 'rule': 'gitlink_or_nested_repo',
                'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                'byte_length': 0, 'target_sha256': None,
            })
            continue
        if entry_kind == 'symlink':
            if _symlink_target_is_unsafe(stripped_path, data):
                counts['forbidden_paths'] += 1
                findings.append({
                    'category': 'forbidden_path', 'disposition': 'blocked_forbidden_symlink', 'rule': 'unsafe_or_forbidden_symlink',
                    'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                    'byte_length': len(data) if data is not None else 0,
                    'target_sha256': sha256_hex(data) if data is not None else None,
                })
                continue
            if encoded_rules and data is not None:
                norm_target = data.decode('utf-8', 'surrogateescape').replace('\r\n', '\n').replace('\r', '\n')
                for rule_id, literal, _ in encoded_rules:
                    if literal in norm_target:
                        counts['reference_literal_matches'] += 1
                        findings.append({
                            'category': 'reference_literal_match',
                            'disposition': 'blocked_reference_literal_match',
                            'rule_id': rule_id,
                            'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                            'target_sha256': sha256_hex(data), 'line': 1,
                            'match_count': norm_target.count(literal),
                        })
            continue
        if entry_kind == 'dir' or data is None:
            continue

        raw_sha = sha256_hex(data)
        if (stripped_path, raw_sha) in pinned:
            counts['legitimate_dependency_preserved'] += 1
            continue
        if len(data.strip()) == 0:
            counts['trivial_empty_skipped'] += 1
            continue

        ending, norm_text, norm_sha = analyze_text(data)
        if zips_meta:
            raw_matches = [m for m in by_raw.get(raw_sha, []) if not m['trivial']]
            norm_matches = [m for m in by_norm.get(norm_sha, []) if not m['trivial']] if norm_sha else []
            matches = raw_matches or norm_matches
            if matches:
                chosen = matches[0]
                base = PurePosixPath(stripped_path).name.lower()
                is_ambiguous = base in COMMON_BOILERPLATE or len(data) < AMBIGUOUS_MAX_BYTES
                category = 'ambiguous_reference_match' if is_ambiguous else 'unique_reference_match'
                disposition = 'blocked_ambiguous_review_required' if is_ambiguous else 'blocked_unique_reference_match'
                counts['ambiguous_reference_matches' if is_ambiguous else 'unique_reference_matches'] += 1
                findings.append({
                    'category': category, 'disposition': disposition,
                    'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                    'target_sha256': raw_sha, 'target_normalized_sha256': norm_sha,
                    'byte_length': len(data), 'line_ending': ending,
                    'match_kind': 'exact_bytes' if raw_matches else 'normalized_text_lf',
                    'renamed': not any(m['base'] == base for m in (*raw_matches, *norm_matches)),
                    'reference_index': chosen['idx'], 'reference_zip_sha256': chosen['zip_sha'],
                    'reference_member_sha256': chosen['raw_sha'], 'reference_member_line_ending': chosen['ending'],
                })

        if encoded_rules:
            if norm_text is not None:
                for rule_id, literal, _ in encoded_rules:
                    pos = norm_text.find(literal)
                    if pos != -1:
                        counts['reference_literal_matches'] += 1
                        findings.append({
                            'category': 'reference_literal_match',
                            'disposition': 'blocked_reference_literal_match',
                            'rule_id': rule_id,
                            'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                            'target_sha256': raw_sha, 'line': norm_text.count('\n', 0, pos) + 1,
                            'match_count': norm_text.count(literal),
                        })
            else:
                norm_bytes = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
                for rule_id, _, lit_bytes in encoded_rules:
                    pos = norm_bytes.find(lit_bytes)
                    if pos != -1:
                        counts['reference_literal_matches'] += 1
                        findings.append({
                            'category': 'reference_literal_match',
                            'disposition': 'blocked_reference_literal_match',
                            'rule_id': rule_id,
                            'target_kind': target_kind, 'target_label': target_label, 'target_path': raw_path,
                            'target_sha256': raw_sha, 'line': norm_bytes.count(b'\n', 0, pos) + 1,
                            'match_count': norm_bytes.count(lit_bytes),
                        })
    return counts, findings


def collect_git_entries(repo: Path, ref: str | None) -> tuple[list[tuple[str, str, bytes | None, str]], callable]:
    if ref is not None:
        safe_ref(ref)
        run_git(repo, 'rev-parse', '--verify', f'{ref}^{{tree}}')
        raw = run_git(repo, 'ls-tree', '-r', '-z', ref)
    else:
        raw = run_git(repo, 'ls-files', '--stage', '-z')
    records, blob_oids = [], []
    for rec in raw.split(b'\0'):
        if not rec:
            continue
        meta, path_b = rec.split(b'\t', 1)
        fields = meta.decode('ascii').split()
        rel = normalize_rel_path(path_b.decode('utf-8', 'surrogateescape')).as_posix()
        if ref is not None:
            mode, obj_type, oid = fields[0], fields[1], fields[2]
            is_blob = obj_type == 'blob' and mode in ('100644', '100755')
            is_symlink = obj_type == 'blob' and mode == '120000'
        else:
            if len(fields) != 3 or fields[2] != '0':
                raise GuardError(f'unmerged staged entry: {rel}')
            mode, oid = fields[0], fields[1]
            is_blob = mode in ('100644', '100755')
            is_symlink = mode == '120000'
        kind = 'file' if is_blob else 'symlink' if is_symlink else 'gitlink' if mode == '160000' else 'other'
        records.append((kind, oid, rel))
        if is_blob or is_symlink:
            blob_oids.append(oid)
    blobs = batch_git_blobs(repo, blob_oids)
    by_path, entries = {}, []
    for kind, oid, rel in records:
        if kind == 'file':
            data = blobs[oid]
            by_path[rel] = data
            entries.append((rel, rel, data, 'file'))
        elif kind == 'symlink':
            entries.append((rel, rel, blobs[oid], 'symlink'))
        else:
            entries.append((rel, rel, None, 'gitlink'))
    return entries, lambda p: by_path.get(p)


def collect_worktree_entries(repo: Path) -> tuple[list[tuple[str, str, bytes | None, str]], callable]:
    root = repo.resolve(strict=True)
    raw_items = (
        *run_git(repo, 'ls-files', '-z').split(b'\0'),
        *run_git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'),
    )
    paths_map: dict[str, bool] = {}
    for item in raw_items:
        if not item:
            continue
        text = item.decode('utf-8', 'surrogateescape')
        is_dir_hint = text.endswith('/')
        rel = normalize_rel_path(text.rstrip('/') if is_dir_hint else text).as_posix()
        paths_map[rel] = paths_map.get(rel, False) or is_dir_hint

    by_path, entries = {}, []
    for rel in sorted(paths_map):
        cur = root
        is_symlink = False
        symlink_target: bytes | None = None
        for part in PurePosixPath(rel).parts:
            cur = cur / part
            if cur.is_symlink():
                is_symlink = True
                symlink_target = os.readlink(cur).encode('utf-8', 'surrogateescape')
                break
        if is_symlink:
            entries.append((rel, rel, symlink_target, 'symlink'))
            continue
        candidate = root.joinpath(*PurePosixPath(rel).parts)
        if candidate.is_dir() or paths_map[rel]:
            entries.append((rel, rel, None, 'gitlink'))
            continue
        if not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise GuardError(f'worktree file escapes repository root: {rel}')
        data = resolved.read_bytes()
        by_path[rel] = data
        entries.append((rel, rel, data, 'file'))
    return entries, lambda p: by_path.get(p)


def collect_target_zip_entries(zip_path: Path) -> tuple[str, str, int, list[tuple[str, str, bytes | None, str]], callable]:
    path = zip_path.expanduser()
    if not path.is_file():
        raise GuardError(f'target ZIP not found: {path.name}')
    try:
        zip_bytes = path.read_bytes()
    except OSError as exc:
        raise GuardError(f'unable to read target ZIP {path.name}: {type(exc).__name__}') from exc
    if len(zip_bytes) > MAX_SCAN_BYTES:
        raise GuardError(f'target ZIP exceeds size limit: {path.name}')
    zip_sha = sha256_hex(zip_bytes)
    raw_members = []
    total_uncompressed = 0
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            for info in zf.infolist():
                if info.is_dir():
                    d = info.filename.rstrip('/')
                    if d:
                        raw_members.append((normalize_rel_path(d).as_posix(), None, 'dir'))
                    continue
                if len(raw_members) >= MAX_ARCHIVE_MEMBERS:
                    raise GuardError(f'target ZIP exceeds member limit: {path.name}')
                total_uncompressed += max(0, info.file_size)
                if total_uncompressed > MAX_SCAN_BYTES:
                    raise GuardError(f'target ZIP uncompressed content exceeds size limit: {path.name}')
                is_sym = stat.S_ISLNK((info.external_attr >> 16) & 0o170000)
                raw_members.append((
                    normalize_rel_path(info.filename.rstrip('/')).as_posix(),
                    zf.read(info.filename),
                    'symlink' if is_sym else 'file',
                ))
    except zipfile.BadZipFile as exc:
        raise GuardError(f'invalid target ZIP: {path.name}') from exc

    files_only = [rel for rel, _, kind in raw_members if kind != 'dir']
    roots = {PurePosixPath(r).parts[0] for r in files_only if len(PurePosixPath(r).parts) > 1}
    prefix = (next(iter(roots)) + '/') if files_only and len(roots) == 1 and all(len(PurePosixPath(r).parts) > 1 for r in files_only) else ''
    by_stripped, entries = {}, []
    for rel, data, kind in raw_members:
        stripped = rel[len(prefix):] if prefix and rel.startswith(prefix) else rel
        if kind == 'dir':
            if classify_path(rel + '/placeholder', stripped + '/placeholder') is not None:
                entries.append((rel, stripped, None, 'dir'))
            continue
        if kind == 'file':
            by_stripped[stripped] = data
        entries.append((rel, stripped, data, kind))
    return path.name, zip_sha, len(zip_bytes), entries, lambda p: by_stripped.get(p)


def run_guard(*, repo: Path, refs: list[str] | None = None, staged: bool = False, worktree: bool = False,
              target_zips: list[Path] | None = None, reference_zips: list[Path] | None = None,
              reference_literals: list[Path] | None = None) -> dict:
    refs, target_zips = list(refs or []), list(target_zips or [])
    if not refs and not staged and not worktree and not target_zips:
        refs = ['HEAD']
    zip_index = load_reference_zips(list(reference_zips or []))
    literals_meta, literal_rules = load_reference_literals(list(reference_literals or []))
    totals = {
        'scanned_files': 0, 'forbidden_paths': 0, 'ephemeral_evidence': 0,
        'exact_reference_zips': 0, 'unique_reference_matches': 0,
        'ambiguous_reference_matches': 0, 'reference_literal_matches': 0,
        'trivial_empty_skipped': 0, 'legitimate_dependency_preserved': 0,
    }
    targets_checked, all_findings = [], []
    resolved_repo = repo.resolve(strict=True) if (refs or staged or worktree) else repo

    def scan(kind: str, label: str, entries, reader) -> int:
        counts, findings = evaluate_entries(kind, label, entries, load_legitimate_pins(reader), zip_index, literal_rules)
        for k, v in counts.items():
            totals[k] += v
        all_findings.extend(findings)
        return counts['scanned_files']

    for ref in refs:
        n = scan('git-ref', ref, *collect_git_entries(resolved_repo, ref))
        targets_checked.append({'kind': 'git-ref', 'ref': ref, 'file_count': n})
    if staged:
        n = scan('git-staged', 'INDEX', *collect_git_entries(resolved_repo, None))
        targets_checked.append({'kind': 'git-staged', 'label': 'INDEX', 'file_count': n})
    if worktree:
        n = scan('worktree', 'WORKTREE', *collect_worktree_entries(resolved_repo))
        targets_checked.append({'kind': 'worktree', 'label': 'WORKTREE', 'file_count': n})
    for zp in target_zips:
        label, zsha, zsize, entries, reader = collect_target_zip_entries(zp)
        targets_checked.append({'kind': 'target-zip', 'label': label, 'zip_sha256': zsha, 'byte_length': zsize, 'file_count': len(entries)})
        if zsha in zip_index[1]:
            totals['exact_reference_zips'] += 1
            all_findings.append({
                'category': 'exact_reference_zip', 'disposition': 'blocked_exact_reference_zip',
                'target_kind': 'target-zip', 'target_label': label, 'target_path': label,
                'target_sha256': zsha, 'byte_length': zsize,
                'reference_index': zip_index[1][zsha][0], 'reference_zip_sha256': zsha,
            })
        scan('target-zip', label, entries, reader)

    has_zips, has_lits = bool(zip_index[0]), bool(literal_rules)
    mode = ('paths-and-reference-hashes-and-literals' if has_zips and has_lits else
            'paths-and-reference-hashes' if has_zips else
            'paths-and-reference-literals' if has_lits else 'paths-only')
    status = 'blocked' if all_findings else ('clear' if (has_zips or has_lits) else 'paths_only_clear')
    omitted = [name for flag, name in ((has_zips, '--reference-zip'), (has_lits, '--reference-literals')) if not flag]
    notice = ('Checked forbidden paths, ephemeral evidence, reference ZIP hashes, and reference literals.'
              if not omitted else
              f'Checked paths and ephemeral evidence only for omitted inputs ({", ".join(omitted)} absent). '
              + ('No local reference lists supplied; path checks only.' if len(omitted) == 2 else 'Partial reference comparison only.'))
    return {
        'schema': SCHEMA, 'status': status, 'mode': mode,
        'reference_comparison_performed': has_zips,
        'reference_literals_checked': has_lits,
        'checks_performed': {'paths_and_ephemeral': True, 'reference_zips': has_zips, 'reference_literals': has_lits},
        'notice': notice, 'targets_checked': targets_checked,
        'reference_zips': zip_index[0], 'reference_literals': literals_meta,
        'counts': totals, 'findings': all_findings,
    }


def format_text(report: dict) -> str:
    c = report['counts']
    lines = [
        f"status: {report['status']} (mode={report['mode']})",
        f"notice: {report['notice']}",
        (f"counts: scanned={c['scanned_files']} forbidden_paths={c['forbidden_paths']} "
         f"ephemeral_evidence={c['ephemeral_evidence']} exact_zips={c['exact_reference_zips']} "
         f"unique_matches={c['unique_reference_matches']} ambiguous_matches={c['ambiguous_reference_matches']} "
         f"literal_matches={c['reference_literal_matches']} trivial_skipped={c['trivial_empty_skipped']} "
         f"legitimate_preserved={c['legitimate_dependency_preserved']}"),
    ]
    for f in report['findings']:
        rule_tag = f" rule={f['rule_id']}" if 'rule_id' in f else ''
        lines.append(f"- [{f['disposition']}] {f['target_kind']}:{f['target_path']} sha256={f.get('target_sha256') or 'none'}{rule_tag}")
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path('.'))
    p.add_argument('--ref', action='append', dest='refs', default=[])
    p.add_argument('--staged', action='store_true')
    p.add_argument('--worktree', action='store_true')
    p.add_argument('--target-zip', action='append', type=Path, default=[])
    p.add_argument('--reference-zip', action='append', type=Path, default=[])
    p.add_argument('--reference-literals', action='append', type=Path, default=[], help='optional private literal list (JSON or line-per-rule); never printed')
    p.add_argument('--format', choices=('json', 'text'), default='json')
    args = p.parse_args(argv)
    try:
        report = run_guard(repo=args.repo, refs=args.refs, staged=args.staged, worktree=args.worktree,
                           target_zips=args.target_zip, reference_zips=args.reference_zip,
                           reference_literals=args.reference_literals)
    except (GuardError, OSError, ValueError) as exc:
        msg = f'{type(exc).__name__}: {exc.strerror}' if isinstance(exc, OSError) else str(exc)
        if args.format == 'json':
            print(json.dumps({'schema': SCHEMA, 'status': 'error', 'error': msg}, ensure_ascii=False, indent=2))
        else:
            print(f'error: {msg}', file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n' if args.format == 'json' else format_text(report))
    return 1 if report['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
