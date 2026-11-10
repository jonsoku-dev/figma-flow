const test = require('node:test');
const assert = require('node:assert/strict');
const { createSession, remaining, render } = require('../app/rules/list.js');

test('a fresh session shows every supplied daily card in order, without changing the input', () => {
  const cards = [{ id: 'a', title: '첫 카드' }, { id: 'b', title: '둘째 카드' }];
  const state = createSession(cards);
  assert.deepEqual(remaining(state), cards);
  assert.deepEqual(state, { cards, completedIds: [], query: '', review: null });
  state.cards[0].title = '수정';
  assert.equal(cards[0].title, '첫 카드');
});

test('the pending list excludes completed cards and supports an empty daily deck', () => {
  const state = createSession([{ id: 'a' }, { id: 'b' }]);
  assert.deepEqual(remaining({ ...state, completedIds: ['a'] }), [{ id: 'b' }]);
  assert.equal(remaining(createSession([])).length, 0);
  assert.deepEqual(state.completedIds, []);
});

test('list rendering creates accessible buttons that open the selected card and clears obsolete results', () => {
  function element(tag) {
    return {
      tag, children: [], dataset: {}, attributes: {}, events: {},
      append(...children) { this.children.push(...children); },
      replaceChildren() { this.children = []; },
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, callback) { this.events[name] = callback; }
    };
  }
  const list = element('ul');
  const document = { getElementById: () => list, createElement: element };
  let opened;
  render(document, [{ id: 'a', title: '<b>제목</b>', tag: 'WEB' }], id => { opened = id; });
  const button = list.children[0].children[0];
  assert.equal(button.tag, 'button');
  assert.equal(button.type, 'button');
  assert.equal(button.attributes['aria-label'], '<b>제목</b> 복습하기');
  assert.equal(button.children[1].textContent, '<b>제목</b>');
  assert.equal(button.children[2].attributes['aria-hidden'], 'true');
  button.events.click();
  assert.equal(opened, 'a');
  render(document, [], () => assert.fail('no card should open'));
  assert.equal(list.children.length, 0);
});
