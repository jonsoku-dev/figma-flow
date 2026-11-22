const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const fromRoot = (...parts) => path.join(root, ...parts);
const json = (name) => JSON.parse(fs.readFileSync(fromRoot(name), 'utf8'));

test('registered routes resolve to concrete panel views with one registered home', async () => {
  const { panelViewRegistryModule } = await import(pathToFileURL(fromRoot('panel-ui/view-registry.mjs')));
  const graph = json('library/panel-design/views.json');
  const generated = await panelViewRegistryModule({ root });
  const screens = graph.nodes.filter((node) => node.type === 'screen');

  assert.equal(screens.filter((node) => node.role === 'registered-home' && node.lifecycle === 'active').length, 1);
  assert.equal(screens.length, 6);
  for (const screen of screens) {
    const edge = graph.edges.find((item) => item.from === screen.id && item.type === 'implemented by');
    const implementation = graph.nodes.find((item) => item.id === edge?.to && item.type === 'code');
    assert.ok(implementation, `${screen.id} has a code implementation`);
    assert.ok(fs.existsSync(fromRoot('panel-ui/src', implementation.source.split('/').at(-1))), `${screen.id} source exists`);
    assert.match(generated, new RegExp(`${JSON.stringify(screen.id)}: PanelView\\d+`));
  }
  assert.match(generated, /\.\/RelayViewer\.jsx/);
  assert.match(generated, /\.\/Workspace\.jsx/);
  assert.match(generated, /\.\/ImportPanel\.jsx/);
  assert.match(generated, /\.\/ReviewPanel\.jsx/);
  assert.match(generated, /\.\/GraphPanel\.jsx/);
  assert.match(generated, /\.\/ChatPanel\.jsx/);
});

test('panel design tokens project to the shipped CSS and all authored styles use known palette variables', () => {
  const result = spawnSync(process.execPath, [fromRoot('panel-ui/build-tokens.mjs'), '--check'], {
    cwd: root, encoding: 'utf8', timeout: 20000,
  });
  assert.equal(result.status, 0, result.stdout + result.stderr);

  const graph = json('library/panel-design/tokens.json');
  const css = fs.readFileSync(fromRoot('panel-ui/src/styles/tokens.css'), 'utf8');
  const declared = new Set(graph.tokens.map(({ id }) => `--${id}`));
  for (const { id } of graph.tokens) declared.add(`--${id}-dark`);
  for (const runtimeToken of ['--token-color', '--token-font-size', '--token-space']) declared.add(runtimeToken);
  const styles = fs.readdirSync(fromRoot('panel-ui/src/styles')).filter((name) => name.endsWith('.css'));
  for (const name of styles) {
    const source = fs.readFileSync(fromRoot('panel-ui/src/styles', name), 'utf8');
    for (const [, variable] of source.matchAll(/var\(\s*(--[a-z0-9-]+)/gi)) {
      assert.ok(declared.has(variable), `${name} references declared token ${variable}`);
    }
    if (name !== 'tokens.css') assert.doesNotMatch(source, /#[0-9a-f]{3,8}\b/i, `${name} keeps palette values in the graph`);
  }
  for (const token of graph.tokens) {
    assert.ok(css.includes(`--${token.id}: ${token.light};`));
    assert.ok(css.includes(`--${token.id}-dark: ${token.dark};`));
  }
  const relay = fs.readFileSync(fromRoot('panel-ui/src/styles/relay.css'), 'utf8');
  assert.equal(relay.split('__PANEL_TOKEN_relay-mobile-breakpoint__').length - 1, 1);
});

test('relay snapshot accepts only request and session bound host state', async () => {
  const source = fs.readFileSync(fromRoot('panel-ui/src/useRelaySnapshot.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export function useRelaySnapshot', 'function useRelaySnapshot');
  let receive;
  let queryClient;
  let queryOptions;
  const states = [];
  const sent = [];
  const signal = { addEventListener() {}, removeEventListener() {} };
  const maxNodes = json('library/figma-profile/read-limits.json').maxNodes;
  const window = {
    FlowUI: { locale: 'en', locales: ['en', 'ja'], setLocale(code) { this.locale = code; } },
    addEventListener(name, handler) { if (name === 'message') receive = handler; },
    removeEventListener() {},
  };
  class QueryClient {
    constructor() { queryClient = this; this.data = new Map(); }
    setQueryData(key, value) { this.data.set(JSON.stringify(key), value); }
    getQueryData(key) { return this.data.get(JSON.stringify(key)); }
  }
  const useState = (initializer) => {
    const value = typeof initializer === 'function' ? initializer() : initializer;
    states.push(value);
    return [value, () => {}];
  };
  const useEffect = (effect) => effect();
  const useQuery = (options) => { queryOptions = options; return { data: undefined }; };
  const useRelaySnapshot = new Function('useEffect', 'useState', 'QueryClient', 'useQuery', 'navigator', 'window', 'setTimeout', 'clearTimeout', '__FLOW_MAX_NODES__',
    `${source}\nreturn useRelaySnapshot;`)(useEffect, useState, QueryClient, useQuery,
      { languages: ['ja-JP'] }, window, () => 1, () => {}, maxNodes);
  useRelaySnapshot((message) => sent.push(message));
  const firstPoll = queryOptions.queryFn({ signal });
  const request = sent[0];
  assert.equal(request.type, 'workspace-home-ready');
  assert.equal(request.locale, 'en');
  assert.equal(typeof request.requestId, 'string');

  const base = {
    type: 'workspace-relay-viewer-state', requestId: request.requestId, workspaceSession: 'session-a', status: 'live',
    file: { key: 'file-a' }, page: { id: '0:1' }, selection: Array.from({ length: 25 }, (_, i) => ({
      id: `node-${i}`, type: 'FRAME', name: `Frame ${i}`,
    })), selectionTotal: 25, selectionTruncated: true, locale: 'ja',
  };
  const event = (pluginMessage) => receive({ data: { pluginMessage } });
  event({ ...base, requestId: 'another-request' });
  event({ ...base, status: 'invented' });
  event({ ...base, workspaceSession: '../bad' });
  assert.equal(queryClient.data.size, 0);

  event(base);
  const snapshot = queryClient.getQueryData(states[1].key);
  assert.equal(snapshot.status, 'live');
  assert.equal(snapshot.selection.length, maxNodes);
  assert.equal(snapshot.selectionTotal, 25);
  assert.equal(snapshot.selectionTruncated, true);
  assert.equal(window.FlowUI.locale, 'ja');
  assert.equal(typeof queryOptions.queryFn, 'function');
  await firstPoll;

  const secondPoll = queryOptions.queryFn({ signal });
  assert.deepEqual(sent[1], { type: 'workspace-control-tick', workspaceSession: 'session-a', fileKey: 'file-a' });
  event({ ...base, workspaceSession: 'session-b', status: 'offline' });
  assert.equal(queryClient.getQueryData(states[1].key).status, 'live');
  event({ ...base, status: 'busy' });
  assert.equal(queryClient.getQueryData(states[1].key).status, 'busy');
  await secondPoll;
  assert.equal(sent.length, 2);
});

test('import and review task reducers keep host outcomes fail closed', () => {
  const importSource = fs.readFileSync(fromRoot('panel-ui/src/ImportPanel.jsx'), 'utf8');
  const importStart = importSource.indexOf('function reduce(state, action)');
  const importEnd = importSource.indexOf('\n\nfunction NativeSummary', importStart);
  const importReduce = new Function('operations', 'syncStatuses', 'previewAddress',
    `${importSource.slice(importStart, importEnd)}\nreturn reduce;`)(
      new Set(['import', 'export', 'sync']), new Set(['baseline', 'applied', 'unchanged']), /^http:\/\/localhost:\d+\/$/);
  const base = { connected: true, paired: true, busy: false, operation: 'sync', fresh: true, preview: 'http://localhost:4000/' };
  const started = importReduce(base, { type: 'start', operation: 'sync' });
  assert.equal(started.status.kind, 'progress');
  assert.equal(started.preview, null);
  assert.equal(importReduce(started, { type: 'message', message: { type: 'preview', url: 'https://example.invalid/' } }).preview, null);
  assert.equal(importReduce(started, { type: 'message', message: { type: 'sync-result', result: { status: 'invented' } } }).status.kind, 'invalid-result');
  const readback = importReduce(started, { type: 'message', message: { type: 'readback', data: { safe: true } } });
  assert.deepEqual(readback.data, { safe: true });

  const reviewSource = fs.readFileSync(fromRoot('panel-ui/src/ReviewPanel.jsx'), 'utf8');
  const reviewStart = reviewSource.indexOf('function readbackNotice(');
  const reviewEnd = reviewSource.indexOf('\n\nconst productionCopy', reviewStart);
  const reviewFunctions = reviewSource.slice(reviewStart, reviewEnd);
  const initialState = { result: null, resultKind: null, nativeBusy: false, receipt: null, deliveryFailed: false,
    notice: { state: 'ready', title: 'readyTitle', body: 'readyBody', details: '' } };
  const { reducer: reviewReduce } = new Function('initialState', `${reviewFunctions}\nreturn {reducer};`)(initialState);
  const created = reviewReduce(initialState, { type: 'create' });
  assert.equal(created.nativeBusy, true);
  const pendingRead = reviewReduce(created, { type: 'readback', data: { schema: 'readback' }, paired: true });
  assert.equal(pendingRead.receipt, 'pending');
  const rejected = reviewReduce(pendingRead, { type: 'receipt', passed: false, details: 'receipt rejected' });
  assert.equal(rejected.receipt, 'rejected');
  assert.equal(rejected.notice.state, 'error');
  assert.equal(reviewReduce(rejected, { type: 'status', message: { state: 'ready', busy: false } }).notice.title, 'rejectedTitle');
  assert.equal(reviewReduce(pendingRead, { type: 'geometry-failure', data: { issue: 'missing' } }).resultKind, 'failure');
});

test('chat input helpers classify bounded selection and recoverable errors', () => {
  const source = fs.readFileSync(fromRoot('panel-ui/src/ChatPanel.jsx'), 'utf8')
    .replace(/^import .*;\s*$/gm, '');
  const helpers = source.slice(source.indexOf('const UUID ='), source.indexOf('export default function ChatPanel'));
  const chatContract = json('library/panel-design/contracts.json').nodes.find(({ id }) => id === 'chat-error-codes');
  const chatErrorMessageKeys = Object.fromEntries(chatContract.codes.map(({ code, messageKey }) => [code, messageKey]));
  const { requestId, selectedTypes, errorKey } = new Function('globalThis', 'Uint8Array', 'chatErrorMessageKeys',
    `${helpers}\nreturn {requestId, selectedTypes, errorKey};`)(
      { crypto: { getRandomValues(bytes) { bytes.fill(1); return bytes; } } }, Uint8Array, chatErrorMessageKeys);
  assert.match(requestId(() => ''), /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.deepEqual(selectedTypes('draft\n\n{"selection":{"nodes":[{"type":"FRAME"},{"type":"TEXT"},{"type":"FRAME"}]}}'),
    [['FRAME', 2], ['TEXT', 1]]);
  assert.deepEqual(selectedTypes('malformed'), []);
  assert.equal(errorKey('요청이 불확실합니다'), 'uncertain');
  assert.equal(errorKey('20개 제한'), 'limitError');
  assert.equal(errorKey('이전 작업이 만료'), 'expired');
  assert.equal(errorKey('localized native diagnostic', 'scope'), 'scopeError');
  assert.equal(errorKey('localized native diagnostic', 'limit'), 'limitError');
  assert.equal(errorKey('localized native diagnostic', 'uncertain'), 'uncertain');
});

test('task domain helpers preserve selection, evidence, freshness and current execution state', async () => {
  const load = async (name) => import(pathToFileURL(fromRoot(`panel-ui/src/${name}`)));
  const [{ graphSelection }, { nativeSummaryView }, { dependencyFreshness, dependencyView },
    { assetInventory }, { verifiedPresentationLink }, { workspaceActivity }, { selectRecommendation }, detail] = await Promise.all([
      load('graphSelection.mjs'), load('nativeSummary.mjs'), load('dependencyView.mjs'), load('assetInventory.mjs'),
      load('carouselPresentation.mjs'), load('WorkspaceActivity.mjs'), load('workspaceRecommendation.mjs'), load('operationDetail.mjs'),
    ]);

  const changes = graphSelection([{ identity: 'text', targets: ['node-a', 'node-b'] }, { identity: 'color' }], ['text']);
  assert.equal(changes.count, 1);
  assert.deepEqual(changes.rows[0], { identity: 'text', targets: ['node-a', 'node-b'], selected: true });
  assert.equal(changes.rows[1].selected, false);

  const summary = nativeSummaryView({ schema: 'figma-flow-native-read-summary-v1', coverage: {
    profile: 'summary', complete: false, fields: ['name'], nodeIds: ['0:1'], omitted: ['fills'],
  }, nodes: [{ id: '0:1', name: 'Hero' }] });
  assert.equal(summary.ready, true);
  assert.equal(summary.read_only, true);
  assert.deepEqual(summary.rows[0].values, [{ field: 'name', value: 'Hero' }]);
  assert.equal(nativeSummaryView({ ...summary, schema: 'wrong' }).ready, false);

  const tasks = [
    { key: 'foundation', title: 'Foundation', revision: 'r2' },
    { key: 'screen', title: 'Screen', revision: 'r3', depends_on: [{ relation: 'uses-output', artifact: 'code.js', task_key: 'foundation', revision: 'r1', artifact_sha256: 'a'.repeat(64) }] },
  ];
  const workspaceCopy = json('figma-bridge/locales/workspace.json');
  const localize = (locale) => (key, params = {}) =>
    workspaceCopy[`workspace.${key}`][locale].replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`);
  assert.equal(dependencyView(tasks, 'screen', localize('ko')).predecessors[0].pinned_revision, 'r1');
  assert.deepEqual(dependencyFreshness(tasks).labels.map(({ state }) => state), ['stale']);
  assert.equal(dependencyFreshness([{ key: 'screen', revision: 'r3', depends_on: tasks[1].depends_on }], [{ key: 'foundation', revision: 'r1' }]).labels[0].state, 'retired');
  assert.match(dependencyView(tasks, 'screen', localize('en')).text[0], /^Predecessor Foundation \(foundation\) · Current r2 · Pinned r1/);
  assert.match(dependencyView(tasks, 'screen', localize('ja')).text[0], /^先行 Foundation \(foundation\) · 現在 r2 · 固定 r1/);
  assert.equal(dependencyView([{ key: 'alone' }], 'alone', localize('en')).text[0], 'No linked predecessors or successors');
  const importCopy = json('figma-bridge/locales/import.json');
  for (const locale of ['ko', 'en', 'ja']) {
    assert.ok(importCopy['import.partialReadSummary'][locale]);
    assert.ok(importCopy['import.readDimensionsOnly'][locale]);
  }

  const inventory = assetInventory([
    { ref: 'hero.png', kind: 'image', status: 'ready', digest: 'd1' },
    { ref: 'font.woff', kind: 'font', status: '404' },
  ]);
  assert.equal(inventory.ready, false);
  assert.equal(inventory.problems, 1);
  assert.equal(inventory.rows[0].status, '404');

  const task = { key: 'screen', kind: 'native-edit', revision: 'r3', fileKey: 'file-a', pageId: '0:1' };
  const history = [{ taskKey: 'screen', revision: 'r3', executionId: 'exec-a', carousel: {
    status: 'current', file_key: 'file-a', page_id: '0:1', flow_start_node_id: '2:3', initial_state: 'idle',
  } }];
  const url = 'https://www.figma.com/proto/file-a/screen?node-id=2-3&starting-point-node-id=2-3&page-id=0-1&scaling=scale-down';
  assert.deepEqual(verifiedPresentationLink({ type: 'workspace-carousel-presented', taskKey: 'screen', executionId: 'exec-a', nodeId: '2:3', stateId: 'idle', url },
    { fileKey: 'file-a', tasks: [task], history }), { taskKey: 'screen', executionId: 'exec-a', url });
  assert.equal(verifiedPresentationLink({ type: 'workspace-carousel-presented', taskKey: 'screen', executionId: 'exec-a', nodeId: '2:3', stateId: 'wrong', url },
    { fileKey: 'file-a', tasks: [task], history }), null);

  const activity = workspaceActivity([{ key: 'screen', revision: 'r3' }], [
    { taskKey: 'screen', revision: 'r3', executionId: 'exec-a', status: 'running', operation: 'apply' },
  ]);
  assert.equal(activity.counts.running, 1);
  assert.equal(activity.flows[0].executionId, 'exec-a');
  assert.equal(selectRecommendation({ fileKey: 'file-a', tasks: [] }, [task]).task, task);

  const scope = detail.buildDetailScope({ fileKey: 'file-a', pageId: '0:1' }, 'session-a');
  assert.equal(detail.scopesMatch(scope, { ...scope }), true);
  assert.equal(detail.redactDetailText('Private /Users/alice/secret?token=hidden'), 'Private [home]/secret?token=[redacted]');
});
