/**
 * Read a rendered page into web-design graph geometry. Call in the page's
 * browser evaluation context. This function reads the DOM and requests no URLs.
 */
function captureWebDesign({screenId, extent = 'viewport', maxLayers = 1500} = {}) {
  if (!/^WEB-[a-zA-Z0-9-]+$/.test(screenId) || !['viewport', 'document'].includes(extent)
      || !Number.isInteger(maxLayers) || maxLayers < 1 || maxLayers > 1500) {
    throw Error('Provide a WEB- screen ID, a supported extent and a 1–1500 layer bound.');
  }
  const width = document.documentElement.clientWidth;
  const height = extent === 'document' ? document.documentElement.scrollHeight : innerHeight;
  const dx = extent === 'document' ? scrollX : 0;
  const dy = extent === 'document' ? scrollY : 0;
  const elements = [], unboundImages = [], limitations = new Set();
  const round = v => Math.round(v * 100) / 100;
  const numeric = (value, fallback = 0) => Number.isFinite(Number.parseFloat(value)) ? Number.parseFloat(value) : fallback;
  function color(css) {
    if (!css || css === 'none' || css === 'transparent') return null;
    const numbers = css.match(/-?[\d.]+(?:e[+-]?\d+)?/gi)?.map(Number);
    if (!numbers || numbers.length < 3) return null;
    let [r,g,b,alpha = 1] = numbers;
    if (/^rgba?\(/.test(css)) {
      [r,g,b] = [r/255,g/255,b/255];
    } else if (/^color\(srgb /.test(css)) {
      // Already expressed in [0,1].
    } else if (/^(?:lab|lch|oklab|oklch)\(/.test(css)) {
      if (css.includes('lch')) {
        const radians = b * Math.PI / 180;
        [g,b] = [g * Math.cos(radians), g * Math.sin(radians)];
      }
      if (css.startsWith('ok')) {
        const l = (r + .3963377774*g + .2158037573*b)**3;
        const m = (r - .1055613458*g - .0638541728*b)**3;
        const s = (r - .0894841775*g - 1.291485548*b)**3;
        [r,g,b] = [4.0767416621*l-3.3077115913*m+.2309699292*s,
          -1.2684380046*l+2.6097574011*m-.3413193965*s,-.0041960863*l-.7034186147*m+1.707614701*s];
      } else {
        const f = (r + 16)/116;
        const inv = k => k > 6/29 ? k**3 : 3*(6/29)**2*(k-4/29);
        const x = .96422*inv(f+g/500), y = inv(f), z = .82521*inv(f-b/200);
        [r,g,b] = [3.1338561*x-1.6168667*y-.4906146*z,-.9787684*x+1.9161415*y+.033454*z,
          .0719453*x-.2289914*y+1.4052427*z];
      }
      [r,g,b] = [r,g,b].map(v=>v<=.0031308 ? 12.92*v : 1.055*v**(1/2.4)-.055);
    } else {
      limitations.add('unsupported CSS color space'); return null;
    }
    if (alpha <= 0) return null;
    const hex = v => Math.round(Math.max(0,Math.min(1,v))*255).toString(16).padStart(2,'0');
    return '#'+[r,g,b].map(hex).join('')+(alpha<1 ? hex(alpha) : '');
  }
  function box(r) {
    return {x:round(r.x+dx), y:round(r.y+dy), width:round(r.width), height:round(r.height)};
  }
  function intersects(b) {
    return b.width>0 && b.height>0 && b.x<width && b.y<height && b.x+b.width>0 && b.y+b.height>0;
  }
  function push(layer) {
    if (elements.length >= maxLayers) throw Error('Screen exceeds the approved layer budget. Choose a smaller viewport or section.');
    elements.push(layer);
  }
  function typography(style, characters) {
    return {characters, fontFamily:style.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g,''),
      fontWeight:numeric(style.fontWeight,400),fontSize:numeric(style.fontSize,16),
      lineHeight:numeric(style.lineHeight,numeric(style.fontSize,16)*1.2),
      textAlignHorizontal:({center:'center',right:'right',end:'right'})[style.textAlign]||'left',
      color:color(style.color)||'#000000'};
  }
  function paint(style) {
    const p={},bg=color(style.backgroundColor),border=numeric(style.borderTopWidth);
    if (bg) p.background=bg;
    if (border>0 && style.borderTopStyle!=='none') {
      const stroke=color(style.borderTopColor);
      if(stroke){p.borderWidth=border;p.borderColor=stroke;}
    }
    const radius=numeric(style.borderTopLeftRadius);
    if(radius>0)p.borderRadius=radius;
    if(numeric(style.opacity,1)<1)p.opacity=numeric(style.opacity,1);
    return p;
  }
  function simpleVector(el) {
    const tags={svg:['viewBox','width','height'],g:['transform'],path:['d','transform','fill-rule'],
      rect:['x','y','width','height','rx','ry'],circle:['cx','cy','r'],ellipse:['cx','cy','rx','ry'],
      line:['x1','y1','x2','y2'],polygon:['points'],polyline:['points']};
    let count=0;
    const esc=v=>String(v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
    function draw(n) {
      if(++count>1200)throw Error('complex SVG');
      const tag=n.tagName.toLowerCase();
      if(tag==='title'||tag==='desc')return '';
      if(!tags[tag])throw Error('complex SVG');
      const attrs=tags[tag].filter(k=>n.hasAttribute(k)).map(k=>k+'="'+esc(n.getAttribute(k))+'"');
      if(tag==='svg')attrs.push('xmlns="http://www.w3.org/2000/svg"');
      const s=getComputedStyle(n);
      for(const prop of ['fill','stroke']){
        if(tag==='svg' || (tag==='line' && prop==='fill'))continue;
        if(/^url\(/.test(s[prop]))throw Error('SVG paint server');
        const c=color(s[prop]);attrs.push(prop+'="'+(c||'none')+'"');
      }
      if(tag!=='svg' && tag!=='g' && numeric(s.strokeWidth)>0)attrs.push('stroke-width="'+numeric(s.strokeWidth)+'"');
      return '<'+tag+' '+attrs.join(' ')+'>'+Array.from(n.children).map(draw).join('')+'</'+tag+'>';
    }
    const svg=draw(el);
    if(svg.length>100000)throw Error('complex SVG');
    return svg;
  }
  function textRuns(node, style, id, path) {
    const text=node.textContent;
    if(!text.trim())return;
    const range=document.createRange(); range.selectNodeContents(node);
    const runs=Array.from(range.getClientRects()).filter(r=>r.width>0&&r.height>0);
    if(!runs.some(r=>intersects(box(r))))return;
    // Browser line boxes supply the wrap positions. Group adjacent characters on
    // the same baseline so inline links, weights and wrapped runs stay editable.
    let segment, serial=0;
    function finish(){
      if(!segment)return;
      const value=segment.characters.replace(/\s+/g,' ');
      if(value.trim() && intersects(segment.box)) push({id:id+'-t'+(++serial),path,kind:'text',
        box:segment.box,text:typography(style,value)});
      segment=null;
    }
    if(runs.length===1){
      segment={characters:text,box:box(runs[0])}; finish(); return;
    }
    for(let i=0;i<text.length;){
      const len=text.codePointAt(i)>65535?2:1;
      range.setStart(node,i); range.setEnd(node,i+len);
      const r=box(range.getBoundingClientRect()),ch=text.slice(i,i+len); i+=len;
      if(!r.width||!r.height)continue;
      if(!segment||Math.abs(r.y-segment.box.y)>1||r.x>segment.box.x+segment.box.width+1){
        finish();segment={characters:ch,box:r};
      }else{
        segment.characters+=ch;
        const end=Math.max(segment.box.x+segment.box.width,r.x+r.width);
        segment.box.x=Math.min(segment.box.x,r.x); segment.box.width=round(end-segment.box.x);
      }
    }
    finish();
  }
  let serial=0;
  function visit(el, path) {
    const tag=el.tagName.toLowerCase();
    if(['script','style','noscript','template','head','iframe'].includes(tag))return;
    const s=getComputedStyle(el);
    if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0)return;
    const b=box(el.getBoundingClientRect()),id='el-'+(++serial);
    const visible=intersects(b);
    if(!visible && (['hidden','clip','scroll','auto'].includes(s.overflowY)||tag==='svg'))return;
    let childrenPath=path;
    if(visible){
      if(s.backgroundImage!=='none')limitations.add('background image or gradient');
      if(s.boxShadow!=='none')limitations.add('CSS shadow');
      if(tag==='svg'){
        try{push({id,path,kind:'vector',box:b,svg:simpleVector(el)});}catch(error){if(String(error).includes('budget'))throw error;limitations.add('complex SVG');}
        return;
      }
      if(tag==='img'){
        const src=el.currentSrc||el.src;
        if(el.complete&&el.naturalWidth>0 && src){
          const u=new URL(src,location.href);
          if(u.origin===location.origin){unboundImages.push({id,path,box:b,requestTarget:u.pathname+u.search,alt:el.alt||'',paint:paint(s),position:elements.length});}
          else limitations.add('external raster');
        }else limitations.add('unloaded image');
        return;
      }
      if(tag==='video'||tag==='canvas'){limitations.add(tag+' content');return;}
      const p=paint(s);
      if(p.borderRadius)p.borderRadius=round(Math.min(p.borderRadius,b.width/2,b.height/2));
      const label=el.textContent.trim().replace(/\s+/g,' ');
      const isControl=(tag==='a'||tag==='button'||el.getAttribute('role')==='button');
      if(isControl && el.getClientRects().length===1 && label && label.length<=90 && !el.querySelector('svg,img,picture,input,select,textarea,video,button') && el.children.length<=1){
        // Reuse visually equivalent controls only. Identity also contains geometry
        // when its height and visual treatment match a prior control.
        const text=typography(s,label);const signature=JSON.stringify([tag,b.height,p,text.fontFamily,text.fontSize,text.fontWeight,text.color,text.textAlignHorizontal]);
        push({id,kind:'component',path,box:b,paint:p,text,componentKey:signature,props:{label}});return;
      }
      if(Object.keys(p).length || ['main','section','article','nav','header','footer','aside','form'].includes(tag)){
        push({id,path,kind:'frame',box:b,paint:p});childrenPath=[...path,id];
      }
      if(tag==='input'||tag==='textarea'){
        // Never inspect the value of a form control.
        if(el.placeholder)push({id:id+'-placeholder',path:childrenPath,kind:'text',box:{...b,x:b.x+numeric(s.paddingLeft),width:Math.max(1,b.width-numeric(s.paddingLeft)-numeric(s.paddingRight))},text:typography(s,el.placeholder)});
        return;
      }
    }
    let index=0;
    for(const child of el.childNodes){
      if(child.nodeType===1)visit(child,childrenPath);
      if(child.nodeType===3)textRuns(child,s,id+'-'+index,childrenPath);
      index++;
    }
  }
  visit(document.body,[]);
  return {screen:{id:screenId,type:'screen',title:document.title,status:'observed',
      layout:{width,height,background:color(getComputedStyle(document.body).backgroundColor)||color(getComputedStyle(document.documentElement).backgroundColor)||'#ffffff'},elements},
    images:unboundImages,limitations:[...limitations].sort(),origin:location.origin,pathname:location.pathname,
    extent,viewport:{width:innerWidth,height:innerHeight},observedAt:new Date().toISOString()};
}
if(typeof module!=='undefined')module.exports={captureWebDesign};
