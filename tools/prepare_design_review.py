#!/usr/bin/env python3
"""Pin actual creative observations into a review receipt; never fabricate missing observations."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct

import design_review


def prepare(project, out, artifacts, *, operation='create', target_kind='website', font=None, critique=None,
            applications=None, assets=None, asset_path_base=None, batch_path_base=None, skins=(), music_directed=False, game_id=None):
    project, out = Path(project).resolve(), Path(out).resolve()
    if target_kind == 'game-campaign' and not game_id:
        raise ValueError('Game profile requires the selected actual --game-id')
    if not out.is_relative_to(project):
        raise ValueError('Prepared review output must stay inside the selected project')
    if not artifacts:
        raise ValueError('Select actual current implementation/native artifacts')

    def record(value, base=project):
        path = Path(value)
        path = path if path.is_absolute() else Path(base) / path
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(project):
            raise ValueError('Selected evidence must be an existing file inside project: ' + str(path))
        return {'path': os.path.relpath(path, project), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def normalize(value, base=project):
        value = copy.deepcopy(value)
        if isinstance(value, dict):
            if isinstance(value.get('path'), str):
                actual = record(value['path'], base)
                if value.get('sha256') and value['sha256'] != actual['sha256']:
                    raise ValueError('Refuse to rewrite a mismatched original evidence hash: ' + value['path'])
                value.update(actual)
                if value.get('viewport'):
                    raw = (project / value['path']).read_bytes()
                    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
                        value['width'], value['height'] = struct.unpack('>II', raw[16:24])
                    else:
                        from PIL import Image
                        with Image.open(project / value['path']) as image:
                            value['width'], value['height'] = image.size
            return {key: normalize(item, base) if isinstance(item, (dict, list)) else item for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item, base) for item in value]
        return value

    def document(path, fallback):
        return json.loads(Path(path).read_text()) if path else fallback

    pinned_artifacts = [record(path) for path in artifacts]
    hashes = {item['path']: item['sha256'] for item in pinned_artifacts}
    skill_records = []
    application_data = document(applications, {})
    for identity in sorted(design_review.SKILLS | ({'taste'} if music_directed else set())):
        path = design_review.resolve_skill(identity)
        item = {'id': identity, 'source': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'application': application_data.get(identity, {'target': pinned_artifacts[0]['path'],
                    'decision': 'PENDING actual source-specific decisions before authoring and after critique.',
                    'phases': ['before-authoring', 'after-critique']})}
        if identity == 'taste':
            item['scope'] = 'rhythm-and-motion-only'
        elif identity == 'design-taste-frontend' and target_kind == 'product-ui':
            item['scope'] = 'limited-to-applicable-surfaces'
        skill_records.append(item)
    receipt = {'schema': 'figma-flow-design-review-v1', 'skills': skill_records, 'artifacts': pinned_artifacts,
               'font_selection': normalize(document(font, {'sequence': 1, 'sample_text': 'PENDING actual target-script specimens',
                   'candidates': [], 'chosen': [], 'specimens': []})), 'authoring': {'sequence': 2},
               'critique': normalize(document(critique, {'sequence': 3, 'reviewer': None, 'findings': [],
                   'confirmation': {'sequence': 4, 'captures': []}})), 'responsive_skins': []}
    for capture in receipt['critique'].get('confirmation', {}).get('captures', []):
        capture['artifact_hashes'] = hashes
    for path in skins:
        data = document(path, {})
        receipt['responsive_skins'].extend(normalize(data if isinstance(data, list) else [data]))
    if assets:
        assets = Path(assets).resolve()
        data = document(assets, {})
        original_base = Path(asset_path_base).resolve() if asset_path_base else assets.parent
        receipt['asset_batch'] = normalize(data['batch'], original_base)
        if batch_path_base:
            receipt['asset_batch']['path_base'] = os.path.relpath(Path(batch_path_base).resolve(), project)
        receipt['assets'] = normalize(data['assets'], original_base)
        for item in receipt['assets']:
            item['generation']['path_base'] = os.path.relpath(original_base, project)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'design-review.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    declaration = {'operation': operation, 'target_kind': target_kind,
                   'receipt': os.path.relpath(out / 'design-review.json', project)}
    if game_id:
        declaration['game_id'] = game_id
    if music_directed:
        declaration['music_directed'] = True
    (out / 'bindings-design-review.json').write_text(json.dumps({'design_review': declaration}, ensure_ascii=False, indent=2) + '\n')
    return {'status': 'prepared-not-reviewed', 'receipt': str(out / 'design-review.json'),
            'declaration': str(out / 'bindings-design-review.json'),
            'next': 'Merge declaration into project bindings, preserve actual observed evidence, run check_project.py --intent create. Missing records stay blocked.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--artifact', action='append', required=True)
    p.add_argument('--operation', choices=sorted(design_review.OPERATIONS), default='create')
    p.add_argument('--target-kind', choices=('website', 'product-ui', 'game-campaign'), default='website')
    for name in ('font', 'critique', 'applications', 'assets', 'asset-path-base', 'batch-path-base'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--skin', type=Path, action='append', default=[])
    p.add_argument('--music-directed', action='store_true')
    p.add_argument('--game-id')
    a = p.parse_args()
    try:
        print(json.dumps(prepare(a.project, a.out, a.artifact, operation=a.operation, target_kind=a.target_kind,
            font=a.font, critique=a.critique, applications=a.applications, assets=a.assets,
            asset_path_base=a.asset_path_base, batch_path_base=a.batch_path_base, skins=a.skin,
            music_directed=a.music_directed, game_id=a.game_id), ensure_ascii=False))
    except (OSError, ValueError, KeyError, ImportError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
