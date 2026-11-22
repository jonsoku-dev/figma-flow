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
const relayBreakpoint = paletteGraph.tokens.find(({ id }) => id === 'relay-mobile-breakpoint')?.light;
const relayStylePath = fileURLToPath(new URL('src/styles/relay.css', import.meta.url));
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
  }, {
    name: 'resolve-panel-media-token',
    setup(build) {
      build.onLoad({ filter: /relay\.css$/ }, async (args) => {
        if (args.path !== relayStylePath) return null;
        const source = await readFile(args.path, 'utf8');
        const marker = '__PANEL_TOKEN_relay-mobile-breakpoint__';
        if (!relayBreakpoint || source.split(marker).length !== 2) {
          throw new Error('Relay breakpoint token marker must occur exactly once');
        }
        return { contents: source.replace(marker, relayBreakpoint), loader: 'css' };
      });
    },
  }],
  define: {
    'process.env.NODE_ENV': '"production"',
    __FLOW_DISPLAY_NAME__: JSON.stringify(displayName),
    __FLOW_LOCALES__: JSON.stringify(localeCodes),
    __FLOW_MAX_NODES__: String(readLimits.maxNodes),
  },
  legalComments: 'external',
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
