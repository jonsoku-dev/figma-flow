"""Probe Django and MySQL through the private HTTP listener."""
import http.client
import json
from pathlib import Path
import os
from urllib.parse import urlsplit

origin = urlsplit(os.environ['LH_SITE_URL'])
settings = json.loads((Path(__file__).resolve().parents[1] / 'config/deployment.json').read_bytes())['web']
connection = http.client.HTTPConnection('127.0.0.1', settings['internalPort'], timeout=settings['healthTimeout'])
connection.request('GET', '/health/', headers={'Host': origin.netloc, 'X-Forwarded-Proto': 'https'})
response = connection.getresponse()
raise SystemExit(0 if response.status == 200 else 1)
