const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const policy = JSON.parse(read('library/figma-profile/policy.json'));
const env = vm.createContext({});
vm.runInContext(read('figma-bridge/profile_policy.js') + '\n' + read('figma-bridge/workspace_profile.js'), env);

function fixture() {
  const store = new Map();
  const api = {currentUser:{id:'member-A',name:'A',photoUrl:'unused'}, root:{name:'File'}, fileKey:'file-A',
    currentPage:{id:'page-A',name:'Page'},editorType:'figma',mode:'default',pluginId:'123',apiVersion:'1.0.0',
    clientStorage:{getAsync:async k => store.get(k), setAsync:async (k,v) => {store.set(k,v);}}};
  const open = () => env.createWorkspaceProfile(api,policy,{version:'test'});
  return {api,store,open};
}

test('first launch observes metadata and separate declarations survive reopening on the same client',async () => {
  const {api,store,open} = fixture();
  const profile=open();
  const first=await profile.load('ko');
  assert.equal(first.needsSetup,true);
  assert.equal(first.context.userName,'A');
  assert.equal(first.context.fileName,'File');
  assert.equal(first.source.seat,'unknown');
  assert.ok(profile.allowsOperation('read'));
  assert.equal(profile.allowsOperation('apply'),false);
  const saved=await profile.save({plan:'starter',seat:'unknown'},'ko');
  assert.equal(saved.needsSetup,false);
  assert.equal(saved.source.plan,'user');
  assert.equal(saved.capabilities.designEdit,true);
  assert.equal(saved.capabilities.devInspect,false);
  const next=open();
  assert.equal((await next.load('en')).declared.plan,'starter');
  api.currentPage={id:'page-B',name:'Another page'};
  assert.equal((await next.load('en')).context.pageId,'page-B');
  assert.equal(store.size,2);
  assert.ok(!JSON.stringify([...store.values()]).includes('unused'));
  api.fileKey='file-B';
  assert.equal((await next.load('ko')).needsSetup,true);
  api.fileKey='file-A'; api.currentUser={id:'member-B',name:'B'};
  assert.equal((await next.load('ko')).needsSetup,true);
});

test('declared plan and seat can restrict or suggest, only the observed Inspect surface enables inspection',async () => {
  const {api,open} = fixture(); const profile=open(); await profile.load('ko');
  for (const plan of policy.options.plans) {
    for (const seat of policy.options.seats) {
      const {capabilities}=await profile.save({plan,seat},'ko');
      assert.equal(capabilities.devInspect,false);
      assert.equal(capabilities.designEdit,seat==='full'||seat==='unknown');
      assert.equal(capabilities.devHandoff,!['unknown','starter'].includes(plan)&&['dev','full'].includes(seat));
      for (const operation of ['draft-review','workspace-recipe-run','create','apply','sync','import'])
        assert.equal(profile.allowsOperation(operation),capabilities.designEdit);
    }
  }
  api.editorType='dev';api.mode='inspect';
  const {capabilities}=await profile.load('ko');
  assert.equal(capabilities.devInspect,true);assert.equal(capabilities.designEdit,false);
  api.editorType='figma';api.mode='default';api.currentUser={id:'switched',name:'B'};
  assert.equal(profile.allowsOperation('apply'),false);
  await assert.rejects(profile.save({plan:'professional',seat:'full'},'ko'),/current Figma user/);
  await assert.rejects(profile.save({plan:'invented',seat:'full'},'ko'),/listed/);
});

test('missing identity or unavailable client storage leaves a usable session',async () => {
  const {api,store,open}=fixture();
  const profile=open();
  await profile.load('ko');await profile.save({plan:'professional',seat:'full'},'ko');
  api.clientStorage.setAsync=async()=>{throw Error('storage unavailable');};
  const fallback=await profile.save({plan:'professional',seat:'view'},'ko');
  assert.equal(fallback.storage,'session');
  assert.equal((await profile.load('ko')).declared.seat,'view');
  assert.equal(profile.allowsOperation('apply'),false);
  api.currentUser=null;
  assert.equal((await profile.load('ko')).needsSetup,true);
  assert.equal((await profile.save({plan:'unknown',seat:'unknown'},'ko')).storage,'session');
  assert.equal(store.size,2);
});

test('every capability edge and action resolves to a declared node in the canonical graph',()=>{
  for (const options of Object.values(policy.capabilities)) {
    assert.ok(options.length);
    for (const parents of options) {
      assert.ok(parents.length);
      for (const id of parents) assert.ok(Object.hasOwn(policy.facts,id),id);
    }
  }
  for (const op of policy.passthrough) assert.ok(!Object.hasOwn(policy.operations,op),op);
  for (const cap of policy.refreshBeforeDispatch) assert.ok(Object.hasOwn(policy.capabilities,cap),cap);
  for (const cap of Object.values(policy.operations)) assert.ok(Object.hasOwn(policy.capabilities,cap),cap);
});

test('pending initialization cannot write the observed profile into a changed account scope',async () => {
  const {api,store,open}=fixture();
  let unblock;
  api.clientStorage.getAsync=()=>new Promise(resolve=>{unblock=resolve;});
  const loading=open().load('ko');
  await Promise.resolve();
  api.currentUser={id:'other-user',name:'Other'};
  unblock(undefined);
  await assert.rejects(loading,/scope changed/);
  assert.equal(store.size,0);
});

test('every declared plan and seat has a translated settings label',()=>{
  const locale=JSON.parse(read('figma-bridge/locales/workspace.json'));
  for (const [group,codes] of [['plan',policy.options.plans],['seat',policy.options.seats]]) {
    for (const code of codes) {
      const label=locale['workspace.profile.'+group+'.'+code];
      for (const language of ['ko','en','ja']) assert.ok(label?.[language],group+' '+code+' '+language);
    }
  }
});

test('a second window restricting authoring takes effect at the next write dispatch',async()=>{
  const {open}=fixture();const first=open(),second=open();
  await first.load('ko');await first.save({plan:'professional',seat:'full'},'ko');
  await second.load('ko');await second.save({plan:'professional',seat:'dev'},'ko');
  assert.equal(await first.admitOperation('apply'),false);
  assert.equal(await first.admitOperation('read'),true);
});

test('first launch can resolve a late user without storing the declaration under an anonymous key',async()=>{
  const {api,store}=fixture();
  const user=api.currentUser;api.currentUser=null;
  const context=vm.createContext({setTimeout(done){queueMicrotask(()=>{api.currentUser=user;done();});}});
  vm.runInContext(read('figma-bridge/profile_policy.js')+'\n'+read('figma-bridge/workspace_profile.js'),context);
  const profile=context.createWorkspaceProfile(api,policy,{version:'fixture'});
  const loaded=await profile.load('ko');
  assert.equal(loaded.context.userId,user.id);
  assert.equal(loaded.storage,'local');
  await profile.save({plan:'unknown',seat:'unknown'},'ko');
  assert.ok([...store.keys()].every(key=>key.includes(user.id)));
});
