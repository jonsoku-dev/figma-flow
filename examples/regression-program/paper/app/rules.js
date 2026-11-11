(function () {
  const router = globalThis.RegressionRouter;

  function articlesOf(count) {
    const rows = [
      { id: 'desk-lamp', slug: 'desk-lamp', title: '책상 위의 램프', status: 'published', body: '램프 아래의 문장은 한 줄이 너무 길어지기 전에 다음 줄로 넘어간다.' },
      { id: 'draft-1', slug: 'draft-1', title: '아직 제목이 짧은 초고', status: 'draft', body: '' },
    ];
    for (let index = rows.length; index < count; index += 1) {
      rows.push({ id: 'article-' + (index + 1), slug: 'article-' + (index + 1), title: '글 ' + (index + 1), status: 'published', body: '생성된 본문 ' + (index + 1) });
    }
    return rows.slice(0, Math.max(count, rows.length));
  }

  function createState(app, options) {
    options = options || {};
    const articles = articlesOf(options.articleCount || 4);
    return {
      app: app,
      design: options.designSystem || null,
      longTextCopy: options.longTextCopy || null,
      seed: options.seed || 20261111,
      role: options.role || 'reader',
      path: options.path || '/',
      faults: Object.assign({}, options.faults),
      inputs: Object.assign({ html: false, url: false, designSystem: false }, options.inputs),
      articles: articles,
      drafts: { 'draft-1': { title: '아직 제목이 짧은 초고', body: '' } },
      saved: [],
      list: { page: 1, sort: 'name', filter: '', pageSize: 20 },
      history: [],
      future: [],
      notice: null,
      focus: null,
      longText: !!options.longText,
      articleCount: options.articleCount || 4,
      dialog: null,
    };
  }

  function draftOf(payload) {
    const draft = payload && payload.draft;
    if (!draft || typeof draft !== 'object' || Array.isArray(draft) || Object.values(draft).some(function (value) { return typeof value !== 'string'; })) return null;
    return draft;
  }

  function decideAutosave(payload) {
    const draft = draftOf(payload);
    if (!draft) return { status: 400, body: { ok: false, error: 'invalid-draft' } };
    if (payload.fault === 'autosave') return { status: 409, body: { ok: false, error: 'autosave-failed', draft: draft } };
    return { status: 200, body: { ok: true, draft: draft } };
  }

  function decidePublish(payload) {
    const draft = draftOf(payload);
    if (payload.role !== 'editor') return { status: 403, body: { ok: false, error: 'editor-required' } };
    if (!draft) return { status: 400, body: { ok: false, error: 'invalid-draft' } };
    if (payload.fault === 'publish') return { status: 409, body: { ok: false, error: 'publish-failed', draft: draft } };
    return { status: 200, body: { ok: true, mode: 'virtual', article: { title: draft.title, body: draft.body, status: 'published' } } };
  }

  function currentDraft(state, articleId, fields) {
    const existing = state.drafts[articleId] || { title: '', body: '' };
    return {
      title: fields && fields['article-title'] != null ? fields['article-title'] : existing.title,
      body: fields && fields['article-body'] != null ? fields['article-body'] : existing.body,
    };
  }

  function payloadFor(state, action, fields) {
    const located = router.match(state.app.routes, state.path);
    const articleId = located && (located.params.articleId || located.params.reviewId) || state.app.samples.articleId;
    const draft = currentDraft(state, articleId, fields || {});
    if (action === 'autosave') return { fault: state.faults.autosave ? 'autosave' : '', draft: draft };
    if (action === 'ACT-PAPER-11') return { role: state.role, fault: state.faults.publish ? 'publish' : '', draft: draft };
    return {};
  }

  function decideFor(action, payload) {
    if (action === 'autosave') return decideAutosave(payload);
    if (action === 'ACT-PAPER-11') return decidePublish(payload);
    return { status: 204, body: {} };
  }

  function remember(state, path, extra) {
    return router.patch(state, Object.assign({
      history: state.history.concat([{ path: state.path, list: router.copy(state.list) }]),
      future: [],
      path: path,
      notice: null,
      focus: null,
    }, extra || {}));
  }

  function sectionsFor(state, screenId) {
    const sections = [];
    if (state.inputs.html) sections.push({ id: 'html-mock', title: state.app.html.title, gap: state.app.html.gap, source: 'html' });
    if (state.inputs.url && state.app.url.target === screenId) sections.push({ id: 'reference-principle', title: state.app.url.principle, source: 'url' });
    if (state.inputs.designSystem && state.design) sections.push({ id: 'design-system', title: '디자인 시스템', components: state.design.components, token: state.design.token, importPath: state.design.importPath, source: 'design-system' });
    return sections;
  }

  function shell(state, route, extra) {
    const access = route.access && route.access[state.role] || 'allowed';
    const primary = access === 'allowed' ? { id: route.primary.id, label: state.longText && route.id === 'SCR-PAPER-09' ? state.longTextCopy.ko : route.primary.label, remote: route.primary.remote || null } : null;
    return Object.assign({
      id: route.id,
      path: route.path,
      title: route.title,
      access: access,
      state: 'content',
      notice: state.notice,
      primary: primary,
      nav: (state.role === 'reader' ? [['/', '읽기'], ['/search', '찾기'], ['/saved', '보관']] : [['/', '읽기'], ['/search', '찾기'], ['/studio', '작업실'], ['/studio/reviews', '검토'], ['/studio/calendar', '달력']]).map(function (item) {
        return { href: state.app.mount + item[0], label: item[1], current: item[0] === route.path };
      }),
      sections: sectionsFor(state, route.id),
      fields: [],
      secondary: [],
      table: null,
      cards: null,
      prose: null,
      focus: state.focus,
      list: state.list,
      longText: state.longText ? state.longTextCopy : null,
      dialog: null,
    }, extra || {});
  }

  function view(state) {
    const located = router.match(state.app.routes, state.path);
    if (!located) return { id: 'missing', path: state.path, title: '없는 경로', access: 'denied', state: 'empty', primary: null, sections: [], nav: [] };
    const route = located.route;
    const access = route.access && route.access[state.role] || 'allowed';
    if (access === 'denied') return shell(state, route, { prose: '이 역할로는 작업실을 열 수 없습니다.' });
    if (state.faults.load === 'loading') return shell(state, route, { state: 'loading', notice: { kind: 'info', text: '불러오는 중입니다.' } });
    if (state.faults.load === 'error') return shell(state, route, { state: 'error', notice: { kind: 'error', text: '목록을 불러오지 못했습니다.' }, secondary: [{ id: 'retry', label: '다시 시도', focus: 'retry' }] });
    const published = state.articles.filter(function (item) { return item.status === 'published'; });
    if (route.id === 'SCR-PAPER-01' || route.id === 'SCR-PAPER-02' || route.id === 'SCR-PAPER-04' || route.id === 'SCR-PAPER-05') {
      const source = route.id === 'SCR-PAPER-05' ? published.filter(function (item) { return state.saved.includes(item.id); }) : published;
      const page = router.pageItems(source, state.list, function (item) { return item.title + ' ' + item.body; });
      if (page.total === 0) return shell(state, route, { state: 'empty', prose: '읽을 글이 없습니다.' });
      return shell(state, route, { prose: page.rows[0].title, cards: page.rows.map(function (item) { return { id: item.id, title: item.title, meta: item.status }; }), table: { columns: ['글'], rows: page.rows.map(function (item) { return [item.title]; }), total: page.total, page: page.page, pages: page.pages, measured: page.measured } });
    }
    if (route.id === 'SCR-PAPER-03') {
      const article = state.articles.find(function (item) { return item.slug === located.params.slug; });
      if (!article) return shell(state, route, { state: 'empty', prose: '글을 찾지 못했습니다.' });
      return shell(state, route, { prose: article.title + '\n' + article.body, secondary: [{ id: 'save-article', label: '보관', focus: 'save-article' }] });
    }
    if (route.id === 'SCR-PAPER-07' || route.id === 'SCR-PAPER-10') {
      const source = route.id === 'SCR-PAPER-10' ? state.articles.filter(function (item) { return item.status === 'in-review' || item.status === 'changes-requested' || item.status === 'rejected'; }) : state.articles.filter(function (item) { return item.status !== 'published'; });
      return shell(state, route, { table: { columns: ['제목', '상태'], rows: source.map(function (item) { return [item.title, item.status]; }), total: source.length, page: 1, pages: 1, measured: 'current page only' }, state: source.length ? 'content' : 'empty' });
    }
    if (route.id === 'SCR-PAPER-09') {
      const draft = state.drafts[located.params.articleId] || { title: '', body: '' };
      return shell(state, route, { fields: [{ id: 'article-title', label: '제목', value: draft.title }, { id: 'article-body', label: '본문', value: draft.body, multiline: true }], secondary: [{ id: 'autosave', label: '자동 저장', focus: 'autosave' }] });
    }
    if (route.id === 'SCR-PAPER-11') {
      const article = state.articles.find(function (item) { return item.id === located.params.reviewId; }) || state.articles.find(function (item) { return item.id === 'draft-1'; });
      const draft = state.drafts[article.id] || { title: article.title, body: article.body };
      const secondary = state.role === 'editor' ? [{ id: 'reject', label: '반려', focus: 'reject' }, { id: 'request-changes', label: '수정 요청', focus: 'request-changes' }] : [];
      return shell(state, route, { prose: draft.title + '\n' + draft.body + '\n' + article.status, secondary: secondary });
    }
    if (route.id === 'SCR-PAPER-12') {
      return shell(state, route, { table: { columns: ['발행'], rows: published.map(function (item) { return [item.title]; }), total: published.length, page: 1, pages: 1, measured: 'current page only' } });
    }
    return shell(state, route, { fields: [{ id: 'article-title', label: '제목', value: '' }, { id: 'article-body', label: '본문', value: '', multiline: true }] });
  }

  function updateArticle(state, articleId, values) {
    return state.articles.map(function (item) { return item.id === articleId ? Object.assign({}, item, values) : item; });
  }

  function dispatch(state, action, payload) {
    payload = payload || {};
    if (action === 'navigate') return remember(state, payload.path || state.path);
    if (action === 'back') {
      if (!state.history.length) return state;
      const previous = state.history[state.history.length - 1];
      return router.patch(state, { history: state.history.slice(0, -1), path: previous.path, list: previous.list, notice: null });
    }
    if (action === 'set-filter') return router.patch(state, { list: Object.assign({}, state.list, { filter: payload.filter || '', page: 1 }) });
    if (action === 'set-page') return router.patch(state, { list: Object.assign({}, state.list, { page: Number(payload.page) || 1 }) });
    if (action === 'retry') {
      const faults = Object.assign({}, state.faults);
      delete faults.load;
      return router.patch(state, { faults: faults, notice: null });
    }
    if (action === 'save-article') {
      const located = router.match(state.app.routes, state.path);
      const article = state.articles.find(function (item) { return item.slug === (located && located.params.slug); });
      if (!article) return state;
      const saved = state.saved.includes(article.id) ? state.saved : state.saved.concat([article.id]);
      return router.patch(state, { saved: saved, notice: { kind: 'saved', text: '보관한 글에 넣었습니다.' } });
    }
    const located = router.match(state.app.routes, state.path);
    const route = located && located.route;
    if (route && route.access && route.access[state.role] === 'denied') return router.patch(state, { notice: { kind: 'error', text: '이 역할로는 진행할 수 없습니다.' } });
    if (action === 'autosave') {
      const articleId = located.params.articleId;
      const body = payloadFor(state, action, payload);
      const decision = decideAutosave(body);
      const drafts = Object.assign({}, state.drafts, { [articleId]: body.draft });
      if (decision.status !== 200) return router.patch(state, { drafts: drafts, notice: { kind: 'error', text: '자동 저장에 실패했습니다. 본문은 유지됩니다.' }, focus: 'article-body' });
      return router.patch(state, { drafts: drafts, notice: { kind: 'saved', text: '자동 저장했습니다.' }, focus: null });
    }
    if (action === 'ACT-PAPER-08') return remember(state, '/studio/articles/draft-1/edit');
    if (action === 'ACT-PAPER-09') {
      const articleId = located.params.articleId;
      const draft = currentDraft(state, articleId, payload);
      const drafts = Object.assign({}, state.drafts, { [articleId]: draft });
      const articles = updateArticle(state, articleId, { status: 'in-review', title: draft.title, body: draft.body });
      return remember(router.patch(state, { drafts: drafts, articles: articles }), '/studio/reviews');
    }
    if (action === 'reject' || action === 'request-changes') {
      if (state.role !== 'editor') return router.patch(state, { notice: { kind: 'error', text: '편집자만 검토를 마칩니다.' } });
      const articleId = located.params.reviewId || 'draft-1';
      const status = action === 'reject' ? 'rejected' : 'changes-requested';
      return router.patch(state, { articles: updateArticle(state, articleId, { status: status }), notice: { kind: 'saved', text: status === 'rejected' ? '반려했습니다.' : '수정을 요청했습니다.' } });
    }
    if (action === 'ACT-PAPER-11') {
      const articleId = located.params.reviewId || state.app.samples.reviewId;
      const body = payloadFor(state, action, payload);
      const decision = decidePublish(body);
      if (decision.status !== 200) return router.patch(state, { notice: { kind: 'error', text: '가상 발행을 진행하지 못했습니다.' } });
      const article = Object.assign({ id: articleId, slug: articleId }, decision.body.article);
      const articles = state.articles.some(function (item) { return item.id === articleId; }) ? updateArticle(state, articleId, article) : state.articles.concat([article]);
      return remember(router.patch(state, { articles: articles, notice: { kind: 'saved', text: '가상 발행했습니다. 공개 사이트에는 나가지 않습니다.' } }), '/');
    }
    if (!route || route.primary.id !== action) return router.patch(state, { notice: { kind: 'error', text: '지원하지 않는 동작입니다.' } });
    const target = route.primary.to.map(function (screenId) { return router.screenPath(state.app.routes, screenId, state.app.samples); }).find(Boolean);
    return target ? remember(state, target) : state;
  }

  function snapshot(state) {
    return router.copy({ articles: state.articles, drafts: state.drafts, saved: state.saved, role: state.role, list: state.list });
  }

  function hydrate(state, saved) {
    return router.patch(state, router.copy(saved));
  }

  globalThis.RegressionApps = globalThis.RegressionApps || {};
  globalThis.RegressionApps.paper = {
    createState: createState,
    view: view,
    dispatch: dispatch,
    snapshot: snapshot,
    hydrate: hydrate,
    decideAutosave: decideAutosave,
    decidePublish: decidePublish,
    decideFor: decideFor,
    payloadFor: payloadFor,
    markMismatch: function (state) { return router.patch(state, { notice: { kind: 'error', text: '모의 서버와 화면 규칙이 달라 저장하지 않았습니다.' } }); },
    withPath: function (state, path, extra) { return router.patch(state, Object.assign({ path: path }, extra || {})); },
  };
})();
