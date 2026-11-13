const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../figma-bridge/web_design.js'), 'utf8');
const captureSource = fs.readFileSync(require.resolve('../tools/web_design_capture.js'), 'utf8');
let corruptInstanceLineHeight = false;

let nextId = 1;
class MockNode {
  constructor(type) {
    this.id = String(nextId++);
    this.type = type;
    this.name = type;
    this.geometryWrites = 0;
    this._x = 0;
    this._y = 0;
    this.width = 0;
    this.height = 0;
    this.opacity = 1;
    this.isMask = false;
    this.maskType = 'ALPHA';
    this.fills = [];
    this.strokes = [];
    this.children = [];
    this.data = {};
    Object.defineProperties(this, {
      x: { get: () => this._x, set: value => { if (this.parent?.type === 'INSTANCE') throw Error('relative-transform cannot be overridden in an instance'); this.geometryWrites++; this._x = value; } },
      y: { get: () => this._y, set: value => { if (this.parent?.type === 'INSTANCE') throw Error('relative-transform cannot be overridden in an instance'); this.geometryWrites++; this._y = value; } },
      characters: { get: () => this._characters, set: value => { this._characters = value; if (this.type === 'TEXT' && this.textAutoResize === 'WIDTH_AND_HEIGHT') this.width = String(value).length * (this.fontSize || 14) * 0.5; } },
      fontSize: { get: () => this._fontSize, set: value => { this._fontSize = value; if (this.type === 'TEXT' && this.textAutoResize === 'WIDTH_AND_HEIGHT') this.width = String(this._characters || '').length * value * 0.5; } },
      textAutoResize: { get: () => this._textAutoResize, set: value => { this._textAutoResize = value; if (this.type === 'TEXT' && value === 'WIDTH_AND_HEIGHT') this.width = String(this._characters || '').length * (this.fontSize || 14) * 0.5; } },
      layoutSizingHorizontal: { get: () => this._layoutSizingHorizontal, set: value => { if (!this.parent || !this.parent.layoutMode || this.parent.layoutMode === 'NONE') throw Error('layout sizing requires an auto-layout parent'); this._layoutSizingHorizontal = value; } },
      layoutSizingVertical: { get: () => this._layoutSizingVertical, set: value => { if (!this.parent || !this.parent.layoutMode || this.parent.layoutMode === 'NONE') throw Error('layout sizing requires an auto-layout parent'); this._layoutSizingVertical = value; } },
    });
  }
  resize(width, height) { if (this.parent?.type === 'INSTANCE') throw Error('relative-transform cannot be overridden in an instance'); this.geometryWrites++; this.width = width; this.height = height; }
  appendChild(node) {
    if (node.parent) node.parent.children = node.parent.children.filter(child => child !== node);
    node.parent = this;
    if (this.type === 'INSTANCE') node.geometryWrites = 0;
    this.children.push(node);
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
  }
  setPluginData(key, value) { this.data[key] = value; }
  getPluginData(key) { return this.data[key] || ''; }
  findAll(predicate) {
    return this.children.flatMap(child => [ ...(predicate(child) ? [child] : []), ...child.findAll(predicate) ]);
  }
  createInstance() {
    const instance = new MockNode('INSTANCE');
    instance._mainComponent = this;
    instance.layoutMode = this.layoutMode;
    instance.primaryAxisAlignItems = this.primaryAxisAlignItems;
    instance.counterAxisAlignItems = this.counterAxisAlignItems;
    instance.resize(this.width, this.height);
    for (const child of this.children) instance.appendChild(cloneNode(child));
    return instance;
  }
  get mainComponent() { throw Error('Cannot call with documentAccess: dynamic-page. Use getMainComponentAsync instead.'); }
  async getMainComponentAsync() { return this._mainComponent || null; }
  getRangeFontName() { return this.fontName; }
  getRangeFontSize() { return this.fontSize; }
  getRangeLineHeight() {
    if (corruptInstanceLineHeight && this.parent?.type === 'INSTANCE' && this.lineHeight?.unit === 'PIXELS') {
      return { ...this.lineHeight, value: this.lineHeight.value + 4 };
    }
    return this.lineHeight;
  }
  getRangeFills() { return this.fills; }
  get absoluteBoundingBox() { return { x: this.x, y: this.y, width: this.width, height: this.height }; }
}

function cloneNode(original) {
  const copy = new MockNode(original.type);
  for (const key of ['name', 'x', 'y', 'width', 'height', 'opacity', 'fills', 'strokes', 'strokeWeight', 'cornerRadius', 'characters', 'fontName', 'fontSize', 'lineHeight', 'textAlignHorizontal', 'textAlignVertical', 'textAutoResize']) {
    if (original[key] !== undefined) copy[key] = structuredClone(original[key]);
  }
  for (const child of original.children) copy.appendChild(cloneNode(child));
  return copy;
}

function harness(discovery = async () => ({ schema: 'figma-flow-graph-native-discovery-v1' })) {
  nextId = 1;
  const page = new MockNode('PAGE');
  page.id = '1:1';
  const fonts = [{ fontName: { family: 'Inter', style: 'Regular' } }, { fontName: { family: 'Inter', style: 'Medium' } }];
  const images = [];
  const videos = [];
  const imageSizeReads = [];
  const timeline = [];
  let fontListReads = 0;
  let fontLoads = 0;
  const figma = {
    fileKey: 'file', currentPage: page,
    createFrame: () => { timeline.push('frame'); return new MockNode('FRAME'); },
    createComponent: () => new MockNode('COMPONENT'),
    createText: () => new MockNode('TEXT'),
    createRectangle: () => new MockNode('RECTANGLE'),
    createNodeFromSvg: () => new MockNode('VECTOR'),
    createImage(bytes) {
      const signature = Array.from(bytes).join(',');
      images.push(signature);
      return { hash: `image-${signature}` };
    },
    async createVideoAsync(bytes) { const video = { hash: `video-${videos.length + 1}` }; videos.push({ bytes: Array.from(bytes), video }); return video; },
    getVideoByHash(hash) { return videos.find(item => item.video.hash === hash)?.video || null; },
    getImageByHash(hash) {
      return { async getSizeAsync() { imageSizeReads.push(hash); timeline.push('image-ready'); return { width: 2, height: 2 }; } };
    },
    async listAvailableFontsAsync() { fontListReads++; return fonts; },
    async loadFontAsync() { fontLoads++; },
  };
  const context = vm.createContext({ figma, nativeEditScope: () => {}, nativeEditDiscovery: discovery, setTimeout, clearTimeout });
  vm.runInContext(source, context);
  return { figma, page, fonts, images, videos, imageSizeReads, timeline,
    apply: plan => context.webApply(figma, plan),
    read: plan => context.webRead(figma, plan),
    sceneHash: (node, includeTextStyle = true) => context.webSceneHash(node, includeTextStyle),
    sceneHashLegacy: (node, includeTextStyle = true) => context.webSceneHash(node, includeTextStyle, false),
    counts: () => ({ fontListReads, fontLoads }),
    corruptInstances: value => { corruptInstanceLineHeight = value; } };
}

function plan() {
  const imageHash = 'c'.repeat(64);
  const raster = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).toString('base64');
  return {
    schema: 'figma-flow-native-edit-plan-v1', file_key: 'file', page_id: '1:1',
    web_design: {
      schema: 'figma-flow-web-design-v1', graph_id: 'saas-capture', graph_sha256: 'a'.repeat(64), assets: { [imageHash]: raster },
      screens: [{ id: 'WEB-signup', title: 'Signup', layout: { width: 390, height: 720, background: '#ffffff80' }, elements: [
        { id: 'cta-main', kind: 'component', componentKey: 'primary-button', box: { x: 20, y: 100, width: 240, height: 36 }, props: { labelBox: { x: 32, y: 8, width: 176, height: 20 } }, paint: { background: '#e7000b', borderRadius: 8 }, text: { characters: 'Create an account', fontFamily: 'Inter', fontSize: 14, fontWeight: 500, lineHeight: 20, textAlignHorizontal: 'center', color: '#ffffff' } },
        { id: 'cta-instance', kind: 'component', componentKey: 'primary-button', box: { x: 20, y: 152, width: 190, height: 36 }, props: { labelBox: { x: 12, y: 8, width: 166, height: 20 } }, paint: { background: '#e7000b', borderRadius: 8 }, text: { characters: 'Join now', fontFamily: 'Inter', fontSize: 14, fontWeight: 500, lineHeight: 20, textAlignHorizontal: 'center', color: '#ffffff' } },
        { id: 'logo-a', kind: 'image', box: { x: 20, y: 220, width: 32, height: 32 }, objectFit: 'contain', asset: { sha256: imageHash, mimeType: 'image/png' } },
        { id: 'logo-b', kind: 'image', box: { x: 60, y: 220, width: 32, height: 32 }, objectFit: 'cover', asset: { sha256: imageHash, mimeType: 'image/png' } },
      ] }],
    },
  };
}

function legacyImportedFrame(harnessState, sourcePlan, nativeFont = { family: 'Inter', style: 'Medium' }) {
  const screen = sourcePlan.web_design.screens[0];
  const page = harnessState.page;
  const root = new MockNode('FRAME');
  root.name = screen.title;
  root.resize(screen.layout.width, screen.layout.height);
  root.layoutMode = 'NONE';
  root.clipsContent = true;
  root.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 }, opacity: 128 / 255 }];
  root.setPluginData('figma-flow-web-design-id', `${sourcePlan.web_design.graph_id}/${screen.id}`);
  root.setPluginData('figma-flow-web-design-sha256', sourcePlan.web_design.graph_sha256);
  const elements = screen.elements.filter(element => element.kind === 'component');
  const main = new MockNode('COMPONENT');
  main.name = 'Legacy component main';
  main.resize(elements[0].box.width, elements[0].box.height);
  main.layoutMode = 'HORIZONTAL';
  main.primaryAxisAlignItems = 'CENTER';
  main.counterAxisAlignItems = 'CENTER';
  main.setPluginData('figma-flow-web-element-id', elements[0].id);
  const mainLabel = new MockNode('TEXT');
  mainLabel.name = 'label';
  mainLabel.characters = elements[0].text.characters;
  mainLabel.fontName = nativeFont;
  mainLabel.fontSize = elements[0].text.fontSize;
  mainLabel.lineHeight = { unit: 'PIXELS', value: 20 };
  mainLabel.letterSpacing = { unit: 'PIXELS', value: 0 };
  mainLabel.textAlignHorizontal = 'CENTER';
  mainLabel.textAutoResize = 'WIDTH_AND_HEIGHT';
  mainLabel.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 }, opacity: 1 }];
  main.appendChild(mainLabel);
  root.appendChild(main);

  const instance = new MockNode('INSTANCE');
  instance.name = 'Legacy component instance';
  instance._mainComponent = main;
  instance.resize(elements[1].box.width, elements[1].box.height);
  instance.setPluginData('figma-flow-web-component-main-id', main.id);
  instance.setPluginData('figma-flow-web-element-id', elements[1].id);
  const instanceLabel = new MockNode('TEXT');
  instanceLabel.name = 'label';
  instanceLabel.characters = elements[1].text.characters;
  instanceLabel.fontName = nativeFont;
  instanceLabel.fontSize = elements[1].text.fontSize;
  instanceLabel.lineHeight = { unit: 'PIXELS', value: 20 };
  instanceLabel.letterSpacing = { unit: 'PIXELS', value: 0 };
  instanceLabel.textAlignHorizontal = 'CENTER';
  instanceLabel.textAutoResize = 'WIDTH_AND_HEIGHT';
  instanceLabel.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 }, opacity: 1 }];
  instance.appendChild(instanceLabel);
  root.appendChild(instance);
  page.appendChild(root);
  root.setPluginData('figma-flow-web-scene-fingerprint', harnessState.sceneHashLegacy(root, false));
  return root;
}

test('repeated native components retain the main label and override different instance text', async () => {
  corruptInstanceLineHeight = false;
  const h = harness();
  const result = await h.apply(plan());
  const root = h.page.children[0];
  const main = root.children.find(node => node.type === 'COMPONENT');
  const instance = root.children.find(node => node.type === 'INSTANCE');
  assert.equal(main.findAll(node => node.type === 'TEXT').length, 1);
  assert.equal(main.findAll(node => node.type === 'TEXT')[0].characters, 'Create an account');
  assert.equal(main.layoutMode, 'HORIZONTAL');
  assert.equal(main.primaryAxisAlignItems, 'CENTER');
  assert.equal(instance.findAll(node => node.type === 'TEXT').length, 1);
  assert.equal(instance.findAll(node => node.type === 'TEXT')[0].characters, 'Join now');
  assert.equal(instance.findAll(node => node.type === 'TEXT')[0].x, main.findAll(node => node.type === 'TEXT')[0].x);
  assert.equal(instance.findAll(node => node.type === 'TEXT')[0].width, 'Join now'.length * 7);
  assert.equal(instance.findAll(node => node.type === 'TEXT')[0].geometryWrites, 0);
  assert.equal(root.fills[0].opacity, 128 / 255);
  assert.equal(result.receipt.screens[0].editable_node_count, 6);
  assert.equal(h.images.length, 1);
  assert.equal(h.imageSizeReads.length, 1);
  assert.ok(h.timeline.indexOf('image-ready') < h.timeline.indexOf('frame'));
  const nativeImages = root.children.filter(node => node.fills?.[0]?.type === 'IMAGE');
  assert.equal(nativeImages.length, 2);
  assert.equal(nativeImages[0].fills[0].imageHash, nativeImages[1].fills[0].imageHash);
  assert.equal(nativeImages[0].fills[0].scaleMode, 'FIT');
  assert.equal(nativeImages[1].fills[0].scaleMode, 'FILL');
  const fontsReadBeforeReuse = h.counts().fontListReads;
  assert.equal((await h.apply(plan())).receipt.screens[0].reused, true);
  assert.equal(h.counts().fontListReads, fontsReadBeforeReuse);
  assert.equal(h.images.length, 1);
  instance.findAll(node => node.type === 'TEXT')[0].characters = 'User edit';
  await assert.rejects(() => h.apply(plan()), /changed/);
  assert.equal(h.page.children.length, 1);
});

test('component family separates materially different native line heights', async () => {
  corruptInstanceLineHeight = false;
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements[1].text.lineHeight = 24;
  const result = await h.apply(data);
  const root = h.page.children[0];
  const mains = root.children.filter(node => node.type === 'COMPONENT');
  assert.equal(mains.length, 2);
  assert.equal(root.children.some(node => node.type === 'INSTANCE'), false);
  assert.deepEqual(mains.map(node => node.findAll(child => child.type === 'TEXT')[0].lineHeight.value).sort(), [20, 24]);
  assert.equal(result.receipt.screens[0].editable_node_count > 0, true);
});

test('reused component instance text style is checked before accepting the screen', async () => {
  const h = harness();
  h.corruptInstances(true);
  await assert.rejects(() => h.apply(plan()), /line height differs from the captured typography/);
  assert.equal(h.page.children.length, 0);
  corruptInstanceLineHeight = false;
});

test('v0.30 scene fingerprint compatibility rejects legacy or newly edited mask state', async () => {
  const h = harness();
  const sourcePlan = plan();
  const legacy = legacyImportedFrame(h, sourcePlan);
  assert.equal((await h.read(sourcePlan)).screens[0].status, 'current');
  const addedMask = new MockNode('RECTANGLE');
  addedMask.isMask = true;
  legacy.appendChild(addedMask);
  assert.equal((await h.read(sourcePlan)).screens[0].status, 'changed');

  const current = harness();
  const currentPlan = plan();
  await current.apply(currentPlan);
  const root = current.page.children[0];
  assert.equal(root.getPluginData('figma-flow-web-scene-version'), '2');
  root.maskType = 'VECTOR';
  assert.equal((await current.read(currentPlan)).screens[0].status, 'changed');
  root.setPluginData('figma-flow-web-scene-version', '');
  assert.equal((await current.read(currentPlan)).screens[0].status, 'changed');
});

test('legacy reused components with canonical line-height drift are changed and preserved', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements[1].text.lineHeight = 24;
  const legacy = legacyImportedFrame(h, data);
  const read = await h.read(data);
  assert.equal(read.screens[0].status, 'changed');
  assert.match(read.screens[0].error, /line height differs.*new graph ID/i);
  await assert.rejects(() => h.apply(data), /new graph ID.*line height differs/i);
  assert.equal(h.page.children.length, 1);
  assert.equal(h.page.children[0], legacy);
  assert.equal(legacy.findAll(node => node.type === 'TEXT')[1].lineHeight.value, 20);
});

test('legacy font-family aliases verify without loading font files', async () => {
  const h = harness();
  h.fonts.push({ fontName: { family: 'Geist', style: 'Medium' } });
  const data = plan();
  for (const element of data.web_design.screens[0].elements.filter(row => row.kind === 'component')) {
    element.text.fontFamily = 'Geist Sans';
  }
  legacyImportedFrame(h, data, { family: 'Geist', style: 'Medium' });
  const result = await h.read(data);
  assert.equal(result.screens[0].status, 'current');
  assert.equal(h.counts().fontLoads, 0);
  assert.equal(h.counts().fontListReads, 1);
});

test('failed scoped readback rolls back only this transaction’s unchanged nodes', async () => {
  const h = harness(async () => { throw Error('readback failed'); });
  await assert.rejects(() => h.apply(plan()), /readback failed/);
  assert.equal(h.page.children.length, 0);
});

test('radial gradient capture becomes a native paint and survives readback', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({
    id: 'hero-glow', kind: 'frame', path: [], box: { x: 0, y: 270, width: 390, height: 180 },
    paint: { radialGradient: { centerX: 0.5, centerY: 0.2, stops: [
      { position: 0, color: '#65aaffcc' }, { position: 1, color: '#ffffff00' },
    ] } },
  });
  const receipt = await h.apply(data);
  const root = h.page.children[0];
  const glow = root.children.find(node => node.getPluginData('figma-flow-web-element-id') === 'hero-glow');
  assert.equal(glow.fills[0].type, 'GRADIENT_RADIAL');
  assert.equal(glow.fills[0].gradientStops.length, 2);
  assert.equal(glow.fills[0].gradientStops[0].color.a, 0xcc / 255);
  assert.equal(receipt.receipt.screens[0].gradients[0].element_id, 'hero-glow');
});

test('CSSOM radial gradients without an explicit center keep their rendered solid stops', () => {
  const rect = { x: 0, y: 0, width: 341, height: 150 };
  const style = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'rgba(0, 0, 0, 0)',
    backgroundImage: 'radial-gradient(rgb(250, 116, 107) 0%, rgb(168, 74, 240) 55%, rgb(52, 120, 246) 100%)',
    borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '14px', borderTopColor: 'rgb(0, 0, 0)',
    fontFamily: 'Arial', fontWeight: '400', fontSize: '16px', lineHeight: '19px', textAlign: 'left', color: 'rgb(0,0,0)',
    overflowX: 'visible', overflowY: 'visible', maskImage: 'none', filter: 'none', boxShadow: 'none' };
  const body = { tagName: 'MAIN', textContent: '', children: [], childNodes: [], getBoundingClientRect: () => rect,
    getClientRects: () => [rect], getAttribute: () => null };
  const document = { body, documentElement: { clientWidth: 341, scrollHeight: 150 }, title: 'CSSOM radial' };
  const context = vm.createContext({ document, location: { origin: 'http://localhost:3000', pathname: '/' },
    innerHeight: 150, innerWidth: 341, scrollX: 0, scrollY: 0, getComputedStyle: () => style });
  vm.runInContext(captureSource, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-cssom-radial' })));
  assert.deepEqual(captured.screen.elements[0].paint.radialGradient, { centerX: 0.5, centerY: 0.5, stops: [
    { position: 0, color: '#fa746b' }, { position: 0.55, color: '#a84af0' }, { position: 1, color: '#3478f6' },
  ] });
  assert.equal(captured.limitations.includes('background image or unsupported gradient'), false);
});

test('bounded native shadow and blur effects survive editable import', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({ id: 'fx', kind: 'frame', path: [],
    box: { x: 12, y: 260, width: 80, height: 40 }, paint: { background: '#ffffff', effects: [
      { type: 'DROP_SHADOW', x: 0, y: 2, blur: 6, spread: 0, color: '#00000033' },
      { type: 'LAYER_BLUR', radius: 3 },
    ] } });
  await h.apply(data);
  const node = h.page.children[0].children.find(item => item.name === 'frame · fx');
  assert.deepEqual(node.effects.map(effect => effect.type), ['DROP_SHADOW', 'LAYER_BLUR']);
  assert.equal(node.effects[0].color.a, 0x33 / 255);
  assert.equal('opacity' in node.effects[0], false);
  assert.equal(node.effects[0].offset.y, 2);
  assert.equal(node.effects[1].blurType, 'NORMAL');
});

test('image filter effects are retained beside the pinned image fill', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({ id: 'filtered-image', kind: 'image',
    box: { x: 8, y: 265, width: 40, height: 40 }, asset: { sha256: 'c'.repeat(64), mimeType: 'image/png' },
    paint: { effects: [{ type: 'DROP_SHADOW', x: 0, y: 1, blur: 3, spread: 0, color: '#00000044' }] } });
  await h.apply(data);
  const node = h.page.children[0].children.find(item => item.name === 'image · filtered-image');
  assert.equal(node.fills[0].type, 'IMAGE');
  assert.equal(node.effects[0].type, 'DROP_SHADOW');
});

test('linear alpha mask stays a native editable mask sibling inside an owned wrapper', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({ id: 'masked', kind: 'frame', path: [],
    box: { x: 12, y: 260, width: 80, height: 40 }, paint: { background: '#ffffff', alphaMask: {
      angle: 90, stops: [{ position: 0, color: '#00000000' }, { position: 1, color: '#000000ff' }],
    } } });
  await h.apply(data);
  const wrapper = h.page.children[0].children.find(item => item.name === 'Mask wrapper · masked');
  assert.equal(wrapper.children.length, 2);
  assert.equal(wrapper.children[0].isMask, true);
  assert.equal(wrapper.children[0].maskType, 'ALPHA');
  assert.equal(wrapper.children[1].type, 'FRAME');
});

test('intersecting linear and radial CSS masks capture and import as nested native alpha masks', async () => {
  const rect = { x: 20, y: 30, width: 100, height: 60 };
  const style = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'rgb(255, 255, 255)',
    backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px',
    borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px',
    textAlign: 'left', color: 'rgb(0,0,0)', overflowX: 'visible', overflowY: 'visible',
    maskImage: 'radial-gradient(ellipse at 50% 50%, rgba(0, 0, 0, 1) 0%, rgba(0, 0, 0, 0) 100%), linear-gradient(90deg, rgba(0, 0, 0, 1) 0%, rgba(0, 0, 0, 0) 100%)',
    maskComposite: 'intersect', filter: 'none', boxShadow: 'none' };
  const button = { nodeType: 1, tagName: 'BUTTON', textContent: 'Mask', children: [], childNodes: [],
    getClientRects: () => [rect], getBoundingClientRect: () => rect, querySelector: () => null, getAttribute: () => null };
  const body = { tagName: 'BODY', textContent: '', childNodes: [button], children: [button], getAttribute: () => null,
    getBoundingClientRect: () => rect, getClientRects: () => [] };
  const document = { body, documentElement: { clientWidth: 400, scrollHeight: 300 }, title: 'Mask fixture',
    createRange() { return { selectNodeContents() {}, getBoundingClientRect: () => ({ x: 24, y: 44, width: 40, height: 19 }) }; } };
  const context = vm.createContext({ document, location: { origin: 'http://localhost:3000', pathname: '/' },
    innerHeight: 300, innerWidth: 400, scrollX: 0, scrollY: 0,
    getComputedStyle: () => style });
  vm.runInContext(captureSource, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-mask-fixture' })));
  const element = captured.screen.elements.find(item => item.kind === 'component');
  assert.deepEqual(element.paint.alphaMasks.map(mask => mask.kind), ['radial', 'linear']);
  assert.equal(element.paint.alphaMaskComposite, 'intersect');
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({ id: 'two-masks', kind: 'frame', path: [], box: rect, paint: element.paint });
  await h.apply(data);
  const outer = h.page.children[0].children.find(item => item.name === 'Mask wrapper 2 · two-masks');
  assert.equal(outer.children[0].isMask, true);
  const inner = outer.children[1];
  assert.equal(inner.children[0].isMask, true);
  assert.equal(inner.children[1].type, 'FRAME');
  assert.equal(outer.children[0].fills[0].type, 'GRADIENT_LINEAR');
  assert.equal(inner.children[0].fills[0].type, 'GRADIENT_RADIAL');
});

test('unsupported mask union and partial filter chains are explicitly reported and omitted', () => {
  const rect = { x: 20, y: 30, width: 100, height: 60 };
  const style = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'rgb(255, 255, 255)',
    backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px',
    borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px',
    textAlign: 'left', color: 'rgb(0,0,0)', overflowX: 'visible', overflowY: 'visible',
    maskImage: 'linear-gradient(90deg, #000, transparent), radial-gradient(ellipse at 50% 50%, #000, transparent)',
    maskComposite: 'add', filter: 'blur(3px) brightness(1.2)', boxShadow: 'none' };
  const button = { nodeType: 1, tagName: 'BUTTON', textContent: 'Unsupported', children: [], childNodes: [],
    getClientRects: () => [rect], getBoundingClientRect: () => rect, querySelector: () => null, getAttribute: () => null };
  const body = { tagName: 'BODY', textContent: '', childNodes: [button], children: [button], getAttribute: () => null,
    getBoundingClientRect: () => rect, getClientRects: () => [] };
  const document = { body, documentElement: { clientWidth: 400, scrollHeight: 300 }, title: 'Unsupported fixture',
    createRange() { return { selectNodeContents() {}, getBoundingClientRect: () => ({ x: 24, y: 44, width: 80, height: 19 }) }; } };
  const context = vm.createContext({ document, location: { origin: 'http://localhost:3000', pathname: '/' },
    innerHeight: 300, innerWidth: 400, scrollX: 0, scrollY: 0,
    getComputedStyle: () => style });
  vm.runInContext(captureSource, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-unsupported' })));
  const element = captured.screen.elements.find(item => item.kind === 'component');
  assert.equal(element.paint.alphaMasks, undefined);
  assert.equal(element.paint.effects, undefined);
  assert(captured.limitations.includes('unsupported CSS mask composition or layer'));
  assert(captured.limitations.includes('unsupported CSS filter chain'));
});

test('color filter chains transform opaque leaf solid paints with ordered CSS matrix math', () => {
  const rect = { x: 20, y: 30, width: 100, height: 60 };
  const style = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'rgb(100, 80, 60)',
    backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px',
    borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px',
    textAlign: 'left', color: 'rgb(0,0,0)', overflowX: 'visible', overflowY: 'visible', maskImage: 'none',
    filter: 'brightness(120%) saturate(150%)', boxShadow: 'none' };
  const shape = { nodeType: 1, tagName: 'DIV', textContent: '', children: [], childNodes: [],
    getClientRects: () => [rect], getBoundingClientRect: () => rect, querySelector: () => null, getAttribute: () => null };
  const body = { tagName: 'BODY', textContent: '', childNodes: [shape], children: [shape], getAttribute: () => null,
    getBoundingClientRect: () => rect, getClientRects: () => [] };
  const document = { body, documentElement: { clientWidth: 400, scrollHeight: 300 }, title: 'Filter fixture' };
  const context = vm.createContext({ document, location: { origin: 'http://localhost:3000', pathname: '/' },
    innerHeight: 300, innerWidth: 400, scrollX: 0, scrollY: 0,
    getComputedStyle: element => element === body ? { ...style, backgroundColor: 'transparent', filter: 'none' } : style });
  vm.runInContext(captureSource, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-color-filter' })));
  assert.equal(captured.screen.elements[0].paint.background, '#825e3a');
  assert.equal(captured.limitations.includes('unsupported CSS filter chain'), false);
});

test('pinned local video becomes a native VIDEO paint with hash readback', async () => {
  const h = harness();
  const data = plan();
  const videoHash = 'd'.repeat(64), pngHash = 'e'.repeat(64);
  data.web_design.assets[videoHash] = Buffer.from('0000ftypmp42').toString('base64');
  data.web_design.assets[pngHash] = Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]).toString('base64');
  data.web_design.screens[0].elements.push({ id: 'video', kind: 'video', box: { x: 10, y: 260, width: 160, height: 90 },
    objectFit: 'cover', asset: { path: 'media/source.mp4', sha256: videoHash, mimeType: 'video/mp4' },
    fallbackAsset: { path: 'media/frame.png', sha256: pngHash, mimeType: 'image/png' } });
  await h.apply(data);
  assert.equal(h.videos.length, 1);
  const node = h.page.children[0].children.find(item => item.name === 'video · video');
  assert.equal(node.fills[0].type, 'VIDEO');
  assert.equal(node.fills[0].videoHash, 'video-1');
});

test('video permission failure uses only its pinned first-frame fallback and reports why', async () => {
  const h = harness();
  h.figma.createVideoAsync = async () => { throw Error('Uploads are unavailable in this plan'); };
  const data = plan();
  const videoHash = 'd'.repeat(64), pngHash = 'e'.repeat(64);
  data.web_design.assets[videoHash] = Buffer.from('0000ftypmp42').toString('base64');
  data.web_design.assets[pngHash] = Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]).toString('base64');
  data.web_design.screens[0].elements.push({ id: 'video', kind: 'video', box: { x: 10, y: 260, width: 160, height: 90 },
    objectFit: 'cover', asset: { path: 'media/source.mp4', sha256: videoHash, mimeType: 'video/mp4' },
    fallbackAsset: { path: 'media/frame.png', sha256: pngHash, mimeType: 'image/png' } });
  const result = await h.apply(data);
  const node = h.page.children[0].children.find(item => item.name === 'video · video');
  assert.equal(node.fills[0].type, 'IMAGE');
  const diagnostic = result.receipt.screens[0].fallbacks.find(row => row.element_id === 'video');
  assert.equal(diagnostic.type, 'video');
  assert.equal(diagnostic.status, 'poster-fallback');
  assert.match(diagnostic.reason, /Uploads are unavailable/);
});

test('font style matching ignores native spacing while recording actual family fallback', async () => {
  corruptInstanceLineHeight = false;
  const h = harness();
  h.fonts.push({ fontName: { family: 'Geist', style: 'Semibold' } });
  const data = plan();
  data.web_design.screens[0].elements.push(
    { id: 'geist-title', kind: 'text', box: { x: 20, y: 280, width: 180, height: 24 }, text: { characters: 'Native title', fontFamily: 'Geist', fontSize: 18, fontWeight: 600 } },
    { id: 'missing-family', kind: 'text', box: { x: 20, y: 310, width: 180, height: 20 }, text: { characters: 'Fallback copy', fontFamily: 'Geist Sans', fontSize: 14, fontWeight: 400 } },
  );
  const receipt = await h.apply(data);
  const fallbacks = receipt.receipt.screens[0].fallbacks;
  assert.equal(fallbacks.some(row => row.element_id === 'geist-title'), false);
  assert.deepEqual(fallbacks.find(row => row.element_id === 'missing-family').used, { family: 'Inter', style: 'Regular' });
});

test('browser control keys stay short and typography family is added natively', () => {
  const rect = {x: 20, y: 40, width: 120, height: 32};
  const styles = new Map();
  const styleFor = element => styles.get(element) || { display: 'block', visibility: 'visible', opacity: '1',
    backgroundColor: 'rgb(231, 0, 11)', backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none',
    borderTopLeftRadius: '8px', borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '500',
    fontSize: '14px', lineHeight: element.lineHeight + 'px', textAlign: 'center', color: 'rgb(255,255,255)',
    overflowX: 'visible', overflowY: 'visible', maskImage: 'none', filter: 'none', boxShadow: 'none' };
  const buttons = [20, 24].map((lineHeight, index) => ({
    nodeType: 1, tagName: 'BUTTON', textContent: index ? 'Join now' : 'Continue', children: [],
    lineHeight, getClientRects: () => [rect], getBoundingClientRect: () => rect,
    querySelector: () => null, getAttribute: () => null,
  }));
  buttons.forEach(button => styles.set(button, styleFor(button)));
  styles.get(buttons[0]).boxShadow = 'rgba(0, 0, 0, 0.2) 0px 2px 6px 0px';
  styles.get(buttons[0]).filter = 'blur(3px) drop-shadow(rgb(0, 0, 0) 0px 2px 4px) blur(4px) drop-shadow(rgba(0, 0, 0, .2) 1px 1px 3px)';
  styles.get(buttons[1]).maskImage = 'linear-gradient(rgb(255, 255, 255), rgba(0, 0, 0, 0))';
  const body = {tagName: 'BODY', textContent: '', childNodes: buttons, children: buttons,
    getAttribute: () => null,
    getBoundingClientRect: () => ({x: 0, y: 0, width: 400, height: 800}),
    getClientRects: () => []};
  const document = {body, documentElement: {clientWidth: 400, scrollHeight: 800}, title: 'Buttons',
    createRange() { let target; return {selectNodeContents(node) { target = node; },
      getBoundingClientRect() { return {x: rect.x + 12, y: rect.y + 6, width: 96, height: 20}; }}; }};
  const context = vm.createContext({document, location: {origin: 'http://localhost:3000', pathname: '/'},
    innerHeight: 600, innerWidth: 400, scrollX: 0, scrollY: 0, getComputedStyle: styleFor});
  vm.runInContext(captureSource, context);
  const captured = JSON.parse(JSON.stringify(context.captureWebDesign({screenId: 'WEB-buttons'})));
  const controls = captured.screen.elements.filter(element => element.kind === 'component');
  assert.equal(controls.length, 2);
  assert.equal(controls[0].componentKey, 'control-button');
  assert.equal(controls[1].componentKey, 'control-button');
  assert.ok(controls.every(element => element.componentKey.length < 160));
  assert.notEqual(controls[0].text.lineHeight, controls[1].text.lineHeight);
  assert.deepEqual(controls[0].paint.effects.map(effect => effect.type),
    ['DROP_SHADOW', 'LAYER_BLUR', 'DROP_SHADOW', 'LAYER_BLUR', 'DROP_SHADOW']);
  assert.equal(controls[0].paint.effects[0].y, 2);
  assert.equal(controls[0].paint.effects[1].radius, 3);
  assert.equal(controls[0].paint.effects[3].radius, 4);
  assert.deepEqual(controls[1].paint.alphaMask.stops.map(stop => stop.position), [0, 1]);
});

test('video capture keeps source and poster URLs on one distinct video candidate', () => {
  const rect = { x: 0, y: 0, width: 320, height: 180 };
  const video = { nodeType: 1, tagName: 'VIDEO', textContent: '', children: [], childNodes: [],
    currentSrc: '', poster: '/poster.png', querySelector: () => ({ src: '/clip.mp4' }),
    getBoundingClientRect: () => rect, getClientRects: () => [rect], getAttribute: () => null };
  const style = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'transparent',
    backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none', borderTopLeftRadius: '0px',
    borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '400', fontSize: '16px', lineHeight: '19px',
    textAlign: 'left', color: 'rgb(0,0,0)', overflowX: 'visible', overflowY: 'visible', maskImage: 'none', filter: 'none', boxShadow: 'none' };
  const body = { tagName: 'BODY', textContent: '', childNodes: [video], children: [video], getAttribute: () => null,
    getBoundingClientRect: () => rect, getClientRects: () => [] };
  const document = { body, documentElement: { clientWidth: 320, scrollHeight: 180 }, title: 'Video' };
  const context = vm.createContext({ document, location: { origin: 'https://portfolio.example', pathname: '/', href: 'https://portfolio.example/' },
    innerHeight: 180, innerWidth: 320, scrollX: 0, scrollY: 0, getComputedStyle: () => style, URL });
  vm.runInContext(captureSource, context);
  const result = JSON.parse(JSON.stringify(context.captureWebDesign({ screenId: 'WEB-video' })));
  assert.equal(result.images.length, 1);
  assert.equal(result.images[0].mediaKind, 'video');
  assert.equal(result.images[0].requestTarget, 'https://portfolio.example/clip.mp4');
  assert.equal(result.images[0].fallbackRequestTarget, 'https://portfolio.example/poster.png');
});

test('native SVG preflight accepts only resolved local clip and gradient references', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({ id: 'svg-logo', kind: 'vector', box: { x: 10, y: 260, width: 20, height: 20 },
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><clipPath id="clip0"><rect width="10" height="10"/></clipPath><linearGradient id="paint0"><stop offset="0" stop-color="#000000"/><stop offset="1" stop-color="#ffffff"/></linearGradient></defs><g clip-path="url(#clip0)"><path d="M0 0h10v10H0z" fill="url(#paint0)"/></g></svg>' });
  await h.apply(data);
  data.web_design.graph_id = 'svg-bad';
  data.web_design.screens[0].elements.at(-1).svg = data.web_design.screens[0].elements.at(-1).svg.replace('paint0)', 'missing)');
  await assert.rejects(() => h.apply(data), /Unresolved or duplicate SVG local reference/);
});

test('captured text gradients stay editable with normalized stops', () => {
  const rect = {x: 20, y: 40, width: 120, height: 32};
  const styles = new Map();
  const styleFor = element => styles.get(element) || { display: 'block', visibility: 'visible', opacity: '1',
    backgroundColor: 'rgb(231, 0, 11)', backgroundImage: 'none', borderTopWidth: '0px', borderTopStyle: 'none',
    borderTopLeftRadius: '8px', borderTopColor: 'rgb(0,0,0)', fontFamily: 'Inter', fontWeight: '500',
    fontSize: '14px', lineHeight: '20px', textAlign: 'left', color: 'rgb(255,255,255)',
    overflowX: 'visible', overflowY: 'visible', maskImage: 'none', filter: 'none', boxShadow: 'none' };
  const span = { nodeType: 1, tagName: 'SPAN', textContent: 'AI Agent SDK', children: [], childNodes: [{nodeType: 3, textContent: 'AI Agent SDK'}],
    getClientRects: () => [rect], getBoundingClientRect: () => rect, querySelector: () => null, getAttribute: () => null };
  const textStyle = styleFor(span);
  textStyle.color = 'rgba(0, 0, 0, 0)';
  textStyle.backgroundClip = 'text';
  textStyle.backgroundImage = 'linear-gradient(135deg, oklch(0.68 0.17 15), oklch(0.68 0.17 321), oklch(0.68 0.17 130))';
  styles.set(span, textStyle);
  const srOnly = { nodeType: 1, tagName: 'SPAN', textContent: 'AI Agent SDK', children: [],
    childNodes: [{nodeType: 3, textContent: 'AI Agent SDK'}], getClientRects: () => [{x: 0, y: 0, width: 1, height: 1}],
    getBoundingClientRect: () => ({x: 0, y: 0, width: 1, height: 1}), querySelector: () => null, getAttribute: () => null };
  styles.set(srOnly, {...styleFor(srOnly), clip: 'rect(0px, 0px, 0px, 0px)'});
  const body = { tagName: 'BODY', textContent: 'AI Agent SDK', childNodes: [span, srOnly], children: [span, srOnly], getAttribute: () => null,
    getBoundingClientRect: () => ({x: 0, y: 0, width: 400, height: 800}), getClientRects: () => [] };
  const document = {body, documentElement: {clientWidth: 400, scrollHeight: 800}, title: 'Gradient',
    createRange() { return {selectNodeContents() {}, getClientRects: () => [rect], setStart() {}, setEnd() {}, getBoundingClientRect: () => rect}; }};
  const context = vm.createContext({document, location: {origin: 'http://localhost', pathname: '/', href: 'http://localhost/'},
    innerHeight: 600, innerWidth: 400, scrollX: 0, scrollY: 0, getComputedStyle: styleFor, URL});
  vm.runInContext(captureSource, context);
  const result = JSON.parse(JSON.stringify(context.captureWebDesign({screenId: 'WEB-text-gradient'})));
  assert.equal(result.screen.elements.filter(element => element.kind === 'text').length, 1);
  const text = result.screen.elements.find(element => element.kind === 'text').text;
  assert.equal(text.color, undefined);
  assert.equal(text.linearGradient.angle, 135);
  assert.deepEqual(text.linearGradient.stops.map(stop => stop.position), [0, 0.5, 1]);
  textStyle.backgroundImage = 'radial-gradient(ellipse at center, oklch(0.68 0.17 15), oklch(0.68 0.17 130))';
  const fallback = JSON.parse(JSON.stringify(context.captureWebDesign({screenId: 'WEB-text-gradient-fallback'})));
  const fallbackText = fallback.screen.elements.find(element => element.kind === 'text').text;
  assert.equal(fallbackText.paintApproximation, 'first-gradient-stop');
  assert.notEqual(fallbackText.color, '#000000');
  assert.ok(fallback.limitations.includes('text gradient approximated as a solid color'));
});

test('editable text gradient is written and checked through native range fills', async () => {
  const h = harness();
  const data = plan();
  data.web_design.screens[0].elements.push({ id: 'gradient-title', kind: 'text', box: { x: 10, y: 260, width: 160, height: 30 },
    text: { characters: 'AI Agent SDK', fontFamily: 'Inter', fontSize: 24, fontWeight: 700, lineHeight: 30,
      linearGradient: { angle: 135, stops: [{position: 0, color: '#ee5577'}, {position: 1, color: '#33aa88'}] } } });
  await h.apply(data);
  const node = h.page.children[0].children.find(item => item.name === 'AI Agent SDK · gradient-title');
  assert.equal(node.fills[0].type, 'GRADIENT_LINEAR');
  assert.equal(node.fills[0].gradientStops.length, 2);
  assert.equal(node.fills[0].gradientTransform.length, 2);
});
