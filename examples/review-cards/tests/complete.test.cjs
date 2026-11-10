const test = require('node:test');
const assert = require('node:assert/strict');
const { complete } = require('../app/rules/complete.js');

function session(review = { cardId: 'a', phase: 'answer' }) {
  return { cards: [{ id: 'a' }, { id: 'b' }], completedIds: ['b'], query: '카드', review };
}

test('completion records exactly the selected card, returns to the list, and preserves the search', () => {
  const before = session();
  const after = complete(before);
  assert.deepEqual(after.completedIds, ['b', 'a']);
  assert.equal(after.review, null);
  assert.equal(after.query, '카드');
  assert.strictEqual(after.cards, before.cards);
  assert.deepEqual(before.completedIds, ['b']);
  assert.strictEqual(complete(after), after);
});

test('completion is unavailable before reveal, from the list, or for an unknown card', () => {
  for (const review of [null, { cardId: 'a', phase: 'question' }, { cardId: 'unknown', phase: 'answer' }]) {
    const state = session(review);
    assert.strictEqual(complete(state), state);
  }
});

test('completion never duplicates an already recorded card', () => {
  const before = session({ cardId: 'b', phase: 'answer' });
  const after = complete(before);
  assert.deepEqual(after.completedIds, ['b']);
  assert.equal(after.review, null);
});
