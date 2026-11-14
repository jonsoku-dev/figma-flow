"use strict";
const KEY = "figmaFlow";
const PAYLOAD = { "version": 1, "tokens": { "color.ink": { "type": "color", "value": "#202020", "css_name": "--color-ink", "alias": null }, "color.surface": { "type": "color", "value": "#ffffff", "css_name": "--color-surface", "alias": null }, "font.body": { "type": "fontFamily", "value": "Arial", "css_name": "--font-body", "alias": null }, "font.size": { "type": "dimension", "value": "16px", "css_name": "--font-size", "alias": null }, "space.gap": { "type": "dimension", "value": "8px", "css_name": "--space-gap", "alias": null } }, "components": { "button": { "usage": "Button with an optional swappable leading symbol.", "variants": { "default": { "color": "color.ink", "background": "color.surface", "padding": "space.gap", "font-family": "font.body", "font-size": "font.size" } }, "properties": { "ShowLabel": { "type": "BOOLEAN", "target": "label", "default_value": true }, "Symbol": { "type": "INSTANCE_SWAP", "target": "symbol", "default_value": { "component": "symbol", "variant": "circle" }, "preferred_values": [{ "component": "symbol", "variant": "circle" }, { "component": "symbol", "variant": "square" }] }, "ShowSymbol": { "type": "BOOLEAN", "target": "symbol", "default_value": true } } }, "symbol": { "usage": "Two local swap choices.", "variants": { "circle": { "color": "color.ink", "padding": "space.gap", "font-size": "font.size" }, "square": { "color": "color.ink", "padding": "space.gap", "font-size": "font.size" } } } }, "screens": [{ "id": "properties-demo", "title": "Declared component properties", "trace": ["REQ-DECLARED-PROPERTIES"], "elements": [{ "id": "default-button", "kind": "component", "component": "button", "variant": "default", "text": "Default" }, { "id": "swapped-button", "kind": "component", "component": "button", "variant": "default", "text": "Swapped", "property_values": { "Symbol": { "component": "symbol", "variant": "square" }, "ShowLabel": false } }, { "id": "hidden-symbol-button", "kind": "component", "component": "button", "variant": "default", "text": "Hidden symbol", "property_values": { "ShowSymbol": false } }] }] };
function metadata(node, id, extra = {}) {
    node.setPluginData(KEY, JSON.stringify({ semantic_id: id, ...extra }));
    if (node.type !== "VARIABLE" && node.type !== "VARIABLE_COLLECTION")
        node.setPluginData("semanticKey", id);
}
function info(node) {
    try {
        return JSON.parse(node.getPluginData(KEY) || "{}");
    }
    catch (_) {
        return {};
    }
}
function bindOwnedLabelProperty(owner, mains, warnings) {
    const labels = mains.map(main => {
        const label = (main.children || []).find(child => child.type === "TEXT");
        if (!label)
            throw new Error(`Component variant has no label: ${main.name}`);
        return label;
    });
    if (typeof owner.addComponentProperty !== "function") {
        warnings.add(`Native text properties unavailable for ${owner.name}; direct label text is preserved.`);
        return null;
    }
    const referenced = [...new Set(labels.map(label => label.componentPropertyReferences?.characters).filter(Boolean))];
    if (referenced.length > 1)
        throw new Error(`Label property conflict on ${owner.name}: ${referenced.join(", ")}`);
    let key = referenced[0];
    if (key) {
        if (owner.componentPropertyDefinitions?.[key]?.type !== "TEXT")
            throw new Error(`Existing label reference is not a TEXT property on ${owner.name}: ${key}`);
    }
    else {
        const displayName = "문구";
        key = owner.addComponentProperty(displayName, "TEXT", labels[0].characters);
        if (typeof key !== "string" || !key || key === displayName || owner.componentPropertyDefinitions?.[key]?.type !== "TEXT")
            throw new Error(`Native text property key missing for ${owner.name}`);
    }
    for (const label of labels) {
        if (label.componentPropertyReferences?.characters === key)
            continue;
        if (label.componentPropertyReferences?.characters)
            throw new Error(`Label property conflict on ${owner.name}: ${label.componentPropertyReferences.characters}`);
        try {
            label.componentPropertyReferences = { ...(label.componentPropertyReferences || {}), characters: key };
        }
        catch (error) {
            throw new Error(`Cannot link owned label on ${owner.name}: ${error.message || error}`);
        }
        if (label.componentPropertyReferences?.characters !== key)
            throw new Error(`Label reference was not retained on ${owner.name}`);
    }
    for (const node of [owner, ...mains])
        node.setPluginData(KEY, JSON.stringify({ ...info(node), label_property_key: key }));
    return key;
}
function validateDeclaredComponentProperties(payload) {
    const fail = message => { throw new Error("Declared component properties: " + message); };
    const secretPattern = /(?:sk-[A-Za-z0-9_-]{12,}|figd_[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{12,}|\/Users\/[^\s/]+|(?:api[_-]?key|secret|password|passwd|access[_-]?token)\s*[:=]\s*\S+)/i;
    const checkText = (value, label) => {
        if (typeof value !== "string")
            fail(label + " must be string");
        if (secretPattern.test(value))
            fail("secret or private path forbidden in " + label);
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
        if (!Array.isArray(rawFamilies) || !rawFamilies.length || rawFamilies.length > 32)
            fail("componentFamilies must be a bounded nonempty list");
        const seenFamilies = new Set();
        for (const fam of rawFamilies) {
            if (!fam || typeof fam !== "object" || typeof fam.id !== "string" || !Object.prototype.hasOwnProperty.call(familySpecs, fam.id) || fam.version !== 1)
                fail("unsupported or unversioned component family");
            if (seenFamilies.has(fam.id))
                fail("duplicate component family " + fam.id);
            seenFamilies.add(fam.id);
            const spec = familySpecs[ /** @type {keyof typeof familySpecs} */(fam.id)];
            if (spec.requiredLayout && fam.layout && fam.layout !== spec.requiredLayout)
                fail("invalid layout for family " + fam.id);
        }
    }
    const dependencies = new Map(Object.keys(components).map(name => [name, new Set()]));
    const reference = value => {
        if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).sort().join(",") !== "component,variant" || typeof value.component !== "string" || typeof value.variant !== "string" || !Object.prototype.hasOwnProperty.call(components[value.component]?.variants || {}, value.variant))
            fail("swap requires an existing local component variant");
        return value.component;
    };
    const allowedSwapSetFor = (definition, prop) => {
        let compAllowed = null;
        if (Object.prototype.hasOwnProperty.call(definition, "swap_targets")) {
            if (!Array.isArray(definition.swap_targets) || !definition.swap_targets.length || definition.swap_targets.some((/** @type {any} */ item) => typeof item !== "string" || !Object.prototype.hasOwnProperty.call(components, item)))
                fail("swap_targets must reference local components");
            compAllowed = new Set(definition.swap_targets);
        }
        let propAllowed = null;
        if (prop.allowed_components !== undefined) {
            if (!Array.isArray(prop.allowed_components) || !prop.allowed_components.length || prop.allowed_components.some((/** @type {any} */ item) => typeof item !== "string" || !Object.prototype.hasOwnProperty.call(components, item)))
                fail("allowed_components must reference local components");
            propAllowed = new Set(prop.allowed_components);
        }
        if (compAllowed && propAllowed) {
            const intersection = new Set([...propAllowed].filter(item => compAllowed.has(item)));
            if (!intersection.size)
                fail("allowed_components conflicts with component swap_targets");
            return intersection;
        }
        return propAllowed || compAllowed;
    };
    for (const [name, definition] of Object.entries(components)) {
        if (Object.prototype.hasOwnProperty.call(definition, "family")) {
            if (typeof definition.family !== "string" || !Object.prototype.hasOwnProperty.call(familySpecs, definition.family))
                fail("unsupported component family " + definition.family);
            const spec = familySpecs[ /** @type {keyof typeof familySpecs} */(definition.family)];
            if (spec.requiredLayout && (definition.layout || "VERTICAL") !== spec.requiredLayout)
                fail("invalid layout for family " + definition.family);
            const stateValues = definition.variant_axes?.state;
            if (Array.isArray(stateValues) && stateValues.some((/** @type {any} */ st) => !spec.states.includes(st)))
                fail("undeclared state value on " + name);
        }
        if (Object.prototype.hasOwnProperty.call(definition, "swap_targets")) {
            if (!Array.isArray(definition.swap_targets) || !definition.swap_targets.length || definition.swap_targets.some((/** @type {any} */ item) => typeof item !== "string" || !Object.prototype.hasOwnProperty.call(components, item)))
                fail("swap_targets must reference local components");
        }
        const properties = Object.prototype.hasOwnProperty.call(definition, "properties") ? definition.properties : {};
        if (!properties || typeof properties !== "object" || Array.isArray(properties) || Object.keys(properties).length > 32)
            fail("properties must be a bounded mapping");
        const swaps = new Set(), textTargets = new Set(), targets = new Set();
        const axes = new Set(["Variant", ...Object.keys(definition.variant_axes || {})]);
        for (const [propId, prop] of Object.entries(/** @type {Record<string, any>} */ (properties))) {
            const display = prop?.name === undefined ? propId : prop.name;
            if (!propId.trim() || propId.includes("#") || propId === "문구" || axes.has(propId) || typeof display !== "string" || !display.trim() || display.includes("#") || display === "문구" || axes.has(display))
                fail("property display name conflicts with an owned native property");
            const allowedKeys = prop?.type === "INSTANCE_SWAP" ? ["type", "target", "default_value", "name", "preferred_values", "allowed_components"] : ["type", "target", "default_value", "name"];
            if (!prop || !["TEXT", "BOOLEAN", "INSTANCE_SWAP"].includes(prop.type) || typeof prop.target !== "string" || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(prop.target) || !Object.prototype.hasOwnProperty.call(prop, "default_value") || Object.keys(prop).some(key => !allowedKeys.includes(key)))
                fail("invalid declaration " + propId);
            const target = prop.type + ":" + prop.target;
            if (targets.has(target))
                fail("duplicate target field " + prop.target);
            targets.add(target);
            if (prop.type === "TEXT") {
                checkText(prop.default_value, name + "." + propId);
                if (prop.target !== "label")
                    textTargets.add(prop.target);
            }
            else if (prop.type === "BOOLEAN") {
                if (typeof prop.default_value !== "boolean")
                    fail("BOOLEAN default must be boolean");
            }
            else {
                if (prop.target === "label")
                    fail("swap target must be a named slot");
                swaps.add(prop.target);
                const allowedSwapSet = allowedSwapSetFor(definition, prop);
                if (definition.family === "table-row" && allowedSwapSet && [...allowedSwapSet].some(tc => components[tc]?.family && components[tc].family !== "table-cell"))
                    fail("table-row swap targets must belong to table-cell");
                const defaultComp = reference(prop.default_value);
                if (allowedSwapSet && !allowedSwapSet.has(defaultComp))
                    fail("swap default outside allowed swap_targets: " + defaultComp);
                dependencies.get(name).add(defaultComp);
                if (prop.preferred_values !== undefined && (!Array.isArray(prop.preferred_values) || prop.preferred_values.length > 100))
                    fail("invalid preferred_values");
                for (const preferred of prop.preferred_values || []) {
                    const prefComp = reference(preferred);
                    if (allowedSwapSet && !allowedSwapSet.has(prefComp))
                        fail("preferred_values outside allowed swap_targets: " + prefComp);
                    dependencies.get(name).add(prefComp);
                }
            }
        }
        for (const slotName of swaps)
            if (textTargets.has(slotName))
                fail("slot and text target collision " + slotName);
        for (const prop of Object.values(/** @type {Record<string, any>} */ (properties))) {
            if (prop.type === "BOOLEAN" && prop.target !== "label" && !swaps.has(prop.target) && !textTargets.has(prop.target) && !(definition.family === "field" && prop.target === "field-help")) {
                fail("BOOLEAN target must be label or declared slot");
            }
        }
    }
    for (const screen of payload.screens)
        for (const element of /** @type {any[]} */ (screen.elements)) {
            if (!Object.prototype.hasOwnProperty.call(element, "property_values"))
                continue;
            const overrides = element.property_values;
            if (element.kind !== "component" || !overrides || typeof overrides !== "object" || Array.isArray(overrides))
                fail("invalid instance property_values");
            const compDef = components[element.component];
            for (const [name, value] of Object.entries(overrides)) {
                const prop = compDef?.properties?.[name];
                if (!prop)
                    fail("unknown instance property " + name);
                if (prop.type === "TEXT") {
                    checkText(value, element.component + "." + name);
                }
                else if (prop.type === "BOOLEAN") {
                    if (typeof value !== "boolean")
                        fail("BOOLEAN override must be boolean");
                }
                else {
                    const swapComp = reference(value);
                    const allowedSwapSet = allowedSwapSetFor(compDef, prop);
                    if (allowedSwapSet && !allowedSwapSet.has(swapComp))
                        fail("instance swap outside allowed swap_targets: " + swapComp);
                    dependencies.get(element.component).add(swapComp);
                }
            }
        }
    const visiting = new Set(), done = new Set();
    function visit(name) {
        if (visiting.has(name))
            fail("recursive swap dependencies are unsupported");
        if (done.has(name))
            return;
        visiting.add(name);
        for (const dependency of dependencies.get(name))
            visit(dependency);
        visiting.delete(name);
        done.add(name);
    }
    for (const name of dependencies.keys())
        visit(name);
}
function markComponentSlot(node, semanticId, slot) {
    metadata(node, semanticId, { kind: "component-slot", slot });
    for (const [index, child] of (node.children || []).entries())
        markComponentSlot(child, semanticId + "/child:" + index, slot);
}
function markImportedInstanceSlots(instance, identity) {
    for (const child of instance.children || []) {
        if (child.name?.startsWith("slot:"))
            markComponentSlot(child, identity + "/" + child.name, child.name.slice(5));
        else if (child.name?.startsWith("text:"))
            metadata(child, identity + "/" + child.name, { kind: "component-text-slot", target: child.name.slice(5) });
    }
}
function bindDeclaredComponentProperties(components, definitions) {
    const done = new Set();
    const resolve = ref => components.get(JSON.stringify([ref.component, ref.variant]));
    const createOwnedTextNode = value => {
        const helper = /** @type {any} */ (globalThis).text;
        if (typeof helper === "function")
            return helper(value);
        const node = figma.createText();
        node.characters = value;
        return node;
    };
    function bind(name) {
        if (done.has(name))
            return;
        const definition = /** @type {any} */ (definitions[name]);
        const properties = /** @type {Record<string, any>} */ (definition.properties || {});
        for (const prop of Object.values(properties)) {
            if (prop.type === "INSTANCE_SWAP") {
                bind(prop.default_value.component);
                for (const pref of prop.preferred_values || [])
                    bind(pref.component);
                for (const ac of prop.allowed_components || definition.swap_targets || [])
                    if (Object.prototype.hasOwnProperty.call(definitions, ac))
                        bind(ac);
            }
        }
        const mains = [...components.entries()].filter(([key]) => JSON.parse(key)[0] === name).map(([, main]) => main);
        const owners = new Map();
        for (const main of mains) {
            const owner = main.parent?.type === "COMPONENT_SET" ? main.parent : main;
            if (!owners.has(owner))
                owners.set(owner, []);
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
            for (const prop of Object.values(properties))
                if (prop.type === "INSTANCE_SWAP")
                    for (const main of variants) {
                        const slot = resolve(prop.default_value).createInstance();
                        main.appendChild(slot);
                        slot.name = "slot:" + prop.target;
                        markComponentSlot(slot, info(main).semantic_id + "/slot:" + prop.target, prop.target);
                        slots.get(main).set(prop.target, slot);
                    }
            const textTargetsToCreate = new Map();
            for (const prop of Object.values(properties)) {
                if (prop.type === "TEXT" && prop.target !== "label")
                    textTargetsToCreate.set(prop.target, prop.default_value);
            }
            if (definition.family === "field") {
                for (const prop of Object.values(properties)) {
                    if (prop.type === "BOOLEAN" && prop.target === "field-help" && !textTargetsToCreate.has("field-help"))
                        textTargetsToCreate.set("field-help", "");
                }
            }
            for (const [targetName, initialText] of textTargetsToCreate) {
                for (const main of variants) {
                    const childText = createOwnedTextNode(initialText);
                    main.appendChild(childText);
                    childText.name = "text:" + targetName;
                    metadata(childText, info(main).semantic_id + "/text:" + targetName, { kind: "component-text-slot", target: targetName });
                    textSlots.get(main).set(targetName, childText);
                }
            }
            for (const [propId, prop] of Object.entries(properties)) {
                const display = prop.name === undefined ? propId : prop.name;
                if (typeof owner.addComponentProperty !== "function")
                    throw new Error("Native declared component property API unavailable: " + owner.name);
                const value = prop.type === "INSTANCE_SWAP" ? resolve(prop.default_value).id : prop.default_value;
                const preferredValues = (prop.preferred_values || []).map((/** @type {any} */ ref) => {
                    const target = resolve(ref);
                    if (!target.key)
                        throw new Error("Native swap target has no component key: " + ref.component);
                    return { type: "COMPONENT", key: target.key };
                });
                const key = owner.addComponentProperty(display, prop.type, value, prop.type === "INSTANCE_SWAP" ? { preferredValues } : undefined);
                const actual = owner.componentPropertyDefinitions?.[key];
                if (!key || key === display || seenNativeKeys.has(key) || actual?.type !== prop.type || actual.defaultValue !== value || (prop.type === "INSTANCE_SWAP" && JSON.stringify(actual.preferredValues || []) !== JSON.stringify(preferredValues)))
                    throw new Error("Native declaration was not retained: " + propId);
                seenNativeKeys.add(key);
                keys[propId] = key;
                const targetSuffix = prop.target === "label" ? "/label" : (slots.get(variants[0])?.has(prop.target) ? "/slot:" + prop.target : "/text:" + prop.target);
                contracts[propId] = { id: propId, name: display, actual_key: key, type: prop.type, target: prop.target, target_semantic_suffix: targetSuffix };
                if (prop.type === "TEXT" && prop.target === "label")
                    explicitLabelKey = key;
                const field = prop.type === "TEXT" ? "characters" : (prop.type === "BOOLEAN" ? "visible" : "mainComponent");
                for (const main of variants) {
                    const node = prop.target === "label"
                        ? (main.children || []).find(child => child.type === "TEXT" && !child.name?.startsWith("text:"))
                        : (slots.get(main).get(prop.target) || textSlots.get(main).get(prop.target));
                    if (!node || node.componentPropertyReferences?.[field])
                        throw new Error("Owned component property target conflict: " + propId);
                    if (field === "visible")
                        node.visible = value;
                    if (field === "characters")
                        node.characters = value;
                    node.componentPropertyReferences = { ...(node.componentPropertyReferences || {}), [field]: key };
                    if (node.componentPropertyReferences?.[field] !== key)
                        throw new Error("Native property reference was not retained: " + propId);
                }
            }
            if (Object.keys(keys).length) {
                for (const node of [owner, ...variants]) {
                    node.setPluginData(KEY, JSON.stringify({
                        ...info(node),
                        ...(explicitLabelKey ? { label_property_key: explicitLabelKey } : {}),
                        declared_property_keys: keys,
                        declared_property_contracts: contracts,
                    }));
                }
            }
        }
        done.add(name);
    }
    for (const name of Object.keys(definitions))
        bind(name);
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
            if (!key)
                throw new Error("Native declared instance property key unavailable: " + propId);
            values[key] = element.text;
        }
    }
    for (const [name, value] of Object.entries(overrides)) {
        const prop = properties[name];
        const key = declaredKeys[name];
        if (!prop || !key)
            throw new Error("Native declared instance property key unavailable: " + name);
        if (prop.type === "INSTANCE_SWAP") {
            const targetMain = components.get(JSON.stringify([value.component, value.variant]));
            if (!targetMain)
                throw new Error("Native declared swap target unavailable: " + name);
            values[key] = targetMain.id;
        }
        else {
            values[key] = value;
        }
    }
    if (Object.keys(values).length)
        instance.setProperties(values);
    for (const [key, value] of Object.entries(values))
        if (instance.componentProperties?.[key]?.value !== value)
            throw new Error("Native instance property override was not retained: " + key);
    for (const [name, prop] of Object.entries(properties)) {
        const hasOverride = Object.prototype.hasOwnProperty.call(overrides, name);
        const value = hasOverride ? overrides[name] : (prop.type === "TEXT" && prop.target === "label" && typeof element.text === "string" ? element.text : prop.default_value);
        const target = prop.target === "label"
            ? (instance.children || []).find(child => child.type === "TEXT" && !child.name?.startsWith("text:"))
            : (instance.children || []).find(child => child.name === "slot:" + prop.target || child.name === "text:" + prop.target);
        if (!target)
            throw new Error("Native instance property target missing: " + name);
        if (prop.type === "TEXT") {
            if (target.type !== "TEXT" || target.characters !== value)
                throw new Error("Native instance text differs from declared property: " + name);
        }
        else if (prop.type === "BOOLEAN") {
            if (target.visible !== value)
                throw new Error("Native instance visibility differs from declared property: " + name);
        }
        else {
            if (target.type !== "INSTANCE")
                throw new Error("Native instance swap target is not an instance: " + name);
            const actual = await target.getMainComponentAsync();
            if (actual?.id !== components.get(JSON.stringify([value.component, value.variant]))?.id)
                throw new Error("Native instance swap differs from declared property: " + name);
        }
    }
    markImportedInstanceSlots(instance, element.id || info(main).semantic_id);
}
async function main() {
    if (figma.editorType !== 'figma')
        throw new Error('Open this recipe in Figma Design.');
    const page = figma.currentPage;
    const selection = [...page.selection];
    const owned = [];
    const track = (node) => { owned.push(node); return node; };
    try {
        validateDeclaredComponentProperties(PAYLOAD);
        const font = { family: 'Inter', style: 'Regular' };
        await figma.loadFontAsync(font);
        const x = page.children.reduce((right, node) => {
            const bounds = node.absoluteBoundingBox;
            return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
        }, 0) + 160;
        const container = track(figma.createFrame());
        container.name = 'Recipe · Native BOOLEAN and INSTANCE_SWAP';
        container.x = x;
        container.layoutMode = 'VERTICAL';
        container.primaryAxisSizingMode = 'AUTO';
        container.counterAxisSizingMode = 'AUTO';
        container.paddingTop = container.paddingBottom = container.paddingLeft = container.paddingRight = 32;
        container.itemSpacing = 20;
        const label = (parent, value) => {
            const text = track(figma.createText());
            parent.appendChild(text);
            text.fontName = font;
            text.characters = value;
            text.fontSize = 18;
            return text;
        };
        label(container, 'Native component properties · BOOLEAN + INSTANCE_SWAP');
        const components = new class extends Map {
            get(key) {
                const main = super.get(key);
                return main && new Proxy(main, { get(target, field) {
                        if (field === 'createInstance')
                            return () => track(target.createInstance());
                        const value = Reflect.get(target, field, target);
                        return typeof value === 'function' ? value.bind(target) : value;
                    } });
            }
        }();
        const warnings = new Set();
        for (const [name, definition] of Object.entries(PAYLOAD.components)) {
            const mains = [];
            for (const variant of Object.keys(definition.variants)) {
                const main = track(figma.createComponent());
                container.appendChild(main);
                main.name = 'Variant=' + variant;
                main.layoutMode = 'HORIZONTAL';
                main.primaryAxisSizingMode = 'AUTO';
                main.counterAxisSizingMode = 'AUTO';
                main.paddingTop = main.paddingBottom = main.paddingLeft = main.paddingRight = 12;
                main.itemSpacing = 12;
                label(main, name === 'button' ? 'Button label' : variant);
                if (name === 'symbol') {
                    const shape = variant === 'circle' ? figma.createEllipse() : figma.createRectangle();
                    main.appendChild(shape);
                    shape.resize(24, 24);
                    shape.fills = [{ type: 'SOLID', color: { r: 0.22, g: 0.36, b: 0.85 } }];
                }
                metadata(main, 'component:' + name + '/' + variant);
                components.set(JSON.stringify([name, variant]), main);
                mains.push(main);
            }
            const set = track(figma.combineAsVariants(mains, container));
            set.name = 'Main family · ' + name;
            set.layoutMode = 'HORIZONTAL';
            set.primaryAxisSizingMode = 'AUTO';
            set.counterAxisSizingMode = 'AUTO';
            set.itemSpacing = 24;
            bindOwnedLabelProperty(set, mains, warnings);
        }
        bindDeclaredComponentProperties(components, PAYLOAD.components);
        const button = components.get(JSON.stringify(['button', 'default']));
        if (!button)
            throw new Error('Compiled fixture has no button/default.');
        const cases = [
            'Default · label visible, circle symbol visible',
            'Override · label hidden, square symbol visible',
            'Override · label visible, symbol hidden',
        ];
        const report = [];
        for (const [index, element] of PAYLOAD.screens[0].elements.entries()) {
            label(container, cases[index]);
            const instance = button.createInstance();
            container.appendChild(instance);
            instance.name = element.id;
            await applyDeclaredInstanceProperties(instance, button, element, components);
            const text = instance.children.find(child => child.type === 'TEXT');
            const slot = instance.children.find(child => child.name === 'slot:symbol');
            if (!text || !slot || slot.type !== 'INSTANCE')
                throw new Error('Native property targets missing.');
            const main = await slot.getMainComponentAsync();
            if (!main)
                throw new Error('Native swap main component unavailable.');
            report.push({ name: instance.name, id: instance.id, labelVisible: text.visible,
                slotVisible: slot.visible, mainComponentId: main.id });
        }
        const keys = info(button).declared_property_keys;
        if (!keys || button.parent?.type !== 'COMPONENT_SET')
            throw new Error('Native property keys unavailable.');
        const definitions = button.parent.componentPropertyDefinitions;
        const expected = ['circle', 'square'].map(variant => {
            const main = components.get(JSON.stringify(['symbol', variant]));
            if (!main)
                throw new Error('Preferred component unavailable.');
            return { type: 'COMPONENT', key: main.key };
        });
        if (definitions[keys.ShowLabel]?.type !== 'BOOLEAN' || definitions[keys.ShowSymbol]?.type !== 'BOOLEAN' ||
            definitions[keys.Symbol]?.type !== 'INSTANCE_SWAP' ||
            JSON.stringify(definitions[keys.Symbol].preferredValues) !== JSON.stringify(expected)) {
            throw new Error('Native definitions or preferred component keys differ.');
        }
        if (!button.children.find(child => child.type === 'TEXT')?.visible ||
            !button.children.find(child => child.name === 'slot:symbol')?.visible) {
            throw new Error('Instance overrides changed a main default.');
        }
        label(container, 'PASS · native definitions, references, defaults, overrides and preferred keys verified');
        container.setPluginData('componentPropertiesRecipeResult', JSON.stringify({ status: 'PASS', definitions, report }));
        page.selection = [container];
        figma.viewport.scrollAndZoomIntoView([container]);
        figma.closePlugin('PASS · Created native BOOLEAN and INSTANCE_SWAP examples in a new frame.');
    }
    catch (error) {
        for (const node of [...owned].reverse()) {
            if (!node.removed) {
                try {
                    node.remove();
                }
                catch (_) { }
            }
        }
        if (figma.currentPage.id === page.id)
            page.selection = selection.filter(node => !node.removed);
        const remaining = owned.filter(node => !node.removed);
        if (remaining.length)
            throw new Error(String(error) + '; cleanup failed for ' + remaining.map(node => node.id).join(', '));
        throw error;
    }
}
main().catch((error) => figma.closePlugin(String(error)));
