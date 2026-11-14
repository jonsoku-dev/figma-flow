const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../tools/web_design_capture.js'), 'utf8');

test('overlong supported filter chains stay visible and report their unsupported treatment', () => {
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
  const document = { body, documentElement: { clientWidth: 390, scrollHeight: 844 }, title: 'SVG filter limit' };
  const baseStyle = {
    display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'transparent', backgroundImage: 'none',
    borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px', borderTopColor: 'rgb(0,0,0)',
    fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px', textAlign: 'left', color: '#000',
    overflowX: 'visible', overflowY: 'visible', maskImage: 'none', filter: 'none', boxShadow: 'none', objectFit: 'fill',
  };
  const imageStyle = { ...baseStyle, filter: Array(17).fill('brightness(0)').join(' ') };
  const context = vm.createContext({
    document,
    location: { origin: 'http://localhost:8000', pathname: '/' },
    innerHeight: 844, innerWidth: 390, scrollX: 0, scrollY: 0,
    getComputedStyle: element => element === image ? imageStyle : baseStyle,
  });
  vm.runInContext(source, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-svg-filter-limit' })));
  assert.equal(captured.images.length, 1);
  assert.equal(captured.images[0].paint.cssFilter, undefined);
  assert.equal(captured.limitations.includes('unsupported CSS filter chain'), true);
});
