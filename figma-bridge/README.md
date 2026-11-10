# Local Figma Design bridge

The unpaired development plugin imports reviewed local design data without MCP,
API keys, network requests or model calls. The optional 0.9.0 paired companion
connects only to its local loopback helper as described below. The design compiler's `resolved.json` is the
bounded input format: resolved tokens, component variants and screen elements of
kind heading, text or component. It does not parse HTML or implement arbitrary
application behavior. Optional `target_screen` becomes native click navigation;
`action_id`, trace IDs and annotations are declared semantic metadata, not proof
that the application action ran.

## Primary route: one registered Figma Flow workspace

Use the [install-once guide](../docs/figma-guide.md#5-고정-작업공간-등록과-검토-작업-준비). Initialize a private workspace with your own existing Figma-issued manifest ID, then register only its stable manifest:

```sh
python3 tools/figma_workspace.py init --workspace PRIVATE_DIR --id-from OWN_MANIFEST.json
python3 tools/figma_workspace.py prepare --workspace PRIVATE_DIR \
  --key workshop-review --title "Workshop review" --project "Workshop" --kind review -- \
  --manifest PROJECT/review/directions.json
python3 tools/figma_workspace.py list --workspace PRIVATE_DIR
```

`prepare` records the originating `CODEX_THREAD_ID`, or an explicit validated `--thread-id UUID`. If neither exists, preparation remains offline and chat is disabled; malformed explicit UUIDs are rejected. Workspace preparation currently uses POSIX protected files on macOS/Linux; Windows-local preparation retains the standalone compatibility route. The arguments after `--` are generator flags only; the workspace owns output paths and plugin identity. `import`, `review`, `discover` and `sync` tasks appear under **준비된 작업**. **열기** opens the chosen task UI without writing; its original explicit action starts the operation. **작업 목록으로** returns home after completion.

Keep `PRIVATE_DIR/manifest.json` registered. It references immutable code/UI generations; copy the whole private workspace, including hidden directories, when transferring machines. A changed task key requires the current `list` revision as `prepare --replace-expected REVISION`; an unchanged retry is idempotent. Close the older running window and reopen the same plugin to load the new task list.

Private plugin data belongs to the Figma plugin ID that wrote it. Foreign-ID packages and paired state cannot be relabeled into ownership. Preserve the original plugin/ID or prepare an explicit migration from actual old readback. Do not share the private workspace or any relay credentials as a public bundle. [Chat handoff](../docs/figma-guide.md#11-작업을-준비한-codex-채팅으로-연결) opens the task's recorded thread and previews selection/request content before an explicit copy or optional queue action.

For existing private loopback workflows, workspace `import` may use `--paired-state PRIVATE_STATE` only when its plugin ID, file/page, source hash and running endpoint match. Paired direction review uses explicit `--pair-dir` plus `--receiver-port` on a `review` task and the original receiver receipt/download contract. See the [private receiver commands](../docs/installation-and-updates.md#6-5-선택적-로컬-동기화-사용-중이라면); these do not send a chat message.

## Default local control after manual launch

The user manually runs Figma Flow in the target Design file once per plugin session. Codex may then use the explicit local controller instead of repeating UI clicks:

```sh
python3 tools/figma_control.py enable --workspace PRIVATE_DIR --port 43180
python3 tools/figma_workspace.py refresh --workspace PRIVATE_DIR
python3 tools/figma_control.py serve --workspace PRIVATE_DIR
# From another Codex execution, with actual scope/revision from the prepared task:
python3 tools/figma_control.py run --workspace PRIVATE_DIR --key workshop-review \
  --operation create --file-key FILE --page-id PAGE --expected-revision REVISION --timeout 120
```

`review/create`, `discover/read`, `sync/read|apply` and `import/import|read` are bounded operations; an admitted paired import can also `sync`. The returned actual `readback` must pass the normal checker. Inspect `status --workspace PRIVATE_DIR --id OPERATION_ID` after asynchronous or uncertain results. The service cannot evaluate arbitrary remote code, launch a closed plugin in secret, or choose another file. `--focus-page` requires exact signed task file/page pins.

Prepare/refresh updates the stable manifest and metadata. Desktop auto-reload behavior varies, so verify the running revision and manually reopen the same plugin if necessary. Manual panels remain supported. Choose **한국어 / English / 日本語** from the home language selector; user-authored names, raw JSON and native diagnostics remain unchanged. **History / 이력 / 履歴** distinguishes requests, completion, readback and reported verification; actual artifacts remain the evidence.

## Standalone compatibility

The commands below describe legacy standalone packages and the optional paired companion. They are not the default registration path for new workspace tasks. Their existing ID, private-data scope and native evidence checks remain in force.

## One-button local app sync (0.9.0; same 0.8.0 setup)

Start the helper once from the plugin root. Use the original imported
`resolved.json`, the actual native import page ID (`2:77` is an example), the
Figma file key and your Figma-assigned numeric development plugin ID. Keep the
private state directory outside the app project.

```sh
python3 tools/serve_figma_sync.py --project PROJECT --resolved ORIGINAL_RESOLVED --page-id 2:77 --file-key FILE_KEY --plugin-id FIGMA_ID --state-dir PRIVATE_DIR [--prior-sync PRIOR_0_7_APPLIED]
```

Import the printed `PRIVATE_DIR/plugin/manifest.json` in Figma Desktop under
**Plugins → Development → Import plugin from manifest**. Keep the original plugin
identity so it can read that plugin's private metadata. Open the paired file and
import page, then run the plugin. Without prior applied history, click **앱에 반영**
on the unchanged imported design first to save its baseline. After that, edit
supported token values and click the same button to read only the paired current
page and apply its changes to the app. If migrating from 0.7.0, provide the exact
previous successfully applied outer wrapper directory with `--prior-sync` during
initial setup; a preview-only plan cannot seed the chain.

Keep the helper running. Restart with the same private directory and unchanged
pairing inputs to resume its saved chain. Keep the same file key, native page,
original source stamp and protected apply chain. Token topology or variable-binding
changes require a newly imported bundle/page and baseline; preserve the old chain. The generated plugin and state contain
a secret pairing key: keep them private, outside the app, and never share or
publish them. The paired companion uses an authenticated loopback write API;
remote Figma MCP is unnecessary. Legacy unpaired kits remain network-disabled.

A separate read-only loopback server serves the real app comparison. Expected
colors and dimensions come from native Figma measurements, rather than generated
CSS. Version 0.9.0 adds all four padding sides, all four corner radii and the
font size of a variable-bound button label, compared with actual browser styles
in CSS px. During a live sync click with paired prior state available, capture
the real app before and after application and compare each with its native values.
Missing or mixed native values, ambiguous labels/bindings and absent historical
app capture remain `unknown`; generated CSS cannot supply historical measurements.
Current selector support is limited to the review-cards example. Unsupported
fields and ambiguous mappings stay unverified. Graph-declared screens,
static class candidates and actual browser comparison results are distinct
observations. A passing unit or mocked Plugin API test does not establish native
button execution, visual parity or actual app interactions. Verify affected states
and real pointer/keyboard behavior separately. See the [local sync guide](../skills/figma-flow/references/token-sync.md)
for scope, manual JSON planning/apply and chained edits.

## Build and open (unpaired import/export)

1. Generate and review the local design-system output. Inspect `resolved.json`
   along with its wireframe/styled previews; this command does not perform review.
2. In Figma Desktop, use **Plugins → Development → Create new plugin** to obtain
   your Figma-assigned numeric plugin ID. This one-time local setup does not use
   MCP or model tokens. Obtain the SHA256 of the exact reviewed `resolved.json`
   bytes, then run:

   ```sh
   python3 tools/figma_bridge.py --input PATH/resolved.json --reviewed-sha256 REVIEWED_SHA256 --out NEW_DIRECTORY --plugin-id YOUR_FIGMA_ID \
     --selection PROJECT/reviews/rN/selection.json --product-graph PROJECT/graph.json
   ```

   This runs only after a real user selected one direction
   ([direction selection](../skills/figma-flow/references/direction-selection.md)). Add
   `--batch … --asset-receipts …` when the selected scope needs generated assets.
   Before a selection, use `--draft-only`, which writes `draft-preview.json` and no plugin.

3. In Figma **Desktop**, open a Design file, open **Plugins → Development → Import
   plugin from manifest**, and choose `NEW_DIRECTORY/manifest.json`. Run the plugin
   under Development. Importing a local development plugin is distinct from
   publishing a Community plugin. A build without `--plugin-id` still needs the
   selection; it reports `manifest_identity: obtain-figma-id-before-import` and is not
   claimed import-ready.
   The compiler never invents a Figma identity. An ID's existence or ownership
   cannot be verified offline; use your own Figma-created development ID.
4. Click **가져오기 · 기존 페이지 열기**. Import creates a dedicated page and
   local variable collection. Repeating it first rechecks required native annotations, instance links and token bindings, then focuses the same payload and preserves edits. Missing native semantics block success; existing user edits are never removed. A changed payload requires explicitly checking **별도 페이지로 새로 가져오기**. That action adds a page and collection; it never updates earlier
   imports. Do not use fresh-page mode when you only want to find an existing
   import. A failed import rolls back only the objects that attempt created.

Keep the Figma-assigned plugin ID when rebuilding if you want the same plugin's
private metadata to remain discoverable. A different plugin identity cannot read
the old plugin's private data. Duplicate pages made explicitly with the fresh-page
control intentionally have the same semantic IDs but distinct native Figma IDs.

## Editable result and current readback

Screens use vertical auto-layout frames and editable text. Each component variant
is a native main component; groups with multiple variants become native component
sets with a `Variant` property when `combineAsVariants` is available, including single-variant definitions. Repeated uses are instances with editable text
overrides. If native sets are unavailable, individual components remain and the
UI reports that limitation. Local color, dimension/number, string/font-family and boolean variables
retain aliases. Supported bindings are background/text/border color, padding,
corner radius, spacing, font size and available font families. Declared fonts must be
installed; the import fails instead of falling back to Inter. Unsupported variant
properties are rejected at compile time. The compiler writes `expected-native-handoff.json`, a shared-validator contract derived from reviewed screen/control semantic IDs, declared actions/states, component references and supported native token bindings. No manual recreation of expected native IDs is needed. The compiler derives required screen/control annotations from trace IDs, declared action/target/state, component variants and token properties, including any supplied prose. The native `node.annotations` API must retain those notes. Unsupported or missing required annotations fail the import and roll back only newly created objects; metadata fallback cannot pass. Before success, both new and repeated imports check real instance-to-main-component links and native variable aliases on used screen components. A library of unused components or unbound token values cannot pass.

Offline compilation and SVG/manual exports remain available for historical or local-only designs. Their generated bundle is `pending_native_handoff`, never native acceptance. Text/action annotations describe declared behavior; they do not prove application action execution.

Figma numeric dimensions use the same fixed conversion as the local SVG preview:
`1rem = 16px`; this is an explicit design-artifact assumption, not a measurement of
the browser's root font size. Original CSS dimension values/units and token CSS
names stay in variable plugin data and readback. Color alpha is stored in the
RGBA variable value; bound base paints keep opacity 1 to avoid applying it twice.

After editing text, styles, variables, components or prototype reactions in Figma,
click **현재 디자인 읽기**, then **JSON 파일 저장**. The optional **JSON 원문 확인** disclosure also
supports manual copying if the host blocks a download. The file contains actual
native IDs, current geometry/text/style values and bound-variable aliases, current
instance-to-main-component IDs, reaction destination IDs, collection modes and
current variable values. Scope is **the currently open page generated by this
plugin**, including user-added children; open that page before reading. Other
pages are excluded. Declared annotations/action IDs/trace IDs are separate from observed
attributes under `declared_metadata`; actual annotations are exported as
`annotations`, with an observed/unavailable status. A copied node retains its declared ID; local
inspection reports native IDs rather than treating declared identity as unique.

Inspect a saved readback locally:

```sh
python3 tools/figma_bridge.py --check-readback PATH/figma-flow-readback.json --input PATH/resolved.json
```

This checks the export shape, unique native IDs, and reaction/variable references.
With `--input`, each page stamped with the source SHA is compared independently
against that reviewed source. Screen coverage is never combined across pages or
source hashes. `origin_stamp_match` only describes that declared source stamp.
`matches_supplied_source` is true only when every matching page's compared current
state matches: token native names/types/values/aliases across exported collection
modes, screen names, element text and native click targets. Per-page
`import_checks` report `match`, `changed`, `missing` or `unsupported`, including
the current values and native target IDs. Alias target value edits are detected
even when the alias reference itself is unchanged. Each page uses only its own
declared collection; other imports cannot supply missing tokens or screens.

For an acceptance gate, add `--require-match` to the inspection command with `--input`. A mismatch or missing required native semantics exits nonzero. The gate also checks generated screen/control annotations, actual instance-to-main-component links and bindings on screen instances. Historical exports remain inspectable with partial coverage; plugin metadata and source stamps cannot substitute for native evidence. The shared `native_handoff.evaluate` gate runs automatically against the reviewed-source-derived contract for every matching page. The report includes this generated contract and each page's observed native screen specification. `--expected EXPECTED.json` can add a stricter custom contract; it does not enable or bypass the default gate. Native per-corner radius aliases are checked individually.

Generate the observed screen specification from the actual saved readback and the automatically compiled contract:

```sh
python3 tools/native_handoff.py --readback PATH/figma-flow-readback.json --contract NEW_DIRECTORY/expected-native-handoff.json --out NEW_HANDOFF_DIRECTORY
```

A single exported page is selected automatically; for multiple imports use the observed page ID with `--page-id`. The output contains `report.json`, `screen-spec.json` and `screen-spec.md`. Bind this same readback and generated contract in the project's `bindings.native_handoff` and run `tools/check_project.py` to pin their hashes to the project gate. Static screens may have no controls; actual static reusable instances still require native annotations and bindings. A whole design with only unused components cannot satisfy native handoff.

Ordinary drift is reported as JSON with a false match and explicit status; a
successful inspector process means inspection completed, not that state matched.
Malformed exports fail. Targets outside the export scope are reported rather
than silently discarded. The compared state does not cover arbitrary visual
edits, full binding parity or action execution. It does not authenticate the
origin of supplied JSON or assert visual parity. A digest in declared metadata
alone is never live execution evidence. Missing source stamps yield
`current_compared_state: source-mismatch`, not a current-state match.

## Verification boundary

Offline tests exercise the compiler and Plugin API lifecycle with an in-memory
double: first import, idempotent focus preserving edits, explicit fresh import,
changed-payload protection, variable aliases/bindings, native variant-set creation,
native annotations and unavailable-host rejection, instances, navigation,
current readback and failure rollback. Explicit simulated readback fixtures test
current value/alias/text/reaction drift and prevent cross-page coverage unions.
The automated lifecycle cases are mocked API tests. In the separate 0.6.1 local
Figma Desktop rehearsal, a Figma-assigned development ID was used to import the
review-cards design. The file contained two editable screens per import, a
component set and instances, 13 variables per collection, annotations and four
click reactions. The generated card-to-question reaction played in Figma.
Re-import preserved an edited frame name and did not create a duplicate.
Exporting after a palette and screen-name change made the strict inspector fail;
restoring them made it pass. UI messages use a session handshake. The frame
layout sets its size before enabling vertical auto-sizing. The inspector covers
declared bindings and values; actual frame fit and prototype playback are checked
separately in the editor.

## API references

API shapes were checked against Figma's first-party documentation and plugin
typings (retrieved 2026-11-08):

- [Manifest and network policy](https://developers.figma.com/docs/plugins/manifest/)
- [Variables and bindings](https://developers.figma.com/docs/plugins/working-with-variables/)
- [Node properties, reactions and plugin data](https://developers.figma.com/docs/plugins/api/node-properties/)
- [Native annotations](https://developers.figma.com/docs/plugins/api/Annotation/)
- [Component set creation](https://developers.figma.com/docs/plugins/api/figma/#combineasvariants)
- [Official Plugin API typings](https://github.com/figma/plugin-typings/blob/master/plugin-api.d.ts)

The runtime uses dynamic-page-compatible async page, variables and reaction APIs;
`createVariable` and `setBoundVariable` receive objects rather than deprecated ID
overloads. Native actions use `actions` and `resetScrollPosition`. The development manifest enables the private Plugin API only to read the actual current file key for native evidence pinning, as in the paired companion. This grants no remote transport; unpaired builds retain network `allowedDomains: ["none"]`. No proposed APIs are enabled.
