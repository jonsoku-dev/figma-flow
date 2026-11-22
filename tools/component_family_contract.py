"""Project the code-free family vocabulary and layout into the standalone native helper."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('library/component-families.json')
RUNTIME = Path('figma-bridge/semantic_components.js')
BEGIN = '  /* Generated family contract: begin */\n'
END = '  /* Generated family contract: end */'


def projection(root):
    data=json.loads((root/DATA).read_bytes())
    if data['schema']!='figma-flow-component-family-authority-v1':
        raise ValueError('Unknown component family authority')
    names={'required_layout':'requiredLayout','canonical_states':'canonicalStates',
           'canonical_text_slots':'canonicalTextSlots','extra_axes':'extraAxes'}
    native={k:{names.get(key,key):value for key,value in v.items()} for k,v in data['families'].items()}
    def block(name,values):
        pretty=json.dumps(values,ensure_ascii=False,indent=2).replace('\n','\n  ')
        return '  const '+name+' = '+pretty+';\n'
    source=(root/RUNTIME).read_text(encoding='utf8')
    if source.count(BEGIN)!=1 or source.count(END)!=1:
        raise ValueError('Expected one native component family projection')
    prefix,tail=source.split(BEGIN)
    _,suffix=tail.split(END)
    return prefix+BEGIN+block('CANONICAL_FAMILIES',native)+block('NATIVE_LAYOUT',data['native'])+END+suffix


def check(root):
    if projection(root)!=(root/RUNTIME).read_text(encoding='utf8'):
        return [{'code':'family-authority-drift','path':RUNTIME.as_posix(),'message':'Regenerate the native component family projection.'}]
    return []


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    if args.write:
        (ROOT/RUNTIME).write_text(projection(ROOT),encoding='utf8')
    return int(bool(check(ROOT)))


if __name__=='__main__':
    raise SystemExit(main())
