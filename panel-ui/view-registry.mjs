import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PANEL_UI = path.dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = path.resolve(PANEL_UI, '..');
const GRAPH_RELATIVE = 'library/panel-design/views.json';
const ROLE_LIFECYCLE = Object.freeze({
  'registered-home': 'active',
  task: 'active',
  standalone: 'legacy',
});

export async function panelViewRegistryModule({ root = REPOSITORY_ROOT, graphPath } = {}) {
  root = path.resolve(root);
  graphPath = path.resolve(graphPath || path.join(root, GRAPH_RELATIVE));
  const graph = JSON.parse(await readFile(graphPath, 'utf8'));
  if (graph.schema !== 'figma-flow-panel-view-graph-v1' || graph.version !== 1 ||
      !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    throw new Error('Unsupported panel view graph');
  }

  const nodes = new Map();
  for (const node of graph.nodes) {
    if (!node || typeof node.id !== 'string' || !node.id || nodes.has(node.id)) {
      throw new Error('Panel view graph contains an invalid or duplicate node ID');
    }
    nodes.set(node.id, node);
  }

  const screens = graph.nodes.filter((node) => node.type === 'screen');
  const homeCount = screens.filter((node) => node.role === 'registered-home').length;
  if (homeCount !== 1) throw new Error('Panel view graph must define exactly one registered-home route');

  const imports = [];
  const entries = [];
  for (const [index, view] of screens.entries()) {
    if (!/^[a-z][a-z0-9-]*$/.test(view.id) || !ROLE_LIFECYCLE[view.role] ||
        view.lifecycle !== ROLE_LIFECYCLE[view.role] || typeof view.locale !== 'string' || !view.locale) {
      throw new Error(`Invalid panel view ID, role or lifecycle: ${view.id}`);
    }
    const implementations = graph.edges.filter((edge) => edge?.from === view.id && edge.type === 'implemented by');
    if (implementations.length !== 1) {
      throw new Error(`Panel view requires exactly one React implementation edge: ${view.id}`);
    }
    const implementation = nodes.get(implementations[0].to);
    if (implementation?.type !== 'code' || typeof implementation.source !== 'string') {
      throw new Error(`Panel view React implementation is missing: ${view.id}`);
    }
    const source = path.resolve(path.dirname(graphPath), implementation.source);
    const sourceRelative = path.relative(root, source);
    const panelRelative = path.relative(path.join(root, 'panel-ui/src'), source);
    if (!sourceRelative || sourceRelative.startsWith('..') || path.isAbsolute(sourceRelative) ||
        !panelRelative || panelRelative === '..' || panelRelative.startsWith(`..${path.sep}`) ||
        path.isAbsolute(panelRelative) || path.extname(source) !== '.jsx' || !existsSync(source)) {
      throw new Error(`Panel view React source is missing or outside panel-ui/src: ${implementation.source}`);
    }
    let importPath = path.relative(path.join(root, 'panel-ui/src'), source).split(path.sep).join('/');
    if (!importPath.startsWith('.')) importPath = `./${importPath}`;
    const symbol = `PanelView${index}`;
    imports.push(`import ${symbol} from ${JSON.stringify(importPath)};`);
    entries.push(`${JSON.stringify(view.id)}: ${symbol}`);
  }
  if (!screens.length) throw new Error('Panel view graph has no screen routes');
  return `${imports.join('\n')}\nexport const views = Object.freeze({${entries.join(',')}});\n`;
}
