"""Render local report styles from their role-specific palettes and ordered CSS rules."""
import argparse
import json
from pathlib import Path
import re

TOOLS = Path(__file__).resolve().parent
SOURCE = 'report-presentation.json'
COLOR = re.compile(r'\$color\(([A-Za-z][A-Za-z0-9]*)\)')


def report_graph(tools=TOOLS):
    graph=json.loads((tools/SOURCE).read_bytes())
    if graph['schema']!='figma-flow-report-presentation-v1':
        raise ValueError('Unknown report appearance schema')
    return graph


def graphic(name, tools=TOOLS):
    return report_graph(tools)['graphics'][name]


def report_css(name, tools=TOOLS):
    surface=report_graph(tools)['surfaces'][name]
    css=''.join(surface['rules'])
    palette=surface['palette']
    if {m[1] for m in COLOR.finditer(css)}!=set(palette):
        raise ValueError('Missing or unused report palette role in '+name)
    for value in palette.values():
        if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',value):
            raise ValueError('Invalid report palette color in '+name)
    return COLOR.sub(lambda m:palette[m[1]],css)


def static_projections(tools):
    graph=json.loads((tools/SOURCE).read_bytes())
    for name,surface in graph['surfaces'].items():
        css=report_css(name,tools)
        if 'stylesheet' in surface:
            filename=Path(surface['stylesheet'])
            if filename.name!=str(filename) or filename.suffix!='.css':
                raise ValueError('Expected a standalone report stylesheet')
            path=tools/filename
            yield path,path.read_text(encoding='utf8'),css
            continue
        if 'html' not in surface:
            continue
        filename=Path(surface['html'])
        if filename.name!=str(filename) or filename.suffix!='.html':
            raise ValueError('Expected a static report filename')
        path=tools/filename
        current=path.read_text(encoding='utf-8')
        if current.count('<style>')!=1 or current.count('</style>')!=1:
            raise ValueError(f'Expected one inline style block in {filename}')
        start,rest=current.split('<style>')
        _,end=rest.split('</style>')
        yield path,current,start+'<style>'+css+'</style>'+end


def check(root):
    return [{'code':'report-style-drift','path':path.relative_to(root).as_posix(),'message':'Rebuild the local report stylesheet from its presentation graph.'}
            for path,current,expected in static_projections(root/'tools') if current!=expected]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    for path,current,expected in static_projections(TOOLS):
        if current!=expected:
            if not args.write:
                parser.exit(1,'Stale local report: '+path.name+'\n')
            path.write_text(expected,encoding='utf-8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
