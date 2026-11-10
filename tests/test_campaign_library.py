import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'tools/campaign_library.py'
spec = importlib.util.spec_from_file_location('campaign_library', TOOL)
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)


def fixture():
    return {'version': 1, 'captured_on': '2026-11-09',
            'categories': [{'id': 'beauty', 'name': '뷰티'}, {'id': 'food', 'name': '식품'}],
            'sources': [{'id': 'kr', 'title': '한국 캠페인', 'url': 'https://example.com/kr', 'market': 'KR', 'type': 'official', 'evidence': '공개 페이지', 'observed': '2026-11-09', 'categories': ['beauty']},
                        {'id': 'jp', 'title': '일본 캠페인', 'url': 'https://example.com/jp', 'market': 'JP', 'type': 'official', 'evidence': '공개 페이지', 'observed': '2026-11-09', 'categories': ['beauty', 'food']}],
            'patterns': [{'id': 'p1', 'title': '비교', 'category': 'beauty', 'source_ids': ['kr', 'jp'], 'observation': '관측한 구조', 'application': '제품에 적용', 'checks': ['키보드로 선택하고 상태 변화를 확인한다.'], 'limits': '성과 미검증'},
                         {'id': 'p2', 'title': '상세', 'category': 'food', 'source_ids': ['jp'], 'observation': '관측', 'application': '적용', 'checks': ['모바일에서 상세 내용을 읽을 수 있는지 확인한다.'], 'limits': '수동 검증 필요'}]}


class CampaignLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = fixture()
        self.path = self.root / 'library.json'
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(TOOL), '--data', str(self.path), *args], text=True, capture_output=True)

    def test_filters_and_source_joins(self):
        result = self.run_cli('list', '--market', 'KR', '--category', 'beauty')
        self.assertEqual(result.returncode, 0, result.stderr)
        selected = json.loads(result.stdout)
        self.assertEqual([s['id'] for s in selected['sources']], ['kr'])
        self.assertEqual([p['id'] for p in selected['patterns']], ['p1'])
        self.assertEqual(selected['patterns'][0]['source_ids'], ['kr'])
        self.assertEqual(library.select(self.data, 'food', 'KR')['patterns'], [])
        self.assertEqual(library.select(self.data, market='JP')['patterns'][0]['source_ids'], ['jp'])
        self.assertNotEqual(self.run_cli('list', '--category', 'unknown').returncode, 0)

    def test_plan_keeps_evidence_and_checks_untested(self):
        result = self.run_cli('plan', '--category', 'beauty', '--market', 'KR')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual((plan['status'], plan['verification']), ('untested', 'manual'))
        pattern = plan['patterns'][0]
        self.assertEqual(pattern['pattern_id'], 'p1')
        self.assertEqual(pattern['evidence'][0]['url'], 'https://example.com/kr')
        self.assertEqual(len(pattern['evidence']), 1)
        self.assertEqual(pattern['checks'][0]['status'], 'untested')
        self.assertEqual(pattern['checks'][0]['check'], self.data['patterns'][0]['checks'][0])

    def test_cross_category_analogy_is_labeled_and_not_plan_evidence(self):
        self.data['patterns'][1]['source_ids'] = ['kr']
        selected = library.select(self.data)
        self.assertEqual(selected['patterns'][1]['cross_category_analogy_source_ids'], ['kr'])
        self.assertIn('타 카테고리 유추', library.report(self.data))
        self.assertEqual(library.plan(self.data, 'food')['patterns'], [])
        direct = library.plan(self.data, 'beauty', 'KR')['patterns'][0]['evidence'][0]
        self.assertEqual(direct['relationship'], 'same_category_observation')
        self.assertIn('beauty', direct['source_categories'])

    def test_filtered_observation_preserves_full_original_provenance(self):
        self.data['patterns'][0]['observation'] = 'kr와 jp의 전체 사례를 종합했다.'
        self.data['sources'][1]['categories'] = ['food']
        pattern = library.plan(self.data, 'beauty', 'KR')['patterns'][0]
        self.assertEqual(pattern['observation'], self.data['patterns'][0]['observation'])
        self.assertEqual([s['source_id'] for s in pattern['evidence']], ['kr'])
        self.assertEqual(pattern['synthesis_scope'], {'filtered': False, 'category': 'beauty', 'source_ids': ['kr', 'jp'], 'markets': ['JP', 'KR']})
        support = {s['source_id']: s for s in pattern['supporting_sources']}
        self.assertEqual(set(support), {'kr', 'jp'})
        self.assertEqual(support['jp']['url'], 'https://example.com/jp')
        self.assertEqual(support['jp']['market'], 'JP')
        self.assertEqual(support['jp']['relationship'], 'cross_category_analogy')
        self.assertEqual(support['kr']['relationship'], 'same_category_observation')

    def test_validation_rejects_broken_schema_and_links(self):
        for mutate in (lambda d: d['sources'][0].update(url='javascript:alert(1)'),
                       lambda d: d['sources'][0].update(url='https://user:secret@example.com'),
                       lambda d: d['sources'][0].update(categories=['missing']),
                       lambda d: d['patterns'][0].update(source_ids=['missing']),
                       lambda d: d['categories'].append(d['categories'][0]),
                       lambda d: d.update(version=True),
                       lambda d: d['patterns'][0].update(checks=[])):
            with self.subTest(mutate=mutate):
                self.data = fixture()
                mutate(self.data)
                self.write()
                with self.assertRaises((ValueError, TypeError)):
                    library.load_library(self.path)

    def test_fresh_report_escapes_data_and_refuses_overwrite(self):
        hostile = '</script><script>alert("x")</script><img src=x onerror=alert(1)>'
        self.data['sources'][0]['title'] = hostile
        self.data['patterns'][0]['application'] = hostile
        self.data['sources'][0]['visual'] = [{'surface': '실제 브라우저', 'observations': [hostile, '모바일 화면 관측']}]
        self.write()
        out = self.root / 'catalog.html'
        result = self.run_cli('report', '--out', str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        content = out.read_text(encoding='utf-8')
        self.assertNotIn(hostile, content)
        self.assertIn('&lt;img', content)
        self.assertIn('\\u003c/script\\u003e', content)
        self.assertIn('Content-Security-Policy', content)
        self.assertIn('id="category"', content)
        self.assertIn('id="market"', content)
        self.assertIn('id="search"', content)
        self.assertIn('<details><summary>시각 관측 기록</summary><p>실제 브라우저</p>', content)
        self.assertIn('모바일 화면 관측</li>', content)
        self.assertIn('모바일게임 캠페인 레퍼런스', content)
        self.assertIn('https://example.com/kr', content)
        self.assertIn('전체 출처 2개 · 패턴 2개', content)
        embedded = content.split('<script id="catalog-data" type="application/json">')[1].split('</script>')[0]
        payload = json.loads(embedded)
        self.assertEqual(payload['plans']['beauty:KR'], library.plan(self.data, 'beauty', 'KR'))
        self.assertNotEqual(self.run_cli('report', '--out', str(out)).returncode, 0)
        self.assertEqual(out.read_text(encoding='utf-8'), content)
        link = self.root / 'symlink.html'
        link.symlink_to(out)
        self.assertNotEqual(self.run_cli('report', '--out', str(link)).returncode, 0)
        self.assertEqual(out.read_text(encoding='utf-8'), content)


if __name__ == '__main__':
    unittest.main()
