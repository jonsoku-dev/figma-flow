#!/usr/bin/env python3
"""Build an offline, deterministic multi-skill plan from a design brief."""
import argparse
import json
from pathlib import Path
import re
import sys

import campaign_library
import campaign_forms
import review_destination
import workflow
from design_intent import direction_mode

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / 'library/design-routes.json'
ORDER = ('direction', 'logo', 'icons', 'images', 'typography', 'motion', 'figma', 'verification')
SKILLS = {
    'direction': ['figma-flow', 'frontend-design'],
    'logo': ['campaign-identity'], 'icons': ['campaign-identity'], 'images': ['imagegen'],
    'typography': ['campaign-identity'], 'motion': ['motion', 'emil-design-eng'],
    'figma': ['figma-flow'], 'verification': ['figma-flow'],
}
TERMS = {
    'logo': r'logo|wordmark|logotype|로고|워드마크|ロゴ',
    'icons': r'icons?|아이콘|アイコン|ピクト|인장|スタンプ|seal|stamp',
    'images': r'image|illustrat|photo|이미지|일러스트|사진|イラスト|画像|写真|키\s*비주얼|키아트|key[ -]?art|원화|キービジュアル|(?<![a-z])kv(?![a-z])',
    'typography': r'font|typograph|lettering|폰트|서체|타이포|레터링|글자|フォント|書体|文字|レタリング',
    'motion': r'motion|animat|transition|모션|애니메이션|움직|전환|アニメ|モーション|動き',
    'figma': r'figma|피그마|フィグマ',
}
SURFACES = {
    'key_visual': r'key[ -]?art|키아트|key[ -]?visual|(?<![a-z])kv(?![a-z])|키비주얼|키 비주얼|キービジュアル|hero|히어로|ヒーロー',
    'lettering': TERMS['logo'] + '|' + TERMS['typography'],
    'collectible': r'collectible|souvenir|merch|굿즈|기념품|수집품|수집형|수집용|승선증|티켓|패스|boarding[ -]?pass|ticket|\bpass\b|乗船証|チケット|パス|グッズ|記念品|コレク',
    'seal': r'인장|スタンプ|seal|stamp',
    'web': r'website|landing|web|웹|랜딩|사이트|ウェブ|サイト|ランディング',
    'poster': r'poster|포스터|ポスター',
}
STYLES = {
    'cinematic': r'cinematic|film[ -]?like|시네마|영화|シネマ|映画',
    'graphic': r'bold|graphic|그래픽|대담|강렬|볼드|グラフィック|大胆',
    'illustrated_collectible': r'illustrat|collectible|일러스트|수집|イラスト|コレク',
}
NEGATIVE = r'없이|제외|금지|하지\s*마|하지\s*않|말고|원치\s*않|불필요|아닌|아니라|말고|ではなく|じゃなく|不要|なし|禁止|しない|除外'

# A transport constraint must not be parsed as a ban on generating artwork.
NO_MCP = r'(?:figma\s*|피그마\s*|フィグマ\s*)?mcp(?:는|를|를?\s*사용)?\s*(?:없이|금지|제외|なし|禁止|使わない)|(?:no|without)\s+(?:figma\s+)?mcp'


def load_registry(path=DEFAULT_REGISTRY):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Expected version 1 design route registry')
    for key in ('resources', 'lanes'):
        if not isinstance(data.get(key), list):
            raise ValueError(f'{key} must be an array')
        seen = set()
        for row in data[key]:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', row['id']) or row['id'] in seen:
                raise ValueError(f'Invalid or duplicate {key} ID')
            seen.add(row['id'])
    resources = {r['id'] for r in data['resources']}
    for row in data['resources']:
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('title', 'kind', 'publisher', 'url', 'role', 'limit')):
            raise ValueError('Resource fields must be nonempty text')
    if {r['id'] for r in data['lanes']} != set(ORDER):
        raise ValueError('Registry must contain exactly the eight supported lanes')
    for lane in data['lanes']:
        for key in ('resources', 'steps', 'checks'):
            if not isinstance(lane.get(key), list) or not all(isinstance(s, str) and s.strip() for s in lane[key]):
                raise ValueError(f'Lane {key} must be a text array')
        if not isinstance(lane.get('title'), str) or not lane['title'].strip() or not set(lane['resources']) <= resources:
            raise ValueError('Lane title or resource references are invalid')
    return data


def matches(pattern, text):
    return bool(re.search(pattern, text, re.I))


def clauses(prompt):
    return [s.strip() for s in re.split(r'[\n,.;。；!?]|(?:그리고|하지만|대신|\bbut\b|\bwhile\b)', prompt, flags=re.I) if s.strip()]


def denied(term, text):
    return matches(r'(?:no|not|without|exclude|do not|don.t)\s+(?:\w+\s+){0,2}(?:' + term + r')|(?:' + term + r')[^,;。.!?\n]{0,18}(?:' + NEGATIVE + ')', text)


def direction_for(surface, text):
    cues = []
    for chunk in clauses(text):
        targets = [(name, hit) for name, pattern in SURFACES.items() for hit in re.finditer(pattern, chunk, re.I)]
        for style, pattern in STYLES.items():
            for cue in re.finditer(pattern, chunk, re.I):
                if denied(pattern, chunk) or not targets:
                    continue
                # Attach each aesthetic cue to the nearest named surface, not the whole sentence.
                following = [item for item in targets if 0 <= item[1].start() - cue.end() <= 20 and not matches(r'\band\b|와|과|및|と', chunk[cue.end():item[1].start()])]
                pool = following or targets
                nearest, _ = min(pool, key=lambda item: (max(item[1].start() - cue.end(), cue.start() - item[1].end(), 0), item[1].start() < cue.start()))
                if nearest == surface:
                    cues.append(style)
    cues = list(dict.fromkeys(cues))
    choice = cues[0] if len(cues) == 1 else 'repository_context'
    return {'surface': surface, 'direction': choice, 'cues': cues,
            'basis': 'explicit_cue' if choice in cues else 'inspect_existing_design',
            'fallback': choice not in cues}


def route(prompt, registry=None, campaign_data=None, context=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('Prompt must be nonempty text')
    registry = registry if registry is not None else load_registry()
    if context is not None and not isinstance(context, str):
        raise ValueError('Context must be text')
    text = ((context + '\n') if context else '') + prompt
    text = text.casefold()
    intent = re.sub(NO_MCP, ' ', text, flags=re.I)
    chunks = clauses(intent)
    current = re.sub(NO_MCP, ' ', prompt.casefold(), flags=re.I)
    research = matches(r'research[ -]?only|recommendations?\s+only|references?\s+only|조사만|리서치만|추천만|자료만|조사\s*전용|調査のみ|提案のみ|おすすめだけ', text)
    recommendation_goal = matches(r'추천해|추천해줘|조사해|조사해봐|스킬[^.!?\n]{0,20}(?:추천|조사)|recommend|research|調べて|おすすめ', current)
    creation_goal = matches(r'만들어|제작해|구현해|옮겨|생성해|그려|create|build|implement|generate|作って|作成して', current)
    if recommendation_goal and not creation_goal:
        research = True
    elif context and creation_goal and not recommendation_goal:
        research = False
    form_plans = campaign_forms.select(prompt, context)
    continuation = bool(context and (matches(r'모두|전부|함께|계속|그대로|all|both|continue', current) or re.search(r'(?<!\d)[123](?!\d)', current)))
    game_campaign = matches(r'game|게임|ゲーム', text) and (bool(form_plans) or matches(r'campaign|캠페인|キャンペーン|landing|랜딩', text))
    ui_scope = game_campaign or bool(form_plans) or matches(r'website|landing|portfolio|frontend|interface|dashboard|\bui\b|웹|랜딩|사이트|화면|앱|application|프론트|대시보드|피그마|figma|フィグマ', intent)
    design_draft = matches(r'시안|목업|프로토타입|\bmockups?\b|\bprototypes?\b|モックアップ|プロトタイプ', current)
    if design_draft and matches(r'버튼|조작|화면|캠페인|페이지|button|screen|page|campaign|画面', current):
        ui_scope = True
    technical_only = matches(r'read.only|inspect.only|technical.only|backend.only|읽기만|열람만|분석만|기술\s*(?:수정|검사)만|백엔드만|조사만|추천만', current)
    observational = matches(r'\binspect\b|\breview\b|\baudit\b|critique|열람|검토|리뷰|비평|분석', current) and not creation_goal and not matches(r'redesign|polish|refine|fix|리디자인|개선|수정|다듬', current)
    technical_only = technical_only or observational
    ui_creation = ui_scope and not research and not technical_only and (creation_goal or design_draft or matches(r'redesign|design|polish|refine|리디자인|디자인|개선|다듬|새로|처음부터', current) or any(matches(pattern, current) for pattern in campaign_forms.PATTERNS.values()) or (continuation and (form_plans or matches(r'create|build|design|만들|제작|구현|디자인', intent))))
    selected = {'direction', 'verification'}
    exclusions = []
    for lane, term in TERMS.items():
        if matches(term, text):
            positive = [c for c in chunks if matches(term, c) and not denied(term, c)]
            if positive:
                selected.add(lane)
            else:
                exclusions.append({'lane': lane, 'reason': 'explicit_exclusion'})
    if matches(r'(?:기존\s*)?(?:로고|워드마크)(?:를|는|는?만)?\s*(?:그대로\s*)?유지|keep (?:the )?(?:existing )?(?:logo|wordmark)|ロゴを維持', current):
        selected.discard('logo')
        exclusions.append({'lane': 'logo', 'action': 'redesign', 'reason': 'preserve_existing_mark'})
    surfaces = [direction_for(s, text) for s, p in SURFACES.items() if matches(p, text)]
    if not surfaces:
        surfaces = [{'surface': 'requested_output', 'direction': 'repository_context', 'cues': [], 'basis': 'inspect_existing_design', 'fallback': True}]
    generation_term = r'image\s*gen(?:eration)?|generat(?:e|ion)\s+(?:new\s+)?image|이미지\s*생성|画像生成|生成画像'
    generation_action = generation_term + r'|generate|generation|그려|그리기|만들|생성|描いて|作成|生成'
    # The current turn supersedes historical generation instructions; SSOT below still uses context.
    generation_scope = current if matches(generation_action + r'|no\s+(?:new\s+)?assets|에셋\s*없이', current) else intent
    no_images = denied(generation_action, generation_scope) or (any(e['lane'] == 'images' for e in exclusions) and not (context and matches(generation_action, current) and not denied(generation_action, current))) or matches(r'no\s+(?:new\s+)?assets|에셋\s*없이|자산\s*생성\s*없이|素材生成なし', generation_scope)
    reuse_pattern = r'download|다운로드|ダウンロード|existing\s+(?:images?|assets?|art)|기존\s*(?:이미지|에셋|원화)|既存.*画像'
    image_download = matches(reuse_pattern, current if matches(reuse_pattern, current) else text)
    image_save = matches(r'(?:이미지|image|画像)[^,;。.!?\n]{0,8}(?:저장|save|保存)|save\s+(?:the\s+)?image', current)
    image_generate = any(matches(generation_action, chunk) and not denied(generation_action, chunk) for chunk in clauses(generation_scope))
    if any(s['surface'] == 'collectible' for s in surfaces) and not no_images:
        selected.add('images')
    images_action = 'generate' if image_generate and not no_images else 'reuse_or_download' if image_download else 'inspect_existing_assets'
    if no_images:
        selected.discard('images')
        exclusions.append({'lane': 'images', 'action': 'generate', 'reason': 'explicit_generation_exclusion'})
        if image_download:
            selected.add('images')
            images_action = 'reuse_or_download'
    if ui_creation and (game_campaign or {'logo', 'icons'} & selected):
        if game_campaign:
            selected.update(('logo', 'icons'))
        if not no_images:
            selected.add('images')
            images_action = 'generate'
    font_scope = current if matches(TERMS['typography'], current) else text
    preserve_font = matches(r'(?:폰트|서체|font|フォント|書体)[^,;。.!?\n]{0,12}(?:유지|그대로|keep|preserve|維持|そのまま)|keep\s+(?:the\s+)?(?:existing\s+)?fonts?', font_scope)
    if preserve_font and not matches(r'font\s*redesign|서체\s*재설계|폰트\s*변경|フォント変更', font_scope):
        selected.discard('typography')
        exclusions.append({'lane': 'typography', 'action': 'redesign', 'reason': 'preserve_existing_fonts'})
    ssot = matches(r'ssot|source\s+of\s+truth|원본\s*(?:그대로|기준)|정확(?:히|한)?\s*(?:figma|피그마)|(?:figma|피그마)[^\n]{0,25}(?:그대로|정확|동일)|完全一致', text) and matches(TERMS['figma'], text)
    if ssot:
        selected.add('figma')
    # The same policy admits the draft itself; optional tools do not select the destination.
    scope = (review_destination.resolve(prompt, context=context) if ui_creation else
             review_destination.requested(prompt) or review_destination.requested(context))
    if scope == 'figma':
        selected.add('figma')
        exclusions = [row for row in exclusions if row['lane'] != 'figma']
    elif scope == 'local' or not scope:
        selected.discard('figma')
        ssot = False
    figma_backed = 'figma' in selected
    locales = [locale for locale, pattern in (('KR', r'한일|한국|한글|한국어|korean|\bkr\b|韓国'), ('JP', r'한일|일본|일문|일본어|japanese|\bjp\b|日本')) if matches(pattern, text)]
    constraints = {'figma_transport': 'local_developer_plugin',
                   'figma_mcp_allowed': False,
                   'native_handoff': 'required_before_acceptance' if figma_backed else 'not_applicable_local_only',
                   'dev_mode_required': False, 'review_destination': scope,
                   'image_generation': 'excluded' if no_images else 'only_for_selected_asset_scopes',
                   'logo_icon_origin': 'genuine_image_generation_required' if ui_creation else 'task_scope',
                   'font_policy': 'preserve' if preserve_font else 'inspect_repository_and_requested_locales',
                   'locales': locales, 'network': 'not_performed', 'install': 'never_automatic',
                   'authority': 'plan_does_not_grant_permissions',
                   'skill_capabilities': 'verify_local_availability_and_target_fit_before_dispatch; resource publisher is not execution authority'}
    direction = dict(direction_mode(prompt), source='current_request')
    if direction['mode'] == 'inspect-context' and direction['basis'] != 'non_authoring_request' and context:
        inherited = direction_mode(context)
        if inherited['mode'] != 'inspect-context':
            direction = dict(inherited, source='provided_context')
    direction_instruction = {
        'direct': 'Author one direction from the specific user request. Run design_actions.py draft --mode direct and review. Admit the current artifact hashes through the actual managed user instruction with admit-direct after critique and required native verification; do not ask for a candidate choice.',
        'compare': 'Show two or three distinct comparable directions. Run design_actions.py draft --mode compare and review. Present the current artifacts, then wait for the actual user to select an exact candidate version. Production remains blocked until that choice is verified.',
        'inspect-context': 'Inspect the actual repository, brief, references and design system before resolving the direction protocol. No draft count or production admission is decided yet. Resolve direct or compare from that context before drafting.'
    }[direction['mode']]
    lanes = {r['id']: r for r in registry['lanes']}
    resources = {r['id']: r for r in registry['resources']}
    routes = []
    for lane in ORDER:
        if lane not in selected:
            continue
        row = lanes[lane]
        scopes = [s['surface'] for s in surfaces if (lane != 'images' or s['surface'] not in ('lettering', 'web')) and (lane not in ('logo', 'icons', 'typography') or (lane == 'icons' and s['surface'] == 'seal') or (lane != 'icons' and s['surface'] == 'lettering'))]
        if not scopes:
            scopes = [lane]
        actions = list(row['steps'])
        if lane == 'images':
            actions = [images_action + ': ' + s for s in scopes]
            if images_action == 'generate' and image_download:
                actions.append('reuse_or_download: only explicitly selected existing reference assets; keep generated deliverables separate.')
            if image_save:
                actions.append('save_image: persist the actual selected/generated image file and verify its path; saving is separate from generation.')
            if images_action != 'generate':
                actions.append('Do not invoke imagegen; inspect licenses and available source assets.')
        if lane == 'typography':
            actions.append('Inspect actual KR/JP glyph coverage, font license, weight, fallback and line breaking for requested locales.')
        if lane == 'figma':
            actions.append('Native semantic handoff is required for every Figma-backed design: use actual getters to read screen/control meanings from legacy native annotations or graph-linked structured specification metadata with ordinary readable specification boards outside artboards. Verify target IDs, real component instances and bound variables against the expected graph with tools/native_handoff.py. A planned record or screenshot does not establish actual native state.')
            actions.insert(0, 'Use local developer-plugin import/readback; do not call Figma MCP. Run python3 tools/figma_feature.py route FEATURE to find registered Flow operations or a reviewed local SDK route; read skills/figma-flow/references/figma-feature-routes.md for product UI and REST gates.')
        resource_ids = row['resources']
        skill_ids = SKILLS[lane] if lane != 'images' or images_action == 'generate' else ['figma-flow']
        raster_cue = r'(?:raster|bitmap|illustrated|as an? image|래스터|비트맵|이미지(?:로|를)?|일러스트(?:형|풍)?|イラスト|画像(?:で|を))'
        raster_ideation = lane in ('logo', 'icons') and not no_images and (image_generate or matches(r'ideat|concept|시안|컨셉|발상|아이디어|案', text)) and any(
            matches(raster_cue + r'\s*(?:style\s+)?(?:' + TERMS[lane] + r')|(?:' + TERMS[lane] + r')(?:를|을|は|を)?\s*' + raster_cue, c) for c in chunks)
        if raster_ideation:
            skill_ids = ['imagegen'] + skill_ids
            actions.insert(0, 'Use imagegen only for requested raster/illustrated ' + lane + ' ideation; preserve editable/vector delivery checks separately. Local brandkit is optional and is not verified design authority.')
        if ui_creation and lane in ('direction', 'typography', 'verification'):
            skill_ids = list(dict.fromkeys(['impeccable', 'design-taste-frontend', *skill_ids]))
            actions.insert(0, 'Run tools/skill_dependencies.py --check and read the verified bundled Impeccable and design-taste-frontend sources before authoring. Inspect actual purpose, content hierarchy, design-system typography, layout and assets; use desktop/mobile typography specimens. Follow the resolved direction protocol, critique actual artifacts, fix issues and confirm current hashes. Respect tasteskill scope exclusions for dense product UI.')
        if ui_creation and lane in ('logo', 'icons'):
            skill_ids = list(dict.fromkeys(['imagegen', *skill_ids]))
            actions.insert(0, 'Logo/icon original must be genuine image generation; preserve real raster/tool-result identity, raster-only derivative transforms and actual visible usage. Library icons, hand-coded/traced SVG paths, emoji and font-built marks cannot substitute. If generation is excluded, keep this required phase blocked.')
        if game_campaign and ui_creation and lane == 'direction':
            actions.insert(0, 'After validating the exact admitted direction and its user authority, freeze its visual references plus the shared concept/reference sheets and purpose-specific full game role inventory with tools/asset_batch.py; then invoke the actual image_gen.imagegen host tool for every ready-to-run generation-requests.json request. Preserve real managed originals/tool results. Pending packets are not generation; scoped retries keep the same batch. Generated title/button skins must content-hug live labels using nine-slice/repeat-center, titleFor/wrapping/downstream flow, and actual narrow-mobile short/long probes before completion.')
        conditional_skills = []
        if not ui_creation and (lane == 'typography' or (lane == 'direction' and matches(r'critique|review|audit|비평|검토|리뷰|평가|レビュー', text))):
            conditional_skills.append({'id': 'impeccable', 'when': 'Target is a frontend typography or critique task; verify local capability and target fit.', 'status': 'conditional'})
        if ui_creation and not research and lane == 'direction':
            actions.insert(0, direction_instruction + ' For requested Figma scope, verify actual getter readback of the native review, graph-linked meanings, component palette, variable bindings, prototype destinations and return links before admission.')
        if research:
            actions = ['Recommend resources and describe proposed checks; do not dispatch edits or generation.']
        routes.append({'id': lane, 'title': row['title'], 'skill_ids': skill_ids, 'conditional_skills': conditional_skills,
                       'resource_ids': resource_ids, 'resources': [resources[i] for i in resource_ids],
                       'asset_scopes': scopes, 'actions': actions, 'checks': row['checks'],
                       'depends_on': [r['id'] for r in routes], 'status': 'recommended' if research else 'planned'})
    gates = [
        {'id': 'scope_authority', 'status': 'required', 'requirement': 'Inspect repository, selected surfaces, available skills and authorized destinations; never auto-install or infer permission.'},
        {'id': 'verification', 'status': 'untested', 'requirement': 'Execute applicable browser, accessibility, responsive, motion and asset checks; record actual evidence separately.'},
    ]
    if ui_creation:
        gates.insert(1, {'id': 'creative_design_review', 'status': 'blocked_until_observed',
                        'requirement': 'Frontend UI creation/redesign requires source-resolved Impeccable and applicable tasteskill, target-script font-first desktop/mobile specimens, concrete post-authoring visual critique and fixes, and final captures pinned to current artifacts. Logos and icons must originate in genuine image generation with raster original/tool-result evidence, verified derivative crops and visible usage. Every game asset shares one frozen concept/version/reference-sheet batch and complete role inventory before production. Missing or generic evidence blocks design completion.',
                        'receipt': 'bindings.design_review -> evidence/design-review.json', 'cli': 'python3 tools/check_project.py --init --brief BRIEF --graph GRAPH --bindings BINDINGS --out NEW_DIRECTORY'})
    if figma_backed:
        gates.insert(1, {'id': 'native_semantic_handoff', 'status': 'blocked_until_observed',
                        'requirement': 'Before accepting any Figma-backed design, read actual getters for screen/control meanings and action/state coverage from legacy native annotations or graph-linked structured specification metadata with readable linked specification boards outside artboards. Verify actual component-set instances used by important controls and actual variable bindings with mode/alias values against an explicit expected graph contract using tools/native_handoff.py. Planned metadata, placeholders, screenshots and unused components do not establish actual native state; missing getter evidence stays blocked.',
                        'transport': constraints['figma_transport']})
    if ssot:
        gates.insert(2, {'id': 'figma_ssot_before_web_writes', 'status': 'blocked_until_observed',
                        'requirement': 'Create or edit every visible output and state in the actual selected Figma source. Observe native nodes and actual exports, record file/page/node IDs and export hashes, and consume those observed values/assets before any downstream web implementation writes. Include locale and responsive states. Scripts, intermediate JSON, invented nodes and planned frames are not readback evidence.',
                        'transport': constraints['figma_transport']})
    creation_workflow = None
    if ui_creation:
        public = workflow.public_graph()
        creation_workflow = {'source': 'library/workflow.json', 'sha256': public['graph_sha256'],
                             'initial_state': public['graph']['initial'],
                             'selection_boundary': (workflow.State.NATIVE_REVIEW_PENDING.value if figma_backed else workflow.State.SELECTION_READY.value) if direction['mode'] == 'direct' else workflow.State.WAIT_SELECTION.value if direction['mode'] == 'compare' else None,
                             'approval_event': workflow.Event.ADMIT_DIRECT.value if direction['mode'] == 'direct' else workflow.Event.SELECT.value if direction['mode'] == 'compare' else None, 'authority': 'human',
                             'direction_mode': direction,
                             'source_of_truth': 'Graph describes allowed transitions; routing is a plan, not an executed transition.'}
        gates.insert(1, {'id': 'human_direction_selection', 'status': 'blocked_until_context_resolution' if direction['mode'] == 'inspect-context' else 'required_before_production',
                        'state': creation_workflow['selection_boundary'],
                        'requirement': direction_instruction + ' Current artifact critique, meaningful content, responsive checks and required actual native verification remain mandatory. Routing is a plan, not visual proof.',
                        'draft_cli': ('python3 tools/design_actions.py draft --project ROOT --brief BRIEF --research RESEARCH --from-existing SPEC --out NEW_DIR --mode ' + direction['mode'] + ' --review-destination ' + ('figma' if figma_backed else 'local')) if direction['mode'] in ('direct', 'compare') else None,
                        'next_action': 'Inspect actual context and resolve direct or compare before drafting.' if direction['mode'] == 'inspect-context' else 'Author the resolved direction protocol with current artifact-linked critique.',
                        'graph_sha256': public['graph_sha256']})
        if figma_backed:
            gates.insert(1, {'id': 'figma_direction_review', 'state': workflow.State.NATIVE_REVIEW_PENDING.value,
                'status': 'required_before_admission' if direction['mode'] == 'direct' else 'required_before_selection' if direction['mode'] == 'compare' else 'required_after_context_resolution', 'requirement': 'Verify actual editable Figma screens, graph-linked specifications and their readable boards, component palette instances, variable bindings, prototype click destinations and return links. ' + direction_instruction,
                'verify_cli': 'python3 tools/design_actions.py verify-native-review --manifest MANIFEST --readback ACTUAL_FIGMA_READBACK'})
    categories = []
    for category, pattern in [('prelaunch', r'prelaunch|launch|사전등록|출시|事前登録|リリース'), ('anniversary', r'anniversary|주년|기념|周年'), ('update', r'update|업데이트|アップデート'), ('participation', r'mission|reward|참여|미션|보상|参加|ミッション|報酬'), ('event', r'event|collab|행사|협업|이벤트|イベント|コラボ'), ('brand-world', r'brand|character|world|브랜드|캐릭터|세계관|ブランド|キャラ|世界観')]:
        if matches(pattern, text):
            categories.append(category)
    campaign_basis = 'explicit_category_cue'
    if not categories and matches(r'campaign|캠페인|キャンペーン', text):
        categories = ['brand-world']
        campaign_basis = 'campaign_context_fallback'
    campaign_plans = []
    if categories:
        data = campaign_data if campaign_data is not None else campaign_library.load_library(campaign_library.DEFAULT_DATA)
        available = {c['id'] for c in data['categories']}
        for category in categories:
            if category in available:
                campaign_plans.append({'category': category, 'basis': campaign_basis, 'market': locales[0] if len(locales) == 1 else None,
                                       'plan': campaign_library.plan(data, category, locales[0] if len(locales) == 1 else None)})
    return {'version': 1, 'status': 'planned', 'mode': 'research' if research else 'execute', 'prompt': prompt, 'context': context,
            'direction_mode': direction, 'authoring_context': {'status': 'inspection_required', 'sources': ['repository', 'brief', 'references', 'design_system'], 'decisions': ['purpose', 'content_hierarchy', 'typography', 'layout', 'asset_rationale'], 'visual_quality': 'unverified'},
            'workflow': creation_workflow, 'interpretation': 'deterministic cue-based proposal; review ambiguous scopes before acting',
            'surfaces': surfaces, 'routes': routes, 'constraints': constraints, 'exclusions': exclusions,
            'gates': gates, 'campaign_forms': form_plans, 'design_review_declaration': ({'operation': 'redesign' if matches(r'redesign|리디자인|새로|처음부터', current) else 'create', 'target_kind': 'game-campaign' if game_campaign else 'website' if form_plans or matches(r'website|landing|portfolio|웹|랜딩|사이트', text) else 'product-ui', 'receipt': 'evidence/design-review.json'} if ui_creation else None), 'campaign_plans': campaign_plans}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--prompt')
    inputs.add_argument('--prompt-file', type=Path)
    context_inputs = parser.add_mutually_exclusive_group()
    context_inputs.add_argument('--context')
    context_inputs.add_argument('--context-file', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument('--campaign-data', type=Path, default=campaign_library.DEFAULT_DATA)
    args = parser.parse_args(argv)
    try:
        prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding='utf-8')
        context = args.context_file.read_text(encoding='utf-8') if args.context_file else args.context
        result = route(prompt, load_registry(args.registry), campaign_library.load_library(args.campaign_data), context)
        if args.out:
            if args.out.exists() or args.out.is_symlink():
                raise ValueError('Output must be a fresh directory')
            args.out.mkdir(parents=False)
            for item in result['campaign_plans']:
                filename = 'campaign-' + item['category'] + '-' + (item['market'] or 'all') + '.json'
                (args.out / filename).write_text(json.dumps(item['plan'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                item['path'] = filename
            (args.out / 'route-plan.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'route_design: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
