(function () {
  function summary(state) {
    const total = state.cards.length;
    const completed = state.cards.filter(card => state.completedIds.includes(card.id)).length;
    return { total, completed, remaining: total - completed, done: completed === total };
  }

  function render(document, state) {
    const progress = summary(state);
    document.getElementById('progress-label').textContent = `${progress.completed} / ${progress.total} 완료`;
    document.getElementById('progress').max = progress.total || 1;
    document.getElementById('progress').value = progress.completed;
    document.getElementById('remaining-label').textContent = `${progress.remaining}장의 카드가 기다리고 있어요.`;
    document.getElementById('done-panel').hidden = !progress.done;
    document.getElementById('study-list').hidden = progress.done;
    document.getElementById('done-count').textContent = `${progress.total}장의 카드를 모두 복습했어요.`;
    return progress;
  }

  const api = { summary, render };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (globalThis.CardRules ??= {}).finish = api;
})();
