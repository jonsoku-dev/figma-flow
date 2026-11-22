"""Apply a smaller group policy to a disposable copy of the shipped booking app."""
import importlib.util
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/little-hands'

PROBE = """
import django, json, uuid
django.setup()
from django.core.exceptions import ValidationError
from booking.forms import ReserveForm
from booking.models import Booking, ClassSession
from booking import services
from unittest.mock import patch
from types import SimpleNamespace

def allowed(check, number):
    try:
        check(number)
    except ValidationError:
        return False
    return True

field = ReserveForm().fields['quantity']
validators = Booking._meta.get_field('quantity').run_validators
bounds = next(c.condition for c in Booking._meta.constraints if c.name.startswith('booking_quantity_'))
actor = SimpleNamespace(pk=1)
session = SimpleNamespace(revision=1, capacity=8)
with patch.object(services, '_operate', side_effect=lambda *args:args[-1]()), \\
     patch.object(services, '_available'), patch.object(services, '_sessions', return_value={1:session}), \\
     patch.object(Booking.objects, 'filter', side_effect=AssertionError('queried bookings')) as lookup:
    try:
        services.reserve(actor=actor,session_id=1,quantity=3,allow_waitlist=False,expected_revision=1,request_id=uuid.uuid4())
    except services.BookingError as error:
        rejected = str(error)
    except AssertionError:
        rejected = ''
print(json.dumps({'form':[allowed(field.clean,i) for i in (1,2,3)],'model':[allowed(validators,i) for i in (1,2,3)],
                  'condition':dict(bounds.children), 'serviceRejected':bool(rejected), 'serviceMessage':rejected}))
"""


class GroupPolicyTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('django'), 'requires the Little Hands locked dependencies')
    def test_form_model_and_service_follow_the_candidate_group_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for package in ('booking', 'config'):
                shutil.copytree(APP / package, root / package, ignore=shutil.ignore_patterns('__pycache__'))
            policy = root / 'booking/policy.json'
            data = json.loads(policy.read_bytes()) if policy.exists() else {}
            data['groupSize'] = {'minimum': 1, 'maximum': 2}
            policy.write_text(json.dumps(data))
            env = dict(os.environ, PYTHONPATH=str(root), DJANGO_SETTINGS_MODULE='config.settings',
                       LH_ENV='staging', LH_SECRET_KEY='x'*64, LH_ALLOWED_HOSTS='localhost',
                       LH_SITE_URL='http://localhost', LH_DB_PASSWORD='disposable', LH_DB_USER='fixture')
            result = subprocess.run([sys.executable, '-B', '-c', PROBE], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            observation = json.loads(result.stdout)
            self.assertTrue(observation['form'] == [True, True, False], 'Booking form must follow the selected group policy')
            self.assertEqual(observation['model'], [True, True, False])
            self.assertEqual(observation['condition'], {'quantity__gte':1, 'quantity__lte':2})
            self.assertTrue(observation['serviceRejected'])
            self.assertIn('2명', observation['serviceMessage'])


if __name__ == '__main__':
    unittest.main()
