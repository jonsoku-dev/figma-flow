(function () {
  const router = globalThis.RegressionRouter;
  const NAV = [
    ['/dashboard', '오늘'],
    ['/projects', '프로젝트'],
    ['/approvals', '승인'],
    ['/members', '구성원'],
    ['/roles', '역할'],
    ['/settings', '설정'],
  ];

  function members() {
    return [
      { id: 'mem-1', name: '민재', role: 'member' },
      { id: 'rev-1', name: '서윤', role: 'reviewer' },
      { id: 'adm-1', name: '하라', role: 'admin' },
    ];
  }

  function tasksOf(count) {
    const rows = [];
    for (let index = 0; index < count; index += 1) {
      rows.push({
        id: 'task-' + String(index + 1).padStart(4, '0'),
        projectId: ['north', 'harbor', 'kiln'][index % 3],
        title: '할 일 ' + (index + 1),
        due: '2026-11-' + String((index % 28) + 1).padStart(2, '0'),
        column: ['대기', '진행', '완료'][index % 3],
      });
    }
    return rows;
  }

  function createState(app, options) {
    options = options || {};
    return {
      app: app,
      design: options.designSystem || null,
      longTextCopy: options.longTextCopy || null,
      seed: options.seed || 20261111,
      subject: options.subject || 'mem-1',
      members: router.copy(options.members || members()),
      approvals: [{ id: 'apr-1', title: '외부 공유 요청', status: 'pending', requester: 'mem-1' }],
      drafts: {},
      savedTasks: {},
      savedDisplay: 'dense',
      path: options.path || '/sign-in',
      faults: Object.assign({}, options.faults),
      inputs: Object.assign({ html: false, url: false, designSystem: false }, options.inputs),
      signedIn: !!options.signedIn,
      workspaceId: options.workspaceId || null,
      list: { page: 1, sort: 'due', filter: '', pageSize: 20 },
      form: {},
      history: [],
      future: [],
      dialog: null,
      notice: null,
      focus: null,
      longText: !!options.longText,
      taskCount: options.taskCount || 24,
      returnPath: null,
    };
  }

  function roleOf(state) {
    const found = state.members.find(function (item) { return item.id === state.subject; });
    return found ? found.role : 'member';
  }

  function decideSave(payload) {
    const draft = payload && payload.draft;
    if (!draft || typeof draft !== 'object' || Array.isArray(draft) || Object.values(draft).some(function (value) { return typeof value !== 'string'; })) {
      return { status: 400, body: { ok: false, error: 'invalid-draft' } };
    }
    if (payload.fault === 'save-task') return { status: 409, body: { ok: false, error: 'save-failed', draft: draft } };
    return { status: 200, body: { ok: true, task: draft } };
  }

  function payloadFor(state, action, fields) {
    fields = fields || {};
    if (action !== 'ACT-ATLAS-07') return {};
    const located = router.match(state.app.routes, state.path);
    const taskId = located && located.params.taskId || state.app.samples.taskId;
    const existing = state.drafts[taskId] || {};
    const detail = fields['task-detail'] != null ? fields['task-detail'] : existing.detail || '';
    return { fault: state.faults.saveTask ? 'save-task' : '', draft: { detail: detail } };
  }

  function decideFor(action, payload) {
    if (action === 'ACT-ATLAS-07') return decideSave(payload);
    return { status: 204, body: {} };
  }

  function remember(state, path, extra) {
    return router.patch(state, Object.assign({
      history: state.history.concat([{ path: state.path, list: router.copy(state.list), form: router.copy(state.form) }]),
      future: [],
      path: path,
      notice: null,
      dialog: null,
      focus: null,
    }, extra || {}));
  }

  function sectionsFor(state, screenId) {
    const sections = [];
    if (state.inputs.html) sections.push({ id: 'html-mock', title: state.app.html.title, gap: state.app.html.gap, source: 'html' });
    if (state.inputs.url && state.app.url.target === screenId) sections.push({ id: 'reference-principle', title: state.app.url.principle, source: 'url' });
    if (state.inputs.designSystem && state.design) {
      sections.push({ id: 'design-system', title: '디자인 시스템', components: state.design.components, token: state.design.token, importPath: state.design.importPath, source: 'design-system' });
    }
    return sections;
  }

  function nav(state, current) {
    return NAV.map(function (item) {
      return { href: state.app.mount + item[0], label: item[1], current: item[0] === current };
    });
  }

  function shell(state, route, extra) {
    const role = roleOf(state);
    const access = route.access && route.access[role] || 'allowed';
    const primary = access === 'allowed' ? { id: route.primary.id, label: state.longText && route.id === 'SCR-ATLAS-07' ? state.longTextCopy.ko : route.primary.label, remote: route.primary.remote || null } : null;
    return Object.assign({
      id: route.id,
      path: route.path,
      title: route.title,
      access: access,
      state: 'content',
      notice: state.notice,
      primary: primary,
      nav: nav(state, route.path),
      sections: sectionsFor(state, route.id),
      fields: [],
      secondary: [],
      table: null,
      cards: null,
      prose: null,
      dialog: null,
      focus: state.focus,
      list: state.list,
      longText: state.longText ? state.longTextCopy : null,
      returnPath: state.returnPath,
    }, extra || {});
  }

  function view(state) {
    const signIn = state.app.routes.find(function (route) { return route.path === '/sign-in'; });
    if (!state.signedIn && state.path !== '/sign-in') {
      return shell(state, signIn, { returnPath: state.path, notice: { kind: 'info', text: '로그인 뒤 요청한 경로로 돌아갑니다.' } });
    }
    if (state.signedIn && !state.workspaceId && state.path !== '/sign-in' && state.path !== '/workspaces') {
      const workspaces = state.app.routes.find(function (route) { return route.path === '/workspaces'; });
      return shell(state, workspaces, { returnPath: state.path, notice: { kind: 'info', text: '작업 공간을 고르면 요청한 경로로 돌아갑니다.' } });
    }
    const located = router.match(state.app.routes, state.path);
    if (!located) return { id: 'missing', path: state.path, title: '없는 경로', access: 'denied', state: 'empty', primary: null, nav: nav(state, ''), sections: [], notice: state.notice };
    const route = located.route;
    if (state.faults.load === 'loading') return shell(state, route, { state: 'loading', table: null, notice: { kind: 'info', text: '불러오는 중입니다.' } });
    if (state.faults.load === 'error') return shell(state, route, { state: 'error', table: null, notice: { kind: 'error', text: '목록을 불러오지 못했습니다.' }, secondary: [{ id: 'retry', label: '다시 시도', focus: 'retry' }] });
    const role = roleOf(state);
    const access = route.access && route.access[role] || 'allowed';
    if (route.id === 'SCR-ATLAS-04' || route.id === 'SCR-ATLAS-05') {
      const projectId = located.params.projectId;
      const source = tasksOf(state.taskCount).filter(function (task) { return !projectId || task.projectId === projectId; });
      const page = router.pageItems(source, state.list, function (task) { return task.title; });
      if (page.total === 0) return shell(state, route, { state: 'empty', notice: { kind: 'info', text: '조건에 맞는 할 일이 없습니다.' } });
      return shell(state, route, { table: { columns: ['할 일', '프로젝트', '기한'], rows: page.rows.map(function (task) { return [task.title, task.projectId, task.due]; }), total: page.total, page: page.page, pages: page.pages, measured: page.measured } });
    }
    if (route.id === 'SCR-ATLAS-06') {
      const source = tasksOf(state.taskCount).filter(function (task) { return task.projectId === located.params.projectId; });
      const board = ['대기', '진행', '완료'].map(function (column) {
        const rows = source.filter(function (task) { return task.column === column; });
        return { id: column, title: column, total: rows.length, rows: rows.slice(0, 20).map(function (task) { return task.title; }) };
      });
      return shell(state, route, { board: board, prose: '보이는 칸만 세었습니다. ' + board.map(function (column) { return column.title + ' ' + column.rows.length + '/' + column.total; }).join(', ') });
    }
    if (route.id === 'SCR-ATLAS-07') {
      const taskId = located.params.taskId;
      const draft = state.drafts[taskId] || {};
      return shell(state, route, { fields: [{ id: 'task-detail', label: '할 일 내용', value: draft.detail || '', multiline: true }] });
    }
    if (route.id === 'SCR-ATLAS-08') {
      return shell(state, route, { table: { columns: ['요청', '상태'], rows: state.approvals.map(function (item) { return [item.title, item.status === 'approved' ? '승인함' : '대기']; }), total: state.approvals.length, page: 1, pages: 1, measured: 'current page only' } });
    }
    if (route.id === 'SCR-ATLAS-09') {
      const approval = state.approvals.find(function (item) { return item.id === located.params.approvalId; }) || state.approvals[0];
      const readonly = role === 'member';
      return shell(state, route, {
        access: readonly ? 'readonly' : access,
        primary: readonly ? null : shell(state, route).primary,
        prose: approval.title + ' · ' + (approval.status === 'approved' ? '승인함' : '대기'),
      });
    }
    if (route.id === 'SCR-ATLAS-10') {
      return shell(state, route, { table: { columns: ['이름', '역할'], rows: state.members.map(function (item) { return [item.name, item.role]; }), total: state.members.length, page: 1, pages: 1, measured: 'current page only' } });
    }
    if (route.id === 'SCR-ATLAS-11') {
      const dialog = state.dialog ? { title: '초대 대상', fields: [{ id: 'invite-name', label: '이름', value: state.form.invite || '' }] } : null;
      return shell(state, route, { dialog: dialog, focus: state.focus, secondary: [{ id: 'open-dialog', label: '대화상자로 입력', focus: 'invite-button' }] });
    }
    if (route.id === 'SCR-ATLAS-13') {
      return shell(state, route, { prose: '민재의 현재 역할은 ' + (state.members.find(function (item) { return item.id === 'mem-1'; }) || {}).role + '입니다.', secondary: [{ id: 'make-reviewer', label: '민재를 검토자로', focus: 'make-reviewer' }] });
    }
    if (route.id === 'SCR-ATLAS-14') {
      return shell(state, route, { fields: [{ id: 'display-density', label: '표시 밀도', value: state.savedDisplay }] });
    }
    return shell(state, route);
  }

  function saveTask(state, payload) {
    const body = payloadFor(state, 'ACT-ATLAS-07', payload);
    const located = router.match(state.app.routes, state.path);
    const taskId = located && located.params.taskId || state.app.samples.taskId;
    const decision = decideSave(body);
    const drafts = Object.assign({}, state.drafts, { [taskId]: body.draft });
    if (decision.status !== 200) {
      return router.patch(state, { drafts: drafts, notice: { kind: 'error', text: '저장하지 못했습니다. 입력은 그대로입니다.' }, focus: 'task-detail' });
    }
    return router.patch(state, { drafts: drafts, savedTasks: Object.assign({}, state.savedTasks, { [taskId]: decision.body.task }), notice: { kind: 'saved', text: '저장했습니다.' }, focus: null });
  }

  function dispatch(state, action, payload) {
    payload = payload || {};
    if (action === 'navigate') return remember(state, payload.path || state.path);
    if (action === 'back') {
      if (!state.history.length) return state;
      const previous = state.history[state.history.length - 1];
      return router.patch(state, { history: state.history.slice(0, -1), future: state.future.concat([{ path: state.path, list: router.copy(state.list), form: router.copy(state.form) }]), path: previous.path, list: previous.list, form: previous.form, notice: null });
    }
    if (action === 'forward') {
      if (!state.future.length) return state;
      const next = state.future[state.future.length - 1];
      return router.patch(state, { future: state.future.slice(0, -1), history: state.history.concat([{ path: state.path, list: router.copy(state.list), form: router.copy(state.form) }]), path: next.path, list: next.list, form: next.form, notice: null });
    }
    if (action === 'set-filter') return router.patch(state, { list: Object.assign({}, state.list, { filter: payload.filter || '', page: 1 }) });
    if (action === 'set-page') return router.patch(state, { list: Object.assign({}, state.list, { page: Number(payload.page) || 1 }) });
    if (action === 'set-sort') return router.patch(state, { list: Object.assign({}, state.list, { sort: payload.sort || 'due', page: 1 }) });
    if (action === 'retry') {
      const faults = Object.assign({}, state.faults);
      delete faults.load;
      delete faults.saveTask;
      return router.patch(state, { faults: faults, notice: null });
    }
    if (action === 'open-dialog') return router.patch(state, { dialog: 'invite', focus: 'invite-name' });
    if (action === 'close-dialog') return router.patch(state, { dialog: null, focus: 'invite-button', form: Object.assign({}, state.form, { invite: payload['invite-name'] || state.form.invite || '' }) });
    if (action === 'ACT-ATLAS-01') {
      const destination = state.path === '/sign-in' ? '/workspaces' : state.path;
      return remember(state, destination, { signedIn: true, subject: payload.subject || state.subject });
    }
    if (action === 'ACT-ATLAS-02') {
      const destination = state.path === '/workspaces' || state.path === '/sign-in' ? '/dashboard' : state.path;
      return remember(state, destination, { signedIn: true, workspaceId: 'northwind' });
    }
    if (action === 'ACT-ATLAS-07') return saveTask(state, payload);
    if (action === 'ACT-ATLAS-14') {
      const density = String(payload['display-density'] || state.savedDisplay).trim();
      return router.patch(state, { savedDisplay: density || state.savedDisplay, notice: { kind: 'saved', text: '표시 밀도를 저장했습니다.' } });
    }
    if (action === 'ACT-ATLAS-09') {
      if (roleOf(state) === 'member') return router.patch(state, { notice: { kind: 'error', text: '읽기 전용입니다.' } });
      const located = router.match(state.app.routes, state.path);
      const approvalId = located && located.params.approvalId || state.app.samples.approvalId;
      const approvals = state.approvals.map(function (item) { return item.id === approvalId ? Object.assign({}, item, { status: 'approved' }) : item; });
      return remember(router.patch(state, { approvals: approvals }), '/approvals');
    }
    if (action === 'make-reviewer' || action === 'ACT-ATLAS-13') {
      if (roleOf(state) !== 'admin') return router.patch(state, { notice: { kind: 'error', text: '이 역할로는 진행할 수 없습니다.' } });
      const memberId = payload.memberId || 'mem-1';
      const nextRole = payload.role || 'reviewer';
      const updated = state.members.map(function (item) { return item.id === memberId ? Object.assign({}, item, { role: nextRole }) : item; });
      return remember(router.patch(state, { members: updated }), '/roles');
    }
    const located = router.match(state.app.routes, state.path);
    if (!located || located.route.primary.id !== action) return router.patch(state, { notice: { kind: 'error', text: '지원하지 않는 동작입니다.' } });
    if ((located.route.access && located.route.access[roleOf(state)]) === 'denied') return router.patch(state, { notice: { kind: 'error', text: '이 역할로는 진행할 수 없습니다.' } });
    const target = located.route.primary.to.map(function (screenId) { return router.screenPath(state.app.routes, screenId, state.app.samples); }).find(Boolean);
    return target ? remember(state, target) : state;
  }

  function snapshot(state) {
    return router.copy({ drafts: state.drafts, savedTasks: state.savedTasks, members: state.members, approvals: state.approvals, signedIn: state.signedIn, workspaceId: state.workspaceId, subject: state.subject, savedDisplay: state.savedDisplay, list: state.list, form: state.form });
  }

  function hydrate(state, saved) {
    return router.patch(state, router.copy(saved));
  }

  globalThis.RegressionApps = globalThis.RegressionApps || {};
  globalThis.RegressionApps.atlas = {
    createState: createState,
    view: view,
    dispatch: dispatch,
    snapshot: snapshot,
    hydrate: hydrate,
    decideSave: decideSave,
    decideFor: decideFor,
    payloadFor: payloadFor,
    markMismatch: function (state) { return router.patch(state, { notice: { kind: 'error', text: '모의 서버와 화면 규칙이 달라 저장하지 않았습니다.' } }); },
    withPath: function (state, path, extra) { return router.patch(state, Object.assign({ path: path }, extra || {})); },
  };
})();
