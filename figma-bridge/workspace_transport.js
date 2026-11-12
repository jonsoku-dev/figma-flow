/* Pure control transport. Domain checks stay in workspace_control.js. */
async function controlRequest(route, body) {
  const config = WORKSPACE_CONTROL_CONFIG;
  const response = await fetch(config.url + '/control/' + route, {
    method: 'POST', headers: {'Authorization': 'Bearer ' + config.token, 'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if (!response.ok) throw Error('Local command receipt rejected (' + response.status + ')');
  return response.json();
}
