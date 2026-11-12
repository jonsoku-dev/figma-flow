const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const bundle = fs.readFileSync(process.argv[2], 'utf8');

function task(kind, html, onmessage, key = kind) {
  return {
    key, kind, revision: 'r', fileKey: 'file', pageId: '0:1', sourceSha256: 'abc',
    run() {
      const scoped = env.workspaceTaskFigma();
      scoped.showUI(html, {});
      scoped.ui.onmessage = onmessage;
    },
  };
}

function command(kind, operation) {
  return {
    key: kind, revision: 'r', file_key: 'file', page_id: '0:1', claim_id: '1'.repeat(32),
    deadline: Date.now() / 1000 + 30, operation, session_id: 'sess', id: 'op',
  };
}

const graph = '<script id="graph-panel-config" type="application/json">{"session":"s"}</script>';
const tasks = [
  task('discover', graph, message => {
    env.workspaceTaskFigma().ui.postMessage({session: 's', operation: message.type, readback: {schema: 'figma-flow-graph-native-discovery-v1', file_key: 'file', page_id: '0:1'}});
  }),
  task('sync', graph, message => {
    env.workspaceTaskFigma().ui.postMessage({session: 's', operation: message.type, readback: {schema: 'figma-flow-graph-token-readback-v1', file_key: 'file', page_id: '0:1', status: 'success'}});
  }),
  task('review', 'const PAIR = null;\n', () => {
    env.workspaceTaskFigma().ui.postMessage({type: 'readback', data: {packet_sha256: 'ab', fileKey: 'file', nodes: [{id: '1'}]}});
  }),
  task('native-edit', '<script type="application/json" id="flow-model">{"session":"s"}</script>', message => {
    env.workspaceTaskFigma().ui.postMessage({session: 's', operation: message.type, readback: {schema: 'figma-flow-graph-native-discovery-v1', fileKey: 'file', pageId: '0:1', native_edit: {operation: message.type, applied: false}}});
  }),
  task('import', '<html></html>', message => {
    const ui = env.workspaceTaskFigma().ui;
    if (message.type === 'ready') ui.postMessage({ready: true, session_nonce: message.session_nonce});
    if (message.type === 'export') ui.postMessage({type: 'readback', data: {format: 'figma-flow-readback-v1', pages: [{id: '0:1'}]}});
  }),
  task('discover', graph, message => {
    env.workspaceTaskFigma().ui.postMessage({session: 's', operation: message.type, readback: {schema: 'figma-flow-graph-native-discovery-v1', file_key: 'file', page_id: '0:1', error: 'bad'}});
  }, 'discover-error'),
];

const messages = [];
const env = {
  setTimeout, clearTimeout,
  FLOW_TASKS: tasks,
  FLOW_LOCALES: ['ko'],
  WORKSPACE_CHAT_DUPLICATE: 'duplicate',
  __html__: '<html></html>',
  figma: {
    fileKey: 'file',
    currentPage: {id: '0:1'},
    showUI() {},
    ui: {postMessage(message) { messages.push(message); }},
  },
};
vm.runInNewContext(bundle + '\nglobalThis.bundleHistory = () => workspaceState.history.slice();', env);

(async () => {
  const operations = {discover: 'read', sync: 'read', review: 'create', 'native-edit': 'read', import: 'read'};
  for (const item of tasks.slice(0, 5)) {
    const value = await env.controlExecute(item, command(item.kind, operations[item.kind]));
    assert.ok(value);
  }
  await assert.rejects(env.controlExecute(tasks[5], command('discover-error', 'read')), /expected native evidence/);
  assert.ok(env.bundleHistory().some(event => event.status === 'failed' && event.taskKey === 'discover-error'));
  env.WORKSPACE_CONTROL_CONFIG = {url: 'http://localhost:9', token: 'private'};
  let step = 0;
  env.fetch = async () => {
    step += 1;
    if (step === 1) return {ok: true, json: async () => ({operation: command('discover', 'read')})};
    return {ok: false, status: 500, json: async () => ({})};
  };
  await env.workspaceControlTick();
  assert.equal(messages.some(item => item.type === 'workspace-control-state' && item.outcome === 'uncertain'), true);
  assert.equal(messages.some(item => item.outcome === 'finished'), false);
  console.log('bundle-kinds-ok');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
