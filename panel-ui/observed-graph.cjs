'use strict';

const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const { SourceMap } = require('node:module');
const path = require('node:path');
const acorn = require('../vendor/acorn/acorn.js');
const esbuild = require('esbuild');

const sourceDirectory = 'panel-ui/src';
const buildPolicy = 'tools/maintenance-contract.json';
const isModule = (file) => /\.(?:m?js|jsx)$/.test(file);
const digest = (value) => createHash('sha256').update(value).digest('hex');
const byName = (first, second) => first < second ? -1 : first > second ? 1 : 0;
const relativePath = (root, file) => path.relative(root, file).split(path.sep).join('/');
const within = (file, directory) => file.startsWith(`${directory}/`);
const isRepoPath = (file) => typeof file === 'string' && !!file && !file.includes('\\') &&
  !path.posix.isAbsolute(file) && !file.split('/').some((segment) => ['', '.', '..'].includes(segment));

function sourceFiles(directory, prefix, files, findings) {
  const entries = fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => byName(a.name, b.name));
  for (const entry of entries) {
    const file = `${prefix}/${entry.name}`;
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) sourceFiles(absolute, file, files, findings);
    else if (entry.isFile() && isModule(file)) files.set(file, fs.readFileSync(absolute));
    else if (entry.isSymbolicLink()) findings.push({ rule: 'source-symlink', path: file });
  }
}

function walk(node, visit) {
  visit(node);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) {
      for (const child of value) if (child?.type) walk(child, visit);
    } else if (value?.type) walk(value, visit);
  }
}

function exportBindings(pattern) {
  switch (pattern.type) {
    case 'Identifier': return [pattern];
    case 'AssignmentPattern': return exportBindings(pattern.left);
    case 'RestElement': return exportBindings(pattern.argument);
    case 'ArrayPattern': return pattern.elements.filter(Boolean).flatMap(exportBindings);
    case 'ObjectPattern': return pattern.properties.flatMap((property) =>
      exportBindings(property.type === 'Property' ? property.value : property));
    default: return [];
  }
}

function symbol(node) {
  return node.type === 'Identifier' ? node.name : node.value;
}

function callName(callee) {
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type !== 'MemberExpression') return null;
  const owner = callName(callee.object);
  const property = callee.computed
    ? callee.property.type === 'Literal' && `[${JSON.stringify(callee.property.value)}]`
    : `.${callee.property.name}`;
  return owner && property ? owner + property : null;
}

function literalSource(node) {
  if (node?.type === 'Literal' && typeof node.value === 'string') return node.value;
  if (node?.type === 'TemplateLiteral' && !node.expressions.length) return node.quasis[0].value.cooked;
  return null;
}

function moduleSyntax(file, source, captureSymbols = false) {
  const transformed = file.endsWith('.jsx')
    ? esbuild.transformSync(source, { loader: 'jsx', jsx: 'automatic', sourcemap: 'external', sourcefile: file })
    : null;
  const sourceMap = transformed && new SourceMap(JSON.parse(transformed.map));
  const location = (node) => {
    const { line, column } = node.loc.start;
    if (!sourceMap) return { path: file, line, column: column + 1 };
    const mapped = sourceMap.findEntry(line - 1, column);
    return mapped.originalSource
      ? { path: file, line: mapped.originalLine + 1, column: mapped.originalColumn + 1 }
      : null;
  };
  const sourceLines = source.split(/\r?\n/);
  const ast = acorn.parse(transformed?.code ?? source, {
    ecmaVersion: 'latest', sourceType: 'module', locations: true,
  });
  const edges = [];
  const exports = [];
  const exportSyntax = [];
  const addExport = (name, node, syntax, local) => {
    const site = location(node);
    exports.push({ name, location: site });
    if (captureSymbols && name !== '*') exportSyntax.push({ name, location: site, syntax, local });
  };
  walk(ast, (node) => {
    const site = location(node);
    const addDependency = (type, mode, target) => edges.push({
      type, from: file, to: null, mode, specifier: literalSource(target), location: site, certainty: 'extracted',
    });
    switch (node.type) {
      case 'ImportDeclaration': {
        const authored = !sourceMap || (site && /^import\b/.test(sourceLines[site.line - 1].slice(site.column - 1)));
        addDependency('IMPORTS', authored ? 'static' : 'implicit', node.source);
        break;
      }
      case 'ImportExpression':
        addDependency('IMPORTS', 'dynamic', node.source);
        break;
      case 'ExportDefaultDeclaration':
        addExport('default', node, node, node.declaration.type === 'Identifier' ? node.declaration.name : null);
        break;
      case 'ExportAllDeclaration':
        addDependency('REEXPORTS', 'static', node.source);
        addExport(node.exported ? symbol(node.exported) : '*', node.exported ?? node, node);
        break;
      case 'ExportNamedDeclaration':
        if (node.source) addDependency('REEXPORTS', 'static', node.source);
        for (const specifier of node.specifiers) addExport(
          symbol(specifier.exported), specifier.exported, [specifier, node.source],
          node.source ? null : symbol(specifier.local),
        );
        if (node.declaration?.id) addExport(node.declaration.id.name, node.declaration.id, node.declaration);
        for (const declaration of node.declaration?.declarations ?? []) {
          for (const binding of exportBindings(declaration.id)) addExport(
            binding.name, binding, [node.declaration.kind, declaration],
          );
        }
        break;
      case 'CallExpression': {
        const name = callName(node.callee);
        if (name === 'require') addDependency('IMPORTS', 'commonjs', node.arguments[0]);
        if (name && site) edges.push({
          type: 'CALLS', from: file, to: null, symbol: name, location: site, certainty: 'syntactic',
        });
        break;
      }
      default:
        break;
    }
  });
  const authoredBinding = (name, site) => !sourceMap ||
    (site && sourceLines[site.line - 1].slice(site.column - 1).startsWith(name));
  return { edges, exports, symbols: captureSymbols ? moduleSymbols(ast, location, exportSyntax, authoredBinding) : [] };
}

function syntaxDigest(syntax) {
  return digest(JSON.stringify(syntax, (key, value) => {
    if (['start', 'end', 'loc', 'raw'].includes(key)) return undefined;
    return typeof value === 'bigint' ? String(value) : value;
  }));
}

function moduleSymbols(ast, location, exportSyntax, authoredBinding) {
  const declarations = new Map();
  const register = (binding, kind, syntax) => {
    const { name } = binding;
    const key = JSON.stringify([name, kind]);
    if (!declarations.has(key)) declarations.set(key, { name, kind, location: location(binding), definitions: [] });
    declarations.get(key).definitions.push(syntaxDigest(syntax));
  };
  for (const item of ast.body) {
    const statement = item.declaration ?? item;
    if (statement.type === 'VariableDeclaration') {
      for (const definition of statement.declarations) {
        for (const binding of exportBindings(definition.id)) register(binding, 'variable', [statement.kind, definition]);
      }
    } else if (['FunctionDeclaration', 'ClassDeclaration'].includes(statement.type) && statement.id) {
      register(statement.id, statement.type === 'FunctionDeclaration' ? 'function' : 'class', statement);
    }
  }
  const bindings = [...declarations.values()].map(({ definitions, ...row }) => ({
    ...row, sha256: digest(JSON.stringify(definitions)),
  }));
  const localDigests = new Map(bindings.map(({ name, sha256 }) => [name, sha256]));
  const symbols = bindings.filter(({ name, location: site }) => authoredBinding(name, site));
  for (const { name, location: site, local, syntax } of exportSyntax) symbols.push({
    name, kind: 'export', location: site, sha256: syntaxDigest([syntax, localDigests.get(local) ?? null]),
  });
  return symbols;
}

function compareModuleSymbols(rows) {
  if (!Array.isArray(rows)) throw new Error('Compare a list of repository-relative panel sources');
  const paths = new Set();
  const files = rows.map(({ path: file, before, after }) => {
    if (!isRepoPath(file) || !within(file, sourceDirectory) || !isModule(file) || paths.has(file) ||
        [before, after].some((value) => value !== null && typeof value !== 'string')) {
      throw new Error('Compare each panel source once with before/after text or null');
    }
    paths.add(file);
    const unknown = [];
    const key = ({ name, kind }) => JSON.stringify([name, kind]);
    const records = (source, revision) => {
      if (source === null) return new Map();
      try {
        return new Map(moduleSyntax(file, source, true).symbols.map(({ name, kind, ...record }) => [
          key({ name, kind }), record,
        ]));
      } catch (error) {
        const detail = error.errors?.[0];
        const site = detail?.location ?? error.loc;
        unknown.push({
          revision, message: detail?.text ?? error.message,
          location: site ? { path: file, line: site.line, column: site.column + 1 } : null,
        });
        return new Map();
      }
    };
    const old = records(before, 'before');
    const next = records(after, 'after');
    if (unknown.length) return { path: file, status: 'unknown', changes: [], unknown };
    const keys = [...new Set([...old.keys(), ...next.keys()])].sort();
    const changes = keys.flatMap((id) => {
      const before = old.get(id) ?? null;
      const after = next.get(id) ?? null;
      if (before?.sha256 === after?.sha256) return [];
      const [name, kind] = JSON.parse(id);
      return [{ name, kind, change: before ? (after ? 'modified' : 'removed') : 'added', before, after }];
    });
    return { path: file, status: changes.length ? 'changed' : 'unchanged', changes, unknown };
  });
  return {
    schema: 'figma-flow-observed-panel-symbol-diff-v1', files: files.sort((a, b) => byName(a.path, b.path)),
    extractor: { esbuild: esbuild.version, acorn: acorn.version, sha256: digest(fs.readFileSync(__filename)) },
  };
}

const nodeScriptProbe = String.raw`
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

root = Path.cwd()
consumer = Path(sys.argv[1])
source = sys.stdin.read()
tree = ast.parse(source)
imports = {
    alias.asname or alias.name: alias.name
    for statement in tree.body if isinstance(statement, ast.Import)
    for alias in statement.names
}
inputs = {}

def assignments(statements, name):
    return [row.value for row in statements
            if isinstance(row, ast.Assign) and len(row.targets) == 1
            and isinstance(row.targets[0], ast.Name) and row.targets[0].id == name]

def repository_cwd(expression):
    owner, module, name = root / consumer, tree, getattr(expression, 'id', None)
    if isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
        qualified = imports.get(expression.value.id)
        if not qualified or not all(part.isidentifier() for part in qualified.split('.')):
            return False
        owner = (root / consumer).parent.joinpath(*qualified.split('.')).with_suffix('.py')
        if not owner.is_file() or owner.resolve() != owner:
            return False
        content = owner.read_bytes()
        module = ast.parse(content)
        name = expression.attr
        inputs[owner.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
    definitions = assignments(module.body, name)
    if len(definitions) != 1 or not any(
        isinstance(statement, ast.ImportFrom) and statement.module == 'pathlib'
        and any(alias.name == 'Path' and alias.asname is None for alias in statement.names)
        for statement in module.body
    ):
        return False
    match = re.fullmatch(r'Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]', ast.unparse(definitions[0]))
    return match is not None and int(match[1]) < len(owner.parents) and owner.parents[int(match[1])] == root

def local_names(function):
    names = set()
    for part in ast.walk(function):
        if isinstance(part, ast.arg):
            names.add(part.arg)
        elif isinstance(part, ast.Name) and isinstance(part.ctx, (ast.Store, ast.Del)):
            names.add(part.id)
        elif isinstance(part, ast.alias):
            names.add(part.asname or part.name)
    return names

scripts = []
for function in tree.body:
    if not isinstance(function, ast.FunctionDef):
        continue
    locals = local_names(function)
    for index, statement in enumerate(function.body):
        if isinstance(statement, (ast.Return, ast.Raise)):
            break
        call = statement.value if isinstance(statement, (ast.Assign, ast.Expr)) else None
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        receiver = call.func.value
        if (call.func.attr != 'run' or not isinstance(receiver, ast.Name) or receiver.id in locals
                or imports.get(receiver.id) != 'subprocess'):
            continue
        argv = call.args[0] if call.args else None
        if not isinstance(argv, (ast.List, ast.Tuple)) or len(argv.elts) != 3:
            continue
        node, evaluate, script = argv.elts
        if not (isinstance(node, ast.Constant) and node.value == 'node'
                and isinstance(evaluate, ast.Constant) and evaluate.value == '-e' and isinstance(script, ast.Name)):
            continue
        definitions = assignments(function.body[:index], script.id)
        stores = [part for part in ast.walk(function) if isinstance(part, ast.Name)
                  and isinstance(part.ctx, ast.Store) and part.id == script.id]
        if len(stores) != 1 or len(definitions) != 1 or not isinstance(definitions[0], ast.Constant):
            continue
        literal = definitions[0]
        spelling = ast.get_source_segment(source, literal)
        quote = spelling[:4]
        if quote.lower() not in ('r"""', "r'''") or spelling[4:-3] != literal.value or not spelling[4:].startswith('\n'):
            continue
        if any(row.arg not in {'cwd', 'input', 'text', 'capture_output', 'check', 'timeout', 'encoding', 'errors'}
               for row in call.keywords):
            continue
        working_dir = next((row.value for row in call.keywords if row.arg == 'cwd'), None)
        scope = working_dir.value if isinstance(working_dir, ast.Attribute) else working_dir
        if isinstance(scope, ast.Name) and scope.id not in locals and repository_cwd(working_dir):
            scripts.append({'script': literal.value, 'line': literal.lineno, 'function': function.name,
                            'launcher': {'line': call.lineno, 'column': call.col_offset + 1}})
print(json.dumps({'scripts': scripts, 'inputFiles': inputs}))
`;

function consumerImports(root, consumer, source) {
  if (isModule(consumer)) {
    return {
      roots: moduleSyntax(consumer, source).edges.filter((edge) =>
        ['IMPORTS', 'REEXPORTS'].includes(edge.type) && edge.mode === 'static')
        .map(({ specifier, location }) => ({
          specifier, location, directory: path.posix.dirname(consumer), proof: { kind: 'javascript-static-import' },
        })),
      inputFiles: {},
    };
  }
  if (!consumer.endsWith('.py')) return { roots: [], inputFiles: {} };
  const probe = spawnSync('python3', ['-B', '-c', nodeScriptProbe, consumer], {
    cwd: root, input: source, encoding: 'utf8', timeout: 10000,
  });
  if (probe.status !== 0 || probe.error) return { roots: [], inputFiles: {} };
  const { scripts, inputFiles } = JSON.parse(probe.stdout);
  const roots = scripts.flatMap(({ script, line, function: fn, launcher }) =>
    moduleSyntax(consumer, script).edges.filter((edge) =>
      edge.type === 'IMPORTS' && edge.mode === 'dynamic').map(({ specifier, location }) => ({
        specifier, location: { ...location, line: line + location.line - 1 }, directory: '.',
        proof: { kind: 'python-node-e-import', function: fn, launcher: { ...launcher, path: consumer } },
      })));
  return { roots, inputFiles };
}

function inspectPanelExternalConsumers({ root, externalConsumers }) {
  root = fs.realpathSync(root);
  const scanned = new Map();
  const evidence = [];
  const findings = [];
  const inputFiles = {};
  for (const { path: file, consumer } of externalConsumers) {
    if (!isRepoPath(file) || !within(file, sourceDirectory) || !isRepoPath(consumer) || within(consumer, sourceDirectory)) {
      throw new Error('External consumer evidence requires a panel module and a separate repository-relative consumer');
    }
    if (!scanned.has(consumer)) {
      try {
        const absolute = path.join(root, consumer);
        if (fs.realpathSync(absolute) !== absolute || !fs.lstatSync(absolute).isFile()) {
          throw new Error('Expected a regular repository file');
        }
        const content = fs.readFileSync(absolute);
        inputFiles[consumer] = digest(content);
        const observed = consumerImports(root, consumer, content.toString('utf8'));
        Object.assign(inputFiles, observed.inputFiles);
        scanned.set(consumer, observed.roots);
      } catch {
        scanned.set(consumer, []);
      }
    }
    const witness = scanned.get(consumer).find(({ directory, specifier }) =>
      specifier?.startsWith('.') && path.posix.normalize(path.posix.join(directory, specifier)) === file);
    if (!witness) {
      findings.push({ rule: 'external-consumer-unverified', path: file, consumer });
      continue;
    }
    const { specifier, location, proof } = witness;
    evidence.push({ path: file, consumer, consumerSha256: inputFiles[consumer], specifier, location, proof, certainty: 'extracted' });
  }
  return { evidence, findings, inputFiles };
}

async function resolveDependencies(root, files, edges, inputs, virtual) {
  const key = ({ from, specifier, mode }) => JSON.stringify([from, specifier, mode]);
  const requests = new Map(edges.filter(({ type, specifier }) => type !== 'CALLS' && specifier !== null)
    .map((edge) => [key(edge), edge]));
  const resolutions = new Map();
  const packages = new Map();
  await esbuild.build({
    absWorkingDir: root, stdin: { contents: '' }, bundle: true, write: false, logLevel: 'silent',
    plugins: [{
      name: 'observe-panel-resolution',
      setup(build) {
        build.onStart(async () => {
          await Promise.all([...requests].map(async ([id, { from, mode, specifier }]) => {
            const importer = path.join(root, from);
            const resolveDir = path.dirname(importer);
            if (specifier === virtual.specifier && files.has(virtual.path)) {
              resolutions.set(id, { resolution: 'local', to: virtual.path });
              return;
            }
            const kind = mode === 'dynamic' ? 'dynamic-import' : mode === 'commonjs' ? 'require-call' : 'import-statement';
            const result = await build.resolve(specifier, { importer, resolveDir, kind });
            let resolution = 'unresolved';
            let to = null;
            if (result.external) {
              resolution = 'external-reference';
              to = specifier;
            } else if (!result.errors.length && result.path) {
              const target = relativePath(root, result.path);
              if (!specifier.startsWith('.') && !path.isAbsolute(specifier) && target.split('/').includes('node_modules')) {
                resolution = 'package';
                to = specifier;
                const name = specifier.split('/').slice(0, specifier.startsWith('@') ? 2 : 1).join('/');
                const packageLocation = `node_modules/${name}/`;
                const start = target.lastIndexOf(packageLocation);
                if (start !== -1) {
                  const manifest = target.slice(0, start) + packageLocation + 'package.json';
                  if (!packages.has(manifest) && fs.existsSync(path.join(root, manifest))) {
                    const content = fs.readFileSync(path.join(root, manifest));
                    packages.set(manifest, { name, version: JSON.parse(content.toString('utf8')).version, manifest });
                    inputs.set(manifest, digest(content));
                  }
                }
              } else if (isRepoPath(target)) {
                to = target;
                if (files.has(target)) resolution = 'local';
                else if (!within(target, sourceDirectory)) resolution = 'external-file';
                else if (isModule(target)) resolution = 'unscanned-source';
                else resolution = 'asset';
                if (resolution !== 'local' && !inputs.has(target)) inputs.set(target, digest(fs.readFileSync(result.path)));
              }
            }
            resolutions.set(id, { resolution, to });
          }));
        });
      },
    }],
  });
  for (const edge of edges) {
    if (edge.type === 'CALLS') continue;
    if (edge.specifier === null) edge.resolution = 'dynamic-unknown';
    else Object.assign(edge, resolutions.get(key(edge)));
  }
  return [...packages.keys()].sort().map((manifest) => packages.get(manifest));
}

function closure(roots, outgoing) {
  const reached = new Map();
  const queue = [];
  for (const root of roots) {
    reached.set(root, { path: [root], modes: [] });
    queue.push(root);
  }
  for (const parent of queue) {
    const previous = reached.get(parent);
    for (const edge of outgoing.get(parent) ?? []) {
      if (reached.has(edge.to)) continue;
      reached.set(edge.to, { path: [...previous.path, edge.to], modes: [...previous.modes, edge.mode] });
      queue.push(edge.to);
    }
  }
  return reached;
}

function cyclesFor(files, outgoing, includeDynamic) {
  const order = new Map();
  const low = new Map();
  const stack = [];
  const onStack = new Set();
  const cycles = [];
  function visit(file) {
    order.set(file, order.size);
    low.set(file, order.get(file));
    stack.push(file);
    onStack.add(file);
    const dependencies = outgoing.get(file).filter(({ mode }) => includeDynamic || mode !== 'dynamic');
    for (const { to } of dependencies) {
      if (!order.has(to)) {
        visit(to);
        low.set(file, Math.min(low.get(file), low.get(to)));
      } else if (onStack.has(to)) low.set(file, Math.min(low.get(file), order.get(to)));
    }
    if (low.get(file) !== order.get(file)) return;
    const component = [];
    while (onStack.has(file)) {
      const member = stack.pop();
      onStack.delete(member);
      component.push(member);
    }
    if (component.length > 1 || dependencies.some(({ to }) => to === file)) {
      cycles.push(component.sort());
    }
  }
  for (const file of files) if (!order.has(file)) visit(file);
  return cycles.sort((first, second) => byName(first[0], second[0]));
}

async function observePanel({ root = path.resolve(__dirname, '..'), entries, externalConsumers = [] } = {}) {
  root = fs.realpathSync(root);
  const { panelViewRegistry, panelViewRegistryModule } = await import('./view-registry.mjs');
  const virtual = {
    ...panelViewRegistry, path: path.posix.join(sourceDirectory, panelViewRegistry.specifier),
  };
  if (entries === undefined) {
    const { panelBoundaries } = JSON.parse(fs.readFileSync(path.join(root, buildPolicy), 'utf8'));
    entries = [`${sourceDirectory}/${panelBoundaries.entry}`];
  }
  if (!Array.isArray(entries) || !entries.length || !entries.every(isRepoPath) ||
      !Array.isArray(externalConsumers) || !externalConsumers.every((row) => isRepoPath(row?.path) && isRepoPath(row?.consumer))) {
    throw new Error('Panel observation requires repository-relative entry and consumer paths');
  }
  const files = new Map();
  const inputs = new Map();
  const findings = [];
  sourceFiles(path.join(root, sourceDirectory), sourceDirectory, files, findings);
  for (const file of ['panel-ui/package.json', 'panel-ui/package-lock.json', 'panel-ui/build.mjs',
    'panel-ui/view-registry.mjs', virtual.graph, buildPolicy]) {
    if (fs.existsSync(path.join(root, file))) inputs.set(file, digest(fs.readFileSync(path.join(root, file))));
  }
  if (inputs.has(virtual.graph)) {
    if (files.has(virtual.path)) {
      inputs.set(virtual.path, digest(files.get(virtual.path)));
      findings.push({ rule: 'virtual-source-shadowed', path: virtual.path });
    }
    files.set(virtual.path, Buffer.from(await panelViewRegistryModule({ root })));
  }
  const nodes = [];
  const edges = [];
  for (const file of [...files.keys()].sort()) {
    const source = files.get(file);
    const node = {
      path: file, sha256: digest(source), origin: file === virtual.path && inputs.has(virtual.graph) ? 'generated' : 'source',
      exports: [],
    };
    if (node.origin === 'generated') node.generatedFrom = virtual.graph;
    nodes.push(node);
    try {
      const observed = moduleSyntax(file, source.toString('utf8'));
      node.exports = observed.exports;
      edges.push(...observed.edges);
    } catch (error) {
      const details = error.errors?.[0];
      const site = details?.location ?? error.loc;
      findings.push({
        rule: 'parse-error', path: file, message: details?.text ?? error.message,
        location: site ? { path: file, line: site.line, column: site.column + 1 } : null,
      });
    }
  }
  const packages = await resolveDependencies(root, files, edges, inputs, virtual);
  const outgoing = new Map(nodes.map(({ path: file }) => [file, []]));
  for (const edge of edges) {
    if (edge.resolution === 'local') outgoing.get(edge.from).push(edge);
    if (['unresolved', 'unscanned-source', 'dynamic-unknown', 'external-reference'].includes(edge.resolution)) findings.push({
      rule: edge.resolution, path: edge.from, specifier: edge.specifier, location: edge.location,
    });
  }
  for (const entry of entries) if (!files.has(entry)) findings.push({ rule: 'missing-entry', path: entry });
  const runtime = closure(entries.filter((entry) => files.has(entry)), outgoing);
  const external = new Map();
  const unconfirmed = new Map();
  const inspected = inspectPanelExternalConsumers({ root, externalConsumers });
  const externalEvidence = inspected.evidence;
  for (const [input, hash] of Object.entries(inspected.inputFiles)) inputs.set(input, hash);
  for (const issue of inspected.findings) {
    findings.push(issue);
    if (!files.has(issue.path)) continue;
    for (const [file] of closure([issue.path], outgoing)) {
      if (!unconfirmed.has(file)) unconfirmed.set(file, new Set());
      unconfirmed.get(file).add(issue.consumer);
    }
  }
  for (const { path: file, consumer } of externalEvidence) {
    if (!files.has(file)) {
      findings.push({ rule: 'missing-external-target', path: file, consumer });
      continue;
    }
    for (const [reached, route] of closure([file], outgoing)) {
      if (!external.has(reached)) external.set(reached, { ...route, consumer });
    }
  }
  const indeterminate = findings.filter(({ rule, path: file }) =>
    ['source-symlink', 'missing-entry'].includes(rule) ||
    (['dynamic-unknown', 'parse-error', 'unscanned-source', 'external-reference'].includes(rule) &&
      (runtime.has(file) || external.has(file))));
  const usage = nodes.map(({ path: file }) => {
    if (runtime.has(file)) return { path: file, status: 'used', evidence: runtime.get(file) };
    if (external.has(file)) return { path: file, status: 'external', evidence: external.get(file) };
    const unknown = [...(unconfirmed.get(file) ?? []), ...indeterminate.map((finding) => finding.path)];
    if (findings.some((finding) => finding.path === file && finding.rule === 'parse-error')) unknown.push(file);
    return unknown.length
      ? { path: file, status: 'unknown', blockers: [...new Set(unknown)].sort() }
      : { path: file, status: 'unused-candidate' };
  });
  const extractor = {
    name: 'esbuild-acorn-panel-observer', esbuild: esbuild.version, acorn: acorn.version,
    node: process.versions.node, sha256: digest(fs.readFileSync(__filename)),
  };
  const inputFiles = Object.fromEntries([...inputs.keys()].sort().map((file) => [file, inputs.get(file)]));
  const sourceFingerprint = digest(JSON.stringify({
    extractor, inputFiles, entries, externalEvidence, files: nodes.map(({ path: file, sha256 }) => [file, sha256]),
    unverifiedExternal: inspected.findings,
    resolution: edges.filter((edge) => edge.resolution).map(({ to, resolution }) => [to, resolution]),
  }));
  return {
    schema: 'figma-flow-observed-panel-v1', sourceFingerprint, extractor, inputFiles,
    entries, externalEvidence, nodes, edges, packages, usage,
    cycles: cyclesFor(outgoing.keys(), outgoing, false),
    cyclesIncludingDynamic: cyclesFor(outgoing.keys(), outgoing, true),
    findings,
  };
}

if (require.main === module) {
  Promise.resolve().then(() => {
    const args = process.argv.slice(2);
    if (args.length === 0) return observePanel();
    if (args.length === 1 && args[0] === '--options-stdin') return observePanel(JSON.parse(fs.readFileSync(0, 'utf8')));
    if (args.length === 1 && args[0] === '--symbols-stdin') return compareModuleSymbols(JSON.parse(fs.readFileSync(0, 'utf8')));
    throw new Error('Usage: node panel-ui/observed-graph.cjs [--options-stdin | --symbols-stdin]');
  }).then((observation) => {
    process.stdout.write(`${JSON.stringify(observation)}\n`);
  }).catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = { compareModuleSymbols, inspectPanelExternalConsumers, observePanel };
