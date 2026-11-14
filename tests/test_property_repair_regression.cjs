const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const codeRuntime = fs.readFileSync(path.join(root, 'figma-bridge/code.js'), 'utf8');
const {
  ensureSemanticComponents,
  readSemanticComponentFamilies,
} = require('../figma-bridge/semantic_components.js');

const sixFamiliesSource = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'fixtures/nf01/six-families.json'), 'utf8')
);
const compiledDesignPayload = JSON.parse(
  execFileSync(
    'python3',
    [
      '-B',
      '-c',
      'import json,sys;sys.path.insert(0,"tools");from design_system import compile_design;print(json.dumps(compile_design(json.load(sys.stdin))))',
    ],
    { cwd: root, input: JSON.stringify(sixFamiliesSource), encoding: 'utf8' }
  )
);
const examplesDesignContract = JSON.parse(
  execFileSync(
    'python3',
    [
      '-B',
      '-c',
      [
        'import json, pathlib, sys',
        'sys.path.insert(0, "tools")',
        'from design_system import compile_graph_component_families',
        'design = json.loads(pathlib.Path("examples/owned-component-families/design.json").read_text())',
        'print(json.dumps(compile_graph_component_families(design)))',
      ].join('; '),
    ],
    { cwd: root, encoding: 'utf8' }
  )
);

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

function createSemanticRegressionWorld(options = {}) {
  let nodeSeq = 0;
  let propSeq = 0;
  const allComponentsById = new Map();
  const allInstances = new Set();
  const removeCalls = [];
  const descendantRemoveAttempts = [];

  class MockNode {
    constructor(type, name = type) {
      this.id = `${++nodeSeq}:${type.slice(0, 2).toLowerCase()}`;
      if (type === 'COMPONENT') {
        this.key = `comp_key_${nodeSeq}`;
      }
      this.type = type;
      this.name = name;
      this.parent = null;
      this.children = [];
      this.data = {};
      this.visible = true;
      this.removed = false;
      this.x = 0;
      this.y = 0;
      this.width = 160;
      this.height = 48;
      this.relativeTransform = [[1, 0, 0], [0, 1, 0]];
      this.layoutMode = 'NONE';
      this.primaryAxisSizingMode = 'AUTO';
      this.counterAxisSizingMode = 'AUTO';
      this.primaryAxisAlignItems = 'MIN';
      this.counterAxisAlignItems = 'MIN';
      this.paddingTop = 0;
      this.paddingRight = 0;
      this.paddingBottom = 0;
      this.paddingLeft = 0;
      this.itemSpacing = 0;
      this.cornerRadius = 0;
      this.strokeWeight = 1;
      this.fills = [];
      this.strokes = [];
      this.clipsContent = false;
      this.characters = '';
      this.fontName = { family: 'Inter', style: 'Regular' };
      this.fontSize = 14;
      this.variantProperties = null;
      this.componentPropertyDefinitions = {};
      this.componentPropertyReferences = {};
      this.componentProperties = {};
      this._overriddenPropKeys = new Set();
      this._main = null;
      this._firstKeyByName = new Map();
      this._nameCounts = new Map();
      if (type === 'COMPONENT') {
        allComponentsById.set(this.id, this);
      }
    }

    setPluginData(key, value) {
      this.data[key] = String(value);
    }

    getPluginData(key) {
      return Object.prototype.hasOwnProperty.call(this.data, key) ? this.data[key] : '';
    }

    getPluginDataKeys() {
      return Object.keys(this.data);
    }

    resize(w, h) {
      this.width = w;
      this.height = h;
    }

    appendChild(child) {
      this.insertChild(this.children.length, child);
      if (this.type === 'COMPONENT_SET' && child.type === 'COMPONENT' && child.name.includes('=')) {
        child.variantProperties = Object.fromEntries(
          child.name.split(', ').map(part => part.split('='))
        );
      }
    }

    insertChild(index, child) {
      if (child.parent) {
        child.parent.children = child.parent.children.filter(c => c !== child);
      }
      child.parent = this;
      this.children.splice(index, 0, child);
    }

    remove() {
      removeCalls.push({ id: this.id, type: this.type, name: this.name, parentType: this.parent?.type || null });
      if (
        options.denyDescendantRemove &&
        this.parent &&
        (this.parent.type === 'COMPONENT' || this.parent.type === 'COMPONENT_SET' || this.parent.type === 'INSTANCE')
      ) {
        descendantRemoveAttempts.push({ id: this.id, type: this.type, name: this.name, parentType: this.parent.type });
        throw new Error('in remove: Removing this node is not allowed');
      }
      this.removed = true;
      allInstances.delete(this);
      if (this.parent) {
        this.parent.children = this.parent.children.filter(c => c !== this);
        this.parent = null;
      }
    }

    findOne(predicate) {
      for (const child of this.children) {
        if (predicate(child)) return child;
        const hit = child.findOne(predicate);
        if (hit) return hit;
      }
      return null;
    }

    findAll(predicate) {
      const out = [];
      for (const child of this.children) {
        if (predicate(child)) out.push(child);
        out.push(...child.findAll(predicate));
      }
      return out;
    }

    async loadAsync() {}

    addComponentProperty(name, type, defaultValue, propOptions) {
      if (options.failAddPropertyName && name === options.failAddPropertyName) {
        throw new Error(`Simulated failure adding property ${name}`);
      }
      if (options.returnBrokenKeyForName && name === options.returnBrokenKeyForName) {
        return '';
      }
      const mode = options.duplicateMode || 'unique';
      const seenCount = this._nameCounts.get(name) || 0;
      if (seenCount > 0) {
        if (mode === 'same-key') {
          return this._firstKeyByName.get(name);
        }
        if (mode === 'overwrite') {
          const existingKey = this._firstKeyByName.get(name);
          const def = { type, defaultValue };
          if (propOptions && propOptions.preferredValues) {
            def.preferredValues = deepCopy(propOptions.preferredValues);
          }
          this.componentPropertyDefinitions[existingKey] = def;
          this._nameCounts.set(name, seenCount + 1);
          return existingKey;
        }
        if (mode === 'throw-duplicate') {
          throw new Error(`Duplicate component property name: ${name}`);
        }
        if (mode === 'auto-rename') {
          const renamed = `${name} ${seenCount + 1}`;
          const key = `${renamed}#${this.id}:${++propSeq}`;
          const def = { type, defaultValue };
          if (propOptions && propOptions.preferredValues) {
            def.preferredValues = deepCopy(propOptions.preferredValues);
          }
          this.componentPropertyDefinitions[key] = def;
          this._nameCounts.set(name, seenCount + 1);
          return key;
        }
      }

      const key = `${name}#${this.id}:${++propSeq}`;
      const def = { type, defaultValue };
      if (propOptions && propOptions.preferredValues) {
        def.preferredValues = deepCopy(propOptions.preferredValues);
      }
      this.componentPropertyDefinitions[key] = def;
      this._firstKeyByName.set(name, key);
      this._nameCounts.set(name, seenCount + 1);
      return key;
    }

    editComponentProperty(key, patch) {
      const def = this.componentPropertyDefinitions[key];
      if (!def) throw new Error(`Unknown component property ${key}`);
      if (Object.prototype.hasOwnProperty.call(patch, 'defaultValue')) {
        def.defaultValue = patch.defaultValue;
        for (const variant of this.children) {
          this._applyPropertyToBoundChildren(variant, key, def.type, patch.defaultValue);
        }
        for (const inst of allInstances) {
          if (inst.removed || !inst._main || inst._main.parent !== this) continue;
          if (!inst._overriddenPropKeys.has(key) && inst.componentProperties[key]) {
            inst.componentProperties[key].value = patch.defaultValue;
            this._applyPropertyToBoundChildren(inst, key, def.type, patch.defaultValue);
          }
        }
      }
      if (Object.prototype.hasOwnProperty.call(patch, 'preferredValues')) {
        def.preferredValues = deepCopy(patch.preferredValues);
      }
      return key;
    }

    _applyPropertyToBoundChildren(container, key, type, value) {
      for (const child of container.children) {
        const refs = child.componentPropertyReferences || {};
        if (type === 'TEXT' && refs.characters === key) {
          child.characters = value;
        } else if (type === 'BOOLEAN' && refs.visible === key) {
          child.visible = value;
        } else if (type === 'INSTANCE_SWAP' && refs.mainComponent === key) {
          const nextMain = allComponentsById.get(value);
          if (!nextMain) throw new Error(`Unknown swap component id: ${value}`);
          child.swapComponent(nextMain);
        }
      }
    }

    createInstance() {
      const cloneSubtree = (src, isRoot) => {
        const dst = new MockNode(isRoot ? 'INSTANCE' : src.type, src.name);
        dst.visible = src.visible;
        dst.x = src.x;
        dst.y = src.y;
        dst.width = src.width;
        dst.height = src.height;
        dst.relativeTransform = deepCopy(src.relativeTransform);
        dst.layoutMode = src.layoutMode;
        dst.fills = deepCopy(src.fills);
        dst.strokes = deepCopy(src.strokes);
        dst.cornerRadius = src.cornerRadius;
        dst.paddingTop = src.paddingTop;
        dst.paddingRight = src.paddingRight;
        dst.paddingBottom = src.paddingBottom;
        dst.paddingLeft = src.paddingLeft;
        dst.itemSpacing = src.itemSpacing;
        dst.characters = src.characters;
        dst.fontName = deepCopy(src.fontName);
        dst.fontSize = src.fontSize;
        dst.componentPropertyReferences = deepCopy(src.componentPropertyReferences || {});
        dst.data = { ...src.data };
        if (!isRoot && src.type === 'INSTANCE') {
          dst._main = src._main;
          dst.componentProperties = deepCopy(src.componentProperties || {});
        }
        for (const ch of src.children) {
          dst.appendChild(cloneSubtree(ch, false));
        }
        return dst;
      };
      const inst = cloneSubtree(this, true);
      inst._main = this;
      const owner = this.parent && this.parent.type === 'COMPONENT_SET' ? this.parent : this;
      inst.componentProperties = {};
      for (const [k, def] of Object.entries(owner.componentPropertyDefinitions || {})) {
        inst.componentProperties[k] = { type: def.type, value: def.defaultValue };
      }
      allInstances.add(inst);
      return inst;
    }

    async getMainComponentAsync() {
      return this._main;
    }

    swapComponent(nextMain) {
      this._main = nextMain;
      const savedRefs = deepCopy(this.componentPropertyReferences || {});
      const savedName = this.name;
      const fresh = nextMain.createInstance();
      allInstances.delete(fresh);
      for (const oldChild of [...this.children]) oldChild.parent = null;
      this.children = [];
      for (const newChild of [...fresh.children]) this.appendChild(newChild);
      this.name = savedName;
      this.componentPropertyReferences = savedRefs;
      const owner = nextMain.parent && nextMain.parent.type === 'COMPONENT_SET' ? nextMain.parent : nextMain;
      for (const [k, def] of Object.entries(owner.componentPropertyDefinitions || {})) {
        if (!this.componentProperties[k]) {
          this.componentProperties[k] = { type: def.type, value: def.defaultValue };
        }
      }
    }

    setProperties(values) {
      const owner = this._main && this._main.parent && this._main.parent.type === 'COMPONENT_SET'
        ? this._main.parent
        : this._main;
      for (const [k, v] of Object.entries(values)) {
        if (!this.componentProperties[k]) {
          throw new Error(`Unknown instance property key: ${k}`);
        }
        this._overriddenPropKeys.add(k);
        this.componentProperties[k].value = v;
        if (owner) {
          owner._applyPropertyToBoundChildren(this, k, this.componentProperties[k].type, v);
        }
      }
    }
  }

  const page = new MockNode('PAGE', 'Page 1');
  const radius16 = new MockNode('COMPONENT', 'radius16');
  radius16.cornerRadius = 16;
  page.appendChild(radius16);

  const figma = {
    fileKey: 'file_test_1',
    currentPage: page,
    createFrame: () => new MockNode('FRAME', 'Frame'),
    createComponent: () => new MockNode('COMPONENT', 'Component'),
    createText: () => new MockNode('TEXT', 'Text'),
    combineAsVariants(components, parent) {
      const set = new MockNode('COMPONENT_SET', 'ComponentSet');
      parent.appendChild(set);
      for (const c of components) set.appendChild(c);
      return set;
    },
    async loadFontAsync() {},
  };

  return { figma, page, radius16, removeCalls, descendantRemoveAttempts, MockNode };
}

function createCodeJsRegressionWorld(options = {}) {
  let nodeSeq = 0;
  let propSeq = 0;

  class Node {
    constructor(type) {
      Object.assign(this, {
        id: String(++nodeSeq),
        key: 'comp-key-' + nodeSeq,
        type,
        name: '',
        children: [],
        data: {},
        componentPropertyDefinitions: {},
        visible: true,
        x: 0,
        y: 0,
        width: 320,
        height: 60,
        layoutMode: 'NONE',
        _firstKeyByName: new Map(),
        _nameCounts: new Map(),
      });
    }
    appendChild(node) {
      if (node.parent) node.parent.children = node.parent.children.filter(child => child !== node);
      node.parent = this;
      this.children.push(node);
    }
    remove() {
      this.removed = true;
      if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    }
    findOne(predicate) {
      for (const child of this.children) {
        if (predicate(child)) return child;
        const nested = child.findOne ? child.findOne(predicate) : null;
        if (nested) return nested;
      }
      return null;
    }
    findAll(predicate) {
      const results = [];
      for (const child of this.children) {
        if (predicate(child)) results.push(child);
        if (child.findAll) results.push(...child.findAll(predicate));
      }
      return results;
    }
    resize(w, h) {
      this.width = w;
      this.height = h;
    }
    setPluginData(key, value) {
      this.data[key] = String(value);
    }
    getPluginData(key) {
      return this.data[key] || '';
    }
    addComponentProperty(name, type, defaultValue, propOptions) {
      if (options.returnBrokenKeyForName && name === options.returnBrokenKeyForName) {
        return '';
      }
      const mode = options.duplicateMode || 'unique';
      const seenCount = this._nameCounts.get(name) || 0;
      if (seenCount > 0) {
        if (mode === 'same-key') {
          return this._firstKeyByName.get(name);
        }
        if (mode === 'overwrite') {
          const existingKey = this._firstKeyByName.get(name);
          this.componentPropertyDefinitions[existingKey] = {
            type,
            defaultValue,
            ...(propOptions || {}),
          };
          this._nameCounts.set(name, seenCount + 1);
          return existingKey;
        }
        if (mode === 'throw-duplicate') {
          throw new Error(`Duplicate component property name: ${name}`);
        }
        if (mode === 'auto-rename') {
          const renamed = `${name} ${seenCount + 1}`;
          const key = `${renamed}#${this.id}:${++propSeq}`;
          this.componentPropertyDefinitions[key] = {
            type,
            defaultValue,
            ...(propOptions || {}),
          };
          this._nameCounts.set(name, seenCount + 1);
          return key;
        }
      }
      const key = `${name}#${this.id}:${++propSeq}`;
      this.componentPropertyDefinitions[key] = {
        type,
        defaultValue,
        ...(propOptions || {}),
      };
      this._firstKeyByName.set(name, key);
      this._nameCounts.set(name, seenCount + 1);
      return key;
    }
    editComponentProperty(key, patch) {
      const def = this.componentPropertyDefinitions[key];
      if (!def) throw new Error('unknown key: ' + key);
      if (Object.prototype.hasOwnProperty.call(patch, 'defaultValue')) {
        def.defaultValue = patch.defaultValue;
      }
      if (Object.prototype.hasOwnProperty.call(patch, 'preferredValues')) {
        def.preferredValues = deepCopy(patch.preferredValues);
      }
      return key;
    }
    createInstance() {
      const clone = sourceNode => {
        const result = new Node(sourceNode === this ? 'INSTANCE' : sourceNode.type);
        result.characters = sourceNode.characters;
        result.name = sourceNode.name;
        result.visible = sourceNode.visible;
        result.layoutMode = sourceNode.layoutMode;
        result.componentPropertyReferences = { ...(sourceNode.componentPropertyReferences || {}) };
        result.data = { ...sourceNode.data };
        if (sourceNode.main) result.main = sourceNode.main;
        for (const child of sourceNode.children) result.appendChild(clone(child));
        return result;
      };
      const instance = clone(this);
      instance.main = this;
      const owner = this.parent?.type === 'COMPONENT_SET' ? this.parent : this;
      instance.componentProperties = Object.fromEntries(
        Object.entries(owner.componentPropertyDefinitions).map(([key, prop]) => [
          key,
          { type: prop.type, value: prop.defaultValue },
        ])
      );
      return instance;
    }
    async getMainComponentAsync() {
      return this.main;
    }
    getRangeHyperlink() {
      return null;
    }
    setProperties(values) {
      for (const [key, value] of Object.entries(values)) {
        if (!this.componentProperties[key]) throw new Error('unknown native key: ' + key);
        this.componentProperties[key].value = value;
        const apply = child => {
          for (const [field, refKey] of Object.entries(child.componentPropertyReferences || {})) {
            if (refKey === key) {
              if (field === 'mainComponent') {
                const targetMain = [...context.authored.components.values()].find(m => m.id === value);
                if (!targetMain) throw new Error('unknown swap main id: ' + value);
                child.main = targetMain;
                child.children = targetMain.createInstance().children;
              } else {
                child[field] = value;
              }
            }
          }
          for (const grandChild of child.children) apply(grandChild);
        };
        for (const child of this.children) apply(child);
      }
    }
  }

  const customPayload = deepCopy(compiledDesignPayload);
  if (options.mutatePayload) options.mutatePayload(customPayload);

  const page = new Node('PAGE');
  page.setPluginData(
    'figmaFlow',
    JSON.stringify({ semantic_id: 'design-import', bridge: 1, source_sha256: 'a'.repeat(64), complete: true })
  );
  const library = new Node('FRAME');
  page.appendChild(library);
  library.setPluginData('figmaFlow', JSON.stringify({ semantic_id: 'component-library' }));
  library.setPluginData('semanticKey', 'component-library');

  const figma = {
    showUI() {},
    ui: {},
    createComponent: () => new Node('COMPONENT'),
    createFrame: () => new Node('FRAME'),
    createText: () => new Node('TEXT'),
    combineAsVariants(mains, parent) {
      const set = new Node('COMPONENT_SET');
      parent.appendChild(set);
      for (const main of mains) set.appendChild(main);
      return set;
    },
  };

  const context = vm.createContext({
    figma,
    __html__: '',
    PAYLOAD: customPayload,
    library,
    variables: new Map(),
    warnings: new Set(),
    fonts: new Map(),
  });
  vm.runInContext(codeRuntime, context);
  Object.assign(context, {
    layout(node, width) {
      node.width = width;
      node.layoutMode = 'VERTICAL';
    },
    text(value) {
      const t = new Node('TEXT');
      t.characters = value;
      return t;
    },
    applyProps() {},
    decorate: async () => {},
  });

  return { context, page, library, figma, Node };
}

async function runCodeJsAuthor(env) {
  const { context, page, Node } = env;
  vm.runInContext('validateDeclaredComponentProperties(PAYLOAD)', context);
  const start = codeRuntime.indexOf('    const components = new Map();');
  const end = codeRuntime.indexOf('    layoutFoundationSets(library, componentSets);', start);
  context.authored = await vm.runInContext(
    '(async()=>{' + codeRuntime.slice(start, end) + ';return {components,componentSets};})()',
    context
  );
  const { components } = context.authored;
  for (const screen of context.PAYLOAD.screens) {
    const frame = new Node('FRAME');
    page.appendChild(frame);
    frame.name = `${screen.id} · ${screen.title}`;
    context.frame = frame;
    context.screenId = screen.id;
    vm.runInContext('metadata(frame, screenId, {kind:"screen"})', context);
    for (const [index, element] of screen.elements.entries()) {
      const identity = element.id || `${screen.id}/element:${index}`;
      const main = components.get(JSON.stringify([element.component, element.variant]));
      const instance = main.createInstance();
      frame.appendChild(instance);
      instance.name = element.text;
      const primaryLabel = instance.children.find(c => c.type === 'TEXT' && !c.name?.startsWith('text:'));
      const labelKey = JSON.parse(main.getPluginData('figmaFlow') || '{}').label_property_key;
      const hasExplicitLabelOverride = Object.entries(context.PAYLOAD.components[element.component]?.properties || {}).some(
        ([pid, p]) => p.type === 'TEXT' && p.target === 'label' && Object.prototype.hasOwnProperty.call(element.property_values || {}, pid)
      );
      if (labelKey && !hasExplicitLabelOverride) {
        instance.setProperties({ [labelKey]: element.text });
      }
      context.instance = instance;
      context.main = main;
      context.element = { ...element, id: identity };
      context.components = components;
      context.identity = identity;
      context.primaryLabel = primaryLabel;
      await vm.runInContext(
        '(async()=>{await applyDeclaredInstanceProperties(instance, main, element, components); if(primaryLabel) metadata(primaryLabel, identity+"/label"); metadata(instance, identity, {kind:"component"});})()',
        context
      );
    }
  }
  return context.authored;
}

for (const mode of ['same-key', 'overwrite', 'auto-rename', 'throw-duplicate']) {
  test(`semantic_components.js handles duplicate Cell display name under real-Figma ${mode} mode with 6-family/8-instance graph and preserves overrides`, async () => {
    const { figma, page, radius16 } = createSemanticRegressionWorld({ duplicateMode: mode });
    const contract = deepCopy(examplesDesignContract);

    const created = await ensureSemanticComponents(figma, page, contract);
    assert.equal(created.status, 'created');
    assert.equal(created.componentSets.length, 6);
    assert.equal(created.instances.length, 8);
    assert.equal(radius16.removed, false);

    const rowSet = created.componentSets.find(s => s.family === 'table-row');
    const rowProps = new Map(rowSet.propertyMappings.map(p => [p.id, p]));
    assert.equal(rowProps.get('firstCell').name, 'Cell', 'authored display label preserved in metadata');
    assert.equal(rowProps.get('secondCell').name, 'Cell', 'authored display label preserved in metadata');
    assert.notEqual(rowProps.get('firstCell').actualKey, rowProps.get('secondCell').actualKey);
    assert.match(rowProps.get('firstCell').actualKey, /^[^#]+#[^#]+$/);
    assert.match(rowProps.get('secondCell').actualKey, /^[^#]+#[^#]+$/);

    // Unique display names stay exact
    assert.match(rowProps.get('showSecondCell').actualKey, /^Show optional column#/);
    const fieldSet = created.componentSets.find(s => s.family === 'field');
    const fieldProps = new Map(fieldSet.propertyMappings.map(p => [p.id, p]));
    assert.match(fieldProps.get('label').actualKey, /^Label#/);
    assert.match(fieldProps.get('helpText').actualKey, /^Help#/);
    assert.match(fieldProps.get('showHelp').actualKey, /^Show help#/);
    assert.match(fieldProps.get('control').actualKey, /^Control#/);

    // Live instance TEXT/BOOLEAN/INSTANCE_SWAP overrides preserved across repeat apply
    const participantInst = created.instances.find(i => i.elementId === 'form-participant-field');
    const participantNode = page.findOne(n => n.id === participantInst.id);
    const checkboxCheckedId = created.componentSets
      .find(s => s.family === 'checkbox')
      .variants.find(v => v.key.endsWith('/checked')).id;
    participantNode.setProperties({
      [fieldProps.get('label').actualKey]: 'Updated participant label',
      [fieldProps.get('showHelp').actualKey]: false,
      [fieldProps.get('control').actualKey]: checkboxCheckedId,
    });

    const repeat = await ensureSemanticComponents(figma, page, contract);
    assert.equal(repeat.status, 'unchanged');
    assert.deepEqual(repeat.componentSets, created.componentSets);
    assert.equal(repeat.preservedOverrides.length, 3);

    const readback = await readSemanticComponentFamilies(figma, page, contract);
    assert.equal(readback.status, 'present');
    const rowInst = readback.instances.find(i => i.elementId === 'roster-row-1');
    assert(rowInst, 'expected roster-row-1 instance in readback');
    assert.equal(rowInst.resolvedProperties.firstCell.actualKey, rowProps.get('firstCell').actualKey);
    assert.equal(rowInst.resolvedProperties.secondCell.actualKey, rowProps.get('secondCell').actualKey);
  });

  test(`code.js handles duplicate Cell display name under real-Figma ${mode} mode and preserves overrides`, async () => {
    const env = createCodeJsRegressionWorld({ duplicateMode: mode });
    const { components } = await runCodeJsAuthor(env);

    const rowMain = components.get(JSON.stringify(['table-row', 'default']));
    const rowMeta = JSON.parse(rowMain.getPluginData('figmaFlow'));
    assert.equal(rowMeta.declared_property_contracts.firstCell.name, 'Cell');
    assert.equal(rowMeta.declared_property_contracts.secondCell.name, 'Cell');
    assert.notEqual(
      rowMeta.declared_property_keys.firstCell,
      rowMeta.declared_property_keys.secondCell
    );
    assert.match(rowMeta.declared_property_keys.showSecondCell, /^Show optional column#/);

    const fieldMain = components.get(JSON.stringify(['field', 'default']));
    const fieldKeys = JSON.parse(fieldMain.getPluginData('figmaFlow')).declared_property_keys;
    assert.match(fieldKeys.label, /^Label#/);
    assert.match(fieldKeys.helpText, /^Help#/);
    assert.match(fieldKeys.showHelp, /^Show help#/);
    assert.match(fieldKeys.control, /^Control#/);

    env.context.page = env.page;
    env.context.observed = await vm.runInContext('snapshot(page)', env.context);
    vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD, observed)', env.context);

    // Preserve user TEXT/BOOLEAN/INSTANCE_SWAP overrides across reapplyDeclaredComponents
    const screenFrame = env.page.children.find(
      n => n.getPluginData('semanticKey') === env.context.PAYLOAD.screens[0].id
    );
    const fieldInst = screenFrame.children[0];
    const checkedMain = components.get(JSON.stringify(['checkbox', 'checked']));
    fieldInst.setProperties({
      [fieldKeys.label]: 'Live user label',
      [fieldKeys.showHelp]: false,
      [fieldKeys.control]: checkedMain.id,
    });
    const reapply = await vm.runInContext(
      'reapplyDeclaredComponents(page, PAYLOAD, {preserveInstanceOverrides: true})',
      env.context
    );
    assert.equal(reapply.createdInstanceIds.length, 0);
    assert.equal(fieldInst.componentProperties[fieldKeys.label].value, 'Live user label');
    assert.equal(fieldInst.componentProperties[fieldKeys.showHelp].value, false);
    assert.equal(fieldInst.componentProperties[fieldKeys.control].value, checkedMain.id);
  });
}

test('semantic_components.js collision-safe disambiguation preserves unique property whose authored name matches fallback grammar and protects overwritten distinct defaults', async () => {
  const { figma, page } = createSemanticRegressionWorld({ duplicateMode: 'overwrite' });
  const contract = deepCopy(examplesDesignContract);
  const rowSet = contract.componentSets.find(s => s.family === 'table-row');
  rowSet.properties[1].defaultValue = {
    setId: `${contract.ownerKey}/set:table-cell`,
    variantKey: `${contract.ownerKey}/variant:table-cell/header`,
  };
  rowSet.properties.push({
    id: 'explicitCollision',
    name: 'Cell (secondCell)',
    type: 'BOOLEAN',
    targetKey: 'cell-0',
    defaultValue: true,
  });

  const created = await ensureSemanticComponents(figma, page, contract);
  assert.equal(created.status, 'created');
  const createdRow = created.componentSets.find(s => s.family === 'table-row');
  const props = new Map(createdRow.propertyMappings.map(p => [p.id, p]));
  assert.match(props.get('explicitCollision').actualKey, /^Cell \(secondCell\)#/);
  assert.equal(props.get('firstCell').defaultValue.variantKey, `${contract.ownerKey}/variant:table-cell/default`);
  assert.equal(props.get('secondCell').defaultValue.variantKey, `${contract.ownerKey}/variant:table-cell/header`);
  assert.notEqual(props.get('firstCell').actualKey, props.get('secondCell').actualKey);
  assert.notEqual(props.get('secondCell').actualKey, props.get('explicitCollision').actualKey);
});

test('semantic_components.js rollback removes ONLY created top-level owner node when protected descendants deny remove, leaving original COMPONENT radius16 intact', async () => {
  const { figma, page, radius16, removeCalls, descendantRemoveAttempts } = createSemanticRegressionWorld({
    denyDescendantRemove: true,
    failAddPropertyName: 'Show optional column',
  });
  const contract = deepCopy(examplesDesignContract);

  let caught = null;
  try {
    await ensureSemanticComponents(figma, page, contract);
  } catch (err) {
    caught = err;
  }
  assert(caught, 'expected apply to fail');
  assert.match(caught.message, /Simulated failure adding property Show optional column/);
  assert.doesNotMatch(caught.message, /rollback incomplete/);
  assert.doesNotMatch(caught.message, /Removing this node is not allowed/);

  assert.equal(descendantRemoveAttempts.length, 0, 'protected nested descendants must never have remove() called');
  assert.equal(removeCalls.length, 1, 'only created top-level owned workbench root should be removed');
  assert.equal(removeCalls[0].name, contract.workbench.name);
  assert.deepEqual(page.children, [radius16]);
  assert.equal(radius16.removed, false);
  assert.equal(radius16.cornerRadius, 16);
});

test('semantic_components.js repeat-apply rollback removes only newly created top-level set/instance when protected descendants deny remove', async () => {
  const world = createSemanticRegressionWorld({ denyDescendantRemove: true });
  const v1 = deepCopy(examplesDesignContract);
  // Omit table-row on v1, then add table-row in v2 and fail on Show optional column
  v1.componentSets = v1.componentSets.filter(s => s.family !== 'table-row');
  v1.instances = v1.instances.filter(i => i.setId !== `${v1.ownerKey}/set:table-row`);

  const first = await ensureSemanticComponents(world.figma, world.page, v1);
  assert.equal(first.status, 'created');
  assert.equal(world.removeCalls.length, 0);

  // Inject failure during v2 additive set creation
  const v2World = world;
  const origAdd = v2World.MockNode.prototype.addComponentProperty;
  v2World.MockNode.prototype.addComponentProperty = function (name, type, defaultValue, opts) {
    if (name === 'Show optional column') {
      throw new Error('Simulated failure adding property Show optional column');
    }
    return origAdd.call(this, name, type, defaultValue, opts);
  };

  let caught = null;
  try {
    await ensureSemanticComponents(v2World.figma, v2World.page, examplesDesignContract);
  } catch (err) {
    caught = err;
  } finally {
    v2World.MockNode.prototype.addComponentProperty = origAdd;
  }
  assert(caught);
  assert.match(caught.message, /Simulated failure adding property Show optional column/);
  assert.doesNotMatch(caught.message, /rollback incomplete/);
  assert.equal(v2World.descendantRemoveAttempts.length, 0);
  assert.equal(v2World.removeCalls.length, 1, 'only newly created top-level COMPONENT_SET should be removed');
  assert.equal(v2World.removeCalls[0].type, 'COMPONENT_SET');
  assert.equal(v2World.radius16.removed, false);
});

test('retention error diagnostics include safe nativeName, actualKey, status, and defCount on genuine non-retention', async () => {
  const { figma, page } = createSemanticRegressionWorld({ returnBrokenKeyForName: 'Value' });
  await assert.rejects(
    () => ensureSemanticComponents(figma, page, deepCopy(examplesDesignContract)),
    err => {
      assert.match(err.message, /Native component property declaration was not retained for/);
      assert.match(err.message, /nativeName=Value/);
      assert.match(err.message, /actualKey=none/);
      assert.match(err.message, /status=actual-key-missing/);
      assert.match(err.message, /defCount=0/);
      return true;
    }
  );

  const env = createCodeJsRegressionWorld({ returnBrokenKeyForName: 'Value' });
  await assert.rejects(
    () => runCodeJsAuthor(env),
    err => {
      assert.match(err.message, /Native declaration was not retained: value/);
      assert.match(err.message, /nativeName=Value/);
      assert.match(err.message, /actualKey=none/);
      assert.match(err.message, /status=actual-key-missing/);
      assert.match(err.message, /defCount=0/);
      return true;
    }
  );
});
