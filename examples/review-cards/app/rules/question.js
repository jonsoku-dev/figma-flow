(function () {
  function open(state, cardId) {
    if (!state.cards.some(card => card.id === cardId) || state.completedIds.includes(cardId)) return state;
    return { ...state, review: { cardId, phase: 'question' } };
  }

  function back(state) {
    return { ...state, review: null };
  }

  function render(document, state) {
    const card = state.cards.find(item => item.id === state.review?.cardId);
    document.getElementById('review-title').textContent = card?.title ?? '';
    document.getElementById('review-question').textContent = card?.question ?? '';
    document.getElementById('review-tag').textContent = card?.tag ?? '';
  }

  const api = { open, back, render };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).question = api;
})();
