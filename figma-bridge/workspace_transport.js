/* Pure control transport. Domain checks stay in workspace_control.js. */
function controlPayloadSize(value, limit) {
  if (value.length > limit) throw Object.assign(Error('Local command payload exceeds its limit'), {code: 'payload-limit-exceeded'});
  let bytes = 0;
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code < 128) bytes++;
    else if (code < 2048) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff && index + 1 < value.length && value.charCodeAt(index + 1) >= 0xdc00 && value.charCodeAt(index + 1) <= 0xdfff) {index++; bytes += 4;}
    else bytes += 3;
    if (bytes > limit) throw Object.assign(Error('Local command payload exceeds its limit'), {code: 'payload-limit-exceeded'});
  }
}
async function controlRequest(route, body) {
  const config = WORKSPACE_CONTROL_CONFIG;
  const origin = config && typeof config.url === 'string' && config.url.match(/^http:\/\/(?:localhost|127\.0\.0\.1):([0-9]{1,5})$/);
  if (!origin || Number(origin[1]) < 1 || Number(origin[1]) > 65535 || typeof config.token !== 'string' || !config.token ||
      !['poll', 'result', 'readiness', 'native-started', 'history', 'history-detail'].includes(route) || !body || typeof body !== 'object' || Array.isArray(body))
    throw Error('Invalid local command endpoint or envelope');
  if (typeof body.readback_json === 'string') controlPayloadSize(body.readback_json, 32 * 1024 * 1024);
  const encoded = JSON.stringify(body);
  controlPayloadSize(encoded, 40 * 1024 * 1024);
  const responseLimit = route === 'history-detail' ? 262144 : 16 * 1024 * 1024;
  let timer;
  try {
    return await Promise.race([
      (async () => {
        const response = await fetch(config.url + '/control/' + route, {
          method: 'POST', headers: {'Authorization': 'Bearer ' + config.token, 'Content-Type':'application/json'}, body: encoded
        });
        if (!response.ok) {
          let reason;
          if (typeof response.json === 'function') {
            try {
              const errBody = await response.json();
              if (errBody && typeof errBody === 'object' && !Array.isArray(errBody) &&
                  typeof errBody.reason === 'string' && /^[a-z0-9-]{1,80}$/.test(errBody.reason)) {
                reason = errBody.reason;
              }
            } catch (_) {}
          }
          throw Object.assign(Error('Local command receipt rejected (' + response.status + ')'), {
            status: response.status,
            ...(reason ? {reason} : {})
          });
        }
        const contentLength = response.headers && typeof response.headers.get === 'function' ? response.headers.get('Content-Length') : null;
        if (typeof contentLength === 'string' && /^[0-9]{1,12}$/.test(contentLength.trim()) && Number(contentLength.trim()) > responseLimit) {
          throw Object.assign(Error('Local command payload exceeds its limit'), {code: 'payload-limit-exceeded'});
        }
        const value = await response.json();
        controlPayloadSize(JSON.stringify(value), responseLimit);
        return value;
      })(),
      new Promise((_, reject) => {timer = setTimeout(() => reject(Object.assign(Error('Local command request timed out'), {code: 'request-timeout'})), 15000);})
    ]);
  } finally {clearTimeout(timer);}
}
