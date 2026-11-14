# Owned Production Handoff Workspace

A production-like Figma Design handoff fixture for `p2-rights-cleared-fixture`. A designer or engineer triages component handoff packages in a queue, opens one package, reads its gates, scans evidence, and records a review decision. Every file here is authored in this repository under the MIT license. The fixture uses no third-party media, fonts, templates, or network requests.

## Continuation boundary

This fixture continues two earlier owned examples without reading them at runtime:

- The surface, ink, and stroke tokens restate the sRGB values of the owned handoff baseline. Danger tokens are the only new values.
- The form and table follow the label, fieldset, and captioned-table patterns of the owned component families.

No external template name, URL, screenshot, or copied text is recorded. Only the files listed in `manifest.json` are read or served.

## Files and single source

| Path | Role | Served |
| --- | --- | --- |
| `graph.json` | Canonical graph. It owns semantic IDs, copy, screens, states, actions, components, package data, and design token values. | Yes |
| `index.html`, `styles.css`, `renderer.js` | Shell, token-only stylesheet, and renderer. They repeat no graph ID or copy, and the stylesheet has no literal color. | Yes |
| `media/*.svg` | Four repo-authored vector illustrations. | Yes |
| `README.md` | This guide. | No |
| `manifest.json` | Rights and digest manifest (`figma-flow-owned-production-workspace-manifest-v1`). It is the trust root and is not self-hashed. | No |

Every listed file has a SHA-256 digest, a sharing scope, and a retention class. Public files use `repository-history`. Runtime captures, compiled graphs, Design plans, receipts, and readbacks use `private-evidence-untracked` and stay outside Git.

## Screens and states

Each state renders directly from its route, so a reviewer can open any state without replaying clicks.

| Route | State |
| --- | --- |
| `#/queue` | Queue with rows (initial) |
| `#/queue/empty` | No rows match the filters |
| `#/queue/error` | Sync failure with a retry action (route entry only) |
| `#/review?package=pkg-field-input` | Review with no decision (initial) |
| `#/review/invalid?package=pkg-field-input` | Decision form with linked field errors |
| `#/review/recorded?package=pkg-field-input` | Decision recorded and form locked |

The renderer follows a transition only when the graph declares an action for it. The disclosure open state and the rail scroll position are local UI state and do not appear in the graph. The graph declares desktop (1440x900) and mobile (390x844) layouts.

## Verification

Run from the repository root:

```bash
python3 -B tools/owned_production_workspace.py verify
python3 -B -m unittest tests.test_owned_production_workspace
python3 -B -m unittest discover -s tests -p 'test_web_design.py'
```

`verify` rejects an undeclared file, a symlink, a path that escapes the fixture, a digest mismatch, an external URL, an email address, a personal home path, a credential marker, a Figma file link, and a graph `source` outside the manifest. The unit tests apply each rejection to a temporary copy. They also exercise the serve boundary and project the graph through `tools/review_graph.py`.

The graph keeps requirement, screen, state, action, component, and acceptance nodes `unverified` until a live browser and Design check records them. Strict-local validation reports only those pending statuses. Automated checks do not replace the rights review.

## Live runbook

Keep every output in a private directory outside Git:

```bash
export EVIDENCE_DIR="${TMPDIR:-/tmp}/figma-flow-owned-production-evidence"
mkdir -p "$EVIDENCE_DIR"
python3 -B tools/owned_production_workspace.py verify --receipt "$EVIDENCE_DIR/receipt.json"
```

Serve only approved files. The server checks the digest again on every request and sends a content security policy that blocks external requests:

```bash
python3 -B tools/owned_production_workspace.py serve --port 8893 --access-log "$EVIDENCE_DIR/served.jsonl"
```

Open the routes above at `http://127.0.0.1:8893/index.html` at both viewports. `served.jsonl` records each served path, status, and digest.

Capture the gate disclosure with the existing capture route. Repeat with `--width 390 --height 844` and a new output directory for mobile:

```bash
node tools/web_disclosure_capture.mjs \
  --url 'http://127.0.0.1:8893/index.html#/review?package=pkg-field-input' \
  --accordion '[data-slot="accordion"]' \
  --id owned-production-gates \
  --frame-key owned-production-gates \
  --width 1440 --height 900 \
  --click 'Token binding gate' \
  --click 'Token binding gate' \
  --click 'Token binding gate' \
  --click 'Component reuse gate' \
  --click 'Component reuse gate' \
  --click 'Component reuse gate' \
  --click 'Token binding gate' \
  --out "$EVIDENCE_DIR/gates-desktop"
```

Prepare the Design plans with the existing native routes. Replace `<FIGMA_FILE_KEY>` and `<FIGMA_PAGE_ID>` only in the private shell:

```bash
python3 -B tools/native_edit.py web-design \
  --graph "$EVIDENCE_DIR/gates-desktop/disclosure-graph.json" \
  --file-key "<FIGMA_FILE_KEY>" --page-id "<FIGMA_PAGE_ID>" \
  --readback-scope screens --out "$EVIDENCE_DIR/gates-desktop-plan.json"
python3 -B tools/native_edit.py graph-review \
  --graph examples/owned-production-workspace/graph.json \
  --node REQ-OPS-QUEUE --node REQ-OPS-REVIEW --node REQ-OPS-RIGHTS \
  --node SCR-OPS-QUEUE --node SCR-OPS-REVIEW \
  --file-key "<FIGMA_FILE_KEY>" --page-id "<FIGMA_PAGE_ID>" \
  --out "$EVIDENCE_DIR/review-plan.json"
python3 -B tools/native_edit.py prepare \
  --plan "$EVIDENCE_DIR/gates-desktop-plan.json" --out "$EVIDENCE_DIR/gates-desktop-bundle"
```

Apply the bundle with the registered Figma Flow plugin. Do not use the official Figma MCP.

## Out of scope

The fixture provides areas for later nodes. It does not accept them:

- `p2-faq-mobile-keyboard` still needs observed mobile and keyboard transitions and an accessibility-tree review.
- `p2-complex-render-fidelity` still needs a per-media source-to-native mapping. The rail has no autoplay timer, so `tools/web_carousel_capture.mjs` does not apply yet.
