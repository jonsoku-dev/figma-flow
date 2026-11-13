type DeckNode = typeof FLOW_REVIEW_GRAPH.nodes[number];
type DeckEdge = typeof FLOW_REVIEW_GRAPH.edges[number];
type DeckGraph = typeof FLOW_REVIEW_GRAPH;

type DeckMarker = {
  schema: 1;
  graphId: string;
  graphSha256: string;
  selectionSha256: string;
  rowIndex: number;
  slideIds: string[];
  nodeIds: string[];
  edgeIds: string[];
};

type SlideStamp = {
  schema: 1;
  graphId: string;
  graphSha256: string;
  selectionSha256: string;
  nodeIds: string[];
  edgeIds: string[];
};

type LegacyRowMarker = {
  kind: 'row-indexed' | 'aggregate';
  graphId: string;
  graphSha256: string;
  rowIndex?: number;
  slideIds: string[];
};

type LegacyDeck = { rows: SlideRowNode[]; slides: SlideNode[] };
type LegacySlideStamp = { graphId: string; graphSha256: string; nodeIds: string[] };

const MARKER_KEY = 'figmaFlowReviewDeck';
const SLIDE_MARKER_KEY = 'figmaFlowReviewSlide';
const MAX_NODES = 24;
const MAX_EDGES = 48;
const SLIDES_PER_ROW = 3;
const DARK = { r: 0.10, g: 0.14, b: 0.23 };
const MUTED = { r: 0.36, g: 0.40, b: 0.49 };
const FONT_REGULAR: FontName = { family: 'Inter', style: 'Regular' };
const FONT_BOLD: FontName = { family: 'Inter', style: 'Bold' };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isReviewKind(value: unknown): value is DeckNode['kind'] {
  switch (value) {
    case 'requirement':
    case 'screen':
    case 'component':
    case 'evidence':
      return true;
    default:
      return false;
  }
}

function parseGraph(value: unknown): DeckGraph {
  if (!isRecord(value)) throw new Error('The review graph is missing.');
  const graph = value;
  if (typeof graph.id !== 'string' || !graph.id.trim() || typeof graph.title !== 'string' || !graph.title.trim()) {
    throw new Error('The review graph needs a non-empty id and title.');
  }
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error('The review graph needs node and edge arrays.');
  if (graph.nodes.length === 0 || graph.nodes.length > MAX_NODES) {
    throw new Error(`The review graph must contain between 1 and ${MAX_NODES} nodes.`);
  }
  if (graph.edges.length > MAX_EDGES) throw new Error(`The review graph exceeds the ${MAX_EDGES}-edge limit.`);

  const nodes: DeckNode[] = [];
  const ids = new Set<string>();
  for (const item of graph.nodes) {
    if (!isRecord(item)) throw new Error('Every graph node must be an object.');
    const node = item;
    if (typeof node.id !== 'string' || !node.id.trim() || ids.has(node.id)) throw new Error('Graph node IDs must be non-empty and unique.');
    if (!isReviewKind(node.kind)) throw new Error(`Unsupported graph node kind for ${node.id}.`);
    if (typeof node.title !== 'string' || !node.title.trim() || typeof node.detail !== 'string') {
      throw new Error(`Graph node ${node.id} needs a title and detail string.`);
    }
    if (typeof node.type !== 'string' || typeof node.status !== 'string') {
      throw new Error(`Graph node ${node.id} needs its source type and status.`);
    }
    ids.add(node.id);
    nodes.push({
      id: node.id,
      kind: node.kind,
      title: node.title,
      detail: node.detail,
      type: node.type,
      status: node.status,
    });
  }

  const edges: DeckEdge[] = [];
  for (const item of graph.edges) {
    if (!isRecord(item)) throw new Error('Every graph edge must be an object.');
    const edge = item;
    if (typeof edge.from !== 'string' || typeof edge.to !== 'string' || typeof edge.type !== 'string' || !edge.type.trim()) {
      throw new Error('Every graph edge needs string from, to, and type values.');
    }
    if (!ids.has(edge.from) || !ids.has(edge.to)) throw new Error(`Graph edge ${edge.type} points to a missing node.`);
    edges.push({ from: edge.from, to: edge.to, type: edge.type });
  }
  return { id: graph.id, title: graph.title, nodes, edges };
}

function readStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const result: string[] = [];
  for (const item of value) {
    if (typeof item !== 'string') return undefined;
    result.push(item);
  }
  return result;
}

function readMarker(node: SceneNode): DeckMarker | undefined {
  const raw = node.getPluginData(MARKER_KEY);
  if (!raw) return undefined;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) return undefined;
    const marker = value;
    if (marker.schema !== 1 || typeof marker.graphId !== 'string' || typeof marker.graphSha256 !== 'string'
        || typeof marker.selectionSha256 !== 'string'
        || typeof marker.rowIndex !== 'number' || !Number.isInteger(marker.rowIndex) || marker.rowIndex < 0
        || !Array.isArray(marker.slideIds)) return undefined;
    const slideIds = readStringArray(marker.slideIds);
    const nodeIds = readStringArray(marker.nodeIds);
    const edgeIds = readStringArray(marker.edgeIds);
    if (!slideIds || !nodeIds || !edgeIds) return undefined;
    return {
      schema: 1,
      graphId: marker.graphId,
      graphSha256: marker.graphSha256,
      selectionSha256: marker.selectionSha256,
      rowIndex: marker.rowIndex,
      slideIds,
      nodeIds,
      edgeIds,
    };
  } catch {
    return undefined;
  }
}

function ownedRows(page: PageNode): SlideRowNode[] {
  return page.findAll(node => node.type === 'SLIDE_ROW' && readMarker(node) !== undefined)
    .filter((node): node is SlideRowNode => node.type === 'SLIDE_ROW');
}

function rowSlides(row: SlideRowNode): SlideNode[] {
  return row.children.filter((node): node is SlideNode => node.type === 'SLIDE');
}

function readLegacyRowMarker(node: SceneNode): LegacyRowMarker | undefined {
  const raw = node.getPluginData(MARKER_KEY);
  if (!raw) return undefined;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.schema !== 1 || typeof value.graphId !== 'string'
        || typeof value.graphSha256 !== 'string'
        || value.selectionSha256 !== undefined || value.nodeIds !== undefined || value.edgeIds !== undefined) return undefined;
    const indexed = value.rowIndex !== undefined;
    if (indexed && (typeof value.rowIndex !== 'number' || !Number.isInteger(value.rowIndex) || value.rowIndex < 0)) return undefined;
    const slideIds = readStringArray(value.slideIds);
    if (!slideIds) return undefined;
    return {
      kind: indexed ? 'row-indexed' : 'aggregate',
      graphId: value.graphId,
      graphSha256: value.graphSha256,
      ...(indexed && typeof value.rowIndex === 'number' ? { rowIndex: value.rowIndex } : {}),
      slideIds,
    };
  } catch {
    return undefined;
  }
}

function readLegacySlideStamp(slide: SlideNode): LegacySlideStamp | undefined {
  const raw = slide.getPluginData(SLIDE_MARKER_KEY);
  if (!raw) return undefined;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.schema !== 1 || typeof value.graphId !== 'string'
        || typeof value.graphSha256 !== 'string' || value.selectionSha256 !== undefined
        || value.edgeIds !== undefined) return undefined;
    const nodeIds = readStringArray(value.nodeIds);
    return nodeIds ? { graphId: value.graphId, graphSha256: value.graphSha256, nodeIds } : undefined;
  } catch {
    return undefined;
  }
}

function edgeSemanticId(edge: DeckEdge): string {
  return 'edge:' + JSON.stringify([edge.from, edge.to, edge.type]);
}

function nodeIds(graph: DeckGraph): string[] {
  return graph.nodes.map(node => node.id);
}

function edgeIds(graph: DeckGraph): string[] {
  return graph.edges.map(edgeSemanticId);
}

function slideNodeIds(graph: DeckGraph, index: number): string[] {
  return index === 0 ? nodeIds(graph) : [graph.nodes[index - 1]?.id ?? ''];
}

function slideEdgeIds(graph: DeckGraph, index: number): string[] {
  if (index === 0) return edgeIds(graph);
  const nodeId = graph.nodes[index - 1]?.id;
  return nodeId ? graph.edges.filter(edge => edge.from === nodeId || edge.to === nodeId).map(edgeSemanticId) : [];
}

function sameStrings(actual: string[], expected: string[]): boolean {
  return actual.join('\0') === expected.join('\0');
}

function legacySlideHasExpectedStamp(slide: SlideNode, graph: DeckGraph, index: number): boolean {
  const stamp = readLegacySlideStamp(slide);
  return Boolean(stamp && stamp.graphId === graph.id && stamp.graphSha256 === FLOW_REVIEW_GRAPH_SHA256
    && sameStrings(stamp.nodeIds, slideNodeIds(graph, index)));
}

function legacySlideContentMismatch(slide: SlideNode, graph: DeckGraph, index: number, nativeName?: string): string | undefined {
  const node = index === 0 ? undefined : graph.nodes[index - 1];
  const title = node ? node.title : graph.title;
  const body = deckContent(graph, node);
  const expectedName = node
    ? `${String(index).padStart(2, '0')} · ${node.kind} · ${node.title} · ${node.id}`
    : `00 · ${graph.title}`;
  if (slide.name !== expectedName && slide.name !== nativeName) return 'slide name';
  const textNodes = slide.children.filter((child): child is TextNode => child.type === 'TEXT');
  const titleText = textNodes.find(text => text.name === 'Review title');
  const bodyText = textNodes.find(text => text.name === (node ? `Node ${node.id}` : 'Graph provenance'));
  if (textNodes.length !== 2) return 'text node count';
  if (titleText?.characters !== title) return 'title text';
  if (bodyText?.characters !== body) return 'graph content';
  return undefined;
}

function legacyRowEntries(page: PageNode, graph: DeckGraph): Array<{ row: SlideRowNode; marker: LegacyRowMarker }> {
  return page.findAll(node => node.type === 'SLIDE_ROW').filter((node): node is SlideRowNode => node.type === 'SLIDE_ROW')
    .map(row => ({ row, marker: readLegacyRowMarker(row) }))
    .filter((entry): entry is { row: SlideRowNode; marker: LegacyRowMarker } => entry.marker?.graphId === graph.id
      && entry.marker.graphSha256 === FLOW_REVIEW_GRAPH_SHA256);
}

function findRowIndexedLegacyDeck(
  legacyRows: Array<{ row: SlideRowNode; marker: LegacyRowMarker }>,
  graph: DeckGraph,
): LegacyDeck | null {
  const indexedRows = legacyRows.filter(entry => entry.marker.kind === 'row-indexed');
  if (!indexedRows.length) return null;

  const deckSize = graph.nodes.length + 1;
  const rowCount = Math.ceil(deckSize / SLIDES_PER_ROW);
  const nativeNames = canvasSlideNames(figma.getCanvasGrid());
  const coverRows = indexedRows.filter(({ row, marker }) => {
    if (marker.rowIndex !== 0) return false;
    const slides = rowSlides(row);
    return slides[0] !== undefined && legacySlideHasExpectedStamp(slides[0], graph, 0);
  });
  if (!coverRows.length) return null;
  if (coverRows.length !== 1) throw new Error('Multiple source-only legacy decks match this graph; inspect them before migration.');

  const rows: SlideRowNode[] = [];
  const slides: SlideNode[] = [];
  for (let rowIndex = 0; rowIndex < rowCount; rowIndex++) {
    const firstSlideIndex = rowIndex * SLIDES_PER_ROW;
    const expectedCount = Math.min(SLIDES_PER_ROW, deckSize - firstSlideIndex);
    const candidates = indexedRows.filter(({ row, marker }) => {
      if (marker.rowIndex !== rowIndex) return false;
      const children = rowSlides(row);
      return children.length === expectedCount
        && sameStrings(marker.slideIds, children.map(slide => slide.id))
        && children.every((slide, index) => legacySlideHasExpectedStamp(slide, graph, firstSlideIndex + index));
    });
    if (candidates.length !== 1) throw new Error('Legacy slide rows are incomplete or ambiguous; inspect them before migration.');
    const row = candidates[0].row;
    const children = rowSlides(row);
    const mismatch = children.findIndex((slide, index) => legacySlideContentMismatch(slide, graph,
      firstSlideIndex + index, nativeNames.get(slide.id)) !== undefined);
    if (mismatch >= 0) {
      const detail = legacySlideContentMismatch(children[mismatch], graph, firstSlideIndex + mismatch,
        nativeNames.get(children[mismatch].id));
      throw new Error(`Legacy slide content conflicts with this graph selection at row ${rowIndex}, slide ${children[mismatch].id} (${detail}); inspect it before migration.`);
    }
    rows.push(row);
    slides.push(...children);
  }
  return { rows, slides };
}

function findAggregateLegacyDeck(
  page: PageNode,
  entry: { row: SlideRowNode; marker: LegacyRowMarker },
  graph: DeckGraph,
): LegacyDeck | null {
  const { row: markerRow, marker } = entry;
  if (marker.slideIds.length !== graph.nodes.length + 1) return null;
  const cover = page.findAll(node => node.type === 'SLIDE' && node.id === marker.slideIds[0])
    .find((node): node is SlideNode => node.type === 'SLIDE');
  if (!cover) throw new Error('Aggregate legacy marker points to a missing cover slide.');
  const coverStamp = readLegacySlideStamp(cover);
  if (!coverStamp || coverStamp.graphId !== graph.id || coverStamp.graphSha256 !== FLOW_REVIEW_GRAPH_SHA256) {
    throw new Error('Aggregate legacy cover marker conflicts with its row marker.');
  }
  if (!sameStrings(coverStamp.nodeIds, nodeIds(graph))) return null;
  if (new Set(marker.slideIds).size !== marker.slideIds.length) {
    throw new Error('Aggregate legacy marker contains duplicate slide IDs; inspect it before migration.');
  }

  const slidesById = new Map(allSlidesForPage(page).map(slide => [slide.id, slide]));
  const slides: SlideNode[] = [];
  for (const id of marker.slideIds) {
    const slide = slidesById.get(id);
    if (!slide) throw new Error('Aggregate legacy marker points to missing Slides.');
    slides.push(slide);
  }
  const selectedIds = new Set(marker.slideIds);
  const canvasGrid = figma.getCanvasGrid();
  const nativeNames = canvasSlideNames(canvasGrid);
  const gridRows = canvasGrid.map(gridRow => gridRow
    .filter(node => selectedIds.has(node.id))
    .filter((node): node is SlideNode => node.type === 'SLIDE'))
    .filter(gridRow => gridRow.length > 0);
  if (!sameStrings(gridRows.flat().map(slide => slide.id), marker.slideIds)) {
    throw new Error('Aggregate legacy Slides order differs from its stamped IDs; inspect them before migration.');
  }
  if (gridRows.length !== Math.ceil(slides.length / SLIDES_PER_ROW)
      || gridRows.some((gridRow, index) => gridRow.length !== Math.min(SLIDES_PER_ROW, slides.length - index * SLIDES_PER_ROW))) {
    throw new Error('Aggregate legacy slide grid has unexpected rows; inspect it before migration.');
  }

  const rows: SlideRowNode[] = [];
  for (const [index, gridRow] of gridRows.entries()) {
    const parent = gridRow[0].parent;
    if (!parent || parent.type !== 'SLIDE_ROW') throw new Error('Aggregate legacy slide has no native row parent.');
    const row = parent as SlideRowNode;
    if (gridRow.some(slide => slide.parent?.id !== row.id)) {
      throw new Error('Aggregate legacy grid row has slides from multiple native rows.');
    }
    const rowChildren = row.children;
    if (rowChildren.length !== gridRow.length || rowChildren.some((child, childIndex) => child.type !== 'SLIDE'
        || child.id !== gridRow[childIndex].id)) {
      throw new Error('Aggregate legacy row contains unlisted or reordered children.');
    }
    if (rows.some(existing => existing.id === row.id)) throw new Error('Aggregate legacy rows share one native parent.');
    rows.push(row);
    const firstIndex = index * SLIDES_PER_ROW;
    for (let offset = 0; offset < gridRow.length; offset++) {
      const slideIndex = firstIndex + offset;
      if (!legacySlideHasExpectedStamp(gridRow[offset], graph, slideIndex)) {
        throw new Error(`Aggregate legacy slide stamp conflicts at position ${slideIndex}.`);
      }
      const mismatch = legacySlideContentMismatch(gridRow[offset], graph, slideIndex, nativeNames.get(gridRow[offset].id));
      if (mismatch) throw new Error(`Aggregate legacy slide content conflicts at position ${slideIndex} (${mismatch}).`);
    }
  }
  if (rows[0]?.id !== markerRow.id) throw new Error('Aggregate legacy marker is not on its first native row.');
  return { rows, slides };
}

function canvasSlideNames(grid: SceneNode[][]): Map<string, string> {
  const names = new Map<string, string>();
  let index = 1;
  for (const row of grid) {
    for (const node of row) {
      if (node.type === 'SLIDE') names.set(node.id, String(index++));
    }
  }
  return names;
}

function allSlidesForPage(page: PageNode): SlideNode[] {
  return page.findAll(node => node.type === 'SLIDE').filter((node): node is SlideNode => node.type === 'SLIDE');
}

function findLegacyDeck(page: PageNode, graph: DeckGraph): LegacyDeck | null {
  const entries = legacyRowEntries(page, graph);
  if (!entries.length) return null;
  const candidates: LegacyDeck[] = [];
  for (const entry of entries.filter(item => item.marker.kind === 'aggregate')) {
    const deck = findAggregateLegacyDeck(page, entry, graph);
    if (deck) candidates.push(deck);
  }
  const indexed = findRowIndexedLegacyDeck(entries, graph);
  if (indexed) candidates.push(indexed);
  if (candidates.length > 1) throw new Error('Multiple source-only legacy decks match this graph; inspect them before migration.');
  return candidates[0] ?? null;
}

function migrateLegacyDeck(deck: LegacyDeck, graph: DeckGraph, selectionSha256: string): void {
  const writes: Array<{ node: SceneNode; key: string; previous: string }> = [];
  const set = (node: SceneNode, key: string, value: string): void => {
    writes.push({ node, key, previous: node.getPluginData(key) });
    node.setPluginData(key, value);
  };
  try {
    const allNodeIds = nodeIds(graph);
    const allEdgeIds = edgeIds(graph);
    for (const [rowIndex, row] of deck.rows.entries()) {
      const marker: DeckMarker = {
        schema: 1,
        graphId: graph.id,
        graphSha256: FLOW_REVIEW_GRAPH_SHA256,
        selectionSha256,
        rowIndex,
        slideIds: rowSlides(row).map(slide => slide.id),
        nodeIds: allNodeIds,
        edgeIds: allEdgeIds,
      };
      set(row, MARKER_KEY, JSON.stringify(marker));
    }
    deck.slides.forEach((slide, index) => {
      const stamp: SlideStamp = {
        schema: 1,
        graphId: graph.id,
        graphSha256: FLOW_REVIEW_GRAPH_SHA256,
        selectionSha256,
        nodeIds: slideNodeIds(graph, index),
        edgeIds: slideEdgeIds(graph, index),
      };
      set(slide, SLIDE_MARKER_KEY, JSON.stringify(stamp));
    });
  } catch (error: unknown) {
    const conflicts: string[] = [];
    for (const write of writes.reverse()) {
      try { write.node.setPluginData(write.key, write.previous); }
      catch { conflicts.push(write.node.id + ':' + write.key); }
    }
    if (conflicts.length) throw new Error(`${String(error)}; marker rollback failed for ${conflicts.join(', ')}.`);
    throw error;
  }
}

function readSlideStamp(slide: SlideNode): SlideStamp | undefined {
  const raw = slide.getPluginData(SLIDE_MARKER_KEY);
  if (!raw) return undefined;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.schema !== 1 || typeof value.graphId !== 'string'
        || typeof value.graphSha256 !== 'string' || typeof value.selectionSha256 !== 'string') return undefined;
    const nodes = readStringArray(value.nodeIds);
    const edges = readStringArray(value.edgeIds);
    if (!nodes || !edges) return undefined;
    return {
      schema: 1,
      graphId: value.graphId,
      graphSha256: value.graphSha256,
      selectionSha256: value.selectionSha256,
      nodeIds: nodes,
      edgeIds: edges,
    };
  } catch {
    return undefined;
  }
}

function hasSlideStamp(slide: SlideNode, graph: DeckGraph, index: number, selectionSha256: string): boolean {
  const stamp = readSlideStamp(slide);
  if (!stamp || stamp.graphId !== graph.id || stamp.graphSha256 !== FLOW_REVIEW_GRAPH_SHA256
      || stamp.selectionSha256 !== selectionSha256) return false;
  const node = index === 0 ? undefined : graph.nodes[index - 1];
  const expectedNodes = node ? [node.id] : nodeIds(graph);
  const expectedEdges = node
    ? graph.edges.filter(edge => edge.from === node.id || edge.to === node.id).map(edgeSemanticId)
    : edgeIds(graph);
  return stamp.nodeIds.join('\0') === expectedNodes.join('\0')
    && stamp.edgeIds.join('\0') === expectedEdges.join('\0');
}

function assertGraphEqual(actual: SceneNode[][], expected: SceneNode[][]): void {
  if (actual.length !== expected.length) throw new Error('Figma did not preserve the requested canvas grid rows.');
  for (let row = 0; row < expected.length; row++) {
    const actualIds = actual[row].map(node => node.id);
    const expectedIds = expected[row].map(node => node.id);
    if (actualIds.join('\0') !== expectedIds.join('\0')) throw new Error('Figma did not preserve the requested canvas grid order.');
  }
}

function setText(
  slide: SlideNode,
  name: string,
  characters: string,
  font: FontName,
  size: number,
  color: RGB,
  x: number,
  y: number,
  width: number,
  bottom: number,
  track: <T extends SceneNode>(node: T) => T,
): number {
  const text = track(figma.createText());
  slide.appendChild(text);
  text.name = name;
  text.fontName = font;
  text.fontSize = size;
  text.fills = [{ type: 'SOLID', color }];
  text.resize(width, 60);
  text.textAutoResize = 'HEIGHT';
  text.characters = characters;
  text.x = x;
  text.y = y;
  if (text.x < 0 || text.y < 0 || text.x + text.width > slide.width || text.y + text.height > bottom) {
    throw new Error(`Slide content exceeds its bounds: ${name}.`);
  }
  return text.height;
}

function deckContent(graph: DeckGraph, node?: DeckNode): string {
  if (!node) return `${graph.id}\n${graph.nodes.length} nodes · ${graph.edges.length} relationships\nGraph SHA-256: ${FLOW_REVIEW_GRAPH_SHA256}`;
  const outgoing = graph.edges.filter(edge => edge.from === node.id).map(edge => {
    const target = graph.nodes.find(candidate => candidate.id === edge.to);
    return `${edge.type} → ${target?.title ?? edge.to} (${edge.to})`;
  });
  const incoming = graph.edges.filter(edge => edge.to === node.id).map(edge => {
    const source = graph.nodes.find(candidate => candidate.id === edge.from);
    return `${source?.title ?? edge.from} (${edge.from}) → ${edge.type}`;
  });
  const parts = [
    `${node.kind.toUpperCase()} · ${node.id}`,
    ...(node.type ? [`Graph type: ${node.type}`] : []),
    ...(node.status ? [`Status: ${node.status}`] : []),
    node.detail,
  ];
  if (incoming.length) parts.push(`INCOMING\n${incoming.join('\n')}`);
  if (outgoing.length) parts.push(`OUTGOING\n${outgoing.join('\n')}`);
  return parts.filter(Boolean).join('\n\n');
}

function activateDeck(page: PageNode, slide: SlideNode): void {
  figma.viewport.slidesView = 'single-slide';
  page.focusedSlide = slide;
  page.selection = [slide];
  figma.viewport.scrollAndZoomIntoView([slide]);
}

async function main(): Promise<string> {
  if (figma.editorType !== 'slides') throw new Error('Open this recipe in Figma Slides.');
  const graph = parseGraph(FLOW_REVIEW_GRAPH);
  if (!/^[a-f0-9]{64}$/i.test(FLOW_REVIEW_GRAPH_SHA256)) throw new Error('The review graph SHA-256 is invalid.');

  const page = figma.currentPage;
  await page.loadAsync();
  const selectionSha256 = FLOW_REVIEW_SELECTION_SHA256;
  if (!/^[a-f0-9]{64}$/.test(FLOW_REVIEW_GRAPH_SHA256)
      || !/^[a-f0-9]{64}$/.test(selectionSha256)) throw new Error('The review graph or selection SHA-256 is invalid.');
  const existingRows = ownedRows(page);
  const sourceRows = existingRows.filter(row => {
    const marker = readMarker(row);
    return marker?.graphId === graph.id && marker.graphSha256 === FLOW_REVIEW_GRAPH_SHA256;
  });
  const expectedNodeIds = nodeIds(graph);
  const expectedEdgeIds = edgeIds(graph);
  const hasExactSelection = (marker: DeckMarker | undefined): boolean => Boolean(marker
    && marker.nodeIds.join('\0') === expectedNodeIds.join('\0')
    && marker.edgeIds.join('\0') === expectedEdgeIds.join('\0'));
  const matchingRows = sourceRows.filter(row => readMarker(row)?.selectionSha256 === selectionSha256)
    .sort((left, right) => (readMarker(left)?.rowIndex ?? 0) - (readMarker(right)?.rowIndex ?? 0));
  if (sourceRows.some(row => readMarker(row)?.selectionSha256 !== selectionSha256 && hasExactSelection(readMarker(row)))) {
    throw new Error('An existing deck has conflicting selection identity for the same node and edge IDs.');
  }
  if (matchingRows.length) {
    const slides = matchingRows.flatMap(rowSlides);
    const markers = matchingRows.map(readMarker);
    const markerSlideIds = markers.flatMap(marker => marker?.slideIds ?? []);
    const complete = matchingRows.length === Math.ceil((graph.nodes.length + 1) / SLIDES_PER_ROW)
      && markers.every((marker, index) => marker?.rowIndex === index && hasExactSelection(marker))
      && slides.length === graph.nodes.length + 1 && slides.length === markerSlideIds.length
      && slides.every((slide, index) => slide.id === markerSlideIds[index]
        && hasSlideStamp(slide, graph, index, selectionSha256));
    if (!complete) throw new Error('Existing flow review deck content conflicts with this selection; inspect it before rerunning.');
    activateDeck(page, slides[0]);
    return `Selected the existing flow review deck for ${graph.title}.`;
  }
  const legacy = findLegacyDeck(page, graph);
  if (legacy) {
    migrateLegacyDeck(legacy, graph, selectionSha256);
    activateDeck(page, legacy.slides[0]);
    return `Migrated and selected the existing Slides review for ${graph.title}.`;
  }

  const originalGrid = figma.getCanvasGrid().map(row => [...row]);
  const originalSelection = [...page.selection];
  const originalFocusedSlide = page.focusedSlide;
  const originalView = figma.viewport.slidesView;
  const created: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { created.push(node); return node; };
  let newSlides: SlideNode[] = [];
  const newRows: SlideRowNode[] = [];

  try {
    await Promise.all([figma.loadFontAsync(FONT_REGULAR), figma.loadFontAsync(FONT_BOLD)]);
    const rowCount = Math.ceil((graph.nodes.length + 1) / SLIDES_PER_ROW);
    const firstRowIndex = originalGrid.length;
    for (let index = 0; index < rowCount; index++) {
      const row = track(figma.createSlideRow(firstRowIndex + index));
      newRows.push(row);
      row.name = `Flow review · ${graph.id}${rowCount > 1 ? ` · ${index + 1}` : ''}`;
    }

    const entries: Array<DeckNode | undefined> = [undefined, ...graph.nodes];
    newSlides = entries.map((node, index) => {
      const rowIndex = firstRowIndex + Math.floor(index / SLIDES_PER_ROW);
      const columnIndex = index % SLIDES_PER_ROW;
      const slide = track(figma.createSlide(rowIndex, columnIndex));
      slide.name = node
        ? `${String(index).padStart(2, '0')} · ${node.kind} · ${node.id}`
        : `00 · ${graph.id}`;
      slide.fills = [{ type: 'SOLID', color: { r: 0.96, g: 0.97, b: 0.99 } }];
      const margin = slide.width * 0.07;
      const maxBottom = slide.height * 0.88;
      const title = node ? node.title : graph.title;
      const titleHeight = setText(slide, 'Review title', title, FONT_BOLD,
        Math.max(28, Math.min(64, slide.width * 0.038)), DARK, margin, margin, slide.width - 2 * margin,
        maxBottom, track);
      setText(slide, node ? `Node ${node.id}` : 'Graph provenance', deckContent(graph, node), FONT_REGULAR,
        Math.max(16, Math.min(24, slide.width * 0.014)), MUTED, margin, margin + titleHeight + slide.height * 0.045,
        slide.width - 2 * margin, maxBottom, track);
      slide.setSlideTransition({
        style: 'DISSOLVE', duration: 0.35, curve: 'EASE_IN_AND_OUT', timing: { type: 'ON_CLICK' },
      });
      slide.setPluginData(SLIDE_MARKER_KEY, JSON.stringify({
        schema: 1,
        graphId: graph.id,
        graphSha256: FLOW_REVIEW_GRAPH_SHA256,
        selectionSha256,
        nodeIds: node ? [node.id] : expectedNodeIds,
        edgeIds: node
          ? graph.edges.filter(edge => edge.from === node.id || edge.to === node.id).map(edgeSemanticId)
          : expectedEdgeIds,
      }));
      return slide;
    });

    for (const [rowIndex, row] of newRows.entries()) {
      const marker: DeckMarker = {
        schema: 1,
        graphId: graph.id,
        graphSha256: FLOW_REVIEW_GRAPH_SHA256,
        selectionSha256,
        rowIndex,
        slideIds: rowSlides(row).map(slide => slide.id),
        nodeIds: expectedNodeIds,
        edgeIds: expectedEdgeIds,
      };
      if (!marker.slideIds.length) throw new Error(`Figma created an empty slide row at ${rowIndex}.`);
      row.setPluginData(MARKER_KEY, JSON.stringify(marker));
    }

    const addedRows: SceneNode[][] = [];
    for (let index = 0; index < newSlides.length; index += SLIDES_PER_ROW) {
      addedRows.push(newSlides.slice(index, index + SLIDES_PER_ROW));
    }
    const targetGrid = [...originalGrid, ...addedRows];
    figma.setCanvasGrid(targetGrid);
    assertGraphEqual(figma.getCanvasGrid(), targetGrid);
    // Different selected subgraphs can share the same canonical graph digest.
    // Keep their generated rows separate so creating one review cannot erase another.
    try {
      activateDeck(page, newSlides[0]);
    } catch (error: unknown) {
      return `Created the flow review deck, but could not navigate to its cover: ${String(error)}.`;
    }
    return `Created a ${newSlides.length}-slide flow review deck for ${graph.title}.`;
  } catch (error: unknown) {
    for (const node of [...created].reverse()) {
      if (!node.removed) {
        try { node.remove(); } catch { /* Report any artifact that remains below. */ }
      }
    }
    try { figma.setCanvasGrid(originalGrid); } catch { /* The remaining-node report identifies incomplete rollback. */ }
    if (figma.currentPage.id === page.id) {
      page.selection = originalSelection.filter(node => !node.removed);
      page.focusedSlide = originalFocusedSlide && !originalFocusedSlide.removed ? originalFocusedSlide : null;
      figma.viewport.slidesView = originalView;
    }
    const remaining = created.filter(node => !node.removed).map(node => node.id);
    if (remaining.length) throw new Error(`${String(error)}; rollback left nodes ${remaining.join(', ')}.`);
    throw error;
  }
}

main().then(message => figma.closePlugin(message), error => figma.closePlugin(String(error)));
