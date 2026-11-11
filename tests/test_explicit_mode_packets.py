"""New-mode source pipeline fixtures; no real Figma or visual-quality claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import design_directions as directions
import design_critique
import design_quality
import figma_draft

spec = importlib.util.spec_from_file_location('explicit_mode_demo', ROOT / 'examples/native-direction-review/demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def check_mode(mode):
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp)/'project';demo.build_files(root)
  candidate_spec=json.loads((root/'candidate-spec.json').read_text());layout=json.loads((root/'native-layout.json').read_text())
  if mode=='direct':
   candidate_spec['candidates']=candidate_spec['candidates'][:1];layout['candidates']=layout['candidates'][:1]
   request='Create one Figma direction using the supplied Welcome board workshop design without comparison.'
   (root/'brief.md').write_text(request+'\n')
   candidate_spec['direct_instruction']={'request_text':request,'anchors':[{'artifact':'brief','excerpt':request}]}
  for candidate in candidate_spec['candidates']:
   gp=root/candidate['graph'];graph=json.loads(gp.read_text())
   graph['nodes'] += [{'id':'req-demo','type':'requirement','title':'Read workshop information','status':'planned'}, {'id':'ac-demo','type':'acceptance','title':'Open details and return','status':'unverified'}, {'id':'test-demo','type':'test','title':'Synthetic navigation probe','status':'unverified'}]
   graph['edges'] += [{'from':'req-demo','to':n['id'],'type':'appears on'} for n in graph['nodes'] if n['type']=='screen']
   graph['edges'] += [{'from':'req-demo','to':'ac-demo','type':'accepted by'},{'from':'ac-demo','to':'test-demo','type':'checked by'}]
   dump(gp,graph)
   next(c for c in layout['candidates'] if c['id']==candidate['id'])['graph']['sha256']=hashlib.sha256(gp.read_bytes()).hexdigest()
  dump(root/'native-layout.json',layout)
  created=directions.create_draft(root,'brief.md','research.md',candidate_spec,root/'review',mode=mode,review_destination='figma')
  manifest=Path(created['manifest']);data=json.loads(manifest.read_text())
  quality=design_quality.run(root/'native-layout.json')
  assert not quality['errors'],quality['errors']
  aspects={'purpose':'The supplied workshop title and session action state the information reading purpose.',
   'content_hierarchy':'The workshop heading precedes the summary, session information, and opening action.',
   'typography':'The supplied source defines sixteen pixel body typography and explicit button font inheritance.',
   'layout':'The main region contains the overview and hidden detail regions in the supplied HTML source.',
   'assets':'The source test fixture uses text and session content; its preview is synthetic test material.',
   'responsive':'Both pinned preview dimensions exist in this fixture, without asserting real browser layout quality.',
   'interaction':'The source binds its open and back actions to toggle overview and detail visibility.'}
  review={'schema':design_critique.SCHEMA,'role':'agent','brief':data['brief'],'native_layout':data['native_layout'],
   'draft_content_sha256':directions.digest(data['candidates']),'warning_dispositions':[{'warning_sha256':directions.digest(w),'warning':w,'disposition':'accepted','reason':'This warning is retained as a synthetic fixture limitation and does not certify visual quality.'} for w in quality['warnings']],
   'candidates':[]}
  for c in data['candidates']:
   row={k:c[k] for k in ('id','composition','typography','interaction')}
   row.update(candidate_sha256=c['sha256'],truth_and_notes='Source-pinned synthetic workshop semantics; no native or visual observation.',artifacts={k:c[k] for k in ('source','review','product_graph','previews')},observations=[{'aspect':a,'artifact':'source','locator':'Community workshop','excerpt':'Explore sessions','observation':o,'reason':'This located source fragment supports the structural observation without asserting executed visual quality.','resolution':'clean'} for a,o in aspects.items()])
   review['candidates'].append(row)
  dump(root/'critique.json',review)
  directions.review_draft(manifest,root/'critique.json')
  packet=figma_draft.make_packet(manifest)
  assert len(packet['candidates'])==(1 if mode=='direct' else 2)
  assert all(len(c['specifications'])==4 for c in packet['candidates'])
  assert all(s['trace']['status']=='complete' for c in packet['candidates'] for s in c['specifications'].values())
  prepared=figma_draft.prepare(manifest,root/'prepared',plugin_id='123456789')
  proc=subprocess.run(['node','--check',str(root/'prepared/plugin/code.js')],capture_output=True,text=True)
  assert proc.returncode==0,proc.stderr
  assert prepared['status']=='prepared-not-executed'
  changed=root/candidate_spec['candidates'][0]['graph']
  changed.write_text(changed.read_text()+' ')
  try:figma_draft.make_packet(manifest)
  except ValueError:pass
  else:raise AssertionError('Changed graph accepted as current')


class ExplicitModePacketTests(unittest.TestCase):
    def test_direct_source_review_specification_and_packet_chain(self):
        check_mode('direct')

    def test_compare_source_review_specification_and_packet_chain(self):
        check_mode('compare')


if __name__ == '__main__':
    unittest.main()
