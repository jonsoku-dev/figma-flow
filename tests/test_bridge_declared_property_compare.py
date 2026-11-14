import copy
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from design_system import compile_design
from figma_bridge import compare_declared_component_properties


NODE_SNAPSHOT_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const root = input.root;
const mode = input.mode;
const runtime = fs.readFileSync(path.join(root, 'figma-bridge', 'code.js'), 'utf8');

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
    const existing = Object.entries(this.componentPropertyDefinitions).filter(
      ([k]) => k.startsWith(name + '#')
    );
    if (existing.length > 0 && mode === 'overwrite') {
      const [existingKey] = existing[0];
      this.componentPropertyDefinitions[existingKey] = {
        type,
        defaultValue,
        ...(options || {}),
      };
      return existingKey;
    }
    const nativeBase =
      existing.length > 0 && mode === 'auto-rename'
        ? `${name} ${existing.length + 1}`
        : name;
    const key = `${nativeBase}#${this.id}:${++propSeq}`;
    this.componentPropertyDefinitions[key] = {
      type,
      defaultValue,
      ...(options || {}),
    };
    return key;
  }
  editComponentProperty(key, patch) {
    if (!Object.prototype.hasOwnProperty.call(this.componentPropertyDefinitions, key)) {
      throw new Error('missing key: ' + key);
    }
    this.componentPropertyDefinitions[key] = {
      ...this.componentPropertyDefinitions[key],
      ...patch,
    };
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

const page = new Node('PAGE');
page.setPluginData(
  'figmaFlow',
  JSON.stringify({semantic_id: 'design-import', bridge: 1, source_sha256: 'a'.repeat(64), complete: true})
);
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
  PAYLOAD: input.payload,
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
  page,
});

(async () => {
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
      const hasExplicitLabelOverride = Object.entries(
        context.PAYLOAD.components[element.component]?.properties || {}
      ).some(
        ([pid, p]) =>
          p.type === 'TEXT' &&
          p.target === 'label' &&
          Object.prototype.hasOwnProperty.call(element.property_values || {}, pid)
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
  const observed = await vm.runInContext('snapshot(page)', context);
  context.observed = observed;
  vm.runInContext('verifyDeclaredComponentReadback(PAYLOAD, observed)', context);
  process.stdout.write(JSON.stringify({observed, expected: context.PAYLOAD}));
})().catch(err => {
  console.error(err);
  process.exit(1);
});
"""


def run_node_snapshot(mode: str):
    fixture = json.loads((ROOT / "tests" / "fixtures" / "nf01" / "six-families.json").read_text(encoding="utf-8"))
    payload = compile_design(fixture)
    proc = subprocess.run(
        ["node", "-e", NODE_SNAPSHOT_HARNESS],
        input=json.dumps({"root": str(ROOT), "mode": mode, "payload": payload}),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def find_node(root: dict, semantic_id: str):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.get("semantic_id") == semantic_id:
            return node
        stack.extend(node.get("children", []))
    return None


class BridgeDeclaredPropertyCompareTests(unittest.TestCase):
    def test_accepts_disambiguated_duplicate_display_keys_from_real_code_js_snapshot(self):
        data = run_node_snapshot("overwrite")
        observed, expected = data["observed"], data["expected"]
        table_row = find_node(observed, "component:table-row/default")
        self.assertIsNotNone(table_row)
        keys = table_row["declared_metadata"]["declared_property_keys"]
        self.assertTrue(keys["firstCell"].startswith("Cell#"))
        self.assertTrue(keys["secondCell"].startswith("Cell (secondCell)#"))

        checks = compare_declared_component_properties(observed, expected)
        self.assertGreater(len(checks), 0)
        non_match = [c for c in checks if c["status"] != "match"]
        self.assertEqual(non_match, [])

    def test_accepts_figma_auto_renamed_keys_from_real_code_js_snapshot(self):
        data = run_node_snapshot("auto-rename")
        observed, expected = data["observed"], data["expected"]
        table_row = find_node(observed, "component:table-row/default")
        self.assertIsNotNone(table_row)
        keys = table_row["declared_metadata"]["declared_property_keys"]
        self.assertTrue(keys["firstCell"].startswith("Cell#"))
        self.assertTrue(keys["secondCell"].startswith("Cell 2#"))

        checks = compare_declared_component_properties(observed, expected)
        self.assertGreater(len(checks), 0)
        non_match = [c for c in checks if c["status"] != "match"]
        self.assertEqual(non_match, [])

    def test_rejects_shared_keys_contract_mismatches_missing_definitions_and_unsuffixed_keys(self):
        base = run_node_snapshot("overwrite")

        # 1. Non-distinct declared keys across two logical properties
        shared = copy.deepcopy(base)
        row = find_node(shared["observed"], "component:table-row/default")
        row["declared_metadata"]["declared_property_keys"]["secondCell"] = row["declared_metadata"]["declared_property_keys"]["firstCell"]
        shared_defs = [
            c for c in compare_declared_component_properties(shared["observed"], shared["expected"])
            if c["semantic_id"] == "component:table-row/default" and c["scope"] == "definition"
        ]
        self.assertTrue(all(c["status"] == "changed" for c in shared_defs))

        # 2. Missing native definition on component set owner
        missing_def = copy.deepcopy(base)
        row_m = find_node(missing_def["observed"], "component:table-row/default")
        row_set = find_node(missing_def["observed"], "component-set:table-row")
        second_key = row_m["declared_metadata"]["declared_property_keys"]["secondCell"]
        del row_set["componentPropertyDefinitions"][second_key]
        missing_check = [
            c for c in compare_declared_component_properties(missing_def["observed"], missing_def["expected"])
            if c["semantic_id"] == "component:table-row/default" and c["property"] == "secondCell" and c["scope"] == "definition"
        ]
        self.assertEqual([c["status"] for c in missing_check], ["changed"])

        # 3. Contract authored display name mismatch
        bad_name = copy.deepcopy(base)
        row_bn = find_node(bad_name["observed"], "component:table-row/default")
        row_bn["declared_metadata"]["declared_property_contracts"]["secondCell"]["name"] = "WrongDisplay"
        bad_name_check = [
            c for c in compare_declared_component_properties(bad_name["observed"], bad_name["expected"])
            if c["semantic_id"] == "component:table-row/default" and c["property"] == "secondCell" and c["scope"] == "definition"
        ]
        self.assertEqual([c["status"] for c in bad_name_check], ["changed"])

        # 4. Contract actual_key mismatch
        bad_actual_key = copy.deepcopy(base)
        row_bak = find_node(bad_actual_key["observed"], "component:table-row/default")
        row_bak["declared_metadata"]["declared_property_contracts"]["secondCell"]["actual_key"] = "Cell#999:999"
        bad_key_check = [
            c for c in compare_declared_component_properties(bad_actual_key["observed"], bad_actual_key["expected"])
            if c["semantic_id"] == "component:table-row/default" and c["property"] == "secondCell" and c["scope"] == "definition"
        ]
        self.assertEqual([c["status"] for c in bad_key_check], ["changed"])

        # 5. Un-suffixed key rejected
        unsuffixed = copy.deepcopy(base)
        row_u = find_node(unsuffixed["observed"], "component:table-row/default")
        row_set_u = find_node(unsuffixed["observed"], "component-set:table-row")
        old_key = row_u["declared_metadata"]["declared_property_keys"]["secondCell"]
        row_set_u["componentPropertyDefinitions"]["Cell"] = row_set_u["componentPropertyDefinitions"].pop(old_key)
        row_u["declared_metadata"]["declared_property_keys"]["secondCell"] = "Cell"
        row_u["declared_metadata"]["declared_property_contracts"]["secondCell"]["actual_key"] = "Cell"
        unsuffixed_check = [
            c for c in compare_declared_component_properties(unsuffixed["observed"], unsuffixed["expected"])
            if c["semantic_id"] == "component:table-row/default" and c["property"] == "secondCell" and c["scope"] == "definition"
        ]
        self.assertEqual([c["status"] for c in unsuffixed_check], ["changed"])


if __name__ == "__main__":
    unittest.main()
