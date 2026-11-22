// Measure declared CSS box edges in a disposable browser. The page source stays untouched.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { chromiumBinary, withChromiumPage, until } from './chromium_pipe.mjs';

const usage = `node tools/alignment_audit.mjs --url LOCAL_URL --rules RULES.json --out NEW_DIR
  [--widths 320,400] [--height 300] [--chrome BIN]
Rules: optional readySelector and groups with id, axis, edge, anchor, targets, tolerance and expectedOffset.
Writes report.json and clean/guide-overlay PNGs per viewport. Exit 0 pass, 1 drift, 2 unverified/error.`;
const selector = value => typeof value === 'string' && value.trim().length > 0;

function readRules(raw) {
  const rules = JSON.parse(raw);
  if (!rules || !Array.isArray(rules.groups) || !rules.groups.length ||
      Object.keys(rules).some(key => !['groups', 'readySelector'].includes(key)) ||
      (rules.readySelector !== undefined && !selector(rules.readySelector))) {
    throw Error('Expected groups and an optional readySelector.');
  }
  const ids = new Set();
  const groups = rules.groups.map(group => {
    const fields = ['id', 'axis', 'edge', 'anchor', 'targets', 'tolerance', 'expectedOffset'];
    if (!group || typeof group !== 'object' || Object.keys(group).some(key => !fields.includes(key))) {
      throw Error('Unknown rule field.');
    }
    const { id, axis, edge, anchor, targets, tolerance = 1, expectedOffset = 0 } = group;
    if (!selector(id) || ids.has(id) || !['x', 'y'].includes(axis) || !['start', 'center', 'end'].includes(edge) ||
        !selector(anchor) || !Array.isArray(targets) || !targets.length || !targets.every(selector) ||
        new Set(targets).size !== targets.length || !Number.isFinite(tolerance) || tolerance < 0 ||
        !Number.isFinite(expectedOffset)) throw Error('Invalid or duplicate alignment rule: ' + id);
    ids.add(id);
    return { id, axis, edge, anchor, targets, tolerance, expectedOffset };
  });
  return { readySelector: rules.readySelector ?? null, groups };
}

// These functions run in the inspected document. Never measure the injected guides.
function visible(element) {
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  if (element.checkVisibility) return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  if (['hidden', 'collapse'].includes(getComputedStyle(element).visibility)) return false;
  for (let node = element; node; node = node.parentElement) {
    if (Number(getComputedStyle(node).opacity) === 0) return false;
  }
  return true;
}

function measure(rules, isVisible, ready) {
  function readEdge(node, axis, edge) {
    const { x, y, width, height } = node.getBoundingClientRect();
    const start = axis === 'x' ? x : y;
    const size = axis === 'x' ? width : height;
    const value = start + size * { start: 0, center: 0.5, end: 1 }[edge];
    return { rect: { x, y, width, height }, value };
  }
  const groups = rules.groups.map(rule => {
    const anchors = [...document.querySelectorAll(rule.anchor)].filter(isVisible);
    const anchor = anchors.length === 1 ? readEdge(anchors[0], rule.axis, rule.edge) : null;
    const targets = rule.targets.flatMap(selector => {
      const matches = [...document.querySelectorAll(selector)].filter(isVisible);
      const count = matches.length;
      let reason;
      if (!ready) reason = 'screen-not-ready';
      else if (!anchor) reason = anchors.length ? 'ambiguous-anchor' : 'missing-anchor';
      else if (!count) reason = 'missing-target';
      if (reason) return [{ selector, count, status: 'unverified', reason }];
      return matches.map((element, occurrenceIndex) => {
        const { rect, value } = readEdge(element, rule.axis, rule.edge);
        const delta = value - anchor.value;
        const deviation = delta - rule.expectedOffset;
        return { selector, occurrenceIndex, count, rect, value, delta, expectedOffset: rule.expectedOffset,
          deviation, status: Math.abs(deviation) <= rule.tolerance ? 'pass' : 'drift' };
      });
    });
    return { ...rule, anchorCount: anchors.length, anchorRect: anchor?.rect ?? null,
      anchorValue: anchor?.value ?? null, targets };
  });
  const { scrollWidth: documentWidth, scrollHeight: documentHeight } = document.documentElement;
  return { groups, ready, overflow: documentWidth > innerWidth, documentWidth, documentHeight,
    viewportWidth: innerWidth, viewportHeight: innerHeight, scrollX, scrollY,
    captureClipped: documentWidth > innerWidth || documentHeight > innerHeight };
}

function drawGuides(result) {
  const host = document.createElement('div');
  host.setAttribute('aria-hidden', 'true');
  // Shadow DOM keeps the inspected application's SVG styles away from the overlay.
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', innerWidth);
  svg.setAttribute('height', innerHeight);
  Object.assign(svg.style, { position: 'fixed', inset: '0', zIndex: '2147483647', pointerEvents: 'none' });
  host.attachShadow({ mode: 'closed' }).append(svg);
  document.documentElement.append(host);
  const drawn = new Set();
  function add(axis, at, color) {
    const key = [axis, at, color].join(':');
    if (drawn.has(key)) return;
    drawn.add(key);
    const line = document.createElementNS(ns, 'line');
    const endpoints = axis === 'x' ? [at, 0, at, innerHeight] : [0, at, innerWidth, at];
    ['x1','y1','x2','y2'].forEach((attr, i) => line.setAttribute(attr, endpoints[i]));
    line.setAttribute('stroke', color);
    line.setAttribute('stroke-dasharray', '5 4');
    svg.append(line);
  }
  for (const group of result.groups) {
    if (group.anchorValue === null || !result.ready) continue;
    add(group.axis, group.anchorValue, '#255bb5');
    if (group.expectedOffset) add(group.axis, group.anchorValue + group.expectedOffset, '#8354af');
    for (const target of group.targets) if (target.status === 'drift') add(group.axis, target.value, '#d21f3c');
  }
}

async function run(values) {
  if (!values.url || !values.rules || !values.out) throw Error(usage);
  const url = new URL(values.url);
  if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
      url.username || url.password) throw Error('Use a local HTTP(S) URL without embedded credentials.');
  const widths = (values.widths ?? '320,400').split(',').map(Number);
  const height = Number(values.height ?? 300);
  if (widths.length > 10 || new Set(widths).size !== widths.length ||
      widths.some(w => !Number.isInteger(w) || w < 200 || w > 3000) ||
      !Number.isInteger(height) || height < 100 || height > 3000) throw Error('Invalid or duplicate viewport dimensions.');
  const rules = readRules(await readFile(values.rules, 'utf8'));
  const out = path.resolve(values.out);
  await mkdir(path.dirname(out), { recursive: true });
  await mkdir(out, { mode: 0o700 });
  const report = { schemaVersion: 1, url: url.href, pageKey: url.pathname + url.search + url.hash,
    rulesSha256: createHash('sha256').update(JSON.stringify(rules)).digest('hex'), viewports: [] };
  await withChromiumPage(chromiumBinary(values.chrome), async ({ command, evaluate, product }) => {
    report.browser = product;
    await command('Page.enable');
    for (const width of widths) {
      await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
      const nav = await command('Page.navigate', { url: url.href });
      if (nav.errorText || !nav.loaderId) throw Error('Navigation failed: ' + (nav.errorText || 'missing loader'));
      await until(async () => {
        const { frameTree } = await command('Page.getFrameTree');
        return frameTree.frame.loaderId === nav.loaderId && await evaluate('document.readyState === "complete"');
      }, Date.now() + 20000, 'Page did not finish loading.');
      const finalUrl = await evaluate('location.href');
      if (new URL(finalUrl).origin !== url.origin) throw Error('Navigation left the requested local origin.');
      let ready = true;
      if (rules.readySelector) {
        const check = 'Array.from(document.querySelectorAll(' + JSON.stringify(rules.readySelector) + ')).filter(' + visible + ').length === 1';
        const deadline = Date.now() + 8000;
        do {
          ready = await evaluate(check);
          if (!ready) await new Promise(resolve => setTimeout(resolve, 90));
        } while (!ready && Date.now() < deadline);
      }
      await evaluate('document.fonts.ready.then(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))');
      const result = await evaluate('(' + measure + ')(' + JSON.stringify(rules) + ',' + visible + ',' + ready + ')');
      async function capture(kind) {
        const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
        await writeFile(path.join(out, `width-${width}-${kind}.png`), Buffer.from(shot.data, 'base64'), { flag: 'wx', mode: 0o600 });
      }
      await capture('clean');
      await evaluate('(' + drawGuides + ')(' + JSON.stringify(result) + ')');
      await capture('guide-overlay');
      report.viewports.push({ width, height, finalUrl, ...result });
    }
  });
  const statuses = report.viewports.flatMap(view => view.groups.flatMap(group => group.targets.map(row => row.status)));
  report.status = statuses.includes('unverified') ? 'unverified' : statuses.includes('drift') ? 'drift' : 'pass';
  await writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  console.log(report.status + ' · ' + path.join(out, 'report.json'));
  return { pass: 0, drift: 1, unverified: 2 }[report.status];
}

try {
  const options = Object.fromEntries(['url', 'rules', 'out', 'widths', 'height', 'chrome'].map(name => [name, { type: 'string' }]));
  options.help = { type: 'boolean' };
  const { values } = parseArgs({ options });
  if (values.help) console.log(usage);
  else process.exitCode = await run(values);
} catch (error) {
  console.error('alignment_audit: ' + error.message);
  process.exitCode = 2;
}
