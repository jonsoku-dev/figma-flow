'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { inspectPanelExternalConsumers, observePanel } = require('../panel-ui/observed-graph.cjs');

const panel = (name) => `panel-ui/src/${name}`;

function fixture(context, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'figma-flow-panel-observer-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, contents] of Object.entries(files)) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, contents);
  }
  return root;
}

test('observes the built panel entry and its generated view registry with direct source evidence', () => {
  const root = path.resolve(__dirname, '..');
  const graph = JSON.parse(fs.readFileSync(path.join(root, 'library/panel-design/governance.json'), 'utf8'));
  const command = spawnSync(process.execPath, ['panel-ui/observed-graph.cjs', '--options-stdin'], {
    cwd: root, input: JSON.stringify({ entries: [panel('app.jsx')], externalConsumers: graph.externalConsumers }),
    encoding: 'utf8',
  });
  assert.equal(command.status, 0, command.stderr);
  const result = JSON.parse(command.stdout);
  assert.equal(result.schema, 'figma-flow-observed-panel-v1');
  assert.deepEqual(result.entries, [panel('app.jsx')]);
  assert.match(result.sourceFingerprint, /^[a-f0-9]{64}$/);
  assert.equal(result.findings.length, 0);
  const react = result.packages.find((record) => record.name === 'react');
  assert.match(react.version, /^\d+\.\d+\.\d+/);
  assert.match(result.inputFiles[react.manifest], /^[a-f0-9]{64}$/);
  const registry = result.nodes.find((node) => node.path === panel('view-registry.generated.js'));
  assert.equal(registry.origin, 'generated');
  assert.equal(registry.generatedFrom, 'library/panel-design/views.json');
  assert.ok(result.edges.some((edge) =>
    edge.type === 'IMPORTS' && edge.from === registry.path && edge.to === panel('RelayViewer.jsx')));
  assert.ok(result.edges.some((edge) => edge.type === 'IMPORTS' && edge.mode === 'static' &&
    edge.from === panel('ReviewPanel.jsx') && edge.to === panel('reviewTransport.mjs')));
  const reviewCall = result.edges.find((edge) => edge.type === 'CALLS' && edge.mode === 'static-import-binding' &&
    edge.from === panel('ReviewPanel.jsx') && edge.to === panel('reviewTransport.mjs'));
  assert.equal(reviewCall.targetSymbol, 'postDraftReceipt');
  assert.equal(reviewCall.certainty, 'extracted');
  const reviewLines = fs.readFileSync(path.join(root, reviewCall.from), 'utf8').split('\n');
  assert.ok(reviewLines[reviewCall.location.line - 1].slice(reviewCall.location.column - 1)
    .startsWith('postDraftReceipt('));
  assert.ok(reviewLines[reviewCall.importLocation.line - 1].slice(reviewCall.importLocation.column - 1)
    .startsWith('postDraftReceipt'));
  const exportImport = result.edges.find((edge) =>
    edge.type === 'IMPORTS' && edge.from === panel('DiagnosticExport.jsx') && edge.resolution === 'external-file');
  assert.equal(exportImport.to, 'figma-bridge/audit_log.js');
  assert.equal(exportImport.specifier, '../../figma-bridge/audit_log.js');
  assert.deepEqual(exportImport.location, { path: panel('DiagnosticExport.jsx'), line: 3, column: 1 });
  assert.equal(result.usage.find((usage) => usage.path === panel('RelayViewer.jsx')).status, 'used');
  assert.equal(result.externalEvidence.length, graph.externalConsumers.length);
  for (const witness of result.externalEvidence) {
    const { path: sourceFile, line, column } = witness.location;
    const source = fs.readFileSync(path.join(root, sourceFile), 'utf8').split('\n');
    assert.ok(source[line - 1].slice(column - 1).startsWith('import('));
    assert.ok(source[witness.proof.launcher.line - 1].includes('subprocess.run'));
    assert.equal(witness.consumerSha256, result.inputFiles[witness.consumer]);
  }
});

test('retains source positions and differentiates static, dynamic, bundled and syntactic evidence', async (context) => {
  const root = fixture(context, {
    [panel('app.jsx')]: [
      'import { load } from "./loader";',
      'import "./style.css";',
      '',
      'export function App() {',
      '  load();',
      '  return <main />;',
      '}',
    ].join('\n'),
    [panel('loader.js')]: 'export { load } from "./tools.mjs";',
    [panel('tools.mjs')]: 'export function load() { return import(`./lazy.js`); }',
    [panel('lazy.js')]: 'export const data = 1;',
    [panel('style.css')]: 'main { display: block; }',
    'node_modules/react/jsx-runtime.js': 'export function jsx() {}',
  });
  const options = { root, entries: [panel('app.jsx')] };
  const result = await observePanel(options);
  assert.deepEqual(result.findings, []);
  assert.ok(result.edges.some((edge) => edge.mode === 'implicit' && edge.resolution === 'package' &&
    edge.specifier === 'react/jsx-runtime'));
  assert.deepEqual(result.edges.find((edge) => edge.from === panel('app.jsx') && edge.specifier === './loader'), {
    type: 'IMPORTS', from: panel('app.jsx'), to: panel('loader.js'), mode: 'static', specifier: './loader',
    location: { path: panel('app.jsx'), line: 1, column: 1 }, certainty: 'extracted', resolution: 'local',
  });
  assert.ok(result.edges.some((edge) => edge.type === 'REEXPORTS' && edge.to === panel('tools.mjs')));
  assert.ok(result.edges.some((edge) => edge.resolution === 'asset' && edge.to === panel('style.css')));
  assert.deepEqual(result.edges.find((edge) => edge.type === 'CALLS' && edge.symbol === 'load'), {
    type: 'CALLS', from: panel('app.jsx'), to: panel('loader.js'), symbol: 'load', certainty: 'extracted',
    location: { path: panel('app.jsx'), line: 5, column: 3 }, targetSymbol: 'load',
    importLocation: { path: panel('app.jsx'), line: 1, column: 10 }, mode: 'static-import-binding',
  });
  assert.deepEqual(result.usage.find((entry) => entry.path === panel('lazy.js')).evidence, {
    path: ['app.jsx', 'loader.js', 'tools.mjs', 'lazy.js'].map(panel),
    modes: ['static', 'static', 'dynamic'],
  });
  assert.deepEqual(await observePanel(options), result);
  fs.appendFileSync(path.join(root, panel('style.css')), '\n');
  assert.notEqual((await observePanel(options)).sourceFingerprint, result.sourceFingerprint);
});

test('call proof excludes shadowing, imports without calls and unresolved member or wildcard targets', async (context) => {
  const root = fixture(context, {
    [panel('app.mjs')]: [
      'import defaultCall, { named as localAlias, unused, wildcard } from "./adapter.mjs";',
      'import * as adapter from "./adapter.mjs";',
      'export function run(app) {',
      '  localAlias(); defaultCall(); adapter.named(); wildcard();',
      '  return ({ localAlias }) => localAlias();',
      '}',
    ].join('\n'),
    [panel('adapter.mjs')]: 'export default function useDefault() {}\n' +
      'export function named() {} export function unused() {}\nexport * from "./reexports.mjs";',
    [panel('reexports.mjs')]: 'export function wildcard() {}',
  });
  const result = await observePanel({ root, entries: [panel('app.mjs')] });
  assert.deepEqual(result.findings, []);
  const calls = result.edges.filter((edge) => edge.type === 'CALLS' && edge.from === panel('app.mjs'));
  assert.equal(calls.find((edge) => edge.symbol === 'defaultCall').targetSymbol, 'default');
  assert.equal(calls.find((edge) => edge.symbol === 'defaultCall').mode, 'static-import-binding');
  for (const shadowed of calls.filter((edge) => edge.symbol === 'localAlias')) {
    assert.equal(shadowed.to, null);
    assert.equal(shadowed.importCandidate.reason, 'possible-lexical-shadow');
    assert.equal(shadowed.importCandidate.targetSymbol, 'named');
  }
  assert.equal(calls.find((edge) => edge.symbol === 'adapter.named').to, null);
  assert.equal(calls.find((edge) => edge.symbol === 'wildcard').importCandidate.reason, 'unverified-export');
  assert.equal(calls.some((edge) => edge.symbol === 'unused'), false);
  assert.ok(result.edges.some((edge) => edge.type === 'IMPORTS' && edge.to === panel('adapter.mjs')));
  const main = path.join(root, panel('app.mjs'));
  fs.writeFileSync(main, fs.readFileSync(main, 'utf8').replace('({ localAlias }) => localAlias()', '() => localAlias()'));
  const unshadowed = await observePanel({ root, entries: [panel('app.mjs')] });
  assert.ok(unshadowed.edges.some((edge) => edge.symbol === 'localAlias' && edge.targetSymbol === 'named' &&
    edge.mode === 'static-import-binding'));
});

test('reports only initialization cycles separately from dynamic connections', async (context) => {
  const root = fixture(context, {
    [panel('app.js')]: 'import "./peer.js"; export const load = () => import("./lazy.js");',
    [panel('peer.js')]: 'import "./app.js";',
    [panel('lazy.js')]: 'import "./app.js";',
    [panel('unused.js')]: 'export const unused = 1;',
  });
  const result = await observePanel({ root, entries: [panel('app.js')] });
  assert.deepEqual(result.cycles, [['app.js', 'peer.js'].map(panel)]);
  assert.deepEqual(result.cyclesIncludingDynamic, [['app.js', 'lazy.js', 'peer.js'].map(panel)]);
  assert.equal(result.usage.find((record) => record.path === panel('unused.js')).status, 'unused-candidate');
});

test('a staged linked package tree produces portable evidence and source symlinks stay unscanned', async (context) => {
  const installed = fixture(context, {
    'node_modules/fixture-package/package.json': '{"name":"fixture-package","version":"1.0.0","main":"index.js"}',
    'node_modules/fixture-package/index.js': 'export const item = 1;',
    'external.mjs': 'export const outside = 1;',
  });
  const source = {
    [panel('app.mjs')]: 'import "fixture-package";\nimport "./linked.mjs";',
  };
  const records = [];
  for (let index = 0; index < 2; index++) {
    const root = fixture(context, source);
    fs.symlinkSync(path.join(installed, 'node_modules'), path.join(root, 'panel-ui/node_modules'), 'junction');
    fs.symlinkSync(path.join(installed, 'external.mjs'), path.join(root, panel('linked.mjs')));
    records.push(await observePanel({ root, entries: [panel('app.mjs')] }));
  }
  const [first, second] = records;
  const manifest = 'panel-ui/node_modules/fixture-package/package.json';
  assert.deepEqual(first.packages, [{ name: 'fixture-package', version: '1.0.0', manifest }]);
  assert.match(first.inputFiles[manifest], /^[a-f0-9]{64}$/);
  assert.ok(first.edges.some((edge) => edge.specifier === 'fixture-package' && edge.resolution === 'package'));
  assert.ok(first.findings.some((issue) => issue.path === panel('linked.mjs') && issue.rule === 'source-symlink'));
  assert.ok(first.findings.some((issue) => issue.specifier === './linked.mjs' && issue.rule === 'unscanned-source'));
  assert.equal(Object.hasOwn(first.inputFiles, panel('linked.mjs')), false);
  assert.equal(first.sourceFingerprint, second.sourceFingerprint);
  assert.equal(JSON.stringify(first).includes(fs.realpathSync(installed)), false);
  const redirected = fixture(context, { 'panel-ui/package.json': '{}' });
  fs.symlinkSync(path.join(installed, 'node_modules'), path.join(redirected, 'panel-ui/src'), 'junction');
  await assert.rejects(observePanel({ root: redirected, entries: [panel('app.mjs')] }),
    /requires a physical source directory/);
});

test('reports missing imports, nonliteral connections, and parser limits without claiming dead code', async (context) => {
  const root = fixture(context, {
    [panel('app.js')]: 'import "./misspelled.js";\nexport const load = (target) => import(target);',
    [panel('might-be-used.mjs')]: 'export const value = 1;',
    [panel('not-parsed.mjs')]: 'export const = 1;',
  });
  const result = await observePanel({ root, entries: [panel('app.js')] });
  assert.deepEqual(result.findings.map((finding) => finding.rule).sort(),
    ['dynamic-unknown', 'parse-error', 'unresolved']);
  const unknownImport = result.edges.find((edge) => edge.resolution === 'dynamic-unknown');
  assert.equal(unknownImport.to, null);
  assert.equal(unknownImport.location.line, 2);
  assert.deepEqual(result.usage.find((record) => record.path === panel('might-be-used.mjs')), {
    path: panel('might-be-used.mjs'), status: 'unknown', blockers: [panel('app.js')],
  });
  assert.equal(result.usage.find((record) => record.path === panel('not-parsed.mjs')).status, 'unknown');
});

test('represents a declared external consumer independently of runtime reachability', async (context) => {
  const root = fixture(context, {
    [panel('app.js')]: '',
    [panel('outside.mjs')]: 'export { helpers } from "./helpers.mjs";',
    [panel('helpers.mjs')]: 'export const helpers = 1;',
    [panel('unused.mjs')]: 'export const unused = 1;',
    'tools/consumer.mjs': 'import "../panel-ui/src/outside.mjs";',
  });
  const result = await observePanel({
    root, entries: [panel('app.js')], externalConsumers: [{ path: panel('outside.mjs'), consumer: 'tools/consumer.mjs' }],
  });
  assert.deepEqual(result.findings, []);
  assert.equal(result.externalEvidence[0].certainty, 'extracted');
  assert.deepEqual(result.externalEvidence[0].location, { path: 'tools/consumer.mjs', line: 1, column: 1 });
  assert.equal(result.externalEvidence[0].consumerSha256, result.inputFiles['tools/consumer.mjs']);
  assert.deepEqual(result.usage.find((record) => record.path === panel('helpers.mjs')), {
    path: panel('helpers.mjs'), status: 'external',
    evidence: { path: ['outside.mjs', 'helpers.mjs'].map(panel), modes: ['static'], consumer: 'tools/consumer.mjs' },
  });
  assert.equal(result.usage.find((record) => record.path === panel('unused.mjs')).status, 'unused-candidate');
});

test('a comment and an unused Python string cannot establish external usage', async (context) => {
  const root = fixture(context, {
    [panel('app.js')]: '',
    [panel('orphan.mjs')]: 'export { helper } from "./helper.mjs";',
    [panel('helper.mjs')]: 'export const helper = 1;',
    'tools/doc-demo.mjs': '// import "../panel-ui/src/orphan.mjs";',
    'tools/doc-demo.py': 'example = r"""\nimport("./panel-ui/src/orphan.mjs");\n"""\n',
  });
  const result = await observePanel({
    root, entries: [panel('app.js')], externalConsumers: ['doc-demo.mjs', 'doc-demo.py'].map((name) => ({
      path: panel('orphan.mjs'), consumer: 'tools/' + name,
    })),
  });
  assert.deepEqual(result.externalEvidence, []);
  assert.deepEqual(result.findings.map((finding) => finding.rule),
    ['external-consumer-unverified', 'external-consumer-unverified']);
  assert.deepEqual(result.usage.find((row) => row.path === panel('helper.mjs')), {
    path: panel('helper.mjs'), status: 'unknown', blockers: ['tools/doc-demo.mjs', 'tools/doc-demo.py'],
  });
});

test('Python evidence depends on the Node launcher and its repository-relative working directory', (context) => {
  const root = fixture(context, {
    [panel('outside.mjs')]: 'export const exported = 1;',
    'tools/project.py': 'from pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n',
    'tools/report.py': [
      'import subprocess',
      'import project as workspace',
      'def read_external():',
      '    script = r"""',
      'import("./panel-ui/src/outside.mjs");',
      '"""',
      '    return_value = subprocess.run(["node", "-e", script], cwd=workspace.ROOT)',
      '    return return_value.stdout',
    ].join('\n'),
  });
  const options = { root, externalConsumers: [{ path: panel('outside.mjs'), consumer: 'tools/report.py' }] };
  const observed = inspectPanelExternalConsumers(options);
  assert.deepEqual(observed.findings, []);
  assert.deepEqual(observed.evidence[0].location, { path: 'tools/report.py', line: 5, column: 1 });
  assert.match(observed.inputFiles['tools/project.py'], /^[a-f0-9]{64}$/);
  fs.writeFileSync(path.join(root, 'tools/project.py'), 'from pathlib import Path\nROOT = Path(__file__).resolve().parents[0]\n');
  const changed = inspectPanelExternalConsumers(options);
  assert.deepEqual(changed.evidence, []);
  assert.equal(changed.findings[0].rule, 'external-consumer-unverified');
});

test('symbol CLI reports changed and removed named syntax while retaining parse uncertainty', () => {
  const rows = [
    { path: panel('same.mjs'), before: 'export const fresh = 1;', after: '\n// moved\nexport const fresh = 1;' },
    { path: panel('invalid.mjs'), before: 'export const value = 1;', after: 'export const = ;' },
    { path: panel('removed.mjs'), before: 'export class Retired {}', after: null },
    { path: panel('actual.jsx'),
      before: 'function Label() { return <i>before</i>; }\nexport { Label as Public };',
      after: '// shifted\nfunction Label() { return <i>updated</i>; }\nexport { Label as Public };' },
    { path: panel('added.js'), before: null, after: 'export const added = 1n;' },
  ];
  const command = spawnSync(process.execPath, ['panel-ui/observed-graph.cjs', '--symbols-stdin'], {
    cwd: path.resolve(__dirname, '..'), input: JSON.stringify(rows), encoding: 'utf8',
  });
  assert.equal(command.status, 0, command.stderr);
  const result = JSON.parse(command.stdout);
  assert.equal(result.schema, 'figma-flow-observed-panel-symbol-diff-v1');
  const [modified, added, invalid, removed, same] = result.files;
  assert.deepEqual(modified.changes.map(({ name, kind, change }) => [name, kind, change]),
    [['Label', 'function', 'modified'], ['Public', 'export', 'modified']]);
  assert.equal(modified.changes[0].before.location.line, 1);
  assert.equal(modified.changes[0].after.location.line, 2);
  assert.notEqual(modified.changes[0].before.sha256, modified.changes[0].after.sha256);
  assert.ok(added.changes.every((row) => row.change === 'added' && row.before === null));
  assert.equal(invalid.status, 'unknown');
  assert.deepEqual(invalid.changes, []);
  assert.equal(invalid.unknown[0].revision, 'after');
  assert.ok(removed.changes.every((row) => row.change === 'removed' && row.after === null));
  assert.equal(same.status, 'unchanged');
});
