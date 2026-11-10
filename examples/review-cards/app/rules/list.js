(function () {
  function createSession(cards) {
    return { cards: cards.map(card => ({ ...card })), completedIds: [], query: '', review: null };
  }

  function remaining(state) {
    return state.cards.filter(card => !state.completedIds.includes(card.id));
  }

  function render(document, cards, onOpen) {
    const list = document.getElementById('card-list');
    list.replaceChildren();
    for (const card of cards) {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'card-button card--default';
      button.dataset.cardId = card.id;
      button.setAttribute('aria-label', `${card.title} 복습하기`);
      const tag = document.createElement('span');
      tag.className = 'card-tag';
      tag.textContent = card.tag;
      const title = document.createElement('span');
      title.className = 'card-title';
      title.textContent = card.title;
      const arrow = document.createElement('span');
      arrow.className = 'card-arrow';
      arrow.textContent = '↗';
      arrow.setAttribute('aria-hidden', 'true');
      button.append(tag, title, arrow);
      button.addEventListener('click', () => onOpen(card.id));
      item.append(button);
      list.append(item);
    }
  }

  const api = { createSession, remaining, render };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).list = api;
})();
