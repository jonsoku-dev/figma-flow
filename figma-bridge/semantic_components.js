/* Native Plugin API helper; usable directly in a Figma execution context. */
async function ensureSemanticComponents(figma, page, contract) {
  const keyOf = node => {
    const path = [];
    for (let parent = node; parent; parent = parent.parent) {
      if (parent.type === 'INSTANCE') {
        let mapping;
        try { mapping = JSON.parse(parent.getPluginData('semanticComponent') || '{}'); }
        catch (_) { throw new Error(`Invalid instance semantic mapping: ${parent.id}`); }
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
  const visible = node => {
    for (let p = node; p && p !== page; p = p.parent) if (p.visible === false) return false;
    return true;
  };
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
  const sets = contract.componentSets || [];
  const requests = contract.instances || [];
  if (!sets.length || !requests.length) throw new Error('Component sets and instance mappings are required');
  const variants = new Map();
  const setIds = new Set();
  for (const set of sets) {
    if (!set.id || setIds.has(set.id) || !set.name || set.variants.length < 2) throw new Error('Invalid component set');
    setIds.add(set.id);
    const signatures = new Set();
    let propertyNames;
    for (const variant of set.variants) {
      const names = Object.keys(variant.props || {}).sort();
      const signature = JSON.stringify(names.map(name => [name, variant.props[name]]));
      if (!names.length || signatures.has(signature) || variants.has(variant.key) ||
          names.some(name => /[,=]/.test(name) || typeof variant.props[name] !== 'string' || /[,=]/.test(variant.props[name]))) {
        throw new Error(`Invalid variant: ${variant.key}`);
      }
      if (propertyNames && JSON.stringify(names) !== propertyNames) throw new Error(`Variant property mismatch: ${set.id}`);
      propertyNames = JSON.stringify(names);
      signatures.add(signature);
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
  // Idempotence requires live instances connected to the exact declared native variants.
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
  const copy = value => JSON.parse(JSON.stringify(value));
  const visualFields = ['fills', 'strokes', 'strokeWeight', 'strokeAlign', 'dashPattern', 'effects',
    'opacity', 'blendMode', 'visible', 'rotation', 'cornerRadius', 'topLeftRadius', 'topRightRadius',
    'bottomLeftRadius', 'bottomRightRadius', 'clipsContent', 'layoutMode', 'primaryAxisSizingMode',
    'counterAxisSizingMode', 'primaryAxisAlignItems', 'counterAxisAlignItems', 'paddingLeft',
    'paddingRight', 'paddingTop', 'paddingBottom', 'itemSpacing', 'constraints', 'layoutAlign',
    'layoutGrow', 'layoutPositioning', 'vectorPaths'];
  const textFields = ['fontName', 'fontSize', 'textCase', 'textDecoration', 'letterSpacing',
    'lineHeight', 'fills', 'textStyleId', 'fillStyleId'];
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const visualProfile = node => JSON.stringify([
    node.type, node.width, node.height,
    (node.children || []).map(child => [child.relativeTransform, visualProfile(child)])
  ]);
  // Instance resize already reproduces a different root width. Child size, child
  // transform, and height stay in the fingerprint so unsupported geometry still splits.
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
          // Numeric font overrides clear inherited bindings; restore the original range alias last.
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
  let library, archive;
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
      // Overrides are keyed by the original screen-local child semantic key.
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
    return { status: 'created', componentSets: setSummary, instances: plans.map(p => ({ key: p.request.key, id: p.instance.id, mainComponentId: p.main.id, componentKey: keyOf(p.main) })), idMap, archiveId: archive.id };
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
    // A failed restoration must leave preserved originals available for recovery.
    for (const node of [...created.reverse(), library, ...(archive && !archive.children.length ? [archive] : [])]) {
      try { if (node && !node.removed) node.remove(); } catch (failure) { rollbackErrors.push(String(failure)); }
    }
    if (rollbackErrors.length) throw new Error(`${error.message}; rollback incomplete: ${rollbackErrors.join('; ')}`);
    throw error;
  }
}
if (typeof module !== 'undefined') module.exports = { ensureSemanticComponents };
