/* Pure control transport. Domain checks stay in workspace_control.js. */
function controlPayloadSize(value, limit) {
  if (value.length > limit) throw Error('Local command payload exceeds its limit');
  let bytes = 0;
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code < 128) bytes++;
    else if (code < 2048) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff && index + 1 < value.length && value.charCodeAt(index + 1) >= 0xdc00 && value.charCodeAt(index + 1) <= 0xdfff) {index++; bytes += 4;}
    else bytes += 3;
    if (bytes > limit) throw Error('Local command payload exceeds its limit');
  }
}
async function controlRequest(route, body) {
  const config = WORKSPACE_CONTROL_CONFIG;
  const origin = config && typeof config.url === 'string' && config.url.match(/^http:\/\/(?:localhost|127\.0\.0\.1):([0-9]{1,5})$/);
  if (!origin || Number(origin[1]) < 1 || Number(origin[1]) > 65535 || typeof config.token !== 'string' || !config.token ||
      !['poll', 'result', 'readiness', 'native-started', 'history'].includes(route) || !body || typeof body !== 'object' || Array.isArray(body))
    throw Error('Invalid local command endpoint or envelope');
  if (typeof body.readback_json === 'string') controlPayloadSize(body.readback_json, 32 * 1024 * 1024);
  const encoded = JSON.stringify(body);
  controlPayloadSize(encoded, 40 * 1024 * 1024);
  let timer;
  try {
    return await Promise.race([
      (async () => {
        const response = await fetch(config.url + '/control/' + route, {
          method: 'POST', headers: {'Authorization': 'Bearer ' + config.token, 'Content-Type':'application/json'}, body: encoded
        });
        if (!response.ok) throw Error('Local command receipt rejected (' + response.status + ')');
        const value = await response.json();
        controlPayloadSize(JSON.stringify(value), 16 * 1024 * 1024);
        return value;
      })(),
      new Promise((_, reject) => {timer = setTimeout(() => reject(Error('Local command request timed out')), 15000);})
    ]);
  } finally {clearTimeout(timer);}
}
