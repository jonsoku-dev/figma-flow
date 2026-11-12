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

function mergeNativeRasterImages(target, source) {
  for (const [hash, bytes] of Object.entries(source || {})) {
    if (Object.prototype.hasOwnProperty.call(target, hash) && target[hash] !== bytes)
      throw new Error(`Conflicting native raster bytes for image hash ${hash}`);
    target[hash] = bytes;
  }
  return target;
}

const summaryFields = new Set(["x", "y", "width", "height", "visible"]);

function summaryProjectable(request) {
  if (!request || request.profile !== "summary") return null;
  const fail = message => { throw new Error(`Native semantic read: ${message}`); };
  if (!Array.isArray(request.nodeIds) || !request.nodeIds.length || request.nodeIds.some(id => typeof id !== "string") || new Set(request.nodeIds).size !== request.nodeIds.length) fail("summary nodeIds required");
  if (!Array.isArray(request.fields) || !request.fields.length || request.fields.some(field => typeof field !== "string") || new Set(request.fields).size !== request.fields.length) fail("summary fields required");
  return request.fields.every(field => summaryFields.has(field));
}

async function projectNativeSummary(figma, page, request) {
  const fail = message => { throw new Error(`Native semantic read: ${message}`); };
  if (!page?.id || typeof page.loadAsync !== "function") fail("selected page required");
  await page.loadAsync();
  const nodes = [page, ...page.findAll(() => true)];
  const byId = new Map();
  for (const node of nodes) {
    if (!request.nodeIds.includes(node.id) || byId.has(node.id)) continue;
    const row = {id: node.id, parentId: node.parent?.id || null, type: node.type, name: node.name};
    for (const field of request.fields) {
      if (!(field in node)) continue;
      const value = node[field];
      if (value === undefined || typeof value === "symbol") continue;
      row[field] = JSON.parse(JSON.stringify(value));
    }
    byId.set(node.id, row);
  }
  if (byId.size !== request.nodeIds.length) fail("summary node missing");
  return {
    schema: "figma-flow-native-read-summary-v1",
    coverage: {profile: "summary", nodeIds: [...request.nodeIds], fields: [...request.fields], complete: false, omitted: ["styles", "variables", "collections", "rasterImages", "textSegments"]},
    nodes: request.nodeIds.map(id => byId.get(id))
  };
}

async function readNativeSemantics(figma, page) {
  // Callers that omit the third argument stay on the full snapshot. The declared parameters stay (figma, page).
  const request = arguments[2];
  if (summaryProjectable(request) === true) return projectNativeSummary(figma, page, request);
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
  const rasterImages = Object.create(null);
  const rasterImageReads = new Map();
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
    const boardMarker = node.getPluginData("designNoteBoard");
    if (boardMarker) {
      try { row.designNoteBoard = JSON.parse(boardMarker); }
      catch (_) { row.designNoteBoard = {status:"invalid",raw:boardMarker}; }
    }
    const specification = node.getPluginData("figmaFlowSpecification");
    if (specification) {
      try {
        const value = JSON.parse(specification), spec = value.specification;
        const human=value.human_annotation,board=human&&nodes.find(item=>item.id===human.board?.boardId),text=board?.children?.find(item=>item.id===human.board?.textNodeId),expectedUrl=human&&typeof figma.fileKey==='string'?`https://www.figma.com/design/${encodeURIComponent(figma.fileKey)}?node-id=${encodeURIComponent(human.board.textNodeId.replace(/:/g,'-'))}`:null;
        if (unescape(encodeURIComponent(specification)).length >= 90000 || value.schema !== FLOW_SPEC.schemas.native || value.semantic_key !== semanticKey || value.target_id !== node.id || typeof value.source_owner_hash !== "string" || !value.source_owner_hash || !["applied","pending","conflict"].includes(value.state) || !Array.isArray(value.legacy_annotations) || value.legacy_annotations.some(slot => !Number.isInteger(slot?.index) || slot.index < 0 || typeof slot.annotation?.label !== "string") || spec?.schema !== FLOW_SPEC.schemas.readable || !["id","kind","screen_id","target_id","title","meaning_sha256","source_graph_sha256","source_graph_encoding","display_text"].every(key => typeof spec[key] === "string" && spec[key].trim()) || !spec.meaning || !spec.trace || (spec.presentation==='connected-spec-v2'&&(!Object.keys(FLOW_SPEC_LABELS).includes(spec.locale)||!Array.isArray(spec.sections)||typeof spec.annotation_text!=='string'||!spec.annotation_text.trim())) || (spec.presentation==='connected-spec-v2'&&value.state==='applied'&&!human) || (human && (human.schema!==FLOW_SPEC.schemas.human || !Number.isInteger(human.index) || human.index<0 || !human.annotation || !board || board.parent!==page || !text || text.parent!==board || text.getPluginData('semanticKey')!==board.getPluginData('semanticKey')+':'+human.board.key || human.board.key!==human.board.key.trim() || human.board.key==='' || text.characters!==spec.title+'\n'+spec.display_text || JSON.stringify(JSON.parse(board.getPluginData('designNoteBoard')||'null'))!==JSON.stringify({pageId:page.id,sourceHash:value.source_owner_hash}) || typeof human.url!=="string" || human.url!==expectedUrl || !Array.isArray(node.annotations) || !equalNativeValue(node.annotations[human.index],human.annotation) || !nativeHumanMarkdownMatches(human.annotation,spec,human.url) || node.annotations.filter(annotation=>nativeHumanMarkdownMatches(annotation,spec,human.url)).length!==1 || text.getRangeHyperlink?.(0,text.characters.length)?.type!=='NODE' || text.getRangeHyperlink?.(0,text.characters.length)?.value!==node.id))) throw new Error("invalid native specification wrapper");
        row.specification = copy(value);
        row.specification_status = "observed";
      } catch (error) {
        row.specification = {raw:specification,error:error.message || String(error)};
        row.specification_status = "invalid";
      }
    }
    if (node.type === "TEXT" && typeof node.getRangeHyperlink === "function") {
      try { row.hyperlink = copy(node.getRangeHyperlink(0,node.characters.length) || null); }
      catch (error) { row.unavailable_fields.hyperlink = error.message || String(error); }
    }
    for (const field of ["x", "y", "width", "height", "visible", "absoluteBoundingBox", "characters", "fontName", "fontSize", "textStyleId", "fillStyleId", "strokeStyleId", "lineHeight", "letterSpacing", "paragraphSpacing", "textCase", "textDecoration", "opacity", "cornerRadius", "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius", "layoutMode", "primaryAxisSizingMode", "counterAxisSizingMode", "layoutSizingHorizontal", "layoutSizingVertical", "layoutWrap", "textAutoResize", "textAlignHorizontal", "textAlignVertical", "primaryAxisAlignItems", "counterAxisAlignItems", "minWidth", "maxWidth", "minHeight", "maxHeight", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "itemSpacing", "boundVariables", "annotations", "reactions", "clipsContent", "fills", "strokes", "effects", "explicitVariableModes", "resolvedVariableModes", "variantProperties", "componentProperties", "componentPropertyDefinitions", "annotationCategoryId"]) {
      try {
        if (!(field in node)) { row.unavailable_fields[field] = "unsupported on this node"; continue; }
        const value = node[field];
        if (value === undefined || typeof value === "symbol") { row.unavailable_fields[field] = "unavailable or mixed"; continue; }
        row[field] = copy(value);
        if (["boundVariables", "fills", "strokes"].includes(field)) aliases(value);
        if (["textStyleId", "fillStyleId", "strokeStyleId"].includes(field) && typeof value === "string" && value) styleIds.add(value);
      } catch (error) { row.unavailable_fields[field] = error.message || String(error); }
    }
    try {
      const asset = node.getPluginData("rasterAsset");
      const paint = Array.isArray(node.fills) && node.fills.length === 1 && node.fills[0]?.type === "IMAGE" ? node.fills[0] : null;
      if (asset && paint) {
        row.rasterAsset = asset;
        if (typeof paint.imageHash !== "string" || !paint.imageHash) throw new Error("native raster image hash unavailable");
        if (typeof figma.getImageByHash !== "function" || typeof figma.base64Encode !== "function") throw new Error("native raster image read API unavailable");
        if (!rasterImageReads.has(paint.imageHash)) rasterImageReads.set(paint.imageHash, (async () => {
          const image = figma.getImageByHash(paint.imageHash);
          if (!image || typeof image.getBytesAsync !== "function") throw new Error("native raster image unavailable");
          return figma.base64Encode(await image.getBytesAsync());
        })());
        rasterImages[paint.imageHash] = await rasterImageReads.get(paint.imageHash);
        row.rasterImageRef = paint.imageHash;
      }
    } catch (error) { row.unavailable_fields.rasterImageBytes = error.message || String(error); }
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
      try { if ("overrides" in node) row.overrides = copy(node.overrides); }
      catch (error) { row.unavailable_fields.overrides = error.message || String(error); }
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
  return { pageId: page.id, selectedPageIds: [page.id], collectionIds: [...collections.keys()], collections: [...collections.values()], variables: [...variables.values()], nodes: rows, styles, unavailableFields, rasterImages };
}
async function nativeReadGetterLedger(figma, page, request) {
  const names = [];
  const seen = new Set();
  const proxies = new WeakMap();
  const wrap = node => {
    if (!node || typeof node !== "object") return node;
    if (proxies.has(node)) return proxies.get(node);
    const proxy = new Proxy(node, {
      get(target, key, receiver) {
        if (typeof key === "string" && key !== "then") {
          const token = target.id + "." + key;
          if (!seen.has(token)) { seen.add(token); names.push(token); }
        }
        if (key === "findAll") return predicate => (target.findAll(predicate) || []).map(wrap);
        if (key === "children") return (target.children || []).map(wrap);
        if (key === "parent") return wrap(target.parent);
        const value = Reflect.get(target, key, receiver);
        return typeof value === "function" ? value.bind(target) : value;
      }
    });
    proxies.set(node, proxy);
    return proxy;
  };
  return {schema: "figma-flow-native-read-ledger-v1", full: await readNativeSemantics(figma, wrap(page), request), getters: names};
}
function requireFullNativeRead(read) {
  if (!read || read.schema === "figma-flow-native-read-summary-v1" || (read.coverage && read.coverage.complete === false)) throw new Error("partial native read cannot be stored as full evidence");
  return read;
}
if (typeof module !== "undefined") module.exports = { resolveInstanceSemanticKey, readNativeSemantics, mergeNativeRasterImages, nativeReadGetterLedger, requireFullNativeRead };

function equalNativeValue(a,b){return JSON.stringify(a,(_,value)=>value&&typeof value==="object"&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]])):value)===JSON.stringify(b,(_,value)=>value&&typeof value==="object"&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]])):value);}
function nativeHumanMarkdownMatches(annotation,spec,url){const label=FLOW_SPEC_LABELS[spec.locale];return Boolean(label&&typeof spec.annotation_text==="string"&&annotation?.labelMarkdown===`${spec.title}\n${spec.annotation_text.trim()}\n\n[${label}](${url})`);}
