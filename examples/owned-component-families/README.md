# Owned Component Families Baseline (MIT)

Self-contained public canonical example for NF-01 reusable component families (`field`, `input`, `checkbox`, `radio`, `table-cell`, `table-row`) alongside an undeclared control (`action-button`), built with zero external requests, zero private paths, and one shared JSON specification (`design.json`).

## Single Source of Truth & Three Layers

1. **Contract Policy**: `../../docs/next-roadmap/NF-01-component-families.md` (`figma-flow-component-families-v1`).
2. **Owned Public Source**:
   - `design.json`: canonical tokens, `componentFamilies` (`TEXT` / `BOOLEAN` / `INSTANCE_SWAP` with `targetKey`), `components`, and screen instances with `dom_source` metadata.
   - `graph.json`: requirements/acceptance/screen provenance linking to `design.json`.
   - `manifest.json`: three-layer provenance (`MIT`).
   - `index.html`, `styles.css`, `renderer.js`: zero-literal accessibility web demo rendering `<label for>`, `<fieldset>/<legend>`, keyboard-navigable `<table class="data-table">` (`<caption>`, `<th scope="col|row">`), and interactive sibling overrides directly from `design.json`.
   - `prepare.py`: CLI helper validating NF-01 rules and delegating compilation/plugin packaging directly to `tools/design_system.py` and `tools/figma_bridge.py`.
3. **Private Runtime Verification**: runtime screenshots, browser accessibility checks, and native plugin artifacts stay outside Git (for example `$EVIDENCE_DIR`).

## CLI & Localhost Verification

Compile `design.json` via `tools/design_system.py` and prepare a draft or reviewed plugin bundle via `tools/figma_bridge.py`:

```sh
python3 -B examples/owned-component-families/prepare.py --draft-only --out "$EVIDENCE_DIR/nf01-bundle"
```

Or run the underlying core tools directly:

```sh
python3 -B tools/design_system.py --input examples/owned-component-families/design.json --out "$EVIDENCE_DIR/nf01-preview"
```

Serve locally for browser `label`, `keyboard`, and `table` verification:

```sh
python3 -m http.server --directory examples/owned-component-families 4173
```
