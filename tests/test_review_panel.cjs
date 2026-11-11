/* Modeled protocol state and actual React SSR; no Figma execution or approval evidence. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {spawnSync} = require('node:child_process');

const panelRoot = path.resolve(__dirname, '../panel-ui');
const panelRequire = createRequire(path.join(panelRoot, 'package.json'));
const reviewPath = path.join(panelRoot, 'src/ReviewPanel.jsx');

test('selected production labels are truthful in three locales while exploratory review is unchanged', async () => {
  const entry = `
import assert from 'node:assert/strict';
import fs from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ReviewPanel,{reviewMessageKey,__initialState,__reducer} from './src/ReviewPanel.jsx';
import {Shell,PanelContext} from './src/components.jsx';
globalThis.window={};
const dictionary={...JSON.parse(fs.readFileSync('../figma-bridge/locales/workspace.json','utf8')),...JSON.parse(fs.readFileSync('../figma-bridge/locales/review.json','utf8'))};
const translate=locale=>(key,params={})=>{assert(dictionary[key],'missing copy '+key);return dictionary[key][locale].replace(/\\{(\\w+)\\}/g,(match,name)=>params[name]===undefined?match:String(params[name]));};
const candidates=[{id:'briefing',title:'Selected briefing'},{id:'notebook',title:'Other direction'}];
const review={scope:'exploratory-only',candidates,pageName:'DRAFT fixture'};
const production={scope:'selected-production',selectedProduction:true,candidates:candidates.slice(0,1),pageName:'PRODUCTION fixture',sourceSelection:{candidate_id:'briefing',selection_sha256:'a'.repeat(64)}};
function render(locale,model){const t=translate(locale);return renderToStaticMarkup(<PanelContext.Provider value={{locale,t,setLocale(){},hostBusy:false}}><ReviewPanel model={model} locale={locale} t={t} send={()=>{throw Error('SSR must not execute');}} Shell={Shell}/></PanelContext.Provider>);}
const productionTitles={ko:'선택한 방향 본제작',en:'Selected direction production',ja:'選択した案の本制作'};
for(const locale of ['ko','en','ja']){
 const t=translate(locale), ordinary=render(locale,review), selected=render(locale,production);
 assert(ordinary.includes(t('review.heading',{count:2})));assert(ordinary.includes(t('review.boundary')));
 assert(!ordinary.includes(productionTitles[locale]));
 assert(selected.includes(productionTitles[locale]));assert(selected.includes(t('review.production.readyTitle')));
 assert(selected.includes('PRODUCTION fixture'));assert(selected.includes('Selected briefing'));assert(!selected.includes('Other direction'));
 assert(selected.includes(t('review.production.boundary')));assert(!selected.includes(t('review.boundary')));
 assert(!selected.includes(t('review.readBody')));assert(!selected.includes(t('review.production.readTitle')),'ready must not claim a successful native read');
 assert.equal((selected.match(/id="make"/g)||[]).length,1);assert.equal((selected.match(/id="save"/g)||[]).length,1);
 assert(selected.includes(t('review.production.make')));assert(ordinary.includes(t('review.make')));
 const wrongScope=render(locale,{...production,scope:'exploratory-only'});assert(!wrongScope.includes(productionTitles[locale]));
 const multiple=render(locale,{...production,candidates});assert(!multiple.includes(productionTitles[locale]));
 let state=__reducer(__initialState,{type:'create'});assert.equal(state.nativeBusy,true);
 assert.equal(t(reviewMessageKey(true,state.notice.title)),t('review.production.creatingTitle'));
 state=__reducer(state,{type:'readback',data:{scope:'selected-production'},paired:false});
 assert.equal(state.notice.state,'success');assert.equal(state.resultKind,'readback');
 assert.equal(t(reviewMessageKey(true,state.notice.title)),t('review.production.readTitle'));
 assert.equal(t(reviewMessageKey(true,state.notice.body)),t('review.production.readBody'));
 state=__reducer(state,{type:'receipt',passed:true,details:''});
 assert.equal(t(reviewMessageKey(true,state.notice.title)),t('review.production.verifiedTitle'));
 assert.equal(t(reviewMessageKey(true,state.notice.body)),t('review.production.verifiedBody'));
 const rejected=__reducer(state,{type:'receipt',passed:false,details:'real receiver diagnostics'});
 assert.equal(rejected.notice.state,'error');assert.equal(rejected.notice.details,'real receiver diagnostics');
 assert.equal(reviewMessageKey(true,rejected.notice.title),'review.rejectedTitle');
 assert.equal(reviewMessageKey(false,'verifiedBody'),'review.verifiedBody');
}
assert(fs.readFileSync('./src/ReviewPanel.jsx','utf8').includes("send({ type: 'draft-review' })"));
console.log('Production and review ready/readback/validation copy and unchanged actions verified in ko/en/ja.');
`;
  // Export private state functions only in this in-memory test build, leaving the shipped API unchanged.
  const {build} = panelRequire('esbuild');
  const built = await build({
    stdin: {contents: entry, resolveDir: panelRoot, loader: 'jsx'}, absWorkingDir: panelRoot,
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    define: {'process.env.NODE_ENV': '"production"', __FLOW_DISPLAY_NAME__: JSON.stringify(JSON.parse(fs.readFileSync(path.join(panelRoot, '../plugin.json'), 'utf8')).extensions['com.openai'].interface.displayName), __FLOW_LOCALES__: JSON.stringify(Object.keys(Object.values(JSON.parse(fs.readFileSync(path.join(panelRoot, '../figma-bridge/locales/common.json'), 'utf8')))[0]))}, logLevel: 'silent',
    plugins: [{name: 'review-state-fixture', setup(builder) {
      builder.onLoad({filter: /ReviewPanel\.jsx$/}, () => ({
        contents: fs.readFileSync(reviewPath, 'utf8') + '\nexport {initialState as __initialState,reducer as __reducer};',
        loader: 'jsx', resolveDir: path.dirname(reviewPath),
      }));
    }}],
  });
  const result = spawnSync(process.execPath, ['-e', built.outputFiles[0].text], {cwd: panelRoot, encoding: 'utf8'});
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /unchanged actions verified/);
});
