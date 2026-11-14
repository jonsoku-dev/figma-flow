# P1 Acceptance Receipt (`p1-causal-review-history` Verified; `p1-native-component-families` Pending)

- **Canonical Graph Status:** [backlog.graph.json](backlog.graph.json) is the single source of truth for node status and `next-ready` computation:
  - `p1-causal-review-history` (**NF-03**): `verified` (`evidence_status`: `verified-with-public-receipt-and-live-panel-acceptance`)
  - `p1-native-component-families` (**NF-01**): `proposed` (awaiting live Figma Desktop edit/readback acceptance and final frozen SHA)
- **Review Contracts:** [capability-review.md#p1-causal-history](capability-review.md#p1-causal-history) · [capability-review.md#p1-component-families](capability-review.md#p1-component-families)
- **Feature Specs:** [NF-03-causal-history.md](NF-03-causal-history.md) · [NF-01-component-families.md](NF-01-component-families.md)
- **Roadmap Entry Point:** [README.md](README.md)

---

## 1. `p1-causal-review-history` (NF-03) — Verified

### Product Source Pins

- **Read-only exact-scope backend projection (`3e7b44c`, `e7b1efb`):**
  - `3e7b44cc9903b3bfc753b77797e96c2c831dcd5b`: [tools/figma_control.py](../../tools/figma_control.py) (`history_detail`) · [tools/operation_detail.py](../../tools/operation_detail.py) (`figma-flow-operation-detail-v1`)
  - `e7b1efbda8fcbe78bec9aa77d480daa0438c1039`: [tests/test_operation_detail.py](../../tests/test_operation_detail.py) · [tools/operation_detail.py](../../tools/operation_detail.py) (`_extract_sync_map`)
- **Bridge scope relay & bidirectional relation preservation (`ce1bc7d`):**
  - `ce1bc7d2988a7247f61cbf8fd827ed0278e0964d`: [figma-bridge/workspace_control.js](../../figma-bridge/workspace_control.js) · [figma-bridge/workspace_host.js](../../figma-bridge/workspace_host.js) · [figma-bridge/workspace_transport.js](../../figma-bridge/workspace_transport.js) · [tests/nf03_history_detail.cjs](../../tests/nf03_history_detail.cjs)
- **Read-only panel UI, accessibility & bundle (`016a777`):**
  - `016a777e0bc582414c2062a122dfae553851eefc`: [panel-ui/src/operationDetail.mjs](../../panel-ui/src/operationDetail.mjs) · [panel-ui/src/Workspace.jsx](../../panel-ui/src/Workspace.jsx) · [panel-ui/src/styles/workspace.css](../../panel-ui/src/styles/workspace.css) · [figma-bridge/locales/workspace.json](../../figma-bridge/locales/workspace.json) · [tests/test_nf03_panel_ui.cjs](../../tests/test_nf03_panel_ui.cjs)
- **Contract spec alignment (`4e2539e`):** [NF-03-causal-history.md](NF-03-causal-history.md)
- **Note on source freeze:** Product source commits (`3e7b44c`, `e7b1efb`, `ce1bc7d`, `016a777`) were verified live on the pre-freeze runtime (`cfc7fbd` loaded with matching runtime generation); final frozen-main hash re-check will be recorded when NF-01 lands.

### Observed Live Figma & Panel Acceptance Evidence

1. **Pre-condition & Fail-Closed Native Boundary (Unconcealed Initial Rejection):**
   - On the registered Figma Design P1 test page, targeting an initial vanilla `FRAME` failed cleanly without mutating the canvas or fabricating a fake component diff.
   - Converting to the project's own `MAIN` native component, reading the fresh native IDs, and executing two exact revisions under the same task (`p1-nf03-radius-component`, local component `borderRadius` `0 -> 8 -> 16`) succeeded.
2. **Exact-Scope Two-Revision Causal Diff & Signed Execution Pins:**
   - First exact apply pin: `task_key = p1-nf03-radius-component`, `operation_id = e5815c0cd1ec6b2269d4136ebdecb9e0`, `revision = 5f045fd98322d5c4b6995869bfd753e2911c10e1084db465216e2a7f0c1030b7`.
   - Second exact apply pin: `task_key = p1-nf03-radius-component`, `operation_id = 2a0985ec89ee69e76dff56329bd9b8da`, `revision = 5d47eb63edaef932929f8a618610288a5e5b4fea4c52ec8631db235048cf49b1`.
   - Observed field diff from server & read-only native panel: `target:node#1`, field `borderRadius`, `kind = "changed"`, `before = 8`, `after = 16`.
3. **Explicit Predecessor Link, Backstack, Scope Change Invalidation & Keyboard Accessibility:**
   - Native panel read-only detail view rendered the `before: 8` -> `after: 16` diff and linked the explicit same-page predecessor discover artifact pin; opening the predecessor detail and navigating back returned to the radius diff detail via the panel backstack.
   - Switching the active Figma Design page invalidated the previously loaded detail after the asynchronous poll (`1`-poll cycle), cleared stale detail content, and surfaced a stale-reselect notice.
   - Keyboard `Enter` opened the selected row detail, and `Back` restored focus to the invoking row.
4. **Read-Only Zero-Write Guarantee, Negative Routes & Sanitization:**
   - Canonical request and receipt files (`1,226` files checked) remained byte-identical across real detail queries (`detail_endpoint_did_not_write_canonical_requests_or_receipts = true`).
   - All contracted negative HTTP checks (`401`, `404`, `409` on missing scope / mismatched runtime / mismatched task-revision) passed cleanly.
   - Diff payload omitted raw user text, private filesystem paths, bearer tokens, and raw internal Figma file/page/node IDs; the full private raw detail response receipt remains excluded from Git.

### Automated Repository Verification (Observed on `records` `HEAD`)

- `python3 -B -m unittest tests.test_operation_detail`: **6/6 OK**
- `python3 -B -m unittest discover -s tests -p 'test_rd08_*.py'` & `tests.test_rd03_task_dependencies`: **3/3 OK** (and **1,309/1,312** across full `unittest discover -s tests` on identical code, where `2` skipped and `1` failure in `test_finalize_history_scope.py` was solely due to `panel-ui/node_modules/esbuild` not being installed locally)
- `node --test tests/nf03_history_detail.cjs tests/test_workspace_activity.cjs`: **9/9 pass** (`7 + 2`)
- **Boundary note on `esbuild`-dependent panel checks:** `tests/test_nf03_panel_ui.cjs`, `tests/test_workspace_host.cjs`, and `npm --prefix panel-ui run build` require `panel-ui/node_modules` (`esbuild`), which is omitted in bare offline checkouts and executed in CI (`.github/workflows/test.yml`).

---

## 2. `p1-native-component-families` (NF-01) — Pending (`proposed`)

- NF-01 stays `proposed` in [backlog.graph.json](backlog.graph.json) until live Figma Desktop edit/readback acceptance and the final frozen integrated receipt are delivered.

---

## Public Disclosure Boundaries

- Figma file keys, page IDs, node IDs, personal filesystem paths, bearer/API tokens, and raw private detail dumps remain excluded from public documentation and Git history.
