/* Normal makeDraft + production helpers; the API-shaped host does not simulate native reflow. */
const test = require('node:test');
const assert = require('node:assert/strict');
const {host, packet} = require('./helpers/finalize_native_build_reads.cjs');

function declaredPacket() {
  const draft = packet(2);
  for (const states of Object.values(draft.candidates[0].state_layouts)) for (const state of Object.values(states)) {
    state.layers.push(
      {id: 'gap-a', kind: 'rect', x: 20, y: 240, w: 20, h: 20, fill: 'ink'},
      {id: 'gap-b', kind: 'rect', x: 52, y: 240, w: 20, h: 20, fill: 'ink'});
    state.containers.push({key: 'gap-row', kind: 'auto-layout', children: ['gap-a', 'gap-b'], fill: 'paper',
      layout: {direction: 'HORIZONTAL', gap: 12, padding: [4, 8, 4, 8], width: 'fixed', height: 'hug'}});
  }
  return draft;
}

async function unrelated(h) {
  const node = h.figma.createRectangle();
  h.initialPage.appendChild(node);
  node.setPluginData('semanticKey', 'unrelated.keep');
  node.x = 73;
  const collection = h.figma.variables.createVariableCollection('Unrelated');
  const variable = h.figma.variables.createVariable('keep spacing', collection, 'FLOAT');
  variable.setValueForMode(collection.defaultModeId, 99);
  node.setBoundVariable('itemSpacing', variable);
  return {node, variable, alias: node.boundVariables.itemSpacing};
}

async function assertFloat(h, node, field, value) {
  const alias = node.boundVariables[field];
  assert(alias && alias.type === 'VARIABLE_ALIAS', `${node.getPluginData('semanticKey')}.${field} must bind a FLOAT ${value} variable`);
  const variable = await h.figma.variables.getVariableByIdAsync(alias.id);
  assert(variable, 'bound variable must exist in the actual variable store');
  assert.deepEqual(variable.resolveForConsumer(node), {resolvedType: 'FLOAT', value});
  return variable;
}

function rows(page) {
  const nodes = page.findAll(node => node.getPluginData('semanticKey').endsWith('.gap-row'));
  assert.equal(nodes.length, 4, 'both viewports and states must build declared frames');
  return nodes;
}

test('normal makeDraft binds declared positive gap and padding to actual FLOAT variables', async () => {
  const h = host(declaredPacket());
  const page = await h.context.makeDraft();
  const raw = await h.context.readDraft(page);
  for (const node of rows(page)) {
    const spacing = await assertFloat(h, node, 'itemSpacing', 12);
    for (const [field, value] of [['paddingTop', 4], ['paddingRight', 8], ['paddingBottom', 4], ['paddingLeft', 8]])
      await assertFloat(h, node, field, value);
    const observed = raw.nodes.find(row => row.id === node.id);
    assert.equal(observed.boundVariables.itemSpacing.id, spacing.id, 'normal fresh native read must report the actual binding');
    const variable = raw.variables.find(row => row.id === spacing.id);
    assert.equal(variable.resolvedType, 'FLOAT');
    let current = variable, value;
    const seen = new Set();
    while (current) {
      assert(!seen.has(current.id), 'fresh raw binding must not contain an alias cycle');
      seen.add(current.id);
      assert.equal(current.resolvedType, 'FLOAT');
      const collection = raw.collections.find(row => row.id === current.variableCollectionId);
      assert(collection, 'fresh raw alias target must have its actual collection');
      value = current.valuesByMode[collection.defaultModeId];
      if (value?.type !== 'VARIABLE_ALIAS') break;
      current = raw.variables.find(row => row.id === value.id);
      assert(current, 'fresh raw alias target must exist');
    }
    assert.equal(value, 12, 'fresh raw alias chain must resolve to the authored gap');
  }
});

test('normal fresh read preserves declared frame/leaf geometry, paint and existing control bindings', async () => {
  const h = host(declaredPacket());
  const keep = await unrelated(h);
  const page = await h.context.makeDraft();
  assert.equal(h.figma.currentPage, page);
  assert.equal(JSON.parse(page.getPluginData('figmaFlowDraftReviewReservation')).state, 'complete');
  const raw = await h.context.readDraft(page);
  for (const node of rows(page)) {
    assert.equal(node.type, 'FRAME');
    assert.equal(node.layoutMode, 'HORIZONTAL');
    assert.equal(node.itemSpacing, 12);
    assert.deepEqual([node.x, node.y, node.width, node.height], [12, 236, 68, 28]);
    assert.equal(node.parent.type, 'FRAME');
    assert.equal(node.parent.width, 390);
    assert.equal(node.parent.height, 844);
    assert.equal(node.fills[0].type, 'SOLID');
    assert.deepEqual([node.fills[0].color.r, node.fills[0].color.g, node.fills[0].color.b], [1, 1, 1]);
    assert.deepEqual(node.children.map(child => [child.x, child.y, child.width, child.height, child.layoutPositioning]),
      [[8, 4, 20, 20, 'AUTO'], [40, 4, 20, 20, 'AUTO']]);
    const observed = raw.nodes.find(row => row.id === node.id);
    assert.deepEqual([observed.x, observed.y, observed.width, observed.height, observed.itemSpacing], [12, 236, 68, 28, 12]);
    for (const child of node.children) {
      const leaf = raw.nodes.find(row => row.id === child.id);
      assert.equal(leaf.parentId, node.id);
      assert.deepEqual([leaf.x, leaf.y, leaf.width, leaf.height], [child.x, child.y, 20, 20]);
    }
  }
  const control = page.findOne(node => node.getPluginData('semanticKey') === 'app.desktop.component.Primary');
  await assertFloat(h, control, 'paddingLeft', 8);
  assert.equal(keep.node.parent, h.initialPage);
  assert.equal(keep.node.x, 73);
  assert.deepEqual(keep.node.boundVariables.itemSpacing, keep.alias);
  await assertFloat(h, keep.node, 'itemSpacing', 99);
  const first = raw.nodes.find(row => row.id === control.id);
  control.x += 7;
  const second = await h.context.readDraft(page);
  assert.equal(second.nodes.find(row => row.id === control.id).x, first.x + 7, 'later reads must observe actual getter changes');
  assert.equal(first.x, control.x - 7, 'earlier evidence must remain an independent snapshot');
});

test('normal makeDraft rejects invalid gap and contradictory flow before page creation, preserving unrelated bindings', async () => {
  for (const defect of ['negative-gap', 'nonfinite-gap', 'wrong-flow']) {
    const draft = declaredPacket(), state = draft.candidates[0].state_layouts.desktop.s0;
    const declaration = state.containers.find(item => item.key === 'gap-row');
    if (defect === 'wrong-flow') state.layers.find(layer => layer.id === 'gap-b').x += 10;
    else declaration.layout.gap = defect === 'negative-gap' ? -1 : Infinity;
    const h = host(draft), keep = await unrelated(h);
    const before = [...h.nodes.keys()];
    await assert.rejects(h.context.makeDraft(), /invalid auto-layout container declaration|declared flow contradicts pinned geometry/, defect);
    assert.deepEqual([...h.nodes.keys()], before, defect + ': rejection must precede node creation');
    assert.equal(h.figma.currentPage, h.initialPage);
    assert.deepEqual(h.figma.root.children, [h.initialPage]);
    assert.equal(keep.node.parent, h.initialPage);
    assert.deepEqual(keep.node.boundVariables.itemSpacing, keep.alias);
    assert.equal(await h.figma.variables.getVariableByIdAsync(keep.variable.id), keep.variable);
    await assertFloat(h, keep.node, 'itemSpacing', 99);
  }
});
