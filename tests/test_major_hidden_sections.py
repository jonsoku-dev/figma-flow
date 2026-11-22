from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from major_release import authority_field


class HiddenSectionTests(unittest.TestCase):
    def test_comments_do_not_supply_headings_or_normative_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'spec.md'
            path.write_text('# Rules\n<!--\n## Hidden\nexample\n-->\n## Empty\n<!-- only a note -->\n'
                            '## Visible\nCodex <!-- draft -->owns approval.\n')
            for heading in ('Hidden', 'Empty'):
                with self.assertRaises(ValueError):
                    authority_field(path, '/sections/' + heading)
            self.assertEqual(authority_field(path, '/sections/Visible'), 'Codex owns approval.')
