# Panel and Codex parity inventory

`parity-inventory.json` is the source inventory for selectable panel actions and their Codex or Figma routes. It records checked-out source evidence, not a claim that an old screenshot or a CLI parser option proves a live native operation.

## Status meanings

- `codex_route`: the exact user outcome has a documented Codex path, with limits stated on the row.
- `figma_runtime_or_direct_interaction`: the outcome requires the actual Figma plugin/runtime, canvas, or Present interaction. A readback or command receipt may support but does not replace it.
- `retained_panel_control`: the current panel still exposes this control; a Codex path may also exist, but does not recreate the same UI interaction.
- `no_equivalent`: there is no complete outcome-equivalent path in the current source. A parser option or partial protocol is recorded in `codexPath` only as evidence of an incomplete route.

When a dispatch path changes, update the row only after tracing the selector through task admission, signed request, host dispatch, native result, and user-visible outcome. Do not infer equivalence from matching operation names. Keep file/page scope, user confirmation, partial-vs-full behavior, and readback limits on the row.

The inventory includes standalone legacy panel controls still present in source, the current task/history/Codex workspace controls, and Figma-only touchpoints. Retired or unavailable controls remain explicit rows so a migration cannot silently count their absence as a replacement.
