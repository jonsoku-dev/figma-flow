"""Check rejection and atomicity at the native change intake boundary."""
import copy
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import change_journal


def batch():
    scope = {'file_key':'LOCAL-TEST', 'page_id':'0:1', 'generation':'a'*64, 'session_id':'test'}
    return {
        'scope':scope,
        'cursor':{'epoch':'d'*32, 'seq':1},
        'events':[{'seq':1, 'node_id':'1:2', 'type':'PROPERTY_CHANGE', 'properties':['opacity'], 'origin':'unknown'}],
        'gap':None,
        'status':'available',
    }


class JournalBoundaryTests(unittest.TestCase):
    def test_malformed_json_fields_reject_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'changes.json'
            valid = batch()
            change_journal.ingest(path, valid, valid['scope'])
            before = path.read_bytes()
            for key, value in [('status', []), ('type', {}), ('properties', [['opacity']]), ('origin', [])]:
                malformed = copy.deepcopy(valid)
                target = malformed if key == 'status' else malformed['events'][0]
                target[key] = value
                handled = False
                try:
                    change_journal.ingest(path, malformed, valid['scope'])
                except ValueError:
                    handled = True
                except TypeError:
                    pass
                self.assertTrue(handled, 'Native change ingress must reject malformed JSON fields deterministically')
                self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
