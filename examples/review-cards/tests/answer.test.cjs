const test = require('node:test');
const assert = require('node:assert/strict');
const { reveal, render } = require('../app/rules/answer.js');

function session(phase = 'question') {
  return { cards: [{ id: 'a', answer: '<script>inert text</script>' }], completedIds: [], query: '', review: { cardId: 'a', phase } };
}

test('reveal changes only the selected review phase and does not complete the card', () => {
  const before = session();
  const after = reveal(before);
  assert.deepEqual(after.review, { cardId: 'a', phase: 'answer' });
  assert.deepEqual(after.completedIds, []);
  assert.equal(before.review.phase, 'question');
  assert.strictEqual(reveal(after), after);
  const list = { ...before, review: null };
  assert.strictEqual(reveal(list), list);
});

test('answers and rating controls stay hidden and disabled until reveal, and reset on question view', () => {
  const ids = ['answer-panel', 'answer-text', 'reveal-button', 'review-choices', 'retry-button', 'complete-button'];
  const nodes = Object.fromEntries(ids.map(id => [id, { attributes: {}, setAttribute(name, value) { this.attributes[name] = value; } }]));
  const document = { getElementById: id => nodes[id] };
  render(document, session());
  assert.equal(nodes['answer-panel'].hidden, true);
  assert.equal(nodes['answer-text'].textContent, '');
  assert.equal(nodes['review-choices'].hidden, true);
  assert.equal(nodes['retry-button'].disabled, true);
  assert.equal(nodes['complete-button'].disabled, true);
  assert.equal(nodes['reveal-button'].hidden, false);
  assert.equal(nodes['reveal-button'].attributes['aria-expanded'], 'false');
  render(document, reveal(session()));
  assert.equal(nodes['answer-panel'].hidden, false);
  assert.equal(nodes['answer-text'].textContent, '<script>inert text</script>');
  assert.equal(nodes['review-choices'].hidden, false);
  assert.equal(nodes['retry-button'].disabled, false);
  assert.equal(nodes['complete-button'].disabled, false);
  assert.equal(nodes['reveal-button'].hidden, true);
  assert.equal(nodes['reveal-button'].attributes['aria-expanded'], 'true');
  render(document, session());
  assert.equal(nodes['answer-text'].textContent, '');
  assert.equal(nodes['review-choices'].hidden, true);
});
