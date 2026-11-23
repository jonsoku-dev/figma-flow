/* Bounded metadata feed for native Design edits. Never serializes node content. */
const WORKSPACE_CHANGE_MAX_EVENTS = 256;
const WORKSPACE_CHANGE_MAX_BATCH = 64;
const WORKSPACE_CHANGE_PROPERTIES = new Set(WORKSPACE_PROFILE_POLICY.nodeChangeProperties);
const WORKSPACE_CHANGE_PROBE_FIELDS = Object.entries(WORKSPACE_PROFILE_POLICY.inspectFields)
  .filter(([field, kind]) => kind !== 'text' && field !== 'name' && WORKSPACE_CHANGE_PROPERTIES.has(field))
  .map(([field]) => field);
const WORKSPACE_CHANGE_ECHO_WINDOW_MS = 2000;
function workspaceChangeRandomEpoch() {
  let value = '';
  while (value.length < 32) value += Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0');
  return value.slice(0, 32);
}
function sameWorkspaceChangeScope(a, b) {
  return !!a && !!b && a.file_key === b.file_key && a.page_id === b.page_id &&
    a.generation === b.generation && a.session_id === b.session_id;
}
function workspaceChangedNodeId(change) {
  return change?.id ?? change?.node?.id;
}
function createWorkspaceChangeFeed(options = {}) {
  const maxEvents = Number.isInteger(options.maxEvents) ? Math.max(1, Math.min(1024, options.maxEvents)) : WORKSPACE_CHANGE_MAX_EVENTS;
  const maxBatch = Number.isInteger(options.maxBatch) ? Math.max(1, Math.min(128, options.maxBatch)) : WORKSPACE_CHANGE_MAX_BATCH;
  const randomEpoch = typeof options.randomEpoch === 'function' ? options.randomEpoch : workspaceChangeRandomEpoch;
  let scope = null, epoch = null, nextSeq = 0, acceptedSeq = 0, events = [], lostFrom = null, lostTo = null;
  function reset(nextScope) {
    if (!nextScope || typeof nextScope.file_key !== 'string' || typeof nextScope.page_id !== 'string' ||
        typeof nextScope.generation !== 'string' || typeof nextScope.session_id !== 'string') {
      scope = null; epoch = null; nextSeq = acceptedSeq = 0; events = []; lostFrom = lostTo = null;
      return;
    }
    if (sameWorkspaceChangeScope(scope, nextScope)) return;
    scope = {file_key:nextScope.file_key, page_id:nextScope.page_id, generation:nextScope.generation, session_id:nextScope.session_id};
    epoch = randomEpoch(); nextSeq = acceptedSeq = 0; events = []; lostFrom = lostTo = null;
  }
  function record(change) {
    const nodeId = workspaceChangedNodeId(change);
    if (!scope || !change || typeof nodeId !== 'string' || !/^[A-Za-z0-9:;_-]{1,160}$/.test(nodeId) ||
        !['CREATE','DELETE','PROPERTY_CHANGE'].includes(change.type)) return false;
    const propertyNames = change.type === 'PROPERTY_CHANGE' && Array.isArray(change.properties)
      ? [...new Set(change.properties.filter(value => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(value)))].sort()
      : [];
    const allProperties = propertyNames.filter(value => WORKSPACE_CHANGE_PROPERTIES.has(value));
    const allUnknownProperties = propertyNames.filter(value => !WORKSPACE_CHANGE_PROPERTIES.has(value));
    const properties = allProperties.slice(0,32);
    const unknownProperties = allUnknownProperties.slice(0,Math.max(0,32-properties.length));
    const event = {seq:++nextSeq, node_id:nodeId, type:change.type, properties,
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
    if (!sameWorkspaceChangeScope(scope, expectedScope)) return null;
    if (!['available','unavailable'].includes(status)) status = 'unavailable';
    const included = status === 'available' ? events.slice(0,maxBatch) : [];
    const cursorSeq = included.length ? included[included.length - 1].seq : acceptedSeq;
    return {scope:{...scope}, cursor:{epoch,seq:cursorSeq}, events:included
      .map(item=>({...item,properties:[...item.properties],unknown_properties:[...item.unknown_properties]})),
      gap:status === 'available' && lostFrom !== null ? {from:lostFrom,to:lostTo} : null, status,
      ...(status === 'unavailable' ? {reason:'page-listener-unavailable'} : {})};
  }
  function acknowledge(reply, expectedScope) {
    if (!reply || !sameWorkspaceChangeScope(scope, expectedScope) || !sameWorkspaceChangeScope(scope, reply.scope) || reply.status !== 'available' ||
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
      const key = JSON.stringify([workspaceChangedNodeId(change),change?.type,propertyNames]);
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
let workspaceChangeBinding = null, workspaceChangeFlushTimer = null;
var workspaceChangeFeedStatus = {status:'unavailable',reason:'page-listener-unavailable'};
function workspaceChangeScope() {
  if (typeof figma === 'undefined' || !figma.fileKey || !figma.currentPage || !figma.currentPage.id ||
      typeof WORKSPACE_RUNTIME === 'undefined' || !WORKSPACE_RUNTIME?.generation || typeof controlRunSession !== 'string') return null;
  return {file_key:figma.fileKey,page_id:figma.currentPage.id,generation:WORKSPACE_RUNTIME.generation,session_id:controlRunSession};
}
function workspaceChangeProbeValue(node, field) {
  const observation = workspaceReadNodeField(node,field);
  return observation.unavailable ? undefined : JSON.stringify(observation.value);
}
function workspaceSampleSelectionChanges(seedOnly = false) {
  const binding = workspaceChangeBinding;
  if (!binding?.listener || !sameWorkspaceChangeScope(binding.scope,workspaceChangeScope()) ||
      typeof workspaceReadNodeField !== 'function' || typeof WORKSPACE_READ_LIMITS === 'undefined') return;
  let selection;
  try {selection = figma.currentPage.selection;} catch (_) {return;}
  if (!Array.isArray(selection)) return;
  const now = Date.now();
  const next = new Map();
  for (const node of selection.slice(0,WORKSPACE_READ_LIMITS.maxNodes)) {
    const previous = binding.selection.get(node.id);
    const fields = new Map(), echoes = new Map(), changed = [];
    for (const field of WORKSPACE_CHANGE_PROBE_FIELDS) {
      const value = workspaceChangeProbeValue(node,field);
      if (value === undefined) continue;
      const before = previous?.fields.get(field);
      if (!seedOnly && before !== undefined && before !== value) {
        changed.push(field);
        echoes.set(field, {value, until:now + WORKSPACE_CHANGE_ECHO_WINDOW_MS});
      } else {
        const echo = previous?.echoes.get(field);
        if (!seedOnly && echo && echo.until >= now) echoes.set(field,echo);
      }
      fields.set(field,value);
    }
    next.set(node.id,{node,fields,echoes});
    if (changed.length) binding.feed.record({id:node.id,type:'PROPERTY_CHANGE',properties:changed});
  }
  binding.selection = next;
}
function workspaceReconcileNativeChange(binding, change) {
  if (change?.type !== 'PROPERTY_CHANGE' || !Array.isArray(change.properties)) return change;
  const id = workspaceChangedNodeId(change), selected = binding.selection.get(id);
  if (!selected) return change;
  const properties = change.properties.filter(field => {
    if (!WORKSPACE_CHANGE_PROBE_FIELDS.includes(field)) return true;
    const value = workspaceChangeProbeValue(change.node ?? selected.node,field);
    const echo = selected.echoes.get(field);
    selected.echoes.delete(field);
    if (value === undefined) selected.fields.delete(field);
    else selected.fields.set(field,value);
    return !echo || echo.until < Date.now() || echo.value !== value;
  });
  return properties.length || !change.properties.length ? {id,type:change.type,properties} : null;
}
function workspaceBindChangePage() {
  const page = typeof figma === 'undefined' ? null : figma.currentPage;
  const scope = workspaceChangeScope();
  if (!scope || sameWorkspaceChangeScope(workspaceChangeBinding?.scope, scope)) return;
  const previous = workspaceChangeBinding;
  if (previous?.listener && typeof previous.page.off === 'function') {
    try {previous.page.off('nodechange', previous.listener);} catch (_) {}
  }
  const feed = workspaceChangeFeedForScope(scope);
  const binding = {scope, page, feed, listener:null, selection:new Map()};
  workspaceChangeBinding = binding;
  workspaceChangeFeed = feed;
  workspaceChangeFeedStatus = {status:'unavailable',reason:'page-listener-unavailable'};
  if (typeof page.on !== 'function') return;

  const isCurrent = () => workspaceChangeBinding === binding &&
    sameWorkspaceChangeScope(workspaceChangeScope(), scope);
  const retry = () => {
    if (workspaceChangeBinding !== binding) return;
    setTimeout(() => {
      if (workspaceChangeBinding !== binding) return;
      workspaceChangeBinding = null;
      return workspaceBindChangePage();
    },1000);
  };
  const subscribe = () => {
    if (!isCurrent()) {retry(); return;}
    const listener = event => {
      if (!isCurrent()) {workspaceBindChangePage(); return;}
      if (!Array.isArray(event?.nodeChanges) || !feed.recordMany(
        event.nodeChanges.map(change => workspaceReconcileNativeChange(binding,change)).filter(Boolean))) return;
      if (workspaceChangeFlushTimer !== null) clearTimeout(workspaceChangeFlushTimer);
      workspaceChangeFlushTimer = setTimeout(() => {
        workspaceChangeFlushTimer = null;
        if (typeof workspaceControlTick === 'function') workspaceControlTick();
      },80);
    };
    try {
      page.on('nodechange',listener);
      binding.listener = listener;
      workspaceChangeFeedStatus = {status:'available'};
      workspaceSampleSelectionChanges();
    } catch (_) {retry();}
  };
  if (typeof page.loadAsync !== 'function') return subscribe();
  return (async () => {
    try {await page.loadAsync();}
    catch (_) {retry(); return;}
    subscribe();
  })();
}
