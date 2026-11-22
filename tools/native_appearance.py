"""Resolve the Design helper defaults and embed them in their standalone Figma sources."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('figma-bridge/presentation.json')


def resolve(root, value):
    if isinstance(value, dict) and set(value) in ({'source','pointer'}, {'source','pointer','select'}):
        path=(root/value['source']).resolve()
        path.relative_to(root.resolve())
        field=json.loads(path.read_bytes())
        for part in value['pointer'].removeprefix('/').split('/'):
            part=part.replace('~1','/').replace('~0','~')
            field=field[int(part)] if isinstance(field,list) else field[part]
        if 'select' in value:
            if value['select'] != 'keys' or not isinstance(field, dict):
                raise ValueError('Unknown native field selection')
            return list(field)
        return field
    if isinstance(value, dict):
        return {k:resolve(root,v) for k,v in value.items()}
    if isinstance(value, list):
        return [resolve(root,v) for v in value]
    return value


def appearance(name,root=ROOT):
    graph=json.loads((root/SOURCE).read_bytes())
    if graph['schema']!='figma-flow-native-appearance-v1':
        raise ValueError('Unknown native appearance schema')
    return resolve(root,graph['modules'][name]['fields'])


def projections(root):
    graph=json.loads((root/SOURCE).read_bytes())
    for name,node in graph['modules'].items():
        path=Path(node['source'])
        if path.parent!=SOURCE.parent or path.suffix!='.js' or not re.fullmatch('[A-Z][A-Z0-9_]*',node['symbol']):
            raise ValueError('Expected one standalone Figma helper')
        start=f'/* native appearance: begin {name} */\n'
        end=f'/* native appearance: end {name} */'
        current=(root/path).read_text(encoding='utf8')
        if current.count(start)!=1 or current.count(end)!=1:
            raise ValueError('Missing native appearance projection in '+str(path))
        prefix,tail=current.split(start);_,suffix=tail.split(end)
        fields=appearance(name,root)
        data=json.dumps(fields,ensure_ascii=False,indent=2)
        js='const '+node['symbol']+' = '+data+';\n'
        if node.get('trackExisting'):
            stable=json.dumps({k:fields[k] for k in node['trackExisting']},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            js+='const '+node['symbol']+'_SHA256 = '+json.dumps(hashlib.sha256(stable).hexdigest())+';\n'
        yield path,current,prefix+start+js+end+suffix


def check(root):
    return [{'code':'native-appearance-drift','path':str(path),'message':'Republish the graph-owned Design helper.'}
            for path,current,expected in projections(root) if current!=expected]


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    for path,current,expected in projections(ROOT):
        if current!=expected:
            if not args.write:
                parser.exit(1,'Stale native appearance: '+str(path)+'\n')
            (ROOT/path).write_text(expected,encoding='utf8')
