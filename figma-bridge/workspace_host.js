/* One local plugin entry. Registered task hosts retain their native scope guards. */
const workspaceKinds = new Set(['import', 'review', 'discover', 'sync', 'native-edit']);
const workspaceTasks = new Map();
for (const task of FLOW_TASKS) {
  if (!task || typeof task.key !== 'string' || !task.key || workspaceTasks.has(task.key) ||
      !workspaceKinds.has(task.kind) || typeof task.run !== 'function') {
    throw Error('Invalid or duplicate registered Figma Flow task');
  }
  workspaceTasks.set(task.key, task);
}
let workspaceActive = null;
let workspaceHomeSession = '';
let workspaceNotice = '';
const workspaceLocales = new Set(FLOW_LOCALES);
const workspaceOperations = new Set(['import', 'export', 'sync', 'draft-review', 'read', 'apply', 'verification', 'download', 'chat:queue', 'chat:open']);
const workspaceStatuses = new Set(['requested', 'running', 'finished', 'failed', 'readback', 'verified', 'baseline']);
const workspaceStorageKey = figma.fileKey ? 'figma-flow-workspace-v1:' + figma.fileKey : null;
let workspaceState = {locale: null, history: []};
let workspaceServerHistory = [], workspaceJournalUnavailable = false;
let workspaceInputFreshness = [];
let workspaceScope = {session: '', fileKey: null, pageId: null};
let workspaceScopePromise = null;
const workspaceDetailAllowedOps = new Set(['read', 'import', 'sync', 'create', 'apply']);
const workspaceDetailAllowedClasses = new Set(['recorded', 'legacy', 'unknown']);
const workspaceDetailAllowedStates = new Set(['ok', 'pending', 'claimed', 'error', 'uncertain', 'expired']);
const workspaceDetailAllowedPhases = new Set(['queued', 'claimed', 'native-started', 'result-received', 'reconciled', 'uncertain']);
const workspaceDetailAllowedBindings = new Set(['current', 'pinned-historical', 'retired', 'orphan', 'unknown']);
const workspaceDetailAllowedRelTypes = new Set(['declared-dependency', 'recovery-of', 'artifact-input']);
const workspaceDetailAllowedDepDirections = new Set(['predecessor', 'successor']);
const workspaceDetailAllowedRecoveryDirections = new Set(['recovers', 'recovered-by']);
const workspaceDetailAllowedFailureCodes = new Set(['native-conflict', 'result-rejected', 'claim-expired', 'operation-uncertain', 'execution-failed']);
const workspaceDetailAllowedFailureActions = new Set(['inspect-conflicts', 'run-native-read', 'reopen-plugin', 'inspect-private-status']);
const workspaceDetailAllowedDiffStatuses = new Set(['available', 'empty', 'unavailable']);
const workspaceDetailAllowedDiffReasons = new Set(['before-artifact-missing', 'read-only-operation', 'unsupported-task-kind', 'legacy-or-unpinned-artifact', 'unverified-artifact']);
const workspaceDetailAllowedDiffKinds = new Set(['changed', 'added', 'removed', 'type-changed']);
const workspaceDetailAllowedFields = new Set(['value', 'backgroundColor', 'color', 'borderColor', 'fill', 'stroke', 'fontSize', 'fontFamily', 'fontWeight', 'lineHeight', 'letterSpacing', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'gap', 'itemSpacing', 'cornerRadius', 'borderRadius', 'opacity', 'width', 'height', 'visible', 'boolean', 'variant', 'instanceSwap', 'characters']);
const workspaceDetailTextFields = new Set(['characters', 'text', 'rawText', 'textContent', 'label', 'title', 'name', 'placeholder', 'copy', 'content', 'caption', 'description', 'alt']);
function workspaceScrubSecrets(value) {
  if (value === null || value === undefined) return '';
  let text = String(value)
    .replace(/([a-z][a-z0-9+.-]*:\/\/)[^/\s"'<>]+@/gi, '$1')
    .replace(/(?:\/Users\/[^/\s"'<>]+|\/home\/[^/\s"'<>]+|[A-Za-z]:\\Users\\[^\\/\s"'<>]+)/g, '[home]')
    .replace(/([?&](?:access_token|refresh_token|id_token|sync_token|local_sync_token|chat_token|token|api_key|apikey|key|secret|password|capability|bearer|auth)=)[^&#\s"'<>]*/gi, '$1[redacted]')
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]{6,}/g, 'Bearer [redacted]');
  if (typeof WORKSPACE_CONTROL_CONFIG !== 'undefined' && WORKSPACE_CONTROL_CONFIG && typeof WORKSPACE_CONTROL_CONFIG.token === 'string' && WORKSPACE_CONTROL_CONFIG.token) {
    text = text.split(WORKSPACE_CONTROL_CONFIG.token).join('[redacted]');
  }
  if (typeof WORKSPACE_CHAT_CONFIG !== 'undefined' && WORKSPACE_CHAT_CONFIG && typeof WORKSPACE_CHAT_CONFIG.token === 'string' && WORKSPACE_CHAT_CONFIG.token) {
    text = text.split(WORKSPACE_CHAT_CONFIG.token).join('[redacted]');
  }
  return text;
}
function workspaceSanitizeDiffValue(value, field) {
  if (value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) return value;
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    if (value.valueType === 'text') {
      return {valueType: 'text', changed: Boolean(value.changed), length: Number.isFinite(value.length) && value.length >= 0 ? Math.floor(value.length) : 0};
    }
    if (typeof value.r === 'number' && Number.isFinite(value.r) && typeof value.g === 'number' && Number.isFinite(value.g) &&
        typeof value.b === 'number' && Number.isFinite(value.b) && (value.a === undefined || (typeof value.a === 'number' && Number.isFinite(value.a)))) {
      return {r: value.r, g: value.g, b: value.b, a: value.a === undefined ? 1 : value.a};
    }
    return null;
  }
  if (typeof value === 'string') {
    if (workspaceDetailTextFields.has(field)) return {valueType: 'text', changed: true, length: value.length};
    return workspaceScrubSecrets(value).slice(0, 160);
  }
  return null;
}
function workspaceSanitizeOperationDetail(raw, expected) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {ok: false, reason: 'request-rejected'};
  if (raw.schema !== 'figma-flow-operation-detail-v1' || raw.readOnly !== true || !workspaceDetailAllowedClasses.has(raw.classification)) {
    return {ok: false, reason: 'request-rejected'};
  }
  if (!raw.scope || typeof raw.scope !== 'object' || Array.isArray(raw.scope) ||
      raw.scope.fileKey !== expected.fileKey || raw.scope.pageId !== expected.pageId) {
    return {ok: false, reason: 'request-rejected'};
  }
  if (raw.scope.runtimeGeneration !== expected.runtimeGeneration) return {ok: false, reason: 'runtime-mismatch'};
  if (raw.operationId !== expected.operationId || !raw.task || typeof raw.task !== 'object' || Array.isArray(raw.task) ||
      raw.task.key !== expected.taskKey || raw.task.revision !== expected.revision) {
    return {ok: false, reason: 'task-revision-mismatch'};
  }
  const hex32 = v => typeof v === 'string' && /^[a-f0-9]{32}$/.test(v) ? v : null;
  const hex64 = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v) ? v : null;
  const classification = raw.classification;
  const recorded = classification === 'recorded';
  const phases = recorded && Array.isArray(raw.phases)
    ? raw.phases.filter(item => item && typeof item === 'object' && workspaceDetailAllowedPhases.has(item.phase) &&
        typeof item.time === 'string' && item.time.length <= 40 && Number.isFinite(Date.parse(item.time)))
        .slice(0, 64).map(item => ({phase: item.phase, time: item.time}))
    : [];
  const phase = recorded
    ? (workspaceDetailAllowedPhases.has(raw.phase) ? raw.phase : (phases.length ? phases[phases.length - 1].phase : 'unknown'))
    : 'unknown';
  const operation = classification === 'unknown' && !raw.operation
    ? ''
    : (workspaceDetailAllowedOps.has(raw.operation) ? raw.operation : '');
  const state = workspaceDetailAllowedStates.has(raw.state) ? raw.state : 'uncertain';
  const task = {
    key: expected.taskKey,
    revision: expected.revision,
    currentRevision: hex64(raw.task.currentRevision),
    revisionBinding: workspaceDetailAllowedBindings.has(raw.task.revisionBinding) ? raw.task.revisionBinding : 'unknown',
    kind: typeof raw.task.kind === 'string' && workspaceKinds.has(raw.task.kind) ? raw.task.kind : '',
  };
  const failure = raw.failure && typeof raw.failure === 'object' && !Array.isArray(raw.failure) &&
    workspaceDetailAllowedFailureCodes.has(raw.failure.code) && workspaceDetailAllowedFailureActions.has(raw.failure.action)
    ? {code: raw.failure.code, action: raw.failure.action} : null;
  const relations = [];
  if (recorded && Array.isArray(raw.relations)) {
    for (const rel of raw.relations.slice(0, 200)) {
      if (!rel || typeof rel !== 'object' || Array.isArray(rel) || !workspaceDetailAllowedRelTypes.has(rel.type)) continue;
      const taskKey = typeof rel.taskKey === 'string' && rel.taskKey.length > 0 && rel.taskKey.length <= 200 ? workspaceScrubSecrets(rel.taskKey) : '';
      const revision = hex64(rel.revision) || '';
      const currentRevision = hex64(rel.currentRevision);
      const revisionBinding = workspaceDetailAllowedBindings.has(rel.revisionBinding) ? rel.revisionBinding : 'unknown';
      const artifact = typeof rel.artifact === 'string' && rel.artifact.length <= 120 && !/^(?:\/|[A-Za-z]:|~)/.test(rel.artifact) && !rel.artifact.includes('..')
        ? workspaceScrubSecrets(rel.artifact) : '';
      const artifactSha256 = hex64(rel.artifactSha256) || '';
      if (rel.type === 'declared-dependency') {
        if (!workspaceDetailAllowedDepDirections.has(rel.direction)) continue;
        const targetOperationId = taskKey && revision ? hex32(rel.targetOperationId) : null;
        relations.push({type: 'declared-dependency', direction: rel.direction,
          taskKey, revision, currentRevision, revisionBinding, artifact, artifactSha256, targetOperationId});
      } else if (rel.type === 'recovery-of') {
        const linkedId = hex32(rel.operationId);
        if (!linkedId || !taskKey || !revision || !workspaceDetailAllowedRecoveryDirections.has(rel.direction)) continue;
        relations.push({type: 'recovery-of', direction: rel.direction, operationId: linkedId, taskKey, revision, revisionBinding});
      } else if (rel.type === 'artifact-input') {
        const freshness = ['current', 'stale', 'unverified'].includes(rel.freshness) ? rel.freshness : 'unverified';
        relations.push({type: 'artifact-input', taskKey, artifact, artifactSha256, revision, revisionBinding, freshness});
      }
    }
  }
  const rawDiff = recorded && raw.diff && typeof raw.diff === 'object' && !Array.isArray(raw.diff) ? raw.diff : null;
  const conflicts = [];
  if (rawDiff && Array.isArray(rawDiff.conflicts)) {
    for (const conflict of rawDiff.conflicts.slice(0, 50)) {
      if (!conflict || typeof conflict !== 'object' || Array.isArray(conflict)) continue;
      const key = typeof conflict.key === 'string' && conflict.key.length > 0 && conflict.key.length <= 200 ? workspaceScrubSecrets(conflict.key) : '';
      const field = typeof conflict.field === 'string' && (workspaceDetailAllowedFields.has(conflict.field) || workspaceDetailTextFields.has(conflict.field)) ? conflict.field : '';
      if (!key || !field) continue;
      conflicts.push({
        key,
        scope: conflict.scope === 'variable' ? 'variable' : 'node',
        field,
        reasonCode: typeof conflict.reasonCode === 'string' ? workspaceScrubSecrets(conflict.reasonCode).slice(0, 80) : '',
        planSha256: hex64(conflict.planSha256) || '',
        expectedBefore: workspaceSanitizeDiffValue(conflict.expectedBefore, field),
        plannedAfter: workspaceSanitizeDiffValue(conflict.plannedAfter, field),
        observed: workspaceSanitizeDiffValue(conflict.observed, field),
      });
    }
  }
  let diff;
  if (!recorded || !rawDiff || !workspaceDetailAllowedDiffStatuses.has(rawDiff.status) || rawDiff.status === 'unavailable') {
    const reason = !recorded
      ? (classification === 'legacy' ? 'legacy-or-unpinned-artifact' : 'unverified-artifact')
      : (rawDiff && workspaceDetailAllowedDiffReasons.has(rawDiff.reason) ? rawDiff.reason : 'before-artifact-missing');
    diff = {
      status: 'unavailable',
      reason,
      basis: null,
      beforeRevision: null,
      afterRevision: (rawDiff && hex64(rawDiff.afterRevision)) || expected.revision,
      truncated: Boolean(rawDiff && rawDiff.truncated),
      totalFields: 0,
      fields: [],
      conflicts,
    };
  } else {
    const rawFields = Array.isArray(rawDiff.fields) ? rawDiff.fields : [];
    const fields = [];
    for (const row of rawFields.slice(0, 200)) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) continue;
      const key = typeof row.key === 'string' && row.key.length > 0 && row.key.length <= 200 ? workspaceScrubSecrets(row.key) : '';
      const field = typeof row.field === 'string' && (workspaceDetailAllowedFields.has(row.field) || workspaceDetailTextFields.has(row.field)) ? row.field : '';
      const kind = workspaceDetailAllowedDiffKinds.has(row.kind) ? row.kind : null;
      if (!key || !field || !kind) continue;
      fields.push({key, field, kind, before: workspaceSanitizeDiffValue(row.before, field), after: workspaceSanitizeDiffValue(row.after, field)});
    }
    const diffTruncated = Boolean(rawDiff.truncated || rawFields.length > 200);
    const totalFields = Number.isFinite(rawDiff.totalFields) && rawDiff.totalFields >= fields.length ? Math.floor(rawDiff.totalFields) : rawFields.length;
    diff = {
      status: rawDiff.status,
      reason: null,
      basis: rawDiff.basis === 'revision-pair' ? 'revision-pair' : (typeof rawDiff.basis === 'string' ? workspaceScrubSecrets(rawDiff.basis).slice(0, 60) : null),
      beforeRevision: hex64(rawDiff.beforeRevision),
      afterRevision: hex64(rawDiff.afterRevision),
      truncated: diffTruncated,
      totalFields,
      fields,
      conflicts,
    };
  }
  const truncated = Boolean(raw.truncated || diff.truncated);
  const scopeNotice = raw.scopeNotice === 'read-only-truncated-256kib' || truncated ? 'read-only-truncated-256kib' : 'read-only-exact-scope';
  return {
    ok: true,
    detail: {
      schema: 'figma-flow-operation-detail-v1',
      readOnly: true,
      operationId: expected.operationId,
      scope: {fileKey: expected.fileKey, pageId: expected.pageId, runtimeGeneration: expected.runtimeGeneration},
      operation,
      state,
      classification,
      phase,
      phases,
      task,
      failure,
      relations,
      diff,
      truncated,
      scopeNotice,
    },
  };
}
async function workspaceRefreshJournal() {
  if (typeof WORKSPACE_CONTROL_CONFIG === 'undefined' || !WORKSPACE_CONTROL_CONFIG || typeof WORKSPACE_RUNTIME === 'undefined') return;
  const file = figma.fileKey, page = figma.currentPage ? figma.currentPage.id : null, home = workspaceHomeSession;
  if (!file || !page || typeof controlRunSession !== 'string' || !controlRunSession || typeof controlRequest !== 'function') {
    workspaceServerHistory = []; workspaceInputFreshness = []; workspaceJournalUnavailable = true;
    return;
  }
  try {
    const reply = await controlRequest('history', {session_id:controlRunSession, file_key:file, page_id:page, runtime:WORKSPACE_RUNTIME});
    if (file !== figma.fileKey || page !== (figma.currentPage ? figma.currentPage.id : null) || home !== workspaceHomeSession) return;
    workspaceServerHistory = (Array.isArray(reply.journalHistory) ? reply.journalHistory : []).slice(-80).filter(row =>
      row && typeof row.taskKey === 'string' && row.taskKey.length <= 200 && typeof row.revision === 'string' && /^[a-f0-9]{64}$/.test(row.revision) &&
      typeof row.operationId === 'string' && /^[a-f0-9]{32}$/.test(row.operationId) && ['read','import','sync','create','apply'].includes(row.operation))
      .map(row => ({taskKey:row.taskKey, revision:row.revision, operationId:row.operationId, operation:row.operation, ...workspaceJournalHistory(row)}));
    workspaceJournalUnavailable = false;
    workspaceInputFreshness = (Array.isArray(reply.inputFreshness) ? reply.inputFreshness : []).slice(0, 80).filter(row =>
      row && typeof row.taskKey === 'string' && row.taskKey.length <= 200 && typeof row.revision === 'string' && /^[a-f0-9]{64}$/.test(row.revision) && ['current','stale','unverified'].includes(row.status))
      .map(row => ({taskKey:row.taskKey, revision:row.revision, status:row.status, changed:(Array.isArray(row.changed) ? row.changed : []).filter(path => typeof path === 'string' && path.length <= 2048 && !/^(?:\/|[A-Za-z]:|~)/.test(path)).slice(0, 100)}));
  } catch (_) {
    if (file === figma.fileKey && page === (figma.currentPage ? figma.currentPage.id : null) && home === workspaceHomeSession) {
      workspaceServerHistory = []; workspaceInputFreshness = []; workspaceJournalUnavailable = true;
    }
  }
}
async function workspaceHandleScopeChange() {
  if ((workspaceActive && workspaceActive.view !== 'remote') || !workspaceHomeSession || workspaceScope.session !== workspaceHomeSession) return false;
  const currentFile = figma.fileKey || null;
  const currentPage = (figma.currentPage && figma.currentPage.id) || null;
  if (currentFile === workspaceScope.fileKey && currentPage === workspaceScope.pageId) return false;
  if (workspaceScopePromise) return workspaceScopePromise;
  workspaceScopePromise = (async () => {
    let emitted = false;
    for (let attempt = 0; attempt < 3; attempt++) {
      if ((workspaceActive && workspaceActive.view !== 'remote') || !workspaceHomeSession || workspaceScope.session !== workspaceHomeSession) return emitted;
      const nextFile = figma.fileKey || null;
      const nextPage = (figma.currentPage && figma.currentPage.id) || null;
      if (nextFile === workspaceScope.fileKey && nextPage === workspaceScope.pageId) return emitted;
      const home = workspaceHomeSession;
      workspaceScope = {session: home, fileKey: nextFile, pageId: nextPage};
      workspaceServerHistory = [];
      workspaceInputFreshness = [];
      workspaceJournalUnavailable = false;
      await workspaceRefreshJournal();
      if ((workspaceActive && workspaceActive.view !== 'remote') || workspaceHomeSession !== home) return emitted;
      if ((figma.fileKey || null) !== nextFile || ((figma.currentPage && figma.currentPage.id) || null) !== nextPage) continue;
      figma.ui.postMessage({
        type: 'workspace-scope-changed',
        workspaceSession: home,
        fileKey: nextFile,
        pageId: nextPage,
        ...(typeof WORKSPACE_RUNTIME !== 'undefined' && WORKSPACE_RUNTIME && typeof WORKSPACE_RUNTIME.generation === 'string'
          ? {runtimeGeneration: WORKSPACE_RUNTIME.generation} : {}),
        journalHistory: workspaceServerHistory,
        journalUnavailable: workspaceJournalUnavailable,
        inputFreshness: workspaceInputFreshness,
      });
      emitted = true;
      return emitted;
    }
    return emitted;
  })().finally(() => {workspaceScopePromise = null;});
  return workspaceScopePromise;
}
async function workspaceFetchHistoryDetail(message) {
  const initialSession = workspaceHomeSession;
  const initialFileKey = figma.fileKey || null;
  const initialPageId = (figma.currentPage && figma.currentPage.id) || null;
  const hasReqId = message.requestId !== undefined && message.requestId !== null;
  const validReqId = !hasReqId || (typeof message.requestId === 'string' && /^[A-Za-z0-9_:-]{1,80}$/.test(message.requestId));
  const requestId = validReqId && hasReqId ? message.requestId : null;
  const opId = typeof message.operationId === 'string' && /^[a-f0-9]{32}$/.test(message.operationId) ? message.operationId : null;
  const taskKey = typeof message.taskKey === 'string' && message.taskKey.length >= 1 && message.taskKey.length <= 200 ? message.taskKey : null;
  const revision = typeof message.revision === 'string' && /^[a-f0-9]{64}$/.test(message.revision) ? message.revision : null;
  const postResult = (status, reason, detail = null) => {
    figma.ui.postMessage({
      type: 'workspace-history-detail-result',
      workspaceSession: initialSession,
      operationId: opId,
      taskKey: taskKey || '',
      revision: revision || '',
      requestId,
      status,
      reason,
      detail,
    });
  };
  if (!validReqId) {postResult('error', 'request-rejected'); return;}
  if (workspaceScope.session === initialSession &&
      (workspaceScope.fileKey !== initialFileKey || workspaceScope.pageId !== initialPageId)) {
    postResult('scope-changed', 'scope-changed');
    await workspaceHandleScopeChange();
    return;
  }
  if (!opId) {postResult('error', 'invalid-operation-id'); return;}
  if (!taskKey || !revision) {postResult('error', 'invalid-task-revision-binding'); return;}
  const knownRow = workspaceServerHistory.find(row => row.operationId === opId);
  if (knownRow && (knownRow.taskKey !== taskKey || knownRow.revision !== revision)) {
    postResult('error', 'task-revision-mismatch');
    return;
  }
  if (typeof WORKSPACE_CONTROL_CONFIG === 'undefined' || !WORKSPACE_CONTROL_CONFIG || typeof WORKSPACE_RUNTIME === 'undefined' ||
      !WORKSPACE_RUNTIME || typeof controlRunSession !== 'string' || !controlRunSession ||
      typeof controlRequest !== 'function' || !initialFileKey || !initialPageId) {
    postResult('unavailable', 'control-unavailable');
    return;
  }
  if (typeof WORKSPACE_RUNTIME !== 'object' || Array.isArray(WORKSPACE_RUNTIME) ||
      typeof WORKSPACE_RUNTIME.version !== 'string' || !WORKSPACE_RUNTIME.version ||
      typeof WORKSPACE_RUNTIME.implementation !== 'string' || !/^[a-f0-9]{64}$/.test(WORKSPACE_RUNTIME.implementation) ||
      typeof WORKSPACE_RUNTIME.generation !== 'string' || !/^[a-f0-9]{32}$/.test(WORKSPACE_RUNTIME.generation)) {
    postResult('error', 'runtime-mismatch');
    return;
  }
  const runtime = {
    version: WORKSPACE_RUNTIME.version,
    implementation: WORKSPACE_RUNTIME.implementation,
    generation: WORKSPACE_RUNTIME.generation,
  };
  const body = {
    session_id: controlRunSession,
    file_key: initialFileKey,
    page_id: initialPageId,
    runtime,
    operation_id: opId,
    task_key: taskKey,
    revision,
  };
  const checkScope = () => {
    if (workspaceHomeSession !== initialSession || (workspaceActive && workspaceActive.view !== 'remote')) return 'gone';
    if ((figma.fileKey || null) !== initialFileKey || ((figma.currentPage && figma.currentPage.id) || null) !== initialPageId) return 'changed';
    return 'ok';
  };
  let raw;
  try {
    raw = await controlRequest('history-detail', body);
  } catch (error) {
    const scopeState = checkScope();
    if (scopeState === 'gone') return;
    if (scopeState === 'changed') {
      postResult('scope-changed', 'scope-changed');
      await workspaceHandleScopeChange();
      return;
    }
    if (error && (error.code === 'payload-limit-exceeded' || /exceeds its limit/i.test(error.message || ''))) {
      postResult('error', 'payload-limit-exceeded');
    } else if (error && (error.code === 'request-timeout' || /timed out/i.test(error.message || ''))) {
      postResult('error', 'request-timeout');
    } else if (error && error.status === 404) {
      postResult('unavailable', 'not-found-in-scope');
    } else if (error && error.status === 409) {
      const allowed409 = new Set(['invalid-operation-id', 'invalid-task-revision-binding', 'task-revision-mismatch', 'runtime-mismatch']);
      postResult('error', allowed409.has(error.reason) ? error.reason : 'request-rejected');
    } else if (error && (error.status === 403 || error.status === 413 || error.status === 400)) {
      postResult('error', 'request-rejected');
    } else {
      postResult('unavailable', 'control-unavailable');
    }
    return;
  }
  const scopeState = checkScope();
  if (scopeState === 'gone') return;
  if (scopeState === 'changed') {
    postResult('scope-changed', 'scope-changed');
    await workspaceHandleScopeChange();
    return;
  }
  const sanitized = workspaceSanitizeOperationDetail(raw, {
    fileKey: initialFileKey,
    pageId: initialPageId,
    runtimeGeneration: runtime.generation,
    operationId: opId,
    taskKey,
    revision,
  });
  if (!sanitized.ok) {
    postResult('error', sanitized.reason);
    return;
  }
  postResult('ok', null, sanitized.detail);
}
let workspaceWrites = Promise.resolve();
let workspaceStorageError = false;
let workspaceHomeView = 'tasks', workspaceProject = null, workspaceFocus = null;
async function workspaceLoadState() {
  if (!workspaceStorageKey || !figma.clientStorage) return;
  try {
    const saved = await figma.clientStorage.getAsync(workspaceStorageKey);
    if (!saved || typeof saved !== 'object') return;
    if (workspaceLocales.has(saved.locale)) workspaceState.locale = saved.locale;
    if (Array.isArray(saved.history)) workspaceState.history = saved.history.filter(event =>
      event && typeof event.taskKey === 'string' && event.taskKey.length <= 200 &&
      typeof event.revision === 'string' && event.revision.length <= 128 &&
      workspaceOperations.has(event.operation) && workspaceStatuses.has(event.status) &&
      typeof event.time === 'string' && event.time.length <= 40 && Number.isFinite(Date.parse(event.time))).slice(-80)
      .map(({taskKey, revision, time, operation, status, executionId, carousel}) => ({taskKey, revision, time, operation, status,
        ...(typeof executionId === 'string' && /^[a-z0-9-]{1,80}$/.test(executionId) ? {executionId} : {}),
        ...(workspaceStoredCarousel(carousel) ? {carousel: workspaceStoredCarousel(carousel)} : {})}));
  } catch (_) {workspaceStorageError = true;}
}
function workspaceStoredCarousel(value) {
  if (!value || value.schema !== 'figma-flow-carousel-summary-v1' || !/^[a-f0-9]{64}$/.test(value.graph_sha256 || '')
      || typeof value.graph_id !== 'string' || value.graph_id.length > 120 || typeof value.page_id !== 'string' || value.page_id.length > 64
      || typeof value.file_key !== 'string' || value.file_key.length > 128 || typeof value.frame_key !== 'string' || value.frame_key.length > 120
      || !Array.isArray(value.states) || value.states.length < 2 || value.states.length > 16
      || !Array.isArray(value.edges) || value.edges.length > 80) return null;
  const states = value.states.filter(state => state && ['current','changed','missing'].includes(state.status)
    && [state.state_id,state.screen_id,state.frame_id].every(item => typeof item === 'string' && item.length <= 128))
    .map(state => ({state_id:state.state_id, screen_id:state.screen_id, frame_id:state.frame_id, status:state.status,
      ...(typeof state.title === 'string' && state.title.trim().length <= 160 ? {title:state.title.trim()} : {})}));
  const edges = value.edges.filter(edge => edge && typeof edge.from === 'string' && typeof edge.to === 'string'
    && (['AFTER_TIMEOUT','ON_DRAG','ON_CLICK'].includes(edge.trigger) && typeof edge.destination_id === 'string'
      || edge.trigger === 'NO_NAVIGATION' && edge.boundary === 'stay' && edge.destination_id === null))
      .slice(0,80).map(edge => ({from:edge.from, to:edge.to, trigger:edge.trigger, destination_id:edge.destination_id,
      ...(Number.isFinite(edge.timeout) && edge.timeout >= 0 && edge.timeout <= 60 ? {timeout:edge.timeout} : {}),
      ...(edge.direction === 'LEFT' || edge.direction === 'RIGHT' ? {direction:edge.direction} : {}),
      ...(edge.boundary === 'stay' ? {boundary:'stay'} : {}),
      ...(edge.input === 'swipe_left' || edge.input === 'swipe_right' ? {input:edge.input} : {}),
      ...(edge.edge_id && typeof edge.edge_id === 'string' && edge.edge_id.length <= 120 ? {edge_id:edge.edge_id} : {})}));
  if (states.length !== value.states.length) return null;
  return {schema:value.schema, graph_sha256:value.graph_sha256, graph_id:value.graph_id, file_key:value.file_key, page_id:value.page_id,
    frame_key:value.frame_key, status:['current','changed','missing'].includes(value.status) ? value.status : 'changed',
    initial_state:typeof value.initial_state === 'string' ? value.initial_state : '',
    flow_start_node_id:typeof value.flow_start_node_id === 'string' ? value.flow_start_node_id : '', states, edges};
}
function workspaceCarouselSummary(data, task, pageId) {
  const receipt = data?.web_design, carousel = receipt?.carousel || receipt?.tabs || receipt?.disclosure;
  const actualScreenRead = data?.schema === 'figma-flow-web-screen-discovery-v1' && data.readback_scope === 'screens'
    && Array.isArray(data.nodes) && data.graph_sha256 === receipt?.graph_sha256;
  if (!actualScreenRead || data.fileKey !== figma.fileKey
      || data.pageId !== pageId || task.fileKey !== data.fileKey || task.pageId && task.pageId !== pageId
      || !receipt || !/^[a-f0-9]{64}$/.test(receipt.graph_sha256 || '') || typeof receipt.graph_id !== 'string'
      || carousel?.frame_key === undefined || !Array.isArray(carousel.states)) return null;
  const stateByFrame = new Map(carousel.states.map(state => [state.frame_id, state.state_id]));
  const edges = [];
  for (const state of carousel.states.slice(0,16)) {
    for (const reaction of state.reactions || []) edges.push({from:state.state_id,
      to:stateByFrame.get(reaction.destination_id) || '', trigger:reaction.trigger, destination_id:reaction.destination_id,
      timeout:reaction.timeout, direction:reaction.transition?.direction, edge_id:reaction.edge_id});
    for (const hotspot of state.hotspots || []) {
      if (hotspot.boundary === true) edges.push({from:state.state_id, to:state.state_id, trigger:'NO_NAVIGATION',
        destination_id:null, boundary:'stay', input:hotspot.input, edge_id:hotspot.edge_id});
      else if (hotspot.trigger) edges.push({from:state.state_id,
        to:stateByFrame.get(hotspot.destination_id) || '', trigger:hotspot.trigger, destination_id:hotspot.destination_id,
        timeout:hotspot.timeout, direction:hotspot.transition?.direction, input:hotspot.input, edge_id:hotspot.edge_id});
    }
    for (const control of state.controls || []) if (control.trigger) edges.push({from:state.state_id,
      to:stateByFrame.get(control.destination_id) || '', trigger:control.trigger, destination_id:control.destination_id,
      input:control.input, edge_id:control.edge_id});
  }
  return workspaceStoredCarousel({schema:'figma-flow-carousel-summary-v1', graph_sha256:receipt.graph_sha256,
    graph_id:receipt.graph_id, file_key:data.fileKey, page_id:data.pageId, frame_key:carousel.frame_key,
    status:carousel.status, initial_state:carousel.initial_state, flow_start_node_id:carousel.flow_start_node_id,
    states:carousel.states.slice(0,16), edges:edges.slice(0,80)});
}
function workspaceAttachCarousel(current, data, pageId) {
  const summary = workspaceCarouselSummary(data, current.task, pageId);
  if (!summary) return;
  let event = [...workspaceState.history].reverse().find(row => row.taskKey === current.task.key && row.revision === current.task.revision
    && row.executionId === current.executionId);
  if (!event) {
    event = {taskKey:current.task.key, revision:current.task.revision || '', time:new Date().toISOString(), operation:'apply', status:'readback', executionId:current.executionId};
    workspaceState.history.push(event);
  }
  event.carousel = summary;
  workspaceState.history = workspaceState.history.slice(-80);
  workspacePersist();
}
async function workspaceSelectCarousel(current, request, home = false) {
  const task = home ? workspaceTasks.get(request?.taskKey) : current?.task;
  const event = [...workspaceState.history].reverse().find(row => row.taskKey === task?.key && row.revision === task?.revision
    && row.executionId === request?.executionId);
  const summary = workspaceStoredCarousel(event?.carousel), state = summary?.states.find(item => item.state_id === summary.initial_state);
  if (!summary || summary.status !== 'current' || !state || state.status !== 'current'
      || !task || task.kind !== 'native-edit' || task.key !== request?.taskKey || task.revision !== request?.revision
      || summary.file_key !== figma.fileKey || task.fileKey !== summary.file_key || summary.page_id !== task.pageId
      || request?.nodeId !== summary.flow_start_node_id || request?.stateId !== summary.initial_state)
    throw Error('Carousel readback is stale or outside this prepared task. Run native read again.');
  if (home && (request.workspaceSession !== workspaceHomeSession
      || workspaceActive && (workspaceActive.view !== 'remote' || workspaceBusy(workspaceActive)
        || workspaceActive.task.key !== task.key || workspaceActive.task.revision !== task.revision)))
    throw Error('The prepared task session changed. Return to the current file task list.');
  if (!home && !workspaceCurrent(current)) throw Error('The prepared task session changed. Reopen it and try again.');
  const page = await figma.getNodeByIdAsync(summary.page_id);
  if (page?.type !== 'PAGE') throw Error('The carousel page is no longer available.');
  await page.loadAsync();
  const scopeCurrent = () => home
    ? workspaceHomeSession === request.workspaceSession && (!workspaceActive || workspaceActive.view === 'remote'
      && !workspaceBusy(workspaceActive) && workspaceActive.task.key === task.key && workspaceActive.task.revision === task.revision)
    : workspaceCurrent(current);
  if (!scopeCurrent() || figma.fileKey !== summary.file_key) throw Error('The prepared task or active Figma file changed.');
  if (figma.currentPage.id !== page.id) await figma.setCurrentPageAsync(page);
  if (!scopeCurrent() || figma.fileKey !== summary.file_key || figma.currentPage.id !== page.id)
    throw Error('The prepared task or active Figma page changed.');
  const frame = await figma.getNodeByIdAsync(summary.flow_start_node_id);
  let owner = frame;
  while (owner && owner.type !== 'PAGE') owner = owner.parent;
  const sourceState = summary.states.find(item => item.state_id === summary.initial_state);
  if (!frame || frame.type !== 'FRAME' || owner?.id !== page.id
      || frame.getPluginData('figma-flow-web-design-id') !== `${summary.graph_id}/${sourceState.screen_id}`
      || frame.getPluginData('figma-flow-web-design-sha256') !== summary.graph_sha256)
    throw Error('The recorded initial frame changed or is unavailable. Run native read again.');
  if (!(page.flowStartingPoints || []).some(start => start.nodeId === frame.id))
    throw Error('The recorded frame is no longer a Figma flow start. Run native read again.');
  figma.currentPage.selection = [frame];
  figma.viewport.scrollAndZoomIntoView([frame]);
  const url = request.action === 'present' ? workspaceCarouselPresentationUrl(summary) : null;
  if (request.action === 'present') {
    if (!url || typeof figma.openExternal !== 'function') throw Error('A verified Figma presentation link is unavailable.');
    figma.openExternal(url);
  }
  // openExternal gives no delivery signal, so the presented reply carries the same verified URL for a user-clicked link.
  const result = {type:request.action === 'present' ? 'workspace-carousel-presented' : 'workspace-carousel-selected',
    workspaceSession:home ? workspaceHomeSession : current.session, executionId:request.executionId,
    stateId:summary.initial_state, nodeId:frame.id, ...(url ? {taskKey:task.key, url} : {})};
  figma.ui.postMessage(home ? result : {workspaceSession:current.session, payload:result});
}
function workspaceCarouselPresentationUrl(summary) {
  const safeFile = /^[A-Za-z0-9_-]{1,128}$/.test(summary?.file_key || '');
  const safeId = value => typeof value === 'string' && /^\d+(?:[:-]\d+)$/.test(value);
  if (!safeFile || !safeId(summary.page_id) || !safeId(summary.flow_start_node_id)) return null;
  const page = summary.page_id.replaceAll(':', '-'), node = summary.flow_start_node_id.replaceAll(':', '-');
  return `https://www.figma.com/proto/${summary.file_key}/SaaS?node-id=${node}&starting-point-node-id=${node}&page-id=${page}&scaling=scale-down`;
}
function workspacePersist() {
  if (!workspaceStorageKey || !figma.clientStorage) return;
  const snapshot = JSON.parse(JSON.stringify(workspaceState));
  workspaceWrites = workspaceWrites.catch(() => {}).then(() => figma.clientStorage.setAsync(workspaceStorageKey, snapshot))
    .catch(() => {workspaceStorageError = true;});
}
function workspaceJournalHistory(view) {
  if (!view || typeof view !== 'object' || view.classification === 'legacy') return {classification: 'legacy', phase: 'unknown', phases: []};
  if (view.classification !== 'recorded' || !Array.isArray(view.phases)) return {classification: 'unknown', phase: 'unknown', phases: []};
  const phases = view.phases.slice(-32).filter(item => item && ['queued','claimed','native-started','result-received','reconciled','uncertain'].includes(item.phase) &&
    typeof item.time === 'string' && item.time.length <= 40 && Number.isFinite(Date.parse(item.time))).map(item => ({phase: item.phase, time: item.time}));
  return {classification: 'recorded', phase: phases.length ? phases[phases.length - 1].phase : 'unknown', phases};
}
function workspaceRecord(current, operation, status, journal) {
  if (!workspaceCurrent(current) || !workspaceOperations.has(operation) || !workspaceStatuses.has(status)) return;
  const event = {taskKey: current.task.key, revision: current.task.revision || '',
    time: new Date().toISOString(), operation, status,
    ...(operation === 'download' || !current.executionId ? {} : {executionId: current.executionId})};
  if (journal) {
    const serverJournal = workspaceJournalHistory(journal);
    event.classification = serverJournal.classification;
    event.phase = serverJournal.phase;
  }
  workspaceState.history.push(event);
  workspaceState.history = workspaceState.history.slice(-80);
  workspacePersist();
}
function workspaceObserve(current, message) {
  if (!message || !current.operation) return;
  if (message.readback?.web_design?.carousel || message.readback?.web_design?.tabs || message.readback?.web_design?.disclosure) workspaceAttachCarousel(current, message.readback, figma.currentPage.id);
  if (message.busy === true || message.state === 'busy' || (message.type === 'busy' && message.value === true)) {
    if (!current.started) workspaceRecord(current, current.operation, 'running');
    current.started = true;
  }
  if (message.type === 'geometry-failure' || message.type === 'chat:error' || message.error || message.readback?.status === 'error' ||
      message.rollback_conflicts?.length || message.readback?.rollback_conflicts?.length ||
      (message.type === 'sync-result' && (message.result?.preview_error || !['baseline','applied','unchanged'].includes(message.result?.status))) ||
      (message.type === 'status' && (message.state === 'error' || /^Error:/.test(message.message || '')))) {
    if (current.outcome !== 'failed') workspaceRecord(current, current.operation, 'failed');
    current.outcome = 'failed';
  } else if (message.type === 'readback' || message.readback) {
    if (!current.outcome) workspaceRecord(current, current.operation, 'readback');
    current.outcome = 'readback';
  } else if (message.type === 'sync-result' || message.type === 'chat:result') {
    const outcome = message.type === 'sync-result' && message.result.status === 'baseline' ? 'baseline' : 'finished';
    if (!current.outcome) workspaceRecord(current, current.operation, outcome);
    current.outcome = outcome;
  }
}
function workspacePreview(task) {
  return (Array.isArray(task.preview) ? task.preview : []).filter(item =>
    item && typeof item.title === 'string' && item.title.length <= 120 && typeof item.src === 'string' &&
    item.src.length <= 600000 && /^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/=]+$/.test(item.src)).slice(0, 2)
    .map(({title, src}) => ({title, src}));
}
function workspaceLocaleHtml(html) {
  const locale = workspaceState.locale;
  if (!locale) return html;
  return html.replace(/<html([^>]*)>/i, (_, attributes) => '<html' + attributes.replace(/\sdata-flow-locale=(?:"[^"]*"|'[^']*')/gi, '') +
    ' data-flow-locale="' + locale + '">');
}
const workspaceSession = () => Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2);
const workspaceBusy = current => current.inFlight > 0 || current.busy;
const workspaceCurrent = current => workspaceActive === current;
function workspaceControl(current) {
  if (current.view === 'remote') return;
  if (workspaceCurrent(current)) figma.ui.postMessage({workspaceSession: current.session, workspaceControl: true, busy: workspaceBusy(current)});
}
function workspaceHome(notice = '', view = 'tasks', project = null, focus = null) {
  if (workspaceActive && workspaceBusy(workspaceActive)) return false;
  if (workspaceActive?.controller) workspaceActive.controller.close();
  workspaceActive = null;
  workspaceNotice = notice;
  workspaceHomeView = view; workspaceProject = project; workspaceFocus = focus;
  workspaceHomeSession = workspaceSession();
  workspaceScope = {session: '', fileKey: null, pageId: null};
  workspaceServerHistory = []; workspaceInputFreshness = []; workspaceJournalUnavailable = false;
  figma.showUI(workspaceLocaleHtml(__html__), {width: 560, height: 680, themeColors: true});
  return true;
}
function workspaceTaskFigma() {
  const current = workspaceActive;
  if (!current) throw Error('No registered workspace task is open');
  const assertCurrent = () => {
    if (!workspaceCurrent(current)) throw Error('Workspace task session expired');
    if (current.task.fileKey && current.task.fileKey !== figma.fileKey) throw Error('Workspace task file scope changed');
  };
  const ui = new Proxy({}, {
    get(_target, key) {
      const target = figma.ui;
      if (key === 'onmessage') return current.handler;
      if (key === 'postMessage') return message => {
        if (!workspaceCurrent(current)) return;
        if (typeof message?.busy === 'boolean') current.busy = message.busy;
        else if (message?.type === 'busy' && typeof message.value === 'boolean') current.busy = message.value;
        else if (message?.state === 'busy') current.busy = true;
        else if (message && ('readback' in message || 'error' in message)) current.busy = false;
        workspaceObserve(current, message);
        if (current.view === 'remote') {if (current.onOutput) current.onOutput(message); return;}
        target.postMessage({workspaceSession: current.session, payload: message});
        workspaceControl(current);
      };
      const value = Reflect.get(target, key);
      return typeof value === 'function' ? (...args) => {assertCurrent(); return value.apply(target, args);} : value;
    },
    set(target, key, value) {
      assertCurrent();
      if (key !== 'onmessage' || typeof value !== 'function') throw Error('Unsupported task UI assignment');
      current.handler = value;
      return true;
    }
  });
  return new Proxy({}, {
    get(_target, key) {
      const target = figma;
      if (key === 'ui') return ui;
      const value = Reflect.get(target, key);
      return typeof value === 'function' ? (...args) => {
        assertCurrent();
        if (key === 'showUI') {
          if (current.view === 'remote') {current.html = args[0]; current.options = args[1]; return;}
          const options = {...args[1], themeColors: true};
          const result = value.call(target, args[0], options);
          workspaceControl(current);
          return result;
        }
        return value.apply(target, args);
      } : value;
    },
    set() {throw Error('Task cannot replace workspace host state');}
  });
}
function workspaceTaskHtml(html) {
  if (!workspaceActive || typeof html !== 'string') throw Error('Task HTML requires an active workspace session');
  html = workspaceLocaleHtml(html).replace(/<html([^>]*)>/i, (_, attributes) =>
    '<html' + attributes.replace(/\sdata-flow-workspace=(?:"[^"]*"|'[^']*')/gi, '') + ' data-flow-workspace="true">');
  const session = JSON.stringify(workspaceActive.session);
  // The lexical parent wrapper keeps existing approved message schemas intact.
  const relay = `<script>
const workspaceSession = ${session};
const workspaceView = ${JSON.stringify(workspaceActive.view === 'chat' ? 'codex' : 'tasks')};
let workspaceHostBusy = false;
window.FlowWorkspace = Object.freeze({
  active: workspaceView,
  canChat: ${JSON.stringify(!!workspaceActive.task.threadId)},
  get busy() {return workspaceHostBusy;},
  go(name) {
    if (workspaceHostBusy || !['tasks', 'history', 'codex'].includes(name) || (name === 'codex' && workspaceView === 'codex')) return;
    const type = name === 'history' ? 'workspace-history' : name === 'codex' ? 'workspace-chat' : 'workspace-back';
    window.parent.postMessage({pluginMessage: {type, workspaceSession}}, '*');
  },
  setLocale(locale) {
    if (!${JSON.stringify([...workspaceLocales])}.includes(locale)) return;
    if (window.FlowUI) window.FlowUI.setLocale(locale);
    window.parent.postMessage({pluginMessage: {type: 'workspace-locale', workspaceSession, locale}}, '*');
  }
});
const parent = {postMessage(message) {
  window.parent.postMessage({pluginMessage: {type: 'workspace-task-message', workspaceSession, payload: message.pluginMessage}}, '*');
}};
window.addEventListener('message', event => {
  const message = event.data && event.data.pluginMessage;
  if (!message || message.workspaceSession !== workspaceSession) {event.stopImmediatePropagation(); return;}
  if (message.workspaceControl) {
    workspaceHostBusy = !!message.busy;
    window.dispatchEvent(new CustomEvent('flow:host-busy', {detail: {busy: workspaceHostBusy}}));
    if (window.FlowPanel) window.FlowPanel.setState({busy: !!message.busy});
    event.stopImmediatePropagation(); return;
  }
  Object.defineProperty(event, 'data', {value: {pluginMessage: message.payload}});
}, true);
window.addEventListener('DOMContentLoaded', () => {
  if (window.FlowPanel) window.FlowPanel.mount({
    mode: 'workspace', active: workspaceView,
    onNavigate: window.FlowWorkspace.go,
    onLocale: window.FlowWorkspace.setLocale
  });
  document.addEventListener('click', event => {
    if (event.target.closest && event.target.closest('#save:not(:disabled), #download:not(:disabled)'))
      window.parent.postMessage({pluginMessage: {type: 'workspace-download', workspaceSession}}, '*');
  }, true);
  window.parent.postMessage({pluginMessage: {type: 'workspace-navigation-ready', workspaceSession}}, '*');
});
</script>`;
  const head = html.match(/<head(?:\s[^>]*)?>/i);
  if (head) return html.replace(head[0], head[0] + relay);
  const opening = html.match(/<html(?:\s[^>]*)?>/i) || html.match(/<!doctype[^>]*>/i);
  return opening ? html.replace(opening[0], opening[0] + relay) : relay + html;
}
async function workspaceOpen(task, view = 'task') {
  if (workspaceActive && workspaceBusy(workspaceActive)) return;
  if (task.fileKey && task.fileKey !== figma.fileKey) return;
  if (workspaceActive?.controller) workspaceActive.controller.close();
  const current = {task, view, session: workspaceSession(), handler: null, inFlight: 1, busy: false, controller: null};
  workspaceActive = current;
  try {
    if (view === 'chat') {
      if (typeof WorkspaceChat === 'undefined' || !task.threadId) throw Error('이 작업에는 Codex 대화가 연결되지 않았습니다.');
      const proxy = workspaceTaskFigma();
      current.controller = WorkspaceChat.open(proxy, task, {
        session: current.session, isCurrent: () => workspaceCurrent(current),
        showUI: (html, options) => proxy.showUI(workspaceTaskHtml(html), options),
        postMessage: message => proxy.ui.postMessage(message), uiHtml: WORKSPACE_CHAT_UI,
        onBack: workspaceHome,
        relay: typeof WORKSPACE_CHAT_CONFIG === 'undefined' ? null : WORKSPACE_CHAT_CONFIG
      });
      current.handler = message => current.controller.handle(message);
    } else {
      await task.run();
    }
  } catch (error) {
    current.inFlight = 0; current.busy = false;
    if (view === 'remote') {workspaceActive = null; throw error;}
    workspaceHome(String(error.message || error));
  } finally {
    current.inFlight = 0;
    workspaceControl(current);
  }
  return workspaceCurrent(current) ? current : null;
}
function workspaceAssetSummary(value) {
  if (!Array.isArray(value)) return undefined;
  const rows = [];
  for (const row of value) {
    if (!row || typeof row.ref !== 'string' || row.ref.includes('/Users/') || row.ref.startsWith('/') || typeof row.status !== 'string') continue;
    rows.push({ref: row.ref, kind: typeof row.kind === 'string' ? row.kind : 'file', status: row.status, source: typeof row.source === 'string' ? row.source : '', digest: typeof row.digest === 'string' ? row.digest : ''});
  }
  return rows.length ? rows : undefined;
}
function workspaceDependencyEdges(value) {
  if (!Array.isArray(value)) return undefined;
  const names = new Set(['code.js', 'ui.html', 'manifest.json']);
  const edges = [];
  for (const edge of value) {
    if (!edge || edge.relation !== 'uses-output' || !names.has(edge.artifact)) continue;
    if (typeof edge.task_key !== 'string' || typeof edge.revision !== 'string' || typeof edge.artifact_sha256 !== 'string') continue;
    edges.push({task_key: edge.task_key, revision: edge.revision, relation: edge.relation, artifact: edge.artifact, artifact_sha256: edge.artifact_sha256});
  }
  return edges.length ? edges : undefined;
}
async function workspaceOnMessage(message) {
  if (!message || typeof message !== 'object') return;
  const activeBeforeLoad = workspaceActive, homeBeforeLoad = workspaceHomeSession;
  await workspaceLoaded;
  if (workspaceActive !== activeBeforeLoad || (!workspaceActive && workspaceHomeSession !== homeBeforeLoad)) return;
  if (message.type === 'workspace-locale') {
    const expected = !workspaceActive || workspaceActive.view === 'remote' ? workspaceHomeSession : workspaceActive.session;
    if (message.workspaceSession === expected && workspaceLocales.has(message.locale) &&
        (!workspaceActive?.task.fileKey || workspaceActive.task.fileKey === figma.fileKey)) {
      workspaceState.locale = message.locale; workspacePersist();
    }
    return;
  }
  if (message.type === 'workspace-control-tick') {
    if (message.workspaceSession === workspaceHomeSession && (!workspaceActive || workspaceActive.view === 'remote')) {
      await workspaceHandleScopeChange();
      if (message.workspaceSession === workspaceHomeSession && message.fileKey === figma.fileKey &&
          (!workspaceActive || workspaceActive.view === 'remote') && typeof workspaceControlTick === 'function') await workspaceControlTick();
    }
    return;
  }
  if (message.type === 'workspace-history-detail') {
    if (!workspaceHomeSession || message.workspaceSession !== workspaceHomeSession ||
        (workspaceActive && workspaceActive.view !== 'remote')) return;
    await workspaceFetchHistoryDetail(message);
    return;
  }
  if (['workspace-carousel-select','workspace-carousel-present'].includes(message.type)) {
    if (message.workspaceSession !== workspaceHomeSession) return;
    const request = {...message, action:message.type === 'workspace-carousel-present' ? 'present' : 'select'};
    try { await workspaceSelectCarousel(null, request, true); }
    catch (error) { figma.ui.postMessage({type:'workspace-carousel-error', workspaceSession:workspaceHomeSession,
      message:String(error.message || error)}); }
    return;
  }
  if (!workspaceActive) {
    if (message.type === 'workspace-home-ready') {
      if (!workspaceState.locale) {
        const code = String(message.locale || '').toLowerCase().split('-')[0];
        workspaceState.locale = workspaceLocales.has(code) ? code : 'ko'; workspacePersist();
      }
      const readyFile = figma.fileKey || null, readyPage = (figma.currentPage && figma.currentPage.id) || null;
      await workspaceRefreshJournal();
      if (workspaceActive || workspaceHomeSession !== homeBeforeLoad) return;
      if ((figma.fileKey || null) !== readyFile || ((figma.currentPage && figma.currentPage.id) || null) !== readyPage) {
        await workspaceRefreshJournal();
        if (workspaceActive || workspaceHomeSession !== homeBeforeLoad) return;
      }
      const activeFile = figma.fileKey || null, activePage = (figma.currentPage && figma.currentPage.id) || null;
      workspaceScope = {session: workspaceHomeSession, fileKey: activeFile, pageId: activePage};
      const retired = typeof FLOW_RETIRED === 'undefined' || !Array.isArray(FLOW_RETIRED) ? [] : FLOW_RETIRED.filter(row =>
        row && typeof row.key === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(row.key) && typeof row.revision === 'string' && /^[a-f0-9]{64}$/.test(row.revision))
        .map(({key, revision}) => ({key, revision}));
      figma.ui.postMessage({type: 'workspace-tasks', workspaceSession: workspaceHomeSession,
        fileKey: activeFile, pageId: activePage,
        ...(typeof WORKSPACE_RUNTIME !== 'undefined' && WORKSPACE_RUNTIME && typeof WORKSPACE_RUNTIME.generation === 'string'
          ? {runtimeGeneration: WORKSPACE_RUNTIME.generation} : {}),
        controlEnabled: typeof WORKSPACE_CONTROL_CONFIG !== 'undefined' && !!WORKSPACE_CONTROL_CONFIG, locale: workspaceState.locale, history: workspaceState.history,
        journalHistory:workspaceServerHistory, journalUnavailable:workspaceJournalUnavailable, inputFreshness:workspaceInputFreshness, retired,
        view: workspaceHomeView, project: workspaceProject, focusKey: workspaceFocus, storageError: workspaceStorageError, error: workspaceNotice || null, tasks: [...workspaceTasks.values()].map(task => {
          const dependsOn = workspaceDependencyEdges(task.depends_on);
          const assets = workspaceAssetSummary(task.input_summary);
          return {key: task.key, title: task.title, project: task.project, kind: task.kind, fileKey: task.fileKey || null, pageId: task.pageId || null, threadId: task.threadId || null, revision: task.revision || '', preview: workspacePreview(task), paired: task.paired === true, productionAdmitted: task.productionAdmitted === true, has_input_record:task.has_input_record === true, ...(dependsOn ? {depends_on: dependsOn} : {}), ...(assets ? {input_summary: assets} : {})};
        })});
      return;
    }
    if (!['workspace-open', 'workspace-chat-open'].includes(message.type) || message.workspaceSession !== workspaceHomeSession) return;
    const task = workspaceTasks.get(message.key);
    if (!task) return;
    if (task.fileKey && task.fileKey !== figma.fileKey) {
      workspaceNotice = '이 작업은 지정된 Design 파일에서만 열 수 있습니다.';
      figma.ui.postMessage({type: 'workspace-error', workspaceSession: workspaceHomeSession, message: workspaceNotice});
      return;
    }
    await workspaceOpen(task, message.type === 'workspace-chat-open' ? 'chat' : 'task');
    return;
  }
  const current = workspaceActive;
  if (message.workspaceSession !== current.session) return;
  if (message.type === 'workspace-back' || message.type === 'workspace-history') {
    workspaceHome('', message.type === 'workspace-history' ? 'history' : 'tasks', current.task.project || null, current.task.key); return;
  }
  if (message.type === 'workspace-download') {workspaceRecord(current, 'download', 'requested'); return;}
  if (message.type === 'workspace-navigation-ready') {workspaceControl(current); return;}
  if (message.type === 'workspace-chat') {
    if (current.view === 'chat') return;
    if (current.task.threadId) await workspaceOpen(current.task, 'chat');
    else workspaceHome('', 'codex', current.task.project || null, current.task.key);
    return;
  }
  if (message.type !== 'workspace-task-message' || !current.handler) return;
  if (current.view === 'chat' && message.payload?.type === 'chat:back') {workspaceHome(); return;}
  if (current.task.fileKey && current.task.fileKey !== figma.fileKey) return;
  if (['workspace-carousel-select','workspace-carousel-present'].includes(message.payload?.type)) {
    const request = {...message.payload, action:message.payload.type === 'workspace-carousel-present' ? 'present' : 'select'};
    try { await workspaceSelectCarousel(current, request); }
    catch (error) { figma.ui.postMessage({workspaceSession:current.session,
      payload:{type:'workspace-carousel-error', message:String(error.message || error)}}); }
    return;
  }
  const operation = message.payload?.type;
  if (workspaceOperations.has(operation) && workspaceBusy(current)) return;
  if (workspaceOperations.has(operation)) {current.executionId = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12); current.operation = operation; current.outcome = null; current.started = false; current.verificationRecorded = false; workspaceRecord(current, operation, 'requested');}
  if (!workspaceOperations.has(operation) && operation !== 'receipt') {current.operation = null; current.outcome = null;}
  if (operation === 'receipt' && current.operation === 'draft-review' && current.outcome === 'readback' && !current.verificationRecorded) {
    current.verificationRecorded = true; workspaceRecord(current, 'verification', message.payload.passed === true ? 'verified' : 'failed');
    current.operation = 'verification'; current.outcome = message.payload.passed === true ? 'verified' : 'failed';
  }
  current.inFlight++;
  workspaceControl(current);
  try {
    await current.handler(message.payload);
    if (workspaceOperations.has(operation) && !current.outcome && current.started && operation === 'import') workspaceRecord(current, operation, 'finished');
  }
  catch (error) {
    if (current.outcome !== 'failed') workspaceRecord(current, workspaceOperations.has(operation) ? operation : current.operation, 'failed');
    current.outcome = 'failed';
    if (workspaceCurrent(current)) figma.ui.postMessage({workspaceSession: current.session,
      workspaceControl: true, busy: false, error: String(error.message || error)});
  } finally {
    current.inFlight--;
    workspaceControl(current);
  }
}
let workspaceLoaded;
if (typeof workspaceRecipeDispatch !== 'function' || !workspaceRecipeDispatch()) {
  workspaceLoaded = workspaceLoadState();
  figma.ui.onmessage = workspaceOnMessage;
  if (typeof figma !== 'undefined' && typeof figma.on === 'function') {
    try { figma.on('currentpagechange', () => workspaceHandleScopeChange()); } catch (_) {}
  }
  workspaceHome();
}
