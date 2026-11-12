/* Frozen API-shaped geometry oracle. A fractional native line-box ceil is separate from actual overlap. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const runtime = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
const LEADING = 23.390625;
const copy = value => JSON.parse(JSON.stringify(value));

function fixture(defect) {
  const font = {family: 'Inter', style: 'Regular'}, nodes = [];
  const page = {id: 'page', getPluginData() {return '';}, findAll() {return nodes;}};
  const context = vm.createContext({DRAFT: {scope: 'exploratory-only'}, __html__: '', figma: {showUI() {}, ui: {postMessage() {}}}});
  vm.runInContext(runtime, context);
  const style = {fontSize: 14, leading: 20, paddingX: 8, paddingY: 8, radius: 4};
  const candidate = {id: 'app', fonts: {body: font}, prototype: {states: [{id: 'idle'}], bindings: []},
    control_styles: {desktop: {Primary: style}, mobile: {Primary: style}}, state_layouts: {}};
  for (const [viewport, frameY] of [['desktop', 0], ['mobile', 1000]]) {
    const key = 'app.' + viewport + '.idle';
    const frame = {id: viewport, type: 'FRAME', parent: page, x: 0, y: frameY, width: 1200, height: 800, getPluginData: () => key};
    const layer = {id: 'policy', kind: 'text', value: 'Policy', x: 40, y: 153, w: 602, h: LEADING,
      size: 13, leading: LEADING, max_lines: 1, font: 'body', ink: 'ink'};
    const state = {width: 1200, height: 800, layers: [layer], control_boxes: {},
      product_buttons: {open: {box: [40, 176.390625, 64.21875, 44], variant: 'Primary', label: 'Open'}}};
    candidate.state_layouts[viewport] = {idle: state};
    const text = {id: key + '.policy', type: 'TEXT', parent: frame, x: 40, y: 153, width: 602, height: 24,
      characters: 'Policy', fontName: font, fontSize: 13, lineHeight: {unit: 'PIXELS', value: LEADING},
      letterSpacing: {unit: 'PIXELS', value: 0}, textAutoResize: 'HEIGHT', textAlignHorizontal: 'LEFT', getPluginData: () => key + '.policy'};
    const control = {id: key + '.open', type: 'INSTANCE', parent: frame, x: 40, y: 176.390625, width: 64.21875, height: 44,
      cornerRadius: 4, reactions: [], paddingLeft: 8, paddingRight: 8, paddingTop: 8, paddingBottom: 8, getPluginData: () => key + '.open'};
    const label = {id: key + '.open.label', type: 'TEXT', parent: control, x: 8, y: 12, width: 48.21875, height: 20,
      characters: 'Open', fontName: font, fontSize: 14, lineHeight: {unit: 'PIXELS', value: 20}, letterSpacing: {unit: 'PIXELS', value: 0},
      textAutoResize: 'HEIGHT', textAlignHorizontal: 'CENTER', getPluginData: () => key + '.open.label'};
    control.children = [label];
    if (defect === 'control-up' || defect === 'control-down') control.y += defect === 'control-up' ? -.25 : .25;
    if (defect === 'authored-overlap') {state.product_buttons.open.box[1] -= .25; control.y -= .25;}
    if (defect === 'two-lines') text.height = 48;
    if (defect === 'height-not-leading') {layer.h = 23.5; state.product_buttons.open.box[1] = control.y = layer.y + layer.h;}
    if (['text-width', 'text-x', 'text-y'].includes(defect)) text[{'text-width': 'width', 'text-x': 'x', 'text-y': 'y'}[defect]] += .25;
    if (defect === 'not-ceil') text.height = 24.25;
    if (defect === 'multiple-allowed-lines') layer.max_lines = 2;
    if (defect === 'unspecified-lines') delete layer.max_lines;
    nodes.push(frame, text, control, label);
  }
  return {context, page, candidate, nodes, validate() {return context.validateDraftGeometry(page, [candidate], false);}};
}

test('only fractional single-line native height ceil may touch the unchanged control allocation', () => {
  const h = fixture();
  const before = h.nodes.map(node => copy({x: node.x, y: node.y, w: node.width, h: node.height}));
  assert.doesNotThrow(() => h.validate());
  assert.deepEqual(h.nodes.map(node => ({x: node.x, y: node.y, w: node.width, h: node.height})), before,
    'validation must retain full raw native geometry');
});

test('actual source/native collisions and subpixel coordinate drift remain rejected', () => {
  for (const defect of ['control-up', 'control-down', 'authored-overlap', 'two-lines', 'height-not-leading',
    'text-width', 'text-x', 'text-y', 'not-ceil', 'multiple-allowed-lines', 'unspecified-lines']) {
    assert.throws(() => fixture(defect).validate(), /native screen text intersects whole control/, defect);
  }
});
