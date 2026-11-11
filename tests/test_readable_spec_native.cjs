const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
vm.runInThisContext(execFileSync('python3.13', ['-B', '-c',
  'import sys; sys.path.insert(0, sys.argv[1]); from specification_contract import spec_label_prelude; sys.stdout.write(spec_label_prelude())',
  path.join(root, 'tools')], {encoding: 'utf8'}));
const {ensureNativeAnnotations} = require('../figma-bridge/native_annotations.js');
const {ensureDesignNoteBoard} = require('../figma-bridge/design_note_board.js');
const {readNativeSemantics} = require('../figma-bridge/native_semantic_read.js');
let sequence = 0;
class Node {
  constructor(type) { Object.assign(this,{id:String(++sequence),type,name:type,children:[],data:{},annotations:[],x:0,y:0,width:100,height:20,visible:true}); }
  appendChild(node) { if(node.parent) node.parent.children=node.parent.children.filter(n=>n!==node); node.parent=this;this.children.push(node); }
  setPluginData(key,value) { if(this.failData) {this.failData=false;throw Error('injected metadata failure');} this.data[key]=value; }
  getPluginData(key) {return this.data[key] || '';}
  async loadAsync() {}
  findAll(test) {return this.children.flatMap(n=>[...(test(n)?[n]:[]),...n.findAll(test)]);}
  resize(width,height) {this.width=width;this.height=height;}
  setRangeHyperlink(start,end,link) {if(this.failLink){this.failLink=false;throw Error('injected link failure');}this.link=link;}
  getRangeHyperlink() {return this.link;}
  remove() {this.removed=true;this.parent.children=this.parent.children.filter(n=>n!==this);}
}
const spec = (text='좌석을 선택합니다.') => ({schema:'figma-flow-readable-spec-v1',id:'SPEC-seat',kind:'control',screen_id:'map',target_id:'seat',title:'좌석 선택',meaning:{purpose:text},meaning_sha256:'a'.repeat(64),source_graph_sha256:'b'.repeat(64),source_graph_encoding:'canonical-json',display_text:text,trace:{requirements:[],acceptance:[],tests:[],relationships:[],status:'unverified',source_authority:'graph'}});
function setup() {
 const page=new Node('PAGE'),target=new Node('FRAME');target.setPluginData('semanticKey','map.seat');page.appendChild(target);
 const figma={fileKey:'file-key',createFrame:()=>new Node('FRAME'),createText:()=>new Node('TEXT'),loadFontAsync:async()=>{},variables:{getLocalVariableCollectionsAsync:async()=>[]}};
 const boardContract={presentation:'readable-specs',sourceHash:'owner',font:{family:'Explicit',style:'Regular'},notes:[{key:'map.seat',targetId:target.id,specification:spec()}]};
 return {page,target,figma,boardContract};
}
async function prepare(env,expected) {
 const board=await ensureDesignNoteBoard(env.figma,env.page,env.boardContract);
 const annotation={key:'map.seat',label:'unused human label',specification:env.boardContract.notes[0].specification,board:{boardId:board.boardId,textNodeId:board.entries[0].textNodeId,key:'map.seat'}};
 if(expected) annotation.expected_legacy=expected;
 return {board,contract:{presentation:'readable-specs',sourceHash:'owner',annotations:[annotation]}};
}
(async()=>{
 {
 const e=setup(),{board,contract}=await prepare(e);
 const result=await ensureNativeAnnotations(e.figma,e.page,contract);
 assert.equal(result.changed,1);assert.deepEqual(e.target.annotations,[]);
 const wrapper=JSON.parse(e.target.getPluginData('figmaFlowSpecification'));
 assert.equal(wrapper.target_id,e.target.id);assert.equal(wrapper.specification.target_id,'seat');
 assert.equal((await ensureNativeAnnotations(e.figma,e.page,contract)).changed,0);
 const row=(await readNativeSemantics(e.figma,e.page)).nodes.find(n=>n.id===e.target.id);
 assert.equal(row.specification_status,'observed');assert.equal(row.specification.state,'applied');
 const nativeBoard=e.page.findAll(n=>n.id===board.boardId)[0];
 assert.equal(nativeBoard.children[1].characters,'좌석 선택\n좌석을 선택합니다.');assert(!nativeBoard.children[1].characters.includes('map.seat'));
 assert.equal((await ensureDesignNoteBoard(e.figma,e.page,e.boardContract)).changed,0);
 e.boardContract.notes[0].specification=spec('좌석을 선택한 뒤 확인합니다.');
 const updated=await ensureDesignNoteBoard(e.figma,e.page,e.boardContract);
 assert.equal(updated.entries[0].textNodeId,board.entries[0].textNodeId);assert.equal(updated.changed,1);
 await updated.rollback();assert.equal(nativeBoard.children[1].characters,'좌석 선택\n좌석을 선택합니다.');
 await result.rollback();assert.equal(e.target.getPluginData('figmaFlowSpecification'),'');
 await board.rollback();assert(nativeBoard.removed);
 }
 {
 const e=setup(),legacy={label:'[figma-flow:map.seat] Full raw label',labelMarkdown:'**Full** raw label',properties:[{type:'width'}],categoryId:'custom'},user={label:'user note'};
 e.target.annotations=[user,legacy,{label:'last user'}];
 const {contract}=await prepare(e,[{index:1,annotation:legacy}]);
 const result=await ensureNativeAnnotations(e.figma,e.page,contract);
 assert.deepEqual(e.target.annotations,[user,{label:'last user'}]);
 assert.deepEqual(JSON.parse(e.target.getPluginData('figmaFlowSpecification')).legacy_annotations,[{index:1,annotation:legacy}]);
 e.target.annotations.push({label:'concurrent user'});await result.rollback();
 assert.deepEqual(e.target.annotations,[user,legacy,{label:'last user'},{label:'concurrent user'}]);
 }
 for(const failure of ['missing snapshot','edited snapshot','duplicate','unsupported','wrong owner','wrong link','malformed','oversize']) {
 const e=setup(),legacy={label:'[figma-flow:map.seat] original'};e.target.annotations=[legacy];
 const {contract,board}=await prepare(e,[{index:0,annotation:{...legacy}}]);
 const boardNode=e.page.findAll(n=>n.id===board.boardId)[0];
 if(failure==='missing snapshot') delete contract.annotations[0].expected_legacy;
 if(failure==='edited snapshot') e.target.annotations[0]={label:'[figma-flow:map.seat] edited'};
 if(failure==='duplicate') e.target.annotations.push(legacy);
 if(failure==='unsupported'){legacy.extra='unknown';contract.annotations[0].expected_legacy=[{index:0,annotation:legacy}];}
 if(failure==='wrong owner') boardNode.setPluginData('designNoteBoard','{}');
 if(failure==='wrong link') boardNode.children[1].link={type:'NODE',value:'foreign'};
 if(failure==='malformed') e.target.setPluginData('figmaFlowSpecification','{broken');
 if(failure==='oversize') contract.annotations[0].specification={...spec(),display_text:'한'.repeat(31000)};
 const before=JSON.stringify(e.target.annotations),metadata=e.target.getPluginData('figmaFlowSpecification');
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract));
 assert.equal(JSON.stringify(e.target.annotations),before);assert.equal(e.target.getPluginData('figmaFlowSpecification'),metadata);
 }
 {
 const e=setup(),{contract}=await prepare(e);e.target.failData=true;
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/injected/);
 assert.equal(e.target.getPluginData('figmaFlowSpecification'),'');
 e.target.setPluginData('figmaFlowSpecification','malformed');
 assert.equal((await readNativeSemantics(e.figma,e.page)).nodes.find(n=>n.id===e.target.id).specification_status,'invalid');
 }
 {
 const e=setup(),{board}=await prepare(e);const text=e.page.findAll(n=>n.id===board.entries[0].textNodeId)[0];
 e.boardContract.notes[0].specification=spec('바뀐 설명');text.failLink=true;
 await assert.rejects(ensureDesignNoteBoard(e.figma,e.page,e.boardContract),/injected/);
 assert.equal(text.characters,'좌석 선택\n좌석을 선택합니다.');
 const update=await ensureDesignNoteBoard(e.figma,e.page,e.boardContract);text.characters='concurrent user edit';
 await assert.rejects(update.rollback(),/concurrent/);assert.equal(text.characters,'concurrent user edit');
 }

 {
 const e=setup();
 const second=new Node('FRAME');second.setPluginData('semanticKey','map.other');second.x=200;e.page.appendChild(second);
 const legacyContract={sourceHash:'owner',font:e.boardContract.font,notes:[{key:'map.seat',targetId:e.target.id,label:'Legacy first'},{key:'map.other',targetId:second.id,label:'Legacy untouched'}]};
 const legacy=await ensureDesignNoteBoard(e.figma,e.page,legacyContract);
 const board=e.page.findAll(n=>n.id===legacy.boardId)[0];
 const original=board.children.map(n=>({id:n.id,characters:n.characters,link:n.link}));
 const expectedEntries=board.children.map(n=>({key:n.getPluginData('semanticKey'),textNodeId:n.id,characters:n.characters,hyperlink:n.link || null}));
 await assert.rejects(ensureDesignNoteBoard(e.figma,e.page,{...e.boardContract,partial:true}),/heading|unowned/);
 const update=await ensureDesignNoteBoard(e.figma,e.page,{...e.boardContract,partial:true,expectedEntries});
 assert.equal(update.entries[0].textNodeId,legacy.entries[0].textNodeId);
 assert.equal(board.children[2].characters,original[2].characters);
 assert.equal(board.children[2].getPluginData('figmaFlowSpecificationEntry'),'');
 await update.rollback();assert.deepEqual(board.children.map(n=>({id:n.id,characters:n.characters,link:n.link})),original);
 }
 {
 const e=setup(),legacy={label:'[figma-flow:map.seat] original'},user={label:'original user'};
 e.target.annotations=[legacy,user];const {contract}=await prepare(e,[{index:0,annotation:legacy}]);
 const migration=await ensureNativeAnnotations(e.figma,e.page,contract);
 e.target.annotations=[{label:'edited user'}];await assert.rejects(migration.rollback(),/concurrent/);
 assert.deepEqual(e.target.annotations,[{label:'edited user'}]);
 const row=(await readNativeSemantics(e.figma,e.page)).nodes.find(n=>n.id===e.target.id);
 assert.equal(row.specification.state,'conflict');assert.equal(row.specification.legacy_annotations[0].annotation.label,legacy.label);
 }

 {
 const e=setup(),second=new Node('FRAME');second.setPluginData('semanticKey','map.other');second.x=200;e.page.appendChild(second);
 const firstLegacy={label:'[figma-flow:map.seat] first legacy'},secondLegacy={label:'[figma-flow:map.other] second legacy'};
 e.target.annotations=[{label:'first user before'},firstLegacy,{label:'first user after'}];
 second.annotations=[{label:'second user before'},secondLegacy,{label:'second user after'}];
 const firstBefore=JSON.parse(JSON.stringify(e.target.annotations)),secondBefore=JSON.parse(JSON.stringify(second.annotations));
 const otherSpec={...spec(),id:'SPEC-other',target_id:'other'};
 e.boardContract.notes.push({key:'map.other',targetId:second.id,specification:otherSpec});
 const {contract,board}=await prepare(e,[{index:1,annotation:firstLegacy}]);
 contract.annotations.push({key:'map.other',specification:otherSpec,expected_legacy:[{index:1,annotation:secondLegacy}],board:{boardId:board.boardId,textNodeId:board.entries[1].textNodeId,key:'map.other'}});
 const originalSetter=second.setPluginData.bind(second);let injected=false;
 second.setPluginData=(key,value)=>{
   if(key==='figmaFlowSpecification' && value && !injected){
     injected=true;assert.deepEqual(e.target.annotations,firstBefore);assert.deepEqual(second.annotations,secondBefore);
     assert.equal(JSON.parse(e.target.getPluginData(key)).state,'pending');
     throw Error('second target metadata failure');
   }
   originalSetter(key,value);
 };
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/second target metadata failure/);
 assert(injected);assert.deepEqual(e.target.annotations,firstBefore);assert.deepEqual(second.annotations,secondBefore);
 assert.equal(e.target.getPluginData('figmaFlowSpecification'),'');assert.equal(second.getPluginData('figmaFlowSpecification'),'');
 second.setPluginData=originalSetter;
 const migration=await ensureNativeAnnotations(e.figma,e.page,contract);
 assert.equal(JSON.parse(e.target.getPluginData('figmaFlowSpecification')).state,'applied');
 assert.equal(JSON.parse(second.getPluginData('figmaFlowSpecification')).state,'applied');
 await migration.rollback();assert.deepEqual(e.target.annotations,firstBefore);assert.deepEqual(second.annotations,secondBefore);
 }
 {
 const e=setup(),{contract}=await prepare(e);
 await ensureNativeAnnotations(e.figma,e.page,contract);
 const applied=e.target.getPluginData('figmaFlowSpecification');
 const newlyAppeared={label:'[figma-flow:map.seat] newly appeared'};
 e.target.annotations=[{label:'user'},newlyAppeared];contract.annotations[0].expected_legacy=[{index:1,annotation:newlyAppeared}];
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/partial or conflicting/);
 assert.equal(e.target.getPluginData('figmaFlowSpecification'),applied);assert.deepEqual(e.target.annotations,[{label:'user'},newlyAppeared]);
 e.target.annotations=[];delete contract.annotations[0].expected_legacy;
 const pending=JSON.stringify({...JSON.parse(applied),state:'pending'});e.target.setPluginData('figmaFlowSpecification',pending);
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/invalid existing metadata/);
 assert.equal(e.target.getPluginData('figmaFlowSpecification'),pending);
 const row=(await readNativeSemantics(e.figma,e.page)).nodes.find(node=>node.id===e.target.id);
 assert.equal(row.specification.state,'pending');assert.equal(row.specification_status,'observed');
 }

 for(const guard of ['expected_before','preflight']) {
 const e=setup(),{contract}=await prepare(e);
 const expected={specification:null,annotations:[]};
 contract.annotations[0].expected_before=expected;
 let metadataWrites=0,preflights=0;
 const setter=e.target.setPluginData.bind(e.target);
 e.target.setPluginData=(key,value)=>{if(key==='figmaFlowSpecification')metadataWrites++;setter(key,value);};
 e.page.loadAsync=async()=>{e.target.annotations.push({label:'concurrent user during load'});};
 if(guard==='preflight') contract.preflight=async()=>{preflights++;assert.deepEqual(e.target.annotations,[{label:'concurrent user during load'}]);throw Error('trusted preflight conflict');};
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),guard==='preflight' ? /trusted preflight conflict/ : /expected before-state conflict/);
 assert.equal(metadataWrites,0);assert.equal(preflights,guard==='preflight'?1:0);
 assert.deepEqual(e.target.annotations,[{label:'concurrent user during load'}]);
 }
 {
 const e=setup(),{contract}=await prepare(e);
 contract.preflight='untrusted serialized callback';
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/trusted function/);
 delete contract.preflight;
 contract.annotations[0].expected_before={specification:null,annotations:[],extra:'not allowed'};
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/expected before-state conflict/);
 contract.annotations[0].expected_before={annotations:[],specification:null};
 let preflights=0;contract.preflight=async()=>{preflights++;};
 await ensureNativeAnnotations(e.figma,e.page,contract);assert.equal(preflights,1);
 const current=JSON.parse(e.target.getPluginData('figmaFlowSpecification'));
 const reversed=Object.fromEntries(Object.entries(current).reverse());
 contract.annotations[0].expected_before={specification:reversed,annotations:[]};
 assert.equal((await ensureNativeAnnotations(e.figma,e.page,contract)).changed,0);
 }

 {
 const e=setup();
 const nativeKey='map.desktop.state-map-selection.seat-confirm',entryKey='desktop|state-map-selection|seat-confirm';
 e.target.setPluginData('semanticKey',nativeKey);
 e.boardContract.boardKey='review.notes.map';e.boardContract.notes[0].key=entryKey;
 e.boardContract.notes[0].specification={...spec(),target_id:'seat-confirm'};
 const legacy={label:`[figma-flow:${nativeKey}] 기존 설명`,labelMarkdown:'**기존 설명**',properties:[{type:'width'}],categoryId:'existing'};
 e.target.annotations=[{label:'user before'},legacy,{label:'user after'}];
 const {contract,board}=await prepare(e,[{index:1,annotation:legacy}]);
 contract.annotations[0].key=nativeKey;contract.annotations[0].board.key=entryKey;
 const text=e.page.findAll(node=>node.id===board.entries[0].textNodeId)[0];
 const originalTextKey=text.getPluginData('semanticKey');
 assert.equal(originalTextKey,'review.notes.map:'+entryKey);
 const migration=await ensureNativeAnnotations(e.figma,e.page,contract);
 const stored=JSON.parse(e.target.getPluginData('figmaFlowSpecification'));
 assert.equal(stored.semantic_key,nativeKey);assert.equal(stored.target_id,e.target.id);assert.equal(stored.specification.target_id,'seat-confirm');
 assert.equal(text.getPluginData('semanticKey'),originalTextKey);assert.equal(e.target.getPluginData('semanticKey'),nativeKey);
 assert.equal((await ensureNativeAnnotations(e.figma,e.page,contract)).changed,0);
 assert.deepEqual(e.target.annotations,[{label:'user before'},{label:'user after'}]);
 await migration.rollback();assert.deepEqual(e.target.annotations,[{label:'user before'},legacy,{label:'user after'}]);
 }

 for(const nativeKey of ['screen-map','control-map-seat']) {
 const e=setup();e.target.setPluginData('semanticKey',nativeKey);
 e.page.setPluginData('figmaFlow',JSON.stringify({semantic_id:'design-import',bridge:1,source_sha256:'owner',complete:true}));
 e.target.setPluginData('figmaFlow',JSON.stringify({semantic_id:nativeKey,annotation_mode:'native'}));
 const raw={label:'좌석을 선택하면 선택 상태로 바뀌고 확인 버튼이 활성화됩니다.',labelMarkdown:'좌석을 **선택**하면 선택 상태로 바뀝니다.',properties:[{type:'width'}],categoryId:'imported'};
 e.target.annotations=[{label:'사용자 메모'},raw,{label:'다른 사용자 메모'}];
 const original=JSON.parse(JSON.stringify(e.target.annotations));
 const {contract}=await prepare(e,{index:1,annotation:raw});contract.annotations[0].key=nativeKey;
 const migration=await ensureNativeAnnotations(e.figma,e.page,contract);
 assert.deepEqual(e.target.annotations,[original[0],original[2]]);
 assert.deepEqual(JSON.parse(e.target.getPluginData('figmaFlowSpecification')).legacy_annotations,[{index:1,annotation:raw}]);
 assert.equal((await ensureNativeAnnotations(e.figma,e.page,contract)).changed,0);
 e.target.annotations.push(raw);
 const applied=e.target.getPluginData('figmaFlowSpecification');
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/partial or conflicting/);
 assert.equal(e.target.getPluginData('figmaFlowSpecification'),applied);assert.deepEqual(e.target.annotations,[original[0],original[2],raw]);
 e.target.annotations.pop();e.target.annotations.push({label:'나중에 추가된 사용자 메모'});
 await migration.rollback();assert.deepEqual(e.target.annotations,[...original,{label:'나중에 추가된 사용자 메모'}]);
 }
 for(const missingProof of ['missing node','wrong semantic','wrong mode','missing page','wrong source','malformed','duplicate raw']) {
 const e=setup(),raw={label:'직접 작성된 옛 가져오기 설명'};
 e.target.setPluginData('figmaFlow',JSON.stringify({semantic_id:'map.seat',annotation_mode:'native'}));
 e.page.setPluginData('figmaFlow',JSON.stringify({semantic_id:'design-import',source_sha256:'owner'}));
 e.target.annotations=[{label:'사용자 메모'},raw];
 const {contract}=await prepare(e,[{index:1,annotation:raw}]);
 if(missingProof==='missing node') e.target.setPluginData('figmaFlow','');
 if(missingProof==='wrong semantic') e.target.setPluginData('figmaFlow',JSON.stringify({semantic_id:'other',annotation_mode:'native'}));
 if(missingProof==='wrong mode') e.target.setPluginData('figmaFlow',JSON.stringify({semantic_id:'map.seat',annotation_mode:'user'}));
 if(missingProof==='missing page') e.page.setPluginData('figmaFlow','');
 if(missingProof==='wrong source') e.page.setPluginData('figmaFlow',JSON.stringify({source_sha256:'other'}));
 if(missingProof==='malformed') e.target.setPluginData('figmaFlow','{broken');
 if(missingProof==='duplicate raw') e.target.annotations.push(raw);
 const before=JSON.parse(JSON.stringify(e.target.annotations));let writes=0;
 const setter=e.target.setPluginData.bind(e.target);e.target.setPluginData=(key,value)=>{if(key==='figmaFlowSpecification')writes++;setter(key,value);};
 await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/private import ownership|ambiguous or edited/);
 assert.equal(writes,0);assert.deepEqual(e.target.annotations,before);
 }
 {
  const e=setup(),connected={...spec(),presentation:'connected-spec-v2',locale:'ko',sections:[{key:'purpose',title:'목적',body:'좌석 선택을 돕습니다.'}],annotation_text:'좌석을 선택하면 확인할 수 있습니다.'};
  const {board,contract}=await prepare(e);contract.annotations[0].specification=connected;contract.fileKey=e.figma.fileKey;e.target.annotations=[{label:'사용자 메모'}];
  const result=await ensureNativeAnnotations(e.figma,e.page,contract),raw=e.target.annotations[1],url=`https://www.figma.com/design/${e.figma.fileKey}?node-id=${board.entries[0].textNodeId.replace(/:/g,'-')}`;
  assert.match(raw.labelMarkdown,/좌석 선택/);assert.match(raw.labelMarkdown,/좌석을 선택하면 확인할 수 있습니다/);assert.match(raw.labelMarkdown,new RegExp(url.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.deepEqual(e.target.annotations[0],{label:'사용자 메모'});assert.equal((await ensureNativeAnnotations(e.figma,e.page,contract)).changed,0);
  const wrapper=JSON.parse(e.target.getPluginData('figmaFlowSpecification'));assert.equal(wrapper.human_annotation.index,1);assert.deepEqual(wrapper.human_annotation.annotation,raw);assert.equal(wrapper.human_annotation.board.textNodeId,board.entries[0].textNodeId);
  e.target.annotations.push({...raw,categoryId:'duplicate-category'});
  const duplicateRead=await readNativeSemantics(e.figma,e.page);
  assert.equal(duplicateRead.nodes.find(node=>node.id===e.target.id).specification_status,'invalid');
  e.target.annotations.pop();
  e.target.annotations[1]={...raw,labelMarkdown:'edited'};await assert.rejects(ensureNativeAnnotations(e.figma,e.page,contract),/edited or missing/);
  e.target.annotations[1]=raw;e.target.annotations.push({label:'later user note'});await result.rollback();assert.deepEqual(e.target.annotations,[{label:'사용자 메모'},{label:'later user note'}]);
 }
 {
  const e=setup(),connected={...spec(),presentation:'connected-spec-v2',locale:'en',sections:[{key:'purpose',title:'Purpose',body:'Choose a seat.'}],annotation_text:'Selecting a seat enables confirmation.'};
  const {contract}=await prepare(e);contract.annotations[0].specification=connected;contract.fileKey=e.figma.fileKey;e.target.annotations=[{label:'user'},{label:'[figma-flow:map.seat] old owned'},{label:'tail'}];contract.annotations[0].expected_legacy={index:1,annotation:e.target.annotations[1]};
  await ensureNativeAnnotations(e.figma,e.page,contract);assert.deepEqual(e.target.annotations.map(n=>n.label),['user',undefined,'tail']);
  assert.equal(JSON.parse(e.target.getPluginData('figmaFlowSpecification')).legacy_annotations[0].annotation.label,'[figma-flow:map.seat] old owned');
 }
 console.log('readable specification native mock checks passed; actual native execution UNVERIFIED');
})().catch(error=>{console.error(error);process.exitCode=1;});
