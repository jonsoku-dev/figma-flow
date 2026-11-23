#!/usr/bin/env python3
"""Audit the exact Git distribution before its major version is released."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from graph_document import decode_json, read_json
from release_ownership import REGISTRY, ReleaseOwnership, json_member, pointer_parts, relative

import panel_authority
import plugin_manifest
import report_appearance
import native_appearance
import runtime_authority
import spec_graph_coverage

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?')
LOCAL_HOME = re.compile(rb'(?:/(?:Users|home)/[\w.-]+/(?:Documents|Desktop|\.codex)/|[A-Za-z]:[\\/]+Users[\\/]+[\w.-]+[\\/]+(?:Documents|Desktop)[\\/])')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def commit_id(repo, ref):
    if not ref or ref.startswith('-') or any(c.isspace() for c in ref):
        raise ValueError('Invalid Git ref')
    return git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}')


def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError('Invalid package version')
    return tuple(int(v) for v in VERSION.fullmatch(value).groups())


def package_version(repo, commit):
    return decode_json(git(repo, 'show', commit + ':plugin.json'))['version']


def requires_major(candidate, base):
    return version(candidate)[0] > version(base)[0]


def finding(code, path, message, **detail):
    return dict(code=code, path=path, message=message, **detail)


def scope_digest(root, paths):
    hasher = hashlib.sha256()
    for name in sorted(set(paths)):
        hasher.update(name.encode() + b'\0' + hashlib.sha256((root/name).read_bytes()).digest())
    return hasher.hexdigest()


def rerun_witness(root, check, panel_deps=None):
    """Run one named, pinned test case without evaluating a shell/command from a receipt."""
    test = relative(check['test'])
    case = check['case']
    if not test.startswith('tests/') or not isinstance(case, str) or not case.strip():
        raise ValueError('Witness requires a named repository test case.')
    if hashlib.sha256((root/test).read_bytes()).hexdigest() != check['testSha256']:
        raise ValueError('Witness test implementation changed.')
    if test.endswith('.py'):
        if not re.fullmatch(r'[A-Za-z_]\w*\.test_\w+',case):
            raise ValueError('Expected a unittest Class.test_method case.')
        driver = """import importlib.util, pathlib, sys, unittest
path = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(path.parent))
spec = importlib.util.spec_from_file_location(path.stem, path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
suite = unittest.defaultTestLoader.loadTestsFromName(sys.argv[2], module)
result = unittest.TextTestRunner().run(suite)
sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 and not result.skipped and not result.expectedFailures else 1)
"""
        args = [sys.executable, '-B','-c',driver,test,case]
    elif Path(test).suffix in {'.mjs','.cjs','.js'}:
        args = ['node','--test','--test-reporter=tap','--test-name-pattern','^' + re.escape(case) + '$',test]
    else:
        raise ValueError('Unsupported witness test runner.')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1',
           'PYTHONPATH':os.pathsep.join(str(p.resolve()) for p in (root, root/'tests', root/'tools'))}
    deps = Path(panel_deps or os.environ.get('FIGMA_FLOW_PANEL_DEPENDENCIES') or root/'panel-ui/node_modules').resolve()
    env['NODE_PATH'] = str(deps) if deps.is_dir() else ''
    env['FIGMA_FLOW_PANEL_DEPENDENCIES'] = env['NODE_PATH']
    result = subprocess.run(args,cwd=root,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=120)
    if args[0] == 'node':
        # A file without registered cases can report one passing file-level subtest.
        # Only a passing TAP result for the reviewed case is a witness.
        expected = re.escape(case.replace('#', r'\#'))
        named = re.search(r'^[ \t]*ok [0-9]+ - '+expected+r'[ \t]*$',result.stdout,re.M)
        if not named:
            raise ValueError(f'Named test case did not pass at this revision: {test} {case}')
    if result.returncode:
        raise ValueError(f'Witness did not pass at this revision: {test} {case}')


def authority_field(path, pointer):
    """Resolve a JSON field or a unique ATX section of a normative Markdown document."""
    parts = pointer_parts(pointer)
    if path.suffix.lower() not in {'.md', '.markdown'}:
        return json_member(read_json(path), parts)

    if len(parts) != 2 or parts[0] != 'sections' or not parts[1].strip():
        raise ValueError('Markdown authority requires /sections/<exact heading>.')
    lines = path.read_text(encoding='utf-8').splitlines()
    headings = []
    fence = ''
    in_comment = False
    visible = []
    for index, line in enumerate(lines):
        if fence:
            visible.append(line)
            if re.fullmatch(r' {0,3}' + fence[0] + '{' + str(len(fence)) + r',}[ \t]*', line):
                fence = ''
            continue
        if in_comment:
            _, closed, line = line.partition('-->')
            in_comment = not closed
        while '<!--' in line:
            prefix, _, tail = line.partition('<!--')
            _, closed, suffix = tail.partition('-->')
            line = prefix + suffix
            if not closed:
                in_comment = True
                break
        visible.append(line)
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if opening:
            fence = opening.group(1)
            continue
        match = re.fullmatch(r' {0,3}(#{1,6})[ \t]+(.+?)[ \t]*', line)
        if match:
            title = re.sub(r'[ \t]+#+$', '', match[2]).strip()
            headings.append((index, len(match[1]), title))
    matches = [(i, level) for i, level, title in headings if title == parts[1]]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous Markdown authority section: ' + parts[1])
    start, level = matches[0]
    end = next((i for i, depth, _ in headings if i > start and depth <= level), len(lines))
    text = '\n'.join(visible[start + 1:end]).strip()
    if not text:
        raise ValueError('Empty Markdown authority section: ' + parts[1])
    return text


def verify_review(root, surface, paths, owners, fingerprint, panel_deps=None):
    """A review binds every scoped file to an actual JSON authority and a witnessed check."""
    id_ = surface['id']
    note = f'release/reviews/{id_}.json'
    if not (root/note).is_file():
        return [finding('unreviewed-surface', note, 'Hardcoding review has no current source-bound evidence.',
                        surface=id_, count=len(paths))]
    try:
        doc = read_json(root/note)
        if (doc.get('schema') != 'figma-flow-major-review-v1' or doc.get('surface') != id_
                or doc.get('fingerprint') != fingerprint):
            raise ValueError('Review is stale or bound to another surface.')
        if doc.get('openFindings') != []:
            raise ValueError('Hardcoding findings are open or unreported.')
        covered = set()
        reruns = {}
        for binding in doc['bindings']:
            owner, sep, pointer = binding['authority'].partition('#')
            if relative(owner) not in owners:
                raise ValueError('Binding points outside its graph-declared authorities.')
            if not sep or not isinstance(binding['reason'], str) or not binding['reason'].strip():
                raise ValueError('Each binding needs a field-level authority and an explanation.')
            authority_field(root/owner, pointer)
            if not isinstance(binding['files'], list) or not binding['files'] or not set(binding['files']) <= set(paths):
                raise ValueError('Binding lists missing files or files outside the reviewed surface.')
            if not isinstance(binding['witnesses'], list) or not binding['witnesses']:
                raise ValueError('No behavioral witness in binding.')
            for witness in binding['witnesses']:
                proof_path = relative(witness['path'])
                if hashlib.sha256((root/proof_path).read_bytes()).hexdigest() != witness['sha256']:
                    raise ValueError('Witness bytes changed.')
                proof = read_json(root/proof_path)
                if (proof.get('surfaceFingerprint') != fingerprint or proof.get('status') != 'passed'
                        or not isinstance(proof.get('checks'), list) or not proof['checks'] or
                        any(not isinstance(c, dict) or not c.get('assertion') or 'observed' not in c
                            for c in proof['checks'])):
                    raise ValueError('Witness must record the assertions and observations at this fingerprint.')
                accounted = set()
                for c in proof['checks']:
                    if c.get('authority') != binding['authority'] or not isinstance(c.get('covers'),list):
                        raise ValueError('Witness must name its authority field and covered files.')
                    accounted.update(c['covers'])
                    reruns[(c['test'],c['case'],c['testSha256'])] = c
                if not set(binding['files']) <= accounted:
                    raise ValueError('Witness does not cover all files in this binding.')
            covered.update(binding['files'])
        if covered != set(paths):
            raise ValueError(f'Missing bindings for {len(set(paths)-covered)} distributed files.')
        for c in reruns.values():
            rerun_witness(root,c,panel_deps)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as exc:
        return [finding('invalid-surface-review', note, str(exc), surface=id_)]
    return []


def inventory(root, files, panel_deps=None):
    index = ReleaseOwnership(read_json(root/REGISTRY))
    surfaces, checks = index.surfaces, index.checks
    owners = {k:set() for k in surfaces}
    issues = []
    linked_checks = {checks[check] for names in index.checked_by.values() for check in names}
    for id_, owner_ids in index.owned_by.items():
        for owner_id in owner_ids:
            owner_path = index.authorities[owner_id]
            owners[id_].add(owner_path)
            if 'members' in index.nodes[owner_id] and owner_path in files:
                membership = index.nodes[owner_id]['members']
                records = authority_field(root/owner_path, membership['pointer'])
                if not isinstance(records, list):
                    raise ValueError('Authority member index must point to an array.')
                for row in records:
                    owners[id_].add(relative(row[membership['pathField']]))
    classified = {key: [] for key in surfaces}
    for id_ in surfaces:
        if not owners[id_] or not owners[id_] <= files:
            issues.append(finding('missing-surface-authority',REGISTRY,'Source owner missing from release graph or archive.',surface=id_))
    for file in sorted(files):
        match = index.locate(file)
        if match is None:
            issues.append(finding('unowned-archive-file',file,'No owning surface in the release graph.'))
        else:
            classified[match[0]].append(file)
    report = []
    for id_, paths in classified.items():
        surface = surfaces[id_]
        mode = surface['coverage']
        if not paths:
            issues.append(finding('empty-surface',REGISTRY,'Registered surface disappeared from archive.',surface=id_))
        fingerprint = scope_digest(root, set(paths) | (owners[id_] & files))
        report.append(dict(id=id_, role=mode, files=paths, fingerprint=fingerprint, owners=sorted(owners[id_])))
        # Role boundaries apply to archive paths, even if a registry entry is relabelled.
        for name in paths:
            eligible = {
                'test-oracle': name.startswith('tests/'),
                'upstream': name.startswith(('vendor/skills/', 'vendor/acorn/')),
                'build-projection': name.startswith('figma-bridge/assets/'),
                'record': name in {'CHANGELOG.md','LICENSE'} or (name.startswith('docs/llm-wiki/') and Path(name).suffix in {'.json','.md'}),
                'gate-data': name == REGISTRY or (name.startswith('release/reviews/') and name.endswith('.json')),
            }
            if mode in eligible and not eligible[mode]:
                issues.append(finding('incorrect-support-role',name,'First-party product file classified outside review.',role=mode))
        if mode == 'review':
            issues.extend(verify_review(root,surface,paths,owners[id_],fingerprint,panel_deps))
        elif mode == 'projection' and set(paths) != {'plugin.json','.codex-plugin/plugin.json'}:
            issues.append(finding('unverified-projection',REGISTRY,'Unknown derived metadata in release projection.',surface=id_))
        if mode in {'review','projection'}:
            for name in paths:
                if name.endswith('.json'):
                    try:
                        read_json(root/name)
                    except (UnicodeError, ValueError) as exc:
                        issues.append(finding('ambiguous-json-authority',name,str(exc)))
                if Path(name).suffix.lower() not in {'.js','.mjs','.cjs','.ts','.jsx','.tsx','.py','.css','.html','.json','.yml','.yaml','.sh'}:
                    continue
                data = (root/name).read_bytes()
                for match in LOCAL_HOME.finditer(data):
                    issues.append(finding('machine-specific-home',name,'Machine-local path embedded in distributed first-party source.',
                                          line=data.count(b'\n',0,match.start())+1))
                    break
    for path in sorted(index.roots):
        if path not in files and not any(n.startswith(path + '/') for n in files):
            issues.append(finding('missing-archive-root',path,'Registered distribution input is absent.'))
    if not set(checks.values()) <= files or set(checks.values()) != set(CONTROLS) or linked_checks != set(CONTROLS):
        issues.append(finding('missing-release-control',REGISTRY,'Required checks must all have graph relationships.'))
    return issues, report


def bundle_check(root, files, deps):
    name = 'figma-bridge/assets'
    if not deps.is_dir():
        return [finding('panel-build-unverified',name,'Install the project panel dependencies before the major gate.')]
    expected = {n for n in files if n.startswith(name + '/')}
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        for n in files:
            if n not in expected:
                (stage/n).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/n,stage/n)
        (stage/'panel-ui/node_modules').symlink_to(deps.resolve(),target_is_directory=True)
        result = subprocess.run(['node',str(stage/'panel-ui/build.mjs')],cwd=stage,capture_output=True,text=True,timeout=120)
        if result.returncode:
            return [finding('panel-build-failed',name,'Rebuilding the candidate from archived inputs failed.',
                            diagnostic=result.stderr.replace(str(stage),'<tree>').replace(str(deps.resolve()),'<panel dependencies>')[:800])]
        output = {p.relative_to(stage).as_posix() for p in (stage/name).rglob('*') if p.is_file()}
        return [finding('panel-build-drift',n,'Archive output differs from a clean build.')
                for n in sorted(output | expected)
                if n not in output or n not in expected or (stage/n).read_bytes() != (root/n).read_bytes()]


CONTROLS = {
    'tools/plugin_manifest.py': plugin_manifest.check,
    'tools/spec_graph_coverage.py': spec_graph_coverage.check,
    'tools/runtime_authority.py': runtime_authority.check,
    'tools/panel_authority.py': panel_authority.check,
    'tools/report_appearance.py': report_appearance.check,
    'tools/native_appearance.py': native_appearance.check,
    'tools/major_release.py': bundle_check,
}


def checker_inputs(root):
    """Pin local imports of every check, including the two file-loaded graph/view modules."""
    pending = [*CONTROLS,'skills/figma-flow/scripts/graph.py','tools/plugin_panel.py']
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        path = root / name
        if not path.is_file():
            continue
        for node in ast.walk(ast.parse(path.read_bytes(), filename=name)):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for module in names:
                local = path.parent.joinpath(*module.split('.')).with_suffix('.py')
                if local.is_file():
                    pending.append(local.relative_to(root).as_posix())
    return seen


def audit(root, files, deps=None):
    issues, surfaces = inventory(root, files, deps)
    for name, check in CONTROLS.items():
        try:
            if check is bundle_check:
                issues.extend(check(root,files,deps or root/'panel-ui/node_modules'))
            else:
                issues.extend(check(root))
        except (OSError, ValueError, KeyError, TypeError, SyntaxError, subprocess.SubprocessError) as exc:
            issues.append(finding('check-unavailable',name,str(exc)))
    blockers = [i for i in issues if i.get('severity') not in ('advisory','warning','info')]
    return {'status':'blocked' if blockers else 'passed','blockerCount':len(blockers),
            'findings':issues,'surfaces':surfaces,'archiveFileCount':len(files)}


def archive_source(repo, commit, target):
    subprocess.run(['git','-C',str(repo),'archive','--format=zip','--prefix=figma-flow-plugin/',
                    '--output',str(target),commit], check=True)


def inspect_archive(archive, root):
    files = set()
    with ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            if entry.is_dir():
                continue
            prefix = 'figma-flow-plugin/'
            if not entry.filename.startswith(prefix):
                raise ValueError('Unexpected archive prefix.')
            name = relative(entry.filename[len(prefix):])
            if name in files or entry.external_attr >> 28 == 10:
                raise ValueError('Duplicate archive member or symlink: '+name)
            files.add(name)
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(entry))
    return files


def audit_archived_tree(tree, files, deps):
    """Supply installed dependencies inside the disposable archive during witness replay."""
    before = scope_digest(tree, files)
    dependency_link = tree / 'panel-ui/node_modules'
    deps = Path(deps).resolve()
    linked = dependency_link.parent.is_dir() and deps.is_dir()
    if linked:
        if dependency_link.exists() or dependency_link.is_symlink():
            raise ValueError('The candidate archive contains its own panel dependency directory.')
        dependency_link.symlink_to(deps, target_is_directory=True)
    try:
        report = audit(tree, files, deps)
    finally:
        if linked:
            if not dependency_link.is_symlink() or dependency_link.resolve() != deps:
                raise ValueError('A release check modified the temporary panel dependency link.')
            dependency_link.unlink()
    remaining = {p.relative_to(tree).as_posix() for p in tree.rglob('*') if p.is_file()}
    if remaining != files or scope_digest(tree, files) != before:
        raise ValueError('A release check modified the inspected candidate tree.')
    return report


def run(args):
    repo = Path(args.repo).resolve()
    target = commit_id(repo,args.ref)
    declared = package_version(repo,target)
    if args.candidate and args.archive:
        raise ValueError('--candidate is for prospective audits, not for packaging.')
    candidate = args.candidate or declared
    parts = version(candidate)
    version(declared)
    codex_manifest = decode_json(git(repo,'show',target+':.codex-plugin/plugin.json'))
    if codex_manifest['version'] != declared:
        raise ValueError('Manifest versions differ at the candidate commit.')
    named_ref = git(repo,'rev-parse','--symbolic-full-name',args.ref)
    tag = named_ref.removeprefix('refs/tags/') if named_ref.startswith('refs/tags/') else ''
    if tag.startswith('v') and tag != 'v' + declared:
        raise ValueError('Tag does not match the portable plugin manifest.')
    # No tag of this major on an earlier ancestor means this is its first distribution.
    # A caller-supplied base can trigger a gate, but can never suppress this test.
    is_major = parts[0] > 0
    if is_major and parts[1:] != (0, 0):
        for tag in git(repo, 'tag','--merged',target,'--list',f'v{parts[0]}.*').splitlines():
            if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
                continue
            prior = commit_id(repo,tag)
            if prior != target and version(tag[1:]) < parts and package_version(repo,prior) == tag[1:]:
                is_major = False
                break
    # Backport tags on separate branches remain eligible; a rollback on this lineage
    # cannot disable the major gate by lowering the manifest's major number.
    for published in git(repo,'tag','--merged',target,'--list','v*').splitlines():
        if re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',published) and version(published[1:])[0] > parts[0]:
            prior = commit_id(repo,published)
            if prior != target and package_version(repo,prior) == published[1:]:
                raise ValueError('Major downgrade on the candidate release lineage.')
    if args.base_ref:
        base = commit_id(repo,args.base_ref)
        if version(package_version(repo,base))[0] > parts[0]:
            raise ValueError('Major downgrade from the selected baseline.')
        is_major |= requires_major(candidate,package_version(repo,base))
    if args.if_major and not is_major:
        report = {'status':'not-applicable','reason':'no major transition'}
    else:
        report = None
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)
        artifact = tmp/'source.zip'
        if report is None or args.archive:
            archive_source(repo,target,artifact)
        if report is None:
            tree = tmp/'tree'
            files = inspect_archive(artifact,tree)
            check_sources = checker_inputs(ROOT) | checker_inputs(tree)
            mismatch = sorted(n for n in check_sources if n not in files or not (ROOT/n).is_file()
                              or (tree/n).read_bytes() != (ROOT/n).read_bytes())
            if mismatch:
                report = {'status':'blocked','blockerCount':len(mismatch),
                          'findings':[finding('checker-version-drift',n,'Use the release checker from this candidate.') for n in mismatch]}
            else:
                report = audit_archived_tree(tree, files, repo/'panel-ui/node_modules')
        if args.archive and report['status'] in {'passed','not-applicable'}:
            dest = Path(args.archive)
            with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as staged:
                new_file = Path(staged.name)
                try:
                    with artifact.open('rb') as source:
                        shutil.copyfileobj(source,staged)
                    staged.flush()
                    os.fsync(staged.fileno())
                    os.link(new_file,dest)
                finally:
                    new_file.unlink(missing_ok=True)
    return {**report,'commit':target,'version':declared,'candidate':candidate,'majorTransition':is_major}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=ROOT, type=Path)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--candidate', help='Evaluate an intended version without changing the manifest.')
    parser.add_argument('--base-ref', help='Previous release or base commit used to detect a major increment.')
    parser.add_argument('--if-major', action='store_true', help='Skip full audit only for a non-major transition.')
    parser.add_argument('--archive', type=Path, help='Publish a new ZIP only if the applicable gate passes.')
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, subprocess.SubprocessError) as exc:
        report = {'status':'blocked','error':str(exc)}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status'] in {'passed','not-applicable'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
