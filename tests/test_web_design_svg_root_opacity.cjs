const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../figma-bridge/web_design.js'), 'utf8');

class MockNode {
  constructor(type) {
    this.type = type;
    this.id = `${type}-1`;
    this.name = type;
    this.x = 0;
    this.y = 0;
    this.width = 0;
    this.height = 0;
    this.opacity = 1;
    this.fills = [];
    this.strokes = [];
    this.children = [];
    this.pluginData = {};
  }
  resize(width, height) { this.width = width; this.height = height; }
  appendChild(node) { node.parent = this; this.children.push(node); }
  setPluginData(key, value) { this.pluginData[key] = value; }
  getPluginData(key) { return this.pluginData[key] || ''; }
  findAll(predicate) {
    return this.children.flatMap(child => [
      ...(predicate(child) ? [child] : []),
      ...child.findAll(predicate),
    ]);
  }
}

function importedVector(element) {
  const page = new MockNode('PAGE');
  const vector = new MockNode('VECTOR');
  const figma = {
    currentPage: page,
    createFrame: () => new MockNode('FRAME'),
    createNodeFromSvg: svg => { vector.svg = svg; return vector; },
  };
  const context = vm.createContext({ figma });
  vm.runInContext(source, context);
  const screen = {
    id: 'WEB-svg',
    title: 'SVG opacity',
    layout: { width: 240, height: 160 },
    elements: [element],
  };
  context.webCreateScreen(figma, screen, { graph_id: 'svg-opacity', graph_sha256: 'a'.repeat(64), assets: {} },
    new Set(), new Map(), new Map(), 0, {}, {});
  return vector;
}

test('SVG root CSS opacity is applied on the native VECTOR while group opacity stays in SVG', () => {
  const svg = '<svg viewBox="0 0 20 20"><g opacity="0.5"><path d="M0 0h20v20H0z"/></g></svg>';
  const vector = importedVector({
    id: 'hero-art', kind: 'vector', path: [], box: { x: 12, y: 8, width: 20, height: 20 },
    svg, paint: { opacity: 0.4 },
  });

  assert.equal(vector.opacity, 0.4);
  assert.equal(vector.svg, svg);
  assert.deepEqual(vector.fills, []);
  assert.deepEqual(vector.strokes, []);
});
