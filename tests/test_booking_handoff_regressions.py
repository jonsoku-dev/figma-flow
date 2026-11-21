"""Booking handoff regressions: nullable raster refs and real narrow-layout widths."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]

import graph_sync
from graph_design_system import emit_web_module, load_graph, resolve_design_system
import native_handoff
from test_native_handoff import fixture

COMPONENT = 'button.bookingCTA'
COLOR = {'r': 1.0, 'g': 0.0, 'b': 0.0}
ASSET_HASHES = {
    'map-raster-only', 'map-raster-shared', 'frame-raster-ref',
    'frame-paint-1', 'frame-paint-2', 'frame-paint-3',
}


def _native_graph() -> dict:
    return {'design_system': {
        'version': 1, 'id': 'little-hands',
        'tokens': {'color.bookingCta': {'type': 'COLOR', 'value': COLOR},
                   'color.action.primary': {'type': 'COLOR', 'alias': 'color.bookingCta'}},
        'components': {COMPONENT: {
            'properties': {'backgroundColor': 'color.action.primary'},
            'native': {'mainKeys': ['components.play/idle'], 'instanceKeys': ['screen.play'],
                       'semanticToken': 'color.action.primary'},
            'web': {'selector': '.button.booking-cta:not(:hover):not(:active)'},
        }},
        'native': {'file_key': 'fixture', 'page_id': '1:1', 'collection_id': 'c:1'},
    }}


def _cli_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    data, contract = fixture()
    data['schema'] = 'figma-flow-graph-native-discovery-v1'
    data['allowed_page_ids'] = ['1:1']
    data['collections'][0]['modes'] = [data['collections'][0]['modes'][0]]
    for variable in data['variables']:
        variable['valuesByMode'].pop('m:2', None)
    graph = _native_graph()
    graph_path = root / 'graph.json'
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    loaded = load_graph(graph_path)
    resolved = resolve_design_system(loaded)
    _, names = graph_sync.token_native_names(loaded)
    data['variables'][0]['name'] = names['color.bookingCta']
    data['variables'][1]['name'] = names['color.action.primary']
    data['nodes'][1]['semanticKey'] = 'screen.play'
    data['nodes'][1]['fills'][0]['color'] = {key: COLOR[key] for key in 'rgb'}
    data['nodes'][3]['semanticKey'] = 'components.play/idle'
    data['nodes'][3]['fills'] = [{
        'type': 'SOLID', 'color': {key: COLOR[key] for key in 'rgb'},
        'boundVariables': {'color': {'type': 'VARIABLE_ALIAS', 'id': 'v:semantic'}},
    }]
    contract['variables'] = [
        {'name': names[key], 'resolved_type': 'COLOR'}
        for key in ('color.bookingCta', 'color.action.primary')]
    contract['screens'][0]['controls'][0]['token_bindings'] = [
        {'property': 'fills.0.color', 'variable': names['color.action.primary']}]
    contract['screens'][0]['controls'][0]['component_key'] = 'components.play/idle'

    # A frame and its paint layers carry legitimate image refs beside nullable paints.
    data['rasterImages'] = {
        'map-raster-only': {}, 'map-raster-shared': {}, 'frame-paint-1': {},
    }
    data['nodes'][0]['rasterImageRef'] = 'frame-raster-ref'
    data['nodes'][0]['fills'] = [
        {'type': 'IMAGE', 'imageHash': 'frame-paint-1'},
        {'type': 'SOLID', 'color': {key: COLOR[key] for key in 'rgb'}},
        {'type': 'IMAGE', 'imageHash': None},
        {'type': 'IMAGE', 'imageHash': 'frame-paint-2'},
        {'type': 'IMAGE', 'imageHash': 'frame-paint-3'},
    ]
    readback_path = root / 'readback.json'
    readback_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    contract_path = root / 'contract.json'
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    token_ids = {'color.bookingCta': 'v:raw', 'color.action.primary': 'v:semantic'}
    roots = {'color.bookingCta': 'v:raw', 'color.action.primary': 'v:raw'}
    chains = {'color.bookingCta': ['v:raw'], 'color.action.primary': ['v:semantic', 'v:raw']}
    tokens = [{'key': key, 'type': 'COLOR', 'variable_id': token_ids[key],
               'variable_name': names[key], 'root_variable_id': roots[key],
               'alias_chain': chains[key], 'resolved': resolved['tokens'][key]}
              for key in ('color.bookingCta', 'color.action.primary')]
    plan = {'schema': 'figma-flow-graph-token-sync-v1', 'graph_sha256': loaded.source_sha256,
            'file_key': 'fixture', 'page_id': '1:1', 'collection_id': 'c:1', 'tokens': tokens,
            'components': [{'id': COMPONENT,
                            'properties': {'backgroundColor': 'color.action.primary'},
                            'main_keys': ['1:5'], 'instance_keys': ['1:3']} ]}
    web_module = root / 'tokens.mjs'
    emit_web_module(graph_path, web_module)
    web_proof = {'schema': 'figma-flow-graph-web-readback-v1',
                 'graph_sha256': loaded.source_sha256,
                 'observed_at': '2026-11-22T00:00:00Z',
                 'url': 'http://localhost:8769/sessions/1/',
                 'components': [{'id': COMPONENT,
                                 'selector': '.button.booking-cta:not(:hover):not(:active)',
                                 'graph_sha256': loaded.source_sha256,
                                 'properties': resolved['components'][COMPONENT]}]}
    pairing = {'schema': graph_sync.RECEIPT, 'graph_sha256': loaded.source_sha256,
               'tokens': tokens, 'primitive_roots': resolved['primitiveRoots'], 'plan': plan,
               'consumer_ids': {}, 'declarations': graph['design_system']['components'],
               'native_scope': graph['design_system']['native'], 'web_proof': web_proof,
               'web_module_sha256': hashlib.sha256(web_module.read_bytes()).hexdigest()}
    pairing_path = root / 'pairing.json'
    pairing_path.write_text(json.dumps(pairing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return graph_path, readback_path, contract_path, pairing_path, web_module


def _layout_pack(asset_count: int = 64) -> dict:
    labels = {'reserve-preview': '예약 내용 확인', 'reserve-login': '로그인하고 예약하기'}
    node = lambda name, identity, label='': {
        'id': identity, 'key': name, 'name': name,
        'url': f'https://www.figma.com/design/fixture?node-id={identity}',
        'observed': {'width': 165, 'height': 48},
        'label': {'characters': label} if label else {},
    }
    excluded = [{'sha256': f'{index:064x}', 'reason': 'Image bytes are not embedded in this offline pack'}
                for index in range(1, asset_count + 1)]
    report = {'passed': True, 'errors': [], 'screens': [], 'component_scope': {
        'component_id': COMPONENT,
        'frame': node('CTA frame', 'frame:1'),
        'main': node('bookingCTA', 'main:1', '예약하기'),
        'instances': [node('reserve-preview', 'member:1', labels['reserve-preview']),
                      node('reserve-login', 'guest:1', labels['reserve-login'])],
        'sync_fields': [{'field': 'backgroundColor', 'token_key': 'color.action.primary',
                         'status': 'matched', 'native_getter': COLOR,
                         'browser_computed': COLOR}],
        'text_comparison': {'status': 'matched', 'native_actual_labels': labels,
                            'template_branch_labels': labels,
                            'source': 'apps/little-hands/templates/booking/session_detail.html',
                            'source_sha256': 'a' * 64},
        'graph_context': {'status': 'graph-authored; not native screen evidence',
                          'screen': None, 'action': None},
        'coverage': {'application_screen': 'not included', 'acceptance_conditions': 'not included'},
        'web_proof': {'observed_at': '2026-11-22T00:00:00Z',
                      'url': 'http://localhost:8769/sessions/1/',
                      'web_module_sha256': 'b' * 64, 'components': []},
    }}
    return {'format_version': 'figma-flow-offline-handoff-v1',
            'provenance': {
                'observed_at': '2026-11-22T00:00:00Z', 'file_key': 'fixture-file',
                'page_id': 'page:1', 'revision': None, 'revision_status': 'unavailable',
                'scope': 'full selected page', 'coverage': 'all admitted nodes',
                'graph_sha256': 'c' * 64, 'graph_sha256_status': 'paired-current-at-export',
                'readback_sha256': 'd' * 64, 'contract_sha256': None,
                'selected_scope': {'kind': 'component', 'component_key': COMPONENT,
                                   'frame_id': 'frame:1', 'main_id': 'main:1',
                                   'instance_ids': ['member:1', 'guest:1']},
                'graph_sync': {'status': 'paired-current-at-export'},
                'assets': {'included': [], 'excluded': excluded},
                'omissions': ['Private plugin data', 'Unsupported or unavailable native fields',
                              'Raster image bytes'],
            }, 'report': report}


def _chrome_binary() -> str | None:
    configured = os.environ.get('CHROME_BIN')
    if configured:
        return configured if Path(configured).is_file() else None
    binary = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    if binary:
        return binary
    mac_chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    return str(mac_chrome) if mac_chrome.is_file() else None


def _run_viewports(document: str, proof_root: Path | None) -> list[dict]:
    binary = _chrome_binary()
    if not binary:
        raise unittest.SkipTest('Google Chrome/Chromium unavailable; set CHROME_BIN for real-browser proof')
    widths = (320, 390, 1365)
    child_pages = {}
    probe = r'''<script>
const section=document.querySelector('.asset-exclusions');
const details=section?.querySelector('details');
const records=details ? Array.from(details.querySelectorAll('[data-asset-exclusion]')) : [];
const proof={viewport:innerWidth,scroll:document.documentElement.scrollWidth,
 detailsPresent:!!details,detailsInitiallyOpen:details ? details.open : null,
 summary:details?.querySelector('summary')?.textContent||null,
 hashes:records.map(p=>p.dataset.sha256),reasons:records.map(p=>p.textContent)};
if(details) details.open=true;
proof.disclosed=details ? Array.from(details.querySelectorAll('[data-asset-exclusion]')).filter(p=>p.getClientRects().length).length : 0;
proof.scrollAfterOpen=document.documentElement.scrollWidth;
proof.external=performance.getEntriesByType('resource').map(x=>x.name).filter(x=>/^https?:/i.test(x));
parent.postMessage({type:'handoff-proof',proof},'*');
</script></body>'''
    child_document = document.replace('</body>', probe)
    for width in widths:
        child_pages[str(width)] = child_document
    outer = '''<!doctype html><html><head><meta charset="utf-8"><title>handoff viewport probe</title></head>
<body><script>const pages=__PAGES__;const widths=[320,390,1365];const results=[];
function collect(frame,width){return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('viewport probe timeout: '+width)),15000);
function receive(event){if(event.source!==frame.contentWindow||event.data?.type!=='handoff-proof')return;
clearTimeout(timer);window.removeEventListener('message',receive);resolve(event.data.proof);}
window.addEventListener('message',receive);frame.srcdoc=pages[String(width)];document.body.appendChild(frame);});}
(async()=>{for(const width of widths){const frame=document.createElement('iframe');frame.title='handoff '+width;
frame.style.cssText='display:block;width:'+width+'px;height:900px;border:0';frame.width=String(width);frame.height='900';
results.push(await collect(frame,width));}
const output=document.createElement('pre');output.id='browser-results';output.textContent=JSON.stringify(results);document.body.appendChild(output);})();
</script></body></html>'''.replace('__PAGES__', json.dumps(child_pages, ensure_ascii=False).replace('</', '<\\/'))
    with tempfile.TemporaryDirectory(prefix='booking-handoff-chrome-') as temp:
        temp_root = Path(temp)
        page = temp_root / 'viewport-probe.html'
        page.write_text(outer, encoding='utf-8')
        shot = temp_root / 'viewport-probe.png'
        profile = temp_root / 'chrome-profile'
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            raise unittest.SkipTest('real-browser layout proof must run as a normal user with the browser sandbox enabled')
        cmd = [binary, '--headless=new', '--disable-gpu', '--disable-background-networking',
               '--disable-component-update', '--disable-sync', '--disable-default-apps',
               '--disable-extensions', '--no-first-run', '--no-default-browser-check',
               f'--user-data-dir={profile}', '--window-size=1365,900', f'--screenshot={shot}',
               '--virtual-time-budget=10000', '--dump-dom', page.as_uri()]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proof_root:
            proof_root.mkdir(parents=True, exist_ok=True)
            (proof_root / 'outer-probe.html').write_text(outer, encoding='utf-8')
            (proof_root / 'chrome-dump.html').write_text(result.stdout, encoding='utf-8')
            (proof_root / 'chrome-stderr.log').write_text(result.stderr, encoding='utf-8')
            if shot.is_file():
                shutil.copy2(shot, proof_root / 'viewport-probe.png')
        if result.returncode:
            raise AssertionError(f'headless browser failed: {result.stderr[-2000:]}')
        marker = 'id="browser-results">'
        start = result.stdout.find(marker)
        if start < 0:
            raise AssertionError('headless browser did not produce viewport measurements')
        start += len(marker)
        end = result.stdout.find('</pre>', start)
        proofs = json.loads(result.stdout[start:end])
        if proof_root:
            proof_root.mkdir(parents=True, exist_ok=True)
            (proof_root / 'outer-probe.html').write_text(outer, encoding='utf-8')
            (proof_root / 'browser-layout.json').write_text(json.dumps(proofs, indent=2) + '\n', encoding='utf-8')
            (proof_root / 'browser.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            if shot.is_file():
                shutil.copy2(shot, proof_root / 'viewport-probe.png')
    return proofs


class BookingHandoffRegressionTest(unittest.TestCase):
    def _proof_root(self) -> Path | None:
        stage = os.environ.get('BOOKING_HANDOFF_PROOF_STAGE')
        if not stage:
            return None
        if not stage.replace('-', '').isalnum():
            self.fail('BOOKING_HANDOFF_PROOF_STAGE must be a simple name')
        target = ROOT / '.figma-flow/booking-remediation/web' / stage
        target.mkdir(parents=True, exist_ok=True)
        return target

    def test_cli_keeps_all_legitimate_raster_refs_and_skips_null_paints(self):
        with tempfile.TemporaryDirectory(prefix='booking-handoff-cli-') as temp:
            root = Path(temp)
            graph, readback, contract, pairing, web_module = _cli_fixture(root)
            output = root / 'pack'
            cmd = [sys.executable, str(ROOT / 'tools/native_handoff.py'),
                   '--readback', str(readback), '--contract', str(contract), '--page-id', '1:1',
                   '--offline-pack', '--confirm-included-text', '--graph-sync-graph', str(graph),
                   '--graph-sync-pairing', str(pairing), '--web-module', str(web_module), '--out', str(output)]
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            stage = self._proof_root()
            if stage:
                (stage / 'cli-result.json').write_text(json.dumps({
                    'command': cmd, 'returncode': result.returncode,
                    'stdout': result.stdout, 'stderr': result.stderr,
                }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            self.assertEqual(result.returncode, 0,
                'offline handoff CLI should accept nullable multi-paint image refs; '
                f'it exited {result.returncode}: {result.stderr.strip()}')
            pack = json.loads((output / 'handoff.json').read_text(encoding='utf-8'))
            excluded = pack['provenance']['assets']['excluded']
            hashes = [row['sha256'] for row in excluded]
            self.assertEqual(hashes, sorted(ASSET_HASHES),
                'offline handoff should retain every distinct legitimate raster reference exactly once')
            self.assertTrue(all(row['reason'] == 'Image bytes are not embedded in this offline pack'
                                for row in excluded))

    def test_real_browser_layout_and_asset_details_at_320_390_1365(self):
        pack = _layout_pack()
        document = native_handoff.offline_html(pack)
        proofs = _run_viewports(document, self._proof_root())
        self.assertEqual([row['viewport'] for row in proofs], [320, 390, 1365],
                         'browser fixture must exercise exact CSS viewport widths')
        self.assertTrue(all(row['scroll'] <= row['viewport'] and row['scrollAfterOpen'] <= row['viewport'] for row in proofs),
                        'offline handoff must not overflow 320px, 390px, or 1365px; '
                        + json.dumps([{k: r[k] for k in ('viewport', 'scroll', 'scrollAfterOpen')} for r in proofs]))
        mobile = next(row for row in proofs if row['viewport'] == 390)
        self.assertTrue(mobile['detailsPresent'], 'excluded raster hashes must use native details disclosure')
        self.assertFalse(mobile['detailsInitiallyOpen'], 'long excluded asset list must begin collapsed')
        self.assertIn('64', mobile['summary'], 'summary should report excluded asset count')
        expected = [f'{index:064x}' for index in range(1, 65)]
        self.assertEqual(mobile['hashes'], expected, 'details DOM must retain every excluded raster hash')
        self.assertEqual(mobile['disclosed'], 64, 'users can expand to reveal every excluded asset')
        self.assertEqual(mobile['external'], [], 'offline handoff must not request external resources')


if __name__ == '__main__':
    unittest.main()
