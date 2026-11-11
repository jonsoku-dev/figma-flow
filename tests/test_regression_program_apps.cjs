const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const fixture = path.join(__dirname, '..', 'examples/regression-program');
const context = {};
vm.createContext(context);
for (const file of [
  'lib/router.js',
  'lib/paint.js',
  'atlas/app/rules.js',
  'morrow/app/rules.js',
  'paper/app/rules.js',
]) {
  vm.runInContext(fs.readFileSync(path.join(fixture, file), 'utf8'), context, { filename: file });
}
const catalog = JSON.parse(fs.readFileSync(path.join(fixture, 'catalog.json'), 'utf8'));
const apps = context.RegressionApps;

function ready(appId, extra) {
  return apps[appId].createState(catalog.apps[appId], Object.assign({
    seed: catalog.seed,
    designSystem: catalog.designSystem,
    longTextCopy: catalog.longText,
    signedIn: true,
    workspaceId: appId === 'atlas' ? 'northwind' : null,
  }, extra));
}

test('mock decisions match the shared vectors', () => {
  const vectors = JSON.parse(fs.readFileSync(path.join(fixture, 'server/vectors.json'), 'utf8'));
  const functions = {
    decideSave: apps.atlas.decideSave,
    decideOrder: apps.morrow.decideOrder,
    decideReturn: apps.morrow.decideReturn,
    decideAutosave: apps.paper.decideAutosave,
    decidePublish: apps.paper.decidePublish,
  };
  for (const vector of vectors) {
    assert.equal(JSON.stringify(functions[vector.fn](vector.payload)), JSON.stringify({ status: vector.status, body: vector.body }), vector.name);
  }
});

test('every route has a title and a primary action or an explicit denial', () => {
  const roles = { atlas: 'admin', morrow: 'customer', paper: 'editor' };
  for (const appId of ['atlas', 'morrow', 'paper']) {
    const app = catalog.apps[appId];
    for (const route of app.routes) {
      const concrete = route.path.replace(/:([A-Za-z]+)/g, (_, name) => app.samples[name]);
      const state = ready(appId, { role: roles[appId], subject: 'adm-1', path: concrete });
      const seen = apps[appId].view(state);
      assert.equal(seen.title, route.title, route.id);
      assert.ok(seen.primary || seen.access === 'denied' || seen.access === 'readonly', route.id);
      assert.notEqual(seen.title, '');
    }
  }
});

test('atlas saves the displayed density and restores it after reload', () => {
  let state = ready('atlas', { path: '/settings' });
  assert.equal(apps.atlas.view(state).fields[0].value, 'dense');
  state = apps.atlas.dispatch(state, 'ACT-ATLAS-14', { 'display-density': 'comfortable' });
  assert.equal(state.savedDisplay, 'comfortable');
  assert.equal(state.notice.kind, 'saved');
  const restored = apps.atlas.hydrate(ready('atlas', { path: '/settings' }), apps.atlas.snapshot(state));
  assert.equal(apps.atlas.view(restored).fields[0].value, 'comfortable');
});

test('atlas keeps a failed task draft and restores it', () => {
  let state = ready('atlas', { path: '/projects' });
  state = apps.atlas.dispatch(state, 'ACT-ATLAS-04');
  assert.equal(state.path, '/projects/north');
  state = apps.atlas.dispatch(state, 'ACT-ATLAS-05');
  assert.equal(state.path, '/projects/north/board');
  state = apps.atlas.dispatch(state, 'ACT-ATLAS-06');
  assert.equal(state.path, '/tasks/task-0001');
  state = Object.assign({}, state, { faults: { saveTask: true } });
  state = apps.atlas.dispatch(state, 'ACT-ATLAS-07', { 'task-detail': '남김' });
  assert.equal(state.drafts['task-0001'].detail, '남김');
  assert.equal(state.savedTasks['task-0001'], undefined);
  const saved = apps.atlas.snapshot(state);
  const restored = apps.atlas.hydrate(ready('atlas', { path: '/tasks/task-0001' }), saved);
  assert.equal(restored.drafts['task-0001'].detail, '남김');
  state = Object.assign({}, state, { faults: {} });
  state = apps.atlas.dispatch(state, 'ACT-ATLAS-07', { 'task-detail': '남김' });
  assert.equal(JSON.stringify(state.savedTasks['task-0001']), JSON.stringify({ detail: '남김' }));
});

test('atlas approval and role denial follow the mock policy', () => {
  let reviewer = ready('atlas', { subject: 'rev-1', path: '/approvals/apr-1' });
  reviewer = apps.atlas.dispatch(reviewer, 'ACT-ATLAS-09');
  assert.equal(reviewer.approvals[0].status, 'approved');
  let member = ready('atlas', { subject: 'mem-1', path: '/approvals/apr-1' });
  const before = member.approvals[0].status;
  member = apps.atlas.dispatch(member, 'ACT-ATLAS-09');
  assert.equal(member.approvals[0].status, before);
  assert.equal(apps.atlas.view(member).access, 'readonly');
  let admin = ready('atlas', { subject: 'adm-1', path: '/roles/reviewer' });
  admin = apps.atlas.dispatch(admin, 'make-reviewer');
  const promoted = ready('atlas', { subject: 'mem-1', path: '/roles', members: admin.members });
  assert.equal(apps.atlas.view(promoted).access, 'denied');
  assert.equal(apps.atlas.view(ready('atlas', { subject: 'mem-1', path: '/roles' })).access, 'denied');
});

test('atlas direct entry keeps the return path and a list filter survives back', () => {
  const unsigned = apps.atlas.view(ready('atlas', { path: '/projects/north', signedIn: false, workspaceId: null }));
  assert.equal(unsigned.title, 'Atlas 로그인');
  assert.equal(unsigned.returnPath, '/projects/north');
  let state = ready('atlas', { path: '/projects' });
  state = apps.atlas.dispatch(state, 'set-filter', { filter: '할 일 2' });
  state = apps.atlas.dispatch(state, 'navigate', { path: '/projects/north' });
  state = apps.atlas.dispatch(state, 'back');
  assert.equal(state.path, '/projects');
  assert.equal(state.list.filter, '할 일 2');
});

test('atlas pages a thousand tasks without measuring hidden rows', () => {
  let state = ready('atlas', { path: '/projects', taskCount: 1000 });
  let seen = apps.atlas.view(state);
  assert.equal(seen.table.total, 1000);
  assert.equal(seen.table.rows.length, 20);
  assert.equal(seen.table.measured, 'current page only');
  state = apps.atlas.dispatch(state, 'set-page', { page: 50 });
  seen = apps.atlas.view(state);
  assert.equal(seen.table.rows.length, 20);
  state = apps.atlas.dispatch(state, 'set-filter', { filter: '할 일 1000' });
  seen = apps.atlas.view(state);
  assert.equal(seen.table.total, 1);
  state = apps.atlas.dispatch(state, 'set-filter', { filter: '없는 할 일' });
  assert.equal(apps.atlas.view(state).state, 'empty');
  state = ready('atlas', { path: '/projects', faults: { load: 'error' }, taskCount: 1000 });
  state = apps.atlas.dispatch(state, 'set-filter', { filter: '할 일 1' });
  seen = apps.atlas.view(state);
  assert.equal(seen.state, 'error');
  assert.equal(seen.table, null);
  assert.equal(seen.list.filter, '할 일 1');
});

test('input sections appear only for the supplied source', () => {
  for (const appId of ['atlas', 'morrow', 'paper']) {
    const app = catalog.apps[appId];
    const target = app.routes.find(route => route.id === app.url.target);
    const concrete = target.path.replace(/:([A-Za-z]+)/g, (_, name) => app.samples[name]);
    const withHtml = apps[appId].view(ready(appId, { path: concrete, inputs: { html: true, url: true, designSystem: true } }));
    const without = apps[appId].view(ready(appId, { path: concrete, inputs: { html: false, url: false, designSystem: false } }));
    assert.equal(withHtml.sections.find(section => section.id === 'html-mock').title, app.html.title);
    assert.equal(withHtml.sections.find(section => section.id === 'reference-principle').title, app.url.principle);
    assert.equal(withHtml.sections.find(section => section.id === 'design-system').token, '#0e6b4f');
    assert.equal(without.sections.length, 0);
  }
});

test('dialog focus moves into the invite field and returns', () => {
  let state = ready('atlas', { path: '/members/invite' });
  state = apps.atlas.dispatch(state, 'open-dialog');
  const opened = apps.atlas.view(state);
  assert.equal(opened.focus, 'invite-name');
  const document = createDocument();
  context.RegressionPaint.paint(document, opened);
  context.RegressionPaint.focus(document, opened);
  assert.equal(document.activeElement.id, 'invite-name');
  state = apps.atlas.dispatch(state, 'close-dialog', { 'invite-name': '하루' });
  const closed = apps.atlas.view(state);
  context.RegressionPaint.paint(document, closed);
  context.RegressionPaint.focus(document, closed);
  assert.equal(document.activeElement.id, 'invite-button');
});

test('morrow does not add an order on stock or price conflict and keeps one duplicate', () => {
  let state = ready('morrow', { role: 'customer', path: '/products/linen' });
  state = apps.morrow.dispatch(state, 'ACT-MORROW-04');
  state = apps.morrow.dispatch(state, 'ACT-MORROW-07');
  state = apps.morrow.dispatch(state, 'ACT-MORROW-08', { 'contact-name': '하나' });
  assert.equal(state.checkout.contact, '하나');
  state = apps.morrow.dispatch(state, 'back');
  assert.equal(state.path, '/checkout/contact');
  assert.equal(state.checkout.contact, '하나');
  state = apps.morrow.dispatch(state, 'ACT-MORROW-08', { 'contact-name': '하나' });
  state = apps.morrow.dispatch(state, 'ACT-MORROW-09', { 'delivery-note': '문 앞' });
  state = Object.assign({}, state, { faults: { stock: true } });
  state = apps.morrow.dispatch(state, 'ACT-MORROW-10');
  assert.equal(state.orders.length, 0);
  state = Object.assign({}, state, { faults: { price: true } });
  state = apps.morrow.dispatch(state, 'ACT-MORROW-10');
  assert.equal(state.orders.length, 0);
  state = apps.morrow.dispatch(state, 'ack-price');
  state = apps.morrow.dispatch(state, 'ACT-MORROW-10');
  assert.equal(state.orders.length, 1);
  assert.equal(state.orders[0].price, 18000);
  state = apps.morrow.dispatch(state, 'ACT-MORROW-10');
  assert.equal(state.orders.length, 1);
  const guest = ready('morrow', { role: 'guest', path: '/checkout/review' });
  assert.equal(apps.morrow.view(guest).primary, null);
});

test('morrow restores saved products and keeps a failed return', () => {
  let state = ready('morrow', { role: 'customer', path: '/products/linen' });
  state = apps.morrow.dispatch(state, 'save-product');
  const saved = apps.morrow.snapshot(state);
  const restored = apps.morrow.hydrate(ready('morrow', { role: 'customer', path: '/saved' }), saved);
  assert.ok(restored.saved.includes('linen'));
  assert.equal(apps.morrow.view(restored).cards[0].title, '리넨 냅킨');
  let returning = ready('morrow', { role: 'customer', path: '/returns/new/order-1', orders: [{ id: 'order-1', signature: 'linen:1', cart: [], price: 12000 }] });
  returning = Object.assign({}, returning, { faults: { return: true } });
  returning = apps.morrow.dispatch(returning, 'ACT-MORROW-14', { 'return-reason': '파손', 'return-note': '모서리' });
  assert.equal(returning.form.note, '모서리');
  assert.equal(returning.returns['order-1'], undefined);
});

test('paper review submission sends its draft and preserves it on a failed save', () => {
  let state = ready('paper', { role: 'author', path: '/studio/articles/draft-1/edit', faults: { autosave: true } });
  const fields = { 'article-title': '검토할 제목', 'article-body': '검토할 본문' };
  const request = apps.paper.payloadFor(state, 'ACT-PAPER-09', fields);
  assert.equal(JSON.stringify(request.draft), JSON.stringify({ title: fields['article-title'], body: fields['article-body'] }));
  assert.equal(apps.paper.decideFor('ACT-PAPER-09', request).status, 409);
  state = apps.paper.dispatch(state, 'ACT-PAPER-09', fields);
  assert.equal(state.path, '/studio/articles/draft-1/edit');
  assert.equal(state.drafts['draft-1'].body, fields['article-body']);
  assert.equal(state.articles.find(item => item.id === 'draft-1').status, 'draft');
  state = Object.assign({}, state, { faults: {} });
  assert.equal(apps.paper.decideFor('ACT-PAPER-09', apps.paper.payloadFor(state, 'ACT-PAPER-09', fields)).status, 200);
  state = apps.paper.dispatch(state, 'ACT-PAPER-09', fields);
  assert.equal(state.path, '/studio/reviews');
  assert.equal(state.articles.find(item => item.id === 'draft-1').status, 'in-review');
});

test('paper keeps a failed autosave and publishes only for an editor', () => {
  let state = ready('paper', { role: 'author', path: '/studio/articles/new' });
  state = apps.paper.dispatch(state, 'ACT-PAPER-08');
  state = Object.assign({}, state, { faults: { autosave: true } });
  state = apps.paper.dispatch(state, 'autosave', { 'article-title': '남긴 제목', 'article-body': '남긴 문장' });
  assert.equal(state.drafts['draft-1'].body, '남긴 문장');
  const restored = apps.paper.hydrate(ready('paper', { role: 'author', path: '/studio/articles/draft-1/edit' }), apps.paper.snapshot(state));
  assert.equal(restored.drafts['draft-1'].body, '남긴 문장');
  state = Object.assign({}, state, { faults: {} });
  state = apps.paper.dispatch(state, 'ACT-PAPER-09', { 'article-title': '남긴 제목', 'article-body': '남긴 문장' });
  assert.equal(state.articles.find(item => item.id === 'draft-1').status, 'in-review');
  let editor = ready('paper', { role: 'editor', path: '/studio/reviews/draft-1' });
  editor = Object.assign({}, apps.paper.hydrate(editor, apps.paper.snapshot(state)), { role: 'editor', path: '/studio/reviews/draft-1' });
  editor = apps.paper.dispatch(editor, 'reject');
  assert.equal(editor.articles.find(item => item.id === 'draft-1').status, 'rejected');
  editor = apps.paper.dispatch(editor, 'request-changes');
  assert.equal(editor.articles.find(item => item.id === 'draft-1').status, 'changes-requested');
  editor = apps.paper.dispatch(editor, 'ACT-PAPER-11', { 'article-title': '남긴 제목', 'article-body': '남긴 문장' });
  assert.equal(editor.articles.find(item => item.id === 'draft-1').status, 'published');
  assert.equal(editor.path, '/');
  assert.ok(apps.paper.view(editor).cards.some(card => card.title === '남긴 제목'));
  const calendar = apps.paper.view(Object.assign({}, editor, { path: '/studio/calendar' }));
  assert.ok(calendar.table.rows.some(row => row[0] === '남긴 제목'));
  const author = apps.paper.dispatch(ready('paper', { role: 'author', path: '/studio/reviews/draft-1' }), 'ACT-PAPER-11', { 'article-title': '남긴 제목', 'article-body': '남긴 문장' });
  assert.equal(author.articles.find(item => item.id === 'draft-1').status, 'draft');
  const reader = apps.paper.view(ready('paper', { role: 'reader', path: '/studio' }));
  assert.equal(reader.access, 'denied');
  assert.equal(reader.title, '작업실');
});

test('js fixtures create their heading only when the script runs', () => {
  for (const [app, phrase] of [['atlas', 'JS로 만든 승인 큐'], ['morrow', 'JS로 만든 상품 진열'], ['paper', 'JS로 만든 초고 본문']]) {
    const html = fs.readFileSync(path.join(fixture, 'html', app, 'js/index.html'), 'utf8');
    const source = fs.readFileSync(path.join(fixture, 'html', app, 'js/render.js'), 'utf8');
    assert.equal(html.includes(phrase), false);
    const document = createDocument();
    const root = document.createElement('main');
    root.id = 'js-root';
    document.getElementById = id => id === 'js-root' ? root : null;
    const local = { document, console };
    vm.createContext(local);
    vm.runInContext(source, local, { filename: app + '/render.js' });
    assert.equal(root.children[0].textContent, phrase);
  }
});

function createDocument() {
  function createElement(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      id: '',
      className: '',
      textContent: '',
      value: '',
      type: '',
      disabled: false,
      dataset: {},
      children: [],
      attributes: {},
      setAttribute(name, value) { this.attributes[name] = String(value); },
      append(...kids) { this.children.push(...kids); },
      replaceChildren(...kids) { this.children = kids; },
      focus() { document.activeElement = this; },
    };
  }
  const app = createElement('div');
  app.id = 'app';
  const document = {
    title: '',
    activeElement: null,
    createElement,
    getElementById(id) {
      function walk(node) {
        if (!node) return null;
        if (node.id === id) return node;
        for (const child of node.children || []) {
          const found = walk(child);
          if (found) return found;
        }
        return null;
      }
      return walk(app);
    },
  };
  return document;
}
