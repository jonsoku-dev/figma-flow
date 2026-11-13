const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../figma-bridge/web_design.js'), 'utf8');
const context = vm.createContext({ setTimeout, clearTimeout });
vm.runInContext(`${source}\nglobalThis.previewPolicy = webPreviewNeedsWarmup; globalThis.exportPreview = webExportPreview;`, context);

function screen(elements) { return { elements }; }
function receipt(reused = false) { return { reused }; }

test('new image-backed screen discards one warmup and returns rendered bytes', async () => {
  const outputs = [new Uint8Array([0]), new Uint8Array([3, 4, 5])];
  let calls = 0;
  const frame = { exportAsync: async () => { calls++; return outputs.shift(); } };
  const bytes = await context.exportPreview(frame, 1, true);
  assert.deepEqual(Array.from(bytes), [3, 4, 5]);
  assert.equal(calls, 2);
});

test('vector-only and reused image screens export once, preserving valid monochrome PNG bytes', async () => {
  const monoPng = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC', 'base64');
  for (const [design, applied] of [
    [screen([{ kind: 'vector' }]), receipt(false)],
    [screen([{ kind: 'image', asset: { sha256: 'image-hash' } }]), receipt(true)],
  ]) {
    assert.equal(context.previewPolicy(design, applied, {}), false);
    let calls = 0;
    const bytes = await context.exportPreview({ exportAsync: async () => { calls++; return monoPng; } }, 1, false);
    assert.deepEqual(Array.from(bytes), Array.from(monoPng));
    assert.equal(calls, 1);
  }
});

test('only an applied video fallback requests warmup', () => {
  const video = { kind: 'video', asset: { sha256: 'video-hash' } };
  const design = screen([video]);
  assert.equal(context.previewPolicy(design, receipt(false), { 'video-hash': { mode: 'fallback' } }), true);
  assert.equal(context.previewPolicy(design, receipt(false), { 'video-hash': { mode: 'native' } }), false);
  assert.equal(context.previewPolicy(design, receipt(false), {}), false);
});
