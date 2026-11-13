const fs = require('node:fs');
const ts = require(process.argv[2] || 'typescript');
if (ts.version !== '5.9.3') throw new Error('Coverage requires TypeScript 5.9.3');
const sources = JSON.parse(fs.readFileSync(0, 'utf8'));
const references = [];
function pathOf(node) {
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isPropertyAccessExpression(node)) {
    const parent = pathOf(node.expression);
    return parent && `${parent}.${node.name.text}`;
  }
  if (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression)) {
    const parent = pathOf(node.expression);
    return parent && `${parent}.${node.argumentExpression.text}`;
  }
  return null;
}
for (const source of sources) {
  const ast = ts.createSourceFile(source.path, source.text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  if (ast.parseDiagnostics.length) throw new Error(`Cannot parse coverage source: ${source.path}`);
  function visit(node) {
    if (ts.isPropertyAccessExpression(node) || (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression))) {
      const path = pathOf(node);
      const name = ts.isPropertyAccessExpression(node) ? node.name.text : node.argumentExpression.text;
      const position = ast.getLineAndCharacterOfPosition(node.getStart(ast));
      references.push({path: source.path, line: position.line + 1, column: position.character + 1,
        name, qualified: path && path.startsWith('figma.') ? path : null,
        syntax: node.getText(ast), usage: ts.isCallExpression(node.parent) && node.parent.expression === node ? 'call-expression' : 'property-reference'});
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
}
process.stdout.write(JSON.stringify(references));
