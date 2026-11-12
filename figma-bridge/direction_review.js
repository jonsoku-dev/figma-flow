/* Pinned rich-layout renderer. Selected production requires a distinct admitted packet. */
const SELECTED_PRODUCTION=typeof DRAFT!=='undefined'&&typeof FLOW_PRODUCTION_SCHEMA==='string'&&DRAFT.schema===FLOW_PRODUCTION_SCHEMA;
const OWNER=SELECTED_PRODUCTION?'figma-flow-selected-production-v1':'figma-flow-direction-review-v1';let busy=false,last='',lastState='ready',lastData=null;
const RESERVATION='figmaFlowDraftReviewReservation';
const copy=value=>JSON.parse(JSON.stringify(value));
const status=(message,state)=>{last=message;if(state)lastState=state;figma.ui.postMessage({type:'status',message,busy,state:lastState});};
function tag(n,key){n.name=key;n.setPluginData('semanticKey',key);return n;}
function rgb(hex){if(!/^#[0-9a-f]{6}$/i.test(hex))throw Error('Pinned six-digit color required');return {r:parseInt(hex.slice(1,3),16)/255,g:parseInt(hex.slice(3,5),16)/255,b:parseInt(hex.slice(5,7),16)/255};}
function noteLabel(note){const fields=[['purpose','목적'],['journey','사용 순서'],['first_action','첫 행동'],['action','동작 ID'],['behavior','동작'],['precondition','전제'],['result','결과'],['failure','경계'],['design_choice','배치 이유']];return fields.filter(([key])=>note[key]).map(([key,title])=>title+': '+note[key]).concat(note.functional_states?['기능 상태: '+note.functional_states.join(', ')]:[],note.visual_variant?['시각 변형: '+note.visual_variant]:[]).join('\n');}
function draftAnnotation(candidate,key,note){const value={key,label:noteLabel(note)};if(candidate.specifications){if(!candidate.specifications[note.id])throw Error('Canonical readable specification missing: '+note.id);value.specification=candidate.specifications[note.id];}return value;}
function draftBoardEntry(candidate,key,targetId,note,label){return candidate.specifications?{key,targetId,specification:candidate.specifications[note.id]}:{key,targetId,label};}

// Leave room for the key and Figma's per-entry overhead below its 100 kB limit.
function writeDraftJSON(page, key, value) {
  const raw = JSON.stringify(value);
  const previous = page.getPluginData(key);
  const previousValue = previous ? JSON.parse(previous) : null;
  const previousChunkCount = previousValue?.format === 'figma-flow-json-chunks-v1' ? previousValue.chunks : 0;
  if (!Number.isSafeInteger(previousChunkCount) || previousChunkCount < 0) {
    throw Error('Invalid chunked draft metadata ' + key);
  }
  const chunks = [];
  let chunk = '';
  let chunkBytes = 0;

  for (const character of raw) {
    const point = character.codePointAt(0);
    const characterBytes = point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4;
    if (chunkBytes + characterBytes > 60000) {
      chunks.push(chunk);
      chunk = '';
      chunkBytes = 0;
    }
    chunk += character;
    chunkBytes += characterBytes;
  }
  chunks.push(chunk);

  if (chunks.length === 1) {
    page.setPluginData(key, raw);
  } else {
    chunks.forEach((part, index) => page.setPluginData(key + '__chunk_' + index, part));
    page.setPluginData(key, JSON.stringify({format: 'figma-flow-json-chunks-v1', chunks: chunks.length}));
  }
  const firstUnusedChunk = chunks.length === 1 ? 0 : chunks.length;
  for (let index = firstUnusedChunk; index < previousChunkCount; index++) {
    page.setPluginData(key + '__chunk_' + index, '');
  }
}

function readDraftJSON(page, key, fallback) {
  const raw = page.getPluginData(key);
  if (!raw) return fallback;
  const value = JSON.parse(raw);
  if (value?.format !== 'figma-flow-json-chunks-v1') return value;
  if (!Number.isSafeInteger(value.chunks) || value.chunks < 2) {
    throw Error('Invalid chunked draft metadata ' + key);
  }
  const parts = [];
  for (let index = 0; index < value.chunks; index++) {
    const part = page.getPluginData(key + '__chunk_' + index);
    if (!part) throw Error('Missing draft metadata chunk ' + key + ' ' + index);
    parts.push(part);
  }
  return JSON.parse(parts.join(''));
}

function draftReviewIdentity(){return {fileKey:DRAFT.fileKey||figma.fileKey,packet_sha256:DRAFT.packet_sha256,instance_sha256:DRAFT.instance_sha256,layout_sha256:DRAFT.layout_sha256};}
function sameDraftReviewPacket(first,second){return first?.fileKey===second.fileKey&&first?.packet_sha256===second.packet_sha256&&first?.layout_sha256===second.layout_sha256;}
function completedDraftReview(page,identity,reservation){
 const owner=page.getPluginData(OWNER);
 if(!/^[a-f0-9]{64}$/.test(owner||'')||page.getPluginData('packet_sha256')!==identity.packet_sha256)return false;
 return !reservation||(reservation.state==='complete'&&sameDraftReviewPacket(reservation.identity,identity)&&reservation.identity.instance_sha256===owner);
}
function validateCompletedDraftReview(page,identity,reservation){
 const owner=page.getPluginData(OWNER);
 if(!completedDraftReview(page,identity,reservation))throw Error('Completed review page '+page.id+' is missing valid completion ownership; inspect or repair it before retrying.');
 const metadata={};
 for(const key of ['draftCanonicalBindings','draftNoteFrames','draftPalettes','draftTextStyles']){
  if(!page.getPluginData(key))throw Error('Completed review page '+page.id+' is missing '+key+'; inspect or repair it before retrying.');
  metadata[key]=readDraftJSON(page,key,null);
 }
 if(!Array.isArray(metadata.draftCanonicalBindings)||!metadata.draftNoteFrames||Array.isArray(metadata.draftNoteFrames)||
    !metadata.draftPalettes||Array.isArray(metadata.draftPalettes)||!Array.isArray(metadata.draftTextStyles)||!metadata.draftTextStyles.length||
    metadata.draftTextStyles.some(id=>typeof id!=='string'||!id)||new Set(metadata.draftTextStyles).size!==metadata.draftTextStyles.length)
  throw Error('Completed review page '+page.id+' has invalid completion metadata; inspect or repair it before retrying.');
 for(const candidate of DRAFT.candidates){
  const note=metadata.draftNoteFrames[candidate.id],palette=metadata.draftPalettes[candidate.id];
  if(!note||typeof note.boardId!=='string'||!Array.isArray(note.entries)||!note.entries.length||!palette||typeof palette.libraryId!=='string'||!Array.isArray(palette.samples)||!palette.samples.length)
   throw Error('Completed review page '+page.id+' is missing candidate metadata for '+candidate.id+'; inspect or repair it before retrying.');
 }
 if(page.getPluginData('scope')!==DRAFT.scope||page.getPluginData('productionAdmitted')!==String(SELECTED_PRODUCTION))
  throw Error('Completed review page '+page.id+' is missing final scope metadata; inspect or repair it before retrying.');
 const frames=new Map([page,...page.findAll(()=>true)].map(node=>[node.getPluginData('semanticKey'),node]));
 const expected=draftFlowStarts(DRAFT.candidates,frames).map(({node})=>node?.id);
 const actual=page.flowStartingPoints;
 if(!Array.isArray(actual)||actual.some(start=>typeof start?.nodeId!=='string')||new Set(actual.map(start=>start.nodeId)).size!==actual.length||
    actual.length!==expected.length||expected.some(id=>!id||!actual.some(start=>start.nodeId===id)))
  throw Error('Completed review page '+page.id+' is missing declared flow starts; inspect or repair it before retrying.');
 return owner;
}
async function findInterruptedDraftReview(){
 const identity=draftReviewIdentity(),pages=figma.root.children;
 for(const page of pages){
  if(page.getPluginData(OWNER)===identity.instance_sha256){
   if(page.getPluginData('packet_sha256')!==identity.packet_sha256)throw Error('Existing completed review page '+page.id+' has missing or mismatched packet metadata; inspect or repair it before retrying.');
   const raw=page.getPluginData(RESERVATION);
   let reservation=null;
   if(raw){try{reservation=JSON.parse(raw);}catch{throw Error('Invalid completion reservation on page '+page.id+'; inspect or repair it before retrying.');}
    if(!reservation||typeof reservation!=='object')throw Error('Invalid completion reservation on page '+page.id+'; inspect or repair it before retrying.');
    if(reservation.state==='complete'&&!completedDraftReview(page,identity,reservation))throw Error('Existing completed review page '+page.id+' has mismatched reservation ownership; inspect or repair it before retrying.');
    if(reservation.state!=='complete')throw Error('Interrupted review is already reserved on page '+page.id+'; inspect or repair it before retrying.');
   }
   await page.loadAsync();validateCompletedDraftReview(page,identity,reservation);
   return page;
  }
 }
 for(const page of pages){
  const raw=page.getPluginData(RESERVATION);
  if(raw){let reservation;try{reservation=JSON.parse(raw);}catch{continue;}
   if(sameDraftReviewPacket(reservation.identity,identity)){
    if(reservation.state==='complete'&&completedDraftReview(page,identity,reservation))continue;
    throw Error('Interrupted or unclaimed review is already reserved on page '+page.id+'; inspect or repair that page before retrying.');
   }
  }
 }
 const title=(SELECTED_PRODUCTION?'PRODUCTION · '+DRAFT.candidates[0].title:(DRAFT.candidates.length===1?'DRAFT · '+DRAFT.candidates[0].title:'DRAFT · A/B/C 방향 검토'))+' · '+DRAFT.packet_sha256.slice(0,8);
 for(const page of pages){
  if(page.name!==title)continue;
  const raw=page.getPluginData(RESERVATION);
  let reservation;
  if(raw){try{reservation=JSON.parse(raw);}catch{throw Error('Invalid review reservation on matching page '+page.id+'; inspect or repair it before retrying.');}
   if(!reservation||typeof reservation!=='object')throw Error('Invalid review reservation on matching page '+page.id+'; inspect or repair it before retrying.');
   if(reservation.state!=='complete')throw Error('Interrupted review is already reserved on matching page '+page.id+'; inspect or repair it before retrying.');
   if(reservation?.state==='complete'){
    const owner=page.getPluginData(OWNER);
    if(completedDraftReview(page,identity,reservation)){await page.loadAsync();validateCompletedDraftReview(page,identity,reservation);continue;}
   if(page.getPluginData('packet_sha256')===identity.packet_sha256&&/^[a-f0-9]{64}$/.test(owner||''))throw Error('Completed review page '+page.id+' has mismatched reservation ownership; inspect or repair it before retrying.');
   }
  }else if(completedDraftReview(page,identity,null)){await page.loadAsync();validateCompletedDraftReview(page,identity,null);continue;}
  await page.loadAsync();
  for(const board of page.findAll(()=>true)){
   if(board.parent!==page||!DRAFT.candidates.some(candidate=>board.getPluginData('semanticKey')==='review.notes.'+candidate.id))continue;
   let owner;try{owner=JSON.parse(board.getPluginData('designNoteBoard'));}catch{continue;}
   if(owner.pageId===page.id&&typeof owner.sourceHash==='string'&&/^[a-f0-9]{64}$/.test(owner.sourceHash))throw Error('Interrupted legacy review page '+page.id+' is incomplete; inspect or repair that existing page before retrying.');
  }
 }
 return null;
}

function declareDraftNumber(tokens, name, value) {
  if (!Number.isFinite(value) || value < 0) throw Error('Finite draft role value required');
  const safeName = name.replace(/\./g, '_');
  const primitive = 'review/primitive/' + String(value).replace(/\./g, '_');
  declareDraftToken(tokens, primitive, 'FLOAT', value);
  declareDraftToken(tokens, safeName, 'FLOAT', null, primitive);
  return safeName;
}

function sameDraftValue(a,b){if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;const keys=Object.keys(a).sort(),other=Object.keys(b).sort();return keys.length===other.length&&keys.every((key,index)=>key===other[index]&&sameDraftValue(a[key],b[key]));}
function declareDraftToken(tokens,name,type,value,alias){const definition=alias?{name,type,alias}:{name,type,value};const existing=tokens.find(token=>token.name===name);if(existing){if(JSON.stringify(existing)!==JSON.stringify(definition))throw Error('Conflicting native token definition '+name);return;}tokens.push(definition);}
function intendedDraftRole(candidates,key,field){const matches=[];for(const candidate of candidates)for(const role of candidate.foundationBindings)if(role.bindings.some(target=>target.key===key&&target.field===field))matches.push({candidate,role});if(matches.length>1)throw Error('Ambiguous canonical target role '+key+'.'+field);return matches[0]||null;}
function draftFoundationName(candidate, name) {
  if (typeof name !== 'string' || !name) throw Error('Canonical foundation name required');
  if (/[.{}]/.test(name) || /[.{}]/.test(candidate.id)) {
    throw Error('Invalid Figma variable name for canonical foundation: ' + candidate.id + '/' + name + ' (periods and braces are forbidden)');
  }
  return name.startsWith(candidate.id + '/') ? name : candidate.id + '/' + name;
}
function declareDraftFoundations(candidate,add){
 const entries=candidate.foundationBindings;if(!Array.isArray(entries))throw Error('Normalized canonical foundation bindings required');const names=new Set();
 for(const entry of entries){
  const colorValue=entry.type==='COLOR'&&entry.value&&Object.keys(entry.value).every(key=>['r','g','b','a'].includes(key))&&['r','g','b'].every(key=>Number.isFinite(entry.value[key])&&entry.value[key]>=0&&entry.value[key]<=1)&&(entry.value.a===undefined||entry.value.a===1);
  if(!['STRING','FLOAT','COLOR'].includes(entry.type)||entry.type==='COLOR'&&!colorValue||entry.type==='STRING'&&(typeof entry.value!=='string'||!entry.value)||entry.type==='FLOAT'&&!Number.isFinite(entry.value)||!Array.isArray(entry.bindings)||!entry.bindings.length)throw Error('Explicit typed canonical foundation role required');
  const token=draftFoundationName(candidate,entry.token),alias=entry.alias?draftFoundationName(candidate,entry.alias):null;
  if(names.has(token))throw Error('Duplicate canonical foundation role '+token);names.add(token);if(alias===token)throw Error('Cyclic canonical foundation alias');
  for(const target of entry.bindings){if(typeof target.key!=='string'||!target.key||entry.type==='COLOR'&&(target.field!=='fills'||(target.paintIndex??0)!==0)||entry.type==='STRING'&&target.field!=='fontFamily'||entry.type==='FLOAT'&&!['fontSize','paddingLeft','paddingRight','paddingTop','paddingBottom','itemSpacing','cornerRadius','topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'].includes(target.field))throw Error('Supported explicit canonical target required');}
  const colorRole=entry.type==='COLOR'?candidate.graph?.design_foundations?.roles?.find(role=>role.kind==='color'&&role.token===entry.token):null;
  if(entry.type==='COLOR'&&!colorRole)throw Error('Authoritative graph color role required '+entry.token);
  const value=entry.type==='COLOR'?rgb(colorRole.value):entry.value;
  if(alias){add(alias,entry.type,value);add(token,entry.type,null,alias);}else add(token,entry.type,value);
 }
}
function applyDraftFoundations(page,candidates,jobs){const nodes=[page,...page.findAll(()=>true)],byKey=new Map(),claims=new Map(),actual=[];for(const node of nodes){const key=resolveInstanceSemanticKey(node)||node.getPluginData('semanticKey');if(key){if(!byKey.has(key))byKey.set(key,[]);byKey.get(key).push(node);}}for(const candidate of candidates)for(const entry of candidate.foundationBindings)for(const target of entry.bindings){const matches=byKey.get(target.key)||[];if(matches.length!==1)throw Error('Canonical target missing or ambiguous: '+target.key);const node=matches[0],token=draftFoundationName(candidate,entry.token),slot=node.id+':'+target.field;if(entry.type==='COLOR'){
 let source=node;const path=[];
 for(let current=node;current;current=current.parent){if(current.type==='INSTANCE'){const mapping=JSON.parse(current.getPluginData('semanticComponent')||'null'),matches=mapping?(byKey.get(mapping.sourceKey)||[]):[];if(matches.length===1){source=matches[0];for(const index of path)source=source?.children[index];}break;}if(current.parent)path.unshift(current.parent.children.indexOf(current));}
 if(!source||!jobs.some(job=>job.key===source.id&&job.field===target.field&&job.token===token))throw Error('Canonical color must retain its actual named source paint: '+target.key);
} if(claims.has(slot)&&claims.get(slot)!==token)throw Error('Conflicting canonical field roles: '+target.key+'.'+target.field);claims.set(slot,token);for(let i=jobs.length-1;i>=0;i--)if(jobs[i].key===node.id&&jobs[i].field===target.field)jobs.splice(i,1);jobs.push({key:node.id,field:target.field,token,...(target.paintIndex===undefined?{}:{paintIndex:target.paintIndex})});actual.push({... (target.paintIndex===undefined?{}:{paintIndex:target.paintIndex}),candidate:candidate.id,token,alias:entry.alias?draftFoundationName(candidate,entry.alias):null,type:entry.type,value:entry.value,key:target.key,nodeId:node.id,field:target.field});}return actual;}
function draftBoxOverlap(first, second) {
  const width = Math.max(0, Math.min(first.x + first.w, second.x + second.w) - Math.max(first.x, second.x));
  const height = Math.max(0, Math.min(first.y + first.h, second.y + second.h) - Math.max(first.y, second.y));
  return width * height / Math.min(first.w * first.h, second.w * second.h);
}

function draftTextGeometry(layer) {
  const spacing = layer.letter_spacing ?? 0;
  const invalidLines = layer.max_lines !== undefined && (!Number.isSafeInteger(layer.max_lines) || layer.max_lines < 1);
  const invalidLeading = layer.leading !== undefined && (!Number.isFinite(layer.leading) || layer.leading <= 0);
  if (!Number.isFinite(spacing) || invalidLines || invalidLeading) {
    throw Error('Invalid authored text letter_spacing/max_lines/leading ' + layer.id);
  }
  return spacing;
}

function draftShadows(shadows, where) {
  if (shadows === undefined) return [];
  if (!Array.isArray(shadows)) throw Error('Ordered native shadows array required: ' + where);
  const fields = ['x', 'y', 'blur', 'spread', 'color', 'opacity'];
  return shadows.map((shadow, index) => {
    const validFields = shadow && typeof shadow === 'object' && Object.keys(shadow).length === fields.length &&
      fields.every(field => Object.prototype.hasOwnProperty.call(shadow, field));
    const validNumbers = validFields && ['x', 'y', 'blur', 'spread', 'opacity'].every(field => Number.isFinite(shadow[field]));
    if (!validNumbers || shadow.blur < 0 || shadow.opacity < 0 || shadow.opacity > 1 ||
        typeof shadow.color !== 'string' || !/^#[0-9a-f]{6}$/i.test(shadow.color)) {
      throw Error('Finite native shadow x/y/blur/spread, six-digit color and opacity within [0,1] required: ' + where + '[' + index + ']');
    }
    return {
      type: 'DROP_SHADOW', offset: {x: shadow.x, y: shadow.y}, radius: shadow.blur, spread: shadow.spread,
      color: {...rgb(shadow.color), a: shadow.opacity}, visible: true, blendMode: 'NORMAL', showShadowBehindNode: true
    };
  });
}

function draftFlowStarts(candidates, frames) {
  return candidates.flatMap(candidate => ('entry_states' in candidate.prototype ? ['desktop', 'mobile'] : ['desktop']).flatMap(viewport =>
    (candidate.entry_states || [candidate.entry_state]).map(state => ({candidate, node: frames.get(candidate.id + '.' + viewport + '.' + state)}))));
}

function draftProductButtons(candidate, viewport, state) {
  const layout = candidate.state_layouts[viewport][state.id];
  const buttons = layout.product_buttons ?? {};
  if (!buttons || typeof buttons !== 'object' || Array.isArray(buttons)) {
    throw Error('State product_buttons must be an object');
  }
  return Object.entries(buttons).map(([id, button]) => {
    const duplicate = Object.prototype.hasOwnProperty.call(layout.control_boxes || {}, id) || layout.layers.some(layer => layer.id === id);
    if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(id) || duplicate) {
      throw Error('Unique safe product button id required ' + id);
    }
    const validBox = Array.isArray(button?.box) && button.box.length === 4 && button.box.every(Number.isFinite) && button.box[2] > 0 && button.box[3] > 0;
    const validVariant = typeof button?.variant === 'string' && Object.prototype.hasOwnProperty.call(candidate.control_styles?.[viewport] || {}, button.variant);
    const validLabel = typeof button?.label === 'string' && button.label.trim();
    if (!validBox || !validVariant || !validLabel) {
      throw Error('Product button box/variant/label required ' + id);
    }
    const referenced = Object.prototype.hasOwnProperty.call(button, 'specification_id');
    const specification = referenced ? candidate.specifications?.[button.specification_id] : undefined;
    const bound = referenced && candidate.prototype.bindings.some(edge => edge.action === button.specification_id || edge.control_id === id);
    if (referenced && (!specification || specification.kind !== 'action' || specification.screen_id !== state.screen || specification.meaning?.action !== button.specification_id || specification.target_id !== id || bound)) throw Error('Canonical unbound current-screen product button specification required ' + id);
    return {id, box: button.box, variant: button.variant, label: button.label, ...(specification ? {specification} : {})};
  });
}

function linkDraftLabel(set, main, key, phase) {
  const text = main.children.find(child => child.type === 'TEXT');
  if (!text) throw Error('Control variant has no label: ' + main.name);
  if (text.componentPropertyReferences?.characters === key) return;
  try {
    text.componentPropertyReferences = {...text.componentPropertyReferences, characters: key};
  } catch (error) {
    throw Error(`Cannot link owned label during ${phase}: ${set.id} / ${main.id} / ${text.id}, key ${key}, available ${JSON.stringify(Object.keys(set.componentPropertyDefinitions))}, current ${JSON.stringify(text.componentPropertyReferences)}, children ${JSON.stringify(main.children.map(child=>[child.type,child.name,child.componentPropertyReferences]))}, parent ${main.parent.id}: ${error}`);
  }
}

function setDraftControlLabel(instance, main, label, keysBySet) {
  const set = main.parent;
  let key = keysBySet.get(set.id);
  if (!key) throw Error('Control belongs to an unowned component set: ' + main.id);
  // Figma can drop a newly authored text-property link between async operations.
  if (!Object.prototype.hasOwnProperty.call(set.componentPropertyDefinitions, key)) {
    key = set.addComponentProperty('문구', 'TEXT', '검토 행동');
    keysBySet.set(set.id, key);
  }
  if (instance.componentProperties[key]?.type !== 'TEXT') linkDraftLabel(set, main, key, instance.name);
  instance.setProperties({[key]: label});
  if (instance.children.find(child => child.type === 'TEXT')?.characters !== label)
    throw Error('Assigned label differs from the visible text on ' + instance.name);
}

function draftControlIcon(style, assets, where) {
  if ('justifyContent' in style && !['center','space-between'].includes(style.justifyContent)) throw Error('Control justifyContent must be center or space-between: ' + where);
  const icon = style.icon;
  if (icon === undefined && style.justifyContent === 'space-between') throw Error('Control space-between requires a label and icon: ' + where);
  if (icon === undefined) return null;
  if (!icon || Object.keys(icon).sort().join(',') !== 'asset,gap,height,placement,width' ||
      typeof icon.asset !== 'string' || !Object.prototype.hasOwnProperty.call(assets || {}, icon.asset) ||
      !['before','after'].includes(icon.placement) || !['width','height','gap'].every(key => Number.isFinite(icon[key]) && (key === 'gap' ? icon[key] >= 0 : icon[key] > 0))) {
    throw Error('Pinned raster control icon with placement, width, height and gap required: ' + where);
  }
  return icon;
}
function addDraftControlIcon(main,key,style,image) {
  if(!style.icon)return;
  const spec=style.icon,part=image(main,key+'.icon',{x:0,y:0,w:spec.width,h:spec.height,asset:spec.asset,fit:'FIT'});
  part.setPluginData('controlIconAsset',spec.asset);
  part.layoutSizingHorizontal='FIXED';part.layoutSizingVertical='FIXED';
  if(spec.placement==='before')main.insertChild(0,part);
}
function draftControlChildKeys(main, key) {
  return main.children.map((child,index) => ({path:[index],key:key+'.'+(child.type === 'TEXT' ? 'label' : child.getPluginData?.('controlIconAsset') ? 'icon' : index)}));
}
function validateDraftControlIcon(parent, style, label, fail) {
  if(style && 'justifyContent' in style && parent?.primaryAxisAlignItems !== (style.justifyContent === 'space-between' ? 'SPACE_BETWEEN' : 'CENTER')) fail('native control primary axis alignment differs from explicit style');
  if(parent && style && 'justifyContent' in style) for(const field of ['paddingLeft','paddingRight','paddingTop','paddingBottom']) {
    const expected=field==='paddingLeft'||field==='paddingRight'?style.paddingX:style.paddingY;
    if(!Number.isFinite(parent[field]) || Math.abs(parent[field]-expected)>1) fail('native control padding differs from explicit style: '+field);
  }
  const icon = style?.icon;
  if (!icon) return null;
  if(!parent || !Array.isArray(parent.children)){fail('native icon-bearing reusable control missing');return null;}
  const images = parent.children.filter(child => child.getPluginData?.('controlIconAsset'));
  const image=images[0], box=draftNativeBox(image),labelBox=draftNativeBox(label);
  const expectedHash=figma.createImage(figma.base64Decode(DRAFT.assets[icon.asset])).hash;
  const fills=image?.fills;
  if(images.length!==1 || !box || image.type!=='RECTANGLE' || image.parent!==parent || image.visible===false || image.opacity!==1 ||
      image.getPluginData('controlIconAsset')!==icon.asset || !Array.isArray(fills) || fills.length!==1 || fills[0].type!=='IMAGE' ||
      fills[0].imageHash!==expectedHash || fills[0].scaleMode!=='FIT' || fills[0].visible===false || (fills[0].opacity??1)!==1 ||
      Math.abs(box.w-icon.width)>.01 || Math.abs(box.h-icon.height)>.01 || Math.abs(parent.itemSpacing-icon.gap)>.01) {
    fail('native control icon missing or differs from pinned raster/style',icon,box);return box;
  }
  if(label?.textAutoResize!=='WIDTH_AND_HEIGHT'||label?.layoutSizingHorizontal!=='HUG')fail('native icon label must inherit intrinsic HUG sizing from its main');
  if(labelBox){
    const gap=icon.placement==='before'?labelBox.x-box.x-box.w:box.x-labelBox.x-labelBox.w;
    const left=Math.min(box.x,labelBox.x),right=Math.max(box.x+box.w,labelBox.x+labelBox.w);
    const between=style.justifyContent==='space-between';
    if((between ? gap<icon.gap-1 : Math.abs(gap-icon.gap)>1) || Math.abs(box.y+box.h/2-parent.height/2)>1 ||
       (between ? Math.abs(left-parent.paddingLeft)>1 || Math.abs(right-(parent.width-parent.paddingRight))>1 : Math.abs((left+right)/2-parent.width/2)>1) ||
       between && (Math.abs(labelBox.y+labelBox.h/2-parent.height/2)>1 || labelBox.y<parent.paddingTop-1 || labelBox.y+labelBox.h>parent.height-parent.paddingBottom+1) || left<parent.paddingLeft-1 || right>parent.width-parent.paddingRight+1 ||
       box.y<parent.paddingTop-1 || box.y+box.h>parent.height-parent.paddingBottom+1) fail('native control icon/label group gap, centering or padding differs',icon,{box,labelBox});
  }
  return box;
}

function validateDraftPaletteLabel(instance,main,set,expectedLabel,fail) {
  const labels=instance?.children?.filter(child=>child.type==='TEXT')||[],label=labels[0];
  const mainLabel=main?.children?.find(child=>child.type==='TEXT');
  const property=mainLabel?.componentPropertyReferences?.characters;
  const actual=instance?.componentProperties?.[property];
  const reference=label?.componentPropertyReferences?.characters;
  if(instance?.type!=='INSTANCE'||main?.type!=='COMPONENT'||labels.length!==1||label?.characters!==expectedLabel||
     typeof property!=='string'||set?.componentPropertyDefinitions?.[property]?.type!=='TEXT'||actual?.type!=='TEXT'||actual.value!==expectedLabel||
     (reference!==undefined&&reference!==property))fail('native palette action label or exposed text property differs from authored action');
}
async function validateDraftPaletteControls(page,candidates) {
  const keyed=new Map(page.findAll(()=>true).map(node=>[node.getPluginData('semanticKey'),node]));
  for(const candidate of candidates)for(const sample of candidate.foundations?.palette?.samples||[]){
    const key='review.palette.'+candidate.id+'.'+sample.component,instance=keyed.get(key),expected=keyed.get(candidate.id+'.desktop.component.'+sample.variant);
    const main=instance?.type==='INSTANCE'?await instance.getMainComponentAsync():null;
    if(!main||main!==expected)throw Error('Native palette main differs from authored variant: '+key);
    validateDraftPaletteLabel(instance,main,main.parent,candidate.action_labels[sample.action],message=>{throw Error(key+': '+message);});
  }
}

function validateDraftControlFill(node,style,fail) {
  if(style && 'fill' in style && style.fill===null && (!Array.isArray(node?.fills)||node.fills.length!==0||node.boundVariables?.fills))fail('Explicit null control fill requires empty native fills and no fill variable');
}

function configureDraftControlLabel(label,main,style) {
  if(style.justifyContent==='space-between'){main.primaryAxisSizingMode='FIXED';main.resize(style.maxWidth,Math.max(main.height,style.minHeight));}
  label.textAlignHorizontal='CENTER';label.textAutoResize='WIDTH_AND_HEIGHT';
  if(style.icon){label.minWidth=null;label.maxWidth=null;label.layoutSizingHorizontal='HUG';}
  else label.maxWidth=main.maxWidth-main.paddingLeft-main.paddingRight;
}

function fitDraftControl(instance, box) {
  instance.primaryAxisSizingMode = 'FIXED';
  instance.counterAxisSizingMode = 'FIXED';
  instance.minWidth = box[2];
  instance.maxWidth = box[2];
  instance.minHeight = box[3];
  instance.maxHeight = box[3];
  instance.resize(box[2], box[3]);
  instance.x = box[0];
  instance.y = box[1];
  if(instance.children.some(child=>child.getPluginData?.('controlIconAsset')))return;
  for (const label of instance.children.filter(child => child.type === 'TEXT')) {
    label.textAlignHorizontal='CENTER';label.maxWidth=instance.width-instance.paddingLeft-instance.paddingRight;
    label.layoutSizingHorizontal='FILL';label.textAutoResize='HEIGHT';
  }
}

function draftNativeBox(node) {
  if (!node) return null;
  const box = {x: node.x, y: node.y, w: node.width, h: node.height};
  return Object.values(box).every(Number.isFinite) && box.w > 0 && box.h > 0 ? box : null;
}

function draftBoxInside(box, width, height) {
  return box.x >= -1 && box.y >= -1 && box.x + box.w <= width + 1 && box.y + box.h <= height + 1;
}

function draftTextWidth(layer) {
  // Figma quantizes text width; fractional single-line bounds can otherwise wrap by less than 1px.
  return layer.max_lines === 1 ? Math.ceil(layer.w) : layer.w;
}

function draftTextLeading(authored) {
  return authored.leading ?? Math.ceil(authored.size * (authored.font === 'display' ? 1.07 : 1.55));
}

function validateDraftTypography(node, authored, candidate, fail, resizeMode = 'HEIGHT') {
  const expectedFont = candidate.fonts?.[authored.font || 'body'];
  const actualFont = node.fontName;
  const fontMatches = expectedFont && typeof expectedFont.family === 'string' && typeof expectedFont.style === 'string' &&
    actualFont && typeof actualFont === 'object' &&
    actualFont.family === expectedFont.family && actualFont.style === expectedFont.style &&
    Object.entries(expectedFont.variationSettings || {}).every(([axis, value]) => actualFont.variationSettings?.[axis] === value);
  if (node.type !== 'TEXT' || typeof authored.value !== 'string' || node.characters !== authored.value || !fontMatches ||
      !Number.isFinite(authored.size) || authored.size <= 0 ||
      !Number.isFinite(node.fontSize) || Math.abs(node.fontSize - authored.size) > .001) {
    fail('native editable text/font differs from authored typography',
      {value: authored.value, font: expectedFont, size: authored.size},
      {value: node.characters, font: actualFont, size: node.fontSize});
  }
  const leading = draftTextLeading(authored);
  for (const [field, expected] of [['lineHeight', leading], ['letterSpacing', draftTextGeometry(authored)]]) {
    const observed = node[field];
    const pixels = observed?.unit === 'PIXELS' ? observed.value : observed?.unit === 'PERCENT' ? observed.value * authored.size / 100 : NaN;
    if (!Number.isFinite(expected) || !Number.isFinite(pixels) || Math.abs(pixels - expected) > .01) {
      fail('native ' + field + ' differs from authored ' + expected + 'px', expected, observed);
    }
  }
  if (node.textAlignHorizontal !== (authored.align || 'left').toUpperCase()) {
    fail('native text alignment differs from authored', (authored.align || 'left').toUpperCase(), node.textAlignHorizontal);
  }
  if (node.textAutoResize !== resizeMode || node.textTruncation && node.textTruncation !== 'DISABLED' || node.maxLines != null) {
    fail('native text must use authored auto-resize without clipping or truncation', {textAutoResize: resizeMode, textTruncation: 'DISABLED', maxLines: null},
      {textAutoResize: node.textAutoResize, textTruncation: node.textTruncation, maxLines: node.maxLines});
  }
  if (authored.max_lines !== undefined && (!Number.isFinite(node.height) || node.height > authored.max_lines * leading + 1)) {
    const lines = Math.max(1, Math.round(node.height / leading));
    fail('native text lines ' + lines + ' exceeds max_lines ' + authored.max_lines + ' (height ' + node.height + ', leading ' + leading + ')');
  }
  return leading;
}

function measureDraftNaturalWidth(node) {
  let probe, container;
  try {
    const font = node.fontName, leading = node.lineHeight, spacing = node.letterSpacing;
    if (!font || typeof font !== 'object' || typeof font.family !== 'string' || !font.family || typeof font.style !== 'string' || !font.style ||
        font.variationSettings !== undefined && (!font.variationSettings || typeof font.variationSettings !== 'object' || Array.isArray(font.variationSettings) || !Object.values(font.variationSettings).every(Number.isFinite)) ||
        !Number.isFinite(node.fontSize) || node.fontSize <= 0 || typeof node.characters !== 'string' ||
        !leading || typeof leading !== 'object' || !(leading.unit === 'AUTO' || ['PIXELS', 'PERCENT'].includes(leading.unit) && Number.isFinite(leading.value) && leading.value > 0) ||
        !spacing || typeof spacing !== 'object' || !['PIXELS', 'PERCENT'].includes(spacing.unit) || !Number.isFinite(spacing.value)) {
      throw Error('Uniform observed native text typography required for measurement');
    }
    container = figma.createFrame();
    container.name = 'Temporary text measurement';
    container.layoutMode = 'NONE';
    container.visible = false;
    probe = figma.createText();
    container.appendChild(probe);
    probe.fontName = copy(font);
    probe.fontSize = node.fontSize;
    probe.lineHeight = copy(leading);
    probe.letterSpacing = copy(spacing);
    probe.characters = node.characters;
    probe.textAutoResize = 'WIDTH_AND_HEIGHT';
    if (!Number.isFinite(probe.width) || probe.width <= 0 || !Number.isFinite(probe.height) || probe.height <= 0) {
      return {naturalWidth: null, naturalWidthError: 'Native width measurement was unavailable'};
    }
    return {naturalWidth: probe.width, naturalHeight: probe.height};
  } catch (error) {
    return {naturalWidth: null, naturalWidthError: String(error)};
  } finally {
    for (const temporary of [probe, container]) {
      if (!temporary) continue;
      try {
        temporary.remove();
      } catch (error) {
        status('Native measurement cleanup failed: ' + String(error));
      }
    }
  }
}

function validateDraftPlacement(node, expectedParent, fail) {
  if (!node) {
    fail('authored native node missing');
    return;
  }
  if (node.parent !== expectedParent) {
    fail('native parent differs from authored container', {parentId: expectedParent.id}, {parentId: node.parent?.id});
  }
  for (let ancestor = node; ancestor; ancestor = ancestor.parent) {
    if ('visible' in ancestor && ancestor.visible !== true ||
        'opacity' in ancestor && (!Number.isFinite(ancestor.opacity) || ancestor.opacity <= 0)) {
      fail('authored visible node is effectively hidden or transparent', {visible: true, opacity: 'positive'},
        {ancestorId: ancestor.id, visible: ancestor.visible, opacity: ancestor.opacity});
      break;
    }
  }
}

function validateDraftGeometry(page, candidates, measureWidths = true) {
  const keyed = new Map([page, ...page.findAll(() => true)].map(node => [node.getPluginData('semanticKey'), node]));
  const findings = [];
  const stateFrames = [];

  for (const candidate of candidates) {
    for (const viewport of ['desktop', 'mobile']) {
      for (const state of candidate.prototype.states) {
        const key = candidate.id + '.' + viewport + '.' + state.id;
        const layout = candidate.state_layouts[viewport][state.id];
        const frame = keyed.get(key);
        const frameBox = draftNativeBox(frame);
        const occupied = [];
        const fail = (id, message, authored, actual) => findings.push({layer: key + '.' + id, message, authored, actual});
        if (!frameBox || frame.type !== 'FRAME') {
          fail('frame', 'native state frame missing or non-finite');
          continue;
        }
        validateDraftPlacement(frame, page, (message, expected, observed) => fail('frame', message, expected, observed));
        stateFrames.push({key, box: frameBox});
        if (Math.abs(frame.width - layout.width) > 1 || Math.abs(frame.height - layout.height) > 1) {
          fail('frame', 'native frame differs from authored size', {w: layout.width, h: layout.height}, frameBox);
        }

        for (const layer of layout.layers) {
          const node = keyed.get(key + '.' + layer.id);
          const layerFail = (message, expected, observed) => fail(layer.id, message, expected, observed);
          validateDraftPlacement(node, frame, layerFail);
          const expectedType = layer.kind === 'text' ? 'TEXT' : layer.kind === 'ellipse' ? 'ELLIPSE' : 'RECTANGLE';
          if (node && node.type !== expectedType) {
            layerFail('native authored layer type differs', {type: expectedType}, {type: node.type});
          }
        }

        for (const layer of layout.layers.filter(layer => layer.kind === 'text')) {
          const node = keyed.get(key + '.' + layer.id);
          const box = draftNativeBox(node);
          if (!box || node.type !== 'TEXT') {
            fail(layer.id, 'native text missing or non-finite', {x: layer.x, y: layer.y, w: layer.w, h: layer.h},
              node ? {x: node.x, y: node.y, w: node.width, h: node.height, type: node.type} : null);
            continue;
          }
          const authoredRect = {x: layer.x, y: layer.y, w: layer.w, h: layer.h};
          const natural = measureWidths && box.h > layer.h + 1 && (layer.max_lines === 1 || layer.h <= draftTextLeading(layer) + 1) ? measureDraftNaturalWidth(node) : {};
          const textFail = (message, expected, observed) => fail(layer.id, message,
            {rect: authoredRect, ...(expected === undefined ? {} : {detail: expected})},
            {rect: box, ...natural, ...(observed === undefined ? {} : {detail: observed})});
          validateDraftTypography(node, layer, candidate, textFail);
          if (Math.abs(box.w - layer.w) > 1 || Math.abs(box.x - layer.x) > 1 || Math.abs(box.y - layer.y) > 1) {
            textFail('native fixed-width text geometry differs', {x: layer.x, y: layer.y, w: layer.w, h: layer.h}, box);
          }
          if (box.h > layer.h + 1) {
            textFail('native text height ' + box.h + ' exceeds authored budget ' + layer.h + ' at width ' + box.w, layer, box);
          }
          if (!draftBoxInside(box, frame.width, frame.height)) textFail('native text off-frame', layer, box);
          occupied.push({id: layer.id, kind: 'text', authored: layer, actual: box});
        }

        const productButtons = draftProductButtons(candidate, viewport, state);
        const controlSpecs = [
          ...Object.entries(layout.control_boxes || {}).map(([id, box]) => ({id, box})),
          ...productButtons
        ];
        for (const spec of controlSpecs) {
          const instance = keyed.get(key + '.' + spec.id);
          const actual = draftNativeBox(instance);
          const authored = {x: spec.box[0], y: spec.box[1], w: spec.box[2], h: spec.box[3]};
          const controlFail = (message, expected, observed) => fail(spec.id, message,
            {rect: authored, ...(expected === undefined ? {} : {detail: expected})},
            {rect: actual, ...(observed === undefined ? {} : {detail: observed})});
          if (!actual || instance.type !== 'INSTANCE') {
            controlFail('native control instance missing or non-finite');
            continue;
          }
          validateDraftPlacement(instance, frame, controlFail);
          if (Object.keys(actual).some(field => Math.abs(actual[field] - authored[field]) > 1)) {
            controlFail('native control differs from authored', authored, actual);
          }
          if (!draftBoxInside(actual, frame.width, frame.height)) controlFail('native control off-frame', authored, actual);
          const edge = candidate.prototype.bindings?.find(edge => edge.viewport === viewport && edge.source_state === state.id && edge.control_id === spec.id);
          const product = productButtons.find(button => button.id === spec.id);
          const variant = product?.variant ?? (edge ? candidate.action_notes?.[edge.action + '|' + edge.control_id]?.visual_variant : undefined);
          const style = candidate.control_styles?.[viewport]?.[variant];
          const expectedLabel = product?.label ?? (edge ? candidate.action_labels?.[edge.action] : undefined);
          const labels = instance.children.filter(child => child.type === 'TEXT' && typeof child.characters === 'string' && child.characters.trim());
          if (labels.length !== 1 || expectedLabel !== undefined && labels[0]?.characters !== expectedLabel) {
            controlFail('native control label missing or differs from authored text', expectedLabel, labels.map(label => label.characters));
          }
          if (product && ((product.specification && !Array.isArray(instance.reactions)) || instance.reactions?.length)) controlFail('passive product button must have zero reactions');
          const paddings = ['paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom'];
          if (!paddings.every(field => Number.isFinite(instance[field]) && instance[field] >= 0)) {
            controlFail('native control padding must be finite and non-negative');
            continue;
          }
          if (style) {
            validateDraftControlFill(instance,style,controlFail);
            if('justifyContent' in style && instance.primaryAxisAlignItems !== (style.justifyContent==='space-between'?'SPACE_BETWEEN':'CENTER')) controlFail('native control primary axis alignment differs from explicit style');
            for (const field of paddings) {
              const expected = field === 'paddingLeft' || field === 'paddingRight' ? style.paddingX : style.paddingY;
              if (!Number.isFinite(expected) || Math.abs(instance[field] - expected) > 1) {
                controlFail('native control padding differs from authored ' + field, expected, instance[field]);
              }
            }
          }
          const availableWidth = instance.width - instance.paddingLeft - instance.paddingRight;
          const availableHeight = instance.height - instance.paddingTop - instance.paddingBottom;
          for (const label of labels) {
            validateDraftPlacement(label, instance, controlFail);
            const labelBox = draftNativeBox(label);
            if (!labelBox) {
              controlFail('native control label geometry missing or non-finite');
              continue;
            }
            let leading = label.lineHeight?.unit === 'PIXELS' ? label.lineHeight.value : NaN;
            if (style) {
              leading = validateDraftTypography(label, {
                value: expectedLabel, size: style.fontSize, font: style.font || 'body', align: 'center',
                leading: style.leading, letter_spacing: style.letter_spacing, max_lines: 1
              }, candidate, controlFail, style.icon?'WIDTH_AND_HEIGHT':'HEIGHT');
            }
            if (!Number.isFinite(leading) || leading <= 0 || labelBox.h > leading + 1 || label.textAutoResize !== (style?.icon?'WIDTH_AND_HEIGHT':'HEIGHT') || style?.icon && label.layoutSizingHorizontal!=='HUG') {
              controlFail('native control label must occupy one unclipped line with authored auto-resize', {leading, maxLines: 1},
                {...labelBox, ...(measureWidths ? measureDraftNaturalWidth(label) : {})});
            }
            const inner = {...labelBox, x: labelBox.x - instance.paddingLeft, y: labelBox.y - instance.paddingTop};
            const padded = inner.x >= -1 && inner.y >= -1 && inner.x + inner.w <= availableWidth + 1 && inner.y + inner.h <= availableHeight + 1;
            const centered = label.textAlignHorizontal === 'CENTER' &&
              (style?.icon || Math.abs(inner.x + inner.w / 2 - availableWidth / 2) <= 1) &&
              Math.abs(inner.y + inner.h / 2 - availableHeight / 2) <= 1;
            if (!padded || !centered) {
              controlFail('native label exceeds padding or is not centered', {availableWidth, availableHeight}, inner);
            }
          }
          validateDraftControlIcon(instance,style,labels[0],controlFail);
          occupied.push({id: spec.id, kind: 'control', authored, actual});
        }

        for (let index = 0; index < occupied.length; index++) {
          for (const other of occupied.slice(index + 1)) {
            const first = occupied[index];
            const share = draftBoxOverlap(first.actual, other.actual);
            if (first.kind !== other.kind && share > 0) {
              const text = first.kind === 'text' ? first : other;
              const control = first.kind === 'control' ? first : other;
              fail(text.id, 'native screen text intersects whole control ' + control.id,
                {[text.id]: text.authored, [control.id]: control.authored},
                {[text.id]: text.actual, [control.id]: control.actual});
              continue;
            }
            if (share > .05 && (first.kind === 'text' || !(draftBoxOverlap(first.authored, other.authored) > .05))) {
              fail(other.id, 'unexpected native overlap with ' + first.id + ' (' + (share * 100).toFixed(2) + '% of smaller box)',
                {[first.id]: first.authored, [other.id]: other.authored}, {[first.id]: first.actual, [other.id]: other.actual});
            }
          }
        }
      }
    }
  }
  for (let index = 0; index < stateFrames.length; index++) {
    for (const other of stateFrames.slice(index + 1)) {
      if (draftBoxOverlap(stateFrames[index].box, other.box) > 0) {
        findings.push({layer: stateFrames[index].key, message: 'Native state frames overlap: ' + stateFrames[index].key + ' / ' + other.key,
          actual: [stateFrames[index].box, other.box]});
      }
    }
  }
  for(const candidate of candidates){
    for(const viewport of ['desktop','mobile'])for(const [variant,style]of Object.entries(candidate.control_styles?.[viewport]||{})){
      const key=candidate.id+'.'+viewport+'.component.'+variant,main=keyed.get(key);
      validateDraftControlFill(main,style,message=>findings.push({layer:key,message}));
      if(!style.icon)continue;
      validateDraftControlIcon(main,style,main?.children?.find(n=>n.type==='TEXT'),message=>findings.push({layer:key+'.icon',message}));
    }
    for(const sample of candidate.foundations?.palette?.samples||[]){
      const style=candidate.control_styles?.desktop?.[sample.variant];
      const key='review.palette.'+candidate.id+'.'+sample.component,instance=keyed.get(key);
      validateDraftControlFill(instance,style,message=>findings.push({layer:key,message}));
      if(!style?.icon)continue;
      validateDraftControlIcon(instance,style,instance?.children?.find(n=>n.type==='TEXT'),message=>findings.push({layer:key+'.icon',message}));
    }
  }
  if (findings.length) {
    const evidence = {
      schema: 'figma-flow-native-geometry-failure-v1', passed: false, scope: DRAFT.scope, production_admitted: SELECTED_PRODUCTION,
      pageId: page.id, observed_at: new Date().toISOString(), packet_sha256: DRAFT.packet_sha256,
      instance_sha256: DRAFT.instance_sha256, findings
    };
    figma.ui.postMessage({type: 'geometry-failure', data: copy(evidence)});
    const error = Error('Native draft geometry failed:\n- ' + findings.map(finding => finding.layer + ': ' + finding.message +
      (finding.actual === undefined ? '' : '; actual ' + JSON.stringify(finding.actual))).join('\n- '));
    error.geometryEvidence = evidence;
    throw error;
  }
}

function measureDraftText(page, candidates) {
  const keyed = new Map(page.findAll(() => true).map(node => [node.getPluginData('semanticKey'), node]));
  for (const candidate of candidates) {
    for (const viewport of ['desktop', 'mobile']) {
      for (const state of candidate.prototype.states) {
        for (const layer of candidate.state_layouts[viewport][state.id].layers.filter(layer => layer.kind === 'text')) {
          const node = keyed.get(candidate.id + '.' + viewport + '.' + state.id + '.' + layer.id);
          if (node) {
            node.textAutoResize = 'HEIGHT';
            node.resize(draftTextWidth(layer), node.height);
          }
        }
      }
    }
  }
}

function preflightDraft(draft,available){
 const problems=[],seen=new Set(),push=m=>{if(!seen.has(m)){seen.add(m);problems.push(m);}};
 const fonts=Array.isArray(available)?available:[];
 for(const c of draft.candidates||[]){
  for(const edge of c.prototype?.bindings||[])if(edge.source_state===edge.target_state)push('Native NAVIGATE requires a different target state: '+c.id+'.'+edge.viewport+'.'+edge.source_state);
  if (!c.fonts?.body) push('Required review annotation font role missing: '+c.id+'/body');
  for(const [role,font]of Object.entries(c.fonts||{})){
   if(!font||typeof font.family!=='string'||!font.family||typeof font.style!=='string'||!font.style){push('Font role invalid: '+c.id+'/'+role);continue;}
   if(!fonts.some(f=>f&&f.family===font.family&&f.style===font.style))push('필수 실제 글꼴 없음: '+font.family+' '+font.style);
  }
  for (const viewport of ['desktop', 'mobile']) {
    for (const [variant, style] of Object.entries(c.control_styles?.[viewport] || {})) {
      try {
        draftTextGeometry({...style, id: variant});
        draftShadows(style.shadows, c.id + '/' + viewport + '/' + variant);
        draftControlIcon(style,draft.assets,c.id+'/'+viewport+'/'+variant);
      } catch (error) {
        push(String(error));
      }
      if (!c.fonts?.[style.font || 'body']) push('Pinned control font role missing ' + c.id + '/' + variant);
      if (style.stroke !== undefined && (!Number.isFinite(style.stroke_width ?? 1) || (style.stroke_width ?? 1) <= 0)) {
        push('Invalid authored control leading/stroke ' + c.id + '/' + variant);
      }
    }
  }
  for(const viewport of ['desktop','mobile'])for(const state of c.prototype?.states||[]){
   const key=c.id+'.'+viewport+'.'+state.id,l=c.state_layouts?.[viewport]?.[state.id];
   if(!l){push('Pinned state layout missing '+key);continue;}
   try{draftProductButtons(c,viewport,state);}catch(error){push(String(error)+' at '+key);}
   for(const layer of l.layers||[]){
    if(layer.shadows!==undefined){try{if(!['rect','ellipse'].includes(layer.kind))throw Error('Native shadows require rect/ellipse '+layer.id);draftShadows(layer.shadows,key+'.'+layer.id);}catch(error){push(String(error));}}
    if(layer.kind==='image'&&!Object.prototype.hasOwnProperty.call(draft.assets||{},layer.asset))push('Pinned raster reference missing '+layer.asset+' at '+key+'.'+layer.id);
    if(layer.kind==='text'){try{draftTextGeometry(layer);}catch(error){push(String(error));}}
    if(layer.kind==='text'&&!c.fonts?.[layer.font||'body'])push('Pinned font role missing '+(layer.font||'body')+' at '+key+'.'+layer.id);
   }
   for(const edge of (c.prototype?.bindings||[]).filter(e=>e.viewport===viewport&&e.source_state===state.id)){
    const box=l.control_boxes?.[edge.control_id];
    if(!Array.isArray(box)||box.length!==4||!box.every(Number.isFinite)||box[2]<=0||box[3]<=0)push('Pinned canonical control position missing '+key+'.'+edge.control_id);
   }
  }
 }
 return problems;
}
function admitDraftColorConsumers(candidates){
 const reports=[];
 if(!Array.isArray(candidates)||!candidates.length)throw Error('Actual named color consumers: candidates required');
 for(const c of candidates){
  const roles=(c.foundations?.roles||[]).filter(role=>role.kind==='color'),graphRoles=c.graph?.design_foundations?.roles?.filter(role=>role.kind==='color'),declared=new Map(),consumers=new Map();
  if(!graphRoles||!sameDraftValue(graphRoles,roles))throw Error('Actual named color consumers: graph/source color roles differ '+c.id);
  for(const role of roles){
   const name=typeof role.token==='string'?role.token.split('/').pop():null,hex=c.colors?.[name];
   if(!name||declared.has(name)||typeof hex!=='string'||typeof role.value!=='string'||hex.toLowerCase()!==role.value.toLowerCase())throw Error('Actual named color consumers: ambiguous/mismatched source role '+c.id+'/'+name);
   rgb(hex);declared.set(name,role);consumers.set(name,[]);
  }
  if(!roles.length||!c.colors||Object.keys(c.colors).some(name=>!declared.has(name)))throw Error('Actual named color consumers: exact declared source colors required '+c.id);
  const known=(name,key)=>{if(!declared.has(name))throw Error('Actual named color consumers: undeclared paint '+c.id+'/'+name+' at '+key);};
  const use=(name,key,field)=>{
   known(name,key);
   consumers.get(name).push({key,field});
  };
  for(const viewport of ['desktop','mobile'])for(const [variant,style]of Object.entries(c.control_styles?.[viewport]||{})){if(!('fill' in style)||style.fill!==null)known(style.fill,c.id+'.'+viewport+'.component.'+variant);known(style.ink,c.id+'.'+viewport+'.component.'+variant+'.label');if(style.stroke!==undefined)known(style.stroke,c.id+'.'+viewport+'.component.'+variant+'.stroke');}
  const intersects=(box,l)=>box&&['x','y','w','h'].every(k=>Number.isFinite(box[k]))&&box.w>0&&box.h>0&&box.x<l.width&&box.y<l.height&&box.x+box.w>0&&box.y+box.h>0;
  if(!Array.isArray(c.prototype?.states)||!c.prototype.states.length||!Array.isArray(c.prototype.bindings))throw Error('Actual named color consumers: rendered prototype required '+c.id);
  for(const viewport of ['desktop','mobile'])for(const state of c.prototype.states){
   const l=c.state_layouts?.[viewport]?.[state.id],key=c.id+'.'+viewport+'.'+state.id;
   if(!l||!Number.isFinite(l.width)||l.width<=0||!Number.isFinite(l.height)||l.height<=0||!Array.isArray(l.layers))throw Error('Actual named color consumers: rendered state layout required '+key);
   use(l.bg,key,'fills');
   for(const layer of l.layers){
    const solid=layer.kind==='rect'||layer.kind==='ellipse';
    if(solid){known(layer.fill,key+'.'+layer.id);if(layer.stroke!==undefined)known(layer.stroke,key+'.'+layer.id+'.stroke');}else if(layer.kind==='text')known(layer.ink,key+'.'+layer.id);
    if(!intersects(layer,l))continue;
    if(solid){use(layer.fill,key+'.'+layer.id,'fills');if(layer.stroke!==undefined)use(layer.stroke,key+'.'+layer.id,'strokes');}
    else if(layer.kind==='text'&&typeof layer.value==='string'&&layer.value.trim()&&Number.isFinite(layer.size)&&layer.size>0)use(layer.ink,key+'.'+layer.id,'fills');
   }
   for(const edge of c.prototype.bindings.filter(edge=>edge.viewport===viewport&&edge.source_state===state.id)){
    const note=c.action_notes?.[edge.action+'|'+edge.control_id],style=c.control_styles?.[viewport]?.[note?.visual_variant],box=l.control_boxes?.[edge.control_id];
    if(!style||!Array.isArray(box)||box.length!==4||!box.every(Number.isFinite)||box[2]<=0||box[3]<=0)throw Error('Actual named color consumers: actual control/style required '+key+'.'+edge.control_id);
    if(!intersects({x:box[0],y:box[1],w:box[2],h:box[3]},l))continue;
    if(style.fill!==null)use(style.fill,key+'.'+edge.control_id,'fills');if(style.stroke!==undefined)use(style.stroke,key+'.'+edge.control_id,'strokes');
    if(typeof c.action_labels?.[edge.action]==='string'&&c.action_labels[edge.action].trim())use(style.ink,key+'.'+edge.control_id+'.label','fills');
   }
  }
  for (const viewport of ['desktop', 'mobile']) {
    for (const state of c.prototype.states) {
      const layout = c.state_layouts[viewport][state.id];
      const key = c.id + '.' + viewport + '.' + state.id;
      for (const button of draftProductButtons(c, viewport, state)) {
        const style = c.control_styles[viewport][button.variant];
        if (!intersects({x: button.box[0], y: button.box[1], w: button.box[2], h: button.box[3]}, layout)) continue;
        if(style.fill!==null)use(style.fill, key + '.' + button.id, 'fills');
        use(style.ink, key + '.' + button.id + '.label', 'fills');
        if (style.stroke !== undefined) use(style.stroke, key + '.' + button.id, 'strokes');
      }
    }
  }
  for(const row of c.foundationBindings||[])if(row.type==='COLOR'&&!roles.some(role=>role.token===row.token&&role.native?.type==='COLOR'))throw Error('Actual named color consumers: undeclared typed COLOR '+row.token);
  for(const [name,uses]of consumers){
   if(!uses.length)throw Error('Actual named color consumers: unused role '+c.id+'/'+name);
   const role=declared.get(name),rows=(c.foundationBindings||[]).filter(row=>row.token===role.token);
   if(role.native!==undefined){
    const native=role.native,expected=rgb(c.colors[name]);
    if(!native||native.type!=='COLOR'||!native.value||Object.keys(native.value).some(key=>!['r','g','b','a'].includes(key))||['r','g','b'].some(key=>!Number.isFinite(native.value[key])||native.value[key]<0||native.value[key]>1||Math.abs(native.value[key]-expected[key])>0.0000001)||(native.value.a!==undefined&&native.value.a!==1)||!Array.isArray(native.bindings)||!native.bindings.length)throw Error('Actual named color consumers: typed COLOR differs from graph/source '+role.token);
    if(rows.length!==1||rows[0].type!=='COLOR'||!sameDraftValue(rows[0].value,native.value)||!sameDraftValue(rows[0].bindings,native.bindings)||(rows[0].alias||null)!==(role.alias||null))throw Error('Actual named color consumers: normalized COLOR differs from graph '+role.token);
    for(const target of native.bindings)if(target.field!=='fills'||(target.paintIndex??0)!==0||!uses.some(use=>use.key===target.key&&use.field===target.field))throw Error('Actual named color consumers: COLOR target is not its named source paint '+target.key);
   }else if(rows.length)throw Error('Actual named color consumers: undeclared typed COLOR '+role.token);
   reports.push({candidate:c.id,token:role.token,consumers:uses});
  }
 }
 return reports;
}
async function makeDraft(){if(DRAFT.fileKey&&figma.fileKey!==DRAFT.fileKey)throw Error('이 검토 패킷에 지정된 Figma 파일에서만 실행할 수 있습니다.');if(SELECTED_PRODUCTION){const source=DRAFT.sourceSelection,hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);if(DRAFT.scope!=='selected-production'||DRAFT.production_admitted!==true||DRAFT.candidates.length!==1||!source||!hash(source.sha256)||!hash(source.candidate_sha256)||!hash(source.review_layout_sha256)||!hash(DRAFT.change_request?.sha256)||!hash(DRAFT.production_graph?.sha256)||DRAFT.candidates[0].id!==source.candidate_id||DRAFT.candidate_pins[source.candidate_id]!==source.candidate_sha256)throw Error('Exact selected-production scope and selection/source pins required');}else if(DRAFT.schema!=='figma-flow-native-direction-review-v1'||DRAFT.scope!=='exploratory-only'||('production_admitted'in DRAFT&&DRAFT.production_admitted!==false))throw Error('Explicit exploratory review packet required; production admission is forbidden');admitDraftColorConsumers(DRAFT.candidates);const planned=[];for(const candidate of DRAFT.candidates){declareDraftFoundations(candidate,(...args)=>declareDraftToken(planned,...args));for(const role of candidate.foundations.roles.filter(role=>role.kind==='color')){const token=draftFoundationName(candidate,role.token),alias=role.alias?draftFoundationName(candidate,role.alias):null,value=rgb(candidate.colors[role.token.split('/').pop()]);if(alias){declareDraftToken(planned,alias,'COLOR',value);declareDraftToken(planned,token,'COLOR',null,alias);}else declareDraftToken(planned,token,'COLOR',value);}}const availableFonts=(await figma.listAvailableFontsAsync()).map(f=>f.fontName);const problems=preflightDraft(DRAFT,availableFonts);if(problems.length)throw Error('검토 초안을 만들기 전에 확인이 필요합니다 (파일은 변경되지 않았습니다):\n- '+problems.join('\n- '));const previous=figma.currentPage;let page= null,tokenResult,createdPage=false;const styles=[],rollbacks=[];try{page=await findInterruptedDraftReview();if(page){await validateDraftPaletteControls(page,DRAFT.candidates);validateDraftGeometry(page,DRAFT.candidates,false);await figma.setCurrentPageAsync(page);return page;}page=figma.createPage();createdPage=true;page.name=(SELECTED_PRODUCTION?'PRODUCTION · '+DRAFT.candidates[0].title:(DRAFT.candidates.length===1?'DRAFT · '+DRAFT.candidates[0].title:'DRAFT · A/B/C 방향 검토'))+' · '+DRAFT.packet_sha256.slice(0,8);page.setPluginData(RESERVATION,JSON.stringify({state:'preparing',identity:draftReviewIdentity()}));await figma.setCurrentPageAsync(page);
 const tokens=[],bindings=[],notes=[],colors=new Map(),numbers=new Map(),assets=new Map(),styleMap=new Map(),mains=new Map(),labelKeys=new Map(),frames=new Map(),edges=[],palettes={},noteFrames={},gradientBindings=[];
 const add=(...args)=>declareDraftToken(tokens,...args);
 for(const candidate of DRAFT.candidates)declareDraftFoundations(candidate,add);
 const ensureDraftTokens=(api,ownedPage,contract)=>ensureSemanticTokens(api,ownedPage,{...contract,strictValues:true,bindTextStyles:true,ownedTextStyleIds:styles.map(style=>style.id)});
 const num=(name,value)=>declareDraftNumber(tokens,name,value);
 const bind=(n,field,token)=>bindings.push({key:n.id,field,token});
 const color=(c,name)=>{const hex=c.colors[name],roles=c.foundations.roles.filter(role=>role.kind==='color'&&role.token.split('/').pop()===name);if(!hex||roles.length!==1)throw Error('Unambiguous declared source color role required: '+c.id+'/'+name);const role=roles[0],token=draftFoundationName(c,role.token),alias=role.alias?draftFoundationName(c,role.alias):null;if(alias){add(alias,'COLOR',rgb(hex));add(token,'COLOR',null,alias);}else add(token,'COLOR',rgb(hex));return {token,paint:{type:'SOLID',color:rgb(hex)}};};
 const paint=(n,c,name,field='fills')=>{const p=color(c,name);n[field]=[p.paint];bind(n,field,p.token);};
 const shape=(n,parent,key,x,y,w,h)=>{parent.appendChild(n);tag(n,key);n.resize(w,h);n.x=x;n.y=y;return n;};
 const fontNames=new Map();for(const c of DRAFT.candidates)for(const font of Object.values(c.fonts))fontNames.set(font.family+'/'+font.style,font);const available=availableFonts;for(const font of fontNames.values()){if(!available.some(f=>f.family===font.family&&f.style===font.style))throw Error('필수 실제 글꼴 없음: '+font.family+' '+font.style);await figma.loadFontAsync(font);}
 for(const [name,data]of Object.entries(DRAFT.assets))assets.set(name,figma.createImage(figma.base64Decode(data)).hash);
 const gradient=(parent,key,l)=>{const n=shape(figma.createRectangle(),parent,key,l.x,l.y,l.w,l.h);const stops=l.stops.map((stop,i)=>{const name=key.replace(/[.:]/g,'/')+'/gradient/stop-'+i;add(name+'/primitive','COLOR',{...rgb(stop.color),a:stop.opacity});add(name,'COLOR',null,name+'/primitive');gradientBindings.push({node:n,index:i,token:name});return {position:stop.position,color:{...rgb(stop.color),a:stop.opacity}};});n.fills=[{type:'GRADIENT_LINEAR',gradientTransform:l.direction==='horizontal'?[[1,0,0],[0,1,0]]:[[0,1,0],[-1,0,1]],gradientStops:stops}];return n;};
 const image=(parent,key,l)=>{const n=shape(figma.createRectangle(),parent,key,l.x,l.y,l.w,l.h);if(!assets.has(l.asset))throw Error('Pinned raster reference missing '+l.asset);n.fills=[{type:'IMAGE',imageHash:assets.get(l.asset),scaleMode:l.fit||'FIT'}];n.setPluginData('rasterAsset',l.asset);return n;};
 const text=async(parent,key,l,c)=>{const font=c.fonts[l.font||'body'];if(!font)throw Error('Pinned font role missing');const spacing=draftTextGeometry(l),leading=l.leading??Math.ceil(l.size*(l.font==='display'?1.07:1.55));const styleRoles=c.foundationBindings.filter(role=>role.bindings.some(target=>target.key===key&&['fontFamily','fontSize'].includes(target.field))).map(role=>draftFoundationName(c,role.token)).sort();const styleKey=JSON.stringify([c.id,l.font||'body',l.size,leading,spacing,font,styleRoles]);let style=styleMap.get(styleKey);if(!style){style=figma.createTextStyle();styles.push(style);style.name=(SELECTED_PRODUCTION?'PRODUCTION ':'DRAFT ')+DRAFT.instance_sha256.slice(0,8)+'/'+c.id+'/'+(l.font||'body')+'/'+l.size+' · '+leading;style.fontName=font;style.fontSize=l.size;style.lineHeight={unit:'PIXELS',value:leading};style.letterSpacing={unit:'PIXELS',value:spacing};styleMap.set(styleKey,style);}const n=figma.createText();parent.appendChild(n);tag(n,key);await n.setTextStyleIdAsync(style.id);n.characters=l.value;n.textAlignHorizontal=(l.align||'left').toUpperCase();n.resize(draftTextWidth(l),l.h);n.textAutoResize='HEIGHT';n.x=l.x;n.y=l.y;paint(n,c,l.ink);const intendedSize=intendedDraftRole([c],key,'fontSize');bind(n,'fontSize',intendedSize?draftFoundationName(c,intendedSize.role.token):num(c.id+'/type/'+(l.font||'body')+'/'+l.size,l.size));return n;};
 const layoutBindings=n=>{for(const field of ['paddingTop','paddingRight','paddingBottom','paddingLeft','itemSpacing']){const intended=intendedDraftRole(DRAFT.candidates,n.getPluginData('semanticKey'),field);if(intended)bind(n,field,draftFoundationName(intended.candidate,intended.role.token));else if(n[field]>0)bind(n,field,num('review/space/'+n[field],n[field]));}};
 const library=figma.createFrame();page.appendChild(library);tag(library,'review.component-library');library.fills=[];library.x=0;library.y=-1400;
 for(const c of DRAFT.candidates){for(const [name,hex]of Object.entries(c.colors))color(c,name);for(const viewport of ['desktop','mobile']){const variants=[];for(const [visual,style]of Object.entries(c.control_styles[viewport])){const key=c.id+'.'+viewport+'.component.'+visual,n=figma.createComponent();library.appendChild(n);tag(n,key);n.name='Visual='+visual;n.layoutMode='HORIZONTAL';n.primaryAxisSizingMode='AUTO';n.counterAxisSizingMode='AUTO';n.paddingTop=n.paddingBottom=style.paddingY;n.paddingLeft=n.paddingRight=style.paddingX;n.minHeight=style.minHeight;n.maxWidth=style.maxWidth;n.itemSpacing=style.icon?.gap??0;n.primaryAxisAlignItems=style.justifyContent==='space-between'?'SPACE_BETWEEN':'CENTER';n.counterAxisAlignItems='CENTER';layoutBindings(n);const fill=style.fill,ink=style.ink;if(fill===null)n.fills=[];else paint(n,c,fill);if(style.shadows!==undefined)n.effects=draftShadows(style.shadows,key);if(style.stroke!==undefined){paint(n,c,style.stroke,'strokes');n.strokeWeight=style.stroke_width??1;n.strokeAlign='INSIDE';}n.cornerRadius=style.radius;const intendedRadius=intendedDraftRole([c],key,'cornerRadius');if(intendedRadius)bind(n,'cornerRadius',draftFoundationName(c,intendedRadius.role.token));else if(n.cornerRadius>0)bind(n,'cornerRadius',num(c.id+'/radius/observed/'+n.cornerRadius,n.cornerRadius));const label=await text(n,key+'.label',{x:0,y:0,w:240,h:28,size:style.fontSize,value:(note=>note?c.action_labels[note.action]:visual)(Object.values(c.action_notes).find(note=>note.visual_variant===visual)),ink,font:style.font||'body',letter_spacing:style.letter_spacing,leading:style.leading},c);configureDraftControlLabel(label,n,style);addDraftControlIcon(n,key,style,image);mains.set(c.id+'.'+viewport+'.'+visual,n);variants.push(n);}for(const main of variants){const style=c.control_styles[viewport][main.name.slice('Visual='.length)];validateDraftControlIcon(main,style,main.children.find(n=>n.type==='TEXT'),(message,icon,geometry)=>{throw Error(main.getPluginData('semanticKey')+': '+message+' '+JSON.stringify(geometry||{}));});}const set=figma.combineAsVariants(variants,library);tag(set,c.id+'.'+viewport+'.component-set');set.name=c.title+' · '+viewport+' · 시각 역할';set.fills=[];set.strokes=[];const property=set.addComponentProperty('문구','TEXT','검토 행동');labelKeys.set(set.id,property);for(const main of variants)linkDraftLabel(set,main,property,'create');}
 }
 layoutFoundationSets(library,library.children.filter(n=>n.type==='COMPONENT_SET'));for(const n of [library,...library.findAll(n=>n.type==='COMPONENT_SET')])layoutBindings(n);library.y=-library.height-160;
 const control = (frame, key, main, label, box) => {
  if (!main) throw Error('Source visual role has no real native main');
  const instance = main.createInstance();
  frame.appendChild(instance);
  tag(instance, key);
  setDraftControlLabel(instance, main, label, labelKeys);
  fitDraftControl(instance, box);
  instance.setPluginData('semanticComponent', JSON.stringify({
    key,
    sourceKey: main.getPluginData('semanticKey'),
    childKeys: draftControlChildKeys(main,key)
  }));
  return instance;
 };
 let cy=0;for(const c of DRAFT.candidates){const sourceNotes=new Map(c.notes.map(n=>[n.id,n]));let rowY=cy;for(const viewport of ['desktop','mobile']){const dimensions=c.state_layouts[viewport];let x=0;for(const state of c.prototype.states){const l=dimensions[state.id];if(!l)throw Error('Pinned state layout missing');const key=c.id+'.'+viewport+'.'+state.id,frame=shape(figma.createFrame(),page,key,x,rowY,l.width,l.height);frame.name=c.title+' · '+viewport+' · '+state.title+' · '+(SELECTED_PRODUCTION?'PRODUCTION':'DRAFT');frame.clipsContent=true;paint(frame,c,l.bg);frames.set(key,frame);frame.setPluginData('canonicalState',state.id);notes.push(draftAnnotation(c,key,sourceNotes.get(state.screen)));for(const layer of l.layers){if(layer.kind==='image'||layer.kind==='gradient'){const n=(layer.kind==='image'?image:gradient)(frame,key+'.'+layer.id,layer);if(layer.opacity!==undefined)n.opacity=layer.opacity;}else if(layer.kind==='rect'||layer.kind==='ellipse'){const n=shape(layer.kind==='rect'?figma.createRectangle():figma.createEllipse(),frame,key+'.'+layer.id,layer.x,layer.y,layer.w,layer.h);paint(n,c,layer.fill);if(layer.shadows!==undefined)n.effects=draftShadows(layer.shadows,key+'.'+layer.id);if(layer.stroke!==undefined){paint(n,c,layer.stroke,'strokes');n.strokeWeight=layer.stroke_width;n.strokeAlign='INSIDE';}if(layer.kind==='rect'&&layer.radius>0){n.cornerRadius=layer.radius;bind(n,'cornerRadius',num(c.id+'/radius/observed/'+layer.radius,layer.radius));}if(layer.opacity!==undefined)n.opacity=layer.opacity;}else if(layer.kind==='text')await text(frame,key+'.'+layer.id,layer,c);else throw Error('Only declared native draft layer kinds allowed');}
 for(const edge of c.prototype.bindings.filter(e=>e.viewport===viewport&&e.source_state===state.id)){const box=l.control_boxes[edge.control_id];if(!box)throw Error('Pinned canonical control position missing '+edge.control_id);const note=c.action_notes[edge.action+'|'+edge.control_id];const main=mains.get(c.id+'.'+viewport+'.'+note.visual_variant);const n=control(frame,key+'.'+edge.control_id,main,c.action_labels[edge.action],box);notes.push(draftAnnotation(c,key+'.'+edge.control_id,note));edges.push({node:n,target:c.id+'.'+viewport+'.'+edge.target_state});}
 for(const button of draftProductButtons(c,viewport,state)){control(frame,key+'.'+button.id,mains.get(c.id+'.'+viewport+'.'+button.variant),button.label,button.box);if(button.specification)notes.push({key:c.id+'.'+viewport+'.'+state.id+'.'+button.id,label:button.specification.title+'\n'+button.specification.display_text,specification:button.specification});}
 x+=l.width+90;}
 const reference=c.references[viewport];if(reference){const dims=c.layouts[viewport];const ref=shape(figma.createFrame(),page,c.id+'.'+viewport+'.raster-reference',x,rowY,dims.width,dims.height);ref.name=c.title+' · 브라우저 참조 원본 (래스터)';ref.fills=[];image(ref,c.id+'.'+viewport+'.reference-image',{asset:reference,x:0,y:0,w:dims.width,h:dims.height,fit:'FIT'});}rowY+=Math.max(c.layouts[viewport].height,...Object.values(dimensions).map(layout=>layout.height))+170;}
 cy=rowY+650;
 }
 for(const edge of edges){const target=frames.get(edge.target);if(!target)throw Error('Exact candidate destination missing');await edge.node.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:target.id,navigation:'NAVIGATE',transition:null,preserveScrollPosition:false}]}]);}
 // Shared helper creates real visible cards, instances and labeled functional roles.
 const labelToken=num('review/type/palette',17),spaceToken=num('review/space/24',24);for(const c of DRAFT.candidates){const primary=c.control_styles.desktop[c.foundations.palette.samples[0].variant];const ink=color(c,primary.ink);const samples=c.foundations.palette.samples.map(sample=>({...sample,mainComponentId:mains.get(c.id+'.desktop.'+sample.variant).id}));const palette=await createFoundationPalette(figma,page,{sourceHash:DRAFT.instance_sha256,collectionName:(SELECTED_PRODUCTION?'Selected production ':'Direction review ')+DRAFT.instance_sha256.slice(0,10),tokens,type:{token:labelToken,value:17},space:{token:spaceToken,value:24},ink:{token:ink.token,value:ink.paint.color},font:c.fonts.body,samples,configureSample:(instance,main,sample)=>setDraftControlLabel(instance,main,c.action_labels[sample.action],labelKeys),name:c.title+' · 의미 있는 컴포넌트 팔레트',x:0,y:cy},ensureDraftTokens);rollbacks.push(palette.rollback);palettes[c.id]={libraryId:palette.libraryId,samples:palette.samples};for(const sample of palette.samples){const instance=await figma.getNodeByIdAsync(sample.instanceId),main=await instance.getMainComponentAsync(),key='review.palette.'+c.id+'.'+sample.component;instance.setPluginData('semanticKey',key);instance.setPluginData('semanticComponent',JSON.stringify({key,sourceKey:main.getPluginData('semanticKey'),childKeys:draftControlChildKeys(main,key)}));if (main.id !== sample.mainComponentId) throw Error('Palette linked to '+main.id+' instead of '+sample.mainComponentId);
    const edge=c.prototype.bindings.find(e=>e.action===sample.action&&e.viewport==='desktop');if(edge){const target=frames.get(c.id+'.desktop.'+edge.target_state);await instance.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:target.id,navigation:'NAVIGATE',transition:null,preserveScrollPosition:false}]}]);}}const node=await figma.getNodeByIdAsync(palette.libraryId);if(primary.fill===null)node.fills=[];else paint(node,c,primary.fill);cy+=node.height+160;}
 for(const c of DRAFT.candidates){const entries=[];for(const viewport of ['desktop','mobile']){for(const state of c.prototype.states){const target=frames.get(c.id+'.'+viewport+'.'+state.id),note=c.notes.find(n=>n.id===state.screen);entries.push(draftBoardEntry(c,viewport+'|'+state.id+'|'+note.id,target.id,note,viewport+' · '+state.title+' · '+state.screen+'\n'+noteLabel(note)));for(const button of draftProductButtons(c,viewport,state)){if(button.specification){const product=page.findOne(n=>n.getPluginData('semanticKey')===c.id+'.'+viewport+'.'+state.id+'.'+button.id);entries.push({key:viewport+'|'+state.id+'|'+button.id,targetId:product.id,specification:button.specification});}}}for(const edge of c.prototype.bindings.filter(e=>e.viewport===viewport)){const key=c.id+'.'+viewport+'.'+edge.source_state+'.'+edge.control_id,target=page.findOne(n=>n.getPluginData('semanticKey')===key),note=c.action_notes[edge.action+'|'+edge.control_id];entries.push(draftBoardEntry(c,viewport+'|'+edge.source_state+'|'+edge.control_id,target.id,note,viewport+' · '+edge.control_id+' · '+edge.action+'\n'+noteLabel(note)));}}const board=await ensureDesignNoteBoard(figma,page,{...(c.specifications?{presentation:'readable-specs'}:{}),sourceHash:DRAFT.instance_sha256,font:c.fonts.body,fontSize:17,width:760,x:0,y:cy,title:'주석 읽기 · '+c.title,boardKey:'review.notes.'+c.id,notes:entries});rollbacks.push(board.rollback);noteFrames[c.id]={...board,rollback:undefined};const node=await figma.getNodeByIdAsync(board.boardId),style=c.control_styles.desktop[c.foundations.palette.samples[0].variant];if(style.fill===null)node.fills=[];else paint(node,c,style.fill);for(const part of [node,...node.findAll(()=>true)]){if(part.type==='TEXT'){paint(part,c,style.ink);bind(part,'fontSize',num('review/type/note/'+part.fontSize,part.fontSize));}if(part.layoutMode&&part.layoutMode!=='NONE')layoutBindings(part);}cy+=node.height+160;}
 const canonicalBindings=applyDraftFoundations(page,DRAFT.candidates,bindings);tokenResult=await ensureDraftTokens(figma,page,{sourceHash:DRAFT.instance_sha256,collectionName:(SELECTED_PRODUCTION?'Selected production ':'Direction review ')+DRAFT.instance_sha256.slice(0,10),tokens,bindings});for(const job of gradientBindings){const fills=copy(job.node.fills),stop=fills[0].gradientStops[job.index];stop.boundVariables={color:figma.variables.createVariableAlias(tokenResult.variables[job.token])};job.node.fills=fills;}measureDraftText(page,DRAFT.candidates);await validateDraftPaletteControls(page,DRAFT.candidates);validateDraftGeometry(page,DRAFT.candidates);const readable=notes.some(note=>note.specification);if(readable){for(const note of notes){if(!note.specification)throw Error('Mixed legacy/readable annotation package');const target=page.findOne(node=>node.getPluginData('semanticKey')===note.key),matches=Object.values(noteFrames).flatMap(board=>board.entries.filter(entry=>entry.targetId===target?.id).map(entry=>({board,entry})));if(matches.length!==1)throw Error('Exact readable board binding required: '+note.key);const {board,entry}=matches[0];note.board={boardId:board.boardId,textNodeId:entry.textNodeId,key:entry.key};}}const annotationResult=await ensureNativeAnnotations(figma,page,{...(readable?{presentation:'readable-specs',sourceHash:DRAFT.instance_sha256}:{}),annotations:notes});rollbacks.push(annotationResult.rollback);page.setPluginData('packet_sha256',DRAFT.packet_sha256);writeDraftJSON(page,'draftCanonicalBindings',canonicalBindings);writeDraftJSON(page,'draftNoteFrames',noteFrames);writeDraftJSON(page,'draftPalettes',palettes);writeDraftJSON(page,'draftTextStyles',styles.map(s=>s.id));page.setPluginData('scope',DRAFT.scope);page.setPluginData('productionAdmitted',String(SELECTED_PRODUCTION));if(SELECTED_PRODUCTION)writeDraftJSON(page,'selectedProductionSource',{sourceSelection:DRAFT.sourceSelection,production_graph:DRAFT.production_graph,change_request:DRAFT.change_request});const launch=draftFlowStarts(DRAFT.candidates,frames);page.flowStartingPoints=launch.map(({candidate,node})=>({nodeId:node.id,name:candidate.title+' · '+node.name+(SELECTED_PRODUCTION?' · 원정 시작':' · 검토 시작')}));figma.currentPage.selection=[launch[0].node];figma.viewport.scrollAndZoomIntoView(launch.map(item=>item.node));page.setPluginData(OWNER,DRAFT.instance_sha256);page.setPluginData(RESERVATION,JSON.stringify({state:'complete',identity:draftReviewIdentity()}));return page;
 }catch(error){const failures=[];if(createdPage){if(tokenResult)try{await tokenResult.rollback();}catch(e){failures.push(String(e));}for(const rollback of rollbacks.reverse())try{await rollback();}catch(e){failures.push(String(e));}for(const style of styles)try{style.remove();}catch(e){failures.push(String(e));}try{await figma.setCurrentPageAsync(previous);page.remove();}catch(e){failures.push(String(e));}}throw Error(String(error)+(failures.length?' · 정리 오류: '+failures.join('; '):''));}}
async function readDraft(page){const raw=await readNativeSemantics(figma,page),objects=new Map([page,...page.findAll(()=>true)].map(n=>[n.id,n]));for(const row of raw.nodes){const n=objects.get(row.id);for(const field of ['x','y','width','height','characters','fontName','fontSize','lineHeight','letterSpacing','textAutoResize','textAlignHorizontal','textStyleId','visible','constraints','cornerRadius','strokeWeight','opacity','effects','layoutMode','primaryAxisAlignItems','primaryAxisSizingMode','counterAxisSizingMode','paddingTop','paddingRight','paddingBottom','paddingLeft','itemSpacing','componentPropertyReferences'])if(field in n&&typeof n[field]!=='symbol')row[field]=copy(n[field]);if(n.type==='INSTANCE'&&'overrides'in n)row.overrides=copy(n.overrides);if(n.type==='TEXT'&&n.characters.length){if(typeof n.getRangeBoundVariable==='function'){const family=n.getRangeBoundVariable(0,n.characters.length,'fontFamily');row.fontFamilyBinding=typeof family==='symbol'?null:copy(family);}row.fontSegments=copy(n.getStyledTextSegments(['fontName','fontSize','textStyleId','boundVariables']));const link=n.getRangeHyperlink(0,n.characters.length);row.hyperlink=typeof link==='symbol'?null:copy(link);}if(n.getPluginData('controlIconAsset')){const paints=n.fills;if(Array.isArray(paints)&&paints.length===1&&paints[0].type==='IMAGE'&&paints[0].imageHash){const observed=figma.getImageByHash(paints[0].imageHash);if(observed)row.iconImageBytes=figma.base64Encode(await observed.getBytesAsync());}row.controlIconAsset=n.getPluginData('controlIconAsset');}if(typeof n.getReactions==='function')row.reactions=copy(await n.getReactions());else if('reactions'in n&&Array.isArray(n.reactions))row.reactions=copy(n.reactions);}
 const textStyles=[];for(const id of readDraftJSON(page,'draftTextStyles',[])){const style=await figma.getStyleByIdAsync(id);if(style)textStyles.push({id:style.id,name:style.name,fontName:copy(style.fontName),fontSize:style.fontSize,lineHeight:copy(style.lineHeight),boundVariables:copy(style.boundVariables||{})});}return {...raw,fileKey:figma.fileKey,page_owner:page.getPluginData(OWNER),packet_sha256:DRAFT.packet_sha256,instance_sha256:DRAFT.instance_sha256,layout_sha256:DRAFT.layout_sha256,layout_pin:DRAFT.layout_pin,prepared_target:DRAFT.prepared_target,expected_file_key:DRAFT.fileKey,candidate_pins:DRAFT.candidate_pins,schema:SELECTED_PRODUCTION?FLOW_PRODUCTION_READBACK:'figma-flow-native-direction-readback-v1',scope:page.getPluginData('scope'),production_admitted:page.getPluginData('productionAdmitted')==='true',...(SELECTED_PRODUCTION?readDraftJSON(page,'selectedProductionSource',{}):{}),observed_at:new Date().toISOString(),canonicalFoundationBindings:readDraftJSON(page,'draftCanonicalBindings',[]),noteFrames:readDraftJSON(page,'draftNoteFrames',{}),palettes:readDraftJSON(page,'draftPalettes',{}),textStyles,raster_vs_editable:DRAFT.boundary,flowStartingPoints:copy(page.flowStartingPoints||[])};}
figma.showUI(__html__,{width:470,height:650,themeColors:true});figma.ui.onmessage=async message=>{if(message.type==='receipt'){status(message.passed?'실제 Figma 검토 시안·이동·주석·팔레트 검증 완료 · 방향 선택은 별도입니다.':'검토 자료 검증 실패 · 결과 JSON을 확인하세요.',message.passed?'success':'error');return;}if(message.type!=='draft-review'||busy)return;busy=true;status('실제 검토 프레임·글꼴·주석·팔레트를 만드는 중…','busy');try{const page=await makeDraft();lastData=await readDraft(page);figma.ui.postMessage({type:'readback',data:lastData});status('실제 검토 노드 생성 완료 · 읽기 결과를 준비했습니다.','success');}catch(error){status(String(error)+'\n'+String(error.stack||''),'error');}finally{busy=false;status(last);}};
