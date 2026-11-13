/* Read approved values from owned native fixture getters. No user paths are accepted. */
const VALUE_MARK = 'figmaFlowNativeValuePaths';
const SERVICE_MARK = 'figmaFlowServiceSpecimen';
const LAB_NAME = 'Figma Flow · Native value paths';
const MAX_ITEMS = 8;
const MAX_PATH_BYTES = 50000;
const ACTION_TAGS = ['BACK', 'CLOSE', 'CONDITIONAL', 'NODE', 'SET_VARIABLE'];
const TRIGGER_TAGS = ['AFTER_TIMEOUT', 'ON_CLICK', 'ON_DRAG', 'ON_HOVER', 'ON_KEY_DOWN', 'ON_MEDIA_END', 'ON_MEDIA_HIT', 'ON_PRESS'];
const TRANSITION_TAGS = ['DISSOLVE', 'MOVE_IN', 'MOVE_OUT', 'PUSH', 'SCROLL_ANIMATE', 'SLIDE_IN', 'SLIDE_OUT', 'SMART_ANIMATE'];
const EASING_TAGS = ['BOUNCY', 'CUSTOM_CUBIC_BEZIER', 'CUSTOM_SPRING', 'EASE_IN', 'EASE_IN_AND_OUT', 'EASE_IN_AND_OUT_BACK', 'EASE_OUT', 'EASE_OUT_BACK', 'GENTLE', 'LINEAR', 'QUICK', 'SLOW'];
const NAVIGATION_TAGS = ['CHANGE_TO', 'NAVIGATE', 'OVERLAY', 'SCROLL_TO', 'SWAP'];
const EFFECT_TAGS = ['BACKGROUND_BLUR', 'GLASS', 'INNER_SHADOW', 'LAYER_BLUR', 'NOISE', 'TEXTURE'];
const GRID_TAGS = ['COLUMNS', 'GRID', 'ROWS'];
const BLUR_TAGS = ['NORMAL', 'PROGRESSIVE'];
const NOISE_TAGS = ['DUOTONE', 'MONOTONE', 'MULTITONE'];
const VARIABLE_DATA_TAGS = ['BOOLEAN', 'COLOR', 'EASING', 'EXPRESSION', 'FLOAT', 'STRING', 'TIMING', 'VARIABLE_ALIAS'];
const VARIABLE_RESOLVED_TYPES = ['BOOLEAN', 'COLOR', 'FLOAT', 'STRING'];
const EXPRESSION_FUNCTIONS = ['ADDITION', 'AND', 'DIVISION', 'EQUALS', 'GREATER_THAN', 'GREATER_THAN_OR_EQUAL',
  'LESS_THAN', 'LESS_THAN_OR_EQUAL', 'MULTIPLICATION', 'NEGATE', 'NOT', 'NOT_EQUAL', 'OR', 'SUBTRACTION', 'VAR_MODE_LOOKUP'];
const OWNER_TAGS = Object.freeze({
  Action: ACTION_TAGS, Trigger: TRIGGER_TAGS, Transition: TRANSITION_TAGS, Easing: EASING_TAGS,
  Effect: EFFECT_TAGS, LayoutGrid: GRID_TAGS, BlurEffect: BLUR_TAGS, NoiseEffect: NOISE_TAGS,
  VariableData: VARIABLE_DATA_TAGS,
});

const isObject = value => value !== null && typeof value === 'object';
const finite = value => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1_000_000_000;
const enumValue = (value, allowed) => typeof value === 'string' && allowed.includes(value) ? value : 'OTHER';
const emptyState = value => value === undefined ? {state: 'UNSET'} : value === null ? {state: 'NULL'} : null;

function safeNumber(value) { return finite(value) ? value : null; }

function safeVector(value) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  return {x: safeNumber(value.x), y: safeNumber(value.y)};
}

function safeColor(value) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  return {r: safeNumber(value.r), g: safeNumber(value.g), b: safeNumber(value.b),
    a: safeNumber(value.a === undefined ? 1 : value.a)};
}

function safeBoundState(value) {
  if (!isObject(value)) return {count: 0};
  try { return {count: Math.min(Object.keys(value).length, 32)}; }
  catch (_) { return {state: 'UNAVAILABLE'}; }
}

function safePathSummary(data) {
  if (typeof data !== 'string' || data.length > MAX_PATH_BYTES) return {state: 'UNAVAILABLE'};
  const tokens = data.replace(/([MLCQZ])/gi, ' $1 ').trim().split(/\s+/).filter(Boolean);
  const commands = Object.create(null), coordinates = [];
  for (const token of tokens) {
    if (/^[MLCQZ]$/i.test(token)) commands[token.toUpperCase()] = (commands[token.toUpperCase()] || 0) + 1;
    else {
      const number = Number(token);
      if (!Number.isFinite(number) || Math.abs(number) > 1_000_000_000) return {state: 'UNAVAILABLE'};
      coordinates.push(number);
      if (coordinates.length > 4096) return {state: 'UNAVAILABLE'};
    }
  }
  return {commands, coordinateCount: coordinates.length,
    coordinateMinimum: coordinates.length ? Math.min(...coordinates) : null,
    coordinateMaximum: coordinates.length ? Math.max(...coordinates) : null};
}

function valuePathPolicy(plan) {
  const routes = new Map((plan.routes || []).map(route => [route.id, route]));
  const candidates = new Map((plan.candidate_members || []).map(row => [`${row.owner}.${row.name}`, row]));
  return {routes, candidates};
}

function createCollector(plan) {
  const policy = valuePathPolicy(plan);
  const rows = new Map();
  const unions = new Map();
  const scenarioStates = new Map();
  const apiContext = {collector: null};
  function noteUnion(name, value, discriminant = 'type', routeId) {
    const route = policy.routes.get(routeId);
    const union = route?.unions?.[name];
    const raw = isObject(value) ? value[discriminant] : undefined;
    const allowed = union?.branches?.filter(branch => !branch.previouslyObserved).map(branch => branch.tag) || [];
    if (!allowed.includes(raw)) return 'OTHER';
    if (!unions.has(name)) unions.set(name, new Set());
    unions.get(name).add(raw);
    return raw;
  }
  function record(owner, name, routeId, status, value) {
    const candidate = policy.candidates.get(`${owner}.${name}`);
    if (!candidate) return;
    const prior = rows.get(candidate.member_id);
    if (!prior) {
      rows.set(candidate.member_id, {member_id: candidate.member_id, owner, name,
        route: routeId, status, samples: [value]});
      return;
    }
    const samples = prior.samples;
    if (!samples.some(sample => JSON.stringify(sample) === JSON.stringify(value)) && samples.length < MAX_ITEMS) samples.push(value);
    if (prior.status !== 'success' && status === 'success') prior.status = status;
  }
  function readMember(owner, object, name, routeId) {
    if (!policy.candidates.has(`${owner}.${name}`)) return undefined;
    try {
      const raw = object == null ? undefined : object[name];
      record(owner, name, routeId, 'success', projectField(owner, name, raw, routeId, apiContext));
      return raw;
    } catch (_) {
      record(owner, name, routeId, 'runtime-error', {state: 'UNAVAILABLE'});
      return undefined;
    }
  }
  function readOwner(owner, object, routeId) {
    const route = policy.routes.get(routeId);
    const fields = route?.owners?.[owner] || [];
    for (const field of fields) readMember(owner, object, field, routeId);
  }
  function setScenario(route, status) {
    const prior = scenarioStates.get(route) || {route, status, assignments_attempted: 0,
      assignments_succeeded: 0, assignments_failed: 0, readback_objects: 0};
    if (prior.assignments_failed > 0 && prior.readback_objects > 0
        && ['created', 'reused', 'seed-error'].includes(status)) status = 'partial';
    else if (prior.assignments_failed > 0 && ['created', 'reused'].includes(status))
      status = prior.assignments_succeeded > 0 ? 'partial' : 'seed-error';
    prior.status = status;
    scenarioStates.set(route, prior);
  }
  function assignment(route, succeeded) {
    const prior = scenarioStates.get(route) || {route, status: 'created', assignments_attempted: 0,
      assignments_succeeded: 0, assignments_failed: 0, readback_objects: 0};
    prior.assignments_attempted++;
    if (succeeded) prior.assignments_succeeded++;
    else prior.assignments_failed++;
    scenarioStates.set(route, prior);
  }
  function readback(route) {
    const prior = scenarioStates.get(route) || {route, status: 'created', assignments_attempted: 0,
      assignments_succeeded: 0, assignments_failed: 0, readback_objects: 0};
    prior.readback_objects++;
    scenarioStates.set(route, prior);
  }
  function report() {
    const observations = [...rows.values()].map(row => ({member_id: row.member_id, owner: row.owner,
      name: row.name, route: row.route, status: row.status,
      value: row.samples.length === 1 ? row.samples[0] : {samples: row.samples}}))
      .sort((a, b) => a.member_id.localeCompare(b.member_id));
    const counts = {success: 0, unavailable: 0, runtime_error: 0, unsupported: 0};
    for (const row of observations) {
      const key = row.status === 'runtime-error' ? 'runtime_error' : row.status;
      counts[key]++;
    }
    const unionCoverage = {};
    for (const route of policy.routes.values()) {
      for (const [name, spec] of Object.entries(route.unions || {})) {
        if (unionCoverage[name]) continue;
        unionCoverage[name] = {observed: [...(unions.get(name) || [])].sort()};
      }
    }
    return {observations, getter_counts: counts,
      scenarios: [...scenarioStates.values()].sort((a, b) => a.route.localeCompare(b.route)),
      union_coverage: unionCoverage};
  }
  const collector = {policy, readMember, readOwner, record, noteUnion, setScenario, assignment, readback, report};
  apiContext.collector = collector;
  return collector;

  function projectField(owner, name, value, routeId, api) {
    const absent = emptyState(value);
    if (absent) return absent;
    if (name === 'action') return projectAction(value, routeId, api);
    if (name === 'actions') {
      const list = Array.isArray(value) ? value : [];
      return {count: Math.min(list.length, MAX_ITEMS), samples: list.slice(0, MAX_ITEMS).map(action => projectAction(action, routeId, api))};
    }
    if (name === 'trigger') return projectTrigger(value, routeId, api);
    if (name === 'easing') return projectEasing(value, routeId, api);
    if (name === 'condition') return projectVariableData(value, routeId, api);
    if (name === 'value') return projectVariableValue(value, routeId, api);
    if (name === 'expressionArguments') return {count: Array.isArray(value) ? Math.min(value.length, MAX_ITEMS) : 0};
    if (name === 'conditionalBlocks') {
      const list = Array.isArray(value) ? value : [];
      return {count: Math.min(list.length, MAX_ITEMS), samples: list.slice(0, MAX_ITEMS).map(block => projectConditionalBlock(block, routeId, api))};
    }
    if (name === 'transition') return projectTransition(value, routeId, api);
    if (name === 'color' || name === 'secondaryColor') return safeColor(value);
    if (name === 'offset' && owner === 'RowsColsLayoutGrid') return {value: safeNumber(value)};
    if (name === 'offset' && owner === 'InnerShadowEffect') return safeVector(value);
    if (['startOffset', 'endOffset', 'noiseSizeVector'].includes(name)) return safeVector(value);
    if (name === 'boundVariables') return safeBoundState(value);
    if (name === 'data' && owner === 'VectorPath') return safePathSummary(value);
    if (['destinationId', 'variableId', 'variableCollectionId', 'variableModeId'].includes(name)) return {present: typeof value === 'string'};
    if (name === 'keyCodes') return {count: Array.isArray(value) ? Math.min(value.length, MAX_ITEMS) : 0};
    if (name === 'type') return {value: safeUnionTag(owner, value, routeId, api)};
    if (name === 'blurType') return {value: api.collector.noteUnion('BlurEffect', {blurType: value}, 'blurType', routeId)};
    if (name === 'noiseType') return {value: api.collector.noteUnion('NoiseEffect', {noiseType: value}, 'noiseType', routeId)};
    if (name === 'pattern' && owner === 'RowsColsLayoutGrid') return {value: api.collector.noteUnion('LayoutGrid', {pattern: value}, 'pattern', routeId)};
    if (name === 'pattern' && owner === 'GridLayoutGrid') return {value: api.collector.noteUnion('LayoutGrid', {pattern: value}, 'pattern', routeId)};
    if (name === 'type' && owner === 'SimpleTransition') return {value: value};
    if (name === 'type' && owner === 'DirectionalTransition') return {value: value};
    if (name === 'type' && owner === 'Easing') return {value: value};
    if (name === 'type' && owner === 'VariableData') return {value: value};
    if (name === 'expressionFunction') return {value: enumValue(value, EXPRESSION_FUNCTIONS)};
    if (name === 'navigation') return {value: enumValue(value, NAVIGATION_TAGS)};
    if (name === 'direction') return {value: enumValue(value, ['BOTTOM', 'LEFT', 'RIGHT', 'TOP'])};
    if (name === 'alignment') return {value: enumValue(value, ['CENTER', 'MAX', 'MIN', 'STRETCH'])};
    if (name === 'windingRule') return {value: enumValue(value, ['EVENODD', 'NONZERO', 'NONE'])};
    if (name === 'blendMode') return {value: enumValue(value, ['DARKEN', 'DIFFERENCE', 'EXCLUSION', 'HARD_LIGHT', 'LIGHTEN', 'MULTIPLY', 'NORMAL', 'OVERLAY', 'SCREEN', 'SOFT_LIGHT'])};
    if (name === 'device') return {value: enumValue(value, ['KEYBOARD', 'PS4', 'SWITCH_PRO', 'UNKNOWN_CONTROLLER', 'XBOX_ONE'])};
    if (['visible', 'matchLayers', 'clipToShape', 'resetVideoPosition', 'resetScrollPosition', 'resetInteractiveComponents', 'preserveScrollPosition', 'openInNewTab'].includes(name)) {
      return {value: typeof value === 'boolean' ? value : null};
    }
    if (name === 'url') return {present: typeof value === 'string'};
    if (typeof value === 'number') return {value: safeNumber(value)};
    if (typeof value === 'boolean') return {value};
    if (typeof value === 'string') return {value: 'OTHER'};
    if (Array.isArray(value)) return {count: Math.min(value.length, MAX_ITEMS)};
    return {state: isObject(value) ? 'PRESENT' : 'UNAVAILABLE'};
  }
}

function safeUnionTag(owner, value, routeId, api) {
  const union = owner === 'SimpleTransition' || owner === 'DirectionalTransition' ? 'Transition'
    : owner === 'BlurEffectBase' ? 'Effect'
    : owner === 'NoiseEffectBase' ? 'Effect'
    : owner === 'InnerShadowEffect' || owner === 'TextureEffect' || owner === 'GlassEffect' ? 'Effect'
    : owner === 'VariableData' ? 'VariableData' : owner;
  if (owner === 'VariableData') return api.collector.noteUnion('VariableData', {type: value}, 'type', routeId);
  if (owner === 'SimpleTransition' || owner === 'DirectionalTransition') {
    return api.collector.noteUnion('Transition', {type: value}, 'type', routeId);
  }
  if (owner === 'BlurEffectBase') return api.collector.noteUnion('Effect', {type: value}, 'type', routeId);
  if (owner === 'NoiseEffectBase') return api.collector.noteUnion('Effect', {type: value}, 'type', routeId);
  if (['InnerShadowEffect', 'TextureEffect', 'GlassEffect'].includes(owner)) return api.collector.noteUnion('Effect', {type: value}, 'type', routeId);
  if (owner === 'BlurEffectNormal' || owner === 'BlurEffectProgressive') return api.collector.noteUnion('BlurEffect', {blurType: value}, 'blurType', routeId);
  if (owner === 'NoiseEffectMonotone' || owner === 'NoiseEffectDuotone' || owner === 'NoiseEffectMultitone') return api.collector.noteUnion('NoiseEffect', {noiseType: value}, 'noiseType', routeId);
  return enumValue(value, OWNER_TAGS[union] || []);
}

function projectAction(value, routeId, api) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  const type = api.collector.noteUnion('Action', value, 'type', routeId);
  if (type === 'NODE') return {type, navigation: enumValue(value.navigation, NAVIGATION_TAGS),
    destinationPresent: typeof value.destinationId === 'string', transition: projectTransition(value.transition, routeId, api)};
  if (type === 'CONDITIONAL') {
    const blocks = Array.isArray(value.conditionalBlocks) ? value.conditionalBlocks : [];
    return {type, conditionalBlocks: blocks.slice(0, MAX_ITEMS).map(block => projectConditionalBlock(block, routeId, api)), count: Math.min(blocks.length, MAX_ITEMS)};
  }
  if (type === 'SET_VARIABLE') return {type, variablePresent: typeof value.variableId === 'string', variableValue: projectVariableData(value.variableValue, routeId, api)};
  if (type === 'BACK' || type === 'CLOSE') return {type};
  return {type: 'OTHER'};
}

function projectActionArray(value, routeId, api) {
  const list = Array.isArray(value) ? value : [];
  return {count: Math.min(list.length, MAX_ITEMS), samples: list.slice(0, MAX_ITEMS).map(action => projectAction(action, routeId, api))};
}

function projectTrigger(value, routeId, api) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  const type = api.collector.noteUnion('Trigger', value, 'type', routeId);
  if (type === 'AFTER_TIMEOUT') return {type, timeout: safeNumber(value.timeout)};
  if (type === 'ON_KEY_DOWN') return {type, device: enumValue(value.device, ['KEYBOARD', 'PS4', 'SWITCH_PRO', 'UNKNOWN_CONTROLLER', 'XBOX_ONE']),
    keyCount: Array.isArray(value.keyCodes) ? Math.min(value.keyCodes.length, MAX_ITEMS) : 0};
  if (type === 'ON_MEDIA_HIT') return {type, mediaHitTime: safeNumber(value.mediaHitTime)};
  if (type === 'MOUSE_UP' || type === 'MOUSE_DOWN' || type === 'MOUSE_ENTER' || type === 'MOUSE_LEAVE') return {type, delay: safeNumber(value.delay)};
  return type === 'OTHER' ? {type: 'OTHER'} : {type};
}

function projectEasing(value, routeId, api) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  const type = api.collector.noteUnion('Easing', value, 'type', routeId);
  const summary = {type, cubicBezier: null, spring: null};
  const bezier = value.easingFunctionCubicBezier;
  if (isObject(bezier)) {
    api.collector.readOwner('EasingFunctionBezier', bezier, routeId);
    summary.cubicBezier = Object.fromEntries(['x1', 'y1', 'x2', 'y2'].map(key => [key, safeNumber(bezier[key])]));
  }
  const spring = value.easingFunctionSpring;
  if (isObject(spring)) {
    api.collector.readOwner('EasingFunctionSpring', spring, routeId);
    summary.spring = Object.fromEntries(['mass', 'stiffness', 'damping', 'initialVelocity'].map(key => [key, safeNumber(spring[key])]));
  }
  api.collector.readOwner('Easing', value, routeId);
  return summary;
}

function projectTransition(value, routeId, api) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  const type = api.collector.noteUnion('Transition', value, 'type', routeId);
  const owner = ['MOVE_IN', 'MOVE_OUT', 'PUSH', 'SLIDE_IN', 'SLIDE_OUT'].includes(type)
    ? 'DirectionalTransition' : 'SimpleTransition';
  api.collector.readOwner(owner, value, routeId);
  return {type, duration: safeNumber(value.duration), direction: enumValue(value.direction, ['BOTTOM', 'LEFT', 'RIGHT', 'TOP']),
    matchLayers: typeof value.matchLayers === 'boolean' ? value.matchLayers : null,
    easing: projectEasing(value.easing, routeId, api)};
}

function projectVariableValue(value, routeId, api) {
  if (value === null || value === undefined) return {state: emptyState(value).state};
  if (typeof value === 'boolean') return {kind: 'BOOLEAN', value};
  if (typeof value === 'number') return {kind: 'NUMBER', value: safeNumber(value)};
  if (typeof value === 'string') return {kind: 'STRING', present: true};
  if (isObject(value)) {
    if (value.expressionFunction) {
      api.collector.readOwner('Expression', value, routeId);
      return {kind: 'EXPRESSION', function: enumValue(value.expressionFunction, EXPRESSION_FUNCTIONS),
        argumentCount: Array.isArray(value.expressionArguments) ? Math.min(value.expressionArguments.length, MAX_ITEMS) : 0};
    }
    return {kind: value.type === 'VARIABLE_ALIAS' ? 'VARIABLE_ALIAS' : 'OBJECT', present: true};
  }
  return {state: 'UNAVAILABLE'};
}

function projectVariableData(value, routeId, api) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  const type = api.collector.noteUnion('VariableData', value, 'type', routeId);
  api.collector.readOwner('VariableData', value, routeId);
  return {type, resolvedType: enumValue(value.resolvedType, VARIABLE_RESOLVED_TYPES), value: projectVariableValue(value.value, routeId, api)};
}

function projectConditionalBlock(value, routeId, api) {
  if (!isObject(value)) return {state: emptyState(value)?.state || 'INVALID'};
  api.collector.readOwner('ConditionalBlock', value, routeId);
  return {condition: projectVariableData(value.condition, routeId, api), actions: projectActionArray(value.actions, routeId, api)};
}

function summarizeVectorPath(value) {
  if (typeof value !== 'string' || value.length > MAX_PATH_BYTES) return {state: 'UNAVAILABLE'};
  const commandCounts = {C: 0, L: 0, M: 0, Q: 0, Z: 0};
  for (const command of value.match(/[MLCQZ]/gi) || []) commandCounts[command.toUpperCase()]++;
  const numbers = value.match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi)?.map(Number) || [];
  if (numbers.length > 4096 || numbers.some(number => !finite(number))) return {state: 'UNAVAILABLE'};
  return {commandCounts, coordinateCount: numbers.length,
    coordinateMinimum: numbers.length ? Math.min(...numbers) : null,
    coordinateMaximum: numbers.length ? Math.max(...numbers) : null};
}

function projectField(owner, name, value, routeId, api) {
  const absent = emptyState(value);
  if (absent) return absent;
  if (name === 'type') return {value: safeUnionTag(owner, value, routeId, api)};
  if (name === 'blurType') return {value: api.collector.noteUnion('BlurEffect', {blurType: value}, 'blurType', routeId)};
  if (name === 'noiseType') return {value: api.collector.noteUnion('NoiseEffect', {noiseType: value}, 'noiseType', routeId)};
  if (name === 'pattern' && ['RowsColsLayoutGrid', 'GridLayoutGrid'].includes(owner)) {
    return {value: api.collector.noteUnion('LayoutGrid', {pattern: value}, 'pattern', routeId)};
  }
  if (name === 'easing') return projectEasing(value, routeId, api);
  if (name === 'action') return projectAction(value, routeId, api);
  if (name === 'actions') return projectActionArray(value, routeId, api);
  if (name === 'trigger') return projectTrigger(value, routeId, api);
  if (name === 'transition') return projectTransition(value, routeId, api);
  if (name === 'condition') return projectVariableData(value, routeId, api);
  if (name === 'value') return projectVariableValue(value, routeId, api);
  if (name === 'conditionalBlocks') {
    const blocks = Array.isArray(value) ? value : [];
    return {count: Math.min(blocks.length, MAX_ITEMS), samples: blocks.slice(0, MAX_ITEMS).map(item => projectConditionalBlock(item, routeId, api))};
  }
  if (name === 'expressionArguments') return {count: Array.isArray(value) ? Math.min(value.length, MAX_ITEMS) : 0};
  if (name === 'data' && owner === 'VectorPath') return summarizeVectorPath(value);
  if (name === 'boundVariables') return safeBoundState(value);
  if (['color', 'secondaryColor'].includes(name)) return safeColor(value);
  if (['offset', 'startOffset', 'endOffset', 'noiseSizeVector'].includes(name)) return safeVector(value);
  if (name === 'direction') return enumValue(value, ['BOTTOM', 'LEFT', 'RIGHT', 'TOP']);
  if (name === 'alignment') return enumValue(value, ['CENTER', 'MAX', 'MIN', 'STRETCH']);
  if (name === 'windingRule') return enumValue(value, ['EVENODD', 'NONE', 'NONZERO']);
  if (name === 'navigation') return enumValue(value, NAVIGATION_TAGS);
  if (name === 'expressionFunction') return enumValue(value, EXPRESSION_FUNCTIONS);
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return safeNumber(value);
  if (typeof value === 'string') return 'OTHER';
  if (Array.isArray(value)) return {count: Math.min(value.length, MAX_ITEMS)};
  if (isObject(value)) return {state: 'PRESENT'};
  return {state: 'UNAVAILABLE'};
}

function safeUnionTag(owner, value, routeId, api) {
  const route = api.collector.policy.routes.get(routeId);
  const tags = route?.unions?.[owner]?.branches?.map(branch => branch.tag) || OWNER_TAGS[owner] || [];
  if (tags.includes(value)) {
    api.collector.noteUnion(owner, {[route?.unions?.[owner]?.discriminator || 'type']: value},
      route?.unions?.[owner]?.discriminator || 'type', routeId);
    return value;
  }
  if (owner === 'SimpleTransition' || owner === 'DirectionalTransition') {
    return api.collector.noteUnion('Transition', {type: value}, 'type', routeId);
  }
  if (owner === 'InnerShadowEffect' || owner === 'BlurEffectBase' || owner === 'NoiseEffectBase'
      || owner === 'TextureEffect' || owner === 'GlassEffect') return api.collector.noteUnion('Effect', {type: value}, 'type', routeId);
  if (owner === 'VariableData') return api.collector.noteUnion('VariableData', {type: value}, 'type', routeId);
  return 'OTHER';
}

function _makeReceiptApi(collector) {
  return {collector};
}

function _fixtureMarker(plan, label) { return `${plan.graph_sha256}/${label}`; }

function _matchingChildren(parent, marker, type) {
  return (parent.children || []).filter(node => node.type === type && node.getPluginData(VALUE_MARK) === marker);
}

function _appendOwned(api, parent, plan, label, type, create) {
  const marker = _fixtureMarker(plan, label);
  const matches = _matchingChildren(parent, marker, type);
  if (matches.length > 1) throw Error('Ambiguous owned value fixture node.');
  if (matches.length) return {node: matches[0], created: false};
  const node = create();
  if (!node || node.type !== type) throw Error('Figma did not create an expected owned fixture node.');
  node.name = `${LAB_NAME} · ${label}`;
  node.setPluginData(VALUE_MARK, marker);
  parent.appendChild(node);
  return {node, created: true};
}

function _newFrame(api, parent, plan, label, x, y, width, height) {
  const result = _appendOwned(api, parent, plan, label, 'FRAME', () => api.createFrame());
  if (result.created) {
    result.node.x = x; result.node.y = y; result.node.resize(width, height);
    result.node.layoutMode = 'NONE'; result.node.fills = [];
  }
  return result;
}

function _newRect(api, parent, plan, label, x, y) {
  const result = _appendOwned(api, parent, plan, label, 'RECTANGLE', () => api.createRectangle());
  if (result.created) { result.node.x = x; result.node.y = y; result.node.resize(72, 48); }
  return result;
}

function _writeStatus(collector, route, result) {
  collector.setScenario(route, result);
}

async function _ownedRoot(api, page, plan) {
  const marker = _fixtureMarker(plan, 'root');
  const matches = page.children.filter(node => node.type === 'FRAME' && node.getPluginData(VALUE_MARK) === marker);
  if (matches.length > 1 || matches.some(node => node.name !== LAB_NAME)) throw Error('Ambiguous owned native value path fixture root.');
  if (matches.length) return {node: matches[0], created: false};
  const node = api.createFrame();
  node.name = LAB_NAME;
  node.setPluginData(VALUE_MARK, marker);
  node.resize(900, 700);
  node.layoutMode = 'NONE';
  node.clipsContent = true;
  node.fills = [];
  node.x = page.children.reduce((right, child) => Math.max(right, child.x + (child.width || 0)), 0) + 96;
  node.y = 0;
  page.appendChild(node);
  return {node, created: true};
}

async function _ownedServiceVariable(api, page, plan) {
  if (!plan.capabilities?.getLocalVariablesAsync) return null;
  const serviceRoots = page.children.filter(node => node.type === 'FRAME'
    && node.getPluginData(SERVICE_MARK) === plan.service_graph_sha256);
  if (serviceRoots.length !== 1) return null;
  try {
    const variables = await api.variables.getLocalVariablesAsync('FLOAT');
    for (const variable of (Array.isArray(variables) ? variables : []).slice(0, 128)) {
      if (variable.getPluginData(SERVICE_MARK) === plan.service_graph_sha256) return variable;
    }
  } catch (_) {}
  return null;
}

async function _seedPrototype(api, root, plan, collector) {
  const route = 'prototype-reactions';
  try {
    const frame = _newFrame(api, root, plan, 'prototype-frame', 20, 20, 440, 300);
    const destination = _appendOwned(api, api.currentPage, plan, 'prototype-navigation-target', 'FRAME', () => api.createFrame());
    if (destination.created) {
      destination.node.x = root.x + root.width + 96; destination.node.y = 0;
      destination.node.resize(96, 88); destination.node.layoutMode = 'NONE'; destination.node.fills = [];
    }
    const nodeAction = transition => ({type: 'NODE', destinationId: destination.node.id,
      navigation: 'NAVIGATE', transition, preserveScrollPosition: false,
      resetScrollPosition: false, resetVideoPosition: false, resetInteractiveComponents: false});
    const specs = [
      ['prototype-basic', {trigger: {type: 'ON_CLICK'}, actions: [nodeAction(null)]}],
      ['prototype-dissolve', {trigger: {type: 'ON_CLICK'}, actions: [nodeAction({type: 'DISSOLVE', easing: {type: 'EASE_IN'}, duration: 0.2})]}],
      ['prototype-cubic', {trigger: {type: 'ON_CLICK'}, actions: [nodeAction({type: 'DISSOLVE', easing: {type: 'CUSTOM_CUBIC_BEZIER',
        easingFunctionCubicBezier: {x1: 0.18, y1: 0.2, x2: 0.82, y2: 0.8}}, duration: 0.2})]}],
      ['prototype-move', {trigger: {type: 'ON_DRAG'}, actions: [nodeAction({type: 'MOVE_IN', direction: 'LEFT', matchLayers: false,
        easing: {type: 'EASE_OUT'}, duration: 0.2})]}],
      ['prototype-spring', {trigger: {type: 'AFTER_TIMEOUT', timeout: 250}, actions: [nodeAction({type: 'PUSH', direction: 'RIGHT',
        matchLayers: false, easing: {type: 'CUSTOM_SPRING', easingFunctionSpring: {mass: 1, stiffness: 150, damping: 20,
          initialVelocity: 0}}, duration: 0.3})]}],
      ['prototype-conditional', {trigger: {type: 'ON_PRESS'}, actions: [{type: 'CONDITIONAL', conditionalBlocks: [
        {condition: {type: 'BOOLEAN', resolvedType: 'BOOLEAN', value: true}, actions: [{type: 'BACK'}]}]}]}],
    ];
    let attempts = 0, successes = 0, failures = 0, reused = 0;
    for (let index = 0; index < specs.length; index++) {
      const [label, reaction] = specs[index];
      const source = _newRect(api, frame.node, plan, label, 16 + (index % 3) * 92, 24 + Math.floor(index / 3) * 76);
      let current = source.node.reactions;
      if (source.created || Array.isArray(current) && current.length === 0) {
        if (typeof source.node.setReactionsAsync !== 'function') { failures++; }
        else {
          attempts++;
          try { await source.node.setReactionsAsync([reaction]); successes++; }
          catch (_) { failures++; }
        }
        current = source.node.reactions;
      } else reused++;
      if (!Array.isArray(current)) continue;
      for (const item of current.slice(0, MAX_ITEMS)) {
        collector.readback(route);
        collector.readOwner('Reaction', item, route);
        projectAction(item?.action, route, _makeReceiptApi(collector));
        projectActionArray(item?.actions, route, _makeReceiptApi(collector));
        projectTrigger(item?.trigger, route, _makeReceiptApi(collector));
      }
    }
    for (let index = 0; index < attempts; index++) collector.assignment(route, index < successes);
    collector.setScenario(route, failures && successes ? 'partial' : failures ? 'seed-error' : successes ? 'created' : reused ? 'reused' : 'unavailable');
  } catch (_) { _writeStatus(collector, route, 'unavailable'); }
}

async function _seedGrid(api, styleFrame, plan, variable, collector) {
  const route = 'layout-grid-rows-columns';
  try {
    if (styleFrame.created) {
      const value = [
        {pattern: 'ROWS', alignment: 'MIN', gutterSize: 8, count: 3, sectionSize: 24, offset: 4,
          visible: true, color: {r: 0.15, g: 0.35, b: 0.65, a: 0.25}},
        {pattern: 'COLUMNS', alignment: 'MIN', gutterSize: 12, count: 4, sectionSize: 36, offset: 6,
          visible: true, color: {r: 0.25, g: 0.5, b: 0.7, a: 0.2}},
      ];
      try { styleFrame.node.layoutGrids = value; collector.assignment(route, true); }
      catch (error) { collector.assignment(route, false); throw error; }
    }
    let grids = styleFrame.node.layoutGrids;
    if (styleFrame.created && variable && plan.capabilities?.setBoundVariableForLayoutGrid) {
      try {
        const rows = grids.find(grid => grid.pattern === 'ROWS');
        const bound = await api.variables.setBoundVariableForLayoutGrid(rows, 'gutterSize', variable);
        if (bound) {
          styleFrame.node.layoutGrids = [bound, ...grids.filter(grid => grid !== rows)];
          collector.assignment(route, true);
          grids = styleFrame.node.layoutGrids;
        } else collector.assignment(route, false);
      } catch (_) { collector.assignment(route, false); }
    }
    collector.setScenario(route, styleFrame.created ? 'created' : 'reused');
    if (!Array.isArray(grids)) { collector.record('BaseFrameMixin', 'layoutGrids', route, 'unavailable', {state: 'NOT_ARRAY'}); return; }
    for (const grid of grids.slice(0, MAX_ITEMS)) {
      collector.readback(route);
      const owner = grid?.pattern === 'ROWS' || grid?.pattern === 'COLUMNS' ? 'RowsColsLayoutGrid' : 'GridLayoutGrid';
      collector.noteUnion('LayoutGrid', grid, 'pattern', route);
      collector.readOwner(owner, grid, route);
    }
  } catch (_) { _writeStatus(collector, route, 'unavailable'); }
}

async function _seedEffects(api, styleFrame, plan, variable, collector) {
  const route = 'scene-effects';
  const specs = [
    ['inner-shadow', {type: 'INNER_SHADOW', color: {r: 0.2, g: 0.3, b: 0.4, a: 0.35}, offset: {x: 1, y: 2}, radius: 4, spread: 1, visible: true, blendMode: 'NORMAL'}],
    ['layer-blur', {type: 'LAYER_BLUR', blurType: 'NORMAL', radius: 3, visible: true}],
    ['progressive-blur', {type: 'BACKGROUND_BLUR', blurType: 'PROGRESSIVE', radius: 8, startRadius: 2,
      startOffset: {x: 0.1, y: 0.5}, endOffset: {x: 0.9, y: 0.5}, visible: true}],
    ['noise-monotone', {type: 'NOISE', noiseType: 'MONOTONE', color: {r: 0.2, g: 0.3, b: 0.4, a: 0.25},
      visible: true, blendMode: 'NORMAL', noiseSize: 4, noiseSizeVector: {x: 4, y: 6}, density: 0.3}],
    ['noise-duotone', {type: 'NOISE', noiseType: 'DUOTONE', color: {r: 0.2, g: 0.3, b: 0.4, a: 0.25},
      secondaryColor: {r: 0.8, g: 0.4, b: 0.2, a: 0.4}, visible: true, blendMode: 'NORMAL', noiseSize: 4, density: 0.3}],
    ['noise-multitone', {type: 'NOISE', noiseType: 'MULTITONE', color: {r: 0.2, g: 0.3, b: 0.4, a: 0.25},
      opacity: 0.3, visible: true, blendMode: 'NORMAL', noiseSize: 4, density: 0.3}],
    ['texture', {type: 'TEXTURE', visible: true, noiseSize: 4, noiseSizeVector: {x: 4, y: 6}, radius: 5, clipToShape: true}],
    ['glass', {type: 'GLASS', visible: true, lightIntensity: 0.6, lightAngle: 45, refraction: 0.4, depth: 2,
      dispersion: 0.1, radius: 6}],
  ];
  try {
    for (let index = 0; index < specs.length; index++) {
      const [label, specification] = specs[index];
      const owned = _newRect(api, styleFrame.node, plan, `effect-${label}`, 12 + (index % 4) * 150, 16 + Math.floor(index / 4) * 96);
      if (owned.created) {
        try {
          owned.node.effects = [specification];
          collector.assignment(route, true);
          if (label === 'inner-shadow' && variable && plan.capabilities?.setBoundVariableForEffect) {
            try {
              const bound = await api.variables.setBoundVariableForEffect(owned.node.effects[0], 'radius', variable);
              if (bound) { owned.node.effects = [bound]; collector.assignment(route, true); }
              else collector.assignment(route, false);
            } catch (_) { collector.assignment(route, false); }
          }
        } catch (_) { collector.assignment(route, false); /* Read back the native getter below; assignment text is not evidence. */ }
      }
      const effects = owned.node.effects;
      if (!Array.isArray(effects)) continue;
      for (const effect of effects.slice(0, MAX_ITEMS)) { collector.readback(route); _projectEffect(effect, route, collector); }
    }
    collector.setScenario(route, styleFrame.created ? 'created' : 'reused');
  } catch (_) { _writeStatus(collector, route, 'unavailable'); }
}

function _projectEffect(effect, route, collector) {
  if (!isObject(effect)) return;
  collector.noteUnion('Effect', effect, 'type', route);
  if (effect.type === 'INNER_SHADOW') collector.readOwner('InnerShadowEffect', effect, route);
  else if (effect.type === 'LAYER_BLUR' || effect.type === 'BACKGROUND_BLUR') {
    collector.readOwner('BlurEffectBase', effect, route);
    collector.noteUnion('BlurEffect', effect, 'blurType', route);
    if (effect.blurType === 'PROGRESSIVE') collector.readOwner('BlurEffectProgressive', effect, route);
    else if (effect.blurType === 'NORMAL') collector.readOwner('BlurEffectNormal', effect, route);
  } else if (effect.type === 'NOISE') {
    collector.readOwner('NoiseEffectBase', effect, route);
    collector.noteUnion('NoiseEffect', effect, 'noiseType', route);
    if (effect.noiseType === 'MONOTONE') collector.readOwner('NoiseEffectMonotone', effect, route);
    else if (effect.noiseType === 'DUOTONE') collector.readOwner('NoiseEffectDuotone', effect, route);
    else if (effect.noiseType === 'MULTITONE') collector.readOwner('NoiseEffectMultitone', effect, route);
  } else if (effect.type === 'TEXTURE') collector.readOwner('TextureEffect', effect, route);
  else if (effect.type === 'GLASS') collector.readOwner('GlassEffect', effect, route);
}

async function _seedVector(api, page, plan, collector) {
  const route = 'vector-path-values';
  try {
    const serviceRoots = page.children.filter(node => node.type === 'FRAME'
      && node.getPluginData(SERVICE_MARK) === plan.service_graph_sha256);
    if (serviceRoots.length !== 1) { collector.setScenario(route, 'unavailable'); return; }
    const wrappers = (serviceRoots[0].children || []).filter(node => node.getPluginData(SERVICE_MARK) === 'Vector specimen');
    if (wrappers.length !== 1) { collector.setScenario(route, 'unavailable'); return; }
    const wrapper = wrappers[0];
    const vector = wrapper.type === 'VECTOR' ? wrapper : wrapper.findOne(node => node.type === 'VECTOR');
    if (!vector) { collector.setScenario(route, 'unavailable'); return; }
    collector.setScenario(route, 'reused');
    const paths = vector.vectorPaths;
    if (!Array.isArray(paths)) { collector.record('VectorLikeMixin', 'vectorPaths', route, 'unavailable', {state: 'NOT_ARRAY'}); return; }
    for (const path of paths.slice(0, MAX_ITEMS)) { collector.readback(route); collector.readOwner('VectorPath', path, route); }
  } catch (_) { _writeStatus(collector, route, 'unavailable'); }
}

async function _findServiceVariable(api, page, plan) {
  if (!plan.capabilities?.getLocalVariableCollectionsAsync || !plan.capabilities?.getVariableByIdAsync) return null;
  const serviceRoots = page.children.filter(node => node.type === 'FRAME'
    && node.getPluginData(SERVICE_MARK) === plan.service_graph_sha256);
  if (serviceRoots.length !== 1) return null;
  try {
    const collections = await api.variables.getLocalVariableCollectionsAsync();
    for (const collection of (Array.isArray(collections) ? collections : []).slice(0, 128)) {
      let owned = false;
      try { owned = collection.getPluginData(SERVICE_MARK) === plan.service_graph_sha256; } catch (_) {}
      if (!owned) continue;
      for (const variableId of (Array.isArray(collection.variableIds) ? collection.variableIds : []).slice(0, 128)) {
        try {
          const variable = await api.variables.getVariableByIdAsync(variableId);
          if (variable && variable.getPluginData(SERVICE_MARK) === plan.service_graph_sha256) return variable;
        } catch (_) {}
      }
    }
  } catch (_) {}
  return null;
}

async function runNativeValuePaths(api, plan = VALUE_PLAN) {
  if (!plan || api.editorType !== 'figma' || api.fileKey !== plan.file
      || api.currentPage.id !== plan.page) throw Error('Open the exact admitted Design file and page.');
  const page = api.currentPage;
  await page.loadAsync();
  const owned = await _ownedRoot(api, page, plan);
  const root = owned.node;
  const collector = createCollector(plan);
  const variable = await _findServiceVariable(api, page, plan);
  const styleFrame = _newFrame(api, root, plan, 'style-frame', 360, 20, 660, 520);
  // The returned root is private and all seed writes below target new marked children only.
  await _seedPrototype(api, root, plan, collector);
  await _seedGrid(api, styleFrame, plan, variable, collector);
  await _seedEffects(api, styleFrame, plan, variable, collector);
  await _seedVector(api, page, plan, collector);
  const report = collector.report();
  return {schema: plan.receipt_schema || 'figma-flow-native-value-observation-v1', graph_sha256: plan.graph_sha256,
    policy_sha256: plan.policy_sha256, api_source_ref: plan.api_source_ref,
    observed_at: new Date().toISOString(), ...report};
}

function showNativeValuePathReceipt(api, receipt) {
  const json = JSON.stringify(receipt);
  if (json.length > 120000) throw Error('Native value receipt exceeds the local 120 KB bound.');
  const chunks = json.match(/.{1,360}/g) || [];
  const parts = chunks.map((part, index) => `<p>ReceiptPart${String(index).padStart(3, '0')} ${part.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</p>`).join('');
  api.showUI(`<meta charset="utf-8"><h3>Native value path receipt</h3>${parts}<footer>Private local Figma value receipt · ${chunks.length} bounded parts</footer>`, {width: 700, height: 560});
}

if (typeof module !== 'undefined') module.exports = {runNativeValuePaths, safePathSummary: summarizeVectorPath};

if (typeof figma !== 'undefined' && typeof module === 'undefined') {
  runNativeValuePaths(figma, VALUE_PLAN).then(receipt => showNativeValuePathReceipt(figma, receipt))
    .catch(() => figma.closePlugin('Native value path inspection could not complete.'));
}
