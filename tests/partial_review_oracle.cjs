const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');

const root = process.cwd();
const packet = {
  schema: 'figma-flow-native-direction-review-v1', scope: 'exploratory-only', production_admitted: false,
  fileKey: 'fixture-file', packet_sha256: 'a'.repeat(64), instance_sha256: 'b'.repeat(64), layout_sha256: 'c'.repeat(64),
  candidate_pins: {fixture: 'd'.repeat(64)}, assets: {},
  candidates: [{id: 'fixture', title: 'Interrupted review fixture', foundations: {roles: []}, colors: {}, fonts: {}}]
};
const candidate = packet.candidates[0];
const prelude = execFileSync('python3', ['-B', '-c',
  'import sys; sys.path.insert(0,sys.argv[1]); from specification_contract import spec_label_prelude; print(spec_label_prelude())',
  path.join(root, 'tools')], {encoding: 'utf8'});

const boardKey = 'review.notes.' + candidate.id;
const board = {
  id: 'partial-board', type: 'FRAME', parent: null, children: [],
  getPluginData(key) {
    if (key === 'semanticKey') return boardKey;
    if (key === 'designNoteBoard') return JSON.stringify({pageId: '1:2', sourceHash: packet.instance_sha256});
    return '';
  }
};
const partialPage = {
  id: '1:2', type: 'PAGE',
  name: 'DRAFT · ' + candidate.title + ' · ' + packet.packet_sha256.slice(0, 8),
  children: [board],
  getPluginData() { return ''; },
  findAll() { return [board]; },
  async loadAsync() {}
};
board.parent = partialPage;

let createCalls = 0;
const context = vm.createContext({
  DRAFT: packet,
  __html__: '',
  figma: {
    fileKey: packet.fileKey,
    root: {children: [partialPage]},
    currentPage: partialPage,
    ui: {postMessage() {}},
    showUI() {},
    async listAvailableFontsAsync() { return []; },
    createPage() { createCalls++; throw new Error('CREATE_PAGE_SENTINEL'); }
  }
});
vm.runInContext(prelude, context);
for (const file of ['native_annotations.js', 'design_note_board.js', 'native_semantic_read.js', 'direction_review.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'figma-bridge', file), 'utf8'), context);
}
context.admitDraftColorConsumers = () => [];
context.declareDraftFoundations = () => {};
context.draftFoundationName = () => 'oracle/unused';
context.declareDraftToken = () => {};
context.preflightDraft = () => [];

(async () => {
  let operationError = null;
  try { await context.makeDraft(); }
  catch (error) { operationError = String(error?.message || error); }
  assert.equal(createCalls, 0, 'incomplete review must not create another page');
  assert.match(operationError || '', /(existing|partial).*(page|review)|(repair|recovery|incomplete)/i,
    'partial-page rejection must clearly point to the existing page or repair');
  assert.ok((operationError || '').includes(partialPage.id), 'recovery rejection must identify the existing page');
})().catch(error => { console.error(error); process.exitCode = 1; });
