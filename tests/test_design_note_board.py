"""Mock standard Plugin APIs only; this is not a live Design-mode usability result."""
from pathlib import Path
import json
import subprocess
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'figma-bridge/design_note_board.js'


class DesignNoteBoardTests(unittest.TestCase):
    def run_js(self, body):
        setup = """
const assert=require('node:assert/strict');
const {ensureDesignNoteBoard}=require(HELPER);
let seq=0,failLinks=false,styles=0;
class Node {
 constructor(type){this.id=String(++seq);this.type=type;this.name=type;this.children=[];this.data={};this.width=100;this.height=20;this.x=0;this.y=0;this.visible=true;}
 appendChild(n){if(n.parent)n.parent.children=n.parent.children.filter(c=>c!==n);n.parent=this;this.children.push(n);}
 setPluginData(k,v){this.data[k]=v;}getPluginData(k){return this.data[k]||'';}
 async loadAsync(){}findAll(test){return this.children.flatMap(c=>[...(test(c)?[c]:[]),...c.findAll(test)]);}
 resize(w,h){this.width=w;this.height=h;this.primaryAxisSizingMode='FIXED';this.counterAxisSizingMode='FIXED';this.textAutoResize='NONE';}
 setRangeHyperlink(start,end,link){assert.equal(start,0);assert.equal(end,this.characters.length);if(!failLinks)this.hyperlink=link;}
 getRangeHyperlink(start,end){assert.equal(start,0);assert.equal(end,this.characters.length);return this.hyperlink;}
 remove(){this.removed=true;this.parent.children=this.parent.children.filter(c=>c!==this);}
}
const page=new Node('PAGE'),target=new Node('FRAME');target.name='실제 참여 화면';page.appendChild(target);
const figma={createFrame:()=>new Node('FRAME'),createText:()=>new Node('TEXT'),async loadFontAsync(font){assert.equal(font.family,'Explicit Source Font');}};
const contract={sourceHash:'approved-hash',font:{family:'Explicit Source Font',style:'Regular'},fontSize:17,x:0,y:800,
 notes:[{key:'ACT-START',targetId:target.id,label:'선택한 참여 화면으로 이동하고 첫 설명을 표시한다.'}],
 async styleText(node){styles++;node.boundVariables={fontSize:{type:'VARIABLE_ALIAS',id:'source-type'}};}};
""".replace('HELPER', json.dumps(str(HELPER)))
        result = subprocess.run(['node', '-e', setup + '\n(async()=>{' + body + '\n})().catch(e=>{console.error(e);process.exit(1)});'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_readable_ordinary_board_native_link_typography_and_owned_rollback(self):
        self.run_js("""
const result=await ensureDesignNoteBoard(figma,page,contract);
const board=page.children.find(n=>n.id===result.boardId),note=board.children.find(n=>n.id===result.entries[0].textNodeId);
assert.equal(board.type,'FRAME');assert.equal(board.y,800);assert.equal(board.primaryAxisSizingMode,'AUTO');assert.equal(board.counterAxisSizingMode,'FIXED');
assert.equal(board.layoutMode,'VERTICAL');assert(board.itemSpacing>0);assert.equal(board.clipsContent,false);
assert.equal(note.textAutoResize,'HEIGHT');assert.equal(note.fontName.family,'Explicit Source Font');assert.equal(note.fontSize,17);
assert.deepEqual(note.hyperlink,{type:'NODE',value:target.id});assert(note.characters.includes(contract.notes[0].label));
assert.equal(styles,2);assert.equal(note.boundVariables.fontSize.id,'source-type');
const again=await ensureDesignNoteBoard(figma,page,contract);assert.equal(again.boardId,result.boardId);
await again.rollback();assert(!board.removed);await result.rollback();assert(board.removed);assert.deepEqual(page.children,[target]);
""")

    def test_missing_link_or_foreign_target_fails_without_owned_artifact_leaks(self):
        self.run_js("""
failLinks=true;
await assert.rejects(ensureDesignNoteBoard(figma,page,contract),/hyperlink not retained/);
assert.deepEqual(page.children,[target]);failLinks=false;
await assert.rejects(ensureDesignNoteBoard(figma,page,{...contract,notes:[{...contract.notes[0],targetId:'other-page'}]}),/selected-page target/);
assert.deepEqual(page.children,[target]);
await assert.rejects(ensureDesignNoteBoard(figma,page,{...contract,font:null}),/explicit font/);
""")

    def test_existing_board_is_verified_without_overwriting_unrelated_work(self):
        self.run_js("""
const result=await ensureDesignNoteBoard(figma,page,contract),board=page.children.find(n=>n.id===result.boardId);
board.children[1].hyperlink={type:'NODE',value:'wrong'};
await assert.rejects(ensureDesignNoteBoard(figma,page,contract),/hyperlink not retained/);
assert.equal(board.children[1].hyperlink.value,'wrong');assert(!board.removed);
board.setPluginData('designNoteBoard','foreign');
await assert.rejects(ensureDesignNoteBoard(figma,page,contract),/unowned board/);
assert(!target.removed);
""")


if __name__ == '__main__':
    unittest.main()
