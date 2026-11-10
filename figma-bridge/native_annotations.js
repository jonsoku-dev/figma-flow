/* Project-owned native notes; labels remain readable in Figma's annotation panel. */
async function ensureNativeAnnotations(figma, page, contract) {
  const fail = message => { throw new Error(`Native annotations: ${message}`); };
  if (!page || !Array.isArray(contract?.annotations)) fail("page and annotations are required");
  await page.loadAsync();
  const nodes = [page, ...page.findAll(() => true)];
  const seen = new Set();
  const jobs = contract.annotations.map(note => {
    if (!note || typeof note.key !== "string" || !note.key || seen.has(note.key) || typeof note.label !== "string" || !note.label.trim()) fail("unique keys and nonempty readable labels are required");
    seen.add(note.key);
    if (note.properties !== undefined && (!Array.isArray(note.properties) || note.properties.some(value => typeof value !== "string" || !value))) fail(`invalid properties for ${note.key}`);
    const matches = nodes.filter(node => node.getPluginData("semanticKey") === note.key);
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
if (typeof module !== "undefined") module.exports = { ensureNativeAnnotations };
