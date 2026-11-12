/* Actual importer component loop with the compiled shipped independent-axis definitions. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const root = path.join(__dirname, '..');
const runtime = fs.readFileSync(path.join(root, 'figma-bridge/code.js'), 'utf8');
const compiled = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
  'import json,sys; from pathlib import Path; r=Path(sys.argv[1]); sys.path.insert(0,str(r/"tools")); import design_system as d; p=r/"examples/regression-program/design-system"; s=json.loads((p/"design.json").read_text()); s["variant_axes"]=json.loads((p/"axes.json").read_text())["components"]; print(json.dumps(d.compile_design(s)))', root], {encoding: 'utf8'}));

test('importer authors every existing definition without inventing axis values or combinations', async () => {
  let seq = 0;
  class Node {
    constructor(type) {Object.assign(this, {id: String(++seq), type, children: [], data: {}, componentPropertyDefinitions: {}});}
    appendChild(node) {node.parent = this; this.children.push(node);}
    setPluginData(key, value) {this.data[key] = value;}
    getPluginData(key) {return this.data[key] || '';}
    addComponentProperty(name, type, defaultValue) {const key = name + '#' + this.id; this.componentPropertyDefinitions[key] = {type, defaultValue}; return key;}
  }
  const library = new Node('FRAME'), sets = [];
  const figma = {showUI() {}, ui: {}, createComponent: () => new Node('COMPONENT'), combineAsVariants(mains, parent) {
    const set = new Node('COMPONENT_SET'); parent.appendChild(set); sets.push(set);
    for (const main of mains) {main.variantProperties = Object.fromEntries([main.name.split('=')]); set.appendChild(main);}
    return set;
  }};
  const context = vm.createContext({figma, __html__: '', PAYLOAD: compiled, library, variables: new Map(), warnings: new Set(), fonts: new Map(),
    layout() {}, text(value) {return Object.assign(new Node('TEXT'), {characters: value});}, applyProps() {}, decorate: async () => {}});
  vm.runInContext(runtime, context);
  // Keep unrelated token styling out of this API fixture; the importer loop and label linking are real.
  Object.assign(context, {layout() {}, text(value) {return Object.assign(new Node('TEXT'), {characters: value});}, applyProps() {}, decorate: async () => {}});
  const start = runtime.indexOf('    const components = new Map();');
  const end = runtime.indexOf('    layoutFoundationSets(library, componentSets);', start);
  assert(start > 0 && end > start);
  await vm.runInContext('(async()=>{' + runtime.slice(start, end) + '; return {components,componentSets};})()', context);
  const authored = sets.flatMap(set => set.children.map(main => [set.name, main.name]));
  for (const [name, definition] of Object.entries(compiled.components)) {
    for (const variant of Object.keys(definition.variants)) {
      const hits = authored.filter(([setName, mainName]) => (setName === name || setName.startsWith(name + '/')) && mainName.endsWith('=' + variant));
      assert.equal(hits.length, 1, name + '/' + variant + ' must be authored exactly once');
    }
  }
  assert.equal(authored.length, Object.values(compiled.components).reduce((n, definition) => n + Object.keys(definition.variants).length, 0));
  assert(authored.some(([name, variant]) => name === 'field/Variant' && variant === 'Variant=default'));
  assert(authored.some(([name, variant]) => name === 'field/state' && variant === 'state=disabled'));
  assert(!authored.some(([, variant]) => variant.includes(',')), 'no undeclared combination');
  for (const set of sets) for (const main of set.children) {
    const key = main.children[0].componentPropertyReferences.characters;
    assert.equal(set.componentPropertyDefinitions[key].type, 'TEXT');
  }
});
