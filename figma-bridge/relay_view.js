// Viewer commands inspect or navigate the active file without editing design nodes.
async function workspaceViewerExecute(task, cmd, checkCurrent) {
  const options = cmd.viewer_options || {};
  const page = figma.currentPage;
  const check = () => {
    checkCurrent();
    if (task.kind !== 'discover' || task.fileKey !== cmd.file_key || task.pageId !== cmd.page_id ||
        figma.fileKey !== cmd.file_key || figma.currentPage.id !== page.id || page.id !== cmd.page_id ||
        task.revision !== cmd.revision || cmd.session_id !== controlRunSession)
      throw Error('Viewer command requires its prepared Design file, page and session.');
  };
  check();
  const receipt = {schema:'figma-flow-viewer-result-v1', operation:cmd.operation, fileKey:cmd.file_key, pageId:page.id};
  if (cmd.operation === 'viewer-history') {
    if (Object.keys(options).length) throw Error('Unexpected history options.');
    return {...receipt, scope:'file', source:'figma-clientStorage', available:!!workspaceStorageKey && !workspaceStorageError,
      locale:workspaceState.locale, history:workspaceState.history.slice(-80)};
  }
  if (cmd.operation === 'viewer-language') {
    if (Object.keys(options).length !== 1 || (options.language !== 'auto' && !workspaceLocales.has(options.language))) throw Error('Unknown viewer language.');
    workspaceState.locale = options.language === 'auto' ? null : options.language;
    const persisted = await workspacePersist();
    check();
    workspaceRelayViewerState();
    return {...receipt, language:workspaceState.locale, storage:persisted ? 'local' : 'session'};
  }
  if (cmd.operation === 'selection-info') {
    if (Object.keys(options).some(key => key !== 'include_text') ||
        (options.include_text !== undefined && typeof options.include_text !== 'boolean')) throw Error('Invalid selection options.');
    return {...receipt, selection:WorkspaceChat.collect(figma, task, options.include_text === true)};
  }
  if (cmd.operation !== 'select-node' || Object.keys(options).length !== 1 ||
      typeof options.node_id !== 'string' || options.node_id.length > 120 ||
      !/^(?:I?[0-9]+:[0-9]+)(?:;[0-9]+:[0-9]+)*$/.test(options.node_id)) throw Error('Invalid viewer navigation target.');
  const node = await figma.getNodeByIdAsync(options.node_id);
  check();
  if (!node || node.removed || ['DOCUMENT','PAGE'].includes(node.type)) throw Error('Scene node is unavailable.');
  let owner = node.parent;
  while (owner && owner.type !== 'PAGE') owner = owner.parent;
  if (owner?.id !== page.id) throw Error('Node belongs to another page.');
  page.selection = [node];
  figma.viewport.scrollAndZoomIntoView([node]);
  if (page.selection.length !== 1 || page.selection[0].id !== node.id) throw Error('Figma selection was not confirmed.');
  return {...receipt, selected:{id:node.id, name:node.name, type:node.type}};
}
