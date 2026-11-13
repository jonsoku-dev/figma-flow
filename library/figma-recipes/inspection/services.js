/* The graph embeds exact SDK declarations. Only reviewed service operations below can be invoked. */
async function inspectDesignServices(api, plan) {
  const page = api.currentPage;
  if (api.editorType !== 'figma' || api.fileKey !== plan.file || page.id !== plan.page) {
    throw Error('Open the Design file and page admitted by the inspection graph.');
  }
  const rows = Object.create(null);
  const outcomes = new Map();
  for (const row of plan.members) rows[row.owner + '.' + row.name] = row;
  function record(row, status, value) {
    if (!row) return;
    // The receipt contains no file, layer, style, font or variable identifiers or text.
    const summary = Array.isArray(value) ? 'array' : typeof value;
    const prior = outcomes.get(row.id);
    if (!prior || prior.status !== 'success') outcomes.set(row.id, {id: row.id, status, shape: summary});
  }
  function read(owner, object) {
    if (!object) return;
    for (const row of plan.members) {
      if (row.owner !== owner || row.kind !== 'PropertySignature') continue;
      try {
        const value = object[row.name];
        record(row, value == null ? 'unavailable' : 'success', value);
      } catch (_) { record(row, 'runtime-error'); }
    }
  }
  async function call(owner, object, name, ...args) {
    const row = rows[owner + '.' + name];
    if (!row) throw Error('Method not present in the inspection graph: ' + owner + '.' + name);
    if (api.currentPage.id !== page.id) throw Error('Inspection page changed.');
    try {
      if (!object || typeof object[name] !== 'function') { record(row, 'unsupported'); return undefined; }
      const result = await object[name](...args);
      record(row, 'success', result);
      return result;
    } catch (_) { record(row, 'runtime-error'); return undefined; }
  }
  const service = (name, ...args) => call('PluginAPI', api, name, ...args);
  const mark = 'figmaFlowServiceSpecimen';
  const identity = plan.sha256;
  const matches = page.children.filter(n => n.getPluginData(mark) === identity);
  if (matches.length > 1 || (matches[0] && matches[0].type !== 'FRAME')) throw Error('Ambiguous owned specimen.');
  const root = matches[0] || api.createFrame();
  if (!matches.length) {
    root.name = 'Figma Flow · Service inspection';
    root.setPluginData(mark, identity);
    root.resize(340, 112);
    root.x = page.children.reduce((right, node) => node === root ? right : Math.max(right, node.x + (node.width || 0)), 0) + 160;
    root.y = 0;
    root.fills = [];
  }
  function ownNode(label, create) {
    const existing = root.children.find(n => n.getPluginData(mark) === label);
    if (existing) return Promise.resolve(existing);
    return Promise.resolve(create()).then(node => {
      if (!node) return undefined;
      root.appendChild(node);
      node.setPluginData(mark, label);
      node.name = label;
      return node;
    });
  }

  read('PluginAPI', api);
  read('ViewportAPI', api.viewport);
  read('Rect', api.viewport.bounds);
  read('Vector', api.viewport.center);
  read('ConstantsAPI', api.constants);
  await service('getNodeByIdAsync', root.id);
  await service('getNodeById', root.id);
  await service('getFileThumbnailNodeAsync');
  await service('getFileThumbnailNode');
  await service('getSelectionColors');
  const fonts = await service('listAvailableFontsAsync');
  const available = fonts && fonts.find(f => f.fontName.family === 'Inter' && f.fontName.style === 'Regular');
  if (available) {
    read('Font', available); read('FontName', available.fontName);
    await service('loadFontAsync', available.fontName);
    await service('getFontFamilyVariationAxes', available.fontName.family);
  }
  const text = await ownNode('Type specimen', () => service('createText'));
  if (text && available) {
    text.fontName = available.fontName;
    text.characters = 'Operations review';
    text.x = 12; text.y = 10; text.fontSize = 18;
    const fields = plan.members.filter(m => m.owner === 'StyledTextSegment').map(m => m.name)
      .filter(n => !['start', 'end', 'characters'].includes(n));
    // Ask for one field per call. An unavailable beta field cannot suppress the rest.
    for (const field of fields) {
      try {
        const segment = text.getStyledTextSegments([field])[0];
        if (segment) {
          const row = rows['StyledTextSegment.' + field];
          record(row, segment[field] == null ? 'unavailable' : 'success', segment[field]);
          for (const key of ['start','end','characters']) record(rows['StyledTextSegment.' + key], 'success', segment[key]);
        }
      } catch (_) { record(rows['StyledTextSegment.' + field], 'runtime-error'); }
    }
  }
  const util = api.util;
  const rgb = await call('UtilAPI', util, 'rgb', '#366aa6');
  const rgba = await call('UtilAPI', util, 'rgba', '#366aa6', 0.75);
  read('RGB', rgb); read('RGBA', rgba); read('RGBWithColorSpace', rgb); read('RGBAWithColorSpace', rgba);
  const solid = await call('UtilAPI', util, 'solidPaint', '#366aa6');
  await call('UtilAPI', util, 'normalizeMarkdown', '**Review**');
  if (solid) read('SolidPaint', solid);
  const svg = await ownNode('Vector specimen', () => service('createNodeFromSvg',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 30"><path fill="#366aa6" d="M0 0h80L40 30z"/></svg>'));
  if (svg) {
    svg.x = 12; svg.y = 46;
    const vector = svg.findOne(n => n.type === 'VECTOR');
    if (vector) {
      const network = vector.vectorNetwork;
      read('VectorNetwork', network); read('VectorVertex', network.vertices[0]);
      read('VectorSegment', network.segments[0]); read('VectorRegion', (network.regions || [])[0]);
    }
  }
  const sample = await ownNode('Paint specimen', () => api.createRectangle());
  sample.x = 115; sample.y = 42; sample.resize(96,40);
  sample.fills = [{type:'GRADIENT_LINEAR', gradientTransform:[[1,0,0],[0,1,0]],
    gradientStops:[{position:0,color:{r:.1,g:.4,b:.7,a:1}},{position:1,color:{r:.5,g:.9,b:.6,a:1}}]}];
  read('GradientPaint', sample.fills[0]); read('ColorStop', sample.fills[0].gradientStops[0]); read('RGBA', sample.fills[0].gradientStops[0].color);
  root.effects = [{type:'DROP_SHADOW', color:{r:0,g:.1,b:.3,a:.15}, radius:8, offset:{x:0,y:4}, visible:true, blendMode:'NORMAL', spread:0}];
  read('DropShadowEffect', root.effects[0]);
  root.layoutGrids = [{pattern:'GRID',sectionSize:8,visible:false,color:{r:0,g:.3,b:.6,a:.1}}];
  read('GridLayoutGrid', root.layoutGrids[0]);
  sample.exportSettings=[{format:'PNG',suffix:'',constraint:{type:'SCALE',value:1},contentsOnly:true}];
  read('ExportSettingsImage', sample.exportSettings[0]);
  const bytes = await sample.exportAsync({format:'PNG'});
  const encoded = await service('base64Encode', bytes);
  const decoded = encoded && await service('base64Decode', encoded);
  const img = decoded && await service('createImage', decoded);
  if (img) {
    read('Image', img);
    const real = await service('getImageByHash', img.hash);
    if (real) {
      await call('Image',real,'getSizeAsync'); await call('Image',real,'getBytesAsync');
      const raster = await ownNode('Image specimen',()=>api.createRectangle());
      raster.x=222; raster.y=42; raster.resize(96,40);
      raster.fills=[{type:'IMAGE',imageHash:real.hash,scaleMode:'FILL',filters:{contrast:.1,saturation:-.15,exposure:.1,shadows:.1,highlights:0,tint:0,temperature:0}}];
      read('ImagePaint',raster.fills[0]);read('ImageFilters',raster.fills[0].filters);
    }
  }
  const vapi = api.variables;
  const vars = (op,...args)=>call('VariablesAPI',vapi,op,...args);
  const collections = await vars('getLocalVariableCollectionsAsync');
  await vars('getLocalVariableCollections'); await vars('getLocalVariables'); await vars('getLocalVariablesAsync');
  let collection = (collections || []).find(c=>c.getPluginData(mark)===identity);
  if (!collection) {
    collection = await vars('createVariableCollection','Figma Flow · '+identity.slice(0,8));
    if (collection) collection.setPluginData(mark,identity);
  }
  if (collection) {
    read('VariableCollection',collection);await call('VariableCollection',collection,'getPublishStatusAsync');
    await vars('getVariableCollectionById',collection.id); await vars('getVariableCollectionByIdAsync',collection.id);
    const local = await vars('getLocalVariablesAsync','FLOAT');
    let variable = (local || []).find(v=>v.variableCollectionId===collection.id && v.getPluginData(mark)===identity);
    if (!variable) {
      variable=vapi.createVariable('Specimen/spacing',collection,'FLOAT');variable.setPluginData(mark,identity);
    }
    await call('Variable',variable,'setValueForMode',collection.defaultModeId,8);
    await call('Variable',variable,'setVariableCodeSyntax','WEB','var(--specimen-spacing)');
    read('Variable',variable);await call('Variable',variable,'getPublishStatusAsync');
    const resolved=await call('Variable',variable,'resolveForConsumer',sample);read('Variable.resolveForConsumer',resolved);
    await call('Variable',variable,'valuesByModeForCollectionAsync',collection);
    await vars('getVariableById',variable.id);await vars('getVariableByIdAsync',variable.id);
    read('VariableAlias',await vars('createVariableAlias',variable));
    read('VariableAlias',await vars('createVariableAliasByIdAsync',variable.id));
    const eff=await vars('setBoundVariableForEffect',root.effects[0],'radius',variable);
    if (eff) {root.effects=[eff]; read('DropShadowEffect',root.effects[0]);}
    const grid=await vars('setBoundVariableForLayoutGrid',root.layoutGrids[0],'sectionSize',variable);
    if (grid) {root.layoutGrids=[grid]; read('GridLayoutGrid',root.layoutGrids[0]);}
    await vars('setBoundVariableForPaint',solid,'color',null);
  }
  for (const prefix of ['Paint','Text','Effect','Grid']) {
    const plural='getLocal'+prefix+'Styles';
    const styles=await service(plural+'Async');
    await service(plural);
    const owner=prefix+'Style';
    let style=(styles || []).find(s=>s.getPluginData(mark)===identity);
    if (!style) {
      style=await service('create'+owner);
      if (style) {style.name='Figma Flow / '+prefix+' '+identity.slice(0,8);style.setPluginData(mark,identity);}
    }
    if (!style) continue;
    if (prefix==='Paint' && solid) style.paints=[solid];
    if (prefix==='Effect') style.effects=root.effects;
    if (prefix==='Grid') style.layoutGrids=root.layoutGrids;
    if (prefix==='Text' && available) {
      style.fontName=available.fontName;style.fontSize=18;
      await call(owner,style,'setBoundVariable','fontSize',null);
    }
    read(owner,style);read('BaseStyleMixin',style);read('PublishableMixin',style);
    await service('getStyleByIdAsync',style.id);await service('getStyleById',style.id);
    await call('BaseStyleMixin',style,'getStyleConsumersAsync');
    await call('PublishableMixin',style,'getPublishStatusAsync');
  }
  await service('getLocalCustomAnimationStylesAsync');await service('getLocalCustomAnimationStyles');
  const categories=await call('AnnotationsAPI',api.annotations,'getAnnotationCategoriesAsync');
  if (categories && categories.length) {
    const category=await call('AnnotationsAPI',api.annotations,'getAnnotationCategoryByIdAsync',categories[0].id);
    read('AnnotationCategory',category);
  }
  const privateKey='figma-flow-service-inspection-'+identity;
  await call('ClientStorageAPI',api.clientStorage,'setAsync',privateKey,identity);
  await call('ClientStorageAPI',api.clientStorage,'getAsync',privateKey);
  await call('ClientStorageAPI',api.clientStorage,'deleteAsync',privateKey);
  await call('PluginDataMixin',root,'setSharedPluginData','figmaflow','serviceInspection',identity);
  await call('PluginDataMixin',root,'getSharedPluginData','figmaflow','serviceInspection');
  await call('PluginDataMixin',root,'getSharedPluginDataKeys','figmaflow');
  await call('PluginDataMixin',root,'setPluginData','serviceInspection',identity);
  await call('PluginDataMixin',root,'getPluginData','serviceInspection');
  await call('PluginDataMixin',root,'getPluginDataKeys');
  if (api.currentPage.id !== page.id) throw Error('Inspection page changed.');
  return {schema:'figma-flow-service-inspection-receipt-v1', graph_sha256:identity, observed_at:new Date().toISOString(),
    specimen_id:root.id, reused:!!matches.length, observations:[...outcomes.values()]};
}

if (typeof figma !== 'undefined') {
  inspectDesignServices(figma,INSPECTION).then(result => {
    const json=JSON.stringify(result);
    // Compact chunks keep the whole local receipt inspectable in the host dialog.
    const chunks=json.match(/.{1,420}/g) || [];
    const html=chunks.map((s,i)=>'<p>ReceiptPart'+String(i).padStart(3,'0')+' '+s.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</p>').join('');
    figma.showUI('<meta charset="utf-8"><h3>Design service inspection</h3>'+html,{width:680,height:400});
  }).catch(error=>figma.closePlugin(String(error)));
}
