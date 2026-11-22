import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const graphPath = new URL('../library/panel-design/tokens.json', import.meta.url);
const cssPath = new URL('src/styles/tokens.css', import.meta.url);
const graph = JSON.parse(await readFile(graphPath, 'utf8'));
if (graph.schema !== 'figma-flow-panel-design-graph-v1' || graph.id !== 'panel-design-system') {
  throw new Error('Unsupported panel design graph');
}
const surfaceIds = new Set(graph.surfaces.map(({ id }) => id));
const tokenIds = new Set(graph.tokens.map(({ id }) => id));
const length = /^-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|em|rem|vw|vh|%)$/;
function validValue(token, value) {
  if (typeof value !== 'string' || !value.trim() || /[{};]/.test(value)) return false;
  if (token.kind === 'color') return /^(?:#[0-9a-f]{3,8}|rgb\(29 44 67 \/ 6%\))$/i.test(value);
  if (token.kind === 'shadow') return /^0 2px 8px rgb\(29 44 67 \/ 6%\)$/i.test(value);
  if (token.kind === 'dimension') return value === '0' || length.test(value);
  if (token.kind === 'dimension-list') return value.split(/\s+/).every(part => part === '0' || length.test(part));
  if (token.kind === 'percentage') return /^\d+(?:\.\d+)?%$/.test(value);
  if (token.kind === 'weight') return /^\d{3}$/.test(value) && Number(value) >= 100 && Number(value) <= 900;
  if (token.kind === 'number') return /^\d+(?:\.\d+)?$/.test(value);
  if (token.kind === 'font-family') return /^[\w\s,'-]+$/.test(value);
  if (token.kind === 'breakpoint') return /^\d+(?:\.\d+)?px$/.test(value);
  return false;
}
const validGraph = graph.surfaces.length > 0 && graph.tokens.length > 0 && Array.isArray(graph.edges) &&
  surfaceIds.size === graph.surfaces.length && tokenIds.size === graph.tokens.length &&
  graph.surfaces.every(({ id, title, source }) => typeof id === 'string' && /^[a-z][a-z0-9-]*$/.test(id) &&
    typeof title === 'string' && title && typeof source === 'string' && source) &&
  graph.tokens.every(token => /^[a-z][a-z0-9-]*$/.test(token.id) && typeof token.role === 'string' && token.role &&
    surfaceIds.has(token.surface) && validValue(token, token.light) && validValue(token, token.dark)) &&
  graph.edges.length === graph.tokens.length &&
  JSON.stringify(graph.edges.map(({ from, type, to }) => [from, type, to]).sort()) ===
    JSON.stringify(graph.tokens.map(({ id, surface }) => [surface, 'uses-token', id]).sort());
if (!validGraph) {
  throw new Error('Panel design graph has invalid surface, token, palette or relationship data');
}
const tokenName = (token) => `--${token.id}`;
const declarations = (mode) => graph.tokens.map((token) => `  ${tokenName(token)}: ${token[mode]};`).join('\n');
const darkAliases = graph.tokens.map((token) => `  ${tokenName(token)}-dark: ${token.dark};`).join('\n');
const css = `/* Generated from library/panel-design/tokens.json. */
:root {
  color-scheme: light;
${declarations('light')}
${darkAliases}
}
.figma-dark {
  color-scheme: dark;
${declarations('dark')}
}
`;
if (process.argv.includes('--check')) {
  const current = await readFile(cssPath, 'utf8').catch(() => '');
  if (current !== css) throw new Error('tokens.css is stale or was edited outside the panel design graph');
} else {
  await writeFile(cssPath, css, 'utf8');
}
process.stdout.write(`panel token CSS ${process.argv.includes('--check') ? 'matches' : 'generated'} ${fileURLToPath(graphPath)}\n`);
