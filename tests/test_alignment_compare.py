import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from alignment_compare import review


class AlignmentCompareTest(unittest.TestCase):
    def test_portable_comparison_requires_matching_rules_page_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = []
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nmO4AAAAASUVORK5CYII=')
            for port, delta in ((1001, -4), (1002, 0)):
                folder = root / str(port)
                folder.mkdir()
                url = f'http://localhost:{port}/booking#details'
                target = {'selector': '.amount', 'occurrenceIndex': 0, 'count': 1,
                          'delta': delta, 'status': 'drift' if delta else 'pass'}
                group = {'id': '<amount>', 'anchor': 'th', 'targets': [target]}
                view = {'width': 320, 'height': 300, 'finalUrl': url, 'groups': [group]}
                data = {'schemaVersion': 1, 'url': url, 'pageKey': '/booking#details', 'rulesSha256': '0'*64,
                        'browser': 'Chrome/test', 'viewports': [view]}
                file = folder / 'report.json'
                file.write_text(json.dumps(data))
                files.append(file)
                for kind in ('clean', 'guide-overlay'):
                    (folder / f'width-320-{kind}.png').write_bytes(png)
            output = root / 'review.html'
            with self.assertRaisesRegex(ValueError, 'Different pages'):
                review(*files, output)
            review(*files, output, True)
            body = output.read_text()
            self.assertIn('-4 px', body)
            self.assertIn('&lt;amount&gt;', body)
            self.assertIn('data:image/png;base64,', body)
            with self.assertRaises(FileExistsError):
                review(*files, output, True)
            for field in ('browser', 'rulesSha256', 'pageKey'):
                changed = {**data, field: 'different'}
                files[1].write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, field):
                    review(*files, root / 'other.html', True)
            view['height'] += 1
            files[1].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'viewport'):
                review(*files, root / 'other.html', True)
