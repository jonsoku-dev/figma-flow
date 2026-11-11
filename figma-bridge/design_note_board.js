/* Ordinary Design-mode text and NODE hyperlinks; no Dev Mode APIs. */
async function ensureDesignNoteBoard(figma, page, contract) {
  if (contract?.presentation === "readable-specs") return ensureReadableSpecificationBoard(figma, page, contract);
  const fail = message => { throw new Error(`Design note board: ${message}`); };
  const key = contract?.boardKey || "design-note-board";
  if (!page?.id || typeof contract?.sourceHash !== "string" || !contract.sourceHash ||
      !contract.font?.family || !contract.font?.style || !Array.isArray(contract.notes) || !contract.notes.length)
    fail("selected page, sourceHash, explicit font and notes required");
  if (contract.notes.length > 1000) fail("at most 1000 linked notes supported");
  const width = contract.width === undefined ? 760 : contract.width;
  const fontSize = contract.fontSize === undefined ? 17 : contract.fontSize;
  if (!Number.isFinite(width) || width < 360 || !Number.isFinite(fontSize) || fontSize < 14) fail("readable width/fontSize required");
  await page.loadAsync();
  const all = [page, ...page.findAll(() => true)];
  const seen = new Set();
  const notes = contract.notes.map(note => {
    if (!note || typeof note.key !== "string" || !note.key || seen.has(note.key) || typeof note.label !== "string" || !note.label.trim()) fail("unique note keys and concrete labels required");
    seen.add(note.key);
    const matches = all.filter(node => node.id === note.targetId);
    if (matches.length !== 1 || matches[0] === page) fail(`actual selected-page target required: ${note.key}`);
    return {...note, target: matches[0]};
  });
  const owner = JSON.stringify({pageId:page.id,sourceHash:contract.sourceHash});
  const existing = all.filter(node => node.getPluginData("semanticKey") === key);
  if (existing.length > 1 || existing.some(node => node.getPluginData("designNoteBoard") !== owner)) fail("ambiguous or unowned board");
  await figma.loadFontAsync(contract.font);
  let board = existing[0];
  let created = false;
  const rollback = async () => { if (created && board && !board.removed) board.remove(); };
  const characters = note => `${note.target.name} · ${note.key}\n${note.label}\n화면·조작으로 이동`;
  try {
    if (!board) {
      board = figma.createFrame(); created = true; page.appendChild(board);
      board.name = contract.title || "화면·조작 주석 목차 · Design";
      board.setPluginData("semanticKey", key); board.setPluginData("designNoteBoard", owner);
      board.layoutMode = "VERTICAL"; board.resize(width, 100);
      board.primaryAxisSizingMode = "AUTO"; board.counterAxisSizingMode = "FIXED"; board.paddingTop = board.paddingRight = board.paddingBottom = board.paddingLeft = 24;
      board.itemSpacing = 24; board.clipsContent = false;
      board.fills = [{type:"SOLID",color:{r:1,g:1,b:1}}];
      board.x = contract.x === undefined ? Math.max(0,...page.children.filter(node=>node!==board).map(node=>node.x+node.width)) + 64 : contract.x;
      board.y = contract.y === undefined ? 0 : contract.y;
      const makeText = async (text, semantic) => {
        const node = figma.createText(); board.appendChild(node);
        node.name = semantic; node.setPluginData("semanticKey", semantic);
        node.fontName = contract.font; node.fontSize = fontSize; node.characters = text;
        node.resize(width - 48, node.height); node.textAutoResize = "HEIGHT";
        node.fills = [{type:"SOLID",color:{r:0,g:0,b:0}}];
        if (contract.styleText) await contract.styleText(node);
        if (node.fontSize < 14) fail("styled board text is too small");
        return node;
      };
      await makeText(`${board.name}\n일반 Design 모드에서 읽고, 각 주석의 링크로 실제 대상으로 이동합니다.`, key + ":title");
      for (const note of notes) {
        const node = await makeText(characters(note), key + ":" + note.key);
        if (typeof node.setRangeHyperlink !== "function") fail("native text hyperlink API unavailable");
        node.setRangeHyperlink(0, node.characters.length, {type:"NODE",value:note.targetId});
      }
    }
    if (created) { board.primaryAxisSizingMode = "AUTO"; board.counterAxisSizingMode = "FIXED"; }
    if (board.type !== "FRAME" || board.parent !== page || board.visible === false || board.layoutMode !== "VERTICAL" || board.itemSpacing <= 0) fail("visible selected-page board required");
    const entries = notes.map(note => {
      const matches = board.children.filter(node => node.getPluginData("semanticKey") === key + ":" + note.key);
      const node = matches[0];
      if (matches.length !== 1 || node.type !== "TEXT" || node.visible === false || node.characters !== characters(note) || node.fontSize < 14 || typeof node.getRangeHyperlink !== "function") fail(`visible linked text not retained: ${note.key}`);
      const link = node.getRangeHyperlink(0,node.characters.length);
      if (!link || link.type !== "NODE" || link.value !== note.targetId) fail(`native target hyperlink not retained: ${note.key}`);
      return {key:note.key,textNodeId:node.id,targetId:note.targetId,label:note.label};
    });
    return {boardId:board.id,entries,rollback};
  } catch (error) { await rollback(); throw error; }
}
if (typeof module !== "undefined") module.exports = {ensureDesignNoteBoard};

async function ensureReadableSpecificationBoard(figma, page, contract) {
  const fail = message => { throw new Error(`Design specification board: ${message}`); };
  const key = contract.boardKey || "design-note-board";
  const revisionKey = "figmaFlowSpecificationEntry";
  const copy = value => JSON.parse(JSON.stringify(value));
  const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
  if (!page?.id || typeof contract.sourceHash !== "string" || !contract.sourceHash || !contract.font?.family || !contract.font?.style || !Array.isArray(contract.notes) || !contract.notes.length || contract.notes.length > 1000) fail("page, sourceHash, explicit font and notes required");
  const width = contract.width ?? 760, fontSize = contract.fontSize ?? 17;
  if (!Number.isFinite(width) || width < 360 || !Number.isFinite(fontSize) || fontSize < 14) fail("readable width/fontSize required");
  await page.loadAsync();
  const all = [page,...page.findAll(() => true)], seen = new Set();
  const owner = JSON.stringify({pageId:page.id,sourceHash:contract.sourceHash});
  const candidates = all.filter(node => node.getPluginData("semanticKey") === key);
  if (candidates.length > 1 || candidates.some(node => node.getPluginData("designNoteBoard") !== owner)) fail("ambiguous or unowned board");
  let board = candidates[0], created = false;
  const characters = spec => `${spec.title}\n${spec.display_text}`;
  const notes = contract.notes.map(note => {
    const spec = note?.specification;
    if (!note?.key || seen.has(note.key) || !spec || spec.schema !== FLOW_SPEC.schemas.readable || typeof spec.title !== "string" || !spec.title.trim() || typeof spec.display_text !== "string" || !spec.display_text.trim() || typeof spec.id !== "string" || typeof spec.meaning_sha256 !== "string") fail("unique keys and compiled readable specifications required");
    seen.add(note.key);
    if (all.filter(node => node.id === note.targetId && node !== page).length !== 1) fail(`actual selected-page target required ${note.key}`);
    return {...note,characters:characters(spec),revision:JSON.stringify({key:note.key,targetId:note.targetId,specification_id:spec.id,meaning_sha256:spec.meaning_sha256,characters:characters(spec)})};
  });
  const snapshots = [], newNodes = [], newText = new Map();
  if (contract.expectedEntries !== undefined && !Array.isArray(contract.expectedEntries)) fail("expectedEntries must be snapshots");
  const expectedEntries = contract.expectedEntries || [];
  const expectedIds = new Set();
  for (const expected of expectedEntries) {
    if (!expected?.textNodeId || typeof expected.key !== "string" || typeof expected.characters !== "string" || expectedIds.has(expected.textNodeId)) fail("ambiguous expected board entry");
    expectedIds.add(expected.textNodeId);
    const node = board?.children.find(node => node.id === expected.textNodeId);
    if (!node || node.getPluginData("semanticKey") !== expected.key || node.characters !== expected.characters || !same(node.getRangeHyperlink?.(0,node.characters.length) || null,expected.hyperlink)) fail("board entry snapshot conflict");
  }
  if (board) {
    if (board.type !== "FRAME" || board.parent !== page || board.visible === false || board.layoutMode !== "VERTICAL" || board.itemSpacing <= 0) fail("visible selected-page board required");
    const childKeys = new Set();
    for (const node of board.children) {
      const semantic = node.getPluginData("semanticKey");
      if (node.type !== "TEXT" || node.visible === false || node.fontSize < 14 || !semantic.startsWith(key + ":") || childKeys.has(semantic)) fail("unknown or ambiguous board child");
      childKeys.add(semantic);
      const expected = expectedEntries.find(item => item.textNodeId === node.id);
      if (semantic === key + ":title") {
        if (!expected && node.characters !== board.name) fail("unowned board heading");
        continue;
      }
      const marker = node.getPluginData(revisionKey);
      if (!marker) {
        if (!expected || expected.hyperlink?.type !== "NODE" || all.filter(target => target.id === expected.hyperlink.value && target !== page).length !== 1) fail("unowned board child");
        if (!contract.partial && !seen.has(semantic.slice(key.length + 1))) fail("complete board update must include existing entries");
        continue;
      }
      let prior;
      try { prior = JSON.parse(marker); } catch (_) { fail("unowned board child"); }
      const link = node.getRangeHyperlink?.(0,node.characters.length);
      if (!prior || semantic !== key + ":" + prior.key || node.characters !== prior.characters || link?.type !== "NODE" || link.value !== prior.targetId) fail("edited or unowned board child");
      if (!contract.partial && !seen.has(prior.key)) fail("complete board update must include existing entries");
    }
  }
  const beforePosition = board ? {x:board.x,y:board.y} : null;
  const beforeEntries = board ? board.children.map(node => ({node,semantic:node.getPluginData("semanticKey"),characters:node.characters,link:copy(node.getRangeHyperlink(0,node.characters.length) || null),revision:node.getPluginData(revisionKey)})) : [];
  const unchanged = before => before.node.parent === board && before.node.getPluginData("semanticKey") === before.semantic && before.node.characters === before.characters && same(before.node.getRangeHyperlink(0,before.node.characters.length) || null,before.link) && before.node.getPluginData(revisionKey) === before.revision;
  await figma.loadFontAsync(contract.font);
  if (board && (board.getPluginData("designNoteBoard") !== owner || board.x !== beforePosition.x || board.y !== beforePosition.y || board.children.length !== beforeEntries.length || !beforeEntries.every(unchanged))) fail("concurrent board preflight conflict");
  let relocatedTo = null;
  const rollback = async () => {
    if (board && board.getPluginData("designNoteBoard") !== owner) fail("concurrent board ownership conflict");
    const errors = [];
    if (relocatedTo) {
      if (board.x !== relocatedTo.x || board.y !== relocatedTo.y) errors.push("concurrent board position conflict");
      else { board.x = beforePosition.x; board.y = beforePosition.y; }
    }
    for (const snap of snapshots.slice().reverse()) {
      try {
        const currentLink = snap.node.getRangeHyperlink(0,snap.node.characters.length);
        if (snap.node.getPluginData("semanticKey") !== snap.semantic || ![snap.characters,snap.writtenCharacters].includes(snap.node.characters) || (!same(currentLink,snap.writtenLink) && !same(currentLink,snap.link)) || ![snap.revision,snap.writtenRevision].includes(snap.node.getPluginData(revisionKey))) fail("concurrent board text conflict");
        snap.node.characters = snap.characters;
        snap.node.setRangeHyperlink(0,snap.characters.length,snap.link);
        snap.node.setPluginData(revisionKey,snap.revision);
        if (snap.node.characters !== snap.characters || !same(snap.node.getRangeHyperlink(0,snap.characters.length),snap.link) || snap.node.getPluginData(revisionKey) !== snap.revision) fail("board restoration not retained");
      } catch (error) { errors.push(error.message || String(error)); }
    }
    for (const node of newNodes.slice().reverse()) {
      if (node.removed) continue;
      const note = notes.find(note => key + ":" + note.key === node.getPluginData("semanticKey"));
      if (node.characters !== newText.get(node).text || node.getPluginData("semanticKey") !== newText.get(node).semantic || (note && !["",note.revision].includes(node.getPluginData(revisionKey))) || (note && node.getRangeHyperlink?.(0,node.characters.length) && !same(node.getRangeHyperlink(0,node.characters.length),{type:"NODE",value:note.targetId}))) { errors.push("concurrent new board text conflict"); continue; }
      node.remove();
    }
    if (created && board && !board.removed) {
      if (board.getPluginData("designNoteBoard") === owner && board.children.length === 0) board.remove();
      else errors.push("created board has external children or ownership conflict");
    }
    if (errors.length) fail(`rollback incomplete: ${errors.join("; ")}`);
  };
  const makeText = async (text,semantic) => {
    const node = figma.createText(); board.appendChild(node); newNodes.push(node); newText.set(node,{text,semantic});
    node.name = semantic; node.setPluginData("semanticKey",semantic);
    node.fontName = contract.font; node.fontSize = fontSize; node.characters = text;
    node.resize(width - 48,node.height); node.textAutoResize = "HEIGHT";
    node.fills = [{type:"SOLID",color:{r:0,g:0,b:0}}];
    if (contract.styleText) await contract.styleText(node);
    if (node.fontSize < 14) fail("styled board text is too small");
    return node;
  };
  try {
    if (!board) {
      board = figma.createFrame(); created = true; page.appendChild(board);
      board.name = contract.title || "화면 설명";
      board.setPluginData("semanticKey",key); board.setPluginData("designNoteBoard",owner);
      board.layoutMode = "VERTICAL"; board.resize(width,100);
      board.primaryAxisSizingMode = "AUTO"; board.counterAxisSizingMode = "FIXED";
      board.paddingTop = board.paddingRight = board.paddingBottom = board.paddingLeft = 24;
      board.itemSpacing = 24; board.clipsContent = false;
      board.fills = [{type:"SOLID",color:{r:1,g:1,b:1}}];
      board.x = Math.max(0,...page.children.filter(node => node !== board).map(node => node.x + node.width)) + 64;
      board.y = 0;
      await makeText(board.name,key + ":title");
    }
    for (const note of notes) {
      let node = board.children.find(node => node.getPluginData("semanticKey") === key + ":" + note.key);
      const link = {type:"NODE",value:note.targetId};
      if (node) {
        const before = beforeEntries.find(before => before.node === node);
        if (!before || !unchanged(before)) fail("concurrent board entry conflict");
        if (node.characters === note.characters && node.getPluginData(revisionKey) === note.revision) continue;
        snapshots.push({node,semantic:node.getPluginData("semanticKey"),characters:node.characters,link:copy(node.getRangeHyperlink(0,node.characters.length)),revision:node.getPluginData(revisionKey),writtenCharacters:note.characters,writtenLink:link,writtenRevision:note.revision});
        node.characters = note.characters;
      } else node = await makeText(note.characters,key + ":" + note.key);
      node.setRangeHyperlink(0,node.characters.length,link);
      node.setPluginData(revisionKey,note.revision);
      if (node.characters !== note.characters || !same(node.getRangeHyperlink(0,node.characters.length),link) || node.getPluginData(revisionKey) !== note.revision) fail(`native target hyperlink not retained ${note.key}`);
    }
    const box = node => node.absoluteBoundingBox || {x:node.x,y:node.y,width:node.width,height:node.height};
    const overlaps = () => { const bounds = box(board); return page.children.some(node => node !== board && node.visible !== false && (() => { const other = box(node); return bounds.x < other.x + other.width && bounds.x + bounds.width > other.x && bounds.y < other.y + other.height && bounds.y + bounds.height > other.y; })()); };
    let changed = (created ? notes.length : snapshots.length + newNodes.length);
    if (overlaps()) {
      if (!notes.some(note => note.specification.presentation === "connected-spec-v2")) fail("board overlaps artwork after update");
      if (board.x !== beforePosition?.x || board.y !== beforePosition?.y) fail("concurrent board position conflict");
      const x = Math.max(0,...page.children.filter(node => node !== board).map(node => { const other = box(node); return other.x + other.width; })) + 64;
      board.x = x; board.y = 0;
      relocatedTo = {x,y:0};
      if (overlaps()) fail("board overlaps artwork after reflow");
      changed++;
    }
    return {boardId:board.id,changed,entries:notes.map(note => ({key:note.key,textNodeId:board.children.find(node => node.getPluginData("semanticKey") === key + ":" + note.key).id,targetId:note.targetId,label:note.specification.title,displayText:note.specification.display_text,specification_id:note.specification.id,meaning_sha256:note.specification.meaning_sha256})),rollback};
  } catch (error) {
    try { await rollback(); } catch (rollbackError) { throw new Error(`${error.message}; ${rollbackError.message}`); }
    throw error;
  }
}
