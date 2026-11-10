"""Synthetic getter contracts for optional pinned control icons; no Figma writes."""
import base64
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import figma_draft as draft
import draft_token_plan

ASSET=base64.b64encode(b'pinned-icon-bytes').decode()

def fixture(placement='after'):
    style=dict(icon=dict(asset='arrow',placement=placement,width=18,height=18,gap=18),paddingX=20,paddingY=12)
    parent=dict(id='control',type='INSTANCE',width=160,height=54,itemSpacing=18)
    label=dict(id='label',parentId='control',type='TEXT',textAutoResize='WIDTH_AND_HEIGHT',layoutSizingHorizontal='HUG',x=27 if placement=='after'else 63,y=15,width=70,height=24)
    icon=dict(id='icon',parentId='control',type='RECTANGLE',x=115 if placement=='after'else 27,y=18,width=18,height=18,
              controlIconAsset='arrow',iconImageBytes=ASSET,fills=[dict(type='IMAGE',imageHash='observed',scaleMode='FIT')])
    return parent,label,icon,style

class ControlIcons(unittest.TestCase):
    def test_exact_pinned_bytes_and_centered_before_after_group(self):
        for placement in ['before','after']:
            with self.subTest(placement=placement):
                self.assertEqual(draft._native_control_icon_findings(*fixture(placement),'key',{'arrow':ASSET}),[])

    def test_correct_label_cannot_hide_missing_wrong_or_shifted_icon(self):
        for field,value,code in [('type','TEXT','control-icon-missing'),('parentId','foreign','control-icon-missing'),
                ('iconImageBytes',base64.b64encode(b'wrong').decode(),'control-icon-asset'),
                ('width',17,'control-icon-geometry'),('x',112,'control-icon-gap'),('y',10,'control-icon-alignment'),
                ('visible',False,'visibility-drift'),('controlIconAsset','other','control-icon-asset')]:
            parent,label,icon,style=fixture();icon[field]=value
            with self.subTest(field=field):self.assertIn(code,{x['code']for x in draft._native_control_icon_findings(parent,label,icon,style,'key',{'arrow':ASSET})})
        parent,label,icon,style=fixture()
        self.assertIn('control-icon-missing',{x['code']for x in draft._native_control_icon_findings(parent,label,None,style,'key',{'arrow':ASSET})})
        icon['fills'][0]['scaleMode']='FILL'
        self.assertIn('control-icon-asset',{x['code']for x in draft._native_control_icon_findings(parent,label,icon,style,'key',{'arrow':ASSET})})

    def test_style_icon_is_explicit_owned_raster_and_has_label_room(self):
        valid=dict(icon=fixture()[3]['icon'],maxWidth=160,paddingX=20)
        assets={'arrow':{'path':'arrow.png','sha256':'a'*64}}
        draft.check_control_icon(valid,assets,'main')
        for invalid in [None,[],{},'arrow',dict(valid['icon'],asset='missing'),dict(valid['icon'],gap=-1),dict(valid['icon'],width=True),dict(valid['icon'],placement='left'),dict(valid['icon'],extra=1)]:
            with self.subTest(invalid=invalid),self.assertRaises((ValueError,TypeError)):
                draft.check_control_icon(dict(valid,icon=invalid),assets,'main')
        with self.assertRaises(ValueError):draft.check_control_icon(valid,{'arrow':{'reference':True}},'main')
        with self.assertRaises(ValueError):draft.check_control_icon(dict(valid,maxWidth=70),assets,'main')
        draft.check_control_icon({},assets,'text-only')

    def test_same_width_palette_override_and_property_drift_fail_even_without_icon(self):
        prop='문구#1'
        parent=dict(id='control',type='INSTANCE',mainComponentId='main',componentProperties={prop:{'type':'TEXT','value':'Go'}})
        label=dict(type='TEXT',parentId='control',characters='Go',componentPropertyReferences={'characters':prop})
        main=dict(id='main',type='COMPONENT',componentSetId='set')
        main_label=dict(componentPropertyReferences={'characters':prop})
        component_set=dict(id='set',componentPropertyDefinitions={prop:{'type':'TEXT'}})
        self.assertEqual(draft._native_palette_label_findings(parent,label,main,main_label,component_set,'Go','palette'),[])
        for mutated in [dict(label,characters='No'),dict(label,componentPropertyReferences={'characters':'foreign'})]:
            self.assertTrue(draft._native_palette_label_findings(parent,mutated,main,main_label,component_set,'Go','palette'))
        parent['componentProperties'][prop]['value']='No'
        self.assertTrue(draft._native_palette_label_findings(parent,label,main,main_label,component_set,'Go','palette'))

    def test_authored_gap_matches_actual_main_and_instance_fields_without_unsafe_icon_access(self):
        style=dict(radius=0,paddingX=20,paddingY=12,fontSize=14,icon=fixture()[3]['icon'])
        source=dict(id='a',fonts={'body':{'family':'Inter'}},control_styles={'desktop':{'Primary':style}},state_layouts={'desktop':{'idle':{'layers':[],'product_buttons':{'send':{'variant':'Primary'}}}}})
        graph=dict(nodes=[],draft_prototype={'bindings':[]})
        fields=draft_token_plan.authored_fields(source,graph)
        self.assertEqual(fields['a.desktop.component.Primary']['itemSpacing'],18)
        self.assertEqual(fields['a.desktop.idle.send']['itemSpacing'],18)
        for invalid in [None,[],False,'bad']:
            source['control_styles']['desktop']['Primary']['icon']=invalid
            self.assertEqual(draft_token_plan.authored_fields(source,graph)['a.desktop.component.Primary']['itemSpacing'],0)

if __name__=='__main__':unittest.main()
