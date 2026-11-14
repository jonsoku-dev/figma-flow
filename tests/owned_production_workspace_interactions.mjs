// Drive the served owned production workspace in headless Chromium and print observed interaction results.
import { setTimeout as pause } from 'node:timers/promises';
import { chromiumBinary, until, withChromiumPage } from '../tools/chromium_pipe.mjs';

const [url] = process.argv.slice(2);
let binary;
try {
  binary = chromiumBinary();
} catch {
  console.log(JSON.stringify({ skipped: 'no Chromium executable' }));
  process.exit(0);
}

await withChromiumPage(binary, async ({ command, evaluate }) => {
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await command('Page.navigate', { url });
  await until(() => evaluate("document.querySelector('main[data-ready=true]') ? true : null"), Date.now() + 15000, 'review screen not ready');

  const openGate = () => evaluate(`(() => {
    const triggers = Array.from(document.querySelectorAll('[data-slot="accordion-trigger"]'));
    const open = triggers.map(trigger => trigger.getAttribute('aria-expanded') === 'true');
    const panels = triggers.map(trigger => !document.getElementById(trigger.getAttribute('aria-controls')).hidden);
    if (open.some((value, index) => value !== panels[index]) || open.filter(Boolean).length > 1) return 'inconsistent';
    return open.indexOf(true) === -1 ? null : open.indexOf(true);
  })()`);
  const railCard = async () => {
    let previous = null;
    for (let stable = 0; stable < 4;) {
      await pause(120);
      const left = await evaluate("document.getElementById('evidence-rail').scrollLeft");
      stable = left === previous ? stable + 1 : 0;
      previous = left;
    }
    return evaluate(`(() => {
      const rail = document.getElementById('evidence-rail');
      const first = rail.firstElementChild.offsetLeft;
      const distance = Array.from(rail.children, card => Math.abs(card.offsetLeft - first - rail.scrollLeft));
      return distance.indexOf(Math.min(...distance));
    })()`);
  };
  const clickGate = index => evaluate(`document.querySelectorAll('[data-slot="accordion-trigger"]')[${index}].click()`);
  const clickRail = index => evaluate(`document.querySelectorAll('[aria-controls="evidence-rail"]')[${index}].click()`);

  const gates = [await openGate()];
  for (const index of [0, 1, 1, 0, 0]) {
    await clickGate(index);
    await pause(60);
    gates.push(await openGate());
  }
  const rail = [await railCard()];
  for (const index of [1, 1, 1, 0, 0, 0]) {
    await clickRail(index);
    rail.push(await railCard());
  }
  console.log(JSON.stringify({ gates, rail }));
});
