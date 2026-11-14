const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../tools/web_design_capture.js'), 'utf8');

function element(tag, rect, styles = {}, children = []) {
  return {
    tagName: tag.toUpperCase(), nodeType: 1, rect, styles, children, childNodes: children,
    textContent: '',
    getBoundingClientRect() { return this.rect; },
    getClientRects() { return [this.rect]; },
    getAttribute() { return null; },
  };
}

function capture(overflowX, overflowY) {
  const neighbor = element('article', { x: 347, y: 455, width: 240, height: 100 }, { backgroundColor: 'rgb(20,20,20)' });
  const rail = element('ul', { x: 64, y: 405, width: 262, height: 228 }, {
    backgroundColor: 'rgb(255,255,255)', overflowX, overflowY,
  }, [neighbor]);
  const body = element('body', { x: 0, y: 0, width: 390, height: 844 }, {
    backgroundColor: 'rgb(255,255,255)', overflowX: 'visible', overflowY: 'visible',
  }, [rail]);
  const documentElement = { clientWidth: 390, scrollHeight: 844 };
  const context = vm.createContext({
    document: { body, documentElement, title: 'Scroll rail capture' },
    location: { origin: 'https://example.test', pathname: '/' },
    innerWidth: 390, innerHeight: 844, scrollX: 0, scrollY: 0,
    getComputedStyle(node) { return { ...baseStyle, ...node.styles }; },
  });
  vm.runInContext(source, context);
  return JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-scroll-rail' })));
}

const baseStyle = {
  display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'rgba(0, 0, 0, 0)',
  backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none',
  borderTopLeftRadius: '0px', borderTopColor: 'rgb(0, 0, 0)',
  fontFamily: 'Arial', fontWeight: '400', fontSize: '16px', lineHeight: '19px',
  textAlign: 'left', color: 'rgb(0, 0, 0)', maskImage: 'none', filter: 'none', boxShadow: 'none',
};

test('captured frames clip content only when both computed overflow axes clip', () => {
  for (const [overflowX, overflowY] of [['auto', 'hidden'], ['scroll', 'auto'], ['clip', 'hidden'], ['hidden', 'clip']]) {
    const captured = capture(overflowX, overflowY);
    const rail = captured.screen.elements.find(item => item.name === 'ul');
    const neighbor = captured.screen.elements.find(item => item.name === 'article');
    assert.ok(rail, `${overflowX}/${overflowY} rail frame was captured`);
    assert.equal(rail.clipsContent, true, `${overflowX}/${overflowY} clips both axes`);
    assert.ok(neighbor.path.includes(rail.id), 'off-rail neighbor remains a child of the clipped rail');
  }

  for (const [overflowX, overflowY] of [['visible', 'clip'], ['clip', 'visible'], ['visible', 'visible']]) {
    const captured = capture(overflowX, overflowY);
    const rail = captured.screen.elements.find(item => item.name === 'ul');
    assert.ok(rail, `${overflowX}/${overflowY} rail frame was captured`);
    assert.equal(rail.clipsContent, false, `${overflowX}/${overflowY} does not clip both axes`);
  }
});
