"""Exercise change intake and cursor transitions with reproducible synthetic cases."""
import argparse
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest

try:
    from .test_maintenance_journal_boundary import batch, change_journal
except ImportError:
    from test_maintenance_journal_boundary import batch, change_journal


def malformed_cases(seed, count):
    generator = random.Random(seed)
    fields = (('status',), ('cursor','seq'), ('events',0,'seq'), ('events',0,'type'),
              ('events',0,'origin'), ('events',0,'properties'))
    values = (None, False, {}, [], ['opacity'], [{'value':True}], '', -1, 9)
    for index in range(count):
        field = generator.choice(fields)
        value = generator.choice(values)
        if field[-1]=='properties' and value in ([], ['opacity']):
            value = [value]
        yield index, field, value


def rejects_without_writing(path, field, value, scope):
    original = path.read_bytes()
    packet = batch()
    target = packet
    for key in field[:-1]:
        target = target[key]
    target[field[-1]] = value
    try:
        change_journal.ingest(path,packet,scope)
    except ValueError:
        return path.read_bytes() == original
    except TypeError:
        return False
    return False


def malformed_properties(seed, count, iteration=None):
    with tempfile.TemporaryDirectory(prefix='flow-journal-') as temporary:
        journal = Path(temporary)/'test.json'
        valid = batch()
        scope = valid['scope']
        change_journal.ingest(journal,valid,scope)
        for index, field, value in malformed_cases(seed,count):
            if iteration is not None and index != iteration:
                continue
            if not rejects_without_writing(journal,field,value,scope):
                for simpler in (None, [], {}, ''):
                    if not rejects_without_writing(journal,field,simpler,scope):
                        value = simpler
                        break
                raise AssertionError(f'seed={seed} case={index} minimal mutation={json.dumps([field,value])}')


def lifecycle_properties(seed):
    generator = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix='flow-journal-') as temporary:
        path = Path(temporary)/'changes.json'
        packet = batch()
        scope = packet['scope']
        change_journal.ingest(path,packet,scope)
        mark = change_journal.query(path,scope['file_key'],scope['page_id'])['high_water']
        total = 1
        for _ in range(40):
            size = generator.randint(1, 8)
            events = [{**batch()['events'][0], 'seq':current} for current in range(total+1,total+1+size)]
            packet['events'] = events
            packet['cursor']['seq'] = total + size
            accepted = change_journal.ingest(path,packet,scope)
            assert accepted['accepted_cursor']['seq']==total+size
            written = path.read_bytes()
            replay = change_journal.ingest(path,copy.deepcopy(packet),scope)
            assert replay==accepted and path.read_bytes()==written
            observed = change_journal.query(path,scope['file_key'],scope['page_id'],cursor=mark)
            assert [row['seq'] for row in observed['events']]==list(range(total+1,total+1+size))
            assert observed['gap'] is None
            mark = observed['high_water']
            total += size
        foreign = change_journal.query(path,scope['file_key'],'0:2')
        assert foreign['events']==[] and foreign['scope'] is None


class JournalPropertiesTests(unittest.TestCase):
    def test_generated_malformed_fields_are_atomic(self):
        malformed_properties(562,250)

    def test_partitioned_batches_and_replays_keep_cursor_order(self):
        lifecycle_properties(451)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=562)
    parser.add_argument('--count',type=int,default=4000)
    parser.add_argument('--case',type=int)
    args=parser.parse_args()
    if not 1 <= args.count <= 20000 or (args.case is not None and not 0 <= args.case < args.count):
        parser.error('Choose 1–20,000 cases and a replay index within that range')
    malformed_properties(args.seed,args.count,args.case)
    if args.case is None:
        lifecycle_properties(args.seed)
    print(f'Journal rejection and cursor properties passed. seed={args.seed} count={args.count}')
