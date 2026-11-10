import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
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
  define: { 'process.env.NODE_ENV': '"production"' },
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
