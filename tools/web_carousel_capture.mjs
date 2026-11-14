// Measure a CSS scroll-snap carousel using a private Chromium pipe.
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as pause } from 'node:timers/promises';

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const help = `node tools/web_carousel_capture.mjs --url URL --rail SELECTOR --out NEW_DIRECTORY --interval-ms N [--first-card TITLE] [--chrome EXECUTABLE] [--width 390 --height 844]
Capture a mobile CSS scroll-snap rail with 2–16 direct child cards and an autoplay timer.
Writes browser screenshots, measured WEB screens, transition receipts and carousel-graph.json.
Requires Chromium, Node and Python on PATH. No browser extension or account is required.`;

function connect(proc) {
  let seq = 0;
  let buf = '';
  const requests = new Map();
  proc.stdio[4].setEncoding('utf8').on('data', chunk => {
    buf += chunk;
    let i;
    while ((i = buf.indexOf('\0')) >= 0) {
      const msg = JSON.parse(buf.slice(0, i));
      buf = buf.slice(i + 1);
      const pending = requests.get(msg.id);
      if (pending) {
        requests.delete(msg.id);
        clearTimeout(pending.timer);
        if (msg.error) pending.reject(Error(msg.error.message));
        else pending.resolve(msg.result);
      }
    }
  });
  function abort(error) {
    for (const { reject, timer } of requests.values()) { clearTimeout(timer); reject(error); }
    requests.clear();
  }
  proc.on('error', abort);
  proc.once('exit', () => abort(Error('Chromium exited before capture completed')));
  return (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { requests.delete(id); reject(Error('Chromium timed out at ' + method)); }, 20000);
    if (proc.exitCode !== null || proc.signalCode !== null || proc.stdio[3].destroyed) {
      clearTimeout(timer);
      reject(Error('Chromium is no longer running'));
      return;
    }
    requests.set(id, { resolve, reject, timer });
    proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + '\0');
  });
}

// Evaluated inside the inspected page. State is the card nearest the rail's center.
function inspectRail(selector, align, firstCard) {
  const rails = Array.from(document.querySelectorAll(selector)).filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth
    && (!firstCard || el.firstElementChild?.innerText.trim().startsWith(firstCard)));
  if (rails.length !== 1) return null;
  const rail = rails[0];
  const before = rail.getBoundingClientRect();
  const targetY = Math.min(innerHeight * .48, Math.max(0, innerHeight - before.height));
  if (align || Math.abs(before.y - targetY) > 1)
    window.scrollBy({ top: before.y - targetY, behavior: 'instant' });
  const { x, y, width, height } = rail.getBoundingClientRect();
  const cards = Array.from(rail.children).map((el, index) => {
    const box = el.getBoundingClientRect();
    return { index, title: (el.querySelector('h1,h2,h3,h4,h5,h6')?.innerText || el.innerText || '').trim().split('\n')[0],
      offset: box.x + box.width / 2 - x - width / 2 };
  });
  const active = cards.reduce((a, b) => Math.abs(a.offset) < Math.abs(b.offset) ? a : b, cards[0]);
  if (!active) return null;
  return { index: active.index, offset: active.offset, scroll: rail.scrollLeft, cards: cards.map(c => c.title),
    rail: { x, y, width, height }, title: document.title, url: location.href, dpr: devicePixelRatio,
    viewport: { width: innerWidth, height: innerHeight }, observedAt: new Date().toISOString() };
}

async function capture(options, out, interval, width, height) {
  const binary = options.chrome || process.env.CHROME_BIN ||
    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/chromium', '/usr/bin/google-chrome',
     process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google/Chrome/Application/chrome.exe')].filter(Boolean).find(existsSync);
  if (!binary) throw Error('Specify the installed Chromium executable with --chrome');
  const profile = await mkdtemp(path.join(os.tmpdir(), 'figma-flow-chromium-'));
  const proc = spawn(binary, ['--headless=new', '--remote-debugging-pipe', '--no-first-run',
    '--no-default-browser-check', '--user-data-dir=' + profile, 'about:blank'], { stdio: ['ignore','ignore','ignore','pipe','pipe'] });
  const send = connect(proc);
  try {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const command = (method, params) => send(method, params, sessionId);
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
      return result.result.value;
    };
    const rail = (align = false) => evaluate('(' + inspectRail.toString() + ')(' + JSON.stringify(options.rail) + ',' + align + ',' + JSON.stringify(options['first-card'] || '') + ')');
    const { product } = await send('Browser.getVersion');
    await command('Page.enable');
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: true });
    await command('Emulation.setTouchEmulationEnabled', { enabled: true });
    await command('Page.navigate', { url: options.url });
    const until = async (read, end, error) => {
      while (Date.now() < end) {
        const value = await read();
        if (value) return value;
        await pause(90);
      }
      throw Error(error);
    };
    const initial = await until(() => rail(true), Date.now()+20000, 'No unique visible scrollable rail matches --rail');
    await evaluate('document.fonts.ready.then(() => true)');
    if (initial.cards.length < 2 || initial.cards.length > 16 || initial.cards.some(t => !t)) throw Error('Expected 2–16 named cards');
    const count = initial.cards.length;
    const ids = initial.cards.map((_, i) => 'WEB-saas-feature-' + (i + 1));
    const fixed = await readFile(path.join(toolsDir, 'web_design_capture.js'), 'utf8');
    const output = async (name, bytes) => { await writeFile(path.join(out, name), bytes, {flag:'wx', mode:0o600});
      return {path:name, sha256:createHash('sha256').update(bytes).digest('hex')}; };
    const screenshot = async name => output(name, Buffer.from((await command('Page.captureScreenshot', { format:'png' })).data,'base64'));
    const captures = new Map(), edges = new Map(), trace = [];
    const firstTick = Date.now();
    let last, lastStable, boundaryTime;
    const fullIntervals = [];
    const edge = async (from,to,input,detail) => {
      const key = from + ':' + input;
      if (edges.has(key)) return;
      const evidence = await screenshot('event-' + from + '-' + input + '.png');
      edges.set(key,{from:ids[from],to:ids[to],input,observed:true,evidence});trace.push({from,to,input,...detail,evidence});
    };
    // Ignore transient centers crossed while an animated last-to-first scroll is in flight.
    const deadline = Date.now() + interval * (count + 3) + 15000;
    while (Date.now() < deadline) {
      const s = await rail();
      if (s && last && s.index===last.index && Math.abs(s.offset)<2 && Math.abs(s.scroll-last.scroll)<0.25) {
        if (lastStable && lastStable.index !== s.index && s.index === (lastStable.index + 1) % count) {
          const elapsedMs = Date.now() - boundaryTime;
          if (edges.size) fullIntervals.push(elapsedMs);
          await edge(lastStable.index, s.index, 'autoplay', {before:lastStable, after:s, elapsedMs});
        }
        if (!lastStable || lastStable.index!==s.index) boundaryTime=Date.now();
        lastStable=s;
        if (!captures.has(s.index)) {
          const id=ids[s.index];
          const data=await evaluate('(() => {'+fixed+';return captureWebDesign('+JSON.stringify({screenId:id,extent:'viewport'})+');})()');
          const snap=await screenshot('state-'+(s.index+1)+'.png');
          const after=await rail();
          if (after.index!==s.index || Math.abs(after.scroll-s.scroll)>1 || Math.abs(after.rail.y - s.rail.y)>1) throw Error('State changed while recording '+id+'; rerun in a fresh output directory');
          data.screen.title=s.cards[s.index];
          await output(id+'.json',JSON.stringify(data));
          captures.set(s.index,{id,capture:snap});
        }
      }
      last=s;
      if (captures.size===count && edges.has((count-1)+':autoplay') && edges.size===count) break;
      await pause(125);
    }
    if (captures.size!==count || edges.size!==count) throw Error('Autoplay did not produce the complete ordered loop in the observation window');
    const sortedIntervals = fullIntervals.toSorted((a, b) => a - b);
    const measuredInterval = sortedIntervals[Math.floor(sortedIntervals.length / 2)];
    if (!Number.isFinite(measuredInterval) || Math.abs(measuredInterval - interval) > Math.max(500, interval * .2)) {
      throw Error('Observed autoplay cadence differs from --interval-ms; inspect the page timing and retry');
    }
    const swipe = async (from,input) => {
      const start=await until(async()=>{const s=await rail();return s.index===from && Math.abs(s.offset)<1.5 && s;},Date.now()+interval*(count+1),'Required source card did not settle');
      const r=start.rail, y=r.y+r.height/2, left=r.x+r.width*0.13, right=r.x+r.width*.87;
      const [x0,x1]=input==='swipe-left'?[right,left]:[left,right];
      const hit=await evaluate('(() => {const p=document.elementFromPoint('+x0+','+y+');return !!p?.closest('+JSON.stringify(options.rail)+')})()');
      if (!hit) throw Error('Gesture start is outside the measured carousel');
      const touch=(type,x)=>command('Input.dispatchTouchEvent',{type,touchPoints:x===null?[]:[{x,y}]});
      await touch('touchStart',x0);
      for(let i=1;i<=12;i++){await touch('touchMove',x0+(x1-x0)*i/12);await pause(27);}
      await touch('touchEnd',null);await pause(450);
      let previous;
      const settled=await until(async()=>{const s=await rail();const stable=previous && Math.abs(s.offset)<2 && Math.abs(previous.scroll-s.scroll)<.25;previous=s;return stable && s;},Date.now()+1500,'Drag did not settle');
      await edge(from,settled.index,input,{before:start,after:settled,hitTest:hit});
      return settled.index;
    };
    // Start at the beginning of a fresh timer window so timeout cannot be mistaken for touch input.
    const waitCycle=async()=>{await until(async()=>{const s=await rail();return s.index===count-1 && Math.abs(s.offset)<2;},Date.now()+interval*(count+1),'Last card missing');await until(async()=>{const s=await rail();return s.index===0 && Math.abs(s.offset)<2;},Date.now()+interval*2,'First card missing');};
    await waitCycle();
    const backAtStart=await swipe(0,'swipe-right');
    if(backAtStart!==0 && backAtStart!==count-1) throw Error('Unexpected manual starting boundary');
    for(let i=0;i<count-1;i++) if(await swipe(i,'swipe-left')!==i+1) throw Error('Manual forward gesture did not reach the adjacent card');
    const forwardAtEnd=await swipe(count-1,'swipe-left');
    const manualWrap=forwardAtEnd===0;
    if ((!manualWrap && forwardAtEnd!==count-1) || (backAtStart===count-1)!==manualWrap) throw Error('Asymmetric manual boundary needs an explicit interaction graph');
    for(let i=count-1;i>0;i--) if(await swipe(i,'swipe-right')!==i-1) throw Error('Reverse gesture did not reach the adjacent card');
    const observations={schemaVersion:1,source:{url:initial.url,title:initial.title,browser:product,viewport:initial.viewport,dpr:initial.dpr,capturedAt:new Date(firstTick).toISOString()},
      carousel:{frameKey:'feature-carousel',stateIds:ids,initialState:ids[initial.index],intervalMs:interval,manualWrap,wrapAutoplay:true,rail:{rect:lastStable.rail}},
      states:ids.map((_,i)=>captures.get(i)),transitions:[...edges.values()]};
    await output('observations.json',JSON.stringify(observations,null,2));
    await output('inputs.json',JSON.stringify({transitions:trace, configuredIntervalMs:interval,
      settledIntervalsMs:fullIntervals, measuredMedianMs:measuredInterval},null,2));
    const files=ids.map(id=>path.join(out,id+'.json')), python=process.env.PYTHON || 'python3';
    const run=(script,args)=>execFileSync(python,['-B',path.join(toolsDir,script),...args],{stdio:'inherit'});
    run('web_design_media.py',['--survey',files[0],...files.flatMap(f=>['--capture',f]),'--out-dir',path.join(out,'media'),'--index',path.join(out,'media.json')]);
    run('web_design_source.py',[...files.flatMap(f=>['--capture',f]),'--assets',path.join(out,'media.json'),'--id',options.id,'--title',initial.title,'--out',path.join(out,'screens.json')]);
    run('native_edit.py',['web-carousel','--graph',path.join(out,'screens.json'),'--observations',path.join(out,'observations.json'),'--out',path.join(out,'carousel-graph.json')]);
  } finally {
    await send('Browser.close').catch(()=>{});
    if(proc.exitCode===null && proc.signalCode===null) await Promise.race([new Promise(resolve=>proc.once('exit',resolve)),pause(2000)]);
    if(proc.exitCode===null && proc.signalCode===null) proc.kill();
    await rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:150});
  }
}

const {values} = parseArgs({options:Object.fromEntries(['url','rail','out','interval-ms','first-card','chrome','width','height','id'].map(key=>[key,{type:'string'}]).concat([['help',{type:'boolean'}]]))});
if(values.help){console.log(help);process.exit(0);}
const width=Number(values.width||390),height=Number(values.height||844),interval=Number(values['interval-ms']);
if(!values.rail || !values.out || !/^https?:\/\//.test(values.url||'') || !Number.isInteger(interval) || interval<1000 || interval>60000 ||
   ![width,height].every(n=>Number.isInteger(n)&&n>=100&&n<=4096))throw Error(help);
values.id ||= 'captured-feature-carousel';
const out=path.resolve(values.out);
await mkdir(out,{mode:0o700});
await capture(values,out,interval,width,height);
