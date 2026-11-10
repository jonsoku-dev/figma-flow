const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const host = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_host.js'), 'utf8');
const home = fs.readFileSync(path.join(__dirname, '../figma-bridge/workspace_home.html'), 'utf8');
function harness(frozen = false) {
  const messages = [], shown = [], writes = [], commands = [], proxies = [];
  const probe = {messages, shown, writes, commands, proxies, pending: null, closeCount: 0, chatCalls: []};
  const figma = {
    fileKey: 'file-a', ui: {postMessage(message) {assert.equal(this, figma.ui); messages.push(message);}},
    showUI(html, options) {assert.equal(this, figma); shown.push({html, options});},
    createPage() {assert.equal(this, figma); writes.push('page');}
  };
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
    if(message.type==='read') {if(probe.pending)await probe.pending;figma.createPage();}
    figma.ui.postMessage({type:'result',value:message.type});
  };
}
const FLOW_TASKS = [
 {key:'a',title:'Import A',project:'Project A',kind:'import',fileKey:'file-a',pageId:'1:2',threadId:'thread-a',run:runTask},
 {key:'b',title:'Review B',project:'Project B',kind:'review',fileKey:null,threadId:'thread-b',run:runTask},
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

test('task HTML relay wraps outgoing schemas and rejects old inbound sessions', async () => {
  const h = harness(); const session = await h.open('a');
  const noHead = vm.runInContext("workspaceTaskHtml('<!doctype html><html lang=ko><meta charset=utf-8><body>panel</body></html>')",h.context);
  assert.match(noHead,/^<!doctype html><html lang=ko><script>/);
  const relay = h.probe.shown.at(-1).html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const posted = [], listeners = {};
  const node = () => ({style:{},children:[],setAttribute(){},appendChild(child){this.children.push(child);}});
  const document = {body:{prepend(bar){this.bar=bar;}},querySelector:()=>null,createElement:node,getElementById(id){return this.body.bar?.children.find(child=>child.id===id);}};
  const window = {parent:{postMessage:message=>posted.push(message)},addEventListener(type,fn){listeners[type]=fn;}};
  const context = vm.createContext({window,document}); vm.runInContext(relay,context);
  vm.runInContext('parent.postMessage({pluginMessage:{type:"receipt",passed:true}},"*");',context);
  assert.equal(posted[0].pluginMessage.workspaceSession, session);
  assert.equal(posted[0].pluginMessage.payload.type, 'receipt');
  const incoming = {data:{pluginMessage:{workspaceSession:session,payload:{type:'result'}}},stopImmediatePropagation(){this.stopped=true;}};
  listeners.message(incoming); assert.equal(incoming.data.pluginMessage.type,'result');
  const old = {data:{pluginMessage:{workspaceSession:'old',payload:{type:'result'}}},stopImmediatePropagation(){this.stopped=true;}};
  listeners.message(old); assert.equal(old.stopped,true);
  listeners.DOMContentLoaded();
  assert.equal(posted.at(-1).pluginMessage.type,'workspace-navigation-ready');
  assert.match(document.body.bar.style.cssText,/flex-wrap:wrap/);
  assert.equal(document.getElementById('workspace-back').textContent,'작업 목록으로');
  assert.equal(document.getElementById('workspace-chat').textContent,'Codex 연결');
  listeners.message({data:{pluginMessage:{workspaceSession:session,workspaceControl:true,busy:true}},stopImmediatePropagation(){}});
  assert.equal(document.getElementById('workspace-back').disabled,true);
  assert.equal(document.getElementById('workspace-chat').disabled,true);
  const headListeners = {}, headPosted = [];
  const masthead = node(), contextLabel = node();contextLabel.textContent='그래프 동기화';
  const brand = {replaceWith(bar){masthead.controls=bar;}};
  masthead.querySelector=selector=>selector==='.brand'?brand:selector==='.context'?contextLabel:null;
  const headDocument = {body:{prepend(){assert.fail('existing masthead must not get an extra navigation row');}},
    querySelector:selector=>selector==='.masthead'?masthead:null,createElement:node,
    getElementById:id=>masthead.controls?.children.find(child=>child.id===id)};
  const headWindow = {parent:{postMessage:message=>headPosted.push(message)},addEventListener(type,fn){headListeners[type]=fn;}};
  vm.runInNewContext(relay,{window:headWindow,document:headDocument});
  headListeners.DOMContentLoaded();
  assert.equal(masthead.controls.children.length,2);
  assert.equal(contextLabel.textContent,'그래프 동기화');
  assert.equal(contextLabel.style.flex,'1 1 70px');
  assert.equal(masthead.style.flexWrap,'wrap');
  assert.equal(masthead.controls.style.cssText.includes('border-bottom'),false);
  const back=headDocument.getElementById('workspace-back'), chat=headDocument.getElementById('workspace-chat');
  assert.equal(back.type,'button');assert.equal(chat.type,'button');
  back.onclick();assert.equal(headPosted.at(-1).pluginMessage.type,'workspace-back');
  chat.onclick();assert.equal(headPosted.at(-1).pluginMessage.type,'workspace-chat');
  headListeners.message({data:{pluginMessage:{workspaceSession:session,workspaceControl:true,busy:true}},stopImmediatePropagation(){}});
  assert.equal(back.disabled,true);assert.equal(chat.disabled,true);
  headListeners.message({data:{pluginMessage:{workspaceSession:session,workspaceControl:true,busy:false}},stopImmediatePropagation(){}});
  assert.equal(back.disabled,false);assert.equal(chat.disabled,false);
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
test('home groups real names safely, disables wrong files, and supports keyboard navigation and empty state', () => {
  const posts=[], document={activeElement:null};
  const ids=['task-list','home-status','home-status-title','home-status-body'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element('div',document)]));
  document.getElementById=id=>elements[id]; document.createElement=tag=>new Element(tag,document);
  const window={}; const context=vm.createContext({window,document,parent:{postMessage:m=>posts.push(m)}});
  vm.runInContext(home.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  window.onmessage({data:{pluginMessage:{type:'workspace-tasks',workspaceSession:'home',fileKey:'file-a',tasks:[
    {key:'a',title:'<script>hostile</script>',project:'Actual project',kind:'review',threadId:'t',fileKey:'file-a',pageId:'1:2'},
    {key:'b',title:'Other',project:'Actual project',kind:'sync',fileKey:'file-b'},
    {key:'c',title:'Read',project:'Second project',kind:'discover',threadId:'t'}]}}});
  assert.equal(elements['task-list'].children.length,2);
  assert.equal(elements['task-list'].children[0].children[1].children[0].children[1].textContent,'<script>hostile</script>');
  const firstScope = elements['task-list'].children[0].children[1].children[0].children[2];
  assert.equal(firstScope.textContent,'현재 파일 · 지정 페이지');
  assert.equal(firstScope.title,'파일 file-a / 페이지 1:2');
  const foreignRow = elements['task-list'].children[0].children[2];
  assert.equal(foreignRow.children[0].children[2].textContent,'다른 파일에서 실행');
  assert.equal(foreignRow.children[0].children[2].title,'파일 file-b');
  assert.equal(foreignRow.children[1].children[0].disabled,true);
  const visible = element => (element.textContent || '') + element.children.map(visible).join(' ');
  assert.equal(visible(elements['task-list']).includes('file-a'),false);
  assert.equal(visible(elements['task-list']).includes('file-b'),false);
  assert.equal(visible(elements['task-list']).includes('1:2'),false);
  const buttons=elements['task-list'].querySelectorAll(); assert.equal(buttons.length,4);
  assert.equal(buttons[0].className,'primary');
  assert.equal(buttons[1].className,'secondary');
  assert.match(home,/flex-wrap:nowrap/);
  assert.equal(home.includes('작업을 열어 내용을 확인하세요.'),false);
  buttons[0].onclick(); assert.equal(posts.at(-1).pluginMessage.key,'a');
  buttons[0].focus(); elements['task-list'].keydown({key:'End',preventDefault(){}});
  assert.equal(document.activeElement,buttons.at(-1));
  window.onmessage({data:{pluginMessage:{type:'workspace-tasks',workspaceSession:'home',tasks:[]}}});
  assert.equal(elements['home-status'].hidden,false);
  assert.equal(elements['home-status-title'].textContent,'준비된 작업이 없습니다');
});
