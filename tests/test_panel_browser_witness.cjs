const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const file = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const catalog = Object.assign({}, ...fs.readdirSync(path.join(root, 'figma-bridge/locales'))
  .filter((name) => name.endsWith('.json'))
  .map((name) => JSON.parse(file(`figma-bridge/locales/${name}`))));
const maxNodes = JSON.parse(file('library/figma-profile/read-limits.json')).maxNodes;
const scriptJson = (value) => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');

test('compiled panel runs localized partial read and dependency evidence in installed Chromium', async () => {
  const { withChromiumPage, chromiumBinary, until } = await import(pathToFileURL(path.join(root, 'tools/chromium_pipe.mjs')));
  const binary = chromiumBinary();
  await withChromiumPage(binary, async ({ command, evaluate, product }) => {
    await command('Page.enable');
    const frame = await command('Page.getFrameTree');
    const renderScript = `import json,sys;sys.path.insert(0,'tools');from plugin_panel import render_app;value=json.loads(sys.stdin.read());print(render_app(value['view'],value['model']))`;
    const html = (view, model) => {
      const result = spawnSync(process.env.PYTHON || 'python3', ['-B', '-c', renderScript], {
        cwd: root, input: JSON.stringify({ view, model }), encoding: 'utf8', timeout: 20000,
      });
      assert.equal(result.status, 0, result.stdout + result.stderr);
      return result.stdout.replace('<html lang="ko" data-flow-view=', '<html lang="ko" data-flow-locale="ko" data-flow-view=')
        .replace('<script type="application/json" id="flow-model">',
          '<script>window.__hostMessages=[];window.__errors=[];window.addEventListener(\'error\',event=>window.__errors.push(String(event.error||event.message)));window.addEventListener(\'unhandledrejection\',event=>window.__errors.push(String(event.reason)));window.addEventListener(\'message\',event=>{if(event.data?.pluginMessage)window.__hostMessages.push(event.data.pluginMessage)});</script><script type="application/json" id="flow-model">');
    };
    const render = async (view, model) => {
      await command('Page.setDocumentContent', { frameId: frame.frameTree.frame.id, html: html(view, model) });
      try {
        const selector = view === 'relay' ? "document.querySelector('.relay-view')"
          : view === 'workspace' ? "(document.querySelector('.view-workspace') || document.querySelector('.view-profile-setup'))"
            : `document.querySelector('.view-${view}')`;
        return await until(async () => evaluate(`${selector} ? true : null`), Date.now() + 10000,
          `compiled ${view} view did not render in ${product}`);
      } catch (error) {
        throw Error(`${error.message}; browser=${JSON.stringify(await evaluate(`({errors:window.__errors,root:document.querySelector('#flow-root')?.innerHTML.slice(0,1200)})`))}`);
      }
    };

    for (const view of ['relay', 'review', 'graph', 'chat']) {
      await render(view, {});
      await new Promise((resolve) => setTimeout(resolve, 80));
      const state = await evaluate(`({text:document.querySelector('#flow-root').textContent,errors:window.__errors})`);
      assert.ok(state.text.length > 0, `${view} screen rendered visible content`);
      assert.deepEqual(state.errors, [], `${view} screen has no browser runtime error`);
      if (view === 'chat') {
        assert.equal(await evaluate(`window.FlowUI.t('chat.includeSelection')`),
          catalog['chat.includeSelection'].ko.replace('{maxNodes}', String(maxNodes)));
        await evaluate(`Array.from(document.querySelectorAll('.view-chat button')).find(button=>button.textContent===window.FlowUI.t('chat.prepare'))?.click()`);
        await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='chat:prepare') || null`), Date.now() + 3000,
          'Chat view did not send a review request');
        const chatRequest = await evaluate(`window.__hostMessages.find(message=>message.type==='chat:prepare')`);
        await evaluate(`window.postMessage({pluginMessage:${scriptJson({ type: 'chat:preview', requestId: chatRequest.requestId, text: 'Reviewed handoff', count: 1 })}},'*')`);
        await until(async () => evaluate(`document.querySelector('#chat-preview')?.value==='Reviewed handoff' ? true : null`), Date.now() + 3000,
          'Chat view did not display its exact reviewed preview');
        await evaluate(`window.postMessage({pluginMessage:{type:'chat:error',code:'scope',message:'Native diagnostic without locale text.'}},'*')`);
        assert.equal(await evaluate(`document.querySelector('.view-chat .status-body').textContent`), catalog['chat.scopeError'].ko);
        await evaluate(`window.FlowUI.setLocale('en')`);
        assert.equal(await evaluate(`document.querySelector('.view-chat .status-body').textContent`), catalog['chat.scopeError'].en);
        assert.equal(await evaluate(`document.querySelector('.chat-diagnostics').textContent`), 'Native diagnostic without locale text.');
      }
      if (view === 'review') {
        await evaluate(`document.querySelector('#make').click()`);
        await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='draft-review') || null`), Date.now() + 3000,
          'Review view did not send its explicit draft request');
        await evaluate(`window.postMessage({pluginMessage:{type:'readback',data:{schema:'figma-flow-native-readback-v1',nodes:[]}}},'*')`);
        await until(async () => evaluate(`document.querySelector('#status-panel .status-title')?.textContent===window.FlowUI.t('review.readTitle') ? true : null`), Date.now() + 3000,
          'Review view did not render its native readback state');
        assert.equal(await evaluate(`document.querySelector('#status-panel .status-body').textContent`), catalog['review.readBody'].ko);
      }
      if (view === 'relay') {
        const request = await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='workspace-home-ready') || null`), Date.now() + 3000,
          'Relay view did not request host state');
        await evaluate(`window.postMessage({pluginMessage:{type:'workspace-relay-viewer-state',requestId:${scriptJson(request.requestId)},workspaceSession:'session-a',status:'live',file:{key:'file-a',name:'Sample file'},page:{id:'0:1',name:'Page one'},selection:[{id:'2:3',type:'FRAME',name:'Hero frame'}],selectionTotal:1,selectionTruncated:false,locale:'en'}},'*')`);
        await until(async () => evaluate(`document.querySelector('.relay-layers tbody tr') ? true : null`), Date.now() + 3000,
          'Relay view did not render the host selection table');
        const relay = await evaluate(`({text:document.querySelector('.relay-view').textContent,caption:document.querySelector('.relay-layers caption').textContent,cell:document.querySelector('.relay-layers tbody').textContent,errors:window.__errors})`);
        assert.match(relay.text, /Sample file/);
        assert.equal(relay.caption, catalog['relay.selection.title'].en);
        assert.match(relay.cell, /Hero frame/);
        assert.deepEqual(relay.errors, []);
      }
    }

    await render('graph', { mode: 'discovery', session: 'graph-session', file_key: 'file-a', page_id: '0:1', pages: [] });
    await evaluate(`Array.from(document.querySelectorAll('.view-graph button')).find(button=>button.textContent===window.FlowUI.t('graph.summaryRead'))?.click()`);
    await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='native-summary') || null`), Date.now() + 3000,
      'Graph discovery did not send its partial read request');
    const graphRequest = await evaluate(`window.__hostMessages.find(message=>message.type==='native-summary')`);
    await evaluate(`window.postMessage({pluginMessage:{session:${scriptJson(graphRequest.session)},readback:{schema:'figma-flow-native-read-summary-v1',coverage:{profile:'summary',complete:false,fields:['width','height'],nodeIds:['0:1'],omitted:['fills']},nodes:[{id:'0:1',width:320,height:640}]}}},'*')`);
    await until(async () => evaluate(`document.querySelector('.native-summary')?.textContent.includes('320') || null`), Date.now() + 3000,
      'Graph discovery did not show its observed summary');
    await evaluate(`Array.from(document.querySelectorAll('.view-graph button')).find(button=>button.textContent===window.FlowUI.t('graph.auditOpen'))?.click()`);
    await until(async () => evaluate(`document.querySelector('.audit-export textarea') ? true : null`), Date.now() + 3000,
      'Diagnostic export did not open its read-only evidence text');
    assert.match(await evaluate(`document.querySelector('.audit-export textarea').value`), /native_read/);

    await render('import', { connected: true, paired: false, fresh: true });
    await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='ready') || null`), Date.now() + 3000,
      'Import view did not announce its native session');
    const ready = await evaluate(`window.__hostMessages.find(message=>message.type==='ready')`);
    await evaluate(`window.postMessage({pluginMessage:{type:'status',ready:true,paired:false,session_nonce:${scriptJson(ready.session_nonce)}}},'*')`);
    await until(async () => evaluate(`document.querySelector('.native-summary-request')?.disabled === false ? true : null`), Date.now() + 3000,
      'Import view did not enable its native controls after connection');
    const summaryButton = await evaluate(`document.querySelector('.native-summary-request')?.textContent.trim()`);
    assert.equal(summaryButton, catalog['import.readDimensionsOnly'].ko);
    await evaluate(`document.querySelector('.native-summary-request').click()`);
    await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='native-summary') || null`), Date.now() + 3000,
      'Import view did not send the bounded summary request');
    const request = await evaluate(`window.__hostMessages.find(message=>message.type==='native-summary')`);
    assert.deepEqual(request.fields, ['width', 'height']);
    await evaluate(`window.postMessage({pluginMessage:{type:'native-summary',session_nonce:${scriptJson(request.session_nonce)},summary:{schema:'figma-flow-native-read-summary-v1',coverage:{profile:'summary',complete:false,fields:['width','height'],nodeIds:['0:1'],omitted:['fills']},nodes:[{id:'0:1',width:320,height:640}]}}},'*')`);
    try {
      await until(async () => evaluate(`document.querySelector('.native-summary')?.textContent.includes('320') || null`), Date.now() + 3000,
        'Import view did not display the partial native summary');
    } catch (error) {
      throw Error(`${error.message}; panel=${JSON.stringify(await evaluate(`({rootLength:document.querySelector('#flow-root').innerHTML.length,summary:document.querySelector('.native-summary')?.outerHTML,errors:window.__errors})`))}; messages=${JSON.stringify(await evaluate('window.__hostMessages'))}`);
    }
    await evaluate(`window.FlowUI.setLocale('en')`);
    assert.equal(await evaluate(`document.querySelector('.native-summary-request').textContent.trim()`), catalog['import.readDimensionsOnly'].en);
    assert.match(await evaluate(`document.querySelector('.native-summary').textContent`), /^Partial read/);
    await evaluate(`window.FlowUI.setLocale('ja')`);
    assert.equal(await evaluate(`document.querySelector('.native-summary-request').textContent.trim()`), catalog['import.readDimensionsOnly'].ja);
    assert.match(await evaluate(`document.querySelector('.native-summary').textContent`), /^部分読み取り/);

    const revA = 'a'.repeat(64), revB = 'b'.repeat(64), digest = 'c'.repeat(64);
    const model = { fileKey: 'file-a', pageId: '0:1', project: 'demo', view: 'tasks', tasks: [
      { key: 'foundation', title: 'Foundation', project: 'demo', kind: 'review', revision: revA },
      { key: 'screen', title: 'Screen', project: 'demo', kind: 'review', revision: revB, depends_on: [
        { task_key: 'foundation', revision: revA, relation: 'uses-output', artifact: 'code.js', artifact_sha256: digest },
      ] },
    ], history: [], retired: [] };
    await render('workspace', model);
    await until(async () => evaluate(`document.querySelectorAll('.workspace-dependency-link').length > 0 ? true : null`), Date.now() + 3000,
      'Workspace task actions did not render');
    await evaluate(`Array.from(document.querySelectorAll('.workspace-row-title')).find(node=>node.textContent==='Screen')?.closest('.workspace-row-group')?.querySelector('.workspace-dependency-link')?.click()`);
    await until(async () => evaluate(`document.querySelector('.workspace-dependency-view') ? true : null`), Date.now() + 3000,
      'Workspace did not open dependency evidence');
    await evaluate(`window.FlowUI.setLocale('en')`);
    const englishEvidence = await evaluate(`document.querySelector('.workspace-dependency-text')?.textContent`);
    assert.match(englishEvidence, /^Predecessor Foundation/);
    assert.ok(englishEvidence.includes(`Current ${revA} · Pinned ${revA}`));
    await evaluate(`window.FlowUI.setLocale('ja')`);
    const japaneseEvidence = await evaluate(`document.querySelector('.workspace-dependency-text')?.textContent`);
    assert.match(japaneseEvidence, /^先行 Foundation/);
    assert.ok(japaneseEvidence.includes(`現在 ${revA} · 固定 ${revA}`));
    if (process.env.FIGMA_FLOW_PANEL_WORKSPACE_SCREENSHOT) {
      const screenshot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
      fs.writeFileSync(process.env.FIGMA_FLOW_PANEL_WORKSPACE_SCREENSHOT, Buffer.from(screenshot.data, 'base64'));
    }

    const carouselTask = { key: 'carousel', title: 'Carousel demo', project: 'demo', kind: 'native-edit',
      revision: revA, fileKey: 'file-a', pageId: '0:1' };
    const carousel = { schema: 'figma-flow-carousel-summary-v1', status: 'current', file_key: 'file-a', page_id: '0:1',
      flow_start_node_id: '2:3', initial_state: 'idle', frame_key: 'frame-a',
      states: [{ state_id: 'idle', screen_id: 'home', title: 'Home', status: 'current' }], edges: [] };
    const carouselEvent = { taskKey: 'carousel', revision: revA, executionId: 'exec-a', status: 'finished', operation: 'apply', carousel };
    await render('workspace', { fileKey: 'file-a', pageId: '0:1', project: 'demo', view: 'tasks',
      tasks: [carouselTask], history: [carouselEvent], retired: [] });
    await evaluate(`window.postMessage({pluginMessage:${scriptJson({ type: 'workspace-tasks', workspaceSession: 'session-a', fileKey: 'file-a', pageId: '0:1', project: 'demo', view: 'tasks', tasks: [carouselTask], history: [carouselEvent], retired: [] })}},'*')`);
    await until(async () => evaluate(`document.querySelector('.workspace-carousel-present') ? true : null`), Date.now() + 3000,
      'Workspace did not show the current carousel actions');
    const presentation = 'https://www.figma.com/proto/file-a/demo?node-id=2-3&starting-point-node-id=2-3&page-id=0-1&scaling=scale-down';
    await evaluate(`window.postMessage({pluginMessage:${scriptJson({ type: 'workspace-carousel-presented', workspaceSession: 'session-a', taskKey: 'carousel', executionId: 'exec-a', nodeId: '2:3', stateId: 'idle', url: presentation })}},'*')`);
    await until(async () => evaluate(`document.querySelector('.workspace-carousel-link a') ? true : null`), Date.now() + 3000,
      'Workspace did not render the host-verified Figma Present link');
    assert.equal(await evaluate(`document.querySelector('.workspace-carousel-link a').href`), presentation);
    await evaluate(`document.querySelector('.workspace-carousel-link button').click()`);
    await until(async () => evaluate(`document.querySelector('.workspace-carousel-link-status')?.textContent || null`), Date.now() + 3000,
      'Workspace did not provide manual or copied link status');

    const profile = { schemaVersion: 1, needsSetup: true, storage: 'local',
      context: { userId: 'user-a', userName: 'Ada', fileKey: 'file-a', pageId: '0:1', fileName: 'Sample', pageName: 'Page one',
        apiVersion: '1', pluginVersion: '0.36.0', pluginId: 'plugin-a', locale: 'ko', editorType: 'figma', mode: 'design' },
      declared: { plan: 'unknown', seat: 'unknown' }, options: { plans: ['unknown', 'starter'], seats: ['unknown', 'editor'] },
      capabilities: { designRead: true, designEdit: false, devHandoff: false, devInspect: false } };
    const profileModel = { fileKey: 'file-a', pageId: '0:1', project: 'demo', view: 'tasks', tasks: [], history: [], profile };
    await render('workspace', profileModel);
    await until(async () => evaluate(`document.querySelector('.workspace-profile') ? true : null`), Date.now() + 3000,
      'Workspace setup profile did not render');
    await evaluate(`window.postMessage({pluginMessage:${scriptJson({ type: 'workspace-tasks', workspaceSession: 'profile-session', fileKey: 'file-a', pageId: '0:1', project: 'demo', view: 'tasks', tasks: [], history: [], profile })}},'*')`);
    await evaluate(`Array.from(document.querySelectorAll('.workspace-profile-actions button')).find(button=>button.textContent===window.FlowUI.t('workspace.profile.continueUnknown'))?.click()`);
    await until(async () => evaluate(`window.__hostMessages.find(message=>message.type==='workspace-profile-save') || null`), Date.now() + 3000,
      'Workspace profile did not submit the explicit unknown declaration');
    const profileSave = await evaluate(`window.__hostMessages.find(message=>message.type==='workspace-profile-save')`);
    assert.equal(profileSave.plan, 'unknown');
    assert.equal(profileSave.seat, 'unknown');
    assert.equal(profileSave.workspaceSession, 'profile-session');
    if (process.env.FIGMA_FLOW_PANEL_PROFILE_SCREENSHOT) {
      const screenshot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
      fs.writeFileSync(process.env.FIGMA_FLOW_PANEL_PROFILE_SCREENSHOT, Buffer.from(screenshot.data, 'base64'));
    }
    console.log(`Observed compiled import and dependency views in ${product}.`);
  });
});
