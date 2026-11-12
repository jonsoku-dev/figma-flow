"""Canonical history retains a quiet page despite activity in other scopes."""
import copy
import json
import unittest

from tests import finalize_lifecycle_oracle as fixture


class HistoryScopeTests(fixture.FinalizeLifecycle):
    def test_scoped_history_is_not_evicted_by_other_pages(self):
        requests = self.root / '.control/requests'
        original = json.loads((requests / (self.request['id'] + '.json')).read_text())
        for index in range(81):
            other = copy.deepcopy(original)
            other.update(id=f'{index + 1:032x}', file_key='otherfile', page_id='90:1')
            fixture.workspace.atomic(requests / (other['id'] + '.json'), fixture.workspace.encode(other))
        rows = self.post(self.scope())['journalHistory']
        self.assertIn(self.request['id'], [row['operationId'] for row in rows],
                      'scoped history must not discard a quiet page because other pages are busy')
        self.assertLessEqual(len(rows), 80)


if __name__ == '__main__':
    unittest.main()
