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

  const graph = { externalConsumers: [], exportDispositions: [] };
  const packageManifest = {
    name: 'panel-knip-fixture', type: 'module', private: true, scripts: { build: 'node build.mjs' },
  };
  await write('panel-ui/package.json', packageManifest);
  await write('panel-ui/build.mjs', 'console.log("fixture build");');
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

  await rm(join(root, 'panel-ui/src/Orphan.mjs'));
  await write('panel-ui/src/app.jsx', appSource);
  await write('panel-ui/package.json', packageManifest);
  await write('tests/acceptance.cjs', 'let testSurface; // fixture acceptance reference');
  graph.exportDispositions = [{
    path: 'panel-ui/src/View.jsx',
    symbol: 'testSurface',
    reason: 'Fixture acceptance needs the export',
    approval: 'Synthetic test',
    reviewCondition: 'Reassess when acceptance changes',
    evidence: ['tests/acceptance.cjs'],
  }];
  await write('library/panel-design/governance.json', graph);
  const retained = await check({ root });
  assert.equal(retained.status, 'passed');
  assert.equal(retained.dispositions[0].applied, true);
  assert.match(retained.dispositions[0].sourceSha256, /^[0-9a-f]{64}$/);

  await write('panel-ui/src/View.jsx', viewSource);
  const stale = await check({ root });
  assert.equal(stale.status, 'failed');
  assert(stale.findings.some((row) => row.type === 'stale-export-disposition' && row.name === 'testSurface'));
});
