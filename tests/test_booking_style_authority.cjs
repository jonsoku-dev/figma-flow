const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const http = require('node:http');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const app = path.join(root, 'apps/little-hands');

test('a rebuilt booking theme follows graph fields on the captured member home at both widths', async () => {
  const { chromiumBinary, withChromiumPage } = await import('../tools/chromium_pipe.mjs');
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'booking-style-'));
  const from = path.join(app, 'design');
  const design = path.join(temp, 'design');
  const asset = path.join(temp, 'static/littlehands/app.css');
  const meta = path.join(temp, 'templates/includes/theme_color.html');
  const project = (...args) => spawnSync(process.env.PYTHON || 'python3', ['-B', path.join(design, 'publish_styles.py'), ...args], {encoding:'utf8'});
  let server;
  try {
    fs.mkdirSync(design);
    fs.mkdirSync(path.dirname(asset), {recursive:true});
    fs.mkdirSync(path.dirname(meta), {recursive:true});
    for (const name of ['publish_styles.py', 'tokens.json', 'stylesheet.json']) fs.copyFileSync(path.join(from, name), path.join(design, name));
    assert.equal(project('--write').status, 0);
    for (const output of ['static/littlehands/app.css', 'templates/includes/theme_color.html']) {
      assert.deepEqual(fs.readFileSync(path.join(temp, output)), fs.readFileSync(path.join(app, output)));
    }
    const tokenPath = path.join(design, 'tokens.json');
    const tokens = JSON.parse(fs.readFileSync(tokenPath));
    tokens.colors.paper = '#123456';
    tokens.layout.desktop_gutter = 58;
    tokens.layout.mobile_gutter = 11;
    tokens.layout.mobile_breakpoint = 680;
    tokens.image.desktop_aspect_ratio = 2.5;
    fs.writeFileSync(tokenPath, JSON.stringify(tokens));
    assert.notEqual(project().status, 0, 'A stale shipped projection must be rejected');
    assert.equal(project('--write').status, 0);
    assert.equal(project().status, 0);
    assert.match(fs.readFileSync(meta,'utf8'), /content="#123456"/);
    const capture = JSON.parse(fs.readFileSync(path.join(from, 'captures/memberhome-desktop.json')));
    const html = capture.html.replace(/<link\b[^>]*rel="stylesheet"[^>]*>/,
      () => '<style>' + fs.readFileSync(asset, 'utf8') + '</style>');
    const photo = fs.readdirSync(path.join(from,'source_assets/littlehands')).find(name => name.endsWith('.jpg'));
    server=http.createServer((req,res) => {
      if (req.url === '/') { res.setHeader('Content-Type','text/html; charset=utf-8'); res.end(html); }
      else if (req.url === '/static/littlehands/'+photo) { res.setHeader('Content-Type','image/jpeg');res.end(fs.readFileSync(path.join(from,'source_assets/littlehands',photo))); }
      else if (req.url === '/fonts/Hahmlet.woff2') { res.setHeader('Content-Type','font/woff2');res.end(fs.readFileSync(path.join(app,'static/littlehands/fonts/Hahmlet.woff2'))); }
      else {res.statusCode=404;res.end();}
    });
    await new Promise((resolve,reject) => { server.once('error', reject);server.listen(0,'127.0.0.1',resolve); });
    await withChromiumPage(chromiumBinary(), async ({command, evaluate}) => {
      await command('Page.enable');
      await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'});
      const { until } = await import('../tools/chromium_pipe.mjs');
      await until(async () => evaluate("document.querySelector('.hero-photo') ? true : null"), Date.now()+10000, 'Booking capture did not load');
      await evaluate('document.fonts.ready.then(()=>true)');
      const observed = async (width) => {
        await command('Emulation.setDeviceMetricsOverride', {width,height:800,deviceScaleFactor:1,mobile:false});
        return evaluate(`({background:getComputedStyle(document.body).backgroundColor,
          gutter:getComputedStyle(document.querySelector('.site-header')).paddingLeft,
          ratio:getComputedStyle(document.querySelector('.hero-photo')).aspectRatio})`);
      };
      assert.deepEqual(await observed(700), {background:'rgb(18, 52, 86)',gutter:'58px',ratio:'2.5 / 1'});
      assert.deepEqual(await observed(640), {background:'rgb(18, 52, 86)',gutter:'11px',ratio:'1.65 / 1'});
      const measure = fs.readFileSync(path.join(from, 'measure.js'), 'utf8');
      const readback = await evaluate(measure + '\nJSON.stringify(littleHandsMeasure("state-memberhome"))');
      const measured = JSON.parse(readback);
      assert.equal(measured.viewport.width, 640);
      assert.equal(measured.state, capture.state);
      assert.ok(measured.texts.some(item => item.value.trim().length > 1));
      assert.ok(measured.surfaces.length > 0);
      assert.ok(!measured.html.includes('<script'));
      await evaluate('document.body.dataset.environment="production"');
      await assert.rejects(evaluate('littleHandsMeasure("state-memberhome")'), /non-staging/);
      await evaluate(fs.readFileSync(path.join(app,'static/littlehands/app.js'),'utf8'));
      assert.deepEqual(await evaluate(`(() => {
        const form=document.createElement('form');
        form.dataset.submitFeedback='';form.innerHTML='<span class="form-busy" hidden></span>';
        document.body.appendChild(form);
        form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
        const busy=form.getAttribute('aria-busy')==='true' && !form.firstElementChild.hidden;
        window.dispatchEvent(new Event('pageshow'));
        return [busy, !form.hasAttribute('aria-busy') && form.firstElementChild.hidden];
      })()`),[true,true]);
    });
  } finally {
    if (server?.listening) await new Promise(resolve=>server.close(resolve));
    fs.rmSync(temp, {recursive:true,force:true});
  }
});
