const WEB_DESIGN_KEY = 'figma-flow-web-design-id';
const WEB_DESIGN_HASH = 'figma-flow-web-design-sha256';
const WEB_SCENE_HASH = 'figma-flow-web-scene-fingerprint';
const WEB_COMPONENT_MAIN = 'figma-flow-web-component-main-id';
const WEB_ELEMENT_ID = 'figma-flow-web-element-id';
const WEB_TEXT_STYLE = 'figma-flow-web-text-style-v1';
const WEB_AVAILABLE_FONT_CACHE = new WeakMap();

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

function webSceneValue(node, includeTextStyle = true) {
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
  if (includeTextStyle) scene.webTextStyle = node.getPluginData?.(WEB_TEXT_STYLE) || null;
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
  if ('children' in node) scene.children = node.children.map(child => webSceneValue(child, includeTextStyle));
  return scene;
}

function webSceneHash(node, includeTextStyle = true) {
  const scene = webSceneValue(node, includeTextStyle);
  const source = JSON.stringify(scene);
  const states = [2166136261, 2246822519, 3266489917, 668265263];
  for (let index = 0; index < source.length; index++) {
    const code = source.charCodeAt(index);
    for (let state = 0; state < states.length; state++) {
      states[state] = Math.imul(states[state] ^ (code + state * 31), 16777619 + state * 2) >>> 0;
    }
  }
  return `${source.length}:${states.map(value => value.toString(16).padStart(8, '0')).join('')}`;
}

function webSceneMatches(node) {
  const stored = node.getPluginData(WEB_SCENE_HASH);
  return stored === webSceneHash(node) || stored === webSceneHash(node, false);
}

function webNodePaint(node, element) {
  const paint = element.paint || {};
  if (paint.radialGradient) {
    const { centerX, centerY, stops } = paint.radialGradient;
    // CSS's default ellipse touches the farthest corner. Figma maps
    // normalized layer coordinates into gradient space, centered at (½, ½).
    const radiusX = Math.SQRT2 * Math.max(centerX, 1 - centerX);
    const radiusY = Math.SQRT2 * Math.max(centerY, 1 - centerY);
    const scaleX = 0.5 / radiusX;
    const scaleY = 0.5 / radiusY;
    const fill = {
      type: 'GRADIENT_RADIAL',
      gradientTransform: [[scaleX, 0, 0.5 - centerX * scaleX], [0, scaleY, 0.5 - centerY * scaleY]],
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

function webResolveFontMap(available, screens) {
  if (!Array.isArray(available) || available.length > 20000) throw Error('Figma font list exceeds the bounded typography verification limit');
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
  const fontKey = value => String(value).normalize('NFKC').toLowerCase().replace(/[\s_-]/g, '');
  for (const request of requests.values()) {
    const family = fontKey(request.family);
    const exact = available.find(font => fontKey(font.family) === family && fontKey(font.style) === fontKey(request.style));
    const familyRegular = available.find(font => fontKey(font.family) === family && fontKey(font.style) === 'regular');
    const resolvedFamily = family === 'geistsans' ? 'geist' : family;
    const alias = resolvedFamily !== family && available.find(font => fontKey(font.family) === resolvedFamily && fontKey(font.style) === fontKey(request.style));
    const fallback = exact || alias || familyRegular
      || available.find(font => fontKey(font.family) === 'inter' && fontKey(font.style) === 'regular')
      || available.find(font => fontKey(font.style) === 'regular');
    if (!fallback) throw Error('No regular native font is available');
    const exactWeight = [100, 200, 300, 400, 500, 600, 700, 800, 900].includes(Number(request.requestedWeight));
    resolved.set(request.key, { font: fallback, fallback: exact && exactWeight ? null : {
      requested: { family: request.family, weight: request.requestedWeight }, used: fallback,
    } });
  }
  return resolved;
}

async function webAvailableFonts(figma) {
  if (WEB_AVAILABLE_FONT_CACHE.has(figma)) return WEB_AVAILABLE_FONT_CACHE.get(figma);
  const rows = await figma.listAvailableFontsAsync();
  if (!Array.isArray(rows) || rows.length > 20000
      || rows.some(row => !row?.fontName || typeof row.fontName.family !== 'string' || typeof row.fontName.style !== 'string')) {
    throw Error('Figma font list exceeds the bounded typography verification limit');
  }
  const fonts = rows.map(row => row.fontName);
  WEB_AVAILABLE_FONT_CACHE.set(figma, fonts);
  return fonts;
}

async function webResolveFonts(figma, screens) {
  if (!screens.length) return new Map();
  const available = await webAvailableFonts(figma);
  const resolved = webResolveFontMap(available, screens);
  await Promise.all([...resolved.values()].map(row => figma.loadFontAsync(row.font)));
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
  node.setPluginData(WEB_TEXT_STYLE, webTextStyleRecord(element, loaded.font));
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

function webComponentFamily(element, fonts) {
  const bounds = webLabelBounds(element);
  const alignment = webTextAlignment(element);
  const horizontal = alignment === 'center' ? 0 : alignment === 'right'
    ? element.box.width - bounds.x - bounds.width : bounds.x;
  const verticalOffset = bounds.y + bounds.height / 2 - element.box.height / 2;
  const vertical = Math.abs(verticalOffset) <= 1 ? 'CENTER' : verticalOffset < 0 ? 'MIN' : 'MAX';
  const verticalPadding = vertical === 'MIN' ? bounds.y : vertical === 'MAX' ? element.box.height - bounds.y - bounds.height : 0;
  const text = element.text || {};
  const loaded = element.text ? webFontFor(element, fonts)?.font : null;
  const paint = element.paint || {};
  const textColor = text.color || paint.color || null;
  return JSON.stringify({
    componentKey: element.componentKey,
    layout: [alignment, Number(horizontal.toFixed(2)), vertical, Number(verticalPadding.toFixed(2)),
      Number(bounds.height.toFixed(2))],
    typography: element.text ? {
      fontFamily: loaded?.family || text.fontFamily || 'Inter',
      fontStyle: loaded?.style || webFontStyle(text),
      fontSize: Number.isFinite(text.fontSize) ? text.fontSize : null,
      fontWeight: Number.isFinite(Number(text.fontWeight)) ? Number(text.fontWeight) : 400,
      lineHeight: Number.isFinite(text.lineHeight) ? text.lineHeight : null,
      letterSpacing: Number.isFinite(text.letterSpacing) ? text.letterSpacing : null,
      textAlign: alignment,
      color: textColor,
    } : null,
    paint: {
      background: paint.background || null,
      borderColor: paint.borderColor || null,
      borderWidth: paint.borderWidth || 0,
      borderRadius: paint.borderRadius || 0,
      opacity: paint.opacity ?? 1,
      radialGradient: paint.radialGradient || null,
    },
  });
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

function webCreateElement(figma, element, fallbackReport, mains, assets, fonts) {
  if (element.kind === 'frame') return figma.createFrame();
  const family = element.kind === 'component' ? webComponentFamily(element, fonts) : null;
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
  webVerifyTextTypography(labels[0], element, loaded.font);
  labels[0].setPluginData(WEB_TEXT_STYLE, webTextStyleRecord(element, loaded.font));
  const observedWidth = webLabelBounds(element).width;
  const difference = labels[0].width - observedWidth;
  if (Math.abs(difference) > 1) layoutDrifts.push({ element_id: element.id, observed_width: observedWidth, native_width: labels[0].width, drift: difference });
}

function webTextInput(element) {
  return element.kind === 'annotation'
    ? { characters: `Unsupported: ${element.label || element.id}`, fontFamily: 'Inter', fontWeight: 400, color: '#c02e25' }
    : element.text || {};
}

function webTextStyleSpec(element) {
  const text = webTextInput(element);
  return {
    fontFamily: text.fontFamily || 'Inter', fontStyle: webFontStyle(text),
    fontSize: Number.isFinite(text.fontSize) ? text.fontSize : null,
    fontWeight: Number.isFinite(Number(text.fontWeight)) ? Number(text.fontWeight) : 400,
    lineHeight: Number.isFinite(text.lineHeight) ? text.lineHeight : null,
    letterSpacing: Number.isFinite(text.letterSpacing) ? text.letterSpacing : null,
    textAlignHorizontal: ({ left: 'LEFT', center: 'CENTER', right: 'RIGHT', justified: 'JUSTIFIED',
      start: 'LEFT', end: 'RIGHT' })[String(text.textAlign || text.textAlignHorizontal || 'left').toLowerCase()] || 'LEFT',
    color: text.color || element.paint?.color || null,
  };
}

function webTextStyleRecord(element, font) {
  return JSON.stringify({ schema: 1, element_id: element.id, requested: webTextStyleSpec(element),
    native_font: { family: font.family, style: font.style } });
}

function webStoredTextFont(textNode, element) {
  const raw = textNode.getPluginData(WEB_TEXT_STYLE);
  if (!raw) return null;
  let record;
  try { record = JSON.parse(raw); }
  catch (_) { throw Error(`Stored component text style metadata is invalid for ${element.id}`); }
  if (!record || record.schema !== 1 || record.element_id !== element.id
      || JSON.stringify(record.requested) !== JSON.stringify(webTextStyleSpec(element))
      || typeof record.native_font?.family !== 'string' || typeof record.native_font?.style !== 'string') {
    throw Error(`Stored component text style metadata differs from the canonical graph for ${element.id}`);
  }
  return record.native_font;
}

function webVerifyTextTypography(textNode, element, expectedFont) {
  if (!textNode.characters.length) return;
  const start = 0, end = textNode.characters.length;
  const font = textNode.getRangeFontName(start, end);
  if (font === figma.mixed || font.family !== expectedFont.family || font.style !== expectedFont.style) {
    throw Error(`Imported component text font differs from the captured typography for ${element.id}`);
  }
  const expectedText = webTextInput(element);
  if (Number.isFinite(expectedText.fontSize)) {
    const fontSize = textNode.getRangeFontSize(start, end);
    if (fontSize === figma.mixed || Math.abs(fontSize - expectedText.fontSize) > 0.01) {
      throw Error(`Imported component text size differs from the captured typography for ${element.id}`);
    }
  }
  if (Number.isFinite(expectedText.lineHeight) && expectedText.lineHeight > 0) {
    const lineHeight = textNode.getRangeLineHeight(start, end);
    if (lineHeight === figma.mixed || lineHeight.unit !== 'PIXELS'
        || Math.abs(lineHeight.value - expectedText.lineHeight) > 0.01) {
      throw Error(`Imported component text line height differs from the captured typography for ${element.id}`);
    }
  }
  const color = expectedText.color || element.paint?.color;
  if (color) {
    const actual = textNode.getRangeFills(start, end);
    const solid = actual === figma.mixed ? null : actual.find(paint => paint.type === 'SOLID');
    const expected = webColor(color);
    if (!solid || Math.abs(solid.color.r - expected.color.r) > 0.001
        || Math.abs(solid.color.g - expected.color.g) > 0.001
        || Math.abs(solid.color.b - expected.color.b) > 0.001
        || Math.abs((solid.opacity ?? 1) - expected.opacity) > 0.001) {
      throw Error(`Imported component text fill differs from the captured typography for ${element.id}`);
    }
  }
  const expectedAlignment = ({ left: 'LEFT', center: 'CENTER', right: 'RIGHT', justified: 'JUSTIFIED',
    start: 'LEFT', end: 'RIGHT' })[
    String(expectedText.textAlign || expectedText.textAlignHorizontal || 'left').toLowerCase()];
  if (expectedAlignment && textNode.textAlignHorizontal !== expectedAlignment) {
    throw Error(`Imported component text alignment differs from the captured typography for ${element.id}`);
  }
}

async function webVerifyScreenTypography(figma, plan, frame, screen) {
  if (!Array.isArray(screen.elements) || screen.elements.length > 1500) {
    throw Error(`Typography verification scope is invalid for ${screen.id}`);
  }
  const elementsById = new Map();
  for (const node of frame.findAll(child => Boolean(child.getPluginData(WEB_ELEMENT_ID)))) {
    const elementId = node.getPluginData(WEB_ELEMENT_ID);
    if (elementsById.has(elementId)) throw Error(`Duplicate owned element ID ${elementId} in ${screen.id}`);
    elementsById.set(elementId, node);
  }
  const checks = [];
  for (const element of screen.elements) {
    if (element.kind !== 'text' && element.kind !== 'annotation'
        && !(element.kind === 'component' && element.text)) continue;
    const owned = elementsById.get(element.id);
    if (!owned) throw Error(`Owned text element ${element.id} is missing from ${screen.id}`);
    let textNode = owned;
    if (element.kind === 'component') {
      const labels = owned.findAll(node => node.type === 'TEXT');
      if (labels.length !== 1) throw Error(`Component label count differs from the graph for ${element.id}`);
      textNode = labels[0];
    }
    if (textNode.type !== 'TEXT') throw Error(`Owned text element ${element.id} changed native type`);
    const nativeFont = webStoredTextFont(textNode, element);
    if (nativeFont) {
      webVerifyTextTypography(textNode, element, nativeFont);
      continue;
    }
    const requested = webTextStyleSpec(element);
    const length = textNode.characters.length;
    const observedFont = length ? textNode.getRangeFontName(0, length) : null;
    if (observedFont && observedFont !== figma.mixed
        && observedFont.family === requested.fontFamily && observedFont.style === requested.fontStyle) {
      webVerifyTextTypography(textNode, element,
        { family: requested.fontFamily, style: requested.fontStyle });
    } else {
      checks.push({ textNode, element });
    }
  }
  if (checks.length) {
    const fonts = webResolveFontMap(await webAvailableFonts(figma),
      [{ elements: checks.map(check => check.element) }]);
    nativeEditScope(figma, plan);
    for (const check of checks) {
      const expected = webFontFor(check.element, fonts);
      if (!expected) throw Error(`No verified native font is available for ${check.element.id}`);
      webVerifyTextTypography(check.textNode, check.element, expected.font);
    }
  }
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
    frame.clipsContent = element.clipsContent === true;
    frame.layoutMode = 'NONE';
    webNodePaint(frame, element);
    frames.set(element.id, {frame, element});
  }

  const mains = new Map();
  for (const element of screen.elements) {
    const path = element.path || [];
    const owner = frames.get(path[path.length - 1]);
    const parentElement = owner?.element;
    const parent = owner?.frame || root;
    const family = element.kind === 'component' ? webComponentFamily(element, fonts) : null;
    const node = element.kind === 'frame' ? frames.get(element.id).frame
      : element.kind === 'text' || element.kind === 'annotation'
      ? webTextNode(figma, element, fonts, fallbackReport, layoutDrifts, created)
      : webCreateElement(figma, element, fallbackReport, mains, images, fonts);
    created.add(node);
    node.setPluginData(WEB_ELEMENT_ID, element.id);
    const label = element.name || element.text?.characters || element.label || element.kind;
    node.name = label.slice(0, 100) + ' · ' + element.id;
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
    const sceneMatches = webSceneMatches(frame);
    let componentMains = [];
    try {
      componentMains = await webVerifyInstanceMains(figma, plan, frame);
      await webVerifyScreenTypography(figma, plan, frame, screen);
    }
    catch (error) {
      return { screen_id: screen.id, status: 'changed', frame_id: frame.id,
        error: `${String(error.message || error)}. Existing frame was preserved; use a new graph ID for a corrected import.` };
    }
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
            || !webSceneMatches(existing)) {
          throw Error(`Owned frame ${screen.id} changed; preserving its current editable scene`);
        }
        existingByScreen.set(screen.id, { id: existing.id, scene: webSceneHash(existing) });
        await webVerifyInstanceMains(figma, plan, existing);
        try { await webVerifyScreenTypography(figma, plan, existing, screen); }
        catch (error) {
          throw Error(`Owned frame ${screen.id} text style differs from the canonical graph; preserving it. Use a new graph ID to create a corrected frame. ${String(error.message || error)}`);
        }
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
            || !webSceneMatches(existing) || webSceneHash(existing) !== before.scene))) {
        throw Error(`Owned frame ${screen.id} changed during font preparation; preserving its current scene`);
      }
      if (existing) {
        await webVerifyInstanceMains(figma, plan, existing);
        try { await webVerifyScreenTypography(figma, plan, existing, screen); }
        catch (error) {
          throw Error(`Owned frame ${screen.id} text style differs from the canonical graph; preserving it. Use a new graph ID to create a corrected frame. ${String(error.message || error)}`);
        }
      }
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
          || !webSceneMatches(frame)) {
        throw Error(`Actual editable frame readback failed for ${screen.screen_id}`);
      }
      await webVerifyScreenTypography(figma, plan,
        frame, plan.web_design.screens.find(item => item.id === screen.screen_id));
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
      if (!frame || !webSceneMatches(frame)) throw Error(`Frame changed during preview export: ${screen.screen_id}`);
    }
    return { receipt, readback };
  } catch (error) {
    error.webDesignRollbackConflicts = webRollback(created, baselines, synchronousFailure);
    error.rollback_conflicts = error.webDesignRollbackConflicts.map(id => ({ node_id: id, reason: 'Changed after creation; preserved during rollback' }));
    throw error;
  }
}
