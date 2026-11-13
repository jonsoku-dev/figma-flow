const WEB_DESIGN_KEY = 'figma-flow-web-design-id';
const WEB_DESIGN_HASH = 'figma-flow-web-design-sha256';
const WEB_SCENE_HASH = 'figma-flow-web-scene-fingerprint';
const WEB_COMPONENT_MAIN = 'figma-flow-web-component-main-id';
const WEB_ELEMENT_ID = 'figma-flow-web-element-id';

function webColor(value) {
  const hex = value.slice(1);
  const alpha = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1;
  return {
    color: {
      r: parseInt(hex.slice(0, 2), 16) / 255,
      g: parseInt(hex.slice(2, 4), 16) / 255,
      b: parseInt(hex.slice(4, 6), 16) / 255,
    },
    opacity: alpha,
  };
}

function webSolid(value) {
  const parsed = webColor(value);
  return { type: 'SOLID', color: parsed.color, opacity: parsed.opacity };
}

function webDecodeBase64(value) {
  if (typeof value !== 'string' || value.length % 4 !== 0 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    throw Error('Embedded image data is not valid base64');
  }
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const output = new Uint8Array(Math.floor(value.length * 3 / 4) - (value.endsWith('==') ? 2 : value.endsWith('=') ? 1 : 0));
  let bits = 0;
  let buffer = 0;
  let offset = 0;
  for (const character of value.replace(/=+$/, '')) {
    buffer = (buffer << 6) | alphabet.indexOf(character);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      output[offset++] = (buffer >> bits) & 0xff;
    }
  }
  return output;
}

function webValidate(plan) {
  const design = plan.web_design;
  if (design?.schema !== 'figma-flow-web-design-v1' || !Array.isArray(design.screens) || !design.screens.length) {
    throw Error('Pinned web screen graph required');
  }
  for (const screen of design.screens) {
    if (typeof screen.id !== 'string' || !screen.id.startsWith('WEB-') || !screen.layout || !Array.isArray(screen.elements)
        || !Number.isFinite(screen.layout.width) || !Number.isFinite(screen.layout.height)
        || screen.layout.width <= 0 || screen.layout.height <= 0 || screen.layout.width > 32768 || screen.layout.height > 32768) {
      throw Error('Invalid screen node');
    }
    for (const element of screen.elements) {
      const box = element.box;
      if (!['frame', 'text', 'component', 'image', 'vector', 'annotation'].includes(element.kind)
          || !box || !['x', 'y', 'width', 'height'].every(key => Number.isFinite(box[key]))
          || Math.abs(box.x) > 100000 || Math.abs(box.y) > 100000 || box.width < 0 || box.height < 0
          || box.width > 32768 || box.height > 32768) {
        throw Error('Invalid screen element');
      }
      if (element.kind === 'image' && !['cover', 'contain'].includes(element.objectFit || 'cover')) throw Error('Unsupported image object fit');
      const paint = element.paint || {};
      if (paint.borderRadius > 1_000_000_000 || paint.borderWidth > 128 || paint.opacity > 1) throw Error('Paint exceeds native frame limits');
      if (element.kind === 'image' && (!element.asset || !/^[a-f0-9]{64}$/.test(element.asset.sha256)
          || !['image/png', 'image/jpeg', 'image/webp'].includes(element.asset.mimeType))) throw Error('Image needs a pinned raster hash and supported MIME type');
      if (element.kind === 'component' && (typeof element.componentKey !== 'string' || !element.componentKey || element.componentKey.length > 160)) {
        throw Error('Component needs a bounded stable componentKey');
      }
      if (element.kind === 'vector' && (!element.svg || element.svg.length > 200000 || /<!|<\?|url\s*\(|javascript:/i.test(element.svg))) {
        throw Error('Unsafe SVG vector');
      }
      if (element.kind === 'text' && typeof element.text?.characters !== 'string') throw Error('Text element needs observed characters');
    }
  }
  if (design.preview_width !== undefined && (!Number.isInteger(design.preview_width) || design.preview_width < 360 || design.preview_width > 480)) {
    throw Error('Preview width must be between 360 and 480 pixels');
  }
  if (!design.assets || typeof design.assets !== 'object' || Array.isArray(design.assets)) throw Error('Embedded image asset map required');
  const assetHashes = new Set(Object.keys(design.assets));
  for (const screen of design.screens) for (const element of screen.elements) {
    if (element.kind === 'image' && (!assetHashes.has(element.asset.sha256) || typeof design.assets[element.asset.sha256] !== 'string')) {
      throw Error(`Image ${element.id} has no embedded content for its pinned hash`);
    }
  }
}

function webSceneValue(node) {
  const plain = value => {
    try { return JSON.parse(JSON.stringify(value)); }
    catch (_) { return String(value); }
  };
  const paints = value => Array.isArray(value) ? value.map(paint => ({
    type: paint.type, color: plain(paint.color), opacity: paint.opacity, visible: paint.visible,
    blendMode: paint.blendMode, scaleMode: paint.scaleMode, imageHash: paint.imageHash,
    imageTransform: plain(paint.imageTransform), rotation: paint.rotation, filters: plain(paint.filters),
    gradientStops: plain(paint.gradientStops), gradientTransform: plain(paint.gradientTransform),
  })) : null;
  const scene = {
    type: node.type,
    name: node.name,
    x: node.x,
    y: node.y,
    width: node.width,
    height: node.height,
    opacity: node.opacity,
    visible: node.visible,
    locked: node.locked,
    rotation: node.rotation,
    fills: paints(node.fills),
    strokes: paints(node.strokes),
    effects: plain(node.effects),
    strokeWeight: node.strokeWeight,
    strokeAlign: node.strokeAlign,
    cornerRadius: node.cornerRadius,
    corners: ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'].map(key => node[key]),
    boundVariables: plain(node.boundVariables),
    fillStyleId: node.fillStyleId,
    strokeStyleId: node.strokeStyleId,
    effectStyleId: node.effectStyleId,
    clipsContent: node.clipsContent,
    webComponentMainId: node.getPluginData?.(WEB_COMPONENT_MAIN) || null,
    layoutMode: node.layoutMode,
    paddingLeft: node.paddingLeft,
    paddingRight: node.paddingRight,
    paddingTop: node.paddingTop,
    paddingBottom: node.paddingBottom,
  };
  if (node.type === 'TEXT') {
    scene.characters = node.characters;
    scene.fontName = typeof node.fontName === 'object' ? node.fontName : String(node.fontName);
    scene.fontSize = typeof node.fontSize === 'number' ? node.fontSize : null;
    scene.fontStyle = node.fontStyle;
    scene.textStyleId = node.textStyleId;
    scene.lineHeight = plain(node.lineHeight);
    scene.letterSpacing = plain(node.letterSpacing);
    scene.textAlignHorizontal = node.textAlignHorizontal;
    scene.textAlignVertical = node.textAlignVertical;
    scene.textAutoResize = node.textAutoResize;
    scene.textTruncation = node.textTruncation;
    scene.textDecoration = node.textDecoration;
    scene.textCase = node.textCase;
    scene.paragraphIndent = node.paragraphIndent;
    scene.paragraphSpacing = node.paragraphSpacing;
    scene.leadingTrim = node.leadingTrim;
    if (typeof node.getStyledTextSegments === 'function') {
      scene.textSegments = node.getStyledTextSegments([
        'fontName','fontSize','fills','textDecoration','letterSpacing','lineHeight','textCase','boundVariables',
      ]).map(segment => ({
        start: segment.start, end: segment.end, fontName: plain(segment.fontName), fontSize: segment.fontSize,
        fills: paints(segment.fills), textDecoration: segment.textDecoration, letterSpacing: plain(segment.letterSpacing),
        lineHeight: plain(segment.lineHeight), textCase: segment.textCase, boundVariables: plain(segment.boundVariables),
      }));
    }
  }
  if ('children' in node) scene.children = node.children.map(webSceneValue);
  return scene;
}

function webSceneHash(node) {
  const source = JSON.stringify(webSceneValue(node));
  const states = [2166136261, 2246822519, 3266489917, 668265263];
  for (let index = 0; index < source.length; index++) {
    const code = source.charCodeAt(index);
    for (let state = 0; state < states.length; state++) {
      states[state] = Math.imul(states[state] ^ (code + state * 31), 16777619 + state * 2) >>> 0;
    }
  }
  return `${source.length}:${states.map(value => value.toString(16).padStart(8, '0')).join('')}`;
}

function webNodePaint(node, element) {
  const paint = element.paint || {};
  if (paint.radialGradient) {
    const { centerX, centerY, stops } = paint.radialGradient;
    const width = Math.max(1, element.box.width);
    const height = Math.max(1, element.box.height);
    const radius = Math.max(
      Math.hypot(centerX * width, centerY * height),
      Math.hypot((1 - centerX) * width, centerY * height),
      Math.hypot(centerX * width, (1 - centerY) * height),
      Math.hypot((1 - centerX) * width, (1 - centerY) * height),
    );
    const radiusX = radius / width;
    const radiusY = radius / height;
    const fill = {
      type: 'GRADIENT_RADIAL',
      gradientTransform: [[2 * radiusX, 0, centerX - radiusX], [0, 2 * radiusY, centerY - radiusY]],
      gradientStops: stops.map(stop => {
        const value = webColor(stop.color);
        return { position: stop.position, color: { ...value.color, a: value.opacity } };
      }),
    };
    node.fills = paint.background ? [fill, webSolid(paint.background)] : [fill];
  }
  else if (paint.background) node.fills = [webSolid(paint.background)];
  else if (node.type === 'RECTANGLE' || node.type === 'FRAME' || node.type === 'COMPONENT') node.fills = [];
  if (paint.borderColor && paint.borderWidth > 0) {
    node.strokes = [webSolid(paint.borderColor)];
    node.strokeWeight = paint.borderWidth;
  }
  if (Number.isFinite(paint.borderRadius)) node.cornerRadius = Math.min(paint.borderRadius, element.box.width / 2, element.box.height / 2);
  if (Number.isFinite(paint.opacity)) node.opacity = paint.opacity;
}

function webImagePaint(node, element) {
  const paint = element.paint || {};
  if (Number.isFinite(paint.borderRadius)) node.cornerRadius = Math.min(paint.borderRadius, element.box.width / 2, element.box.height / 2);
  if (Number.isFinite(paint.opacity)) node.opacity = paint.opacity;
  if (paint.borderColor && paint.borderWidth > 0) {
    node.strokes = [webSolid(paint.borderColor)];
    node.strokeWeight = paint.borderWidth;
  }
}

function webFontStyle(text) {
  return ({ 100: 'Thin', 200: 'Extra Light', 300: 'Light', 400: 'Regular', 500: 'Medium',
    600: 'Semi Bold', 700: 'Bold', 800: 'Extra Bold', 900: 'Black' })[Number(text.fontWeight)] || 'Regular';
}

async function webResolveFonts(figma, screens) {
  const available = (await figma.listAvailableFontsAsync()).map(item => item.fontName);
  const requests = new Map();
  for (const screen of screens) for (const element of screen.elements) {
    if (element.kind !== 'text' && !(element.kind === 'component' && element.text) && element.kind !== 'annotation') continue;
    const text = element.kind === 'annotation' ? { fontFamily: 'Inter', fontWeight: 400 } : element.text;
    const family = text.fontFamily || 'Inter';
    const style = webFontStyle(text);
    const key = `${family}\0${style}`;
    if (!requests.has(key)) requests.set(key, { family, style, key, requestedWeight: text.fontWeight ?? 400 });
  }
  const resolved = new Map();
  const fontKey = value => String(value).normalize('NFKC').toLowerCase().replace(/[^a-z0-9]/g, '');
  for (const request of requests.values()) {
    const family = fontKey(request.family);
    const exact = available.find(font => fontKey(font.family) === family && fontKey(font.style) === fontKey(request.style));
    const familyRegular = available.find(font => fontKey(font.family) === family && fontKey(font.style) === 'regular');
    const fallback = exact || familyRegular
      || available.find(font => fontKey(font.family) === 'inter' && fontKey(font.style) === 'regular')
      || available.find(font => fontKey(font.style) === 'regular');
    if (!fallback) throw Error('No regular native font is available');
    await figma.loadFontAsync(fallback);
    const exactWeight = [100, 200, 300, 400, 500, 600, 700, 800, 900].includes(Number(request.requestedWeight));
    resolved.set(request.key, { font: fallback, fallback: exact && exactWeight ? null : {
      requested: { family: request.family, weight: request.requestedWeight }, used: fallback,
    } });
  }
  return resolved;
}

function webFontFor(element, fonts) {
  const text = element.kind === 'annotation' ? { fontFamily: 'Inter', fontWeight: 400 } : element.text;
  return fonts.get(`${text.fontFamily || 'Inter'}\0${webFontStyle(text)}`);
}

function webTextNode(figma, element, fonts, fallbackReport, layoutDrifts, created) {
  const text = element.kind === 'annotation'
    ? { characters: `Unsupported: ${element.label || element.id}`, fontFamily: 'Inter', fontWeight: 400, color: '#c02e25' }
    : element.text || {};
  const loaded = webFontFor(element, fonts);
  if (loaded.fallback) fallbackReport.push({ element_id: element.id, ...loaded.fallback });
  const node = figma.createText();
  created.add(node);
  node.fontName = loaded.font;
  node.characters = text.characters || '';
  if (Number.isFinite(text.fontSize) && text.fontSize > 0) node.fontSize = text.fontSize;
  if (Number.isFinite(text.lineHeight) && text.lineHeight > 0) node.lineHeight = { unit: 'PIXELS', value: text.lineHeight };
  const align = { left: 'LEFT', center: 'CENTER', right: 'RIGHT', justified: 'JUSTIFIED' }[String(text.textAlign || text.textAlignHorizontal || 'left').toLowerCase()];
  if (align) node.textAlignHorizontal = align;
  if (element.kind === 'component') node.textAlignVertical = 'CENTER';
  const color = text.color || element.paint?.color;
  if (color) node.fills = [webSolid(color)];
  node.textAutoResize = 'WIDTH_AND_HEIGHT';
  if (element.kind !== 'annotation') {
    const observedWidth = element.kind === 'component' ? webLabelBounds(element).width : element.box.width;
    const difference = node.width - observedWidth;
    if (Math.abs(difference) > 1) layoutDrifts.push({ element_id: element.id, observed_width: observedWidth, native_width: node.width, drift: difference });
  }
  return node;
}

function webTextAlignment(element) {
  return String(element.text?.textAlign || element.text?.textAlignHorizontal || 'left').toLowerCase();
}

function webLabelBounds(element) {
  return element.props?.labelBox || { x: 0, y: 0, width: element.box.width, height: element.box.height };
}

function webComponentFamily(element) {
  const bounds = webLabelBounds(element);
  const alignment = webTextAlignment(element);
  const horizontal = alignment === 'center' ? 0 : alignment === 'right'
    ? element.box.width - bounds.x - bounds.width : bounds.x;
  const verticalOffset = bounds.y + bounds.height / 2 - element.box.height / 2;
  const vertical = Math.abs(verticalOffset) <= 1 ? 'CENTER' : verticalOffset < 0 ? 'MIN' : 'MAX';
  const verticalPadding = vertical === 'MIN' ? bounds.y : vertical === 'MAX' ? element.box.height - bounds.y - bounds.height : 0;
  return JSON.stringify([element.componentKey, alignment, Number(horizontal.toFixed(2)), vertical, Number(verticalPadding.toFixed(2))]);
}

function webConfigureComponent(node, element) {
  if (!element.text) return;
  const alignment = webTextAlignment(element);
  const bounds = webLabelBounds(element);
  node.layoutMode = 'HORIZONTAL';
  node.primaryAxisSizingMode = 'FIXED';
  node.counterAxisSizingMode = 'FIXED';
  node.primaryAxisAlignItems = alignment === 'center' ? 'CENTER' : alignment === 'right' ? 'MAX' : 'MIN';
  node.counterAxisAlignItems = Math.abs(bounds.y + bounds.height / 2 - element.box.height / 2) <= 1
    ? 'CENTER' : bounds.y < element.box.height / 2 ? 'MIN' : 'MAX';
  node.paddingLeft = alignment === 'left' ? bounds.x : 0;
  node.paddingRight = alignment === 'right' ? element.box.width - bounds.x - bounds.width : 0;
  node.paddingTop = node.counterAxisAlignItems === 'MIN' ? bounds.y : 0;
  node.paddingBottom = node.counterAxisAlignItems === 'MAX' ? element.box.height - bounds.y - bounds.height : 0;
  node.itemSpacing = 0;
}

function webCreateElement(figma, element, fallbackReport, mains, assets) {
  if (element.kind === 'frame') return figma.createFrame();
  const family = element.kind === 'component' ? webComponentFamily(element) : null;
  if (family && mains.has(family)) {
    const main = mains.get(family);
    const instance = main.createInstance();
    instance.setPluginData(WEB_COMPONENT_MAIN, main.id);
    return instance;
  }
  if (family) {
    const node = figma.createComponent();
    webConfigureComponent(node, element);
    mains.set(family, node);
    return node;
  }
  if (element.kind === 'image') {
    const node = figma.createRectangle();
    node.fills = [{ type: 'IMAGE', imageHash: assets[element.asset.sha256], scaleMode: element.objectFit === 'contain' ? 'FIT' : 'FILL' }];
    return node;
  }
  if (element.kind === 'vector') return figma.createNodeFromSvg(element.svg);
  return figma.createRectangle();
}

function webNearestFrame(element, frameElements) {
  const path = Array.isArray(element.path) ? element.path : [];
  return frameElements
    .filter(frame => path.includes(frame.id))
    .sort((left, right) => (right.path?.length || 0) - (left.path?.length || 0))[0] || null;
}

function webPosition(node, element, parentElement) {
  if (node.type === 'TEXT') {
    const alignment = webTextAlignment(element);
    const offset = alignment === 'center' ? (element.box.width - node.width) / 2
      : alignment === 'right' ? element.box.width - node.width : 0;
    node.x = element.box.x + offset - (parentElement?.box.x || 0);
    node.y = element.box.y - (parentElement?.box.y || 0);
    return;
  }
  node.x = element.box.x - (parentElement?.box.x || 0);
  node.y = element.box.y - (parentElement?.box.y || 0);
  node.resize(Math.max(0.01, element.box.width), Math.max(0.01, element.box.height));
}

function webCreateTextOverride(instance, element, fonts, fallbackReport, layoutDrifts) {
  if (!element.text) return;
  const labels = instance.findAll(node => node.type === 'TEXT');
  if (labels.length !== 1) throw Error('Repeated component must expose exactly one text label for override');
  const loaded = webFontFor(element, fonts);
  if (loaded.fallback) fallbackReport.push({ element_id: element.id, ...loaded.fallback });
  labels[0].characters = element.text.characters || '';
  const observedWidth = webLabelBounds(element).width;
  const difference = labels[0].width - observedWidth;
  if (Math.abs(difference) > 1) layoutDrifts.push({ element_id: element.id, observed_width: observedWidth, native_width: labels[0].width, drift: difference });
}

function webCreateScreen(figma, screen, graph, created, baselines, fonts, x, images) {
  const fallbackReport = [];
  const layoutDrifts = [];
  const root = figma.createFrame();
  created.add(root);
  root.name = screen.title || screen.id;
  root.resize(screen.layout.width, screen.layout.height);
  root.x = x;
  root.y = 0;
  root.clipsContent = true;
  root.layoutMode = 'NONE';
  root.fills = screen.layout.background ? [webSolid(screen.layout.background)] : [];
  root.setPluginData(WEB_DESIGN_KEY, `${graph.graph_id}/${screen.id}`);
  root.setPluginData(WEB_DESIGN_HASH, graph.graph_sha256);
  figma.currentPage.appendChild(root);

  const frameElements = screen.elements.filter(element => element.kind === 'frame');
  const frames = new Map();
  for (const element of frameElements) {
    const frame = webCreateElement(figma, element, fallbackReport, new Map(), graph.assets);
    created.add(frame);
    frame.name = element.path?.join(' / ') || element.id;
    frame.clipsContent = false;
    frame.layoutMode = 'NONE';
    webNodePaint(frame, element);
    frames.set(element.id, frame);
  }

  const mains = new Map();
  for (const element of screen.elements) {
    const parentElement = webNearestFrame(element, frameElements);
    const parent = frames.get(parentElement?.id) || root;
    const family = element.kind === 'component' ? webComponentFamily(element) : null;
    const node = element.kind === 'frame' ? frames.get(element.id)
      : element.kind === 'text' || element.kind === 'annotation'
      ? webTextNode(figma, element, fonts, fallbackReport, layoutDrifts, created)
      : webCreateElement(figma, element, fallbackReport, mains, images);
    created.add(node);
    node.setPluginData(WEB_ELEMENT_ID, element.id);
    node.name = element.path?.join(' / ') || element.id;
    if (element.kind === 'component' && element.text && mains.get(family) === node) {
      const label = webTextNode(figma, element, fonts, fallbackReport, layoutDrifts, created);
      label.name = 'label';
      node.appendChild(label);
      label.layoutSizingHorizontal = 'HUG';
      label.layoutSizingVertical = 'HUG';
    }
    if (element.kind === 'component' && mains.get(family) === node) webNodePaint(node, element);
    if (element.kind === 'component' && mains.get(family) !== node && node.type === 'INSTANCE') webCreateTextOverride(node, element, fonts, fallbackReport, layoutDrifts);
    if (element.kind === 'image') webImagePaint(node, element);
    else if (element.kind !== 'text' && element.kind !== 'vector' && element.kind !== 'frame') webNodePaint(node, element);
    webPosition(node, element, parentElement);
    parent.appendChild(node);
  }
  const sceneHash = webSceneHash(root);
  root.setPluginData(WEB_SCENE_HASH, sceneHash);
  baselines.set(root, sceneHash);
  return {
    screen_id: screen.id,
    frame_id: root.id,
    reused: false,
    editable: true,
    editable_node_count: root.findAll(node => ['TEXT', 'RECTANGLE', 'FRAME', 'INSTANCE', 'COMPONENT'].includes(node.type)).length,
    fallbacks: fallbackReport,
    layout_drifts: layoutDrifts,
    unsupported: screen.elements.filter(element => element.kind === 'annotation').map(element => ({ element_id: element.id, label: element.label || element.id })),
    gradients: screen.elements.filter(element => element.paint?.radialGradient).map(element => ({ element_id: element.id, stop_count: element.paint.radialGradient.stops.length })),
    viewport: { width: screen.layout.width, height: screen.layout.height },
  };
}

function webRollback(created, baselines, synchronousFailure) {
  const roots = [...created].filter(node => {
    let parent = node.parent;
    while (parent) {
      if (created.has(parent)) return false;
      parent = parent.parent;
    }
    return true;
  });
  const conflicts = [];
  for (const node of roots.reverse()) {
    try {
      if (!synchronousFailure && (!baselines.has(node) || webSceneHash(node) !== baselines.get(node))) {
        conflicts.push(node.id);
        continue;
      }
      node.remove();
    } catch (_) {
      conflicts.push(node.id);
    }
  }
  return conflicts;
}

async function webBounded(promise, timeoutMs, message) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => { timer = setTimeout(() => reject(Error(message)), timeoutMs); }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function webResolveImages(figma, plan, screens) {
  const imageHashes = new Set(screens.flatMap(screen => screen.elements
    .filter(element => element.kind === 'image').map(element => element.asset.sha256)));
  const resolved = {};
  for (const hash of imageHashes) {
    nativeEditScope(figma, plan);
    const bytes = webDecodeBase64(plan.web_design.assets[hash]);
    const image = figma.createImage(bytes);
    const stored = figma.getImageByHash(image.hash);
    if (!stored || typeof stored.getSizeAsync !== 'function') throw Error(`Native image ${hash} is unavailable for decode verification`);
    const size = await webBounded(stored.getSizeAsync(), 10_000, `Timed out decoding native image ${hash}`);
    nativeEditScope(figma, plan);
    if (!size || !Number.isFinite(size.width) || !Number.isFinite(size.height) || size.width <= 0 || size.height <= 0) {
      throw Error(`Native image ${hash} decoded to invalid dimensions`);
    }
    resolved[hash] = image.hash;
  }
  return resolved;
}

async function webVerifyInstanceMains(figma, plan, frame) {
  nativeEditScope(figma, plan);
  const instances = frame.findAll(node => node.type === 'INSTANCE');
  const checks = instances.map(async instance => {
    const expected = instance.getPluginData(WEB_COMPONENT_MAIN);
    if (!expected || typeof instance.getMainComponentAsync !== 'function') throw Error('Imported instance main identity is not pinned');
    const main = await webBounded(instance.getMainComponentAsync(), 10_000, 'Timed out reading an imported instance main');
    if (!main || main.id !== expected) throw Error(`Imported instance ${instance.id} resolves to a different local main`);
    return { instance_id: instance.id, main_id: main.id };
  });
  const result = await Promise.all(checks);
  nativeEditScope(figma, plan);
  return result;
}

async function webRead(figma, plan) {
  nativeEditScope(figma, plan);
  const screens = await Promise.all(plan.web_design.screens.map(async screen => {
    const key = `${plan.web_design.graph_id}/${screen.id}`;
    const frame = figma.currentPage.children.find(node => node.getPluginData(WEB_DESIGN_KEY) === key);
    if (!frame) return { screen_id: screen.id, status: 'missing', frame_id: null, editable_node_count: 0 };
    const hashMatches = frame.getPluginData(WEB_DESIGN_HASH) === plan.web_design.graph_sha256;
    const sceneMatches = frame.getPluginData(WEB_SCENE_HASH) === webSceneHash(frame);
    let componentMains = [];
    try { componentMains = await webVerifyInstanceMains(figma, plan, frame); }
    catch (error) { return { screen_id: screen.id, status: 'changed', frame_id: frame.id, error: String(error.message || error) }; }
    return {
      screen_id: screen.id,
      status: hashMatches && sceneMatches ? 'current' : 'changed',
      frame_id: frame.id,
      editable_node_count: frame.findAll(node => ['TEXT', 'RECTANGLE', 'FRAME', 'INSTANCE', 'COMPONENT'].includes(node.type)).length,
      viewport: { width: frame.width, height: frame.height },
      scene_fingerprint: frame.getPluginData(WEB_SCENE_HASH),
      component_mains: componentMains,
    };
  }));
  nativeEditScope(figma, plan);
  return { schema: 'figma-flow-web-design-receipt-v1', graph_id: plan.web_design.graph_id, graph_sha256: plan.web_design.graph_sha256, screens };
}

async function webApply(figma, plan) {
  webValidate(plan);
  nativeEditScope(figma, plan);
  const page = figma.currentPage;
  const receipts = [];
  const created = new Set();
  const baselines = new Map();
  let synchronousFailure = true;
  let totalPreviewBytes = 0;
  try {
    const existingByScreen = new Map();
    for (const screen of plan.web_design.screens) {
      const stable = `${plan.web_design.graph_id}/${screen.id}`;
      const existing = page.children.find(node => node.getPluginData(WEB_DESIGN_KEY) === stable);
      if (existing) {
        if (existing.getPluginData(WEB_DESIGN_HASH) !== plan.web_design.graph_sha256
            || existing.getPluginData(WEB_SCENE_HASH) !== webSceneHash(existing)) {
          throw Error(`Owned frame ${screen.id} changed; preserving its current editable scene`);
        }
        existingByScreen.set(screen.id, { id: existing.id, scene: webSceneHash(existing) });
        await webVerifyInstanceMains(figma, plan, existing);
      }
    }
    const newScreens = plan.web_design.screens.filter(screen => !existingByScreen.has(screen.id));
    const [fonts, images] = await Promise.all([
      webResolveFonts(figma, newScreens),
      webResolveImages(figma, plan, newScreens),
    ]);
    nativeEditScope(figma, plan);
    for (const screen of plan.web_design.screens) {
      const stable = `${plan.web_design.graph_id}/${screen.id}`;
      const existing = page.children.find(node => node.getPluginData(WEB_DESIGN_KEY) === stable);
      const before = existingByScreen.get(screen.id);
      if ((before?.id || null) !== (existing?.id || null)
          || (existing && (existing.getPluginData(WEB_DESIGN_HASH) !== plan.web_design.graph_sha256
            || webSceneHash(existing) !== before.scene))) {
        throw Error(`Owned frame ${screen.id} changed during font preparation; preserving its current scene`);
      }
      if (existing) await webVerifyInstanceMains(figma, plan, existing);
    }
    for (const screen of plan.web_design.screens) {
      const stable = `${plan.web_design.graph_id}/${screen.id}`;
      const existing = page.children.find(node => node.getPluginData(WEB_DESIGN_KEY) === stable);
      if (existing) {
        receipts.push({
          screen_id: screen.id,
          frame_id: existing.id,
          reused: true,
          editable: true,
          editable_node_count: existing.findAll(node => ['TEXT', 'RECTANGLE', 'FRAME', 'INSTANCE', 'COMPONENT'].includes(node.type)).length,
          fallbacks: [],
          unsupported: [],
          gradients: [],
          viewport: { width: existing.width, height: existing.height },
        });
        continue;
      }
      const rightEdge = page.children.reduce((max, node) => {
        const bounds = node.absoluteBoundingBox;
        return Math.max(max, bounds ? bounds.x + bounds.width : node.x + node.width);
      }, 0);
      const x = rightEdge > 0 ? rightEdge + 160 : 0;
      receipts.push(webCreateScreen(figma, screen, plan.web_design, created, baselines, fonts, x, images));
    }
    synchronousFailure = false;
    const receipt = {
      schema: 'figma-flow-web-design-receipt-v1',
      graph_id: plan.web_design.graph_id,
      graph_sha256: plan.web_design.graph_sha256,
      screens: receipts,
    };
    const readback = await webBounded(nativeEditDiscovery(figma, plan), 30_000, 'Timed out during actual native discovery');
    nativeEditScope(figma, plan);
    for (const screen of receipts) {
      const frame = page.children.find(node => node.id === screen.frame_id);
      if (!frame || frame.type !== 'FRAME' || frame.getPluginData(WEB_DESIGN_KEY) !== `${plan.web_design.graph_id}/${screen.screen_id}`
          || frame.getPluginData(WEB_DESIGN_HASH) !== plan.web_design.graph_sha256
          || frame.getPluginData(WEB_SCENE_HASH) !== webSceneHash(frame)) {
        throw Error(`Actual editable frame readback failed for ${screen.screen_id}`);
      }
      screen.editable_node_count = frame.findAll(node => ['TEXT', 'RECTANGLE', 'FRAME', 'INSTANCE', 'COMPONENT'].includes(node.type)).length;
      if (screen.editable_node_count === 0) throw Error(`No editable native descendants in ${screen.screen_id}`);
      screen.component_mains = await webVerifyInstanceMains(figma, plan, frame);
      for (const gradient of screen.gradients) {
        const matches = frame.findAll(node => node.getPluginData(WEB_ELEMENT_ID) === gradient.element_id);
        if (matches.length !== 1 || !matches[0].fills?.some(fill => fill.type === 'GRADIENT_RADIAL' && fill.gradientStops?.length === gradient.stop_count)) {
          throw Error(`Actual radial gradient paint readback failed for ${gradient.element_id}`);
        }
      }
      if (plan.web_design.preview_width) {
        const requestedWidth = plan.web_design.preview_width;
        const maxPixels = 5_000_000;
        const scale = Math.min(requestedWidth / frame.width, Math.sqrt(maxPixels / (frame.width * frame.height)));
        const bytes = await frame.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: scale } });
        totalPreviewBytes += bytes.length;
        if (bytes.length > 8_000_000 || totalPreviewBytes > 8_000_000) throw Error(`Previews exceed the private 8 MB total limit at ${screen.screen_id}`);
        screen.preview = {
          mimeType: 'image/png',
          width: Math.round(frame.width * scale),
          height: Math.round(frame.height * scale),
          data: figma.base64Encode(bytes),
        };
      }
    }
    nativeEditScope(figma, plan);
    for (const screen of receipts) {
      const frame = page.children.find(node => node.id === screen.frame_id);
      if (!frame || frame.getPluginData(WEB_SCENE_HASH) !== webSceneHash(frame)) throw Error(`Frame changed during preview export: ${screen.screen_id}`);
    }
    return { receipt, readback };
  } catch (error) {
    error.webDesignRollbackConflicts = webRollback(created, baselines, synchronousFailure);
    error.rollback_conflicts = error.webDesignRollbackConflicts.map(id => ({ node_id: id, reason: 'Changed after creation; preserved during rollback' }));
    throw error;
  }
}
