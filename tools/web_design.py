"""Prepare a bounded, pinned Web-to-Figma native design import."""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / 'skills/figma-flow/scripts'
sys.path.insert(0, str(SCRIPT_ROOT))
from graph import validate_graph as validate_canonical_graph

SCHEMA = 'figma-flow-web-design-v1'
KINDS = {'frame', 'text', 'component', 'image', 'vector', 'annotation'}
COLORS = re.compile(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z')

def _box(box):
    if not isinstance(box, dict) or set(box) != {'x','y','width','height'} or any(type(v) not in (int,float) or not math.isfinite(v) for v in box.values()) or abs(box['x'])>100_000 or abs(box['y'])>100_000 or box['width'] < 0 or box['height'] < 0 or box['width']>32768 or box['height']>32768:
        raise ValueError('Finite bounded viewport-relative element bounds required')

def validate_svg(svg):
    if not isinstance(svg, str) or len(svg) > 200_000 or re.search(r'<!|<\?|url\s*\(|javascript:', svg, re.I):
        raise ValueError('Bounded standalone SVG required')
    try: root = ET.fromstring(svg)
    except ET.ParseError as error: raise ValueError('Malformed SVG vector') from error
    allowed = {'svg': {'viewBox','width','height','xmlns'}, 'g': {'fill','stroke','stroke-width','opacity','transform'},
               'path': {'d','fill','stroke','stroke-width','fill-rule','opacity','transform'},
               'rect': {'x','y','width','height','rx','ry','fill','stroke','stroke-width','opacity'},
               'circle': {'cx','cy','r','fill','stroke','stroke-width','opacity'},
               'ellipse': {'cx','cy','rx','ry','fill','stroke','stroke-width','opacity'},
               'line': {'x1','y1','x2','y2','fill','stroke','stroke-width','opacity'},
               'polyline': {'points','fill','stroke','stroke-width','opacity'},
               'polygon': {'points','fill','stroke','stroke-width','opacity'}}
    if root.tag.split('}')[-1] != 'svg': raise ValueError('SVG root required')
    count=0
    for node in root.iter():
        tag=node.tag.split('}')[-1];count+=1
        if tag not in allowed or count>2000 or node.text and node.text.strip(): raise ValueError('Unsupported SVG element or text')
        for key,value in node.attrib.items():
            name=key.split('}')[-1]
            if name not in allowed[tag] or name.lower().startswith('on') or re.search(r'url\s*\(|javascript:|data:|https?:|file:', value, re.I): raise ValueError('Unsupported or external SVG attribute')
            if name in {'fill','stroke'} and value not in {'none','currentColor'} and not COLORS.fullmatch(value): raise ValueError('SVG paint must use literal hex colors')
            if tag == 'line' and name == 'fill' and value != 'none': raise ValueError('SVG line fill must be none')
    return svg

def image_signature(data, mime):
    return {'image/png': data.startswith(b'\x89PNG\r\n\x1a\n'), 'image/jpeg': data.startswith(b'\xff\xd8\xff'), 'image/webp': len(data)>=12 and data[:4]==b'RIFF' and data[8:12]==b'WEBP'}.get(mime, False)

def embed_local_assets(web, max_total=8_000_000):
    graph_dir=Path(web['source_graph_path']).resolve().parent
    pins=[]; total=0; assets={}
    for screen in web['screens']:
        for element in screen['elements']:
            if element['kind']!='image': continue
            asset=element['asset']; relative=Path(asset['path']); path=graph_dir
            for part in relative.parts:
                path=path/part
                if path.is_symlink(): raise ValueError('Image asset path crosses a symbolic link')
            if not path.is_file() or not path.resolve().is_relative_to(graph_dir): raise ValueError('Image asset must stay under the graph directory')
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=asset['sha256'] or not image_signature(data,asset['mimeType']): raise ValueError('Image asset hash or file signature is invalid')
            if asset['sha256'] not in assets:
                total+=len(data)
                if len(data)>8_000_000 or total>max_total: raise ValueError('Unique embedded assets exceed the 8 MB total limit')
                assets[asset['sha256']]=base64.b64encode(data).decode('ascii')
            pins.append({'path':str(path.resolve()),'sha256':asset['sha256']})
    web['assets']=assets
    return pins

def validate_graph(graph, require_embedded=False):
    errors, _ = validate_canonical_graph(graph)
    if errors:
        raise ValueError('Invalid canonical graph: ' + '; '.join(errors[:3]))
    if (not isinstance(graph, dict) or set(graph) != {'version','id','title','nodes','edges'}
            or graph.get('version') != 1 or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', str(graph.get('id','')))
            or not isinstance(graph.get('title'),str) or not graph['title'].strip() or len(graph['title'])>160):
        raise ValueError('Versioned web design graph with stable id required')
    nodes=graph['nodes']; edges=graph['edges']
    if not isinstance(nodes,list) or not isinstance(edges,list) or not 1 <= len(nodes) <= 2000 or len(edges)>4000: raise ValueError('Bounded canonical graph nodes and edges required')
    node_ids=set()
    for node in nodes:
        if (not isinstance(node,dict) or not isinstance(node.get('id'),str) or not node['id']
                or len(node['id'])>160 or not isinstance(node.get('type'),str) or not node['type']
                or not isinstance(node.get('title'),str) or not node['title'].strip()): raise ValueError('Canonical graph nodes need stable ID, type and title')
        if node['id'] in node_ids: raise ValueError('Duplicate canonical graph node ID')
        node_ids.add(node['id'])
    for edge in edges:
        if (not isinstance(edge,dict) or set(edge)!={'from','to','type'}
                or edge.get('from') not in node_ids or edge.get('to') not in node_ids
                or not isinstance(edge.get('type'),str) or not edge['type'].strip() or len(edge['type'])>120):
            raise ValueError('Canonical graph edges must connect declared node IDs')
    screens=[node for node in nodes if node.get('type')=='screen' and node.get('id','').startswith('WEB-')]
    if not 1 <= len(screens) <= 16: raise ValueError('One to sixteen WEB screen nodes required')
    ids=set()
    for screen in screens:
        if set(screen)-{'id','type','title','detail','status','layout','elements'}: raise ValueError('Unsupported WEB screen fields')
        if screen['id'] in ids: raise ValueError('Duplicate web screen id')
        ids.add(screen['id']); layout=screen.get('layout'); elements=screen.get('elements')
        if not isinstance(layout,dict) or set(layout)-{'width','height','background'} or any(type(layout.get(k)) not in (int,float) or not math.isfinite(layout[k]) or layout[k]<=0 or layout[k]>32768 for k in ('width','height')): raise ValueError('Finite bounded actual viewport dimensions required')
        if layout.get('background') is not None and not COLORS.fullmatch(layout['background']): raise ValueError('Hex screen background required')
        if not isinstance(elements,list) or len(elements)>1500: raise ValueError('Bounded flat screen element list required')
        element_ids=set()
        for e in elements:
            if not isinstance(e,dict) or e.get('kind') not in KINDS or not isinstance(e.get('id'),str) or not e['id'] or len(e['id'])>120: raise ValueError('Stable typed element id required')
            if e['id'] in element_ids: raise ValueError('Duplicate screen element ID')
            element_ids.add(e['id'])
            if 'path' in e and (not isinstance(e['path'],list) or len(e['path'])>64 or any(not isinstance(part,str) or not part or len(part)>120 for part in e['path'])): raise ValueError('Bounded ancestor path required')
            if e.get('kind') in ('text','component') and e.get('text') is not None:
                text=e.get('text')
                if not isinstance(text,dict) or set(text)-{'characters','fontFamily','fontSize','fontWeight','lineHeight','textAlign','textAlignHorizontal','color'}: raise ValueError('Unsupported observed text fields')
                if e.get('kind')=='text' and not isinstance(text.get('characters'),str): raise ValueError('Text characters required')
                for key in ('fontSize','fontWeight','lineHeight'):
                    if key in text and (type(text[key]) not in (int,float) and not (key=='fontWeight' and isinstance(text[key],str) and text[key].isdigit()) or not math.isfinite(float(text[key]))): raise ValueError(f'Finite text {key} required')
                if 'color' in text and text['color'] is not None and not COLORS.fullmatch(text['color']): raise ValueError('Text color must be a literal hex color')
            _box(e.get('box'))
            label_box=e.get('props',{}).get('labelBox') if isinstance(e.get('props',{}),dict) else None
            if label_box is not None:
                _box(label_box)
                if e.get('kind')!='component' or label_box['x']<0 or label_box['y']<0 or label_box['x']+label_box['width']>e['box']['width']+1 or label_box['y']+label_box['height']>e['box']['height']+1: raise ValueError('Component labelBox must fit its observed component bounds')
            if e['kind']=='text' and (not isinstance(e.get('text'),dict) or not isinstance(e['text'].get('characters'),str) or len(e['text']['characters'])>10000): raise ValueError('Bounded text characters required')
            if e['kind']=='image' and e.get('objectFit','cover') not in ('cover','contain'): raise ValueError('Image objectFit must be cover or contain')
            if e['kind']=='vector':
                validate_svg(e.get('svg'))
            if e['kind']=='image':
                asset=e.get('asset')
                if not isinstance(asset,dict) or set(asset)!={'path','sha256','mimeType'} or asset['mimeType'] not in ('image/png','image/jpeg','image/webp') or not re.fullmatch(r'[a-f0-9]{64}',str(asset['sha256'])) or not isinstance(asset['path'],str) or any(char in asset['path'] for char in ':\\\0\n\r') or Path(asset['path']).is_absolute() or '..' in Path(asset['path']).parts or not Path(asset['path']).parts: raise ValueError('Image needs a hash-pinned local raster asset')
                if require_embedded: raise ValueError('Raster bytes are loaded from pinned local paths during native preparation')
            paint=e.get('paint',{})
            if not isinstance(paint,dict) or set(paint)-{'background','color','borderColor','borderWidth','borderRadius','opacity','radialGradient'}: raise ValueError('Unsupported paint fields')
            for key in ('background','color','borderColor'):
                if paint.get(key) is not None and not COLORS.fullmatch(paint[key]): raise ValueError('Paint must use literal hex colors')
            bounds={'borderWidth':128,'borderRadius':1_000_000_000,'opacity':1}
            for key,maximum in bounds.items():
                if key in paint and (type(paint[key]) not in (int,float) or not math.isfinite(paint[key]) or paint[key]<0 or paint[key]>maximum): raise ValueError(f'Finite bounded {key} required')
            gradient=paint.get('radialGradient')
            if gradient is not None:
                if (not isinstance(gradient,dict) or set(gradient)!={'centerX','centerY','stops'}
                        or any(type(gradient[key]) not in (int,float) or not math.isfinite(gradient[key]) or not 0<=gradient[key]<=1 for key in ('centerX','centerY'))
                        or not isinstance(gradient['stops'],list) or not 2<=len(gradient['stops'])<=16):
                    raise ValueError('Radial gradient requires normalized center and two to sixteen stops')
                previous=-1
                for stop in gradient['stops']:
                    if (not isinstance(stop,dict) or set(stop)!={'position','color'}
                            or type(stop['position']) not in (int,float) or not math.isfinite(stop['position'])
                            or not 0<=stop['position']<=1 or stop['position']<previous
                            or not isinstance(stop['color'],str) or not COLORS.fullmatch(stop['color'])):
                        raise ValueError('Radial gradient stops must use sorted normalized positions and literal colors')
                    previous=stop['position']
        frame_ids={element['id'] for element in elements if element['kind']=='frame'}
        for element in elements:
            path=element.get('path',[])
            if any(frame_id not in frame_ids for frame_id in path) or element['id'] in path:
                raise ValueError('Element path must name existing ancestor frame IDs')
    return screens

def build_plan(graph_path, file_key, page_id, out, screen_ids=None, preview_width=None):
    source=Path(graph_path).expanduser().absolute()
    if source.is_symlink() or not source.is_file(): raise ValueError('Canonical graph must be a regular local file')
    raw=source.read_bytes()
    if len(raw)>12_000_000: raise ValueError('Bounded source graph required')
    graph=json.loads(raw); screens=validate_graph(graph)
    if screen_ids:
        unknown=set(screen_ids)-{screen['id'] for screen in screens}
        if unknown: raise ValueError('Requested WEB screen ID is not in source graph: '+', '.join(sorted(unknown)))
        screens=[screen for screen in screens if screen['id'] in set(screen_ids)]
    if preview_width is not None and (type(preview_width) is not int or not 360<=preview_width<=480): raise ValueError('Preview width must be between 360 and 480 pixels')
    screens=json.loads(json.dumps(screens))
    web={'schema':SCHEMA,'graph_id':graph['id'],'graph_sha256':hashlib.sha256(raw).hexdigest(),'source_graph_path':str(source.resolve()),'screens':screens}
    if preview_width is not None: web['preview_width']=preview_width
    plan={'schema':'figma-flow-native-edit-plan-v1','file_key':file_key,'page_id':page_id,'web_design':web}
    output=Path(out).expanduser().absolute()
    if output.exists() or output.is_symlink(): raise FileExistsError(f'Refusing to overwrite web design plan: {output}')
    output.write_text(json.dumps(plan,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8'); output.chmod(0o600)
    return {'plan':str(output),'screen_count':len(screens),'graph_sha256':plan['web_design']['graph_sha256'],'status':'prepared-not-executed'}
