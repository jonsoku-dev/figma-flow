"""Project the portable plugin manifest into the Codex package format."""
import argparse
import json
from pathlib import Path


def projection(manifest):
    extension = manifest['extensions']['com.openai']
    shared = {k: manifest[k] for k in ('name', 'version', 'description')}
    if shared.keys() & extension.keys():
        raise ValueError('Codex extension cannot override shared manifest identity.')
    return {**shared, 'skills': './skills/', **extension}


def check(root):
    root = Path(root)
    manifest = json.loads((root / 'plugin.json').read_bytes())
    actual = json.loads((root / '.codex-plugin/plugin.json').read_bytes())
    if actual == projection(manifest):
        return []
    return [{'code': 'manifest-projection-drift', 'path': '.codex-plugin/plugin.json',
             'message': 'Regenerate Codex metadata from plugin.json with tools/plugin_manifest.py --write.'}]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.write:
        from figma_workspace import atomic
        target = repo / '.codex-plugin/plugin.json'
        # This is a tracked public file, so keep its public mode after replacement.
        mode = target.stat().st_mode & 0o777
        value = projection(json.loads((repo / 'plugin.json').read_bytes()))
        atomic(target, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())
        target.chmod(mode)
    findings = check(repo)
    print(json.dumps(findings, ensure_ascii=False))
    raise SystemExit(bool(findings))
