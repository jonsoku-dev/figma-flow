(function () {
  const appId = document.body.dataset.app;
  const mount = document.body.dataset.mount;
  const primary = document.body.dataset.primary;
  const rules = globalThis.RegressionApps[appId];

  function appPath(pathname) {
    if (pathname === mount) return '/';
    if (pathname.indexOf(mount + '/') === 0) return pathname.slice(mount.length) || '/';
    return pathname || '/';
  }

  function inputsFrom(params) {
    const initial = { html: primary === 'html', url: primary === 'url', designSystem: primary === 'design-system' };
    if (params.get('inputs') != null) {
      const selected = new Set(params.get('inputs').split(',').filter(Boolean));
      initial.html = selected.has('html');
      initial.url = selected.has('url');
      initial.designSystem = selected.has('design-system');
    }
    (params.get('omit') || '').split(',').filter(Boolean).forEach(function (name) {
      if (name === 'html') initial.html = false;
      if (name === 'url') initial.url = false;
      if (name === 'design-system') initial.designSystem = false;
    });
    return initial;
  }

  function fields(scope) {
    const values = {};
    scope.querySelectorAll('[data-field]').forEach(function (node) {
      if (node.id) values[node.id] = node.value;
    });
    return values;
  }

  function draw(state) {
    const current = rules.view(state);
    globalThis.RegressionPaint.paint(document, current);
    globalThis.RegressionPaint.focus(document, current);
  }

  async function remoteAgrees(button, payload) {
    if (!button.dataset.remote) return true;
    const response = await fetch(button.dataset.remote, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    const decision = rules.decideFor(button.dataset.action, payload);
    return response.status === decision.status && JSON.stringify(body) === JSON.stringify(decision.body);
  }

  fetch('/catalog.json').then(function (response) {
    if (!response.ok) throw new Error('catalog');
    return response.json();
  }).then(function (catalog) {
    const params = new URLSearchParams(location.search);
    const faults = {};
    const faultNames = { 'save-task': 'saveTask', stock: 'stock', price: 'price', return: 'return', autosave: 'autosave', publish: 'publish', load: 'load' };
    const faultName = params.get('fault');
    if (faultNames[faultName]) faults[faultNames[faultName]] = true;
    let state = rules.createState(catalog.apps[appId], {
      seed: catalog.seed,
      designSystem: catalog.designSystem,
      longTextCopy: catalog.longText,
      inputs: inputsFrom(params),
      faults: faults,
      path: appPath(location.pathname),
      signedIn: params.get('signed') === '1' || appId !== 'atlas',
      workspaceId: params.get('workspace') || (appId === 'atlas' && params.get('signed') === '1' ? 'northwind' : null),
      subject: params.get('subject') || undefined,
      role: params.get('role') || undefined,
      taskCount: Number(params.get('tasks') || 24),
      productCount: Number(params.get('products') || 12),
      articleCount: Number(params.get('articles') || 4),
      longText: params.has('long'),
    });
    const storageKey = 'figma-flow-regression-' + appId;
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (raw) state = rules.hydrate(state, JSON.parse(raw));
    } catch (error) { /* a blocked or old session falls back to the fresh fixture */ }
    const override = {};
    if (params.get('signed') === '1') override.signedIn = true;
    if (params.get('workspace')) override.workspaceId = params.get('workspace');
    if (params.get('role')) override.role = params.get('role');
    if (params.get('subject')) override.subject = params.get('subject');
    state = rules.withPath(state, appPath(location.pathname), override);
    function persist(mode) {
      const snapshot = rules.snapshot(state);
      try { sessionStorage.setItem(storageKey, JSON.stringify(snapshot)); } catch (error) { /* quota or private mode */ }
      const url = mount + (state.path || '/') + location.search;
      if (mode === 'push') history.pushState({ snapshot: snapshot }, '', url);
      else history.replaceState({ snapshot: snapshot }, '', url);
    }
    window.addEventListener('popstate', function (event) {
      const snapshot = event.state && event.state.snapshot;
      if (!snapshot) return;
      state = rules.withPath(rules.hydrate(state, snapshot), appPath(location.pathname));
      draw(state);
    });
    document.getElementById('app').addEventListener('click', async function (event) {
      const link = event.target.closest('a[href]');
      if (link) {
        const next = new URL(link.href, location.origin);
        if (next.origin === location.origin && next.pathname.indexOf(mount) === 0) {
          event.preventDefault();
          state = rules.dispatch(state, 'navigate', { path: appPath(next.pathname) });
          persist('push');
          draw(state);
        }
        return;
      }
      const button = event.target.closest('[data-action]');
      if (!button) return;
      event.preventDefault();
      const payload = fields(document);
      if (button.dataset.remote) {
        const decisionPayload = rules.payloadFor(state, button.dataset.action, payload);
        const agreed = await remoteAgrees(button, decisionPayload);
        if (!agreed) {
          state = rules.markMismatch(state);
          draw(state);
          return;
        }
      }
      state = rules.dispatch(state, button.dataset.action, payload);
      persist('push');
      draw(state);
    });
    document.getElementById('app').addEventListener('input', function (event) {
      if (event.target.id !== 'list-filter') return;
      state = rules.dispatch(state, 'set-filter', { filter: event.target.value });
      persist('replace');
      const caret = event.target.value.length;
      draw(state);
      const field = document.getElementById('list-filter');
      if (field) {
        field.focus();
        if (field.setSelectionRange) field.setSelectionRange(caret, caret);
      }
    });
    persist('replace');
    draw(state);
  }).catch(function () {
    document.title = '목록을 불러오지 못했습니다';
    document.getElementById('app').textContent = '목록을 불러오지 못했습니다. 모의 서버를 다시 실행해 주세요.';
  });
})();
