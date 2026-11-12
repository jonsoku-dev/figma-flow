function littleHandsMeasure(stateId) {
  if (!/^state-[a-z0-9-]+$/.test(stateId)) throw new Error('Explicit semantic state ID required');
  const environment = document.body.dataset.environment || document.querySelector('.environment')?.textContent || '';
  if (!/staging/i.test(environment)) throw new Error('Capture refuses non-staging DOM');
  const round = n => n;
  const box = r => [round(r.left + scrollX), round(r.top + scrollY), round(r.width), round(r.height)];
  const visible = el => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility === 'visible' && Number(s.opacity) > 0 && r.width > 0 && r.height > 0 && r.right + scrollX > 0 && r.bottom + scrollY > 0 && !el.closest('[hidden]') && s.clipPath !== 'inset(50%)' && !(s.clip !== 'auto' && s.position === 'absolute' && r.width <= 1 && r.height <= 1);
  };
  const cssPath = el => {
    if (el.id) return '#' + CSS.escape(el.id);
    const key = el.getAttribute('data-native-key');
    if (key && document.querySelectorAll('[data-native-key="' + CSS.escape(key) + '"]').length === 1) return '[data-native-key="' + CSS.escape(key) + '"]';
    const parts = [];
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      parts.unshift(e.localName + ':nth-child(' + (Array.from(e.parentElement.children).indexOf(e) + 1) + ')');
    }
    return 'body>' + parts.join('>');
  };
  const keyCounts = new Map(), keyedElements = new Map();
  const makeKey = (el, suffix = '') => {
    const raw = el.getAttribute('data-native-key') || el.id || cssPath(el);
    const base = stateId + '-' + raw.replace(/[^A-Za-z0-9_-]+/g, '-') + suffix;
    const count = (keyCounts.get(base) || 0) + 1; keyCounts.set(base, count);
    const id = count === 1 ? base : base + '-occurrence-' + count;
    keyedElements.set(id,el);
    return id;
  };
  const style = el => {
    const s = getComputedStyle(el);
    const leading = Number.parseFloat(s.lineHeight) || Number.parseFloat(s.fontSize) * 1.5;
    return {fill: s.backgroundColor, ink: s.color, stroke: s.borderTopColor, stroke_width: Number.parseFloat(s.borderTopWidth), borders: ['Top','Right','Bottom','Left'].map(side => ({width:Number.parseFloat(s['border'+side+'Width']),color:s['border'+side+'Color']})), radius: Number.parseFloat(s.borderTopLeftRadius), fontFamily: s.fontFamily.split(',')[0].replace(/["']/g, '').trim(), fontWeight: Number(s.fontWeight), fontSize: Number.parseFloat(s.fontSize), leading, letter_spacing: Number.parseFloat(s.letterSpacing) || 0, align: s.textAlign, padding: [s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft].map(Number.parseFloat), objectFit: s.objectFit, objectPosition: s.objectPosition, boxShadow: s.boxShadow, opacity: Number(s.opacity)};
  };
  const controls = [], surfaces = [], images = [], texts = [], containers = [];
  const actionEls = Array.from(document.querySelectorAll('a,button,input:not([type="hidden"]),select,textarea')).filter(visible);
  for (const el of actionEls) {
    if (el.matches('input[type="password"]')) continue;
    const s = style(el), r = el.getBoundingClientRect();
    const isToggle = el.matches('input[type=checkbox],input[type=radio]');
    let label = isToggle ? '' : el.matches('select') ? el.selectedOptions[0]?.textContent : el.matches('input,textarea') ? (el.value || el.getAttribute('placeholder') || '') : el.innerText;
    const form = el.closest('form');
    controls.push({id: makeKey(el), native_key: el.getAttribute('data-native-key'), selector: cssPath(el), tag: el.localName, type: el.getAttribute('type'), box: box(r), label: (label || '').trim(), action: el.getAttribute('data-action'), href: el.matches('a') ? el.getAttribute('href') : null, method: form?.method?.toUpperCase() || null, form_action: form?.getAttribute('action') || null, disabled: !!el.disabled, checked: el.matches('input[type="checkbox"],input[type="radio"]') ? el.checked : null, style: s, label_styles: Array.from(el.querySelectorAll('*')).filter(child=>visible(child) && Array.from(child.childNodes).some(node=>node.nodeType===Node.TEXT_NODE && node.textContent.trim())).map(child=>({fontFamily:style(child).fontFamily,fontWeight:style(child).fontWeight,fontSize:style(child).fontSize,ink:style(child).ink}))});
  }
  for (const el of Array.from(document.querySelectorAll('[data-native-type="surface"],input:not([type="hidden"]),select,textarea')).filter(visible)) {
    const s = style(el);
    if (el.namespaceURI === 'http://www.w3.org/2000/svg') {
      s.fill = getComputedStyle(el).fill;
      s.radius = Number(el.getAttribute('rx') || 0);
    }
    surfaces.push({id: makeKey(el, '-surface'), selector: cssPath(el), tag: el.localName, box: box(el.getBoundingClientRect()), style: s, semantic: el.namespaceURI === 'http://www.w3.org/2000/svg' ? 'data-chart-bar' : 'surface'});
  }
  for (const el of Array.from(document.images).filter(visible)) images.push({id: makeKey(el), selector: cssPath(el), box: box(el.getBoundingClientRect()), src: new URL(el.currentSrc || el.src).pathname, alt: el.alt, style: style(el), naturalWidth: el.naturalWidth, naturalHeight: el.naturalHeight});
  const textNodes = [];
  const collectText = node => {
    if (node.nodeType === Node.TEXT_NODE) textNodes.push(node);
    else for (const child of Array.from(node.childNodes)) collectText(child);
  };
  collectText(document.body);
  for (const node of textNodes) {
    const el = node.parentElement;
    if (!node.textContent.trim() || !visible(el) || el.closest('script,style,template,button,a,select,textarea') || el.closest('[hidden],input[type="hidden"],input[type="password"]')) continue;
    const s = style(el), lines = [];
    const range = document.createRange();
    for (let i = 0; i < node.textContent.length; i++) {
      range.setStart(node, i); range.setEnd(node, i + 1);
      const r = range.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      let line = lines.find(row => Math.abs(row.top - r.top) < 1);
      if (!line) { line = {top:r.top, left:r.left, right:r.right, glyphHeight:r.height, value:''}; lines.push(line); }
      line.value += node.textContent[i]; line.left = Math.min(line.left,r.left); line.right = Math.max(line.right,r.right);
    }
    const pr = el.getBoundingClientRect(), borders = s.borders.map(row=>row.width);
    const contentBox = [round(pr.left+s.padding[3]+borders[3]+scrollX),round(pr.top+s.padding[0]+borders[0]+scrollY),round(pr.width-s.padding[1]-s.padding[3]-borders[1]-borders[3]),round(pr.height-s.padding[0]-s.padding[2]-borders[0]-borders[2])];
    const childTags = Array.from(el.children).map(child=>child.localName);
    const display = getComputedStyle(el).display;
    const blockContent = !['inline','inline-block','inline-flex','contents'].includes(display) && childTags.every(tag=>tag==='br');
    for (const [i, line] of lines.entries()) {
      const value = line.value.trim(); if (!value) continue;
      const y = blockContent ? contentBox[1] + Math.round((line.top+scrollY-contentBox[1])/s.leading)*s.leading : line.top+scrollY-(s.leading-line.glyphHeight)/2;
      texts.push({id: makeKey(el, '-text-' + i), selector: cssPath(el), value, raw_value:line.value, box:[round(blockContent ? contentBox[0] : line.left+scrollX),round(y),round(blockContent ? contentBox[2] : line.right-line.left),round(s.leading)], glyph_box:[round(line.left+scrollX),round(line.top+scrollY),round(line.right-line.left),round(line.glyphHeight)], element_box:box(pr), content_box:contentBox, text_context:{display,tag:el.localName,child_tags:childTags,block_content:blockContent,allocation:blockContent ? 'actual CSS block content area' : 'actual inline fragment range'},style:s,max_lines:1});
    }
  }
  const containerSelector = 'header,main,footer,section,article,form,table,nav,.panel,.paper,.summary-panel,.chart,.stats,.field,.actions,.table-wrap,.header-inner,.nav';
  for (const el of Array.from(document.querySelectorAll(containerSelector)).filter(visible)) {
    const s = getComputedStyle(el), parent = el.parentElement?.closest(containerSelector);
    containers.push({id:makeKey(el,'-container'), selector:cssPath(el), parent_selector:parent ? cssPath(parent) : null, box:box(el.getBoundingClientRect()), tag:el.localName, classes:el.className?.baseVal ?? el.className, members:Array.from(keyedElements).filter(([id,target]) => target === el || el.contains(target)).map(([id])=>id), css:{display:s.display, flex_direction:s.flexDirection, flex_wrap:s.flexWrap, gap:Number.parseFloat(s.gap)||0, align_items:s.alignItems, justify_content:s.justifyContent, padding:[s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft].map(Number.parseFloat), overflow_x:s.overflowX, overflow_y:s.overflowY}});
  }
  const escape = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const allowed = new Set(['id','class','lang','dir','title','role','alt','width','height','src','href','rel','name','type','placeholder','for','tabindex','rows','cols','min','max','step','required','disabled','checked','selected','multiple','scope','colspan','rowspan','viewBox','preserveAspectRatio','x','y','rx','ry','cx','cy','r','d','fill']);
  const voids = new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  const serialize = node => {
    if (node.nodeType === Node.TEXT_NODE) return escape(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE) return '';
    const el = node, originalTag = el.localName;
    if (['script','style','template','noscript','meta','base'].includes(originalTag) || el.hidden) return '';
    if (originalTag === 'input' && el.getAttribute('type') === 'hidden') return '';
    if (el.closest('body') && !['br','option'].includes(originalTag) && !visible(el)) return '';
    const tag = originalTag;
    let attrs = '';
    for (const attr of el.attributes) {
      if ((allowed.has(attr.name) || attr.name.startsWith('aria-') || ['data-native-key','data-native-type','data-action','data-app','data-environment'].includes(attr.name)) && !/csrf|token|nonce|password/i.test(attr.name)) attrs += ' ' + attr.name + '="' + escape(attr.value) + '"';
    }
    if (originalTag === 'form') attrs += ' inert data-export-only="true" method="' + escape(el.method) + '"';
    if (originalTag === 'button') attrs = attrs.replace(/ type="[^"]*"/,'') + ' type="button"';
    if (originalTag === 'input' && !['password','hidden','checkbox','radio'].includes(el.getAttribute('type'))) attrs += ' value="' + escape(el.value) + '"';
    if (originalTag === 'option' && el.selected) attrs += ' selected';
    if (originalTag === 'input' && ['checkbox','radio'].includes(el.getAttribute('type')) && el.checked) attrs += ' checked';
    return '<' + tag + attrs + '>' + (voids.has(tag) ? '' : Array.from(el.childNodes).map(serialize).join('') + '</' + tag + '>');
  };
  return {schema:'little-hands-browser-measurement-v1', state:stateId, scroll:{x:scrollX,y:scrollY}, viewport:{width:innerWidth,height:innerHeight}, document:{width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}, route:location.pathname, title:document.title, body_background:getComputedStyle(document.body).backgroundColor, fonts_ready:document.fonts.status, captured_at:new Date().toISOString(), controls,surfaces,images,texts,containers, html:'<!doctype html>\n' + serialize(document.documentElement), scope:'Actual visible DOM geometry. Visual source only; no authentication, SQL, action execution, acceptance result, or Figma observation is proved.'};
}
