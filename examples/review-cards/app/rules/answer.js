(function () {
  function reveal(state) {
    if (state.review?.phase !== 'question') return state;
    return { ...state, review: { ...state.review, phase: 'answer' } };
  }

  function render(document, state) {
    const shown = state.review?.phase === 'answer';
    const card = state.cards.find(item => item.id === state.review?.cardId);
    document.getElementById('answer-panel').hidden = !shown;
    document.getElementById('answer-text').textContent = shown ? card.answer : '';
    document.getElementById('reveal-button').hidden = shown;
    document.getElementById('reveal-button').setAttribute('aria-expanded', String(shown));
    document.getElementById('review-choices').hidden = !shown;
    document.getElementById('retry-button').disabled = !shown;
    document.getElementById('complete-button').disabled = !shown;
  }

  const api = { reveal, render };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).answer = api;
})();
