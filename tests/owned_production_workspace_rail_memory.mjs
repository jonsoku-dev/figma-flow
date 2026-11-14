// Drive rail and gate input with real pointer and wheel events in headless Chromium and print rail positions.
import { setTimeout as pause } from 'node:timers/promises';
import { chromiumBinary, until, withChromiumPage } from '../tools/chromium_pipe.mjs';

const [url, width, height] = process.argv.slice(2);
let binary;
try {
  binary = chromiumBinary();
} catch {
  console.log(JSON.stringify({ skipped: 'no Chromium executable' }));
  process.exit(0);
}

await withChromiumPage(binary, async ({ command, evaluate }) => {
  await command('Emulation.setDeviceMetricsOverride', { width: Number(width), height: Number(height), deviceScaleFactor: 1, mobile: Number(width) < 600 });
  const ready = () => until(() => evaluate("document.querySelector('main[data-ready=true]') ? true : null"), Date.now() + 15000, 'screen not ready');
  await command('Page.navigate', { url });
  await ready();

  const settle = async () => {
    let previous = null;
    for (let stable = 0; stable < 4;) {
      await pause(120);
      const left = await evaluate("document.getElementById('evidence-rail')?.scrollLeft ?? null");
      stable = left === previous ? stable + 1 : 0;
      previous = left;
    }
  };
  const position = async () => {
    await settle();
    return evaluate(`(() => {
      const rail = document.getElementById('evidence-rail');
      const first = rail.firstElementChild.offsetLeft;
      const distance = Array.from(rail.children, card => Math.abs(card.offsetLeft - first - rail.scrollLeft));
      return distance.indexOf(Math.min(...distance));
    })()`);
  };
  const center = selector => evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    element.scrollIntoView({ block: 'center', inline: 'nearest' });
    const { x, y, width, height } = element.getBoundingClientRect();
    return { x: x + width / 2, y: y + height / 2 };
  })()`);
  const pointer = async selector => {
    const { x, y } = await center(selector);
    for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) {
      await command('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
    }
    await pause(150);
  };
  const wheel = async deltaX => {
    const { x, y } = await center('#evidence-rail');
    await command('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX, deltaY: 0 });
  };
  const gate = index => `[data-slot="accordion-item"]:nth-child(${index + 1}) [data-slot="accordion-trigger"]`;
  const steps = [];
  const record = async label => steps.push({ label, position: await position(), hash: await evaluate('location.hash') });

  await record('entered review');
  await wheel(250);
  await record('direct scroll');
  await pointer(gate(0));
  await record('gate opened after direct scroll');
  await pointer(gate(0));
  await record('gate closed after direct scroll');
  await pointer('[aria-controls="evidence-rail"]:last-of-type');
  await record('next pressed');
  await pointer(gate(1));
  await record('gate opened after next');
  await pointer('.decision-form button[type="submit"]');
  await record('invalid decision re-render');
  await pointer('#review-back');
  await ready();
  await pointer('tbody tr:nth-child(2) button');
  await ready();
  await record('new review entered');
  console.log(JSON.stringify({ steps }));
});
