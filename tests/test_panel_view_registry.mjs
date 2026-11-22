import assert from 'node:assert/strict';
import { access, cp, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { panelViewRegistryModule } from '../panel-ui/view-registry.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceGraph = JSON.parse(await readFile(path.join(root, 'library/panel-design/views.json'), 'utf8'));

async function fixture(graph) {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'panel-views-'));
  const graphPath = path.join(temporary, 'library/panel-design/views.json');
  await mkdir(path.dirname(graphPath), { recursive: true });
  await writeFile(graphPath, JSON.stringify(graph));
  for (const node of graph.nodes.filter((row) => row.type === 'code' && row.source)) {
    const target = path.resolve(path.dirname(graphPath), node.source);
    const original = path.join(root, path.relative(temporary, target));
    if (!await access(original).then(() => true, () => false)) continue;
    await mkdir(path.dirname(target), { recursive: true });
    await cp(original, target);
  }
  return { temporary, graphPath };
}

test('bundler module derives each React route from the view graph', async () => {
  const graph = structuredClone(sourceGraph);
  graph.nodes.push(
    {id: 'preview', type: 'screen', role: 'task', lifecycle: 'active', locale: 'relay'},
    {id: 'react-preview', type: 'code', source: '../../panel-ui/src/RelayViewer.jsx'},
  );
  graph.edges.push({from: 'preview', type: 'implemented by', to: 'react-preview'});
  const {temporary, graphPath} = await fixture(graph);
  try {
    const source = await panelViewRegistryModule({root: temporary, graphPath});
    assert.match(source, /"preview": PanelView6/);
    assert.match(source, /import PanelView6 from "\.\/RelayViewer\.jsx"/);
    assert.match(source, /"workspace": PanelView1/);
    assert.match(source, /"relay": PanelView0/);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

test('bundler rejects multiple registered homes and missing React sources', async () => {
  const multipleHomes = structuredClone(sourceGraph);
  const workspace = multipleHomes.nodes.find((row) => row.id === 'workspace');
  workspace.role = 'registered-home';
  workspace.lifecycle = 'active';
  const homeFixture = await fixture(multipleHomes);
  try {
    await assert.rejects(panelViewRegistryModule({root: homeFixture.temporary, graphPath: homeFixture.graphPath}),
      /exactly one registered-home/);
  } finally {
    await rm(homeFixture.temporary, { recursive: true, force: true });
  }

  const missingComponent = structuredClone(sourceGraph);
  missingComponent.nodes.find((row) => row.id === 'react-relay').source = '../../panel-ui/src/Missing.jsx';
  const componentFixture = await fixture(missingComponent);
  try {
    await assert.rejects(panelViewRegistryModule({root: componentFixture.temporary, graphPath: componentFixture.graphPath}),
      /React source is missing/);
  } finally {
    await rm(componentFixture.temporary, { recursive: true, force: true });
  }
});
