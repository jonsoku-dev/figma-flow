/* Idempotently provisions one graph-keyed booking CTA under an existing page. */
const NATIVE_PROVISION_SCHEMA = 'figma-flow-starter-cta-provision-v1';
const NATIVE_PROVISION_OWNER = 'figmaFlowStarterCtaProvision';
const NATIVE_PROVISION_FRAME = {width: 420, height: 280};
const nativeProvisionClone = value => JSON.parse(JSON.stringify(value));

function nativeProvisionValidate(plan) {
  const p = plan.provision;
  if (!p || p.schema !== NATIVE_PROVISION_SCHEMA || !/^[a-f0-9]{64}$/.test(p.graph_sha256) ||
      p.frame_key !== 'little-hands/booking-cta/starter-frame' || p.main_key !== 'bookingCTA' ||
      JSON.stringify(p.instance_keys) !== JSON.stringify(['reserve-preview', 'reserve-login']) ||
      p.seed_collection_name !== 'Little Hands · CTA SSOT seed' || p.seed_variable_name !== 'starter/little-hands/booking-cta-seed' ||
      p.canonical_variable_name !== 'ssot/little-hands/color/action/primary' ||
      !Array.isArray(p.page_roots) || !p.position || !Number.isFinite(p.position.x) || !Number.isFinite(p.position.y))
    throw Error('Invalid or stale Starter CTA provision plan');
}

function nativeProvisionSemantic(node) {
  return node.getPluginData('semanticKey') || null;
}

function nativeProvisionRows(page) {
  return page.children.map(node => {
    const box = node.absoluteBoundingBox;
    if (!box || !['x', 'y', 'width', 'height'].every(key => Number.isFinite(box[key])))
      throw Error('Existing page sibling bounds unavailable');
    return {id: node.id, type: node.type, name: node.name, semanticKey: nativeProvisionSemantic(node),
      x: node.x, y: node.y, width: node.width, height: node.height,
      absoluteBoundingBox: {x: box.x, y: box.y, width: box.width, height: box.height}};
  }).sort((a, b) => a.id.localeCompare(b.id));
}

function nativeProvisionOverlap(a, b) {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

function nativeProvisionPagePreflight(page, plan, existingFrame) {
  const provision = plan.provision;
  const current = nativeProvisionRows(page);
  const currentById = new Map(current.map(row => [row.id, row]));
  for (const expected of provision.page_roots) {
    const actual = currentById.get(expected.id);
    if (!actual || !nativeEditEqual(actual, expected)) throw Error('An admitted page sibling changed after preparation');
  }
  const admitted = new Set(provision.page_roots.map(row => row.id));
  const additions = current.filter(row => row.id !== existingFrame?.id && !admitted.has(row.id));
  const workbench = {...provision.position, ...NATIVE_PROVISION_FRAME};
  if (additions.some(row => nativeProvisionOverlap(row.absoluteBoundingBox, workbench)))
    throw Error('A new page sibling overlaps the admitted CTA workbench location');
  return current;
}

async function nativeProvisionMatches(figma, page, plan, frame, labelUpdates) {
  const p = plan.provision;
  const rows = [page, ...page.findAll(() => true)];
  const keyed = key => rows.filter(node => nativeProvisionSemantic(node) === key);
  const exact = (key, type, parent) => {
    const matches = keyed(key);
    if (matches.length !== 1 || matches[0].type !== type || matches[0].parent !== parent)
      throw Error('Missing, ambiguous, or misplaced native semantic target: ' + key);
    return matches[0];
  };
  if (frame.type !== 'FRAME' || frame.parent !== page || nativeProvisionSemantic(frame) !== p.frame_key)
    throw Error('Owned CTA workbench frame is not on the pinned existing page');
  const marker = JSON.parse(frame.getPluginData(NATIVE_PROVISION_OWNER) || 'null');
  if (!marker || marker.schema !== NATIVE_PROVISION_SCHEMA || marker.page_id !== plan.page_id ||
      marker.frame_key !== p.frame_key || marker.main_key !== p.main_key ||
      JSON.stringify(marker.instance_keys) !== JSON.stringify(p.instance_keys))
    throw Error('CTA workbench ownership marker is missing or belongs to another task');
  if (frame.layoutMode !== 'VERTICAL' || frame.clipsContent !== false || frame.visible === false ||
      frame.width !== NATIVE_PROVISION_FRAME.width || frame.height !== NATIVE_PROVISION_FRAME.height ||
      frame.x !== p.position.x || frame.y !== p.position.y)
    throw Error('Owned CTA workbench frame geometry changed');
  const main = exact(p.main_key, 'COMPONENT', frame);
  if (main.remote === true || main.layoutMode !== 'HORIZONTAL' || main.height !== 48 || main.cornerRadius !== 0 ||
      !Array.isArray(main.fills) || main.fills.length !== 1 || main.fills[0].type !== 'SOLID' ||
      main.fills[0].opacity !== 1 || !nativeEditEqual(main.fills[0].color, p.background_color))
    throw Error('CTA main does not match its declared native component contract');
  const binding = main.fills[0].boundVariables?.color;
  if (!binding || binding.type !== 'VARIABLE_ALIAS' || !binding.id) throw Error('CTA main fill must be bound to an actual local seed or graph color variable');
  const variable = await figma.variables.getVariableByIdAsync(binding.id);
  const collection = variable && await figma.variables.getVariableCollectionByIdAsync(variable.variableCollectionId);
  const owner = collection && JSON.parse(collection.getPluginData('bloomSemanticTokens') || 'null');
  if (!variable || variable.remote || variable.resolvedType !== 'COLOR' ||
      ![p.seed_variable_name, p.canonical_variable_name].includes(variable.name) || collection?.name !== p.seed_collection_name ||
      owner?.pageId !== page.id || owner?.collectionId !== collection.id)
    throw Error('CTA fill variable must belong to the owned page-scoped seed collection');
  const labels = main.findAll(node => node.type === 'TEXT');
  if (labels.length !== 1) throw Error('CTA main requires one actual text child');
  const label = labels[0];
  if (label.characters !== p.labels.main || label.fontName?.family !== 'Hahmlet' || label.fontName?.style !== 'Bold' ||
      label.fontSize !== 14 || !Array.isArray(label.fills) || label.fills.length !== 1 ||
      !nativeEditEqual(label.fills[0].color, p.text_color))
    throw Error('CTA main label differs from the pinned copy or text style');
  const instances = [];
  for (const key of p.instance_keys) {
    const instance = exact(key, 'INSTANCE', frame);
    if ((await instance.getMainComponentAsync())?.id !== main.id)
      throw Error('CTA instance points to a different local main: ' + key);
    const instanceLabel = instance.findOne(node => node.type === 'TEXT');
    if (!instanceLabel) throw Error('CTA instance label missing: ' + key);
    if (instanceLabel.characters !== p.labels[key]) {
      // The first workbench wrote the main's placeholder to both instance labels.
      // Only migrate that exact authored value. Other overrides require review.
      if (!labelUpdates || !p.label_source_sha256 || instanceLabel.characters !== '예약하기')
        throw Error('CTA instance override changed: ' + key);
      labelUpdates.push({key, node: instanceLabel, before: instanceLabel.characters, after: p.labels[key]});
    }
    instances.push({key, id: instance.id, main_component_id: main.id, label: instanceLabel.characters});
  }
  return {frame_id: frame.id, main_id: main.id, instances};
}

async function nativeProvisionRun(figma, plan, operation = 'apply') {
  nativeEditValidatePlan(plan);
  nativeProvisionValidate(plan);
  nativeEditScope(figma, plan);
  const page = await figma.getNodeByIdAsync(plan.page_id);
  if (!page || page.type !== 'PAGE') throw Error('Pinned existing Figma page is unavailable');
  await page.loadAsync();
  nativeEditScope(figma, plan);
  const foundFrame = page.findAll(node => nativeProvisionSemantic(node) === plan.provision.frame_key);
  if (foundFrame.length > 1) throw Error('Duplicate CTA workbench ownership key');
  const existingFrame = foundFrame[0] || null;
  nativeProvisionPagePreflight(page, plan, existingFrame);
  const keyed = [page, ...page.findAll(() => true)];
  for (const key of [plan.provision.main_key, ...plan.provision.instance_keys]) {
    const matches = keyed.filter(node => nativeProvisionSemantic(node) === key);
    const expectedParent = existingFrame;
    if (matches.length && (!existingFrame || matches.length !== 1 || matches[0].parent !== expectedParent))
      throw Error('CTA key collision outside the owned workbench: ' + key);
  }
  if (operation === 'read') {
    const readback = await nativeEditDiscovery(figma, plan);
    return {...readback, native_edit: {plan_sha256: NATIVE_EDIT_SHA256, applied: false, operation: 'read',
      provision: existingFrame ? await nativeProvisionMatches(figma, page, plan, existingFrame) : null}};
  }
  if (operation !== 'apply') throw Error('Unsupported native provision operation');
  if (existingFrame) {
    const updates = [], written = [];
    let provision = await nativeProvisionMatches(figma, page, plan, existingFrame, updates);
    try {
      if (updates.length) {
        await figma.loadFontAsync({family:'Hahmlet', style:'Bold'});
        nativeEditScope(figma, plan);
        for (const edit of updates) {
          if (edit.node.characters !== edit.before || edit.node.parent?.parent !== existingFrame)
            throw Error('CTA instance changed before label migration: ' + edit.key);
          edit.node.characters = edit.after;
          written.push(edit);
        }
        provision = await nativeProvisionMatches(figma, page, plan, existingFrame);
      }
      const readback = await nativeEditDiscovery(figma, plan);
      return {...readback, native_edit: {plan_sha256: NATIVE_EDIT_SHA256, applied: true, operation: 'apply',
        changed: written.length, provision, idempotent: written.length === 0}};
    } catch (error) {
      for (const edit of written.reverse()) {
        if (!edit.node.removed && edit.node.parent?.parent === existingFrame && edit.node.characters === edit.after)
          edit.node.characters = edit.before;
      }
      throw error;
    }
  }
  nativeProvisionPagePreflight(page, plan, null);
  const font = {family: 'Hahmlet', style: 'Bold'};
  await figma.loadFontAsync(font);
  nativeEditScope(figma, plan);
  nativeProvisionPagePreflight(page, plan, null);
  const cleanup = [];
  let createdCollection, createdSeed, createdFrame, createdMain, createdLabel;
  const createdInstances = [];
  try {
    createdCollection = figma.variables.createVariableCollection(plan.provision.seed_collection_name);
    cleanup.push(() => createdCollection.remove());
    createdSeed = figma.variables.createVariable(plan.provision.seed_variable_name, createdCollection, 'COLOR');
    cleanup.push(() => createdSeed.remove());
    createdSeed.setValueForMode(createdCollection.defaultModeId, {...plan.provision.background_color});
    createdCollection.setPluginData('bloomSemanticTokens', JSON.stringify({pageId: page.id,
      sourceHash: plan.provision.graph_sha256, collectionId: createdCollection.id}));

    createdFrame = figma.createFrame(); cleanup.push(() => createdFrame.remove());
    page.appendChild(createdFrame); createdFrame.name = 'Little Hands · Booking CTA round trip';
    createdFrame.x = plan.provision.position.x; createdFrame.y = plan.provision.position.y;
    createdFrame.resize(NATIVE_PROVISION_FRAME.width, NATIVE_PROVISION_FRAME.height);
    createdFrame.layoutMode = 'VERTICAL'; createdFrame.primaryAxisSizingMode = 'FIXED'; createdFrame.counterAxisSizingMode = 'FIXED';
    createdFrame.primaryAxisAlignItems = 'MIN'; createdFrame.counterAxisAlignItems = 'MIN'; createdFrame.itemSpacing = 16;
    createdFrame.paddingTop = 20; createdFrame.paddingRight = 20; createdFrame.paddingBottom = 20; createdFrame.paddingLeft = 20;
    createdFrame.fills = []; createdFrame.clipsContent = false;
    createdFrame.setPluginData('semanticKey', plan.provision.frame_key);
    createdFrame.setPluginData(NATIVE_PROVISION_OWNER, JSON.stringify({schema: NATIVE_PROVISION_SCHEMA, page_id: plan.page_id,
      frame_key: plan.provision.frame_key, main_key: plan.provision.main_key, instance_keys: plan.provision.instance_keys,
      source_graph_sha256: plan.provision.graph_sha256, seed_variable_id: createdSeed.id,
      seed_collection_id: createdCollection.id}));

    createdMain = figma.createComponent(); cleanup.push(() => createdMain.remove()); createdFrame.appendChild(createdMain);
    createdMain.name = 'bookingCTA · local main'; createdMain.resize(128, 48);
    createdMain.layoutMode = 'HORIZONTAL'; createdMain.primaryAxisSizingMode = 'AUTO'; createdMain.counterAxisSizingMode = 'FIXED';
    createdMain.primaryAxisAlignItems = 'CENTER'; createdMain.counterAxisAlignItems = 'CENTER';
    createdMain.paddingTop = 11; createdMain.paddingBottom = 11; createdMain.paddingLeft = 22; createdMain.paddingRight = 22; createdMain.itemSpacing = 8;
    createdMain.cornerRadius = 0;
    createdMain.fills = [figma.variables.setBoundVariableForPaint({type: 'SOLID', color: {...plan.provision.background_color}, opacity: 1}, 'color', createdSeed)];
    createdMain.setPluginData('semanticKey', plan.provision.main_key);
    createdLabel = figma.createText(); cleanup.push(() => createdLabel.remove()); createdMain.appendChild(createdLabel);
    createdLabel.name = 'bookingCTA label'; createdLabel.fontName = font; createdLabel.fontSize = 14; createdLabel.characters = plan.provision.labels.main;
    createdLabel.fills = [{type: 'SOLID', color: {...plan.provision.text_color}, opacity: 1}];
    for (const key of plan.provision.instance_keys) {
      const instance = createdMain.createInstance(); cleanup.push(() => instance.remove()); createdFrame.appendChild(instance);
      createdInstances.push(instance);
      instance.name = key; instance.setPluginData('semanticKey', key);
      const instanceLabel = instance.findOne(node => node.type === 'TEXT');
      if (!instanceLabel) throw Error('Created CTA instance has no visible text override target');
      instanceLabel.characters = plan.provision.labels[key];
    }
  } catch (error) {
    for (const undo of cleanup.reverse()) try { undo(); } catch (_) {}
    throw error;
  }
  nativeEditScope(figma, plan);
  const actualFrame = page.findAll(node => nativeProvisionSemantic(node) === plan.provision.frame_key);
  if (actualFrame.length !== 1) throw Error('CTA workbench postcondition failed; created nodes were retained for review');
  try {
    const provision = await nativeProvisionMatches(figma, page, plan, actualFrame[0]);
    const readback = await nativeEditDiscovery(figma, plan);
    return {...readback, native_edit: {plan_sha256: NATIVE_EDIT_SHA256, applied: true, operation: 'apply',
      changed: 6, provision, idempotent: false}};
  } catch (error) {
    let safe = false;
    try {
      const marker = JSON.parse(createdFrame.getPluginData(NATIVE_PROVISION_OWNER) || 'null');
      const originalIds = new Set(plan.provision.page_roots.map(row => row.id));
      const currentRoots = nativeProvisionRows(page);
      const extras = currentRoots.filter(row => !originalIds.has(row.id));
      const expectedDirect = new Set([createdMain.id, ...createdInstances.map(node => node.id)]);
      const frameChildren = new Set(createdFrame.children.map(node => node.id));
      const mainChildren = new Set(createdMain.children.map(node => node.id));
      const seedStillSole = createdCollection.variableIds.length === 1 && createdCollection.variableIds[0] === createdSeed.id;
      safe = figma.fileKey === plan.file_key && figma.currentPage.id === plan.page_id && createdFrame.parent === page &&
        marker?.schema === NATIVE_PROVISION_SCHEMA && marker.page_id === plan.page_id && marker.frame_key === plan.provision.frame_key &&
        extras.length === 1 && extras[0].id === createdFrame.id && frameChildren.size === expectedDirect.size &&
        [...expectedDirect].every(id => frameChildren.has(id)) && mainChildren.size === 1 && mainChildren.has(createdLabel.id) && seedStillSole &&
        nativeProvisionSemantic(createdMain) === plan.provision.main_key &&
        plan.provision.instance_keys.every((key, index) => nativeProvisionSemantic(createdInstances[index]) === key);
      if (safe) await nativeProvisionMatches(figma, page, plan, createdFrame);
    } catch (_) { safe = false; }
    if (safe) {
      for (const undo of cleanup.reverse()) try { undo(); } catch (_) {}
      error.native_rollback = 'created CTA frame and seed collection removed after failed getter';
    } else {
      error.rollback_conflicts = ['Created CTA frame retained because exact ownership or unchanged children could not be confirmed'];
    }
    throw error;
  }
}
