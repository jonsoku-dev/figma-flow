const test = require('node:test');
const assert = require('node:assert/strict');
const { retry } = require('../app/rules/retry.js');

function studying(current, completedIds = []) {
  return {cards: ['a','b','c','d'].map(id => ({id})), completedIds, query: '검색어',
    review: {cardId: current, phase: 'answer'}};
}

test('완료한 카드를 건너뛰어 다음 미완료 질문을 보여 주고 원본 진행 상태를 보존한다', () => {
  const state = studying('a', ['b']);
  const next = retry(state);
  assert.deepEqual(next.review, {cardId: 'c', phase: 'question'});
  assert.strictEqual(next.completedIds, state.completedIds);
  assert.strictEqual(next.cards, state.cards);
  assert.equal(next.query, state.query);
  assert.deepEqual(state.review, {cardId: 'a', phase: 'answer'});
});

test('마지막 카드에서 처음으로 돌고 한 장만 남으면 같은 질문을 반복한다', () => {
  assert.equal(retry(studying('d', ['a'])).review.cardId, 'b');
  assert.deepEqual(retry(studying('d', ['a','b','c'])).review, {cardId: 'd', phase: 'question'});
});

test('목록이나 정답 공개 전에는 상태를 유지한다', () => {
  for (const review of [null, {cardId: 'b', phase: 'question'}]) {
    const state = {...studying('b'), review};
    assert.strictEqual(retry(state), state);
  }
});
