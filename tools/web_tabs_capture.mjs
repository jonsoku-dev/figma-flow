// Observe click-selected tab panels in a private Chromium page and compile them into a Design graph.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as pause } from 'node:timers/promises';
import { chromiumBinary, until, withChromiumPage } from './chromium_pipe.mjs';

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const help = `node tools/web_tabs_capture.mjs --url URL --tabs SELECTOR --panel SELECTOR --click LABEL [--click LABEL ...] --out NEW_DIRECTORY [--id GRAPH_ID] [--frame-key KEY] [--chrome EXECUTABLE] [--width 1440 --height 900] [--settle-ms 1500]
Click the named tabs in order, for example A→B→A as --click B --click A.
The direct children of --tabs are the tab controls. The visible text of --panel identifies each state.
Writes screenshots, measured WEB screens, click receipts and tabs-graph.json. Requires Chromium, Node and Python on PATH.`;

// Evaluated in the page. Labels come from the first heading or first text line of each control.
function readTabs(tabsSelector, panelSelector) {
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const lists = Array.from(document.querySelectorAll(tabsSelector)).filter(visible);
  const panels = Array.from(document.querySelectorAll(panelSelector)).filter(visible);
  if (lists.length !== 1 || panels.length !== 1) return null;
  const tabs = Array.from(lists[0].children).filter(visible).map(el => {
    const { x, y, width, height } = el.getBoundingClientRect();
    return { label: (el.querySelector('h1,h2,h3,h4,h5,h6')?.innerText || el.innerText || '').trim().split('\n')[0],
      rect: { x, y, width, height } };
  });
  return { tabs, content: panels[0].innerText, scrollY, title: document.title, url: location.href, dpr: devicePixelRatio,
    viewport: { width: innerWidth, height: innerHeight } };
}

async function capture(options, out, width, height) {
  await withChromiumPage(chromiumBinary(options.chrome), async ({ command, evaluate, product }) => {
    await command('Page.enable');
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
    await command('Page.navigate', { url: options.url });
    const read = () => evaluate('(' + readTabs.toString() + ')(' + JSON.stringify(options.tabs) + ',' + JSON.stringify(options.panel) + ')');
    await until(read, Date.now() + 20000, 'No unique visible --tabs list and --panel region');
    await evaluate('document.fonts.ready.then(() => true)');
    await evaluate('document.querySelector(' + JSON.stringify(options.tabs) + ').scrollIntoView({block:"center",behavior:"instant"}), true');
    // Entrance effects start when the section scrolls into view. Infinite loops never finish and are tolerated.
    await until(() => evaluate('document.getAnimations().every(a => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity)'),
      Date.now() + 15000, 'Finite page animations did not finish');
    await pause(Number(options['settle-ms']));
    const rest = { x: 0, y: height - 1 };
    const moveAway = () => command('Input.dispatchMouseEvent', { type: 'mouseMoved', ...rest });
    await moveAway();
    // A state is settled when two reads 300 ms apart agree on panel text and tab geometry.
    const settled = async () => {
      let previous = await read();
      return until(async () => {
        await pause(300);
        const next = await read();
        const same = next && previous && next.content === previous.content && next.scrollY === previous.scrollY
          && JSON.stringify(next.tabs) === JSON.stringify(previous.tabs);
        previous = next;
        return same && next;
      }, Date.now() + 10000, 'Tab panel did not settle');
    };
    const first = await settled();
    const labels = first.tabs.map(tab => tab.label);
    if (labels.length < 2 || labels.length > 16 || labels.some(label => !label) || new Set(labels).size !== labels.length)
      throw Error('Expected 2–16 uniquely labelled tab controls');
    for (const label of options.click) if (!labels.includes(label)) throw Error('No tab control is labelled ' + JSON.stringify(label));

    const fixed = await readFile(path.join(toolsDir, 'web_design_capture.js'), 'utf8');
    const output = async (name, bytes) => { await writeFile(path.join(out, name), bytes, { flag: 'wx', mode: 0o600 });
      return { path: name, sha256: createHash('sha256').update(bytes).digest('hex') }; };
    const screenshot = async name => output(name, Buffer.from((await command('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
    const digest = text => createHash('sha256').update(text).digest('hex');
    const states = [], screens = new Map(), transitions = [], trace = [];
    const record = async observed => {
      const id = 'WEB-' + options.id + '-' + (states.length + 1);
      const data = await evaluate('(() => {' + fixed + ';return captureWebDesign(' + JSON.stringify({ screenId: id, extent: 'viewport' }) + ');})()');
      const capture = await screenshot('state-' + (states.length + 1) + '.png');
      const after = await read();
      if (after.content !== observed.content || after.scrollY !== observed.scrollY) throw Error('State changed while recording ' + id);
      await output(id + '.json', JSON.stringify(data));
      const state = { id, label: 'Initial state', contentSha256: digest(observed.content), capture };
      states.push(state);
      screens.set(id, data.screen);
      return state;
    };
    let current = await record(first);
    for (const [index, label] of options.click.entries()) {
      const before = await settled();
      if (before.scrollY !== first.scrollY) throw Error('Page scrolled between clicks; rerun with a fixed layout');
      const tab = before.tabs.find(item => item.label === label);
      const x = tab.rect.x + tab.rect.width / 2, y = tab.rect.y + tab.rect.height / 2;
      const hit = await evaluate('(() => {const p=document.elementFromPoint(' + x + ',' + y + ');const list=document.querySelector(' + JSON.stringify(options.tabs) + ');'
        + 'return !!p && Array.from(list.children).findIndex(c => c.contains(p)) === ' + labels.indexOf(label) + ';})()');
      if (!hit) throw Error('The center of tab ' + JSON.stringify(label) + ' is covered by another element');
      const controls = screens.get(current.id).elements.filter(element => element.kind === 'frame'
        && ['x', 'y', 'width', 'height'].every(key => Math.abs(element.box[key] - tab.rect[key]) <= 1));
      if (controls.length !== 1) throw Error('Tab ' + JSON.stringify(label) + ' is not one captured frame in ' + current.id);
      for (const type of ['mousePressed', 'mouseReleased']) await command('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
      await moveAway();
      const after = await settled();
      if (after.content === before.content) throw Error('Clicking ' + JSON.stringify(label) + ' did not change the panel');
      if (after.scrollY !== first.scrollY) throw Error('Clicking ' + JSON.stringify(label) + ' scrolled the page');
      const evidence = await screenshot('click-' + (index + 1) + '.png');
      const target = states.find(state => state.contentSha256 === digest(after.content)) || await record(after);
      target.label = label;
      transitions.push({ from: current.id, to: target.id, input: 'click', controlElementId: controls[0].id, observed: true, evidence });
      trace.push({ click: label, point: { x, y }, hitTest: hit, from: current.id, to: target.id,
        returnedToRecordedState: target.capture.sha256 === evidence.sha256, evidence });
      current = target;
    }
    const observations = { schemaVersion: 1,
      source: { url: first.url, title: first.title, browser: product, viewport: first.viewport, dpr: first.dpr, capturedAt: new Date().toISOString() },
      tabs: { frameKey: options['frame-key'], initialState: states[0].id }, states, transitions };
    await output('observations.json', JSON.stringify(observations, null, 2));
    await output('inputs.json', JSON.stringify({ tabs: options.tabs, panel: options.panel, clicks: trace }, null, 2));
    const files = states.map(state => path.join(out, state.id + '.json')), python = process.env.PYTHON || 'python3';
    const run = (script, args) => execFileSync(python, ['-B', path.join(toolsDir, script), ...args], { stdio: 'inherit' });
    run('web_design_media.py', ['--survey', files[0], ...files.flatMap(f => ['--capture', f]), '--out-dir', path.join(out, 'media'), '--index', path.join(out, 'media.json')]);
    run('web_design_source.py', [...files.flatMap(f => ['--capture', f]), '--assets', path.join(out, 'media.json'), '--id', options.id, '--title', first.title, '--out', path.join(out, 'screens.json')]);
    run('native_edit.py', ['web-tabs', '--graph', path.join(out, 'screens.json'), '--observations', path.join(out, 'observations.json'), '--out', path.join(out, 'tabs-graph.json')]);
  });
}

const { values } = parseArgs({ options: { ...Object.fromEntries(['url', 'tabs', 'panel', 'out', 'id', 'frame-key', 'chrome', 'width', 'height', 'settle-ms']
  .map(key => [key, { type: 'string' }])), click: { type: 'string', multiple: true }, help: { type: 'boolean' } } });
if (values.help) { console.log(help); process.exit(0); }
const width = Number(values.width || 1440), height = Number(values.height || 900);
values.id ||= 'captured-tabs';
values['frame-key'] ||= 'tabs';
values['settle-ms'] ||= '1500';
if (!values.tabs || !values.panel || !values.out || !values.click?.length || values.click.length > 32 || !/^https?:\/\//.test(values.url || '')
    || !/^[a-z0-9][a-z0-9-]{0,60}$/.test(values.id) || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$/.test(values['frame-key'])
    || !(Number(values['settle-ms']) >= 0 && Number(values['settle-ms']) <= 30000)
    || ![width, height].every(n => Number.isInteger(n) && n >= 100 && n <= 4096)) throw Error(help);
const out = path.resolve(values.out);
await mkdir(out, { mode: 0o700 });
await capture(values, out, width, height);
