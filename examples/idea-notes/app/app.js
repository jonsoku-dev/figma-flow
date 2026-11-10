'use strict';
const $ = id => document.getElementById(id);
const list = $('list-screen'), formScreen = $('form-screen'), title = $('title'), content = $('content');
let db;
function openStore() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('moeum-ideas', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('ideas', {keyPath: 'id', autoIncrement: true});
    request.onsuccess = () => {
      const connection = request.result;
      connection.onversionchange = () => { connection.close(); if (db === connection) db = undefined; };
      resolve(connection);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('저장소가 다른 탭에서 사용 중입니다.'));
  });
}
async function store(mode, operation) {
  db ||= await openStore();
  return new Promise((resolve, reject) => {
    let result;
    try {
      const tx = db.transaction('ideas', mode);
      const request = operation(tx.objectStore('ideas'));
      request.onsuccess = () => { result = request.result; };
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error('transaction aborted'));
    } catch (error) { reject(error); }
  });
}
let ideas = [];
function render() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const shown = ideas.filter(idea => `${idea.title}\n${idea.content}`.toLocaleLowerCase().includes(query));
  $('count').textContent = ideas.length;
  const container = $('ideas');
  container.replaceChildren();
  if (!shown.length) {
    const empty = document.createElement('div'); empty.className = 'empty';
    const heading = document.createElement('strong');
    heading.textContent = query ? '검색 결과가 없어요' : '아직 모아둔 생각이 없어요';
    const description = document.createElement('span');
    description.textContent = query ? '다른 검색어로 다시 찾아보세요.' : '첫 번째 아이디어를 기록해 보세요.';
    empty.append(heading, description); container.append(empty); return;
  }
  for (const idea of shown) {
    const card = document.createElement('article'); card.className = 'card';
    const date = document.createElement('time'); date.dateTime = idea.createdAt; date.textContent = new Intl.DateTimeFormat('ko-KR', {year:'numeric',month:'long',day:'numeric'}).format(new Date(idea.createdAt));
    const heading = document.createElement('h3'); heading.textContent = idea.title;
    const memo = document.createElement('p'); memo.textContent = idea.content;
    card.append(date, heading, memo); container.append(card);
  }
}
async function refresh() {
  try { ideas = (await store('readonly', s => s.getAll())).reverse(); $('list-error').hidden = true; $('retry').hidden = true; render(); }
  catch { $('list-error').textContent = '아이디어를 불러오지 못했어요. 브라우저 저장소를 확인하고 다시 시도해 주세요.'; $('list-error').hidden = false; $('retry').hidden = false; }
}
function clearValidation(field) {
  $(field.id + '-error').hidden = true;
  field.removeAttribute('aria-invalid');
  field.setAttribute('aria-describedby', field.id + '-hint');
}
for (const field of [title, content]) field.addEventListener('input', () => {
  if (field === title ? field.value.trim() && field.value.length <= 60 : field.value.length <= 500) clearValidation(field);
});
function showList() { formScreen.hidden = true; list.hidden = false; $('idea-form').reset(); clearValidation(title); clearValidation(content); $('save-error').hidden = true; $('add').focus(); return refresh(); }
$('add').addEventListener('click', () => { list.hidden = true; formScreen.hidden = false; title.focus(); });
$('retry').addEventListener('click', refresh);
window.addEventListener('focus', refresh);
// Each tab writes a separate IndexedDB record; reread notifications never replace drafts.
const updates = typeof BroadcastChannel === 'function' ? new BroadcastChannel('moeum-ideas-updates') : null;
if (updates) updates.onmessage = () => refresh();
$('cancel').addEventListener('click', showList); $('back').addEventListener('click', showList);
$('search').addEventListener('input', render);
$('idea-form').addEventListener('submit', async event => {
  event.preventDefault();
  clearValidation(title); clearValidation(content);
  if (!title.value.trim() || title.value.length > 60) {
    $('title-error').textContent = title.value.length > 60 ? '제목은 최대 60자까지 입력해 주세요.' : '공백이 아닌 제목을 입력해 주세요.';
    $('title-error').hidden = false; title.setAttribute('aria-invalid', 'true'); title.setAttribute('aria-describedby', 'title-hint title-error'); title.focus(); return;
  }
  if (content.value.length > 500) { $('content-error').hidden = false; content.setAttribute('aria-invalid', 'true'); content.setAttribute('aria-describedby', 'content-hint content-error'); content.focus(); return; }
  $('save-error').hidden = true; $('save').disabled = $('cancel').disabled = $('back').disabled = title.disabled = content.disabled = true;
  let saved = false;
  try { await store('readwrite', s => s.add({title: title.value, content: content.value, createdAt: new Date().toISOString()})); saved = true; updates?.postMessage('saved'); }
  catch { $('save-error').hidden = false; }
  finally { $('save').disabled = $('cancel').disabled = $('back').disabled = title.disabled = content.disabled = false; }
  if (saved) await showList();
});
refresh();
