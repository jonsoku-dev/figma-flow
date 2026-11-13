/* Data-only native mutation. The canonical graph is never read or changed here. */
const nativeEditFields = new Set(['fontSize','fontFamily','paddingLeft','paddingRight','backgroundColor','color','borderRadius']);
const nativeEditClone = value => JSON.parse(JSON.stringify(value));
function nativeEditEqual(a,b) {
  if(a&&b&&['r','g','b'].every(key=>typeof a[key]==='number'&&typeof b[key]==='number')&&[a,b].every(value=>Object.keys(value).every(key=>['r','g','b','a'].includes(key))))return ['r','g','b','a'].every(key=>Math.abs((a[key]??1)-(b[key]??1))<0.000001);
  if(typeof a==='number'&&typeof b==='number')return Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<0.000001;
  if(a&&b&&typeof a==='object'&&typeof b==='object'){
    const left=Object.keys(a).sort(),right=Object.keys(b).sort();return JSON.stringify(left)===JSON.stringify(right)&&left.every(key=>nativeEditEqual(a[key],b[key]));
  }
  return a===b;
}
function nativeEditScope(figma,plan) {
  if(figma.fileKey!==plan.file_key||figma.currentPage?.id!==plan.page_id)throw Error('Wrong native edit file or page');
}
function nativeEditOwner(node,plan,mainId) {
  let main=null,page=null;
  for(let current=node;current;current=current.parent){
    if(current.type==='INSTANCE')throw Error('Native edit cannot mutate instance overrides');
    if(current.type==='COMPONENT'){
      if(main)throw Error('Nested component targets are not admitted');
      main=current;
    }
    if(current.type==='PAGE'){page=current;break;}
  }
  if(page?.id!==plan.page_id||!main||main.remote===true||main.id!==(mainId||node.id))throw Error('Declared local main/component ancestry required');
  return main;
}
function nativeEditValue(node,field) {
  if(field==='backgroundColor'||field==='color'){
    const fills=node.fills;
    if(!Array.isArray(fills)||fills.length!==1||fills[0].type!=='SOLID'||fills[0].visible===false)throw Error('Single visible SOLID native fill required');
    return {...fills[0].color,a:fills[0].opacity??1};
  }
  if(field==='fontFamily'){
    if(!node.fontName||typeof node.fontName==='symbol'||typeof node.fontName.family!=='string')throw Error('Uniform existing native font required');
    return node.fontName.family;
  }
  const value=node[field==='borderRadius'?'cornerRadius':field];
  if(typeof value!=='number'||!Number.isFinite(value))throw Error('Finite uniform native property required');
  if(field==='borderRadius'&&['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'].some(key=>node[key]!==value))throw Error('Uniform native corners required');
  return value;
}
const nativeEditFontFields=['fontName','fontSize','textDecoration','letterSpacing','lineHeight','paragraphIndent','paragraphSpacing','leadingTrim','listSpacing','textCase'];
const nativeEditTextBindings=['fontFamily','fontSize','fontStyle','fontWeight','letterSpacing','lineHeight','paragraphSpacing','paragraphIndent'];
function nativeEditRaw(job) {
  if(job.variable)return nativeEditClone(job.variable.valuesByMode[job.edit.mode_id]);
  const node=job.node,field=job.edit.field;
  if(field==='backgroundColor'||field==='color'){
    if(node.fillStyleId!==undefined&&(typeof node.fillStyleId!=='string'||node.fillStyleId!==''))throw Error('Style-backed or mixed native fill cannot be edited');
    return {fills:nativeEditClone(node.fills),fillStyleId:node.fillStyleId??''};
  }
  if(field.startsWith('font')){
    if(typeof node.textStyleId!=='string')throw Error('Uniform text style identity required');
    const profile={},bindings={};
    for(const key of nativeEditFontFields)if(key in node){if(typeof node[key]==='symbol'||node[key]===undefined)throw Error('Mixed or unavailable typography cannot be edited');profile[key]=nativeEditClone(node[key]);}
    for(const key of nativeEditTextBindings){const binding=node.getRangeBoundVariable(0,node.characters.length,key);if(typeof binding==='symbol')throw Error('Mixed typography binding cannot be edited');if(binding)bindings[key]=nativeEditClone(binding);}
    return {styleId:node.textStyleId||'',profile,bindings};
  }
  const keys=field==='borderRadius'?(node.boundVariables?.cornerRadius?['cornerRadius']:['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius']):[field];
  return {value:nativeEditValue(node,field),bindings:Object.fromEntries(keys.map(key=>[key,nativeEditClone(node.boundVariables?.[key]||null)]))};
}
function nativeEditValid(value,field) {
  if(field==='fontFamily')return typeof value==='string'&&value.trim()===value&&value.length>0&&value.length<=200&&!/[,;:{}\\"'<>/\u0000-\u001f]/.test(value);
  if(field==='backgroundColor'||field==='color')return value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).every(key=>['r','g','b','a'].includes(key))&&['r','g','b'].every(key=>typeof value[key]==='number'&&Number.isFinite(value[key])&&value[key]>=0&&value[key]<=1)&&(value.a??1)===1;
  return typeof value==='number'&&Number.isFinite(value)&&value>=0&&(field!=='fontSize'||value>0);
}
function nativeEditValidatePlan(plan) {
  if(plan?.schema!==NATIVE_EDIT_PLAN_SCHEMA||typeof plan.file_key!=='string'||typeof plan.page_id!=='string')throw Error('Explicit scoped native edit plan required');
  if(plan.provision){nativeProvisionValidate(plan);return;}
  if(plan.web_design){webValidate(plan);return;}
  if(plan.specifications){nativeSpecificationValidate(plan);return;}
  if(plan.graph_review){graphReviewValidate(plan);return;}
  const variable=plan.variableedit,edits=plan.edits;
  if(Boolean(variable)===Boolean(edits))throw Error('Choose node edits or one existing variable edit');
  if(variable){if(!variable.variable_id||!variable.mode_id||!('before'in variable)||!('after'in variable))throw Error('Exact existing variable/mode and values required');return;}
  if(!Array.isArray(edits)||!edits.length||edits.length>32)throw Error('Bounded declared edits required');
  const seen=new Set(),fontNodes=new Set();
  for(const edit of edits){
    const key=edit.node_id+'|'+edit.field,text=['fontSize','fontFamily','color'].includes(edit.field);
    if(!edit.node_id||!nativeEditFields.has(edit.field)||seen.has(key)||text!==Boolean(edit.main_id)||!nativeEditValid(edit.before,edit.field)||!nativeEditValid(edit.after,edit.field))throw Error('Unsupported, duplicate or invalid native edit');
    seen.add(key);if(edit.field.startsWith('font')){if(fontNodes.has(edit.node_id))throw Error('Only one font edit per text node per transaction');fontNodes.add(edit.node_id);}
  }
}
async function nativeEditDiscovery(figma,plan) {
  nativeEditScope(figma,plan);
  const page=await figma.getNodeByIdAsync(plan.page_id);
  if(page?.type!=='PAGE')throw Error('Declared native page missing');
  if (plan.web_design?.readback_scope === 'screens') {
    const requested = new Set(plan.web_design.screens.map(screen => plan.web_design.graph_id + '/' + screen.id));
    const nodes = [];
    for (const root of page.children) {
      const screenKey = root.getPluginData(WEB_DESIGN_KEY);
      if (!requested.has(screenKey)) continue;
      for (const node of [root, ...root.findAll(() => true)]) {
        const fills = Array.isArray(node.fills) ? node.fills : [];
        nodes.push({
          id: node.id, parentId: node.parent.id, screenKey, type: node.type,
          elementId: node.getPluginData(WEB_ELEMENT_ID), width: node.width, height: node.height,
          fillTypes: fills.map(fill => fill.type),
          effectTypes: (node.effects || []).map(effect => effect.type),
          isMask: node.isMask === true,
        });
      }
    }
    nativeEditScope(figma, plan);
    return {schema: 'figma-flow-web-screen-discovery-v1', fileKey: figma.fileKey, pageId: page.id,
      graph_sha256: plan.web_design.graph_sha256, readback_scope: 'screens',
      nodes, observed_at: new Date().toISOString()};
  }
  const result=requireFullNativeRead(await readNativeSemantics(figma,page));
  const objects=new Map([page,...page.findAll(()=>true)].map(node=>[node.id,node]));
  for(const row of result.nodes){const node=objects.get(row.id);if(typeof node.strokeWeight==='number')row.strokeWeight=node.strokeWeight;
    if(node.type==='TEXT'&&node.characters.length){const families=[...new Set(node.getRangeAllFontNames(0,node.characters.length).map(font=>font.family))];if(families.length===1)row.nativeFontFamily=families[0];const bound=node.getRangeBoundVariable(0,node.characters.length,'fontFamily');if(typeof bound==='symbol')throw Error('Mixed native family binding');row.boundVariables={...row.boundVariables,fontFamily:bound||undefined};}}
  const collections=[];
  for(const collection of result.collections){const native=await figma.variables.getVariableCollectionByIdAsync(collection.id);collections.push({...collection,owner:JSON.parse(native.getPluginData('bloomSemanticTokens')||'null')});}
  nativeEditScope(figma,plan);
  return {...result,schema:'figma-flow-graph-native-discovery-v1',fileKey:figma.fileKey,pageId:page.id,allowed_page_ids:[page.id],collections,graphSSOT:JSON.parse(page.getPluginData('graphSSOT')||'null'),observed_at:new Date().toISOString()};
}
function nativeEditPageBindings(page) {
  const ids=new Set();
  const aliases=value=>{
    if(!value||typeof value!=='object')return;
    if(value.type==='VARIABLE_ALIAS'){
      if(typeof value.id!=='string'||!value.id)throw Error('Invalid actual page variable alias');
      ids.add(value.id);
    }else for(const child of Object.values(value))aliases(child);
  };
  for(const node of [page,...page.findAll(()=>true)]){
    let owner=node;while(owner&&owner.type!=='PAGE')owner=owner.parent;
    if(owner?.id!==page.id)throw Error('Variable consumer is outside the admitted page');
    aliases(node.boundVariables);
    for(const field of ['fills','strokes','effects'])if(Array.isArray(node[field]))aliases(node[field]);
    if(node.type==='TEXT'&&node.characters.length){
      if(typeof node.getRangeBoundVariable==='function')for(const field of nativeEditTextBindings)aliases(node.getRangeBoundVariable(0,node.characters.length,field));
      if(typeof node.getStyledTextSegments==='function')for(const segment of node.getStyledTextSegments(['boundVariables','fills'])){aliases(segment.boundVariables);aliases(segment.fills);}
    }
  }
  return ids;
}
async function nativeEditVariableScope(figma,page,target) {
  const variables=new Map(),pending=[...nativeEditPageBindings(page)];
  const referenced=value=>{
    if(!value||typeof value!=='object')return [];
    if(value.type==='VARIABLE_ALIAS')return [value.id];
    return Object.values(value).flatMap(referenced);
  };
  while(pending.length){
    const id=pending.pop();if(variables.has(id))continue;
    const variable=await figma.variables.getVariableByIdAsync(id);
    if(!variable)throw Error('Actual page binding variable is unavailable');
    variables.set(id,variable);pending.push(...referenced(variable.valuesByMode));
  }
  return ()=>{
    const used=new Set(),todo=[...nativeEditPageBindings(page)];
    while(todo.length){
      const id=todo.pop();if(used.has(id))continue;
      const variable=variables.get(id);if(!variable)throw Error('Actual page variable binding scope changed during preflight');
      used.add(id);todo.push(...referenced(variable.valuesByMode));
    }
    if(!used.has(target))throw Error('Variable is not used by an actual binding on the admitted page');
  };
}
async function nativeEditStage(figma,plan) {
  nativeEditValidatePlan(plan);nativeEditScope(figma,plan);
  const jobs=[];
  if(plan.variableedit){
    const edit=plan.variableedit;await nativeEditDiscovery(figma,plan);
    const checkBindingScope=await nativeEditVariableScope(figma,figma.currentPage,edit.variable_id);
    checkBindingScope();
    const variable=await figma.variables.getVariableByIdAsync(edit.variable_id);
    const collection=variable&&await figma.variables.getVariableCollectionByIdAsync(variable.variableCollectionId);
    if(!variable||variable.remote||!collection?.modes.some(mode=>mode.modeId===edit.mode_id)||!Object.prototype.hasOwnProperty.call(variable.valuesByMode,edit.mode_id))throw Error('Existing local variable and collection mode required');
    const field=variable.resolvedType==='COLOR'?'backgroundColor':variable.resolvedType==='STRING'?'fontFamily':variable.resolvedType==='FLOAT'?'paddingLeft':null;
    if(!field||!nativeEditValid(edit.before,field)||!nativeEditValid(edit.after,field))throw Error('Unsupported typed variable value');
    jobs.push({edit,variable,checkBindingScope,before:nativeEditRaw({edit,variable})});
  }else{
    for(const edit of plan.edits){
      const node=await figma.getNodeByIdAsync(edit.node_id);
      if(!node)throw Error('Declared native node missing: '+edit.node_id);
      nativeEditOwner(node,plan,edit.main_id);
      if(edit.main_id?node.type!=='TEXT':node.type!=='COMPONENT')throw Error('Only a declared local main or its explicitly scoped TEXT target is editable');
      const job={edit,node,bindingVariables:new Map()};job.before=nativeEditRaw(job);
      const bindings=job.before.bindings||{};
      for(const binding of Object.values(bindings))if(binding){if(binding.type!=='VARIABLE_ALIAS'||typeof binding.id!=='string')throw Error('Uniform existing variable alias required');const variable=await figma.variables.getVariableByIdAsync(binding.id);if(!variable)throw Error('Existing binding variable missing');job.bindingVariables.set(binding.id,variable);}
      if(edit.field.startsWith('font')){
        if(job.before.styleId){
          job.sourceStyle=await figma.getStyleByIdAsync(job.before.styleId);
          if(job.sourceStyle?.type!=='TEXT')throw Error('Existing source text style unavailable');
          job.styleBefore={profile:Object.fromEntries(Object.keys(job.before.profile).map(key=>[key,nativeEditClone(job.sourceStyle[key])])),bindings:nativeEditClone(job.sourceStyle.boundVariables||{})};
        }
        if(typeof node.fontName!=='object')throw Error('Uniform source font required');
        const available=(await figma.listAvailableFontsAsync()).map(font=>font.fontName);
        const fonts=[node.fontName,...node.getRangeAllFontNames(0,node.characters.length)];
        if(edit.field==='fontFamily'){job.afterFont={family:edit.after,style:node.fontName.style};fonts.push(job.afterFont);}
        for(const font of fonts){if(!available.some(item=>item.family===font.family&&item.style===font.style))throw Error('Required existing native font unavailable: '+font.family+' '+font.style);await figma.loadFontAsync(font);}
      }
      jobs.push(job);
    }
  }
  nativeEditScope(figma,plan);
  for(const job of jobs){job.checkBindingScope?.();if(job.node)nativeEditOwner(job.node,plan,job.edit.main_id);const observed=job.variable?job.variable.valuesByMode[job.edit.mode_id]:nativeEditValue(job.node,job.edit.field);if(!nativeEditEqual(observed,job.edit.before)||!nativeEditEqual(nativeEditRaw(job),job.before))throw Error('Native before-value drift after preflight awaits');job.observedBefore=nativeEditClone(observed);if(job.sourceStyle){const live={profile:Object.fromEntries(Object.keys(job.before.profile).map(key=>[key,nativeEditClone(job.sourceStyle[key])])),bindings:nativeEditClone(job.sourceStyle.boundVariables||{})};if(!nativeEditEqual(live,job.styleBefore))throw Error('Source text style changed during preflight');}}
  return jobs;
}
function nativeEditWrite(job) {
  const {edit,node,variable}=job;
  if(variable){variable.setValueForMode(edit.mode_id,nativeEditClone(edit.after));return;}
  if(edit.field==='backgroundColor'||edit.field==='color'){
    const paint=nativeEditClone(node.fills[0]),{a=1,...color}=edit.after;
    if(paint.boundVariables){delete paint.boundVariables.color;if(!Object.keys(paint.boundVariables).length)delete paint.boundVariables;}
    node.fills=[{...paint,color,opacity:a}];return;
  }
  if(edit.field.startsWith('font')){
    node.setRangeBoundVariable(0,node.characters.length,edit.field,null);
    if(edit.field==='fontFamily')node.fontName=job.afterFont;else node.fontSize=edit.after;return;
  }
  for(const key of Object.keys(job.before.bindings))node.setBoundVariable(key,null);
  node[edit.field==='borderRadius'?'cornerRadius':edit.field]=edit.after;
}
async function nativeEditRestore(job,figma,plan) {
  const {node,variable,edit,before}=job;
  if(variable){variable.setValueForMode(edit.mode_id,nativeEditClone(before));return;}
  if(before.fills){node.fills=nativeEditClone(before.fills);return;}
  if(edit.field.startsWith('font')){
    if(node.textStyleId!==before.styleId){if(!before.styleId)throw Error('Cannot safely restore a detached source text style');await node.setTextStyleIdAsync(before.styleId);if(figma.fileKey!==plan.file_key)throw Error('File changed during rollback await');nativeEditOwner(node,plan,edit.main_id);const assigned=nativeEditRaw(job);if(!nativeEditEqual(assigned.profile,job.styleBefore.profile)||!nativeEditEqual(assigned.bindings,job.styleBefore.bindings)||assigned.styleId!==before.styleId)throw Error('Source style changed during rollback await');}
    for(const [key,value]of Object.entries(before.profile))node[key]=nativeEditClone(value);
    for(const key of nativeEditTextBindings)node.setRangeBoundVariable(0,node.characters.length,key,before.bindings[key]?job.bindingVariables.get(before.bindings[key].id):null);
  }else{node[edit.field==='borderRadius'?'cornerRadius':edit.field]=before.value;for(const[key,binding]of Object.entries(before.bindings))node.setBoundVariable(key,binding?job.bindingVariables.get(binding.id):null);}
}
function nativeEditConflict(job, reason) {
  let observed = null;
  try { observed = job.variable ? nativeEditClone(job.variable.valuesByMode[job.edit.mode_id]) : nativeEditValue(job.node, job.edit.field); }
  catch (_) {}
  return {node_id:job.edit.node_id,variable_id:job.edit.variable_id,field:job.edit.field,before:job.edit.before,after:job.edit.after,observed,reason,plan_sha256:NATIVE_EDIT_SHA256};
}
async function runNativeEdit(figma,plan,operation='apply') {
  nativeEditValidatePlan(plan);nativeEditScope(figma,plan);
  if(plan.provision)return nativeProvisionRun(figma,plan,operation);
  if (plan.web_design) {
    if (operation === 'read') {
      const readback = await nativeEditDiscovery(figma, plan);
      return {
        ...readback,
        web_design: await webRead(figma, plan),
        native_edit: { plan_sha256: NATIVE_EDIT_SHA256, applied: false, operation: 'read' },
      };
    }
    if (operation !== 'apply') throw Error('Unsupported web design operation');
    const result = await webApply(figma, plan);
    return {
      ...result.readback,
      web_design: result.receipt,
      native_edit: {
        plan_sha256: NATIVE_EDIT_SHA256,
        applied: true,
        operation: 'apply',
        changed: result.receipt.screens.some(screen => !screen.reused),
      },
    };
  }
  if(plan.graph_review){
    if(operation==='read'){
      const review=graphReviewRead(figma,plan),readback=await nativeEditDiscovery(figma,plan);
      return {...readback,graph_review:review,native_edit:{plan_sha256:NATIVE_EDIT_SHA256,applied:false,operation:'read'}};
    }
    if(operation==='apply')try{
      const review=await graphReviewApply(figma,plan),readback=await nativeEditDiscovery(figma,plan);
      return {...readback,graph_review:review,native_edit:{plan_sha256:NATIVE_EDIT_SHA256,applied:true,operation:'apply',changed:!review.unchanged}};
    }catch(error){
      let existing=null;try{existing=graphReviewRead(figma,plan);}catch(_){}
      error.readback={schema:'figma-flow-graph-review-v1',status:error.rollback_conflicts?.length?'rollback-conflict':'rolled-back',operation:'apply',graph_id:plan.graph_review.projection.id,existing_board:existing,error:String(error.message||error),rollback_conflicts:error.rollback_conflicts||[]};
      throw error;
    }
    throw Error('Unsupported graph review operation');
  }
  if(operation==='read'){const readback=await nativeEditDiscovery(figma,plan);return {...readback,native_edit:{plan_sha256:NATIVE_EDIT_SHA256,applied:false,operation:'read'}};}
  if(operation!=='apply')throw Error('Unsupported native edit operation');
  if(plan.specifications){
    let result;
    try{result=await nativeSpecificationApply(figma,plan);const readback=await nativeEditDiscovery(figma,plan);result.assertAfter();return {...readback,native_edit:{plan_sha256:NATIVE_EDIT_SHA256,applied:true,operation:'apply',changed:result.changed}};}
    catch(error){
      try{await result?.rollback?.();}catch(rollback){error.rollback_conflicts=[...(error.rollback_conflicts||[]),String(rollback.message||rollback)];}
      if(!error.readback)try{error.readback=await nativeEditDiscovery(figma,plan);error.readback.native_edit={plan_sha256:NATIVE_EDIT_SHA256,applied:false,operation:'apply'};error.readback.specification_error=String(error.message||error);error.readback.rollback_conflicts=error.rollback_conflicts||[];}catch(discovery){error.specification_error=String(discovery.message||discovery);}
      throw error;
    }
  }
  const jobs=await nativeEditStage(figma,plan),written=[];
  try{
    for(const job of jobs){nativeEditScope(figma,plan);job.checkBindingScope?.();if(job.node)nativeEditOwner(job.node,plan,job.edit.main_id);if(!nativeEditEqual(nativeEditRaw(job),job.before))throw Error('Native edit target drifted before mutation');written.push(job);try{nativeEditWrite(job);}finally{job.written=nativeEditRaw(job);}const actual=job.variable?job.variable.valuesByMode[job.edit.mode_id]:nativeEditValue(job.node,job.edit.field);if(!nativeEditEqual(actual,job.edit.after))throw Error('Native setter getter differs from requested value');}
    const readback=await nativeEditDiscovery(figma,plan);
    for(const job of written)if(!nativeEditEqual(nativeEditRaw(job),job.written))throw Error('Native target changed during actual discovery');
    return {...readback,native_edit:{plan_sha256:NATIVE_EDIT_SHA256,applied:true,operation:'apply',operations:jobs.map(job=>({...job.edit,before_observed:job.observedBefore,after_observed:job.variable?nativeEditClone(job.variable.valuesByMode[job.edit.mode_id]):nativeEditValue(job.node,job.edit.field)}))}};
  }catch(error){
    const conflicts=[];
    for(const job of written.reverse())try{if(job.node)nativeEditOwner(job.node,plan,job.edit.main_id);if(figma.fileKey!==plan.file_key||!nativeEditEqual(nativeEditRaw(job),job.written)){conflicts.push(nativeEditConflict(job,'Changed externally; not overwritten'));continue;}await nativeEditRestore(job,figma,plan);if(!nativeEditEqual(nativeEditRaw(job),job.before))throw Error('Restored getters differ');}catch(rollback){conflicts.push(nativeEditConflict(job,String(rollback.message||rollback)));}
    error.rollback_conflicts=conflicts;error.readback={schema:'figma-flow-native-edit-receipt-v1',status:conflicts.length?'rollback-conflict':'rolled-back',fileKey:figma.fileKey,pageId:figma.currentPage?.id,native_edit:{plan_sha256:NATIVE_EDIT_SHA256,applied:false,operation:'apply',operations:written.map(job=>{let observed;try{observed=job.variable?nativeEditClone(job.variable.valuesByMode[job.edit.mode_id]):nativeEditValue(job.node,job.edit.field);}catch(_){observed=null;}return{node_id:job.edit.node_id,field:job.edit.field,variable_id:job.edit.variable_id,mode_id:job.edit.mode_id,observed};})},error:String(error.message||error),rollback_conflicts:conflicts};throw error;
  }
}
if(typeof NATIVE_EDIT_PLAN!=='undefined'&&typeof figma!=='undefined'){
  figma.showUI(__html__,{width:520,height:640,themeColors:true});let nativeEditBusy=false;
  figma.ui.onmessage=async message=>{
    if(nativeEditBusy||!['read','apply'].includes(message?.type)||message.session!==NATIVE_EDIT_SESSION)return;
    nativeEditBusy=true;figma.ui.postMessage({session:NATIVE_EDIT_SESSION,state:'busy',operation:message.type});
    try{figma.ui.postMessage({session:NATIVE_EDIT_SESSION,operation:message.type,readback:await runNativeEdit(figma,NATIVE_EDIT_PLAN,message.type)});}
    catch(error){figma.ui.postMessage({session:NATIVE_EDIT_SESSION,operation:message.type,error:String(error.message||error),readback:error.readback||{schema:'figma-flow-native-edit-receipt-v1',status:'failed',fileKey:figma.fileKey,pageId:figma.currentPage?.id,error:String(error.message||error)},rollback_conflicts:error.rollback_conflicts||[]});}
    finally{nativeEditBusy=false;}
  };
}
