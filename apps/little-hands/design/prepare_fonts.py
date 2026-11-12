#!/usr/bin/env python3
"""Derive local metric faces from the app's OFL variable WOFF2, without substitution."""
import hashlib
import json
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

root=Path(__file__).resolve().parent
source=root.parent/'static/littlehands/fonts/Hahmlet.woff2'
faces={}
for style,weight in [('Regular',400),('Bold',700)]:
    font=TTFont(source)
    if 'fvar' not in font:
        raise ValueError('Expected actual variable Hahmlet source')
    font=instantiateVariableFont(font,{'wght':weight},inplace=True,updateFontNames=True)
    font.flavor=None
    destination=root/'fonts'/('Hahmlet-'+style+'.ttf')
    font.save(destination)
    faces[style]={'file':destination.relative_to(root).as_posix(),'index':0}
(root/'fonts/sources.json').write_text(json.dumps({'Hahmlet':{'styles':faces}},ensure_ascii=False,indent=2)+'\n')
(root/'fonts/provenance.json').write_text(json.dumps({'source':'../../static/littlehands/fonts/Hahmlet.woff2','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'license':'../../static/littlehands/fonts/OFL.txt','operation':'FontTools variable wght instantiation and WOFF2-to-TTF container conversion for local metric checks only; no browser/Figma observation'},indent=2)+'\n')
print('Prepared actual Hahmlet400/700 metric faces locally')
