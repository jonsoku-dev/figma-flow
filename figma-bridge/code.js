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
async function verifyHandoff(page, {preserveInstanceOverrides = false} = {}) {
  const data = await readback([page], "native-handoff-verification");
  if (!data.fileKey) throw new Error("Actual native Figma file key unavailable for handoff");
  const nodes = [];
  function visit(node) { nodes.push(node); for (const child of node.children || []) visit(child); }
  visit(data.pages[0]);
  verifyDeclaredComponentReadback(PAYLOAD, data.pages[0], {preserveInstanceOverrides});
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

function componentVariantGroups(definition) {
  const entries = Object.entries(definition.variants || {});
  const axes = definition.variant_axes;
  if (!axes) return [{axis: "Variant", variants: entries}];
  const groups = new Map();
  for (const entry of entries) {
    const hits = Object.entries(axes).filter(([, values]) => Array.isArray(values) && values.includes(entry[0]));
    if (hits.length > 1) throw new Error(`Declared variant axis must be unique: ${entry[0]}`);
    const axis = hits.length ? hits[0][0] : 'Variant';
    if (!hits.length && Object.prototype.hasOwnProperty.call(axes, axis)) throw new Error(`Unassigned definition conflicts with declared ${axis} axis: ${entry[0]}`);
    if (!groups.has(axis)) groups.set(axis, []);
    groups.get(axis).push(entry);
  }
  return [...groups.entries()].map(([axis, variants]) => ({axis, variants}));
}
function componentUsageText(definition) {
  if (!Object.prototype.hasOwnProperty.call(definition, "usage")) return undefined;
  if (typeof definition.usage !== "string" || !definition.usage.trim()) throw new Error("Usage description must be the source text");
  return definition.usage;
}
function componentSwapTargets(definition) {
  if (!Object.prototype.hasOwnProperty.call(definition, "swap_targets")) return undefined;
  if (!Array.isArray(definition.swap_targets) || !definition.swap_targets.length || definition.swap_targets.some(item => typeof item !== "string" || !item.trim())) throw new Error("Swap targets must be declared");
  return [...new Set(definition.swap_targets)];
}
function componentLayoutMode(definition) {
  if (!Object.prototype.hasOwnProperty.call(definition, "layout")) return "VERTICAL";
  if (!["VERTICAL", "HORIZONTAL"].includes(definition.layout)) throw new Error(`Invalid component layout mode: ${definition.layout}`);
  return definition.layout;
}
function bindOwnedLabelProperty(owner, mains, warnings) {
  const labels = mains.map(main => {
    const label = (main.children || []).find(child => child.type === "TEXT");
    if (!label) throw new Error(`Component variant has no label: ${main.name}`);
    return label;
  });
  if (typeof owner.addComponentProperty !== "function") {
    warnings.add(`Native text properties unavailable for ${owner.name}; direct label text is preserved.`);
    return null;
  }
  const referenced = [...new Set(labels.map(label => label.componentPropertyReferences?.characters).filter(Boolean))];
  if (referenced.length > 1) throw new Error(`Label property conflict on ${owner.name}: ${referenced.join(", ")}`);
  let key = referenced[0];
  if (key) {
    if (owner.componentPropertyDefinitions?.[key]?.type !== "TEXT") throw new Error(`Existing label reference is not a TEXT property on ${owner.name}: ${key}`);
  } else {
    const displayName = "문구";
    key = owner.addComponentProperty(displayName, "TEXT", labels[0].characters);
    if (typeof key !== "string" || !key || key === displayName || owner.componentPropertyDefinitions?.[key]?.type !== "TEXT") throw new Error(`Native text property key missing for ${owner.name}`);
  }
  for (const label of labels) {
    if (label.componentPropertyReferences?.characters === key) continue;
    if (label.componentPropertyReferences?.characters) throw new Error(`Label property conflict on ${owner.name}: ${label.componentPropertyReferences.characters}`);
    try {
      label.componentPropertyReferences = {...(label.componentPropertyReferences || {}), characters: key};
    } catch (error) {
      throw new Error(`Cannot link owned label on ${owner.name}: ${error.message || error}`);
    }
    if (label.componentPropertyReferences?.characters !== key) throw new Error(`Label reference was not retained on ${owner.name}`);
  }
  for (const node of [owner, ...mains]) node.setPluginData(KEY, JSON.stringify({...info(node), label_property_key: key}));
  return key;
}

function validateDeclaredComponentProperties(payload) {
  const fail = message => { throw new Error("Declared component properties: " + message); };
  const secretPattern = /(?:sk-[A-Za-z0-9_-]{12,}|figd_[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{12,}|\/Users\/[^\s/]+|(?:api[_-]?key|secret|password|passwd|access[_-]?token)\s*[:=]\s*\S+)/i;
  const checkText = (value, label) => {
    if (typeof value !== "string") fail(label + " must be string");
    if (secretPattern.test(value)) fail("secret or private path forbidden in " + label);
  };
  const familySpecs = {
    field: { requiredLayout: null, states: ["default", "error", "disabled", "focus"] },
    input: { requiredLayout: null, states: ["default", "focus", "error", "disabled"] },
    checkbox: { requiredLayout: null, states: ["unchecked", "checked", "disabled", "focus", "error"] },
    radio: { requiredLayout: null, states: ["unselected", "selected", "disabled", "focus", "error"] },
    "table-row": { requiredLayout: "HORIZONTAL", states: ["default", "selected", "disabled", "hover"] },
    "table-cell": { requiredLayout: null, states: ["default", "header", "selected", "muted"] },
  };
  const components = /** @type {Record<string, any>} */ (payload.components);
  const rawFamilies = /** @type {any} */ (payload).componentFamilies;
  if (rawFamilies !== undefined) {
    if (!Array.isArray(rawFamilies) || !rawFamilies.length || rawFamilies.length > 32) fail("componentFamilies must be a bounded nonempty list");
    const seenFamilies = new Set();
    for (const fam of rawFamilies) {
      if (!fam || typeof fam !== "object" || typeof fam.id !== "string" || !Object.prototype.hasOwnProperty.call(familySpecs, fam.id) || fam.version !== 1) fail("unsupported or unversioned component family");
      if (seenFamilies.has(fam.id)) fail("duplicate component family " + fam.id);
      seenFamilies.add(fam.id);
      const spec = familySpecs[/** @type {keyof typeof familySpecs} */ (fam.id)];
      if (spec.requiredLayout && fam.layout && fam.layout !== spec.requiredLayout) fail("invalid layout for family " + fam.id);
    }
  }
  const dependencies = new Map(Object.keys(components).map(name => [name, new Set()]));
  const reference = value => {
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).sort().join(",") !== "component,variant" || typeof value.component !== "string" || typeof value.variant !== "string" || !Object.prototype.hasOwnProperty.call(components[value.component]?.variants || {}, value.variant)) fail("swap requires an existing local component variant");
    return value.component;
  };
  const allowedSwapSetFor = (definition, prop) => {
    let compAllowed = null;
    if (Object.prototype.hasOwnProperty.call(definition, "swap_targets")) {
      if (!Array.isArray(definition.swap_targets) || !definition.swap_targets.length || definition.swap_targets.some((/** @type {any} */ item) => typeof item !== "string" || !Object.prototype.hasOwnProperty.call(components, item))) fail("swap_targets must reference local components");
      compAllowed = new Set(definition.swap_targets);
    }
    let propAllowed = null;
    if (prop.allowed_components !== undefined) {
      if (!Array.isArray(prop.allowed_components) || !prop.allowed_components.length || prop.allowed_components.some((/** @type {any} */ item) => typeof item !== "string" || !Object.prototype.hasOwnProperty.call(components, item))) fail("allowed_components must reference local components");
      propAllowed = new Set(prop.allowed_components);
    }
    if (compAllowed && propAllowed) {
      const intersection = new Set([...propAllowed].filter(item => compAllowed.has(item)));
      if (!intersection.size) fail("allowed_components conflicts with component swap_targets");
      return intersection;
    }
    return propAllowed || compAllowed;
  };
  for (const [name, definition] of Object.entries(components)) {
    if (Object.prototype.hasOwnProperty.call(definition, "family")) {
      if (typeof definition.family !== "string" || !Object.prototype.hasOwnProperty.call(familySpecs, definition.family)) fail("unsupported component family " + definition.family);
      const spec = familySpecs[/** @type {keyof typeof familySpecs} */ (definition.family)];
      if (spec.requiredLayout && (definition.layout || "VERTICAL") !== spec.requiredLayout) fail("invalid layout for family " + definition.family);
      const stateValues = definition.variant_axes?.state;
      if (Array.isArray(stateValues) && stateValues.some((/** @type {any} */ st) => !spec.states.includes(st))) fail("undeclared state value on " + name);
    }
    if (Object.prototype.hasOwnProperty.call(definition, "swap_targets")) {
      if (!Array.isArray(definition.swap_targets) || !definition.swap_targets.length || definition.swap_targets.some((/** @type {any} */ item) => typeof item !== "string" || !Object.prototype.hasOwnProperty.call(components, item))) fail("swap_targets must reference local components");
    }
    const properties = Object.prototype.hasOwnProperty.call(definition, "properties") ? definition.properties : {};
    if (!properties || typeof properties !== "object" || Array.isArray(properties) || Object.keys(properties).length > 32) fail("properties must be a bounded mapping");
    const swaps = new Set(), textTargets = new Set(), targets = new Set();
    const axes = new Set(["Variant", ...Object.keys(definition.variant_axes || {})]);
    for (const [propId, prop] of Object.entries(/** @type {Record<string, any>} */ (properties))) {
      const display = prop?.name === undefined ? propId : prop.name;
      if (!propId.trim() || propId.includes("#") || propId === "문구" || axes.has(propId) || typeof display !== "string" || !display.trim() || display.includes("#") || display === "문구" || axes.has(display)) fail("property display name conflicts with an owned native property");
      const allowedKeys = prop?.type === "INSTANCE_SWAP" ? ["type", "target", "default_value", "name", "preferred_values", "allowed_components"] : ["type", "target", "default_value", "name"];
      if (!prop || !["TEXT", "BOOLEAN", "INSTANCE_SWAP"].includes(prop.type) || typeof prop.target !== "string" || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(prop.target) || !Object.prototype.hasOwnProperty.call(prop, "default_value") || Object.keys(prop).some(key => !allowedKeys.includes(key))) fail("invalid declaration " + propId);
      const target = prop.type + ":" + prop.target;
      if (targets.has(target)) fail("duplicate target field " + prop.target);
      targets.add(target);
      if (prop.type === "TEXT") {
        checkText(prop.default_value, name + "." + propId);
        if (prop.target !== "label") textTargets.add(prop.target);
      } else if (prop.type === "BOOLEAN") {
        if (typeof prop.default_value !== "boolean") fail("BOOLEAN default must be boolean");
      } else {
        if (prop.target === "label") fail("swap target must be a named slot");
        swaps.add(prop.target);
        const allowedSwapSet = allowedSwapSetFor(definition, prop);
        if (definition.family === "table-row" && allowedSwapSet && [...allowedSwapSet].some(tc => components[tc]?.family && components[tc].family !== "table-cell")) fail("table-row swap targets must belong to table-cell");
        const defaultComp = reference(prop.default_value);
        if (allowedSwapSet && !allowedSwapSet.has(defaultComp)) fail("swap default outside allowed swap_targets: " + defaultComp);
        dependencies.get(name).add(defaultComp);
        if (prop.preferred_values !== undefined && (!Array.isArray(prop.preferred_values) || prop.preferred_values.length > 100)) fail("invalid preferred_values");
        for (const preferred of prop.preferred_values || []) {
          const prefComp = reference(preferred);
          if (allowedSwapSet && !allowedSwapSet.has(prefComp)) fail("preferred_values outside allowed swap_targets: " + prefComp);
          dependencies.get(name).add(prefComp);
        }
      }
    }
    for (const slotName of swaps) if (textTargets.has(slotName)) fail("slot and text target collision " + slotName);
    for (const prop of Object.values(/** @type {Record<string, any>} */ (properties))) {
      if (prop.type === "BOOLEAN" && prop.target !== "label" && !swaps.has(prop.target) && !textTargets.has(prop.target) && !(definition.family === "field" && prop.target === "field-help")) {
        fail("BOOLEAN target must be label or declared slot");
      }
    }
  }
  for (const screen of payload.screens) for (const element of /** @type {any[]} */ (screen.elements)) {
    if (!Object.prototype.hasOwnProperty.call(element, "property_values")) continue;
    const overrides = element.property_values;
    if (element.kind !== "component" || !overrides || typeof overrides !== "object" || Array.isArray(overrides)) fail("invalid instance property_values");
    const compDef = components[element.component];
    for (const [name, value] of Object.entries(overrides)) {
      const prop = compDef?.properties?.[name];
      if (!prop) fail("unknown instance property " + name);
      if (prop.type === "TEXT") {
        checkText(value, element.component + "." + name);
      } else if (prop.type === "BOOLEAN") {
        if (typeof value !== "boolean") fail("BOOLEAN override must be boolean");
      } else {
        const swapComp = reference(value);
        const allowedSwapSet = allowedSwapSetFor(compDef, prop);
        if (allowedSwapSet && !allowedSwapSet.has(swapComp)) fail("instance swap outside allowed swap_targets: " + swapComp);
        dependencies.get(element.component).add(swapComp);
      }
    }
  }
  const visiting = new Set(), done = new Set();
  function visit(name) {
    if (visiting.has(name)) fail("recursive swap dependencies are unsupported");
    if (done.has(name)) return;
    visiting.add(name);
    for (const dependency of dependencies.get(name)) visit(dependency);
    visiting.delete(name); done.add(name);
  }
  for (const name of dependencies.keys()) visit(name);
}

function verifyDeclaredComponentReadback(payload, page, {preserveInstanceOverrides = false} = {}) {
  const nodes = [], parents = new Map();
  function visit(node, parent) {nodes.push(node); parents.set(node.id,parent); for (const child of node.children || []) visit(child,node);}
  visit(page,null);
  const find = identity => {
    const matches = nodes.filter(node => node.semantic_id === identity);
    if (matches.length !== 1) throw new Error("Declared property node missing or ambiguous: " + identity);
    return matches[0];
  };
  const fail = message => {throw new Error("Declared component property readback differs: " + message);};
  const resolve = ref => find(`component:${ref.component}/${ref.variant}`);
  const targetSuffix = (definition, prop) => {
    if (prop.target === "label") return "/label";
    if (prop.type === "TEXT") return "/text:" + prop.target;
    if (prop.type === "INSTANCE_SWAP") return "/slot:" + prop.target;
    const swapNames = new Set(Object.values(definition.properties || {}).filter(item => item.type === "INSTANCE_SWAP").map(item => item.target));
    return (swapNames.has(prop.target) ? "/slot:" : "/text:") + prop.target;
  };
  const target = (node, definition, prop, identity) => {
    const key = identity + targetSuffix(definition, prop);
    const child = find(key);
    if (!(node.children || []).some(item => item.id === child.id)) fail("target is not a direct owned child: " + key);
    return child;
  };
  for (const [name, definition] of Object.entries(payload.components)) {
    const properties = definition.properties || {};
    if (!Object.keys(properties).length) continue;
    const displayCounts = new Map();
    for (const [propId, prop] of Object.entries(properties)) {
      const display = prop.name === undefined ? propId : prop.name;
      displayCounts.set(display, (displayCounts.get(display) || 0) + 1);
    }
    for (const variant of Object.keys(definition.variants)) {
      const identity = `component:${name}/${variant}`, main = find(identity);
      const parent = parents.get(main.id), owner = parent?.type === "COMPONENT_SET" ? parent : main;
      if (main.type !== "COMPONENT") fail(identity + " is not a main component");
      const declaredKeys = main.declared_metadata?.declared_property_keys || {};
      const allKeyVals = Object.values(declaredKeys);
      const distinctKeys = new Set(allKeyVals).size === allKeyVals.length;
      for (const [propId, prop] of Object.entries(properties)) {
        const display = prop.name === undefined ? propId : prop.name;
        const key = declaredKeys[propId];
        const matching = Object.keys(owner.componentPropertyDefinitions || {}).filter(candidate => candidate.startsWith(display + "#"));
        const actual = owner.componentPropertyDefinitions?.[key];
        if (!key || !distinctKeys || !matching.includes(key) || matching.length !== displayCounts.get(display) || actual?.type !== prop.type) fail(identity + "." + propId + " definition/key");
        const value = prop.type === "INSTANCE_SWAP" ? resolve(prop.default_value).id : prop.default_value;
        if (actual.defaultValue !== value) fail(identity + "." + propId + " default");
        if (prop.type === "INSTANCE_SWAP") {
          const preferred = (prop.preferred_values || []).map(ref => {
            const component = resolve(ref);
            if (!component.component_key) fail("swap target component key unavailable");
            return {type:"COMPONENT",key:component.component_key};
          });
          if (JSON.stringify(actual.preferredValues || []) !== JSON.stringify(preferred)) fail(identity + "." + propId + " preferred values");
        }
        const child = target(main,definition,prop,identity);
        const field = prop.type === "TEXT" ? "characters" : (prop.type === "BOOLEAN" ? "visible" : "mainComponent");
        if (child.componentPropertyReferences?.[field] !== key) fail(identity + "." + propId + " layer reference");
        if (prop.type === "TEXT" ? (child.type !== "TEXT" || child.characters !== value) : (prop.type === "BOOLEAN" ? child.visible !== value : (child.type !== "INSTANCE" || child.main_component_id !== value))) fail(identity + "." + propId + " actual target");
      }
    }
  }
  for (const screen of payload.screens) for (const [index, element] of screen.elements.entries()) {
    const definition = payload.components[element.component];
    const properties = definition?.properties || {};
    if (element.kind !== "component" || !Object.keys(properties).length) continue;
    const identity = element.id || `${screen.id}/element:${index}`, instance = find(identity), main = resolve({component:element.component,variant:element.variant});
    if (instance.type !== "INSTANCE" || instance.main_component_id !== main.id) fail(identity + " instance/main");
    for (const [propId, prop] of Object.entries(properties)) {
      const key = main.declared_metadata?.declared_property_keys?.[propId], actual = instance.componentProperties?.[key];
      if (actual?.type !== prop.type) fail(identity + "." + propId + " instance property");
      const hasOverride = Object.prototype.hasOwnProperty.call(element.property_values || {}, propId);
      const requested = hasOverride ? element.property_values[propId] : (prop.type === "TEXT" && prop.target === "label" && typeof element.text === "string" ? element.text : prop.default_value);
      const expected = prop.type === "INSTANCE_SWAP" ? resolve(requested).id : requested;
      if (!preserveInstanceOverrides && actual.value !== expected) fail(identity + "." + propId + " source override");
      const child = target(instance,definition,prop,identity);
      if (prop.type === "TEXT") {
        if (typeof actual.value !== "string" || child.type !== "TEXT" || child.characters !== actual.value) fail(identity + "." + propId + " actual text");
      } else if (prop.type === "BOOLEAN") {
        if (typeof actual.value !== "boolean" || child.visible !== actual.value) fail(identity + "." + propId + " actual visibility");
      } else {
        const swappedMain = nodes.find(node => node.type === "COMPONENT" && node.id === actual.value);
        const allowedList = prop.allowed_components || definition.swap_targets || null;
        const swappedCompName = swappedMain?.semantic_id?.startsWith("component:") ? swappedMain.semantic_id.slice(10).split("/")[0] : null;
        if (typeof actual.value !== "string" || !swappedMain || (allowedList && (!swappedCompName || !allowedList.includes(swappedCompName))) || child.type !== "INSTANCE" || child.main_component_id !== actual.value) fail(identity + "." + propId + " actual swap");
      }
    }
  }
}

function markComponentSlot(node, semanticId, slot) {
  metadata(node, semanticId, {kind:"component-slot", slot});
  for (const [index, child] of (node.children || []).entries()) markComponentSlot(child, semanticId + "/child:" + index, slot);
}

function markImportedInstanceSlots(instance, identity) {
  for (const child of instance.children || []) {
    if (child.name?.startsWith("slot:")) markComponentSlot(child, identity + "/" + child.name, child.name.slice(5));
    else if (child.name?.startsWith("text:")) metadata(child, identity + "/" + child.name, {kind:"component-text-slot", target:child.name.slice(5)});
  }
}

function bindDeclaredComponentProperties(components, definitions) {
  const done = new Set();
  const resolve = ref => components.get(JSON.stringify([ref.component, ref.variant]));
  const createOwnedTextNode = value => {
    const helper = /** @type {any} */ (globalThis).text;
    if (typeof helper === "function") return helper(value);
    const node = figma.createText();
    node.characters = value;
    return node;
  };
  function bind(name) {
    if (done.has(name)) return;
    const definition = /** @type {any} */ (definitions[name]);
    const properties = /** @type {Record<string, any>} */ (definition.properties || {});
    for (const prop of Object.values(properties)) {
      if (prop.type === "INSTANCE_SWAP") {
        bind(prop.default_value.component);
        for (const pref of prop.preferred_values || []) bind(pref.component);
        for (const ac of prop.allowed_components || definition.swap_targets || []) if (Object.prototype.hasOwnProperty.call(definitions, ac)) bind(ac);
      }
    }
    const mains = [...components.entries()].filter(([key]) => JSON.parse(key)[0] === name).map(([, main]) => main);
    const owners = new Map();
    for (const main of mains) {
      const owner = main.parent?.type === "COMPONENT_SET" ? main.parent : main;
      if (!owners.has(owner)) owners.set(owner, []);
      owners.get(owner).push(main);
    }
    for (const [owner, variants] of owners) {
      const keys = Object.create(null);
      const contracts = Object.create(null);
      const seenNativeKeys = new Set();
      let explicitLabelKey = null;
      const slots = new Map(variants.map(main => [main, new Map()]));
      const textSlots = new Map(variants.map(main => [main, new Map()]));
      // Create real nested instances and named text children before assigning references.
      for (const prop of Object.values(properties)) if (prop.type === "INSTANCE_SWAP") for (const main of variants) {
        const slot = resolve(prop.default_value).createInstance();
        main.appendChild(slot); slot.name = "slot:" + prop.target;
        markComponentSlot(slot, info(main).semantic_id + "/slot:" + prop.target, prop.target);
        slots.get(main).set(prop.target, slot);
      }
      const textTargetsToCreate = new Map();
      for (const prop of Object.values(properties)) {
        if (prop.type === "TEXT" && prop.target !== "label") textTargetsToCreate.set(prop.target, prop.default_value);
      }
      if (definition.family === "field") {
        for (const prop of Object.values(properties)) {
          if (prop.type === "BOOLEAN" && prop.target === "field-help" && !textTargetsToCreate.has("field-help")) textTargetsToCreate.set("field-help", "");
        }
      }
      for (const [targetName, initialText] of textTargetsToCreate) {
        for (const main of variants) {
          const childText = createOwnedTextNode(initialText);
          main.appendChild(childText); childText.name = "text:" + targetName;
          metadata(childText, info(main).semantic_id + "/text:" + targetName, {kind:"component-text-slot", target:targetName});
          textSlots.get(main).set(targetName, childText);
        }
      }
      for (const [propId, prop] of Object.entries(properties)) {
        const display = prop.name === undefined ? propId : prop.name;
        if (typeof owner.addComponentProperty !== "function") throw new Error("Native declared component property API unavailable: " + owner.name);
        const value = prop.type === "INSTANCE_SWAP" ? resolve(prop.default_value).id : prop.default_value;
        const preferredValues = (prop.preferred_values || []).map((/** @type {any} */ ref) => {
          const target = resolve(ref);
          if (!target.key) throw new Error("Native swap target has no component key: " + ref.component);
          return {type:"COMPONENT", key:target.key};
        });
        const key = owner.addComponentProperty(display, prop.type, value, prop.type === "INSTANCE_SWAP" ? {preferredValues} : undefined);
        const actual = owner.componentPropertyDefinitions?.[key];
        if (!key || key === display || seenNativeKeys.has(key) || actual?.type !== prop.type || actual.defaultValue !== value || (prop.type === "INSTANCE_SWAP" && JSON.stringify(actual.preferredValues || []) !== JSON.stringify(preferredValues))) throw new Error("Native declaration was not retained: " + propId);
        seenNativeKeys.add(key);
        keys[propId] = key;
        const targetSuffix = prop.target === "label" ? "/label" : (slots.get(variants[0])?.has(prop.target) ? "/slot:" + prop.target : "/text:" + prop.target);
        contracts[propId] = {id:propId, name:display, actual_key:key, type:prop.type, target:prop.target, target_semantic_suffix:targetSuffix};
        if (prop.type === "TEXT" && prop.target === "label") explicitLabelKey = key;
        const field = prop.type === "TEXT" ? "characters" : (prop.type === "BOOLEAN" ? "visible" : "mainComponent");
        for (const main of variants) {
          const node = prop.target === "label"
            ? (main.children || []).find(child => child.type === "TEXT" && !child.name?.startsWith("text:"))
            : (slots.get(main).get(prop.target) || textSlots.get(main).get(prop.target));
          if (!node || node.componentPropertyReferences?.[field]) throw new Error("Owned component property target conflict: " + propId);
          if (field === "visible") node.visible = value;
          if (field === "characters") node.characters = value;
          node.componentPropertyReferences = {...(node.componentPropertyReferences || {}), [field]:key};
          if (node.componentPropertyReferences?.[field] !== key) throw new Error("Native property reference was not retained: " + propId);
        }
      }
      if (Object.keys(keys).length) {
        for (const node of [owner, ...variants]) {
          node.setPluginData(KEY, JSON.stringify({
            ...info(node),
            ...(explicitLabelKey ? {label_property_key:explicitLabelKey} : {}),
            declared_property_keys:keys,
            declared_property_contracts:contracts,
          }));
        }
      }
    }
    done.add(name);
  }
  for (const name of Object.keys(definitions)) bind(name);
}

async function applyDeclaredInstanceProperties(instance, main, element, components) {
  const definition = /** @type {any} */ (PAYLOAD.components)[element.component];
  const properties = /** @type {Record<string, any>} */ (definition?.properties || {});
  const declaredKeys = /** @type {Record<string, string>} */ (info(main).declared_property_keys || {});
  const overrides = /** @type {Record<string, any>} */ (element.property_values || {});
  const values = /** @type {Record<string, string | boolean>} */ ({});
  for (const [propId, prop] of Object.entries(properties)) {
    if (prop.type === "TEXT" && prop.target === "label" && !Object.prototype.hasOwnProperty.call(overrides, propId) && typeof element.text === "string") {
      const key = declaredKeys[propId];
      if (!key) throw new Error("Native declared instance property key unavailable: " + propId);
      values[key] = element.text;
    }
  }
  for (const [name, value] of Object.entries(overrides)) {
    const prop = properties[name];
    const key = declaredKeys[name];
    if (!prop || !key) throw new Error("Native declared instance property key unavailable: " + name);
    if (prop.type === "INSTANCE_SWAP") {
      const targetMain = components.get(JSON.stringify([value.component, value.variant]));
      if (!targetMain) throw new Error("Native declared swap target unavailable: " + name);
      values[key] = targetMain.id;
    } else {
      values[key] = value;
    }
  }
  if (Object.keys(values).length) instance.setProperties(values);
  for (const [key, value] of Object.entries(values)) if (instance.componentProperties?.[key]?.value !== value) throw new Error("Native instance property override was not retained: " + key);
  for (const [name, prop] of Object.entries(properties)) {
    const hasOverride = Object.prototype.hasOwnProperty.call(overrides, name);
    const value = hasOverride ? overrides[name] : (prop.type === "TEXT" && prop.target === "label" && typeof element.text === "string" ? element.text : prop.default_value);
    const target = prop.target === "label"
      ? (instance.children || []).find(child => child.type === "TEXT" && !child.name?.startsWith("text:"))
      : (instance.children || []).find(child => child.name === "slot:" + prop.target || child.name === "text:" + prop.target);
    if (!target) throw new Error("Native instance property target missing: " + name);
    if (prop.type === "TEXT") {
      if (target.type !== "TEXT" || target.characters !== value) throw new Error("Native instance text differs from declared property: " + name);
    } else if (prop.type === "BOOLEAN") {
      if (target.visible !== value) throw new Error("Native instance visibility differs from declared property: " + name);
    } else {
      if (target.type !== "INSTANCE") throw new Error("Native instance swap target is not an instance: " + name);
      const actual = await target.getMainComponentAsync();
      if (actual?.id !== components.get(JSON.stringify([value.component, value.variant]))?.id) throw new Error("Native instance swap differs from declared property: " + name);
    }
  }
  markImportedInstanceSlots(instance, element.id || info(main).semantic_id);
}

async function reapplyDeclaredComponents(page, nextPayload = PAYLOAD, options = {}) {
  const preserveInstanceOverrides = options.preserveInstanceOverrides !== false;
  const fail = message => { throw new Error("Declared component reapply: " + message); };
  if (!page || !Array.isArray(page.children)) fail("target page unavailable");
  if (options.expectedSourceSha256 !== undefined && info(page).source_sha256 !== options.expectedSourceSha256) fail("stale source_sha256 pin");
  validateDeclaredComponentProperties(nextPayload);
  const topNodes = new Map();
  function collectOwned(node, insideInstance = false) {
    const id = info(node).semantic_id || (typeof node.getPluginData === "function" ? node.getPluginData("semanticKey") : "") || null;
    if (id && !insideInstance) {
      if (!topNodes.has(id)) topNodes.set(id, []);
      topNodes.get(id).push(node);
    }
    const nextInside = insideInstance || node.type === "INSTANCE";
    for (const child of node.children || []) collectOwned(child, nextInside);
  }
  collectOwned(page, false);
  const uniqueOwned = identity => {
    const hits = topNodes.get(identity) || [];
    if (hits.length > 1) fail("ambiguous semantic node " + identity);
    return hits[0] || null;
  };
  const library = uniqueOwned("component-library");
  if (!library || library.type !== "FRAME") fail("missing owned component-library");
  for (const screen of nextPayload.screens || []) {
    const frame = uniqueOwned(screen.id);
    if (!frame || frame.type !== "FRAME") fail("missing target screen " + screen.id);
    if (options.strictExistingElements === true) {
      for (const [idx, element] of (screen.elements || []).entries()) {
        if (element.kind !== "component") continue;
        const identity = element.id || `${screen.id}/element:${idx}`;
        if (!uniqueOwned(identity)) fail("missing declared target instance " + identity);
      }
    }
  }
  // Preflight existing components and instances before mutating anything.
  const existingComponents = new Map();
  for (const [name, definition] of Object.entries(nextPayload.components || {})) {
    const swapTargets = componentSwapTargets(definition);
    for (const variant of Object.keys(definition.variants || {})) {
      const main = uniqueOwned(`component:${name}/${variant}`);
      if (!main) {
        if (options.allowNewVariants !== true) fail(`missing main component component:${name}/${variant}`);
        continue;
      }
      if (main.type !== "COMPONENT") fail(`corrupt main component component:${name}/${variant}`);
      existingComponents.set(JSON.stringify([name, variant]), main);
    }
    void swapTargets;
  }
  const allMainById = new Map([...existingComponents.entries()].map(([k, node]) => [node.id, JSON.parse(k)[0]]));
  for (const screen of nextPayload.screens || []) {
    for (const [idx, element] of (screen.elements || []).entries()) {
      if (element.kind !== "component") continue;
      const identity = element.id || `${screen.id}/element:${idx}`;
      const existing = uniqueOwned(identity);
      if (!existing) continue;
      if (existing.type !== "INSTANCE") fail("corrupt target node (not INSTANCE): " + identity);
      const definition = nextPayload.components[element.component];
      const main = existingComponents.get(JSON.stringify([element.component, element.variant]));
      const declaredKeys = info(main).declared_property_keys || {};
      for (const [propId, prop] of Object.entries(definition.properties || {})) {
        const key = declaredKeys[propId];
        const liveProp = existing.componentProperties?.[key];
        if (!key || !liveProp || liveProp.type !== prop.type) fail("stale or missing native property key on " + identity + "." + propId);
        if (preserveInstanceOverrides && prop.type === "INSTANCE_SWAP") {
          const liveCompName = allMainById.get(liveProp.value);
          const allowedList = prop.allowed_components || componentSwapTargets(definition) || null;
          if (!liveCompName || (allowedList && !allowedList.includes(liveCompName))) fail("existing swap override outside allowed range on " + identity + "." + propId);
        }
      }
    }
  }
  const createdNodes = [];
  const backups = [];
  const prevPayload = PAYLOAD;
  try {
    PAYLOAD = nextPayload;
    const reusedIds = { mainComponentIds: [], instanceIds: [], createdInstanceIds: [] };
    for (const [, main] of existingComponents) reusedIds.mainComponentIds.push(main.id);
    for (const screen of nextPayload.screens || []) {
      const frame = uniqueOwned(screen.id);
      for (const [idx, element] of (screen.elements || []).entries()) {
        if (element.kind !== "component") continue;
        const identity = element.id || `${screen.id}/element:${idx}`;
        const desiredMain = existingComponents.get(JSON.stringify([element.component, element.variant]));
        const existing = uniqueOwned(identity);
        if (existing) {
          const savedProps = Object.fromEntries(Object.entries(existing.componentProperties || {}).map(([k, v]) => [k, v.value]));
          const savedX = existing.x, savedY = existing.y;
          const savedTransform = existing.relativeTransform ? JSON.parse(JSON.stringify(existing.relativeTransform)) : undefined;
          backups.push({
            node: existing,
            x: savedX,
            y: savedY,
            relativeTransform: savedTransform,
            figmaFlow: existing.getPluginData(KEY),
            semanticKey: existing.getPluginData("semanticKey"),
            props: savedProps,
          });
          if (!preserveInstanceOverrides) {
            const labelKey = info(desiredMain).label_property_key;
            const hasExplicitLabelOverride = Object.entries(nextPayload.components[element.component]?.properties || {}).some(([pid, p]) => p.type === "TEXT" && p.target === "label" && Object.prototype.hasOwnProperty.call(element.property_values || {}, pid));
            if (labelKey && !hasExplicitLabelOverride && typeof element.text === "string") existing.setProperties({[labelKey]: element.text});
            await applyDeclaredInstanceProperties(existing, desiredMain, {...element, id: identity}, existingComponents);
          } else {
            markImportedInstanceSlots(existing, identity);
          }
          if (savedX !== undefined) existing.x = savedX;
          if (savedY !== undefined) existing.y = savedY;
          if (savedTransform !== undefined) existing.relativeTransform = savedTransform;
          reusedIds.instanceIds.push(existing.id);
        } else {
          const created = desiredMain.createInstance();
          createdNodes.push(created);
          frame.appendChild(created);
          created.name = (element.text || "").slice(0, 80) || element.kind;
          const label = (created.children || []).find(child => child.type === "TEXT" && !child.name?.startsWith("text:"));
          const labelKey = info(desiredMain).label_property_key;
          const hasExplicitLabelOverride = Object.entries(nextPayload.components[element.component]?.properties || {}).some(([pid, p]) => p.type === "TEXT" && p.target === "label" && Object.prototype.hasOwnProperty.call(element.property_values || {}, pid));
          if (labelKey && !hasExplicitLabelOverride && typeof element.text === "string") created.setProperties({[labelKey]: element.text});
          await applyDeclaredInstanceProperties(created, desiredMain, {...element, id: identity}, existingComponents);
          if (label) metadata(label, `${identity}/label`);
          metadata(created, identity, { kind: element.kind, annotation: element.annotation || "", action_id: element.action_id || null, target_screen: element.target_screen || null });
          reusedIds.createdInstanceIds.push(created.id);
        }
      }
    }
    if (typeof options.beforeCommitHook === "function") await options.beforeCommitHook({ createdNodes, reusedIds });
    return reusedIds;
  } catch (error) {
    for (const created of [...createdNodes].reverse()) {
      if (created && !created.removed && typeof created.remove === "function") created.remove();
      else if (created?.parent?.children) created.parent.children = created.parent.children.filter(item => item !== created);
    }
    for (const backup of [...backups].reverse()) {
      if (backup.x !== undefined) backup.node.x = backup.x;
      if (backup.y !== undefined) backup.node.y = backup.y;
      if (backup.relativeTransform !== undefined) backup.node.relativeTransform = backup.relativeTransform;
      backup.node.setPluginData(KEY, backup.figmaFlow);
      backup.node.setPluginData("semanticKey", backup.semanticKey);
      if (Object.keys(backup.props).length && typeof backup.node.setProperties === "function") backup.node.setProperties(backup.props);
    }
    throw error;
  } finally {
    PAYLOAD = prevPayload;
  }
}

async function importDesign(fresh) {
  if (PAYLOAD.technical_existing_only) throw new Error("Existing technical sync cannot author new UI. Select a direction for a production build.");
  if (!PAYLOAD.foundations || !PAYLOAD.selected_direction) throw new Error("Selected canonical design foundations required before native authoring");
  validateProductionColors(PAYLOAD);
  validateDeclaredComponentProperties(PAYLOAD);
  const existing = await imports();
  const matching = existing.filter(page => info(page).source_sha256 === PAYLOAD.source_sha256 && info(page).complete);
  const same = matching.find(page => page.id === figma.currentPage.id) || matching[matching.length - 1];
  if (same && !fresh) {
    await verifyHandoff(same, {preserveInstanceOverrides:true});
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
      const groups = componentVariantGroups(definition);
      const multiple = groups.length > 1;
      const usage = componentUsageText(definition);
      const swapTargets = componentSwapTargets(definition);
      const layoutMode = componentLayoutMode(definition);
      const hasDeclaredLabelTextProp = Object.values(definition.properties || {}).some(prop => prop?.type === "TEXT" && prop?.target === "label");
      for (const group of groups) {
        const variants = [];
        for (const [variant, props] of group.variants) {
          const node = figma.createComponent();
          library.appendChild(node);
          node.name = `${name}/${variant}`;
          layout(node, 320);
          if (layoutMode === "HORIZONTAL") {
            node.layoutMode = "HORIZONTAL";
            node.primaryAxisSizingMode = "AUTO";
            node.counterAxisSizingMode = "AUTO";
          }
          const label = text(name);
          node.appendChild(label);
          metadata(node, `component:${name}/${variant}`, { kind: "component", family: definition.family || null, swap_targets: swapTargets || null, token_properties: props });
          metadata(label, `component:${name}/${variant}/label`);
          applyProps(node, label, props, variables, warnings, fonts);
          await decorate(node);
          components.set(JSON.stringify([name, variant]), node);
          variants.push([variant, node]);
        }
        if (variants.length) {
          if (typeof figma.combineAsVariants === "function") {
            for (const [variant, node] of variants) node.name = `${group.axis}=${variant}`;
            const set = figma.combineAsVariants(variants.map(([, node]) => node), library);
            set.name = multiple ? `${name}/${group.axis}` : name;
            // Figma gives a new variant set a 5px corner radius; leave no unbound rendered radius on the container.
            if ('cornerRadius' in set) set.cornerRadius = 0;
            layout(set, 360);
            componentSets.push(set);
            metadata(set, multiple ? `component-set:${name}:${group.axis}` : `component-set:${name}`, { kind: "component-set", family: definition.family || null, swap_targets: swapTargets || null, variant_property: group.axis });
            if (usage) set.description = usage;
            if (!hasDeclaredLabelTextProp) bindOwnedLabelProperty(set, variants.map(([, node]) => node), warnings);
          } else {
            warnings.add(`Native variant sets unavailable for ${name}; individual main components are preserved.`);
            if (!hasDeclaredLabelTextProp) for (const [, node] of variants) bindOwnedLabelProperty(node, [node], warnings);
          }
        }
      }
    }
    bindDeclaredComponentProperties(components, PAYLOAD.components);
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
          const main = components.get(JSON.stringify([element.component, element.variant]));
          node = main.createInstance();
          const label = node.findOne(child => child.type === "TEXT" && !child.name?.startsWith("text:"));
          const labelKey = info(main).label_property_key;
          const explicitLabelOverrideEntry = Object.entries(PAYLOAD.components[element.component]?.properties || {}).find(([pid, p]) => p?.type === "TEXT" && p?.target === "label" && Object.prototype.hasOwnProperty.call(element.property_values || {}, pid));
          const initialLabelText = explicitLabelOverrideEntry ? element.property_values[explicitLabelOverrideEntry[0]] : element.text;
          if (labelKey) {
            const owner = main.parent?.type === "COMPONENT_SET" ? main.parent : main;
            const instanceReference = label?.componentPropertyReferences?.characters;
            if (owner.componentPropertyDefinitions?.[labelKey]?.type !== "TEXT" || (instanceReference !== undefined && instanceReference !== labelKey)) throw new Error(`Instance label is not linked to the owned text property: ${initialLabelText}`);
            node.setProperties({[labelKey]: initialLabelText});
            if (!label || label.characters !== initialLabelText || node.componentProperties?.[labelKey]?.type !== "TEXT" || node.componentProperties[labelKey].value !== initialLabelText) throw new Error(`Assigned label differs from the visible text: ${initialLabelText}`);
          } else if (label) label.characters = initialLabelText;
          await applyDeclaredInstanceProperties(node, main, {...element, id:element.id || `${screen.id}/element:${elementIndex}`}, components);
          if (label) metadata(label, `${element.id || `${screen.id}/element:${elementIndex}`}/label`);
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
      const sampleInstance = await figma.getNodeByIdAsync(sample.instanceId);
      metadata(sampleInstance,key);
      markImportedInstanceSlots(sampleInstance,key);
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
  const fields = ["x", "y", "width", "height", "visible", "opacity", "layoutMode", "primaryAxisSizingMode", "counterAxisSizingMode", "layoutSizingHorizontal", "layoutSizingVertical", "layoutWrap", "minWidth", "maxWidth", "minHeight", "maxHeight", "absoluteBoundingBox", "clipsContent", "textAutoResize", "itemSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "cornerRadius", "topLeftRadius", "topRightRadius", "bottomRightRadius", "bottomLeftRadius", "characters", "fontName", "fontSize", "fills", "strokes", "boundVariables", "reactions", "componentProperties", "componentPropertyDefinitions", "componentPropertyReferences", "variantProperties"];
  for (const field of fields) {
    try {
      const value = node[field];
      if (value !== undefined && typeof value !== "symbol") data[field] = value;
    } catch (error) {
      (data.unavailable_fields ||= {})[field] = error.message || String(error);
    }
  }
  if (node.type === "COMPONENT" || node.type === "COMPONENT_SET") {
    try { data.component_key = node.key; }
    catch(error) { (data.unavailable_fields ||= {}).component_key = error.message || String(error); }
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
    const read = requireFullNativeRead(await readNativeSemantics(figma,page));
    nativeReads.push(read);
    mergeNativeRasterImages(rasterImages, read.rasterImages);
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
  if (message.type === "native-summary") {
    if (!sessionNonce || message.session_nonce !== sessionNonce || busy) return;
    const page = figma.currentPage;
    const requested = Array.isArray(message.nodeIds) && message.nodeIds.length && message.nodeIds.every(id => typeof id === "string") ? message.nodeIds : [page.id, ...page.findAll(() => true).map(node => node.id)];
    const fields = Array.isArray(message.fields) && message.fields.length && message.fields.every(field => typeof field === "string") ? message.fields : ["width", "height"];
    const summary = await readNativeSemantics(figma, page, {profile: "summary", nodeIds: requested, fields});
    if (summary && summary.schema === "figma-flow-native-read-summary-v1" && summary.coverage && summary.coverage.complete === false) post({type: "native-summary", summary});
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
