const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { rmSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const fromRoot = (...parts) => path.join(root, ...parts);
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const json = (name) => JSON.parse(read(name));
const DIMENSION = /(?<![\w-])-?(?:\d+(?:\.\d+)?|\.\d+)(?:vmin|vmax|rem|em|vw|vh|ch|px|ms|s|fr|deg|rad|turn|%)?(?![\w.-])/g;

function declarationValues(source) {
  const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, '');
  const rows = [];
  for (const match of withoutComments.matchAll(/(?:^|[;{}])\s*([\w-]+)\s*:\s*([^;{}]+)/gm)) {
    const property = match[1];
    const value = match[2].replace(/(['"])(?:\\.|(?!\1)[^\\])*?\1/g, ' ').replace(/var\([^)]*\)/g, 'var');
    for (const item of value.matchAll(DIMENSION)) rows.push({ property, value: item[0] });
  }
  return rows;
}

test('all authored panel CSS dimensions have graph tokens and an injected literal is detected', () => {
  const graph = json('library/panel-design/tokens.json');
  const tokenNames = new Set(graph.tokens.map(({ id }) => `--${id}`));
  for (const { id } of graph.tokens) tokenNames.add(`--${id}-dark`);
  const inlineModelTokens = new Set(['--token-color', '--token-font-size', '--token-space']);
  const roots = graph.surfaces.map(({ source }) => path.resolve(root, 'library/panel-design', source));
  const styleDir = path.dirname(roots.find((name) => name.endsWith('index.css')));
  const styles = fs.readdirSync(styleDir).filter((name) => name.endsWith('.css') && name !== 'tokens.css');

  for (const name of styles) {
    const source = fs.readFileSync(path.join(styleDir, name), 'utf8');
    assert.deepEqual(declarationValues(source), [], `${name} contains an unowned numeric CSS value`);
    for (const query of source.matchAll(/@media[^\{]+/g)) {
      if (/\b(?:min|max)-width\s*:/.test(query[0])) {
        assert.match(query[0], /__PANEL_TOKEN_(?:breakpoint-[a-z0-9-]+|relay-mobile-breakpoint)__/,
          `${name} responsive breakpoints point to a graph field`);
      }
    }
    for (const [, id] of source.matchAll(/__PANEL_TOKEN_([a-z][a-z0-9-]*)__/g)) {
      assert.ok(tokenNames.has(`--${id}`) || tokenNames.has(id), `${name} breakpoint ${id} exists in the graph`);
    }
    for (const [, variable] of source.matchAll(/var\(\s*(--[a-z0-9-]+)/gi)) {
      assert.ok(tokenNames.has(variable) || inlineModelTokens.has(variable), `${name} references ${variable}`);
    }
  }
  const mutation = declarationValues('.probe { padding-inline: 17px; line-height: 1.4; }');
  assert.deepEqual(mutation, [
    { property: 'padding-inline', value: '17px' },
    { property: 'line-height', value: '1.4' },
  ]);
});

test('graph preview metrics and workspace activity enums are projected from their field owners', () => {
  const design = json('library/panel-design/tokens.json');
  const workbench = design.surfaces.find(({ id }) => id === 'panel-workbench');
  const byId = new Map(design.tokens.map((token) => [token.id, token]));
  const expected = {
    graphTypePreviewMax: '48px',
    graphSpacingPreviewMax: '96px',
    dependencyGraphMinHeight: '112px',
    dependencyGraphRowPitch: '52px',
    dependencyGraphOuterPadding: '20px',
    dependencyGraphLabelLimit: '14',
    dependencyGraphWidth: '600px',
    dependencyGraphSideNodeWidth: '180px',
    dependencyGraphCenterNodeWidth: '160px',
    dependencyGraphNodeHeight: '40px',
    dependencyGraphNodeTop: '10px',
    dependencyGraphTextBaseline: '24px',
    dependencyGraphNodeRadius: '6px',
    dependencyGraphArrowViewSize: '10',
    dependencyGraphArrowAnchor: '9',
    dependencyGraphArrowCenter: '5',
    dependencyGraphArrowMarkerSize: '6',
  };
  assert.ok(workbench.metrics);
  for (const [key, value] of Object.entries(expected)) {
    const token = byId.get(workbench.metrics[key]);
    assert.ok(token, `panel-workbench metric ${key} points to a token`);
    assert.equal(token.light, value, `${key} preserves the existing observed value`);
    assert.equal(token.dark, value, `${key} has one shared numeric contract`);
  }

  const graph = json('specs/workspace-activity/graph.json');
  const activity = graph.nodes.find(({ id }) => id === 'CONTRACT-ACTIVITY-01');
  assert.ok(activity, 'workspace activity graph declares its machine-readable contract');
  assert.equal(activity.pendingStatus, 'pending');
  assert.deepEqual(activity.countedStatuses,
    ['pending', 'requested', 'running', 'finished', 'readback', 'baseline', 'verified', 'failed']);
  assert.deepEqual(activity.recommendationProgressStatuses, ['finished', 'readback', 'verified', 'baseline']);
  assert.deepEqual(activity.recommendationPhaseByKind, { default: 1, import: 2, pairedImport: 3, sync: 3 });

  const activitySource = read('panel-ui/src/WorkspaceActivity.mjs');
  const recommendationSource = read('panel-ui/src/workspaceRecommendation.mjs');
  assert.match(activitySource, /workspaceActivityContract\.countedStatuses/);
  assert.match(recommendationSource, /workspaceActivityContract\.recommendationProgressStatuses/);
  assert.match(recommendationSource, /workspaceActivityContract\.recommendationPhaseByKind/);
  assert.doesNotMatch(read('panel-ui/src/GraphPanel.jsx'), /Math\.min\((?:48|96),/);
  assert.doesNotMatch(read('panel-ui/src/Workspace.jsx'), /Math\.max\(112|length > 14/);
});

test('cross-language panel contract graph owns operation detail, dependency artifact and asset status enums', () => {
  const graph = json('library/panel-design/contracts.json');
  assert.equal(graph.schema, 'figma-flow-panel-contract-graph-v1');
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const detail = nodes.get('operation-detail-v1');
  assert.ok(detail);
  assert.deepEqual(detail.operationStates, ['pending', 'claimed', 'ok', 'error', 'uncertain', 'expired']);
  assert.deepEqual(detail.relationTypes, ['declared-dependency', 'recovery-of', 'artifact-input']);
  assert.deepEqual(detail.revisionBindings, ['current', 'pinned-historical', 'retired', 'orphan', 'unknown']);
  assert.deepEqual(nodes.get('dependency-artifacts')?.values,
    ['code.js', 'ui.html', 'manifest.json']);
  assert.equal(nodes.get('dependency-artifacts')?.relation, 'uses-output');
  assert.deepEqual(nodes.get('dependency-artifacts')?.directions, ['predecessor', 'successor']);
  const assetStatuses = nodes.get('asset-inventory-statuses')?.statuses;
  assert.deepEqual(assetStatuses.map(({ value }) => value), ['present', '404', 'rejected', 'external-unverified']);
  assert.deepEqual(assetStatuses.filter(({ severity }) => severity === 'problem').map(({ value }) => value),
    ['404', 'rejected', 'external-unverified']);
  assert.ok(nodes.get('chat-error-codes')?.codes.some(({ code, messageKey }) => code === 'scope' && messageKey === 'scopeError'));
  assert.deepEqual(graph.edges.map((edge) => `${edge.from}:${edge.to}`).sort(), [
    'asset-inventory-statuses:workspace-asset-list',
    'chat-error-codes:workspace-chat-view',
    'dependency-artifacts:workspace-dependency-view',
    'operation-detail-v1:workspace-operation-detail',
  ]);
});

test('React chat input bounds and row counts derive from the shared host contract graph', () => {
  const graph = json('figma-bridge/chat-input.json');
  assert.deepEqual(graph.message, { maxCharacters: 4000, rows: 3 });
  assert.deepEqual(graph.preview, { legacyRows: 11, reactRows: 9 });
  assert.match(read('panel-ui/src/panelContracts.mjs'), /chatInputGraph/);
  const chat = read('panel-ui/src/ChatPanel.jsx');
  assert.match(chat, /rows=\{chatInputPolicy\.message\.rows\}/);
  assert.match(chat, /maxLength=\{chatInputPolicy\.message\.maxCharacters\}/);
  assert.match(chat, /rows=\{chatInputPolicy\.preview\.reactRows\}/);
  assert.doesNotMatch(chat, /rows=\{(?:3|9)\}|maxLength=\{4000\}/);
});

test('operation detail producer imports in a fresh process with the canonical domain graph', () => {
  const result = spawnSync(process.env.PYTHON || 'python3', ['-B', '-c',
    "import sys;sys.path.insert(0,'tools');import operation_detail;print(operation_detail.DETAIL_SCHEMA)"],
  { cwd: root, encoding: 'utf8', timeout: 20000 });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), 'figma-flow-operation-detail-v1');
});

test('token projection mutation fails closed when an authoritative dimension changes', () => {
  const graph = json('library/panel-design/tokens.json');
  const token = graph.tokens.find(({ id }) => id === 'dimension-13px');
  assert.ok(token);
  token.light = '13.5px';
  const css = read('panel-ui/src/styles/tokens.css');
  assert.ok(css.includes('--dimension-13px: 13px;'));
  assert.ok(!css.includes('--dimension-13px: 13.5px;'));
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'panel-token-mutation-'));
  try {
    for (const relative of ['panel-ui/build-tokens.mjs', 'panel-ui/src/styles/tokens.css', 'library/panel-design/tokens.json']) {
      const target = path.join(temporary, relative);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.copyFileSync(fromRoot(relative), target);
    }
    const graphPath = path.join(temporary, 'library/panel-design/tokens.json');
    const mutated = JSON.parse(fs.readFileSync(graphPath, 'utf8'));
    mutated.tokens.find(({ id }) => id === 'dimension-13px').light = '13.5px';
    fs.writeFileSync(graphPath, JSON.stringify(mutated));
    const result = spawnSync(process.execPath, [path.join(temporary, 'panel-ui/build-tokens.mjs'), '--check'], {
      cwd: temporary, encoding: 'utf8', timeout: 20000,
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /tokens\.css is stale/);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});
