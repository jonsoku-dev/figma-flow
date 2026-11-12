/* Project-owned native notes; labels remain readable in Figma's annotation panel. */
function indexAnnotationNodes(nodes) {
  const byKey = new Map();
  for (const node of nodes) {
    const key = node.getPluginData("semanticKey");
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(node);
  }
  return byKey;
}

async function ensureNativeAnnotations(figma, page, contract) {
  if (contract?.presentation === "readable-specs") return ensureReadableNativeSpecifications(figma, page, contract);
  const fail = message => { throw new Error(`Native annotations: ${message}`); };
  if (!page || !Array.isArray(contract?.annotations)) fail("page and annotations are required");
  await page.loadAsync();
  const nodes = [page, ...page.findAll(() => true)];
  const seen = new Set(), byKey = indexAnnotationNodes(nodes);
  const jobs = contract.annotations.map(note => {
    if (!note || typeof note.key !== "string" || !note.key || seen.has(note.key) || typeof note.label !== "string" || !note.label.trim()) fail("unique keys and nonempty readable labels are required");
    seen.add(note.key);
    if (note.properties !== undefined && (!Array.isArray(note.properties) || note.properties.some(value => typeof value !== "string" || !value))) fail(`invalid properties for ${note.key}`);
    const matches = byKey.get(note.key) || [];
    if (matches.length !== 1) fail(`missing or ambiguous semanticKey ${note.key}`);
    const node = matches[0];
    if (!("annotations" in node) || !Array.isArray(node.annotations)) fail(`unsupported annotations on ${note.key}`);
    const prefix = `[figma-flow:${note.key}] `;
    const annotation = { label: prefix + note.label.trim() };
    if (note.properties !== undefined) annotation.properties = note.properties.map(type => ({ type }));
    return { key: note.key, node, prefix, annotation };
  });
  const sameNote = (actual, expected) => {
    if (!actual || Object.entries(expected).some(([key, value]) => key !== "properties" && actual[key] !== value)) return false;
    const types = note => (note.properties || []).map(property => property.type).sort();
    return JSON.stringify(types(actual)) === JSON.stringify(types(expected));
  };
  const sameNotes = (actual, expected) => actual.length === expected.length && expected.every((note, index) => sameNote(actual[index], note));
  const undo = [];
  let rolledBack = false;
  const rollback = async () => {
    if (rolledBack) return;
    const errors = [];
    for (const job of undo.slice().reverse()) {
      try {
        // Restore our slot only, so notes added by someone else after this call survive.
        const current = job.node.annotations.filter(note => !note.label?.startsWith(job.prefix));
        job.node.annotations = [...current, ...job.previous];
        const restored = job.node.annotations.filter(note => note.label?.startsWith(job.prefix));
        if (!sameNotes(restored, job.previous)) fail(`rollback not retained on ${job.key}`);
      } catch (error) { errors.push(error.message || String(error)); }
    }
    if (errors.length) fail(`rollback incomplete: ${errors.join("; ")}`);
    rolledBack = true;
  };
  try {
    for (const job of jobs) {
      const previous = job.node.annotations.filter(note => note.label?.startsWith(job.prefix));
      if (sameNotes(previous, [job.annotation])) continue;
      undo.push({ ...job, previous: JSON.parse(JSON.stringify(previous)) });
      const unrelated = job.node.annotations.filter(note => !note.label?.startsWith(job.prefix));
      job.node.annotations = [...unrelated, job.annotation];
      const retained = job.node.annotations;
      const retainedOwned = retained.filter(note => note.label?.startsWith(job.prefix));
      const retainedUnrelated = retained.filter(note => !note.label?.startsWith(job.prefix));
      // Figma may add derived labelMarkdown, empty properties and a default categoryId.
      if (!sameNotes(retainedOwned, [job.annotation]) || !sameNotes(retainedUnrelated, unrelated)) fail(`native note not retained on ${job.key}: ${JSON.stringify({ expected: job.annotation, actual: retainedOwned }).slice(0, 1800)}`);
    }
    return { changed: undo.length, annotations: jobs.map(job => ({ key: job.key, nodeId: job.node.id, ...job.annotation })), rollback };
  } catch (error) {
    try { await rollback(); } catch (rollbackError) { throw new Error(`${error.message}; ${rollbackError.message}`); }
    throw error;
  }
}
function connectedSpecificationMarkdown(specification, {fileKey,textNodeId,locale}) {
  const labels = FLOW_SPEC_LABELS;
  if (!labels[locale] || typeof fileKey !== "string" || !fileKey || typeof textNodeId !== "string" || !textNodeId || typeof specification?.annotation_text !== "string" || !specification.annotation_text.trim()) throw new Error("Connected specification annotation requires locale, target and source-grounded summary");
  const url = `https://www.figma.com/design/${encodeURIComponent(fileKey)}?node-id=${encodeURIComponent(textNodeId.replace(/:/g,"-"))}`;
  return {markdown:`${specification.title}\n${specification.annotation_text.trim()}\n\n[${labels[locale]}](${url})`,url};
}
function nativeAnnotationMatches(actual, markdown) { return actual?.labelMarkdown === markdown; }
function connectedSpecificationAnnotations(before, legacySlots, priorHuman, replacementRaw) {
  const removed = new Set([...(legacySlots||[]).map(slot=>slot.index),...(priorHuman?[priorHuman.index]:[])]);
  const result = before.filter((_,index)=>!removed.has(index));
  const index = priorHuman?.index ?? legacySlots?.[0]?.index ?? result.length;
  result.splice(Math.min(index,result.length),0,replacementRaw);
  return result;
}
if (typeof module !== "undefined") module.exports = { ensureNativeAnnotations, connectedSpecificationMarkdown, nativeAnnotationMatches, connectedSpecificationAnnotations };

async function ensureReadableNativeSpecifications(figma, page, contract) {
  const fail = message => { throw new Error(`Native specifications: ${message}`); };
  const copy = value => JSON.parse(JSON.stringify(value));
  const ordered = (_, value) => value && typeof value === "object" && !Array.isArray(value) ? Object.fromEntries(Object.keys(value).sort().map(key => [key,value[key]])) : value;
  const equal = (a, b) => JSON.stringify(a,ordered) === JSON.stringify(b,ordered);
  const bytes = value => unescape(encodeURIComponent(value)).length;
  const field = "figmaFlowSpecification";
  if (!page?.id || typeof contract.sourceHash !== "string" || !contract.sourceHash || !Array.isArray(contract.annotations || contract.notes)) fail("page, sourceHash and annotations required");
  if (contract.preflight !== undefined && typeof contract.preflight !== "function") fail("preflight must be a trusted function");
  await page.loadAsync();
  if (contract.preflight) await contract.preflight();
  const nodes = [page, ...page.findAll(() => true)], seen = new Set();
  const byKey = indexAnnotationNodes(nodes), byId = new Map(nodes.map(node => [node.id,node])), boardChildren = new Map();
  const indexChildren = board => {
    const indexed = new Map();
    for (const child of board.children || []) {
      const id = child.id;
      if (indexed.has(id)) fail("ambiguous readable board child");
      indexed.set(id,child);
    }
    return indexed;
  };
  const owner = JSON.stringify({pageId:page.id,sourceHash:contract.sourceHash});
  const jobs = (contract.annotations || contract.notes).map(note => {
    if (!note?.key || seen.has(note.key)) fail("unique semantic keys required");
    seen.add(note.key);
    const matches = byKey.get(note.key) || [];
    if (matches.length !== 1) fail(`missing or ambiguous semanticKey ${note.key}`);
    const node = matches[0], spec = note.specification;
    if (!spec || spec.schema !== FLOW_SPEC.schemas.readable || !["id","kind","screen_id","target_id","title","meaning_sha256","source_graph_sha256","source_graph_encoding","display_text"].every(key => typeof spec[key] === "string" && spec[key].trim()) || !spec.title.trim() || !spec.display_text.trim() || !spec.meaning || !spec.trace) fail(`invalid compiled specification ${note.key}`);
    const rich = spec.presentation === "connected-spec-v2";
    if (rich && (!Object.keys(FLOW_SPEC_LABELS).includes(spec.locale) || !Array.isArray(spec.sections) || !spec.sections.some(section => section && typeof section.key === 'string' && typeof section.title === 'string' && typeof section.body === 'string') || typeof spec.annotation_text !== 'string' || !spec.annotation_text.trim())) fail(`invalid connected specification ${note.key}`);
    const board = byId.get(note.board?.boardId);
    if (board && !boardChildren.has(board)) boardChildren.set(board,indexChildren(board));
    const text = boardChildren.get(board)?.get(note.board?.textNodeId);
    if (!board || board.parent !== page || board.getPluginData("designNoteBoard") !== owner || typeof note.board?.key !== "string" || !note.board.key || board.visible === false || text?.getPluginData("semanticKey") !== board.getPluginData("semanticKey") + ":" + note.board.key || text?.type !== "TEXT" || text.parent !== board || text.visible === false || text.characters !== `${spec.title}\n${spec.display_text}` || text.fontSize < 14) fail(`owned readable board required for ${note.key}`);
    const link = text.getRangeHyperlink?.(0, text.characters.length);
    if (link?.type !== "NODE" || link.value !== node.id) fail(`same-file target hyperlink required for ${note.key}`);
    const previous = node.getPluginData(field);
    let prior = null;
    if (previous) {
      try { prior = JSON.parse(previous); } catch (_) { fail(`invalid existing metadata ${note.key}`); }
      if (bytes(previous) >= 90000 || prior.schema !== FLOW_SPEC.schemas.native || prior.semantic_key !== note.key || prior.target_id !== node.id || prior.source_owner_hash !== contract.sourceHash || prior.state !== "applied" || !Array.isArray(prior.legacy_annotations) || prior.specification?.schema !== FLOW_SPEC.schemas.readable || !["id","kind","screen_id","target_id","title","meaning_sha256","source_graph_sha256","source_graph_encoding","display_text"].every(key => typeof prior.specification[key] === "string" && prior.specification[key].trim()) || !prior.specification.meaning || !prior.specification.trace || prior.legacy_annotations.some(slot => !Number.isInteger(slot?.index) || slot.index < 0 || typeof slot.annotation?.label !== "string")) fail(`invalid existing metadata ${note.key}`);
    }
    if (!Array.isArray(node.annotations)) fail(`unsupported annotations ${note.key}`);
    const before = copy(node.annotations), prefix = `[figma-flow:${note.key}] `;
    const markdown = rich ? connectedSpecificationMarkdown(spec, {fileKey:contract.fileKey || figma.fileKey,textNodeId:note.board.textNodeId,locale:spec.locale}) : null;
    if (note.expected_before !== undefined) {
      const expected = note.expected_before;
      if (!expected || typeof expected !== "object" || Array.isArray(expected) || !equal(Object.keys(expected).sort(),["annotations","specification"]) || !Array.isArray(expected.annotations) || (expected.specification !== null && (typeof expected.specification !== "object" || Array.isArray(expected.specification))) || !equal(expected.specification,prior) || !equal(expected.annotations,before)) fail(`expected before-state conflict ${note.key}`);
    }
    if (prior?.human_annotation) {
      const owned = prior.human_annotation, actual = before[owned.index];
      if (owned.schema !== FLOW_SPEC.schemas.human || !Number.isInteger(owned.index) || owned.index < 0 || !owned.board || !equal(actual,owned.annotation) || !nativeAnnotationMatches(actual, connectedSpecificationMarkdown(prior.specification,{fileKey:contract.fileKey || figma.fileKey,textNodeId:owned.board.textNodeId,locale:prior.specification.locale}).markdown)) fail(`edited or missing owned human annotation ${note.key}`);
      if (before.filter(annotation => nativeAnnotationMatches(annotation, connectedSpecificationMarkdown(prior.specification,{fileKey:contract.fileKey || figma.fileKey,textNodeId:owned.board.textNodeId,locale:prior.specification.locale}).markdown)).length !== 1) fail(`duplicate owned human annotation ${note.key}`);
    }
    let slots = before.flatMap((annotation,index) => annotation.label?.startsWith(prefix) ? [{index,annotation}] : []);
    if (prior && (slots.length || before.some(annotation => prior.legacy_annotations.some(slot => equal(annotation,slot.annotation))))) fail(`partial or conflicting legacy annotations with existing metadata ${note.key}`);
    const expected = note.expected_legacy === undefined ? [] : (Array.isArray(note.expected_legacy) ? note.expected_legacy : [note.expected_legacy]);
    if (expected.length > 1 || expected.some(slot => !Number.isInteger(slot?.index) || slot.index < 0 || typeof slot.annotation?.label !== "string")) fail(`explicit exact legacy snapshot required for ${note.key}`);
    if (!prior && !slots.length && expected.length && !expected[0].annotation.label.startsWith("[figma-flow:")) {
      const slot = expected[0];
      if (!equal(before[slot.index],slot.annotation) || before.filter(annotation => equal(annotation,slot.annotation)).length !== 1) fail(`ambiguous or edited unprefixed legacy annotation ${note.key}`);
      let nodeInfo, pageInfo;
      try { nodeInfo = JSON.parse(node.getPluginData("figmaFlow")); pageInfo = JSON.parse(page.getPluginData("figmaFlow")); }
      catch (_) { fail(`private import ownership required for ${note.key}`); }
      if (nodeInfo?.annotation_mode !== "native" || nodeInfo.semantic_id !== note.key || pageInfo?.source_sha256 !== contract.sourceHash) fail(`private import ownership required for ${note.key}`);
      if (contract.strictLegacyDisplay) {
        const exactLegacyBody = `${node.name} · ${note.board.key}\n${slot.annotation.label}\n화면·조작으로 이동`;
        if (!node.name || note.expected_legacy_display !== exactLegacyBody) fail(`exact original legacy display required for ${note.key}`);
      }
      slots = [{index:slot.index,annotation:before[slot.index]}];
    }
    if (slots.length > 1 || (slots.length && !equal(slots, expected)) || (!slots.length && expected.length && !equal(prior?.legacy_annotations,expected))) fail(`explicit exact legacy snapshot required for ${note.key}`);
    for (const slot of slots) {
      if (Object.keys(slot.annotation).some(key => !["label","labelMarkdown","properties","categoryId"].includes(key)) || (slot.annotation.properties !== undefined && (!Array.isArray(slot.annotation.properties) || slot.annotation.properties.some(property => Object.keys(property).some(key => key !== "type") || typeof property.type !== "string")))) fail(`unsupported legacy annotation fields ${note.key}`);
    }
    const human = rich ? (prior?.human_annotation || {schema:FLOW_SPEC.schemas.human,index:slots[0]?.index ?? before.length,annotation:null,board:copy(note.board),url:markdown.url}) : null;
    const ownedHuman = prior?.human_annotation ? [prior.human_annotation.index] : [];
    const removedIndices = new Set([...slots.map(slot=>slot.index),...ownedHuman]);
    const wrapper = {schema:FLOW_SPEC.schemas.native,semantic_key:note.key,target_id:node.id,source_owner_hash:contract.sourceHash,specification:copy(spec),legacy_annotations:prior ? prior.legacy_annotations : slots,...(rich?{human_annotation:human}:{}),state:"applied"};
    const written = JSON.stringify(wrapper);
    const pendingWrapper = {...wrapper,state:"pending"};
    if (rich) delete pendingWrapper.human_annotation;
    const pending = slots.length || rich ? JSON.stringify(pendingWrapper) : written;
    if (bytes(pending) >= 90000 || bytes(written) >= 90000) fail(`metadata exceeds safe UTF-8 limit ${note.key}`);
    return {key:note.key,node,previous,written,pending,before,slots,after:before.filter((_,index) => !removedIndices.has(index)),human,oldHuman:prior?.human_annotation||null,markdown,rich,wrapper};
  });
  for (const [board, indexed] of boardChildren) {
    const actual = indexChildren(board);
    if (board.parent !== page || board.visible === false || board.getPluginData("designNoteBoard") !== owner ||
        actual.size !== indexed.size || [...actual].some(([id,node]) => indexed.get(id) !== node || node.parent !== board)) fail("concurrent readable board children or ownership conflict");
  }
  const undo = [];
  let rolledBack = false;
  const rollback = async () => {
    if (rolledBack) return;
    const errors = [];
    for (const job of undo.slice().reverse()) {
      try {
        if (![job.written,job.pending,job.previous].includes(job.node.getPluginData(field))) fail(`concurrent metadata conflict ${job.key}`);
        if (job.removed && !equal(job.node.annotations,job.before)) {
          const current = copy(job.node.annotations);
          if (job.rich) {
            const owned = current.flatMap((value,index)=>nativeAnnotationMatches(value,job.markdown.markdown)?[index]:[]);
            if (owned.length !== 1) fail(`owned annotation rollback conflict ${job.key}`);
            current.splice(owned[0],1);
          }
          let cursor = 0;
          for (const old of job.after) { const found = current.findIndex((value,index) => index >= cursor && equal(value,old)); if (found < 0) fail(`concurrent annotation conflict ${job.key}`); cursor = found + 1; }
          const restore = [...job.slots,...(job.oldHuman?[{index:job.oldHuman.index,annotation:job.oldHuman.annotation}]:[])].sort((a,b)=>a.index-b.index);
          for (const slot of restore) {
            if (current.some(value => equal(value,slot.annotation) || value.label?.startsWith(`[figma-flow:${job.key}] `))) fail(`ambiguous restoration ${job.key}`);
            const next = job.before[slot.index + 1];
            const index = next ? current.findIndex(value => equal(value,next)) : current.length;
            if (index < 0 || (next && current.filter(value => equal(value,next)).length !== 1)) fail(`ambiguous restoration ${job.key}`);
            current.splice(index,0,slot.annotation);
          }
          job.node.annotations = current;
          if (!equal(job.node.annotations,current)) fail(`annotation restoration not retained ${job.key}`);
        }
        job.node.setPluginData(field,job.previous);
        if (job.node.getPluginData(field) !== job.previous) fail(`metadata restoration not retained ${job.key}`);
      } catch (error) {
        errors.push(error.message || String(error));
        if ([job.written,job.pending].includes(job.node.getPluginData(field))) {
          try { job.node.setPluginData(field,JSON.stringify({...job.wrapper,state:"conflict"})); } catch (_) {}
        }
      }
    }
    if (errors.length) fail(`rollback incomplete: ${errors.join("; ")}`);
    rolledBack = true;
  };
  try {
    for (const job of jobs) {
      if (job.previous === job.written && !job.slots.length) continue;
      if (job.node.getPluginData(field) !== job.previous || !equal(job.node.annotations,job.before)) fail(`concurrent preflight conflict ${job.key}`);
      undo.push(job);
      job.node.setPluginData(field,job.pending);
      if (job.node.getPluginData(field) !== job.pending) fail(`metadata not retained ${job.key}`);
    }
    for (const job of undo) {
      if (job.node.getPluginData(field) !== job.pending || !equal(job.node.annotations,job.before)) fail(`concurrent annotation conflict ${job.key}`);
    }
    for (const job of undo) {
      if (!job.rich) continue;
      if (job.node.getPluginData(field) !== job.pending || !equal(job.node.annotations,job.before)) fail(`concurrent annotation conflict ${job.key}`);
      const annotations = copy(job.after), index = Math.min(job.human.index,annotations.length);
      annotations.splice(index,0,{labelMarkdown:job.markdown.markdown});
      job.removed = true;
      job.node.annotations = annotations;
      const actual = job.node.annotations[index];
      if (!nativeAnnotationMatches(actual,job.markdown.markdown) || job.node.annotations.filter(annotation=>nativeAnnotationMatches(annotation,job.markdown.markdown)).length !== 1 || !equal(job.node.annotations.filter((_,i)=>i!==index),job.after)) fail(`connected human annotation not retained ${job.key}`);
      job.human = {...job.human,index,annotation:copy(actual),board:copy(job.human.board),url:job.markdown.url};
      job.wrapper.human_annotation = job.human;
      job.written = JSON.stringify(job.wrapper);
      job.pending = JSON.stringify({...job.wrapper,state:"pending"});
      if (bytes(job.pending) >= 90000 || bytes(job.written) >= 90000) fail(`metadata exceeds safe UTF-8 limit ${job.key}`);
      job.node.setPluginData(field,job.pending);
      if (job.node.getPluginData(field) !== job.pending) fail(`connected annotation metadata not retained ${job.key}`);
    }
    for (const job of undo) {
      if (!job.slots.length || job.rich) continue;
      if (job.node.getPluginData(field) !== job.pending || !equal(job.node.annotations,job.before)) fail(`concurrent annotation conflict ${job.key}`);
      job.removed = true;
      job.node.annotations = job.after;
      if (!equal(job.node.annotations,job.after)) fail(`legacy removal not retained ${job.key}`);
    }
    for (const job of undo) {
      const expectedAnnotations = job.rich ? [...job.after.slice(0,job.human.index),job.human.annotation,...job.after.slice(job.human.index)] : job.after;
      if (job.node.getPluginData(field) !== job.pending || !equal(job.node.annotations,expectedAnnotations)) fail(`concurrent finalization conflict ${job.key}`);
      if (job.pending !== job.written) job.node.setPluginData(field,job.written);
      if (job.node.getPluginData(field) !== job.written) fail(`applied metadata not retained ${job.key}`);
    }
    return {changed:undo.length,annotations:jobs.map(job => ({key:job.key,nodeId:job.node.id,specification:job.wrapper.specification})),rollback};
  } catch (error) {
    try { await rollback(); } catch (rollbackError) { throw new Error(`${error.message}; ${rollbackError.message}`); }
    throw error;
  }
}
