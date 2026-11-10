"""Self-contained draft tests. Mocks/Pillow demos are never live Figma evidence."""
import importlib.util
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('figma_draft',ROOT/'tools/figma_draft.py')
draft=importlib.util.module_from_spec(spec);spec.loader.exec_module(draft)
EXAMPLE=ROOT/'examples/native-direction-review'
demo_spec=importlib.util.spec_from_file_location('native_review_demo',EXAMPLE/'demo.py')
demo=importlib.util.module_from_spec(demo_spec);demo_spec.loader.exec_module(demo)


def panel_script(html):
    script = re.search(r'<script>([\s\S]*)</script>', html).group(1)
    shared = (ROOT/'figma-bridge/panel_components.js').read_text()
    return shared + '\nconst PAIR = ' + script.split('const PAIR = ', 1)[1]


def file_hashes(folder):
    import hashlib
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()for p in folder.rglob('*')if p.is_file()and'__pycache__'not in p.parts}


class DraftReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.project=Path(cls.temp.name)/'workshop'
        cls.before=file_hashes(EXAMPLE)
        cls.result=demo.instantiate(cls.project)
        cls.manifest=Path(cls.result['manifest'])

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_default_is_native_pending_without_selection_or_foreign_context(self):
        data=json.loads(self.manifest.read_text())
        self.assertEqual(data['workflow_symbol'],'NATIVE_REVIEW_PENDING')
        self.assertEqual(data['review_destination'],'figma')
        self.assertEqual(data['native_target'],{'mode':'current-design-file'})
        self.assertNotIn('selection',data)
        self.assertFalse(any(self.project.rglob('*selection*.json')))
        self.assertEqual(self.before,file_hashes(EXAMPLE))

    def test_two_non_game_directions_have_exact_native_controls_and_returns(self):
        packet=draft.make_packet(self.manifest)
        self.assertEqual({c['id']for c in packet['candidates']},{'bulletin','agenda'})
        self.assertIsNone(packet['fileKey'])
        self.assertFalse(packet['production_admitted'])
        self.assertEqual(packet['execution_status'],'prepared-not-executed')
        self.assertEqual(packet['layout_sha256'],json.loads(self.manifest.read_text())['native_layout']['sha256'])
        count=0
        for c in packet['candidates']:
            self.assertNotIn(c['prototype']['states'][0]['view'],('reveal','pass','teaser'))
            for viewport,states in c['state_layouts'].items():
                for state_id,state in states.items():
                    self.assertTrue(any(l['kind']=='text'for l in state['layers']))
                    expected={e['control_id']for e in c['prototype']['bindings']if e['viewport']==viewport and e['source_state']==state_id}
                    self.assertEqual(set(state['control_boxes']),expected);count+=len(expected)
        self.assertEqual(count,8)

    def test_unused_named_color_stops_the_normal_cli_before_writing_a_draft(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / 'example'
            shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns('__pycache__'))
            spec_path = project / 'candidate-spec.json'
            spec = json.loads(spec_path.read_text())
            row = spec['candidates'][0]
            graph_path = project / row['graph']
            graph = json.loads(graph_path.read_text())
            color = next(r for r in graph['design_foundations']['roles'] if r['kind'] == 'color')
            role = dict(color, name='Unused duplicate', token='color/unplayed', alias='palette/unplayed')
            graph['design_foundations']['roles'].append(role)
            graph_path.write_text(json.dumps(graph))
            with (project / row['review']).open('a') as review:
                review.write('<p>' + ' '.join(str(v) for v in role.values()) + '</p>')
            layout_path = project / spec['native_layout']['path']
            layout = json.loads(layout_path.read_text())
            authored = next(c for c in layout['candidates'] if c['id'] == row['id'])
            authored['colors']['unplayed'] = role['value']
            authored['graph']['sha256'] = hashlib.sha256(graph_path.read_bytes()).hexdigest()
            layout_path.write_text(json.dumps(layout))
            spec['native_layout']['sha256'] = hashlib.sha256(layout_path.read_bytes()).hexdigest()
            spec_path.write_text(json.dumps(spec))
            output = project / 'new-review'
            result = subprocess.run([sys.executable, '-B', str(ROOT/'tools/design_actions.py'),
                'draft', '--project', str(project), '--brief', 'brief.md', '--research', 'research.md',
                '--from-existing', str(spec_path), '--out', str(output)], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('color/unplayed', json.loads(result.stderr)['blocked_reason'])
            self.assertFalse(output.exists())

    def test_panel_displays_packaged_candidates_and_escapes_review_context(self):
        review = {'candidates': [{'title': 'North <script>alert(1)</script>'}, {'title': 'South & Studio'}],
                  'fileKey': 'fictional-target', 'packet_sha256': 'abcdef1234567890'}
        pair = {'url': 'http://localhost/</script><script>unexpected()</script>', 'capability': 'fictional'}
        html = draft.ui_html(pair, review=review)
        self.assertIn('검토할 방향 2개', html)
        self.assertIn('North &lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('South &amp; Studio', html)
        self.assertIn('지정 Design 파일', html)
        self.assertIn('DRAFT · A/B/C 방향 검토 · abcdef12', html)
        self.assertNotIn('data-i18n="review.page"', html)
        self.assertEqual(html.count('id="workspace-locale"'), 1)
        self.assertNotIn('id="review-locale"', html)
        self.assertIn('data-i18n-aria="workspace.language"', html)
        self.assertNotIn('fictional-target', html)
        self.assertNotIn('만들어 보세요', html)
        self.assertEqual(html.count('<script>'), 1)
        self.assertEqual(html.count('</script>'), 1)
        self.assertEqual(json.loads(re.search(r'const PAIR = (.*);', html).group(1)), pair)

    def test_panel_exposes_task_hierarchy_theme_and_distinct_readback_states(self):
        html = draft.ui_html()
        self.assertIn('class="panel"', html)
        self.assertIn('class="panel-shell masthead"', html)
        self.assertEqual(html.count('id="workspace-tablist"'), 1)
        self.assertIn('class="panel-status status"', html)
        self.assertIn('role="status"', html)
        self.assertIn('class="primary" id="make"', html)
        self.assertIn('class="secondary" id="save" disabled', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('.figma-dark {', html)
        self.assertIn('color-scheme: dark', html)
        self.assertIn('background:var(--paper)', html)
        self.assertIn('themeColors:true', (ROOT/'figma-bridge/direction_review.js').read_text())
        harness = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const ids = ['make','save','status','status-panel','status-title','status-body','status-details','workspace-locale'];
const elements = Object.fromEntries(ids.map(id => [id, {dataset:{},disabled:id==='save',setAttribute(name,value){this[name]=value;},removeAttribute(name){delete this[name];},addEventListener(name,callback){this['on'+name]=callback;}}]));
const posts = []; let requests=0, reject=false, invalid=false;
const translations=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const locale=process.argv[4]; const listeners={};
const flow={locale,apply(){},t(key,params={}){return Object.entries(params).reduce((value,[name,replacement])=>value.replaceAll('{'+name+'}',replacement),translations[key][this.locale]);},setLocale(value){this.locale=value;for(const callback of listeners['flow:locale']||[])callback();}};
const expected=key=>translations['review.'+key][flow.locale];
const context = {FlowUI:flow,document:{documentElement:{dataset:{}},getElementById:id=>elements[id],querySelectorAll:()=>[]},window:{addEventListener:(name,callback)=>(listeners[name]??=[]).push(callback)},parent:{postMessage:m=>posts.push(m)},
  fetch:async()=>{requests++;if(reject)throw Error('offline');return {ok:!invalid,json:async()=>({passed:!invalid,errors:invalid?['synthetic invalid geometry']:[]})};}};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'),context);
const receive = m=>context.window.onmessage({data:{pluginMessage:m}});
(async()=>{
  elements.make.onclick();
  assert.equal(elements.make.disabled,true);
  assert.equal(elements['status-panel'].dataset.state,'busy');
  assert.equal(elements.make.textContent,expected('makeBusy'));
  assert.equal(elements.make['aria-label'],expected('makeBusy'));
  assert.equal(elements['status-body'].textContent,expected('creatingBody'));
  flow.setLocale(locale==='ko'?'en':'ko');
  assert.equal(elements['status-title'].textContent,expected('creatingTitle'));
  flow.setLocale(locale);
  await receive({type:'status',busy:false,state:'error',message:'synthetic generation error'});
  assert.equal(elements['status-panel'].dataset.state,'error');
  assert.equal(elements['status-title'].textContent,expected('generationFailed'));
  elements.make.onclick();
  await receive({type:'readback',data:{nodes:[]}});
  await receive({type:'status',busy:false,state:'success',message:'done'});
  assert.equal(elements['status-panel'].dataset.state,'success');
  assert.equal(elements.make.disabled,false);
  assert.equal(elements.save.disabled,false);
  assert.equal(elements.save.className,'primary');
  assert.equal(elements.make.className,'secondary');
  if(process.argv[2]==='paired'){
    assert.equal(requests,1);
    assert.equal(elements['status-title'].textContent,expected('verifiedTitle'));
    assert.equal(elements['status-body'].textContent,expected('verifiedBody'));
    invalid=true;elements.make.onclick();
    await receive({type:'readback',data:{nodes:[]}});
    await receive({type:'status',busy:false,state:'error',message:'verification failed'});
    assert.equal(elements['status-title'].textContent,expected('rejectedTitle'));
    assert(elements.status.textContent.includes('synthetic invalid geometry'));
    assert.equal(elements['status-body'].textContent,expected('rejectedBody'));
    assert.equal(elements['status-details'].hidden,false);
    invalid=false;reject=true;elements.make.onclick();
    await receive({type:'readback',data:{nodes:[]}});
    await receive({type:'status',busy:false,state:'success',message:'done'});
    assert.equal(elements['status-title'].textContent,expected('deliveryTitle'));
    assert.equal(elements['status-panel'].dataset.state,'error');
    assert.equal(elements.save.disabled,false);
  }else{
    assert.equal(requests,0);
    assert.equal(elements['status-title'].textContent,expected('readTitle'));
    assert.equal(elements['status-body'].textContent,expected('readBody'));
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        with tempfile.TemporaryDirectory() as folder:
            for label, pair in [('portable', None), ('paired', {'url':'http://localhost/synthetic','capability':'fictional-fixture'})]:
                for locale in ('ko', 'en', 'ja'):
                    with self.subTest(mode=label, locale=locale):
                        script=Path(folder)/'panel.js'
                        script.write_text(panel_script(draft.ui_html(pair)))
                        result=subprocess.run(['node','-e',harness,str(script),label,str(ROOT/'figma-bridge/locales/review.json'),locale],capture_output=True,text=True)
                        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_reference_thumbnails_use_only_bounded_packet_pngs(self):
        from io import BytesIO
        from PIL import Image
        packet = draft.make_packet(self.manifest)
        html = draft.ui_html(review=packet)
        images = re.findall(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', html)
        self.assertEqual(len(images), sum(len(c['references']) for c in packet['candidates']))
        for encoded in images:
            raw = draft.base64.b64decode(encoded, validate=True)
            self.assertLessEqual(len(raw), 256_000)
            with Image.open(BytesIO(raw)) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertLessEqual(image.width, 640)
                self.assertLessEqual(image.height, 360)
        self.assertNotRegex(html, r'<img[^>]+src="https?://')
        for candidate in packet['candidates']:
            self.assertIn(escape(candidate['title']), html)
        invalid = {'schema': packet['schema'], 'candidates': [{'title': '<unsafe "name">',
                   'references': {'desktop': 'missing', 'mobile': 'invalid'}}], 'assets': {'invalid': 'https://invalid.example/image.png'}}
        html = draft.ui_html(review=invalid)
        self.assertNotIn('<img', html)
        self.assertIn('검증된 참고 이미지를 표시할 수 없습니다.', html)
        self.assertIn('&lt;unsafe &quot;name&quot;&gt;', html)
        self.assertNotIn('https://invalid.example', html)

    def test_complete_generated_runtime_localizes_snapshots_and_accessible_names(self):
        from html.parser import HTMLParser

        class PanelElements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.elements = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'html' or 'id' in attrs or any(key.startswith('data-i18n') for key in attrs) or 'data-preview-label' in attrs:
                    self.elements.append({'tag': tag, 'attrs': attrs})

        packet = draft.make_packet(self.manifest)
        html = draft.ui_html({'url': 'http://localhost/synthetic', 'capability': 'fixture'}, review=packet)
        parser = PanelElements()
        parser.feed(html)
        from plugin_panel import panel_messages
        catalog = panel_messages('review')
        for key, values in catalog.items():
            self.assertEqual(set(values), {'ko', 'en', 'ja'}, key)
            parameters = [set(re.findall(r'\{(\w+)\}', value)) for value in values.values()]
            self.assertTrue(all(value.strip() for value in values.values()), key)
            self.assertEqual(parameters[0], parameters[1], key)
            self.assertEqual(parameters[1], parameters[2], key)
        for element in parser.elements:
            for attribute, key in element['attrs'].items():
                if attribute in ('data-i18n', 'data-i18n-aria', 'data-i18n-alt', 'data-i18n-title', 'data-i18n-placeholder'):
                    self.assertIn(key, catalog)
        harness = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const listeners={};
const nodes=source.map(({tag,attrs})=>({tag,attrs,dataset:Object.fromEntries(Object.entries(attrs).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()),v])),
  disabled:'disabled' in attrs,textContent:'',setAttribute(key,value){this.attrs[key]=value;},getAttribute(key){return this.attrs[key];},removeAttribute(key){delete this.attrs[key];},addEventListener(name,callback){this['on'+name]=callback;}}));
const ids=Object.fromEntries(nodes.filter(n=>n.attrs.id).map(n=>[n.attrs.id,n]));
const doc={documentElement:nodes.find(n=>n.tag==='html'),getElementById:id=>ids[id],querySelectorAll:selector=>nodes.filter(n=>selector.slice(1,-1) in n.attrs)};
const inherited=process.argv[3]||'';
if(inherited) doc.documentElement.dataset.flowLocale=inherited;
let invalid=false,offline=false;
const context={document:doc,navigator:{language:'en-US'},window:{addEventListener:(name,callback)=>(listeners[name]??=[]).push(callback),dispatchEvent:event=>(listeners[event.type]||[]).forEach(callback=>callback(event))},CustomEvent:class{constructor(type,init){this.type=type;this.detail=init.detail;}},
  parent:{postMessage(){}},fetch:async()=>{if(offline)throw Error('raw offline diagnostic');return {ok:!invalid,json:async()=>({passed:!invalid,errors:invalid?['raw invalid diagnostic']:[]})};}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const receive=m=>context.window.onmessage({data:{pluginMessage:m}});
const snapshots={ko:{make:'검토 시안 만들기',busy:'검토 시안 생성 중',verified:'읽기 결과 검증 완료',rejected:'읽기 결과 검증 실패',delivery:'로컬 결과 전달 실패',language:'언어'},en:{make:'Create review drafts',busy:'Creating review drafts',verified:'Readback validated',rejected:'Readback validation failed',delivery:'Local delivery failed',language:'Language'},ja:{make:'レビュー用の案を作成',busy:'レビュー用の案を作成中',verified:'読み取り結果の検証が完了',rejected:'読み取り結果の検証に失敗',delivery:'ローカルへの結果の送信に失敗',language:'言語'}};
(async()=>{
  assert.equal(context.FlowUI.locale,inherited||'en');
  for(const locale of ['ko','en','ja']){
    context.FlowUI.setLocale(locale);
    const expected=snapshots[locale];
    assert.equal(doc.documentElement.lang,locale);
    assert.equal(ids['workspace-locale'].attrs['aria-label'],expected.language);
    assert.equal(ids.make.textContent,expected.make);
    assert.equal(ids.make.attrs['aria-label'],expected.make);
    ids.make.onclick();
    assert.equal(ids['status-title'].textContent,expected.busy);
    await receive({type:'status',busy:true,message:'raw internal progress'});
    assert(!ids['status-body'].textContent.includes('raw internal progress'));
    assert(ids.status.textContent.includes('raw internal progress'));
    await receive({type:'readback',data:{nodes:[]}});
    await receive({type:'status',busy:false,state:'success',message:'raw success'});
    assert.equal(ids['status-title'].textContent,expected.verified);
    invalid=true;ids.make.onclick();await receive({type:'readback',data:{nodes:[]}});
    assert.equal(ids['status-title'].textContent,expected.rejected);
    assert(ids.status.textContent.includes('raw invalid diagnostic'));
    assert.equal(ids['status-details'].hidden,false);
    assert(!ids['status-body'].textContent.includes('raw invalid diagnostic'));
    invalid=false;offline=true;ids.make.onclick();await receive({type:'readback',data:{nodes:[]}});
    assert.equal(ids['status-title'].textContent,expected.delivery);
    assert.equal(ids.save.disabled,false);
    await receive({type:'status',busy:false,state:'success',message:'raw completion'});
    offline=false;
    nodes.filter(n=>'data-preview-viewport' in n.attrs).forEach(image=>{
      context.FlowUI.apply();
      const viewport={ko:{desktop:'데스크톱',mobile:'모바일'},en:{desktop:'Desktop',mobile:'Mobile'},ja:{desktop:'デスクトップ',mobile:'モバイル'}}[locale][image.dataset.previewViewport];
      assert(image.attrs.alt.includes(image.dataset.previewName));
      assert(image.attrs.alt.includes(viewport),image.attrs.alt);
      assert(!image.attrs.alt.includes('{'));
      if(locale!=='ko') assert(!/데스크톱|모바일/.test(image.attrs.alt),image.attrs.alt);
    });
    nodes.filter(n=>'data-i18n' in n.attrs).forEach(n=>assert(!n.textContent.includes('{'),n.textContent));
    assert(!ids['status-title'].textContent.startsWith('review.'));
  }
  ids['workspace-locale'].value='en';ids['workspace-locale'].onchange();assert.equal(context.FlowUI.locale,'en');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder)/'runtime.js'
            elements = Path(folder)/'elements.json'
            script.write_text(re.search(r'<script>([\s\S]*)</script>', html).group(1))
            elements.write_text(json.dumps(parser.elements))
            for inherited in ('', 'ja'):
                with self.subTest(inherited_locale=inherited):
                    result = subprocess.run(['node', '-e', harness, str(script), str(elements), inherited], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generic_portable_package_never_registers_or_approves(self):
        output=self.project/'portable'
        with patch.object(draft,'PRIVATE',self.project/'forbidden-private'):
            result=draft.prepare(self.manifest,output,plugin_id='1000000000000000001')
        self.assertEqual(result['status'],'prepared-not-executed')
        self.assertEqual(result['warnings'], [])
        self.assertFalse((self.project/'forbidden-private').exists())
        packaged=json.loads((output/'plugin/manifest.json').read_text())
        self.assertEqual(packaged['id'],'1000000000000000001')
        self.assertNotIn('NIGHT',packaged['name'])
        panel=(output/'plugin/ui.html').read_text()
        packet=json.loads((output/'packet.json').read_text())
        self.assertIn(f"검토할 방향 {len(packet['candidates'])}개",panel)
        for candidate in packet['candidates']:
            self.assertIn(candidate['title'],panel)
        self.assertEqual(json.loads(self.manifest.read_text())['workflow_symbol'],'NATIVE_REVIEW_PENDING')
        self.assertFalse(any(self.project.rglob('*selection*.json')))
        subprocess.run(['node','--check',str(output/'plugin/code.js')],check=True,capture_output=True)

    def test_large_embedded_previews_warn_on_normal_cli_without_blocking(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            shutil.copytree(EXAMPLE, source)
            layout_path = source / 'native-layout.json'
            layout = json.loads(layout_path.read_text())
            for asset in layout['assets'].values():
                if 'desktop' in asset['path']:
                    path = source / asset['path']
                    with Image.open(path) as image:
                        image.copy().save(path, compress_level=0)
                    asset['sha256'] = demo.pin(path)
            demo.dump(layout_path, layout)
            with patch.object(demo, 'EXAMPLE', source):
                manifest = demo.instantiate(root / 'project')['manifest']
            out = root / 'prepared'
            command = [sys.executable, '-B', str(ROOT / 'tools/design_actions.py'), 'prepare-native-review',
                       '--manifest', str(manifest), '--plugin-id', '12345', '--out', str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            packet = json.loads((out / 'packet.json').read_text())
            size = sum(len(data) for data in packet['assets'].values())
            self.assertGreater(size, 4_000_000)
            warnings = json.loads(result.stdout)['warnings']
            self.assertIn(f'{size:,} base64 bytes', warnings[0])
            self.assertEqual(json.loads((out / 'prepared.json').read_text())['warnings'], warnings)
            self.assertTrue((out / 'Figma-Direction-Review.zip').is_file())

    def test_implicit_demo_registration_fails_before_side_effects(self):
        output=self.project/'must-not-exist'
        with patch.object(draft.design_directions,'admit_native_draft')as admission:
            with self.assertRaises(ValueError):draft.prepare(self.manifest,output,register=True)
            admission.assert_not_called()
        self.assertFalse(output.exists())

    def test_private_demo_needs_explicit_matching_owner_pins(self):
        for env, kwargs in [({}, {}),
                            ({'FIGMA_FLOW_NIGHT_FILE_KEY': 'owned', 'FIGMA_FLOW_NIGHT_PLUGIN_ID': '123'},
                             {'file_key': 'another'}),
                            ({'FIGMA_FLOW_NIGHT_FILE_KEY': 'owned', 'FIGMA_FLOW_NIGHT_PLUGIN_ID': '123'},
                             {'plugin_id': '456'})]:
            with self.subTest(kwargs=kwargs), patch.dict(os.environ, env, clear=True), patch.object(draft, 'make_packet') as make:
                with self.assertRaises(ValueError):
                    draft.prepare(self.manifest, self.project/'never-written', register=True, night_demo=True, **kwargs)
                make.assert_not_called()

    def test_wrong_owned_layout_is_rejected(self):
        with tempfile.NamedTemporaryFile(suffix='.json')as file:
            with self.assertRaises(ValueError):draft.make_packet(self.manifest,file.name)

    def test_ui_and_wrong_file_mock_do_not_author(self):
        with tempfile.TemporaryDirectory()as folder:
            script=Path(folder)/'ui.js';script.write_text(re.search(r'<script>([\s\S]*)</script>',draft.ui_html()).group(1));subprocess.run(['node','--check',str(script)],check=True,capture_output=True)
            code="""const fs=require('fs'),vm=require('vm'),assert=require('assert');const messages=[];let creates=0;const figma={fileKey:'wrong',ui:{postMessage:m=>messages.push(m)},showUI:()=>{},createPage:()=>{creates++;throw Error('must not create')}};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{DRAFT:{fileKey:'expected'},figma,__html__:''});(async()=>{await figma.ui.onmessage({type:'select-direction'});await figma.ui.onmessage({type:'draft-review'});assert.equal(creates,0);assert(messages.some(m=>m.message&&m.message.includes('Figma')));})();"""
            subprocess.run(['node','-e',code,str(ROOT/'figma-bridge/direction_review.js')],check=True,capture_output=True)


class CopiedPackageTests(unittest.TestCase):
    def test_installed_copy_needs_no_sibling_project(self):
        with tempfile.TemporaryDirectory()as folder:
            copied=Path(folder)/'plugin'
            shutil.copytree(ROOT,copied,ignore=shutil.ignore_patterns('__pycache__','.git'))
            self.assertEqual([p.name for p in Path(folder).iterdir()],['plugin'])
            result=subprocess.run([sys.executable,str(copied/'tests/test_figma_draft.py'),'DraftReviewTests'],cwd=copied,check=False,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('skipped',result.stderr)


class OptionalLiveReadbackTests(unittest.TestCase):
    """Opt-in operator evidence only; never a package/example prerequisite."""
    @unittest.skipUnless(os.getenv('FIGMA_DRAFT_LIVE_MANIFEST')and os.getenv('FIGMA_DRAFT_LIVE_READBACK'),'Optional operator evidence not supplied')
    def test_supplied_native_evidence_and_tampering(self):
        manifest=Path(os.environ['FIGMA_DRAFT_LIVE_MANIFEST']);current=Path(os.environ['FIGMA_DRAFT_LIVE_READBACK'])
        self.assertTrue(draft.verify_native_review(manifest,current)['passed'])
        for mutation in('reaction','design-link'):
            raw=json.loads(current.read_text())
            if mutation=='reaction':next(n for n in raw['nodes']if n.get('type')=='INSTANCE'and n.get('reactions'))['reactions'][0]['actions'][0]['destinationId']='missing-target'
            else:
                entry=next(iter(raw['noteFrames'].values()))['entries'][0]
                next(n for n in raw['nodes']if n['id']==entry['textNodeId'])['hyperlink']={'type':'NODE','value':'unrelated-target'}
            with self.subTest(mutation=mutation),tempfile.NamedTemporaryFile(suffix='.json',mode='w')as file:
                json.dump(raw,file);file.flush();self.assertFalse(draft.verify_native_review(manifest,file.name)['passed'])


if __name__=='__main__':unittest.main()
