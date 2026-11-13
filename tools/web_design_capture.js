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
  const elements = [], unboundImages = [], canvases = [], limitations = new Set();
  const round = v => Math.round(v * 100) / 100;
  const numeric = (value, fallback = 0) => Number.isFinite(Number.parseFloat(value)) ? Number.parseFloat(value) : fallback;
  function color(css, includeTransparent = false) {
    if (!css || css === 'none') return null;
    if (css === 'transparent') return includeTransparent ? '#00000000' : null;
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
    if (alpha <= 0) return includeTransparent ? '#00000000' : null;
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
    if (elements.length + unboundImages.length + canvases.length >= maxLayers) throw Error('Screen exceeds the approved layer budget. Choose a smaller viewport or section.');
    elements.push({...layer,path:[...layer.path]});
  }
  function mediaCandidate(candidate) {
    if(elements.length+unboundImages.length+canvases.length>=maxLayers)throw Error('Screen exceeds the approved layer budget.');
    unboundImages.push(candidate);
  }
  function mediaLoaded(url) {
    try { return typeof performance!=='undefined' && performance.getEntriesByName(url).length>0; }
    catch (_) { return false; }
  }
  function firstLinearGradient(value) {
    const start=value.indexOf('linear-gradient(');if(start<0)return null;
    let depth=0;
    for(let i=start;i<value.length;i++){
      if(value[i]==='(')depth++;else if(value[i]===')'){depth--;if(depth===0)return value.slice(start,i+1);}
    }
    return null;
  }
  function firstTextGradient(value) {
    const starts=['linear-gradient(','radial-gradient('].map(token=>value.indexOf(token)).filter(index=>index>=0);
    if(!starts.length)return null;
    const start=Math.min(...starts);let depth=0;
    for(let i=start;i<value.length;i++){
      if(value[i]==='(')depth++;else if(value[i]===')'){depth--;if(depth===0)return value.slice(start,i+1);}
    }
    return null;
  }
  function splitCssList(value) {
    const parts=[];let start=0,depth=0;
    for(let i=0;i<value.length;i++){
      if(value[i]==='(')depth++;else if(value[i]===')')depth--;
      else if(value[i]===','&&depth===0){parts.push(value.slice(start,i).trim());start=i+1;}
    }
    parts.push(value.slice(start).trim());return parts;
  }
  function linearGradient(value) {
    const match=/^linear-gradient\(\s*(-?[\d.]+)deg\s*,\s*(.*)\)$/.exec(value);if(!match)return null;
    const stops=[];
    for(const part of splitCssList(match[2])){
      const row=/^(.*?)(?:\s+([\d.]+)%)?$/.exec(part);if(!row)return null;
      const parsed=color(row[1].trim(),true);if(!parsed)return null;
      stops.push({position:row[2]===undefined?null:Number(row[2])/100,color:parsed});
    }
    if(stops.length<2||stops.length>16)return null;
    if(stops[0].position===null)stops[0].position=0;
    if(stops.at(-1).position===null)stops.at(-1).position=1;
    for(let i=1;i<stops.length-1;){
      if(stops[i].position!==null){i++;continue;}
      let end=i+1;while(end<stops.length&&stops[end].position===null)end++;
      const from=i-1,step=(stops[end].position-stops[from].position)/(end-from);
      for(let j=i;j<end;j++)stops[j].position=stops[from].position+step*(j-from);i=end;
    }
    if(stops.some((stop,i)=>stop.position<0||stop.position>1||(i>0&&stop.position<stops[i-1].position)))return null;
    return {angle:(Number(match[1])%360+360)%360,stops:stops.map(stop=>({position:stop.position,color:stop.color}))};
  }
  function typography(style, characters) {
    const clipped=style.backgroundClip==='text'||style.webkitBackgroundClip==='text';
    const cssGradient=clipped?firstTextGradient(style.backgroundImage||''):null;
    const gradient=cssGradient?.startsWith('linear-gradient(')?linearGradient(cssGradient):null;
    const text={characters, fontFamily:style.fontFamily.split(',')[0].trim().replace(/^['"]|['"]$/g,''),
      fontWeight:numeric(style.fontWeight,400),fontSize:numeric(style.fontSize,16),
      lineHeight:numeric(style.lineHeight,numeric(style.fontSize,16)*1.2),
      textAlignHorizontal:({center:'center',right:'right',end:'right'})[style.textAlign]||'left',
      color:gradient?undefined:color(style.color)||'#000000'};
    if(gradient)text.linearGradient=gradient;
    else if(clipped){
      const first=cssGradient;
      const stop=first&&splitCssList(first.slice(first.indexOf(',')+1,first.length-1))[0];
      const representative=stop&&color(stop.replace(/\s+[\d.]+%$/,''),true)
        ||color(style.color)||color(style.backgroundColor);
      if(representative){text.color=representative;text.paintApproximation='first-gradient-stop';}
      limitations.add('text gradient approximated as a solid color');
    }
    return text;
  }
  function radialGradient(value) {
    // Browser-computed percentage centers and stops. Commas inside CSS
    // color functions belong to the color, not to the list of stops.
    const gradient = /^radial-gradient\((?:(?:ellipse(?:\s+farthest-corner)?)\s+)?(?:at ([\d.]+)% ([\d.]+)%,\s*)?(.*)\)$/.exec(value);
    if (!gradient) return null;
    const stops = [];
    for (const entry of gradient[3].split(/,\s*(?![^()]*\))/)) {
      const match = /^(.*) (\d+(?:\.\d+)?)%$/.exec(entry.trim());
      if (!match) return null;
      const hex = color(match[1], true);
      const position = Number(match[2]) / 100;
      if (!hex || position > 1 || (stops.length && position < stops[stops.length - 1].position)) return null;
      stops.push({position, color: hex});
    }
    const centerX = gradient[1] === undefined ? 0.5 : Number(gradient[1]) / 100;
    const centerY = gradient[2] === undefined ? 0.5 : Number(gradient[2]) / 100;
    return stops.length >= 2 && stops.length <= 16 && centerX <= 1 && centerY <= 1
      ? {centerX, centerY, stops} : null;
  }
  function alphaMask(value) {
    const match=/^linear-gradient\((?:(-?[\d.]+)deg,\s*)?(.*)\)$/.exec(value);if(!match)return null;
    const stops=[];
    for(const part of match[2].split(/,\s*(?![^()]*\))/)){
      const stop=/^(.*?)(?:\s+([\d.]+)%)?$/.exec(part.trim());if(!stop)return null;
      const c=color(stop[1].trim(),true),position=stop[2]===undefined?null:Number(stop[2])/100;
      if(!c||position!==null&&(position<0||position>1||stops.length&&position<stops.at(-1).position))return null;
      stops.push({position,color:c});
    }
    if(stops.length) { if(stops[0].position===null)stops[0].position=0; if(stops.at(-1).position===null)stops.at(-1).position=1; }
    for(let i=1;i<stops.length-1;){if(stops[i].position!==null){i++;continue;}let end=i+1;while(end<stops.length&&stops[end].position===null)end++;const start=i-1,step=(stops[end].position-stops[start].position)/(end-start);for(let j=i;j<end;j++)stops[j].position=stops[start].position+step*(j-start);i=end;}
    const angle=((Number(match[1]??180)%360)+360)%360;
    return stops.length>=2&&stops.length<=16&&[90,180].includes(angle)?{angle,stops}:null;
  }
  function maskGradient(value,bounds) {
    const linear = alphaMask(value);
    if (linear) return { kind: 'linear', ...linear };
    const radial = radialGradient(value);
    if (radial) return { kind: 'radial', ...radial };
    return radialCircleMask(value, bounds);
  }
  function radialCircleMask(value, bounds) {
    const match=/^radial-gradient\(circle(?:\s+at ([\d.]+)% ([\d.]+)%)?,\s*(.*)\)$/.exec(value);
    if(!match||!bounds||Math.abs(bounds.width-bounds.height)>.01)return null;
    const centerX=match[1]===undefined ? .5 : Number(match[1])/100;
    const centerY=match[2]===undefined ? .5 : Number(match[2])/100;
    if(centerX!==.5||centerY!==.5)return null;
    const radius=Math.hypot(bounds.width/2,bounds.height/2),stops=[];
    for(const entry of splitCssList(match[3])){
      const stop=/^(.*?)\s+(-?(?:\d+(?:\.\d*)?|\.\d+))(px|%)$/.exec(entry);
      if(!stop)return null;
      const parsedColor=color(stop[1].trim(),true),raw=Number(stop[2]);
      if(!parsedColor||raw<0)return null;
      const position=stop[3]==='px'?raw/radius:raw/100;
      if(position>1)return null;
      stops.push({position:stops.length?Math.max(position,stops.at(-1).position):position,color:parsedColor});
    }
    return stops.length>=2&&stops.length<=16?{kind:'radial',centerX,centerY,stops}:null;
  }
  function cssFunctions(value) {
    const result=[];let i=0;
    while(i<value.length){
      while(/\s/.test(value[i]||''))i++;
      const head=/^([a-z-]+)\(/i.exec(value.slice(i));if(!head)return null;
      const name=head[1],start=i+head[0].length;let depth=1,end=start;
      for(;end<value.length&&depth;end++){if(value[end]==='(')depth++;else if(value[end]===')')depth--;}
      if(depth)return null;
      result.push([name,value.slice(start,end-1).trim()]);i=end;
    }
    return result;
  }
  function colorFilterChain(tokens) {
    const operations=[];
    for(const [name,arg] of tokens||[]){
      const match=/^((?:\d+(?:\.\d*)?|\.\d+))(%)?(deg)?$/.exec(arg);
      if(!match)return null;
      const value=Number(match[1])/(match[2]?100:1),unit=match[3]?'deg':match[2]?'%':'';
      if(!Number.isFinite(value))return null;
      const allowed={brightness:unit!=='deg'&&value>=0,contrast:unit!=='deg'&&value>=0,saturate:unit!=='deg'&&value>=0,
        grayscale:unit!=='deg'&&value>=0&&value<=1,sepia:unit!=='deg'&&value>=0&&value<=1,
        invert:unit!=='deg'&&value>=0&&value<=1,opacity:unit!=='deg'&&value>=0&&value<=1,
        'hue-rotate':unit==='deg'||(unit===''&&value===0)};
      if(!allowed[name])return null;
      operations.push({name,value});
    }
    return operations.length?operations:null;
  }
  function filterColor(value, operations) {
    const hex=value?.slice(1)||'';if(!/^[\da-f]{6}(?:[\da-f]{2})?$/i.test(hex))return value;
    let c=[0,2,4].map(i=>Number.parseInt(hex.slice(i,i+2),16)/255),a=hex.length===8?Number.parseInt(hex.slice(6,8),16)/255:1;
    const clamp=n=>Math.max(0,Math.min(1,n));
    for(const {name,value:v} of operations){
      if(name==='brightness')c=c.map(x=>x*v);
      else if(name==='contrast')c=c.map(x=>(x-.5)*v+.5);
      else if(name==='saturate'||name==='grayscale'){
        const s=name==='grayscale'?1-v:v,[r,g,b]=c,l=.2126*r+.7152*g+.0722*b;
        c=[l+(r-l)*s,l+(g-l)*s,l+(b-l)*s];
      }else if(name==='sepia'){
        const t=v,[r,g,b]=c;c=[r*(1-.607*t)+g*.769*t+b*.189*t,
          r*.349*t+g*(1-.314*t)+b*.168*t,r*.272*t+g*.534*t+b*(1-.869*t)];
      }else if(name==='invert')c=c.map(x=>x*(1-2*v)+v);
      else if(name==='opacity')a*=v;
      else if(name==='hue-rotate'){
        const t=v*Math.PI/180,cos=Math.cos(t),sin=Math.sin(t),[r,g,b]=c;
        c=[r*(.213+cos*.787-sin*.213)+g*(.715-cos*.715-sin*.715)+b*(.072-cos*.072+sin*.928),
          r*(.213-cos*.213+sin*.143)+g*(.715+cos*.285+sin*.140)+b*(.072-cos*.072-sin*.283),
          r*(.213-cos*.213-sin*.787)+g*(.715-cos*.715+sin*.715)+b*(.072+cos*.928+sin*.072)];
      }
      c=c.map(clamp);a=clamp(a);
    }
    const out=c.map(n=>Math.round(n*255).toString(16).padStart(2,'0')).join('');
    return '#'+out+(a<1?Math.round(a*255).toString(16).padStart(2,'0'):'');
  }
  function paint(style, allowColorFilters=false, bounds=null) {
    const p={},bg=color(style.backgroundColor),border=numeric(style.borderTopWidth);
    if (bg) p.background=bg;
    if (style.backgroundImage !== 'none') {
      const radial = radialGradient(style.backgroundImage);
      if (radial) p.radialGradient = radial;
      else limitations.add('background image or unsupported gradient');
    }
    if(style.maskImage&&style.maskImage!=='none'){
      const layers=splitCssList(style.maskImage).map(value=>maskGradient(value,bounds));
      const composites=String(style.maskComposite||'add').split(/,\s*/).map(value=>value.trim());
      const compositeSupported=layers.length===1 || composites.length>=layers.length-1
        && composites.slice(0,layers.length-1).every(value=>value==='intersect');
      if(layers.length&&layers.every(Boolean)&&compositeSupported){
        if(layers.length===1&&layers[0].kind==='linear')p.alphaMask={angle:layers[0].angle,stops:layers[0].stops};
        else {p.alphaMasks=layers;p.alphaMaskComposite='intersect';}
      }else limitations.add('unsupported CSS mask composition or layer');
    }
    if (border>0 && style.borderTopStyle!=='none') {
      const stroke=color(style.borderTopColor);
      if(stroke){p.borderWidth=border;p.borderColor=stroke;}
    }
    const radius=numeric(style.borderTopLeftRadius);
    if(radius>0)p.borderRadius=radius;
    if(numeric(style.opacity,1)<1)p.opacity=numeric(style.opacity,1);
    const effects=[];
    const splitFunctions=value=>value.match(/(?:rgba?\([^)]*\)|[^,])+/g)?.map(x=>x.trim())||[];
    const shadow=(part,type)=>{
      const colorMatch=part.match(/rgba?\([^)]*\)|#[\da-f]{3,8}|\b(?:black|white|transparent)\b/i);
      const nums=(part.replace(colorMatch?.[0]||'', '').match(/-?(?:\d*\.)?\d+px/g)||[]).map(x=>Number.parseFloat(x));
      if(nums.length<2||nums.length>4)return null;
      const c=color(colorMatch?.[0]||'rgba(0,0,0,.25)',true);if(!c)return null;
      return {type,x:nums[0],y:nums[1],blur:nums[2]||0,spread:nums[3]||0,color:c};
    };
    if(style.boxShadow&&style.boxShadow!=='none'){
      const parts=splitFunctions(style.boxShadow);
      if(parts.length<=8){for(const part of parts){const inset=/\binset\b/.test(part);const e=shadow(part,inset?'INNER_SHADOW':'DROP_SHADOW');if(e)effects.push(e);else limitations.add('unsupported CSS shadow');}}
      else limitations.add('unsupported CSS shadow');
    }
    if(style.filter&&style.filter!=='none'){
      const tokens=cssFunctions(style.filter);
      const colorFilters=colorFilterChain(tokens);
      let supported=!!tokens&&tokens.length>0&&!colorFilters;
      const parsed=[];
      for(const [fn,arg] of tokens||[]){
        if(fn==='blur'&&/^\d+(?:\.\d+)?px$/.test(arg))parsed.push({type:'LAYER_BLUR',radius:Number.parseFloat(arg)});
        else if(fn==='drop-shadow'){const e=shadow(arg,'DROP_SHADOW');if(e)parsed.push(e);else supported=false;}
        else supported=false;
      }
      if(colorFilters&&allowColorFilters&&style.boxShadow==='none'&&style.backgroundImage==='none'){
        if(p.background)p.background=filterColor(p.background,colorFilters);
        const borderColor=color(style.borderTopColor);
        if(borderColor)p.borderColor=filterColor(borderColor,colorFilters);
      }else if(supported&&effects.length+parsed.length<=8&&parsed.every(effect=>effect.type!=='LAYER_BLUR'||effect.radius<=100))effects.push(...parsed);
      else limitations.add('unsupported CSS filter chain');
    }
    if(effects.length)p.effects=effects;
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
    if(b.width<=1&&b.height<=1&&/rect\(0(?:px)?,\s*0(?:px)?,\s*0(?:px)?,\s*0(?:px)?\)/.test(s.clip||''))return;
    const visible=intersects(b);
    if(!visible && (['hidden','clip','scroll','auto'].includes(s.overflowY)||tag==='svg'))return;
    let childrenPath=path;
    if(visible){
      if(tag==='svg'){
        if(s.maskImage&&s.maskImage!=='none')limitations.add('unsupported CSS mask on SVG');
        if(s.filter&&s.filter!=='none')limitations.add('unsupported CSS filter on SVG');
        if(s.boxShadow&&s.boxShadow!=='none')limitations.add('unsupported CSS shadow on SVG');
        try{push({id,path,kind:'vector',box:b,svg:simpleVector(el)});}catch(error){if(String(error).includes('budget'))throw error;limitations.add('complex SVG');}
        return;
      }
      if(s.backgroundImage&&s.backgroundImage!=='none'&&/url\(/.test(s.backgroundImage)){
        const urls=[...s.backgroundImage.matchAll(/url\(["']?(.*?)["']?\)/g)].map(match=>match[1]);
        for(const [index,src] of urls.entries()){
          try{const url=new URL(src,location.href);mediaCandidate({id:`${id}-background-${index+1}`,path:[...path],box:b,
            requestTarget:url.href,status:mediaLoaded(url.href)?'loaded':'unloaded',mediaKind:'background',alt:'',objectFit:'cover',paint:paint(s,false,b),position:elements.length});}
          catch(_){limitations.add('invalid CSS background media URL');}
        }
      }
      if(tag==='img'){
        const src=el.currentSrc||el.src;
        if(src){
          let requestTarget;
          try{requestTarget=new URL(src,location.href).href;}catch(_){requestTarget=null;}
          const loaded=!!(el.complete&&el.naturalWidth>0);
          const objectFit=s.objectFit==='contain'?'contain':'cover';
          if(loaded&&Math.abs(el.naturalWidth/el.naturalHeight-b.width/b.height)>.02&&!['contain','cover'].includes(s.objectFit))limitations.add('approximated image fit');
          mediaCandidate({id,path:[...path],box:b,requestTarget,status:loaded?'loaded':'unloaded',mediaKind:'image',alt:el.alt||'',objectFit,paint:paint(s,false,b),position:elements.length});
        }else limitations.add('image without a request URL');
        return;
      }
      if(tag==='video'){
        const source=el.currentSrc||el.querySelector('source')?.src||'';
        let requestTarget=null,fallbackRequestTarget=null;
        try{if(source)requestTarget=new URL(source,location.href).href;if(el.poster)fallbackRequestTarget=new URL(el.poster,location.href).href;}catch(_){limitations.add('invalid video media URL');}
        if(!requestTarget)limitations.add('video without a source');
        const loaded=!!(el.readyState>0)||(requestTarget&&mediaLoaded(requestTarget));
        mediaCandidate({id,path:[...path],box:b,requestTarget,status:requestTarget&&loaded?'loaded':'unloaded',mediaKind:'video',
          ...(fallbackRequestTarget?{fallbackRequestTarget}:{}),alt:'',objectFit:'cover',paint:paint(s,false,b),position:elements.length});
        return;
      }
      if(tag==='canvas'){
        if(elements.length+unboundImages.length+canvases.length>=maxLayers)throw Error('Screen exceeds the approved layer budget.');
        const candidate={id,path:[...path],box:b,paint:paint(s,false,b),position:elements.length+unboundImages.length+canvases.length,
          canvas:{width:el.width,height:el.height,devicePixelRatio:typeof devicePixelRatio==='number'?devicePixelRatio:1,
            pixelRatioX:b.width?el.width/b.width:null,pixelRatioY:b.height?el.height/b.height:null,
            captureMode:'canvas.toDataURL',status:'unavailable'}};
        if(el.width>0&&el.height>0){
          try{
            const dataUrl=el.toDataURL('image/png');
            if(typeof dataUrl==='string'&&dataUrl.startsWith('data:image/png;base64,')){
              const bytes=(dataUrl.length-'data:image/png;base64,'.length)*.75;
              if(bytes>8_000_000)candidate.canvas.reason='canvas PNG exceeds the 8 MB asset limit';
              else{candidate.canvas.status='captured';candidate.canvas.mimeType='image/png';candidate.canvas.dataUrl=dataUrl;}
            }else candidate.canvas.reason='browser returned a non-PNG canvas data URL';
          }catch(error){candidate.canvas.reason=error?.name==='SecurityError'?'canvas is not origin-clean':'canvas pixel export failed';}
        }else candidate.canvas.reason='canvas has zero intrinsic width or height';
        canvases.push(candidate);
        if(candidate.canvas.status!=='captured')limitations.add('canvas pixels unavailable');
        return;
      }
      const colorOnlyLeaf=el.children.length===0&&!el.textContent.trim();
      const p=paint(s,colorOnlyLeaf,b);
      if(p.borderRadius)p.borderRadius=round(Math.min(p.borderRadius,b.width/2,b.height/2));
      const label=el.textContent.trim().replace(/\s+/g,' ');
      const isControl=(tag==='a'||tag==='button'||el.getAttribute('role')==='button');
      if(isControl && el.getClientRects().length===1 && label && label.length<=90 && !el.querySelector('svg,img,picture,input,select,textarea,video,button') && el.children.length<=1){
        // Reuse visually equivalent controls only. Identity also contains geometry
        // when its height and visual treatment match a prior control.
        const labelRange=document.createRange();labelRange.selectNodeContents(el);
        const measured=box(labelRange.getBoundingClientRect());
        const labelBox={x:round(measured.x-b.x),y:round(measured.y-b.y),width:measured.width,height:measured.height};
        const text=typography(s,label);const roleToken=tag==='a'?'link':'button';
        push({id,kind:'component',path,box:b,paint:p,text,componentKey:'control-'+roleToken,props:{label,labelBox}});return;
      }
      const clips = ['hidden','clip'].includes(s.overflowX) && ['hidden','clip'].includes(s.overflowY);
      if(Object.keys(p).length || clips || ['main','section','article','nav','header','footer','aside','form'].includes(tag)){
        push({id,path,kind:'frame',name:el.getAttribute('aria-label')?.slice(0,100)||tag,clipsContent:clips,box:b,paint:p});childrenPath=[...path,id];
      }
      if(tag==='input'||tag==='textarea'){
        // Never inspect the value of a form control.
        if(el.placeholder)push({id:id+'-placeholder',path:childrenPath,kind:'text',box:{...b,x:b.x+numeric(s.paddingLeft)+numeric(s.borderLeftWidth),y:b.y+(b.height-numeric(s.lineHeight,numeric(s.fontSize)*1.2))/2,height:numeric(s.lineHeight,numeric(s.fontSize)*1.2),width:Math.max(1,b.width-numeric(s.paddingLeft)-numeric(s.paddingRight)-numeric(s.borderLeftWidth)-numeric(s.borderRightWidth))},text:typography(s,el.placeholder)});
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
    images:unboundImages,canvases,limitations:[...limitations].sort(),origin:location.origin,pathname:location.pathname,
    extent,viewport:{width:innerWidth,height:innerHeight},scrollPosition:{x:scrollX,y:scrollY},observedAt:new Date().toISOString()};
}
if(typeof module!=='undefined')module.exports={captureWebDesign};
