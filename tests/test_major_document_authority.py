"""A source-bound review can name a real normative Markdown section."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from major_release import scope_digest, verify_review


class MarkdownAuthorityTests(unittest.TestCase):
    def test_witness_binds_unique_section_without_promoting_code_fence_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            owner = 'CONSTITUTION.md'
            path = 'specs/use.md'
            for folder in ('specs', 'tests', 'release/reviews'):
                (root/folder).mkdir(parents=True)
            (root/path).write_text('Codex owns approval.\n')
            test = root/'tests/test_approval.py'
            test.write_text("from pathlib import Path\nimport unittest\nclass Approval(unittest.TestCase):\n"
                            " def test_published(self):\n  self.assertEqual(Path('specs/use.md').read_text(), 'Codex owns approval.\\n')\n")

            def run(source):
                (root/owner).write_text(source)
                fingerprint = scope_digest(root, [owner, path])
                rule = owner + '#/sections/Design ~1 approval'
                proof = root/'release/reviews/proof.json'
                proof.write_text(json.dumps({'surfaceFingerprint': fingerprint,'status':'passed','checks':[
                    {'authority':rule,'covers':[path],'test':'tests/test_approval.py','testSha256':hashlib.sha256(test.read_bytes()).hexdigest(),
                     'case':'Approval.test_published','assertion':'Published approval instruction follows the Design rule',
                     'observed':'Codex owns approval.'}]}))
                (root/'release/reviews/example.json').write_text(json.dumps({'schema':'figma-flow-major-review-v1','surface':'example',
                    'fingerprint':fingerprint,'openFindings':[],'bindings':[{'files':[path],'authority':rule,'reason':'Approval ownership',
                    'witnesses':[{'path':'release/reviews/proof.json','sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}]}]}))
                return verify_review(root,{'id':'example'},[path],{owner},fingerprint)

            sample = '# Rules\n\n```md\n## Design / approval\nExample only.\n```\n'
            section = '\n## Design / approval\n\nCodex owns approval.\n'
            self.assertFalse(run(sample + section), 'A reviewed normative Markdown section must bind its field-level witness')
            self.assertTrue(run(sample))
            self.assertTrue(run(sample + section * 2))
            self.assertTrue(run(sample + '\n## Design / approval\n\n## Another\ntext\n'))


if __name__ == '__main__':
    unittest.main()
