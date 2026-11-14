const SVG_NS = 'http://www.w3.org/2000/svg';
const ROUTE = /^#\/([a-z-]+)(?:\/([a-z-]+))?(?:\?package=([a-z0-9-]+))?$/;

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'className') node.className = value;
    else if (key === 'textContent') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, String(value));
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key]));
}

function indexGraph(graph) {
  const byId = new Map(graph.nodes.map(node => [node.id, node]));
  const outgoing = (id, type) => graph.edges
    .filter(edge => edge.from === id && edge.type === type)
    .map(edge => byId.get(edge.to));
  const screens = graph.nodes.filter(node => node.type === 'screen');
  const screenOfState = new Map();
  for (const screen of screens) {
    for (const state of outgoing(screen.id, 'has state')) screenOfState.set(state.id, screen);
  }
  const componentKeys = new Set(graph.nodes.filter(node => node.type === 'component').map(node => node.component_key));
  return {
    screens,
    screenOfState,
    statesOf: screen => outgoing(screen.id, 'has state'),
    follow(state, control, outcome) {
      const actions = outgoing(state.id, 'accepts input')
        .filter(action => action.control === control && (action.outcome === undefined || action.outcome === outcome));
      return actions.length === 1 ? outgoing(actions[0].id, 'navigates to')[0] : null;
    },
    component: key => (componentKeys.has(key) ? key : null),
  };
}

function createChevron(open, tokens) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'trigger-chevron');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('width', '16');
  svg.setAttribute('height', '16');
  const group = document.createElementNS(SVG_NS, 'g');
  if (open) group.setAttribute('transform', 'rotate(180 8 8)');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', 'M4 6L8 10L12 6');
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', open ? tokens['ink-accent'] : tokens['ink-secondary']);
  path.setAttribute('stroke-width', '1.75');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  group.append(path);
  svg.append(group);
  return svg;
}

const svgCache = new Map();

function inlineSvg(frame, asset) {
  if (!svgCache.has(asset)) {
    svgCache.set(asset, fetch(asset).then(response => {
      if (!response.ok) throw new Error(`${response.status} ${asset}`);
      return response.text();
    }));
  }
  return svgCache.get(asset).then(text => {
    const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
    const root = doc.documentElement;
    if (root.localName !== 'svg' || doc.querySelector('parsererror, script, foreignObject')) {
      throw new Error(`Rejected media ${asset}`);
    }
    root.setAttribute('aria-hidden', 'true');
    frame.replaceChildren(document.importNode(root, true));
  }).catch(error => {
    frame.setAttribute('data-media-error', error.message);
  });
}

function mediaFrame(media, pending) {
  const frame = el('div', { className: 'media-frame', role: 'img', 'aria-label': media.alt });
  pending.push(inlineSvg(frame, media.asset));
  return frame;
}

function drawTrend(canvas, points, tokens) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 300;
  const height = canvas.clientHeight || 160;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const pad = 12;
  const slot = (width - pad * 2) / points.length;
  const barWidth = Math.min(36, slot * 0.6);
  const chartHeight = height - pad * 2;
  points.forEach((point, index) => {
    const x = pad + slot * index + (slot - barWidth) / 2;
    const filled = chartHeight * (point.passed / point.total);
    ctx.fillStyle = tokens['bg-accent'];
    ctx.fillRect(x, pad, barWidth, chartHeight);
    ctx.fillStyle = tokens['ink-accent'];
    ctx.fillRect(x, pad + chartHeight - filled, barWidth, filled);
  });
  ctx.strokeStyle = tokens['border-control'];
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, height - pad + 0.5);
  ctx.lineTo(width - pad, height - pad + 0.5);
  ctx.stroke();
}

async function mount() {
  const response = await fetch('./graph.json');
  if (!response.ok) throw new Error('graph.json could not be loaded');
  const graph = await response.json();
  const data = graph.workspace;
  const copy = data.copy;
  const tokens = data.tokens;
  const g = indexGraph(graph);
  const statusOf = new Map(data.statuses.map(status => [status.key, status]));
  const teamOf = new Map(data.teams.map(team => [team.key, team]));
  const resultOf = new Map(data.gate_results.map(result => [result.key, result]));
  const decisionOf = new Map(data.decisions.map(decision => [decision.key, decision]));
  const packageOf = new Map(data.packages.map(pkg => [pkg.key, pkg]));
  const queueScreen = g.screens.find(screen => screen.layout === 'queue');
  const reviewScreen = g.screens.find(screen => screen.layout === 'review');

  for (const [name, value] of Object.entries(tokens)) {
    document.documentElement.style.setProperty(`--${name}`, value);
  }
  const root = document.getElementById('workspace-root');

  let model = null;
  let fromAction = false;
  let pendingFocus = null;

  function initialOf(screen) {
    return g.statesOf(screen).find(state => state.initial);
  }

  function hrefFor(state, packageKey) {
    const screen = g.screenOfState.get(state.id);
    const path = state.initial ? `#/${screen.route}` : `#/${screen.route}/${state.route}`;
    return screen.layout === 'review' ? `${path}?package=${packageKey}` : path;
  }

  function resolveRoute() {
    const match = ROUTE.exec(location.hash);
    const screen = match && g.screens.find(candidate => candidate.route === match[1]);
    const state = screen && (match[2]
      ? g.statesOf(screen).find(candidate => candidate.route === match[2] && !candidate.initial)
      : initialOf(screen));
    if (!state) return null;
    const packageKey = packageOf.has(match[3]) ? match[3] : data.default_package;
    return { screen, state, packageKey };
  }

  function freshModel(state, packageKey) {
    const fixture = state.route_fixture || {};
    return {
      packageKey,
      filter: { query: fixture.query || '', status: fixture.status || '' },
      decision: { choice: fixture.decision || '', note: fixture.note || '' },
      openGate: null,
    };
  }

  function go(state, focusId) {
    fromAction = true;
    pendingFocus = focusId;
    const href = hrefFor(state, model.packageKey);
    if (location.hash === href) render();
    else location.hash = href;
  }

  function visibleRows() {
    const query = model.filter.query.trim().toLowerCase();
    return data.packages.filter(pkg => (!model.filter.status || pkg.status === model.filter.status)
      && (!query || [pkg.code, pkg.title, pkg.family].some(text => text.toLowerCase().includes(query))));
  }

  function decisionErrors() {
    const errors = [];
    const decision = decisionOf.get(model.decision.choice);
    if (!decision) errors.push({ field: 'decision-first', message: copy.error_decision });
    else if (decision.requires_note && model.decision.note.trim().length < data.note_min_length) {
      errors.push({ field: 'decision-note', message: copy.error_note });
    }
    return errors;
  }

  function badge(entry) {
    return el('span', {
      className: 'badge',
      'data-tone': entry.tone,
      'data-component': g.component('status-badge'),
      textContent: entry.label,
    });
  }

  function field({ id, label, hint, error, control }) {
    const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ');
    if (describedBy) control.setAttribute('aria-describedby', describedBy);
    if (error) control.setAttribute('aria-invalid', 'true');
    return el('div', { className: 'field', 'data-component': g.component('form-field') }, [
      el('label', { className: 'field-label', for: id, textContent: label }),
      control,
      hint && el('p', { className: 'field-hint', id: `${id}-hint`, textContent: hint }),
      error && el('p', { className: 'field-error', id: `${id}-error`, textContent: error }),
    ]);
  }

  function renderQueue(state) {
    const kind = state.kind;
    const disabled = kind === 'error';
    const rows = disabled ? [] : visibleRows();

    const summary = disabled ? null : el('ul', { className: 'summary-grid', 'aria-label': copy.summary_heading },
      data.statuses.map(status => el('li', { className: 'summary-tile' }, [
        el('span', {
          className: 'summary-count',
          textContent: String(data.packages.filter(pkg => pkg.status === status.key).length),
        }),
        badge(status),
      ])));

    const search = el('input', {
      className: 'control', id: 'filter-search', type: 'search', name: 'query', value: model.filter.query, disabled,
    });
    const select = el('select', { className: 'control', id: 'filter-status', name: 'status', disabled }, [
      el('option', { value: '', textContent: copy.status_all }),
      ...data.statuses.map(status => el('option', {
        value: status.key, selected: status.key === model.filter.status, textContent: status.label,
      })),
    ]);

    const form = el('form', {
      className: 'card',
      role: 'search',
      'aria-labelledby': 'filter-legend',
      onsubmit(event) {
        event.preventDefault();
        model.filter = { query: search.value, status: select.value };
        const outcome = visibleRows().length ? 'match' : 'none';
        go(g.follow(state, 'filter', outcome) || state, 'filter-apply');
      },
    }, [
      el('fieldset', { className: 'filter-form', disabled }, [
        el('legend', { className: 'filter-legend', id: 'filter-legend', textContent: copy.filter_legend }),
        el('div', { className: 'filter-grid' }, [
          field({ id: 'filter-search', label: copy.search_label, hint: copy.search_hint, control: search }),
          field({ id: 'filter-status', label: copy.status_label, control: select }),
          el('div', { className: 'filter-actions' }, [
            el('button', { className: 'button button-primary', id: 'filter-apply', type: 'submit', textContent: copy.filter_apply }),
            el('button', { className: 'button', id: 'filter-clear', type: 'button', textContent: copy.filter_clear, onclick: clearFilters }),
          ]),
        ]),
      ]),
    ]);

    function clearFilters() {
      model.filter = { query: '', status: '' };
      go(g.follow(state, 'clear-filters') || state, 'filter-search');
    }

    let body;
    if (kind === 'error') {
      const retry = g.follow(state, 'retry');
      body = el('div', { className: 'notice', 'data-tone': state.tone, role: 'alert' }, [
        el('div', { className: 'notice-body' }, [
          el('h3', { className: 'notice-title', textContent: state.title }),
          el('p', { className: 'notice-detail', textContent: state.detail }),
        ]),
        retry && el('button', {
          className: 'button', id: 'queue-retry', type: 'button', textContent: copy.retry,
          onclick: () => go(retry, 'screen-title'),
        }),
      ]);
    } else if (kind === 'empty') {
      body = el('div', { className: 'notice' }, [
        mediaFrame(data.empty_media, pendingMedia),
        el('div', { className: 'notice-body' }, [
          el('h3', { className: 'notice-title', textContent: state.title }),
          el('p', { className: 'notice-detail', textContent: state.detail }),
        ]),
        el('button', { className: 'button', type: 'button', textContent: copy.filter_clear, onclick: clearFilters }),
      ]);
    } else {
      const openReview = pkg => {
        model.packageKey = pkg.key;
        model.decision = { choice: '', note: '' };
        model.openGate = null;
        const target = g.follow(state, 'open-review');
        if (target) go(target, 'screen-title');
      };
      const columns = [copy.col_package, copy.col_family, copy.col_team, copy.col_status, copy.col_gates, copy.col_updated, copy.col_action];
      body = el('div', { className: 'table-scroll' }, [
        el('table', { className: 'data-table', 'data-component': g.component('data-table') }, [
          el('caption', { textContent: copy.table_caption }),
          el('thead', {}, [el('tr', {}, columns.map(label => el('th', { scope: 'col', textContent: label })))]),
          el('tbody', {}, rows.map(pkg => {
            const results = Object.values(pkg.gate_results);
            return el('tr', {}, [
              el('th', { scope: 'row' }, [pkg.title, el('span', { className: 'row-code', textContent: pkg.code })]),
              el('td', { textContent: pkg.family }),
              el('td', { textContent: teamOf.get(pkg.team).label }),
              el('td', {}, [badge(statusOf.get(pkg.status))]),
              el('td', { textContent: fill(copy.gates_value, { passed: results.filter(key => resultOf.get(key).passed).length, total: results.length }) }),
              el('td', {}, [el('time', { datetime: pkg.updated, textContent: pkg.updated })]),
              el('td', {}, [el('button', {
                className: 'button button-compact', type: 'button', textContent: copy.open_review,
                'aria-label': fill(copy.open_review_label, pkg), onclick: () => openReview(pkg),
              })]),
            ]);
          })),
        ]),
      ]);
    }

    const resultCount = disabled ? null : el('p', {
      className: 'result-count', role: 'status',
      textContent: fill(copy.result_count, { count: rows.length, total: data.packages.length }),
    });

    return [summary, form, el('div', { className: 'card' }, [resultCount, body])];
  }

  function renderReview(state) {
    const pkg = packageOf.get(model.packageKey);
    const kind = state.kind;
    const locked = kind === 'recorded';
    const errors = kind === 'invalid' ? decisionErrors() : [];
    const errorFor = id => errors.find(error => error.field === id)?.message;
    const back = g.follow(state, 'back');

    const head = el('section', { className: 'card' }, [
      el('div', { className: 'package-head' }, [
        el('div', {}, [
          el('h3', { className: 'package-title', textContent: pkg.title }),
          el('p', {
            className: 'package-meta',
            textContent: fill(copy.package_meta, { code: pkg.code, team: teamOf.get(pkg.team).label, updated: pkg.updated }),
          }),
        ]),
        badge(statusOf.get(pkg.status)),
      ]),
      back && el('button', {
        className: 'button', id: 'review-back', type: 'button', textContent: copy.back,
        onclick() {
          model.filter = { query: '', status: '' };
          go(back, 'screen-title');
        },
      }),
    ]);

    const accordion = el('div', { className: 'disclosure-list', 'data-slot': 'accordion' });
    const gateItems = data.gates.map((gate, index) => {
      const open = model.openGate === gate.key;
      const triggerId = `gate-trigger-${index + 1}`;
      const panelId = `gate-panel-${index + 1}`;
      return el('div', {
        className: 'disclosure-item', 'data-slot': 'accordion-item', 'data-state': open ? 'open' : 'closed',
        'data-component': g.component('gate-disclosure'),
      }, [
        el('div', { className: 'disclosure-row' }, [
          el('h4', { className: 'disclosure-heading' }, [
            el('button', {
              className: 'disclosure-trigger', type: 'button', id: triggerId, 'data-slot': 'accordion-trigger',
              'aria-expanded': String(open), 'aria-controls': panelId, 'data-state': open ? 'open' : 'closed',
              onclick() {
                model.openGate = open ? null : gate.key;
                fromAction = true;
                pendingFocus = triggerId;
                render();
              },
            }, [el('span', { className: 'trigger-label', textContent: gate.title }), createChevron(open, tokens)]),
          ]),
          badge(resultOf.get(pkg.gate_results[gate.key])),
        ]),
        el('div', {
          className: 'disclosure-panel', id: panelId, role: 'region', 'aria-labelledby': triggerId,
          'data-slot': 'accordion-content', 'data-state': open ? 'open' : 'closed', hidden: !open,
        }, [el('ul', { className: 'check-list' }, gate.checks.map(check => el('li', { textContent: check })))]),
      ]);
    });
    accordion.replaceChildren(...gateItems);
    const gates = el('section', { className: 'card', 'aria-labelledby': 'gates-title' }, [
      el('div', { className: 'card-head' }, [
        el('h3', { className: 'card-title', id: 'gates-title', textContent: copy.gates_heading }),
        el('span', { className: 'badge', textContent: copy.gates_mode }),
      ]),
      accordion,
    ]);

    const rail = el('ul', { className: 'rail', id: 'evidence-rail', tabindex: '0', 'aria-labelledby': 'evidence-title' },
      data.evidence.map((item, index) => el('li', {
        className: 'rail-card', 'data-component': g.component('evidence-card'),
      }, [
        mediaFrame(item, pendingMedia),
        el('h4', { className: 'rail-card-title', textContent: item.title }),
        el('p', { className: 'rail-card-caption', textContent: item.caption }),
        el('span', {
          className: 'rail-card-position',
          textContent: fill(copy.evidence_position, { index: index + 1, count: data.evidence.length }),
        }),
      ])));
    const step = direction => () => {
      const card = rail.firstElementChild;
      rail.scrollBy({ left: direction * (card ? card.getBoundingClientRect().width + 12 : rail.clientWidth), behavior: 'smooth' });
    };
    const evidence = el('section', { className: 'card', 'aria-labelledby': 'evidence-title' }, [
      el('div', { className: 'card-head' }, [
        el('h3', { className: 'card-title', id: 'evidence-title', textContent: copy.evidence_heading }),
        el('div', { className: 'rail-controls' }, [
          el('button', { className: 'button button-compact', type: 'button', 'aria-controls': 'evidence-rail', textContent: copy.evidence_previous, onclick: step(-1) }),
          el('button', { className: 'button button-compact', type: 'button', 'aria-controls': 'evidence-rail', textContent: copy.evidence_next, onclick: step(1) }),
        ]),
      ]),
      rail,
    ]);

    const canvas = el('canvas', { className: 'trend-canvas', role: 'img', 'aria-labelledby': 'trend-title' });
    const trend = el('section', { className: 'card', 'aria-labelledby': 'trend-title' }, [
      el('h3', { className: 'card-title', id: 'trend-title', textContent: copy.trend_heading }),
      canvas,
      el('ul', { className: 'trend-list' }, data.trend.map(point => el('li', { textContent: fill(copy.trend_point, point) }))),
    ]);
    afterMount.push(() => drawTrend(canvas, data.trend, tokens));

    const note = el('textarea', { className: 'control', id: 'decision-note', name: 'note', rows: '4', disabled: locked });
    note.value = model.decision.note;
    const decisionError = errorFor('decision-first');
    const radios = data.decisions.map((decision, index) => {
      const input = el('input', {
        type: 'radio', name: 'decision', value: decision.key, id: index === 0 ? 'decision-first' : `decision-${decision.key}`,
        checked: model.decision.choice === decision.key, disabled: locked,
        'aria-invalid': decisionError ? 'true' : null,
        'aria-describedby': decisionError ? 'decision-error' : null,
      });
      return el('div', { className: 'radio-option' }, [input, el('label', { for: input.id, textContent: decision.label })]);
    });

    const form = el('form', {
      className: 'decision-form', novalidate: true,
      onsubmit(event) {
        event.preventDefault();
        const chosen = form.querySelector('input[name="decision"]:checked');
        model.decision = { choice: chosen ? chosen.value : '', note: note.value };
        const outcome = decisionErrors().length ? 'invalid' : 'valid';
        const target = g.follow(state, 'submit-decision', outcome);
        if (target) go(target, outcome === 'invalid' ? 'error-summary' : 'decision-status');
      },
    }, [
      errors.length ? el('div', { className: 'error-summary', id: 'error-summary', tabindex: '-1', role: 'alert' }, [
        el('h4', { className: 'error-summary-title', textContent: copy.error_summary }),
        el('ul', {}, errors.map(error => el('li', {}, [el('button', {
          className: 'link-button', type: 'button', textContent: error.message,
          onclick: () => document.getElementById(error.field)?.focus(),
        })]))),
      ]) : null,
      el('fieldset', { className: 'radio-group', disabled: locked }, [
        el('legend', { textContent: copy.decision_legend }),
        ...radios,
        decisionError && el('p', { className: 'field-error', id: 'decision-error', textContent: decisionError }),
      ]),
      field({ id: 'decision-note', label: copy.note_label, hint: copy.note_hint, error: errorFor('decision-note'), control: note }),
      el('div', {}, [el('button', {
        className: 'button button-primary', type: 'submit', disabled: locked, textContent: copy.decision_submit,
      })]),
    ]);

    const decision = decisionOf.get(model.decision.choice);
    const recorded = locked && decision ? el('div', {
      className: 'notice', 'data-tone': state.tone, id: 'decision-status', role: 'status', tabindex: '-1',
    }, [el('p', { className: 'notice-detail', textContent: fill(copy.recorded, { decision: decision.label, code: pkg.code }) })]) : null;

    const decisionCard = el('section', { className: 'card', 'aria-labelledby': 'decision-title' }, [
      el('h3', { className: 'card-title', id: 'decision-title', textContent: copy.decision_heading }),
      recorded,
      form,
    ]);

    return [el('div', { className: 'review-grid' }, [
      el('div', {}, [head, gates, evidence]),
      el('div', {}, [decisionCard, trend]),
    ])];
  }

  let pendingMedia = [];
  let afterMount = [];

  function render() {
    const route = resolveRoute();
    if (!route) {
      history.replaceState(null, '', hrefFor(initialOf(queueScreen), data.default_package));
      fromAction = false;
      return render();
    }
    if (!fromAction || !model) model = freshModel(route.state, route.packageKey);
    fromAction = false;
    const { screen, state } = route;
    pendingMedia = [];
    afterMount = [];

    const content = screen.layout === 'queue' ? renderQueue(state) : renderReview(state);
    const reviewHref = hrefFor(initialOf(reviewScreen), model.packageKey);
    const main = el('main', {
      id: 'workspace-main', className: 'screen', tabindex: '-1',
      'data-screen-route': screen.route, 'data-state-route': state.route, 'data-state-kind': state.kind,
    }, [el('h2', { className: 'screen-title', id: 'screen-title', tabindex: '-1', textContent: screen.title }), ...content]);

    const shell = el('div', { className: 'shell' }, [
      el('a', {
        className: 'skip-link', href: '#workspace-main', textContent: copy.skip_link,
        onclick(event) {
          event.preventDefault();
          main.focus();
        },
      }),
      el('header', { className: 'app-bar' }, [
        el('div', {}, [
          el('p', { className: 'app-eyebrow', textContent: copy.eyebrow }),
          el('h1', { className: 'app-title', textContent: copy.app_title }),
          el('p', { className: 'app-summary', textContent: copy.app_summary }),
        ]),
        el('nav', { className: 'app-nav', 'aria-label': copy.nav_label }, [el('ul', {}, [
          el('li', {}, [el('a', { href: hrefFor(initialOf(queueScreen)), 'aria-current': screen === queueScreen ? 'page' : null, textContent: copy.nav_queue })]),
          el('li', {}, [el('a', { href: reviewHref, 'aria-current': screen === reviewScreen ? 'page' : null, textContent: copy.nav_review })]),
        ])]),
      ]),
      main,
    ]);

    document.title = `${state.title} · ${screen.title} · ${copy.app_title}`;
    root.replaceChildren(shell);
    for (const callback of afterMount) callback();
    if (pendingFocus) document.getElementById(pendingFocus)?.focus();
    pendingFocus = null;
    Promise.all(pendingMedia).then(() => main.setAttribute('data-ready', 'true'));
  }

  window.addEventListener('hashchange', render);
  render();
}

mount();
