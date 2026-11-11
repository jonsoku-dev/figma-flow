"""Prerender the shared shell, navigation and status components for Figma panels."""
from html import escape
import json
from pathlib import Path

from plugin_panel import display_name, supported_locales

BRIDGE = Path(__file__).resolve().parents[1] / 'figma-bridge'
STATUS = {
    'workspace': ('home-status', 'home-status-title', 'home-status-body', 'ready', 'workspace.loading', 'workspace.loadingBody', False),
    'import': ('status-region', 'status-title', 'status', 'busy', 'import.connectingTitle', 'import.connectingBody', False),
    'graph': ('status', 'status-title', 'status-body', 'ready', 'graph.ready', 'graph.readyHelp', True),
    'review': ('status-panel', 'status-title', 'status-body', 'ready', 'review.readyTitle', 'review.readyBody', False),
    'chat': ('chat-status', 'status-title', 'status-body', 'ready', 'chat.ready', None, False),
}
ICONS = {
    'tasks': 'M3 3h10v10H3zM3 6h10M6 6v7',
    'history': 'M2 5a6 6 0 1 1 0 6M2 1v4h4M8 4v4l3 2',
    'codex': 'M3 3h10v8H7l-4 3zM6 6h4M6 8h3',
}
LOCALE_NAMES = {'ko': '한국어', 'en': 'English', 'ja': '日本語'}


def locale_options():
    return ''.join('<option value="' + escape(code, quote=True) + '">' + escape(LOCALE_NAMES.get(code, code)) + '</option>'
                   for code in supported_locales())


def message(key, locale='ko'):
    group = key.split('.')[0]
    return json.loads((BRIDGE / 'locales' / (group + '.json')).read_text(encoding='utf-8'))[key][locale]


def localized(tag, key, **attributes):
    attrs = ''.join(' ' + name.replace('_', '-') + '="' + escape(str(value), quote=True) + '"' for name, value in attributes.items())
    if key is None:
        return '<' + tag + attrs + '></' + tag + '>'
    return '<' + tag + attrs + ' data-i18n="' + escape(key, quote=True) + '">' + escape(message(key)) + '</' + tag + '>'


def navigation():
    buttons = []
    for name, path in ICONS.items():
        icon = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="' + path + '"/></svg>'
        buttons.append('<button id="tab-' + name + '" type="button">' + icon + localized('span', 'workspace.nav.' + name) + '</button>')
    return '<nav class="panel-nav workspace-tabs" id="workspace-tablist" data-i18n-aria="workspace.nav.label" aria-label="' + escape(message('workspace.nav.label'), quote=True) + '" hidden>' + ''.join(buttons) + '</nav>'


def shell():
    language = localized('label', 'workspace.language', **{'for': 'workspace-locale'})
    return ('<header class="panel-shell masthead"><div class="brand"><span class="brand-mark" aria-hidden="true"></span>' + escape(display_name()) + '</div>'
            '<span id="context" class="context" hidden></span><div class="workspace-toolbar">' + language +
            '<select id="workspace-locale" class="panel-input" data-i18n-aria="workspace.language" aria-label="' + escape(message('workspace.language'), quote=True) + '">'
            + locale_options() + '</select></div></header>' + navigation())


def status(view, *, control=False):
    if control:
        region, title, body, state, title_key, body_key, hidden = ('control-status', 'control-title', 'control-body', 'ready', None, None, True)
    else:
        region, title, body, state, title_key, body_key, hidden = STATUS[view]
    attributes = ' hidden' if hidden else ''
    return ('<section class="panel-status status" id="' + region + '" data-state="' + state + '" role="status" aria-live="polite" aria-atomic="true" tabindex="-1"' + attributes + '>' +
            localized('h2', title_key, id=title, **{'class': 'status-title'}) +
            localized('p', body_key, id=body, **{'class': 'status-body'}) + '</section>')


def render_components(html, view):
    if view not in STATUS:
        raise ValueError('Unknown shared panel component view')
    for marker, rendered in (('<!-- FLOW_SHELL -->', shell()), ('<!-- FLOW_STATUS -->', status(view))):
        if html.count(marker) != 1:
            raise ValueError('Panel requires exactly one ' + marker)
        html = html.replace(marker, rendered)
    marker = '<!-- FLOW_CONTROL_STATUS -->'
    if html.count(marker) > 1 or marker in html and view != 'workspace':
        raise ValueError('Only the workspace may contain one control status')
    return html.replace(marker, status(view, control=True))
