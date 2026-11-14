const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const {
  ensureSemanticComponents,
  readSemanticComponentFamilies
} = require('../figma-bridge/semantic_components.js');
const { checkSupportedWidthReuse } = require('./semantic_component_reuse_oracle.cjs');

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

function createMockFigmaWorld(options = {}) {
  let nodeSeq = 0;
  let propSeq = 0;
  const allComponentsById = new Map();
  const allInstances = new Set();

  class MockNode {
    constructor(type, name = type) {
      this.id = `${ ++nodeSeq }:${ type.slice(0, 2).toLowerCase() }`;
      if (type === 'COMPONENT') {
        this.key = `comp_key_${ nodeSeq }`;
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
        throw new Error(`Simulated failure adding property ${ name }`);
      }
      const key = `${ name }#${ this.id }:${ ++propSeq }`;
      const def = { type, defaultValue };
      if (propOptions && propOptions.preferredValues) {
        def.preferredValues = deepCopy(propOptions.preferredValues);
      }
      this.componentPropertyDefinitions[key] = def;
      return key;
    }

    editComponentProperty(key, patch) {
      if (options.disableEditComponentProperty) {
        throw new Error('editComponentProperty disabled');
      }
      const def = this.componentPropertyDefinitions[key];
      if (!def) throw new Error(`Unknown component property ${ key }`);
      if (Object.prototype.hasOwnProperty.call(patch, 'name') && patch.name !== undefined) {
        throw new Error('Renaming property suffix not expected');
      }
      if (Object.prototype.hasOwnProperty.call(patch, 'defaultValue')) {
        def.defaultValue = patch.defaultValue;
        // Update variant children bound to key
        for (const variant of this.children) {
          this._applyPropertyToBoundChildren(variant, key, def.type, patch.defaultValue);
        }
        // Propagate ONLY to live instances of this set that have NOT overridden key!
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
          if (!nextMain) throw new Error(`Unknown swap component id: ${ value }`);
          child.swapComponent(nextMain);
        }
      }
    }

    createInstance() {
      if (this.type !== 'COMPONENT') {
        throw new Error('createInstance is only valid on COMPONENT');
      }
      if (options.failOnInstanceNumber && allInstances.size + 1 === options.failOnInstanceNumber) {
        throw new Error(`Simulated failure creating instance #${ options.failOnInstanceNumber }`);
      }
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
        inst.componentProperties[k] = {
          type: def.type,
          value: def.defaultValue
        };
      }
      allInstances.add(inst);
      return inst;
    }

    async getMainComponentAsync() {
      return this._main;
    }

    swapComponent(nextMain) {
      if (!nextMain || nextMain.type !== 'COMPONENT') {
        throw new Error('swapComponent requires a COMPONENT node');
      }
      this._main = nextMain;
      // Rebuild sub-children if this is a nested slot swapped across families while preserving outer references
      const savedRefs = deepCopy(this.componentPropertyReferences || {});
      const savedName = this.name;
      const fresh = nextMain.createInstance();
      allInstances.delete(fresh);
      for (const oldChild of [...this.children]) oldChild.remove();
      for (const newChild of [...fresh.children]) this.appendChild(newChild);
      this.name = savedName;
      this.componentPropertyReferences = savedRefs;
      const owner = nextMain.parent && nextMain.parent.type === 'COMPONENT_SET' ? nextMain.parent : nextMain;
      for (const [k, def] of Object.entries(owner.componentPropertyDefinitions || {})) {
        if (!this.componentProperties[k]) {
          this.componentProperties[k] = { type: def.type, value: def.defaultValue };
        }
      }
      // Re-apply existing overridden properties on this instance to rebuilt children
      for (const k of this._overriddenPropKeys) {
        const entry = this.componentProperties[k];
        if (entry && owner.componentPropertyDefinitions[k]) {
          owner._applyPropertyToBoundChildren(this, k, entry.type, entry.value);
        }
      }
    }

    setProperties(values) {
      if (options.failOnSetPropertiesCall) {
        options.setPropertiesCount = (options.setPropertiesCount || 0) + 1;
        if (options.setPropertiesCount === options.failOnSetPropertiesCall) {
          throw new Error('Simulated failure during instance.setProperties');
        }
      }
      const owner = this._main && this._main.parent && this._main.parent.type === 'COMPONENT_SET'
        ? this._main.parent
        : this._main;
      for (const [k, v] of Object.entries(values)) {
        if (!this.componentProperties[k]) {
          throw new Error(`Unknown instance property key: ${ k }`);
        }
        this._overriddenPropKeys.add(k);
        this.componentProperties[k].value = v;
        if (owner) {
          owner._applyPropertyToBoundChildren(this, k, this.componentProperties[k].type, v);
        }
      }
    }
  }

  if (options.omitEditComponentProperty) {
    delete MockNode.prototype.editComponentProperty;
  }

  const root = new MockNode('DOCUMENT', 'Document');
  const page = new MockNode('PAGE', 'Current Page');
  const otherPage = new MockNode('PAGE', 'Unrelated Sibling Page');
  root.appendChild(page);
  root.appendChild(otherPage);

  // Add pre-existing sibling nodes on both pages to prove untouched sibling/page preservation
  const existingHero = new MockNode('FRAME', 'Existing Hero Banner');
  existingHero.x = 40;
  existingHero.y = 60;
  existingHero.resize(960, 320);
  existingHero.relativeTransform = [[1, 0, 40], [0, 1, 60]];
  existingHero.setPluginData('semanticKey', 'existing.hero.banner');
  const heroTitle = new MockNode('TEXT', 'Hero Title');
  heroTitle.characters = 'Keep existing product canvas intact';
  existingHero.appendChild(heroTitle);
  page.appendChild(existingHero);

  const otherPageFrame = new MockNode('FRAME', 'Other Page Frame');
  otherPageFrame.x = 12;
  otherPageFrame.y = 24;
  otherPageFrame.setPluginData('semanticKey', 'other.page.frame');
  otherPage.appendChild(otherPageFrame);

  const loadedFonts = [];
  const figma = {
    fileKey: options.fileKey || 'test_local_file_key',
    root,
    currentPage: page,
    loadedFonts,
    async loadFontAsync(font) {
      loadedFonts.push(deepCopy(font));
    },
    createFrame() {
      return new MockNode('FRAME', 'Frame');
    },
    createText() {
      return new MockNode('TEXT', 'Text');
    },
    createComponent() {
      return new MockNode('COMPONENT', 'Component');
    },
    createComponentFromNode(node) {
      node.type = 'COMPONENT';
      node.key = `comp_key_${ ++nodeSeq }`;
      allComponentsById.set(node.id, node);
      return node;
    },
    combineAsVariants(components, parent) {
      const set = new MockNode('COMPONENT_SET', 'ComponentSet');
      parent.appendChild(set);
      for (const comp of components) {
        set.appendChild(comp);
      }
      return set;
    }
  };

  const snapshotTree = node => ({
    id: node.id,
    type: node.type,
    name: node.name,
    x: node.x,
    y: node.y,
    width: node.width,
    height: node.height,
    visible: node.visible,
    characters: node.characters,
    relativeTransform: deepCopy(node.relativeTransform),
    data: deepCopy(node.data),
    children: node.children.map(snapshotTree)
  });

  return {
    figma,
    page,
    otherPage,
    existingHero,
    otherPageFrame,
    MockNode,
    snapshotTree
  };
}

function buildSixFamiliesContract(ownerKey = 'nf01.component-families') {
  const baseStyle = {
    background: { r: 1, g: 1, b: 1, a: 1 },
    color: { r: 0.1216, g: 0.1412, b: 0.1686, a: 1 },
    borderColor: { r: 0.7804, g: 0.8039, b: 0.8314, a: 1 },
    paddingTop: 8,
    paddingRight: 8,
    paddingBottom: 8,
    paddingLeft: 8,
    itemSpacing: 8,
    cornerRadius: 4,
    fontFamily: 'Arial',
    fontSize: 14
  };
  const variant = (fid, name, overrides = {}) => ({
    key: `${ ownerKey }/variant:${ fid }/${ name }`,
    variant: name,
    props: { state: name },
    style: { ...baseStyle, ...overrides },
    defaultLabel: fid
  });

  return {
    schema: 'figma-flow-semantic-family-contract-v1',
    version: 1,
    mode: 'additive-family-workbench',
    ownerKey,
    workbench: {
      frameKey: `${ ownerKey }/workbench`,
      libraryKey: `${ ownerKey }/library`,
      instancesFrameKey: `${ ownerKey }/instances`,
      name: 'NF-01 · Component families workbench',
      position: { x: 1680, y: 0 },
      font: { family: 'Arial', style: 'Regular' }
    },
    componentSets: [
      {
        id: `${ ownerKey }/set:input`,
        family: 'input',
        component: 'input',
        name: 'Input',
        layout: 'HORIZONTAL',
        axes: { state: ['default', 'focus', 'error', 'disabled'] },
        swapTargets: [],
        variants: [
          variant('input', 'default'),
          variant('input', 'focus'),
          variant('input', 'error'),
          variant('input', 'disabled')
        ],
        properties: [
          {
            id: 'value',
            name: 'Value',
            type: 'TEXT',
            targetKey: 'label',
            defaultValue: 'Sample input'
          }
        ]
      },
      {
        id: `${ ownerKey }/set:checkbox`,
        family: 'checkbox',
        component: 'checkbox',
        name: 'Checkbox',
        layout: 'HORIZONTAL',
        axes: { state: ['unchecked', 'checked', 'disabled'] },
        swapTargets: [],
        variants: [
          variant('checkbox', 'unchecked'),
          variant('checkbox', 'checked'),
          variant('checkbox', 'disabled')
        ],
        properties: [
          {
            id: 'optionLabel',
            name: 'Label',
            type: 'TEXT',
            targetKey: 'label',
            defaultValue: 'Agree to workshop guide'
          }
        ]
      },
      {
        id: `${ ownerKey }/set:radio`,
        family: 'radio',
        component: 'radio',
        name: 'Radio',
        layout: 'HORIZONTAL',
        axes: { state: ['unselected', 'selected', 'disabled'] },
        swapTargets: [],
        variants: [
          variant('radio', 'unselected'),
          variant('radio', 'selected'),
          variant('radio', 'disabled')
        ],
        properties: [
          {
            id: 'choiceLabel',
            name: 'Label',
            type: 'TEXT',
            targetKey: 'label',
            defaultValue: 'Morning session'
          }
        ]
      },
      {
        id: `${ ownerKey }/set:field`,
        family: 'field',
        component: 'field',
        name: 'Field',
        layout: 'VERTICAL',
        axes: { state: ['default', 'error', 'disabled'] },
        swapTargets: [
          `${ ownerKey }/set:input`,
          `${ ownerKey }/set:checkbox`,
          `${ ownerKey }/set:radio`
        ],
        variants: [
          variant('field', 'default', { itemSpacing: 4, cornerRadius: 0 }),
          variant('field', 'error', { itemSpacing: 4, cornerRadius: 0 }),
          variant('field', 'disabled', { itemSpacing: 4, cornerRadius: 0 })
        ],
        properties: [
          {
            id: 'label',
            name: 'Copy',
            type: 'TEXT',
            targetKey: 'field-label',
            defaultValue: 'Participant name'
          },
          {
            // Intentionally uses the exact same display name 'Copy' as 'label' to verify duplicate TEXT name disambiguation!
            id: 'helpText',
            name: 'Copy',
            type: 'TEXT',
            targetKey: 'field-help',
            defaultValue: 'Use the name shown on booking confirmation.'
          },
          {
            id: 'showHelp',
            name: 'Show help',
            type: 'BOOLEAN',
            targetKey: 'field-help',
            defaultValue: true
          },
          {
            id: 'control',
            name: 'Control',
            type: 'INSTANCE_SWAP',
            targetKey: 'field-control',
            allowedSetIds: [
              `${ ownerKey }/set:input`,
              `${ ownerKey }/set:checkbox`,
              `${ ownerKey }/set:radio`
            ],
            defaultValue: {
              setId: `${ ownerKey }/set:input`,
              variantKey: `${ ownerKey }/variant:input/default`
            },
            preferredValues: [
              { setId: `${ ownerKey }/set:input`, variantKey: `${ ownerKey }/variant:input/default` },
              { setId: `${ ownerKey }/set:checkbox`, variantKey: `${ ownerKey }/variant:checkbox/unchecked` },
              { setId: `${ ownerKey }/set:radio`, variantKey: `${ ownerKey }/variant:radio/unselected` }
            ]
          }
        ]
      },
      {
        id: `${ ownerKey }/set:table-cell`,
        family: 'table-cell',
        component: 'table-cell',
        name: 'TableCell',
        layout: 'HORIZONTAL',
        axes: { state: ['default', 'header', 'selected', 'muted'] },
        swapTargets: [],
        variants: [
          variant('table-cell', 'default'),
          variant('table-cell', 'header'),
          variant('table-cell', 'selected'),
          variant('table-cell', 'muted')
        ],
        properties: [
          {
            id: 'cellText',
            name: 'Cell text',
            type: 'TEXT',
            targetKey: 'label',
            defaultValue: 'Sample cell'
          }
        ]
      },
      {
        id: `${ ownerKey }/set:table-row`,
        family: 'table-row',
        component: 'table-row',
        name: 'TableRow',
        layout: 'HORIZONTAL',
        axes: { state: ['default', 'selected'] },
        swapTargets: [`${ ownerKey }/set:table-cell`],
        variants: [
          variant('table-row', 'default'),
          variant('table-row', 'selected')
        ],
        properties: [
          {
            id: 'firstCell',
            name: 'Cell',
            type: 'INSTANCE_SWAP',
            targetKey: 'cell-0',
            allowedSetIds: [`${ ownerKey }/set:table-cell`],
            defaultValue: {
              setId: `${ ownerKey }/set:table-cell`,
              variantKey: `${ ownerKey }/variant:table-cell/default`
            },
            preferredValues: [
              { setId: `${ ownerKey }/set:table-cell`, variantKey: `${ ownerKey }/variant:table-cell/default` },
              { setId: `${ ownerKey }/set:table-cell`, variantKey: `${ ownerKey }/variant:table-cell/header` }
            ]
          },
          {
            // Intentionally uses the exact same display name 'Cell' as 'firstCell' to verify duplicate INSTANCE_SWAP name disambiguation!
            id: 'secondCell',
            name: 'Cell',
            type: 'INSTANCE_SWAP',
            targetKey: 'cell-1',
            allowedSetIds: [`${ ownerKey }/set:table-cell`],
            defaultValue: {
              setId: `${ ownerKey }/set:table-cell`,
              variantKey: `${ ownerKey }/variant:table-cell/default`
            },
            preferredValues: [
              { setId: `${ ownerKey }/set:table-cell`, variantKey: `${ ownerKey }/variant:table-cell/default` },
              { setId: `${ ownerKey }/set:table-cell`, variantKey: `${ ownerKey }/variant:table-cell/header` }
            ]
          },
          {
            id: 'showSecondCell',
            name: 'Show optional column',
            type: 'BOOLEAN',
            targetKey: 'cell-1',
            defaultValue: true
          }
        ]
      }
    ],
    instances: [
      {
        key: `${ ownerKey }/instance:form-default-field`,
        elementId: 'form-default-field',
        setId: `${ ownerKey }/set:field`,
        variantKey: `${ ownerKey }/variant:field/default`,
        name: 'Default inherited field',
        text: 'Participant name',
        propertyValues: {}
      },
      {
        key: `${ ownerKey }/instance:form-consent-field`,
        elementId: 'form-consent-field',
        setId: `${ ownerKey }/set:field`,
        variantKey: `${ ownerKey }/variant:field/error`,
        name: 'Safety notice',
        text: 'Safety notice',
        propertyValues: {
          label: 'Safety notice',
          helpText: 'Please confirm before reserving.',
          showHelp: true,
          control: {
            setId: `${ ownerKey }/set:checkbox`,
            variantKey: `${ ownerKey }/variant:checkbox/checked`
          }
        }
      },
      {
        key: `${ ownerKey }/instance:radio-morning`,
        elementId: 'radio-morning',
        setId: `${ ownerKey }/set:radio`,
        variantKey: `${ ownerKey }/variant:radio/selected`,
        name: 'Morning session',
        text: 'Morning session',
        propertyValues: {
          choiceLabel: 'Morning session'
        }
      },
      {
        key: `${ ownerKey }/instance:roster-row-1`,
        elementId: 'roster-row-1',
        setId: `${ ownerKey }/set:table-row`,
        variantKey: `${ ownerKey }/variant:table-row/selected`,
        name: 'Mina Park / Confirmed',
        text: 'Mina Park / Confirmed',
        propertyValues: {
          firstCell: {
            setId: `${ ownerKey }/set:table-cell`,
            variantKey: `${ ownerKey }/variant:table-cell/header`
          },
          secondCell: {
            setId: `${ ownerKey }/set:table-cell`,
            variantKey: `${ ownerKey }/variant:table-cell/muted`
          },
          showSecondCell: false
        }
      }
    ]
  };
}

test('legacy pre-existing frame conversion branch remains unchanged', async () => {
  await checkSupportedWidthReuse();
});

test('six canonical families, three property mappings, duplicate display-name disambiguation, and pure readback', async () => {
  const { figma, page, otherPage, existingHero, otherPageFrame, snapshotTree } = createMockFigmaWorld();
  const heroBefore = snapshotTree(existingHero);
  const otherPageBefore = snapshotTree(otherPage);
  const contract = buildSixFamiliesContract();

  const absentReadback = await readSemanticComponentFamilies(figma, page, contract);
  assert.equal(absentReadback.schema, 'figma-flow-semantic-family-readback-v1');
  assert.equal(absentReadback.status, 'absent');
  assert.equal(absentReadback.workbenchFrameId, null);
  assert.equal(page.children.length, 1, 'readSemanticComponentFamilies must never mutate an absent page');

  const created = await ensureSemanticComponents(figma, page, contract);
  assert.equal(created.schema, 'figma-flow-semantic-family-result-v1');
  assert.equal(created.status, 'created');
  assert.equal(created.componentSets.length, 6);
  assert.equal(created.instances.length, 4);
  assert.deepEqual(snapshotTree(existingHero), heroBefore, 'existing page sibling must remain untouched');
  assert.deepEqual(snapshotTree(otherPage), otherPageBefore, 'other page must remain untouched');
  assert.equal(otherPage.children[0], otherPageFrame);

  const setsByFamily = new Map(created.componentSets.map(s => [s.family, s]));
  assert.equal(setsByFamily.get('field').layout, 'VERTICAL');
  assert.equal(setsByFamily.get('input').layout, 'HORIZONTAL');
  assert.equal(setsByFamily.get('checkbox').layout, 'HORIZONTAL');
  assert.equal(setsByFamily.get('radio').layout, 'HORIZONTAL');
  assert.equal(setsByFamily.get('table-row').layout, 'HORIZONTAL');
  assert.equal(setsByFamily.get('table-cell').layout, 'HORIZONTAL');

  // Verify duplicate TEXT display names ('Copy' on label and helpText) get distinct #suffix keys
  const fieldProps = new Map(setsByFamily.get('field').propertyMappings.map(p => [p.id, p]));
  assert.match(fieldProps.get('label').actualKey, /^Copy#/);
  assert.match(fieldProps.get('helpText').actualKey, /^Copy#/);
  assert.notEqual(fieldProps.get('label').actualKey, fieldProps.get('helpText').actualKey);
  assert.equal(fieldProps.get('label').referenceField, 'characters');
  assert.equal(fieldProps.get('helpText').referenceField, 'characters');
  assert.equal(fieldProps.get('showHelp').referenceField, 'visible');
  assert.equal(fieldProps.get('control').referenceField, 'mainComponent');
  assert.equal(
    fieldProps.get('label').targetSemanticKey,
    'component.nf01.component-families/variant:field/default/text:field-label'
  );
  assert.equal(
    fieldProps.get('control').targetSemanticKey,
    'component.nf01.component-families/variant:field/default/slot:field-control'
  );

  // Verify duplicate INSTANCE_SWAP display names ('Cell' on firstCell and secondCell) get distinct #suffix keys
  const rowProps = new Map(setsByFamily.get('table-row').propertyMappings.map(p => [p.id, p]));
  assert.match(rowProps.get('firstCell').actualKey, /^Cell#/);
  assert.match(rowProps.get('secondCell').actualKey, /^Cell#/);
  assert.notEqual(rowProps.get('firstCell').actualKey, rowProps.get('secondCell').actualKey);
  assert.equal(rowProps.get('showSecondCell').referenceField, 'visible');

  // Pure readback matches live getters without mutation
  const readback = await readSemanticComponentFamilies(figma, page, contract);
  assert.equal(readback.status, 'present');
  assert.equal(readback.workbenchFrameId, created.workbenchFrameId);
  assert.deepEqual(readback.componentSets, created.componentSets);
  assert.deepEqual(readback.instances, created.instances);

  const instByKey = new Map(readback.instances.map(i => [i.key, i]));
  const consent = instByKey.get('nf01.component-families/instance:form-consent-field');
  assert.equal(consent.resolvedProperties.label.characters, 'Safety notice');
  assert.equal(consent.resolvedProperties.helpText.characters, 'Please confirm before reserving.');
  assert.equal(consent.resolvedProperties.showHelp.visible, true);
  assert.equal(
    consent.resolvedProperties.control.targetVariantKey,
    'nf01.component-families/variant:checkbox/checked'
  );

  const row = instByKey.get('nf01.component-families/instance:roster-row-1');
  assert.equal(row.resolvedProperties.firstCell.targetVariantKey, 'nf01.component-families/variant:table-cell/header');
  assert.equal(row.resolvedProperties.secondCell.targetVariantKey, 'nf01.component-families/variant:table-cell/muted');
  assert.equal(row.resolvedProperties.showSecondCell.visible, false);
});

test('repeat apply preserves all IDs, manual TEXT/BOOLEAN/INSTANCE_SWAP overrides, instance placement, and siblings', async () => {
  const { figma, page, existingHero, snapshotTree } = createMockFigmaWorld();
  const contract = buildSixFamiliesContract();
  const heroBefore = snapshotTree(existingHero);

  const first = await ensureSemanticComponents(figma, page, contract);
  assert.equal(first.status, 'created');

  const fieldSet = first.componentSets.find(s => s.family === 'field');
  const propKeyById = Object.fromEntries(fieldSet.propertyMappings.map(p => [p.id, p.actualKey]));
  const radioSet = first.componentSets.find(s => s.family === 'radio');
  const radioSelectedMainId = radioSet.variants.find(v => v.key.endsWith('/selected')).id;

  // Simulate user editing form-consent-field in Figma (TEXT + BOOLEAN + INSTANCE_SWAP + manual drag placement)
  const consentRecord = first.instances.find(i => i.key.endsWith(':form-consent-field'));
  const consentNode = page.findOne(n => n.id === consentRecord.id);
  consentNode.setProperties({
    [propKeyById.label]: 'Custom VIP Safety Title',
    [propKeyById.showHelp]: false,
    [propKeyById.control]: radioSelectedMainId
  });
  consentNode.x = 340;
  consentNode.y = 512;
  consentNode.relativeTransform = [[1, 0, 340], [0, 1, 512]];

  const second = await ensureSemanticComponents(figma, page, contract);
  assert.equal(second.status, 'unchanged');
  assert.equal(second.workbenchFrameId, first.workbenchFrameId);
  assert.deepEqual(
    second.componentSets.map(s => ({ id: s.id, variants: s.variants.map(v => v.id), keys: s.propertyMappings.map(p => p.actualKey) })),
    first.componentSets.map(s => ({ id: s.id, variants: s.variants.map(v => v.id), keys: s.propertyMappings.map(p => p.actualKey) })),
    'repeat apply must reuse exact COMPONENT_SET, COMPONENT, and #suffix property keys'
  );
  assert.deepEqual(
    second.instances.map(i => i.id),
    first.instances.map(i => i.id),
    'repeat apply must reuse exact INSTANCE IDs without recreation or detach'
  );

  // Verify user overrides survived
  const overriddenIds = second.preservedOverrides.map(o => `${ o.instanceKey }:${ o.propId }`).sort();
  assert.deepEqual(overriddenIds, [
    'nf01.component-families/instance:form-consent-field:control',
    'nf01.component-families/instance:form-consent-field:label',
    'nf01.component-families/instance:form-consent-field:showHelp'
  ]);
  const consentAfter = second.instances.find(i => i.key === consentRecord.key);
  assert.equal(consentAfter.resolvedProperties.label.characters, 'Custom VIP Safety Title');
  assert.equal(consentAfter.resolvedProperties.showHelp.visible, false);
  assert.equal(consentAfter.resolvedProperties.control.mainComponentId, radioSelectedMainId);
  assert.deepEqual(consentAfter.placement, { x: 340, y: 512, relativeTransform: [[1, 0, 340], [0, 1, 512]] });
  assert.equal(second.preservedPlacements.length, 1);
  assert.equal(second.preservedPlacements[0].instanceKey, consentRecord.key);
  assert.deepEqual(snapshotTree(existingHero), heroBefore);
});

test('source main default change propagates only to unoverridden instances while preserving user overrides (and rejects conflicts cleanly)', async () => {
  const { figma, page } = createMockFigmaWorld();
  const contractV1 = buildSixFamiliesContract();
  const first = await ensureSemanticComponents(figma, page, contractV1);

  const fieldSet = first.componentSets.find(s => s.family === 'field');
  const propKeyById = Object.fromEntries(fieldSet.propertyMappings.map(p => [p.id, p.actualKey]));
  const checkboxUncheckedId = first.componentSets
    .find(s => s.family === 'checkbox')
    .variants.find(v => v.key.endsWith('/unchecked')).id;

  // Instance 0 (form-default-field) has NO overrides -> should inherit updated main defaults!
  // Instance 1 (form-consent-field) gets interactive user overrides -> must NOT be overwritten by new main defaults!
  const consentId = first.instances.find(i => i.key.endsWith(':form-consent-field')).id;
  const consentNode = page.findOne(n => n.id === consentId);
  consentNode.setProperties({
    [propKeyById.helpText]: 'User edited help note',
    [propKeyById.showHelp]: true,
    [propKeyById.control]: checkboxUncheckedId
  });

  // Update main defaults on Field in V2 contract
  const contractV2 = deepCopy(contractV1);
  const fieldContractV2 = contractV2.componentSets.find(s => s.family === 'field');
  fieldContractV2.properties.find(p => p.id === 'helpText').defaultValue = 'Updated check-in policy V2.';
  fieldContractV2.properties.find(p => p.id === 'showHelp').defaultValue = false;
  fieldContractV2.properties.find(p => p.id === 'control').defaultValue = {
    setId: 'nf01.component-families/set:radio',
    variantKey: 'nf01.component-families/variant:radio/unselected'
  };

  const updated = await ensureSemanticComponents(figma, page, contractV2);
  assert.equal(updated.status, 'updated');

  const defaultInstAfter = updated.instances.find(i => i.key.endsWith(':form-default-field'));
  assert.equal(defaultInstAfter.resolvedProperties.helpText.characters, 'Updated check-in policy V2.');
  assert.equal(defaultInstAfter.resolvedProperties.showHelp.visible, false);
  assert.equal(
    defaultInstAfter.resolvedProperties.control.targetVariantKey,
    'nf01.component-families/variant:radio/unselected'
  );
  assert.equal(updated.inheritedDefaults.length, 3);

  const consentInstAfter = updated.instances.find(i => i.key.endsWith(':form-consent-field'));
  assert.equal(consentInstAfter.resolvedProperties.helpText.characters, 'User edited help note');
  assert.equal(consentInstAfter.resolvedProperties.showHelp.visible, true);
  assert.equal(consentInstAfter.resolvedProperties.control.mainComponentId, checkboxUncheckedId);

  // Conflict check: when editComponentProperty is unavailable, main default change is rejected before any write
  const noEditWorld = createMockFigmaWorld({ omitEditComponentProperty: true });
  await ensureSemanticComponents(noEditWorld.figma, noEditWorld.page, contractV1);
  const beforeConflictSnap = noEditWorld.snapshotTree(noEditWorld.page);
  await assert.rejects(
    () => ensureSemanticComponents(noEditWorld.figma, noEditWorld.page, contractV2),
    /Conflict: editComponentProperty API unavailable/
  );
  assert.deepEqual(noEditWorld.snapshotTree(noEditWorld.page), beforeConflictSnap);

  // Conflict check: corrupt/missing initial authoring metadata on instance rejects before any write
  consentNode.setPluginData('figmaFlowFamilyInstance', '');
  await assert.rejects(
    () => ensureSemanticComponents(figma, page, contractV2),
    /Conflict: missing or corrupt instance authoring metadata/
  );
});

test('preflight rejects disallowed families, undeclared variants, out-of-range swaps, CAS mismatch, and rolls back only created nodes on partial failure', async () => {
  const base = buildSixFamiliesContract();

  // 1. Unsupported family ID
  {
    const { figma, page, snapshotTree } = createMockFigmaWorld();
    const snap = snapshotTree(page);
    const bad = deepCopy(base);
    bad.componentSets[0].family = 'accordion';
    await assert.rejects(() => ensureSemanticComponents(figma, page, bad), /unsupported component family: accordion/);
    assert.deepEqual(snapshotTree(page), snap);
  }

  // 2. Undeclared variant state
  {
    const { figma, page, snapshotTree } = createMockFigmaWorld();
    const snap = snapshotTree(page);
    const bad = deepCopy(base);
    bad.componentSets[3].axes.state.push('hover');
    await assert.rejects(() => ensureSemanticComponents(figma, page, bad), /Undeclared state value for family field: hover/);
    assert.deepEqual(snapshotTree(page), snap);
  }

  // 3. Disallowed swap target (table-row targeting input, or instance swap outside allowedSetIds)
  {
    const { figma, page, snapshotTree } = createMockFigmaWorld();
    const snap = snapshotTree(page);
    const badRow = deepCopy(base);
    badRow.componentSets[5].swapTargets.push('nf01.component-families/set:input');
    badRow.componentSets[5].properties[0].allowedSetIds.push('nf01.component-families/set:input');
    await assert.rejects(() => ensureSemanticComponents(figma, page, badRow), /table-row swap slots can only target table-cell/);

    const badInstSwap = deepCopy(base);
    badInstSwap.instances[1].propertyValues.control = {
      setId: 'nf01.component-families/set:table-cell',
      variantKey: 'nf01.component-families/variant:table-cell/default'
    };
    await assert.rejects(() => ensureSemanticComponents(figma, page, badInstSwap), /outside allowedSetIds/);
    assert.deepEqual(snapshotTree(page), snap);
  }

  // 4. Disallowed live user swap in Figma outside allowedSetIds rejected on repeat apply with zero mutation
  {
    const { figma, page, snapshotTree } = createMockFigmaWorld();
    const created = await ensureSemanticComponents(figma, page, base);
    const fieldSet = created.componentSets.find(s => s.family === 'field');
    const controlActualKey = fieldSet.propertyMappings.find(p => p.id === 'control').actualKey;
    const illegalTableCellMainId = created.componentSets.find(s => s.family === 'table-cell').variants[0].id;
    const consentNode = page.findOne(n => n.id === created.instances[1].id);
    consentNode.setProperties({ [controlActualKey]: illegalTableCellMainId });
    const snapBeforeReject = snapshotTree(page);
    await assert.rejects(
      () => ensureSemanticComponents(figma, page, base),
      /Disallowed INSTANCE_SWAP override outside allowedSetIds/
    );
    assert.deepEqual(snapshotTree(page), snapBeforeReject);
  }

  // 5. CAS expectedRevision mismatch rejected before any write
  {
    const { figma, page, snapshotTree } = createMockFigmaWorld();
    await ensureSemanticComponents(figma, page, base);
    const snap = snapshotTree(page);
    const staleCas = { ...deepCopy(base), expectedRevision: 99 };
    await assert.rejects(() => ensureSemanticComponents(figma, page, staleCas), /CAS revision mismatch/);
    assert.deepEqual(snapshotTree(page), snap);
  }

  // 6. Partial write failure on first apply rolls back ONLY created owner nodes, preserving existing page siblings
  {
    const { figma, page, existingHero, snapshotTree } = createMockFigmaWorld({ failAddPropertyName: 'Show optional column' });
    const pageBefore = snapshotTree(page);
    await assert.rejects(
      () => ensureSemanticComponents(figma, page, base),
      /Simulated failure adding property Show optional column/
    );
    assert.equal(page.children.length, 1);
    assert.equal(page.children[0], existingHero);
    assert.deepEqual(snapshotTree(page), pageBefore);
  }

  // 7. Partial write failure on repeat apply rolls back in-flight edits and NEVER deletes existing workbench/instances
  {
    const failState = { failOnSetPropertiesCall: 999 };
    const { figma, page, snapshotTree } = createMockFigmaWorld(failState);
    const initial = await ensureSemanticComponents(figma, page, base);
    assert.equal(initial.status, 'created');
    const beforeFailedUpdate = snapshotTree(page);

    failState.setPropertiesCount = 0;
    failState.failOnSetPropertiesCall = 1;
    const nextContract = deepCopy(base);
    nextContract.instances[1].propertyValues.label = 'Trigger setProperties failure';
    nextContract.componentSets[3].properties[1].defaultValue = 'Should revert on failure';

    await assert.rejects(
      () => ensureSemanticComponents(figma, page, nextContract),
      /Simulated failure during instance\.setProperties/
    );
    assert.deepEqual(snapshotTree(page), beforeFailedUpdate, 'existing workbench and instances must roll back cleanly without deletion');
  }
});

test('compiles real examples/owned-component-families/design.json and preserves live overrides/placement on static repeat apply', async () => {
  const rootDir = path.resolve(__dirname, '..');
  const compiledContracts = JSON.parse(
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
          'graph = {"nodes": [], "edges": [], "componentFamilies": design["componentFamilies"]}',
          'print(json.dumps([compile_graph_component_families(design), compile_graph_component_families(graph, owner_key="nf01.graph-families")]))'
        ].join('; ')
      ],
      { cwd: rootDir, encoding: 'utf8' }
    )
  );
  const [designContract, graphContract] = compiledContracts;
  const { figma, page, existingHero, snapshotTree } = createMockFigmaWorld();
  const heroBefore = snapshotTree(existingHero);

  const res1 = await ensureSemanticComponents(figma, page, designContract);
  assert.equal(res1.status, 'created');
  assert.equal(res1.componentSets.length, 6);
  assert.equal(res1.instances.length, 8);

  // Simulate user editing participant field on the compiled real design contract
  const fieldSet = res1.componentSets.find(s => s.family === 'field');
  const fieldKeyById = Object.fromEntries(fieldSet.propertyMappings.map(p => [p.id, p.actualKey]));
  const checkboxCheckedId = res1.componentSets
    .find(s => s.family === 'checkbox')
    .variants.find(v => v.key.endsWith('/checked')).id;
  const participantInst = res1.instances.find(i => i.elementId === 'form-participant-field');
  const participantNode = page.findOne(n => n.id === participantInst.id);
  participantNode.setProperties({
    [fieldKeyById.label]: 'Overridden participant label',
    [fieldKeyById.showHelp]: false,
    [fieldKeyById.control]: checkboxCheckedId
  });
  participantNode.x = 256;
  participantNode.y = 384;
  participantNode.relativeTransform = [[1, 0, 256], [0, 1, 384]];

  // Repeat static apply: IDs, overrides, placement, and page siblings preserved
  const res2 = await ensureSemanticComponents(figma, page, designContract);
  assert.equal(res2.status, 'unchanged');
  assert.equal(res2.workbenchFrameId, res1.workbenchFrameId);
  assert.deepEqual(res2.instances.map(i => i.id), res1.instances.map(i => i.id));
  assert.equal(res2.preservedOverrides.length, 3);
  assert.equal(res2.preservedPlacements.length, 1);

  const readback = await readSemanticComponentFamilies(figma, page, designContract);
  assert.equal(readback.status, 'present');
  const participantAfter = readback.instances.find(i => i.elementId === 'form-participant-field');
  assert.equal(participantAfter.resolvedProperties.label.characters, 'Overridden participant label');
  assert.equal(participantAfter.resolvedProperties.showHelp.visible, false);
  assert.equal(participantAfter.resolvedProperties.control.mainComponentId, checkboxCheckedId);
  assert.deepEqual(participantAfter.placement, { x: 256, y: 384, relativeTransform: [[1, 0, 256], [0, 1, 384]] });

  // Also provision canonical graph-sourced contract as an independent owned workbench on the same page
  const graphRes = await ensureSemanticComponents(figma, page, graphContract);
  assert.equal(graphRes.status, 'created');
  assert.equal(graphRes.componentSets.length, 6);
  assert.deepEqual(snapshotTree(existingHero), heroBefore);
});
