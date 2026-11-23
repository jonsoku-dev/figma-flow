<!-- Generated from tools/maintenance-contract.json -->
# Panel boundaries

Change [the maintenance contract](../../tools/maintenance-contract.json) to update these boundaries.

- The panel bundle starts at `panel-ui/src/app.jsx`.
- `reviewTransport.mjs` owns network access through `EventSource`, `WebSocket`, `XMLHttpRequest`, `fetch`, `sendBeacon`.
- `app.jsx` owns native messages through `postMessage`.
- Panel modules cannot import Node built-ins, remote URLs or the packages `axios`, `undici`.
- Imports outside the panel source directory require an explicit contract binding.

| Panel module | Allowed external import |
| --- | --- |
| `DiagnosticExport.jsx` | `../../figma-bridge/audit_log.js` |
| `panelContracts.mjs` | `../../figma-bridge/chat-input.json` |
| `panelContracts.mjs` | `../../library/panel-design/contracts.json` |
| `panelContracts.mjs` | `../../library/panel-design/tokens.json` |
| `panelContracts.mjs` | `../../specs/workspace-activity/graph.json` |

## Offline panel artifacts

| Role | Generated file |
| --- | --- |
| `bundleStyle` | `figma-bridge/assets/panels.css` |
| `legalComments` | `figma-bridge/assets/panels.js.LEGAL.txt` |
| `licenses` | `figma-bridge/assets/LICENSES.txt` |
| `script` | `figma-bridge/assets/panels.js` |
| `shellStyle` | `figma-bridge/assets/panel-shell.css` |
