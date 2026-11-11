(function () {
  function compile(routes) {
    return routes.map(function (route) {
      const names = [];
      const pattern = route.path.replace(/:([A-Za-z]+)/g, function (_, name) {
        names.push(name);
        return '([^/]+)';
      });
      return { route: route, names: names, regex: new RegExp('^' + pattern + '$') };
    });
  }

  function match(routes, path) {
    for (const item of compile(routes)) {
      const found = item.regex.exec(path);
      if (!found) continue;
      const params = {};
      item.names.forEach(function (name, index) {
        params[name] = decodeURIComponent(found[index + 1]);
      });
      return { route: item.route, params: params };
    }
    return null;
  }

  function screenPath(routes, screenId, samples) {
    const route = routes.find(function (item) { return item.id === screenId; });
    if (!route || route.path.indexOf('/') !== 0) return null;
    return route.path.replace(/:([A-Za-z]+)/g, function (_, name) {
      return samples[name] || name;
    });
  }

  function pageItems(items, list, textOf) {
    const filtered = list.filter ? items.filter(function (item) { return textOf(item).includes(list.filter); }) : items.slice();
    const sorted = filtered.slice().sort(function (a, b) {
      if (list.sort === 'name') return textOf(a).localeCompare(textOf(b), 'ko') || String(a.id).localeCompare(String(b.id));
      return String(a.due || '').localeCompare(String(b.due || '')) || String(a.id).localeCompare(String(b.id));
    });
    const pageSize = list.pageSize || 20;
    const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
    const page = Math.min(Math.max(list.page || 1, 1), pages);
    const start = (page - 1) * pageSize;
    return {
      rows: sorted.slice(start, start + pageSize),
      total: sorted.length,
      page: page,
      pages: pages,
      measured: 'current page only',
    };
  }

  function patch(state, values) {
    return Object.assign({}, state, values);
  }

  function copy(value) {
    return JSON.parse(JSON.stringify(value));
  }

  globalThis.RegressionRouter = {
    compile: compile,
    match: match,
    screenPath: screenPath,
    pageItems: pageItems,
    patch: patch,
    copy: copy,
  };
})();
