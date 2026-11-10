"""Shared panel structure and DOM behavior; no live Figma claim."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from panel_components import STATUS, render_components, shell
from plugin_panel import render_panel


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = {}
        self.duplicates = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if 'id' in attributes:
            identity = attributes['id']
            if identity in self.ids:
                self.duplicates.append(identity)
            self.ids[identity] = (tag, attributes)


class PanelComponentTests(unittest.TestCase):
    def test_every_view_consumes_the_same_shell_and_accessible_status(self):
        for view in STATUS:
            with self.subTest(view=view):
                output = render_components('<body><!-- FLOW_SHELL --><main><!-- FLOW_STATUS --></main></body>', view)
                elements = Elements(output)
                self.assertFalse(elements.duplicates)
                self.assertIn(shell(), output)
                for identity in ('workspace-locale', 'tab-tasks', 'tab-history', 'tab-codex'):
                    self.assertIn(identity, elements.ids)
                nav = elements.ids['workspace-tablist'][1]
                self.assertIn('hidden', nav)
                self.assertEqual(nav['data-i18n-aria'], 'workspace.nav.label')
                region, title, body = STATUS[view][:3]
                attributes = elements.ids[region][1]
                self.assertEqual(attributes['role'], 'status')
                self.assertEqual(attributes['aria-live'], 'polite')
                self.assertEqual(attributes['aria-atomic'], 'true')
                self.assertIn(title, elements.ids)
                self.assertIn(body, elements.ids)

    def test_missing_duplicate_and_foreign_slots_fail_closed(self):
        for html, view in [('', 'import'), ('<!-- FLOW_SHELL --><!-- FLOW_SHELL --><!-- FLOW_STATUS -->', 'import'),
                           ('<!-- FLOW_SHELL --><!-- FLOW_STATUS --><!-- FLOW_CONTROL_STATUS -->', 'graph')]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                render_components(html, view)
        output = render_components('<!-- FLOW_SHELL --><!-- FLOW_STATUS --><!-- FLOW_CONTROL_STATUS -->', 'workspace')
        self.assertIn('id="control-status"', output)
        self.assertIn('id="control-title"', output)

    def test_real_child_templates_consume_components_and_preserve_controls(self):
        expected = {'import': ('ui.html', ['import', 'export', 'sync', 'save', 'json']),
                    'graph': ('graph-panel.html', ['read', 'review', 'apply', 'cancel', 'download']),
                    'chat': ('workspace_chat.html', ['prepare', 'send', 'copy', 'request', 'preview'])}
        for view, (name, controls) in expected.items():
            with self.subTest(view=view):
                source = (ROOT / 'figma-bridge' / name).read_text()
                output = render_components(source, view)
                elements = Elements(output)
                self.assertFalse(elements.duplicates)
                self.assertNotIn('<!-- FLOW_', output)
                self.assertIn('FlowPanel.status(', output)
                for identity in controls:
                    self.assertIn(identity, elements.ids)
                self.assertLess(output.index('id="workspace-tablist"'), output.index('<main'))

    def test_standalone_renderer_injects_real_shared_runtime_and_ids(self):
        sources = [(ROOT / 'figma-bridge' / name).read_text() for name in
                   ('ui.html', 'graph-panel.html', 'workspace_chat.html', 'workspace_home.html')]
        review = (ROOT / 'tools/figma_draft.py').read_text()
        sources.append(re.search(r"html = '''(<!doctype html>.*?)'''", review, re.S)[1])
        for source in sources:
            view = re.search(r'data-flow-view="([^"]+)"', source)[1]
            with self.subTest(view=view):
                output = render_panel(source)
                self.assertNotIn('<!-- FLOW_', output)
                self.assertNotIn('FIGMA_FLOW_PANEL_CSS', output)
                self.assertFalse(Elements(output).duplicates)
                self.assertIn('globalThis.FlowPanel = Object.freeze', output)
                self.assertLess(output.index('globalThis.FlowUI = Object.freeze'), output.index('globalThis.FlowPanel = Object.freeze'))
                self.assertIn(shell(), output)

    def test_review_uses_shared_shell_without_changing_native_protocol(self):
        source = (ROOT / 'tools/figma_draft.py').read_text()
        template = re.search(r"html = '''(<!doctype html>.*?)'''", source, re.S)[1]
        output = render_components(template, 'review')
        elements = Elements(output)
        self.assertFalse(elements.duplicates)
        for identity in ('make', 'save', 'status', 'status-panel', 'status-details'):
            self.assertIn(identity, elements.ids)
        self.assertIn("document.getElementById('workspace-locale')", output)
        self.assertIn('FlowPanel.status(', output)
        self.assertIn("receiptOutcome = response.ok && receipt.passed === true", output)

    @unittest.skipUnless(shutil.which('node'), 'Node required for DOM helper behavior')
    def test_real_runtime_navigation_locale_busy_and_safe_status(self):
        script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(){this.hidden=false;this.disabled=false;this.value='preserved form value';this.dataset={};this.attributes={};this.listeners={};this.textContent='';}
  addEventListener(name,handler){this.listeners[name]=handler;}
  setAttribute(name,value){this.attributes[name]=String(value);}
  removeAttribute(name){delete this.attributes[name];}
  set innerHTML(_value){throw Error('Raw HTML mutation is forbidden');}
}
const elements=Object.fromEntries(['workspace-tablist','workspace-locale','tab-tasks','tab-history','tab-codex','status','status-title','status-body','request'].map(id=>[id,new Element()]));
const listeners={},root={dataset:{}};
const context={document:{documentElement:root,getElementById:id=>elements[id]},window:{addEventListener:(name,handler)=>listeners[name]=handler},FlowUI:{locale:'en',setLocale(value){this.locale=value;listeners['flow:locale']?.();}}};
context.globalThis=context;vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const panel=context.FlowPanel;assert.equal(elements['workspace-tablist'].hidden,true);
const navigation=[],locales=[];
panel.mount({mode:'workspace',active:'history',onNavigate:name=>navigation.push(name),onLocale:locale=>{locales.push(locale);context.FlowUI.setLocale(locale);}});
assert.equal(elements['workspace-tablist'].hidden,false);assert.equal(elements['tab-history'].attributes['aria-current'],'page');
elements['tab-codex'].listeners.click();assert.deepEqual(navigation,['codex']);
panel.setState({busy:true});elements['tab-tasks'].listeners.click();assert.deepEqual(navigation,['codex']);assert.equal(elements['tab-tasks'].disabled,true);
elements['workspace-locale'].value='ja';elements['workspace-locale'].listeners.change();assert.deepEqual(locales,['ja']);assert.equal(elements.request.value,'preserved form value');
panel.status({region:'status',title:'status-title',body:'status-body',state:'busy',titleText:'<img src=x onerror=alert(1)>',bodyText:'native error <script>'});
assert.equal(elements['status-title'].textContent,'<img src=x onerror=alert(1)>');assert.equal(elements.status.attributes['aria-busy'],'true');assert.equal(elements['status-body'].hidden,false);
panel.status({region:'status',title:'status-title',body:'status-body',state:'success',titleText:'Saved'});
assert.equal(elements['status-body'].hidden,true);assert.equal(elements.status.attributes['aria-busy'],'false');
panel.mount({mode:'standalone',busy:false});assert.equal(elements['workspace-tablist'].hidden,true);
'''
        result = subprocess.run(['node', '-e', script, str(ROOT / 'figma-bridge/panel_components.js')], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
