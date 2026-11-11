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
    (props.children || []).forEach(function (child) { node.append(child); });
    return node;
  }

  function paint(document, view) {
    const app = document.getElementById('app');
    app.replaceChildren();
    document.title = view.title;
    const nav = element(document, 'nav', { id: 'nav', label: '주요 이동' });
    (view.nav || []).forEach(function (item) {
      nav.append(element(document, 'a', { text: item.label, href: item.href, className: item.current ? 'current' : '' }));
    });
    const heading = element(document, 'h1', { id: 'screen-title', text: view.title });
    const pieces = [nav, heading];
    if (view.notice) pieces.push(element(document, 'p', { id: 'notice', className: view.notice.kind, text: view.notice.text }));
    if (view.access === 'denied' || view.access === 'readonly') {
      pieces.push(element(document, 'p', { id: 'access', text: view.access === 'denied' ? '이 역할로는 열 수 없습니다.' : '읽기 전용입니다.' }));
    }
    if (view.returnPath) pieces.push(element(document, 'p', { id: 'return-path', text: view.returnPath }));
    (view.sections || []).forEach(function (section) {
      pieces.push(element(document, 'section', {
        id: section.id,
        className: 'input-section',
        children: [
          element(document, 'h2', { text: section.title }),
          element(document, 'p', { text: section.gap || section.token || section.components && section.components.join(' ') || '' }),
        ],
      }));
    });
    if (view.longText) pieces.push(element(document, 'p', { id: 'long-copy', text: [view.longText.ko, view.longText.en, view.longText.ja].join(' / ') }));
    if (view.table) {
      pieces.push(element(document, 'label', { text: '목록 필터', forId: 'list-filter' }));
      pieces.push(element(document, 'input', { id: 'list-filter', field: true, value: (view.list && view.list.filter) || '', type: 'search', label: '목록 필터' }));
      const table = element(document, 'table', { id: 'data-table' });
      const head = element(document, 'tr', {});
      view.table.columns.forEach(function (column) { head.append(element(document, 'th', { text: column })); });
      table.append(head);
      view.table.rows.forEach(function (row) {
        const line = element(document, 'tr', {});
        row.forEach(function (cell) { line.append(element(document, 'td', { text: String(cell) })); });
        table.append(line);
      });
      pieces.push(table);
      pieces.push(element(document, 'p', { id: 'table-meta', text: view.table.measured + ' ' + view.table.total }));
    }
    (view.cards || []).forEach(function (card) {
      pieces.push(element(document, 'article', { className: 'card', children: [element(document, 'h2', { text: card.title }), element(document, 'p', { text: card.meta || '' })] }));
    });
    if (view.prose) pieces.push(element(document, 'article', { id: 'prose', className: 'prose', children: [element(document, 'p', { text: view.prose })] }));
    (view.fields || []).forEach(function (field) {
      pieces.push(element(document, 'label', { text: field.label, forId: field.id }));
      pieces.push(element(document, field.multiline ? 'textarea' : 'input', { id: field.id, field: true, value: field.value || '', type: 'text' }));
    });
    (view.secondary || []).forEach(function (action) {
      pieces.push(element(document, 'button', { id: action.focus || action.id, type: 'button', text: action.label, action: action.id }));
    });
    if (view.primary) {
      pieces.push(element(document, 'button', {
        id: 'primary-action',
        type: 'button',
        text: view.primary.label,
        action: view.primary.id,
        remote: view.primary.remote,
        disabled: view.primary.disabled,
      }));
    }
    if (view.dialog) {
      const dialog = element(document, 'div', { id: 'dialog', role: 'dialog', modal: 'true', label: view.dialog.title, children: [element(document, 'h2', { text: view.dialog.title })] });
      (view.dialog.fields || []).forEach(function (field) {
        dialog.append(element(document, 'label', { text: field.label, forId: field.id }));
        dialog.append(element(document, 'input', { id: field.id, field: true, value: field.value || '', type: 'text' }));
      });
      dialog.append(element(document, 'button', { id: 'dialog-close', type: 'button', text: '닫기', action: 'close-dialog' }));
      pieces.push(dialog);
    }
    pieces.forEach(function (piece) { app.append(piece); });
  }

  function focus(document, view) {
    if (!view.focus) return null;
    const node = document.getElementById(view.focus);
    if (node && node.focus) node.focus();
    return node;
  }

  globalThis.RegressionPaint = { paint: paint, focus: focus };
})();
