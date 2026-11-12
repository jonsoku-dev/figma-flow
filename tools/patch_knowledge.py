#!/usr/bin/env python3
"""Build and verify a portable, commit-addressed patch knowledge catalog."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

SCHEMA = "figma-flow-patch-catalog-v1"
SECTIONS = ("문제와 계기", "결과 동작", "변경 파일과 인터페이스", "설계 이유와 출처",
            "호환성·이관·복구", "검증과 미검증", "한계와 후속 개선", "관련 기록")
VERSION = re.compile(r"(?<![\w])v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")
HEADING = re.compile(r"^#{1,3}\s+.*?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)", re.M)
BAD = re.compile(r"\b(?:TODO|TBD|PLACEHOLDER|SCAFFOLD|INCOMPLETE)\b|미작성|작성 예정|여기에 작성", re.I)

class CatalogError(Exception):
    pass

def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", str(repo), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise CatalogError(p.stderr.decode("utf-8", "replace").strip() or "git command failed")
    return p.stdout

def safe_ref(ref):
    if not ref or ref.startswith("-") or ref.startswith("/") or ".." in ref or "\\" in ref or re.search(r"[\x00-\x20~^:?*\[]", ref):
        raise CatalogError("unsafe ref")

def sha(data): return hashlib.sha256(data).hexdigest()

def sanitize_remote(raw):
    s=raw.strip()
    if not s: return None
    if re.search(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|(?:access[_-]?token|api[_-]?key|password|passwd|secret)=)",s,re.I):
        return "[redacted-private-or-local-remote]"
    # URL forms retain only public host/path; SCP form accepts public host/path.
    u=urlsplit(s)
    if u.scheme.lower() in ("http","https","git","ssh") and u.hostname:
        host,path=u.hostname.lower(),u.path.strip("/")
    else:
        m=re.fullmatch(r"(?:[^@/:]+@)?([A-Za-z0-9.-]+):([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+?)(?:\.git)?", s.split("?",1)[0])
        if not m: return "[redacted-private-or-local-remote]"
        host,path=m.group(1).lower(),m.group(2).strip("/")
    path=re.sub(r"\.git$","",path)
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith((".local", ".internal")) or path.startswith(("Users/", "home/", "private/")):
        return "[redacted-private-or-local-remote]"
    return f"{host}/{path}.git"

def manifest_files(repo, ref):
    candidates=["plugin.json", ".codex-plugin/plugin.json"]
    found=[]
    for f in candidates:
        raw=git(repo,"show",f"{ref}:{f}",check=False)
        if raw:
            try:
                obj=json.loads(raw)
                if isinstance(obj,dict) and isinstance(obj.get("version"),str): found.append({"path":f,"version":obj["version"]})
            except (ValueError,UnicodeDecodeError): pass
    return found

def inventory(repo, ref):
    safe_ref(ref)
    resolved=git(repo,"rev-parse","--verify",f"{ref}^{{commit}}").decode().strip()
    commits=[]
    ids=git(repo,"rev-list","--reverse","--topo-order",resolved).decode().splitlines()
    for oid in ids:
        parents=git(repo,"show","-s","--format=%P",oid).decode().split()
        tree=git(repo,"show","-s","--format=%T",oid).decode().strip()
        subject=git(repo,"show","-s","--format=%s",oid).decode("utf-8","replace").strip()
        base=parents[0] if parents else git(repo,"hash-object","-t","tree","--stdin").decode().strip()
        diff=git(repo,"diff", "--binary", "--no-ext-diff", "--no-textconv", "--no-color", base, oid)
        names=git(repo,"diff-tree","--no-commit-id","--name-only","-r","-z",*(parents[:1] or ["--root"]),oid).decode("utf-8","surrogateescape").split("\0")
        commits.append({"commit":oid,"parents":parents,"tree":tree,"subject":subject,"files":sorted(x for x in names if x),"diff_sha256":sha(diff),"versions":manifest_files(repo,oid)})
    tags=[]
    for row in git(repo,"tag","--merged",resolved,"--format=%(refname:short)%00%(objectname)").decode().splitlines():
        if not row: continue
        tag,obj=row.split("\0",1)
        target=git(repo,"rev-parse",f"{tag}^{{commit}}").decode().strip()
        vers=VERSION.search(tag)
        if vers: tags.append({"tag":tag,"version":vers.group(1),"commit":target})
    changelog=git(repo,"show",f"{resolved}:CHANGELOG.md",check=False).decode("utf-8","replace")
    changelog_versions=list(dict.fromkeys(HEADING.findall(changelog)))
    remotes=[]
    for line in git(repo,"remote","-v",check=False).decode("utf-8","replace").splitlines():
        bits=line.split()
        if len(bits)>1:
            value=sanitize_remote(bits[1])
            if value and value not in remotes: remotes.append(value)
    return {"schema":SCHEMA,"source_commit":resolved,"remotes":sorted(remotes),"commits":commits,"tags":sorted(tags,key=lambda x:(x["version"],x["tag"],x["commit"])),"changelog_versions":changelog_versions}

def page_metadata(commit):
    return {k:commit[k] for k in ("commit","parents","tree","subject","files","diff_sha256","versions")}

def prefix(meta): return "<!-- patch-knowledge\n"+json.dumps(meta,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n-->\n"

def page_path(wiki, oid): return wiki/"patches"/(oid+".md")

def release_inventory(inv):
    versions=sorted(set(inv["changelog_versions"])|{t["version"] for t in inv["tags"]},key=lambda x:tuple(int(y) if y.isdigit() else y for y in re.split(r"[.+-]",x)))
    releases=[]
    for v in versions:
        matches=[t for t in inv["tags"] if t["version"]==v]
        commits=list(dict.fromkeys(t["commit"] for t in matches))
        if not commits:
            candidates=[c["commit"] for c in inv["commits"] if any(x["version"]==v for x in c["versions"])]
            commits=candidates[-1:]
        releases.append({"version":v,"tags":[t["tag"] for t in matches],"tagged":bool(matches),"source_commits":commits})
    return releases

def atomic(path,data):
    if path.is_file() and not path.is_symlink() and path.read_bytes()==data:
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream: stream.write(data)
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def assert_safe_dir(root, path, create=False):
    root=root.resolve()
    # Reject symlink components, including an existing final component.
    cur=root
    try: rel=path.relative_to(root)
    except ValueError: raise CatalogError("path escapes repo")
    for part in rel.parts:
        cur=cur/part
        if cur.is_symlink(): raise CatalogError(f"symlink path rejected: {cur}")
    if create: path.mkdir(parents=True,exist_ok=True)
    if path.exists() and not path.is_dir(): raise CatalogError("wiki path is not a directory")

def sync(repo, ref, wiki):
    inv=inventory(repo,ref); assert_safe_dir(repo,wiki,True)
    old_catalog=wiki/"catalog.json"
    provenance=[]
    if old_catalog.is_file() and not old_catalog.is_symlink():
        try: provenance.extend(json.loads(old_catalog.read_text()).get("provenance_remotes",[]))
        except (ValueError,OSError): pass
    for remote in inv["remotes"]:
        item={"observed_at_commit":inv["source_commit"],"remote":remote}
        if item not in provenance: provenance.append(item)
    for c in inv["commits"]:
        path=page_path(wiki,c["commit"])
        assert_safe_dir(repo,path.parent,True)
        if path.is_symlink(): raise CatalogError(f"symlink page rejected: {path}")
        old=path.read_bytes() if path.exists() else b""
        if old.startswith(b"<!-- patch-knowledge\n"):
            end=old.find(b"\n-->\n")
            if end<0: raise CatalogError(f"malformed metadata prefix: {path}")
            body=old[end+5:]
        elif old:
            body=old
        else:
            body=("\n# " + c["subject"] + "\n\n" + "\n".join("## "+s+"\n\n[미작성: 사람의 기록 필요]" for s in SECTIONS)+"\n").encode()
        atomic(path,prefix(page_metadata(c)).encode()+body)
    releases=release_inventory(inv)
    inv["releases"]=releases
    inv["provenance_remotes"]=sorted(provenance,key=lambda x:(x.get("observed_at_commit",""),x.get("remote","")))
    inv["pages"]={c["commit"]:sha(page_path(wiki,c["commit"]).read_bytes()) for c in inv["commits"]}
    catalog=wiki/"catalog.json"
    if catalog.is_symlink(): raise CatalogError("symlink catalog rejected")
    atomic(catalog,(json.dumps(inv,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode())
    relpath=wiki/"releases.md"
    if relpath.is_symlink(): raise CatalogError("symlink release index rejected")
    if not relpath.exists():
        atomic(relpath,("# Releases\n\n"+"\n".join(f"- [v{r['version']}](#v{r['version']})\n\n## v{r['version']}\n\n[미상: 이 버전의 기록 필요]" for r in releases)+"\n").encode())
    return inv

def metadata_body(data):
    marker=b"\n-->\n"
    if not data.startswith(b"<!-- patch-knowledge\n") or marker not in data: raise CatalogError("missing or malformed metadata prefix")
    end=data.index(marker)
    try: meta=json.loads(data[len(b"<!-- patch-knowledge\n"):end])
    except ValueError: raise CatalogError("invalid page metadata JSON")
    return meta,data[end+len(marker):]

def substantive_page(path, text, required_sections):
    errors=[]
    if BAD.search(text): errors.append(f"placeholder text: {path}")
    if not re.search(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])",text): errors.append(f"full commit missing: {path}")
    if required_sections:
        for section in SECTIONS:
            m=re.search(r"^##\s+"+re.escape(section)+r"\s*$([\s\S]*?)(?=^##\s|\Z)",text,re.M)
            if not m or len(re.sub(r"[\s#*_`>-]", "", m.group(1)))<16:
                errors.append(f"empty or missing section {section}: {path}")
        if len(re.sub(r"[\s#*_`>-]", "", text))<180: errors.append(f"page lacks explanation: {path}")
    return errors

def links(text): return re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)",text)

def check_links(base, sources, wiki, repo):
    errors=[]
    for file,text in sources:
        for target in links(text):
            if target.startswith(("http://","https://","mailto:","//")): continue
            raw,_,frag=target.partition("#")
            if not raw:
                dest=file
            else:
                dest=(file.parent/raw).resolve()
            try: dest.relative_to(repo.resolve())
            except ValueError: errors.append(f"link escapes repo in {file}: {target}"); continue
            if not dest.is_file(): errors.append(f"broken link in {file}: {target}"); continue
            if frag:
                content=dest.read_text(encoding="utf-8",errors="replace")
                anchors={x.lower().replace(" ","-") for x in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$",content,re.M)}
                explicit=set(re.findall(r"<a[^>]+id=[\"']([^\"']+)",content,re.I))
                if frag not in anchors and frag not in explicit: errors.append(f"missing link anchor in {file}: {target}")
    return errors

def verify(repo, ref, wiki, changelog, committed_only=False):
    safe_ref(ref)
    tip=git(repo,"rev-parse","--verify",f"{ref}^{{commit}}").decode().strip()
    if not committed_only:
        dirty=[line[3:] for line in git(repo,"status","--porcelain","--untracked-files=all").decode("utf-8","surrogateescape").splitlines() if line[3:] and line[3:]!="CHANGELOG.md" and not line[3:].startswith("docs/llm-wiki/")]
        if dirty: raise CatalogError("uncommitted source changes outside patch records; commit them or use --committed-only")
    assert_safe_dir(repo,wiki)
    catpath=wiki/"catalog.json"
    if catpath.is_symlink() or not catpath.is_file(): raise CatalogError("missing or unsafe catalog")
    cat=json.loads(catpath.read_text(encoding="utf-8"))
    base=cat.get("source_commit")
    if not isinstance(base,str) or not re.fullmatch(r"[0-9a-f]{40}",base): raise CatalogError("invalid catalog source commit")
    if git(repo,"merge-base",base,tip,check=False).decode().strip()!=base: raise CatalogError("catalog source is not an ancestor of requested ref")
    actual=inventory(repo,base)
    actual["releases"]=release_inventory(actual)
    publication=[]
    if base!=tip:
        ids=git(repo,"rev-list","--reverse","--topo-order",f"{base}..{tip}").decode().splitlines()
        for oid in ids:
            ps=git(repo,"show","-s","--format=%P",oid).decode().split()
            parent=ps[0] if ps else git(repo,"hash-object","-t","tree","--stdin").decode().strip()
            changed=git(repo,"diff","--name-only","-z",parent,oid).decode("utf-8","surrogateescape").split("\0")
            files=[x for x in changed if x]
            if not files or any(not (x=="CHANGELOG.md" or x.startswith("docs/llm-wiki/")) for x in files):
                raise CatalogError(f"unrecorded non-document commit after catalog source: {oid}")
            publication.append(oid)
    for field in ("schema","source_commit","commits","tags","changelog_versions","releases"):
        if cat.get(field)!=actual.get(field): raise CatalogError(f"catalog inventory mismatch: {field}")
    observed={x.get("remote") for x in cat.get("provenance_remotes",[]) if isinstance(x,dict)}
    if not set(actual["remotes"]).issubset(observed) or not set(cat.get("remotes",[])).issubset(observed):
        raise CatalogError("remote provenance missing current or recorded observation; run sync")
    expected={c["commit"]:c for c in actual["commits"]}
    if set(cat.get("pages",{}))!=set(expected): raise CatalogError("catalog page coverage mismatch")
    errors=[]
    pages=[]
    for oid,c in expected.items():
        p=page_path(wiki,oid)
        if p.is_symlink() or not p.is_file(): errors.append(f"missing or unsafe page: {p}"); continue
        raw=p.read_bytes()
        if cat["pages"].get(oid)!=sha(raw): errors.append(f"page hash mismatch: {p}")
        try: meta,body=metadata_body(raw)
        except CatalogError as e: errors.append(f"{p}: {e}"); continue
        if meta!=page_metadata(c): errors.append(f"page metadata mismatch: {p}")
        text=body.decode("utf-8","replace")
        errors.extend(substantive_page(p,text,True))
        if oid not in text: errors.append(f"source commit missing from human record: {p}")
        if c["files"] and not any(changed in text for changed in c["files"]): errors.append(f"no changed path referenced: {p}")
        pages.append((p,text))
    # Every release gets a human record, including an honest unknown mapping when no manifest exists.
    rel=wiki/"releases.md"
    rtext=""
    if rel.is_symlink() or not rel.is_file(): errors.append("missing or unsafe releases.md")
    else:
        rtext=rel.read_text(encoding="utf-8",errors="replace")
        if BAD.search(rtext): errors.append("release index contains scaffold placeholders")
        for release in actual["releases"]:
            if f"## v{release['version']}" not in rtext: errors.append(f"release record missing: {release['version']}")
            section=re.search(r"^##\s+v"+re.escape(release["version"])+r"\s*$([\s\S]*?)(?=^##\s|\Z)",rtext,re.M)
            if not section or len(re.sub(r"[\s#*_`>-]", "", section.group(1)))<35:
                errors.append(f"release explanation missing: {release['version']}")
            if not release["source_commits"] and section and not re.search(r"미상|unknown|unavailable|없음",section.group(1),re.I):
                errors.append(f"unknown release mapping must be explicit: {release['version']}")
        pages.append((rel,rtext))
    changelog_path=Path(os.path.abspath(repo/changelog))
    try: changelog_path.relative_to(repo.resolve())
    except ValueError: raise CatalogError("changelog path escapes repo")
    if changelog_path.is_symlink(): raise CatalogError("symlink changelog rejected")
    try: changelog_text=changelog_path.read_text(encoding="utf-8")
    except OSError: errors.append(f"missing changelog: {changelog}"); changelog_text=""
    for version in dict.fromkeys(actual["changelog_versions"]+HEADING.findall(changelog_text)):
        match=re.search(r"^#{1,3}\s+.*?"+re.escape(version)+r"[^\n]*\n([\s\S]*?)(?=^#{1,3}\s|\Z)",changelog_text,re.M)
        if not match or not re.search(r"\]\([^)]*(?:releases\.md|patches/)[^)]*#v?"+re.escape(version)+r"[^)]*\)",match.group(1)):
            errors.append(f"changelog version lacks wiki link: {version}")
        if rel.is_file() and not re.search(r"^##\s+v"+re.escape(version)+r"\s*$",rtext,re.M):
            errors.append(f"changelog version lacks release record: {version}")
    link_sources=[]
    for directory,dirs,files in os.walk(wiki,followlinks=False):
        basepath=Path(directory)
        for name in dirs+files:
            if (basepath/name).is_symlink(): errors.append(f"symlink in wiki: {basepath/name}")
        for name in files:
            candidate=basepath/name
            if candidate.suffix.lower() in (".md",".markdown"):
                try: link_sources.append((candidate,candidate.read_text(encoding="utf-8",errors="replace")))
                except OSError: errors.append(f"unreadable wiki file: {candidate}")
    errors.extend(check_links(repo,link_sources+[(changelog_path,changelog_text)],wiki,repo))
    if errors: raise CatalogError("verification failed:\n- "+"\n- ".join(errors))
    legacy=wiki/"legacy"
    if legacy.exists():
        from patch_knowledge_legacy import verify as verify_legacy, CatalogError as LegacyCatalogError
        try: actual["archived_pages_structural"]=verify_legacy(legacy,repo_root=repo)
        except LegacyCatalogError as error: raise CatalogError(str(error)) from None
    actual["publication_commits"]=publication
    return actual

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",default=".")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("inventory"); a.add_argument("--ref",default="HEAD"); a.add_argument("--output")
    a=sub.add_parser("sync"); a.add_argument("--ref",default="HEAD"); a.add_argument("--wiki",default="docs/llm-wiki")
    a=sub.add_parser("verify"); a.add_argument("--ref",default="HEAD"); a.add_argument("--wiki",default="docs/llm-wiki"); a.add_argument("--changelog",default="CHANGELOG.md"); a.add_argument("--committed-only",action="store_true",help="verify the committed ref while ignoring uncommitted source changes")
    args=p.parse_args(argv); repo=Path(args.repo).resolve()
    try:
        if args.command=="inventory":
            result=inventory(repo,args.ref); out=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
            if args.output:
                target=Path(os.path.abspath(repo/args.output))
                if target==repo or repo not in target.parents: raise CatalogError("output path escapes repo")
                if target.is_symlink(): raise CatalogError("symlink output rejected")
                assert_safe_dir(repo,target.parent)
                atomic(target,out.encode())
            else: sys.stdout.write(out)
        elif args.command=="sync":
            wiki=Path(os.path.abspath(repo/args.wiki))
            result=sync(repo,args.ref,wiki); print(f"synced {len(result['commits'])} commits; schema={SCHEMA}")
        else:
            result=verify(repo,args.ref,Path(os.path.abspath(repo/args.wiki)),args.changelog,args.committed_only)
            print(f"verified {len(result['commits'])} commits; {len(result['publication_commits'])} documentation publication commits; schema={SCHEMA}")
            if "archived_pages_structural" in result:
                print(f"archived pages: {result['archived_pages_structural']}; structural-only, use legacy verify --source-git for original Git proof")
    except (CatalogError, OSError, ValueError) as e:
        print(f"patch_knowledge: {e}",file=sys.stderr); return 2
    return 0

if __name__=="__main__": raise SystemExit(main())
