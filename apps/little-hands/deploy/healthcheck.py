"""Probe Django and PostgreSQL through the private HTTP listener."""
import http.client
import os
from urllib.parse import urlsplit

origin = urlsplit(os.environ['LH_SITE_URL'])
connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=5)
connection.request('GET', '/health/', headers={'Host': origin.netloc, 'X-Forwarded-Proto': 'https'})
response = connection.getresponse()
raise SystemExit(0 if response.status == 200 else 1)
