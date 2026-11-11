// Synthetic Figma geometry models the observed HUG + SPACE_BETWEEN zero-gap failure.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../figma-bridge/direction_review.js'),'utf8');
function host(){const h=vm.createContext({DRAFT:{assets:{}},__html__:'',figma:{showUI(){},ui:{postMessage(){}}}});vm.runInContext(source,h);return h;}
async function create(style){
 const h=host(),paints=[],bindings=[];
 const main={height:46,width:100,children:[],resize(w,height){this.width=w;this.height=height;}};
 function layout(){if(main.primaryAxisSizingMode==='AUTO')main.width=main.paddingLeft+97+18+main.paddingRight;main.children[0].x=main.paddingLeft;main.children[1].x=main.width-main.paddingRight-18;}
 Object.assign(h,{style,c:{id:'map',action_notes:{submit:{visual_variant:'Submit',action:'submit'}},action_labels:{submit:'Pick a seat'}},viewport:'desktop',visual:'Submit',library:{appendChild(){}},tag(){},layoutBindings(){},paint(n,c,name,field='fills'){assert.equal(typeof name,'string');paints.push([name,field]);n[field]=[{type:'SOLID'}];},bind(...args){bindings.push(args);},intendedDraftRole:()=>null,text:async()=>{const n={type:'TEXT',width:97,height:20};main.children.push(n);return n;},image(){},addDraftControlIcon(){main.children.push({width:18,height:18});layout();}});
 h.figma.createComponent=()=>main;
 const start=source.indexOf("const key=c.id+'.'+viewport+'.component.'+visual,n=figma.createComponent()"),end=source.indexOf('mains.set(',start);
 await vm.runInContext('(async()=>{'+source.slice(start,end)+'})()',h);
 return {h,main,paints,bindings};
}
const style={fill:null,ink:'ink',radius:0,fontSize:16,paddingX:16,paddingY:13,minHeight:46,maxWidth:292,justifyContent:'space-between',icon:{width:18,height:18,gap:12}};
test('native creation keeps explicit null unpainted and fixed width preserves endpoint spacing',async()=>{
 const {h,main,paints}=await create({...style,stroke:'ink',stroke_width:1});
 assert.deepEqual(JSON.parse(JSON.stringify(main.fills)),[]);assert.deepEqual(paints,[['ink','strokes']]);
 assert.equal(main.primaryAxisSizingMode,'FIXED');assert.equal(main.width,292);assert.equal(main.height,46);
 assert.equal(main.children[1].x-(main.children[0].x+97),145);assert.equal(main.strokeWeight,1);
 const errors=[];h.validateDraftControlFill(main,style,m=>errors.push(m));assert.deepEqual(errors,[]);
 for(const change of [()=>{main.fills=[{type:'SOLID'}];},()=>{main.fills=[];main.boundVariables={fills:[{id:'variable'}]};},()=>{delete main.fills;main.boundVariables={};}]){change();h.validateDraftControlFill(main,style,m=>errors.push(m));}
 assert.equal(errors.length,3);
});
test('legacy centered HUG and named fill remain unchanged; observed HUG between has zero spare gap',async()=>{
 const {h,main,paints}=await create({...style,fill:'paper',justifyContent:'center'});
 assert.equal(main.primaryAxisSizingMode,'AUTO');assert.deepEqual(paints,[['paper','fills']]);
 main.primaryAxisAlignItems='SPACE_BETWEEN';assert.equal(main.children[1].x-(main.children[0].x+97),0);
 const errors=[];h.validateDraftControlFill(main,{fill:'paper'},m=>errors.push(m));assert.deepEqual(errors,[]);
});
test('color admission preserves ink and stroke consumers, skips only explicit null fill',()=>{
 const h=host(),colors={paper:'#ffffff',ink:'#111111'},roles=Object.entries(colors).map(([name,value])=>({kind:'color',token:'color/'+name,value}));
 const candidate={id:'x',colors,foundations:{roles},graph:{design_foundations:{roles}},foundationBindings:[],control_styles:{},state_layouts:{},action_labels:{back:'Back'},action_notes:{'back|back':{action:'back',visual_variant:'Return'}},prototype:{states:[{id:'entry'}],bindings:[]}};
 for(const viewport of ['desktop','mobile']){
  candidate.control_styles[viewport]={Return:{fill:null,ink:'ink',stroke:'ink'}};
  candidate.state_layouts[viewport]={entry:{width:320,height:240,bg:'paper',layers:[],control_boxes:{back:[20,20,200,46]},product_buttons:{clear:{variant:'Return',label:'Clear',box:[20,100,200,46]}}}};
  candidate.prototype.bindings.push({viewport,source_state:'entry',action:'back',control_id:'back'});
 }
 const reports=h.admitDraftColorConsumers([candidate]);const targets=JSON.parse(JSON.stringify(reports.flatMap(row=>row.consumers)));
 for(const viewport of ['desktop','mobile'])for(const id of ['back','clear']){
  const key='x.'+viewport+'.entry.'+id;
  assert(!targets.some(t=>t.key===key&&t.field==='fills'));
  assert(targets.some(t=>t.key===key&&t.field==='strokes'));
  assert(targets.some(t=>t.key===key+'.label'&&t.field==='fills'));
 }
 delete candidate.control_styles.desktop.Return.fill;
 assert.throws(()=>h.admitDraftColorConsumers([candidate]),/undeclared paint/);
});
