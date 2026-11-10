'use strict';
// Deterministic DOM/IndexedDB contract doubles. Real layout and trusted keyboard events require a browser.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/app.js'), 'utf8');
function database() {
  const records = []; let failure = false;
  return {records, fail(value) { failure = value; }, open() {
    const request = {};
    queueMicrotask(() => {
      request.result = {close() {}, transaction(_name, mode) {
        const tx = {objectStore() { return {
          getAll() { return execute(() => records.map(r => ({...r}))); },
          add(record) { return execute(() => { records.push({...record, id: records.length + 1}); return records.length; }); }
        }; }};
        function execute(operation) {
          const result = {};
          queueMicrotask(() => {
            if (failure) { tx.error = new Error('storage unavailable'); tx.onabort(); return; }
            result.result = operation(); result.onsuccess(); tx.oncomplete();
          }); return result;
        }
        return tx;
      }}; request.onsuccess();
    }); return request;
  }};
}
async function app(db = database(), channels = []) {
  let focused; const elements = new Map(); const windowEvents = {};
  function element(id = '') {
    return {id, value:'', hidden:false, disabled:false, textContent:'', children:[], attributes:{}, events:{},
      addEventListener(name, handler) { this.events[name] = handler; },
      setAttribute(name, value) { this.attributes[name] = value; }, removeAttribute(name) { delete this.attributes[name]; },
      focus() { if (!this.disabled) focused = id; }, append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      reset() { get('title').value = get('content').value = ''; }
    };
  }
  const get = id => { if (!elements.has(id)) elements.set(id, element(id)); return elements.get(id); };
  class Channel {
    constructor() { channels.push(this); }
    postMessage(data) { for (const other of channels) if (other !== this) other.onmessage?.({data}); }
  }
  const context = vm.createContext({document:{getElementById:get, createElement:element}, indexedDB:db,
    window:{addEventListener(name, handler) { windowEvents[name] = handler; }}, BroadcastChannel:Channel, Intl, Date});
  vm.runInContext(source, context);
  const settle = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };
  await settle();
  return {db, get, context, settle, windowEvents, focused:() => focused,
    async event(id, name = 'click') { await get(id).events[name]({preventDefault(){}}); await settle(); },
    text() { function flat(node) { return node.textContent + node.children.map(flat).join(' '); } return flat(get('ideas')); },
    async save(title, content = '') { await this.event('add'); get('title').value = title; get('content').value = content; await this.event('idea-form', 'submit'); }
  };
}
test('TEST-001 fresh store and empty-store search have distinct messages', async () => {
  const a = await app(); assert.match(a.text(), /아직 모아둔/);
  a.get('search').value = 'unknown'; await a.event('search','input'); assert.match(a.text(), /검색 결과가 없어요/);
});
test('TEST-002 blank title, length boundaries and defensive overlength validation preserve input', async () => {
  const a = await app(); await a.save('  '); assert.equal(a.db.records.length, 0); assert.equal(a.focused(), 'title');
  assert.equal(a.get('title').attributes['aria-invalid'], 'true');
  assert.equal(a.get('title').attributes['aria-describedby'], 'title-hint title-error');
  a.get('title').value='corrected'; await a.event('title','input');
  assert.equal(a.get('title-error').hidden,true); assert.equal(a.get('title').attributes['aria-describedby'],'title-hint');
  await a.save('x'.repeat(61)); assert.equal(a.db.records.length,0); assert.match(a.get('title-error').textContent,/60/);
  await a.save('x', 'y'.repeat(501)); assert.equal(a.db.records.length,0); assert.equal(a.focused(),'content');
  assert.equal(a.get('content').attributes['aria-describedby'],'content-hint content-error');
  a.get('content').value='corrected'; await a.event('content','input');
  assert.equal(a.get('content-error').hidden,true); assert.equal(a.get('content').attributes['aria-describedby'],'content-hint');
  await a.save('x'.repeat(60),'y'.repeat(500)); assert.equal(a.db.records.length,1); assert.equal(a.get('form-screen').hidden,true);
  assert.equal(a.focused(),'add'); assert.equal(a.get('save').disabled,false);
  assert.equal(a.get('title').attributes['aria-describedby'],'title-hint');
  assert.equal(a.get('content').attributes['aria-describedby'],'content-hint');
});
test('TEST-003 persistence, literal text rendering and case-insensitive title/content search', async () => {
  const a = await app(); await a.save('<script>Alpha</script>','Beta notes');
  const b = await app(a.db); assert.match(b.text(),/<script>Alpha/); assert.match(b.text(),/Beta notes/);
  b.get('search').value='ALPHA'; await b.event('search','input'); assert.match(b.text(),/Beta notes/);
  b.get('search').value='BETA'; await b.event('search','input'); assert.match(b.text(),/Alpha/);
  b.get('search').value='missing'; await b.event('search','input'); assert.match(b.text(),/검색 결과가 없어요/);
});
test('TEST-004 cancel/back discard draft; native submit path focuses new title and restored add button', async () => {
  const a = await app(); await a.event('add'); assert.equal(a.focused(),'title');
  a.get('title').value='discard'; await a.event('cancel'); assert.equal(a.db.records.length,0); assert.equal(a.get('title').value,'');
  await a.event('add'); a.get('title').value='discard too'; await a.event('back'); assert.equal(a.db.records.length,0); assert.equal(a.focused(),'add');
});
test('TEST-005 failed write preserves draft and explicit retry succeeds; read retry recovers', async () => {
  const a = await app(); a.db.fail(true); await a.save('Keep me','Keep content');
  assert.equal(a.db.records.length,0); assert.equal(a.get('title').value,'Keep me'); assert.equal(a.get('content').value,'Keep content');
  assert.equal(a.get('save-error').hidden,false); assert.equal(a.get('save').disabled,false);
  a.db.fail(false); await a.event('idea-form','submit'); assert.equal(a.db.records.length,1);
  a.db.fail(true); await a.context.refresh(); assert.equal(a.get('retry').hidden,false);
  a.db.fail(false); await a.event('retry'); assert.equal(a.get('list-error').hidden,true); assert.equal(a.get('retry').hidden,true);
});
test('TEST-006 two tabs append independently and refresh without losing an open draft', async () => {
  const db = database(), channels=[]; const a = await app(db, channels), b = await app(db, channels);
  await b.event('add'); b.get('title').value='Draft'; await a.save('First'); await b.settle();
  assert.equal(b.get('title').value,'Draft'); assert.equal(b.get('form-screen').hidden,false); assert.match(b.text(),/First/);
  await b.event('idea-form','submit'); await a.settle(); assert.equal(db.records.length,2); assert.match(a.text(),/Draft/);
  await a.windowEvents.focus(); assert.equal(a.get('count').textContent,2);
});
test('TEST-007 HTML supplies labels, limits, native keyboard controls, error relationships and responsive CSS', () => {
  const html=fs.readFileSync(path.join(__dirname,'../app/index.html'),'utf8');
  for (const id of ['search','title','content']) assert.match(html,new RegExp(`for="${id}"`));
  assert.match(html,/id="title" maxlength="60"/); assert.match(html,/maxlength="500"/);
  assert.match(html,/type="submit"/); assert.match(html,/aria-describedby="content-hint"/);
  assert.match(html,/aria-describedby="title-hint"/); assert.doesNotMatch(html,/aria-describedby="[^"]*-error/);
  assert.match(html,/<link rel="icon" href="data:image\/svg\+xml,/);
  const css=fs.readFileSync(path.join(__dirname,'../app/style.css'),'utf8'); assert.match(css,/:focus-visible/); assert.match(css,/@media\(max-width:600px\)/);
});
