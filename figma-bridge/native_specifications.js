/* Existing-document specification update; no graph or caller code is evaluated. */
function nativeSpecificationValidate(plan) {
  const value=plan.specifications,keys=object=>Object.keys(object||{}).sort().join('|');
  if(keys(plan)!=='file_key|page_id|schema|specifications'||keys(value)!=='board|source_graph|targets'||!Array.isArray(value.targets)||value.targets.length<1||value.targets.length>32)throw Error('Exact bounded specification plan required');
  if(keys(value.board)!=='entries|font|key|node_id|owner'||!Array.isArray(value.board.entries)||!value.board.entries.length||value.board.owner?.pageId!==plan.page_id)throw Error('Exact existing board snapshot required');
  const seen=new Set();
  for(const row of value.targets){
    if(keys(row)!=='after|before|legacy_annotations|legacy_proof|node_id|semantic_key'||seen.has(row.node_id)||!row.semantic_key||row.after?.schema!==FLOW_SPEC.schemas.readable||!row.after.meaning||!row.after.trace||!row.after.display_text||!row.after.title||row.after.source_graph_sha256!==value.source_graph?.sha256||keys(row.before)!=='annotations|specification'||!Array.isArray(row.before.annotations)||!Array.isArray(row.legacy_annotations))throw Error('Invalid specification target or source pin');
    if(row.legacy_proof!==null&&(keys(row.legacy_proof)!=='annotation_mode|legacy_body|page_source_sha256|semantic_id|target_name'||row.legacy_proof.annotation_mode!=='native'||row.legacy_proof.semantic_id!==row.semantic_key||row.legacy_proof.page_source_sha256!==value.board.owner.sourceHash||typeof row.legacy_proof.target_name!=='string'||!row.legacy_proof.target_name||typeof row.legacy_proof.legacy_body!=='string'))throw Error('Invalid observed legacy ownership proof');
    seen.add(row.node_id);
  }
}
async function nativeSpecificationApply(figma,plan) {
  nativeSpecificationValidate(plan);nativeEditScope(figma,plan);
  const contract=plan.specifications,board=contract.board,page=figma.currentPage;
  const all=()=>[page,...page.findAll(()=>true)],same=nativeEditEqual,copy=nativeEditClone;
  const metadata=node=>{const raw=node.getPluginData('figmaFlowSpecification');return raw?JSON.parse(raw):null;};
  const expectedWrapper=row=>({schema:FLOW_SPEC.schemas.native,semantic_key:row.semantic_key,target_id:row.node_id,source_owner_hash:board.owner.sourceHash,specification:row.after,legacy_annotations:[...(row.before.specification?.legacy_annotations||[]),...row.legacy_annotations],state:'applied'});
  const objects=new Map(all().map(node=>[node.id,node]));
  const actualBoard=objects.get(board.node_id);
  const entry=row=>{const matches=board.entries.filter(entry=>entry.hyperlink?.type==='NODE'&&entry.hyperlink.value===row.node_id);if(matches.length!==1)throw Error('Specification target requires one exact observed board hyperlink');return matches[0];};
  const rowState=row=>{
    const node=objects.get(row.node_id),text=objects.get(entry(row)?.textNodeId);
    if(!node||!text||node.getPluginData('semanticKey')!==row.semantic_key||text.parent!==actualBoard||text.getPluginData('semanticKey')!==entry(row).key)throw Error('Specification target/entry identity conflict');
    const link=text.getRangeHyperlink(0,text.characters.length)||null;
    const before=same(metadata(node),row.before.specification)&&same(node.annotations,row.before.annotations)&&text.characters===entry(row).characters&&same(link,entry(row).hyperlink);
    if(before&&row.legacy_proof){const slot=row.legacy_annotations[0],body=`${node.name} · ${entry(row).key.slice(board.key.length+1)}\n${slot?.annotation?.label||''}\n화면·조작으로 이동`;if(node.name!==row.legacy_proof.target_name||body!==row.legacy_proof.legacy_body||text.characters!==row.legacy_proof.legacy_body)throw Error('Exact observed legacy display conflict');}
    const wrapper=metadata(node),expected=expectedWrapper(row),human=wrapper?.human_annotation;
    const base=wrapper&&Object.fromEntries(Object.entries(wrapper).filter(([key])=>key!=='human_annotation'));
    let annotationAfter=false;
    if(row.after.presentation==='connected-spec-v2'&&human?.schema===FLOW_SPEC.schemas.human&&Number.isInteger(human.index)&&human.index>=0&&same(node.annotations[human.index],human.annotation)&&human.board?.boardId===board.node_id&&human.board?.textNodeId===entry(row).textNodeId&&human.board?.key===entry(row).key.slice(board.key.length+1)){
      const generated=connectedSpecificationMarkdown(row.after,{fileKey:plan.file_key,textNodeId:entry(row).textNodeId,locale:row.after.locale});
      const expectedArray=connectedSpecificationAnnotations(row.before.annotations,row.legacy_annotations,row.before.specification?.human_annotation,{labelMarkdown:generated.markdown});
      annotationAfter=same(node.annotations.filter((_,index)=>index!==human.index).length,expectedArray.filter((_,index)=>index!==human.index).length)&&same(node.annotations.filter((_,index)=>index!==human.index),expectedArray.filter((_,index)=>index!==human.index))&&nativeAnnotationMatches(human.annotation,generated.markdown)&&human.url===generated.url;
    } else annotationAfter=same(node.annotations,row.before.annotations.filter((_,index)=>!row.legacy_annotations.some(slot=>slot.index===index)));
    const after=same(base,expected)&&annotationAfter&&text.characters===row.after.title+'\n'+row.after.display_text&&same(link,{type:'NODE',value:row.node_id});
    return after&&before?'neutral':after?'after':before?'before':'conflict';
  };
  const preflight=()=>{
    nativeEditScope(figma,plan);
    if(!actualBoard||actualBoard.parent!==page||actualBoard.getPluginData('semanticKey')!==board.key||!same(JSON.parse(actualBoard.getPluginData('designNoteBoard')||'null'),board.owner)||actualBoard.children.length!==board.entries.length||all().filter(node=>node.getPluginData('semanticKey')===board.key).length!==1)throw Error('Specification board ownership/children conflict');
    for(const row of contract.targets)if(all().filter(node=>node.getPluginData('semanticKey')===row.semantic_key).length!==1)throw Error('Ambiguous specification native key');
    for(const expected of board.entries){
      const text=objects.get(expected.textNodeId),row=contract.targets.find(row=>entry(row)?.textNodeId===expected.textNodeId);
      if(!text||text.parent!==actualBoard||text.getPluginData('semanticKey')!==expected.key||(!row&&(text.characters!==expected.characters||!same(text.getRangeHyperlink(0,text.characters.length)||null,expected.hyperlink))))throw Error('Unmentioned board entry changed');
    }
    const states=contract.targets.map(rowState);
    if(states.every(state=>['after','neutral'].includes(state)))return 'after';
    if(states.every(state=>['before','neutral'].includes(state)))return 'before';
    throw Error('Specification mixed partial state or before-state conflict');
  };
  let state=preflight();
  await figma.loadFontAsync(board.font);
  if(preflight()!==state)throw Error('Specification changed during font preflight');
  if(state==='after')return {changed:0,assertAfter:()=>{if(preflight()!=='after')throw Error('Specification drift during discovery');}};
  const rollbacks=[];
  try {
    const guardedBoardAPI={loadFontAsync:async font=>{await figma.loadFontAsync(font);if(preflight()!=='before')throw Error('Specification changed during board font await');},createFrame:()=>{throw Error('Existing board required');},createText:()=>{throw Error('Existing display text required');}};
    const result=await ensureDesignNoteBoard(guardedBoardAPI,page,{presentation:'readable-specs',sourceHash:board.owner.sourceHash,boardKey:board.key,font:board.font,partial:true,expectedEntries:board.entries,notes:contract.targets.map(row=>({key:entry(row).key.slice(board.key.length+1),targetId:row.node_id,specification:row.after}))});
    rollbacks.push(result.rollback);
    // Board helper awaits fonts; every target must still have its admitted before state.
    nativeEditScope(figma,plan);
    for(const row of contract.targets){const node=objects.get(row.node_id);if(!same(metadata(node),row.before.specification)||!same(node.annotations,row.before.annotations))throw Error('Specification target drifted during board update');}
    // One helper call archives every target before removing the exact legacy slots last.
    const annotationPreflight=()=>{
      nativeEditScope(figma,plan);
      if(actualBoard.parent!==page||!same(JSON.parse(actualBoard.getPluginData('designNoteBoard')||'null'),board.owner)||actualBoard.children.length!==board.entries.length)throw Error('Specification board changed during annotation await');
      for(const expected of board.entries){
        const text=objects.get(expected.textNodeId),row=contract.targets.find(row=>entry(row)?.textNodeId===expected.textNodeId);
        const characters=row?row.after.title+'\n'+row.after.display_text:expected.characters,link=row?{type:'NODE',value:row.node_id}:expected.hyperlink;
        if(!text||text.parent!==actualBoard||text.getPluginData('semanticKey')!==expected.key||text.characters!==characters||!same(text.getRangeHyperlink(0,text.characters.length)||null,link))throw Error('Specification display changed during annotation await');
      }
      for(const row of contract.targets){
        const node=objects.get(row.node_id);
        if(all().filter(item=>item.getPluginData('semanticKey')===row.semantic_key).length!==1||node.getPluginData('semanticKey')!==row.semantic_key||!same(metadata(node),row.before.specification)||!same(node.annotations,row.before.annotations))throw Error('Specification target changed during annotation await');
      }
    };
    const annotations=await ensureNativeAnnotations(figma,page,{presentation:'readable-specs',strictLegacyDisplay:true,sourceHash:board.owner.sourceHash,preflight:annotationPreflight,annotations:contract.targets.map(row=>({key:row.semantic_key,label:row.after.title,specification:row.after,expected_before:row.before,expected_legacy:row.legacy_annotations,expected_legacy_display:row.legacy_proof?.legacy_body,board:{boardId:board.node_id,textNodeId:entry(row).textNodeId,key:entry(row).key.slice(board.key.length+1)}}))});
    rollbacks.push(annotations.rollback);
    if(preflight()!=='after')throw Error('Independent specification getters differ after update');
    return {changed:result.changed+annotations.changed,assertAfter:()=>{if(preflight()!=='after')throw Error('Specification drift during discovery');},rollback:async()=>{for(const rollback of rollbacks.slice().reverse()){nativeEditScope(figma,plan);await rollback();}}};
  } catch(error) {
    const conflicts=[];
    for(const rollback of rollbacks.reverse())try{nativeEditScope(figma,plan);await rollback();}catch(rollbackError){conflicts.push(String(rollbackError.message||rollbackError));}
    error.rollback_conflicts=conflicts;
    try{error.readback=await nativeEditDiscovery(figma,plan);error.readback.native_edit={plan_sha256:NATIVE_EDIT_SHA256,operation:'apply',applied:false};error.readback.specification_error=String(error.message||error);error.readback.rollback_conflicts=conflicts;}catch(discoveryError){error.specification_error=String(discoveryError.message||discoveryError);}
    throw error;
  }
}
