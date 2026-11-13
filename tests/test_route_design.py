import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/route_design.py'
sys.path.insert(0, str(TOOL.parent))
spec = importlib.util.spec_from_file_location('route_design', TOOL)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


def registry():
    return {'version': 1,
            'resources': [{'id': 'ref', 'title': 'Reference', 'kind': 'reference', 'publisher': 'Example', 'url': 'https://example.com', 'role': 'evidence', 'limit': 'manual validation'}],
            'lanes': [{'id': lane, 'title': lane, 'resources': ['ref'], 'steps': ['Inspect source and plan selected work.'], 'checks': ['Record observed evidence.']} for lane in router.ORDER]}


class RouteDesignTests(unittest.TestCase):
    def plan(self, text):
        return router.route(text, registry())

    def lanes(self, plan):
        return {r['id']: r for r in plan['routes']}

    def test_ui_and_all_campaign_forms_plan_selection_without_claiming_approval(self):
        import workflow
        plan = router.route('1,2,3 모두 할수있어야해.', registry(), context='기념 이벤트 특설, 신작 공개, 참여 프로모션 웹 만들기')
        self.assertEqual(len(plan['campaign_forms']), 3)
        self.assertEqual(plan['workflow']['sha256'], workflow.graph_hash())
        self.assertEqual(plan['workflow']['initial_state'], workflow.load_graph()['initial'])
        gate = next(g for g in plan['gates'] if g['id'] == 'human_direction_selection')
        self.assertIsNone(gate['state'])
        self.assertIsNone(plan['workflow']['approval_event'])
        self.assertNotIn('selection_sha256', plan)
        self.assertIsNone(gate['draft_cli'])
        self.assertIn('resolve direct or compare', gate['next_action'])
        native = self.plan('Figma 원본으로 게임 캠페인 UI 만들어줘')
        gates = {row['id']: row for row in native['gates']}
        self.assertIsNone(gates['human_direction_selection']['draft_cli'])
        self.assertEqual(gates['figma_direction_review']['state'], workflow.State.NATIVE_REVIEW_PENDING.value)
        self.assertIsNone(self.plan('디자인 자료 조사만')['workflow'])

    def test_every_action_uses_the_resolved_direction_protocol(self):
        direct = self.plan('Figma에서 게임 캠페인 시안 하나만 디자인해줘. 폰트와 로고도 만들어줘.')
        self.assertEqual(direct['direction_mode']['mode'], 'direct')
        actions = ' '.join(action for lane in direct['routes'] for action in lane['actions'])
        self.assertIn('Author one direction', actions)
        self.assertIn('actual managed user instruction with admit-direct', actions)
        for stale in ('Show two or three', 'then compare distinct', 'After explicit selection', 'before selection', 'human-selected'):
            self.assertNotIn(stale, actions)
        native = next(g for g in direct['gates'] if g['id'] == 'native_semantic_handoff')['requirement']
        for evidence in ('actual getters', 'graph-linked structured specification metadata', 'readable linked specification boards', 'actual variable bindings'):
            self.assertIn(evidence, native)
        unresolved = self.plan('게임 캠페인 웹사이트 만들어줘')
        self.assertEqual(unresolved['direction_mode']['mode'], 'inspect-context')
        actions = ' '.join(action for lane in unresolved['routes'] for action in lane['actions'])
        self.assertIn('No draft count or production admission is decided yet', actions)
        self.assertNotIn('Show two or three', actions)
        self.assertIsNone(unresolved['workflow']['approval_event'])
        self.assertIsNone(unresolved['workflow']['selection_boundary'])
        compare = self.plan('게임 캠페인 시안 세 가지 만들어줘')
        self.assertEqual(compare['direction_mode']['mode'], 'compare')
        self.assertIn('Show two or three', ' '.join(self.lanes(compare)['direction']['actions']))
        continued = router.route('계속 만들어줘', registry(), context='Figma에서 시안 하나만 디자인해줘')
        self.assertEqual(continued['direction_mode']['source'], 'provided_context')
        self.assertIn('Author one direction', ' '.join(self.lanes(continued)['direction']['actions']))

    def test_multi_surface_multi_lane_directions_and_dependencies(self):
        result = self.plan('한국 일본 출시 캠페인: cinematic KV와 bold graphic 로고 레터링, illustrated collectible 굿즈 이미지 생성, 아이콘, KR JP typography, motion, Figma SSOT 웹')
        self.assertEqual(list(self.lanes(result)), list(router.ORDER))
        surfaces = {s['surface']: s for s in result['surfaces']}
        self.assertEqual(surfaces['key_visual']['direction'], 'cinematic')
        self.assertEqual(surfaces['lettering']['direction'], 'graphic')
        self.assertEqual(surfaces['collectible']['direction'], 'illustrated_collectible')
        self.assertEqual(self.lanes(result)['icons']['asset_scopes'], ['icons'])
        self.assertNotIn('imagegen', self.lanes(result)['logo']['skill_ids'])
        self.assertNotIn('imagegen', self.lanes(result)['icons']['skill_ids'])
        for i, route in enumerate(result['routes']):
            self.assertEqual(route['status'], 'planned')
            self.assertTrue(route['skill_ids'])
            self.assertEqual(route['depends_on'], list(router.ORDER[:i]))
            self.assertEqual(route['resources'][0]['role'], 'evidence')
        self.assertIn('prelaunch', [p['category'] for p in result['campaign_plans']])
        self.assertEqual(result['constraints']['locales'], ['KR', 'JP'])

    def test_negative_contrast_does_not_route_denied_cinematic_style(self):
        result = self.plan('시네마틱이 아닌 bold graphic lettering 로고만 제작. 이미지 생성 없이. 모션 제외.')
        self.assertEqual({s['surface']: s['direction'] for s in result['surfaces']}['lettering'], 'graphic')
        self.assertNotIn('motion', self.lanes(result))
        self.assertNotIn('images', self.lanes(result))
        self.assertEqual(self.lanes(result)['logo']['asset_scopes'], ['lettering'])

    def test_download_and_preserved_fonts_do_not_dispatch_generation(self):
        result = self.plan('기존 이미지 다운로드만. 이미지 생성 없이. 폰트 유지. 웹 랜딩 구현')
        images = self.lanes(result)['images']
        self.assertNotIn('imagegen', images['skill_ids'])
        self.assertTrue(images['actions'][0].startswith('reuse_or_download:'))
        self.assertNotIn('typography', self.lanes(result))
        self.assertEqual(result['constraints']['font_policy'], 'preserve')

    def test_figma_exact_no_mcp_no_assets_has_real_source_gate(self):
        result = self.plan('Figma SSOT 원본 그대로 웹 구현. Figma MCP 없이. 이미지 생성 없이. no new assets. 폰트 유지')
        self.assertEqual(result['constraints']['figma_transport'], 'local_developer_plugin')
        self.assertFalse(result['constraints']['figma_mcp_allowed'])
        self.assertNotIn('images', self.lanes(result))
        gate = next(g for g in result['gates'] if g['id'] == 'figma_ssot_before_web_writes')
        self.assertEqual(gate['status'], 'blocked_until_observed')
        for cue in ('every visible output', 'actual selected Figma source', 'native nodes', 'exports', 'before any downstream web'):
            self.assertIn(cue, gate['requirement'])
        self.assertIn('do not call Figma MCP', self.lanes(result)['figma']['actions'][0])

    def test_all_figma_requests_use_local_routes_without_remote_fallback(self):
        for prompt in ('Figma 화면 만들어줘', 'Figma 화면을 MCP 없이 만들어줘',
                       'Figma 디자인을 원격 MCP로 만들어줘'):
            with self.subTest(prompt=prompt):
                plan = self.plan(prompt)
                self.assertEqual(plan['constraints']['figma_transport'], 'local_developer_plugin')
                self.assertIs(plan['constraints']['figma_mcp_allowed'], False)
                action = self.lanes(plan)['figma']['actions'][0]
                self.assertIn('tools/figma_feature.py route FEATURE', action)
                self.assertIn('registered Flow', action)
                self.assertIn('local SDK', action)
                self.assertNotIn('only when explicitly requested', action)

    def test_every_figma_destination_requires_native_handoff_without_ssot_keyword(self):
        for prompt in ('Figma 화면 만들어줘', '피그마 디자인 MCP 없이 만들어줘',
                       'Figma 디자인을 원격 MCP로 만들어줘', 'フィグマの画面を作成して'):
            with self.subTest(prompt=prompt):
                plan = self.plan(prompt)
                gate = next(g for g in plan['gates'] if g['id'] == 'native_semantic_handoff')
                self.assertEqual(gate['status'], 'blocked_until_observed')
                self.assertIn('annotations', gate['requirement'])
                self.assertIn('actual variable bindings', gate['requirement'])
                self.assertEqual(plan['constraints']['native_handoff'], 'required_before_acceptance')
                self.assertIn('Native semantic handoff', ' '.join(self.lanes(plan)['figma']['actions']))
        continued = router.route('화면을 계속 만들어줘', registry(), context='Figma 화면 제작')
        self.assertTrue(any(g['id'] == 'native_semantic_handoff' for g in continued['gates']))

    def test_true_local_only_has_no_native_gate_and_current_exclusion_wins_context(self):
        for prompt, context in [('로컬 HTML 화면을 만들어줘', None),
                                ('Figma 없이 로컬 HTML 화면만 만들어줘', 'Figma SSOT 화면 제작'),
                                ('Create a local page without Figma.', 'Figma design')]:
            with self.subTest(prompt=prompt):
                plan = router.route(prompt, registry(), context=context)
                self.assertNotIn('figma', self.lanes(plan))
                self.assertFalse(any(g['id'] in ('native_semantic_handoff', 'figma_ssot_before_web_writes') for g in plan['gates']))
                self.assertEqual(plan['constraints']['native_handoff'], 'not_applicable_local_only')

    def test_frontend_creation_defaults_to_real_skills_font_first_and_generated_game_inventory(self):
        for prompt in ('웹 랜딩을 새로 디자인해줘', 'Figma 게임 캠페인 랜딩을 처음부터 만들어줘', 'Create a frontend website'):
            plan = self.plan(prompt)
            self.assertIsNotNone(plan['design_review_declaration'])
            self.assertTrue(any(g['id'] == 'creative_design_review' for g in plan['gates']))
            for lane in ('direction', 'verification'):
                self.assertTrue({'impeccable', 'design-taste-frontend'} <= set(self.lanes(plan)[lane]['skill_ids']))
        game = self.plan('게임 캠페인 웹을 처음부터 만들어줘')
        self.assertEqual(game['design_review_declaration']['target_kind'], 'game-campaign')
        for lane in ('logo', 'icons'):
            self.assertIn('imagegen', self.lanes(game)[lane]['skill_ids'])
        for prompt in ('Read-only inspect a frontend website', 'Inspect a frontend website', 'Review the existing UI design', 'Technical only: inspect a backend API', 'Figma 디자인 조사만'):
            self.assertIsNone(self.plan(prompt)['design_review_declaration'])

    def test_rhythm_campaign_keeps_motion_without_routing_music_taste_skill(self):
        plan = self.plan('리듬 게임 캠페인 웹을 만들어줘. 120 BPM에 맞춘 모션도 넣어줘.')
        lanes = self.lanes(plan)
        self.assertIn('motion', lanes)
        self.assertTrue({'impeccable', 'design-taste-frontend'} <= set(lanes['direction']['skill_ids']))
        self.assertTrue({'impeccable', 'design-taste-frontend'} <= set(lanes['verification']['skill_ids']))
        for lane in lanes.values():
            self.assertNotIn('taste', lane['skill_ids'])
            self.assertFalse(any('Read actual taste source' in action for action in lane['actions']))

    def test_three_campaign_forms_individual_and_all_numbered_context(self):
        context = '게임 웹 캠페인 제작. 1 기념·행사형, 2 출시·공개형, 3 참여·프로모션형 중 선택한다.'
        ids = ['commemorative-event', 'launch-reveal', 'participation-promotion']
        all_forms = router.route('1,2,3 모두', registry(), context=context)
        self.assertEqual([row['id'] for row in all_forms['campaign_forms']], ids)
        self.assertIsNotNone(all_forms['design_review_declaration'])
        for number, expected in enumerate(ids, 1):
            result = router.route(str(number) + '번으로 만들어줘', registry(), context=context)
            self.assertEqual([row['id'] for row in result['campaign_forms']], [expected])
        for text, expected in zip(('기념·행사형 웹을 만들어줘', '출시·공개형 웹을 만들어줘', '참여·프로모션형 웹을 만들어줘'), ids):
            result = self.plan(text)
            self.assertEqual([row['id'] for row in result['campaign_forms']], [expected])
            self.assertTrue(result['campaign_forms'][0]['asset_coverage'])
            self.assertTrue(result['campaign_forms'][0]['primary_cta'])
        combined = router.route('기념·행사형과 참여·프로모션형을 함께 제작해줘', registry())
        self.assertEqual([row['id'] for row in combined['campaign_forms']], [ids[0], ids[2]])
        self.assertIn('real-teaser', all_forms['campaign_forms'][1]['sequence'])
        self.assertEqual(all_forms['campaign_forms'][2]['sequence'][0], 'offer-and-reward')

    def test_campaign_form_numbers_are_menu_answers_not_counts_and_honor_exclusions(self):
        context = '1 기념·행사형 2 출시·공개형 3 참여·프로모션형 게임 웹 제작'
        natural = self.plan('2주년 기념 캠페인에 캐릭터 3명으로 만들어줘')
        self.assertEqual([f['id'] for f in natural['campaign_forms']], ['commemorative-event'])
        for text in ('사전예약 웹을 만들어줘', '신작 공개 캠페인 웹', 'launch-reveal'):
            self.assertEqual([f['id'] for f in self.plan(text)['campaign_forms']], ['launch-reveal'])
        self.assertEqual([f['id'] for f in self.plan('기념 이벤트 특설 웹')['campaign_forms']], ['commemorative-event'])
        for text in ('출시·공개형 제외하고 참여·프로모션형만 만들어줘', 'not launch-reveal but participation-promotion'):
            self.assertEqual([f['id'] for f in self.plan(text)['campaign_forms']], ['participation-promotion'])
        selected = router.route('2번 유형으로 만들어줘', registry(), context=context)
        self.assertEqual([f['id'] for f in selected['campaign_forms']], ['launch-reveal'])
        selected = router.route('출시·공개형은 제외', registry(), context=context)
        self.assertEqual([f['id'] for f in selected['campaign_forms']], ['commemorative-event', 'participation-promotion'])

    def test_research_only_is_recommendation_without_dispatch(self):
        result = self.plan('Research only: recommend cinematic KV image generation, logo and typography for Japanese launch campaign')
        self.assertEqual(result['mode'], 'research')
        for lane in result['routes']:
            self.assertEqual(lane['status'], 'recommended')
            self.assertEqual(lane['actions'], ['Recommend resources and describe proposed checks; do not dispatch edits or generation.'])
        self.assertTrue(result['campaign_plans'])
        self.assertEqual(result['campaign_plans'][0]['plan']['status'], 'untested')

    def test_japanese_and_explicit_style_has_no_forced_mashup(self):
        result = self.plan('映画風キービジュアル。大胆なロゴ。イラストのグッズとアイコンを作成。フォントはそのまま。モーション不要。画像生成なし。Figma完全一致、MCPなし')
        self.assertNotIn('images', self.lanes(result))
        self.assertNotIn('motion', self.lanes(result))
        self.assertNotIn('typography', self.lanes(result))
        self.assertIn('logo', self.lanes(result))
        self.assertFalse(result['constraints']['figma_mcp_allowed'])

    def test_carried_context_routes_all_requested_assets_without_making_up_direction(self):
        result = router.route('모두. 유저의 프롬프트에 따라 자동라우팅', registry(), context='cinematic KV, bold graphic logo lettering, illustrated collectible souvenir images 생성. typography, icons, motion')
        self.assertEqual(set(self.lanes(result)), set(router.ORDER) - {'figma'})
        self.assertEqual({s['surface']: s['direction'] for s in result['surfaces']}['collectible'], 'illustrated_collectible')
        self.assertNotIn('lettering', self.lanes(result)['images']['asset_scopes'])
        empty = self.plan('모두. 유저의 프롬프트에 따라 자동라우팅')
        self.assertEqual(empty['surfaces'][0]['direction'], 'repository_context')

    def test_explicit_raster_ideation_and_target_specific_optional_skills(self):
        result = self.plan('Create raster logo concepts and illustrated icons. KR typography critique, authored motion.')
        lanes = self.lanes(result)
        self.assertIn('imagegen', lanes['logo']['skill_ids'])
        self.assertIn('imagegen', lanes['icons']['skill_ids'])
        self.assertEqual(lanes['typography']['conditional_skills'][0]['id'], 'impeccable')
        self.assertIn('emil-design-eng', lanes['motion']['skill_ids'])
        denied = self.plan('Create raster logo concepts and illustrated icons. no image generation.')
        self.assertNotIn('imagegen', self.lanes(denied)['logo']['skill_ids'])

    def test_unknown_prompt_is_labeled_fallback_and_deterministic(self):
        first = self.plan('Make a pleasant page')
        self.assertEqual(first, self.plan('Make a pleasant page'))
        self.assertEqual(first['surfaces'][0]['basis'], 'inspect_existing_design')
        self.assertTrue(first['surfaces'][0]['fallback'])
        self.assertEqual(set(self.lanes(first)), {'direction', 'verification'})
        with self.assertRaises(ValueError):
            self.plan('  ')

    def test_no_surface_style_preset_and_context_first_route(self):
        plan = self.plan('Create a landing page with a key visual and a logo')
        self.assertTrue(all(s['direction'] == 'repository_context' for s in plan['surfaces']))
        self.assertEqual(plan['direction_mode']['mode'], 'inspect-context')
        self.assertEqual(plan['authoring_context']['visual_quality'], 'unverified')
        direct = self.plan('Create one direction for our reading dashboard without comparison')
        self.assertEqual(direct['direction_mode']['mode'], 'direct')
        self.assertEqual(direct['workflow']['approval_event'], 'admit-direct')
        self.assertEqual(self.plan('Create cinematic key art')['surfaces'][0]['direction'], 'cinematic')

    def test_real_registry_korean_campaign_brief_and_normal_cli(self):
        prompt = '일본 모바일 RPG 캠페인의 시네마틱 키아트와 대담한 전용 로고, 항구 인장 아이콘, 수집용 승선증을 이미지로 생성하고 한일 폰트를 정해줘. Figma 원본 그대로 웹으로 옮겨줘. Figma MCP 없이.'
        result = router.route(prompt)
        surfaces = {s['surface']: s for s in result['surfaces']}
        self.assertEqual(surfaces['key_visual']['cues'], ['cinematic'])
        self.assertEqual(surfaces['lettering']['cues'], ['graphic'])
        self.assertEqual(surfaces['collectible']['direction'], 'illustrated_collectible')
        self.assertEqual(surfaces['seal']['direction'], 'repository_context')
        self.assertEqual(self.lanes(result)['icons']['asset_scopes'], ['seal'])
        self.assertNotIn('lettering', self.lanes(result)['images']['asset_scopes'])
        self.assertEqual(result['constraints']['locales'], ['KR', 'JP'])
        cli = subprocess.run([sys.executable, str(TOOL), '--prompt', prompt], text=True, capture_output=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout), result)
        for lane in result['routes']:
            self.assertTrue(lane['resources'])

    def test_current_generation_denial_overrides_context_and_keeps_ssot(self):
        context = 'cinematic key art 이미지 생성. Figma SSOT 원본 그대로 웹 구현. MCP 없이.'
        result = router.route('이번에는 생성하지 말고 기존 원화로 구현해줘.', context=context)
        self.assertEqual(result['constraints']['image_generation'], 'excluded')
        images = self.lanes(result)['images']
        self.assertNotIn('imagegen', images['skill_ids'])
        self.assertTrue(images['actions'][0].startswith('reuse_or_download:'))
        self.assertTrue(any(g['id'] == 'figma_ssot_before_web_writes' for g in result['gates']))
        continued = router.route('모두. 프롬프트에 따라 자동라우팅', context=context)
        self.assertIn('figma', self.lanes(continued))
        self.assertTrue(any(g['id'] == 'figma_ssot_before_web_writes' for g in continued['gates']))

    def test_current_recommendation_goal_overrides_prior_creation(self):
        context = 'cinematic KV와 로고 이미지 생성하고 Figma SSOT 웹으로 구현해줘.'
        for prompt in ('권위있는 스킬 추천/조사해봐', '권위있는 스킬 추천', '추천해줘', '조사해봐'):
            with self.subTest(prompt=prompt):
                result = router.route(prompt, context=context)
                self.assertEqual(result['mode'], 'research')
                self.assertTrue(all(r['status'] == 'recommended' for r in result['routes']))
                self.assertTrue(all('do not dispatch' in r['actions'][0] for r in result['routes']))

    def test_generation_save_and_download_are_independent_tasks(self):
        result = router.route('키아트 이미지 생성 + 이미지 저장. 참고 이미지 다운로드도 해줘.')
        images = self.lanes(result)['images']
        self.assertIn('imagegen', images['skill_ids'])
        for action in ('generate:', 'save_image:', 'reuse_or_download:'):
            self.assertTrue(any(a.startswith(action) for a in images['actions']))
        reuse = router.route('이미지 다운로드만. 생성하지 말고 기존 원화 유지.')
        self.assertNotIn('imagegen', self.lanes(reuse)['images']['skill_ids'])

    def test_additional_multilingual_asset_terms(self):
        for prompt in ('key art and collectible boarding pass', '키 비주얼, 티켓, 패스, 인장', 'キービジュアル、乗船証、スタンプ'):
            with self.subTest(prompt=prompt):
                result = router.route(prompt)
                surfaces = {s['surface'] for s in result['surfaces']}
                self.assertIn('key_visual', surfaces)
                self.assertIn('collectible', surfaces)

    def test_explicit_logo_as_image_uses_identity_and_imagegen(self):
        for text, key in [('게임 로고를 이미지로 만들어줘', 'logo'), ('아이콘을 이미지로 생성해줘', 'icons')]:
            route = self.lanes(self.plan(text))[key]
            self.assertIn('imagegen', route['skill_ids'])
            self.assertIn('campaign-identity', route['skill_ids'])

    def test_local_transport_does_not_exclude_logo_generation(self):
        plan = self.plan('로고 이미지를 생성하되 MCP 없이 해줘')
        self.assertIn('imagegen', self.lanes(plan)['logo']['skill_ids'])
        self.assertIn('images', self.lanes(plan))
        self.assertFalse(plan['constraints']['figma_mcp_allowed'])
        kept = self.plan('기존 로고만 유지하고 다른 이미지 생성하지 말고 일본어 폰트만 검토해줘')
        self.assertNotIn('logo', self.lanes(kept))

    def test_registry_validation_and_cli_fresh_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / 'routes.json'
            data.write_text(json.dumps(registry()), encoding='utf-8')
            prompt = root / 'prompt.txt'
            prompt.write_text('한국 출시 캠페인 로고만', encoding='utf-8')
            out = root / 'out'
            command = [sys.executable, str(TOOL), '--registry', str(data), '--prompt-file', str(prompt), '--out', str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(result.stdout)
            self.assertEqual(actual, json.loads((out / 'route-plan.json').read_text(encoding='utf-8')))
            self.assertTrue((out / 'campaign-prelaunch-KR.json').is_file())
            self.assertEqual(json.loads((out / 'campaign-prelaunch-KR.json').read_text())['status'], 'untested')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            for mutate in (lambda d: d.update(version=True), lambda d: d['lanes'].pop(), lambda d: d['lanes'][0].update(resources=['missing']), lambda d: d['resources'][0].update(role='')):
                broken = copy.deepcopy(registry())
                mutate(broken)
                data.write_text(json.dumps(broken), encoding='utf-8')
                with self.assertRaises(ValueError):
                    router.load_registry(data)


if __name__ == '__main__':
    unittest.main()
