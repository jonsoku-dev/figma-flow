#!/usr/bin/env python3
"""Prepare and verify exploratory Figma directions. Never selects or approves one."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import re
import shutil
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS=Path(__file__).resolve().parent
if str(TOOLS) not in sys.path: sys.path.insert(0,str(TOOLS))
from embedded_assets import embedded_asset_warnings
import annotation_contract
from draft_foundation_audit import audit_draft_foundations
from draft_token_plan import foundation_bindings
import design_directions

PLUGIN=TOOLS.parent
HELPERS=('semantic_tokens.js','native_annotations.js','native_semantic_read.js','foundation_palette.js','design_note_board.js')
PRIVATE=Path.home()/'Library/Application Support/Figma Flow/night-editions'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical_sha(value): return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def now(): return datetime.now(timezone.utc).isoformat()
def write_json(path,value): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def checked_review(manifest):
    result=design_directions.validate_draft(Path(manifest),require_native_review=False)
    data=result['data']
    if data.get('scope')!='exploratory-only' or not 2<=len(data['candidates'])<=3:
        raise ValueError('Two or three checked exploratory candidates required')
    for candidate in data['candidates']:
        for field in ('source','review','product_graph'):
            design_directions.current(candidate[field])
        for preview in candidate['previews']: design_directions.current(preview['file'])
    return data




BASE_LAYER=('id','kind','x','y','w','h')
LAYER_FIELDS={'text':BASE_LAYER+('value','size','leading','ink','font','align'),
              'rect':BASE_LAYER+('fill','radius','stroke','stroke_width','opacity','role'),
              'ellipse':BASE_LAYER+('fill','stroke','stroke_width','opacity','role'),
              'gradient':BASE_LAYER+('direction','stops','opacity','role'),
              'image':BASE_LAYER+('asset','fit','opacity','role')}
LAYER_ROLES={'background','surface','illustration','image','divider','ornament','frame'}
IMAGE_FITS={'FILL','FIT','CROP','TILE'}


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def check_layer(layer,colors,assets,key):
    """Reject an authored layer before any Figma write unless every property is declared and in range."""
    where=key+'.'+str(layer.get('id','?'))if isinstance(layer,dict)else key
    if not isinstance(layer,dict)or layer.get('kind')not in LAYER_FIELDS:raise ValueError('Only declared native draft layer kinds allowed: '+where)
    kind=layer['kind'];extra=set(layer)-set(LAYER_FIELDS[kind])
    if extra:raise ValueError('Undeclared native draft layer property '+', '.join(sorted(extra))+' at '+where)
    if not isinstance(layer.get('id'),str)or not layer['id']or not all(_finite(layer.get(k))for k in('x','y','w','h'))or layer['w']<=0 or layer['h']<=0:raise ValueError('Finite positive native layer geometry required: '+where)
    if 'role'in layer and layer['role']not in LAYER_ROLES:raise ValueError('Unknown native layer role '+repr(layer['role'])+' at '+where)
    if 'opacity'in layer and not(_finite(layer['opacity'])and 0<layer['opacity']<=1):raise ValueError('Native layer opacity must be within (0, 1]: '+where)
    if kind in('rect','ellipse'):
        if layer.get('fill')not in colors:raise ValueError('Declared color role required for fill at '+where)
        thin=min(layer['w'],layer['h'])/2
        if ('stroke'in layer)!=('stroke_width'in layer):raise ValueError('stroke and stroke_width must be declared together: '+where)
        if 'stroke'in layer:
            if layer['stroke']not in colors:raise ValueError('Declared color role required for stroke at '+where)
            if not(_finite(layer['stroke_width'])and 0<layer['stroke_width']<=thin):raise ValueError('stroke_width must be within (0, min(w,h)/2]: '+where)
        if 'radius'in layer and not(_finite(layer['radius'])and 0<=layer['radius']<=thin):raise ValueError('radius must be within [0, min(w,h)/2]: '+where)
    elif kind=='image':
        if layer.get('asset')not in assets:raise ValueError('Pinned raster asset required at '+where)
        if 'fit'in layer and layer['fit']not in IMAGE_FITS:raise ValueError('Image fit must be one of FILL, FIT, CROP, TILE (Figma scaleMode): '+where)
    elif kind=='gradient':
        stops=layer.get('stops')
        if layer.get('direction','vertical')not in('horizontal','vertical'):raise ValueError('Gradient direction must be horizontal or vertical: '+where)
        if not isinstance(stops,list)or len(stops)<2 or not all(isinstance(stop,dict)for stop in stops):raise ValueError('Gradient needs at least two stops: '+where)
        last=0
        for stop in stops:
            if set(stop)!={'position','color','opacity'}or not isinstance(stop['color'],str)or not re.fullmatch(r'#[0-9a-fA-F]{6}',stop['color'])or not all(_finite(stop[k])and 0<=stop[k]<=1 for k in('position','opacity'))or stop['position']<last:
                raise ValueError('Gradient stops need #RRGGBB color, opacity and non-decreasing position in [0, 1]: '+where)
            last=stop['position']


def layout_errors(authored):
    """Every authored-layout problem at once (before any packet or Figma write), not only the first."""
    problems=[]
    rows=authored.get('candidates')
    rows=list(rows.values())if isinstance(rows,dict)else rows if isinstance(rows,list)else[]
    assets=authored.get('assets')if isinstance(authored.get('assets'),dict)else{}
    for c in rows:
        if not isinstance(c,dict):problems.append('candidate row must be an object');continue
        cid=str(c.get('id','?'));colors=c.get('colors')if isinstance(c.get('colors'),dict)else{};fonts=c.get('fonts')if isinstance(c.get('fonts'),dict)else{}
        for role,font in fonts.items():
            if not isinstance(font,dict)or not isinstance(font.get('family'),str)or not font['family']or not isinstance(font.get('style'),str)or not font['style']:problems.append(f'{cid}: font role {role} needs family and style')
        for viewport,states in(c.get('state_layouts')or{}).items():
            for state_id,l in(states or{}).items():
                key=f'{cid}.{viewport}.{state_id}'
                if not isinstance(l,dict)or not all(_finite(l.get(k))and l[k]>0 for k in('width','height')):problems.append(key+': width/height must be finite and > 0');continue
                controls=set(l.get('control_boxes')or{});seen=set()
                for layer in l.get('layers')if isinstance(l.get('layers'),list)else[]:
                    try:check_layer(layer,colors,assets,key)
                    except ValueError as error:problems.append(str(error));continue
                    lid=layer['id']
                    if lid in seen:problems.append(f'{key}.{lid}: duplicate layer id')
                    if lid in controls:problems.append(f'{key}.{lid}: layer id collides with control id')
                    seen.add(lid)
                    if layer['kind']=='text':
                        if not isinstance(layer.get('value'),str)or not layer['value'].strip()or not _finite(layer.get('size'))or layer['size']<=0:problems.append(f'{key}.{lid}: text needs a value and a positive size')
                        if(layer.get('font')or'body')not in fonts:problems.append(f"{key}.{lid}: unknown font role {layer.get('font')or'body'!r}")
                        if layer.get('ink')not in colors:problems.append(f"{key}.{lid}: undeclared ink {layer.get('ink')!r}")
    return problems


def _hex_map(value):
    """Compare color roles by name and value; HEX letter case is not a different color."""
    return {k:v.lower()for k,v in value.items()}if isinstance(value,dict)and all(isinstance(v,str)for v in value.values())else value


def make_packet(manifest,layout_path=None,file_key=None):
    data=checked_review(manifest)
    packet_hash=design_directions.review_packet_sha256(data)
    content=json.loads(design_directions.current(data['content']).read_text())
    root=Path(data['project_root']).resolve();layout_record=data.get('native_layout')or data.get('native_target',{}).get('layout')
    if not layout_record:raise ValueError('Checked review must pin its owned authored native layout before packaging')
    pinned_layout=design_directions.current(layout_record,root).resolve()
    layout_path=Path(layout_path or pinned_layout).resolve()
    if layout_path!=pinned_layout:raise ValueError('Explicit layout differs from immutable reviewed layout pin')
    if root not in layout_path.parents: raise ValueError('Authored layout must belong to the reviewed project')
    authored=json.loads(layout_path.read_text());layout_hash=sha(layout_path.read_bytes())
    if authored.get('schema')!='figma-flow-authored-native-layout-v1'or authored.get('scope')!='exploratory-only':raise ValueError('Explicit exploratory native layout required')
    problems=layout_errors(authored)
    if problems:raise ValueError('Authored layout invalid ('+str(len(problems))+'):\n- '+'\n- '.join(problems))
    target=data.get('native_target',{'mode':'current-design-file'})
    if target.get('mode')not in ('current-design-file','exact-file'):raise ValueError('Explicit current-design-file or exact-file native target required')
    if target['mode']=='exact-file':
        if file_key and file_key!=target.get('file_key'):raise ValueError('Explicit target differs from reviewed exact file')
        file_key=target.get('file_key')
    if file_key and not re.fullmatch(r'[A-Za-z0-9_-]+',file_key):raise ValueError('Safe exact target file key required')
    prepared_target={'mode':'exact-file','file_key':file_key}if file_key else{'mode':'current-design-file'}
    native_candidates={c['id']:c for c in authored['candidates']}
    if set(native_candidates)!={c['id']for c in data['candidates']}:raise ValueError('Layout candidate identities must match reviewed candidates')
    candidates=[];assets={};pins=[]
    for candidate in data['candidates']:
        graph=json.loads(design_directions.current(candidate['product_graph']).read_text());prototype=graph.get('draft_prototype')
        if not prototype or not prototype.get('states') or not prototype.get('bindings'): raise ValueError('Canonical native draft prototype states/returns required: '+candidate['id'])
        notes=annotation_contract.derive_notes(graph);by_node={n['id']:n for n in graph['nodes']};by_note={n['id']:n for n in notes}
        states={state['id']:state for state in prototype['states']}
        if not states or len(states)!=len(prototype['states']):raise ValueError('Unique canonical review states required')
        marked=[state['id']for state in states.values()if state.get('entry')]
        entry=prototype.get('entry_state')or(marked[0]if len(marked)==1 else next(iter(states)))
        if len(marked)>1 or entry not in states:raise ValueError('Unambiguous declared entry state required')
        def reached(edges,start):
            found={start};todo=[start]
            while todo:
                for other in edges.get(todo.pop(),[]):
                    if other not in found:found.add(other);todo.append(other)
            return found
        for viewport in ('desktop','mobile'):
            forward={};reverse={}
            for edge in prototype['bindings']:
                if edge['viewport']!=viewport:continue
                forward.setdefault(edge['source_state'],[]).append(edge['target_state']);reverse.setdefault(edge['target_state'],[]).append(edge['source_state'])
            if reached(forward,entry)!=set(states)or reached(reverse,entry)!=set(states):raise ValueError('Every canonical state must be reachable out and back in each viewport')
        for state in states.values():
            if by_node.get(state['id'],{}).get('type')!='state' or by_node.get(state['screen'],{}).get('type')!='screen': raise ValueError('State/screen must be canonical')
        for edge in prototype['bindings']:
            action=by_node.get(edge['action'],{});note=by_note.get(edge['action'],{})
            if action.get('type')!='action' or edge['source_state']not in states or edge['target_state']not in states or edge['viewport']not in('desktop','mobile'):
                raise ValueError('Canonical per-viewport prototype edge required')
            matches=[n for n in notes if n.get('action')==edge['action']and edge['control_id']in(set(n.get('control_ids',[]))|{n.get('control_id')})]
            if len(matches)!=1: raise ValueError('Control does not match canonical annotation')
        foundations=graph['design_foundations']
        if len((foundations.get('palette')or{}).get('samples')or[])<2:raise ValueError('Documented primary/secondary samples required: '+candidate['id'])
        colors={r['token'].split('/')[-1]:r['value']for r in foundations['roles']if r['kind']=='color'}
        source=native_candidates[candidate['id']]
        if source['graph']['sha256']!=candidate['product_graph']['sha256']or _hex_map(source.get('colors'))!=_hex_map(colors):raise ValueError('Authored layout graph/color roles mismatch')
        if not source.get('fonts')or not source.get('control_styles'):raise ValueError('Exact configured native fonts/control styles required')
        action_notes={edge['action']+'|'+edge['control_id']:next(n for n in notes if n.get('action')==edge['action']and edge['control_id']in(set(n.get('control_ids',[]))|{n.get('control_id')}))for edge in prototype['bindings']}
        for viewport in ('desktop','mobile'):
            if set(source['state_layouts'][viewport])!=set(states):raise ValueError('Exact canonical states required in every viewport')
            for state_id,state_layout in source['state_layouts'][viewport].items():
                expected_controls={e['control_id']for e in prototype['bindings']if e['viewport']==viewport and e['source_state']==state_id}
                if set(state_layout['control_boxes'])!=expected_controls:raise ValueError('Exact state control layout required')
                if not any(l['kind']=='text'for l in state_layout['layers']):raise ValueError('Editable text required; screenshots-only review is invalid')
                for layer in state_layout['layers']:
                    check_layer(layer,source['colors'],authored['assets'],f"{candidate['id']}.{viewport}.{state_id}")
                    if layer['kind']=='image'and authored['assets'][layer['asset']].get('reference'):raise ValueError('Browser screenshots may only be separate labeled references')
        refs={}
        for preview in candidate['previews']:
            names=[name for name,record in authored['assets'].items()if record.get('reference')and record['sha256']==preview['file']['sha256']]
            if len(names)!=1:raise ValueError('Exact labeled raster reference required')
            refs[preview['viewport']]=names[0]
        c={**source,'id':candidate['id'],'title':candidate['title'],'sha256':candidate['sha256'],'graph':graph,'notes':notes,'action_notes':action_notes,'action_labels':{node['id']:node['title']for node in graph['nodes']if node['type']=='action'},'foundations':foundations,'colors':colors,'prototype':prototype,'entry_state':entry,'references':refs}
        c['foundationBindings'] = foundation_bindings(source, graph)
        candidates.append(c)
    for name,record in authored['assets'].items():
        path=(layout_path.parent/record['path']).resolve()
        if root not in path.parents or path.is_symlink()or sha(path.read_bytes())!=record['sha256']:raise ValueError('Pinned owned draft asset required')
        assets[name]=base64.b64encode(path.read_bytes()).decode();pins.append({'path':str(path),'sha256':record['sha256']})
    importer_hash=canonical_sha({name:sha((PLUGIN/'figma-bridge'/name).read_bytes())for name in (*HELPERS,'direction_review.js')})
    instance_hash=canonical_sha({'packet':packet_hash,'layout':layout_hash,'fileKey':file_key,'importer':importer_hash})
    return {'schema':'figma-flow-native-direction-review-v1','scope':'exploratory-only','production_admitted':False,'fileKey':file_key,'prepared_target':prepared_target,'instance_sha256':instance_hash,'importer_sha256':importer_hash,'layout_sha256':layout_hash,'layout_pin':{'path':str(layout_path),'sha256':layout_hash},'packet_sha256':packet_hash,'manifest':str(Path(manifest).resolve()),'candidate_pins':{c['id']:c['sha256']for c in candidates},'content':content,'candidates':candidates,'assets':assets,'input_pins':pins,'prepared_at':now(),'execution_status':'prepared-not-executed','boundary':'Reference images are raster; authored titles/body/controls/role palette are native editable nodes. No approval, final asset batch or reservation.'}


def verify_native_review(manifest_path,readback_path):
    report={'passed':False,'errors':[],'scope':'exploratory-only','production_admitted':False,'evidence':'supplied-native-readback-not-origin-authentication','screens':[],'annotation_checks':[],'foundation_checks':[],'prototype_checks':[],'return_checks':[],'design_note_board_checks':[],'dev_mode_required':False}
    try:
        raw=json.loads(Path(readback_path).read_text());packet=make_packet(manifest_path,raw.get('layout_pin',{}).get('path'),raw.get('prepared_target',{}).get('file_key'));nodes={n['id']:n for n in raw['nodes']};keyed={n.get('semanticKey'):n for n in raw['nodes']if n.get('semanticKey')}
        if not raw.get('fileKey')or packet['fileKey']and raw.get('fileKey')!=packet['fileKey']or raw.get('instance_sha256')!=packet['instance_sha256'] or raw.get('packet_sha256')!=packet['packet_sha256'] or raw.get('candidate_pins')!=packet['candidate_pins'] or raw.get('scope')!='exploratory-only'or raw.get('production_admitted')is not False or raw.get('approved')is True: raise ValueError('Exact current checked draft inputs/file/scope required')
        page=nodes.get(raw.get('pageId'),{});report.update(file_key=raw['fileKey'],page_id=raw['pageId'],packet_sha256=raw['packet_sha256'])
        if page.get('type')!='PAGE' or raw.get('page_owner')!=packet['instance_sha256']: raise ValueError('Owned draft root page required')
        for candidate in packet['candidates']:
            notes={n['id']:n for n in candidate['notes']};states={s['id']:s for s in candidate['prototype']['states']}
            for viewport in ('desktop','mobile'):
                for state in states.values():
                    key=f"{candidate['id']}.{viewport}.{state['id']}";node=keyed.get(key)
                    if not node or node.get('type')!='FRAME': raise ValueError('Actual editable draft frame missing: '+key)
                    for layer in candidate['state_layouts'][viewport][state['id']]['layers']:
                        actual=keyed.get(key+'.'+layer['id'])
                        if layer['kind']=='text':
                            expected_font=candidate['fonts'][layer.get('font','body')];actual_font=(actual or{}).get('fontName',{})
                            if not actual or actual.get('type')!='TEXT'or actual.get('characters')!=layer['value']or any(actual_font.get(field)!=expected_font[field]for field in ('family','style'))or any(actual_font.get('variationSettings',{}).get(axis)!=value for axis,value in expected_font.get('variationSettings',{}).items())or abs(actual.get('fontSize',0)-layer['size'])>.001:raise ValueError('Actual editable text/font differs from authored layout: '+key+'.'+layer['id'])
                        elif layer['kind']in('rect','ellipse'):
                            expected_type='RECTANGLE'if layer['kind']=='rect'else'ELLIPSE'
                            if not actual or actual.get('type')!=expected_type:raise ValueError('Actual editable native shape missing: '+key+'.'+layer['id'])
                            checks=[('opacity',layer.get('opacity',1))]
                            if layer['kind']=='rect'and layer.get('radius'):checks.append(('cornerRadius',layer['radius']))
                            if 'stroke'in layer:checks.append(('strokeWeight',layer['stroke_width']))
                            for field,expected in checks:
                                observed=actual.get(field,1 if field=='opacity'else None)
                                if not _finite(observed)or abs(observed-expected)>.001:raise ValueError('Native shape '+field+' differs from authored layout: '+key+'.'+layer['id'])
                            if 'stroke'in layer and not any(paint.get('type')=='SOLID'and paint.get('visible',True)for paint in actual.get('strokes',[])or[]):raise ValueError('Native shape stroke missing: '+key+'.'+layer['id'])
                        elif layer['kind']=='gradient':
                            fills=(actual or{}).get('fills');paint=fills[0]if isinstance(fills,list)and fills and isinstance(fills[0],dict)else{}
                            if paint.get('type')!='GRADIENT_LINEAR'or len(paint.get('gradientStops',[]))!=len(layer['stops']):raise ValueError('Editable native source gradient missing')
                            for stop,expected in zip(paint['gradientStops'],layer['stops']):
                                rgb_value={k:int(expected['color'][offset:offset+2],16)/255 for k,offset in [('r',1),('g',3),('b',5)]};rgb_value['a']=expected['opacity']
                                if abs(stop['position']-expected['position'])>.0001 or any(abs(stop['color'][k]-v)>.0001 for k,v in rgb_value.items()):raise ValueError('Native gradient differs from authored source stops')
                    check_note(node,notes[state['screen']]);report['screens'].append({'key':key,'id':node['id'],'viewport':viewport,'state':state['id']})
                for edge in [e for e in candidate['prototype']['bindings']if e['viewport']==viewport]:
                    src=f"{candidate['id']}.{viewport}.{edge['source_state']}";target=keyed[f"{candidate['id']}.{viewport}.{edge['target_state']}"]
                    node=keyed.get(src+'.'+edge['control_id']);note=candidate['action_notes'][edge['action']+'|'+edge['control_id']]
                    if not node or node.get('type')!='INSTANCE' or nodes.get(node.get('mainComponentId'),{}).get('type')!='COMPONENT': raise ValueError('Real reusable control missing')
                    check_note(node,note);report['annotation_checks'].append({'key':node['semanticKey'],'action':edge['action'],'states':note['functional_states']})
                    actions=[a for r in node.get('reactions',[])for a in r.get('actions',[])if r.get('trigger',{}).get('type')=='ON_CLICK']
                    if not any(a.get('type')=='NODE'and a.get('navigation')=='NAVIGATE'and a.get('destinationId')==target['id']for a in actions): raise ValueError('Exact native click destination missing: '+node['semanticKey'])
                    item={'source':node['id'],'destination':target['id'],'action':edge['action']};report['prototype_checks'].append(item)
                    if edge['target_state']==candidate['entry_state']:report['return_checks'].append(item)
            palette=raw.get('palettes',{}).get(candidate['id'],{})
            if not palette.get('libraryId')in nodes or not nodes[palette['libraryId']].get('visible',True):raise ValueError('Visible role palette missing')
            if len(palette.get('samples',[]))<2:raise ValueError('Documented primary/secondary samples required')
            for sample in palette['samples']:
                if nodes.get(sample.get('instanceId'),{}).get('type')!='INSTANCE' or not sample.get('action')or not sample.get('state')or not sample.get('useCases'):raise ValueError('Real meaningful palette sample missing')
            note_board=raw.get('noteFrames',{}).get(candidate['id'],{})
            board_node=nodes.get(note_board.get('boardId'),{})
            if board_node.get('type')!='FRAME'or board_node.get('visible')is False or board_node.get('layoutMode')!='VERTICAL':raise ValueError('Ordinary Design-mode note board missing')
            entries={entry['targetId']:entry for entry in note_board.get('entries',[])}
            targets=[]
            for viewport in ('desktop','mobile'):
                for state in states.values():targets.append((keyed[f"{candidate['id']}.{viewport}.{state['id']}"],notes[state['screen']]))
                for edge in [e for e in candidate['prototype']['bindings']if e['viewport']==viewport]:targets.append((keyed[f"{candidate['id']}.{viewport}.{edge['source_state']}."+edge['control_id']],candidate['action_notes'][edge['action']+'|'+edge['control_id']]))
            for target,note in targets:
                entry=entries.get(target['id'],{});text=nodes.get(entry.get('textNodeId'),{})
                if text.get('type')!='TEXT'or text.get('visible')is False or text.get('fontSize',0)<14 or text.get('parentId')!=board_node['id']:raise ValueError('Readable ordinary Design note text missing')
                for field in ('purpose','behavior','result','journey','action'):
                    if note.get(field)and note[field]not in text.get('characters',''):raise ValueError('Visible Design note omits source meaning')
                link=text.get('hyperlink')
                if not isinstance(link,dict)or link.get('type')!='NODE'or link.get('value')!=target['id']:raise ValueError('Actual same-file Design target hyperlink missing')
                if text.get('y',0)+text.get('height',0)>board_node.get('height',0)-board_node.get('paddingBottom',0)+1:raise ValueError('Ordinary note board clips readable text')
            report['design_note_board_checks'].append({'candidate':candidate['id'],'board_id':board_node['id'],'linked_targets':len(targets),'design_url':'https://www.figma.com/design/'+raw['fileKey']+'?node-id='+board_node['id'].replace(':','-')})
            audit=audit_draft_foundations(raw,candidate);report['foundation_checks'].append(audit)
            if not audit.get('passed',audit.get('ok')):raise ValueError('Actual draft foundations: '+'; '.join(audit.get('errors',[])))
        if not raw.get('variables')or not raw.get('collections')or not raw.get('textStyles'):raise ValueError('Actual native variables and typography styles required')
        variable_ids={v['id']for v in raw['variables']}
        for n in nodes.values():
            if n.get('type')=='PAGE':continue
            for field in('fills','strokes'):
                for paint in n.get(field,[])if isinstance(n.get(field),list)else[]:
                    if paint.get('type')=='SOLID'and paint.get('visible',True)and paint.get('opacity',1)>0:
                        alias=paint.get('boundVariables',{}).get('color',{})
                        if alias.get('id')not in variable_ids:raise ValueError('Unbound visible solid paint: '+n['id'])
            if n.get('type')=='TEXT'and n.get('characters'):
                alias=n.get('boundVariables',{}).get('fontSize',{})
                if isinstance(alias,list):alias=alias[0]if len(alias)==1 else{}
                if alias.get('id')not in variable_ids:raise ValueError('Native typography role unbound: '+n['id'])
        report['source_readback']={'path':str(Path(readback_path).resolve()),'sha256':sha(Path(readback_path).read_bytes())}
        report['layout_sha256']=packet['layout_sha256']
        report['design_url']='https://www.figma.com/design/'+raw['fileKey']+'?node-id='+raw['pageId'].replace(':','-')
        report['passed']=True;report['observed_at']=raw.get('observed_at');report['received_at']=now()
    except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError)as error:report['errors'].append(str(error))
    return report


def check_note(node,note):
    text='\n'.join(a.get('label','')for a in node.get('annotations',[]))
    for field in('purpose','behavior','result','journey','first_action','action'):
        if note.get(field)and note[field]not in text:raise ValueError('Canonical native annotation field missing: '+field)
    for state in note.get('functional_states',[]):
        if state not in text:raise ValueError('Canonical native functional state missing')


def prepare(manifest,out,register=False,port=49185,layout_path=None,file_key=None,plugin_id=None,night_demo=False):
    if register and not night_demo:raise ValueError('No implicit NIGHT registration: use an explicit task demo or the normal portable local plugin package.')
    if register:
        allowed_file = os.environ.get('FIGMA_FLOW_NIGHT_FILE_KEY')
        assigned_id = os.environ.get('FIGMA_FLOW_NIGHT_PLUGIN_ID')
        if not allowed_file or not assigned_id:
            raise ValueError('Set the owned NIGHT demo file key and plugin ID before private registration')
        if file_key not in (None, allowed_file) or plugin_id not in (None, assigned_id):
            raise ValueError('Task-owned NIGHT registration cannot target another file or plugin')
        file_key, plugin_id = allowed_file, assigned_id
    packet=make_packet(manifest,layout_path,file_key);admission=design_directions.admit_native_draft(Path(manifest))
    if admission['packet_sha256']!=packet['packet_sha256']:raise ValueError('Draft admission packet mismatch')
    if not isinstance(plugin_id,str) or not re.fullmatch(r'[0-9]+',plugin_id):raise ValueError('Supply the numeric local plugin ID assigned by Figma; a demo plugin identity cannot be used implicitly')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    write_json(out/'packet.json',packet)
    helpers='\n'.join((PLUGIN/'figma-bridge'/name).read_text()for name in HELPERS)
    payload_json = json.dumps(packet, ensure_ascii=False)
    warnings = embedded_asset_warnings(payload_json, packet['assets'].values())
    code='const DRAFT='+payload_json+';\n'+helpers+'\n'+(PLUGIN/'figma-bridge/direction_review.js').read_text()
    portable=out/'plugin';portable.mkdir(exist_ok=True)
    manifest_data={'name':'NIGHT · A/B/C Figma 방향 검토'if register else'Figma Flow · 디자인 방향 검토','id':plugin_id,'api':'1.0.0','editorType':['figma'],'main':'code.js','ui':'ui.html','documentAccess':'dynamic-page','enablePrivatePluginApi':True,'networkAccess':{'allowedDomains':['none']}}
    for name,value in{'code.js':code,'ui.html':ui_html(night_demo=night_demo),'manifest.json':json.dumps(manifest_data,ensure_ascii=False,indent=2)}.items():(portable/name).write_text(value)
    zip_name='NIGHT-Figma-Draft-Review.zip'if night_demo else'Figma-Direction-Review.zip'
    with zipfile.ZipFile(out/zip_name,'w',zipfile.ZIP_DEFLATED)as z:
        for path in portable.iterdir():z.write(path,path.name)
    if register:
        pair=PRIVATE/'draft-pair';pair.mkdir(parents=True,exist_ok=True,mode=0o700);token_path=pair/'capability'
        if not token_path.exists():token_path.write_text(secrets.token_hex(32));token_path.chmod(0o600)
        private=PRIVATE/'plugin';private.mkdir(parents=True,exist_ok=True,mode=0o700)
        for path in portable.iterdir():shutil.copyfile(path,private/path.name);(private/path.name).chmod(0o600)
        manifest_data['networkAccess']['devAllowedDomains']=[f'http://localhost:{port}']
        (private/'manifest.json').write_text(json.dumps(manifest_data,ensure_ascii=False,indent=2));(private/'ui.html').write_text(ui_html({'url':f'http://localhost:{port}/draft-readback','capability':token_path.read_text().strip()},night_demo=True));(private/'ui.html').chmod(0o600)
    (out/'사용방법.txt').write_text(('지정한 Figma 파일에서 로컬 검토 플러그인을 열고')+' 「검토 시안 만들기」를 한 번 누르세요.\n이 도구는 검토용 화면·주석·팔레트·클릭 이동만 만듭니다. 방향 선택·승인·본 제작은 하지 않습니다.\nDev Mode나 유료 업그레이드 없이 일반 Design 모드의 「주석 읽기」 프레임에서 설명을 읽고 링크로 해당 화면·조작으로 이동하세요.\n원화와 브라우저 참조는 래스터이고 제목·본문·행동 제어·팔레트는 편집 가능한 실제 Figma 노드입니다. 「결과 JSON 저장」으로 원본 읽기 결과를 내보내세요. 로컬 수신기를 연결한 경우에는 결과가 그 수신기에도 전달됩니다.\n')
    write_json(out/'prepared.json',{'status':'prepared-not-executed','packet_sha256':packet['packet_sha256'],'fileKey':packet['fileKey'],'production_admitted':False,'manifest':str(portable/'manifest.json'),'registered':register,'warnings':warnings})
    return {'manifest':str((PRIVATE/'plugin/manifest.json')if register else portable/'manifest.json'),'packet':str(out/'packet.json'),'zip':str(out/zip_name),'status':'prepared-not-executed','warnings':warnings}


def ui_html(pair=None,night_demo=False):
    return '''<!doctype html><meta charset="utf-8"><style>body{font:14px/1.65 system-ui;padding:18px;background:#102b36;color:#f3e9d3}button{font:inherit;padding:12px;width:100%;margin:7px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h2>디자인 방향 · Figma 검토</h2><p>검토용 실제 노드·주석·팔레트·클릭 이동을 만듭니다. 방향을 선택하거나 승인하지 않습니다.</p><button id="make">검토 시안 만들기</button><button id="save" disabled>결과 JSON 저장</button><pre id="status">준비됨 · 검토 패킷에 지정한 Design 파일에서 실행</pre><script>const PAIR=__PAIR__;let result;document.getElementById('make').onclick=()=>parent.postMessage({pluginMessage:{type:'draft-review'}},'*');document.getElementById('save').onclick=()=>{if(!result)return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));a.download='figma-direction-review-readback.json';a.click();};window.onmessage=async e=>{const m=e.data&&e.data.pluginMessage;if(!m)return;if(m.type==='status'){document.getElementById('status').textContent=result&&!PAIR?'검토 시안이 준비됐습니다. 결과 JSON 저장을 눌러 읽기 결과를 내보내세요.':m.message;document.getElementById('make').disabled=!!m.busy;}if(m.type==='readback'){result=m.data;document.getElementById('save').disabled=false;if(PAIR){try{const r=await fetch(PAIR.url,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+PAIR.capability},body:JSON.stringify(m.data)});const receipt=await r.json();if(!r.ok)throw Error(receipt.errors?.join('; ')||receipt.error||r.status);parent.postMessage({pluginMessage:{type:'receipt',passed:receipt.passed}},'*');}catch(error){document.getElementById('status').textContent='실제 화면은 생성됨 · 로컬 결과 저장 실패: '+error+String.fromCharCode(10)+'결과 JSON 저장 버튼을 사용하세요.';}}}};</script>'''.replace('__PAIR__',json.dumps(pair))


class DraftReceiver(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204);self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Authorization,Content-Type');self.send_header('Access-Control-Allow-Methods','POST,OPTIONS');self.end_headers()
    def do_POST(self):
        import hmac
        try:
            if self.path!='/draft-readback'or self.headers.get('Host')!=f'localhost:{self.server.server_port}'or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.capability):raise ValueError('Exact paired local draft endpoint required')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<25_000_000 or self.headers.get('Transfer-Encoding'):raise ValueError('Bounded draft JSON required')
            raw=json.loads(self.rfile.read(length));packet=json.loads(self.server.packet.read_text())
            if not raw.get('fileKey')or packet['fileKey']and raw.get('fileKey')!=packet['fileKey']or raw.get('instance_sha256')!=packet['instance_sha256'] or raw.get('packet_sha256')!=packet['packet_sha256']:raise ValueError('Exact prepared direction-review packet required')
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder=self.server.output/stamp;write_json(folder/'readback.json',raw)
            report=verify_native_review(packet['manifest'],folder/'readback.json');write_json(folder/'receipt.json',report)
            write_json(self.server.output/'latest.json',{'folder':str(folder),'passed':report['passed'],'packet_sha256':packet['packet_sha256']})
            status=200 if report['passed']else 409
        except(ValueError,OSError,TypeError,KeyError)as error:report={'passed':False,'errors':[str(error)]};status=409
        body=json.dumps(report,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    build=commands.add_parser('prepare');build.add_argument('--manifest',type=Path,required=True);build.add_argument('--out',type=Path,required=True);build.add_argument('--register-night',action='store_true');build.add_argument('--port',type=int,default=49185);build.add_argument('--layout',type=Path);build.add_argument('--file-key');build.add_argument('--plugin-id')
    verify=commands.add_parser('verify');verify.add_argument('--manifest',type=Path,required=True);verify.add_argument('--readback',type=Path,required=True)
    serve=commands.add_parser('serve');serve.add_argument('--packet',type=Path,required=True);serve.add_argument('--out',type=Path,required=True);serve.add_argument('--port',type=int,default=49185);serve.add_argument('--pair-dir',type=Path,required=True)
    args=parser.parse_args()
    try:
        _run(parser,args)
    except (OSError,ValueError,KeyError,TypeError)as exc:
        print(json.dumps({'passed':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)


def _run(parser,args):
    if args.command=='prepare':print(json.dumps(prepare(args.manifest,args.out,args.register_night,args.port,args.layout,args.file_key,args.plugin_id,night_demo=args.register_night),ensure_ascii=False))
    elif args.command=='verify':
        result=verify_native_review(args.manifest,args.readback);print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['passed']else 2)
    else:
        packet=json.loads(args.packet.read_text());current=make_packet(packet['manifest'],packet['layout_pin']['path'],packet['fileKey'])
        if {k:v for k,v in packet.items() if k!='prepared_at'}!={k:v for k,v in current.items() if k!='prepared_at'}:
            parser.error('Prepared draft packet no longer matches the reviewed layout, importer, target or inputs')
        capability=(args.pair_dir/'capability').read_text().strip()
        if not re.fullmatch(r'[0-9a-f]{64}', capability):parser.error('Valid local pairing is required')
        args.out.mkdir(parents=True,exist_ok=True)
        with HTTPServer(('127.0.0.1',args.port),DraftReceiver)as server:
            server.packet=args.packet.resolve();server.output=args.out.resolve();server.capability=capability;print('Figma draft-only receiver '+str(args.port),flush=True);server.serve_forever()


if __name__=='__main__':main()
