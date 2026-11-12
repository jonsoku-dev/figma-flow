import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"tools/patch_knowledge.py"

def run(repo,*args):
    return subprocess.run([sys.executable,str(SCRIPT),"--repo",str(repo),*args],capture_output=True,text=True)

def git(repo,*args): return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()

class PatchKnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.repo=Path(self.tmp.name)/"repo"; self.repo.mkdir()
        git(self.repo,"init","-q"); git(self.repo,"config","user.name","Fixture"); git(self.repo,"config","user.email","fixture@example.invalid")
        (self.repo/"panel-ui").mkdir(); (self.repo/"panel-ui/package.json").write_text('{"version":"1.0.0"}\n')
        (self.repo/".codex-plugin").mkdir(); (self.repo/".codex-plugin/plugin.json").write_text('{"version":"0.9.0"}\n')
        (self.repo/"plugin.json").write_text('{"version":"1.0.0"}\n')
        (self.repo/"CHANGELOG.md").write_text("## 1.0.0\n\nRelease notes.\n")
        (self.repo/"a.txt").write_text("root\n"); git(self.repo,"add","."); git(self.repo,"commit","-qm","root"); self.root=git(self.repo,"rev-parse","HEAD")
        git(self.repo,"tag","v1.0.0")
        git(self.repo,"checkout","-qb","side"); (self.repo/"side.txt").write_text("side\n"); git(self.repo,"add","."); git(self.repo,"commit","-qm","side change"); self.side=git(self.repo,"rev-parse","HEAD")
        # Checkout the initial branch without assuming Git's configured default name.
        branches=git(self.repo,"branch","--format=%(refname:short)").splitlines(); primary=next(x for x in branches if x!="side")
        git(self.repo,"checkout","-q",primary); (self.repo/"main.txt").write_text("main\n"); git(self.repo,"add","."); git(self.repo,"commit","-qm","main change"); self.main=git(self.repo,"rev-parse","HEAD")
        git(self.repo,"merge","--no-ff","side","-qm","merge history"); self.head=git(self.repo,"rev-parse","HEAD")
        git(self.repo,"remote","add","origin","https://user:secret@example.com/org/repo.git?token=private")
        self.wiki=self.repo/"docs/llm-wiki"

    def tearDown(self): self.tmp.cleanup()

    def test_inventory_covers_merge_graph_versions_and_sanitizes_remote(self):
        r=run(self.repo,"inventory","--ref","HEAD")
        self.assertEqual(r.returncode,0,r.stderr)
        data=json.loads(r.stdout); by={x["commit"]:x for x in data["commits"]}
        self.assertEqual(set(by),{self.root,self.side,self.main,self.head})
        self.assertEqual(by[self.head]["parents"],[self.main,self.side])
        self.assertEqual(by[self.root]["parents"],[])
        self.assertEqual(by[self.root]["versions"],[{"path":"plugin.json","version":"1.0.0"},{"path":".codex-plugin/plugin.json","version":"0.9.0"}])
        self.assertEqual(data["tags"],[{"tag":"v1.0.0","version":"1.0.0","commit":self.root}])
        self.assertNotIn("secret",json.dumps(data)); self.assertIn("example.com/org/repo.git",data["remotes"])

    def test_access_token_in_remote_is_redacted(self):
        git(self.repo,"remote","set-url","origin","https://example.com/org/repo?access_token="+"ghp_"+"x"*32)
        data=json.loads(run(self.repo,"inventory","--ref","HEAD").stdout)
        self.assertEqual(data["remotes"],["[redacted-private-or-local-remote]"])

    def test_inventory_does_not_consume_caller_standard_input(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), "inventory"],
                                input="not a Git tree\n", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["commits"]), 4)

    def test_inventory_does_not_execute_configured_external_diff(self):
        marker=self.repo/"external-diff-ran"
        helper=self.repo/".git"/"external-diff"
        helper.write_text("#!"+sys.executable+"\nfrom pathlib import Path\nPath("+repr(str(marker))+").write_text('unexpected execution')\n")
        helper.chmod(0o755)
        git(self.repo,"config","diff.external",str(helper))
        result=run(self.repo,"inventory")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(marker.exists())

    def test_sync_is_repeatable_and_preserves_human_body_but_scaffolds_fail_verify(self):
        a=run(self.repo,"sync","--wiki","docs/llm-wiki"); self.assertEqual(a.returncode,0,a.stderr)
        page=self.wiki/"patches"/(self.root+".md"); original=page.read_bytes()
        page.write_bytes(original+b"\nHuman notes stay byte-for-byte.\n")
        b=run(self.repo,"sync","--wiki","docs/llm-wiki"); self.assertEqual(b.returncode,0,b.stderr)
        self.assertTrue(page.read_bytes().endswith(b"\nHuman notes stay byte-for-byte.\n"))
        self.assertNotEqual(json.loads((self.wiki/"catalog.json").read_text())["pages"][self.root],None)
        self.assertNotEqual(run(self.repo,"verify","--wiki","docs/llm-wiki").returncode,0)

    def test_first_sync_preserves_existing_manual_page_without_metadata(self):
        page=self.wiki/"patches"/(self.root+".md")
        page.parent.mkdir(parents=True)
        page.write_bytes(b"# Existing human record\n\nKeep this exact content.\n")
        self.assertEqual(run(self.repo,"sync","--wiki","docs/llm-wiki").returncode,0)
        raw=page.read_bytes()
        self.assertTrue(raw.startswith(b"<!-- patch-knowledge\n"))
        self.assertTrue(raw.endswith(b"# Existing human record\n\nKeep this exact content.\n"))

    def test_wrong_ref_stale_catalog_and_unsafe_paths_fail(self):
        self.assertNotEqual(run(self.repo,"inventory","--ref","--all").returncode,0)
        self.assertNotEqual(run(self.repo,"sync","--wiki","../outside").returncode,0)
        self.assertEqual(run(self.repo,"sync","--wiki","docs/llm-wiki").returncode,0)
        cat=self.wiki/"catalog.json"; data=json.loads(cat.read_text()); data["source_commit"]="0"*40; cat.write_text(json.dumps(data))
        self.assertNotEqual(run(self.repo,"verify","--wiki","docs/llm-wiki").returncode,0)
        link=self.repo/"unsafe-wiki"; link.symlink_to(self.wiki,target_is_directory=True)
        self.assertNotEqual(run(self.repo,"sync","--wiki","unsafe-wiki").returncode,0)

    def test_inventory_output_rejects_symlink_target(self):
        destination=self.repo/"redirect.json"; destination.symlink_to(self.repo/"CHANGELOG.md")
        self.assertNotEqual(run(self.repo,"inventory","--output","redirect.json").returncode,0)

    def test_atomic_inventory_output_does_not_follow_planted_tmp_symlink(self):
        sentinel=self.repo/"sentinel.txt"; sentinel.write_text("preserve me")
        (self.repo/"catalog.json.tmp").symlink_to(sentinel)
        result=run(self.repo,"inventory","--output","catalog.json")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(sentinel.read_text(),"preserve me")
        self.assertTrue((self.repo/"catalog.json.tmp").is_symlink())

    def test_output_and_wiki_reject_symlink_ancestors(self):
        outside=Path(self.tmp.name)/"outside"; outside.mkdir()
        (self.repo/"redirect-dir").symlink_to(outside,target_is_directory=True)
        self.assertNotEqual(run(self.repo,"inventory","--output","redirect-dir/catalog.json").returncode,0)
        self.assertNotEqual(run(self.repo,"sync","--wiki","redirect-dir/wiki").returncode,0)

    def test_documentation_publication_is_allowed_but_code_after_cutoff_is_not(self):
        self.assertEqual(run(self.repo,"sync","--ref",self.head,"--wiki","docs/llm-wiki").returncode,0)
        catalog=json.loads((self.wiki/"catalog.json").read_text())
        for oid in catalog["pages"]:
            page=self.wiki/"patches"/(oid+".md")
            raw=page.read_text(); body=raw.split("\n-->\n",1)[1]
            sections="\n".join(f"## {s}\n\nThis record explains the observed behavior, its evidence and its limits for this historical change." for s in ("문제와 계기","결과 동작","변경 파일과 인터페이스","설계 이유와 출처","호환성·이관·복구","검증과 미검증","한계와 후속 개선","관련 기록"))
            page.write_text(raw.split("\n-->\n",1)[0]+"\n-->\n\n# Historical record\n\n"+oid+"\n\n"+"\n".join(catalog["commits"][next(i for i,c in enumerate(catalog["commits"]) if c["commit"]==oid)]["files"])+"\n\n"+sections+"\n")
        (self.wiki/"releases.md").write_text("# Releases\n\n## v1.0.0\n\nThis record describes the release and its verified source mapping to the original version tag and plugin manifest.\n")
        self.assertEqual(run(self.repo,"sync","--ref",self.head,"--wiki","docs/llm-wiki").returncode,0)
        (self.repo/"CHANGELOG.md").write_text("## 1.0.0\n\n[Patch record](docs/llm-wiki/releases.md#v1.0.0)\n")
        git(self.repo,"add","docs/llm-wiki","CHANGELOG.md"); git(self.repo,"commit","-qm","publish knowledge records")
        result=run(self.repo,"verify","--ref","HEAD","--wiki","docs/llm-wiki")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("1 documentation publication commits",result.stdout)
        legacy=self.wiki/"legacy"
        legacy.mkdir()
        (legacy/"catalog.json").write_text("{}")
        invalid_legacy=run(self.repo,"verify","--ref","HEAD")
        self.assertNotEqual(invalid_legacy.returncode,0)
        self.assertNotIn("Traceback",invalid_legacy.stderr)
        (legacy/"catalog.json").unlink()
        legacy.rmdir()
        page=self.wiki/"patches"/(self.root+".md")
        authored=page.read_text()
        page.unlink()
        missing=run(self.repo,"verify","--ref","HEAD")
        self.assertNotEqual(missing.returncode,0)
        self.assertIn("missing or unsafe page",missing.stderr)
        page.write_text(authored.replace(self.root,"f"*40))
        self.assertEqual(run(self.repo,"sync","--ref",self.head).returncode,0)
        forged=run(self.repo,"verify","--ref","HEAD")
        self.assertNotEqual(forged.returncode,0)
        self.assertIn("source commit missing",forged.stderr)
        page.write_text(authored)
        self.assertEqual(run(self.repo,"sync","--ref",self.head).returncode,0)
        changelog=self.repo/"CHANGELOG.md"
        original_changelog=changelog.read_text()
        changelog.write_text(original_changelog+"\n## 2.0.0\n\nUnrecorded new release.\n")
        self.assertNotEqual(run(self.repo,"verify","--ref","HEAD").returncode,0)
        changelog.write_text(original_changelog)
        (self.repo/"uncommitted-source.txt").write_text("local change\n")
        self.assertNotEqual(run(self.repo,"verify","--ref","HEAD","--wiki","docs/llm-wiki").returncode,0)
        committed=run(self.repo,"verify","--ref","HEAD","--wiki","docs/llm-wiki","--committed-only")
        self.assertEqual(committed.returncode,0,committed.stderr)
        (self.repo/"uncommitted-source.txt").unlink()
        (self.repo/"a.txt").write_text("product change after cutoff\n"); git(self.repo,"add","a.txt"); git(self.repo,"commit","-qm","new product change")
        self.assertNotEqual(run(self.repo,"verify","--ref","HEAD","--wiki","docs/llm-wiki").returncode,0)

    def test_sync_preserves_remote_observations_after_fork(self):
        self.assertEqual(run(self.repo,"sync","--ref",self.head,"--wiki","docs/llm-wiki").returncode,0)
        git(self.repo,"remote","set-url","origin","git@github.com:forked/figma-flow.git")
        self.assertEqual(run(self.repo,"sync","--ref",self.head,"--wiki","docs/llm-wiki").returncode,0)
        seen=json.loads((self.wiki/"catalog.json").read_text())["provenance_remotes"]
        values={x["remote"] for x in seen}
        self.assertIn("example.com/org/repo.git",values)
        self.assertIn("github.com/forked/figma-flow.git",values)

    def test_same_version_tags_keep_distinct_commit_identities(self):
        git(self.repo,"tag","release-1.0.0",self.side)
        data=json.loads(run(self.repo,"inventory","--ref","HEAD").stdout)
        matching=[x for x in data["tags"] if x["version"]=="1.0.0"]
        self.assertEqual({x["commit"] for x in matching},{self.root,self.side})

if __name__=="__main__": unittest.main()
