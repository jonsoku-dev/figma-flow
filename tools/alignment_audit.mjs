// Measure declared CSS box edges in a disposable browser. The page source stays untouched.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { chromiumBinary, withChromiumPage, until } from './chromium_pipe.mjs';

const execFileAsync = promisify(execFile);

const usage = `node tools/alignment_audit.mjs --url LOCAL_URL --rules RULES.json --out NEW_DIR
  [--widths 320,400] [--height 300] [--chrome BIN]
Rules: optional readySelector, measurement:'paint', and groups with id, axis, edge, anchor, targets, tolerance and expectedOffset.
Paint mode records before/hidden/restored evidence and compares observed pixels. Exit 0 pass, 1 drift, 2 unverified/error.`;
const selector = value => typeof value === 'string' && value.trim().length > 0;

function readRules(raw) {
  const rules = JSON.parse(raw);
  if (!rules || !Array.isArray(rules.groups) || !rules.groups.length ||
      Object.keys(rules).some(key => !['groups', 'readySelector', 'measurement'].includes(key)) ||
      (rules.measurement !== undefined && rules.measurement !== 'paint') ||
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
  return { ...(rules.measurement ? { measurement: rules.measurement } : {}), readySelector: rules.readySelector ?? null, groups };
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

function inspectPaintTarget(selector, occurrenceIndex, isVisible) {
  const matches = [...document.querySelectorAll(selector)].filter(isVisible);
  const element = matches[occurrenceIndex];
  if (!element) return { reason: 'target-changed' };
  const allMatches = [...document.querySelectorAll(selector)];
  const rawIndex = allMatches.indexOf(element);
  const rect = element.getBoundingClientRect();
  if (rect.left < 0 || rect.top < 0 || rect.right > innerWidth || rect.bottom > innerHeight) return { reason: 'offscreen-or-clipped' };
  const svgNamespace = 'http://www.w3.org/2000/svg';
  const isSvg = element.namespaceURI === svgNamespace;
  if (isSvg) {
    const allowed = new Set(['svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan']);
    if ([element, ...element.querySelectorAll('*')].some(node => !allowed.has(node.localName.toLowerCase()))) return { reason: 'unsupported-svg-content' };
  } else {
    if (element.children.length || !element.textContent.trim()) return { reason: 'unsupported-or-empty-text' };
    const style = getComputedStyle(element);
    const pseudoHasContent = ['::before','::after'].some(pseudo => {
      const content = getComputedStyle(element, pseudo).content;
      return content !== 'none' && content !== 'normal' && content !== '""';
    });
    if (style.backgroundImage !== 'none' || style.backgroundColor !== 'rgba(0, 0, 0, 0)' ||
        ['Top','Right','Bottom','Left'].some(side => parseFloat(style['border' + side + 'Width']) > 0) ||
        style.boxShadow !== 'none' || style.outlineStyle !== 'none' || style.textShadow !== 'none' || pseudoHasContent) {
      return { reason: 'decorated-or-mixed-html' };
    }
    if ((['hidden','clip','scroll','auto'].includes(style.overflowX) && element.scrollWidth > element.clientWidth) ||
        (['hidden','clip','scroll','auto'].includes(style.overflowY) && element.scrollHeight > element.clientHeight)) {
      return { reason: 'partially-clipped' };
    }
  }
  for (let node = element; node && node !== document.documentElement; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (style.animationName !== 'none' || style.filter !== 'none' ||
        style.clipPath !== 'none' || style.maskImage !== 'none') {
      return { reason: 'dynamic-or-clipped' };
    }
    if (node !== element) {
      const clip = node.getBoundingClientRect();
      const clipLeft = clip.left + node.clientLeft;
      const clipTop = clip.top + node.clientTop;
      const clipRight = clipLeft + node.clientWidth;
      const clipBottom = clipTop + node.clientHeight;
      const clipsX = ['hidden','clip','scroll','auto'].includes(style.overflowX);
      const clipsY = ['hidden','clip','scroll','auto'].includes(style.overflowY);
      if ((clipsX && (rect.left < clipLeft - 0.5 || rect.right > clipRight + 0.5)) ||
          (clipsY && (rect.top < clipTop - 0.5 || rect.bottom > clipBottom + 0.5))) {
        return { reason: 'partially-clipped' };
      }
    }
  }
  if (element.getAnimations({ subtree: true }).some(animation => animation.playState === 'running' || animation.playState === 'pending')) {
    return { reason: 'dynamic-content' };
  }
  return { rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, kind: isSvg ? 'svg' : 'text', rawIndex };
}

async function capturePaint(elementSelector, occurrenceIndex, evaluate, command, out, width, key, expectedRect) {
  const inspected = await evaluate('(' + inspectPaintTarget + ')(' + JSON.stringify(elementSelector) + ',' + occurrenceIndex + ',' + visible + ')');
  if (inspected.reason) return inspected;
  if (expectedRect && ['x','y','width','height'].some(key => Math.abs(expectedRect[key] - inspected.rect[key]) > 0.05)) {
    return { reason: 'layout-changed-before-capture' };
  }
  const before = Buffer.from((await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  const hidden = await evaluate(`(()=>{const element=[...document.querySelectorAll(${JSON.stringify(elementSelector)})][${inspected.rawIndex}]; if(!element)return {reason:'target-changed'}; const style=element.getAttribute('style'); element.style.setProperty('visibility','hidden','important'); return {style};})()`);
  if (hidden.reason) return hidden;
  let concealed;
  try {
    concealed = Buffer.from((await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  } finally {
    await evaluate(`(()=>{const element=[...document.querySelectorAll(${JSON.stringify(elementSelector)})][${inspected.rawIndex}]; if(element){const prior=${JSON.stringify(hidden.style)}; if(prior===null)element.removeAttribute('style'); else element.setAttribute('style',prior);}})()`);
  }
  const restored = Buffer.from((await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  const paths = ['before','hidden','restored'].map(suffix => path.join(out, `width-${width}-paint-${key}-${suffix}.png`));
  for (let i = 0; i < paths.length; i++) await writeFile(paths[i], [before, concealed, restored][i], { flag: 'wx', mode: 0o600 });
  try {
    const helper = path.join(path.dirname(fileURLToPath(import.meta.url)), 'alignment_pixels.py');
    const margin = 2; // Include antialiasing/stroke at the CSS-box edge while keeping the scan local.
    const crop = [inspected.rect.x - margin, inspected.rect.y - margin,
      inspected.rect.width + margin * 2, inspected.rect.height + margin * 2]
      .map(value => String(value));
    const { stdout } = await execFileAsync('python3', ['-B', helper, ...paths, String(width),
      String(Number(await evaluate('innerHeight'))), ...crop]);
    const pixels = JSON.parse(stdout);
    return { ...inspected, ...pixels, pixelEvidence: paths.map(file => path.basename(file)) };
  } catch (error) {
    if (error.code === 'ENOENT') return { reason: 'pixel-helper-unavailable' };
    return { reason: 'pixel-analysis-failed', detail: String(error.stderr || error.message).trim().slice(0, 300) };
  }
}

async function applyPaintMeasurements(result, evaluate, command, out, width) {
  let sequence = 0;
  for (const group of result.groups) {
    const anchor = await capturePaint(group.anchor, 0, evaluate, command, out, width, sequence++, group.anchorRect);
    if (anchor.reason || !anchor.paintedRect) {
      group.anchorPaintedRect = null;
      group.anchorPaintedValue = null;
      group.anchorPaintReason = anchor.reason || 'empty-ink';
      if (anchor.pixelEvidence) group.anchorPixelEvidence = anchor.pixelEvidence;
      for (const target of group.targets) {
        if (target.status !== 'unverified') Object.assign(target, { status: 'unverified', reason: 'paint-anchor-' + (anchor.reason || 'empty-ink') });
      }
      continue;
    }
    group.anchorPaintedRect = anchor.paintedRect;
    group.anchorCapturedBoxRect = anchor.rect;
    group.anchorBoxValue = group.anchorValue;
    group.anchorPaintedValue = edgeValue(anchor.paintedRect, group.axis, group.edge);
    group.anchorPixelEvidence = anchor.pixelEvidence;
    group.anchorValue = group.anchorPaintedValue;
    for (const target of group.targets) {
      if (target.status === 'unverified') continue;
      const pixels = await capturePaint(target.selector, target.occurrenceIndex, evaluate, command, out, width, sequence++, target.rect);
      if (pixels.reason || !pixels.paintedRect) {
        Object.assign(target, { status: 'unverified', reason: pixels.reason || 'empty-ink', pixelEvidence: pixels.pixelEvidence });
        continue;
      }
      const boxRect = pixels.rect;
      const boxValue = target.value;
      const value = edgeValue(pixels.paintedRect, group.axis, group.edge);
      const delta = value - group.anchorPaintedValue;
      const deviation = delta - group.expectedOffset;
      Object.assign(target, { boxRect, boxValue, paintedRect: pixels.paintedRect, paintedValue: value,
        value, pixelEvidence: pixels.pixelEvidence, delta, deviation,
        status: Math.abs(deviation) <= group.tolerance ? 'pass' : 'drift' });
    }
  }
  result.measurement = 'paint';
  result.perceivedBalance = 'not-assessed';
}

function edgeValue(rect, axis, edge) {
  const start = axis === 'x' ? rect.x : rect.y;
  const size = axis === 'x' ? rect.width : rect.height;
  return start + size * { start: 0, center: 0.5, end: 1 }[edge];
}

function drawGuides(result, style) {
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
    line.setAttribute('stroke-dasharray', style.dash);
    svg.append(line);
  }
  for (const group of result.groups) {
    if (group.anchorValue === null || !result.ready) continue;
    add(group.axis, group.anchorValue, style.anchor);
    if (group.expectedOffset) add(group.axis, group.anchorValue + group.expectedOffset, style.expected);
    for (const target of group.targets) if (target.status === 'drift') add(group.axis, target.value, style.drift);
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
      if (rules.measurement === 'paint') await applyPaintMeasurements(result, evaluate, command, out, width);
      async function capture(kind) {
        const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
        await writeFile(path.join(out, `width-${width}-${kind}.png`), Buffer.from(shot.data, 'base64'), { flag: 'wx', mode: 0o600 });
      }
      await capture('clean');
      const appearance = JSON.parse(await readFile(new URL('./report-presentation.json', import.meta.url), 'utf8'));
      await evaluate('(' + drawGuides + ')(' + JSON.stringify(result) + ',' + JSON.stringify(appearance.graphics.alignment) + ')');
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
