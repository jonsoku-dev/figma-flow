/* Ordinary Design-mode text and NODE hyperlinks; no Dev Mode APIs. */
async function ensureDesignNoteBoard(figma, page, contract) {
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
