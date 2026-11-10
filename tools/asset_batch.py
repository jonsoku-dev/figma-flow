#!/usr/bin/env python3
"""Freeze a game asset role inventory and exact shared image-generation context before production."""
import argparse
import hashlib
import json
from io import BytesIO
import re
from pathlib import Path
from workflow import Event


def _request_packet(batch, batch_hash, context_text, selection, out):
    refs, planned = batch['references'], batch['roles']
    batch_id, game_id = batch['batch_id'], batch['game_id']
    selection_pin = batch['design_selection']
    prompt = (f"Production batch: {batch_id}\nBatch SHA256: {batch_hash}\nGame: {game_id}\n"
              f"Chosen direction: {selection_pin['candidate_id']} ({selection_pin['candidate_sha256']})\n"
              f"Selection SHA256: {selection_pin['selection_sha256']}\nWorkflow graph SHA256: {selection_pin['workflow_graph_sha256']}\n"
              f"APPROVED DIRECTION\nComposition: {selection['candidate']['composition']}\n"
              f"Typography: {selection['candidate']['typography']}\nInteraction: {selection['candidate']['interaction']}\n"
              f"Product graph SHA256: {selection_pin['product_graph_sha256']}\n"
              f"Concept SHA256: {batch['concept']['sha256']}\nLocked reference SHA256: " +
              ', '.join(r['sha256'] for r in refs) + '\n\nEXACT SHARED CONCEPT\n' + context_text +
              '\n\nPLANNED ROLES\n' + json.dumps(planned, ensure_ascii=False) +
              '\n\nGenerate each role from this exact common game context and supplied reference sheets. '
              'Title treatments and button plates contain decorative art only; final visible labels remain real text. '
              'Record exact role/call identity and original raster result. Scoped retries keep this batch/context; '
              'a concept/reference/inventory expansion starts a newly frozen complete batch, with prior work only as references.\n')
    requests = []
    for role in planned:
        role_prompt = prompt + '\nPRODUCE NOW: ' + role['id'] + ' (' + role['kind'] + '). Use the exact shared concept and locked references above. '
        if role['kind'] in ('section_title', 'button_frame'):
            role_prompt += 'Generate clean decorative bitmap skin art suitable for nine-slice corners and stretchable/repeating edges/center. No words or baked labels; actual labels remain live text in content-hug frames. '
        if role['kind'] == 'key_art':
            role_prompt += 'The locked reference sheets include review comps with live UI text, titles and buttons. Reproduce their world, character and palette only; never paint any letters, words, headings, buttons or interface elements into this artwork. '
        if role['kind'] in ('logo', 'icon'):
            role_prompt += 'This mark/icon must be genuinely image-generated original raster artwork, never code/font/library/vector substitutes. '
        references_absolute = [str((out / r['path']).resolve()) for r in refs]
        requests.append({'role_ids': [role['id']], 'tool': 'image_gen.imagegen',
                         'args': {'prompt': role_prompt, **({'referenced_image_paths': references_absolute} if references_absolute else {}),
                                  'transparent_background': role['kind'] != 'key_art'},
                         'evidence_input': {'role_ids': [role['id']], 'prompt': role_prompt, 'batch_id': batch_id,
                             'batch_sha256': batch_hash, 'context_sha256': batch['concept']['sha256'],
                             'context_text': context_text, **selection_pin, 'reference_sha256': [r['sha256'] for r in refs],
                             'referenced_image_paths': references_absolute}})
    return prompt, {'schema': 'figma-flow-generation-requests-v1',
        'workflow_state': batch['workflow_state'], 'host_generation_executed': False, 'requests': requests,
        'execution': 'The Figma Flow agent must invoke each request through the actual image_gen.imagegen host tool before visual authoring, preserve the real result/original and record observed tool identity. This file is a call packet, never generation evidence.'}


def freeze(concept, references, roles, out, *, batch_id, game_id, concept_id, version, profile='game-campaign', selection_path=None):
    from design_directions import current, require_selected, guard_production, read
    selection = require_selected(selection_path)
    selection_pin = {key: selection[key] for key in (
        'selection_sha256', 'candidate_id', 'candidate_sha256', 'workflow_graph_sha256')}
    selection_pin['product_graph_sha256'] = selection['product_graph']['sha256']
    if profile not in ('game-campaign', 'website'):
        raise ValueError('Unknown asset profile')
    if not all(isinstance(value, str) and value.strip() for value in (batch_id, game_id, concept_id, version)):
        raise ValueError('Batch, game, concept and version require stable nonempty identifiers')
    approved_graph = read(selection['product_graph'])
    draft = json.loads(Path(selection['draft_path']).read_text())
    fixed_content = read(draft['content'])
    if (approved_graph.get('game_id') or fixed_content.get('requested_forms')) and profile != 'game-campaign':
        raise ValueError('Selected game/campaign scope cannot use a smaller website role inventory')
    if approved_graph.get('game_id') and approved_graph['game_id'] != game_id:
        raise ValueError('Batch game differs from the selected game')
    concept, out = Path(concept), Path(out)
    if not concept.is_file() or concept.is_symlink():
        raise ValueError('A regular concept file is required')
    planned = []
    for role in roles:
        identity, kind = role.split(':', 1)
        if not re.fullmatch(r'[\w./-]{1,160}', identity) or kind not in ('logo', 'icon', 'character', 'key_art', 'section_title', 'button_frame', 'state_stamp', 'ornament'):
            raise ValueError('Roles use ID:kind with a supported generated production kind')
        planned.append({'id': identity, 'kind': kind})
    if not planned or len({r['id'] for r in planned}) != len(planned) or (profile == 'game-campaign' and not {'logo', 'icon', 'character', 'key_art', 'section_title', 'button_frame'} <= {r['kind'] for r in planned}):
        raise ValueError('Declare the complete unique game role inventory, including titles and button frames')
    raw = concept.read_bytes()
    context_text = raw.decode('utf-8')
    refs_to_read = list(references) + [current(p['file']) for p in selection['candidate']['previews']]
    sheets, seen = [], set()
    for reference in refs_to_read:
        path = Path(reference)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Locked references must be regular image files')
        image = path.read_bytes()
        if not image.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
            raise ValueError('Locked references must be PNG or JPEG files')
        from PIL import Image
        with Image.open(BytesIO(image)) as reference_image:
            reference_image.verify()
        digest = hashlib.sha256(image).hexdigest()
        if digest not in seen:
            seen.add(digest)
            sheets.append((path, image))
    if profile == 'game-campaign' and not sheets:
        raise ValueError('Game production requires locked visual references')
    prospective = {
        'schema': 'figma-flow-asset-batch-v1', 'batch_id': batch_id, 'game_id': game_id,
        'concept': {'id': concept_id, 'version': version, 'path': str(concept.absolute()), 'sha256': hashlib.sha256(raw).hexdigest()},
        'references': [{'path': str(path.absolute()), 'sha256': hashlib.sha256(content).hexdigest()} for path, content in sheets],
        'roles': planned, 'design_selection': selection_pin}
    admission = guard_production(selection_path, event=Event.FREEZE_BATCH, batch=prospective)
    out.mkdir(parents=True, exist_ok=False)
    concept_name = 'concept' + concept.suffix
    (out / concept_name).write_bytes(raw)
    refs = []
    for index, (_, content) in enumerate(sheets, 1):
        suffix = '.png' if content.startswith(b'\x89PNG') else '.jpg'
        name = f'reference-{index:02d}{suffix}'
        (out / name).write_bytes(content)
        refs.append({'path': name, 'sha256': hashlib.sha256(content).hexdigest()})
    batch = {'schema': 'figma-flow-asset-batch-v1', 'batch_id': batch_id, 'game_id': game_id,
             'concept': {'id': concept_id, 'version': version, 'path': concept_name, 'sha256': hashlib.sha256(raw).hexdigest()},
             'references': refs, 'roles': planned, 'design_selection': selection_pin, 'workflow_state': admission['state']}
    encoded = (json.dumps(batch, ensure_ascii=False, indent=2) + '\n').encode()
    (out / 'batch.json').write_bytes(encoded)
    batch_hash = hashlib.sha256(encoded).hexdigest()
    prompt, packet = _request_packet(batch, batch_hash, context_text, selection, out)
    (out / 'shared-prompt.txt').write_text(prompt)
    (out / 'generation-requests.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2)+'\n')
    return {'batch': str((out / 'batch.json').resolve()), 'batch_sha256': batch_hash,
            'shared_prompt': str((out / 'shared-prompt.txt').resolve()), 'generation_requests': str((out / 'generation-requests.json').resolve()), 'status': admission['state'],
            'design_selection': selection_pin, 'workflow_state': admission['state'],
            'production_rule': 'Use a single planned batch; independent role calls may overlap and scoped retries preserve exact context. No wall-clock simultaneity claim.'}


def release_requests(selection_path, batch_path, requests_path):
    from design_directions import current, guard_production, pin
    batch_path, requests_path = Path(batch_path).absolute(), Path(requests_path).absolute()
    admission = guard_production(selection_path, event=Event.GENERATE, batch_path=batch_path)
    if requests_path != batch_path.parent / 'generation-requests.json' or requests_path.is_symlink():
        raise ValueError('Host requests must be the actual file next to the current frozen batch')
    batch = json.loads(batch_path.read_bytes())
    for record in [batch['concept'], *batch['references']]:
        rel = Path(record['path'])
        if rel.is_absolute() or len(rel.parts) != 1 or rel.name in {'.', '..'}:
            raise ValueError('Host requests require frozen inputs inside the batch directory')
    context_text = current(batch['concept'], batch_path.parent).read_text()
    _, expected = _request_packet(batch, pin(batch_path)['sha256'], context_text, admission, batch_path.parent)
    if json.loads(requests_path.read_bytes()) != expected:
        raise ValueError('Cached host requests differ from the verified direction, roles or shared prompt')
    return {**admission, 'requests': expected['requests'], 'executed': ['verify-current-selection-and-host-packet'],
            'pending': 'Host image-generation calls and their actual returned originals are still required.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection', type=Path, help='Verified human choice receipt for current candidate bytes')
    p.add_argument('--concept', type=Path, required=True)
    p.add_argument('--reference', type=Path, action='append', default=[])
    p.add_argument('--profile', choices=('game-campaign', 'website'), default='game-campaign')
    p.add_argument('--role', action='append', required=True, help='ID:kind; include the complete planned role inventory')
    for field in ('batch-id', 'game-id', 'concept-id', 'version'):
        p.add_argument('--' + field, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(freeze(a.concept, a.reference, a.role, a.out, batch_id=a.batch_id, game_id=a.game_id,
                               concept_id=a.concept_id, version=a.version, profile=a.profile, selection_path=a.selection), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
