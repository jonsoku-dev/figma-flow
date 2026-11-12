const assert = require('node:assert/strict');
const {readNativeSemantics, nativeReadSessionSnapshot} = require('../figma-bridge/native_semantic_read.js');

// Supplemental native API fixture, not a Figma event/cache integration test.
// The caller owns file/page scope and supplies the matching API and selected page;
// this reader does not validate fileKey or discover a newly selected page itself.
const fields = ['x', 'y', 'width', 'height', 'visible'];
const alias = id => ({type: 'VARIABLE_ALIAS', id});
const row = (snapshot, id) => snapshot.nodes.find(node => node.id === id);
const variable = (snapshot, id) => snapshot.variables.find(item => item.id === id);

function node(id, type = 'RECTANGLE') {
  return {
    id, type, name: id, children: [], x: 1, y: 2, width: 30, height: 20, visible: true,
    fills: [], getPluginData: () => '', async loadAsync() { this.loads = (this.loads || 0) + 1; },
    findAll(predicate) {
      const visit = parent => parent.children.flatMap(child => [child, ...visit(child)]);
      return visit(this).filter(predicate);
    },
  };
}

function attach(parent, child) {
  if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1);
  child.parent = parent;
  parent.children.push(child);
}

function world(fileKey, value) {
  const reads = {style: 0, variable: 0, collection: 0, local: 0, image: 0, heavy: 0};
  const page = node('page', 'PAGE');
  const frame = node('frame', 'FRAME');
  const text = node('text', 'TEXT');
  attach(page, frame);
  attach(frame, text);
  const state = {characters: fileKey, color: {r: 1, g: 0, b: 0}, bytes: Uint8Array.from([value, 2, 3]), hash: 'image'};
  text.fillStyleId = 'style';
  text.boundVariables = {width: alias('token')};
  text.getPluginData = key => key === 'rasterAsset' ? 'photo' : '';
  Object.defineProperty(text, 'characters', {get() { reads.heavy++; return state.characters; }});
  Object.defineProperty(text, 'fills', {get() { reads.heavy++; return [{type: 'IMAGE', imageHash: state.hash, scaleMode: 'FIT'}]; }});
  text.getStyledTextSegments = () => {
    reads.heavy++;
    return [{start: 0, end: state.characters.length, characters: state.characters, boundVariables: {width: alias('token')}}];
  };
  const style = {id: 'style', type: 'PAINT', name: fileKey};
  Object.defineProperty(style, 'paints', {get() { reads.heavy++; return [{type: 'SOLID', color: state.color}]; }});
  const variables = new Map([
    ['token', {id: 'token', name: fileKey, resolvedType: 'FLOAT', variableCollectionId: 'main', valuesByMode: {mode: alias('leaf-a')}}],
    ['leaf-a', {id: 'leaf-a', name: 'first', resolvedType: 'FLOAT', variableCollectionId: 'collection-a', valuesByMode: {mode: value}}],
    ['leaf-b', {id: 'leaf-b', name: 'second', resolvedType: 'FLOAT', variableCollectionId: 'collection-b', valuesByMode: {mode: value + 1}}],
  ]);
  const collections = new Map(['main', 'collection-a', 'collection-b'].map((id, index) => [id, {
    id, name: `${fileKey}-${id}`, modes: [{modeId: 'mode', name: 'Default'}], defaultModeId: 'mode',
    variableIds: [['token'], ['leaf-a'], ['leaf-b']][index], getPluginData: () => '',
  }]));
  const figma = {
    fileKey,
    async getStyleByIdAsync(id) { reads.style++; return id === style.id ? style : null; },
    getImageByHash(hash) {
      assert.equal(hash, state.hash);
      return {async getBytesAsync() { reads.image++; return state.bytes; }};
    },
    base64Encode: bytes => Buffer.from(bytes).toString('base64'),
    variables: {
      async getLocalVariableCollectionsAsync() { reads.local++; return []; },
      async getVariableByIdAsync(id) { reads.variable++; return variables.get(id); },
      async getVariableCollectionByIdAsync(id) { reads.collection++; return collections.get(id); },
    },
  };
  return {figma, page, frame, text, state, reads, variables};
}

(async () => {
  const saved = [];
  let previous;
  let cases = 0;
  async function readPair(env, page = env.page) {
    const full = await readNativeSemantics(env.figma, page);
    const nodeIds = [page, ...page.findAll(() => true)].map(item => item.id);
    const beforeSummary = {...env.reads};
    const summary = await readNativeSemantics(env.figma, page, {profile: 'summary', nodeIds, fields});
    assert.deepEqual(env.reads, beforeSummary, 'summary must not read heavy getters or dependency APIs');
    assert.equal(summary.schema, 'figma-flow-native-read-summary-v1');
    assert.deepEqual(summary.coverage.fields, fields);
    assert.equal(summary.coverage.complete, false);
    for (const omitted of ['styles', 'variables', 'collections', 'rasterImages', 'textSegments']) {
      assert.ok(summary.coverage.omitted.includes(omitted));
      assert.equal(Object.hasOwn(summary, omitted), false);
    }
    assert.deepEqual(full.nodes.map(item => item.id), nodeIds);
    assert.deepEqual(summary.nodes.map(item => item.id), nodeIds);
    for (const item of summary.nodes) {
      assert.deepEqual(Object.keys(item).sort(), ['id', 'parentId', 'type', 'name', ...fields].sort());
      for (const field of ['parentId', 'name', ...fields]) assert.deepEqual(item[field], row(full, item.id)[field]);
      if (previous && row(previous.summary, item.id)) {
        assert.notStrictEqual(item, row(previous.summary, item.id));
        assert.notStrictEqual(row(full, item.id), row(previous.full, item.id));
      }
    }
    if (previous) {
      assert.notStrictEqual(full, previous.full);
      assert.notStrictEqual(summary, previous.summary);
      assert.notStrictEqual(full.nodes, previous.full.nodes);
      assert.notStrictEqual(full.variables, previous.full.variables);
    }
    assert.equal(nativeReadSessionSnapshot(), null);
    saved.push([full, JSON.stringify(full)], [summary, JSON.stringify(summary)]);
    for (const [snapshot, serialized] of saved) assert.ok(JSON.stringify(snapshot) === serialized, 'earlier raw snapshots must remain unchanged');
    previous = {full, summary};
    cases++;
    return previous;
  }

  const env = world('file-a', 10);
  let result = await readPair(env);
  assert.equal(row(result.full, 'text').characters, 'file-a');
  assert.equal(variable(result.full, 'leaf-a').valuesByMode.mode, 10);
  assert.deepEqual([...result.full.collectionIds].sort(), ['collection-a', 'main']);
  assert.equal(result.full.rasterImages.image, 'CgID');
  assert.equal(result.full.styles[0].paints[0].color.r, 1);

  const added = node('added');
  attach(env.frame, added);
  result = await readPair(env);
  assert.equal(row(result.full, 'added').parentId, 'frame');
  assert.equal(row(result.summary, 'added').width, 30);

  attach(env.page, added);
  added.x = 90;
  result = await readPair(env);
  assert.equal(row(result.full, 'added').parentId, 'page');
  assert.equal(row(result.summary, 'added').parentId, 'page');
  assert.equal(row(result.summary, 'added').x, 90);

  env.page.children.splice(env.page.children.indexOf(added), 1);
  added.parent = null;
  result = await readPair(env);
  assert.equal(row(result.full, 'added'), undefined);
  assert.equal(row(result.summary, 'added'), undefined);
  await assert.rejects(() => readNativeSemantics(env.figma, env.page, {profile: 'summary', nodeIds: ['added'], fields}), /summary node missing/);

  env.state.characters = 'Changed text';
  env.text.x = 7;
  env.text.y = 9;
  env.text.width = 75;
  env.text.height = 42;
  env.text.visible = false;
  result = await readPair(env);
  assert.equal(row(result.full, 'text').characters, 'Changed text');
  assert.equal(row(result.full, 'text').textSegments[0].characters, 'Changed text');
  for (const field of fields) assert.equal(row(result.summary, 'text')[field], env.text[field]);

  env.state.color.r = 0.25;
  const styleReads = env.reads.style;
  result = await readPair(env);
  assert.equal(result.full.styles[0].paints[0].color.r, 0.25);
  assert.equal(env.reads.style, styleReads + 1);

  env.variables.get('leaf-a').valuesByMode.mode = 99;
  result = await readPair(env);
  assert.equal(variable(result.full, 'leaf-a').valuesByMode.mode, 99);
  env.variables.get('token').valuesByMode.mode.id = 'leaf-b';
  result = await readPair(env);
  assert.equal(variable(result.full, 'leaf-a'), undefined);
  assert.equal(variable(result.full, 'leaf-b').valuesByMode.mode, 11);
  assert.deepEqual([...result.full.collectionIds].sort(), ['collection-b', 'main']);

  // Same-hash byte replacement is synthetic: it proves per-request API reads.
  env.state.bytes[0] = 20;
  const imageReads = env.reads.image;
  result = await readPair(env);
  assert.equal(result.full.rasterImages.image, 'FAID');
  assert.equal(env.reads.image, imageReads + 1);
  env.state.hash = 'replacement';
  env.state.bytes = Uint8Array.from([4, 5, 6]);
  result = await readPair(env);
  assert.deepEqual({...result.full.rasterImages}, {replacement: 'BAUG'});
  assert.equal(row(result.full, 'text').rasterImageRef, 'replacement');

  const otherPage = node('other-page', 'PAGE');
  const otherText = node('other-text', 'TEXT');
  otherText.characters = 'Other page';
  attach(otherPage, otherText);
  env.figma.currentPage = otherPage;
  result = await readPair(env, env.figma.currentPage);
  assert.equal(result.full.pageId, 'other-page');
  assert.equal(row(result.full, 'text'), undefined);
  assert.equal(row(result.summary, 'other-text').parentId, 'other-page');
  assert.equal(row(result.full, 'other-text').characters, 'Other page');
  assert.deepEqual(result.full.variables, []);
  assert.deepEqual(result.full.styles, []);
  assert.deepEqual({...result.full.rasterImages}, {});
  result = await readPair(env, env.page);
  assert.equal(row(result.full, 'text').characters, 'Changed text');
  assert.equal(variable(result.full, 'leaf-b').valuesByMode.mode, 11);

  // Deliberately reuse native IDs across files to detect leaked dependency maps.
  const otherFile = world('file-b', 50);
  result = await readPair(otherFile);
  assert.equal(row(result.full, 'text').characters, 'file-b');
  assert.equal(result.full.styles[0].name, 'file-b');
  assert.equal(variable(result.full, 'token').name, 'file-b');
  assert.equal(variable(result.full, 'leaf-a').valuesByMode.mode, 50);
  assert.equal(variable(result.full, 'leaf-b'), undefined);
  assert.equal(result.full.collections.find(item => item.id === 'main').name, 'file-b-main');
  assert.equal(result.full.rasterImages.image, 'MgID');
  assert.equal(row(result.summary, 'text').width, 30);
  result = await readPair(env);
  assert.equal(result.full.styles[0].name, 'file-a');
  assert.equal(variable(result.full, 'leaf-b').valuesByMode.mode, 11);
  assert.deepEqual({...result.full.rasterImages}, {replacement: 'BAUG'});
  console.log(`PASS: ${cases} full/summary fresh-read pairs; tree, text, style, variable closure, raster, page and file scope`);
})().catch(error => { console.error(error); process.exitCode = 1; });
