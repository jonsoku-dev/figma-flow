const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const host = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_host.js'), 'utf8');
const home = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_home.html'), 'utf8');
function harness(frozen = false, options = {}) {
  const messages = [], shown = [], writes = [], commands = [], proxies = [];
  const probe = {messages, shown, writes, commands, proxies, pending: null, closeCount: 0, chatCalls: []};
  const figma = {
    fileKey: options.fileKey || 'file-a', ui: {postMessage(message) {assert.equal(this, figma.ui); messages.push(message);}},
    showUI(html, options) {assert.equal(this, figma); shown.push({html, options});},
    createPage() {assert.equal(this, figma); writes.push('page');}
  };
  if (options.storage) figma.clientStorage = options.storage;
  if (frozen) {
    let handler;
    Object.defineProperty(figma.ui, 'onmessage', {get() {return handler;}, set(value) {handler=value;}, configurable:false});
    Object.freeze(figma.ui); Object.freeze(figma);
  }
  const context = vm.createContext({figma, __html__: 'HOME', probe});
  vm.runInContext(`
const WORKSPACE_CHAT_UI = '<html><head></head><body>CHAT</body></html>';
const WORKSPACE_CHAT_CONFIG = {url:'http://127.0.0.1:1234',token:'host-only-secret'};
const WorkspaceChat = {open(figma,task,options) {
  probe.chatCalls.push({task,options}); options.showUI(options.uiHtml,{width:480,height:640});
  return {async handle(message){probe.commands.push(message.type);if(probe.pending)await probe.pending;},close(){probe.closeCount++;}};
}};
function runTask() {
  if(probe.failInit)throw Error('synthetic init failure');
  const figma = workspaceTaskFigma(); probe.proxies.push(figma);
  figma.showUI(workspaceTaskHtml('<html><head></head><body><script>parent.postMessage({pluginMessage:{type:"ready"}},"*");</script></body></html>'),{width:480,height:640});
  figma.ui.onmessage = async message => {
    probe.commands.push(message.type);
    if(probe.emitBusyStart)figma.ui.postMessage({type:'busy',value:true});
    if(message.type==='draft-review')figma.ui.postMessage({type:'readback',data:{secret:'PRIVATE CONTENT'}});
    if(message.type==='apply')figma.ui.postMessage({operation:'apply',readback:{secret:'PRIVATE CONTENT'}});
    if(message.type==='read') {if(probe.pending)await probe.pending;figma.createPage();}
    figma.ui.postMessage({type:'result',value:message.type});
    if(probe.emitBusyStart)figma.ui.postMessage({type:'busy',value:false});
  };
}
const FLOW_TASKS = [
 {key:'a',title:'Import A',project:'Project A',kind:${JSON.stringify(options.kind || 'import')},revision:'r1',fileKey:'file-a',pageId:'1:2',threadId:'thread-a',run:runTask},
 {key:'b',title:'Review B',project:'Project B',kind:'review',revision:'r1',fileKey:null,threadId:'thread-b',run:runTask},
 {key:'foreign',title:'Other file',project:'Project A',kind:'sync',fileKey:'file-b',run:runTask}
];
` + host, context);
  const send = message => figma.ui.onmessage(message);
  async function listing() {
    await send({type: 'workspace-home-ready'});
    return messages.filter(message => message.type === 'workspace-tasks').at(-1);
  }
  async function open(key, type = 'workspace-open') {
    const list = await listing();
    await send({type, key, workspaceSession: list.workspaceSession});
    const match = shown.at(-1).html.match(/const workspaceSession = ("[^"]+")/);
    return match ? JSON.parse(match[1]) : null;
  }
  return {figma, context, probe, send, listing, open};
}

test('home lists registered metadata, exact-key and file guards prevent execution', async () => {
  const h = harness();
  assert.equal(h.probe.shown.length, 1);
  assert.equal(h.probe.shown[0].options.themeColors, true);
  const list = await h.listing();
  assert.equal(list.tasks.length, 3);
  assert.equal(list.tasks[0].pageId, '1:2');
  assert.equal('run' in list.tasks[0], false);
  assert.equal(JSON.stringify(list).includes('host-only-secret'), false);
  await h.send({type:'workspace-open',key:'a'});
  await h.send({type:'workspace-open',key:'unknown',workspaceSession:list.workspaceSession});
  await h.send({type:'workspace-open',key:'foreign',workspaceSession:list.workspaceSession});
  assert.equal(h.probe.shown.length, 1);
  assert.equal(h.probe.proxies.length, 0);
  assert.match(h.probe.messages.at(-1).message, /지정된 Design 파일/);
  await h.open('a');
  assert.equal(h.probe.proxies.length, 1);
  assert.deepEqual(h.probe.writes, []);
  assert.deepEqual(h.probe.commands, []);
});

test('frozen Figma API and UI properties permit task open and bound native calls', async () => {
  const h = harness(true);
  assert.equal(Object.isFrozen(h.figma),true);
  assert.equal(Object.isFrozen(h.figma.ui),true);
  assert.equal(Object.getOwnPropertyDescriptor(h.figma,'ui').configurable,false);
  assert.equal(Object.getOwnPropertyDescriptor(h.figma.ui,'postMessage').writable,false);
  const session = await h.open('a');
  assert.ok(session);
  assert.deepEqual(h.probe.writes,[]);
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'read'}});
  assert.deepEqual(h.probe.writes,['page']);
  assert.equal(h.probe.messages.some(message=>message.payload?.type==='result'),true);
  await h.send({type:'workspace-back',workspaceSession:session});
  assert.equal(h.probe.shown.at(-1).html,'HOME');
});

test('initialization errors remain visible after the new home requests its list', async () => {
  const h = harness(); h.probe.failInit = true;
  await h.open('a');
  assert.equal(h.probe.shown.at(-1).html,'HOME');
  const listing = await h.listing();
  assert.equal(listing.error,'synthetic init failure');
  assert.deepEqual(h.probe.writes,[]);
});

test('in-flight work blocks navigation; old UI envelopes and expired proxies cannot reach next task', async () => {
  const h = harness();
  const first = await h.open('a');
  let release;
  h.probe.pending = new Promise(resolve => {release = resolve;});
  const running = h.send({type:'workspace-task-message',workspaceSession:first,payload:{type:'read'}});
  await h.send({type:'workspace-back',workspaceSession:first});
  await h.send({type:'workspace-history',workspaceSession:first});
  await h.send({type:'workspace-chat',workspaceSession:first});
  assert.equal(h.probe.shown.length, 2);
  assert.equal(h.probe.messages.at(-1).busy, true);
  release(); await running; h.probe.pending = null;
  assert.deepEqual(h.probe.writes, ['page']);
  await h.send({type:'workspace-back',workspaceSession:first});
  assert.equal(h.probe.shown.at(-1).html, 'HOME');
  const second = await h.open('b');
  assert.notEqual(first, second);
  await h.send({type:'workspace-task-message',workspaceSession:first,payload:{type:'read'}});
  await h.send({type:'workspace-task-message',workspaceSession:first,payload:{type:'receipt',passed:true}});
  await h.send({type:'read'});
  assert.deepEqual(h.probe.commands, ['read']);
  assert.throws(() => h.probe.proxies[0].createPage(), /expired/);
  const count = h.probe.messages.length;
  h.probe.proxies[0].ui.postMessage({type:'late'});
  assert.equal(h.probe.messages.length, count);
  await h.send({type:'workspace-task-message',workspaceSession:second,payload:{type:'inspect'}});
  assert.deepEqual(h.probe.commands, ['read','inspect']);
});

test('task messages stay scoped when the current file changes', async () => {
  const h = harness(); const session = await h.open('a');
  h.figma.fileKey = 'file-b';
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'read'}});
  assert.equal(h.probe.commands.length, 0);
  assert.throws(() => h.probe.proxies[0].createPage(), /file scope changed/);
});

test('chat opens without executing task and remains isolated across return and async relay', async () => {
  const h = harness();
  const session = await h.open('a', 'workspace-chat-open');
  assert.equal(h.probe.proxies.length, 0);
  assert.equal(h.probe.chatCalls.length, 1);
  assert.equal(h.probe.chatCalls[0].options.relay.token, 'host-only-secret');
  assert.equal(h.probe.shown.at(-1).html.includes('host-only-secret'), false);
  let release; h.probe.pending = new Promise(resolve => {release = resolve;});
  const running = h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'chat:queue'}});
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'chat:back'}});
  assert.notEqual(h.probe.shown.at(-1).html, 'HOME');
  release(); await running; h.probe.pending = null;
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'chat:back'}});
  assert.equal(h.probe.shown.at(-1).html, 'HOME');
  assert.equal(h.probe.closeCount, 1);
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'chat:queue'}});
  assert.deepEqual(h.probe.commands, ['chat:queue']);
});

test('React workspace bridge exposes authenticated navigation, busy events, locale persistence and legacy fallback', async () => {
  const h=harness(); const session=await h.open('a');
  const noHead=vm.runInContext("workspaceTaskHtml('<!doctype html><html lang=ko><meta charset=utf-8><body>panel</body></html>')",h.context);
  assert.match(noHead,/^<!doctype html><html lang=ko data-flow-locale="ko" data-flow-workspace="true"><script>/);
  const relay=h.probe.shown.at(-1).html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const posted=[],listeners={},events=[],states=[];let legacy;
  const form={value:'unsaved form input'};
  const window={parent:{postMessage:message=>posted.push(message)},addEventListener:(type,fn)=>{listeners[type]=fn;},
    dispatchEvent:event=>events.push(event),FlowUI:{setLocale(code){this.locale=code;}},
    FlowPanel:{mount(options){legacy=options;},setState(state){states.push(state);}}};
  const document={addEventListener(){}};
  const context=vm.createContext({window,document,CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}}});
  vm.runInContext(relay,context);
  vm.runInContext('parent.postMessage({pluginMessage:{type:"receipt",passed:true}},"*");',context);
  assert.equal(posted[0].pluginMessage.workspaceSession,session);assert.equal(posted[0].pluginMessage.payload.type,'receipt');
  listeners.DOMContentLoaded();assert.equal(legacy.mode,'workspace');assert.equal(legacy.active,'tasks');
  assert.equal(posted.at(-1).pluginMessage.type,'workspace-navigation-ready');
  window.FlowWorkspace.go('history');assert.equal(posted.at(-1).pluginMessage.type,'workspace-history');
  const count=posted.length;window.FlowWorkspace.go('invalid');assert.equal(posted.length,count);
  const busy={data:{pluginMessage:{workspaceSession:session,workspaceControl:true,busy:true}},stopImmediatePropagation(){}};
  listeners.message(busy);assert.equal(window.FlowWorkspace.busy,true);assert.equal(states.at(-1).busy,true);
  assert.equal(events.at(-1).type,'flow:host-busy');assert.equal(events.at(-1).detail.busy,true);
  window.FlowWorkspace.go('tasks');assert.equal(posted.length,count);
  window.FlowWorkspace.setLocale('ja');assert.equal(posted.at(-1).pluginMessage.type,'workspace-locale');
  assert.equal(posted.at(-1).pluginMessage.locale,'ja');assert.equal(form.value,'unsaved form input');
  const old={data:{pluginMessage:{workspaceSession:'old',payload:{type:'result'}}},stopImmediatePropagation(){this.stopped=true;}};
  listeners.message(old);assert.equal(old.stopped,true);
  const incoming={data:{pluginMessage:{workspaceSession:session,payload:{type:'result'}}},stopImmediatePropagation(){}};
  listeners.message(incoming);assert.equal(incoming.data.pluginMessage.type,'result');
  await h.send({type:'workspace-locale',workspaceSession:session,locale:'en'});
  assert.equal(vm.runInContext('workspaceState.locale',h.context),'en');
  await h.send({type:'workspace-locale',workspaceSession:'old',locale:'ja'});
  assert.equal(vm.runInContext('workspaceState.locale',h.context),'en');
});

class Element {
  constructor(tag, document) {this.tagName=tag;this.document=document;this.children=[];this.dataset={};this.hidden=false;this.attributes={};}
  appendChild(child) {this.children.push(child);return child;}
  replaceChildren() {this.children=[];}
  setAttribute(key,value) {this.attributes[key]=value;}
  addEventListener(type, fn) {this[type]=fn;}
  querySelectorAll() {return this.children.flatMap(child=>[...(child.tagName==='button'&&!child.disabled?[child]:[]),...child.querySelectorAll()]);}
  focus() {this.document.activeElement=this;}
}
function homeHarness() {
  const posts=[], document={activeElement:null};
  const ids=['task-list','history-list','home-status','home-status-title','home-status-body','workspace-title',
    'workspace-locale','workspace-tablist','project-filter','stage-filter','next-action','project-scope','project-subtitle','type-filter','recent-receipt','project-preview','automatic-notice','history-boundary','tab-tasks','tab-history','tab-codex'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element('div',document)]));
  document.getElementById=id=>elements[id]; document.createElement=tag=>new Element(tag,document);
  const dictionary=JSON.parse(fs.readFileSync(path.join(__dirname,'../figma-bridge/locales/workspace.json'),'utf8'));
  const window={addEventListener(){},FlowUI:{locale:'ko',apply(){},setLocale(code){this.locale=code;},t(key,params={}){
    let text=dictionary[key]?.[this.locale]||key;for(const [name,value]of Object.entries(params))text=text.replace('{'+name+'}',value);return text;
  }}};
  window.FlowPanel={mount(options){this.settings=options;for(const name of ['tasks','history','codex'])elements['tab-'+name].onclick=()=>options.onNavigate(name);elements['workspace-locale'].onchange=event=>options.onLocale(event.target.value);},
    setState({active,busy}){for(const name of ['tasks','history','codex']){elements['tab-'+name].disabled=!!busy;elements['tab-'+name].attributes['aria-current']=name===active?'page':undefined;}},
    status({region,title,body,state,titleText,bodyText}){elements[region].hidden=false;elements[region].dataset.state=state;elements[title].textContent=titleText;elements[body].textContent=bodyText;}};
  const context=vm.createContext({window,document,parent:{postMessage:m=>posts.push(m)}});
  vm.runInContext(home.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  const receive=message=>window.onmessage({data:{pluginMessage:message}});
  const text=element=>(element.textContent||'')+element.children.map(text).join(' ');
  return {posts,document,elements,receive,text,window};
}
test('home exposes workflow, private scope, accessible project filtering, keyboard and empty states',()=>{
  const h=homeHarness(), {elements,posts,document}=h;
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'file-a',locale:'ko',history:[],tasks:[
    {key:'a',title:'<script>hostile</script>',project:'Actual project',kind:'review',threadId:'t',fileKey:'file-a',pageId:'1:2',revision:'r1'},
    {key:'b',title:'Other',project:'Actual project',kind:'sync',fileKey:'file-b',revision:'r1'},
    {key:'c',title:'Read',project:'Second project',kind:'discover',threadId:'t',revision:'r1'}]});
  assert.equal(elements['next-action'].hidden,false);
  assert.equal(elements['workspace-title'].textContent,'Actual project');
  assert.equal(h.text(elements['task-list']).includes('hostile'),false,'recommended task must not repeat in list');
  assert.match(h.text(elements['task-list']),/다른 파일에서 실행/);
  assert.equal(h.text(elements['task-list']).includes('file-a'),false);
  assert.equal(h.text(elements['task-list']).includes('1:2'),false);
  const primary=elements['next-action'].querySelectorAll()[0];assert.equal(primary.className,'primary');
  primary.onclick();assert.equal(posts.at(-1).pluginMessage.key,'a');
  elements['project-filter'].onchange({target:{value:''}});
  const buttons=elements['task-list'].querySelectorAll();assert.equal(buttons.length,1);
  assert.equal(buttons[0].className,'task-hit');
  buttons[0].focus();elements['task-list'].keydown({key:'End',preventDefault(){}});assert.equal(document.activeElement,buttons.at(-1));
  elements['project-filter'].onchange({target:{value:'Second project'}});
  assert.equal(h.text(elements['task-list']).includes('hostile'),false);
  h.receive({type:'workspace-tasks',workspaceSession:'home',locale:'ko',history:[],tasks:[]});
  assert.equal(elements['home-status'].hidden,false);assert.equal(elements['home-status-title'].textContent,'준비된 작업이 없습니다');
});
test('home history marks stale revisions, never treats downloads as save acknowledgements, and changes locale instantly',()=>{
  const h=homeHarness();
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'file-a',locale:'en',view:'history',focusKey:'a',tasks:[
    {key:'a',title:'Actual task',project:'Project',kind:'review',revision:'new',threadId:'t'}],history:[
    {taskKey:'a',revision:'old',time:'2026-11-10T00:00:00Z',operation:'download',status:'requested'}]});
  assert.equal(h.document.activeElement,h.elements['history-list'].querySelectorAll()[0]);
  assert.match(h.text(h.elements['history-list']),/Previous version/);
  assert.match(h.text(h.elements['history-list']),/JSON download requested/);
  h.elements['history-list'].querySelectorAll()[0].onclick();assert.equal(h.posts.at(-1).pluginMessage.key,'a');
  h.elements['workspace-locale'].onchange({target:{value:'ja'}});
  assert.match(h.text(h.elements['history-list']),/旧バージョンの記録/);
  assert.equal(h.posts.at(-1).pluginMessage.locale,'ja');
  h.elements['tab-codex'].onclick();assert.equal(h.elements['tab-codex'].attributes['aria-current'],'page');
  const chat=h.elements['task-list'].querySelectorAll()[0];
  assert.equal(chat.attributes['aria-label'],'Actual task をCodexに接続');
  chat.onclick();assert.equal(h.posts.at(-1).pluginMessage.type,'workspace-chat-open');
});

test('file-scoped history persists bounded sanitized events serially and restores valid locale',async()=>{
  const saved=new Map();let writing=0,maxWriting=0;
  const storage={async getAsync(key){return saved.get(key);},async setAsync(key,value){writing++;maxWriting=Math.max(maxWriting,writing);await Promise.resolve();saved.set(key,JSON.parse(JSON.stringify(value)));writing--;}};
  const h=harness(false,{storage});const session=await h.open('a');
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'draft-review',private:'NEVER STORE'}});
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'receipt',passed:true}});
  await h.send({type:'workspace-download',workspaceSession:session});
  let history=vm.runInContext('workspaceState.history',h.context);
  assert.deepEqual(Array.from(history,event=>event.status),['requested','readback','verified','requested']);
  assert.equal(history.at(-1).operation,'download');
  assert.equal(JSON.stringify(history).includes('PRIVATE'),false);
  for(let index=0;index<45;index++)await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'apply'}});
  assert.equal(vm.runInContext('workspaceState.history.length',h.context),80);
  await h.send({type:'workspace-history',workspaceSession:session});
  const list=await h.listing();assert.equal(list.view,'history');assert.equal(list.project,'Project A');assert.equal(list.focusKey,'a');
  await h.send({type:'workspace-locale',workspaceSession:list.workspaceSession,locale:'ja'});
  await h.send({type:'workspace-locale',workspaceSession:list.workspaceSession,locale:'xx'});
  await vm.runInContext('workspaceWrites',h.context);assert.equal(maxWriting,1);
  const stored=saved.get('figma-flow-workspace-v1:file-a');assert.equal(stored.locale,'ja');assert.equal(stored.history.length,80);
  assert.deepEqual(Object.keys(stored.history[0]).sort(),['operation','revision','status','taskKey','time']);
  const next=harness(false,{storage});const restored=await next.listing();assert.equal(restored.locale,'ja');assert.equal(restored.history.length,80);
  await next.open('b');assert.match(next.probe.shown.at(-1).html,/data-flow-locale="ja"/);
  const other=harness(false,{storage,fileKey:'file-b'});assert.equal((await other.listing()).history.length,0);
});
test('late storage loading cannot populate an expired home session or admit a forged verification',async()=>{
  let release;const storage={getAsync:()=>new Promise(resolve=>{release=resolve;}),async setAsync(){}};
  const h=harness(false,{storage});const pending=h.listing();
  vm.runInContext('workspaceHome()',h.context);release({locale:'en',history:[{taskKey:'a',revision:'r1',time:'2026-11-10',operation:'evil',status:'finished'}]});
  await pending;assert.equal(h.probe.messages.some(message=>message.type==='workspace-tasks'),false);
  const list=await h.listing();assert.equal(list.locale,'en');assert.equal(list.history.length,0);
  const session=await h.open('a');await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'receipt',passed:true}});
  assert.equal(vm.runInContext('workspaceState.history.length',h.context),0);
});

test('ignored import remains requested; actual native start is needed for finish; remote UI stays home',async()=>{
  const h=harness();const session=await h.open('a');
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'import'}});
  assert.deepEqual(Array.from(vm.runInContext('workspaceState.history',h.context),event=>event.status),['requested']);
  h.probe.emitBusyStart=true;
  await h.send({type:'workspace-task-message',workspaceSession:session,payload:{type:'import'}});
  assert.equal(vm.runInContext('workspaceState.history.at(-1).status',h.context),'finished');
  await h.send({type:'workspace-back',workspaceSession:session});
  const homeSession=(await h.listing()).workspaceSession;let ticks=0;
  h.context.workspaceControlTick=async()=>{ticks++;};
  await h.send({type:'workspace-control-tick',workspaceSession:'foreign',fileKey:'file-a'});
  assert.equal(ticks,0);
  await h.send({type:'workspace-control-tick',workspaceSession:homeSession,fileKey:'file-a'});assert.equal(ticks,1);
  const count=h.probe.shown.length;
  const remote=await vm.runInContext("workspaceOpen(FLOW_TASKS[0],'remote')",h.context);
  assert.equal(h.probe.shown.length,count);assert.ok(remote.html.includes('data-flow-locale'));
  const outputs=[];remote.onOutput=message=>outputs.push(message);
  const before=h.probe.messages.length;await remote.handler({type:'apply'});
  assert.equal(h.probe.messages.length,before);assert.ok(outputs.some(message=>message.readback));
  await h.send({type:'workspace-control-tick',workspaceSession:homeSession,fileKey:'file-a'});assert.equal(ticks,2);
});

test('workbench uses vetted project artwork, one primary next step, and admitted production phase before review',()=>{
  const h=homeHarness();
  const src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jnd0AAAAASUVORK5CYII=';
  const tasks=[
    {key:'review',title:'Compare actual candidates',project:'Studio',kind:'review',revision:'r1',preview:[{title:'Actual north',src},{title:'Actual south',src}]},
    {key:'production',title:'Import selected direction',project:'Studio',kind:'import',revision:'p1',productionAdmitted:true},
    {key:'paired',title:'Sync prepared app',project:'Studio',kind:'sync',revision:'s1',paired:true}];
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'f',locale:'en',history:[],tasks});
  assert.equal(h.elements['project-scope'].hidden,true);
  assert.equal(h.elements['project-preview'].children.length,2);
  assert.equal(h.elements['project-preview'].children[0].children[0].src,src);
  assert.equal(h.elements['project-preview'].children[0].children[0].alt,'Actual north');
  assert.equal(h.text(h.elements['task-list']).includes('Import selected direction'),false);
  const primary=h.elements['next-action'].querySelectorAll()[0];primary.onclick();assert.equal(h.posts.at(-1).pluginMessage.key,'production');
  assert.equal(h.elements['task-list'].querySelectorAll().some(button=>button.className==='primary'),false);
  assert.equal(h.elements['task-list'].querySelectorAll().length,2);
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'f',locale:'en',tasks,history:[
    {taskKey:'production',revision:'p1',operation:'import',status:'finished',time:'2026-11-10T00:00:00Z'}]});
  h.elements['next-action'].querySelectorAll()[0].onclick();assert.equal(h.posts.at(-1).pluginMessage.key,'paired');
  assert.equal(h.elements['recent-receipt'].hidden,false);
  assert.match(h.text(h.elements['recent-receipt']),/Operation finished/);
  tasks[0].preview=[{title:'unsafe',src:'https://foreign.example/image.png'}];
  tasks[1].productionAdmitted=false;
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'f',locale:'en',tasks,history:[]});
  assert.equal(h.elements['project-preview'].hidden,true);
  h.elements['next-action'].querySelectorAll()[0].onclick();assert.equal(h.posts.at(-1).pluginMessage.key,'review','pairing alone must not imply an approved later phase');
});

test('public workspace metadata forwards only bounded PNG previews and admitted booleans',async()=>{
  const h=harness();
  vm.runInContext(`FLOW_TASKS[0].preview=[{title:'Actual',src:'data:image/png;base64,iVBORw0KGgoAAA='},
    {title:'Foreign',src:'https://foreign.example/a.png'},{title:'SVG',src:'data:image/svg+xml,<svg/>'}];
    FLOW_TASKS[0].paired=true;FLOW_TASKS[0].productionAdmitted=true;FLOW_TASKS[0].handoff={secret:'NEVER SHOW'};`,h.context);
  const data=(await h.listing()).tasks[0];
  assert.equal(data.preview.length,1);assert.equal(data.preview[0].title,'Actual');
  assert.equal(data.paired,true);assert.equal(data.productionAdmitted,true);
  assert.equal(JSON.stringify(data).includes('NEVER SHOW'),false);
});

test('completed later phase recommends its actual receipt without reopening completed import',()=>{
  const h=homeHarness();
  const tasks=[
    {key:'review',title:'Compare directions',project:'Studio',kind:'review',revision:'r1'},
    {key:'production',title:'Selected production import',project:'Studio',kind:'import',revision:'p1',productionAdmitted:true},
    {key:'app',title:'Paired app result',project:'Studio',kind:'sync',revision:'s1',paired:true}];
  const history=[
    {taskKey:'production',revision:'p1',operation:'import',status:'finished',time:'2026-11-10T00:00:00Z'},
    {taskKey:'app',revision:'s1',operation:'sync',status:'finished',time:'2026-11-10T00:01:00Z'}];
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'f',locale:'en',tasks,history});
  assert.match(h.text(h.elements['next-action']),/Latest receipt/);
  assert.match(h.text(h.elements['next-action']),/Paired app result/);
  assert.equal(h.text(h.elements['next-action']).includes('Selected production import'),false);
  const primary=h.elements['next-action'].querySelectorAll()[0];assert.equal(primary.textContent,'View receipt');
  const before=h.posts.length;primary.onclick();assert.equal(h.posts.length,before,'receipt navigation must not dispatch a task');
  assert.equal(h.elements['tab-history'].attributes['aria-current'],'page');
  assert.match(h.text(h.elements['history-list']),/Operation finished/);
  assert.equal(h.document.activeElement,h.elements['history-list'].querySelectorAll()[0]);
  h.elements['history-list'].querySelectorAll()[0].onclick();assert.equal(h.posts.at(-1).pluginMessage.key,'app');
  const upstream=h.elements['history-list'].children.find(row=>h.text(row).includes('Selected production import'));
  upstream.querySelectorAll()[0].onclick();assert.equal(h.posts.at(-1).pluginMessage.key,'production','manual upstream route remains available');
  h.receive({type:'workspace-tasks',workspaceSession:'home',fileKey:'f',locale:'ja',tasks,history});
  assert.match(h.text(h.elements['next-action']),/直近の実行結果/);
  assert.equal(h.elements['next-action'].querySelectorAll()[0].textContent,'結果を見る');
  assert.match(home,/workspace.switchProject/);assert.match(home,/\.scope-filter select\{position:absolute/);
});

test('real React workspace compiles with shared components and Lucide and preserves result-first policy',()=>{
  const {createRequire}=require('node:module');
  const {spawnSync}=require('node:child_process');
  const panelRoot=path.join(__dirname,'../panel-ui');
  const panelRequire=createRequire(path.join(panelRoot,'package.json'));
  const {buildSync}=panelRequire('esbuild');
  const entry=`
import assert from 'node:assert/strict';
import fs from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Workspace,{selectRecommendation,workspacePreviews} from './src/Workspace.jsx';
import {Shell,PanelContext} from './src/components.jsx';
globalThis.window={};
const dictionary=JSON.parse(fs.readFileSync('../figma-bridge/locales/workspace.json','utf8'));
const translate=(locale)=>(key,params={})=>{let text=dictionary[key]?.[locale]||key;for(const [name,value]of Object.entries(params))text=text.replace('{'+name+'}',value);return text;};
const tasks=[
 {key:'review',title:'Actual review',project:'Studio',kind:'review',revision:'r1'},
 {key:'import',title:'Actual selected import',project:'Studio',kind:'import',revision:'i1',productionAdmitted:true},
 {key:'sync',title:'Actual paired app',project:'Studio',kind:'sync',revision:'s1',paired:true,threadId:'thread'}];
const model={tasks,fileKey:'f',history:[
 {taskKey:'import',revision:'i1',operation:'import',status:'finished',time:'2026-11-10T00:00:00Z'},
 {taskKey:'sync',revision:'s1',operation:'sync',status:'finished',time:'2026-11-10T00:01:00Z'}]};
assert.equal(selectRecommendation(model,tasks).task.key,'sync');
assert.equal(selectRecommendation(model,tasks).inspect,true);
assert.equal(workspacePreviews({preview:[{title:'foreign',src:'https://foreign.example/image.png'}]}).length,0);
function render(locale){const t=translate(locale);return renderToStaticMarkup(<PanelContext.Provider value={{locale,t,setLocale(){},hostBusy:false}}><Workspace model={model} locale={locale} t={t} send={()=>{throw Error('render must not dispatch');}} Shell={Shell}/></PanelContext.Provider>);}
const en=render('en');assert(en.includes('View receipt'));assert(en.includes('Actual paired app'));assert(en.includes('<svg'));assert(!en.includes('<style'));
assert.equal((en.match(/panel-action primary/g)||[]).length,1);
assert(render('ja').includes('結果を見る'));assert(render('ko').includes('결과 보기'));
const laterProject={key:'other',title:'Other admitted project',project:'Other',kind:'import',revision:'o1',productionAdmitted:true};
assert.equal(selectRecommendation({...model,tasks:[...tasks,laterProject]},[...tasks,laterProject]).task.key,'other','later phase in another project must not hide this project pending work');
console.log('Compiled React workspace/shared components/Lucide,3 locales and phase/result policy verified.');
`;
  const built=buildSync({stdin:{contents:entry,resolveDir:panelRoot,loader:'jsx'},absWorkingDir:panelRoot,
    bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',define:{'process.env.NODE_ENV':'"production"'},logLevel:'silent'});
  const run=spawnSync(process.execPath,['-e',built.outputFiles[0].text],{cwd:panelRoot,encoding:'utf8'});
  assert.equal(run.status,0,run.stdout+run.stderr);
  assert.match(run.stdout,/Compiled React workspace/);
});

test('every prepared scoped native edit registers in the actual host', async()=>{
  const h=harness(false,{kind:'native-edit'});
  const listed=await h.listing();
  assert(listed.tasks.some(task=>task.key==='a'&&task.kind==='native-edit'));
});
