---
name: graph-ssot
description: Use when a graph must own component design values, export them to Figma and web, import designer edits, or verify a native/web round trip.
---

# Graph-owned component design

Resolve tools relative to this installed plugin root. Read [the command and schema guide](../../examples/graph-ssot/README.md) before pairing or importing. The canonical values live in graph.design_system.tokens. Component properties contain token references, and generated web modules/stylesheets carry the graph hash.

Before creating or critiquing UI, follow the [bundled skill dependency contract](../figma-flow/references/skill-dependencies.md) and run the installed plugin's `tools/skill_dependencies.py --check`. Read verified bundled guidance within the graph-owned design constraints. Before browser proof, apply [target origin registration](../figma-flow/references/browser-access.md) through the current authorized host tools.

## Establish the source

1. Read the selected graph and component native/web references. Inspect user changes. Preserve existing files and actual native getter evidence.
2. Discover the exact Figma file, source page and additional declared instance pages with graph_sync.py discover. Run the generated local plugin in that file and save its actual getter JSON.
3. Use explicit export --adopt to migrate existing components to the graph's owned token namespace. Check actual old bindings/values and every instance of each declared main. Shared variables outside the declared graph scope must stay untouched. Each normal/disabled visual variant needs its own graph property scope.
4. Import graphStylesheet or muiComponents from the generated web module. MUI length values are explicit CSS pixels. Add the emitted graphSha256 as data-graph-sha on each matched element. Render actual web proof with exported web-probe.js through the current authorized browser.
5. Apply the generated Figma plan, save the actual focused getter, and pair with native plan, exact generated module and actual browser proof. A generated file alone cannot complete pairing.

## Change and reconcile

- Graph edits: update token roots through graph_design_system.update_graph_values with the expected graph hash; export the graph+pairing; apply in Figma; reload/read the real web; pair the actual current native/web result.
- Native variable edits: save Read native values, preview graph_sync.py import, then --apply. Changes land in the graph first and regenerate the web module. Export with the same actual native readback to reconcile the native baseline, then verify/pair.
- Designer direct main/instance edits: preview import --node-edit-scope component. Show affected mains, all connected instances and web selectors. Promote one unambiguous edit to that graph component only. Conflicting edits on a shared token stop the import. After --apply, export with the accepted --import-report and exact actual readback; the repair plan restores canonical bindings and guards against further edits. Verify native and rendered web before pairing.
- Interrupted graph/web publication: keep the recovery journal. Use recover only when its expected graph hash still matches; otherwise export the current graph again. A conflict never advances the baseline.

## Acceptance

Test font size/family, spacing and at least one visual property in both directions on the real component. Read main/instance values and bindings, CSS pixels/colors and actual graph hashes. Also inspect normal/error/loading/success and mobile, and verify a nonparticipating neighboring component stays unchanged. Preserve command exit codes and actual PNGs. Existing user-selection and design-acceptance gates retain their own meaning.

The current adapter handles declared typography/spacing, solid color/borders, radius/gap and supported dimensions. Fixed width/height require FIXED sizing. Mixed paints, external paint styles and changes requiring unmapped structure are conflicts. Component-scope import changes the declared logical component; an independent per-instance variant needs an explicit graph declaration and web selector.
