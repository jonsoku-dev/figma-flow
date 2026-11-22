"""Project the registered Figma window options into standalone scripts and assembled tasks."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('library/figma-profile/native-windows.json')
MARKER = re.compile(r'/\* flow-window ([a-zA-Z0-9]+) \*/\s*\{[^{}]*\}')


def projections(root):
    graph = json.loads((root/SOURCE).read_bytes())
    if graph['schema'] != 'figma-flow-native-window-v1':
        raise ValueError('Unsupported native window contract')
    windows = graph['windows']
    if set(windows) != {name for fields in graph['bindings'].values() for name in fields}:
        raise ValueError('Every native window needs a projecting script')
    for name, options in windows.items():
        if (set(options) - {'width','height','themeColors'} or
                any(type(options.get(k)) is not int or options[k] <= 0 for k in ('width','height')) or
                ('themeColors' in options and type(options['themeColors']) is not bool)):
            raise ValueError(f'Invalid native window options: {name}')
    for source, expected in graph['bindings'].items():
        path = Path(source)
        if path.parent not in (Path('tools'),Path('figma-bridge')) or path.suffix not in ('.py','.js'):
            raise ValueError('Unexpected native window source')
        current = (root/path).read_text(encoding='utf8')
        if Counter(match[1] for match in MARKER.finditer(current)) != expected:
            raise ValueError(f'Native window bindings differ in {source}')
        def render(match):
            options = ', '.join(key+': '+json.dumps(value) for key,value in windows[match[1]].items())
            return '/* flow-window '+match[1]+' */ {'+options+'}'
        yield path,current,MARKER.sub(render,current)


def check(root):
    return [{'code':'native-window-drift','path':path.as_posix(),'message':'Regenerate the graph-owned Figma window options.'}
            for path,source,expected in projections(root) if source!=expected]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    for path,current,expected in projections(ROOT):
        if current==expected:
            continue
        if not args.write:
            parser.exit(1,'Stale native window options in '+path.as_posix()+'\n')
        (ROOT/path).write_text(expected,encoding='utf8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
