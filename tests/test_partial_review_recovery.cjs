const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../figma-bridge/direction_review.js'), 'utf8');
const packet = {
  schema: 'figma-flow-native-direction-review-v1', scope: 'exploratory-only', production_admitted: false,
  fileKey: 'fixture-file', packet_sha256: 'a'.repeat(64), instance_sha256: 'b'.repeat(64), layout_sha256: 'c'.repeat(64),
  candidates: [{id: 'fixture', title: 'Interrupted review fixture', entry_state: 'home', prototype: {}}]
};

function harness(pages = []) {
  const writes = [];
  const figma = {fileKey: packet.fileKey, root: {children: pages}, currentPage: null,
    showUI() {}, ui: {postMessage() {}},
    setCurrentPageAsync: async page => {figma.currentPage = page;},
    createPage() { throw new Error('unexpected page creation'); }};
  const context = vm.createContext({DRAFT: structuredClone(packet), __html__: '', figma});
  vm.runInContext(source, context);
  return {context, writes};
}

function page(id, name = '') {
  const data = new Map(), writes = [];
  return {id, name, type: 'PAGE', children: [], writes,
    getPluginData(key) {return data.get(key) || '';},
    setPluginData(key, value) {writes.push([key, value]); if(value)data.set(key, value);else data.delete(key);},
    findAll() {return this.children;}, async loadAsync() {}, remove() {writes.push(['remove']);}};
}

function complete(page, owner = packet.instance_sha256) {
  page.setPluginData('figma-flow-direction-review-v1', owner);
  page.setPluginData('packet_sha256', packet.packet_sha256);
  page.setPluginData('draftCanonicalBindings', '[]');
  page.setPluginData('draftNoteFrames', JSON.stringify({fixture: {boardId: 'board', entries: [{key: 'home'}]}}));
  page.setPluginData('draftPalettes', JSON.stringify({fixture: {libraryId: 'library', samples: [{instanceId: 'sample'}]}}));
  page.setPluginData('draftTextStyles', JSON.stringify(['style-id']));
  page.setPluginData('scope', 'exploratory-only');
  page.setPluginData('productionAdmitted', 'false');
  page.children.push({id: 'entry-frame', getPluginData(key) {return key === 'semanticKey' ? 'fixture.desktop.home' : '';}});
  page.flowStartingPoints = [{nodeId: 'entry-frame', name: 'Review start'}];
}

function makeDraftAdmissionReady(h) {
  const candidate = h.context.DRAFT.candidates[0];
  candidate.foundations = {roles: []};
  candidate.foundationBindings = [];
  h.context.admitDraftColorConsumers = () => [];
  h.context.declareDraftFoundations = () => {};
  h.context.declareDraftToken = () => {};
  h.context.preflightDraft = () => [];
  h.context.figma.listAvailableFontsAsync = async () => [];
}

test('a preparing reservation blocks the same logical packet across renderer upgrades', async () => {
  const reserved = page('reserved');
  reserved.setPluginData('figmaFlowDraftReviewReservation', JSON.stringify({state: 'preparing', identity: {
    fileKey: packet.fileKey, packet_sha256: packet.packet_sha256, instance_sha256: 'f'.repeat(64), layout_sha256: packet.layout_sha256
  }}));
  reserved.writes.length = 0;
  const upgraded = harness([reserved]);
  upgraded.context.DRAFT.instance_sha256 = 'e'.repeat(64);
  const {context} = upgraded;
  await assert.rejects(context.findInterruptedDraftReview(), error => /page reserved/.test(error.message) && /repair/i.test(error.message));
  assert.deepEqual(reserved.writes, []);
});

test('the exact legacy page and owned notes board fail closed without mutation', async () => {
  const existing = page('legacy', 'DRAFT · Interrupted review fixture · aaaaaaaa');
  const board = {id: 'notes', type: 'FRAME', parent: existing, getPluginData(key) {
    if(key === 'semanticKey') return 'review.notes.fixture';
    if(key === 'designNoteBoard') return JSON.stringify({pageId: existing.id, sourceHash: packet.instance_sha256});
    return '';
  }};
  existing.children.push(board);
  existing.writes.length = 0;
  const {context} = harness([existing]);
  await assert.rejects(context.findInterruptedDraftReview(), error => /page legacy/.test(error.message) && /incomplete/i.test(error.message));
  assert.deepEqual(existing.writes, []);
});

test('unrelated pages do not block a new review and matching completed pages remain reusable', async () => {
  const unrelated = page('unrelated', 'Project notes');
  unrelated.setPluginData('figmaFlowDraftReviewReservation', '{malformed');
  const {context} = harness([unrelated]);
  assert.equal(await context.findInterruptedDraftReview(), null);

  const completed = page('complete');
  complete(completed);
  const next = harness([completed]);
  assert.equal(await next.context.findInterruptedDraftReview(), completed);
  completed.setPluginData('packet_sha256', '');
  await assert.rejects(next.context.findInterruptedDraftReview(), /missing or mismatched packet metadata/);
});

test('older completed reviews are not mistaken for interrupted pages after a renderer upgrade', async () => {
  for(const withReservation of [false, true]) {
    const completed = page('old-complete', 'DRAFT · Interrupted review fixture · aaaaaaaa');
    complete(completed, 'f'.repeat(64));
    if(withReservation)completed.setPluginData('figmaFlowDraftReviewReservation', JSON.stringify({state: 'complete', identity: {
      fileKey: packet.fileKey, packet_sha256: packet.packet_sha256, instance_sha256: 'f'.repeat(64), layout_sha256: packet.layout_sha256
    }}));
    const board = {id: 'notes', type: 'FRAME', parent: completed, getPluginData(key) {
      if(key === 'semanticKey') return 'review.notes.fixture';
      if(key === 'designNoteBoard') return JSON.stringify({pageId: completed.id, sourceHash: packet.instance_sha256});
      return '';
    }};
    completed.children.push(board);
    completed.writes.length = 0;
    const {context} = harness([completed]);
    assert.equal(await context.findInterruptedDraftReview(), null);
    assert.deepEqual(completed.writes, []);
  }
});

test('same-owner pages need late completion metadata and preparing state still blocks reuse', async () => {
  const incomplete = page('incomplete');
  incomplete.setPluginData('figma-flow-direction-review-v1', packet.instance_sha256);
  incomplete.setPluginData('packet_sha256', packet.packet_sha256);
  incomplete.writes.length = 0;
  const h = harness([incomplete]);
  makeDraftAdmissionReady(h);
  let creates = 0;
  h.context.figma.createPage = () => {creates++; throw new Error('unexpected create');};
  await assert.rejects(h.context.makeDraft(), /missing draftCanonicalBindings/);
  assert.equal(creates, 0);
  assert.deepEqual(incomplete.writes, []);

  const preparing = page('preparing');
  preparing.setPluginData('figma-flow-direction-review-v1', packet.instance_sha256);
  preparing.setPluginData('packet_sha256', packet.packet_sha256);
  preparing.setPluginData('figmaFlowDraftReviewReservation', JSON.stringify({state: 'preparing', identity: {
    fileKey: packet.fileKey, packet_sha256: packet.packet_sha256, instance_sha256: packet.instance_sha256, layout_sha256: packet.layout_sha256
  }}));
  preparing.writes.length = 0;
  const h2 = harness([preparing]);
  makeDraftAdmissionReady(h2);
  h2.context.figma.createPage = () => {creates++; throw new Error('unexpected create');};
  await assert.rejects(h2.context.makeDraft(), /already reserved on page preparing/);
  assert.equal(creates, 0);
  assert.deepEqual(preparing.writes, []);
});

test('malformed reservations block only the matching owned or generated-name page', async () => {
  for(const matchingOwner of [true, false]) {
    const existing = page('corrupt', matchingOwner ? '' : 'DRAFT · Interrupted review fixture · aaaaaaaa');
    if(matchingOwner) {
      existing.setPluginData('figma-flow-direction-review-v1', packet.instance_sha256);
      existing.setPluginData('packet_sha256', packet.packet_sha256);
    }
    existing.setPluginData('figmaFlowDraftReviewReservation', '{broken');
    existing.writes.length = 0;
    const h = harness([existing]);
    makeDraftAdmissionReady(h);
    let creates = 0;
    h.context.figma.createPage = () => {creates++; throw new Error('unexpected create');};
    await assert.rejects(h.context.makeDraft(), /Invalid (completion )?review reservation|Invalid completion reservation/);
    assert.equal(creates, 0);
    assert.deepEqual(existing.writes, []);
  }
  const unrelated = page('other', 'Other page');
  unrelated.setPluginData('figmaFlowDraftReviewReservation', '{broken');
  unrelated.writes.length = 0;
  assert.equal(await harness([unrelated]).context.findInterruptedDraftReview(), null);
  assert.deepEqual(unrelated.writes, []);
});
