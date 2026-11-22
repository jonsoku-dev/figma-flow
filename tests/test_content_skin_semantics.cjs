const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname,'..');

test('the generated skin follows its label, measured caps and declared heading relationship', async () => {
  const {chromiumBinary,withChromiumPage} = await import('../tools/chromium_pipe.mjs');
  const css=fs.readFileSync(path.join(root,'tools/content-skin.css'),'utf8');
  const js=fs.readFileSync(path.join(root,'tools/content_skin.js'),'utf8');
  await withChromiumPage(chromiumBinary(), async({evaluate,command})=>{
    const {frameTree}=await command('Page.getFrameTree');
    await command('Page.setDocumentContent',{frameId:frameTree.frame.id,html:'<style>'+css+'</style><main></main>'});
    await evaluate(js);
    const sizes=await evaluate(`(()=>{
      const form={roleId:'action',label:'Short',imageUrl:'local-skin.png',slice:6,cap:6};
      const button=createContentSkin(form);
      document.querySelector('main').append(button);
      const before=button.getBoundingClientRect().width, style=getComputedStyle(button);
      const padding=style.paddingLeft, height=button.getBoundingClientRect().height;
      button.querySelector('[data-skin-label]').textContent='An extended label that needs more space';
      const after=button.getBoundingClientRect().width;
      const heading=createContentSkin({...form,tag:'h2',titleFor:'appointments',padding:12});
      document.querySelector('main').append(heading);
      return {before,after,height,padding,heading:heading.dataset.titleFor,
        explicit:getComputedStyle(heading).paddingLeft,cap:style.borderLeftWidth,
        type:button.type};
    })()`);
    assert.ok(sizes.after>sizes.before);
    assert.ok(sizes.height>=44);
    assert.equal(sizes.padding,'4px');
    assert.equal(sizes.explicit,'12px');
    assert.equal(sizes.cap,'6px');
    assert.equal(sizes.type,'button');
    assert.equal(sizes.heading,'appointments');
    await assert.rejects(evaluate("createContentSkin({tag:'h2',label:'Heading',roleId:'heading',imageUrl:'image.png',slice:8,cap:6})"),/titleFor/);
  });
  const retired=require('../tools/browser_probes.js');
  for(const call of Object.values(retired)) assert.throws(()=>call(),/disabled/);
});
