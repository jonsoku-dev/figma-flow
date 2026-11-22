const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');

test('standalone Design views apply graph-owned CSS and input limits to actual browser elements',async()=>{
  const root=path.resolve(__dirname,'..');
  const stage=fs.mkdtempSync(path.join(os.tmpdir(),'flow-view-'));
  const copy=name=>{
    const dest=path.join(stage,name);
    fs.mkdirSync(path.dirname(dest),{recursive:true});
    fs.cpSync(path.join(root,name),dest,{recursive:true,filter:file=>!file.includes('node_modules')&&!file.includes('__pycache__')});
  };
  const change=(name,edit)=>{
    const dest=path.join(stage,name),data=JSON.parse(fs.readFileSync(dest));
    edit(data);fs.writeFileSync(dest,JSON.stringify(data));
  };
  try {
    for(const name of ['tools/plugin_panel.py','tools/panel_components.py','tools/relay_limits.py','plugin.json','figma-bridge','library/panel-design','library/figma-profile','panel-ui/src'])copy(name);
    change('figma-bridge/standalone-views.json',g=>{
      g.views.import.values.miniPagesWidth='56px';
      g.views.graph.values.swatchHeight='49px';
      g.views.workspace.values.previewImageHeight='190px';
    });
    change('figma-bridge/chat-input.json',g=>{
      g.message.rows=5;g.message.maxCharacters=321;g.preview.legacyRows=13;
    });
    const render=name=>{
      const p=spawnSync(process.env.PYTHON||'python3',['-B','-c', "from pathlib import Path;import sys;sys.path.insert(0,'tools');from plugin_panel import render_panel;print(render_panel((Path('figma-bridge')/sys.argv[1]).read_text()))",name],{cwd:stage,encoding:'utf8',maxBuffer:5e6});
      assert.equal(p.status,0,p.stderr);
      return p.stdout.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
    };
    const {chromiumBinary,withChromiumPage}=await import('../tools/chromium_pipe.mjs');
    await withChromiumPage(chromiumBinary(),async({command,evaluate})=>{
      await command('Page.enable'); const {frameTree}=await command('Page.getFrameTree');
      const set=async name=>command('Page.setDocumentContent',{frameId:frameTree.frame.id,html:render(name)});
      await set('ui.html');
      assert.equal(await evaluate("getComputedStyle(document.querySelector('.mini-pages')).width"),'56px');
      await set('graph-panel.html');
      assert.equal(await evaluate("(()=>{const n=document.createElement('b');n.className='swatch';document.body.append(n);return getComputedStyle(n).height})()"),'49px');
      await set('workspace_home.html');
      assert.equal(await evaluate("(()=>{const g=document.createElement('div');g.className='preview-strip';const n=document.createElement('img');g.append(n);document.body.append(g);return getComputedStyle(n).height})()"),'190px');
      await set('workspace_chat.html');
      assert.deepEqual(await evaluate("[document.querySelector('#request').rows,document.querySelector('#request').maxLength,document.querySelector('#preview').rows]"),[5,321,13]);
    });
  } finally {fs.rmSync(stage,{recursive:true,force:true});}
});
