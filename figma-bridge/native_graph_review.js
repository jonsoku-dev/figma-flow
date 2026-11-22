const GRAPH_REVIEW_OWNER = 'figma-flow-graph-review-v1';
const GRAPH_REVIEW_OWNER_KEY = 'figmaFlow.graphReview.owner';
const GRAPH_REVIEW_ID_KEY = 'figmaFlow.graphReview.id';
const GRAPH_REVIEW_DIGEST_KEY = 'figmaFlow.graphReview.digest';
const GRAPH_REVIEW_APPEARANCE_KEY = 'figmaFlow.graphReview.appearance';
// Boards published before appearance fingerprints used this exact visual contract.
const GRAPH_REVIEW_LEGACY_APPEARANCE = '9aa0f5bd162031929d76d5f89865c8cd1f272984c4dabe371471fa8d87570144';
const GRAPH_REVIEW_SOURCE_KEY = 'figmaFlow.graphReview.sourceSha256';
const GRAPH_REVIEW_NODE_KEY = 'figmaFlow.graphReview.nodeId';
const GRAPH_REVIEW_EDGE_KEY = 'figmaFlow.graphReview.edge';
const GRAPH_REVIEW_SCENE_KEY = 'figmaFlow.graphReview.sceneSignature';
/* native appearance: begin graphReview */
const GRAPH_BOARD = {
  "groups": {
    "requirement": {
      "accent": {
        "r": 0.31,
        "g": 0.52,
        "b": 0.91
      },
      "fill": {
        "r": 0.93,
        "g": 0.96,
        "b": 1
      }
    },
    "screen": {
      "accent": {
        "r": 0.18,
        "g": 0.65,
        "b": 0.56
      },
      "fill": {
        "r": 0.9,
        "g": 0.98,
        "b": 0.96
      }
    },
    "component": {
      "accent": {
        "r": 0.72,
        "g": 0.48,
        "b": 0.9
      },
      "fill": {
        "r": 0.97,
        "g": 0.93,
        "b": 1
      }
    },
    "evidence": {
      "accent": {
        "r": 0.9,
        "g": 0.57,
        "b": 0.2
      },
      "fill": {
        "r": 1,
        "g": 0.96,
        "b": 0.89
      }
    }
  },
  "palette": {
    "paper": {
      "r": 0.97,
      "g": 0.98,
      "b": 0.99
    },
    "surface": {
      "r": 0.93,
      "g": 0.94,
      "b": 0.96
    },
    "white": {
      "r": 1,
      "g": 1,
      "b": 1
    },
    "title": {
      "r": 0.09,
      "g": 0.11,
      "b": 0.15
    },
    "meta": {
      "r": 0.34,
      "g": 0.38,
      "b": 0.44
    },
    "summary": {
      "r": 0.2,
      "g": 0.24,
      "b": 0.3
    },
    "cardTitle": {
      "r": 0.1,
      "g": 0.12,
      "b": 0.17
    },
    "detail": {
      "r": 0.32,
      "g": 0.35,
      "b": 0.4
    },
    "heading": {
      "r": 0.25,
      "g": 0.28,
      "b": 0.33
    },
    "link": {
      "r": 0.13,
      "g": 0.16,
      "b": 0.21
    }
  },
  "card": {
    "width": 236,
    "height": 106,
    "radius": 10,
    "stroke": 1,
    "marker": 5,
    "textX": 15,
    "labels": {
      "kind": [
        10,
        200,
        9
      ],
      "title": [
        28,
        205,
        14
      ],
      "status": [
        51,
        205,
        10
      ],
      "detail": [
        70,
        205,
        9
      ]
    }
  },
  "board": {
    "radius": 12,
    "centerY": 400,
    "minOffset": 80,
    "outerGap": 160,
    "snap": 20,
    "columnPitch": 268,
    "insets": 48,
    "laneY": 172,
    "laneMinHeight": 170,
    "rowPitch": 132,
    "rowsPadding": 42,
    "gap": 18,
    "relationsMinHeight": 92,
    "relationPitch": 30,
    "relationsPadding": 54,
    "bottom": 30,
    "side": 20,
    "laneWidth": 252,
    "cellX": 8,
    "firstRowY": 32,
    "templatesY": 110,
    "templatesHeight": 50,
    "masterX": 10,
    "masterPitch": 250,
    "masterY": 8,
    "textMinHeight": 18,
    "lineHeight": 1.5,
    "labels": {
      "title": {
        "x": 24,
        "y": 20,
        "size": 22
      },
      "identity": {
        "x": 24,
        "y": 55,
        "size": 10
      },
      "summary": {
        "x": 24,
        "y": 78,
        "size": 11
      },
      "lane": {
        "x": 12,
        "y": 10,
        "width": 228,
        "size": 11
      },
      "relations": {
        "x": 12,
        "y": 10,
        "size": 11
      },
      "link": {
        "x": 8,
        "y": 4,
        "size": 9
      }
    },
    "relationRowHeight": 26,
    "relationRowsY": 34,
    "relationX": 12,
    "relationInsets": 64,
    "linkInsets": 84
  },
  "typefaces": {
    "families": [
      "Inter",
      "Arial",
      "Roboto"
    ],
    "style": "Regular"
  },
  "limits": {
    "nodes": 24,
    "edges": 48
  },
  "nodeGroups": {
    "requirement": "requirement",
    "acceptance": "requirement",
    "screen": "screen",
    "state": "screen",
    "action": "screen",
    "component": "component",
    "design-token": "component",
    "test": "evidence",
    "code": "evidence",
    "reference": "evidence",
    "figma": "evidence"
  }
};
const GRAPH_BOARD_SHA256 = "9aa0f5bd162031929d76d5f89865c8cd1f272984c4dabe371471fa8d87570144";
/* native appearance: end graphReview */
const GRAPH_REVIEW_COLORS = GRAPH_BOARD.groups;
const GR = GRAPH_BOARD.board;

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
  if (!graph || typeof graph.id !== 'string' || typeof graph.title !== 'string' || !Array.isArray(graph.nodes) || !graph.nodes.length || graph.nodes.length > GRAPH_BOARD.limits.nodes || !Array.isArray(graph.edges) || graph.edges.length > GRAPH_BOARD.limits.edges) throw Error('Bounded graph review projection required');
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

function graphReviewCurrent(board, digest) {
  return board.getPluginData(GRAPH_REVIEW_DIGEST_KEY) === digest &&
    (board.getPluginData(GRAPH_REVIEW_APPEARANCE_KEY) || GRAPH_REVIEW_LEGACY_APPEARANCE) === GRAPH_BOARD_SHA256;
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
  return {schema:'figma-flow-graph-review-v1', status:!intact ? 'integrity-conflict' : graphReviewCurrent(board, digest) ? 'current' : 'stale', graph_id:graph.id, board_id:board.id,
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
  const preferred = GRAPH_BOARD.typefaces.families;
  const fontName = preferred.map(family => fonts.find(item => item.fontName?.family === family && item.fontName?.style === GRAPH_BOARD.typefaces.style)?.fontName).find(Boolean) || fonts[0]?.fontName;
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
  node.resize(width, Math.max(GR.textMinHeight, size * GR.lineHeight));
  parent.appendChild(node);
  node.x = x; node.y = y;
  return node;
}

function graphReviewFrame(figma, name, x, y, width, height, fill) {
  const node = figma.createFrame();
  node.name = name; node.x = x; node.y = y; node.resize(width, height);
  node.cornerRadius = GR.radius; node.fills = [{type:'SOLID', color:fill, opacity:1}];
  node.clipsContent = true;
  return node;
}

function graphReviewCardMaster(figma, board, kind, fontName, x, y) {
  const colors = GRAPH_REVIEW_COLORS[kind];
  const main = figma.createComponent();
  main.name = 'Reusable card · ' + kind;
  main.resize(GRAPH_BOARD.card.width, GRAPH_BOARD.card.height); main.cornerRadius = GRAPH_BOARD.card.radius;
  main.fills = [{type:'SOLID', color:colors.fill, opacity:1}];
  main.strokes = [{type:'SOLID', color:colors.accent, opacity:1}];
  main.strokeWeight = GRAPH_BOARD.card.stroke;
  const marker = graphReviewFrame(figma, 'Accent', 0, 0, GRAPH_BOARD.card.marker, GRAPH_BOARD.card.height, colors.accent); main.appendChild(marker);
  graphReviewText(figma, main, 'Kind', kind.toUpperCase(), fontName, GRAPH_BOARD.card.textX, ...GRAPH_BOARD.card.labels.kind, colors.accent);
  graphReviewText(figma, main, 'Title', 'Reusable ' + kind + ' node', fontName, GRAPH_BOARD.card.textX, ...GRAPH_BOARD.card.labels.title, GRAPH_BOARD.palette.cardTitle);
  graphReviewText(figma, main, 'Status', 'status', fontName, GRAPH_BOARD.card.textX, ...GRAPH_BOARD.card.labels.status, colors.accent);
  graphReviewText(figma, main, 'Detail', 'Source-backed graph node', fontName, GRAPH_BOARD.card.textX, ...GRAPH_BOARD.card.labels.detail, GRAPH_BOARD.palette.detail);
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
  const centerY = Number.isFinite(figma.viewport?.center?.y) ? figma.viewport.center.y : GR.centerY;
  return {x:Math.max(GR.minOffset, right + GR.outerGap), y:Math.max(GR.minOffset, Math.round((centerY - height / 2) / GR.snap) * GR.snap)};
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
  if (found.length === 1 && graphReviewCurrent(found[0], projectionDigest)) {
    figma.viewport.scrollAndZoomIntoView([found[0]]);
    return {...graphReviewRead(figma, plan), operation:'apply', unchanged:true};
  }
  const columns = Object.keys(GRAPH_REVIEW_COLORS);
  const laneRows = Object.fromEntries(columns.map(kind => [kind, graph.nodes.filter(node => node.kind === kind)]));
  const maxRows = Math.max(...Object.values(laneRows).map(rows => rows.length), 1);
  const boardWidth = columns.length * GR.columnPitch + GR.insets;
  const laneY = GR.laneY, laneHeight = Math.max(GR.laneMinHeight, maxRows * GR.rowPitch + GR.rowsPadding);
  const relationshipY = laneY + laneHeight + GR.gap;
  const relationHeight = Math.max(GR.relationsMinHeight, graph.edges.length * GR.relationPitch + GR.relationsPadding);
  const boardHeight = relationshipY + relationHeight + GR.bottom;
  let stage;
  try {
    graphReviewScope(figma, plan);
    const fontName = await graphReviewFont(figma);
    graphReviewScope(figma, plan);
    stage = graphReviewFrame(figma, 'Figma Flow · Graph Review · ' + graph.id, 0, 0, boardWidth, boardHeight, GRAPH_BOARD.palette.paper);
    stage.setPluginData(GRAPH_REVIEW_OWNER_KEY, GRAPH_REVIEW_OWNER);
    stage.setPluginData(GRAPH_REVIEW_ID_KEY, graph.id);
    stage.setPluginData(GRAPH_REVIEW_DIGEST_KEY, projectionDigest);
    stage.setPluginData(GRAPH_REVIEW_APPEARANCE_KEY, GRAPH_BOARD_SHA256);
    stage.setPluginData(GRAPH_REVIEW_SOURCE_KEY, plan.graph_review.source_graph_sha256);
    stage.setPluginData('figmaFlow.graphReview.nodeCount', String(graph.nodes.length));
    stage.setPluginData('figmaFlow.graphReview.edgeCount', String(graph.edges.length));
    stage.setPluginData('figmaFlow.graphReview.nodeIds', JSON.stringify(graph.nodes.map(node => node.id).sort()));
    stage.setPluginData('figmaFlow.graphReview.edges', graphReviewStable(graph.edges));
    stage.visible = false;
    figma.currentPage.appendChild(stage);
    graphReviewText(figma, stage, 'Board title', graph.title, fontName, GR.labels.title.x, GR.labels.title.y, boardWidth - GR.insets, GR.labels.title.size, GRAPH_BOARD.palette.title);
    graphReviewText(figma, stage, 'Graph identity', 'GRAPH ' + graph.id + '   ·   SOURCE ' + plan.graph_review.source_graph_sha256.slice(0, 16), fontName, GR.labels.identity.x, GR.labels.identity.y, boardWidth - GR.insets, GR.labels.identity.size, GRAPH_BOARD.palette.meta);
    graphReviewText(figma, stage, 'Summary', graph.nodes.length + ' nodes   ·   ' + graph.edges.length + ' direct relationships   ·   ' + graphReviewStatusSummary(graph.nodes), fontName, GR.labels.summary.x, GR.labels.summary.y, boardWidth - GR.insets, GR.labels.summary.size, GRAPH_BOARD.palette.summary);

    const templates = graphReviewFrame(figma, 'Reusable graph node components', GR.side, GR.templatesY, boardWidth - 2 * GR.side, GR.templatesHeight, GRAPH_BOARD.palette.surface);
    stage.appendChild(templates);
    const masters = {};
    columns.forEach((kind, index) => { masters[kind] = graphReviewCardMaster(figma, templates, kind, fontName, GR.masterX + index * GR.masterPitch, GR.masterY); });

    const locations = new Map();
    columns.forEach((kind, index) => {
      const laneX = GR.side + index * GR.columnPitch;
      const lane = graphReviewFrame(figma, 'Group · ' + kind + ' (' + laneRows[kind].length + ')', 0, 0, GR.laneWidth, laneHeight, GRAPH_BOARD.palette.surface);
      stage.appendChild(lane);
      lane.x = laneX; lane.y = laneY;
      graphReviewText(figma, lane, 'Group label', kind.toUpperCase(), fontName, GR.labels.lane.x, GR.labels.lane.y, GR.labels.lane.width, GR.labels.lane.size, GRAPH_REVIEW_COLORS[kind].accent);
      laneRows[kind].forEach((row, rowIndex) => {
        const x = GR.cellX, y = GR.firstRowY + rowIndex * GR.rowPitch;
        graphReviewInstance(masters[kind], row, fontName, lane, x, y);
        locations.set(row.id, {kind, row:rowIndex});
      });
    });

    const relations = graphReviewFrame(figma, 'Direct relationships (' + graph.edges.length + ')', GR.side, relationshipY, boardWidth - 2 * GR.side, relationHeight, GRAPH_BOARD.palette.surface);
    stage.appendChild(relations);
    graphReviewText(figma, relations, 'Relationships heading', 'DIRECT RELATIONSHIPS', fontName, GR.labels.relations.x, GR.labels.relations.y, boardWidth - GR.relationInsets, GR.labels.relations.size, GRAPH_BOARD.palette.heading);
    const byId = new Map(graph.nodes.map(node => [node.id,node]));
    graph.edges.forEach((edge, index) => {
      const row = graphReviewFrame(figma, 'Link · ' + edge.from + ' → ' + edge.type + ' → ' + edge.to, 0, 0, boardWidth - GR.relationInsets, GR.relationRowHeight, GRAPH_BOARD.palette.white);
      row.setPluginData(GRAPH_REVIEW_EDGE_KEY, JSON.stringify(edge));
      relations.appendChild(row);
      row.x = GR.relationX; row.y = GR.relationRowsY + index * GR.relationPitch;
      const from = byId.get(edge.from), to = byId.get(edge.to);
      graphReviewText(figma, row, 'Relationship label', from.title.slice(0, 72) + '  →  ' + edge.type + '  →  ' + to.title.slice(0, 72), fontName, GR.labels.link.x, GR.labels.link.y, boardWidth - GR.linkInsets, GR.labels.link.size, GRAPH_BOARD.palette.link);
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
