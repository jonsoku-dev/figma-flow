/* Shared native authoring helpers. Call only inside the caller's authorized
 * transaction, before creating instances. No live document is edited on import.
 * layoutFoundationSets receives ONLY newly authored, caller-owned sets already
 * in its library. createFoundationPalette creates new nodes, rolls back on error,
 * and delegates all variable creation/binding/readback to ensureSemanticTokens.
 *
 * Example tokens: [{name:'size/body',type:'FLOAT',value:16},
 * {name:'type/body',type:'FLOAT',alias:'size/body'},
 * {name:'space/4',type:'FLOAT',value:16},
 * {name:'space/content',type:'FLOAT',alias:'space/4'},
 * {name:'palette/ink',type:'COLOR',value:{r:0,g:0,b:0}},
 * {name:'color/ink',type:'COLOR',alias:'palette/ink'}].
 * Pass type:{token:'type/body',value:16}, space:{token:'space/content',value:16},
 * ink:{token:'color/ink',value:{r:0,g:0,b:0}}, sourceHash, tokens, samples:
 * [{mainComponentId,label,component,variant,action,state,useCases:[...]}].
 */
function layoutFoundationSets(library, sets) {
  if (!library || !Array.isArray(sets) || !sets.length || sets.some(set =>
    set.type !== 'COMPONENT_SET' || set.parent !== library)) throw new Error('New owned sets in their library required');
  for (const node of [library, ...sets]) {
    node.layoutMode = 'VERTICAL';
    node.primaryAxisSizingMode = 'AUTO';
    node.counterAxisSizingMode = 'AUTO';
    node.itemSpacing = 24;
    node.paddingTop = node.paddingBottom = node.paddingLeft = node.paddingRight = 24;
  }
}

async function createFoundationPalette(figma, page, contract, ensureTokens) {
  const fail = message => { throw new Error(`Foundation palette: ${message}`); };
  if (!contract?.sourceHash || typeof ensureTokens !== 'function' || !contract.samples?.length) fail('source, samples and shared token author required');
  for (const role of ['type', 'space', 'ink']) if (!contract[role]?.token || contract[role].value === undefined) fail(`missing ${role} role`);
  if (!Number.isFinite(contract.type.value) || contract.type.value <= 0 || !Number.isFinite(contract.space.value) || contract.space.value <= 0) fail('positive font size and spacing required');
  const labels = new Set();
  const mains = [];
  for (const sample of contract.samples) {
    if (typeof sample.label !== 'string' || sample.label.trim().length < 3 || labels.has(sample.label.trim().toLowerCase()) ||
        ['component', 'variant', 'action', 'state'].some(key => typeof sample[key] !== 'string' || !sample[key].trim()) ||
        !Array.isArray(sample.useCases) || !sample.useCases.length || sample.useCases.some(value => typeof value !== 'string' || !value.trim())) fail('unique labeled samples with action, state and use cases required');
    labels.add(sample.label.trim().toLowerCase());
    const main = await figma.getNodeByIdAsync(sample.mainComponentId);
    if (main?.type !== 'COMPONENT' || main.parent?.type !== 'COMPONENT_SET' || !Object.values(main.variantProperties || {}).includes(sample.variant)) fail('sample must resolve a real main/set/variant');
    mains.push(main);
  }
  const font = contract.font || {family: 'Inter', style: 'Regular'};
  await figma.loadFontAsync(font);
  let library, tokens;
  const bindings = [], samples = [], created = [];
  const removeCreated = () => { for (const node of [...created].reverse()) if (!node.removed) node.remove(); };
  const bind = (node, field, token) => bindings.push({key: node.id, field, token});
  const frame = name => {
    const node = figma.createFrame();
    created.push(node);
    node.name = name;
    node.layoutMode = 'VERTICAL';
    node.primaryAxisSizingMode = 'AUTO';
    node.counterAxisSizingMode = 'AUTO';
    node.fills = [];
    node.itemSpacing = contract.space.value;
    bind(node, 'itemSpacing', contract.space.token);
    for (const field of ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft']) {
      node[field] = contract.space.value;
      bind(node, field, contract.space.token);
    }
    return node;
  };
  const text = characters => {
    const node = figma.createText();
    created.push(node);
    node.fontName = font;
    node.fontSize = contract.type.value;
    node.characters = characters;
    node.fills = [{type:'SOLID', color:{r:contract.ink.value.r,g:contract.ink.value.g,b:contract.ink.value.b}, opacity:contract.ink.value.a ?? 1}];
    bind(node, 'fontSize', contract.type.token);
    bind(node, 'fills', contract.ink.token);
    return node;
  };
  try {
    library = frame(contract.name || 'Component palette');
    page.appendChild(library);
    library.x = contract.x ?? 0;
    library.y = contract.y ?? 0;
    for (const [index, sample] of contract.samples.entries()) {
      const card = frame(sample.label);
      library.appendChild(card);
      const label = text(sample.label);
      card.appendChild(label);
      const instance = mains[index].createInstance();
      created.push(instance);
      card.appendChild(instance);
      instance.name = sample.label;
      if (contract.configureSample) contract.configureSample(instance, mains[index], sample);
      const documentation = text(`Action: ${sample.action}\nState: ${sample.state}\nUse: ${sample.useCases.join('; ')}`);
      card.appendChild(documentation);
      samples.push({...sample, labelNodeId:label.id, documentationNodeId:documentation.id, instanceId:instance.id, mainComponentId:mains[index].id, componentSetId:mains[index].parent.id});
    }
    tokens = await ensureTokens(figma, page, {sourceHash:contract.sourceHash, collectionName:contract.collectionName, tokens:contract.tokens, bindings});
    return {libraryId:library.id, samples, tokenReadback:tokens,
      async rollback() { await tokens.rollback(); removeCreated(); }};
  } catch (error) {
    if (tokens) await tokens.rollback();
    removeCreated();
    throw error;
  }
}
if (typeof module !== 'undefined') module.exports = {layoutFoundationSets, createFoundationPalette};
