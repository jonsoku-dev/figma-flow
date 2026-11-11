import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const esbuild = require('../../../panel-ui/node_modules/esbuild');

await esbuild.build({
  entryPoints: [path.join(root, 'entry.js')],
  outfile: path.join(root, 'runtime.js'),
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'es2020',
});
