const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const captureSource = fs.readFileSync(require.resolve('../tools/web_design_capture.js'), 'utf8');

function capture(canvas) {
  const rect = { x: 12, y: 24, width: 120, height: 60 };
  canvas.nodeType = 1;
  canvas.tagName = 'CANVAS';
  canvas.textContent = '';
  canvas.children = [];
  canvas.childNodes = [];
  canvas.getBoundingClientRect = () => rect;
  canvas.getClientRects = () => [rect];
  canvas.getAttribute = () => null;
  const body = { tagName: 'BODY', textContent: '', childNodes: [canvas], children: [canvas], getAttribute: () => null,
    getBoundingClientRect: () => ({ x: 0, y: 0, width: 400, height: 800 }), getClientRects: () => [] };
  const document = { body, documentElement: { clientWidth: 400, scrollHeight: 800 }, title: 'Canvas sample' };
  const style = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'transparent',
    backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px',
    borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px',
    textAlign: 'left', color: 'rgb(0,0,0)', overflowX: 'visible', overflowY: 'visible', maskImage: 'none',
    filter: 'none', boxShadow: 'none' };
  const context = vm.createContext({ document, location: { origin: 'http://localhost:3000', pathname: '/' },
    innerHeight: 600, innerWidth: 400, scrollX: 0, scrollY: 0, devicePixelRatio: 2, getComputedStyle: () => style });
  vm.runInContext(captureSource, context);
  return JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-canvas' })));
}

test('canvas capture preserves real PNG pixels and intrinsic dimensions', () => {
  const dataUrl = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jV9sAAAAASUVORK5CYII=';
  const result = capture({ width: 240, height: 120, toDataURL: type => { assert.equal(type, 'image/png'); return dataUrl; } });
  assert.equal(result.canvases.length, 1);
  assert.equal(result.canvases[0].box.width, 120);
  assert.equal(result.canvases[0].canvas.width, 240);
  assert.equal(result.canvases[0].canvas.devicePixelRatio, 2);
  assert.equal(result.canvases[0].canvas.pixelRatioX, 2);
  assert.equal(result.canvases[0].canvas.dataUrl, dataUrl);
  assert.deepEqual(result.limitations, []);
});

test('canvas export failure remains explicit without fabricated pixels', () => {
  const result = capture({ width: 240, height: 120, toDataURL() { const error = new Error('tainted'); error.name = 'SecurityError'; throw error; } });
  assert.equal(result.canvases[0].canvas.status, 'unavailable');
  assert.equal(result.canvases[0].canvas.reason, 'canvas is not origin-clean');
  assert.equal('dataUrl' in result.canvases[0].canvas, false);
  assert.deepEqual(result.limitations, ['canvas pixels unavailable']);
});

test('oversized canvas pixels are unavailable instead of exceeding the asset budget', () => {
  const result = capture({ width: 240, height: 120, toDataURL: () => 'data:image/png;base64,' + 'A'.repeat(11_000_000) });
  assert.equal(result.canvases[0].canvas.status, 'unavailable');
  assert.equal(result.canvases[0].canvas.reason, 'canvas PNG exceeds the 8 MB asset limit');
  assert.equal('dataUrl' in result.canvases[0].canvas, false);
});
