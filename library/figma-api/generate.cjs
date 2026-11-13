// This reads declarations only. It never evaluates Plugin API operations.
const fs = require('node:fs');
const ts = require(process.argv[2] || 'typescript');
if (ts.version !== '5.9.3') throw new Error('Regeneration requires TypeScript 5.9.3');
const file = 'plugin-api.d.ts';
const source = fs.readFileSync(`${__dirname}/${file}`, 'utf8');
const program = ts.createProgram([`${__dirname}/${file}`], {noEmit: true});
const ast = program.getSourceFile(`${__dirname}/${file}`);
const checker = program.getTypeChecker();
const memberIds = new Map();
const declarationNodes = new Map();
if (ast.parseDiagnostics.length) throw new Error('Declaration parse errors');
const declarations = [];
const members = [];
const text = node => node.getText(ast);
const docs = node => (node.jsDoc || []).map(text).join('\n');
const span = node => ({line: ast.getLineAndCharacterOfPosition(node.getStart(ast)).line + 1,
  end_line: ast.getLineAndCharacterOfPosition(node.end).line + 1});
function references(node) {
  const names = new Set();
  function visit(child) {
    if (ts.isTypeReferenceNode(child)) names.add(text(child.typeName));
    ts.forEachChild(child, visit);
  }
  visit(node);
  return [...names].sort();
}
function member(node, owner, ordinal) {
  const name = node.name ? text(node.name).replace(/^['"]|['"]$/g, '') : `[${ts.SyntaxKind[node.kind]}]`;
  const doc = docs(node);
  const restrictionLines = doc.split('\n').filter(line => /only available|must be specified|permission|capabilit|private API|enablePrivatePluginApi|dynamic-page|deprecated/i.test(line));
  const id = `${owner}.${name}#${ordinal}`;
  memberIds.set(node.pos, id);
  members.push({id, owner, name,
    kind: ts.SyntaxKind[node.kind], signature: text(node), documentation: doc,
    readonly: !!node.modifiers?.some(mod => mod.kind === ts.SyntaxKind.ReadonlyKeyword),
    optional: !!node.questionToken, references: references(node),
    value_type: node.type && ts.isTypeReferenceNode(node.type) ? text(node.type.typeName) : null,
    restrictions: restrictionLines.map(line => line.replace(/^\s*\*\s?/, '').trim()),
    ...span(node)});
  if (node.type && ts.isTypeLiteralNode(node.type)) node.type.members.forEach((child, i) => member(child, `${owner}.${name}`, i));
}
function declaration(node, prefix = '') {
  if (ts.isModuleDeclaration(node)) {
    const name = prefix + text(node.name);
    declarations.push({name, kind: 'ModuleDeclaration', documentation: docs(node), ...span(node), extends: [], references: []});
    if (node.body && ts.isModuleBlock(node.body)) node.body.statements.forEach(child => declaration(child, `${name}.`));
    return;
  }
  if (!node.name || !(ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node) || ts.isEnumDeclaration(node) || ts.isFunctionDeclaration(node))) return;
  const name = prefix + text(node.name);
  declarationNodes.set(name, node);
  const bases = (node.heritageClauses || []).flatMap(clause => clause.types.map(type => text(type.expression)));
  declarations.push({name, kind: ts.SyntaxKind[node.kind], documentation: docs(node),
    signature: ts.isTypeAliasDeclaration(node) ? text(node) : null,
    extends: bases, references: references(node), ...span(node)});
  if (node.members) node.members.forEach((child, i) => member(child, name, i));
  else if (node.type && ts.isTypeLiteralNode(node.type)) node.type.members.forEach((child, i) => member(child, name, i));
}
ast.statements.forEach(node => declaration(node));
for (const row of declarations) {
  const node = declarationNodes.get(row.name);
  if (!node || !ts.isInterfaceDeclaration(node)) continue;
  row.effective_member_ids = [...new Set(checker.getPropertiesOfType(checker.getTypeAtLocation(node))
    .flatMap(symbol => (symbol.declarations || []).map(member => memberIds.get(member.pos)).filter(Boolean)))];
  row.heritage_signatures = (node.heritageClauses || []).flatMap(clause => clause.types.map(text));
}

process.stdout.write(JSON.stringify({declarations, members}));
