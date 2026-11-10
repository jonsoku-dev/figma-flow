(function () {
  function complete(state) {
    if (state.review?.phase !== 'answer') return state;
    const cardId = state.review.cardId;
    if (!state.cards.some(card => card.id === cardId)) return state;
    return {
      ...state,
      completedIds: state.completedIds.includes(cardId) ? state.completedIds : [...state.completedIds, cardId],
      review: null
    };
  }

  const api = { complete };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).complete = api;
})();
