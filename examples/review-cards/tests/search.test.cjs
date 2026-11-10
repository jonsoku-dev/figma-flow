const test = require('node:test');
const assert = require('node:assert/strict');
const { matching, render } = require('../app/rules/search.js');

test('title search trims whitespace, ignores case, and normalizes Korean Unicode', () => {
  const cards = [{ id: 'a', title: 'JavaScript 클로저' }, { id: 'b', title: '시맨틱 HTML' }];
  assert.deepEqual(matching(cards, '  JAVAscript '), [cards[0]]);
  assert.deepEqual(matching(cards, '시맨틱'.normalize('NFD')), [cards[1]]);
  assert.deepEqual(matching(cards, ''), cards);
  assert.deepEqual(matching(cards, '   '), cards);
  assert.equal(cards.length, 2);
});

test('search matches only titles, never question or answer contents, and treats symbols literally', () => {
  const cards = [{ id: 'a', title: 'CSS [기초]', question: 'private question', answer: 'secret answer' }];
  assert.deepEqual(matching(cards, 'private'), []);
  assert.deepEqual(matching(cards, 'secret'), []);
  assert.deepEqual(matching(cards, '['), cards);
  assert.deepEqual(matching(cards, '.*'), []);
});

test('empty results display the query as text and clearing it restores the list', () => {
  const nodes = Object.fromEntries(['empty-search', 'empty-query', 'search-count', 'clear-search'].map(id => [id, {}]));
  const document = { getElementById: id => nodes[id] };
  const cards = [{ id: 'a', title: '질문' }];
  assert.deepEqual(render(document, cards, '<img src=x>'), []);
  assert.equal(nodes['empty-search'].hidden, false);
  assert.equal(nodes['empty-query'].textContent, '<img src=x>');
  assert.equal(nodes['search-count'].textContent, '0개의 카드');
  assert.equal(nodes['clear-search'].hidden, false);
  assert.deepEqual(render(document, cards, ''), cards);
  assert.equal(nodes['empty-search'].hidden, true);
  assert.equal(nodes['search-count'].textContent, '1개의 카드');
  assert.equal(nodes['clear-search'].hidden, true);
});
