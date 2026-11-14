# P1 Acceptance Receipt (`p1-causal-review-history` & `p1-native-component-families` Verified)

- **Canonical Graph Status:** [backlog.graph.json](backlog.graph.json) is the single source of truth for node status and `next-ready` computation:
  - `p1-causal-review-history` (**NF-03**): `verified` (`evidence_status`: `verified-with-public-receipt-and-live-panel-acceptance`)
  - `p1-native-component-families` (**NF-01**): `verified` (`evidence_status`: `verified-with-public-receipt-and-native-readback`)
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
- **Note on source freeze:** Product source commits (`3e7b44c`, `e7b1efb`, `ce1bc7d`, `016a777`) were verified live on the pre-freeze runtime (`cfc7fbd` loaded with matching runtime generation); NF-03 unit and bridge regression suites continued passing through `974b5de`.

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

### Automated Repository Verification (NF-03)

- `python3 -B -m unittest tests.test_operation_detail`: **6/6 OK**
- `python3 -B -m unittest discover -s tests -p 'test_rd08_*.py'` & `tests.test_rd03_task_dependencies`: **3/3 OK**
- `node --test tests/nf03_history_detail.cjs tests/test_workspace_activity.cjs`: **9/9 pass** (`7 + 2`)
- **Boundary note on `esbuild`-dependent panel checks:** `tests/test_nf03_panel_ui.cjs`, `tests/test_workspace_host.cjs`, and `npm --prefix panel-ui run build` require `panel-ui/node_modules` (`esbuild`), which is omitted in bare offline checkouts and executed in CI (`.github/workflows/test.yml`).

---

## 2. `p1-native-component-families` (NF-01) — Verified

### Product Source Pins

- **Core compiler, bridge validation & selective CAS sync (`ad26c90`, `fd1a9d2`):**
  - `ad26c908c5db034ef58d253e4c125df3e2afe469`: [tools/design_system.py](../../tools/design_system.py) · [tools/figma_bridge.py](../../tools/figma_bridge.py) · [tests/test_component_families.py](../../tests/test_component_families.py)
  - `fd1a9d28551e9101fa5f5bc1e0d42570b385aa31`: [NF-01-component-families.md](NF-01-component-families.md) · [figma-bridge/graph_token_sync.js](../../figma-bridge/graph_token_sync.js) · [tools/graph_design_system.py](../../tools/graph_design_system.py) · [tools/graph_sync.py](../../tools/graph_sync.py)
- **App opt-in target mapping & owned six-family handoff example (`13c36f8`, `b402782`, `baac57e`):**
  - `13c36f870bcca606cde9ba15a5cb238e2c3cc9b6` / `b40278221d8c023249462cd628edbdc51c0b041f` / `baac57eb1582698d4cdfef2cbf63b2c34d3ba9fd`: [apps/little-hands/design/source.py](../../apps/little-hands/design/source.py) · [examples/owned-component-families/README.md](../../examples/owned-component-families/README.md) · [tests/test_nf01_app_mapping.py](../../tests/test_nf01_app_mapping.py)
- **Native plugin importer, additive semantic workbench & scope-pinned provision CLI (`cfc7fbd`, `709f110`, `8af6db4`, `f9ba897`):**
  - `cfc7fbd1a2867d2665c29e9eaa066b4b18eac254`: [figma-bridge/code.js](../../figma-bridge/code.js) · [tests/nf01_component_properties.cjs](../../tests/nf01_component_properties.cjs)
  - `709f11042d3aa621dd47a064168828f6aa4f828d` / `f9ba8978d04dcee8164d9f8f78b4f942fcbadd3d`: [figma-bridge/semantic_components.js](../../figma-bridge/semantic_components.js) · [tests/nf01_semantic_family_runtime.cjs](../../tests/nf01_semantic_family_runtime.cjs)
  - `8af6db43123e03bdf6b28456944243cf487da3fd`: [tools/family_provision.py](../../tools/family_provision.py) · [figma-bridge/native_provision.js](../../figma-bridge/native_provision.js) · [tests/test_family_provision.py](../../tests/test_family_provision.py) · [tests/test_family_provision_runtime.cjs](../../tests/test_family_provision_runtime.cjs)
- **Duplicate/auto-renamed native key repair & top-level rollback (`63b3555`, `578ffc3`, `974b5de` + official gate `437aa048` -> `3e3f4e42`):**
  - `63b355586fdd2cc9df5c7324980d490d393b543c`: [figma-bridge/native_provision.js](../../figma-bridge/native_provision.js) · [tests/test_family_provision_runtime.cjs](../../tests/test_family_provision_runtime.cjs)
  - `578ffc3c51ae6e9664f03c6f71ae3d1c18a922ec`: [tests/test_property_repair_regression.cjs](../../tests/test_property_repair_regression.cjs)
  - `974b5de74bc99d645926afd5595f21f155356203`: [figma-bridge/code.js](../../figma-bridge/code.js) · [figma-bridge/semantic_components.js](../../figma-bridge/semantic_components.js)
- **Recipe bundle & API coverage baseline alignment (`a7378b8`):**
  - [library/figma-recipes/build.py](../../library/figma-recipes/build.py) · [library/figma-recipes/bundle.json](../../library/figma-recipes/bundle.json) · [library/figma-recipes/component-properties.helpers.js](../../library/figma-recipes/component-properties.helpers.js) · [library/figma-recipes/bundled/design-component-properties.js](../../library/figma-recipes/bundled/design-component-properties.js) · [library/figma-api/coverage-baseline.json](../../library/figma-api/coverage-baseline.json)
- **Frozen cross-language readback tests & Python comparator alignment (`f88643b`, `e6f4fd8`):**
  - `f88643bcb99f060f1f9af09e618bc3491c5e8f02`: [tests/test_bridge_declared_property_compare.py](../../tests/test_bridge_declared_property_compare.py)
  - `e6f4fd848a11cd292d9f8d9f50dad54ccb53ea10`: [tools/figma_bridge.py](../../tools/figma_bridge.py) (`compare_declared_component_properties`)

### Observed Live Figma Acceptance Evidence (NF-01)

1. **Initial Duplicate-Name Failure & Clean Rollback (Unconcealed):**
   - The first live apply encountered a duplicate display-name native collision where the native prefix was not retained uniquely; execution rolled back cleanly with zero residual owned nodes on the page (emitting only the earlier child duplicate `.remove()` diagnostic) and left the pre-existing `MAIN` component (`radius = 16`) untouched.
   - Repairs landed in `63b3555`, `578ffc3`, and `974b5de` (unique collision-safe native property keys while preserving logical property contracts and top-level-only rollback root removal), passing the independent improvement gate (`base = 437aa0485e85dd2e2dcef621f570847317759b63` -> `target = 3e3f4e42b884cb64cc32c9d9f5d9173ec8bbb550`, `NODE-REPAIR-RC` 12/12 + `PY-REPAIR-RC` 1/1).
   - Python `compare_declared_component_properties` was subsequently aligned in `e6f4fd8` (with frozen Node-to-Python snapshot tests in `f88643b`) so collision-safe and Figma-normalized `#suffix` keys in `componentPropertyDefinitions` and `declared_property_contracts` verify cleanly.
2. **Final Real Figma Apply, Edit, Repeat Apply & Readback (`real_figma = true`, `readback_status = "present"`):**
   - Installed own plugin rendered `6` canonical component sets, `19` variants, and `8` top-level instances (`actual_node_count = 108`) with unique final native `#suffix` property keys and `stable_main_and_instance_ids = true`.
   - Manual edits on one top-level instance:
     - `TEXT` (`label`): `"Reviewed attendee"`
     - `BOOLEAN` (`showHelp`): `false`
     - `INSTANCE_SWAP` (`control_family`): `"checkbox"`
     - Position moved to `x = 60`, `y = 48` (`relativeTransform = [[1, 0, 60], [0, 1, 48]]`).
   - `after-edit -> repeat apply -> after-read` confirmed:
     - Selected 3 property actual keys/values and `(x=60, y=48)` placement survived repeat apply (`repeat_preserved_edited_values = true`).
     - Recompiling from `main` `a7378b8` and running real native repeat/read on a fresh revision of the same task matched staged family metadata identically and preserved user props and placement (`main_recompiled_repeat_exactly_matches = true`; JS runtime files remained unchanged through `e6f4fd8`).
     - Top-level and main/instance IDs remained stable (`full_node_ids_stable_after_manual_swap = true`); deliberately swapping the nested `INSTANCE_SWAP` control replaced only the `3` inner swapped child IDs inside that manually swapped instance (`ids_changed_only_inside_manually_swapped_instance = 3`, expected swap semantics).
     - The remaining `7` sibling instances (`unchanged_other_instances = 7`) and the pre-existing `MAIN` component (`radius = 16`, `own_original_component_unchanged = true`) stayed unchanged.
   - The private inspector screenshot remains excluded from Git history.

### Scope Boundaries & Unobserved Claims

- Legacy `metadata` fields and separate three-family duplicated helper paths outside the NF-01 six-family workbench remain unchanged and out of scope; this receipt claims only the verified NF-01 six-family compiler, importer/workbench, provision CLI, and rollback guarantees.
- **Unverified Python Formal Gate & Full-Tree Copy Budget:** While the Python comparator and frozen Node-to-Python tests pass (`24` tests in the NF-01 comparator set below; `23` tests in the earlier coordinator comparator run), the separate Python formal improvement gate failed to execute due to host disk exhaustion (`No space left on device`) and is being resolved separately — it is **not** claimed as passed in this receipt. Full repository archive runs (`panel-ui` rebuild and full-tree `test_figma_draft.py`) are deferred to clean isolated runs outside the shared workspace.
- Official Figma MCP was not used, cloud sync is not guaranteed, and separate browser DOM accessibility correspondence for `examples/owned-component-families/` is not claimed as live-observed in this receipt unless separately recorded.
- Static API coverage baseline counts (`664` `no-static-reference`, `70` `qualified-static-reference`, `648` `unresolved-receiver-name-reference` across `1,382` members) reflect AST source occurrences only and keep all `implementation` and `runtime_acceptance` fields `unverified`.

### Automated Repository Verification (NF-01 & Recipe/API Sync on `e6f4fd8`)

- Recipe bundle & rollback: `python3 -B library/figma-recipes/build.py --typescript <ts-5.9.3 tsc.js>` + `git diff --exit-code -- library/figma-recipes`, `python3 -B tools/workspace_recipes.py verify-helpers`, `node library/figma-recipes/test-rollback.cjs`: **all passed**.
- API & REST baselines: `tools/figma_rest_inventory.py verify` (`59` endpoints `ok`), `tools/figma_api_inventory.py verify`, `tools/figma_api_inventory.py coverage --check-baseline`, `tools/figma_api_audit.py verify` (`1,382` records): **all passed**.
- Node suites (`nf01_component_properties.cjs`, `nf01_semantic_family_runtime.cjs`, `test_family_provision_runtime.cjs`, `test_property_repair_regression.cjs`, `nf03_history_detail.cjs`, `test_workspace_activity.cjs`): **36/36 pass**.
- Python suites:
  - NF-01 & Python readback comparator (`test_component_families`, `test_declared_component_properties`, `test_rd04_component_fields`, `test_bridge_declared_property_compare`): **24/24 OK**.
  - Roadmap, API, design, and NF-03 suites (`test_next_roadmap_backlog`, `test_design_specialization`, `test_graph`, `test_workspace_recipes`, `test_figma_api_inventory`, `test_figma_rest_inventory`, `test_design_system`, `test_nf01_app_mapping`, `test_family_provision`, `test_operation_detail`): **99/99 OK**.
  - `apps/little-hands/design`: **28/28 OK**.

---

## Public Disclosure Boundaries

- Figma file keys, page IDs, node IDs, personal filesystem paths, bearer/API tokens, private inspector images, and raw private JSON dumps remain excluded from public documentation and Git history.
