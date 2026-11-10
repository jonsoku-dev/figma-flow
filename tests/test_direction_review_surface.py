import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from direction_fixture import selected_direction
from direction_review_surface import render_surface, write_surface


class PortableReviewTests(unittest.TestCase):
    def test_review_carries_visible_images_and_graph_evidence_without_a_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with selected_direction(root) as case:
                data=json.loads(case.manifest.read_text())
                out=root/'offline';out.mkdir()
                result=write_surface(data,out)
                html=Path(result['review_page']).read_text()
                self.assertEqual(html,render_surface(data,out))
                self.assertEqual(html.count('src="data:image/jpeg;base64,'),4)
                self.assertIn('제안 토큰',html)
                self.assertIn('Reading panel',html)
                image=Path(result['comparison_image'])
                self.assertTrue(image.read_bytes().startswith(b'\xff\xd8\xff'))
                inputs=data['candidates'][0]['previews']
                Path(inputs[0]['file']['path']).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'Review input changed'):
                    write_surface(data,out)
                self.assertEqual(Path(result['review_page']).read_text(),html)

if __name__=='__main__':
    unittest.main()
