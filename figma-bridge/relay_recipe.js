/* RECIPE_PLAN, runPinnedExample and the session are embedded at preparation. */
figma.showUI(__html__);
figma.ui.onmessage = async message => {
  const operation = message && message.type;
  if (message?.session !== RECIPE_SESSION || !['read', 'apply'].includes(operation)) return;
  const page = figma.currentPage;
  if (figma.editorType !== 'figma' || figma.mode !== 'default' ||
      page.id !== RECIPE_PLAN.page_id || figma.fileKey !== RECIPE_PLAN.file_key)
    throw Error('The example requires its prepared Design file and page.');

  const marker = 'flowRelayRecipe';
  const marked = page.findAllWithCriteria({types:['FRAME', 'SECTION'], pluginData:{keys:[marker]}});
  const matches = marked.filter(node => node.getPluginData(marker) === RECIPE_PLAN.pin);
  if (matches.length > 1) throw Error('Multiple matching example containers on the prepared page.');
  let root = matches[0];
  let created = false;
  if (!root && operation === 'apply') {
    const prior = new Set(page.children.map(node => node.id));
    await runPinnedExample(figma);
    root = page.selection[0];
    while (root && root.parent && root.parent.id !== page.id) root = root.parent;
    if (figma.currentPage.id !== page.id || !root || root.parent?.id !== page.id || prior.has(root.id) ||
        !['FRAME','SECTION'].includes(root.type)) throw Error('Cannot confirm the new example container.');
    root.setPluginData(marker, RECIPE_PLAN.pin);
    created = true;
  }
  figma.ui.postMessage({session:RECIPE_SESSION, operation, readback:{
    schema:'figma-flow-example-readback-v1', fileKey:figma.fileKey, pageId:page.id,
    recipe:RECIPE_PLAN.recipe, pin:RECIPE_PLAN.pin, created,
    container:root ? {id:root.id, name:root.name, type:root.type, childCount:root.children.length} : null,
    native_edit:{operation, applied:operation === 'apply'}
  }});
};
