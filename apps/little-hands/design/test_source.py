import importlib.util
import unittest
import json
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent

def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

source=module('source')
export=module('export')

class SourceChecks(unittest.TestCase):
    def test_sanitizer_never_exports_secrets_or_live_form(self):
        value=export.sanitize('<html><body><form method="post" action="/reserve/"><input type="hidden" value="SECRET"><input type="password" value="SECRET"><script>SECRET</script><p>공개 문구</p><button type="submit">예약</button></form></body></html>')
        self.assertNotIn('SECRET',value)
        self.assertIn('<form inert data-export-only="true" method="post">',value)
        self.assertIn('data-export-only="true"',value)
        self.assertIn('<button type="button">예약</button>',value)
        self.assertIn('공개 문구',value)

    def test_gallery_namespaces_real_elements(self):
        parser=source.GalleryParser('state-login')
        parser.feed('<html><body><main id="main"><label for="username">계정</label><input id="username"><a data-native-key="nav-login" href="#main">로그인</a></main></body></html>')
        value=''.join(parser.output)
        self.assertIn('id="state-login-main"',value)
        self.assertIn('for="state-login-username"',value)
        self.assertIn('id="state-login-nav-login"',value)
        self.assertIn('href="#state-login-main"',value)

    def test_current_links_stay_static(self):
        self.assertIsNone(source.resolve_target('state-login',{'id':'control','href':'#main'}, {}, {}))
        self.assertEqual(source.resolve_target('state-mybookings',{'id':'control','href':'/staff/'}, {}, {}),'staffdashboard')
        self.assertIsNone(source.resolve_target('state-mybookings',{'id':'control','href':'/bookings/abc/reschedule/'}, {}, {}))
        captured={('state-reschedule','desktop'):({'route':'/bookings/abc/reschedule/'},None)}
        self.assertEqual(source.resolve_target('state-mybookings',{'id':'control','href':'/bookings/abc/reschedule/'},captured,{}),'reschedule')

    def test_error_recovery_keeps_observed_member_navigation_scope(self):
        capture={'controls':[{'native_key':'nav-bookings'}]}
        self.assertEqual(source.resolve_target('state-403',{'id':'recover','href':'/'},{('state-403','desktop'):(capture,None)},{}),'memberhome')
        capture={'controls':[{'native_key':'nav-login'}]}
        self.assertEqual(source.resolve_target('state-404',{'id':'recover','href':'/'},{('state-404','desktop'):(capture,None)},{}),'publichome')

    def test_actual_linear_children_become_auto_layout_without_moving_boxes(self):
        style={'fill':'rgb(142, 62, 40)','ink':'rgb(255, 253, 248)','stroke':'rgb(142, 62, 40)','stroke_width':1,'radius':0,'fontFamily':'Hahmlet','fontWeight':700,'fontSize':14,'leading':22.4,'letter_spacing':0,'padding':[11,22,11,22],'boxShadow':'none'}
        data={'viewport':{'width':390,'height':960},'document':{'height':960},'body_background':'rgb(246, 242, 233)','surfaces':[],'images':[],'texts':[],'controls':[{'id':'state-unit-one','selector':'#one','tag':'button','label':'첫 조작','style':style,'box':[24,40,100,48]},{'id':'state-unit-two','selector':'#two','tag':'button','label':'다음 조작','style':style,'box':[136,40,120,48]}],'containers':[{'id':'state-unit-actions','selector':'.actions','parent_selector':None,'box':[24,40,342,48],'classes':'actions','members':['state-unit-one','state-unit-two'],'css':{'display':'flex','flex_direction':'row','gap':12}}]}
        layout=source.layout_for(data,{'paper':'#f6f2e9'}, {}, {}, [])
        self.assertEqual(layout['containers'][0]['kind'],'auto-layout')
        self.assertEqual(layout['containers'][0]['layout']['gap'],12)
        self.assertEqual(layout['product_buttons']['state-unit-two']['box'],[136,40,120,48])
        variant=layout['product_buttons']['state-unit-one']['variant']
        style['fontSize']=13
        mobile=source.layout_for(data,{'paper':'#f6f2e9'}, {}, {}, [])
        self.assertEqual(mobile['product_buttons']['state-unit-one']['variant'],variant)
        data['controls'][1]['box']=[24,100,120,48]
        layout=source.layout_for(data,{'paper':'#f6f2e9'}, {}, {}, [])
        self.assertEqual(layout['containers'][0]['kind'],'frame')

    def test_transport_alias_requires_exact_prior_actual_selector(self):
        data={'texts':[{'id':'first','selector':'#same','style':{'fontSize':14}},{'id':'second','selector':'#same','style':'[Circular]'}]}
        source.restore_transport_aliases(data,Path('actual.json'))
        self.assertEqual(data['texts'][1]['style'],{'fontSize':14})
        self.assertEqual(data['_transport_alias_resolutions'][0]['actual_style_source'],'first')
        with self.assertRaises(ValueError):source.restore_transport_aliases({'texts':[{'id':'missing','selector':'#other','style':'[Circular]'}]},Path('actual.json'))

    def test_required_mark_merges_only_literal_same_style_actual_label(self):
        style={'fontFamily':'Hahmlet','fontWeight':700,'fontSize':14,'leading':25.2,'letter_spacing':0,'ink':'rgb(41, 39, 32)'}
        data={'html':'<label data-native-key="label-password">비밀번호<span> *</span></label>','texts':[{'id':'label','selector':'[data-native-key="label-password"]','value':'비밀번호','style':style,'box':[40,100,52,25.2]},{'id':'mark','selector':'label>span','value':'*','style':dict(style),'box':[92,100,13,25.2]}]}
        records=source.inline_label_records(data)
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['value'],'비밀번호 *')
        self.assertEqual(records[0]['box'],[40,100,65,25.2])
        data['html']=data['html'].replace(' *',' 필수')
        self.assertEqual(len(source.inline_label_records(data)),2)

    def test_line_boxes_use_observed_css_quantization_without_padding_height(self):
        data={'html':'<p>안내</p>','texts':[{'id':'line','selector':'#policy','value':'안내','box':[40,153,602,23.4],'style':{'leading':23.4},'content_box':[40,153,602,23.391],'text_context':{'block_content':True}}]}
        row=source.used_line_records(data)[0]
        self.assertEqual(row['box'],[40,153,602,23.391])
        self.assertEqual(row['style']['leading'],23.391)
        self.assertEqual(row['native_line_metrics']['computed_css_leading'],23.4)
        self.assertEqual(data['texts'][0]['box'][3],23.4)
        data['texts'][0]['content_box'][3]=60
        self.assertEqual(source.used_line_records(data)[0]['box'][3],23.4)

    def test_font_calibration_matches_only_exact_observed_native_case(self):
        text={'id':'native-case','value':'수업에서 만나요.','style':{'fontFamily':'Hahmlet','fontWeight':700,'fontSize':40,'leading':58,'letter_spacing':-1.2}}
        observed=source.observed_native_text(text)
        self.assertEqual(observed['node_id'],'5:3')
        self.assertEqual(observed['width'],276)
        text['style']['fontWeight']=400
        self.assertIsNone(source.observed_native_text(text))
        text['style']['fontWeight']=700;text['value']='다른 문자열'
        self.assertIsNone(source.observed_native_text(text))

    def test_actual_snapshot_declares_utf8_once_and_preserves_korean(self):
        capture=json.loads((HERE/'captures/publichome-desktop.json').read_text(encoding='utf-8'))
        exported=source.snapshot_html(capture['html'])
        self.assertIn(capture['title'],exported)
        self.assertIn('작은손 커피공방',exported)
        self.assertIn(b'<meta charset="utf-8">',exported.encode('utf-8')[:1024])
        self.assertEqual(len(re.findall(r'<meta\b[^>]*charset\s*=',exported,re.I)),1)
        self.assertEqual(source.snapshot_html(exported),exported)

    def test_shared_pair_ignores_labels_widths_and_ids_but_preserves_instances(self):
        base={'fill':'rust','ink':'cream','radius':0,'fontSize':14,'font':'display','leading':22.4,'letter_spacing':0,'paddingX':22,'paddingY':11,'minHeight':48,'maxWidth':100,'stroke':'rust','stroke_width':1}
        styles={'desktop':{'old-a':dict(base),'old-b':{**base,'maxWidth':220}},'mobile':{'old-a':{**base,'fontSize':13,'maxWidth':110},'old-b':{**base,'fontSize':13,'maxWidth':210}}}
        layouts={vp:{'state':{'product_buttons':{'control-a':{'box':[24,40,100,48],'variant':'old-a','label':'확인','specification_id':'action-a'},'control-b':{'box':[136,40,220,48],'variant':'old-b','label':'긴 문구를 가진 다른 행동','specification_id':'action-b'}}}} for vp in styles}
        nodes=[{'id':'action-a','type':'action','target_ids':['state-a'],'annotation':{'control_id':'control-a','visual_variant':'old-a'}},{'id':'action-b','type':'action','target_ids':[],'annotation':{'control_id':'control-b','visual_variant':'old-b'}}]
        samples=[{'variant':'old-a','component':'legacy-a','label':'확인','state':'state-a'}]
        before=json.loads(json.dumps(layouts));actions_before=json.loads(json.dumps(nodes))
        shared,renamed=source.share_control_styles(styles,layouts,nodes,samples)
        family=renamed['old-a']
        self.assertEqual(family,renamed['old-b'])
        self.assertTrue(family.startswith('Solid-'))
        self.assertEqual([len(shared[vp]) for vp in ('desktop','mobile')],[1,1])
        self.assertEqual(shared['desktop'][family]['maxWidth'],220)
        self.assertEqual(shared['mobile'][family]['maxWidth'],210)
        self.assertEqual(shared['desktop'][family]['fontSize'],14)
        self.assertEqual(shared['mobile'][family]['fontSize'],13)
        self.assertEqual(len({node['component_id'] for node in nodes}),1)
        self.assertEqual(samples[0]['component'],'component-'+family)
        for vp in layouts:
            for key,button in layouts[vp]['state']['product_buttons'].items():
                self.assertEqual({k:v for k,v in button.items() if k!='variant'},{k:v for k,v in before[vp]['state']['product_buttons'][key].items() if k!='variant'})
                self.assertEqual(button['variant'],family)
        self.assertEqual([node['target_ids'] for node in nodes],[node['target_ids'] for node in actions_before])
        renamed_ids={vp:{'different-id-'+str(index):style for index,style in enumerate(variants.values())} for vp,variants in styles.items()}
        again,other=source.share_control_styles(renamed_ids,{},[],[])
        self.assertEqual(set(other.values()),{family})
        self.assertEqual(styles['desktop']['old-a']['maxWidth'],100)

    def test_shared_pair_retains_paint_mobile_font_and_shadow_differences(self):
        base={'fill':None,'ink':'ink','radius':0,'fontSize':14,'font':'body','leading':25.2,'letter_spacing':0,'paddingX':0,'paddingY':0,'minHeight':44,'maxWidth':100}
        styles={'desktop':{'a':dict(base),'paint':{**base,'ink':'rust'},'mobile-font':dict(base),'shadow':{**base,'shadows':[{'x':0,'y':1,'blur':2,'spread':0,'color':'#000000','opacity':.2}]}},'mobile':{'a':{**base,'fontSize':13},'paint':{**base,'fontSize':13,'ink':'rust'},'mobile-font':dict(base),'shadow':{**base,'fontSize':13}}}
        shared,renamed=source.share_control_styles(styles,{},[],[])
        self.assertEqual(len(set(renamed.values())),4)
        self.assertEqual(len(shared['desktop']),4)
        self.assertTrue(all(name.startswith('Text-') for name in renamed.values()))
        self.assertIn('shadows',shared['desktop'][renamed['shadow']])

    def hero_case(self, name='publichome-desktop', key='hero-browse'):
        data=json.loads((HERE/'captures'/(name+'.json')).read_text())
        data['controls']=[control for control in data['controls'] if control.get('native_key')==key]
        for field in ('texts','images','surfaces','containers'):data[field]=[]
        return data

    def test_r6_brand_uses_exact_observed_control_allocation_and_keeps_css_box(self):
        for name,width in [('publichome-desktop',146),('publichome-mobile',126)]:
            data=self.hero_case(name,'brand');control=data['controls'][0];raw=list(control['box']);mapping=[]
            layout=source.layout_for(data,{'paper':'#f6f2e9'},{},{},mapping)
            self.assertEqual(layout['product_buttons'][control['id']]['box'],[raw[0],raw[1],width,raw[3]])
            item=next(row for row in mapping if row['kind']=='control')
            self.assertEqual(item['raw_css_box'],raw)
            self.assertEqual(item['native_allocation_delta']['width'],width-raw[2])
            self.assertEqual(item['native_text_calibration']['file'],'native-font-calibration-v2.json')
            self.assertEqual(control['box'],raw)

    def test_r6_hero_normalization_requires_actual_row_proof(self):
        data=self.hero_case();control=data['controls'][0];raw=control['label'];mapping=[]
        layout=source.layout_for(data,{'paper':'#f6f2e9'},{},{},mapping)
        button=layout['product_buttons'][control['id']]
        self.assertEqual(button['label'],'수업 일정 보기 ↓')
        self.assertEqual(button['box'],control['box'])
        item=next(row for row in mapping if row['kind']=='control')
        self.assertEqual(item['raw_label'],raw)
        self.assertEqual(item['label_normalization']['file'],'control-line-observation.json')
        self.assertEqual(control['label'],raw)
        data['html']=data['html'].replace('app.3539de012f0c.css','app.unobserved.css')
        with self.assertRaises(ValueError):source.layout_for(data,{'paper':'#f6f2e9'},{},{},[])
        data=self.hero_case();data['controls'][0]['native_key']='unobserved-control'
        with self.assertRaises(ValueError):source.layout_for(data,{'paper':'#f6f2e9'},{},{},[])

    def test_r6_calibration_keeps_both_authentic_sources_and_exact_weight(self):
        old={'id':'old','value':'수업에서 만나요.','style':{'fontFamily':'Hahmlet','fontWeight':700,'fontSize':40,'leading':58,'letter_spacing':-1.2}}
        self.assertEqual(source.observed_native_text(old)['file'],'native-font-calibration.json')
        new={'id':'new','value':'예정 수업 현황','style':{'fontFamily':'Hahmlet','fontWeight':700,'fontSize':26,'leading':39,'letter_spacing':-.6}}
        self.assertEqual(source.observed_native_text(new)['width'],155)
        self.assertEqual(source.observed_native_text(new)['file'],'native-font-calibration-v2.json')
        old['style']['fontWeight']=600
        self.assertIsNone(source.observed_native_text(old))
        new['style']['letter_spacing']=0
        self.assertIsNone(source.observed_native_text(new))

    def test_translucent_paint_is_not_silently_flattened(self):
        palette={}
        self.assertIsNone(source.color('rgba(0, 0, 0, 0)',palette))
        with self.assertRaises(ValueError):source.color('rgba(0, 0, 0, 0.2)',palette)
        self.assertEqual(source.color('rgb(41, 39, 32)',palette),'css-292720')


class FamilyTargetMappingTests(unittest.TestCase):
    def test_family_targets_remap_representative_forms_and_tables_without_changing_actions_or_styles(self):
        loaded = source.load_family_targets(HERE / 'family-targets.json')
        targets = loaded['targets']
        self.assertEqual(
            {entry['family'] for entry in targets},
            {'Field', 'Input', 'Checkbox', 'Radio', 'TableRow', 'TableCell'},
        )
        for state in ('sessionavailable', 'reschedule', 'staffedit', 'staffsessions'):
            for viewport in ('desktop', 'mobile'):
                cap = json.loads((HERE / 'captures' / f'{state}-{viewport}.json').read_text(encoding='utf-8'))
                p_plain, s_plain, a_plain, m_plain = {}, {}, {}, []
                plain = source.layout_for(cap, p_plain, s_plain, a_plain, m_plain, HERE)
                p_map, s_map, a_map, m_map = {}, {}, {}, []
                mapped = source.layout_for(cap, p_map, s_map, a_map, m_map, HERE, family_targets=loaded)

                self.assertEqual(s_plain, s_map)
                self.assertEqual(p_plain, p_map)
                self.assertEqual(plain['product_buttons'], mapped['product_buttons'])
                self.assertEqual(len(plain['layers']), len(mapped['layers']))
                self.assertEqual(len(plain['containers']), len(mapped['containers']))

                remapped = {row['semantic_id']: row for row in m_map if 'family' in row}
                self.assertTrue(remapped)
                for row in remapped.values():
                    self.assertIn('original_key', row)
                    self.assertNotEqual(row['original_key'], row['semantic_id'])

                if state == 'staffedit':
                    self.assertTrue(remapped['littlehands.form.session_edit.input.course']['control_state']['disabled'])
                    self.assertFalse(remapped['littlehands.form.session_edit.input.price_krw']['control_state']['disabled'])
                    self.assertEqual(
                        'littlehands.form.session_edit.field.price_krw.help.line-1' in remapped,
                        viewport == 'mobile',
                    )
                if state == 'sessionavailable':
                    self.assertEqual(
                        'littlehands.form.reserve.field.allow_waitlist.label.line-1' in remapped,
                        viewport == 'mobile',
                    )
                if state == 'staffsessions':
                    row_entries = [row for row in m_map if row.get('kind') == 'table_row']
                    self.assertEqual(len(row_entries), 2)
                    self.assertEqual({row['family'] for row in row_entries}, {'TableRow'})

    def test_family_targets_reject_duplicate_password_action_or_unknown_values(self):
        import tempfile

        base = json.loads((HERE / 'family-targets.json').read_text(encoding='utf-8'))

        with tempfile.TemporaryDirectory() as tmp:
            bad_dup = json.loads(json.dumps(base))
            bad_dup['targets'][1]['semantic_id'] = bad_dup['targets'][0]['semantic_id']
            dup_path = Path(tmp) / 'dup.json'
            dup_path.write_text(json.dumps(bad_dup), encoding='utf-8')
            with self.assertRaises(ValueError):
                source.load_family_targets(dup_path)

            bad_pwd = json.loads(json.dumps(base))
            bad_pwd['targets'].append({
                'state': 'state-staffedit',
                'kind': 'surface',
                'selector': '#id_password',
                'family': 'Input',
                'role': 'surface',
                'semantic_id': 'littlehands.form.auth.input.password',
            })
            pwd_path = Path(tmp) / 'pwd.json'
            pwd_path.write_text(json.dumps(bad_pwd), encoding='utf-8')
            with self.assertRaises(ValueError):
                source.load_family_targets(pwd_path)

            bad_fam = json.loads(json.dumps(base))
            bad_fam['targets'][0]['family'] = 'Button'
            fam_path = Path(tmp) / 'fam.json'
            fam_path.write_text(json.dumps(bad_fam), encoding='utf-8')
            with self.assertRaises(ValueError):
                source.load_family_targets(fam_path)

        cap = json.loads((HERE / 'captures' / 'sessionavailable-desktop.json').read_text(encoding='utf-8'))
        bad_action = {
            'schema': 'little-hands-family-targets-v1',
            'targets': [{
                'state': 'state-sessionavailable',
                'kind': 'surface',
                'selector': 'button.primary',
                'family': 'Input',
                'role': 'surface',
                'semantic_id': 'littlehands.form.reserve.illegal_action',
            }],
        }
        with self.assertRaises(ValueError):
            source.layout_for(cap, {}, {}, {}, [], HERE, family_targets=bad_action)

    def test_generate_with_family_targets_preserves_graph_structure_and_reuse_ids(self):
        import shutil
        import subprocess
        import sys
        import tempfile

        baseline = json.loads((HERE / 'graph.json').read_bytes())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            design = root / 'apps/little-hands/design'
            shutil.copytree(HERE, design, ignore=shutil.ignore_patterns('reviews', '.figma-flow', '__pycache__'))
            app = design.parent
            for name in ('templates', 'static', 'booking', 'ARCHITECTURE.md'):
                (app / name).symlink_to(HERE.parent / name)
            for name in ('tools', 'skills'):
                (root / name).symlink_to(HERE.parents[2] / name)

            subprocess.run(
                [sys.executable, str(design / 'source.py'), '--static-root', str(HERE / 'source_assets')],
                check=True,
                capture_output=True,
            )
            plain_dom = json.loads((design / 'dom-map.json').read_bytes())
            self.assertEqual(json.loads((design / 'graph.json').read_bytes()), baseline)
            self.assertFalse(any('semantic_id' in item for item in plain_dom['controls_and_layers']))

            subprocess.run(
                [
                    sys.executable,
                    str(design / 'source.py'),
                    '--static-root',
                    str(HERE / 'source_assets'),
                    '--family-targets',
                    str(design / 'family-targets.json'),
                ],
                check=True,
                capture_output=True,
            )
            mapped_graph = json.loads((design / 'graph.json').read_bytes())
            mapped_dom = json.loads((design / 'dom-map.json').read_bytes())
            mapped_layout = json.loads((design / 'native-layout.json').read_bytes())

            self.assertEqual(mapped_graph['nodes'], baseline['nodes'])
            self.assertEqual(mapped_graph['edges'], baseline['edges'])
            self.assertEqual(mapped_graph['design_system'], baseline['design_system'])
            self.assertEqual(mapped_graph['design_foundations']['palette'], baseline['design_foundations']['palette'])
            self.assertEqual(mapped_graph['draft_prototype'], baseline['draft_prototype'])
            size_role = next(
                role for role in mapped_graph['design_foundations']['roles']
                if role.get('token') == 'type/body'
            )
            binding_keys = {entry['key'] for entry in size_role['native']['bindings']}
            self.assertIn(
                'littlehands.desktop.state-sessionavailable.littlehands.form.reserve.input.quantity.value',
                binding_keys,
            )
            self.assertNotIn(
                'littlehands.desktop.state-sessionavailable.state-sessionavailable-id_quantity-value',
                binding_keys,
            )
            action_cids = {
                node.get('component_id')
                for node in mapped_graph['nodes']
                if node.get('type') == 'action'
            }
            self.assertTrue(action_cids)
            self.assertTrue(all(
                cid and cid.startswith(('component-Solid-', 'component-Outline-', 'component-Text-'))
                for cid in action_cids
            ))
            control_styles = mapped_layout['candidates'][0]['control_styles']['desktop']
            self.assertTrue(all(k.startswith(('Solid-', 'Outline-', 'Text-')) for k in control_styles))

            session_map = {
                row['semantic_id']: row
                for row in mapped_dom['controls_and_layers']
                if row.get('state') == 'state-sessionavailable'
                and row.get('viewport') == 'desktop'
                and 'semantic_id' in row
            }
            self.assertIn('littlehands.form.reserve.input.quantity', session_map)
            self.assertEqual(
                session_map['littlehands.form.reserve.input.quantity']['original_key'],
                'state-sessionavailable-id_quantity-surface',
            )
            layer_ids = {
                layer['id']
                for layer in mapped_layout['candidates'][0]['state_layouts']['desktop']['state-sessionavailable']['layers']
            }
            self.assertIn('littlehands.form.reserve.input.quantity', layer_ids)
            self.assertNotIn('state-sessionavailable-id_quantity-surface', layer_ids)


if __name__=='__main__':unittest.main()
