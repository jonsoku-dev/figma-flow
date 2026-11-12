/* Local Figma Design Plugin API runtime. PAYLOAD is prepended by the compiler. */
const KEY = "figmaFlow";
let busy = false;
let sessionNonce = null;
const font = { family: "Inter", style: "Regular" };
const bold = { family: "Inter", style: "Bold" };
let authoredFont = font;
function metadata(node, id, extra = {}) {
  node.setPluginData(KEY, JSON.stringify({ semantic_id: id, ...extra }));
  if (node.type !== "VARIABLE" && node.type !== "VARIABLE_COLLECTION") node.setPluginData("semanticKey", id);
}
function info(node) {
  try { return JSON.parse(node.getPluginData(KEY) || "{}"); }
  catch (_) { return {}; }
}
function annotate(node, annotation) {
  if (!annotation) return;
  if (PAYLOAD.specifications) {
    node.setPluginData(KEY, JSON.stringify({...info(node), annotation_mode: "metadata", technical_annotation: annotation}));
    return;
  }
  if (!("annotations" in node)) throw new Error(`Required native annotations unsupported: ${info(node).semantic_id}`);
  node.annotations = [{ label: annotation }];
  if (!node.annotations.some(item => item.label === annotation)) throw new Error("Required native annotation not retained");
  node.setPluginData(KEY, JSON.stringify({ ...info(node), annotation_mode: "native" }));
}
function textVariableAlias(node, field) {
  const ranged = node.type === "TEXT" && node.characters?.length && typeof node.getRangeBoundVariable === "function";
  const value = ranged ? node.getRangeBoundVariable(0, node.characters.length, field) : node.boundVariables?.[field];
  const aliases = Array.isArray(value) ? value : value ? [value] : [];
  if (!aliases.length) return null;
  if (aliases.some(alias => alias?.type !== "VARIABLE_ALIAS" || alias.id !== aliases[0]?.id)) throw new Error(`Mixed native typography binding: ${node.id}.${field}`);
  return aliases[0];
}
async function verifyHandoff(page) {
  const data = await readback([page], "native-handoff-verification");
  if (!data.fileKey) throw new Error("Actual native Figma file key unavailable for handoff");
  const nodes = [];
  function visit(node) { nodes.push(node); for (const child of node.children || []) visit(child); }
  visit(data.pages[0]);
  function find(identity) {
    const found = nodes.filter(node => node.semantic_id === identity);
    if (found.length !== 1) throw new Error(`Missing or ambiguous native node: ${identity}`);
    return found[0];
  }
  for (const [identity, note] of Object.entries(PAYLOAD.native_handoff.required_annotations)) {
    const node = find(identity), spec = PAYLOAD.specifications?.[identity];
    if (spec) {
      const actual = node.specification;
      if (actual?.state !== 'applied' || actual.target_id !== node.id || actual.semantic_key !== identity ||
          actual.source_owner_hash !== PAYLOAD.source_sha256 || actual.specification?.meaning_sha256 !== spec.meaning_sha256 ||
          actual.specification?.source_graph_sha256 !== spec.source_graph_sha256 || actual.specification?.display_text !== spec.display_text)
        throw new Error(`Required graph specification missing: ${identity}`);
      if (spec.presentation === 'connected-spec-v2') {
        const entry = PAYLOAD.expected_native_handoff.design_note_board.entries.find(entry => entry.target_key === identity);
        const board = find(PAYLOAD.expected_native_handoff.design_note_board.key);
        const text = find(`${PAYLOAD.expected_native_handoff.design_note_board.key}:${entry.key}`);
        const human = actual.human_annotation;
        const expected = connectedSpecificationMarkdown(spec,{fileKey:data.fileKey,textNodeId:text.id,locale:spec.locale});
        if (!human || human.board?.boardId !== board.id || human.board?.textNodeId !== text.id || human.board?.key !== entry.key ||
            human.url !== expected.url || !nativeAnnotationMatches(node.annotations?.[human.index],expected.markdown) ||
            JSON.stringify(node.annotations[human.index]) !== JSON.stringify(human.annotation))
          throw new Error(`Connected human specification annotation missing: ${identity}`);
      }
    } else if (PAYLOAD.specifications ? node.declared_metadata?.technical_annotation !== note : !(node.annotations || []).some(item => item.label === note))
      throw new Error(`Required native annotation missing: ${identity}`);
  }
  const boardContract = PAYLOAD.expected_native_handoff.design_note_board;
  if (!boardContract?.required) throw new Error("Required Design-mode note board contract missing");
  const board = find(boardContract.key);
  if (board.type !== "FRAME" || board.visible === false || board.layoutMode !== "VERTICAL" || board.itemSpacing <= 0)
    throw new Error("Required Design-mode note board missing or unreadable");
  for (const entry of boardContract.entries) {
    const target = find(entry.target_key), note = find(`${boardContract.key}:${entry.key}`);
    if (note.type !== "TEXT" || note.visible === false || note.fontSize < 14 || !note.characters.includes(entry.label) ||
        note.hyperlink?.type !== "NODE" || note.hyperlink.value !== target.id || !(board.children || []).some(child=>child.id===note.id))
      throw new Error(`Required Design-mode linked note missing: ${entry.key}`);
  }
  const variables = new Map(data.variables.map(variable => [variable.semantic_id, variable.id]));
  let instances = 0, bindings = 0;
  for (const screen of PAYLOAD.screens) for (const [index, element] of screen.elements.entries()) {
    if (element.kind !== "component") continue;
    const identity = element.id || `${screen.id}/element:${index}`, node = find(identity);
    const main = find(`component:${element.component}/${element.variant}`);
    if (node.type !== "INSTANCE" || main.type !== "COMPONENT" || node.main_component_id !== main.id)
      throw new Error(`Required native component instance missing: ${identity}`);
    if (element.action_id || element.target_screen) {
      const set = find(`component-set:${element.component}`);
      if (set.type !== "COMPONENT_SET" || !(set.children || []).some(child => child.id === main.id))
        throw new Error(`Required native component set missing: ${identity}`);
    }
    instances++;
    const previousBindings = bindings;
    const label = find(identity + "/label");
    const numeric = { radius: ["topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"],
      cornerRadius: ["topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"],
      "border-radius": ["topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"],
      padding: ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft"], "padding-inline":["paddingLeft","paddingRight"], "padding-block":["paddingTop","paddingBottom"], gap: ["itemSpacing"] };
    for (const [prop, path] of Object.entries(PAYLOAD.components[element.component].variants[element.variant])) {
      let aliases = [];
      if (["background", "color", "borderColor", "border-color"].includes(prop)) {
        const target = prop === "color" ? label : node;
        aliases = [(target[["borderColor", "border-color"].includes(prop) ? "strokes" : "fills"] || [])[0]?.boundVariables?.color];
      } else if (numeric[prop]) aliases = numeric[prop].map(field => node.boundVariables?.[field]);
      else if (["fontSize", "font-size", "font-family"].includes(prop)) {
        aliases = [textVariableAlias(label, prop === "font-family" ? "fontFamily" : "fontSize")];
      }
      const expectedFields = PAYLOAD.expected_native_handoff.screens.flatMap(s=>s.controls).find(c=>c.key===identity)?.token_bindings || [];
      if (numeric[prop]) aliases = numeric[prop].filter(field=>expectedFields.some(binding=>binding.property===field && binding.variable===path.replace(/\./g,"/"))).map(field=>node.boundVariables?.[field]);
      for (const alias of aliases) {
        if (!variables.get(path) || alias?.type !== "VARIABLE_ALIAS" || alias.id !== variables.get(path))
          throw new Error(`Required native token binding missing: ${identity} ${prop}; expected ${variables.get(path) || "missing"}; observed ${alias?.id || "unbound"}`);
        bindings++;
      }
    }
    if (bindings === previousBindings && PAYLOAD.foundations) {
      const type = PAYLOAD.foundations.auxiliary_type;
      const alias = textVariableAlias(label, "fontSize");
      if (alias?.id === variables.get(type.token.replace(/\//g,"."))) bindings++;
    }
    if (bindings === previousBindings) throw new Error(`Required native token bindings absent: ${identity}`);
  }
  if (!instances || !bindings) throw new Error("Native handoff requires screen component instances with actual token bindings");
  if (PAYLOAD.foundations) {
    const actual = key => {
      const matches = data.nodes.filter(node => key === node.semanticKey || key === node.key);
      if (matches.length !== 1) throw new Error(`Required native foundation target missing: ${key}`);
      return matches[0];
    };
    for (const role of PAYLOAD.foundations.roles) {
      const variableId = variables.get(role.token.replace(/\//g,"."));
      if (!variableId) throw new Error(`Required native foundation token missing: ${role.token}`);
      for (const binding of role.bindings) {
        const node = actual(binding.key);
        const aliases = ["fills","strokes"].includes(binding.field) ? [node[binding.field]?.[binding.paintIndex || 0]?.boundVariables?.color] : binding.field === "cornerRadius" ? [node.boundVariables?.cornerRadius || node.boundVariables?.topLeftRadius, node.boundVariables?.cornerRadius || node.boundVariables?.topRightRadius, node.boundVariables?.cornerRadius || node.boundVariables?.bottomLeftRadius, node.boundVariables?.cornerRadius || node.boundVariables?.bottomRightRadius] : [node.boundVariables?.[binding.field]];
        if (role.native_type === "STRING" && (binding.field !== "fontFamily" || node.fontName?.family !== role.native_value)) throw new Error(`Required native font family mismatch: ${binding.key}`);
        if (aliases.some(value => Array.isArray(value) ? !value.length || value.some(alias=>alias?.id!==variableId) : value?.id!==variableId)) throw new Error(`Required native foundation binding missing: ${binding.key}.${binding.field}`);
        if (role.styleName) {
          const style = data.styles.filter(style => style.name === role.styleName);
          if (style.length !== 1 || node.textStyleId !== style[0].id) throw new Error(`Required native typography style missing: ${binding.key}`);
          if (style[0].fontSize !== role.native_value || style[0].fontName?.family !== node.fontName?.family || style[0].fontName?.style !== node.fontName?.style || textVariableAlias(style[0], "fontSize")?.id !== variableId) throw new Error(`Required native typography style values differ: ${binding.key}`);
        }
      }
    }
    const paletteItems = [];
    for (const sample of PAYLOAD.foundations.samples) {
      const instance = actual(sample.instanceKey), main = actual(sample.mainComponentKey), set = actual(sample.componentSetKey);
      const label = actual(sample.labelKey), documentation = actual(sample.documentationKey);
      if (instance.type !== "INSTANCE" || instance.mainComponentId !== main.id || main.componentSetId !== set.id || !Object.values(main.variantProperties || {}).includes(sample.variant) || label.characters !== sample.label || [sample.action,sample.state,...sample.useCases].some(value => !documentation.characters?.includes(value))) throw new Error(`Required native palette relationship/documentation missing: ${sample.label}`);
      paletteItems.push(instance);
    }
    const relevant = new Set(PAYLOAD.foundations.samples.map(sample => actual(sample.componentSetKey).id));
    const sets = data.nodes.filter(node => relevant.has(node.id));
    function separate(items) {
      for (let i=0;i<items.length;i++) {
        const a=items[i].absoluteBoundingBox;
        if (!a || a.width<=0 || a.height<=0) throw new Error("Native palette bounds unavailable");
        for (const other of items.slice(i+1)) { const b=other.absoluteBoundingBox; if (b && a.x<b.x+b.width && b.x<a.x+a.width && a.y<b.y+b.height && b.y<a.y+a.height) throw new Error("Native palette samples or component sets overlap"); }
      }
    }
    separate([...paletteItems,...sets]);
    for (const set of sets) separate(data.nodes.filter(node=>node.parentId===set.id));
  }

}

function post(message) {
  figma.ui.postMessage({ ...message, session_nonce: sessionNonce });
}
function status(message, extra = {}) {
  post({ type: "status", message, ...extra });
}
function layout(node, width, padding = 16) {
  // Figma resize fixes both axes, so enable height auto-sizing after the initial size.
  node.fills = [];
  node.resize(width, 60);
  node.layoutMode = "VERTICAL";
  node.primaryAxisSizingMode = "AUTO";
  node.counterAxisSizingMode = "FIXED";
  node.paddingTop = node.paddingBottom = node.paddingLeft = node.paddingRight = padding;
  node.itemSpacing = 12;
}
function text(value, heading = false) {
  const node = figma.createText();
  node.fontName = authoredFont;
  const typeRole = PAYLOAD.foundations?.auxiliary_type;
  node.fontSize = typeRole ? typeRole.native_value : heading ? 24 : 16;
  node.characters = value;
  node.textAutoResize = "HEIGHT";
  node.resize(300, node.height);
  return node;
}
function applyProps(node, label, props, variables, warnings, fonts) {
  const corners = ["topLeftRadius", "topRightRadius", "bottomRightRadius", "bottomLeftRadius"];
  const numeric = { radius: corners, cornerRadius: corners, "border-radius": corners,
    padding: ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft"], "padding-inline":["paddingLeft","paddingRight"], "padding-block":["paddingTop","paddingBottom"], gap: ["itemSpacing"] };
  for (const [prop, path] of Object.entries(props)) {
    const variable = variables.get(path);
    const [kind, value] = PAYLOAD.variable_values[path];
    if (["background", "color", "borderColor", "border-color"].includes(prop) && kind === "COLOR") {
      /** @type {SolidPaint} */
      let paint = { type: "SOLID", color: { r: value.r, g: value.g, b: value.b }, opacity: 1 };
      paint = figma.variables.setBoundVariableForPaint(paint, "color", variable);
      const target = prop === "color" ? label : node;
      target[["borderColor", "border-color"].includes(prop) ? "strokes" : "fills"] = [paint];
    } else if (numeric[prop] && kind === "FLOAT" && value >= 0) {
      for (const field of numeric[prop]) { node[field] = value; node.setBoundVariable(field, variable); }
    } else if (["fontSize", "font-size"].includes(prop) && kind === "FLOAT" && value > 0) {
      label.fontSize = value;
      label.setBoundVariable("fontSize", variable);
    } else if (prop === "font-family" && fonts.has(path)) {
      label.fontName = fonts.get(path);
      label.setBoundVariable("fontFamily", variable);
    } else {
      throw new Error(`Unsupported reviewed native property: ${prop} (${path})`);
    }
  }
}
async function imports() {
  // Root-page plugin data is readable with dynamic-page access without loading every unrelated page.
  return figma.root.children.filter(page => info(page).bridge === 1);
}
async function focus(page) {
  await figma.setCurrentPageAsync(page);
  await page.loadAsync();
  const screens = page.children.filter(node => info(node).kind === "screen");
  page.selection = screens;
  if (screens.length) figma.viewport.scrollAndZoomIntoView(screens);
}
function validateProductionColors(payload) {
  const fail = message => { throw new Error(`Invalid production color contract: ${message}`); };
  const colors = new Map();
  const paths = new Set([...Object.keys(payload.tokens || {}), ...Object.keys(payload.variable_values || {})]);
  const valid = value => value && ["r", "g", "b"].every(channel => Number.isFinite(value[channel]) && value[channel] >= 0 && value[channel] <= 1) && (value.a === undefined || Number.isFinite(value.a) && value.a >= 0 && value.a <= 1);
  const equal = (a, b) => ["r", "g", "b", "a"].every(channel => Math.abs((channel === "a" ? a[channel] ?? 1 : a[channel]) - (channel === "a" ? b[channel] ?? 1 : b[channel])) < 1e-9);
  for (const path of paths) {
    const token = payload.tokens?.[path], compiled = payload.variable_values?.[path];
    if (token?.type !== "color" && compiled?.[0] !== "COLOR") continue;
    if (token?.type !== "color" || compiled?.[0] !== "COLOR" || typeof token.value !== "string" || !/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(token.value)) fail(`malformed token ${path}`);
    const value = compiled[1];
    if (!valid(value)) fail(`malformed COLOR ${path}`);
    const expected = Object.fromEntries(["r", "g", "b", "a"].map((channel, index) => [channel, index === 3 && token.value.length === 7 ? 1 : parseInt(token.value.slice(1 + index * 2, 3 + index * 2), 16) / 255]));
    if (!equal(value, expected)) fail(`compiled value differs from source ${path}`);
    colors.set(path, value);
  }
  for (const [path, value] of colors) {
    let current = path;
    const seen = new Set([path]);
    while (payload.tokens[current].alias) {
      current = payload.tokens[current].alias;
      if (!colors.has(current) || seen.has(current) || !equal(value, colors.get(current))) fail(`invalid color alias ${path}`);
      seen.add(current);
    }
  }
  const roles = payload.foundations?.roles;
  if (!Array.isArray(roles) || !Array.isArray(payload.screens)) fail("missing planned screen colors");
  const planned = roles.filter(role => role.kind === "color");
  if (!planned.length) fail("missing planned screen colors");
  const ink = planned.find(role => /text|ink|foreground/i.test(role.name + role.token)) || planned[0];
  const slots = new Map();
  for (const screen of payload.screens) {
    if (!Array.isArray(screen.elements)) fail("missing authored screen elements");
    for (const [index, element] of screen.elements.entries()) {
      const key = element.id || `${screen.id}/element:${index}`;
      const label = element.kind === "component" ? key + "/label" : key;
      const props = element.kind === "component" ? payload.components?.[element.component]?.variants?.[element.variant] : {};
      if (!props || !["component", "heading", "text"].includes(element.kind)) fail(`missing authored paint consumer ${key}`);
      for (const [prop, path] of Object.entries(props)) {
        if (!["background", "color", "borderColor", "border-color"].includes(prop)) continue;
        if (!colors.has(path)) fail(`invalid authored paint ${key}.${prop}`);
        const target = prop === "color" ? label : key;
        slots.set(target + "\0" + (["borderColor", "border-color"].includes(prop) ? "strokes" : "fills"), path);
      }
      // decorate() uses the planned ink on actual labels without an explicit color.
      if (!Object.prototype.hasOwnProperty.call(props, "color")) slots.set(label + "\0fills", ink.token.replace(/\//g, "."));
    }
  }
  for (const role of planned) {
    if (typeof role.token !== "string") fail("missing planned token name");
    const path = role.token.replace(/\//g, "."), value = colors.get(path);
    if (!value || role.native_type !== "COLOR" || !valid(role.native_value) || !equal(value, role.native_value)) fail(`planned value differs from source ${role.token}`);
    const source = payload.tokens[path];
    if (role.alias && role.alias.replace(/\//g, ".") !== source.alias) fail(`planned alias differs from source ${role.token}`);
    if (!Array.isArray(role.bindings) || !role.bindings.length || role.bindings.some(binding => !["fills", "strokes"].includes(binding.field) || slots.get(binding.key + "\0" + binding.field) !== path)) fail(`no actual authored screen consumer ${role.token}`);
  }
}

async function importDesign(fresh) {
  if (PAYLOAD.technical_existing_only) throw new Error("Existing technical sync cannot author new UI. Select a direction for a production build.");
  if (!PAYLOAD.foundations || !PAYLOAD.selected_direction) throw new Error("Selected canonical design foundations required before native authoring");
  validateProductionColors(PAYLOAD);
  const existing = await imports();
  const matching = existing.filter(page => info(page).source_sha256 === PAYLOAD.source_sha256 && info(page).complete);
  const same = matching.find(page => page.id === figma.currentPage.id) || matching[matching.length - 1];
  if (same && !fresh) {
    await verifyHandoff(same);
    await focus(same);
    status(FLOW_IMPORT_COPY.reused, {event: "reused", page_id:same.id, source_sha256:PAYLOAD.source_sha256});
    return;
  }
  if (existing.length && !fresh) throw new Error("A different or incomplete import exists. Use the explicit fresh-page checkbox to add this reviewed design without changing existing work.");
  await figma.loadFontAsync(font);
  await figma.loadFontAsync(bold);
  const warnings = new Set();
  const fonts = new Map();
  for (const [path, token] of Object.entries(PAYLOAD.tokens)) {
    if (token.type !== "fontFamily") continue;
    const candidate = { family: token.value, style: "Regular" };
    try { await figma.loadFontAsync(candidate); fonts.set(path, candidate); }
    catch (_) { throw new Error(`Declared native font unavailable: ${token.value}`); }
  }
  authoredFont = fonts.values().next().value || font;
  const previousPage = figma.currentPage;
  let page, collection;
  const createdVariables = [];
  const createdStyles = [];
  try {
    page = figma.createPage();
    page.name = `Reviewed design · ${PAYLOAD.source_sha256.slice(0, 8)}`;
    metadata(page, "design-import", { bridge: 1, source_sha256: PAYLOAD.source_sha256, complete: false });
    await figma.setCurrentPageAsync(page);
    collection = figma.variables.createVariableCollection(`${page.name} · ${page.id}`);
    metadata(collection, "token-collection", { bridge: 1, source_sha256: PAYLOAD.source_sha256 });
    const variables = new Map();
    for (const [path, [kind]] of Object.entries(PAYLOAD.variable_values)) {
      const variable = figma.variables.createVariable(path.replace(/\./g, "/"), collection, kind);
      createdVariables.push(variable);
      const token = PAYLOAD.tokens[path];
      metadata(variable, path, { token_type: token.type, source_value: token.value, css_name: token.css_name || null,
        dimension_base_px: token.type === "dimension" ? PX_PER_REM : null, alias: token.alias || null });
      variables.set(path, variable);
    }
    for (const [path, variable] of variables) {
      const alias = PAYLOAD.tokens[path].alias;
      variable.setValueForMode(collection.defaultModeId, alias ? figma.variables.createVariableAlias(variables.get(alias)) : PAYLOAD.variable_values[path][1]);
    }
    collection.setPluginData("bloomSemanticTokens", JSON.stringify({pageId:page.id, sourceHash:PAYLOAD.source_sha256, collectionId:collection.id}));
    const roles = PAYLOAD.foundations.roles;
    const roleOf = kind => roles.find(role => role.kind === kind);
    const space = PAYLOAD.foundations.auxiliary_space, type = PAYLOAD.foundations.auxiliary_type;
    const ink = roles.find(role => role.kind === "color" && /text|ink|foreground/i.test(role.name + role.token)) || roleOf("color");
    const variableOf = role => variables.get(role.token.replace(/\//g, "."));
    const styles = new Map();
    if (typeof figma.createTextStyle !== "function") throw new Error("Native text style author API unavailable");
    const sizeRoles = roles.filter(role => role.kind === "typography" && role.native_type === "FLOAT");
    if (!sizeRoles.some(role=>role.token===type.token)) sizeRoles.push(type);
    for (const role of sizeRoles) {
      const style = figma.createTextStyle(); createdStyles.push(style);
      style.name = role.token; style.fontName = authoredFont; style.fontSize = role.native_value;
      style.setBoundVariable("fontSize", variableOf(role)); styles.set(role.token, style);
    }
    const styledRoles = new Set();
    async function decorate(node) {
      if (node.type === "INSTANCE") return;
      if (node.type === "TEXT") {
        if (!textVariableAlias(node, "fontSize")) { node.fontSize = type.native_value; node.setBoundVariable("fontSize", variableOf(type)); }
        const family = roles.find(role => role.kind === "typography" && role.native_type === "STRING" && role.native_value === node.fontName?.family);
        if (family && !textVariableAlias(node, "fontFamily")) node.setBoundVariable("fontFamily",variableOf(family));
        // Match by the variable the text is actually bound to: two roles may share one size value.
        const role = sizeRoles.find(role => textVariableAlias(node, "fontSize")?.id === variableOf(role)?.id && role.native_value === node.fontSize);
        if (role) {
          const style = styles.get(role.token), actualFont = node.fontName;
          if (!actualFont || typeof actualFont !== "object" || !actualFont.family || !actualFont.style) throw new Error(`Mixed native typography font: ${info(node).semantic_id}`);
          if (styledRoles.has(role.token) && (style.fontName.family !== actualFont.family || style.fontName.style !== actualFont.style)) throw new Error(`Conflicting native fonts for typography role: ${role.token}`);
          if (!styledRoles.has(role.token)) {
            style.fontName = {...actualFont}; style.fontSize = role.native_value;
            style.setBoundVariable("fontSize", variableOf(role));
            if (family) style.setBoundVariable("fontFamily", variableOf(family));
            styledRoles.add(role.token);
          }
          if (typeof node.setTextStyleIdAsync !== "function") throw new Error("Native text style binding API unavailable");
          await node.setTextStyleIdAsync(styles.get(role.token).id);
        }
      }
      if (node.layoutMode === "VERTICAL" || node.layoutMode === "HORIZONTAL") {
        for (const field of ["paddingTop","paddingRight","paddingBottom","paddingLeft","itemSpacing"]) {
          if (typeof node[field] === "number" && node[field] > 0 && !node.boundVariables?.[field]) { node[field] = space.native_value; node.setBoundVariable(field, variableOf(space)); }
        }
      }
      for (const field of ["fills", "strokes"]) if (Array.isArray(node[field])) {
        node[field] = node[field].map(paint => paint.type === "SOLID" && !paint.boundVariables?.color ? figma.variables.setBoundVariableForPaint({...paint,color:{r:ink.native_value.r,g:ink.native_value.g,b:ink.native_value.b},opacity:1}, "color", variableOf(ink)) : paint);
      }
      for (const child of node.children || []) await decorate(child);
    }
    const library = figma.createFrame();
    page.appendChild(library);
    library.name = "Reusable components";
    library.x = -480;
    layout(library, 400);
    metadata(library, "component-library");
    const components = new Map();
    const componentSets = [];
    for (const [name, definition] of Object.entries(PAYLOAD.components)) {
      const variants = [];
      for (const [variant, props] of Object.entries(definition.variants)) {
        const node = figma.createComponent();
        library.appendChild(node);
        node.name = `${name}/${variant}`;
        layout(node, 320);
        const label = text(name);
        node.appendChild(label);
        metadata(node, `component:${name}/${variant}`, { kind: "component", token_properties: props });
        metadata(label, `component:${name}/${variant}/label`);
        applyProps(node, label, props, variables, warnings, fonts);
        await decorate(node);
        components.set(JSON.stringify([name, variant]), node);
        variants.push([variant, node]);
      }
      if (variants.length) {
        if (typeof figma.combineAsVariants === "function") {
          for (const [variant, node] of variants) node.name = `Variant=${variant}`;
          const set = figma.combineAsVariants(variants.map(([, node]) => node), library);
          set.name = name;
          // Figma gives a new variant set a 5px corner radius; leave no unbound rendered radius on the container.
          if ('cornerRadius' in set) set.cornerRadius = 0;
          layout(set, 360);
          componentSets.push(set);
          metadata(set, `component-set:${name}`, { kind: "component-set", variant_property: "Variant" });
        } else warnings.add(`Native variant sets unavailable for ${name}; individual main components are preserved.`);
      }
    }
    layoutFoundationSets(library, componentSets);
    await decorate(library);
    library.x = -library.width - 48;
    const screens = new Map();
    const links = [];
    for (const [index, screen] of PAYLOAD.screens.entries()) {
      const frame = figma.createFrame();
      page.appendChild(frame);
      frame.name = `${screen.id} · ${screen.title}`;
      layout(frame, 390, 24);
      frame.x = index * 470;
      frame.y = 0;
      frame.clipsContent = false;
      metadata(frame, screen.id, { kind: "screen", trace: screen.trace || [], annotation: screen.annotation || "" });
      annotate(frame, PAYLOAD.native_handoff.required_annotations[screen.id]);
      screens.set(screen.id, frame);
      for (const [elementIndex, element] of screen.elements.entries()) {
        let node;
        if (element.kind === "component") {
          node = components.get(JSON.stringify([element.component, element.variant])).createInstance();
          const label = node.findOne(child => child.type === "TEXT");
          if (label) { label.characters = element.text; metadata(label, `${element.id || `${screen.id}/element:${elementIndex}`}/label`); }
        } else node = text(element.text, element.kind === "heading");
        frame.appendChild(node);
        node.name = element.text.slice(0, 80) || element.kind;
        metadata(node, element.id || `${screen.id}/element:${elementIndex}`, { kind: element.kind,
          annotation: element.annotation || "", action_id: element.action_id || null, target_screen: element.target_screen || null });
        annotate(node, PAYLOAD.native_handoff.required_annotations[element.id || `${screen.id}/element:${elementIndex}`] || element.annotation);
        if (element.target_screen) links.push([node, element.target_screen]);
      }
    }
    for (const [node, target] of links) {
      await node.setReactionsAsync([{ trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", destinationId: screens.get(target).id,
        navigation: "NAVIGATE", transition: null, resetScrollPosition: true }] }]);
    }
    for (const frame of screens.values()) await decorate(frame);
    const tokenDefinitions = Object.entries(PAYLOAD.tokens).map(([path, token]) => ({name:path.replace(/\./g,"/"), type:PAYLOAD.variable_values[path][0], ...(token.alias ? {alias:token.alias.replace(/\./g,"/")} : {value:PAYLOAD.variable_values[path][1]})}));
    const palette = await createFoundationPalette(figma, page, {sourceHash:PAYLOAD.source_sha256,
      name:"Component palette · selected direction", font:authoredFont, x:library.x - library.width - 640, y:0,
      collectionName:collection.name, tokens:tokenDefinitions,
      type:{token:type.token,value:type.native_value}, space:{token:space.token,value:space.native_value},
      ink:{token:ink.token,value:ink.native_value},
      samples:PAYLOAD.foundations.samples.map(sample => ({...sample, mainComponentId:components.get(JSON.stringify([sample.component,sample.variant])).id}))}, (api,target,contract)=>ensureSemanticTokens(api,target,{...contract,strictValues:true}));
    const paletteNode = await figma.getNodeByIdAsync(palette.libraryId);
    metadata(paletteNode,"foundation-palette");
    for (const sample of palette.samples) {
      const key = sample.instanceKey;
      metadata(await figma.getNodeByIdAsync(sample.instanceId),key);
      metadata(await figma.getNodeByIdAsync(sample.labelNodeId),sample.labelKey);
      metadata(await figma.getNodeByIdAsync(sample.documentationNodeId),sample.documentationKey);
    }
    // Every declared role has a visible, bound specimen, including numeric roles.
    for (const role of roles) {
      const specimen = role.kind === "typography" ? text(role.name) : figma.createFrame();
      paletteNode.appendChild(specimen);
      if (role.kind !== "typography") {
        layout(specimen,320); specimen.fills=[];
        const label=text(`${role.name}: ${role.token} · ${JSON.stringify(role.native_value)}`);
        if (role.kind === "color") paletteNode.appendChild(label); else specimen.appendChild(label);
      }
      metadata(specimen,"foundation-role:" + role.name);
      const field=role.kind === "typography" && role.native_type === "STRING" ? "fontFamily" : {color:"fills", typography:"fontSize", spacing:"paddingTop", radius:"cornerRadius"}[role.kind];
      if (field === "fills") specimen.fills=[figma.variables.setBoundVariableForPaint({type:"SOLID",color:{r:role.native_value.r,g:role.native_value.g,b:role.native_value.b},opacity:1},"color",variableOf(role))];
      else { if(field === "fontFamily") specimen.fontName={family:role.native_value,style:"Regular"}; else specimen[field]=role.native_value; specimen.setBoundVariable(field,variableOf(role)); }
      await decorate(specimen);
    }
    await decorate(paletteNode);
    paletteNode.x = library.x - paletteNode.width - 48;
    const noteTargets = [page,...page.findAll(()=>true)];
    const boardContract = PAYLOAD.expected_native_handoff.design_note_board;
    if (!boardContract?.required) throw new Error("Required Design-mode note board declaration missing");
    const designBoard = await ensureDesignNoteBoard(figma,page,{sourceHash:PAYLOAD.source_sha256,font:authoredFont,fontSize:type.native_value,
      ...(PAYLOAD.specifications?{presentation:'readable-specs'}:{}),boardKey:boardContract.key,styleText:decorate,notes:boardContract.entries.map(entry=>{
        const matches=noteTargets.filter(node=>info(node).semantic_id===entry.target_key);
        if(matches.length!==1) throw new Error(`Missing actual annotation target: ${entry.target_key}`);
        return {key:entry.key,targetId:matches[0].id,...(entry.specification?{specification:entry.specification}:{label:entry.label})};
      })});
    if (PAYLOAD.specifications) {
      const notes = Object.entries(PAYLOAD.specifications).map(([key,specification])=>{
        const matches=noteTargets.filter(node=>info(node).semantic_id===key);
        if(matches.length!==1) throw new Error(`Missing canonical specification target: ${key}`);
        const entry=designBoard.entries.find(entry=>entry.targetId===matches[0].id);
        if(!entry) throw new Error(`Missing readable specification link: ${key}`);
        return {key,label:PAYLOAD.native_handoff.required_annotations[key],specification,
                board:{boardId:designBoard.boardId,textNodeId:entry.textNodeId,key:entry.key}};
      });
      await ensureNativeAnnotations(figma,page,{presentation:'readable-specs',sourceHash:PAYLOAD.source_sha256,annotations:notes});
    }
    const designBoardNode = await figma.getNodeByIdAsync(designBoard.boardId);
    designBoardNode.fills = [];
    for (const field of ["paddingTop","paddingRight","paddingBottom","paddingLeft","itemSpacing"]) {
      designBoardNode[field] = space.native_value;
      designBoardNode.setBoundVariable(field,variableOf(space));
    }
    metadata(page, "design-import", { bridge: 1, source_sha256: PAYLOAD.source_sha256, complete: false, collection_id: collection.id });
    await verifyHandoff(page);
    metadata(page, "design-import", { bridge: 1, source_sha256: PAYLOAD.source_sha256, complete: true,
      collection_id: collection.id, warnings: [...warnings], annotation_policy: "required native annotations, component instances and variable bindings verified" });
    await focus(page);
    status(`화면 ${screens.size}개, 컴포넌트 ${components.size}개, 변수 ${variables.size}개를 가져왔습니다.`, { event: "imported", page_id:page.id, source_sha256:PAYLOAD.source_sha256, counts: {screens: screens.size, components: components.size, variables: variables.size}, warnings: [...warnings] });
  } catch (error) {
    // Only objects created by this attempt are removed; existing imports and user edits are never touched.
    await figma.setCurrentPageAsync(previousPage);
    if (page && !page.removed) page.remove();
    for (const style of createdStyles) if (!style.removed) style.remove();
    for (const variable of createdVariables) if (!variable.removed) variable.remove();
    if (collection && !collection.removed) collection.remove();
    throw error;
  }
}
async function snapshot(node) {
  const declared = info(node);
  const data = { id: node.id, type: node.type, name: node.name, semantic_id: declared.semantic_id || node.getPluginData("semanticKey") || null,
    source_sha256: declared.source_sha256 || null, declared_metadata: declared };
  const fields = ["x", "y", "width", "height", "visible", "opacity", "layoutMode", "primaryAxisSizingMode", "counterAxisSizingMode", "layoutSizingHorizontal", "layoutSizingVertical", "layoutWrap", "minWidth", "maxWidth", "minHeight", "maxHeight", "absoluteBoundingBox", "clipsContent", "textAutoResize", "itemSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "cornerRadius", "topLeftRadius", "topRightRadius", "bottomRightRadius", "bottomLeftRadius", "characters", "fontName", "fontSize", "fills", "strokes", "boundVariables", "reactions", "componentProperties", "variantProperties"];
  for (const field of fields) {
    try {
      const value = node[field];
      if (value !== undefined && typeof value !== "symbol") data[field] = value;
    } catch (error) {
      (data.unavailable_fields ||= {})[field] = error.message || String(error);
    }
  }
  if (node.type === "TEXT") {
    try {
      if (typeof node.getRangeHyperlink !== "function") throw new Error("Native hyperlink read API unavailable");
      data.hyperlink = node.characters.length ? node.getRangeHyperlink(0,node.characters.length) : null;
    } catch(error) { (data.unavailable_fields ||= {}).hyperlink = error.message || String(error); }
  }
  if ("annotations" in node) {
    try { data.annotations = node.annotations; data.annotations_status = "observed"; }
    catch (error) {
      data.annotations_status = "unavailable";
      (data.unavailable_fields ||= {}).annotations = error.message || String(error);
    }
  }
  const specification = node.getPluginData('figmaFlowSpecification');
  if (specification) {
    try { data.specification=JSON.parse(specification);data.specification_status='observed'; }
    catch(error){data.specification_status='invalid';(data.unavailable_fields ||= {}).specification=error.message || String(error);}
  }
  const boardOwner = node.getPluginData('designNoteBoard');
  if(boardOwner){try{data.designNoteBoard=JSON.parse(boardOwner);}catch(error){(data.unavailable_fields ||= {}).designNoteBoard=error.message || String(error);}}
  if (node.type === "INSTANCE") {
    try {
      const component = await node.getMainComponentAsync();
      data.main_component_id = component ? component.id : null;
    } catch (error) {
      (data.unavailable_fields ||= {}).main_component_id = error.message || String(error);
    }
  }
  if ("children" in node) {
    data.children = [];
    for (const child of node.children) data.children.push(await snapshot(child));
  }
  return data;
}
async function readback(pages, scope) {
  const snapshots = [];
  const nativeReads = [];
  const rasterImages = Object.create(null);
  const collectionIds = new Set(pages.map(page => info(page).collection_id).filter(Boolean));
  for (const page of pages) {
    await page.loadAsync();
    snapshots.push(await snapshot(page));
    const read = await readNativeSemantics(figma,page);
    nativeReads.push(read);
    for (const [hash, bytes] of Object.entries(read.rasterImages || {})) {
      if (Object.prototype.hasOwnProperty.call(rasterImages, hash) && rasterImages[hash] !== bytes) throw new Error(`Conflicting native raster bytes for image hash ${hash}`);
      rasterImages[hash] = bytes;
    }
  }
  const collections = (await figma.variables.getLocalVariableCollectionsAsync()).filter(collection => collectionIds.has(collection.id));
  const variables = (await figma.variables.getLocalVariablesAsync()).filter(variable => collectionIds.has(variable.variableCollectionId));
  return { format: "figma-flow-readback-v1", evidence: "observed-plugin-api-readback", scope,
    fileKey: figma.fileKey || null, exported_at: new Date().toISOString(), pages: snapshots,
    expected_native_handoff: PAYLOAD.expected_native_handoff,
    nodes:nativeReads.flatMap(read => read.nodes), styles:nativeReads.flatMap(read => read.styles), unavailableFields:nativeReads.flatMap(read => read.unavailableFields), rasterImages,
    collections: collections.map(collection => ({ id: collection.id, name: collection.name, modes: collection.modes, defaultModeId: collection.defaultModeId, ...info(collection) })),
    variables: variables.map(variable => ({ id: variable.id, name: variable.name, resolvedType: variable.resolvedType,
      variableCollectionId: variable.variableCollectionId, valuesByMode: variable.valuesByMode, ...info(variable) })) };
}
async function exportReadback() {
  const pages = [figma.currentPage];
  if (!PAYLOAD.technical_existing_only && !info(figma.currentPage).complete) throw new Error("Open the generated page to export its actual native evidence");
  if (PAYLOAD.technical_existing_only && (figma.fileKey !== LOCAL_SYNC.file_key || figma.currentPage.id !== LOCAL_SYNC.page_id)) throw new Error("Existing technical export requires paired native file/page");
  const output = await readback(pages, "active-generated-import-page");
  post({ type: "readback", data: output });
  status(`페이지 ${output.pages.length}개 · 변수 ${output.variables.length}개`, {event: "read", counts: {pages: output.pages.length, variables: output.variables.length}});
}
async function syncToApp() {
  if (typeof LOCAL_SYNC === "undefined") throw new Error("This build is not paired with a local app.");
  if (!LOCAL_SYNC.file_key || figma.fileKey !== LOCAL_SYNC.file_key) throw new Error("페어링된 Figma 파일에서 다시 시도하세요.");
  const page = figma.currentPage;
  const declared = info(page);
  if (page.id !== LOCAL_SYNC.page_id) throw new Error("페어링된 페이지를 열고 다시 시도하세요.");
  if (declared.bridge !== 1 || declared.complete !== true || declared.source_sha256 !== PAYLOAD.source_sha256 || !declared.collection_id)
    throw new Error("현재 페이지의 가져오기 지문이 일치하지 않습니다.");
  if (figma.root.children.some(other => other.id !== page.id && info(other).collection_id === declared.collection_id))
    throw new Error("다른 페이지와 공유하는 변수 컬렉션은 반영할 수 없습니다.");
  const collections = await figma.variables.getLocalVariableCollectionsAsync();
  const owned = collections.find(collection => collection.id === declared.collection_id);
  if (!owned || info(owned).bridge !== 1 || info(owned).source_sha256 !== PAYLOAD.source_sha256)
    throw new Error("페이지가 소유한 변수 컬렉션을 확인할 수 없습니다.");
  const data = await readback([page], "paired-active-import-page");
  status(FLOW_IMPORT_COPY.syncWait, {event: "sync-wait"});
  const response = await fetch(LOCAL_SYNC.url, { method: "POST", headers: {
    Authorization: `Bearer ${LOCAL_SYNC.token}`, "Content-Type": "application/json"
  }, body: JSON.stringify({ file_key: LOCAL_SYNC.file_key, page_id: LOCAL_SYNC.page_id, readback: data }) });
  const result = await response.json();
  if (!response.ok || result.error) throw new Error(result.error || `HTTP ${response.status}`);
  if (!["baseline", "applied", "unchanged"].includes(result.status)) throw new Error("앱에서 올바른 반영 결과를 받지 못했습니다.");
  post({ type: "sync-result", result });
  if (!result.preview_error && result.preview_url === LOCAL_SYNC.preview_url && /^http:\/\/localhost:\d+\/$/.test(LOCAL_SYNC.preview_url)) {
    post({ type: "preview", url: LOCAL_SYNC.preview_url });
    if (typeof figma.ui.resize === "function") figma.ui.resize(820, 720);
  }
}
figma.ui.onmessage = async message => {
  if (!message || !/^[a-f0-9]{32}$/.test(message.session_nonce)) return;
  if (message.type === "ready") {
    if (sessionNonce && message.session_nonce !== sessionNonce) return;
    sessionNonce = message.session_nonce;
    const paired = typeof LOCAL_SYNC !== "undefined";
    const targetPage = paired ? figma.root.children.find(page => page.id === LOCAL_SYNC.page_id) : figma.currentPage;
    const titles = PAYLOAD.screens.slice(0, 2).map(screen => screen.title || screen.id);
    const sourceLabel = titles.length ? titles.join(" · ") + (PAYLOAD.screens.length > 2 ? ` 외 ${PAYLOAD.screens.length - 2}개 화면` : "") : `화면 ${PAYLOAD.screens.length}개`;
    status(`화면 ${PAYLOAD.screens.length}개`, { ready: true, paired, existing_only: PAYLOAD.technical_existing_only === true, source_label: sourceLabel, source_names: titles, source_count: PAYLOAD.screens.length, event: "ready", target_page_name: targetPage?.name || null });
    post({ type: "busy", value: busy });
    return;
  }
  if (!sessionNonce || message.session_nonce !== sessionNonce || !["import", "export", "sync"].includes(message.type) || busy) return;
  busy = true;
  post({ type: "busy", value: true, operation: message.type });
  try {
    if (message.type === "import") await importDesign(message.fresh === true);
    else if (message.type === "export") await exportReadback();
    else await syncToApp();
  } catch (error) { status(`Error: ${error.message || String(error)}`, {event: "error", operation: message.type, details: String(error.message || error) + (error.stack ? "\n" + error.stack : "")}); }
  finally { busy = false; post({ type: "busy", value: false }); }
};
figma.showUI(__html__, { width: 480, height: 720, themeColors: true });
