"""Name the offline panel artifacts consumed by the product and verifier."""
import json
from pathlib import Path
import re


ASSET_DIR = Path('figma-bridge/assets')
CONTRACT_PATH = Path('tools/maintenance-contract.json')
OUTPUT_SUFFIXES = {'script': 'js', 'shellStyle': 'css', 'licenses': 'txt'}


def artifact_paths(contract):
    names = contract.get('panelArtifacts')
    if not isinstance(names, dict) or set(names) != set(OUTPUT_SUFFIXES):
        raise ValueError('Declare the script, shell stylesheet and licenses roles in the panel artifact contract.')
    for role, suffix in OUTPUT_SUFFIXES.items():
        name = names[role]
        if not isinstance(name, str) or not re.fullmatch(rf'[A-Za-z0-9][A-Za-z0-9_.-]*\.{suffix}', name):
            raise ValueError(f'Invalid panel artifact filename for {role}: {name!r}')
    files = {role: ASSET_DIR / name for role, name in names.items()}
    files['bundleStyle'] = files['script'].with_suffix('.css')
    files['legalComments'] = ASSET_DIR / (names['script'] + '.LEGAL.txt')
    if len(set(files.values())) != len(files):
        raise ValueError('Each panel artifact role requires a distinct filename.')
    return files


def read_panel_artifact(root, role):
    contract = json.loads((root / CONTRACT_PATH).read_bytes())
    return (root / artifact_paths(contract)[role]).read_text(encoding='utf-8')
