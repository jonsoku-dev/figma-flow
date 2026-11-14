const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const provisionSource = fs.readFileSync(path.join(__dirname, '../figma-bridge/native_provision.js'), 'utf8');

function buildRuntimePlan() {
  return {
    schema: 'figma-flow-native-edit-plan-v1',
    file_key: 'sample_file',
    page_id: '10:1',
    provision: {
      schema: 'figma-flow-component-families-provision-v1',
      graph_id: 'owned-component-families',
      graph_sha256: 'a'.repeat(64),
      design_source_sha256: 'b'.repeat(64),
      readback_sha256: 'c'.repeat(64),
      owner_key: 'nf01.component-families',
      frame_key: 'nf01.component-families/workbench',
      position: {x: 1296, y: 0},
      workbench_bounds: {width: 960, height: 1464},
      page_roots: [],
      contract: {
        schema: 'figma-flow-semantic-family-contract-v1',
        version: 1,
        mode: 'additive-family-workbench',
        ownerKey: 'nf01.component-families',
        workbench: {
          frameKey: 'nf01.component-families/workbench',
          libraryKey: 'nf01.component-families/library',
          instancesFrameKey: 'nf01.component-families/instances',
          name: 'NF-01 · Component families workbench',
          position: {x: 1296, y: 0},
          font: {family: 'Inter', style: 'Regular'},
        },
        componentSets: [
          {
            id: 'nf01.component-families/set:input',
            family: 'input',
            component: 'input',
            name: 'Input',
            layout: 'HORIZONTAL',
            axes: {state: ['default', 'focus']},
            swapTargets: [],
            variants: [{key: 'nf01.component-families/variant:input/default', variant: 'default', props: {state: 'default'}, style: {}, defaultLabel: 'Sample'}],
            properties: [{id: 'value', name: 'Value', type: 'TEXT', targetKey: 'label', defaultValue: 'Sample'}],
          },
          {
            id: 'nf01.component-families/set:checkbox',
            family: 'checkbox',
            component: 'checkbox',
            name: 'Checkbox',
            layout: 'HORIZONTAL',
            axes: {state: ['unchecked', 'checked']},
            swapTargets: [],
            variants: [{key: 'nf01.component-families/variant:checkbox/unchecked', variant: 'unchecked', props: {state: 'unchecked'}, style: {}, defaultLabel: 'Check'}],
            properties: [{id: 'optionLabel', name: 'Label', type: 'TEXT', targetKey: 'label', defaultValue: 'Check'}],
          },
          {
            id: 'nf01.component-families/set:field',
            family: 'field',
            component: 'field',
            name: 'Field',
            layout: 'VERTICAL',
            axes: {state: ['default', 'error']},
            swapTargets: ['nf01.component-families/set:input', 'nf01.component-families/set:checkbox'],
            variants: [{key: 'nf01.component-families/variant:field/default', variant: 'default', props: {state: 'default'}, style: {}, defaultLabel: 'Participant'}],
            properties: [
              {id: 'label', name: 'Label', type: 'TEXT', targetKey: 'field-label', defaultValue: 'Participant'},
              {id: 'showHelp', name: 'Show help', type: 'BOOLEAN', targetKey: 'field-help', defaultValue: true},
              {
                id: 'control',
                name: 'Control',
                type: 'INSTANCE_SWAP',
                targetKey: 'field-control',
                allowedSetIds: ['nf01.component-families/set:input', 'nf01.component-families/set:checkbox'],
                defaultValue: {setId: 'nf01.component-families/set:input', variantKey: 'nf01.component-families/variant:input/default'},
              },
            ],
          },
        ],
        instances: [
          {
            key: 'nf01.component-families/instance:field-1',
            elementId: 'field-1',
            setId: 'nf01.component-families/set:field',
            variantKey: 'nf01.component-families/variant:field/default',
            name: 'Participant',
            text: 'Participant',
            propertyValues: {
              label: 'Participant',
              showHelp: true,
              control: {setId: 'nf01.component-families/set:input', variantKey: 'nf01.component-families/variant:input/default'},
            },
          },
          {
            key: 'nf01.component-families/instance:field-2',
            elementId: 'field-2',
            setId: 'nf01.component-families/set:field',
            variantKey: 'nf01.component-families/variant:field/default',
            name: 'Consent',
            text: 'Consent',
            propertyValues: {
              label: 'Consent',
              showHelp: true,
              control: {setId: 'nf01.component-families/set:checkbox', variantKey: 'nf01.component-families/variant:checkbox/unchecked'},
            },
          },
        ],
      },
    },
  };
}

function createHarness() {
  let next = 1;
  let failDiscovery = false;
  let beforeDiscovery = null;
  let ensureOverride = null;
  let ensureCalls = 0;
  let readCalls = 0;
  let removeCalls = 0;
  const objects = new Map();

  class Node {
    constructor(type, name = '') {
      this.id = `20:${next++}`;
      this.type = type;
      this.name = name;
      this.parent = null;
      this.children = [];
      this.data = {};
      this.x = 0;
      this.y = 0;
      this.width = 200;
      this.height = 80;
      this.visible = true;
      objects.set(this.id, this);
    }
    appendChild(child) {
      if (child.parent) throw Error('already parented');
      child.parent = this;
      this.children.push(child);
    }
    remove() {
      removeCalls += 1;
      if (this.parent) {
        const idx = this.parent.children.indexOf(this);
        if (idx >= 0) this.parent.children.splice(idx, 1);
      }
      this.parent = null;
      objects.delete(this.id);
    }
    setPluginData(k, v) { this.data[k] = String(v); }
    getPluginData(k) { return this.data[k] || ''; }
    resize(w, h) { this.width = w; this.height = h; }
    get absoluteBoundingBox() {
      const px = this.parent && this.parent.type !== 'PAGE' ? this.parent.absoluteBoundingBox.x : 0;
      const py = this.parent && this.parent.type !== 'PAGE' ? this.parent.absoluteBoundingBox.y : 0;
      return {x: px + this.x, y: py + this.y, width: this.width, height: this.height};
    }
    findAll(pred) {
      const out = [];
      const walk = n => {
        for (const ch of n.children) {
          if (pred(ch)) out.push(ch);
          walk(ch);
        }
      };
      walk(this);
      return out;
    }
  }

  const page = new Node('PAGE', 'Pinned Test Page');
  page.id = '10:1';
  objects.set(page.id, page);
  page.loadAsync = async () => {};

  const sibling = new Node('FRAME', 'Existing Screen');
  sibling.id = '10:2';
  objects.set(sibling.id, sibling);
  sibling.x = 0;
  sibling.y = 0;
  sibling.resize(1200, 800);
  page.appendChild(sibling);

  const rootRow = {
    id: sibling.id,
    type: sibling.type,
    name: sibling.name,
    semanticKey: null,
    x: sibling.x,
    y: sibling.y,
    width: sibling.width,
    height: sibling.height,
    absoluteBoundingBox: sibling.absoluteBoundingBox,
  };

  const figma = {
    fileKey: 'sample_file',
    currentPage: page,
    async getNodeByIdAsync(id) { return objects.get(id) || null; },
  };

  async function ensureSemanticComponents(_figma, targetPage, contract) {
    ensureCalls += 1;
    if (ensureOverride) {
      const fn = ensureOverride;
      ensureOverride = null;
      return fn(_figma, targetPage, contract);
    }
    let wb = targetPage.findAll(n => n.getPluginData('semanticKey') === contract.workbench.frameKey)[0] || null;
    if (wb) {
      const sets = wb.findAll(n => n.type === 'COMPONENT_SET');
      const insts = wb.findAll(n => n.type === 'INSTANCE' && n.parent?.getPluginData('semanticKey') === contract.workbench.instancesFrameKey);
      return {
        schema: 'figma-flow-semantic-family-result-v1',
        status: 'unchanged',
        ownerKey: contract.ownerKey,
        workbenchFrameId: wb.id,
        componentSets: sets.map(s => ({
          key: s.getPluginData('semanticKey'),
          id: s.id,
          family: JSON.parse(s.getPluginData('figmaFlow')).family,
          propertyMappings: JSON.parse(s.getPluginData('figmaFlow')).propertyMappings,
        })),
        instances: insts.map(i => ({
          key: i.getPluginData('semanticKey'),
          id: i.id,
          mainComponentId: i.mainComponentId,
          componentProperties: i.componentProperties,
          placement: {x: i.x, y: i.y},
        })),
        preservedOverrides: [],
        preservedPlacements: [],
        idMap: {},
      };
    }
    wb = new Node('FRAME', contract.workbench.name);
    wb.x = contract.workbench.position.x;
    wb.y = contract.workbench.position.y;
    wb.resize(960, 1464);
    wb.setPluginData('semanticKey', contract.workbench.frameKey);
    wb.setPluginData('figmaFlowFamilyWorkbench', JSON.stringify({schema: contract.schema, ownerKey: contract.ownerKey, pageId: targetPage.id}));
    targetPage.appendChild(wb);

    const lib = new Node('FRAME', 'Library');
    lib.setPluginData('semanticKey', contract.workbench.libraryKey);
    wb.appendChild(lib);

    const instFrame = new Node('FRAME', 'Instances');
    instFrame.setPluginData('semanticKey', contract.workbench.instancesFrameKey);
    wb.appendChild(instFrame);

    const variantByKey = new Map();
    const setResults = [];
    for (const cs of contract.componentSets) {
      const setNode = new Node('COMPONENT_SET', cs.name);
      setNode.setPluginData('semanticKey', cs.id);
      const defs = {};
      const declaredKeys = {};
      const mappings = [];
      for (const prop of cs.properties) {
        const actualKey = `${prop.name}#${setNode.id}:${prop.id}`;
        defs[actualKey] = {type: prop.type, defaultValue: prop.defaultValue};
        declaredKeys[prop.id] = actualKey;
        mappings.push({id: prop.id, name: prop.name, type: prop.type, actualKey, targetKey: prop.targetKey});
      }
      setNode.componentPropertyDefinitions = defs;
      setNode.setPluginData('figmaFlow', JSON.stringify({family: cs.family, declared_property_keys: declaredKeys, propertyMappings: mappings}));
      lib.appendChild(setNode);

      for (const v of cs.variants) {
        const comp = new Node('COMPONENT', `${cs.name}/${v.variant}`);
        comp.setPluginData('semanticKey', v.key);
        comp.setPluginData('figmaFlow', JSON.stringify({family: cs.family, declared_property_keys: declaredKeys}));
        comp.componentPropertyDefinitions = {};
        const labelChild = new Node('TEXT', 'label');
        labelChild.characters = v.defaultLabel;
        comp.appendChild(labelChild);
        setNode.appendChild(comp);
        variantByKey.set(v.key, {comp, setNode, declaredKeys});
      }
      setResults.push({key: cs.id, id: setNode.id, family: cs.family, propertyMappings: mappings});
    }

    const instResults = [];
    let iy = 0;
    for (const instSpec of contract.instances) {
      const target = variantByKey.get(instSpec.variantKey);
      const inst = new Node('INSTANCE', instSpec.name);
      inst.x = 0;
      inst.y = iy;
      iy += 96;
      inst.setPluginData('semanticKey', instSpec.key);
      inst.mainComponentId = target.comp.id;
      inst.componentSetId = target.setNode.id;
      const cprops = {};
      for (const [pid, val] of Object.entries(instSpec.propertyValues || {})) {
        const actualKey = target.declaredKeys[pid];
        const ptype = typeof val === 'boolean' ? 'BOOLEAN' : typeof val === 'string' ? 'TEXT' : 'INSTANCE_SWAP';
        const resolvedVal = ptype === 'INSTANCE_SWAP' ? variantByKey.get(val.variantKey).comp.id : val;
        cprops[actualKey] = {type: ptype, value: resolvedVal};
      }
      inst.componentProperties = cprops;
      const clonedText = new Node('TEXT', 'label');
      clonedText.characters = instSpec.text;
      inst.appendChild(clonedText);
      instFrame.appendChild(inst);
      instResults.push({key: instSpec.key, id: inst.id, mainComponentId: inst.mainComponentId, componentProperties: cprops, placement: {x: inst.x, y: inst.y}});
    }

    return {
      schema: 'figma-flow-semantic-family-result-v1',
      status: 'created',
      ownerKey: contract.ownerKey,
      workbenchFrameId: wb.id,
      componentSets: setResults,
      instances: instResults,
      preservedOverrides: [],
      preservedPlacements: [],
      idMap: {},
    };
  }

  async function readSemanticComponentFamilies(_figma, targetPage, contract) {
    readCalls += 1;
    const wb = targetPage.findAll(n => n.getPluginData('semanticKey') === contract.workbench.frameKey)[0] || null;
    if (!wb) {
      return {
        schema: 'figma-flow-semantic-family-readback-v1',
        status: 'absent',
        ownerKey: contract.ownerKey,
        workbenchFrameId: null,
        componentSets: [],
        instances: [],
      };
    }
    const sets = wb.findAll(n => n.type === 'COMPONENT_SET');
    const insts = wb.findAll(n => n.type === 'INSTANCE' && n.parent?.getPluginData('semanticKey') === contract.workbench.instancesFrameKey);
    return {
      schema: 'figma-flow-semantic-family-readback-v1',
      status: 'present',
      ownerKey: contract.ownerKey,
      workbenchFrameId: wb.id,
      componentSets: sets.map(s => ({
        key: s.getPluginData('semanticKey'),
        id: s.id,
        family: JSON.parse(s.getPluginData('figmaFlow')).family,
        propertyMappings: JSON.parse(s.getPluginData('figmaFlow')).propertyMappings,
      })),
      instances: insts.map(i => ({
        key: i.getPluginData('semanticKey'),
        id: i.id,
        mainComponentId: i.mainComponentId,
        componentProperties: i.componentProperties,
        placement: {x: i.x, y: i.y},
      })),
    };
  }

  function serializeNode(node) {
    const row = {
      id: node.id,
      parentId: node.parent ? node.parent.id : '0:0',
      type: node.type,
      name: node.name,
      key: node.getPluginData('semanticKey') || null,
      semanticKey: node.getPluginData('semanticKey') || null,
      x: node.x,
      y: node.y,
      width: node.width,
      height: node.height,
      visible: node.visible,
      absoluteBoundingBox: node.absoluteBoundingBox,
    };
    if (node.type === 'COMPONENT_SET') {
      row.componentPropertyDefinitions = JSON.parse(JSON.stringify(node.componentPropertyDefinitions || {}));
      row.componentIds = node.children.filter(c => c.type === 'COMPONENT').map(c => c.id);
    } else if (node.type === 'COMPONENT') {
      row.componentSetId = node.parent?.type === 'COMPONENT_SET' ? node.parent.id : null;
      row.componentPropertyDefinitions = JSON.parse(JSON.stringify(node.componentPropertyDefinitions || {}));
    } else if (node.type === 'INSTANCE') {
      row.mainComponentId = node.mainComponentId;
      row.componentSetId = node.componentSetId || null;
      row.componentProperties = JSON.parse(JSON.stringify(node.componentProperties || {}));
    } else if (node.type === 'TEXT') {
      row.characters = node.characters;
    }
    return row;
  }

  const plan = buildRuntimePlan();
  plan.provision.page_roots = [rootRow];

  const context = vm.createContext({
    figma,
    NATIVE_EDIT_SHA256: 'd'.repeat(64),
    NATIVE_EDIT_PLAN_SCHEMA: plan.schema,
    ensureSemanticComponents,
    readSemanticComponentFamilies,
    nativeEditValidatePlan(p) {
      if (p?.schema !== 'figma-flow-native-edit-plan-v1' || !p.provision) throw Error('invalid plan');
    },
    nativeEditScope(f, p) {
      if (f.fileKey !== p.file_key || f.currentPage.id !== p.page_id) throw Error('scope mismatch');
    },
    nativeEditEqual(a, b) {
      return JSON.stringify(a) === JSON.stringify(b);
    },
    async nativeEditDiscovery() {
      if (beforeDiscovery) {
        const fn = beforeDiscovery;
        beforeDiscovery = null;
        fn();
      }
      if (failDiscovery) throw Error('getter failure');
      return {
        schema: 'figma-flow-graph-native-discovery-v1',
        fileKey: figma.fileKey,
        pageId: page.id,
        allowed_page_ids: [page.id],
        nodes: [page, ...page.findAll(() => true)].map(serializeNode),
        collections: [],
        variables: [],
      };
    },
  });
  vm.runInContext(provisionSource, context);

  return {
    Node,
    figma,
    page,
    sibling,
    plan,
    get ensureCalls() { return ensureCalls; },
    get readCalls() { return readCalls; },
    get removeCalls() { return removeCalls; },
    failGetter() { failDiscovery = true; },
    onBeforeDiscovery(fn) { beforeDiscovery = fn; },
    onEnsure(fn) { ensureOverride = fn; },
    run(p = plan, op = 'apply') { return context.nativeProvisionRun(figma, p, op); },
  };
}

test('delegates read and apply to core semantic helpers, enriches owner declared_metadata only, and preserves user overrides on repeat apply', async () => {
  const h = createHarness();

  const initialRead = await h.run(h.plan, 'read');
  assert.equal(initialRead.native_edit.applied, false);
  assert.equal(initialRead.native_edit.operation, 'read');
  assert.equal(initialRead.component_families.status, 'absent');
  assert.equal(h.ensureCalls, 0);
  assert.equal(h.page.children.length, 1);

  const applied = await h.run(h.plan, 'apply');
  assert.equal(applied.native_edit.applied, true);
  assert.equal(applied.native_edit.idempotent, false);
  assert.equal(applied.native_edit.changed, 5);
  assert.equal(h.page.children.length, 2);

  const setRows = applied.nodes.filter(r => r.type === 'COMPONENT_SET');
  const variantRows = applied.nodes.filter(r => r.type === 'COMPONENT' && r.componentSetId);
  assert.equal(setRows.length, 3);
  for (const sr of setRows) {
    assert(sr.declared_metadata?.declared_property_keys);
    for (const mappedKey of Object.values(sr.declared_metadata.declared_property_keys)) {
      assert(mappedKey in sr.componentPropertyDefinitions);
    }
  }
  for (const vr of variantRows) {
    assert.equal(vr.declared_metadata, undefined);
  }

  const wb = h.page.children.find(n => n.getPluginData('semanticKey') === 'nf01.component-families/workbench');
  const inst1 = wb.findAll(n => n.getPluginData('semanticKey') === 'nf01.component-families/instance:field-1')[0];
  const inst2 = wb.findAll(n => n.getPluginData('semanticKey') === 'nf01.component-families/instance:field-2')[0];
  const checkboxComp = wb.findAll(n => n.getPluginData('semanticKey') === 'nf01.component-families/variant:checkbox/unchecked')[0];

  for (const [k, v] of Object.entries(inst1.componentProperties)) {
    if (v.type === 'TEXT') v.value = 'Edited sample label';
    if (v.type === 'BOOLEAN') v.value = false;
    if (v.type === 'INSTANCE_SWAP') v.value = checkboxComp.id;
  }
  inst1.x = 48;
  inst1.y = 24;
  const inst2Before = JSON.stringify(inst2.componentProperties);

  const repeated = await h.run(h.plan, 'apply');
  assert.equal(repeated.native_edit.applied, true);
  assert.equal(repeated.native_edit.idempotent, true);
  assert.equal(repeated.native_edit.changed, 0);
  assert.equal(inst1.x, 48);
  assert.equal(inst1.y, 24);
  assert.equal(JSON.stringify(inst2.componentProperties), inst2Before);
  for (const v of Object.values(inst1.componentProperties)) {
    if (v.type === 'TEXT') assert.equal(v.value, 'Edited sample label');
    if (v.type === 'BOOLEAN') assert.equal(v.value, false);
    if (v.type === 'INSTANCE_SWAP') assert.equal(v.value, checkboxComp.id);
  }
});

test('rejects scope mismatch, leaked local paths, sibling drift, overlapping additions, and outside-workbench key collisions before mutating', async () => {
  const wrongScope = createHarness();
  wrongScope.figma.fileKey = 'other_file';
  await assert.rejects(() => wrongScope.run(), /scope mismatch/);
  assert.equal(wrongScope.ensureCalls, 0);

  const leakedPath = createHarness();
  leakedPath.plan.provision.source_graph_path = '/tmp/should-not-be-embedded.json';
  await assert.rejects(() => leakedPath.run(), /Invalid or stale NF-01/);
  assert.equal(leakedPath.ensureCalls, 0);

  const drifted = createHarness();
  drifted.sibling.x = 24;
  await assert.rejects(() => drifted.run(), /sibling changed/);
  assert.equal(drifted.ensureCalls, 0);

  const overlap = createHarness();
  const intruder = new overlap.Node('FRAME', 'Overlapping frame');
  intruder.x = 1350;
  intruder.y = 20;
  intruder.resize(300, 300);
  overlap.page.appendChild(intruder);
  await assert.rejects(() => overlap.run(), /overlaps/);
  assert.equal(overlap.ensureCalls, 0);

  const collision = createHarness();
  const rogue = new collision.Node('FRAME', 'Rogue key');
  rogue.x = 0;
  rogue.y = 950;
  rogue.setPluginData('semanticKey', 'nf01.component-families/set:field');
  collision.page.appendChild(rogue);
  await assert.rejects(() => collision.run(), /key collision outside the owned workbench/);
  assert.equal(collision.ensureCalls, 0);
});

test('skips duplicate wrapper compensation on apply failure and conservatively classifies rolled-back, partial, and unknown outcomes', async () => {
  // 1) Core throws `rollback incomplete` even with zero visible residual owned nodes (exact live failure pattern) -> unknown, zero wrapper remove()
  const incNoResidual = createHarness();
  incNoResidual.onEnsure(() => {
    throw Error('Native component property declaration was not retained for nf01.component-families/set:table-row.secondCell; rollback incomplete: Error: in remove: Removing this node is not allowed');
  });
  await assert.rejects(
    () => incNoResidual.run(),
    err => {
      assert.equal(err.readback.schema, 'figma-flow-native-edit-receipt-v1');
      assert.equal(err.readback.status, 'unknown');
      assert.equal(err.readback.mutation_state, 'unknown');
      assert.equal(err.readback.native_edit.applied, null);
      assert.equal(err.readback.native_edit.wrapper_compensated, false);
      assert.equal(err.readback.native_edit.internal_rollback_incomplete, true);
      assert.equal(err.rollback_conflicts.length, 1);
      assert.equal(err.rollback_conflicts[0].kind, 'internal-rollback-incomplete');
      return true;
    },
  );
  assert.equal(incNoResidual.removeCalls, 0);
  assert.equal(incNoResidual.page.children.length, 1);

  // 2) Core throws and leaves residual owned workbench/nodes on page -> partial, retained untouched (zero wrapper remove())
  const partialLeftover = createHarness();
  partialLeftover.onEnsure((_f, targetPage, contract) => {
    const wb = new partialLeftover.Node('FRAME', contract.workbench.name);
    wb.setPluginData('semanticKey', contract.workbench.frameKey);
    targetPage.appendChild(wb);
    throw Error('Partial creation aborted; rollback incomplete: Error: in remove: Removing this node is not allowed');
  });
  await assert.rejects(
    () => partialLeftover.run(),
    err => {
      assert.equal(err.readback.status, 'partial');
      assert.equal(err.readback.mutation_state, 'partial');
      assert.equal(err.readback.native_edit.applied, null);
      assert.equal(err.readback.native_edit.wrapper_compensated, false);
      assert.equal(err.readback.native_edit.observed_post_failure.workbench_present, true);
      assert.equal(err.readback.native_edit.observed_post_failure.residual_owned_node_count, 1);
      assert.equal(err.rollback_conflicts[0].kind, 'partial-owned-nodes-retained');
      return true;
    },
  );
  assert.equal(partialLeftover.removeCalls, 0);
  assert.equal(partialLeftover.page.children.length, 2);

  // 3) Core throws cleanly on fresh page with zero residual owned nodes and intact page_roots -> rolled-back, zero wrapper remove()
  const cleanCoreRollback = createHarness();
  cleanCoreRollback.onEnsure(() => {
    throw Error('Preflight inside core semantic runtime rejected contract');
  });
  await assert.rejects(
    () => cleanCoreRollback.run(),
    err => {
      assert.equal(err.readback.status, 'rolled-back');
      assert.equal(err.readback.mutation_state, 'rolled-back');
      assert.equal(err.readback.native_edit.applied, false);
      assert.equal(err.readback.native_edit.wrapper_compensated, false);
      assert.equal(err.rollback_conflicts.length, 0);
      return true;
    },
  );
  assert.equal(cleanCoreRollback.removeCalls, 0);

  // 4) Core completes creation, then post-apply discovery getter fails -> partial, created tree retained untouched (zero wrapper remove())
  const postApplyGetterFail = createHarness();
  postApplyGetterFail.failGetter();
  await assert.rejects(
    () => postApplyGetterFail.run(),
    err => {
      assert.equal(err.readback.status, 'partial');
      assert.equal(err.readback.mutation_state, 'partial');
      assert.equal(err.readback.native_edit.applied, null);
      assert.equal(err.readback.native_edit.core_completed, true);
      assert.equal(err.readback.native_edit.wrapper_compensated, false);
      assert.equal(err.rollback_conflicts[0].kind, 'post-apply-readback-failed');
      return true;
    },
  );
  assert.equal(postApplyGetterFail.removeCalls, 0);
  assert.equal(postApplyGetterFail.page.children.length, 2);

  // 5) Repeat apply on pre-existing workbench fails inside core -> unknown, existing workbench retained untouched (zero wrapper remove())
  const repeatCoreFail = createHarness();
  await repeatCoreFail.run();
  assert.equal(repeatCoreFail.removeCalls, 0);
  repeatCoreFail.onEnsure(() => {
    throw Error('CAS conflict on existing workbench');
  });
  await assert.rejects(
    () => repeatCoreFail.run(),
    err => {
      assert.equal(err.readback.status, 'unknown');
      assert.equal(err.readback.mutation_state, 'unknown');
      assert.equal(err.readback.native_edit.applied, null);
      assert.equal(err.readback.native_edit.wrapper_compensated, false);
      assert.equal(err.rollback_conflicts[0].kind, 'repeat-apply-outcome-uncertain');
      return true;
    },
  );
  assert.equal(repeatCoreFail.removeCalls, 0);
  assert.equal(repeatCoreFail.page.children.length, 2);
});
