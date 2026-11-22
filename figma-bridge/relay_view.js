// Viewer commands inspect or navigate the active file without editing design nodes.
function workspaceReadNodeField(node, field, textBudget) {
  try {
    const value = node[field];
    switch (WORKSPACE_PROFILE_POLICY.inspectFields[field]) {
      case 'string':
      case 'text': {
        if (typeof value !== 'string') break;
        const limit = field === 'characters' ? Math.min(200, textBudget.remaining) : 160;
        const excerpt = value.slice(0, limit);
        if (field === 'characters') textBudget.remaining -= excerpt.length;
        return {value:excerpt, truncated:excerpt.length !== value.length};
      }
      case 'number': if (Number.isFinite(value)) return {value}; break;
      case 'boolean': if (typeof value === 'boolean') return {value}; break;
      case 'font':
        if (typeof value?.family === 'string' && typeof value?.style === 'string')
          return {value:{family:value.family.slice(0,120),style:value.style.slice(0,120)}};
        break;
      case 'paints':
        if (Array.isArray(value) && value.length <= 8 && value.every(p => p.type === 'SOLID')) {
          return {value:value.map(p => ({type:'SOLID', color:{r:p.color.r,g:p.color.g,b:p.color.b},
            opacity:p.opacity ?? 1, visible:p.visible !== false}))};
        }
    }
    return {unavailable:true};
  } catch (_) {
    return {unavailable:true};
  }
}

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
    if (Object.keys(options).some(key => !['include_text', 'geometry_node_ids', 'inspect_node_ids', 'fields'].includes(key)) ||
        (options.include_text !== undefined && typeof options.include_text !== 'boolean') ||
        (options.geometry_node_ids !== undefined && options.include_text === true)) throw Error('Invalid selection options.');
    const inspecting = options.inspect_node_ids !== undefined;
    const fields = options.fields;
    if (inspecting && (options.geometry_node_ids !== undefined || !Array.isArray(fields) || !fields.length ||
        fields.length > Object.keys(WORKSPACE_PROFILE_POLICY.inspectFields).length ||
        new Set(fields).size !== fields.length || fields.some(f => typeof f !== 'string' ||
        !Object.prototype.hasOwnProperty.call(WORKSPACE_PROFILE_POLICY.inspectFields, f)) ||
        fields.includes('characters') !== (options.include_text === true))) throw Error('Invalid detail fields.');
    if (!inspecting && fields !== undefined) throw Error('Field inspection requires exact node IDs.');
    const ids = inspecting ? options.inspect_node_ids : options.geometry_node_ids;
    const result = ids === undefined ? {...receipt, selection:WorkspaceChat.collect(figma, task, options.include_text === true)} :
      {...receipt, selection_included:false};
    if (ids !== undefined) {
      if (!Array.isArray(ids) || ids.length < 1 || ids.length > WORKSPACE_READ_LIMITS.maxNodes ||
          ids.some(id => typeof id !== 'string' || id.length > 120 || !/^(?:I?[0-9]+:[0-9]+)(?:;[0-9]+:[0-9]+)*$/.test(id)) ||
          new Set(ids).size !== ids.length) throw Error(`Read 1 to ${WORKSPACE_READ_LIMITS.maxNodes} unique exact Design scene node IDs.`);
      const nodes = [];
      const textBudget = {remaining:1000};
      for (const id of ids) {
        check();
        const node = await figma.getNodeByIdAsync(id);
        check();
        if (!node || node.removed || ['DOCUMENT', 'PAGE'].includes(node.type)) {
          nodes.push({id, status:'missing'});
          continue;
        }
        let owner = node.parent;
        while (owner && owner.type !== 'PAGE') owner = owner.parent;
        if (owner?.id !== page.id) {
          nodes.push({id, status:'missing'});
          continue;
        }
        if (inspecting) {
          const values = {};
          for (const field of fields) values[field] = workspaceReadNodeField(node, field, textBudget);
          nodes.push({id:node.id,type:node.type,status:'observed',fields:values});
          continue;
        }
        const box = node.absoluteBoundingBox;
        const validBox = box && ['x', 'y', 'width', 'height'].every(key => Number.isFinite(box[key])) &&
          box.width >= 0 && box.height >= 0 && ['x', 'y', 'width', 'height'].every(key => Math.abs(box[key]) <= 10000000);
        const rotation = Number.isFinite(node.rotation) ? node.rotation : null;
        nodes.push({id:node.id, name:String(node.name || '').slice(0, 120), type:node.type,
          rotation, status:validBox ? 'observed' : 'unmeasurable',
          absoluteBoundingBox:validBox ? {x:box.x, y:box.y, width:box.width, height:box.height} : null});
      }
      check();
      if (inspecting) result.details = {fields,nodes};
      else result.geometry = {coordinate_space:'page-absolute-axis-aligned', nodes};
    }
    return result;
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
