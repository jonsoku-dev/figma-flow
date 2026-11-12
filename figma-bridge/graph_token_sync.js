/* GRAPH_SYNC_PLAN is data only. New variables require explicit scoped pairing. */
function graphSyncEqual(a, b) {
  if (a && b && ['r', 'g', 'b'].every(key => typeof a[key] === 'number' && typeof b[key] === 'number')) return ['r', 'g', 'b', 'a'].every(key => Math.abs((a[key] === undefined ? 1 : a[key]) - (b[key] === undefined ? 1 : b[key])) <= 0.000001);
  return JSON.stringify(a) === JSON.stringify(b);
}
const GRAPH_SYNC_FIELDS = new Set(['fontFamily', 'fontSize', 'paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom', 'backgroundColor', 'color', 'borderColor', 'borderWidth', 'borderRadius', 'gap', 'minWidth', 'minHeight', 'width', 'height']);
const graphSyncNativeField = field => ({backgroundColor: 'fills', color: 'fills', borderColor: 'strokes', borderWidth: 'strokeWeight', borderRadius: 'cornerRadius', gap: 'itemSpacing'})[field] || field;
const graphSyncPaintField = field => ['backgroundColor', 'color', 'borderColor'].includes(field);
const graphSyncTextField = field => field.startsWith('font') || field === 'color';
const graphSyncFieldType = field => graphSyncPaintField(field) ? 'COLOR' : field === 'fontFamily' ? 'STRING' : 'FLOAT';
function graphSyncPaint(node, field) {
  const paints = node[graphSyncNativeField(field)];
  if (!Array.isArray(paints) || paints.length !== 1 || paints[0].type !== 'SOLID' || paints[0].visible === false) throw Error(`Graph token sync: single visible SOLID paint required: ${node.id}.${field}`);
  return paints[0];
}
function graphSyncFieldBinding(node, field) {
  let result;
  if (graphSyncPaintField(field)) result = graphSyncPaint(node, field).boundVariables?.color;
  else if (field === 'fontFamily' || field === 'fontSize') result = node.getRangeBoundVariable(0, node.characters.length, field);
  else if (field === 'borderRadius') {
    const fields = ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'];
    const aliases = fields.map(key => node.boundVariables?.[key] || node.boundVariables?.cornerRadius || null);
    if (aliases.some(alias => (alias?.id || null) !== (aliases[0]?.id || null))) throw Error(`Graph token sync: mixed corner bindings: ${node.id}`);
    result = aliases[0];
  } else result = node.boundVariables?.[graphSyncNativeField(field)];
  if (Array.isArray(result)) {
    if (!result.length || result.some(item => item.id !== result[0].id)) throw Error(`Graph token sync: mixed bindings: ${node.id}.${field}`);
    result = result[0];
  }
  if (typeof result === 'symbol') throw Error(`Graph token sync: mixed binding: ${node.id}.${field}`);
  return result || null;
}
function graphSyncFieldValue(node, field) {
  if (graphSyncPaintField(field)) {const paint = graphSyncPaint(node, field); return {...paint.color, a: paint.opacity === undefined ? 1 : paint.opacity};}
  if (field === 'fontFamily') {
    const families = [...new Set(node.getRangeAllFontNames(0, node.characters.length).map(font => font.family))];
    if (families.length !== 1) throw Error(`Graph token sync: mixed font families: ${node.id}`);
    return families[0];
  }
  const value = node[graphSyncNativeField(field)];
  if (field === 'borderRadius') {
    const corners = ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'].filter(key => key in node).map(key => node[key]);
    if (corners.some(corner => corner !== value)) throw Error(`Graph token sync: mixed corner radii: ${node.id}`);
  }
  if (typeof value === 'symbol' || value === undefined) throw Error(`Graph token sync: unavailable native field: ${node.id}.${field}`);
  return value;
}
function graphSyncWritable(node, field) {
  if (field === 'width' || field === 'height') {
    const mode = node[field === 'width' ? 'layoutSizingHorizontal' : 'layoutSizingVertical'];
    if (mode !== 'FIXED') throw Error(`Graph token sync: ${node.id}.${field} requires FIXED sizing; actual ${mode || 'unavailable'}. Use minWidth/minHeight to preserve HUG.`);
  }
  if (graphSyncPaintField(field)) {
    const style = node[graphSyncNativeField(field) === 'fills' ? 'fillStyleId' : 'strokeStyleId'];
    if (style) throw Error(`Graph token sync: preserve paint style ${style}; explicit style migration required: ${node.id}.${field}`);
  }
}
function graphSyncBindField(figma, node, field, variable) {
  graphSyncWritable(node, field);
  if (node.type === 'TEXT' && ['fontSize', 'fontFamily'].includes(field) && node.textStyleId) throw Error(`Graph token sync: linked typography requires scoped style migration: ${node.id}.${field}`);
  if (graphSyncPaintField(field)) node[graphSyncNativeField(field)] = [figma.variables.setBoundVariableForPaint(graphSyncPaint(node, field), 'color', variable)];
  else if (field === 'fontFamily' || field === 'fontSize') node.setRangeBoundVariable(0, node.characters.length, field, variable);
  else if (field === 'borderRadius') for (const corner of ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius']) node.setBoundVariable(corner, variable);
  else node.setBoundVariable(graphSyncNativeField(field), variable);
}
const GRAPH_SYNC_STYLE_FIELDS = ['fontName', 'fontSize', 'textDecoration', 'letterSpacing', 'lineHeight', 'leadingTrim', 'paragraphIndent', 'paragraphSpacing', 'textWrapStyle', 'listSpacing', 'hangingPunctuation', 'hangingList', 'textCase'];
const GRAPH_SYNC_TEXT_BINDINGS = ['fontFamily', 'fontSize', 'fontStyle', 'fontWeight', 'letterSpacing', 'lineHeight', 'paragraphSpacing', 'paragraphIndent'];
function graphSyncTextEqual(a, b) {
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((value, index) => graphSyncTextEqual(value, b[index]));
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && graphSyncTextEqual(a[key], b[key]));
  }
  return graphSyncEqual(a, b);
}

function graphSyncTextState(node) {
  const profile = {};
  for (const field of GRAPH_SYNC_STYLE_FIELDS) if (field in node) {
    if (typeof node[field] === 'symbol') throw Error(`Graph token sync: mixed text property: ${node.id}.${field}`);
    profile[field] = JSON.parse(JSON.stringify(node[field]));
  }
  const bindings = {};
  for (const field of GRAPH_SYNC_TEXT_BINDINGS) {
    const binding = node.getRangeBoundVariable(0, node.characters.length, field);
    if (typeof binding === 'symbol') throw Error(`Graph token sync: mixed text binding: ${node.id}.${field}`);
    if (binding) bindings[field] = {type: binding.type, id: binding.id};
  }
  return {style_id: node.textStyleId || '', profile, bindings};
}
async function graphSyncTextStyles(figma, entries, namespace) {
  const records = new Map(), written = [], styles = [], expectedStyles = new Map();
  const clone = value => JSON.parse(JSON.stringify(value));
  const same = graphSyncTextEqual;
  for (const entry of entries) {
    if (!['fontSize', 'fontFamily'].includes(entry.field) || entry.node.type !== 'TEXT') continue;
    if (typeof entry.node.textStyleId === 'symbol') throw Error(`Graph token sync: mixed text styles: ${entry.node.id}`);
    if (!entry.node.textStyleId) continue;
    let record = records.get(entry.node.id);
    if (!record) {
      const before = graphSyncTextState(entry.node);
      const source = await figma.getStyleByIdAsync(before.style_id);
      if (!source || source.type !== 'TEXT' || typeof figma.createTextStyle !== 'function' || typeof entry.node.setTextStyleIdAsync !== 'function') throw Error('Graph token sync: scoped text style API required');
      for (const [field, value] of Object.entries(before.profile)) if (!same(source[field], value)) throw Error(`Graph token sync: existing typography override requires explicit review: ${entry.node.id}.${field}`);
      if (!same(source.boundVariables || {}, before.bindings)) throw Error(`Graph token sync: existing text binding override requires explicit review: ${entry.node.id}`);
      if (!same(graphSyncTextState(entry.node), before)) throw Error('Graph token sync: text changed during style preflight');
      record = {node: entry.node, before, source, targets: new Map(), main: entry.main}; records.set(entry.node.id, record);
    }
    record.targets.set(entry.field, entry.variable);
  }
  const styleState = style => ({profile: Object.fromEntries(GRAPH_SYNC_STYLE_FIELDS.filter(field => field in style).map(field => [field, clone(style[field])])), bindings: clone(style.boundVariables || {}), name: style.name, owner: style.getPluginData('graphSSOT')});
  return {
    handles(node, field) {return records.has(node.id) && ['fontSize', 'fontFamily'].includes(field);},
    async bind(node) {
      const record = records.get(node.id);
      if (written.includes(record)) return;
      if (!same(graphSyncTextState(node), record.before)) {
        const inherited = written.find(item => node.textStyleId === item.style.id && same(node.textStyleId && graphSyncTextState(node).bindings, item.after.bindings));
        if (inherited && [...record.targets].every(([field, variable]) => graphSyncFieldBinding(node, field)?.id === variable.id)) return;
        throw Error(`Graph token sync: text changed before style migration: ${node.id}`);
      }
      const originalBindings = new Map();
      for (const [field, alias] of Object.entries(record.before.bindings)) {
        const variable = await figma.variables.getVariableByIdAsync(alias.id);
        if (!variable) throw Error('Graph token sync: source text style binding unavailable');
        originalBindings.set(field, variable);
      }
      const style = figma.createTextStyle();
      styles.push(style);
      try {
        style.name = `${namespace || 'Graph'}/typography/${node.id}`;
        for (const [field, value] of Object.entries(record.before.profile)) style[field] = clone(value);
        for (const field of ['description', 'descriptionMarkdown', 'documentationLinks']) if (field in record.source) style[field] = clone(record.source[field]);
        style.setPluginData('graphSSOT', JSON.stringify({namespace: namespace || null, source_style_id: record.before.style_id, node_id: node.id}));
        for (const [field, variable] of originalBindings) style.setBoundVariable(field, variable);
        for (const [field, variable] of record.targets) style.setBoundVariable(field, variable);
      } finally {
        // Capture partial synchronous writes before anything can yield to another editor.
        expectedStyles.set(style.id, styleState(style));
      }
      if (!same(graphSyncTextState(node), record.before)) throw Error('Graph token sync: text changed before style assignment');
      record.style = style; record.after = {style_id: style.id, profile: styleState(style).profile, bindings: styleState(style).bindings}; written.push(record);
      await node.setTextStyleIdAsync(style.id);
      if (!same(graphSyncTextState(node), record.after)) throw Error(`Graph token sync: scoped text style getter differs: ${node.id}`);
    },
    mark() {
      for (const record of written) {
        const state = graphSyncTextState(record.node), expected = styleState(record.style);
        if (state.style_id !== record.style.id || !same(state.profile, expected.profile) || !same(state.bindings, expected.bindings)) throw Error('Graph token sync: owned text style state changed');
        record.after = state;
      }
    },
    async rollback(conflicts) {
      for (const record of [...written].sort((a, b) => Number(b.main) - Number(a.main))) try {
        const state = graphSyncTextState(record.node);
        if (same(state, record.before)) continue;
        if (!same(state, record.after)) {conflicts.push({kind: 'text-style-changed', node_id: record.node.id, actual: state}); continue;}
        await record.node.setTextStyleIdAsync(record.before.style_id);
        if (!same(graphSyncTextState(record.node), record.before)) conflicts.push({kind: 'text-style-restore-differs', node_id: record.node.id, actual: graphSyncTextState(record.node)});
      } catch (error) {conflicts.push({kind: 'text-style-restore-failed', node_id: record.node.id, error: String(error)});}
      for (const record of records.values()) try {
        if (!same(graphSyncTextState(record.node), record.before) && !conflicts.some(item => item.node_id === record.node.id && item.kind.startsWith('text-style-'))) conflicts.push({kind: 'text-style-restore-differs', node_id: record.node.id, actual: graphSyncTextState(record.node)});
      } catch (error) {conflicts.push({kind: 'text-style-restore-failed', node_id: record.node.id, error: String(error)});}
      for (const style of styles) try {
        if (!same(styleState(style), expectedStyles.get(style.id))) {conflicts.push({kind: 'created-text-style-changed', style_id: style.id}); continue;}
        if (typeof style.getStyleConsumersAsync !== 'function' || (await style.getStyleConsumersAsync()).length) {conflicts.push({kind: 'created-text-style-referenced', style_id: style.id}); continue;}
        style.remove();
      } catch (error) {conflicts.push({kind: 'text-style-cleanup-failed', style_id: style.id, error: String(error)});}
    }
  };
}

function graphSyncRestoreLiteral(node, field, value) {
  if (graphSyncPaintField(field)) {
    const paint = graphSyncPaint(node, field); const {a = 1, ...color} = value;
    node[graphSyncNativeField(field)] = [{...paint, color, opacity: a}];
  } else if (field === 'fontFamily') for (const font of node.getRangeAllFontNames(0, node.characters.length)) node.setRangeFontName(0, node.characters.length, {...font, family: value});
  else if (field === 'width' || field === 'height') node.resize(field === 'width' ? value : node.width, field === 'height' ? value : node.height);
  else node[graphSyncNativeField(field)] = value;
  if (graphSyncFieldBinding(node, field) !== null || !graphSyncEqual(graphSyncFieldValue(node, field), value)) throw Error(`Graph token sync: literal restoration differs: ${node.id}.${field}`);
}
function graphSyncRollbackError(error, plan, conflicts) {
  const combined = [...(error.rollback_conflicts || []), ...conflicts];
  error.rollback_conflicts = combined;
  error.readback = {schema: 'figma-flow-graph-token-readback-v1', operation: 'apply',
    file_key: plan.file_key, page_id: plan.page_id, collection_id: plan.collection_id,
    status: combined.length ? 'rollback-conflict' : 'rolled-back', binding_diagnostics: error.binding_diagnostics || null, error: error.message || String(error), stack: error.stack || null, rollback_conflicts: combined};
  if (conflicts.length) error.message += `; rollback conflicts: ${conflicts.map(item => item.kind).join(', ')}`;
  error.readback.error = error.message || String(error);
  return error;
}
async function graphSyncPages(figma, plan) {
  const ids = plan.allowed_page_ids || [plan.page_id];
  if (!Array.isArray(ids) || !ids.includes(plan.page_id) || new Set(ids).size !== ids.length) throw Error('Graph token sync: invalid allowed pages');
  const candidates = figma.root?.children || [figma.currentPage];
  const pages = [];
  for (const id of ids) {
    const page = candidates.find(item => item.id === id && (item.type === 'PAGE' || item === figma.currentPage));
    if (!page) throw Error(`Graph token sync: allowed page unavailable: ${id}`);
    await page.loadAsync(); pages.push(page);
  }
  return pages;
}
async function graphSyncConsumerGuard(figma, admittedPages, consumers, rootIds) {
  const fail = message => {throw Error(`Graph token sync: ${message}`);};
  const pages = (figma.root?.children || admittedPages).filter(page => !page.type || page.type === 'PAGE');
  for (const page of pages) await page.loadAsync();
  const variables = new Map();
  if (typeof figma.variables.getLocalVariablesAsync === 'function') for (const variable of await figma.variables.getLocalVariablesAsync()) variables.set(variable.id, variable);
  const aliases = value => {
    if (!value || typeof value !== 'object') return [];
    if (value.type === 'VARIABLE_ALIAS') return [value.id];
    return Object.values(value).flatMap(aliases);
  };
  const bindings = node => {
    const result = Object.entries(node.boundVariables || {});
    for (const field of ['fills', 'strokes', 'effects']) if (Array.isArray(node[field])) result.push([field, node[field]]);
    if (node.type === 'TEXT' && typeof node.getStyledTextSegments === 'function') for (const segment of node.getStyledTextSegments(['boundVariables'])) result.push(...Object.entries(segment.boundVariables || {}));
    if (node.type === 'TEXT' && node.characters.length && typeof node.getRangeBoundVariable === 'function') for (const field of ['fontFamily', 'fontSize']) result.push([field, node.getRangeBoundVariable(0, node.characters.length, field)]);
    return result;
  };
  const allNodes = () => pages.flatMap(page => [page, ...page.findAll(() => true)]);
  const preload = async (id, ancestors = new Set()) => {
    if (ancestors.has(id)) fail('cyclic fanout alias');
    if (!variables.has(id)) variables.set(id, await figma.variables.getVariableByIdAsync(id));
    const variable = variables.get(id);
    if (!variable) fail(`fanout variable unavailable: ${id}`);
    const seen = new Set(ancestors); seen.add(id);
    for (const alias of aliases(variable.valuesByMode)) await preload(alias, seen);
  };
  for (const node of allNodes()) for (const [, value] of bindings(node)) for (const id of aliases(value)) await preload(id);
  const instanceIds = new Set(allNodes().filter(node => node.type === 'INSTANCE').map(node => node.id));
  const rootFor = (id, ancestors = new Set()) => {
    if (rootIds.has(id)) return id;
    if (ancestors.has(id)) fail('cyclic fanout alias');
    const variable = variables.get(id);
    if (!variable) fail(`consumer variable topology changed: ${id}`);
    const seen = new Set(ancestors); seen.add(id);
    for (const alias of aliases(variable.valuesByMode)) {const root = rootFor(alias, seen); if (root) return root;}
    return null;
  };
  return () => {
    const currentPages = (figma.root?.children || admittedPages).filter(page => !page.type || page.type === 'PAGE');
    if (currentPages.length !== pages.length || currentPages.some(page => !pages.some(original => original.id === page.id))) fail('page closure changed during transaction');
    const nodes = allNodes();
    const liveInstances = nodes.filter(node => node.type === 'INSTANCE');
    if (liveInstances.length !== instanceIds.size || liveInstances.some(node => !instanceIds.has(node.id))) fail('instance closure changed during transaction');
    for (const node of nodes) for (const [field, value] of bindings(node)) for (const id of aliases(value)) if (rootFor(id) && !consumers.some(item => item.node.id === node.id && graphSyncNativeField(item.field) === field || item.node.id === node.id && item.field === 'borderRadius' && ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius'].includes(field))) fail(`unplanned shared root consumer: ${node.id}.${field}`);
  };
}
async function graphTokenSync(figma, syncPlan, operation = 'inspect') {
  const plan = syncPlan;
  if (plan?.tokens?.some(token => token.create)) return graphTokenPairMigration(figma, plan, operation);
  const fail = message => { throw Error(`Graph token sync: ${message}`); };
  const copy = value => JSON.parse(JSON.stringify(value));
  const same = graphSyncEqual;
  const markerKey = 'graphSSOT';
  const fields = GRAPH_SYNC_FIELDS;
  if (!plan || plan.schema !== GRAPH_SYNC_SCHEMA || !['inspect', 'apply'].includes(operation)) fail('invalid plan or operation');
  if (!/^[a-f0-9]{64}$/.test(plan.graph_sha256 || '')) fail('graph SHA256 required');
  if (!plan.file_key || figma.fileKey !== plan.file_key || figma.currentPage.id !== plan.page_id) fail('wrong file or selected page');
  const page = figma.currentPage;
  await page.loadAsync();
  const collection = await figma.variables.getVariableCollectionByIdAsync(plan.collection_id);
  if (!collection || collection.id !== plan.collection_id || collection.remote || collection.modes.length !== 1) fail('exact local single-mode collection required');
  const mode = collection.defaultModeId;
  let owner;
  try { owner = JSON.parse(collection.getPluginData('bloomSemanticTokens') || 'null'); }
  catch (_) { fail('invalid collection ownership'); }
  if (owner?.pageId !== page.id || owner.collectionId !== collection.id) fail('collection page owner mismatch');
  const markerBefore = page.getPluginData(markerKey);
  let marker;
  try { marker = JSON.parse(markerBefore || 'null'); }
  catch (_) { fail('invalid page baseline'); }
  if (marker && (marker.page_id !== page.id || marker.collection_id !== collection.id)) fail('page baseline owner mismatch');
  if (operation === 'apply' && (marker ? marker.graph_sha256 !== plan.previous_graph_sha256 : plan.pairing !== true || plan.previous_graph_sha256)) fail('stale graph baseline or explicit pairing required');
  if (!Array.isArray(plan.tokens) || !plan.tokens.length || !Array.isArray(plan.components) || !plan.components.length) fail('tokens and components required');
  const tokens = new Map(), roots = new Map();
  const variable = async id => {
    if (!id || !collection.variableIds.includes(id)) fail(`variable outside collection: ${id}`);
    const item = await figma.variables.getVariableByIdAsync(id);
    if (!item || item.id !== id || item.remote || item.variableCollectionId !== collection.id) fail(`missing local variable: ${id}`);
    if (plan.system_id) {
      const ownership = JSON.parse(item.getPluginData('graphSSOT') || 'null');
      if (ownership?.system_id !== plan.system_id) fail(`variable belongs to another system: ${id}`);
    }
    return item;
  };
  const validValue = (type, value) => type === 'FLOAT' ? typeof value === 'number' && Number.isFinite(value) : type === 'STRING' ? typeof value === 'string' && value.length > 0 : type === 'BOOLEAN' ? typeof value === 'boolean' : type === 'COLOR' ? value && ['r', 'g', 'b'].every(key => Number.isFinite(value[key]) && value[key] >= 0 && value[key] <= 1) && (value.a === undefined || Number.isFinite(value.a) && value.a >= 0 && value.a <= 1) : false;
  for (const token of plan.tokens) {
    if (!token.key || tokens.has(token.key) || !validValue(token.type, token.value)) fail('invalid or duplicate token');
    const bound = await variable(token.variable_id);
    if (bound.name !== token.variable_name || bound.resolvedType !== token.type) fail(`variable identity/type mismatch: ${token.key}`);
    let root = bound;
    const chain = [], seen = new Set();
    while (true) {
      if (seen.has(root.id) || root.resolvedType !== token.type) fail(`invalid alias topology: ${token.key}`);
      seen.add(root.id);
      const value = root.valuesByMode[mode];
      chain.push({id: root.id, value: copy(value), variable: root});
      if (!value || value.type !== 'VARIABLE_ALIAS') break;
      root = await variable(value.id);
    }
    if (!token.root_variable_id || root.id !== token.root_variable_id || !validValue(token.type, root.valuesByMode[mode])) fail(`root identity/type mismatch: ${token.key}`);
    if (token.alias_chain && !same(token.alias_chain, chain.map(item => item.id))) fail(`alias topology changed: ${token.key}`);
    if (operation === 'apply' && (!Object.prototype.hasOwnProperty.call(token, 'before') || !same(token.before, root.valuesByMode[mode]))) fail(`stale before value: ${token.key}`);
    if (token.root_variable_name && root.name !== token.root_variable_name) fail(`root variable name changed: ${token.key}`);
    const prior = roots.get(root.id);
    if (prior && !same(prior.value, token.value)) fail(`conflicting root values: ${root.id}`);
    roots.set(root.id, {root, value: token.value, before: copy(root.valuesByMode[mode])});
    tokens.set(token.key, {token, bound, root, chain});
  }
  const pages = await graphSyncPages(figma, plan);
  const nodePages = new Map();
  const nodes = pages.flatMap(item => {const rows = [item, ...item.findAll(() => true)]; for (const row of rows) nodePages.set(row.id, item.id); return rows;});
  const find = key => {
    const matches = nodes.filter(node => node.id === key || node.getPluginData('semanticKey') === key);
    if (matches.length !== 1) fail(`missing or ambiguous node: ${key}`);
    return matches[0];
  };
  const consumers = [], groups = [], sources = new Map();
  const repairs = new Map();
  for (const repair of plan.repair_bindings || []) {
    const slot = `${repair.node_id}:${repair.field}`;
    if (repairs.has(slot) || !tokens.has(repair.token) || !fields.has(repair.field) || !(repair.before_variable_id === null || typeof repair.before_variable_id === 'string') || !Object.prototype.hasOwnProperty.call(repair, 'before_value')) fail('invalid repair binding');
    repairs.set(slot, repair);
  }
  const nodeInInstance = node => {
    for (let parent = node; parent; parent = parent.parent) if (parent.type === 'INSTANCE') return true;
    return groups.some(item => item.node.type === 'INSTANCE' && item.node.findAll?.(child => child.id === node.id).length);
  };
  const binding = graphSyncFieldBinding;
  const actual = graphSyncFieldValue;
  for (const component of plan.components) {
    if (!component.id || !component.main_keys?.length || !component.instance_keys?.length || !component.properties || !Object.keys(component.properties).length) fail('main and instance scope required');
    const mains = component.main_keys.map(find), instances = component.instance_keys.map(find);
    for (const main of mains) if (typeof main.getInstancesAsync === 'function') {
      const fanout = await main.getInstancesAsync();
      if (fanout.some(instance => !instances.some(item => item.id === instance.id))) fail(`undeclared component instance: ${main.id}`);
    } else if (plan.system_id) fail('native instance fanout API required');
    if (mains.some(node => node.type !== 'COMPONENT') || instances.some(node => node.type !== 'INSTANCE')) fail('component/instance types required');
    for (const node of [...mains, ...instances]) if (plan.node_page_ids && plan.node_page_ids[node.id] !== nodePages.get(node.id)) fail(`native node page mismatch: ${node.id}`);
    for (const instance of instances) {
      const main = await instance.getMainComponentAsync();
      if (!main || !mains.some(node => node.id === main.id)) fail(`instance source mismatch: ${instance.id}`);
      sources.set(instance.id, main.id);
    }
    for (const node of [...mains, ...instances]) {
      for (const [field, key] of Object.entries(component.properties)) {
        if (!fields.has(field) || !tokens.has(key)) fail(`unsupported field/token: ${field}`);
        const entry = tokens.get(key);
        if (entry.token.type !== graphSyncFieldType(field)) fail(`consumer type mismatch: ${field}`);
        const candidates = graphSyncTextField(field) ? [node, ...(node.findAll ? node.findAll(child => child.type === 'TEXT') : [])].filter(child => child.type === 'TEXT') : [node];
        if (!candidates.length) fail(`missing text consumer: ${node.id}`);
        for (const target of candidates) {
          const alias = binding(target, field);
          const repair = repairs.get(`${target.id}:${field}`);
          if (repair && (repair.token !== key || (alias?.id || null) !== repair.before_variable_id || !same(actual(target, field), repair.before_value))) fail(`stale repair binding: ${target.id}.${field}`);
          const mismatch = !alias || alias.type !== 'VARIABLE_ALIAS' || alias.id !== entry.bound.id || !same(actual(target, field), entry.root.valuesByMode[mode]);
          if (operation === 'apply' && mismatch && !repair) {
            const error = Error(`Graph token sync: ${alias?.id !== entry.bound.id ? 'binding mismatch' : 'native getter mismatch'}: ${target.id}.${field}`);
            const aggregate = target.boundVariables?.[field];
            error.binding_diagnostics = {node_id: target.id, field, expected_variable_id: entry.bound.id, effective_range_binding: alias,
              aggregate_bindings: (Array.isArray(aggregate) ? aggregate : [aggregate]).slice(0, 8).map(item => item?.id || null),
              text_style_id: typeof target.textStyleId === 'string' ? target.textStyleId.slice(0, 200) : null};
            throw error;
          }
          consumers.push({node: target, field, entry, repair, source: sources.get(node.id) || node.id, source_node: node});
        }
      }
      groups.push({id: component.id, node});
    }
  }
  for (const slot of repairs.keys()) if (!consumers.some(item => `${item.node.id}:${item.field}` === slot)) fail('repair outside declared consumers');
  const guardScope = await graphSyncConsumerGuard(figma, pages, consumers, new Set([...roots.keys()]));
  guardScope();
  const flush = async () => {
    // Export awaits native layout and bound typography propagation.
    for (const {node} of groups) await node.exportAsync({format: 'PNG', constraint: {type: 'SCALE', value: 1}});
  };
  const geometry = () => {
    for (const {node} of groups) {
      if (![node.width, node.height].every(value => Number.isFinite(value) && value > 0)) fail(`invalid geometry: ${node.id}`);
      const labels = node.findAll ? node.findAll(child => child.type === 'TEXT') : [];
      for (const label of labels) {
        const widthBudget = node.width - node.paddingLeft - node.paddingRight;
        const heightBudget = node.height - node.paddingTop - node.paddingBottom;
        // Native text bounds can round fractional layout budgets to whole pixels.
        if (![label.width, label.height].every(value => Number.isFinite(value) && value > 0) || label.width > widthBudget + 1 || label.height > heightBudget + 1) fail(`label exceeds width/height budget: ${label.id}; actual ${label.width}x${label.height}, budget ${widthBudget}x${heightBudget}, tolerance 1px`);
      }
    }
  };
  const readback = () => ({
    schema: 'figma-flow-graph-token-readback-v1', operation,
    file_key: figma.fileKey, page_id: page.id, collection_id: collection.id, allowed_page_ids: pages.map(item => item.id),
    graph_sha256: JSON.parse(page.getPluginData(markerKey) || 'null')?.graph_sha256 || null,
    baseline: JSON.parse(page.getPluginData(markerKey) || 'null'),
    tokens: [...tokens.values()].map(({token, bound, root, chain}) => ({
      key: token.key, variable_id: bound.id, variable_name: bound.name, type: bound.resolvedType,
      valuesByMode: copy(bound.valuesByMode), root_variable_id: root.id,
      root_valuesByMode: copy(root.valuesByMode), alias_chain: chain.map(item => item.id),
      resolved: copy(root.valuesByMode[mode])
    })),
    unsupported_changes: groups.filter(({node}) => node.type === 'INSTANCE').flatMap(({node}) => (node.overrides || []).flatMap(item => (item.overriddenFields || []).filter(field => !fields.has(field) && !['boundVariables', 'fontName'].includes(field)).map(field => ({node_id: item.id || node.id, field, reason: 'instance override outside supported token fields; change timing unverified'})))),
    components: groups.map(({id, node}) => ({
      id, node_id: node.id, page_id: nodePages.get(node.id), type: node.type,
      main_component_id: node.type === 'INSTANCE' ? sources.get(node.id) : node.id,
      width: node.width, height: node.height, layoutSizingHorizontal: node.layoutSizingHorizontal || null, layoutSizingVertical: node.layoutSizingVertical || null,
      consumers: consumers.filter(item => item.node === node || node.findAll?.(child => child.id === item.node.id).length)
        .map(({node: target, field, entry, source, source_node}) => {
          const bound = binding(target, field), value = actual(target, field);
          const changedBinding = bound?.id !== entry.bound.id;
          const override = changedBinding || !same(value, entry.root.valuesByMode[mode]);
          return {node_id: target.id, field, token: entry.token.key, source_main_component_id: source,
          source_node_id: source_node.id, value: copy(value), binding: bound ? copy(bound) : null,
          expected_value: copy(entry.token.value), root_value: copy(entry.root.valuesByMode[mode]),
          expected_variable_id: entry.bound.id, root_variable_id: entry.root.id, changedBinding, override,
          classification: changedBinding ? bound ? 'binding-changed' : 'detached-override' : override ? 'getter-override' : !same(value, entry.token.value) ? 'variable-drift' : 'canonical',
          width: target.width, height: target.height};})
    }))
  });
  if (operation === 'apply') {
    for (const {node, field, entry} of consumers) {
      if (node.type !== 'TEXT' || !field.startsWith('font')) continue;
      for (const font of node.getRangeAllFontNames(0, node.characters.length)) await figma.loadFontAsync(field === 'fontFamily' ? {...font, family: entry.token.value} : font);
    }
    for (const {node} of groups) if (node.type === 'INSTANCE' && (await node.getMainComponentAsync())?.id !== sources.get(node.id)) fail('instance source changed during preflight');
    for (const {node} of groups) if (node.type === 'COMPONENT' && typeof node.getInstancesAsync === 'function' && (await node.getInstancesAsync()).some(instance => !groups.some(item => item.node.type === 'INSTANCE' && item.node.id === instance.id))) fail('undeclared component instance during preflight');
    for (const {node, field, entry, repair} of consumers) {
      graphSyncWritable(node, field);
      if (repair ? (binding(node, field)?.id || null) !== repair.before_variable_id || !same(actual(node, field), repair.before_value) : binding(node, field)?.id !== entry.bound.id || !same(actual(node, field), entry.root.valuesByMode[mode])) fail('consumer changed during preflight');
    }
    // Font loading yields; check the full compare-and-set guard again before writes.
    if (figma.fileKey !== plan.file_key || figma.currentPage.id !== page.id || page.getPluginData(markerKey) !== markerBefore) fail('scope or baseline changed during preflight');
    for (const {root, before} of roots.values()) if (!same(root.valuesByMode[mode], before)) fail('before value changed during preflight');
    for (const {chain} of tokens.values()) for (const item of chain) if (!same((await variable(item.id)).valuesByMode[mode], item.value)) fail('alias topology changed during preflight');
    const writes = [], bindingWrites = [];
    const bindRepair = (node, field, variable) => graphSyncBindField(figma, node, field, variable);
    const repairBeforeVariables = new Map();
    for (const repair of repairs.values()) if (repair.before_variable_id) repairBeforeVariables.set(repair.before_variable_id, await figma.variables.getVariableByIdAsync(repair.before_variable_id));
    guardScope();
    for (const {root, before} of roots.values()) if (!same(root.valuesByMode[mode], before)) fail('before value changed before mutation');
    let markerWritten = null;
    try {
      const ordered = [...consumers.filter(item => !nodeInInstance(item.node)), ...consumers.filter(item => nodeInInstance(item.node))];
      for (const {node, field, entry, repair} of ordered) if (repair) {
        const live = binding(node, field);
        if (live?.id === entry.bound.id && same(actual(node, field), entry.root.valuesByMode[mode])) continue;
        if ((live?.id || null) !== repair.before_variable_id || !same(actual(node, field), repair.before_value)) fail('repair changed before mutation');
        bindingWrites.push({node, field, repair, written: entry.bound.id});
        bindRepair(node, field, entry.bound);
      }
      for (const {root, value, before} of roots.values()) if (!same(value, before)) {
        writes.push({root, before, written: copy(value)});
        root.setValueForMode(mode, value);
      }
      await flush();
      if (figma.fileKey !== plan.file_key || figma.currentPage.id !== page.id || page.getPluginData(markerKey) !== markerBefore) fail('scope or baseline changed during apply');
      for (const {root, value} of roots.values()) if (!same(root.valuesByMode[mode], value)) fail(`canonical root getter differs: ${root.id}`);
      for (const {chain} of tokens.values()) for (const item of chain.slice(0, -1)) if (!same(item.variable.valuesByMode[mode], item.value)) fail('alias topology changed during apply');
      for (const {node} of groups) if (node.type === 'INSTANCE' && (await node.getMainComponentAsync())?.id !== sources.get(node.id)) fail('instance source changed during apply');
      for (const {node} of groups) if (node.type === 'COMPONENT' && typeof node.getInstancesAsync === 'function' && (await node.getInstancesAsync()).some(instance => !groups.some(item => item.node.type === 'INSTANCE' && item.node.id === instance.id))) fail('undeclared component instance during apply');
      for (const {node, field, entry} of consumers) if (!same(actual(node, field), entry.token.value) || binding(node, field)?.id !== entry.bound.id) fail(`canonical native getter differs: ${node.id}.${field}`);
      guardScope();
      geometry();
      markerWritten = JSON.stringify({page_id: page.id, collection_id: collection.id, graph_sha256: plan.graph_sha256, system_id: plan.system_id, namespace: plan.namespace, owned_variable_ids: [...new Set([...tokens.values()].flatMap(item => item.chain.map(part => part.id)))], token_topology: [...tokens.values()].map(({token, chain}) => ({key: token.key, variable_ids: chain.map(item => item.id)})), consumers: consumers.map(({node, field, entry}) => ({node_id: node.id, page_id: nodePages.get(node.id), field, token: entry.token.key}))});
      page.setPluginData(markerKey, markerWritten);
      return readback();
    } catch (error) {
      const conflicts = [];
      for (const {node, field, repair, written} of bindingWrites.reverse()) try {
        const live = binding(node, field);
        if (live?.id === written) {
          bindRepair(node, field, repair.before_variable_id ? repairBeforeVariables.get(repair.before_variable_id) : null);
          if (!repair.before_variable_id) {
            graphSyncRestoreLiteral(node, field, repair.before_value);
          }
        } else if ((live?.id || null) !== repair.before_variable_id) conflicts.push({kind: 'binding-changed', node_id: node.id, field, actual: live || null});
      } catch (failure) {conflicts.push({kind: 'binding-restore-failed', node_id: node.id, field, error: String(failure)});}
      for (const {root, before, written} of writes.reverse()) try {
        const live = root.valuesByMode[mode];
        if (same(live, written)) root.setValueForMode(mode, before);
        else if (!same(live, before)) conflicts.push({kind: 'root-changed', variable_id: root.id, before, written, actual: copy(live)});
      } catch (failure) {conflicts.push({kind: 'root-restore-failed', variable_id: root.id, error: String(failure)});}
      try {
        const live = page.getPluginData(markerKey);
        if (markerWritten !== null && live === markerWritten) page.setPluginData(markerKey, markerBefore);
        else if (live !== markerBefore) conflicts.push({kind: 'marker-changed', actual: live});
        await flush();
      } catch (failure) {conflicts.push({kind: 'rollback-layout-failed', error: String(failure)});}
      throw graphSyncRollbackError(error, plan, conflicts);
    }
  }
  return readback();
}
async function graphTokenPairMigration(figma, plan, operation) {
  const fail = message => {throw Error(`Graph token pairing: ${message}`);};
  const same = graphSyncEqual;
  const clone = value => JSON.parse(JSON.stringify(value));
  if (plan.schema !== GRAPH_SYNC_SCHEMA || !['inspect', 'apply'].includes(operation) || !/^[a-f0-9]{64}$/.test(plan.graph_sha256 || '')) fail('invalid plan');
  if (plan.pairing !== true) fail('create requires explicit all-new pairing or topology extension');
  if (!plan.file_key || figma.fileKey !== plan.file_key || figma.currentPage.id !== plan.page_id) fail('wrong file or selected page');
  const page = figma.currentPage;
  await page.loadAsync();
  const collection = await figma.variables.getVariableCollectionByIdAsync(plan.collection_id);
  if (!collection || collection.remote || collection.modes.length !== 1) fail('exact local single-mode collection required');
  const owner = JSON.parse(collection.getPluginData('bloomSemanticTokens') || 'null');
  if (owner?.pageId !== page.id || owner.collectionId !== collection.id) fail('collection page owner mismatch');
  const markerBefore = page.getPluginData('graphSSOT');
  const marker = JSON.parse(markerBefore || 'null');
  if (marker && (marker.page_id !== page.id || marker.collection_id !== collection.id || marker.graph_sha256 !== plan.previous_graph_sha256) || !marker && plan.previous_graph_sha256) fail('stale pairing baseline');
  const mode = collection.defaultModeId;
  if (typeof plan.system_id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(plan.system_id) || plan.namespace !== `ssot/${plan.system_id}`) fail('generic system ID and namespace required');
  const definitions = new Map(), edges = new Map(), reused = new Map();
  const valid = (type, value) => type === 'FLOAT' ? Number.isFinite(value) : type === 'STRING' ? typeof value === 'string' && !!value : type === 'BOOLEAN' ? typeof value === 'boolean' : type === 'COLOR' && value && ['r', 'g', 'b'].every(key => Number.isFinite(value[key]) && value[key] >= 0 && value[key] <= 1) && (value.a === undefined || Number.isFinite(value.a) && value.a >= 0 && value.a <= 1);
  const tokenByKey = new Map();
  for (const token of plan.tokens) {
    if (!token.key || tokenByKey.has(token.key) || !valid(token.type, token.value)) fail('invalid create token');
    tokenByKey.set(token.key, token);
    if (!token.create) continue;
    if (token.variable_id || token.root_variable_id) fail('new token already has native IDs');
    const chain = token.alias_chain_names || (token.variable_name === token.root_variable_name ? [token.variable_name] : [token.variable_name, token.root_variable_name]);
    if (!chain.length || chain[0] !== token.variable_name || chain[chain.length - 1] !== token.root_variable_name || new Set(chain).size !== chain.length) fail('invalid create alias chain');
    for (let index = 0; index < chain.length; index++) {
      const name = chain[index], alias = chain[index + 1] || null;
      if (typeof name !== 'string' || !name.startsWith(`${plan.namespace}/`) || !/^[A-Za-z0-9_/-]+$/.test(name)) fail('new variable must use declared system namespace');
      const definition = {type: token.type, alias, value: alias ? null : token.value};
      if (definitions.has(name) && !same(definitions.get(name), definition)) fail(`conflicting new variable: ${name}`);
      definitions.set(name, definition); edges.set(name, alias);
    }
  }
  for (const name of definitions.keys()) {
    const seen = new Set();
    for (let current = name; current; current = edges.get(current)) {if (seen.has(current)) fail('cyclic create alias'); seen.add(current);}
  }
  for (const id of collection.variableIds) {
    const item = await figma.variables.getVariableByIdAsync(id);
    if (definitions.has(item?.name)) {
      const definition = definitions.get(item.name);
      const ownership = JSON.parse(item.getPluginData('graphSSOT') || 'null');
      if (definition.alias || plan.tokens.some(token => token.create && token.variable_name === item.name) || ownership?.system_id !== plan.system_id || item.resolvedType !== definition.type || !same(item.valuesByMode[mode], definition.value)) fail(`new variable name already exists: ${item.name}`);
      reused.set(item.name, item);
    }
  }
  const pages = await graphSyncPages(figma, plan);
  const nodePages = new Map();
  const nodes = pages.flatMap(item => {const rows = [item, ...item.findAll(() => true)]; for (const row of rows) nodePages.set(row.id, item.id); return rows;});
  const exact = id => {const matches = nodes.filter(node => node.id === id); if (matches.length !== 1) fail(`exact native node ID required: ${id}`); return matches[0];};
  const aliasOf = graphSyncFieldBinding;
  const valueOf = graphSyncFieldValue;
  const existingTokens = plan.tokens.filter(token => !token.create);
  if (existingTokens.length) {
    if (!marker || marker.system_id !== plan.system_id) fail('topology extension requires existing system pairing');
    const components = plan.components.map(component => ({...component, properties: Object.fromEntries(Object.entries(component.properties).filter(([, key]) => !tokenByKey.get(key)?.create))})).filter(component => Object.keys(component.properties).length);
    const observed = await graphTokenSync(figma, {...plan, tokens: existingTokens, components}, 'inspect');
    if (observed.tokens.some(token => !same(token.resolved, tokenByKey.get(token.key).value)) || observed.components.some(component => component.consumers.some(consumer => consumer.override))) fail('existing owned tokens must stay canonical during topology extension');
  }
  const migrations = [], slots = new Set();
  if (!Array.isArray(plan.migrations) || !plan.migrations.length || !Array.isArray(plan.components) || !plan.components.length) fail('exact migration consumers required');
  const required = new Map(), mainTargets = new Set();
  for (const component of plan.components) {
    if (!component.main_keys?.length || !component.instance_keys?.length) fail('main and instance scope required');
    const mains = component.main_keys.map(exact), instances = component.instance_keys.map(exact);
    if (mains.some(node => node.type !== 'COMPONENT') || instances.some(node => node.type !== 'INSTANCE')) fail('component/instance type required');
    for (const node of [...mains, ...instances]) if (plan.node_page_ids && plan.node_page_ids[node.id] !== nodePages.get(node.id)) fail(`native node page mismatch: ${node.id}`);
    if (operation === 'apply') for (const main of mains) {
      if (typeof main.getInstancesAsync !== 'function') fail('native instance fanout API required');
      if ((await main.getInstancesAsync()).some(instance => !instances.some(item => item.id === instance.id))) fail(`undeclared component instance: ${main.id}`);
    }
    for (const instance of instances) {
      const source = await instance.getMainComponentAsync();
      if (!source || !mains.some(main => main.id === source.id)) fail(`instance source mismatch: ${instance.id}`);
    }
    for (const node of [...mains, ...instances]) for (const [field, key] of Object.entries(component.properties || {})) {
      if (!GRAPH_SYNC_FIELDS.has(field) || !tokenByKey.has(key)) fail('unsupported migration property');
      if (tokenByKey.get(key).type !== graphSyncFieldType(field)) fail('migration property type mismatch');
      if (!tokenByKey.get(key).create) continue;
      const targets = graphSyncTextField(field) ? node.findAll(child => child.type === 'TEXT') : [node];
      if (!targets.length) fail('missing migration text');
      for (const target of targets) {
        const slot = `${target.id}:${field}`;
        if (required.has(slot)) fail('duplicate migration consumer');
        required.set(slot, key); if (mains.includes(node)) mainTargets.add(slot);
      }
    }
  }
  for (const migration of plan.migrations) {
    const slot = `${migration.node_id}:${migration.field}`;
    if (slots.has(slot) || required.get(slot) !== migration.token || !(migration.before_variable_id === null || typeof migration.before_variable_id === 'string')) fail('unplanned or duplicate migration');
    slots.add(slot);
    const node = exact(migration.node_id), alias = aliasOf(node, migration.field);
    if ((alias?.id || null) !== migration.before_variable_id || !same(valueOf(node, migration.field), migration.before_value)) fail(`stale migration consumer: ${slot}`);
    graphSyncWritable(node, migration.field);
    let variable = alias ? await figma.variables.getVariableByIdAsync(alias.id) : null;
    const seen = new Set();
    while (variable) {
      if (seen.has(variable.id) || variable.variableCollectionId !== collection.id || variable.resolvedType !== tokenByKey.get(migration.token).type) fail('invalid migration alias');
      seen.add(variable.id); const value = variable.valuesByMode[mode];
      if (value?.type !== 'VARIABLE_ALIAS') {if (!same(value, migration.before_value)) fail('stale migration root'); break;}
      variable = await figma.variables.getVariableByIdAsync(value.id);
    }
    if (alias && !variable) fail('missing migration variable');
    migrations.push({...migration, node, alias: alias ? clone(alias) : null, main: mainTargets.has(slot)});
  }
  if (slots.size !== required.size) fail('incomplete migration coverage');
  if (operation === 'inspect') return {schema: 'figma-flow-graph-token-readback-v1', operation, file_key: figma.fileKey, page_id: page.id, collection_id: collection.id, graph_sha256: marker?.graph_sha256 || null, baseline: marker, migration_pending: true, migrations: migrations.map(({node, field, token}) => ({node_id: node.id, field, token, binding: aliasOf(node, field) ? clone(aliasOf(node, field)) : null, value: valueOf(node, field), width: node.width, height: node.height}))};
  const guardPairScope = await graphSyncConsumerGuard(figma, pages, migrations.map(item => ({node: item.node, field: item.field})), new Set());
  for (const {node, field, token} of migrations) if (field.startsWith('font')) for (const font of node.getRangeAllFontNames(0, node.characters.length)) await figma.loadFontAsync(field === 'fontFamily' ? {...font, family: tokenByKey.get(token).value} : font);
  for (const component of plan.components) for (const id of component.main_keys) if ((await exact(id).getInstancesAsync()).some(instance => !component.instance_keys.includes(instance.id))) fail('undeclared component instance during pairing');
  guardPairScope();
  if (figma.fileKey !== plan.file_key || figma.currentPage.id !== page.id || page.getPluginData('graphSSOT') !== markerBefore) fail('scope or baseline changed during pairing');
  for (const migration of migrations) if ((aliasOf(migration.node, migration.field)?.id || null) !== migration.before_variable_id || !same(valueOf(migration.node, migration.field), migration.before_value)) fail('migration changed during preflight');
  const pairVariables = new Map(reused);
  const created = new Map(), createdExpected = new Map(), rebound = [];
  const snapshot = item => ({name: item.name, type: item.resolvedType, valuesByMode: clone(item.valuesByMode), ownership: item.getPluginData('graphSSOT')});
  const bindVariable = (node, field, variable) => graphSyncBindField(figma, node, field, variable);
  let textStyles = null;
  try {
    for (const [name, definition] of definitions) {
      if (reused.has(name)) continue;
      const item = figma.variables.createVariable(name, collection, definition.type);
      created.set(name, item); pairVariables.set(name, item);
      createdExpected.set(item.id, snapshot(item));
      item.setPluginData('graphSSOT', JSON.stringify({system_id: plan.system_id, key: [...tokenByKey.values()].find(token => token.variable_name === name)?.key || name}));
      createdExpected.set(item.id, snapshot(item));
    }
    for (const [name, definition] of definitions) {
      if (reused.has(name)) continue;
      const item = created.get(name);
      item.setValueForMode(mode, definition.alias ? {type: 'VARIABLE_ALIAS', id: pairVariables.get(definition.alias).id} : definition.value);
      createdExpected.set(item.id, snapshot(item));
    }
    textStyles = await graphSyncTextStyles(figma, migrations.map(item => ({...item, variable: pairVariables.get(tokenByKey.get(item.token).variable_name)})), plan.namespace);
    for (const migration of [...migrations.filter(item => item.main), ...migrations.filter(item => !item.main)]) {
      const variable = pairVariables.get(tokenByKey.get(migration.token).variable_name);
      const live = aliasOf(migration.node, migration.field);
      if (live?.id === variable.id && same(valueOf(migration.node, migration.field), tokenByKey.get(migration.token).value)) continue;
      if ((live?.id || null) !== migration.before_variable_id || !same(valueOf(migration.node, migration.field), migration.before_value)) fail('migration changed before rebinding');
      if (textStyles.handles(migration.node, migration.field)) {await textStyles.bind(migration.node); continue;}
      rebound.push({...migration, written_variable_id: variable.id});
      bindVariable(migration.node, migration.field, variable);
    }
    textStyles.mark();
    if (figma.fileKey !== plan.file_key || figma.currentPage.id !== page.id || page.getPluginData('graphSSOT') !== markerBefore) fail('scope or baseline changed during style migration');
    const adopted = {...plan, migrations: undefined, tokens: plan.tokens.map(token => token.create ? ({...token, create: undefined, before: token.value, variable_id: pairVariables.get(token.variable_name).id, root_variable_id: pairVariables.get(token.root_variable_name).id, alias_chain: (token.alias_chain_names || (token.variable_name === token.root_variable_name ? [token.variable_name] : [token.variable_name, token.root_variable_name])).map(name => pairVariables.get(name).id)}) : ({...token, before: token.value}))};
    const result = await graphTokenSync(figma, adopted, 'apply');
    result.tokens.forEach(token => {const source = tokenByKey.get(token.key); if (source.alias_chain_names) token.alias_chain_names = source.alias_chain_names; else if (source.create) token.alias_chain_names = source.variable_name === source.root_variable_name ? [source.variable_name] : [source.variable_name, source.root_variable_name];});
    return result;
  } catch (error) {
    const conflicts = [];
    if (textStyles) await textStyles.rollback(conflicts);
    for (const migration of rebound.reverse()) try {
      const old = migration.before_variable_id ? await figma.variables.getVariableByIdAsync(migration.before_variable_id) : null;
      const live = aliasOf(migration.node, migration.field);
      if (live?.id === migration.written_variable_id && (!migration.before_variable_id || old)) {
        bindVariable(migration.node, migration.field, old);
        if (!migration.before_variable_id) graphSyncRestoreLiteral(migration.node, migration.field, migration.before_value);
      }
      else if ((live?.id || null) !== migration.before_variable_id) conflicts.push({kind: 'binding-changed', node_id: migration.node.id, field: migration.field, actual: live || null});
    } catch (failure) {conflicts.push({kind: 'binding-restore-failed', node_id: migration.node.id, field: migration.field, error: String(failure)});}
    let retain = conflicts.some(item => item.kind === 'created-text-style-changed' || item.kind === 'created-text-style-referenced' || item.kind === 'text-style-cleanup-failed');
    const createdIds = new Set([...created.values()].map(item => item.id));
    const referencesCreated = value => {
      if (!value || typeof value !== 'object') return false;
      if (value.type === 'VARIABLE_ALIAS') return createdIds.has(value.id);
      return Object.values(value).some(referencesCreated);
    };
    try {
      const allPages = (figma.root?.children || pages).filter(item => !item.type || item.type === 'PAGE');
      for (const item of allPages) await item.loadAsync();
      const localVariables = typeof figma.variables.getLocalVariablesAsync === 'function' ? await figma.variables.getLocalVariablesAsync() : null;
      // Complete asynchronous reads first; compare references and delete without yielding.
      for (const item of created.values()) if (!same(snapshot(item), createdExpected.get(item.id))) {
        retain = true; conflicts.push({kind: 'created-variable-changed', variable_id: item.id});
      }
      for (const item of allPages) for (const node of item.findAll(() => true)) {
        let referenced = referencesCreated(node.boundVariables);
        for (const field of ['fills', 'strokes', 'effects']) if (Array.isArray(node[field])) referenced ||= referencesCreated(node[field]);
        if (node.type === 'TEXT' && node.characters.length && typeof node.getRangeBoundVariable === 'function') for (const field of ['fontFamily', 'fontSize']) referenced ||= referencesCreated(node.getRangeBoundVariable(0, node.characters.length, field));
        if (node.type === 'TEXT' && typeof node.getStyledTextSegments === 'function') referenced ||= node.getStyledTextSegments(['boundVariables']).some(segment => referencesCreated(segment.boundVariables));
        if (referenced) {retain = true; conflicts.push({kind: 'created-variable-referenced', node_id: node.id});}
      }
      if (!localVariables) {retain = true; conflicts.push({kind: 'variable-reference-check-unavailable'});}
      else for (const item of localVariables) if (!createdIds.has(item.id) && referencesCreated(item.valuesByMode)) {
        retain = true; conflicts.push({kind: 'created-variable-referenced', variable_id: item.id});
      }
    } catch (failure) {retain = true; conflicts.push({kind: 'variable-reference-check-failed', error: String(failure)});}
    if (!retain) for (const item of [...created.values()].reverse()) try {item.remove();} catch (failure) {conflicts.push({kind: 'variable-remove-failed', variable_id: item.id, error: String(failure)});}
    // The inner transaction owns its marker compensation; preserve any external replacement.
    const liveMarker = page.getPluginData('graphSSOT');
    if (liveMarker !== markerBefore && !(error.rollback_conflicts || []).some(item => item.kind === 'marker-changed')) conflicts.push({kind: 'marker-changed', actual: liveMarker});
    throw graphSyncRollbackError(error, plan, conflicts);
  }
}
if (typeof module !== 'undefined') module.exports = {graphTokenSync, commitGraphSelection};
function selectionDigest(text) {
  if (typeof require !== 'function') throw Error('selective apply digest is unavailable');
  return require('crypto').createHash('sha256').update(text).digest('hex');
}
function selectionIdentity(kind, key) {
  return selectionDigest(JSON.stringify({key, kind}));
}
function commitGraphSelection(payload, selection, observed) {
  if (!payload || payload.schema !== 'figma-flow-selective-sync-v1' || !observed || typeof observed !== 'object' || Array.isArray(observed)) {
    throw Error('selective apply requires observed values');
  }
  if (!Array.isArray(selection) || !selection.length) throw Error('empty selection');
  const aliasKeys = payload.alias_bundle.keys.slice();
  if (selection.some(key => aliasKeys.includes(key)) && (new Set(selection).size !== aliasKeys.length || selection.some(key => !aliasKeys.includes(key)))) {
    throw Error('partial alias bundle');
  }
  const independent = new Map(payload.independent.map(item => [item.key, item]));
  const wholeAlias = aliasKeys.length === new Set(selection).size && aliasKeys.every(key => selection.includes(key));
  const selected = new Set(wholeAlias ? aliasKeys : selection);
  if (!wholeAlias && [...selected].some(key => !independent.has(key))) throw Error('unknown selection');
  for (const key of selected) {
    const item = independent.get(key);
    if (item && observed[key] !== item.before) throw Error('stale before value: ' + key);
  }
  const bundleId = selectionIdentity('bundle', aliasKeys.join('|'));
  const changes = [
    ...payload.independent.map(item => ({identity: selectionIdentity('token', item.key), kind: 'token', key: item.key, bundle: null, selected: selected.has(item.key)})),
    ...aliasKeys.map(key => ({identity: selectionIdentity('token', key), kind: 'token', key, bundle: bundleId, selected: selected.has(key)})),
  ];
  const planSha = selectionDigest(JSON.stringify(changes.map(row => ({bundle: row.bundle, identity: row.identity, key: row.key, kind: row.kind}))));
  const values = {...observed};
  const applied = [];
  for (const row of changes) if (row.selected) {
    const item = independent.get(row.key);
    if (item) {
      values[row.key] = item.after;
      applied.push({key: row.key, value: values[row.key]});
    } else applied.push({key: row.key});
  }
  const skipped = changes.filter(row => !row.selected).map(row => ({key: row.key}));
  const baseline = {};
  for (const item of applied) if (Object.prototype.hasOwnProperty.call(item, 'value')) baseline[item.key] = item.value;
  return {applied, skipped, values, readback: {...values}, baseline, plan_sha256: planSha, full_apply: skipped.length === 0};
}
function graphSyncPlanForMessage(plan, message) {
  if (!message || message.selection == null) return plan;
  const committed = commitGraphSelection(message.fixture, message.selection, message.observed);
  const selected = new Set(committed.applied.map(item => item.key));
  return {...plan, tokens: (plan.tokens || []).filter(token => selected.has(token.key)), selection_baseline: committed.baseline, partial_apply: committed.full_apply !== true};
}
if (typeof GRAPH_SYNC_PLAN !== 'undefined' && typeof figma !== 'undefined') {
  figma.showUI(__html__, {width: 440, height: 470, themeColors: true});
  let busy = false;
  figma.ui.onmessage = async message => {
    if (busy || !['read', 'apply'].includes(message?.type) || message.session !== GRAPH_PANEL_SESSION) return;
    busy = true;
    figma.ui.postMessage({session: GRAPH_PANEL_SESSION, state: 'busy', operation: message.type});
    const plan = graphSyncPlanForMessage(GRAPH_SYNC_PLAN, message);
    try { figma.ui.postMessage({session: GRAPH_PANEL_SESSION, operation: message.type, readback: await graphTokenSync(figma, plan, message.type === 'apply' ? 'apply' : 'inspect')}); }
    catch (error) {
      const detail = error.message || String(error);
      const safely = getter => {try {return getter() ?? null;} catch (_) {return null;}};
      const readback = error.readback || {schema: 'figma-flow-graph-token-readback-v1', status: 'failed',
        operation: message.type === 'apply' ? 'apply' : 'inspect', error: detail, stack: error.stack || detail,
        file_key: safely(() => figma.fileKey), page_id: safely(() => figma.currentPage?.id),
        expected_scope: {file_key: GRAPH_SYNC_PLAN.file_key, page_id: GRAPH_SYNC_PLAN.page_id, collection_id: GRAPH_SYNC_PLAN.collection_id},
        rollback_conflicts: error.rollback_conflicts || []};
      figma.ui.postMessage({session: GRAPH_PANEL_SESSION, operation: message.type, error: detail, readback, rollback_conflicts: error.rollback_conflicts || []});
    }
    finally { busy = false; }
  };
}
