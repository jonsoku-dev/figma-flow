/* A running home panel can execute only the signed, prepared tasks it loaded. */
let controlPolling = false;
let controlRetryAt = 0;
const controlRunSession = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
const controlAllowed = {review: ['create'], import: ['read', 'import', 'sync'], discover: ['read'], sync: ['read', 'apply'], 'native-edit': ['read', 'apply']};

function controlState(outcome, busy) {
  figma.ui.postMessage({type:'workspace-control-state', workspaceSession:workspaceHomeSession, history:workspaceState.history, outcome, busy});
}

async function controlRequest(route, body) {
  const config = WORKSPACE_CONTROL_CONFIG;
  const response = await fetch(config.url + '/control/' + route, {
    method: 'POST', headers: {'Authorization': 'Bearer ' + config.token, 'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if (!response.ok) throw Error('Local command receipt rejected (' + response.status + ')');
  return response.json();
}

async function controlExecute(task, cmd) {
  if (!task || task.revision !== cmd.revision || !controlAllowed[task.kind]?.includes(cmd.operation))
    throw Error('Prepared task changed. Reopen Figma Flow and issue a new command.');
  const checkCommand = () => {
    if (Date.now() >= cmd.deadline * 1000 || workspaceActive) throw Error('Command is expired or the panel is busy.');
    if (figma.fileKey !== cmd.file_key || (task.fileKey && task.fileKey !== cmd.file_key) ||
        (task.pageId && task.pageId !== cmd.page_id)) throw Error('Command differs from the prepared file or page.');
  };
  checkCommand();
  if (figma.currentPage.id !== cmd.page_id) {
    if (!cmd.focus_page || task.fileKey !== cmd.file_key || task.pageId !== cmd.page_id)
      throw Error('Command differs from the active page.');
    const initialPage = figma.currentPage.id;
    const page = await figma.getNodeByIdAsync(cmd.page_id);
    if (page?.type !== 'PAGE' || page.id !== task.pageId) throw Error('The pinned page is unavailable.');
    await page.loadAsync();
    checkCommand();
    if (initialPage !== figma.currentPage.id) throw Error('The active page changed while preparing the command.');
    await figma.setCurrentPageAsync(page);
    checkCommand();
    if (figma.currentPage.id !== cmd.page_id) throw Error('Failed to activate the pinned page.');
  }
  const active = await workspaceOpen(task, 'remote');
  if (!active?.handler) throw Error('The prepared native handler is unavailable.');
  active.inFlight++;
  let output = [];
  let outputPage = cmd.page_id;
  active.executionId = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
  active.onOutput = msg => output.push(msg);
  async function invoke(message) {
    if (Date.now() >= cmd.deadline * 1000 || figma.fileKey !== cmd.file_key || figma.currentPage.id !== outputPage)
      throw Error('Scope or deadline changed before native dispatch.');
    output = [];
    active.operation = message.type;
    active.outcome = null;
    active.started = false;
    workspaceRecord(active, message.type, 'requested');
    await active.handler(message);
    const fail = output.find(m => m.error || m.type === 'geometry-failure' ||
      (m.type === 'status' && (m.state === 'error' || String(m.message).startsWith('Error:'))));
    if (fail) throw Object.assign(Error(fail.error || fail.message || 'Native geometry validation failed.'),
      {nativeReadback:fail.readback || fail.data});
    return output;
  }
  try {
    const operation = cmd.operation;
    const appData = active.html?.match(/<script type="application\/json" id="flow-model">([\s\S]*?)<\/script>/);
    const model = appData ? JSON.parse(appData[1]) : null;
    if (task.kind === 'import') {
      const envelope = {session_nonce:cmd.claim_id};
      const ready = (await invoke({...envelope,type:'ready'})).find(m => m.ready && m.session_nonce === cmd.claim_id);
      if (!ready || (ready.existing_only && operation === 'import') || (!ready.paired && operation === 'sync'))
        throw Error('The current import package does not admit this operation.');
      if (operation === 'import') {
        const messages = await invoke({...envelope,type:'import',fresh:false});
        if (!messages.some(m=>m.type==='busy' && m.value && m.operation==='import') ||
            !messages.some(m=>m.type==='status' && !m.ready) || !messages.some(m=>m.type==='busy' && m.value===false))
          throw Error('No native import completion was observed.');
        const completed = messages.find(m => ['imported','reused'].includes(m.event));
        if (!completed?.page_id || !task.sourceSha256 || completed.source_sha256 !== task.sourceSha256)
          throw Error('No matching native import page receipt. Refresh the prepared import task.');
        outputPage = completed.page_id;
        workspaceRecord(active,'import','finished');
      }
      if (operation === 'sync') {
        const result = (await invoke({...envelope,type:'sync'})).find(m=>m.type==='sync-result')?.result;
        if (!result || !['baseline','applied','unchanged'].includes(result.status)) throw Error('The local app did not confirm synchronization.');
        return result;
      }
      const data = (await invoke({...envelope,type:'export'})).find(m=>m.type==='readback')?.data;
      if (data?.format !== 'figma-flow-readback-v1' || data.pages?.length !== 1 || data.pages[0].id !== outputPage || figma.fileKey !== cmd.file_key ||
          (operation==='import' && (!data.pages[0].declared_metadata?.complete || data.pages[0].source_sha256 !== task.sourceSha256)))
        throw Error('Import did not provide a readback for the current page.');
      return data;
    }
    if (task.kind === 'review') {
      const data = (await invoke({type:'draft-review'})).find(m=>m.type==='readback')?.data;
      if (!data?.packet_sha256 || data.fileKey !== cmd.file_key || !Array.isArray(data.nodes) || !data.nodes.length)
        throw Error('No native review readback for this file.');
      const pairLine = active.html.match(/^const PAIR = (.*);$/m);
      if (!model && !pairLine) throw Object.assign(Error('Unknown review receiver contract.'), {nativeReadback:data});
      const pair = model ? model.pair : JSON.parse(pairLine[1]);
      if (pair) {
        if (!/^http:\/\/localhost:\d+\/draft-readback$/.test(pair.url) || !/^[a-f0-9]{64}$/.test(pair.capability))
          throw Object.assign(Error('Invalid private review endpoint.'), {nativeReadback:data});
        try {
          const reply = await fetch(pair.url, {method:'POST', headers:{Authorization:'Bearer '+pair.capability,'Content-Type':'application/json'},body:JSON.stringify(data)});
          const receipt = await reply.json();
          if (!reply.ok || receipt.passed !== true) throw Error('The review receiver rejected the native result.');
          workspaceRecord(active,'verification','verified');
        } catch (error) {workspaceRecord(active,'verification','failed'); active.outcome = 'failed'; error.nativeReadback = data; throw error;}
      }
      return data;
    }
    if (task.kind === 'native-edit') {
      const session = model?.session;
      if (!session) throw Error('Missing prepared native edit session.');
      const messages = await invoke({type:operation,session});
      const data = messages.find(m => m.session === session && m.operation === operation && m.readback)?.readback;
      if (!data || data.schema !== 'figma-flow-graph-native-discovery-v1' ||
          data.fileKey !== cmd.file_key || data.pageId !== cmd.page_id || data.native_edit?.operation !== operation ||
          data.native_edit?.applied !== (operation === 'apply'))
        throw Object.assign(Error('Native edit did not return the expected actual getter.'), {nativeReadback:data});
      return data;
    }
    const match = active.html.match(/<script id="graph-panel-config" type="application\/json">([\s\S]*?)<\/script>/);
    if (!model && !match) throw Error('Missing prepared graph panel configuration.');
    const session = (model || JSON.parse(match[1])).session;
    const messages = await invoke({type:operation,session});
    const reply = messages.find(m => m.session === session && m.operation === operation && m.readback);
    const data = reply?.readback;
    const discovery = task.kind === 'discover';
    if (!data || data.schema !== (discovery?'figma-flow-graph-native-discovery-v1':'figma-flow-graph-token-readback-v1') ||
        data.error || (data.status && data.status !== 'success') ||
        (data.file_key || data.fileKey) !== cmd.file_key || (data.page_id || data.pageId) !== cmd.page_id)
      throw Object.assign(Error('Graph operation did not return the expected native evidence.'), {nativeReadback:data});
    return data;
  } catch (error) {
    if (active.outcome !== 'failed') workspaceRecord(active, active.operation === 'ready' ? cmd.operation : active.operation || cmd.operation, 'failed');
    active.outcome = 'failed';
    throw error;
  } finally {
    active.onOutput = null;
    active.executionId = null;
    active.inFlight--;
    if (workspaceActive === active) workspaceActive = null;
  }
}

async function workspaceControlTick() {
  if (typeof WORKSPACE_CONTROL_CONFIG === 'undefined' || !WORKSPACE_CONTROL_CONFIG || controlPolling || workspaceActive || Date.now() < controlRetryAt) return;
  const home = workspaceHomeSession;
  controlPolling = true;
  let cmd = null;
  try {
    const reply = await controlRequest('poll', {session_id:controlRunSession,file_key:figma.fileKey,page_id:figma.currentPage.id,
      ...(typeof WORKSPACE_RUNTIME === 'undefined' ? {} : {runtime:WORKSPACE_RUNTIME})});
    cmd = reply.operation;
    if (!cmd) return;
    const receipt = Object.fromEntries(['id','claim_id','session_id','revision','file_key','page_id'].map(k=>[k,cmd[k]]));
    controlState('running', true);
    try {
      if (workspaceActive || home !== workspaceHomeSession || cmd.session_id !== controlRunSession) throw Error('The open workspace session changed.');
      const data = await controlExecute(workspaceTasks.get(cmd.key), cmd);
      receipt.status = 'ok';
      receipt.readback_json = JSON.stringify(data);
    } catch (error) {
      receipt.status = 'error';
      receipt.error = String(error.message || error).slice(0,1900);
      if (error.nativeReadback) receipt.readback_json = JSON.stringify(error.nativeReadback);
    }
    await controlRequest('result', receipt);
    controlState(receipt.status === 'ok' ? 'finished' : 'failed', false);
  } catch (_error) {
    controlRetryAt = Date.now() + 8000;
    if (cmd) controlState('uncertain', false);
  } finally {controlPolling = false;}
}
