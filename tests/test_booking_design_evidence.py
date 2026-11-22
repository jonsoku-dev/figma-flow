"""Reconcile the booking design handoff with its observed SSR inputs and projections."""
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/little-hands'
DESIGN = APP / 'design'


def read(name):
    return json.loads((DESIGN / name).read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class BookingDesignEvidenceTests(unittest.TestCase):
    def test_every_capture_has_a_reproducible_inert_snapshot_and_review_link(self):
        spec = importlib.util.spec_from_file_location('booking_design_source', DESIGN / 'source.py')
        source = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source)
        baseline = read('snapshot-baseline-r5.json')['snapshots']
        plan = read('capture-plan.json')
        pairs = {('state-'+row['id'], view) for row in plan['screens'] for view in ('desktop','mobile')}
        self.assertEqual({(row['state'],row['viewport']) for row in baseline}, pairs)
        self.assertEqual(len(baseline), len(pairs))
        linked = {attrs.get('href') for tag, attrs in Tags((DESIGN/'visual-review.html').read_text()).tags if tag=='a'}
        self.assertEqual({row['path'] for row in baseline}, {p for p in linked if p and p.startswith('snapshots/')})
        pins = read('input-pins.json')
        for row in pins['source'] + pins['captures']:
            self.assertEqual(digest(DESIGN / row['path']), row['sha256'], row['path'])
        self.assertEqual({row['path'] for row in pins['captures']},{row['capture'] for row in baseline})
        for row in baseline:
            capture = read(row['capture'])
            html = (DESIGN / row['path']).read_text(encoding='utf8')
            self.assertEqual((capture['state'],capture['viewport'],capture['route']),
                             (row['state'],row['css_viewport'],row['route']))
            self.assertEqual(digest(DESIGN / row['capture']), row['capture_sha256'])
            self.assertEqual(digest(DESIGN / row['path']), row['html_sha256'])
            self.assertEqual(html, source.snapshot_html(capture['html']))
            for tag, attrs in Tags(html).tags:
                self.assertNotEqual(tag, 'script')
                if tag == 'form':
                    self.assertIn('inert', attrs)
                    self.assertNotIn('action', attrs)
                if tag == 'link' and attrs.get('rel')=='stylesheet':
                    self.assertTrue((DESIGN / row['path']).parent.joinpath(attrs['href']).is_file())

    def test_review_images_pair_to_the_recorded_screen_viewport_and_capture(self):
        images = read('visual-review-images/index.json')
        snapshots = {(r['state'],r['viewport']):r for r in read('snapshot-baseline-r5.json')['snapshots']}
        self.assertEqual(set(snapshots), {(r['state'],r['viewport']) for r in images['records']})
        shipped = {f.relative_to(DESIGN).as_posix() for d in ('visual-review-images','previews') for f in (DESIGN/d).glob('*.jpg')}
        self.assertEqual(shipped,{r['path'] for r in images['records']+images['supplemental']['images']})
        for row in images['records'] + images['supplemental']['images']:
            shot = DESIGN / row['path']
            state = snapshots[row['state'],row['viewport']]
            if 'observed' in row:
                self.assertTrue(row['observed']['inert'])
                self.assertEqual(row['capture_sha256'], state['capture_sha256'])
                self.assertEqual(row['html_sha256'], state['html_sha256'])
                self.assertEqual(row['observed']['width'],state['css_viewport']['width'])
            else:
                self.assertIn(row['framing'], ('entry','bottom'))
                self.assertGreater(len(row['witness']),20)
            self.assertEqual(digest(shot),row.get('image_sha256',row.get('sha256')))
            with Image.open(shot) as image:
                self.assertEqual(image.format,'JPEG')
                self.assertEqual(list(image.size),row.get('image_pixels',row.get('pixels')))
                histogram = image.convert('L').histogram()
                self.assertGreater(sum(histogram[:100]), 100, f'Missing dark foreground in {shot.name}')
                self.assertGreater(sum(histogram[200:]), 100, f'Missing paper background in {shot.name}')

    def test_archived_revision_comparisons_match_the_two_historical_rosters(self):
        for left, right in (('r2','r3'),('r3','r4')):
            def inventory(version):
                return {(r['state'],r['viewport']):r for r in read(f'snapshot-baseline-{version}.json')['snapshots']}
            before, after = inventory(left),inventory(right)
            report = read(f'snapshot-comparison-{left}-{right}.json')
            seen = set()
            for status in ('changed','unchanged'):
                self.assertEqual(report[status+'_count'], len(report[status]))
                for row in report[status]:
                    key = row['state'],row['viewport']
                    self.assertNotIn(key,seen)
                    seen.add(key)
                    for field in ('capture','html'):
                        old,new = before[key][field+'_sha256'],after[key][field+'_sha256']
                        self.assertEqual((old,new),(row['previous_'+field+'_sha256'],row['current_'+field+'_sha256']))
                        self.assertEqual(old==new,row[field+'_unchanged'])
                    self.assertEqual(status=='unchanged',row['capture_unchanged'] and row['html_unchanged'])
            self.assertEqual(seen,set(before))
            self.assertEqual(seen,set(after))

    def test_source_assets_retain_the_photo_and_metric_font_provenance(self):
        static = APP/'static/littlehands'
        assets = json.loads((static/'sources.json').read_bytes())
        shipped = [p for p in (DESIGN/'source_assets').rglob('*') if p.is_file()]
        for key in ('photo','font'):
            entry=assets[key]
            self.assertEqual(digest(static/entry['path']),entry['sha256'])
            self.assertTrue(any(digest(file)==entry['sha256'] for file in shipped))
        with Image.open(static/assets['photo']['path']) as im:
            self.assertEqual(list(im.size), assets['photo']['dimensions'])
        license_data=(static/assets['font']['license_path']).read_bytes()
        self.assertIn(b'SIL OPEN FONT LICENSE',license_data)
        self.assertTrue(any(file.read_bytes()==license_data for file in shipped))
        self.assertEqual(read('fonts/provenance.json')['source_sha256'],assets['font']['sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)
            dest=app/'design'
            (dest/'fonts').mkdir(parents=True)
            (app/'static').symlink_to(APP/'static',target_is_directory=True)
            for name in ('tokens.json','prepare_fonts.py'):
                shutil.copyfile(DESIGN/name,dest/name)
            subprocess.run([sys.executable,'-B',str(dest/'prepare_fonts.py')],check=True,capture_output=True,timeout=60)
            for name in ('fonts/provenance.json','fonts/sources.json'):
                self.assertEqual((dest/name).read_bytes(),(DESIGN/name).read_bytes())
            from fontTools.ttLib import TTFont
            faces=read('fonts/sources.json')
            for role in read('tokens.json')['fonts'].values():
                face=faces[role['family']]['styles'][role['native_style']]
                with TTFont(dest/face['file']) as font:
                    self.assertEqual(font['OS/2'].usWeightClass,role['weight'])
                    self.assertNotIn('fvar',font)


    def test_authored_candidate_preserves_brief_assets_and_observation_scope(self):
        product = json.loads((APP/'booking/product.json').read_bytes())
        brief = (DESIGN/'brief.md').read_text()
        research = (DESIGN/'research.md').read_text()
        content = read('content.json')
        template_text = '\n'.join(f.read_text() for f in (APP/'templates').rglob('*.html'))
        self.assertIn('{{copy.paymentDisclosure}}', (DESIGN/'session-detail.html.in').read_text())
        subprocess.run([sys.executable,'-B',DESIGN/'publish_copy.py'],cwd=APP,check=True)
        self.assertIn('{% booking_brand %}', template_text)
        self.assertEqual(content['product'], product['serviceName'])
        self.assertEqual(set(content['required_text']),set(product.values()))
        facts = read('input-facts.json')
        for key,row in read('material-priority.json')['facts'].items():
            self.assertEqual(row['priority'],['brief'])
            self.assertIn(facts[key],brief)
        selection=read('candidate-spec.json')
        self.assertIn(selection['direct_instruction']['request_text'],brief)
        for anchor in selection['direct_instruction']['anchors']:
            self.assertEqual(anchor['artifact'],'brief')
            self.assertIn(anchor['excerpt'],brief)
        candidate,=selection['candidates']
        self.assertEqual(candidate['title'],product['serviceName'])
        self.assertEqual(read('native-layout.json')['content']['sha256'],digest(APP/selection['content']['path']))
        for key in ('source','review','graph'):
            self.assertTrue((APP/candidate[key]).is_file())
        for preview in candidate['previews']:
            with Image.open(APP/preview['path']) as image:
                self.assertEqual(image.size,(preview['width'],preview['height']))
            self.assertIn(str(preview['css_viewport']['width']),research)
        self.assertIn('Hahmlet',research)
        self.assertIn('작은손',brief)
        calibrations=read('calibration-headlines.json')['headlines']
        for row in calibrations:
            capture=read('captures/'+row['state'].removeprefix('state-')+'-'+row['viewport']+'.json')
            self.assertTrue(any(t['id']==row['id'] and t['value']==row['value'] for t in capture['texts']))
            self.assertTrue(row['scope'])
            self.assertIn('UNAPPLIED_proposed_tracking_allocation_w',row)


if __name__ == '__main__':
    unittest.main()
