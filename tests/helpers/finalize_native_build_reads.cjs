/* API-shaped host for the unmodified normal makeDraft entrypoint. No timing claims. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const root = path.join(__dirname, '../..');
const copy = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const font = {family: 'Inter', style: 'Regular'};
const compiled = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
  'import json,sys;sys.path[:0]=sys.argv[1:];from specification_contract import spec_label_prelude,derive_specifications;from test_specification_contract import fixture;print(json.dumps({"prelude":spec_label_prelude(),"specification":derive_specifications(fixture())[1]}))',
  path.join(root, 'tools'), path.join(root, 'tests')], {encoding: 'utf8'}));


function packet(stateCount = 6) {
  const roles = [{kind: 'color', token: 'color/paper', value: '#FFFFFF'}, {kind: 'color', token: 'color/ink', value: '#111111'}];
  const states = Array.from({length: stateCount}, (_, index) => ({id: 's' + index, screen: 'screen' + index, title: 'Screen ' + index}));
  const style = {fill: 'ink', ink: 'paper', fontSize: 16, leading: 20, paddingX: 8, paddingY: 8, minHeight: 44, maxWidth: 200, radius: 4};
  const candidate = {id: 'app', title: 'Build read oracle', entry_state: states[0].id, colors: {paper: '#FFFFFF', ink: '#111111'}, fonts: {body: font},
    graph: {design_foundations: {roles}}, foundationBindings: [],
    foundations: {roles, palette: {samples: [{label: 'Open next screen', component: 'open', variant: 'Primary', action: 'open', state: 'ready', useCases: ['Open the next screen']}]}},
    action_labels: {open: 'Open'}, action_notes: {'open|open': {purpose: 'Open next screen', action: 'open', visual_variant: 'Primary'}},
    notes: states.map(state => ({id: state.screen, purpose: 'Review ' + state.title})),
    prototype: {states, bindings: []}, state_layouts: {}, control_styles: {desktop: {Primary: style}, mobile: {Primary: style}},
    references: {}, layouts: {desktop: {width: 390, height: 844}, mobile: {width: 390, height: 844}}};
  for (const viewport of ['desktop', 'mobile']) {
    candidate.state_layouts[viewport] = {};
    states.forEach((state, index) => {
      candidate.prototype.bindings.push({viewport, source_state: state.id, target_state: states[(index + 1) % states.length].id, control_id: 'open', action: 'open'});
      candidate.state_layouts[viewport][state.id] = {width: 390, height: 844, bg: 'paper', control_boxes: {open: [20, 80, 120, 44]},
        layers: [{id: 'title', kind: 'text', value: 'Title', x: 20, y: 20, w: 120, h: 20, size: 16, leading: 20, ink: 'ink'}],
        containers: [{key: 'card', kind: 'frame', children: ['title', 'open'], box: [10, 10, 370, 200], clip: true, scroll: 'horizontal'}]};
    });
  }
  return {schema: 'figma-flow-native-direction-review-v1', scope: 'exploratory-only', production_admitted: false,
    fileKey: 'synthetic-file', packet_sha256: 'a'.repeat(64), instance_sha256: 'b'.repeat(64), layout_sha256: 'c'.repeat(64),
    candidate_pins: {}, candidates: [candidate], assets: {}, boundary: {}};
}

function host(draft = packet(), corrupt = null) {
  let sequence = 0, corruptionApplied = false;
  const nodes = new Map(), styles = new Map(), collections = [], variables = [];
  const counts = {main: new Map(), segments: new Map(), semanticKeys: 0};
  const count = (map, id) => map.set(id, (map.get(id) || 0) + 1);
  const id = () => 'n' + (++sequence);
  class Node {
    constructor(type) {
      Object.assign(this, {id: id(), type, name: type, children: [], parent: null, data: {}, x: 0, y: 0, width: 100, height: 20,
        visible: true, opacity: 1, fills: [], strokes: [], effects: [], annotations: [], reactions: [], _bound: {},
        clipsContent: false, overflowDirection: 'NONE', layoutMode: 'NONE', layoutPositioning: 'AUTO',
        paddingLeft: 0, paddingRight: 0, paddingTop: 0, paddingBottom: 0, itemSpacing: 0, cornerRadius: 0,
        fontName: copy(font), fontSize: 16, lineHeight: {unit: 'PIXELS', value: 20}, letterSpacing: {unit: 'PIXELS', value: 0},
        characters: '', _textAutoResize: 'NONE', textAlignHorizontal: 'LEFT', componentPropertyReferences: {}, componentPropertyDefinitions: {}, componentProperties: {}});
      nodes.set(this.id, this);
    }
    setPluginData(key, value) {this.data[key] = String(value);}
    getPluginData(key) {if (key === 'semanticKey') counts.semanticKeys++; return this.data[key] || '';}
    get boundVariables() {return {...this._bound, ...(styles.get(this.textStyleId)?.boundVariables || {})};}
    setBoundVariable(field, variable) {if (variable) this._bound[field] = {type: 'VARIABLE_ALIAS', id: variable.id}; else delete this._bound[field];}
    appendChild(node) {this.insertChild(this.children.length, node);}
    insertChild(index, node) {
      if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1);
      node.parent = this; this.children.splice(index, 0, node);
    }
    findAll(predicate) {return this.children.flatMap(child => [...(predicate(child) ? [child] : []), ...child.findAll(predicate)]);}
    findOne(predicate) {for (const child of this.children) {if (predicate(child)) return child; const found = child.findOne(predicate); if (found) return found;} return null;}
    async loadAsync() {
      // Inject native drift at fresh page load, after parenting and before reader traversal.
      if (this.type === 'PAGE' && corrupt && !corruptionApplied) {
        const container = this.findAll(node => node.data.semanticKey?.endsWith('.card'))[0];
        if (container) {corruptionApplied = true; corrupt(container, this);}
      }
    }
    remove() {this.removed = true; if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null;}
    resize(width, height) {
      this.width = width; this.height = height;
      if (this.type === 'INSTANCE') for (const label of this.children.filter(child => child.type === 'TEXT')) {
        label.x = this.paddingLeft; label.y = (height - label.height) / 2; label.width = width - this.paddingLeft - this.paddingRight;
      }
    }
    set textAutoResize(mode) {this._textAutoResize = mode; if (this.type === 'TEXT') this.height = this.lineHeight.value;}
    get textAutoResize() {return this._textAutoResize;}
    async setTextStyleIdAsync(styleId) {
      this.textStyleId = styleId;
      const style = styles.get(styleId);
      for (const field of ['fontName', 'fontSize', 'lineHeight', 'letterSpacing']) this[field] = copy(style[field]);
    }
    getRangeAllFontNames() {return [this.fontName];}
    getRangeBoundVariable(_start, _end, field) {return this.boundVariables[field] || null;}
    setRangeBoundVariable(_start, _end, field, variable) {this.setBoundVariable(field, variable);}
    getStyledTextSegments() {count(counts.segments, this.id); return [{start: 0, end: this.characters.length, fontName: this.fontName, fontSize: this.fontSize, boundVariables: this.boundVariables}];}
    setRangeHyperlink(_start, _end, hyperlink) {this.hyperlink = hyperlink;}
    getRangeHyperlink() {return this.hyperlink || null;}
    async getMainComponentAsync() {count(counts.main, this.id); return this.main;}
    async setReactionsAsync(reactions) {this.reactions = copy(reactions);}
    addComponentProperty(name, type, defaultValue) {const key = name + '#1'; this.componentPropertyDefinitions[key] = {type, defaultValue}; return key;}
    setProperties(properties) {
      for (const [key, value] of Object.entries(properties)) {
        this.componentProperties[key] = {type: 'TEXT', value};
        for (const text of this.children.filter(node => node.componentPropertyReferences.characters === key)) text.characters = value;
      }
    }
    createInstance() {
      const instance = new Node('INSTANCE');
      const cloneFields = ['x', 'y', 'width', 'height', 'fills', 'strokes', 'effects', '_bound', 'paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom', 'cornerRadius',
        'layoutMode', 'primaryAxisAlignItems', 'counterAxisAlignItems', 'primaryAxisSizingMode', 'counterAxisSizingMode', 'characters', 'fontName', 'fontSize', 'lineHeight', 'letterSpacing', 'textAlignHorizontal', 'componentPropertyReferences', 'textStyleId', '_textAutoResize'];
      const assign = (target, source) => {for (const field of cloneFields) if (field in source) target[field] = copy(source[field]);};
      assign(instance, this); instance.main = this;
      for (const child of this.children) {const copied = new Node(child.type); assign(copied, child); instance.appendChild(copied);}
      for (const [key, definition] of Object.entries(this.parent.componentPropertyDefinitions)) instance.componentProperties[key] = {type: definition.type, value: definition.defaultValue};
      return instance;
    }
  }
  const rootNode = new Node('DOCUMENT'), initialPage = new Node('PAGE'); rootNode.appendChild(initialPage);
  const resolveVariable = variable => {
    const value = variable.valuesByMode[variable.collection.defaultModeId];
    return value?.type === 'VARIABLE_ALIAS' ? resolveVariable(variables.find(item => item.id === value.id)) : {resolvedType: variable.resolvedType, value};
  };
  const figma = {root: rootNode, currentPage: initialPage, fileKey: draft.fileKey, showUI() {}, ui: {postMessage() {}}, viewport: {scrollAndZoomIntoView() {}},
    createPage() {const page = new Node('PAGE'); page.flowStartingPoints = []; rootNode.appendChild(page); return page;},
    createFrame: () => new Node('FRAME'), createRectangle: () => new Node('RECTANGLE'), createEllipse: () => new Node('ELLIPSE'), createText: () => new Node('TEXT'), createComponent: () => new Node('COMPONENT'),
    combineAsVariants(variants, parent) {const set = new Node('COMPONENT_SET'); parent.appendChild(set); for (const node of variants) {set.appendChild(node); node.variantProperties = {Visual: node.name.slice('Visual='.length)};} return set;},
    async setCurrentPageAsync(page) {this.currentPage = page;}, async getNodeByIdAsync(key) {return nodes.get(key);},
    async listAvailableFontsAsync() {return [{fontName: font}];}, async loadFontAsync() {},
    createTextStyle() {
      const style = {id: id(), type: 'TEXT', boundVariables: {}, setBoundVariable(field, variable) {if (variable) this.boundVariables[field] = {type: 'VARIABLE_ALIAS', id: variable.id}; else delete this.boundVariables[field];}, remove() {styles.delete(this.id);}};
      styles.set(style.id, style); return style;
    },
    async getStyleByIdAsync(key) {return styles.get(key);},
    variables: {
      async getLocalVariableCollectionsAsync() {return collections;}, async getLocalVariablesAsync() {return variables;},
      async getVariableByIdAsync(key) {return variables.find(variable => variable.id === key);},
      async getVariableCollectionByIdAsync(key) {return collections.find(collection => collection.id === key);},
      createVariableCollection(name) {
        const collection = {id: id(), name, modes: [{modeId: 'mode', name: 'Mode'}], defaultModeId: 'mode', variableIds: [], data: {},
          setPluginData(key, value) {this.data[key] = value;}, getPluginData(key) {return this.data[key] || '';}, remove() {collections.splice(collections.indexOf(this), 1);}};
        collections.push(collection); return collection;
      },
      createVariable(name, collection, resolvedType) {
        const variable = {id: id(), name, collection, variableCollectionId: collection.id, resolvedType, valuesByMode: {},
          setValueForMode(mode, value) {this.valuesByMode[mode] = copy(value);}, resolveForConsumer() {return resolveVariable(this);},
          remove() {variables.splice(variables.indexOf(this), 1); collection.variableIds.splice(collection.variableIds.indexOf(this.id), 1);}};
        variables.push(variable); collection.variableIds.push(variable.id); return variable;
      },
      createVariableAlias(variable) {return {type: 'VARIABLE_ALIAS', id: variable.id};},
      setBoundVariableForPaint(paint, field, variable) {return {...copy(paint), boundVariables: {...paint.boundVariables, [field]: {type: 'VARIABLE_ALIAS', id: variable.id}}};}
    }};
  const context = vm.createContext({figma, DRAFT: draft, __html__: '', console});
  vm.runInContext(compiled.prelude, context);
  for (const file of ['semantic_tokens.js', 'native_annotations.js', 'native_semantic_read.js', 'foundation_palette.js', 'design_note_board.js', 'direction_review.js'])
    vm.runInContext(fs.readFileSync(path.join(root, 'figma-bridge', file), 'utf8'), context, {filename: file});
  return {context, figma, nodes, counts, initialPage};
}
module.exports = {host, packet, specification: compiled.specification};
