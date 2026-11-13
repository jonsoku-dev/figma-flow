# Editable web import verification

This record covers browser capture, graph binding, native import, and the representative API observations gathered for the 0.30.0 candidate. The native receipts and raw browser readbacks remain in the local ignored workspace. This document omits Figma file and node identifiers.

## Browser captures

Four local template pages were captured as document-sized graphs. Their screen dimensions and element counts come from the final shipping graphs.

| Template | Observed page | Document size | Captured elements |
| --- | --- | ---: | ---: |
| Portfolio | Home page | 1265 × 7371 | 508 |
| Codeforge | Home page | 1265 × 11677 | 492 |
| Devtool | Blog page | 1275 × 1139 | 38 |
| SaaS | Signup page | 1280 × 720 | 20 |

The graphs retain visible DOM text, geometry, selected paint properties, stable element paths, and capture limitations. They do not represent every visual feature. CSS masks, filters, shadows, external media, canvas and video content, complex SVG, and unsupported background paint remain outside the conversion claim.

## Native imports

Final shipping apply and readback receipts confirm an editable frame for each captured screen.

| Template | Editable native nodes | Component instances |
| --- | ---: | ---: |
| Portfolio | 512 | 2 |
| Codeforge | 526 | 24 |
| Devtool | 41 | 1 |
| SaaS | 23 | 0 |
| **Total** | **1102** | **27** |

The native count includes text, rectangle, frame, instance, and component nodes. It excludes `VECTOR` descendants. It proves editable nodes were created for these four inputs. It does not prove pixel parity or general support for arbitrary websites. On Devtool, 21 `GeistSans` alias requests resolved to actual Geist `Regular`, `Bold`, or `SemiBold` fonts. Receipts report the family rename as a fallback. Rounded type and font handling were improved in the final pass.

## Unit checks

The focused web subsystem run passed eight Python tests and four native bridge Node tests. The broader Python suite is tracked separately.

The dedicated stable-clone release suite passed 1215 Python tests, 326 Node tests, 75 finalize tests, 18 design tests, and 2 demo tests. Every suite reported zero skips. The three additional Node cases cover component identity, instance typography readback, and rollback when a reused instance's line height differs.

### Asset and vector review

Eight local Portfolio photos, including `me.png`, and three Devtool thumbnails passed byte-hash, file-signature, native image-fill, and decoded-size checks. Four final Figma PNG previews were visually compared with the browser outputs. This was a visual comparison, not a pixel-equality measurement. Four native radial fills were verified on Codeforge. CSS masks, filters, shadows, and external media were not converted. Three external SVGs in Portfolio were not imported.

### Reapply and conflict protection

The same shipping graph with its stable ID was reapplied to all four screens without a change. On the original SaaS signup frame, the main button font size changed from 14 to 16 and then back to 14. A repeated apply preserved the intervening user edit and the final unchanged apply wrote nothing.

## Component reuse with different line heights

A real browser rendered three visually similar buttons with line heights of 20, 24 and 20 pixels. The first Figma import reported 20 pixels on all three labels. The corrected import created two mains, preserved all three native line heights and linked the third button to the first main. Applying the same graph again preserved the frame and main IDs. This additional case used a separate graph and is outside the four-template totals.

The importer now includes resolved font family/style, size, weight, line height, letter spacing, alignment and paint in component identity. Before accepting a reused instance, it reads the actual text range values and rejects a mismatch. The focused web-native test set passed 7 of 7 cases, including distinct 20/24 pixel component families and corrupt-instance rollback.

## API observations

The browser-to-Figma work recorded 253 actual typed-probe calls: 236 calls across ten observed nodes and 17 calls for the Codeforge vector follow-up. Those calls covered 50 distinct API members. A typography lab then inspected 19 exact member IDs, adding 10 net new members. The total observed set is now 150, up from the previous 127, with 1232 of 1382 audit members unobserved. The work includes `listAvailableFontsAsync`, `createComponentFromNode`, native range metadata, and text-range values. The typography specimen retained its main component and four text children on repeat. Eight before-and-after graph audit checks passed. These observations do not establish support for unobserved members. The [sanitized API observation graph](../specs/editable-web/api-observations.json) links the observed member keys to their receipt summaries.

The API priority inventory ranks every pinned audit member and carries observation status only from validated evidence edges. Its score is a work-order hint. It does not show that a method works or authorize invoking it. See [Plugin API evidence priority](api-priority.md) for the ranking contract and filters.

## Optional fixture replays

Three formerly skipped checks were replayed with the original local fixtures and native readback. All ran with zero skips:

| Case | Earlier skip reason | Replay result |
| --- | --- | --- |
| `test_shadow_troupe_light_bars_are_placeholder_bars` | The isolated checkout did not contain the private Shadow Troupe layout. | 1 pass, 0 skips |
| `test_supplied_native_evidence_and_tampering` | Operator native readback evidence was not supplied. | 1 pass, 0 skips |
| `actual saved initial Moss tint packet is rejected without writes` | The isolated checkout did not contain the private Moss Choir packet. | 16 Node tests pass, 0 skips |

The native readback replay also rejected a changed reaction destination and a changed design link. See [optional evidence replay instructions](optional-evidence-tests.md). The receipt contains input hashes and test output hashes without local paths or Figma identifiers.

## Remaining scope

These results cover the four named template pages and their supplied native readbacks. They do not establish visual parity for arbitrary pages, full support for masks, filters, shadows, external media or SVG, or coverage of every API member. Figma publishing, installation, and release-tag state are reported separately from these local observations.
