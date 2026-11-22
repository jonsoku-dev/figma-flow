"""A valid receipt for a different screen cannot vouch for the selected Design frame."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from spec_graph_coverage import check


class PairedReceiptTests(unittest.TestCase):
    def test_rejects_mismatched_real_receipts_even_when_both_targets_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            feature=root/'specs/paired'
            feature.mkdir(parents=True)
            (feature/'record.md').write_text('Recorded viewport and native readback.\n')
            index='specs/paired/graph.json'
            (root/'specs/README.md').write_text('[graph-roots.json](graph-roots.json)\n[Paired](paired/graph.json)\n')
            (root/'specs/graph-roots.json').write_text(json.dumps({'version':1,'roots':[{'path':index,'role':'paired fixture'}]}))
            nodes=[];edges=[]
            sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
            for n in ('one','two'):
                receipt=sha(n)
                for prefix,kind,metadata in (
                    ('screen','screen',{'document':{'width':350,'height':520}}),
                    ('frame','figma',{'frame_width':350,'frame_height':520,'receipt_sha256':receipt}),
                    ('observation','test',{'capture_sha256':sha('capture-'+n),'reapply_sha256':receipt,
                                           'browser_png_sha256':sha('web-'+n),'figma_png_sha256':sha('fig-'+n)})):
                    nodes.append({'id':prefix+'-'+n,'title':n,'type':kind,'status':'verified','source':'record.md',**metadata})
                for src,dst,relation in [('screen','frame','rendered as'),('screen','observation','observed in'),('frame','observation','observed in')]:
                    edges.append({'from':src+'-'+n,'to':dst+'-'+n,'type':relation})
            def findings(nn,ee):
                (root/index).write_text(json.dumps({'version':1,'nodes':nn,'edges':ee}))
                result=check(root)
                self.assertFalse(any(x['code'] in ('invalid-root-entry','unregistered-graph') for x in result))
                return [x for x in result if x['code']=='unpaired-render-observation']
            self.assertFalse(findings(nodes,edges))
            wrong=copy.deepcopy(edges);wrong[1]['to']='observation-two'
            self.assertTrue(findings(nodes,wrong),'A screen must not borrow another frame observation')
            wrong=copy.deepcopy(nodes);wrong[1]['frame_width']=150
            self.assertTrue(findings(wrong,edges))
            wrong=copy.deepcopy(nodes);wrong[1]['receipt_sha256']=sha('other')
            self.assertTrue(findings(wrong,edges))
            self.assertTrue(findings(nodes,[e for e in edges if e['type']!='observed in']))


if __name__=='__main__':
    unittest.main()
