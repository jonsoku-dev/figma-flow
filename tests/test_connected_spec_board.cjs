const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const vm = require('node:vm');
const path = require('node:path');
vm.runInThisContext(execFileSync('python3.13', ['-B', '-c',
  'import sys; sys.path.insert(0, sys.argv[1]); from specification_contract import spec_label_prelude; sys.stdout.write(spec_label_prelude())',
  path.join(__dirname, '../tools')], {encoding: 'utf8'}));
const {ensureDesignNoteBoard} = require('../figma-bridge/design_note_board.js');
let sequence = 0;
class Node {
  constructor(type) { Object.assign(this,{id:String(++sequence),type,name:type,children:[],data:{},x:0,y:0,width:100,_height:20,visible:true}); }
  get height() {
    if(this.type==='FRAME'&&this.layoutMode==='VERTICAL'&&this.primaryAxisSizingMode==='AUTO')return this.paddingTop+this.paddingBottom+this.children.reduce((sum,node)=>sum+node.height,0)+Math.max(0,this.children.length-1)*this.itemSpacing;
    if(this.type==='TEXT'&&this.textAutoResize==='HEIGHT')return Math.max(20,Math.ceil((this.characters||'').length/80)*20);
    return this._height;
  }
  set height(value) { this._height=value; }
  appendChild(node) { if(node.parent) node.parent.children=node.parent.children.filter(child=>child!==node);node.parent=this;this.children.push(node); }
  resize(width,height) { this.width=width;this._height=height; }
  setPluginData(key,value) { this.data[key]=value; }
  getPluginData(key) { return this.data[key] || ''; }
  async loadAsync() {}
  findAll(test) { return this.children.flatMap(node=>[...(test(node)?[node]:[]),...node.findAll(test)]); }
  setRangeHyperlink(start,end,link) { this.link=link; }
  getRangeHyperlink() { return this.link; }
  remove() { this.removed=true;this.parent.children=this.parent.children.filter(node=>node!==this); }
}
const spec = (display_text,presentation) => ({schema:'figma-flow-readable-spec-v1',id:'SPEC-one',meaning_sha256:'a'.repeat(64),title:'기능 설명',display_text,...(presentation?{presentation}:{})});
function setup(presentation='connected-spec-v2') {
  const page=new Node('PAGE'),target=new Node('FRAME');page.appendChild(target);
  const neighbor=new Node('FRAME');neighbor.x=0;neighbor.y=11431;neighbor.resize(760,120);page.appendChild(neighbor);
  const figma={createFrame:()=>new Node('FRAME'),createText:()=>new Node('TEXT'),loadFontAsync:async()=>{}};
  const contract={presentation:'readable-specs',sourceHash:'owner',font:{family:'Explicit',style:'Regular'},notes:[{key:'map.one',targetId:target.id,specification:spec('짧은 설명',presentation)}]};
  return {page,target,neighbor,figma,contract};
}
async function ownedScene(presentation) {
  const env=setup(presentation), first=await ensureDesignNoteBoard(env.figma,env.page,env.contract);
  const board=env.page.children.find(node=>node.id===first.boardId);
  board.x=0;board.y=9091;
  return {...env,first,board};
}

(async()=>{
  {
    const e=await ownedScene('connected-spec-v2'), entry=e.board.children[1];
    const originalTarget={x:e.target.x,y:e.target.y};
    e.contract.notes[0].specification=spec('상세 설명. '.repeat(11000),'connected-spec-v2');
    const update=await ensureDesignNoteBoard(e.figma,e.page,e.contract);
    assert.equal(e.board.x,824);assert.equal(e.board.y,0);assert.equal(update.changed,2);
    assert.equal(update.entries[0].textNodeId,entry.id);assert.equal(entry.getRangeHyperlink().value,e.target.id);
    assert.deepEqual({x:e.target.x,y:e.target.y},originalTarget);assert.equal(e.neighbor.y,11431);
    const again=await ensureDesignNoteBoard(e.figma,e.page,e.contract);
    assert.equal(again.changed,0);assert.equal(e.board.x,824);assert.equal(e.board.y,0);
    await update.rollback();assert.equal(e.board.x,0);assert.equal(e.board.y,9091);assert.equal(entry.characters,'기능 설명\n짧은 설명');
    assert.equal(entry.id,update.entries[0].textNodeId);assert.equal(entry.getRangeHyperlink().value,e.target.id);
  }
  {
    const e=await ownedScene(undefined);
    e.contract.notes[0].specification=spec('상세 설명. '.repeat(11000));
    await assert.rejects(ensureDesignNoteBoard(e.figma,e.page,e.contract),/overlaps artwork/);
    assert.equal(e.board.x,0);assert.equal(e.board.y,9091);
  }
  {
    const e=await ownedScene('connected-spec-v2');
    e.contract.notes[0].specification=spec('상세 설명. '.repeat(11000),'connected-spec-v2');
    const update=await ensureDesignNoteBoard(e.figma,e.page,e.contract);
    e.board.x=9999;e.board.y=777;
    await assert.rejects(update.rollback(),/concurrent board position conflict/);
    assert.equal(e.board.x,9999);assert.equal(e.board.y,777);
  }
})().catch(error=>{console.error(error);process.exit(1);});
