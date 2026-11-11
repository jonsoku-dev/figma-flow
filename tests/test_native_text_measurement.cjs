/* Supplied Figma API model. Live measurements remain separate acceptance evidence. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const runtime = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

function fixture(failure) {
  const page = {children: [], selection: []}, instance = {layoutMode: 'HORIZONTAL', children: []};
  const original = {parent: instance, width: 81, height: 41, x: 12, y: 13, constraints: {horizontal: 'STRETCH', vertical: 'CENTER'},
    layoutSizingHorizontal: 'FILL', layoutSizingVertical: 'FILL', textAutoResize: 'HEIGHT', minWidth: 0, maxWidth: 81,
    fontName: {family: 'Variable face', style: 'Regular', variationSettings: {wght: 537, wdth: 88}}, fontSize: 14,
    lineHeight: {unit: 'PIXELS', value: 20.5}, letterSpacing: {unit: 'PERCENT', value: -1.2}, characters: 'Observed label',
    clone() {assert.fail('measurement must not clone inherited FILL');}};
  const before = {type: 'VECTOR'}, after = {type: 'TEXT'};
  instance.children = [before, original, after]; page.children.push(instance); page.selection = [original];
  let sample, container, sampleRemovals = 0, frameRemovals = 0, factories = 0;
  const writes = [], remove = node => {node.parent.children = node.parent.children.filter(item => item !== node);};
  const figma = {showUI() {}, ui: {postMessage() {}}, createFrame() {
    factories++; if (failure === 'frame') throw Error('frame unavailable');
    container = {parent: page, children: [], layoutMode: 'VERTICAL', appendChild(node) {
      if (failure === 'append') throw Error('reparent unavailable');
      remove(node); this.children.push(node); node.parent = this;
    }, remove() {frameRemovals++; remove(this);}};
    page.children.push(container); return container;
  }, createText() {
    factories++; if (failure === 'factory') throw Error('factory unavailable');
    sample = {parent: page, remove() {sampleRemovals++; remove(this);}}; page.children.push(sample);
    for (const field of ['fontName', 'fontSize', 'lineHeight', 'letterSpacing', 'characters', 'textAutoResize']) {
      let value;
      Object.defineProperty(sample, field, {get() {return value;}, set(next) {
        if (failure === field || field === 'textAutoResize' && failure === 'measure') throw Error(field + ' unavailable');
        value = next; writes.push(field);
        if (field === 'textAutoResize') {
          assert.equal(this.parent.layoutMode, 'NONE'); assert.equal(next, 'WIDTH_AND_HEIGHT');
          this.width = 128.375; this.height = this.characters.includes('\n') ? 41 : 20.5;
        }
      }});
    }
    for (const field of ['layoutSizingHorizontal', 'layoutSizingVertical']) Object.defineProperty(sample, field, {set() {assert.fail('fresh text needs no layout sizing setter');}});
    return sample;
  }};
  const host = vm.createContext({DRAFT: {}, __html__: '', figma}); vm.runInContext(runtime, host);
  return {host, page, instance, original, before, after, writes, get sample() {return sample;}, get container() {return container;},
    counts: () => ({sampleRemovals, frameRemovals, factories})};
}
function originalState(e) {return Object.fromEntries(Object.entries(e.original).filter(([key]) => key !== 'parent' && key !== 'clone'));}
function unchanged(e, before) {
  assert.deepEqual(e.instance.children, [e.before, e.original, e.after]); assert.deepEqual(e.page.children, [e.instance]);
  assert.deepEqual(e.page.selection, [e.original]); assert.equal(e.original.parent, e.instance); assert.deepEqual(originalState(e), before);
}

test('fresh TEXT copies observed uniform variable font and raw units without inheriting FILL or mutating its source', () => {
  for (const [leading, spacing] of [[{unit: 'PIXELS', value: 20.5}, {unit: 'PERCENT', value: -1.2}],
    [{unit: 'PERCENT', value: 145}, {unit: 'PIXELS', value: -0.25}], [{unit: 'AUTO'}, {unit: 'PIXELS', value: 0}]]) {
    const e = fixture(); e.original.lineHeight = leading; e.original.letterSpacing = spacing; const before = structuredClone(originalState(e));
    assert.deepEqual(plain(e.host.measureDraftNaturalWidth(e.original)), {naturalWidth: 128.375, naturalHeight: 20.5});
    assert.deepEqual(e.writes, ['fontName', 'fontSize', 'lineHeight', 'letterSpacing', 'characters', 'textAutoResize']);
    for (const field of ['fontName', 'fontSize', 'lineHeight', 'letterSpacing', 'characters']) assert.deepEqual(plain(e.sample[field]), e.original[field]);
    assert.notEqual(e.sample.fontName, e.original.fontName); assert.notEqual(e.sample.lineHeight, e.original.lineHeight);
    assert.equal(e.container.layoutMode, 'NONE'); assert.equal(e.container.visible, false);
    assert.deepEqual(e.counts(), {sampleRemovals: 1, frameRemovals: 1, factories: 2}); unchanged(e, before);
  }
});

test('explicit multiline text returns observed intrinsic height without imposing a single-line policy', () => {
  const e = fixture(); e.original.characters = 'First line\nSecond line';
  assert.deepEqual(plain(e.host.measureDraftNaturalWidth(e.original)), {naturalWidth: 128.375, naturalHeight: 41});
});

test('factory, reparent, font, style and measurement errors clean temporary nodes and preserve original context', () => {
  for (const failure of ['frame', 'factory', 'append', 'fontName', 'fontSize', 'lineHeight', 'letterSpacing', 'characters', 'measure']) {
    const e = fixture(failure), before = structuredClone(originalState(e)), result = e.host.measureDraftNaturalWidth(e.original);
    assert.equal(result.naturalWidth, null); assert.match(result.naturalWidthError, /unavailable/);
    assert.equal(e.counts().sampleRemovals, ['frame', 'factory'].includes(failure) ? 0 : 1);
    assert.equal(e.counts().frameRemovals, failure === 'frame' ? 0 : 1); unchanged(e, before);
  }
});

test('mixed or non-finite observed typography is rejected before creating measurement nodes', () => {
  for (const [field, value] of [['fontName', Symbol('mixed')], ['fontName', {family: 'Inter', style: 'Regular', variationSettings: {wght: NaN}}],
    ['fontSize', NaN], ['fontSize', 0], ['lineHeight', Symbol('mixed')], ['lineHeight', {unit: 'PERCENT', value: Infinity}],
    ['letterSpacing', Symbol('mixed')], ['letterSpacing', {unit: 'PIXELS', value: NaN}], ['characters', Symbol('mixed')]]) {
    const e = fixture(); e.original[field] = value;
    const result = e.host.measureDraftNaturalWidth(e.original);
    assert.equal(result.naturalWidth, null); assert.match(result.naturalWidthError, /Uniform observed native text/);
    assert.deepEqual(e.counts(), {sampleRemovals: 0, frameRemovals: 0, factories: 0});
    assert.deepEqual(e.page.children, [e.instance]); assert.deepEqual(e.instance.children, [e.before, e.original, e.after]);
  }
});
