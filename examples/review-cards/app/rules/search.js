(function () {
  function matching(cards, query) {
    const term = query.normalize('NFC').trim().toLocaleLowerCase('ko-KR');
    return cards.filter(card => card.title.normalize('NFC').toLocaleLowerCase('ko-KR').includes(term));
  }

  function render(document, cards, query) {
    const results = matching(cards, query);
    document.getElementById('empty-search').hidden = results.length !== 0;
    document.getElementById('empty-query').textContent = query.trim();
    document.getElementById('search-count').textContent = `${results.length}개의 카드`;
    document.getElementById('clear-search').hidden = query.length === 0;
    return results;
  }

  const api = { matching, render };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).search = api;
})();
