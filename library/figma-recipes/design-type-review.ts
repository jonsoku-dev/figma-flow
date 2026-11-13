type ReviewGraph = typeof FLOW_REVIEW_GRAPH;
type ReviewNode = ReviewGraph['nodes'][number];

const RECIPE_VERSION = '1.0.0';
const RECIPE_TITLE = 'Figma Flow typography specimen';
const EXPECTED_GRAPH_ID = 'figma-flow-designer-developer-typography';
const EXPECTED_AUDIT_SHA256 = '4e907bc440efbcbe8826927fdb6463222b5e9c86d2a9dd7137d5e4ee25c39db8';
const EXPECTED_API_REF = 'dff4874ca083e18cd74835fd5afc5079d46866b7';
const EXPECTED_API_VERSION = '1.142.0';
const FRAME_NAME_PREFIX = `${RECIPE_TITLE} · v${RECIPE_VERSION}`;

type PriorityMember = {
  api_member_id: string;
  owner: string;
  name: string;
  signature: string;
  priority_score: number;
  feasibility: string;
  receiver_types: string[];
  queue_receiver: string;
  queue_position: number | null;
  release_status: string;
  evidence_status: string;
  official_source_url: string;
};

type ReviewScope = {
  fileKey: string;
  pageId: string;
  auditSha256: string;
  apiSource: string;
  apiSourceRef: string;
  priorityInventorySha256: string;
  recipeVersion: string;
};

type RangeReadback = {
  label: string;
  font: { family: string; style: string };
  fontSize: number;
  lineHeight: LineHeight;
  letterSpacing: LetterSpacing;
  fill: { r: number; g: number; b: number; opacity: number };
};

const EXPECTED_API_MEMBERS: Record<string, string> = {
  'PluginAPI.listAvailableFontsAsync': 'member:5b6b924901a936cdd4c32c0c0b76d550eb1ee998cb00e0f761bd55e5cc7cb0ad',
  'PluginAPI.createComponentFromNode': 'member:b75b36905b99a2481ecf0e6480d88c8c360221a235d6322dd16a5c113d495d94',
  'BaseNodeMixin.getCSSAsync': 'member:7821990348079d68d21707dcd0f1f6ca556564f7f0b13dadc883bb2cbb3602f7',
  'BaseNonResizableTextMixin.getRangeFontName': 'member:92feaeeb3a10f7f94c457374941aa443901c1c66f9b3fc67e94baeb610891d1c',
  'BaseNonResizableTextMixin.getRangeFontSize': 'member:31a014edb3bedba5aa87755040799e8832055ba95a38a00c3d0df2eb81c80068',
  'NonResizableTextMixin.getRangeLineHeight': 'member:2726fa835362ba50faf4c1a2775c57b587da98e492f47e15827312a36fd221d7',
  'BaseNonResizableTextMixin.getRangeLetterSpacing': 'member:7c5cc7ccd900976c330c9a635f5232c994ab71ce17251c481789669c5befaf75',
  'BaseNonResizableTextMixin.getRangeFills': 'member:680c68c4592dde8f6f84ecc8cf7bb29a3822799de430682b4c5bc29995ea3af7',
  'BaseNonResizableTextMixin.setRangeFontName': 'member:57803cdab8acbb5e8a9ba3ec24506f6c17e33057c9f8935ec180193375aa5e08',
  'BaseNonResizableTextMixin.setRangeFontSize': 'member:447c8c34808ed80daa766ab19aa3dba04be98da602c0742bd53a97b99065a212',
  'NonResizableTextMixin.setRangeLineHeight': 'member:83bba70ec68c4c8a866b233c3765e773d0d212b97f72550895cc3bb0ca9818c2',
  'BaseNonResizableTextMixin.setRangeLetterSpacing': 'member:875ac391a64017fe272eaa8f3d983b455b3a21923d0281505dc27e395b9a9133',
  'BaseNonResizableTextMixin.setRangeFills': 'member:bf3d5d481b0b87de0da04e7b12f924cbc0399254fccccdb05b3b57aa9bb89099',
  'MinimalFillsMixin.fills': 'member:25f2ee610adf3460e00415cf1146a9b3933067b85513b2e07103b262c945cbff',
  'CornerMixin.cornerRadius': 'member:6cfa692e82d179a7d4f7d87ca6e747057c6964920b28e065920e51e6f894913c',
  'BlendMixin.effects': 'member:7e594e865f9703a703b99949e6e591f3a9a9830815a9c6e4328e632d9b117c29',
  'MinimalStrokesMixin.dashPattern': 'member:3f63b8388af891028b2378d4e7bd01a03b77a4b0433d8bb9a1fbf744f3c68d94',
  'MinimalStrokesMixin.strokeWeight': 'member:705aafee7a9e058c907d0563818bc8aa05d71df0c7cfc0e3768b060691428a93',
  'MinimalStrokesMixin.strokes': 'member:401ea520ea52370118f0a68e01621eb558d7eeee9aa7c49dabbe5353b10ab071',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isReviewScope(value: unknown): value is ReviewScope {
  return isRecord(value) && typeof value.fileKey === 'string' && typeof value.pageId === 'string'
    && typeof value.auditSha256 === 'string' && typeof value.apiSource === 'string'
    && typeof value.apiSourceRef === 'string' && typeof value.priorityInventorySha256 === 'string'
    && typeof value.recipeVersion === 'string';
}

function isPriorityMember(value: unknown): value is PriorityMember {
  return isRecord(value) && typeof value.api_member_id === 'string' && typeof value.owner === 'string'
    && typeof value.name === 'string' && typeof value.signature === 'string'
    && typeof value.priority_score === 'number' && typeof value.feasibility === 'string'
    && Array.isArray(value.receiver_types) && value.receiver_types.every(item => typeof item === 'string')
    && typeof value.queue_receiver === 'string'
    && (value.queue_position === null || (typeof value.queue_position === 'number' && Number.isInteger(value.queue_position)))
    && typeof value.release_status === 'string' && typeof value.evidence_status === 'string'
    && typeof value.official_source_url === 'string';
}

function parseDetail<T>(node: ReviewNode, name: string, validate: (value: unknown) => value is T): T {
  let parsed: unknown;
  try {
    parsed = JSON.parse(node.detail);
  } catch {
    throw new Error(`${name} graph detail is not valid JSON.`);
  }
  if (!validate(parsed)) throw new Error(`${name} graph detail does not match its expected shape.`);
  return parsed;
}

function readScope(graph: ReviewGraph): ReviewScope {
  if (graph.id !== EXPECTED_GRAPH_ID || !/^[a-f0-9]{64}$/.test(FLOW_REVIEW_GRAPH_SHA256)
      || !/^[a-f0-9]{64}$/.test(FLOW_REVIEW_SELECTION_SHA256)) {
    throw new Error('Typography review requires its pinned priority graph and selection identity.');
  }
  const scopeNode = graph.nodes.find(node => node.id === 'scope:lab');
  if (!scopeNode) throw new Error('Typography graph has no exact lab scope node.');
  const value = parseDetail(scopeNode, 'Scope', isReviewScope);
  if (value.auditSha256 !== EXPECTED_AUDIT_SHA256
      || value.apiSource !== EXPECTED_API_VERSION || value.apiSourceRef !== EXPECTED_API_REF
      || !/^[a-f0-9]{64}$/.test(value.priorityInventorySha256) || value.recipeVersion !== RECIPE_VERSION) {
    throw new Error('Typography graph does not match the pinned API audit and priority inventory.');
  }
  return value;
}

function readPriorityMembers(graph: ReviewGraph): Map<string, PriorityMember> {
  const members = new Map<string, PriorityMember>();
  for (const node of graph.nodes) {
    if (node.type !== 'figma' || !node.id.startsWith('figma:member:')) continue;
    const row = parseDetail(node, 'Priority member', isPriorityMember);
    const key = row.owner + '.' + row.name;
    if (members.has(key) || row.api_member_id !== EXPECTED_API_MEMBERS[key]
        || node.id !== 'figma:' + row.api_member_id || row.signature.length > 1000
        || !Array.isArray(row.receiver_types) || typeof row.priority_score !== 'number') {
      throw new Error('Typography graph contains an unknown or duplicate priority API row.');
    }
    members.set(key, row);
  }
  if (members.size !== Object.keys(EXPECTED_API_MEMBERS).length) {
    throw new Error('Typography graph is missing a required ranked API member.');
  }
  for (const key of Object.keys(EXPECTED_API_MEMBERS)) {
    if (!members.has(key)) throw new Error(`Typography graph is missing ${key}.`);
  }
  return members;
}

function exactRow(members: Map<string, PriorityMember>, key: string, receiver: string,
  feasibility: string): PriorityMember {
  const row = members.get(key);
  if (!row || row.feasibility !== feasibility || !row.receiver_types.includes(receiver)) {
    throw new Error(`Priority row ${key} is not approved for ${receiver} as ${feasibility}.`);
  }
  return row;
}

function readMetadata(component: ComponentNode): TextNode {
  const matches = component.children.filter(node => node.type === 'TEXT' && node.name === 'Engineer metadata');
  if (matches.length !== 1 || matches[0].type !== 'TEXT') {
    throw new Error('Typography component has no unique engineer metadata node.');
  }
  return matches[0];
}

function colorHex(color: RGB): string {
  const channel = (value: number): string => Math.round(value * 255).toString(16).padStart(2, '0');
  return '#' + channel(color.r) + channel(color.g) + channel(color.b);
}

function solidFillSummary(paints: readonly Paint[]): { r: number; g: number; b: number; opacity: number } {
  const solid = paints.find((paint): paint is SolidPaint => paint.type === 'SOLID');
  if (!solid) throw new Error('Text fill readback did not return a solid paint.');
  return { r: solid.color.r, g: solid.color.g, b: solid.color.b, opacity: solid.opacity ?? 1 };
}

function readTextRange(text: TextNode, label: string, onReadback: (row: RangeReadback) => void): void {
  const end = text.characters.length;
  const font = text.getRangeFontName(0, end);
  const fontSize = text.getRangeFontSize(0, end);
  const lineHeight = text.getRangeLineHeight(0, end);
  const letterSpacing = text.getRangeLetterSpacing(0, end);
  const fills = text.getRangeFills(0, end);
  if (font === figma.mixed || fontSize === figma.mixed || lineHeight === figma.mixed
      || letterSpacing === figma.mixed || fills === figma.mixed) {
    throw new Error(`${label} range readback returned mixed styles.`);
  }
  onReadback({ label, font: { family: font.family, style: font.style }, fontSize,
    lineHeight, letterSpacing, fill: solidFillSummary(fills) });
}

function cssSummary(css: { [key: string]: string }): Record<string, string> {
  const projected: Record<string, string> = {};
  const keys = ['width', 'height', 'border-radius', 'opacity', 'display', 'box-sizing'];
  for (const key of keys) {
    const value = css[key];
    if (typeof value !== 'string' || value.length > 64) continue;
    if (/^-?(?:\d+\.?\d*|\.\d+)(?:px|%)?$/.test(value)
        || ['block', 'flex', 'inline-flex', 'border-box', 'content-box'].includes(value)) {
      projected[key] = value;
    }
  }
  return projected;
}

function fontChoice(available: Font[]): { regular: FontName; strong: FontName } {
  if (!available.length) throw new Error('This Figma editor reports no available fonts.');
  const preferred = (family: string): FontName | undefined =>
    available.find(item => item.fontName.family === family)?.fontName;
  const family = preferred('Inter')?.family ?? preferred('Arial')?.family ?? available[0].fontName.family;
  const familyFonts = available.filter(item => item.fontName.family === family).map(item => item.fontName);
  const regular = familyFonts.find(font => /regular|book/i.test(font.style)) ?? familyFonts[0];
  const strong = familyFonts.find(font => /bold|black|semibold/i.test(font.style)) ?? regular;
  return { regular, strong };
}

function setTextRange(text: TextNode, content: string, font: FontName, size: number,
  lineHeight: number, letterSpacing: number, color: RGB): void {
  text.characters = content;
  const end = text.characters.length;
  text.setRangeFontName(0, end, font);
  text.setRangeFontSize(0, end, size);
  text.setRangeLineHeight(0, end, { unit: 'PIXELS', value: lineHeight });
  text.setRangeLetterSpacing(0, end, { unit: 'PIXELS', value: letterSpacing });
  text.setRangeFills(0, end, [{ type: 'SOLID', color }]);
}

function expectedRowSummary(members: Map<string, PriorityMember>): string[] {
  return [...members.values()].map(row => {
    const position = row.queue_position === null ? 'observed in graph' : `queue ${row.queue_receiver} #${row.queue_position}`;
    return `${row.owner}.${row.name} · ${position} · score ${row.priority_score} · ${row.feasibility} · ${row.api_member_id}`;
  });
}

function verifyFrameStyles(component: ComponentNode): void {
  if (component.cornerRadius !== 16 || component.strokeWeight !== 1
      || component.dashPattern.length !== 2 || component.dashPattern[0] !== 8 || component.dashPattern[1] !== 4) {
    throw new Error('Typography frame geometry or stroke readback changed.');
  }
  const fills = component.fills;
  const background = Array.isArray(fills) ? fills.find((paint): paint is SolidPaint => paint.type === 'SOLID') : undefined;
  if (!background || Math.abs(background.color.r - 0.075) > 0.001
      || Math.abs(background.color.g - 0.09) > 0.001 || Math.abs(background.color.b - 0.13) > 0.001) {
    throw new Error('Typography frame fill readback changed.');
  }
  const shadow = component.effects.find(effect => effect.type === 'DROP_SHADOW');
  if (!shadow || shadow.radius !== 16 || component.strokes.length !== 1
      || component.strokes[0].type !== 'SOLID') {
    throw new Error('Typography frame shadow or stroke readback changed.');
  }
}

function verifyExisting(component: ComponentNode, identity: string): void {
  verifyFrameStyles(component);
  const metadata = readMetadata(component);
  if (!metadata.characters.includes(identity)) {
    throw new Error('A same-name component exists with different graph or selection metadata.');
  }
  const textNodes = component.children.filter((node): node is TextNode => node.type === 'TEXT'
    && node.name !== 'Engineer metadata');
  if (textNodes.length !== 3) throw new Error('Existing typography component has changed its specimen text nodes.');
  for (const node of textNodes) readTextRange(node, node.name, () => {});
}

async function main(): Promise<void> {
  if (figma.editorType !== 'figma' || figma.mode !== 'default') {
    throw new Error('Open this recipe in Figma Design default mode.');
  }
  const graph = FLOW_REVIEW_GRAPH;
  const scope = readScope(graph);
  const members = readPriorityMembers(graph);
  if (figma.fileKey !== scope.fileKey || figma.currentPage.id !== scope.pageId) {
    throw new Error('Current file or page does not match the selected typography lab scope.');
  }
  exactRow(members, 'PluginAPI.listAvailableFontsAsync', 'PluginAPI', 'read-only-method');
  exactRow(members, 'PluginAPI.createComponentFromNode', 'PluginAPI', 'owned-write-method');
  exactRow(members, 'BaseNodeMixin.getCSSAsync', 'FRAME', 'read-only-method');
  for (const key of ['BaseNonResizableTextMixin.getRangeFontName', 'BaseNonResizableTextMixin.getRangeFontSize',
    'NonResizableTextMixin.getRangeLineHeight', 'BaseNonResizableTextMixin.getRangeLetterSpacing',
    'BaseNonResizableTextMixin.getRangeFills']) {
    exactRow(members, key, 'TEXT', 'read-only-method');
  }
  for (const key of ['BaseNonResizableTextMixin.setRangeFontName', 'BaseNonResizableTextMixin.setRangeFontSize',
    'NonResizableTextMixin.setRangeLineHeight', 'BaseNonResizableTextMixin.setRangeLetterSpacing',
    'BaseNonResizableTextMixin.setRangeFills']) {
    exactRow(members, key, 'TEXT', 'owned-write-method');
  }
  for (const key of ['CornerMixin.cornerRadius', 'BlendMixin.effects', 'MinimalStrokesMixin.dashPattern',
    'MinimalStrokesMixin.strokeWeight', 'MinimalStrokesMixin.strokes', 'MinimalFillsMixin.fills']) {
    exactRow(members, key, 'FRAME', 'readable-property');
  }

  const identity = `graph:${FLOW_REVIEW_GRAPH_SHA256}|selection:${FLOW_REVIEW_SELECTION_SHA256}|audit:${scope.auditSha256}`;
  const name = `${FRAME_NAME_PREFIX} · ${FLOW_REVIEW_GRAPH_SHA256.slice(0, 8)} · ${FLOW_REVIEW_SELECTION_SHA256.slice(0, 8)}`;
  const page = figma.currentPage;
  const matching = page.children.filter(node => node.name === name);
  if (matching.length > 1) throw new Error('Duplicate typography specimen names exist on the selected page.');
  if (matching.length === 1) {
    const existing = matching[0];
    if (existing.type !== 'COMPONENT') throw new Error('A partial typography specimen exists; inspect it before rerunning.');
    verifyExisting(existing, identity);
    page.selection = [existing];
    figma.viewport.scrollAndZoomIntoView([existing]);
    figma.closePlugin('Verified the existing typography specimen for this graph selection.');
    return;
  }

  const font = fontChoice(await figma.listAvailableFontsAsync());
  const fonts = new Map<string, FontName>();
  for (const selected of [font.regular, font.strong]) fonts.set(`${selected.family}\0${selected.style}`, selected);
  await Promise.all([...fonts.values()].map(selected => figma.loadFontAsync(selected)));

  const frame = figma.createFrame();
  frame.name = name;
  frame.x = page.children.reduce((right, child) => {
    const bounds = child.absoluteBoundingBox;
    return Math.max(right, bounds ? bounds.x + bounds.width : child.x + child.width);
  }, 0) + 120;
  frame.y = 80;
  frame.resize(560, 360);
  frame.layoutMode = 'VERTICAL';
  frame.primaryAxisSizingMode = 'AUTO';
  frame.counterAxisSizingMode = 'FIXED';
  frame.paddingTop = 28;
  frame.paddingRight = 32;
  frame.paddingBottom = 28;
  frame.paddingLeft = 32;
  frame.itemSpacing = 16;
  frame.fills = [{ type: 'SOLID', color: { r: 0.075, g: 0.09, b: 0.13 } }];
  frame.cornerRadius = 16;
  frame.effects = [{ type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.18 },
    offset: { x: 0, y: 8 }, radius: 16, spread: 0, visible: true, blendMode: 'NORMAL' }];
  frame.strokes = [{ type: 'SOLID', color: { r: 0.32, g: 0.38, b: 0.5 }, opacity: 1, visible: true }];
  frame.strokeWeight = 1;
  frame.dashPattern = [8, 4];
  if (frame.cornerRadius !== 16 || frame.effects[0]?.type !== 'DROP_SHADOW'
      || frame.dashPattern[0] !== 8 || frame.strokes.length !== 1) {
    throw new Error('Figma did not preserve the requested frame styling.');
  }

  const rangeReadbacks: RangeReadback[] = [];
  const addSpecimenText = (label: string, content: string, selectedFont: FontName,
    size: number, lineHeight: number, spacing: number, color: RGB): TextNode => {
    const text = figma.createText();
    text.name = label;
    frame.appendChild(text);
    setTextRange(text, content, selectedFont, size, lineHeight, spacing, color);
    readTextRange(text, label, row => rangeReadbacks.push(row));
    return text;
  };
  addSpecimenText('Display · H1', 'Aa · 24/32', font.strong, 30, 36, -0.4,
    { r: 0.96, g: 0.97, b: 1 });
  addSpecimenText('Interface · body', 'Typography that stays clear across products.', font.regular, 17, 25, 0.1,
    { r: 0.78, g: 0.82, b: 0.9 });
  addSpecimenText('Caption · label', 'FONT · SCALE · COLOR · GEOMETRY', font.strong, 11, 16, 0.8,
    { r: 0.45, g: 0.72, b: 1 });

  const css = await frame.getCSSAsync();
  const projectedCss = cssSummary(css);
  const metadataLines = [
    `Identity · ${identity}`,
    `Font · ${font.regular.family} ${font.regular.style}; strong ${font.strong.style}`,
    `CSS projection · ${JSON.stringify(projectedCss)}`,
    `Frame · radius ${frame.cornerRadius}px; shadow ${frame.effects[0].type}; dash ${frame.dashPattern.join('/')}; stroke ${frame.strokeWeight}px`,
    'Text range readbacks',
    ...rangeReadbacks.map(row => `${row.label} · ${row.font.family} ${row.font.style} · ${row.fontSize}px · ${JSON.stringify(row.lineHeight)} · ${JSON.stringify(row.letterSpacing)} · ${colorHex(row.fill)}`),
    'Priority API members',
    ...expectedRowSummary(members),
  ];
  const metadata = figma.createText();
  metadata.name = 'Engineer metadata';
  frame.appendChild(metadata);
  metadata.characters = metadataLines.join('\n');
  metadata.fontName = font.regular;
  metadata.fontSize = 9;
  metadata.fills = [{ type: 'SOLID', color: { r: 0.63, g: 0.68, b: 0.77 } }];
  if (!metadata.characters.includes(identity) || !metadata.characters.includes('member:b75b36905b99a2481ecf0e6480d88c8c360221a235d6322dd16a5c113d495d94')) {
    throw new Error('Engineer metadata does not include the selected graph identity and component API evidence.');
  }

  const component = figma.createComponentFromNode(frame);
  component.name = name;
  verifyFrameStyles(component);
  for (const text of component.children.filter((node): node is TextNode => node.type === 'TEXT'
    && node.name !== 'Engineer metadata')) readTextRange(text, text.name, () => {});
  page.selection = [component];
  figma.viewport.scrollAndZoomIntoView([component]);
  figma.closePlugin('Created and verified a reusable typography specimen from ranked API members.');
}

main().catch((error: unknown) => figma.closePlugin(String(error)));
