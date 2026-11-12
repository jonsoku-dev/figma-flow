/* Frozen native-getter complexity oracle; actual shared authoring functions, API-shaped host, no timing claims. */
const test = require('node:test');
const assert = require('node:assert/strict');
const {host, specification} = require('./helpers/finalize_native_build_reads.cjs');

function fixture(noteCount = 24) {
  const h = host(), page = h.initialPage;
  const targets = Array.from({length: noteCount}, (_, index) => {
    const node = h.figma.createFrame(); page.appendChild(node);
    node.setPluginData('semanticKey', 'target-' + index);
    return node;
  });
  const contract = {presentation: 'readable-specs', sourceHash: h.context.DRAFT.instance_sha256,
    font: {family: 'Inter', style: 'Regular'}, boardKey: 'fresh-readable-board',
    notes: targets.map((node, index) => ({key: 'entry-' + index, targetId: node.id, specification}))};
  return {...h, page, targets, contract, create() {return h.context.ensureDesignNoteBoard(h.figma, page, contract);}};
}

function entrySnapshot(board) {
  return board.children.map(node => ({id: node.id, characters: node.characters, key: node.getPluginData('semanticKey'),
    revision: node.getPluginData('figmaFlowSpecificationEntry'), link: node.getRangeHyperlink()}));
}

test('fresh real readable board authoring bounds native semantic-key getter work linearly', async () => {
  const observations = [];
  for (const notes of [24, 48]) {
    const h = fixture(notes), sourceNodes = 1 + h.page.findAll(() => true).length;
    h.counts.semanticKeys = 0;
    const result = await h.create();
    const observed = {notes, sourceNodes, semanticKeyReads: h.counts.semanticKeys};
    observations.push(observed);
    assert.equal(result.entries.length, notes);
    assert.equal(result.changed, notes);
    for (const entry of result.entries) {
      const text = h.nodes.get(entry.textNodeId);
      assert.equal(text.parent.id, result.boardId);
      assert.equal(text.characters, specification.title + '\n' + specification.display_text);
      assert.equal(text.getRangeHyperlink().value, entry.targetId);
    }
  }
  assert(observations.every(row => row.semanticKeyReads <= 4 * (row.sourceNodes + row.notes)),
    'Growing board child scans repeat native key getters: ' + JSON.stringify(observations));
});

test('readable annotation board-child id getters and child materializations stay linear per batch', async () => {
  const h = fixture(48), result = await h.create(), board = h.nodes.get(result.boardId);
  const annotations = result.entries.map((entry, index) => ({key: h.targets[index].data.semanticKey, specification,
    board: {boardId: result.boardId, textNodeId: entry.textNodeId, key: entry.key}}));
  let childIdReads = 0, childrenReads = 0, children = board.children;
  for (const child of children) {
    const stableId = child.id;
    Object.defineProperty(child, 'id', {configurable: true, get() {childIdReads++; return stableId;}});
  }
  Object.defineProperty(board, 'children', {configurable: true, get() {childrenReads++; return children;}, set(value) {children = value;}});
  const written = await h.context.ensureNativeAnnotations(h.figma, h.page, {presentation: 'readable-specs',
    sourceHash: h.contract.sourceHash, annotations});
  assert.equal(written.annotations.length, annotations.length);
  assert(childIdReads <= 4 * annotations.length && childrenReads <= 4,
    'Repeated native board child lookups during annotation batch: ' + JSON.stringify({notes: annotations.length, childIdReads, childrenReads}));
});

test('existing readable boards reject stale ownership without overwriting entries', async () => {
  const h = fixture(), result = await h.create(), board = h.nodes.get(result.boardId);
  board.setPluginData('designNoteBoard', JSON.stringify({pageId: h.page.id, sourceHash: 'different-owner'}));
  const before = entrySnapshot(board);
  await assert.rejects(h.create(), /ambiguous or unowned board/);
  assert.deepEqual(entrySnapshot(board), before);
});

test('supplied duplicate note keys and duplicate native child keys remain rejected', async () => {
  const fresh = fixture();
  fresh.contract.notes[1].key = fresh.contract.notes[0].key;
  await assert.rejects(fresh.create(), /unique keys/);
  assert.deepEqual(fresh.page.children.map(node => node.id), fresh.targets.map(node => node.id));
  const h = fixture(), result = await h.create(), board = h.nodes.get(result.boardId);
  const original = h.nodes.get(result.entries[0].textNodeId), duplicate = h.figma.createText();
  duplicate.characters = original.characters; duplicate.fontSize = original.fontSize;
  duplicate.setPluginData('semanticKey', original.data.semanticKey); board.appendChild(duplicate);
  const before = entrySnapshot(board);
  await assert.rejects(h.create(), /unknown or ambiguous board child/);
  assert.deepEqual(entrySnapshot(board), before);
});

test('fresh board failure rolls back only new board nodes and preserves existing targets', async () => {
  const h = fixture(), before = h.page.children.map(node => node.id);
  let calls = 0;
  h.contract.styleText = async () => {if (++calls === 5) throw Error('injected note styling failure');};
  await assert.rejects(h.create(), /injected note styling failure/);
  assert.deepEqual(h.page.children.map(node => node.id), before);
  assert(h.targets.every(node => node.parent === h.page && !node.removed));
});

test('board update rejects a concurrent font-await edit and retains the user text', async () => {
  const h = fixture(), result = await h.create(), board = h.nodes.get(result.boardId);
  const text = h.nodes.get(result.entries[0].textNodeId), ids = board.children.map(node => node.id);
  h.figma.loadFontAsync = async () => {text.characters = 'Concurrent human edit';};
  await assert.rejects(h.create(), /concurrent board preflight conflict/);
  assert.equal(text.characters, 'Concurrent human edit');
  assert.deepEqual(board.children.map(node => node.id), ids);
});
