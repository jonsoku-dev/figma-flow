'use strict';

const fs = require('node:fs');
const path = require('node:path');
const acorn = require('../vendor/acorn/acorn.js');
const { transformSync } = require('esbuild');
const { panelBoundaries } = require('../tools/maintenance-contract.json');
const networkGlobals = new Set(['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'sendBeacon']);

function checkSource(file, source) {
  const loader = file.endsWith('.jsx') ? 'jsx' : 'js';
  const { code } = transformSync(source, { loader, jsx: 'automatic' });
  const root = acorn.parse(code, { ecmaVersion: 'latest', sourceType: 'module' });
  const findings = new Set();
  const visit = (node) => {
    if (!node || typeof node !== 'object') return;
    const name = node.type === 'Identifier' ? node.name : node.type === 'Literal' ? node.value : null;
    if (networkGlobals.has(name) && file !== panelBoundaries.networkOwner) {
      findings.add('Network access bypasses local pairing. Use reviewTransport.mjs for prepared review delivery.');
    }
    if (name === 'postMessage' && file !== panelBoundaries.bridgeOwner) {
      findings.add('Direct host messages bypass panel routing. Use the send callback supplied by app.jsx.');
    }
    if ((node.type === 'ImportDeclaration' || node.type === 'ImportExpression' ||
        node.type === 'ExportNamedDeclaration' || node.type === 'ExportAllDeclaration') && node.source) {
      const target = node.source.value;
      const outside = typeof target === 'string' && target.startsWith('.') &&
        path.posix.normalize(path.posix.join(path.posix.dirname(file), target)).startsWith('../');
      if (typeof target !== 'string' || target.startsWith('node:') || /^https?:/.test(target) ||
          ['fs','http','https','net','child_process','axios','undici'].includes(target) ||
          (outside && !(panelBoundaries.externalImports[file] || []).includes(target))) {
        findings.add('Panel dependency crosses its source boundary. Use a local view module or a declared panel contract.');
      }
    }
    for (const child of Object.values(node)) {
      if (Array.isArray(child)) child.forEach(visit);
      else if (child && typeof child === 'object') visit(child);
    }
  };
  visit(root);
  return [...findings];
}

function checkPanel(root = path.join(__dirname, 'src')) {
  function walk(directory) {
    return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) return walk(file);
      if (!entry.isFile() || !/\.(?:m?js|jsx)$/.test(file)) return [];
      const relative = path.relative(root, file).split(path.sep).join('/');
      return checkSource(relative, fs.readFileSync(file,'utf8')).map(reason => `${relative}: ${reason}`);
    });
  }
  return walk(root).sort();
}

if (require.main === module) {
  const findings = checkPanel();
  for (const issue of findings) console.error(issue);
  process.exitCode = Number(findings.length > 0);
}

module.exports = { checkSource, checkPanel };
