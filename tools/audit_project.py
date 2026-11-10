#!/usr/bin/env python3
"""Audit local source dependencies and requirement contradictions independently.

Explicit paths may be absolute or relative to --project. Output must be new.
Exit 1 means a finding, 2 means limited/unknown coverage, 0 means checked scope clear.
"""
import argparse
import re
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts'))
import ssot
import audit_dependencies
import audit_brief


def local_path(root, value, *, project_only=True):
    path = (root / value).resolve(strict=True)
    if (project_only and not path.is_relative_to(root)) or not path.is_file():
        raise ValueError('Input must be a file inside project: ' + str(value))
    return path


def input_name(root, path):
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def audit_project(root, graph_path, bindings_path, brief_path, specs=(), *, project_only=True, review=None):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Project must be a directory')
    graph_path, bindings_path, brief_path = [local_path(root, p, project_only=project_only) for p in (graph_path, bindings_path, brief_path)]
    specs = sorted({local_path(root, p) for p in specs} - {brief_path})
    review_path = local_path(root, review) if review else None
    pinned = ssot.build(brief_path, graph_path, bindings_path, root, scope='local-only')
    graph_hash, graph_bytes = ssot.read_local(graph_path, capture=True)
    bindings_hash, bindings_bytes = ssot.read_local(bindings_path, capture=True)
    if graph_hash != pinned['inputs']['graph']['sha256'] or bindings_hash != pinned['inputs']['bindings']['sha256']:
        raise ValueError('Audit inputs changed while reading')
    data, bindings = json.loads(graph_bytes), json.loads(bindings_bytes)
    normalized = {**bindings, 'evidence': {}}
    unavailable = []
    input_hashes = {}
    refs = list(pinned['inputs'].values()) + list(pinned['authorities'].values())
    for node_id, node in pinned['nodes'].items():
        refs.extend(node['evidence'])
        if node['type'] in ('code', 'test'):
            normalized['evidence'][node_id] = []
            for ref in node['evidence']:
                if ref['availability'] == 'local-hashed':
                    path = local_path(root, ref['path'], project_only=project_only)
                    if path.is_relative_to(root):
                        normalized['evidence'][node_id].append(str(path.relative_to(root)))
                    else:
                        unavailable.append({'path': str(path), 'node': node_id, 'reason': 'bound source outside project audit scope'})
                else:
                    unavailable.append({'path': ref['path'], 'node': node_id, 'reason': 'bound evidence unavailable'})
    for ref in refs:
        if ref['availability'] == 'local-hashed':
            path = local_path(root, ref['path'], project_only=project_only)
            input_hashes[input_name(root, path)] = ref['sha256']
    for path in [*specs, *([review_path] if review_path else [])]:
        input_hashes[str(path.relative_to(root))] = ssot.read_local(path)[0]
    # SSOT resolves graph sources and binding evidence against their own file bases.
    normalized_graph = {**data, 'nodes': [{k: v for k, v in node.items() if k != 'source'} for node in data['nodes']]}
    source = audit_dependencies.audit(root, normalized_graph, normalized)
    source['unknown'].extend(unavailable)
    if unavailable and source['status'] == 'clear':
        source['status'] = 'unknown'
    for name in source.get('scanned_files', []):
        path = local_path(root, name)
        digest = source.get('scanned_hashes', {}).get(name)
        if digest is None or input_hashes.get(name, digest) != digest:
            raise ValueError('Source bytes analyzed differ from pinned audit input: ' + name)
        input_hashes[name] = digest
    brief = audit_brief.audit([brief_path, *specs], review=review_path)
    for item in brief.get('sources', []):
        path = Path(item['file']).resolve(strict=True)
        if input_hashes.get(input_name(root, path)) != item['sha256']:
            raise ValueError('Brief bytes analyzed differ from pinned audit input: ' + str(path))
    if any(ssot.read_local(root / name)[0] != digest for name, digest in input_hashes.items()):
        raise ValueError('Audit inputs changed during analysis')
    blocked = brief['status'] == 'fail'
    return {'version': 1, 'project': str(root), 'inputs': dict(sorted(input_hashes.items())),
            'source_dependencies': source, 'brief_consistency': brief,
            'acceptance_claim': 'blocked-by-active-contradiction' if blocked else 'not-established',
            'status': 'findings' if source['missing'] or blocked else 'review' if source['status'] != 'clear' or brief['status'] != 'pass' else 'checked-scope-clear',
            'limitations': ['Source paths and requirement contradictions are separate judgments.',
                            'Proposed paths are not approved semantic graph facts; inputs are never rewritten.',
                            'Neither this audit nor passing selected tests establishes product acceptance.']}


def literal(value):
    """Keep quoted project prose and filenames inert in the Markdown report."""
    value = str(value).replace('\n', ' ').replace('\r', ' ')
    fence = '`' * (1 + max((len(part) for part in re.findall(r'`+', value)), default=0))
    return f'{fence} {value} {fence}'


def markdown(report):
    source, brief = report['source_dependencies'], report['brief_consistency']
    lines = ['# 로컬 프로젝트 감사', '',
             f"- 소스 의존성: `{source['status']}`. 확인된 누락 {len(source['missing'])}건, 후보 {len(source['candidates'])}건, 미해결 {len(source['unknown'])}건.",
             f"- 요구사항 일관성: `{brief['status']}`. 활성 모순 {len(brief['findings'])}건, 미분석 구문 {len(brief['unsupported'])}건, 명시적 과거·예시 {len(brief['ignored'])}건, 검토자 후보 {len(brief.get('review_findings', []))}건.",
             f"- 인수 완료 주장: `{report['acceptance_claim']}`.", '', '## 소스 근거', '']
    for category, key in [('확인된 누락', 'missing'), ('미확정 후보', 'candidates'), ('미해결', 'unknown')]:
        for item in source[key]:
            location = str(item.get('path', '')) + (':' + str(item['line']) if item.get('line') else '')
            detail = f"{item['from']} → {item['to']} ({item['kind']})" if 'from' in item else item['reason']
            lines.append(f'- {category}: {literal(location)} {literal(detail)}.')
    if not any(source[key] for key in ('missing', 'candidates', 'unknown')):
        lines.append('- 검사한 정적 참조에서 누락을 찾지 못했습니다.')
    lines.extend(['', '## 요구사항 근거', ''])
    for finding in brief['findings']:
        lines.append(f"- 활성 모순: `{finding['rule']}` / `{finding['scope']}` / `{finding['condition']}`.")
        for item in finding['evidence']:
            lines.append(f"  - {literal(str(item['file']) + ':' + str(item['line']))} {literal(item['quote'])}")
    if not brief['findings']:
        lines.append('- 추출된 규칙 사이에서 활성 모순을 찾지 못했습니다.')
    for item in brief['unsupported'][:8]:
        lines.append(f"- 검토 필요: {literal(str(item['file']) + ':' + str(item['line']))} {literal(item['reason'])}. {literal(item['quote'])}")
    if len(brief['unsupported']) > 8:
        lines.append(f"- 나머지 미분석 구문 {len(brief['unsupported']) - 8}건의 파일·줄·원문은 `audit.json`에 기록했습니다.")
    lines.extend(['', '## 검토자가 제안한 의미 모순 후보', ''])
    for finding in brief.get('review_findings', []):
        lines.append(f"- 판정 대기: {literal(finding['topic'])}. {literal(finding['rationale'])}")
        for item in finding['evidence']:
            lines.append(f"  - {literal(str(item['file']) + ':' + str(item['line']))} {literal(item['quote'])}")
    if not brief.get('review_findings'):
        lines.append('- 제출된 의미 검토 후보가 없습니다.')
    lines.extend(['', '## 검사 범위와 한계', '', '- 정적 소스 참조, 명시한 코드·테스트 바인딩, 입력한 브리프·명세의 지원 패턴만 검사했습니다.',
                  '- 동적 참조와 모호한 소유권은 미해결로 남깁니다. 화면 이동이나 파일 공유만으로 의미적 의존성을 확정하지 않습니다.',
                  '- 활성 모순은 인수 완료 주장을 차단합니다. 소스 누락·미해결은 선택 테스트 범위를 보수적으로 넓히며 유용한 테스트 실행은 계속합니다.',
                  '- 검토자 후보의 현재 파일·줄·인용만 대조했습니다. 공통 주제·범위·조건과 모순 판단은 검토자가 제안한 내용입니다.',
                  '- 제품 실행, 실제 브라우저, 전체 자연어 의미와 제품 인수 완료는 검증하지 않았습니다.'])
    lines.extend('- ' + item for item in source['limitations'])
    lines.append('- ' + brief['limitation'])
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'graph', 'bindings', 'brief', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--spec', action='append', default=[])
    parser.add_argument('--review', help='Optional pinned semantic-review candidates; never automatic proof')
    args = parser.parse_args(argv)
    try:
        out = Path(args.out).resolve()
        if out.exists():
            raise ValueError('Output directory already exists')
        result = audit_project(args.project, args.graph, args.bindings, args.brief, args.spec, review=args.review)
        root = Path(result['project'])
        if any((root / name) == out or (root / name).is_relative_to(out) for name in result['inputs']):
            raise ValueError('Output directory overlaps an input')
        out.mkdir(exist_ok=False)
        (out / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (out / 'audit.md').write_text(markdown(result), encoding='utf-8')
        return {'checked-scope-clear': 0, 'findings': 1, 'review': 2}[result['status']]
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
