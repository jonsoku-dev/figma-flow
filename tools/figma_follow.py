#!/usr/bin/env python3
"""Follow changes on one Design page from Codex, optionally reading a paired task."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import UUID, uuid4

import figma_control as control
import figma_workspace as workspace
from relay_view import INSPECT_FIELDS

ROOT = Path(__file__).resolve().parent
SCHEMA = 'figma-flow-live-follow-v1'


def save(path, data):
    workspace.atomic(path, workspace.encode(data))


def digest(value):
    return hashlib.sha256(workspace.encode(value)).hexdigest()


def thread_destination(enabled):
    if not enabled:
        return None
    value = os.environ.get('CODEX_THREAD_ID', '')
    try:
        thread = str(UUID(value))
    except ValueError:
        raise ValueError('Start current-chat notifications inside the receiving Codex thread.') from None
    if not shutil.which('codex'):
        raise ValueError('Current-chat notifications require the local codex queue command.')
    return thread


@contextmanager
def exclusive(directory):
    import fcntl
    fd = os.open(directory / 'follow.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This page already has a follower for this subscription.') from None
        yield
    finally:
        os.close(fd)


def settings(args):
    ws = workspace.private_dir(args.workspace)
    control.scope(args.file_key, args.page_id, '0'*64)
    if bool(args.read_task) != bool(args.revision):
        raise ValueError('Supply the signed read task and its revision together.')
    files = (args.graph, args.pairing, args.web_module)
    if (any(files) and not all(files)) or (any(files) and not args.read_task):
        raise ValueError('Graph preview requires --graph, --pairing, --web-module and a signed read task.')
    if args.component_edits and not all(files):
        raise ValueError('Component edits require a paired graph preview.')
    if bool(args.inspect_task) != bool(args.inspect_revision):
        raise ValueError('Specify both the discover task and its exact revision.')
    if args.include_text and not args.inspect_task:
        raise ValueError('Text detail requires a scoped inspect task.')
    if args.apply_clean and not all(files):
        raise ValueError('Clean graph publishing requires all pairing inputs.')
    catalog = workspace.current(ws, repair=False)
    tasks = {row['key']:row for row in catalog['tasks']}
    for key, revision, kinds in ((args.inspect_task,args.inspect_revision,{'discover'}),
                                (args.read_task,args.revision,{k for k, v in control.OPERATIONS.items() if 'read' in v})):
        if not key:
            continue
        row = tasks.get(key)
        if (not row or row['revision'] != revision or row.get('fileKey') != args.file_key
                or row.get('pageId') != args.page_id or row['kind'] not in kinds):
            raise ValueError('Task must match the requested file, page, operation and revision.')
    if args.read_task:
        row = tasks[args.read_task]
        if args.pairing:
            pair = json.loads(args.pairing.read_bytes())
            plan = pair['plan']
            if (row['kind'] not in ('sync','discover') or plan.get('file_key') != args.file_key or
                    plan.get('page_id') != args.page_id):
                raise ValueError('The read task and graph pairing must describe the watched scope.')
    return ws


def read_operation(args, key, revision, operation, options=()):
    cmd = [sys.executable, '-B', str(ROOT / 'figma_control.py'), 'run', '--workspace', str(args.workspace),
           '--key', key, '--expected-revision', revision, '--operation', operation,
           '--file-key', args.file_key, '--page-id', args.page_id, '--timeout', str(args.read_timeout), *options]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.read_timeout + 10)
    if proc.returncode:
        raise ValueError('signed-read-failed')
    receipt = json.loads(proc.stdout)
    if receipt.get('state') != 'ok' or not receipt.get('readback'):
        raise ValueError('Missing successful native readback.')
    return {'state':'read','operation_id':receipt['id'],'readback':receipt['readback'],
            'native_session':receipt.get('session_id')}


def inspect_events(args, events):
    aliases = {'size': ('width','height'), 'relativeTransform': ('x','y','rotation'),
               'text': ('characters',), 'fontFamily': ('fontName',), 'fontStyle': ('fontName',)}
    ids = list(dict.fromkeys(e['node_id'] for e in events if e.get('node_id')))
    if not ids:
        return {'state':'read-required','reason':'no-node-ids'}
    fields = {'name'}
    changed = {prop for event in events for prop in [*event.get('properties', []), *event.get('unknown_properties', [])]}
    for prop in changed:
        fields.update(f for f in aliases.get(prop,(prop,)) if f in INSPECT_FIELDS)
    if any(e.get('type') == 'CREATE' for e in events):
        fields.update(('width','height','x','y'))
    if not args.include_text:
        fields.discard('characters')
    options = [v for node_id in ids[:20] for v in ('--inspect-node-id',node_id)]
    options.extend(v for field in sorted(fields) for v in ('--field',field))
    if 'characters' in fields:
        options.append('--include-text')
    result = read_operation(args,args.inspect_task,args.inspect_revision,'selection-info',options)
    result.update(node_count=len(ids), observed_limit=20, omitted_node_count=max(0,len(ids)-20),
                  requested_fields=sorted(fields), unsupported_properties=sorted(changed-set(INSPECT_FIELDS)-set(aliases)),
                  text_omitted='characters' not in fields and bool({'text','characters'} & changed))
    return result


def touched_roots(pairing, report, events):
    """Which proposed roots have a native property-change witness in this batch?"""
    properties = {}
    for event in events:
        if event.get('type') == 'PROPERTY_CHANGE':
            properties.setdefault(event['node_id'], set()).update(event.get('properties', []))
    declarations = {part['id']:part['properties'] for part in pairing['plan']['components']}
    names = {'backgroundColor': {'fills'}, 'color': {'fills'}, 'textColor': {'fills'},
             'borderColor': {'strokes'}, 'borderWidth': {'strokeWeight'},
             'gap': {'itemSpacing'}, 'width': {'width','size'}, 'height': {'height','size'}}
    covered = set()
    for component in report['affected_components']:
        for field in component['fields']:
            consumers = {node for owner in component['main_ids'] + component['instance_ids']
                         for node in pairing['consumer_ids'].get(f"{component['component']}:{owner}:{field}", [])}
            changed = set().union(*(properties.get(node, set()) for node in consumers))
            if changed & (names.get(field, set()) | {field}):
                key = declarations[component['component']][field]
                covered.add(pairing['primitive_roots'][key])
    return covered


def fresh_read(args, directory, allow_publish, events=(), live_scope=None):
    record = read_operation(args,args.read_task,args.revision,'read')
    if not args.pairing:
        return record
    if allow_publish and live_scope is not None and args.apply_clean:
        runtime = workspace.current(Path(args.workspace),repair=False).get('runtime',{})
        allow_publish = (allow_publish and record.get('native_session') == live_scope.get('session_id')
                         and runtime.get('generation') == live_scope.get('generation'))
    import graph_sync
    pairing = json.loads(args.pairing.read_bytes())
    data = json.loads(Path(record['readback']).read_bytes())
    mode = 'component' if args.component_edits else None
    try:
        report = graph_sync.import_values(args.graph,pairing,data,args.web_module,directory/'graph-preview',
                                          apply=False,node_edit_scope=mode)
        record.update(state='preview', proposed_updates=len(report['updates']),
                      unsupported_changes=len(report['unsupported_changes']), applied=False)
        if args.apply_clean and report['updates']:
            # A stale pair may still produce a useful preview. Publishing requires its unmodified pair of local files.
            clean = (allow_publish and set(report['updates']) <= touched_roots(pairing, report, events)
                     and not report['unsupported_changes'] and not report['repair_bindings']
                     and report['graph_sha256_before']==pairing['graph_sha256']
                     and hashlib.sha256(args.web_module.read_bytes()).hexdigest()==pairing.get('web_module_sha256'))
            if not clean:
                return {**record,'state':'review-required','reason':'missing change witness, gap, local drift, or unsupported changes'}
            applied = graph_sync.import_values(args.graph,pairing,data,args.web_module,directory/'graph-apply',
                                               apply=True,node_edit_scope=mode, expected_graph_sha256=report['graph_sha256_before'],
                                               expected_web_sha256=pairing['web_module_sha256'])
            record.update(state='applied',applied=applied['applied'],pairing_advanced=False)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        record.update(state='review-required',reason=str(exc)[:500],applied=False)
    return record


def notify(thread, packet_path, count, gap, resume, properties=()):
    # No Figma-authored labels, text or excerpts are inserted into a model prompt.
    notice = (f'[Figma Flow] 감시한 Design 페이지에서 변경 {count}건을 감지했습니다.' if count else '[Figma Flow] 감시하던 페이지 연결이 바뀌었습니다.')
    fields = sorted(set(properties) & INSPECT_FIELDS.keys())
    if fields:
        notice += ' 변경 속성: ' + ', '.join(fields) + '.'
    if gap:
        notice += ' 수신 공백이 있어 현재 상태 재확인이 필요합니다.'
    notice += f' 로컬 변경 기록: {packet_path}'
    try:
        command = ['codex','queue','--thread',thread,'--message='+notice]
        if resume:
            command.append('--resume')
        proc = subprocess.run(command,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return {'state':'uncertain','consumed':False}
    if proc.returncode:
        return {'state':'uncertain','consumed':False}
    detail = proc.stderr.lower()
    if not resume:
        resume_state = 'not-requested'
    elif 'already has an active writer' in detail:
        resume_state = 'already-active'
    elif 'could not resume' in detail or 'failed to resume' in detail:
        resume_state = 'not-resumed'
    else:
        resume_state = 'request-accepted'
    return {'state':'queued','resume_requested':resume,'resume_state':resume_state,
            'cli_warning':bool(proc.stderr.strip()),'consumed':False}


def update_latest(directory, record, path):
    """Last locally read fields per node. The event journal remains the change history."""
    output = directory / 'latest.json'
    view = workspace.read(output, private=True, limit=8_000_000) if output.exists() else {'nodes':{}}
    generation_changed = view.get('scope') and view['scope'].get('generation') != record['scope'].get('generation')
    if generation_changed or record.get('gap') or (view.get('cursor') and view['cursor']['epoch'] != record['cursor']['epoch']):
        view['nodes'] = {}
    details = record.get('details') or {}
    observed = {}
    if details.get('state') == 'read':
        data = json.loads(Path(details['readback']).read_bytes())
        if (data.get('fileKey'),data.get('pageId')) != (record['scope']['file_key'],record['scope']['page_id']):
            raise ValueError('Readback target changed before the local view was saved.')
        observed = {n['id']:n for n in data.get('details',{}).get('nodes',[])}
    for event in record['events']:
        node_id = event['node_id']
        snapshot = observed.get(node_id, {'id':node_id, 'status':'read-required'})
        if event['type'] == 'DELETE' and node_id not in observed:
            snapshot = {'id':node_id,'status':'deletion-reported'}
        view['nodes'][node_id] = {**snapshot,'cursor':record['cursor'], 'event_type':event['type'],
                                  'observed_at':record['received_at'], 'receipt':path.parent.name}
    if len(view['nodes']) > 256:
        keep = sorted(view['nodes'],key=lambda key:view['nodes'][key]['observed_at'])[-256:]
        view['nodes'] = {key:view['nodes'][key] for key in keep}
    view.update(schema='figma-flow-latest-observations-v1', scope=record['scope'], cursor=record['cursor'],
                last_event=str(path), gap=record.get('gap'), notification=record['notification'])
    save(output,view)


def handle_batch(args, directory, thread, batch):
    events = batch.get('events', [])
    # Known plugin-origin traffic remains visible in the journal. It cannot drive a feedback loop.
    relevant = [event for event in events if event.get('origin') != 'figma-flow-plugin']
    if not relevant and not batch.get('gap'):
        return None
    identifier = digest((batch['scope'], batch['cursor']))
    event_dir = workspace.private_dir(directory / identifier, create=True)
    path = event_dir / 'event.json'
    if path.exists():
        # A crash during queueing is ambiguous. Never repeat a model turn automatically.
        record = workspace.read(path, private=True)
    else:
        record = {'schema':SCHEMA,'scope':batch['scope'],'cursor':batch['cursor'], 'events':relevant,
                  'gap':batch.get('gap'), 'received_at':time.time(), 'notification':{'state':'pending' if thread else 'disabled'}}
        save(path, record)
    if thread and record['notification']['state'] == 'pending':
        now = time.time()
        window_path = directory/'notification-window.json'
        window = workspace.read(window_path,private=True) if window_path.exists() else {}
        same_burst = (not batch.get('gap') and now-window.get('last_edit',0) < 2
                      and now-window.get('last_notice',0) < 30)
        if same_burst:
            record['notification'] = {'state':'coalesced','notice':window['notice'],'consumed':False}
        else:
            record['notification'] = {'state':'uncertain','consumed':False}
            save(path, record)
            properties = [field for row in relevant for field in row.get('properties', [])]
            record['notification'] = notify(thread,path,len(relevant),bool(batch.get('gap')),args.resume_chat,properties)
            window.update(notice=identifier,last_notice=now)
        save(path, record)
        save(window_path,{**window,'last_edit':now})
    print(json.dumps({'state':'changed','receipt':str(path),'count':len(relevant),'gap':batch.get('gap'),
                      'notification':record['notification']}, ensure_ascii=False), flush=True)
    if args.inspect_task and 'details' not in record:
        try:
            record['details'] = inspect_events(args,relevant)
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            record['details'] = {'state':'read-required','reason':str(exc)[:200]}
        save(path,record)
    if args.read_task and 'read' not in record:
        try:
            consistent = (not batch.get('gap') and not batch.get('offline') and
                          batch.get('status','available') == 'available' and
                          all(event.get('scope') == batch['scope'] for event in relevant))
            record['read'] = fresh_read(args,event_dir,consistent,relevant,batch['scope'])
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            record['read'] = {'state':'read-required','reason':type(exc).__name__}
        save(path, record)
        print(json.dumps(record['read'],ensure_ascii=False),flush=True)
    update_latest(directory,record,path)
    return path


def follow(args):
    ws = settings(args)
    args.workspace = ws
    thread = thread_destination(args.notify_current_chat)
    source = {'file_key':args.file_key,'page_id':args.page_id,'thread':thread,
              'read_task':args.read_task,'revision':args.revision, 'component_edits':args.component_edits,
              'inspect_task':args.inspect_task,'inspect_revision':args.inspect_revision,'resume_chat':args.resume_chat,
              'include_text':args.include_text,'apply_clean':args.apply_clean,
              'graph':str(args.graph.resolve()) if args.graph else None,
              'web_module':str(args.web_module.resolve()) if args.web_module else None,
              'pairing':str(args.pairing.resolve()) if args.pairing else None}
    directory = workspace.private_dir(args.state_dir or ws / '.control' / 'followers' / digest(source), create=True)
    checkpoint = directory / 'cursor.json'
    with exclusive(directory):
        instance = str(uuid4())
        save(directory/'running.json',{'instance':instance,'scope':{'file_key':args.file_key,'page_id':args.page_id},
             'pid':os.getpid(),'started_at':time.time(),'notify_current_chat':bool(thread),'resume_requested':args.resume_chat})
        stop = directory/'stop.json'
        cursor = None
        if checkpoint.exists():
            existing = workspace.read(checkpoint, private=True)
            if existing.get('source') != source:
                raise ValueError('Checkpoint belongs to a different subscription.')
            cursor = existing['cursor']
        pending = directory / 'pending.json'
        if pending.exists():
            pending_batch = workspace.read(pending, private=True)
            path = handle_batch(args,directory,thread,pending_batch)
            cursor = pending_batch['cursor']
            save(checkpoint, {'source':source,'cursor':cursor})
            pending.unlink()
            if args.once and path:
                return
        announced = False
        while True:
            if stop.exists() and workspace.read(stop,private=True).get('instance') == instance:
                print(json.dumps({'state':'stopped','directory':str(directory)}),flush=True)
                return
            try:
                batch = control.change_request(ws, args.file_key, args.page_id, cursor=cursor, timeout=args.wait if cursor else 0)
            except (OSError, control.ReadinessError) as exc:
                if args.once:
                    raise
                if announced:
                    print(json.dumps({'state':'disconnected','reason':type(exc).__name__}),flush=True)
                    announced = False
                time.sleep(1)
                continue
            if stop.exists() and workspace.read(stop,private=True).get('instance') == instance:
                continue
            new_cursor = batch.get('cursor')
            if not new_cursor:
                if cursor is not None and batch.get('gap'):
                    lost = {**batch, 'scope':{'file_key':args.file_key,'page_id':args.page_id},'cursor':cursor}
                    handle_batch(args,directory,thread,lost)
                    cursor = None
                    save(checkpoint,{'source':source,'cursor':None})
                    if args.once:
                        return
                if args.once and batch.get('offline'):
                    raise ValueError('Open the registered Figma plugin on the requested page.')
                time.sleep(1)
                continue
            starting = cursor is None
            if starting:
                save(checkpoint, {'source':source,'cursor':new_cursor})
                cursor = new_cursor
            state = 'offline' if batch.get('offline') else ('watching' if batch.get('status') == 'available' else 'listener-unavailable')
            if state != announced:
                print(json.dumps({'state':state,'cursor':cursor,'directory':str(directory),
                                  'notify_current_chat':bool(thread)}),flush=True)
                announced = state
            if starting:
                continue
            if not batch.get('events') and not batch.get('gap'):
                if state != 'watching':
                    time.sleep(1)
                continue
            # Collect one short edit burst. A rollover or gap is handled in a separate receipt.
            time.sleep(0.35)
            try:
                extra = control.change_request(ws,args.file_key,args.page_id,cursor=new_cursor,timeout=0)
            except (OSError, control.ReadinessError):
                extra = {}
            if extra.get('scope') == batch.get('scope') and extra.get('events') and not extra.get('gap'):
                batch = {**batch,'events':[*batch['events'], *extra['events']], 'cursor':extra['cursor']}
            save(pending,batch)
            path = handle_batch(args, directory, thread, batch)
            cursor = batch['cursor']
            save(checkpoint, {'source':source,'cursor':cursor})
            pending.unlink()
            if args.once and path:
                return


def manage(action, argv):
    parser = argparse.ArgumentParser(prog=f'figma_follow.py {action}')
    parser.add_argument('--state-dir',required=True,type=Path)
    if action == 'latest':
        parser.add_argument('--node-id')
    args = parser.parse_args(argv)
    directory = workspace.private_dir(args.state_dir)
    if action == 'latest':
        latest_path = directory / 'latest.json'
        latest = workspace.read(latest_path, private=True, limit=8_000_000) if latest_path.exists() else {'nodes':{},'last_event':None}
        if args.node_id:
            latest['nodes'] = {args.node_id: latest['nodes'].get(args.node_id,{'status':'unobserved'})}
        print(json.dumps(latest,ensure_ascii=False))
        return
    running = workspace.read(directory/'running.json',private=True)
    try:
        with exclusive(directory):
            state = 'stopped'
    except ValueError:
        state = 'running'
        if action == 'stop':
            save(directory/'stop.json',{'instance':running['instance']})
            state = 'stop-requested'
    print(json.dumps({'state':state,'scope':running['scope'],'pid':running['pid'] if state!='stopped' else None}))


def main():
    if sys.argv[1:2] in (['status'],['stop'],['latest']):
        try:
            return manage(sys.argv[1],sys.argv[2:])
        except (KeyError, OSError, ValueError) as exc:
            raise SystemExit(f'figma-follow: {exc}') from None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--file-key', required=True)
    parser.add_argument('--page-id', required=True)
    parser.add_argument('--notify-current-chat', action='store_true', help='Queue a metadata-only message in the originating Codex thread.')
    parser.add_argument('--resume-chat', action='store_true', help='Also ask the running local Codex daemon to resume the thread.')
    parser.add_argument('--once', action='store_true', help='Exit after one external/unknown edit burst.')
    parser.add_argument('--wait', type=int, default=30, choices=range(1,61), metavar='SECONDS')
    parser.add_argument('--state-dir', type=Path, help='Private resumable checkpoint and event directory.')
    parser.add_argument('--inspect-task', help='Pinned discover task for fresh bounded node property reads.')
    parser.add_argument('--inspect-revision')
    parser.add_argument('--include-text', action='store_true', help='Allow local text excerpts for changed text nodes.')
    parser.add_argument('--apply-clean', action='store_true', help='Publish mapped, conflict-free values only against the unchanged graph and web pair.')
    parser.add_argument('--read-task')
    parser.add_argument('--revision')
    parser.add_argument('--read-timeout', type=int, default=120)
    parser.add_argument('--graph', type=Path)
    parser.add_argument('--pairing', type=Path)
    parser.add_argument('--web-module', type=Path)
    parser.add_argument('--component-edits', action='store_true', help='Preview direct edits on declared component roots.')
    args = parser.parse_args()
    if args.resume_chat and not args.notify_current_chat:
        parser.error('--resume-chat requires --notify-current-chat')
    if not 1 <= args.read_timeout <= 3600:
        parser.error('read timeout must be between 1 and 3600 seconds')
    try:
        follow(args)
    except (KeyError, OSError, ValueError, TypeError) as exc:
        parser.exit(2, f'figma-follow: {exc}\n')


if __name__ == '__main__':
    main()
