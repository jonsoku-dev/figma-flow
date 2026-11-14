# Owned Design Handoff Baseline

Self-contained, publicly distributable Figma Design review and engineering handoff baseline requiring **zero external template sources**, **zero external fonts or media**, and **zero external network requests**.

## Artifact Boundary & Provenance

`graph.json` is the single canonical source of semantic node IDs, disclosure copy, states, and directed transitions. `manifest.json` declares MIT ownership (`../../LICENSE`), external reference non-recording rules, and per-file sharing scope across three separated layers:

| Layer | Sharing Scope | Tracked in Git | Contents |
| --- | --- | --- | --- |
| `reference-input` | `public-contract-only` | Yes | Internal disclosure interaction contract (`REF-DISCLOSURE-CONTRACT`); records zero external template names, URLs, screenshots, or copied text |
| `owned-public-baseline` | `public` | Yes | Repo-authored `graph.json`, `manifest.json`, `index.html`, `styles.css`, `renderer.js`, and `README.md` under MIT |
| `generated-private-output` | `private` | No | Browser captures (`state-*.png`, `click-*.png`, `WEB-*.json`, `observations.json`, `inputs.json`), compiled `disclosure-graph.json`, `native-edit` plans, prepared plugin bundles, and Figma readbacks |

`index.html`, `styles.css`, and `renderer.js` contain no duplicated semantic node IDs or domain copy; `renderer.js` reads `./graph.json` and `./manifest.json` at runtime to render the two single-collapsible handoff disclosures and live state/route relationships.

## Copyable CLI Guide

Run all commands from the repository root and store runtime outputs in an external private directory outside Git:

```bash
export EVIDENCE_DIR="${TMPDIR:-/tmp}/figma-flow-owned-baseline-evidence"
mkdir -p "$EVIDENCE_DIR"
```

### 1. Validate Canonical Graph & Unit Checks

```bash
python3 -B skills/figma-flow/scripts/graph.py validate examples/owned-design-baseline/graph.json --strict-local
python3 -B -m unittest tests.test_owned_design_baseline
```

### 2. Serve the Owned Baseline Locally

```bash
python3 -m http.server 8891 --bind 127.0.0.1 --directory examples/owned-design-baseline
```

### 3. Capture 3 States & 6 Directed Transitions (7 Clicks)

In a second terminal from the repository root:

```bash
node tools/web_disclosure_capture.mjs \
  --url http://127.0.0.1:8891/index.html \
  --accordion '[data-slot="accordion"]' \
  --id owned-handoff \
  --frame-key owned-handoff-disclosure \
  --width 1440 \
  --height 900 \
  --click 'Token & Typography Handoff Gate' \
  --click 'Token & Typography Handoff Gate' \
  --click 'Token & Typography Handoff Gate' \
  --click 'Single-Collapsible Transition Parity' \
  --click 'Single-Collapsible Transition Parity' \
  --click 'Single-Collapsible Transition Parity' \
  --click 'Token & Typography Handoff Gate' \
  --out "$EVIDENCE_DIR/disclosure-capture"
```

This records:
- **3 reachable states**: `All closed`, `Token & Typography Handoff Gate`, and `Single-Collapsible Transition Parity`
- **6 directed transitions**: `open` (×2), `close` (×2), and `switch` (×2)

### 4. Compile & Prepare the Figma Design Plan

Replace `<FIGMA_FILE_KEY>` and `<FIGMA_PAGE_ID>` (for example `0:1`) when targeting a live Figma Desktop document:

```bash
python3 -B tools/native_edit.py web-design \
  --graph "$EVIDENCE_DIR/disclosure-capture/disclosure-graph.json" \
  --file-key "<FIGMA_FILE_KEY>" \
  --page-id "<FIGMA_PAGE_ID>" \
  --readback-scope screens \
  --out "$EVIDENCE_DIR/disclosure-plan.json"

python3 -B tools/native_edit.py prepare \
  --plan "$EVIDENCE_DIR/disclosure-plan.json" \
  --out "$EVIDENCE_DIR/prepared-bundle"
```

Keep `$EVIDENCE_DIR` private and outside Git.
