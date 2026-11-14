export const OPERATION_DETAIL_SCHEMA = 'figma-flow-operation-detail-v1';
export const MAX_DIFF_ROWS = 200;
export const MAX_CONFLICT_ROWS = 50;

export const DETAIL_PROTOCOL = Object.freeze({
  requestType: 'workspace-history-detail',
  resultType: 'workspace-history-detail-result',
  scopeChangedType: 'workspace-scope-changed',
});

const ALLOWED_RESULT_STATUSES = new Set(['ok', 'unavailable', 'scope-changed', 'error']);
const ALLOWED_CLASSIFICATIONS = new Set(['recorded', 'legacy', 'unknown']);
const ALLOWED_OPERATION_STATES = new Set(['ok', 'pending', 'claimed', 'error', 'uncertain', 'expired']);
const ALLOWED_PHASES = new Set([
  'queued',
  'claimed',
  'native-started',
  'result-received',
  'reconciled',
  'uncertain',
  'unknown',
]);
const ALLOWED_RELATION_TYPES = new Set(['declared-dependency', 'recovery-of', 'artifact-input']);
const ALLOWED_RELATION_DIRECTIONS = Object.freeze({
  'declared-dependency': new Set(['predecessor', 'successor']),
  'recovery-of': new Set(['recovers', 'recovered-by']),
});
const ALLOWED_REVISION_BINDINGS = new Set(['current', 'pinned-historical', 'retired', 'orphan', 'unknown']);
const ALLOWED_DIFF_STATUSES = new Set(['available', 'empty', 'unavailable']);
const ALLOWED_DIFF_KINDS = new Set(['changed', 'added', 'removed', 'type-changed']);
const ALLOWED_RAW_DESIGN_FIELDS = new Set([
  'value',
  'backgroundColor',
  'color',
  'borderColor',
  'fill',
  'stroke',
  'fontSize',
  'fontFamily',
  'fontWeight',
  'lineHeight',
  'letterSpacing',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'gap',
  'itemSpacing',
  'cornerRadius',
  'borderRadius',
  'opacity',
  'width',
  'height',
  'visible',
  'boolean',
  'variant',
  'instanceSwap',
]);
const TEXT_CONTENT_FIELDS = new Set([
  'characters',
  'text',
  'rawText',
  'textContent',
  'label',
  'title',
  'name',
  'placeholder',
  'copy',
  'content',
  'caption',
  'description',
  'alt',
]);

const SECRET_QUERY =
  /([?&](?:access_token|refresh_token|id_token|sync_token|local_sync_token|chat_token|token|api_key|apikey|key|secret|password|capability|bearer|auth)=)[^&#\s"'<>]*/gi;
const HOME_PATH = /(?:\/Users\/[^/\s"'<>]+|\/home\/[^/\s"'<>]+|[A-Za-z]:\\Users\\[^\\/\s"'<>]+)/g;

export function redactDetailText(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/([a-z][a-z0-9+.-]*:\/\/)[^/\s"'<>]+@/gi, '$1')
    .replace(HOME_PATH, '[home]')
    .replace(SECRET_QUERY, '$1[redacted]')
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]{6,}/g, 'Bearer [redacted]');
}

function cleanString(value, maxLen = 200) {
  return typeof value === 'string' ? redactDetailText(value).slice(0, maxLen) : '';
}

export function safeRevision(value) {
  if (typeof value !== 'string') return '';
  const trimmed = value.trim();
  return /^[a-f0-9]{64}$/i.test(trimmed) ? trimmed.toLowerCase() : '';
}

export function safeOperationId(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return /^[a-f0-9]{32}$/i.test(trimmed) ? trimmed.toLowerCase() : null;
}

export function normalizeRuntimeGeneration(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return null;
    if (/^[a-f0-9]{32}$/i.test(trimmed)) return trimmed.toLowerCase();
    return cleanString(trimmed, 128) || null;
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    if (typeof value.generation === 'string' && value.generation.trim()) {
      const gen = value.generation.trim();
      return /^[a-f0-9]{32}$/i.test(gen) ? gen.toLowerCase() : cleanString(gen, 128) || null;
    }
  }
  return null;
}

export function buildDetailScope(model = {}, workspaceSession = null) {
  return {
    workspaceSession: typeof workspaceSession === 'string' && workspaceSession ? workspaceSession : null,
    fileKey: typeof model.fileKey === 'string' && model.fileKey ? model.fileKey : null,
    pageId: typeof model.pageId === 'string' && model.pageId ? model.pageId : null,
    runtimeGeneration: normalizeRuntimeGeneration(
      model.runtimeGeneration ?? model.scope?.runtimeGeneration ?? model.runtime,
    ),
  };
}

export function scopesMatch(left, right) {
  if (!left || !right) return false;
  if ((left.workspaceSession || null) !== (right.workspaceSession || null)) return false;
  if ((left.fileKey || null) !== (right.fileKey || null)) return false;
  if ((left.pageId || null) !== (right.pageId || null)) return false;
  if (left.runtimeGeneration && right.runtimeGeneration && left.runtimeGeneration !== right.runtimeGeneration) {
    return false;
  }
  return true;
}

export function isDetailResponseStale(pendingRequest, message, currentScope) {
  if (!pendingRequest || !message || typeof message !== 'object') return true;
  if (message.type !== DETAIL_PROTOCOL.resultType) return true;
  if (!scopesMatch(pendingRequest.scope, currentScope)) return true;
  if (!message.workspaceSession || message.workspaceSession !== currentScope?.workspaceSession) return true;
  if (pendingRequest.requestId && message.requestId !== pendingRequest.requestId) return true;
  if (safeOperationId(message.operationId) !== pendingRequest.operationId) return true;
  if (!ALLOWED_RESULT_STATUSES.has(message.status)) return true;

  const expectedRevision = safeRevision(pendingRequest.revision);
  if (pendingRequest.taskKey && message.taskKey !== undefined && message.taskKey !== pendingRequest.taskKey) {
    return true;
  }
  if (expectedRevision && message.revision !== undefined && safeRevision(message.revision) !== expectedRevision) {
    return true;
  }

  if (message.status === 'ok') {
    const detail = message.detail;
    if (!detail || typeof detail !== 'object') return true;
    if (detail.schema !== OPERATION_DETAIL_SCHEMA) return true;
    if (safeOperationId(detail.operationId) !== pendingRequest.operationId) return true;
    const detailScope = detail.scope;
    if (!detailScope || typeof detailScope !== 'object') return true;
    if (typeof detailScope.fileKey !== 'string' || !detailScope.fileKey) return true;
    if (typeof detailScope.pageId !== 'string' || !detailScope.pageId) return true;
    if (detailScope.fileKey !== (currentScope?.fileKey || null)) return true;
    if (detailScope.pageId !== (currentScope?.pageId || null)) return true;
    const detailRuntimeGen = normalizeRuntimeGeneration(detailScope.runtimeGeneration);
    if (currentScope?.runtimeGeneration && detailRuntimeGen !== currentScope.runtimeGeneration) {
      return true;
    }
    if (pendingRequest.taskKey && detail.task?.key !== pendingRequest.taskKey) return true;
    if (expectedRevision && safeRevision(detail.task?.revision) !== expectedRevision) return true;
  }

  return false;
}

function isRgbaObject(value) {
  return (
    Boolean(value) &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    typeof value.r === 'number' &&
    typeof value.g === 'number' &&
    typeof value.b === 'number' &&
    (value.a === undefined || typeof value.a === 'number')
  );
}

function formatDesignValue(value, fieldIsTextField, allowRawString) {
  if (value === undefined) return { isText: false, textLength: null, text: '' };
  if (value === null) return { isText: false, textLength: null, text: 'null' };
  if (typeof value === 'object' && !Array.isArray(value) && value.valueType === 'text') {
    return {
      isText: true,
      textLength: Number.isFinite(value.length) ? value.length : null,
      text: '',
    };
  }
  if (fieldIsTextField) {
    return {
      isText: true,
      textLength: typeof value === 'string' ? value.length : Number.isFinite(value) ? value : null,
      text: '',
    };
  }
  if (isRgbaObject(value)) {
    const a = typeof value.a === 'number' ? value.a : 1;
    return {
      isText: false,
      textLength: null,
      text: `rgba(${value.r}, ${value.g}, ${value.b}, ${a})`,
    };
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return { isText: false, textLength: null, text: String(value) };
  }
  if (typeof value === 'string') {
    if (!allowRawString) {
      return { isText: true, textLength: value.length, text: '' };
    }
    return { isText: false, textLength: null, text: cleanString(value, 160) };
  }
  return { isText: true, textLength: null, text: '' };
}

function normalizeDiffRow(row) {
  if (!row || typeof row !== 'object') return null;
  const key = cleanString(row.key || '', 200);
  const field = cleanString(row.field || '', 80);
  if (!key && !field) return null;
  const fieldIsTextField = TEXT_CONTENT_FIELDS.has(field);
  const allowRawString = ALLOWED_RAW_DESIGN_FIELDS.has(field);
  const before = formatDesignValue(row.before, fieldIsTextField, allowRawString);
  const after = formatDesignValue(row.after, fieldIsTextField, allowRawString);
  const kind = ALLOWED_DIFF_KINDS.has(row.kind) ? row.kind : 'unknown';
  const isText = Boolean(before.isText || after.isText || fieldIsTextField);
  return {
    key,
    field,
    kind,
    isText,
    before: before.text,
    after: after.text,
    textLengthBefore: isText ? before.textLength : null,
    textLengthAfter: isText ? after.textLength : null,
  };
}

function normalizeConflictRow(row) {
  if (!row || typeof row !== 'object') return null;
  const key = cleanString(row.key || '', 200);
  const field = cleanString(row.field || '', 80);
  if (!key && !field) return null;
  const fieldIsTextField = TEXT_CONTENT_FIELDS.has(field);
  const allowRawString = ALLOWED_RAW_DESIGN_FIELDS.has(field);
  const expectedBefore = formatDesignValue(row.expectedBefore, fieldIsTextField, allowRawString);
  const plannedAfter = formatDesignValue(row.plannedAfter, fieldIsTextField, allowRawString);
  const observed = formatDesignValue(row.observed, fieldIsTextField, allowRawString);
  return {
    key,
    scope: row.scope === 'variable' ? 'variable' : row.scope === 'node' ? 'node' : cleanString(row.scope || '', 40),
    field,
    reasonCode: cleanString(row.reasonCode || '', 80),
    planSha256: safeRevision(row.planSha256),
    expectedBefore: expectedBefore.isText ? { isText: true, length: expectedBefore.textLength } : { isText: false, text: expectedBefore.text },
    plannedAfter: plannedAfter.isText ? { isText: true, length: plannedAfter.textLength } : { isText: false, text: plannedAfter.text },
    observed: observed.isText ? { isText: true, length: observed.textLength } : { isText: false, text: observed.text },
  };
}

function normalizeDiff(rawDiff, classification, topTruncated) {
  if (classification !== 'recorded') {
    return {
      status: 'unavailable',
      reason: classification === 'legacy' ? 'legacy-record' : 'unknown-record',
      basis: null,
      beforeRevision: null,
      afterRevision: null,
      truncated: false,
      totalFields: 0,
      fields: [],
      conflicts: [],
    };
  }
  if (!rawDiff || typeof rawDiff !== 'object') {
    return {
      status: 'unavailable',
      reason: 'unavailable',
      basis: null,
      beforeRevision: null,
      afterRevision: null,
      truncated: Boolean(topTruncated),
      totalFields: 0,
      fields: [],
      conflicts: [],
    };
  }
  const status = ALLOWED_DIFF_STATUSES.has(rawDiff.status) ? rawDiff.status : 'unavailable';
  const conflicts = Array.isArray(rawDiff.conflicts)
    ? rawDiff.conflicts.slice(0, MAX_CONFLICT_ROWS).map(normalizeConflictRow).filter(Boolean)
    : [];
  if (status === 'unavailable') {
    return {
      status: 'unavailable',
      reason: cleanString(rawDiff.reason || 'unavailable', 120) || 'unavailable',
      basis: cleanString(rawDiff.basis || '', 60) || null,
      beforeRevision: safeRevision(rawDiff.beforeRevision) || null,
      afterRevision: safeRevision(rawDiff.afterRevision) || null,
      truncated: Boolean(topTruncated || rawDiff.truncated),
      totalFields: 0,
      fields: [],
      conflicts,
    };
  }
  const rawFields = Array.isArray(rawDiff.fields) ? rawDiff.fields : [];
  const fields = rawFields.slice(0, MAX_DIFF_ROWS).map(normalizeDiffRow).filter(Boolean);
  const totalFields = Number.isFinite(rawDiff.totalFields) ? rawDiff.totalFields : rawFields.length;
  return {
    status,
    reason: rawDiff.reason ? cleanString(rawDiff.reason, 120) : null,
    basis: cleanString(rawDiff.basis || '', 60) || null,
    beforeRevision: safeRevision(rawDiff.beforeRevision) || null,
    afterRevision: safeRevision(rawDiff.afterRevision) || null,
    truncated: Boolean(topTruncated || rawDiff.truncated || rawFields.length > MAX_DIFF_ROWS),
    totalFields,
    fields,
    conflicts,
  };
}

function resolveRevisionBinding(rawBinding, taskKey, revision, tasksByKey, retiredByKey) {
  if (ALLOWED_REVISION_BINDINGS.has(rawBinding)) return rawBinding;
  if (!taskKey || !revision) return 'unknown';
  const active = tasksByKey.get(taskKey);
  if (active) return active.revision === revision ? 'current' : 'pinned-historical';
  if (retiredByKey.has(taskKey)) return 'retired';
  return 'orphan';
}

function normalizeRelations(rawRelations, tasksByKey, retiredByKey) {
  if (!Array.isArray(rawRelations)) return [];
  const list = [];
  for (const rel of rawRelations) {
    if (!rel || typeof rel !== 'object' || !ALLOWED_RELATION_TYPES.has(rel.type)) continue;
    const allowedDirs = ALLOWED_RELATION_DIRECTIONS[rel.type];
    const direction = typeof rel.direction === 'string' ? rel.direction : '';
    if (allowedDirs && !allowedDirs.has(direction)) continue;
    const taskKey = cleanString(rel.taskKey || '', 200);
    const revision = safeRevision(rel.revision);
    const currentRevision =
      safeRevision(rel.currentRevision) || (taskKey ? tasksByKey.get(taskKey)?.revision || retiredByKey.get(taskKey) || null : null);
    const revisionBinding = resolveRevisionBinding(rel.revisionBinding, taskKey, revision, tasksByKey, retiredByKey);
    const linkedOperationId =
      rel.type === 'declared-dependency'
        ? safeOperationId(rel.targetOperationId)
        : rel.type === 'recovery-of'
          ? safeOperationId(rel.operationId)
          : null;
    list.push({
      type: rel.type,
      direction: allowedDirs ? direction : cleanString(direction, 40),
      taskKey,
      title: taskKey ? tasksByKey.get(taskKey)?.title || taskKey : '',
      revision,
      currentRevision,
      revisionBinding,
      artifact: cleanString(rel.artifact || '', 120),
      artifactSha256: safeRevision(rel.artifactSha256),
      freshness: cleanString(rel.freshness || '', 40),
      linkedOperationId,
    });
  }
  return list;
}

export function normalizeDetailDto(rawDetail, currentScope = null, tasks = [], retired = []) {
  const tasksByKey = new Map((Array.isArray(tasks) ? tasks : []).filter((t) => t?.key).map((t) => [t.key, t]));
  const retiredByKey = new Map(
    (Array.isArray(retired) ? retired : []).filter((r) => r?.key && r?.revision).map((r) => [r.key, r.revision]),
  );

  const validSchema = rawDetail && typeof rawDetail === 'object' && rawDetail.schema === OPERATION_DETAIL_SCHEMA;
  const classification = validSchema && ALLOWED_CLASSIFICATIONS.has(rawDetail.classification) ? rawDetail.classification : 'unknown';

  const operationId = safeOperationId(rawDetail?.operationId);
  const scope = {
    workspaceSession: currentScope?.workspaceSession || null,
    fileKey: cleanString(rawDetail?.scope?.fileKey || '', 120) || currentScope?.fileKey || null,
    pageId: cleanString(rawDetail?.scope?.pageId || '', 120) || currentScope?.pageId || null,
    runtimeGeneration:
      normalizeRuntimeGeneration(rawDetail?.scope?.runtimeGeneration) || currentScope?.runtimeGeneration || null,
  };

  const operation = classification === 'unknown' ? '' : cleanString(rawDetail?.operation || '', 40);
  const state = ALLOWED_OPERATION_STATES.has(rawDetail?.state) ? rawDetail.state : 'unknown';

  const phases =
    classification === 'recorded' && Array.isArray(rawDetail?.phases)
      ? rawDetail.phases
          .filter((item) => item && typeof item === 'object' && ALLOWED_PHASES.has(item.phase))
          .map((item) => ({
            phase: item.phase,
            time: typeof item.time === 'string' && item.time.length <= 40 ? item.time : '',
          }))
      : [];
  const phase =
    classification === 'recorded'
      ? ALLOWED_PHASES.has(rawDetail?.phase)
        ? rawDetail.phase
        : phases.at(-1)?.phase || 'unknown'
      : 'unknown';

  const rawTask = rawDetail?.task && typeof rawDetail.task === 'object' ? rawDetail.task : null;
  const taskKey = classification === 'unknown' ? '' : cleanString(rawTask?.key || '', 200);
  const revision = classification === 'unknown' ? '' : safeRevision(rawTask?.revision);
  const currentRevision =
    classification === 'unknown'
      ? null
      : safeRevision(rawTask?.currentRevision) || tasksByKey.get(taskKey)?.revision || retiredByKey.get(taskKey) || null;
  const revisionBinding =
    classification === 'unknown'
      ? 'unknown'
      : resolveRevisionBinding(rawTask?.revisionBinding, taskKey, revision, tasksByKey, retiredByKey);

  const task = {
    key: taskKey,
    revision,
    currentRevision,
    revisionBinding,
    kind: classification === 'unknown' ? '' : cleanString(rawTask?.kind || '', 40),
  };

  const failure =
    rawDetail?.failure && typeof rawDetail.failure === 'object'
      ? {
          code: cleanString(rawDetail.failure.code || '', 60),
          action: cleanString(rawDetail.failure.action || '', 60),
        }
      : null;

  const relations = classification === 'recorded' ? normalizeRelations(rawDetail?.relations, tasksByKey, retiredByKey) : [];
  const diff = normalizeDiff(rawDetail?.diff, classification, Boolean(rawDetail?.truncated));
  const truncated = Boolean(rawDetail?.truncated || diff.truncated);
  const scopeNotice =
    rawDetail?.scopeNotice === 'read-only-truncated-256kib' ? 'read-only-truncated-256kib' : 'read-only-exact-scope';

  return {
    schema: OPERATION_DETAIL_SCHEMA,
    readOnly: true,
    operationId,
    scope,
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
  };
}

export function normalizeDetailResult(envelope, currentScope = null, tasks = [], retired = []) {
  const status = envelope?.status;
  if (status === 'scope-changed') {
    return {
      status: 'scope-changed',
      reason: 'scope-changed',
      operationId: safeOperationId(envelope?.operationId),
      detail: null,
      scope: currentScope,
    };
  }
  if (status === 'unavailable') {
    return {
      status: 'unavailable',
      reason: cleanString(envelope?.reason || 'control-unavailable', 80) || 'control-unavailable',
      operationId: safeOperationId(envelope?.operationId),
      detail: null,
      scope: currentScope,
    };
  }
  if (status === 'error') {
    return {
      status: 'error',
      reason: cleanString(envelope?.reason || 'request-rejected', 80) || 'request-rejected',
      operationId: safeOperationId(envelope?.operationId),
      detail: null,
      scope: currentScope,
    };
  }
  if (status === 'ok') {
    const detail = normalizeDetailDto(envelope?.detail, currentScope, tasks, retired);
    return {
      status: 'ok',
      reason: null,
      operationId: detail.operationId,
      detail,
      scope: detail.scope,
    };
  }
  return {
    status: 'error',
    reason: 'invalid-envelope',
    operationId: safeOperationId(envelope?.operationId),
    detail: null,
    scope: currentScope,
  };
}
