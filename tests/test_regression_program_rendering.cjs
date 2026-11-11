const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..', 'examples/regression-program');

function documentFor(app) {
  const document = {
    title: '',
    body: { dataset: { app } },
    documentElement: { dataset: {}, style: { setProperty() {} } },
    createElement(tag) {
      return {
        tagName: tag.toUpperCase(), id: '', className: '', textContent: '', value: '', dataset: {},
        children: [], attributes: {}, setAttribute(name, value) { this.attributes[name] = String(value); },
        append(...children) { this.children.push(...children); }, replaceChildren(...children) { this.children = children; },
      };
    },
  };
  const appRoot = document.createElement('div');
  appRoot.id = 'app';
  document.getElementById = id => id === 'app' ? appRoot : find(appRoot, id);
  function find(node, id) {
    if (node.id === id) return node;
    for (const child of node.children) {
      const match = find(child, id);
      if (match) return match;
    }
    return null;
  }
  return document;
}

function descendants(node) {
  return [node, ...(node.children || []).flatMap(descendants)];
}

function load() {
  const context = {};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, 'design-system/runtime.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(root, 'lib/paint.js'), 'utf8'), context);
  return context;
}

test('enabled design source renders typed component models; excluded sources stay out of the page', () => {
  const context = load();
  const calls = {};
  for (const [name, factory] of Object.entries(context.RegressionDesignSystem)) {
    context.RegressionDesignSystem[name] = props => {
      calls[name] = (calls[name] || 0) + 1;
      return factory(props);
    };
  }
  const view = {
    title: '작업 목록', nav: [{ href: '/atlas', label: '목록', current: true }],
    sections: [
      { id: 'html-mock', title: '레퍼런스 제목', gap: '12px', source: 'html' },
      { id: 'reference-principle', title: 'atlas-check-answers', source: 'url' },
      { id: 'design-system', title: '디자인 시스템', token: '#0e6b4f', source: 'design-system' },
    ],
    table: { columns: ['할 일', '기한'], rows: [['초안 검토', '오늘']], total: 1, measured: '1개' },
    list: { filter: '' }, fields: [{ id: 'task-detail', label: '내용', value: '실제 내용', multiline: true }],
    primary: { id: 'save', label: '저장' }, dialog: { title: '초대', fields: [] },
  };
  const included = documentFor('atlas');
  context.RegressionPaint.paint(included, view);
  const rendered = descendants(included.getElementById('app'));
  assert.equal(included.getElementById('nav').tagName, 'NAV');
  assert.deepEqual(calls, { Nav: 1, Field: 2, Table: 1, Button: 1, Dialog: 1 });
  assert.ok(rendered.some(node => node.dataset.component === 'Table' && node.dataset.componentSource === 'design-system/components/Table.tsx'));
  assert.ok(rendered.some(node => node.dataset.component === 'Field'));
  assert.equal(rendered.some(node => node.textContent === '디자인 시스템' || node.textContent === '#0e6b4f' || node.textContent === '12px'), false);
  assert.equal(included.getElementById('app').dataset.htmlSpacing, '12px');
  assert.equal(included.getElementById('app').dataset.urlPrinciple, 'atlas-check-answers');

  const excluded = documentFor('atlas');
  context.RegressionPaint.paint(excluded, Object.assign({}, view, { sections: [] }));
  const excludedNodes = descendants(excluded.getElementById('app'));
  assert.equal(excludedNodes.some(node => node.dataset.component), false);
  assert.equal(excluded.getElementById('app').dataset.htmlSpacing, '');
  assert.equal(excluded.getElementById('app').dataset.urlPrinciple, '');
  assert.deepEqual(calls, { Nav: 1, Field: 2, Table: 1, Button: 1, Dialog: 1 });
});

test('rendered values consume component model output rather than decorative markers', () => {
  const context = load();
  const library = context.RegressionDesignSystem;
  for (const name of ['Button', 'Field', 'Dialog']) {
    const original = library[name];
    library[name] = props => Object.assign({}, original(props), { label: 'typed ' + props.label, value: 'typed value' });
  }
  const table = library.Table;
  library.Table = props => Object.assign({}, table(props), { columns: ['typed column'], rows: [['typed row']] });
  const nav = library.Nav;
  library.Nav = props => Object.assign({}, nav(props), { items: [{ label: 'typed navigation', href: '/paper/' }] });
  const document = documentFor('paper');
  context.RegressionPaint.paint(document, {
    title: 'Editor', sections: [{ source: 'design-system' }], nav: [],
    fields: [{ id: 'article-title', label: 'Title', value: 'app value' }],
    primary: { id: 'save', label: 'Save' }, dialog: { title: 'Invite', fields: [] },
    table: { columns: ['app column'], rows: [['app row']], measured: 1, total: 1 },
  });
  const nodes = descendants(document.getElementById('app'));
  for (const expected of ['typed Save', 'typed Title', 'typed Invite', 'typed navigation', 'typed column', 'typed row']) {
    assert.ok(nodes.some(node => node.textContent === expected), expected);
  }
  assert.equal(document.getElementById('article-title').value, 'typed value');
});
