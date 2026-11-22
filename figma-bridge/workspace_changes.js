/* Bounded metadata feed for native Design edits. Never serializes node content. */
const WORKSPACE_CHANGE_MAX_EVENTS = 256;
const WORKSPACE_CHANGE_MAX_BATCH = 64;
const WORKSPACE_CHANGE_PROPERTIES = new Set(WORKSPACE_PROFILE_POLICY.nodeChangeProperties);
function workspaceChangeRandomEpoch() {
  let value = '';
  while (value.length < 32) value += Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0');
  return value.slice(0, 32);
}
function createWorkspaceChangeFeed(options = {}) {
  const maxEvents = Number.isInteger(options.maxEvents) ? Math.max(1, Math.min(1024, options.maxEvents)) : WORKSPACE_CHANGE_MAX_EVENTS;
  const maxBatch = Number.isInteger(options.maxBatch) ? Math.max(1, Math.min(128, options.maxBatch)) : WORKSPACE_CHANGE_MAX_BATCH;
  const randomEpoch = typeof options.randomEpoch === 'function' ? options.randomEpoch : workspaceChangeRandomEpoch;
  let scope = null, epoch = null, nextSeq = 0, acceptedSeq = 0, events = [], lostFrom = null, lostTo = null;
  const sameScope = (a, b) => !!a && !!b && a.file_key === b.file_key && a.page_id === b.page_id &&
    a.generation === b.generation && a.session_id === b.session_id;
  function reset(nextScope) {
    if (!nextScope || typeof nextScope.file_key !== 'string' || typeof nextScope.page_id !== 'string' ||
        typeof nextScope.generation !== 'string' || typeof nextScope.session_id !== 'string') {
      scope = null; epoch = null; nextSeq = acceptedSeq = 0; events = []; lostFrom = lostTo = null;
      return;
    }
    if (sameScope(scope, nextScope)) return;
    scope = {file_key:nextScope.file_key, page_id:nextScope.page_id, generation:nextScope.generation, session_id:nextScope.session_id};
    epoch = randomEpoch(); nextSeq = acceptedSeq = 0; events = []; lostFrom = lostTo = null;
  }
  function record(change) {
    if (!scope || !change || typeof change.id !== 'string' || !/^[A-Za-z0-9:;_-]{1,160}$/.test(change.id) ||
        !['CREATE','DELETE','PROPERTY_CHANGE'].includes(change.type)) return false;
    const propertyNames = change.type === 'PROPERTY_CHANGE' && Array.isArray(change.properties)
      ? [...new Set(change.properties.filter(value => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(value)))].sort()
      : [];
    const allProperties = propertyNames.filter(value => WORKSPACE_CHANGE_PROPERTIES.has(value));
    const allUnknownProperties = propertyNames.filter(value => !WORKSPACE_CHANGE_PROPERTIES.has(value));
    const properties = allProperties.slice(0,32);
    const unknownProperties = allUnknownProperties.slice(0,Math.max(0,32-properties.length));
    const event = {seq:++nextSeq, node_id:change.id.slice(0, 160), type:change.type, properties,
      unknown_properties:unknownProperties, properties_truncated:allProperties.length + allUnknownProperties.length > 32,
      origin:'unknown'};
    events.push(event);
    if (events.length > maxEvents) {
      const removed = events.shift();
      if (removed.seq > acceptedSeq) {
        lostFrom = lostFrom === null ? removed.seq : Math.min(lostFrom, removed.seq);
        lostTo = Math.max(lostTo || 0, removed.seq);
      }
    }
    return true;
  }
  function batch(expectedScope, status = 'available') {
    if (!sameScope(scope, expectedScope)) return null;
    if (!['available','unavailable'].includes(status)) status = 'unavailable';
    const included = status === 'available' ? events.slice(0,maxBatch) : [];
    const cursorSeq = included.length ? included[included.length - 1].seq : acceptedSeq;
    return {scope:{...scope}, cursor:{epoch,seq:cursorSeq}, events:included
      .map(item=>({...item,properties:[...item.properties],unknown_properties:[...item.unknown_properties]})),
      gap:status === 'available' && lostFrom !== null ? {from:lostFrom,to:lostTo} : null, status,
      ...(status === 'unavailable' ? {reason:'page-listener-unavailable'} : {})};
  }
  function acknowledge(reply, expectedScope) {
    if (!reply || !sameScope(scope, expectedScope) || !sameScope(scope, reply.scope) || reply.status !== 'available' ||
        !reply.accepted_cursor || reply.accepted_cursor.epoch !== epoch || !Number.isInteger(reply.accepted_cursor.seq) ||
        reply.accepted_cursor.seq < acceptedSeq || reply.accepted_cursor.seq > nextSeq) return false;
    acceptedSeq = reply.accepted_cursor.seq;
    events = events.filter(item=>item.seq > acceptedSeq);
    if (lostFrom !== null && acceptedSeq >= lostTo) lostFrom = lostTo = null;
    return true;
  }
  function recordMany(changes) {
    const seen = new Set(); let count = 0;
    for (const change of Array.isArray(changes) ? changes : []) {
      const propertyNames = Array.isArray(change?.properties) ? [...new Set(change.properties)].sort() : [];
      const key = JSON.stringify([change?.id,change?.type,propertyNames]);
      if (seen.has(key)) continue;
      seen.add(key); if (record(change)) count++;
    }
    return count;
  }
  return {reset,record,recordMany,batch,acknowledge,getState:()=>({scope:scope&&{...scope},epoch,nextSeq,acceptedSeq,pending:events.length,gap:lostFrom===null?null:{from:lostFrom,to:lostTo}})};
}
var workspaceChangeFeed = createWorkspaceChangeFeed();
const workspaceChangeFeedCache = new Map();
function workspaceChangeFeedForScope(nextScope) {
  if (!nextScope) return workspaceChangeFeed;
  const key = JSON.stringify([nextScope.file_key,nextScope.page_id,nextScope.generation,nextScope.session_id]);
  let feed = workspaceChangeFeedCache.get(key);
  if (!feed) {
    feed = createWorkspaceChangeFeed(); workspaceChangeFeedCache.set(key,feed);
    while (workspaceChangeFeedCache.size > 16) workspaceChangeFeedCache.delete(workspaceChangeFeedCache.keys().next().value);
  } else {
    workspaceChangeFeedCache.delete(key); workspaceChangeFeedCache.set(key,feed);
  }
  feed.reset(nextScope);
  return feed;
}
let workspaceChangePage = null, workspaceChangeListener = null, workspaceChangeFlushTimer = null, workspaceChangeRetryTimer = null;
var workspaceChangeFeedStatus = {status:'unavailable',reason:'page-listener-unavailable'};
function workspaceChangeScope() {
  if (typeof figma === 'undefined' || !figma.fileKey || !figma.currentPage || !figma.currentPage.id ||
      typeof WORKSPACE_RUNTIME === 'undefined' || !WORKSPACE_RUNTIME?.generation || typeof controlRunSession !== 'string') return null;
  return {file_key:figma.fileKey,page_id:figma.currentPage.id,generation:WORKSPACE_RUNTIME.generation,session_id:controlRunSession};
}
function workspaceBindChangePage() {
  const page = typeof figma === 'undefined' ? null : figma.currentPage;
  const scope = workspaceChangeScope();
  if (workspaceChangePage === page && workspaceChangeListener) {
    workspaceChangeFeed = workspaceChangeFeedForScope(scope);
    workspaceChangeFeedStatus = {status:'available'};
    return;
  }
  if (workspaceChangePage && workspaceChangeListener && typeof workspaceChangePage.off === 'function') {
    try {workspaceChangePage.off('nodechange',workspaceChangeListener);} catch (_) {}
  }
  workspaceChangePage = page; workspaceChangeListener = null;
  workspaceChangeFeed = workspaceChangeFeedForScope(scope);
  if (!page || typeof page.on !== 'function') {
    workspaceChangeFeedStatus = {status:'unavailable',reason:'page-listener-unavailable'};
    return; // A page without the subscription API cannot be repaired by loading it again.
  }
  workspaceChangeListener = event => {
    if (figma.currentPage !== page) {workspaceBindChangePage(); return;}
    const scope = workspaceChangeScope();
    workspaceChangeFeed = workspaceChangeFeedForScope(scope);
    workspaceChangeFeed.recordMany(event?.nodeChanges);
    if (workspaceChangeFlushTimer !== null) clearTimeout(workspaceChangeFlushTimer);
    workspaceChangeFlushTimer = setTimeout(() => {
      workspaceChangeFlushTimer = null;
      if (typeof workspaceControlTick === 'function') workspaceControlTick();
    },80);
  };
  try {
    page.on('nodechange',workspaceChangeListener);
    workspaceChangeFeedStatus = {status:'available'};
  } catch (_) {
    workspaceChangeListener = null;
    workspaceChangeFeedStatus = {status:'unavailable',reason:'page-listener-unavailable'};
    workspaceScheduleChangeBindRetry(page);
  }
}
function workspaceScheduleChangeBindRetry(page) {
  if (workspaceChangeRetryTimer !== null || typeof setTimeout !== 'function') return;
  workspaceChangeRetryTimer = setTimeout(async () => {
    workspaceChangeRetryTimer = null;
    const current = typeof figma === 'undefined' ? null : figma.currentPage;
    if (current !== page) {workspaceBindChangePage(); return;}
    if (page && typeof page.loadAsync === 'function') {
      try {await page.loadAsync();} catch (_) {}
    }
    if (typeof figma !== 'undefined' && figma.currentPage === page) workspaceBindChangePage();
  },1000);
}
