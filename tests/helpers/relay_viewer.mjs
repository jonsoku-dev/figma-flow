// Exercise the built panel with a forwarded Figma event whose source is null.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { chromiumBinary, until, withChromiumPage } from '../../tools/chromium_pipe.mjs';

let binary;
try { binary = chromiumBinary(); }
catch { process.exit(77); }
const html = await readFile(process.argv[2]);
const server = createServer((_, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html;charset=utf-8' });
  response.end(html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
try {
  await withChromiumPage(binary, async ({ command, evaluate }) => {
    await command('Page.enable');
    await command('Page.addScriptToEvaluateOnNewDocument', {
      source: `window.addEventListener('message', event => {
        const message = event.data?.pluginMessage;
        if (message?.type === 'workspace-home-ready') window.readyId = message.requestId;
        if (message?.type === 'workspace-control-tick') window.tick = message;
      });`
    });
    await command('Page.navigate', { url: 'http://127.0.0.1:' + server.address().port });
    const waitFor = expression => until(() => evaluate(expression), Date.now() + 8000, expression);
    const requestId = await waitFor('window.readyId');
    const post = (id, session, status) => {
      const message = {type: 'workspace-relay-viewer-state', requestId: id, workspaceSession: session, status,
        file: {key:'testfile',name:'Design source'}, page:{id:'2:3',name:'Booking'},
        selection:[{id:'4:5',name:'Reserve',type:'INSTANCE'}]};
      return evaluate("window.dispatchEvent(new MessageEvent('message', {data:{pluginMessage:" + JSON.stringify(message) + '}}))');
    };
    const status = "document.querySelector('[role=status]').dataset.state";
    await post('wrong', 'test-session', 'busy');
    assert.equal(await evaluate(status), 'offline');
    await post(requestId, 'test-session', 'live');
    await waitFor(status + "==='live'");
    assert.match(await evaluate('document.body.innerText'), /Design source[\s\S]*Booking[\s\S]*Reserve/);
    assert.equal(await evaluate("document.querySelectorAll('button,input,textarea,select').length"), 0);
    const tick = await waitFor('window.tick');
    assert.deepEqual(tick,{type:'workspace-control-tick',workspaceSession:'test-session',fileKey:'testfile'});
    await post(requestId, 'other-session', 'busy');
    assert.equal(await evaluate(status), 'live');
  });
} finally {
  await new Promise(resolve => server.close(resolve));
}
