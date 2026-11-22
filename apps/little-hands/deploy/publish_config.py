"""Project the app's deployment contract into the native container and PostgreSQL formats."""
import argparse
import json
from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1]
FILES = ('Dockerfile','compose.yaml','deploy/nginx.conf.example','deploy/roles.sql','deploy/grants.sql','deploy/verify.sql')
FIELD = re.compile(r'\{\{cfg\.([A-Za-z]+)\.([A-Za-z]+)\}\}')


def outputs(app):
    settings = json.loads((app/'config/deployment.json').read_bytes())
    for port in (settings['web']['internalPort'],settings['web']['hostPort'],settings['database']['port'],settings['database']['developmentPort']):
        if type(port) is not int or not 0 < port < 65536:
            raise ValueError('Expected a TCP port number')
    for role in ('name','owner','runtime'):
        if not re.fullmatch(r'[a-z][a-z0-9_]*',settings['database'][role]):
            raise ValueError('Expected a lower-case PostgreSQL identifier')
    if settings['database']['owner']==settings['database']['runtime']:
        raise ValueError('Owner and application roles must differ')
    for image in (settings['web']['pythonImage'],settings['database']['image']):
        if not re.fullmatch(r'[a-z0-9./:-]+@sha256:[0-9a-f]{64}',image):
            raise ValueError('Deployment images must be digest pinned')
    for path in FILES:
        template = app/'deploy/templates'/(Path(path).name+'.in')
        text = FIELD.sub(lambda m:str(settings[m[1]][m[2]]),template.read_text(encoding='utf-8'))
        if '{{cfg.' in text:
            raise ValueError(f'Unknown configuration field in {template.name}')
        yield app/path,text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    for path,text in outputs(APP):
        if path.exists() and path.read_bytes()==text.encode('utf8'):
            continue
        if not args.write:
            parser.exit(1, f'Stale deployment configuration: {path.name}\n')
        path.write_text(text,encoding='utf-8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
