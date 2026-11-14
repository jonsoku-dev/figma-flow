const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

const root = path.join(__dirname, '..');
const runtime = fs.readFileSync(path.join(root, 'figma-bridge/code.js'), 'utf8');
const sixFamiliesSource = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/nf01/six-families.json'), 'utf8'));
const compiledPayload = JSON.parse(
  execFileSync(
    'python3',
    [
      '-B',
      '-c',
      'import json,sys;sys.path.insert(0,"tools");from design_system import compile_design;print(json.dumps(compile_design(json.load(sys.stdin))))',
    ],
    {cwd: root, input: JSON.stringify(sixFamiliesSource), encoding: 'utf8'}
  )
);

function createEnvironment(customPayload = compiledPayload) {
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
      });
    }
    appendChild(node) {
      if (node.parent) {
        node.parent.children = node.parent.children.filter(child => child !== node);
      }
      node.parent = this;
      this.children.push(node);
    }
    remove() {
      this.removed = true;
      if (this.parent) {
        this.parent.children = this.parent.children.filter(child => child !== this);
      }
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
    addComponentProperty(name, type, defaultValue, options) {
      const key = `${name}#${this.id}:${++propSeq}`;
      this.componentPropertyDefinitions[key] = {type, defaultValue, ...(options || {})};
      return key;
    }
    createInstance() {
      const clone = sourceNode => {
        const result = new Node(sourceNode === this ? 'INSTANCE' : sourceNode.type);
        result.characters = sourceNode.characters;
        result.name = sourceNode.name;
        result.visible = sourceNode.visible;
        result.layoutMode = sourceNode.layoutMode;
        result.componentPropertyReferences = {...(sourceNode.componentPropertyReferences || {})};
        result.data = {...sourceNode.data};
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
          {type: prop.type, value: prop.defaultValue},
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
                const targetMain = [...env.context.authored.components.values()].find(m => m.id === value);
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

  const page = new Node('PAGE');
  page.setPluginData('figmaFlow', JSON.stringify({semantic_id: 'design-import', bridge: 1, source_sha256: 'a'.repeat(64), complete: true}));
  const library = new Node('FRAME');
  page.appendChild(library);
  library.setPluginData('figmaFlow', JSON.stringify({semantic_id: 'component-library'}));
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
    PAYLOAD: structuredClone(customPayload),
    library,
    variables: new Map(),
    warnings: new Set(),
    fonts: new Map(),
  });
  vm.runInContext(runtime, context);
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

  const env = {context, page, library, figma, Node};
  return env;
}

async function authorLibraryAndScreens(env) {
  const {context, page, Node} = env;
  vm.runInContext('validateDeclaredComponentProperties(PAYLOAD)', context);
  const start = runtime.indexOf('    const components = new Map();');
  const end = runtime.indexOf('    layoutFoundationSets(library, componentSets);', start);
  context.authored = await vm.runInContext(
    '(async()=>{' + runtime.slice(start, end) + ';return {components,componentSets};})()',
    context
  );
  const {components} = context.authored;
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
        instance.setProperties({[labelKey]: element.text});
      }
      context.instance = instance;
      context.main = main;
      context.element = {...element, id: identity};
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

test('authors all 6 canonical NF-01 families with distinct #suffix keys, duplicate display names, and Python/JS readback parity', async () => {
  const env = createEnvironment();
  const {components, componentSets} = await authorLibraryAndScreens(env);
  assert.equal(componentSets.length, 6);

  // Verify layout modes: field is VERTICAL, table-row is HORIZONTAL
  const fieldDefault = components.get(JSON.stringify(['field', 'default']));
  const rowDefault = components.get(JSON.stringify(['table-row', 'default']));
  assert.equal(fieldDefault.layoutMode, 'VERTICAL');
  assert.equal(rowDefault.layoutMode, 'HORIZONTAL');

  // Verify visual focus and disabled states exist as variants
  assert(components.get(JSON.stringify(['input', 'focus'])));
  assert(components.get(JSON.stringify(['input', 'disabled'])));
  assert(components.get(JSON.stringify(['checkbox', 'disabled'])));
  assert(components.get(JSON.stringify(['radio', 'disabled'])));

  // Verify input/checkbox/radio/table-cell do not create a duplicate "문구" property when explicit TEXT owns label
  const inputSet = fieldDefault.parent.parent.children.find(n => n.name === 'input');
  const inputPropKeys = Object.keys(inputSet.componentPropertyDefinitions);
  assert.equal(inputPropKeys.length, 1);
  assert.match(inputPropKeys[0], /^Value#/);

  // Verify duplicate display name ("Cell") on table-row produces two distinct #suffix keys
  const rowMeta = JSON.parse(rowDefault.getPluginData('figmaFlow'));
  const firstCellKey = rowMeta.declared_property_keys.firstCell;
  const secondCellKey = rowMeta.declared_property_keys.secondCell;
  assert.match(firstCellKey, /^Cell#/);
  assert.match(secondCellKey, /^Cell#/);
  assert.notEqual(firstCellKey, secondCellKey);
  assert.equal(rowMeta.declared_property_contracts.firstCell.target_semantic_suffix, '/slot:cell-0');
  assert.equal(rowMeta.declared_property_contracts.secondCell.target_semantic_suffix, '/slot:cell-1');

  // Verify JS verifyDeclaredComponentReadback + Python compare_declared_component_properties both pass 100%
  env.context.page = env.page;
  const observed = await vm.runInContext('snapshot(page)', env.context);
  env.context.observed = observed;
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD, observed)', env.context);

  const pyChecks = JSON.parse(
    execFileSync(
      'python3',
      [
        '-B',
        '-c',
        'import json,sys;sys.path.insert(0,"tools");from figma_bridge import compare_declared_component_properties;data=json.load(sys.stdin);print(json.dumps(compare_declared_component_properties(data["page"],data["expected"])))',
      ],
      {cwd: root, input: JSON.stringify({page: observed, expected: env.context.PAYLOAD}), encoding: 'utf8'}
    )
  );
  assert(pyChecks.length > 0);
  const nonMatch = pyChecks.filter(item => item.status !== 'match');
  assert.deepEqual(nonMatch, []);
});

test('rejects out-of-range swaps, unsupported families, secrets, and target collisions before native writes', () => {
  const mutations = [
    p => {
      p.screens[0].elements[0].property_values.control = {component: 'table-row', variant: 'default'};
    },
    p => {
      p.components['table-row'].properties.firstCell.default_value = {component: 'input', variant: 'default'};
    },
    p => {
      p.components.button = {family: 'button', variants: {default: {color: 'color.ink'}}};
    },
    p => {
      p.screens[0].elements[0].property_values.helpText = 'sk-live-1234567890abcdefSECRET';
    },
    p => {
      p.components.field.properties.badCollision = {type: 'TEXT', target: 'field-control', default_value: 'x'};
    },
  ];
  for (const mutate of mutations) {
    const env = createEnvironment();
    mutate(env.context.PAYLOAD);
    assert.throws(() => vm.runInContext('validateDeclaredComponentProperties(PAYLOAD)', env.context), /Declared component properties:/);
    assert.equal(env.library.children.length, 0, 'zero nodes authored when preflight rejects');
  }
});

test('repeat apply reuses exact IDs, preserves user TEXT/BOOLEAN/INSTANCE_SWAP overrides + manual placement, and leaves undeclared siblings untouched', async () => {
  const env = createEnvironment();
  const {components} = await authorLibraryAndScreens(env);

  // Add an undeclared sibling frame on the same page to verify non-interference
  const undeclaredFrame = new env.Node('FRAME');
  undeclaredFrame.name = 'Manual scratchpad';
  undeclaredFrame.x = 920;
  undeclaredFrame.y = 40;
  env.page.appendChild(undeclaredFrame);

  const screenFrame = env.page.children.find(n => n.getPluginData('semanticKey') === env.context.PAYLOAD.screens[0].id);
  const fieldInstance = screenFrame.children[0];
  const fieldMain = components.get(JSON.stringify(['field', 'default']));
  const fieldKeys = JSON.parse(fieldMain.getPluginData('figmaFlow')).declared_property_keys;
  const checkedBoxMain = components.get(JSON.stringify(['checkbox', 'checked']));

  // Simulate user editing TEXT, BOOLEAN visibility, nested INSTANCE_SWAP, and manual placement on a single instance
  fieldInstance.setProperties({
    [fieldKeys.label]: 'Edited participant full name',
    [fieldKeys.helpText]: 'User-edited custom note',
    [fieldKeys.showHelp]: false,
    [fieldKeys.control]: checkedBoxMain.id,
  });
  fieldInstance.x = 184;
  fieldInstance.y = 296;
  fieldInstance.relativeTransform = [[1, 0, 184], [0, 1, 296]];

  const originalMainIds = [...components.values()].map(n => n.id);
  const originalInstanceIds = screenFrame.children.map(n => n.id);

  // Re-apply the same owner contract with preserveInstanceOverrides=true
  env.context.page = env.page;
  const reapplyResult = await vm.runInContext(
    'reapplyDeclaredComponents(page, PAYLOAD, {preserveInstanceOverrides: true, expectedSourceSha256: "a".repeat(64)})',
    env.context
  );

  assert.deepEqual(Array.from(reapplyResult.mainComponentIds), originalMainIds);
  assert.deepEqual(Array.from(reapplyResult.instanceIds), originalInstanceIds);
  assert.deepEqual(Array.from(reapplyResult.createdInstanceIds), []);

  // User overrides and manual placement are 100% intact
  assert.equal(fieldInstance.componentProperties[fieldKeys.label].value, 'Edited participant full name');
  assert.equal(fieldInstance.componentProperties[fieldKeys.helpText].value, 'User-edited custom note');
  assert.equal(fieldInstance.componentProperties[fieldKeys.showHelp].value, false);
  assert.equal(fieldInstance.componentProperties[fieldKeys.control].value, checkedBoxMain.id);
  assert.equal(fieldInstance.x, 184);
  assert.equal(fieldInstance.y, 296);
  assert.deepEqual(JSON.parse(JSON.stringify(fieldInstance.relativeTransform)), [[1, 0, 184], [0, 1, 296]]);

  // Undeclared sibling frame is untouched
  assert(env.page.children.includes(undeclaredFrame));
  assert.equal(undeclaredFrame.x, 920);

  // Readback verification with preserveInstanceOverrides=true succeeds
  const observed = await vm.runInContext('snapshot(page)', env.context);
  env.context.observed = observed;
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD, observed, {preserveInstanceOverrides: true})', env.context);
});

test('stale, missing, or corrupt targets and disallowed live swaps fail preflight with zero mutation', async () => {
  const env = createEnvironment();
  const {components} = await authorLibraryAndScreens(env);
  env.context.page = env.page;

  const snapshotJson = () => JSON.stringify(env.page.children.map(n => ({id: n.id, name: n.name, count: n.children.length})));
  const baseline = snapshotJson();

  // 1. Stale source_sha256 pin
  await assert.rejects(
    vm.runInContext('reapplyDeclaredComponents(page, PAYLOAD, {expectedSourceSha256: "b".repeat(64)})', env.context),
    /stale source_sha256 pin/
  );
  assert.equal(snapshotJson(), baseline);

  // 2. Missing declared target screen
  const missingScreenPayload = structuredClone(env.context.PAYLOAD);
  missingScreenPayload.screens.push({id: 'absent-screen', title: 'Absent', trace: ['NF-01'], elements: []});
  env.context.badPayload = missingScreenPayload;
  await assert.rejects(
    vm.runInContext('reapplyDeclaredComponents(page, badPayload)', env.context),
    /missing target screen absent-screen/
  );
  assert.equal(snapshotJson(), baseline);

  // 3. Existing instance has a live swap outside allowed swap_targets
  const screenFrame = env.page.children.find(n => n.getPluginData('semanticKey') === env.context.PAYLOAD.screens[0].id);
  const fieldInstance = screenFrame.children[0];
  const fieldMain = components.get(JSON.stringify(['field', 'default']));
  const controlKey = JSON.parse(fieldMain.getPluginData('figmaFlow')).declared_property_keys.control;
  const rowMain = components.get(JSON.stringify(['table-row', 'default']));
  fieldInstance.componentProperties[controlKey].value = rowMain.id;

  await assert.rejects(
    vm.runInContext('reapplyDeclaredComponents(page, PAYLOAD, {preserveInstanceOverrides: true})', env.context),
    /existing swap override outside allowed range/
  );
  assert.equal(snapshotJson(), baseline);
});

test('partial failure during reapply rolls back newly created owned nodes while preserving existing instances, and retry succeeds', async () => {
  const env = createEnvironment();
  const {components} = await authorLibraryAndScreens(env);
  env.context.page = env.page;

  const screenFrame = env.page.children.find(n => n.getPluginData('semanticKey') === env.context.PAYLOAD.screens[0].id);
  const fieldInstance = screenFrame.children[0];
  const fieldMain = components.get(JSON.stringify(['field', 'default']));
  const fieldKeys = JSON.parse(fieldMain.getPluginData('figmaFlow')).declared_property_keys;
  fieldInstance.setProperties({[fieldKeys.label]: 'Preserved across rollback'});
  fieldInstance.x = 72;
  fieldInstance.y = 144;

  const initialChildIds = screenFrame.children.map(n => n.id);

  // Add a 4th declared element and simulate a failure after creation
  const nextPayload = structuredClone(env.context.PAYLOAD);
  nextPayload.screens[0].elements.push({
    id: 'table-roster-row-2',
    kind: 'component',
    component: 'table-row',
    variant: 'selected',
    text: 'Row 2',
    property_values: {
      firstCell: {component: 'table-cell', variant: 'default'},
      secondCell: {component: 'table-cell', variant: 'default'},
      showSecondCell: true,
    },
  });
  env.context.nextPayload = nextPayload;

  await assert.rejects(
    vm.runInContext(
      `reapplyDeclaredComponents(page, nextPayload, {
        preserveInstanceOverrides: true,
        beforeCommitHook({createdNodes}) {
          if (!createdNodes.length) throw new Error("expected created node");
          throw new Error("simulated native write interruption");
        }
      })`,
      env.context
    ),
    /simulated native write interruption/
  );

  // Newly created instance was rolled back; existing instances & overrides untouched
  assert.deepEqual(screenFrame.children.map(n => n.id), initialChildIds);
  assert.equal(fieldInstance.componentProperties[fieldKeys.label].value, 'Preserved across rollback');
  assert.equal(fieldInstance.x, 72);
  assert.equal(fieldInstance.y, 144);

  // Clean retry without the injected error succeeds and adds the 4th element
  const retryResult = await vm.runInContext(
    'reapplyDeclaredComponents(page, nextPayload, {preserveInstanceOverrides: true})',
    env.context
  );
  assert.equal(retryResult.instanceIds.length, 3);
  assert.equal(retryResult.createdInstanceIds.length, 1);
  assert.equal(screenFrame.children.length, 4);
  assert.equal(fieldInstance.componentProperties[fieldKeys.label].value, 'Preserved across rollback');

  const observed = await vm.runInContext('snapshot(page)', env.context);
  env.context.observed = observed;
  vm.runInContext('verifyDeclaredComponentReadback(nextPayload, observed, {preserveInstanceOverrides: true})', env.context);
});

test('commitComponentFields enforces CAS, swap allowlists, #suffix property keys, and selective apply for BOOLEAN/INSTANCE_SWAP/TEXT', () => {
  const {commitComponentFields} = require(path.join(root, 'figma-bridge/graph_token_sync.js'));
  const spec = {
    schema: 'figma-flow-component-field-v1',
    component: {id: 'participant-field', node_id: 'inst:field-1', main_component_id: 'comp:field-default'},
    fields: [
      {
        field: 'label',
        type: 'TEXT',
        property_key: 'Label#field:label',
        token: 'nf01/field/label',
        before: 'Participant name',
        after: 'Attendee full name',
      },
      {
        field: 'showHelp',
        type: 'BOOLEAN',
        property_key: 'Show help#field:showHelp',
        token: 'nf01/field/show-help',
        before: true,
        after: false,
      },
      {
        field: 'control',
        type: 'INSTANCE_SWAP',
        property_key: 'Control#field:control',
        allowed_swap_ids: ['comp:input-default', 'comp:checkbox-checked', 'comp:radio-selected'],
        before: 'comp:input-default',
        after: 'comp:radio-selected',
      },
      {
        field: 'helpText',
        type: 'TEXT',
        property_key: 'Help#field:helpText',
        before: 'As shown on roster',
        after: 'Should not apply when unselected',
      },
    ],
  };
  const observed = {
    label: 'Participant name',
    showHelp: true,
    control: 'comp:input-default',
    helpText: 'As shown on roster',
  };
  const observedSnapshot = JSON.stringify(observed);

  const committed = commitComponentFields(spec, ['showHelp', 'control'], observed);
  assert.equal(JSON.stringify(observed), observedSnapshot, 'input observed map is never mutated');
  assert.equal(committed.node_id, 'inst:field-1');
  assert.equal(committed.main_component_id, 'comp:field-default');
  assert.equal(committed.full_apply, false);
  assert.deepEqual(committed.applied, [
    {id: 'participant-field', field: 'showHelp', value: false, property_key: 'Show help#field:showHelp'},
    {id: 'participant-field', field: 'control', value: 'comp:radio-selected', property_key: 'Control#field:control'},
  ]);
  assert.equal(committed.values.label, 'Participant name');
  assert.equal(committed.values.helpText, 'As shown on roster');
  assert.deepEqual(committed.baseline, {showHelp: false, control: 'comp:radio-selected'});

  // CAS rejection on drifted BOOLEAN or INSTANCE_SWAP
  assert.throws(
    () => commitComponentFields(spec, ['showHelp'], {...observed, showHelp: false}),
    /stale before value: showHelp/
  );
  assert.throws(
    () => commitComponentFields(spec, ['control'], {...observed, control: 'comp:checkbox-checked'}),
    /stale before value: control/
  );

  // Disallowed swap target and missing #suffix property key rejection
  const disallowedSpec = structuredClone(spec);
  disallowedSpec.fields[2].after = 'comp:table-row-default';
  assert.throws(() => commitComponentFields(disallowedSpec, ['control'], observed), /disallowed swap target: control/);

  const badKeySpec = structuredClone(spec);
  badKeySpec.fields[1].property_key = 'Show help without suffix';
  assert.throws(() => commitComponentFields(badKeySpec, ['showHelp'], observed), /invalid component property key: showHelp/);
});
