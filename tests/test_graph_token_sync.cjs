const test = require('node:test');
const assert = require('node:assert/strict');
const {graphTokenSync} = require('../figma-bridge/graph_token_sync.js');

function world() {
  const state = {writes: 0, marker: '', exports: 0, fonts: []};
  const values = new Map();
  const variable = (id, name, type, value) => {
    const result = {id, name, resolvedType: type, variableCollectionId: 'collection', valuesByMode: {mode: value}, setValueForMode(mode, next) {state.writes++; this.valuesByMode[mode] = next;}};
    values.set(id, result); return result;
  };
  const root = variable('root', 'b/size/button', 'FLOAT', 14);
  variable('alias', 'b/type/button', 'FLOAT', {type: 'VARIABLE_ALIAS', id: 'root'});
  const family = variable('family', 'b/font/family', 'STRING', 'Inter');
  const scalar = id => {const value = values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? scalar(value.id) : value;};
  const node = (id, type) => ({id, type, getPluginData() {return '';}, width: 100, height: 40, paddingLeft: 10, paddingRight: 10, paddingTop: 4, paddingBottom: 4,
    findAll(fn) {return (this.children || []).filter(fn);}, async exportAsync() {state.exports++; if(state.exportFailure) throw Error('export failure'); return new Uint8Array();}});
  const main = node('main', 'COMPONENT'), instance = node('instance', 'INSTANCE');
  instance.getMainComponentAsync = async () => state.wrongSource ? {id: 'other'} : main;
  const text = id => {
    const result = node(id, 'TEXT'); result.characters = 'Label'; result.width = 40; result.height = 16;
    Object.defineProperty(result, 'fontSize', {configurable: true, get: () => state.override || scalar('alias')});
    result.boundVariables = {fontSize: [{type: 'VARIABLE_ALIAS', id: 'alias'}]};
    result.getRangeBoundVariable = (start, end, field) => field === 'fontSize' ? result.boundVariables.fontSize?.[0] || null : field === 'fontFamily' ? {type: 'VARIABLE_ALIAS', id: 'family'} : null;
    result.getRangeAllFontNames = () => [{family: scalar('family'), style: 'Regular'}];
    return result;
  };
  main.children = [text('label')]; instance.children = [text('copy')];
  const nodes = [main, ...main.children, instance, ...instance.children];
  const page = {id: 'page', async loadAsync() {}, findAll(fn) {return nodes.filter(fn);}, getPluginData() {return state.marker;}, setPluginData(key, value) {state.marker = value;}};
  const collection = {id: 'collection', defaultModeId: 'mode', modes: [{modeId: 'mode'}], variableIds: [...values.keys()], getPluginData() {return JSON.stringify({pageId: 'page', collectionId: 'collection'});}};
  const figma = {fileKey: 'file', currentPage: page, async loadFontAsync(font) {state.fonts.push(font); if(state.onFont) state.onFont();}, variables: {async getVariableByIdAsync(id) {return values.get(id);}, async getVariableCollectionByIdAsync(id) {return id === 'collection' ? collection : null;}}};
  const plan = {schema: 'figma-flow-graph-token-sync-v1', graph_sha256: 'a'.repeat(64), file_key: 'file', page_id: 'page', collection_id: 'collection', pairing: true,
    tokens: [{key: 'b/type/button', type: 'FLOAT', value: 18, before: 14, variable_name: 'b/type/button', variable_id: 'alias', root_variable_id: 'root', alias_chain: ['alias', 'root']}, {key: 'b/font/family', type: 'STRING', value: 'Roboto', before: 'Inter', variable_name: 'b/font/family', variable_id: 'family', root_variable_id: 'family'}],
    components: [{id: 'button', main_keys: ['main'], instance_keys: ['instance'], properties: {fontSize: 'b/type/button', fontFamily: 'b/font/family'}}]};
  return {state, figma, plan, values, root, family, main, instance};
}

test('inspect reads actual aliases and getters without writes or graph marker changes', async () => {
  const w = world(); const read = await graphTokenSync(w.figma, w.plan);
  assert.equal(w.state.writes, 0); assert.equal(w.state.marker, ''); assert.equal(w.state.exports, 0);
  assert.equal(read.tokens[0].resolved, 14); assert.deepEqual(read.tokens[0].alias_chain, ['alias', 'root']);
  assert.equal(read.components[1].main_component_id, 'main');
  assert.equal(read.components[1].consumers[0].value, 14);
});

test('apply edits only scalar roots, checks direct inherited getters and saves graph baseline', async () => {
  const w = world(); const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(w.state.writes, 2); assert.equal(w.state.exports, 2);
  assert.deepEqual(w.values.get('alias').valuesByMode.mode, {type: 'VARIABLE_ALIAS', id: 'root'});
  assert.equal(read.tokens[0].resolved, 18); assert.equal(read.graph_sha256, w.plan.graph_sha256);
  assert.equal(read.components[1].consumers[0].value, 18);
  assert(w.state.fonts.some(font => font.family === 'Roboto'));
});

for (const [name, change, pattern] of [
  ['wrong file', w => {w.figma.fileKey = 'other';}, /wrong file/],
  ['wrong page', w => {w.plan.page_id = 'other';}, /selected page/],
  ['wrong variable ID', w => {w.plan.tokens[0].variable_id = 'other';}, /outside collection/],
  ['wrong root ID', w => {w.plan.tokens[0].root_variable_id = 'family';}, /root identity/],
  ['wrong type', w => {w.plan.tokens[0].type = 'STRING'; w.plan.tokens[0].value = '18';}, /identity\/type/],
  ['stale before', w => {w.plan.tokens[1].before = 'Arial';}, /stale before/],
  ['wrong source', w => {w.state.wrongSource = true;}, /source mismatch/],
  ['direct node override', w => {w.state.override = 22;}, /native getter mismatch/],
  ['stale graph', w => {w.state.marker = JSON.stringify({page_id: 'page', collection_id: 'collection', graph_sha256: 'b'.repeat(64)});}, /stale graph/],
  ['unpaired apply', w => {delete w.plan.pairing;}, /explicit pairing/],
  ['CAS during font load', w => {w.state.onFont = () => {w.root.valuesByMode.mode = 20;};}, /before value changed/],
  ['alias CAS during font load', w => {w.state.onFont = () => {w.values.get('alias').valuesByMode.mode = {type: 'VARIABLE_ALIAS', id: 'family'};};}, /topology changed|consumer changed/],
]) test(`rejects ${name} before mutation`, async () => {
  const w = world(); change(w); await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), pattern); assert.equal(w.state.writes, 0);
});

test('post-write getter failure restores all roots and graph marker', async () => {
  const w = world(); const original = w.root.setValueForMode;
  w.root.setValueForMode = function(mode, value) {original.call(this, mode, value); w.state.override = value === 18 ? 99 : 0;};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /canonical native getter differs/);
  assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.family.valuesByMode.mode, 'Inter'); assert.equal(w.state.marker, '');
});

test('layout budget failure rolls back roots and existing baseline', async () => {
  const w = world(); w.main.children[0].width = 82;
  w.state.marker = JSON.stringify({page_id: 'page', collection_id: 'collection', graph_sha256: 'b'.repeat(64)});
  w.plan.previous_graph_sha256 = 'b'.repeat(64); const before = w.state.marker;
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /width\/height budget/);
  assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.family.valuesByMode.mode, 'Inter'); assert.equal(w.state.marker, before);
});

test('source linkage changed during font loading is rejected', async () => {
  const w = world(); w.state.onFont = () => {w.state.wrongSource = true;};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /source changed during preflight/);
  assert.equal(w.state.writes, 0);
});

test('unchanged first pairing creates only an owned baseline on explicit apply', async () => {
  const w = world(); for (const token of w.plan.tokens) token.value = token.before;
  await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(JSON.parse(w.state.marker).graph_sha256, w.plan.graph_sha256);
  assert.equal(w.values.size, 3);
});

test('scalar COLOR and BOOLEAN roots preserve native value shapes', async () => {
  const w = world(); const collection = await w.figma.variables.getVariableCollectionByIdAsync('collection');
  for (const [type, before, value] of [['COLOR', {r: 0, g: 0, b: 0, a: 1}, {r: 1, g: 0.2, b: 0.3, a: 1}], ['BOOLEAN', false, true]]) {
    const id = type.toLowerCase(); const variable = {id, name: `b/${id}`, resolvedType: type, variableCollectionId: 'collection', valuesByMode: {mode: before}, setValueForMode(mode, next) {this.valuesByMode[mode] = next;}};
    collection.variableIds.push(id); w.values.set(id, variable);
    w.plan.tokens.push({key: `b/${id}`, variable_name: `b/${id}`, variable_id: id, root_variable_id: id, type, before, value});
  }
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.deepEqual(read.tokens[2].resolved, {r: 1, g: 0.2, b: 0.3, a: 1}); assert.equal(read.tokens[3].resolved, true);
});

test('silent native setter failure is detected for a root without consumers', async () => {
  const w = world(); const collection = await w.figma.variables.getVariableCollectionByIdAsync('collection');
  const extra = {id: 'extra', name: 'b/extra', resolvedType: 'FLOAT', variableCollectionId: 'collection', valuesByMode: {mode: 1}, setValueForMode() {}};
  collection.variableIds.push(extra.id); w.values.set(extra.id, extra);
  w.plan.tokens.push({key: 'b/extra', type: 'FLOAT', value: 2, before: 1, variable_name: 'b/extra', variable_id: 'extra', root_variable_id: 'extra'});
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /canonical root getter differs/);
  assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.family.valuesByMode.mode, 'Inter'); assert.equal(w.state.marker, '');
});

for (const height of [25, 25.5, 26, 27]) test(`fractional native label budget 24.5px with actual ${height}px`, async () => {
  const w = world();
  for (const node of [w.main, w.instance]) {
    node.height = 44; node.paddingTop = 9.75; node.paddingBottom = 9.75;
    node.children[0].height = height;
  }
  if (height <= 25.5) {
    const read = await graphTokenSync(w.figma, w.plan, 'apply');
    assert.equal(read.components[0].consumers[0].height, height);
  } else {
    await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), new RegExp(`actual 40x${height}, budget 80x24\\.5, tolerance 1px`));
    assert.equal(w.root.valuesByMode.mode, 14);
    assert.equal(w.family.valuesByMode.mode, 'Inter');
    assert.equal(w.state.marker, '');
  }
});

function migrationWorld() {
  const w = world(); let sequence = 0;
  w.plan.system_id = 'example-system'; w.plan.namespace = 'ssot/example-system';
  w.plan.allowed_page_ids = ['page'];
  const bindings = new Map();
  const original = w.main.children[0], inherited = w.instance.children[0];
  bindings.set('fontSize', {type: 'VARIABLE_ALIAS', id: 'alias'});
  bindings.set('fontFamily', {type: 'VARIABLE_ALIAS', id: 'family'});
  const resolve = id => {const value = w.values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? resolve(value.id) : value;};
  for (const node of [original, inherited]) {
    Object.defineProperty(node, 'boundVariables', {get: () => ({fontSize: [bindings.get('fontSize')]})});
    Object.defineProperty(node, 'fontSize', {get: () => resolve(bindings.get('fontSize').id)});
    node.getRangeBoundVariable = (start, end, field) => bindings.get(field);
    node.getRangeAllFontNames = () => [{family: resolve(bindings.get('fontFamily').id), style: 'Regular'}];
    node.setBoundVariable = (field, variable) => {bindings.set(field, {type: 'VARIABLE_ALIAS', id: variable.id});};
    node.setRangeBoundVariable = (start, end, field, variable) => {bindings.set(field, {type: 'VARIABLE_ALIAS', id: variable.id});};
  }
  w.main.getInstancesAsync = async () => w.state.extraInstance ? [w.instance, {id: 'undeclared'}] : [w.instance];
  w.figma.variables.getLocalVariablesAsync = async () => [...w.values.values()];
  w.figma.variables.createVariable = (name, collection, resolvedType) => {
    const id = `new-${++sequence}`; const data = new Map();
    const item = {id, name, resolvedType, variableCollectionId: collection.id, valuesByMode: {}, setValueForMode(mode, value) {this.valuesByMode[mode] = value;}, setPluginData(key, value) {data.set(key, value);}, getPluginData(key) {return data.get(key) || '';}, remove() {w.values.delete(id); collection.variableIds.splice(collection.variableIds.indexOf(id), 1);}};
    w.values.set(id, item); collection.variableIds.push(id); return item;
  };
  w.plan.migrations = [];
  for (const node of [original, inherited]) for (const [field, token] of Object.entries(w.plan.components[0].properties)) {
    const old = w.plan.tokens.find(item => item.key === token);
    w.plan.migrations.push({node_id: node.id, field, token, before_variable_id: old.variable_id, before_value: old.before});
  }
  for (const token of w.plan.tokens) {
    const root = token.key === 'b/type/button' ? 'size/button' : 'font/family';
    token.create = true; token.variable_name = `${w.plan.namespace}/${token.key}`;
    token.root_variable_name = `${w.plan.namespace}/${root}`;
    token.alias_chain_names = [token.variable_name, token.root_variable_name];
    delete token.variable_id; delete token.root_variable_id; delete token.alias_chain;
  }
  w.bindings = bindings;
  return w;
}

test('explicit migration creates owned scoped aliases and preserves legacy roots', async () => {
  const w = migrationWorld(); const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.family.valuesByMode.mode, 'Inter');
  assert.equal(read.tokens[0].resolved, 18); assert.equal(read.components[1].consumers[0].value, 18);
  assert.equal(read.tokens[0].variable_name, 'ssot/example-system/b/type/button');
  assert.equal(JSON.parse(w.values.get(read.tokens[0].variable_id).getPluginData('graphSSOT')).system_id, w.plan.system_id);
  const marker = JSON.parse(w.state.marker); assert.equal(marker.owned_variable_ids.length, 4); assert.equal(marker.consumers.length, 4);
});

test('migration inspection never creates variables or rebinds nodes', async () => {
  const w = migrationWorld(); const read = await graphTokenSync(w.figma, w.plan, 'inspect');
  assert.equal(read.migration_pending, true); assert.equal(w.values.size, 3); assert.equal(w.bindings.get('fontSize').id, 'alias'); assert.equal(w.state.marker, '');
});

test('migration failure restores old bindings, removes new variables, and restores marker', async () => {
  const w = migrationWorld(); w.main.children[0].height = 90;
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /height budget/);
  assert.equal(w.values.size, 3); assert.equal(w.bindings.get('fontSize').id, 'alias'); assert.equal(w.bindings.get('fontFamily').id, 'family');
  assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.family.valuesByMode.mode, 'Inter'); assert.equal(w.state.marker, '');
});

for (const [name, change, error] of [
  ['non-pair create', w => {w.plan.pairing = false;}, /explicit all-new pairing/],
  ['stale binding', w => {w.plan.migrations[0].before_variable_id = 'family';}, /stale migration consumer/],
  ['missing migration', w => {w.plan.migrations.pop();}, /incomplete migration coverage/],
  ['undeclared instance', w => {w.state.extraInstance = true;}, /undeclared component instance/],
  ['wrong namespace', w => {w.plan.tokens[0].alias_chain_names[0] = 'ssot/other/token'; w.plan.tokens[0].variable_name = 'ssot/other/token';}, /declared system namespace/]
]) test(`migration rejects ${name} before variable creation`, async () => {
  const w = migrationWorld(); change(w); await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error); assert.equal(w.values.size, 3); assert.equal(w.bindings.get('fontSize').id, 'alias');
});

test('legacy shared root used by an unrelated RESET button blocks apply', async () => {
  const w = world();
  const reset = {id: 'reset', type: 'TEXT', characters: 'Reset', boundVariables: {fontSize: [{type: 'VARIABLE_ALIAS', id: 'alias'}]}, getPluginData() {return ''}, getRangeBoundVariable() {return null;}};
  const find = w.figma.currentPage.findAll;
  w.figma.currentPage.findAll = fn => [...find.call(w.figma.currentPage, fn), ...[reset].filter(fn)];
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /unplanned shared root consumer: reset.fontSize/);
  assert.equal(w.state.writes, 0); assert.equal(w.root.valuesByMode.mode, 14);
});

test('explicit exact instance IDs can migrate across admitted pages', async () => {
  const w = migrationWorld(); const page = w.figma.currentPage;
  const oldFind = page.findAll;
  page.findAll = fn => oldFind.call(page, node => node !== w.instance && node !== w.instance.children[0] && fn(node));
  const other = {id: 'recommendations', type: 'PAGE', getPluginData() {return '';}, async loadAsync() {}, findAll(fn) {return [w.instance, ...w.instance.children].filter(fn);}};
  w.figma.root = {children: [page, other]};
  w.plan.allowed_page_ids.push(other.id); w.plan.node_page_ids = {main: 'page', instance: 'recommendations'};
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(read.components[1].page_id, other.id); assert.equal(read.components[1].consumers[0].value, 18);
});

test('an instance outside admitted pages cannot be adopted by exact ID', async () => {
  const w = migrationWorld(); w.plan.node_page_ids = {main: 'page', instance: 'other'};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /native node page mismatch/);
  assert.equal(w.values.size, 3);
});

test('owned variable newly bound outside declared consumers blocks subsequent apply', async () => {
  const w = migrationWorld(); const first = await graphTokenSync(w.figma, w.plan, 'apply');
  const existingPlan = {...w.plan, pairing: false, previous_graph_sha256: w.plan.graph_sha256, graph_sha256: 'c'.repeat(64), migrations: undefined,
    tokens: w.plan.tokens.map((token, index) => ({...token, create: undefined, before: token.value, value: index === 0 ? 20 : token.value, variable_id: first.tokens[index].variable_id, root_variable_id: first.tokens[index].root_variable_id, alias_chain: first.tokens[index].alias_chain}))};
  const extra = {id: 'foreign-label', type: 'TEXT', characters: 'Unrelated', boundVariables: {fontSize: [{type: 'VARIABLE_ALIAS', id: first.tokens[0].variable_id}]}};
  const other = {id: 'foreign-page', type: 'PAGE', async loadAsync() {}, findAll(fn) {return [extra].filter(fn);}};
  w.figma.root = {children: [w.figma.currentPage, other]};
  await assert.rejects(() => graphTokenSync(w.figma, existingPlan, 'apply'), /unplanned shared root consumer: foreign-label.fontSize/);
  assert.equal(w.values.get(first.tokens[0].root_variable_id).valuesByMode.mode, 18);
  assert.equal(JSON.parse(w.state.marker).graph_sha256, first.graph_sha256);
});

test('cross-collection aliases to an edited root also count as shared fanout', async () => {
  const w = world();
  w.values.set('foreign-alias', {id: 'foreign-alias', variableCollectionId: 'foreign-collection', valuesByMode: {'foreign-mode': {type: 'VARIABLE_ALIAS', id: 'root'}}});
  const extra = {id: 'cross-label', type: 'TEXT', characters: 'Cross collection', boundVariables: {fontSize: [{type: 'VARIABLE_ALIAS', id: 'foreign-alias'}]}};
  const other = {id: 'other-page', type: 'PAGE', async loadAsync() {}, findAll(fn) {return [extra].filter(fn);}};
  w.figma.root = {children: [w.figma.currentPage, other]};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /unplanned shared root consumer: cross-label.fontSize/);
  assert.equal(w.state.writes, 0);
});

test('rollback preserves externally edited roots and untouched roots after export yields', async () => {
  const w = world(); w.plan.tokens[1].value = 'Inter';
  w.main.exportAsync = async () => {w.root.valuesByMode.mode = 22; w.family.valuesByMode.mode = 'External font';};
  let failure;
  try {await graphTokenSync(w.figma, w.plan, 'apply');} catch (error) {failure = error;}
  assert(failure); assert.equal(w.root.valuesByMode.mode, 22); assert.equal(w.family.valuesByMode.mode, 'External font');
  assert.equal(w.state.writes, 1);
  assert.equal(failure.readback.status, 'rollback-conflict');
  assert(failure.rollback_conflicts.some(item => item.kind === 'root-changed' && item.variable_id === 'root' && item.actual === 22));
});

test('rollback preserves an externally replaced graph marker', async () => {
  const w = world();
  w.main.exportAsync = async () => {w.state.marker = 'external-marker';};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error => error.readback.status === 'rollback-conflict' && error.rollback_conflicts.some(item => item.kind === 'marker-changed'));
  assert.equal(w.state.marker, 'external-marker'); assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.family.valuesByMode.mode, 'Inter');
});

test('migration updates explicit instance bindings after main bindings', async () => {
  const w = migrationWorld(); const instanceLabel = w.instance.children[0];
  const own = new Map([['fontSize', {type: 'VARIABLE_ALIAS', id: 'alias'}], ['fontFamily', {type: 'VARIABLE_ALIAS', id: 'family'}]]);
  const scalar = id => {const value = w.values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? scalar(value.id) : value;};
  // Use a distinct instance label so it retains explicit legacy bindings when the main changes.
  const replacement = {...instanceLabel, id: instanceLabel.id, get boundVariables() {return {fontSize: [own.get('fontSize')]};}, get fontSize() {return scalar(own.get('fontSize').id);}, getRangeBoundVariable(start, end, field) {return own.get(field);}, getRangeAllFontNames() {return [{family: scalar(own.get('fontFamily').id), style: 'Regular'}];}, setBoundVariable(field, variable) {own.set(field, {type: 'VARIABLE_ALIAS', id: variable.id});}, setRangeBoundVariable(start, end, field, variable) {own.set(field, {type: 'VARIABLE_ALIAS', id: variable.id});}};
  w.instance.children = [replacement];
  const oldFind = w.figma.currentPage.findAll;
  w.figma.currentPage.findAll = fn => oldFind.call(w.figma.currentPage, () => true).map(node => node.id === replacement.id ? replacement : node).filter(fn);
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(own.get('fontSize').id, read.tokens[0].variable_id); assert.equal(own.get('fontFamily').id, read.tokens[1].variable_id);
  assert.equal(read.components[1].consumers[0].value, 18); assert.equal(w.root.valuesByMode.mode, 14);
});

test('migration rollback preserves external binding changes and reports the conflict', async () => {
  const w = migrationWorld();
  w.main.exportAsync = async () => {w.bindings.set('fontSize', {type: 'VARIABLE_ALIAS', id: 'family'}); throw Error('external binding edit');};
  let failure;
  try {await graphTokenSync(w.figma, w.plan, 'apply');} catch (error) {failure = error;}
  assert(failure); assert.equal(w.bindings.get('fontSize').id, 'family');
  assert(failure.rollback_conflicts.some(item => item.kind === 'binding-changed'));
});

test('migration rollback retains a new variable externally edited during export', async () => {
  const w = migrationWorld(); let edited;
  w.main.exportAsync = async () => {edited = [...w.values.values()].find(item => item.name === `${w.plan.namespace}/size/button`); edited.valuesByMode.mode = 29; throw Error('external variable edit');};
  let failure;
  try {await graphTokenSync(w.figma, w.plan, 'apply');} catch (error) {failure = error;}
  assert(failure); assert.equal(w.values.get(edited.id).valuesByMode.mode, 29); assert.equal(w.bindings.get('fontSize').id, 'alias');
  assert(failure.rollback_conflicts.some(item => item.kind === 'created-variable-changed' && item.variable_id === edited.id));
});

test('migration rollback retains created variables referenced by an unrelated new alias', async () => {
  const w = migrationWorld(); let referenced;
  w.main.exportAsync = async () => {
    referenced = [...w.values.values()].find(item => item.name === `${w.plan.namespace}/size/button`);
    w.values.set('outside', {id: 'outside', valuesByMode: {other: {type: 'VARIABLE_ALIAS', id: referenced.id}}});
    throw Error('external alias reference');
  };
  let failure;
  try {await graphTokenSync(w.figma, w.plan, 'apply');} catch (error) {failure = error;}
  assert(failure); assert(w.values.has(referenced.id));
  assert(failure.rollback_conflicts.some(item => item.kind === 'created-variable-referenced' && item.variable_id === 'outside'));
});

for (const phase of ['onFont', 'export']) test(`late RESET fanout added during ${phase} is rejected`, async () => {
  const w = world(); let reset = null;
  const oldFind = w.figma.currentPage.findAll;
  w.figma.currentPage.findAll = fn => [...oldFind.call(w.figma.currentPage, fn), ...[reset].filter(node => node && fn(node))];
  const add = () => {reset = {id: 'late-reset', type: 'TEXT', characters: 'Reset', boundVariables: {fontSize: [{type: 'VARIABLE_ALIAS', id: 'alias'}]}};};
  if (phase === 'onFont') w.state.onFont = add; else w.main.exportAsync = async () => {add();};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /unplanned shared root consumer: late-reset.fontSize/);
  assert.equal(w.root.valuesByMode.mode, 14); assert.equal(w.state.marker, '');
  if (phase === 'onFont') assert.equal(w.state.writes, 0);
});

test('rollback diagnostics include the original error and stack', async () => {
  const w = world(); w.main.children[0].height = 90;
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error => error.readback.error.includes('height budget') && error.readback.stack.includes('Graph token sync'));
});

function directPaddingWorld() {
  const w = world();
  const variable = {id: 'spacing', name: 'b/space/x', resolvedType: 'FLOAT', variableCollectionId: 'collection', valuesByMode: {mode: 10}, setValueForMode(mode, value) {this.valuesByMode[mode] = value;}};
  w.values.set(variable.id, variable);
  const collectionPromise = w.figma.variables.getVariableCollectionByIdAsync('collection');
  w.plan.tokens.push({key: 'b/space/x', type: 'FLOAT', value: 10, before: 10, variable_id: 'spacing', variable_name: 'b/space/x', root_variable_id: 'spacing'});
  w.plan.components[0].properties.paddingLeft = 'b/space/x';
  for (const node of [w.main, w.instance]) {
    node._spacing = node === w.main ? null : {type: 'VARIABLE_ALIAS', id: 'spacing'}; node._padding = node === w.main ? 21 : 10;
    Object.defineProperty(node, 'paddingLeft', {get() {return this._spacing ? variable.valuesByMode.mode : this._padding;}, set(value) {this._padding = value; this._spacing = null;}});
    Object.defineProperty(node, 'boundVariables', {get() {return this._spacing ? {paddingLeft: this._spacing} : {};}});
    node.setBoundVariable = (field, value) => {assert.equal(field, 'paddingLeft'); node._spacing = value ? {type: 'VARIABLE_ALIAS', id: value.id} : null;};
  }
  w.ready = async () => {(await collectionPromise).variableIds.push(variable.id);};
  return w;
}

test('inspect captures direct main padding without overwriting it', async () => {
  const w = directPaddingWorld(); await w.ready();
  const read = await graphTokenSync(w.figma, w.plan, 'inspect');
  const row = read.components[0].consumers.find(item => item.field === 'paddingLeft');
  assert.equal(row.value, 21); assert.equal(row.binding, null); assert.equal(row.root_value, 10); assert.equal(row.expected_value, 10);
  assert.equal(row.classification, 'detached-override'); assert.equal(row.token, 'b/space/x'); assert.equal(w.main.paddingLeft, 21);
});

test('accepted direct main padding can repair its pinned binding and update the graph root', async () => {
  const w = directPaddingWorld(); await w.ready(); w.plan.tokens[2].value = 21;
  w.plan.repair_bindings = [{node_id: 'main', field: 'paddingLeft', token: 'b/space/x', before_variable_id: null, before_value: 21}];
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(w.main.paddingLeft, 21); assert.equal(w.main.boundVariables.paddingLeft.id, 'spacing');
  assert.equal(read.components[0].consumers.find(item => item.field === 'paddingLeft').classification, 'canonical');
});

test('a detached edit cannot be applied without accepted repair and stale repair cannot overwrite it', async () => {
  const w = directPaddingWorld(); await w.ready();
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /binding mismatch/);
  w.plan.repair_bindings = [{node_id: 'main', field: 'paddingLeft', token: 'b/space/x', before_variable_id: null, before_value: 20}];
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /stale repair binding/);
  assert.equal(w.main.paddingLeft, 21); assert.equal(w.main._spacing, null);
});

function addVisualMigration(w) {
  const blue = {r: 21 / 255, g: 101 / 255, b: 192 / 255, a: 1};
  w.figma.variables.setBoundVariableForPaint = (paint, field, variable) => ({...paint, boundVariables: variable ? {color: {type: 'VARIABLE_ALIAS', id: variable.id}} : {}});
  const scalar = id => {const value = w.values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? scalar(value.id) : value;};
  for (const node of [w.main, w.instance]) {
    let paint = {type: 'SOLID', color: {r: blue.r, g: blue.g, b: blue.b}, opacity: 1};
    node._corners = new Map(); node._radius = 8;
    Object.defineProperty(node, 'fills', {get() {const rgba = paint.boundVariables?.color ? scalar(paint.boundVariables.color.id) : {...paint.color, a: paint.opacity}; return [{...paint, color: {r: Math.fround(rgba.r), g: Math.fround(rgba.g), b: Math.fround(rgba.b)}, opacity: rgba.a}];}, set(value) {paint = value[0];}});
    Object.defineProperty(node, 'cornerRadius', {get() {const alias = node._corners.get('topLeftRadius'); return alias ? scalar(alias.id) : node._radius;}, set(value) {node._radius = value;}});
    for (const field of ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius']) Object.defineProperty(node, field, {get() {return node.cornerRadius;}});
    Object.defineProperty(node, 'boundVariables', {get() {return Object.fromEntries(node._corners);}});
    node.setBoundVariable = (field, variable) => {if (variable) node._corners.set(field, {type: 'VARIABLE_ALIAS', id: variable.id}); else node._corners.delete(field);};
  }
  for (const [key, type, value, field] of [['color/button', 'COLOR', blue, 'backgroundColor'], ['radius/button', 'FLOAT', 8, 'borderRadius']]) {
    w.plan.tokens.push({key, type, value, create: true, variable_name: `${w.plan.namespace}/${key}`, root_variable_name: `${w.plan.namespace}/${key}`, alias_chain_names: [`${w.plan.namespace}/${key}`]});
    w.plan.components[0].properties[field] = key;
    for (const node of [w.main, w.instance]) w.plan.migrations.push({node_id: node.id, field, token: key, before_variable_id: null, before_value: value});
  }
}

test('initial adoption binds unbound single-SOLID background and four-corner radius', async () => {
  const w = migrationWorld(); addVisualMigration(w);
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(read.tokens[2].type, 'COLOR'); assert.equal(w.main.fills[0].boundVariables.color.id, read.tokens[2].variable_id);
  assert.equal(w.main.boundVariables.topLeftRadius.id, read.tokens[3].variable_id);
  assert.equal(w.instance.boundVariables.bottomRightRadius.id, read.tokens[3].variable_id);
  assert.equal(w.root.valuesByMode.mode, 14);
});

test('owned background blue to green and radius8 to12 update without legacy root changes', async () => {
  const w = migrationWorld(); addVisualMigration(w); const first = await graphTokenSync(w.figma, w.plan, 'apply');
  const green = {r: 22 / 255, g: 115 / 255, b: 68 / 255, a: 1};
  const next = {...w.plan, graph_sha256: 'd'.repeat(64), previous_graph_sha256: w.plan.graph_sha256, pairing: false, migrations: undefined,
    tokens: w.plan.tokens.map((token, index) => ({...token, create: undefined, before: token.value, value: index === 2 ? green : index === 3 ? 12 : token.value, variable_id: first.tokens[index].variable_id, root_variable_id: first.tokens[index].root_variable_id, alias_chain: first.tokens[index].alias_chain}))};
  const read = await graphTokenSync(w.figma, next, 'apply');
  const color = read.components[0].consumers.find(row => row.field === 'backgroundColor');
  assert(Math.abs(color.value.g - green.g) < 0.000001); assert.equal(color.classification, 'canonical');
  assert.equal(w.main.cornerRadius, 12); assert.equal(w.instance.cornerRadius, 12); assert.equal(w.root.valuesByMode.mode, 14);
});

test('topology extension adopts new visual tokens while preserving existing owned tokens', async () => {
  const w = migrationWorld(); const first = await graphTokenSync(w.figma, w.plan, 'apply');
  w.plan.previous_graph_sha256 = w.plan.graph_sha256; w.plan.graph_sha256 = 'e'.repeat(64);
  w.plan.tokens = w.plan.tokens.map((token, index) => ({...token, create: undefined, before: token.value, variable_id: first.tokens[index].variable_id, root_variable_id: first.tokens[index].root_variable_id, alias_chain: first.tokens[index].alias_chain}));
  w.plan.migrations = []; addVisualMigration(w);
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(read.tokens[0].variable_id, first.tokens[0].variable_id); assert.equal(read.tokens[1].variable_id, first.tokens[1].variable_id);
  assert.equal(read.tokens[0].resolved, 18); assert.equal(read.tokens[2].type, 'COLOR'); assert.equal(w.values.size, 9);
});

test('mixed or style-backed paint migration fails before creating variables', async () => {
  const w = migrationWorld(); addVisualMigration(w); w.main.fillStyleId = 'preserved-style';
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /preserve paint style/); assert.equal(w.values.size, 3);
});

test('width binding preserves HUG by rejecting implicit sizing conversion', async () => {
  const w = directPaddingWorld(); await w.ready();
  w.plan.components[0].properties.width = 'b/space/x';
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /binding mismatch/);
  // Isolate the adapter's explicit policy with a pinned width edit repair.
  w.plan.components[0].properties.width = 'b/space/x'; w.main.layoutSizingHorizontal = 'HUG'; w.instance.layoutSizingHorizontal = 'HUG';
  w.plan.repair_bindings = [{node_id: 'main', field: 'paddingLeft', token: 'b/space/x', before_variable_id: null, before_value: 21}, ...['main', 'instance'].map(node_id => ({node_id, field: 'width', token: 'b/space/x', before_variable_id: null, before_value: 100}))];
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /requires FIXED sizing; actual HUG/); assert.equal(w.state.writes, 0);
});

function instanceDirectEditWorld() {
  const w = world(); const original = w.instance.children[0]; let literal = 22, alias = null;
  const scalar = id => {const value = w.values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? scalar(value.id) : value;};
  const replacement = {...original, get fontSize() {return alias ? scalar(alias.id) : literal;}, set fontSize(value) {literal = value;}, get boundVariables() {return alias ? {fontSize: [alias]} : {};}, getRangeBoundVariable(start, end, field) {return field === 'fontSize' ? alias : original.getRangeBoundVariable(start, end, field);}, setBoundVariable(field, variable) {assert.equal(field, 'fontSize'); alias = variable ? {type: 'VARIABLE_ALIAS', id: variable.id} : null;}, setRangeBoundVariable(start, end, field, variable) {assert.equal(field, 'fontSize'); alias = variable ? {type: 'VARIABLE_ALIAS', id: variable.id} : null;}};
  w.instance.children = [replacement];
  const oldFind = w.figma.currentPage.findAll;
  w.figma.currentPage.findAll = fn => oldFind.call(w.figma.currentPage, () => true).map(node => node.id === replacement.id ? replacement : node).filter(fn);
  w.label = replacement; return w;
}

test('inspect captures a detached direct instance font size and its source relationship', async () => {
  const w = instanceDirectEditWorld(); const read = await graphTokenSync(w.figma, w.plan, 'inspect');
  const row = read.components[1].consumers.find(item => item.field === 'fontSize');
  assert.equal(row.value, 22); assert.equal(row.root_value, 14); assert.equal(row.binding, null); assert.equal(row.source_main_component_id, 'main'); assert.equal(row.classification, 'detached-override');
});

test('accepted direct instance font size repair restores its canonical graph binding', async () => {
  const w = instanceDirectEditWorld(); w.plan.tokens[0].value = 22;
  w.plan.repair_bindings = [{node_id: 'copy', field: 'fontSize', token: 'b/type/button', before_variable_id: null, before_value: 22}];
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(w.label.boundVariables.fontSize[0].id, 'alias'); assert.equal(w.label.fontSize, 22);
  assert.equal(read.components[1].consumers[0].classification, 'canonical');
});

test('direct instance edit after repair preflight is not overwritten', async () => {
  const w = instanceDirectEditWorld(); w.plan.tokens[0].value = 22;
  w.plan.repair_bindings = [{node_id: 'copy', field: 'fontSize', token: 'b/type/button', before_variable_id: null, before_value: 22}];
  w.state.onFont = () => {w.label.fontSize = 23;};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /consumer changed during preflight/);
  assert.equal(w.label.fontSize, 23); assert.equal(w.label.boundVariables.fontSize, undefined); assert.equal(w.state.writes, 0);
});

test('failed repair restores a detached instance literal and original root values', async () => {
  const w = instanceDirectEditWorld(); w.plan.tokens[0].value = 22; w.main.children[0].height = 100;
  w.plan.repair_bindings = [{node_id: 'copy', field: 'fontSize', token: 'b/type/button', before_variable_id: null, before_value: 22}];
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /height budget/);
  assert.equal(w.label.fontSize, 22); assert.equal(w.label.boundVariables.fontSize, undefined); assert.equal(w.root.valuesByMode.mode, 14);
});

test('topology extension can add a new declared alias to an existing owned root', async () => {
  const w = migrationWorld(); const first = await graphTokenSync(w.figma, w.plan, 'apply');
  w.plan.previous_graph_sha256 = w.plan.graph_sha256; w.plan.graph_sha256 = 'f'.repeat(64);
  w.plan.tokens = w.plan.tokens.map((token, index) => ({...token, create: undefined, before: token.value, variable_id: first.tokens[index].variable_id, root_variable_id: first.tokens[index].root_variable_id, alias_chain: first.tokens[index].alias_chain}));
  w.plan.tokens.push({key: 'space/control', type: 'FLOAT', value: 18, create: true, variable_name: `${w.plan.namespace}/space/control`, root_variable_name: `${w.plan.namespace}/size/button`, alias_chain_names: [`${w.plan.namespace}/space/control`, `${w.plan.namespace}/size/button`]});
  w.plan.components[0].properties.gap = 'space/control';
  w.plan.migrations = [];
  for (const node of [w.main, w.instance]) {
    let alias = null, literal = 18;
    Object.defineProperty(node, 'itemSpacing', {get() {return alias ? w.values.get(first.tokens[0].root_variable_id).valuesByMode.mode : literal;}, set(value) {literal = value;}});
    Object.defineProperty(node, 'boundVariables', {get() {return alias ? {itemSpacing: alias} : {};}});
    node.setBoundVariable = (field, variable) => {assert.equal(field, 'itemSpacing'); alias = variable ? {type: 'VARIABLE_ALIAS', id: variable.id} : null;};
    w.plan.migrations.push({node_id: node.id, field: 'gap', token: 'space/control', before_variable_id: null, before_value: 18});
  }
  const read = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(read.tokens[2].root_variable_id, first.tokens[0].root_variable_id); assert.equal(w.values.size, 8); assert.equal(w.main.itemSpacing, 18);
});

test('a new page added after font loading invalidates the scanned consumer closure', async () => {
  const w = world(); w.figma.root = {children: [w.figma.currentPage]};
  w.state.onFont = () => {if (w.figma.root.children.length === 1) w.figma.root.children.push({id: 'late-page', type: 'PAGE'});};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), /page closure changed during transaction/);
  assert.equal(w.state.writes, 0); assert.equal(w.state.marker, '');
});

async function readonlyDimensionWorld(axis, silentResize = false) {
  const w = world(), before = axis === 'width' ? 100 : 40, after = axis === 'width' ? 160 : 80;
  const dimension = {id: 'dimension', name: `b/${axis}`, resolvedType: 'FLOAT', variableCollectionId: 'collection', valuesByMode: {mode: before}, setValueForMode(mode, value) {this.valuesByMode[mode] = value;}};
  w.values.set(dimension.id, dimension); (await w.figma.variables.getVariableCollectionByIdAsync('collection')).variableIds.push(dimension.id);
  w.plan.tokens.push({key: `b/${axis}`, type: 'FLOAT', value: after, before, variable_id: dimension.id, root_variable_id: dimension.id, variable_name: dimension.name});
  w.plan.components[0].properties[axis] = `b/${axis}`;
  w.plan.repair_bindings = [];
  for (const node of [w.main, w.instance]) {
    let width = 100, height = 40, bound = null;
    node.layoutSizingHorizontal = 'FIXED'; node.layoutSizingVertical = 'FIXED';
    Object.defineProperty(node, 'width', {get() {return axis === 'width' && bound ? dimension.valuesByMode.mode : width;}});
    Object.defineProperty(node, 'height', {get() {return axis === 'height' && bound ? dimension.valuesByMode.mode : height;}});
    Object.defineProperty(node, 'boundVariables', {get() {return bound ? {[axis]: bound} : {};}});
    node.setBoundVariable = (field, variable) => {
      assert.equal(field, axis);
      if (!variable && bound) {width = node.width; height = node.height;}
      bound = variable ? {type: 'VARIABLE_ALIAS', id: variable.id} : null;
    };
    node.resize = (nextWidth, nextHeight) => {if (!silentResize) {width = nextWidth; height = nextHeight;}};
    w.plan.repair_bindings.push({node_id: node.id, field: axis, token: `b/${axis}`, before_variable_id: null, before_value: before});
  }
  w.main.exportAsync = async () => {throw Error('force dimension rollback');};
  return w;
}

for (const axis of ['width', 'height']) test(`readonly native ${axis} rollback restores its literal through resize`, async () => {
  const w = await readonlyDimensionWorld(axis); let failure;
  try {await graphTokenSync(w.figma, w.plan, 'apply');} catch (error) {failure = error;}
  assert(failure); assert.equal(w.main[axis], axis === 'width' ? 100 : 40); assert.equal(w.instance[axis], axis === 'width' ? 100 : 40);
  assert.equal(w.main.boundVariables[axis], undefined);
  assert(!failure.rollback_conflicts.some(item => item.kind === 'binding-restore-failed'));
});

test('a silently ignored resize is reported as rollback conflict rather than successful restoration', async () => {
  const w = await readonlyDimensionWorld('width', true); let failure;
  try {await graphTokenSync(w.figma, w.plan, 'apply');} catch (error) {failure = error;}
  assert(failure); assert.equal(w.main.width, 160);
  assert.equal(failure.readback.status, 'rollback-conflict');
  assert(failure.rollback_conflicts.some(item => item.kind === 'binding-restore-failed' && item.error.includes('literal restoration differs')));
});

function styledMigrationWorld() {
  const w = migrationWorld(), styles = new Map();
  let styleId = 'source-style', sequence = 0;
  const resolve = id => {const value = w.values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? resolve(value.id) : value;};
  const makeStyle = (id, bindings) => {
    const data = new Map(); let fontName = {family: 'Inter', style: 'Regular'}, fontSize = 14;
    const style = {id, type: 'TEXT', name: 'Original typography', boundVariables: structuredClone(bindings), lineHeight: {unit: 'PIXELS', value: 24}, letterSpacing: {unit: 'PIXELS', value: 0}, paragraphSpacing: 0, textCase: 'ORIGINAL',
      get fontSize() {return this.boundVariables.fontSize ? resolve(this.boundVariables.fontSize.id) : fontSize;}, set fontSize(value) {fontSize = value;},
      get fontName() {return {...fontName, family: this.boundVariables.fontFamily ? resolve(this.boundVariables.fontFamily.id) : fontName.family};}, set fontName(value) {fontName = structuredClone(value);},
      setBoundVariable(field, variable) {if (variable) this.boundVariables[field] = {type: 'VARIABLE_ALIAS', id: variable.id}; else delete this.boundVariables[field];},
      getPluginData(key) {return data.get(key) || '';}, setPluginData(key, value) {data.set(key, value);},
      async getStyleConsumersAsync() {return styleId === id ? [{node: w.main.children[0]}, {node: w.instance.children[0]}] : [];},
      remove() {styles.delete(id);}};
    styles.set(id, style); return style;
  };
  const original = makeStyle(styleId, {fontSize: {type: 'VARIABLE_ALIAS', id: 'alias'}, fontFamily: {type: 'VARIABLE_ALIAS', id: 'family'}});
  for (const node of [w.main.children[0], w.instance.children[0]]) {
    Object.defineProperty(node, 'textStyleId', {get: () => node === w.instance.children[0] && Object.prototype.hasOwnProperty.call(w.state, 'instanceStyleOverride') ? w.state.instanceStyleOverride : styleId});
    Object.defineProperty(node, 'fontName', {get: () => styles.get(styleId).fontName});
    for (const field of ['lineHeight', 'letterSpacing', 'paragraphSpacing', 'textCase']) Object.defineProperty(node, field, {get: () => styles.get(styleId)[field]});
    node.getRangeTextStyleId = () => styleId;
    node.setTextStyleIdAsync = async id => {
      if (w.state.ignoreStyleRestore && id === 'source-style') return;
      styleId = id;
      for (const field of ['fontSize', 'fontFamily']) w.bindings.set(field, structuredClone(styles.get(id).boundVariables[field]));
    };
    node.setRangeBoundVariable = () => {throw Error('direct typography binding would detach the shared style');};
    node.setBoundVariable = () => {throw Error('node typography binding would detach the shared style');};
  }
  w.figma.getStyleByIdAsync = async id => styles.get(id);
  w.figma.createTextStyle = () => makeStyle('derived-' + ++sequence, {});
  w.styles = styles; w.originalStyle = original;
  w.makeExternalStyle = () => {const style = makeStyle('external-style', structuredClone(styles.get(styleId).boundVariables)); styleId = style.id;};
  // Match the fresh native graph: new typography variables are concrete leaves, not aliases.
  for (const token of w.plan.tokens) {token.root_variable_name = token.variable_name; token.alias_chain_names = [token.variable_name];}
  return w;
}

test('styled concrete-leaf adoption derives scoped typography and preserves the original shared style', async () => {
  const w = styledMigrationWorld();
  const before = JSON.stringify({name: w.originalStyle.name, bindings: w.originalStyle.boundVariables, lineHeight: w.originalStyle.lineHeight, letterSpacing: w.originalStyle.letterSpacing});
  const result = await graphTokenSync(w.figma, w.plan, 'apply');
  assert.equal(result.tokens[0].variable_id, result.tokens[0].root_variable_id);
  assert.match(w.main.children[0].textStyleId, /^derived-/);
  assert.equal(w.instance.children[0].textStyleId, w.main.children[0].textStyleId);
  assert.equal(w.main.children[0].fontSize, 18);
  assert.deepEqual(w.main.children[0].lineHeight, {unit: 'PIXELS', value: 24});
  assert.equal(w.styles.size, 2);
  assert.equal(JSON.stringify({name: w.originalStyle.name, bindings: w.originalStyle.boundVariables, lineHeight: w.originalStyle.lineHeight, letterSpacing: w.originalStyle.letterSpacing}), before);
});

test('failed styled adoption restores original and inherited style links, bindings and non-target typography', async () => {
  const w = styledMigrationWorld(); w.main.children[0].height = 90;
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error => error.readback.status === 'rolled-back' && error.rollback_conflicts.length === 0);
  for (const node of [w.main.children[0], w.instance.children[0]]) {
    assert.equal(node.textStyleId, 'source-style'); assert.equal(node.fontSize, 14);
    assert.equal(node.getRangeBoundVariable(0, node.characters.length, 'fontFamily').id, 'family');
    assert.deepEqual(node.lineHeight, {unit: 'PIXELS', value: 24});
  }
  assert.equal(w.styles.size, 1); assert.equal(w.values.size, 3); assert.equal(w.state.marker, '');
});

test('silent text-style restoration failure is a rollback conflict and retains referenced state', async () => {
  const w = styledMigrationWorld(); w.main.children[0].height = 90; w.state.ignoreStyleRestore = true;
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error => error.readback.status === 'rollback-conflict' && error.rollback_conflicts.some(conflict => conflict.kind === 'text-style-restore-differs'));
  assert.match(w.main.children[0].textStyleId, /^derived-/); assert.equal(w.styles.size, 2);
});

test('external text-style replacement during layout is preserved and reported', async () => {
  const w = styledMigrationWorld();
  w.main.exportAsync = async () => {w.makeExternalStyle(); throw Error('layout interrupted');};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error => error.readback.status === 'rollback-conflict' && error.rollback_conflicts.some(conflict => conflict.kind === 'text-style-changed'));
  assert.equal(w.main.children[0].textStyleId, 'external-style');
  assert.ok(w.styles.has('source-style'));
});


test('rollback verifies an inherited instance whose binding was skipped even when aliases and values recover', async () => {
  const w = styledMigrationWorld();
  w.main.exportAsync = async () => {w.state.instanceStyleOverride = ''; throw Error('layout interrupted after instance detach');};
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error => error.readback.status === 'rollback-conflict' && error.rollback_conflicts.some(conflict => conflict.kind === 'text-style-restore-differs' && conflict.node_id === 'copy'));
  assert.equal(w.main.children[0].textStyleId, 'source-style');
  assert.equal(w.instance.children[0].textStyleId, '');
  assert.equal(w.instance.children[0].fontSize, 14);
  assert.equal(w.instance.children[0].getRangeBoundVariable(0, w.instance.children[0].characters.length, 'fontSize').id, 'alias');
});

test('failed style initialization removes the unassigned partial copy', async () => {
  const w = styledMigrationWorld();
  const create = w.figma.createTextStyle.bind(w.figma);
  w.figma.createTextStyle = () => {
    const style = create();
    style.setBoundVariable = () => {throw Error('style setter failed');};
    return style;
  };
  await assert.rejects(() => graphTokenSync(w.figma, w.plan, 'apply'), error =>
    error.readback.status === 'rolled-back' && error.rollback_conflicts.length === 0);
  assert.equal(w.styles.size, 1);
  assert.equal(w.main.children[0].textStyleId, 'source-style');
});
