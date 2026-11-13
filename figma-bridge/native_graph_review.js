const GRAPH_REVIEW_OWNER = 'figma-flow-graph-review-v1';
const GRAPH_REVIEW_OWNER_KEY = 'figmaFlow.graphReview.owner';
const GRAPH_REVIEW_ID_KEY = 'figmaFlow.graphReview.id';
const GRAPH_REVIEW_DIGEST_KEY = 'figmaFlow.graphReview.digest';
const GRAPH_REVIEW_SOURCE_KEY = 'figmaFlow.graphReview.sourceSha256';
const GRAPH_REVIEW_NODE_KEY = 'figmaFlow.graphReview.nodeId';
const GRAPH_REVIEW_EDGE_KEY = 'figmaFlow.graphReview.edge';
const GRAPH_REVIEW_SCENE_KEY = 'figmaFlow.graphReview.sceneSignature';
const GRAPH_REVIEW_COLORS = {
  requirement: {accent:{r:0.31,g:0.52,b:0.91}, fill:{r:0.93,g:0.96,b:1}},
  screen: {accent:{r:0.18,g:0.65,b:0.56}, fill:{r:0.9,g:0.98,b:0.96}},
  component: {accent:{r:0.72,g:0.48,b:0.9}, fill:{r:0.97,g:0.93,b:1}},
  evidence: {accent:{r:0.9,g:0.57,b:0.2}, fill:{r:1,g:0.96,b:0.89}},
};

function graphReviewStable(value) {
  if (Array.isArray(value)) return '[' + value.map(graphReviewStable).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + graphReviewStable(value[key])).join(',') + '}';
  return JSON.stringify(value);
}

function graphReviewDigest(value) {
  let hash = 2166136261;
  for (const char of graphReviewStable(value)) {
    hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  }
  return ('00000000' + (hash >>> 0).toString(16)).slice(-8);
}

function graphReviewSceneDigest(value) {
  let left = 2166136261, right = 2246822519;
  for (const char of graphReviewStable(value)) {
    left = Math.imul(left ^ char.charCodeAt(0), 16777619);
    right = Math.imul(right ^ char.charCodeAt(0), 3266489917);
  }
  return ('00000000' + (left >>> 0).toString(16)).slice(-8) + ('00000000' + (right >>> 0).toString(16)).slice(-8);
}

function graphReviewValidate(plan) {
  const review = plan?.graph_review;
  if (!review || typeof review.source_graph_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(review.source_graph_sha256)) throw Error('Pinned graph review digest required');
  const graph = review.projection;
  if (!graph || typeof graph.id !== 'string' || typeof graph.title !== 'string' || !Array.isArray(graph.nodes) || !graph.nodes.length || graph.nodes.length > 24 || !Array.isArray(graph.edges) || graph.edges.length > 48) throw Error('Bounded graph review projection required');
  const ids = new Set();
  for (const node of graph.nodes) {
    if (!node || typeof node.id !== 'string' || !node.id || ids.has(node.id) || !Object.hasOwn(GRAPH_REVIEW_COLORS, node.kind) || typeof node.title !== 'string' || typeof node.detail !== 'string' || typeof node.status !== 'string') throw Error('Invalid graph review node');
    ids.add(node.id);
  }
  for (const edge of graph.edges) if (!edge || !ids.has(edge.from) || !ids.has(edge.to) || typeof edge.type !== 'string' || !edge.type) throw Error('Graph review relationship must connect selected nodes');
  return graph;
}

function graphReviewMatches(page, graphId) {
  return page.children.filter(node => node.getPluginData(GRAPH_REVIEW_OWNER_KEY) === GRAPH_REVIEW_OWNER && node.getPluginData(GRAPH_REVIEW_ID_KEY) === graphId);
}

function graphReviewScene(node) {
  const paints = value => Array.isArray(value) ? value.map(paint => ({type:paint.type, visible:paint.visible, opacity:paint.opacity, color:paint.color})) : [];
  return {type:node.type,name:node.name,x:node.x,y:node.y,width:node.width,height:node.height,visible:node.visible,
    characters:node.type==='TEXT'?node.characters:undefined,fills:paints(node.fills),strokes:paints(node.strokes),strokeWeight:node.strokeWeight,
    children:Array.isArray(node.children)?node.children.map(graphReviewScene):[]};
}

function graphReviewIntegrity(board) {
  let expectedNodes, expectedEdges;
  try {
    expectedNodes = JSON.parse(board.getPluginData('figmaFlow.graphReview.nodeIds'));
    expectedEdges = JSON.parse(board.getPluginData('figmaFlow.graphReview.edges'));
  } catch (_) { return false; }
  if (!Array.isArray(expectedNodes) || !Array.isArray(expectedEdges)) return false;
  const actualNodes = board.findAll(node => Boolean(node.getPluginData(GRAPH_REVIEW_NODE_KEY))).map(node => node.getPluginData(GRAPH_REVIEW_NODE_KEY)).sort();
  const actualEdges = board.findAll(node => Boolean(node.getPluginData(GRAPH_REVIEW_EDGE_KEY))).map(node => {
    try { return JSON.parse(node.getPluginData(GRAPH_REVIEW_EDGE_KEY)); } catch (_) { return null; }
  });
  return graphReviewStable(actualNodes) === graphReviewStable([...expectedNodes].sort())
    && graphReviewStable(actualEdges) === graphReviewStable(expectedEdges)
    && (!board.getPluginData(GRAPH_REVIEW_SCENE_KEY)
      || board.getPluginData(GRAPH_REVIEW_SCENE_KEY) === graphReviewSceneDigest(graphReviewScene(board)));
}

function graphReviewRead(figma, plan) {
  graphReviewScope(figma, plan);
  const graph = graphReviewValidate(plan);
  const digest = graphReviewDigest({source:plan.graph_review.source_graph_sha256, projection:graph});
  const matches = graphReviewMatches(figma.currentPage, graph.id);
  if (matches.length > 1) throw Error('Multiple owned graph review boards share this graph ID; manual reconciliation required');
  if (!matches.length) return {schema:'figma-flow-graph-review-v1', status:'absent', graph_id:graph.id, source_graph_sha256:plan.graph_review.source_graph_sha256, projection_digest:digest};
  const board = matches[0];
  const intact = graphReviewIntegrity(board);
  return {schema:'figma-flow-graph-review-v1', status:!intact ? 'integrity-conflict' : board.getPluginData(GRAPH_REVIEW_DIGEST_KEY) === digest ? 'current' : 'stale', graph_id:graph.id, board_id:board.id,
    source_graph_sha256:board.getPluginData(GRAPH_REVIEW_SOURCE_KEY), projection_digest:board.getPluginData(GRAPH_REVIEW_DIGEST_KEY), node_count:Number(board.getPluginData('figmaFlow.graphReview.nodeCount')||0), edge_count:Number(board.getPluginData('figmaFlow.graphReview.edgeCount')||0)};
}

function graphReviewScope(figma, plan) {
  if (figma.fileKey !== plan.file_key || figma.currentPage?.id !== plan.page_id) throw Error('Wrong native graph review file or page');
}

function graphReviewSetFill(node, color) {
  node.fills = [{type:'SOLID', color, opacity:1}];
}

async function graphReviewFont(figma) {
  const fonts = await figma.listAvailableFontsAsync();
  const preferred = ['Inter', 'Arial', 'Roboto'];
  const fontName = preferred.map(family => fonts.find(item => item.fontName?.family === family && item.fontName?.style === 'Regular')?.fontName).find(Boolean) || fonts[0]?.fontName;
  if (!fontName) throw Error('No available font for graph review board');
  await figma.loadFontAsync(fontName);
  return fontName;
}

function graphReviewText(figma, parent, name, text, fontName, x, y, width, size, color) {
  const node = figma.createText();
  node.name = name;
  node.fontName = fontName;
  node.fontSize = size;
  node.characters = String(text).slice(0, 1000);
  node.fills = [{type:'SOLID', color, opacity:1}];
  node.resize(width, Math.max(18, size * 1.5));
  parent.appendChild(node);
  node.x = x; node.y = y;
  return node;
}

function graphReviewFrame(figma, name, x, y, width, height, fill) {
  const node = figma.createFrame();
  node.name = name; node.x = x; node.y = y; node.resize(width, height);
  node.cornerRadius = 12; node.fills = [{type:'SOLID', color:fill, opacity:1}];
  node.clipsContent = true;
  return node;
}

function graphReviewCardMaster(figma, board, kind, fontName, x, y) {
  const colors = GRAPH_REVIEW_COLORS[kind];
  const main = figma.createComponent();
  main.name = 'Reusable card · ' + kind;
  main.resize(236, 106); main.cornerRadius = 10;
  main.fills = [{type:'SOLID', color:colors.fill, opacity:1}];
  main.strokes = [{type:'SOLID', color:colors.accent, opacity:1}];
  main.strokeWeight = 1;
  const marker = graphReviewFrame(figma, 'Accent', 0, 0, 5, 106, colors.accent); main.appendChild(marker);
  graphReviewText(figma, main, 'Kind', kind.toUpperCase(), fontName, 15, 10, 200, 9, colors.accent);
  graphReviewText(figma, main, 'Title', 'Reusable ' + kind + ' node', fontName, 15, 28, 205, 14, {r:0.1,g:0.12,b:0.17});
  graphReviewText(figma, main, 'Status', 'status', fontName, 15, 51, 205, 10, colors.accent);
  graphReviewText(figma, main, 'Detail', 'Source-backed graph node', fontName, 15, 70, 205, 9, {r:0.32,g:0.35,b:0.4});
  board.appendChild(main);
  main.x = x; main.y = y;
  return main;
}

function graphReviewInstance(main, row, fontName, parent, x, y) {
  const instance = main.createInstance();
  instance.name = row.id + ' · ' + row.title.slice(0, 70);
  instance.setPluginData(GRAPH_REVIEW_NODE_KEY, row.id);
  parent.appendChild(instance);
  instance.x = x; instance.y = y;
  const text = instance.findAll(node => node.type === 'TEXT');
  const set = (name, value) => { const target = text.find(node => node.name === name); if (!target) throw Error('Graph review card template is incomplete'); target.fontName = fontName; target.characters = value.slice(0, 400); };
  set('Kind', row.type.toUpperCase()); set('Title', row.title); set('Status', row.status); set('Detail', row.detail || 'No detail recorded.');
  return instance;
}

function graphReviewStatusSummary(nodes) {
  const counts = {};
  for (const node of nodes) counts[node.status] = (counts[node.status] || 0) + 1;
  return Object.keys(counts).sort().map(key => key + ' ' + counts[key]).join('  ·  ') || 'No status data';
}

function graphReviewPosition(figma, page, width, height) {
  const right = page.children.reduce((max, node) => Math.max(max, node.x + node.width), 0);
  const centerY = Number.isFinite(figma.viewport?.center?.y) ? figma.viewport.center.y : 400;
  return {x:Math.max(80, right + 160), y:Math.max(80, Math.round((centerY - height / 2) / 20) * 20)};
}

function graphReviewRemove(node) {
  if (!node || node.removed) return;
  node.remove();
}

async function graphReviewApply(figma, plan) {
  graphReviewScope(figma, plan);
  const graph = graphReviewValidate(plan);
  const projectionDigest = graphReviewDigest({source:plan.graph_review.source_graph_sha256, projection:graph});
  const found = graphReviewMatches(figma.currentPage, graph.id);
  const previous = found[0];
  if (found.length > 1) throw Error('Multiple owned graph review boards share this graph ID; manual reconciliation required');
  if (found.length === 1 && !graphReviewIntegrity(found[0])) throw Error('Existing graph review board content changed; manual reconciliation required');
  if (found.length === 1 && found[0].getPluginData(GRAPH_REVIEW_DIGEST_KEY) === projectionDigest) {
    figma.viewport.scrollAndZoomIntoView([found[0]]);
    return {...graphReviewRead(figma, plan), operation:'apply', unchanged:true};
  }
  const columns = ['requirement','screen','component','evidence'];
  const laneRows = Object.fromEntries(columns.map(kind => [kind, graph.nodes.filter(node => node.kind === kind)]));
  const maxRows = Math.max(...Object.values(laneRows).map(rows => rows.length), 1);
  const boardWidth = 4 * 268 + 48;
  const laneY = 172, laneHeight = Math.max(170, maxRows * 132 + 42);
  const relationshipY = laneY + laneHeight + 18;
  const relationHeight = Math.max(92, graph.edges.length * 30 + 54);
  const boardHeight = relationshipY + relationHeight + 30;
  let stage;
  try {
    graphReviewScope(figma, plan);
    const fontName = await graphReviewFont(figma);
    graphReviewScope(figma, plan);
    stage = graphReviewFrame(figma, 'Figma Flow · Graph Review · ' + graph.id, 0, 0, boardWidth, boardHeight, {r:0.97,g:0.98,b:0.99});
    stage.setPluginData(GRAPH_REVIEW_OWNER_KEY, GRAPH_REVIEW_OWNER);
    stage.setPluginData(GRAPH_REVIEW_ID_KEY, graph.id);
    stage.setPluginData(GRAPH_REVIEW_DIGEST_KEY, projectionDigest);
    stage.setPluginData(GRAPH_REVIEW_SOURCE_KEY, plan.graph_review.source_graph_sha256);
    stage.setPluginData('figmaFlow.graphReview.nodeCount', String(graph.nodes.length));
    stage.setPluginData('figmaFlow.graphReview.edgeCount', String(graph.edges.length));
    stage.setPluginData('figmaFlow.graphReview.nodeIds', JSON.stringify(graph.nodes.map(node => node.id).sort()));
    stage.setPluginData('figmaFlow.graphReview.edges', graphReviewStable(graph.edges));
    stage.visible = false;
    figma.currentPage.appendChild(stage);
    graphReviewText(figma, stage, 'Board title', graph.title, fontName, 24, 20, boardWidth - 48, 22, {r:0.09,g:0.11,b:0.15});
    graphReviewText(figma, stage, 'Graph identity', 'GRAPH ' + graph.id + '   ·   SOURCE ' + plan.graph_review.source_graph_sha256.slice(0, 16), fontName, 24, 55, boardWidth - 48, 10, {r:0.34,g:0.38,b:0.44});
    graphReviewText(figma, stage, 'Summary', graph.nodes.length + ' nodes   ·   ' + graph.edges.length + ' direct relationships   ·   ' + graphReviewStatusSummary(graph.nodes), fontName, 24, 78, boardWidth - 48, 11, {r:0.2,g:0.24,b:0.3});

    const templates = graphReviewFrame(figma, 'Reusable graph node components', 20, 110, boardWidth - 40, 50, {r:0.93,g:0.94,b:0.96});
    stage.appendChild(templates);
    const masters = {};
    columns.forEach((kind, index) => { masters[kind] = graphReviewCardMaster(figma, templates, kind, fontName, 10 + index * 250, 8); });

    const locations = new Map();
    columns.forEach((kind, index) => {
      const laneX = 20 + index * 268;
      const lane = graphReviewFrame(figma, 'Group · ' + kind + ' (' + laneRows[kind].length + ')', 0, 0, 252, laneHeight, {r:0.93,g:0.94,b:0.96});
      stage.appendChild(lane);
      lane.x = laneX; lane.y = laneY;
      graphReviewText(figma, lane, 'Group label', kind.toUpperCase(), fontName, 12, 10, 228, 11, GRAPH_REVIEW_COLORS[kind].accent);
      laneRows[kind].forEach((row, rowIndex) => {
        const x = 8, y = 32 + rowIndex * 132;
        graphReviewInstance(masters[kind], row, fontName, lane, x, y);
        locations.set(row.id, {kind, row:rowIndex});
      });
    });

    const relations = graphReviewFrame(figma, 'Direct relationships (' + graph.edges.length + ')', 20, relationshipY, boardWidth - 40, relationHeight, {r:0.93,g:0.94,b:0.96});
    stage.appendChild(relations);
    graphReviewText(figma, relations, 'Relationships heading', 'DIRECT RELATIONSHIPS', fontName, 12, 10, boardWidth - 64, 11, {r:0.25,g:0.28,b:0.33});
    const byId = new Map(graph.nodes.map(node => [node.id,node]));
    graph.edges.forEach((edge, index) => {
      const row = graphReviewFrame(figma, 'Link · ' + edge.from + ' → ' + edge.type + ' → ' + edge.to, 0, 0, boardWidth - 64, 26, {r:1,g:1,b:1});
      row.setPluginData(GRAPH_REVIEW_EDGE_KEY, JSON.stringify(edge));
      relations.appendChild(row);
      row.x = 12; row.y = 34 + index * 30;
      const from = byId.get(edge.from), to = byId.get(edge.to);
      graphReviewText(figma, row, 'Relationship label', from.title.slice(0, 72) + '  →  ' + edge.type + '  →  ' + to.title.slice(0, 72), fontName, 8, 4, boardWidth - 84, 9, {r:0.13,g:0.16,b:0.21});
    });
    graphReviewScope(figma, plan);
    stage.visible = true;
  } catch (error) {
    try { graphReviewRemove(stage); } catch (cleanup) { error.rollback_conflicts = [String(cleanup.message || cleanup)]; }
    throw error;
  }
  const position = previous ? {x:previous.x,y:previous.y} : graphReviewPosition(figma, figma.currentPage, stage.width, stage.height);
  stage.x = position.x; stage.y = position.y;
  stage.setPluginData(GRAPH_REVIEW_SCENE_KEY, graphReviewSceneDigest(graphReviewScene(stage)));
  try { figma.viewport.scrollAndZoomIntoView([stage]); }
  catch (error) {
    try { graphReviewRemove(stage); } catch (cleanup) { error.rollback_conflicts = [String(cleanup.message || cleanup)]; }
    throw error;
  }
  if (previous) {
    try { graphReviewRemove(previous); }
    catch (error) {
      try { graphReviewRemove(stage); } catch (cleanup) { error.rollback_conflicts = [String(cleanup.message || cleanup)]; }
      throw error;
    }
  }
  return {schema:'figma-flow-graph-review-v1', status:'created', operation:'apply', unchanged:false, graph_id:graph.id,
    board_id:stage.id, source_graph_sha256:plan.graph_review.source_graph_sha256, projection_digest:projectionDigest,
    node_count:graph.nodes.length, edge_count:graph.edges.length, position};
}
