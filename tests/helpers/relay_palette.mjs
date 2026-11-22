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
        if (message?.type === 'workspace-control-tick' && window.relayFixture) {
          window.dispatchEvent(new MessageEvent('message', { data: { pluginMessage: window.relayFixture } }));
        }
      });
    `});
    await command('Page.navigate', { url: 'http://127.0.0.1:' + server.address().port });
    const requestId = await until(() => evaluate('window.relayReady'), Date.now() + 8000,
      'relay viewer did not request its initial state');
    const snapshot = {
      type: 'workspace-relay-viewer-state', requestId, workspaceSession: 'alignment-fixture', status: 'live',
      locale: 'ko', file: { key: 'fixture-file', name: '예약 흐름 설계' },
      page: { id: '2:3', name: '모바일 화면' },
      selection: [
        { id: '4:5', name: '예약 카드', type: 'FRAME' },
        { id: '4:6', name: '확인 버튼', type: 'INSTANCE' },
      ],
    };
    await evaluate(`(() => {
      window.relayFixture = ${JSON.stringify(snapshot)};
      window.dispatchEvent(new MessageEvent('message', { data: { pluginMessage: window.relayFixture } }));
    })()`);
    await until(() => evaluate("document.querySelectorAll('.relay-layers tbody tr').length === 2"),
      Date.now() + 8000, 'bounded selection fixture did not render');
    await evaluate("document.querySelector('.relay-footer details').open = true");
    await evaluate(`(() => {
      const panel = document.querySelector('.relay-view');
      const status = document.createElement('span');
      status.className = 'relay-status';
      status.dataset.state = 'error';
      status.dataset.paletteProbe = 'status-error';
      const error = document.createElement('div');
      error.className = 'relay-error';
      for (const element of [status, error]) {
        element.style.position = 'absolute';
        element.style.visibility = 'hidden';
        panel.append(element);
      }
    })()`);
    await command('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
    const results = [];
    for (const width of [320, 400]) {
      await command('Emulation.setDeviceMetricsOverride', {
        width, height: 900, deviceScaleFactor: 1, mobile: false,
      });
      results.push(await evaluate(`(() => {
        const left = selector => document.querySelector(selector).getBoundingClientRect().left;
        const computed = selector => getComputedStyle(document.querySelector(selector));
        const table = document.querySelector('.relay-layers');
        const rowCells = [...table.tBodies[0].rows].map(row => row.cells[0].getBoundingClientRect().left);
        const contextIcons = [...document.querySelectorAll('.relay-context-row svg')]
          .map(icon => icon.getBoundingClientRect().left);
        return {
          width: innerWidth,
          locale: document.documentElement.lang,
          rowCount: table.tBodies[0].rows.length,
          documentWidth: document.documentElement.scrollWidth,
          palette: {
            text: getComputedStyle(document.querySelector('.relay-view')).color,
            canvas: getComputedStyle(document.querySelector('.relay-view')).backgroundColor,
            card: getComputedStyle(document.querySelector('.relay-card')).backgroundColor,
            cardBorder: getComputedStyle(document.querySelector('.relay-card')).borderTopColor,
            statusError: getComputedStyle(document.querySelector('.relay-status[data-palette-probe=status-error]')).color,
            errorText: getComputedStyle(document.querySelector('.relay-error')).color,
            errorSurface: getComputedStyle(document.querySelector('.relay-error')).backgroundColor,
          },
          metrics: {
            pagePadding: computed('.relay-view').paddingTop,
            pageMinHeight: computed('.relay-view').minHeight,
            pageFont: computed('.relay-view').fontFamily,
            pageTracking: computed('.relay-view').letterSpacing,
            cardWidth: computed('.relay-card').width,
            cardBorder: computed('.relay-card').borderTopWidth,
            cardRadius: computed('.relay-card').borderTopLeftRadius,
            cardShadow: computed('.relay-card').boxShadow,
            headerHeight: computed('.relay-header').minHeight,
            headerGap: computed('.relay-header').gap,
            headerInset: computed('.relay-header').paddingLeft,
            titleSize: computed('.relay-header > strong').fontSize,
            titleTracking: computed('.relay-header > strong').letterSpacing,
            brandSize: computed('.relay-brand-mark').width,
            statusSize: computed('.relay-status').fontSize,
            contentInset: computed('.relay-content').paddingLeft,
            headingSize: computed('.relay-content h1').fontSize,
            headingLineHeight: computed('.relay-content h1').lineHeight,
            headingTracking: computed('.relay-content h1').letterSpacing,
            captionSize: computed('.relay-caption').fontSize,
            captionLineHeight: computed('.relay-caption').lineHeight,
            contextHeight: computed('.relay-context-row').minHeight,
            contextLabelWidth: computed('.relay-context-row > span').flexBasis,
            contextWeight: computed('.relay-context-row > strong').fontWeight,
            errorRadius: computed('.relay-error').borderTopLeftRadius,
            errorFontSize: computed('.relay-error').fontSize,
            footerHeight: computed('.relay-footer').minHeight,
            summaryHeight: computed('.relay-footer summary').minHeight,
            detailsPadding: computed('.relay-details').padding,
            tableLabelWidth: computed('.relay-layers th:first-child').width,
          },
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
    await command('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'dark' }] });
    const darkPalette = await evaluate(`(() => ({
      text: getComputedStyle(document.querySelector('.relay-view')).color,
      canvas: getComputedStyle(document.querySelector('.relay-view')).backgroundColor,
      card: getComputedStyle(document.querySelector('.relay-card')).backgroundColor,
      cardBorder: getComputedStyle(document.querySelector('.relay-card')).borderTopColor,
      statusError: getComputedStyle(document.querySelector('.relay-status[data-palette-probe=status-error]')).color,
      errorText: getComputedStyle(document.querySelector('.relay-error')).color,
      errorSurface: getComputedStyle(document.querySelector('.relay-error')).backgroundColor,
    }))()`);
    const darkMetrics = await evaluate(`(() => {
      const computed = selector => getComputedStyle(document.querySelector(selector));
      return {
        pagePadding: computed('.relay-view').paddingTop,
        cardWidth: computed('.relay-card').width,
        headerInset: computed('.relay-header').paddingLeft,
        contextLabelWidth: computed('.relay-context-row > span').flexBasis,
        titleSize: computed('.relay-header > strong').fontSize,
        contextWeight: computed('.relay-context-row > strong').fontWeight,
      };
    })()`);
    for (const sample of results) {
      sample.darkPalette = darkPalette;
      sample.darkMetrics = darkMetrics;
    }
    return results;
  });
  assert.equal(samples.length, 2);
  process.stdout.write(JSON.stringify(samples));
} finally {
  await new Promise(resolve => server.close(resolve));
}
