#!/usr/bin/env python3
"""Reproduce and verify an improvement against its parent commit.

Baseline assertions use the final AssertionError in Python's last stderr
traceback, or a direct Node AssertionError [ERR_ASSERTION] stderr message.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

SCHEMA = "figma-flow-improvement-v1"
HASH = re.compile(r"^[0-9a-f]{40}$")
FIELDS = {"schema", "base", "target", "problem", "result", "rationale", "compatibility", "limits", "follow_up", "related", "scope", "criteria", "reproduction", "checks"}
TEXT_FIELDS = ("problem", "result", "rationale", "compatibility", "limits", "follow_up")
BAD = re.compile(r"\b(?:TODO|TBD|PLACEHOLDER|SCAFFOLD|INCOMPLETE|N/?A)\b|미작성|작성 예정", re.I)
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_OUTPUT = 2 * 1024 * 1024


class GateError(Exception):
    pass


def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", str(repo), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise GateError(p.stderr.decode("utf-8", "replace").strip() or "git command failed")
    return p.stdout


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise GateError("invalid repository path")
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ("", ".", "..") for x in value.split("/")):
        raise GateError(f"unsafe repository path: {value}")
    return value


def meaningful(value, label):
    if not isinstance(value, str) or len(value.strip()) < 12 or BAD.search(value):
        raise GateError(f"{label} must contain meaningful text")


def archive(repo, commit, destination):
    tree = git(repo, "ls-tree", "-r", "-z", commit)
    if any(record.startswith(b"160000 ") for record in tree.split(b"\0") if record):
        raise GateError("gitlinks are not supported in archived baselines")
    destination.mkdir()
    raw = destination / "archive.tar"
    with raw.open("wb") as output:
        p = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit], stdout=output, stderr=subprocess.PIPE)
    if p.returncode:
        raise GateError(p.stderr.decode("utf-8", "replace").strip() or "git archive failed")
    if raw.stat().st_size > MAX_ARCHIVE:
        raise GateError("archive exceeds 256 MiB limit")
    root = destination / "tree"
    root.mkdir()
    count = 0
    total = 0
    with tarfile.open(raw, "r:") as tar:
        for member in tar:
            name = safe_path(member.name.rstrip("/"))
            count += 1
            total += max(0, member.size)
            if count > 100000 or total > MAX_ARCHIVE:
                raise GateError("archive exceeds extraction limits")
            if not (member.isdir() or member.isfile()) or member.issym() or member.islnk():
                raise GateError(f"unsupported archive entry: {name}")
            out = root.joinpath(*PurePosixPath(name).parts)
            if not out.resolve().is_relative_to(root.resolve()):
                raise GateError(f"archive path escapes tree: {name}")
            if member.isdir():
                out.mkdir(parents=True, exist_ok=True)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(member)
                if data is None:
                    raise GateError(f"missing archive data: {name}")
                with out.open("xb") as f:
                    shutil.copyfileobj(data, f)
                out.chmod(0o755 if member.mode & 0o111 else 0o644)
    return root


def tracked(repo, commit, rel):
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}:{rel}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def regular_blob(repo, commit, rel):
    records = git(repo, "ls-tree", "-z", commit, "--", rel).split(b"\0")
    if len(records) != 2 or not records[0]:
        return None
    metadata, path = records[0].split(b"\t", 1)
    mode, kind, oid = metadata.split()
    if path.decode("utf-8", "surrogateescape") != rel or kind != b"blob" or mode not in (b"100644", b"100755"):
        return None
    return mode, oid


def command_paths(argv, repo, commits):
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x and "\x00" not in x for x in argv):
        raise GateError("commands must be nonempty argv arrays")
    if any(x.startswith(("/", "~")) for x in argv):
        raise GateError("commands must not contain absolute or home-relative paths")
    paths = []
    if argv[0] in ("python", "python3", "node"):
        if len(argv) >= 2 and (argv[1] == "-B" and len(argv) >= 4 and argv[2] == "-m" and argv[3] == "unittest"):
            modules = argv[4:]
            if not modules:
                raise GateError("unittest command must name tracked test modules")
            for module in modules:
                if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*", module):
                    raise GateError("invalid unittest module name")
                rel = module.replace(".", "/") + ".py"
                paths.append(rel)
        elif argv[0] == "node" and len(argv) >= 3 and argv[1] == "--test":
            paths.extend(argv[2:])
        elif len(argv) >= 2:
            paths.append(argv[1])
        else:
            raise GateError("command must name a tracked script")
    else:
        raise GateError("command executable must be python, python3, or node")
    for rel in paths:
        safe_path(rel)
        versions = [regular_blob(repo, commit, rel) for commit in commits]
        if any(version is None for version in versions):
            raise GateError(f"command file must be a regular tracked file at both commits: {rel}")
        if versions[0] != versions[1]:
            raise GateError(f"command file changed between base and target: {rel}")
    return paths


def validate(repo, proposal):
    if not isinstance(proposal, dict) or set(proposal) != FIELDS:
        raise GateError("proposal has missing or unknown fields")
    if proposal["schema"] != SCHEMA:
        raise GateError("unsupported proposal schema")
    for key in ("base", "target"):
        value = proposal[key]
        if not isinstance(value, str) or not HASH.fullmatch(value):
            raise GateError(f"{key} must be a full commit hash")
        actual = git(repo, "rev-parse", "--verify", f"{value}^{{commit}}").decode().strip()
        if actual != value:
            raise GateError(f"{key} is not a canonical commit hash")
    if proposal["target"] != git(repo, "rev-parse", "HEAD").decode().strip():
        raise GateError("target must equal current HEAD")
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", proposal["base"], proposal["target"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0 or proposal["base"] == proposal["target"]:
        raise GateError("base must be a strict ancestor of target")
    for key in TEXT_FIELDS:
        meaningful(proposal[key], key)
    related = proposal["related"]
    if not isinstance(related, list) or not related or any(not isinstance(x, str) for x in related) or len(set(related)) != len(related):
        raise GateError("related must be a nonempty unique path list")
    for rel in related:
        safe_path(rel)
        if not rel.startswith("docs/llm-wiki/"):
            raise GateError("related paths must be inside docs/llm-wiki")
        path = repo.joinpath(*PurePosixPath(rel).parts)
        cur = repo
        for part in PurePosixPath(rel).parts:
            cur = cur / part
            if cur.is_symlink():
                raise GateError(f"symlink related path rejected: {rel}")
        if not path.is_file():
            raise GateError(f"related path does not exist: {rel}")
    scope = proposal["scope"]
    if not isinstance(scope, list) or not scope or any(not isinstance(x, str) for x in scope) or scope != sorted(set(scope)):
        raise GateError("scope must be sorted, unique changed paths")
    for rel in scope:
        safe_path(rel)
    changed = sorted(x for x in git(repo, "diff", "--name-only", "-z", proposal["base"], proposal["target"]).decode("utf-8", "surrogateescape").split("\0") if x)
    if changed != scope:
        raise GateError("scope must exactly match all changed paths between base and target")
    criteria = proposal["criteria"]
    if not isinstance(criteria, list) or not criteria or any(not isinstance(x, str) or not x.strip() for x in criteria) or len(criteria) != len(set(criteria)):
        raise GateError("criteria must be nonempty with unique IDs")
    repro = proposal["reproduction"]
    if not isinstance(repro, dict) or set(repro) != {"criterion", "argv", "failure_contains"}:
        raise GateError("invalid reproduction object")
    if repro["criterion"] not in criteria:
        raise GateError("reproduction criterion is not declared")
    if not isinstance(repro["failure_contains"], str) or not repro["failure_contains"].strip() or BAD.search(repro["failure_contains"]):
        raise GateError("failure_contains must be a nonempty assertion fragment")
    repopaths = command_paths(repro["argv"], repo, [proposal["base"], proposal["target"]])
    checks = proposal["checks"]
    if not isinstance(checks, list) or len(checks) != len(criteria):
        raise GateError("each criterion must have exactly one check")
    ids = []
    checkpaths = []
    repro_count = 0
    for item in checks:
        if not isinstance(item, dict) or set(item) != {"criterion", "argv"} or not isinstance(item["criterion"], str):
            raise GateError("invalid check object")
        ids.append(item["criterion"])
        checkpaths.extend(command_paths(item["argv"], repo, [proposal["base"], proposal["target"]]))
        if item["argv"] == repro["argv"]:
            repro_count += 1
    if sorted(ids) != sorted(criteria) or len(set(ids)) != len(ids) or repro_count != 1:
        raise GateError("checks must cover each criterion once and include reproduction argv once")
    return set(repopaths + checkpaths)


def snapshot(repo, target, paths):
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    if head != target:
        raise GateError("checkout HEAD changed")
    ignored = lambda rel: rel == "CHANGELOG.md" or rel.startswith("docs/llm-wiki/")
    tracked_paths = [x.decode("utf-8", "surrogateescape") for x in git(repo, "ls-files", "-z").split(b"\0") if x]
    untracked = [x.decode("utf-8", "surrogateescape") for x in git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if x]
    for rel in untracked:
        if not ignored(rel):
            raise GateError(f"untracked product source: {rel}")
    result = {}
    for rel in sorted(set(tracked_paths) | set(paths)):
        if ignored(rel):
            continue
        for flag in ([], ["--cached"]):
            if subprocess.run(["git", "-C", str(repo), "diff", *flag, "--quiet", target, "--", rel], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
                raise GateError(f"tracked source is modified: {rel}")
        path = repo.joinpath(*PurePosixPath(rel).parts)
        cur = repo
        for part in PurePosixPath(rel).parts:
            cur = cur / part
            if cur.is_symlink():
                raise GateError(f"symlink source path rejected: {rel}")
        expected_exists = tracked(repo, target, rel)
        if not expected_exists:
            if path.exists():
                raise GateError(f"source differs from target commit: {rel}")
            result[rel] = None
            continue
        if not path.is_file():
            raise GateError(f"missing or unsafe checkout source: {rel}")
        data = path.read_bytes()
        expected = git(repo, "show", f"{target}:{rel}")
        if data != expected:
            raise GateError(f"source differs from target commit: {rel}")
        result[rel] = hashlib.sha256(data).hexdigest()
    return head, result


def run(argv, cwd, timeout):
    executable = shutil.which(argv[0])
    if not executable:
        raise GateError(f"executable not found on PATH: {argv[0]}")
    args = [executable, *argv[1:]]
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            p = subprocess.Popen(args, cwd=cwd, stdout=out, stderr=err, start_new_session=True,
                                 env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
        except OSError as e:
            raise GateError(f"could not start command: {e}")
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            raise GateError(f"command timed out after {timeout}s")
        try:
            os.killpg(p.pid, 0)
        except ProcessLookupError:
            pass
        else:
            os.killpg(p.pid, signal.SIGKILL)
            raise GateError("command left child processes running")
        digest = hashlib.sha256()
        diagnostic = bytearray()
        for name, stream in ((b"stdout\0", out), (b"stderr\0", err)):
            digest.update(name)
            stream.seek(0)
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
                if len(diagnostic) < MAX_OUTPUT:
                    diagnostic.extend(chunk[:MAX_OUTPUT - len(diagnostic)])
        err.seek(0)
        return {"argv": argv, "returncode": code, "output_sha256": digest.hexdigest(),
                "diagnostic": diagnostic.decode("utf-8", "replace"),
                "stderr": err.read(MAX_OUTPUT).decode("utf-8", "replace")}


def expected_assertion(result, fragment):
    stderr = result["stderr"]
    if "Traceback (most recent call last):" in stderr:
        traceback = stderr.rsplit("Traceback (most recent call last):", 1)[1]
        failures = re.findall(r"^AssertionError(?::[^\n]*)?$", traceback, re.M)
    else:
        failures = re.findall(r"^AssertionError \[ERR_ASSERTION\](?::[^\n]*)?$", stderr, re.M)
    return bool(failures and fragment in failures[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, help="write local result JSON; never used as gate input")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--execute", action="store_true", help="run proposal commands; commands are untrusted code")
    parser.add_argument("gate", choices=["gate"])
    parser.add_argument("proposal", type=Path)
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required to run untrusted proposal commands")
    if not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    repo = args.repo.resolve()
    repo_input = args.repo.absolute()
    proposal_path = args.proposal if args.proposal.is_absolute() else repo_input / args.proposal
    if proposal_path.is_symlink():
        raise GateError("proposal path symlinks are not allowed")
    if proposal_path.is_relative_to(repo_input):
        cur = repo_input
        for part in proposal_path.relative_to(repo_input).parts[:-1]:
            cur /= part
            if cur.is_symlink():
                raise GateError("proposal path symlinks are not allowed")
    resolved_proposal = proposal_path.resolve()
    proposal = json.loads(resolved_proposal.read_text(encoding="utf-8"))
    paths = validate(repo, proposal)
    head_before, files_before = snapshot(repo, proposal["target"], set(proposal["scope"]) | paths)
    with tempfile.TemporaryDirectory(prefix="figma-flow-improvement-") as temp:
        root = Path(temp)
        base_tree = archive(repo, proposal["base"], root / "base")
        target_tree = archive(repo, proposal["target"], root / "target")
        for rel in paths:
            if any(not tree.joinpath(*PurePosixPath(rel).parts).is_file() for tree in (base_tree, target_tree)):
                raise GateError(f"command file missing from commit archive: {rel}")
        repro = proposal["reproduction"]
        baseline = run(repro["argv"], base_tree, args.timeout)
        assertion_failure = expected_assertion(baseline, repro["failure_contains"])
        if baseline["returncode"] == 0 or not assertion_failure:
            raise GateError("baseline reproducer did not fail with the expected assertion")
        records = []
        for item in proposal["checks"]:
            result = run(item["argv"], target_tree, args.timeout)
            result["criterion"] = item["criterion"]
            records.append(result)
            if result["returncode"] != 0:
                raise GateError(f"target check failed: {item['criterion']}")
        head_after, files_after = snapshot(repo, proposal["target"], set(proposal["scope"]) | paths)
        if head_before != head_after or files_before != files_after:
            raise GateError("source checkout changed during verification")
    result = {"schema": "figma-flow-improvement-result-v1", "status": "passed", "base": proposal["base"], "target": proposal["target"], "scope": proposal["scope"], "baseline": baseline, "checks": records, "created_at": int(time.time())}
    if args.output:
        output = args.output if args.output.is_absolute() else repo / args.output
        local_results = repo / ".figma-flow"
        if not output.is_absolute():
            output = repo / output
        if not output.is_relative_to(repo) or not output.is_relative_to(local_results) or output.is_symlink():
            raise GateError("--output must be a non-symlink path under .figma-flow")
        safe_path(output.relative_to(repo).as_posix())
        cur = repo
        for part in output.relative_to(repo).parts[:-1]:
            cur = cur / part
            if cur.is_symlink():
                raise GateError("--output path has a symlink ancestor")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
            temp_output = Path(f.name)
        os.replace(temp_output, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GateError, OSError, ValueError, json.JSONDecodeError, tarfile.TarError) as e:
        print(f"gate failed: {e}", file=sys.stderr)
        raise SystemExit(1)
