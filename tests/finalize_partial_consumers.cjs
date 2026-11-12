/* API-shaped fixtures only; these assertions do not claim live Figma origin. */
const assert = require('node:assert/strict');
const {readNativeSemantics} = require('../figma-bridge/native_semantic_read.js');
global.GRAPH_SYNC_SCHEMA = 'figma-flow-graph-token-sync-v1';
const {graphTokenSync} = require('../figma-bridge/graph_token_sync.js');

async function summary() {
  const rect = {id: 'rect', type: 'RECTANGLE', name: 'Rectangle', width: 12, height: 8};
  const page = {id: 'page', type: 'PAGE', name: 'Page', async loadAsync() {}, findAll: () => [rect]};
  rect.parent = page;
  return readNativeSemantics({}, page, {profile: 'summary', nodeIds: ['rect'], fields: ['width', 'height']});
}

if (process.argv.includes('--summary')) {
  summary().then(value => process.stdout.write(JSON.stringify(value))).catch(error => {console.error(error); process.exitCode = 1;});
} else {
  const test = require('node:test');
  test('actual projected summary cannot enter the normal native apply plan boundary', async () => {
    const partial = await summary();
    let apiCalls = 0;
    const figma = new Proxy({}, {get() {apiCalls++; throw Error('unexpected Figma API access');}});
    await assert.rejects(graphTokenSync(figma, partial, 'apply'), /invalid plan or operation/);
    assert.equal(apiCalls, 0);
  });

  test('extra summary evidence cannot bypass fresh native scalar getters or stale-before rejection', async () => {
    const partial = await summary();
    let reads = 0, writes = 0;
    const variable = {id: 'root', name: 'b/size/button', resolvedType: 'FLOAT', variableCollectionId: 'collection',
      get valuesByMode() {reads++; return {mode: 99};}, setValueForMode() {writes++;}};
    const page = {id: 'page', async loadAsync() {}, getPluginData: () => '', setPluginData() {writes++;}};
    const collection = {id: 'collection', modes: [{modeId: 'mode'}], defaultModeId: 'mode', variableIds: ['root'],
      getPluginData: () => JSON.stringify({pageId: 'page', collectionId: 'collection'})};
    const figma = {fileKey: 'file', currentPage: page, variables: {
      getVariableCollectionByIdAsync: async () => collection, getVariableByIdAsync: async () => variable}};
    const plan = {schema: GRAPH_SYNC_SCHEMA, graph_sha256: 'a'.repeat(64), file_key: 'file', page_id: 'page',
      collection_id: 'collection', pairing: true, evidence: partial, readback: partial,
      tokens: [{key: 'b/size/button', type: 'FLOAT', value: 18, before: 14,
        variable_name: 'b/size/button', variable_id: 'root', root_variable_id: 'root'}],
      components: [{id: 'button', main_keys: ['main'], instance_keys: ['instance'], properties: {}}]};
    await assert.rejects(graphTokenSync(figma, plan, 'apply'), /stale before value/);
    assert.ok(reads > 0, 'apply must consult the actual native variable getter');
    assert.equal(writes, 0);
  });
}
