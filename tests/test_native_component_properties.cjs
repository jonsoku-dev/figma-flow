const assert = require('node:assert/strict');
const {readNativeSemantics, nativeReadGetterLedger} = require('../figma-bridge/native_semantic_read.js');

function node(id, type) {
  return {id, type, name: id, children: [], width: 10, getPluginData: () => '',
    async loadAsync() {}, findAll() { return this.children; }};
}

(async () => {
  const page = node('page', 'PAGE');
  const component = node('component', 'COMPONENT');
  const text = node('text', 'TEXT');
  const unsupported = node('unsupported', 'RECTANGLE');
  const unavailable = node('unavailable', 'RECTANGLE');
  page.children = [component, text, unsupported, unavailable];
  for (const child of page.children) child.parent = page;
  let definitions = {
    'Icon#1': {type: 'INSTANCE_SWAP', defaultValue: 'original', preferredValues: [
      {type: 'COMPONENT', key: 'icon-key'}, {type: 'COMPONENT_SET', key: 'set-key'},
    ], description: 'Leading icon'},
    'Label#2': {type: 'TEXT', defaultValue: 'Hello'},
    Size: {type: 'VARIANT', defaultValue: 'Small', variantOptions: ['Small', 'Large']},
  };
  let references = {characters: 'Label#2', visible: 'Show#3', mainComponent: 'Icon#1'};
  let reads = 0;
  // Real node properties are API getters; definitions and references are returned data maps.
  Object.defineProperty(component, 'componentPropertyDefinitions', {get() { reads++; return definitions; }});
  Object.defineProperty(text, 'componentPropertyReferences', {get() { reads++; return references; }});
  component.componentPropertyReferences = null;
  for (const field of ['componentPropertyDefinitions', 'componentPropertyReferences']) {
    Object.defineProperty(unavailable, field, {get() { throw new Error('getter denied'); }});
  }
  const figma = {variables: {async getLocalVariableCollectionsAsync() { return []; }}};
  const row = (read, id) => read.nodes.find(item => item.id === id);
  const receipt = await nativeReadGetterLedger(figma, page);
  assert.deepEqual(row(receipt.full, 'component').componentPropertyDefinitions, definitions);
  assert.deepEqual(row(receipt.full, 'text').componentPropertyReferences, references);
  assert.equal(row(receipt.full, 'component').componentPropertyReferences, null);
  assert.ok(receipt.getters.includes('component.componentPropertyDefinitions'));
  assert.ok(receipt.getters.includes('text.componentPropertyReferences'));
  for (const field of ['componentPropertyDefinitions', 'componentPropertyReferences']) {
    for (const [id, reason] of [['unsupported', 'unsupported on this node'], ['unavailable', 'getter denied']]) {
      assert.equal(Object.hasOwn(row(receipt.full, id), field), false);
      assert.equal(row(receipt.full, id).unavailable_fields[field], reason);
      assert.ok(receipt.full.unavailableFields.some(item => item.nodeId === id && item.field === field && item.reason === reason));
    }
  }
  const beforeSummary = reads;
  const summary = await nativeReadGetterLedger(figma, page, {profile: 'summary', nodeIds: ['component', 'text'], fields: ['width']});
  assert.equal(reads, beforeSummary);
  assert.equal(summary.full.coverage.complete, false);
  for (const item of summary.full.nodes) {
    assert.equal(Object.hasOwn(item, 'componentPropertyDefinitions'), false);
    assert.equal(Object.hasOwn(item, 'componentPropertyReferences'), false);
  }
  assert.ok(!summary.getters.some(key => /componentProperty(Definitions|References)/.test(key)));
  definitions['Icon#1'].preferredValues[0].key = 'changed-key';
  references.characters = 'New label#4';
  const fresh = await readNativeSemantics(figma, page);
  assert.equal(row(fresh, 'component').componentPropertyDefinitions['Icon#1'].preferredValues[0].key, 'changed-key');
  assert.equal(row(fresh, 'text').componentPropertyReferences.characters, 'New label#4');
  assert.equal(row(receipt.full, 'component').componentPropertyDefinitions['Icon#1'].preferredValues[0].key, 'icon-key');
  assert.equal(row(receipt.full, 'text').componentPropertyReferences.characters, 'Label#2');
  // A summary request for component data must fall back to the complete read.
  const fallback = await readNativeSemantics(figma, page, {profile: 'summary', nodeIds: ['text'], fields: ['componentPropertyReferences']});
  assert.equal(fallback.coverage, undefined);
  assert.deepEqual(row(fallback, 'text').componentPropertyReferences, references);
})().catch(error => { console.error(error); process.exitCode = 1; });
