const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const folder = process.argv[2];
const html = fs.readFileSync(path.join(folder,'ui.html'),'utf8');
const model = JSON.parse(html.match(/<script[^>]+>(.+)<\/script>/)[1]);
const page = {id:'2:3',children:[],selection:[]};
page.findAllWithCriteria = ({types, pluginData}) => {
  const found = [];
  function visit(parent) {
    for (const child of parent.children) {
      if (types.includes(child.type) && pluginData.keys.some(key => child.getPluginData(key))) found.push(child);
      visit(child);
    }
  }
  visit(page);
  return found;
};
const messages = [];
let count = 0;
function node(type) {
  const data = new Map();
  const n={id:'2:'+ ++count,type,children:[],parent:page,x:0,width:0,resize(width){this.width=width;},
    getPluginData:k=>data.get(k)||'',setPluginData:(k,v)=>data.set(k,v),
    appendChild(c){c.parent.children.splice(c.parent.children.indexOf(c),1);c.parent=this;this.children.push(c);}};
  page.children.push(n);return n;
}
const figma = {editorType:'figma',mode:'default',fileKey:'fixture',currentPage:page,
  ui:{postMessage:m=>messages.push(m)},showUI(){},closePlugin(){throw Error('relay closed');},
  createFrame:()=>node('FRAME'),createRectangle:()=>node('RECTANGLE'),viewport:{scrollAndZoomIntoView(){}}};
vm.runInNewContext(fs.readFileSync(path.join(folder,'code.js'),'utf8'),{figma,__html__:html});
async function run(type) {await figma.ui.onmessage({type,session:model.session});return messages.at(-1).readback;}
(async()=>{
  assert.equal((await run('read')).container,null);
  const first=await run('apply');assert.equal(first.created,true);assert.equal(first.container.childCount,4);
  const again=await run('apply');assert.equal(again.created,false);assert.equal(again.container.id,first.container.id);
  assert.equal(page.children.length,1);
  const wrapper=node('FRAME');
  wrapper.appendChild(page.children[0]);
  const nested=await run('apply');
  assert.equal(nested.created,false);
  assert.equal(nested.container.id,first.container.id);
  assert.equal(page.children.length,1);
  figma.fileKey='another';await assert.rejects(run('apply'),/prepared Design file/);
})().catch(e=>{console.error(e);process.exitCode=1;});
