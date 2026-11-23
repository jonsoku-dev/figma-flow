import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { panelViewRegistry, panelViewRegistryModule } from './view-registry.mjs';
import { checkPanel } from './architecture.cjs';
import { panelTokenCss } from './build-tokens.mjs';
import maintenance from '../tools/maintenance-contract.json' with { type: 'json' };

const [flag, destination, ...unexpected] = process.argv.slice(2);
if (flag !== undefined && (flag !== '--output-root' || !destination || unexpected.length)) {
  throw new Error('Usage: node panel-ui/build.mjs [--output-root <directory>]');
}
const outputRoot = destination ? resolve(destination) : fileURLToPath(new URL('../', import.meta.url));
const panelSource = fileURLToPath(new URL('src/', import.meta.url));
const sourceTokenCss = join(panelSource, 'styles/tokens.css');
const generatedTokenCss = join(outputRoot, 'panel-ui/src/styles/tokens.css');
const out = join(outputRoot, 'figma-bridge/assets');
const artifacts = maintenance.panelArtifacts;
for (const [role, extension] of [['script', 'js'], ['shellStyle', 'css'], ['licenses', 'txt']]) {
  if (typeof artifacts?.[role] !== 'string' || !new RegExp(`^[A-Za-z0-9][A-Za-z0-9_.-]*\\.${extension}$`).test(artifacts[role])) {
    throw new Error(`Invalid panel artifact filename for ${role}`);
  }
}

const boundaryFailures = checkPanel();
if (boundaryFailures.length) throw new Error(boundaryFailures.join('\n'));

const plugin = JSON.parse(await readFile(new URL('../plugin.json', import.meta.url), 'utf8'));
const viewRegistrySource = await panelViewRegistryModule();
const viewRegistryFilter = new RegExp('^' + panelViewRegistry.specifier.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$');
await mkdir(dirname(generatedTokenCss), { recursive: true });
await writeFile(generatedTokenCss, panelTokenCss, 'utf8');
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
    build.onResolve({ filter: /^\.\/tokens\.css$/ }, (args) => {
      if (resolve(args.resolveDir, args.path) === sourceTokenCss) return { path: generatedTokenCss };
      return null;
    });
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
await mkdir(out, { recursive: true });
await build({
  entryPoints: [join(panelSource, maintenance.panelBoundaries.entry)],
  bundle: true,
  outfile: join(out, artifacts.script),
  minify: true,
  format: 'iife',
  target: 'chrome109',
  charset: 'utf8',
  jsx: 'automatic',
  plugins: [{
    name: 'panel-view-graph',
    setup(build) {
      build.onResolve({ filter: viewRegistryFilter }, () => ({
        path: 'panel-view-registry', namespace: 'panel-view-graph',
      }));
      build.onLoad({ filter: /.*/, namespace: 'panel-view-graph' }, () => ({
        contents: viewRegistrySource, loader: 'js', resolveDir: panelSource,
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
  outfile: join(out, artifacts.shellStyle),
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
await writeFile(join(out, artifacts.licenses), licenses.join('\n\n'));
