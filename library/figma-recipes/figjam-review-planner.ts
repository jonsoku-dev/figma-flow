type ReviewGraph = typeof FLOW_REVIEW_GRAPH;
type ReviewNode = ReviewGraph['nodes'][number];
type ReviewEdge = ReviewGraph['edges'][number];

const RECIPE_ID = 'figjam-review-planner';
const MARKER_KEY = 'figmaFlowRecipe';
const GRAPH_ID_KEY = 'figmaFlowGraphId';
const GRAPH_HASH_KEY = 'figmaFlowGraphSha256';
const SELECTION_HASH_KEY = 'figmaFlowSelectionSha256';
const SEMANTIC_ID_KEY = 'figmaFlowSemanticId';
const MAX_NODES = 24;
const MAX_EDGES = 48;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

type ReviewIdentity = { graphId: string; graphSha256: string; selectionSha256: string };

function validateReviewGraph(graph: ReviewGraph, identity: ReviewIdentity): void {
  if (typeof identity.graphSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(identity.graphSha256)) {
    throw new Error('Review graph SHA-256 must be a lowercase 64-character digest.');
  }
  if (typeof identity.selectionSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(identity.selectionSha256)) {
    throw new Error('Review selection SHA-256 must be a lowercase 64-character digest.');
  }
  if (!graph || typeof graph !== 'object' || typeof graph.id !== 'string' || !graph.id.trim()
      || graph.id.length > 180 || CONTROL_CHARS.test(graph.id)
      || typeof graph.title !== 'string' || !graph.title.trim() || graph.title.length > 512
      || CONTROL_CHARS.test(graph.title)) {
    throw new Error('Review graph must include a non-empty ID and title of at most 120 characters.');
  }
  if (!Array.isArray(graph.nodes) || graph.nodes.length < 1 || graph.nodes.length > MAX_NODES) {
    throw new Error(`Choose a review graph with 1–${MAX_NODES} nodes.`);
  }
  if (!Array.isArray(graph.edges) || graph.edges.length > MAX_EDGES) {
    throw new Error(`Choose a review graph with at most ${MAX_EDGES} visible edges.`);
  }
  const nodeIds = new Set<string>();
  for (const node of graph.nodes) {
    if (!node || typeof node.id !== 'string' || !node.id.trim() || node.id.length > 256
        || CONTROL_CHARS.test(node.id) || nodeIds.has(node.id)
        || !['requirement', 'screen', 'component', 'evidence'].includes(node.kind)
        || typeof node.title !== 'string' || !node.title.trim() || node.title.length > 512
        || CONTROL_CHARS.test(node.title) || typeof node.detail !== 'string' || node.detail.length > 4000
        || CONTROL_CHARS.test(node.detail) || typeof node.status !== 'string' || !node.status.trim()
        || CONTROL_CHARS.test(node.status)) {
      throw new Error('Review graph contains an invalid or duplicate node.');
    }
    nodeIds.add(node.id);
  }
  const edgeIds = new Set<string>();
  for (const edge of graph.edges) {
    if (!edge || !nodeIds.has(edge.from) || !nodeIds.has(edge.to)
        || typeof edge.type !== 'string' || !edge.type.trim() || edge.type.length > 128
        || CONTROL_CHARS.test(edge.type)) {
      throw new Error('Review graph contains an invalid edge reference or label.');
    }
    const edgeId = JSON.stringify([edge.from, edge.to, edge.type]);
    if (edgeIds.has(edgeId)) throw new Error('Review graph contains a duplicate semantic edge.');
    edgeIds.add(edgeId);
  }
}

function edgeSemanticId(edge: ReviewEdge): string {
  return 'edge:' + JSON.stringify([edge.from, edge.to, edge.type]);
}

function displayText(value: string, limit: number): string {
  return value.length <= limit ? value : value.slice(0, limit - 1) + '…';
}

function authoredNode(
  create: () => SceneNode,
  semanticId: string,
  identity: ReviewIdentity,
  name: string,
): SceneNode {
  const node = create();
  node.name = name;
  node.setPluginData(MARKER_KEY, RECIPE_ID);
  node.setPluginData(GRAPH_ID_KEY, identity.graphId);
  node.setPluginData(GRAPH_HASH_KEY, identity.graphSha256);
  node.setPluginData(SELECTION_HASH_KEY, identity.selectionSha256);
  node.setPluginData(SEMANTIC_ID_KEY, semanticId);
  return node;
}

function expectedSemanticIds(graph: ReviewGraph): Set<string> {
  return new Set([
    'meta:title', 'meta:table', 'meta:evidence',
    ...graph.nodes.map(node => 'node:' + node.id),
    ...graph.edges.map(edgeSemanticId),
  ]);
}

function expectedNodeTypes(graph: ReviewGraph): Map<string, SceneNode['type']> {
  return new Map([
    ['meta:title', 'STICKY'], ['meta:table', 'TABLE'], ['meta:evidence', 'CODE_BLOCK'],
    ...graph.nodes.map(item => ['node:' + item.id, 'STICKY'] as const),
    ...graph.edges.map(edge => [edgeSemanticId(edge), 'CONNECTOR'] as const),
  ]);
}

function findExistingBoard(page: PageNode, identity: ReviewIdentity, graph: ReviewGraph): SceneNode[] | null {
  const sourceMatches = page.children.filter(node => node.getPluginData(MARKER_KEY) === RECIPE_ID
    && node.getPluginData(GRAPH_ID_KEY) === identity.graphId
    && node.getPluginData(GRAPH_HASH_KEY) === identity.graphSha256);
  const matches = sourceMatches.filter(node => node.getPluginData(SELECTION_HASH_KEY) === identity.selectionSha256);
  const expected = expectedSemanticIds(graph);
  if (matches.length === 0) {
    const otherSelections = new Map<string, SceneNode[]>();
    for (const node of sourceMatches) {
      const selectionSha256 = node.getPluginData(SELECTION_HASH_KEY);
      otherSelections.set(selectionSha256, [...(otherSelections.get(selectionSha256) ?? []), node]);
    }
    const sameSelectionContent = [...otherSelections.entries()].some(([selectionSha256, nodes]) => {
      const semanticIds = nodes.map(node => node.getPluginData(SEMANTIC_ID_KEY));
      return selectionSha256 !== identity.selectionSha256
        && nodes.length === expected.size
        && new Set(semanticIds).size === expected.size
        && semanticIds.every(id => expected.has(id));
    });
    if (sameSelectionContent) throw new Error('A board with matching node and edge IDs has conflicting selection identity; inspect it before rerunning.');
    return null;
  }
  const semanticIds = matches.map(node => node.getPluginData(SEMANTIC_ID_KEY));
  const expectedTypes = expectedNodeTypes(graph);
  const complete = matches.length === expected.size
    && new Set(semanticIds).size === expected.size
    && semanticIds.every(id => expected.has(id))
    && matches.every(node => expectedTypes.get(node.getPluginData(SEMANTIC_ID_KEY)) === node.type);
  if (!complete) throw new Error('A partial board for this graph revision exists; inspect it before rerunning.');
  return matches;
}

function matchesIdentity(node: SceneNode, identity: ReviewIdentity): boolean {
  return node.getPluginData(MARKER_KEY) === RECIPE_ID
    && node.getPluginData(GRAPH_ID_KEY) === identity.graphId
    && node.getPluginData(GRAPH_HASH_KEY) === identity.graphSha256
    && node.getPluginData(SELECTION_HASH_KEY) === identity.selectionSha256;
}

function expectedTableRows(graph: ReviewGraph): string[][] {
  return [
    ['Kind · status', 'Semantic ID', 'Node title', 'Designer ↔ developer note'],
    ...graph.nodes.map(item => [item.kind + ' · ' + item.status, displayText(item.id, 160),
      displayText(item.title, 160), displayText(item.detail, 280)]),
  ];
}

function expectedEvidenceCode(graph: ReviewGraph, graphSha256: string): string {
  return JSON.stringify({
    recipe: RECIPE_ID,
    graphId: graph.id,
    graphSha256,
    nodes: graph.nodes.map(item => ({ id: item.id, kind: item.kind, type: item.type, status: item.status, title: item.title })),
    semanticEdges: graph.edges.map(edge => ({ id: edgeSemanticId(edge), from: edge.from, to: edge.to, type: edge.type })),
  }, null, 2);
}

function legacyBoardContentMatches(nodes: SceneNode[], graph: ReviewGraph, identity: ReviewIdentity): boolean {
  const bySemanticId = new Map(nodes.map(node => [node.getPluginData(SEMANTIC_ID_KEY), node]));
  const title = bySemanticId.get('meta:title');
  const table = bySemanticId.get('meta:table');
  const evidence = bySemanticId.get('meta:evidence');
  if (title?.type !== 'STICKY' || table?.type !== 'TABLE' || evidence?.type !== 'CODE_BLOCK') return false;
  if (title.text.characters !== `Review planner · ${displayText(graph.title, 120)}\nGraph ${graph.id} · SHA-256 ${identity.graphSha256}`) return false;

  for (const item of graph.nodes) {
    const sticky = bySemanticId.get('node:' + item.id);
    if (sticky?.type !== 'STICKY') return false;
    const expectedText = `${item.kind.toUpperCase()} · ${item.status}\n${displayText(item.title, 120)}\n${displayText(item.detail, 320)}\nID: ${displayText(item.id, 128)}`;
    if (sticky.text.characters !== expectedText) return false;
  }

  const rows = expectedTableRows(graph);
  for (let row = 0; row < rows.length; row++) {
    for (let column = 0; column < rows[row].length; column++) {
      if (table.cellAt(row, column).text.characters !== rows[row][column]) return false;
    }
  }
  if (evidence.code !== expectedEvidenceCode(graph, identity.graphSha256)) return false;

  for (const edge of graph.edges) {
    const connector = bySemanticId.get(edgeSemanticId(edge));
    const from = bySemanticId.get('node:' + edge.from);
    const to = bySemanticId.get('node:' + edge.to);
    if (connector?.type !== 'CONNECTOR' || from?.type !== 'STICKY' || to?.type !== 'STICKY'
        || !('endpointNodeId' in connector.connectorStart) || !('endpointNodeId' in connector.connectorEnd)
        || connector.connectorStart.endpointNodeId !== from.id || connector.connectorEnd.endpointNodeId !== to.id
        || connector.text.characters !== displayText(edge.type, 80)) return false;
  }
  return true;
}

function migrateLegacyBoard(nodes: SceneNode[], identity: ReviewIdentity): void {
  const writes: Array<{ node: SceneNode; key: string; previous: string }> = [];
  try {
    for (const node of nodes) {
      for (const [key, value] of [[GRAPH_ID_KEY, identity.graphId], [SELECTION_HASH_KEY, identity.selectionSha256]]) {
        const previous = node.getPluginData(key);
        writes.push({ node, key, previous });
        node.setPluginData(key, value);
      }
    }
  } catch (error: unknown) {
    const failed: string[] = [];
    for (const write of writes.reverse()) {
      try { write.node.setPluginData(write.key, write.previous); }
      catch { failed.push(write.node.id + ':' + write.key); }
    }
    if (failed.length) throw new Error(`${String(error)}; legacy marker rollback failed for ${failed.join(', ')}.`);
    throw error;
  }
}

function findLegacyBoard(page: PageNode, identity: ReviewIdentity, graph: ReviewGraph): SceneNode[] | null {
  const legacy = page.children.filter(node => node.getPluginData(MARKER_KEY) === RECIPE_ID
    && node.getPluginData(GRAPH_HASH_KEY) === identity.graphSha256
    && !node.getPluginData(GRAPH_ID_KEY) && !node.getPluginData(SELECTION_HASH_KEY));
  if (!legacy.length) return null;

  const expected = expectedSemanticIds(graph);
  const semanticIds = legacy.map(node => node.getPluginData(SEMANTIC_ID_KEY));
  const counts = new Map<string, number>();
  for (const id of semanticIds) counts.set(id, (counts.get(id) ?? 0) + 1);
  const exactSelection = [...expected].every(id => counts.has(id))
    && semanticIds.every(id => expected.has(id));
  if (!exactSelection) return null;
  if (legacy.length !== expected.size || [...expected].some(id => counts.get(id) !== 1)) {
    throw new Error('Legacy board markers are ambiguous for this graph selection; inspect them before rerunning.');
  }
  const expectedTypes = expectedNodeTypes(graph);
  if (legacy.some(node => expectedTypes.get(node.getPluginData(SEMANTIC_ID_KEY)) !== node.type)
      || !legacyBoardContentMatches(legacy, graph, identity)) {
    throw new Error('Legacy board content conflicts with this graph selection; inspect it before rerunning.');
  }
  return legacy;
}

function setStickyText(sticky: StickyNode, characters: string, font: FontName): void {
  sticky.text.fontName = font;
  sticky.text.characters = characters;
}

async function main(): Promise<void> {
  if (figma.editorType !== 'figjam' || figma.mode !== 'default') {
    figma.closePlugin('Open this recipe in FigJam in default mode.');
    return;
  }
  const graph = FLOW_REVIEW_GRAPH;
  const graphSha256 = FLOW_REVIEW_GRAPH_SHA256;
  const selectionSha256 = FLOW_REVIEW_SELECTION_SHA256;
  const identity: ReviewIdentity = { graphId: graph.id, graphSha256, selectionSha256 };
  const page = figma.currentPage;
  const originalSelection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };

  try {
    validateReviewGraph(graph, identity);
    const existing = findExistingBoard(page, identity, graph);
    if (existing) {
      page.selection = existing;
      figma.viewport.scrollAndZoomIntoView(existing);
      figma.closePlugin(`Already on this page: ${graph.title} · ${graphSha256} · ${selectionSha256} · ${graph.nodes.length} nodes / ${graph.edges.length} edges.`);
      return;
    }
    const legacy = findLegacyBoard(page, identity, graph);
    if (legacy) {
      migrateLegacyBoard(legacy, identity);
      page.selection = legacy;
      figma.viewport.scrollAndZoomIntoView(legacy);
      figma.closePlugin(`Migrated and selected the existing FigJam review for ${graph.title}.`);
      return;
    }

    const font: FontName = { family: 'Inter', style: 'Regular' };
    await figma.loadFontAsync(font);
    await figma.loadFontAsync({ family: 'Source Code Pro', style: 'Medium' });
    if (figma.currentPage.id !== page.id) throw new Error('Current page changed while preparing the board; run the recipe again.');

    const { x: centerX, y: centerY } = figma.viewport.center;
    const columns = Math.min(4, graph.nodes.length);
    const rows = Math.ceil(graph.nodes.length / columns);
    const pitchX = 340;
    const pitchY = 200;
    const boardWidth = Math.max(1000, columns * pitchX);
    const left = centerX - boardWidth / 2;
    const top = centerY - (rows * pitchY + 520) / 2;

    const title = track(authoredNode(() => figma.createSticky(), 'meta:title', identity,
      `Flow review · ${graph.title}`) as StickyNode);
    title.isWideWidth = true;
    title.x = left;
    title.y = top;
    setStickyText(title, `Review planner · ${displayText(graph.title, 120)}\nGraph ${graph.id} · SHA-256 ${graphSha256}`, font);

    const byId = new Map<string, StickyNode>();
    graph.nodes.forEach((item, index) => {
      const sticky = track(authoredNode(() => figma.createSticky(), 'node:' + item.id, identity,
        `${item.kind} · ${item.title}`) as StickyNode);
      sticky.isWideWidth = true;
      sticky.x = left + (index % columns) * pitchX;
      sticky.y = top + 200 + Math.floor(index / columns) * pitchY;
      setStickyText(sticky, `${item.kind.toUpperCase()} · ${item.status}\n${displayText(item.title, 120)}\n${displayText(item.detail, 320)}\nID: ${displayText(item.id, 128)}`, font);
      byId.set(item.id, sticky);
    });

    const table = track(authoredNode(() => figma.createTable(graph.nodes.length + 1, 4),
      'meta:table', identity, `Flow review · ${graph.title} · traceability table`) as TableNode);
    table.x = left;
    table.y = top + 220 + rows * pitchY;
    table.resizeColumn(0, 180);
    table.resizeColumn(1, 220);
    table.resizeColumn(2, 260);
    table.resizeColumn(3, Math.max(340, boardWidth - 660));
    const tableRows = expectedTableRows(graph);
    tableRows.forEach((cells, row) => cells.forEach((value, column) => {
      const cell = table.cellAt(row, column);
      cell.text.fontName = font;
      cell.text.characters = value;
    }));

    const evidence = track(authoredNode(() => figma.createCodeBlock(), 'meta:evidence', identity,
      `Flow review · ${graph.title} · graph evidence`) as CodeBlockNode);
    evidence.codeLanguage = 'JSON';
    evidence.code = JSON.stringify({
      recipe: RECIPE_ID,
      graphId: graph.id,
      graphTitle: graph.title,
      graphSha256,
      selectionSha256,
      nodes: graph.nodes.map(item => ({ id: item.id, kind: item.kind, type: item.type, status: item.status, title: item.title })),
      semanticEdges: graph.edges.map(edge => ({ id: edgeSemanticId(edge), from: edge.from, to: edge.to, type: edge.type })),
    }, null, 2);
    evidence.x = left + boardWidth + 48;
    evidence.y = table.y;

    graph.edges.forEach(edge => {
      const connector = track(authoredNode(() => figma.createConnector(), edgeSemanticId(edge), identity,
        `Flow review edge · ${edge.from} → ${edge.to}`) as ConnectorNode);
      connector.connectorLineType = 'ELBOWED';
      connector.connectorStart = { endpointNodeId: byId.get(edge.from)!.id, magnet: 'AUTO' };
      connector.connectorEnd = { endpointNodeId: byId.get(edge.to)!.id, magnet: 'AUTO' };
      connector.text.fontName = font;
      connector.text.characters = displayText(edge.type, 80);
    });

    const readback = page.children.filter(node => matchesIdentity(node, identity));
    const readbackIds = new Set(readback.map(node => node.getPluginData(SEMANTIC_ID_KEY)));
    const expected = expectedSemanticIds(graph);
    const expectedTypes = expectedNodeTypes(graph);
    if (readback.length !== expected.size || readbackIds.size !== expected.size
        || [...expected].some(id => !readbackIds.has(id))
        || readback.some(node => expectedTypes.get(node.getPluginData(SEMANTIC_ID_KEY)) !== node.type)) {
      throw new Error('Board evidence readback did not match the graph projection.');
    }
    const evidenceReadback = readback.find(node => node.getPluginData(SEMANTIC_ID_KEY) === 'meta:evidence');
    const expectedCode = evidenceReadback?.type === 'CODE_BLOCK' ? (evidenceReadback as CodeBlockNode).code : '';
    if (!expectedCode.includes(`"graphSha256": "${graphSha256}"`)
        || !expectedCode.includes(`"graphId": ${JSON.stringify(graph.id)}`)
        || !expectedCode.includes(`"selectionSha256": "${selectionSha256}"`)) {
      throw new Error('Graph identity or selection SHA-256 was missing from the evidence readback.');
    }

    page.selection = owned;
    figma.viewport.scrollAndZoomIntoView(owned);
    figma.closePlugin(`Created ${graph.title} · ${graphSha256} · ${graph.nodes.length} nodes / ${graph.edges.length} edges, with table and evidence JSON.`);
    return;
  } catch (error: unknown) {
    for (const node of [...owned].reverse()) {
      if (!node.removed) { try { node.remove(); } catch (_) {} }
    }
    if (figma.currentPage.id === page.id) page.selection = originalSelection.filter(node => !node.removed);
    const remaining = owned.filter(node => !node.removed);
    const message = String(error) + (remaining.length
      ? '; cleanup failed for ' + remaining.map(node => node.id).join(', ')
      : '');
    figma.closePlugin(message);
  }
}

main().catch((error: unknown) => figma.closePlugin(String(error)));
