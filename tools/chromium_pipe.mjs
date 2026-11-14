// Private headless Chromium driven over --remote-debugging-pipe. Shared by the web capture CLIs.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as pause } from 'node:timers/promises';

function connect(proc) {
  let seq = 0;
  let buf = '';
  const requests = new Map();
  proc.stdio[4].setEncoding('utf8').on('data', chunk => {
    buf += chunk;
    let i;
    while ((i = buf.indexOf('\0')) >= 0) {
      const msg = JSON.parse(buf.slice(0, i));
      buf = buf.slice(i + 1);
      const pending = requests.get(msg.id);
      if (pending) {
        requests.delete(msg.id);
        clearTimeout(pending.timer);
        if (msg.error) pending.reject(Error(msg.error.message));
        else pending.resolve(msg.result);
      }
    }
  });
  function abort(error) {
    for (const { reject, timer } of requests.values()) { clearTimeout(timer); reject(error); }
    requests.clear();
  }
  proc.on('error', abort);
  proc.once('exit', () => abort(Error('Chromium exited before capture completed')));
  return (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { requests.delete(id); reject(Error('Chromium timed out at ' + method)); }, 20000);
    if (proc.exitCode !== null || proc.signalCode !== null || proc.stdio[3].destroyed) {
      clearTimeout(timer);
      reject(Error('Chromium is no longer running'));
      return;
    }
    requests.set(id, { resolve, reject, timer });
    proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + '\0');
  });
}

export function chromiumBinary(explicit) {
  const binary = explicit || process.env.CHROME_BIN ||
    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/chromium', '/usr/bin/google-chrome',
     process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google/Chrome/Application/chrome.exe')].filter(Boolean).find(existsSync);
  if (!binary) throw Error('Specify the installed Chromium executable with --chrome');
  return binary;
}

/** Run `body` with one attached page in a throwaway profile; the browser and profile are always removed. */
export async function withChromiumPage(binary, body) {
  const profile = await mkdtemp(path.join(os.tmpdir(), 'figma-flow-chromium-'));
  const proc = spawn(binary, ['--headless=new', '--remote-debugging-pipe', '--no-first-run',
    '--no-default-browser-check', '--user-data-dir=' + profile, 'about:blank'], { stdio: ['ignore','ignore','ignore','pipe','pipe'] });
  const send = connect(proc);
  try {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const command = (method, params) => send(method, params, sessionId);
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
      return result.result.value;
    };
    const { product } = await send('Browser.getVersion');
    return await body({ command, evaluate, product });
  } finally {
    await send('Browser.close').catch(()=>{});
    if(proc.exitCode===null && proc.signalCode===null) await Promise.race([new Promise(resolve=>proc.once('exit',resolve)),pause(2000)]);
    if(proc.exitCode===null && proc.signalCode===null) proc.kill();
    await rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:150});
  }
}

export async function until(read, end, error) {
  while (Date.now() < end) {
    const value = await read();
    if (value) return value;
    await pause(90);
  }
  throw Error(error);
}
