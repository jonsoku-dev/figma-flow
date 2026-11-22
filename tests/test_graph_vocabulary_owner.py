"""The portable graph CLI and archive audit share the same local relationship vocabulary."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GraphVocabularyTests(unittest.TestCase):
    def test_feature_audit_uses_the_portable_local_endpoint_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            canonical=Path('skills/figma-flow/scripts/graph.py')
            audit=Path('tools/spec_graph_coverage.py')
            for source in (canonical,audit):
                (root/source).parent.mkdir(parents=True)
                shutil.copyfile(ROOT/source,root/source)
            with (root/canonical).open('a',encoding='utf8') as stream:
                stream.write("\nLOCAL_TRACE_ENDPOINTS['checked by'] = (('acceptance','code','screen'), 'test')\n")
            script="""
import sys
sys.path.insert(0,'tools')
from spec_graph_coverage import TYPED_EDGES, _graph_contract
assert TYPED_EDGES['checked by'] == ({'acceptance','code','screen'}, {'test'})
assert TYPED_EDGES['verified by'] == TYPED_EDGES['checked by']
assert 'requirement' in TYPED_EDGES['implemented by'][0]
assert 'requirement' not in _graph_contract.LOCAL_TRACE_ENDPOINTS['implemented by'][0]
"""
            subprocess.run([sys.executable,'-B','-c',script],cwd=root,check=True)


if __name__=='__main__':
    unittest.main()
