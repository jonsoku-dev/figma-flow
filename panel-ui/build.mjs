import { build } from 'esbuild';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { panelViewRegistryModule } from './view-registry.mjs';
const plugin = JSON.parse(await readFile(new URL('../plugin.json', import.meta.url), 'utf8'));
const viewRegistrySource = await panelViewRegistryModule();
execFileSync(process.execPath, [fileURLToPath(new URL('build-tokens.mjs', import.meta.url))], { stdio: 'inherit' });
const readLimits = JSON.parse(await readFile(new URL('../library/figma-profile/read-limits.json', import.meta.url), 'utf8'));
if (!Number.isSafeInteger(readLimits.maxNodes) || readLimits.maxNodes < 1) {
  throw new Error('Panel selection limit must be a positive safe integer');
}
const paletteGraph = JSON.parse(await readFile(new URL('../library/panel-design/tokens.json', import.meta.url), 'utf8'));
const tokensById = new Map(paletteGraph.tokens.map((token) => [token.id, token]));
const workbench = paletteGraph.surfaces.find(({ id }) => id === 'panel-workbench');
const metric = (name) => {
  const tokenId = workbench?.metrics?.[name];
  const value = tokensById.get(tokenId)?.light;
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) throw new Error(`Panel workbench metric is invalid: ${name}`);
  return parsed;
};
const resolvePanelTokens = {
  name: 'resolve-panel-media-tokens',
  setup(build) {
    build.onLoad({ filter: /\.css$/ }, async (args) => {
      const source = await readFile(args.path, 'utf8');
      const used = [...source.matchAll(/__PANEL_TOKEN_([a-z][a-z0-9-]*)__/g)];
      if (args.path.endsWith('/relay.css') &&
          source.split('__PANEL_TOKEN_relay-mobile-breakpoint__').length !== 2) {
        throw new Error('Relay breakpoint token marker must occur exactly once');
      }
      let contents = source;
      for (const [, id] of used) {
        const token = tokensById.get(id);
        if (!token || token.kind !== 'breakpoint') throw new Error(`Unknown panel breakpoint token: ${id}`);
        contents = contents.replaceAll(`__PANEL_TOKEN_${id}__`, token.light);
      }
      return contents === source ? null : { contents, loader: 'css' };
    });
  },
};
const common = JSON.parse(await readFile(new URL('../figma-bridge/locales/common.json', import.meta.url), 'utf8'));
const displayName = plugin.extensions['com.openai'].interface.displayName;
const localeCodes = Object.keys(Object.values(common)[0]);
const out = fileURLToPath(new URL('../figma-bridge/assets/', import.meta.url));
await mkdir(out, { recursive: true });
await build({
  entryPoints: [fileURLToPath(new URL('src/app.jsx', import.meta.url))],
  bundle: true,
  outfile: out + '/panels.js',
  minify: true,
  format: 'iife',
  target: 'chrome109',
  charset: 'utf8',
  jsx: 'automatic',
  plugins: [{
    name: 'panel-view-graph',
    setup(build) {
      build.onResolve({ filter: /^\.\/view-registry\.generated\.js$/ }, () => ({
        path: 'panel-view-registry', namespace: 'panel-view-graph',
      }));
      build.onLoad({ filter: /.*/, namespace: 'panel-view-graph' }, () => ({
        contents: viewRegistrySource, loader: 'js', resolveDir: fileURLToPath(new URL('src/', import.meta.url)),
      }));
    },
  }, resolvePanelTokens],
  define: {
    'process.env.NODE_ENV': '"production"',
    __FLOW_DISPLAY_NAME__: JSON.stringify(displayName),
    __FLOW_LOCALES__: JSON.stringify(localeCodes),
    __FLOW_MAX_NODES__: String(readLimits.maxNodes),
    __FLOW_GRAPH_TYPE_PREVIEW_MAX__: String(metric('graphTypePreviewMax')),
    __FLOW_GRAPH_SPACING_PREVIEW_MAX__: String(metric('graphSpacingPreviewMax')),
    __FLOW_DEPENDENCY_GRAPH_MIN_HEIGHT__: String(metric('dependencyGraphMinHeight')),
    __FLOW_DEPENDENCY_GRAPH_ROW_PITCH__: String(metric('dependencyGraphRowPitch')),
    __FLOW_DEPENDENCY_GRAPH_OUTER_PADDING__: String(metric('dependencyGraphOuterPadding')),
    __FLOW_DEPENDENCY_GRAPH_LABEL_LIMIT__: String(metric('dependencyGraphLabelLimit')),
  },
  legalComments: 'external',
  logLevel: 'info',
});
const shellStyles = fileURLToPath(new URL('src/styles/panel-shell.css', import.meta.url));
await build({
  entryPoints: [shellStyles],
  bundle: true,
  outfile: out + '/panel-shell.css',
  minify: true,
  target: 'chrome109',
  charset: 'utf8',
  plugins: [resolvePanelTokens],
  logLevel: 'info',
});
const licenses = await Promise.all(
  ['react', 'react-dom', 'scheduler', 'lucide-react', 'use-sync-external-store', '@tanstack/react-query',
    '@tanstack/query-core', '@tanstack/react-table', '@tanstack/table-core', '@tanstack/react-store', '@tanstack/store'].map(
    async (name) =>
      name +
      '\n' +
      (await readFile(new URL('node_modules/' + name + '/LICENSE', import.meta.url), 'utf8')),
  ),
);
await writeFile(out + '/LICENSES.txt', licenses.join('\n\n'));
