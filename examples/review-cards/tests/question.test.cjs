const test = require('node:test');
const assert = require('node:assert/strict');
const { open, back, render } = require('../app/rules/question.js');

function session() {
  return { cards: [{ id: 'a', title: '클로저', question: '무엇인가요?', answer: '렉시컬 환경', tag: 'JS' }, { id: 'b' }], completedIds: ['b'], query: '클로저', review: null };
}

test('opening a pending card starts at its question without marking it complete', () => {
  const before = session();
  const after = open(before, 'a');
  assert.deepEqual(after.review, { cardId: 'a', phase: 'question' });
  assert.equal(after.query, '클로저');
  assert.deepEqual(after.completedIds, ['b']);
  assert.equal(before.review, null);
});

test('unknown or already completed cards cannot be opened', () => {
  const state = session();
  assert.strictEqual(open(state, 'unknown'), state);
  assert.strictEqual(open(state, 'b'), state);
});

test('returning to the list preserves the query and progress; reopening hides the prior answer', () => {
  const state = { ...session(), review: { cardId: 'a', phase: 'answer' } };
  const returned = back(state);
  assert.equal(returned.review, null);
  assert.equal(returned.query, state.query);
  assert.deepEqual(returned.completedIds, state.completedIds);
  assert.equal(open(returned, 'a').review.phase, 'question');
  assert.equal(state.review.phase, 'answer');
});

test('the question view writes the selected title, prompt, and category as text', () => {
  const nodes = Object.fromEntries(['review-title', 'review-question', 'review-tag'].map(id => [id, {}]));
  const document = { getElementById: id => nodes[id] };
  render(document, open(session(), 'a'));
  assert.equal(nodes['review-title'].textContent, '클로저');
  assert.equal(nodes['review-question'].textContent, '무엇인가요?');
  assert.equal(nodes['review-tag'].textContent, 'JS');
  render(document, session());
  assert.equal(nodes['review-question'].textContent, '');
});
