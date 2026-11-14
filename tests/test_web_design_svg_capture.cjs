const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../tools/web_design_capture.js'), 'utf8');

test('external image capture preserves supported SVG color filters and opacity', () => {
  const rect = { x: 10, y: 20, width: 112, height: 40 };
  const image = {
    nodeType: 1, tagName: 'IMG', textContent: '', children: [], childNodes: [],
    complete: true, naturalWidth: 113, naturalHeight: 48, currentSrc: 'https://assets.example/logo.svg',
    src: 'https://assets.example/logo.svg', alt: 'Logo',
    getBoundingClientRect: () => rect, getClientRects: () => [rect], getAttribute: () => null,
  };
  const body = {
    tagName: 'BODY', textContent: '', children: [image], childNodes: [image], getAttribute: () => null,
    getBoundingClientRect: () => ({ x: 0, y: 0, width: 390, height: 844 }), getClientRects: () => [],
  };
  const document = { body, documentElement: { clientWidth: 390, scrollHeight: 844 }, title: 'SVG filter' };
  const baseStyle = {
    display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'transparent', backgroundImage: 'none',
    borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px', borderTopColor: 'rgb(0,0,0)',
    fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px', textAlign: 'left', color: '#000',
    overflowX: 'visible', overflowY: 'visible', maskImage: 'none', filter: 'none', boxShadow: 'none', objectFit: 'fill',
  };
  const imageStyle = { ...baseStyle, opacity: '0.3', filter: 'brightness(0) grayscale(1) invert(1)' };
  const context = vm.createContext({
    document,
    location: { origin: 'http://localhost:8000', pathname: '/' },
    innerHeight: 844, innerWidth: 390, scrollX: 0, scrollY: 0,
    getComputedStyle: element => element === image ? imageStyle : baseStyle,
  });
  vm.runInContext(source, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-svg-filter' })));
  const [candidate] = captured.images;
  assert.deepEqual(candidate.paint.cssFilter, [
    { name: 'brightness', value: 0 },
    { name: 'grayscale', value: 1 },
    { name: 'invert', value: 1 },
  ]);
  assert.equal(candidate.paint.svgSilhouetteColor, '#ffffff');
  assert.equal(candidate.paint.opacity, 0.3);
  assert.equal(captured.limitations.includes('unsupported CSS filter chain'), false);
});
