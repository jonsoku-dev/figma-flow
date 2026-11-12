// Production bundle oracle. The sandbox deliberately has no require or Node globals.
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const dir = process.env.RD04_BUNDLE;
assert(dir, 'Run through python3 tests/finalize_selective_sync.py');
const html = fs.readFileSync(path.join(dir, 'bundle/ui.html'), 'utf8');
const code = fs.readFileSync(path.join(dir, 'bundle/code.js'), 'utf8');
const config = JSON.parse(html.match(/<script id="graph-panel-config"[^>]*>([\s\S]*?)<\/script>/)[1]);
const native = JSON.parse(fs.readFileSync(path.join(dir, 'native.json')));
const initialMarker = fs.readFileSync(path.join(dir, 'marker.json'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));

function panel() {
  const elements = new Map(), posted = [];
  class Element {
    constructor(tag) {this.tagName = tag; this.children = []; this.style = {}; this.dataset = {}; this.textContent = '';}
    appendChild(child) {this.children.push(child); return child;}
    replaceChildren() {this.children = [];}
    setAttribute(key, value) {this[key] = value;}
    removeAttribute(key) {delete this[key];}
    addEventListener(name, fn) {this[name] = fn;}
    focus() {}
    click() {if (!this.disabled) this.onclick?.();}
  }
  for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
    const element = new Element(match[0].match(/^<([^\s>]+)/)[1]);
    element.hidden = /\bhidden\b/.test(match[0]);
    element.disabled = /\bdisabled\b/.test(match[0]);
    elements.set(match[1], element);
  }
  elements.get('graph-panel-config').textContent = JSON.stringify(config);
  const context = {document: {documentElement: {dataset: {}}, getElementById: id => elements.get(id), createElement: tag => new Element(tag)},
    FlowUI: {t: key => key, apply() {}}, FlowPanel: {status() {}},
    parent: {postMessage(message) {posted.push(clone(message.pluginMessage));}}, addEventListener() {}};
  context.window = context;
  const script = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].find(match => match[1].includes('const config = JSON.parse'))[1];
  vm.runInNewContext(script, context);
  const boxes = () => elements.get('impact').children.filter(child => child.className === 'change-card')
    .map(card => card.children.find(child => child.tagName === 'label').children.find(child => child.tagName === 'input'));
  return {elements, posted, boxes, apply() {elements.get('review').click(); elements.get('apply').click(); return posted.at(-1);}};
}

function world() {
  let marker = initialMarker;
  const messages = [], writes = [];
  const values = new Map(native.variables.map(raw => {
    const item = clone(raw);
    item.setValueForMode = function(mode, next) {writes.push(item.id); this.valuesByMode[mode] = clone(next);};
    return [item.id, item];
  }));
  const scalar = id => {const value = values.get(id).valuesByMode.mode; return value?.type === 'VARIABLE_ALIAS' ? scalar(value.id) : value;};
  const nodes = native.nodes.map(raw => {
    const node = {...clone(raw), width: 160, height: 60, paddingTop: 4, paddingBottom: 4,
      getPluginData() {return '';}, async exportAsync() {return new Uint8Array();}};
    for (const [field, binding] of Object.entries(node.boundVariables || {})) {
      const id = (Array.isArray(binding) ? binding[0] : binding).id;
      Object.defineProperty(node, field, {configurable: true, get: () => scalar(id)});
    }
    if (node.type === 'TEXT') {
      node.characters = 'Label'; node.width = 30; node.height = 20;
      node.getRangeBoundVariable = (start, end, field) => node.boundVariables[field]?.[0] || null;
      node.getRangeAllFontNames = () => [{family: 'Inter', style: 'Regular'}];
    }
    return node;
  });
  for (const node of nodes) {
    node.children = nodes.filter(child => child.parentId === node.id);
    node.findAll = predicate => node.children.filter(predicate);
    node.getMainComponentAsync = async () => nodes.find(item => item.id === 'main');
  }
  const page = {id: 'page', async loadAsync() {}, findAll: predicate => nodes.filter(predicate),
    getPluginData: () => marker, setPluginData(key, value) {marker = value;}};
  const collection = {...clone(native.collections[0]), variableIds: [...values.keys()],
    getPluginData: () => JSON.stringify({pageId: 'page', collectionId: 'collection'})};
  const figma = {fileKey: 'file', currentPage: page, showUI() {}, async loadFontAsync() {},
    ui: {postMessage(message) {messages.push(clone(message));}},
    variables: {async getVariableByIdAsync(id) {return values.get(id);},
      async getVariableCollectionByIdAsync(id) {return id === 'collection' ? collection : null;}}};
  vm.runInNewContext(code, {figma, __html__: html, Uint8Array});
  return {figma, values, nodes, messages, writes, marker: () => marker,
    snapshot: () => JSON.stringify({variables: [...values.values()].map(item => [item.id, item.valuesByMode]),
      bindings: nodes.map(item => [item.id, item.boundVariables]), marker}),
    async send(message) {await figma.ui.onmessage(clone(message)); return messages.at(-1);}};
}

function manifest() {
  assert.equal(config.selection_manifest?.schema, 'figma-flow-selection-v2', 'host config must carry a pinned v2 manifest');
  assert.match(config.selection_manifest.plan_sha256, /^[0-9a-f]{64}$/);
  assert(config.changes.every(change => typeof change.identity === 'string' && change.identity.length > 0), 'every displayed change needs a host identity');
  return config.selection_manifest;
}
function selectedMessage(identity) {
  const m = manifest();
  const row = m.changes.find(item => item.identity === identity);
  const ids = row?.group ? m.changes.filter(item => item.group === row.group).map(item => item.identity) : [identity];
  return {type: 'apply', session: config.session, protocol: 2, plan_sha256: m.plan_sha256, selected_ids: ids};
}

// Select via real checkbox handlers; never manufacture a UI fixture/before value.
test('host config -> actual HTML checkbox -> sandbox changes one independent token only', async () => {
  manifest();
  const p = panel();
  assert.equal(p.boxes().length, config.changes.length);
  const index = config.changes.findIndex(change => change.name === 'left');
  assert(index >= 0, 'independent left token must be reviewable');
  const expected = selectedMessage(config.changes[index].identity).selected_ids;
  const toggled = new Set();
  for (let i = 0; i < config.changes.length; i++) {
    const row = config.changes[i];
    const group = row.group || row.identity;
    if (!expected.includes(row.identity) && !toggled.has(group)) {p.boxes()[i].onchange(); toggled.add(group);}
  }
  const message = p.apply();
  assert.equal(message.protocol, 2, 'real sender must send v2 selection');
  assert.equal(message.plan_sha256, config.selection_manifest.plan_sha256);
  assert.deepEqual([...message.selected_ids].sort(), [...expected].sort());
  assert(!('fixture' in message || 'observed' in message), 'UI cannot supply trusted observations');
  const w = world(), beforeBindings = JSON.stringify(w.nodes.map(node => node.boundVariables));
  const reply = await w.send(message);
  assert(!reply.error, reply.error);
  assert.equal(w.values.get('left').valuesByMode.mode, 22);
  assert.equal(w.values.get('right').valuesByMode.mode, 18, 'unchecked variable must remain exact');
  assert.equal(w.values.get('size').valuesByMode.mode, 18, 'unchecked alias root must remain exact');
  assert.deepEqual(w.writes, ['left']);
  assert.equal(JSON.stringify(w.nodes.map(node => node.boundVariables)), beforeBindings);
  assert.notEqual(JSON.parse(w.marker() || 'null')?.graph_sha256, config.graph_sha256, 'partial apply must not certify skipped state');
});

test('invalid selection fails without mutation and releases busy for a subsequent read', async () => {
  const id = manifest().changes.find(row => row.kind === 'token')?.identity || config.changes[0].identity;
  const base = selectedMessage(id);
  for (const override of [
    {selected_ids: []}, {selected_ids: undefined}, {selected_ids: [id, id]},
    {selected_ids: ['unknown']}, {plan_sha256: '0'.repeat(64)},
    {protocol: 1}, {fixture: {independent: []}, observed: {left: 18}},
  ]) {
    const w = world(), before = w.snapshot();
    const reply = await w.send({...base, ...override});
    assert(reply?.error || reply?.readback?.error, 'invalid v2 selection must return recoverable error evidence');
    assert.equal(w.snapshot(), before, 'rejected selection must preserve every value/binding/marker');
    const read = await w.send({type: 'read', session: config.session});
    assert(read.readback && !read.error, 'preflight error must not latch busy');
  }
});

test('selection validates actual native before values and preserves rollback', async () => {
  manifest();
  const row = config.changes.find(change => change.name === 'left');
  const w = world();
  w.values.get('left').valuesByMode.mode = 99;
  const before = w.snapshot();
  const reply = await w.send(selectedMessage(row.identity));
  assert(reply.error || reply.readback?.error, 'native CAS drift must be rejected');
  assert.equal(w.snapshot(), before);
});

test('legacy omission retains full apply', async () => {
  const w = world();
  const reply = await w.send({type: 'apply', session: config.session});
  assert(!reply.error, reply.error);
  assert.equal(w.values.get('left').valuesByMode.mode, 22);
  assert.equal(w.values.get('right').valuesByMode.mode, 26);
  assert.equal(w.values.get('size').valuesByMode.mode, 24);
});


test('component-field selection reaches production consumers and preserves skipped fields', async () => {
  const m = manifest();
  const row = m.changes.find(item => item.kind === 'component_field' && item.component_id === 'button' && item.field === 'paddingLeft');
  assert(row, 'host must expose actual component-field identities, not token-only fixtures');
  const w = world(), bindings = JSON.stringify(w.nodes.map(item => item.boundVariables));
  const reply = await w.send(selectedMessage(row.identity));
  assert(!reply.error, reply.error);
  for (const node of w.nodes.filter(item => ['main', 'instance'].includes(item.id))) {
    assert.equal(node.paddingLeft, 22);
    assert.equal(node.paddingRight, 18);
  }
  assert.equal(w.values.get('size').valuesByMode.mode, 18);
  assert.equal(JSON.stringify(w.nodes.map(item => item.boundVariables)), bindings);
  assert.deepEqual(w.writes, ['left']);
  assert.equal(reply.readback.components.find(item => item.node_id === 'instance').main_component_id, 'main');
});

test('alias and shared-consumer groups cannot be split; v1 cannot carry selections', async () => {
  const m = manifest();
  const grouped = m.changes.find(row => row.group && m.changes.filter(other => other.group === row.group).length > 1);
  assert(grouped, 'host must encode indivisible alias/shared-consumer groups');
  const base = selectedMessage(grouped.identity);
  for (const message of [{...base, selected_ids: [grouped.identity]},
    {type: 'apply', session: config.session, selection: ['left'], fixture: {}, observed: {}},
    {type: 'apply', session: config.session, protocol: 1, selected_ids: base.selected_ids}]) {
    const w = world(), before = w.snapshot();
    const reply = await w.send(message);
    assert(reply.error || reply.readback?.error, 'split group or legacy selection must fail');
    assert.equal(w.snapshot(), before);
  }
});

test('untrusted legacy payload preflight is contained and cannot latch the real handler', async () => {
  const w = world(), before = w.snapshot();
  let escaped;
  try {
    await w.send({type: 'apply', session: config.session, selection: ['left'],
      fixture: {independent: [{key: 'left', before: 18, after: 999}], alias_chain: []}, observed: {left: 18}});
  } catch (error) {escaped = error;}
  assert.equal(escaped, undefined, 'preflight must return failure evidence inside handler try/finally, without sandbox require');
  assert(w.messages.at(-1).error || w.messages.at(-1).readback?.error);
  assert.equal(w.snapshot(), before);
  const reply = await w.send({type: 'read', session: config.session});
  assert(reply.readback && !reply.error, 'handler must accept read after invalid input');
});
