// Render the built relay at two widths and report actual browser geometry.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { chromiumBinary, until, withChromiumPage } from '../../tools/chromium_pipe.mjs';

let binary;
try { binary = chromiumBinary(); }
catch { process.exit(77); }

const html = await readFile(process.argv[2]);
const server = createServer((_, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html;charset=utf-8' });
  response.end(html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
try {
  const samples = await withChromiumPage(binary, async ({ command, evaluate }) => {
    await command('Page.enable');
    await command('Network.enable');
    await command('Page.addScriptToEvaluateOnNewDocument', {source: `
      window.addEventListener('message', event => {
        const message = event.data?.pluginMessage;
        if (message?.type === 'workspace-home-ready') window.relayReady = message.requestId;
      });
    `});
    await command('Page.navigate', { url: 'http://127.0.0.1:' + server.address().port });
    const requestId = await until(() => evaluate('window.relayReady'), Date.now() + 8000,
      'relay viewer did not request its initial state');
    await evaluate(`window.dispatchEvent(new MessageEvent('message', {data:{pluginMessage:${JSON.stringify({
      type: 'workspace-relay-viewer-state', requestId, workspaceSession: 'alignment-fixture', status: 'live',
      locale: 'ko', file: { key: 'fixture-file', name: '예약 흐름 설계' },
      page: { id: '2:3', name: '모바일 화면' },
      selection: [
        { id: '4:5', name: '예약 카드', type: 'FRAME' },
        { id: '4:6', name: '확인 버튼', type: 'INSTANCE' },
      ],
    })}}}))`);
    await until(() => evaluate("document.querySelectorAll('.relay-layers tbody tr').length === 2"),
      Date.now() + 8000, 'bounded selection fixture did not render');
    await evaluate("document.querySelector('.relay-footer details').open = true");
    const results = [];
    for (const width of [320, 400]) {
      await command('Emulation.setDeviceMetricsOverride', {
        width, height: 900, deviceScaleFactor: 1, mobile: false,
      });
      results.push(await evaluate(`(() => {
        const left = selector => document.querySelector(selector).getBoundingClientRect().left;
        const table = document.querySelector('.relay-layers');
        const rowCells = [...table.tBodies[0].rows].map(row => row.cells[0].getBoundingClientRect().left);
        const contextIcons = [...document.querySelectorAll('.relay-context-row svg')]
          .map(icon => icon.getBoundingClientRect().left);
        return {
          width: innerWidth,
          locale: document.documentElement.lang,
          rowCount: table.tBodies[0].rows.length,
          documentWidth: document.documentElement.scrollWidth,
          edges: {
            brand: left('.relay-brand-mark'),
            heading: left('.relay-content h1'),
            ...Object.fromEntries(contextIcons.map((edge, index) => ['contextIcon' + index, edge])),
            tableHeader: left('.relay-layers thead th:first-child'),
            ...Object.fromEntries(rowCells.map((edge, index) => ['tableRow' + index, edge])),
          },
        };
      })()`));
    }
    return results;
  });
  assert.equal(samples.length, 2);
  process.stdout.write(JSON.stringify(samples));
} finally {
  await new Promise(resolve => server.close(resolve));
}
