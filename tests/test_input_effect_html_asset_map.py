"""Opt-in HTML asset maps bind captured same-origin bytes to local fresh sources."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import input_effect


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class HtmlAssetMapTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        app = root / 'app'
        (root / 'captures').mkdir()
        (app / '.next/static/css').mkdir(parents=True)
        (app / '.next/static/media').mkdir(parents=True)
        (app / 'public/images').mkdir(parents=True)
        html = b'''<!doctype html><html><head><title>Bound asset fixture</title>
<link rel="stylesheet" href="/_next/static/css/main.css?build=a">
<link rel="preload" href="/_next/static/media/preload.woff2?hash=preload" as="font">
</head><body><img src="/_next/image?url=%2Fimages%2Fhero.png&w=640&q=75">
<picture><source type="image/png" srcset="/images/hero.png?w=320 1x, /images/hero.png?w=640 2x"></picture>
<svg><image href="/images/icon.svg"></image></svg>
<style>.hero{background-image:url('/images/panel.webp')}</style>
<p style="background-image:url('/_next/static/media/inline.woff2?hash=inline')">Content</p>
</body></html>'''
        html_path = root / 'page.html'
        html_path.write_bytes(html)
        app_files = {
            '.next/static/css/main.css': b"@font-face{src:url('/_next/static/media/body.woff2?hash=body')}\n.card{background:url('/images/card.png')}",
            '.next/static/media/preload.woff2': b'preload-font-bytes',
            '.next/static/media/body.woff2': b'body-font-bytes',
            '.next/static/media/inline.woff2': b'inline-font-bytes',
            'public/images/hero.png': b'original-hero-image',
            'public/images/icon.svg': b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>',
            'public/images/panel.webp': b'panel-image-bytes',
            'public/images/card.png': b'card-image-bytes',
        }
        for rel, raw in app_files.items():
            path = app / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        page_meta = {'url_requested':'http://127.0.0.1:8871/','url_final':'http://127.0.0.1:8871/',
            'http_status':200,'body_bytes':len(html),'body_sha256':sha(html)}
        page_capture = root / 'captures/page.json'
        page_capture.write_text(json.dumps(page_meta, indent=2)+'\n')
        entries = [
            ('/ _next/static/css/main.css?build=a'.replace('/ ', '/'), '.next/static/css/main.css', True),
            ('/_next/static/media/preload.woff2?hash=preload', '.next/static/media/preload.woff2', True),
            ('/_next/static/media/body.woff2?hash=body', '.next/static/media/body.woff2', True),
            ('/_next/static/media/inline.woff2?hash=inline', '.next/static/media/inline.woff2', True),
            ('/images/panel.webp', 'public/images/panel.webp', True),
            ('/images/card.png', 'public/images/card.png', True),
            ('/images/hero.png?w=320', 'public/images/hero.png', True),
            ('/images/hero.png?w=640', 'public/images/hero.png', True),
            ('/images/icon.svg', 'public/images/icon.svg', True),
            ('/_next/image?url=%2Fimages%2Fhero.png&w=640&q=75', 'public/images/hero.png', False),
        ]
        captures = {'schema':'test-http-asset-capture-v1','origin':'http://127.0.0.1:8871','external_assets_requested':0,'assets':[]}
        map_entries = []
        for index, (reference, local, same_bytes) in enumerate(entries):
            local_bytes = (app / local).read_bytes()
            response = local_bytes if same_bytes else b'next-optimized-body'
            captures['assets'].append({'reference':reference,'local_app_path':local,'http_status':200,
                'bytes':len(response),'response_sha256':sha(response),'local_sha256':sha(local_bytes),
                'bytes_match_local':same_bytes})
            row = {'id':f'asset-{index+1}','capture_path':'captures/assets.json','capture_sha256':'',
                'reference':reference,'request_target':reference,'local_app_path':local,
                'mapping':'byte-identical' if same_bytes else 'transformed'}
            if not same_bytes:
                row['reason']='Next image optimization changes the response bytes; this mapping identifies the pinned local original.'
            map_entries.append(row)
        asset_capture = root / 'captures/assets.json'
        asset_capture.write_text(json.dumps(captures, indent=2)+'\n')
        capture_hash = sha(asset_capture.read_bytes())
        for row in map_entries:
            row['capture_sha256'] = capture_hash
        manifest = {'schema':input_effect.HTML_ASSET_MAP_SCHEMA,
            'page_capture':{'metadata_path':'captures/page.json','metadata_sha256':sha(page_capture.read_bytes())},
            'local_root':'app','assets':map_entries}
        manifest_path = root / 'assets-map.json'
        manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
        brief_fact='An explicitly mapped captured asset is still a local source input.'
        (root/'brief.md').write_text(brief_fact+'\n')
        (root/'facts.json').write_text(json.dumps({'capture-policy':brief_fact})+'\n')
        (root/'authority.json').write_text(json.dumps({'facts':{
            'capture-policy':{'priority':['brief']},'screen-title':{'priority':['html']},
        }})+'\n')
        spec={'schema':input_effect.SCHEMA,'brief':'brief.md','facts':'facts.json','authority':'authority.json',
            'inputs':{'html':'page.html','html-asset-map':'assets-map.json'}}
        return temp, root, app, manifest, spec

    def test_manifest_projects_image_css_and_font_bindings_into_freshness_sources(self):
        temp, root, _app, _manifest, spec = self.fixture()
        with temp:
            record = input_effect.project(root, spec)
            self.assertEqual(record['schema'], 'figma-flow-input-effect-result-v4')
            assets = {asset['ref']:asset for asset in record['channels']['html']['assets']}
            for ref in (
                '/_next/static/css/main.css?build=a',
                '/_next/static/media/preload.woff2?hash=preload',
                '/_next/static/media/body.woff2?hash=body',
                '/_next/static/media/inline.woff2?hash=inline',
                '/images/panel.webp', '/images/card.png',
                '/images/hero.png?w=320','/images/hero.png?w=640','/images/icon.svg',
                '/_next/image?url=%2Fimages%2Fhero.png&w=640&q=75',
            ):
                self.assertEqual(assets[ref]['status'], 'present', ref)
                self.assertIn('binding_id', assets[ref])
                self.assertEqual(assets[ref]['request_target'], ref)
            transformed = assets['/_next/image?url=%2Fimages%2Fhero.png&w=640&q=75']
            self.assertEqual(transformed['mapping'], 'transformed')
            self.assertNotEqual(transformed['response_sha256'], transformed['source_sha256'])
            expected = {
                'assets-map.json','captures/page.json','captures/assets.json',
                'app/.next/static/css/main.css','app/.next/static/media/preload.woff2',
                'app/.next/static/media/body.woff2','app/.next/static/media/inline.woff2',
                'app/public/images/hero.png','app/public/images/panel.webp','app/public/images/card.png',
                'app/public/images/icon.svg',
            }
            self.assertTrue(expected.issubset({item['path'] for item in record['sources']}))
            self.assertEqual(input_effect.freshness(record, root)['status'], 'current')
            (root/'out').mkdir()
            result = input_effect.write_record(root, record, 'out/input-record.json')
            stored = json.loads(result.read_text())
            self.assertEqual(input_effect.summarize_input_record(stored)['sha256'], input_effect.summarize_input_record(record)['sha256'])
            (root/'app/.next/static/media/preload.woff2').write_bytes(b'replaced font')
            fresh = input_effect.freshness(record, root)
            self.assertEqual(fresh['status'], 'stale')
            self.assertIn('app/.next/static/media/preload.woff2', fresh['changed'])

    def test_default_path_keeps_root_absolute_rejected_and_remote_unverified(self):
        temp, root, _app, _manifest, spec = self.fixture()
        with temp:
            spec['inputs'].pop('html-asset-map')
            record = input_effect.project(root, spec)
            assets = record['channels']['html']['assets']
            self.assertEqual(next(item for item in assets if item['ref']=='/images/panel.webp')['status'], 'rejected')
            self.assertEqual(input_effect._relative_asset(root/'page.html', root, 'https://other.example/a.png')['status'], 'external-unverified')

    def test_query_is_exact_and_unlisted_same_origin_request_is_not_inferred(self):
        temp, root, _app, manifest, spec = self.fixture()
        with temp:
            html_path = root/'page.html'
            html_path.write_bytes(html_path.read_bytes().replace(b'w=640',b'w=641'))
            page_meta = json.loads((root/'captures/page.json').read_text())
            page_meta['body_sha256'] = sha(html_path.read_bytes())
            page_meta['body_bytes'] = html_path.stat().st_size
            (root/'captures/page.json').write_text(json.dumps(page_meta,indent=2)+'\n')
            manifest['page_capture']['metadata_sha256'] = sha((root/'captures/page.json').read_bytes())
            (root/'assets-map.json').write_text(json.dumps(manifest,indent=2)+'\n')
            with self.assertRaisesRegex(ValueError, 'unused by static HTML/CSS'):
                input_effect.project(root, spec)

    def test_bad_origin_path_hash_duplicate_or_ambiguous_binding_is_rejected(self):
        mutations = ('origin', 'traversal', 'asset-traversal', 'source-hash', 'duplicate-capture-row', 'remote-reference', 'remote-next-image', 'missing-transform-reason')
        for mutation in mutations:
            temp, root, _app, manifest, spec = self.fixture()
            with temp, self.subTest(mutation=mutation):
                if mutation == 'origin':
                    report=json.loads((root/'captures/assets.json').read_text());report['origin']='https://remote.example'
                    (root/'captures/assets.json').write_text(json.dumps(report,indent=2)+'\n')
                    for row in manifest['assets']: row['capture_sha256']=sha((root/'captures/assets.json').read_bytes())
                elif mutation == 'traversal':
                    manifest['local_root']='../outside'
                elif mutation == 'asset-traversal':
                    manifest['assets'][0]['local_app_path']='../outside/secret.png'
                    report=json.loads((root/'captures/assets.json').read_text());report['assets'][0]['local_app_path']='../outside/secret.png'
                    (root/'captures/assets.json').write_text(json.dumps(report,indent=2)+'\n')
                    for row in manifest['assets']: row['capture_sha256']=sha((root/'captures/assets.json').read_bytes())
                elif mutation == 'source-hash':
                    manifest['assets'][0]['local_app_path']='.next/static/css/main.css'
                    (root/'app/.next/static/css/main.css').write_bytes(b'changed after capture')
                elif mutation == 'duplicate-capture-row':
                    report=json.loads((root/'captures/assets.json').read_text());report['assets'].append(copy.deepcopy(report['assets'][0]))
                    (root/'captures/assets.json').write_text(json.dumps(report,indent=2)+'\n')
                    for row in manifest['assets']: row['capture_sha256']=sha((root/'captures/assets.json').read_bytes())
                elif mutation == 'remote-reference':
                    manifest['assets'][0]['reference']='https://remote.example/image.png'
                    manifest['assets'][0]['request_target']='/image.png'
                elif mutation == 'remote-next-image':
                    manifest['assets'][0]['reference']='/_next/image?url=https%3A%2F%2Fremote.example%2Fimage.png&w=64'
                    manifest['assets'][0]['request_target']=manifest['assets'][0]['reference']
                elif mutation == 'missing-transform-reason':
                    manifest['assets'][-1].pop('reason')
                (root/'assets-map.json').write_text(json.dumps(manifest,indent=2)+'\n')
                with self.assertRaises(ValueError):
                    input_effect.project(root, spec)

    def test_legacy_v3_records_stay_fresh_and_external_urls_are_never_bound(self):
        temp, root, _app, manifest, spec = self.fixture()
        with temp:
            record=input_effect.project(root,spec)
            legacy=dict(record,schema='figma-flow-input-effect-result-v3')
            self.assertEqual(input_effect.freshness(legacy,root)['status'],'current')
            self.assertEqual(input_effect.summarize_input_record(legacy)['summary'],input_effect.summarize_input_record(record)['summary'])
            manifest['assets'].append({**manifest['assets'][0],'id':'remote','reference':'https://third.example/secret.png','request_target':'/secret.png'})
            (root/'assets-map.json').write_text(json.dumps(manifest,indent=2)+'\n')
            with self.assertRaises(ValueError):
                input_effect.project(root,spec)

    def test_capture_and_manifest_metadata_are_both_part_of_freshness(self):
        temp, root, _app, _manifest, spec = self.fixture()
        with temp:
            record=input_effect.project(root,spec)
            (root/'captures/assets.json').write_text((root/'captures/assets.json').read_text()+'\n')
            result=input_effect.freshness(record,root)
            self.assertEqual(result['status'],'stale')
            self.assertIn('captures/assets.json',result['changed'])


if __name__ == '__main__':
    unittest.main()
