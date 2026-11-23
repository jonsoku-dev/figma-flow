const assert = require('node:assert/strict');
const { mkdir, mkdtemp, rm, symlink, writeFile } = require('node:fs/promises');
const { tmpdir } = require('node:os');
const { dirname, join, resolve } = require('node:path');
const { test } = require('node:test');

test('Knip resolves the real registry and blocks new or stale production usage findings', async (t) => {
  const { check } = await import('../panel-ui/knip.config.mjs');
  const root = await mkdtemp(join(tmpdir(), 'figma-flow-knip-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));

  async function write(path, content) {
    const target = join(root, path);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, typeof content === 'string' ? content : JSON.stringify(content));
  }

  const graph = { nodes: [], contractTests: {}, externalConsumers: [], exportDispositions: [] };
  const packageManifest = {
    name: 'panel-knip-fixture', type: 'module', private: true, scripts: { build: 'node build.mjs' },
  };
  await write('panel-ui/package.json', packageManifest);
  const build = 'import { buildOutput } from "./tooling.mjs"; console.log(buildOutput());';
  await write('panel-ui/build.mjs', build);
  await write('panel-ui/tooling.mjs', 'export const buildOutput = () => "build"; export const testOnlyOutput = () => 1;');
  await write('tests/tooling.cjs', 'const assert = require("node:assert/strict"); const { testOnlyOutput } = require("../panel-ui/tooling.mjs"); assert.equal(testOnlyOutput(), 1);');
  graph.contractTests['tests/tooling.cjs'] = ['tooling checks local output'];
  await symlink(resolve(__dirname, '../panel-ui/node_modules'), join(root, 'panel-ui/node_modules'), 'junction');
  await write('tools/maintenance-contract.json', {
    panelBoundaries: { entry: 'app.jsx', externalImports: {} },
  });
  await write('library/panel-design/governance.json', graph);
  await write('library/panel-design/views.json', {
    schema: 'figma-flow-panel-view-graph-v1',
    version: 1,
    nodes: [
      { id: 'home', type: 'screen', role: 'registered-home', lifecycle: 'active', locale: 'en' },
      { id: 'view', type: 'code', source: '../../panel-ui/src/View.jsx' },
    ],
    edges: [{ from: 'home', to: 'view', type: 'implemented by' }],
  });
  const appSource = 'import { views } from "./view-registry.generated.js"; console.log(views.home);';
  await write('panel-ui/src/app.jsx', appSource);
  const viewSource = 'export default function View() { return "fixture"; }\n';
  await write('panel-ui/src/View.jsx', viewSource);
  assert.equal((await check({ root })).status, 'passed');

  await write('panel-ui/src/Orphan.mjs', 'export default 42;');
  await write('panel-ui/orphan-tooling.mjs', 'export default 42;');
  await write('panel-ui/build.mjs', build + 'import "./missing-tooling.mjs";');
  await write('panel-ui/package.json', {
    ...packageManifest, dependencies: { react: '*' }, devDependencies: { picomatch: '*' },
  });
  await write('panel-ui/src/View.jsx', viewSource + 'export const testSurface = 42;');
  await write('panel-ui/src/app.jsx', appSource + 'import "./missing-module.js";');
  const violations = await check({ root });
  assert.equal(violations.status, 'failed');
  assert(violations.findings.some((row) => row.type === 'files' && row.path === 'panel-ui/src/Orphan.mjs'));
  assert(violations.findings.some((row) => row.type === 'dependencies' && row.name === 'react'));
  assert(violations.findings.some((row) => row.type === 'devDependencies' && row.name === 'picomatch'));
  assert(violations.findings.some((row) => row.type === 'exports' && row.name === 'testSurface'));
  assert(violations.findings.some((row) => row.type === 'unresolved' && row.name === './missing-module.js'));
  assert.equal(violations.findings.filter((row) => row.type === 'files' && row.path === 'panel-ui/src/Orphan.mjs').length, 1);
  const development = violations.runs.find((run) => run.mode === 'development');
  assert(development.issues.some((row) => row.type === 'files' && row.path === 'panel-ui/orphan-tooling.mjs'));
  assert(development.issues.some((row) => row.type === 'unresolved' && row.name === './missing-tooling.mjs'));
  assert(!violations.runs.find((run) => run.mode === 'production').issues.some((row) => row.path === 'panel-ui/orphan-tooling.mjs'));

  await rm(join(root, 'panel-ui/src/Orphan.mjs'));
  await rm(join(root, 'panel-ui/orphan-tooling.mjs'));
  await write('panel-ui/build.mjs', build);
  await write('panel-ui/src/app.jsx', appSource);
  await write('panel-ui/package.json', packageManifest);
  await write('tests/acceptance.cjs', '// assert.equal(testSurface, 42);');
  graph.exportDispositions = [{
    path: 'panel-ui/src/View.jsx',
    symbol: 'testSurface',
    reason: 'Fixture acceptance needs the export',
    approval: 'Synthetic test',
    reviewCondition: 'Reassess when acceptance changes',
    evidence: ['tests/acceptance.cjs'],
  }];
  await write('library/panel-design/governance.json', graph);
  const comment = await check({ root });
  assert.equal(comment.status, 'failed');
  assert(comment.findings.some((row) => row.type === 'stale-export-evidence' && row.name === 'testSurface'));

  await write('tests/acceptance.cjs', 'const assert = require("node:assert/strict"); const {testSurface} = require("../panel-ui/src/View.jsx"); assert.equal(testSurface, 42);');
  const retained = await check({ root });
  assert.equal(retained.status, 'passed');
  assert.equal(retained.dispositions[0].applied, true);
  assert.match(retained.dispositions[0].sourceSha256, /^[0-9a-f]{64}$/);

  await write('panel-ui/src/View.jsx', viewSource);
  const stale = await check({ root });
  assert.equal(stale.status, 'failed');
  assert(stale.findings.some((row) => row.type === 'stale-export-disposition' && row.name === 'testSurface'));
});
