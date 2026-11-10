#!/usr/bin/env python3
"""Self-contained source/Pillow demo. No browser, Figma, approval or user records."""
import argparse
import hashlib
import json
from html import escape
from pathlib import Path
import shutil
import sys
from PIL import Image, ImageDraw, ImageFont

EXAMPLE=Path(__file__).resolve().parent
PLUGIN=EXAMPLE.parents[1]


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def pin(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build_files(root):
    """Regenerate only deterministic example source/data and explicitly labeled demo PNGs."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    (root/'brief.md').write_text('# Community workshop\nCompare two overview/detail directions before making a choice. No registration or purchases.\n')
    (root/'research.md').write_text('# Demo research boundary\nA bulletin prioritizes an introduction; an agenda prioritizes ordered session information. These are local test proposals, not usability research or browser/native evidence.\n')
    content={'title':'Community workshop','summary':'A place to learn practical skills together.','required_text':['Community workshop','Explore sessions'],'scope':'test/demo directions; not production'}
    dump(root/'content.json',content);candidates=[];native=[];assets={}
    for identity,title,composition in [('bulletin','Welcome board','A left text column and a warm sun illustration; two outlined session cards sit on a rounded sage table.'),('agenda','Session agenda','A tinted masthead with a clock illustration over a dotted timeline of rounded time rows.')]:
        folder=root/identity;folder.mkdir(exist_ok=True)
        paper,ink,accent,highlight=('#fffaf0','#20363d','#d8e8dc','#f2a65a')if identity=='bulletin'else('#f0f5fa','#152d4a','#c7ddf1','#3d6fd6')
        colors={'paper':paper,'ink':ink,'accent':accent,'highlight':highlight};overview='state-'+identity+'-overview';details='state-'+identity+'-details';open_action='action-'+identity+'-open';back_action='action-'+identity+'-back';screen='screen-'+identity+'-overview';detail_screen='screen-'+identity+'-details';open_control=identity+'-open';back_control=identity+'-back'
        annotations=[{'id':screen,'type':'screen','title':title,'annotation':{'purpose':'Introduce the community workshop and its session overview.','journey':'Read the introduction, inspect session details, then return without registering.','first_action':open_action,'failure':'This is a local demo; it never creates a registration.'}}, {'id':detail_screen,'type':'screen','title':'Session details','annotation':{'purpose':'Show the sample session information in a readable detail view.','journey':'Read the sample information and return to the workshop overview.','first_action':back_action,'failure':'The sample has no booking, payment or account functionality.'}}]
        nodes=annotations+[{'id':overview,'type':'state','title':'Workshop overview visible'},{'id':details,'type':'state','title':'Sample session details visible'}]
        for action,source,target,control,label,variant in [(open_action,screen,details,open_control,'Explore sessions','Primary'),(back_action,detail_screen,overview,back_control,'Back to overview','Return')]:
            nodes.append({'id':action,'type':'action','title':label,'source_screen':source,'source_state':overview if source==screen else details,'target_ids':[target],'annotation':{'control_id':control,'purpose':'Let visitors inspect the example and keep their place in the overview.','behavior':'Open the sample details view.'if source==screen else'Return to the workshop overview.','result':'The sample session text becomes visible.'if source==screen else'The overview becomes visible again.','failure':'No form data, registration, account or payment is created.','functional_states':[overview,details],'visual_variant':variant}})
        roles=[{'name':name+' color','kind':'color','token':'color/'+name,'alias':'palette/'+name,'value':value}for name,value in colors.items()]+[{'name':'Reading size','kind':'typography','token':'type/body','alias':'size/body','value':'16px','source_values':['16px']},{'name':'Reading family','kind':'typography','token':'type/family/body','alias':'font/family/body','value':'Inter','source_values':['Inter']},{'name':'Content gap','kind':'spacing','token':'space/content','alias':'space/base','value':'24px','source_values':['24px']},{'name':'Control radius','kind':'radius','token':'radius/control','alias':'radius/base','value':'6px','source_values':['6px']}]
        samples=[{'label':'Explore sample sessions','component':'component-'+identity+'-open','variant':'Primary','action':open_action,'state':details,'useCases':['Inspect the sample session from the overview']},{'label':'Return to overview','component':'component-'+identity+'-back','variant':'Return','action':back_action,'state':overview,'useCases':['Return without creating a registration']}]
        for sample in samples:nodes.append({'id':sample['component'],'type':'component','title':sample['label']})
        graph={'version':1,'stage':'draft','scope':'Self-contained test/demo source; no browser or native evidence','nodes':nodes,'edges':[edge for node in nodes if node['type']=='action' for edge in [{'from':node['source_screen'],'to':node['id'],'type':'enables'}]+[{'from':node['id'],'to':target,'type':'shows'} for target in node.get('target_ids',[])]],'design_foundations':{'version':1,'roles':roles,'palette':{'samples':samples}},'draft_prototype':{'entry_state':overview,'viewports':[{'id':'desktop','width':1200,'height':760},{'id':'mobile','width':360,'height':720}],'states':[{'id':overview,'screen':screen,'view':'workshop-overview','title':title,'body':content['summary']},{'id':details,'screen':detail_screen,'view':'session-detail','title':'Session details','body':'Repair skills · Saturday 10:00. Demo only; no registration.'}],'bindings':[{'action':action,'source_state':src,'target_state':target,'viewport':viewport,'control_id':control}for viewport in ('desktop','mobile')for action,src,target,control in [(open_action,overview,details,open_control),(back_action,details,overview,back_control)]]}}
        # A real local HTML prototype; its two authored forms differ structurally.
        overview_tag='article'if identity=='bulletin'else'section'
        form='<ul><li>Repair skills · 10:00</li><li>Paper craft · 13:00</li></ul>'if identity=='bulletin'else'<table><tr><th>10:00</th><td>Repair skills</td></tr><tr><th>13:00</th><td>Paper craft</td></tr></table>'
        html=f'''<!doctype html><meta charset="utf-8"><title>{title} demo</title><style>body{{font:16px/1.6 Inter,system-ui;background:{paper};color:{ink};padding:24px}}button{{font:inherit;padding:14px 24px;border-radius:6px}}[hidden]{{display:none}}</style><main><{overview_tag} id="{screen}"><h1>Community workshop</h1><p>{escape(content['summary'])}</p>{form}<button id="{open_control}">Explore sessions</button></{overview_tag}><section id="{detail_screen}" hidden><h2>Session details</h2><p>Repair skills · Saturday 10:00. Demo only; no registration.</p><button id="{back_control}">Back to overview</button></section></main><script>const overview=document.getElementById('{screen}'),details=document.getElementById('{detail_screen}');document.getElementById('{open_control}').onclick=()=>{{overview.hidden=true;details.hidden=false;}};document.getElementById('{back_control}').onclick=()=>{{details.hidden=true;overview.hidden=false;}};</script>'''
        (folder/'index.html').write_text(html)
        # Literal graph semantics and roles, visibly planned and linked; no native claim.
        docs=['<!doctype html><meta charset="utf-8"><title>Planned demo notes</title><h1>planned / not native · test/demo</h1>']
        for node in annotations+[n for n in nodes if n['type']=='action']:
            meaning=node['annotation'];target=meaning.get('control_id',node['id']);docs.append('<article><a href="index.html#'+target+'">'+escape(node['title'])+'</a>')
            for key,value in meaning.items():docs.append('<p>'+escape(key)+': '+escape(', '.join(value)if isinstance(value,list)else value)+'</p>')
            docs.append('</article>')
        for role in roles:docs.append('<p>'+' · '.join(escape(str(role[k]))for k in ('name','kind','token','value'))+'</p>')
        for sample in samples:docs.append('<p>'+' · '.join(escape(str(sample[k]))for k in ('label','component','variant','action','state'))+' · '+escape('; '.join(sample['useCases']))+'</p>')
        (folder/'inspect.html').write_text('\n'.join(docs))
        layouts={};state_layouts={};previews=[];refs={}
        for viewport,w,h in [('desktop',1200,760),('mobile',360,720)]:
            mobile=viewport=='mobile';margin=24 if mobile else 48
            boxes={open_control:[margin,h-112,min(w-margin*2,300),56]}
            first={'width':w,'height':h,'bg':'paper','layers':overview_layers(identity,mobile,content),'control_boxes':boxes};layouts[viewport]=first
            detail={'width':w,'height':h,'bg':'paper','layers':detail_layers(identity,mobile,w),'control_boxes':{back_control:[margin,h-112,min(w-margin*2,300),56]}}
            state_layouts[viewport]={overview:first,details:detail}
            path=root/'previews'/(identity+'-'+viewport+'.png');render_demo(path,first,colors,boxes,identity)
            asset=identity+'-reference-'+viewport;assets[asset]={'path':str(path.relative_to(root)),'sha256':pin(path),'reference':True};refs[viewport]=asset;previews.append({'path':str(path.relative_to(root)),'viewport':viewport,'width':w,'height':h})
        fonts={'display':{'family':'Inter','style':'Regular'},'body':{'family':'Inter','style':'Regular'}}
        control_styles={viewport:{variant:{'fill':'ink'if variant=='Primary'else'paper','ink':'paper'if variant=='Primary'else'ink','radius':6,'fontSize':16,'paddingX':24,'paddingY':14,'minHeight':44,'maxWidth':w-48}for variant in('Primary','Return')}for viewport,w in [('desktop',1200),('mobile',360)]}
        attach_native_roles(identity,graph,state_layouts,fonts,control_styles)
        for node in graph['nodes']:node.setdefault('status','planned')
        dump(folder/'graph.json',graph)
        native.append({'id':identity,'graph':{'path':identity+'/graph.json','sha256':pin(folder/'graph.json')},'colors':colors,'fonts':fonts,'layouts':layouts,'state_layouts':state_layouts,'references':refs,'control_styles':control_styles})
        candidates.append({'id':identity,'title':title,'source':identity+'/index.html','review':identity+'/inspect.html','graph':identity+'/graph.json','composition':composition,'typography':'Left-aligned 56px display greeting over a 14px kicker and 16px body; asymmetric against a large sun illustration.'if identity=='bulletin'else'48px masthead in a tinted band with a clock illustration; 20px times on a timeline beside 16px session names.','interaction':'Open a session from an introductory board and return to the greeting.'if identity=='bulletin'else'Inspect an agenda entry from a structured schedule and return to the list.','previews':previews})
    dump(root/'native-layout.json',{'schema':'figma-flow-authored-native-layout-v1','scope':'exploratory-only','production_admitted':False,'content':{'path':'content.json','sha256':pin(root/'content.json')},'assets':assets,'candidates':native})
    dump(root/'candidate-spec.json',{'content':{'path':'content.json'},'native_target':{'mode':'current-design-file'},'native_layout':{'path':'native-layout.json'},'candidates':candidates})


def attach_native_roles(identity,graph,state_layouts,fonts,control_styles):
    """Declare only actual source targets; auxiliary notes/palette typography stays separate."""
    targets={};body=[];controls=[]
    for viewport,layouts in state_layouts.items():
        for state,layout in layouts.items():
            for layer in layout['layers']:
                if layer['kind']!='text':continue
                key=f"{identity}.{viewport}.{state}.{layer['id']}"
                targets[key]={'fontSize':layer['size'],'fontFamily':fonts[layer.get('font','body')]['family']}
                if layer.get('font','body')=='body':body.append(key)
        for variant,style in control_styles[viewport].items():
            key=f"{identity}.{viewport}.component.{variant}"
            targets[key]={'paddingLeft':style['paddingX'],'paddingRight':style['paddingX'],'cornerRadius':style['radius']};controls.append(key)
            targets[key+'.label']={'fontSize':style['fontSize'],'fontFamily':fonts['body']['family']};body.append(key+'.label')
        for edge in graph['draft_prototype']['bindings']:
            if edge['viewport']!=viewport:continue
            layout=layouts.get(edge['source_state'])
            if not layout or edge['control_id']not in layout.get('control_boxes',{}):
                raise ValueError('Native role target missing from actual control layout: '+edge['control_id'])
            source=next(n for n in graph['nodes']if n['id']==edge['action'])
            style=control_styles[viewport][source['annotation']['visual_variant']]
            key=f"{identity}.{viewport}.{edge['source_state']}.{edge['control_id']}"
            targets[key]={'paddingLeft':style['paddingX'],'paddingRight':style['paddingX'],'cornerRadius':style['radius']};controls.append(key)
            targets[key+'.label']={'fontSize':style['fontSize'],'fontFamily':fonts['body']['family']};body.append(key+'.label')
    planned={'type/body':('FLOAT',16,body,['fontSize']),
             'type/family/body':('STRING','Inter',body,['fontFamily']),
             'space/content':('FLOAT',24,controls,['paddingLeft','paddingRight']),
             'radius/control':('FLOAT',6,controls,['cornerRadius'])}
    for role in graph['design_foundations']['roles']:
        if role['token']not in planned:continue
        kind,value,keys,fields=planned[role['token']]
        bindings=[{'key':key,'field':field}for key in keys for field in fields]
        role['native']={'type':kind,'value':value,'bindings':bindings}
    check_native_roles(graph,targets)
    return targets


def check_native_roles(graph,targets):
    for role in graph['design_foundations']['roles']:
        if role['kind']=='color':continue
        native=role.get('native',{});kind=native.get('type');value=native.get('value');bindings=native.get('bindings')
        if kind not in ('FLOAT','STRING')or not bindings:raise ValueError('Native role has no typed source targets: '+role['token'])
        for binding in bindings:
            actual=targets.get(binding['key'],{}).get(binding['field'])
            if actual!=value or (kind=='FLOAT'and type(actual)not in (int,float))or(kind=='STRING'and not isinstance(actual,str)):
                raise ValueError('Native role target missing or value/type mismatch: '+role['token']+' '+str(binding))


def T(id,value,x,y,w,h,size,font='body',ink='ink',leading=None,align='left'):
    return {'id':id,'kind':'text','value':value,'x':x,'y':y,'w':w,'h':h,'size':size,'leading':leading or round(size*1.4),'font':font,'ink':ink,'align':align}


def S(id,kind,x,y,w,h,fill,role,**extra):
    return {'id':id,'kind':kind,'x':x,'y':y,'w':w,'h':h,'fill':fill,'role':role,**extra}


SESSIONS=[('10:00','Repair skills'),('13:00','Paper craft'),('15:00','Shared questions')]


def overview_layers(identity,mobile,content):
    """Entry state: a real visual anchor, declared roles on every shape, 4-step type scale, no filler bars."""
    if identity=='bulletin':
        if mobile:
            layers=[S('sun-glow','ellipse',208,16,136,136,'highlight','illustration',opacity=.24),
                    S('sun','ellipse',228,36,96,96,'highlight','illustration'),
                    T('kicker','SATURDAY · COMMUNITY HALL',24,40,176,40,14,'display',leading=20),
                    T('headline',content['title'],24,160,312,96,36,'display',leading=44),
                    T('summary',content['summary'],24,264,312,48,16,leading=24),
                    S('table','rect',24,328,312,264,'accent','surface',radius=20)]
            for i,(time,name) in enumerate(SESSIONS[:2]):
                y=344+i*120
                layers+=[S('card-'+str(i),'rect',40,y,280,104,'paper','surface',radius=12,stroke='ink',stroke_width=2),
                         T('time-'+str(i),time,56,y+16,120,28,20,'display',leading=28),T('session-'+str(i),name,56,y+56,248,24,16,leading=24)]
            return layers
        layers=[S('sun-glow','ellipse',704,24,456,456,'highlight','illustration',opacity=.24),
                S('sun','ellipse',760,80,344,344,'highlight','illustration'),
                T('kicker','SATURDAY · COMMUNITY HALL',48,96,400,24,14,'display',leading=20),
                T('headline',content['title'],48,136,520,144,56,'display',leading=68),
                T('summary',content['summary'],48,304,440,56,16,leading=24),
                S('table','rect',632,344,520,312,'accent','surface',radius=24)]
        for i,(time,name) in enumerate(SESSIONS[:2]):
            y=376+i*136
            layers+=[S('card-'+str(i),'rect',664,y,456,112,'paper','surface',radius=16,stroke='ink',stroke_width=2),
                     T('time-'+str(i),time,696,y+20,120,28,20,'display',leading=28),T('session-'+str(i),name,696,y+60,400,24,16,leading=24)]
        return layers
    if mobile:
        layers=[S('masthead','rect',0,0,360,232,'accent','background'),
                S('clock','ellipse',240,32,96,96,'paper','illustration',stroke='highlight',stroke_width=6),
                S('clock-hour','rect',285,48,6,36,'ink','illustration',radius=3),
                S('clock-minute','rect',285,78,30,6,'ink','illustration',radius=3),
                T('kicker','SATURDAY · 3 SESSIONS',24,40,200,24,14,'display',leading=20),
                T('headline',content['title'],24,72,208,80,32,'display',leading=40),
                T('summary',content['summary'],24,160,312,48,16,leading=24),
                S('timeline','rect',36,280,4,200,'highlight','illustration',radius=2)]
        for i,(time,name) in enumerate(SESSIONS):
            y=264+i*80
            layers+=[S('dot-'+str(i),'ellipse',28,y+18,20,20,'highlight','illustration',stroke='paper',stroke_width=3),
                     S('row-'+str(i),'rect',64,y,272,56,'accent','surface',radius=12),
                     T('time-'+str(i),time,80,y+12,64,32,20,'display',leading=32),T('row-text-'+str(i),name,144,y+16,184,24,16,leading=24)]
        return layers
    layers=[S('masthead','rect',0,0,1200,248,'accent','background'),
            S('clock','ellipse',944,36,176,176,'paper','illustration',stroke='highlight',stroke_width=8),
            S('clock-hour','rect',1028,64,8,64,'ink','illustration',radius=4),
            S('clock-minute','rect',1028,120,56,8,'ink','illustration',radius=4),
            T('kicker','SATURDAY · 3 SESSIONS',48,64,400,24,14,'display',leading=20),
            T('headline',content['title'],48,96,760,64,48,'display',leading=60),
            T('summary',content['summary'],48,176,760,32,16,leading=24),
            S('timeline','rect',88,296,4,216,'highlight','illustration',radius=2)]
    for i,(time,name) in enumerate(SESSIONS):
        y=288+i*80
        layers+=[S('dot-'+str(i),'ellipse',78,y+16,24,24,'highlight','illustration',stroke='paper',stroke_width=4),
                 S('row-'+str(i),'rect',128,y,1024,56,'accent','surface',radius=12),
                 T('time-'+str(i),time,152,y+12,96,32,20,'display',leading=32),T('row-text-'+str(i),name,264,y+16,600,24,16,leading=24)]
    return layers


def detail_layers(identity,mobile,w):
    margin=24 if mobile else 48
    art=(S('sun','ellipse',w-margin-96,48,96,96,'highlight','illustration')if identity=='bulletin'else
         S('clock','ellipse',w-margin-96,48,96,96,'paper','illustration',stroke='highlight',stroke_width=6))
    band=[]if identity=='bulletin'else[S('masthead','rect',0,0,w,192,'accent','background')]
    text_w=w-margin*2-(112 if mobile else 128)
    return band+[art,
            T('kicker','REPAIR SKILLS · 10:00',margin,56,text_w,24,14,'display',leading=20),
            T('headline','Session details',margin,88,text_w,48 if not mobile else 80,28,'display',leading=36),
            T('body','Repair skills · Saturday 10:00. Demo only; no registration.',margin,216,w-margin*2,72,16,leading=24)]


def _rgba(hex_value,opacity=1):
    return tuple(int(hex_value[i:i+2],16)for i in (1,3,5))+(round(255*opacity),)


def render_demo(path,layout,colors,boxes,identity):
    """Labeled Pillow approximation of the authored layers: radius, stroke, ellipse and opacity included."""
    path.parent.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGBA',(layout['width'],layout['height']),_rgba(colors[layout['bg']]))
    for layer in layout['layers']:
        if layer['kind']in('rect','ellipse'):
            overlay=Image.new('RGBA',image.size,(0,0,0,0));draw=ImageDraw.Draw(overlay)
            box=(layer['x'],layer['y'],layer['x']+layer['w']-1,layer['y']+layer['h']-1);opacity=layer.get('opacity',1)
            outline=_rgba(colors[layer['stroke']],opacity)if 'stroke'in layer else None;width=round(layer.get('stroke_width',0))
            if layer['kind']=='ellipse':draw.ellipse(box,fill=_rgba(colors[layer['fill']],opacity),outline=outline,width=width)
            else:draw.rounded_rectangle(box,radius=layer.get('radius',0),fill=_rgba(colors[layer['fill']],opacity),outline=outline,width=width)
            image=Image.alpha_composite(image,overlay)
        elif layer['kind']=='text':
            draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=layer['size']);y=layer['y']
            for line in wrap(layer['value'],font,layer['w']):
                draw.text((layer['x'],y),line,font=font,fill=_rgba(colors[layer['ink']]));y+=layer['leading']
    draw=ImageDraw.Draw(image)
    for control,box in boxes.items():
        label='Explore sessions'if control.endswith('-open')else'Back to overview'
        draw.rounded_rectangle((box[0],box[1],box[0]+box[2],box[1]+box[3]),radius=6,fill=_rgba(colors['ink']));draw.text((box[0]+24,box[1]+18),label,font=ImageFont.load_default(size=16),fill=_rgba(colors['paper']))
    draw.text((16,layout['height']-24),'PIL DEMO / not browser or Figma evidence / '+identity,font=ImageFont.load_default(size=10),fill=_rgba(colors['ink']))
    image.convert('RGB').save(path)


def wrap(value,font,width):
    lines=[]
    for paragraph in value.split('\n'):
        line=''
        for word in paragraph.split(' '):
            trial=(line+' '+word).strip()
            if line and font.getlength(trial)>width:lines.append(line);line=word
            else:line=trial
        lines.append(line)
    return lines


def instantiate(out):
    out=Path(out).resolve()
    if out==EXAMPLE or EXAMPLE in out.parents:raise ValueError('Output must be outside the installed example')
    if out.exists():raise ValueError('Choose a new output directory; existing data is never replaced')
    shutil.copytree(EXAMPLE,out,ignore=shutil.ignore_patterns('__pycache__'))
    sys.path.insert(0,str(PLUGIN/'tools'));import design_directions,workflow
    initial=design_directions.create_draft(out,'brief.md','research.md','candidate-spec.json',out/'review')
    manifest=Path(initial['manifest']);data=json.loads(manifest.read_text())
    # A fixture/source review, explicitly not browser, native or human-choice evidence.
    judgement={'role':'agent','scope':'fixture-source/Pillow-demo-only; not browser/Figma/human approval','draft_content_sha256':design_directions.digest(data['candidates']),'candidates':[{'id':c['id'],'candidate_sha256':c['sha256'],'composition':c['composition']+' Verified from the shipped deterministic Pillow layout data.','typography':c['typography']+' Native Inter rendering remains unobserved.','interaction':c['interaction']+' Verified as source graph/control coverage only.','truth_and_notes':'Planned notes and palette fields link exact HTML controls. PNGs are Pillow demo references, not browser captures or native results; no choice/approval exists.'}for c in data['candidates']]}
    dump(out/'fixture-source-review.json',judgement)
    design_directions.review_draft(manifest,out/'fixture-source-review.json')
    final=json.loads(manifest.read_text())
    if final['workflow_symbol']!=workflow.State.NATIVE_REVIEW_PENDING.name:raise ValueError('Default must wait for real native review')
    if 'selection'in final or final.get('production_admitted'):raise ValueError('Demo cannot select or approve')
    return {'manifest':str(manifest),'workflow_symbol':final['workflow_symbol'],'production_admitted':False,'evidence':'source/Pillow demo only; actual Figma run pending'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);p.add_argument('--regenerate-fixture',action='store_true');args=p.parse_args()
    if args.regenerate_fixture:build_files(EXAMPLE);print('Regenerated example inputs and labeled Pillow demos only.')
    elif args.out:print(json.dumps(instantiate(args.out),indent=2))
    else:p.error('--out NEW_DIRECTORY or --regenerate-fixture required')


if __name__=='__main__':main()
