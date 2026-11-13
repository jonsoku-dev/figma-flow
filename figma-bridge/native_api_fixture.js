const NATIVE_API_LAB_MARKER = 'figmaFlowNativeApiLab';
const NATIVE_API_LAB_VERSION = '0.31-scene-v1';
const NATIVE_API_LAB_PAGE = 'Figma Flow API Probe Lab';

function markNativeApiLabNode(node, semanticId) {
  node.setPluginData(NATIVE_API_LAB_MARKER, JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId}));
  return node;
}

function findNativeApiLabNode(page, semanticId) {
  const expected = JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId});
  const pending = [page];
  const seen = new Set();
  while (pending.length) {
    const node = pending.pop();
    if (!node || seen.has(node)) continue;
    seen.add(node);
    try {
      if (node.getPluginData(NATIVE_API_LAB_MARKER) === expected) return node;
    } catch (_) { /* The node may not expose plugin data. */ }
    try {
      const children = node.children;
      if (Array.isArray(children)) {
        for (let index = children.length - 1; index >= 0; index--) {
          if (children[index] && children[index].removed !== true) pending.push(children[index]);
        }
      }
    } catch (_) { /* A stale child is skipped; other live fixture nodes remain searchable. */ }
  }
  return null;
}

async function createNativeApiLabFixtures(figma, expectedFileKey) {
  if (figma.editorType !== 'figma' || figma.mode !== 'default') throw Error('Open this lab in Figma Design default mode.');
  if (expectedFileKey && figma.fileKey !== expectedFileKey) throw Error('The lab file key does not match the pinned fixture scope.');
  const fileKey = figma.fileKey;
  if (typeof fileKey !== 'string' || !fileKey) throw Error('Figma did not expose a private file key.');
  const originalPage = figma.currentPage;
  const originalSelection = [...originalPage.selection];
  let page = null;
  for (const candidate of figma.root.children) {
    if (candidate.type !== 'PAGE' || candidate.name !== NATIVE_API_LAB_PAGE) continue;
    await candidate.loadAsync();
    if (candidate.getPluginData(NATIVE_API_LAB_MARKER)
        === JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId: 'page'})) {
      page = candidate;
      break;
    }
  }
  if (!page) {
    page = figma.createPage();
    page.name = NATIVE_API_LAB_PAGE;
    markNativeApiLabNode(page, 'page');
  }
  await figma.setCurrentPageAsync(page);
  await page.loadAsync();
  const created = [];
  const createdSemanticIds = [];
  const failures = [];
  const owned = (semanticId, create) => {
    let node = findNativeApiLabNode(page, semanticId);
    if (!node) {
      node = create();
      markNativeApiLabNode(node, semanticId);
      created.push(node);
      createdSemanticIds.push(semanticId);
    }
    return node;
  };
  const addTo = (parent, node) => {
    if (node.parent !== parent) parent.appendChild(node);
    return node;
  };
  const nodes = [];
  const record = (semanticId, node) => {
    if (node && !nodes.some(row => row.semantic_id === semanticId))
      nodes.push({semantic_id: semanticId, observed_node_id: node.id, observed_type: node.type});
    return node;
  };
  const runStep = async (feature, action) => {
    try { return await action(); }
    catch (error) { failures.push({feature, reason: String(error)}); return null; }
  };
  try {
    const frame = owned('frame', () => figma.createFrame());
    frame.name = `${NATIVE_API_LAB_PAGE} · owned fixtures`;
    frame.resize(1400, 1100);
    frame.x = 0;
    frame.y = 0;
    record('scene-frame', frame);
    const rectangle = addTo(frame, owned('rectangle', () => figma.createRectangle()));
    rectangle.name = 'Figma Flow API lab · rectangle';
    rectangle.x = 16; rectangle.y = 16; rectangle.resize(80, 50);
    record('scene-rectangle', rectangle);
    const ellipse = addTo(frame, owned('ellipse', () => figma.createEllipse()));
    ellipse.name = 'Figma Flow API lab · ellipse'; ellipse.x = 112; ellipse.y = 16;
    record('scene-ellipse', ellipse);
    const line = addTo(frame, owned('line', () => figma.createLine()));
    line.name = 'Figma Flow API lab · line'; line.x = 208; line.y = 16;
    record('scene-line', line);
    const polygon = addTo(frame, owned('polygon', () => figma.createPolygon()));
    polygon.name = 'Figma Flow API lab · polygon'; polygon.x = 304; polygon.y = 16;
    record('scene-polygon', polygon);
    const star = addTo(frame, owned('star', () => figma.createStar()));
    star.name = 'Figma Flow API lab · star'; star.x = 400; star.y = 16;
    record('scene-star', star);
    let vector = owned('vector', () => figma.createVector());
    vector.name = 'Figma Flow API lab · vector';
    if (!vector.vectorPaths.length) vector.vectorPaths = [{windingRule: 'NONZERO', data: 'M 0 0 L 40 0 L 40 40 Z'}];
    addTo(frame, vector); vector.x = 496; vector.y = 16;
    record('scene-vector', vector);
    const text = addTo(frame, owned('text', () => figma.createText()));
    text.name = 'Figma Flow API lab · text';
    if (!text.characters) {
      await figma.loadFontAsync(text.fontName);
      text.characters = 'API probe sample';
    }
    text.x = 592; text.y = 16;
    record('scene-text', text);
    const componentA = owned('component-a', () => figma.createComponent());
    if (componentA.parent === page) addTo(frame, componentA);
    componentA.name = 'Figma Flow API lab · component A'; componentA.x = 760; componentA.y = 16;
    const componentB = owned('component-b', () => figma.createComponent());
    if (componentB.parent === page) addTo(frame, componentB);
    componentB.name = 'Figma Flow API lab · component B'; componentB.x = 856; componentB.y = 16;
    let componentSet = await runStep('scene-component-set', () => {
      let node = componentA.parent && componentA.parent.type === 'COMPONENT_SET'
        ? componentA.parent : findNativeApiLabNode(page, 'component-set');
      if (!node) {
        node = figma.combineAsVariants([componentA, componentB], frame);
        node.name = 'Figma Flow API lab · component set';
        markNativeApiLabNode(node, 'component-set'); created.push(node); createdSemanticIds.push('component-set');
      }
      return node;
    });
    record('scene-component-set', componentSet);
    let component = null;
    if (componentSet) {
      component = await runStep('scene-component', () => componentSet.children.find(node => node.type === 'COMPONENT')
        || findNativeApiLabNode(frame, 'component-a'));
    }
    record('scene-component', component);
    const slot = component ? await runStep('scene-slot', () =>
      owned('slot', () => component.createSlot())) : null;
    record('scene-slot', slot);
    const instance = component ? await runStep('scene-instance', () => {
      const node = addTo(frame, owned('instance', () => component.createInstance()));
      node.name = 'Figma Flow API lab · instance'; node.x = 952; node.y = 16;
      return node;
    }) : null;
    record('scene-instance', instance);
    const group = await runStep('scene-group', () => {
      let node = findNativeApiLabNode(page, 'group');
      if (!node) {
        const groupRect = addTo(frame, owned('group-child', () => figma.createRectangle()));
        groupRect.x = 16; groupRect.y = 112;
        const groupEllipse = addTo(frame, owned('group-child-ellipse', () => figma.createEllipse()));
        groupEllipse.x = 48; groupEllipse.y = 112;
        node = figma.group([groupRect, groupEllipse], frame);
        node.name = 'Figma Flow API lab · group'; markNativeApiLabNode(node, 'group'); created.push(node); createdSemanticIds.push('group');
      }
      return node;
    });
    record('scene-group', group);
    const booleanNode = await runStep('scene-boolean-operation', () => {
      let node = findNativeApiLabNode(page, 'boolean-operation');
      if (!node) {
        const booleanA = addTo(frame, owned('boolean-child-a', () => figma.createRectangle()));
        booleanA.x = 160; booleanA.y = 112;
        const booleanB = addTo(frame, owned('boolean-child-b', () => figma.createEllipse()));
        booleanB.x = 184; booleanB.y = 112;
        node = figma.union([booleanA, booleanB], frame);
        node.name = 'Figma Flow API lab · boolean'; markNativeApiLabNode(node, 'boolean-operation'); created.push(node); createdSemanticIds.push('boolean-operation');
      }
      return node;
    });
    record('scene-boolean-operation', booleanNode);
    const section = await runStep('scene-section', () => {
      const node = owned('section', () => figma.createSection());
      node.name = 'Figma Flow API lab · section';
      return node;
    });
    record('scene-section', section);
    const slice = await runStep('scene-slice', () => {
      const node = owned('slice', () => figma.createSlice());
      node.name = 'Figma Flow API lab · slice'; node.x = 0; node.y = 1150;
      return node;
    });
    record('scene-slice', slice);
    const textPath = await runStep('scene-text-path', () => {
      let node = findNativeApiLabNode(page, 'text-path');
      if (!node) {
        node = figma.createTextPath(vector, 0, 0.5);
        node.name = 'Figma Flow API lab · text path';
        markNativeApiLabNode(node, 'text-path'); created.push(node); createdSemanticIds.push('text-path');
      }
      return node;
    });
    record('scene-text-path', textPath);
    const document = figma.root;
    record('document-root', document);
    nodes.push({semantic_id: 'page-root', observed_node_id: page.id, observed_type: 'PAGE'});
    const result = {schema: 'figma-flow-native-api-lab-fixture-v1', fileKey, pageId: page.id,
      originalPageId: originalPage.id, createdCount: created.length, reused: created.length === 0,
      fixtureVersion: NATIVE_API_LAB_VERSION, createdSemanticIds, skipped: failures, nodes};
    return result;
  } finally {
    if (figma.currentPage.id === page.id) page.selection = [];
    await figma.setCurrentPageAsync(originalPage);
    if (figma.currentPage.id === originalPage.id)
      originalPage.selection = originalSelection.filter(node => !node.removed);
  }
}

function showNativeApiLabReceipt(figma, result) {
  const safe = JSON.stringify(result, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  figma.showUI(`<meta charset="utf-8"><h2>Figma Flow API lab fixtures</h2><pre style="white-space:pre-wrap">${safe}</pre><button onclick="parent.postMessage({pluginMessage:1},'*')">Close</button>`, {width: 680, height: 560});
  figma.ui.onmessage = () => figma.closePlugin();
}

async function runNativeApiLabOwnedWrites(figma, expectedFileKey) {
  if (figma.editorType !== 'figma' || figma.mode !== 'default') throw Error('Open this lab in Figma Design default mode.');
  if (expectedFileKey && figma.fileKey !== expectedFileKey) throw Error('The lab file key does not match the pinned fixture scope.');
  const expectedPage = JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId: 'page'});
  const page = figma.root.children.find(node => node.type === 'PAGE' && node.name === NATIVE_API_LAB_PAGE);
  if (!page) throw Error('Create the owned API fixture page before running write scenarios.');
  await page.loadAsync();
  if (page.getPluginData(NATIVE_API_LAB_MARKER) !== expectedPage) throw Error('The API fixture page is not owned by this lab.');
  if (figma.currentPage.id !== page.id) throw Error('Open the owned API fixture page before running write scenarios.');
  const frame = findNativeApiLabNode(page, 'frame');
  const text = findNativeApiLabNode(page, 'text');
  if (!frame || !text || text.type !== 'TEXT' || !text.characters.length) throw Error('The owned frame and text fixture are required.');
  const result = [];
  const record = async (method, receiver, action) => {
    const item = {method, receiver, status: 'unavailable', restored: false};
    try {
      const outcome = await action();
      item.status = outcome.applied ? 'success' : 'unavailable';
      item.restored = outcome.restored;
      if (outcome.reason) item.reason = outcome.reason;
      else if (!outcome.applied) item.reason = 'result-did-not-match';
    } catch (_) { item.status = 'unavailable'; item.reason = 'getter-or-setter-threw'; }
    result.push(item);
  };
  const textRange = () => [0, text.characters.length];
  const fontName = text.getRangeFontName(...textRange());
  const fontReady = fontName !== figma.mixed && fontName && typeof fontName.family === 'string'
    && typeof fontName.style === 'string';
  if (fontReady) await figma.loadFontAsync(fontName);
  await record('resize', 'FRAME', async () => {
    const width = frame.width, height = frame.height;
    let applied = false, restored = false;
    try {
      frame.resize(width + 1, height + 1);
      applied = frame.width === width + 1 && frame.height === height + 1;
    } finally {
      frame.resize(width, height);
      restored = frame.width === width && frame.height === height;
    }
    return {applied, restored};
  });
  const probeDataKey = 'figmaFlowNativeApiProbeRoundTrip';
  await record('getPluginData', 'FRAME', async () => {
    const value = frame.getPluginData(probeDataKey);
    return {applied: typeof value === 'string', restored: true,
      reason: value === '' ? 'owned-key-empty' : 'owned-key-present'};
  });
  await record('setPluginData', 'FRAME', async () => {
    const previous = frame.getPluginData(probeDataKey);
    let applied = false, restored = false;
    try {
      frame.setPluginData(probeDataKey, 'round-trip');
      applied = frame.getPluginData(probeDataKey) === 'round-trip';
    } finally {
      frame.setPluginData(probeDataKey, previous);
      restored = frame.getPluginData(probeDataKey) === previous;
    }
    return {applied, restored};
  });
  if (fontReady) {
    await record('setRangeFontName', 'TEXT', async () => {
      let applied = false, restored = false;
      try {
        text.setRangeFontName(...textRange(), fontName);
        applied = text.getRangeFontName(...textRange()) !== figma.mixed;
      } finally {
        text.setRangeFontName(...textRange(), fontName);
        restored = text.getRangeFontName(...textRange()) !== figma.mixed;
      }
      return {applied, restored};
    });
    const fontSize = text.getRangeFontSize(...textRange());
    if (typeof fontSize === 'number' && Number.isFinite(fontSize)) {
      await record('setRangeFontSize', 'TEXT', async () => {
        const temporary = fontSize < 9999 ? fontSize + 1 : fontSize - 1;
        let applied = false, restored = false;
        try {
          text.setRangeFontSize(...textRange(), temporary);
          applied = text.getRangeFontSize(...textRange()) === temporary;
        } finally {
          text.setRangeFontSize(...textRange(), fontSize);
          restored = text.getRangeFontSize(...textRange()) === fontSize;
        }
        return {applied, restored};
      });
    }
    const lineHeight = text.getRangeLineHeight(...textRange());
    if (lineHeight !== figma.mixed && lineHeight && typeof lineHeight === 'object') {
      await record('setRangeLineHeight', 'TEXT', async () => {
        const temporary = {unit: 'PIXELS', value: 21};
        let applied = false, restored = false;
        try {
          text.setRangeLineHeight(...textRange(), temporary);
          const current = text.getRangeLineHeight(...textRange());
          applied = current !== figma.mixed && current.unit === temporary.unit && current.value === temporary.value;
        } finally {
          text.setRangeLineHeight(...textRange(), lineHeight);
          const current = text.getRangeLineHeight(...textRange());
          restored = current !== figma.mixed && current.unit === lineHeight.unit
            && (lineHeight.unit === 'AUTO' || current.value === lineHeight.value);
        }
        return {applied, restored};
      });
    }
    const letterSpacing = text.getRangeLetterSpacing(...textRange());
    if (letterSpacing !== figma.mixed && letterSpacing && typeof letterSpacing === 'object') {
      await record('setRangeLetterSpacing', 'TEXT', async () => {
        const temporary = {unit: 'PIXELS', value: letterSpacing.value === 1 ? 2 : 1};
        let applied = false, restored = false;
        try {
          text.setRangeLetterSpacing(...textRange(), temporary);
          const current = text.getRangeLetterSpacing(...textRange());
          applied = current !== figma.mixed && current.unit === temporary.unit && current.value === temporary.value;
        } finally {
          text.setRangeLetterSpacing(...textRange(), letterSpacing);
          const current = text.getRangeLetterSpacing(...textRange());
          restored = current !== figma.mixed && current.unit === letterSpacing.unit && current.value === letterSpacing.value;
        }
        return {applied, restored};
      });
    }
    const fills = text.getRangeFills(...textRange());
    if (fills !== figma.mixed && Array.isArray(fills)) {
      await record('setRangeFills', 'TEXT', async () => {
        const temporary = [{type: 'SOLID', color: {r: 0.12, g: 0.42, b: 0.92}}];
        let applied = false, restored = false, reason;
        if (typeof text.setRangeFills !== 'function')
          return {applied: false, restored: true, reason: 'method-absent'};
        try {
          text.setRangeFills(...textRange(), temporary);
          const current = text.getRangeFills(...textRange());
          if (current === figma.mixed) reason = 'mixed-range';
          else if (!Array.isArray(current) || current.length !== 1 || current[0].type !== 'SOLID') reason = 'unexpected-paint-shape';
          else applied = ['r', 'g', 'b'].every(channel =>
            Math.abs(current[0].color[channel] - temporary[0].color[channel]) <= 0.001);
          if (!applied && !reason) reason = 'color-readback-mismatch';
        } finally {
          text.setRangeFills(...textRange(), fills);
          const current = text.getRangeFills(...textRange());
          restored = current !== figma.mixed && Array.isArray(current)
            && JSON.stringify(current) === JSON.stringify(fills);
        }
        return {applied, restored, reason};
      });
    }
  }
  return {schema: 'figma-flow-native-api-lab-write-receipt-v1', observed_at: new Date().toISOString(), fileKey: figma.fileKey,
    pageId: page.id, fixtureVersion: NATIVE_API_LAB_VERSION, methods: result,
    counts: result.reduce((counts, item) => { counts[item.status]++; if (!item.restored) counts.restoreFailed++; return counts; },
      {success: 0, unavailable: 0, restoreFailed: 0})};
}

async function runNativeApiLabOwnedReads(figma, expectedFileKey) {
  if (figma.editorType !== 'figma' || figma.mode !== 'default') throw Error('Open this lab in Figma Design default mode.');
  if (expectedFileKey && figma.fileKey !== expectedFileKey) throw Error('The lab file key does not match the pinned fixture scope.');
  const expectedPage = JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId: 'page'});
  const page = figma.root.children.find(node => node.type === 'PAGE' && node.name === NATIVE_API_LAB_PAGE);
  if (!page) throw Error('Create the owned API fixture page before running API read scenarios.');
  await page.loadAsync();
  if (page.getPluginData(NATIVE_API_LAB_MARKER) !== expectedPage) throw Error('The API fixture page is not owned by this lab.');
  if (figma.currentPage.id !== page.id) throw Error('Open the owned API fixture page before running API read scenarios.');
  const component = findNativeApiLabNode(page, 'component-a');
  const instance = findNativeApiLabNode(page, 'instance');
  const componentMarker = JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId: 'component-a'});
  const instanceMarker = JSON.stringify({version: NATIVE_API_LAB_VERSION, semanticId: 'instance'});
  if (!component || component.type !== 'COMPONENT' || component.getPluginData(NATIVE_API_LAB_MARKER) !== componentMarker
      || !instance || instance.type !== 'INSTANCE' || instance.getPluginData(NATIVE_API_LAB_MARKER) !== instanceMarker) {
    throw Error('The owned component and instance fixtures are required.');
  }
  const methods = [];
  let status = 'unavailable', count = 0, reason;
  try {
    if (typeof component.getInstancesAsync !== 'function') status = 'unsupported';
    else {
      const instances = await component.getInstancesAsync();
      if (!Array.isArray(instances)) reason = 'unexpected-result-shape';
      else if (instances.length > 64) reason = 'instance-list-cap';
      else {
        const owned = instances.filter(node => node && node.type === 'INSTANCE'
          && node.getPluginData(NATIVE_API_LAB_MARKER) === instanceMarker);
        count = owned.length;
        status = 'success';
      }
    }
  } catch (_) { reason = 'getter-threw'; }
  methods.push({method: 'getInstancesAsync', status, ...(status === 'success' ? {value: {count}} : {}), ...(reason ? {reason} : {})});
  let mainStatus = 'unavailable', mainValue, mainReason;
  try {
    if (typeof instance.getMainComponentAsync !== 'function') mainStatus = 'unsupported';
    else {
      const main = await instance.getMainComponentAsync();
      if (main === null) { mainStatus = 'success'; mainValue = 'unlinked'; }
      else if (main && main.getPluginData(NATIVE_API_LAB_MARKER) === componentMarker) {
        mainStatus = 'success'; mainValue = 'linked-to-owned-component';
      } else { mainStatus = 'success'; mainValue = 'linked-to-other-component'; }
    }
  } catch (_) { mainReason = 'getter-threw'; }
  methods.push({method: 'getMainComponentAsync', status: mainStatus,
    ...(mainStatus === 'success' ? {value: mainValue} : {}), ...(mainReason ? {reason: mainReason} : {})});
  const counts = methods.reduce((result, row) => { result[row.status]++; return result; },
    {success: 0, unavailable: 0, unsupported: 0, blocked: 0});
  return {schema: 'figma-flow-native-api-lab-read-receipt-v1', observed_at: new Date().toISOString(),
    fileKey: figma.fileKey, pageId: page.id, fixtureVersion: NATIVE_API_LAB_VERSION, methods, counts};
}
