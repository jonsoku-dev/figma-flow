import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFile, cp, lstat, mkdir, mkdtemp, readFile, readdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { inspectPanelExternalConsumers } from './observed-graph.cjs';
import { panelViewRegistry, panelViewRegistryModule } from './view-registry.mjs';

const repository = fileURLToPath(new URL('../', import.meta.url));
const knipManifest = new URL('../package.json', import.meta.resolve('knip'));
const panelDirectory = 'panel-ui';
const sourceDirectory = panelDirectory + '/src';
const sourceFiles = 'src/**/*.{js,mjs,cjs,jsx,ts,mts,cts,tsx}';
const productionChecks = 'files,dependencies,unlisted,unresolved,exports,nsExports,types,nsTypes';

const parseJson = async (file) => JSON.parse(await readFile(file, 'utf8'));
const sha256 = (content) => createHash('sha256').update(content).digest('hex');

function repositoryRelative(root, path) {
  const name = relative(root, path);
  if (!name || isAbsolute(name) || name === '..' || name.startsWith('..' + sep)) {
    throw new Error('Knip input must be within the repository: ' + path);
  }
  return name.split(sep).join('/');
}

async function readRegular(root, name) {
  const path = resolve(root, name);
  if (repositoryRelative(root, path) !== name || (await realpath(path)) !== path || !(await lstat(path)).isFile()) {
    throw new Error('Knip input must be a regular repository file: ' + name);
  }
  return readFile(path);
}

async function stageFile(root, scratch, name) {
  const destination = join(scratch, name);
  const bytes = await readRegular(root, name);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, bytes);
}

async function stagePanel(root, scratch, policy) {
  const current = join(root, panelDirectory);
  const panel = join(scratch, panelDirectory);
  await mkdir(panel, { recursive: true });
  await cp(join(root, sourceDirectory), join(scratch, sourceDirectory), {
    recursive: true,
    filter: async (path) => {
      const info = await lstat(path);
      if (info.isSymbolicLink()) throw new Error('Knip cannot analyze a symbolic panel source: ' + repositoryRelative(root, path));
      return info.isDirectory() || info.isFile();
    },
  });
  const tooling = (await readdir(current, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && /\.[cm]?js$/.test(entry.name))
    .map((entry) => entry.name).sort();
  for (const name of ['package.json', ...tooling]) {
    await copyFile(join(current, name), join(panel, name));
  }
  await symlink(join(current, 'node_modules'), join(panel, 'node_modules'), 'junction');
  await stageFile(root, scratch, 'tools/maintenance-contract.json');
  for (const [importer, specifiers] of Object.entries(policy.externalImports)) {
    const source = dirname(resolve(root, sourceDirectory, importer));
    for (const specifier of specifiers) await stageFile(root, scratch, repositoryRelative(root, resolve(source, specifier)));
  }
  const registry = await panelViewRegistryModule({ root });
  await writeFile(resolve(panel, 'src', panelViewRegistry.specifier), registry, { flag: 'wx' });
  return { panel, tooling };
}

async function runKnip(panel, cli, mode, issueTypes, entry) {
  const reportName = 'knip-' + mode + '-report.json';
  const args = ['--no-progress', '--reporter', 'symbols', '--reporter', 'json',
    '--output-file', 'json=' + reportName, '--include', issueTypes, '--treat-config-hints-as-errors'];
  if (mode === 'production') args.push('--production', '--include-entry-exports');
  const result = spawnSync(process.execPath, [fileURLToPath(cli), ...args], {
    cwd: panel,
    encoding: 'utf8',
  });
  if (result.error) throw result.error;
  if (![0, 1].includes(result.status) || result.signal) {
    throw new Error('Knip ' + mode + ' execution failed: ' + (result.stderr || result.stdout).trim());
  }
  const report = await parseJson(join(panel, reportName));
  if (!Array.isArray(report.issues)) throw new Error('Knip omitted its findings');
  const issues = report.issues.flatMap(({ file, ...groups }) => {
    const path = repositoryRelative(dirname(panel), resolve(panel, file));
    return Object.entries(groups).flatMap(([type, values]) => values.map((item) => ({ ...item, type, path })));
  });
  if (Boolean(issues.length) !== (result.status === 1) || result.stderr.trim()) {
    throw new Error('Knip ' + mode + ' reported an incomplete analysis: ' + (result.stderr || result.stdout).trim());
  }
  return { mode, entry, issueTypes: issueTypes.split(','), exitStatus: result.status, issues };
}

async function reviewExports(root, scratch, graph, issues) {
  if (!Array.isArray(graph.exportDispositions)) throw new Error('Graph must declare exportDispositions');
  const dispositions = new Map();
  const findings = [];
  for (const row of graph.exportDispositions) {
    if (!row.path?.startsWith(sourceDirectory + '/') ||
        !['symbol', 'reason', 'approval', 'reviewCondition'].every((key) => typeof row[key] === 'string' && row[key].trim()) ||
        !Array.isArray(row.evidence) || !row.evidence.length) {
      throw new Error('Retain a specific panel export only with its exact name, reason, evidence and review condition');
    }
    const key = JSON.stringify([row.path, row.symbol]);
    if (dispositions.has(key)) throw new Error('Duplicate export disposition: ' + key);
    const evidence = [];
    const name = new RegExp('(?<![\\w$])' + RegExp.escape(row.symbol) + '(?![\\w$])');
    for (const path of row.evidence) {
      const bytes = await readRegular(root, path);
      if (!name.test(bytes.toString('utf8'))) {
        findings.push({ type: 'stale-export-evidence', path, name: row.symbol });
      }
      evidence.push({ path, sha256: sha256(bytes) });
    }
    const sourceSha256 = sha256(await readRegular(scratch, row.path));
    dispositions.set(key, { ...row, evidence, sourceSha256, applied: false });
  }
  for (const issue of issues) {
    const record = dispositions.get(JSON.stringify([issue.path, issue.name]));
    if (issue.type === 'exports' && record) {
      record.applied = true;
    } else {
      findings.push(issue);
    }
  }
  for (const record of dispositions.values()) {
    if (!record.applied) findings.push({ type: 'stale-export-disposition', path: record.path, name: record.symbol });
  }
  return { findings, dispositions: [...dispositions.values()] };
}

async function check({ root = repository } = {}) {
  root = await realpath(root);
  const [{ panelBoundaries }, graph, manifest] = await Promise.all([
    parseJson(join(root, 'tools/maintenance-contract.json')),
    parseJson(join(root, 'library/panel-design/governance.json')),
    parseJson(knipManifest),
  ]);
  const scratch = await realpath(await mkdtemp(join(tmpdir(), 'figma-flow-knip-')));
  try {
    const entry = ['src/' + panelBoundaries.entry];
    await readRegular(root, panelDirectory + '/' + entry[0]);
    const { evidence: externalEvidence, findings: externalFindings } = inspectPanelExternalConsumers({
      root, externalConsumers: graph.externalConsumers,
    });
    if (externalFindings.length) throw new Error('Knip cannot establish external use: ' + JSON.stringify(externalFindings));
    const external = [];
    for (const row of externalEvidence) {
      await readRegular(root, row.path);
      external.push(row.path.slice(panelDirectory.length + 1));
    }
    const { panel, tooling } = await stagePanel(root, scratch, panelBoundaries);
    const panelManifest = await parseJson(join(panel, 'package.json'));
    const scriptEntrypoints = new Set(Object.values(panelManifest.scripts).map((command) => /^node (\S+)/.exec(command)?.[1]));
    const development = tooling.filter((name) => !scriptEntrypoints.has(name));
    await writeFile(join(panel, 'knip.json'), JSON.stringify({
      entry: [...new Set([...entry, ...external])].map((path) => path + '!').concat(development),
      project: [sourceFiles + '!', '*.{js,mjs,cjs}'],
    }));
    const cli = new URL(manifest.bin.knip, knipManifest);
    const runs = [
      await runKnip(panel, cli, 'production', productionChecks, { runtime: entry, external }),
      await runKnip(panel, cli, 'development', 'devDependencies,binaries', { tooling }),
    ];
    const { findings, dispositions } = await reviewExports(root, scratch, graph, runs.flatMap(({ issues }) => issues));
    return {
      schema: 'figma-flow-panel-knip-v1',
      status: findings.length ? 'failed' : 'passed',
      tool: { version: manifest.version, node: process.versions.node },
      externalEvidence,
      runs,
      findings,
      dispositions,
    };
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }
}

export { check };

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    if (args.length > 1 || (args.length === 1 && args[0] !== '--json')) throw new Error('Usage: node knip.config.mjs [--json]');
    const report = await check();
    if (args.length) {
      console.log(JSON.stringify(report, null, 2));
    } else {
      console.log(`Knip ${report.tool.version}: ${report.status}, ${report.dispositions.length} reviewed production export candidates`);
      for (const { path, type, name } of report.findings) console.error(`${path}: ${type}${name ? ' ' + name : ''}`);
    }
    process.exitCode = report.status === 'passed' ? 0 : 1;
  } catch (error) {
    console.error('Knip: ' + error.message);
    process.exitCode = 1;
  }
}
