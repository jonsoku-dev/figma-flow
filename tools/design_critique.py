"""Validate current artifact-linked critique, not aesthetic quality or GUI execution."""
import re
import math

SCHEMA = 'figma-flow-artifact-critique-v2'


def _reason(value):
    return isinstance(value, str) and len(value.strip()) >= 35 and not re.search(r'looks? good|all (?:fine|good)|no issues|lorem ipsum|문제\s*없|좋습니다', value, re.I)


def validate(data, review, current, digest):
    if review.get('schema') != SCHEMA:
        raise ValueError('Explicit-mode drafts require artifact-linked critique v2; legacy prose is unverified')
    if review.get('brief') != data['brief'] or review.get('native_layout') != data.get('native_layout'):
        raise ValueError('Critique brief/layout pins are stale or missing')
    rows = review.get('candidates', [])
    if len(rows) != len(data['candidates']):
        raise ValueError('Critique requires every current candidate')
    for candidate in data['candidates']:
        item = next((r for r in rows if r.get('id') == candidate['id']), {})
        artifacts = {k: candidate[k] for k in ('source', 'review', 'product_graph', 'previews')}
        if item.get('artifacts') != artifacts or item.get('candidate_sha256') != candidate['sha256']:
            raise ValueError('Critique must pin current source, review, graph and viewport previews')
        observations = item.get('observations', [])
        expected = {'purpose', 'content_hierarchy', 'typography', 'layout', 'assets', 'responsive', 'interaction'}
        if len(observations) != len(expected) or {r.get('aspect') for r in observations} != expected:
            raise ValueError('Critique needs located purpose/content/type/layout/assets/responsive/interaction observations')
        if len({r.get('observation') for r in observations}) != len(observations):
            raise ValueError('Repeated generic prose cannot review separate design aspects')
        for row in observations:
            role = row.get('artifact')
            locator, excerpt = row.get('locator'), row.get('excerpt')
            if role in ('source', 'review', 'product_graph'):
                if not isinstance(locator, str) or not locator.strip() or not isinstance(excerpt, str) or len(excerpt.strip()) < 8:
                    raise ValueError('Critique requires an actual artifact locator and excerpt')
                text = current(candidate[role]).read_text()
                if locator not in text or excerpt not in text:
                    raise ValueError('Critique locator/excerpt is absent from the current artifact')
            elif role in ('preview-mobile', 'preview-desktop'):
                preview = next(p for p in candidate['previews'] if role == 'preview-' + p['viewport'])
                current(preview['file'])
                region = locator.get('region') if isinstance(locator, dict) else None
                if not isinstance(region, list) or len(region) != 4 or any(type(n) not in (int, float) or (type(n) is float and not math.isfinite(n)) for n in region):
                    raise ValueError('Preview critique requires a viewport pixel region [x,y,width,height]')
                x, y, width, height = region
                if min(x, y) < 0 or min(width, height) <= 0 or x + width > preview['width'] or y + height > preview['height']:
                    raise ValueError('Preview critique region escapes the pinned viewport')
            else:
                raise ValueError('Unknown critique artifact')
            if not _reason(row.get('observation')) or not _reason(row.get('reason')) or row.get('resolution') not in ('clean', 'fixed'):
                raise ValueError('Generic, unsupported or unresolved critique observation')
    warnings = []
    if data.get('native_layout'):
        import design_quality
        report = design_quality.run(current(data['native_layout']))
        if report['errors']:
            raise ValueError('Objective authored layout errors must be fixed before review')
        warnings = report['warnings']
    dispositions = review.get('warning_dispositions', [])
    if len(dispositions) != len(warnings) or {r.get('warning_sha256') for r in dispositions} != {digest(w) for w in warnings}:
        raise ValueError('Each current heuristic warning needs its exact warning identity and disposition')
    for row in dispositions:
        warning = next(w for w in warnings if digest(w) == row['warning_sha256'])
        if row.get('warning') != warning or row.get('disposition') not in ('accepted', 'fixed') or not _reason(row.get('reason')):
            raise ValueError('Unsupported heuristic warning disposition')
        if row['disposition'] == 'fixed':
            raise ValueError('A current warning cannot be marked fixed; fix and rerun the layout first')
    return {'evidence': 'current-artifact-linked-agent-critique', 'visual_quality': 'unverified', 'visual_execution': 'unverified'}
