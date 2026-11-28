/* A running home panel can execute only the signed, prepared tasks it loaded. */
let controlPolling = false;
let controlRetryAt = 0;
let controlRelayProfileResult = null;
let controlRelayProfileBinding = null;
let controlRelayIdentity;
const controlRunSession = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
// Registered workspaces load their task vocabulary from the same policy as Codex.
const controlAllowed = typeof WORKSPACE_PROFILE_POLICY !== 'undefined' && WORKSPACE_PROFILE_POLICY?.taskOperations
  ? WORKSPACE_PROFILE_POLICY.taskOperations : Object.freeze({});

function controlState(outcome, busy) {
  if (typeof workspaceRelayViewer !== 'undefined' && workspaceRelayViewer) {
    if (typeof workspaceRelayViewerState === 'function') workspaceRelayViewerState(busy ? 'busy' : undefined);
    return;
  }
  figma.ui.postMessage({type:'workspace-control-state', workspaceSession:workspaceHomeSession,
    fileKey:(typeof figma !== 'undefined' && figma.fileKey) || null,
    pageId:(typeof figma !== 'undefined' && figma.currentPage && figma.currentPage.id) || null,
    ...(typeof WORKSPACE_RUNTIME !== 'undefined' && WORKSPACE_RUNTIME && typeof WORKSPACE_RUNTIME.generation === 'string'
      ? {runtimeGeneration:WORKSPACE_RUNTIME.generation} : {}),
    history:workspaceState.history,
    journalHistory:workspaceServerHistory, journalUnavailable:workspaceJournalUnavailable, inputFreshness:workspaceInputFreshness, outcome, busy});
}

async function controlExecute(task, cmd, beforeDispatch) {
  const homeSession = workspaceHomeSession;
  if (typeof workspaceNeedsProfileAdmission === 'function' && workspaceNeedsProfileAdmission(cmd.operation)) {
    const file = figma.fileKey, page = figma.currentPage.id;
    if (!await workspaceProfileAdmit(cmd.operation))
      throw Error('The local profile or current Figma context does not allow this operation.');
    if (figma.fileKey !== file || figma.currentPage.id !== page || Date.now() >= cmd.deadline * 1000)
      throw Error('Scope or deadline changed while admitting native dispatch.');
  } else if (typeof workspaceProfileAllows === 'function' && !workspaceProfileAllows(cmd.operation)) {
    throw Error('The local profile or current Figma context does not allow this operation.');
  }
  if (!task || task.revision !== cmd.revision || !controlAllowed[task.kind]?.includes(cmd.operation))
    throw Error('Prepared task changed. Reopen Figma Flow and issue a new command.');
  const checkCommand = () => {
    if (Date.now() >= cmd.deadline * 1000 || workspaceActive) throw Error('Command is expired or the panel is busy.');
    if (figma.fileKey !== cmd.file_key || (task.fileKey && task.fileKey !== cmd.file_key) ||
        (task.pageId && task.pageId !== cmd.page_id)) throw Error('Command differs from the prepared file or page.');
  };
  checkCommand();
  if (['select-node', 'selection-info', 'viewer-history', 'viewer-language'].includes(cmd.operation)) {
    if (figma.currentPage.id !== cmd.page_id) throw Error('Viewer command requires the prepared active page.');
    if (beforeDispatch) await beforeDispatch();
    checkCommand();
    if (workspaceActive || workspaceHomeSession !== homeSession) throw Error('The viewer session changed before native navigation.');
    return workspaceViewerExecute(task, cmd, checkCommand);
  }
  if (['carousel-select', 'carousel-present'].includes(cmd.operation)) {
    if (task.kind !== 'native-edit' || figma.currentPage.id !== cmd.page_id)
      throw Error('Carousel action requires its prepared active Design task.');
    if (beforeDispatch) await beforeDispatch();
    checkCommand();
    if (workspaceActive || workspaceHomeSession !== homeSession) throw Error('The carousel session changed before native navigation.');
    const options = cmd.viewer_options || {};
    const event = [...workspaceState.history].reverse().find(row => row.taskKey === task.key &&
      row.revision === task.revision && row.executionId === options.execution_id);
    const summary = workspaceStoredCarousel(event?.carousel);
    const state = summary?.states.find(item => item.state_id === options.state_id);
    if (!summary || summary.status !== 'current' || !state || state.status !== 'current' ||
        state.state_id !== summary.initial_state || summary.file_key !== cmd.file_key || summary.page_id !== cmd.page_id)
      throw Error('Carousel readback is stale or outside this prepared task. Run native read again.');
    return workspaceSelectCarousel(null, {taskKey:task.key, revision:task.revision,
      executionId:options.execution_id, stateId:options.state_id, nodeId:summary.flow_start_node_id,
      action:cmd.operation === 'carousel-present' ? 'present' : 'select', workspaceSession:workspaceHomeSession,
      deadline:cmd.deadline}, true);
  }
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
  let dispatched = false;
  async function invoke(message) {
    if (Date.now() >= cmd.deadline * 1000 || figma.fileKey !== cmd.file_key || figma.currentPage.id !== outputPage || task.revision !== cmd.revision || active.busy)
      throw Error('Scope or deadline changed before native dispatch.');
    if (workspaceActive !== active) throw Error('Workspace task session expired before native dispatch.');
    const operation = message.type;
    if (typeof workspaceNeedsProfileAdmission === 'function' && workspaceNeedsProfileAdmission(operation)) {
      const file = figma.fileKey, page = figma.currentPage.id, session = active.session;
      if (!await workspaceProfileAdmit(operation))
        throw Error('The local profile or current Figma context does not allow this operation.');
      if (workspaceActive !== active || active.session !== session || figma.fileKey !== file ||
          figma.currentPage.id !== page || Date.now() >= cmd.deadline * 1000 || task.revision !== cmd.revision)
        throw Error('Scope or deadline changed while admitting native dispatch.');
    }
    if (!dispatched && beforeDispatch) {
      await beforeDispatch();
      if (workspaceActive !== active || Date.now() >= cmd.deadline * 1000 || figma.fileKey !== cmd.file_key || figma.currentPage.id !== outputPage)
        throw Error('Scope or deadline changed while admitting native dispatch.');
    }
    dispatched = true;
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
        const messages = await invoke({...envelope,type:'import',fresh:cmd.fresh === true});
        if (!messages.some(m=>m.type==='busy' && m.value && m.operation==='import') ||
            !messages.some(m=>m.type==='status' && !m.ready) || !messages.some(m=>m.type==='busy' && m.value===false))
          throw Error('No native import completion was observed.');
        const completed = messages.find(m => ['imported','reused'].includes(m.event));
        if (!completed?.page_id || !task.sourceSha256 || completed.source_sha256 !== task.sourceSha256)
          throw Error('No matching native import page receipt. Refresh the prepared import task.');
        if (cmd.fresh === true && completed.event !== 'imported') throw Error('Fresh import did not create a new page.');
        if (cmd.fresh !== true && completed.event === 'imported' && messages.some(m => m.event === 'reused'))
          throw Error('Import completion was ambiguous.');
        outputPage = completed.page_id;
        workspaceRecord(active,'import','finished');
      }
      if (operation === 'sync') {
        const messages = await invoke({...envelope,type:'sync'});
        const result = messages.find(m=>m.type==='sync-result')?.result;
        if (!result || !['baseline','applied','unchanged'].includes(result.status)) throw Error('The local app did not confirm synchronization.');
        if (Object.prototype.hasOwnProperty.call(result, 'preview_url')) {
          const preview = messages.find(m=>m.type==='preview')?.url;
          if (typeof result.preview_url !== 'string' || !/^http:\/\/localhost:\d+\/$/.test(result.preview_url) || preview !== result.preview_url) {
            const {preview_url, ...safeResult} = result;
            return safeResult;
          }
        }
        return result;
      }
      if (operation === 'native-summary') {
        const summary = (await invoke({...envelope,type:'native-summary',fields:['width','height']})).find(m=>m.type==='native-summary')?.summary;
        if (summary?.schema !== 'figma-flow-native-read-summary-v1' || summary.coverage?.profile !== 'summary' ||
            summary.coverage?.complete !== false || !summary.coverage.nodeIds?.includes(cmd.page_id) ||
            JSON.stringify(summary.coverage.fields) !== JSON.stringify(['width','height']) ||
            figma.fileKey !== cmd.file_key || figma.currentPage.id !== cmd.page_id)
          throw Error('Native summary did not return the requested scoped getter.');
        return summary;
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
      if (operation === 'apply' && cmd.selection) throw Error('Partial selection applies only to a signed graph token task.');
      const session = model?.session;
      if (!session) throw Error('Missing prepared native edit session.');
      const messages = await invoke({type:operation,session});
      const data = messages.find(m => m.session === session && m.operation === operation && m.readback)?.readback;
      if (model.recipe_receipt) {
        const recipe = model.recipe_receipt;
        if (data?.schema !== 'figma-flow-example-readback-v1' || data.fileKey !== cmd.file_key ||
            data.pageId !== cmd.page_id || data.recipe !== recipe.recipe || data.pin !== recipe.pin ||
            data.native_edit?.operation !== operation || data.native_edit?.applied !== (operation === 'apply') ||
            (operation === 'apply' && !data.container?.id))
          throw Error('Example result differs from the prepared scope.');
        return data;
      }
      const expected = model.web_screen_receipt;
      const screens = data?.web_design?.screens;
      const valid = expected
        ? data?.schema === 'figma-flow-web-screen-discovery-v1' && data.readback_scope === 'screens'
          && data.graph_sha256 === expected.graph_sha256 && data.web_design?.graph_sha256 === expected.graph_sha256
          && Array.isArray(data.nodes) && Array.isArray(screens) && screens.length === expected.screen_ids.length
          && screens.every((screen, i) => screen.screen_id === expected.screen_ids[i])
        : data?.schema === 'figma-flow-graph-native-discovery-v1';
      if (!valid ||
          data.fileKey !== cmd.file_key || data.pageId !== cmd.page_id || data.native_edit?.operation !== operation ||
          data.native_edit?.applied !== (operation === 'apply'))
        throw Object.assign(Error('Native edit did not return the expected actual getter.'), {nativeReadback:data});
      if (data.web_design?.carousel || data.web_design?.tabs || data.web_design?.disclosure) workspaceAttachCarousel(active, data, cmd.page_id, operation);
      return data;
    }
    const match = active.html.match(/<script id="graph-panel-config" type="application\/json">([\s\S]*?)<\/script>/);
    if (!model && !match) throw Error('Missing prepared graph panel configuration.');
    const panelConfig = model || JSON.parse(match[1]);
    const session = panelConfig.session;
    let command = {type:operation,session};
    if (operation === 'apply' && cmd.selection) {
      const manifest = panelConfig.selection_manifest;
      const allowed = new Set((manifest?.changes || []).map((change, index) => String(change.identity || change.name || change.key || index)));
      const selected = cmd.selection.selected_ids;
      if (cmd.selection.protocol !== 2 || !manifest || manifest.plan_sha256 !== cmd.selection.plan_sha256 ||
          !Array.isArray(selected) || !selected.length || selected.length > 500 ||
          new Set(selected).size !== selected.length || selected.some(id => !allowed.has(id)))
        throw Error('Partial selection differs from the prepared graph plan.');
      command = {...command, protocol:2, plan_sha256:cmd.selection.plan_sha256, selected_ids:selected};
    }
    const messages = await invoke(command);
    const reply = messages.find(m => m.session === session && m.operation === operation && m.readback);
    const data = reply?.readback;
    const discovery = task.kind === 'discover';
    const expectedSchema = operation === 'native-summary' ? 'figma-flow-native-read-summary-v1' :
      discovery ? 'figma-flow-graph-native-discovery-v1' : 'figma-flow-graph-token-readback-v1';
    const scopedSummary = operation === 'native-summary' && data?.coverage?.profile === 'summary'
      && data.coverage.complete === false && Array.isArray(data.coverage.nodeIds) && data.coverage.nodeIds.includes(cmd.page_id)
      && JSON.stringify(data.coverage.fields) === JSON.stringify(['width','height'])
      && figma.fileKey === cmd.file_key && figma.currentPage.id === cmd.page_id;
    if (!data || data.schema !== expectedSchema ||
        data.error || (data.status && data.status !== 'success') ||
        (operation === 'native-summary' ? !scopedSummary : (data.file_key || data.fileKey) !== cmd.file_key ||
          (data.page_id || data.pageId) !== cmd.page_id))
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
    const relayMode = typeof workspaceRelayViewer !== 'undefined' && workspaceRelayViewer;
    if (relayMode && typeof workspaceRelayIdentity === 'function') {
      const identity = workspaceRelayIdentity();
      const scopeKey = identity ? identity + ':' + (figma.fileKey || '') : null;
      if (scopeKey !== controlRelayIdentity || (scopeKey && !workspaceProfile)) {
        controlRelayIdentity = scopeKey;
        if (scopeKey && workspaceProfileManager) {
          try {workspaceProfile = await workspaceProfileManager.load(workspaceState.locale);} catch (_) {workspaceProfile = null;}
          workspaceRelayViewerState(workspaceRelayStatus);
        } else if (!scopeKey) {
          workspaceProfile = null;
        }
      }
    }
    const relayContext = relayMode && typeof workspaceRelayContext === 'function' ? workspaceRelayContext() : null;
    if (controlRelayProfileBinding && (controlRelayProfileBinding.session_id !== relayContext?.session_id ||
        controlRelayProfileBinding.file_key !== relayContext?.file_key || controlRelayProfileBinding.page_id !== relayContext?.page_id ||
        controlRelayProfileBinding.user_id !== relayContext?.user_id)) {
      controlRelayProfileResult = null; controlRelayProfileBinding = null;
    }
    const relay = relayMode && relayContext
      ? {context:relayContext, ...(controlRelayProfileResult ? {profile_result:controlRelayProfileResult} : {})}
      : undefined;
    if (typeof workspaceBindChangePage === 'function') workspaceBindChangePage();
    if (typeof workspaceSampleSelectionChanges === 'function') workspaceSampleSelectionChanges();
    const changeScope = typeof workspaceChangeScope === 'function' ? workspaceChangeScope() : null;
    const changeFeed = typeof workspaceChangeFeed === 'undefined' ? null : workspaceChangeFeed;
    const changeBatch = changeScope && changeFeed
      ? changeFeed.batch(changeScope,workspaceChangeFeedStatus?.status) : null;
    const reply = await controlRequest('poll', {session_id:controlRunSession,file_key:figma.fileKey,page_id:figma.currentPage.id,
      ...(relay ? {relay} : {}),
      ...(changeBatch ? {change_batch:changeBatch} : {}),
      ...(typeof WORKSPACE_RUNTIME === 'undefined' ? {} : {runtime:WORKSPACE_RUNTIME})});
    if (reply?.changes && changeBatch) changeFeed.acknowledge(reply.changes,changeScope);
    if (relayMode) {
      if (controlRelayProfileResult && relay?.profile_result === controlRelayProfileResult) {
        controlRelayProfileResult = null; controlRelayProfileBinding = null;
      }
      const remote = reply?.relay;
      const context = remote?.context;
      const matches = value => value && value.session_id === controlRunSession && value.file_key === figma.fileKey &&
        value.page_id === figma.currentPage.id && value.user_id === (typeof workspaceRelayIdentity === 'function' ? workspaceRelayIdentity() : null);
      if (context && matches(context)) {
        workspaceRelayStatus = 'live'; workspaceRelayError = null;
      } else if (!context) {
        workspaceRelayStatus = 'offline'; workspaceRelayError = 'Relay context is unavailable';
      }
      const request = remote?.profile_request;
      if (request && matches(request) && workspaceProfileManager && !controlRelayProfileResult) {
        workspaceRelayStatus = 'busy'; workspaceRelayError = null; workspaceRelayViewerState('busy');
        try {
          if (!workspaceProfile) {
            try {workspaceProfile = await workspaceProfileManager.load(workspaceState.locale);} catch (_) {workspaceProfile = null;}
          }
          const saved = await workspaceProfileManager.save(request.profile, workspaceState.locale, () => matches(request));
          if (matches(request) && figma.fileKey === request.file_key && figma.currentPage.id === request.page_id) {
            workspaceProfile = saved;
            const persisted = saved?.storage === 'local' && saved?.needsSetup === false;
            controlRelayProfileResult = {request_id:request.request_id, status:persisted?'ok':'uncertain',
              profile:workspaceRelayProfile(), ...(!persisted ? {error_code:'profile-storage-unavailable'} : {})};
            controlRelayProfileBinding = {session_id:request.session_id,file_key:request.file_key,page_id:request.page_id,user_id:request.user_id};
            workspaceRelayLastResult = persisted ? 'ok' : 'uncertain';
            workspaceRelayError = persisted ? null : 'Profile is available for this session only';
          }
        } catch (_) {
          if (matches(request)) {
            controlRelayProfileResult = {request_id:request.request_id,status:'error',error_code:'profile-save-failed'};
            controlRelayProfileBinding = {session_id:request.session_id,file_key:request.file_key,page_id:request.page_id,user_id:request.user_id};
            workspaceRelayLastResult = 'error'; workspaceRelayError = 'Profile could not be saved';
          }
        }
        workspaceRelayStatus = 'live';
      }
      if (context && !matches(context)) { workspaceRelayStatus = 'uncertain'; workspaceRelayError = 'Figma context changed during relay'; }
      workspaceRelayViewerState(workspaceRelayStatus);
    }
    cmd = reply.operation;
    if (!cmd) return;
    const receipt = Object.fromEntries(['id','claim_id','session_id','revision','file_key','page_id'].map(k=>[k,cmd[k]]));
    if (home === workspaceHomeSession) controlState('running', true);
    if (relayMode) {workspaceRelayStatus = 'busy'; workspaceRelayError = null; workspaceRelayViewerState('busy');}
    try {
      if (workspaceActive || home !== workspaceHomeSession || cmd.session_id !== controlRunSession) throw Error('The open workspace session changed.');
      const data = await controlExecute(workspaceTasks.get(cmd.key), cmd, async () => {
        if (home !== workspaceHomeSession || cmd.session_id !== controlRunSession) throw Error('The open workspace session changed.');
        if (typeof WORKSPACE_RUNTIME !== 'undefined') await controlRequest('native-started', {...receipt, runtime: WORKSPACE_RUNTIME});
      });
      receipt.status = 'ok';
      receipt.readback_json = JSON.stringify(data);
    } catch (error) {
      receipt.status = 'error';
      receipt.error = String(error.message || error).slice(0,1900);
      if (error.nativeReadback) receipt.readback_json = JSON.stringify(error.nativeReadback);
    } finally {
      if (typeof workspaceSampleSelectionChanges === 'function' &&
          WORKSPACE_PROFILE_POLICY.operations[cmd.operation] === 'designEdit') workspaceSampleSelectionChanges(true);
    }
    await controlRequest('result', receipt, cmd.operation === 'read');
    if (relayMode) {
      workspaceRelayStatus = 'live';
      workspaceRelayLastResult = receipt.status === 'ok' ? 'ok' : 'error';
      workspaceRelayError = receipt.status === 'ok' ? null : (receipt.error || 'Native task failed');
      if (receipt.status === 'ok') workspaceRelayLastOkAt = new Date().toISOString();
      workspaceRelayViewerState(workspaceRelayStatus, workspaceRelayError);
    }
    if (!relayMode) await workspaceRefreshJournal();
    if (typeof workspaceHandleScopeChange === 'function') await workspaceHandleScopeChange();
    if (home === workspaceHomeSession) controlState(receipt.status === 'ok' ? 'finished' : 'failed', false);
  } catch (_error) {
    controlRetryAt = Date.now() + 8000;
    if (typeof workspaceRelayViewer !== 'undefined' && workspaceRelayViewer) {
      workspaceRelayStatus = cmd ? 'uncertain' : 'offline';
      if (cmd) workspaceRelayLastResult = 'uncertain';
      workspaceRelayError = 'Local relay is unavailable';
      workspaceRelayViewerState(workspaceRelayStatus, workspaceRelayError);
    }
    if (!(typeof workspaceRelayViewer !== 'undefined' && workspaceRelayViewer)) await workspaceRefreshJournal();
    if (typeof workspaceHandleScopeChange === 'function') await workspaceHandleScopeChange();
    if (cmd && home === workspaceHomeSession) controlState('uncertain', false);
  } finally {controlPolling = false;}
}
