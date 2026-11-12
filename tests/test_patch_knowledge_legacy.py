import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patch_knowledge_legacy", ROOT / "tools/patch_knowledge_legacy.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def run(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def commit(repo, message, content):
    (repo / "tracked.txt").write_text(content)
    run(repo, "add", "tracked.txt")
    run(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", message)
    return run(repo, "rev-parse", "HEAD")


def source_fixture(test, tmp_path):
    repo = tmp_path / "source.git"
    subprocess.run(["git", "init", "-q", "--bare", str(repo)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(repo), str(work)], check=True)
    run(work, "checkout", "-qb", "main")
    (work / "tracked.txt").write_text("base")
    run(work, "add", "tracked.txt")
    run(work, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    base = run(work, "rev-parse", "HEAD")
    (work / "tracked.txt").write_text("canonical import")
    run(work, "add", "tracked.txt")
    run(work, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "canonical import")
    cutoff = run(work, "rev-parse", "HEAD")
    run(work, "push", "-q", "origin", "HEAD:main")
    run(work, "checkout", "-qb", "history", base)
    (work / "plugin.json").write_text('{"version":"1.0.0"}')
    run(work, "add", "plugin.json")
    run(work, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "legacy v1.0.0")
    old = run(work, "rev-parse", "HEAD")
    (work / "tracked.txt").write_text("same")
    run(work, "add", "tracked.txt")
    run(work, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "release v1.0.0 duplicate")
    same_version = run(work, "rev-parse", "HEAD")
    run(work, "push", "-q", "origin", "HEAD:release")
    for name, value in (("EXPECTED_HEAD", same_version), ("EXPECTED_CUTOFF", cutoff),
                        ("EXPECTED_BUNDLE", "a" * 64), ("EXPECTED_COMMITS", 2),
                        ("EXPECTED_HEADS", {"main": cutoff, "release/1": same_version})):
        p = patch.object(legacy, name, value)
        p.start()
        test.addCleanup(p.stop)
    return repo, cutoff, [old, same_version]


def body(commit_id):
    return (f"# Patch {commit_id}\n\nCommit `{commit_id}` records behavior in `tracked.txt` and `plugin.json`.\n\n" +
            "\n".join(f"## {section}\n\nThis section records the actual change and its rationale with enough detail for later review.\n"
                      for section in legacy.SECTIONS)).encode()


class LegacyCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)

    def test_capture_repeat_preserves_authored_body_and_duplicate_version_hashes(self):
        repo, cutoff, commits = source_fixture(self, self.tmp_path)
        wiki = self.tmp_path / "wiki"
        (wiki / "patches").mkdir(parents=True)
        bodies = {oid: body(oid) for oid in commits}
        for oid, value in bodies.items():
            (wiki / "patches" / f"{oid}.md").write_bytes(value)
        first = legacy.capture(repo, cutoff, "release", legacy.EXPECTED_BUNDLE, wiki)
        self.assertEqual(len({c["commit"] for c in first["commits"]}), 2)
        self.assertEqual({h["name"]: h["classification"] for h in first["saved_heads"]},
                         {"main": "canonical", "release/1": "archived-only"})
        self.assertEqual(len({tuple(c["versions"][0].values()) for c in first["commits"]}), 1)
        self.assertTrue(all((wiki / "patches" / f"{oid}.md").read_bytes().endswith(value)
                            for oid, value in bodies.items()))
        legacy.capture(repo, cutoff, "release", legacy.EXPECTED_BUNDLE, wiki)
        self.assertEqual(legacy.verify(wiki, repo), 2)
        self.assertTrue(all(legacy.metadata_body((wiki / "patches" / f"{oid}.md").read_bytes())[1] == value
                            for oid, value in bodies.items()))

    def test_capture_refuses_missing_page_and_wrong_bundle(self):
        repo, cutoff, _ = source_fixture(self, self.tmp_path)
        wiki = self.tmp_path / "wiki"
        with self.assertRaisesRegex(legacy.CatalogError, "bundle digest"):
            legacy.capture(repo, cutoff, "release", "b" * 64, wiki)
        with self.assertRaisesRegex(legacy.CatalogError, "missing or unsafe authored page"):
            legacy.capture(repo, cutoff, "release", legacy.EXPECTED_BUNDLE, wiki)

    def test_verify_rejects_missing_tampered_mixed_and_source_mismatch(self):
        repo, cutoff, commits = source_fixture(self, self.tmp_path)
        wiki = self.tmp_path / "wiki"
        (wiki / "patches").mkdir(parents=True)
        for oid in commits:
            (wiki / "patches" / f"{oid}.md").write_bytes(body(oid))
        legacy.capture(repo, cutoff, "release", legacy.EXPECTED_BUNDLE, wiki)
        catalog_path = wiki / "catalog.json"
        original = catalog_path.read_bytes()
        catalog = json.loads(original)
        catalog["saved_heads"][0]["commit"] = "f" * 40
        catalog_path.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(legacy.CatalogError, "saved ref coverage"):
            legacy.verify(wiki)
        catalog_path.write_bytes(original)
        catalog = json.loads(original)
        catalog.pop("canonical_source_commit")
        catalog_path.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(legacy.CatalogError, "canonical_source_commit"):
            legacy.verify(wiki)
        catalog_path.write_bytes(original)
        page = wiki / "patches" / f"{commits[0]}.md"
        page.write_bytes(page.read_bytes() + b"changed")
        with self.assertRaisesRegex(legacy.CatalogError, "page hash mismatch"):
            legacy.verify(wiki)
        page.unlink()
        with self.assertRaisesRegex(legacy.CatalogError, "missing or unsafe page"):
            legacy.verify(wiki)
        for oid in commits:
            (wiki / "patches" / f"{oid}.md").write_bytes(body(oid))
        legacy.capture(repo, cutoff, "release", legacy.EXPECTED_BUNDLE, wiki)
        other = self.tmp_path / "other.git"
        subprocess.run(["git", "clone", "-q", "--bare", "--single-branch", "--branch", "main", str(repo), str(other)], check=True)
        with self.assertRaisesRegex(legacy.CatalogError, "archived source head mismatch"):
            legacy.verify(wiki, other)

    def test_cli_accepts_relative_project_wiki_path(self):
        result = subprocess.run([sys.executable, "tools/patch_knowledge_legacy.py", "verify",
                                 "--wiki", "docs/llm-wiki/legacy"], cwd=ROOT, text=True, capture_output=True)
        self.assertNotIn("path escapes repo", result.stderr)


if __name__ == "__main__":
    unittest.main()
