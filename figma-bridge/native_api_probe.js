const NATIVE_API_PROBE_MAX_TARGETS = 12;
const NATIVE_API_PROBE_MAX_GETTERS = 192;
const NATIVE_API_PROBE_MAX_ELAPSED_MS = 1500;
const NATIVE_API_PROBE_MAX_ANCESTORS = 32;
const NATIVE_API_PROBE_STATUSES = ['success', 'unavailable', 'unsupported', 'blocked'];
const NATIVE_API_PROBE_METHODS = {
  getCSSAsync: {foundation: 'css', value_kind: 'css-summary'},
  getRangeFontName: {foundation: 'text-style', value_kind: 'font-range'},
  getRangeFontSize: {foundation: 'text-style', value_kind: 'font-size-range'},
  getRangeFills: {foundation: 'text-style', value_kind: 'solid-paints'},
};

function nativeProbeFinite(value, minimum = -1000000, maximum = 1000000) {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum;
}

function nativeProbeRound(value) {
  return Math.round(value * 10000) / 10000;
}

function nativeProbeColor(value) {
  if (!value || typeof value !== 'object'
      || !nativeProbeFinite(value.r, 0, 1) || !nativeProbeFinite(value.g, 0, 1)
      || !nativeProbeFinite(value.b, 0, 1)) return null;
  return {r: nativeProbeRound(value.r), g: nativeProbeRound(value.g), b: nativeProbeRound(value.b)};
}

function nativeProbeCssSummary(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {ok: false};
  const entries = Object.entries(value);
  if (entries.length > 96 || entries.some(([key, item]) => typeof key !== 'string'
      || key.length > 80 || typeof item !== 'string' || item.length > 256)) return {ok: false};
  const numeric = new Set(['width', 'height', 'min-width', 'max-width', 'min-height', 'max-height',
    'top', 'right', 'bottom', 'left', 'font-size', 'line-height', 'border-radius', 'opacity',
    'gap', 'row-gap', 'column-gap', 'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left']);
  const colorProperties = new Set(['color', 'background-color', 'border-color', 'outline-color']);
  const enumValues = {
    display: ['block', 'flex', 'inline', 'inline-block', 'none'],
    position: ['static', 'relative', 'absolute', 'fixed'],
    'flex-direction': ['row', 'row-reverse', 'column', 'column-reverse'],
    'align-items': ['stretch', 'flex-start', 'flex-end', 'center', 'baseline'],
    'justify-content': ['normal', 'flex-start', 'flex-end', 'center', 'space-between', 'space-around', 'space-evenly'],
    overflow: ['visible', 'hidden', 'clip', 'scroll', 'auto'],
    'box-sizing': ['content-box', 'border-box'],
    'text-align': ['left', 'right', 'center', 'justify', 'start', 'end'],
  };
  const projected = {};
  for (const [key, raw] of entries) {
    const valueText = raw.trim().toLowerCase();
    if (numeric.has(key)) {
      const match = /^(-?(?:\d+\.?\d*|\.\d+))(px|deg|%)?$/.exec(valueText);
      const amount = match ? Number(match[1]) : NaN;
      if (match && nativeProbeFinite(amount)) {
        projected[key] = {type: 'number', value: nativeProbeRound(amount), unit: match[2] || ''};
      }
    } else if (colorProperties.has(key)) {
      const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(valueText);
      if (hex) {
        const digits = hex[1].length === 3 ? [...hex[1]].map(char => char + char).join('') : hex[1];
        projected[key] = {type: 'SOLID', color: {r: nativeProbeRound(parseInt(digits.slice(0, 2), 16) / 255),
          g: nativeProbeRound(parseInt(digits.slice(2, 4), 16) / 255),
          b: nativeProbeRound(parseInt(digits.slice(4, 6), 16) / 255)}};
      }
    } else if (enumValues[key]?.includes(valueText)) {
      projected[key] = {type: 'enum', value: valueText.toUpperCase().replaceAll('-', '_')};
    }
  }
  return {ok: true, value: {propertyCount: entries.length, projected}};
}

function nativeProbeValue(kind, value, figma) {
  if (kind === 'css-summary') return nativeProbeCssSummary(value);
  if (kind === 'font-range') {
    if (value === figma.mixed) return {ok: true, value: {mixed: true}};
    if (!value || typeof value !== 'object' || Array.isArray(value)
        || typeof value.family !== 'string' || !/^[\p{L}\p{M}\p{N} .,'()+&_-]{1,96}$/u.test(value.family)
        || typeof value.style !== 'string' || !/^[\p{L}\p{M}\p{N} .,'()+&_-]{1,96}$/u.test(value.style)) return {ok: false};
    const result = {mixed: false, family: value.family, style: value.style};
    if (value.variationSettings !== undefined) {
      if (!value.variationSettings || typeof value.variationSettings !== 'object'
          || Array.isArray(value.variationSettings)) return {ok: false};
      const entries = Object.entries(value.variationSettings);
      if (entries.length > 12 || entries.some(([axis, amount]) => !/^[A-Za-z0-9]{4}$/.test(axis)
          || !nativeProbeFinite(amount, -100000, 100000))) return {ok: false};
      result.variationSettings = Object.fromEntries(entries.map(([axis, amount]) => [axis, nativeProbeRound(amount)]));
    }
    return {ok: true, value: result};
  }
  if (kind === 'font-size-range') {
    if (value === figma.mixed) return {ok: true, value: {mixed: true}};
    if (!nativeProbeFinite(value, 0, 10000)) return {ok: false};
    return {ok: true, value: {mixed: false, value: nativeProbeRound(value)}};
  }
  if (kind === 'boolean') return typeof value === 'boolean' ? {ok: true, value} : {ok: false};
  if (kind === 'number') {
    if (!nativeProbeFinite(value)) return {ok: false};
    return {ok: true, value: nativeProbeRound(value)};
  }
  if (kind === 'nullable-number') {
    if (value === null) return {ok: true, value: null};
    if (!nativeProbeFinite(value)) return {ok: false};
    return {ok: true, value: nativeProbeRound(value)};
  }
  if (kind === 'enum') {
    return typeof value === 'string' && /^[A-Z][A-Z0-9_:-]{0,63}$/.test(value)
      ? {ok: true, value} : {ok: false};
  }
  if (kind === 'rect') {
    if (!value || typeof value !== 'object'
        || !nativeProbeFinite(value.x) || !nativeProbeFinite(value.y)
        || !nativeProbeFinite(value.width, 0) || !nativeProbeFinite(value.height, 0)) return {ok: false};
    return {ok: true, value: {x: nativeProbeRound(value.x), y: nativeProbeRound(value.y),
      width: nativeProbeRound(value.width), height: nativeProbeRound(value.height)}};
  }
  if (kind === 'matrix') {
    if (!Array.isArray(value) || value.length !== 2
        || !value.every(row => Array.isArray(row) && row.length === 3
          && row.every(item => nativeProbeFinite(item)))) return {ok: false};
    return {ok: true, value: value.map(row => row.map(nativeProbeRound))};
  }
  if (kind === 'number-list') {
    if (!Array.isArray(value) || value.length > 16
        || !value.every(item => nativeProbeFinite(item, 0, 100000))) return {ok: false};
    return {ok: true, value: value.map(nativeProbeRound)};
  }
  if (kind === 'arc') {
    if (!value || typeof value !== 'object'
        || !nativeProbeFinite(value.startingAngle, -100, 100)
        || !nativeProbeFinite(value.endingAngle, -100, 100)
        || !nativeProbeFinite(value.innerRadius, 0, 1)) return {ok: false};
    return {ok: true, value: {startingAngle: nativeProbeRound(value.startingAngle),
      endingAngle: nativeProbeRound(value.endingAngle), innerRadius: nativeProbeRound(value.innerRadius)}};
  }
  if (kind === 'solid-paints') {
    if (!Array.isArray(value) || value.length > 32) return {ok: false};
    const colors = [];
    for (const paint of value) {
      if (!paint || typeof paint !== 'object' || paint.type !== 'SOLID') continue;
      const color = nativeProbeColor(paint.color);
      if (!color) continue;
      const row = {type: 'SOLID', color};
      if (paint.opacity !== undefined) {
        if (!nativeProbeFinite(paint.opacity, 0, 1)) continue;
        row.opacity = nativeProbeRound(paint.opacity);
      }
      if (paint.visible !== undefined) {
        if (typeof paint.visible !== 'boolean') continue;
        row.visible = paint.visible;
      }
      colors.push(row);
      if (colors.length === 8) break;
    }
    return colors.length ? {ok: true, value: colors} : {ok: false};
  }
  return {ok: false};
}

function nativeProbeId(value) {
  return typeof value === 'string' && /^(?:I?\d+:\d+)(?:;\d+:\d+)*$/.test(value);
}

function nativeProbeStatusCounts(observations) {
  return NATIVE_API_PROBE_STATUSES.reduce((counts, status) => {
    counts[status] = observations.filter(row => row.status === status).length;
    return counts;
  }, {});
}

function nativeProbeGraph(observations, targets, probeMeta, eligibleByType, eligibilityByType) {
  const nodes = [], edges = [], graphNodeIds = new Set();
  const addNode = node => { if (!graphNodeIds.has(node.id)) { graphNodeIds.add(node.id); nodes.push(node); } };
  const edgeIds = new Set();
  const addEdge = (from, to, type) => {
    const edgeId = JSON.stringify([from, to, type]);
    if (!edgeIds.has(edgeId)) { edgeIds.add(edgeId); edges.push({from, to, type}); }
  };
  const byObservation = new Map(observations.map(row => [`${row.semantic_id}\u0000${row.api_member_id}`, row]));
  for (const target of targets) {
    const targetId = `selected:${target.semantic_id}`;
    const typeId = `node-type:${target.observed_type}`;
    addNode({id: targetId, type: 'figma', title: 'Selected native node', status: 'observed',
      source: 'explicit observed-node selection', detail: JSON.stringify({semantic_id: target.semantic_id,
        observed_node_id: target.observed_node_id, observed_type: target.observed_type})});
    addNode({id: typeId, type: 'figma', title: `Figma node type ${target.observed_type}`, status: 'observed',
      source: `Figma Plugin API ${probeMeta.apiVersion}`, detail: JSON.stringify({node_type: target.observed_type})});
    addEdge(targetId, typeId, 'observed as');
    const eligibility = eligibilityByType[target.observed_type];
    for (const candidate of eligibleByType[target.observed_type] || []) {
      const memberId = `api-member:${candidate.api_member_id}`;
      const key = `${target.semantic_id}\u0000${candidate.api_member_id}`;
      const observation = byObservation.get(key);
      const observationId = `observation:${target.semantic_id}:${candidate.api_member_id}`;
      const status = observation?.status === 'success' ? 'observed'
        : observation?.status === 'blocked' ? 'blocked'
          : observation ? 'unverified' : 'planned';
      const detail = observation ? {semantic_id: observation.semantic_id,
        observed_node_id: observation.observed_node_id, observed_type: observation.observed_type,
        api_member_id: observation.api_member_id, property: observation.property,
        owner: observation.owner, foundation: observation.foundation,
        probe_status: observation.status, previous_status: observation.previous_status,
        delta: observation.delta, observed_at: observation.observed_at,
        ...(observation.value !== undefined ? {value: observation.value} : {}),
        ...(observation.reason ? {reason: observation.reason} : {})}
        : {semantic_id: target.semantic_id, observed_node_id: target.observed_node_id,
          observed_type: target.observed_type, api_member_id: candidate.api_member_id,
          property: candidate.property, foundation: candidate.foundation,
          probe_status: 'not-observed-yet', candidate_total: eligibility.eligible,
          candidate_offset: eligibility.offset, coverage: eligibility.coverage,
          observed_candidates: eligibility.observed, remaining_candidates: eligibility.remaining,
          blocked_candidates: eligibility.blocked, next_offset: eligibility.nextOffset};
      addNode({id: memberId, type: 'figma', title: `${candidate.owner}.${candidate.property}`,
        status: 'unverified', source: `Figma Plugin API ${probeMeta.apiVersion} unresolved candidate`,
        detail: JSON.stringify({api_member_id: candidate.api_member_id,
          official_member_id: candidate.official_member_id, signature: candidate.signature,
          foundation: candidate.foundation, audit_status: candidate.audit_status})});
      addNode({id: observationId, type: 'test', title: `Probe ${candidate.property} on selected node`, status,
        source: 'bounded read-only native API probe', detail: JSON.stringify(detail)});
      addEdge(memberId, typeId, 'declared for');
      addEdge(observationId, memberId, 'reads property');
      addEdge(observationId, targetId, observation ? 'observed on' : 'selected for');
    }
  }
  return {schema: 'figma-flow-native-api-probe-graph-v1', version: 1,
    title: 'Native Figma API probe', auditSha256: probeMeta.auditSha256,
    fieldPolicySha256: probeMeta.fieldPolicySha256, nodes, edges};
}

async function discoverSelectedNativeApi(figma, scope, config) {
  if (figma.fileKey !== scope.file_key || figma.currentPage.id !== scope.page_id
      || config.fileKey !== scope.file_key || config.pageId !== scope.page_id) {
    throw Error('Wrong native API probe file or page.');
  }
  if (config.schema !== 'figma-flow-native-api-probe-config-v1'
      || !config.fieldPolicy || !/^[a-f0-9]{64}$/.test(config.fieldPolicySha256 || '')
      || !Array.isArray(config.targets) || config.targets.length < 1
      || config.targets.length > NATIVE_API_PROBE_MAX_TARGETS) throw Error('Invalid bounded API probe config.');
  const planned = config.targets.reduce((total, target) => {
    const fields = config.candidatesByType?.[target.observed_type];
    return total + (Array.isArray(fields) ? fields.length : 0);
  }, 0);
  if (planned > NATIVE_API_PROBE_MAX_GETTERS) throw Error('API getter budget exceeds 192 calls.');
  for (const target of config.targets) {
    const eligible = config.eligibleByType?.[target.observed_type];
    if (!Array.isArray(eligible) || eligible.length > 64) throw Error('Eligible property list exceeds 64 fields per node type.');
  }
  const start = Date.now(), observations = [], targets = [];
  let attempted = 0, ancestorChecks = 0;
  for (const target of config.targets) {
    const candidates = config.candidatesByType[target.observed_type];
    if (!Array.isArray(candidates) || candidates.length > 16
        || typeof config.nodeTypeInterfaces?.[target.observed_type] !== 'string'
        || !nativeProbeId(target.observed_node_id) || typeof target.semantic_id !== 'string') {
      throw Error('Unsupported or malformed selected API probe target.');
    }
    const base = {semantic_id: target.semantic_id, observed_node_id: target.observed_node_id,
      observed_type: target.observed_type};
    targets.push(base);
    let node = null, targetBlock = null;
    if (Date.now() - start >= NATIVE_API_PROBE_MAX_ELAPSED_MS) targetBlock = 'time-budget';
    else {
      try { node = await figma.getNodeByIdAsync(target.observed_node_id); }
      catch (_) { targetBlock = 'lookup-failed'; }
      if (!node && !targetBlock) targetBlock = 'node-unavailable';
      if (node && node.id !== target.observed_node_id) targetBlock = 'id-mismatch';
      if (node && node.type !== target.observed_type) targetBlock = 'type-mismatch';
      if (node && !targetBlock) {
        let cursor = node, depth = 0;
        try {
          while (cursor && cursor.id !== scope.page_id && depth < NATIVE_API_PROBE_MAX_ANCESTORS) {
            cursor = cursor.parent;
            depth++;
            ancestorChecks++;
          }
        } catch (_) { targetBlock = 'scope-check-failed'; }
        if (!targetBlock && (!cursor || cursor.id !== scope.page_id)) targetBlock = 'outside-page';
      }
    }
    for (const candidate of candidates) {
      const fieldPolicy = config.fieldPolicy?.[candidate?.property];
      if (!fieldPolicy || fieldPolicy.value_kind !== candidate?.value_kind
          || fieldPolicy.foundation !== candidate?.foundation
          || fieldPolicy.access !== candidate?.access
          || (candidate?.access === 'method' && (!NATIVE_API_PROBE_METHODS[candidate?.property]
            || NATIVE_API_PROBE_METHODS[candidate.property].value_kind !== candidate.value_kind
            || NATIVE_API_PROBE_METHODS[candidate.property].foundation !== candidate.foundation))
          || candidate?.receiver_type !== target.observed_type
          || !Array.isArray(fieldPolicy.allowed_receivers)
          || (!fieldPolicy.allowed_receivers.includes('*')
            && !fieldPolicy.allowed_receivers.includes(target.observed_type))
          || candidate?.audit_status !== 'unresolved'
          || typeof candidate?.api_member_id !== 'string') throw Error('Probe contains a non-allowlisted property candidate.');
      const prior = config.previous?.observed_at && Array.isArray(config.previous.statuses)
        ? config.previous.statuses.find(row => row.semantic_id === target.semantic_id
          && row.observed_node_id === target.observed_node_id && row.api_member_id === candidate.api_member_id)?.status
        : undefined;
      let status, reason, value;
      if (targetBlock) { status = targetBlock === 'node-unavailable' ? 'unavailable' : 'blocked'; reason = targetBlock; }
      else if (node.type !== target.observed_type) { status = 'blocked'; reason = 'type-mismatch'; }
      else if (Date.now() - start >= NATIVE_API_PROBE_MAX_ELAPSED_MS || attempted >= NATIVE_API_PROBE_MAX_GETTERS) {
        status = 'blocked'; reason = 'getter-budget';
      } else if (candidate.access === 'property' && !(candidate.property in node)) {
        status = 'unsupported'; reason = 'property-absent';
      } else if (candidate.access === 'method' && typeof node[candidate.property] !== 'function') {
        status = 'unsupported'; reason = 'method-absent';
      }
      else {
        attempted++;
        try {
          let rawValue;
          if (candidate.access === 'property') rawValue = node[candidate.property];
          else if (candidate.property === 'getCSSAsync') rawValue = await node.getCSSAsync();
          else if (candidate.property === 'getRangeFontName'
              || candidate.property === 'getRangeFontSize' || candidate.property === 'getRangeFills') {
            if (typeof node.characters !== 'string' || !node.characters.length) {
              status = 'unavailable'; reason = 'empty-text-range';
            } else if (candidate.property === 'getRangeFontName') {
              rawValue = node.getRangeFontName(0, node.characters.length);
            } else if (candidate.property === 'getRangeFontSize') {
              rawValue = node.getRangeFontSize(0, node.characters.length);
            } else rawValue = node.getRangeFills(0, node.characters.length);
          } else { status = 'blocked'; reason = 'method-not-allowlisted'; }
          const safe = status ? {ok: false} : nativeProbeValue(candidate.value_kind, rawValue, figma);
          if (safe.ok) { status = 'success'; value = safe.value; }
          else if (!status) { status = 'unavailable'; reason = 'value-not-in-safe-projection'; }
        } catch (_) { status = 'unavailable'; reason = 'getter-threw'; }
      }
      const delta = prior === undefined ? 'unknown' : prior === status ? 'matched' : 'changed';
      observations.push({semantic_id: target.semantic_id, observed_node_id: target.observed_node_id,
        observed_type: target.observed_type, api_member_id: candidate.api_member_id,
        official_member_id: candidate.official_member_id, owner: candidate.owner,
        property: candidate.property, signature: candidate.signature, foundation: candidate.foundation,
        status, previous_status: prior || null, delta, ...(status === 'success' ? {value} : {}),
        ...(reason ? {reason} : {})});
    }
  }
  if (figma.fileKey !== scope.file_key || figma.currentPage.id !== scope.page_id) {
    throw Error('Discovery scope changed during native API probe.');
  }
  const counts = nativeProbeStatusCounts(observations);
  const currentDeltas = observations.reduce((out, row) => { out[row.delta]++; return out; }, {matched: 0, changed: 0, unknown: 0});
  const merged = new Map();
  for (const old of config.previous?.statuses || []) {
    const target = targets.find(row => row.semantic_id === old.semantic_id && row.observed_node_id === old.observed_node_id);
    if (!target) continue;
    const candidate = config.eligibleByType[target.observed_type].find(row => row.api_member_id === old.api_member_id);
    if (!candidate || !NATIVE_API_PROBE_STATUSES.includes(old.status)) continue;
    const prior = {semantic_id: target.semantic_id, observed_node_id: target.observed_node_id,
      observed_type: target.observed_type, api_member_id: candidate.api_member_id,
      official_member_id: candidate.official_member_id, owner: candidate.owner,
      property: candidate.property, signature: candidate.signature, foundation: candidate.foundation,
      status: old.status, previous_status: old.status, delta: 'previous-batch',
      observed_at: config.previous.observed_at};
    merged.set(`${prior.semantic_id}\u0000${prior.api_member_id}`, prior);
  }
  for (const row of observations) merged.set(`${row.semantic_id}\u0000${row.api_member_id}`, row);
  const mergedObservations = [...merged.values()];
  const mergedCounts = nativeProbeStatusCounts(mergedObservations);
  const eligibility = {};
  for (const nodeType of Object.keys(config.eligibleByType)) {
    const fields = config.eligibleByType[nodeType];
    const selectedTargets = targets.filter(row => row.observed_type === nodeType);
    let expected = 0, observed = 0, blocked = 0, nextIndex = null;
    for (const target of selectedTargets) {
      for (let index = 0; index < fields.length; index++) {
        expected++;
        const result = mergedObservations.find(row => row.semantic_id === target.semantic_id
          && row.observed_node_id === target.observed_node_id && row.api_member_id === fields[index].api_member_id);
        if (result && result.status !== 'blocked') observed++;
        else {
          if (result?.status === 'blocked') blocked++;
          if (nextIndex === null) nextIndex = index;
        }
      }
    }
    const remaining = Math.max(0, expected - observed - blocked);
    eligibility[nodeType] = {eligible: fields.length, offset: config.candidateOffset,
      planned: config.candidatesByType[nodeType]?.length || 0, observed, remaining, blocked,
      nextOffset: nextIndex === null ? null : Math.floor(nextIndex / 16) * 16,
      coverage: fields.length === 0 ? 'no-candidate'
        : remaining === 0 && blocked === 0 ? 'complete'
          : remaining === 0 ? 'blocked' : 'partial'};
  }
  const observedAt = new Date().toISOString();
  const probe = {schema: 'figma-flow-native-api-probe-v1', status: 'success',
    auditRelease: config.auditRelease, apiSource: config.apiSource, observed_at: observedAt,
    auditSha256: config.auditSha256, selectionSha256: config.selectionSha256,
    fieldPolicySha256: config.fieldPolicySha256,
    candidateOffset: config.candidateOffset, eligibleByType: eligibility,
    counts, mergedCounts, deltaCounts: currentDeltas,
    previousComparable: config.previous?.comparable ?? false,
    previousReason: config.previous?.reason || (config.previous ? null : 'no-previous-readback'),
    previousObservedAt: config.previous?.observed_at || null,
    observations: mergedObservations,
    budget: {selectedNodes: targets.length, candidateRows: planned, attemptedGetters: attempted,
      maxGetters: NATIVE_API_PROBE_MAX_GETTERS, elapsedMs: Math.max(0, Date.now() - start),
      maxElapsedMs: NATIVE_API_PROBE_MAX_ELAPSED_MS, ancestorChecks,
      maxAncestorChecks: targets.length * NATIVE_API_PROBE_MAX_ANCESTORS}};
  const graph = nativeProbeGraph(mergedObservations, targets, {apiVersion: config.apiSource.version,
    auditSha256: config.auditSha256, fieldPolicySha256: config.fieldPolicySha256},
    config.eligibleByType, eligibility);
  return {schema: 'figma-flow-graph-native-discovery-v1', status: 'success',
    fileKey: figma.fileKey, pageId: scope.page_id, allowed_page_ids: [scope.page_id],
    nodes: targets.map(row => ({id: row.observed_node_id, semanticId: row.semantic_id, type: row.observed_type})),
    collections: [], variables: [], api_probe: probe, graph, observed_at: observedAt};
}
