"""Frozen capture contract for a real, layered radial/linear alpha mask."""
from pathlib import Path
import subprocess
import unittest


class CompoundEffectImport(unittest.TestCase):
    def test_browser_capture_records_all_intersecting_layers(self):
        root = Path(__file__).resolve().parents[1]
        js = r'''
const capture = require('./tools/web_design_capture.js').captureWebDesign;
const rect = {x:0,y:0,width:80,height:80,top:0,left:0,right:80,bottom:80};
const style = {display:'block',visibility:'visible',opacity:'1',backgroundColor:'rgb(20, 80, 152)',color:'rgb(20, 30, 40)',
  filter:'none',boxShadow:'none',backgroundImage:'none',maskImage:'radial-gradient(at 50% 50%, rgb(0, 0, 0) 0%, rgba(0, 0, 0, 0) 100%), linear-gradient(90deg, rgba(0, 0, 0, 0) 0%, rgb(0, 0, 0) 100%)',
  maskComposite:'intersect',maskMode:'alpha',maskRepeat:'repeat',maskSize:'auto',maskPosition:'0% 0%',fontFamily:'Arial',
  borderTopWidth:'0px',borderTopStyle:'none',borderTopLeftRadius:'0px'};
const body={tagName:'MAIN',textContent:'',children:[],childNodes:[],getBoundingClientRect:()=>rect,getAttribute:()=>null};
global.document={documentElement:{clientWidth:80,scrollHeight:80},body,title:'Fixture'};
global.location={origin:'http://localhost:8000',pathname:'/',href:'http://localhost:8000/'};
global.innerWidth=80;global.innerHeight=80;global.scrollX=0;global.scrollY=0;global.getComputedStyle=()=>style;
const result=capture({screenId:'WEB-mask',extent:'document'});
const paint=result.screen.elements[0].paint;
if (!paint.alphaMasks || JSON.stringify(paint.alphaMasks).indexOf('radial')<0) throw Error('compound mask evidence is missing');
'''
        run = subprocess.run(['node', '-e', js], cwd=root, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
