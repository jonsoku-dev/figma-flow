#!/usr/bin/env python3
"""Capture and verify the archived patch lineage without its source bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_knowledge import (  # noqa: E402
    CatalogError, atomic, assert_safe_dir, git, inventory, metadata_body, page_metadata,
    page_path, prefix, sha, substantive_page, check_links, SECTIONS,
)

SCHEMA = "figma-flow-legacy-patch-catalog-v1"
EXPECTED_HEAD = "bce939d1ea7e268ca5ef809eee63a5b3ce3bb29a"
EXPECTED_BUNDLE = "69aac71126cd34c9a451e091e134aec80ca6a9d401485830567c2869e8017192"
EXPECTED_CUTOFF = "0bd817701f3df66673e314007f768a6de404fd78"
EXPECTED_COMMITS = 39
EXPECTED_HEADS = {
    "codex/browser-access-unslop": "1f8d203dff972a1c98b8b2a49d5d0d20a838d80e",
    "codex/bundled-design-skills": "01735351c2d82f1372442192b9bf14fa6f049a74",
    "codex/remove-music-taste": "a787647678eb3d8369bbdc9930a18b90427ed122",
    "codex/skill-dependency-runtime": "b27dffc2e923347831d30368faaf8136f2cc3b54",
    "feat/readable-graph-specs": "61c0b1ea79abda7b258459e245a1187e1ecc0314",
    "feature/graph-ssot-roundtrip": "bf049266356987b6abbf62533a5d3b0f9c549b8b",
    "local-history/0.18.0": "738b84b96cb51b3fafc5ef2667409ca189b90652",
    "main": "90f9195600dd54131c80a817bebdd88fd63fe52a",
    "release/0.17.0": "616599f249500d3b437361959616298715a7712d",
    "release/0.17.1": "953bbd9999d0a01001c50916b074c28c836a1360",
    "release/0.17.2": "a3bc4285f3ade2aa8bebf88e6ad6f3b8f2e70f62",
    "release/0.17.3": "822c2156f56fd7edc485c5df956aa93a9faf5d74",
    "release/0.17.4": "ce60a7a897c0af15e445025f1eb05f1584129653",
    "release/0.17.5": "3725fe26fb24de31e3a4f6b82e3366c35d29e8e0",
    "release/0.17.6": "3541524341756e1b173223cbf49135931e3ff384",
    "release/0.18.0": "77d96ebc870b64227cccbae72c9c92aa245b544d",
    "release/0.18.1": EXPECTED_HEAD,
    "release/0.18.2": "10a379463f5bfa8af845420d3c3936b4b211596d",
    "release/unified-figma-0220": "f64d9a9e592343a0910cec236d358cd841b8e207",
}

def capture(source, main_ref, historical_ref, bundle_sha, wiki):
    wiki = Path(wiki).absolute()
    wiki = wiki.parent.resolve() / wiki.name
    if bundle_sha != EXPECTED_BUNDLE: raise CatalogError("unexpected archived bundle digest")
    if git(source, "rev-parse", f"{historical_ref}^{{commit}}").decode().strip() != EXPECTED_HEAD:
        raise CatalogError("historical ref does not resolve to pinned release head")
    canonical = git(source, "rev-parse", f"{main_ref}^{{commit}}").decode().strip()
    if canonical != EXPECTED_CUTOFF: raise CatalogError("main ref does not resolve to pinned canonical cutoff")
    actual = inventory(source, historical_ref)
    canonical_ids = set(git(source, "rev-list", canonical).decode().splitlines())
    commits = [c for c in actual["commits"] if c["commit"] not in canonical_ids]
    if len(commits) != EXPECTED_COMMITS: raise CatalogError(f"expected {EXPECTED_COMMITS} noncanonical commits, found {len(commits)}")
    heads = []
    for name, oid in EXPECTED_HEADS.items():
        if not git(source, "rev-parse", f"{oid}^{{commit}}", check=False): raise CatalogError(f"missing saved ref object: {name}")
        heads.append({"name": name, "commit": oid, "classification": "canonical" if oid in canonical_ids else "archived-only"})
    assert_safe_dir(wiki.parent.resolve(), wiki, create=True)
    pages = {}
    for commit in commits:
        path = page_path(wiki, commit["commit"])
        assert_safe_dir(wiki.parent.resolve(), path.parent, create=True)
        if path.is_symlink() or not path.is_file(): raise CatalogError(f"missing or unsafe authored page: {path}")
        raw = path.read_bytes()
        if raw.startswith(b"<!-- patch-knowledge\n"):
            meta, body = metadata_body(raw)
            if meta != page_metadata(commit): raise CatalogError(f"existing metadata mismatch: {path}")
        else:
            body = raw
            raw = prefix(page_metadata(commit)).encode() + body
            atomic(path, raw)
        pages[commit["commit"]] = sha(raw)
    catalog = {"schema": SCHEMA, "source_head": EXPECTED_HEAD, "bundle_sha256": EXPECTED_BUNDLE,
               "canonical_source_commit": canonical, "source_main_cutoff": EXPECTED_CUTOFF,
               "historical_ref": historical_ref, "saved_heads": heads, "commits": commits, "pages": pages}
    dest = wiki / "catalog.json"
    if dest.is_symlink(): raise CatalogError("symlink catalog rejected")
    atomic(dest, (json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    return catalog

def verify(wiki, source=None, repo_root=None):
    wiki = Path(wiki).absolute()
    wiki = wiki.parent.resolve() / wiki.name
    repo_root = Path(repo_root).resolve() if repo_root else wiki.parent.parent.resolve()
    assert_safe_dir(repo_root, wiki)
    path = wiki / "catalog.json"
    if path.is_symlink() or not path.is_file(): raise CatalogError("missing or unsafe legacy catalog")
    cat = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in (("schema", SCHEMA), ("source_head", EXPECTED_HEAD), ("bundle_sha256", EXPECTED_BUNDLE), ("canonical_source_commit", EXPECTED_CUTOFF), ("source_main_cutoff", EXPECTED_CUTOFF)):
        if cat.get(key) != expected: raise CatalogError(f"legacy catalog {key} mismatch")
    commits = cat.get("commits")
    if not isinstance(commits, list) or len(commits) != EXPECTED_COMMITS: raise CatalogError("legacy commit coverage mismatch")
    ids = [c.get("commit") for c in commits]
    if len(set(ids)) != EXPECTED_COMMITS or any(not re.fullmatch(r"[0-9a-f]{40}", x or "") for x in ids): raise CatalogError("invalid or duplicate legacy commit IDs")
    saved = cat.get("saved_heads")
    if not isinstance(saved, list) or {x.get("name"): x.get("commit") for x in saved} != EXPECTED_HEADS: raise CatalogError("saved ref coverage mismatch")
    if any(x.get("classification") not in ("canonical", "archived-only") for x in saved): raise CatalogError("invalid saved ref classification")
    if set(cat.get("pages", {})) != set(ids): raise CatalogError("legacy page hash coverage mismatch")
    errors = []
    for c in commits:
        p = page_path(wiki, c["commit"])
        try: assert_safe_dir(wiki.parent.resolve(), p.parent)
        except CatalogError as e: errors.append(str(e)); continue
        if p.is_symlink() or not p.is_file(): errors.append(f"missing or unsafe page: {p}"); continue
        raw = p.read_bytes()
        if sha(raw) != cat["pages"].get(c["commit"]): errors.append(f"page hash mismatch: {p}"); continue
        try: meta, body = metadata_body(raw)
        except CatalogError as e: errors.append(f"{p}: {e}"); continue
        if meta != page_metadata(c): errors.append(f"page metadata mismatch: {p}")
        text = body.decode("utf-8", "replace")
        errors.extend(substantive_page(p, text, True))
        if c["commit"] not in text: errors.append(f"source commit missing from human record: {p}")
        if c["files"] and not any(filename in text for filename in c["files"]): errors.append(f"no changed path referenced: {p}")
    if source:
        canonical = cat["canonical_source_commit"]
        if canonical != EXPECTED_CUTOFF or git(source, "rev-parse", f"{canonical}^{{commit}}").decode().strip() != canonical:
            raise CatalogError("canonical source object unavailable or changed")
        if git(source, "rev-parse", f"{cat['historical_ref']}^{{commit}}", check=False).decode().strip() != EXPECTED_HEAD:
            raise CatalogError("archived source head mismatch")
        full = inventory(source, cat["historical_ref"])
        canonical_ids = set(git(source, "rev-list", canonical).decode().splitlines())
        expected = [c for c in full["commits"] if c["commit"] not in canonical_ids]
        if expected != commits: errors.append("archived source inventory mismatch")
        for item in saved:
            if not git(source, "rev-parse", f"{item['commit']}^{{commit}}", check=False): errors.append(f"saved ref object missing: {item['name']}"); continue
            classification = "canonical" if item["commit"] in canonical_ids else "archived-only"
            if classification != item["classification"]: errors.append(f"saved ref ancestry mismatch: {item['name']}")
    link_sources = []
    for c in commits:
        p = page_path(wiki, c["commit"])
        if p.is_file() and not p.is_symlink(): link_sources.append((p, p.read_text(encoding="utf-8", errors="replace")))
    errors.extend(check_links(wiki, link_sources, wiki, repo_root))
    if errors: raise CatalogError("verification failed:\n- " + "\n- ".join(errors))
    return len(commits)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture"); c.add_argument("--source-git", required=True); c.add_argument("--main-ref", required=True); c.add_argument("--historical-ref", required=True); c.add_argument("--bundle-sha256", required=True); c.add_argument("--wiki", required=True)
    v = sub.add_parser("verify"); v.add_argument("--wiki", required=True); v.add_argument("--source-git")
    a = p.parse_args(argv)
    try:
        repo_root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip()).resolve()
        wiki = Path(a.wiki)
        if not wiki.is_absolute(): wiki = Path.cwd() / wiki
        wiki = Path(os.path.abspath(wiki))
        assert_safe_dir(repo_root, wiki)
        if a.command == "capture":
            result = capture(Path(a.source_git), a.main_ref, a.historical_ref, a.bundle_sha256, wiki); print(f"captured {len(result['commits'])} archived commits; source evidence pinned, original source path omitted")
        else:
            count = verify(wiki, Path(a.source_git) if a.source_git else None, repo_root)
            print(f"verified {count} archived pages; " + ("archived Git source verified" if a.source_git else "structural-only; archived source evidence unavailable in this clone"))
    except (CatalogError, OSError, ValueError, KeyError) as e:
        print(f"patch_knowledge_legacy: {e}", file=sys.stderr); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
