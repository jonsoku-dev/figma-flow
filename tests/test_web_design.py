import json
import hashlib
import base64
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import web_design, native_edit

def graph():
    return {'version':1,'id':'magic-ui-demo','title':'Magic UI','nodes':[{'id':'WEB-home','type':'screen','title':'Home','status':'observed','layout':{'width':390,'height':844,'background':'#ffffff'},'elements':[{'id':'heading','kind':'text','path':[],'box':{'x':24,'y':40,'width':300,'height':48},'text':{'characters':'Hello','fontFamily':'Inter','fontSize':32,'fontWeight':'700','color':'#111111'}}]}],'edges':[]}

def representative_graph(asset_path, asset_hash, count=506):
    elements=[{'id':'root','kind':'frame','path':[],'box':{'x':0,'y':0,'width':1265,'height':11678},'paint':{'background':'#ffffff'}}]
    for index in range(count-14):
        elements.append({'id':f'text-{index}','kind':'text','path':['root'],'box':{'x':32,'y':index*20,'width':300,'height':18},'text':{'characters':f'Observed line {index}','fontFamily':'Inter','fontSize':14,'fontWeight':400,'lineHeight':20,'textAlign':'left','color':'#111111'}})
    for index,label in enumerate(('Create an account','Join now')):
        elements.append({'id':f'button-{index}','kind':'component','componentKey':'primary-button','path':['root'],'box':{'x':24,'y':11000+index*48,'width':280-index*40,'height':36},'props':{'label':label,'labelBox':{'x':0,'y':8,'width':200-index*40,'height':20}},'paint':{'background':'#e7000b','borderRadius':8},'text':{'characters':label,'fontFamily':'Inter','fontSize':14,'fontWeight':500,'lineHeight':20,'textAlign':'center','color':'#ffffff'}})
    for index in range(11):
        elements.append({'id':f'image-{index}','kind':'image','path':['root'],'box':{'x':24+index*42,'y':11200,'width':40,'height':40},'asset':{'path':asset_path,'sha256':asset_hash,'mimeType':'image/png'},'objectFit':'cover'})
    return {'version':1,'id':'representative-magic-ui','title':'Representative capture','nodes':[{'id':'WEB-representative','type':'screen','title':'Representative capture','status':'observed','layout':{'width':1265,'height':11678,'background':'#ffffff'},'elements':elements}],'edges':[]}

class WebDesignTests(unittest.TestCase):
    def test_graph_to_pinned_native_plan(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'graph.json';src.write_text(json.dumps(graph()));out=Path(d)/'plan.json'
            receipt=web_design.build_plan(src,'file','1:1',out)
            plan=json.loads(out.read_text());native_edit.validate_plan(plan)
            self.assertEqual(receipt['screen_count'],1);self.assertEqual(plan['web_design']['screens'][0]['layout']['width'],390)
            with self.assertRaises(FileExistsError):web_design.build_plan(src,'file','1:1',out)
    def test_forged_plan_cannot_change_pinned_screen_content_or_graph_edges(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'graph.json';src.write_text(json.dumps(graph()));plan_path=Path(d)/'plan.json'
            web_design.build_plan(src,'file','1:1',plan_path)
            plan=json.loads(plan_path.read_text());plan['web_design']['screens'][0]['elements'][0]['text']['characters']='Forged'
            with self.assertRaisesRegex(ValueError,'exactly match selected pinned canonical screen content'):native_edit.validate_plan(plan)
            source=json.loads(src.read_text());source['edges']=[{'from':'WEB-home','to':'missing','type':'evidence'}];src.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError,'source graph changed'):native_edit.validate_plan(json.loads(plan_path.read_text()))
    def test_rejects_unpinned_or_unsafe_geometry_and_assets(self):
        bad=graph();bad['nodes'][0]['elements'][0]['box']['x']=float('nan')
        with self.assertRaises(ValueError):web_design.validate_graph(bad)
        for svg in ('<svg><script/></svg>', '<svg><path onclick="alert(1)"/></svg>', '<svg><path fill="url(https://x)"/></svg>'):
            bad=graph();element=bad['nodes'][0]['elements'][0];element['kind']='vector';element['svg']=svg
            with self.subTest(svg=svg),self.assertRaises(ValueError):web_design.validate_graph(bad)

    def test_screen_selection_and_image_signature_are_enforced(self):
        data=b'not a png';digest=hashlib.sha256(data).hexdigest()
        sample=graph();image=dict(id='hero-image',kind='image',box={'x':0,'y':0,'width':10,'height':10},asset={'path':'hero.png','sha256':digest,'mimeType':'image/png'})
        sample['nodes'][0]['elements'].append(image)
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'graph.json';src.write_text(json.dumps(sample));(Path(d)/'hero.png').write_bytes(data)
            plan=Path(d)/'bad.json';web_design.build_plan(src,'file','1:1',plan)
            with self.assertRaises(ValueError):native_edit.prepare(plan,Path(d)/'plugin')
            with self.assertRaises(ValueError):web_design.build_plan(src,'file','1:1',Path(d)/'missing.json',['WEB-absent'])

    def test_full_length_plan_deduplicates_verified_local_raster_content(self):
        with tempfile.TemporaryDirectory() as d:
            asset=b'\x89PNG\r\n\x1a\n'+b'bounded representative raster bytes'
            digest=hashlib.sha256(asset).hexdigest()
            asset_path=Path(d)/'assets/shared.png';asset_path.parent.mkdir();asset_path.write_bytes(asset)
            source=Path(d)/'capture.json';source.write_text(json.dumps(representative_graph('assets/shared.png',digest)))
            plan=Path(d)/'plan.json';web_design.build_plan(source,'file','1:1',plan,preview_width=420)
            self.assertLess(plan.stat().st_size,400_000)
            native=json.loads(plan.read_text());native_edit.validate_plan(native)
            self.assertEqual(native['web_design']['preview_width'],420)
            self.assertFalse(any('data' in element.get('asset',{}) for screen in native['web_design']['screens'] for element in screen['elements']))
            bundle=Path(d)/'bundle';native_edit.prepare(plan,bundle)
            code=(bundle/'code.js').read_text();encoded=base64.b64encode(asset).decode()
            self.assertEqual(code.count(encoded),1)
            pins=json.loads((bundle/'source-inputs.json').read_text())['pins']
            self.assertEqual(len(pins),len({row['path'] for row in pins}))
            import subprocess
            result=subprocess.run(['node','--check',str(bundle/'code.js')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_prepare_builds_graph_panel_bundle_and_bridge_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'graph.json';src.write_text(json.dumps(graph()));plan=Path(d)/'plan.json';web_design.build_plan(src,'file','1:1',plan)
            out=Path(d)/'plugin';native_edit.prepare(plan,out)
            code=(out/'code.js').read_text()
            self.assertIn('async function webApply(figma, plan)',code);self.assertIn('figma-flow-web-design-id',code)
            import subprocess
            result=subprocess.run(['node','--check',str(out/'code.js')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
