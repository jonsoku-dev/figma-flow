import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const plugin = JSON.parse(await readFile(new URL('../plugin.json', import.meta.url), 'utf8'));
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
  define: {
    'process.env.NODE_ENV': '"production"',
    __FLOW_DISPLAY_NAME__: JSON.stringify(displayName),
    __FLOW_LOCALES__: JSON.stringify(localeCodes),
  },
  legalComments: 'external',
  logLevel: 'info',
});
const licenses = await Promise.all(
  ['react', 'react-dom', 'scheduler', 'lucide-react'].map(
    async (name) =>
      name +
      '\n' +
      (await readFile(new URL('node_modules/' + name + '/LICENSE', import.meta.url), 'utf8')),
  ),
);
await writeFile(out + '/LICENSES.txt', licenses.join('\n\n'));
