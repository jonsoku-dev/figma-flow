/* Native Plugin API helper; usable directly in a Figma execution context. */
const SEMANTIC_COMPONENTS_RUNTIME = (() => {
  const CONTRACT_SCHEMA = 'figma-flow-semantic-family-contract-v1';
  const RESULT_SCHEMA = 'figma-flow-semantic-family-result-v1';
  const READBACK_SCHEMA = 'figma-flow-semantic-family-readback-v1';
  const WORKBENCH_SCHEMA = 'figma-flow-semantic-family-workbench-v1';
  const INSTANCE_META_SCHEMA = 'figma-flow-semantic-family-instance-v1';
  const WORKBENCH_PLUGIN_KEY = 'figmaFlowFamilyWorkbench';
  const INSTANCE_PLUGIN_KEY = 'figmaFlowFamilyInstance';
  const FIGMA_FLOW_KEY = 'figmaFlow';
  const IDENT_RE = /^[A-Za-z][A-Za-z0-9_-]*$/;
  const OWNER_RE = /^[A-Za-z][A-Za-z0-9._:-]{0,119}$/;

  const CANONICAL_FAMILIES = {
    field: {
      name: 'Field',
      layout: 'VERTICAL',
      requiredLayout: 'VERTICAL',
      canonicalStates: ['default', 'error', 'disabled'],
      canonicalTextSlots: ['field-label', 'field-help'],
      extraAxes: {}
    },
    input: {
      name: 'Input',
      layout: 'HORIZONTAL',
      requiredLayout: null,
      canonicalStates: ['default', 'focus', 'error', 'disabled'],
      canonicalTextSlots: ['input-value'],
      extraAxes: {}
    },
    checkbox: {
      name: 'Checkbox',
      layout: 'HORIZONTAL',
      requiredLayout: 'HORIZONTAL',
      canonicalStates: ['unchecked', 'checked', 'disabled'],
      canonicalTextSlots: ['checkbox-label'],
      extraAxes: {}
    },
    radio: {
      name: 'Radio',
      layout: 'HORIZONTAL',
      requiredLayout: 'HORIZONTAL',
      canonicalStates: ['unselected', 'selected', 'disabled'],
      canonicalTextSlots: ['radio-label'],
      extraAxes: {}
    },
    'table-row': {
      name: 'TableRow',
      layout: 'HORIZONTAL',
      requiredLayout: 'HORIZONTAL',
      canonicalStates: ['default', 'selected'],
      canonicalTextSlots: [],
      extraAxes: {}
    },
    'table-cell': {
      name: 'TableCell',
      layout: 'HORIZONTAL',
      requiredLayout: null,
      canonicalStates: ['default', 'header', 'selected', 'muted'],
      canonicalTextSlots: ['cell-text'],
      extraAxes: { role: ['header', 'body'] }
    }
  };

  const SECRET_PATTERNS = [
    /\bfigd_[A-Za-z0-9_-]{12,}\b/,
    /\bgh[pousr]_[A-Za-z0-9]{16,}\b/,
    /\bsk-[A-Za-z0-9_-]{16,}\b/,
    /\bAKIA[0-9A-Z]{16}\b/,
    /\bBearer\s+[A-Za-z0-9._-]{16,}/,
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    /(?:^|[\s"'])\/Users\/[^/\s]+/,
    /\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*\S+/i
  ];

  const copy = value => JSON.parse(JSON.stringify(value));
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  const checkSafeText = (value, context) => {
    if (typeof value !== 'string' || value.length > 2000) {
      throw new Error(`Invalid text value in ${context}`);
    }
    for (let i = 0; i < value.length; i += 1) {
      const code = value.charCodeAt(i);
      if (code < 32 && value[i] !== '\n' && value[i] !== '\t') {
        throw new Error(`Invalid control character in ${context}`);
      }
    }
    for (const pattern of SECRET_PATTERNS) {
      if (pattern.test(value)) {
        throw new Error(`Rejected secret-like or private path text in ${context}`);
      }
    }
  };

  const keyOf = node => {
    const path = [];
    for (let parent = node; parent; parent = parent.parent) {
      if (parent.type === 'INSTANCE') {
        let mapping;
        try { mapping = JSON.parse(parent.getPluginData('semanticComponent') || '{}'); }
        catch (_) { throw new Error(`Invalid instance semantic mapping: ${parent.id}`); }
        if (!path.length && mapping.key) return mapping.key;
        const entry = (mapping.childKeys || []).find(item => JSON.stringify(item.path) === JSON.stringify(path));
        if (entry && entry.key) return entry.key;
      }
      if (parent.parent) path.unshift(parent.parent.children.indexOf(parent));
    }
    return node.getPluginData('semanticKey');
  };

  const walk = (node, visit, path = []) => {
    visit(node, path);
    for (const [i, child] of (node.children || []).entries()) walk(child, visit, [...path, i]);
  };

  const visibleOnPage = (node, page) => {
    for (let p = node; p && p !== page; p = p.parent) if (p.visible === false) return false;
    return true;
  };

  const readJsonPluginData = (node, key, label) => {
    const raw = node.getPluginData(key);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_) {
      throw new Error(`Invalid ${label || key} metadata on ${node.id}`);
    }
  };

  const setFlowMetadata = (node, semanticId, extra = {}) => {
    const prior = readJsonPluginData(node, FIGMA_FLOW_KEY, FIGMA_FLOW_KEY) || {};
    node.setPluginData(FIGMA_FLOW_KEY, JSON.stringify({ ...prior, semantic_id: semanticId, ...extra }));
    node.setPluginData('semanticKey', semanticId);
  };

  const validateVariantPropsList = (variants, setId, seenVariantKeys, minVariants = 2) => {
    if (!Array.isArray(variants) || variants.length < minVariants) {
      throw new Error(`Invalid component set: ${setId || 'unnamed'}`);
    }
    const signatures = new Set();
    let propertyNames = null;
    for (const variant of variants) {
      if (!variant || typeof variant.key !== 'string' || !variant.key) {
        throw new Error(`Invalid variant in ${setId}`);
      }
      const names = Object.keys(variant.props || {}).sort();
      const signature = JSON.stringify(names.map(name => [name, variant.props[name]]));
      if (!names.length || signatures.has(signature) || seenVariantKeys.has(variant.key) ||
          names.some(name => /[,=]/.test(name) || typeof variant.props[name] !== 'string' || /[,=]/.test(variant.props[name]))) {
        throw new Error(`Invalid variant: ${variant.key}`);
      }
      if (propertyNames && JSON.stringify(names) !== propertyNames) {
        throw new Error(`Variant property mismatch: ${setId}`);
      }
      propertyNames = JSON.stringify(names);
      signatures.add(signature);
      seenVariantKeys.add(variant.key);
    }
  };

  const rollbackCreatedNodes = (nodes, rollbackErrors) => {
    const validNodes = (nodes || []).filter(Boolean);
    const createdSet = new Set(validNodes);
    const hasCreatedAncestor = node => {
      for (let p = node.parent; p; p = p.parent) {
        if (createdSet.has(p)) return true;
      }
      return false;
    };
    const rootsToRemove = validNodes.filter(node => !node.removed && !hasCreatedAncestor(node));
    for (const node of rootsToRemove) {
      try {
        if (!node.removed && typeof node.remove === 'function') node.remove();
      } catch (failure) {
        rollbackErrors.push(String(failure));
      }
    }
  };

  const hasValidPropertyKey = key => {
    if (typeof key !== 'string' || !key) return false;
    const hashIndex = key.indexOf('#');
    return hashIndex > 0 && hashIndex < key.length - 1;
  };

  const resolveCollisionSafePropertyName = (display, propId, usedNativeNames, reservedUniqueNames) => {
    const isBlocked = candidate => (
      !candidate ||
      candidate.includes('#') ||
      usedNativeNames.has(candidate) ||
      reservedUniqueNames.has(candidate)
    );
    const primary = `${display} (${propId})`;
    if (!isBlocked(primary)) return primary;
    let seq = 2;
    while (isBlocked(`${display} (${propId}:${seq})`)) seq += 1;
    return `${display} (${propId}:${seq})`;
  };

  const addDeclaredPropertySafely = (owner, setPlan, prop, nativeDefault, options, state) => {
    const defs = owner.componentPropertyDefinitions || {};
    const { usedActualKeys, usedNativeNames, reservedUniqueNames } = state;
    const prevSnapshots = new Map();
    for (const [k, meta] of usedActualKeys.entries()) {
      prevSnapshots.set(k, { meta, def: defs[k] ? copy(defs[k]) : null });
    }

    const restoreMutatedPrior = () => {
      const liveDefs = owner.componentPropertyDefinitions || {};
      for (const [k, { meta, def: prevDef }] of prevSnapshots.entries()) {
        const curDef = liveDefs[k];
        if (!prevDef || equal(curDef, prevDef)) continue;
        if (typeof owner.editComponentProperty !== 'function') {
          throw new Error(
            `Duplicate display name collision overwrote ${setPlan.id}.${meta.propId} (${k}) and editComponentProperty is unavailable`
          );
        }
        const revertPatch = { defaultValue: prevDef.defaultValue };
        if (prevDef.type === 'INSTANCE_SWAP') {
          revertPatch.preferredValues = copy(prevDef.preferredValues || []);
        }
        owner.editComponentProperty(k, revertPatch);
        const restored = (owner.componentPropertyDefinitions || {})[k];
        if (!equal(restored, prevDef)) {
          throw new Error(`Failed to restore overwritten property ${setPlan.id}.${meta.propId} (${k})`);
        }
      }
    };

    const evaluateResult = (nativeName, actualKey) => {
      const liveDefs = owner.componentPropertyDefinitions || {};
      const actualDef = typeof actualKey === 'string' && Object.prototype.hasOwnProperty.call(liveDefs, actualKey)
        ? liveDefs[actualKey]
        : null;
      let status = 'ok';
      if (typeof actualKey !== 'string' || !actualKey) status = 'actual-key-missing';
      else if (!hasValidPropertyKey(actualKey)) status = 'actual-key-unsuffixed';
      else if (usedActualKeys.has(actualKey)) status = 'duplicate-actual-key';
      else if (!actualDef) status = 'definition-missing';
      else if (actualDef.type !== prop.type) status = 'definition-type-mismatch';
      else if (actualDef.defaultValue !== nativeDefault) status = 'definition-default-mismatch';
      else if (prop.type === 'INSTANCE_SWAP' && !equal(actualDef.preferredValues || [], options.preferredValues)) {
        status = 'definition-preferred-mismatch';
      }
      return { nativeName, actualKey, actualDef, status, defCount: Object.keys(liveDefs).length };
    };

    const isRepeatedDisplay = usedNativeNames.has(prop.name);
    let skipDirectDuplicate = false;
    if (isRepeatedDisplay && typeof owner.editComponentProperty !== 'function') {
      for (const { meta, def: prevDef } of prevSnapshots.values()) {
        if (meta.nativeName === prop.name && prevDef && (
          prevDef.defaultValue !== nativeDefault ||
          (prop.type === 'INSTANCE_SWAP' && !equal(prevDef.preferredValues || [], options.preferredValues))
        )) {
          skipDirectDuplicate = true;
          break;
        }
      }
    }

    let result = null;
    if (!skipDirectDuplicate) {
      let thrown = null;
      let actualKey;
      try {
        actualKey = owner.addComponentProperty(prop.name, prop.type, nativeDefault, options);
      } catch (err) {
        thrown = err;
      }
      if (!thrown) {
        result = evaluateResult(prop.name, actualKey);
        if (result.status === 'ok') {
          let mutatedPrior = false;
          const liveDefs = owner.componentPropertyDefinitions || {};
          for (const [k, { def: prevDef }] of prevSnapshots.entries()) {
            if (prevDef && !equal(liveDefs[k], prevDef)) {
              mutatedPrior = true;
              break;
            }
          }
          if (!mutatedPrior) {
            return result;
          }
        }
      } else if (!isRepeatedDisplay) {
        throw thrown;
      }
      restoreMutatedPrior();
      if (!isRepeatedDisplay) {
        if (result.status === 'definition-preferred-mismatch') {
          throw new Error(
            `Native INSTANCE_SWAP preferredValues were not retained for ${setPlan.id}.${prop.id} ` +
            `(nativeName=${result.nativeName}, actualKey=${result.actualKey || 'none'}, status=${result.status}, defCount=${result.defCount})`
          );
        }
        throw new Error(
          `Native component property declaration was not retained for ${setPlan.id}.${prop.id} ` +
          `(nativeName=${result.nativeName}, actualKey=${result.actualKey || 'none'}, status=${result.status}, defCount=${result.defCount})`
        );
      }
    }

    const fallbackName = resolveCollisionSafePropertyName(prop.name, prop.id, usedNativeNames, reservedUniqueNames);
    const fallbackKey = owner.addComponentProperty(fallbackName, prop.type, nativeDefault, options);
    result = evaluateResult(fallbackName, fallbackKey);
    if (result.status === 'definition-preferred-mismatch') {
      throw new Error(
        `Native INSTANCE_SWAP preferredValues were not retained for ${setPlan.id}.${prop.id} ` +
        `(nativeName=${result.nativeName}, actualKey=${result.actualKey || 'none'}, status=${result.status}, defCount=${result.defCount})`
      );
    }
    if (result.status !== 'ok') {
      throw new Error(
        `Native component property declaration was not retained for ${setPlan.id}.${prop.id} ` +
        `(nativeName=${result.nativeName}, actualKey=${result.actualKey || 'none'}, status=${result.status}, defCount=${result.defCount})`
      );
    }
    return result;
  };

  const isFamilyContract = contract => Boolean(
    contract && typeof contract === 'object' && (
      contract.mode === 'additive-family-workbench' ||
      contract.schema === CONTRACT_SCHEMA ||
      contract.workbench !== undefined ||
      contract.ownerKey !== undefined ||
      (Array.isArray(contract.componentSets) && contract.componentSets.some(
        set => set && (set.family !== undefined || set.properties !== undefined || set.axes !== undefined)
      ))
    )
  );

  const solidPaint = rgba => ({
    type: 'SOLID',
    color: {
      r: typeof rgba?.r === 'number' ? rgba.r : 1,
      g: typeof rgba?.g === 'number' ? rgba.g : 1,
      b: typeof rgba?.b === 'number' ? rgba.b : 1
    },
    opacity: typeof rgba?.a === 'number' ? rgba.a : 1
  });

  const referenceFieldForType = type => (
    type === 'TEXT' ? 'characters' : type === 'BOOLEAN' ? 'visible' : 'mainComponent'
  );

  const targetSuffixForProp = (prop, setPlan) => {
    if (prop.targetKey === 'label') return '/label';
    if (prop.type === 'TEXT') return `/text:${prop.targetKey}`;
    if (prop.type === 'INSTANCE_SWAP') return `/slot:${prop.targetKey}`;
    if (setPlan.swapTargetsByKey.has(prop.targetKey)) return `/slot:${prop.targetKey}`;
    return `/text:${prop.targetKey}`;
  };

  const childNameForSuffix = suffix => suffix.slice(1);

  const setCoordinates = (node, x, y) => {
    node.x = x;
    node.y = y;
    node.relativeTransform = [[1, 0, x], [0, 1, y]];
  };

  const readPlacement = node => ({
    x: node.x,
    y: node.y,
    relativeTransform: copy(node.relativeTransform || [[1, 0, node.x || 0], [0, 1, node.y || 0]])
  });

  const buildInstanceSemanticMapping = (inst, instanceKey, sourceKey, setPlan) => {
    const childKeys = [];
    for (const [idx, child] of (inst.children || []).entries()) {
      let suffix = null;
      if (child.name === 'label') suffix = '/label';
      else if (child.name === 'indicator') suffix = '/indicator';
      else if (typeof child.name === 'string' && (child.name.startsWith('text:') || child.name.startsWith('slot:'))) {
        suffix = `/${child.name}`;
      } else {
        suffix = `/child:${idx}`;
      }
      const childKey = `${instanceKey}${suffix}`;
      childKeys.push({ path: [idx], key: childKey, id: child.id });
      const addNested = (subParent, prefixPath, prefixKey) => {
        for (const [subIdx, subChild] of (subParent.children || []).entries()) {
          const nextPath = [...prefixPath, subIdx];
          const nextKey = `${prefixKey}/child:${subIdx}`;
          childKeys.push({ path: nextPath, key: nextKey, id: subChild.id });
          addNested(subChild, nextPath, nextKey);
        }
      };
      if (setPlan) addNested(child, [idx], childKey);
    }
    return { key: instanceKey, sourceKey, childKeys };
  };

  const validateSwapRef = (ref, setsById, variantsByKey, context) => {
    if (!ref || typeof ref !== 'object' || Array.isArray(ref)) {
      throw new Error(`Invalid INSTANCE_SWAP reference in ${context}`);
    }
    const keys = Object.keys(ref).sort();
    if (keys.join(',') !== 'setId,variantKey' || typeof ref.setId !== 'string' || typeof ref.variantKey !== 'string') {
      throw new Error(`INSTANCE_SWAP reference requires {setId, variantKey} in ${context}`);
    }
    const targetSet = setsById.get(ref.setId);
    const targetVariant = variantsByKey.get(ref.variantKey);
    if (!targetSet || !targetVariant || targetVariant.setId !== ref.setId) {
      throw new Error(`INSTANCE_SWAP target refers to undeclared local set/variant in ${context}: ${ref.setId} / ${ref.variantKey}`);
    }
    return { setId: ref.setId, variantKey: ref.variantKey };
  };

  const normalizeThreeKindValue = (prop, rawVal, setsById, variantsByKey, context) => {
    if (prop.type === 'TEXT') {
      if (typeof rawVal !== 'string') throw new Error(`TEXT value must be string in ${context}`);
      checkSafeText(rawVal, context);
      return rawVal;
    }
    if (prop.type === 'BOOLEAN') {
      if (typeof rawVal !== 'boolean') throw new Error(`BOOLEAN value must be boolean in ${context}`);
      return rawVal;
    }
    const sRef = validateSwapRef(rawVal, setsById, variantsByKey, context);
    if (!prop.allowedSetIds.includes(sRef.setId)) {
      throw new Error(`Swap value outside allowedSetIds in ${context}: ${sRef.setId}`);
    }
    return sRef;
  };

  const validateFamilyContract = (figma, page, contract, { readOnly = false } = {}) => {
    if (!page || page.type !== 'PAGE') {
      throw new Error('Semantic component families require a valid Figma PAGE node');
    }
    if (!contract || typeof contract !== 'object' || Array.isArray(contract)) {
      throw new Error('Semantic component family contract must be an object');
    }
    if (contract.pageId !== undefined && contract.pageId !== page.id) {
      throw new Error(`Page scope mismatch: expected ${contract.pageId}, observed ${page.id}`);
    }
    if (contract.fileKey !== undefined && figma && figma.fileKey && contract.fileKey !== figma.fileKey) {
      throw new Error(`File scope mismatch: expected ${contract.fileKey}, observed ${figma.fileKey}`);
    }
    if (contract.schema !== CONTRACT_SCHEMA) {
      throw new Error(`Unsupported semantic family contract schema: ${contract.schema}`);
    }
    if (contract.version !== 1) {
      throw new Error(`Semantic family contract version must be 1: ${contract.version}`);
    }
    if (contract.mode !== undefined && contract.mode !== 'additive-family-workbench') {
      throw new Error(`Unsupported semantic family contract mode: ${contract.mode}`);
    }
    const ownerKey = contract.ownerKey;
    if (typeof ownerKey !== 'string' || !OWNER_RE.test(ownerKey)) {
      throw new Error(`Invalid ownerKey: ${ownerKey}`);
    }
    const wb = contract.workbench;
    if (!wb || typeof wb !== 'object' || Array.isArray(wb)) {
      throw new Error('Semantic family contract requires workbench configuration');
    }
    for (const k of ['frameKey', 'libraryKey', 'instancesFrameKey']) {
      if (typeof wb[k] !== 'string' || !wb[k].trim() || wb[k].length > 200) {
        throw new Error(`Invalid workbench.${k}`);
      }
    }
    if (new Set([wb.frameKey, wb.libraryKey, wb.instancesFrameKey]).size !== 3) {
      throw new Error('Workbench container semantic keys must be distinct');
    }
    const wbName = wb.name || 'NF-01 · Component families workbench';
    if (typeof wbName !== 'string' || !wbName.trim() || wbName.length > 120) {
      throw new Error('Invalid workbench.name');
    }
    checkSafeText(wbName, 'workbench.name');
    const pos = wb.position === undefined ? { x: 1680, y: 0 } : wb.position;
    if (!pos || typeof pos !== 'object' || typeof pos.x !== 'number' || typeof pos.y !== 'number' ||
        !Number.isFinite(pos.x) || !Number.isFinite(pos.y)) {
      throw new Error('Invalid workbench.position');
    }
    const defaultFont = wb.font || { family: 'Inter', style: 'Regular' };
    if (!defaultFont || typeof defaultFont.family !== 'string' || !defaultFont.family.trim() ||
        typeof defaultFont.style !== 'string' || !defaultFont.style.trim()) {
      throw new Error('Invalid workbench.font');
    }

    const rawSets = contract.componentSets;
    if (!Array.isArray(rawSets) || (!readOnly && rawSets.length < 1) || rawSets.length > 32) {
      throw new Error('Semantic family contract requires 1..32 componentSets');
    }
    const rawInstances = contract.instances === undefined ? [] : contract.instances;
    if (!Array.isArray(rawInstances) || rawInstances.length > 200) {
      throw new Error('Semantic family contract instances must be an array of at most 200 entries');
    }

    const setsById = new Map();
    const variantsByKey = new Map();
    const seenFamilies = new Set();
    const seenVariantKeys = new Set();
    const reservedKeys = new Set([wb.frameKey, wb.libraryKey, wb.instancesFrameKey]);

    for (const rawSet of rawSets) {
      if (!rawSet || typeof rawSet !== 'object' || Array.isArray(rawSet)) {
        throw new Error('Invalid componentSet entry');
      }
      if (typeof rawSet.id !== 'string' || !rawSet.id.trim() || reservedKeys.has(rawSet.id) || setsById.has(rawSet.id)) {
        throw new Error(`Invalid or duplicate componentSet id: ${rawSet?.id}`);
      }
      const fid = rawSet.family;
      if (typeof fid !== 'string' || !Object.prototype.hasOwnProperty.call(CANONICAL_FAMILIES, fid)) {
        throw new Error(`unsupported component family: ${fid}`);
      }
      if (seenFamilies.has(fid)) {
        throw new Error(`Duplicate component family declaration: ${fid}`);
      }
      seenFamilies.add(fid);
      reservedKeys.add(rawSet.id);
      const spec = CANONICAL_FAMILIES[fid];
      const layout = rawSet.layout || spec.layout;
      if (layout !== 'VERTICAL' && layout !== 'HORIZONTAL') {
        throw new Error(`Invalid layout for family ${fid}: ${layout}`);
      }
      if (spec.requiredLayout && layout !== spec.requiredLayout) {
        throw new Error(`Component family ${fid} requires ${spec.requiredLayout} layout`);
      }
      const setName = rawSet.name || spec.name;
      if (typeof setName !== 'string' || !setName.trim()) {
        throw new Error(`Invalid componentSet name for ${fid}`);
      }
      checkSafeText(setName, `${fid}.name`);

      const axes = rawSet.axes;
      if (!axes || typeof axes !== 'object' || Array.isArray(axes) || !Object.keys(axes).length) {
        throw new Error(`Component family axes required for ${fid}`);
      }
      const allowedAxisPairs = new Map();
      const seenAxisValues = new Set();
      for (const [axisName, values] of Object.entries(axes)) {
        if (!IDENT_RE.test(axisName) || !Array.isArray(values) || !values.length || new Set(values).size !== values.length) {
          throw new Error(`Invalid variant axis ${fid}.${axisName}`);
        }
        for (const val of values) {
          if (typeof val !== 'string' || !IDENT_RE.test(val) || seenAxisValues.has(val)) {
            throw new Error(`Invalid or duplicate axis value ${fid}.${axisName}.${val}`);
          }
          if (axisName === 'state' && !spec.canonicalStates.includes(val)) {
            throw new Error(`Undeclared state value for family ${fid}: ${val}`);
          }
          if (axisName !== 'state' && Object.prototype.hasOwnProperty.call(spec.extraAxes, axisName) &&
              !spec.extraAxes[axisName].includes(val)) {
            throw new Error(`Undeclared ${axisName} value for family ${fid}: ${val}`);
          }
          seenAxisValues.add(val);
          allowedAxisPairs.set(`${axisName}=${val}`, { axisName, val });
        }
      }

      validateVariantPropsList(rawSet.variants, rawSet.id, seenVariantKeys, 1);
      if (rawSet.variants.length !== seenAxisValues.size) {
        throw new Error(`Undeclared or missing variant combinations on ${rawSet.id}`);
      }
      const matchedAxisValues = new Set();
      const normVariants = rawSet.variants.map(v => {
        const entries = Object.entries(v.props || {});
        if (entries.length !== 1) {
          throw new Error(`Combinatorial or undeclared variant props unsupported on ${v.key}`);
        }
        const [aName, aVal] = entries[0];
        if (!allowedAxisPairs.has(`${aName}=${aVal}`) || matchedAxisValues.has(aVal)) {
          throw new Error(`Undeclared variant combination on ${v.key}: ${aName}=${aVal}`);
        }
        matchedAxisValues.add(aVal);
        const componentSemanticKey = `component.${v.key}`;
        if (reservedKeys.has(v.key) || reservedKeys.has(componentSemanticKey)) {
          throw new Error(`Semantic key collision on variant ${v.key}`);
        }
        reservedKeys.add(v.key);
        reservedKeys.add(componentSemanticKey);
        const defaultLabel = v.defaultLabel !== undefined ? v.defaultLabel : spec.name;
        checkSafeText(defaultLabel, `${v.key}.defaultLabel`);
        const normV = {
          key: v.key,
          componentKey: componentSemanticKey,
          setId: rawSet.id,
          variant: v.variant || aVal,
          props: copy(v.props),
          style: copy(v.style || {}),
          defaultLabel
        };
        variantsByKey.set(v.key, normV);
        return normV;
      });

      setsById.set(rawSet.id, {
        id: rawSet.id,
        family: fid,
        component: rawSet.component || fid,
        name: setName,
        layout,
        axes: copy(axes),
        axisNameSet: new Set(['Variant', ...Object.keys(axes)]),
        swapTargets: Array.isArray(rawSet.swapTargets) ? [...rawSet.swapTargets] : null,
        variants: normVariants,
        rawProperties: Array.isArray(rawSet.properties) ? rawSet.properties : null,
        properties: [],
        propsById: new Map(),
        textTargetsByKey: new Map(),
        swapTargetsByKey: new Map(),
        booleanTargetsByKey: new Map(),
        childSpecs: []
      });
    }

    const dependencies = new Map([...setsById.keys()].map(id => [id, new Set()]));

    for (const setPlan of setsById.values()) {
      const rawProps = setPlan.rawProperties === null ? [] : setPlan.rawProperties;
      if (!Array.isArray(rawProps) || rawProps.length > 32) {
        throw new Error(`Invalid properties list on ${setPlan.id}`);
      }
      if (setPlan.swapTargets !== null) {
        for (const stId of setPlan.swapTargets) {
          if (!setsById.has(stId)) {
            throw new Error(`Undeclared swapTargets entry on ${setPlan.id}: ${stId}`);
          }
        }
      }
      const targetTypePairs = new Set();
      for (const rawProp of rawProps) {
        if (!rawProp || typeof rawProp !== 'object' || Array.isArray(rawProp)) {
          throw new Error(`Invalid property entry on ${setPlan.id}`);
        }
        const pid = rawProp.id;
        if (typeof pid !== 'string' || !IDENT_RE.test(pid) || pid === '문구' || setPlan.propsById.has(pid)) {
          throw new Error(`Invalid or duplicate property id on ${setPlan.id}: ${pid}`);
        }
        const ptype = rawProp.type;
        if (ptype !== 'TEXT' && ptype !== 'BOOLEAN' && ptype !== 'INSTANCE_SWAP') {
          throw new Error(`Unsupported property type on ${setPlan.id}.${pid}: ${ptype}`);
        }
        const pname = rawProp.name !== undefined ? rawProp.name : pid;
        if (typeof pname !== 'string' || !pname.trim() || pname.includes('#') || pname === '문구') {
          throw new Error(`Invalid property display name on ${setPlan.id}.${pid}: ${pname}`);
        }
        checkSafeText(pname, `${setPlan.id}.${pid}.name`);
        if (setPlan.axisNameSet.has(pid) || setPlan.axisNameSet.has(pname)) {
          throw new Error(`Property collides with variant axis on ${setPlan.id}.${pid}`);
        }
        const targetKey = rawProp.targetKey !== undefined ? rawProp.targetKey : rawProp.target;
        if ((rawProp.targetKey !== undefined && rawProp.target !== undefined && rawProp.targetKey !== rawProp.target) ||
            typeof targetKey !== 'string' || !IDENT_RE.test(targetKey)) {
          throw new Error(`Invalid targetKey on ${setPlan.id}.${pid}`);
        }
        const pairKey = `${ptype}:${targetKey}`;
        if (targetTypePairs.has(pairKey)) {
          throw new Error(`Duplicate ${ptype} property binding target ${targetKey} on ${setPlan.id}`);
        }
        targetTypePairs.add(pairKey);

        const normProp = {
          id: pid,
          name: pname,
          type: ptype,
          targetKey
        };

        if (ptype === 'TEXT' || ptype === 'BOOLEAN') {
          normProp.defaultValue = normalizeThreeKindValue(
            normProp, rawProp.defaultValue, setsById, variantsByKey, `${setPlan.id}.${pid}.defaultValue`
          );
          if (ptype === 'TEXT') setPlan.textTargetsByKey.set(targetKey, normProp);
          else setPlan.booleanTargetsByKey.set(targetKey, normProp);
        } else {
          if (targetKey === 'label') {
            throw new Error(`INSTANCE_SWAP targetKey cannot be label on ${setPlan.id}.${pid}`);
          }
          const rawAllowed = rawProp.allowedSetIds;
          if (!Array.isArray(rawAllowed) || !rawAllowed.length || rawAllowed.length > 16) {
            throw new Error(`INSTANCE_SWAP allowedSetIds required on ${setPlan.id}.${pid}`);
          }
          const allowedSetIds = [];
          for (const allowedId of rawAllowed) {
            const allowedSet = setsById.get(allowedId);
            if (!allowedSet) {
              throw new Error(`Disallowed or unknown swap target set ${allowedId} on ${setPlan.id}.${pid}`);
            }
            if (setPlan.family === 'table-row' && allowedSet.family !== 'table-cell') {
              throw new Error(`table-row swap slots can only target table-cell (${setPlan.id}.${pid})`);
            }
            if (setPlan.swapTargets !== null && !setPlan.swapTargets.includes(allowedId)) {
              throw new Error(`allowedSetIds entry ${allowedId} missing from set.swapTargets on ${setPlan.id}.${pid}`);
            }
            if (!allowedSetIds.includes(allowedId)) allowedSetIds.push(allowedId);
            dependencies.get(setPlan.id).add(allowedId);
          }
          normProp.allowedSetIds = allowedSetIds;
          const defRef = normalizeThreeKindValue(
            normProp, rawProp.defaultValue, setsById, variantsByKey, `${setPlan.id}.${pid}.defaultValue`
          );
          const rawPreferred = rawProp.preferredValues === undefined ? [defRef] : rawProp.preferredValues;
          if (!Array.isArray(rawPreferred) || rawPreferred.length > 100) {
            throw new Error(`Invalid preferredValues on ${setPlan.id}.${pid}`);
          }
          const preferredValues = rawPreferred.map((pref, idx) => {
            const pRef = normalizeThreeKindValue(
              normProp, pref, setsById, variantsByKey, `${setPlan.id}.${pid}.preferredValues[${idx}]`
            );
            dependencies.get(setPlan.id).add(pRef.setId);
            return pRef;
          });
          normProp.defaultValue = defRef;
          normProp.preferredValues = preferredValues;
          setPlan.swapTargetsByKey.set(targetKey, normProp);
        }

        setPlan.properties.push(normProp);
        setPlan.propsById.set(pid, normProp);
      }

      for (const targetKey of setPlan.swapTargetsByKey.keys()) {
        if (setPlan.textTargetsByKey.has(targetKey)) {
          throw new Error(`Property targetKey ${targetKey} cannot be both TEXT and INSTANCE_SWAP on ${setPlan.id}`);
        }
      }
      const canonicalTextSlots = new Set(CANONICAL_FAMILIES[setPlan.family].canonicalTextSlots);
      for (const [targetKey] of setPlan.booleanTargetsByKey) {
        const valid = targetKey === 'label' ||
          setPlan.textTargetsByKey.has(targetKey) ||
          setPlan.swapTargetsByKey.has(targetKey) ||
          canonicalTextSlots.has(targetKey);
        if (!valid) {
          throw new Error(`Disallowed or missing BOOLEAN targetKey ${targetKey} on ${setPlan.id}`);
        }
      }

      // Build canonical owned child specifications for every variant in setPlan
      const childSpecs = [];
      if (setPlan.family === 'checkbox' || setPlan.family === 'radio') {
        childSpecs.push({ kind: 'indicator', name: 'indicator', suffix: '/indicator', targetKey: null });
      }
      const needsPrimaryLabel =
        setPlan.textTargetsByKey.has('label') ||
        setPlan.booleanTargetsByKey.has('label') ||
        (setPlan.textTargetsByKey.size === 0 && setPlan.swapTargetsByKey.size === 0 && setPlan.booleanTargetsByKey.size === 0);
      if (needsPrimaryLabel) {
        const labelProp = setPlan.textTargetsByKey.get('label');
        childSpecs.push({
          kind: 'text',
          name: 'label',
          suffix: '/label',
          targetKey: 'label',
          initialText: labelProp ? labelProp.defaultValue : null
        });
      }
      const materializedTargets = new Set(needsPrimaryLabel ? ['label'] : []);
      const orderedTargetProps = [...setPlan.properties];
      if (setPlan.family === 'field') {
        const rank = p => {
          if (p.targetKey === 'field-label' || p.targetKey === 'label') return 0;
          if (p.type === 'INSTANCE_SWAP' || setPlan.swapTargetsByKey.has(p.targetKey)) return 1;
          if (p.targetKey === 'field-help') return 2;
          return 1.5;
        };
        orderedTargetProps.sort((a, b) => rank(a) - rank(b));
      }
      for (const prop of orderedTargetProps) {
        if (materializedTargets.has(prop.targetKey)) continue;
        if (prop.type === 'INSTANCE_SWAP') {
          materializedTargets.add(prop.targetKey);
          childSpecs.push({
            kind: 'slot',
            name: `slot:${prop.targetKey}`,
            suffix: `/slot:${prop.targetKey}`,
            targetKey: prop.targetKey,
            swapProp: prop
          });
        } else if (prop.type === 'TEXT' && prop.targetKey !== 'label') {
          materializedTargets.add(prop.targetKey);
          childSpecs.push({
            kind: 'text',
            name: `text:${prop.targetKey}`,
            suffix: `/text:${prop.targetKey}`,
            targetKey: prop.targetKey,
            initialText: prop.defaultValue
          });
        } else if (prop.type === 'BOOLEAN' && !setPlan.swapTargetsByKey.has(prop.targetKey) &&
                   !setPlan.textTargetsByKey.has(prop.targetKey) && prop.targetKey !== 'label') {
          materializedTargets.add(prop.targetKey);
          childSpecs.push({
            kind: 'text',
            name: `text:${prop.targetKey}`,
            suffix: `/text:${prop.targetKey}`,
            targetKey: prop.targetKey,
            initialText: prop.targetKey
          });
        }
      }
      for (const prop of setPlan.properties) {
        prop.referenceField = referenceFieldForType(prop.type);
        prop.targetSuffix = targetSuffixForProp(prop, setPlan);
        prop.targetChildName = childNameForSuffix(prop.targetSuffix);
      }
      setPlan.childSpecs = childSpecs;
    }

    // Topological sort & cycle detection on INSTANCE_SWAP dependencies
    const visiting = new Set();
    const visited = new Set();
    const orderedSets = [];
    const visitSet = setId => {
      if (visiting.has(setId)) {
        throw new Error(`Cyclic INSTANCE_SWAP dependency involving ${setId}`);
      }
      if (visited.has(setId)) return;
      visiting.add(setId);
      for (const depId of dependencies.get(setId) || []) {
        visitSet(depId);
      }
      visiting.delete(setId);
      visited.add(setId);
      orderedSets.push(setsById.get(setId));
    };
    for (const setId of setsById.keys()) visitSet(setId);

    const instances = [];
    const seenInstanceKeys = new Set();
    for (const rawInst of rawInstances) {
      if (!rawInst || typeof rawInst !== 'object' || Array.isArray(rawInst)) {
        throw new Error('Invalid instance declaration');
      }
      if (typeof rawInst.key !== 'string' || !rawInst.key.trim() ||
          seenInstanceKeys.has(rawInst.key) || reservedKeys.has(rawInst.key)) {
        throw new Error(`Invalid or colliding instance key: ${rawInst?.key}`);
      }
      seenInstanceKeys.add(rawInst.key);
      reservedKeys.add(rawInst.key);
      const setPlan = setsById.get(rawInst.setId);
      const variantPlan = variantsByKey.get(rawInst.variantKey);
      if (!setPlan || !variantPlan || variantPlan.setId !== setPlan.id) {
        throw new Error(`Instance ${rawInst.key} references undeclared setId/variantKey: ${rawInst.setId} / ${rawInst.variantKey}`);
      }
      const rawValues = rawInst.propertyValues === undefined ? {} : rawInst.propertyValues;
      if (!rawValues || typeof rawValues !== 'object' || Array.isArray(rawValues)) {
        throw new Error(`Invalid propertyValues on instance ${rawInst.key}`);
      }
      const normValues = {};
      for (const [pid, val] of Object.entries(rawValues)) {
        const prop = setPlan.propsById.get(pid);
        if (!prop) {
          throw new Error(`Unknown property ${pid} in instance ${rawInst.key}`);
        }
        normValues[pid] = normalizeThreeKindValue(
          prop, val, setsById, variantsByKey, `${rawInst.key}.propertyValues.${pid}`
        );
      }
      const instName = rawInst.name || rawInst.elementId || setPlan.name;
      checkSafeText(String(instName), `${rawInst.key}.name`);
      if (rawInst.text !== undefined) checkSafeText(String(rawInst.text), `${rawInst.key}.text`);
      instances.push({
        key: rawInst.key,
        elementId: rawInst.elementId || null,
        setId: setPlan.id,
        variantKey: variantPlan.key,
        name: String(instName),
        text: rawInst.text !== undefined ? String(rawInst.text) : variantPlan.defaultLabel,
        propertyValues: normValues,
        domSource: rawInst.domSource ? copy(rawInst.domSource) : undefined
      });
    }

    return {
      ownerKey,
      expectedRevision: contract.expectedRevision,
      workbench: {
        frameKey: wb.frameKey,
        libraryKey: wb.libraryKey,
        instancesFrameKey: wb.instancesFrameKey,
        name: wbName,
        position: { x: pos.x, y: pos.y },
        font: { family: defaultFont.family, style: defaultFont.style }
      },
      setsInContractOrder: rawSets.map(s => setsById.get(s.id)),
      orderedSets,
      setsById,
      variantsByKey,
      instances,
      reservedKeys
    };
  };

  const applyVariantVisualStyle = (main, setPlan, variantPlan, defaultFont) => {
    const style = variantPlan.style || {};
    main.layoutMode = setPlan.layout;
    main.primaryAxisSizingMode = 'AUTO';
    main.counterAxisSizingMode = 'AUTO';
    main.primaryAxisAlignItems = 'MIN';
    main.counterAxisAlignItems = setPlan.layout === 'HORIZONTAL' ? 'CENTER' : 'MIN';
    main.paddingTop = typeof style.paddingTop === 'number' ? style.paddingTop : 8;
    main.paddingRight = typeof style.paddingRight === 'number' ? style.paddingRight : 12;
    main.paddingBottom = typeof style.paddingBottom === 'number' ? style.paddingBottom : 8;
    main.paddingLeft = typeof style.paddingLeft === 'number' ? style.paddingLeft : 12;
    main.itemSpacing = typeof style.itemSpacing === 'number' ? style.itemSpacing : 8;
    if ('cornerRadius' in main) {
      main.cornerRadius = typeof style.cornerRadius === 'number' ? style.cornerRadius : 0;
    }
    main.fills = style.background ? [solidPaint(style.background)] : [solidPaint({ r: 1, g: 1, b: 1, a: 1 })];
    main.strokes = style.borderColor ? [solidPaint(style.borderColor)] : [];
    if (main.strokes.length && 'strokeWeight' in main) main.strokeWeight = 1;
    main.clipsContent = false;

    const fontName = {
      family: typeof style.fontFamily === 'string' && style.fontFamily ? style.fontFamily : defaultFont.family,
      style: defaultFont.style || 'Regular'
    };
    const fontSize = typeof style.fontSize === 'number' && style.fontSize > 0 ? style.fontSize : 14;
    const inkPaint = solidPaint(style.color || { r: 0.1255, g: 0.1412, b: 0.1647, a: 1 });

    for (const child of main.children || []) {
      if (child.type === 'TEXT') {
        child.fontName = fontName;
        child.fontSize = fontSize;
        child.fills = [inkPaint];
      } else if (child.name === 'indicator') {
        const active = variantPlan.variant === 'checked' || variantPlan.variant === 'selected';
        if ('cornerRadius' in child) child.cornerRadius = setPlan.family === 'radio' ? 8 : 3;
        child.fills = [active ? inkPaint : solidPaint(style.background || { r: 1, g: 1, b: 1, a: 1 })];
        child.strokes = [solidPaint(style.borderColor || style.color || { r: 0.5, g: 0.5, b: 0.5, a: 1 })];
        if ('strokeWeight' in child) child.strokeWeight = 1;
      }
    }
  };

  const inspectWorkbenchState = async (figma, page, validated, { strictContractMatch = true } = {}) => {
    if (page && typeof page.loadAsync === 'function') {
      await page.loadAsync();
    }
    const allNodes = [];
    walk(page, node => {
      if (node !== page) allNodes.push(node);
    });

    const isDescendantOf = (node, ancestor) => {
      for (let p = node.parent; p; p = p.parent) {
        if (p === ancestor) return true;
      }
      return false;
    };

    const workbenchMatches = allNodes.filter(node => {
      const sk = node.getPluginData('semanticKey');
      const marker = readJsonPluginData(node, WORKBENCH_PLUGIN_KEY, WORKBENCH_PLUGIN_KEY);
      return sk === validated.workbench.frameKey || (marker && marker.ownerKey === validated.ownerKey);
    });

    if (workbenchMatches.length > 1) {
      throw new Error(`Ambiguous duplicate workbench frames for ${validated.workbench.frameKey}`);
    }

    const workbenchFrame = workbenchMatches[0] || null;
    const siblingIds = (page.children || []).filter(n => n !== workbenchFrame).map(n => n.id);

    if (!workbenchFrame) {
      // Ensure no partial or colliding owned keys exist outside an owned workbench
      for (const node of allNodes) {
        const sk = node.getPluginData('semanticKey');
        if (sk && (validated.reservedKeys.has(sk) || sk.startsWith(`${validated.ownerKey}/`) || sk.startsWith(`component.${validated.ownerKey}/`))) {
          throw new Error(`Partial or colliding semantic family node outside owned workbench: ${sk}`);
        }
      }
      if (validated.expectedRevision !== undefined && validated.expectedRevision !== null && validated.expectedRevision !== 0) {
        throw new Error(`CAS revision mismatch: expected ${validated.expectedRevision}, observed absent workbench`);
      }
      return {
        status: 'absent',
        workbenchFrame: null,
        siblingIds
      };
    }

    if (workbenchFrame.type !== 'FRAME' || workbenchFrame.parent !== page || workbenchFrame.visible === false ||
        workbenchFrame.getPluginData('semanticKey') !== validated.workbench.frameKey) {
      throw new Error(`Owned workbench frame ${validated.workbench.frameKey} is misplaced, hidden, or invalid`);
    }

    const marker = readJsonPluginData(workbenchFrame, WORKBENCH_PLUGIN_KEY, WORKBENCH_PLUGIN_KEY);
    if (!marker || marker.schema !== WORKBENCH_SCHEMA || marker.ownerKey !== validated.ownerKey ||
        marker.pageId !== page.id || marker.frameKey !== validated.workbench.frameKey ||
        marker.libraryKey !== validated.workbench.libraryKey ||
        marker.instancesFrameKey !== validated.workbench.instancesFrameKey) {
      throw new Error(`Corrupt or foreign workbench ownership metadata on ${workbenchFrame.id}`);
    }
    if (marker.fileKey && figma && figma.fileKey && marker.fileKey !== figma.fileKey) {
      throw new Error(`Workbench fileKey mismatch: expected ${marker.fileKey}, observed ${figma.fileKey}`);
    }
    if (validated.expectedRevision !== undefined && validated.expectedRevision !== null &&
        marker.revision !== validated.expectedRevision) {
      throw new Error(`CAS revision mismatch: expected ${validated.expectedRevision}, observed ${marker.revision}`);
    }

    // Check no owned semantic keys exist outside workbenchFrame
    for (const node of allNodes) {
      if (node === workbenchFrame || isDescendantOf(node, workbenchFrame)) continue;
      const sk = node.getPluginData('semanticKey');
      if (sk && (validated.reservedKeys.has(sk) || sk.startsWith(`${validated.ownerKey}/`) || sk.startsWith(`component.${validated.ownerKey}/`))) {
        throw new Error(`Semantic key collision outside owned workbench: ${sk}`);
      }
    }

    const wbNodes = [];
    walk(workbenchFrame, node => {
      if (node !== workbenchFrame) wbNodes.push(node);
    });

    const findDirectFrame = (parent, semKey) => {
      const hits = (parent.children || []).filter(n => n.getPluginData('semanticKey') === semKey);
      if (hits.length !== 1 || hits[0].type !== 'FRAME' || hits[0].visible === false) {
        throw new Error(`Missing or invalid owned workbench container: ${semKey}`);
      }
      return hits[0];
    };

    const libraryFrame = findDirectFrame(workbenchFrame, validated.workbench.libraryKey);
    const instancesFrame = findDirectFrame(workbenchFrame, validated.workbench.instancesFrameKey);

    // Check that no previously owned sets or instances were destructively removed from contract
    if (strictContractMatch) {
      for (const prevSetId of marker.setIds || []) {
        if (!validated.setsById.has(prevSetId)) {
          throw new Error(`Conflict: cannot remove existing owned componentSet ${prevSetId}`);
        }
      }
      for (const prevInstKey of marker.instanceKeys || []) {
        if (!validated.instances.some(inst => inst.key === prevInstKey)) {
          throw new Error(`Conflict: cannot remove existing owned instance ${prevInstKey}`);
        }
      }
    }

    const existingSets = new Map();
    const mainsByVariantKey = new Map();
    const variantMetaByMainId = new Map();

    // Inspect existing COMPONENT_SETs in topological order so swap targets resolve first
    for (const setPlan of validated.orderedSets) {
      const setHits = (libraryFrame.children || []).filter(n => n.getPluginData('semanticKey') === setPlan.id);
      if (setHits.length > 1) {
        throw new Error(`Duplicate COMPONENT_SET for ${setPlan.id}`);
      }
      if (setHits.length === 0) {
        if ((marker.setIds || []).includes(setPlan.id)) {
          throw new Error(`Missing previously owned COMPONENT_SET: ${setPlan.id}`);
        }
        continue;
      }
      const nativeSet = setHits[0];
      if (nativeSet.type !== 'COMPONENT_SET' || nativeSet.visible === false) {
        throw new Error(`Invalid COMPONENT_SET node for ${setPlan.id}`);
      }
      const setFlow = readJsonPluginData(nativeSet, FIGMA_FLOW_KEY, FIGMA_FLOW_KEY) || {};
      const declaredKeys = setFlow.declared_property_keys || {};
      const declaredContracts = setFlow.declared_property_contracts || {};

      // Verify existing declared properties were not removed or schema-mutated incompatibly
      for (const [prevPropId, prevContract] of Object.entries(declaredContracts)) {
        const nextProp = setPlan.propsById.get(prevPropId);
        if (!nextProp) {
          throw new Error(`Conflict: cannot delete existing component property ${setPlan.id}.${prevPropId}`);
        }
        if (nextProp.type !== prevContract.type || nextProp.targetKey !== prevContract.targetKey ||
            nextProp.name !== prevContract.name) {
          throw new Error(`Conflict: incompatible schema change on property ${setPlan.id}.${prevPropId}`);
        }
      }

      if ((nativeSet.children || []).length !== setPlan.variants.length) {
        throw new Error(`Conflict: variant count mismatch on existing set ${setPlan.id}`);
      }

      const setMains = new Map();
      for (const variantPlan of setPlan.variants) {
        const mainHits = (nativeSet.children || []).filter(
          c => c.getPluginData('semanticKey') === variantPlan.componentKey
        );
        if (mainHits.length !== 1 || mainHits[0].type !== 'COMPONENT') {
          throw new Error(`Missing or detached COMPONENT variant: ${variantPlan.key}`);
        }
        const main = mainHits[0];
        if (main.layoutMode !== setPlan.layout) {
          throw new Error(`Variant layoutMode drift on ${variantPlan.key}: expected ${setPlan.layout}, observed ${main.layoutMode}`);
        }
        for (const [axisName, axisVal] of Object.entries(variantPlan.props)) {
          if (!main.variantProperties || main.variantProperties[axisName] !== axisVal) {
            throw new Error(`Variant property drift on ${variantPlan.key}: expected ${axisName}=${axisVal}`);
          }
        }
        if (Object.keys(main.variantProperties || {}).length !== Object.keys(variantPlan.props).length) {
          throw new Error(`Undeclared extra variant axis on ${variantPlan.key}`);
        }
        setMains.set(variantPlan.key, main);
        mainsByVariantKey.set(variantPlan.key, main);
        variantMetaByMainId.set(main.id, { setId: setPlan.id, variantKey: variantPlan.key, family: setPlan.family });
      }

      const defs = nativeSet.componentPropertyDefinitions || {};
      const seenActualKeys = new Set();
      const propStates = new Map();

      for (const prop of setPlan.properties) {
        const actualKey = declaredKeys[prop.id];
        if (!hasValidPropertyKey(actualKey) || seenActualKeys.has(actualKey)) {
          throw new Error(`Missing or colliding suffixed actualKey for ${setPlan.id}.${prop.id}`);
        }
        seenActualKeys.add(actualKey);
        const def = defs[actualKey];
        if (!def || def.type !== prop.type) {
          throw new Error(`Native componentPropertyDefinitions mismatch on ${setPlan.id}.${prop.id} (${actualKey})`);
        }

        // Verify target child & componentPropertyReferences on EVERY variant of this set
        const variantChildren = new Map();
        for (const variantPlan of setPlan.variants) {
          const main = setMains.get(variantPlan.key);
          const expectedChildSemKey = `${variantPlan.componentKey}${prop.targetSuffix}`;
          const childHits = (main.children || []).filter(
            c => c.name === prop.targetChildName || c.getPluginData('semanticKey') === expectedChildSemKey
          );
          if (childHits.length !== 1) {
            throw new Error(`Missing or ambiguous target child ${expectedChildSemKey} on ${variantPlan.key}`);
          }
          const child = childHits[0];
          if (prop.type === 'TEXT' && child.type !== 'TEXT') {
            throw new Error(`TEXT property target is not a TEXT node: ${expectedChildSemKey}`);
          }
          if (prop.type === 'INSTANCE_SWAP' && child.type !== 'INSTANCE') {
            throw new Error(`INSTANCE_SWAP property target is not an INSTANCE node: ${expectedChildSemKey}`);
          }
          if (child.componentPropertyReferences?.[prop.referenceField] !== actualKey) {
            throw new Error(`Broken componentPropertyReferences.${prop.referenceField} on ${expectedChildSemKey}`);
          }
          if (prop.type === 'TEXT' && child.characters !== def.defaultValue) {
            throw new Error(`Main variant TEXT child out of sync with definition default on ${expectedChildSemKey}`);
          }
          if (prop.type === 'BOOLEAN' && child.visible !== def.defaultValue) {
            throw new Error(`Main variant BOOLEAN child out of sync with definition default on ${expectedChildSemKey}`);
          }
          if (prop.type === 'INSTANCE_SWAP') {
            const slotMain = await child.getMainComponentAsync();
            if (!slotMain || slotMain.id !== def.defaultValue) {
              throw new Error(`Main variant INSTANCE_SWAP slot out of sync with definition default on ${expectedChildSemKey}`);
            }
          }
          variantChildren.set(variantPlan.key, child);
        }

        let liveDefaultNorm;
        if (prop.type === 'TEXT' || prop.type === 'BOOLEAN') {
          liveDefaultNorm = def.defaultValue;
        } else {
          const liveTargetMeta = variantMetaByMainId.get(def.defaultValue);
          if (!liveTargetMeta || !prop.allowedSetIds.includes(liveTargetMeta.setId)) {
            throw new Error(`Main INSTANCE_SWAP default on ${setPlan.id}.${prop.id} points outside allowedSetIds`);
          }
          liveDefaultNorm = { setId: liveTargetMeta.setId, variantKey: liveTargetMeta.variantKey };
        }

        let desiredNativeDefault;
        let desiredPreferredValues;
        if (prop.type === 'TEXT' || prop.type === 'BOOLEAN') {
          desiredNativeDefault = prop.defaultValue;
        } else {
          const targetMain = mainsByVariantKey.get(prop.defaultValue.variantKey);
          if (!targetMain) {
            throw new Error(`Unresolved swap default target ${prop.defaultValue.variantKey} for ${setPlan.id}.${prop.id}`);
          }
          desiredNativeDefault = targetMain.id;
          desiredPreferredValues = prop.preferredValues.map(pref => {
            const pm = mainsByVariantKey.get(pref.variantKey);
            if (!pm || !pm.key) {
              throw new Error(`Native swap preferred target missing component key: ${pref.variantKey}`);
            }
            return { type: 'COMPONENT', key: pm.key };
          });
        }

        const defaultChanged = def.defaultValue !== desiredNativeDefault;
        const preferredChanged = prop.type === 'INSTANCE_SWAP' &&
          !equal(def.preferredValues || [], desiredPreferredValues || []);

        if ((defaultChanged || preferredChanged) && strictContractMatch && typeof nativeSet.editComponentProperty !== 'function') {
          throw new Error(`Conflict: editComponentProperty API unavailable to update main default on ${setPlan.id}.${prop.id}`);
        }

        propStates.set(prop.id, {
          prop,
          actualKey,
          liveDefinition: copy(def),
          liveDefaultNorm,
          desiredNativeDefault,
          desiredPreferredValues,
          defaultChanged,
          preferredChanged,
          variantChildren
        });
      }

      // Check if variant styles changed vs stored style metadata
      let styleChanged = false;
      const prevVariantStyles = setFlow.variant_styles || {};
      for (const variantPlan of setPlan.variants) {
        if (!equal(prevVariantStyles[variantPlan.key] || {}, variantPlan.style || {})) {
          styleChanged = true;
        }
      }

      existingSets.set(setPlan.id, {
        setPlan,
        nativeSet,
        setMains,
        declaredKeys: copy(declaredKeys),
        declaredContracts: copy(declaredContracts),
        propStates,
        styleChanged
      });
    }

    const existingInstances = new Map();
    const preservedOverrides = [];
    const preservedPlacements = [];

    for (const instReq of validated.instances) {
      const instHits = (instancesFrame.children || []).filter(n => keyOf(n) === instReq.key || n.getPluginData('semanticKey') === instReq.key);
      if (instHits.length > 1) {
        throw new Error(`Duplicate INSTANCE node for ${instReq.key}`);
      }
      if (instHits.length === 0) {
        if ((marker.instanceKeys || []).includes(instReq.key)) {
          throw new Error(`Missing previously owned INSTANCE: ${instReq.key}`);
        }
        continue;
      }
      const inst = instHits[0];
      if (inst.type !== 'INSTANCE' || inst.visible === false) {
        throw new Error(`Detached, hidden, or non-INSTANCE node at ${instReq.key}`);
      }
      const instMeta = readJsonPluginData(inst, INSTANCE_PLUGIN_KEY, INSTANCE_PLUGIN_KEY);
      if (!instMeta || instMeta.schema !== INSTANCE_META_SCHEMA || instMeta.key !== instReq.key ||
          instMeta.setId !== instReq.setId || !instMeta.props || typeof instMeta.props !== 'object' ||
          !instMeta.authoredPlacement) {
        throw new Error(`Conflict: missing or corrupt instance authoring metadata on ${instReq.key}`);
      }

      const setInfo = existingSets.get(instReq.setId);
      if (!setInfo) {
        throw new Error(`Instance ${instReq.key} exists without owned set ${instReq.setId}`);
      }
      const liveMain = await inst.getMainComponentAsync();
      if (!liveMain || liveMain.parent !== setInfo.nativeSet) {
        throw new Error(`Disconnected or foreign main component on instance ${instReq.key}`);
      }
      const liveMainMeta = variantMetaByMainId.get(liveMain.id);
      if (!liveMainMeta || liveMainMeta.setId !== instReq.setId) {
        throw new Error(`Instance ${instReq.key} points to undeclared variant ${liveMain.id}`);
      }

      const liveVariantKey = liveMainMeta.variantKey;
      const variantUserOverridden = liveVariantKey !== instMeta.authoredVariantKey;
      if (variantUserOverridden) {
        preservedOverrides.push({
          instanceKey: instReq.key,
          instanceId: inst.id,
          propId: 'variant',
          actualKey: 'VARIANT',
          type: 'VARIANT',
          authoredValue: instMeta.authoredVariantKey,
          contractValue: instReq.variantKey,
          liveValue: liveVariantKey
        });
      }

      const livePlacement = readPlacement(inst);
      const placementModified = !equal(livePlacement, instMeta.authoredPlacement);
      if (placementModified) {
        preservedPlacements.push({
          instanceKey: instReq.key,
          instanceId: inst.id,
          authoredPlacement: copy(instMeta.authoredPlacement),
          livePlacement: copy(livePlacement)
        });
      }

      const livePropObs = new Map();
      const resolvedProperties = {};
      const liveCompProps = inst.componentProperties || {};

      for (const prop of setInfo.setPlan.properties) {
        const pState = setInfo.propStates.get(prop.id);
        const actualKey = pState.actualKey;
        const propAuthorMeta = instMeta.props[prop.id];
        if (!propAuthorMeta) {
          throw new Error(`Conflict: missing authoring metadata for property ${instReq.key}.${prop.id}`);
        }
        const cpEntry = liveCompProps[actualKey];
        if (!cpEntry || cpEntry.type !== prop.type) {
          throw new Error(`Missing or mismatched instance.componentProperties[${actualKey}] on ${instReq.key}`);
        }
        const childHits = (inst.children || []).filter(c => c.name === prop.targetChildName);
        if (childHits.length !== 1) {
          throw new Error(`Missing or detached bound child ${prop.targetChildName} on instance ${instReq.key}`);
        }
        const child = childHits[0];
        if (child.componentPropertyReferences?.[prop.referenceField] !== actualKey) {
          throw new Error(`Broken instance child componentPropertyReferences.${prop.referenceField} on ${instReq.key}`);
        }

        let liveNormVal;
        let childObservation;
        if (prop.type === 'TEXT') {
          if (child.type !== 'TEXT' || typeof cpEntry.value !== 'string' || child.characters !== cpEntry.value) {
            throw new Error(`TEXT getter mismatch on ${instReq.key}.${prop.id}`);
          }
          liveNormVal = cpEntry.value;
          childObservation = { characters: child.characters };
        } else if (prop.type === 'BOOLEAN') {
          if (typeof cpEntry.value !== 'boolean' || child.visible !== cpEntry.value) {
            throw new Error(`BOOLEAN getter mismatch on ${instReq.key}.${prop.id}`);
          }
          liveNormVal = cpEntry.value;
          childObservation = { visible: child.visible };
        } else {
          if (child.type !== 'INSTANCE' || typeof cpEntry.value !== 'string') {
            throw new Error(`INSTANCE_SWAP child detached or invalid on ${instReq.key}.${prop.id}`);
          }
          const nestedMain = await child.getMainComponentAsync();
          if (!nestedMain || nestedMain.id !== cpEntry.value) {
            throw new Error(`INSTANCE_SWAP getter mismatch on ${instReq.key}.${prop.id}`);
          }
          const swappedMeta = variantMetaByMainId.get(nestedMain.id);
          if (!swappedMeta || !prop.allowedSetIds.includes(swappedMeta.setId)) {
            throw new Error(`Disallowed INSTANCE_SWAP override outside allowedSetIds on ${instReq.key}.${prop.id}`);
          }
          liveNormVal = { setId: swappedMeta.setId, variantKey: swappedMeta.variantKey };
          childObservation = {
            mainComponentId: nestedMain.id,
            targetSetId: swappedMeta.setId,
            targetVariantKey: swappedMeta.variantKey
          };
        }

        const hasExplicitContract = Object.prototype.hasOwnProperty.call(instReq.propertyValues, prop.id);
        const desiredContractNorm = hasExplicitContract ? instReq.propertyValues[prop.id] : prop.defaultValue;
        const desiredMode = hasExplicitContract ? 'explicit' : 'default';
        const isUserOverride = !equal(liveNormVal, propAuthorMeta.authoredValue);

        if (strictContractMatch && pState.defaultChanged && propAuthorMeta.mode === 'explicit' && desiredMode === 'default' && !isUserOverride) {
          throw new Error(`Conflict: ambiguous explicit-to-default transition during main default change on ${instReq.key}.${prop.id}`);
        }

        if (isUserOverride) {
          preservedOverrides.push({
            instanceKey: instReq.key,
            instanceId: inst.id,
            propId: prop.id,
            actualKey,
            type: prop.type,
            authoredValue: copy(propAuthorMeta.authoredValue),
            contractValue: copy(desiredContractNorm),
            liveValue: copy(liveNormVal)
          });
        }

        resolvedProperties[prop.id] = {
          actualKey,
          type: prop.type,
          value: cpEntry.value,
          targetSemanticKey: `${instReq.key}${prop.targetSuffix}`,
          childId: child.id,
          userOverridden: isUserOverride,
          ...childObservation
        };

        livePropObs.set(prop.id, {
          prop,
          actualKey,
          child,
          liveNativeValue: cpEntry.value,
          liveNormVal,
          propAuthorMeta: copy(propAuthorMeta),
          desiredMode,
          desiredContractNorm,
          isUserOverride
        });
      }

      existingInstances.set(instReq.key, {
        instReq,
        inst,
        instMeta: copy(instMeta),
        liveMain,
        liveVariantKey,
        variantUserOverridden,
        livePlacement,
        placementModified,
        livePropObs,
        resolvedProperties
      });
    }

    return {
      status: 'present',
      workbenchFrame,
      libraryFrame,
      instancesFrame,
      marker: copy(marker),
      existingSets,
      mainsByVariantKey,
      variantMetaByMainId,
      existingInstances,
      preservedOverrides,
      preservedPlacements,
      siblingIds
    };
  };

  const formatReadbackPayload = (validated, page, inspection) => {
    if (inspection.status === 'absent') {
      return {
        schema: READBACK_SCHEMA,
        status: 'absent',
        ownerKey: validated.ownerKey,
        pageId: page.id,
        workbenchFrameId: null,
        libraryFrameId: null,
        instancesFrameId: null,
        revision: null,
        componentSets: [],
        instances: [],
        preservedOverrides: [],
        preservedPlacements: [],
        siblingIds: inspection.siblingIds
      };
    }

    const componentSets = validated.setsInContractOrder
      .filter(sp => inspection.existingSets.has(sp.id))
      .map(setPlan => {
        const sInfo = inspection.existingSets.get(setPlan.id);
        const firstVariant = setPlan.variants[0];
        return {
          key: setPlan.id,
          id: sInfo.nativeSet.id,
          family: setPlan.family,
          component: setPlan.component,
          name: setPlan.name,
          layout: setPlan.layout,
          variants: setPlan.variants.map(vp => {
            const main = sInfo.setMains.get(vp.key);
            return {
              key: vp.key,
              componentKey: vp.componentKey,
              id: main.id,
              props: copy(vp.props),
              layoutMode: main.layoutMode
            };
          }),
          propertyMappings: setPlan.properties.map(prop => {
            const pState = sInfo.propStates.get(prop.id);
            const variantTargetSemanticKeys = {};
            for (const vp of setPlan.variants) {
              variantTargetSemanticKeys[vp.key] = `${vp.componentKey}${prop.targetSuffix}`;
            }
            const mapping = {
              id: prop.id,
              name: prop.name,
              type: prop.type,
              actualKey: pState.actualKey,
              referenceField: prop.referenceField,
              targetKey: prop.targetKey,
              targetSemanticKey: `${firstVariant.componentKey}${prop.targetSuffix}`,
              variantTargetSemanticKeys,
              defaultValue: copy(pState.liveDefaultNorm),
              nativeDefaultValue: pState.liveDefinition.defaultValue
            };
            if (prop.type === 'INSTANCE_SWAP') {
              mapping.allowedSetIds = [...prop.allowedSetIds];
              mapping.preferredValues = copy(pState.liveDefinition.preferredValues || []);
            }
            return mapping;
          })
        };
      });

    const instances = validated.instances
      .filter(ir => inspection.existingInstances.has(ir.key))
      .map(instReq => {
        const iInfo = inspection.existingInstances.get(instReq.key);
        const filteredProps = {};
        const sInfo = inspection.existingSets.get(instReq.setId);
        for (const prop of sInfo.setPlan.properties) {
          const actualKey = sInfo.propStates.get(prop.id).actualKey;
          if (iInfo.inst.componentProperties && iInfo.inst.componentProperties[actualKey]) {
            filteredProps[actualKey] = copy(iInfo.inst.componentProperties[actualKey]);
          }
        }
        return {
          key: instReq.key,
          elementId: instReq.elementId,
          id: iInfo.inst.id,
          setId: instReq.setId,
          mainComponentId: iInfo.liveMain.id,
          componentKey: keyOf(iInfo.liveMain),
          variantKey: iInfo.liveVariantKey,
          componentProperties: filteredProps,
          resolvedProperties: copy(iInfo.resolvedProperties),
          placement: copy(iInfo.livePlacement)
        };
      });

    return {
      schema: READBACK_SCHEMA,
      status: 'present',
      ownerKey: validated.ownerKey,
      pageId: page.id,
      workbenchFrameId: inspection.workbenchFrame.id,
      libraryFrameId: inspection.libraryFrame.id,
      instancesFrameId: inspection.instancesFrame.id,
      revision: inspection.marker.revision,
      componentSets,
      instances,
      preservedOverrides: copy(inspection.preservedOverrides),
      preservedPlacements: copy(inspection.preservedPlacements),
      siblingIds: inspection.siblingIds
    };
  };

  const collectContractFonts = validated => {
    const map = new Map();
    const add = font => {
      if (font && font.family && font.style) {
        map.set(`${font.family}\0${font.style}`, { family: font.family, style: font.style });
      }
    };
    add(validated.workbench.font);
    for (const setPlan of validated.orderedSets) {
      for (const vp of setPlan.variants) {
        if (vp.style && vp.style.fontFamily) {
          add({ family: vp.style.fontFamily, style: validated.workbench.font.style || 'Regular' });
        }
      }
    }
    return [...map.values()];
  };

  const createSetOnLibrary = (figma, libraryFrame, setPlan, setIndex, mainsByVariantKey, defaultFont, createdNodes) => {
    if (typeof figma.combineAsVariants !== 'function' ||
        (typeof figma.createComponent !== 'function' && typeof figma.createComponentFromNode !== 'function')) {
      throw new Error('Native component authoring APIs are unavailable');
    }
    if (typeof figma.createText !== 'function' || typeof figma.createFrame !== 'function') {
      throw new Error('Native text/frame authoring APIs are unavailable');
    }

    const components = [];
    const setMains = new Map();
    const variantStylesRecord = {};

    for (const [vIndex, variantPlan] of setPlan.variants.entries()) {
      const main = typeof figma.createComponent === 'function'
        ? figma.createComponent()
        : figma.createComponentFromNode(figma.createFrame());
      createdNodes.push(main);
      libraryFrame.appendChild(main);
      main.name = Object.entries(variantPlan.props).map(([k, v]) => `${k}=${v}`).join(', ');
      main.resize(220, 48);
      setFlowMetadata(main, variantPlan.componentKey, {
        kind: 'family-variant',
        family: setPlan.family,
        set_id: setPlan.id,
        variant_key: variantPlan.key
      });

      const fontName = {
        family: variantPlan.style?.fontFamily || defaultFont.family,
        style: defaultFont.style || 'Regular'
      };

      for (const cSpec of setPlan.childSpecs) {
        const childSemKey = `${variantPlan.componentKey}${cSpec.suffix}`;
        if (cSpec.kind === 'indicator') {
          const ind = figma.createFrame();
          createdNodes.push(ind);
          main.appendChild(ind);
          ind.name = 'indicator';
          ind.resize(16, 16);
          setFlowMetadata(ind, childSemKey, { kind: 'family-indicator', family: setPlan.family });
        } else if (cSpec.kind === 'text') {
          const txt = figma.createText();
          createdNodes.push(txt);
          main.appendChild(txt);
          txt.name = cSpec.name;
          txt.fontName = fontName;
          txt.characters = cSpec.initialText !== null ? cSpec.initialText : variantPlan.defaultLabel;
          setFlowMetadata(txt, childSemKey, { kind: 'family-text', target: cSpec.targetKey });
        } else if (cSpec.kind === 'slot') {
          const defaultTargetMain = mainsByVariantKey.get(cSpec.swapProp.defaultValue.variantKey);
          if (!defaultTargetMain) {
            throw new Error(`Unresolved INSTANCE_SWAP default target ${cSpec.swapProp.defaultValue.variantKey}`);
          }
          const slotInst = defaultTargetMain.createInstance();
          createdNodes.push(slotInst);
          main.appendChild(slotInst);
          slotInst.name = cSpec.name;
          setFlowMetadata(slotInst, childSemKey, { kind: 'component-slot', slot: cSpec.targetKey });
        }
      }

      applyVariantVisualStyle(main, setPlan, variantPlan, defaultFont);
      setCoordinates(main, 24 + vIndex * 280, 48);
      variantStylesRecord[variantPlan.key] = copy(variantPlan.style || {});
      components.push(main);
      setMains.set(variantPlan.key, main);
      mainsByVariantKey.set(variantPlan.key, main);
    }

    const nativeSet = figma.combineAsVariants(components, libraryFrame);
    createdNodes.push(nativeSet);
    nativeSet.name = setPlan.name;
    if ('cornerRadius' in nativeSet) nativeSet.cornerRadius = 0;
    nativeSet.clipsContent = false;
    setCoordinates(nativeSet, 24, 24 + setIndex * 220);
    nativeSet.resize(Math.max(320, components.length * 280 + 24), 180);
    components.forEach((main, idx) => setCoordinates(main, 24 + idx * 280, 48));

    for (const variantPlan of setPlan.variants) {
      const main = setMains.get(variantPlan.key);
      for (const [k, v] of Object.entries(variantPlan.props)) {
        if (!main.variantProperties || main.variantProperties[k] !== v) {
          throw new Error(`Native variant property was not retained on ${variantPlan.key}`);
        }
      }
    }

    const declaredKeys = {};
    const declaredContracts = {};
    const usedActualKeys = new Map();
    const usedNativeNames = new Set();
    const displayCounts = new Map();
    for (const prop of setPlan.properties) {
      displayCounts.set(prop.name, (displayCounts.get(prop.name) || 0) + 1);
    }
    const reservedUniqueNames = new Set(['문구', ...setPlan.axisNameSet]);
    for (const [disp, count] of displayCounts.entries()) {
      if (count === 1) reservedUniqueNames.add(disp);
    }
    let explicitLabelKey = null;

    for (const prop of setPlan.properties) {
      if (typeof nativeSet.addComponentProperty !== 'function') {
        throw new Error(`addComponentProperty API unavailable on ${nativeSet.name}`);
      }
      let nativeDefault;
      let options;
      if (prop.type === 'TEXT' || prop.type === 'BOOLEAN') {
        nativeDefault = prop.defaultValue;
      } else {
        const defaultTargetMain = mainsByVariantKey.get(prop.defaultValue.variantKey);
        nativeDefault = defaultTargetMain.id;
        const preferredValues = prop.preferredValues.map(pref => {
          const pm = mainsByVariantKey.get(pref.variantKey);
          if (!pm || !pm.key) {
            throw new Error(`Native swap target has no component key: ${pref.variantKey}`);
          }
          return { type: 'COMPONENT', key: pm.key };
        });
        options = { preferredValues };
      }

      const { nativeName, actualKey } = addDeclaredPropertySafely(
        nativeSet,
        setPlan,
        prop,
        nativeDefault,
        options,
        { usedActualKeys, usedNativeNames, reservedUniqueNames }
      );
      usedActualKeys.set(actualKey, { propId: prop.id, nativeName });
      usedNativeNames.add(nativeName);
      declaredKeys[prop.id] = actualKey;
      if (prop.type === 'TEXT' && prop.targetKey === 'label') explicitLabelKey = actualKey;
      declaredContracts[prop.id] = {
        id: prop.id,
        name: prop.name,
        ...(nativeName !== prop.name ? { nativeName } : {}),
        actual_key: actualKey,
        type: prop.type,
        target: prop.targetKey,
        targetKey: prop.targetKey,
        target_semantic_suffix: prop.targetSuffix,
        allowedSetIds: prop.type === 'INSTANCE_SWAP' ? [...prop.allowedSetIds] : undefined
      };

      for (const variantPlan of setPlan.variants) {
        const main = setMains.get(variantPlan.key);
        const child = (main.children || []).find(c => c.name === prop.targetChildName);
        if (!child || child.componentPropertyReferences?.[prop.referenceField]) {
          throw new Error(`Owned component property target conflict on ${variantPlan.key}.${prop.id}`);
        }
        if (prop.type === 'TEXT') child.characters = prop.defaultValue;
        else if (prop.type === 'BOOLEAN') child.visible = prop.defaultValue;
        child.componentPropertyReferences = {
          ...(child.componentPropertyReferences || {}),
          [prop.referenceField]: actualKey
        };
        if (child.componentPropertyReferences?.[prop.referenceField] !== actualKey) {
          throw new Error(`Native componentPropertyReferences.${prop.referenceField} not retained on ${variantPlan.key}.${prop.id}`);
        }
      }
    }

    const flowExtra = {
      kind: 'family-set',
      family: setPlan.family,
      ...(explicitLabelKey ? { label_property_key: explicitLabelKey } : {}),
      declared_property_keys: declaredKeys,
      declared_property_contracts: declaredContracts,
      variant_styles: variantStylesRecord
    };
    setFlowMetadata(nativeSet, setPlan.id, flowExtra);
    for (const variantPlan of setPlan.variants) {
      const main = setMains.get(variantPlan.key);
      setFlowMetadata(main, variantPlan.componentKey, {
        kind: 'family-variant',
        family: setPlan.family,
        set_id: setPlan.id,
        variant_key: variantPlan.key,
        ...(explicitLabelKey ? { label_property_key: explicitLabelKey } : {}),
        declared_property_keys: declaredKeys,
        declared_property_contracts: declaredContracts
      });
    }

    return { nativeSet, setMains, declaredKeys, declaredContracts };
  };

  const instantiateDeclaredInstance = (instancesFrame, instReq, index, setPlan, declaredKeys, mainsByVariantKey, createdNodes) => {
    const main = mainsByVariantKey.get(instReq.variantKey);
    if (!main) {
      throw new Error(`Missing main component for instance ${instReq.key}: ${instReq.variantKey}`);
    }
    const inst = main.createInstance();
    createdNodes.push(inst);
    instancesFrame.appendChild(inst);
    inst.name = instReq.name;
    setCoordinates(inst, 24, 24 + index * 104);

    const patch = {};
    const propsMeta = {};

    for (const prop of setPlan.properties) {
      const actualKey = declaredKeys[prop.id];
      const isExplicit = Object.prototype.hasOwnProperty.call(instReq.propertyValues, prop.id);
      const desiredNorm = isExplicit ? instReq.propertyValues[prop.id] : prop.defaultValue;
      const desiredNative = prop.type === 'INSTANCE_SWAP'
        ? mainsByVariantKey.get(desiredNorm.variantKey).id
        : desiredNorm;
      const currentNative = inst.componentProperties?.[actualKey]?.value;
      if (isExplicit && currentNative !== desiredNative) {
        patch[actualKey] = desiredNative;
      }
      propsMeta[prop.id] = {
        mode: isExplicit ? 'explicit' : 'default',
        authoredValue: copy(desiredNorm),
        mainDefault: copy(prop.defaultValue)
      };
    }

    if (Object.keys(patch).length) {
      if (typeof inst.setProperties !== 'function') {
        throw new Error(`InstanceNode.setProperties unavailable for ${instReq.key}`);
      }
      inst.setProperties(patch);
      for (const [aKey, expectedVal] of Object.entries(patch)) {
        if (inst.componentProperties?.[aKey]?.value !== expectedVal) {
          throw new Error(`Instance property override not retained on ${instReq.key}: ${aKey}`);
        }
      }
    }

    const authoredPlacement = readPlacement(inst);
    const mapping = buildInstanceSemanticMapping(inst, instReq.key, `component.${instReq.variantKey}`, setPlan);
    inst.setPluginData('semanticKey', instReq.key);
    inst.setPluginData('semanticComponent', JSON.stringify(mapping));
    inst.setPluginData(INSTANCE_PLUGIN_KEY, JSON.stringify({
      schema: INSTANCE_META_SCHEMA,
      key: instReq.key,
      elementId: instReq.elementId,
      setId: instReq.setId,
      authoredVariantKey: instReq.variantKey,
      authoredMainComponentId: main.id,
      authoredPlacement,
      props: propsMeta,
      domSource: instReq.domSource || null
    }));

    return inst;
  };

  const ensureAdditiveFamilyWorkbench = async (figma, page, contract) => {
    const validated = validateFamilyContract(figma, page, contract);
    const preflight = await inspectWorkbenchState(figma, page, validated, { strictContractMatch: true });

    if (preflight.status === 'absent') {
      const fonts = collectContractFonts(validated);
      for (const font of fonts) await figma.loadFontAsync(font);

      const createdNodes = [];
      let workbenchFrame = null;
      try {
        workbenchFrame = figma.createFrame();
        createdNodes.push(workbenchFrame);
        page.appendChild(workbenchFrame);
        workbenchFrame.name = validated.workbench.name;
        workbenchFrame.layoutMode = 'NONE';
        workbenchFrame.fills = [];
        workbenchFrame.clipsContent = false;
        setCoordinates(workbenchFrame, validated.workbench.position.x, validated.workbench.position.y);
        workbenchFrame.resize(1280, Math.max(720, validated.orderedSets.length * 220 + validated.instances.length * 104 + 96));
        workbenchFrame.setPluginData('semanticKey', validated.workbench.frameKey);

        const libraryFrame = figma.createFrame();
        createdNodes.push(libraryFrame);
        workbenchFrame.appendChild(libraryFrame);
        libraryFrame.name = `${validated.workbench.name} · Library`;
        libraryFrame.layoutMode = 'NONE';
        libraryFrame.fills = [];
        libraryFrame.clipsContent = false;
        setCoordinates(libraryFrame, 24, 24);
        libraryFrame.resize(640, Math.max(320, validated.orderedSets.length * 220 + 24));
        libraryFrame.setPluginData('semanticKey', validated.workbench.libraryKey);

        const instancesFrame = figma.createFrame();
        createdNodes.push(instancesFrame);
        workbenchFrame.appendChild(instancesFrame);
        instancesFrame.name = `${validated.workbench.name} · Instances`;
        instancesFrame.layoutMode = 'NONE';
        instancesFrame.fills = [];
        instancesFrame.clipsContent = false;
        setCoordinates(instancesFrame, 688, 24);
        instancesFrame.resize(568, Math.max(320, validated.instances.length * 104 + 48));
        instancesFrame.setPluginData('semanticKey', validated.workbench.instancesFrameKey);

        const mainsByVariantKey = new Map();
        const createdSets = new Map();

        for (const [idx, setPlan] of validated.orderedSets.entries()) {
          const setCreated = createSetOnLibrary(
            figma, libraryFrame, setPlan, idx, mainsByVariantKey, validated.workbench.font, createdNodes
          );
          createdSets.set(setPlan.id, setCreated);
        }

        for (const [idx, instReq] of validated.instances.entries()) {
          const setPlan = validated.setsById.get(instReq.setId);
          const setCreated = createdSets.get(instReq.setId);
          instantiateDeclaredInstance(
            instancesFrame, instReq, idx, setPlan, setCreated.declaredKeys, mainsByVariantKey, createdNodes
          );
        }

        workbenchFrame.setPluginData(WORKBENCH_PLUGIN_KEY, JSON.stringify({
          schema: WORKBENCH_SCHEMA,
          contractSchema: CONTRACT_SCHEMA,
          version: 1,
          ownerKey: validated.ownerKey,
          pageId: page.id,
          fileKey: (figma && figma.fileKey) || null,
          frameKey: validated.workbench.frameKey,
          libraryKey: validated.workbench.libraryKey,
          instancesFrameKey: validated.workbench.instancesFrameKey,
          setIds: validated.setsInContractOrder.map(s => s.id),
          instanceKeys: validated.instances.map(i => i.key),
          revision: 1
        }));

        const verified = await inspectWorkbenchState(figma, page, validated, { strictContractMatch: true });
        if (verified.status !== 'present') {
          throw new Error('Workbench readback verification failed after creation');
        }
        const payload = formatReadbackPayload(validated, page, verified);
        return {
          ...payload,
          schema: RESULT_SCHEMA,
          status: 'created',
          inheritedDefaults: [],
          idMap: {}
        };
      } catch (error) {
        const rollbackErrors = [];
        rollbackCreatedNodes([...createdNodes].reverse(), rollbackErrors);
        if (rollbackErrors.length) {
          throw new Error(`${error.message}; rollback incomplete: ${rollbackErrors.join('; ')}`);
        }
        throw error;
      }
    }

    // Repeat-apply on existing owned workbench
    const newlyCreatedNodes = [];
    const undoActions = [];
    let mutated = false;
    const inheritedDefaults = [];

    // Determine whether any mutations are needed before loading fonts or touching nodes
    let needsFontLoad = false;
    for (const setPlan of validated.orderedSets) {
      const sInfo = preflight.existingSets.get(setPlan.id);
      if (!sInfo) {
        needsFontLoad = true;
      } else {
        if (sInfo.styleChanged) needsFontLoad = true;
        for (const pState of sInfo.propStates.values()) {
          if (pState.defaultChanged || pState.preferredChanged) needsFontLoad = true;
        }
      }
    }
    for (const instReq of validated.instances) {
      const iInfo = preflight.existingInstances.get(instReq.key);
      if (!iInfo) {
        needsFontLoad = true;
      } else {
        if (!iInfo.variantUserOverridden && iInfo.liveVariantKey !== instReq.variantKey) {
          needsFontLoad = true;
        }
        for (const obs of iInfo.livePropObs.values()) {
          if (!obs.isUserOverride && !equal(obs.liveNormVal, obs.desiredContractNorm)) {
            needsFontLoad = true;
          }
        }
      }
    }

    if (!needsFontLoad) {
      const payload = formatReadbackPayload(validated, page, preflight);
      return {
        ...payload,
        schema: RESULT_SCHEMA,
        status: 'unchanged',
        inheritedDefaults: [],
        idMap: {}
      };
    }

    try {
      const fonts = collectContractFonts(validated);
      for (const font of fonts) await figma.loadFontAsync(font);

      // Re-verify CAS marker revision right before mutating
      const liveMarkerNow = readJsonPluginData(preflight.workbenchFrame, WORKBENCH_PLUGIN_KEY, WORKBENCH_PLUGIN_KEY);
      if (!liveMarkerNow || liveMarkerNow.revision !== preflight.marker.revision) {
        throw new Error('CAS conflict: workbench changed concurrently during font loading');
      }

      const mainsByVariantKey = new Map(preflight.mainsByVariantKey);
      const setDeclarations = new Map();

      for (const [setIdx, setPlan] of validated.orderedSets.entries()) {
        const sInfo = preflight.existingSets.get(setPlan.id);
        if (!sInfo) {
          const created = createSetOnLibrary(
            figma,
            preflight.libraryFrame,
            setPlan,
            preflight.existingSets.size + setIdx,
            mainsByVariantKey,
            validated.workbench.font,
            newlyCreatedNodes
          );
          setDeclarations.set(setPlan.id, created.declaredKeys);
          mutated = true;
          continue;
        }

        const declaredKeys = { ...sInfo.declaredKeys };
        const declaredContracts = { ...sInfo.declaredContracts };

        // Add any newly declared additive properties on existing set
        for (const prop of setPlan.properties) {
          const pState = sInfo.propStates.get(prop.id);
          if (pState && (pState.defaultChanged || pState.preferredChanged)) {
            const prevDef = copy(pState.liveDefinition);
            const editPatch = {};
            if (pState.defaultChanged) editPatch.defaultValue = pState.desiredNativeDefault;
            if (pState.preferredChanged) editPatch.preferredValues = pState.desiredPreferredValues;

            const prevVariantStates = [];
            for (const vp of setPlan.variants) {
              const vChild = pState.variantChildren.get(vp.key);
              if (prop.type === 'TEXT') prevVariantStates.push([vChild, 'characters', vChild.characters]);
              else if (prop.type === 'BOOLEAN') prevVariantStates.push([vChild, 'visible', vChild.visible]);
              else prevVariantStates.push([vChild, 'swap', await vChild.getMainComponentAsync()]);
            }

            const returnedKey = sInfo.nativeSet.editComponentProperty(pState.actualKey, editPatch);
            if (returnedKey !== pState.actualKey) {
              throw new Error(`Unexpected key change from editComponentProperty on ${setPlan.id}.${prop.id}`);
            }
            undoActions.push(() => {
              const revertPatch = { defaultValue: prevDef.defaultValue };
              if (prop.type === 'INSTANCE_SWAP') revertPatch.preferredValues = prevDef.preferredValues || [];
              sInfo.nativeSet.editComponentProperty(pState.actualKey, revertPatch);
              for (const [vChild, kind, prevVal] of prevVariantStates) {
                if (kind === 'characters') vChild.characters = prevVal;
                else if (kind === 'visible') vChild.visible = prevVal;
                else if (kind === 'swap' && prevVal && typeof vChild.swapComponent === 'function') vChild.swapComponent(prevVal);
              }
            });

            // Sync variant children if host runtime did not automatically update them
            for (const vp of setPlan.variants) {
              const vChild = pState.variantChildren.get(vp.key);
              if (prop.type === 'TEXT' && vChild.characters !== prop.defaultValue) {
                vChild.characters = prop.defaultValue;
              } else if (prop.type === 'BOOLEAN' && vChild.visible !== prop.defaultValue) {
                vChild.visible = prop.defaultValue;
              } else if (prop.type === 'INSTANCE_SWAP') {
                const newTargetMain = mainsByVariantKey.get(prop.defaultValue.variantKey);
                const curMain = await vChild.getMainComponentAsync();
                if (curMain?.id !== newTargetMain.id) {
                  if (typeof vChild.swapComponent !== 'function') {
                    throw new Error(`Conflict: swapComponent unavailable to update main slot on ${vp.key}.${prop.id}`);
                  }
                  vChild.swapComponent(newTargetMain);
                }
              }
            }
            mutated = true;
          }
        }

        if (sInfo.styleChanged) {
          const prevSetFlow = sInfo.nativeSet.getPluginData(FIGMA_FLOW_KEY);
          undoActions.push(() => sInfo.nativeSet.setPluginData(FIGMA_FLOW_KEY, prevSetFlow));
          const nextVariantStyles = {};
          for (const vp of setPlan.variants) {
            const main = sInfo.setMains.get(vp.key);
            const prevFills = copy(main.fills);
            const prevStrokes = copy(main.strokes);
            const prevPad = [main.paddingTop, main.paddingRight, main.paddingBottom, main.paddingLeft, main.itemSpacing, main.cornerRadius];
            undoActions.push(() => {
              main.fills = prevFills;
              main.strokes = prevStrokes;
              [main.paddingTop, main.paddingRight, main.paddingBottom, main.paddingLeft, main.itemSpacing] = prevPad;
              if ('cornerRadius' in main) main.cornerRadius = prevPad[5];
            });
            applyVariantVisualStyle(main, setPlan, vp, validated.workbench.font);
            nextVariantStyles[vp.key] = copy(vp.style || {});
          }
          setFlowMetadata(sInfo.nativeSet, setPlan.id, {
            kind: 'family-set',
            family: setPlan.family,
            declared_property_keys: declaredKeys,
            declared_property_contracts: declaredContracts,
            variant_styles: nextVariantStyles
          });
          mutated = true;
        }

        setDeclarations.set(setPlan.id, declaredKeys);
      }

      // Reconcile existing & newly added instances
      for (const [instIdx, instReq] of validated.instances.entries()) {
        const setPlan = validated.setsById.get(instReq.setId);
        const declaredKeys = setDeclarations.get(instReq.setId);
        const iInfo = preflight.existingInstances.get(instReq.key);

        if (!iInfo) {
          instantiateDeclaredInstance(
            preflight.instancesFrame,
            instReq,
            preflight.existingInstances.size + instIdx,
            setPlan,
            declaredKeys,
            mainsByVariantKey,
            newlyCreatedNodes
          );
          mutated = true;
          continue;
        }

        const inst = iInfo.inst;
        const prevInstMetaRaw = inst.getPluginData(INSTANCE_PLUGIN_KEY);
        const prevSemCompRaw = inst.getPluginData('semanticComponent');
        const nextInstMeta = copy(iInfo.instMeta);
        let instMetaChanged = false;

        // Variant update if source changed variantKey and user did NOT override variant
        if (!iInfo.variantUserOverridden && iInfo.liveVariantKey !== instReq.variantKey) {
          const newMain = mainsByVariantKey.get(instReq.variantKey);
          const prevMain = iInfo.liveMain;
          if (typeof inst.swapComponent !== 'function') {
            throw new Error(`Conflict: InstanceNode.swapComponent unavailable to update ${instReq.key}`);
          }
          inst.swapComponent(newMain);
          undoActions.push(() => inst.swapComponent(prevMain));
          nextInstMeta.authoredVariantKey = instReq.variantKey;
          nextInstMeta.authoredMainComponentId = newMain.id;
          instMetaChanged = true;
          mutated = true;
        }

        const sInfo = preflight.existingSets.get(instReq.setId);
        const propPatch = {};
        const revertPropPatch = {};

        for (const prop of setPlan.properties) {
          const obs = iInfo.livePropObs.get(prop.id);
          const pState = sInfo.propStates.get(prop.id);
          const actualKey = declaredKeys[prop.id];
          const desiredNative = prop.type === 'INSTANCE_SWAP'
            ? mainsByVariantKey.get(obs.desiredContractNorm.variantKey).id
            : obs.desiredContractNorm;

          if (obs.isUserOverride) {
            // Preserve user's live override even if main default changed!
            const currentValAfterMainEdit = inst.componentProperties?.[actualKey]?.value;
            if (currentValAfterMainEdit !== obs.liveNativeValue) {
              propPatch[actualKey] = obs.liveNativeValue;
              revertPropPatch[actualKey] = currentValAfterMainEdit;
            }
            nextInstMeta.props[prop.id] = {
              ...obs.propAuthorMeta,
              mainDefault: copy(prop.defaultValue)
            };
            if (!equal(nextInstMeta.props[prop.id], obs.propAuthorMeta)) instMetaChanged = true;
          } else {
            // Not overridden by user: inherit new main default (if mode === 'default') or apply updated explicit contract value!
            const currentValAfterMainEdit = inst.componentProperties?.[actualKey]?.value;
            if (currentValAfterMainEdit !== desiredNative) {
              propPatch[actualKey] = desiredNative;
              revertPropPatch[actualKey] = obs.liveNativeValue;
            }
            if (obs.desiredMode === 'default' && pState && pState.defaultChanged && !equal(obs.liveNormVal, prop.defaultValue)) {
              inheritedDefaults.push({
                instanceKey: instReq.key,
                instanceId: inst.id,
                propId: prop.id,
                actualKey,
                type: prop.type,
                previousValue: copy(obs.liveNormVal),
                inheritedValue: copy(prop.defaultValue)
              });
              mutated = true;
            } else if (!equal(obs.liveNormVal, obs.desiredContractNorm)) {
              mutated = true;
            }
            const updatedPropMeta = {
              mode: obs.desiredMode,
              authoredValue: copy(obs.desiredContractNorm),
              mainDefault: copy(prop.defaultValue)
            };
            if (!equal(updatedPropMeta, obs.propAuthorMeta)) {
              nextInstMeta.props[prop.id] = updatedPropMeta;
              instMetaChanged = true;
            }
          }
        }

        if (Object.keys(propPatch).length) {
          inst.setProperties(propPatch);
          undoActions.push(() => inst.setProperties(revertPropPatch));
          mutated = true;
        }

        if (instMetaChanged || Object.keys(propPatch).length) {
          const liveMainAfter = await inst.getMainComponentAsync();
          const refreshedMapping = buildInstanceSemanticMapping(inst, instReq.key, keyOf(liveMainAfter), setPlan);
          undoActions.push(() => {
            inst.setPluginData(INSTANCE_PLUGIN_KEY, prevInstMetaRaw);
            inst.setPluginData('semanticComponent', prevSemCompRaw);
          });
          inst.setPluginData('semanticComponent', JSON.stringify(refreshedMapping));
          inst.setPluginData(INSTANCE_PLUGIN_KEY, JSON.stringify(nextInstMeta));
        }
      }

      if (mutated) {
        const prevWbRaw = preflight.workbenchFrame.getPluginData(WORKBENCH_PLUGIN_KEY);
        undoActions.push(() => preflight.workbenchFrame.setPluginData(WORKBENCH_PLUGIN_KEY, prevWbRaw));
        preflight.workbenchFrame.setPluginData(WORKBENCH_PLUGIN_KEY, JSON.stringify({
          ...preflight.marker,
          setIds: validated.setsInContractOrder.map(s => s.id),
          instanceKeys: validated.instances.map(i => i.key),
          revision: (preflight.marker.revision || 1) + 1
        }));
      }

      const postVerify = await inspectWorkbenchState(figma, page, validated, { strictContractMatch: true });
      const payload = formatReadbackPayload(validated, page, postVerify);
      return {
        ...payload,
        schema: RESULT_SCHEMA,
        status: mutated ? 'updated' : 'unchanged',
        inheritedDefaults,
        idMap: {}
      };
    } catch (error) {
      const rollbackErrors = [];
      rollbackCreatedNodes([...newlyCreatedNodes].reverse(), rollbackErrors);
      for (const undo of [...undoActions].reverse()) {
        try { undo(); } catch (failure) { rollbackErrors.push(String(failure)); }
      }
      if (rollbackErrors.length) {
        throw new Error(`${error.message}; rollback incomplete: ${rollbackErrors.join('; ')}`);
      }
      throw error;
    }
  };

  const readFamilyWorkbench = async (figma, page, contract) => {
    const validated = validateFamilyContract(figma, page, contract, { readOnly: true });
    const inspection = await inspectWorkbenchState(figma, page, validated, { strictContractMatch: false });
    return formatReadbackPayload(validated, page, inspection);
  };

  // Existing pre-existing frame conversion branch (preserved unchanged when no family declarations are present)
  const ensureLegacyPreExistingFrames = async (figma, page, contract) => {
    const visible = node => visibleOnPage(node, page);
    const registry = new Map();
    walk(page, node => {
      const key = keyOf(node);
      if (!key || !visible(node)) return;
      if (registry.has(key)) throw new Error(`Duplicate visible semanticKey: ${key}`);
      registry.set(key, node);
    });
    const requireNode = key => {
      const node = registry.get(key);
      if (!node) throw new Error(`Missing visible semanticKey: ${key}`);
      return node;
    };
    const sets = (contract && contract.componentSets) || [];
    const requests = (contract && contract.instances) || [];
    if (!sets.length || !requests.length) throw new Error('Component sets and instance mappings are required');
    const variants = new Map();
    const setIds = new Set();
    const seenVariantKeys = new Set();
    for (const set of sets) {
      if (!set.id || setIds.has(set.id) || !set.name || !Array.isArray(set.variants) || set.variants.length < 2) {
        throw new Error('Invalid component set');
      }
      setIds.add(set.id);
      validateVariantPropsList(set.variants, set.id, seenVariantKeys, 2);
      for (const variant of set.variants) {
        variants.set(variant.key, { ...variant, source: requireNode(variant.key), set });
      }
    }
    const targets = new Set();
    const plans = requests.map(request => {
      const original = requireNode(request.key);
      const variant = variants.get(request.variantKey);
      if (!variant || targets.has(request.key)) throw new Error(`Invalid instance mapping: ${request.key}`);
      targets.add(request.key);
      const compatible = (a, b, root = true) => {
        if ((!root && a.type !== b.type) || (a.children || []).length !== (b.children || []).length) return false;
        return (a.children || []).every((child, i) => compatible(child, b.children[i], false));
      };
      if (!compatible(original, variant.source)) throw new Error(`Incompatible child tree: ${request.key}`);
      return { request, original, variant, parent: original.parent, index: original.parent.children.indexOf(original) };
    });
    for (const plan of plans) {
      for (let p = plan.original.parent; p && p !== page; p = p.parent) {
        if (targets.has(keyOf(p))) throw new Error('Nested replacement targets are unsupported');
      }
      if (plan.original.type !== 'FRAME' && plan.original.type !== 'INSTANCE') throw new Error(`Unsupported target: ${plan.request.key}`);
    }
    if (plans.every(plan => plan.original.type === 'INSTANCE')) {
      const result = [];
      for (const plan of plans) {
        const main = await plan.original.getMainComponentAsync();
        const prior = JSON.parse(plan.original.getPluginData('semanticComponent') || '{}');
        if (!main || keyOf(main) !== prior.sourceKey ||
            main.parent.type !== 'COMPONENT_SET' || keyOf(main.parent) !== plan.variant.set.id || !visible(main)) {
          throw new Error(`Disconnected or incompatible instance: ${plan.request.key}`);
        }
        for (const [name, value] of Object.entries(plan.variant.props)) {
          if (main.variantProperties[name] !== value) throw new Error(`Variant property drift: ${plan.request.key}`);
        }
        result.push({ key: plan.request.key, id: plan.original.id, mainComponentId: main.id, componentKey: keyOf(main) });
      }
      return { status: 'unchanged', instances: result, componentSets: [...setIds], idMap: {} };
    }
    if (plans.some(plan => plan.original.type === 'INSTANCE') || [...setIds].some(id => registry.has(id))) {
      throw new Error('Partial component conversion requires explicit recovery');
    }
    if (typeof figma.createComponentFromNode !== 'function' || typeof figma.combineAsVariants !== 'function') {
      throw new Error('Native component conversion APIs are unavailable');
    }
    const fonts = new Map();
    for (const node of new Set([...plans.map(p => p.original), ...[...variants.values()].map(v => v.source)])) {
      walk(node, child => {
        if (child.type !== 'TEXT') return;
        const names = child.getRangeAllFontNames(0, child.characters.length);
        for (const font of names) fonts.set(JSON.stringify(font), font);
      });
    }
    for (const font of fonts.values()) await figma.loadFontAsync(font);
    const visualFields = ['fills', 'strokes', 'strokeWeight', 'strokeAlign', 'dashPattern', 'effects',
      'opacity', 'blendMode', 'visible', 'rotation', 'cornerRadius', 'topLeftRadius', 'topRightRadius',
      'bottomLeftRadius', 'bottomRightRadius', 'clipsContent', 'layoutMode', 'primaryAxisSizingMode',
      'counterAxisSizingMode', 'primaryAxisAlignItems', 'counterAxisAlignItems', 'paddingLeft',
      'paddingRight', 'paddingTop', 'paddingBottom', 'itemSpacing', 'constraints', 'layoutAlign',
      'layoutGrow', 'layoutPositioning', 'vectorPaths'];
    const textFields = ['fontName', 'fontSize', 'textCase', 'textDecoration', 'letterSpacing',
      'lineHeight', 'fills', 'textStyleId', 'fillStyleId'];
    const visualProfile = node => JSON.stringify([
      node.type, node.width, node.height,
      (node.children || []).map(child => [child.relativeTransform, visualProfile(child)])
    ]);
    const supportedRootWidth = (original, source) => original.type === source.type && original.height === source.height &&
      JSON.stringify((original.children || []).map(child => [child.relativeTransform, visualProfile(child)])) ===
      JSON.stringify((source.children || []).map(child => [child.relativeTransform, visualProfile(child)]));
    const childKeys = [];
    const transfer = async (source, target, path = []) => {
      target.name = source.name;
      for (const field of visualFields) {
        if (field in source && field in target && source[field] !== undefined && typeof source[field] !== 'symbol' && !equal(source[field], target[field])) target[field] = copy(source[field]);
      }
      if (source.type === 'TEXT') {
        const segments = source.getStyledTextSegments([...textFields, 'boundVariables']);
        const textChanged = source.characters !== target.characters || !equal(segments, target.getStyledTextSegments([...textFields, 'boundVariables']));
        if (source.characters !== target.characters) target.characters = source.characters;
        for (const segment of textChanged ? segments : []) {
          for (const field of textFields) {
            const setter = `setRange${field[0].toUpperCase()}${field.slice(1)}`;
            if (!(field in segment) || segment.start === segment.end) continue;
            if (field.endsWith('StyleId')) {
              if (segment[field] && typeof target[`${setter}Async`] === 'function') await target[`${setter}Async`](segment.start, segment.end, segment[field]);
            } else if (typeof target[setter] === 'function') target[setter](segment.start, segment.end, copy(segment[field]));
          }
          const fontSizeAlias = segment.boundVariables && segment.boundVariables.fontSize;
          if (fontSizeAlias && segment.start !== segment.end) {
            if (typeof target.setRangeBoundVariable !== 'function' || !figma.variables ||
                typeof figma.variables.getVariableByIdAsync !== 'function') throw new Error('Font size binding API unavailable');
            const variable = await figma.variables.getVariableByIdAsync(fontSizeAlias.id);
            if (!variable) throw new Error(`Missing font size variable: ${fontSizeAlias.id}`);
            target.setRangeBoundVariable(segment.start, segment.end, 'fontSize', variable);
          }
        }
        for (const field of ['textAutoResize', 'textAlignHorizontal', 'textAlignVertical', 'paragraphSpacing', 'paragraphIndent']) {
          if (field in source && !equal(source[field], target[field])) target[field] = source[field];
        }
      }
      if (source.width !== target.width || source.height !== target.height) target.resize(source.width, source.height);
      if (!equal(source.relativeTransform, target.relativeTransform)) {
        if (path.length) throw new Error(`Instance child geometry mismatch: ${keyOf(source)}`);
        target.relativeTransform = copy(source.relativeTransform);
      }
      for (const key of source.getPluginDataKeys()) target.setPluginData(key, source.getPluginData(key));
      childKeys.push({ path, key: keyOf(source), id: target.id });
      if (source.reactions) await target.setReactionsAsync(copy(source.reactions));
      for (const [i, child] of (source.children || []).entries()) await transfer(child, target.children[i], [...path, i]);
    };
    let library;
    let archive;
    const created = [];
    const reactionEdits = [];
    const archived = [];
    try {
      library = figma.createFrame();
      page.appendChild(library);
      library.name = 'BLOOM · Native component library';
      library.setPluginData('semanticKey', 'component.library');
      library.x = Math.max(0, ...page.children.filter(n => n !== library).map(n => n.x + n.width)) + 400;
      library.y = 0;
      library.resize(1600, Math.max(800, sets.length * 240));
      library.fills = [];
      library.clipsContent = false;
      library.visible = false;
      const mains = new Map();
      const nativeSets = new Map();
      const layoutMains = new Map();
      const setSummary = [];
      for (const [index, set] of sets.entries()) {
        const components = [];
        for (const variant of set.variants) {
          const clone = variants.get(variant.key).source.clone();
          created.push(clone);
          library.appendChild(clone);
          const main = figma.createComponentFromNode(clone);
          created.push(main);
          main.name = Object.entries({ ...variant.props, Layout: 'Sample' }).map(([name, value]) => `${name}=${value}`).join(', ');
          walk(main, node => {
            const key = keyOf(node);
            if (key) node.setPluginData('semanticKey', `component.${key}`);
          });
          main.setPluginData('semanticKey', `component.${variant.key}`);
          mains.set(variant.key, main);
          components.push(main);
        }
        const nativeSet = figma.combineAsVariants(components, library);
        nativeSets.set(set.id, nativeSet);
        nativeSet.name = set.name;
        if ('cornerRadius' in nativeSet) nativeSet.cornerRadius = 0;
        nativeSet.setPluginData('semanticKey', set.id);
        nativeSet.x = 0;
        nativeSet.y = index * 240;
        components.forEach((main, i) => { main.x = 24 + i * 320; main.y = 48; });
        nativeSet.resize(Math.max(360, components.length * 320), 200);
        nativeSet.clipsContent = false;
        for (const variant of set.variants) {
          const main = mains.get(variant.key);
          for (const [name, value] of Object.entries(variant.props)) {
            if (!main.variantProperties || main.variantProperties[name] !== value) throw new Error(`Native variant property was not retained: ${variant.key}`);
          }
        }
        setSummary.push({ key: set.id, id: nativeSet.id, variants: set.variants.map(v => ({ key: v.key, id: mains.get(v.key).id, props: v.props })) });
      }
      const idMap = {};
      for (const plan of plans) {
        let main = mains.get(plan.request.variantKey);
        const profile = visualProfile(plan.original);
        if (profile !== visualProfile(plan.variant.source) && !supportedRootWidth(plan.original, plan.variant.source)) {
          const signature = `${plan.request.variantKey}:${profile}`;
          main = layoutMains.get(signature);
          if (!main) {
            const clone = plan.original.clone();
            created.push(clone);
            library.appendChild(clone);
            main = figma.createComponentFromNode(clone);
            created.push(main);
            main.name = Object.entries({ ...plan.variant.props, Layout: plan.request.key }).map(([name, value]) => `${name}=${value}`).join(', ');
            walk(main, node => { const key = keyOf(node); if (key) node.setPluginData('semanticKey', `component.${key}`); });
            main.setPluginData('semanticKey', `component.${plan.request.variantKey}.layout.${plan.request.key}`);
            const nativeSet = nativeSets.get(plan.variant.set.id);
            nativeSet.appendChild(main);
            main.x = 24 + (nativeSet.children.length - 1) * 320;
            main.y = 48;
            nativeSet.resize(nativeSet.children.length * 320, 200);
            layoutMains.set(signature, main);
            setSummary.find(set => set.key === plan.variant.set.id).variants.push({ key: keyOf(main), id: main.id, props: { ...plan.variant.props, Layout: plan.request.key } });
          }
        }
        if (plan.request.componentKey && keyOf(main) !== plan.request.componentKey) throw new Error(`Resolved component key mismatch: ${plan.request.key}`);
        const instance = main.createInstance();
        created.push(instance);
        library.appendChild(instance);
        childKeys.length = 0;
        await transfer(plan.original, instance);
        const mapping = childKeys.map(item => ({ ...item }));
        instance.setPluginData('semanticComponent', JSON.stringify({ key: plan.request.key, sourceKey: keyOf(main), childKeys: mapping }));
        for (const [key, value] of Object.entries(plan.request.overrides || {})) {
          const entry = mapping.find(item => item.key === key);
          if (!entry || typeof value !== 'string') throw new Error(`Invalid text override: ${key}`);
          let text = instance;
          for (const i of entry.path) text = text.children[i];
          if (text.type !== 'TEXT') throw new Error(`Override is not text: ${key}`);
          text.characters = value;
        }
        for (const item of mapping) {
          let source = plan.original;
          for (const i of item.path) source = source.children[i];
          idMap[source.id] = item.id;
        }
        plan.instance = instance;
        plan.main = main;
      }
      archive = figma.createFrame();
      page.appendChild(archive);
      archive.name = 'BLOOM · Preserved pre-component controls';
      archive.setPluginData('semanticKey', `archive.${archive.id}`);
      archive.visible = false;
      for (const plan of plans) {
        const keys = [];
        walk(plan.original, node => keys.push([node, keyOf(node)]));
        archived.push({ ...plan, keys, transform: copy(plan.original.relativeTransform) });
        plan.parent.insertChild(plan.parent.children.indexOf(plan.original), plan.instance);
        plan.instance.relativeTransform = copy(plan.original.relativeTransform);
        archive.appendChild(plan.original);
        for (const [node, key] of keys) if (key) node.setPluginData('semanticKey', `archive.${node.id}.${key}`);
      }
      const reactionNodes = [];
      walk(page, node => {
        let inLibrary = false;
        for (let p = node; p && p !== page; p = p.parent) if (p === library) inLibrary = true;
        if ((visible(node) || inLibrary) && node.reactions && node.reactions.length) reactionNodes.push(node);
      });
      for (const node of reactionNodes) {
        const before = copy(node.reactions);
        let changed = false;
        const remap = value => {
          if (!value || typeof value !== 'object') return;
          if (value.destinationId && idMap[value.destinationId]) { value.destinationId = idMap[value.destinationId]; changed = true; }
          for (const child of Object.values(value)) remap(child);
        };
        const after = copy(before);
        remap(after);
        if (changed) { reactionEdits.push([node, before]); await node.setReactionsAsync(after); }
      }
      library.visible = true;
      return {
        status: 'created',
        componentSets: setSummary,
        instances: plans.map(p => ({ key: p.request.key, id: p.instance.id, mainComponentId: p.main.id, componentKey: keyOf(p.main) })),
        idMap,
        archiveId: archive.id
      };
    } catch (error) {
      const rollbackErrors = [];
      for (const [node, reactions] of reactionEdits.reverse()) {
        try { await node.setReactionsAsync(reactions); } catch (failure) { rollbackErrors.push(String(failure)); }
      }
      for (const item of archived.reverse()) {
        try {
          item.parent.insertChild(Math.min(item.index, item.parent.children.length), item.original);
          item.original.relativeTransform = item.transform;
          for (const [node, key] of item.keys) node.setPluginData('semanticKey', key);
        } catch (failure) { rollbackErrors.push(String(failure)); }
      }
      rollbackCreatedNodes(
        [...created.reverse(), library, ...(archive && !archive.children.length ? [archive] : [])],
        rollbackErrors
      );
      if (rollbackErrors.length) throw new Error(`${error.message}; rollback incomplete: ${rollbackErrors.join('; ')}`);
      throw error;
    }
  };

  return {
    isFamilyContract,
    ensureAdditiveFamilyWorkbench,
    ensureLegacyPreExistingFrames,
    readFamilyWorkbench
  };
})();

async function ensureSemanticComponents(figma, page, contract) {
  if (SEMANTIC_COMPONENTS_RUNTIME.isFamilyContract(contract)) {
    return SEMANTIC_COMPONENTS_RUNTIME.ensureAdditiveFamilyWorkbench(figma, page, contract);
  }
  return SEMANTIC_COMPONENTS_RUNTIME.ensureLegacyPreExistingFrames(figma, page, contract);
}

async function readSemanticComponentFamilies(figma, page, contract) {
  return SEMANTIC_COMPONENTS_RUNTIME.readFamilyWorkbench(figma, page, contract);
}

if (typeof module !== 'undefined') {
  module.exports = { ensureSemanticComponents, readSemanticComponentFamilies };
}
