const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const [configPath, bridgePath] = process.argv.slice(2);
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const context = {};
const source = fs.readFileSync(bridgePath, 'utf8')
  + '\nglobalThis.__probeApi = {discoverSelectedNativeApi};';
vm.runInNewContext(source, context, {filename: bridgePath});

async function main() {
  const methodNames = ['getCSSAsync', 'getRangeFontName', 'getRangeFontSize', 'getRangeFills'];
  const candidates = config.eligibleByType.TEXT.filter(row => methodNames.includes(row.property));
  assert.deepEqual(candidates.map(row => row.property).sort(), methodNames.slice().sort());
  config.targets = [config.targets.find(row => row.observed_type === 'TEXT')];
  config.eligibleByType = {TEXT: config.eligibleByType.TEXT};
  config.nodeTypeInterfaces = {TEXT: config.nodeTypeInterfaces.TEXT};
  config.candidatesByType.TEXT = candidates;
  const calls = [];
  const pageId = config.pageId;
  const node = {id: config.targets.find(row => row.observed_type === 'TEXT').observed_node_id,
    type: 'TEXT', parent: {id: pageId}, characters: 'private text',
    getCSSAsync: async () => ({width: '120px', color: '#f00', 'font-family': 'Private Font', content: 'private text'}),
    getRangeFontName: (start, end) => { calls.push(['font', start, end]); return {family: 'Inter', style: 'Semi Bold', variationSettings: {wght: 600}}; },
    getRangeFontSize: (start, end) => { calls.push(['size', start, end]); return 14; },
    getRangeFills: (start, end) => { calls.push(['fills', start, end]); return [{type: 'SOLID', color: {r: 1, g: 0, b: 0}}]; }};
  const figma = {fileKey: config.fileKey, currentPage: {id: pageId}, mixed: Symbol('mixed'),
    getNodeByIdAsync: async () => node};
  const scope = {file_key: config.fileKey, page_id: pageId};
  const result = await context.__probeApi.discoverSelectedNativeApi(figma, scope, config);
  assert.equal(result.api_probe.counts.success, 4);
  const observations = result.api_probe.observations.filter(row => methodNames.includes(row.property));
  const byName = Object.fromEntries(observations.map(row => [row.property,
    JSON.parse(JSON.stringify(row))]));
  assert.deepEqual(byName.getCSSAsync.value.projected.width, {type: 'number', value: 120, unit: 'px'});
  assert.equal(byName.getCSSAsync.value.projected.color.type, 'SOLID');
  assert.equal(byName.getRangeFontName.value.family, 'Inter');
  assert.equal(byName.getRangeFontName.value.variationSettings.wght, 600);
  assert.deepEqual(byName.getRangeFontSize.value, {mixed: false, value: 14});
  assert.equal(byName.getRangeFills.value[0].type, 'SOLID');
  assert.deepEqual(calls, [['fills', 0, 12], ['font', 0, 12], ['size', 0, 12]]);
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes('Private Font'));
  assert.ok(!serialized.includes('private text'));
  assert.ok(serialized.includes('"family":"Inter"'));

  const spoof = JSON.parse(JSON.stringify(config));
  spoof.candidatesByType.TEXT = [{...candidates[0], property: 'deleteCharacters', foundation: 'text-style',
    value_kind: 'font-range', access: 'method'}];
  spoof.fieldPolicy.deleteCharacters = {foundation: 'text-style', value_kind: 'font-range',
    access: 'method', allowed_receivers: ['TEXT']};
  await assert.rejects(context.__probeApi.discoverSelectedNativeApi(figma, scope, spoof), /non-allowlisted/);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
