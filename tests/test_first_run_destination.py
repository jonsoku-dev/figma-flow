"""Fresh creation scope: lower-cost drafts, no Dev Mode or generated approval."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from review_destination import resolve
from route_design import route


class FirstRunDestinationTests(unittest.TestCase):
    def test_new_campaign_and_tool_bans_take_design_canvas_branch(self):
        for brief in ('게임 신작 캠페인 페이지를 만들어줘', '게임 캠페인 시안 세 가지', '버튼에 주석 달린 예약 프로토타입 부탁해',
                      'Figma에서 Dev Mode 없이 캠페인 화면을 만들어줘',
                      'Figma MCP 없이 로컬에서 게임 캠페인 페이지를 만들어줘',
                      'Build a campaign website without Figma Dev Mode.'):
            with self.subTest(brief=brief):
                plan = route(brief)
                self.assertEqual(resolve(brief), 'figma')
                self.assertFalse(plan['constraints']['dev_mode_required'])
                gates = {g['id']:g for g in plan['gates']}
                self.assertIn('--review-destination figma', gates['human_direction_selection']['draft_cli'])
                self.assertEqual(gates['figma_direction_review']['status'],'required_before_selection')
                with self.assertRaises(ValueError):
                    resolve(brief, explicit='local')

    def test_explicit_web_only_preserved_and_conflicts_fail(self):
        brief = 'Figma 없이 로컬 HTML 화면만 만들어줘'
        self.assertEqual(resolve(brief,context='Figma 제작'), 'local')
        self.assertNotIn('figma_direction_review', {g['id'] for g in route(brief,context='Figma 제작')['gates']})
        with self.assertRaises(ValueError):
            resolve(brief,graph_requires=True)
        plan = route('게임 캠페인 디자인 자료 조사만')
        self.assertIsNone(plan['workflow'])
        self.assertIsNone(route('기존 캠페인 시안들을 검토해줘')['workflow'])
