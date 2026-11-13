const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const [configPath, bridgePath] = process.argv.slice(2);
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const context = {};
vm.runInNewContext(fs.readFileSync(bridgePath, 'utf8')
  + '\nglobalThis.__probe = {discoverSelectedNativeApi};', context, {filename: bridgePath});

async function main() {
  const target = config.targets[0];
  assert.ok(['INSTANCE', 'COMPONENT'].includes(target.observed_type));
  const candidate = config.candidatesByType[target.observed_type][0];
  assert.ok(['getMainComponentAsync', 'getInstancesAsync', 'variantProperties'].includes(candidate.property));
  const page = {id: config.pageId};
  const instance = {id: target.observed_node_id, type: target.observed_type, parent: page,
    getPluginData(key) { return key === 'figmaFlowNativeApiLab'
      ? JSON.stringify({version: '0.31-scene-v1', semanticId: target.semantic_id}) : ''; },
    variantProperties: {PRIVATE_VARIANT_NAME: 'Private Variant Value'},
    async getMainComponentAsync() { return {id: 'PRIVATE-COMPONENT-ID', type: 'COMPONENT'}; },
    async getInstancesAsync() { return [{id: 'PRIVATE-INSTANCE-ID', type: 'INSTANCE'}]; }};
  const figma = {fileKey: config.fileKey, currentPage: page, root: null, mixed: Symbol('mixed'),
    async getNodeByIdAsync(id) { assert.equal(id, instance.id); return instance; }};
  const result = await context.__probe.discoverSelectedNativeApi(figma,
    {file_key: config.fileKey, page_id: config.pageId}, config);
  const observation = result.api_probe.observations[0];
  assert.equal(observation.status, 'success');
  if (candidate.property === 'getMainComponentAsync') assert.equal(observation.value, 'linked');
  else if (candidate.property === 'getInstancesAsync') assert.deepEqual(JSON.parse(JSON.stringify(observation.value)), {count: 1});
  else assert.deepEqual(JSON.parse(JSON.stringify(observation.value)), {count: 1});
  assert.ok(!JSON.stringify(result).includes('PRIVATE-COMPONENT-ID'));
  assert.ok(!JSON.stringify(result).includes('PRIVATE-INSTANCE-ID'));
  if (candidate.access === 'method') {
    const unowned = {...instance, getPluginData() { return ''; }};
    figma.getNodeByIdAsync = async () => unowned;
    const refused = await context.__probe.discoverSelectedNativeApi(figma,
      {file_key: config.fileKey, page_id: config.pageId}, config);
    assert.equal(refused.api_probe.observations[0].status, 'blocked');
    assert.equal(refused.api_probe.observations[0].reason, 'owned-fixture-required');
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
