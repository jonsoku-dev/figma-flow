'use strict';
// Parses source text only; it never loads or evaluates project modules.
const acorn = require('../vendor/acorn/acorn.js');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  const files = JSON.parse(input);
  const result = files.map(({path, text}) => {
    let ast;
    try { ast = acorn.parse(text, {ecmaVersion: 'latest', sourceType: 'module', locations: true, allowHashBang: true}); }
    catch (first) {
      try { ast = acorn.parse(text, {ecmaVersion: 'latest', sourceType: 'script', locations: true, allowHashBang: true, allowReturnOutsideFunction: true}); }
      catch (error) { return {path, refs: [], unknown: [{line: error.loc?.line || 1, reason: 'JavaScript parse error: ' + error.message}]}; }
    }
    const refs = [], unknown = [];
    let shadowed = false;
    function binds(node) {
      if (!node) return false;
      if (node.type === 'Identifier') return node.name === 'require';
      if (node.type === 'RestElement') return binds(node.argument);
      if (node.type === 'AssignmentPattern') return binds(node.left);
      if (node.type === 'ArrayPattern') return node.elements.some(binds);
      if (node.type === 'ObjectPattern') return node.properties.some(p => binds(p.value || p.argument));
      return false;
    }
    function walk(node, visit) {
      if (!node || typeof node !== 'object') return;
      if (node.type) visit(node);
      for (const [key, value] of Object.entries(node)) {
        if (key === 'loc' || key === 'start' || key === 'end') continue;
        if (Array.isArray(value)) value.forEach(v => walk(v, visit));
        else if (value && typeof value === 'object') walk(value, visit);
      }
    }
    walk(ast, n => {
      if ((n.type === 'VariableDeclarator' && binds(n.id)) ||
          (n.type === 'AssignmentExpression' && binds(n.left)) ||
          ((n.type === 'FunctionDeclaration' || n.type === 'FunctionExpression' || n.type === 'ArrowFunctionExpression') && (binds(n.id) || n.params.some(binds))) ||
          (n.type === 'CatchClause' && binds(n.param)) ||
          (n.type === 'ClassDeclaration' && binds(n.id)) ||
          (n.type === 'ImportSpecifier' && binds(n.local)) ||
          (n.type === 'ImportDefaultSpecifier' && binds(n.local)) ||
          (n.type === 'ImportNamespaceSpecifier' && binds(n.local))) shadowed = true;
    });
    function add(arg, n, kind) {
      if (arg?.type === 'Literal' && typeof arg.value === 'string') refs.push([arg.value, n.loc.start.line, kind]);
      else unknown.push({line: n.loc.start.line, reason: 'dynamic ' + kind});
    }
    walk(ast, n => {
      if (n.type === 'CallExpression' && n.callee.type === 'MemberExpression' && !n.callee.computed && n.callee.property.name === 'require') unknown.push({line: n.loc.start.line, reason: 'indirect require'});
      if (n.type === 'ImportDeclaration' || n.type === 'ExportNamedDeclaration' || n.type === 'ExportAllDeclaration') {
        if (n.source) add(n.source, n, 'import');
      } else if (n.type === 'ImportExpression') add(n.source, n, 'import');
      else if (n.type === 'CallExpression' && n.callee.type === 'Identifier' && n.callee.name === 'require') {
        if (shadowed) unknown.push({line: n.loc.start.line, reason: 'require may be shadowed'});
        else if (n.arguments.length === 1) add(n.arguments[0], n, 'require');
        else unknown.push({line: n.loc.start.line, reason: 'dynamic require'});
      }
    });
    return {path, refs, unknown};
  });
  process.stdout.write(JSON.stringify(result));
});
