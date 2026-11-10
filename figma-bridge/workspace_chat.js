/* A reviewed handoff contains only the current task and explicitly selected nodes. */
const WorkspaceChat = (() => {
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const NODE_ID = /^(?:I?[0-9]+:[0-9]+)(?:;[0-9]+:[0-9]+)*$/;
  const LIMIT = 20;
  const clean = (value, length) => String(value || '').slice(0, length + 512).replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[이메일 생략]').slice(0, length);
  function threadUrl(threadId) {
    if (!UUID.test(threadId || '')) throw Error('연결된 Codex 채팅이 없습니다. 내용을 복사해 사용할 수 있습니다.');
    return 'codex://threads/' + threadId;
  }
  function scope(figma, task) {
    const page = figma.currentPage;
    if (!page || (task.fileKey && task.fileKey !== figma.fileKey) || (task.pageId && task.pageId !== page.id)) {
      throw Error('지정된 Design 파일과 페이지에서 다시 열어 주세요.');
    }
    return page;
  }
  function collect(figma, task, includeText = false, includeSelection = true) {
    const page = scope(figma, task);
    const selected = includeSelection ? page.selection : [];
    if (!Array.isArray(selected) || selected.length > LIMIT) throw Error('선택은 최대 20개까지 포함할 수 있습니다. 선택을 줄여 주세요.');
    let remainingText = 1000;
    const nodes = selected.map(node => {
      if (!node || typeof node.id !== 'string' || node.id.length > 120 || !NODE_ID.test(node.id) ||
          typeof node.type !== 'string' || node.type.length > 64 || !/^[A-Z_]+$/.test(node.type) ||
          ['DOCUMENT', 'PAGE'].includes(node.type)) throw Error('지원하지 않는 선택이 섞여 있습니다.');
      const result = {id: node.id, name: clean(node.name, 120), type: node.type};
      for (const key of ['x', 'y', 'width', 'height']) {
        const value = node[key];
        if (!Number.isFinite(value) || Math.abs(value) > 10000000 || (['width', 'height'].includes(key) && value < 0)) {
          throw Error('크기나 위치를 읽을 수 없는 선택이 있습니다.');
        }
        result[key] = Math.round(value * 100) / 100;
      }
      if (includeText && node.type === 'TEXT' && remainingText > 0) {
        result.textExcerpt = clean(node.characters, Math.min(200, remainingText));
        remainingText -= result.textExcerpt.length;
      }
      return result;
    });
    if (figma.currentPage !== page) throw Error('페이지가 바뀌었습니다. 내용을 다시 확인해 주세요.');
    const fileKey = typeof figma.fileKey === 'string' && figma.fileKey.length <= 128 && /^[A-Za-z0-9_-]+$/.test(figma.fileKey) ? figma.fileKey : null;
    const target = nodes[0]?.id || page.id;
    return {fileKey, page: {id: page.id, name: clean(page.name, 120)}, nodes,
      link: fileKey && NODE_ID.test(target) ? 'https://www.figma.com/design/' + fileKey + '?node-id=' + encodeURIComponent(target.replace(/:/g, '-')) : null};
  }
  function preview(task, message, selection) {
    if (typeof message !== 'string' || message.length > 4000 || (!message.trim() && !selection.nodes.length)) throw Error('요청을 적거나 포함할 노드를 선택해 주세요. 요청은 4000자까지 가능합니다.');
    return (message.trim() || '선택한 Figma 노드를 확인해 주세요.') + '\n\n' + JSON.stringify({schema: 'figma-flow-chat-handoff-v1', task: task.key,
      title: clean(task.title, 160), selection}, null, 2);
  }
  function open(figma, task, options) {
    if (!task || typeof task.key !== 'string' || typeof task.revision !== 'string') throw Error('현재 작업 연결 정보가 없습니다.');
    task = {...task};
    let closed = false, busy = false, prepared = null;
    const used = new Set();
    const current = () => !closed && options.isCurrent();
    const check = () => {if (!current()) throw Error('이전 작업의 연결은 만료되었습니다.'); scope(figma, task);};
    const post = message => {if (current()) options.postMessage(message);};
    const relay = options.relay;
    const paired = !!relay && /^http:\/\/localhost:[0-9]{1,5}$/.test(relay.url || '') && /^[a-f0-9]{64}$/i.test(relay.token || '') &&
      UUID.test(task.threadId || '');
    const context = {title: clean(task.title, 160), threadId: UUID.test(task.threadId || '') ? task.threadId : null, paired};
    const encoded = JSON.stringify(context).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
    options.showUI(options.uiHtml.replace('/* WORKSPACE_CHAT_CONTEXT */', () => encoded), {width: 520, height: 720, themeColors: true});
    async function relayAction(action, requestId, text) {
      check();
      if (!paired) throw Error('로컬 채팅 연결이 없습니다. 내용을 복사하고 채팅에서 붙여 넣어 주세요.');
      if (!UUID.test(requestId || '') || used.has(requestId)) throw Error('이미 처리한 요청입니다. 중복 전송하지 않았습니다.');
      used.add(requestId);
      const body = {key: task.key, threadId: task.threadId, revision: task.revision, requestId};
      if (action === 'queue') body.text = text;
      const requestFetch = options.fetch || fetch;
      let timer;
      const response = await Promise.race([
        requestFetch(relay.url + '/chat/' + action, {method: 'POST',
          headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + relay.token}, body: JSON.stringify(body)}),
        new Promise((_, reject) => {timer = setTimeout(() => reject(Error('접수 여부를 확인할 수 없습니다. Codex 채팅을 확인해 주세요. 자동 재전송하지 않습니다.')), 20000);})
      ]).finally(() => clearTimeout(timer));
      const result = await response.json();
      if (result.status === 'uncertain') throw Error('접수 여부를 확인할 수 없습니다. Codex 채팅을 확인한 뒤 진행해 주세요.');
      if (!response.ok) throw Error('채팅 연결을 확인할 수 없습니다. 같은 요청을 자동으로 다시 보내지 않습니다.');
      if (action === 'queue' && result.status !== 'queued') throw Error('접수 여부를 확인할 수 없습니다. Codex 채팅을 확인해 주세요.');
      post({type: 'chat:result', action, status: action === 'queue' ? 'queued' : 'opened'});
    }
    return {
      close() {closed = true; prepared = null;},
      async handle(message) {
        if (!current() || !message || typeof message !== 'object') return;
        if (message.type === 'chat:back') {if (!busy) options.onBack(); return;}
        if (busy) return;
        try {
          check();
          if (message.type === 'chat:prepare') {
            if (!UUID.test(message.requestId || '')) throw Error('요청을 다시 확인해 주세요.');
            const selection = collect(figma, task, message.includeText === true, message.includeSelection === true);
            prepared = {requestId: message.requestId, text: preview(task, message.message, selection)};
            post({type: 'chat:preview', requestId: prepared.requestId, text: prepared.text, count: selection.nodes.length});
          } else if (message.type === 'chat:queue' || message.type === 'chat:open') {
            const action = message.type === 'chat:queue' ? 'queue' : 'open';
            if (action === 'queue' && (!prepared || message.requestId !== prepared.requestId)) throw Error('변경된 내용을 먼저 미리 확인해 주세요.');
            busy = true;
            await relayAction(action, message.requestId, prepared?.text);
          } else if (message.type === 'chat:open-fallback') {
            figma.openExternal(threadUrl(task.threadId));
            post({type: 'chat:result', action: 'open', status: 'link-requested'});
          }
        } catch (error) {post({type: 'chat:error', message: String(error.message || error)});}
        finally {busy = false;}
      }
    };
  }
  return {collect, preview, threadUrl, open};
})();
