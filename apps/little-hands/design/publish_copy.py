"""Project the signed booking template from its authored source and shared product copy."""
import argparse
from html import escape
import json
import os
import tempfile
from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1]
COPY_FIELD = re.compile(r'\{\{copy\.([a-zA-Z][a-zA-Z0-9]*)\}\}')


def projection(app=APP):
    product = json.loads((app/'booking/product.json').read_bytes())
    template = (app/'design/session-detail.html.in').read_text(encoding='utf8')
    def literal(match):
        text = escape(product[match[1]], quote=True)
        return text.replace('{', '&#123;').replace('}', '&#125;')
    return COPY_FIELD.sub(literal,template)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    target=APP/'templates/booking/session_detail.html'
    expected=projection()
    if target.exists() and target.read_bytes()==expected.encode('utf8'):
        return 0
    if not args.write:
        parser.exit(1,'The signed booking template differs from its public copy. Regenerate before task preparation.\n')
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
        temporary=Path(output.name)
    try:
        temporary.write_text(expected,encoding='utf8')
        temporary.chmod(0o644)
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
