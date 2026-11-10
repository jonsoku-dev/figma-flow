function resolveInstanceSemanticKey(node) {
  const path = [];
  for (let current = node; current; current = current.parent) {
    if (current.type === "INSTANCE") {
      let mapping;
      try { mapping = JSON.parse(current.getPluginData("semanticComponent") || "null"); }
      catch (_) { throw new Error(`Invalid semanticComponent on ${current.id}`); }
      if (mapping) {
        if (!path.length) return mapping.key || null;
        const matches = (mapping.childKeys || []).filter(child => JSON.stringify(child.path) === JSON.stringify(path));
        if (matches.length > 1) throw new Error(`Ambiguous semanticComponent path on ${current.id}`);
        if (matches.length) return matches[0].key;
      }
    }
    if (current.parent) path.unshift(Array.from(current.parent.children || []).indexOf(current));
  }
  return null;
}

async function readNativeSemantics(figma, page) {
  const fail = message => { throw new Error(`Native semantic read: ${message}`); };
  if (!page?.id || typeof page.loadAsync !== "function") fail("selected page required");
  await page.loadAsync();
  const nodes = [page, ...page.findAll(() => true)];
  const rows = [];
  const variableIds = new Set();
  const collectionIds = new Set();
  const styleIds = new Set();
  const styles = [];
  const unavailableFields = [];
  const copy = value => JSON.parse(JSON.stringify(value));
  const aliases = value => {
    if (!value || typeof value !== "object") return;
    if (value.type === "VARIABLE_ALIAS" && typeof value.id === "string") variableIds.add(value.id);
    else for (const item of Object.values(value)) aliases(item);
  };
  for (const node of nodes) {
    const semanticKey = resolveInstanceSemanticKey(node) || node.getPluginData("semanticKey") || null;
    const row = { id: node.id, parentId: node.parent?.id || null, type: node.type, name: node.name, key: semanticKey, semanticKey, frameKey: node.getPluginData("frameKey") || null };
    row.unavailable_fields = {};
    for (const field of ["x", "y", "width", "height", "visible", "absoluteBoundingBox", "characters", "fontName", "fontSize", "textStyleId", "fillStyleId", "strokeStyleId", "lineHeight", "letterSpacing", "paragraphSpacing", "textCase", "textDecoration", "opacity", "cornerRadius", "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius", "layoutMode", "primaryAxisSizingMode", "counterAxisSizingMode", "layoutSizingHorizontal", "layoutSizingVertical", "layoutWrap", "textAutoResize", "textAlignHorizontal", "textAlignVertical", "primaryAxisAlignItems", "counterAxisAlignItems", "minWidth", "maxWidth", "minHeight", "maxHeight", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "itemSpacing", "boundVariables", "annotations", "fills", "strokes", "effects", "explicitVariableModes", "resolvedVariableModes", "variantProperties", "componentProperties", "componentPropertyDefinitions", "annotationCategoryId"]) {
      try {
        if (!(field in node)) { row.unavailable_fields[field] = "unsupported on this node"; continue; }
        const value = node[field];
        if (value === undefined || typeof value === "symbol") { row.unavailable_fields[field] = "unavailable or mixed"; continue; }
        row[field] = copy(value);
        if (["boundVariables", "fills", "strokes"].includes(field)) aliases(value);
        if (["textStyleId", "fillStyleId", "strokeStyleId"].includes(field) && typeof value === "string" && value) styleIds.add(value);
      } catch (error) { row.unavailable_fields[field] = error.message || String(error); }
    }
    if (node.type === "TEXT" && typeof node.getStyledTextSegments === "function") {
      try {
        row.textSegments = copy(node.getStyledTextSegments(["fontSize", "fontName", "textStyleId", "fillStyleId", "boundVariables"]));
        for (const segment of row.textSegments) {
          aliases(segment.boundVariables);
          for (const field of ["textStyleId", "fillStyleId"]) if (typeof segment[field] === "string" && segment[field]) styleIds.add(segment[field]);
        }
      } catch (error) { row.unavailable_fields.textSegments = error.message || String(error); }
    }
    if (node.type === "INSTANCE") {
      try {
        if (typeof node.getMainComponentAsync !== "function") throw new Error("main component API unavailable");
        const main = await node.getMainComponentAsync();
        if (!main) throw new Error("main component unavailable");
        row.mainComponentId = main.id;
        row.componentSetId = main.parent?.type === "COMPONENT_SET" ? main.parent.id : null;
      } catch (error) {
        row.unavailable_fields.mainComponentId = error.message || String(error);
      }
    } else if (node.type === "COMPONENT") {
      row.componentSetId = node.parent?.type === "COMPONENT_SET" ? node.parent.id : null;
    } else if (node.type === "COMPONENT_SET") {
      row.componentIds = Array.from(node.children).filter(child => child.type === "COMPONENT").map(child => child.id);
    }
    for (const [field, reason] of Object.entries(row.unavailable_fields)) unavailableFields.push({ nodeId: node.id, field, reason });
    rows.push(row);
  }
  // Read native getters explicitly: JSON.stringify(style) can omit API-backed fields.
  for (const id of styleIds) {
    try {
      if (typeof figma.getStyleByIdAsync !== "function") throw new Error("native style read API unavailable");
      const style = await figma.getStyleByIdAsync(id);
      if (!style) throw new Error("native style unavailable");
      const row = { id: style.id, type: style.type, name: style.name, unavailable_fields: {} };
      const fields = style.type === "TEXT" ? ["fontName", "fontSize", "lineHeight", "letterSpacing", "paragraphSpacing", "paragraphIndent", "textCase", "textDecoration", "boundVariables"] : style.type === "PAINT" ? ["paints", "boundVariables"] : [];
      for (const field of fields) {
        try {
          const value = style[field];
          if (value === undefined || typeof value === "symbol") continue;
          row[field] = copy(value);
          aliases(value);
        } catch (error) {
          row.unavailable_fields[field] = error.message || String(error);
          unavailableFields.push({ styleId: id, field, reason: row.unavailable_fields[field] });
        }
      }
      styles.push(row);
    } catch (error) {
      unavailableFields.push({ styleId: id, field: "style", reason: error.message || String(error) });
    }
  }
  if (typeof figma.variables?.getLocalVariableCollectionsAsync !== "function") fail("native variable collection read API unavailable");
  const localCollections = await figma.variables.getLocalVariableCollectionsAsync();
  for (const collection of localCollections) {
    let marker;
    try { marker = JSON.parse(collection.getPluginData("bloomSemanticTokens") || "null"); }
    catch (_) { continue; }
    if (marker?.pageId === page.id) collectionIds.add(collection.id);
  }
  const variables = new Map();
  const collections = new Map();
  const readVariable = async id => {
    if (variables.has(id)) return;
    if (typeof figma.variables.getVariableByIdAsync !== "function") fail(`native variable read API unavailable: ${id}`);
    const variable = await figma.variables.getVariableByIdAsync(id);
    if (!variable || !variable.valuesByMode || !variable.variableCollectionId) fail(`native variable unavailable: ${id}`);
    variables.set(id, { id: variable.id, name: variable.name, resolvedType: variable.resolvedType, variableCollectionId: variable.variableCollectionId, valuesByMode: copy(variable.valuesByMode) });
    collectionIds.add(variable.variableCollectionId);
    aliases(variable.valuesByMode);
  };
  while ([...collectionIds].some(id => !collections.has(id)) || [...variableIds].some(id => !variables.has(id))) {
    for (const id of [...collectionIds]) {
      if (collections.has(id)) continue;
      const local = localCollections.find(item => item.id === id);
      if (!local && typeof figma.variables.getVariableCollectionByIdAsync !== "function") fail(`native collection read API unavailable: ${id}`);
      const collection = local || await figma.variables.getVariableCollectionByIdAsync(id);
      if (!collection || !Array.isArray(collection.modes) || !collection.defaultModeId || !Array.isArray(collection.variableIds)) fail(`native collection unavailable: ${id}`);
      collections.set(id, { id, name: collection.name, modes: copy(collection.modes), defaultModeId: collection.defaultModeId, variableIds: [...collection.variableIds] });
      for (const variableId of collection.variableIds) variableIds.add(variableId);
    }
    for (const id of [...variableIds]) await readVariable(id);
  }
  return { pageId: page.id, selectedPageIds: [page.id], collectionIds: [...collections.keys()], collections: [...collections.values()], variables: [...variables.values()], nodes: rows, styles, unavailableFields };
}
if (typeof module !== "undefined") module.exports = { resolveInstanceSemanticKey, readNativeSemantics };
