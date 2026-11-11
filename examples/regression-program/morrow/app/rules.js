(function () {
  const router = globalThis.RegressionRouter;
  const BASE = [
    { id: 'linen', name: '리넨 냅킨', price: 12000, stock: 4, material: '리넨' },
    { id: 'oak', name: '오크 도마', price: 38000, stock: 2, material: '나무' },
    { id: 'bowl', name: '모래 그릇', price: 16000, stock: 6, material: '도자' },
    { id: 'cloth', name: '먹색 식탁보', price: 42000, stock: 3, material: '면' },
  ];

  function productsOf(count) {
    const rows = BASE.slice();
    for (let index = rows.length; index < count; index += 1) {
      rows.push({ id: 'p-' + (index + 1), name: '상품 ' + (index + 1), price: 1000 + index, stock: (index % 5) + 1, material: '종이' });
    }
    return rows.slice(0, Math.max(count, 0));
  }

  function createState(app, options) {
    options = options || {};
    return {
      app: app,
      design: options.designSystem || null,
      longTextCopy: options.longTextCopy || null,
      seed: options.seed || 20261111,
      role: options.role || 'customer',
      path: options.path || '/',
      faults: Object.assign({}, options.faults),
      inputs: Object.assign({ html: false, url: false, designSystem: false }, options.inputs),
      cart: [],
      orders: router.copy(options.orders || []),
      saved: [],
      returns: {},
      checkout: { contact: '', delivery: '', priceSeen: false },
      list: { page: 1, sort: 'name', filter: '', pageSize: 20 },
      form: { reason: '', note: '' },
      history: [],
      future: [],
      notice: null,
      focus: null,
      longText: !!options.longText,
      productCount: options.productCount || 12,
      dialog: null,
    };
  }

  function decideOrder(payload) {
    if (payload.fault === 'stock') return { status: 409, body: { ok: false, error: 'stock-conflict', orders: payload.existing || [] } };
    if (payload.fault === 'price' && !payload.priceSeen) return { status: 409, body: { ok: false, error: 'price-changed', price: payload.nextPrice, orders: payload.existing || [] } };
    if ((payload.existingSignatures || []).includes(payload.signature)) return { status: 200, body: { ok: true, duplicate: true, orderId: payload.existingOrderId } };
    return { status: 200, body: { ok: true, duplicate: false, orderId: payload.nextOrderId } };
  }

  function decideReturn(payload) {
    const form = payload.form || {};
    if (!form || typeof form !== 'object' || typeof form.reason !== 'string' || typeof form.note !== 'string') return { status: 400, body: { ok: false, error: 'invalid-draft' } };
    if (payload.fault === 'return') return { status: 409, body: { ok: false, error: 'return-failed', form: form } };
    if (!form.reason.trim()) return { status: 400, body: { ok: false, error: 'reason-required', form: form } };
    return { status: 200, body: { ok: true, returnId: payload.nextReturnId } };
  }

  function signatureOf(cart) {
    return cart.map(function (item) { return item.productId + ':' + item.qty; }).join(',');
  }

  function payloadFor(state, action, fields) {
    fields = fields || {};
    if (action === 'ACT-MORROW-10') {
      const signature = signatureOf(state.cart);
      const existing = state.orders.find(function (order) { return order.signature === signature; });
      return {
        fault: state.faults.stock ? 'stock' : state.faults.price ? 'price' : '',
        existing: state.orders.map(function (order) { return order.id; }),
        existingSignatures: state.orders.map(function (order) { return order.signature; }),
        existingOrderId: existing ? existing.id : '',
        signature: signature,
        nextOrderId: 'order-' + (state.orders.length + 1),
        priceSeen: !!state.checkout.priceSeen,
        nextPrice: 18000,
      };
    }
    if (action === 'ACT-MORROW-14') {
      return {
        fault: state.faults.return ? 'return' : '',
        form: { reason: fields['return-reason'] != null ? fields['return-reason'] : state.form.reason, note: fields['return-note'] != null ? fields['return-note'] : state.form.note },
        nextReturnId: 'ret-' + (Object.keys(state.returns).length + 1),
      };
    }
    return {};
  }

  function decideFor(action, payload) {
    if (action === 'ACT-MORROW-10') return decideOrder(payload);
    if (action === 'ACT-MORROW-14') return decideReturn(payload);
    return { status: 204, body: {} };
  }

  function remember(state, path, extra) {
    return router.patch(state, Object.assign({
      history: state.history.concat([{ path: state.path, list: router.copy(state.list), form: router.copy(state.form), checkout: router.copy(state.checkout) }]),
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
    const guestBlocked = state.role !== 'customer' && route.id === 'SCR-MORROW-10';
    return Object.assign({
      id: route.id,
      path: route.path,
      title: route.title,
      access: guestBlocked ? 'readonly' : 'allowed',
      state: 'content',
      notice: state.notice,
      primary: guestBlocked ? null : { id: route.primary.id, label: state.longText && route.id === 'SCR-MORROW-04' ? state.longTextCopy.ko : route.primary.label, remote: route.primary.remote || null },
      nav: [['/', '식탁'], ['/search', '찾기'], ['/saved', '보관'], ['/cart', '장바구니'], ['/orders', '주문']].map(function (item) {
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
    if (state.faults.load === 'loading') return shell(state, route, { state: 'loading', notice: { kind: 'info', text: '불러오는 중입니다.' } });
    if (state.faults.load === 'error') return shell(state, route, { state: 'error', notice: { kind: 'error', text: '목록을 불러오지 못했습니다.' }, secondary: [{ id: 'retry', label: '다시 시도', focus: 'retry' }] });
    const products = productsOf(state.productCount);
    if (route.id === 'SCR-MORROW-02' || route.id === 'SCR-MORROW-03' || route.id === 'SCR-MORROW-06') {
      const source = route.id === 'SCR-MORROW-06' ? products.filter(function (item) { return state.saved.includes(item.id); }) : products.filter(function (item) { return route.id !== 'SCR-MORROW-02' || item.material; });
      const page = router.pageItems(source, state.list, function (item) { return item.name + ' ' + item.material; });
      if (page.total === 0) return shell(state, route, { state: 'empty', notice: { kind: 'info', text: '조건에 맞는 상품이 없습니다.' } });
      return shell(state, route, { cards: page.rows.map(function (item) { return { id: item.id, title: item.name, meta: item.price + '원 · 재고 ' + item.stock }; }), table: { columns: ['상품'], rows: page.rows.map(function (item) { return [item.name]; }), total: page.total, page: page.page, pages: page.pages, measured: page.measured } });
    }
    if (route.id === 'SCR-MORROW-04') {
      const product = products.find(function (item) { return item.id === located.params.productId; }) || products[0];
      return shell(state, route, { prose: product.name + ' · ' + product.price + '원 · 재고 ' + product.stock, secondary: [{ id: 'save-product', label: '보관', focus: 'save-product' }] });
    }
    if (route.id === 'SCR-MORROW-05') {
      return shell(state, route, { table: { columns: ['상품', '가격', '재고'], rows: products.slice(0, 2).map(function (item) { return [item.name, String(item.price), String(item.stock)]; }), total: 2, page: 1, pages: 1, measured: 'current page only' } });
    }
    if (route.id === 'SCR-MORROW-07') {
      return shell(state, route, { table: { columns: ['상품', '수량'], rows: state.cart.map(function (item) { return [item.productId, String(item.qty)]; }), total: state.cart.length, page: 1, pages: 1, measured: 'current page only' }, state: state.cart.length ? 'content' : 'empty' });
    }
    if (route.id === 'SCR-MORROW-08') return shell(state, route, { fields: [{ id: 'contact-name', label: '주문자', value: state.checkout.contact }] });
    if (route.id === 'SCR-MORROW-09') return shell(state, route, { fields: [{ id: 'delivery-note', label: '배송 메모', value: state.checkout.delivery }], secondary: [{ id: 'back', label: '이전 단계', focus: 'back' }] });
    if (route.id === 'SCR-MORROW-10') {
      const price = state.faults.price ? 18000 : state.cart.reduce(function (sum, item) { return sum + item.price * item.qty; }, 0);
      return shell(state, route, { prose: '확인할 금액 ' + price + '원', secondary: state.faults.price ? [{ id: 'ack-price', label: '바뀐 가격 확인', focus: 'ack-price' }] : [] });
    }
    if (route.id === 'SCR-MORROW-12' || route.id === 'SCR-MORROW-13' || route.id === 'SCR-MORROW-11') {
      return shell(state, route, { prose: state.orders.map(function (order) { return order.id; }).join(', ') || '접수한 주문이 없습니다.' });
    }
    if (route.id === 'SCR-MORROW-14') {
      return shell(state, route, { fields: [{ id: 'return-reason', label: '반품 사유', value: state.form.reason }, { id: 'return-note', label: '설명', value: state.form.note, multiline: true }] });
    }
    const page = router.pageItems(products, state.list, function (item) { return item.name; });
    return shell(state, route, { prose: '이번 주 식탁에 올릴 상품 ' + page.total + '개', cards: page.rows.slice(0, 4).map(function (item) { return { id: item.id, title: item.name, meta: item.material }; }) });
  }

  function dispatch(state, action, payload) {
    payload = payload || {};
    if (action === 'navigate') return remember(state, payload.path || state.path);
    if (action === 'back') {
      if (!state.history.length) return state;
      const previous = state.history[state.history.length - 1];
      return router.patch(state, { history: state.history.slice(0, -1), future: state.future.concat([{ path: state.path, list: state.list, form: state.form, checkout: state.checkout }]), path: previous.path, list: previous.list, form: previous.form, checkout: previous.checkout, notice: null });
    }
    if (action === 'set-filter') return router.patch(state, { list: Object.assign({}, state.list, { filter: payload.filter || '', page: 1 }) });
    if (action === 'set-page') return router.patch(state, { list: Object.assign({}, state.list, { page: Number(payload.page) || 1 }) });
    if (action === 'retry') {
      const faults = Object.assign({}, state.faults);
      delete faults.load;
      return router.patch(state, { faults: faults, notice: null });
    }
    if (action === 'save-product') {
      const located = router.match(state.app.routes, state.path);
      const productId = located && located.params.productId || state.app.samples.productId;
      const saved = state.saved.includes(productId) ? state.saved : state.saved.concat([productId]);
      return router.patch(state, { saved: saved, notice: { kind: 'saved', text: '보관한 상품에 넣었습니다.' } });
    }
    if (action === 'ack-price') return router.patch(state, { checkout: Object.assign({}, state.checkout, { priceSeen: true }), notice: { kind: 'info', text: '바뀐 가격을 확인했습니다.' } });
    if (action === 'ACT-MORROW-04') {
      const located = router.match(state.app.routes, state.path);
      const productId = located && located.params.productId || state.app.samples.productId;
      const product = productsOf(state.productCount).find(function (item) { return item.id === productId; });
      const cart = state.cart.concat([{ productId: product.id, qty: 1, price: product.price }]);
      return remember(router.patch(state, { cart: cart }), '/cart');
    }
    if (action === 'ACT-MORROW-08') {
      const contact = payload['contact-name'] != null ? payload['contact-name'] : state.checkout.contact;
      return remember(router.patch(state, { checkout: Object.assign({}, state.checkout, { contact: contact }) }), '/checkout/delivery');
    }
    if (action === 'ACT-MORROW-09') {
      const delivery = payload['delivery-note'] != null ? payload['delivery-note'] : state.checkout.delivery;
      return remember(router.patch(state, { checkout: Object.assign({}, state.checkout, { delivery: delivery }) }), '/checkout/review');
    }
    if (action === 'ACT-MORROW-10') {
      if (state.role !== 'customer') return router.patch(state, { notice: { kind: 'error', text: '고객 역할에서만 접수합니다.' } });
      const body = payloadFor(state, action, payload);
      const decision = decideOrder(body);
      if (decision.status !== 200) {
        const text = decision.body.error === 'price-changed' ? '가격이 바뀌었습니다. 주문은 늘어나지 않았습니다.' : '재고가 바뀌었습니다. 주문은 늘어나지 않았습니다.';
        return router.patch(state, { notice: { kind: 'error', text: text }, focus: 'primary-action' });
      }
      if (decision.body.duplicate) return remember(state, '/orders/complete/' + decision.body.orderId, { notice: { kind: 'info', text: '이미 접수된 주문입니다.' } });
      const order = { id: decision.body.orderId, signature: body.signature, cart: router.copy(state.cart), price: state.faults.price ? 18000 : state.cart.reduce(function (sum, item) { return sum + item.price * item.qty; }, 0) };
      return remember(router.patch(state, { orders: state.orders.concat([order]) }), '/orders/complete/' + order.id);
    }
    if (action === 'ACT-MORROW-14') {
      const body = payloadFor(state, action, payload);
      const decision = decideReturn(body);
      const form = body.form;
      if (decision.status !== 200) return router.patch(state, { form: form, notice: { kind: 'error', text: '반품을 접수하지 못했습니다. 입력은 그대로입니다.' }, focus: 'return-note' });
      const located = router.match(state.app.routes, state.path);
      const orderId = located && located.params.orderId || state.app.samples.orderId;
      const returns = Object.assign({}, state.returns, { [orderId]: { id: decision.body.returnId, form: form } });
      return router.patch(state, { form: form, returns: returns, notice: { kind: 'saved', text: '반품을 접수했습니다.' }, focus: null });
    }
    const located = router.match(state.app.routes, state.path);
    if (!located || located.route.primary.id !== action) return router.patch(state, { notice: { kind: 'error', text: '지원하지 않는 동작입니다.' } });
    const target = located.route.primary.to.map(function (screenId) { return router.screenPath(state.app.routes, screenId, state.app.samples); }).find(Boolean);
    return target ? remember(state, target) : state;
  }

  function snapshot(state) {
    return router.copy({ cart: state.cart, orders: state.orders, saved: state.saved, returns: state.returns, checkout: state.checkout, form: state.form, role: state.role, list: state.list });
  }

  function hydrate(state, saved) {
    return router.patch(state, router.copy(saved));
  }

  globalThis.RegressionApps = globalThis.RegressionApps || {};
  globalThis.RegressionApps.morrow = {
    createState: createState,
    view: view,
    dispatch: dispatch,
    snapshot: snapshot,
    hydrate: hydrate,
    decideOrder: decideOrder,
    decideReturn: decideReturn,
    decideFor: decideFor,
    payloadFor: payloadFor,
    markMismatch: function (state) { return router.patch(state, { notice: { kind: 'error', text: '모의 서버와 화면 규칙이 달라 저장하지 않았습니다.' } }); },
    withPath: function (state, path, extra) { return router.patch(state, Object.assign({ path: path }, extra || {})); },
  };
})();
