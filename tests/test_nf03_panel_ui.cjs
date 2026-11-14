const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const { buildSync } = require(path.join(root, 'panel-ui/node_modules/esbuild'));

async function loadDetailModule() {
  return import(pathToFileURL(path.join(root, 'panel-ui/src/operationDetail.mjs')).href);
}

test('operationDetail normalizes contract v1 DTO, preserves canonical phases, caps diff, and redacts text', async () => {
  const mod = await loadDetailModule();
  const revA = 'a'.repeat(64);
  const revB = 'b'.repeat(64);
  const revC = 'c'.repeat(64);
  const revD = 'd'.repeat(64);
  const revE = 'e'.repeat(64);
  const opId = '1'.repeat(32);
  const depOpId = '2'.repeat(32);
  const recOpId = '3'.repeat(32);

  const tasks = [
    { key: 'screen-a', title: 'Screen A', revision: revB, project: 'App' },
    { key: 'tokens', title: 'Tokens', revision: revC, project: 'App' },
  ];
  const scope = mod.buildDetailScope(
    {
      fileKey: 'file-1',
      pageId: '1:2',
      runtime: { version: '25.0.0', implementation: revD, generation: 'f'.repeat(32) },
    },
    'sess-1',
  );

  const manyFields = Array.from({ length: 205 }, (_, i) => ({
    key: `node-${i}`,
    field: 'fontSize',
    kind: 'changed',
    before: 14,
    after: 16 + i,
  }));
  manyFields[0] = {
    key: 'hero.copy',
    field: 'characters',
    kind: 'changed',
    before: { valueType: 'text', changed: true, length: 14 },
    after: { valueType: 'text', changed: true, length: 21 },
  };
  manyFields[1] = {
    key: 'color.surface.primary',
    field: 'value',
    kind: 'changed',
    before: '#ffffff',
    after: '#f5f7fa',
  };
  manyFields[2] = {
    key: 'chip.fill',
    field: 'backgroundColor',
    kind: 'changed',
    before: { r: 1, g: 1, b: 1, a: 1 },
    after: { r: 0.9, g: 0.92, b: 0.95, a: 1 },
  };
  manyFields[3] = {
    key: 'secret.leak',
    field: 'characters',
    kind: 'changed',
    before: 'Secret customer name',
    after: 'Updated /Users/alice/private?token=abc123',
  };

  const result = mod.normalizeDetailResult(
    {
      type: mod.DETAIL_PROTOCOL.resultType,
      workspaceSession: 'sess-1',
      operationId: opId,
      taskKey: 'screen-a',
      revision: revA,
      requestId: 'detail-1',
      status: 'ok',
      reason: null,
      detail: {
        schema: mod.OPERATION_DETAIL_SCHEMA,
        readOnly: true,
        operationId: opId,
        scope: {
          fileKey: 'file-1',
          pageId: '1:2',
          runtimeGeneration: 'f'.repeat(32),
        },
        operation: 'apply',
        state: 'error',
        classification: 'recorded',
        phase: 'result-received',
        phases: [
          { phase: 'queued', time: '2026-11-14T10:00:02Z' },
          { phase: 'claimed', time: '2026-11-14T10:00:01Z' },
          { phase: 'native-started', time: '2026-11-14T10:00:03Z' },
          { phase: 'result-received', time: '2026-11-14T10:00:04Z' },
        ],
        task: {
          key: 'screen-a',
          revision: revA,
          currentRevision: revB,
          revisionBinding: 'pinned-historical',
          kind: 'sync',
        },
        failure: {
          code: 'native-conflict',
          action: 'inspect-conflicts',
        },
        relations: [
          {
            type: 'declared-dependency',
            direction: 'predecessor',
            taskKey: 'tokens',
            revision: revC,
            currentRevision: revC,
            revisionBinding: 'current',
            artifact: 'code.js',
            artifactSha256: revD,
            targetOperationId: depOpId,
          },
          {
            type: 'recovery-of',
            direction: 'recovers',
            operationId: recOpId,
            taskKey: 'screen-a',
            revision: revA,
            revisionBinding: 'pinned-historical',
          },
          {
            type: 'recovery-of',
            direction: 'recovered-by',
            operationId: depOpId,
            taskKey: 'screen-a',
            revision: revB,
            revisionBinding: 'current',
          },
          {
            type: 'recovery-of',
            direction: 'invalid-dir',
            operationId: depOpId,
            taskKey: 'screen-a',
            revision: revA,
            revisionBinding: 'pinned-historical',
          },
          {
            type: 'declared-dependency',
            taskKey: 'missing-dir',
            revision: revA,
            revisionBinding: 'current',
          },
          {
            type: 'artifact-input',
            artifact: 'input-record.json',
            artifactSha256: revE,
            revision: revA,
            revisionBinding: 'pinned-historical',
            freshness: 'stale',
          },
          {
            type: 'invented-causal',
            taskKey: 'tokens',
            revision: revA,
          },
        ],
        diff: {
          status: 'available',
          reason: null,
          basis: 'pinned-plan',
          beforeRevision: null,
          afterRevision: revA,
          truncated: false,
          totalFields: 205,
          fields: manyFields,
          conflicts: [
            {
              key: 'hero.copy',
              scope: 'node',
              field: 'characters',
              reasonCode: 'native-text-mismatch',
              planSha256: revD,
              expectedBefore: { valueType: 'text', changed: false, length: 14 },
              plannedAfter: { valueType: 'text', changed: true, length: 21 },
              observed: 'Private observed copy',
            },
          ],
        },
        truncated: false,
        scopeNotice: 'read-only-exact-scope',
      },
    },
    scope,
    tasks,
    [],
  );

  assert.equal(result.status, 'ok');
  const detail = result.detail;
  assert.equal(detail.classification, 'recorded');
  assert.equal(detail.task.revisionBinding, 'pinned-historical');
  assert.equal(detail.task.currentRevision, revB);
  assert.deepEqual(detail.failure, { code: 'native-conflict', action: 'inspect-conflicts' });
  // Preserves exact canonical server phase order even when timestamps are out of order.
  assert.deepEqual(detail.phases.map((p) => p.phase), [
    'queued',
    'claimed',
    'native-started',
    'result-received',
  ]);
  // Invalid relation types AND missing/invalid directions on dependency/recovery edges are discarded; canonical directions stay intact.
  assert.equal(detail.relations.length, 4);
  assert.equal(detail.relations[0].direction, 'predecessor');
  assert.equal(detail.relations[0].linkedOperationId, depOpId);
  assert.equal(detail.relations[1].direction, 'recovers');
  assert.equal(detail.relations[1].linkedOperationId, recOpId);
  assert.equal(detail.relations[2].direction, 'recovered-by');
  assert.equal(detail.relations[2].linkedOperationId, depOpId);
  assert.equal(detail.relations[3].type, 'artifact-input');
  assert.equal(detail.relations[3].linkedOperationId, null);
  // Bounded diff and redaction checks.
  assert.equal(detail.diff.fields.length, 200);
  assert.equal(detail.diff.totalFields, 205);
  assert.equal(detail.diff.truncated, true);
  assert.equal(detail.truncated, true);
  assert.equal(detail.diff.fields[0].isText, true);
  assert.equal(detail.diff.fields[0].textLengthBefore, 14);
  assert.equal(detail.diff.fields[0].textLengthAfter, 21);
  assert.equal(detail.diff.fields[1].isText, false);
  assert.equal(detail.diff.fields[1].before, '#ffffff');
  assert.equal(detail.diff.fields[1].after, '#f5f7fa');
  assert.equal(detail.diff.fields[2].before, 'rgba(1, 1, 1, 1)');
  assert.equal(detail.diff.conflicts.length, 1);
  assert.deepEqual(detail.diff.conflicts[0].expectedBefore, { isText: true, length: 14 });
  assert.deepEqual(detail.diff.conflicts[0].observed, { isText: true, length: 21 });
  assert.ok(!JSON.stringify(detail).includes('Secret customer name'));
  assert.ok(!JSON.stringify(detail).includes('Private observed copy'));
  assert.ok(!JSON.stringify(detail).includes('abc123'));
  assert.ok(!JSON.stringify(detail).includes('/Users/alice'));
});

test('operationDetail keeps legacy and unknown records free of invented phases, relations, or diffs', async () => {
  const mod = await loadDetailModule();
  const rev = 'a'.repeat(64);
  const scope = mod.buildDetailScope({ fileKey: 'file-1', pageId: '1:2', runtimeGeneration: 'f'.repeat(32) }, 'sess-1');

  const legacy = mod.normalizeDetailDto(
    {
      schema: mod.OPERATION_DETAIL_SCHEMA,
      operationId: '3'.repeat(32),
      task: { key: 'screen-a', revision: rev },
      classification: 'legacy',
      phase: 'native-started',
      phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
      relations: [{ type: 'declared-dependency', taskKey: 'tokens', revision: rev }],
      diff: { status: 'available', fields: [{ key: 'k', field: 'width', kind: 'changed', before: 10, after: 20 }] },
    },
    scope,
  );
  assert.equal(legacy.classification, 'legacy');
  assert.equal(legacy.phase, 'unknown');
  assert.deepEqual(legacy.phases, []);
  assert.deepEqual(legacy.relations, []);
  assert.equal(legacy.diff.status, 'unavailable');
  assert.equal(legacy.diff.reason, 'legacy-record');
  assert.deepEqual(legacy.diff.fields, []);

  const unknown = mod.normalizeDetailDto(
    {
      schema: 'unexpected-schema',
      classification: 'recorded',
      phases: [{ phase: 'native-started', time: '2026-11-14T10:00:00Z' }],
      relations: [{ type: 'recovery-of', operationId: '4'.repeat(32), taskKey: 'screen-a', revision: rev }],
    },
    scope,
  );
  assert.equal(unknown.classification, 'unknown');
  assert.equal(unknown.phase, 'unknown');
  assert.deepEqual(unknown.phases, []);
  assert.deepEqual(unknown.relations, []);
  assert.equal(unknown.diff.status, 'unavailable');
  assert.equal(unknown.diff.reason, 'unknown-record');
});

test('operationDetail rejects stale or mismatched responses fail-closed including taskKey and revision pin', async () => {
  const mod = await loadDetailModule();
  const revA = 'a'.repeat(64);
  const revB = 'b'.repeat(64);
  const opId = '1'.repeat(32);
  const genA = 'f'.repeat(32);
  const genB = 'e'.repeat(32);
  const scopeA = mod.buildDetailScope(
    { fileKey: 'file-1', pageId: '1:2', runtime: { version: '25.0.0', implementation: revA, generation: genA } },
    'sess-1',
  );
  const scopePageB = mod.buildDetailScope({ fileKey: 'file-1', pageId: '1:9', runtimeGeneration: genA }, 'sess-1');
  const scopeRuntimeB = mod.buildDetailScope({ fileKey: 'file-1', pageId: '1:2', runtimeGeneration: genB }, 'sess-1');

  const pending = {
    requestId: 'detail-1',
    operationId: opId,
    taskKey: 'screen-a',
    revision: revA,
    scope: scopeA,
  };

  const makeValidResult = (overrides = {}, detailOverrides = {}) => ({
    type: mod.DETAIL_PROTOCOL.resultType,
    workspaceSession: 'sess-1',
    operationId: opId,
    taskKey: 'screen-a',
    revision: revA,
    requestId: 'detail-1',
    status: 'ok',
    reason: null,
    ...overrides,
    detail:
      overrides.status && overrides.status !== 'ok'
        ? null
        : {
            schema: mod.OPERATION_DETAIL_SCHEMA,
            operationId: opId,
            scope: { fileKey: 'file-1', pageId: '1:2', runtimeGeneration: genA },
            classification: 'recorded',
            task: { key: 'screen-a', revision: revA },
            ...detailOverrides,
          },
  });

  assert.equal(mod.isDetailResponseStale(pending, makeValidResult(), scopeA), false);
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult({ status: 'unavailable', reason: 'not-found-in-scope' }), scopeA), false);
  // Session, requestId, page/file/runtime scope, and schema mismatches fail closed.
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult({ workspaceSession: '' }), scopeA), true);
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult({ requestId: 'detail-0' }), scopeA), true);
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult(), scopePageB), true);
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult(), scopeRuntimeB), true);
  assert.equal(
    mod.isDetailResponseStale(pending, makeValidResult({}, { scope: { fileKey: 'file-1' } }), scopeA),
    true,
  );
  assert.equal(
    mod.isDetailResponseStale(pending, makeValidResult({}, { scope: { fileKey: 'file-1', pageId: '1:9', runtimeGeneration: genA } }), scopeA),
    true,
  );
  assert.equal(
    mod.isDetailResponseStale(pending, makeValidResult({}, { scope: { fileKey: 'file-1', pageId: '1:2', runtimeGeneration: genB } }), scopeA),
    true,
  );
  // Clicked row taskKey / revision pin mismatch (envelope OR detail.task) MUST be rejected.
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult({ taskKey: 'other-task' }), scopeA), true);
  assert.equal(mod.isDetailResponseStale(pending, makeValidResult({ revision: revB }), scopeA), true);
  assert.equal(
    mod.isDetailResponseStale(pending, makeValidResult({}, { task: { key: 'other-task', revision: revA } }), scopeA),
    true,
  );
  assert.equal(
    mod.isDetailResponseStale(pending, makeValidResult({}, { task: { key: 'screen-a', revision: revB } }), scopeA),
    true,
  );
});

test('workspace.json NF-03 keys include all three locales and identical placeholders', () => {
  const catalog = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/workspace.json'), 'utf8'));
  const keys = Object.keys(catalog).filter((k) => k.startsWith('workspace.journal'));
  assert.ok(keys.length >= 45);
  for (const key of keys) {
    const entry = catalog[key];
    assert.deepEqual(Object.keys(entry).sort(), ['en', 'ja', 'ko'], key);
    for (const loc of ['ko', 'en', 'ja']) {
      assert.equal(typeof entry[loc], 'string', `${key}.${loc}`);
      assert.ok(entry[loc].trim().length > 0, `${key}.${loc} empty`);
    }
    const params = ['ko', 'en', 'ja'].map((loc) =>
      [...new Set((entry[loc].match(/\{(\w+)\}/g) || []))].sort(),
    );
    assert.deepEqual(params[1], params[0], `${key} en params`);
    assert.deepEqual(params[2], params[0], `${key} ja params`);
  }
});

function createInteractiveDomShim() {
  const winListeners = new Map();
  const docListeners = new Map();
  const scrollCalls = [];

  class NodeShim {
    constructor(tagName, ownerDocument) {
      this.tagName = String(tagName).toUpperCase();
      this.nodeName = this.tagName;
      this.nodeType = tagName === '#text' ? 3 : tagName === '#comment' ? 8 : 1;
      this.ownerDocument = ownerDocument;
      this.childNodes = [];
      this.parentNode = null;
      this.style = {};
      this.dataset = {};
      this.attributes = new Map();
      this.listeners = new Map();
      this._textContent = '';
      this._value = '';
      this.className = '';
      this.tabIndex = 0;
      this.disabled = false;
      this.selected = false;
      this.multiple = false;
    }
    get type() { return this.tagName === 'SELECT' ? (this.multiple ? 'select-multiple' : 'select-one') : this.getAttribute('type') || ''; }
    get options() {
      const out = [];
      const walk = (n) => {
        for (const c of n.childNodes) {
          if (c.tagName === 'OPTION') out.push(c);
          walk(c);
        }
      };
      walk(this);
      return out;
    }
    get firstChild() { return this.childNodes[0] || null; }
    get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
    get nextSibling() {
      if (!this.parentNode) return null;
      const i = this.parentNode.childNodes.indexOf(this);
      return i >= 0 ? this.parentNode.childNodes[i + 1] || null : null;
    }
    get textContent() {
      if (this.nodeType === 3) return this._textContent;
      return this.childNodes.length ? this.childNodes.map((c) => c.textContent).join('') : this._textContent;
    }
    set textContent(v) {
      this._textContent = String(v ?? '');
      this.childNodes = [];
    }
    get value() {
      if (this.tagName === 'SELECT') {
        const opts = this.options;
        const sel = opts.find((o) => o.selected);
        if (sel) return sel.getAttribute('value') ?? sel.textContent;
        if (this._value) return this._value;
        return opts[0] ? (opts[0].getAttribute('value') ?? opts[0].textContent) : '';
      }
      return this._value;
    }
    set value(v) {
      const str = String(v ?? '');
      this._value = str;
      if (this.tagName === 'SELECT') {
        for (const opt of this.options) {
          opt.selected = (opt.getAttribute('value') ?? opt.textContent) === str;
        }
      }
    }
    appendChild(child) {
      if (child.parentNode) child.parentNode.removeChild(child);
      child.parentNode = this;
      this.childNodes.push(child);
      return child;
    }
    insertBefore(child, before) {
      if (!before) return this.appendChild(child);
      if (child.parentNode) child.parentNode.removeChild(child);
      const idx = this.childNodes.indexOf(before);
      if (idx < 0) return this.appendChild(child);
      child.parentNode = this;
      this.childNodes.splice(idx, 0, child);
      return child;
    }
    removeChild(child) {
      const idx = this.childNodes.indexOf(child);
      if (idx >= 0) this.childNodes.splice(idx, 1);
      child.parentNode = null;
      return child;
    }
    contains(node) {
      let cur = node;
      while (cur) {
        if (cur === this) return true;
        cur = cur.parentNode;
      }
      return false;
    }
    setAttribute(name, val) {
      const str = String(val);
      this.attributes.set(name, str);
      if (name === 'class') this.className = str;
      if (name === 'tabindex') this.tabIndex = Number(str);
      if (name === 'value') this._value = str;
      if (name === 'disabled') this.disabled = true;
    }
    removeAttribute(name) {
      this.attributes.delete(name);
      if (name === 'disabled') this.disabled = false;
    }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    hasAttribute(name) { return this.attributes.has(name); }
    addEventListener(type, fn) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type).add(fn);
    }
    removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
    dispatchEvent(evt) {
      const eventObj = {
        target: evt.target || this,
        currentTarget: this,
        bubbles: true,
        cancelBubble: false,
        preventDefault() {},
        stopPropagation() { this.cancelBubble = true; },
        ...evt,
      };
      for (const fn of [...(this.listeners.get(eventObj.type) || [])]) fn(eventObj);
      if (eventObj.bubbles && !eventObj.cancelBubble) {
        if (this.parentNode) this.parentNode.dispatchEvent(eventObj);
        else this.ownerDocument.dispatchEvent(eventObj);
      }
      return true;
    }
    focus() { this.ownerDocument.activeElement = this; }
    click() { this.dispatchEvent({ type: 'click', bubbles: true }); }
  }

  const doc = {
    nodeType: 9,
    activeElement: null,
    documentElement: null,
    defaultView: null,
    createElement(tag) { return new NodeShim(tag, this); },
    createElementNS(_ns, tag) { return new NodeShim(tag, this); },
    createTextNode(text) {
      const n = new NodeShim('#text', this);
      n._textContent = String(text ?? '');
      return n;
    },
    createComment(text) {
      const n = new NodeShim('#comment', this);
      n._textContent = String(text ?? '');
      return n;
    },
    addEventListener(type, fn) {
      if (!docListeners.has(type)) docListeners.set(type, new Set());
      docListeners.get(type).add(fn);
    },
    removeEventListener(type, fn) { docListeners.get(type)?.delete(fn); },
    dispatchEvent(eventObj) {
      for (const fn of [...(docListeners.get(eventObj.type) || [])]) {
        fn({ ...eventObj, currentTarget: doc });
      }
      return true;
    },
  };
  doc.documentElement = doc.createElement('html');

  const win = {
    scrollY: 0,
    event: undefined,
    scrollTo(x, y) {
      this.scrollY = y;
      scrollCalls.push({ x, y });
    },
    addEventListener(type, fn) {
      if (!winListeners.has(type)) winListeners.set(type, new Set());
      winListeners.get(type).add(fn);
    },
    removeEventListener(type, fn) { winListeners.get(type)?.delete(fn); },
    dispatchEvent(evt) {
      for (const fn of [...(winListeners.get(evt.type) || [])]) fn(evt);
    },
    setInterval() { return 1; },
    clearInterval() {},
  };
  doc.defaultView = win;

  function findAll(node, pred, out = []) {
    if (pred(node)) out.push(node);
    for (const child of node.childNodes || []) findAll(child, pred, out);
    return out;
  }

  return { doc, win, NodeShim, findAll, scrollCalls, getActive: () => doc.activeElement };
}

test('Workspace interactive History detail opens read-only, navigates causal links with back-stack, restores filter/scroll/focus, and clears on scope-changed', async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ff-nf03-panel-'));
  const entryPath = path.join(tmpDir, 'entry.jsx');
  const outPath = path.join(tmpDir, 'bundle.cjs');
  fs.writeFileSync(
    entryPath,
    `
    export * as React from 'react';
    export { createRoot } from 'react-dom/client';
    export { flushSync } from 'react-dom';
    export { default as Workspace } from ${JSON.stringify(path.join(root, 'panel-ui/src/Workspace.jsx'))};
    export { Shell, PanelContext } from ${JSON.stringify(path.join(root, 'panel-ui/src/components.jsx'))};
    `,
  );
  buildSync({
    entryPoints: [entryPath],
    outfile: outPath,
    bundle: true,
    platform: 'node',
    format: 'cjs',
    define: {
      __FLOW_DISPLAY_NAME__: '"Figma Flow"',
      __FLOW_LOCALES__: '["ko","en","ja"]',
    },
    nodePaths: [path.join(root, 'panel-ui/node_modules')],
  });

  const prevWin = globalThis.window;
  const prevDoc = globalThis.document;
  const prevNav = globalThis.navigator;
  const prevHTMLEl = globalThis.HTMLElement;
  const prevSVGEl = globalThis.SVGElement;
  const prevIframe = globalThis.HTMLIFrameElement;

  const { doc, win, NodeShim, findAll, scrollCalls, getActive } = createInteractiveDomShim();
  globalThis.HTMLElement = NodeShim;
  globalThis.SVGElement = NodeShim;
  globalThis.HTMLIFrameElement = class HTMLIFrameElement {};
  win.HTMLIFrameElement = globalThis.HTMLIFrameElement;
  win.HTMLElement = NodeShim;
  win.SVGElement = NodeShim;
  globalThis.window = win;
  globalThis.document = doc;
  if (!globalThis.navigator) Object.defineProperty(globalThis, 'navigator', { value: { language: 'en' }, configurable: true });

  try {
    const { React, createRoot, flushSync, Workspace, Shell, PanelContext } = require(outPath);

    const workspaceCatalog = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/workspace.json'), 'utf8'));
    const commonCatalog = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/common.json'), 'utf8'));
    const catalog = { ...workspaceCatalog, ...commonCatalog };
    const t = (key, params = {}) => {
      let text = catalog[key]?.en || key;
      for (const [k, v] of Object.entries(params)) text = text.replace(`{${k}}`, String(v));
      return text;
    };

    const opA = '1'.repeat(32);
    const opB = '2'.repeat(32);
    const revA = 'a'.repeat(64);
    const revB = 'b'.repeat(64);
    const revC = 'c'.repeat(64);
    const sent = [];

    const flushEffects = () => new Promise((resolve) => setTimeout(resolve, 15));

    const container = doc.createElement('div');
    const reactRoot = createRoot(container, { onUncaughtError(err) { throw err; } });
    flushSync(() => {
      reactRoot.render(
        React.createElement(
          PanelContext.Provider,
          { value: { locale: 'en', t, setLocale() {}, hostBusy: false } },
          React.createElement(Workspace, { model: {}, locale: 'en', t, send: (m) => sent.push(m), Shell }),
        ),
      );
    });
    await flushEffects();

    const deliver = async (pluginMessage) => {
      flushSync(() => {
        win.dispatchEvent({ type: 'message', data: { pluginMessage } });
      });
      await flushEffects();
    };

    // Host loads workspace-tasks on History tab with two projects.
    await deliver({
      type: 'workspace-tasks',
      workspaceSession: 'sess-live',
      fileKey: 'file-a',
      pageId: '1:2',
      view: 'history',
      project: 'Beta',
      controlEnabled: true,
      tasks: [
        { key: 'screen-a', title: 'Screen Alpha', project: 'Alpha', kind: 'sync', revision: revB },
        { key: 'tokens', title: 'Tokens', project: 'Alpha', kind: 'import', revision: revC },
        { key: 'other-proj', title: 'Other Project Task', project: 'Beta', kind: 'sync', revision: revA },
      ],
      history: [
        { taskKey: 'screen-a', revision: revA, operation: 'apply', status: 'finished', executionId: 'ui-exec-1', time: '2026-11-14T10:00:00Z' },
      ],
      journalHistory: [
        {
          operationId: opA,
          taskKey: 'screen-a',
          revision: revA,
          operation: 'apply',
          classification: 'recorded',
          phase: 'result-received',
          phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
        },
        {
          taskKey: 'other-proj',
          revision: revA,
          operation: 'apply',
          classification: 'legacy',
          phase: 'unknown',
          phases: [],
        },
      ],
    });

    const setSelectValue = async (selectEl, val) => {
      const desc = Object.getOwnPropertyDescriptor(NodeShim.prototype, 'value');
      desc.set.call(selectEl, val);
      flushSync(() => {
        selectEl.dispatchEvent({ type: 'change', bubbles: true, target: selectEl });
      });
      await flushEffects();
    };

    // Switch project filter to Alpha and task filter to screen-a, then scroll down.
    const projectSelect = findAll(
      container,
      (n) => n.tagName === 'SELECT' && n.getAttribute('aria-label') === 'Project',
    )[0];
    assert.ok(projectSelect);
    await setSelectValue(projectSelect, 'Alpha');
    const taskSelect = findAll(container, (n) => n.tagName === 'SELECT').at(-1);
    assert.ok(taskSelect);
    await setSelectValue(taskSelect, 'screen-a');
    win.scrollY = 420;

    // Click "View details" button for opA.
    const detailBtn = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-detail-btn'))[0];
    assert.ok(detailBtn);
    flushSync(() => {
      detailBtn.click();
    });
    await flushEffects();

    // Request matches exact nf03-contract.md Section 3.1 (read-only).
    const detailReqs = sent.filter((m) => m.type === 'workspace-history-detail');
    assert.equal(detailReqs.length, 1);
    assert.deepEqual(detailReqs[0], {
      type: 'workspace-history-detail',
      workspaceSession: 'sess-live',
      operationId: opA,
      taskKey: 'screen-a',
      revision: revA,
      requestId: 'detail-1',
    });
    assert.equal(sent.some((m) => ['workspace-open', 'workspace-chat-open'].includes(m.type)), false);

    // Focus moves to the detail <h2> heading.
    const detailHeading = findAll(container, (n) => n.tagName === 'H2' && n.parentNode?.className?.includes('workspace-detail-header'))[0];
    assert.equal(getActive(), detailHeading);

    // A forged response whose taskKey mismatches the clicked row MUST be ignored!
    await deliver({
      type: 'workspace-history-detail-result',
      workspaceSession: 'sess-live',
      operationId: opA,
      taskKey: 'screen-a',
      revision: revA,
      requestId: 'detail-1',
      status: 'ok',
      reason: null,
      detail: {
        schema: 'figma-flow-operation-detail-v1',
        readOnly: true,
        operationId: opA,
        scope: { fileKey: 'file-a', pageId: '1:2', runtimeGeneration: 'f'.repeat(32) },
        classification: 'recorded',
        phase: 'result-received',
        phases: [],
        task: { key: 'forged-task', revision: revA, revisionBinding: 'pinned-historical' },
        relations: [],
        diff: { status: 'empty', fields: [], conflicts: [] },
      },
    });
    assert.ok(container.textContent.includes('Loading details'));

    // Valid contract v1 response renders detail with non-color badges, redacted text length, and linked operation button.
    await deliver({
      type: 'workspace-history-detail-result',
      workspaceSession: 'sess-live',
      operationId: opA,
      taskKey: 'screen-a',
      revision: revA,
      requestId: 'detail-1',
      status: 'ok',
      reason: null,
      detail: {
        schema: 'figma-flow-operation-detail-v1',
        readOnly: true,
        operationId: opA,
        scope: { fileKey: 'file-a', pageId: '1:2', runtimeGeneration: 'f'.repeat(32) },
        operation: 'apply',
        state: 'error',
        classification: 'recorded',
        phase: 'result-received',
        phases: [
          { phase: 'queued', time: '2026-11-14T10:00:00Z' },
          { phase: 'claimed', time: '2026-11-14T09:59:59Z' },
        ],
        task: {
          key: 'screen-a',
          revision: revA,
          currentRevision: revB,
          revisionBinding: 'pinned-historical',
          kind: 'sync',
        },
        failure: { code: 'native-conflict', action: 'inspect-conflicts' },
        relations: [
          {
            type: 'declared-dependency',
            direction: 'predecessor',
            taskKey: 'tokens',
            revision: revC,
            currentRevision: revC,
            revisionBinding: 'current',
            targetOperationId: opB,
          },
        ],
        diff: {
          status: 'available',
          basis: 'pinned-plan',
          totalFields: 2,
          fields: [
            { key: 'btn.bg', field: 'backgroundColor', kind: 'changed', before: '#ffffff', after: '#111111' },
            {
              key: 'hero.copy',
              field: 'characters',
              kind: 'changed',
              before: { valueType: 'text', changed: true, length: 9 },
              after: { valueType: 'text', changed: true, length: 12 },
            },
          ],
          conflicts: [],
        },
        truncated: false,
        scopeNotice: 'read-only-exact-scope',
      },
    });

    assert.ok(container.textContent.includes('Pinned past revision'));
    assert.ok(container.textContent.includes('Native conflict detected'));
    assert.ok(container.textContent.includes('#111111'));
    assert.ok(container.textContent.includes('Text length (raw text hidden) (12)'));
    assert.ok(container.textContent.includes('Changed'));
    assert.ok(container.textContent.includes('~'));

    // Click causal predecessor link -> pushes detail onto back-stack and opens opB detail.
    const linkBtn = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-recovery-link'))[0];
    assert.ok(linkBtn);
    flushSync(() => {
      linkBtn.click();
    });
    await flushEffects();
    assert.equal(sent.filter((m) => m.type === 'workspace-history-detail').length, 2);
    assert.equal(sent.at(-1).operationId, opB);
    assert.equal(sent.at(-1).taskKey, 'tokens');
    assert.equal(sent.at(-1).revision, revC);

    await deliver({
      type: 'workspace-history-detail-result',
      workspaceSession: 'sess-live',
      operationId: opB,
      taskKey: 'tokens',
      revision: revC,
      requestId: 'detail-2',
      status: 'ok',
      reason: null,
      detail: {
        schema: 'figma-flow-operation-detail-v1',
        readOnly: true,
        operationId: opB,
        scope: { fileKey: 'file-a', pageId: '1:2', runtimeGeneration: 'f'.repeat(32) },
        operation: 'import',
        state: 'ok',
        classification: 'recorded',
        phase: 'reconciled',
        phases: [],
        task: { key: 'tokens', revision: revC, currentRevision: revC, revisionBinding: 'current', kind: 'import' },
        relations: [],
        diff: { status: 'empty', fields: [], conflicts: [] },
      },
    });
    assert.ok(container.textContent.includes('No recorded changes in allowed design fields'));

    // First Back (via Escape key) pops back-stack to opA detail!
    flushSync(() => {
      win.dispatchEvent({ type: 'keydown', key: 'Escape', preventDefault() {} });
    });
    await flushEffects();
    assert.ok(container.textContent.includes(opA));

    // Second Back button returns to History list, restores filters + scrollY + calling button focus.
    const backBtn = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-back'))[0];
    flushSync(() => {
      backBtn.click();
    });
    await flushEffects();
    const projectSelectAfter = findAll(
      container,
      (n) => n.tagName === 'SELECT' && n.getAttribute('aria-label') === 'Project',
    )[0];
    const taskSelectAfter = findAll(container, (n) => n.tagName === 'SELECT').at(-1);
    assert.equal(projectSelectAfter.value, 'Alpha');
    assert.equal(taskSelectAfter.value, 'screen-a');
    assert.equal(scrollCalls.at(-1).y, 420);
    const restoredTrigger = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-detail-btn'))[0];
    assert.equal(getActive(), restoredTrigger);

    // Re-open detail and receive workspace-scope-changed -> immediately clears stale detail and shows notice.
    flushSync(() => {
      restoredTrigger.click();
    });
    await flushEffects();
    await deliver({
      type: 'workspace-scope-changed',
      workspaceSession: 'sess-live',
      fileKey: 'file-a',
      pageId: '1:99',
      journalHistory: [],
      journalUnavailable: false,
      inputFreshness: [],
    });
    assert.ok(container.textContent.includes('scope changed'));
    assert.ok(!container.textContent.includes('#111111'));

    // Returning from scope-changed navigates back cleanly without restoring popped back-stack, then verifies unavailable, error, and legacy-without-opId.
    const backAfterScopeBtn = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-back'))[0];
    flushSync(() => {
      backAfterScopeBtn.click();
    });
    await flushEffects();

    // Deliver updated journalHistory with a legacy row lacking operationId + a recorded row that gets 404/unavailable & 409/mismatch.
    await deliver({
      type: 'workspace-scope-changed',
      workspaceSession: 'sess-live',
      fileKey: 'file-a',
      pageId: '1:99',
      journalUnavailable: false,
      inputFreshness: [],
      journalHistory: [
        {
          taskKey: 'screen-a',
          revision: revA,
          operation: 'apply',
          classification: 'legacy',
          phase: 'unknown',
          phases: [],
        },
        {
          operationId: opB,
          taskKey: 'screen-a',
          revision: revA,
          operation: 'apply',
          classification: 'recorded',
          phase: 'result-received',
          phases: [],
        },
      ],
    });
    await setSelectValue(
      findAll(container, (n) => n.tagName === 'SELECT').at(-1),
      '',
    );
    const detailBtnsScope2 = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-detail-btn'));
    assert.equal(detailBtnsScope2.length, 2);

    // Click legacy row without operationId -> zero host request sent, legacy notice rendered cleanly.
    const countBeforeLegacy = sent.filter((m) => m.type === 'workspace-history-detail').length;
    flushSync(() => {
      detailBtnsScope2[1].click();
    });
    await flushEffects();
    assert.equal(sent.filter((m) => m.type === 'workspace-history-detail').length, countBeforeLegacy);
    assert.ok(container.textContent.includes('Legacy records do not include canonical phases or artifact diffs.'));

    flushSync(() => {
      findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-back'))[0].click();
    });
    await flushEffects();

    // Click opB -> test status: 'unavailable' (not-found-in-scope).
    flushSync(() => {
      findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-detail-btn'))[0].click();
    });
    await flushEffects();
    const lastReq = sent.filter((m) => m.type === 'workspace-history-detail').at(-1);
    await deliver({
      type: 'workspace-history-detail-result',
      workspaceSession: 'sess-live',
      operationId: opB,
      taskKey: 'screen-a',
      revision: revA,
      requestId: lastReq.requestId,
      status: 'unavailable',
      reason: 'not-found-in-scope',
      detail: null,
    });
    assert.ok(container.textContent.includes('This operation does not belong to the active file and page scope.'));

    flushSync(() => {
      findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-back'))[0].click();
    });
    await flushEffects();

    // Click opB -> test status: 'error' (task-revision-mismatch).
    flushSync(() => {
      findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-detail-btn'))[0].click();
    });
    await flushEffects();
    const mismatchReq = sent.filter((m) => m.type === 'workspace-history-detail').at(-1);
    await deliver({
      type: 'workspace-history-detail-result',
      workspaceSession: 'sess-live',
      operationId: opB,
      taskKey: 'screen-a',
      revision: revA,
      requestId: mismatchReq.requestId,
      status: 'error',
      reason: 'task-revision-mismatch',
      detail: null,
    });
    assert.ok(container.textContent.includes('The selected row task key or revision does not match the recorded operation.'));

    flushSync(() => {
      reactRoot.unmount();
    });
    await flushEffects();
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    globalThis.window = prevWin;
    globalThis.document = prevDoc;
    globalThis.HTMLElement = prevHTMLEl;
    globalThis.SVGElement = prevSVGEl;
    globalThis.HTMLIFrameElement = prevIframe;
    if (prevNav === undefined) delete globalThis.navigator;
    else Object.defineProperty(globalThis, 'navigator', { value: prevNav, configurable: true });
  }
});

test('Workspace recovery relation labels clearly distinguish recovers vs recovered-by in Korean and English with accessible button labels', async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ff-nf03-dir-'));
  const entryPath = path.join(tmpDir, 'entry.jsx');
  const outPath = path.join(tmpDir, 'bundle.cjs');
  fs.writeFileSync(
    entryPath,
    `
    export * as React from 'react';
    export { createRoot } from 'react-dom/client';
    export { flushSync } from 'react-dom';
    export { default as Workspace } from ${JSON.stringify(path.join(root, 'panel-ui/src/Workspace.jsx'))};
    export { Shell, PanelContext } from ${JSON.stringify(path.join(root, 'panel-ui/src/components.jsx'))};
    `,
  );
  buildSync({
    entryPoints: [entryPath],
    outfile: outPath,
    bundle: true,
    platform: 'node',
    format: 'cjs',
    define: { __FLOW_DISPLAY_NAME__: '"Figma Flow"', __FLOW_LOCALES__: '["ko","en","ja"]' },
    nodePaths: [path.join(root, 'panel-ui/node_modules')],
  });

  const prevWin = globalThis.window;
  const prevDoc = globalThis.document;
  const prevNav = globalThis.navigator;
  const prevHTMLEl = globalThis.HTMLElement;
  const prevSVGEl = globalThis.SVGElement;
  const prevIframe = globalThis.HTMLIFrameElement;

  const { doc, win, NodeShim, findAll } = createInteractiveDomShim();
  globalThis.HTMLElement = NodeShim;
  globalThis.SVGElement = NodeShim;
  globalThis.HTMLIFrameElement = class HTMLIFrameElement {};
  win.HTMLIFrameElement = globalThis.HTMLIFrameElement;
  win.HTMLElement = NodeShim;
  win.SVGElement = NodeShim;
  globalThis.window = win;
  globalThis.document = doc;
  if (!globalThis.navigator) Object.defineProperty(globalThis, 'navigator', { value: { language: 'ko' }, configurable: true });

  try {
    const { React, createRoot, flushSync, Workspace, Shell, PanelContext } = require(outPath);
    const workspaceCatalog = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/workspace.json'), 'utf8'));
    const commonCatalog = JSON.parse(fs.readFileSync(path.join(root, 'figma-bridge/locales/common.json'), 'utf8'));
    const catalog = { ...workspaceCatalog, ...commonCatalog };
    const flushEffects = () => new Promise((resolve) => setTimeout(resolve, 15));

    const opA = '1'.repeat(32);
    const opB = '2'.repeat(32);
    const opC = '3'.repeat(32);
    const revA = 'a'.repeat(64);
    const revB = 'b'.repeat(64);
    const revC = 'c'.repeat(64);

    for (const loc of ['ko', 'en']) {
      const sent = [];
      const t = (key, params = {}) => {
        let text = catalog[key]?.[loc] || key;
        for (const [k, v] of Object.entries(params)) text = text.replace(`{${k}}`, String(v));
        return text;
      };
      const container = doc.createElement('div');
      const reactRoot = createRoot(container, { onUncaughtError(err) { throw err; } });
      flushSync(() => {
        reactRoot.render(
          React.createElement(
            PanelContext.Provider,
            { value: { locale: loc, t, setLocale() {}, hostBusy: false } },
            React.createElement(Workspace, { model: {}, locale: loc, t, send: (m) => sent.push(m), Shell }),
          ),
        );
      });
      await flushEffects();

      flushSync(() => {
        win.dispatchEvent({
          type: 'message',
          data: {
            pluginMessage: {
              type: 'workspace-tasks',
              workspaceSession: 'sess-' + loc,
              fileKey: 'file-a',
              pageId: '1:2',
              view: 'history',
              locale: loc,
              tasks: [{ key: 'screen-a', title: 'Screen A', project: 'Alpha', kind: 'sync', revision: revB }],
              history: [],
              journalHistory: [
                {
                  operationId: opA,
                  taskKey: 'screen-a',
                  revision: revA,
                  operation: 'apply',
                  classification: 'recorded',
                  phase: 'result-received',
                  phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
                },
              ],
            },
          },
        });
      });
      await flushEffects();

      const btn = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-journal-detail-btn'))[0];
      flushSync(() => btn.click());
      await flushEffects();

      const req = sent.filter((m) => m.type === 'workspace-history-detail').at(-1);
      flushSync(() => {
        win.dispatchEvent({
          type: 'message',
          data: {
            pluginMessage: {
              type: 'workspace-history-detail-result',
              workspaceSession: 'sess-' + loc,
              operationId: opA,
              taskKey: 'screen-a',
              revision: revA,
              requestId: req.requestId,
              status: 'ok',
              reason: null,
              detail: {
                schema: 'figma-flow-operation-detail-v1',
                readOnly: true,
                operationId: opA,
                scope: { fileKey: 'file-a', pageId: '1:2', runtimeGeneration: 'f'.repeat(32) },
                operation: 'apply',
                state: 'ok',
                classification: 'recorded',
                phase: 'result-received',
                phases: [{ phase: 'queued', time: '2026-11-14T10:00:00Z' }],
                task: { key: 'screen-a', revision: revA, currentRevision: revB, revisionBinding: 'pinned-historical', kind: 'sync' },
                failure: null,
                relations: [
                  { type: 'recovery-of', direction: 'recovers', operationId: opB, taskKey: 'screen-a', revision: revA, revisionBinding: 'pinned-historical' },
                  { type: 'recovery-of', direction: 'recovered-by', operationId: opC, taskKey: 'screen-a', revision: revB, revisionBinding: 'current' },
                  { type: 'declared-dependency', direction: 'predecessor', taskKey: 'tokens', revision: revC, currentRevision: revC, revisionBinding: 'current', targetOperationId: opB },
                  { type: 'declared-dependency', direction: 'successor', taskKey: 'cards', revision: revB, currentRevision: revB, revisionBinding: 'current', targetOperationId: opC },
                ],
                diff: { status: 'empty', fields: [], conflicts: [] },
              },
            },
          },
        });
      });
      await flushEffects();

      const linkBtns = findAll(container, (n) => n.tagName === 'BUTTON' && n.className.includes('workspace-recovery-link'));
      assert.equal(linkBtns.length, 4);
      const arias = linkBtns.map((b) => b.getAttribute('aria-label'));
      if (loc === 'ko') {
        assert.ok(container.textContent.includes('이 실행이 복구한 이전 실행'));
        assert.ok(container.textContent.includes('이 실행을 복구한 이후 실행'));
        assert.ok(container.textContent.includes('선언된 선행 의존성'));
        assert.ok(container.textContent.includes('선언된 후행 의존 작업'));
        assert.ok(arias.some((a) => a.includes('이 실행이 복구한 이전 실행') && a.includes(opB)));
        assert.ok(arias.some((a) => a.includes('이 실행을 복구한 이후 실행') && a.includes(opC)));
      } else {
        assert.ok(container.textContent.includes('This operation recovers'));
        assert.ok(container.textContent.includes('Recovered by later operation'));
        assert.ok(container.textContent.includes('Declared predecessor dependency'));
        assert.ok(container.textContent.includes('Declared downstream dependent'));
        assert.ok(arias.some((a) => a.includes('This operation recovers') && a.includes(opB)));
        assert.ok(arias.some((a) => a.includes('Recovered by later operation') && a.includes(opC)));
      }

      flushSync(() => reactRoot.unmount());
      await flushEffects();
    }
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    globalThis.window = prevWin;
    globalThis.document = prevDoc;
    globalThis.HTMLElement = prevHTMLEl;
    globalThis.SVGElement = prevSVGEl;
    globalThis.HTMLIFrameElement = prevIframe;
    if (prevNav === undefined) delete globalThis.navigator;
    else Object.defineProperty(globalThis, 'navigator', { value: prevNav, configurable: true });
  }
});
