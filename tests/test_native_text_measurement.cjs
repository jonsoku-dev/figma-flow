/* API-shaped Auto Layout constraints; live Figma measurements are separate evidence. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const runtime = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');

function fixture(failure) {
  const page = {children: [], selection: []};
  const instance = {layoutMode: 'HORIZONTAL', children: []};
  const original = {parent: instance, width: 81, height: 41, x: 12, y: 13, constraints: {horizontal: 'STRETCH', vertical: 'CENTER'}, layoutSizingHorizontal: 'FILL', textAutoResize: 'HEIGHT', minWidth: 0, maxWidth: 81};
  const before = {type: 'VECTOR'}, after = {type: 'TEXT'};
  instance.children = [before, original, after];
  page.children.push(instance); page.selection = [original];
  let probe, container, cloneRemovals = 0, frameRemovals = 0;
  const remove = node => {node.parent.children = node.parent.children.filter(item => item !== node);};
  original.clone = () => {
    if (failure === 'clone') throw Error('clone unavailable');
    probe = {...original, constraints: {...original.constraints}, remove() {cloneRemovals++; remove(this);}};
    instance.children.splice(2, 0, probe);
    Object.defineProperty(probe, 'textAutoResize', {get() {return this.mode;}, set(value) {
      if (failure === 'measure') throw Error('measurement unavailable');
      this.mode = value;
      const constrained = this.parent.layoutMode !== 'NONE' && this.layoutSizingHorizontal === 'FILL';
      this.width = constrained ? 81 : 128.375;
      this.height = constrained ? 41 : 20.5;
    }});
    return probe;
  };
  const figma = {showUI() {}, ui: {postMessage() {}}, createFrame() {
    container = {parent: page, children: [], layoutMode: 'VERTICAL', appendChild(node) {
      if (failure === 'append') throw Error('reparent unavailable');
      remove(node); this.children.push(node); node.parent = this;
    }, remove() {frameRemovals++; remove(this);}};
    page.children.push(container); return container;
  }};
  const host = vm.createContext({DRAFT: {}, __html__: '', figma});
  vm.runInContext(runtime, host);
  return {host, page, instance, original, before, after, get probe() {return probe;}, get container() {return container;}, counts: () => ({cloneRemovals, frameRemovals})};
}
const plain = value => JSON.parse(JSON.stringify(value));
function unchanged(e) {
  assert.deepEqual(e.instance.children, [e.before, e.original, e.after]);
  assert.deepEqual(e.page.children, [e.instance]);
  assert.deepEqual(e.page.selection, [e.original]);
  assert.equal(e.original.parent, e.instance);
  assert.deepEqual({width: e.original.width, height: e.original.height, x: e.original.x, y: e.original.y, constraints: e.original.constraints, sizing: e.original.layoutSizingHorizontal, resize: e.original.textAutoResize, min: e.original.minWidth, max: e.original.maxWidth},
    {width: 81, height: 41, x: 12, y: 13, constraints: {horizontal: 'STRETCH', vertical: 'CENTER'}, sizing: 'FILL', resize: 'HEIGHT', min: 0, max: 81});
}

test('intrinsic text width escapes parent FILL and returns true single-line geometry without altering the original', () => {
  const e = fixture();
  assert.deepEqual(plain(e.host.measureDraftNaturalWidth(e.original)), {naturalWidth: 128.375, naturalHeight: 20.5});
  assert.equal(e.container.layoutMode, 'NONE');
  assert.equal(e.container.visible, false);
  assert.equal(e.probe.minWidth, null); assert.equal(e.probe.maxWidth, null);
  assert.equal(e.probe.minHeight, null); assert.equal(e.probe.maxHeight, null);
  assert.deepEqual(e.counts(), {cloneRemovals: 1, frameRemovals: 1});
  unchanged(e);
});

test('clone, reparent and measurement errors remove every temporary node and preserve original context', () => {
  for (const failure of ['clone', 'append', 'measure']) {
    const e = fixture(failure), result = e.host.measureDraftNaturalWidth(e.original);
    assert.equal(result.naturalWidth, null);
    assert.match(result.naturalWidthError, /unavailable/);
    assert.deepEqual(e.counts(), {cloneRemovals: failure === 'clone' ? 0 : 1, frameRemovals: 1});
    unchanged(e);
  }
});
