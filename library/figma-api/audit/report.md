# Figma Plugin API member audit

This report audits each of the 1,382 distinct candidate owner/member/signature keys. The catalog is a declaration inventory, not an implementation inventory. The audit keeps candidate source references, curated source/tests, compile-only evidence, and actual Figma observations separate.

## Pinned comparison

| Snapshot | Ref | Commit | Tree | Plugin version | API inventory |
| --- | --- | --- | --- | --- | --- |
| Baseline | `v0.27.1` | `42379a56d677ad29296ae3ae6495742a11fbaf43` | `0a62cb4cc395ac41ed522927cafce0d3c0f4cdb7` | `0.27.1` | No catalog in this tree |
| Candidate runtime | `4c3b39218e5b214e0e21b762678a23dc55a3cd1f` | `4c3b39218e5b214e0e21b762678a23dc55a3cd1f` | `779be49d9fe2068b763d62dcdc23505e9059f83d` | `0.28.0` | 1,382 members, API source 1.142.0 |

The catalog was introduced at `fad40b21f8fbb14209f50b3029bd656d40bbb1fe`. The candidate catalog and pinned source blobs match that inventory commit. The v0.27.1 baseline has no `library/figma-api` inventory, so this is not a declaration-version diff. Per-member release deltas compare exact candidate namespace routes against static source references in each runtime snapshot. Those references do not prove support.

The candidate runtime includes `figma-bridge/native_provision.js`. The report cutoff is `4c3b39218e5b214e0e21b762678a23dc55a3cd1f`. Follow-up `42752d575ebe17ca5b10a176a29d6525719685b0` changes existing native label writes and records later source/readback validation. Its diff added no API categories, but those later results are not substituted for evidence from the pinned candidate snapshot. The later G5 handoff package changes Python packaging only and is outside the audited native runtime snapshot.

## Disjoint per-release status totals

| Status | v0.27.1 baseline | 0.28.0 development candidate |
| --- | ---: | ---: |
| `observed` | 0 | 78 |
| `implemented` | 14 | 3 |
| `compile_only` | 0 | 12 |
| `unsupported` | 0 | 1 |
| `verified_unimplemented` | 0 | 6 |
| `unresolved` | 1368 | 1282 |

| Owner surface class | Members |
| --- | ---: |
| `runtime-api-member` | 249 |
| `runtime-object-member` | 471 |
| `type-contract-member` | 45 |
| `unresolved-owner-member` | 617 |

`runtime-api-member` rows have a generated namespace route. `runtime-object-member` rows belong to a concrete node or inherited node mixin. `type-contract-member` rows belong to a TypeScript type alias and are not treated as callable runtime routes. Other owners remain applicability-unresolved. None of these classes means implemented or unsupported.

## Per-release support bounds

| Release | Runtime code lower bound | Runtime native-observed lower bound | All-member code lower bound | All-member native-observed lower bound | Possible runtime upper bound |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 14 / 736 | 0 / 736 | 14 / 1382 | 0 / 1382 | 1381 / 1381 |
| candidate | 80 / 736 | 77 / 736 | 81 / 1382 | 78 / 1382 | 1374 / 1381 |

The v0.27.1 baseline has no pinned API catalog. Its rows reuse the candidate API keys only to compare routes with historical runtime source. A baseline unresolved row does not mean the API member was absent or unsupported in v0.27.1. Current evidence never fills a historical status.

Runtime lower bounds count curated `observed` and `implemented` runtime rows. The native-observed runtime lower bound counts `observed` rows only. All-member bounds also count curated type-only contract fields when their exact shape was observed. The possible runtime upper bound adds compile-only and unresolved rows that are not explicitly type-only. This is a ceiling, not a support estimate. There are 14 members with non-unresolved status in both releases; 14 of those have different status labels.

## Scoped feature findings

These findings are separate from the 1,382 member totals. A feature-level limitation does not mean the corresponding official API member is unavailable in Figma.

| Finding | v0.27.1 | Candidate | Scope |
| --- | --- | --- | --- |
| `commercial-importer-boolean-instance-swap-integration` | unresolved | unresolved | Actual Figma runtime acceptance of BOOLEAN visibility and INSTANCE_SWAP values/overrides. |
| `dev-codegen-sdk-scaffold` | unresolved | compile_only | Separate Figma Dev Mode codegen SDK scaffold; not the registered Design Flow plugin or a generic member-support claim. |
| `g4-style-raster-coverage` | unresolved | unresolved | This exact one-page G4 Starter discovery only |
| `starter-team-plan-multiuser-acceptance` | unresolved | unresolved | Exactly three-page Starter team file, fresh-account collaboration and view-only participant setup. |
| `widget-api-inventory-denominator` | unresolved | unresolved | Definition of the 1,382-member Plugin API inventory denominator; not a Widget API product support verdict. |

Curated feature-evidence files:
- `library/figma-api/audit/evidence/curated.json` SHA-256 `5f3002da316ae9b66e1ecaf30cbd876649dd931350fdebede2f7386b40715e15`
- `library/figma-api/audit/evidence/design-recipes.json` SHA-256 `8bde35357a88cb32a989c47b2b72a7bd496ea57bb2658ee18e759cd9785b4054`
- `library/figma-api/audit/evidence/editor-gaps.json` SHA-256 `6e3b594f1f283548d037aedd8a30c0ca9105e6481cd42e24ac72aaa385805819`
- `library/figma-api/audit/evidence/editor-recipes.json` SHA-256 `0fd71644d509db8598f7ee727d5b1a99a8db73a0c16ebbbe44decad87807d730`
- `library/figma-api/audit/evidence/native-read.json` SHA-256 `25ca2efb784fa317ebc1deff342e96319776bfef2416edc69ae47248f541cde7`

## Separate API denominators

- **figma-widget-api** is excluded. Source 1.13.0 at `8815555bab1cf358ee9958fe2fa2cf46f77f3fb6` is pinned separately. Widget API declarations have a separate pinned source under library/figma-widget. They are not part of the @figma/plugin-typings Plugin API denominator.

`unsupported` requires an explicit scoped limitation. `verified_unimplemented` requires a feature-route review and exact declaration lookup. A missing source reference, missing route, or absent old catalog leaves a row unresolved. A static reference and a test name mention are locators only.

## Verified gaps in shipped routes

The following methods are verified absent only from the stated prebuilt Flow routes and unmodified recipe. These entries do not claim that Figma lacks the API or that a user-authored SDK plugin cannot call it.

| Member | Scope checked |
| --- | --- |
| `PluginAPI.createCodeBlock` | FigJam prebuilt native operations available to a user running the shipped Flow application or an unmodified bundled recipe. Inspected library/figma-recipes/figjam-diagram.ts and the SDK template/recipe manifests against the official return type and operation; the recipe provides no corresponding operation. Writing new SDK code or using the Figma UI remains possible. |
| `PluginAPI.createSlideRow` | Slides prebuilt native operations available to a user running the shipped Flow application or an unmodified bundled recipe. Inspected library/figma-recipes/slides-slide.ts and the SDK template/recipe manifests against the official return type and operation; the recipe provides no corresponding operation. Writing new SDK code or using the Figma UI remains possible. |
| `PluginAPI.createSticky` | FigJam prebuilt native operations available to a user running the shipped Flow application or an unmodified bundled recipe. Inspected library/figma-recipes/figjam-diagram.ts and the SDK template/recipe manifests against the official return type and operation; the recipe provides no corresponding operation. Writing new SDK code or using the Figma UI remains possible. |
| `PluginAPI.createTable` | FigJam prebuilt native operations available to a user running the shipped Flow application or an unmodified bundled recipe. Inspected library/figma-recipes/figjam-diagram.ts and the SDK template/recipe manifests against the official return type and operation; the recipe provides no corresponding operation. Writing new SDK code or using the Figma UI remains possible. |
| `PluginAPI.getSlideGrid` | Slides prebuilt native operations available to a user running the shipped Flow application or an unmodified bundled recipe. Inspected library/figma-recipes/slides-slide.ts and the SDK template/recipe manifests against the official return type and operation; the recipe provides no corresponding operation. Writing new SDK code or using the Figma UI remains possible. |
| `PluginAPI.setSlideGrid` | Slides prebuilt native operations available to a user running the shipped Flow application or an unmodified bundled recipe. Inspected library/figma-recipes/slides-slide.ts and the SDK template/recipe manifests against the official return type and operation; the recipe provides no corresponding operation. Writing new SDK code or using the Figma UI remains possible. |

## Row-level data

[`members.json`](members.json) contains every row, the official declaration URL and source lines, route and permission metadata, exact baseline/candidate static references, test name mentions, curated evidence, and release deltas. Review each `status_basis` and evidence object before using a row as a product claim. The files under `evidence/` hold the separately reviewed per-member and scoped feature records.

## Reproduction

Run the pinned TypeScript 5.9.3 scanner and rebuild the report:

```sh
python3 tools/figma_api_audit.py generate --typescript PATH_TO_TYPESCRIPT_5_9_3
python3 tools/figma_api_audit.py verify --typescript PATH_TO_TYPESCRIPT_5_9_3
```

The tool reads the baseline and candidate by their pinned Git refs, checks their commit/tree IDs, and writes only `library/figma-api/audit/members.json` and `report.md`. It does not edit the existing API catalog. It makes no Figma MCP call or native runtime claim.
