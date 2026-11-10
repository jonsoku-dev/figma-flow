/* Native variables only. Bind main components before creating their instances.
 * API follows https://github.com/figma/plugin-typings/blob/master/plugin-api.d.ts
 * contract: {sourceHash, collectionName?, tokens:[{name,type,value?|alias?}],
 * bindings:[{key:semanticKeyOrNodeId,field,token,paintIndex?}], strictValues?:boolean}.
 * fontFamily uses the real whole-text STRING binding API. strictValues rejects
 * changed immutable draft literals without overwriting historical replay edits.
 * Successful calls return rollback() for the caller's larger transaction.
 */
async function ensureSemanticTokens(figma, page, contract) {
  const marker = "bloomSemanticTokens";
  const fail = message => { throw new Error(`Semantic tokens: ${message}`); };
  const clone = value => JSON.parse(JSON.stringify(value));
  const aliasIs = (value, id) => value && value.type === "VARIABLE_ALIAS" && value.id === id;
  const close = (a, b) => typeof a === "number" && typeof b === "number" && Math.abs(a - b) < 0.00001;
  const colorIs = (a, b) => a && b && ["r", "g", "b"].every(key => close(a[key], b[key])) && close(a.a === undefined ? 1 : a.a, b.a === undefined ? 1 : b.a);
  const numericFields = new Set(["cornerRadius", "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "itemSpacing", "fontSize"]);
  const familyOf = node => {
    const names = node.type === 'TEXT' && node.characters.length ? node.getRangeAllFontNames(0,node.characters.length) : [];
    const families = [...new Set(names.map(font => font.family))];
    return families.length === 1 ? families[0] : null;
  };
  const familyAlias = node => {
    const actual = node.getRangeBoundVariable(0,node.characters.length,'fontFamily');
    return actual && typeof actual !== 'symbol' ? actual : node.boundVariables?.fontFamily;
  };
  const corners = ["topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"];
  if (!page || !page.id || !contract || typeof contract.sourceHash !== "string" || !contract.sourceHash) fail("page and sourceHash are required");
  if (!Array.isArray(contract.tokens) || !contract.tokens.length || !Array.isArray(contract.bindings) || !contract.bindings.length) fail("nonempty tokens and bindings are required");
  const definitions = new Map();
  for (const token of contract.tokens) {
    if (!token || typeof token.name !== "string" || !token.name || definitions.has(token.name) || !["COLOR", "FLOAT", "STRING", "BOOLEAN"].includes(token.type)) fail("invalid or duplicate token definition");
    const hasAlias = Object.prototype.hasOwnProperty.call(token, "alias");
    if (hasAlias === Object.prototype.hasOwnProperty.call(token, "value")) fail(`${token.name} requires exactly one of value or alias`);
    if (!hasAlias && !(token.type === "COLOR" ? token.value && ["r", "g", "b"].every(key => Number.isFinite(token.value[key]) && token.value[key] >= 0 && token.value[key] <= 1) && (token.value.a === undefined || Number.isFinite(token.value.a) && token.value.a >= 0 && token.value.a <= 1) : token.type === "FLOAT" ? Number.isFinite(token.value) : token.type === "BOOLEAN" ? typeof token.value === "boolean" : typeof token.value === "string")) fail(`invalid value for ${token.name}`);
    definitions.set(token.name, token);
  }
  for (const token of definitions.values()) {
    const seen = new Set([token.name]);
    let current = token;
    while (Object.prototype.hasOwnProperty.call(current, "alias")) {
      const target = definitions.get(current.alias);
      if (!target || target.type !== token.type || seen.has(target.name)) fail(`invalid or cyclic alias for ${token.name}`);
      seen.add(target.name);
      current = target;
    }
  }
  await page.loadAsync();
  const nodes = [page, ...page.findAll(() => true)];
  const findNode = key => {
    const matches = nodes.filter(node => node.id === key || node.getPluginData("semanticKey") === key);
    if (typeof key !== "string" || !key || matches.length !== 1) fail(`missing or ambiguous node ${key}`);
    return matches[0];
  };
  const jobs = [];
  const slots = new Set();
  for (const binding of contract.bindings) {
    if (!binding || !definitions.has(binding.token)) fail("binding references missing token");
    const node = findNode(binding.key);
    const paint = binding.field === "fills" || binding.field === "strokes";
    const textFamily = binding.field === 'fontFamily';
    const index = binding.paintIndex === undefined ? 0 : binding.paintIndex;
    if (!paint && !textFamily && !numericFields.has(binding.field)) fail(`unsupported field ${binding.field}`);
    if (definitions.get(binding.token).type !== (paint ? "COLOR" : textFamily ? 'STRING' : "FLOAT")) fail(`type mismatch for ${binding.key}.${binding.field}`);
    if (textFamily ? node.type !== "TEXT" || !node.characters.length || !familyOf(node) || typeof node.setRangeBoundVariable !== "function" || typeof node.getRangeBoundVariable !== "function" : !(binding.field in node) || (paint ? !Array.isArray(node[binding.field]) || !Number.isInteger(index) || index < 0 || !node[binding.field][index] || node[binding.field][index].type !== "SOLID" : typeof node[binding.field] !== "number" || !Number.isFinite(node[binding.field]) || typeof node.setBoundVariable !== "function")) fail(`unsupported or mixed value at ${binding.key}.${binding.field}`);
    const slot = `${node.id}:${binding.field}:${paint ? index : ""}`;
    if (slots.has(slot)) fail(`duplicate binding ${slot}`);
    slots.add(slot);
    let instance = false;
    for (let parent = node; parent && parent !== page; parent = parent.parent) if (parent.type === "INSTANCE") instance = true;
    let textStyle = null;
    if (contract.bindTextStyles && node.type === 'TEXT' && (textFamily || binding.field === 'fontSize') && typeof node.textStyleId === 'string' && node.textStyleId) {
      if (!Array.isArray(contract.ownedTextStyleIds) || !contract.ownedTextStyleIds.includes(node.textStyleId)) fail(`text style is outside the new owned transaction: ${node.textStyleId}`);
      textStyle = await figma.getStyleByIdAsync(node.textStyleId);
      if (!textStyle || textStyle.type !== 'TEXT' || typeof textStyle.setBoundVariable !== 'function' || typeof node.setTextStyleIdAsync !== 'function') fail('native bound typography style API unavailable');
    }
    jobs.push({ ...binding, node, paint, textFamily, textStyle, index, instance });
  }
  const collectionName = contract.collectionName || `BLOOM semantic · ${page.id}`;
  const ownership = item => {
    try { return JSON.parse(item.getPluginData(marker) || "null"); } catch (_) { return null; }
  };
  const collections = await figma.variables.getLocalVariableCollectionsAsync();
  const owned = collections.filter(item => {
    const owner = ownership(item);
    return owner && owner.pageId === page.id && owner.sourceHash === contract.sourceHash && owner.collectionId === item.id;
  });
  if (owned.length > 1 || owned.some(item => item.name !== collectionName)) fail("ambiguous or renamed managed collection");
  const pageOwned = collections.filter(item => ownership(item)?.pageId === page.id);
  if (pageOwned.some(item => !owned.includes(item))) fail("page belongs to a different token source; reconcile explicitly");
  if (!owned.length && collections.some(item => item.name === collectionName)) fail("collection name is already used without matching ownership");
  let collection = owned[0];
  const created = [];
  const undo = [];
  let createdCollection = false;
  let rolledBack = false;
  const rollback = async () => {
    if (rolledBack) return;
    const errors = [];
    for (const restore of undo.slice().reverse()) { try { await restore(); } catch (error) { errors.push(error.message); } }
    for (const variable of created.slice().reverse()) { try { variable.remove(); } catch (error) { errors.push(error.message); } }
    if (createdCollection) { try { collection.remove(); } catch (error) { errors.push(error.message); } }
    if (errors.length) fail(`rollback incomplete: ${errors.join("; ")}`);
    rolledBack = true;
  };
  try {
    if (!collection) {
      collection = figma.variables.createVariableCollection(collectionName);
      createdCollection = true;
      collection.setPluginData(marker, JSON.stringify({ pageId: page.id, sourceHash: contract.sourceHash, collectionId: collection.id }));
    }
    if (collection.modes.length !== 1) fail("managed collection must have one mode");
    const mode = collection.defaultModeId;
    const variables = Object.create(null);
    const localVariables = await figma.variables.getLocalVariablesAsync();
    const existing = localVariables.filter(variable => variable.variableCollectionId === collection.id);
    if (!Array.isArray(collection.variableIds) || collection.variableIds.length !== existing.length || collection.variableIds.some(id => !existing.some(variable => variable.id === id))) fail("managed collection contains unavailable native variables");
    if (existing.some(variable => !definitions.has(variable.name)) || new Set(existing.map(variable => variable.name)).size !== existing.length) fail("managed token names differ from contract");
    for (const token of definitions.values()) {
      let variable = existing.find(item => item.name === token.name);
      if (variable && variable.resolvedType !== token.type) fail(`native type mismatch for ${token.name}`);
      if (!variable) {
        variable = figma.variables.createVariable(token.name, collection, token.type);
        created.push(variable);
      }
      variables[token.name] = variable;
    }
    for (const token of definitions.values()) {
      const variable = variables[token.name];
      const isAlias = Object.prototype.hasOwnProperty.call(token, "alias");
      if (created.includes(variable)) variable.setValueForMode(mode, isAlias ? figma.variables.createVariableAlias(variables[token.alias]) : token.value);
      const actual = variable.valuesByMode[mode];
      if (isAlias ? !aliasIs(actual, variables[token.alias].id) : actual === undefined || actual && actual.type === "VARIABLE_ALIAS" || (token.type === "FLOAT" ? !Number.isFinite(actual) : token.type === "STRING" ? typeof actual !== "string" : token.type === "BOOLEAN" ? typeof actual !== "boolean" : !actual || !["r", "g", "b"].every(key => Number.isFinite(actual[key])))) fail(`native value or alias mismatch for ${token.name}`);
      if (contract.strictValues && !isAlias && (token.type === 'COLOR' ? !colorIs(actual,token.value) : actual !== token.value)) fail(`immutable native value differs for ${token.name}`);
    }
    const bound = (job, variable) => {
      const effectiveStyle = job.textStyle && job.node.textStyleId === job.textStyle.id ? job.textStyle.boundVariables?.[job.field] : null;
      const value = job.textFamily ? familyAlias(job.node) || effectiveStyle : job.paint ? job.node[job.field][job.index].boundVariables?.color : job.node.boundVariables?.[job.field];
      if (!job.paint && job.field === "cornerRadius" && corners.every(field => field in job.node)) return corners.every(field => aliasIs(job.node.boundVariables?.[field], variable.id));
      return Array.isArray(value) ? value.length > 0 && value.every(item => aliasIs(item, variable.id)) : aliasIs(value, variable.id);
    };
    jobs.sort((a,b)=>Number(a.instance)-Number(b.instance)||Number(b.textFamily)-Number(a.textFamily));
    for (const job of jobs) {
      const variable = variables[job.token];
      if (bound(job, variable)) {
        if (contract.strictValues) {
          const resolved=variable.resolveForConsumer(job.node);
          const actual=job.textFamily?familyOf(job.node):job.paint?{...job.node[job.field][job.index].color,a:job.node[job.field][job.index].opacity??1}:job.node[job.field];
          if (job.paint?!colorIs(actual,resolved.value):job.textFamily?actual!==resolved.value:!close(actual,resolved.value)) fail(`immutable bound consumer differs at ${job.key}.${job.field}`);
        }
        continue;
      }
      if (job.instance) fail(`bind main component before instance ${job.key}.${job.field}`);
      const fields = job.field === "cornerRadius" && corners.every(field => field in job.node) ? corners : [job.field];
      const previousBindings = job.textFamily ? [familyAlias(job.node)] : job.paint ? job.node[job.field][job.index].boundVariables?.color : fields.map(field => job.node.boundVariables?.[field]);
      if (job.paint ? previousBindings : previousBindings.some(Boolean)) fail(`existing different binding at ${job.key}.${job.field}`);
      const resolved = variable.resolveForConsumer(job.node);
      if (resolved.resolvedType !== definitions.get(job.token).type) fail(`unresolved token ${job.token}`);
      const actual = job.textFamily ? familyOf(job.node) : job.paint ? { ...job.node[job.field][job.index].color, a: job.node[job.field][job.index].opacity === undefined ? 1 : job.node[job.field][job.index].opacity } : job.node[job.field];
      if (job.paint ? !colorIs(actual, resolved.value) : job.textFamily ? actual !== resolved.value : !close(actual, resolved.value)) fail(`binding would change appearance at ${job.key}.${job.field}`);
      if (job.node.type === "TEXT") {
        const fonts = job.node.getRangeAllFontNames(0, job.node.characters.length);
        for (const font of fonts) await figma.loadFontAsync(font);
      }
      if (job.textStyle) {
        const previous = job.textStyle.boundVariables?.[job.field];
        if (previous && !aliasIs(previous,variable.id)) fail(`existing different style binding at ${job.textStyle.id}.${job.field}`);
        if (!previous) {
          undo.push(async () => { job.textStyle.setBoundVariable(job.field,null);await job.node.setTextStyleIdAsync(job.textStyle.id); });
          job.textStyle.setBoundVariable(job.field,variable);
        }
        await job.node.setTextStyleIdAsync(job.textStyle.id);
      } else if (job.paint) {
        const original = clone(job.node[job.field]);
        undo.push(() => { job.node[job.field] = original; });
        const paints = clone(original);
        paints[job.index] = figma.variables.setBoundVariableForPaint(paints[job.index], "color", variable);
        job.node[job.field] = paints;
      } else if (job.textFamily) {
        undo.push(() => job.node.setRangeBoundVariable(0,job.node.characters.length,'fontFamily',null));
        job.node.setRangeBoundVariable(0,job.node.characters.length,'fontFamily',variable);
      } else {
        const original = fields.map(field => job.node[field]);
        undo.push(() => { fields.forEach((field, index) => { job.node.setBoundVariable(field, null); job.node[field] = original[index]; }); });
        job.node.setBoundVariable(job.field, variable);
      }
      if (job.textStyle && job.node.textStyleId !== job.textStyle.id) fail(`native text style detached at ${job.key}`);
      if (!bound(job, variable)) fail(`native binding readback failed at ${job.key}.${job.field}`);
    }
    return { collectionId: collection.id, variables, tokens: Object.keys(variables).map(name => ({ name, id: variables[name].id, type: variables[name].resolvedType })), bindings: jobs.map(job => ({ key: job.key, nodeId: job.node.id, field: job.field, paintIndex: job.paint ? job.index : undefined, variableId: variables[job.token].id, inherited: job.instance })), rollback };
  } catch (error) {
    try { await rollback(); } catch (rollbackError) { throw new Error(`${error.message}; ${rollbackError.message}`); }
    throw error;
  }
}
