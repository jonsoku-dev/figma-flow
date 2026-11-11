(function () {
  function element(document, tag, props) {
    const node = document.createElement(tag);
    if (props.id) node.id = props.id;
    if (props.className) node.className = props.className;
    if (props.type) node.type = props.type;
    if (props.text != null) node.textContent = props.text;
    if (props.value != null) node.value = props.value;
    if (props.action) node.dataset.action = props.action;
    if (props.remote) node.dataset.remote = props.remote;
    if (props.field) node.dataset.field = 'true';
    if (props.disabled) node.disabled = true;
    if (props.forId) node.setAttribute('for', props.forId);
    if (props.role) node.setAttribute('role', props.role);
    if (props.modal) node.setAttribute('aria-modal', 'true');
    if (props.label) node.setAttribute('aria-label', props.label);
    if (props.href) node.setAttribute('href', props.href);
    if (props.children) props.children.forEach(function (child) { node.append(child); });
    return node;
  }

  function model(name, props, enabled) {
    return enabled && globalThis.RegressionDesignSystem && globalThis.RegressionDesignSystem[name]
      ? globalThis.RegressionDesignSystem[name](props)
      : null;
  }

  function mark(node, descriptor, source) {
    if (descriptor) {
      node.dataset.component = descriptor.component;
      node.dataset.componentSource = source;
    }
    return node;
  }

  function paint(document, view) {
    const app = document.getElementById('app');
    const appId = document.body && document.body.dataset.app || 'paper';
    const enabled = (view.sections || []).some(function (section) { return section.source === 'design-system'; });
    const html = (view.sections || []).find(function (section) { return section.source === 'html'; });
    const url = (view.sections || []).find(function (section) { return section.source === 'url'; });
    app.replaceChildren();
    app.className = 'workspace ' + appId;
    app.dataset.htmlSpacing = html ? html.gap : '';
    app.dataset.urlPrinciple = url ? url.title : '';
    if (document.documentElement) {
      document.documentElement.dataset.designSystem = enabled ? 'enabled' : 'disabled';
      if (document.documentElement.style) document.documentElement.style.setProperty('--fixture-space', html ? html.gap : '');
    }
    document.title = view.title;

    const shell = element(document, 'div', { className: 'app-shell' });
    const navModel = model('Nav', { label: '주요 이동', items: view.nav || [] }, enabled);
    const nav = mark(element(document, 'nav', { id: 'nav', label: '주요 이동', children: (navModel ? navModel.items : view.nav || []).map(function (item) {
      return element(document, 'a', { text: item.label, href: item.href, className: item.current ? 'current' : '' });
    }) }), navModel, 'design-system/components/Nav.tsx');
    shell.append(nav);

    const main = element(document, 'main', { className: 'page' });
    const heading = element(document, 'h1', { id: 'screen-title', text: view.title });
    main.append(heading);
    if (view.notice) main.append(element(document, 'p', { id: 'notice', className: 'notice ' + view.notice.kind, text: view.notice.text }));
    if (view.access === 'denied' || view.access === 'readonly') main.append(element(document, 'p', { id: 'access', className: 'notice', text: view.access === 'denied' ? '이 역할로는 열 수 없습니다.' : '읽기 전용입니다.' }));
    if (view.returnPath) main.append(element(document, 'p', { id: 'return-path', className: 'return-path', text: view.returnPath }));

    if (view.table) {
      const toolbar = element(document, 'div', { className: 'toolbar' });
      const fieldModel = model('Field', { label: '목록 필터', value: (view.list && view.list.filter) || '' }, enabled);
      toolbar.append(element(document, 'label', { text: fieldModel ? fieldModel.label : '목록 필터', forId: 'list-filter' }));
      toolbar.append(mark(element(document, 'input', { id: 'list-filter', field: true, value: fieldModel ? fieldModel.value : (view.list && view.list.filter) || '', type: 'search', label: fieldModel ? fieldModel.label : '목록 필터' }), fieldModel, 'design-system/components/Field.tsx'));
      main.append(toolbar);
      const tableModel = model('Table', { label: view.title, columns: view.table.columns, rows: view.table.rows }, enabled);
      const table = mark(element(document, 'table', { id: 'data-table' }), tableModel, 'design-system/components/Table.tsx');
      const head = element(document, 'tr', {});
      (tableModel ? tableModel.columns : view.table.columns).forEach(function (column) { head.append(element(document, 'th', { text: column })); });
      table.append(head);
      (tableModel ? tableModel.rows : view.table.rows).forEach(function (row) {
        const line = element(document, 'tr', {});
        row.forEach(function (cell) { line.append(element(document, 'td', { text: String(cell) })); });
        table.append(line);
      });
      main.append(table);
      main.append(element(document, 'p', { id: 'table-meta', className: 'meta', text: view.table.measured + ' · ' + view.table.total }));
    }
    if (view.board) main.append(element(document, 'div', { className: 'board', children: view.board.map(function (column) {
      return element(document, 'section', { className: 'board-column', children: [element(document, 'h2', { text: column.title }), element(document, 'p', { text: column.rows.join(' · ') })] });
    }) }));
    (view.cards || []).forEach(function (card) { main.append(element(document, 'article', { className: 'card', children: [element(document, 'h2', { text: card.title }), element(document, 'p', { text: card.meta || '' })] })); });
    if (view.prose) main.append(element(document, 'article', { id: 'prose', className: 'prose', children: [element(document, 'p', { text: view.prose })] }));
    if (view.longText) main.append(element(document, 'p', { id: 'long-copy', className: 'long-copy', text: [view.longText.ko, view.longText.en, view.longText.ja].join(' / ') }));
    (view.fields || []).forEach(function (field) {
      const fieldModel = model('Field', field, enabled);
      main.append(element(document, 'label', { text: fieldModel ? fieldModel.label : field.label, forId: field.id }));
      main.append(mark(element(document, field.multiline ? 'textarea' : 'input', { id: field.id, field: true, value: fieldModel ? fieldModel.value : field.value || '', type: 'text' }), fieldModel, 'design-system/components/Field.tsx'));
    });
    const actions = (view.secondary || []).map(function (action) {
      const buttonModel = model('Button', { label: action.label }, enabled);
      return mark(element(document, 'button', { id: action.focus || action.id, type: 'button', text: buttonModel ? buttonModel.label : action.label, action: action.id }), buttonModel, 'design-system/components/Button.tsx');
    });
    if (view.primary) {
      const buttonModel = model('Button', { label: view.primary.label }, enabled);
      actions.push(mark(element(document, 'button', { id: 'primary-action', type: 'button', text: buttonModel ? buttonModel.label : view.primary.label, action: view.primary.id, remote: view.primary.remote, disabled: view.primary.disabled }), buttonModel, 'design-system/components/Button.tsx'));
    }
    if (actions.length) main.append(element(document, 'div', { className: 'actions', children: actions }));
    if (view.dialog) {
      const dialogModel = model('Dialog', { label: view.dialog.title, open: true }, enabled);
      const dialogLabel = dialogModel ? dialogModel.label : view.dialog.title;
      const dialog = mark(element(document, 'div', { id: 'dialog', className: 'dialog', role: 'dialog', modal: 'true', label: dialogLabel, children: [element(document, 'h2', { text: dialogLabel })] }), dialogModel, 'design-system/components/Dialog.tsx');
      (view.dialog.fields || []).forEach(function (field) {
        dialog.append(element(document, 'label', { text: field.label, forId: field.id }));
        dialog.append(element(document, 'input', { id: field.id, field: true, value: field.value || '', type: 'text' }));
      });
      dialog.append(element(document, 'button', { id: 'dialog-close', type: 'button', text: '닫기', action: 'close-dialog' }));
      main.append(dialog);
    }
    shell.append(main);
    app.append(shell);
  }

  function focus(document, view) {
    if (!view.focus) return null;
    const node = document.getElementById(view.focus);
    if (node && node.focus) node.focus();
    return node;
  }

  globalThis.RegressionPaint = { paint: paint, focus: focus };
})();
