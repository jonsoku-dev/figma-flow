const test = require('node:test');
const assert = require('node:assert/strict');
const { summary, render } = require('../app/rules/finish.js');

test('daily completion counts the whole deck rather than the filtered search results', () => {
  const state = { cards: [{ id: 'a' }, { id: 'b' }], completedIds: ['a'], query: 'no results', review: null };
  assert.deepEqual(summary(state), { total: 2, completed: 1, remaining: 1, done: false });
  assert.deepEqual(summary({ ...state, completedIds: ['a', 'b'] }), { total: 2, completed: 2, remaining: 0, done: true });
});

test('duplicate or foreign completion IDs do not inflate progress, and an empty day is done', () => {
  assert.deepEqual(summary({ cards: [{ id: 'a' }], completedIds: ['ghost', 'ghost'] }), { total: 1, completed: 0, remaining: 1, done: false });
  assert.deepEqual(summary({ cards: [{ id: 'a' }], completedIds: ['a', 'a', 'ghost'] }), { total: 1, completed: 1, remaining: 0, done: true });
  assert.deepEqual(summary({ cards: [], completedIds: [] }), { total: 0, completed: 0, remaining: 0, done: true });
});

test('the last completion shows the daily success state and hides the search/list area', () => {
  const nodes = Object.fromEntries(['progress-label', 'progress', 'remaining-label', 'done-panel', 'study-list', 'done-count'].map(id => [id, {}]));
  const document = { getElementById: id => nodes[id] };
  render(document, { cards: [{ id: 'a' }], completedIds: [] });
  assert.equal(nodes['done-panel'].hidden, true);
  assert.equal(nodes['study-list'].hidden, false);
  assert.equal(nodes.progress.value, 0);
  render(document, { cards: [{ id: 'a' }], completedIds: ['a'] });
  assert.equal(nodes['done-panel'].hidden, false);
  assert.equal(nodes['study-list'].hidden, true);
  assert.equal(nodes['progress-label'].textContent, '1 / 1 완료');
  assert.equal(nodes.progress.value, 1);
  assert.equal(nodes.progress.max, 1);
  assert.equal(nodes['done-count'].textContent, '1장의 카드를 모두 복습했어요.');
});
