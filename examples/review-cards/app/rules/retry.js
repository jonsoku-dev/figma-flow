(function () {
  function retry(state) {
    if (state.review?.phase !== 'answer') return state;
    const start = state.cards.findIndex(card => card.id === state.review.cardId);
    if (start < 0) return state;
    const done = new Set(state.completedIds);
    for (let step = 1; step <= state.cards.length; step++) {
      const candidate = state.cards[(start + step) % state.cards.length];
      if (!done.has(candidate.id)) {
        return { ...state, review: { cardId: candidate.id, phase: 'question' } };
      }
    }
    return state;
  }

  const api = { retry };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).retry = api;
})();
