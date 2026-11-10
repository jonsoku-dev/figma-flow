#!/usr/bin/env python3
"""Validate supplied creative evidence and current bytes; never attest tool execution or taste."""
import argparse
import base64
import hashlib
import json
import math
from io import BytesIO
from pathlib import Path
import re
import struct
import zlib
import workflow
from workflow import State
import skill_dependencies

OPERATIONS = {'create', 'redesign', 'refine'}
SKILLS = {'impeccable', 'design-taste-frontend'}


def verify_derivative(original, derivative, operations):
    def need(value, message):
        if not value:
            raise ValueError(message)
    need(isinstance(operations, list), 'explicit derivative operation list required')
    if operations:
        try:
            from PIL import Image
        except ImportError:
            raise ValueError('Pillow is required to verify transformed raster derivatives; byte-identical originals need no dependency')
        expected = Image.open(BytesIO(original))
        for operation in operations:
            need(isinstance(operation, dict), 'crop/resize/convert/format operation records required')
            op = operation.get('op')
            if op == 'crop':
                box = operation.get('box')
                need(isinstance(box, list) and len(box) == 4 and all(type(v) is int for v in box) and
                     0 <= box[0] < box[2] <= expected.width and 0 <= box[1] < box[3] <= expected.height,
                     'crop must use actual source extents [left,top,right,bottom]')
                expected = expected.crop(box)
            elif op == 'resize':
                size = operation.get('size')
                need(isinstance(size, list) and len(size) == 2 and all(type(v) is int and v > 0 for v in size) and
                     operation.get('resample') == 'LANCZOS', 'resize needs positive native output size and LANCZOS')
                expected = expected.resize(size, Image.Resampling.LANCZOS)
            elif op == 'convert':
                need(operation.get('mode') in ('RGB', 'RGBA', 'L', 'LA'), 'unsupported derivative color conversion')
                expected = expected.convert(operation['mode'])
            elif op == 'format':
                need(operation.get('format') in ('PNG', 'JPEG'), 'unsupported raster export format')
                options = operation.get('options', {})
                need(isinstance(options, dict) and set(options) <= {'quality', 'subsampling', 'optimize', 'progressive', 'compress_level'}, 'unsupported raster encoder options')
                encoded = BytesIO()
                expected.save(encoded, format=operation['format'], **options)
                expected = Image.open(BytesIO(encoded.getvalue()))
                expected.load()
            else:
                raise ValueError('creative/redrawn/traced derivative operation forbidden')
        observed = Image.open(BytesIO(derivative))
        need(expected.size == observed.size and expected.convert('RGBA').tobytes() == observed.convert('RGBA').tobytes(),
             'derivative pixels/dimensions differ from replayed generated-original transforms')
    else:
        need(derivative == original, 'changed derivative requires replayable raster-only crop/resize/convert/format operations')


def frontend(data, bindings):
    ui_suffixes = {'.html', '.css', '.jsx', '.tsx', '.vue', '.svelte'}
    implementation = bindings.get('authorities', {}).get('implementation', '')
    return (data.get('requires_figma') is True or Path(implementation).suffix.lower() in ui_suffixes or
            (Path(implementation).suffix.lower() in ('.js', '.mjs') and any(n.get('type') == 'screen' for n in data.get('nodes', []) if isinstance(n, dict))) or 'native_handoff' in bindings or
            any(n.get('type') == 'figma' or n.get('type') == 'code' and
                Path(n.get('source', '')).suffix.lower() in ui_suffixes
                for n in data.get('nodes', []) if isinstance(n, dict)))


def generated_artifact_root():
    return Path.home() / '.codex/generated_images'


def resolve_skill(identity):
    return skill_dependencies.resolve_skill(identity)


def evaluate(base, declaration, *, request_text='', required=False, expected_paths=(), native_required=False, selection_path=None, inspection=False):
    bindings_base = Path(base).resolve()
    base = bindings_base
    if isinstance(declaration, dict) and declaration.get("project_root"):
        base = (bindings_base / declaration["project_root"]).resolve()
        if not base.is_dir() or not bindings_base.is_relative_to(base):
            return {"schema": "figma-flow-design-review-v1", "status": "blocked", "passed": False, "errors": ["explicit project_root must contain the bindings directory"], "pinned_files": {}}
    report = {'schema': 'figma-flow-design-review-v1', 'status': 'blocked', 'passed': False,
              'workflow_graph_sha256': workflow.graph_hash(), 'workflow_state': None, 'workflow_symbol': None, 'required_boundary': State.WAIT_SELECTION.name, 'production_admitted': False, 'errors': [], 'project_root': str(base), 'pinned_files': {}, 'asset_inventory': [],
              'evidence_boundary': 'Checks supplied evidence structure and current byte bindings. Skill hashes do not prove instructions were followed; tool capture is not authenticated platform execution; creative quality and visible use require the recorded actual visual review.'}
    errors, pins = report['errors'], report['pinned_files']

    def need(value, message):
        if not value:
            raise ValueError(message)

    def text(value, name):
        need(isinstance(value, str) and len(value.strip()) >= 1 and value.casefold().strip() not in
             {'looks good', 'all good', 'pass', 'checked', 'done', 'reviewed', 'no issues found', 'all checks passed', 'looks good overall', '문제 없음', '확인 완료'}, name + ' needs a concrete observation/decision')
        need(not value.strip().casefold().startswith(('pending', 'todo', 'tbd', 'placeholder', 'not observed', '미검증', '작성 필요')), name + ' remains unobserved')
        return value

    def pin(item, *, external=False, at=None):
        need(isinstance(item, dict) and isinstance(item.get('path'), str), 'file path/hash record required')
        path = Path(item['path'])
        path = path if path.is_absolute() else (at or base) / path
        need(not path.is_symlink() and path.is_file(), 'regular evidence file required: ' + str(path))
        path = path.resolve()
        need(external or path.is_relative_to(base), 'project evidence must stay inside project: ' + str(path))
        need(path.stat().st_size <= 64_000_000, 'evidence file exceeds bounded 64MB input')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        need(item.get('sha256') == digest, 'current byte hash mismatch: ' + str(path))
        pins[str(path)] = digest
        return path, raw

    def raster(item, *, at=None):
        path, raw = pin(item, at=at)
        need(path.suffix.lower() in {'.png', '.jpg', '.jpeg'}, 'actual raster required; SVG/markup/font files are not image generation')
        if raw.startswith(b'\x89PNG\r\n\x1a\n'):
            offset, compressed, dimensions = 8, b'', None
            while offset + 12 <= len(raw):
                size = struct.unpack('>I', raw[offset:offset + 4])[0]
                kind, payload = raw[offset + 4:offset + 8], raw[offset + 8:offset + 8 + size]
                need(offset + 12 + size <= len(raw), 'truncated PNG: ' + str(path))
                crc = struct.unpack('>I', raw[offset + 8 + size:offset + 12 + size])[0]
                need(zlib.crc32(kind + payload) & 0xffffffff == crc, 'invalid PNG chunk: ' + str(path))
                if kind == b'IHDR':
                    need(len(payload) == 13, 'invalid PNG header')
                    width, height, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', payload)
                    need(depth == 8 and color in (0, 2, 4, 6) and interlace == 0 and width * height <= 50_000_000, 'unsupported/oversized evidence PNG format')
                    dimensions = (width, height)
                    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
                if kind == b'IDAT':
                    compressed += payload
                offset += size + 12
                if kind == b'IEND':
                    break
            need(dimensions and min(dimensions) > 0 and compressed, 'invalid PNG image')
            stride = dimensions[0] * channels + 1
            decoded = zlib.decompressobj().decompress(compressed, stride * dimensions[1] + 1)
            need(len(decoded) == stride * dimensions[1] and all(decoded[row * stride] <= 4 for row in range(dimensions[1])), 'invalid PNG scanline image payload')
            return path, raw, dimensions
        need(raw.startswith(b'\xff\xd8') and raw.endswith(b'\xff\xd9'), 'invalid raster image')
        offset = 2
        while offset + 4 < len(raw):
            if raw[offset] != 255:
                offset += 1
                continue
            marker = raw[offset + 1]
            size = int.from_bytes(raw[offset + 2:offset + 4], 'big')
            if marker in (192, 193, 194):
                try:
                    from PIL import Image
                    Image.open(BytesIO(raw)).verify()
                except ImportError:
                    raise ValueError('Pillow required for JPEG evidence validation')
                return path, raw, (int.from_bytes(raw[offset + 7:offset + 9], 'big'), int.from_bytes(raw[offset + 5:offset + 7], 'big'))
            offset += max(size + 2, 2)
        raise ValueError('JPEG dimensions unavailable')

    try:
        skill_dependencies.verify_bundle()
        if not inspection:
            import design_directions
            selected = design_directions.require_selected(selection_path)
            report.update(workflow_state=State.SELECTED.value, workflow_symbol=State.SELECTED.name, production_admitted=True, direction_selection=selected)
        else:
            selected = None
            report['scope'] = 'inspection-not-production'
        need(isinstance(declaration, dict), 'frontend UI creation requires bindings.design_review')
        need(declaration.get('operation') in OPERATIONS, 'design_review.operation must be create, redesign or refine')
        need(declaration.get('target_kind') in ('website', 'product-ui', 'game-campaign'), 'design_review.target_kind required')
        receipt_path = declaration.get('receipt')
        need(isinstance(receipt_path, str), 'design_review.receipt required')
        path = bindings_base / receipt_path
        need(path.resolve().is_relative_to(base) and path.is_file() and not path.is_symlink(), 'design review receipt missing/outside selected project')
        raw = path.read_bytes()
        pins[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
        receipt = json.loads(raw)
        need(receipt.get('schema') == report['schema'], 'versioned design-review evidence required')
        artifacts = receipt.get('artifacts')
        need(isinstance(artifacts, list) and artifacts, 'current visual artifacts required')
        artifact_hashes, corpus = {}, request_text
        for artifact in artifacts:
            artifact_path, content = pin(artifact)
            artifact_hashes[artifact['path']] = artifact['sha256']
            if artifact_path.suffix.lower() in ('.html', '.css', '.js', '.jsx', '.ts', '.tsx', '.json', '.md'):
                corpus += '\n' + content.decode('utf-8', errors='replace')
        report['artifact_hashes'] = artifact_hashes
        actual_artifacts = {(base / name).resolve() for name in artifact_hashes}
        need(all(Path(path).resolve() in actual_artifacts for path in expected_paths if Path(path).is_file()), 'review must cover the selected current implementation/native readback artifacts')
        required_skills = set(SKILLS)
        skills = receipt.get('skills')
        need(isinstance(skills, list) and {s.get('id') for s in skills if isinstance(s, dict)} >= required_skills, 'actual Impeccable and design-taste-frontend source records required')
        identities = [s.get('id') for s in skills if isinstance(s, dict)]
        need(len(identities) == len(skills) and len(identities) == len(set(identities)), 'skill records must have unique known ids')
        for skill in skills:
            identity = skill['id']
            need(identity in ('impeccable', 'design-taste-frontend', 'unslop'), 'unknown managed skill id: ' + str(identity))
            managed = skill_dependencies.source_record(identity)
            need(skill.get('source_scope') == 'plugin' and skill.get('source') == managed['source'], 'skill evidence must reference the canonical plugin-managed source')
            need(skill.get('sha256') == managed['sha256'], 'managed skill source hash mismatch: ' + identity)
            source = skill_dependencies.resolve_skill(identity)
            pins[str(source)] = managed['sha256']
            if identity == 'unslop':
                continue
            need(identity in required_skills, 'unexpected managed skill id: ' + identity)
            application = skill.get('application', {})
            need(application.get('target') in artifact_hashes, 'skill application must name a current target artifact')
            text(application.get('decision'), 'skill application')
            need(set(application.get('phases', [])) >= {'before-authoring', 'after-critique'}, 'record required source application before authoring and after critique')
            if declaration['target_kind'] == 'product-ui' and identity == 'design-taste-frontend':
                need(skill.get('scope') == 'limited-to-applicable-surfaces', 'tasteskill excludes dense product UI; record bounded applicability')
        fonts = receipt.get('font_selection', {})
        need(fonts.get('sequence') == 1 and receipt.get('authoring', {}).get('sequence') == 2, 'font selection/specimen must precede authoring in recorded production sequence')
        sample = text(fonts.get('sample_text'), 'target-script typography specimen')
        if re.search('[가-힣]', corpus):
            need(re.search('[가-힣]', sample), 'Korean target requires actual Korean typography specimen text')
        if re.search('[ぁ-ヿ]', corpus):
            need(re.search('[ぁ-ヿ]', sample), 'Japanese target requires actual Japanese typography specimen text')
        candidates, chosen = fonts.get('candidates'), fonts.get('chosen')
        need(isinstance(candidates, list) and len({c.get('family') for c in candidates}) >= 2, 'compare at least two actual target-script font candidates')
        families = {c.get('family') for c in candidates}
        need(None not in families and isinstance(chosen, list) and chosen, 'chosen font roles required')
        for choice in chosen:
            need(choice.get('family') in families and choice.get('role'), 'chosen family must come from compared candidates')
            text(choice.get('reason'), 'font role choice')
        pin(fonts.get('decision'))

        def captures(items, *, final=False):
            need(isinstance(items, list) and {c.get('viewport') for c in items} >= {'desktop', 'mobile'}, 'desktop and mobile observed captures required')
            if final:
                need({c.get('viewport') for c in items if c.get('state') != 'responsive-probe'} >= {'desktop', 'mobile'}, 'actual desktop/mobile product captures required separately from resize probes')
            for capture in items:
                path, raw, dimensions = raster(capture)
                width, height = dimensions
                need((width, height) == (capture.get('width'), capture.get('height')), 'capture dimensions differ from raster')
                need(width >= 1000 if capture['viewport'] == 'desktop' else 240 <= width <= 600, 'capture viewport is not desktop/mobile specimen')
                need(capture.get('tool') in (('stagehand', 'cua', 'figma-native-export', 'static-render', 'manual-user-capture') if inspection else ('figma-native-export', 'static-render', 'manual-user-capture')) and capture.get('target') and capture.get('observed_at'), 'actual capture tool/target/time required')
                if final:
                    need(capture.get('artifact_hashes') == artifact_hashes, 'final capture must pin every current visual artifact')
                else:
                    need(capture.get('text') == sample, 'font specimen must use actual target-script sample')
                    observed = capture.get('fonts', [])
                    need({f.get('family') for f in observed if f.get('loaded') is True} >= families, 'both candidate fonts must actually load in each specimen')
            return items

        specimens = captures(fonts.get('specimens'))
        critique = receipt.get('critique', {})
        need(critique.get('sequence') == 3 and critique.get('reviewer'), 'post-authoring concrete creative critique required')
        confirmation = critique.get('confirmation', {})
        need(confirmation.get('sequence') == 4, 'confirmation after critique/fixes required')
        finals = captures(confirmation.get('captures'), final=True)
        findings = critique.get('findings')
        need(isinstance(findings, list), 'concrete creative findings or substantiated clean checks required')
        clean_required = {'typography', 'composition', 'desktop', 'mobile', 'click_area'}
        if declaration['target_kind'] == 'game-campaign':
            clean_required.update(('focal_crop', 'heading_treatment', 'control_treatment'))
        checks = critique.get('checks', [])
        if not findings or declaration['target_kind'] == 'game-campaign':
            need(isinstance(checks, list) and {c.get('criterion') for c in checks} >= clean_required,
                 'clean critique requires concrete desktop/mobile/type/composition/click-area criteria; games also focal crop/title/control treatments')
            for check in checks:
                need(check.get('target') in artifact_hashes and check.get('status') == 'pass' and check.get('capture') in {c['path'] for c in finals if c.get('state') != 'responsive-probe'}, 'clean check must bind a current target and observed final capture')
                locator = check.get('locator')
                text(check.get('observation'), 'visual criterion observation')
                _, target_content = pin({'path': check['target'], 'sha256': artifact_hashes[check['target']]})
                need(isinstance(locator, str) and locator.strip() and locator in check['observation'] and locator.lstrip('#.').encode() in target_content,
                     'clean critique must name the actual source-resolved element/node')
                need(check.get('observed_value') is not None, 'clean visual criterion needs an actual observed value, not a bare pass')
        if findings:
            dimensions = {f.get('dimension') for f in findings}
            need('typography' in dimensions and bool(dimensions & {'composition', 'hierarchy', 'layout'}), 'fix critique must cover typography and composition/hierarchy/layout')
        final_hashes = {c['sha256'] for c in finals}
        for finding in findings:
            need(finding.get('target') in artifact_hashes and finding.get('status') == 'fixed', 'critique must identify a current target and checked fix')
            text(finding.get('observation'), 'critique observation')
            text(finding.get('fix'), 'critique fix')
            locator = finding.get('locator')
            need(isinstance(locator, str) and locator.strip(), 'critique must identify an actual element/node locator')
            _, target_content = pin({'path': finding['target'], 'sha256': artifact_hashes[finding['target']]})
            need(locator.lstrip('#.').encode() in target_content and locator in finding['observation'], 'generic critique has no source-resolved target observation')
            need(finding.get('before_value') is not None and finding.get('after_value') is not None and finding['before_value'] != finding['after_value'], 'record the concrete observed typography/composition change')
            _, before, _ = raster(finding.get('before'))
            _, after, _ = raster(finding.get('after'))
            need(before != after and finding['after']['sha256'] in final_hashes, 'critique fix needs distinct before and final confirmation raster')

        required_kinds = set()
        if re.search(r'\b(?:logo|wordmark)\b|로고|워드마크', corpus, re.I):
            required_kinds.add('logo')
        if re.search(r'\bicons?(?:ography)?\b|아이콘', corpus, re.I):
            required_kinds.add('icon')
        game = declaration['target_kind'] == 'game-campaign'
        if game:
            required_kinds.update(('logo', 'icon', 'character', 'key_art', 'section_title', 'button_frame'))
            if re.search(r'state.stamp|상태.?인장|별도.?장식|추가.?장식|ornament', request_text, re.I):
                required_kinds.add('state_stamp' if re.search(r'state.stamp|상태.?인장', request_text, re.I) else 'ornament')
        need(not re.search(r'<svg\b[^>]*(?:logo|icon|aria-hidden)|lucide|fontawesome|@phosphor|@tabler/icons|iconify|<(?:span|i)\b[^>]*(?:class|id)=[^>]*(?:logo|wordmark|icon)[^>]*>[^<\s][^<]*</', corpus, re.I), 'hand-coded/library/font icon or logo substitute detected in current visual source')
        assets = receipt.get('assets', [])
        need(isinstance(assets, list), 'asset inventory required')
        if required_kinds or assets:
            batch_path, batch_raw = pin(receipt.get('asset_batch'))
            batch = json.loads(batch_raw)
            if selected is not None:
                admitted = batch.get('design_selection', {})
                need(admitted.get('selection_sha256') == selected['selection_sha256'] and admitted.get('candidate_sha256') == selected['candidate_sha256'], 'production batch predates or lacks the exact admitted human choice')
            batch_base = (base / receipt['asset_batch']['path_base']).resolve() if receipt['asset_batch'].get('path_base') else batch_path.parent
            report['asset_batch_path_base'] = str(batch_base)
            if game:
                need(isinstance(declaration.get('game_id'), str) and declaration['game_id'] == batch.get('game_id'), 'selected game identity must match frozen asset production batch')
            need(batch.get('schema') == 'figma-flow-asset-batch-v1' and batch.get('batch_id') and batch.get('game_id'), 'frozen asset production batch required')
            concept = batch.get('concept', {})
            need(concept.get('id') and concept.get('version'), 'versioned common game concept required')
            _, concept_raw = pin(concept, at=batch_base)
            references = batch.get('references')
            need(isinstance(references, list) and (references or not game), 'games require locked common reference sheets')
            for reference in references:
                raster(reference, at=batch_base)
            roles = batch.get('roles')
            need(isinstance(roles, list) and roles and len({r.get('id') for r in roles}) == len(roles), 'complete unique planned asset role inventory required')
            by_role = {r['id']: r for r in roles}
            need(required_kinds <= {r.get('kind') for r in roles}, 'required logo/icon/game roles absent from frozen batch')
            need({a.get('role_id') for a in assets} == set(by_role), 'every planned asset role must be generated and visibly used')
            capture_paths = {c['path'] for c in finals if c.get('state') != 'responsive-probe'}
            screenshot_hashes = {c['sha256'] for c in [*specimens, *finals]}
            for asset in assets:
                need(asset.get('batch_id') == batch['batch_id'], 'cross-game/mixed asset production batch')
                original_path, original, _ = raster(asset.get('source'))
                need(asset['source']['sha256'] not in screenshot_hashes and not re.search(r'screenshot|specimen|capture', original_path.name, re.I), 'screenshots are not generated original assets')
                generation = asset.get('generation', {})
                need(generation.get('tool') == 'image_gen.imagegen' and generation.get('tool_call_id'), 'genuine image generation result identity required')
                _, event_raw = pin(generation.get('evidence'))
                event = json.loads(event_raw)
                need(event.get('tool') == generation['tool'] and event.get('tool_call_id') == generation['tool_call_id'], 'generation tool-result identity mismatch')
                call, result = event.get('input', {}), event.get('output', {})
                need(isinstance(call.get('role_ids'), list) and asset['role_id'] in call['role_ids'] and set(call['role_ids']) <= set(by_role), 'generation call must identify its actual planned production roles')
                text(call.get('prompt'), 'actual generation prompt')
                need(call.get('batch_id') == batch['batch_id'] and call.get('batch_sha256') == receipt['asset_batch']['sha256'] and
                     call.get('context_sha256') == concept['sha256'] and call.get('reference_sha256') == [r['sha256'] for r in references], 'generation call must carry exact frozen batch/context/reference hashes')
                need(call.get('context_text') == concept_raw.decode('utf-8') and call['context_text'] in call['prompt'], 'actual generation call must include the frozen full concept context')
                supplied_refs = call.get('referenced_image_paths')
                need(isinstance(supplied_refs, list) and len(supplied_refs) == len(references), 'generation call must supply every locked reference image')
                for supplied, reference in zip(supplied_refs, references):
                    supplied_path = Path(supplied) if Path(supplied).is_absolute() else batch_base / supplied
                    need(supplied_path.is_file() and hashlib.sha256(supplied_path.read_bytes()).hexdigest() == reference['sha256'], 'generation call reference raster differs from frozen sheet')
                need(concept['sha256'] in call['prompt'] and all(r['sha256'] in call['prompt'] for r in references), 'shared context/reference pins must be present in actual generation prompt')
                need(result.get('mime_type') in ('image/png', 'image/jpeg') and result.get('sha256') == asset['source']['sha256'], 'recorded generation raster output mismatch')
                output_path = result.get('image_path')
                need(isinstance(output_path, str), 'actual platform tool output path required')
                generation_base = (base / generation.get('path_base', '.')).resolve()
                need(generation_base.is_relative_to(base), 'generation relative path base must stay in selected project')
                output_path = Path(output_path) if Path(output_path).is_absolute() else generation_base / output_path
                need(output_path.is_file() and output_path.read_bytes() == original, 'original must match recorded tool-result raster bytes')
                managed_path = event.get('result', {}).get('generated_image_path', str(output_path))
                managed_path = Path(managed_path)
                need(managed_path.is_absolute() and managed_path.resolve().is_relative_to(generated_artifact_root().resolve()) and
                     managed_path.stem == generation['tool_call_id'] and managed_path.is_file() and not managed_path.is_symlink(),
                     'known engine-generated original artifact and actual result identity required; a self-written asset manifest is insufficient')
                need(managed_path.read_bytes() == original, 'managed imagegen original differs from source/export bytes')
                pins[str(managed_path.resolve())] = asset['source']['sha256']
                pins[str(output_path.resolve())] = asset['source']['sha256']
                if result.get('image_base64'):
                    need(base64.b64decode(result['image_base64'], validate=True) == original, 'recorded tool payload differs from original')
                _, derivative, _ = raster(asset.get('derivative'))
                verify_derivative(original, derivative, asset['derivative'].get('operations', []))
                usages = asset.get('usage')
                need(isinstance(usages, list) and usages, 'unused generated asset declaration')
                for usage in usages:
                    need(usage.get('target') in artifact_hashes and usage.get('locator') and usage.get('visible') is True and
                         usage.get('capture') in capture_paths and usage.get('source_sha256') == asset['derivative']['sha256'], 'final visible usage must connect role, current target, derivative bytes and final capture')
                    _, target_raw = pin({'path': usage['target'], 'sha256': artifact_hashes[usage['target']]})
                    direct = Path(asset['derivative']['path']).name.encode() in target_raw
                    manifest_record = usage.get('manifest')
                    if manifest_record is not None:
                        manifest_path, manifest_raw = pin(manifest_record)
                        need(manifest_record['path'] in artifact_hashes and artifact_hashes[manifest_record['path']] == manifest_record['sha256'], 'usage manifest must be a pinned current visual artifact')
                        manifest_data = json.loads(manifest_raw)
                        role_records = manifest_data.get('roles', manifest_data.get('assets', []))
                        direct = any(item.get('id', item.get('role_id')) == asset['role_id'] and item.get('sha256') == asset['derivative']['sha256'] and
                                     Path(item.get('path', '')).name == Path(asset['derivative']['path']).name for item in role_records) and (
                                     asset['role_id'].encode() in target_raw or manifest_path.name.encode() in target_raw)
                    need(direct, 'asset not connected to actual target via direct reference or pinned role manifest')
                    need(usage['locator'].lstrip('#.').encode() in target_raw, 'visible asset locator absent from current target')
                    bounds = usage.get('bounds')
                    capture = next(c for c in finals if c['path'] == usage['capture'])
                    need(isinstance(bounds, list) and len(bounds) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bounds) and
                         min(bounds[:2]) >= 0 and min(bounds[2:]) > 0 and bounds[0] + bounds[2] <= capture['width'] and bounds[1] + bounds[3] <= capture['height'],
                         'visible usage needs actual positive bounds inside the cited state capture')
                    text(usage.get('semantic_role'), 'actual action/section asset purpose')
                    text(usage.get('purpose'), 'actual action/section asset purpose')
                    text(usage.get('observation'), 'visible generated role observation')
                    need(asset['role_id'] in usage['observation'], 'usage observation must identify the actual generated role')
                    if by_role[asset['role_id']]['kind'] in ('section_title', 'button_frame'):
                        need(usage.get('text_mode') == 'live-text' and isinstance(usage.get('label_text'), str) and usage['label_text'].strip() and
                             usage['label_text'].encode() in target_raw, 'title/button generated plate must retain actual live text label in target')
                semantic_roles = {usage['semantic_role'] for usage in usages}
                if by_role[asset['role_id']]['kind'] == 'button_frame' and len(semantic_roles) > 1:
                    decision = next((d for d in receipt.get('asset_role_decisions', []) if d.get('role_id') == asset['role_id']), None)
                    need(isinstance(decision, dict) and set(decision.get('semantic_roles', [])) == semantic_roles and decision.get('review_capture') in capture_paths, 'distinct action roles sharing a frame require an explicit reviewed reuse decision, never a blanket button skin')
                    text(decision.get('rationale'), 'purpose-aware reuse rationale')
                    need(asset['role_id'] in text(decision.get('observation'), 'purpose-aware reuse observation'), 'reuse observation must identify the actual frame')
                report['asset_inventory'].append({'role_id': asset['role_id'], 'kind': by_role[asset['role_id']]['kind'], 'batch_id': batch['batch_id'], 'source_sha256': asset['source']['sha256'], 'provenance_level': 'managed-imagegen-original-and-supplied-tool-result-matched', 'derivative_sha256': asset['derivative']['sha256'], 'usage': usages})
        if game:
            required_surfaces = set(declaration.get('required_surfaces', []))
            if any(Path(name).suffix.lower() in ('.html', '.css', '.jsx', '.tsx', '.vue', '.svelte') for name in artifact_hashes):
                required_surfaces.add('web')
            if native_required:
                required_surfaces.add('figma')
            need(required_surfaces and required_surfaces <= {'web', 'figma'}, 'actual game delivery surfaces required for responsive generated skins')
            skins = receipt.get('responsive_skins')
            need(isinstance(skins, list), 'generated button/title skins require actual text-resize evidence')
            required_skin_roles = {r['id'] for r in roles if r.get('kind') in ('button_frame', 'section_title')}
            need(all(any(s.get('role_id') == role and s.get('surface') == surface for s in skins)
                     for role in required_skin_roles for surface in required_surfaces), 'responsive evidence missing for each generated button/title role and actual delivery surface')
            need(all(any(s.get('role_id') == role and s.get('surface') == surface and s.get('observations') and s['observations'][0].get('viewport_width', 10000) <= 360 for s in skins)
                     for role in required_skin_roles for surface in required_surfaces), 'each title/control skin needs an actual narrow mobile text stress test')
            for skin in skins:
                need(skin.get('role_id') in required_skin_roles and skin.get('surface') in required_surfaces and
                     skin.get('model') in ('nine-slice', 'repeat-center'), 'text-responsive skin needs a generated role, actual surface and stretch/repeat perimeter model')
                need(skin.get('target') in artifact_hashes and skin.get('locator'), 'responsive skin target must be a current visual artifact')
                source, source_bytes = pin(skin.get('source'))
                need(skin['source']['path'] in artifact_hashes and artifact_hashes[skin['source']['path']] == skin['source']['sha256'] and
                     source.suffix.lower() in ('.html', '.css', '.js', '.jsx', '.ts', '.tsx', '.json'), 'responsive skin source must be pinned current implementation/native structure, not a plan')
                if skin['surface'] == 'web':
                    source_text = source_bytes.decode('utf-8')
                    need(re.search(r'border-image|borderImage|nine-slice|repeat-center', source_text) and
                         re.search(r'inline-flex|inline-grid|display\s*[:=]\s*[\"\']?(?:flex|grid)', source_text) and
                         re.search(r'fit-content|max-content|(?:width|inline-size)\s*:\s*auto', source_text),
                         'current HTML/CSS must implement text-hug and sliced/repeated generated perimeter, not a plan or fixed img')
                _, measured = pin(skin.get('evidence'))
                measured = json.loads(measured)
                observations = skin.get('observations')
                need(isinstance(observations, list) and len(observations) >= 2 and measured.get('observations') == observations and
                     measured.get('locator') == skin['locator'] and measured.get('surface') == skin['surface'], 'responsive observations must match supplied actual tool measurement record')
                need(len(observations[-1].get('label', '')) > len(observations[0].get('label', '')) or
                     '\n' in observations[-1].get('label', ''), 'actually change short label to longer or multiline text')
                first = observations[0]
                if by_role[skin['role_id']]['kind'] == 'section_title':
                    title_for = skin.get('title_for')
                    _, target_bytes = pin({'path': skin['target'], 'sha256': artifact_hashes[skin['target']]})
                    relationships = list(title_for.values()) if isinstance(title_for, dict) and {'title', 'content', 'next'} <= set(title_for) else [title_for]
                    need(relationships and all(isinstance(value, str) and value.strip() and value.lstrip('#.').encode() in target_bytes for value in relationships) and measured.get('title_for') == title_for, 'actual titleFor content relationship required in target and measurement')
                    flow_relation = skin.get('flow_relation', 'content-follows-title')
                    need(flow_relation in ('content-follows-title', 'content-wraps-title'), 'explicit actual title/content flow relationship required')
                    for observation in observations:
                        content, following = observation.get('content_bounds'), observation.get('next_bounds')
                        need(all(isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in box) and min(box[2:]) > 0 for box in (content, following)), 'actual content/downstream flow bounds required')
                        frame = observation['frame']
                        separated = content[1] >= frame[1] + frame[3] - 1
                        contained = content[0] <= frame[0] + 1 and content[1] <= frame[1] + 1 and content[0] + content[2] >= frame[0] + frame[2] - 1 and content[1] + content[3] >= frame[1] + frame[3] - 1
                        need((contained if flow_relation == 'content-wraps-title' else separated) and following[1] >= content[1] + content[3] - 1, 'title/content/downstream sections overlap')
                    if observations[-1]['frame'][3] > first['frame'][3] + 0.5:
                        content_axis = 3 if flow_relation == 'content-wraps-title' else 1
                        need(observations[-1]['content_bounds'][content_axis] > first['content_bounds'][content_axis] and observations[-1]['next_bounds'][1] > first['next_bounds'][1], 'title grew but content/downstream flow stayed fixed')
                need(all(o.get('viewport_width') == first.get('viewport_width') for o in observations), 'text perturbations must compare like-for-like viewport widths')
                need(observations[-1]['frame'][2] > first['frame'][2] + 0.5 or observations[-1]['frame'][3] > first['frame'][3] + 0.5,
                     'text changed but skin frame geometry stayed fixed')
                for observed in observations:
                    frame, label, padding, corners = (observed.get(key) for key in ('frame', 'label_bounds', 'padding', 'corners'))
                    need(all(isinstance(values, list) and len(values) == 4 for values in (frame, label, padding, corners)), 'actual frame/label/padding/corner measurements required')
                    need(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in [*frame, *label, *padding]) and
                         min(frame[2:]) > 0 and min(label[2:]) > 0 and min(padding) >= 0, 'invalid native/DOM skin geometry')
                    extents = [v for corner in corners for v in (corner if isinstance(corner, list) else [corner])]
                    need(extents and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in extents) and
                         corners == first['corners'], 'corners must retain actual positive physical extents when edges/center stretch')
                    x, y, width, height = frame
                    lx, ly, lw, lh = label
                    top, right, bottom, left = padding
                    need(lx >= x + left - 1 and ly >= y + top - 1 and lx + lw <= x + width - right + 1 and
                         ly + lh <= y + height - bottom + 1, 'responsive label clips or escapes actual padding/frame')
                    viewport = observed.get('viewport_width')
                    need(isinstance(viewport, (int, float)) and 240 <= viewport and x >= -1 and x + width <= viewport + 1,
                         'generated skin exceeds actual max viewport')
                    if by_role[skin['role_id']]['kind'] == 'button_frame':
                        need(width >= 44 and height >= 44, 'generated control violates minimum 44px touch target')
                    capture = next((c for c in finals if c['path'] == observed.get('capture')), None)
                    need(capture is not None and capture.get('state') == 'responsive-probe', 'text perturbation needs actual explicitly labelled probe capture, not final-product substitution')
                    layout = observed.get('source_layout', {})
                    if skin['surface'] == 'web':
                        need(layout.get('display') in ('inline-flex', 'inline-grid', 'flex', 'grid') and
                             layout.get('width') in ('auto', 'fit-content', 'max-content') and layout.get('height') in ('auto', 'fit-content', 'max-content') and
                             layout.get('border_model') == skin['model'], 'HTML skin must hug real text with stretch/repeat perimeter, not a fixed img')
                    else:
                        need(layout.get('layoutMode') in ('HORIZONTAL', 'VERTICAL') and
                             ((layout.get('primaryAxisSizingMode') == 'AUTO' and layout.get('counterAxisSizingMode') == 'AUTO') or
                              (layout.get('layoutSizingHorizontal') == 'HUG' and layout.get('layoutSizingVertical') == 'HUG')),
                             'native generated skin must use actual content-hug layout in both dimensions')
            report['responsive_skin_roles'] = sorted(required_skin_roles)
            report['responsive_skin_surfaces'] = sorted(required_surfaces)
        for path, digest in pins.items():
            need(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'evidence changed during validation: ' + path)
        report.update(status='passed', passed=True, declared_sequence=[1, 2, 3, 4])
    except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error, zlib.error) as exc:
        errors.append(str(exc))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--intent', choices=('create', 'inspect'), default='create')
    args = parser.parse_args()
    try:
        bindings = json.loads(args.bindings.read_text())
        selection_path = None
        if args.intent == 'create':
            import design_directions
            declaration = bindings.get('design_directions', {})
            selection_path = args.bindings.parent / declaration.get('selection', '')
            design_directions.require_selected(selection_path)
        # Same base as check_project: bindings-relative paths resolve from the bindings file's folder.
        result = evaluate(args.bindings.parent, bindings.get('design_review'), required=True, native_required='native_handoff' in bindings, selection_path=selection_path, inspection=args.intent == 'inspect')
        root = Path(result.get('project_root') or args.bindings.parent).resolve()
        if not (root == args.project.resolve() or root.is_relative_to(args.project.resolve())):
            raise ValueError('--project must contain the bindings project root: ' + str(root))
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / 'design-review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': result['status'], 'passed': result['passed'], 'errors': result['errors']}))
        return 0 if result['passed'] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        import sys
        print(json.dumps({'workflow_state': None, 'required_boundary': State.WAIT_SELECTION.name, 'blocked_reason': str(exc), 'executed': []}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
