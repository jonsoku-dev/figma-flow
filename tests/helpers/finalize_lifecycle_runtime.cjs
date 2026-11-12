// Real published host + HTTP, with no Figma mutations or browser/native claims.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const [mode, filename, operationId] = process.argv.slice(2);

async function main() {
  const messages = [], calls = [];
  const figma = {fileKey:'fixturefile', currentPage:{id:'12:1'},
    ui:{postMessage: value => messages.push(value)}, showUI(){},
    clientStorage:{getAsync:async()=>({locale:'ko',history:[]}), setAsync:async()=>{}}};
  const context = vm.createContext({figma, __html__:'<html></html>', console,
    setTimeout, clearTimeout, fetch:async(url, options)=>{
      const route = String(url).split('/').at(-1); calls.push(route);
      const response = await fetch(url, options);
      if (mode !== 'expired' || route !== 'poll') return response;
      const body = await response.json();
      if (body.operation) body.operation.deadline = Date.now()/1000 - 1;
      return {ok:response.ok,status:response.status,json:async()=>body};
    }});
  vm.runInContext(fs.readFileSync(filename, 'utf8'), context);
  await figma.ui.onmessage({type:'workspace-home-ready',locale:'ko'});
  if (mode === 'stale') vm.runInContext("workspaceTasks.get('discovery').revision = 'stale-oracle'", context);
  if (mode === 'history') {
    // A queued request is a canonical fact even before this host polls it.
    const initial = messages.find(message => message.type === 'workspace-tasks');
    assert.ok(initial, 'published home must emit a model');
    const rows = initial.journalHistory;
    assert.ok(Array.isArray(rows), 'published host must retrieve canonical server journal, separately from telemetry');
    const row = rows.find(row => row.operationId === operationId);
    assert.equal(row?.phase, 'queued', 'real HTTP journal must reach the actual published host model');
    assert.equal(row.classification, 'recorded');
    assert.equal(initial.history.length, 0, 'journal cannot masquerade as clientStorage telemetry');
    const {build} = require('../../panel-ui/node_modules/esbuild');
    const bundle = await build({entryPoints:[path.resolve('panel-ui/src/Workspace.jsx')],bundle:true,write:false,
      platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom'],
      define:{__FLOW_LOCALES__:'["ko"]',__FLOW_DISPLAY_NAME__:'"Figma Flow"'}});
    const Module = require('node:module');
    const loaded = new Module(path.resolve('panel-ui/oracle.cjs'));
    loaded.filename = path.resolve('panel-ui/oracle.cjs');
    loaded.paths = Module._nodeModulePaths(path.resolve('panel-ui'));
    loaded._compile(bundle.outputFiles[0].text, loaded.filename);
    const React = require('../../panel-ui/node_modules/react');
    const {renderToStaticMarkup} = require('../../panel-ui/node_modules/react-dom/server');
    const html = renderToStaticMarkup(React.createElement(loaded.exports.default,{model:{...initial,view:'history'},
      t:(key)=>key,send(){},setLocale(){},Shell:({children})=>React.createElement('main',null,children)}));
    assert.ok(html.includes(operationId), 'actual history UI must render the canonical operation identity');
    assert.ok(html.includes('queued'), 'actual history UI must render the canonical phase');
  } else {
    await context.workspaceControlTick();
    assert.ok(calls.includes('poll'), 'oracle must traverse real authenticated poll');
    assert.ok(!calls.includes('native-started'), `${mode} preflight rejection must not claim native dispatch`);
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
