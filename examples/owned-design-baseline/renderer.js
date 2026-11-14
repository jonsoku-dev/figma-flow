const SVG_NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'className') node.className = value;
    else if (key === 'textContent') node.textContent = value;
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, String(value));
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

function createChevron(isOpen) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'trigger-chevron');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('width', '16');
  svg.setAttribute('height', '16');

  const group = document.createElementNS(SVG_NS, 'g');
  if (isOpen) group.setAttribute('transform', 'rotate(180 8 8)');

  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', 'M4 6L8 10L12 6');
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', isOpen ? '#1d4ed8' : '#334155');
  path.setAttribute('stroke-width', '1.75');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');

  group.appendChild(path);
  svg.appendChild(group);
  return { svg, group, path };
}

function layerPillClass(sharingScope) {
  if (sharingScope === 'public-contract-only') return 'pill pill-contract';
  if (sharingScope === 'public') return 'pill pill-owned';
  return 'pill pill-private';
}

function requirementTraces(graph, reqId) {
  const traces = [];
  for (const edge of graph.edges) {
    if (edge.to === reqId && edge.type === 'informs') {
      traces.push(`${edge.from} -> ${edge.type}`);
    } else if (edge.from === reqId && (edge.type === 'appears on' || edge.type === 'accepted by')) {
      traces.push(`${edge.type} -> ${edge.to}`);
    }
  }
  return traces;
}

function stateRoutes(graph, byId, stateId) {
  const routes = [];
  for (const edge of graph.edges) {
    if (edge.from !== stateId || edge.type !== 'accepts input') continue;
    const action = byId.get(edge.to);
    if (!action || action.type !== 'action') continue;
    const navEdge = graph.edges.find(candidate => candidate.from === action.id && candidate.type === 'navigates to');
    const targetState = navEdge ? byId.get(navEdge.to) : null;
    if (targetState) {
      routes.push({ action, targetState });
    }
  }
  return routes;
}

function screenTraces(graph, byId, screenId) {
  const items = [];
  for (const edge of graph.edges) {
    if (edge.from === screenId && (edge.type === 'implemented by' || edge.type === 'represented by')) {
      const target = byId.get(edge.to);
      if (target) items.push({ relation: edge.type, target });
    }
  }
  for (const edge of graph.edges) {
    if (edge.type === 'checked by') {
      const source = byId.get(edge.from);
      const target = byId.get(edge.to);
      if (source && target && source.type === 'acceptance') {
        items.push({ relation: `${source.id} ${edge.type}`, target });
      }
    }
  }
  return items;
}

async function mountBaseline() {
  const [graphRes, manifestRes] = await Promise.all([
    fetch('./graph.json'),
    fetch('./manifest.json'),
  ]);
  if (!graphRes.ok || !manifestRes.ok) {
    throw new Error('Failed to load canonical graph.json or manifest.json');
  }
  const [graph, manifest] = await Promise.all([graphRes.json(), manifestRes.json()]);
  const byId = new Map(graph.nodes.map(node => [node.id, node]));
  const screenNode = graph.nodes.find(node => node.type === 'screen');
  const requirementNodes = graph.nodes.filter(node => node.type === 'requirement');
  const stateNodes = graph.nodes.filter(node => node.type === 'state');
  const initialState = stateNodes.find(node => node.initial) || stateNodes[0];

  document.title = screenNode.title;

  const root = document.getElementById('baseline-root');
  const meta = graph.workspace_meta;

  const header = el('header', { className: 'workspace-header' }, [
    el('div', { className: 'header-main' }, [
      el('div', { className: 'eyebrow-row' }, [
        el('span', { className: 'pill pill-accent', textContent: meta.eyebrow }),
        el('span', { className: 'pill', textContent: screenNode.id }),
        el('span', { className: 'pill pill-owned', textContent: manifest.ownership.license }),
      ]),
      el('h1', { className: 'workspace-title', textContent: screenNode.title }),
      el('p', { className: 'workspace-summary', textContent: meta.summary }),
    ]),
    el('div', { className: 'header-badges' }, [
      el('span', {
        className: 'pill',
        textContent: `${manifest.ownership.external_network_requests} external requests`,
      }),
      el('span', {
        className: 'pill',
        textContent: manifest.external_reference_policy.policy_id,
      }),
    ]),
  ]);

  const layerCards = Object.entries(manifest.artifact_layers).map(([layerKey, layerMeta]) => {
    const layerNodeIds = graph.nodes.filter(node => node.layer === layerKey).map(node => node.id);
    return el('article', { className: 'layer-card' }, [
      el('div', { className: 'layer-card-head' }, [
        el('h2', { className: 'layer-card-title', textContent: layerMeta.label }),
        el('span', {
          className: layerPillClass(layerMeta.sharing_scope),
          textContent: layerMeta.sharing_scope,
        }),
      ]),
      el('p', { className: 'layer-card-summary', textContent: layerMeta.summary }),
      el('div', {
        className: 'layer-card-meta',
        textContent: `${layerKey} · ${layerNodeIds.length} graph nodes`,
      }),
    ]);
  });

  const layerStrip = el('div', {
    className: 'layer-strip',
  }, layerCards);

  const activeStatePill = el('span', { className: 'pill pill-accent' });
  const accordionRoot = el('div', {
    className: 'disclosure-list',
    'data-slot': 'accordion',
  });

  const itemRefs = new Map();
  let activeStateId = initialState.id;

  function applyState(nextStateId) {
    activeStateId = nextStateId;
    const activeState = byId.get(activeStateId);
    activeStatePill.textContent = activeState.id;

    for (const req of requirementNodes) {
      const refs = itemRefs.get(req.id);
      const isOpen = activeState.expanded_requirement === req.id;
      const stateToken = isOpen ? 'open' : 'closed';
      refs.itemEl.setAttribute('data-state', stateToken);
      refs.triggerEl.setAttribute('aria-expanded', String(isOpen));
      refs.triggerEl.setAttribute('data-state', stateToken);
      refs.panelEl.setAttribute('data-state', stateToken);
      if (isOpen) {
        refs.panelEl.removeAttribute('hidden');
        refs.chevronGroup.setAttribute('transform', 'rotate(180 8 8)');
        refs.chevronPath.setAttribute('stroke', '#1d4ed8');
      } else {
        refs.panelEl.setAttribute('hidden', '');
        refs.chevronGroup.removeAttribute('transform');
        refs.chevronPath.setAttribute('stroke', '#334155');
      }
    }

    renderInspector(activeState);
  }

  requirementNodes.forEach((req, index) => {
    const triggerId = `disclosure-trigger-${index + 1}`;
    const panelId = `disclosure-panel-${index + 1}`;
    const chevron = createChevron(false);

    const triggerEl = el('button', {
      type: 'button',
      className: 'disclosure-trigger',
      'data-slot': 'accordion-trigger',
      id: triggerId,
      'aria-expanded': 'false',
      'aria-controls': panelId,
      'data-state': 'closed',
    }, [
      el('span', { className: 'trigger-label', textContent: req.title }),
      chevron.svg,
    ]);

    triggerEl.addEventListener('click', () => {
      const routes = stateRoutes(graph, byId, activeStateId);
      const matched = routes.find(route => route.action.trigger_requirement === req.id);
      if (matched) applyState(matched.targetState.id);
    });

    const checks = Array.isArray(req.handoff_checks)
      ? el('ul', { className: 'check-list' }, req.handoff_checks.map(line => el('li', { textContent: line })))
      : null;

    const traces = requirementTraces(graph, req.id);
    const panelEl = el('div', {
      className: 'disclosure-panel',
      'data-slot': 'accordion-content',
      id: panelId,
      'data-state': 'closed',
      hidden: true,
    }, [
      el('div', { className: 'disclosure-meta-row' }, [
        el('span', { className: 'pill pill-owned', textContent: req.id }),
        el('span', { className: 'pill', textContent: req.status }),
        el('span', { className: 'pill', textContent: req.source }),
      ]),
      el('p', { className: 'disclosure-detail', textContent: req.detail }),
      checks,
      el('div', { className: 'trace-pills' }, traces.map(trace => el('span', {
        className: 'pill',
        textContent: trace,
      }))),
    ]);

    const itemEl = el('div', {
      className: 'disclosure-item',
      'data-slot': 'accordion-item',
      'data-state': 'closed',
    }, [
      el('h3', { className: 'disclosure-heading' }, [triggerEl]),
      panelEl,
    ]);

    itemRefs.set(req.id, {
      itemEl,
      triggerEl,
      panelEl,
      chevronGroup: chevron.group,
      chevronPath: chevron.path,
    });
    accordionRoot.appendChild(itemEl);
  });

  const leftCard = el('section', {
    className: 'panel-card',
    'aria-labelledby': 'disclosure-heading-title',
  }, [
    el('div', { className: 'section-head' }, [
      el('h2', {
        className: 'section-title',
        id: 'disclosure-heading-title',
        textContent: meta.disclosure_heading,
      }),
      el('span', { className: 'pill', textContent: meta.disclosure_mode }),
    ]),
    accordionRoot,
  ]);

  const inspectorBody = el('div');
  const rightCard = el('aside', {
    className: 'panel-card',
    'aria-labelledby': 'inspector-heading-title',
  }, [
    el('div', { className: 'section-head' }, [
      el('h2', {
        className: 'section-title',
        id: 'inspector-heading-title',
        textContent: meta.inspector_heading,
      }),
      activeStatePill,
    ]),
    inspectorBody,
  ]);

  const fixedTraces = screenTraces(graph, byId, screenNode.id);

  function renderInspector(activeState) {
    const routes = stateRoutes(graph, byId, activeState.id);
    const expandedLabel = activeState.expanded_requirement || 'none';

    const stateBlock = el('div', { className: 'inspector-block' }, [
      el('div', { className: 'inspector-subhead' }, [
        el('span', { className: 'mono-code', textContent: activeState.id }),
        el('span', { className: 'pill', textContent: `expanded: ${expandedLabel}` }),
      ]),
      el('p', { className: 'state-title', textContent: activeState.title }),
      el('p', { className: 'state-detail', textContent: activeState.detail }),
    ]);

    const routesBlock = el('div', { className: 'inspector-block' }, [
      el('div', { className: 'inspector-subhead' }, [
        el('h3', { className: 'inspector-subtitle', textContent: meta.routes_heading }),
      ]),
      el('ul', { className: 'route-list', role: 'list' }, routes.map(({ action, targetState }) => el('li', {
        className: 'route-item',
      }, [
        el('span', {
          className: 'mono-code',
          textContent: `${action.transition_kind}: ${action.trigger_requirement}`,
        }),
        el('span', {
          textContent: `${action.id} -> ${targetState.id}`,
        }),
      ]))),
    ]);

    const traceBlock = el('div', { className: 'inspector-block' }, [
      el('div', { className: 'inspector-subhead' }, [
        el('h3', { className: 'inspector-subtitle', textContent: meta.trace_heading }),
      ]),
      el('ul', { className: 'trace-list', role: 'list' }, fixedTraces.map(({ relation, target }) => {
        const layerMeta = manifest.artifact_layers[target.layer];
        return el('li', { className: 'trace-item' }, [
          el('span', { textContent: `${relation} -> ${target.id}` }),
          el('span', {
            className: layerPillClass(layerMeta ? layerMeta.sharing_scope : 'public'),
            textContent: layerMeta ? layerMeta.sharing_scope : target.status,
          }),
        ]);
      })),
    ]);

    inspectorBody.replaceChildren(stateBlock, routesBlock, traceBlock);
  }

  const grid = el('div', { className: 'workspace-grid' }, [leftCard, rightCard]);
  root.replaceChildren(header, layerStrip, grid);
  applyState(initialState.id);
}

mountBaseline();
