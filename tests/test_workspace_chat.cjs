const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'figma-bridge/workspace_chat.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'figma-bridge/workspace_chat.html'), 'utf8');
const ctx = vm.createContext({setTimeout, clearTimeout, URL});
vm.runInContext(source + '\nthis.Chat = WorkspaceChat;', ctx);
const Chat = ctx.Chat;
const id = '12345678-1234-4234-8234-123456789abc';
const secondId = '22345678-1234-4234-8234-123456789abc';
const task = {key:'review-a', title:'<img src=x onerror=alert(1)>', revision:'a'.repeat(64), threadId:id, fileKey:'fileKey', pageId:'1:2'};
const node = () => Object.defineProperty({id:'3:4',type:'TEXT',name:'<script>evil()</script> a@example.com',x:1.125,y:-2,width:100,height:40,
  characters:'Private text a@example.com'},'children',{get() {throw Error('No child traversal');}});
const figma = () => ({fileKey:'fileKey',currentPage:{id:'1:2',name:'Page',selection:[]},openExternal:url=>opened.push(url)});
let opened = [];
async function main() {
  const f = figma();
  assert.equal(Chat.collect(f,task).nodes.length,0);
  f.currentPage.selection = [node()];
  Object.defineProperty(f.currentPage.selection[0], 'characters', {get() {throw Error('Text was not opted in');}});
  const selection = Chat.collect(f,task);
  assert.equal(selection.nodes[0].textExcerpt,undefined);
  assert.equal(selection.nodes[0].x,1.13);
  assert.equal(selection.nodes[0].name.includes('@'),false);
  assert.equal(selection.link,'https://www.figma.com/design/fileKey?node-id=3-4');
  f.currentPage.selection = [node()];
  assert.equal(Chat.collect(f,task,true).nodes[0].textExcerpt.includes('@'),false);
  assert.equal(Chat.collect(f,task,true,false).nodes.length,0);
  f.currentPage.selection = Array.from({length:21},node);
  assert.throws(()=>Chat.collect(f,task),/20/);
  f.currentPage.selection = [node(),{...node(),type:'PAGE'}];
  assert.throws(()=>Chat.collect(f,task),/지원하지/);
  f.currentPage.selection = [{...node(),width:Infinity}];
  assert.throws(()=>Chat.collect(f,task),/크기/);
  f.currentPage.selection = Array.from({length:20},()=>({...node(),characters:'a'.repeat(400)}));
  const texts = Chat.collect(f,task,true).nodes.map(n=>n.textExcerpt || '');
  assert.equal(texts.reduce((n,s)=>n+s.length,0),1000);
  assert.ok(texts.every(s=>s.length<=200));
  assert.throws(()=>Chat.threadUrl('https://evil.test/?text=secret'));
  assert.equal(Chat.threadUrl(id),'codex://threads/'+id);
  assert.throws(()=>Chat.preview(task,'',{nodes:[]}));
  assert.ok(Chat.preview(task,'',selection).includes('선택한 Figma'));
  assert.throws(()=>Chat.preview(task,'x'.repeat(4001),selection));

  f.currentPage.selection = [node()];
  let active = true, shown = '', posts = [], requests = [];
  const relay = {url:'http://localhost:4337',token:'b'.repeat(64)};
  const options = {isCurrent:()=>active,session:'session',uiHtml:html,showUI:value=>shown=value,
    postMessage:value=>posts.push(value),onBack:()=>{},relay,fetch:async(url,request)=>{
      requests.push({url,request});return {ok:true,json:async()=>({status:url.endsWith('/queue')?'queued':'opened'})};}};
  const controller = Chat.open(f,task,options);
  assert.equal(shown.includes(relay.token),false,'Capability must remain in trusted host');
  assert.equal(shown.includes('<img src=x'),false,'Task metadata must not break out of script');
  await controller.handle({type:'chat:queue',requestId:id});
  assert.equal(requests.length,0,'Queue requires reviewed preview');
  await controller.handle({type:'chat:prepare',requestId:id,message:'이 선택을 바꿔 주세요',includeSelection:true,includeText:false});
  const prepared = posts.find(p=>p.type==='chat:preview');
  assert.ok(prepared.text.includes('<script>evil()</script>'),'Untrusted names remain data');
  assert.equal(prepared.text.includes('Private text'),false);
  await controller.handle({type:'chat:queue',requestId:id,text:'tampered',key:'evil',threadId:secondId});
  assert.equal(requests.length,1);
  const body = JSON.parse(requests[0].request.body);
  assert.equal(body.text,prepared.text,'Queued text is exactly host-owned preview');
  assert.equal(body.key,task.key);assert.equal(body.threadId,id);assert.equal(body.revision,task.revision);
  assert.equal(requests[0].url,'http://localhost:4337/chat/queue');
  assert.equal(requests[0].request.headers.Authorization,'Bearer '+relay.token);
  assert.equal(requests[0].url.includes('선택'),false);
  assert.ok(posts.some(p=>p.status==='queued'));
  await controller.handle({type:'chat:queue',requestId:id});
  assert.equal(requests.length,1,'Repeated click must not resend');
  active = false;
  await controller.handle({type:'chat:open',requestId:secondId});
  assert.equal(requests.length,1,'Old task session must not send');
  active = true;f.fileKey='wrong';
  await controller.handle({type:'chat:open',requestId:secondId});
  assert.equal(requests.length,1,'Wrong file must not send');
  f.fileKey='fileKey';f.currentPage.id='9:9';
  await controller.handle({type:'chat:open',requestId:secondId});
  assert.equal(requests.length,1,'Wrong page must not send');
  f.currentPage.id='1:2';
  await controller.handle({type:'chat:open-fallback',threadId:secondId});
  assert.deepEqual(opened,['codex://threads/'+id]);
  controller.close();
  await controller.handle({type:'chat:open',requestId:secondId});assert.equal(requests.length,1);

  let complete;
  const concurrent = Chat.open(f,task,{...options,fetch:()=>new Promise(resolve=>{complete=resolve;})});
  const pending = concurrent.handle({type:'chat:open',requestId:secondId});
  await concurrent.handle({type:'chat:open',requestId:secondId});
  complete({ok:true,json:async()=>({status:'opened'})});await pending;
  const unpaired = Chat.open(f,{...task,threadId:null},{...options,relay:null});
  await unpaired.handle({type:'chat:open',requestId:secondId});
  assert.equal(requests.length,1);
  assert.ok(posts.some(p=>p.type==='chat:error' && p.message.includes('복사')));
  assert.ok(html.includes('document.execCommand(\'copy\')'));
  assert.ok(html.includes("el('preview').select()"));
  assert.ok(html.includes('textContent'));
  assert.equal(html.includes('innerHTML'),false);
  assert.equal(html.includes('fetch('),false,'Untrusted iframe must not hold relay access');
  assert.ok(html.includes('아직 에이전트가 읽거나 실행했다는 뜻은 아닙니다'));
  const elements = new Map(), uiMessages = [], listeners = new Map();
  const element = key => {
    if (!elements.has(key)) elements.set(key,{value:'',checked:key==='include-selection',disabled:false,textContent:'',
      addEventListener(type,handler){this[type]=handler;},focus(){},select(){this.selected=true;}});
    return elements.get(key);
  };
  const ui = vm.createContext({document:{getElementById:element,execCommand:()=>false},
    parent:{postMessage:m=>uiMessages.push(m.pluginMessage)},crypto:{randomUUID:()=>id},
    window:{addEventListener:(type,handler)=>listeners.set(type,handler)}});
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1].replace('/* WORKSPACE_CHAT_CONTEXT */',JSON.stringify({title:task.title,threadId:id,paired:true})),ui);
  assert.equal(uiMessages.length,0,'Opening chat never collects or sends automatically');
  assert.equal(element('task-title').textContent,task.title);
  assert.equal(element('thread-destination').textContent,id);
  element('request').value='Please review';element('prepare').onclick();
  assert.equal(uiMessages.at(-1).type,'chat:prepare');
  listeners.get('message')({data:{pluginMessage:{type:'chat:preview',requestId:id,text:'exact preview',count:0}}});
  assert.equal(element('preview').value,'exact preview');
  element('copy').onclick();assert.equal(element('preview').selected,true);
  assert.ok(element('status-title').textContent.includes('복사해'));
  element('send').onclick();element('send').onclick();
  assert.equal(uiMessages.filter(m=>m.type==='chat:queue').length,1);
  assert.equal(uiMessages.at(-1).requestId,id);
  element('request').input();
  listeners.get('message')({data:{pluginMessage:{type:'chat:preview',requestId:id,text:'stale preview',count:0}}});
  assert.equal(element('preview').value,'','Edited input invalidates late preview');
  assert.equal(element('send').disabled,true);
  function checkRng(cryptoValue) {
    const nodes = new Map(), sent = [];
    const get = key => {
      if (!nodes.has(key)) nodes.set(key,{value:'',checked:true,disabled:false,textContent:'',addEventListener(){}});
      return nodes.get(key);
    };
    const sandbox = vm.createContext({crypto:cryptoValue,document:{getElementById:get},parent:{postMessage:m=>sent.push(m.pluginMessage)},window:{addEventListener(){}}});
    vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1].replace('/* WORKSPACE_CHAT_CONTEXT */',JSON.stringify({title:'Task',threadId:id,paired:true})),sandbox);
    get('request').value='Figma Flow 통합 패널 연결 점검';get('prepare').onclick();
    return {sent,get};
  }
  const opaque = checkRng({getRandomValues:bytes=>{bytes.fill(23);return bytes;}});
  assert.equal(opaque.sent[0].type,'chat:prepare');
  assert.match(opaque.sent[0].requestId,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  const denied = checkRng(undefined);
  assert.equal(denied.sent.length,0);
  assert.ok(denied.get('status-body').textContent.includes('보안 난수'));
  console.log('workspace chat: selection privacy, bounds, exact preview, scope/session pins, replay and clipboard checks passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
