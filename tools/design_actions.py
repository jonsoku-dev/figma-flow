#!/usr/bin/env python3
"""Execute bounded normal design actions; no eval, shell handlers, hooks or GUI automation."""
import argparse
import json
from pathlib import Path
import sys

import design_directions as directions
import workflow
from workflow import State, Event


def _cause(exc):
    """A short machine-readable category for the blocked reason."""
    message = str(exc)
    if isinstance(exc, ImportError) and (getattr(exc, 'name', '') or '').split('.')[0] == 'PIL':
        return 'missing-dependency'
    if isinstance(exc, QualityBlocked):
        return 'design-quality'
    if isinstance(exc, directions.SelectionRequired):
        return 'selection-required'
    if 'Canonical workflow/generated consumers drift' in message:
        return 'workflow-drift'
    if message.startswith('Stale/missing input hash'):
        return 'stale-input'
    if 'COLOR consumer' in message:
        return 'unused-color-role'
    return 'invalid-input'


class QualityBlocked(ValueError):
    """Objective design quality errors; nothing is packaged."""

    def __init__(self, message, report_path):
        super().__init__(message)
        self.report_path = report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    draft = actions.add_parser('draft')
    for name in ('project', 'brief', 'research', 'from-existing', 'out'):
        draft.add_argument('--' + name, type=Path, required=True)
    draft.add_argument('--mode', choices=('direct', 'compare'))
    draft.add_argument('--judgement', type=Path)
    draft.add_argument('--review-destination', choices=('local', 'figma'))
    review = actions.add_parser('review')
    review.add_argument('--manifest', type=Path, required=True)
    review.add_argument('--judgement', type=Path, required=True)
    select = actions.add_parser('select')
    select.add_argument('--manifest', type=Path, required=True)
    select.add_argument('--user-event', type=Path, required=True)
    select.add_argument('--out', type=Path, required=True)
    direct = actions.add_parser('admit-direct')
    for name in ('manifest', 'user-event', 'out'):
        direct.add_argument('--' + name, type=Path, required=True)
    validate = actions.add_parser('validate-selection')
    validate.add_argument('--selection', type=Path, required=True)
    generate = actions.add_parser('generate-requests')
    generate.add_argument('--selection', type=Path, required=True)
    generate.add_argument('--batch', type=Path, required=True)
    generate.add_argument('--requests', type=Path, required=True)
    reselect = actions.add_parser('reselect')
    reselect.add_argument('--selection', type=Path, required=True)
    prepare_native = actions.add_parser('prepare-native-review')
    prepare_native.add_argument('--manifest', type=Path, required=True)
    prepare_native.add_argument('--out', type=Path, required=True)
    prepare_native.add_argument('--register-night-demo', action='store_true')
    prepare_native.add_argument('--layout', type=Path)
    prepare_native.add_argument('--file-key')
    prepare_native.add_argument('--plugin-id')
    prepare_native.add_argument('--port', type=int, default=49185)
    status = actions.add_parser('status', help='Read-only: workflow state, input freshness and next events of a review')
    status.add_argument('--manifest', type=Path, required=True)
    status.add_argument('--selection', type=Path)
    quality = actions.add_parser('quality', help='Run the design quality gate on the native layout a review manifest pins')
    quality.add_argument('--manifest', type=Path, required=True)
    quality.add_argument('--out', type=Path)
    quality.add_argument('--strict', action='store_true')
    native = actions.add_parser('verify-native-review')
    native.add_argument('--manifest', type=Path, required=True)
    native.add_argument('--readback', type=Path, required=True)
    graph = actions.add_parser('graph')
    graph.add_argument('--format', choices=('json', 'mermaid'), default='json')
    args = parser.parse_args(argv)
    try:
        if args.action != 'graph':
            directions.assert_workflow_sync()
        if args.action == 'draft':
            result = directions.create_draft(args.project, args.brief, args.research, args.from_existing, args.out, judgement=args.judgement, review_destination=args.review_destination, mode=args.mode)
        elif args.action == 'review':
            result = directions.review_draft(args.manifest, args.judgement)
        elif args.action == 'admit-direct':
            result = directions.record_direct_admission(args.manifest, args.user_event, args.out)
        elif args.action == 'select':
            result = directions.record_selection(args.manifest, args.user_event, args.out)
        elif args.action == 'validate-selection':
            result = directions.require_selected(args.selection)
        elif args.action == 'status':
            result = directions.status(args.manifest, args.selection)
        elif args.action == 'quality':
            import design_quality
            report = design_quality.run(design_quality.manifest_layout(args.manifest), strict=args.strict)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['passed'] else 1
        elif args.action == 'prepare-native-review':
            import design_quality
            import figma_draft
            layout = design_quality.manifest_layout(args.manifest)
            report = design_quality.run(layout)
            report_path = Path(args.manifest).resolve().parent / 'design-quality.json'
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            if report['errors']:
                raise QualityBlocked(design_quality.blocking_summary(report, report_path), report_path)
            admission = directions.admit_native_draft(args.manifest)
            prepared = figma_draft.prepare(args.manifest, args.out, register=args.register_night_demo, night_demo=args.register_night_demo, port=args.port, layout_path=args.layout, file_key=args.file_key, plugin_id=args.plugin_id)
            result = {'workflow_state': admission['state'], 'workflow_symbol': admission['workflow_symbol'],
                      'prepared': prepared, 'warnings': prepared['warnings'], 'production_admitted': False, 'executed': ['prepare-exploratory-native-review-package'],
                      'pending': 'Actual native import and supplied getter readback verification; preparation is not observation.',
                      'quality': {'report': str(report_path), 'errors': 0, 'warnings': len(report['warnings']),
                                  'warning_codes': report['summary']['warning_codes']}}
        elif args.action == 'verify-native-review':
            result = directions.verify_native_review(args.manifest, args.readback)
        elif args.action == 'reselect':
            result = directions.reselect(args.selection)
        elif args.action == 'generate-requests':
            import asset_batch
            packet = asset_batch.release_requests(args.selection, args.batch, args.requests)
            result = {'workflow_state': State.GENERATION.value, 'workflow_symbol': State.GENERATION.name,
                      'requests': packet.get('requests', []), 'executed': ['verify-current-selection-and-exact-host-packet'],
                      'pending': 'Actual image_gen host calls and returned originals. A subprocess cannot authenticate or execute that host tool.'}
        else:
            if args.format == 'mermaid':
                print(workflow.mermaid())
                return 0
            result = workflow.public_graph()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError) as exc:
        actual_state = getattr(exc, 'state', None)
        manifest = getattr(args, 'manifest', None)
        if actual_state is None and manifest:
            try:
                verified = directions.validate_draft(manifest, require_agent_review=False)
                actual_state = State(verified['data']['workflow_state'])
            except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError):
                actual_state = None
        blocked = {'workflow_state': actual_state.value if actual_state else None, 'workflow_symbol': actual_state.name if actual_state else None,
                   'required_boundary': State.WAIT_SELECTION.name if isinstance(exc, directions.SelectionRequired) else None,
                   'blocked_reason': str(exc), 'executed': [],
                   'next_action': 'Prepare and inspect real comparable drafts, present them, and wait for the actual human decision. Never default or auto-approve.'}
        blocked['cause'] = _cause(exc)
        if blocked['cause'] == 'missing-dependency':
            blocked['next_action'] = f'{sys.executable} -m pip install Pillow  (README의 실행 환경 확인 절차 참고)'
        elif blocked['cause'] == 'workflow-drift':
            blocked['next_action'] = 'python3 tools/sync_workflow.py --check 로 차이를 확인한 뒤 다시 실행하세요.'
        elif blocked['cause'] == 'stale-input':
            blocked['next_action'] = '바뀐 입력 파일을 확인하고, 의도한 변경이면 검토를 다시 준비하세요. 해시를 손으로 고치지 마세요.'
        if isinstance(exc, QualityBlocked):
            blocked['quality_report'] = str(exc.report_path)
            blocked['next_action'] = 'Fix every design quality error in the authored layout, re-render and re-run the gate, then prepare the review package again.'
        print(json.dumps(blocked, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
