'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const transportSource = fs.readFileSync(path.join(ROOT, 'figma-bridge/workspace_transport.js'), 'utf8');
const controlSource = fs.readFileSync(path.join(ROOT, 'figma-bridge/workspace_control.js'), 'utf8');
const hostSource = fs.readFileSync(path.join(ROOT, 'figma-bridge/workspace_host.js'), 'utf8');
const localeCatalog = JSON.parse(fs.readFileSync(path.join(ROOT, 'figma-bridge/locales/common.json'), 'utf8'));
const flowLocales = JSON.stringify(Object.keys(Object.values(localeCatalog)[0]));

const OP_A = '0123456789abcdef0123456789abcdef';
const OP_B = '11111111111111111111111111111111';
const OP_C = '22222222222222222222222222222222';
const REV_A = 'a'.repeat(64);
const REV_B = 'b'.repeat(64);
const REV_C = 'c'.repeat(64);
const REV_D = 'd'.repeat(64);
const RUNTIME = {
  version: '0.35.0',
  implementation: 'e'.repeat(64),
  generation: 'f'.repeat(32),
};
const CONTROL_TOKEN = 'secret-control-token-' + '9'.repeat(44);
const CHAT_TOKEN = 'secret-chat-token-' + '8'.repeat(47);

function makeValidDto(overrides = {}) {
  const base = {
    schema: 'figma-flow-operation-detail-v1',
    readOnly: true,
    operationId: OP_A,
    scope: {
      fileKey: 'fileA',
      pageId: '1:1',
      runtimeGeneration: RUNTIME.generation,
    },
    operation: 'apply',
    state: 'ok',
    classification: 'recorded',
    phase: 'result-received',
    phases: [
      { phase: 'queued', time: '2026-11-14T10:00:05Z' },
      { phase: 'claimed', time: '2026-11-14T10:00:01Z' },
      { phase: 'native-started', time: '2026-11-14T10:00:02Z' },
      { phase: 'result-received', time: '2026-11-14T10:00:03Z' },
    ],
    task: {
      key: 'screen-a',
      revision: REV_A,
      currentRevision: REV_B,
      revisionBinding: 'pinned-historical',
      kind: 'sync',
    },
    failure: null,
    relations: [
      {
        type: 'declared-dependency',
        direction: 'predecessor',
        taskKey: 'tokens',
        revision: REV_C,
        currentRevision: REV_C,
        revisionBinding: 'current',
        artifact: 'code.js',
        artifactSha256: REV_D,
        targetOperationId: OP_B,
      },
      {
        type: 'recovery-of',
        direction: 'recovers',
        operationId: OP_C,
        taskKey: 'screen-a',
        revision: REV_A,
        revisionBinding: 'pinned-historical',
      },
      {
        type: 'artifact-input',
        taskKey: 'screen-a',
        artifact: 'input-record.json',
        artifactSha256: REV_D,
        revision: REV_A,
        revisionBinding: 'pinned-historical',
        freshness: 'stale',
      },
    ],
    diff: {
      status: 'available',
      reason: null,
      basis: 'revision-pair',
      beforeRevision: REV_A,
      afterRevision: REV_B,
      truncated: false,
      totalFields: 2,
      fields: [
        { key: 'color.surface.primary', field: 'value', kind: 'changed', before: '#ffffff', after: '#f5f7fa' },
        {
          key: 'hero.copy',
          field: 'characters',
          kind: 'changed',
          before: { valueType: 'text', changed: true, length: 14 },
          after: { valueType: 'text', changed: true, length: 21 },
        },
      ],
      conflicts: [],
    },
    truncated: false,
    scopeNotice: 'read-only-exact-scope',
  };
  return { ...base, ...overrides };
}

function createBridgeHarness(options = {}) {
  const messages = [];
  const shown = [];
  const mutations = [];
  const requests = [];
  const listeners = new Map();
  const controlConfig = Object.prototype.hasOwnProperty.call(options, 'controlConfig')
    ? options.controlConfig
    : { url: 'http://localhost:49198', token: CONTROL_TOKEN };
  const runtimeConfig = Object.prototype.hasOwnProperty.call(options, 'runtime') ? options.runtime : RUNTIME;

  const figma = {
    fileKey: options.fileKey ?? 'fileA',
    currentPage: options.page ?? { id: '1:1', type: 'PAGE' },
    ui: {
      postMessage(message) {
        assert.equal(this, figma.ui);
        messages.push(message);
      },
    },
    viewport: {
      scrollAndZoomIntoView() {
        mutations.push('viewport');
      },
    },
    async getNodeByIdAsync() {
      return null;
    },
    async setCurrentPageAsync(page) {
      mutations.push('setCurrentPage:' + page?.id);
      this.currentPage = page;
    },
    createPage() {
      mutations.push('createPage');
    },
    openExternal() {
      mutations.push('openExternal');
    },
    showUI(html, opts) {
      shown.push({ html, opts });
    },
    on(eventName, callback) {
      if (!listeners.has(eventName)) listeners.set(eventName, new Set());
      listeners.get(eventName).add(callback);
    },
    clientStorage: {
      async getAsync() {
        return null;
      },
      async setAsync() {
        mutations.push('clientStorage.setAsync');
      },
    },
  };

  let fetchImpl = options.fetch;
  if (!fetchImpl) {
    fetchImpl = async (url, init) => {
      const route = url.split('/control/')[1];
      const body = JSON.parse(init.body);
      requests.push({ url, route, headers: init.headers, body });
      if (route === 'history') {
        const rows = options.historyRows || [
          {
            taskKey: 'screen-a',
            revision: REV_A,
            operationId: OP_A,
            operation: 'apply',
            classification: 'recorded',
            phase: 'result-received',
            phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
          },
        ];
        return { ok: true, status: 200, json: async () => ({ journalHistory: rows, inputFreshness: [] }) };
      }
      if (route === 'poll') {
        return { ok: true, status: 200, json: async () => ({ operation: null }) };
      }
      if (route === 'history-detail') {
        return { ok: true, status: 200, json: async () => makeValidDto() };
      }
      throw new Error('Unexpected route: ' + route);
    };
  }

  const context = vm.createContext({
    figma,
    __html__: 'HOME',
    fetch: async (url, init) => fetchImpl(url, init, requests),
    setTimeout: options.setTimeout || setTimeout,
    clearTimeout: options.clearTimeout || clearTimeout,
  });

  const prelude = `
    const FLOW_LOCALES = ${flowLocales};
    const WORKSPACE_CONTROL_CONFIG = ${JSON.stringify(controlConfig)};
    const WORKSPACE_CHAT_CONFIG = { url: 'http://127.0.0.1:49199', token: ${JSON.stringify(CHAT_TOKEN)} };
    const WORKSPACE_CHAT_UI = '<html><head></head><body>CHAT</body></html>';
    ${runtimeConfig === undefined ? '' : `const WORKSPACE_RUNTIME = ${JSON.stringify(runtimeConfig)};`}
    const FLOW_TASKS = [
      {
        key: 'screen-a',
        title: 'Screen A',
        project: 'App',
        kind: 'sync',
        fileKey: 'fileA',
        pageId: '1:1',
        revision: ${JSON.stringify(REV_B)},
        run() {
          const scoped = workspaceTaskFigma();
          scoped.showUI('<html><head></head><body>TASK</body></html>', {});
          scoped.ui.onmessage = async () => {};
        }
      }
    ];
  `;
  vm.runInContext([prelude, transportSource, controlSource, hostSource].join('\n'), context);

  const send = (message) => figma.ui.onmessage(message);
  async function listing() {
    await send({ type: 'workspace-home-ready' });
    return messages.filter((m) => m.type === 'workspace-tasks').at(-1);
  }
  async function emitPageChange(pageId) {
    figma.currentPage = { id: pageId, type: 'PAGE' };
    const cbs = [...(listeners.get('currentpagechange') || [])];
    for (const cb of cbs) await cb();
  }

  return { figma, context, messages, shown, mutations, requests, listeners, send, listing, emitPageChange };
}

test('transport admits history-detail with exact 262144-byte UTF-8 response cap and redacted error reasons', async () => {
  const calls = [];
  const env = vm.createContext({
    WORKSPACE_CONTROL_CONFIG: { url: 'http://127.0.0.1:49198', token: CONTROL_TOKEN },
    setTimeout,
    clearTimeout,
    fetch: async (url, opts) => {
      calls.push({ url, opts });
      return env.__nextResponse;
    },
  });
  vm.runInContext(transportSource, env);

  // Exact 262,144 UTF-8 bytes succeeds
  const prefix = '{"note":"';
  const suffix = '"}';
  const exactPad = 'a'.repeat(262144 - prefix.length - suffix.length);
  env.__nextResponse = { ok: true, status: 200, json: async () => JSON.parse(prefix + exactPad + suffix) };
  const okVal = await env.controlRequest('history-detail', { operation_id: OP_A });
  assert.equal(okVal.note.length, 262144 - prefix.length - suffix.length);
  assert.equal(calls.at(-1).url, 'http://127.0.0.1:49198/control/history-detail');

  // 262,145 UTF-8 bytes fails with payload-limit-exceeded
  const overUtf8 = { note: '가'.repeat(Math.ceil(262144 / 3)) };
  env.__nextResponse = { ok: true, status: 200, json: async () => overUtf8 };
  await assert.rejects(
    env.controlRequest('history-detail', { operation_id: OP_A }),
    (err) => err.code === 'payload-limit-exceeded' && /limit/.test(err.message),
  );

  // Content-Length header > 262144 rejects before reading JSON body
  let jsonCalled = false;
  env.__nextResponse = {
    ok: true,
    status: 200,
    headers: { get: (h) => (h.toLowerCase() === 'content-length' ? '262145' : null) },
    json: async () => {
      jsonCalled = true;
      return {};
    },
  };
  await assert.rejects(
    env.controlRequest('history-detail', { operation_id: OP_A }),
    (err) => err.code === 'payload-limit-exceeded',
  );
  assert.equal(jsonCalled, false);

  // 404 / 409 attach status and safe reason without leaking arbitrary error strings
  env.__nextResponse = {
    ok: false,
    status: 404,
    json: async () => ({ error: 'secret details /Users/alice', reason: 'not-found-in-scope' }),
  };
  await assert.rejects(
    env.controlRequest('history-detail', { operation_id: OP_A }),
    (err) => err.status === 404 && err.reason === 'not-found-in-scope' && !err.message.includes('alice'),
  );
});

test('host forwards exact 7-key request, enforces pre-flight & post-flight binding, and preserves read-only + 80-row summary', async () => {
  const h = createBridgeHarness({
    historyRows: Array.from({ length: 85 }, (_, i) => ({
      taskKey: i === 84 ? 'screen-a' : 'other-task',
      revision: REV_A,
      operationId: i === 84 ? OP_A : i.toString(16).padStart(32, '0'),
      operation: 'apply',
      classification: 'recorded',
      phase: 'result-received',
      phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
    })),
  });
  const list = await h.listing();
  assert.equal(list.pageId, '1:1');
  assert.equal(list.fileKey, 'fileA');
  assert.equal(list.runtimeGeneration, RUNTIME.generation);
  assert.equal(list.journalHistory.length, 80);
  assert.equal(JSON.stringify(list).includes(CONTROL_TOKEN), false);
  assert.equal(JSON.stringify(list).includes(CHAT_TOKEN), false);

  const reqCountBefore = h.requests.length;
  h.mutations.length = 0;

  // 1. UI executionId and malformed operationId rejected with zero HTTP calls
  for (const badOp of ['mabc12-xyz', '', null, 'G'.repeat(32), 'a'.repeat(31)]) {
    await h.send({
      type: 'workspace-history-detail',
      workspaceSession: list.workspaceSession,
      operationId: badOp,
      taskKey: 'screen-a',
      revision: REV_A,
      requestId: 'req-bad-op',
    });
    const res = h.messages.at(-1);
    assert.equal(res.type, 'workspace-history-detail-result');
    assert.equal(res.status, 'error');
    assert.equal(res.reason, 'invalid-operation-id');
    assert.equal(res.detail, null);
    assert.equal(res.requestId, 'req-bad-op');
  }

  // 2. Missing/invalid taskKey or revision rejected with zero HTTP calls
  for (const [badKey, badRev] of [['', REV_A], ['x'.repeat(201), REV_A], ['screen-a', 'not-sha256'], ['screen-a', '']]) {
    await h.send({
      type: 'workspace-history-detail',
      workspaceSession: list.workspaceSession,
      operationId: OP_A,
      taskKey: badKey,
      revision: badRev,
      requestId: 'req-bad-bind',
    });
    const res = h.messages.at(-1);
    assert.equal(res.status, 'error');
    assert.equal(res.reason, 'invalid-task-revision-binding');
    assert.equal(res.detail, null);
  }

  // 3. Pre-flight mismatch against workspaceServerHistory rejected with zero HTTP calls
  await h.send({
    type: 'workspace-history-detail',
    workspaceSession: list.workspaceSession,
    operationId: OP_A,
    taskKey: 'wrong-task',
    revision: REV_A,
    requestId: 'req-mismatch-key',
  });
  assert.equal(h.messages.at(-1).reason, 'task-revision-mismatch');
  await h.send({
    type: 'workspace-history-detail',
    workspaceSession: list.workspaceSession,
    operationId: OP_A,
    taskKey: 'screen-a',
    revision: REV_B,
    requestId: 'req-mismatch-rev',
  });
  assert.equal(h.messages.at(-1).reason, 'task-revision-mismatch');
  assert.equal(h.requests.length, reqCountBefore, 'invalid pre-flight requests must not touch HTTP');

  // 4. Forged workspaceSession is ignored silently with zero HTTP calls
  const msgCountBefore = h.messages.length;
  await h.send({
    type: 'workspace-history-detail',
    workspaceSession: 'forged-session',
    operationId: OP_A,
    taskKey: 'screen-a',
    revision: REV_A,
    requestId: 'req-forged',
  });
  assert.equal(h.messages.length, msgCountBefore);
  assert.equal(h.requests.length, reqCountBefore);

  // 5. Valid request sends exact 7-key body and forwards validated DTO preserving server phase order
  await h.send({
    type: 'workspace-history-detail',
    workspaceSession: list.workspaceSession,
    operationId: OP_A,
    taskKey: 'screen-a',
    revision: REV_A,
    requestId: 'req-ok',
  });
  const detailReq = h.requests.at(-1);
  assert.equal(detailReq.route, 'history-detail');
  assert.deepEqual(Object.keys(detailReq.body).sort(), [
    'file_key',
    'operation_id',
    'page_id',
    'revision',
    'runtime',
    'session_id',
    'task_key',
  ]);
  assert.equal(detailReq.body.file_key, 'fileA');
  assert.equal(detailReq.body.page_id, '1:1');
  assert.deepEqual(detailReq.body.runtime, RUNTIME);
  assert.equal(detailReq.body.operation_id, OP_A);
  assert.equal(detailReq.body.task_key, 'screen-a');
  assert.equal(detailReq.body.revision, REV_A);

  const okRes = h.messages.at(-1);
  assert.equal(okRes.status, 'ok');
  assert.equal(okRes.reason, null);
  assert.equal(okRes.requestId, 'req-ok');
  assert.equal(okRes.detail.schema, 'figma-flow-operation-detail-v1');
  assert.equal(okRes.detail.readOnly, true);
  // Preserves exact canonical phase order even though queued timestamp > claimed timestamp
  assert.deepEqual(okRes.detail.phases.map((p) => p.phase), ['queued', 'claimed', 'native-started', 'result-received']);
  assert.equal(okRes.detail.relations.length, 3);
  assert.deepEqual(h.mutations, [], 'detail inspection must remain strictly read-only');
});

test('host rejects post-flight scope, runtime, and task/revision mismatches and scrubs secrets/raw readbacks', async () => {
  let nextDto;
  const h = createBridgeHarness({
    fetch: async (url) => {
      const route = url.split('/control/')[1];
      if (route === 'history') return { ok: true, status: 200, json: async () => ({ journalHistory: [], inputFreshness: [] }) };
      if (route === 'history-detail') return { ok: true, status: 200, json: async () => nextDto };
      throw new Error('Unexpected route ' + route);
    },
  });
  const list = await h.listing();

  // Mismatched task/revision in returned DTO -> task-revision-mismatch
  nextDto = makeValidDto({ task: { key: 'other-task', revision: REV_A, currentRevision: REV_B, revisionBinding: 'current', kind: 'sync' } });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'r1' });
  assert.equal(h.messages.at(-1).status, 'error');
  assert.equal(h.messages.at(-1).reason, 'task-revision-mismatch');
  assert.equal(h.messages.at(-1).detail, null);

  // Mismatched page scope in returned DTO -> request-rejected
  nextDto = makeValidDto({ scope: { fileKey: 'fileA', pageId: '9:9', runtimeGeneration: RUNTIME.generation } });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'r2' });
  assert.equal(h.messages.at(-1).status, 'error');
  assert.equal(h.messages.at(-1).reason, 'request-rejected');
  assert.equal(h.messages.at(-1).detail, null);

  // Mismatched runtimeGeneration in returned DTO -> runtime-mismatch
  nextDto = makeValidDto({ scope: { fileKey: 'fileA', pageId: '1:1', runtimeGeneration: '0'.repeat(32) } });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'r3' });
  assert.equal(h.messages.at(-1).status, 'error');
  assert.equal(h.messages.at(-1).reason, 'runtime-mismatch');
  assert.equal(h.messages.at(-1).detail, null);

  // Secret/raw-readback scrubbing, invented-relation stripping, and 200-row diff cap
  const manyFields = Array.from({ length: 205 }, (_, idx) => ({
    key: `node.${idx}`,
    field: 'fontSize',
    kind: 'changed',
    before: 12,
    after: 14 + idx,
  }));
  manyFields[0] = {
    key: 'hero.copy',
    field: 'characters',
    kind: 'changed',
    before: 'CONFIDENTIAL CUSTOMER TEXT',
    after: 'UPDATED SECRET TEXT',
  };
  manyFields[1] = {
    key: 'token.url',
    field: 'value',
    kind: 'changed',
    before: `https://user:pass@localhost/p?token=${CONTROL_TOKEN}&x=1`,
    after: `/Users/alice/private Bearer ${CHAT_TOKEN}`,
  };

  nextDto = makeValidDto({
    readback_json: '{"nodes":[{"id":"secret-raw-node"}]}',
    control_token: CONTROL_TOKEN,
    conflict_detail: { before: 'RAW BEFORE', observed: 'RAW OBSERVED' },
    relations: [
      { type: 'timestamp-adjacent', taskKey: 'other', revision: REV_B },
      { type: 'declared-dependency', direction: 'predecessor', taskKey: 'tokens', revision: REV_C, currentRevision: REV_C, revisionBinding: 'current', artifact: 'code.js', artifactSha256: REV_D, targetOperationId: OP_B },
    ],
    diff: {
      status: 'available',
      reason: null,
      basis: 'revision-pair',
      beforeRevision: REV_A,
      afterRevision: REV_B,
      truncated: false,
      totalFields: 205,
      fields: manyFields,
      conflicts: [
        {
          key: 'hero.copy',
          scope: 'node',
          field: 'characters',
          reasonCode: 'native-text-mismatch',
          planSha256: REV_D,
          expectedBefore: 'RAW EXPECTED',
          plannedAfter: 'RAW PLANNED',
          observed: 'RAW OBSERVED',
        },
      ],
    },
  });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'r4' });
  const sanitized = h.messages.at(-1);
  assert.equal(sanitized.status, 'ok');
  const serialized = JSON.stringify(sanitized);
  for (const forbidden of [CONTROL_TOKEN, CHAT_TOKEN, 'CONFIDENTIAL CUSTOMER TEXT', 'UPDATED SECRET TEXT', 'secret-raw-node', 'RAW BEFORE', 'RAW OBSERVED', 'RAW EXPECTED', 'RAW PLANNED', '/Users/alice', 'timestamp-adjacent']) {
    assert.equal(serialized.includes(forbidden), false, `Must not leak ${forbidden}`);
  }
  assert.equal(sanitized.detail.relations.length, 1);
  assert.equal(sanitized.detail.diff.fields.length, 200);
  assert.equal(sanitized.detail.diff.totalFields, 205);
  assert.equal(sanitized.detail.diff.truncated, true);
  assert.equal(sanitized.detail.truncated, true);
  assert.equal(sanitized.detail.scopeNotice, 'read-only-truncated-256kib');
  assert.deepEqual(JSON.parse(JSON.stringify(sanitized.detail.diff.fields[0].before)), { valueType: 'text', changed: true, length: 'CONFIDENTIAL CUSTOMER TEXT'.length });
  assert.deepEqual(JSON.parse(JSON.stringify(sanitized.detail.diff.conflicts[0].observed)), { valueType: 'text', changed: true, length: 'RAW OBSERVED'.length });

  // Legacy & unknown paths never invent phases, relations, or diffs
  nextDto = makeValidDto({
    classification: 'legacy',
    phase: 'native-started',
    phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
  });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'r5' });
  const legacyRes = h.messages.at(-1);
  assert.equal(legacyRes.status, 'ok');
  assert.equal(legacyRes.detail.classification, 'legacy');
  assert.equal(legacyRes.detail.phase, 'unknown');
  assert.equal(legacyRes.detail.phases.length, 0);
  assert.equal(legacyRes.detail.relations.length, 0);
  assert.equal(legacyRes.detail.diff.status, 'unavailable');
  assert.equal(legacyRes.detail.diff.fields.length, 0);

  nextDto = makeValidDto({
    classification: 'unknown',
    phase: 'reconciled',
    phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
  });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'r6' });
  const unknownRes = h.messages.at(-1);
  assert.equal(unknownRes.status, 'ok');
  assert.equal(unknownRes.detail.classification, 'unknown');
  assert.equal(unknownRes.detail.phase, 'unknown');
  assert.equal(unknownRes.detail.phases.length, 0);
  assert.equal(unknownRes.detail.relations.length, 0);
  assert.equal(unknownRes.detail.diff.status, 'unavailable');
  assert.equal(unknownRes.detail.diff.fields.length, 0);
});

test('host maps HTTP 404/409/403/timeout/unavailable accurately and handles delayed response & scope-changed resets', async () => {
  let detailHandler;
  const h = createBridgeHarness({
    fetch: async (url, init) => {
      const route = url.split('/control/')[1];
      if (route === 'history') {
        const pageId = JSON.parse(init.body).page_id;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            journalHistory: [
              { taskKey: 'screen-a', revision: REV_A, operationId: pageId === '1:1' ? OP_A : OP_B, operation: 'apply', classification: 'recorded', phase: 'result-received', phases: [] },
            ],
            inputFreshness: [],
          }),
        };
      }
      if (route === 'poll') return { ok: true, status: 200, json: async () => ({ operation: null }) };
      if (route === 'history-detail') return detailHandler(JSON.parse(init.body));
      throw new Error('Unexpected route ' + route);
    },
  });
  const list = await h.listing();

  // HTTP 404 -> unavailable / not-found-in-scope
  detailHandler = async () => ({ ok: false, status: 404, json: async () => ({ error: 'Control operation not found in this scope', reason: 'not-found-in-scope' }) });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'e1' });
  assert.equal(h.messages.at(-1).status, 'unavailable');
  assert.equal(h.messages.at(-1).reason, 'not-found-in-scope');

  // HTTP 409 -> error / task-revision-mismatch & workspace-unverified -> request-rejected
  detailHandler = async () => ({ ok: false, status: 409, json: async () => ({ error: 'Rejected', reason: 'task-revision-mismatch' }) });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'e2' });
  assert.equal(h.messages.at(-1).status, 'error');
  assert.equal(h.messages.at(-1).reason, 'task-revision-mismatch');

  detailHandler = async () => ({ ok: false, status: 409, json: async () => ({ error: 'Rejected', reason: 'workspace-unverified' }) });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'e3' });
  assert.equal(h.messages.at(-1).status, 'error');
  assert.equal(h.messages.at(-1).reason, 'request-rejected');

  // HTTP 403 -> error / request-rejected
  detailHandler = async () => ({ ok: false, status: 403, json: async () => ({ error: 'Forbidden' }) });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'e4' });
  assert.equal(h.messages.at(-1).status, 'error');
  assert.equal(h.messages.at(-1).reason, 'request-rejected');

  // Network down -> unavailable / control-unavailable
  detailHandler = async () => { throw new TypeError('connect ECONNREFUSED'); };
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'e5' });
  assert.equal(h.messages.at(-1).status, 'unavailable');
  assert.equal(h.messages.at(-1).reason, 'control-unavailable');

  // Stale delayed response when Figma currentPage changes in-flight
  let releaseDelayed;
  detailHandler = () => new Promise((resolve) => {
    releaseDelayed = () => resolve({ ok: true, status: 200, json: async () => makeValidDto() });
  });
  const pendingDetail = h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'delayed-1' });
  await Promise.resolve();
  h.figma.currentPage = { id: '1:2', type: 'PAGE' };
  releaseDelayed();
  await pendingDetail;

  const delayedResult = h.messages.find((m) => m.type === 'workspace-history-detail-result' && m.requestId === 'delayed-1');
  assert.equal(delayedResult.status, 'scope-changed');
  assert.equal(delayedResult.reason, 'scope-changed');
  assert.equal(delayedResult.detail, null);

  const scopeChangedMsg = h.messages.filter((m) => m.type === 'workspace-scope-changed').at(-1);
  assert.ok(scopeChangedMsg);
  assert.equal(scopeChangedMsg.pageId, '1:2');
  assert.equal(scopeChangedMsg.journalHistory[0].operationId, OP_B);

  // currentpagechange event triggers proactive workspace-scope-changed
  await h.emitPageChange('1:3');
  const afterEvent = h.messages.filter((m) => m.type === 'workspace-scope-changed').at(-1);
  assert.equal(afterEvent.pageId, '1:3');

  // workspace-control-tick detects fileKey change even while UI still sends previous fileKey
  h.figma.fileKey = 'fileB';
  await h.send({ type: 'workspace-control-tick', workspaceSession: list.workspaceSession, fileKey: 'fileA' });
  const afterFileChange = h.messages.filter((m) => m.type === 'workspace-scope-changed').at(-1);
  assert.equal(afterFileChange.fileKey, 'fileB');
  assert.equal(afterFileChange.pageId, '1:3');

  // Delayed response arriving after task open / new Home session does NOT leak into new session
  let releaseForNewSession;
  detailHandler = () => new Promise((resolve) => {
    releaseForNewSession = () => resolve({ ok: true, status: 200, json: async () => makeValidDto({ scope: { fileKey: 'fileB', pageId: '1:3', runtimeGeneration: RUNTIME.generation }, operationId: OP_B }) });
  });
  const pendingOldSession = h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_B, taskKey: 'screen-a', revision: REV_A, requestId: 'old-sess-req' });
  await Promise.resolve();
  vm.runInContext('workspaceHome()', h.context);
  const countBeforeRelease = h.messages.length;
  releaseForNewSession();
  await pendingOldSession;
  assert.equal(h.messages.length, countBeforeRelease, 'stale reply for expired home session must be dropped silently');

  // Control disabled -> unavailable / control-unavailable with zero fetch
  const hNoCtrl = createBridgeHarness({ controlConfig: null });
  const noCtrlList = await hNoCtrl.listing();
  await hNoCtrl.send({ type: 'workspace-history-detail', workspaceSession: noCtrlList.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'no-ctrl' });
  assert.equal(hNoCtrl.messages.at(-1).status, 'unavailable');
  assert.equal(hNoCtrl.messages.at(-1).reason, 'control-unavailable');

  // Timeout -> error / request-timeout
  const timers = new Map();
  let nextTimer = 0;
  const hTimeout = createBridgeHarness({
    setTimeout: (fn) => { const id = ++nextTimer; timers.set(id, fn); return id; },
    clearTimeout: (id) => timers.delete(id),
    fetch: async (url) => {
      const route = url.split('/control/')[1];
      if (route === 'history') return { ok: true, status: 200, json: async () => ({ journalHistory: [], inputFreshness: [] }) };
      if (route === 'history-detail') return new Promise(() => {});
      throw new Error('Unexpected route ' + route);
    },
  });
  const timeoutList = await hTimeout.listing();
  const pendingTimeout = hTimeout.send({ type: 'workspace-history-detail', workspaceSession: timeoutList.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'to-1' });
  await Promise.resolve();
  await Promise.resolve();
  for (const fn of timers.values()) fn();
  await pendingTimeout;
  assert.equal(hTimeout.messages.at(-1).status, 'error');
  assert.equal(hTimeout.messages.at(-1).reason, 'request-timeout');

  // Click arriving after page changed before tick/event -> immediate scope-changed without querying detail endpoint
  let staleClickDetailCalled = false;
  const hStaleClick = createBridgeHarness({
    fetch: async (url) => {
      const route = url.split('/control/')[1];
      if (route === 'history') return { ok: true, status: 200, json: async () => ({ journalHistory: [], inputFreshness: [] }) };
      if (route === 'history-detail') {
        staleClickDetailCalled = true;
        return { ok: true, status: 200, json: async () => makeValidDto() };
      }
      throw new Error('Unexpected route ' + route);
    },
  });
  const staleList = await hStaleClick.listing();
  hStaleClick.figma.currentPage = { id: '1:4', type: 'PAGE' };
  await hStaleClick.send({ type: 'workspace-history-detail', workspaceSession: staleList.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'stale-click' });
  assert.equal(staleClickDetailCalled, false);
  const staleClickRes = hStaleClick.messages.find((m) => m.type === 'workspace-history-detail-result' && m.requestId === 'stale-click');
  assert.equal(staleClickRes.status, 'scope-changed');
  assert.equal(staleClickRes.detail, null);
  assert.equal(hStaleClick.messages.filter((m) => m.type === 'workspace-scope-changed').at(-1).pageId, '1:4');
});

test('workspace_control emits fileKey, pageId, and runtimeGeneration in workspace-control-state', async () => {
  const h = createBridgeHarness({
    fetch: async (url) => {
      const route = url.split('/control/')[1];
      if (route === 'history') return { ok: true, status: 200, json: async () => ({ journalHistory: [], inputFreshness: [] }) };
      if (route === 'poll') return { ok: true, status: 200, json: async () => ({ operation: null }) };
      throw new Error('Unexpected route ' + route);
    },
  });
  await h.listing();
  vm.runInContext("controlState('finished', false)", h.context);
  const stateMsg = h.messages.filter((m) => m.type === 'workspace-control-state').at(-1);
  assert.equal(stateMsg.fileKey, 'fileA');
  assert.equal(stateMsg.pageId, '1:1');
  assert.equal(stateMsg.runtimeGeneration, RUNTIME.generation);
  assert.equal(JSON.stringify(stateMsg).includes(CONTROL_TOKEN), false);
});

test('end-to-end real loopback HTTP server with bridge runtime enforces auth, 200, 404, 409, and 256KiB cap', async () => {
  let mode = 'ok';
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      if (req.headers.authorization !== 'Bearer ' + CONTROL_TOKEN) {
        res.writeHead(403, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Control authentication or endpoint rejected' }));
        return;
      }
      if (req.url === '/control/history') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          journalHistory: [{ taskKey: 'screen-a', revision: REV_A, operationId: OP_A, operation: 'apply', classification: 'recorded', phase: 'result-received', phases: [] }],
          inputFreshness: [],
        }));
        return;
      }
      if (req.url === '/control/history-detail') {
        const parsed = JSON.parse(body);
        assert.deepEqual(Object.keys(parsed).sort(), ['file_key', 'operation_id', 'page_id', 'revision', 'runtime', 'session_id', 'task_key']);
        if (mode === 'ok') {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(makeValidDto()));
        } else if (mode === '404') {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Control operation not found in this scope', reason: 'not-found-in-scope' }));
        } else if (mode === '409') {
          res.writeHead(409, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Control request rejected; inspect private operation status', reason: 'task-revision-mismatch' }));
        } else if (mode === 'oversized') {
          const big = makeValidDto({ diff: { status: 'available', reason: null, basis: 'revision-pair', beforeRevision: REV_A, afterRevision: REV_B, truncated: false, totalFields: 1, fields: [{ key: 'k', field: 'fontFamily', kind: 'changed', before: 'x'.repeat(265000), after: 'y' }], conflicts: [] } });
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(big));
        }
        return;
      }
      res.writeHead(403, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Forbidden' }));
    });
  });

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const h = createBridgeHarness({
      controlConfig: { url: `http://127.0.0.1:${port}`, token: CONTROL_TOKEN },
      fetch: globalThis.fetch,
    });
    const list = await h.listing();

    mode = 'ok';
    await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'http-1' });
    assert.equal(h.messages.at(-1).status, 'ok');
    assert.equal(h.messages.at(-1).detail.operationId, OP_A);

    mode = '404';
    await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_B, taskKey: 'screen-a', revision: REV_A, requestId: 'http-2' });
    assert.equal(h.messages.at(-1).status, 'unavailable');
    assert.equal(h.messages.at(-1).reason, 'not-found-in-scope');

    mode = '409';
    await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_B, taskKey: 'screen-a', revision: REV_A, requestId: 'http-3' });
    assert.equal(h.messages.at(-1).status, 'error');
    assert.equal(h.messages.at(-1).reason, 'task-revision-mismatch');

    mode = 'oversized';
    await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'http-4' });
    assert.equal(h.messages.at(-1).status, 'error');
    assert.equal(h.messages.at(-1).reason, 'payload-limit-exceeded');
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('host preserves bidirectional recovery-of (recovers + recovered-by) and declared-dependency directions without guessing', async () => {
  let nextDto;
  const h = createBridgeHarness({
    fetch: async (url) => {
      const route = url.split('/control/')[1];
      if (route === 'history') return { ok: true, status: 200, json: async () => ({ journalHistory: [], inputFreshness: [] }) };
      if (route === 'history-detail') return { ok: true, status: 200, json: async () => nextDto };
      throw new Error('Unexpected route ' + route);
    },
  });
  const list = await h.listing();

  // 1. Bidirectional recovery-of ('recovers' and 'recovered-by') and declared-dependency ('predecessor' and 'successor')
  nextDto = makeValidDto({
    relations: [
      {
        type: 'recovery-of',
        direction: 'recovers',
        operationId: OP_B,
        taskKey: 'screen-a',
        revision: REV_A,
        revisionBinding: 'pinned-historical',
      },
      {
        type: 'recovery-of',
        direction: 'recovered-by',
        operationId: OP_C,
        taskKey: 'screen-a',
        revision: REV_A,
        revisionBinding: 'current',
      },
      {
        type: 'declared-dependency',
        direction: 'predecessor',
        taskKey: 'tokens',
        revision: REV_C,
        currentRevision: REV_C,
        revisionBinding: 'current',
        artifact: 'code.js',
        artifactSha256: REV_D,
        targetOperationId: OP_B,
      },
      {
        type: 'declared-dependency',
        direction: 'successor',
        taskKey: 'cards',
        revision: REV_D,
        currentRevision: REV_D,
        revisionBinding: 'current',
        artifact: 'ui.html',
        artifactSha256: REV_C,
        targetOperationId: OP_C,
      },
    ],
  });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'dir-both' });
  const bothRes = h.messages.at(-1);
  assert.equal(bothRes.status, 'ok');
  assert.equal(bothRes.reason, null);
  assert.equal(bothRes.detail.classification, 'recorded');
  assert.equal(bothRes.detail.scopeNotice, 'read-only-exact-scope');
  const recoveries = bothRes.detail.relations.filter((r) => r.type === 'recovery-of');
  assert.deepEqual(
    JSON.parse(JSON.stringify(recoveries.map((r) => ({ direction: r.direction, operationId: r.operationId })))),
    [
      { direction: 'recovers', operationId: OP_B },
      { direction: 'recovered-by', operationId: OP_C },
    ],
  );
  const deps = bothRes.detail.relations.filter((r) => r.type === 'declared-dependency');
  assert.deepEqual(
    JSON.parse(JSON.stringify(deps.map((r) => ({ direction: r.direction, taskKey: r.taskKey, targetOperationId: r.targetOperationId })))),
    [
      { direction: 'predecessor', taskKey: 'tokens', targetOperationId: OP_B },
      { direction: 'successor', taskKey: 'cards', targetOperationId: OP_C },
    ],
  );

  // 2. Invalid or missing directions must never be guessed as 'recovers' or 'predecessor' -> dropped (no relation)
  nextDto = makeValidDto({
    relations: [
      { type: 'recovery-of', operationId: OP_B, taskKey: 'screen-a', revision: REV_A, revisionBinding: 'current' },
      { type: 'recovery-of', direction: '', operationId: OP_B, taskKey: 'screen-a', revision: REV_A, revisionBinding: 'current' },
      { type: 'recovery-of', direction: 'predecessor', operationId: OP_B, taskKey: 'screen-a', revision: REV_A, revisionBinding: 'current' },
      { type: 'recovery-of', direction: 'sideways', operationId: OP_C, taskKey: 'screen-a', revision: REV_A, revisionBinding: 'current' },
      { type: 'declared-dependency', taskKey: 'tokens', revision: REV_C, revisionBinding: 'current' },
      { type: 'declared-dependency', direction: '', taskKey: 'tokens', revision: REV_C, revisionBinding: 'current' },
      { type: 'declared-dependency', direction: 'recovers', taskKey: 'tokens', revision: REV_C, revisionBinding: 'current' },
      { type: 'declared-dependency', direction: 'upstream', taskKey: 'tokens', revision: REV_C, revisionBinding: 'current' },
    ],
  });
  await h.send({ type: 'workspace-history-detail', workspaceSession: list.workspaceSession, operationId: OP_A, taskKey: 'screen-a', revision: REV_A, requestId: 'dir-invalid' });
  const invalidRes = h.messages.at(-1);
  assert.equal(invalidRes.status, 'ok');
  assert.equal(invalidRes.reason, null);
  assert.equal(invalidRes.detail.relations.length, 0);
});
