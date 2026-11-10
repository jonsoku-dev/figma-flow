"""Isolated selection fixture. Never reads or writes real conversation records."""
from contextlib import contextmanager
from html import escape
from pathlib import Path
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import annotation_contract
import design_directions as directions
import design_foundations


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return path


def annotated_graph(graph):
    graph = json.loads(json.dumps(graph))
    nodes = graph['nodes']
    screens = [node for node in nodes if node.get('type') == 'screen']
    if not screens:
        raise ValueError('The test graph needs a screen')
    actions = [node for node in nodes if node.get('type') == 'action']
    state_ids = [node['id'] for node in nodes if node.get('type') == 'state']
    if actions and not state_ids:
        nodes.append({'id':'ST-FIXTURE-READY','type':'state','title':'Fixture ready','status':'observed'})
        state_ids = [nodes[-1]['id']]
    for node in actions:
        node.setdefault('source_screen', screens[0]['id'])
        node.setdefault('annotation', {
            'control_id':node['id']+'-control', 'purpose':'Read the selected note.', 'behavior':'Open the selected detail view.',
            'result':'Show the selected note detail.', 'failure':'Keep the existing note when reading fails.',
            'functional_states':state_ids})
    for screen in screens:
        starts = [a['id'] for a in actions if a['source_screen'] == screen['id']]
        screen.setdefault('annotation', {
            'purpose':'Present the fixture screen to its reader.', 'journey':'Read its content and inspect the available action.',
            **({'first_action':starts[0]} if starts else {})})
    for node in nodes:
        node.setdefault('status', 'planned')
    edges = graph.setdefault('edges', [])
    for node in actions:
        for edge in [{'from': node['source_screen'], 'to': node['id'], 'type': 'enables'}] + [
                {'from': node['id'], 'to': target, 'type': 'shows'} for target in node.get('target_ids', [])]:
            if not any(e['from'] == edge['from'] and e['to'] == edge['to'] for e in edges):
                edges.append(edge)
    foundation = design_foundations.derive_foundations(graph)
    if not foundation['palette']['samples']:
        foundation['palette']['samples'] = [{
            'label':'Reading panel','component':'card','variant':'default','action':'Present a note',
            'state':'Ready to read','useCases':['Reader note detail']}]
    graph['design_foundations'] = foundation
    return graph


@contextmanager
def selected_direction(base, graph=None, native_review=False):
    """Yield a verified test receipt with the managed-user resolver pinned to a temporary directory."""
    from PIL import Image, ImageDraw
    base = Path(base).resolve()
    root = base / 'direction-fixture'
    root.mkdir(parents=True)
    managed = root / 'managed-records'
    managed.mkdir()
    if isinstance(graph, (str, Path)):
        graph_path = Path(graph).resolve()
        source_graph = json.loads(graph_path.read_text())
    else:
        graph_path = root / 'product-graph.json'
        source_graph = graph if graph is not None else {
            'version':1, 'nodes':[{'id':'R','type':'requirement','title':'Read a note','status':'observed'},
                                  {'id':'S','type':'screen','title':'Reader','status':'planned'}],
            'edges':[{'from':'R','to':'S','type':'appears on'}]}
    graph_data = annotated_graph(source_graph)
    write(graph_path, graph_data)
    notes = annotation_contract.derive_notes(graph_data)
    native_review = native_review or graph_data.get('requires_figma', False) or any(n.get('type') == 'figma' for n in graph_data['nodes'])
    brief = root / 'brief.md'; brief.write_text(('Figma native draft review. ' if native_review else 'Local HTML only. ') + 'Compare two possible note-reading layouts before authoring.')
    research = root / 'research.md'; research.write_text('Fixture reference review: compare a reading poster with an indexed document.')
    content = write(root/'shared.json', {'required_text':['Fixture title','Open the note']})
    candidates=[]
    for i, identity in enumerate(('A','B')):
        folder = root/identity
        folder.mkdir()
        # Distinct synthetic layouts for testing only; these are not generated or user-approved design assets.
        tags=('main','button') if i==0 else ('article','section')
        fragments = [f'<{tags[n % len(tags)]} id="{escape(note["target_id"])}">Fixture title · Open the note</{tags[n % len(tags)]}>' for n,note in enumerate(notes)]
        source=folder/'index.html'
        source.write_text((''.join(fragments) if i==0 else '<header>Fixture title</header><aside>Open the note</aside>'+''.join(fragments))+
                          ('<script>button.onclick=show;</script>' if i==0 else '<script>for(const item of cards){item.onclick=()=>next(item)}</script>'))
        review=folder/'inspect.html'
        review.write_text('<p>planned · not native</p>'+''.join(
            '<section><a href="index.html#'+escape(n['target_id'])+'">annotated element</a>'+
            ''.join('<p>'+escape(n[key])+'</p>' for key in annotation_contract.TEXT_FIELDS if n.get(key))+'</section>' for n in notes))
        with review.open('a') as stream:
            for row in graph_data['design_foundations']['roles'] + graph_data['design_foundations']['palette']['samples']:
                stream.write('<p>'+escape(' '.join(str(value) for value in row.values()))+'</p>')
        previews=[]
        for viewport,w,h in [('mobile',390,844),('desktop',1440,900)]:
            image=Image.new('RGB',(w,h),'white')
            pen=ImageDraw.Draw(image)
            if i:
                for top in range(h//8,h,h//4):
                    pen.rectangle((w//12,top,w*3//4,top+h//10),fill='#272d30')
            else:
                pen.rectangle((0,h//3,w//2,h),fill='#272d30')
                pen.rectangle((w//2,0,w,h//3),fill='#272d30')
            png=folder/(viewport+'.png');image.save(png)
            previews.append({'path':str(png),'viewport':viewport,'width':w,'height':h})
        candidates.append({'id':identity,'title':'Direction '+identity,'source':str(source),'review':str(review),'graph':str(graph_path),'previews':previews,
                           'composition':['An asymmetric reading poster.','A sequence of horizontal note entries.'][i],
                           'typography':['One large title above the note.','Small type organizes an index.'][i],
                           'interaction':['Open a single note from the poster.','Pick a row to open a detail.'][i]})
    spec={'content':{'path':str(content)},'candidates':candidates}
    native_review = native_review or graph_data.get('requires_figma', False) or any(n.get('type') == 'figma' for n in graph_data['nodes'])
    draft = directions.create_draft(base,brief,research,spec,root/'draft',review_destination='figma' if native_review else 'local')
    manifest=Path(draft['manifest']);data=json.loads(manifest.read_text())
    review_data={'role':'agent','draft_content_sha256':directions.digest(data['candidates']),'candidates':[
        {k:c[k] for k in ('id','composition','typography','interaction')}|
        {'candidate_sha256':c['sha256'],'truth_and_notes':'Visible source links expose the planned note and palette.'}
        for c in data['candidates']]}
    review = directions.review_draft(manifest,write(root/'agent-review.json',review_data))
    from contextlib import nullcontext
    def modeled_native(manifest_path, data, readback_path=None):
        record = readback_path or data['native_review']['readback']['path']
        raw = json.loads(Path(record).read_text())
        if raw.get('packet_sha256') != directions.review_packet_sha256(data) or raw.get('candidates') != {c['id']:c['sha256'] for c in data['candidates']}:
            raise ValueError('Modeled native fixture packet drift')
        return {'passed':True,'errors':[],'file_key':'synthetic-fixture','page_id':'synthetic-page',
                'screens':[{'id':c['id']} for c in data['candidates']], 'annotation_checks':[], 'foundation_checks':[],
                'prototype_checks':[], 'return_checks':[], 'evidence':'trusted-test-adapter-model-not-live-Figma'}
    native_adapter = patch.object(directions,'_native_review',side_effect=modeled_native) if native_review else nullcontext()
    with native_adapter:
        if native_review:
            pending=json.loads(manifest.read_text())
            readback=write(root/'native-review-fixture.json',{'packet_sha256':directions.review_packet_sha256(pending),
                'candidates':{c['id']:c['sha256'] for c in pending['candidates']}})
            review=directions.verify_native_review(manifest,readback)
        user_event=managed/'fixture.jsonl'
        records=[{'type':'response_item','payload':{'type':'message','role':'assistant','content':[{'type':'output_text','text':
            f"Review {data['review_id']} {review['draft_sha256']}. Compare A and B."}]}},
            {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'A'}]}}]
        user_event.write_text(''.join(json.dumps(row)+'\n' for row in records))
        selection_path=manifest.parent/'selection.json'
        with patch.object(directions, 'user_record_root', return_value=managed):
            directions.record_selection(manifest,user_event,selection_path)
            yield SimpleNamespace(selection_path=selection_path,product_graph=graph_path,manifest=manifest,user_event=user_event)
