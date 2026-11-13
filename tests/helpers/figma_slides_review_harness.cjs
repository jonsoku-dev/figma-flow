const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(process.argv[2], 'utf8');
const expected = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const secondSource = process.argv[4] ? fs.readFileSync(process.argv[4], 'utf8') : null;
const secondExpected = process.argv[5] ? JSON.parse(fs.readFileSync(process.argv[5], 'utf8')) : null;
let nextNodeId = 0;

function sceneNode(type, name) {
  const data = new Map();
  return {
    id: `${type}-${++nextNodeId}`,
    type,
    name,
    removed: false,
    children: [],
    getPluginData(key) { return data.get(key) ?? ''; },
    setPluginData(key, value) { data.set(key, value); },
    getPluginDataKeys() { return [...data.keys()]; },
    remove() {
      this.removed = true;
      if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
      for (const row of state.rows) row.children = row.children.filter(child => child !== this);
      for (const gridRow of state.gridRows) gridRow.slides = gridRow.slides.filter(child => child !== this);
    },
  };
}

function makeState({ failSetSlideGrid = false } = {}) {
  const userRow = sceneNode('SLIDE_ROW', 'User row');
  const userSlide = sceneNode('SLIDE', 'Existing user slide');
  userSlide.width = 1920;
  userSlide.height = 1080;
  userSlide.parent = userRow;
  userRow.children.push(userSlide);
  const state = {
    rows: [userRow],
    gridRows: [{ row: userRow, slides: [userSlide] }],
    messages: [],
    failSetSlideGrid,
    currentPage: null,
  };
  const page = {
    id: 'page-1',
    selection: [userSlide],
    focusedSlide: null,
    async loadAsync() {},
    findAll(predicate) {
      const result = [];
      const visit = node => {
        for (const child of node.children) {
          if (predicate(child)) result.push(child);
          visit(child);
        }
      };
      for (const row of state.rows) {
        if (predicate(row)) result.push(row);
        visit(row);
      }
      return result;
    },
  };
  state.currentPage = page;
  const figma = {
    editorType: 'slides',
    currentPage: page,
    viewport: {
      slidesView: 'grid',
      scrollAndZoomIntoView() {},
    },
    async loadFontAsync() {},
    createSlideRow(index) {
      const row = sceneNode('SLIDE_ROW', '');
      row.remove = function removeRow() {
        this.removed = true;
        for (const child of this.children) child.removed = true;
        state.rows = state.rows.filter(candidate => candidate !== this);
        state.gridRows = state.gridRows.filter(gridRow => gridRow.row !== this);
      };
      state.rows.splice(index, 0, row);
      state.gridRows.splice(index, 0, { row, slides: [] });
      return row;
    },
    createSlide(rowIndex, columnIndex) {
      const slide = sceneNode('SLIDE', '');
      slide.width = 1920;
      slide.height = 1080;
      slide.fills = [];
      slide.setSlideTransition = transition => { slide.transition = transition; };
      slide.appendChild = child => {
        child.parent = slide;
        slide.children.push(child);
      };
      const row = state.gridRows[rowIndex];
      if (!row || row.slides.length !== columnIndex) throw new Error('Invalid row or column index.');
      row.slides.push(slide);
      row.row.children.push(slide);
      slide.parent = row.row;
      return slide;
    },
    createText() {
      const text = sceneNode('TEXT', '');
      let characters = '';
      let fontSize = 16;
      let width = 100;
      Object.defineProperty(text, 'characters', {
        get() { return characters; },
        set(value) { characters = value; },
      });
      Object.defineProperty(text, 'fontSize', {
        get() { return fontSize; },
        set(value) { fontSize = value; },
      });
      Object.defineProperty(text, 'width', { get() { return width; } });
      Object.defineProperty(text, 'height', {
        get() {
          const columns = Math.max(1, Math.floor(width / (fontSize * 0.55)));
          const lines = characters.split('\n').reduce((total, line) => total + Math.max(1, Math.ceil(line.length / columns)), 0);
          return lines * fontSize * 1.35;
        },
      });
      text.resize = (nextWidth) => { width = nextWidth; };
      return text;
    },
    getCanvasGrid() { return state.gridRows.map(row => [...row.slides]); },
    setCanvasGrid(rows) {
      if (state.failSetSlideGrid) {
        state.failSetSlideGrid = false;
        throw new Error('Injected grid write failure.');
      }
      state.gridRows = rows.map(slides => {
        const row = slides[0]?.parent ?? null;
        return { row, slides: [...slides] };
      });
    },
    closePlugin(message) { state.messages.push(String(message ?? '')); },
  };
  return { state, figma, userSlide };
}

function addLegacyDeck(state, expected) {
  const graph = expected.graph;
  const slideCount = graph.nodes.length + 1;
  const rowCount = Math.ceil(slideCount / 3);
  const legacyRows = [];
  const legacySlides = [];
  for (let rowIndex = 0; rowIndex < rowCount; rowIndex++) {
    const row = sceneNode('SLIDE_ROW', `Flow review · ${graph.id} · ${rowIndex + 1}`);
    const slides = [];
    const firstIndex = rowIndex * 3;
    const endIndex = Math.min(slideCount, firstIndex + 3);
    for (let index = firstIndex; index < endIndex; index++) {
      const node = index === 0 ? undefined : graph.nodes[index - 1];
      const slide = sceneNode('SLIDE', node
        ? `${String(index).padStart(2, '0')} · ${node.kind} · ${node.title} · ${node.id}`
        : `00 · ${graph.title}`);
      slide.width = 1920;
      slide.height = 1080;
      slide.fills = [];
      slide.setSlideTransition = transition => { slide.transition = transition; };
      slide.appendChild = child => { child.parent = slide; slide.children.push(child); };
      const addText = (name, characters) => {
        const text = sceneNode('TEXT', name);
        text.characters = characters;
        text.fontName = { family: 'Inter', style: name === 'Review title' ? 'Bold' : 'Regular' };
        text.fills = [];
        text.textAutoResize = 'HEIGHT';
        text.resize = width => { text.width = width; };
        slide.appendChild(text);
      };
      const title = node ? node.title : graph.title;
      const body = node ? (() => {
        const incoming = graph.edges.filter(edge => edge.to === node.id).map(edge => {
          const source = graph.nodes.find(candidate => candidate.id === edge.from);
          return `${source?.title ?? edge.from} (${edge.from}) → ${edge.type}`;
        });
        const outgoing = graph.edges.filter(edge => edge.from === node.id).map(edge => {
          const target = graph.nodes.find(candidate => candidate.id === edge.to);
          return `${edge.type} → ${target?.title ?? edge.to} (${edge.to})`;
        });
        const parts = [`${node.kind.toUpperCase()} · ${node.id}`, ...(node.type ? [`Graph type: ${node.type}`] : []),
          ...(node.status ? [`Status: ${node.status}`] : []), node.detail];
        if (incoming.length) parts.push(`INCOMING\n${incoming.join('\n')}`);
        if (outgoing.length) parts.push(`OUTGOING\n${outgoing.join('\n')}`);
        return parts.filter(Boolean).join('\n\n');
      })() : `${graph.id}\n${graph.nodes.length} nodes · ${graph.edges.length} relationships\nGraph SHA-256: ${expected.sha256}`;
      addText('Review title', title);
      addText(node ? `Node ${node.id}` : 'Graph provenance', body);
      slide.setPluginData('figmaFlowReviewSlide', JSON.stringify({
        schema: 1,
        graphId: graph.id,
        graphSha256: expected.sha256,
        nodeIds: node ? [node.id] : graph.nodes.map(item => item.id),
      }));
      slides.push(slide);
      legacySlides.push(slide);
    }
    for (const slide of slides) {
      slide.parent = row;
      row.children.push(slide);
    }
    row.setPluginData('figmaFlowReviewDeck', JSON.stringify({
      schema: 1,
      graphId: graph.id,
      graphSha256: expected.sha256,
      rowIndex,
      slideIds: slides.map(slide => slide.id),
    }));
    legacyRows.push(row);
    state.rows.push(row);
    state.gridRows.push({ row, slides });
  }
  return { rows: legacyRows, slides: legacySlides };
}

function addAggregateLegacyDeck(state, expected, useNativeGridNames = false) {
  const deck = addLegacyDeck(state, expected);
  if (useNativeGridNames) {
    state.gridRows.flatMap(row => row.slides).forEach((slide, index) => { slide.name = String(index + 1); });
  }
  deck.rows[0].setPluginData('figmaFlowReviewDeck', JSON.stringify({
    schema: 1,
    graphId: expected.graph.id,
    graphSha256: expected.sha256,
    slideIds: deck.slides.map(slide => slide.id),
  }));
  for (const row of deck.rows.slice(1)) row.setPluginData('figmaFlowReviewDeck', '');
  return deck;
}

async function run(code, state, figma) {
  vm.runInNewContext(code, vm.createContext({ figma }));
  await new Promise(resolve => setImmediate(resolve));
  return state.messages.at(-1);
}

(async () => {
  const { state, figma, userSlide } = makeState();
  const created = await run(source, state, figma);
  assert.match(created, /Created a \d+-slide flow review deck/);
  assert.equal(state.rows.length, Math.ceil((expected.nodes.length + 1) / 3) + 1);
  assert.equal(state.gridRows[0].slides[0], userSlide);
  const deckSlides = state.gridRows.slice(1).flatMap(row => row.slides);
  assert.equal(deckSlides.length, expected.nodes.length + 1);
  assert.equal(JSON.stringify(deckSlides.slice(1).map(slide => slide.name.split(' · ').at(-1))),
    JSON.stringify(expected.nodes.map(node => node.id)));
  assert.equal(deckSlides[0].getPluginData('figmaFlowReviewDeck'), '');
  assert.equal(JSON.stringify(JSON.parse(state.rows[1].getPluginData('figmaFlowReviewDeck')).slideIds),
    JSON.stringify(deckSlides.slice(0, 3).map(slide => slide.id)));
  const titleStamp = JSON.parse(deckSlides[0].getPluginData('figmaFlowReviewSlide'));
  assert.equal(titleStamp.graphId, expected.id);
  assert.equal(JSON.stringify(titleStamp.nodeIds), JSON.stringify(expected.nodes.map(node => node.id)));
  for (const node of expected.nodes) {
    const slide = deckSlides.find(candidate => candidate.name.endsWith(` · ${node.id}`));
    assert.ok(slide, `Missing slide for ${node.id}`);
    const stamp = JSON.parse(slide.getPluginData('figmaFlowReviewSlide'));
    assert.equal(stamp.graphSha256, expected.sha256);
    assert.equal(JSON.stringify(stamp.nodeIds), JSON.stringify([node.id]));
    const text = slide.children.map(child => child.characters).join('\n');
    assert.ok(text.includes(node.title));
    assert.ok(text.includes(node.type));
    assert.ok(text.includes(node.status));
    for (const edge of expected.edges.filter(item => item.from === node.id || item.to === node.id)) {
      assert.ok(text.includes(edge.type), `Missing ${edge.type} relation on ${node.id}`);
      const other = expected.nodes.find(candidate => candidate.id === (edge.from === node.id ? edge.to : edge.from));
      assert.ok(text.includes(other.id), `Missing endpoint ${other.id} for relation on ${node.id}`);
    }
    assert.equal(slide.transition.style, 'DISSOLVE');
  }
  assert.equal(state.currentPage.focusedSlide, deckSlides[0]);
  assert.equal(state.currentPage.selection[0], deckSlides[0]);
  assert.equal(figma.viewport.slidesView, 'single-slide');

  const rowCount = state.rows.length;
  const slideCount = state.gridRows.flatMap(row => row.slides).length;
  const reused = await run(source, state, figma);
  assert.match(reused, /Selected the existing flow review deck/);
  assert.equal(state.rows.length, rowCount);
  assert.equal(state.gridRows.flatMap(row => row.slides).length, slideCount);

  if (secondSource && secondExpected) {
    assert.equal(expected.sha256, secondExpected.sha256);
    assert.notEqual(expected.selectionSha256, secondExpected.selectionSha256);
    const secondCreated = await run(secondSource, state, figma);
    assert.match(secondCreated, /Created a \d+-slide flow review deck/);
    const selectedRowsA = state.rows.filter(row => {
      try { return JSON.parse(row.getPluginData('figmaFlowReviewDeck')).selectionSha256 === expected.selectionSha256; }
      catch { return false; }
    });
    const selectedRowsB = state.rows.filter(row => {
      try { return JSON.parse(row.getPluginData('figmaFlowReviewDeck')).selectionSha256 === secondExpected.selectionSha256; }
      catch { return false; }
    });
    assert.equal(selectedRowsA.length, Math.ceil((expected.nodes.length + 1) / 3));
    assert.equal(selectedRowsB.length, Math.ceil((secondExpected.nodes.length + 1) / 3));
    for (const [rows, graph] of [[selectedRowsA, expected], [selectedRowsB, secondExpected]]) {
      const nodeIds = graph.nodes.map(node => node.id);
      const edgeIds = graph.edges.map(edge => `edge:${JSON.stringify([edge.from, edge.to, edge.type])}`);
      for (const row of rows) {
        const marker = JSON.parse(row.getPluginData('figmaFlowReviewDeck'));
        assert.equal(JSON.stringify(marker.nodeIds), JSON.stringify(nodeIds));
        assert.equal(JSON.stringify(marker.edgeIds), JSON.stringify(edgeIds));
      }
    }
    const combinedSlideCount = state.gridRows.flatMap(row => row.slides).length;
    assert.equal(combinedSlideCount, 1 + (expected.nodes.length + 1) + (secondExpected.nodes.length + 1));

    const selectedAgain = await run(source, state, figma);
    assert.match(selectedAgain, /Selected the existing flow review deck/);
    assert.equal(state.gridRows.flatMap(row => row.slides).length, combinedSlideCount);

    const selectedSlide = state.gridRows.flatMap(row => row.slides)
      .find(slide => slide.getPluginData('figmaFlowReviewSlide')
        && JSON.parse(slide.getPluginData('figmaFlowReviewSlide')).selectionSha256 === expected.selectionSha256);
    assert.ok(selectedSlide);
    const stamp = JSON.parse(selectedSlide.getPluginData('figmaFlowReviewSlide'));
    stamp.nodeIds = ['node:manual-edit'];
    stamp.edgeIds = ['edge:manual-edit'];
    selectedSlide.setPluginData('figmaFlowReviewSlide', JSON.stringify(stamp));
    const countBeforeConflict = state.gridRows.flatMap(row => row.slides).length;
    const conflict = await run(source, state, figma);
    assert.match(conflict, /manual reconciliation|content conflicts/);
    assert.equal(state.gridRows.flatMap(row => row.slides).length, countBeforeConflict);

    const legacy = makeState();
    const legacyDeck = addLegacyDeck(legacy.state, expected);
    const legacySlideCount = legacy.state.gridRows.flatMap(row => row.slides).length;
    const legacyText = legacyDeck.slides.map(slide => slide.children.map(child => child.characters));
    const distinctSelection = await run(secondSource, legacy.state, legacy.figma);
    assert.match(distinctSelection, /Created a \d+-slide flow review deck/);
    const expectedWithB = legacySlideCount + secondExpected.nodes.length + 1;
    assert.equal(legacy.state.gridRows.flatMap(row => row.slides).length, expectedWithB);
    assert.ok(legacyDeck.rows.every(row => !JSON.parse(row.getPluginData('figmaFlowReviewDeck')).selectionSha256));

    const migratedLegacy = await run(source, legacy.state, legacy.figma);
    assert.match(migratedLegacy, /Migrated and selected the existing Slides review/);
    assert.equal(legacy.state.gridRows.flatMap(row => row.slides).length, expectedWithB);
    assert.ok(legacyDeck.rows.every(row => JSON.parse(row.getPluginData('figmaFlowReviewDeck')).selectionSha256 === expected.selectionSha256));
    assert.equal(JSON.stringify(legacyDeck.slides.map(slide => slide.children.map(child => child.characters))), JSON.stringify(legacyText));
    const migratedAgain = await run(source, legacy.state, legacy.figma);
    assert.match(migratedAgain, /Selected the existing flow review deck/);
    assert.equal(legacy.state.gridRows.flatMap(row => row.slides).length, expectedWithB);

    const aggregateLegacy = makeState();
    const aggregateDeck = addAggregateLegacyDeck(aggregateLegacy.state, expected, true);
    const aggregateSlideCount = aggregateLegacy.state.gridRows.flatMap(row => row.slides).length;
    const aggregateB = await run(secondSource, aggregateLegacy.state, aggregateLegacy.figma);
    assert.match(aggregateB, /Created a \d+-slide flow review deck/);
    const aggregateAfterB = aggregateSlideCount + secondExpected.nodes.length + 1;
    assert.equal(aggregateLegacy.state.gridRows.flatMap(row => row.slides).length, aggregateAfterB);
    const aggregateMigration = await run(source, aggregateLegacy.state, aggregateLegacy.figma);
    assert.match(aggregateMigration, /Migrated and selected the existing Slides review/);
    assert.equal(aggregateLegacy.state.gridRows.flatMap(row => row.slides).length, aggregateAfterB);
    assert.equal(aggregateDeck.rows.length, Math.ceil((expected.nodes.length + 1) / 3));
    assert.ok(aggregateDeck.rows.every((row, index) => {
      const marker = JSON.parse(row.getPluginData('figmaFlowReviewDeck'));
      return marker.rowIndex === index && marker.selectionSha256 === expected.selectionSha256;
    }));
    const aggregateAgain = await run(source, aggregateLegacy.state, aggregateLegacy.figma);
    assert.match(aggregateAgain, /Selected the existing flow review deck/);
    assert.equal(aggregateLegacy.state.gridRows.flatMap(row => row.slides).length, aggregateAfterB);

    const editedLegacy = makeState();
    const editedDeck = addLegacyDeck(editedLegacy.state, expected);
    const editedText = editedDeck.slides[1].children[1];
    editedText.characters += '\nmanual edit';
    const editedSlideCount = editedLegacy.state.gridRows.flatMap(row => row.slides).length;
    const rejectedLegacy = await run(source, editedLegacy.state, editedLegacy.figma);
    assert.match(rejectedLegacy, /Legacy slide content conflicts/);
    assert.equal(editedLegacy.state.gridRows.flatMap(row => row.slides).length, editedSlideCount);
    assert.ok(editedDeck.rows.every(row => !JSON.parse(row.getPluginData('figmaFlowReviewDeck')).selectionSha256));

    const ambiguousLegacy = makeState();
    const firstLegacyDeck = addLegacyDeck(ambiguousLegacy.state, expected);
    const secondLegacyDeck = addLegacyDeck(ambiguousLegacy.state, expected);
    const ambiguousSlideCount = ambiguousLegacy.state.gridRows.flatMap(row => row.slides).length;
    const ambiguousLegacyResult = await run(source, ambiguousLegacy.state, ambiguousLegacy.figma);
    assert.match(ambiguousLegacyResult, /Multiple source-only legacy decks match this graph/);
    assert.equal(ambiguousLegacy.state.gridRows.flatMap(row => row.slides).length, ambiguousSlideCount);
    assert.ok([...firstLegacyDeck.rows, ...secondLegacyDeck.rows].every(row => !JSON.parse(row.getPluginData('figmaFlowReviewDeck')).selectionSha256));
  }

  const rollback = makeState({ failSetSlideGrid: true });
  const failed = await run(source, rollback.state, rollback.figma);
  assert.match(failed, /Injected grid write failure/);
  assert.equal(JSON.stringify(rollback.state.gridRows.map(row => row.slides.map(slide => slide.id))),
    JSON.stringify([[rollback.userSlide.id]]));
  assert.equal(rollback.state.rows.length, 1);
  assert.equal(rollback.state.currentPage.selection[0], rollback.userSlide);
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
