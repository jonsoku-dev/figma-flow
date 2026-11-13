#!/usr/bin/env python3
"""Create a private, network-disabled Figma Design API fixture plugin project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SOURCE = ROOT / 'figma-bridge' / 'native_api_fixture.js'
PLUGIN_ID = re.compile(r'\d{10,22}\Z')
FILE_KEY = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


def _write_private_new(path, content):
    path = Path(path).expanduser().absolute()
    if any(parent.is_symlink() for parent in [path, *path.parents]):
        raise ValueError('Output path must not contain symlinks.')
    if path.exists() or not path.parent.is_dir():
        raise ValueError('Output must be a new path with an existing parent.')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(fd, 0o600)
        stream.write(content.encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())


def generate(plugin_id, file_key):
    if not isinstance(plugin_id, str) or not PLUGIN_ID.fullmatch(plugin_id):
        raise ValueError('A Figma-issued numeric plugin ID is required.')
    if not isinstance(file_key, str) or not FILE_KEY.fullmatch(file_key):
        raise ValueError('A Figma file key is required.')
    helper = FIXTURE_SOURCE.read_text(encoding='utf-8')
    code = helper + '\n' + f"""
const NATIVE_API_LAB_FILE_KEY = {json.dumps(file_key)};

async function nativeApiLabMain() {{
  if (figma.command === 'native-api-lab-fixtures') {{
    const result = await createNativeApiLabFixtures(figma, NATIVE_API_LAB_FILE_KEY);
    showNativeApiLabReceipt(figma, result);
  }} else if (figma.command === 'native-api-lab-owned-reads') {{
    const result = await runNativeApiLabOwnedReads(figma, NATIVE_API_LAB_FILE_KEY);
    showNativeApiLabReceipt(figma, result);
  }} else if (figma.command === 'native-api-lab-owned-writes') {{
    const result = await runNativeApiLabOwnedWrites(figma, NATIVE_API_LAB_FILE_KEY);
    showNativeApiLabReceipt(figma, result);
  }} else {{
    figma.closePlugin('Choose a Figma Flow API lab menu command.');
  }}
}}

nativeApiLabMain().catch(error => showNativeApiLabReceipt(figma, {{
  schema: 'figma-flow-native-api-lab-error-v1', status: 'error', message: String(error),
}}));
"""
    manifest = {
        'name': 'Figma Flow API Probe Lab',
        'id': plugin_id,
        'api': '1.0.0',
        'main': 'code.js',
        'capabilities': [],
        'enableProposedApi': False,
        'enablePrivatePluginApi': True,
        'documentAccess': 'dynamic-page',
        'editorType': ['figma'],
        'networkAccess': {'allowedDomains': ['none']},
        'menu': [
            {'name': 'API probe · create owned fixtures', 'command': 'native-api-lab-fixtures'},
            {'name': 'API probe · read owned component links', 'command': 'native-api-lab-owned-reads'},
            {'name': 'API probe · reversible owned calls', 'command': 'native-api-lab-owned-writes'},
        ],
    }
    return code, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-id', required=True, help='Figma-issued private plugin ID')
    parser.add_argument('--file-key', required=True, help='Exact Figma file key admitted for this private lab')
    parser.add_argument('--out', type=Path, required=True, help='New private project directory under .figma-flow')
    args = parser.parse_args(argv)
    try:
        output = args.out.expanduser().absolute()
        private_root = (ROOT / '.figma-flow').resolve()
        if private_root not in output.parents:
            raise ValueError('Output must be inside the private .figma-flow workspace.')
        code, manifest = generate(args.plugin_id, args.file_key)
        output.mkdir(mode=0o700)
        _write_private_new(output / 'code.js', code)
        _write_private_new(output / 'manifest.json', manifest)
        print(json.dumps({'project': str(output), 'code_sha256': hashlib.sha256(code.encode()).hexdigest(),
                          'manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest(),
                          'network_domains': 0, 'editor_types': ['figma']}))
        return 0
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f'native-api-fixture-project: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
