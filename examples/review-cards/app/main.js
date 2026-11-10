(function () {
  const rules = globalThis.CardRules;
  let state = rules.list.createSession(globalThis.TodayCards);
  const get = id => document.getElementById(id);

  function render() {
    get('SCR-CARDS-LIST').hidden = state.review !== null;
    get('SCR-CARDS-REVIEW').hidden = state.review === null;
    rules.finish.render(document, state);
    const cards = rules.search.render(document, rules.list.remaining(state), state.query);
    rules.list.render(document, cards, cardId => {
      state = rules.question.open(state, cardId);
      render();
      get('review-title').focus();
    });
    rules.question.render(document, state);
    rules.answer.render(document, state);
  }

  get('search').addEventListener('input', event => {
    state = { ...state, query: event.target.value };
    render();
  });
  get('clear-search').addEventListener('click', () => {
    state = { ...state, query: '' };
    get('search').value = '';
    render();
    get('search').focus();
  });
  get('back-button').addEventListener('click', () => {
    const cardId = state.review.cardId;
    state = rules.question.back(state);
    render();
    const cardButton = [...document.querySelectorAll('[data-card-id]')].find(button => button.dataset.cardId === cardId);
    (cardButton ?? get('list-title')).focus();
  });
  get('reveal-button').addEventListener('click', () => {
    state = rules.answer.reveal(state);
    render();
    get('answer-panel').focus();
  });
  get('retry-button').addEventListener('click', () => {
    state = rules.retry.retry(state);
    render();
    get('review-question').focus();
  });
  get('complete-button').addEventListener('click', () => {
    state = rules.complete.complete(state);
    render();
    get(rules.finish.summary(state).done ? 'done-title' : 'list-title').focus();
  });
  render();
})();
