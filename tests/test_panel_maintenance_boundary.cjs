const assert = require('node:assert/strict');
const test = require('node:test');
const { checkSource, checkPanel } = require('../panel-ui/architecture.cjs');

test('panel build flags transport and native bridge bypasses', () => {
  const violations = [
    ['View.jsx', 'export function View(){ fetch("/path"); return <main/> }', /local pairing/],
    ['nested/View.js', 'const send = globalThis["fetch"]; send("/path");', /local pairing/],
    ['View.jsx', 'window.parent.postMessage({unsafe: true},"*");', /send callback/],
    ['View.jsx', "import fs from 'node:fs'; console.log(fs);", /source boundary/],
    ['View.jsx', "const dns = require('dns/promises'); export { dns };", /source boundary/],
    ['View.jsx', "const client = require('axios'); export { client };", /source boundary/],
    ['nested/View.js', 'import native from "../../../figma-bridge/workspace_host.js"; console.log(native);', /source boundary/],
  ];
  for (const [file, source, expected] of violations) {
    assert.match(checkSource(file, source).join('\n'), expected);
  }
  assert.deepEqual(checkPanel(), []);
});

test('review pairing posts only the approved payload to the prepared local receiver', async (t) => {
  const { postDraftReceipt } = await import('../panel-ui/src/reviewTransport.mjs');
  const requests = [];
  t.mock.method(global, 'fetch', async (url, options) => {
    requests.push([String(url), options]);
    return { ok:true, json: async () => ({ passed:true }) };
  });
  const pair = { url:'http://localhost:4312/draft-readback', capability:'e'.repeat(64) };
  const data = { schema:'synthetic-receipt' };
  const signal = new AbortController().signal;
  assert.equal((await postDraftReceipt(pair, data, signal)).passed, true);
  assert.equal(requests[0][0], pair.url);
  assert.equal(requests[0][1].body, JSON.stringify(data));
  assert.equal(requests[0][1].signal, signal);
  for (const url of ['https://example.com/draft-readback',
                     'http://localhost:4312/draft-readback?other=true',
                     'http://localhost:4312/not-the-prepared-receiver']) {
    await assert.rejects(postDraftReceipt({...pair,url}, data, signal), /exact prepared/);
  }
  assert.equal(requests.length, 1);
});
