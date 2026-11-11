"""Pinned source pixels, not screenshots or declared success counters, determine contrast."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import design_quality as quality
try:
    from PIL import Image
except ImportError:
    Image=None

def text(**extra):
    return dict(id='title',kind='text',x=8,y=8,w=16,h=32,value='X',size=16,leading=24,ink='paper',font='body',**extra)
def picture(**extra):
    return dict(id='art',kind='image',asset='art',x=0,y=0,w=64,h=64,fit='FIT',role='image',**extra)
def document(layers,assets):
    return dict(schema=quality.LAYOUT_SCHEMA,assets=assets,candidates=[dict(id='a',colors={'paper':'#FFFFFF','ink':'#000000'},fonts={'body':{'family':'none','style':'Regular'}},control_styles={'mobile':{}},state_layouts={'mobile':{'entry':dict(width=64,height=64,bg='paper',control_boxes={},layers=layers)}})])
def codes(report,kind):return [row['code']for row in report[kind]]
def measurement(report):return report['metrics']['a/mobile/entry']['contrast_measurements']['title']

@unittest.skipUnless(Image,'optional Pillow is required for source pixel tests')
class PixelContrast(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def asset(self,color,size=(64,64),edit=None):
        image=Image.new('RGBA',size,color)
        if edit:edit(image)
        path=self.root/'art.png';image.save(path)
        return {'art':{'path':'art.png','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
    def run_doc(self,layers,assets):return quality.evaluate(document(layers,assets),self.root)
    def test_pinned_dark_passes_bright_fails_and_one_noncenter_pixel_cannot_be_averaged_away(self):
        assets=self.asset((0,0,0,255));report=self.run_doc([picture(),text()],assets)
        self.assertNotIn('contrast',codes(report,'errors'));self.assertNotIn('contrast-unknown',codes(report,'warnings'))
        self.assertEqual(measurement(report)['min_ratio'],21);self.assertEqual(measurement(report)['pixels'],512)
        for edit in [None,lambda image:image.putpixel((9,9),(255,255,255,255))]:
            assets=self.asset((255,255,255,255)if edit is None else(0,0,0,255),edit=edit)
            report=self.run_doc([picture(),text()],assets)
            self.assertIn('contrast',codes(report,'errors'));self.assertEqual(measurement(report)['min_ratio'],1)
    def test_actual_opacity_and_gradient_stops_are_composited_in_source_order(self):
        assets=self.asset((255,255,255,255))
        gradient=dict(id='tone',kind='gradient',x=0,y=0,w=64,h=64,direction='vertical',role='background',stops=[dict(position=0,color='#000000',opacity=.9),dict(position=1,color='#000000',opacity=.9)])
        dark=self.run_doc([picture(),gradient,text()],assets);self.assertNotIn('contrast',codes(dark,'errors'));self.assertGreater(measurement(dark)['min_ratio'],17)
        gradient['opacity']=.5
        light=self.run_doc([picture(),gradient,text()],assets);self.assertIn('contrast',codes(light,'errors'));self.assertLess(measurement(light)['min_ratio'],4.5)
        gradient.pop('opacity');gradient['stops']=[dict(position=0,color='#000000',opacity=1),dict(position=1,color='#000000',opacity=0)]
        top=text();top.update(y=0,h=8)
        bottom=text();bottom.update(y=56,h=8)
        self.assertNotIn('contrast',codes(self.run_doc([picture(),gradient,top],assets),'errors'))
        self.assertIn('contrast',codes(self.run_doc([picture(),gradient,bottom],assets),'errors'))
    def test_image_alpha_and_layer_opacity_are_actual_rgba_not_opaque_guesses(self):
        for native_alpha, layer_opacity in [(128,1),(255,.5)]:
            assets=self.asset((0,0,0,native_alpha));image=picture();image['opacity']=layer_opacity
            report=self.run_doc([image,text()],assets)
            self.assertIn('contrast',codes(report,'errors'));self.assertLess(measurement(report)['min_ratio'],4.5)
    def test_asset_hash_is_rechecked_even_after_decoded_pixel_cache(self):
        assets=self.asset((0,0,0,255));state=document([picture(),text()],assets)['candidates'][0]['state_layouts']['mobile']['entry']
        resolver=quality._PixelContrast(self.root,assets,{'paper':'#FFFFFF','ink':'#000000'},state)
        self.assertEqual(resolver.measure(state['layers'][:1],text(),(1,1,1))['min_ratio'],21)
        (self.root/'art.png').write_bytes(b'tampered')
        self.assertIsNone(resolver.measure(state['layers'][:1],text(),(1,1,1))['min_ratio'])

    def test_fit_letterbox_and_center_cover_are_not_stretched(self):
        assets=self.asset((0,0,0,255),size=(64,32));top=text();top.update(y=2,h=8)
        self.assertIn('contrast',codes(self.run_doc([picture(),top],assets),'errors'))
        for fit in ['FILL','CROP']:
            image=picture();image['fit']=fit
            self.assertNotIn('contrast',codes(self.run_doc([image,top],assets),'errors'))
    def test_text_and_shapes_above_text_never_pollute_the_background(self):
        assets=self.asset((0,0,0,255));other=text();other['id']='other'
        report=self.run_doc([picture(),other,text(),dict(id='later',kind='rect',x=0,y=0,w=64,h=64,fill='paper',role='surface')],assets)
        self.assertNotIn('contrast',codes(report,'errors'));self.assertEqual(measurement(report)['min_ratio'],21)
    def test_tampered_missing_reference_or_unsupported_input_stays_unknown(self):
        for change in ['hash','missing','reference','transform','tile','ellipse','outside']:
            assets=self.asset((0,0,0,255));image=picture();title=text();layers=[image,title]
            if change=='hash':assets['art']['sha256']='0'*64
            if change=='missing':(self.root/'art.png').unlink()
            if change=='reference':assets['art']['reference']=True
            if change=='transform':image['imageTransform']=[[1,0,0],[0,1,0]]
            if change=='tile':image['fit']='TILE'
            if change=='ellipse':layers.insert(1,dict(id='unsupported',kind='ellipse',x=0,y=0,w=64,h=64,fill='ink',role='surface'))
            if change=='outside':title['x']=-1
            with self.subTest(change=change):
                report=self.run_doc(layers,assets);self.assertIn('contrast-unknown',codes(report,'warnings'));self.assertIsNone(measurement(report)['min_ratio']);self.assertTrue(measurement(report)['reason'])
    def test_missing_optional_dependency_or_layout_directory_stays_unknown(self):
        assets=self.asset((0,0,0,255));doc=document([picture(),text()],assets)
        self.assertIn('contrast-unknown',codes(quality.evaluate(doc),'warnings'))
        with patch.dict(sys.modules,{'PIL':None}):
            self.assertIn('contrast-unknown',codes(quality.evaluate(doc,self.root),'warnings'))
    def test_unknown_raster_never_downgrades_a_proven_solid_contrast_failure(self):
        assets=self.asset((0,0,0,255));assets['art']['sha256']='0'*64
        panel=dict(id='panel',kind='rect',x=0,y=0,w=64,h=64,fill='paper',role='surface')
        report=self.run_doc([picture(),panel,text()],assets)
        self.assertIn('contrast-unknown',codes(report,'warnings'));self.assertIn('contrast',codes(report,'errors'))

if __name__=='__main__':unittest.main()
