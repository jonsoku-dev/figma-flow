#!/usr/bin/env python3
"""Prepare the declared metric faces from the pinned local variable font."""
import hashlib
import json
import os
from pathlib import Path
import re
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

root = Path(__file__).resolve().parent
static = root.parent / 'static/littlehands'
metadata = json.loads((static / 'sources.json').read_bytes())['font']
source = static / metadata['path']
license_path = static / metadata['license_path']
digest = hashlib.sha256(source.read_bytes()).hexdigest()
if digest != metadata['sha256'] or not license_path.is_file():
    raise ValueError('Metric preparation requires the declared font bytes and license')

roles = json.loads((root / 'tokens.json').read_bytes())['fonts']
faces = {}
for role in sorted(roles.values(), key=lambda row: row['weight']):
    family, style, weight = role['family'], role['native_style'], role['weight']
    if not all(re.fullmatch(r'[\w][\w -]*', value) for value in (family, style)):
        raise ValueError('Unsafe family or face name')
    with TTFont(source, recalcTimestamp=False) as font:
        families = {n.toUnicode() for n in font['name'].names if n.nameID in (1, 16)}
        weights = next((axis for axis in font['fvar'].axes if axis.axisTag == 'wght'), None)
        if family not in families or weights is None or not weights.minValue <= weight <= weights.maxValue:
            raise ValueError('The supplied font has no matching family and weight')
        instance = instantiateVariableFont(font, {'wght':weight}, inplace=True, updateFontNames=True)
        instance.flavor = None
        if style in faces.setdefault(family, {'styles':{}})['styles']:
            raise ValueError('Duplicate metric face')
        destination = root / 'fonts' / f'{family}-{style}.ttf'
        instance.save(destination)
        faces[family]['styles'][style] = {'file':destination.relative_to(root).as_posix(),'index':0}
(root/'fonts/sources.json').write_text(json.dumps(faces,ensure_ascii=False,indent=2)+'\n')
provenance = {
    'source':os.path.relpath(source, root/'fonts'), 'source_sha256':digest,
    'license':os.path.relpath(license_path, root/'fonts'),
    'operation':'FontTools variable wght instantiation and WOFF2-to-TTF container conversion for local metric checks only; no browser/Figma observation',
}
(root/'fonts/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print('Prepared metric faces from the pinned local font.')
