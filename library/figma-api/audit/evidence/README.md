# Curated Plugin API evidence for the booking CTA route

This audit separates three questions: whether a member appears in the pinned Figma declaration, whether this repository calls it, and whether a named product route was observed running in Figma. The member records in [`curated.json`](curated.json) cover selected API members related to local component creation, variable binding, native readback, and component properties. They are not a sample from which to estimate support across the full SDK.

## Version pins

| Snapshot | Pin | Use in this audit |
| --- | --- | --- |
| Baseline | `v0.27.1`, commit `42379a56d677ad29296ae3ae6495742a11fbaf43`, tree `0a62cb4cc395ac41ed522927cafce0d3c0f4cdb7` | Historical source and tests only. The tag does not contain a generated per-member coverage baseline. |
| Candidate | commit `4c3b39218e5b214e0e21b762678a23dc55a3cd1f`, tree `779be49d9fe2068b763d62dcdc23505e9059f83d` | Current native implementation, tests, and the G4 booking CTA observation summarized in the verification record. This is a development candidate, not a release claim. |

The declaration inventory is pinned to `figma/plugin-typings` commit `dff4874ca083e18cd74835fd5afc5079d46866b7`, package version `1.142.0`. It contains 385 declarations and 1,382 member entries. The entries include properties and overload signatures; they are not 1,382 distinct features.

## What the candidate actually demonstrated

The G4 run in [the verification record](../../../../apps/little-hands/design/VERIFICATION.md) used the registered Design plugin on an existing page. It created an owned booking CTA main and two instances, bound the CTA background through a local primitive and semantic variable, compared Figma getter values with the browser's computed color, then imported a Figma-side edit and paired the regenerated web output again. The verification record keeps the change scope to those three consumers and that file. Raw native IDs and readback payloads are intentionally omitted here.

The `observed` member rows connect that result to the candidate calls in `native_provision.js` and `graph_token_sync.js`. Their automated test references use mock Figma hosts; the separate runtime evidence points to the actual Figma/browser verification summary. The tests alone are not treated as a runtime observation.

Several underlying API calls already existed in the `v0.27.1` source, including local variable creation and binding, component creation, instance creation, semantic metadata, and bounded readback. The feature change demonstrated here is the persistent booking CTA route joining those calls to the graph, web CSS, and a reverse import. It did not make the entire Plugin API newly supported.

The separate `design-component-properties` Design recipe was also run against Figma: its button had BOOLEAN visibility and INSTANCE_SWAP properties, local preferred component keys, default/hidden/swapped instances, and a passing native definition/reference/getter check. The recipe reuses production property helpers, but it is not the full commercial `importDesign` path or app-wide change-impact workflow. The tagged R8 record itself only observed TEXT and Visual axes; the G4 booking CTA route did not exercise BOOLEAN/SWAP. The curated member rows scope `observed` to the isolated recipe and leave the full importer integration unresolved.

## Candidate static coverage is not API support

The candidate's checked [`coverage-baseline.json`](../../coverage-baseline.json) reports:

- 52 `qualified-static-reference` members
- 553 `unresolved-receiver-name-reference` members
- 777 `no-static-reference` members

All 1,382 rows still say `implementation: unverified` and `runtime_acceptance: unverified`. The scanner covers top-level bridge JavaScript, shipped recipe entries, and the generated recipe dispatcher. It excludes tests, generated panel assets, unshipped TypeScript recipes, dynamic access, and alias resolution. A qualified `figma.*` occurrence may be a guard or read; it does not establish which overload executed. An absent occurrence does not prove the product lacks the member. These counts are not support percentages. The v0.27.1 tag has no like-for-like coverage artifact, so this audit does not claim a cross-release count change.

## Product boundaries and unverified surfaces

| Surface | Evidence-based status |
| --- | --- |
| Booking CTA local variables and color binding | Observed in the candidate G4 Design-file run for one local collection, one main and two instances. This does not establish cross-file library publication. |
| Team-library variable import | The official `importVariableByKeyAsync` declaration exists. The Flow `team-library` route offers declaration search and product access checks, but no local import operation or `teamlibrary` permission. The curated status is scoped to this Flow route; the Figma API member is not globally unsupported. |
| BOOLEAN / INSTANCE_SWAP | A separate Design example observed real native definitions, property references, preferred component keys and getter values. The full commercial importDesign route and app-wide impact workflow remain unresolved. |
| Other editors | The G4 and generated Graph Sync plugin paths target Figma Design. No runtime acceptance is claimed for FigJam, Slides, Buzz, Sites, Make, or Weave. Separate SDK scaffolds and UI paths must be assessed independently. |
| Starter plan and multi-user setup | The candidate observation used an existing Draft file with a free-plan indicator. It did not exercise an exactly three-page Starter team file, separate fresh accounts, or view-only participants. |
| Remaining inventory members | The declaration catalog records official type presence only. Uncurated members remain unverified; this audit does not infer implementation or absence for the rest of the 1,382 entries. |

`createComponent()` is documented for Figma Design. Flow's generated Graph Sync and native-edit manifests also select `editorType: ['figma']`. API declaration metadata and the candidate run do not establish plan entitlements; the plan-specific scenarios above remain separate acceptance work.

The machine-readable [`scope_findings`](curated.json) section keeps product-surface findings outside the per-member totals. It records the Dev Codegen path as a separate SDK scaffold/build only (baseline unresolved, candidate compile-only), the Widget API as outside this Plugin API denominator, the full commercial BOOLEAN/INSTANCE_SWAP import route as unresolved, and Starter-team acceptance as unresolved. These findings are scoped statements, not claims that Figma lacks those products or APIs.

## Reading the member statuses

- `observed` means candidate code and tests identify a specific member, and the verification record reports a matching live Figma/browser behavior within the stated `evidence_scope`.
- `implemented` means candidate code and automated tests exercise the member in a synthetic or local test surface; the record does not claim live Figma acceptance.
- `unsupported` is limited to the explicitly named Flow team-library import route. It is not a statement about Figma's generic Plugin API.
- Baseline fields in `curated.json` use only paths and tests present at `v0.27.1`. They are not promoted from the candidate. No baseline runtime evidence is carried because the historical verification note labels its Figma plugin observation as `0.27.0`, not `0.27.1`.

The checked inventory summary and routes can be reproduced without opening Figma:

```sh
python3 tools/figma_api_inventory.py summary
python3 tools/figma_api_inventory.py route figma.createComponent --editor figma
python3 tools/figma_api_inventory.py route figma.variables.createVariable --editor figma
```

These commands inspect declarations and context restrictions. They do not execute any member.
