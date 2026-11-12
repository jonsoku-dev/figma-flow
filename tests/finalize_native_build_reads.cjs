/* Frozen complexity oracle: actual normal makeDraft + native reader, API-shaped getters, no wall-clock proof. */
const test = require('node:test');
const assert = require('node:assert/strict');
const {host, packet, specification} = require('./helpers/finalize_native_build_reads.cjs');
const total = counts => [...counts.values()].reduce((sum, count) => sum + count, 0);

async function build(stateCount = 6, corrupt = null) {
  const h = host(packet(stateCount), corrupt);
  const page = await h.context.makeDraft();
  assert.equal(page.parent, h.figma.root);
  assert.equal(page.getPluginData('figma-flow-direction-review-v1'), h.context.DRAFT.instance_sha256);
  assert.equal(JSON.parse(page.getPluginData('figmaFlowDraftReviewReservation')).state, 'complete');
  assert.equal(h.figma.currentPage, page);
  return {...h, page};
}

test('normal multi-screen makeDraft bounds full native getter work linearly in final node count', async () => {
  for (const stateCount of [2, 6]) {
    const h = await build(stateCount);
    const instances = h.page.findAll(node => node.type === 'INSTANCE').length;
    const texts = h.page.findAll(node => node.type === 'TEXT').length;
    const observed = {screens: stateCount * 2, instances, texts, mainReads: total(h.counts.main), textSegmentReads: total(h.counts.segments)};
    // Two full snapshots plus constant palette validation fit this budget; one snapshot per screen does not.
    assert(observed.mainReads <= 2 * instances + 4 && observed.textSegmentReads <= 2 * texts,
      'Repeated page-wide native reads during normal build: ' + JSON.stringify(observed));
  }
});

test('actual native annotation authoring indexes page semantic getters once for a note batch', async () => {
  const h = await build();
  const all = [h.page, ...h.page.findAll(() => true)];
  const annotations = all.filter(node => /^app\.(desktop|mobile)\.s\d+(\.open)?$/.test(node.data.semanticKey || ''))
    .map(node => ({key: node.data.semanticKey, label: 'Read oracle note for ' + node.data.semanticKey}));
  assert.equal(annotations.length, 24);
  h.counts.semanticKeys = 0;
  const result = await h.context.ensureNativeAnnotations(h.figma, h.page, {annotations});
  assert.equal(result.annotations.length, annotations.length);
  assert(h.counts.semanticKeys <= 2 * all.length + annotations.length,
    'Repeated page-wide annotation key getters: ' + JSON.stringify({nodes: all.length, notes: annotations.length, semanticKeyReads: h.counts.semanticKeys}));
});

test('readable native specification authoring also bounds semantic getter work for a whole batch', async () => {
  const h = await build();
  const targets = h.page.findAll(node => /^app\.(desktop|mobile)\.s\d+(\.open)?$/.test(node.data.semanticKey || ''));
  const notes = targets.map(node => ({key: node.data.semanticKey, targetId: node.id, specification}));
  const board = await h.context.ensureDesignNoteBoard(h.figma, h.page, {presentation: 'readable-specs',
    sourceHash: h.context.DRAFT.instance_sha256, font: {family: 'Inter', style: 'Regular'},
    boardKey: 'readable-performance-notes', notes});
  const annotations = targets.map(node => {
    const entry = board.entries.find(entry => entry.targetId === node.id);
    return {key: node.data.semanticKey, specification,
      expected_legacy: node.annotations.map((annotation, index) => ({index, annotation})),
      board: {boardId: board.boardId, textNodeId: entry.textNodeId, key: entry.key}};
  });
  const nodeCount = 1 + h.page.findAll(() => true).length;
  h.counts.semanticKeys = 0;
  const result = await h.context.ensureNativeAnnotations(h.figma, h.page, {presentation: 'readable-specs',
    sourceHash: h.context.DRAFT.instance_sha256, annotations});
  assert.equal(result.annotations.length, annotations.length);
  // Board ownership/link checks have a constant number of key getters per note in addition to page indexing.
  assert(h.counts.semanticKeys <= 2 * nodeCount + 8 * annotations.length,
    'Repeated page-wide readable specification key getters: ' + JSON.stringify({nodes: nodeCount, notes: annotations.length, semanticKeyReads: h.counts.semanticKeys}));
});

test('independent readDraft after completed build reads changed native getters afresh', async () => {
  const h = await build();
  const title = h.page.findOne(node => node.data.semanticKey === 'app.desktop.s0.title');
  const control = h.page.findOne(node => node.data.semanticKey === 'app.desktop.s0.open');
  const otherMain = h.page.findOne(node => node.data.semanticKey === 'app.mobile.component.Primary');
  const container = title.parent;
  title.characters = 'Changed after build'; title.x += 7;
  control.main = otherMain;
  container.overflowDirection = 'VERTICAL';
  const mainBefore = h.counts.main.get(control.id) || 0;
  const segmentsBefore = h.counts.segments.get(title.id) || 0;
  const first = await h.context.readDraft(h.page);
  const byId = new Map(first.nodes.map(row => [row.id, row]));
  assert.equal(byId.get(title.id).characters, 'Changed after build');
  assert.equal(byId.get(title.id).x, title.x);
  assert.equal(byId.get(control.id).mainComponentId, otherMain.id);
  assert.equal(byId.get(container.id).overflowDirection, 'VERTICAL');
  assert(h.counts.main.get(control.id) > mainBefore, 'final read must invoke the live main component getter');
  assert(h.counts.segments.get(title.id) > segmentsBefore, 'final read must invoke the live text segment getter');
  title.characters = 'Changed again';
  const second = await h.context.readDraft(h.page);
  assert.equal(second.nodes.find(row => row.id === title.id).characters, 'Changed again');
  assert.equal(byId.get(title.id).characters, 'Changed after build', 'earlier evidence must remain an independent snapshot');
});

test('normal build rejects native container parent/type/clip/axis drift and restores page ownership', async () => {
  for (const [name, corrupt, pattern] of [
    ['parent', (node, page) => page.appendChild(node), /native container parent differs|outside the screen|native parent differs/],
    ['type', node => {node.type = 'GROUP';}, /native container type differs|native scroll clip/],
    ['clip', node => {node.clipsContent = false;}, /frame clip differs|native scroll clip/],
    ['axis', node => {node.overflowDirection = 'VERTICAL';}, /scroll overflow differs|native scroll clip/],
    ['missing axis', node => {delete node.overflowDirection;}, /scroll overflow differs|native scroll clip/]
  ]) {
    const h = host(packet(), corrupt);
    h.initialPage.setPluginData('unrelated', 'keep');
    await assert.rejects(h.context.makeDraft(), pattern, name + ' drift was admitted');
    assert.equal(h.figma.currentPage, h.initialPage, name + ': rollback must restore the previous active page');
    assert.deepEqual(h.figma.root.children.map(node => node.id), [h.initialPage.id], name + ': failed owned build must remove only its new page');
    assert.equal(h.initialPage.getPluginData('unrelated'), 'keep');
  }
});
