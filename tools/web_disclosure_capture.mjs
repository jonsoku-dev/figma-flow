// Observe click-toggled single-collapsible disclosure/accordion items in a private Chromium page and compile them into a Design graph.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as pause } from 'node:timers/promises';
import { chromiumBinary, until, withChromiumPage } from './chromium_pipe.mjs';

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const defaultItemSelector = '[data-slot="accordion-item"], details';
const defaultTriggerSelector = '[data-slot="accordion-trigger"], button[aria-expanded], [role="button"][aria-expanded], summary';
const defaultContentSelector = '[data-slot="accordion-content"], [role="region"]';

const help = `node tools/web_disclosure_capture.mjs --url URL --accordion SELECTOR [--item SELECTOR] [--trigger SELECTOR] [--content SELECTOR] --click LABEL [--click LABEL ...] --out NEW_DIRECTORY [--id GRAPH_ID] [--frame-key KEY] [--chrome EXECUTABLE] [--width 1440 --height 900] [--settle-ms 1500]
Click the named disclosure triggers in order, for example open->close->open->switch as --click Q1 --click Q1 --click Q1 --click Q2.
Writes screenshots, measured WEB screens, click receipts, observations.json, inputs.json and disclosure-graph.json. Requires Chromium, Node and Python on PATH.`;

// Evaluated in the page. Explicit { x, y, width, height } destructuring is required because CDP returnByValue serializes DOMRect as {}.
function readDisclosure(accordionSelector, itemSelector, triggerSelector, contentSelector, probe) {
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const rectOf = el => { const { x, y, width, height } = el.getBoundingClientRect(); return { x, y, width, height }; };
  const roots = Array.from(document.querySelectorAll(accordionSelector)).filter(visible);
  if (roots.length !== 1) return null;
  const root = roots[0];
  const itemEls = Array.from(root.querySelectorAll(itemSelector))
    .filter(el => visible(el) && el.closest(accordionSelector) === root);
  if (!itemEls.length) return null;

  const collect = () => itemEls.map(itemEl => {
    const triggers = Array.from(itemEl.querySelectorAll(triggerSelector))
      .filter(el => visible(el) && el.closest(itemSelector) === itemEl);
    if (triggers.length !== 1) return { invalid: 'Expected 1 visible trigger per disclosure item (found ' + triggers.length + ')' };
    const trigger = triggers[0];
    const tag = itemEl.tagName.toLowerCase();
    const triggerTag = trigger.tagName.toLowerCase();
    let ariaExpanded = trigger.getAttribute('aria-expanded');
    if (ariaExpanded === null && triggerTag === 'summary' && tag === 'details') {
      ariaExpanded = String(Boolean(itemEl.open));
    }
    const triggerDataState = trigger.getAttribute('data-state');
    const itemDataState = itemEl.getAttribute('data-state');
    const dataState = triggerDataState ?? itemDataState ?? null;
    const expanded = ariaExpanded === 'true';
    const controlsId = trigger.getAttribute('aria-controls');
    let content = controlsId ? document.getElementById(controlsId) : null;
    if (!content) content = itemEl.querySelector(contentSelector);
    if (!content && tag === 'details') {
      content = Array.from(itemEl.children).find(child => child !== trigger && child.tagName.toLowerCase() !== 'summary') || null;
    }
    let answerText = '';
    let contentHeight = 0;
    if (content && !content.hidden) {
      const style = getComputedStyle(content);
      if (style.display !== 'none' && style.visibility !== 'hidden') {
        const contentRect = rectOf(content);
        if (contentRect.width > 1 && contentRect.height > 1) {
          answerText = (content.innerText || '').trim().replace(/\s+/g, ' ');
          contentHeight = contentRect.height;
        }
      }
    }
    const label = (trigger.innerText || trigger.textContent || '').trim().replace(/\s+/g, ' ');
    return {
      trigger,
      label,
      ariaExpanded,
      expanded,
      dataState,
      triggerDataState,
      itemDataState,
      answerText,
      contentHeight,
      triggerRect: rectOf(trigger),
      itemRect: rectOf(itemEl),
    };
  });

  if (probe === 'ready') {
    const items = collect();
    return items.length >= 2 && items.every(item => !item.invalid) ? true : null;
  }
  if (probe === 'scroll') {
    root.scrollIntoView({ block: 'center', behavior: 'instant' });
    const items = collect();
    const openItem = items.find(item => !item.invalid && item.expanded);
    if (openItem) {
      const contentHeight = openItem.contentHeight > 0
        ? openItem.contentHeight
        : Math.max(0, openItem.itemRect.height - openItem.triggerRect.height);
      const maxScrollY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      const headroom = maxScrollY - window.scrollY;
      if (contentHeight > 0 && headroom < contentHeight + 16) {
        const backoff = Math.ceil((contentHeight + 16) - headroom);
        window.scrollTo({ top: Math.max(0, window.scrollY - backoff), behavior: 'instant' });
      }
    }
    return true;
  }
  const items = collect();
  if (probe && typeof probe === 'object') {
    const target = items[probe.index];
    if (!target || target.invalid) return false;
    const p = document.elementFromPoint(probe.x, probe.y);
    return !!p && target.trigger.contains(p);
  }
  return {
    items: items.map(({ trigger, ...rest }) => rest),
    scrollY: window.scrollY,
    scrollHeight: document.documentElement.scrollHeight,
    title: document.title,
    url: location.href,
    dpr: devicePixelRatio,
    viewport: { width: innerWidth, height: innerHeight },
  };
}

function assertDisclosureInvariants(state) {
  if (!state || !Array.isArray(state.items)) throw Error('Disclosure root is missing or not unique');
  for (const item of state.items) {
    if (item.invalid) throw Error(item.invalid);
  }
  const labels = state.items.map(item => item.label);
  if (labels.length < 2 || labels.length > 16 || labels.some(label => !label || label.length > 160) || new Set(labels).size !== labels.length) {
    throw Error('Expected 2–16 uniquely labelled disclosure items (<= 160 chars each)');
  }
  for (const item of state.items) {
    if (item.ariaExpanded !== 'true' && item.ariaExpanded !== 'false') {
      throw Error('Disclosure trigger ' + JSON.stringify(item.label) + ' has invalid aria-expanded: ' + JSON.stringify(item.ariaExpanded));
    }
    for (const ds of [item.triggerDataState, item.itemDataState]) {
      if ((ds === 'open' || ds === 'closed') && (ds === 'open') !== item.expanded) {
        throw Error('Disclosure data-state ' + JSON.stringify(ds) + ' disagrees with aria-expanded on ' + JSON.stringify(item.label));
      }
    }
  }
  const expandedItems = state.items.filter(item => item.expanded);
  if (expandedItems.length > 1) {
    throw Error('Expected at most 1 expanded item in single-collapsible mode, got ' + expandedItems.length);
  }
  for (const item of state.items) {
    if (!item.expanded && item.answerText !== '') {
      throw Error('Collapsed disclosure item ' + JSON.stringify(item.label) + ' still exposes answer text');
    }
    if (item.expanded) {
      if (!(item.answerText.length > 0)) {
        throw Error('Expanded disclosure item ' + JSON.stringify(item.label) + ' has empty answer text');
      }
      if (!(item.triggerRect.height < item.itemRect.height - 4)) {
        throw Error('Expanded disclosure trigger spans item box for ' + JSON.stringify(item.label));
      }
    }
  }
}

function contentFingerprint(state) {
  return JSON.stringify(state.items.map(item => [item.label, item.expanded, item.answerText]));
}

function settleKey(state) {
  return JSON.stringify({
    scrollY: state.scrollY,
    scrollHeight: state.scrollHeight,
    items: state.items.map(({ label, expanded, dataState, answerText, triggerRect, itemRect }) =>
      ({ label, expanded, dataState, answerText, triggerRect, itemRect })),
  });
}

async function capture(options, out, width, height) {
  await withChromiumPage(chromiumBinary(options.chrome), async ({ command, evaluate, product }) => {
    await command('Page.enable');
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
    await command('Page.navigate', { url: options.url });

    const read = probe => evaluate(
      '(' + readDisclosure.toString() + ')('
      + JSON.stringify(options.accordion) + ','
      + JSON.stringify(options.item) + ','
      + JSON.stringify(options.trigger) + ','
      + JSON.stringify(options.content) + ','
      + JSON.stringify(probe ?? null) + ')'
    );

    await until(() => read('ready'), Date.now() + 20000, 'No unique visible --accordion root with 2+ valid disclosure items');
    await evaluate('document.fonts.ready.then(() => true)');

    // Step-scroll through the full page so lazy/below-fold sections mount before locking scrollY.
    const step = Math.max(400, Math.floor(height * 0.7));
    let top = 0;
    for (let guard = 0; guard < 200; guard++) {
      const info = await evaluate(`(() => {
        window.scrollTo({ top: ${top}, behavior: 'instant' });
        const scrollHeight = document.documentElement.scrollHeight;
        return { scrollHeight, atBottom: ${top} >= Math.max(0, scrollHeight - window.innerHeight) };
      })()`);
      await pause(80);
      const latestHeight = await evaluate('document.documentElement.scrollHeight');
      if (info.atBottom && latestHeight <= info.scrollHeight) break;
      const maxTop = Math.max(0, latestHeight - height);
      top = Math.min(top + step, maxTop);
    }

    const waitFiniteAnimations = error => until(
      () => evaluate(`(() => {
        const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const roots = Array.from(document.querySelectorAll(${JSON.stringify(options.accordion)})).filter(visible);
        if (roots.length !== 1) return false;
        return roots[0].getAnimations({ subtree: true }).every(a => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity);
      })()`),
      Date.now() + 15000,
      error
    );

    await waitFiniteAnimations('Finite page animations did not finish after warmup');
    await read('scroll');
    await waitFiniteAnimations('Finite page animations did not finish after scrolling to accordion');
    await pause(Number(options['settle-ms']));

    const rest = { x: 0, y: height - 1 };
    const moveAway = () => command('Input.dispatchMouseEvent', { type: 'mouseMoved', ...rest });
    await moveAway();

    const settled = async () => {
      let previous = await read();
      return until(async () => {
        await pause(300);
        const next = await read();
        const same = next && previous && settleKey(next) === settleKey(previous);
        previous = next;
        if (!same) return false;
        assertDisclosureInvariants(next);
        return next;
      }, Date.now() + 10000, 'Disclosure state did not settle');
    };

    const first = await settled();
    const labels = first.items.map(item => item.label);
    for (const label of options.click) {
      if (!labels.includes(label)) throw Error('No disclosure item is labelled ' + JSON.stringify(label));
    }

    const fixed = await readFile(path.join(toolsDir, 'web_design_capture.js'), 'utf8');
    const output = async (name, bytes) => {
      await writeFile(path.join(out, name), bytes, { flag: 'wx', mode: 0o600 });
      return { path: name, sha256: createHash('sha256').update(bytes).digest('hex') };
    };
    const screenshot = async name => output(name, Buffer.from((await command('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
    const digest = text => createHash('sha256').update(text).digest('hex');

    const states = [], screens = new Map(), transitions = [], trace = [];
    const record = async observed => {
      const id = 'WEB-' + options.id + '-' + (states.length + 1);
      const data = await evaluate('(() => {' + fixed + ';return captureWebDesign(' + JSON.stringify({ screenId: id, extent: 'viewport' }) + ');})()');
      const captureResult = await screenshot('state-' + (states.length + 1) + '.png');
      const after = await read();
      if (!after || contentFingerprint(after) !== contentFingerprint(observed) || after.scrollY !== observed.scrollY) {
        throw Error('State changed while recording ' + id);
      }
      await output(id + '.json', JSON.stringify(data));
      const openItem = observed.items.find(item => item.expanded) || null;
      const expandedItem = openItem ? openItem.label : null;
      const state = {
        id,
        label: expandedItem ?? 'All closed',
        expandedItem,
        answerSha256: openItem ? digest(openItem.answerText) : null,
        contentSha256: digest(contentFingerprint(observed)),
        capture: captureResult,
      };
      states.push(state);
      screens.set(id, data.screen);
      return state;
    };

    let current = await record(first);
    for (const [index, label] of options.click.entries()) {
      const before = await settled();
      if (before.scrollY !== first.scrollY) throw Error('Page scrolled between clicks; rerun with a fixed layout');
      const targetIndex = before.items.findIndex(item => item.label === label);
      const targetItem = before.items[targetIndex];
      const x = targetItem.triggerRect.x + targetItem.triggerRect.width / 2;
      const y = targetItem.triggerRect.y + targetItem.triggerRect.height / 2;
      const hit = await read({ x, y, index: targetIndex });
      if (!hit) throw Error('The center of disclosure trigger ' + JSON.stringify(label) + ' is covered by another element');

      const controls = screens.get(current.id).elements.filter(element => element.kind === 'frame'
        && ['x', 'y', 'width', 'height'].every(key => Math.abs(element.box[key] - targetItem.triggerRect[key]) <= 1));
      if (controls.length !== 1) {
        throw Error('Disclosure trigger ' + JSON.stringify(label) + ' is not one captured frame in ' + current.id + ' (matched ' + controls.length + ')');
      }

      for (const type of ['mousePressed', 'mouseReleased']) {
        await command('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
      }
      await moveAway();
      await waitFiniteAnimations('Finite disclosure animation did not finish after clicking ' + JSON.stringify(label));
      const after = await settled();
      if (after.scrollY !== first.scrollY) {
        throw Error('Clicking ' + JSON.stringify(label) + ' scrolled the page (' + first.scrollY + ' -> ' + after.scrollY + ')');
      }

      const beforeOpen = before.items.find(item => item.expanded) || null;
      const afterOpen = after.items.find(item => item.expanded) || null;
      const prevExp = beforeOpen ? beforeOpen.label : null;
      const nextExp = afterOpen ? afterOpen.label : null;

      let action;
      let autoClosedItem = null;
      if (prevExp === null) {
        action = 'open';
        if (nextExp !== label) {
          throw Error('Clicking closed disclosure ' + JSON.stringify(label) + ' did not open it (expanded: ' + JSON.stringify(nextExp) + ')');
        }
      } else if (prevExp === label) {
        action = 'close';
        if (nextExp !== null) {
          throw Error('Clicking open disclosure ' + JSON.stringify(label) + ' did not close it (expanded: ' + JSON.stringify(nextExp) + ')');
        }
      } else {
        action = 'switch';
        autoClosedItem = prevExp;
        if (nextExp !== label) {
          throw Error('Clicking sibling disclosure ' + JSON.stringify(label) + ' while ' + JSON.stringify(prevExp) + ' was open did not switch to it');
        }
        const closedPrev = after.items.find(item => item.label === prevExp);
        if (!closedPrev || closedPrev.expanded !== false || closedPrev.answerText !== '') {
          throw Error('Previously open disclosure ' + JSON.stringify(prevExp) + ' was not auto-closed cleanly');
        }
      }

      const evidence = await screenshot('click-' + (index + 1) + '.png');
      const afterContentSha = digest(contentFingerprint(after));
      const target = states.find(state => state.contentSha256 === afterContentSha) || await record(after);

      if (!transitions.some(edge => edge.from === current.id && edge.to === target.id && edge.controlElementId === controls[0].id)) {
        transitions.push({
          from: current.id,
          to: target.id,
          input: 'click',
          action,
          itemLabel: label,
          autoClosedItem,
          controlElementId: controls[0].id,
          observed: true,
          evidence,
        });
      }

      const afterTargetItem = after.items.find(item => item.label === label);
      trace.push({
        click: label,
        action,
        itemLabel: label,
        autoClosedItem,
        controlElementId: controls[0].id,
        triggerRect: targetItem.triggerRect,
        itemRect: targetItem.itemRect,
        ariaExpandedBefore: targetItem.ariaExpanded,
        ariaExpandedAfter: afterTargetItem.ariaExpanded,
        visibleQuestions: after.items.map(item => item.label),
        visibleAnswerBefore: beforeOpen ? beforeOpen.answerText : '',
        visibleAnswerAfter: afterOpen ? afterOpen.answerText : '',
        point: { x, y },
        hitTest: hit,
        from: current.id,
        to: target.id,
        returnedToRecordedState: target.capture.sha256 === evidence.sha256,
        evidence,
      });
      current = target;
    }

    const observations = {
      schemaVersion: 1,
      source: {
        url: first.url,
        title: first.title,
        browser: product,
        viewport: first.viewport,
        dpr: first.dpr,
        capturedAt: new Date().toISOString(),
      },
      disclosure: {
        frameKey: options['frame-key'],
        mode: 'single-collapsible',
        initialState: states[0].id,
        items: labels,
      },
      states,
      transitions,
    };

    await output('observations.json', JSON.stringify(observations, null, 2));
    await output('inputs.json', JSON.stringify({
      accordion: options.accordion,
      item: options.item,
      trigger: options.trigger,
      content: options.content,
      clicks: trace,
    }, null, 2));

    const files = states.map(state => path.join(out, state.id + '.json'));
    const python = process.env.PYTHON || 'python3';
    const run = (script, args) => execFileSync(python, ['-B', path.join(toolsDir, script), ...args], { stdio: 'inherit' });
    run('web_design_media.py', ['--survey', files[0], ...files.flatMap(f => ['--capture', f]), '--out-dir', path.join(out, 'media'), '--index', path.join(out, 'media.json')]);
    run('web_design_source.py', [...files.flatMap(f => ['--capture', f]), '--assets', path.join(out, 'media.json'), '--id', options.id, '--title', first.title, '--out', path.join(out, 'screens.json')]);
    run('native_edit.py', ['web-disclosure', '--graph', path.join(out, 'screens.json'), '--observations', path.join(out, 'observations.json'), '--out', path.join(out, 'disclosure-graph.json')]);
  });
}

const { values } = parseArgs({
  options: {
    ...Object.fromEntries(['url', 'accordion', 'item', 'trigger', 'content', 'out', 'id', 'frame-key', 'chrome', 'width', 'height', 'settle-ms']
      .map(key => [key, { type: 'string' }])),
    click: { type: 'string', multiple: true },
    help: { type: 'boolean' },
  },
});

if (values.help) {
  console.log(help);
  process.exit(0);
}

const width = Number(values.width || 1440);
const height = Number(values.height || 900);
values.id ||= 'captured-disclosure';
values['frame-key'] ||= 'faq';
values['settle-ms'] ||= '1500';
values.item = values.item ?? defaultItemSelector;
values.trigger = values.trigger ?? defaultTriggerSelector;
values.content = values.content ?? defaultContentSelector;

if (!values.accordion || !values.item || !values.trigger || !values.content
    || !values.out || !values.click?.length || values.click.length > 32
    || !/^https?:\/\//.test(values.url || '')
    || !/^[a-z0-9][a-z0-9-]{0,60}$/.test(values.id)
    || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$/.test(values['frame-key'])
    || !(Number(values['settle-ms']) >= 0 && Number(values['settle-ms']) <= 30000)
    || ![width, height].every(n => Number.isInteger(n) && n >= 100 && n <= 4096)) {
  throw Error(help);
}

const out = path.resolve(values.out);
await mkdir(out, { mode: 0o700 });
await capture(values, out, width, height);
