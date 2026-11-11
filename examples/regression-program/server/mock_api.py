"""Stateless mock responses for the regression apps.

Payloads are fixtures. This server does not take payment, send mail, or publish.
"""


def _text_draft(payload):
    draft = payload.get('draft')
    if not isinstance(draft, dict) or any(not isinstance(value, str) for value in draft.values()):
        return None
    return draft


def decide_save(payload):
    draft = _text_draft(payload)
    if draft is None:
        return 400, {'ok': False, 'error': 'invalid-draft'}
    if payload.get('fault') == 'save-task':
        return 409, {'ok': False, 'error': 'save-failed', 'draft': draft}
    return 200, {'ok': True, 'task': draft}


def decide_order(payload):
    if payload.get('fault') == 'stock':
        return 409, {'ok': False, 'error': 'stock-conflict', 'orders': payload.get('existing') or []}
    if payload.get('fault') == 'price' and not payload.get('priceSeen'):
        return 409, {'ok': False, 'error': 'price-changed', 'price': payload.get('nextPrice'), 'orders': payload.get('existing') or []}
    if payload.get('signature') in (payload.get('existingSignatures') or []):
        return 200, {'ok': True, 'duplicate': True, 'orderId': payload.get('existingOrderId')}
    return 200, {'ok': True, 'duplicate': False, 'orderId': payload.get('nextOrderId')}


def decide_return(payload):
    form = payload.get('form')
    if not isinstance(form, dict) or not isinstance(form.get('reason'), str) or not isinstance(form.get('note'), str):
        return 400, {'ok': False, 'error': 'invalid-draft'}
    if payload.get('fault') == 'return':
        return 409, {'ok': False, 'error': 'return-failed', 'form': form}
    if not form['reason'].strip():
        return 400, {'ok': False, 'error': 'reason-required', 'form': form}
    return 200, {'ok': True, 'returnId': payload.get('nextReturnId')}


def decide_autosave(payload):
    draft = _text_draft(payload)
    if draft is None:
        return 400, {'ok': False, 'error': 'invalid-draft'}
    if payload.get('fault') == 'autosave':
        return 409, {'ok': False, 'error': 'autosave-failed', 'draft': draft}
    return 200, {'ok': True, 'draft': draft}


def decide_publish(payload):
    draft = _text_draft(payload)
    if payload.get('role') != 'editor':
        return 403, {'ok': False, 'error': 'editor-required'}
    if draft is None:
        return 400, {'ok': False, 'error': 'invalid-draft'}
    if payload.get('fault') == 'publish':
        return 409, {'ok': False, 'error': 'publish-failed', 'draft': draft}
    return 200, {'ok': True, 'mode': 'virtual', 'article': {'title': draft['title'], 'body': draft['body'], 'status': 'published'}}


ROUTES = {
    '/api/atlas/tasks/save': decide_save,
    '/api/morrow/orders': decide_order,
    '/api/morrow/returns': decide_return,
    '/api/paper/drafts': decide_autosave,
    '/api/paper/publish': decide_publish,
}


def handle(path, payload):
    if not isinstance(payload, dict):
        raise ValueError('JSON object required')
    route = ROUTES.get(path)
    if route is None:
        raise ValueError('unknown api')
    return route(payload)
